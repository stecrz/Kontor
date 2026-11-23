"""Devices added at the Mac (Einstellungen -> Zugang): each iPhone's passkey, the one-time pairing link and the one-time
challenges a sign-in or a change from an iPhone is signed over.

devices.json, encrypted in Kontor's data folder like every file there: per device a random id, the name typed at pairing,
the passkey's credential id and public key (the private key never leaves the iPhone), a random user handle (nothing
personal), the host name it belongs to (rpId), whether it may change things (with Face ID; chosen on the card at the Mac,
changed there), its flag BE at registration, its sign count, when it was added and last used -- and "Nur mit Face ID". Never in
a backup, a package or the log; reset and uninstall remove it. A damaged file is set aside (never deleted), Kontor goes on
with no devices and "Nur mit Face ID" on (fail closed: no password session from elsewhere comes of it), the page names it.

Pairing links and challenges live in memory only: random (32 bytes), single use, short-lived by the monotonic clock (the
Mac's clock being set stretches nothing): a pairing link 10 minutes, only the newest one and only while the Mac's session that
made it lasts; a challenge 2 minutes and only for what it was made for. Challenges are kept apart by purpose and by whom they
belong to (an address for signing in and pairing, a session for a confirmation): a few each -- nobody can push out another's,
and a session's confirmations never go for anyone else's. Asking for a sign-in challenge has its own budget per address.
"""
from __future__ import annotations

import hmac
import logging
import re
import secrets
import threading
import time
import unicodedata
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from i18n import tr
from storage import StoreDamaged, StoreError

log = logging.getLogger("kontor.devices")

DEVICES_FILE = "devices.json"
MAX_DEVICES = 20
NAME_MAX = 40
PAIR_SECONDS = 600
CHALLENGE_SECONDS = 120
PER_OWNER = {"login": 3, "pair": 2, "confirm": 4}      # outstanding challenges per address (login, pair) or session (confirm)
MAX_OWNERS = 256                    # addresses with challenges for signing in or pairing at once (the longest waiting goes first)
OPTIONS_PER_MINUTE = 10             # sign-in challenges one address may ask for
MAX_BUDGETS = 1024
_ID = re.compile(r"d[0-9a-f]{16}")


class NotWritable(ValueError):
    """The list of devices cannot be saved right now (the text for the page)."""
    def __init__(self) -> None:
        super().__init__(tr("s_pk_liste_nicht_speicherbar"))


def clean_name(name: Any) -> str:
    """A device's name as typed: printable characters only, at most NAME_MAX, never empty."""
    text = "".join(ch for ch in str(name or "") if unicodedata.category(ch)[0] not in "C")
    text = " ".join(text.split())[:NAME_MAX].strip()
    return text or "iPhone"


