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
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        final = r.geturl()
        if urlparse(final).netloc not in ALLOWED_HOSTS:
            raise ValueError("Umleitung auf fremden Host: %s" % final)
        return r.read()


def check(repo: str) -> Dict[str, object]:
    """Neueste Version auf GitHub (Release, sonst Tag, sonst VERSION im Hauptzweig)."""
    cur = current_version()
    out: Dict[str, object] = {"aktuell": cur, "verfuegbar": None, "neuer": False, "notizen": "", "quelle": "", "fehler": None}
    try:
        try:
            rel = json.loads(_get("https://api.github.com/repos/%s/releases/latest" % repo).decode("utf-8"))
            out.update({"verfuegbar": rel.get("tag_name"), "notizen": (rel.get("body") or "")[:4000], "quelle": "release",
                        "zip": rel.get("zipball_url")})
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            tags = json.loads(_get("https://api.github.com/repos/%s/tags" % repo).decode("utf-8"))
            if tags:
                out.update({"verfuegbar": tags[0]["name"], "quelle": "tag", "zip": tags[0].get("zipball_url")})
            else:
                v = _get("https://raw.githubusercontent.com/%s/main/VERSION" % repo, "text/plain").decode("utf-8").strip()
                out.update({"verfuegbar": v, "quelle": "main", "zip": "https://api.github.com/repos/%s/zipball/main" % repo})
        out["neuer"] = _vtuple(str(out["verfuegbar"])) > _vtuple(cur)
    except Exception as e:  # Netz aus, Repo privat, Ratenlimit ...
        out["fehler"] = "Update-Pruefung nicht moeglich: %s" % (str(e)[:200])
        log.warning(out["fehler"])
    return out


def install(repo: str, zip_url: Optional[str] = None, restart: bool = True) -> Dict[str, object]:
    info = check(repo) if not zip_url else {"zip": zip_url, "verfuegbar": "?"}
    url = zip_url or info.get("zip")
    if not url:
        return {"ok": False, "text": info.get("fehler") or "Keine Version gefunden."}
    try:
        data = _get(str(url), "application/octet-stream")
    except Exception as e:
        return {"ok": False, "text": "Download fehlgeschlagen: %s" % str(e)[:200]}
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return {"ok": False, "text": "Archiv unlesbar."}
    names = zf.namelist()
    roots = {n.split("/")[0] for n in names if "/" in n}
    base = None
    for r in roots:
        if r + "/kontor.py" in names and r + "/VERSION" in names:
            base = r
            break
    if base is None:
        return {"ok": False, "text": "Archiv enthaelt kein Kontor (kontor.py/VERSION fehlen)."}
    new_version = zf.read(base + "/VERSION").decode("utf-8").strip()
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
            subprocess.run(["swiftc", "-O", "-o", os.path.join(HERE, "mm_touchid"), os.path.join(HERE, "mm_touchid.swift")],
                           capture_output=True, timeout=300)
    except Exception:
        pass
    restarted = False
    if restart and sys.platform == "darwin":
        restarted = schedule_restart()
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
