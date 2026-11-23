"""Kontor: TLS-Zertifikat ueber Tailscale (fuer https, Offline-Ansicht am iPhone).

Service Worker (Offline-Kopie der Oberflaeche) laufen nur in einem sicheren Kontext, also ueber https
oder 127.0.0.1. Tailscale stellt fuer jeden Rechner ein echtes Let's-Encrypt-Zertifikat auf den
MagicDNS-Namen aus (Admin-Konsole: DNS -> HTTPS Certificates aktivieren). Dieses Modul holt das
Zertifikat ueber ``tailscale cert``, legt es im Datenordner ab, traegt es in die Konfiguration ein
und erneuert es, bevor es ablaeuft.
"""
from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Tuple, Union
from urllib.parse import quote
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
            log.debug("Tailscale CLI via launchctl: exit %s", r2.returncode)
        except (OSError, subprocess.TimeoutExpired) as e:
            log.debug("Tailscale CLI via launchctl failed: %s", e)
    return r


# -- Local interface of the Tailscale app (macOS) ----------------------------------------------------------------------
# The Mac apps of Tailscale answer on 127.0.0.1 (the same "LocalAPI" their own command line tool uses). Port and a
# per-session token come from a file only the logged-in user can read ("sameuserproof"). Kontor reads them for each
# request, keeps nothing and logs neither token nor port. This works even when the bundled CLI refuses to run from a
# background service ("The Tailscale GUI failed to start").
MACSYS_DIR = "/Library/Tailscale"


def parse_proof(text: str) -> Optional[Tuple[int, str]]:
    """(port, token) from a file name like ".../sameuserproof-12345-0123456789abcdef0000" (made-up example)."""
    m = re.search(r"sameuserproof-(\d+)-([^\s/]+)", text or "")
    return (int(m.group(1)), m.group(2)) if m else None


