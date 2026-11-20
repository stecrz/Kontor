"""The assistant's language model on this Mac: llama.cpp's server (llama-server) and model files (GGUF) -- installed, updated,
started and stopped by Kontor, only from Einstellungen -> Assistent, only on your click.

What goes over the network -- only on such a click, only downloads, HTTPS, fixed hosts:
  - llama.cpp from its releases on GitHub (api.github.com, github.com, *.githubusercontent.com), checked by the SHA-256 GitHub
    names for the file;
  - a model file from Hugging Face (huggingface.co and its download hosts *.huggingface.co, *.hf.co), checked by its SHA-256.
Nothing of yours is ever sent: a request names the file to fetch, nothing else.

How the model runs: as a child process of the service, listening on 127.0.0.1 only, on a free port, with a key made for that
start (kept in memory only, given to it in its environment, never on its command line); without its chat app, without tools of
its own, offline. On the Mac inside the system's sandbox (sandbox-exec): no network at all but connections coming in on this
Mac; it starts no other program, sends no Apple events (cannot steer MoneyMoney or a browser), opens nothing through the system,
writes only temporary files and reads nothing in your home folder but its own folder -- so not Kontor's data, not MoneyMoney's,
no documents. That sandbox is a second line behind llama.cpp itself (should the program or a model file ever be faulty); which
rules apply is your setting -- nothing the process does makes Kontor try weaker ones. Kontor talks to it at 127.0.0.1 and
nowhere else (there is no address to set). It ends when you stop it, after some idle minutes, and when Kontor restarts.

Nothing here knows your figures: what the model is asked and may do is in assistant.py.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import logging
import os
import platform
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections import deque
from datetime import datetime
from typing import Any, Callable, Dict, Iterator, List, Optional
from urllib.parse import quote, urlparse

from i18n import tr

log = logging.getLogger("kontor.assistant")

GITHUB, HF = "github", "hf"
RUNTIME_REPO = "ggml-org/llama.cpp"
# the newest releases, not ".../releases/latest": llama.cpp publishes its builds as pre-releases, and "latest" is only the newest
# full release -- one without any build (v0.7.0, only "nightly-tag.txt")
RELEASES_URL = "https://api.github.com/repos/%s/releases?per_page=10" % RUNTIME_REPO
REPO_RE = re.compile(r"[A-Za-z0-9][\w.\-]{0,95}/[A-Za-z0-9][\w.\-]{0,95}")
FILE_RE = re.compile(r"[A-Za-z0-9][\w.\-]{0,180}\.gguf")
SHA_RE = re.compile(r"[0-9a-f]{64}")
MAX_RUNTIME = 2 << 30               # an unpacked llama.cpp is far smaller: more than this is refused
START_SECONDS = 420                 # a large model from a slow disk
REACH_SECONDS = 45                  # llama-server listens (and says "loading") long before the model is there
SANDBOX = "/usr/bin/sandbox-exec"

# Models Kontor names (they change with Kontor's versions); any other GGUF from Hugging Face can be added by its repository.
# pick: the variant in that repository (its file is looked up there when you load it); gb: about, for the list before loading.
# The models offered, largest first (all GGUF, one file, free licences). "pick": the variant wanted, then what to take if the
# repository names it differently; "gb": about the size of that file; "ram": from how many GB of memory of the Mac it runs well
# beside macOS, MoneyMoney and a browser. Kontor suggests the first one that fits this Mac.
CATALOG: List[Dict[str, Any]] = [
    {"id": "qwen3.6-35b-a3b", "name": "Qwen3.6 35B-A3B", "repo": "unsloth/Qwen3.6-35B-A3B-GGUF", "pick": ["UD-Q4_K_M", "UD-Q4_K_XL"], "gb": 22, "ram": 48, "note": "large"},
    {"id": "qwen3.6-35b-a3b-compact", "name": "Qwen3.6 35B-A3B Compact", "repo": "unsloth/Qwen3.6-35B-A3B-GGUF", "pick": ["UD-IQ4_XS", "UD-Q3_K_XL"], "gb": 18, "ram": 32, "note": "compact"},
    {"id": "gemma-4-26b-a4b", "name": "Gemma 4 26B-A4B", "repo": "unsloth/gemma-4-26B-A4B-it-GGUF", "pick": ["UD-Q4_K_M", "UD-Q4_K_XL"], "gb": 17, "ram": 32, "note": "alternative"},
    {"id": "qwen3.8-27b", "name": "Qwen3.8 27B", "repo": "unsloth/Qwen3.8-27B-GGUF", "pick": ["Q4_K_M", "UD-Q4_K_XL"], "gb": 15, "ram": 32, "note": "thorough"},
    {"id": "gemma-4-12b", "name": "Gemma 4 12B", "repo": "unsloth/gemma-4-12b-it-GGUF", "pick": ["UD-Q4_K_XL", "Q4_K_M"], "gb": 8, "ram": 24, "note": "medium"},
    {"id": "qwen3.5-9b", "name": "Qwen3.5 9B", "repo": "unsloth/Qwen3.5-9B-GGUF", "pick": ["Q4_K_M", "UD-Q4_K_XL"], "gb": 6, "ram": 16, "note": "small"},
    {"id": "qwen3.5-4b", "name": "Qwen3.5 4B", "repo": "bartowski/Qwen_Qwen3.5-4B-GGUF", "pick": ["Q4_K_M"], "gb": 3, "ram": 8, "note": "tiny"},
]
# For dictating: models that only write down what is said (speech recognition). llama.cpp runs them like any other model,
# with their audio part (a second file, "mmproj-...") beside them -- on this Mac, without a network, in the same sandbox.
SPEECH: List[Dict[str, Any]] = [
    {"id": "qwen3-asr-1.7b", "name": "Qwen3-ASR 1.7B", "repo": "ggml-org/Qwen3-ASR-1.7B-GGUF", "pick": ["Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "F16", "BF16"], "gb": 3, "note": "speech"},
    {"id": "qwen3-asr-0.6b", "name": "Qwen3-ASR 0.6B", "repo": "ggml-org/Qwen3-ASR-0.6B-GGUF", "pick": ["Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "F16", "BF16"], "gb": 1, "note": "speech_small"},
]
SPEECH_IDS = tuple(c["id"] for c in SPEECH)
SPEECH_CONTEXT = 8192    # a few minutes of speech and their text
MAX_AUDIO = 6 * 1024 * 1024          # bytes of one recording (WAV, 16 kHz, mono: about three minutes)
HEADROOM_GB = 2          # beside the file: the conversation in memory and the program itself


def physical_ram() -> int:
    """The memory of this machine in bytes (0: unknown)."""
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return 0


def fit(gb: float, ram_from: Optional[int], ram: int) -> str:
    """How a model of this size sits in this Mac's memory: "good" (runs beside everything else), "tight" (runs, with little
    else open -- up to about three quarters of the memory, what macOS gives the graphics chip), "big" (will swap or not load).
    Unknown memory: "good" (nothing is claimed)."""
    if not ram:
        return "good"
    have = ram / 2 ** 30
    if (have + 0.5 >= ram_from) if ram_from else (gb + HEADROOM_GB <= have * 0.6):
        return "good"
    return "tight" if gb + HEADROOM_GB <= have * 0.75 else "big"


def recommended(ram: int) -> str:
    """The model of the list for this Mac: the first (largest) that runs well; with less memory than any needs, the smallest.
    Unknown memory: none."""
    if not ram:
        return ""
    return next((c["id"] for c in CATALOG if fit(c["gb"], c["ram"], ram) == "good"), CATALOG[-1]["id"])


class Cancelled(Exception):
    pass


class ModelError(Exception):
    """The model did not start or did not answer (its text is for the user)."""


def host_allowed(url: str, kind: str) -> bool:
    """HTTPS to GitHub (llama.cpp) or Hugging Face (model files) and their download hosts -- nothing else."""
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host or u.username or u.password:
        return False
    if kind == GITHUB:
        return host in ("api.github.com", "github.com") or host.endswith(".githubusercontent.com")
    if kind == HF:
        return host == "huggingface.co" or host.endswith(".huggingface.co") or host.endswith(".hf.co")
    return False


class _Checked(urllib.request.HTTPRedirectHandler):
    """Every hop of a redirect stays on the allowed hosts."""

    def __init__(self, kind: str):
        self.kind = kind

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_allowed(newurl, self.kind):
            raise ValueError(tr("s_umleitung_auf_fremden_host_s") % urlparse(newurl).netloc)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, kind: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30):
    """The only way out of this module (tests replace it): a GET, nothing is sent but the address."""
    if not host_allowed(url, kind):
        raise ValueError(tr("s_adresse_nicht_erlaubt_s") % url)
    opener = urllib.request.build_opener(_Checked(kind))
    req = urllib.request.Request(url, headers=dict({"User-Agent": "Kontor"}, **(headers or {})))
    log.info("Assistant download: GET %s", url.split("?")[0])
    return opener.open(req, timeout=timeout)


def _json_get(url: str, kind: str) -> Any:
    with _open(url, kind, {"Accept": "application/json"}) as r:
        return json.loads(r.read(8 << 20).decode("utf-8")), r.headers


def asset_tag() -> str:
    """Which build of llama.cpp fits this machine (the name its release files carry)."""
    arm = platform.machine().lower() in ("arm64", "aarch64")
    if sys.platform == "darwin":
        if not arm:                       # a Python running translated (Rosetta) on Apple silicon still gets the build for the chip
            try:
                arm = subprocess.run(["/usr/sbin/sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True, timeout=5).stdout.strip() == "1"
            except (OSError, subprocess.SubprocessError):
                pass
        return "macos-arm64" if arm else "macos-x64"
    return "ubuntu-arm64" if arm else "ubuntu-x64"


def pick_asset(release: dict) -> Optional[dict]:
    want = "-bin-" + asset_tag()
    for a in release.get("assets") or []:
        name = str(a.get("name") or "")
        if name.startswith("llama-") and (name.endswith(want + ".tar.gz") or name.endswith(want + ".zip")):
            dig = str(a.get("digest") or "")
            return {"name": name, "url": str(a.get("browser_download_url") or ""), "size": int(a.get("size") or 0),
                    "sha256": dig[7:].lower() if dig.startswith("sha256:") and SHA_RE.fullmatch(dig[7:].lower()) else ""}
    return None


def resolve_pick(files: List[dict], pick: Any) -> Optional[dict]:
    """The file of a variant (e.g. UD-Q4_K_M) among a repository's model files; of several variants the first there is."""
    for p in ([pick] if isinstance(pick, str) else list(pick)):
        p = p.lower()
        hits = [f for f in files if re.search(r"[-.]%s\.gguf$" % re.escape(p), f["file"].lower())]
        if hits:
            return min(hits, key=lambda f: len(f["file"]))        # "…-Q4_K_M.gguf" before "…-UD-Q4_K_M.gguf"
    return None


