"""Zugangskontrolle der Web-Oberflaeche: Passwort, Sitzungen, CSRF, Touch ID.

* Passwort: PBKDF2-HMAC-SHA256, 600.000 Runden, 16 Byte Salz (nur Bordmittel).
* Sitzung: 32 Byte Zufall als HttpOnly-Cookie, Leerlauf- und Hoechstdauer,
  CSRF-Token je Sitzung (Header X-CSRF-Token) fuer jede aendernde Anfrage.
* Fehlversuche: nach 5 Fehlern 5 Minuten Sperre je Adresse.
* Touch ID: kleiner Helfer (touchid.swift, bei der Installation uebersetzt),
  der den macOS-Dialog zeigt. Nur fuer Anfragen von diesem Mac (127.0.0.1) --
  von einem anderen Geraet aus zaehlt nur das Passwort. Derselbe Helfer haelt einen
  Schluessel in der Secure Enclave, den nur Touch ID (oder das Mac-Passwort) nutzbar
  macht: damit oeffnet Touch ID auch nach einem Neustart die Daten (access.py).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple, Union
from i18n import tr

HERE = os.path.dirname(os.path.abspath(__file__))
TOUCHID_SRC = os.path.join(HERE, "touchid.swift")
# A small app bundle (no Dock icon): started through LaunchServices it comes to the front with keyboard focus, so Touch ID
# works without a click on the dialog. Its name appears in the dialog ("Kontor möchte deine Daten öffnen" -- or the demo).
TOUCHID_APP = os.path.join(HERE, ".touchid", "Kontor.app")
TOUCHID_BIN = os.path.join(TOUCHID_APP, "Contents", "MacOS", "Kontor")
TOUCHID_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>Kontor</string><key>CFBundleIdentifier</key><string>local.kontor.touchid</string>
<key>CFBundleName</key><string>Kontor</string><key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0</string><key>LSUIElement</key><true/>
</dict></plist>
"""
TOUCHID_REASON = "s_touchid_reason"          # Schluessel in web/i18n.js (Text im macOS-Fenster)
TOUCHID_REASON_DEMO = "s_touchid_reason_demo"     # ... when the sign-in opens the demo
PBKDF2_ROUNDS = 600_000
_HELPER_ARG = re.compile(r"[A-Za-z0-9+/=]{1,4096}")         # what goes to the helper besides its mode: base64 or hex Kontor made


def hash_password(password: str, salt: Optional[bytes] = None) -> Dict[str, str]:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return {"alg": "pbkdf2-sha256", "rounds": PBKDF2_ROUNDS, "salt": salt.hex(), "hash": dk.hex()}


OFFLINE_ROUNDS = 200_000


