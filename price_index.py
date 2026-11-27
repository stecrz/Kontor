"""Prices in Germany month by month -- the consumer price index (Verbraucherpreisindex, VPI) of the Statistisches Bundesamt --
to show the balance sheet in today's purchasing power (Bilanz, switch "Kaufkraft").

A balance of month m in today's money = balance × level(today) / level(m). Up to the last month published, the level is the
VPI; after it (the running month, the plan) the area's inflation of Planung is assumed, so that the plan -- planned with that
very rate -- turns into today's money without a jump. Before January 1991 (the first month of the index for all of Germany)
it is unknown: no value then, never a guess.

What the program holds: the index since January 1991 (BUNDLED, 2020 = 100, as the Bundesbank published it on BUNDLED_AS_OF).
What Kontor fetches: newer months -- only while the switch is on (the page asks for its factors), at most once a day while a
newer month may be out (else every two weeks: the newest month may have been the Bundesbank's estimate), from the Deutsche
Bundesbank's time series interface (the same series, as it publishes it for Destatis), through the sealed web reader of the
assistant's internet search (web_reader.py: a process of its own, in the Mac's sandbox, https to this one host, GET, no
cookies). The address is fixed (it starts two years before the last month this version holds). Nothing of yours goes
out. What comes back is checked before it counts (one series of the index for Germany, months without a gap,
plausible values, the same as the bundled ones where both are final; a new base year -- 2025 = 100 one day -- is chained on
where both overlap) and kept in state.json ("price_index"). This part opens no connection itself.

Source: Statistisches Bundesamt (Destatis), Verbraucherpreisindex für Deutschland (GENESIS-Online 61111-0002),
Datenlizenz Deutschland – Namensnennung – Version 2.0 (dl-de/by-2-0, www.govdata.de/dl-de/by-2-0); fetched from the
Deutsche Bundesbank (series BBDP1.M.DE.N.VPI.C.A00000.I20.A). What Kontor computes from it is its own calculation.
"""
from __future__ import annotations

import logging
import math
import re
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Tuple

import web_search

log = logging.getLogger("kontor.prices")

