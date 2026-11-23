"""Everything foreign that Kontor uses, named for you (Einstellungen -> Updates -> "Verwendete Programme", and the help):
its name, its version, its licence, where it comes from, and whether it runs shielded. Foreign is what Kontor did not write
itself: the Python it runs in, llama.cpp and the models of the assistant, the tools macOS brings along -- and, later,
libraries.

One list for all of it:
  - a library that comes later needs one entry in LIBRARIES (and, once it is on this Mac, shows by itself);
  - a model the assistant's lists name needs its licence -- as "licence" in its entry there (llm_local), or in
    MODEL_LICENCES here.
tests/test_components.py asks for both, so nothing foreign comes without its name and licence.

This part only reads what is on this Mac (the state of Kontor's own Python, the assistant's lists of what is loaded). It
connects nowhere, starts nothing, and a licence or an address named on the page is always a fixed text from here -- never
something a downloaded file or a model says about itself.
"""
from __future__ import annotations

import platform
import sys
from typing import Any, Dict, List, Optional

import llm_local
import pyruntime

# where a part comes from: the page makes a link of the site's fixed address and this path (web/app.js, VP_SITES)
SITES = ("github", "huggingface", "apple")
# the licences by the names the settings use everywhere (Einstellungen -> KI-Assistent shows a model's the same way)
PYTHON = {"name": "Python", "licence": "PSF 2.0"}                  # CPython: Python Software Foundation License Version 2
# ... Kontor's own build carries other free software inside, among it OpenSSL (Apache 2.0) and SQLite (public domain) -- seen
# in the build itself; the licence texts of everything in it lie in its folder (python/lib/python3.x/LICENSE.txt). The page
# says so in its own words ("holds": web/i18n.js, vp_enthaelt)
LLAMA = {"name": "llama.cpp", "licence": "MIT"}                    # as the project's own LICENSE file and Kontor's NOTICE say
# The licence of a model stands in its entry of the assistant's lists ("licence" in llm_local.CATALOG, as its model card says).
# For the models of the lists whose entries name none (dictation, finding by meaning), by their repository on Hugging Face:
# what that repository's page names as "License" (looked up 2026-11-23). A model that comes later: "licence" in its entry.
MODEL_LICENCES: Dict[str, str] = {
    "ggml-org/Qwen3-ASR-1.7B-GGUF": "Apache 2.0",
    "ggml-org/Qwen3-ASR-0.6B-GGUF": "Apache 2.0",      # (its own page names none: as the model it is made from, Qwen/Qwen3-ASR-0.6B, names it)
    "Qwen/Qwen3-Embedding-0.6B-GGUF": "Apache 2.0",
}
# Libraries for shielded helpers (ROADMAP.md, "Bibliotheken in abgeschirmten Helfern"): none yet. One entry each --
#   {"id": "...", "name": "...", "version": "...", "licence": "MIT", "site": "github", "path": "owner/project",
#    "use": "vp_wofuer_...", "shielded": True}
# -- and it is named on the page as soon as it is on this Mac (`loaded` says which are).
LIBRARIES: List[Dict[str, Any]] = []
KINDS = ("python", "runtime", "model", "library", "system")
SHIELDS = ("strict", "basic", "off", "no")      # the Mac's sandbox around it, as set for the assistant -- or "no": it is not shielded


def model_licence(entry: Optional[dict], repo: str) -> str:
    """The licence of a model: named in its entry of the assistant's lists -- or in the entry of another variant from the
    same repository --, else here; "" when Kontor does not know it (a model you added by its repository: its page says)."""
    named = (entry or {}).get("licence") or next((c["licence"] for c in llm_local.CATALOG + llm_local.SPEECH + llm_local.EMBED
                                                  if c.get("repo") == repo and c.get("licence")), "")
    return str(named or MODEL_LICENCES.get(repo) or "")[:60]


def _item(kind: str, name: str, version: str, licence: str, site: str, path: str, shield: str, use: str, **more: Any) -> dict:
    return dict({"kind": kind if kind in KINDS else "system", "name": str(name)[:120], "version": str(version)[:60], "licence": str(licence)[:60],
                 "site": site if site in SITES else "", "path": str(path)[:200], "shielded": shield if shield in SHIELDS else "no", "use": use}, **more)


def python_item(st: dict) -> dict:
    """The Python the service runs in: Kontor's own (a build of python-build-standalone) or the Mac's (Apple's)."""
    run = st.get("running") or {}
    if run.get("own"):
        have = st.get("loaded") or {}
        return _item("python", PYTHON["name"], str(run.get("version") or ""), PYTHON["licence"], "github", "%s/releases/tag/%s" % (pyruntime.REPO, have.get("build") or pyruntime.BUILD),
                     "no", "vp_wofuer_python", holds=True, build=str(have.get("build") or "")[:20])
    return _item("python", PYTHON["name"], str(run.get("version") or ""), PYTHON["licence"], "apple", "", "no", "vp_wofuer_python_mac", ended=str(run.get("ended") or "")[:10])


def assistant_items(ai: Any, sandbox: str) -> List[dict]:
    """llama.cpp and every model on this Mac, as the assistant's own lists have them (llm_local.LocalAI)."""
    out: List[dict] = []
    shield = sandbox if sandbox in llm_local.SANDBOXES else "strict"
    rt = ai.runtime() or {}
    if rt:
        out.append(_item("runtime", LLAMA["name"], str(rt.get("tag") or rt.get("version") or ""), LLAMA["licence"], "github", llm_local.RUNTIME_REPO, shield, "vp_wofuer_llama"))
    named = {c["id"]: c for c in llm_local.CATALOG + llm_local.SPEECH + llm_local.EMBED}
    for mid, m in sorted((ai.models() or {}).items(), key=lambda kv: str(kv[1].get("name") or kv[0]).lower()):
        c = named.get(mid)
        use = "vp_wofuer_diktat" if mid in llm_local.SPEECH_IDS else "vp_wofuer_bedeutung" if mid in llm_local.EMBED_IDS else "vp_wofuer_modell"
        out.append(_item("model", str((c or {}).get("name") or m.get("name") or m.get("file") or mid), str(m.get("file") or ""), model_licence(c, str(m.get("repo") or "")),
                         "huggingface", str(m.get("repo") or ""), shield, use))
    return out


def loaded(program_dir: str) -> List[dict]:
    """The libraries of LIBRARIES that are on this Mac -- in their place beside Kontor's own Python (.python/libs/ in the
    program folder: pyruntime.LIBS). None yet: loading and checking them comes with the first one."""
    return []


def system_item() -> dict:
    """What macOS brings along and Kontor calls: openssl, osascript, the Swift compiler, the sandbox, text recognition."""
    mac = platform.mac_ver()[0] if sys.platform == "darwin" else ""
    return _item("system", "macOS", mac, "", "apple", "", "no", "vp_wofuer_macos")


def listing(python_status: dict, ai: Any = None, sandbox: str = "strict", program_dir: str = "") -> List[dict]:
    """The list for the page, in a fixed order: Python, llama.cpp, the models, libraries, macOS's own tools. ai: the
    assistant's LocalAI (None: the assistant is not there -- nothing of it is listed then)."""
    out = [python_item(python_status)]
    if ai is not None:
        out += assistant_items(ai, sandbox)
    for lib in loaded(program_dir):
        out.append(_item("library", lib["name"], lib["version"], lib["licence"], lib.get("site") or "", lib.get("path") or "",
                         "strict" if lib.get("shielded") else "no", str(lib.get("use") or "vp_wofuer_bibliothek")))
    out.append(system_item())
    return out