def localapi_endpoint() -> Optional[Tuple[int, str]]:
    if sys.platform != "darwin":
        return None
    try:                                                  # Standalone variant (download from tailscale.com)
        port = os.readlink(os.path.join(MACSYS_DIR, "ipnport"))
        with open(os.path.join(MACSYS_DIR, "sameuserproof-" + port)) as f:
            return int(port), f.read().strip()
    except (OSError, ValueError):
        pass
    lsof = shutil.which("lsof") or "/usr/sbin/lsof"
    try:                                                  # App Store variant: the extension keeps the proof file open
        pids = subprocess.run(["pgrep", "-x", "IPNExtension"], capture_output=True, text=True, timeout=5).stdout.split()
        sel = ["-p", ",".join(pids)] if pids else ["-c", "IPNExtension"]   # only that process: much faster than scanning all
        out = subprocess.run([lsof, "-n", "-P", "-a"] + sel + ["-F", "n"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_proof(out)


def localapi(path: str, timeout: int = 15) -> bytes:
    """GET ``path`` on the Tailscale app's local interface; raises RuntimeError (with Tailscale's message) on failure."""
    ep = localapi_endpoint()
    if not ep:
        raise RuntimeError("Tailscale local interface not found")
    port, token = ep
    auth = base64.b64encode((":" + token).encode()).decode()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path, headers={"Host": "local-tailscaled.sock", "Sec-Tailscale": "localapi", "Authorization": "Basic " + auth})
        res = conn.getresponse()
        body = res.read()
    except (OSError, http.client.HTTPException) as e:
        raise RuntimeError("Tailscale local interface: %s" % e)
    finally:
        conn.close()
    if res.status != 200:
        raise RuntimeError(("Tailscale %s: %s" % (res.status, body[:300].decode("utf-8", "replace").strip()))[:300])
    return body


def access_check(port: int) -> dict:
    """What Tailscale lets in on this Mac: the filter rules Tailscale applies to incoming connections (from the app's local
    interface). zustand: "abgesichert" (only Kontor's port), "offen" (more ports, "alle" = every port), "gesperrt" (not even
    Kontor's port) or "unbekannt" (could not be read)."""
    data, why = None, ""
    for path in ("/localapi/v0/debug-packet-filter-rules", "/localapi/v0/debug-packet-filter-matches"):
        try:
            data = json.loads(localapi(path, 10).decode("utf-8"))
            break
        except (RuntimeError, ValueError) as e:
            why = str(e)
    if not isinstance(data, list):
        return {"state": "unknown", "error": why[:200], "port": port}
    ranges = []
    for r in data:
        for d in (r.get("DstPorts") or r.get("Dsts") or []) if isinstance(r, dict) else []:
            p = d.get("Ports") or {}
            ranges.append((int(p.get("First", 0)), int(p.get("Last", 65535))))
    kontor = any(a <= port <= b for a, b in ranges)
    other = sorted({(a, b) for a, b in ranges if not a == b == port})
    info = {"all": any(a <= 1 and b >= 65535 for a, b in other), "ports": [list(x) for x in other[:6]], "port": port}
    if not kontor:
        return dict(info, state="locked")
    return dict(info, state="open" if other else "secured")


# -- How this Mac is reachable beyond your devices: read only, Kontor changes nothing in Tailscale ------------------------
# Two fixed questions, each first to the app's local interface, then to Tailscale's own program: is Tailnet Lock on (new
# devices only with a signature of one of yours -- Tailscale itself cannot add one), and does "tailscale serve" (or Funnel,
# the same into the internet) pass something on to Kontor's port?
_ASK = {"lock": ("/localapi/v0/tka/status", ("lock", "status", "--json")),
        "serve": ("/localapi/v0/serve-config", ("serve", "status", "--json"))}


OFF = "off"                 # ask(): Tailscale is not on this Mac, or its service does not run -- nothing it could pass on
# what Tailscale's own program says when its service does not run (it could not reach it at all) -- never a refused access
_NOT_RUNNING = re.compile(r"(?i)failed to connect to local tailscale|doesn'?t appear to be running")


def ask(what: str) -> Union[dict, str, None]:
    """One of the fixed questions of _ASK, read only: Tailscale's answer as a dict; OFF when Tailscale is not on this Mac or
    its service does not run (then it passes nothing on); None when it runs but gives no answer (the last known state holds)."""
    if what not in _ASK:
        return None
    path, args = _ASK[what]
    reached = True
    try:
        got = json.loads(localapi(path, 10).decode("utf-8") or "{}")
        if got is None and what == "serve":
            return {}                                     # nothing served (or signed out): Tailscale answers null
        if isinstance(got, dict):
            return got
    except RuntimeError as e:
        reached = "not found" not in str(e)              # its app's local interface is not there (the app does not run)
    except ValueError:
        pass
    binary = find_tailscale()
    if not binary:
        return None if reached else OFF                 # neither its app nor its program on this Mac
    try:
        r = run(binary, list(args), 15)
        got = json.loads(r.stdout or "") if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None
    except ValueError:
        got = None
    out = (r.stdout or "") + " " + (r.stderr or "")
    if r.returncode != 0:
        return OFF if _NOT_RUNNING.search(out) and "denied" not in out.lower() else None
    if what == "serve" and got is None:
        return {}                                         # nothing served: "null" (or an empty answer)
    return got if isinstance(got, dict) else None


# a target that is this Mac itself: its own addresses (127.0.0.1, ::1, localhost, every address of the Mac) -- and the names
# and addresses of this Mac given by the caller (its address in the Tailscale network, its name there, its host name)
_HERE = re.compile(r"127(?:\.\d{1,3}){3}|::1|::ffff:127(?:\.\d{1,3}){3}|0\.0\.0\.0|::|localhost|[a-z0-9-]+\.localhost")


def _target(target: object) -> Optional[Tuple[str, int]]:
    """(host, port) a serve handler passes on to ("http://127.0.0.1:8765", "localhost:8765", "[::1]:8765"); a port alone
    ("8765") is this Mac: host ""; None without a port."""
    t = re.sub(r"^[a-z][a-z0-9+.-]*://", "", str(target or "").strip().lower()).split("/", 1)[0]
    m = re.fullmatch(r"(\[[0-9a-f:.]+\]|[a-z0-9._-]+):(\d{1,5})|(\d{1,5})", t)
    if not m:
        return None
    return ("", int(m.group(3))) if m.group(3) else (m.group(1).strip("[]").rstrip("."), int(m.group(2)))


def _this_mac(host: str, own: frozenset) -> bool:
    if host == "" or _HERE.fullmatch(host) or host in own:
        return True
    try:                                                   # any spelling of 127.x, ::1, 0.0.0.0/:: -- also IPv4 written in IPv6
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    inner = getattr(ip, "ipv4_mapped", None) or ip
    return bool(ip.is_loopback or ip.is_unspecified or inner.is_loopback or inner.is_unspecified)


def _targets(node: object, depth: int = 0) -> list:
    """Every place a serve configuration passes connections on to (Proxy of a web handler, TCPForward), however nested."""
    out: list = []
    if depth > 8:
        return out
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("Proxy", "TCPForward") and isinstance(v, str):
                out.append(v)
            else:
                out += _targets(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            out += _targets(v, depth + 1)
    return out


def _funnel(node: object, depth: int = 0) -> bool:
    if depth > 8:
        return False
    if isinstance(node, dict):
        return any((k == "AllowFunnel" and isinstance(v, dict) and any(x is True for x in v.values())) or _funnel(v, depth + 1) for k, v in node.items())
    return isinstance(node, list) and any(_funnel(v, depth + 1) for v in node)


def exposure(port: int, own: Iterable[str] = ()) -> dict:
    """lock: True/False/None (unknown); serve: "funnel" (Kontor's port on this Mac reachable from the internet), "serve" (passed
    on within your network -- each request then seems to come from this Mac itself), "none", "off" (Tailscale is not on this
    Mac or does not run) or "unknown" (it runs but gave no answer). Only targets on this Mac count: own are its names and
    addresses beyond 127.0.0.1/localhost (another device's address with the same port is not Kontor)."""
    serve = ask("serve")
    lock = ask("lock") if serve != OFF else None
    out = {"lock": (lock.get("Enabled") is True) if isinstance(lock, dict) and isinstance(lock.get("Enabled"), bool) else None, "port": port}
    if serve == OFF:
        return dict(out, serve="off")
    if not isinstance(serve, dict):
        return dict(out, serve="unknown")
    mine = frozenset(str(x).strip().strip("[]").rstrip(".").lower() for x in own if x)
    if not any(t is not None and t[1] == port and _this_mac(t[0], mine) for t in map(_target, _targets(serve))):
        return dict(out, serve="none")
    return dict(out, serve="funnel" if _funnel(serve) else "serve")


def status_json(binary: Optional[str], timeout: int = 15) -> dict:
    """Tailscale status as a dict: first via the app's local interface, then ``tailscale status --json``. Raises
    RuntimeError with Tailscale's own message if neither answers."""
    first = None
    try:
        st = json.loads(localapi("/localapi/v0/status", timeout).decode("utf-8"))
        if isinstance(st, dict):
            return st
    except (RuntimeError, ValueError) as e:
        first = str(e)
    if not binary:
        raise RuntimeError(first or "Tailscale not found")
    r = run(binary, ["status", "--json"], timeout)
    try:
        st = json.loads(r.stdout or "")
        if isinstance(st, dict):
            return st
    except ValueError:
        pass
    msg = ((r.stderr or "") + " " + (r.stdout or "")).strip().splitlines()
    cli = (msg[0] if msg else "exit %s" % r.returncode)[:200]
    raise RuntimeError(cli if not first or "not found" in first else "%s · CLI: %s" % (first[:200], cli))


def tailscale_self(binary: Optional[str]) -> dict:
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
    if not binary and not localapi_endpoint():
        return {"found": False}
    try:
        st = status_json(binary)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
        log.warning("Tailscale status unreadable: %s", e)
        return {"found": True, "connected": False, "state": "", "error": str(e)[:200]}
    if st.get("BackendState") != "Running":
        log.info("Tailscale state: %s", st.get("BackendState") or "?")
    me = st.get("Self") or {}
    tn = st.get("CurrentTailnet") or {}
    user = (st.get("User") or {}).get(str(me.get("UserID")), {}) if me.get("UserID") is not None else {}
    peers = [{"name": p.get("HostName") or (p.get("DNSName") or "").split(".")[0], "os": p.get("OS") or "", "online": bool(p.get("Online"))}
             for p in (st.get("Peer") or {}).values()]
    return {"found": True, "connected": st.get("BackendState") == "Running", "state": st.get("BackendState") or "",
            "name": (me.get("DNSName") or "").rstrip("."), "ip": next((ip for ip in (me.get("TailscaleIPs") or []) if ":" not in ip), ""),
            "tailnet": tn.get("Name") or "", "magicdns": bool(tn.get("MagicDNSEnabled", bool(me.get("DNSName")))),
            "https": bool(st.get("CertDomains")), "account": user.get("LoginName") or "",
            "devices": sorted(peers, key=lambda x: (not x["online"], x["name"].lower()))}


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


def issue(binary: Optional[str], name: str, data_dir: str) -> Tuple[str, str]:
    """Fetch (or renew) the certificate for ``name``; returns (cert, key). First via the app's local interface, then the
    CLI (certificate and key to stdout, "-"). Kontor writes the files itself: the Mac App Store variant of Tailscale runs
    sandboxed and may not write into Kontor's data folder."""
    crt, key = cert_paths(data_dir, name)
    os.makedirs(os.path.dirname(crt), mode=0o700, exist_ok=True)
    log.info("Requesting Tailscale certificate")
    blocks, why = [], ""
    try:                                                  # app's local interface: private key, then the certificate chain
        blocks = _pem_blocks(localapi("/localapi/v0/cert/%s?type=pair" % quote(name, safe=""), 180).decode("utf-8", "replace"))
    except RuntimeError as e:
        why = str(e)
    if [b for t, b in blocks if t == "CERTIFICATE"] and [b for t, b in blocks if "PRIVATE KEY" in t]:
        r = subprocess.CompletedProcess([], 0, "", "")
    elif binary:
        r = run(binary, ["cert", "--cert-file", "-", "--key-file", "-", name], 180)
        blocks = _pem_blocks(r.stdout) if r.returncode == 0 else []
    else:
        r = subprocess.CompletedProcess([], 1, "", why)
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
    if not binary and not localapi_endpoint():
        raise RuntimeError(tr("s_tailscale_nicht_gefunden"))
    me = tailscale_self(binary)
    crt, key = issue(binary, me["name"], data_dir)
    ui = dict(config.get("ui") or {})
    ui["tls_cert"], ui["tls_key"] = crt, key
    if not ui.get("bind") or ui.get("bind") == "127.0.0.1":
        ui["bind"] = me["ip"]
    port = int(ui.get("port") or 8765)
    exp = cert_expiry(crt)
    return {"ui": ui, "url": "https://%s:%d/" % (me["name"], port), "name": me["name"], "ip": me["ip"],
            "valid_until": exp.isoformat() if exp else None}


def renew_if_due(config: dict, data_dir: str, days: int = RENEW_DAYS) -> bool:
    """Erneuert ein von Kontor verwaltetes Tailscale-Zertifikat, wenn es in weniger als ``days`` Tagen ablaeuft."""
    ui = config.get("ui") or {}
    crt = ui.get("tls_cert") or ""
    if not crt or not crt.startswith(os.path.join(data_dir, "tls") + os.sep):
        return False
    exp = cert_expiry(crt)
    if exp and exp - datetime.now(timezone.utc) > timedelta(days=days):
        return False
    binary = find_tailscale()
    if not binary and not localapi_endpoint():
        log.warning("TLS certificate expires (%s), but Tailscale is missing", exp)
        return False
    name = os.path.basename(crt)[:-4]
    try:
        issue(binary, name, data_dir)
        return True
    except Exception as e:
        log.warning("Certificate could not be renewed: %s", e)
        return False
