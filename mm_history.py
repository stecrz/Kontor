"""Kontostand-Verlauf aus MoneyMoneys eigener Datenbank -- einmalig, auf Klick in der Oberflaeche (Einrichtung).

MoneyMoneys Skript-Schnittstelle liefert nur aktuelle Salden; die Kurve der Kontostaende (v. a. Depots) steht nur in seiner
Datenbank (SQLCipher, verschluesselt mit dem MoneyMoney-Passwort). Der Weg ist bewusst eng gefasst:

* Keine macOS-Freigabe fuer Kontor: Der Finder zeigt die Datei (Kontor selbst greift nicht auf MoneyMoneys Ordner zu),
  du ziehst sie ins Browserfenster; sie kommt ueber 127.0.0.1 an und liegt nur im Arbeitsspeicher, nie auf der Platte.
  MoneyMoney muss beendet sein; an seiner Datei aendert sich nichts.
* Das Passwort erreicht Kontor nie. Ein kleiner macOS-Helfer (mm_history.swift) wird nur fuer diesen einen Vorgang
  in einem privaten Ordner uebersetzt, fragt das Passwort im eigenen Fenster ab, gibt ueber eine private Pipe nur die
  daraus berechneten Schluessel zurueck und wird danach samt Ordner geloescht.
* Entschluesselt wird im Arbeitsspeicher dieses Prozesses (macOS CommonCrypto) an Ort und Stelle; SQLite liest
  schreibgeschuetzt direkt aus diesem Puffer (keine Kopie, keine Zwischendateien). Danach werden Schluessel und Puffer
  mit Nullen ueberschrieben. Spitzenbedarf an Arbeitsspeicher: etwa die Dateigroesse.
* Waehrenddessen keine Netzverbindung von Kontor (Update-Pruefung ruht); protokolliert werden nur Zaehlerstaende.
* Gelesen werden nur die Tabellen accounts (Kennzeichen zum Zuordnen: IBAN, Kontonummer, BLZ, Name, Depot ja/nein),
  balance_chart und portfolio_chart (Zeitpunkt und Betrag); Zugangsdaten und Umsaetze werden nicht angesehen. Uebernommen
  werden nur Monatsend-Staende eindeutig zugeordneter Konten, und nur, wenn die juengsten Werte zum aktuellen Saldo passen.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import gc
import logging
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
from i18n import tr

HERE = os.path.dirname(os.path.abspath(__file__))
HELPER_SRC = os.path.join(HERE, "mm_history.swift")
MAX_DB = 2 * 1024 * 1024 * 1024        # Obergrenze fuer die hochgeladene Datei

# Schluesselableitung je SQLCipher-Generation: (Name, Hash fuer PBKDF2, Runden). Seitengroesse und reservierte Bytes
# (IV + Pruefsumme) werden an der entschluesselten Kopfzeile erkannt, nicht angenommen.
FORMATS = [("SQLCipher 4", "sha512", 256000), ("SQLCipher 3", "sha1", 64000)]
PAGE_SIZES = (1024, 4096, 2048, 8192, 16384, 32768, 65536)
RESERVES = (48, 80, 32, 64)
SQLITE_HEADER = b"SQLite format 3\x00"

log = logging.getLogger("kontor.history")
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
        raise HistorieError(tr("s_nur_auf_dem_mac_moeglich"))
    work = tempfile.mkdtemp(prefix="kontor-")          # 0700, nur fuer diesen Benutzer
    try:
        exe = os.path.join(work, "Kontor")             # der Name erscheint als Programmname im Fenster
        try:
            r = subprocess.run(["swiftc", "-O", "-o", exe, HELPER_SRC], capture_output=True, text=True, timeout=300)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            r = None
        if r is None or r.returncode != 0:
            subprocess.run(["xcode-select", "--install"], capture_output=True)     # macOS bietet die Installation an
            raise HistorieError(tr("s_fuer_das_passwortfenster_fehlen_apples"))
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
            raise HistorieError(tr("s_keine_eingabe_im_passwortfenster_zeitl"))
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
            raise HistorieError(tr("s_das_passwortfenster_konnte_nicht_angez"))
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
                raise HistorieError(tr("s_entschluesselung_fehlgeschlagen_d") % st)
        return dec
    try:   # andere Systeme (nur Tests)
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:  # pragma: no cover
        raise HistorieError(tr("s_entschluesselung_nur_auf_dem_mac"))

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
    raise HistorieError(tr("s_passwort_falsch_oder_unbekanntes_daten"))


# -- Datenbank im Arbeitsspeicher (SQLite direkt auf dem Puffer, ohne Kopie) ------------------------------

def _sqlite_lib():
    """SQLite-Bibliothek mit sqlite3_deserialize: macOS-System, sonst die von Python mitgebrachte."""
    import _sqlite3
    names = (["/usr/lib/libsqlite3.dylib"] if sys.platform == "darwin" else []) + \
        [getattr(_sqlite3, "__file__", None), ctypes.util.find_library("sqlite3"), "libsqlite3.so.0", None]
    for name in names:
        try:
            lib = ctypes.CDLL(name)
            lib.sqlite3_deserialize
            return lib
        except (OSError, AttributeError, TypeError):
            continue
    raise HistorieError(tr("s_sqlite_ohne_speicherfunktion_gefunden"))


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
            raise HistorieError(tr("s_sqlite_konnte_nicht_geoeffnet_werden"))
        # 4 = SQLITE_DESERIALIZE_READONLY: SQLite liest direkt aus dem Puffer, aendert und vergroessert ihn nie
        if lib.sqlite3_deserialize(self.db, b"main", ctypes.addressof(self._area), len(buf), len(buf), 4) != 0:
            self.close()
            raise HistorieError(tr("s_datenbank_konnte_nicht_geoeffnet_werde"))
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

SHADOW = ("_content", "_segments", "_segdir", "_docsize", "_stat", "_data", "_idx", "_config", "_node", "_parent", "_rowid")


def table_names(db: "MemDB") -> Tuple[List[str], List[str]]:
    """(gewoehnliche Tabellen, virtuelle Tabellen). Virtuelle Tabellen -- bei MoneyMoney die Volltextsuche mit eigenem
    Tokenizer -- lassen sich ohne MoneyMoney nicht oeffnen und werden samt ihren Schattentabellen nie angefasst."""
    rows = db.rows("SELECT name, coalesce(sql, '') FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    virtual = [n for n, sql in rows if sql.lstrip().upper().startswith("CREATE VIRTUAL TABLE")]
    plain = [n for n, _sql in rows if n not in virtual and not any(n == v + sfx for v in virtual for sfx in SHADOW)]
    return plain, virtual


def columns(db: "MemDB", table: str) -> List[Tuple[str, str]]:
    try:
        return [(r[1], (r[2] or "").upper()) for r in db.rows("PRAGMA table_info(%s)" % _q(table))]
    except sqlite3.DatabaseError:
        return []


def schema_of(db: "MemDB") -> List[Dict]:
    plain, virtual = table_names(db)
    tables = []
    for name in plain:
        try:
            n = db.one("SELECT count(*) FROM %s" % _q(name))[0]
        except sqlite3.DatabaseError:
            n = None
        tables.append({"name": name, "spalten": columns(db, name), "zeilen": n})
    tables += [{"name": name, "spalten": [], "zeilen": None, "virtuell": True} for name in virtual]
    return tables


def schema_text(tables: List[Dict], fmt: str) -> str:
    lines = ["MoneyMoney database schema (names and row counts only, no contents)", "Format: %s" % fmt, ""]
    for t in tables:
        lines.append("%s  (%s)" % (t["name"], "virtual, skipped" if t.get("virtuell") else "%s rows" % ("?" if t["zeilen"] is None else t["zeilen"])))
        lines.append("  " + ", ".join("%s %s" % (c, ty) for c, ty in t["spalten"]))
    return "\n".join(lines) + "\n"


def receive(rfile, n: int) -> bytearray:
    """Hochgeladene Datei direkt in einen Puffer lesen (keine Zwischenkopie)."""
    if n <= 0 or n > MAX_DB:
        raise HistorieError(tr("s_keine_oder_zu_grosse_datei"))
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        if total and n > 0.5 * total:
            raise HistorieError(tr("s_die_datenbank_ist_fuer_den") % (n // 1048576))
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
        raise HistorieError(tr("s_datei_unvollstaendig_uebertragen"))
    return buf


# -- Kontostand-Verlauf finden und pruefen ---------------------------------------------------------------

def _q(name: str) -> str:
    return '"%s"' % name.replace('"', '""')


def _in(n: int) -> str:
    return "(%s)" % ",".join("?" * n)


def _to_date(v, kind: str) -> Optional[date]:
    try:
        x = float(v)
        if kind == "unix_ms":
            x /= 1000.0
        elif kind == "cocoa":
            x += 978307200.0
        return datetime.fromtimestamp(x).date()
    except (ValueError, OverflowError, OSError, TypeError):
        return None


def _time_kind(db: "MemDB", table: str, today: date) -> Optional[str]:
    """Zeitformat der Spalte timestamp: Unix-Sekunden, -Millisekunden oder Cocoa (ab 2001); der juengste Wert liegt nahe heute."""
    lo, hi = db.one("SELECT min(timestamp), max(timestamp) FROM %s WHERE typeof(timestamp) IN ('integer', 'real')" % _q(table))
    if hi is None:
        return None
    for kind in ("unix", "unix_ms", "cocoa"):
        a, b = _to_date(lo, kind), _to_date(hi, kind)
        if a and b and a.year >= 1990 and today - timedelta(days=4 * 366) <= b <= today + timedelta(days=2):
            return kind
    return None


def _norm(v) -> str:
    return re.sub(r"\s+", "", str(v or "")).upper()


def _match_accounts(db: "MemDB", accounts: Dict[str, Dict]) -> Tuple[Dict[int, Tuple[str, str]], Dict[str, List[int]]]:
    """Konten der Datenbank (rowid) den Konten von Kontor zuordnen: IBAN, sonst Kontonummer + BLZ, sonst Name.
    Gelesen werden nur diese Kennzeichen (keine Zugangsdaten). Liefert (rowid -> (uuid, Merkmal) fuer eindeutige Treffer,
    uuid -> [rowid, ...] fuer mehrdeutige Namen; die entscheidet spaeter der aktuelle Saldo)."""
    have = {c for c, _ty in columns(db, "accounts")}
    want = [c for c in ("iban", "account", "bankcode", "name", "portfolio") if c in have]
    if "name" not in want:
        return {}, {}
    rows = [dict(zip(["rowid"] + want, r)) for r in db.rows("SELECT rowid, %s FROM accounts" % ", ".join(_q(c) for c in want))]
    out: Dict[int, Tuple[str, str]] = {}
    taken: Dict[int, int] = {}
    unclear: Dict[str, List[int]] = {}
    for u, a in accounts.items():
        hit, how = [], ""
        if _norm(a.get("iban")):
            hit, how = [r for r in rows if _norm(r.get("iban")) == _norm(a["iban"])], "iban"
        if not hit and _norm(a.get("nummer")) and _norm(a.get("blz")):
            hit, how = [r for r in rows if _norm(r.get("account")) == _norm(a["nummer"]) and _norm(r.get("bankcode")) == _norm(a["blz"])], "nummer"
        if not hit and a.get("name"):
            hit, how = [r for r in rows if str(r.get("name") or "").strip() == a["name"].strip()
                        and ("portfolio" not in r or bool(r["portfolio"]) == bool(a.get("depot")))], "name"
        if len(hit) > 1 and how != "name":               # gleiche IBAN/Nummer mehrfach (Unterkonten): Name entscheidet
            hit = [r for r in hit if str(r.get("name") or "").strip() == (a.get("name") or "").strip()] or hit
        if len(hit) == 1:
            k = hit[0]["rowid"]
            taken[k] = taken.get(k, 0) + 1
            out[k] = (u, how)
        elif len(hit) > 1 and how == "name":
            unclear[u] = [r["rowid"] for r in hit]
    out = {k: v for k, v in out.items() if taken[k] == 1}
    return out, {u: [k for k in ks if k not in out] for u, ks in unclear.items()}


def _series(rows, kind: str) -> List[Tuple[date, float]]:
    out = []
    for ts, v in rows:
        d = _to_date(ts, kind)
        if d is not None and v is not None:
            out.append((d, float(v)))
    return out


# Deutungen eines Verlaufspunkts (Zeitpunkt T, Wert v): Saldo am Ende des Tages T oder davor (Ende T-1), nach Buchungs-
# oder Wertstellungsdatum. Welche zutrifft, zeigt der Vergleich mit den Salden, die Kontor aus den Umsaetzen kennt.
INTERP = (("end", False), ("start", False), ("end", True), ("start", True))
BalanceAt = Callable[[str, date, bool], Optional[float]]


def _load_series(db: "MemDB", plain: List[str], keys: List[int], info: Callable[[int], Dict], today: date) -> Dict[int, Tuple[str, List]]:
    """Verlauf je Konto der Datenbank: balance_chart (Saldo je Zeitpunkt, Waehrung des Kontos); Depots ohne eigenen
    Saldo-Verlauf aus portfolio_chart (Summe der Wertpapiere je Zeitpunkt). Gelesen werden nur Kennung, Zeitpunkt, Betrag."""
    series: Dict[int, Tuple[str, List]] = {}
    kind = _time_kind(db, "balance_chart", today)
    if kind:
        by_key: Dict[int, Dict[str, List]] = {}
        for k, c, ts, v in db.rows("SELECT account_key, currency, timestamp, balance FROM balance_chart WHERE account_key IN %s "
                                   "AND typeof(balance) IN ('integer', 'real') ORDER BY timestamp" % _in(len(keys)), keys):
            by_key.setdefault(k, {}).setdefault(c or "", []).append((ts, v))
        for k, per in by_key.items():
            rows = per.get(info(k).get("waehrung") or "") or (next(iter(per.values())) if len(per) == 1 else None)
            if rows:
                series[k] = ("balance_chart", _series(rows, kind))
    if "portfolio_chart" in plain:
        pkind = _time_kind(db, "portfolio_chart", today)
        dep = [k for k in keys if k not in series and info(k).get("depot")]
        if pkind and dep:
            snaps: Dict[int, List] = {}
            for k, ts, v in db.rows("SELECT account_key, timestamp, sum(balance) FROM portfolio_chart WHERE account_key IN %s "
                                    "AND typeof(balance) IN ('integer', 'real') GROUP BY account_key, timestamp ORDER BY timestamp" % _in(len(dep)), dep):
                snaps.setdefault(k, []).append((ts, v))
            for k, rows in snaps.items():
                series[k] = ("portfolio_chart", _series(rows, pkind))
    return series


def _day(d: date, when: str) -> date:
    return d - timedelta(days=1) if when == "start" else d


def _score(ser: List, u: str, scale: float, interp: Tuple[str, bool], balance_at: BalanceAt, since: Optional[date], today: date) -> Tuple[int, int]:
    """(passende Punkte, vergleichbare Punkte) eines Verlaufs gegen die aus den Umsaetzen bekannten Tagessalden."""
    when, by_value = interp
    hits = n = 0
    for d, v in ser:
        day = _day(d, when)
        if day >= today or (since and day < since):
            continue
        ref = balance_at(u, day, by_value)
        if ref is None:
            return 0, 0
        n += 1
        hits += abs(v * scale - ref) <= max(0.011, 0.001 * abs(ref))
    return hits, n


def _diagnose(series: Dict[int, Tuple[str, List]], matched: Dict[int, Tuple[str, str]], results: Dict, today: date) -> None:
    """Protokoll fuer die Fehlersuche, wenn nichts uebernommen wird: nur Anzahlen und Anteile, keine Betraege oder Namen."""
    pts = [d for _t, ser in series.values() for d, _v in ser]
    if pts:
        first = sum(1 for d in pts if d.day == 1) / len(pts)
        last = sum(1 for d in pts if (d + timedelta(days=1)).day == 1) / len(pts)
        gaps = sorted((b[0] - a[0]).days for _t, ser in series.values() for a, b in zip(ser, ser[1:]))
        log.info("MoneyMoney database (diagnostics): %d points, %.0f %% on the 1st, %.0f %% on the last day of a month, median gap %s days, latest %s days ago",
                 len(pts), 100 * first, 100 * last, gaps[len(gaps) // 2] if gaps else "-", (today - max(pts)).days)
    for key, (hits, n) in sorted(results.items(), key=lambda x: str(x[0])):
        log.info("MoneyMoney database (diagnostics): interpretation %s: %d of %d points match", key, hits, n)
    for i, (k, (t, ser)) in enumerate(sorted(series.items())):
        if k in matched:
            log.info("MoneyMoney database (diagnostics): account %d (%s, %s): %d points", i + 1, matched[k][1], t, len(ser))


def find_history(db: "MemDB", accounts: Dict[str, Dict], today: date, balance_at: Optional[BalanceAt] = None,
                 since: Optional[date] = None) -> Optional[Dict]:
    """Kontostand-Verlauf aus MoneyMoneys Tabellen balance_chart und portfolio_chart.
    accounts: uuid -> {saldo, depot, iban, nummer, blz, name, waehrung}; balance_at(uuid, tag, nach_wertstellung): Saldo am
    Ende des Tages laut den Umsaetzen in Kontor (None fuer Depots), verlaesslich ab since.
    Massstab und Deutung der Zeitpunkte werden an diesen Salden geeicht; ein Konto mit Umsaetzen wird nur uebernommen, wenn
    mindestens 70 % seiner Punkte passen, insgesamt muessen 60 % der pruefbaren Konten passen. Depots (ohne Umsaetze) nur bei
    eindeutiger Zuordnung. Liefert {"tabelle", "spalten", "konten": {uuid: {JJJJ-MM: Saldo am Monatsende}}, "treffer",
    "geprueft"} oder None."""
    plain, virtual = table_names(db)
    if "accounts" not in plain or "balance_chart" not in plain:
        log.info("MoneyMoney database: %d tables (%d virtual skipped), no accounts/balance_chart", len(plain), len(virtual))
        return None
    matched, unclear = _match_accounts(db, accounts)
    hows = [h for _u, h in matched.values()]
    log.info("MoneyMoney database: %d tables (%d virtual skipped); %d of %d accounts matched (IBAN %d, number %d, name %d), %d names ambiguous",
             len(plain), len(virtual), len(matched), len(accounts), hows.count("iban"), hows.count("nummer"), hows.count("name"), len(unclear))
    if not matched and not unclear:
        return None
    owner = {k: u for u, ks in unclear.items() for k in ks}           # Kandidat -> ein Konto gleichen Namens (Waehrung, Depot)
    info = lambda k: accounts[matched[k][0] if k in matched else owner[k]]
    series = _load_series(db, plain, sorted(set(matched) | set(owner)), info, today)
    if not series:
        log.info("MoneyMoney database: no balance history for the matched accounts")
        return None
    balance_at = balance_at or (lambda _u, _d, _v: None)
    # Eichung: Massstab (Euro/Cent, Vorzeichen) und Deutung, bei der die meisten Punkte zu den bekannten Salden passen
    results: Dict = {}
    for scale in (1.0, -1.0, 0.01, -0.01):
        for interp in INTERP:
            tot = [0, 0]
            for k, (_t, ser) in series.items():
                if k in matched:
                    h, n = _score(ser, matched[k][0], scale, interp, balance_at, since, today)
                    tot[0] += h; tot[1] += n
            results[(scale, interp)] = tuple(tot)
    (scale, interp), (all_hits, all_n) = max(results.items(), key=lambda x: (x[1][0], x[0][0] == 1.0, x[0][1] == ("end", False)))
    good = lambda k, u: (lambda h, n: (n > 0 and h >= 0.7 * n, n))(*_score(series[k][1], u, scale, interp, balance_at, since, today))
    ok: Dict[int, bool] = {}
    for k in series:
        if k in matched:
            fit, n = good(k, matched[k][0])
            if n:
                ok[k] = fit
            elif series[k][1] and abs(info(k).get("saldo") or 0.0) >= 1.0:
                # ohne Umsaetze (Depots): nur Plausibilitaet -- juengster Wert in der Groessenordnung des aktuellen Saldos
                q = series[k][1][-1][1] * scale / info(k)["saldo"]
                if not 0.5 <= q <= 2.0:
                    ok[k] = False
    # mehrdeutige Namen: der Kandidat, dessen Verlauf zu den Salden dieses Kontos passt (genau einer)
    for u, ks in unclear.items():
        fits = [k for k in ks if k in series and k not in matched and good(k, u)[0]]
        if len(fits) == 1:
            matched[fits[0]] = (u, "name")
            ok[fits[0]] = True
    hits, checked = sum(ok.values()), len(ok)
    log.info("MoneyMoney database: scale %s, interpretation %s/%s: %d of %d points, %d of %d accounts with transactions match",
             scale, interp[0], "value date" if interp[1] else "booking date", all_hits, all_n, hits, checked)
    if checked and hits < 0.6 * checked:
        _diagnose(series, matched, results, today)
        return None
    cur = "%04d-%02d" % (today.year, today.month)
    konten: Dict[str, Dict[str, float]] = {}
    for k, (_t, ser) in series.items():
        if k not in matched or ok.get(k) is False:
            continue                                       # Konto mit Umsaetzen, dessen Verlauf nicht passt: nicht uebernehmen
        u = matched[k][0]
        for d, v in ser:
            day = _day(d, interp[0])
            mk = "%04d-%02d" % (day.year, day.month)
            if mk < cur:                                   # laufender Monat kommt aus MoneyMoneys aktuellem Saldo
                konten.setdefault(u, {})[mk] = round(v * scale, 2)       # spaeterer Wert im Monat ueberschreibt -> Monatsende
    tabellen = sorted({series[k][0] for k in series if k in matched})
    return {"tabelle": "+".join(tabellen), "spalten": ["account_key", "timestamp", "balance"], "konten": konten, "treffer": hits, "geprueft": checked}


def run(buf: bytearray, accounts: Dict[str, Dict], today: date, keys_fn: Optional[Callable[[bytes], List[bytearray]]] = None,
        step: Optional[Callable[[str], None]] = None, balance_at: Optional[BalanceAt] = None,
        since: Optional[date] = None) -> Tuple[Optional[Dict], List[Dict], str]:
    """Hochgeladene Datenbank (Puffer) entschluesseln und den Kontostand-Verlauf suchen.
    Liefert (Verlauf oder None, Aufbau, Format). Schluessel und Puffer werden in jedem Fall ueberschrieben."""
    step = step or (lambda _t: None)
    keys: List[bytearray] = []
    db = None
    AKTIV.set()
    try:
        if len(buf) < 1024:
            raise HistorieError(tr("s_das_ist_keine_moneymoney_datenbank"))
        if bytes(buf[:16]) == SQLITE_HEADER:
            fmt = "unencrypted"
        else:
            step("password")
            keys = [k if isinstance(k, bytearray) else bytearray(k) for k in (keys_fn or keys_from_dialog)(bytes(buf[:16]))]
            step("decrypt")
            fmt = decrypt_in_place(buf, keys)
            for k in keys:
                _wipe(k)
        step("search")
        try:
            db = MemDB(buf)
        except sqlite3.DatabaseError:
            raise HistorieError(tr("s_das_ist_keine_moneymoney_datenbank"))
        try:
            return find_history(db, accounts, today, balance_at, since), schema_of(db), fmt
        except sqlite3.DatabaseError as e:
            raise HistorieError(tr("s_datenbank_nicht_lesbar_s") % str(e)[:80])
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
