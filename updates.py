"""Updates aus GitHub: pruefen, laden, Programmdateien ersetzen, Dienst neu starten.

Nur zu GitHub und nur auf Wunsch (Einstellungen: taeglich pruefen und/oder "Jetzt pruefen"). Installiert wird
nie automatisch, sondern nach Klick. Der Datenordner wird nicht angefasst.
Integritaet: HTTPS zu GitHub, feste Host-Liste, das Archiv muss kontor.py und
VERSION enthalten.
Before anything of a new version is installed (or run), the installed one reads its files and compares what they hold of
the things that reach beyond the program -- network, other programs, loading code, addresses, helpers (update_guard.py).
Nothing new or changed among them: installed as before. Otherwise the update waits, the settings name what was found, and
it is installed only with an approval given for exactly these files (their digest). A folder that is a git clone is
checked the same way: fetched from the repository the settings name (its origin must be that one), read as a whole -- what
of it is no part of the program and no ordinary file of its tests is a finding, an approval is for the whole new state --
and only then moved forward to exactly the commit that was read.
Die Programmdateien werden direkt ersetzt, ohne Sicherung: VERSION
zuletzt -- bricht ein Update ab, bleibt die alte Nummer, der Dienst startet nicht neu
(die alte Version laeuft im Speicher weiter) und das Update laesst sich wiederholen.
Dateien, die die vorige Version gebracht hat und die neue nicht mehr enthaelt, werden
entfernt -- nur diese (Liste in .files), nur im Programmordner.
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
from typing import Dict, List, Optional, Tuple
from i18n import tr
import update_guard

log = logging.getLogger("kontor.update")
HERE = os.path.dirname(os.path.abspath(__file__))
ALLOWED_HOSTS = ("api.github.com", "codeload.github.com", "github.com", "raw.githubusercontent.com", "objects.githubusercontent.com")
TIMEOUT = 25
KEEP = {".touchid", "web/.DS_Store"}       # nicht ueberschreiben/loeschen
MANIFEST = ".files"                         # what the installed version brought: removed again when the next one no longer has it


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
        if urlparse(final).netloc not in ALLOWED_HOSTS or not final.startswith("https://"):
            raise ValueError(tr("s_umleitung_auf_fremden_host_s") % final)
        data = r.read()
        log.debug("GET %s -> %s, %d bytes%s", url, r.status, len(data), (" via " + final) if final != url else "")
        return data


def archive_url(repo: str, ref: str, kind: str = "tags") -> str:
    """ZIP-Archiv eines Tags oder Zweigs ueber github.com (leitet auf codeload.github.com um).
    Nicht die API-Adresse 'zipball' verwenden: sie antwortet auf Accept: application/octet-stream mit 415."""
    return "https://github.com/%s/archive/refs/%s/%s.zip" % (repo, kind, ref)


HEADING_RE = re.compile(r"^##\s+v?(\S+)(?:\s+\((\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?)\))?")      # date, optionally with time (local)


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


DEV_RE = re.compile(r"^\s*[-*]\s+(?:Entwicklung|Development)\s*:")      # rules, tests, CI -- nothing the user notices
TOPIC_RE = re.compile(r"^\s*[-*]\s+([^:]{1,40}):\s")                         # "- KI-Assistent: ..." -> "KI-Assistent"


def changelog_since(text: str, current: str, upto: str) -> Tuple[str, str, str]:
    """Was ein Update von <current> auf <upto> bringt: die Punkte aller Abschnitte dazwischen in einer Liste
    (neueste zuerst, gleicher Bezug vor dem Doppelpunkt beieinander, doppelte und Entwicklungs-Punkte weg).
    Rueckgabe: (Neuerungen, Datum von <upto>, aelteste enthaltene Version)."""
    cur, top = _vtuple(current), _vtuple(upto)
    lines, datum, first, on = [], "", "", False
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            v = _vtuple(m.group(1))
            on = cur < v <= top
            if on:
                first = m.group(1)
                if v == top:
                    datum = m.group(2) or ""
            continue
        if on and line.strip() and not line.startswith("# ") and not DEV_RE.match(line):
            lines.append(line.rstrip())
    groups: Dict[str, List[str]] = {}
    for line in lines:
        m = TOPIC_RE.match(line)
        g = groups.setdefault(m.group(1).strip().lower() if m else "\0%d" % len(groups), [])
        if line not in g:
            g.append(line)
    return "\n".join(x for g in groups.values() for x in g)[:8000], datum, first


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


def _archive(data: bytes) -> Tuple[Optional[zipfile.ZipFile], Optional[str]]:
    """The archive and its folder that holds Kontor (the one with kontor.py and VERSION) -- (None, None) when it is none."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return None, None
    names = zf.namelist()
    for r in sorted({n.split("/")[0] for n in names if "/" in n}):
        if r + "/kontor.py" in names and r + "/VERSION" in names:
            return zf, r
    return zf, None


