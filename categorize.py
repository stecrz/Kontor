"""Categories: MoneyMoney is the only truth -- Kontor helps fill in what is still without one there.

* A transaction's category is the one in MoneyMoney. Kontor has no categories of its own and never overrides MoneyMoney.
* What has no category in MoneyMoney you assign in Kontor (Zuordnen); Kontor writes it into MoneyMoney right away (only the
  category field, see mm_categories) -- at the Mac directly, from elsewhere at the next sync at the Mac. Until it is written
  the assignment waits in Kontor (zuordnung: {"k": path, "q": "manuell", "p": 1}) and counts already.
* Kontor never assigns by itself: patterns learned from your categories are only suggestions.
* Fixed rules belong in MoneyMoney (settings of a category); Kontor proposes them in MoneyMoney's search syntax.
* MoneyMoney's default category ("Unkategorisiert") counts as none.

Everything is stored encrypted in categories.json. Paths are canonical 'A / B / C' (model.norm_cat)."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import operator
import re
import sys
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from model import Ledger, Tx, has_mark, norm_cat

FILE = "categories.json"
log = logging.getLogger("kontor.categorize")


def empty() -> dict:
    return {"version": 3, "assignment": {}, "rules": [], "learned_at": None}


def load(store) -> dict:
    """The stored state (empty when there is none or it has an unknown shape)."""
    d = store.load(FILE, None) or {}
    if d.get("version") != 3:
        return empty()
    d.setdefault("assignment", {}); d.setdefault("rules", [])
    return d


STANDARD: set = set()          # MoneyMoney's default category ("Unkategorisiert"): counts as none


def set_standard(categories: Optional[List[dict]]) -> None:
    """Remember MoneyMoney's default category from its category list (export_categories)."""
    global STANDARD
    if categories:
        STANDARD = {norm_cat(str(c.get("path") or c.get("name") or "")) for c in categories if c.get("default")}


LOCK = threading.RLock()        # writing the file; the report checks and writes under it (see core._prepare_categories)


def save(store, d: dict) -> None:
    with LOCK:
        store.save(FILE, {k: v for k, v in d.items() if not k.startswith("_")})      # "_..." = cache, not stored


