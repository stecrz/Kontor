"""The assistant's language model on this Mac: llama.cpp's server (llama-server) and model files (GGUF) -- installed, updated,
started and stopped by Kontor, only from Einstellungen -> Assistent, only on your click.

What goes over the network -- only on such a click, only downloads, HTTPS, fixed hosts:
  - llama.cpp from its releases on GitHub (api.github.com, github.com, *.githubusercontent.com), checked by the SHA-256 GitHub
    names for the file;
  - a model file from Hugging Face (huggingface.co and its download hosts *.huggingface.co, *.hf.co), checked by its SHA-256.
Nothing of yours is ever sent: a request names the file to fetch, nothing else.

How the model runs: as a child process of the service, listening on no address of any network -- not even this Mac's own
(127.0.0.1) -- but on a socket file in a temporary folder made for that start, which only this user's programs can reach;
with a key made for that start (kept in memory only, given to it in its environment, never on its command line); without its
chat app, without tools of its own, offline. On the Mac inside the system's sandbox (sandbox-exec): no network at all -- that
one file excepted, on which it may listen; it starts no other program, sends no Apple events (cannot steer MoneyMoney or a
browser), opens nothing through the system, writes only into that temporary folder of its own (besides it the system's
caches) -- never into Kontor's temporary folders -- and reads nothing in your home folder but its own folder -- so not
Kontor's data, not MoneyMoney's, no documents. That sandbox is a second line behind llama.cpp itself (should the program or a
model file ever be faulty); which rules apply is your setting -- nothing the process does makes Kontor try weaker ones.
Kontor talks to it over that file and nowhere else (LocalAI._connect: there is no address to set). It ends when you stop it,
after some idle minutes, and when Kontor restarts.

Nothing here knows your figures: what the model is asked and may do is in assistant.py.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import logging
import math
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
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections import deque
from datetime import datetime, timezone
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
# where a model file lies in its repository: at the top, or one folder down (large models: a folder for each variant)
PATH_RE = re.compile(r"(?:[A-Za-z0-9][\w.\-]{0,95}/)?[A-Za-z0-9][\w.\-]{0,180}\.gguf")
# a model in several files, as llama.cpp splits and loads them: name-00001-of-00003.gguf, ... -- started with the first
SPLIT_RE = re.compile(r"(.+)-(\d{5})-of-(\d{5})\.gguf")
MAX_PARTS = 99
NOT_MODELS = ("mtp-", "imatrix", "dspark-")       # GGUF files beside the models (drafters for faster answers, measurements): no chat models
STAGED = ".new"                     # a file of a model in several files that has arrived and is checked, until all of them are
SHA_RE = re.compile(r"[0-9a-f]{64}")
MAX_RUNTIME = 2 << 30               # an unpacked llama.cpp is far smaller: more than this is refused
START_SECONDS = 420                 # a large model from a slow disk
REACH_SECONDS = 45                  # llama-server listens (and says "loading") long before the model is there
SANDBOX = "/usr/bin/sandbox-exec"
TMP_PREFIX = "llm-run-"             # a model process's own temporary folder, a new one for every start (never "kontor-...")
SOCK_NAME = "m.sock"                # the socket file the model's server listens on, in that folder (llama.cpp: a --host ending in .sock)
SOCK_MAX = 100                      # bytes of its whole path at most (macOS takes 103)

# Models Kontor names (they change with Kontor's versions); any other GGUF from Hugging Face can be added by its repository.
# In the order the settings show them, by what a model is for ("kind"), within a kind the most thorough first:
#   thorough -- for figures, documents and research: answers that are right count more than speed. Kontor suggests the first
#               of them that runs well on this Mac (recommended) -- and nothing where none does;
#   fast     -- answers several times as fast (only a part of the model computes each word), less reliable with long documents;
#   simple   -- small ones, for simple questions: they rather guess than say that they do not know;
#   large    -- for a machine with far more memory: shown on every Mac with what they need, loaded only where they fit.
#               Never suggested by Kontor (none of them was tried in Kontor yet). They come in several files, a folder for
#               each variant -- names as Unsloth publishes them (looked up when you load: a variant that is not there is said so).
# "pick": the variant wanted, then what to take if the repository names it differently (its file is looked up there when you
# load it); "gb": about the size of that file; "ram": from how many GB of memory of the Mac it runs well beside macOS,
# MoneyMoney and a browser; "maker", "licence": who made the model and under which licence it may be used (as its model card
# says); "note": its line in the settings (web/i18n.js: ki_note_...). What each is said to be good at goes back to
# independent tests of the models as published (long documents: about 82 % right with Qwen3.8 27B, 72 % with Qwen3.6
# 35B-A3B; Gemma 4 26B-A4B guessed in most cases where it could not know) -- no figure of them is shown, they age fast.
CATALOG: List[Dict[str, Any]] = [
    {"id": "qwen3.8-27b-q6", "name": "Qwen3.8 27B", "kind": "thorough", "maker": "Alibaba", "licence": "Apache 2.0",
     "repo": "unsloth/Qwen3.8-27B-GGUF", "pick": ["Q6_K", "Q6_K_M"], "gb": 22, "ram": 64, "note": "thorough"},
    {"id": "qwen3.8-27b", "name": "Qwen3.8 27B Compact", "kind": "thorough", "maker": "Alibaba", "licence": "Apache 2.0",
     "repo": "unsloth/Qwen3.8-27B-GGUF", "pick": ["Q4_K_M", "UD-Q4_K_XL"], "gb": 17, "ram": 32, "note": "thorough_compact"},
    {"id": "qwen3.6-35b-a3b", "name": "Qwen3.6 35B-A3B", "kind": "fast", "maker": "Alibaba", "licence": "Apache 2.0",
     "repo": "unsloth/Qwen3.6-35B-A3B-GGUF", "pick": ["UD-Q4_K_M", "UD-Q4_K_XL"], "gb": 22, "ram": 48, "note": "fast"},
    {"id": "qwen3.6-35b-a3b-compact", "name": "Qwen3.6 35B-A3B Compact", "kind": "fast", "maker": "Alibaba", "licence": "Apache 2.0",
     "repo": "unsloth/Qwen3.6-35B-A3B-GGUF", "pick": ["UD-IQ4_XS", "UD-Q3_K_XL"], "gb": 18, "ram": 32, "note": "fast_compact"},
    {"id": "gemma-4-26b-a4b", "name": "Gemma 4 26B-A4B", "kind": "simple", "maker": "Google", "licence": "Apache 2.0",
     "repo": "unsloth/gemma-4-26B-A4B-it-GGUF", "pick": ["UD-Q4_K_M", "UD-Q4_K_XL"], "gb": 17, "ram": 32, "note": "guesses"},
    {"id": "gemma-4-12b", "name": "Gemma 4 12B", "kind": "simple", "maker": "Google", "licence": "Apache 2.0",
     "repo": "unsloth/gemma-4-12b-it-GGUF", "pick": ["UD-Q4_K_XL", "Q4_K_M"], "gb": 8, "ram": 24, "note": "guesses"},
    {"id": "qwen3.5-9b", "name": "Qwen3.5 9B", "kind": "simple", "maker": "Alibaba", "licence": "Apache 2.0",
     "repo": "unsloth/Qwen3.5-9B-GGUF", "pick": ["Q4_K_M", "UD-Q4_K_XL"], "gb": 6, "ram": 16, "note": "small"},
    {"id": "qwen3.5-4b", "name": "Qwen3.5 4B", "kind": "simple", "maker": "Alibaba", "licence": "Apache 2.0",
     "repo": "bartowski/Qwen_Qwen3.5-4B-GGUF", "pick": ["Q4_K_M"], "gb": 3, "ram": 8, "note": "small"},
    # 125 billion parameters, of which 6 billion compute each word (fast for its size); its maker's own licence, not a free one.
    # Needs llama.cpp from about b12233 (Kontor loads the newest). In several files of up to 50 GB, in a folder of its
    # variant (UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-0000N-of-0000M.gguf)
    {"id": "qwen3.8-flash-next", "name": "Qwen3.8 Flash Next", "kind": "large", "maker": "Alibaba", "licence": "Qwen Community 1.0",
     "repo": "unsloth/Qwen3.8-Flash-Next-GGUF", "pick": ["UD-IQ4_XS", "UD-Q3_K_XL"], "gb": 94, "ram": 192, "note": "large"},
]
# Not in the list, though larger still (looked at on 2026-11-23): GLM-5.3 Flash -- it cannot answer without thinking first,
# which the quick steps here need (the look at what to remember), and llama.cpp runs it only since lately, its publisher's own
# guide still by a fork; DeepSeek V4.1 Flash -- only with a runtime of its own; MiMo-V2.6 Flash and DeepSeek V4 Flash -- at
# 160 to 170 GB they read long documents no more reliably than Qwen3.8 27B does at 22 GB.
KINDS = ("thorough", "fast", "simple", "large")       # the groups of the list, in this order
# For dictating: models that only write down what is said (speech recognition). llama.cpp runs them like any other model,
# with their audio part (a second file, "mmproj-...") beside them -- on this Mac, without a network, in the same sandbox.
SPEECH: List[Dict[str, Any]] = [
    {"id": "qwen3-asr-1.7b", "name": "Qwen3-ASR 1.7B", "repo": "ggml-org/Qwen3-ASR-1.7B-GGUF", "pick": ["Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "F16", "BF16"], "gb": 3, "note": "speech"},
    {"id": "qwen3-asr-0.6b", "name": "Qwen3-ASR 0.6B", "repo": "ggml-org/Qwen3-ASR-0.6B-GGUF", "pick": ["Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "F16", "BF16"], "gb": 1, "note": "speech_small"},
]
SPEECH_IDS = tuple(c["id"] for c in SPEECH)
# A model that answers and reads pictures has its picture part beside it in its repository (a second file, "mmproj-...", about
# 1 GB): loaded and checked with the model, started with it -- no switch of its own (user, 2026-11-23). Of its variants the
# first there is (F16 runs on every Mac's graphics chip), else the smallest. A picture costs the model at most PICTURE_TOKENS
# of its context (llama.cpp scales it down to that); figures never come from a picture -- they come from the text recognition.
VISION_PICK = ("f16", "bf16", "q8_0", "f32")
PICTURE_TOKENS = 1536
# For finding by meaning (the assistant's memory): a small model that turns a text into a row of numbers, its embedding -- texts
# about the same lie close together, whatever their words. It writes no text; llama.cpp runs it as a third process, on this Mac,
# without a network, in the same sandbox. query: put before a question (the model is trained so); eos: after every text.
EMBED: List[Dict[str, Any]] = [
    {"id": "qwen3-embedding-0.6b", "name": "Qwen3-Embedding 0.6B", "repo": "Qwen/Qwen3-Embedding-0.6B-GGUF", "pick": ["Q8_0", "F16"], "gb": 1, "note": "embed",
     "query": "Instruct: %s\nQuery:", "task": "Given a question, retrieve the notes that help to answer it", "eos": "<|endoftext|>"},
]
EMBED_IDS = tuple(c["id"] for c in EMBED)
EMBED_CONTEXT = 2048     # tokens of one text at most (a note is far shorter)
EMBED_TEXT = 4000        # characters of one text given to it (more: cut)
EMBED_DIMS = 512         # numbers kept of each embedding: its first ones (Qwen3-Embedding is trained so that they carry most), half the room
SPEECH_CONTEXT = 8192    # a few minutes of speech and their text
MAX_AUDIO = 20 * 1024 * 1024         # bytes of one recording (WAV, 16 kHz, mono: ten minutes and a little more)
HEADROOM_GB = 2          # beside the file: the conversation in memory and the program itself
MAC_RAM = (8, 16, 18, 24, 32, 36, 48, 64, 96, 128, 192, 256, 512)       # GB of memory Macs are sold with


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
    if (have + max(0.5, have * 0.02) >= ram_from) if ram_from else (gb + HEADROOM_GB <= have * 0.6):       # (a Mac may name a little less than the round number)
        return "good"
    return "tight" if gb + HEADROOM_GB <= have * 0.75 else "big"


def least_ram(gb: float) -> int:
    """The smallest memory a Mac is sold with on which a model file of this size runs at all ("tight", see fit) -- what the
    settings name for a model that is too big for this Mac. 0: none."""
    return next((s for s in MAC_RAM if gb + HEADROOM_GB <= s * 0.75), 0)


def recommended(ram: int) -> str:
    """The model Kontor suggests for this Mac: the most thorough one that runs well on it -- answers that are right count
    more than speed. None where only the small models run (they are for simple questions: suggesting one would promise
    too much), and none with unknown memory. Only a suggestion: the model in use is never changed by Kontor."""
    if not ram:
        return ""
    return next((c["id"] for c in CATALOG if c["kind"] == "thorough" and fit(c["gb"], c["ram"], ram) == "good"), "")


def part_names(m: dict) -> List[str]:
    """The files of a model kept in several files, in their order, as models.json names them ([]: not such a model, or a
    name that is none -- nothing outside the model's folder is ever named)."""
    parts = m.get("parts") if isinstance(m.get("parts"), list) else []
    names = [str(x.get("file") or "") if isinstance(x, dict) else "" for x in parts]
    return names if names and len(names) <= MAX_PARTS and len(set(names)) == len(names) and all(FILE_RE.fullmatch(n) for n in names) else []


_RUNTIME_LOCKS: Dict[str, threading.Lock] = {}     # one per assistant folder: runtime.json and the builds beside it change one at a time
_RUNTIME_LOCKS_GUARD = threading.Lock()


def runtime_lock(base: str) -> threading.Lock:
    """Shared by the processes of one folder (answers, dictation, meaning). Taken after a LocalAI's own lock, never before it."""
    with _RUNTIME_LOCKS_GUARD:
        return _RUNTIME_LOCKS.setdefault(os.path.realpath(base), threading.Lock())


class Cancelled(Exception):
    pass


class ModelError(Exception):
    """The model did not start or did not answer (its text is for the user)."""


class StreamError(ModelError):
    """llama.cpp's error in the middle of an answer it had begun (the last piece of its stream): the request itself was taken."""


# How a family of models wants to be asked -- its maker's recommendation on the model card, not one setting for all of them
# (a model asked with other values answers worse than it can). "think": the sampling while it thinks before it answers,
# "plain": without thinking; "levels": how much it thinks where its chat template knows levels of its own (Kontor's effort ->
# the template's reasoning_effort). A family is known by the name of the model (its id in the list, its repository, its file).
# Sources (read 2026-11-23):
#   Qwen3.8 -- card of Qwen3.8-27B: thinking 1.0 / 0.95 / 20 / min_p 0 / presence 0, without 0.7 / 0.80 / 20; reasoning_effort
#              low, medium, xhigh (xhigh when none is given: it then thinks very long);
#   Qwen3.5, 3.6 -- card of Qwen3.6-35B-A3B: thinking, precise tasks 0.6 / 0.95 / 20 / min_p 0 / presence 0; without 0.7 / 0.8 / 20;
#   Gemma 4 -- Google's defaults: 1.0 / 0.95 / 64.
# presence_penalty stays 0 for all, also where a card names 1.5 for general chat: it lowers every sign that stood shortly
# before -- digits, the bars of a table, the quotes of a tool call -- and makes Qwen mix languages (as the card says itself).
# Nothing here for a model Kontor does not know: llama.cpp then uses its own defaults (and what the model file carries).
FAMILIES: List[Dict[str, Any]] = [
    {"id": "qwen3.8", "match": r"qwen[\W_]?3\.8",
     "think": {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0},
     "plain": {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0},
     "levels": {"balanced": "medium"}},
    {"id": "qwen3", "match": r"qwen[\W_]?3(?![\w.\-]*(?:asr|embed|rerank|tts))",
     "think": {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0},
     "plain": {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0}},
    {"id": "gemma4", "match": r"gemma[\W_]?4",
     "think": {"temperature": 1.0, "top_p": 0.95, "top_k": 64},
     "plain": {"temperature": 1.0, "top_p": 0.95, "top_k": 64}},
]


def tuning(model_id: str) -> Dict[str, Any]:
    """How the model with this id wants to be asked (FAMILIES): {"id", "think", "plain", "levels"} -- for a model of the
    list by its repository too, for any other by its own name (repository/file). Unknown: {"id": "", ...} with nothing set."""
    entry = next((c for c in CATALOG if c["id"] == model_id), None)
    name = ("%s %s" % (model_id, entry["repo"] if entry else "")).lower()
    fam = next((f for f in FAMILIES if re.search(f["match"], name)), None)
    return {"id": fam["id"] if fam else "", "think": dict(fam["think"]) if fam else {}, "plain": dict(fam["plain"]) if fam else {},
            "levels": dict(fam.get("levels") or {}) if fam else {}}


def template_caps(props: Any) -> Dict[str, Any]:
    """What llama.cpp's /props says of the running model, every value checked (see LocalAI._caps)."""
    if not isinstance(props, dict) or not isinstance(props.get("chat_template_caps"), dict):
        return {}
    c = props["chat_template_caps"]
    words = lambda v: [x for x in v if isinstance(x, str) and re.fullmatch(r"[a-z]{2,12}", x)][:12] if isinstance(v, list) else []
    mod = props.get("modalities") if isinstance(props.get("modalities"), dict) else {}
    return {"levels": words(c.get("reasoning_effort_levels")), "rejected": words(c.get("reasoning_effort_rejected")),
            "preserve": c.get("supports_preserve_reasoning") is True, "vision": mod.get("vision") is True}


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


def _aged(published: Any, seconds: float) -> bool:
    """A release out at least that long (GitHub's published_at, "2026-11-20T08:15:00Z"). Not named at all: counts as old
    enough (GitHub names it for every published release); named but not readable or in the future: not."""
    if published is None:
        return True
    try:
        when = datetime.strptime(str(published)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - when).total_seconds() >= seconds


def older_build(tag: str, than: str) -> bool:
    """llama.cpp's builds are numbered (b7123): an older one than the installed is never named newer nor installed in its place."""
    a, b = re.fullmatch(r"b(\d{1,7})", tag or ""), re.fullmatch(r"b(\d{1,7})", than or "")
    return bool(a and b and int(a.group(1)) < int(b.group(1)))


def pick_asset(release: dict) -> Optional[dict]:
    want = "-bin-" + asset_tag()
    for a in release.get("assets") or []:
        name = str(a.get("name") or "")
        if name.startswith("llama-") and (name.endswith(want + ".tar.gz") or name.endswith(want + ".zip")):
            dig = str(a.get("digest") or "")
            return {"name": name, "url": str(a.get("browser_download_url") or ""), "size": int(a.get("size") or 0),
                    "sha256": dig[7:].lower() if dig.startswith("sha256:") and SHA_RE.fullmatch(dig[7:].lower()) else ""}
    return None


def plain_name(file: str) -> str:
    """A model file's name without the count of a model in several files (x-Q4-00001-of-00003.gguf -> x-Q4.gguf)."""
    m = SPLIT_RE.fullmatch(file)
    return m.group(1) + ".gguf" if m else file


def whole(files: List[dict]) -> List[dict]:
    """Model files as models: a file alone as it is; the files of a model in several ("...-00001-of-00003.gguf", all in one
    folder) as one entry -- "file": the first of them (the one llama.cpp is started with), "size": all together, "sha256":
    one value over the SHA-256 of each in their order ("" if one of them has none: such a model is never loaded), "parts":
    each file in its order. A model with a file missing is left out."""
    out: List[dict] = []
    sets: Dict[tuple, Dict[int, dict]] = {}
    for f in files:
        m = SPLIT_RE.fullmatch(f["file"])
        if not m:
            out.append(f)
        elif 1 <= int(m.group(2)) <= int(m.group(3)) <= MAX_PARTS:
            sets.setdefault((f["path"][:-len(f["file"])], m.group(1), int(m.group(3))), {}).setdefault(int(m.group(2)), f)
    for (_folder, _name, count), found in sets.items():
        if len(found) == count:
            parts = [found[i] for i in range(1, count + 1)]
            checked = all(x["sha256"] for x in parts)
            out.append({"file": parts[0]["file"], "size": sum(x["size"] for x in parts), "parts": parts,
                        "sha256": hashlib.sha256("\n".join(x["sha256"] for x in parts).encode("ascii")).hexdigest() if checked else ""})
    return out


def vision_part(parts: List[dict]) -> Optional[dict]:
    """The picture part of a model that answers, among the "mmproj-..." files of its repository (repo_files, projectors):
    the first of VISION_PICK there is, else the smallest -- None where the repository has none (a model without pictures)."""
    for p in VISION_PICK:
        hits = [x for x in parts if re.search(r"(?<![a-z0-9])%s\.gguf$" % re.escape(p), x["file"].lower())]
        if hits:
            return min(hits, key=lambda x: (x["size"], x["file"]))
    return min(parts, key=lambda x: (x["size"], x["file"])) if parts else None


def resolve_pick(files: List[dict], pick: Any) -> Optional[dict]:
    """The file of a variant (e.g. UD-Q4_K_M) among a repository's model files; of several variants the first there is."""
    for p in ([pick] if isinstance(pick, str) else list(pick)):
        p = p.lower()
        hits = [f for f in files if re.search(r"[-.]%s\.gguf$" % re.escape(p), plain_name(f["file"]).lower())]
        if hits:
            return min(hits, key=lambda f: len(f["file"]))        # "…-Q4_K_M.gguf" before "…-UD-Q4_K_M.gguf"
    return None


# The sandbox the model runs in is your choice (Einstellungen -> Assistent), never the model's: nothing its process does -- not
# starting, crashing, not answering -- makes Kontor try weaker rules. Every level but "off": no network connection of its own.
SANDBOXES = ("strict", "basic", "off")


def sandbox_profile(data_dir: str, program_dir: str, base_dir: str, level: str = "strict", home: Optional[str] = None, sock: str = "") -> str:
    """The rules for sandbox-exec (later rules win).
    Both levels: no network at all -- no connection going out, none coming in, no address listened on, not even this Mac's
    own; the one thing excepted is the socket file of this start (sock, in the process's own temporary folder), on which it
    may listen and take what comes in (without sock, as when a new llama.cpp is only tried: nothing at all); nothing written
    into Kontor's folders, nor into Kontor's temporary folders (kontor-..., where e.g. the helper for MoneyMoney's password
    is built and started, an update is unpacked, Touch ID answers); Kontor's data not read (only the model's own folder
    inside it).
    strict: besides that it starts no other program, sends no Apple events (so it cannot steer MoneyMoney, a browser or any
    other app), opens nothing through the system (no addresses, no files), signals no other process, does not read the
    clipboard, reads nothing in the home folder and writes only into the temporary folder Kontor makes for each start
    (own_tmp, its TMPDIR) and the system's caches (the graphics chip's compiled programs) -- not into the temporary folders
    at large, where other programs keep theirs (Apple's compilers too: xcrun's list of tools, swiftc's own files), and not
    into the compilers' module caches among the caches, from which Kontor's helpers are built (the one asking for
    MoneyMoney's password)."""
    q = lambda p: json.dumps(os.path.realpath(p), ensure_ascii=False)
    listen = ["(allow network-bind (local unix-socket (path-literal %s)))" % q(sock), "(allow network-inbound (local unix-socket (path-literal %s)))" % q(sock)] if sock else []
    rules = ["(version 1)", "(allow default)", "(deny network*)", *listen]
    if level == "strict":
        rules += ["(deny process-exec*)", "(allow process-exec* (subpath %s))" % q(os.path.join(base_dir, "runtime")),
                  "(deny appleevent-send)", "(deny lsopen)",
                  "(deny signal)", "(allow signal (target self))",
                  '(deny mach-lookup (global-name "com.apple.pasteboard.1"))',
                  "(deny file-write*)",
                  '(allow file-write* (regex #"^/private/var/folders/[^/]+/[^/]+/T/%s[^/]+/") (regex #"^/private/var/folders/[^/]+/[^/]+/C/")'
                  ' (literal "/dev/null") (literal "/dev/dtracehelper") (literal "/dev/tty"))' % TMP_PREFIX,
                  '(deny file-write* (regex #"^/private/var/folders/[^/]+/[^/]+/C/(clang|org\\.llvm\\.clang)"))',      # (clang's and swiftc's modules)
                  "(deny file-read* (subpath %s) (subpath %s))" % (q(home or os.path.expanduser("~")), q(data_dir))]
    else:
        rules += ["(deny file-write* (subpath %s) (subpath %s))" % (q(data_dir), q(program_dir)), "(deny file-read* (subpath %s))" % q(data_dir)]
    return "\n".join(rules + ['(deny file-write* (regex #"/kontor-[^/]*(/|$)"))',           # after every rule that allows writing: this one wins
                              "(allow file-read* (subpath %s))" % q(base_dir), "(allow file-read-metadata (vnode-type DIRECTORY))"])


def own_tmp() -> str:
    """A new, empty temporary folder for one start of a model process -- handed to it as TMPDIR, removed when it has ended.
    In the system's temporary folder, never one of Kontor's own (kontor-...): those no model process may write."""
    return os.path.realpath(tempfile.mkdtemp(prefix=TMP_PREFIX))


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


def listens_on_file(helped: str) -> bool:
    """Does this llama-server's own help say that --host takes a socket file (a path ending in .sock) instead of an address?
    What it says about --host may run over several lines (up to the next option)."""
    m = re.search(r"(?m)^[ \t]*--host\b.*(?:\n(?![ \t]*-).*)*", helped)
    said = re.sub(r"\s+", " ", m.group(0)) if m else ""
    return bool(re.search(r"(?i)unix socket", said) and ".sock" in said)


class _OnFile(http.client.HTTPConnection):
    """HTTP over the socket file of a model Kontor started: nothing of it travels over any network, no address is listened
    on. Only ever such a file -- named SOCK_NAME, in a folder made by own_tmp -- whatever path it is handed."""

    def __init__(self, path: str, timeout: int):
        super().__init__("localhost", timeout=timeout)        # (a name for the request's Host line only: never looked up, never connected to)
        self.path = path

    def connect(self) -> None:
        if os.path.basename(self.path) != SOCK_NAME or not os.path.basename(os.path.dirname(self.path)).startswith(TMP_PREFIX):
            raise OSError("no socket file of a model")
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        try:
            s.connect(self.path)
        except OSError:
            s.close()
            raise
        self.sock = s


class LocalAI:
    """llama.cpp and the models in one folder (base_dir), and the one running model."""

    def __init__(self, base_dir: str, data_dir: str, program_dir: str, role: str = "server"):
        """role: "server" for the model that answers, "speech" for the one that writes down what is dictated -- two processes
        of the same program, each kept track of in a file of its own."""
        self.base, self.data_dir, self.program_dir, self.role = base_dir, data_dir, program_dir, role
        self.lock = threading.RLock()
        self.job: Optional[dict] = None                # a download in progress (or its end)
        self.news: dict = {}                           # the last look for newer versions (by itself or on your click)
        self.min_age = 0                               # updated by itself: only builds of llama.cpp out at least that long (seconds; AUTO_AGE)
        self.proc: Optional[subprocess.Popen] = None
        self.sock = ""                                 # the socket file the running model listens on (in its own temporary folder)
        self.key = ""
        self.model = ""
        self.file = ("", "")                           # the running model's file (path, SHA-256): a newer one starts it anew
        self.ctx = 0
        self.state = "stopped"                         # stopped | starting | ready | error
        self.error = ""
        self.sealed = ""                               # "" | "strict" | "basic": the sandbox the running model is in
        self.tmp = ""                                  # the running model's own temporary folder (own_tmp)
        self.since: Optional[float] = None
        self.last_used = 0.0
        self.busy = False
        self.tps: Optional[float] = None
        self.blind: Optional[tuple] = None             # (llama.cpp build, picture part) the model did not start with: started without it
        self._told: tuple = (0, {})                    # what the running model's chat template can do (caps), and which start told it
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
        """The installed llama.cpp: {} or {"tag", "bin", "version", "flags", "sock", "installed"} (bin exists; sock: it can
        listen on a socket file -- not there for one installed before Kontor asked: ensure asks then)."""
        r = self._load("runtime.json")
        b = self._p("runtime", str(r.get("dir") or ""), str(r.get("bin") or "")) if r.get("dir") and r.get("bin") else ""
        inside = os.path.realpath(b).startswith(os.path.realpath(self._p("runtime")) + os.sep) if b else False    # only ever a program in its own folder
        return dict(r, path=b) if inside and os.path.isfile(b) and os.path.basename(b) == "llama-server" else {}

    def models(self) -> Dict[str, dict]:
        """The model files on this Mac: id -> {"repo", "file", "size", "sha256", "name", "path"} (files that exist). A model
        in several files ("parts": their names in order, "file" the first of them) is there with every one of them only."""
        out = {}
        for mid, m in (self._load("models.json").get("models") or {}).items():
            if not isinstance(m, dict) or not REPO_RE.fullmatch(str(m.get("repo") or "")) or not FILE_RE.fullmatch(str(m.get("file") or "")):
                continue
            path = self.model_path(m["repo"], m["file"])
            if not os.path.isfile(path) or m.get("replacing"):      # (replacing: its files were being exchanged and not all of them got there)
                continue
            if "parts" in m:
                names = part_names(m)
                if not names or names[0] != m["file"] or not all(os.path.isfile(self.model_path(m["repo"], n)) for n in names):
                    continue
            pj = m.get("mmproj") if isinstance(m.get("mmproj"), dict) else None       # its audio or picture part: a second file beside it
            if pj is not None and FILE_RE.fullmatch(str(pj.get("file") or "")) and os.path.isfile(self.model_path(m["repo"], pj["file"])):
                out[str(mid)] = dict(m, path=path, mmproj_path=self.model_path(m["repo"], pj["file"]))
            elif pj is None or str(mid) not in SPEECH_IDS:        # (a model that answers, its picture part gone: it answers without pictures;
                out[str(mid)] = dict(m, path=path)              # a speech model hears nothing without its audio part)
        return out

    def _parts(self, repo: str, data: Optional[dict] = None) -> set:
        """The second parts (file, SHA-256) the models of this repository on record have (data: models.json as it is about to
        be saved) -- models of one repository share one file of it: it goes only with the last of them."""
        out = set()
        for m in ((self._load("models.json") if data is None else data).get("models") or {}).values():
            pj = m.get("mmproj") if isinstance(m, dict) and isinstance(m.get("mmproj"), dict) else None
            if pj and m.get("repo") == repo:
                out.add((str(pj.get("file") or ""), str(pj.get("sha256") or "")))
        return out

    def model_path(self, repo: str, file: str) -> str:
        return self._p("models", repo.replace("/", "--"), file)

    # -- looking for newer versions (by itself, as set) and loading (on your click only) ----------------------------------------------
    def latest_runtime(self) -> dict:
        """The newest published release (pre-releases included, drafts not) with a build for this machine. With min_age
        (updated by itself): only a build out at least that long -- a broken or planted build is usually found and taken
        back within hours -- and never one that did not start here before (bad_builds)."""
        rels, _ = _json_get(RELEASES_URL, GITHUB)
        bad = self.bad_builds()
        for rel in rels if isinstance(rels, list) else []:
            if not isinstance(rel, dict) or rel.get("draft"):
                continue
            if str(rel.get("tag_name") or "")[:40] in bad or (self.min_age and not _aged(rel.get("published_at"), self.min_age)):
                continue
            a = pick_asset(rel)
            if a:                             # the newest build it is -- one from another address is refused, not swapped for an older one
                if not host_allowed(a["url"], GITHUB):
                    break
                return dict(a, tag=str(rel.get("tag_name") or "")[:40])
        raise ValueError(tr("s_ki_kein_build") % asset_tag())

    def listing(self, repo: str) -> List[Any]:
        """What Hugging Face lists of a repository (its files and folders, as it says them -- repo_files reads them)."""
        if not REPO_RE.fullmatch(repo or ""):
            raise ValueError(tr("s_ki_repo_ungueltig"))
        out: List[Any] = []
        url: Optional[str] = "https://huggingface.co/api/models/%s/tree/main?recursive=true" % quote(repo, safe="/")
        for _ in range(6):                          # a few pages at most
            if not url:
                break
            data, headers = _json_get(url, HF)
            out += data if isinstance(data, list) else []
            m = re.search(r'<([^>]+)>;\s*rel="next"', str(headers.get("Link") or ""))
            url = m.group(1) if m and host_allowed(m.group(1), HF) else None
        return out

    def repo_files(self, repo: str, projectors: bool = False, listed: Optional[List[Any]] = None) -> List[dict]:
        """The models (GGUF) of a repository at Hugging Face: [{"file", "path", "size", "sha256"}] -- "path": where the file
        lies there (at the top or one folder down), "file": its name, under which it is kept on this Mac. A model in several
        files ("...-00001-of-00003.gguf") is one entry with its "parts" (see whole).
        projectors: instead the audio/vision parts that belong to them ("mmproj-...", at the top). listed: what listing gave
        (not asked again)."""
        if not REPO_RE.fullmatch(repo or ""):
            raise ValueError(tr("s_ki_repo_ungueltig"))
        out: Dict[str, dict] = {}
        for f in self.listing(repo) if listed is None else listed:
            if not isinstance(f, dict):
                continue
            path = str(f.get("path") or "")
            name = path.rsplit("/", 1)[-1]
            if f.get("type") != "file" or not PATH_RE.fullmatch(path) or name.lower().startswith(NOT_MODELS):
                continue
            if name.lower().startswith("mmproj") != projectors or (projectors and name != path):
                continue
            lfs = f.get("lfs") if isinstance(f.get("lfs"), dict) else {}
            sha = str(lfs.get("oid") or "").lower()
            out.setdefault(name, {"file": name, "path": path, "size": int(lfs.get("size") or f.get("size") or 0), "sha256": sha if SHA_RE.fullmatch(sha) else ""})
        return sorted(whole(list(out.values())), key=lambda f: f["size"])

    def check(self) -> dict:
        """Looks for a newer llama.cpp and newer files of the loaded models (network: GitHub and Hugging Face)."""
        news: dict = {"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "models": {}}
        try:
            lr = self.latest_runtime()
            cur = self.runtime().get("tag") or ""
            news["runtime"] = {"tag": lr["tag"], "newer": lr["tag"] != cur and not older_build(lr["tag"], cur)}
        except Exception as e:
            news["error"] = str(e)[:300]
        cat = {c["id"]: c for c in CATALOG + SPEECH + EMBED}
        for mid, m in self.models().items():
            try:
                listed = self.listing(m["repo"])
                files = self.repo_files(m["repo"], listed=listed)
                f = resolve_pick(files, cat[mid]["pick"]) if mid in cat else next((x for x in files if x["file"] == m["file"]), None)
                if f and f["sha256"] and m.get("sha256"):
                    news["models"][mid] = {"newer": f["sha256"] != m["sha256"], "size": f["size"]}
                    if not news["models"][mid]["newer"] and mid not in SPEECH_IDS and mid not in EMBED_IDS:     # the same model: is its picture part new
                        part = vision_part([x for x in self.repo_files(m["repo"], True, listed) if SHA_RE.fullmatch(x["sha256"] or "")])     # (or one there is, where it has none yet)?
                        had = m.get("mmproj") if isinstance(m.get("mmproj"), dict) else {}
                        if part and ((part["file"], part["sha256"]) != (had.get("file"), had.get("sha256")) or "mmproj_path" not in m):
                            news["models"][mid] = {"newer": True, "size": part["size"]}
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
        if not j:
            return None
        j = dict(j)                                                # as it is at this moment (a download goes on beside this)
        rate, smp = 0, tuple(j.get("samples") or ())
        if j["state"] == "running" and len(smp) >= 2:
            span = max(time.time(), smp[-1][0]) - smp[0][0]        # up to now: when nothing arrives, the rate falls
            rate = int((smp[-1][1] - smp[0][1]) / span) if span >= 1 else 0
        if j.get("whole"):                                         # a model in several files: one progress over all of them
            j.update(done=min(j["whole"], j.get("before", 0) + j["done"]), total=j["whole"])
        return dict({k: j[k] for k in ("kind", "id", "label", "done", "total", "state", "text")}, seconds=round(time.time() - j["started"], 1), rate=max(0, rate))

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
                job["samples"] = [(time.time(), job["done"])]     # the speed: from what arrives over the network from here on
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
                        now, smp = time.time(), job["samples"]
                        if now - smp[-1][0] >= 0.5:               # a point every half second, the last six seconds
                            smp.append((now, job["done"]))
                            del smp[:-13]
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
            if older_build(a["tag"], self.runtime().get("tag") or ""):
                raise ValueError(tr("s_ki_nichts_neues"))
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
                version, flags, sock = self._probe(os.path.join(tmp, rel), sandbox)   # a build that does not start here is not kept (the old one stays)
                if not sock:                               # ... nor one that could only be talked to at an address
                    raise ValueError(tr("s_ki_nur_adresse"))
            except Exception:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
            self._changing("")
            final = os.path.join(rdir, tag)
            with runtime_lock(self.base):
                cur = self._load("runtime.json")
                old = {k: v for k, v in cur.items() if k != "previous"}
                if old.get("dir") == tag:                   # the same build again: the one before it (if any) stays the one before
                    old = cur.get("previous") if isinstance(cur.get("previous"), dict) else {}
                elif not self.runtime():
                    old = {}
                keep = str(old.get("dir") or "") if old.get("dir") != tag else ""
                shutil.rmtree(final, ignore_errors=True)
                os.replace(tmp, final)
                # the build before stays until the new one has started a model here once (proven): a new build that does not
                # start gives way to it by itself (ensure)
                self._save("runtime.json", dict({"tag": a["tag"], "dir": tag, "bin": rel, "version": version, "flags": flags, "sock": sock, "sha256": sha,
                                                 "installed": datetime.now().strftime("%Y-%m-%d %H:%M")}, **({"previous": old} if keep else {})))
                self._tidy_runtime(tag, keep)
            self.news.pop("runtime", None)
        return self._start_job("runtime", "llama.cpp", "llama.cpp", work)

    def _tidy_runtime(self, *keep: str) -> None:
        """Every build of llama.cpp in its folder but these (folder names) goes -- and anything else left there."""
        rdir = self._p("runtime")
        for name in os.listdir(rdir) if os.path.isdir(rdir) else []:
            if name not in keep:
                full = os.path.join(rdir, name)
                shutil.rmtree(full, ignore_errors=True) if os.path.isdir(full) and not os.path.islink(full) else os.remove(full)

    def bad_builds(self) -> List[str]:
        """Builds of llama.cpp that did not start a model here while the one before did: never installed again."""
        return [str(t)[:40] for t in (self._load("runtime-bad.json").get("tags") or [])][-50:]

    def _proven(self, path: str) -> None:
        """The installed build (path: its llama-server) has started a model here: the one before is not needed any more."""
        with runtime_lock(self.base):
            r = self._load("runtime.json")
            if isinstance(r.get("previous"), dict) and self.runtime().get("path") == path:
                self._save("runtime.json", {k: v for k, v in r.items() if k != "previous"})
                self._tidy_runtime(str(r.get("dir") or ""))

    def _give_way(self) -> Optional[dict]:
        """The newly installed build did not start a model: back to the build before it (still in its folder). Returns the
        runtime.json of the new one (to come back to), None when there is nothing to go back to."""
        r = self._load("runtime.json")
        prev = r.get("previous") if isinstance(r.get("previous"), dict) else None
        if not prev or not prev.get("dir") or not prev.get("bin"):
            return None
        self._changing("")
        with runtime_lock(self.base):
            if self._load("runtime.json") != r:         # installed or proven meanwhile: as it is now
                return None
            self._save("runtime.json", prev)
            if not self.runtime():                      # its folder is gone: the new build it stays
                self._save("runtime.json", r)
                return None
        return r

    def _probe(self, binp: str, level: str = "strict") -> tuple:
        """Version and options of a llama-server (run inside the sandbox where there is one, with nothing of any network
        allowed), and whether it can listen on a socket file instead of an address: a build that does not start here is not
        kept."""
        if level != "off" and not self._can_seal() and sys.platform == "darwin":
            raise ModelError(tr("s_ki_sandbox_fehlt"))          # as at the start: the sandbox asked for but not there -- not run without it

        tmp = ""

        def run(arg: str) -> str:
            cmd = self._sealed_cmd([binp, arg], level) if level != "off" and self._can_seal() else [binp, arg]      # inside the sandbox you chose
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=self._env("", tmp), cwd=os.path.dirname(binp))
            return (r.stdout or "") + (r.stderr or "")
        try:
            tmp = own_tmp()
            ver = run("--version")
            m = re.search(r"version:\s*([^\n]+)", ver)
            helped = run("--help")
            flags = sorted(set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]+", helped)))
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ValueError(tr("s_ki_startet_nicht") % str(e)[:200])
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
        if "--host" not in flags or "--model" not in flags:
            raise ValueError(tr("s_ki_startet_nicht") % (ver.strip()[:200] or "llama-server"))
        return (m.group(1).strip()[:60] if m else ""), flags, listens_on_file(helped)

    def remove_runtime(self) -> None:
        self._changing("")
        shutil.rmtree(self._p("runtime"), ignore_errors=True)
        try:
            os.remove(self._p("runtime.json"))
        except OSError:
            pass

    def download_model(self, model_id: str = "", repo: str = "", file: str = "") -> dict:
        """A model from the list (model_id) or any model of a repository at Hugging Face (repo, file: its file, of a model in
        several files the first one)."""
        entry = next((c for c in CATALOG + SPEECH + EMBED if c["id"] == model_id), None)
        if entry is None:
            if not REPO_RE.fullmatch(repo or "") or not FILE_RE.fullmatch(file or ""):
                raise ValueError(tr("s_ki_repo_ungueltig"))
            model_id, name = "%s/%s" % (repo, file), plain_name(file)[:-5]
        else:
            repo, name = entry["repo"], entry["name"]

        def work(job: dict) -> None:
            listed = self.listing(repo)
            files = self.repo_files(repo, listed=listed)
            f = resolve_pick(files, entry["pick"]) if entry else next((x for x in files if x["file"] == file), None)
            if f is None:
                raise ValueError(tr("s_ki_datei_fehlt"))
            address = lambda name_: "https://huggingface.co/%s/resolve/main/%s?download=true" % (quote(repo, safe="/"), quote(name_))
            several = f.get("parts") or []                 # a model in several files: each checked, all put in place together
            self._begun(model_id, {"repo": repo, "files": [x["file"] for x in several] or [f["file"]], "size": f["size"]})
            if not all(SHA_RE.fullmatch(x["sha256"] or "") for x in several or [f]):     # nothing loaded -- not even its second part -- that cannot be checked
                raise ValueError(tr("s_ki_keine_pruefsumme"))
            part = None
            before = ((self._load("models.json").get("models") or {}).get(model_id) or {})
            if entry is not None and entry["id"] in SPEECH_IDS:     # a speech model: its audio part first (small), then the model
                parts = self.repo_files(repo, True, listed)
                tag = f["file"].rsplit("-", 1)[-1].lower()
                part = next((x for x in parts if x["file"].lower().endswith(tag)), None) or (min(parts, key=lambda x: x["size"]) if parts else None)
                if part is None:
                    raise ValueError(tr("s_ki_datei_fehlt"))
            elif model_id not in EMBED_IDS:                         # a model that answers: its picture part, where its repository has one
                part = vision_part([x for x in self.repo_files(repo, True, listed) if SHA_RE.fullmatch(x["sha256"] or "")])     # (one that cannot be checked: the model alone)
            if part is not None:
                at = self.model_path(repo, part["file"])
                if (part["file"], part["sha256"]) in self._parts(repo) and os.path.isfile(at):
                    part = dict(part)                               # (the same, here already -- of this model or another of its repository)
                else:
                    part = dict(part, sha256=self._fetch(address(part["file"]), HF, at, part["size"], part["sha256"], job))
            dest = self.model_path(repo, f["file"])
            staged: List[str] = []
            try:
                if not several and f["sha256"] and before.get("sha256") == f["sha256"] and before.get("file") == f["file"] \
                        and not before.get("replacing") and (job.update(done=0, total=f["size"]) or self._is(dest, f, job)):
                    sha = f["sha256"]                               # the model is here already and right (only its picture part was new): not loaded again
                elif several:
                    sha, staged = f["sha256"], self._fetch_all(repo, f, address, job)
                else:
                    sha = self._fetch(address(f["path"]), HF, dest, f["size"], f["sha256"], job)
            except BaseException:
                if part and part["file"] not in {f for f, _ in self._parts(repo)}:      # the audio or picture part alone is of no use: it goes again (the model's
                    try:                                            # own partial file stays, the download goes on from there)
                        os.remove(self.model_path(repo, part["file"]))
                    except OSError:
                        pass
                raise
            self._changing(model_id)                       # a newer file of a running model: loaded at the next question
            if staged:                                     # every file is here and right: into their places, one after the other --
                data = self._load("models.json")           # until the last one is there, the model does not count (never old and new files mixed)
                if isinstance((data.get("models") or {}).get(model_id), dict):
                    data["models"][model_id]["replacing"] = True
                    self._save("models.json", data)
                for final in staged:
                    os.replace(final + STAGED, final)
            data = self._load("models.json")
            old = (data.get("models") or {}).get(model_id) or {}
            data.setdefault("models", {})[model_id] = dict({"repo": repo, "file": f["file"], "size": f["size"], "sha256": sha, "name": name,
                                                            "downloaded": datetime.now().strftime("%Y-%m-%d %H:%M")},
                                                           **({"mmproj": {"file": part["file"], "size": part["size"], "sha256": part["sha256"]}} if part else {}),
                                                           **({"parts": [{k: x[k] for k in ("file", "size", "sha256")} for x in several]} if several else {}))
            (data.get("begun") or {}).pop(model_id, None)
            self._save("models.json", data)
            now = set(x["file"] for x in several) or {f["file"]}
            gone = [n for n in (part_names(old) or [old.get("file")]) if n not in now]
            old_part = (old.get("mmproj") or {}).get("file")
            gone.append(old_part if old_part != (part or {}).get("file") and old_part not in {f for f, _ in self._parts(repo)} else None)     # (unless another model uses it)
            for name_ in gone:                             # the variant got other file names: the old files go
                if name_ and FILE_RE.fullmatch(str(name_)):
                    try:
                        os.remove(self.model_path(repo, name_))
                    except OSError:
                        pass
            (self.news.get("models") or {}).pop(model_id, None)
            if self.on_loaded is not None:
                self.on_loaded(model_id)
        return self._start_job("model", model_id, name, work)

    def _fetch_all(self, repo: str, f: dict, address: Callable[[str], str], job: dict) -> List[str]:
        """Every file of a model in several files (f: its entry of repo_files), each through _fetch -- its size and SHA-256
        must fit -- to a place beside its final one (name + STAGED). A file that is here already and right (in place, or
        staged by an earlier try: read in full, nothing counts unchecked) is not loaded again; a partial one goes on where
        it stopped. Before the first byte: each file has its SHA-256, and the disk has room for all that is missing. Nothing
        is put in place here -- the caller does, once every file is right. Returns the places whose staged file is to go in."""
        parts = f["parts"]
        if not all(SHA_RE.fullmatch(x["sha256"] or "") for x in parts):       # nothing is installed or run that cannot be checked
            raise ValueError(tr("s_ki_keine_pruefsumme"))
        place = lambda x: self.model_path(repo, x["file"])
        os.makedirs(os.path.dirname(place(parts[0])), exist_ok=True)
        self._no_backup()
        job.update(done=0, total=0, before=0, whole=f["size"])
        staged, todo = [], []
        for x in parts:
            if self._is(place(x), x, job):
                self._drop(place(x) + STAGED, place(x) + STAGED + ".part")       # (left by an earlier try, of no use any more)
            elif self._is(place(x) + STAGED, x, job):
                staged.append(place(x))
            else:
                todo.append(x)
                continue
            job.update(done=0, before=job["before"] + x["size"])
        have = lambda x: min(x["size"], os.path.getsize(place(x) + STAGED + ".part")) if os.path.exists(place(x) + STAGED + ".part") else 0
        missing = sum(x["size"] - have(x) for x in todo)
        free = shutil.disk_usage(os.path.dirname(place(parts[0]))).free
        if todo and free < missing + (1 << 30):
            raise ValueError(tr("s_ki_platz_fehlt") % ("%.0f" % (missing / 1e9 + 1), "%.0f" % (free / 1e9)))
        for x in todo:
            self._fetch(address(x["path"]), HF, place(x) + STAGED, x["size"], x["sha256"], job)
            staged.append(place(x))
            job.update(done=0, before=job["before"] + x["size"])
        return staged

    def _is(self, path: str, x: dict, job: dict) -> bool:
        """Is the file at path the one announced (x: its "size" and "sha256")? Read in full; what is read counts as done
        while it is read."""
        try:
            if os.path.getsize(path) == x["size"]:
                h = hashlib.sha256()
                with open(path, "rb") as fh:
                    for chunk in iter(lambda: fh.read(4 << 20), b""):
                        if job["cancel"].is_set():
                            raise Cancelled()
                        h.update(chunk)
                        job["done"] += len(chunk)
                if h.hexdigest() == x["sha256"]:
                    return True
        except OSError:
            pass
        job["done"] = 0
        return False

    @staticmethod
    def _drop(*paths: str) -> None:
        for path in paths:
            try:
                os.remove(path)
            except OSError:
                pass

    def _begun(self, model_id: str, plan: dict) -> None:
        """Notes which files a download is about to bring (models.json, "begun"): what a download that was cancelled or failed
        left behind can be named and removed (delete_model) -- or gone on with."""
        left = self.begun()
        data = self._load("models.json")
        data["begun"] = dict({k: v for k, v in (data.get("begun") or {}).items() if k in left}, **{model_id: plan})      # (what left nothing is forgotten)
        self._save("models.json", data)

    def begun(self) -> Dict[str, dict]:
        """Downloads that did not arrive whole and left something on this Mac: id -> {"repo", "files", "bytes", "size"}
        (bytes: what is there of them, partial or staged; size: the whole model's)."""
        out = {}
        for mid, b in (self._load("models.json").get("begun") or {}).items():
            names = [str(n) for n in b.get("files") or []] if isinstance(b, dict) and isinstance(b.get("files"), list) else []
            if not names or len(names) > MAX_PARTS or not REPO_RE.fullmatch(str(b.get("repo") or "")) or not all(FILE_RE.fullmatch(n) for n in names):
                continue
            left = [self.model_path(b["repo"], n) + end for n in names for end in (".part", STAGED, STAGED + ".part")]
            size = sum(os.path.getsize(x) for x in left if os.path.isfile(x))
            if size:
                out[str(mid)] = {"repo": b["repo"], "files": names, "bytes": size, "size": b["size"] if isinstance(b.get("size"), int) else 0}
        return out

    def _changing(self, model_id: str) -> None:
        """Files are about to be replaced or removed -- a model's, or the program's (""): whatever runs on them ends first,
        here and in the process beside this one (on_change)."""
        if not model_id or self.model == model_id:
            self.stop()
        if self.on_change is not None:
            self.on_change(model_id)

    def delete_model(self, model_id: str) -> None:
        """A model's files go -- all of them, and whatever a download of it left behind (also of one that never arrived)."""
        job = self.job
        if job and job.get("state") == "running" and job.get("kind") == "model" and job.get("id") == model_id:
            raise ValueError(tr("s_ki_laedt_schon"))        # (not from under a download that is writing them)
        data = self._load("models.json")
        m = (data.get("models") or {}).pop(model_id, None)
        left = self.begun().get(model_id)
        if (data.get("begun") or {}).pop(model_id, None) is None and not m:
            return
        if m:
            self._changing(model_id)
        folders = set()
        if m and REPO_RE.fullmatch(str(m.get("repo") or "")) and FILE_RE.fullmatch(str(m.get("file") or "")):
            pj = str((m.get("mmproj") or {}).get("file") or "") if isinstance(m.get("mmproj"), dict) else ""
            pj = "" if pj in {f for f, _ in self._parts(m["repo"], data)} else pj       # (a part another model of the repository uses stays)
            for n in (part_names(m) or [m["file"]]) + ([pj] if FILE_RE.fullmatch(pj) else []):
                path = self.model_path(m["repo"], n)
                self._drop(path, path + ".part", path + STAGED, path + STAGED + ".part")
                folders.add(os.path.dirname(path))
        for n in (left or {}).get("files") or []:
            path = self.model_path(left["repo"], n)
            self._drop(path + ".part", path + STAGED, path + STAGED + ".part")
            folders.add(os.path.dirname(path))
        for folder in folders:
            try:
                os.rmdir(folder)
            except OSError:
                pass
        self._save("models.json", data)

    # -- the running model ------------------------------------------------------------------------------------------------
    def _can_seal(self) -> bool:
        return sys.platform == "darwin" and os.path.exists(SANDBOX)

    def _sealed_cmd(self, cmd: List[str], level: str = "strict", sock: str = "") -> List[str]:
        return [SANDBOX, "-p", sandbox_profile(self.data_dir, self.program_dir, self.base, level, sock=sock)] + cmd

    def _env(self, key: str, tmp: str = "") -> Dict[str, str]:
        """A small environment of its own: no proxies, no tokens, nothing of Kontor's -- and for temporary files its own folder
        of this start (tmp: from own_tmp), not the one Kontor and other programs use."""
        env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.path.expanduser("~"), "LANG": "en_US.UTF-8",
               "HF_HUB_OFFLINE": "1", "LLAMA_ARG_OFFLINE": "1"}
        if tmp:
            env["TMPDIR"] = tmp
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
        """seal: "" = not in a sandbox, else its level ("strict" | "basic"). extra: further arguments (a model's audio part).
        The server listens on a socket file in its own temporary folder of this start -- on no address, at every level."""
        key = secrets.token_urlsafe(32)
        tmp = own_tmp()                                   # for this start only; gone with the process (_kill)
        sock = os.path.join(tmp, SOCK_NAME)
        args = [binp, "--model", model_path, "--host", sock, "--ctx-size", str(ctx), "--parallel", "1"] + list(extra or [])
        for flag in ("--no-webui", "--offline", "--jinja", "--no-slots"):     # only what this build knows
            if flag in flags:
                args.append(flag)
        if "--no-webui" not in flags and "--no-ui" in flags:
            args.append("--no-ui")
        try:
            if len(sock.encode("utf-8")) > SOCK_MAX:      # (a temporary folder with a very long path: the system takes no such file)
                raise OSError(tr("s_ki_pfad_lang") % tmp)
            cmd = self._sealed_cmd(args, seal, sock) if seal else args
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=self._env(key, tmp),
                                    cwd=os.path.dirname(binp), close_fds=True)
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        self.sock, self.key, self.tmp = sock, key, tmp

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

    def _connect(self, timeout: int) -> http.client.HTTPConnection:
        """To the model -- the one place that decides where a model is talked to: always the socket file of the process this
        object started, never an address (there is none to set). chat, transcribe and embed speak OpenAI's formats over what
        this returns, with the key of that start. (A model service on another machine of your own would be a second answer
        here; nothing of that is built -- what it needs first is in ROADMAP.md under "Offen".)"""
        return _OnFile(self.sock, timeout=timeout)

    def _healthy(self) -> Optional[bool]:
        """True: ready; False: still loading; None: not reachable."""
        try:
            c = self._connect(3)
            c.request("GET", "/health")
            r = c.getresponse()
            r.read()
            c.close()
            return r.status == 200
        except (OSError, http.client.HTTPException):
            return None

    def _ask_file(self, sandbox: str) -> dict:
        """Asks the installed llama.cpp once whether it can listen on a socket file, and notes the answer (runtime.json)."""
        try:
            kept = dict(self._load("runtime.json"), **dict(zip(("version", "flags", "sock"), self._probe(self.runtime()["path"], sandbox))))
        except ValueError as e:
            self.state, self.error = "error", str(e)[:300]
            raise ModelError(self.error)
        self._save("runtime.json", kept)
        return self.runtime()

    def ensure(self, model_id: str, ctx: int, sandbox: str = "strict", cancel: Optional[threading.Event] = None, fallback: bool = True, eyes: bool = True) -> None:
        """The model runs and is ready (started if needed; another model, context size or sandbox: started anew).
        sandbox: "strict" | "basic" | "off" -- exactly that, or no start at all. A new build that does not start it: _fall_back (ended at once with its picture part, also there: then _without_part)."""
        sandbox = sandbox if sandbox in SANDBOXES else "strict"
        with self.lock:
            seal = "" if sandbox == "off" or (not self._can_seal() and sys.platform != "darwin") else sandbox     # (not a Mac: there is no sandbox-exec)
            rt, m = self.runtime(), self.models().get(model_id)
            if self.proc is not None and self.proc.poll() is None and self.state == "ready" and (self.model, self.ctx, self.sealed) == (model_id, ctx, seal) \
                    and (not m or self.file == (m["path"], str(m.get("sha256") or ""))):
                self.last_used = time.time()
                return
            if not rt:
                raise ModelError(tr("s_ki_nicht_installiert"))
            if not m:
                raise ModelError(tr("s_ki_modell_fehlt"))
            if rt.get("sock") is None:                   # installed before Kontor asked whether it can listen on a file: asked now, once
                rt = self._ask_file(sandbox)
            if not rt.get("sock"):                       # never on an address instead -- a newer llama.cpp can
                self.state, self.error = "error", tr("s_ki_zu_alt")
                raise ModelError(self.error)
            ram = physical_ram()
            if ram and int(m.get("size") or 0) + 2 ** 30 > ram:        # larger than the memory itself: it would only swap, the Mac with it
                raise ModelError(tr("s_ki_passt_nicht") % (round(m["size"] / 1e9), round(ram / 2 ** 30)))
            self.stop()
            if seal and not self._can_seal():
                raise ModelError(tr("s_ki_sandbox_fehlt"))
            self.state, self.error, self.model, self.ctx, self.file = "starting", "", model_id, ctx, (m["path"], str(m.get("sha256") or ""))
            self.tail.clear()
            extra = self._part_args(rt, m, eyes)            # (a model that answers: its picture part, see eyes)
            if self.role == "embed":                     # the model for finding by meaning: embeddings only, each text in one piece
                flags = rt.get("flags") or []
                if "--embedding" not in flags or "--pooling" not in flags:
                    self.state, self.error = "error", tr("s_ki_einbettung_alt")
                    raise ModelError(self.error)
                extra = ["--embedding", "--pooling", "last"] + [x for f in ("--batch-size", "--ubatch-size") if f in flags for x in (f, str(ctx))]
            try:
                self.proc = self._spawn(rt["path"], rt.get("flags") or [], m["path"], ctx, seal, extra)
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
                    if self.role == "server" and eyes:            # the model that answers decides whether a new build holds (not one started blind)
                        self._proven(rt["path"])
                    return
                reached = reached or h is False                  # it answers "still loading": Kontor reaches it
                if time.time() - t0 > (START_SECONDS if reached else REACH_SECONDS):
                    break
                time.sleep(0.3)
            why, ended = " | ".join(list(self.tail)[-4:])[:500] or "llama-server", self.proc.poll() is not None      # ended: by itself, not never ready in time
            self._kill()
            self.state, self.sealed = "error", ""
            # never reached inside the sandbox: said so (the rules are yours to change, not tried weaker by itself)
            self.error = (tr("s_ki_sandbox_start") % why) if seal and not reached else why
            log.warning("Assistant: model did not start (sandbox: %s): %s", seal or "off", why[:300])
            if (fallback and self._fall_back(model_id, ctx, sandbox, cancel, self.error)) or (extra and ended and fallback and self.role == "server" and self._without_part(rt, m, model_id, ctx, sandbox, cancel)):
                return
            raise ModelError(tr("s_ki_startet_nicht") % self.error)

    def _part_args(self, rt: dict, m: dict, eyes: bool) -> Optional[List[str]]:
        """ensure: what starts a model with its second part -- a speech model always with its audio part; a model that answers
        with its picture part, unless it is not to see (eyes) or did not start with it under this build (blind)."""
        if not m.get("mmproj_path") or (self.role == "server" and (not eyes or self.blind == (rt.get("tag"), m["mmproj_path"]))):
            return None
        extra = ["--mmproj", m["mmproj_path"]]
        if self.role == "server" and "--image-max-tokens" in (rt.get("flags") or []):
            extra += ["--image-max-tokens", str(PICTURE_TOKENS)]       # a large photo scaled down to this, not the whole context
        return extra

    def _without_part(self, rt: dict, m: dict, model_id: str, ctx: int, sandbox: str, cancel: Optional[threading.Event]) -> bool:
        """ensure (in self.lock): the model ended at once with its picture part, and the build before (if there was one) did
        not start it either -- it starts without it (it answers, sees no pictures; so until Kontor restarts or another build
        of llama.cpp comes; such a start proves no build). True: it runs; does it not start that way either, the part was
        not the reason (its error is raised)."""
        log.warning("Assistant: model %s starts without its picture part", model_id)
        self.blind = (self.runtime().get("tag"), m["mmproj_path"])
        try:
            self.ensure(model_id, ctx, sandbox, cancel, False, eyes=False)
        except ModelError:
            self.blind = None                             # (tried with it again next time)
            raise
        return True

    def _fall_back(self, model_id: str, ctx: int, sandbox: str, cancel: Optional[threading.Event], why: str) -> bool:
        """ensure: a newly installed build of llama.cpp did not start the model that answers -- the build before it tries (in
        self.lock). True: it runs (the new build is never installed again); False: nothing to go back to, or the build before
        does not start it either (then the new one stays: it is not the build)."""
        new = self._give_way() if self.role == "server" else None
        if new is None:
            return False
        prev = self._load("runtime.json")
        try:
            self.ensure(model_id, ctx, sandbox, cancel, fallback=False)
        except (ModelError, Cancelled) as again:
            self._changing("")
            with runtime_lock(self.base):                # back to the new build, unless something was installed meanwhile
                if self._load("runtime.json") == prev:
                    self._save("runtime.json", new)
            if isinstance(again, Cancelled):
                raise
            self.state, self.error = "error", why
            return False
        with runtime_lock(self.base):
            if self._load("runtime.json") == prev:
                tags = self.bad_builds() + [str(new.get("tag") or "")[:40]]
                self._save("runtime-bad.json", {"tags": tags[-50:]})
                self._tidy_runtime(str(prev.get("dir") or ""))
        log.warning("Assistant: llama.cpp %s did not start the model -- back to %s", new.get("tag"), self.runtime().get("tag"))
        return True

    @property
    def caps(self) -> Dict[str, Any]:
        """What the running model's chat template can do, as llama.cpp tells it (/props, over its socket file with this start's key;
        asked once for each start): {"levels": the levels of thinking the template knows (reasoning_effort, lowest first),
        "rejected": those it refuses, "preserve": earlier thoughts stay in the conversation, "vision": it reads pictures (its
        picture part is loaded)} -- {} when no model runs or the build does not say (an older llama.cpp): nothing is assumed."""
        p = self.proc
        pid = p.pid if p is not None and p.poll() is None and self.state == "ready" else 0
        if not pid:
            return {}
        if self._told[0] != pid:
            told = self._props()
            if told is None:                             # not reached right now: asked again with the next question
                return {}
            self._told = (pid, told)
        return self._told[1]

    @caps.setter
    def caps(self, told: Dict[str, Any]) -> None:
        self._told = (self.proc.pid if self.proc is not None else 0, dict(told))

    def _props(self) -> Optional[Dict[str, Any]]:
        """None: the model did not answer (busy, just ending)."""
        try:
            c = self._connect(10)
            c.request("GET", "/props", headers={"Authorization": "Bearer " + self.key})
            r = c.getresponse()
            raw = r.read(4 << 20)
            c.close()
            d = json.loads(raw.decode("utf-8", "replace")) if r.status == 200 else {}
        except (OSError, http.client.HTTPException):
            return None
        except ValueError:
            return {}
        return template_caps(d)

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
        tmp, self.tmp, self.sock = self.tmp, "", ""
        if tmp:                                          # its temporary folder of that start (with its socket file)
            shutil.rmtree(tmp, ignore_errors=True)
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

    def settle(self, seconds: float = 2.0) -> None:
        """After a request that failed: a process that is ending (it fell over) is waited for a moment -- ensure then sees it
        gone and starts it anew, instead of finding it still there and failing again."""
        p = self.proc
        if p is not None:
            try:
                p.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                pass

    def chat(self, body: dict, cancel: threading.Event) -> Iterator[dict]:
        """One answer of the model as its stream of pieces (OpenAI's chat format). Only ever the model Kontor started: over
        its socket file (_connect), with the key of that start."""
        if self.state != "ready" or self.proc is None or self.proc.poll() is not None:
            raise ModelError(tr("s_ki_laeuft_nicht"))
        conn = self._connect(900)
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
                    err = piece.get("error")
                    if err and not piece.get("choices"):   # llama.cpp ends a stream it has begun with its error as the last piece:
                        msg = err.get("message") if isinstance(err, dict) else err      # said, never taken for an answer without words
                        raise StreamError(tr("s_ki_antwortet_nicht") % str(msg or "error")[:200])
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
        over its socket file with this start's key."""
        if self.state != "ready" or self.proc is None or self.proc.poll() is not None:
            raise ModelError(tr("s_ki_laeuft_nicht"))
        mark = "kontor" + secrets.token_hex(12)
        field = lambda name, value: ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (mark, name, value)).encode("utf-8")
        body = (field("response_format", "json") + field("temperature", "0") + (field("language", language) if re.fullmatch(r"[a-z]{2}", language or "") else b"")
                + ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n" % mark).encode("utf-8") + wav
                + ("\r\n--%s--\r\n" % mark).encode("utf-8"))
        conn = self._connect(300)
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

    def embed(self, texts: List[str], query: bool = False, task: str = "") -> List[List[float]]:
        """Each text as its embedding, by the model for finding by meaning that runs -- llama.cpp's /v1/embeddings over its
        socket file with this start's key; query: the texts are questions (said so to the model, with what is looked for: task, else the
        model's own). Each cut to EMBED_DIMS numbers and to length 1, so that comparing two is one sum of products."""
        if self.state != "ready" or self.proc is None or self.proc.poll() is not None:
            raise ModelError(tr("s_ki_laeuft_nicht"))
        entry = next((c for c in EMBED if c["id"] == self.model), {})
        head = entry.get("query", "%s") % (task or entry.get("task", "")) if query and entry.get("query") else ""
        given = [head + str(t)[:EMBED_TEXT] + entry.get("eos", "") for t in texts]
        conn = self._connect(300)
        self.busy, self.last_used = True, time.time()
        try:
            conn.request("POST", "/v1/embeddings", json.dumps({"input": given, "encoding_format": "float"}).encode("utf-8"),
                         {"Content-Type": "application/json", "Authorization": "Bearer " + self.key})
            resp = conn.getresponse()
            raw = resp.read(64 * 1024 * 1024).decode("utf-8", "replace")
            try:
                data = json.loads(raw)
            except ValueError:
                data = {}
            if resp.status != 200 or not isinstance(data, dict) or not isinstance(data.get("data"), list):
                raise ModelError(str(((data.get("error") or {}) if isinstance(data, dict) else {}).get("message") or raw)[:300])
            rows = sorted((r for r in data["data"] if isinstance(r, dict) and isinstance(r.get("index"), int)), key=lambda r: r["index"])
            out: List[List[float]] = []
            for r in rows:
                v = r.get("embedding")
                if not isinstance(v, list) or len(v) < EMBED_DIMS or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in v[:EMBED_DIMS]):
                    raise ModelError(tr("s_ki_antwortet_nicht") % "embedding")
                v = [float(x) for x in v[:EMBED_DIMS]]
                n = math.sqrt(sum(x * x for x in v)) or 1.0
                out.append([x / n for x in v])
            if len(out) != len(given):
                raise ModelError(tr("s_ki_antwortet_nicht") % "embedding")
            return out
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
        rt, have, news, begun = self.runtime(), self.models(), self.news, self.begun()
        ram = physical_ram()
        size = lambda m: int(m["size"]) + (int((m.get("mmproj") or {}).get("size") or 0) if m.get("mmproj_path") else 0)     # with its audio or picture part
        models = []
        for c in CATALOG:
            m, fits = have.get(c["id"]), fit(c["gb"], c["ram"], ram)
            models.append({"id": c["id"], "name": c["name"], "repo": c["repo"], "note": c["note"], "gb": c["gb"], "ram": c["ram"], "fit": fits,
                           "kind": c["kind"], "maker": c["maker"], "licence": c["licence"], "needs": least_ram(c["gb"]) if fits == "big" else 0,
                           "installed": bool(m), "size": size(m) if m else 0, "file": m["file"] if m else "", "custom": False,
                           "partial": (begun.get(c["id"]) or {}).get("bytes", 0),
                           "newer": bool(((news.get("models") or {}).get(c["id"]) or {}).get("newer"))})
        speech = [{"id": c["id"], "name": c["name"], "repo": c["repo"], "note": c["note"], "gb": c["gb"], "installed": c["id"] in have,
                   "size": size(have[c["id"]]) if c["id"] in have else 0,
                   "file": have[c["id"]]["file"] if c["id"] in have else "", "newer": bool(((news.get("models") or {}).get(c["id"]) or {}).get("newer"))} for c in SPEECH]
        embed = [{"id": c["id"], "name": c["name"], "repo": c["repo"], "note": c["note"], "gb": c["gb"], "installed": c["id"] in have,
                  "size": have[c["id"]]["size"] if c["id"] in have else 0, "file": have[c["id"]]["file"] if c["id"] in have else "",
                  "newer": bool(((news.get("models") or {}).get(c["id"]) or {}).get("newer"))} for c in EMBED]
        for mid, m in have.items():
            if mid in SPEECH_IDS or mid in EMBED_IDS:
                continue
            if not any(c["id"] == mid for c in CATALOG):
                models.append({"id": mid, "name": m.get("name") or m["file"], "repo": m["repo"], "note": "", "gb": 0, "ram": 0, "fit": fit(m["size"] / 1e9, None, ram),
                               "kind": "", "maker": "", "licence": "", "needs": 0, "installed": True, "size": size(m), "file": m["file"], "custom": True,
                               "partial": (begun.get(mid) or {}).get("bytes", 0),
                               "newer": bool(((news.get("models") or {}).get(mid) or {}).get("newer"))})
        for mid, b in begun.items():                        # a model of your own whose download did not arrive whole: to go on with or to remove
            if mid not in have and not any(c["id"] == mid for c in CATALOG + SPEECH + EMBED):
                models.append({"id": mid, "name": plain_name(b["files"][0])[:-5], "repo": b["repo"], "note": "", "gb": 0, "ram": 0, "fit": fit(b["size"] / 1e9, None, ram),
                               "kind": "", "maker": "", "licence": "", "needs": 0, "installed": False, "size": b["size"], "file": b["files"][0], "custom": True,
                               "partial": b["bytes"], "newer": False})
        try:
            free = shutil.disk_usage(self.base if os.path.isdir(self.base) else self.data_dir).free
        except OSError:
            free = 0
        running = self.proc is not None and self.proc.poll() is None
        return {"platform": {"system": sys.platform, "build": asset_tag(), "ram": ram, "can_seal": self._can_seal()},
                "runtime": {"installed": bool(rt), "tag": rt.get("tag", ""), "version": rt.get("version", ""), "date": rt.get("installed", ""),
                            "latest": (news.get("runtime") or {}).get("tag", ""), "newer": bool((news.get("runtime") or {}).get("newer"))},
                "models": models, "speech": speech, "embed": embed, "recommended": recommended(ram), "checked": news.get("at", ""), "check_error": news.get("error", ""),
                "server": dict({"state": self.state if running or self.state in ("error", "starting") else "stopped", "model": self.model if running else "",
                                "since": int(time.time() - self.since) if running and self.since else 0, "sealed": self.sealed if running else "",
                                "busy": self.busy, "error": self.error if self.state == "error" else "", "tps": self.tps, "context": self.ctx if running else 0},
                               **(self.usage() if running else {})),
                "job": self.job_view(), "disk_free": free}
