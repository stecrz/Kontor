"""Verschluesselte Ablage der Programmdaten.

Alle Dateien im Datenordner (Konfiguration, Planwerte, Zustand, Bericht) liegen
verschluesselt: AES-256-CBC (ueber /usr/bin/openssl, auf jedem Mac vorhanden)
plus HMAC-SHA256 ueber den Chiffretext (Encrypt-then-MAC). Der Hauptschluessel
(32 Byte Zufall) liegt im macOS-Schluesselbund des Benutzers; ohne Schluesselbund
(nicht-macOS, Zugriff verweigert) als Datei mit Rechten 0600 -- die Oberflaeche
zeigt dann einen Hinweis.

Dateiformat: b"MMT1" + openssl-Ausgabe ("Salted__" + Salt + Chiffretext) + 32 Byte HMAC.
Das Passwort der Oberflaeche ist davon unabhaengig (es regelt den Zugang, nicht den
Schluessel), damit der Dienst nach dem Anmelden am Mac ohne Eingabe laufen kann --
wie MoneyMoney mit "Passwort im Schluesselbund sichern".
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import logging
import os
import secrets
import subprocess
import threading
from typing import Any, Dict, Optional, Tuple

_MISSING = object()
CACHE_MAX_BYTES = 24 * 1024 * 1024
log = logging.getLogger("kontor.store")

MAGIC = b"MMT1"
KEYCHAIN_SERVICE = "kontor.datenschluessel"
KEYCHAIN_ACCOUNT = "kontor"
# Eintrag frueherer Versionen (mmtools): wird gelesen und unter dem neuen Namen uebernommen
OLD_KEYCHAIN = ("mmtools.datenschluessel", "mmtools")


class StoreError(Exception):
    pass


# ---------------------------------------------------------------------------
# Schluessel
# ---------------------------------------------------------------------------

def _security(args, input_text: Optional[str] = None) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(["security"] + args, capture_output=True, text=True, timeout=30, input=input_text)
        return r.returncode, r.stdout, r.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return 127, "", str(e)


def load_or_create_master_key(data_dir: str) -> Tuple[bytes, str]:
    """Liefert (Schluessel, Quelle). Quelle: 'schluesselbund' | 'datei'."""
    rc, out, _ = _security(["find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"])
    if rc == 0 and len(out.strip()) == 64:
        return bytes.fromhex(out.strip()), "schluesselbund"
    key_file = os.path.join(data_dir, "master.key")
    if rc == 127:   # kein `security` (nicht macOS)
        return _file_key(key_file), "datei"
    # Eintrag einer frueheren Version (mmtools) uebernehmen
    rc_old, out_old, _ = _security(["find-generic-password", "-s", OLD_KEYCHAIN[0], "-a", OLD_KEYCHAIN[1], "-w"])
    if rc_old == 0 and len(out_old.strip()) == 64:
        key = bytes.fromhex(out_old.strip())
        log.info("Datenschlüssel der Vorversion (mmtools) übernommen.")
    else:
        # Schluesselbund vorhanden, aber kein Eintrag: neu anlegen
        key = secrets.token_bytes(32)
    rc2, _, err = _security(["add-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT,
                             "-l", "Kontor Datenschlüssel", "-w", key.hex(), "-U"])
    if rc2 == 0:
        rc3, out3, _ = _security(["find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"])
        if rc3 == 0 and out3.strip() == key.hex():
            return key, "schluesselbund"
    log.warning("Schlüsselbund nicht nutzbar (%s) -- Schlüssel wird als Datei abgelegt.", err.strip()[:120])
    return _file_key(key_file), "datei"


def _file_key(path: str) -> bytes:
    if os.path.exists(path):
        with open(path, "rb") as f:
            raw = f.read().strip()
        if len(raw) == 64:
            return bytes.fromhex(raw.decode())
    key = secrets.token_bytes(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key.hex())
    os.chmod(path, 0o600)
    return key


def _subkeys(master: bytes) -> Tuple[str, bytes]:
    enc_secret = hmac.new(master, b"mmtools-enc", hashlib.sha256).hexdigest()
    mac_key = hmac.new(master, b"mmtools-mac", hashlib.sha256).digest()
    return enc_secret, mac_key


# ---------------------------------------------------------------------------
# Verschluesselung
# ---------------------------------------------------------------------------

def _openssl(args, data: bytes, secret: str) -> bytes:
    env = dict(os.environ, MMTOOLS_SECRET=secret)
    try:
        r = subprocess.run(["openssl", "enc"] + args + ["-aes-256-cbc", "-md", "sha256", "-pass", "env:MMTOOLS_SECRET"],
                           input=data, capture_output=True, timeout=600, env=env)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise StoreError("openssl nicht verfügbar: %s" % e)
    if r.returncode != 0:
        raise StoreError("openssl-Fehler: %s" % r.stderr.decode(errors="replace")[:200])
    return r.stdout


def encrypt(master: bytes, data: bytes) -> bytes:
    enc_secret, mac_key = _subkeys(master)
    ct = _openssl(["-salt"], data, enc_secret)
    return MAGIC + ct + hmac.new(mac_key, ct, hashlib.sha256).digest()


def decrypt(master: bytes, blob: bytes) -> bytes:
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 32 + 16:
        raise StoreError("Datei hat nicht das erwartete Format.")
    enc_secret, mac_key = _subkeys(master)
    body, tag = blob[len(MAGIC):-32], blob[-32:]
    if not hmac.compare_digest(hmac.new(mac_key, body, hashlib.sha256).digest(), tag):
        raise StoreError("Prüfsumme stimmt nicht -- Datei verändert oder falscher Schlüssel.")
    return _openssl(["-d"], body, enc_secret)


def selftest(master: bytes) -> bool:
    try:
        probe = secrets.token_bytes(1000) + b"mmtools"
        return decrypt(master, encrypt(master, probe)) == probe
    except Exception as e:
        log.warning("Selbsttest der Verschlüsselung fehlgeschlagen: %s", e)
        return False


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class Store:
    """load/save von JSON-Dokumenten im Datenordner, verschluesselt wenn ein Schluessel vorliegt."""

    def __init__(self, data_dir: str, master: Optional[bytes] = None, key_source: str = ""):
        self.data_dir = data_dir
        self.master = master
        self.key_source = key_source
        self.encrypted = master is not None and selftest(master)
        if master is not None and not self.encrypted:
            log.error("Verschlüsselung nicht verfügbar -- Daten werden UNVERSCHLUESSELT abgelegt.")
        os.makedirs(data_dir, exist_ok=True)
        try:
            os.chmod(data_dir, 0o700)
        except OSError:
            pass
        self._cache: Dict[str, Tuple[Tuple[int, int], Any]] = {}     # name -> ((mtime_ns, size), Objekt)
        self._cache_lock = threading.Lock()
        self._file_locks: Dict[str, threading.RLock] = {}
        self._migrate_plaintext()

    # Pfade
    def path(self, name: str) -> str:
        return os.path.join(self.data_dir, name + (".enc" if self.encrypted else ""))

    def exists(self, name: str) -> bool:
        return os.path.exists(self.path(name))

    # JSON
    def _stamp(self, name: str) -> Optional[Tuple[int, int]]:
        try:
            st = os.stat(self.path(name))
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def stamp(self, name: str) -> Optional[Tuple[int, int]]:
        """(Aenderungszeit, Groesse) der Datei -- aendert sich bei jedem Speichern."""
        return self._stamp(name)

    def load_shared(self, name: str, default: Any = None) -> Any:
        """Wie load, liefert aber das im Speicher gehaltene Objekt (nur lesen, nicht veraendern!). Entschluesselt
        und parst eine Datei nur, wenn sie sich seit dem letzten Zugriff geaendert hat."""
        stamp = self._stamp(name)
        if stamp is None:
            return default
        with self._cache_lock:
            hit = self._cache.get(name)
            if hit and hit[0] == stamp:
                return hit[1]
        raw = self.read_bytes(name)
        if raw is None:
            return default
        try:
            obj = json.loads(raw.decode("utf-8"))
        except ValueError as e:
            raise StoreError("%s ist kein gültiges JSON: %s" % (name, e))
        if stamp[1] <= CACHE_MAX_BYTES:        # sehr grosse Dateien (Umsatzliste) nicht dauerhaft im Speicher halten
            with self._cache_lock:
                self._cache[name] = (stamp, obj)
        return obj

    def load(self, name: str, default: Any = None) -> Any:
        """JSON-Dokument laden (eigene Kopie, darf veraendert werden)."""
        obj = self.load_shared(name, _MISSING)
        if obj is _MISSING:
            return default
        return copy.deepcopy(obj)

    def update(self, name: str, fn, default: Any = None) -> Any:
        """Lesen-Aendern-Schreiben in einem Schritt, je Datei serialisiert (kein verlorenes Update durch parallele Threads).
        fn bekommt das geladene Objekt (bzw. default) und veraendert es in place; Rueckgabe ist das gespeicherte Objekt."""
        with self._cache_lock:
            lock = self._file_locks.setdefault(name, threading.RLock())
        with lock:
            obj = self.load(name, _MISSING)
            if obj is _MISSING:
                obj = copy.deepcopy(default) if default is not None else {}
            fn(obj)
            self.save(name, obj)
            return obj

    def save(self, name: str, obj: Any) -> None:
        # kompakt und ohne Einrueckung: nutzt den schnellen C-Kodierer (bei grossen Dateien Faktor 5-10)
        self.write_bytes(name, json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))
        stamp = self._stamp(name)
        with self._cache_lock:
            if stamp is not None and stamp[1] <= CACHE_MAX_BYTES:
                self._cache[name] = (stamp, copy.deepcopy(obj))
            else:
                self._cache.pop(name, None)

    # Bytes (z.B. bericht.html)
    def read_bytes(self, name: str) -> Optional[bytes]:
        p = self.path(name)
        if not os.path.exists(p):
            return None
        with open(p, "rb") as f:
            raw = f.read()
        if self.encrypted:
            return decrypt(self.master, raw)
        return raw

    def write_bytes(self, name: str, data: bytes) -> None:
        p = self.path(name)
        tmp = p + ".tmp"
        payload = encrypt(self.master, data) if self.encrypted else data
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
        os.replace(tmp, p)
        os.chmod(p, 0o600)

    def delete(self, name: str) -> None:
        with self._cache_lock:
            self._cache.pop(name, None)
        try:
            os.remove(self.path(name))
        except FileNotFoundError:
            pass

    def _migrate_plaintext(self) -> None:
        """Klartextdateien frueherer Versionen in die verschluesselte Ablage uebernehmen."""
        if not self.encrypted:
            return
        for name in ("config.json", "plan.json", "state.json", "dataset.json", "auth.json", "belege.json", "umsaetze.json"):
            src = os.path.join(self.data_dir, name)
            if os.path.exists(src) and not os.path.exists(self.path(name)):
                with open(src, "rb") as f:
                    raw = f.read()
                try:
                    if name.endswith(".json"):
                        json.loads(raw.decode("utf-8"))
                except ValueError:
                    continue
                self.write_bytes(name, raw)
                if self.read_bytes(name) == raw:      # erst nach erfolgreicher Kontrolle den Klartext entfernen
                    os.remove(src)
                    log.info("%s in die verschlüsselte Ablage übernommen, Klartext gelöscht.", name)
        # Klartext-Reste aelterer Versionen (regenerierbar) entfernen
        for name in ("bericht.html", "dataset.json", "umsaetze.json", "launchd.out.log", "launchd.err.log"):
            src = os.path.join(self.data_dir, name)
            if os.path.exists(src) and not (name.endswith(".json") and not os.path.exists(self.path(name))):
                try:
                    os.remove(src)
                    log.info("Klartextdatei %s entfernt (wird verschlüsselt neu erzeugt).", name)
                except OSError:
                    pass