BUNDLED_UNIT = "2020=100"
BUNDLED_AS_OF = "2026-11-27"
# the index, one line a year from January (as published: one decimal)
BUNDLED_TEXT = """
1991 60.5 60.8 60.8 61.0 61.1 61.5 62.2 62.2 62.2 63.2 63.4 63.5
1992 63.9 64.3 64.5 64.7 64.9 65.1 65.3 65.3 65.3 65.3 65.6 65.7
1993 66.8 67.3 67.5 67.7 67.8 68.0 68.3 68.3 68.2 68.2 68.3 68.5
1994 68.8 69.4 69.5 69.6 69.7 69.8 69.9 70.1 69.9 69.8 69.9 70.1
1995 70.4 70.8 70.8 70.9 70.9 71.0 71.2 71.2 71.2 71.0 71.0 71.2
1996 71.4 71.8 71.8 71.8 71.9 72.0 72.1 72.1 72.1 72.1 72.0 72.3
1997 72.9 73.0 73.0 72.9 73.1 73.1 73.8 73.8 73.7 73.6 73.6 73.8
1998 73.8 73.9 73.8 73.9 74.0 74.1 74.4 74.2 74.0 73.9 73.9 74.0
1999 73.9 74.0 74.0 74.4 74.4 74.5 74.8 74.8 74.6 74.5 74.7 74.9
2000 75.1 75.1 75.1 75.1 75.1 75.4 75.8 75.6 75.8 75.7 75.8 76.4
2001 76.2 76.6 76.6 76.9 77.2 77.3 77.4 77.2 77.2 77.1 76.9 77.7
2002 77.7 78.0 78.2 78.1 78.2 78.2 78.3 78.2 78.2 78.1 77.8 78.5
2003 78.5 79.0 79.0 78.8 78.6 78.9 79.0 79.0 79.0 79.0 78.8 79.4
2004 79.4 79.6 79.9 80.1 80.3 80.3 80.4 80.5 80.3 80.4 80.3 81.2
2005 80.6 80.9 81.3 81.0 81.2 81.3 81.7 81.8 81.9 81.9 81.7 82.3
2006 82.0 82.4 82.4 82.7 82.7 82.9 83.2 83.0 82.7 82.8 82.8 83.5
2007 83.5 83.8 84.0 84.4 84.4 84.5 84.9 84.8 84.9 85.1 85.6 86.1
2008 85.8 86.2 86.6 86.4 86.9 87.2 87.7 87.4 87.4 87.2 86.8 87.0
2009 86.6 87.1 87.0 87.0 87.0 87.3 87.3 87.5 87.1 87.2 87.1 87.8
2010 87.3 87.6 88.1 88.1 88.1 88.1 88.2 88.3 88.2 88.3 88.4 89.0
2011 88.7 89.3 89.8 89.8 89.8 89.9 90.1 90.2 90.3 90.4 90.5 90.7
2012 90.6 91.2 91.7 91.6 91.5 91.4 91.7 92.1 92.2 92.2 92.2 92.5
2013 92.1 92.6 93.0 92.6 93.0 93.1 93.5 93.5 93.5 93.3 93.5 93.9
2014 93.3 93.8 94.0 93.9 93.8 94.0 94.3 94.3 94.3 94.1 94.1 94.0
2015 93.1 93.8 94.3 94.7 94.9 94.9 95.1 95.0 94.9 94.9 94.3 94.3
2016 93.6 93.9 94.5 94.6 95.1 95.2 95.5 95.4 95.5 95.6 95.0 95.6
2017 95.1 95.6 95.8 96.2 96.2 96.5 96.9 97.0 97.0 96.9 96.5 96.9
2018 96.4 96.7 97.2 97.5 98.2 98.3 98.7 98.8 99.0 99.1 98.5 98.5
2019 97.7 98.1 98.5 99.4 99.6 99.9 100.3 100.2 100.2 100.2 99.5 100.0
2020 99.8 100.1 100.3 100.4 100.4 100.5 99.7 99.7 99.7 99.9 99.7 99.8
2021 101.0 101.6 102.1 102.4 102.6 102.9 103.4 103.5 103.8 104.3 104.5 104.7
2022 105.2 106.0 108.1 108.8 109.8 109.8 110.3 110.7 112.7 113.5 113.7 113.2
2023 114.3 115.2 116.1 116.6 116.5 116.8 117.1 117.5 117.8 117.8 117.3 117.4
2024 117.6 118.1 118.6 119.2 119.3 119.4 119.8 119.7 119.7 120.2 119.9 120.5
2025 120.3 120.8 121.2 121.7 121.8 121.8 122.2 122.3 122.6 123.0 122.7 122.7
2026 122.8 123.1 124.5 125.2 125.0 124.6 125.6 125.8 126.6 126.5
"""
HOST = "api.statistiken.bundesbank.de"
# every base year of the index for Germany (..): after a new base year the newest series is taken and chained on
URL = "https://api.statistiken.bundesbank.de/rest/data/BBDP1/M.DE.N.VPI.C.A00000..A?format=sdmx_csv&startPeriod=%s"
SERIES_RE = re.compile(r"BBDP1\.M\.DE\.N\.VPI\.C\.A00000\.I(\d{2})\.A")
UNIT_RE = re.compile(r"(\d{4})=100")
MONTH_RE = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")
STATE = "price_index"            # its key in state.json
MAX_BYTES = 1 << 20              # an answer larger than this is not read (two years of a few series: about 15 KB)
TIMEOUT = 15
BACK = 24                        # months asked for before the last bundled one (what comes back joins on; an estimate made final)
RETRY = 20 * 3600                # seconds between two tries while a newer month may be out (also after a failure)
AGAIN = 14 * 86400               # ... and while Kontor is up to date
TOLERANCE = 0.6                  # index points a final month may differ between the bundled and the fetched series
LINK_TOLERANCE = 0.03            # a new base year: joined at the first common months; after them the new series may differ by
                                 # up to 3 % (new weights from the base year on -- 2023 the rate of 2022 fell from 7.9 to 6.9 %)
