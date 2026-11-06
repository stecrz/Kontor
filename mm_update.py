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

log = logging.getLogger("kontor.update")
HERE = os.path.dirname(os.path.abspath(__file__))
ALLOWED_HOSTS = ("api.github.com", "codeload.github.com", "github.com", "raw.githubusercontent.com", "objects.githubusercontent.com")
TIMEOUT = 25
KEEP = {".alt", "mm_touchid", "web/.DS_Store"}       # nicht ueberschreiben/loeschen


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
        raise ValueError("Adresse nicht erlaubt: %s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": "Kontor-Update", "Accept": accept})
    log.debug("GET %s (Accept: %s)", url, accept)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        final = r.geturl()
        if urlparse(final).netloc not in ALLOWED_HOSTS:
            raise ValueError("Umleitung auf fremden Host: %s" % final)
        data = r.read()
        log.debug("GET %s -> %s, %d Bytes%s", url, r.status, len(data), (" via " + final) if final != url else "")
        return data


def archive_url(repo: str, ref: str, kind: str = "tags") -> str:
    """ZIP-Archiv eines Tags oder Zweigs ueber github.com (leitet auf codeload.github.com um).
    Nicht die API-Adresse 'zipball' verwenden: sie antwortet auf Accept: application/octet-stream mit 415."""
    return "https://github.com/%s/archive/refs/%s/%s.zip" % (repo, kind, ref)


def check(repo: str) -> Dict[str, object]:
    """Neueste Version auf GitHub (Release, sonst Tag, sonst VERSION im Hauptzweig)."""
    cur = current_version()
    out: Dict[str, object] = {"aktuell": cur, "verfuegbar": None, "neuer": False, "notizen": "", "quelle": "", "fehler": None}
    log.info("Update-Prüfung: installiert %s, Repo %s", cur, repo)
    try:
        try:
            rel = json.loads(_get("https://api.github.com/repos/%s/releases/latest" % repo).decode("utf-8"))
            tag = str(rel.get("tag_name") or "")
            out.update({"verfuegbar": tag, "notizen": (rel.get("body") or "")[:4000], "quelle": "release", "zip": archive_url(repo, tag)})
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            log.debug("Kein Release (404), prüfe Tags")
            tags = json.loads(_get("https://api.github.com/repos/%s/tags" % repo).decode("utf-8"))
            if tags:
                tag = str(tags[0]["name"])
                out.update({"verfuegbar": tag, "quelle": "tag", "zip": archive_url(repo, tag)})
            else:
                log.debug("Keine Tags, lese VERSION aus main")
                v = _get("https://raw.githubusercontent.com/%s/main/VERSION" % repo, "text/plain").decode("utf-8").strip()
                out.update({"verfuegbar": v, "quelle": "main", "zip": archive_url(repo, "main", "heads")})
        out["neuer"] = _vtuple(str(out["verfuegbar"])) > _vtuple(cur)
        log.info("Update-Prüfung: verfügbar %s (%s)%s", out["verfuegbar"], out["quelle"], " -- neuer als installiert" if out["neuer"] else "")
    except urllib.error.HTTPError as e:
        out["fehler"] = "Update-Prüfung nicht möglich: HTTP %s bei %s (%s)" % (e.code, e.geturl(), e.reason)
        log.warning(out["fehler"])
    except Exception as e:  # Netz aus, Repo privat, Ratenlimit ...
        out["fehler"] = "Update-Prüfung nicht möglich: %s: %s" % (type(e).__name__, str(e)[:200])
        log.warning(out["fehler"], exc_info=True)
    return out


