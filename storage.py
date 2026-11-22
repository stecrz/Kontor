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

import base64
import copy
import hashlib
import hmac
import json
import logging
import os
import secrets
import subprocess
import sys
import threading
from typing import Any, Dict, Optional, Tuple
from i18n import tr

_MISSING = object()
CACHE_MAX_BYTES = 24 * 1024 * 1024
log = logging.getLogger("kontor.store")

MAGIC = b"MMT1"
KEYCHAIN_SERVICE = "kontor.datenschluessel"       # the entry in the keychain (kept: it lives outside Kontor's folder)
KEYCHAIN_ACCOUNT = "kontor"
KEYCHAIN_NEXT = "kontor-next"                      # a new key while the data are re-encrypted (renew_master_key)
KEYCHAIN_LABEL = "Kontor Datenschlüssel"


class StoreError(Exception):
    pass


class StoreLocked(StoreError):
    """The store has no key yet (nobody signed in since the service started): nothing can be read or written."""


# ---------------------------------------------------------------------------
# Schluessel
# ---------------------------------------------------------------------------

def _security(args, input_text: Optional[str] = None) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(["security"] + args, capture_output=True, text=True, timeout=30, input=input_text)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError as e:                       # no `security` (not macOS)
        return 127, "", str(e)
    except subprocess.TimeoutExpired as e:               # the keychain did not answer (locked, a prompt waiting): not "no keychain"
        return 124, "", str(e)


