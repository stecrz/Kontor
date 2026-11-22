"""What changed in Kontor, for the page Settings -> Updates: the versions of CHANGELOG.md grouped by major version (3.16,
3.15 ...), each with its short overview from HIGHLIGHTS.md. Reads only these two files of the program folder -- kept apart from
updates.py, the updater, which an update checks with special care."""
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


def series_of(version: str) -> str:
    """Hauptversion: 3.16.53 -> 3.16, 3.0 -> 3.0."""
    nums = re.findall(r"\d+", version or "")
    return ".".join((nums + ["0"])[:2]) if nums else ""


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
    """Alle Versionen nach Hauptversion (neueste zuerst): Zeitraum (Datum der aeltesten bis neuesten Version), Anzahl,
    der Ueberblick aus HIGHLIGHTS.md (fehlt er: die haeufigsten Bezuege als "topics", ohne Entwicklung) und die Abschnitte
    der einzelnen Versionen als Markdown (wie in CHANGELOG.md)."""
    hl = highlights(hl_text)
    groups: Dict[str, Dict[str, object]] = {}
    for part in re.split(r"\n(?=##\s)", "\n" + (text or "")):
        m = HEADING_RE.match(part)
        s = series_of(m.group(1)) if m else ""
        if not s:
            continue
        g = groups.setdefault(s, {"series": s, "parts": [], "dates": [], "topics": {}})
        g["parts"].append(part.strip())
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
        out.append({"series": s, "count": len(g["parts"]), "from": dates[0][1] if dates else "", "to": dates[-1][1] if dates else "",
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