# The sandbox the model runs in is your choice (Einstellungen -> Assistent), never the model's: nothing its process does -- not
# starting, crashing, not answering -- makes Kontor try weaker rules. Every level but "off": no network connection of its own.
SANDBOXES = ("strict", "basic", "off")


def sandbox_profile(data_dir: str, program_dir: str, base_dir: str, level: str = "strict", home: Optional[str] = None) -> str:
    """The rules for sandbox-exec (later rules win).
    Both levels: no network but connections coming in on this Mac -- none going out at all; nothing written into Kontor's
    folders; Kontor's data not read (only the model's own folder inside it).
    strict: besides that it starts no other program, sends no Apple events (so it cannot steer MoneyMoney, a browser or any
    other app), opens nothing through the system (no addresses, no files), signals no other process, does not read the
    clipboard, writes temporary files only and reads nothing in the home folder."""
    q = lambda p: json.dumps(os.path.realpath(p), ensure_ascii=False)
    rules = ["(version 1)", "(allow default)", "(deny network*)",
             '(allow network-bind (local ip "localhost:*"))', '(allow network-inbound (local ip "localhost:*"))']
    if level == "strict":
        rules += ["(deny process-exec*)", "(allow process-exec* (subpath %s))" % q(os.path.join(base_dir, "runtime")),
                  "(deny appleevent-send)", "(deny lsopen)",
                  "(deny signal)", "(allow signal (target self))",
                  '(deny mach-lookup (global-name "com.apple.pasteboard.1"))',
                  "(deny file-write*)",
                  '(allow file-write* (subpath "/private/var/folders") (subpath "/private/tmp") (literal "/dev/null") (literal "/dev/dtracehelper") (literal "/dev/tty"))',
                  "(deny file-read* (subpath %s) (subpath %s))" % (q(home or os.path.expanduser("~")), q(data_dir))]
    else:
        rules += ["(deny file-write* (subpath %s) (subpath %s))" % (q(data_dir), q(program_dir)), "(deny file-read* (subpath %s))" % q(data_dir)]
    return "\n".join(rules + ["(allow file-read* (subpath %s))" % q(base_dir), "(allow file-read-metadata (vnode-type DIRECTORY))"])


