"""Kontostand-Verlauf aus MoneyMoneys eigener Datenbank -- einmalig, auf Klick in der Oberflaeche (Einrichtung).

MoneyMoneys Skript-Schnittstelle liefert nur aktuelle Salden; die Kurve der Kontostaende (v. a. Depots) steht nur in seiner
Datenbank (SQLCipher, verschluesselt mit dem MoneyMoney-Passwort). Der Weg ist bewusst eng gefasst:

* Keine macOS-Freigabe fuer Kontor: Der Finder zeigt die Datei (Kontor selbst greift nicht auf MoneyMoneys Ordner zu),
  du ziehst sie ins Browserfenster; sie kommt ueber 127.0.0.1 an und liegt nur im Arbeitsspeicher, nie auf der Platte.
  MoneyMoney muss beendet sein; an seiner Datei aendert sich nichts.
* Das Passwort erreicht Kontor nie. Ein kleiner macOS-Helfer (mm_historie.swift) wird nur fuer diesen einen Vorgang
  in einem privaten Ordner uebersetzt, fragt das Passwort im eigenen Fenster ab, gibt ueber eine private Pipe nur die
  daraus berechneten Schluessel zurueck und wird danach samt Ordner geloescht.
* Entschluesselt wird im Arbeitsspeicher dieses Prozesses (macOS CommonCrypto) an Ort und Stelle; SQLite liest
  schreibgeschuetzt direkt aus diesem Puffer (keine Kopie, keine Zwischendateien). Danach werden Schluessel und Puffer
  mit Nullen ueberschrieben. Spitzenbedarf an Arbeitsspeicher: etwa die Dateigroesse.
* Waehrenddessen keine Netzverbindung von Kontor (Update-Pruefung ruht); protokolliert werden nur Zaehlerstaende.
* Gesucht und verglichen wird in SQLite; in Python kommen nur Konto-Kennungen, Datumswerte und Betraege an. Tabellen
  und Spalten, deren Namen nach Zugangsdaten klingen, werden nicht angesehen. Uebernommen werden nur Monatsend-Staende,
  und nur, wenn die juengsten Werte zum aktuellen Saldo aus MoneyMoney passen.
"""
from __future__ import annotations

import ctypes
import gc
import os
import shutil
import sqlite3
import subprocess
import sys
import re
import tempfile
import threading
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
HELPER_SRC = os.path.join(HERE, "mm_historie.swift")
MAX_DB = 2 * 1024 * 1024 * 1024        # Obergrenze fuer die hochgeladene Datei

# Schluesselableitung je SQLCipher-Generation: (Name, Hash fuer PBKDF2, Runden). Seitengroesse und reservierte Bytes
# (IV + Pruefsumme) werden an der entschluesselten Kopfzeile erkannt, nicht angenommen.
FORMATS = [("SQLCipher 4", "sha512", 256000), ("SQLCipher 3", "sha1", 64000)]
PAGE_SIZES = (1024, 4096, 2048, 8192, 16384, 32768, 65536)
RESERVES = (48, 80, 32, 64)
SQLITE_HEADER = b"SQLite format 3\x00"

AKTIV = threading.Event()        # waehrend des Vorgangs gesetzt: keine Update-Pruefung (keine Netzverbindung)


class HistorieError(Exception):
    pass


def _wipe(buf) -> None:
    """Puffer mit Nullen ueberschreiben (bytearray)."""
    if isinstance(buf, bytearray) and buf:
        ctypes.memset((ctypes.c_char * len(buf)).from_buffer(buf), 0, len(buf))


# -- Passwortfenster (Helfer nur fuer diesen Vorgang) -----------------------------------------------------