def digest(d: dict) -> Dict[str, str]:
    """A fingerprint per part (assignments, rules ...): which parts changed since it was read."""
    return {k: hashlib.sha1(json.dumps(v, sort_keys=True, default=str).encode()).hexdigest() for k, v in d.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# A transaction's category
# ---------------------------------------------------------------------------

def mm_of(t: Tx) -> str:
    """The transaction's category in MoneyMoney (canonical; MoneyMoney's default category counts as none)."""
    p = norm_cat(t.mm_category_path if t.mm_category_path is not None else t.category_path)
    return "" if p in STANDARD else p


def waiting(z: Optional[dict]) -> bool:
    """An assignment you made in Kontor that waits to be written into MoneyMoney (at the next sync at the Mac)."""
    return bool(z and z.get("k") and z.get("p"))


def effective(d: dict, t: Tx) -> Tuple[str, str]:
    """(path, source): MoneyMoney's category; without one an assignment of yours that waits to be written ("wartet");
    otherwise ''."""
    mm = mm_of(t)
    if mm:
        return mm, "moneymoney"
    z = d["assignment"].get(str(t.id))
    if waiting(z):
        return z["k"], "waiting"
    return "", ""


def apply_to_ledger(d: dict, ledger: Ledger) -> Dict[str, int]:
    """Put the categories on the transactions in memory (MoneyMoney's, else a waiting assignment). Counts per source."""
    counts: Counter = Counter()
    for t in ledger.txs:
        if t.mm_category_path is None:
            t.mm_category_path = t.category_path
        path, q = effective(d, t)
        if q and q != "moneymoney":
            t.category_path = path.replace(" / ", "\\")
            t.category = path.split(" / ")[-1]
        elif q:
            t.category_path = t.mm_category_path
            t.category = norm_cat(t.mm_category_path).split(" / ")[-1] if t.mm_category_path else ""
        else:
            t.category_path, t.category = "", ""
        counts[q or "without"] += 1
    return dict(counts)


def set_waiting(d: dict, tx_ids: Iterable[int], path: str, only_empty: bool = False) -> int:
    """Your assignment, to be written into MoneyMoney ('' takes back what still waits). only_empty ("e"): from the assistant's
    card -- written, also later, only where MoneyMoney shows no category at all."""
    path = norm_cat(path)
    n = 0
    for tid in tx_ids:
        if path:
            d["assignment"][str(tid)] = dict({"k": path, "q": "manual", "p": 1}, **({"e": 1} if only_empty else {}))
        else:
            d["assignment"].pop(str(tid), None)
        n += 1
    return n


# ---------------------------------------------------------------------------
# Suggestions: learned from your categories (never applied by themselves)
# ---------------------------------------------------------------------------

_WS = re.compile(r"\s+")
_NUM = re.compile(r"\d[\d.,/-]*")


@lru_cache(maxsize=8192)
def norm_name(s: str) -> str:
    s = (s or "").lower()
    s = _NUM.sub(" ", s)
    s = re.sub(r"[^\wäöüß]+", " ", s)
    return _WS.sub(" ", s).strip()[:60]


def purpose_key(s: str, words: int = 3) -> str:
    return " ".join(norm_name(s).split()[:words])


def party_key(t: Tx) -> str:
    """The other side of a booking: its IBAN, else its name, else the start of its purpose (e.g. a savings plan the bank debits
    itself)."""
    return (t.counter_iban or "").replace(" ", "").upper() or norm_name(t.name) or ("purpose:" + purpose_key(t.purpose, 4))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")).strip("-")[:80] or "k"


def rule_matches(r: dict, t: Tx) -> bool:
    if r.get("iban") and r["iban"] != (t.counter_iban or "").replace(" ", "").upper():
        return False
    if r.get("name_is") and r["name_is"] != norm_name(t.name):
        return False
    if r.get("purpose_contains") and r["purpose_contains"] not in norm_name(t.purpose + " " + t.booking_text):
        return False
    return bool(r.get("iban") or r.get("name_is"))


def _specificity(r: dict) -> int:
    return (3 if r.get("iban") else 0) + (2 if r.get("purpose_contains") else 0) + (2 if r.get("name_is") else 0)


def _rule_index(d: dict) -> dict:
    """Learned patterns by IBAN and by name (kept in memory with the rules they were made of)."""
    idx = d.get("_idx")
    if idx is None or idx[0] is not d["rules"]:
        by_iban: Dict[str, List[dict]] = defaultdict(list)
        by_name: Dict[str, List[dict]] = defaultdict(list)
        for r in d["rules"]:
            if r.get("iban"):
                by_iban[r["iban"]].append(r)
            elif r.get("name_is"):
                by_name[r["name_is"]].append(r)
        idx = d["_idx"] = (d["rules"], by_iban, by_name)
    return idx


def suggest(d: dict, t: Tx) -> Optional[dict]:
    """The best matching learned pattern for a transaction."""
    _, by_iban, by_name = _rule_index(d)
    best = None
    for r in by_iban.get((t.counter_iban or "").replace(" ", "").upper(), []) + by_name.get(norm_name(t.name), []):
        if rule_matches(r, t) and (best is None or _specificity(r) > _specificity(best)):
            best = r
    return best


def learn(d: dict, ledger: Ledger, min_count: int = 2, min_share: float = 0.9, progress=None) -> Dict[str, int]:
    """Patterns from your categories (MoneyMoney and what waits to be written): counterparty IBAN, name with the start of the
    purpose, name -- where at least 90 % of its transactions have the same category."""
    samples: List[Tuple[Tx, str]] = []
    n_all = len(ledger.txs) or 1
    for i, t in enumerate(ledger.txs):
        if progress and i % 20000 == 0:
            progress(0.5 * i / n_all)
        path, q = effective(d, t)
        if path and not has_mark(t.purpose):
            samples.append((t, path))
    groups: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
    for i, (t, path) in enumerate(samples):
        if progress and i % 20000 == 0:
            progress(0.5 + 0.3 * i / (len(samples) or 1))
        iban = (t.counter_iban or "").replace(" ", "").upper()
        nm = norm_name(t.name)
        if iban and len(iban) >= 8:
            groups[("iban", iban)][path] += 1
        if nm:
            groups[("name", nm)][path] += 1
            pk = purpose_key(t.purpose)
            if pk:
                groups[("name+zweck", nm + "|" + pk)][path] += 1
    if progress:
        progress(0.8)
    learned: List[dict] = []
    seen_names: set = set()
    stats = Counter()
    for (kind, key), cnt in groups.items():           # a name alone is enough where it is unambiguous
        total = sum(cnt.values())
        path, n = cnt.most_common(1)[0]
        if kind == "name" and total >= min_count and n / total >= min_share:
            seen_names.add(key)
    for (kind, key), cnt in sorted(groups.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(cnt.values())
        path, n = cnt.most_common(1)[0]
        if total < min_count or n / total < min_share:
            continue
        rid = "g-" + _slug(kind + "-" + key)[:70]
        if kind == "iban":
            r = {"id": rid, "category": path, "iban": key, "source": "learned", "hits": total, "active": True}
        elif kind == "name":
            r = {"id": rid, "category": path, "name_is": key, "source": "learned", "hits": total, "active": True}
        else:
            nm, pk = key.split("|", 1)
            if nm in seen_names:
                continue
            r = {"id": rid, "category": path, "name_is": nm, "purpose_contains": pk, "source": "learned", "hits": total, "active": True}
        learned.append(r)
        stats[kind] += 1
    d["rules"] = learned
    d["learned_at"] = time.strftime("%Y-%m-%d %H:%M")
    return {"rules": len(learned), "pattern": len(samples), **{k: v for k, v in stats.items()}}


# ---------------------------------------------------------------------------
# Suggestions with a level: for every open transaction Kontor's best guess, how likely it is right, and why
# ---------------------------------------------------------------------------
#
# Each kind of hint says how likely its category is right as the share of earlier cases -- Laplace's rule of succession
# (k + 1) / (n + 2) for k of n earlier cases with this category (1 of 1: 67 %, 3 of 3: 80 %, 9 of 10: 83 %). The counterparty's
# own past counts fully; what other counterparties show (a word they share, alike by meaning) a little less, as it is about
# others. The category with the best hint wins; a second kind of hint for it adds to it (half of what is left), a hint of
# another kind for another category takes from it. Never applied by itself: you click.

HIGH, MEDIUM = 0.8, 0.6          # likely right from 80 %: "sicher"; from 60 %: "wahrscheinlich"; below: "unsicher"
LEVELS = ("high", "medium", "low")
REVERSE = 0.85                   # the counterparty's past only in the other direction (a refund of a purchase): a little weaker
WORDS = 0.9                      # a word other counterparties had: their past, not this one's
MEANING = 0.8                    # alike by meaning (the embeddings the assistant made): weaker still
MEANING_MIN = 0.5                # likeness (cosine) from which another counterparty counts as alike (as memory.SEM_MIN)
MEANING_DIMS = 128               # numbers of an embedding compared: its first ones carry most (Matryoshka) -- a quarter of the work
MEANING_K = 5                    # the most alike counterparties vote
MEANING_MAX = 120                # transactions compared by meaning per call beyond those compared before (the rest: the next call)
MEANING_PARTY = 20               # texts of a counterparty per category its embedding is made of (the latest)
COUNTER_DAYS = 5                 # a counter-booking at most this many days apart
STUMP_TEXTS = 2000               # transactions of a counterparty whose amounts are split (the latest)
WORDS_TEXTS = 50                 # texts of a counterparty per category whose words count (the latest)
GUESS = 0.5                      # the most common category, where nothing else is known: at most this (a guess, whatever its share)
CATNAME = 0.45                   # a word of the name of one of your categories (nothing better known): a guess
_LETTERS = re.compile(r"(?<![a-z])[a-z]{3,30}(?![a-z])")
_sumprod = getattr(math, "sumprod", None) or (lambda a, b: sum(map(operator.mul, a, b)))


def chance(k: int, n: int) -> float:
    """How likely the next case is like k of n earlier ones (Laplace's rule of succession)."""
    return (k + 1) / (n + 2)


def level_of(p: float) -> str:
    return "high" if p >= HIGH - 1e-9 else "medium" if p >= MEDIUM - 1e-9 else "low"


@lru_cache(maxsize=65536)
def text_words(s: str) -> frozenset:
    """The words of a text as the suggestions compare them: folded like MoneyMoney (ä as ae ...), letters only, 3 to 30."""
    return frozenset(sys.intern(w) for w in _LETTERS.findall(_fold(s))) if s else frozenset()


def _all_words(t: Tx) -> frozenset:
    return text_words(t.name) | text_words(t.purpose) | text_words(t.booking_text)


def _shown(t: Tx, w: str) -> str:
    """A word as the transaction writes it (the folded form only where it is not found)."""
    for x in re.split(r"[^\wäöüÄÖÜß]+", (t.name or "") + " " + (t.purpose or "") + " " + (t.booking_text or "")):
        if x and _fold(x) == w:
            return x
    return w


def _top(cats: Iterable[str]) -> Tuple[str, int, int]:
    """(the most common category, how often, of how many) -- among equals the first by name."""
    if isinstance(cats, list) and len(cats) == 1:
        return cats[0], 1, 1
    c = Counter(cats)
    n = sum(c.values())
    cat, k = min(c.items(), key=lambda kv: (-kv[1], kv[0]))
    return cat, k, n


def _cents(x: float) -> int:
    return int(round(x * 100))


class Meaning:
    """For suggestions by meaning: the embeddings of transactions' texts the assistant already made (never new ones) -- sig
    names their state (model, how many), vectors(txs) gives {id: numbers} for those that have one; cache: the counterparties'
    embeddings made before (kept by the caller across states of your assignments -- only what changed is made anew)."""

    def __init__(self, sig: Any, vectors: Callable[[List[Tx]], Dict[int, Sequence[float]]], cache: Optional[dict] = None):
        self.sig, self.vectors = sig, vectors
        self.cache = cache if cache is not None else {}


class Hints:
    """What the suggestions are made of -- your categories (MoneyMoney's and what waits to be written): by counterparty, the
    words other counterparties had, the most common one per area and direction, the words of the categories' names, and the
    bookings a counter-booking can be. Made once for a state of the transactions and your assignments (service keeps it).
    area_of: account -> area; counter_accounts: the accounts a counter-booking can be on (None: all); assignable: the
    categories that exist in MoneyMoney (None: not known -- all); transfer: your category for transfers, is_transfer: whether
    a category is one; everyday: whether a category is income or spending (the most common one is guessed only among those --
    never saving, a repayment or a transfer; None: all but transfers)."""

    def __init__(self, d: dict, ledger: Ledger, area_of: Optional[Dict[str, str]] = None, counter_accounts: Optional[set] = None,
                 assignable: Optional[set] = None, transfer: Optional[str] = None, is_transfer: Optional[Callable[[str], bool]] = None,
                 everyday: Optional[Callable[[str], bool]] = None):
        self.area_of = area_of or {}
        self.accounts = ledger.accounts
        self.is_transfer = is_transfer or (lambda p: False)
        self.transfer = transfer if transfer and (assignable is None or transfer in assignable) else None
        self.by_iban: Dict[str, list] = defaultdict(list)       # counterparty IBAN -> [(area, sign, cents, category, tx, currency)]
        self.by_name: Dict[str, list] = defaultdict(list)       # its name (normalised) -> the same
        self.words: Dict[tuple, Dict[str, set]] = {}            # (area or "*", sign, word) -> category -> counterparties that had it
        self.common: Dict[tuple, Counter] = defaultdict(Counter)    # (area or "*", sign) -> categories
        self.direction: Dict[str, List[int]] = defaultdict(lambda: [0, 0])     # category -> [out, in]
        self.texts: Dict[tuple, list] = defaultdict(list)       # (area, sign, counterparty, category) -> its transactions (meaning)
        self.names: Dict[str, str] = {}                         # counterparty -> its name as shown
        self.cents: Dict[int, list] = defaultdict(list)         # amount in cents -> [(tx, category)] a counter-booking can be
        self.own = ledger.own_ibans()
        self.paired = set().union(*((getattr(ledger, "_paired", None) or {}).values()))     # the cash flow paired them already
        self._party: dict = {}
        self._mean: Optional[tuple] = None
        self._meant: Dict[int, Any] = {}
        self._meant_sig: Any = None
        for t in ledger.txs:
            if not t.booked or t.id <= 0 or has_mark(t.purpose):
                continue
            path = effective(d, t)[0]
            if counter_accounts is None or t.account_uuid in counter_accounts:
                self.cents[_cents(t.amount)].append((t, path))
            if not path or (assignable is not None and path not in assignable):
                continue
            area, sign = str(self.area_of.get(t.account_uuid, "")), (-1 if t.amount < 0 else 1)
            s = (area, sign, abs(_cents(t.amount)), path, t, self.currency(t))
            iban = (t.counter_iban or "").replace(" ", "").upper()
            if len(iban) >= 8:
                self.by_iban[iban].append(s)
            nm = norm_name(t.name)
            if nm:
                self.by_name[nm].append(s)
            party = _party(t) or "purpose:" + purpose_key(t.purpose, 4)
            self.names[party] = (t.name or t.purpose or "")[:60]
            if not self.is_transfer(path) and (everyday is None or everyday(path)):      # (the most common: of income or spending only)
                self.common[(area, sign)][path] += 1
                self.common[("*", sign)][path] += 1
            self.direction[path][0 if sign < 0 else 1] += 1
            self.texts[(area, sign, party, path)].append(t)
        # the words each counterparty had per category (its latest texts), in its area and in all (one area: in all only)
        several = len({str(v) for v in self.area_of.values()}) > 1
        for (area, sign, party, path), txs in self.texts.items():
            if len(txs) > WORDS_TEXTS:
                txs = sorted(txs, key=lambda t: (t.booking_date, t.id))[-WORDS_TEXTS:]
            ws: set = set()
            for t in txs:
                ws |= _all_words(t)
            for w in ws:
                for key in (((area, sign, w), ("*", sign, w)) if several else (("*", sign, w),)):
                    m = self.words.get(key)
                    if m is None:
                        m = self.words[key] = {}
                    ps = m.get(path)
                    if ps is None:
                        ps = m[path] = set()
                    ps.add(party)
        for key, m in self.words.items():                   # per word: [(counterparties, category, them)] most first, and how many had it
            rows = sorted(((len(ps), cat, ps) for cat, ps in m.items()), key=lambda x: (-x[0], x[1])) if len(m) > 1 else [(len(ps), cat, ps) for cat, ps in m.items()]
            had = set().union(*m.values()) if len(m) > 1 else rows[0][2]
            self.words[key] = (rows, had)
        self._words_seen: Dict[tuple, Optional[tuple]] = {}
        self.catword: Dict[str, set] = defaultdict(set)         # word of a category's name -> categories
        self.catstem: Dict[str, set] = defaultdict(set)         # ... without an ending of up to two letters (Versicherungen: versicherung)
        for path in sorted(assignable if assignable is not None else self.direction):
            if self.is_transfer(path):
                continue                                         # a transfer: by the counter-booking, never by a word
            for w in text_words(path.replace(" / ", " ")):
                if len(w) >= 4:
                    self.catword[w].add(path)
                if len(w) >= 6:
                    self.catstem[w[:max(6, len(w) - 2)]].add(path)

    def currency(self, t: Tx) -> str:
        a = self.accounts.get(t.account_uuid)
        return ((a.currency if a else "") or "EUR").upper()

    # -- the counterparty's own past ---------------------------------------------------------------------------------------
    def _past(self, kind: str, key: str, area: str, sign: int, cur: str) -> Optional[dict]:
        """What the counterparty's past says (kept): in this area where it has any there, else in all; amounts compared only in
        the transaction's currency. Categories counted (Counter): all of it (prior), per amount, per word of the purpose, per
        side of the split by amount. Made whole before it is kept (requests run side by side)."""
        ck = (kind, key, area, sign, cur)
        got = self._party.get(ck, False)
        if got is not False:
            return got
        out = self._past_of((self.by_iban if kind == "iban" else self.by_name).get(key) or [], area, sign, cur)
        self._party[ck] = out
        return out

    @staticmethod
    def _past_of(hist: list, area: str, sign: int, cur: str) -> Optional[dict]:
        """What a past says (see _past) -- for any part of it (Kategorisieren → Auffällig: without the transaction asked about)."""
        here = [s for s in hist if s[0] == area]
        hist = here or hist
        same = [s for s in hist if s[1] == sign]
        out: Optional[dict] = None
        if same:
            prior = Counter(s[3] for s in same)
            out = {"n": len(same), "ids": {s[4].id for s in same}, "prior": prior, "mixed": len(prior) > 1, "amounts": {}, "words": {}, "stump": None}
            if out["mixed"]:
                mine = [s for s in same if s[5] == cur]
                amounts: Dict[int, Counter] = defaultdict(Counter)
                for s in mine:
                    amounts[s[2]][s[3]] += 1
                out["amounts"] = dict(amounts)
                out["stump"] = _stump(mine)
                words: Dict[str, Counter] = defaultdict(Counter)     # word of the purpose -> the categories of the transactions with it
                for s in same:
                    for w in text_words(s[4].purpose) | text_words(s[4].booking_text):
                        words[w][s[3]] += 1
                out["words"] = {w: c for w, c in words.items() if 2 <= sum(c.values()) < len(same)}
        elif hist:
            out = {"reverse": _top(s[3] for s in hist), "reverse_prior": Counter(s[3] for s in hist)}
        return out

    @staticmethod
    def _like(sub: Counter, p: dict) -> Tuple[str, int, int, float]:
        """Of the counterparty's transactions like this one (sub: their categories counted) -- with its whole past as the
        prior, worth one transaction: (category, k, n, how likely)."""
        n_all, n = sum(p["prior"].values()), sum(sub.values())
        cat = max(sub, key=lambda x: (sub[x] + p["prior"][x] / n_all, x))
        return cat, sub[cat], n, (sub[cat] + p["prior"][cat] / n_all) / (n + 1)

    def _keys(self, t: Tx) -> List[Tuple[str, str]]:
        iban = (t.counter_iban or "").replace(" ", "").upper()
        return ([("iban", iban)] if len(iban) >= 8 else []) + ([("name", norm_name(t.name))] if norm_name(t.name) else [])

    def _subsets(self, t: Tx, p: dict) -> List[Tuple[int, str, Counter, list]]:
        """The counterparty's transactions like this one, where its categories differ: (how telling, kind, their categories,
        what the reason names) -- exactly this amount, a word of this purpose, the same side of the split by amount."""
        c = abs(_cents(t.amount))
        out = []
        eq = p["amounts"].get(c)
        if eq and sum(eq.values()) < p["n"]:
            out.append((3, "party_amount", eq, [c / 100]))
        for w in sorted(text_words(t.purpose) | text_words(t.booking_text)):
            if w in p["words"]:
                out.append((2, "party_word", p["words"][w], [_shown(t, w)]))
        if p["stump"]:
            mid, below, above, low_max, high_min, _ = p["stump"]
            if c <= low_max or c >= high_min:                    # (between the two sides: neither)
                out.append((1, "party_below" if c < mid else "party_above", below if c < mid else above, [mid / 100]))
        return out

    def _pasts(self, t: Tx, area: str, sign: int, without: Optional[int] = None) -> List[Optional[dict]]:
        """The counterparty's past by its IBAN and by its name -- without: as if that transaction had no category (made anew)."""
        cur = self.currency(t)
        if without is None:
            return [self._past(kind, key, area, sign, cur) for kind, key in self._keys(t)]
        return [self._past_of([s for s in (self.by_iban if kind == "iban" else self.by_name).get(key) or [] if s[4].id != without], area, sign, cur)
                for kind, key in self._keys(t)]

    def _party_hint(self, t: Tx, area: str, sign: int, without: Optional[int] = None) -> List[tuple]:
        """The counterparty's past: where all of it has one category, its share; where its categories differ, those of its
        transactions that are like this one (_subsets; its whole past as the prior: one of them does not outweigh twenty
        others) -- the likeliest of these; one of them for another category (from 50 %) comes as a hint of its own (it takes
        from the first). Only where none is like this one, all of it."""
        best: Optional[List[tuple]] = None
        for p in self._pasts(t, area, sign, without):
            if p is None:
                continue
            if "reverse" in p:
                cat, k, n = p["reverse"]
                found = [(REVERSE * chance(k, n), 0, cat, {"k": "party_reverse", "a": [k, n]})]
            elif not p["mixed"]:
                cat, k = next(iter(p["prior"].items()))
                found = [(chance(k, k), 0, cat, {"k": "party", "a": [k, k]})]
            else:
                cands = []                                       # (how likely, among equals the more telling, category, why)
                for rank, kk, sub, extra in self._subsets(t, p):
                    cat, k, n, pr = self._like(sub, p)
                    cands.append((pr, rank, cat, {"k": kk, "a": [k, n] + extra}))
                if not cands:
                    cat, k, n = _top(p["prior"].elements())
                    cands.append((chance(k, n), 0, cat, {"k": "party", "a": [k, n]}))
                cands.sort(key=lambda x: (-x[0], -x[1], x[2]))
                found = [cands[0]]
                rival = next((x for x in cands if x[2] != cands[0][2]), None)
                if rival and rival[0] >= 0.5:
                    found.append(rival)
            if best is None or found[0][0] > best[0][0]:
                best = found
        if not best:
            return []
        return [("party", best[0][2], best[0][0], best[0][3])] + [("party_other", x[2], x[0], x[3]) for x in best[1:]]

    # -- what others show ---------------------------------------------------------------------------------------------------
    def _words_best(self, t: Tx, area: str, sign: int, own: frozenset) -> Optional[tuple]:
        """A word other counterparties had (counted by counterparty: the same shop a hundred times is one), in this area where
        two or more had it there, else in all: ("word", category, how likely, why, the word folded, its key) -- kept."""
        ws = _all_words(t)
        ck = (area, sign, ws, own)
        if ck in self._words_seen:
            return self._words_seen[ck]
        best: Optional[tuple] = None
        for w in sorted(ws):
            for a in (area, "*"):
                e = self.words.get((a, sign, w))
                if not e:
                    continue
                rows, had = e
                n = len(had) - sum(1 for o in own if o in had)
                if n < 2:
                    continue
                top: Optional[Tuple[int, str]] = None
                for k, cat, ps in rows:                   # most first: leaving out this counterparty takes at most len(own)
                    if top is not None and k < top[0]:
                        break
                    k -= sum(1 for o in own if o in ps)
                    if top is None or (k, top[1]) > (top[0], cat):
                        top = (k, cat)
                p = WORDS * chance(top[0], n)
                if best is None or (p, n, len(w)) > (best[2], best[3]["a"][1], len(best[4])):      # among equals: more had it, the longer word
                    best = ("word", top[1], p, {"k": "word", "a": [top[0], n, w]}, w, (a, sign, w))
                break
        self._words_seen[ck] = best
        return best

    def _words_hint(self, t: Tx, area: str, sign: int, own: frozenset) -> Optional[tuple]:
        best = self._words_best(t, area, sign, own)
        return best and best[:3] + ({"k": "word", "a": best[3]["a"][:2] + [_shown(t, best[4])]},)

    def _catname_hint(self, t: Tx, sign: int) -> Optional[tuple]:
        """A word of the transaction in the name of one of your categories (Versicherungsbeitrag -- Versicherungen): a guess --
        not where a category was only ever used in the other direction."""
        hits: Dict[str, set] = defaultdict(set)
        for w in _all_words(t):
            found = set(self.catword.get(w, ()))
            for i in range(5, len(w)):                           # the word goes on after a word of the name (Stromabschlag: Strom)
                found |= self.catword.get(w[:i], set())
            for i in range(6, len(w) + 1):                       # ... or after its stem (Versicherungsbeitrag, Versicherung: Versicherungen)
                found |= self.catstem.get(w[:i], set())
            for cat in found:
                o, i_ = self.direction.get(cat, (0, 0))
                if (o if sign < 0 else i_) or not (i_ if sign < 0 else o):
                    hits[cat].add(w)
        if not hits:
            return None
        ranked = sorted(hits.items(), key=lambda kv: (-len(kv[1]), -sum(self.direction.get(kv[0], (0, 0))), kv[0]))
        cat, ws = ranked[0]
        sure = len(ranked) == 1 or len(ranked[1][1]) < len(ws)
        return ("catname", cat, CATNAME if sure else CATNAME - 0.05, {"k": "catname", "a": [_shown(t, sorted(ws)[0])]})

    def _common_hint(self, area: str, sign: int) -> Optional[tuple]:
        """Nothing else known: the most common category of payments in this direction in this area (else in all) -- its share
        is how likely it is right."""
        c = self.common.get((area, sign)) or self.common.get(("*", sign))
        if not c:
            return None
        cat, k = min(c.items(), key=lambda kv: (-kv[1], kv[0]))
        n = sum(c.values())
        return ("common", cat, chance(k, n), {"k": "common_out" if sign < 0 else "common_in", "a": [k, n]})

    # -- counter-booking ----------------------------------------------------------------------------------------------------
    def _counter_hint(self, t: Tx, area: str) -> Optional[tuple]:
        """Your transfer category where the money went to (came from) an account of yours: its IBAN is the other side, or the
        opposite amount is booked on another of your accounts within COUNTER_DAYS (without a category, or with a transfer one)."""
        if not self.transfer or not _cents(t.amount):
            return None
        acc = self.own.get(t.counter_iban) if t.counter_iban else None
        if t.counter_iban and not acc:
            return None                                          # it went to (came from) someone else's account
        cur, nm = self.currency(t), norm_name(t.name)
        cands = []
        for o, path in self.cents.get(-_cents(t.amount), ()):
            days = abs((o.booking_date - t.booking_date).days)
            if o.account_uuid == t.account_uuid or days > COUNTER_DAYS or (path and not self.is_transfer(path)) or o.id in self.paired:
                continue
            if (o.counter_iban and not self.own.get(o.counter_iban)) or self.currency(o) != cur:
                continue                                         # from someone else, or another currency
            if nm and norm_name(o.name) and norm_name(o.name) != nm:
                continue                                         # both name a counterparty, and not the same: two payments
            cands.append((days, o.id, o, path))
        if not cands:
            if acc and acc != t.account_uuid and acc in self.accounts:
                return ("counter", self.transfer, 0.6, {"k": "own_account", "a": [self.accounts[acc].name]})
            return None
        days, _, o, path = min(cands, key=lambda x: (x[0], x[1]))
        p = 0.85 if path else 0.7 if len(cands) == 1 and days <= 2 else 0.6
        name = self.accounts[o.account_uuid].name if o.account_uuid in self.accounts else ""
        return ("counter", self.transfer, p, {"k": "counter_cat" if path else "counter", "a": [name, o.booking_date.isoformat()]})

    # -- by meaning ---------------------------------------------------------------------------------------------------------
    def _means(self, meaning: Meaning) -> Dict[tuple, list]:
        """(area, sign) and ("*", sign) -> [(counterparty, category, its embedding: the mean of its latest texts, unit length)]
        -- one made before for the same texts comes from meaning.cache (only complete ones are kept there)."""
        got = self._mean
        if got is not None and got[0] == meaning.sig:
            return got[1]
        keep = {k: sorted(v, key=lambda t: (t.booking_date, t.id))[-MEANING_PARTY:] for k, v in self.texts.items()}
        model = meaning.sig[0] if isinstance(meaning.sig, tuple) else meaning.sig
        keys = {k: (model, k, tuple(t.id for t in txs)) for k, txs in keep.items()}
        new = [t for k, txs in keep.items() if keys[k] not in meaning.cache for t in txs]
        vecs = meaning.vectors(new) if new else {}
        out: Dict[tuple, list] = defaultdict(list)
        cache: dict = {}
        for k, txs in keep.items():
            (area, sign, party, cat), ck = k, keys[k]
            if ck in meaning.cache:
                e = meaning.cache[ck]
            else:
                rows = [vecs[t.id] for t in txs if t.id in vecs]
                e = None
                if rows:
                    m = [sum(x) for x in zip(*(r[:MEANING_DIMS] for r in rows))]
                    norm = math.sqrt(_sumprod(m, m))
                    e = (party, cat, [x / norm for x in m]) if norm > 0 else None
                if len(rows) < len(txs):                         # (not all made yet: made anew next time)
                    e = e and e + (False,)
            if e is not None:
                if len(e) == 3:
                    cache[ck] = e
                out[(area, sign)].append(e[:3])
                out[("*", sign)].append(e[:3])
        meaning.cache.clear()
        meaning.cache.update(cache)
        self._meant = {}
        self._mean = (meaning.sig, out)
        return out

    def _meaning_hint(self, t: Tx, vec: Sequence[float], area: str, sign: int, own: set, means: dict) -> Optional[tuple]:
        q = list(vec[:MEANING_DIMS])
        norm = math.sqrt(_sumprod(q, q))
        if not norm:
            return None
        pool = means.get((area, sign)) or []
        if len({e[0] for e in pool} - own) < MEANING_K:
            pool = means.get(("*", sign)) or []
        best: Dict[str, tuple] = {}
        for party, cat, v in pool:
            if party in own:
                continue
            s = _sumprod(q, v) / norm
            if s >= MEANING_MIN and (party not in best or s > best[party][0]):
                best[party] = (s, cat, party)
        near = sorted(best.values(), key=lambda x: (-x[0], x[2]))[:MEANING_K]
        if not near:
            return None
        cat, k, n = _top(x[1] for x in near)
        like = next(x for x in near if x[1] == cat)
        return ("meaning", cat, MEANING * chance(k, n), {"k": "meaning", "a": [k, n, self.names.get(like[2], "")]})

    # -- all together -------------------------------------------------------------------------------------------------------
    def hints(self, t: Tx, without: Optional[int] = None) -> List[tuple]:
        """(kind, category, how likely right, why) of each kind of hint that has one -- without meaning (see suggest); without:
        as if that transaction (this one) had no category."""
        area, sign = str(self.area_of.get(t.account_uuid, "")), (-1 if t.amount < 0 else 1)
        own = _own(t)
        out = self._party_hint(t, area, sign, without)
        out += [h for h in (self._counter_hint(t, area), self._words_hint(t, area, sign, own), self._catname_hint(t, sign),
                            self._common_hint(area, sign)) if h]
        return out


def _own(t: Tx) -> frozenset:
    """The keys this transaction's counterparty can have among the others (its IBAN, its name, the start of its purpose)."""
    iban = (t.counter_iban or "").replace(" ", "").upper()
    nm = norm_name(t.name)
    return frozenset(k for k in ((iban if len(iban) >= 8 else ""), nm, ("" if nm else "purpose:" + purpose_key(t.purpose, 4))) if k)


def _stump(same: list) -> Optional[tuple]:
    """Where the counterparty's categories part by the size of the amount (service charges below, rent above): the split
    between two amounts that leaves the most on the side of their side's category -- (split, the categories below counted,
    those above, the largest amount below, the smallest above, the transactions it was made of); None where no split leaves
    at least two on each side with different categories. Its latest STUMP_TEXTS transactions."""
    xs = sorted(sorted(same, key=lambda s: (s[4].booking_date, s[4].id))[-STUMP_TEXTS:], key=lambda s: s[2])
    best = None
    left: Counter = Counter()
    right = Counter(s[3] for s in xs)
    for i in range(1, len(xs)):
        left[xs[i - 1][3]] += 1
        right[xs[i - 1][3]] -= 1
        if xs[i - 1][2] == xs[i][2] or i < 2 or len(xs) - i < 2:
            continue
        cl, kl = min(((c, k) for c, k in left.items() if k), key=lambda ck: (-ck[1], ck[0]))
        cr, kr = min(((c, k) for c, k in right.items() if k), key=lambda ck: (-ck[1], ck[0]))
        if cl != cr and (best is None or kl + kr > best[0]):
            best = (kl + kr, i)
    if not best:
        return None
    i = best[1]
    return ((xs[i - 1][2] + xs[i][2]) / 2, Counter(s[3] for s in xs[:i]), Counter(s[3] for s in xs[i:]), xs[i - 1][2], xs[i][2],
            frozenset(s[4].id for s in xs))


def combine(hs: List[tuple]) -> Optional[dict]:
    """The suggestion from the hints: the category whose best hint is likeliest; a second kind of hint for it adds half of
    what is left times its own; the best hint of another kind for another category (from 50 %) takes half of what it has above
    40 %. The most common category counts only where nothing else is known -- a guess (at most GUESS), no evidence about this
    transaction. {category, chance, level, why}."""
    if not hs:
        return None
    if any(h[0] != "common" for h in hs):                # the most common category only where nothing else is known: a guess, never evidence
        hs = [h for h in hs if h[0] != "common"]
    else:
        hs = [h[:2] + (min(h[2], GUESS),) + h[3:] for h in hs]
    by: Dict[str, List[tuple]] = defaultdict(list)
    for h in hs:
        by[h[1]].append(h)

    def score(lst: List[tuple]) -> float:
        ps = sorted((h[2] for h in lst), reverse=True)
        return ps[0] + (0.5 * (1 - ps[0]) * ps[1] if len(ps) > 1 else 0.0)
    ranked = sorted(((score(lst), cat) for cat, lst in by.items()), key=lambda x: (-x[0], x[1]))
    p, cat = ranked[0]
    why = [h[3] for h in sorted(by[cat], key=lambda h: -h[2])]
    kinds = {h[0] for h in by[cat]}
    rival = max(((h[2], h[1]) for h in hs if h[1] != cat and h[0] not in kinds), default=None, key=lambda x: x[0])
    if rival and rival[0] >= 0.5:
        p -= 0.5 * (rival[0] - 0.4)
        why.append({"k": "also", "a": [rival[1]]})
    p = max(0.0, min(1.0, p))
    return {"category": cat, "chance": round(p, 3), "level": level_of(p), "why": why[:4]}


def suggest_one(h: Hints, t: Tx, vec: Optional[Sequence[float]] = None, means: Optional[dict] = None) -> Optional[dict]:
    """Kontor's suggestion for one transaction (with meaning, when its embedding and the counterparties' are given)."""
    hs = h.hints(t)
    if vec is not None and means:
        area, sign = str(h.area_of.get(t.account_uuid, "")), (-1 if t.amount < 0 else 1)
        m = h._meaning_hint(t, vec, area, sign, _own(t), means)
        if m:
            hs.append(m)
    return combine(hs)


# ---------------------------------------------------------------------------
# What is still without a category
# ---------------------------------------------------------------------------

def needs_category(t: Tx, banks: Optional[set]) -> bool:
    """A transaction a category matters for: booked, of a bank account (loans, assets and the like count by their account,
    not their category), not one of Kontor's own bookings (mirror, interest, value)."""
    return t.booked and t.id > 0 and (banks is None or t.account_uuid in banks) and not has_mark(t.purpose)


def transfers(ledger: Ledger, area_of: Optional[Dict[str, str]] = None) -> set:
    """Bank bookings that are a transfer whatever their category, so none is needed: the other side is another account of the
    same area (counter IBAN), or the cash flow found the counter-booking (e.g. entered by hand in a manual account; set when
    the report is built, report.build_dataset). A payment between two of your areas is not among them: a category says
    whether it is a salary or rent, or a contribution or withdrawal. area_of: account -> area (None: areas unknown, then only
    what the cash flow paired)."""
    ids: set = set()
    if area_of:
        own = ledger.own_ibans()
        for t in ledger.txs:
            p = own.get(t.counter_iban) if t.counter_iban else None
            if p is not None and p != t.account_uuid and area_of.get(p) is not None and area_of.get(p) == area_of.get(t.account_uuid):
                ids.add(t.id)
    for part in (getattr(ledger, "_paired", None) or {}).values():
        ids |= part
    return ids


def open_items(d: dict, ledger: Ledger, bereich_of: Dict[str, str], jahr: Optional[int] = None, bereich: Optional[str] = None,
               min_betrag: float = 0.0, limit: int = 400, banks: Optional[set] = None, hidden: Optional[set] = None,
               before: Optional[date] = None, hints: Optional[Hints] = None, meaning: Optional[Meaning] = None,
               level: Optional[str] = None) -> Dict[str, Any]:
    """Transactions without a category (in MoneyMoney, nothing waiting), grouped by counterparty, each with Kontor's suggestion
    and how sure it is (Hints; with meaning: also by the embeddings the assistant made). banks: the accounts a category matters
    for (bank accounts); None: all. Transfers between your accounts are left out, and so are the areas you do not categorise
    (hidden: their ids) and what was booked before the day you chose (before) -- the cash flow estimates their positions.
    assigned / assigned_sum / open_sum: the progress under the same filters -- how many have a category (MoneyMoney's or
    waiting) and the absolute sums in euros of those with and without one. levels: groups per level of their suggestion (all
    of them); level: only the groups of that level are listed (up to limit)."""
    groups: Dict[str, dict] = {}
    total = 0
    # the progress: of the transactions these filters show, how many have a category (MoneyMoney's or waiting -- the cash flow
    # counts them where it says) and how many the cash flow estimates; amounts in cents, accounts in euros only (never converted)
    done, done_c, open_c = 0, 0, 0
    skip = transfers(ledger, bereich_of)
    own = ledger.own_ibans()
    if hints is None:
        hints = Hints(d, ledger, bereich_of)
    for t in ledger.txs:
        if not needs_category(t, banks) or t.id in skip:
            continue
        if jahr and t.booking_date.year != jahr:
            continue
        if before and t.booking_date < before:
            continue
        if bereich and bereich_of.get(t.account_uuid) != bereich:
            continue
        if hidden and str(bereich_of.get(t.account_uuid)) in hidden:
            continue
        if min_betrag and abs(t.amount) < min_betrag:
            continue
        cur = ((ledger.accounts[t.account_uuid].currency if t.account_uuid in ledger.accounts else "") or "EUR").upper()
        cents = int(round(abs(t.amount) * 100)) if cur == "EUR" else 0
        path, q = effective(d, t)
        if path:
            done += 1
            done_c += cents
            continue
        total += 1
        open_c += cents
        key = party_key(t) + ("" if cur == "EUR" else " " + cur)       # another currency: a group of its own (its sum in it, never mixed)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": key, "name": t.name[:80] or t.purpose[:80], "iban": (t.counter_iban or "")[:34], "count": 0, "sum": 0.0, "ids": [],
                               "transactions": [], "proposals": {}, "accounts": [], "date_from": t.booking_date.isoformat(), "date_to": t.booking_date.isoformat(),
                               "own_account": bool(t.counter_iban and own.get(t.counter_iban)), "_txs": [], "_sug": {}}      # own_account: the other side is an account of yours (another area)
            if cur != "EUR":
                g["currency"] = cur
        g["_sug"][t.id] = combine(hints.hints(t))
        acc = ledger.accounts[t.account_uuid].name if t.account_uuid in ledger.accounts else ""
        g["count"] += 1
        g["sum"] = round(g["sum"] + t.amount, 2)
        g["ids"].append(t.id)
        g["_txs"].append(t)
        if acc not in g["accounts"]:
            g["accounts"].append(acc)
        g["date_from"] = min(g["date_from"], t.booking_date.isoformat()); g["date_to"] = max(g["date_to"], t.booking_date.isoformat())
    out = sorted(groups.values(), key=lambda g: (-abs(g["sum"]), -g["count"]))
    if meaning is not None:
        _by_meaning(hints, meaning, out)
    levels: Counter = Counter()
    for g in out:
        sug = g.pop("_sug")
        txs = sorted(g.pop("_txs"), key=lambda u: (u.booking_date, u.id), reverse=True)
        for t in txs[:300]:                              # the transactions of the group: choose some of them (e.g. a shop that sells many things)
            s = sug.get(t.id) or {}
            g["transactions"].append({"id": t.id, "date": t.booking_date.isoformat(), "amount": t.amount, "name": t.name[:80], "purpose": t.purpose[:400],
                                      "kind": t.booking_text[:60], "account": ledger.accounts[t.account_uuid].name if t.account_uuid in ledger.accounts else "",
                                      "proposal": s.get("category"), "level": s.get("level"), "chance": s.get("chance"), "why": s.get("why") or []})
        made = [s for s in sug.values() if s]
        kinds = {s["category"] for s in made}
        weakest = min(made, key=lambda s: (s["chance"], s["category"])) if made else None
        # the group's suggestion only where every transaction has the same one (e.g. rent and service charges differ); its level
        # and reasons those of its least sure transaction
        g["proposal"] = next(iter(kinds)) if len(kinds) == 1 and len(made) == g["count"] else None
        g["level"] = weakest["level"] if weakest and len(made) == g["count"] else "low"
        g["chance"] = weakest["chance"] if weakest else 0.0
        g["why"] = weakest["why"] if weakest and g["proposal"] else []
        g["proposals"] = {str(i): s["category"] for i, s in sug.items() if s}
        g["levels"] = {str(i): s["level"] for i, s in sug.items() if s}
        levels[g["level"]] += 1
    out.sort(key=lambda g: (-abs(g["sum"]), -g["count"]))
    shown = [g for g in out if g["level"] == level] if level in LEVELS else out
    return {"open": total, "groups": shown[:limit], "groups_shown": len(shown), "groups_total": len(out), "levels": {lv: levels.get(lv, 0) for lv in LEVELS},
            "assigned": done, "assigned_sum": done_c / 100, "open_sum": open_c / 100}


def _by_meaning(hints: Hints, meaning: Meaning, groups: List[dict]) -> None:
    """Where nothing is sure yet: the suggestion also by meaning -- the most alike other counterparties by the embeddings of
    their texts (the assistant's; none are made here). In the order shown, MEANING_MAX new transactions per call; what was
    compared stays with the hints (a state of the embeddings: meaning.sig)."""
    try:
        means = hints._means(meaning)
    except Exception as e:                               # (locked, a file not readable: the other hints stay)
        log.warning("Categories: no suggestions by meaning (%s)", type(e).__name__)
        return
    if not means:
        return
    todo = [t for g in groups for t in g["_txs"] if t.id not in hints._meant and (g["_sug"].get(t.id) or {}).get("level") != "high"][:MEANING_MAX]
    if todo:
        try:
            vecs = meaning.vectors(todo) or {}
        except Exception as e:
            log.warning("Categories: no suggestions by meaning (%s)", type(e).__name__)
            return
        for t in todo:
            v = vecs.get(t.id)
            area, sign = str(hints.area_of.get(t.account_uuid, "")), (-1 if t.amount < 0 else 1)
            hints._meant[t.id] = hints._meaning_hint(t, v, area, sign, _own(t), means) if v is not None else None
    for g in groups:
        for t in g["_txs"]:
            m = hints._meant.get(t.id)
            if m and (g["_sug"].get(t.id) or {}).get("level") != "high":
                g["_sug"][t.id] = combine(hints.hints(t) + [m])


# ---------------------------------------------------------------------------
# Doubts: categories that make no sense to Kontor -- coarse outliers for you to look at (nothing is changed by itself)
# ---------------------------------------------------------------------------
#
# Leaving the transaction itself out, Kontor looks at what is comparable -- the counterparty's past (all of it, exactly this
# amount, a word of this purpose, the same side of the split by amount) and a word other counterparties had -- and asks how
# likely the category it has is there: (k + 0.5) / (n + 1) for k of n with it. The base is all of the counterparty's past
# (without any: the word of others); a smaller set counts only where it has the category (one other payment of the same amount
# says nothing against it). Doubted only where the best of these gives it less than DOUBT_LOW (under 10 %: none of 5 or more,
# one of 15, two of 25) and Kontor would suggest another one at least DOUBT_TOP likely -- where only a word of others is the base
# (a counterparty without a past), at least HIGH. A category Kontor gives some chance (30 % for B while it suggests A at 60 %) is never doubted, and neither is
# one the category's name or a counter-booking speaks for.

DOUBT_TOP = 0.6                  # Kontor's own suggestion, without this transaction, at least this likely ...
DOUBT_OK_MAX = 5000              # categories you said are fine ("Passt so"): the latest kept
DOUBT_LOW = 0.1                  # ... and the category it has less than this by everything comparable


def _support(k: int, n: int) -> float:
    """How likely a category is that k of n comparable transactions had (half a case for it: none of 1 is not nothing)."""
    return (k + 0.5) / (n + 1)


def doubt_of(h: Hints, t: Tx, cat: str) -> Optional[dict]:
    """Why t's category cat makes no sense to Kontor: {category: what Kontor would suggest for t without its category (as under
    Offen, without meaning), chance, level, why, support: how likely cat is by the best comparable cases} -- None where it makes
    sense or too little is known to say. Looked at closely only where the counterparty's past has cat rarely or hardly any past
    (everything else is never doubted: all of its past is the base)."""
    area, sign = str(h.area_of.get(t.account_uuid, "")), (-1 if t.amount < 0 else 1)
    rare = not h._keys(t)
    for p in h._pasts(t, area, sign):
        if p is None or "reverse" in p or p["n"] <= 1 or (p["prior"][cat] - 0.5) / p["n"] < DOUBT_LOW:
            rare = True
    if not rare:
        return None
    hs = h.hints(t, without=t.id)
    s = combine(hs)
    if not s or s["category"] == cat or s["chance"] < DOUBT_TOP:
        return None
    if any(x[1] == cat and x[0] in ("catname", "counter") for x in hs):
        return None                                      # the category's name, or a counter-booking: it makes sense
    support, base = _doubt_support(h, t, cat, area, sign)
    if support >= DOUBT_LOW or (not base and s["chance"] < HIGH):
        return None                                      # (only a word others had: doubted only where Kontor is sure)
    return dict(s, support=round(support, 3))


def _doubt_support(h: Hints, t: Tx, cat: str, area: str, sign: int) -> Tuple[float, bool]:
    """How likely cat is for t by what is comparable without t: the base is all of the counterparty's past (only in the other
    direction: that) -- a smaller set of it (exactly this amount, a word of this purpose, a side of the split) counts only where
    it has cat; without a past of its own, the word other counterparties had that Kontor's suggestion rests on, and any other
    word others had where it has cat. (support, whether the counterparty's own past is the base)."""
    support, base = 0.0, False
    for p in h._pasts(t, area, sign, without=t.id):
        if p is None:
            continue
        base = True
        if "reverse" in p:
            rp = p["reverse_prior"]
            support = max(support, _support(rp[cat], sum(rp.values())))
            continue
        support = max(support, _support(p["prior"][cat], p["n"]))
        if p["mixed"]:
            for _, _, sub, _ in h._subsets(t, p):
                if sub[cat]:
                    support = max(support, _support(sub[cat], sum(sub.values())))
    if base:
        return support, True                             # (its own past outweighs words others had: they do not speak for it)
    own = _own(t)
    best = h._words_best(t, area, sign, own)
    for w in _all_words(t):
        for a in (area, "*"):
            e = h.words.get((a, sign, w))
            if not e:
                continue
            rows, had = e
            n = len(had) - sum(1 for o in own if o in had)
            k = sum(len(ps) - sum(1 for o in own if o in ps) for _, c_, ps in rows if c_ == cat)
            if n >= 1 and (k or (best is not None and best[5] == (a, sign, w))):
                support = max(support, _support(k, n))
            break
    return support, False


def doubts(d: dict, ledger: Ledger, bereich_of: Dict[str, str], hints: Optional[Hints] = None, jahr: Optional[int] = None,
           bereich: Optional[str] = None, banks: Optional[set] = None, hidden: Optional[set] = None, before: Optional[date] = None,
           limit: int = 300) -> Dict[str, Any]:
    """Transactions whose category makes no sense to Kontor (doubt_of), grouped by counterparty, category and Kontor's
    suggestion, the surest doubts first -- under the same filters as what is open (bank accounts, areas you categorise, ignore before, year). One you
    said is fine (d["doubt_ok"]: id -> its category then) stays out while it keeps that category. Changes nothing."""
    if hints is None:
        hints = Hints(d, ledger, bereich_of)
    ok = d.get("doubt_ok") or {}
    skip = transfers(ledger, bereich_of)
    groups: Dict[Tuple[str, str], dict] = {}
    for t in ledger.txs:
        if not needs_category(t, banks):
            continue
        if (jahr and t.booking_date.year != jahr) or (before and t.booking_date < before):
            continue
        if (bereich and bereich_of.get(t.account_uuid) != bereich) or (hidden and str(bereich_of.get(t.account_uuid)) in hidden):
            continue
        cat, q = effective(d, t)
        if not cat or ok.get(str(t.id)) == cat or (t.id in skip and hints.is_transfer(cat)):
            continue                                     # (a transfer the cash flow paired: its category is right)
        why = doubt_of(hints, t, cat)
        if why is None:
            continue
        cur = hints.currency(t)
        key = (party_key(t) + ("" if cur == "EUR" else " " + cur), cat, why["category"])      # one suggestion per group: changed alike
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": "|".join(key), "name": t.name[:80] or t.purpose[:80], "iban": (t.counter_iban or "")[:34], "category": cat,
                               "count": 0, "sum": 0.0, "ids": [], "transactions": [], "accounts": [], "_best": None}
            if cur != "EUR":
                g["currency"] = cur
        acc = ledger.accounts[t.account_uuid].name if t.account_uuid in ledger.accounts else ""
        g["count"] += 1
        g["sum"] = round(g["sum"] + t.amount, 2)
        g["ids"].append(t.id)
        if acc not in g["accounts"]:
            g["accounts"].append(acc)
        if len(g["transactions"]) < 300:
            g["transactions"].append({"id": t.id, "date": t.booking_date.isoformat(), "amount": t.amount, "name": t.name[:80], "purpose": t.purpose[:400],
                                      "kind": t.booking_text[:60], "account": acc, "source": q, "proposal": why["category"], "level": why["level"],
                                      "chance": why["chance"], "why": why["why"], "support": why["support"]})
        if g["_best"] is None or (why["chance"], -why["support"]) > (g["_best"]["chance"], -g["_best"]["support"]):
            g["_best"] = why
    out = []
    for g in groups.values():
        b = g.pop("_best")
        g.update(proposal=b["category"], level=b["level"], chance=b["chance"], why=b["why"], support=b["support"])
        g["transactions"].sort(key=lambda u: (u["date"], u["id"]), reverse=True)
        out.append(g)
    out.sort(key=lambda g: (-g["chance"], g["support"], -abs(g["sum"]), g["key"]))
    return {"groups": out[:limit], "groups_total": len(out), "count": sum(g["count"] for g in out)}


