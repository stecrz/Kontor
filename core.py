"""Kernablaeufe, gemeinsam fuer Kommandozeile und Dienst: Daten holen, Konfiguration
pruefen, Lauf (Regeln anwenden, Buchungen schreiben, Berichte je Bereich bauen),
Einstellungspakete, Diagnoseprotokoll."""
from __future__ import annotations

import copy
import hashlib
import json
import time
import logging
import os
import platform
import re
import threading
import traceback
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from mm_bridge import Bridge, MoneyMoneyError, MoneyMoneyLocked, MoneyMoneyNotPermitted, MoneyMoneyNotRunning
from model import UUID_RE, Account, Ledger, Tx, accounts_from_export, add_months, fmt_eur, marks_in, month_key, tx_from_export, norm_cat
import mm_categories
import realestate
import categorize
from report import COST_WORDS, POS, ROLES, account_roles, build_dataset, equity_ratio, holding_key, my_positions
import rules
from rules import Proposal, parse_start, plan_all
from storage import Store
from tax import build_tax
from i18n import tr

log = logging.getLogger("kontor.core")
RUN_LOCK = threading.Lock()
REPORT_LOCK = threading.Lock()          # building the report (dataset.json): one at a time, beside a run
HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CONFIG: Dict[str, Any] = {
    "dry_run": True,
    "schedule": {"interval_minutes": 30, "automatic": True, "full_read_days": 30},
    "loans": [], "companies": [], "account_mirrors": [],
    "assign_without": None,        # areas whose transactions you do not categorise (their ids): left out under Kategorisieren;
                                   # None: not chosen yet -- all but the private areas (assign_skipped)
    "areas": [],
    "real_estate": [],
    "balance": {"months_back": 0, "roles": {}, "history_source": {}, "illiquid_roles": ["participations", "real_estate", "tangibles"],
               "illiquid_accounts": [], "inactive_months": 12, "hidden_accounts": [], "always_show": [], "view": "positions"},
    "cashflow": {"positions": {}, "category_to_account": {},
                     "recipient_to_account": {},      # per area: recipient (IBAN, else name) -> the account saving goes into | "extern"
                     "transfer_categories": ["Umbuchung"], "transfer_pairing": True, "pairing_manual_accounts": True},
    "tax": {"rental_category": "Vermietung", "property_loans": {}, "depreciation": {}, "positions": {}, "entities": []},
    "receipts": {"folder": "~/Documents/Kontor-Belege", "subfolder": "{year}", "write_comment": False, "folder_confirmed": False},
    "fetch": {"online": [], "offline": []},      # eigene Festlegung: Konto wird von MoneyMoney abgerufen / nicht (sonst erkannt)
    "not_book": [],      # bookings of the rules you chose not to book: {"key": account|mark, "datum", "betrag", "konto", "art", "text", "regel", "seit"}
    "updates": {"repo": "stecrz/Kontor", "check_mode": "daily"},   # pruefen: taeglich | woechentlich | aus
    "ui": {"lock_minutes": 15, "touchid": True, "port": 8765, "bind": "127.0.0.1", "tls_cert": "", "tls_key": ""},
}

# Felder mit Kontoreferenzen in Listen (fuer Pakete und Pruefung)
REF_FIELDS = [
    ("loans", "loan_account"), ("loans", "source_accounts"), ("companies", "participation"),
]


def _shape(cfg: dict) -> dict:
    """A configuration edited by hand or imported may hold the wrong kind of value somewhere (a text where a list belongs, a
    number where an account reference belongs). Such parts are dropped here, once, so nothing after it has to expect them --
    a rule that is incomplete after that is named by check_config and simply does not book."""
    def text(v) -> str:
        return v if isinstance(v, str) else ""

    def texts(v) -> List[str]:
        return [x for x in v if isinstance(x, str)] if isinstance(v, list) else ([v] if isinstance(v, str) and v else [])

    def number(v, default=None):
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v else default

    def day(v) -> str:
        try:
            return date.fromisoformat(v).isoformat() if isinstance(v, str) else ""
        except ValueError:
            return ""

    def dicts(v) -> List[dict]:
        return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []
    for k, v in DEFAULT_CONFIG.items():
        if k in cfg and isinstance(v, dict) and not isinstance(cfg[k], dict):
            cfg.pop(k)
        elif k in cfg and isinstance(v, list) and k != "assign_without":       # lists of entries (zuordnen_ohne: of area ids, below)
            cfg[k] = dicts(cfg[k])
    kf = cfg.get("cashflow")
    if isinstance(kf, dict) and "recipient_to_account" in kf:
        e = kf["recipient_to_account"]
        kf["recipient_to_account"] = {str(a): {str(k): v for k, v in m.items() if isinstance(v, str) and v}
                                     for a, m in (e.items() if isinstance(e, dict) else []) if isinstance(m, dict)}
    for b in cfg.get("areas") or []:
        for f in ("id", "name", "kind"):
            if f in b and not isinstance(b[f], str):
                b[f] = str(b[f]) if isinstance(b[f], (int, float)) and not isinstance(b[f], bool) else ""
            if f in b and not b[f] and f != "kind":
                b.pop(f)
        b["accounts"] = texts(b.get("accounts"))
        if "share" in b:
            b["share"] = number(b["share"])
    for d in cfg.get("loans") or []:
        d["loan_account"] = text(d.get("loan_account"))
        d["source_accounts"] = texts(d.get("source_accounts"))
        e = d["detection"] = d["detection"] if isinstance(d.get("detection"), dict) else {}
        for f in ("counter_iban", "text_contains", "exclude_text"):
            if f in e and not isinstance(e[f], str):
                e[f] = texts(e[f])
        d["from_date"] = day(d.get("from_date"))
        if not d["from_date"] or not d["loan_account"]:
            d["active"] = False                      # cannot run: shown as switched off until it is complete
        if "name" in d and not isinstance(d["name"], str):
            d.pop("name")
        if "booking" in d and not isinstance(d["booking"], dict):
            d.pop("booking")
        for f in [f for f, v in (d.get("booking") or {}).items() if v is not None and not isinstance(v, str)]:
            d["booking"].pop(f)
        if "kind" in d and not isinstance(d["kind"], str):
            d.pop("kind")
        z = d.get("interest")
        if z is not None and not isinstance(z, dict):
            d.pop("interest")
        elif z:
            z["rate_list"] = [{"from_date": day(r.get("from_date")), "percent": number(r.get("percent"))} for r in dicts(z.get("rate_list")) if number(r.get("percent")) is not None]
            z["base_override"] = {str(k): number(v) for k, v in z["base_override"].items() if number(v) is not None} if isinstance(z.get("base_override"), dict) else {}
            for f in ("model", "booking_day"):
                if f in z and not isinstance(z[f], str):
                    z.pop(f)
    for g in cfg.get("companies") or []:
        g["area"] = str(g["area"]) if isinstance(g.get("area"), (str, int)) and not isinstance(g.get("area"), bool) else ""
        for f in ("participation", "retroactive_from", "cycle", "counterparty", "category"):
            if f in g:
                g[f] = text(g[f])
        if "threshold" in g:
            g["threshold"] = number(g["threshold"], 0.01)
    if cfg.get("assign_without") is not None:
        cfg["assign_without"] = [str(x) for x in cfg["assign_without"] if isinstance(x, (str, int)) and not isinstance(x, bool)] if isinstance(cfg["assign_without"], list) else []
    if "account_mirrors" in cfg:
        cfg["account_mirrors"] = [dict({"a": text(m.get("a")), "b": text(m.get("b")), "from_date": text(m.get("from_date"))},
                                     **{f: text(m[f]) for f in ("category",) if text(m.get(f))}) for m in dicts(cfg["account_mirrors"])]
    bil = cfg.get("balance")
    if isinstance(bil, dict):
        for f in ("roles", "history_source", "accounts_mapping"):
            if f in bil:
                bil[f] = {k: v for k, v in bil[f].items() if isinstance(k, str) and isinstance(v, dict if f == "accounts_mapping" else str)} if isinstance(bil[f], dict) else {}
        for f in ("illiquid_accounts", "hidden_accounts", "always_show", "illiquid_roles"):
            if f in bil:
                bil[f] = texts(bil[f])
        for f in ("months_back", "inactive_months"):
            if f in bil and number(bil[f]) is None:
                bil.pop(f)
    ab = cfg.get("fetch")
    if isinstance(ab, dict):
        for f in ("online", "offline"):
            if f in ab:
                ab[f] = texts(ab[f])
    if "not_book" in cfg:
        keep, have = [], set()
        for x in cfg["not_book"]:
            acc, _, tag = text(x.get("key")).partition("|")
            if acc and rules.TAG_RE.fullmatch(tag) and x["key"] not in have:
                have.add(x["key"])
                keep.append({k: v for k, v in x.items() if isinstance(v, (str, int, float)) and not isinstance(v, bool)})
        cfg["not_book"] = keep[-1000:]
    return cfg


def merged_config(cfg: Optional[dict]) -> dict:
    out: Dict[str, Any] = {}
    cfg = _shape(copy.deepcopy(cfg)) if isinstance(cfg, dict) else {}
    for k, v in DEFAULT_CONFIG.items():
        if isinstance(v, dict):
            out[k] = copy.deepcopy(v)
            out[k].update(cfg.get(k) or {})
        else:
            out[k] = cfg.get(k, v)
    for k, v in cfg.items():
        if k not in out:
            out[k] = v
    for i, b in enumerate(out["areas"]):
        b.setdefault("id", "b%d" % (i + 1))
        b.setdefault("name", "Bereich %d" % (i + 1))
        b.setdefault("accounts", [])
        b.setdefault("kind", "")
        b.setdefault("active", True)
    if out["areas"] and not any(b.get("main_area") for b in out["areas"]):
        out["areas"][0]["main_area"] = True
    for im in out.get("real_estate") or []:
        im.setdefault("calcs", [])
        im.setdefault("documents", [])
        im.setdefault("loan_accounts", {})
    return out


def assign_skipped(config: dict, bereiche: List[dict]) -> Set[str]:
    """The areas left out under Kategorisieren: your choice; before you chose, all but the private ones (the main area if none
    is private) -- a company with countless bookings stays out until you tick it."""
    v = config.get("assign_without")
    if isinstance(v, list):
        return {str(x) for x in v}
    keep = {str(b["id"]) for b in bereiche if b.get("kind") == "private"} or {str(b["id"]) for b in bereiche if b.get("main_area")}
    return {str(b["id"]) for b in bereiche if str(b["id"]) not in keep}


def version_on_disk() -> str:
    """Version laut Datei VERSION im Programmordner (aendert sich bei git pull / Update)."""
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0"


LOADED_VERSION = version_on_disk()      # Version des Codes, der in diesem Prozess tatsaechlich laeuft


def version() -> str:
    """Version des laufenden Codes (nicht der Datei -- die kann nach einem Update schon neuer sein)."""
    return LOADED_VERSION


# ---------------------------------------------------------------------------
# Daten holen
# ---------------------------------------------------------------------------

def earliest_needed(config: dict, today: date) -> date:
    back = int((config.get("balance", {}) or {}).get("months_back", 0) or 0)
    if back <= 0:
        return date(2000, 1, 1)
    y, m = add_months(today, -(back + 1))
    start = date(y, m, 1)
    for l in config.get("loans", []) or []:
        try:
            ab = date.fromisoformat(l["from_date"])
            start = min(start, date(ab.year - 1, 1, 1))
        except Exception:
            pass
    for ab in [(g or {}).get("retroactive_from") for g in config.get("companies", []) or []] + [m["from_date"] for m in rules.mirrors(config)]:
        rs = parse_start(ab)
        if rs == "all":
            start = min(start, date(2000, 1, 1))
        elif rs:
            start = min(start, date(rs.year - 1, 1, 1))
    return start


INCREMENT_DAYS = 30          # quick read: only the last 30 days of transactions, older ones come from the last full read
RECHECK_HOURS = 12           # a balance the quick read cannot explain triggers a full read at most this often


def recategorized(base: Ledger, fresh: List[Tx]) -> int:
    """Transactions of the quick read that changed from one category to another in MoneyMoney (not: got their first one). You
    are rearranging categories there -- older transactions may have moved as well, so everything is read."""
    def cat(path: Optional[str]) -> str:
        p = norm_cat(path or "")
        return "" if p in categorize.STANDARD else p            # MoneyMoney's default category counts as none
    old = {t.id: cat(t.mm_category_path if t.mm_category_path is not None else t.category_path) for t in base.txs if t.id > 0}
    n = 0
    for t in fresh:
        was = old.get(t.id)
        if was and was != cat(t.category_path):
            n += 1
    return n


def category_tree(categories: Optional[List[dict]]) -> set:
    """MoneyMoney's categories as a set of (id, path): differs when one was added, deleted, renamed or moved."""
    return {(str(c.get("uuid") or ""), norm_cat(str(c.get("path") or c.get("name") or ""))) for c in categories or []}


