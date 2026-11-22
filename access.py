"""Zugang zu Kontors Daten: der Datenschluessel kommt nur mit der Anmeldung frei und liegt danach nur im Arbeitsspeicher des
Dienstes, bis er endet.

* key.json (storage.KEY_FILE) haelt den Schluessel nur verpackt: mit einem Schluessel aus dem Passwort (PBKDF2, 600.000
  Runden) und -- wo der Mac es kann und Touch ID an ist -- mit einem Schluessel aus der Secure Enclave, den nur Touch ID oder
  das Mac-Passwort freigibt (auth.touchid_unseal). Ohne Anmeldung ist nichts davon nutzbar, auch nicht am entsperrten Mac.
* start.json haelt, was der Dienst vor der Anmeldung braucht (Port, Adresse, Zertifikat, Sprache, Touch ID, Sperrzeit,
  Offline-Kopie) -- keine Daten.
* Umstellung von frueher (Schluessel im Schluesselbund bzw. in master.key, Passwort in auth.json): bei der ersten Anmeldung mit
  Passwort wird derselbe Schluessel mit dem Passwort verpackt; der alte verschwindet erst, wenn der aus key.json nachweislich
  jede Datei oeffnet -- auch in den Ordnern aus storage.ENC_DIRS. Bricht etwas ab, macht die naechste Anmeldung weiter.
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
LEGACY_FILE = "master.key"
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


def prepare(data_dir: str) -> None:
    """At the service's start, from before (no key file yet): the start settings from the settings, once -- with the key from
    before (the keychain), which until the switch opens the data anyway. Afterwards nothing is read before a sign-in."""
    if os.path.exists(os.path.join(data_dir, START_FILE)) or state(data_dir) != "legacy":
        return
    try:
        key, _ = storage.read_master_key(data_dir)
        raw = Store(data_dir, key, "legacy").read_bytes("config.json")
        write_start(data_dir, json.loads(raw.decode("utf-8")) if raw else {})
        log.info("Start settings taken from the settings once (switch to the key file pending)")
    except Exception as e:                            # nothing known: the defaults (127.0.0.1, port 8765) until the sign-in
        log.warning("Start settings not taken from before: %s", e)


# ---------------------------------------------------------------------------
# Zustand
# ---------------------------------------------------------------------------

def has_data(data_dir: str) -> bool:
    return bool(storage._enc_files(data_dir)) if os.path.isdir(data_dir) else False


def state(data_dir: str) -> str:
    """'login' (the key file is there), 'legacy' (encrypted data from before, the key in the keychain or master.key), 'broken'
    (the key file does not read) or 'new' (nothing there yet: set up)."""
    try:
        rec = storage.key_record(data_dir)
    except StoreError:
        return "broken"
    if rec is not None:
        return "login" if rec.get("password") else "broken"
    return "legacy" if has_data(data_dir) else "new"


def password_set(data_dir: str) -> bool:
    """Is a password set? (The key file -- or, from before, Kontor's password in auth.json beside the data.) A broken key file
    counts as set: never a new setup over data the old key opens."""
    st = state(data_dir)
    return st in ("login", "broken") or (st == "legacy" and os.path.exists(os.path.join(data_dir, "auth.json.enc")))


def touchid_ready(data_dir: str) -> bool:
    """Can Touch ID open the data (the key file holds a key for it and the helper is there)?"""
    try:
        rec = storage.key_record(data_dir)
    except StoreError:
        return False
    e = (rec or {}).get("touchid")
    return bool(e) and not e.get("gone") and auth._helper_current()


def legacy_left(data_dir: str) -> bool:
    """Is a key from before still there (keychain entry, master.key)?"""
    if os.path.exists(os.path.join(data_dir, LEGACY_FILE)):
        return True
    return any(storage._kc_read(a)[0] == 0 for a in (storage.KEYCHAIN_ACCOUNT, storage.KEYCHAIN_NEXT))


# ---------------------------------------------------------------------------
# Anmelden: Schluessel freigeben
# ---------------------------------------------------------------------------

def _legacy_auth(data_dir: str, key: bytes) -> dict:
    raw = Store(data_dir, key, "legacy").read_bytes("auth.json")
    rec = json.loads(raw.decode("utf-8")) if raw else {}
    return rec if isinstance(rec, dict) else {}


def unlock_password(data_dir: str, password: str, finish: bool = True) -> Optional[Tuple[bytes, str]]:
    """(key, how) when the password is right, else None. how: 'password' (key file) -- or, from before, where the key lies
    ('keychain', 'file'; the password checked against auth.json, complete() then makes the key file). From before an
    unfinished renewal is finished first (finish: only under the service's lock); never a new key over data."""
    st = state(data_dir)
    if st == "broken":
        if not legacy_left(data_dir):
            raise StoreError(tr("s_schluesseldatei_kaputt"))
        st = "legacy"                                    # the key from before is still there: it opens, complete() makes the key file anew
    if st == "login":
        with _KeyFileLock(data_dir):
            rec = storage.key_record(data_dir)
            got = storage.open_password_entry(rec["password"], password)
            if got is None:
                return None
            return _checked(data_dir, _finish_renewal(data_dir, rec, *got)), "password"
    if st == "legacy":
        if finish:                                      # a renewal from before that did not finish: first (only under the service's lock)
            storage._finish_renewal(data_dir)
        key, src = storage.load_or_create_master_key(data_dir, finish=False)
        rec = _legacy_auth(data_dir, key)
        return (key, src) if rec and auth.verify_password(password, rec) else None
    return None


def unlock_touchid(data_dir: str) -> Optional[Tuple[bytes, str]]:
    """(key, 'touchid') after Touch ID (or the Mac's password) in the macOS window -- None when not confirmed or not set up."""
    try:
        rec = storage.key_record(data_dir)
    except StoreError:
        return None
    e = (rec or {}).get("touchid")
    if not e or e.get("gone"):
        return None
    try:
        kek = auth.touchid_unseal(str(e.get("se") or ""), str(e.get("eph") or ""), str(e.get("salt") or ""))
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
        a = _legacy_auth(data_dir, key)
        return bool(a) and auth.verify_password(password, a)
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
# Nach der Anmeldung: Schluesseldatei anlegen, Altes entfernen
# ---------------------------------------------------------------------------

def setup_key(data_dir: str, store: Store) -> bytes:
    """The key a first password wraps: the one in use, the one from before (data without a password yet), or a new one --
    a new one only when no encrypted data are there."""
    if store.is_open and store.master is not None:
        return store.master
    if has_data(data_dir):
        key, _ = storage.read_master_key(data_dir)
        return key
    return secrets.token_bytes(32)


def complete(data_dir: str, key: bytes, password: Optional[str] = None) -> bool:
    """After a sign-in (or a first password): the key file with the password where it is missing or another key's, and the
    key from before removed -- only once the key from the key file provably opens every file (set_touchid follows). Returns
    True when nothing from before is left. Anything that fails changes nothing that is needed: the next sign-in tries again."""
    with _KeyFileLock(data_dir):
        try:
            rec = storage.key_record(data_dir)
        except StoreError:
            rec = None                                   # broken: made anew below -- only once the key provably opens every file
        if rec is None or not rec.get("password") or not _opens_or_empty(key, data_dir):
            if password is None:
                return False                             # e.g. Touch ID from before: done at the next sign-in with the password
            bad = storage.files_not_opening(key, data_dir)
            if bad:
                log.error("Key file not made: %d file(s) do not open with the key -- nothing changed", len(bad))
                return False
            storage.write_key_record(data_dir, {"password": storage.password_entry(key, password), "touchid": None})
            got = storage.open_password_entry(storage.key_record(data_dir)["password"], password)
            if not got or got[0] != key:
                raise StoreError(tr("s_schluesseldatei_kaputt"))
            log.warning("Key file made: the data key is wrapped with the password")
        return _drop_legacy(data_dir, key)


def _opens_or_empty(key: bytes, data_dir: str) -> bool:
    return not has_data(data_dir) or storage._opens(key, data_dir)


def _drop_legacy(data_dir: str, key: bytes) -> bool:
    """The key from before (keychain entries, master.key) goes -- only when the key file holds a password entry and the key it
    opens, checked file by file, opens every encrypted file. True when nothing from before is left."""
    if not legacy_left(data_dir):
        return True
    bad = storage.files_not_opening(key, data_dir)
    if bad:
        log.error("Key from before kept: %d file(s) do not open with the key from the key file", len(bad))
        return False
    ok = True
    for acc in (storage.KEYCHAIN_NEXT, storage.KEYCHAIN_ACCOUNT):
        if storage._kc_read(acc)[0] == 0:
            rc, _, _ = storage._security(["delete-generic-password", "-s", storage.KEYCHAIN_SERVICE, "-a", acc])
            ok = ok and rc == 0 and storage._kc_read(acc)[0] == 44
    if os.path.exists(os.path.join(data_dir, LEGACY_FILE)):
        storage._wipe(os.path.join(data_dir, LEGACY_FILE))
        ok = ok and not os.path.exists(os.path.join(data_dir, LEGACY_FILE))
    if ok:
        log.warning("Data key from before removed: the key file opens all %d file(s)", len(storage._enc_files(data_dir)))
    else:
        log.warning("Data key from before not removed completely -- tried again at the next sign-in")
    return ok


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
        rec = storage.key_record(data_dir) or {"touchid": None}
        if _pending(rec):                                # a renewal waits: the next sign-in finishes it first
            raise StoreError(tr("s_schluessel_erneuern_halb"))
        if rec.get("password") and not _opens_or_empty(key, data_dir):
            raise StoreError(tr("s_schluessel_passt_nicht"))
        storage.write_key_record(data_dir, dict(rec, password=storage.password_entry(key, password)))
        got = storage.open_password_entry(storage.key_record(data_dir)["password"], password)
        if not got or got[0] != key:
            raise StoreError(tr("s_schluesseldatei_kaputt"))
    _drop_legacy(data_dir, key)


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
    """Everything deleted with the password (Settings -> Reset): every encrypted file of the store, then the key file and the
    key from before, then the key in memory. A file that does not go stops it before any key is touched."""
    data_dir = store.data_dir
    with _KeyFileLock(data_dir), store._key_lock:       # no file is written meanwhile: the store locks first
        store.close()
        for n in storage._names(data_dir) if os.path.isdir(data_dir) else []:
            if n.endswith((".enc", ".enc.tmp", ".enc.renew")):
                os.remove(os.path.join(data_dir, n))      # one that does not go: the key file stays, a sign-in opens the rest
        storage._remove(os.path.join(data_dir, storage.KEY_FILE))
        for acc in (storage.KEYCHAIN_NEXT, storage.KEYCHAIN_ACCOUNT):
            storage._security(["delete-generic-password", "-s", storage.KEYCHAIN_SERVICE, "-a", acc])
        if os.path.exists(os.path.join(data_dir, LEGACY_FILE)):
            storage._wipe(os.path.join(data_dir, LEGACY_FILE))
    log.warning("Data key forgotten with everything it opened")


def remove_keys(data_dir: str) -> bool:
    """Uninstalling: the key file and the key from before -- only when no encrypted file is left (a key is never deleted
    while data it opens remain). True when no key is left."""
    if any(n.endswith((".enc", ".enc.tmp", ".enc.renew")) for n in (storage._names(data_dir) if os.path.isdir(data_dir) else [])):
        return False
    storage._remove(os.path.join(data_dir, storage.KEY_FILE))
    for acc in (storage.KEYCHAIN_NEXT, storage.KEYCHAIN_ACCOUNT):
        storage._security(["delete-generic-password", "-s", storage.KEYCHAIN_SERVICE, "-a", acc])
    if os.path.exists(os.path.join(data_dir, LEGACY_FILE)):
        storage._wipe(os.path.join(data_dir, LEGACY_FILE))
    return not os.path.exists(os.path.join(data_dir, storage.KEY_FILE)) and not legacy_left(data_dir)


_LEGACY_GONE: set = set()           # data folders where nothing from before is left (the keychain is not asked again)


def key_source(data_dir: str, store: Store) -> str:
    """For the status: 'login' (the key only after a sign-in), else where the key from before lies ('keychain', 'file')."""
    if not store.encrypted:
        return ""
    if state(data_dir) == "login":                       # a key from before still there: shown as such until it is gone
        if data_dir in _LEGACY_GONE or not legacy_left(data_dir):
            _LEGACY_GONE.add(data_dir)
            return "login"
        return "file" if os.path.exists(os.path.join(data_dir, LEGACY_FILE)) else "keychain"
    return store.key_source