MAX_FILE = 64 * 1024 * 1024         # bytes of one file of an update, unpacked (the largest today: a help picture of 1 MB)
MAX_TREE = 512 * 1024 * 1024        # bytes of everything a git clone's new state holds (today under 20 MB)


def _new_files(zf: zipfile.ZipFile, base: str) -> Dict[str, bytes]:
    """What the archive would put into the program folder: {path in the folder: content} (as install copies it)."""
    out: Dict[str, bytes] = {}
    for info in zf.infolist():
        if info.is_dir() or not info.filename.startswith(base + "/"):
            continue
        rel = os.path.normpath(info.filename[len(base) + 1:]).replace(os.sep, "/")
        if rel.startswith(("/", "../")) or rel == ".." or not update_guard.installable(rel):
            continue
        if info.file_size > MAX_FILE:
            raise ValueError("%s: %d MB" % (rel, info.file_size // 1048576))
        out[rel] = zf.read(info)
    return out


def review(new: Dict[str, bytes]) -> Dict[str, object]:
    """The new files against the installed ones: {"digest": of exactly these new files, "findings": what they hold that the
    installed version does not hold the same way (update_guard.compare) -- empty: nothing to ask about}. If the check itself
    fails, that is a finding: an update is never installed unread."""
    old: Dict[str, bytes] = {}
    for rel in sorted(set(new) | update_guard.kept()):         # the files the check names: also when the new version has them no more
        try:
            with open(os.path.join(HERE, *rel.split("/")), "rb") as f:
                old[rel] = f.read()
        except OSError:
            pass
    try:
        found = update_guard.compare(old, new)
    except Exception as e:          # a file no reader of Python understands: shown, not passed over
        log.warning("Update: check of the new files failed (%s)", type(e).__name__)
        found = [{"kind": "unreadable", "file": "", "what": type(e).__name__, "new": True}]
    for f in found:                 # a helper or script: how many lines change, and whether calls to the outside are among them
        if "added" in f:
            f["what"] = " · ".join([tr("upd_zeilen", f["added"], f["removed"])] + ([tr("upd_aussen")] if f.get("out") else []) + [str(f["what"])])
    return {"digest": update_guard.digest(new), "findings": found}


def _approved(rev: Dict[str, object], approved: str) -> bool:
    return not rev["findings"] or (bool(approved) and approved == rev["digest"])


def _waits(rev: Dict[str, object], version: str) -> Dict[str, object]:
    kinds = update_guard.summary(rev["findings"])            # type: ignore[arg-type]
    log.warning("Update to %s waits for approval: %s", version, ", ".join("%d %s" % (n, k) for k, n in sorted(kinds.items())))
    return {"ok": False, "needs_approval": True, "version": version, "review": rev, "text": tr("s_update_wartet")}


def check(repo: str, look: bool = True) -> Dict[str, object]:
    """Neueste Version auf GitHub: VERSION im Hauptzweig (eine kleine Datei, kein API-Limit); nur wenn das
    nicht geht, Release bzw. Tag. Tags sind damit keine Voraussetzung mehr fuer ein Update."""
    cur = current_version()
    out: Dict[str, object] = {"current": cur, "available": None, "date": "", "newer": False, "notes": "", "since": "", "source": "", "error": None}
    log.info("Update check: installed %s, repo %s", cur, repo)
    try:
        try:
            v = _get("https://raw.githubusercontent.com/%s/main/VERSION" % repo, "text/plain").decode("utf-8").strip()
            if not re.match(r"^v?\d+(\.\d+)*$", v):
                raise ValueError(tr("s_version_im_hauptzweig_unlesbar_r") % v[:40])
            out.update({"available": v, "source": "main", "zip": archive_url(repo, "main", "heads")})
            try:
                cl = _get("https://raw.githubusercontent.com/%s/main/CHANGELOG.md" % repo, "text/plain").decode("utf-8", "replace")
                out["notes"], out["date"], out["since"] = changelog_since(cl, cur, v)
            except Exception as e:      # Neuerungen sind nur Beiwerk
                log.debug("CHANGELOG not readable: %s", e)
        except urllib.error.HTTPError as e:
            if e.code not in (404, 403):
                raise
            log.debug("VERSION on main branch not readable (%s), checking releases/tags", e.code)
            try:
                rel = json.loads(_get("https://api.github.com/repos/%s/releases/latest" % repo).decode("utf-8"))
                tag = str(rel.get("tag_name") or "")
                out.update({"available": tag, "notes": (rel.get("body") or "")[:4000], "date": str(rel.get("published_at") or "")[:10],
                            "source": "release", "zip": archive_url(repo, tag)})
            except urllib.error.HTTPError as e2:
                if e2.code != 404:
                    raise
                tags = json.loads(_get("https://api.github.com/repos/%s/tags" % repo).decode("utf-8"))
                if not tags:
                    raise
                tag = max((str(t["name"]) for t in tags), key=_vtuple)
                out.update({"available": tag, "source": "tag", "zip": archive_url(repo, tag)})
        out["newer"] = _vtuple(str(out["available"])) > _vtuple(cur)
        if out["newer"]:
            log.info("Update check: %s available (%s), newer than installed", out["available"], out["source"])
            if look and out.get("zip"):                        # read it now, so the settings can say whether it will wait for you
                try:
                    clone = _clone(repo)                       # a git clone: read as installing reads it (the whole repository)
                    if clone is not None:
                        if "review" in clone:
                            out["review"] = clone["review"]
                    else:
                        zf, base = _archive(_get(str(out["zip"]), "*/*"))
                        if zf is not None and base is not None:
                            out["review"] = review(_new_files(zf, base))
                    if "review" in out:
                        log.info("Update check: %d finding(s) in the new version's files", len(out["review"]["findings"]))      # type: ignore[index]
                except Exception as e:                         # not readable now: installing reads it again and decides
                    log.info("Update check: new version not read yet (%s)", type(e).__name__)
        else:
            log.info("Update check: up to date (%s shows %s)", out["source"], out["available"])
    except urllib.error.HTTPError as e:
        out["error"] = tr("s_update_pruefung_nicht_moeglich_http") % (e.code, e.geturl(), e.reason)
        log.warning("Update check failed: %s", out["error"])
    except Exception as e:  # Netz aus, Repo privat, Ratenlimit ...
        out["error"] = tr("s_update_pruefung_nicht_moeglich_s") % (type(e).__name__, str(e)[:200])
        log.warning("Update check failed: %s", out["error"], exc_info=True)
    return out


def _git(*args: str, timeout: int = 120, binary: bool = False, data: Optional[bytes] = None):
    # never a hook or a filter of the repository: what git runs here is git alone
    return subprocess.run(["git", "-C", HERE, "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false"] + list(args),
                          capture_output=True, text=not binary, timeout=timeout, input=data)


GIT_OWN = (".gitattributes", ".gitmodules")        # files that change what git itself does with the other files
GIT_SOURCE = "https://github.com/%s.git"
REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}")


def _git_source(repo: str) -> str:
    """Where a clone of the repository the settings name fetches from."""
    return GIT_SOURCE % repo


def _same_source(url: str, want: str) -> bool:
    """Is the clone's origin the address of that repository (https or ssh to github.com, with or without .git)?"""
    def plain(u: str) -> str:
        u = u.strip().rstrip("/")
        u = u[:-4] if u.endswith(".git") else u
        m = re.match(r"(?i)^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+/[^/]+)$", u)
        return "github.com/" + m.group(1).lower() if m else u
    return bool(url.strip()) and plain(url) == plain(want)


def _here(rel: str) -> bytes:
    """A file of the program folder as it is now (empty when there is none)."""
    try:
        with open(os.path.join(HERE, *rel.split("/")), "rb") as f:
            return f.read()
    except OSError:
        return b""


def _git_tree(ref: str) -> List[Tuple[str, str, str, str]]:
    """Every entry of a commit's tree as git holds it: [(path, mode, kind, object)]."""
    r = _git("ls-tree", "-r", "-z", "--full-tree", ref, binary=True)
    if r.returncode != 0:
        raise ValueError("git ls-tree")
    out = []
    for entry in r.stdout.split(b"\0"):
        if entry:
            meta, _, raw = entry.partition(b"\t")
            mode, kind, oid = meta.decode("ascii").split()
            out.append((raw.decode("utf-8", "surrogateescape"), mode, kind, oid))
    return out


def _git_files(sha: str) -> Tuple[Dict[str, bytes], List[Dict[str, object]], str]:
    """The files of a commit as git holds them (no filters, no archive rules of the repository): ({path: content} of what
    reaches the program folder as program, [findings for everything else of the new state that arrives unread -- no plain
    file (a link, another repository), files that tell git to treat others differently, files that are no part of the program
    and no ordinary file of its tests and development (update_guard.beside)], the fingerprint of the whole tree). Only what is
    new or changed against the commit there is now is named."""
    entries = _git_tree(sha)
    try:
        before = {rel: (mode, oid) for rel, mode, _kind, oid in _git_tree("HEAD")}
    except ValueError:
        before = {}
    blobs = [(rel, oid) for rel, _mode, kind, oid in entries if kind == "blob"]
    ask = b"".join(o.encode("ascii") + b"\n" for _, o in blobs)
    sizes = [int(x.split()[2]) if len(x.split()) == 3 else -1 for x in _git("cat-file", "--batch-check", binary=True, data=ask).stdout.splitlines()]
    if len(sizes) != len(blobs) or min(sizes, default=0) < 0 or sum(sizes) > MAX_TREE:      # sizes first: nothing too big is read
        raise ValueError("git cat-file: %d MB" % (sum(sizes) // 1048576))
    for (rel, _oid), size in zip(blobs, sizes):
        if size > MAX_FILE:
            raise ValueError("%s: %d MB" % (rel, size // 1048576))
    out = _git("cat-file", "--batch", binary=True, data=ask).stdout
    data: Dict[str, bytes] = {}
    pos = 0
    for rel, oid in blobs:
        end = out.index(b"\n", pos)
        head = out[pos:end].split()
        if len(head) != 3 or head[0].decode("ascii") != oid:
            raise ValueError("git cat-file")
        size = int(head[2])
        if size > MAX_FILE:
            raise ValueError("%s: %d MB" % (rel, size // 1048576))
        data[rel] = out[end + 1:end + 1 + size]
        pos = end + 1 + size + 1
    lists = []                                               # the repository's own list of what programs make (both versions)
    for text in (data.get(".gitignore", b""), _here(".gitignore")):
        lists += text.decode("utf-8", "replace").splitlines()
    files: Dict[str, bytes] = {}
    odd: List[Dict[str, object]] = []
    whole: Dict[str, bytes] = {}
    for rel, mode, kind, oid in entries:
        whole[rel + "\0" + mode] = data[rel] if rel in data else (kind + " " + oid).encode("ascii")
        same = before.get(rel) == (mode, oid)
        base = rel.rsplit("/", 1)[-1]
        if kind != "blob" or mode not in ("100644", "100755"):
            if not same:
                odd.append({"kind": "file", "file": rel, "what": "link" if mode == "120000" else kind, "new": rel not in before})
            continue
        if base in GIT_OWN:
            if not same:
                odd.append({"kind": "file", "file": rel, "what": rel, "new": rel not in before})
            continue
        if update_guard.installable(rel):
            files[rel] = data[rel]
            if not same and update_guard.ignored(rel, update_guard.MADE_HERE.splitlines() + lists):
                odd.append({"kind": "extra", "file": rel, "what": rel, "new": rel not in before})
            continue
        why = None if same else update_guard.beside(rel, data[rel], lists)
        if why:
            odd.append({"kind": "extra", "file": rel, "what": why, "new": rel not in before})
    return files, odd, update_guard.digest(whole, whole=True)


def _clone(repo: str) -> Optional[Dict[str, object]]:
    """Programmordner ist ein Git-Klon: fetched from exactly the repository the settings name (its origin must be that one),
    read as a whole -- {"sha", "version", "review"} or {"text"} when that is not possible; None when it is no clone."""
    if not os.path.isdir(os.path.join(HERE, ".git")) or not shutil.which("git"):
        return None
    origin = _git("remote", "get-url", "origin")
    want = _git_source(repo) if REPO_RE.fullmatch(repo or "") and ".." not in repo else ""
    if not want or origin.returncode != 0 or not _same_source(origin.stdout, want):
        log.error("Update: the clone fetches from %r, not from %r: not updated", origin.stdout.strip()[:200], want)
        return {"text": tr("s_git_pull_fehlgeschlagen") % ("origin %s ≠ %s" % (origin.stdout.strip()[:200] or "?", want or repo))}
    log.info("Update: program folder is a git clone, fetching %s", want)
    r = _git("fetch", "--quiet", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main")
    sha = _git("rev-parse", "--verify", "--quiet", "refs/remotes/origin/main^{commit}").stdout.strip() if r.returncode == 0 else ""
    if r.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        log.error("Update: git fetch failed: %s", (r.stderr or r.stdout).strip()[:300])
        return {"text": tr("s_git_pull_fehlgeschlagen") % ((r.stderr or r.stdout).strip()[:300] or "origin/main")}
    new, odd, whole = _git_files(sha)
    if "kontor.py" not in new or "VERSION" not in new:
        return {"text": tr("s_archiv_enthaelt_kein_kontor_kontor")}
    rev = review(new)
    rev["findings"] = odd + rev["findings"]                  # type: ignore[operator]
    rev["digest"] = whole                                    # an approval is for the whole new state of the clone
    return {"sha": sha, "version": new["VERSION"].decode("utf-8", "replace").strip(), "review": rev}


def install_via_git(restart: bool = True, approved: str = "", repo: str = "") -> Optional[Dict[str, object]]:
    """Programmordner ist ein Git-Klon: holen, lesen, dann genau auf den gelesenen Stand vorruecken (statt Archiv; haelt das Repo
    konsistent). None, wenn nicht anwendbar. Nothing of the new state is in the folder before it is read and approved -- and
    then exactly the commit that was read."""
    try:
        clone = _clone(repo)
        if clone is None:
            return None
        if "sha" not in clone:
            return {"ok": False, "text": clone["text"]}
        sha, rev = str(clone["sha"]), clone["review"]
        if not _approved(rev, approved):                     # type: ignore[arg-type]
            return _waits(rev, str(clone["version"]))        # type: ignore[arg-type]
        r = _git("merge", "--ff-only", "--quiet", sha)
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        log.error("Update: git update failed: %s", e)
        return {"ok": False, "text": tr("s_git_pull_fehlgeschlagen") % e}
    log.info("Update: git merge --ff-only %s: status %d: %s", sha[:10], r.returncode, (r.stdout + r.stderr).strip()[:500])
    if r.returncode != 0:
        return {"ok": False, "text": tr("s_git_pull_fehlgeschlagen") % (r.stderr or r.stdout).strip()[:300]}
    restarted = schedule_restart() if (restart and sys.platform == "darwin") else False
    return {"ok": True, "version": current_version(), "files": 0, "restart": restarted,
            "text": tr("s_repo_aktualisiert") % (sha[:10], tr("s_dienst_startet_neu") if restarted else "")}


def _manifest() -> set:
    """The files the installed version brought (empty before the first update that wrote the list: nothing is removed then)."""
    try:
        with open(os.path.join(HERE, MANIFEST), encoding="utf-8") as f:
            return {ln.strip() for ln in f if ln.strip() and not ln.startswith("/") and ".." not in ln.split("/")}
    except OSError:
        return set()


def _put(src: str, rel: str) -> None:
    dst = os.path.join(HERE, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    if rel.endswith((".py", ".sh", ".command")):
        os.chmod(dst, 0o755)


def _remove_gone(before: set, installed: set) -> int:
    """Remove what the previous version brought and this one no longer has -- only files of that list, really inside the
    program folder (links resolved), never one this version just wrote under another case of its name (the Mac's disks
    do not tell Foo.py from foo.py)."""
    home, now, n = os.path.realpath(HERE), {x.casefold() for x in installed}, 0
    for rel in sorted(before - installed):
        if rel in KEEP or rel.casefold() in now:
            continue
        dst = os.path.join(HERE, rel)
        real = os.path.realpath(dst)
        if os.path.commonpath([real, home]) != home or real == home or not os.path.isfile(dst):
            continue
        try:
            os.remove(dst)
            n += 1
        except OSError as e:
            log.warning("Update: %s not removed: %s", rel, e)
    return n


def install(repo: str, zip_url: Optional[str] = None, restart: bool = True, approved: str = "") -> Dict[str, object]:
    """approved: the digest of the files you have seen the findings of (from check or an earlier try) -- an update with
    findings is installed only when it is exactly those files."""
    via_git = install_via_git(restart, approved, repo)
    if via_git is not None:
        return via_git
    info = check(repo, look=False) if not zip_url else {"zip": zip_url, "available": "?"}
    url = zip_url or info.get("zip")
    if not url:
        return {"ok": False, "text": info.get("error") or tr("s_keine_version_gefunden")}
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
    zf, base = _archive(data)
    if zf is None:
        log.error("Update: archive unreadable (not a ZIP, starts with %r)", data[:40])
        return {"ok": False, "text": tr("s_archiv_unlesbar")}
    names = zf.namelist()
    if base is None:
        log.error("Update: archive without kontor.py/VERSION; roots: %s", sorted({n.split("/")[0] for n in names if "/" in n})[:5])
        return {"ok": False, "text": tr("s_archiv_enthaelt_kein_kontor_kontor")}
    new_version = zf.read(base + "/VERSION").decode("utf-8").strip()
    log.info("Update: archive contains version %s (%d files), program folder %s", new_version, len(names), HERE)
    try:                                                       # read before anything of it is copied (or run)
        new = _new_files(zf, base)
        rev = review(new)
    except (ValueError, OSError, zipfile.BadZipFile) as e:
        log.error("Update: archive not readable for the check: %s", e)
        return {"ok": False, "text": tr("s_archiv_unlesbar")}
    if not _approved(rev, approved):
        return _waits(rev, new_version)
    tmp = tempfile.mkdtemp(prefix="kontor-update-")
    before, installed = _manifest(), set()
    try:
        # exactly the files that were read, nothing else of the archive. VERSION last: an update stopped half-way keeps the old
        # number -- offered again, the service not restarted on a mix
        part = os.path.join(tmp, "file")
        for rel in sorted(new):
            if rel in KEEP or rel == "VERSION":
                continue
            with open(part, "wb") as f:
                f.write(new[rel])
            _put(part, os.path.normpath(rel))
            installed.add(rel)
        removed = _remove_gone(before, installed)
        try:
            with open(os.path.join(HERE, MANIFEST), "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(installed | {"VERSION"})) + "\n")
        except OSError as e:
            log.warning("Update: file list not written: %s", e)
        with open(part, "wb") as f:
            f.write(new["VERSION"])
        _put(part, "VERSION")
        installed.add("VERSION")
    except OSError as e:
        log.error("Update: stopped while copying: %s", e, exc_info=True)
        return {"ok": False, "text": tr("s_update_abgebrochen") % str(e)[:200]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for d in () if os.path.isdir(os.path.join(HERE, ".git")) else (".github", ".claude"):
        if os.path.isdir(os.path.join(HERE, d)) and not os.path.islink(os.path.join(HERE, d)):
            shutil.rmtree(os.path.join(HERE, d), ignore_errors=True)          # folders of the repository that are not part of the program
    changed = len(installed)
    log.info("Update to %s applied (%d files, %d removed)", new_version, changed, removed)
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
    return {"ok": True, "version": new_version, "files": changed, "restart": restarted,
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
