"""Depot-Historie aus MoneyMoneys eigener Datenbank -- einmalig, auf Klick in der Oberflaeche.

MoneyMoneys Skript-Schnittstelle liefert nur aktuelle Salden; die Kurve der Kontostaende steht nur in seiner
Datenbank (SQLCipher, verschluesselt mit dem MoneyMoney-Passwort). Der Weg ist bewusst eng gefasst:

* Keine macOS-Freigabe fuer Kontor: Die (verschluesselte) Datenbankdatei ziehst du selbst ins Browserfenster;
  sie kommt ueber 127.0.0.1 an und wird nur im Arbeitsspeicher gehalten, nie gespeichert.
* Das Passwort erreicht Kontor nie. Ein kleiner macOS-Helfer (mm_historie.swift) wird nur fuer diesen einen Vorgang
  in einem privaten Ordner uebersetzt, fragt das Passwort im eigenen Fenster ab, gibt ueber eine private Pipe nur den
  daraus berechneten Schluessel zurueck und wird danach samt Ordner geloescht.
* Entschluesselt wird ausschliesslich im Arbeitsspeicher dieses Prozesses (macOS CommonCrypto) direkt in einen
  Puffer, der nach dem Lesen mit Nullen ueberschrieben wird. Keine Datei, keine Auslagerung durch SQLite
  (temp_store = MEMORY), kein Fremdprogramm sieht Schluessel oder Inhalt.
* Waehrenddessen keine Netzverbindung von Kontor (Update-Pruefung ruht); protokolliert werden nur Zaehlerstaende.
* Gelesen werden nur Aufbau (Tabellen-/Spaltennamen, Zeilenzahl) bzw. die Kontostand-Historie -- nie Zugangsdaten.
"""
from __future__ import annotations

import ctypes
import gc
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
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

def _aes_cbc_into() -> Callable[[bytearray, bytes, memoryview, bytearray, int], None]:
    """AES-256-CBC (ohne Auffuellen) direkt in einen Zielpuffer. macOS: CommonCrypto im eigenen Prozess."""
    if sys.platform == "darwin":
        lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        fn = lib.CCCrypt
        fn.restype = ctypes.c_int32
        fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p,
                       ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

        def dec(key: bytearray, iv: bytes, data: memoryview, out: bytearray, off: int) -> None:
            k = (ctypes.c_char * len(key)).from_buffer(key)
            src = (ctypes.c_char * len(data)).from_buffer_copy(data)          # verschluesselte Daten
            dst = (ctypes.c_char * len(data)).from_buffer(out, off)           # Klartext direkt in den Zielpuffer
            moved = ctypes.c_size_t(0)
            st = fn(1, 0, 0, ctypes.addressof(k), len(key), iv, ctypes.addressof(src), len(data), ctypes.addressof(dst), len(data), ctypes.byref(moved))
            if st != 0 or moved.value != len(data):
                raise HistorieError("Entschlüsselung fehlgeschlagen (%d)." % st)
        return dec
    try:   # andere Systeme (nur Tests)
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:  # pragma: no cover
        raise HistorieError("Entschlüsselung nur auf dem Mac verfügbar.")

    def dec2(key: bytearray, iv: bytes, data: memoryview, out: bytearray, off: int) -> None:
        d = Cipher(algorithms.AES(bytes(key)), modes.CBC(bytes(iv))).decryptor()
        pt = d.update(bytes(data)) + d.finalize()
        out[off:off + len(pt)] = pt
    return dec2


def _page1_ok(raw: memoryview, key: bytearray, page: int, reserve: int, dec) -> bool:
    if len(raw) < page:
        return False
    probe = bytearray(16)
    dec(key, bytes(raw[page - reserve:page - reserve + 16]), raw[16:32], probe, 0)
    # Kopfbytes 16..23 des SQLite-Formats: Seitengroesse, Schreib-/Leseversion, Reserve (>= IV + Pruefsumme), 64, 32, 32
    ps = int.from_bytes(probe[0:2], "big")
    ok = (ps == page or (ps == 1 and page == 65536)) and probe[2] in (1, 2) and probe[3] in (1, 2) and reserve <= probe[4] and probe[5:8] == b"\x40\x20\x20"
    _wipe(probe)
    return ok


def decrypt_into(raw: memoryview, keys: List[bytearray]) -> Tuple[bytearray, str]:
    """Datenbank im Speicher entschluesseln (in einen bytearray, den der Aufrufer ueberschreibt). Falsches Passwort -> Fehler."""
    dec = _aes_cbc_into()
    for (name, _h, _r), key in zip(FORMATS, keys):
        for page in PAGE_SIZES:
            if len(raw) % page:
                continue
            for reserve in RESERVES:
                if not _page1_ok(raw, key, page, reserve, dec):
                    continue
                out = bytearray(len(raw))
                try:
                    for i in range(len(raw) // page):
                        base = i * page
                        start = 16 if i == 0 else 0
                        dec(key, bytes(raw[base + page - reserve:base + page - reserve + 16]), raw[base + start:base + page - reserve], out, base + start)
                except Exception:
                    _wipe(out)
                    raise
                out[0:16] = SQLITE_HEADER
                return out, name
    raise HistorieError("Passwort falsch (oder unbekanntes Datenbankformat).")


def open_memory(plain: bytearray) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    if not hasattr(con, "deserialize"):
        con.close()
        raise HistorieError("Diese Python-Version kann Datenbanken nicht im Speicher öffnen (ab Python 3.11).")
    con.execute("PRAGMA temp_store = MEMORY")       # nie Zwischendateien
    con.deserialize(plain)
    con.execute("PRAGMA temp_store = MEMORY")
    con.execute("PRAGMA query_only = 1")
    return con


# -- Aufbau lesen ----------------------------------------------------------------------------------------

def schema_of(con: sqlite3.Connection) -> List[Dict]:
    tables = []
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
        q = name.replace('"', '""')
        cols = [(r[1], r[2]) for r in con.execute('PRAGMA table_info("%s")' % q).fetchall()]
        try:
            n = con.execute('SELECT count(*) FROM "%s"' % q).fetchone()[0]
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


def read_schema(raw: bytes, keys_fn: Optional[Callable[[bytes], List[bytearray]]] = None) -> Tuple[List[Dict], str]:
    """Aufbau der (hochgeladenen, verschluesselten) Datenbank lesen. Schluessel und Klartext werden danach ueberschrieben."""
    if len(raw) < 1024 or raw[:16] == SQLITE_HEADER:
        raise HistorieError("Das ist keine verschlüsselte MoneyMoney-Datenbank (MoneyMoney.sqlite).")
    keys_fn = keys_fn or keys_from_dialog
    AKTIV.set()
    keys: List[bytearray] = []
    plain = bytearray()
    con = None
    try:
        keys = [k if isinstance(k, bytearray) else bytearray(k) for k in keys_fn(bytes(raw[:16]))]
        plain, fmt = decrypt_into(memoryview(raw), keys)
        for k in keys:
            _wipe(k)
        con = open_memory(plain)
        _wipe(plain)                                   # SQLite haelt seine eigene Kopie im Speicher
        return schema_of(con), fmt
    finally:
        if con is not None:
            con.close()
        for k in keys:
            _wipe(k)
        _wipe(plain)
        gc.collect()
        AKTIV.clear()
