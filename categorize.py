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
import re
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

from model import Ledger, Tx, has_mark, norm_cat

FILE = "categories.json"


def empty() -> dict:
    return {"version": 3, "zuordnung": {}, "regeln": [], "gelernt_am": None}


def load(store) -> dict:
    """The stored state; a file of an older version (Kontor's own categories before 3.13.5) starts empty."""
    d = store.load(FILE, None) or {}
    if d.get("version") != 3:
        return empty()
    d.setdefault("zuordnung", {}); d.setdefault("regeln", [])
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
    z = d["zuordnung"].get(str(t.id))
    if waiting(z):
        return z["k"], "wartet"
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
        counts[q or "ohne"] += 1
    return dict(counts)


def set_waiting(d: dict, tx_ids: Iterable[int], path: str) -> int:
    """Your assignment, to be written into MoneyMoney ('' takes back what still waits)."""
    path = norm_cat(path)
    n = 0
    for tid in tx_ids:
        if path:
            d["zuordnung"][str(tid)] = {"k": path, "q": "manuell", "p": 1}
        else:
            d["zuordnung"].pop(str(tid), None)
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


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")).strip("-")[:80] or "k"


def rule_matches(r: dict, t: Tx) -> bool:
    if r.get("iban") and r["iban"] != (t.counter_iban or "").replace(" ", "").upper():
        return False
    if r.get("name_ist") and r["name_ist"] != norm_name(t.name):
        return False
    if r.get("zweck_enthaelt") and r["zweck_enthaelt"] not in norm_name(t.purpose + " " + t.booking_text):
        return False
    return bool(r.get("iban") or r.get("name_ist"))


def _specificity(r: dict) -> int:
    return (3 if r.get("iban") else 0) + (2 if r.get("zweck_enthaelt") else 0) + (2 if r.get("name_ist") else 0)


def _rule_index(d: dict) -> dict:
    """Learned patterns by IBAN and by name (kept in memory with the rules they were made of)."""
    idx = d.get("_idx")
    if idx is None or idx[0] is not d["regeln"]:
        by_iban: Dict[str, List[dict]] = defaultdict(list)
        by_name: Dict[str, List[dict]] = defaultdict(list)
        for r in d["regeln"]:
            if r.get("iban"):
                by_iban[r["iban"]].append(r)
            elif r.get("name_ist"):
                by_name[r["name_ist"]].append(r)
        idx = d["_idx"] = (d["regeln"], by_iban, by_name)
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
            r = {"id": rid, "kategorie": path, "iban": key, "quelle": "gelernt", "treffer": total, "aktiv": True}
        elif kind == "name":
            r = {"id": rid, "kategorie": path, "name_ist": key, "quelle": "gelernt", "treffer": total, "aktiv": True}
        else:
            nm, pk = key.split("|", 1)
            if nm in seen_names:
                continue
            r = {"id": rid, "kategorie": path, "name_ist": nm, "zweck_enthaelt": pk, "quelle": "gelernt", "treffer": total, "aktiv": True}
        learned.append(r)
        stats[kind] += 1
    d["regeln"] = learned
    d["gelernt_am"] = time.strftime("%Y-%m-%d %H:%M")
    return {"regeln": len(learned), "muster": len(samples), **{k: v for k, v in stats.items()}}


# ---------------------------------------------------------------------------
# What is still without a category
# ---------------------------------------------------------------------------

def needs_category(t: Tx, banks: Optional[set]) -> bool:
    """A transaction a category matters for: booked, of a bank account (loans, assets and the like count by their account,
    not their category), not one of Kontor's own bookings (mirror, interest, value)."""
    return t.booked and t.id > 0 and (banks is None or t.account_uuid in banks) and not has_mark(t.purpose)


