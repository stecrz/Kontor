"""Updates aus GitHub: pruefen, laden, Programmdateien ersetzen, Dienst neu starten.

Einzige Netzverbindung von Kontor -- nur zu github.com und nur auf Wunsch
(Einstellungen: taeglich pruefen und/oder "Jetzt pruefen"). Installiert wird
nie automatisch, sondern nach Klick. Der Datenordner wird nicht angefasst.
Integritaet: HTTPS zu GitHub, feste Host-Liste, das Archiv muss kontor.py und
VERSION enthalten; alte Dateien bleiben als Sicherung (Programmordner/.alt).
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlparse
import zipfile
from typing import Dict, Optional, Tuple
from i18n import tr

log = logging.getLogger("kontor.update")
HERE = os.path.dirname(os.path.abspath(__file__))
ALLOWED_HOSTS = ("api.github.com", "codeload.github.com", "github.com", "raw.githubusercontent.com", "objects.githubusercontent.com")
TIMEOUT = 25
KEEP = {".alt", ".touchid", "web/.DS_Store"}       # nicht ueberschreiben/loeschen


def current_version() -> str:
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0"


def _vtuple(v: str) -> Tuple[int, ...]:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(x) for x in nums[:4]) or (0,)


def _get(url: str, accept: str = "application/vnd.github+json") -> bytes:
    host = urlparse(url).netloc
    if host not in ALLOWED_HOSTS or not url.startswith("https://"):
        raise ValueError(tr("s_adresse_nicht_erlaubt_s") % url)
    req = urllib.request.Request(url, headers={"User-Agent": "Kontor-Update", "Accept": accept})
    log.debug("GET %s (Accept: %s)", url, accept)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        final = r.geturl()
        if urlparse(final).netloc not in ALLOWED_HOSTS:
            raise ValueError(tr("s_umleitung_auf_fremden_host_s") % final)
        data = r.read()
        log.debug("GET %s -> %s, %d bytes%s", url, r.status, len(data), (" via " + final) if final != url else "")
        return data


def archive_url(repo: str, ref: str, kind: str = "tags") -> str:
    """ZIP-Archiv eines Tags oder Zweigs ueber github.com (leitet auf codeload.github.com um).
    Nicht die API-Adresse 'zipball' verwenden: sie antwortet auf Accept: application/octet-stream mit 415."""
    return "https://github.com/%s/archive/refs/%s/%s.zip" % (repo, kind, ref)


HEADING_RE = re.compile(r"^##\s+v?(\S+)(?:\s+\((\d{4}-\d{2}-\d{2})\))?")


def changelog_section(text: str, version: str) -> Tuple[str, str]:
    """Abschnitt '## <version> (<datum>)' aus CHANGELOG.md: (Neuerungen, Datum JJJJ-MM-TT oder '')."""
    out, on, datum = [], False, ""
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            if on:
                break
            on = m.group(1) == version.lstrip("v")
            datum = (m.group(2) or "") if on else datum
            continue
        if on:
            out.append(line)
    return "\n".join(out).strip()[:4000], datum


def changelog() -> str:
    """CHANGELOG.md der installierten Version (alle Versionen, fuer die Anzeige unter Updates)."""
    try:
        with open(os.path.join(HERE, "CHANGELOG.md"), encoding="utf-8") as f:
            return f.read()[:200000]
    except OSError:
        return ""


def installed_date() -> str:
    """Datum der installierten Version laut CHANGELOG.md im Programmordner."""
    try:
        with open(os.path.join(HERE, "CHANGELOG.md"), encoding="utf-8") as f:
            return changelog_section(f.read(), current_version())[1]
    except OSError:
        return ""


def check(repo: str) -> Dict[str, object]:
    """Neueste Version auf GitHub: VERSION im Hauptzweig (eine kleine Datei, kein API-Limit); nur wenn das
    nicht geht, Release bzw. Tag. Tags sind damit keine Voraussetzung mehr fuer ein Update."""
    cur = current_version()
    out: Dict[str, object] = {"aktuell": cur, "verfuegbar": None, "datum": "", "neuer": False, "notizen": "", "quelle": "", "fehler": None}
    log.info("Update check: installed %s, repo %s", cur, repo)
    try:
        try:
            v = _get("https://raw.githubusercontent.com/%s/main/VERSION" % repo, "text/plain").decode("utf-8").strip()
            if not re.match(r"^v?\d+(\.\d+)*$", v):
                raise ValueError(tr("s_version_im_hauptzweig_unlesbar_r") % v[:40])
            out.update({"verfuegbar": v, "quelle": "main", "zip": archive_url(repo, "main", "heads")})
            try:
                cl = _get("https://raw.githubusercontent.com/%s/main/CHANGELOG.md" % repo, "text/plain").decode("utf-8", "replace")
                out["notizen"], out["datum"] = changelog_section(cl, v)
            except Exception as e:      # Neuerungen sind nur Beiwerk
                log.debug("CHANGELOG not readable: %s", e)
        except urllib.error.HTTPError as e:
            if e.code not in (404, 403):
                raise
            log.debug("VERSION on main branch not readable (%s), checking releases/tags", e.code)
            try:
                rel = json.loads(_get("https://api.github.com/repos/%s/releases/latest" % repo).decode("utf-8"))
                tag = str(rel.get("tag_name") or "")
                out.update({"verfuegbar": tag, "notizen": (rel.get("body") or "")[:4000], "datum": str(rel.get("published_at") or "")[:10],
                            "quelle": "release", "zip": archive_url(repo, tag)})
            except urllib.error.HTTPError as e2:
                if e2.code != 404:
                    raise
                tags = json.loads(_get("https://api.github.com/repos/%s/tags" % repo).decode("utf-8"))
                if not tags:
                    raise
                tag = max((str(t["name"]) for t in tags), key=_vtuple)
                out.update({"verfuegbar": tag, "quelle": "tag", "zip": archive_url(repo, tag)})
        out["neuer"] = _vtuple(str(out["verfuegbar"])) > _vtuple(cur)
        log.info("Update check: available %s (%s)%s", out["verfuegbar"], out["quelle"], " -- newer than installed" if out["neuer"] else "")
    except urllib.error.HTTPError as e:
        out["fehler"] = tr("s_update_pruefung_nicht_moeglich_http") % (e.code, e.geturl(), e.reason)
        log.warning("Update check failed: %s", out["fehler"])
    except Exception as e:  # Netz aus, Repo privat, Ratenlimit ...
        out["fehler"] = tr("s_update_pruefung_nicht_moeglich_s") % (type(e).__name__, str(e)[:200])
        log.warning("Update check failed: %s", out["fehler"], exc_info=True)
    return out


def install_via_git(restart: bool = True) -> Optional[Dict[str, object]]:
    """Programmordner ist ein Git-Klon: 'git pull --ff-only' statt Archiv (haelt das Repo konsistent). None, wenn nicht anwendbar."""
    if not os.path.isdir(os.path.join(HERE, ".git")) or not shutil.which("git"):
        return None
    log.info("Update: program folder is a git clone, running git pull")
    try:
        r = subprocess.run(["git", "-C", HERE, "pull", "--ff-only"], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.error("Update: git pull failed: %s", e)
        return {"ok": False, "text": tr("s_git_pull_fehlgeschlagen") % e}
    log.info("Update: git pull Status %d: %s", r.returncode, (r.stdout + r.stderr).strip()[:500])
    if r.returncode != 0:
        return {"ok": False, "text": tr("s_git_pull_fehlgeschlagen") % (r.stderr or r.stdout).strip()[:300]}
    restarted = schedule_restart() if (restart and sys.platform == "darwin") else False
    return {"ok": True, "version": current_version(), "dateien": 0, "neustart": restarted,
            "text": tr("s_repo_aktualisiert") % ((r.stdout.strip().splitlines() or ["ok"])[-1][:80], tr("s_dienst_startet_neu") if restarted else "")}


def install(repo: str, zip_url: Optional[str] = None, restart: bool = True) -> Dict[str, object]:
    via_git = install_via_git(restart)
    if via_git is not None:
        return via_git
    info = check(repo) if not zip_url else {"zip": zip_url, "verfuegbar": "?"}
    url = zip_url or info.get("zip")
    if not url:
        return {"ok": False, "text": info.get("fehler") or tr("s_keine_version_gefunden")}
    log.info("Update: downloading %s", url)
    try:
        data = _get(str(url), "*/*")
    except urllib.error.HTTPError as e:
        log.error("Update: download failed: HTTP %s at %s (%s)", e.code, e.geturl(), e.reason)
        return {"ok": False, "text": tr("s_download_fehlgeschlagen_http_s_s") % (e.code, e.reason, e.geturl())}
    except Exception as e:
        log.error("Update: download failed: %s", e, exc_info=True)
        return {"ok": False, "text": tr("s_download_fehlgeschlagen") % (type(e).__name__, str(e)[:200])}
    log.info("Update: %d bytes downloaded", len(data))
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        log.error("Update: archive unreadable (not a ZIP, starts with %r)", data[:40])
        return {"ok": False, "text": tr("s_archiv_unlesbar")}
    names = zf.namelist()
    roots = {n.split("/")[0] for n in names if "/" in n}
    base = None
    for r in roots:
        if r + "/kontor.py" in names and r + "/VERSION" in names:
            base = r
            break
    if base is None:
        log.error("Update: archive without kontor.py/VERSION; roots: %s", sorted(roots)[:5])
        return {"ok": False, "text": tr("s_archiv_enthaelt_kein_kontor_kontor")}
    new_version = zf.read(base + "/VERSION").decode("utf-8").strip()
    log.info("Update: archive contains version %s (%d files), program folder %s", new_version, len(names), HERE)
    tmp = tempfile.mkdtemp(prefix="kontor-update-")
    zf.extractall(tmp)
    src = os.path.join(tmp, base)
    backup = os.path.join(HERE, ".alt")
    shutil.rmtree(backup, ignore_errors=True)
    os.makedirs(backup, exist_ok=True)
    changed = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in (".git", "tests", "__pycache__")]
        rel_root = os.path.relpath(root, src)
        for fn in files:
            rel = os.path.normpath(os.path.join(rel_root, fn))
            if rel in KEEP or fn.startswith("."):
                continue
            dst = os.path.join(HERE, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst):
                os.makedirs(os.path.dirname(os.path.join(backup, rel)), exist_ok=True)
                shutil.copy2(dst, os.path.join(backup, rel))
            shutil.copy2(os.path.join(root, fn), dst)
            if fn.endswith((".py", ".sh", ".command")):
                os.chmod(dst, 0o755)
            changed += 1
    shutil.rmtree(tmp, ignore_errors=True)
    log.info("Update to %s applied (%d files), backup in .alt", new_version, changed)
    # Touch-ID-Helfer bei Bedarf neu uebersetzen (ohne Fehler zu werfen)
    try:
        if sys.platform == "darwin":
            import auth
            log.info("Update: Touch ID helper: %s", auth.build_touchid(force=True))
    except Exception as e:
        log.warning("Update: Touch ID helper not built: %s", e)
    restarted = False
    if restart and sys.platform == "darwin":
        restarted = schedule_restart()
        log.info("Update: service restart %s", "scheduled" if restarted else "not possible")
    return {"ok": True, "version": new_version, "dateien": changed, "neustart": restarted,
            "text": tr("s_version_installiert") % (new_version, tr("s_dienst_startet_neu") if restarted else tr("s_bitte_dienst_neu_starten"))}


LABEL = "de.kontor.service"                 # launchd job of the background service


def plist_path(label: str = LABEL) -> str:
    return os.path.expanduser("~/Library/LaunchAgents/%s.plist" % label)


def schedule_restart() -> bool:
    """Dienst nach der Antwort neu starten (launchd haelt ihn am Leben)."""
    try:
        cmd = "sleep 1; launchctl kickstart -k gui/$(id -u)/%s" % LABEL
        subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False
