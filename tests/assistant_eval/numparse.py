"""Numbers and words in a model's answer -- read whatever the notation, German or English.

Every number in a text is taken in every reading its notation allows ("1.234" can be 1234 or 1.234); grading then asks
whether one reading meets the value expected. So "1.234,56 €" counts like "1234.56 EUR". (From the test set jarvis-lab.)
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Sequence

_TOKEN = re.compile(r"(?<![\w.,])(?P<neg>[-−–]\s?)?(?P<paren>\()?(?P<num>\d[\d.,  ']*\d|\d)(?P<tail>\)?-?)")
_SCALE = re.compile(r"\s*(?P<s>Mio\.?|Millionen|Mrd\.?|Milliarden|Tsd\.?|Tausend|T€|TEUR)", re.I)
_ANSWER = re.compile(r"(?im)^[ \t>*_#-]*(?:\*\*)?\s*(?:ANTWORT|Antwort|Ergebnis)\s*(?:\*\*)?\s*[:：]\s*(?:\*\*)?(?P<rest>.*)$")
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


class Num:
    """A number found in a text: where, as written, and every value it can mean."""

    __slots__ = ("text", "start", "end", "values")

    def __init__(self, text: str, start: int, end: int, values: List[float]):
        self.text, self.start, self.end, self.values = text, start, end, values

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "Num(%r, %r)" % (self.text, self.values)


def _grouped(parts: Sequence[str]) -> bool:
    """Thousands groups: the first 1-3 digits, every further group exactly 3."""
    return 1 <= len(parts[0]) <= 3 and all(len(p) == 3 for p in parts[1:]) and all(p.isdigit() for p in parts)


def readings(raw: str) -> List[float]:
    """All values a written number can have (without sign). Empty: no number (e.g. a date like 30.09.2034)."""
    s = raw.replace(" ", "").replace(" ", "").replace("'", "")
    if not s or not s[0].isdigit() or not s[-1].isdigit():
        return []
    has_dot, has_comma = "." in s, "," in s
    if not has_dot and not has_comma:
        return [float(s)]
    if has_dot and has_comma:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        whole, _, frac = s.rpartition(dec)
        if dec in whole or not frac.isdigit() or not _grouped(whole.split(thou)):
            return []
        return [float(whole.replace(thou, "") + "." + frac)]
    sep = "," if has_comma else "."
    parts = s.split(sep)
    out: List[float] = []
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        out.append(float(parts[0] + "." + parts[1]))             # decimal separator
    if len(parts) >= 2 and _grouped(parts):
        v = float("".join(parts))                                  # thousands separator
        if v not in out:
            out.append(v)
    return out


def numbers(text: str) -> List[Num]:
    """Every number in a text with its possible values (signed; "Mio." and the like scale it)."""
    out: List[Num] = []
    for m in _TOKEN.finditer(text or ""):
        vals = readings(m.group("num"))
        if not vals:
            continue
        neg = bool(m.group("neg")) or (bool(m.group("paren")) and m.group("tail").startswith(")")) or m.group("tail").endswith("-")
        # a dash right after a word or digit is a hyphen ("Q3-2026", "S-Bahn"), not a minus
        if m.group("neg") and m.start() > 0 and (text[m.start() - 1].isalnum()):
            neg = False
        sc = _SCALE.match(text, m.end())
        factor = 1.0
        if sc:
            w = sc.group("s").lower()
            factor = 1e6 if w.startswith("mio") or w.startswith("million") else 1e9 if w.startswith("mrd") or w.startswith("milliard") else 1e3
        out.append(Num(m.group(0), m.start(), m.end(), [(-v if neg else v) * factor for v in vals]))
    return out


def strip_thinking(text: str) -> str:
    """The answer without a <think>…</think> block (servers that do not split the reasoning off)."""
    t = _THINK.sub("", text or "")
    if "</think>" in t:                                             # opening tag swallowed by the template
        t = t.split("</think>", 1)[1]
    return t.strip()


def answer_line(text: str) -> Optional[str]:
    """The text after the last "ANTWORT:" line (None: there is none)."""
    found = list(_ANSWER.finditer(text or ""))
    if not found:
        return None
    rest = found[-1].group("rest").strip()
    if not rest:                                                     # "ANTWORT:" and the value on the next line
        after = text[found[-1].end():].strip().splitlines()
        rest = after[0].strip() if after else ""
    return rest


def last_paragraph(text: str) -> str:
    parts = [p for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]
    return parts[-1] if parts else ""


def matches(value: float, expected: float, tol: float, sign: str = "strict", percent: bool = False) -> bool:
    cands = [value]
    if percent:
        cands.append(value * 100.0)
    for v in cands:
        if sign == "any":
            if abs(abs(v) - abs(expected)) <= tol + 1e-9:
                return True
        elif abs(v - expected) <= tol + 1e-9:
            return True
    return False


def find_value(text: str, expected: float, tol: float = 0.005, sign: str = "strict", percent: bool = False) -> bool:
    return any(matches(v, expected, tol, sign, percent) for n in numbers(text) for v in n.values)


_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "–": "-", "—": "-", "−": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "„": '"'})


def norm(text: str) -> str:
    """Lower case, umlauts folded (ä → ae), markdown marks and extra white space removed."""
    t = unicodedata.normalize("NFKC", text or "").lower().translate(_FOLD)
    t = re.sub(r"[*_`#]+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def has_keyword(text_norm: str, kw: str) -> bool:
    """A keyword in a normalized text: "re:" a regular expression; a number with boundaries on both sides; words as a
    word start (so "widerspr" finds "widersprechen" and "Widerspruch")."""
    if kw.startswith("re:"):
        return re.search(kw[3:], text_norm) is not None
    k = norm(kw)
    if not k:
        return False
    if re.fullmatch(r"(19|20)\d\d", k):                                  # a year, also inside a date (30.09.2034)
        return re.search(r"(?<!\d)" + k + r"(?!\d)", text_norm) is not None
    if re.fullmatch(r"[\d.,% ]+", k):
        return re.search(r"(?<![\d.,])" + re.escape(k) + r"(?![\d]|[.,]\d)", text_norm) is not None
    return re.search(r"(?<![0-9a-z])" + re.escape(k), text_norm) is not None