def _safe_join(root: str, name: str) -> Optional[str]:
    name = name.replace("\\", "/")
    if name.startswith("/") or any(p == ".." for p in name.split("/")):
        return None
    full = os.path.normpath(os.path.join(root, name))
    return full if full == root or full.startswith(root.rstrip(os.sep) + os.sep) else None


def unpack(archive: str, dest: str) -> None:
    """Unpacks a release of llama.cpp into dest: plain files, folders and links that stay inside -- nothing else, nothing
    outside, not more than MAX_RUNTIME."""
    os.makedirs(dest, exist_ok=True)
    root, total = os.path.realpath(dest), 0
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                target = _safe_join(root, info.filename)
                if target is None:
                    raise ValueError(tr("s_ki_archiv_unsicher"))
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                total += info.file_size
                if total > MAX_RUNTIME:
                    raise ValueError(tr("s_ki_archiv_unsicher"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                os.chmod(target, 0o755 if (info.external_attr >> 16) & 0o111 else 0o644)
        return
    links = []
    with tarfile.open(archive, "r:*") as tar:
        for m in tar:
            target = _safe_join(root, m.name)
            if target is None:
                raise ValueError(tr("s_ki_archiv_unsicher"))
            if m.isdir():
                os.makedirs(target, exist_ok=True)
            elif m.isreg():
                total += m.size
                if total > MAX_RUNTIME:
                    raise ValueError(tr("s_ki_archiv_unsicher"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                src = tar.extractfile(m)
                with open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                os.chmod(target, 0o755 if m.mode & 0o111 else 0o644)
            elif m.issym():
                links.append((target, m.linkname))
            # anything else (devices, hard links): left out
    for target, link in links:                       # a link: only to something inside (e.g. libllama.dylib -> libllama.0.dylib)
        if os.path.isabs(link) or _safe_join(root, os.path.relpath(os.path.join(os.path.dirname(target), link), root)) is None:
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.lexists(target):
            os.remove(target)
        os.symlink(link, target)
    for target, _ in links:                          # ... also where it really ends (a link through another link)
        if os.path.islink(target) and not (os.path.realpath(target) + os.sep).startswith(root + os.sep):
            os.remove(target)


class LocalAI:
    """llama.cpp and the models in one folder (base_dir), and the one running model."""

    def __init__(self, base_dir: str, data_dir: str, program_dir: str, role: str = "server"):
        """role: "server" for the model that answers, "speech" for the one that writes down what is dictated -- two processes
        of the same program, each kept track of in a file of its own."""
        self.base, self.data_dir, self.program_dir, self.role = base_dir, data_dir, program_dir, role
        self.lock = threading.RLock()
        self.job: Optional[dict] = None                # a download in progress (or its end)
        self.news: dict = {}                           # the last look for newer versions (on your click)
        self.proc: Optional[subprocess.Popen] = None
        self.port = 0
        self.key = ""
        self.model = ""
        self.ctx = 0
        self.state = "stopped"                         # stopped | starting | ready | error
        self.error = ""
        self.sealed = ""                               # "" | "strict" | "basic": the sandbox the running model is in
        self.since: Optional[float] = None
        self.last_used = 0.0
        self.busy = False
        self.tps: Optional[float] = None
        self.tail: deque = deque(maxlen=40)
        self._conn: Optional[http.client.HTTPConnection] = None
        self._halt = threading.Event()                 # "stop" while a start is waiting for the model
        self.on_loaded: Optional[Callable[[str], None]] = None     # a model file has arrived (its id)
        self.on_change: Optional[Callable[[str], None]] = None     # files are about to be replaced or removed: a model's (its id) or the program's ("")
        self._stale()

    # -- files --------------------------------------------------------------------------------------------------------
    def _p(self, *parts: str) -> str:
        return os.path.join(self.base, *parts)

    def _load(self, name: str) -> dict:
        try:
            with open(self._p(name), encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, name: str, data: dict) -> None:
        os.makedirs(self.base, exist_ok=True)
        tmp = self._p(name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._p(name))

    def runtime(self) -> dict:
        """The installed llama.cpp: {} or {"tag", "bin", "version", "flags", "installed"} (bin exists)."""
        r = self._load("runtime.json")
        b = self._p("runtime", str(r.get("dir") or ""), str(r.get("bin") or "")) if r.get("dir") and r.get("bin") else ""
        inside = os.path.realpath(b).startswith(os.path.realpath(self._p("runtime")) + os.sep) if b else False    # only ever a program in its own folder
        return dict(r, path=b) if inside and os.path.isfile(b) and os.path.basename(b) == "llama-server" else {}

    def models(self) -> Dict[str, dict]:
        """The model files on this Mac: id -> {"repo", "file", "size", "sha256", "name", "path"} (files that exist)."""
        out = {}
        for mid, m in (self._load("models.json").get("models") or {}).items():
            if not isinstance(m, dict) or not REPO_RE.fullmatch(str(m.get("repo") or "")) or not FILE_RE.fullmatch(str(m.get("file") or "")):
                continue
            path = self.model_path(m["repo"], m["file"])
            if not os.path.isfile(path):
                continue
            pj = m.get("mmproj") if isinstance(m.get("mmproj"), dict) else None       # a speech model's audio part: a second file beside it
            if pj is not None:
                if not FILE_RE.fullmatch(str(pj.get("file") or "")) or not os.path.isfile(self.model_path(m["repo"], pj["file"])):
                    continue
                out[str(mid)] = dict(m, path=path, mmproj_path=self.model_path(m["repo"], pj["file"]))
            else:
                out[str(mid)] = dict(m, path=path)
        return out

    def model_path(self, repo: str, file: str) -> str:
        return self._p("models", repo.replace("/", "--"), file)

    # -- looking for newer versions and loading (network, on your click only) ----------------------------------------------
    def latest_runtime(self) -> dict:
        """The newest published release (pre-releases included, drafts not) with a build for this machine."""
        rels, _ = _json_get(RELEASES_URL, GITHUB)
        for rel in rels if isinstance(rels, list) else []:
            if not isinstance(rel, dict) or rel.get("draft"):
                continue
            a = pick_asset(rel)
            if a:                             # the newest build it is -- one from another address is refused, not swapped for an older one
                if not host_allowed(a["url"], GITHUB):
                    break
                return dict(a, tag=str(rel.get("tag_name") or "")[:40])
        raise ValueError(tr("s_ki_kein_build") % asset_tag())

    def repo_files(self, repo: str, projectors: bool = False) -> List[dict]:
        """The model files (GGUF, one file each) of a repository at Hugging Face: [{"file", "size", "sha256"}].
        projectors: instead the audio/vision parts that belong to them ("mmproj-...")."""
        if not REPO_RE.fullmatch(repo or ""):
            raise ValueError(tr("s_ki_repo_ungueltig"))
        out: List[dict] = []
        url: Optional[str] = "https://huggingface.co/api/models/%s/tree/main" % quote(repo, safe="/")
        for _ in range(6):                          # a few pages at most
            if not url:
                break
            data, headers = _json_get(url, HF)
            for f in data if isinstance(data, list) else []:
                name = str(f.get("path") or "")
                if f.get("type") != "file" or not FILE_RE.fullmatch(name) or name.lower().startswith("mtp-") or re.search(r"-\d{5}-of-\d{5}\.gguf$", name):
                    continue
                if name.lower().startswith("mmproj") != projectors:
                    continue
                lfs = f.get("lfs") if isinstance(f.get("lfs"), dict) else {}
                sha = str(lfs.get("oid") or "").lower()
                out.append({"file": name, "size": int(lfs.get("size") or f.get("size") or 0), "sha256": sha if SHA_RE.fullmatch(sha) else ""})
            m = re.search(r'<([^>]+)>;\s*rel="next"', str(headers.get("Link") or ""))
            url = m.group(1) if m and host_allowed(m.group(1), HF) else None
        return sorted(out, key=lambda f: f["size"])

    def check(self) -> dict:
        """Looks for a newer llama.cpp and newer files of the loaded models (network: GitHub and Hugging Face)."""
        news: dict = {"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "models": {}}
        try:
            lr = self.latest_runtime()
            news["runtime"] = {"tag": lr["tag"], "newer": lr["tag"] != (self.runtime().get("tag") or "")}
        except Exception as e:
            news["error"] = str(e)[:300]
        cat = {c["id"]: c for c in CATALOG + SPEECH}
        for mid, m in self.models().items():
            try:
                files = self.repo_files(m["repo"])
                f = resolve_pick(files, cat[mid]["pick"]) if mid in cat else next((x for x in files if x["file"] == m["file"]), None)
                if f and f["sha256"] and m.get("sha256"):
                    news["models"][mid] = {"newer": f["sha256"] != m["sha256"], "size": f["size"]}
            except Exception as e:
                news.setdefault("error", str(e)[:300])
        self.news = news
        return news

    def _start_job(self, kind: str, ident: str, label: str, fn: Callable[[dict], None]) -> dict:
        with self.lock:
            if self.job and self.job.get("state") == "running":
                raise ValueError(tr("s_ki_laedt_schon"))
            job = {"kind": kind, "id": ident, "label": label, "done": 0, "total": 0, "state": "running", "text": "",
                   "started": time.time(), "cancel": threading.Event()}
            self.job = job

        def run():
            try:
                fn(job)
                job["state"] = "done"
                log.info("Assistant: %s %s loaded", kind, label)
            except Cancelled:
                job["state"] = "cancelled"
            except Exception as e:
                text = tr("s_ki_netz") % str(e.reason)[:200] if isinstance(e, urllib.error.URLError) and not isinstance(e, urllib.error.HTTPError) else str(e)[:400]
                job.update(state="error", text=text)
                log.warning("Assistant: %s %s not loaded: %s", kind, label, str(e)[:300])
        threading.Thread(target=run, name="kontor-ai-load", daemon=True).start()
        return self.job_view()

    def job_view(self) -> Optional[dict]:
        j = self.job
        return {k: j[k] for k in ("kind", "id", "label", "done", "total", "state", "text")} | {"seconds": round(time.time() - j["started"], 1)} if j else None

    def cancel_job(self) -> None:
        if self.job:
            self.job["cancel"].set()

    def _fetch(self, url: str, kind: str, dest: str, total: int, sha256: str, job: dict) -> str:
        """Loads url into dest (via dest.part, going on where an earlier try stopped); the size and the SHA-256 the source
        names must fit -- a file without a SHA-256 is not loaded at all. Returns the SHA-256 of the file."""
        if not SHA_RE.fullmatch(sha256 or ""):             # nothing is installed or run that cannot be checked
            raise ValueError(tr("s_ki_keine_pruefsumme"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        self._no_backup()
        part = dest + ".part"
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if total and have > total:
            os.remove(part)
            have = 0
        free = shutil.disk_usage(os.path.dirname(dest)).free
        if total and free < total - have + (1 << 30):
            raise ValueError(tr("s_ki_platz_fehlt") % ("%.0f" % ((total - have) / 1e9 + 1), "%.0f" % (free / 1e9)))
        job.update(done=have, total=total)
        h = hashlib.sha256()
        if have:                                          # what is there already counts into the check
            with open(part, "rb") as f:
                for chunk in iter(lambda: f.read(4 << 20), b""):
                    if job["cancel"].is_set():
                        raise Cancelled()
                    h.update(chunk)
        if not (total and have == total):
            try:
                r = _open(url, kind, {"Range": "bytes=%d-" % have} if have else None, timeout=60)
            except urllib.error.HTTPError as e:
                raise ValueError(tr("s_download_fehlgeschlagen") % (e.code, e.reason))
            with r:
                if have and getattr(r, "status", 200) != 206:   # the server starts over: so do we
                    have, h = 0, hashlib.sha256()
                    job["done"] = 0
                with open(part, "ab" if have else "wb") as out:
                    while True:
                        if job["cancel"].is_set():
                            raise Cancelled()
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                        h.update(chunk)
                        job["done"] += len(chunk)
        got = h.hexdigest()
        size = os.path.getsize(part)
        if (total and size != total) or got != sha256:
            os.remove(part)                               # not what was announced: nothing of it stays
            raise ValueError(tr("s_ki_pruefsumme"))
        os.replace(part, dest)
        return got

    def _no_backup(self) -> None:
        """Programs and models can be loaded again any time: Time Machine leaves this folder out (many gigabytes)."""
        if sys.platform == "darwin" and not getattr(self, "_excluded", False):
            self._excluded = True
            try:
                subprocess.run(["tmutil", "addexclusion", self.base], capture_output=True, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def install_runtime(self, sandbox: str = "strict") -> dict:
        """llama.cpp's newest release for this machine: loaded, checked, unpacked, tried (--version inside the sandbox)."""
        def work(job: dict) -> None:
            a = self.latest_runtime()
            job["label"] = a["tag"]
            tag = re.sub(r"[^\w.\-]", "_", a["tag"]) or "release"
            rdir = self._p("runtime")
            arch = os.path.join(rdir, a["name"])
            sha = self._fetch(a["url"], GITHUB, arch, a["size"], a["sha256"], job)
            tmp = os.path.join(rdir, tag + ".tmp")
            shutil.rmtree(tmp, ignore_errors=True)
            try:
                unpack(arch, tmp)
                rel = next((os.path.relpath(os.path.join(d, "llama-server"), tmp) for d, _, fs in os.walk(tmp) if "llama-server" in fs), None)
                if rel is None:
                    raise ValueError(tr("s_ki_archiv_unsicher"))
            except Exception:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
            finally:
                try:
                    os.remove(arch)
                except OSError:
                    pass
            try:
                version, flags = self._probe(os.path.join(tmp, rel), sandbox)   # a build that does not start here is not kept (the old one stays)
            except Exception:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
            self._changing("")
            final = os.path.join(rdir, tag)
            shutil.rmtree(final, ignore_errors=True)
            os.replace(tmp, final)
            self._save("runtime.json", {"tag": a["tag"], "dir": tag, "bin": rel, "version": version, "flags": flags, "sha256": sha,
                                        "installed": datetime.now().strftime("%Y-%m-%d %H:%M")})
            for name in os.listdir(rdir):                   # older versions go
                if name != tag:
                    full = os.path.join(rdir, name)
                    shutil.rmtree(full, ignore_errors=True) if os.path.isdir(full) and not os.path.islink(full) else os.remove(full)
            self.news.pop("runtime", None)
        return self._start_job("runtime", "llama.cpp", "llama.cpp", work)

    def _probe(self, binp: str, level: str = "strict") -> tuple:
        """Version and options of a llama-server (run inside the sandbox where there is one): a build that does not start
        here is not kept."""
        if level != "off" and not self._can_seal() and sys.platform == "darwin":
            raise ModelError(tr("s_ki_sandbox_fehlt"))          # as at the start: the sandbox asked for but not there -- not run without it

        def run(arg: str) -> str:
            cmd = self._sealed_cmd([binp, arg], level) if level != "off" and self._can_seal() else [binp, arg]      # inside the sandbox you chose
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=self._env(""), cwd=os.path.dirname(binp))
            return (r.stdout or "") + (r.stderr or "")
        try:
            ver = run("--version")
            m = re.search(r"version:\s*([^\n]+)", ver)
            flags = sorted(set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]+", run("--help"))))
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ValueError(tr("s_ki_startet_nicht") % str(e)[:200])
        if "--port" not in flags or "--model" not in flags:
            raise ValueError(tr("s_ki_startet_nicht") % (ver.strip()[:200] or "llama-server"))
        return (m.group(1).strip()[:60] if m else ""), flags

    def remove_runtime(self) -> None:
        self._changing("")
        shutil.rmtree(self._p("runtime"), ignore_errors=True)
        try:
            os.remove(self._p("runtime.json"))
        except OSError:
            pass

    def download_model(self, model_id: str = "", repo: str = "", file: str = "") -> dict:
        """A model from the list (model_id) or any model file of a repository at Hugging Face (repo, file)."""
        entry = next((c for c in CATALOG + SPEECH if c["id"] == model_id), None)
        if entry is None:
            if not REPO_RE.fullmatch(repo or "") or not FILE_RE.fullmatch(file or ""):
                raise ValueError(tr("s_ki_repo_ungueltig"))
            model_id, name = "%s/%s" % (repo, file), file[:-5]
        else:
            repo, name = entry["repo"], entry["name"]

        def work(job: dict) -> None:
            files = self.repo_files(repo)
            f = resolve_pick(files, entry["pick"]) if entry else next((x for x in files if x["file"] == file), None)
            if f is None:
                raise ValueError(tr("s_ki_datei_fehlt"))
            address = lambda name_: "https://huggingface.co/%s/resolve/main/%s?download=true" % (quote(repo, safe="/"), quote(name_))
            part = None
            if entry is not None and entry["id"] in SPEECH_IDS:     # a speech model: its audio part first (small), then the model
                parts = self.repo_files(repo, projectors=True)
                tag = f["file"].rsplit("-", 1)[-1].lower()
                part = next((x for x in parts if x["file"].lower().endswith(tag)), None) or (min(parts, key=lambda x: x["size"]) if parts else None)
                if part is None:
                    raise ValueError(tr("s_ki_datei_fehlt"))
                part = dict(part, sha256=self._fetch(address(part["file"]), HF, self.model_path(repo, part["file"]), part["size"], part["sha256"], job))
            dest = self.model_path(repo, f["file"])
            try:
                sha = self._fetch(address(f["file"]), HF, dest, f["size"], f["sha256"], job)
            except BaseException:
                known = ((self._load("models.json").get("models") or {}).get(model_id) or {}).get("mmproj") or {}
                if part and known.get("file") != part["file"]:      # the audio part alone is of no use: it goes again (the model's
                    try:                                            # own partial file stays, the download goes on from there)
                        os.remove(self.model_path(repo, part["file"]))
                    except OSError:
                        pass
                raise
            self._changing(model_id)                       # a newer file of a running model: loaded at the next question
            data = self._load("models.json")
            old = (data.get("models") or {}).get(model_id) or {}
            data.setdefault("models", {})[model_id] = dict({"repo": repo, "file": f["file"], "size": f["size"], "sha256": sha, "name": name,
                                                            "downloaded": datetime.now().strftime("%Y-%m-%d %H:%M")},
                                                           **({"mmproj": {"file": part["file"], "size": part["size"], "sha256": part["sha256"]}} if part else {}))
            self._save("models.json", data)
            gone = [old.get("file") if old.get("file") != f["file"] else None,
                    (old.get("mmproj") or {}).get("file") if part and (old.get("mmproj") or {}).get("file") != part["file"] else None]
            for name_ in gone:                             # the variant got another file name: the old file goes
                if name_ and FILE_RE.fullmatch(str(name_)):
                    try:
                        os.remove(self.model_path(repo, name_))
                    except OSError:
                        pass
            (self.news.get("models") or {}).pop(model_id, None)
            if self.on_loaded is not None:
                self.on_loaded(model_id)
        return self._start_job("model", model_id, name, work)

    def _changing(self, model_id: str) -> None:
        """Files are about to be replaced or removed -- a model's, or the program's (""): whatever runs on them ends first,
        here and in the process beside this one (on_change)."""
        if not model_id or self.model == model_id:
            self.stop()
        if self.on_change is not None:
            self.on_change(model_id)

    def delete_model(self, model_id: str) -> None:
        data = self._load("models.json")
        m = (data.get("models") or {}).pop(model_id, None)
        if not m:
            return
        self._changing(model_id)
        if REPO_RE.fullmatch(str(m.get("repo") or "")) and FILE_RE.fullmatch(str(m.get("file") or "")):
            path = self.model_path(m["repo"], m["file"])
            pj = str((m.get("mmproj") or {}).get("file") or "") if isinstance(m.get("mmproj"), dict) else ""
            more = [self.model_path(m["repo"], pj), self.model_path(m["repo"], pj) + ".part"] if FILE_RE.fullmatch(pj) else []
            for p in [path, path + ".part"] + more:
                try:
                    os.remove(p)
                except OSError:
                    pass
            try:
                os.rmdir(os.path.dirname(path))
            except OSError:
                pass
        self._save("models.json", data)

    # -- the running model ------------------------------------------------------------------------------------------------
    def _can_seal(self) -> bool:
        return sys.platform == "darwin" and os.path.exists(SANDBOX)

    def _sealed_cmd(self, cmd: List[str], level: str = "strict") -> List[str]:
        return [SANDBOX, "-p", sandbox_profile(self.data_dir, self.program_dir, self.base, level)] + cmd

    def _env(self, key: str) -> Dict[str, str]:
        """A small environment of its own: no proxies, no tokens, nothing of Kontor's."""
        env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.path.expanduser("~"), "LANG": "en_US.UTF-8",
               "HF_HUB_OFFLINE": "1", "LLAMA_ARG_OFFLINE": "1"}
        if os.environ.get("TMPDIR"):
            env["TMPDIR"] = os.environ["TMPDIR"]
        if key:
            env["LLAMA_API_KEY"] = key
        return env

    def _stale(self) -> None:
        """A model left over from before a restart of Kontor (its own, by its path): ended."""
        info = self._load(self.role + ".json")
        pid = info.get("pid")
        if isinstance(pid, int) and pid > 1:
            try:
                cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=10).stdout
                rt = self._p("runtime")
                if "llama-server" in cmd and (rt in cmd or os.path.realpath(rt) in cmd):
                    os.kill(pid, signal.SIGTERM)
                    log.info("Assistant: model left running by an earlier start ended")
            except (OSError, subprocess.TimeoutExpired):
                pass
        try:
            os.remove(self._p(self.role + ".json"))
        except OSError:
            pass

    def _spawn(self, binp: str, flags: List[str], model_path: str, ctx: int, seal: str, extra: Optional[List[str]] = None) -> subprocess.Popen:
        """seal: "" = not in a sandbox, else its level ("strict" | "basic"). extra: further arguments (a model's audio part)."""
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        key = secrets.token_urlsafe(32)
        args = [binp, "--model", model_path, "--host", "127.0.0.1", "--port", str(port), "--ctx-size", str(ctx), "--parallel", "1"] + list(extra or [])
        for flag in ("--no-webui", "--offline", "--jinja", "--no-slots"):     # only what this build knows
            if flag in flags:
                args.append(flag)
        if "--no-webui" not in flags and "--no-ui" in flags:
            args.append("--no-ui")
        cmd = self._sealed_cmd(args, seal) if seal else args
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=self._env(key),
                                cwd=os.path.dirname(binp), close_fds=True)
        self.port, self.key = port, key

        def drain(p=proc):                                # its output: only the last lines, in memory, for a failed start
            try:
                for raw in p.stdout:
                    line = raw.decode("utf-8", "replace").rstrip()[:300]
                    if "api_key" not in line.lower() and key not in line:      # nothing about the key, not even its end
                        self.tail.append(line)
            except (OSError, ValueError):
                pass
        threading.Thread(target=drain, name="kontor-ai-out", daemon=True).start()
        return proc

    def _healthy(self) -> Optional[bool]:
        """True: ready; False: still loading; None: not reachable."""
        try:
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
            c.request("GET", "/health")
            r = c.getresponse()
            r.read()
            c.close()
            return r.status == 200
        except (OSError, http.client.HTTPException):
            return None

    def ensure(self, model_id: str, ctx: int, sandbox: str = "strict", cancel: Optional[threading.Event] = None) -> None:
        """The model runs and is ready (started if needed; another model, context size or sandbox: started anew).
        sandbox: "strict" | "basic" | "off" -- exactly that, or no start at all."""
        sandbox = sandbox if sandbox in SANDBOXES else "strict"
        with self.lock:
            seal = "" if sandbox == "off" or (not self._can_seal() and sys.platform != "darwin") else sandbox     # (not a Mac: there is no sandbox-exec)
            if self.proc is not None and self.proc.poll() is None and self.state == "ready" and (self.model, self.ctx, self.sealed) == (model_id, ctx, seal):
                self.last_used = time.time()
                return
            rt, m = self.runtime(), self.models().get(model_id)
            if not rt:
                raise ModelError(tr("s_ki_nicht_installiert"))
            if not m:
                raise ModelError(tr("s_ki_modell_fehlt"))
            ram = physical_ram()
            if ram and int(m.get("size") or 0) + 2 ** 30 > ram:        # larger than the memory itself: it would only swap, the Mac with it
                raise ModelError(tr("s_ki_passt_nicht") % (round(m["size"] / 1e9), round(ram / 2 ** 30)))
            self.stop()
            if seal and not self._can_seal():
                raise ModelError(tr("s_ki_sandbox_fehlt"))
            self.state, self.error, self.model, self.ctx = "starting", "", model_id, ctx
            self.tail.clear()
            try:
                self.proc = self._spawn(rt["path"], rt.get("flags") or [], m["path"], ctx, seal, ["--mmproj", m["mmproj_path"]] if m.get("mmproj_path") else None)
            except OSError as e:
                self.state, self.error = "error", str(e)[:300]
                raise ModelError(tr("s_ki_startet_nicht") % self.error)
            self.sealed = seal
            self._save(self.role + ".json", {"pid": self.proc.pid})
            t0, reached = time.time(), False
            while True:
                if self._halt.is_set() or (cancel is not None and cancel.is_set()):
                    self._kill()
                    self.state, self.since, self.sealed = "stopped", None, ""
                    raise Cancelled()
                if self.proc.poll() is not None:
                    break
                h = self._healthy()
                if h:
                    self.state, self.since, self.last_used = "ready", time.time(), time.time()
                    log.info("Assistant: model %s ready after %.0f s (sandbox: %s)", model_id, time.time() - t0, self.sealed or "off")
                    return
                reached = reached or h is False                  # it answers "still loading": Kontor reaches it
                if time.time() - t0 > (START_SECONDS if reached else REACH_SECONDS):
                    break
                time.sleep(0.3)
            why = " | ".join(list(self.tail)[-4:])[:500] or "llama-server"
            self._kill()
            self.state, self.sealed = "error", ""
            # never reached inside the sandbox: said so (the rules are yours to change, not tried weaker by itself)
            self.error = (tr("s_ki_sandbox_start") % why) if seal and not reached else why
            log.warning("Assistant: model did not start (sandbox: %s): %s", seal or "off", why[:300])
            raise ModelError(tr("s_ki_startet_nicht") % self.error)

    def _kill(self) -> None:
        p, self.proc = self.proc, None
        if p is not None and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    p.kill()
                except OSError:
                    pass
        try:
            os.remove(self._p(self.role + ".json"))
        except OSError:
            pass

    def stop(self) -> None:
        self._halt.set()                                 # a start that is waiting gives up (it holds the lock)
        self.abort()
        with self.lock:
            self._halt.clear()
            was = self.proc is not None
            self._kill()
            self.state, self.since, self.busy, self.sealed = "stopped", None, False, ""
            if was:
                log.info("Assistant: model stopped")

    def abort(self) -> None:
        """Ends the answer being written (the connection to the model is cut; it stops computing)."""
        c = self._conn
        sock = c.sock if c is not None else None
        if sock is not None:                              # only cut it: the thread that reads notices and closes it itself
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def chat(self, body: dict, cancel: threading.Event) -> Iterator[dict]:
        """One answer of the model as its stream of pieces (OpenAI's chat format). Only ever 127.0.0.1 and the port and
        key of the model Kontor started."""
        if self.state != "ready" or self.proc is None or self.proc.poll() is not None:
            raise ModelError(tr("s_ki_laeuft_nicht"))
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=900)
        self._conn, self.busy, self.last_used = conn, True, time.time()
        try:
            conn.request("POST", "/v1/chat/completions", json.dumps(body).encode("utf-8"),
                         {"Content-Type": "application/json", "Authorization": "Bearer " + self.key, "Accept": "text/event-stream"})
            resp = conn.getresponse()
            if resp.status != 200:
                raw = resp.read(4000).decode("utf-8", "replace")
                try:
                    msg = str((json.loads(raw).get("error") or {}).get("message") or raw)
                except ValueError:
                    msg = raw
                raise ModelError(msg[:300])
            for raw in resp:
                if cancel.is_set():
                    raise Cancelled()
                line = raw.strip()
                if not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    break
                try:
                    piece = json.loads(data)
                except ValueError:
                    continue
                if isinstance(piece, dict):
                    t = piece.get("timings")
                    if isinstance(t, dict) and t.get("predicted_per_second"):
                        self.tps = round(float(t["predicted_per_second"]), 1)
                    yield piece
            if cancel.is_set():                            # cut off: the stream just ends
                raise Cancelled()
        except (OSError, http.client.HTTPException, AttributeError, ValueError) as e:      # a connection cut while it is read fails in many ways
            if cancel.is_set():
                raise Cancelled()
            if isinstance(e, (AttributeError, ValueError)) and not isinstance(e, http.client.HTTPException):
                raise
            raise ModelError(tr("s_ki_antwortet_nicht") % str(e)[:200])
        finally:
            self._conn, self.busy, self.last_used = None, False, time.time()
            try:
                conn.close()
            except OSError:
                pass

    def transcribe(self, wav: bytes, language: str = "") -> str:
        """What is said in a recording (WAV), written down by the speech model that runs -- llama.cpp's /v1/audio/transcriptions,
        on 127.0.0.1 with this start's key."""
        if self.state != "ready" or self.proc is None or self.proc.poll() is not None:
            raise ModelError(tr("s_ki_laeuft_nicht"))
        mark = "kontor" + secrets.token_hex(12)
        field = lambda name, value: ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (mark, name, value)).encode("utf-8")
        body = (field("response_format", "json") + field("temperature", "0") + (field("language", language) if re.fullmatch(r"[a-z]{2}", language or "") else b"")
                + ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n" % mark).encode("utf-8") + wav
                + ("\r\n--%s--\r\n" % mark).encode("utf-8"))
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=300)
        self.busy, self.last_used = True, time.time()
        try:
            conn.request("POST", "/v1/audio/transcriptions", body, {"Content-Type": "multipart/form-data; boundary=" + mark, "Authorization": "Bearer " + self.key})
            resp = conn.getresponse()
            raw = resp.read(200000).decode("utf-8", "replace")
            try:
                data = json.loads(raw)
            except ValueError:
                data = {}
            if resp.status != 200 or not isinstance(data, dict):
                raise ModelError(str(((data.get("error") or {}) if isinstance(data, dict) else {}).get("message") or raw)[:300])
            return str(data.get("text") or "").strip()
        except (OSError, http.client.HTTPException) as e:
            raise ModelError(tr("s_ki_antwortet_nicht") % str(e)[:200])
        finally:
            self.busy, self.last_used = False, time.time()
            try:
                conn.close()
            except OSError:
                pass

    def idle_check(self, minutes: int) -> None:
        """Called now and then: a model nobody asked for a while is ended (its memory is free again)."""
        if self.proc is not None and not self.busy and self.state == "ready" and minutes > 0 and time.time() - self.last_used > minutes * 60:
            log.info("Assistant: model idle for %d min", minutes)
            self.stop()
        elif self.proc is not None and self.state == "ready" and self.proc.poll() is not None:
            self.stop()                                    # it ended by itself

    def usage(self) -> dict:
        p = self.proc
        if p is None or p.poll() is not None:
            return {}
        try:
            out = subprocess.run(["ps", "-o", "rss=,pcpu=", "-p", str(p.pid)], capture_output=True, text=True, timeout=5).stdout.split()
            return {"rss": int(out[0]) * 1024, "cpu": float(out[1].replace(",", "."))}
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            return {}

    def status(self) -> dict:
        rt, have, news = self.runtime(), self.models(), self.news
        ram = physical_ram()
        models = []
        for c in CATALOG:
            m = have.get(c["id"])
            models.append({"id": c["id"], "name": c["name"], "repo": c["repo"], "note": c["note"], "gb": c["gb"], "ram": c["ram"], "fit": fit(c["gb"], c["ram"], ram),
                           "installed": bool(m), "size": m["size"] if m else 0, "file": m["file"] if m else "", "custom": False,
                           "newer": bool(((news.get("models") or {}).get(c["id"]) or {}).get("newer"))})
        speech = [{"id": c["id"], "name": c["name"], "repo": c["repo"], "note": c["note"], "gb": c["gb"], "installed": c["id"] in have,
                   "size": (have[c["id"]]["size"] + int((have[c["id"]].get("mmproj") or {}).get("size") or 0)) if c["id"] in have else 0,
                   "file": have[c["id"]]["file"] if c["id"] in have else "", "newer": bool(((news.get("models") or {}).get(c["id"]) or {}).get("newer"))} for c in SPEECH]
        for mid, m in have.items():
            if mid in SPEECH_IDS:
                continue
            if not any(c["id"] == mid for c in CATALOG):
                models.append({"id": mid, "name": m.get("name") or m["file"], "repo": m["repo"], "note": "", "gb": 0, "ram": 0, "fit": fit(m["size"] / 1e9, None, ram),
                               "installed": True, "size": m["size"], "file": m["file"], "custom": True,
                               "newer": bool(((news.get("models") or {}).get(mid) or {}).get("newer"))})
        try:
            free = shutil.disk_usage(self.base if os.path.isdir(self.base) else self.data_dir).free
        except OSError:
            free = 0
        running = self.proc is not None and self.proc.poll() is None
        return {"platform": {"system": sys.platform, "build": asset_tag(), "ram": ram, "can_seal": self._can_seal()},
                "runtime": {"installed": bool(rt), "tag": rt.get("tag", ""), "version": rt.get("version", ""), "date": rt.get("installed", ""),
                            "latest": (news.get("runtime") or {}).get("tag", ""), "newer": bool((news.get("runtime") or {}).get("newer"))},
                "models": models, "speech": speech, "recommended": recommended(ram), "checked": news.get("at", ""), "check_error": news.get("error", ""),
                "server": dict({"state": self.state if running or self.state in ("error", "starting") else "stopped", "model": self.model if running else "",
                                "since": int(time.time() - self.since) if running and self.since else 0, "sealed": self.sealed if running else "",
                                "busy": self.busy, "error": self.error if self.state == "error" else "", "tps": self.tps, "context": self.ctx if running else 0},
                               **(self.usage() if running else {})),
                "job": self.job_view(), "disk_free": free}
