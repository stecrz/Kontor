"""Verschluesselte Ablage der Programmdaten.

Alle Dateien im Datenordner (Konfiguration, Planwerte, Zustand, Bericht, Ordner aus ENC_DIRS) liegen verschluesselt:
AES-256-CBC (ueber /usr/bin/openssl, auf jedem Mac vorhanden) plus HMAC-SHA256 ueber den Chiffretext (Encrypt-then-MAC).
Der Hauptschluessel (32 Byte Zufall) liegt nur verpackt in key.json -- mit einem Schluessel aus dem Passwort (und per Touch
ID, access.py); erst die Anmeldung gibt ihn frei, danach liegt er nur im Arbeitsspeicher des Dienstes. Bis dahin ist der Store
gesperrt (Store.closed, is_open): jedes Lesen und Schreiben wirft StoreLocked.

Dateiformat: b"MMT1" + openssl-Ausgabe ("Salted__" + Salt + Chiffretext) + 32 Byte HMAC.
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
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple
from i18n import tr

_MISSING = object()
CACHE_MAX_BYTES = 24 * 1024 * 1024
log = logging.getLogger("kontor.store")

MAGIC = b"MMT1"


class StoreError(Exception):
    pass


class StoreLocked(StoreError):
    """The store has no key yet (nobody signed in since the service started): nothing can be read or written."""


class StoreDamaged(StoreError):
    """A file of the store that the key does not open or whose content is not what was written (not the store's format, the
    check sum does not match, no JSON): damaged for good -- unlike a failure that may pass (openssl missing, the disk not
    answering), which stays a plain StoreError. name: the file, as the store names it."""

    def __init__(self, text: str, name: str = ""):
        super().__init__(text)
        self.name = name


# ---------------------------------------------------------------------------
# Schluessel
# ---------------------------------------------------------------------------

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


# A file that does not read is never deleted. Two names keep such a file out of the store (neither ends in ".enc", so no key
# is asked to open it and none waits for it): ".damaged-<time>" for settings or state set aside at a sign-in (Store.set_aside),
# and ".left" for the moments a renewal of the key changes the files (Store.renew_key) -- afterwards it has its name again.
DAMAGED = ".damaged-"
LEFT = ".left"


def _restore_left(data_dir: str) -> None:
    """Files a renewal of the key had put out of its way and could not put back (the Mac went off in the middle): back under
    their names -- unless a new file took the name meanwhile (then it stays beside it; nothing is overwritten)."""
    for n in _names(data_dir) if os.path.isdir(data_dir) else []:
        if n.endswith(".enc" + LEFT):
            src, dst = os.path.join(data_dir, n), os.path.join(data_dir, n[:-len(LEFT)])
            try:
                if not os.path.exists(dst):
                    os.rename(src, dst)
            except OSError as e:
                log.warning("A file left out of a renewal did not get its name back: %s", type(e).__name__)


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


def _subkeys(master: bytes) -> Tuple[str, bytes]:
    enc_secret = hmac.new(master, b"mmtools-enc", hashlib.sha256).hexdigest()
    mac_key = hmac.new(master, b"mmtools-mac", hashlib.sha256).digest()
    return enc_secret, mac_key


# ---------------------------------------------------------------------------
# Verschluesselung
# ---------------------------------------------------------------------------

_PASS: Optional[str] = None      # how openssl gets the secret: "fd" (a pipe) or "env" (an openssl that cannot read a pipe)


def _openssl_run(args, data: bytes, secret: str, how: str) -> bytes:
    """openssl enc with the secret over a pipe (fd: no other program of this user sees it -- the environment of a process
    they can read, `ps -E`) or, only where openssl cannot read a pipe, in its environment as before."""
    opts = args + ["-aes-256-cbc", "-md", "sha256"]
    try:
        if how == "fd":
            rfd, wfd = os.pipe()
            try:
                os.write(wfd, secret.encode("ascii"))     # 64 hex digits: far below what a pipe holds, never blocks
                os.close(wfd)
                wfd = -1
                r = subprocess.run(["openssl", "enc"] + opts + ["-pass", "fd:%d" % rfd], input=data, capture_output=True, timeout=600, pass_fds=(rfd,))
            finally:
                os.close(rfd)
                if wfd >= 0:
                    os.close(wfd)
        else:
            r = subprocess.run(["openssl", "enc"] + opts + ["-pass", "env:MMTOOLS_SECRET"], input=data, capture_output=True, timeout=600,
                               env=dict(os.environ, MMTOOLS_SECRET=secret))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        raise StoreError(tr("s_openssl_nicht_verfuegbar_s") % e)
    if r.returncode != 0:
        raise StoreError(tr("s_openssl_fehler_s") % r.stderr.decode(errors="replace")[:200])
    return r.stdout


def _pass_mode() -> str:
    """Once: does openssl take the secret over a pipe exactly as from its environment? Checked with a made-up secret --
    encrypted over the pipe, decrypted the old way. Only then the pipe; else the environment as before (logged)."""
    global _PASS
    if _PASS is None:
        probe, secret = secrets.token_bytes(64), secrets.token_hex(32)
        try:
            same = _openssl_run(["-d"], _openssl_run(["-salt"], probe, secret, "fd"), secret, "env") == probe
        except StoreError:
            same = False
        _PASS = "fd" if same else "env"
        if not same:
            log.warning("openssl does not read the secret from a pipe -- it gets it in its environment, as before")
    return _PASS


def _openssl(args, data: bytes, secret: str) -> bytes:
    return _openssl_run(args, data, secret, _pass_mode())


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


def damage(master: bytes, blob: bytes) -> Optional[str]:
    """Why this key will never open the file -- not the store's format, or the check sum over it does not match (the file
    changed, or it was written with another key) -- or None: it is as it was written with this key. Nothing is decrypted, so
    this tells "damaged for good" from a failure that may pass (openssl missing or not answering)."""
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 32 + 16:
        return tr("s_datei_hat_nicht_das_erwartete")
    if not hmac.compare_digest(hmac.new(_subkeys(master)[1], blob[len(MAGIC):-32], hashlib.sha256).digest(), blob[-32:]):
        return tr("s_pruefsumme_stimmt_nicht_datei_veraende")
    return None


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

    def __init__(self, data_dir: str, master: Optional[bytes] = None):
        self.data_dir = data_dir
        self.master = master
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
        self._key_lock = threading.RLock()            # no file is read, written or deleted while the key is renewed
        self.renew_left: list = []                    # files the last renewal of the key left as they are (no key opens them)

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

    def unlock(self, master: bytes) -> None:
        """The key, once someone signed in: from here on the store reads and writes."""
        if not selftest(master):
            raise StoreError(tr("s_ohne_verschluesselung"))
        with self._key_lock:
            self.master, self.encrypted = master, True
            with self._cache_lock:
                self._cache.clear()
            _restore_left(self.data_dir)                 # (what a renewal that broke off had put out of its way)

    def close(self) -> None:
        """Drops the key from memory (everything deleted with the password): locked again until someone sets one up."""
        with self._key_lock:
            self.master, self.encrypted = None, True
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
            raise StoreDamaged(tr("s_s_ist_kein_gueltiges_json") % (name, e), name)
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

    def read_record(self, name: str) -> Tuple[dict, str]:
        """A document that holds a record (settings, state): (record, "") -- {} when there is none -- or ({}, why) when the
        file is damaged for good: it does not open with the key, is no JSON or holds no record. What may pass (the disk,
        openssl) raises, as with load."""
        try:
            doc = self.load(name, {}) or {}
        except StoreDamaged as e:
            return {}, str(e)
        return (doc, "") if isinstance(doc, dict) else ({}, "%s: %s" % (os.path.basename(self.path(name)), tr("s_datei_hat_nicht_das_erwartete")))

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
                try:
                    return decrypt(self.master, raw)
                except StoreError:
                    why = damage(self.master, raw)
                    if why is None:                      # (openssl: may pass)
                        raise
                    raise StoreDamaged("%s: %s" % (os.path.basename(p), why), name) from None      # which file: the message alone would leave you guessing
            return raw

    def write_bytes(self, name: str, data: bytes) -> None:
        self._need_key()
        p = self.path(name)
        if os.path.dirname(name):                        # a file in one of the store's folders (ENC_DIRS): the folder first, only for the user
            os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
        with self._key_lock:
            self._need_key()
            payload = encrypt(self.master, data) if self.encrypted else data
            # whole or not at all, and on the disk before it takes the name: the Mac going off right after never leaves a
            # file that has its name but not its content (state.json is written every few minutes)
            _write_atomic(p, payload)
            os.chmod(p, 0o600)

    def renew_key(self, keep: Callable[[bytes, bytes], None], take: Callable[[bytes], None]) -> int:
        """A new data key: every encrypted file of the store (also in its folders, ENC_DIRS) is decrypted with the old key and
        written anew with the new one. The old key stays until all files provably open with the new one: first everything is
        written beside the files and checked, then keep(old, new) keeps the new key beside the old one (the key file), only then
        the files are replaced and take(new) lets the new key take the old one's place. Interrupted after keep, the next sign-in
        finishes it. Returns the number of files.
        A file the old key does not open (damaged: no key opens it, so none is lost with the old one) does not stop the
        renewal: it stays as it is, byte for byte, and is named in renew_left (and the log). While the files change it is
        out of the way under another name (LEFT) -- an interrupted renewal is finished by reading every file of the store
        with one of the two keys, and would stop at it for good; afterwards (or at the next sign-in) it has its name again.
        A file that cannot be read for another reason (the disk, openssl) still stops it before anything changes."""
        self._need_key()
        if not self.encrypted:
            raise StoreError(tr("s_ohne_verschluesselung"))
        with self._key_lock:
            old = self.master
            names = []
            left: list = []
            plain: Dict[str, bytes] = {}
            for n in _enc_files(self.data_dir):          # everything opens with the old key (or with none), or nothing changes
                with open(os.path.join(self.data_dir, n), "rb") as f:
                    raw = f.read()
                try:
                    plain[n] = decrypt(old, raw)
                    names.append(n)
                except StoreError:
                    if damage(old, raw) is None:         # (openssl: may pass -- nothing changes)
                        raise
                    left.append(n)
            new = secrets.token_bytes(32)
            if new == old or not selftest(new):
                raise StoreError(tr("s_ohne_verschluesselung"))
            written, kept, aside = [], False, []
            try:
                for n, data in plain.items():
                    p = os.path.join(self.data_dir, n + ".renew")
                    _write_atomic(p, encrypt(new, data))
                    written.append(p)
                    with open(p, "rb") as f:
                        if decrypt(new, f.read()) != data:
                            raise StoreError(tr("s_schluessel_erneuern_fehler"))
                for n in left:                           # out of the way before the key file names two keys
                    os.rename(os.path.join(self.data_dir, n), os.path.join(self.data_dir, n + LEFT))
                    aside.append(n)
                if aside:
                    _sync_dir(self.data_dir)
                    for sub in ENC_DIRS:
                        _sync_dir(os.path.join(self.data_dir, sub))
                kept = True
                keep(old, new)
            except Exception as e:
                for p in written:
                    _remove(p)
                if not kept:
                    _restore_left(self.data_dir)
                    raise
                # the key file may hold the next key already: the old one in memory must not write on -- locked, the next
                # sign-in sees the key file as it is and finishes (or, without a next key there, simply opens)
                log.warning("Renewal of the data key not finished (%s) -- locked, finished at the next sign-in", type(e).__name__)
                self.close()
                raise StoreError(tr("s_schluessel_erneuern_halb")) from e
            try:
                for n in names:                          # from here on the new key opens every replaced file
                    os.replace(os.path.join(self.data_dir, n + ".renew"), os.path.join(self.data_dir, n))
                self.master = new                        # the files need it now
                with self._cache_lock:
                    self._cache.clear()
                take(new)
            except Exception as e:
                # some files may have the new key, others the old one: neither key in memory would do -- the store locks, and
                # the next sign-in finishes it from the key file (both keys wait there)
                log.warning("Renewal of the data key not finished (%s) -- locked, finished at the next sign-in", type(e).__name__)
                self.close()
                raise StoreError(tr("s_schluessel_erneuern_halb")) from e
            plain.clear()
            _restore_left(self.data_dir)
            self.renew_left = list(left)
            log.warning("Data key renewed: %d files encrypted with the new key", len(names))
            for n in left:                               # (file names of the store say nothing about you)
                log.warning("Data key renewed: %s opens with no key (damaged) -- left as it is", n)
            return len(names)

    def read_raw(self, name: str) -> Optional[bytes]:
        """The file as it lies on the disk (encrypted, also one that does not open) -- to put it back byte for byte (put_raw).
        None: there is none."""
        with self._key_lock:
            self._need_key()
            try:
                with open(self.path(name), "rb") as f:
                    return f.read()
            except FileNotFoundError:
                return None

    def put_raw(self, name: str, blob: Optional[bytes]) -> None:
        """A file back as read_raw gave it (None: there was none -- it goes)."""
        if blob is None:
            self.delete(name)
            return
        with self._key_lock:
            self._need_key()
            _write_atomic(self.path(name), blob)
            os.chmod(self.path(name), 0o600)
            with self._cache_lock:
                self._cache.pop(name, None)

    def held(self) -> "threading.RLock":
        """Held (with ...): the key is not renewed meanwhile -- for deleting files of the folder by their own names (leftovers
        .tmp/.renew among them): the renewal would write a file again that was deleted while it ran."""
        return self._key_lock

    def delete(self, name: str) -> None:
        with self._key_lock:                             # not while the key is renewed: the renewal would write the file again
            self._need_key()
            with self._cache_lock:
                self._cache.pop(name, None)
            try:
                os.remove(self.path(name))
            except FileNotFoundError:
                pass

    def set_aside(self, name: str) -> Optional[str]:
        """A file that does not read (damaged), out of the way so that Kontor can go on without it: renamed, never deleted or
        changed -- "<file>.damaged-<date>-<time>" beside it. Returns the new file name (None: there was no such file)."""
        with self._key_lock:
            self._need_key()
            src = self.path(name)
            if not os.path.exists(src):
                return None
            stamp, n = time.strftime("%Y%m%d-%H%M%S"), 0
            while True:
                dst = src + DAMAGED + stamp + ("-%d" % n if n else "")
                if not os.path.exists(dst):
                    break
                n += 1
            os.rename(src, dst)
            _sync_dir(os.path.dirname(dst))
            with self._cache_lock:
                self._cache.pop(name, None)
            return os.path.basename(dst)
