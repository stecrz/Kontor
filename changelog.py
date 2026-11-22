"""What changed in Kontor, for the page Settings -> Updates: the versions of CHANGELOG.md grouped by major version, each
with its short overview from HIGHLIGHTS.md. A major version X.Y.0 closes the steps before it: 3.17 holds 3.16.1 ... 3.17.0
(the sub-versions are steps towards the next major version, which brings them after a final review); steps whose major
version is not out yet are "in progress". Reads only these two files of the program folder -- kept apart from updates.py,
the updater, which an update checks with special care."""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
HEADING_RE = re.compile(r"^##\s+v?(\S+)(?:\s+\((\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?)\))?")      # "## 3.16.53 (2026-11-21 23:28)"
DEV_RE = re.compile(r"^\s*[-*]\s+(?:Entwicklung|Development)\s*:")      # rules, tests, CI -- nothing the user notices
TOPIC_RE = re.compile(r"^\s*[-*]\s+([^:]{1,40}):\s")                         # "- KI-Assistent: ..." -> "KI-Assistent"


def _vtuple(v: str) -> Tuple[int, ...]:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(x) for x in nums[:4]) or (0,)


SERIES_RE = re.compile(r"^##\s+v?(\d+\.\d+)\s*$")          # HIGHLIGHTS.md: "## 3.16"
BULLET_RE = re.compile(r"^\s*[-*]\s+\S")


def release_of(version: str) -> str:
    """The major version a version belongs to: 3.16.0 -> 3.16 (it closes the steps before it), 3.16.53 -> 3.17 (a step
    towards it), 3.0 -> 3.0."""
    nums = [int(x) for x in re.findall(r"\d+", version or "")[:3]]
    if not nums:
        return ""
    major, minor, step = (nums + [0, 0])[:3]
    return "%d.%d" % (major, minor + 1 if step else minor)


def highlights(text: str) -> Dict[str, List[str]]:
    """HIGHLIGHTS.md: die Punkte je Hauptversion ("## 3.16", darunter "- ...")."""
    out: Dict[str, List[str]] = {}
    cur: Optional[List[str]] = None
    for line in (text or "").splitlines():
        m = SERIES_RE.match(line)
        if m:
            cur = out.setdefault(m.group(1), [])
        elif re.match(r"^#{1,2}\s", line):         # another heading of the first two levels ends the block
            cur = None
        elif cur is not None and BULLET_RE.match(line):
            cur.append(line.strip())
    return out


def group_changelog(text: str, hl_text: str = "") -> List[Dict[str, object]]:
    """All versions by major version (newest first): first and last version, whether the major version itself is out
    ("released"), period (date of the oldest to the newest version), count, the overview from HIGHLIGHTS.md (none: the
    topics named most often, no development) and the sections of the single versions as Markdown (as in CHANGELOG.md)."""
    hl = highlights(hl_text)
    groups: Dict[str, Dict[str, object]] = {}
    for part in re.split(r"\n(?=##\s)", "\n" + (text or "")):
        m = HEADING_RE.match(part)
        s = release_of(m.group(1)) if m else ""
        if not s:
            continue
        g = groups.setdefault(s, {"series": s, "parts": [], "versions": [], "dates": [], "topics": {}})
        g["parts"].append(part.strip())
        g["versions"].append(m.group(1).lstrip("v"))
        if m.group(2):
            g["dates"].append((_vtuple(m.group(1)), m.group(2)))
        for line in part.splitlines()[1:]:
            tm = TOPIC_RE.match(line)
            if tm and not DEV_RE.match(line):
                k = tm.group(1).strip()
                g["topics"][k] = g["topics"].get(k, 0) + 1
    out = []
    for s in sorted(groups, key=_vtuple, reverse=True):
        g = groups[s]
        dates = sorted(g["dates"])
        top = sorted(g["topics"].items(), key=lambda kv: -kv[1])[:5]            # stable: equal counts keep the newest first
        vs = sorted(g["versions"], key=_vtuple)
        out.append({"series": s, "count": len(g["parts"]), "first": vs[0], "last": vs[-1], "released": _vtuple(vs[-1])[:2] == _vtuple(s)[:2],
                    "from": dates[0][1] if dates else "", "to": dates[-1][1] if dates else "",
                    "highlights": hl.get(s, []), "topics": [] if hl.get(s) else [k for k, _ in top], "text": "\n\n".join(g["parts"])})
    return out


def _read(name: str, limit: int = 2000000) -> str:
    try:
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            return f.read(limit)
    except OSError:
        return ""


def history() -> List[Dict[str, object]]:
    """Die Aenderungen der installierten Version je Hauptversion (fuer die Anzeige unter Updates)."""
    return group_changelog(_read("CHANGELOG.md"), _read("HIGHLIGHTS.md"))