def _kc_read(account: str) -> Tuple[int, Optional[bytes]]:
    rc, out, _ = _security(["find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account, "-w"])
    return rc, (_hex_key(out) if rc == 0 else None)


def _kc_write(account: str, key: bytes) -> bool:
    """Puts the key into the keychain entry and reads it back: True only when the entry holds exactly this key."""
    rc, _, _ = _security(["add-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account, "-l", KEYCHAIN_LABEL, "-w", key.hex(), "-U"])
    return rc == 0 and _kc_read(account)[1] == key


ENC_DIRS = ("chats",)                              # folders in the data folder whose files belong to the store (saved conversations)


def _names(data_dir: str) -> list:
    """The files of the data folder and of its store folders, as names relative to it ("chats/x.json.enc")."""
    out = []
    for sub in ("",) + ENC_DIRS:
        try:
            out += [os.path.join(sub, n) if sub else n for n in os.listdir(os.path.join(data_dir, sub))
                    if not sub or os.path.isfile(os.path.join(data_dir, sub, n))]
        except OSError:
            continue
    return out


def _enc_files(data_dir: str) -> list:
    """Every encrypted file of the store -- also in its folders: a new key re-encrypts them all, none is left behind."""
    return sorted(n for n in _names(data_dir) if n.endswith(".enc"))


def _finish_renewal(data_dir: str) -> Optional[bytes]:
    """A renewal of the data key that did not finish (the Mac went off in the middle): the new key waits in its own entry.
    Every file that still opens with the old key is re-encrypted with the new one, then the new key takes the main entry.
    Returns the key that opens the data, or None when there is nothing to finish. Never deletes a key that opens a file."""
    rc, new = _kc_read(KEYCHAIN_NEXT)
    if rc == 44 or rc == 127:                          # no unfinished renewal
        for n in _names(data_dir) if os.path.isdir(data_dir) else []:
            if n.endswith(".enc.renew"):                 # written with a key that was never kept: worthless
                _remove(os.path.join(data_dir, n))
        return None
    if rc != 0 or new is None:                         # no answer, refused, odd content: unknown -- stop rather than guess
        log.error("Keychain did not answer about an unfinished renewal of the data key (code %s) -- Kontor stops.", rc)
        raise StoreError(tr("s_schluesselbund_antwortet_nicht" if rc == 124 else "s_schluesselbund_nicht_nutzbar"))
    _, old = _kc_read(KEYCHAIN_ACCOUNT)
    for n in _enc_files(data_dir):
        p = os.path.join(data_dir, n)
        with open(p, "rb") as f:
            raw = f.read()
        try:
            decrypt(new, raw)
            continue
        except StoreError:
            pass
        if old is None:
            raise StoreError(tr("s_schluessel_passt_nicht"))
        plain = decrypt(old, raw)                        # neither key opens it: stops here, both entries stay
        _write_atomic(p, encrypt(new, plain))
    for n in _names(data_dir):
        if n.endswith(".enc.renew"):
            _remove(os.path.join(data_dir, n))
    if not _kc_write(KEYCHAIN_ACCOUNT, new):         # the data open with it: start, and move it into the main entry next time
        log.warning("Keychain did not take the new data key into its main entry -- tried again at the next start")
        return new
    _security(["delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_NEXT])
    log.warning("Renewal of the data key finished after an interruption")
    return new


def read_master_key(data_dir: str) -> Tuple[bytes, str]:
    """The key that opens the data -- read only: none is made, moved or replaced (for removing Kontor). The main entry, the key
    of an unfinished renewal, or a key file: the first that opens the encrypted files."""
    data = bool(_enc_files(data_dir))
    for k, src in ((_kc_read(KEYCHAIN_ACCOUNT)[1], "keychain"), (_kc_read(KEYCHAIN_NEXT)[1], "keychain"),
                   (_read_key_file(os.path.join(data_dir, "master.key")), "file")):
        if k and (not data or _opens(k, data_dir)):
            return k, src
    raise StoreError(tr("s_schluessel_passt_nicht"))


def load_or_create_master_key(data_dir: str, finish: bool = True) -> Tuple[bytes, str]:
    """Liefert (Schluessel, Quelle). Quelle: 'keychain' | 'file'.
    The key belongs in the keychain, not next to the data: a key file left from a fallback is moved into the keychain as soon
    as that works (and the file removed); only if the keychain cannot be used at all, the file stays (with a warning). A new
    key is made only when no encrypted data are there: a key is never replaced before it is clear which one opens the data.
    finish=False (a command while the service runs): an unfinished renewal is left to the service; its key is used if only it
    opens the data."""
    if sys.platform == "darwin":
        if finish:
            done = _finish_renewal(data_dir)
            if done is not None:
                return done, "keychain"
        else:
            _, nxt = _kc_read(KEYCHAIN_NEXT)
            if nxt is not None and _opens(nxt, data_dir) and not _opens(_kc_read(KEYCHAIN_ACCOUNT)[1] or b"", data_dir):
                return nxt, "keychain"
    rc, out, _ = _security(["find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"])
    key_file = os.path.join(data_dir, "master.key")
    kc = _hex_key(out) if rc == 0 else None
    if kc:
        if os.path.exists(key_file):
            # a key file besides the keychain entry: the one that opens the data stays (in the keychain), the file goes
            fk = _read_key_file(key_file)
            if fk and fk != kc and _opens(fk, data_dir) and not _opens(kc, data_dir):
                rc2, _, _ = _security(["add-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-l", KEYCHAIN_LABEL, "-w", fk.hex(), "-U"])
                rc3, out3, _ = _security(["find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"])
                if rc2 != 0 or rc3 != 0 or out3.strip() != fk.hex():
                    log.warning("Key file opens the data, but the keychain did not take it -- the file stays")
                    return fk, "file"
                kc = fk
            _wipe(key_file)
            log.info("Key file besides the keychain entry removed")
        return kc, "keychain"
    if rc == 127:   # kein `security` (nicht macOS)
        return _file_key(key_file), "file"
    if rc != 44:
        # only 44 means "no entry". Anything else -- no answer in time (124), access refused, locked, an entry with unexpected
        # content: its key is unknown, so no new one is made and none replaced. Only a key file that opens the data already
        # there is used; otherwise Kontor stops (and starts again once the keychain answers).
        old = _read_key_file(key_file)
        if old and _opens(old, data_dir):
            log.warning("Keychain did not give the key (code %s) -- the existing key file that opens the data is used this time", rc)
            return old, "file"
        log.error("Keychain did not give the key (code %s) -- no key created; Kontor stops.", rc)
        raise StoreError(tr("s_schluesselbund_antwortet_nicht" if rc == 124 else "s_schluesselbund_nicht_nutzbar"))
    # keychain there, no entry: the key of a fallback file goes into it -- otherwise a new one, but only without encrypted data
    old = _read_key_file(key_file)
    if not old and _enc_files(data_dir):
        log.error("Encrypted data without their key -- no new key created; Kontor stops.")
        raise StoreError(tr("s_schluessel_passt_nicht"))
    key = old or secrets.token_bytes(32)
    rc2, _, err = _security(["add-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT,
                             "-l", KEYCHAIN_LABEL, "-w", key.hex(), "-U"])
    if rc2 == 0:
        rc3, out3, _ = _security(["find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"])
        if rc3 == 0 and out3.strip() == key.hex():
            if old:
                _wipe(key_file)
                log.info("Data key moved from the key file into the keychain; file removed")
            return key, "keychain"
    if not old:
        # on the Mac a new key never goes into a file next to the data: without the keychain Kontor does not start
        log.error("Keychain not usable (%s) -- no key file created; Kontor stops.", err.strip()[:120])
        raise StoreError(tr("s_schluesselbund_nicht_nutzbar"))
    log.warning("Keychain not usable (%s) -- the existing key file is used until the keychain works (less protected).", err.strip()[:120])
    return old, "file"


def _hex_key(text: str) -> Optional[bytes]:
    """The 32-byte key the keychain holds (64 hex digits) -- None for anything else."""
    try:
        raw = text.strip()
        return bytes.fromhex(raw) if len(raw) == 64 else None
    except ValueError:
        return None


def _opens(key: bytes, data_dir: str) -> bool:
    """Does this key open the data in the folder (the check sum of an encrypted file matches)?"""
    for name in ("config.json.enc", "state.json.enc", "auth.json.enc"):
        try:
            with open(os.path.join(data_dir, name), "rb") as f:
                decrypt(key, f.read())
            return True
        except (OSError, StoreError):
            continue
    return False


def _read_key_file(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as f:
            raw = f.read().strip()
        return bytes.fromhex(raw.decode()) if len(raw) == 64 else None
    except (OSError, ValueError):
        return None


def _wipe(path: str) -> None:
    """Overwrite, then remove a small secret file."""
    try:
        n = os.path.getsize(path)
        with open(path, "r+b") as f:
            f.write(secrets.token_bytes(max(n, 64)))
            f.flush()
            os.fsync(f.fileno())
        os.remove(path)
    except OSError as e:
        log.warning("Key file not removed: %s", e)


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _write_atomic(path: str, payload: bytes) -> None:
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _file_key(path: str) -> bytes:
    if os.path.exists(path):
        with open(path, "rb") as f:
            raw = f.read().strip()
        if len(raw) == 64:
            return bytes.fromhex(raw.decode())
    if _enc_files(os.path.dirname(path)):             # a broken or missing key file next to encrypted data: never a new one
        raise StoreError(tr("s_schluessel_passt_nicht"))
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
        raise StoreError(tr("s_openssl_nicht_verfuegbar_s") % e)
    if r.returncode != 0:
        raise StoreError(tr("s_openssl_fehler_s") % r.stderr.decode(errors="replace")[:200])
    return r.stdout


def encrypt(master: bytes, data: bytes) -> bytes:
    enc_secret, mac_key = _subkeys(master)
    ct = _openssl(["-salt"], data, enc_secret)
    return MAGIC + ct + hmac.new(mac_key, ct, hashlib.sha256).digest()


def decrypt(master: bytes, blob: bytes) -> bytes:
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 32 + 16:
        raise StoreError(tr("s_datei_hat_nicht_das_erwartete"))
    enc_secret, mac_key = _subkeys(master)
    body, tag = blob[len(MAGIC):-32], blob[-32:]
    if not hmac.compare_digest(hmac.new(mac_key, body, hashlib.sha256).digest(), tag):
        raise StoreError(tr("s_pruefsumme_stimmt_nicht_datei_veraende"))
    return _openssl(["-d"], body, enc_secret)


def selftest(master: bytes) -> bool:
    try:
        probe = secrets.token_bytes(1000) + b"mmtools"
        return decrypt(master, encrypt(master, probe)) == probe
    except Exception as e:
        log.warning("Encryption self-test failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Schluesseldatei: der Datenschluessel nur verpackt -- mit einem Schluessel aus dem Passwort (bzw. per Touch ID), nie offen
# ---------------------------------------------------------------------------

KEY_FILE = "key.json"           # in the data folder; holds no key in the clear, only wrapped ones (and what unwraps them needs)
KDF = "pbkdf2-sha256"
KDF_ROUNDS = 600_000


def key_record(data_dir: str) -> Optional[dict]:
    """The key file, or None when there is none. Unreadable or odd content raises StoreError -- never taken for "none" (that
    would lead to a new key over data the old one opens)."""
    try:
        with open(os.path.join(data_dir, KEY_FILE), "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise StoreError(tr("s_schluesseldatei_kaputt")) from e
    try:
        rec = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise StoreError(tr("s_schluesseldatei_kaputt")) from e
    if not isinstance(rec, dict) or rec.get("kontor_key") != 1 or not all(isinstance(rec.get(m), (dict, type(None))) for m in ("password", "touchid")):
        raise StoreError(tr("s_schluesseldatei_kaputt"))
    return rec


def write_key_record(data_dir: str, rec: dict) -> None:
    """Writes the key file whole or not at all (beside it, then renamed; on the disk before the rename counts) and reads it
    back: StoreError unless the file holds exactly this record."""
    rec = dict(rec, kontor_key=1)
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("utf-8")
    os.makedirs(data_dir, mode=0o700, exist_ok=True)
    _write_atomic(os.path.join(data_dir, KEY_FILE), raw)
    _sync_dir(data_dir)
    if key_record(data_dir) != rec:
        raise StoreError(tr("s_schluesseldatei_kaputt"))


def _sync_dir(path: str) -> None:
    """The folder's entries on the disk too (a renamed file survives the Mac going off right after)."""
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def password_kek(password: str, salt: bytes, rounds: int = KDF_ROUNDS) -> bytes:
    """The key that wraps the data key, made from the password (PBKDF2-HMAC-SHA256)."""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)


def wrap_entry(kek: bytes, key: bytes, nxt: Optional[bytes] = None, **fields: Any) -> dict:
    """An entry of the key file: the data key (and, while it is renewed, the next one) wrapped with kek."""
    e = dict(fields, key=base64.b64encode(encrypt(kek, key)).decode("ascii"))
    if nxt is not None:
        e["next"] = base64.b64encode(encrypt(kek, nxt)).decode("ascii")
    return e


def _unwrap(kek: bytes, b64: Any) -> Optional[bytes]:
    try:
        blob = base64.b64decode(str(b64), validate=True)
    except (ValueError, TypeError) as e:
        raise StoreError(tr("s_schluesseldatei_kaputt")) from e
    if not blob.startswith(MAGIC):
        raise StoreError(tr("s_schluesseldatei_kaputt"))
    try:
        key = decrypt(kek, blob)
    except StoreError:
        return None                                      # the check sum does not match: not the right password (or key)
    if len(key) != 32:
        raise StoreError(tr("s_schluesseldatei_kaputt"))
    return key


def open_entry(kek: bytes, entry: dict) -> Optional[Tuple[bytes, Optional[bytes]]]:
    """(data key, next key or None) -- None when kek is not the one it was wrapped with; StoreError for a broken entry."""
    if not isinstance(entry, dict) or "key" not in entry:
        raise StoreError(tr("s_schluesseldatei_kaputt"))
    key = _unwrap(kek, entry["key"])
    if key is None:
        return None
    nxt = _unwrap(kek, entry["next"]) if entry.get("next") else None
    if entry.get("next") and nxt is None:
        raise StoreError(tr("s_schluesseldatei_kaputt"))
    return key, nxt


def password_entry(key: bytes, password: str, nxt: Optional[bytes] = None) -> dict:
    """The data key wrapped with the password (a fresh salt each time)."""
    salt = secrets.token_bytes(16)
    return wrap_entry(password_kek(password, salt), key, nxt, kdf=KDF, rounds=KDF_ROUNDS, salt=salt.hex())


def open_password_entry(entry: dict, password: str) -> Optional[Tuple[bytes, Optional[bytes]]]:
    """(data key, next key) with the password -- None for a wrong one."""
    try:
        rounds, salt = int(entry["rounds"]), bytes.fromhex(entry["salt"])
    except (KeyError, TypeError, ValueError) as e:
        raise StoreError(tr("s_schluesseldatei_kaputt")) from e
    if entry.get("kdf") != KDF or not 100_000 <= rounds <= 10_000_000 or len(salt) < 16:
        raise StoreError(tr("s_schluesseldatei_kaputt"))
    return open_entry(password_kek(password, salt, rounds), entry)


def files_not_opening(key: bytes, data_dir: str) -> list:
    """Every encrypted file of the store -- also in its folders (ENC_DIRS) --, each opened whole: the names this key does
    not open. Empty: the key provably opens all data."""
    bad = []
    for n in _enc_files(data_dir):
        try:
            with open(os.path.join(data_dir, n), "rb") as f:
                decrypt(key, f.read())
        except (OSError, StoreError):
            bad.append(n)
    return bad


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
            # never fall back to plain text: without working encryption Kontor stores nothing (and does not start)
            log.error("Encryption not available -- Kontor stores nothing unencrypted and stops.")
            raise StoreError(tr("s_ohne_verschluesselung"))
        os.makedirs(data_dir, exist_ok=True)
        try:
            os.chmod(data_dir, 0o700)
        except OSError:
            pass
        self._cache: Dict[str, Tuple[Tuple[int, int], Any]] = {}     # name -> ((mtime_ns, size), Objekt)
        self._cache_lock = threading.Lock()
        self._file_locks: Dict[str, threading.RLock] = {}
        self._key_lock = threading.RLock()            # no file is read or written while the key is renewed

    @classmethod
    def closed(cls, data_dir: str) -> "Store":
        """The store before anyone signed in: the data are encrypted, the key is not there yet -- every read and write raises
        StoreLocked until unlock()."""
        st = cls(data_dir, None)
        st.encrypted = True
        return st

    @property
    def is_open(self) -> bool:
        """Ablage offen? False until someone signed in after the service started (and after the key was dropped): then every
        read and write -- load, save, update, read_bytes, write_bytes, delete, exists, stamp -- raises StoreLocked."""
        return self.master is not None or not self.encrypted

    def unlock(self, master: bytes, key_source: str) -> None:
        """The key, once someone signed in: from here on the store reads and writes."""
        if not selftest(master):
            raise StoreError(tr("s_ohne_verschluesselung"))
        with self._key_lock:
            self.master, self.key_source, self.encrypted = master, key_source, True
            with self._cache_lock:
                self._cache.clear()

    def close(self) -> None:
        """Drops the key from memory (everything deleted with the password): locked again until someone sets one up."""
        with self._key_lock:
            self.master, self.key_source, self.encrypted = None, "", True
            with self._cache_lock:
                self._cache.clear()

    def _need_key(self) -> None:
        if self.master is None and self.encrypted:
            raise StoreLocked(tr("s_ablage_gesperrt"))

    # Pfade
    def path(self, name: str) -> str:
        return os.path.join(self.data_dir, name + (".enc" if self.encrypted else ""))

    def exists(self, name: str) -> bool:
        self._need_key()
        return os.path.exists(self.path(name))

    # JSON
    def _stamp(self, name: str) -> Optional[Tuple[int, int]]:
        self._need_key()
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
            raise StoreError(tr("s_s_ist_kein_gueltiges_json") % (name, e))
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
        with self._key_lock:
            self._need_key()
            if not os.path.exists(p):
                return None
            with open(p, "rb") as f:
                raw = f.read()
            if self.encrypted:
                return decrypt(self.master, raw)
            return raw

    def write_bytes(self, name: str, data: bytes) -> None:
        self._need_key()
        p = self.path(name)
        tmp = p + ".tmp"
        if os.path.dirname(name):                        # a file in one of the store's folders (ENC_DIRS): the folder first, only for the user
            os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
        with self._key_lock:
            self._need_key()
            payload = encrypt(self.master, data) if self.encrypted else data
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
            os.replace(tmp, p)
            os.chmod(p, 0o600)

    def renew_key(self) -> int:
        """A new data key: every encrypted file in the folder is decrypted with the old key and written anew with the new one.
        The old key stays until all files provably open with the new one: first everything is written beside the files and
        checked, then the new key is kept in its own keychain entry and checked, only then the files are replaced and the new
        key takes the main entry. Interrupted after that, the next start finishes it (_finish_renewal). Only with the keychain,
        and never while an earlier renewal is unfinished (its key would be lost). Returns the number of files."""
        self._need_key()
        if not self.encrypted:
            raise StoreError(tr("s_ohne_verschluesselung"))
        if self.key_source != "keychain":
            raise StoreError(tr("s_schluessel_erneuern_schluesselbund"))
        rc_next, nxt = _kc_read(KEYCHAIN_NEXT)        # asked before the lock: a slow keychain does not hold up the files
        rc_main, main = _kc_read(KEYCHAIN_ACCOUNT)
        with self._key_lock:
            if rc_next != 44 or rc_main != 0 or main != self.master:
                half = rc_next == 0 and nxt == self.master            # this Kontor runs with a key the main entry did not take
                raise StoreError(tr("s_schluessel_erneuern_halb" if half else "s_schluessel_erneuern_nicht"))
            old = self.master
            names = _enc_files(self.data_dir)
            plain: Dict[str, bytes] = {}
            for n in names:                              # everything opens with the old key, or nothing changes
                with open(os.path.join(self.data_dir, n), "rb") as f:
                    plain[n] = decrypt(old, f.read())
            new = secrets.token_bytes(32)
            if new == old or not selftest(new):
                raise StoreError(tr("s_ohne_verschluesselung"))
            written = []
            try:
                for n, data in plain.items():
                    p = os.path.join(self.data_dir, n + ".renew")
                    _write_atomic(p, encrypt(new, data))
                    written.append(p)
                    with open(p, "rb") as f:
                        if decrypt(new, f.read()) != data:
                            raise StoreError(tr("s_schluessel_erneuern_fehler"))
                if not _kc_write(KEYCHAIN_NEXT, new):
                    raise StoreError(tr("s_schluesselbund_nicht_nutzbar"))
            except Exception:
                for p in written:
                    _remove(p)
                _security(["delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_NEXT])     # no file uses it yet
                raise
            for n in names:                              # from here on the new key opens every replaced file
                os.replace(os.path.join(self.data_dir, n + ".renew"), os.path.join(self.data_dir, n))
            if not _kc_write(KEYCHAIN_ACCOUNT, new):
                self.master = new                        # the files need it now; the next start moves it into the main entry
                raise StoreError(tr("s_schluessel_erneuern_halb"))
            _security(["delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_NEXT])
            self.master = new
            plain.clear()
            log.warning("Data key renewed: %d files encrypted with the new key", len(names))
            return len(names)

    def delete(self, name: str) -> None:
        self._need_key()
        with self._cache_lock:
            self._cache.pop(name, None)
        try:
            os.remove(self.path(name))
        except FileNotFoundError:
            pass