def stats(d: dict, ledger: Ledger, banks: Optional[set] = None, area_of: Optional[Dict[str, str]] = None,
          hidden: Optional[set] = None, before: Optional[date] = None) -> Dict[str, Any]:
    """How many transactions have which kind of category (MoneyMoney, waiting, none) -- the areas you do not categorise
    (hidden) and what was booked before the day you chose (before) left out."""
    c: Counter = Counter()
    years: Dict[int, Counter] = defaultdict(Counter)
    skip = transfers(ledger, area_of)
    for t in ledger.txs:
        if not needs_category(t, banks):
            continue
        if hidden and area_of is not None and str(area_of.get(t.account_uuid)) in hidden:
            continue
        if before and t.booking_date < before:
            continue
        path, q = effective(d, t)
        if not path and t.id in skip:                  # a transfer between your accounts: no category needed
            continue
        k = q or "without"
        c[k] += 1
        years[t.booking_date.year][k] += 1
    return {"total": dict(c), "years": {str(y): dict(v) for y, v in sorted(years.items())}, "learned_at": d.get("learned_at")}


# ---------------------------------------------------------------------------
# Rules for MoneyMoney: proposed in its search syntax (Kontor cannot create rules there)
# ---------------------------------------------------------------------------

def _fold(s: str) -> str:
    """Text as MoneyMoney compares it: lower case, umlauts as ae/oe/ue, ß as ss, accents dropped, spaces collapsed."""
    s = (s or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return _WS.sub(" ", s).strip()


def _words(s: str) -> set:
    return {w for w in re.split(r"[^a-z0-9]+", _fold(s)) if len(w) >= 3 and not w.isdigit()}


def _name_phrase(names: List[str]) -> Tuple[str, bool]:
    """The words all names start with (without parts with digits); True if some name goes on after them."""
    toks = [[w for w in re.split(r"\s+", (n or "").replace('"', "").strip()) if w] for n in names]
    if not toks or not all(toks):
        return "", False
    common: List[str] = []
    for i, w in enumerate(toks[0]):
        if any(i >= len(t) or _fold(t[i]) != _fold(w) for t in toks) or any(ch.isdigit() for ch in w):
            break
        common.append(w)
    return " ".join(common), any(len(t) > len(common) for t in toks)


_TXT: Dict[int, Tuple[str, set]] = {}


def _txt(t: Tx) -> Tuple[str, set]:
    """(name, words of the purpose) of a transaction as MoneyMoney compares them (kept while proposing)."""
    v = _TXT.get(t.id)
    if v is None:
        v = _TXT[t.id] = (_fold(t.name), _words(t.purpose))          # purpose: only the purpose, as MoneyMoney's purpose:
    return v


def _tokens(s: str) -> List[str]:
    return [w for w in re.split(r"[^a-z0-9]+", s) if w]


def _phrase_in(phrase: List[str], words: List[str], prefix: bool) -> bool:
    """MoneyMoney's phrase search: the words in this order as whole words; with * the last one may go on."""
    n = len(phrase)
    for i in range(len(words) - n + 1):
        if words[i:i + n - 1] == phrase[:-1] and (words[i + n - 1].startswith(phrase[-1]) if prefix else words[i + n - 1] == phrase[-1]):
            return True
    return False


def _matches(p: dict, t: Tx) -> bool:
    if p.get("iban") and (t.counter_iban or "").replace(" ", "").upper() != p["iban"]:
        return False
    name, words = _txt(t)
    if p.get("name"):
        if "_name" not in p:
            p["_name"] = _tokens(_fold(p["name"]))   # folded once per rule
        if not p["_name"] or not _phrase_in(p["_name"], _tokens(name), bool(p.get("more"))):
            return False
    if p.get("purpose") and not set(p["purpose"]) <= words:
        return False
    if p.get("sign") and (t.amount < 0) != (p["sign"] < 0):
        return False
    return True


def expression(p: dict) -> str:
    """The rule in MoneyMoney's syntax (Kategorie -> Einstellungen -> Regeln)."""
    parts = []
    if p.get("iban"):
        parts.append('remote_account:"%s"' % p["iban"])
    if p.get("name"):
        parts.append('name:"%s%s"' % (p["name"], "*" if p.get("more") else ""))
    for w in p.get("purpose") or []:
        parts.append('purpose:"%s"' % w)
    if p.get("sign"):
        parts.append("amount<0" if p["sign"] < 0 else "amount>0")
    return " AND ".join(parts)


def rule_proposals(d: dict, ledger: Ledger, written: Dict[str, Any], assignable: Optional[set] = None, limit: int = 60) -> List[dict]:
    """Rules worth adding in MoneyMoney: for counterparties whose transactions you categorized in Kontor at least twice
    (written into MoneyMoney by Kontor, or still waiting) -- MoneyMoney's rules evidently did not catch them. The rule is the
    counterparty (IBAN, else the start of the name); where the same counterparty also has other categories, words of the
    purpose (or the direction of the payment) that only this category has. Proposed only if it catches nothing of another
    category. assignable: categories that exist in MoneyMoney (others are left out)."""
    _TXT.clear()
    by_id = {t.id: t for t in ledger.txs if t.id > 0 and t.booked and not has_mark(t.purpose)}
    cats = {i: effective(d, t)[0] for i, t in by_id.items()}
    cat_of = lambda t: cats.get(t.id, "")
    done = set(d.get("rule_done") or [])
    chosen: Dict[Tuple[str, str], List[Tx]] = defaultdict(list)            # (counterparty, category) -> your transactions
    for tid, w in (written or {}).items():
        t = by_id.get(int(tid)) if str(tid).lstrip("-").isdigit() else None
        if t is not None and mm_of(t) and mm_of(t) == norm_cat(w.get("new") or ""):
            chosen[(_party(t), mm_of(t))].append(t)
    for tid, z in d["assignment"].items():
        t = by_id.get(int(tid)) if str(tid).lstrip("-").isdigit() else None
        if t is not None and waiting(z) and not mm_of(t):
            chosen[(_party(t), z["k"])].append(t)
    by_party: Dict[str, List[Tx]] = defaultdict(list)
    by_iban: Dict[str, List[Tx]] = defaultdict(list)
    by_word: Dict[str, List[Tx]] = defaultdict(list)            # word of the name -> transactions (to find what a rule hits)
    for t in by_id.values():
        by_party[_party(t)].append(t)
        iban = (t.counter_iban or "").replace(" ", "").upper()
        if iban:
            by_iban[iban].append(t)
        for w in set(re.split(r"[^a-z0-9]+", _txt(t)[0])) - {""}:
            by_word[w].append(t)

    def pool(p: dict) -> List[Tx]:
        """The transactions a rule can hit at all (same IBAN, or the rarest whole word of its name; a last word with * as
        the start of a word)."""
        if p.get("iban"):
            return by_iban.get(p["iban"], [])
        words = _tokens(_fold(p.get("name") or ""))
        if not words:
            return list(by_id.values())
        whole = words[:-1] if p.get("more") else words
        if whole:
            return min((by_word.get(w, []) for w in whole), key=len)
        return list({t.id: t for w, ts in by_word.items() if w.startswith(words[-1]) for t in ts}.values())
    out: List[dict] = []
    for (party, cat), mine in chosen.items():
        if not party or len(mine) < 2 or (assignable is not None and cat not in assignable):
            continue
        p = _base_rule(mine)
        if p is None:
            continue
        others = [t for t in by_party.get(party, ()) if _matches(p, t) and cat_of(t) and cat_of(t) != cat]
        if others:                                  # the same counterparty has other categories: tell them apart
            common = set.intersection(*(_txt(t)[1] for t in mine))
            words = sorted((w for w in common if not any(w in _txt(o)[1] for o in others)), key=lambda w: (-len(w), w))[:2]
            if words:
                p["purpose"] = words
            elif all(t.amount < 0 for t in mine) and all(o.amount > 0 for o in others):
                p["sign"] = -1
            elif all(t.amount > 0 for t in mine) and all(o.amount < 0 for o in others):
                p["sign"] = 1
            else:
                continue                            # cannot be told apart safely
        hits, clash = [], False
        for t in pool(p):
            if _matches(p, t):
                if cat_of(t) and cat_of(t) != cat:
                    clash = True                    # would hit another category: no proposal
                    break
                hits.append(t)
        if clash or not hits:
            continue
        ausdruck = expression(p)
        key = cat + "|" + ausdruck
        latest = max(hits, key=lambda t: (t.booking_date, t.id))
        if key in done or any(o["key"] == key for o in out) or (mm_of(latest) == cat and str(latest.id) not in (written or {})):
            continue                                # dismissed, twice, or the newest one MoneyMoney categorized itself: rule exists
        out.append({"key": key, "category": cat, "phrase": ausdruck, "name": mine[0].name[:80],
                    "yours": len(mine), "hits": len(hits), "open": sum(1 for t in hits if not cat_of(t))})
    out.sort(key=lambda x: (-x["open"], -x["yours"], x["category"]))
    _TXT.clear()
    return out[:limit]


def _party(t: Tx) -> str:
    iban = (t.counter_iban or "").replace(" ", "").upper()
    return iban if len(iban) >= 8 else norm_name(t.name)


def _base_rule(txs: List[Tx]) -> Optional[dict]:
    ibans = {(t.counter_iban or "").replace(" ", "").upper() for t in txs}
    if len(ibans) == 1 and len(next(iter(ibans))) >= 8:
        return {"iban": next(iter(ibans))}
    phrase, more = _name_phrase([t.name for t in txs])
    if len(_fold(phrase)) < 3:
        return None
    return {"name": phrase, "more": more}