LOW, HIGH, STEP = 10.0, 1000.0, 0.05     # plausible values, and at most 5 % from one month to the next


def _key(m: str) -> int:
    return int(m[:4]) * 12 + int(m[5:7]) - 1


def _month(k: int) -> str:
    return "%04d-%02d" % (k // 12, k % 12 + 1)


def add(m: str, n: int) -> str:
    return _month(_key(m) + n)


def month_of(d: date) -> str:
    return "%04d-%02d" % (d.year, d.month)


def _parse_bundled(text: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for line in text.split("\n"):
        parts = line.split()
        if parts:
            for i, v in enumerate(parts[1:]):
                out["%s-%02d" % (parts[0], i + 1)] = float(v)
    return out


BUNDLED: Dict[str, float] = _parse_bundled(BUNDLED_TEXT)
BUNDLED_FIRST, BUNDLED_LAST = min(BUNDLED), max(BUNDLED)


def _plausible(series: Dict[str, float]) -> bool:
    """Months without a gap, each value plausible, at most STEP from one month to the next."""
    if not series:
        return False
    ms = sorted(series)
    if any(not MONTH_RE.fullmatch(m) for m in ms) or _key(ms[-1]) - _key(ms[0]) != len(ms) - 1:
        return False
    vs = [series[m] for m in ms]
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not LOW <= v <= HIGH for v in vs):
        return False
    return all(abs(b / a - 1) <= STEP for a, b in zip(vs, vs[1:]))


def known(state: Optional[dict]) -> Dict[str, float]:
    """The index as Kontor knows it: the bundled one, with the months fetched (where they are kept in the bundled base and
    still fit on: no gap, plausible -- else the bundled one alone)."""
    st = state if isinstance(state, dict) else {}
    vals = st.get("values")
    if st.get("unit") != BUNDLED_UNIT or not isinstance(vals, dict) or not vals:
        return dict(BUNDLED)
    got = {str(m): v for m, v in vals.items()}
    if not _plausible(got) or not BUNDLED_FIRST < min(got) <= add(BUNDLED_LAST, 1):
        return dict(BUNDLED)
    out = dict(BUNDLED)
    out.update({m: float(v) for m, v in got.items()})
    return out if _plausible(out) else dict(BUNDLED)


def due(state: Optional[dict], today: date, now: float) -> bool:
    """Is it time to ask for newer months? While a newer month may be out (Kontor's last one is before last month): once a
    day; else every two weeks (the newest month may have been an estimate). Never twice within RETRY."""
    st = state if isinstance(state, dict) else {}
    tried, fetched = (float(st.get(k) or 0) for k in ("tried", "fetched_at"))
    tried, fetched = (0.0 if t > now else t for t in (tried, fetched))      # (a clock that once ran ahead blocks nothing)
    if now - tried < RETRY:
        return False
    if max(known(st)) < add(month_of(today), -1):
        return True
    return now - fetched >= AGAIN


def counts(state: Optional[dict]) -> bool:
    """Do the months fetched count (kept in the bundled base, fitting on)? Else the bundled index alone."""
    return known(state) != BUNDLED


def request() -> dict:
    """What the sealed reader is handed: the fixed address (from two years before the last month this version holds -- so
    that what comes back always joins on to it), this one host, GET, the same plain name as every request of the internet
    search -- nothing else."""
    start = add(BUNDLED_LAST, -BACK)
    url = URL % start
    return {"url": url, "hosts": [HOST], "method": "GET", "as": "csv", "max_bytes": MAX_BYTES, "max_text": 1000,
            "timeout": TIMEOUT, "user_agent": web_search.user_agent(url), "headers": {}}


def candidates(rows: Any, today: date) -> List[Tuple[str, str, Dict[str, float]]]:
    """The series of the index for Germany in the answer (SDMX-CSV rows) that pass (no gap, plausible values, nothing after
    the running month), the newest first: [(series, unit, {month: value})]. ValueError when there is none."""
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], list):
        raise ValueError("no rows")
    head = [str(h).strip().lstrip("﻿").upper() for h in rows[0]]
    need = ("TIME_PERIOD", "OBS_VALUE", "BBK_ID", "BBK_UNIT")
    if any(h not in head for h in need):
        raise ValueError("columns missing")
    t, v, k, u = (head.index(h) for h in need)
    now = month_of(today)
    series: Dict[Tuple[str, str], Dict[str, float]] = {}
    for r in rows[1:]:
        if not isinstance(r, list) or len(r) <= max(t, v, k, u):
            continue
        key, unit, m = str(r[k]).strip(), str(r[u]).strip(), str(r[t]).strip()
        if not SERIES_RE.fullmatch(key) or not UNIT_RE.fullmatch(unit) or not MONTH_RE.fullmatch(m) or m > now:
            continue
        if SERIES_RE.fullmatch(key).group(1) != UNIT_RE.fullmatch(unit).group(1)[2:]:
            continue                                      # the base year in the key and in the unit: the same
        try:
            val = float(str(r[v]).strip())
        except ValueError:
            continue
        series.setdefault((key, unit), {})[m] = val
    good = sorted(((max(s), int(UNIT_RE.fullmatch(ku[1]).group(1)), ku) for ku, s in series.items() if _plausible(s)), reverse=True)
    if not good:
        raise ValueError("no plausible series")
    return [(key, unit, series[(key, unit)]) for _, _, (key, unit) in good]