def install_via_git(restart: bool = True) -> Optional[Dict[str, object]]:
    """Programmordner ist ein Git-Klon: 'git pull --ff-only' statt Archiv (haelt das Repo konsistent). None, wenn nicht anwendbar."""
    if not os.path.isdir(os.path.join(HERE, ".git")) or not shutil.which("git"):
        return None
    log.info("Update: Programmordner ist ein Git-Klon, führe git pull aus")
    try:
        r = subprocess.run(["git", "-C", HERE, "pull", "--ff-only"], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.error("Update: git pull fehlgeschlagen: %s", e)
        return {"ok": False, "text": "git pull fehlgeschlagen: %s" % e}
    log.info("Update: git pull Status %d: %s", r.returncode, (r.stdout + r.stderr).strip()[:500])
    if r.returncode != 0:
        return {"ok": False, "text": "git pull fehlgeschlagen: %s" % (r.stderr or r.stdout).strip()[:300]}
    restarted = schedule_restart() if (restart and sys.platform == "darwin") else False
    return {"ok": True, "version": current_version(), "dateien": 0, "neustart": restarted,
            "text": "Repo aktualisiert (%s)%s." % ((r.stdout.strip().splitlines() or ["ok"])[-1][:80], " -- Dienst startet neu" if restarted else "")}


def install(repo: str, zip_url: Optional[str] = None, restart: bool = True) -> Dict[str, object]:
    via_git = install_via_git(restart)
    if via_git is not None:
        return via_git
    info = check(repo) if not zip_url else {"zip": zip_url, "verfuegbar": "?"}
    url = zip_url or info.get("zip")
    if not url:
        return {"ok": False, "text": info.get("fehler") or "Keine Version gefunden."}
    log.info("Update: lade %s", url)
    try:
        data = _get(str(url), "*/*")
    except urllib.error.HTTPError as e:
        log.error("Update: Download fehlgeschlagen: HTTP %s bei %s (%s)", e.code, e.geturl(), e.reason)
        return {"ok": False, "text": "Download fehlgeschlagen: HTTP %s (%s) bei %s" % (e.code, e.reason, e.geturl())}
    except Exception as e:
        log.error("Update: Download fehlgeschlagen: %s", e, exc_info=True)
        return {"ok": False, "text": "Download fehlgeschlagen: %s: %s" % (type(e).__name__, str(e)[:200])}
    log.info("Update: %d Bytes geladen", len(data))
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        log.error("Update: Archiv unlesbar (kein ZIP, Anfang: %r)", data[:40])
        return {"ok": False, "text": "Archiv unlesbar."}
    names = zf.namelist()
    roots = {n.split("/")[0] for n in names if "/" in n}
    base = None
    for r in roots:
        if r + "/kontor.py" in names and r + "/VERSION" in names:
            base = r
            break
    if base is None:
        log.error("Update: Archiv ohne kontor.py/VERSION; Wurzeln: %s", sorted(roots)[:5])
        return {"ok": False, "text": "Archiv enthält kein Kontor (kontor.py/VERSION fehlen)."}
    new_version = zf.read(base + "/VERSION").decode("utf-8").strip()
    log.info("Update: Archiv enthält Version %s (%d Dateien), Programmordner %s", new_version, len(names), HERE)
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
    log.info("Update auf %s eingespielt (%d Dateien), Sicherung unter .alt", new_version, changed)
    # Touch-ID-Helfer bei Bedarf neu uebersetzen (ohne Fehler zu werfen)
    try:
        if sys.platform == "darwin":
            r = subprocess.run(["swiftc", "-O", "-o", os.path.join(HERE, "mm_touchid"), os.path.join(HERE, "mm_touchid.swift")],
                               capture_output=True, text=True, timeout=300)
            log.info("Update: Touch-ID-Helfer übersetzt (Status %s)%s", r.returncode, (": " + r.stderr.strip()[:300]) if r.returncode else "")
    except Exception as e:
        log.warning("Update: Touch-ID-Helfer nicht übersetzt: %s", e)
    restarted = False
    if restart and sys.platform == "darwin":
        restarted = schedule_restart()
        log.info("Update: Neustart des Dienstes %s", "angestossen" if restarted else "nicht möglich")
    return {"ok": True, "version": new_version, "dateien": changed, "neustart": restarted,
            "text": "Version %s installiert%s." % (new_version, " -- Dienst startet neu" if restarted else " -- bitte Dienst neu starten")}


def schedule_restart(label: str = "de.kontor.dienst") -> bool:
    """Dienst nach der Antwort neu starten (launchd haelt ihn am Leben)."""
    try:
        cmd = "sleep 1; launchctl kickstart -k gui/$(id -u)/%s" % label
        subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False
