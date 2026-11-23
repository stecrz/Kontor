"""Kontor's own Python: one fixed build of CPython in the program folder (.python/) -- loaded, checked, tried, switched to.
Only at the Mac and only on your click (Einstellungen -> Updates), or when you run the installer.

Why: the Python that comes with the Mac (Apple's command line tools) is 3.9, which gets no security fixes any more.

What is loaded: exactly one file per kind of Mac, named below with its size and SHA-256 -- a build of CPython from the
releases of python-build-standalone on GitHub. It comes over llm_local's checked way (https, GitHub's hosts only, every
redirect too; nothing is sent but the address); a file of another size or SHA-256 is thrown away before anything of it is
unpacked, let alone run.

Then, step by step -- whatever fails, nothing changes and the service goes on in the Python it runs in:
  1. unpacked beside what is in use (plain files and links that stay inside: llm_local.unpack), then compared with the
     archive file by file: all there, each as the archive holds it;
  2. made runnable without your help (macOS: the mark for files from the internet taken off; a signature the Mac does
     not accept -- there should be none -- made anew on this Mac for the files just compared);
  3. tried: the new Python starts, is the version named here and loads every part of Python and of Kontor that Kontor uses
     (pyselftest.py: certificates for https, the database, another program started ...);
  4. switched: the folder gets its name and the state file names it, written in one piece. From the next start the starter
     (pyboot.py) runs the service in it -- and should it not start there, in the Mac's Python again, by itself.
There is no way back to the Mac's Python by choice (user, 2026-11-23: always the newest Python) -- only the starter's own:
should Kontor's Python not start one day, the Mac's serves until it is loaded anew.
A newer build comes with a version of Kontor that names it here: shown as available, loaded on your click, never by itself.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.error
from datetime import datetime
from typing import Callable, Dict, List, Optional
from urllib.parse import quote

import llm_local
import pyboot
from i18n import tr

log = logging.getLogger("kontor.python")
HERE = os.path.dirname(os.path.abspath(__file__))
SELFTEST = os.path.join(HERE, "pyselftest.py")

# The build Kontor loads: CPython as python.org publishes it, built by the project python-build-standalone (the builds `uv`
# installs), from that project's release of this day on GitHub.
REPO = "astral-sh/python-build-standalone"
VERSION = "3.15.2"
BUILD = "20261110"
# One file per kind of Mac: its name in that release, its size, its SHA-256 -- as the release's own list (SHA256SUMS) names
# them, as the list of downloads in astral-sh/uv (crates/uv-python-managed/download-metadata.json) carries them, and as the
# files had them when they were loaded and looked at for this version (2026-11-23). A newer build: all of these lines.
FILES: Dict[str, Dict[str, object]] = {
    "macos-arm64": {"file": "cpython-3.15.2+20261110-aarch64-apple-darwin-install_only_stripped.tar.gz", "size": 27940828,
                    "sha256": "7e58607647b5b4832092a339ff1c55eeeccee128221232509b8fc8d27957065e"},
    "macos-x64": {"file": "cpython-3.15.2+20261110-x86_64-apple-darwin-install_only_stripped.tar.gz", "size": 28081859,
                  "sha256": "11143c2a2556b14619e8241d3f74bb43ad97181c0eb4909bab87d7aad1154e49"},
}
URL = "https://github.com/%s/releases/download/%s/%s"
ROOM = 400 * 1024 * 1024               # free space asked for: the archive, the build unpacked, what Python writes beside it
TRY_SECONDS = 180
# until when a line of Python gets security fixes (python.org) -- said of the Python Kontor runs in when it is past
ENDED = {(3, 9): "2025-10-31"}
STEPS = ("load", "unpack", "try", "switch")


class Cancelled(Exception):
    pass


def build() -> Optional[dict]:
    """The build for this machine: its file, size, SHA-256, address, and the name of its folder -- None: there is none."""
    f = FILES.get(llm_local.asset_tag())
    if not f:
        return None
    return dict(f, version=VERSION, build=BUILD, name="cpython-%s-%s" % (VERSION, BUILD), url=URL % (REPO, BUILD, quote(str(f["file"]))))


def fetch(b: dict, dest: str, job: dict) -> None:
    """Loads the one file of a build into dest (beside it first): exactly the size and SHA-256 named in FILES, or nothing
    of it stays."""
    part = dest + ".part"
    h, got, size = hashlib.sha256(), 0, int(b["size"])
    try:
        with llm_local._open(str(b["url"]), llm_local.GITHUB, timeout=60) as r, open(part, "wb") as out:
            while True:
                if job["cancel"].is_set():
                    raise Cancelled()
                chunk = r.read(1 << 18)
                if not chunk:
                    break
                got += len(chunk)
                if got > size:                  # more than announced: not that file
                    break
                out.write(chunk)
                h.update(chunk)
                job["done"] = got
        if got != size or h.hexdigest() != b["sha256"]:
            raise ValueError(tr("s_ki_pruefsumme"))
        os.replace(part, dest)
    finally:
        _gone(part)


def same(archive: str, dest: str) -> None:
    """What was unpacked into dest is what the archive holds: every file there, with its content; every link as written."""
    n = 0
    with tarfile.open(archive, "r:*") as tar:
        for m in tar:
            path = llm_local._safe_join(os.path.realpath(dest), m.name)
            if path is None:
                raise ValueError(tr("s_ki_archiv_unsicher"))
            if m.isreg():
                h = hashlib.sha256()
                src = tar.extractfile(m)
                for chunk in iter(lambda: src.read(1 << 20), b""):
                    h.update(chunk)
                if not os.path.isfile(path) or os.path.islink(path) or os.path.getsize(path) != m.size or _sha(path) != h.hexdigest():
                    raise ValueError(tr("s_ki_archiv_unsicher"))
                n += 1
            elif m.issym():
                if not os.path.islink(path) or os.readlink(path) != m.linkname:
                    raise ValueError(tr("s_ki_archiv_unsicher"))
            elif not m.isdir():
                raise ValueError(tr("s_ki_archiv_unsicher"))          # (a build holds files, folders and links, nothing else)
    if not n:
        raise ValueError(tr("s_ki_archiv_unsicher"))


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _gone(path: str) -> None:
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.lexists(path):
            os.remove(path)
    except OSError:
        pass


def _env(work: str) -> Dict[str, str]:
    """A small environment of its own for a Python that is tried: nothing of Kontor's, no proxies, its own folder for
    temporary files -- and a data folder that is not yours."""
    return {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.path.expanduser("~"), "LANG": "en_US.UTF-8", "TMPDIR": work,
            "KONTOR_DIR": os.path.join(work, "data")}


def run_python(here: str, exe: str, args: List[str], timeout: int) -> subprocess.CompletedProcess:
    """Runs a Python of Kontor's own folder (.python/ -- nothing else is ever started here), alone (-I -S: its own standard
    library only, no settings of yours) and without writing beside its files (-B), with the words given; in a temporary
    folder of its own that goes afterwards."""
    if not pyboot.inside(here, exe) or not os.path.isfile(exe):
        raise ValueError("not a Python of Kontor's own folder: %s" % os.path.basename(exe))
    work = tempfile.mkdtemp(prefix="kontor-python-")
    try:
        return subprocess.run([exe, "-I", "-S", "-B"] + list(args), capture_output=True, text=True, timeout=timeout, env=_env(work), cwd=work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def unmark(here: str, path: str) -> None:
    """macOS marks files that came from the internet and may refuse to run them (Gatekeeper). Kontor's own downloads do not
    get the mark; should this folder carry it all the same, it is taken off -- a folder of Kontor's own Python only, its
    files the ones just checked."""
    if sys.platform == "darwin" and pyboot.inside(here, path):
        try:
            subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", path], capture_output=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            pass


def programs(root: str) -> List[str]:
    """The files of a build that are programs or libraries of macOS (by how they begin)."""
    out = []
    for d, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(d, name)
            if os.path.islink(path):
                continue
            try:
                with open(path, "rb") as f:
                    if f.read(4) in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xce\xfa\xed\xfe"):
                        out.append(path)
            except OSError:
                pass
    return sorted(out)


def sign(here: str, root: str) -> None:
    """A Mac with Apple's own chip runs only programs that carry a valid signature. The builds carry one; should the Mac not
    accept it, each program file of this folder of Kontor's own Python gets a signature made on this Mac ("ad hoc": it names
    no one, it seals the file as it is -- and the file is the one just compared with the archive)."""
    for path in programs(root) if pyboot.inside(here, root) else []:
        try:
            subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", path], capture_output=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            pass


def starts(here: str, exe: str) -> str:
    """Does this Python start at all? "" when it does, else why not."""
    try:
        r = run_python(here, exe, ["-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"], 60)
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        return str(e)[:200] or type(e).__name__
    if r.returncode != 0 or not r.stdout.strip():
        return ((r.stderr or "").strip().splitlines() or ["exit %d" % r.returncode])[-1][:200]
    return ""


def runnable(here: str, root: str, exe: str) -> None:
    """Whatever a Mac may want before it runs a program loaded from the internet, done here instead of by you: the mark for
    such files taken off; if the program still does not start on a Mac, its files signed on this Mac, once."""
    unmark(here, root)
    why = starts(here, exe)
    if why and sys.platform == "darwin":
        log.warning("Python: the build does not start as unpacked (%s) -- signing it on this Mac", why)
        sign(here, root)
        why = starts(here, exe)
    if why:
        raise ValueError(tr("s_py_startet_nicht") % why)


def tried(here: str, exe: str, version: str) -> dict:
    """The new Python loads everything Kontor needs and it works there (pyselftest.py, run by that Python): its answer --
    or ValueError with what is missing. Only the version named counts."""
    try:
        r = run_python(here, exe, [SELFTEST], TRY_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(tr("s_py_test") % (str(e)[:200] or type(e).__name__))
    try:
        out = json.loads((r.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        out = None
    if not isinstance(out, dict):
        raise ValueError(tr("s_py_test") % ((r.stderr or "").strip().splitlines() or ["exit %d" % r.returncode])[-1][:200])
    if out.get("ok") is not True or r.returncode != 0:
        raise ValueError(tr("s_py_test") % str(out.get("error") or "exit %d" % r.returncode)[:300])
    if out.get("version") != version:
        raise ValueError(tr("s_py_version") % (str(out.get("version"))[:20], version))
    return out


def running_own(here: str) -> bool:
    """Does this very process run in Kontor's own Python?"""
    return bool(pyboot.starter()) or pyboot.inside(here, pyboot.running())


