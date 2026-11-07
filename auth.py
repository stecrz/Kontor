"""Zugangskontrolle der Web-Oberflaeche: Passwort, Sitzungen, CSRF, Touch ID.

* Passwort: PBKDF2-HMAC-SHA256, 600.000 Runden, 16 Byte Salz (nur Bordmittel).
* Sitzung: 32 Byte Zufall als HttpOnly-Cookie, Leerlauf- und Hoechstdauer,
  CSRF-Token je Sitzung (Header X-CSRF-Token) fuer jede aendernde Anfrage.
* Fehlversuche: nach 5 Fehlern 5 Minuten Sperre je Adresse.
* Touch ID: kleiner Helfer (touchid.swift, bei der Installation uebersetzt),
  der den macOS-Dialog zeigt. Nur fuer Anfragen von diesem Mac (127.0.0.1) --
  von einem anderen Geraet aus zaehlt nur das Passwort.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import subprocess
import sys
import threading
import time
from typing import Dict, Optional
from i18n import tr

HERE = os.path.dirname(os.path.abspath(__file__))
TOUCHID_SRC = os.path.join(HERE, "touchid.swift")
# Der Dateiname erscheint im macOS-Dialog ("Kontor möchte die Finanzübersicht entsperren")
TOUCHID_BIN = os.path.join(HERE, ".touchid", "Kontor")
TOUCHID_REASON = "s_touchid_reason"          # Schluessel in web/i18n.js (Text im macOS-Fenster)
PBKDF2_ROUNDS = 600_000


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
        return "Mindestens 10 Zeichen."
    return None


class Sessions:
    def __init__(self, idle_minutes: int = 15, max_hours: int = 12):
        self.idle = idle_minutes * 60
        self.max = max_hours * 3600
        self._s: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._fails: Dict[str, list] = {}

    # Sitzungen
    def create(self, remote: str, via: str) -> dict:
        token = secrets.token_urlsafe(32)
        now = time.time()
        s = {"token": token, "csrf": secrets.token_urlsafe(32), "created": now, "last": now, "remote": remote, "via": via}
        with self._lock:
            self._s[token] = s
        return s

    def get(self, token: Optional[str]) -> Optional[dict]:
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
            s["last"] = now
            return s

    def drop(self, token: Optional[str]) -> None:
        with self._lock:
            self._s.pop(token or "", None)

    def drop_all(self) -> None:
        with self._lock:
            self._s.clear()

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
        r = subprocess.run(["swiftc", "-O", "-o", TOUCHID_BIN, TOUCHID_SRC], capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            os.chmod(TOUCHID_BIN, 0o755)
            return "ok"
        return tr("s_swiftc_fehler") % (r.stderr or r.stdout)[-300:]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return tr("s_swiftc_nicht_verfuegbar_s_xcode") % e


def touchid_verify(reason: str = "") -> bool:
    reason = reason or tr(TOUCHID_REASON)
    if not touchid_available():
        return False
    try:
        r = subprocess.run([TOUCHID_BIN, reason], capture_output=True, timeout=90)
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def is_loopback(remote: str) -> bool:
    return remote in ("127.0.0.1", "::1", "localhost")
