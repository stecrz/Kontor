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
import shutil
import ssl
import subprocess
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


def tailscale_self(binary: str) -> dict:
    """Eigener Knoten laut ``tailscale status --json``: {name, ip, cert_domains}."""
    r = subprocess.run([binary, "status", "--json"], capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError("tailscale status: %s" % (r.stderr or r.stdout).strip())
    st = json.loads(r.stdout or "{}")
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
        r = subprocess.run([binary, "status", "--json"], capture_output=True, text=True, timeout=15)
        st = json.loads(r.stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return {"gefunden": True, "verbunden": False, "fehler": str(e)[:200]}
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


def issue(binary: str, name: str, data_dir: str) -> Tuple[str, str]:
    """Holt (oder erneuert) das Zertifikat fuer ``name``; gibt (cert, key) zurueck."""
    crt, key = cert_paths(data_dir, name)
    os.makedirs(os.path.dirname(crt), mode=0o700, exist_ok=True)
    log.info("Requesting Tailscale certificate for %s", name)
    r = subprocess.run([binary, "cert", "--cert-file", crt, "--key-file", key, name], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip()
        if "not enabled" in msg.lower() or "https" in msg.lower():
            msg += "\nIn der Tailscale-Admin-Konsole (https://login.tailscale.com/admin/dns) MagicDNS und „HTTPS Certificates“ einschalten, dann erneut versuchen."
        raise RuntimeError("tailscale cert: " + msg)
    try:
        os.chmod(key, 0o600)
    except OSError:
        pass
    exp = cert_expiry(crt)
    log.info("Certificate stored in %s (valid until %s)", crt, exp.strftime("%Y-%m-%d") if exp else "?")
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
