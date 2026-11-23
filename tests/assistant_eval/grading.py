"""Grading an answer by itself: a figure to the cent, words, a JSON schema, the order of tool calls, an honest "I do not know".

Each grader returns a score between 0 and 1 (parts count) and "passed" (only with the full score). A figure is looked for in
the line after "ANTWORT:" if the answer has one, else in the whole answer -- Kontor's assistant puts the figure first, not
last. (From the test set jarvis-lab, where the model is told to end with such a line.)
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Sequence

import numparse as P
from schema import extract_json, validate

# how a model says plainly that it does not know, or that what it was given does not tell (normalised)
ABSTAIN = [
    "weiss ich nicht", "weiss es nicht", "weiss nicht", "nicht bekannt", "unbekannt", "keine information", "keine informationen",
    "keine angabe", "keine daten", "liegen mir nicht vor", "liegt mir nicht vor", "liegen mir keine", "liegt mir keine",
    "liegen keine", "liegt keine", "nicht ermitteln", "nicht beantworten", "kann ich nicht sagen", "kann ich nicht wissen",
    "kann ich nicht verlaesslich", "nicht vorhersagen", "nicht vorhersehbar", "nicht absehbar", "nicht verlaesslich",
    "keine verlaessliche", "habe ich keine", "habe keine", "nicht moeglich", "nicht enthalten", "nicht in den unterlagen",
    "nicht feststellbar", "keinen zugriff", "kein zugriff", "nicht seriös", "nicht serioes", "nicht sicher sagen",
    "kann nicht sagen", "kann dazu nichts", "nicht genannt", "nicht angegeben", "nicht hervor", "nicht aufgefuehrt",
    "nicht ableiten", "nicht nachpruefen", "nicht pruefen", "spekulieren", "spekulation", "fiktiv", "erfunden",
    "nicht bekannte", "nicht verfuegbar", "keine kenntnis", "keine belastbar", "nicht beurteilen", "nicht ohne weitere",
    "nicht zuverlaessig", "kann ich nicht", "nicht mitgeteilt", "nicht vorliegen",
]


# --------------------------------------------------------------------------------------------- matchers (args, JSON)
def _as_number(v: Any) -> Optional[List[float]]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return [float(v)]
    if isinstance(v, str):
        ns = P.numbers(v)
        if len(ns) == 1:
            return ns[0].values
    return None


def _month_of(v: Any) -> Optional[str]:
    s = str(v or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})(?:-\d{2})?", s)
    if m:
        return "%s-%s" % (m.group(1), m.group(2))
    m = re.match(r"^(?:\d{1,2}\.)?(\d{1,2})[./](\d{4})$", s)
    if m:
        return "%s-%02d" % (m.group(2), int(m.group(1)))
    return None


def _date_of(v: Any) -> Optional[str]:
    s = str(v or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return s[:10]
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
    return None


def _maybe_json(v: Any) -> Any:
    if isinstance(v, str) and v.strip()[:1] in "[{":
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def match_value(actual: Any, m: Any) -> bool:
    """Whether a value meets a matcher ({"eq"}, {"contains"}, {"num"}, {"month"}, {"date"}, {"in"}, {"regex"}, {"has"},
    {"any"}, {"not"}, {"exists"}, {"absent"}, {"len"}). A plain value means {"eq": value}."""
    if not isinstance(m, dict):
        m = {"eq": m}
    if "any" in m:
        return any(match_value(actual, x) for x in m["any"])
    if "not" in m:
        return not match_value(actual, m["not"])
    if m.get("absent"):
        return actual in (None, "", [], {}, False)
    if m.get("exists"):
        return actual not in (None, "", [], {})
    if "eq" in m:
        e = m["eq"]
        if isinstance(e, str):
            return isinstance(actual, (str, int, float)) and P.norm(str(actual)) == P.norm(e)
        if isinstance(e, bool):
            return actual is e
        if isinstance(e, (int, float)):
            vals = _as_number(actual)
            return bool(vals) and any(abs(v - e) < 1e-9 for v in vals)
        return actual == e
    if "contains" in m:
        hay = P.norm(actual if isinstance(actual, str) else json.dumps(actual, ensure_ascii=False))
        needles = m["contains"] if isinstance(m["contains"], list) else [m["contains"]]
        return any(P.norm(n) in hay for n in needles)
    if "num" in m:
        vals = _as_number(actual)
        return bool(vals) and any(P.matches(v, float(m["num"]), float(m.get("tol", 0.005)), "any" if m.get("abs") else "strict") for v in vals)
    if "month" in m:
        return _month_of(actual) == m["month"]
    if "date" in m:
        return _date_of(actual) == m["date"]
    if "in" in m:
        return isinstance(actual, str) and P.norm(actual) in [P.norm(x) for x in m["in"]]
    if "regex" in m:
        return isinstance(actual, str) and re.search(m["regex"], actual, re.I) is not None
    if "has" in m:
        actual = _maybe_json(actual)
        if not isinstance(actual, list):
            return False
        spec = m["has"]
        return any(match_args(x, spec) if isinstance(spec, dict) and not _is_matcher(spec) else match_value(x, spec) for x in actual)
    if "has_all" in m:
        return all(match_value(actual, {"has": spec}) for spec in m["has_all"])
    if "len" in m:
        actual = _maybe_json(actual)
        return isinstance(actual, (list, str)) and len(actual) == m["len"]
    raise ValueError("unknown matcher %r" % m)


_MATCHER_KEYS = {"eq", "contains", "num", "month", "date", "in", "regex", "has", "has_all", "any", "not", "exists", "absent", "len"}


def _is_matcher(d: dict) -> bool:
    """A matcher ({"contains": "x"}) or a map of fields to matchers ({"month": {"month": "2026-11"}})? Field maps hold only
    dicts; a matcher has at least one plain value (the one exception, {"not": {...}}, is a matcher)."""
    if not d or not set(d) <= _MATCHER_KEYS | {"tol", "abs"}:
        return False
    return set(d) == {"not"} or not all(isinstance(v, dict) for v in d.values())


def _get(obj: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def match_args(args: Any, spec: Dict[str, Any]) -> bool:
    if not isinstance(args, dict):
        return False
    for key, m in spec.items():
        val = _get(args, key)
        if isinstance(m, dict) and m.get("absent"):
            if not match_value(val, m):
                return False
        elif not match_value(val, m):
            return False
    return True


def match_step(call: dict, step: dict) -> bool:
    names = step.get("name")
    names = names if isinstance(names, list) else [names]
    if call.get("name") not in names:
        return False
    if call.get("arguments") is None:
        return not step.get("args")
    return match_args(call["arguments"], step.get("args") or {})


def ordered_hits(calls: Sequence[dict], steps: Sequence[dict]) -> int:
    """How many steps are met by the calls in their order (other calls in between are allowed) – longest common subsequence."""
    n, k = len(calls), len(steps)
    dp = [[0] * (k + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, k + 1):
            dp[i][j] = max(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1] + (1 if match_step(calls[i - 1], steps[j - 1]) else 0))
    return dp[n][k]


def unordered_hits(calls: Sequence[dict], steps: Sequence[dict]) -> int:
    return sum(1 for s in steps if any(match_step(c, s) for c in calls))


# ------------------------------------------------------------------------------------------------------------ graders
MANY = 60          # more numbers than this in an answer without an answer line: it lists figures instead of naming one


def _scope(answer: str):
    line = P.answer_line(answer)
    if line is not None:
        return line, True
    return answer or "", False


def _numbers(spec: dict, answer: str, calls) -> dict:
    values = spec["values"] if "values" in spec else [spec["value"]]
    tol, sign, pct = float(spec.get("tol", 0.005)), spec.get("sign", "strict"), bool(spec.get("percent"))
    scope, fmt = _scope(answer)
    found = [P.find_value(scope, float(v), tol, sign, pct) for v in values]
    count = len(P.numbers(scope))
    frac = sum(found) / len(values)
    note = ""
    if count > len(values) + (6 if fmt else MANY):
        frac, note = 0.0, "too many numbers (%d)" % count
    return {"score": frac, "passed": frac == 1.0, "format_ok": fmt, "details": {"found": found, "scope": scope[:300], "note": note}}


def _keywords(spec: dict, answer: str, calls) -> dict:
    t = P.norm(answer)
    req = spec.get("all", [])
    hits = []
    for item in req:
        alts = item if isinstance(item, list) else [item]
        hits.append(any(P.has_keyword(t, a) for a in alts))
    bad = [kw for kw in spec.get("none", []) if P.has_keyword(t, kw)]
    frac = (sum(hits) / len(hits)) if hits else 1.0
    if bad:
        frac = 0.0
    return {"score": frac, "passed": frac == 1.0, "format_ok": None, "details": {"hits": hits, "forbidden": bad}}


def _regex(spec: dict, answer: str, calls) -> dict:
    ok = re.search(spec["pattern"], answer.strip(), re.I | re.M) is not None
    return {"score": 1.0 if ok else 0.0, "passed": ok, "format_ok": None, "details": {"pattern": spec["pattern"]}}


def _abstain(spec: dict, answer: str, calls) -> dict:
    t = P.norm(answer)
    said = [p for p in ABSTAIN if p in t]
    bad = [r for r in spec.get("forbid", []) if re.search(r, t)]
    ok = bool(said) and not bad
    return {"score": 1.0 if ok else 0.0, "passed": ok, "format_ok": None, "details": {"abstained": said[:3], "forbidden": bad}}


def _json(spec: dict, answer: str, calls) -> dict:
    val, how = extract_json(answer)
    if val is None:
        return {"score": 0.0, "passed": False, "format_ok": False, "details": {"error": "no JSON found"}}
    errs = validate(val, spec.get("schema", {}))
    exp = spec.get("expect", {})
    hits = {k: match_value(_get(val, k), m) for k, m in exp.items()}
    frac = (sum(hits.values()) / len(hits)) if hits else 1.0
    score = 0.25 * (not errs) + 0.75 * frac
    return {"score": score, "passed": not errs and frac == 1.0, "format_ok": how != "none",
            "details": {"schema_errors": errs[:5], "fields": hits}}


def _tools(spec: dict, answer: str, calls) -> dict:
    paths = spec.get("paths") or [spec.get("steps", [])]
    best, best_path = 0.0, 0
    for i, steps in enumerate(paths):
        if not steps:
            continue
        hits = ordered_hits(calls, steps) if spec.get("ordered", True) else unordered_hits(calls, steps)
        if hits / len(steps) > best:
            best, best_path = hits / len(steps), i
    forbidden = [c for c in calls for f in spec.get("forbid", []) if match_step(c, f)]
    bad_args = sum(1 for c in calls if c.get("arguments") is None)
    tool_score = 0.0 if forbidden else best
    max_calls = spec.get("max_calls")
    if max_calls and len(calls) > max_calls:
        tool_score *= 0.5
    details: Dict[str, Any] = {"tool_score": round(tool_score, 3), "path": best_path, "calls": len(calls), "unparsed_args": bad_args,
                               "forbidden": [c["name"] for c in forbidden]}
    passed = tool_score == 1.0
    score, fmt = tool_score, None
    if spec.get("final"):
        fin = grade_spec(spec["final"], answer, calls)
        w = float(spec.get("final_weight", 0.5))
        score = (1 - w) * tool_score + w * fin["score"]
        passed = passed and fin["passed"]
        fmt = fin.get("format_ok")
        details["final"] = fin
    if forbidden:
        score = 0.0
    return {"score": score, "passed": passed, "format_ok": fmt, "details": details}


def _calc(spec: dict, answer: str, calls) -> dict:
    res = _numbers(spec, answer, calls)
    tool = spec.get("tool", "calculate")
    used = any(c.get("name") == tool and c.get("arguments") is not None for c in calls)
    res["score"] = res["score"] * (1.0 if used else 0.5)
    res["passed"] = res["passed"] and used
    res["details"]["tool_used"] = used
    return res


def _all(spec: dict, answer: str, calls) -> dict:
    parts = spec["parts"]
    out, total, wsum, passed, fmt = [], 0.0, 0.0, True, None
    for p in parts:
        w = float(p.get("weight", 1.0))
        r = grade_spec(p, answer, calls)
        out.append(r)
        total += w * r["score"]
        wsum += w
        passed = passed and r["passed"]
        if r.get("format_ok") is not None:
            fmt = r["format_ok"] if fmt is None else (fmt and r["format_ok"])
    return {"score": total / wsum if wsum else 0.0, "passed": passed, "format_ok": fmt, "details": {"parts": out}}


GRADERS: Dict[str, Callable[[dict, str, list], dict]] = {
    "number": _numbers, "numbers": _numbers, "keywords": _keywords, "regex": _regex, "abstain": _abstain,
    "json": _json, "tools": _tools, "calc": _calc, "all": _all,
}


def grade_spec(spec: dict, answer: str, calls: Optional[List[dict]] = None) -> dict:
    return GRADERS[spec["type"]](spec, answer or "", calls or [])


def grade(task: dict, answer: str, calls: Optional[List[dict]] = None) -> dict:
    """Grade one answer (the model's final text, reasoning already removed) and the tool calls it made."""
    r = grade_spec(task["grader"], P.strip_thinking(answer or ""), calls or [])
    r["score"] = round(max(0.0, min(1.0, r["score"])), 4)
    return r
