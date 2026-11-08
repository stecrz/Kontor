"""Names of securities by their ISIN, looked up at OpenFIGI -- only when the user asks for it (setup, "Historische
Kontostaende"), never on its own.

What leaves the Mac: only the ISINs of the securities that have no name in MoneyMoney -- no amounts, quantities, accounts,
names or anything else. HTTPS to one fixed host (api.openfigi.com, a free service for security identifiers), no API key.
What is kept: the names found (state "wp_suche", ISIN -> name), shown below your own names and MoneyMoney's; removable at
any time. MoneyMoney's own data (name, ISIN) is never changed and stays visible on hover.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from typing import Callable, Dict, Iterable, List, Optional
from urllib.parse import urlparse

log = logging.getLogger("kontor.securities")
URL = "https://api.openfigi.com/v3/mapping"
HOST = "api.openfigi.com"
BATCH = 10            # jobs per request without an API key
PAUSE = 2.6           # seconds between requests (at most 25 per minute without an API key)
TIMEOUT = 20
ISIN_RE = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")


def valid_isin(s: str) -> bool:
    """Format and check digit (letters as 10..35, then Luhn) -- nothing else is ever sent."""
    s = (s or "").strip().upper()
    if not ISIN_RE.fullmatch(s):
        return False
    digits = "".join(str(int(c, 36)) for c in s[:-1])
    total = 0
    for i, c in enumerate(reversed(digits)):
        d = int(c) * (2 if i % 2 == 0 else 1)
        total += d - 9 if d > 9 else d
    return (10 - total % 10) % 10 == int(s[-1])


def unnamed(history_wp: Dict[str, list], snapshots_wp: Dict[str, dict], seen_names: Dict[str, str], own: Dict[str, str],
            done: Iterable[str] = ()) -> List[str]:
    """ISINs of the securities without a name: in MoneyMoney's history (no name), in Kontor's monthly record (no name seen in
    MoneyMoney's export), and without a name of your own; those already looked up (found or not) are left out."""
    named = {k for k, v in (seen_names or {}).items() if v} | {k for k, v in (own or {}).items() if v}
    isins = set()
    for rows in (history_wp or {}).values():
        for w in rows or []:
            i = str(w.get("isin") or "").strip().upper()
            if i and not str(w.get("name") or "").strip():
                isins.add(i)
            elif i:
                named.add(i)
    for per in (snapshots_wp or {}).values():
        for vals in (per or {}).values():
            isins.update(k for k in (vals or {}) if not k.startswith("n:"))
    skip = named | {str(x).upper() for x in done}
    return sorted(i for i in isins if i not in skip and valid_isin(i))


def _post(jobs: list) -> list:
    req = urllib.request.Request(URL, data=json.dumps(jobs).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "Kontor"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if urlparse(r.geturl()).netloc != HOST:
            raise ValueError("redirect to another host: %s" % r.geturl())
        return json.loads(r.read(1 << 20).decode("utf-8"))


def lookup(isins: Iterable[str], post: Optional[Callable[[list], list]] = None, sleep: Callable[[float], None] = time.sleep) -> Dict[str, str]:
    """ISIN -> name for the ISINs OpenFIGI knows (the most frequent name of its listings). Invalid ISINs are never sent."""
    todo = sorted({str(i).strip().upper() for i in isins if valid_isin(str(i))})
    send = post or _post
    out: Dict[str, str] = {}
    for n in range(0, len(todo), BATCH):
        chunk = todo[n:n + BATCH]
        if n:
            sleep(PAUSE)
        jobs = [{"idType": "ID_ISIN", "idValue": i} for i in chunk]
        try:
            res = send(jobs)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            log.info("OpenFIGI: too many requests, waiting")
            sleep(7.0)
            res = send(jobs)
        for i, job in zip(chunk, res if isinstance(res, list) else []):
            names = [str(d.get("name") or "").strip() for d in ((job or {}).get("data") or []) if isinstance(d, dict)]
            names = [x for x in names if x]
            if names:
                out[i] = Counter(names).most_common(1)[0][0][:120]
        log.info("OpenFIGI: %d ISINs sent, %d names so far", min(n + BATCH, len(todo)), len(out))
    return out