def offline_record(password: str) -> Dict[str, str]:
    """Zweiter, unabhaengiger Pruefwert fuer die Offline-Ansicht am iPhone (WebCrypto-PBKDF2 im Browser).
    Eigenes Salz, weniger Runden; wird nur an angemeldete Clients ausgeliefert und dort zwischengespeichert."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, OFFLINE_ROUNDS)
    return {"alg": "pbkdf2-sha256", "rounds": OFFLINE_ROUNDS, "salt": salt.hex(), "hash": dk.hex()}


def with_offline(rec: Dict[str, str], password: str) -> Dict[str, str]:
    """Pruefwert fuer offline ergaenzen (bei Einrichtung, Passwortwechsel und Passwort-Anmeldung)."""
    rec = dict(rec)
    rec["offline"] = offline_record(password)
    return rec


def verify_password(password: str, rec: Dict[str, str]) -> bool:
    if not rec or rec.get("alg") != "pbkdf2-sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(rec["salt"]), int(rec.get("rounds", PBKDF2_ROUNDS)))
    return hmac.compare_digest(dk.hex(), rec.get("hash", ""))


def password_ok(password: str) -> Optional[str]:
    if len(password) < 10:
        return tr("s_passwort_mindestens")
    return None


class Sessions:
    def __init__(self, idle_minutes: int = 15, max_hours: int = 12):
        self.idle = idle_minutes * 60
        self.max = max_hours * 3600
        self._s: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._fails: Dict[str, list] = {}
        self._check = threading.Lock()

    # Sitzungen
    def create(self, remote: str, via: str) -> dict:
        token = secrets.token_urlsafe(32)
        now = time.time()
        s = {"token": token, "csrf": secrets.token_urlsafe(32), "created": now, "last": now, "remote": remote, "via": via}
        with self._lock:
            self._s[token] = s
        return s

    def get(self, token: Optional[str], touch: bool = True) -> Optional[dict]:
        """The session of a token while valid. touch=False (a request the page made on its own, e.g. the status every 30 s)
        checks it without counting as activity -- so the idle lock comes after the set minutes even with the page open."""
        if not token:
            return None
        now = time.time()
        with self._lock:
            s = self._s.get(token)
            if s is None:
                return None
            if now - s["last"] > self.idle or now - s["created"] > self.max:
                self._s.pop(token, None)
                return None
            if touch:
                s["last"] = now
            return s

    def drop_all(self) -> None:
        with self._lock:
            self._s.clear()

    def active(self) -> int:
        """How many sessions are still valid (the demo ends with its last one)."""
        now = time.time()
        with self._lock:
            return sum(1 for s in self._s.values() if now - s["last"] <= self.idle and now - s["created"] <= self.max)

    def rotate(self, token: Optional[str]) -> Optional[str]:
        """The same session under a new token (after a password change: a copy of the old cookie no longer works)."""
        with self._lock:
            s = self._s.pop(token or "", None)
            if s is None:
                return None
            s["token"] = secrets.token_urlsafe(32)
            self._s[s["token"]] = s
            return s["token"]

    def drop_others(self, token: Optional[str]) -> int:
        """Ends every session but this one (after a password change: a stolen session stops working at once)."""
        with self._lock:
            gone = [k for k in self._s if k != token]
            for k in gone:
                self._s.pop(k, None)
            return len(gone)

    def set_idle(self, minutes: int) -> None:
        self.idle = max(1, int(minutes)) * 60

    # Fehlversuche
    def locked(self, remote: str) -> int:
        """Sekunden Restsperre fuer diese Adresse (0 = frei)."""
        now = time.time()
        with self._lock:
            fails = [t for t in self._fails.get(remote, []) if now - t < 300]
            self._fails[remote] = fails
            if len(fails) >= 5:
                return int(300 - (now - fails[0])) + 1
            return 0

    def check_password(self, remote: str, password: str, rec: Union[Optional[dict], Callable[[str], bool]]) -> Optional[bool]:
        """Kontor's password, checked for this address: one check at a time and every wrong one counted -- after five within
        five minutes the address waits, also when the attempts come all at once and also behind a session. None: it has to
        wait (nothing was checked). rec: the stored record, or a function that checks (it opens the data key)."""
        with self._check:
            if self.locked(remote):
                return None
            if (rec(password) if callable(rec) else bool(rec) and verify_password(password, rec)):
                self.clear_fails(remote)
                return True
            self.fail(remote)
        time.sleep(0.5)
        return False

    def fail(self, remote: str) -> None:
        with self._lock:
            self._fails.setdefault(remote, []).append(time.time())

    def clear_fails(self, remote: str) -> None:
        with self._lock:
            self._fails.pop(remote, None)


def touchid_available() -> bool:
    return os.path.exists(TOUCHID_BIN) and os.access(TOUCHID_BIN, os.X_OK)


def build_touchid(force: bool = False) -> str:
    """Touch-ID-Helfer uebersetzen (macOS, Xcode Command Line Tools). Ohne force nur, wenn er fehlt oder aelter als die Quelle ist."""
    if sys.platform != "darwin":
        return tr("s_nicht_macos")
    if not force and touchid_available() and os.path.getmtime(TOUCHID_BIN) >= os.path.getmtime(TOUCHID_SRC):
        return "ok"
    try:
        os.makedirs(os.path.dirname(TOUCHID_BIN), exist_ok=True)
        with open(os.path.join(TOUCHID_APP, "Contents", "Info.plist"), "w", encoding="utf-8") as f:
            f.write(TOUCHID_PLIST)
        r = subprocess.run(["swiftc", "-O", "-o", TOUCHID_BIN, TOUCHID_SRC], capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            os.chmod(TOUCHID_BIN, 0o755)
            subprocess.run(["codesign", "--force", "--sign", "-", TOUCHID_APP], capture_output=True, timeout=60)     # ad hoc, as a whole bundle
            return "ok"
        return tr("s_swiftc_fehler") % (r.stderr or r.stdout)[-300:]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return tr("s_swiftc_nicht_verfuegbar_s_xcode") % e


# The sign-in page's Touch ID request (service.py: one at a time, with a random id) -> the answer file of its macOS window: so
# that touchid_close can close that window when the page switches between your data and the demo while it is open.
_TID_LOCK = threading.Lock()
_TID_FILES: Dict[str, str] = {}             # ("" once closed)


def _tid_track(tid: str, out: Optional[str]) -> bool:
    """out: the answer file of the request tid from now on; None: the request is over -- True when touchid_close closed it."""
    if not tid:
        return False
    with _TID_LOCK:
        if out is not None:
            _TID_FILES[tid] = out
            return False
        return _TID_FILES.pop(tid, None) == ""


def touchid_close(tid: str) -> bool:
    """Closes the macOS window of the sign-in page's running request tid: its answer file goes, and the empty folder Kontor made
    for it (so that none is made after) -- touchid.swift sees its output gone and stops without an answer. Only that file, only
    in a folder of Kontor's own (kontor-tid-...) in the temporary folder. False when no such request runs."""
    with _TID_LOCK:
        out = _TID_FILES.get(tid) if tid else None
        if not out:
            return out == ""                     # closed already
        _TID_FILES[tid] = ""
    d = os.path.dirname(out)
    if os.path.basename(out) != "result" or not os.path.basename(d).startswith("kontor-tid-") \
            or os.path.dirname(d) != os.path.abspath(tempfile.gettempdir()):
        return False
    try:
        os.unlink(out)                           # (never follows a link)
    except FileNotFoundError:
        pass                                     # not made yet: the folder goes, so none is made after
    except OSError:
        return False
    try:
        os.rmdir(d)                              # only while empty
    except OSError:
        pass
    return True


