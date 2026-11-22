"""Zugang zu Kontors Daten: der Datenschluessel kommt nur mit der Anmeldung frei und liegt danach nur im Arbeitsspeicher des
Dienstes, bis er endet.

* key.json (storage.KEY_FILE) haelt den Schluessel nur verpackt: mit einem Schluessel aus dem Passwort (PBKDF2, 600.000
  Runden) und -- wo der Mac es kann und Touch ID an ist -- mit einem Schluessel aus der Secure Enclave, den nur Touch ID oder
  das Mac-Passwort freigibt (auth.touchid_unseal). Ohne Anmeldung ist nichts davon nutzbar, auch nicht am entsperrten Mac.
* start.json haelt, was der Dienst vor der Anmeldung braucht (Port, Adresse, Zertifikat, Sprache, Touch ID, Sperrzeit,
  Offline-Kopie) -- keine Daten.
* Ein Schluessel verschwindet erst, wenn der neue nachweislich jede Datei oeffnet -- auch in den Ordnern aus storage.ENC_DIRS
  (Erneuern); bricht etwas ab, macht die naechste Anmeldung weiter. Nie ein neuer Schluessel ueber vorhandene Daten.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import secrets
import threading
from typing import Any, Dict, Optional, Tuple

import auth
import storage
from storage import Store, StoreError
from i18n import tr

log = logging.getLogger("kontor.access")
START_FILE = "start.json"
LOCK_FILE = "key.lock"
METHODS = ("password", "touchid")
# what the service needs before anyone signs in -- settings, no data
START_KEYS = {"port": int, "bind": str, "tls_cert": str, "tls_key": str, "language": str, "touchid": bool, "lock_minutes": int, "offline_copy": bool}
_thread_lock = threading.RLock()


class _KeyFileLock:
    """One change of the key file at a time -- within the service and between the service and the terminal."""

    def __init__(self, data_dir: str):
        self.path = os.path.join(data_dir, LOCK_FILE)

    def __enter__(self):
        _thread_lock.acquire()
        try:
            os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
            self.f = open(self.path, "a")
            os.chmod(self.path, 0o600)
            fcntl.flock(self.f, fcntl.LOCK_EX)
        except BaseException:
            _thread_lock.release()
            raise
        return self

    def __exit__(self, *a):
        try:
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()
        finally:
            _thread_lock.release()


# ---------------------------------------------------------------------------
# Start-Einstellungen (vor der Anmeldung)
# ---------------------------------------------------------------------------

def start_settings(data_dir: str) -> Dict[str, Any]:
    """The settings the service needs before anyone signs in; {} when there are none (yet)."""
    try:
        with open(os.path.join(data_dir, START_FILE), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k in START_KEYS and isinstance(v, START_KEYS[k]) and not (START_KEYS[k] is int and isinstance(v, bool))}


def write_start(data_dir: str, config: dict) -> None:
    """Keeps start.json in step with the settings (written only when something changed)."""
    ui = (config or {}).get("ui") or {}
    new: Dict[str, Any] = {}
    for k, typ in START_KEYS.items():
        v = ui.get(k)
        if typ is int:
            try:
                v = int(v) if v not in (None, "", True, False) else None
            except (TypeError, ValueError):
                v = None
        if isinstance(v, typ) and not (typ is int and isinstance(v, bool)):
            new[k] = v
    if new == start_settings(data_dir):
        return
    try:
        os.makedirs(data_dir, mode=0o700, exist_ok=True)
        storage._write_atomic(os.path.join(data_dir, START_FILE), json.dumps(new, sort_keys=True).encode("utf-8"))
    except OSError as e:
        log.warning("Start settings not written: %s", e)


# ---------------------------------------------------------------------------
# Zustand
# ---------------------------------------------------------------------------

def has_data(data_dir: str) -> bool:
    return bool(storage._enc_files(data_dir)) if os.path.isdir(data_dir) else False


def state(data_dir: str) -> str:
    """'login' (the key file is there), 'broken' (the key file does not read) or 'new' (no key file: set up -- a new key only
    where no encrypted data are, setup_key)."""
    try:
        rec = storage.key_record(data_dir)
    except StoreError:
        return "broken"
    if rec is not None:
        return "login" if rec.get("password") else "broken"
    return "new"


def password_set(data_dir: str) -> bool:
    """Is a password set (the key file)? A broken key file counts as set: never a new setup over data its key opens."""
    return state(data_dir) != "new"


def touchid_ready(data_dir: str) -> bool:
    """Can Touch ID open the data (the key file holds a key for it and the helper is there)?"""
    try:
        rec = storage.key_record(data_dir)
    except StoreError:
        return False
    e = (rec or {}).get("touchid")
    return bool(e) and not e.get("gone") and auth._helper_current()


# ---------------------------------------------------------------------------
# Anmelden: Schluessel freigeben
# ---------------------------------------------------------------------------

def unlock_password(data_dir: str, password: str) -> Optional[Tuple[bytes, str]]:
    """(key, 'password') when the password opens the key file, else None. An unfinished renewal is finished first; never a
    new key over data."""
    st = state(data_dir)
    if st == "broken":
        raise StoreError(tr("s_schluesseldatei_kaputt"))
    if st != "login":
        return None
    with _KeyFileLock(data_dir):
        rec = storage.key_record(data_dir)
        got = storage.open_password_entry(rec["password"], password)
        if got is None:
            return None
        return _checked(data_dir, _finish_renewal(data_dir, rec, *got)), "password"


def unlock_touchid(data_dir: str, reason: str = "", tid: str = "") -> Optional[Tuple[bytes, str]]:
    """(key, 'touchid') after Touch ID (or the Mac's password) in the macOS window -- None when not confirmed or not set up.
    reason: what the window says (what the sign-in opens); tid: the sign-in page's request (auth.touchid_close)."""
    try:
        rec = storage.key_record(data_dir)
    except StoreError:
        return None
    e = (rec or {}).get("touchid")
    if not e or e.get("gone"):
        return None
    try:
        kek = auth.touchid_unseal(str(e.get("se") or ""), str(e.get("eph") or ""), str(e.get("salt") or ""), reason, tid=tid)
    except auth.TouchIdGone:
        # this Mac's Secure Enclave cannot use it (made on another Mac): marked, not offered any more -- it stays until the next
        # sign-in with the password makes a new one, so a single odd answer never takes the only other way in
        with _KeyFileLock(data_dir):
            rec = storage.key_record(data_dir)
            if rec and (rec.get("touchid") or {}).get("se") == e.get("se"):
                storage.write_key_record(data_dir, dict(rec, touchid=dict(rec["touchid"], gone=True)))
        log.warning("Touch ID's key is not usable on this Mac -- a new one is made after a sign-in with the password")
        return None
    if kek is None:
        return None
    with _KeyFileLock(data_dir):
        rec = storage.key_record(data_dir)                # as it is now (a renewal may have finished meanwhile)
        e2 = (rec or {}).get("touchid")
        got = storage.open_entry(kek, e2) if e2 and e2.get("eph") == e.get("eph") else None
        if got is None:
            return None
        return _checked(data_dir, _finish_renewal(data_dir, rec, *got)), "touchid"


def _checked(data_dir: str, key: bytes) -> bytes:
    """The key from the key file must open the data (a quick look; file by file only when the usual files are missing)."""
    if has_data(data_dir) and not storage._opens(key, data_dir) and storage.files_not_opening(key, data_dir):
        raise StoreError(tr("s_schluessel_passt_nicht"))
    return key


def verify_password(data_dir: str, key: bytes, password: str) -> bool:
    """Kontor's password, asked again while signed in: does it open the key in use?"""
    rec = storage.key_record(data_dir)
    if not rec or not rec.get("password"):
        return False
    got = storage.open_password_entry(rec["password"], password)
    return bool(got) and key in got


def _finish_renewal(data_dir: str, rec: dict, key: bytes, nxt: Optional[bytes]) -> bytes:
    """A renewal of the data key that did not finish (the Mac went off in the middle): the next key waits beside the current
    one in the key file. Every file still opening with the current key is encrypted with the next one, then the next one takes
    its place. Returns the key that opens the data. Never drops a key while a file opens only with it."""
    if nxt is None:
        for n in storage._names(data_dir) if os.path.isdir(data_dir) else []:
            if n.endswith(".enc.renew"):                 # written with a key that was never kept: worthless
                storage._remove(os.path.join(data_dir, n))
        return key
    promoted = _promoted(rec)                            # what the key file will say -- checked before any file changes
    for n in storage._enc_files(data_dir):
        p = os.path.join(data_dir, n)
        with open(p, "rb") as f:
            raw = f.read()
        try:
            storage.decrypt(nxt, raw)
            continue
        except StoreError:
            pass
        storage._write_atomic(p, storage.encrypt(nxt, storage.decrypt(key, raw)))     # neither key opens it: stops here, both stay
    for n in storage._names(data_dir):
        if n.endswith(".enc.renew"):
            storage._remove(os.path.join(data_dir, n))
    if storage.files_not_opening(nxt, data_dir):
        raise StoreError(tr("s_schluessel_erneuern_fehler"))
    storage.write_key_record(data_dir, promoted)
    log.warning("Renewal of the data key finished after an interruption")
    return nxt


def _promoted(rec: dict) -> dict:
    """The key file with each next key in the place of the current one. Touch ID's entry without a next key would open
    nothing any more: it goes (set up again after the sign-in); the password's entry always has one (else: broken)."""
    out = dict(rec)
    for m in METHODS:
        e = rec.get(m)
        if isinstance(e, dict) and e.get("next"):
            out[m] = {k: v for k, v in e.items() if k != "next"}
            out[m]["key"] = e["next"]
        elif isinstance(e, dict):
            if m == "password":
                raise StoreError(tr("s_schluesseldatei_kaputt"))
            out[m] = None
    return out


# ---------------------------------------------------------------------------
# Einrichten, Touch ID, Passwort, Erneuern, Zuruecksetzen
# ---------------------------------------------------------------------------

def setup_key(data_dir: str, store: Store) -> bytes:
    """The key a first password wraps: the one in use (the store already open), or a new one -- a new one only when no
    encrypted data are there (their key would be lost: they stay, nothing is set up over them)."""
    if store.is_open and store.master is not None:
        return store.master
    if has_data(data_dir):
        raise StoreError(tr("s_schluessel_passt_nicht"))
    return secrets.token_bytes(32)


def complete(data_dir: str, key: bytes, password: str) -> bool:
    """The first password: the key file with the data key wrapped with it -- only where there is none yet and the key provably
    opens every file (set_touchid follows); read back before it counts. False: nothing changed."""
    with _KeyFileLock(data_dir):
        if storage.key_record(data_dir) is not None:     # (a broken one raises: never written over)
            log.error("Key file not made: there is one already -- nothing changed")
            return False
        bad = storage.files_not_opening(key, data_dir)
        if bad:
            log.error("Key file not made: %d file(s) do not open with the key -- nothing changed", len(bad))
            return False
        storage.write_key_record(data_dir, {"password": storage.password_entry(key, password), "touchid": None})
        got = storage.open_password_entry(storage.key_record(data_dir)["password"], password)
        if not got or got[0] != key:
            raise StoreError(tr("s_schluesseldatei_kaputt"))
        log.warning("Key file made: the data key is wrapped with the password")
        return True


def _opens_or_empty(key: bytes, data_dir: str) -> bool:
    return not has_data(data_dir) or storage._opens(key, data_dir)


def _touch_entry(key: bytes, nxt: Optional[bytes] = None, prev: Optional[dict] = None) -> Optional[dict]:
    """The data key (and the next one) wrapped with a key only Touch ID (or the Mac's password) releases: the Secure Enclave's
    key of this Mac (kept from prev, else a new one) and a fresh key pair for wrapping. None where the Mac cannot."""
    se, pub = (str(prev.get("se") or ""), str(prev.get("pub") or "")) if prev else ("", "")
    if not (se and pub):
        made = auth.touchid_new_key()
        if made is None:
            return None
        se, pub = made
    salt = secrets.token_hex(16)
    sealed = auth.touchid_seal(pub, salt)
    if sealed is None:
        return None
    eph, kek = sealed
    return storage.wrap_entry(kek, key, nxt, se=se, pub=pub, eph=eph, salt=salt)


def _pending(rec: Optional[dict]) -> bool:
    """A renewal waits in the key file (next keys): no entry is changed until a sign-in has finished it."""
    return any(isinstance((rec or {}).get(m), dict) and rec[m].get("next") for m in METHODS)


def _set_touchid(data_dir: str, rec: dict, key: bytes, on: bool) -> bool:
    """Touch ID's entry in the key file as switched (under the key file's lock). True when Touch ID can open the data. An
    entry this Mac's Secure Enclave could not use stays until a new one is made (it is the only other way in)."""
    if _pending(rec):
        return False
    e0 = rec.get("touchid")
    has = bool(e0) and not e0.get("gone")
    if on and not has:
        e = _touch_entry(key)
        if e is None:
            log.info("Touch ID cannot open the data on this Mac (no Secure Enclave or helper) -- the password does")
            return False
        storage.write_key_record(data_dir, dict(rec, touchid=e))
        log.info("Touch ID can open the data")
        return True
    if not on and e0:
        storage.write_key_record(data_dir, dict(rec, touchid=None))
        log.info("Touch ID no longer opens the data")
    return on and has


def set_touchid(data_dir: str, key: bytes, on: bool) -> bool:
    """Touch ID switched on or off: its entry in the key file made or removed. True when Touch ID can open the data."""
    with _KeyFileLock(data_dir):
        rec = storage.key_record(data_dir)
        if not rec or not rec.get("password"):
            return False
        return _set_touchid(data_dir, rec, key, on)


def change_password(data_dir: str, key: bytes, password: str) -> None:
    """A new password: the key wrapped with it (Touch ID's entry stays). Read back before it counts."""
    with _KeyFileLock(data_dir):
        rec = storage.key_record(data_dir)
        if not rec or not rec.get("password"):
            raise StoreError(tr("s_schluesseldatei_kaputt"))
        if _pending(rec):                                # a renewal waits: the next sign-in finishes it first
            raise StoreError(tr("s_schluessel_erneuern_halb"))
        if not _opens_or_empty(key, data_dir):
            raise StoreError(tr("s_schluessel_passt_nicht"))
        storage.write_key_record(data_dir, dict(rec, password=storage.password_entry(key, password)))
        got = storage.open_password_entry(storage.key_record(data_dir)["password"], password)
        if not got or got[0] != key:
            raise StoreError(tr("s_schluesseldatei_kaputt"))


def renew(store: Store, password: str) -> int:
    """A new data key (Settings -> Backup): every file re-encrypted (Store.renew_key); meanwhile the key file holds the next
    key beside the current one, wrapped the same way -- an interruption is finished at the next sign-in. Returns the number
    of files."""
    data_dir = store.data_dir
    with _KeyFileLock(data_dir):
        rec = storage.key_record(data_dir)
        if not rec or not rec.get("password"):
            raise StoreError(tr("s_schluessel_erneuern_nicht"))

        def keep(old: bytes, new: bytes) -> None:
            r = dict(rec, password=storage.password_entry(old, password, nxt=new))
            if rec.get("touchid") and not rec["touchid"].get("gone"):
                r["touchid"] = _touch_entry(old, new, rec["touchid"])       # None: Touch ID set up again afterwards
            else:
                r["touchid"] = None
            storage.write_key_record(data_dir, r)

        def take(new: bytes) -> None:
            storage.write_key_record(data_dir, _promoted(storage.key_record(data_dir)))

        n = store.renew_key(keep, take)
        if not storage.key_record(data_dir).get("touchid") and rec.get("touchid"):
            _set_touchid(data_dir, storage.key_record(data_dir), store.master, True)
        return n


def forget(store: Store) -> None:
    """Everything deleted with the password (Settings -> Reset): every encrypted file of the store, then the key file, then
    the key in memory. A file that does not go stops it before the key file is touched."""
    data_dir = store.data_dir
    with _KeyFileLock(data_dir), store._key_lock:       # no file is written meanwhile: the store locks first
        store.close()
        for n in storage._names(data_dir) if os.path.isdir(data_dir) else []:
            if n.endswith((".enc", ".enc.tmp", ".enc.renew")):
                os.remove(os.path.join(data_dir, n))      # one that does not go: the key file stays, a sign-in opens the rest
        storage._remove(os.path.join(data_dir, storage.KEY_FILE))
    log.warning("Data key forgotten with everything it opened")


def remove_keys(data_dir: str) -> bool:
    """Uninstalling: the key file -- only when no encrypted file is left (a key is never deleted while data it opens remain).
    True when no key is left."""
    if any(n.endswith((".enc", ".enc.tmp", ".enc.renew")) for n in (storage._names(data_dir) if os.path.isdir(data_dir) else [])):
        return False
    storage._remove(os.path.join(data_dir, storage.KEY_FILE))
    return not os.path.exists(os.path.join(data_dir, storage.KEY_FILE))
