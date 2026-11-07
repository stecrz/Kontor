"""Einmaliges Einlesen der Depot-Historie aus MoneyMoneys eigener Datenbank.

MoneyMoneys Skript-Schnittstelle liefert nur aktuelle Salden; die Kurve der Kontostaende steht nur in seiner
Datenbank (SQLCipher, verschluesselt mit dem MoneyMoney-Passwort). Dieser Weg ist bewusst eng gefasst:

* Das Passwort erreicht Kontor nie. Ein kleiner macOS-Helfer (mm_historie.swift) fragt es im eigenen Fenster ab
  und gibt nur den daraus berechneten Datenbank-Schluessel zurueck (ueber eine private Pipe, nicht ueber das Netz,
  nicht in der Befehlszeile, nie in einer Datei).
* Entschluesselt wird ausschliesslich im Arbeitsspeicher dieses Prozesses (macOS CommonCrypto); es entsteht keine
  unverschluesselte Kopie auf der Festplatte, kein Fremdprogramm sieht Schluessel oder Inhalt.
* Nur lesend, nur am Mac, nur bei beendetem MoneyMoney (dann ist die Datenbank vollstaendig und unveraendert).
* Kontor baut waehrenddessen keine Netzverbindung auf; es wird nichts protokolliert ausser Zaehlerstaenden.
* Gelesen werden nur Aufbau (Tabellen-/Spaltennamen, Zeilenzahl) bzw. spaeter die Kontostand-Historie -- nie
  Tabellen mit Zugangsdaten.
"""
from __future__ import annotations

import ctypes
import gc
import os
import sqlite3
import subprocess
import sys
import threading
from typing import Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.expanduser("~/Library/Containers/com.moneymoney-app.retail/Data/Library/Application Support/MoneyMoney/Database/MoneyMoney.sqlite")
HELPER_SRC = os.path.join(HERE, "mm_historie.swift")
HELPER_BIN = os.path.join(HERE, ".historie", "Kontor")

# Schluesselableitung je SQLCipher-Generation: (Name, Hash fuer PBKDF2, Runden). Seitengroesse und reservierte Bytes
# (IV + Pruefsumme) werden an der entschluesselten Kopfzeile erkannt, nicht angenommen.
FORMATS = [("SQLCipher 4", "sha512", 256000), ("SQLCipher 3", "sha1", 64000)]
PAGE_SIZES = (1024, 4096, 2048, 8192, 16384, 32768, 65536)
RESERVES = (48, 80, 32, 64)
SQLITE_HEADER = b"SQLite format 3\x00"

AKTIV = threading.Event()        # waehrend des Einlesens gesetzt: z. B. keine Update-Pruefung (keine Netzverbindung)


class HistorieError(Exception):
    pass


# -- Helfer (Passwortdialog) -------------------------------------------------------------------------------

def helper_available() -> bool:
    return os.path.exists(HELPER_BIN) and os.access(HELPER_BIN, os.X_OK)