def parse(rows: Any, today: date) -> Tuple[str, str, Dict[str, float]]:
    """The newest series that passes (candidates)."""
    return candidates(rows, today)[0]


def merge(state: Optional[dict], unit: str, got: Dict[str, float]) -> Dict[str, float]:
    """The months fetched, in the bundled base -- checked against what Kontor knows. The same base: every month that is
    final on both sides (not the last two Kontor knows: they may have been estimates) within TOLERANCE. Another base (a new
    base year): chained on at the first months both have, every later one within LINK_TOLERANCE of what Kontor knew (the
    new weights change the months from the base year on; the new series counts). ValueError otherwise."""
    have = known(state)
    final = set(sorted(have)[:-2])
    both = sorted(m for m in got if m in final)
    if len(both) < 6:
        raise ValueError("too few months to compare (%d)" % len(both))
    if unit == BUNDLED_UNIT:
        off = [m for m in both if abs(got[m] - have[m]) > TOLERANCE]
        if off:
            raise ValueError("differs from the known index in %s" % ", ".join(off[:3]))
        scale = 1.0
    else:
        first = both[:3]                                   # (three months: less of the rounding to one decimal)
        scale = sum(have[m] / got[m] for m in first) / len(first)
        if any(abs(got[m] * scale / have[m] - 1) > LINK_TOLERANCE for m in both):
            raise ValueError("the new base does not chain on")
    out = {m: round(val * scale, 4) for m, val in got.items() if m >= both[0]}
    test = dict(have)
    test.update(out)
    if not _plausible(test) or min(out) <= BUNDLED_FIRST:
        raise ValueError("does not fit on")
    return out


def refresh(fetch: Callable[[dict], dict], state: Optional[dict], today: date, now: float) -> dict:
    """One try: the request to the sealed reader (fetch), the answer checked and merged. The new state for state.json --
    with the error when it failed (what Kontor knew stays)."""
    st = dict(state) if isinstance(state, dict) else {}
    st["tried"] = now
    try:
        res = fetch(request())
        if not isinstance(res, dict) or res.get("ok") is not True or not isinstance(res.get("data"), list):
            raise ValueError("no answer (%s)" % (str((res or {}).get("error") or "?")[:20] if isinstance(res, dict) else "?"))
        why = ""
        for key, unit, got in candidates(res["data"], today):         # the newest first; one that does not fit: the next
            try:
                vals = merge(state, unit, got)
                break
            except ValueError as e:
                why = why or str(e)
        else:
            raise ValueError(why)
    except (ValueError, OSError, web_search.WebError) as e:
        st["error"] = str(e)[:200]
        log.info("Prices: no newer index (%s)", st["error"])
        return st
    st.update(values=vals, unit=BUNDLED_UNIT, series=key, fetched=today.isoformat(), fetched_at=now, error="")
    log.info("Prices: index known until %s", max(known(st)))
    return st