def follow_categories(config: dict, old: Optional[List[dict]], new: Optional[List[dict]]) -> Optional[dict]:
    """A category renamed, moved or deleted in MoneyMoney: what you set for it in Kontor follows (cash flow position, target
    account, a property's category) or goes with it. Returns the changed settings, or None when nothing changed. Only with both
    lists known and ids in them (never guesses by name)."""
    was = {str(c.get("uuid")): norm_cat(str(c.get("path") or c.get("name") or "")) for c in old or [] if c.get("uuid")}
    now = {str(c.get("uuid")): norm_cat(str(c.get("path") or c.get("name") or "")) for c in new or [] if c.get("uuid")}
    if not was or not now:
        return None
    moved = {p: now[u] for u, p in was.items() if u in now and now[u] != p and p}
    vanished = {p for u, p in was.items() if u not in now and p}
    # deleted: its entry goes -- unless a new category has its name (deleted and made again); one renamed into the name wins.
    # Most of them gone at once (another database, or a big tidy-up): nothing is dropped -- renamed ones still follow (by id).
    gone = {p for p in vanished if p not in set(now.values()) or p in set(moved.values())}
    if len(vanished) > max(3, len(was) // 2):
        gone = gone & set(moved.values())
    if not moved and not gone:
        return None
    cfg = copy.deepcopy(config)
    kf = cfg.setdefault("cashflow", {})
    changed = False
    for key in ("positions", "category_to_account"):
        out, follow = {}, {}
        for k, v in (kf.get(key) or {}).items():
            p = norm_cat(str(k))
            if p in moved:
                changed = True
                follow[moved[p]] = v
            elif p in gone:
                changed = True
            else:
                out[k] = v
        out.update(follow)
        kf[key] = out
    for im in cfg.get("real_estate") or []:
        p = norm_cat(str(im.get("category") or "")) if isinstance(im, dict) else ""
        if p and p in moved:
            im["category"] = moved[p].replace(" / ", "\\")
            changed = True
    return cfg if changed else None


def unexplained_balances(base: Ledger, accounts: Dict[str, Account], fresh: List[Tx], cut: date) -> List[str]:
    """Accounts whose balance changed by more than the transactions since `cut` explain: something older than `cut` changed
    in MoneyMoney (a late booking with an old date, an edited or deleted transaction). Portfolios are skipped (their value
    moves without transactions); pending transactions may or may not be part of a bank's balance, so either way counts."""
    def sums(txs):
        booked: Dict[str, float] = {}
        total: Dict[str, float] = {}
        for t in txs:
            if t.booking_date < cut:
                continue
            total[t.account_uuid] = total.get(t.account_uuid, 0.0) + t.amount
            if t.booked:
                booked[t.account_uuid] = booked.get(t.account_uuid, 0.0) + t.amount
        return booked, total
    # base holds no planned bookings (Ledger.without_planned), only Kontor's written ones (id <= 0) until the next full read:
    # they are in MoneyMoney's balance as well, so they count like any other transaction
    ob, oa = sums(base.txs)
    nb, na = sums(fresh)
    out = []
    for uuid, acc in accounts.items():
        old = base.accounts.get(uuid)
        if acc.group or acc.portfolio or old is None or old.portfolio or old.currency != acc.currency:
            continue
        d = acc.balance - old.balance
        if abs(d - (nb.get(uuid, 0.0) - ob.get(uuid, 0.0))) < 0.005 or abs(d - (na.get(uuid, 0.0) - oa.get(uuid, 0.0))) < 0.005:
            continue
        out.append(uuid)
    return out


def _base_txs(base: Ledger, accounts: Dict[str, Account], fresh_ids: set, cut: date, fresh_txs: List[Tx] = ()) -> List[Tx]:
    """Aeltere Umsaetze aus dem letzten Stand (nur echte aus MoneyMoney, Kategorie im Original). Was an oder nach `cut`
    gebucht oder wertgestellt ist, kommt nur aus dem frischen Lesen -- so verschwinden dort geloeschte Umsaetze
    (z. B. vorgemerkte, die MoneyMoney durch die gebuchten ersetzt)."""
    out = []
    fresh_marks = None
    for t in base.txs:
        if t.id in fresh_ids or t.account_uuid not in accounts:
            continue
        if t.id <= 0:                 # written by Kontor, real one not read yet: keep it unless the quick read brought it
            if fresh_marks is None:
                fresh_marks = {(x.account_uuid, m) for x in fresh_txs for m in marks_in(x.purpose)}
            ms = marks_in(t.purpose)
            if not ms or any((t.account_uuid, m) in fresh_marks for m in ms) or t.booking_date >= cut:
                continue
            out.append(t)
            continue
        if t.booking_date >= cut or (t.value_date is not None and t.value_date >= cut):
            continue
        c = Tx.__new__(Tx)                       # flache Kopie (schneller als dataclasses.replace bei ~200.000 Umsaetzen)
        c.__dict__.update(t.__dict__)
        if t.mm_category_path is not None:       # Kontor-Kategorie lag darueber -> Original aus MoneyMoney
            path = t.mm_category_path
            c.category_path, c.category, c.mm_category_path = path, (path.replace("\\", " / ").split(" / ")[-1] if path else ""), None
        out.append(c)
    return out


def fetch(bridge: Bridge, config: dict, today: date, with_portfolio: bool = False, progress: Optional[Callable[[str], None]] = None,
          base: Optional[Ledger] = None, full: bool = True) -> Ledger:
    """Konten, Umsaetze und ggf. Depotbestaende aus MoneyMoney lesen. progress(schritt) meldet den laufenden Schritt.
    full=False und ein vollstaendiger letzter Stand (base, gleicher Zeitraum): nur die letzten INCREMENT_DAYS Tage lesen und
    mit den aelteren Umsaetzen aus base zusammenfuehren. Aenderungen an aelteren Umsaetzen in MoneyMoney kommen mit dem
    naechsten vollstaendigen Lesen (siehe App.full_read_due)."""
    step = progress or (lambda _s: None)
    step("accounts")
    accounts = accounts_from_export(bridge.export_accounts())
    since = earliest_needed(config, today)
    inc = None
    if not full and base is not None and getattr(base, "since", None) == since and getattr(base, "full_at", None):
        inc = max(since, today - timedelta(days=INCREMENT_DAYS))
    step("transactions")
    raw = bridge.export_transactions(inc or since)
    step("parse")
    txs = tx_from_export(raw)
    del raw
    n_read = len(txs)
    if inc:
        bad = unexplained_balances(base, accounts, txs, inc)
        if bad and datetime.now() - base.full_at >= timedelta(hours=RECHECK_HOURS):
            log.info("Quick read does not explain the balance of %d account(s) -- reading all transactions", len(bad))
            step("transactions")
            raw = bridge.export_transactions(since)
            step("parse")
            txs = tx_from_export(raw)
            del raw
            n_read, inc = len(txs), None
        elif bad:
            log.info("Quick read does not explain the balance of %d account(s); last full read %s, next one later",
                     len(bad), base.full_at.strftime("%Y-%m-%d %H:%M"))
    if inc:
        moved = recategorized(base, txs)
        if moved:
            log.info("%d transaction(s) moved to another category in MoneyMoney -- reading all transactions", moved)
            step("transactions")
            raw = bridge.export_transactions(since)
            step("parse")
            txs = tx_from_export(raw)
            del raw
            n_read, inc = len(txs), None
    if inc:
        txs = _base_txs(base, accounts, {t.id for t in txs}, inc, txs) + txs
        # the accounts the booking rules read or book are always read in full: the rules never plan on an older state of them
        # (a booking with an old date added, changed or deleted there since the last full read) -- they are few and small
        try:
            uu = rule_accounts(Ledger(accounts, []), config)
        except Exception:  # pragma: no cover - a broken reference: the checks name it, the quick read stands
            uu = set()
        if uu:
            step("transactions")
            fresh, got = _read_accounts(bridge, since, uu)
            txs = [t for t in txs if t.account_uuid not in got] + fresh
            n_read += len(fresh)
        txs.sort(key=lambda t: (t.booking_date, t.id))
    ledger = Ledger(accounts, txs)
    ledger.since = since
    ledger.full_at = base.full_at if inc else datetime.now()
    ledger.incremental = bool(inc)
    ledger.portfolios = {}
    if with_portfolio:
        step("portfolios")
        for a in accounts.values():
            if a.portfolio and not a.group:
                try:
                    ledger.portfolios[a.uuid] = bridge.export_portfolio(a.uuid)
                except MoneyMoneyError as e:
                    log.info("Portfolio %s: no holdings data (%s)", a.uuid[:8], str(e)[:80])
    log.info("MoneyMoney: %d accounts, %d transactions since %s%s, %d portfolios", len(accounts), len(txs), since,
             (" (read from %s: %d, older from last full read %s)" % (inc, n_read, base.full_at.strftime("%Y-%m-%d %H:%M"))) if inc
             else " (full read)", len(ledger.portfolios))
    ledger.fp = fingerprint(ledger)          # Fingerabdruck des frischen Stands (vor Probelauf-Buchungen, die Salden veraendern)
    ledger.acc_sig = account_sig(accounts)   # Kontenstand dieses Lesens (Vergleich fuer den Schnellabgleich)
    return ledger


def rule_accounts(ledger: Ledger, config: dict) -> set:
    """The accounts the booking rules read or book -- all the approval list depends on: loan accounts and the accounts their
    payments come from, participation and counter accounts with their sources, the accounts of each company (its value)."""
    out: set = set()

    def add(ref) -> None:
        try:
            a = ledger.resolve(str(ref or ""))
        except KeyError:
            return
        out.update(x.uuid for x in (ledger.descendants(a.uuid) if a.group else [a]))
    for d in config.get("loans") or []:
        if isinstance(d, dict) and d.get("active", True):
            add(d.get("loan_account"))
            for src in d.get("source_accounts") or []:
                add(src)
    for m in rules.mirrors(config):
        add(m["a"]); add(m["b"])
    companies = [g for g in config.get("companies") or [] if isinstance(g, dict) and g.get("participation")]
    if companies:
        areas = {str(b["id"]): b for b in bereiche_for(ledger, config)}
        for g in companies:
            add(g.get("participation"))
            area = areas.get(str(g.get("area")))
            if area:
                out.update(a.uuid for a in area["leaves"] if not a.group)
    return out


def _read_accounts(bridge: Bridge, since: date, uuids: set) -> Tuple[List[Tx], set]:
    """All transactions of some accounts since `since`, one account at a time (only what belongs to it): (transactions, the
    accounts read). An account MoneyMoney does not export on its own keeps what was read before (the rest is still read);
    MoneyMoney locked or gone stops everything as usual."""
    out: List[Tx] = []
    read: set = set()
    for u in sorted(uuids):
        try:
            rows = bridge.export_transactions(since, account=u)
        except (MoneyMoneyNotRunning, MoneyMoneyLocked, MoneyMoneyNotPermitted):
            raise
        except MoneyMoneyError as e:
            log.warning("Account %s not read on its own (%s) -- kept as read before", u[:8], str(e)[:80])
            continue
        out += [t for t in tx_from_export(rows) if t.account_uuid == u]
        read.add(u)
    return out, read


def refresh_accounts(bridge: Bridge, base: Ledger, config: dict, today: date, uuids: set) -> Ledger:
    """The last state with only some accounts read again (balance, transactions since the start of the period); the others
    stay as read last. Kontor's own bookings kept until the next full read are replaced by what is in MoneyMoney now."""
    now = accounts_from_export(bridge.export_accounts())
    since = getattr(base, "since", None) or earliest_needed(config, today)
    fresh, got = _read_accounts(bridge, since, uuids)
    accs = dict(base.accounts)
    for u in got:
        if u in now:
            accs[u] = now[u]
    txs = [t for t in base.txs if t.account_uuid not in got] + fresh
    txs.sort(key=lambda t: (t.booking_date, t.id))
    led = Ledger({k: copy.copy(a) for k, a in accs.items()}, txs)
    for k, v in base.__dict__.items():          # read times, period, portfolios ... (no caches: "_...")
        if k not in ("accounts", "txs") and not k.startswith("_"):
            setattr(led, k, v)
    led.hints = []
    led.fp = fingerprint(led)
    log.info("MoneyMoney: %d account(s) read again, %d transactions", len(got), len(fresh))
    return led


def account_sig(accounts: Dict[str, Account]) -> tuple:
    """Salden und Abrufzeiten aller Konten -- aendert sich, sobald MoneyMoney neue Daten hat."""
    return tuple(sorted((a.uuid, a.balance, a.refresh.isoformat() if a.refresh else "") for a in accounts.values() if not a.group))


def ledger_fp(ledger: Ledger) -> str:
    return getattr(ledger, "fp", None) or fingerprint(ledger)


def fingerprint(ledger: Ledger) -> str:
    """Inhalt des MoneyMoney-Stands: Konten (Name, Pfad, Typ, Saldo), Umsaetze (Betrag, Datum, Texte, Kategorie aus
    MoneyMoney, vorgemerkt) und Depotpositionen. Kontor-eigene Ueberlagerungen (Kategorien, Probelauf-Buchungen mit
    negativer Nummer) zaehlen nicht -- gleicher Fingerabdruck = gleiche Daten in MoneyMoney. Die Abrufzeit zaehlt nicht:
    ein Bankabruf ohne neue Daten braucht keine Neuberechnung (App.set_ledger uebernimmt nur die Zeiten)."""
    h = hashlib.sha256()
    for a in sorted(ledger.accounts.values(), key=lambda x: x.uuid):
        h.update(("%s|%s|%s|%s|%.2f\n" % (a.uuid, a.path or a.name, a.type, a.portfolio, a.balance)).encode())
    rows = []
    for t in ledger.txs:
        if t.id < 0:
            continue
        mm = t.mm_category_path if t.mm_category_path is not None else t.category_path
        rows.append("%d|%s|%s|%.2f|%s|%s|%s|%s|%s|%d|%s" % (t.id, t.account_uuid, t.booking_date, t.amount, mm, t.name, t.purpose,
                                                           t.booking_text, t.counter_iban, t.booked, t.comment))
    h.update("\n".join(rows).encode())
    h.update(json.dumps(getattr(ledger, "portfolios", None) or {}, sort_keys=True, default=str).encode())
    return h.hexdigest()


def unavailable_text(e: Exception) -> Optional[str]:
    if isinstance(e, MoneyMoneyNotRunning):
        return tr("s_moneymoney_laeuft_nicht")
    if isinstance(e, MoneyMoneyLocked):
        return tr("s_moneymoney_ist_gesperrt_bitte_in")
    if isinstance(e, MoneyMoneyNotPermitted):
        return (tr("s_keine_berechtigung_moneymoney_zu_steue"))
    return None


# wie guessArt in der Oberflaeche
_FIRMA_RE = re.compile(r"\b(gmbh|ug|ag|se|kg|ohg|gbr|egbr|e\.?\s?k\.?|e\.?\s?v\.?|eg|ltd|inc|llc|holding|verwaltung|beteiligung|"
                       r"immobilien|stiftung|verein|genossenschaft|partner|&\s?co)\b|gmbh|gbr|holding|gesellschaft", re.I)


def _bereich_art(name: str) -> str:
    return "company" if _FIRMA_RE.search(name or "") else "private"


def bereiche_for(ledger: Ledger, config: dict) -> List[dict]:
    """Bereiche mit aufgeloesten Konten: konfiguriert, sonst alle Kontengruppen der obersten Ebene.
    Jeder Bereich: {"id", "name", "art", "anteil", "haupt", "konten" (Referenzen), "leaves" (Account), "gruppen"}."""
    out: List[dict] = []
    cfg = [b for b in (config.get("areas") or []) if isinstance(b, dict) and b.get("active", True)]
    if cfg:
        for b in cfg:
            leaves: List[Account] = []
            gruppen: List[Account] = []
            seen = set()
            for ref in b.get("accounts") or []:
                try:
                    a = ledger.resolve(ref)
                except KeyError:
                    continue
                members = ledger.descendants(a.uuid) if a.group else [a]
                if a.group:
                    gruppen.append(a)
                for x in members:
                    if x.uuid not in seen:
                        seen.add(x.uuid)
                        leaves.append(x)
            if not leaves and not b.get("accounts"):
                continue
            first_group = gruppen[0] if gruppen else None
            anteil = b.get("share")
            out.append({"id": str(b.get("id")), "name": b.get("name") or (first_group.name if first_group else "Bereich"),
                        "kind": b.get("kind") or _bereich_art(b.get("name") or (first_group.name if first_group else "")),
                        "share": float(anteil) if anteil not in (None, "") else None, "main_area": bool(b.get("main_area")),
                        "accounts": list(b.get("accounts") or []), "leaves": leaves, "groups": gruppen})
    if not out:
        for g in ledger.roots():
            out.append({"id": g.uuid, "name": g.name, "kind": _bereich_art(g.name), "share": None, "main_area": False,
                        "accounts": ["%s | %s" % (g.uuid, g.name)], "leaves": ledger.descendants(g.uuid), "groups": [g]})
        if out and not any(b["main_area"] for b in out):
            (next((b for b in out if b["kind"] == "private"), None) or out[0])["main_area"] = True
        # Vorschlag: Hauptbereich zuerst, dann weitere private Bereiche, dann Gesellschaften
        out.sort(key=lambda b: (not b["main_area"], b["kind"] != "private"))
    if out and not any(b["main_area"] for b in out):
        out[0]["main_area"] = True
    # Explizite Kontenzuordnung (Einrichtung → Konten): Konto in genau diesem Bereich, unabhaengig von der Gruppe
    by_id = {b["id"]: b for b in out}
    for ref, z in ((config.get("balance") or {}).get("accounts_mapping") or {}).items():
        if not isinstance(z, dict) or not z.get("area") or z["area"] not in by_id:
            continue
        try:
            a = ledger.resolve(ref)
        except KeyError:
            continue
        if a.group:
            continue
        for b in out:
            b["leaves"] = [x for x in b["leaves"] if x.uuid != a.uuid]
        by_id[z["area"]]["leaves"].append(a)
    return out


def abruf_arten(ledger: Ledger, config: dict) -> Dict[str, Dict[str, str]]:
    """uuid -> {"art": "online"|"offline", "grund": Text} fuer alle Konten (keine Gruppen). Online = MoneyMoney ruft bei
    Bank oder Dienst ab; offline = von Hand gefuehrt, kein Abruf (zaehlt nicht fuer den Datenstand). MoneyMoney setzt den
    Abrufzeitpunkt auch bei Offline-Konten (z. B. nach einer Buchung), deshalb mehrere Merkmale; eigene Festlegung geht vor."""
    out: Dict[str, Dict[str, str]] = {}
    for a in ledger.accounts.values():
        if not a.group:
            art, grund = ledger.fetch_kind(a.uuid, config)
            out[a.uuid] = {"kind": art, "reason": tr(grund)}
    return out


def freeze_assignments(ledger: Ledger, config: dict) -> Optional[dict]:
    """Bestaetigte Konten ohne feste Position/Verlaufsquelle (aeltere Einrichtung mit "auto") auf den heute erkannten Wert
    festlegen, damit spaetere Aenderungen an Name, Typ oder Gruppe in MoneyMoney die Zuordnung nicht verschieben.
    Liefert die geaenderte Konfiguration oder None, wenn nichts zu tun ist. Unbestaetigte (neue) Konten bleiben Vorschlag."""
    bil = config.get("balance") or {}
    zu = bil.get("accounts_mapping") or {}
    if not zu:
        return None
    roles = account_roles(ledger, config)
    ver_cfg = {}
    for ref in (bil.get("history_source") or {}):
        try:
            ver_cfg[ledger.resolve(ref).uuid] = ref
        except KeyError:
            pass
    new = copy.deepcopy(config)
    nb = new.setdefault("balance", {})
    nzu, nver = nb.setdefault("accounts_mapping", {}), nb.setdefault("history_source", {})
    changed = 0
    for ref, z in zu.items():
        if not isinstance(z, dict) or not z.get("confirmed", True):
            continue
        try:
            a = ledger.resolve(ref)
        except KeyError:
            continue
        if a.group:
            continue
        if z.get("position") not in ROLES and roles.get(a.uuid) in ROLES:
            nzu[ref] = dict(z, position=roles[a.uuid])
            changed += 1
        if a.uuid not in ver_cfg:
            nver[ref] = "balances" if a.portfolio else "transactions"
            changed += 1
    return new if changed else None


def konten_neu(ledger: Ledger, config: dict, bereiche: List[dict], roles: Dict[str, str]) -> List[dict]:
    """Konten ohne bestaetigte Zuordnung (neu in MoneyMoney oder noch nie bestaetigt) mit Vorschlag."""
    zu = (config.get("balance") or {}).get("accounts_mapping") or {}
    confirmed = set()
    for ref in zu:
        try:
            confirmed.add(ledger.resolve(ref).uuid)
        except KeyError:
            pass
    bereich_of = {a.uuid: b for b in bereiche for a in b["leaves"]}
    out = []
    for a in ledger.accounts.values():           # Reihenfolge wie in MoneyMoney
        if a.group or a.uuid in confirmed or not a.path:
            continue
        b = bereich_of.get(a.uuid)
        out.append({"uuid": a.uuid, "name": a.name, "path": a.path, "type_name": a.type, "balance_amount": a.balance,
                    "area": b["id"] if b else None, "area_name": b["name"] if b else None, "position": roles.get(a.uuid, "other")})
    return out


def main_bereich(bereiche: List[dict]) -> Optional[dict]:
    return next((b for b in bereiche if b.get("main_area")), bereiche[0] if bereiche else None)


# ---------------------------------------------------------------------------
# Konfiguration pruefen
# ---------------------------------------------------------------------------

def _acct_name(ledger, ref: str) -> str:
    """An account's name for a message (the reference itself if it is gone)."""
    try:
        return ledger.resolve(ref).name
    except KeyError:
        return str(ref).split("|")[-1].strip()


def check_config(ledger: Ledger, categories: List[dict], config: dict) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    cat_names = {str(c.get("name") or "") for c in categories}
    cat_names |= {str(c.get("path") or "").split("\\")[-1] for c in categories}

    def add(level, text):
        out.append({"severity": level, "text": text})

    def ref(label, r, want_offline=False, group_ok=True, want_group=False):
        try:
            a = ledger.resolve(r)
        except KeyError as e:
            add("error", "%s: %s" % (label, e)); return None
        if want_offline and not ledger.writable(a.uuid, config):
            add("error", tr("s_s_s_hat_eine_bankanbindung") % (label, a.path))
        elif not group_ok and a.group:
            add("error", tr("s_s_s_ist_eine_gruppe") % (label, a.path))
        elif want_group and not a.group:
            add("error", tr("s_s_s_ist_keine_gruppe") % (label, a.path))
        else:
            add("ok", "%s → %s" % (label, a.path))
        return a

    def setting(label, r, **kw):
        """A setting kept per account (position, history, shown/hidden): an account deleted in MoneyMoney is no finding --
        the entry is ignored and goes with the next save (prune_account_settings)."""
        if account_deleted(ledger, r):
            return None
        return ref(label, r, **kw)

    def cat(label, name):
        name = norm_cat(name).replace(" / ", "\\") if name else name      # paths as Kontor's pages write them ("A / B", "A › B")
        if name and categories and name not in cat_names and name.split("\\")[-1] not in cat_names:
            add("warning", tr("s_s_kategorie_s_existiert_nicht") % (label, name))

    for l in config.get("loans", []) or []:
        n = l.get("name", "?") + ("" if l.get("active", True) else " (inaktiv)")
        ref(tr("s_darlehen_s_konto") % n, l.get("loan_account", ""), want_offline=True, group_ok=False)
        for s_ in l.get("source_accounts", []) or []:
            ref("Darlehen %s: Quelle" % n, s_, group_ok=False)
        b = l.get("booking", {}) or {}
        cat("Darlehen %s" % n, b.get("category_repayment"))
        cat("Darlehen %s" % n, b.get("category_interest"))
        erk = l.get("detection") or {}
        iban = (erk.get("counter_iban") or "").replace(" ", "")
        if not iban and not erk.get("text_contains"):
            add("error", tr("s_darlehen_s_erkennung_braucht_gegen") % n)
        if iban and not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", iban):
            add("error", tr("s_darlehen_s_s_ist_keine") % (n, iban))
        try:
            date.fromisoformat(l.get("from_date", ""))
        except ValueError:
            add("error", tr("s_darlehen_s_ab_datum_fehlt") % n)
    bil = config.get("balance", {}) or {}
    for b in config.get("areas") or []:
        if not isinstance(b, dict):
            continue
        if not b.get("accounts"):
            add("error", tr("s_bereich_s_hat_keine_konten") % b.get("name"))
        for r in b.get("accounts") or []:
            ref("Bereich %s" % b.get("name"), r)
    bereiche = bereiche_for(ledger, config)
    seen_leaf: Dict[str, str] = {}
    roles = account_roles(ledger, config)
    for b in bereiche:
        for a in b["leaves"]:
            if a.uuid in seen_leaf and seen_leaf[a.uuid] != b["name"]:
                add("warning", tr("s_konto_s_liegt_in_mehreren") % (a.path, seen_leaf[a.uuid], b["name"]))
            seen_leaf[a.uuid] = b["name"]
        missing = [a.path for a in b["leaves"] if roles.get(a.uuid) == "other"]
        if missing:
            add("warning", tr("s_s_konten_ohne_position_umsaetze")
                % (b["name"], "; ".join(missing[:8]) + (" …" if len(missing) > 8 else "")))
    by_id = {b["id"]: b for b in bereiche}
    used: Dict[str, str] = {}
    for g in config.get("companies") or []:
        if not isinstance(g, dict) or not g.get("participation"):
            continue
        b = by_id.get(str(g.get("area")))
        if b is None:              # area removed or changed: the rules wait (no error, so the areas can still be saved)
            add("warning", tr("s_gesellschaft_s_bereich_fehlt") % g.get("area"))
            continue
        n, inside = b["name"], {a.uuid for a in b["leaves"]}
        if g.get("cycle") not in (None, "", "daily", "monthly"):
            add("error", tr("s_s_takt_unbekannt") % (n, g.get("cycle")))
        rs = parse_start(g.get("retroactive_from")) if g.get("retroactive_from") else ""
        if rs is None or (rs not in ("", "all") and rs > date.today()):
            add("error", tr("s_s_rueckwirkend_ungueltig") % (n, g["retroactive_from"]))
        targets = []
        if g.get("participation"):
            if b.get("share") is None:
                add("error", tr("s_s_anteil_fehlt") % (tr("s_regel_beteiligung") % n))
            a = ref(tr("s_regel_beteiligung") % n, g["participation"], want_offline=True, group_ok=False)
            if a is not None:
                targets.append(a)
                if roles.get(a.uuid) != "participations":
                    add("warning", tr("s_s_keine_position_beteiligungen") % (tr("s_regel_beteiligung") % n, a.name))
        for a in targets:
            if a.uuid in inside:
                add("error", tr("s_s_zielkonto_liegt_innerhalb_der") % ("%s: %s" % (n, a.name)))
            if a.uuid in used:
                add("error", tr("s_konto_s_mehrfach_ziel") % (a.path, used[a.uuid], n))
            used.setdefault(a.uuid, n)
    # account mirrors (a list of their own; any two accounts, at least one of them an offline account)
    with_stake = {a.uuid: b["name"] for g in config.get("companies") or [] if isinstance(g, dict) and g.get("participation")
                  for b in [by_id.get(str(g.get("area")))] if b for a in b["leaves"]}
    # the same pair twice counts once (said so); an account Kontor cannot book into in two mirrors: each of its bookings would
    # arrive twice, once in each mirror (one booked into is caught below: booked by two rules)
    pairs_seen, twice, in_mirrors = set(), set(), {}
    for m in [m for m in config.get("account_mirrors") or [] if isinstance(m, dict) and m.get("a") and m.get("b")]:
        ends = frozenset(str(m.get(f) or "").split("|")[0].strip() for f in ("a", "b"))
        if ends in pairs_seen and len(ends) == 2 and ends not in twice:          # said once per pair
            twice.add(ends)
            add("warning", tr("s_spiegel_doppelt") % (tr("s_regel_gegenkonto") % _acct_name(ledger, m["a"])))
        pairs_seen.add(ends)
    for i, m in enumerate(rules.mirrors(config)):          # only mirrors that book: the other side an offline account, no group, one currency
        try:
            a, q = ledger.resolve(m["a"]), ledger.resolve(m["b"])
        except KeyError:
            continue
        if a.uuid == q.uuid or a.group or q.group or (a.currency or "EUR").upper() != (q.currency or "EUR").upper():
            continue
        for x, y in ((a, q), (q, a)):
            if not ledger.writable(x.uuid, config) and ledger.writable(y.uuid, config):
                in_mirrors.setdefault(x.uuid, (x, set()))[1].add(i)
    for x, ix in in_mirrors.values():
        if len(ix) > 1:
            add("error", tr("s_spiegel_mehrfach") % (x.name, len(ix)))
    for i, m in enumerate(rules.mirrors(config)):
        label = tr("s_regel_gegenkonto") % str(i + 1)
        a = ref(label, m["a"], group_ok=False)
        q = ref(label, m["b"], group_ok=False)
        n = tr("s_regel_gegenkonto") % (a.name if a is not None else str(i + 1))
        rs = parse_start(m.get("from_date")) if m.get("from_date") else ""
        if rs is None or (rs not in ("", "all") and rs > date.today()):
            add("error", tr("s_s_rueckwirkend_ungueltig") % (n, m["from_date"]))
        if a is None or q is None:
            continue
        if a.uuid == q.uuid:
            add("error", tr("s_s_spiegel_selbst") % n)
            continue
        if (a.currency or "EUR").upper() != (q.currency or "EUR").upper():
            add("warning", tr("s_s_spiegel_waehrung") % n)
        if not (ledger.writable(a.uuid, config) or ledger.writable(q.uuid, config)):
            add("warning", tr("s_s_spiegel_kein_offline") % (n, a.name, q.name))
        # also booked by another rule (a participation, another mirror): every side Kontor books into
        for x in (x for x in (a, q) if ledger.writable(x.uuid, config)):
            if x.uuid in used:
                add("error", tr("s_konto_s_mehrfach_ziel") % (x.path, used[x.uuid], n))
            used.setdefault(x.uuid, n)
        for x in (a, q):
            if x.uuid in with_stake and roles.get(x.uuid) in rules.VALUE_OFF:
                add("warning", tr("s_s_doppelt_gezaehlt") % (with_stake[x.uuid], x.name))
    for r in bil.get("illiquid_accounts") or []:
        setting(tr("s_chk_bilanz_illiquide"), r)
    for k, v in (bil.get("roles") or {}).items():
        if not k.startswith("_"):
            setting(tr("s_position_fuer"), k)
            if v not in ROLES:
                add("error", tr("s_unbekannte_position_s_fuer_s") % (v, k))
    for k, v in (bil.get("history_source") or {}).items():
        setting(tr("s_verlauf_fuer"), k, group_ok=False)
        if v not in ("transactions", "balances"):
            add("error", tr("s_unbekannte_verlaufsquelle_s_fuer_s") % (v, k))
    for k in (bil.get("hidden_accounts") or []) + (bil.get("always_show") or []):
        setting(tr("s_chk_bilanz_anzeige"), k)
    for im in config.get("real_estate") or []:
        n = im.get("name") or "?"
        if im.get("property_account"):
            ref("Immobilie %s: Objektkonto" % n, im["property_account"], group_ok=False)
        for ln, r in (im.get("loan_accounts") or {}).items():
            if r:
                ref("Immobilie %s: Darlehen %s" % (n, ln), r, group_ok=False)
        if im.get("area") and not any(b["id"] == im["area"] for b in bereiche):
            add("warning", tr("s_immobilie_s_bereich_s_existiert") % (n, im["area"]))
        if im.get("category"):
            cat("Immobilie %s" % n, str(im["category"]).split("\\")[-1])
    kfc = config.get("cashflow", {}) or {}
    for k, v in (kfc.get("positions") or {}).items():      # a category gone in MoneyMoney: its entry is ignored (no finding)
        if v not in POS and v != "transfer":
            add("error", tr("s_kapitalfluss_zuordnung_s_s_unbekannt") % (k, v))
    for k, v in (kfc.get("category_to_account") or {}).items():
        if not k.startswith("_"):
            ref(tr("s_kapitalfluss_depot_fuer_s") % k, v, group_ok=False)
    # the account per recipient: gone, or no longer in that area -- Kontor's choice applies again (a note only)
    area_accs = {str(b["id"]): {a.uuid for a in b["leaves"]} for b in bereiche_for(ledger, config)} if ledger is not None else {}
    for area, m in (kfc.get("recipient_to_account") or {}).items():
        for k, v in (m or {}).items():
            if v == "external" or ledger is None:
                continue
            try:
                a = ledger.resolve(v)
            except KeyError as e:
                add("warning", "%s: %s" % (tr("s_kapitalfluss_ziel_fuer_s") % k, e)); continue
            if area not in area_accs or a.uuid not in area_accs[area]:
                add("warning", tr("s_kapitalfluss_ziel_bereich") % (tr("s_kapitalfluss_ziel_fuer_s") % k, a.name))
    st = config.get("tax", {}) or {}
    for k, v in (st.get("property_loans") or {}).items():
        ref(tr("s_steuer_darlehen_fuer_objekt_s") % v, k)
    bel = config.get("receipts", {}) or {}
    folder = os.path.expanduser(bel.get("folder") or DEFAULT_CONFIG["receipts"]["folder"])
    if os.path.isdir(folder) and not os.access(folder, os.W_OK):
        add("error", tr("s_belegordner_nicht_beschreibbar_s") % folder)
    for h in ledger.hints:
        add("hint", h)
    return out


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def not_booked_entry(row: dict, key: str) -> dict:
    """An entry of "Don't book" (config nicht_buchen): the booking as it was shown, so the list can name it."""
    def num(v):
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return None
    out = {"key": key, "date": str(row.get("date") or "")[:10], "amount": num(row.get("amount")),
           "account": str(row.get("account_name") or row.get("account") or "")[:120], "kind": str(row.get("kind") or "")[:20],
           "text": rules.TAG_RE.sub("", str(row.get("text") or row.get("purpose") or "")).strip(" ·")[:200],
           "rule": str(row.get("rule") or "")[:120], "since": datetime.now().strftime("%Y-%m-%d %H:%M")}
    return {k: v for k, v in out.items() if v is not None}


def _plan_round(ledger: Ledger, config: dict, today: date, seen: "rules.Seen", hold: Optional[set] = None,
                edits: Optional[Dict[str, dict]] = None, auto: bool = False) -> "rules.RuleResult":
    """The rules once: hold = left out of this run (planned as not booked: what follows makes up for it, a loan's interest
    after it waits too), edits = your changes from the approval (planned as changed), auto = only what booking fully
    automatically books (what is new since the last check)."""
    return plan_all(ledger, config, today, set(hold or ()), edits, seen, auto)


def proposal_rows(ledger: Ledger, proposals: List[Proposal]) -> List[dict]:
    """Bookings waiting for approval, as the interface shows them."""
    return [{"kind": x.kind, "account": x.account_path, "account_name": ledger.accounts[x.account_uuid].name if x.account_uuid in ledger.accounts else "",
             "account_id": x.account_uuid, "key": x.key, "date": x.booking_date.isoformat(), "amount": x.amount, "text": x.purpose,
             "category": x.category, "tag": x.tag, "rule": x.rule, "retroactive": x.retro, "counterparty": x.payee, "note": x.note, "pair": x.pair}
            for x in proposals]


def plan_pending(ledger: Ledger, config: dict, state: dict, today: date, hold: Optional[set] = None,
                 edits: Optional[Dict[str, dict]] = None) -> List[dict]:
    """The approval list with your selection: what you leave out or change, and everything planned after it, recalculated
    (nothing is written)."""
    lg = ledger.fork()
    seen = rules.Seen.from_state(state.get("seen"), lg, today)
    return proposal_rows(lg, _plan_round(lg, config, today, seen, hold, edits).proposals)


def apply_proposals(bridge: Bridge, ledger: Ledger, proposals: List[Proposal], made: Optional[List[Proposal]] = None,
                    config: Optional[dict] = None, progress: Optional[Callable[[str, int, int], None]] = None,
                    categories: Optional[List[dict]] = None, notes: Optional[List[str]] = None) -> int:
    """Writes the proposals: only new bookings (nothing existing is ever changed or deleted), only into offline accounts
    (Ledger.writable, checked again here for each one), each with Kontor's mark in its purpose and never one whose mark is
    in that account already. A category is passed only if MoneyMoney has it (categories: its list) -- otherwise the booking
    goes without one, so MoneyMoney's category tree is never touched. The bookings written go into made.
    progress("buchen", n, of) before each one."""
    done = 0
    present = rules.present_marks(ledger)                 # in MoneyMoney already (the last read)
    cats = {str(c.get(f) or "") for c in categories or [] if isinstance(c, dict) for f in ("name", "path", "uuid")}
    cats |= {str(c.get("path") or "").split("\\")[-1] for c in categories or [] if isinstance(c, dict)}
    unknown: set = set()
    for pr in proposals:
        if progress:
            progress("buchen", done, len(proposals))
        acc = ledger.accounts.get(pr.account_uuid)
        if acc is None or acc.group or not ledger.writable(pr.account_uuid, config):
            raise MoneyMoneyError(tr("s_verweigert_s_ist_kein_manuell") % (acc.path if acc is not None else pr.account_path))
        amount = round(float(pr.amount), 2)
        if not pr.tag or pr.tag not in (pr.purpose or "") or not rules.TAG_RE.fullmatch(pr.tag):
            raise MoneyMoneyError(tr("s_verweigert_ohne_markierung") % acc.name)       # without its mark it could be made twice
        if amount != amount or abs(amount) > 1e10:
            raise MoneyMoneyError(tr("s_verweigert_betrag") % acc.name)
        if abs(amount) < 0.005 or (acc.uuid, pr.tag) in present:      # nothing to book, or there already (never twice)
            log.warning("Booking skipped: %s (%s)", "no amount" if abs(amount) < 0.005 else "its mark is in the account already", pr.kind)
            continue
        cat = pr.category or None
        if cat and cat not in cats and cat.split("\\")[-1] not in cats:
            unknown.add(cat)
            cat = None
        bridge.add_transaction(acc.uuid, pr.booking_date, pr.payee, amount, pr.purpose, cat)
        present.add((acc.uuid, pr.tag))
        if made is not None and not bridge.dry_run:
            made.append(pr)
        done += 1
        log.info("%s: %s booking", "BOOKED" if not bridge.dry_run else "DRY RUN", pr.kind)      # no amounts, payees or purposes in the log
    if unknown and notes is not None:
        notes.append(tr("s_kategorie_fehlt_ohne_gebucht") % ", ".join(sorted(unknown)))
    return done


def budgets_from_categories(categories: List[dict]) -> Dict[str, float]:
    """Kategorie-Budgets aus MoneyMoney als Monatsbetrag je Pfad ('A / B')."""
    out: Dict[str, float] = {}
    for c in categories or []:
        b = c.get("budget")
        if not isinstance(b, dict) or not b.get("amount"):
            continue
        try:
            amt = float(b.get("amount") or 0.0)
        except (TypeError, ValueError):
            continue
        period = str(b.get("period") or "monthly").lower()
        monthly = amt / 12 if period.startswith("year") else amt / 3 if period.startswith("quart") else amt
        path = norm_cat(str(c.get("path") or c.get("name") or ""))
        if path and monthly:
            out[path] = round(monthly, 2)
    return out


def compact_transactions(ledger: Ledger, bereiche: List[dict], store: Optional[Store] = None, banks: Optional[set] = None) -> List[dict]:
    """Umsatzliste fuer Belege und Suche (ohne Gegen-IBAN). banks: Konten, bei denen eine Kategorie zaehlt ("braucht")."""
    ent_of: Dict[str, str] = {}
    for b in bereiche:
        for a in b["leaves"]:
            ent_of.setdefault(a.uuid, b["id"])
    out = []
    kat = categorize.load(store) if store is not None else categorize.empty()
    skip = categorize.transfers(ledger, ent_of)
    own = ledger.own_ibans()
    for t in ledger.txs:
        if t.account_uuid not in ent_of:
            continue
        path, q = categorize.effective(kat, t)
        row = {"id": t.id, "account": t.account_uuid, "account_name": ledger.accounts[t.account_uuid].name, "entity": ent_of[t.account_uuid],
               "date": t.booking_date.isoformat(), "amount": t.amount, "name": t.name[:80], "purpose": t.purpose[:140],
               "category": path, "source": q, "booked_count": t.booked, "checkmark": t.checkmark,
               "needs": categorize.needs_category(t, banks)}
        if t.id in skip:
            row["transfer"] = True                    # between your accounts: counts as a transfer, no category needed
        else:
            p = own.get(t.counter_iban) if t.counter_iban else None
            if p is not None and ent_of.get(p) is not None and ent_of.get(p) != ent_of[t.account_uuid]:
                row["other_area"] = True           # to or from another of your areas (without a category: a contribution or withdrawal)
        out.append(row)
    out.sort(key=lambda x: (x["date"], x["id"]), reverse=True)
    return out


def record_holdings(state: dict, portfolios: Dict[str, list], today: date) -> None:
    """Month-end values of the securities of each portfolio as Kontor sees them (overwritten during the month, like the
    portfolio values), for the breakdown of a portfolio in months the MoneyMoney history does not cover."""
    if not portfolios:
        return
    mk = month_key(today)
    snaps, names = state.setdefault("snapshots_sec", {}), state.setdefault("sec_names", {})
    for uuid, rows in portfolios.items():
        vals: Dict[str, float] = {}
        for p in rows or []:
            try:
                key = holding_key(str(p.get("name") or ""), str(p.get("isin") or ""))
                vals[key] = round(vals.get(key, 0.0) + float(p.get("marketValue") or p.get("amount") or 0), 2)
                names[key] = str(p.get("name") or "") or names.get(key, "")
            except (TypeError, ValueError, AttributeError):
                continue
        if vals:
            snaps.setdefault(mk, {})[uuid] = vals


def portfolio_summary(ledger: Ledger, bereiche: List[dict]) -> List[dict]:
    out = []
    ent_of = {a.uuid: b["name"] for b in bereiche for a in b["leaves"]}
    for uuid, rows in (getattr(ledger, "portfolios", {}) or {}).items():
        acc = ledger.accounts.get(uuid)
        if acc is None:
            continue
        pos = []
        for p in rows:
            try:
                pos.append({"name": str(p.get("name") or ""), "isin": str(p.get("isin") or ""), "quantity": float(p.get("quantity") or 0),
                            "price": float(p.get("marketPrice") or p.get("price") or 0), "value": float(p.get("marketValue") or p.get("amount") or 0),
                            "cost_basis": float(p.get("purchaseValue") or 0), "currency": str(p.get("currency") or acc.currency),
                            "asset_class": str(p.get("assetClass") or "")})
            except (TypeError, ValueError, AttributeError):
                continue
        pos.sort(key=lambda x: -x["value"])
        out.append({"account": uuid, "name": acc.name, "entity": ent_of.get(uuid, ""), "sum": round(sum(p["value"] for p in pos), 2),
                    "cost_basis": round(sum(p["cost_basis"] for p in pos), 2), "positions": pos})
    return out


# ---------------------------------------------------------------------------
# Immobilien
# ---------------------------------------------------------------------------

def immo_active(im: dict) -> Optional[dict]:
    kalks = im.get("calcs") or []
    if not kalks:
        return None
    return next((k for k in kalks if k.get("active")), kalks[0])


def immo_results(config: dict, today: date) -> Dict[str, dict]:
    """id -> Ergebnis der aktiven Kalkulation je Immobilie (fuer Datensatz und Planung)."""
    out: Dict[str, dict] = {}
    for im in config.get("real_estate") or []:
        k = immo_active(im)
        if not k:
            continue
        try:
            res = realestate.berechne(k.get("inputs") or {}, today)
        except Exception as e:  # pragma: no cover - fehlerhafte Eingaben duerfen den Bericht nicht stoppen
            log.warning("Property %s: calculation failed (%s)", im.get("id"), type(e).__name__)
            out[str(im.get("id"))] = {"error": str(e)}
            continue
        out[str(im.get("id"))] = {"calc": k.get("id"), "name": k.get("name"), "figures": res["figures"], "years": res["years"],
                                  "hints": res["hints"], "loan_names": res["loan_names"], "start": res["start"],
                                  "series_data": realestate.planreihen(res)}
    return out


def immo_afa_map(config: dict, results: Dict[str, dict]) -> Dict[str, Dict[str, float]]:
    """Objektname (letzter Teil der Vermietungskategorie bzw. Name) -> {Jahr: AfA} aus den aktiven Kalkulationen."""
    out: Dict[str, Dict[str, float]] = {}
    for im in config.get("real_estate") or []:
        r = results.get(str(im.get("id")))
        if not r or "error" in r:
            continue
        obj = (norm_cat(im.get("category") or "").split(" / ")[-1] if im.get("category") else "") or str(im.get("name") or "")
        out[obj] = {str(j["year"]): j["depreciation"] for j in r["years"]}
    return out


def immo_for_plan(config: dict, bereich_id: str, results: Dict[str, dict]) -> List[dict]:
    """Kalkulationen eines Bereichs, die in die Planung uebernommen werden sollen."""
    out = []
    for im in config.get("real_estate") or []:
        if str(im.get("area") or "") != str(bereich_id) or not im.get("in_planning"):
            continue
        r = results.get(str(im.get("id")))
        if not r or "error" in r:
            continue
        out.append({"name": im.get("name"), "category": im.get("category") or "", "property_account": im.get("property_account"),
                    "loan_accounts": im.get("loan_accounts") or {}, "series_data": r["series_data"]})
    return out


def immo_soll_ist(ledger: Ledger, config: dict, im: dict, res: dict, roles: Dict[str, str], today: date) -> List[dict]:
    """Jahresvergleich Kalkulation (Soll) gegen MoneyMoney (Ist): Miete, Kosten, Zinsen, Restschuld."""
    cat = norm_cat(im.get("category") or "").lower()
    loans: Dict[str, str] = {}
    for ln, ref in (im.get("loan_accounts") or {}).items():
        try:
            loans[ln] = ledger.resolve(ref).uuid
        except KeyError:
            pass
    years = sorted({j["year"] for j in res.get("years", [])} & {t.booking_date.year for t in ledger.txs})
    out = []
    cost_words = [w.lower() for w in COST_WORDS]
    for y in years:
        soll = next(j for j in res["years"] if j["year"] == y)
        miete = kosten = 0.0
        if cat:
            for t in ledger.txs:
                if not t.booked or t.booking_date.year != y:
                    continue
                cl = norm_cat(t.category_path).lower()
                if cl == cat or cl.startswith(cat + " / "):
                    if t.amount > 0:
                        miete += t.amount
                    else:
                        kosten += t.amount
        zins = 0.0
        rest = 0.0
        for ln, u in loans.items():
            for t in ledger.transactions(u):
                if t.booking_date.year == y and any(w in t.text.lower() for w in cost_words):
                    zins += t.amount
            rest += ledger.balance_at(u, date(y, 12, 31)) if y < today.year else ledger.accounts[u].balance
        out.append({"year": y, "rent_target": soll["rent"], "rent_actual": round(miete, 2), "costs_target": soll["costs"] + soll["reserve"],
                    "costs_actual": round(kosten, 2), "interest_target": soll["interest"], "interest_actual": round(zins, 2),
                    "remaining_debt_target": soll["remaining_debt"], "remaining_debt_actual": round(rest, 2) if loans else None})
    return out




def _kat_sig(store: Store, config: dict, categories: Optional[List[dict]]) -> tuple:
    return (store.stamp(categorize.FILE), json.dumps(config.get("categories") or {}, sort_keys=True), len(categories or []))


def prepare_categories(store: Store, ledger: Ledger, config: dict, categories: Optional[List[dict]],
                       progress: Optional[Callable[[float, str], None]] = None) -> dict:
    """Kontor-Kategorien: MoneyMoney-Baum als Vorschlag uebernehmen, Regeln lernen, Luecken fuellen, auf den Ledger legen.
    Unveraendert seit dem letzten Mal (gleicher MoneyMoney-Stand, gleiche Kategorien-Datei)? Dann nichts tun."""
    cached = getattr(ledger, "_kat_cache", None)
    if cached and cached[0] == _kat_sig(store, config, categories):
        return cached[1]
    kat = _prepare_categories(store, ledger, config, categories, progress or (lambda f, t: None))
    ledger._kat_cache = (_kat_sig(store, config, categories), kat)
    return kat


def account_deleted(ledger: Ledger, r) -> bool:
    """A reference "id | name" whose account is gone in MoneyMoney (the id unknown, the name not found either). A name alone
    that is unknown or ambiguous is not that: it stays a finding."""
    head = str(r or "").split("|", 1)[0].strip()
    if not UUID_RE.match(head) or head.lower() in {u.lower() for u in ledger.accounts}:
        return False
    try:
        ledger.resolve(str(r))
        return False
    except KeyError:
        return True


def prune_account_settings(config: dict, ledger: Optional[Ledger]) -> dict:
    """Settings kept per account (position, history, shown/hidden, illiquid) of accounts that no longer exist in MoneyMoney
    are dropped -- nothing you could correct, and they must not stand in the way of saving something else."""
    if ledger is None or not ledger.accounts:
        return config
    cfg = copy.deepcopy(config)
    bil = cfg.get("balance")
    if not isinstance(bil, dict):
        return cfg

    def known(r) -> bool:
        return not account_deleted(ledger, r)
    refs = [k for key in ("roles", "history_source") if isinstance(bil.get(key), dict) for k in bil[key] if not str(k).startswith("_")] \
        + [r for key in ("illiquid_accounts", "hidden_accounts", "always_show") if isinstance(bil.get(key), list) for r in bil[key]]
    lost = len({str(r).split("|")[0].strip() for r in refs if not known(r)})
    if lost > max(3, len({str(r).split("|")[0].strip() for r in refs}) // 2):     # other accounts altogether (another database open): nothing is dropped
        return config
    for key in ("roles", "history_source"):
        if isinstance(bil.get(key), dict):
            bil[key] = {k: v for k, v in bil[key].items() if str(k).startswith("_") or known(k)}
    for key in ("illiquid_accounts", "hidden_accounts", "always_show"):
        if isinstance(bil.get(key), list):
            bil[key] = [r for r in bil[key] if known(r)]
    return cfg


def positions_overview(ledger: Ledger, config: dict, categories: List[dict], today: date) -> dict:
    """Kategorien -> Cashflow-Positionen: each of MoneyMoney's categories with bookings in your areas (in MoneyMoney's order):
    bookings, sum of the last 12 months, Kontor's proposal, what you chose, the property it belongs to, the account saving goes
    into, transfer category."""
    from report import POSITIONS, category_totals, propose_position, transfer_check
    bereiche = bereiche_for(ledger, config)
    keep = {a.uuid for b in bereiche for a in b["leaves"]}
    firm = {a.uuid for b in bereiche if b.get("kind") == "company" for a in b["leaves"]}
    since = (today.replace(day=28) if today.month == 2 and today.day == 29 else today).replace(year=today.year - 1) + timedelta(days=1)
    count: Counter = Counter()
    in_firm: Counter = Counter()                          # bookings in a company's accounts (its names for the positions)
    year: Dict[str, float] = defaultdict(float)
    for t in ledger.txs:
        p = norm_cat(t.category_path)
        if t.booked and p and p not in categorize.STANDARD and t.account_uuid in keep:
            count[p] += 1
            if t.account_uuid in firm:
                in_firm[p] += 1
            if since <= t.booking_date <= today:
                year[p] += t.amount
    used = set()
    for p in count:
        parts = p.split(" / ")
        used.update(" / ".join(parts[:i]) for i in range(1, len(parts) + 1))
    order = [norm_cat(str(c.get("path") or c.get("name") or "")) for c in categories or [] if not c.get("default")]
    paths = [p for p in dict.fromkeys(order) if p in used] + sorted(used - set(order))
    # the direction of a category counts within each area, as in the cash flow ("Gehalt": income for you, an expense of your
    # company): the proposal of the area with the most bookings first, those of the others after it
    per_area = []
    for b in bereiche:
        accs = {a.uuid for a in b["leaves"]}
        n = Counter(norm_cat(t.category_path) for t in ledger.txs if t.booked and t.category_path and t.account_uuid in accs)
        per_area.append((category_totals(ledger, accs), n))

    def proposals(p: str) -> List[str]:
        if by_name(p):
            return ["transfer"]
        c: Counter = Counter()
        for tot, n in per_area:
            if n.get(p):
                c[propose_position(p, tot.get(p, 0.0) > 0)] += n[p]
        return [k for k, _ in c.most_common()]
    kf = config.get("cashflow") or {}
    names_only = dict(config, cashflow=dict(kf, positions={}))
    by_name = transfer_check(names_only)                 # a transfer category by its name (Kontor's "proposal")
    konto = {norm_cat(k): v for k, v in (kf.get("category_to_account") or {}).items()}
    objekte = {norm_cat(str(im.get("category"))): str(im.get("name") or "") for im in config.get("real_estate") or []
               if isinstance(im, dict) and im.get("category")}
    mine = my_positions(config)
    out = []
    for p in paths:
        sub = [q for q in count if q == p or q.startswith(p + " / ")]
        hits = [c for c in objekte if p == c or p.startswith(c + " / ")]
        obj = objekte[max(hits, key=len)] if hits else None
        also: List[str] = []
        if count.get(p):
            prop, also = (proposals(p) + [""])[0], proposals(p)[1:]
        else:                       # only a folder for others: what they get, if it is the same for all ("" = differs)
            props = {(proposals(q) + [""])[0] for q in sub if count.get(q)}
            prop = props.pop() if len(props) == 1 else ""
        out.append({"path": p, "name": p.split(" / ")[-1], "depth": p.count(" / "), "count": count.get(p, 0),
                    "count_all": sum(count[q] for q in sub), "sum_12m": round(sum(year.get(q, 0.0) for q in sub), 2),
                    "proposal": prop, "proposal_also": also,
                    "own": mine.get(p), "account": konto.get(p) or "", "property_name": obj,
                    "company": 2 * sum(in_firm[q] for q in sub) > sum(count[q] for q in sub)})
    return {"categories": out, "positions": [[k, sec] for k, sec, _ in POSITIONS], "transfer": list(kf.get("transfer_categories") or ["Umbuchung"])}


def save_positions(config: dict, body: dict, ledger: Optional[Ledger]) -> dict:
    """The settings with your positions (Kategorien -> Cashflow-Positionen): {pfad: position | "umbuchung" | "" (Kontor's
    proposal)}, the account saving of a category goes into {pfad: account}. Only the categories sent change."""
    cfg = copy.deepcopy(config)
    kf = cfg.setdefault("cashflow", {})
    pos = {norm_cat(k): v for k, v in (kf.get("positions") or {}).items()}
    acc = {norm_cat(k): v for k, v in (kf.get("category_to_account") or {}).items()}
    for k, v in (body.get("positions") or {}).items():
        p = norm_cat(str(k))
        if not p:
            continue
        if v not in POS and v not in ("", None, "transfer"):
            raise ValueError(tr("s_kapitalfluss_zuordnung_s_s_unbekannt") % (p, v))
        pos.pop(p, None)
        if v:
            pos[p] = v
    for k, v in (body.get("accounts") or {}).items():
        p = norm_cat(str(k))
        if not p:
            continue
        acc.pop(p, None)
        if v:
            if ledger is not None:
                ledger.resolve(str(v), groups_ok=False)          # KeyError: unknown account
            acc[p] = str(v)
    kf["positions"], kf["category_to_account"] = pos, acc
    # the account saving goes into, per area and recipient: {area: {recipient: account | "extern" | "" (Kontor's)}}
    emp = {a: dict(m) for a, m in (kf.get("recipient_to_account") or {}).items() if isinstance(m, dict)}
    sent = body.get("recipient", {})
    if not isinstance(sent, dict):
        raise ValueError("recipient")
    for area, m in sent.items():
        if not isinstance(m, dict):
            raise ValueError("recipient")
        mine = emp.setdefault(str(area), {})
        for k, v in m.items():
            if not isinstance(k, str) or not k or len(k) > 120 or not isinstance(v, (str, type(None))):
                raise ValueError("recipient")
            mine.pop(k, None)
            if v:
                if v != "external" and ledger is not None:
                    ledger.resolve(v, groups_ok=False)           # KeyError: unknown account
                mine[k] = v
    kf["recipient_to_account"] = {a: m for a, m in emp.items() if m}
    return cfg


def bank_accounts(roles: Dict[str, str]) -> set:
    """The accounts a category matters for (cash flow, tax): those with the position "liquidity"."""
    return {u for u, r in roles.items() if r == "cash"}


def _prepare_categories(store: Store, ledger: Ledger, config: dict, categories: Optional[List[dict]],
                        step: Callable[[float, str], None]) -> dict:
    """Categories are MoneyMoney's; on top only what you assigned and what waits to be written there. The patterns for the
    suggestions are learned at the full read (daily)."""
    categorize.set_standard(categories)
    kat = categorize.load(store)
    base = categorize.digest(kat)
    changed = False
    if not getattr(ledger, "incremental", False) or not kat.get("learned_at"):
        categorize.learn(kat, ledger, progress=lambda f: step(0.8 * f, tr("s_kategorien_regeln_lernen")))
        changed = True
    step(0.9, tr("s_kategorien_uebernehmen"))
    if changed:
        with categorize.LOCK:
            now = categorize.load(store)
            dnow = categorize.digest(now)
            if dnow != base:
                # changed meanwhile (e.g. a category you assigned while the report was being built): that stays; what was
                # worked out here goes only where nothing changed
                for k, v in kat.items():
                    if not k.startswith("_") and (k not in dnow or dnow[k] == base.get(k)):
                        now[k] = v
                kat = now
            categorize.save(store, kat)
    categorize.apply_to_ledger(kat, ledger)
    return kat


MM_HISTORY_FILE = "mm-history.json"


def record_snapshot(snaps: dict, accounts, today: date) -> bool:
    """Staende fuers Monatsende merken. Depots unter dem Monat ihres letzten Abrufs in MoneyMoney (nicht dem Monat, in dem
    Kontor liest: ein Abruf am 31. landet im richtigen Monat, auch wenn Kontor erst am 2. liest), uebrige Konten unter dem
    laufenden Monat. Liefert True, wenn sich etwas geaendert hat."""
    changed = False
    cur = month_key(today)
    for a in accounts:
        if a.group:
            continue
        mk = cur
        if a.portfolio and a.refresh is not None and a.refresh.year >= 2005 and a.refresh.date() <= today:
            mk = month_key(a.refresh.date())
        row = snaps.setdefault(mk, {})
        if row.get(a.uuid) != a.balance:
            row[a.uuid] = a.balance
            changed = True
    if len(snaps) > 600:
        for k in sorted(snaps)[:-600]:
            snaps.pop(k, None)
    return changed


def merge_snapshots(state: dict, snaps: dict) -> None:
    cur = state.setdefault("snapshots", {})
    for mk, row in (snaps or {}).items():
        cur.setdefault(mk, {}).update(row)


def merge_holdings(state: dict, built: dict) -> None:
    """Kontor's monthly record of the securities (and the names seen in MoneyMoney's export) from a run or a rebuild."""
    cur = state.setdefault("snapshots_sec", {})
    for mk, row in (built.get("snapshots_sec") or {}).items():
        cur.setdefault(mk, {}).update(row)
    if built.get("sec_names"):
        state.setdefault("sec_names", {}).update(built["sec_names"])


def build_report(store: Store, ledger: Ledger, config: dict, state: dict, today: date, warnings: List[str],
                 categories: Optional[List[dict]] = None, progress: Optional[Callable[[float, str], None]] = None) -> dict:
    # Fortschritt grob nach Laufzeit eines Laufs ohne Zwischenergebnisse gewichtet: Kategorien 5-25 %, Bereiche 25-75 % (nach
    # Umsatzzahl), Steuer bis 85 %, Kategorienstatistik und Umsatzliste bis 95 %, Speichern
    step = progress or (lambda f, t: None)
    step(0.05, tr("s_schritt_kategorien"))
    kat = prepare_categories(store, ledger, config, categories, lambda f, t: step(0.05 + 0.2 * f, t))
    if kat.get("_sig_of") is not kat.get("rules"):          # the learned patterns (cash flow estimates; "_..." is not stored)
        kat["_sig"], kat["_sig_of"] = categorize.digest({"rules": kat.get("rules") or []})["rules"], kat.get("rules")
    record_snapshot(state.setdefault("snapshots", {}), ledger.accounts.values(), today)
    record_holdings(state, getattr(ledger, "portfolios", None) or {}, today)
    # aus MoneyMoney uebernommene Kontostand-Verlaeufe (verschluesselt abgelegt, nur im Speicher in den Zustand gelegt)
    mmh = store.load_shared(MM_HISTORY_FILE, {}) or {}
    state["history_mm"], state["history_mm_start"] = mmh.get("accounts") or {}, mmh.get("opening") or {}
    state["history_mm_sec"] = mmh.get("securities") or {}
    bereiche = bereiche_for(ledger, config)
    haupt = main_bereich(bereiche)
    roles = account_roles(ledger, config)
    budgets = budgets_from_categories(categories or [])
    immo_res = immo_results(config, today)
    log.debug("Report: %d areas, %d accounts with position, %d property calculations, %d budgets",       # no names in the log
              len(bereiche), len(roles), len(immo_res), len(budgets))
    ledger._kat_sig = repr(getattr(ledger, "_kat_cache", (None,))[0])      # fuer Zwischenergebnisse in build_dataset
    datasets: Dict[str, dict] = {}
    weights = [1 + sum(len(ledger.transactions(a.uuid)) for a in b["leaves"]) for b in bereiche]
    total_w, done_w = float(sum(weights) or 1), 0.0
    for i, b in enumerate(bereiche):
        lo, hi = 0.25 + 0.5 * done_w / total_w, 0.25 + 0.5 * (done_w + weights[i]) / total_w
        done_w += weights[i]
        step(lo, tr("s_bereich_n") % b["name"])
        sub = (lambda f, t, lo=lo, hi=hi, name=b["name"]: step(lo + (hi - lo) * f, "Bereich %s: %s" % (name, t)))
        try:
            ds = build_dataset(ledger, config, state, today, b, roles, warnings if (haupt and b["id"] == haupt["id"]) else [], sub, kat)
            ds["budgets"] = budgets
            datasets[b["id"]] = ds
        except Exception as e:
            log.exception("Area %s: report failed", str(b["id"])[:8])
            datasets[b["id"]] = {"error": str(e), "root_name": b["name"]}
    try:
        equity_ratio(ledger, config, roles, bereiche, datasets)
    except Exception:  # pragma: no cover
        log.exception("Equity ratio failed")
    neu = konten_neu(ledger, config, bereiche, roles)
    if neu:
        warnings.append(tr("s_s_ohne_bestaetigte_zuordnung_einrichtu")
                        % (tr("s_ein_konto") if len(neu) == 1 else tr("s_d_konten") % len(neu), ", ".join(k["name"] for k in neu[:5]) + (" …" if len(neu) > 5 else "")))
    immobilien = []
    for im in config.get("real_estate") or []:
        r = immo_res.get(str(im.get("id")))
        entry = {"id": im.get("id"), "name": im.get("name"), "area": im.get("area"), "in_planning": bool(im.get("in_planning")),
                 "category": im.get("category"), "property_account": im.get("property_account"), "loan_accounts": im.get("loan_accounts") or {},
                 "calcs": [{"id": k.get("id"), "name": k.get("name"), "active": bool(k.get("active")), "created": k.get("created")} for k in im.get("calcs") or []],
                 "documents": im.get("documents") or [], "notes": im.get("notes") or ""}
        if r and "error" not in r:
            entry.update({"figures": r["figures"], "years": r["years"], "hints": r["hints"], "loan_names": r["loan_names"], "start": r["start"]})
            try:
                entry["target_actual"] = immo_soll_ist(ledger, config, im, r, roles, today)
            except Exception as e:  # pragma: no cover
                entry["target_actual"] = []
                log.warning("Plan vs. actual %s: %s", im.get("id"), type(e).__name__)
        elif r:
            entry["error"] = r["error"]
        immobilien.append(entry)
    for bid, ds in datasets.items():
        if "error" not in ds:
            log.debug("Area %s: %d months (%s to %s), %d accounts, %d inactive, %d warning(s)", str(bid)[:8],
                      len(ds["months"]), ds["months"][0] if ds["months"] else "-", ds["months"][-1] if ds["months"] else "-",
                      sum(1 for r in ds["balance"]["rows"] if not r["group"]), len(ds.get("accounts_inactive") or []), len(ds.get("warnings") or []))
    # bank bookings that are transfers (no category needed): within an area, or paired by the cash flow just built
    area_of = {a.uuid: str(b["id"]) for b in bereiche for a in b["leaves"]}
    if isinstance(getattr(ledger, "_paired", None), dict):
        ledger._paired = {k: v for k, v in ledger._paired.items() if k in {str(b["id"]) for b in bereiche}}     # areas that still exist
    transfer_sig = hash(frozenset(categorize.transfers(ledger, area_of)))
    dataset = {
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "today": today.isoformat(),
        "main_area": haupt["id"] if haupt else None,
        "areas": datasets,
        "area_names": {b["id"]: b["name"] for b in bereiche},
        "area_info": {b["id"]: {"name": b["name"], "kind": b["kind"], "share": b["share"], "main_area": b["main_area"], "accounts": b["accounts"],
                                   "groups": [g.name for g in b["groups"]], "account_count": len(b["leaves"])} for b in bereiche},
        "accounts": account_tree(ledger, config, roles, datasets),
        "tax": (step(0.76, "Steuer"), _cached(ledger, "_tax_cache", (ledger._kat_sig, today.isoformat(), _bereiche_sig(bereiche),
                                                   json.dumps([config.get(k) for k in ("tax", "cashflow", "companies", "areas", "real_estate")]
                                                              + [(config.get("balance") or {}).get(k) for k in ("roles", "accounts_mapping")], sort_keys=True, default=str)),
                          lambda: build_tax(ledger, config, today, bereiche, roles, immo_afa_map(config, immo_res))))[1],
        "depots": portfolio_summary(ledger, bereiche),
        "real_estate": immobilien,
        "budgets": budgets,
        "warnings": warnings,
        "categories": dict((step(0.86, "Kategorienstatistik"), _cached(ledger, "_katstats_cache", (ledger._kat_sig, tuple(sorted(bank_accounts(roles))), transfer_sig, tuple(sorted(assign_skipped(config, bereiche)))),
                                                                                  lambda: categorize.stats(kat, ledger, bank_accounts(roles), area_of, assign_skipped(config, bereiche))))[1],
                           positions=len(my_positions(config))),
        "accounts_new": neu,
    }
    step(0.88, "Speichern")
    # the bookings behind each cash flow row: in a file of their own (large; fetched on a click, not sent with every page)
    ids = {bid: (b.get("cashflow") or {}).pop("cf_ids", {}) for bid, b in (dataset.get("areas") or {}).items() if isinstance(b, dict)}
    store.save("cf-ids.json", ids)
    store.save("dataset.json", dataset)
    sig = (ledger._kat_sig, _bereiche_sig(bereiche), tuple(sorted(bank_accounts(roles))), transfer_sig)
    cached = getattr(ledger, "_ums_cache", None)
    if cached and cached[0] == sig and store.exists("transactions.json"):
        ums = cached[1]                # Umsatzliste unveraendert (z. B. nur Verlauf geaendert) -> nicht neu schreiben
    else:
        step(0.93, "Umsatzliste")
        ums = compact_transactions(ledger, bereiche, store, bank_accounts(roles))
        store.save("transactions.json", ums)
        ledger._ums_cache = (sig, ums)
    dataset["_transactions"] = ums        # fuer den Dienst: Liste im Speicher behalten (teilt die Strings mit dem Ledger), nicht Teil der Datei
    return dataset


def _bereiche_sig(bereiche: List[dict]) -> tuple:
    return tuple((b["id"], tuple(a.uuid for a in b["leaves"])) for b in bereiche)


def _cached(ledger: Ledger, attr: str, key, fn):
    """Ergebnis am Ledger zwischenspeichern (gleicher MoneyMoney-Stand + gleiche Eingaben -> gleiches Ergebnis)."""
    hit = getattr(ledger, attr, None)
    if hit and hit[0] == key:
        return copy.deepcopy(hit[1])
    val = fn()
    setattr(ledger, attr, (key, copy.deepcopy(val)))
    return val


def account_tree(ledger: Ledger, config: dict, roles: Optional[Dict[str, str]] = None, datasets: Optional[Dict[str, dict]] = None) -> List[dict]:
    roles = roles if roles is not None else account_roles(ledger, config)
    inactive: set = set()
    inactive_auto: set = set()
    limits: Dict[str, int] = {}
    verlauf: Dict[str, str] = {}
    bereich_of: Dict[str, str] = {}
    bereich_id: Dict[str, str] = {}
    for bid, ds in (datasets or {}).items():
        inactive.update(ds.get("accounts_inactive") or [])
        inactive_auto.update(ds.get("accounts_inactive_auto") or [])
        limits.update(ds.get("accounts_activity") or {})
        bname = (ds.get("area") or {}).get("name") or ""
        for r in ((ds.get("balance") or {}).get("rows") or []) + ((ds.get("balance") or {}).get("outside") or []):
            if not r.get("group") and r.get("history_source"):
                verlauf[r["id"]] = r["history_source"]
            if not r.get("group") and bname:
                bereich_of[r["id"]] = (bereich_of[r["id"]] + ", " + bname) if r["id"] in bereich_of else bname
                bereich_id.setdefault(r["id"], bid)
    zu = (config.get("balance") or {}).get("accounts_mapping") or {}
    confirmed = set()
    for ref in zu:
        try:
            confirmed.add(ledger.resolve(ref).uuid)
        except KeyError:
            pass
    n_inakt = int((config.get("balance") or {}).get("inactive_months", 12) or 12)
    y, m = add_months(date.today(), -n_inakt)
    cutoff = date(y, m, 1)
    last_tx: Dict[str, date] = {}
    for t in ledger.txs:
        if t.booked and (t.account_uuid not in last_tx or t.booking_date > last_tx[t.account_uuid]):
            last_tx[t.account_uuid] = t.booking_date
    out = []
    kinds = abruf_arten(ledger, config)
    plain = copy.deepcopy(config)                # Vorschlag ohne eigene Zuordnungen (was Kontor heute erkennen wuerde)
    plain.setdefault("balance", {})["roles"] = {}
    plain["balance"]["accounts_mapping"] = {r: dict(z, position="") for r, z in (plain["balance"].get("accounts_mapping") or {}).items() if isinstance(z, dict)}
    suggested = account_roles(ledger, plain)
    for a in ledger.accounts.values():           # Reihenfolge wie in MoneyMoney
        if not a.path:
            continue
        out.append({"uuid": a.uuid, "name": a.name, "path": a.path, "depth": a.path.count(" / "), "group": a.group,
                    "depot": a.portfolio, "manual": ledger.writable(a.uuid, config), "role": roles.get(a.uuid, "") if not a.group else "",
                    "balance_amount": None if a.group else a.balance, "currency": a.currency, "type_name": a.type, "inactive": a.uuid in inactive, "inactive_auto": a.uuid in inactive_auto, "active_limit": limits.get(a.uuid, 0),
                    "role_proposal": suggested.get(a.uuid, "") if not a.group else "", "fetch": kinds.get(a.uuid, {}).get("kind") if not a.group else None,
                    "history_source": verlauf.get(a.uuid) or ("balances" if a.portfolio else "transactions"), "area": bereich_of.get(a.uuid, ""),
                    "area_id": bereich_id.get(a.uuid, ""), "confirmed": a.uuid in confirmed,
                    "updated": a.refresh.strftime("%Y-%m-%d %H:%M") if a.refresh else None,
                    "last_booking": last_tx[a.uuid].isoformat() if a.uuid in last_tx else None,
                    # Saldo, aber weder Buchung noch Aktualisierung seit N Monaten: Stand vermutlich veraltet (Konto aufgeloest?)
                    "stale": (not a.group and (a.portfolio or not a.offline) and abs(a.balance) > 0.005 and (a.uuid not in last_tx or last_tx[a.uuid] < cutoff)
                                 and (a.refresh is None or a.refresh.date() < cutoff))})
    return out


def run_once(store: Store, config: dict, today: date, dry: bool, force: bool,
             bridge_factory: Callable[[bool], Bridge] = Bridge, with_report: bool = True,
             categories: Optional[List[dict]] = None, base: Optional[Ledger] = None, full: bool = True,
             approve: Optional[Dict[str, dict]] = None, report: bool = True, ledger: Optional[Ledger] = None,
             progress: Optional[Callable[[str, int, int], None]] = None) -> dict:
    """approve (a live run from "Approve" under Auto bookings): account|mark -> changes (amount, date, purpose) of the
    bookings you approved; only these are written, the others keep waiting. None: booking fully automatically, what is new
    since the last check (see wanted). What you chose not to book (settings: nicht_buchen) is never proposed.
    report=False: no report here (the service builds it in the background, so the page is up to date at once).
    ledger: a state read already (e.g. only the accounts of the rules, refresh_accounts): not read again, and the mark of the
    last full check stays (the next sync still sees what changed in MoneyMoney).
    progress(step, n, of): "lesen", "regeln", "buchen" (n of the bookings) -- shown while the run is going."""
    step = progress or (lambda *_a: None)
    if not RUN_LOCK.acquire(blocking=False):
        return {"status": "already_running", "text": tr("s_ein_abgleich_laeuft_bereits")}
    try:
        state = store.load("state.json", {}) or {}
        bridge = bridge_factory(dry)
        t_start = time.time()
        prefetched = ledger is not None
        try:
            if categories is None and prefetched:
                categories = state.get("categories_raw") or []
            elif categories is None:
                try:
                    categories = mm_categories.with_paths(bridge.export_categories())
                except MoneyMoneyError:
                    categories = state.get("categories_raw") or []
            if not prefetched:
                step("read", 0, 0)
                # a category added, deleted, renamed or moved in MoneyMoney: older transactions may carry another one now
                if not full and state.get("categories_raw") and category_tree(categories) != category_tree(mm_categories.with_paths(state["categories_raw"])):
                    log.info("Categories changed in MoneyMoney -- reading all transactions")
                    full = True
                ledger = fetch(bridge, config, today, with_portfolio=with_report, base=base, full=full)
        except MoneyMoneyError as e:
            txt = unavailable_text(e)
            if txt:
                log.info("MoneyMoney not available: %s", txt)
                return {"status": "unavailable", "text": txt}
            log.error("MoneyMoney error: %s", e)
            return {"status": "error", "text": tr("s_moneymoney_fehler_s") % e}
        # a new version builds the report again (new figures, e.g. after an update); the rules run again when their basis
        # changed: their settings (your "Don't book" among them) and the day (interest at month end, values)
        basis = json.dumps([[config.get(k) for k in ("loans", "companies", "account_mirrors", "areas", "fetch", "dry_run", "balance", "not_book")],
                            today.isoformat()], sort_keys=True, default=str)
        fp = "%s@%s#%s" % (ledger_fp(ledger), version(), hashlib.sha256(basis.encode()).hexdigest()[:16])
        if fp == state.get("fingerprint") and not force:
            log.info("No change in MoneyMoney since the last run.")
            return {"status": "unchanged", "text": tr("s_keine_aenderung_in_moneymoney_seit"), "_ledger": ledger,
                    "_categories": categories}

        # when Kontor first saw each account: one new in MoneyMoney shows at once (before its first transaction); the first
        # time all known accounts count as long known
        seen_before = state.get("accounts_since")
        known = dict(seen_before) if isinstance(seen_before, dict) else {}
        for u, a in ledger.accounts.items():
            if not a.group and u not in known:
                known[u] = today.isoformat() if isinstance(seen_before, dict) else "old"      # "alt": known before
        known_new = {u: v for u, v in known.items() if u not in (seen_before or {})}
        state["accounts_since"] = known                # for the report of this run
        step("rules", 0, 0)
        # up to where Kontor had looked when it last booked on its own: what arose after that is new (Seen)
        seen = rules.Seen.from_state(state.get("seen"), ledger, today)
        new_seen = None if isinstance(state.get("seen"), dict) and state["seen"].get("tag") else seen.dump()
        top = rules.Seen.top_id(ledger)
        t_read = time.time()
        approving = not dry and approve is not None
        automatic = not dry and approve is None
        edits = {k: v for k, v in approve.items() if isinstance(v, dict)} if approving else None
        hold: set = set()

        def wanted(p: Proposal) -> bool:
            """Booked in this run: what you approved; booking fully automatically what is new since the last check -- what is
            backdated or missing again (deleted in MoneyMoney) waits for you, and a loan's interest after it too."""
            return p.key in approve if approving else not p.retro and not p.note
        failed = False
        moved: List[str] = []
        try:
            result = _plan_round(ledger, config, today, seen, hold, edits, automatic)
            if not dry:
                # what is left out is not booked, and what comes after it is planned without it (the next value adjustment of
                # that account takes up the difference) -- again until nothing depends on it (booking fully automatically the
                # rules plan only what is new in the first place)
                for _ in range(8):
                    extra = {p.key for p in result.proposals if not wanted(p)} - hold
                    if not extra:
                        break
                    hold |= extra
                    ledger = ledger.without_planned()
                    result = _plan_round(ledger, config, today, seen, hold, edits, automatic)
                # planned and booked must be the same: what does not settle is not written this time
                moved = [p.key for p in result.proposals if not wanted(p)]
            # booked is exactly what you saw: if an amount is different now (MoneyMoney changed meanwhile), nothing is written
            if approving:
                now = {p.key: p for p in result.proposals}
                for k, ch in approve.items():
                    shown = ch.get("shown") if isinstance(ch, dict) else None
                    if shown is not None and (k not in now or abs(now[k].amount - float(shown)) >= 0.005):
                        moved.append(k)
            if moved:
                log.info("%d planned booking(s) not settled or changed since shown, nothing written", len(moved))
                ledger = ledger.without_planned()
                result = _plan_round(ledger, config, today, seen)
                result.warnings.insert(0, tr("s_betraege_geaendert"))
        except Exception as e:      # the rules met something unexpected: nothing is booked, everything else goes on
            where = traceback.extract_tb(e.__traceback__)[-1]
            log.error("Booking rules failed (%s at %s:%d) -- nothing booked", type(e).__name__, os.path.basename(where.filename), where.lineno)
            failed, hold, moved = True, set(), []
            ledger = ledger.without_planned()
            result = rules.RuleResult()
            result.warnings.append(tr("s_regeln_fehler") % type(e).__name__)
        t_rules = time.time()
        result.info.extend(ledger.hints)            # an account renamed in MoneyMoney: found by its number, nothing to do
        # the log (plain text) holds no amounts, payees, purposes or account names: the details are in the encrypted state and
        # shown in the interface; here only how many
        kinds = Counter(p.kind for p in result.proposals)
        log.info("Rules: %d note(s), %d warning(s), %d proposal(s)%s", len(result.info), len(result.warnings), len(result.proposals),
                 " (%s)" % ", ".join("%s %d" % kv for kv in sorted(kinds.items())) if kinds else "")
        bookings = list(result.proposals)

        written, err = 0, None
        made: List[Proposal] = []
        chosen = [] if dry or moved or failed else [p for p in result.proposals if wanted(p)]
        expect = {u: ledger.accounts[u].balance for u in {x.account_uuid for x in bookings}}      # balances after writing
        if chosen:
            try:
                written = apply_proposals(bridge, ledger, chosen, made, config, progress, categories, result.warnings)
            except MoneyMoneyError as e:
                err = e
                log.error("Writing aborted after %d booking(s): %s", written, e)
            try:
                after = accounts_from_export(bridge.export_accounts())
                for u in {x.account_uuid for x in chosen}:
                    if u in after and abs(after[u].balance - expect[u]) > 0.01:
                        msg = tr("s_saldo_s_nach_buchung_s") % (ledger.accounts[u].name, fmt_eur(after[u].balance), fmt_eur(expect[u]))
                        log.warning("Balance check after booking failed for account %s", u[:8]); result.warnings.append(msg)
            except MoneyMoneyError as e:
                log.warning("Verification after writing not possible: %s", e)
            # Bookings written now may be dated far back (e.g. interest since January): the quick read does not see them, so
            # the ledger keeps them (Ledger.without_planned(keep)) until the next full read -- no full read needed for them
        made_keys = {p.key for p in made}
        # waiting for approval after this run: everything of a dry run; after booking a part, the rules again on the state after
        # writing (what was left out comes back with the amount it needs now); what could not be written
        if dry or moved:
            left = bookings
        elif err is not None:
            left = [x for x in bookings if x.key not in made_keys]
        elif not failed:                    # what is left out (booking fully automatically: what is older) still waits
            left = list(_plan_round(ledger.fork(), config, today, seen).proposals)
        else:
            left = []
        waiting = left if dry or moved or err is None else []
        if not dry and not approving and err is None and not failed and not moved and not prefetched:
            new_seen = rules.Seen(top, today).dump()        # booked on its own what was new: from here on the next is new

        warnings = list(result.warnings)
        if dry and bookings:
            warnings.insert(0, tr("s_probelauf_d_vorgeschlagene_buchung_en") % len(bookings))
        ums = None
        t_write = time.time()
        if with_report and report:
            with REPORT_LOCK:
                ums = build_report(store, ledger, config, state, today, warnings, categories).pop("_transactions", None)
        if with_report:
            state["categories_raw"] = categories or []
        log.info("Run times: read %.1f s (%s), rules %.1f s, write %.1f s, report %.1f s", t_read - t_start,
                 "quick" if getattr(ledger, "incremental", False) else "full", t_rules - t_read, t_write - t_rules, time.time() - t_write)

        # shown: what waits for approval, otherwise what was just booked
        summary = {"status": "error" if err else "ok", "time": datetime.now().strftime("%Y-%m-%d %H:%M"), "dry_run": dry or bool(waiting) or bool(moved),
                   "proposals": proposal_rows(ledger, waiting or bookings),
                   "written": written, "booked_count": len(made), "warnings": result.warnings, "hints": result.info,
                   "error": str(err) if err else None}

        def _merge(cur: dict) -> None:
            if known_new:
                cur["accounts_since"] = dict(known_new, **(cur.get("accounts_since") or {}))
            if new_seen:
                cur["seen"] = new_seen
            if not prefetched:
                cur["fingerprint"] = fp if err is None and not failed else None        # after an error: again at the next sync
            cur["last_run"] = summary
            if not prefetched:                  # "Refresh" (only the accounts of the rules) is no check of its own
                cur.setdefault("history_source", []).append({"time": summary["time"], "dry_run": dry, "written": written,
                                                      "proposals": len(bookings), "error": summary["error"]})
            cur["history_source"] = [{k: v for k, v in x.items() if k != "bookings"} for x in (cur.get("history_source") or [])[-100:]]     # at most 100
            if state.get("snapshots"):
                merge_snapshots(cur, state["snapshots"])     # Schnellabgleich waehrend des Laufs bleibt erhalten
            merge_holdings(cur, state)
            if state.get("categories_raw"):
                cur["categories_raw"] = state["categories_raw"]
        store.update("state.json", _merge, {})      # Verlauf-Eingaben waehrend des Laufs bleiben erhalten

        return dict(summary, _ledger=ledger, _categories=categories, _transactions=ums, _booked=[p.key for p in made])
    finally:
        RUN_LOCK.release()


# ---------------------------------------------------------------------------
# Einstellungspakete
# ---------------------------------------------------------------------------

def _walk_refs(cfg: dict, fn: Callable[[str, str], str]) -> None:
    """Alle Kontoreferenzen der Konfiguration durch fn(feld, ref) ersetzen (in place)."""
    for section, field in REF_FIELDS:
        for item in cfg.get(section, []) or []:
            v = item.get(field)
            if isinstance(v, list):
                item[field] = [fn(section + "." + field, x) for x in v]
            elif isinstance(v, str) and v:
                item[field] = fn(section + "." + field, v)
    for b in cfg.get("areas") or []:
        if isinstance(b, dict):
            b["accounts"] = [fn("areas.accounts", x) for x in (b.get("accounts") or [])]
    bil = cfg.setdefault("balance", {})
    bil["illiquid_accounts"] = [fn("balance.illiquid_accounts", x) for x in (bil.get("illiquid_accounts") or [])]
    for key in ("hidden_accounts", "always_show"):
        if bil.get(key):
            bil[key] = [fn("balance." + key, x) for x in bil[key]]
    for key in ("roles", "history_source", "accounts_mapping"):
        if bil.get(key):
            bil[key] = {(fn("balance." + key, k) if not k.startswith("_") else k): v for k, v in bil[key].items()}
    for im in cfg.get("real_estate") or []:
        if im.get("property_account"):
            im["property_account"] = fn("real_estate.property_account", im["property_account"])
        if im.get("loan_accounts"):
            im["loan_accounts"] = {k: (fn("real_estate.loan_accounts", v) if v else v) for k, v in im["loan_accounts"].items()}
    for m in cfg.get("account_mirrors") or []:
        for f in ("a", "b"):
            if isinstance(m, dict) and m.get(f):
                m[f] = fn("account_mirrors." + f, m[f])
    kf = cfg.setdefault("cashflow", {})
    if kf.get("category_to_account"):
        kf["category_to_account"] = {k: (fn("cashflow.category_to_account", v) if not k.startswith("_") else v)
                                    for k, v in kf["category_to_account"].items()}
    st = cfg.setdefault("tax", {})
    if st.get("property_loans"):
        st["property_loans"] = {(fn("tax.property_loans", k) if not k.startswith("_") else k): v for k, v in st["property_loans"].items()}
    ents = []
    for e in st.get("entities") or []:
        if isinstance(e, dict):
            e = dict(e); e["group"] = fn("tax.entities", e.get("group", "")); ents.append(e)
        else:
            ents.append(fn("tax.entities", e))
    st["entities"] = ents


def export_package(config: dict, name: str = "Kontor-Einstellungen", strip_uuids: bool = False,
                   plan: Optional[dict] = None, ledger: Optional[Ledger] = None) -> dict:
    """Einstellungen als weitergebbares Paket. strip_uuids: Kontoreferenzen als Pfad (wenn ein Ledger
    vorliegt) bzw. Name statt UUID -- fuer eine andere MoneyMoney-Installation."""
    cfg = copy.deepcopy(merged_config(config))
    cfg.pop("ui", None)
    cfg.pop("updates", None)
    cfg.pop("not_book", None)                 # decisions about bookings in your MoneyMoney: they stay here
    (cfg.get("cashflow") or {}).pop("recipient_to_account", None)       # so do your recipients (their IBANs)
    (cfg.get("receipts") or {}).pop("folder", None)
    ids = {str(b.get("id")) for b in cfg.get("areas") or [] if isinstance(b, dict)}
    if ids:                                   # rules of companies whose area no longer exists do not travel along
        cfg["companies"] = [g for g in cfg.get("companies") or [] if isinstance(g, dict) and str(g.get("area")) in ids]
    if strip_uuids:
        def strip(field: str, r: str) -> str:
            if "|" not in r:
                return r
            uuid, label = (x.strip() for x in r.split("|", 1))
            if ledger is not None and uuid in ledger.accounts:
                return ledger.accounts[uuid].path
            return label
        _walk_refs(cfg, strip)
    pkg = {"kontor_package": 1, "name": name, "version": version(), "created": datetime.now().strftime("%Y-%m-%d"), "config": cfg}
    if plan:
        pkg["plan"] = plan
    return pkg


FILE_FORMAT_SINCE = (3, 15, 0)        # packages and backups: settings named as from this version on


def check_file_version(d: dict) -> None:
    """A package or backup written by a Kontor before 3.15.0 names its settings differently: refused, so nothing is replaced by
    defaults. A file without a version (a configuration written by hand) counts as current."""
    v = d.get("version") if isinstance(d, dict) else None
    if not v:
        return
    try:
        old = tuple(int(x) for x in str(v).split(".")[:3]) < FILE_FORMAT_SINCE
    except ValueError:
        old = True
    if old:
        raise ValueError(tr("s_datei_zu_alt", str(v)))


def import_package(current: dict, pkg: dict, ledger: Optional[Ledger], mode: str = "merge",
                   mapping: Optional[Dict[str, str]] = None) -> Tuple[dict, List[dict], List[str]]:
    """Paket in die Konfiguration uebernehmen. Liefert (config, unaufgeloeste Referenzen, Bericht)."""
    if not isinstance(pkg, dict) or not isinstance(pkg.get("config"), dict):
        raise ValueError(tr("s_keine_einstellungsdatei"))
    check_file_version(pkg)
    inc = copy.deepcopy(pkg["config"])
    for k in ("ui", "updates", "not_book"):
        inc.pop(k, None)
    if isinstance(inc.get("cashflow"), dict):
        inc["cashflow"].pop("recipient_to_account", None)
    mapping = mapping or {}
    unresolved: List[dict] = []
    report: List[str] = []

    def resolve(field: str, ref: str) -> str:
        if not ref:
            return ref
        if ref in mapping and mapping[ref]:
            return mapping[ref]
        if ledger is None:
            return ref
        try:
            a = ledger.resolve(ref)
            return "%s | %s" % (a.uuid, a.name)
        except KeyError:
            label = ref.split("|", 1)[1].strip() if "|" in ref else ref
            if not any(u["ref"] == ref for u in unresolved):
                unresolved.append({"ref": ref, "label": label, "field": field})
            return ref

    _walk_refs(inc, resolve)
    base = copy.deepcopy(merged_config(current))
    if mode == "replace":
        keep = copy.deepcopy((base.get("cashflow") or {}).get("recipient_to_account") or {})
        for k, v in inc.items():
            base[k] = v
            report.append("%s ersetzt" % k)
        if keep and isinstance(base.get("cashflow"), dict):      # a package never carries your recipients: they stay
            base["cashflow"]["recipient_to_account"] = keep
    else:
        for k, v in inc.items():
            if k == "account_mirrors":                   # pair by pair, whichever way round
                pair = lambda m: frozenset(str(m.get(f) or "").split("|")[0].strip() for f in ("a", "b"))
                base.setdefault(k, [])
                have = {pair(x): i for i, x in enumerate(base[k]) if isinstance(x, dict)}
                for item in v or []:
                    if not isinstance(item, dict) or not item.get("a") or not item.get("b"):
                        continue
                    if pair(item) in have:
                        base[k][have[pair(item)]] = item
                        report.append(tr("s_s_s_aktualisiert") % (k, ""))
                    else:
                        have[pair(item)] = len(base[k])
                        base[k].append(item)
                        report.append(tr("s_s_s_hinzugefuegt") % (k, ""))
                continue
            if k in ("loans", "companies", "areas", "real_estate"):
                key = {"areas": "id", "real_estate": "id", "companies": "area"}.get(k, "name")
                existing = {x.get(key): i for i, x in enumerate(base.get(k) or []) if isinstance(x, dict)}
                base.setdefault(k, [])
                for item in v or []:
                    if not isinstance(item, dict):
                        continue
                    if k == "areas" and item.get("main_area"):
                        for x in base[k]:
                            if isinstance(x, dict):
                                x["main_area"] = False
                    if item.get(key) in existing:
                        base[k][existing[item[key]]] = item
                        report.append(tr("s_s_s_aktualisiert") % (k, item.get("name") or item.get(key)))
                    else:
                        base[k].append(item)
                        report.append(tr("s_s_s_hinzugefuegt") % (k, item.get("name") or item.get(key)))
            elif isinstance(v, dict):
                base.setdefault(k, {})
                for kk, vv in v.items():
                    if isinstance(vv, dict) and isinstance(base[k].get(kk), dict):
                        base[k][kk].update(vv)
                    elif isinstance(vv, list) and kk in ("illiquid_accounts", "areas", "transfer_categories", "entities"):
                        base[k][kk] = list(dict.fromkeys((base[k].get(kk) or []) + vv))
                    else:
                        base[k][kk] = vv
                report.append(tr("s_s_ergaenzt") % k)
            else:
                base[k] = v
                report.append("%s gesetzt" % k)
    return merged_config(base), unresolved, report


# ---------------------------------------------------------------------------
# Diagnose
# ---------------------------------------------------------------------------

_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9 ]{10,32}\b")
_DIGITS = re.compile(r"\d{7,}")


def mask_text(text: str, names: Optional[Dict[str, str]] = None) -> str:
    text = _IBAN.sub(lambda m: m.group(0)[:4] + "…", text)
    text = _DIGITS.sub("#######", text)
    if names:
        for n in sorted(names, key=len, reverse=True):
            if len(n) >= 3:
                text = text.replace(n, names[n])
    return text


def diagnose(store: Store, data_dir: str, config: dict, status: dict, mask_names: bool = True, lines: int = 400) -> str:
    cfg = copy.deepcopy(config)
    cfg.pop("ui", None)
    cfg["not_book"] = len(cfg.get("not_book") or [])        # only how many (amounts and texts stay out)
    kfd = cfg.get("cashflow") if isinstance(cfg.get("cashflow"), dict) else {}
    if kfd.get("recipient_to_account"):                                # recipients (names, IBANs): only how many per area
        kfd["recipient_to_account"] = {"Bereich%d" % i: len(m or {}) for i, m in enumerate(kfd["recipient_to_account"].values())}
    names: Dict[str, str] = {}
    if mask_names:
        ds = store.load("dataset.json", {}) or {}
        for i, k in enumerate(ds.get("accounts") or []):
            names[k["name"]] = "Konto%02d" % i
        for i, k in enumerate((ds.get("area_names") or {}).values()):
            names[k] = "Bereich%d" % i
        for l in cfg.get("loans") or []:
            if (l.get("detection") or {}).get("counter_iban"):
                l["detection"]["counter_iban"] = tr("s_iban")
    _walk_refs(cfg, lambda f, r: ((r.split("|", 1)[0].strip()[:8] + " | " + mask_text(r.split("|", 1)[1].strip(), names))
                                  if "|" in r else mask_text(r, names)))
    state = store.load("state.json", {}) or {}
    st = copy.deepcopy(status)
    for k in ("last_result", "last_run"):
        if isinstance(st.get(k), dict):
            st[k] = {kk: vv for kk, vv in st[k].items() if kk != "proposals"}
    home = os.path.expanduser("~")

    def m(text: str) -> str:
        text = mask_text(text, names)
        return text.replace(home, "~") if home and home != "/" else text

    out = ["Kontor-Diagnose %s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
           "Version %s, Python %s, %s %s" % (version(), platform.python_version(), platform.system(), platform.release()),
           "Status: " + m(json.dumps(st, ensure_ascii=False, default=str)),
           "Konfiguration (Namen %s): %s" % ("maskiert" if mask_names else tr("s_im_klartext"), m(json.dumps(cfg, ensure_ascii=False, indent=1))),
           tr("s_letzter_lauf") + m(json.dumps(state.get("last_run"), ensure_ascii=False, default=str)),
           "Verlauf: " + m(json.dumps((state.get("history_source") or [])[-10:], ensure_ascii=False, default=str)),
           "--- Protokoll (letzte %d Zeilen) ---" % lines]
    try:
        with open(os.path.join(data_dir, "kontor.log"), encoding="utf-8", errors="replace") as f:
            out += [m(l.rstrip("\n")) for l in f.readlines()[-lines:]]
    except FileNotFoundError:
        out.append(tr("s_kein_protokoll"))
    return "\n".join(out)