def keys_from_dialog(salt: bytes) -> List[bytearray]:
    """Helfer in einem privaten Ordner uebersetzen, Passwort im eigenen Fenster abfragen lassen, Ordner loeschen.
    Zurueck kommen nur die Schluessel je Format (bytearray, werden nach Gebrauch ueberschrieben)."""
    if sys.platform != "darwin":
        raise HistorieError("Nur auf dem Mac möglich.")
    work = tempfile.mkdtemp(prefix="kontor-")          # 0700, nur fuer diesen Benutzer
    try:
        exe = os.path.join(work, "Kontor")             # der Name erscheint als Programmname im Fenster
        try:
            r = subprocess.run(["swiftc", "-O", "-o", exe, HELPER_SRC], capture_output=True, text=True, timeout=300)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            r = None
        if r is None or r.returncode != 0:
            subprocess.run(["xcode-select", "--install"], capture_output=True)     # macOS bietet die Installation an
            raise HistorieError("Für das Passwortfenster fehlen Apples Entwicklerwerkzeuge – macOS bietet die Installation "
                                "gerade an. Danach erneut versuchen.")
        proc = subprocess.Popen([exe, salt.hex()] + ["%s:%d" % (h, n) for _x, h, n in FORMATS],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin"})
        buf = bytearray(1024)
        got = 0
        try:
            while got < len(buf):
                n = proc.stdout.readinto(memoryview(buf)[got:])
                if not n:
                    break
                got += n
            code = proc.wait(timeout=600)
        except subprocess.TimeoutExpired:
            proc.kill()
            _wipe(buf)
            raise HistorieError("Keine Eingabe im Passwortfenster (Zeitlimit).")
        if code == 1:
            _wipe(buf)
            raise HistorieError("abgebrochen")
        keys: List[bytearray] = []
        try:
            for line in bytes(buf[:got]).split(b"\n"):
                line = line.strip()
                if line:
                    keys.append(bytearray(bytes.fromhex(line.decode("ascii"))))
        except ValueError:
            keys = []
        _wipe(buf)
        if code != 0 or len(keys) != len(FORMATS) or any(len(k) != 32 for k in keys):
            for k in keys:
                _wipe(k)
            raise HistorieError("Das Passwortfenster konnte nicht angezeigt werden.")
        return keys
    finally:
        shutil.rmtree(work, ignore_errors=True)


# -- Entschluesseln im Arbeitsspeicher --------------------------------------------------------------------

def _aes_cbc() -> Callable[[bytearray, bytes, bytearray, int, int], None]:
    """AES-256-CBC (ohne Auffuellen) an Ort und Stelle: buf[off:off+n] wird durch den Klartext ersetzt.
    macOS: CommonCrypto im eigenen Prozess (erlaubt Ein- und Ausgabe im selben Puffer)."""
    if sys.platform == "darwin":
        lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        fn = lib.CCCrypt
        fn.restype = ctypes.c_int32
        fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p,
                       ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

        def dec(key: bytearray, iv: bytes, buf: bytearray, off: int, n: int) -> None:
            k = (ctypes.c_char * len(key)).from_buffer(key)
            area = (ctypes.c_char * n).from_buffer(buf, off)
            moved = ctypes.c_size_t(0)
            st = fn(1, 0, 0, ctypes.addressof(k), len(key), iv, ctypes.addressof(area), n, ctypes.addressof(area), n, ctypes.byref(moved))
            if st != 0 or moved.value != n:
                raise HistorieError("Entschlüsselung fehlgeschlagen (%d)." % st)
        return dec
    try:   # andere Systeme (nur Tests)
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:  # pragma: no cover
        raise HistorieError("Entschlüsselung nur auf dem Mac verfügbar.")

    def dec2(key: bytearray, iv: bytes, buf: bytearray, off: int, n: int) -> None:
        d = Cipher(algorithms.AES(bytes(key)), modes.CBC(bytes(iv))).decryptor()
        buf[off:off + n] = d.update(bytes(buf[off:off + n])) + d.finalize()
    return dec2


def _page1_ok(buf: bytearray, key: bytearray, page: int, reserve: int, dec) -> bool:
    if len(buf) < page:
        return False
    probe = bytearray(buf[16:32])
    dec(key, bytes(buf[page - reserve:page - reserve + 16]), probe, 0, 16)
    # Kopfbytes 16..23 des SQLite-Formats: Seitengroesse, Schreib-/Leseversion, Reserve (>= IV + Pruefsumme), 64, 32, 32
    ps = int.from_bytes(probe[0:2], "big")
    ok = (ps == page or (ps == 1 and page == 65536)) and probe[2] in (1, 2) and probe[3] in (1, 2) and reserve <= probe[4] and probe[5:8] == b"\x40\x20\x20"
    _wipe(probe)
    return ok


def decrypt_in_place(buf: bytearray, keys: List[bytearray]) -> str:
    """Hochgeladene Datenbank im selben Puffer entschluesseln (danach Klartext; der Aufrufer ueberschreibt ihn).
    Format an der Kopfzeile erkennen; falsches Passwort -> Fehler, Puffer unveraendert."""
    dec = _aes_cbc()
    for (name, _h, _r), key in zip(FORMATS, keys):
        for page in PAGE_SIZES:
            if len(buf) % page:
                continue
            for reserve in RESERVES:
                if not _page1_ok(buf, key, page, reserve, dec):
                    continue
                for i in range(len(buf) // page):
                    base = i * page
                    start = 16 if i == 0 else 0
                    iv = bytes(buf[base + page - reserve:base + page - reserve + 16])
                    dec(key, iv, buf, base + start, page - reserve - start)
                buf[0:16] = SQLITE_HEADER
                return name
    raise HistorieError("Passwort falsch (oder unbekanntes Datenbankformat).")


# -- Datenbank im Arbeitsspeicher (SQLite direkt auf dem Puffer, ohne Kopie) ------------------------------

def _sqlite_lib():
    if sys.platform == "darwin":
        return ctypes.CDLL("/usr/lib/libsqlite3.dylib")
    import ctypes.util
    import _sqlite3
    for name in (getattr(_sqlite3, "__file__", None), ctypes.util.find_library("sqlite3"), "libsqlite3.so.0", None):
        try:
            lib = ctypes.CDLL(name)
            lib.sqlite3_deserialize
            return lib
        except (OSError, AttributeError):
            continue
    raise HistorieError("SQLite nicht gefunden.")


class MemDB:
    """Nur-Lese-Datenbank direkt auf einem Puffer (sqlite3_deserialize ohne Kopie, schreibgeschuetzt). SQLite legt
    keine zweite Kopie an; nach close() ueberschreibt der Aufrufer den Puffer. Abfragen liefern nur Zahlen und Texte."""

    def __init__(self, buf: bytearray):
        lib = self.lib = _sqlite_lib()
        P, I, I64 = ctypes.c_void_p, ctypes.c_int, ctypes.c_int64
        for name, res, args in (("sqlite3_open", I, [ctypes.c_char_p, ctypes.POINTER(P)]), ("sqlite3_close", I, [P]),
                                ("sqlite3_deserialize", I, [P, ctypes.c_char_p, P, I64, I64, ctypes.c_uint]),
                                ("sqlite3_prepare_v2", I, [P, ctypes.c_char_p, I, ctypes.POINTER(P), P]),
                                ("sqlite3_step", I, [P]), ("sqlite3_finalize", I, [P]), ("sqlite3_column_count", I, [P]),
                                ("sqlite3_column_type", I, [P, I]), ("sqlite3_column_int64", I64, [P, I]),
                                ("sqlite3_column_double", ctypes.c_double, [P, I]), ("sqlite3_column_text", ctypes.c_char_p, [P, I]),
                                ("sqlite3_bind_int64", I, [P, I, I64]), ("sqlite3_bind_double", I, [P, I, ctypes.c_double]),
                                ("sqlite3_bind_text", I, [P, I, ctypes.c_char_p, I, P]), ("sqlite3_errmsg", ctypes.c_char_p, [P])):
            f = getattr(lib, name)
            f.restype, f.argtypes = res, args
        self.db = P()
        self._area = (ctypes.c_char * len(buf)).from_buffer(buf)
        if lib.sqlite3_open(b":memory:", ctypes.byref(self.db)) != 0:
            self.close()
            raise HistorieError("SQLite konnte nicht geöffnet werden.")
        # 4 = SQLITE_DESERIALIZE_READONLY: SQLite liest direkt aus dem Puffer, aendert und vergroessert ihn nie
        if lib.sqlite3_deserialize(self.db, b"main", ctypes.addressof(self._area), len(buf), len(buf), 4) != 0:
            self.close()
            raise HistorieError("Datenbank konnte nicht geöffnet werden.")
        for pragma in ("query_only = 1", "temp_store = MEMORY", "mmap_size = 2147418112", "cache_size = -256"):
            self.rows("PRAGMA " + pragma)          # mmap: Seiten direkt aus dem Puffer statt Kopien im Seitencache
        self.rows("SELECT count(*) FROM sqlite_master")

    def rows(self, sql: str, params=()) -> List[tuple]:
        lib, st = self.lib, ctypes.c_void_p()
        if lib.sqlite3_prepare_v2(self.db, sql.encode(), -1, ctypes.byref(st), None) != 0:
            raise sqlite3.DatabaseError((lib.sqlite3_errmsg(self.db) or b"").decode("utf-8", "replace"))
        try:
            for i, v in enumerate(params, 1):
                if isinstance(v, bool) or isinstance(v, int):
                    lib.sqlite3_bind_int64(st, i, int(v))
                elif isinstance(v, float):
                    lib.sqlite3_bind_double(st, i, v)
                else:
                    b = str(v).encode()
                    lib.sqlite3_bind_text(st, i, b, len(b), ctypes.c_void_p(-1))
            out = []
            while True:
                rc = lib.sqlite3_step(st)
                if rc == 101:          # fertig
                    return out
                if rc != 100:
                    raise sqlite3.DatabaseError((lib.sqlite3_errmsg(self.db) or b"").decode("utf-8", "replace"))
                row = []
                for c in range(lib.sqlite3_column_count(st)):
                    t = lib.sqlite3_column_type(st, c)
                    if t == 1:
                        row.append(lib.sqlite3_column_int64(st, c))
                    elif t == 2:
                        row.append(lib.sqlite3_column_double(st, c))
                    elif t == 3:
                        row.append((lib.sqlite3_column_text(st, c) or b"").decode("utf-8", "replace"))
                    else:
                        row.append(None)            # Binaerdaten werden nie gelesen
                out.append(tuple(row))
        finally:
            lib.sqlite3_finalize(st)

    def one(self, sql: str, params=()) -> tuple:
        r = self.rows(sql, params)
        return r[0] if r else ()

    def close(self) -> None:
        if self.db:
            self.lib.sqlite3_close(self.db)
            self.db = ctypes.c_void_p()
        self._area = None


# -- Aufbau lesen ----------------------------------------------------------------------------------------

def schema_of(db: "MemDB") -> List[Dict]:
    tables = []
    for (name,) in db.rows("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        cols = [(r[1], r[2]) for r in db.rows("PRAGMA table_info(%s)" % _q(name))]
        try:
            n = db.one("SELECT count(*) FROM %s" % _q(name))[0]
        except sqlite3.DatabaseError:
            n = None
        tables.append({"name": name, "spalten": cols, "zeilen": n})
    return tables


def schema_text(tables: List[Dict], fmt: str) -> str:
    lines = ["MoneyMoney-Datenbank: Aufbau (nur Namen und Zeilenzahlen, keine Inhalte)", "Format: %s" % fmt, ""]
    for t in tables:
        lines.append("%s  (%s Zeilen)" % (t["name"], "?" if t["zeilen"] is None else t["zeilen"]))
        lines.append("  " + ", ".join("%s %s" % (c, ty) for c, ty in t["spalten"]))
    return "\n".join(lines) + "\n"


def receive(rfile, n: int) -> bytearray:
    """Hochgeladene Datei direkt in einen Puffer lesen (keine Zwischenkopie)."""
    if n <= 0 or n > MAX_DB:
        raise HistorieError("Keine oder zu große Datei.")
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        if total and n > 0.5 * total:
            raise HistorieError("Die Datenbank ist für den Arbeitsspeicher dieses Macs zu groß (%d MB)." % (n // 1048576))
    except (ValueError, OSError, AttributeError):
        pass
    buf = bytearray(n)
    view = memoryview(buf)
    got = 0
    while got < n:
        k = rfile.readinto(view[got:])
        if not k:
            break
        got += k
    view.release()
    if got != n:
        _wipe(buf)
        raise HistorieError("Datei unvollständig übertragen.")
    return buf


# -- Kontostand-Verlauf finden und pruefen ---------------------------------------------------------------

def _q(name: str) -> str:
    return '"%s"' % name.replace('"', '""')


SKIP = re.compile(r"pass|secret|credential|token|kennwort|zugang|login|keychain|auth|cert|signatur", re.I)   # nie angesehen


def _to_date(v, kind: str) -> Optional[date]:
    try:
        if kind == "text":
            return date.fromisoformat(str(v)[:10])
        if kind == "ymd":
            x = int(v)
            return date(x // 10000, x // 100 % 100, x % 100)
        x = float(v)
        if kind == "unix_ms":
            x /= 1000.0
        elif kind == "cocoa":
            x += 978307200.0
        elif kind == "julian":
            x = (x - 2440587.5) * 86400.0
        return datetime.fromtimestamp(x).date()
    except (ValueError, OverflowError, OSError, TypeError):
        return None


ISO = "[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9]*"
NUM = "typeof(%s) IN ('integer', 'real')"


def _date_kinds(db: "MemDB", t: str, c: str, today: date) -> List[str]:
    """Moegliche Datumsformate einer Spalte: alle Werte muessen passen, der juengste liegt nahe heute."""
    q = _q(c)
    n_all, n_num, n_iso, lo, hi = db.one("SELECT count(%s), sum(%s), sum(typeof(%s) = 'text' AND %s GLOB '%s'), min(CASE WHEN %s THEN %s END), "
                                         "max(CASE WHEN %s THEN %s END) FROM %s" % (q, NUM % q, q, q, ISO, NUM % q, q, NUM % q, q, _q(t)))
    if not n_all:
        return []
    if n_iso == n_all:
        lo, hi = db.one("SELECT min(%s), max(%s) FROM %s" % (q, q, _q(t)))
        kinds = ["text"]
    elif n_num == n_all and lo is not None:
        kinds = ["ymd", "unix", "unix_ms", "cocoa", "julian"]
    else:
        return []
    out = []
    for kind in kinds:
        a, b = _to_date(lo, kind), _to_date(hi, kind)
        if a and b and a.year >= 1990 and today - timedelta(days=4 * 366) <= b <= today + timedelta(days=2):
            out.append(kind)
    return out


def _in(n: int) -> str:
    return "(%s)" % ",".join("?" * n)


def find_history(db: "MemDB", accounts: Dict[str, Tuple[float, bool]], today: date) -> Optional[Dict]:
    """Tabelle mit dem Kontostand-Verlauf suchen und pruefen. accounts: uuid -> (aktueller Saldo, Depot?).
    Geprueft wird: Bei den meisten Konten steht der aktuelle Saldo aus MoneyMoney unter den juengsten Werten.
    Verglichen wird in SQLite; in Python kommen nur Konto-Kennungen, Datumswerte und Betraege an.
    Liefert {"tabelle", "spalten", "konten": {uuid: {JJJJ-MM: Saldo am Monatsende}}, "treffer", "geprueft"} oder None."""
    uuids = {u.lower(): u for u in accounts}
    ulist = sorted(uuids)
    if not ulist:
        return None
    tables: Dict[str, List[Tuple[str, str]]] = {}
    for (t,) in db.rows("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        if SKIP.search(t):
            continue
        tables[t] = [(r[1], (r[2] or "").upper()) for r in db.rows("PRAGMA table_info(%s)" % _q(t)) if not SKIP.search(r[1])]
    counts = {}
    for t in tables:
        try:
            counts[t] = db.one("SELECT count(*) FROM %s" % _q(t))[0]
        except sqlite3.DatabaseError:
            counts[t] = 0
    # 1. Kontentabelle: Spalte mit den Kennungen der Konten -> Schluessel je Konto (rowid oder andere Ganzzahlspalte)
    key_maps: List[Dict[int, str]] = []
    acct_table, best = None, 0
    for t, cols in tables.items():
        if not counts[t] or counts[t] > 20000:
            continue
        for c, _ty in cols:
            try:
                found = db.rows("SELECT rowid, %s FROM %s WHERE typeof(%s) = 'text' AND lower(%s) IN %s" % (_q(c), _q(t), _q(c), _q(c), _in(len(ulist))), ulist)
            except sqlite3.DatabaseError:
                continue
            if len(found) > best:
                best, acct_table = len(found), t
                maps = [{r[0]: uuids[r[1].lower()] for r in found}]
                for c2, _t2 in cols:
                    if c2 == c:
                        continue
                    try:
                        vals = db.rows("SELECT %s, %s FROM %s WHERE typeof(%s) = 'integer' AND lower(%s) IN %s"
                                       % (_q(c2), _q(c), _q(t), _q(c2), _q(c), _in(len(ulist))), ulist)
                    except sqlite3.DatabaseError:
                        continue
                    m = {r[0]: uuids[r[1].lower()] for r in vals}
                    if len(m) == len(found):
                        maps.append(m)
                key_maps = maps
    if best < max(1, len(accounts) // 3):
        return None
    # 2. Verlaufstabelle: Kontospalte, Datumsspalte, Wertspalte
    winner = None
    for t, cols in tables.items():
        if t == acct_table or counts[t] < 2:
            continue
        acc_cols: List[Tuple[str, Dict]] = []
        for c, _ty in cols:
            q = _q(c)
            try:
                nd, nt = db.one("SELECT count(DISTINCT %s), count(DISTINCT CASE WHEN typeof(%s) = 'text' AND lower(%s) IN %s THEN lower(%s) END) FROM %s"
                                % (q, q, q, _in(len(ulist)), q, _q(t)), ulist)
            except sqlite3.DatabaseError:
                continue
            if nt >= 1 and nt >= 0.8 * nd:
                acc_cols.append((c, {}))           # Kennungen direkt
                continue
            for m in key_maps:
                keys = sorted(m)
                try:
                    nk = db.one("SELECT count(DISTINCT CASE WHEN typeof(%s) = 'integer' AND %s IN %s THEN %s END) FROM %s"
                                % (q, q, _in(len(keys)), q, _q(t)), keys)[0]
                except sqlite3.DatabaseError:
                    continue
                if nk >= 1 and nk >= 0.8 * nd:
                    acc_cols.append((c, m))
                    break
        if not acc_cols:
            continue
        num_cols = [c for c, ty in cols if ty == "" or any(x in ty for x in ("REAL", "INT", "NUM", "DOUBLE", "FLOAT", "DEC"))]
        date_cols = [(c, k) for c, _ty in cols for k in _date_kinds(db, t, c, today)]
        for ac, m in acc_cols:
            ref = (lambda a, m=m: m.get(a)) if m else (lambda a: uuids.get(str(a).lower()))
            for dc, kind in date_cols:
                if dc == ac:
                    continue
                for vc in num_cols:
                    if vc in (ac, dc):
                        continue
                    try:     # die drei juengsten Werte je Konto
                        recent = db.rows("SELECT a, v FROM (SELECT %s AS a, %s AS v, row_number() OVER (PARTITION BY %s ORDER BY %s DESC) AS n FROM %s "
                                         "WHERE %s IS NOT NULL AND %s AND %s) WHERE n <= 3"
                                         % (_q(ac), _q(vc), _q(ac), _q(dc), _q(t), _q(ac), NUM % _q(dc), NUM % _q(vc))
                                         if kind != "text" else
                                         "SELECT a, v FROM (SELECT %s AS a, %s AS v, row_number() OVER (PARTITION BY %s ORDER BY %s DESC) AS n FROM %s "
                                         "WHERE %s IS NOT NULL AND %s IS NOT NULL AND %s) WHERE n <= 3"
                                         % (_q(ac), _q(vc), _q(ac), _q(dc), _q(t), _q(ac), _q(dc), NUM % _q(vc)))
                    except sqlite3.DatabaseError:
                        continue
                    per: Dict[str, List[float]] = {}
                    for a, v in recent:
                        u = ref(a)
                        if u is not None:
                            per.setdefault(u, []).append(v)
                    for scale in (1.0, 0.01):
                        hits = depots = checked = 0
                        for u, vals in per.items():
                            bal, depot = accounts[u]
                            if abs(bal) < 1.0:
                                continue                   # Nullsalden beweisen nichts
                            checked += 1
                            if any(abs(v * scale - bal) <= max(0.011, 0.005 * abs(bal)) for v in vals):
                                hits += 1
                                depots += 1 if depot else 0
                        if hits and hits >= 0.6 * checked and counts[t] >= max(6, 2 * checked):
                            score = (min(depots, 1), round(hits / checked, 2), hits, counts[t])
                            if winner is None or score > winner[0]:
                                winner = (score, t, ac, ref, dc, kind, vc, scale, hits, checked)
    if winner is None:
        return None
    _s, t, ac, ref, dc, kind, vc, scale, hits, checked = winner
    konten: Dict[str, Dict[str, float]] = {}
    cur = "%04d-%02d" % (today.year, today.month)
    cond = NUM % _q(dc) if kind != "text" else "%s IS NOT NULL" % _q(dc)
    for a, d, v in db.rows("SELECT %s, %s, %s FROM %s WHERE %s IS NOT NULL AND %s AND %s ORDER BY %s"
                           % (_q(ac), _q(dc), _q(vc), _q(t), _q(ac), cond, NUM % _q(vc), _q(dc))):
        u = ref(a)
        day = _to_date(d, kind)
        if u is None or day is None:
            continue
        mk = "%04d-%02d" % (day.year, day.month)
        if mk >= cur:
            continue                                   # laufender Monat kommt aus MoneyMoneys aktuellem Saldo
        konten.setdefault(u, {})[mk] = round(v * scale, 2)       # spaeterer Wert im Monat ueberschreibt -> Monatsende
    return {"tabelle": t, "spalten": [ac, dc, vc], "konten": konten, "treffer": hits, "geprueft": checked}


def run(buf: bytearray, accounts: Dict[str, Tuple[float, bool]], today: date,
        keys_fn: Optional[Callable[[bytes], List[bytearray]]] = None, step: Optional[Callable[[str], None]] = None) -> Tuple[Optional[Dict], List[Dict], str]:
    """Hochgeladene Datenbank (Puffer) entschluesseln und den Kontostand-Verlauf suchen.
    Liefert (Verlauf oder None, Aufbau, Format). Schluessel und Puffer werden in jedem Fall ueberschrieben."""
    step = step or (lambda _t: None)
    keys: List[bytearray] = []
    db = None
    AKTIV.set()
    try:
        if len(buf) < 1024:
            raise HistorieError("Das ist keine MoneyMoney-Datenbank (MoneyMoney.sqlite).")
        if bytes(buf[:16]) == SQLITE_HEADER:
            fmt = "unverschlüsselt"
        else:
            step("Passwort")
            keys = [k if isinstance(k, bytearray) else bytearray(k) for k in (keys_fn or keys_from_dialog)(bytes(buf[:16]))]
            step("Entschlüsseln")
            fmt = decrypt_in_place(buf, keys)
            for k in keys:
                _wipe(k)
        step("Kontostände suchen")
        try:
            db = MemDB(buf)
        except sqlite3.DatabaseError:
            raise HistorieError("Das ist keine MoneyMoney-Datenbank (MoneyMoney.sqlite).")
        try:
            return find_history(db, accounts, today), schema_of(db), fmt
        except sqlite3.DatabaseError as e:
            raise HistorieError("Datenbank nicht lesbar (%s)." % str(e)[:80])
    finally:
        if db is not None:
            db.close()
        for k in keys:
            _wipe(k)
        _wipe(buf)
        gc.collect()
        AKTIV.clear()


def reveal() -> None:
    """MoneyMoney.sqlite im Finder markieren. Kontor selbst greift dabei nicht auf MoneyMoneys Ordner zu (keine
    Freigabe noetig): Der Pfad geht als Adresse an den Finder, der die Datei zeigt."""
    if sys.platform != "darwin":
        return
    js = ("ObjC.import('AppKit');"
          "var ws=$.NSWorkspace.sharedWorkspace, id='com.moneymoney-app.retail';"
          "var app=ws.URLForApplicationWithBundleIdentifier(id);"
          "if(!app||app.isNil()){var p=ws.fullPathForApplication('MoneyMoney');if(p&&!p.isNil()){var b=$.NSBundle.bundleWithPath(p);if(b&&!b.isNil()&&b.bundleIdentifier&&!b.bundleIdentifier.isNil())id=b.bundleIdentifier.js;}}"
          "var f=$.NSHomeDirectory().js+'/Library/Containers/'+id+'/Data/Library/Application Support/MoneyMoney/Database/MoneyMoney.sqlite';"
          "ws.activateFileViewerSelectingURLs($.NSArray.arrayWithObject($.NSURL.fileURLWithPathIsDirectory(f,false)));")
    subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", js], capture_output=True, timeout=20)