def build_helper(force: bool = False) -> str:
    if sys.platform != "darwin":
        return "nicht macOS"
    if not force and helper_available() and os.path.getmtime(HELPER_BIN) >= os.path.getmtime(HELPER_SRC):
        return "ok"
    try:
        os.makedirs(os.path.dirname(HELPER_BIN), exist_ok=True)
        r = subprocess.run(["swiftc", "-O", "-o", HELPER_BIN, HELPER_SRC], capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            os.chmod(HELPER_BIN, 0o700)
            return "ok"
        return "swiftc-Fehler: " + (r.stderr or r.stdout)[-300:]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return "swiftc nicht verfügbar (%s) -- Xcode Command Line Tools: xcode-select --install" % e


def keys_from_dialog(salt: bytes) -> List[bytes]:
    """Passwort im Dialog des Helfers abfragen lassen; zurueck kommen nur die Schluessel je Format."""
    if not helper_available():
        raise HistorieError("Der Passwort-Helfer ist noch nicht übersetzt (Xcode Command Line Tools nötig: xcode-select --install).")
    args = [HELPER_BIN, salt.hex()] + ["%s:%d" % (h, r) for _n, h, r in FORMATS]
    try:
        r = subprocess.run(args, capture_output=True, timeout=600, env={"PATH": "/usr/bin:/bin"})
    except subprocess.TimeoutExpired:
        raise HistorieError("Keine Eingabe im Passwortfenster (Zeitlimit).")
    if r.returncode == 1:
        raise HistorieError("abgebrochen")
    if r.returncode != 0:
        raise HistorieError("Passwortfenster konnte nicht angezeigt werden.")
    out = [bytes.fromhex(x.strip()) for x in r.stdout.decode("ascii", "ignore").splitlines() if x.strip()]
    if len(out) != len(FORMATS) or any(len(k) != 32 for k in out):
        raise HistorieError("Unerwartete Antwort des Passwortfensters.")
    return out


# -- Entschluesseln im Arbeitsspeicher --------------------------------------------------------------------

def _aes_cbc_decryptor() -> Callable[[bytes, bytes, bytes], bytes]:
    """AES-256-CBC ohne Auffuellen. macOS: CommonCrypto (Systembibliothek, im eigenen Prozess)."""
    if sys.platform == "darwin":
        lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        fn = lib.CCCrypt
        fn.restype = ctypes.c_int32
        fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p,
                       ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

        def dec(key: bytes, iv: bytes, data: bytes) -> bytes:
            buf = ctypes.create_string_buffer(len(data))
            moved = ctypes.c_size_t(0)
            st = fn(1, 0, 0, key, len(key), iv, data, len(data), buf, len(data), ctypes.byref(moved))   # kCCDecrypt, AES, CBC
            if st != 0:
                raise HistorieError("Entschlüsselung fehlgeschlagen (%d)." % st)
            return buf.raw[:moved.value]
        return dec
    try:   # andere Systeme (Tests)
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:  # pragma: no cover
        raise HistorieError("Entschlüsselung nur auf macOS verfügbar.")

    def dec2(key: bytes, iv: bytes, data: bytes) -> bytes:
        d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        return d.update(data) + d.finalize()
    return dec2


def _page1_ok(raw: bytes, key: bytes, page: int, reserve: int, dec) -> bool:
    if len(raw) < page:
        return False
    pt = dec(key, raw[page - reserve:page - reserve + 16], raw[16:page - reserve])
    # Kopfbytes 16..23 des SQLite-Formats: Seitengroesse (2 Byte), Schreib-/Leseversion, Reserve, 64, 32, 32
    ps = int.from_bytes(pt[0:2], "big")
    # Reserve-Byte: mindestens der Platz fuer IV + Pruefsumme (bei umgestellten Datenbanken kann es groesser sein)
    return (ps == page or (ps == 1 and page == 65536)) and pt[2] in (1, 2) and pt[3] in (1, 2) and reserve <= pt[4] <= 255 and pt[5:8] == b"\x40\x20\x20"


def decrypt(raw: bytes, keys: List[bytes]) -> Tuple[bytes, str]:
    """Datenbank im Speicher entschluesseln: passendes Format anhand der Kopfzeile erkennen. Falsches Passwort -> Fehler."""
    dec = _aes_cbc_decryptor()
    combos = [(name, key, page, reserve) for (name, _h, _r), key in zip(FORMATS, keys) for page in PAGE_SIZES for reserve in RESERVES]
    for name, key, page, reserve in combos:
        if len(raw) % page or not _page1_ok(raw, key, page, reserve, dec):
            continue
        n = len(raw) // page
        out = bytearray(n * page)
        for i in range(n):
            pg = raw[i * page:(i + 1) * page]
            start = 16 if i == 0 else 0
            pt = dec(key, pg[page - reserve:page - reserve + 16], pg[start:page - reserve])
            out[i * page + start:i * page + page - reserve] = pt
        out[0:16] = SQLITE_HEADER
        return bytes(out), name
    raise HistorieError("Passwort falsch (oder unbekanntes Datenbankformat).")


def open_memory(plain: bytes) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    if not hasattr(con, "deserialize"):
        con.close()
        raise HistorieError("Diese Python-Version kann Datenbanken nicht im Speicher öffnen (ab Python 3.11).")
    con.deserialize(plain)
    con.execute("PRAGMA query_only = 1")
    return con


# -- Aufbau lesen (Schritt 1) ----------------------------------------------------------------------------

def schema_of(con: sqlite3.Connection) -> List[Dict]:
    tables = []
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        cols = [(r[1], r[2]) for r in con.execute('PRAGMA table_info("%s")' % name.replace('"', '""'))]
        try:
            n = con.execute('SELECT count(*) FROM "%s"' % name.replace('"', '""')).fetchone()[0]
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


def read_database(path: Optional[str] = None, keys_fn: Optional[Callable[[bytes], List[bytes]]] = None,
                  is_running: Optional[Callable[[], bool]] = None) -> Tuple[List[Dict], str]:
    """Aufbau der MoneyMoney-Datenbank lesen. Gibt (Tabellen, Format) zurueck; Schluessel und Inhalte werden verworfen."""
    path = path or DB_PATH
    keys_fn = keys_fn or keys_from_dialog
    if is_running is not None and is_running():
        raise HistorieError("Bitte MoneyMoney zuerst beenden (⌘Q) – dann ist die Datenbank vollständig und wird nicht gleichzeitig geändert.")
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        raise HistorieError("MoneyMoney-Datenbank nicht gefunden.")
    except PermissionError:
        raise HistorieError("macOS hat den Zugriff auf die Daten von MoneyMoney verweigert. Beim nächsten Versuch die Rückfrage "
                            "„python3 möchte auf Daten von anderen Apps zugreifen“ mit „Erlauben“ beantworten.")
    AKTIV.set()
    keys: List[bytes] = []
    plain = b""
    con = None
    try:
        keys = keys_fn(raw[:16])
        plain, fmt = decrypt(raw, keys)
        con = open_memory(plain)
        tables = schema_of(con)
        return tables, fmt
    finally:
        if con is not None:
            con.close()
        keys = []
        plain = b""
        raw = b""
        gc.collect()
        AKTIV.clear()