def span(frm: str, to: str, most: int = 1200) -> List[str]:
    """The months from frm to to (YYYY-MM each, at most most of them); ValueError otherwise."""
    if not MONTH_RE.fullmatch(str(frm)) or not MONTH_RE.fullmatch(str(to)) or not 0 <= _key(to) - _key(frm) < most:
        raise ValueError("months: from and to as YYYY-MM, from before to")
    return [_month(k) for k in range(_key(frm), _key(to) + 1)]


def base_month(m: str, today: date) -> str:
    """The month whose money the figures are in: the running month as the page has it (its data may be from the month
    before), else today's."""
    now = month_of(today)
    return m if MONTH_RE.fullmatch(str(m)) and -2 <= _key(m) - _key(now) <= 1 else now


def rate_of(plan: Optional[dict]) -> float:
    """The area's inflation as Planung takes it (report.apply_plan), within -50 ... +100 % a year."""
    try:
        r = float((plan or {}).get("inflation_percent_pa", 2.0) or 0.0)
    except (TypeError, ValueError):
        r = 2.0
    return max(-50.0, min(100.0, r)) if math.isfinite(r) else 2.0


def level(series: Dict[str, float], m: str, rate: float) -> Optional[float]:
    """The price level of month m: the index; after its last month, that one growing with rate % a year; before its first:
    unknown (None)."""
    if m in series:
        return series[m]
    first, last = min(series), max(series)
    if m < first:
        return None
    return series[last] * (1 + rate / 100.0) ** ((_key(m) - _key(last)) / 12.0)


def factors(series: Dict[str, float], months: List[str], base: str, rate: float) -> dict:
    """Per month the factor that turns its balance into the money of month base: level(base) / level(m) (None: unknown).
    With what the page says about it: the last month of the index, its first, the rate assumed after it."""
    lb = level(series, base, rate)
    out: Dict[str, Optional[float]] = {}
    for m in months:
        lm = level(series, m, rate)
        out[m] = round(lb / lm, 10) if lb and lm else None
    return {"factors": out, "base": base, "known_until": max(series), "first": min(series), "rate": rate,
            "assumed": base > max(series) or any(m > max(series) for m in months)}


def _scale(d: dict, f: Dict[str, Optional[float]]) -> dict:
    return {m: None if v is None or f.get(m) is None else v * f[m] for m, v in d.items()}      # (a month without a factor: unknown)


def _month_map(d: Any) -> bool:
    return isinstance(d, dict) and bool(d) and all(isinstance(k, str) and MONTH_RE.fullmatch(k) for k in d)         and all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)) for v in d.values())


def deflate(balance: Any, f: Dict[str, Optional[float]]) -> Any:
    """A copy of a balance sheet (an area's "balance") with every amount by month in today's money: the rows, their
    securities, net worth, the plan. Not the equity ratio (a share, the same either way) nor accounts in another currency
    (never converted). The page does the same (web/app.js, realBalance)."""
    def walk(o: Any) -> Any:
        if _month_map(o):
            return _scale(o, f)
        if isinstance(o, dict):
            if o.get("role") == "foreign_currency":
                return o
            return {k: (v if k == "equity_ratio" else walk(v)) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(x) for x in o]
        return o
    return walk(balance)


__all__ = ["BUNDLED", "BUNDLED_UNIT", "HOST", "URL", "known", "counts", "due", "request", "candidates", "parse", "merge", "refresh", "span", "base_month",
           "rate_of", "level", "factors", "deflate", "add", "month_of"]