def touchid_verify(reason: str = "", tid: str = "") -> bool:
    reason = reason or tr(TOUCHID_REASON)
    if not touchid_available():
        return False
    if sys.platform == "darwin":
        # through LaunchServices ("open"): the helper comes to the front with focus. It writes "ok <nonce>" only after a
        # confirmed Touch ID, into a file in a fresh private folder; the random nonce ties the answer to this very request.
        nonce, d = secrets.token_hex(16), tempfile.mkdtemp(prefix="kontor-tid-")
        out = os.path.join(d, "result")
        _tid_track(tid, out)
        try:
            r = subprocess.run(["open", "-n", "-W", "--stdout", out, "-a", TOUCHID_APP, "--args", reason, nonce], capture_output=True, timeout=95)
            if r.returncode == 0:
                try:
                    with open(out, encoding="utf-8") as f:
                        return ("ok " + nonce) in f.read()
                except OSError:
                    return False
        except (subprocess.TimeoutExpired, OSError):
            pass
        finally:
            closed = _tid_track(tid, None)
            shutil.rmtree(d, ignore_errors=True)
        if closed:                  # closed by the sign-in page (touchid_close): not asked again without LaunchServices
            return False
    try:                            # without LaunchServices: the helper directly (the dialog may then need a click)
        r = subprocess.run([TOUCHID_BIN, reason], capture_output=True, timeout=90)
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


class TouchIdGone(Exception):
    """The Secure Enclave of this Mac cannot use the key in the key file (it was made on another Mac)."""


def _helper_current() -> bool:
    """The helper is built from the touchid.swift beside it -- an older build (right after an update, until the service has
    built it anew) would take a mode for the text of its window."""
    try:
        return touchid_available() and os.path.getmtime(TOUCHID_BIN) >= os.path.getmtime(TOUCHID_SRC)
    except OSError:
        return False


