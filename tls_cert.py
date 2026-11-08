"""Kontor: TLS-Zertifikat ueber Tailscale (fuer https, Offline-Ansicht am iPhone).

Service Worker (Offline-Kopie der Oberflaeche) laufen nur in einem sicheren Kontext, also ueber https
oder 127.0.0.1. Tailscale stellt fuer jeden Rechner ein echtes Let's-Encrypt-Zertifikat auf den
MagicDNS-Namen aus (Admin-Konsole: DNS -> HTTPS Certificates aktivieren). Dieses Modul holt das
Zertifikat ueber ``tailscale cert``, legt es im Datenordner ab, traegt es in die Konfiguration ein
und erneuert es, bevor es ablaeuft.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from i18n import tr

log = logging.getLogger("kontor.tls")

CANDIDATES = ["/Applications/Tailscale.app/Contents/MacOS/Tailscale", "/usr/local/bin/tailscale", "/opt/homebrew/bin/tailscale"]
RENEW_DAYS = 21


def find_tailscale() -> Optional[str]:
    for p in CANDIDATES:
        if os.path.exists(p):
            return p
    return shutil.which("tailscale")


def run(binary: str, args: list, timeout: int) -> subprocess.CompletedProcess:
    """Run the Tailscale CLI. On macOS the CLI inside Tailscale.app sometimes answers "The Tailscale GUI failed to start"
    when it is not started in the user's GUI session (e.g. from a launchd service); then retry via ``launchctl asuser``."""
    r = subprocess.run([binary] + list(args), capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or "") + (r.stderr or "")
    if sys.platform == "darwin" and os.path.exists("/bin/launchctl") and (r.returncode != 0 or "GUI failed" in out):
        try:
            r2 = subprocess.run(["/bin/launchctl", "asuser", str(os.getuid()), binary] + list(args), capture_output=True, text=True, timeout=timeout)
            if r2.returncode == 0 and "GUI failed" not in (r2.stdout or ""):
                return r2
        except (OSError, subprocess.TimeoutExpired):
            pass
    return r


def status_json(binary: str, timeout: int = 15) -> dict:
    """``tailscale status --json`` as a dict; raises RuntimeError with the CLI's own message if there is no JSON."""
    r = run(binary, ["status", "--json"], timeout)
    try:
        st = json.loads(r.stdout or "")
        if isinstance(st, dict):
            return st
    except ValueError:
        pass
    msg = ((r.stderr or "") + " " + (r.stdout or "")).strip().splitlines()
    raise RuntimeError((msg[0] if msg else "exit %s" % r.returncode)[:200])


def tailscale_self(binary: str) -> dict:
    """Own node according to ``tailscale status --json``: {name, ip, cert_domains}."""
    st = status_json(binary, 20)
    me = st.get("Self") or {}
    name = (me.get("DNSName") or "").rstrip(".")
    ips = [ip for ip in (me.get("TailscaleIPs") or []) if ":" not in ip]
    if not name or not ips:
        raise RuntimeError(tr("s_tailscale_ist_nicht_verbunden_kein"))
    return {"name": name, "ip": ips[0], "cert_domains": st.get("CertDomains") or [], "backend": st.get("BackendState")}


def status() -> dict:
    """Zustand von Tailscale auf diesem Mac fuer die Einrichtung des Zugriffs vom iPhone: gefunden, verbunden, eigener Name
    (MagicDNS) und Adresse, Tailnet, Konto, ob HTTPS-Zertifikate eingeschaltet sind, und die anderen Geraete im Tailnet
    (die Kontor erreichen koennten). Nichts davon wird gespeichert oder protokolliert."""
    binary = find_tailscale()
    if not binary:
        return {"gefunden": False}
    try:
        st = status_json(binary)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
        log.warning("Tailscale status unreadable: %s", e)
        return {"gefunden": True, "verbunden": False, "zustand": "", "fehler": str(e)[:200]}
    if st.get("BackendState") != "Running":
        log.info("Tailscale state: %s", st.get("BackendState") or "?")
    me = st.get("Self") or {}
    tn = st.get("CurrentTailnet") or {}
    user = (st.get("User") or {}).get(str(me.get("UserID")), {}) if me.get("UserID") is not None else {}
    peers = [{"name": p.get("HostName") or (p.get("DNSName") or "").split(".")[0], "os": p.get("OS") or "", "online": bool(p.get("Online"))}
             for p in (st.get("Peer") or {}).values()]
    return {"gefunden": True, "verbunden": st.get("BackendState") == "Running", "zustand": st.get("BackendState") or "",
            "name": (me.get("DNSName") or "").rstrip("."), "ip": next((ip for ip in (me.get("TailscaleIPs") or []) if ":" not in ip), ""),
            "tailnet": tn.get("Name") or "", "magicdns": bool(tn.get("MagicDNSEnabled", bool(me.get("DNSName")))),
            "https": bool(st.get("CertDomains")), "konto": user.get("LoginName") or "",
            "geraete": sorted(peers, key=lambda x: (not x["online"], x["name"].lower()))}