def remove_all(here: str, program: bool) -> str:
    """Uninstall: Kontor's own Python goes with everything of it -- "" (there was none), "removed", or "later": this very
    process runs in it, so the starter removes the folder once the service has ended (pyboot.py; with the program folder
    when that is to go too)."""
    root = pyboot.folder(here)
    if not os.path.lexists(root):
        return ""
    if running_own(here):
        with open(os.path.join(root, pyboot.REMOVE), "w", encoding="utf-8") as f:
            f.write("program" if program else "")
        return "later"
    _gone(root)
    return "removed"


class Runtime:
    """Kontor's own Python in one program folder: what is there, what is in use, and the one job that changes it."""

    def __init__(self, program_dir: str):
        self.here = program_dir
        self.lock = threading.Lock()
        self.job: Optional[dict] = None
        self.on_switch: Optional[Callable[[], None]] = None       # another Python is to run the service: the service starts anew

    # -- what is there ---------------------------------------------------------------------------------------------------
    def status(self) -> dict:
        st, b = pyboot.read_state(self.here), build()
        exe = pyboot.exe_in(self.here, st.get("dir"))
        have, own = bool(exe), running_own(self.here)
        failed = st.get("failed") if isinstance(st.get("failed"), dict) else None
        want = exe if st.get("use") == "own" and not failed else ""          # the Python the next start runs the service in ("": the Mac's)
        runs = pyboot.serving(self.here)
        return {"supported": b is not None,
                "running": {"version": "%d.%d.%d" % sys.version_info[:3], "own": own, "ended": "" if own else ENDED.get(tuple(sys.version_info[:2]), "")},
                "offered": {"version": VERSION, "build": BUILD, "size": int(b["size"])} if b else None,
                "loaded": {"version": str(st.get("version") or "")[:20], "build": str(st.get("build") or "")[:20], "date": str(st.get("installed") or "")[:16]} if have else None,
                "use": "own" if st.get("use") == "own" else "",          # "": none chosen (the Mac's serves)
                "failed": {"at": str(failed.get("at") or "")[:16], "why": str(failed.get("why") or "")[:20], "detail": str(failed.get("detail") or "")[:200]} if failed else None,
                "newer": bool(have and b and st.get("dir") != b["name"]),
                "restart": want != runs,                       # what is chosen is not what runs: after the next start
                "job": self.job_view()}

    def job_view(self) -> Optional[dict]:
        j = self.job
        return {k: j[k] for k in ("state", "step", "done", "total", "text")} if j else None

    # -- the one job: load (unless it is there), try, switch ------------------------------------------------------------------
    def install(self) -> dict:
        """Loads the build named here unless it is on this Mac already, tries it, and switches to it -- in the background."""
        with self.lock:
            if self.job and self.job["state"] == "running":
                raise ValueError(tr("s_ki_laedt_schon"))
            job = self.job = {"state": "running", "step": "load", "done": 0, "total": 0, "text": "", "cancel": threading.Event()}

        def run():
            try:
                self._work(job)
                job["state"] = "done"
            except Cancelled:
                job["state"] = "cancelled"
            except Exception as e:
                job.update(state="error", text=_reason(e, job["step"]))
                log.warning("Python: not switched (%s): %s", job["step"], str(e)[:300])
            if job["state"] == "done" and self.on_switch is not None:
                self.on_switch()
        threading.Thread(target=run, name="kontor-python", daemon=True).start()
        return self.status()

    def install_now(self, say: Callable[[str], None]) -> bool:
        """The same in the foreground, for the installer: True when Kontor's own Python is the one to run the service."""
        b = build()
        if b is None:
            return False
        job = self.job = {"state": "running", "step": "load", "done": 0, "total": 0, "text": "", "cancel": threading.Event()}
        say(tr("s_py_cli_laden") % (b["version"], round(int(b["size"]) / 1e6)))
        try:
            self._work(job)
        except Exception as e:
            job.update(state="error", text=_reason(e, job["step"]))
            say(tr("s_py_cli_fehler") % job["text"])
            return False
        job["state"] = "done"
        say(tr("s_py_cli_fertig") % b["version"])
        return True

    def cancel(self) -> None:
        if self.job:
            self.job["cancel"].set()

    def _step(self, job: dict, step: str) -> None:
        if job["cancel"].is_set():
            raise Cancelled()
        job["step"] = step

    def _work(self, job: dict) -> None:
        b = build()
        if b is None:
            raise ValueError(tr("s_py_kein_build"))
        root = pyboot.folder(self.here)
        os.makedirs(root, exist_ok=True)
        self.sweep()
        final = os.path.join(root, str(b["name"]))
        exe = pyboot.exe_in(self.here, b["name"])
        if exe:                                          # on this Mac already (switched back since, or tried again): tried, not loaded
            self._step(job, "try")
            try:
                tried(self.here, exe, str(b["version"]))
            except ValueError:
                if running_own(self.here):
                    raise
                exe = ""                                 # damaged: loaded anew
        if not exe:
            free = shutil.disk_usage(root).free
            if free < ROOM:
                raise ValueError(tr("s_ki_platz_fehlt") % ("%.1f" % (ROOM / 1e9), "%.1f" % (free / 1e9)))
            arch, tmp = os.path.join(root, str(b["file"])), final + ".tmp"
            job.update(step="load", done=0, total=int(b["size"]))
            try:
                fetch(b, arch, job)
                self._step(job, "unpack")
                llm_local.unpack(arch, tmp)
                same(arch, tmp)
                exe = os.path.realpath(os.path.join(tmp, "python", "bin", "python3"))
                if not pyboot.inside(self.here, exe) or not os.path.isfile(exe):
                    raise ValueError(tr("s_ki_archiv_unsicher"))          # (no program in it: not a build)
                self._step(job, "try")
                runnable(self.here, tmp, exe)
                tried(self.here, exe, str(b["version"]))
                self._step(job, "switch")
                _gone(final)                             # (no program in it, or one that failed: nothing runs from it)
                os.replace(tmp, final)
            finally:
                _gone(tmp)
                _gone(arch)
        self._step(job, "switch")
        st = pyboot.read_state(self.here)
        st.update(use="own", dir=b["name"], version=b["version"], build=b["build"], sha256=b["sha256"], installed=datetime.now().strftime("%Y-%m-%d %H:%M"))
        st.pop("failed", None)
        pyboot.write_state(self.here, st)
        log.info("Python: Kontor's own %s (%s) is the one to run the service from the next start", b["version"], b["build"])

    # -- away -------------------------------------------------------------------------------------------------------------
    def remove(self) -> dict:
        """The loaded builds go (one that did not start) -- not while the service runs in one of them."""
        if running_own(self.here) or (self.job and self.job["state"] == "running"):
            raise ValueError(tr("s_py_in_gebrauch"))
        root = pyboot.folder(self.here)
        if os.path.isdir(root):
            pyboot.write_state(self.here, {})
            for name in os.listdir(root):
                if name != pyboot.STATE:
                    _gone(os.path.join(root, name))
        log.info("Python: Kontor's own removed")
        return self.status()

    def sweep(self) -> None:
        """What an earlier try left behind (a file half loaded, a folder half unpacked) and builds no longer in use go --
        never the one the state file names, never while this process runs in one that is not named there."""
        root = pyboot.folder(self.here)
        if not os.path.isdir(root):
            return
        keep = {pyboot.STATE, pyboot.REMOVE, str(pyboot.read_state(self.here).get("dir") or "")}
        mine = pyboot.serving(self.here)
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if name in keep or mine.startswith(os.path.realpath(path) + os.sep):
                continue
            _gone(path)


def _reason(e: Exception, step: str) -> str:
    """An error as a line for you: no connection said as that, what Kontor found in its own words."""
    if isinstance(e, urllib.error.HTTPError):
        return tr("s_download_fehlgeschlagen") % (e.code, e.reason)
    if isinstance(e, urllib.error.URLError):
        return tr("s_ki_netz") % str(e.reason)[:200]
    if isinstance(e, ValueError):
        return str(e)[:400]
    return tr("s_ki_netz" if step == "load" else "s_py_fehler") % ("%s: %s" % (type(e).__name__, str(e)[:200])).rstrip(": ")