def _helper_line(args: List[str]) -> Optional[str]:
    """Kontor's own helper without a window (a new key in the Secure Enclave, wrapping with its public key): its one line of
    output over a pipe, or None. Only fixed modes and values Kontor made itself (base64, hex)."""
    if not _helper_current() or not args or args[0] not in ("--create", "--seal") or not all(_HELPER_ARG.fullmatch(a) for a in args[1:]):
        return None
    try:
        r = subprocess.run([TOUCHID_BIN] + args, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def touchid_new_key() -> Optional[Tuple[str, str]]:
    """A new key in this Mac's Secure Enclave, usable only with Touch ID or the Mac's password (making it asks nothing):
    (its handle, its public key), both base64 -- the handle is of no use on any other Mac. None where the Mac cannot."""
    out = (_helper_line(["--create"]) or "").split()
    return (out[0], out[1]) if len(out) == 2 and all(_HELPER_ARG.fullmatch(x) for x in out) else None


def touchid_seal(pub: str, salt: str) -> Optional[Tuple[str, bytes]]:
    """A key to wrap the data key with, that only the Secure Enclave's key (Touch ID) can make again: (the public half of a
    fresh key pair, base64; the 32-byte key). Asks nothing."""
    out = (_helper_line(["--seal", pub, salt]) or "").split()
    if len(out) != 2 or not _HELPER_ARG.fullmatch(out[0]) or not re.fullmatch(r"[0-9a-f]{64}", out[1]):
        return None
    return out[0], bytes.fromhex(out[1])


# The helper's answer of --unseal goes through a file (LaunchServices gives it its output that way): the key in it is wrapped
# for this request only -- X25519 between a key pair made here (its private half never leaves this process) and one the helper
# makes, HKDF-SHA256 to a one-time pad and an HMAC key. What lands in the file is of no use to anyone reading it.
_P25519 = 2 ** 255 - 19
_TRANSPORT_INFO = b"kontor-touchid-transport-v1"


def _x25519(k: bytes, u: bytes) -> bytes:
    """X25519 (RFC 7748): scalar k times the point with u-coordinate u, both 32 bytes little-endian."""
    kb = bytearray(k)
    kb[0] &= 248
    kb[31] &= 127
    kb[31] |= 64
    n, x1 = int.from_bytes(bytes(kb), "little"), int.from_bytes(u, "little") & ((1 << 255) - 1)
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in range(254, -1, -1):
        bit = (n >> t) & 1
        swap ^= bit
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = bit
        a, b, c, d = x2 + z2, x2 - z2, x3 + z3, x3 - z3
        aa, bb = a * a % _P25519, b * b % _P25519
        e, da, cb = aa - bb, d * a % _P25519, c * b % _P25519
        x3, z3 = (da + cb) ** 2 % _P25519, x1 * (da - cb) ** 2 % _P25519
        x2, z2 = aa * bb % _P25519, e * (aa + 121665 * e) % _P25519
    if swap:
        x2, z2 = x3, z3
    return (x2 * pow(z2, _P25519 - 2, _P25519) % _P25519).to_bytes(32, "little")


def _hkdf(ikm: bytes, salt: bytes, info: bytes, n: int) -> bytes:
    """HKDF-SHA256 (RFC 5869)."""
    prk, out, t, i = hmac.new(salt, ikm, hashlib.sha256).digest(), b"", b"", 1
    while len(out) < n:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        out, i = out + t, i + 1
    return out[:n]


def _unwrap_transport(mine: bytes, nonce: str, line: str) -> Optional[bytes]:
    """The key out of the helper's answer "ok <nonce> <its public key> <wrapped key> <tag>" -- None unless it checks out."""
    m = re.fullmatch(r"ok " + nonce + r" ([A-Za-z0-9+/=]{44}) ([0-9a-f]{64}) ([0-9a-f]{64})", line.strip())
    if not m:
        return None
    try:
        theirs = base64.b64decode(m.group(1), validate=True)
    except (ValueError, TypeError):
        return None
    shared = _x25519(mine, theirs) if len(theirs) == 32 else bytes(32)
    if shared == bytes(32):
        return None
    okm = _hkdf(shared, nonce.encode("ascii"), _TRANSPORT_INFO, 64)
    ct = bytes.fromhex(m.group(2))
    if not hmac.compare_digest(hmac.new(okm[32:], ct, hashlib.sha256).hexdigest(), m.group(3)):
        return None
    return bytes(a ^ b for a, b in zip(ct, okm[:32]))


def touchid_unseal(se: str, eph: str, salt: str, reason: str = "", tid: str = "") -> Optional[bytes]:
    """The key touchid_seal made, again -- only after Touch ID (or the Mac's password) in the macOS window. None when not
    confirmed; TouchIdGone when this Mac's Secure Enclave cannot use the key. As touchid_verify: through LaunchServices with
    focus, the answer in a fresh private folder, tied to this request by a random nonce -- and wrapped for it (above)."""
    reason = reason or tr(TOUCHID_REASON)
    if sys.platform != "darwin" or not _helper_current() or not all(_HELPER_ARG.fullmatch(a) for a in (se, eph, salt)):
        return None
    mine = secrets.token_bytes(32)
    pub = base64.b64encode(_x25519(mine, (9).to_bytes(32, "little"))).decode("ascii")
    nonce, d = secrets.token_hex(16), tempfile.mkdtemp(prefix="kontor-tid-")
    out = os.path.join(d, "result")
    _tid_track(tid, out)
    try:
        r = subprocess.run(["open", "-n", "-W", "--stdout", out, "-a", TOUCHID_APP, "--args", "--unseal", reason, nonce, se, eph, salt, pub],
                           capture_output=True, timeout=95)
        if r.returncode != 0:
            return None
        with open(out, encoding="utf-8") as f:
            text = f.read()
        if ("gone " + nonce) in text:
            raise TouchIdGone()
        for line in text.splitlines():
            key = _unwrap_transport(mine, nonce, line)
            if key is not None:
                return key
        return None
    except (subprocess.TimeoutExpired, OSError):
        return None
    finally:
        _tid_track(tid, None)
        shutil.rmtree(d, ignore_errors=True)


def is_loopback(remote: str) -> bool:
    return remote in ("127.0.0.1", "::1", "localhost")