def cert_expiry(cert_path: str) -> Optional[datetime]:
    try:
        info = ssl._ssl._test_decode_cert(cert_path)  # type: ignore[attr-defined]
        return datetime.strptime(info["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        r = subprocess.run(["openssl", "x509", "-enddate", "-noout", "-in", cert_path], capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and "=" in r.stdout:
            return datetime.strptime(r.stdout.strip().split("=", 1)[1], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def cert_paths(data_dir: str, name: str) -> Tuple[str, str]:
    d = os.path.join(data_dir, "tls")
    return os.path.join(d, name + ".crt"), os.path.join(d, name + ".key")


def _pem_blocks(text: str) -> list:
    """(type, block) for every PEM block in ``text``."""
    out = []
    for m in re.finditer(r"-----BEGIN ([A-Z ]+)-----.*?-----END \1-----", text or "", re.S):
        out.append((m.group(1), m.group(0)))
    return out


def _write_private(path: str, data: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(data)
    os.chmod(path, 0o600)


def issue(binary: str, name: str, data_dir: str) -> Tuple[str, str]:
    """Fetch (or renew) the certificate for ``name``; returns (cert, key).
    The CLI prints certificate and key to stdout ("-") and Kontor writes the files itself: the Mac App Store variant of
    Tailscale runs sandboxed and may not write into Kontor's data folder."""
    crt, key = cert_paths(data_dir, name)
    os.makedirs(os.path.dirname(crt), mode=0o700, exist_ok=True)
    log.info("Requesting Tailscale certificate")
    r = run(binary, ["cert", "--cert-file", "-", "--key-file", "-", name], 180)
    blocks = _pem_blocks(r.stdout) if r.returncode == 0 else []
    certs = [b for t, b in blocks if t == "CERTIFICATE"]
    keys = [b for t, b in blocks if "PRIVATE KEY" in t]
    if not (certs and keys):
        if r.returncode == 0:                            # older CLI without "-": write the files directly
            r = run(binary, ["cert", "--cert-file", crt, "--key-file", key, name], 180)
        if r.returncode != 0:
            msg = ((r.stderr or "") + " " + (r.stdout or "")).strip()
            if "not enabled" in msg.lower() or "https" in msg.lower():
                msg += "\n" + tr("s_tailscale_https_einschalten")
            raise RuntimeError("tailscale cert: " + msg[:500])
    else:
        _write_private(crt, "\n".join(certs) + "\n")
        _write_private(key, keys[0] + "\n")
    try:
        os.chmod(key, 0o600)
    except OSError:
        pass
    exp = cert_expiry(crt)
    log.info("Certificate stored (valid until %s)", exp.strftime("%Y-%m-%d") if exp else "?")
    return crt, key


def setup(config: dict, data_dir: str) -> dict:
    """Richtet https ueber Tailscale ein und gibt die anzupassenden Konfigurationswerte zurueck.

    Rueckgabe: {"oberflaeche": {...}, "url": "https://name:port/", "name": ..., "ip": ..., "gueltig_bis": ...}
    """
    binary = find_tailscale()
    if not binary:
        raise RuntimeError(tr("s_tailscale_nicht_gefunden"))
    me = tailscale_self(binary)
    crt, key = issue(binary, me["name"], data_dir)
    ui = dict(config.get("oberflaeche") or {})
    ui["tls_cert"], ui["tls_key"] = crt, key
    if not ui.get("bind") or ui.get("bind") == "127.0.0.1":
        ui["bind"] = me["ip"]
    port = int(ui.get("port") or 8765)
    exp = cert_expiry(crt)
    return {"oberflaeche": ui, "url": "https://%s:%d/" % (me["name"], port), "name": me["name"], "ip": me["ip"],
            "gueltig_bis": exp.isoformat() if exp else None}


def renew_if_due(config: dict, data_dir: str, days: int = RENEW_DAYS) -> bool:
    """Erneuert ein von Kontor verwaltetes Tailscale-Zertifikat, wenn es in weniger als ``days`` Tagen ablaeuft."""
    ui = config.get("oberflaeche") or {}
    crt = ui.get("tls_cert") or ""
    if not crt or not crt.startswith(os.path.join(data_dir, "tls") + os.sep):
        return False
    exp = cert_expiry(crt)
    if exp and exp - datetime.now(timezone.utc) > timedelta(days=days):
        return False
    binary = find_tailscale()
    if not binary:
        log.warning("TLS certificate expires (%s), but Tailscale is missing", exp)
        return False
    name = os.path.basename(crt)[:-4]
    try:
        issue(binary, name, data_dir)
        return True
    except Exception as e:
        log.warning("Certificate could not be renewed: %s", e)
        return False