def open_items(d: dict, ledger: Ledger, bereich_of: Dict[str, str], jahr: Optional[int] = None, bereich: Optional[str] = None,
               min_betrag: float = 0.0, limit: int = 400, banks: Optional[set] = None) -> Dict[str, Any]:
    """Transactions without a category (in MoneyMoney, nothing waiting), grouped by counterparty, with a suggestion.
    banks: the accounts a category matters for (bank accounts); None: all."""
    groups: Dict[str, dict] = {}
    total = 0
    for t in ledger.txs:
        if not needs_category(t, banks):
            continue
        path, q = effective(d, t)
        if path:
            continue
        if jahr and t.booking_date.year != jahr:
            continue
        if bereich and bereich_of.get(t.account_uuid) != bereich:
            continue
        if min_betrag and abs(t.amount) < min_betrag:
            continue
        total += 1
        key = (t.counter_iban or "").replace(" ", "").upper() or norm_name(t.name) or ("zweck:" + purpose_key(t.purpose, 4))
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": key, "name": t.name[:80] or t.purpose[:80], "iban": (t.counter_iban or "")[:34], "anzahl": 0, "summe": 0.0, "ids": [],
                               "umsaetze": [], "vorschlaege": {}, "konten": [], "von": t.booking_date.isoformat(), "bis": t.booking_date.isoformat()}
        r = suggest(d, t)
        if r:
            g["vorschlaege"][t.id] = r["kategorie"]
        acc = ledger.accounts[t.account_uuid].name if t.account_uuid in ledger.accounts else ""
        g["anzahl"] += 1
        g["summe"] = round(g["summe"] + t.amount, 2)
        g["ids"].append(t.id)
        if acc not in g["konten"]:
            g["konten"].append(acc)
        g["von"] = min(g["von"], t.booking_date.isoformat()); g["bis"] = max(g["bis"], t.booking_date.isoformat())
        if len(g["umsaetze"]) < 300:                # the transactions of the group: choose some of them (e.g. a shop that sells many things)
            g["umsaetze"].append({"id": t.id, "datum": t.booking_date.isoformat(), "betrag": t.amount, "zweck": t.purpose[:120], "konto": acc,
                                  "vorschlag": r["kategorie"] if r else None})
    out = sorted(groups.values(), key=lambda g: (-abs(g["summe"]), -g["anzahl"]))
    for g in out:
        g["umsaetze"].sort(key=lambda u: (u["datum"], u["id"]), reverse=True)
        kinds = set(g["vorschlaege"].values())
        # the group's suggestion only where every transaction has the same one (e.g. rent and service charges differ)
        g["vorschlag"] = next(iter(kinds)) if len(kinds) == 1 and len(g["vorschlaege"]) == g["anzahl"] else None
        g["vorschlaege"] = {str(k): v for k, v in g["vorschlaege"].items()}
    return {"offen": total, "gruppen": out[:limit], "gruppen_gesamt": len(out)}


def stats(d: dict, ledger: Ledger, banks: Optional[set] = None) -> Dict[str, Any]:
    c: Counter = Counter()
    years: Dict[int, Counter] = defaultdict(Counter)
    for t in ledger.txs:
        if not needs_category(t, banks):
            continue
        path, q = effective(d, t)
        k = q or "ohne"
        c[k] += 1
        years[t.booking_date.year][k] += 1
    return {"gesamt": dict(c), "jahre": {str(y): dict(v) for y, v in sorted(years.items())}, "gelernt_am": d.get("gelernt_am")}


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
        if not p["_name"] or not _phrase_in(p["_name"], _tokens(name), bool(p.get("weiter"))):
            return False
    if p.get("zweck") and not set(p["zweck"]) <= words:
        return False
    if p.get("vorzeichen") and (t.amount < 0) != (p["vorzeichen"] < 0):
        return False
    return True


def expression(p: dict) -> str:
    """The rule in MoneyMoney's syntax (Kategorie -> Einstellungen -> Regeln)."""
    parts = []
    if p.get("iban"):
        parts.append('remote_account:"%s"' % p["iban"])
    if p.get("name"):
        parts.append('name:"%s%s"' % (p["name"], "*" if p.get("weiter") else ""))
    for w in p.get("zweck") or []:
        parts.append('purpose:"%s"' % w)
    if p.get("vorzeichen"):
        parts.append("amount<0" if p["vorzeichen"] < 0 else "amount>0")
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
    done = set(d.get("regel_erledigt") or [])
    chosen: Dict[Tuple[str, str], List[Tx]] = defaultdict(list)            # (counterparty, category) -> your transactions
    for tid, w in (written or {}).items():
        t = by_id.get(int(tid)) if str(tid).lstrip("-").isdigit() else None
        if t is not None and mm_of(t) and mm_of(t) == norm_cat(w.get("neu") or ""):
            chosen[(_party(t), mm_of(t))].append(t)
    for tid, z in d["zuordnung"].items():
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
        whole = words[:-1] if p.get("weiter") else words
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
                p["zweck"] = words
            elif all(t.amount < 0 for t in mine) and all(o.amount > 0 for o in others):
                p["vorzeichen"] = -1
            elif all(t.amount > 0 for t in mine) and all(o.amount < 0 for o in others):
                p["vorzeichen"] = 1
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
        out.append({"key": key, "kategorie": cat, "ausdruck": ausdruck, "name": mine[0].name[:80],
                    "deine": len(mine), "treffer": len(hits), "offen": sum(1 for t in hits if not cat_of(t))})
    out.sort(key=lambda x: (-x["offen"], -x["deine"], x["kategorie"]))
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
    return {"name": phrase, "weiter": more}