class Devices:
    def __init__(self, store, clock: Callable[[], float] = time.monotonic):
        self.store = store
        self.clock = clock
        self._lock = threading.Lock()
        self._pair: Optional[Dict[str, Any]] = None
        self._ch: Dict[str, Dict[str, Dict[bytes, Dict[str, Any]]]] = {p: {} for p in PER_OWNER}
        self._budget: Dict[str, List[float]] = {}
        self._closed: Optional[dict] = None              # the file damaged and not written anew: no devices, "Nur mit Face ID" on

    # -- the file ---------------------------------------------------------------------------------------------------------
    def _doc(self) -> dict:
        """devices.json as stored -- a damaged one set aside (fail closed); one that does not read right now (openssl, the
        disk) counts as no devices with "Nur mit Face ID" on, for this time ("unread": a session of a device does not end
        because of it, see present)."""
        if not self.store.is_open:
            return {}
        if self._closed is not None:
            return {"devices": [], "passkey_only": True, "damaged": self._closed}
        try:
            doc = self.store.load_shared(DEVICES_FILE, {}) or {}
            if isinstance(doc, dict) and isinstance(doc.get("devices", []), list):
                return doc
            why = "not a list of devices"
        except StoreDamaged as e:
            why = str(e)
        except StoreError as e:                          # may pass: nothing set aside, nothing let in
            log.warning("Devices not readable right now (%s) -- none until they are", type(e).__name__)
            return {"devices": [], "passkey_only": True, "unread": True}
        return self._set_aside(why)

    def _set_aside(self, why: str) -> dict:
        try:
            kept = self.store.set_aside(DEVICES_FILE) or ""
        except (OSError, StoreError):
            kept = ""
        rec = {"kept": kept, "time": datetime.now().strftime("%Y-%m-%d %H:%M")}
        log.error("devices.json does not read (%s) -- set aside as %s; no devices, sign-in from elsewhere only with Face ID", why[:120], kept or "?")
        fresh = {"devices": [], "passkey_only": True, "damaged": rec}
        try:
            self.store.save(DEVICES_FILE, fresh)
        except (OSError, StoreError):
            self._closed = rec                           # not written: the same in memory, until the service ends
        return fresh

    def damaged(self) -> Optional[dict]:
        """The damaged list set aside ({"kept", "time"}) until a device is added again -- for Einstellungen -> Zugang."""
        d = self._doc().get("damaged")
        return d if isinstance(d, dict) else None

    def _update(self, fn: Callable[[dict], None]) -> None:
        self._doc()                                      # (a damaged file first set aside)
        if self._closed is not None:
            raise NotWritable()
        try:
            self.store.update(DEVICES_FILE, fn, {"devices": []})
        except StoreError as e:                          # (never written over what did not read)
            log.warning("Devices not saved (%s)", type(e).__name__)
            raise NotWritable() from e

    # -- the devices ------------------------------------------------------------------------------------------------------
    def all(self) -> List[dict]:
        """Every device (copies). Nothing while the data are locked."""
        return [dict(d) for d in (self._doc().get("devices") or []) if isinstance(d, dict) and _ID.fullmatch(str(d.get("id") or ""))]

    def readable(self) -> bool:
        """False while the list does not read right now (a passing error): no sign-in with a passkey meanwhile."""
        return not self._doc().get("unread")

    def present(self, did: Any) -> Optional[bool]:
        """Is this device added? None while the list does not read right now -- nothing ends because of a passing error."""
        doc = self._doc()
        if doc.get("unread"):
            return None
        return any(isinstance(d, dict) and d.get("id") == did for d in doc.get("devices") or []) if isinstance(did, str) and _ID.fullmatch(did) else False

    def get(self, did: Any) -> Optional[dict]:
        if not isinstance(did, str) or not _ID.fullmatch(did):
            return None
        return next((d for d in self.all() if d["id"] == did), None)

    def by_credential(self, cred: bytes) -> Optional[dict]:
        from webauthn import b64u
        want = b64u(cred)
        return next((d for d in self.all() if hmac.compare_digest(str(d.get("cred") or ""), want)), None)

    def add(self, name: str, cred: bytes, x: int, y: int, user: bytes, rp: str, count: int, changes: bool = False, be: bool = False) -> dict:
        from webauthn import b64u
        dev = {"id": "d" + secrets.token_hex(8), "name": clean_name(name), "cred": b64u(cred), "x": "%064x" % x, "y": "%064x" % y,
               "user": b64u(user), "rp": rp, "changes": bool(changes), "be": bool(be), "count": int(count),
               "added": datetime.now().strftime("%Y-%m-%d %H:%M"), "used": None}

        def put(doc: dict) -> None:
            devs = [d for d in doc.get("devices") or [] if isinstance(d, dict)]
            if len(devs) >= MAX_DEVICES:
                raise ValueError("too many devices")
            if any(d.get("cred") == dev["cred"] for d in devs):
                raise ValueError("passkey already added")
            doc["devices"] = devs + [dev]
            doc.pop("damaged", None)                     # a device added again: the note on the damaged list is done
        self._update(put)
        return dev

    def set_changes(self, did: str, changes: bool) -> bool:
        """Whether this device may change things (with Face ID) -- only at the Mac."""
        found = []

        def upd(doc: dict) -> None:
            for d in doc.get("devices") or []:
                if isinstance(d, dict) and d.get("id") == did:
                    d["changes"] = bool(changes)
                    found.append(d)
        if self.get(did) is None:
            return False
        self._update(upd)
        return bool(found)

    def remove(self, did: str) -> Optional[dict]:
        """The device gone (its passkey works no more): what it was, or None."""
        gone: List[dict] = []

        def drop(doc: dict) -> None:
            devs = [d for d in doc.get("devices") or [] if isinstance(d, dict)]
            gone.extend(d for d in devs if d.get("id") == did)
            doc["devices"] = [d for d in devs if d.get("id") != did]
        if self.get(did) is None:
            return None
        self._update(drop)
        with self._lock:                                 # its open challenges too
            for owner, mine in list(self._ch["confirm"].items()):
                for k in [k for k, v in mine.items() if v["bind"].get("device") == did]:
                    mine.pop(k, None)
        return gone[0] if gone else None

    def used(self, did: str, count: int) -> None:
        """After a signature that checked out: its sign count (never lower than before) and when."""
        def upd(doc: dict) -> None:
            for d in doc.get("devices") or []:
                if isinstance(d, dict) and d.get("id") == did:
                    d["count"] = max(int(d.get("count") or 0), int(count))
                    d["used"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            self._update(upd)
        except ValueError:                               # not writable (damaged and not written anew): nothing to note it in
            pass

    def passkey_only(self) -> bool:
        """Sign-in from other devices only with the passkey of an added device (while the data are open; after a restart the
        password opens them once, then Face ID). As set at the Mac -- not set: on as soon as a device was added; a damaged
        list: on."""
        if not self.store.is_open:
            return False
        doc = self._doc()
        v = doc.get("passkey_only")
        return v if isinstance(v, bool) else bool(self.all())

    def passkey_only_set(self) -> Optional[bool]:
        doc = self._doc()
        return doc.get("passkey_only") if isinstance(doc.get("passkey_only"), bool) else None

    def set_passkey_only(self, on: bool) -> None:
        self._update(lambda doc: doc.__setitem__("passkey_only", bool(on)))

    def forget(self) -> None:
        """Every device, link and challenge gone (reset)."""
        with self._lock:
            self._pair = None
            for p in self._ch:
                self._ch[p].clear()
            self._closed = None
        if self.store.is_open:
            self.store.delete(DEVICES_FILE)

    # -- the pairing link (made at the Mac) -------------------------------------------------------------------------------
    def pairing_new(self, changes: bool, by: str = "", first: bool = False) -> str:
        """A new link (the one before is no longer valid). changes: whether this iPhone may change things (with Face ID);
        by: the Mac's session that made it -- the link holds only while it lasts (see service); first: made while no device
        was added (the first one, added with the tick, switches "Änderungen vom iPhone" on)."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._pair = {"token": token, "until": self.clock() + PAIR_SECONDS, "changes": bool(changes), "by": str(by or ""), "first": bool(first)}
        return token

    def pairing_state(self, with_token: bool = False) -> Optional[dict]:
        """The link while it holds: seconds left, whether changes are allowed -- with_token: also the link itself (only for
        the Mac's own page, which shows it as a QR code)."""
        with self._lock:
            p = self._pair
            if p is None or self.clock() >= p["until"]:
                self._pair = None
                return None
            out = {"seconds": int(p["until"] - self.clock()), "changes": p["changes"]}
            return dict(out, token=p["token"]) if with_token else out

    def pairing_set(self, changes: bool) -> bool:
        with self._lock:
            if self._pair is None or self.clock() >= self._pair["until"]:
                return False
            self._pair["changes"] = bool(changes)
            return True

    def pairing_cancel(self) -> None:
        with self._lock:
            self._pair = None

    def pairing_check(self, token: Any) -> Optional[dict]:
        """The link's state when token is the current one and still valid (it stays valid until used)."""
        if not isinstance(token, str) or not 20 <= len(token) <= 64:
            return None
        with self._lock:
            p = self._pair
            if p is None or self.clock() >= p["until"]:
                self._pair = None
                return None
            if not hmac.compare_digest(p["token"].encode("ascii"), token.encode("utf-8")):
                return None
            return dict(p)

    def pairing_take(self, token: str) -> Optional[dict]:
        """Uses the link up (once a device was added with it)."""
        with self._lock:
            p = self._pair
            if p is None or self.clock() >= p["until"] or not hmac.compare_digest(p["token"].encode("ascii"), str(token).encode("utf-8")):
                return None
            self._pair = None
            return p

    # -- challenges -------------------------------------------------------------------------------------------------------
    def allow(self, owner: str, per_minute: int = OPTIONS_PER_MINUTE) -> bool:
        """The budget of an address for sign-in challenges: at most per_minute in a minute (False: wait)."""
        with self._lock:
            now = self.clock()
            seen = [t for t in self._budget.pop(owner, []) if now - t < 60]
            ok = len(seen) < per_minute
            if ok:
                seen.append(now)
            self._budget[owner] = seen                   # (to the end: the longest quiet go first)
            while len(self._budget) > MAX_BUDGETS:
                self._budget.pop(next(iter(self._budget)))
            return ok

    def challenge_new(self, purpose: str, owner: str, bind: Dict[str, Any]) -> bytes:
        """A challenge for purpose ("login", "pair", "confirm"), belonging to owner (an address, a session). An owner keeps a
        few (PER_OWNER: its own oldest goes); for signing in and pairing at most MAX_OWNERS addresses at once (the one waiting
        longest goes); a session's confirmations are never pushed out by anyone else."""
        raw = secrets.token_bytes(32)
        with self._lock:
            now, store = self.clock(), self._ch[purpose]
            for o in list(store):
                live = {k: v for k, v in store[o].items() if now < v["until"]}
                if live:
                    store[o] = live
                else:
                    del store[o]
            mine = store.pop(owner, {})
            while len(mine) >= PER_OWNER[purpose]:
                mine.pop(next(iter(mine)))
            if purpose != "confirm":
                while len(store) >= MAX_OWNERS:
                    store.pop(next(iter(store)))
            mine[raw] = {"bind": dict(bind), "until": now + CHALLENGE_SECONDS}
            store[owner] = mine
        return raw

    def challenge_take(self, raw: bytes, purpose: str, owner: str) -> Optional[Dict[str, Any]]:
        """What the challenge was made for -- once: it is gone whatever follows. None when unknown, used, expired, made for
        something else or someone else."""
        if not isinstance(raw, bytes) or len(raw) != 32 or purpose not in self._ch:
            return None
        with self._lock:
            mine = self._ch[purpose].get(owner)
            c = mine.pop(raw, None) if mine is not None else None
        if c is None or self.clock() >= c["until"]:
            return None
        return c["bind"]
