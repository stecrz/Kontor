"""Kontor-Dienst: Web-Oberflaeche (API + statische Dateien) und Zeitplaner in einem Prozess.

Sicherheit:
  * bindet an 127.0.0.1 (oder eine Tailscale-Adresse 100.64.0.0/10, wenn eingestellt); nie 0.0.0.0
  * Anmeldung mit Passwort (oder Touch ID von diesem Mac aus, Face ID von einem hinzugefuegten iPhone), Sitzungscookie
    HttpOnly/SameSite=Strict, CSRF-Token fuer jede aendernde Anfrage, Origin-Pruefung, Ratenbegrenzung, Leerlaufsperre
  * von einem anderen Geraet: jede Aenderung nur von einem hinzugefuegten iPhone mit Face ID fuer genau diese Anfrage
    (_remote_check); MAC_ONLY nie
  * CSP ohne Fremdquellen; Netzverbindungen nur zu GitHub (Update-Pruefung) und -- auf Klick -- zu OpenFIGI
    (Wertpapiernamen) sowie GitHub und Hugging Face (Programm und Modelle des Assistenten)
  * Schreibzugriffe auf MoneyMoney nur ueber die Bruecke (Liste erlaubter Methoden): Buchungen der Regeln in
    Offline-Konten, die Kategorie eines Umsatzes nach deinem Klick, auf Wunsch der Belegpfad im Kommentar
  * Updates, Zugang, Dateizugriffe (Belegordner oeffnen) nur von diesem Mac aus; Buchen auch vom hinzugefuegten iPhone, nur wie gezeigt
"""
from __future__ import annotations

import atexit
import base64
import bisect
import binascii
import copy
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import shutil
import signal
import logging
import mimetypes
import os
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, quote, urlparse

import access
import auth
import i18n
import mac_app
import mm_categories
import mm_history
import realestate
import security_names
import history_import
import categorize
import updates
import changelog
import pyboot
import pyruntime
import components
import price_index
import web_search
import assistant as assistant_mod
import demo
import devices as devices_mod
import qr
import webauthn
from receipts import Belege, file_status, pattern_problem
import receipt_text
from mm_bridge import Bridge, MoneyMoneyError, MoneyMoneyLocked, MoneyMoneyNotRunning, is_running
from core import (REPORT_LOCK, with_property_categories, assign_period, assign_skipped, check_file_version, positions_overview, save_positions, category_tree, follow_categories, prune_account_settings, account_sig, account_tree, bank_accounts, bereiche_for, build_report, abruf_arten, check_config, diagnose, earliest_needed, export_package, fetch, freeze_assignments, immo_for_plan, merge_snapshots, record_snapshot,
                     immo_results, import_package, ledger_fp, merge_holdings, merged_config, not_booked_entry, plan_pending, refresh_accounts, rule_accounts, run_once, unavailable_text, version, version_on_disk, MM_HISTORY_FILE)
from model import Ledger, Tx, accounts_from_export, ledger_from_bytes, ledger_to_bytes
from report import ROLES, account_balance_series, account_months, account_roles, apply_plan, role_label
from report import PLAN_AREA_METHODS, PLAN_METHODS, PLAN_MODELS, PLAN_SIDES, moved_plan_rows, plan_defaults, plan_one_off, plan_rule, plan_sec
from model import marks_in
from rules import Seen, TAG_RE, bkey as rules_bkey, plan_all as plan_rules
from storage import DAMAGED as storage_damaged, Store, StoreDamaged, StoreError, StoreLocked, _names as storage_names, _remove as _remove_quietly
from excel import Sheet, workbook
from i18n import tr

log = logging.getLogger("kontor.app")
HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, "web")
MAX_BODY = 2 * 1024 * 1024
MAX_UPLOAD = 90 * 1024 * 1024      # Base64 eines 60-MB-Belegs
MAX_RESTORE = 64 * 1024 * 1024     # a backup to restore (with everything the assistant was told to remember)
MAX_SPEECH = 28 * 1024 * 1024      # a dictated recording (base64 of at most 20 MB of WAV: ten minutes), a receipt given to the assistant (20 MB)
PLAN_PARAMS = ("horizon_months", "default_method", "inflation_percent_pa", "income_increase_percent_pa",
               "expense_increase_percent_pa", "return_percent_pa", "fi_real_return_percent")



def approval(raw) -> Tuple[Optional[Dict[str, dict]], Optional[str]]:
    """"Book selected": {mark: {betrag, datum, zweck}} checked -- marks of Kontor, amount not zero, a real date, a short text."""
    if not isinstance(raw, dict) or len(raw) > 2000:
        return None, tr("s_freigabe_ungueltig")
    out: Dict[str, dict] = {}
    for key, ch in raw.items():
        acc, _, tag = str(key).partition("|")
        if not re.fullmatch(r"[0-9A-Za-z-]{8,64}", acc) or not TAG_RE.fullmatch(tag):
            return None, tr("s_markierung_ungueltig")
        ch = ch if isinstance(ch, dict) else {}
        c: dict = {}
        try:
            if ch.get("amount") not in (None, ""):
                c["amount"] = round(float(str(ch["amount"]).replace(",", ".")), 2)
                if abs(c["amount"]) < 0.01 or abs(c["amount"]) > 1e9:
                    raise ValueError
            if ch.get("date"):
                d = date.fromisoformat(str(ch["date"]))
                if not date(1990, 1, 1) <= d <= date.today() + timedelta(days=366):
                    raise ValueError
                c["date"] = d.isoformat()
        except ValueError:
            return None, tr("s_aenderung_ungueltig")
        if ch.get("purpose") is not None:
            c["purpose"] = str(ch["purpose"])[:300]
        try:                    # the amount you saw: booked only if it is still the same
            if ch.get("shown") not in (None, ""):
                c["shown"] = round(float(ch["shown"]), 2)
        except (TypeError, ValueError):
            return None, tr("s_aenderung_ungueltig")
        out[rules_bkey(acc, tag)] = c
    return out, None


def transfer_category(app: "App") -> Tuple[Optional[str], Callable[[str], bool]]:
    """Your category for transfers in MoneyMoney (the first the cash flow takes as one; None: there is none) and the check
    whether a category is one."""
    from report import transfer_check
    is_transfer = transfer_check(app.config)
    return next((p for p in (categorize.norm_cat(str(c.get("path") or c.get("name") or "")) for c in app.categories_raw
                             if not c.get("group") and not c.get("default")) if p and is_transfer(p)), None), is_transfer


def open_category_items(app: "App", year: Optional[int], area: Optional[str], minimum: float = 0.0, limit: int = 300, level: Optional[str] = None) -> dict:
    """The bank bookings without a category, grouped by counterparty, each with Kontor's suggestion and how sure it is (the
    page Kategorisieren; by meaning too where the assistant's embeddings of transactions may be used)."""
    # in the areas and the period you chose there -- a year asked for (the assistant) instead of that period; `period` in the
    # answer: the one that applied (ISO days, "": open)
    kat = categorize.load(app.store)
    areas = bereiche_for(app.ledger, app.config)
    bereich_of = {a.uuid: b["id"] for b in areas for a in b["leaves"]}
    roles = account_roles(app.ledger, app.config)
    period = (date(year, 1, 1), date(year, 12, 31)) if year and 1 <= year <= 9999 else assign_period(app.config)
    res = categorize.open_items(kat, app.ledger, bereich_of, None, area, minimum, limit, bank_accounts(roles), assign_skipped(app.config, areas),
                                period, app.category_hints(kat, bereich_of, roles), app.tx_meaning(), level)
    res["period"] = {"from": period[0].isoformat() if period[0] else "", "to": period[1].isoformat() if period[1] else ""}
    return res


def category_doubts(app: "App", limit: int = 300) -> dict:
    """Categories that make no sense to Kontor (categorize.doubts): bank bookings of the areas you categorise in the period you
    chose, the surest doubts first -- kept while nothing they rest on changed (the hints, the ones you said are fine)."""
    kat = categorize.load(app.store)
    areas = bereiche_for(app.ledger, app.config)
    bereich_of = {a.uuid: b["id"] for b in areas for a in b["leaves"]}
    roles = account_roles(app.ledger, app.config)
    hints = app.category_hints(kat, bereich_of, roles)
    skipped, cut, banks = assign_skipped(app.config, areas), assign_period(app.config), bank_accounts(roles)
    paired = hash(frozenset(categorize.transfers(app.ledger, bereich_of)))
    key = (json.dumps(kat.get("doubt_ok") or {}, sort_keys=True), tuple(sorted(skipped)), cut, limit, tuple(sorted(banks)), paired)
    cached = getattr(app, "_doubts", None)
    if cached and cached[0] is hints and cached[1] == key:   # (the hints themselves: a new object may get an old one's id)
        return cached[2]
    res = categorize.doubts(kat, app.ledger, bereich_of, hints, None, None, banks, skipped, cut, limit)
    app._doubts = (hints, key, res)
    return res


def assign_categories(app: "App", ids: List[int], pfad: str, modus: str = "auto", local: bool = True, confirmed: Optional[dict] = None,
                      wait: bool = False, grund: str = "assignment") -> dict:
    """Your assignment of a category to transactions (from Kategorisieren or the assistant's card): into MoneyMoney (only categories
    that exist there) -- at the Mac right away, from elsewhere at the next sync at the Mac; until then it waits in Kontor and counts."""
    if not ids:
        raise ValueError(tr("s_keine_umsaetze_angegeben"))
    if len(ids) > 2000:                                  # the page sends larger selections in parts
        raise ValueError(tr("s_hoechstens_2000"))
    if pfad:
        why = mm_categories.assignable(mm_categories.index(app.categories_raw), pfad)
        if why:
            raise ValueError(tr({"lacking": "s_kategorie_in_mm_anlegen", "folder": "s_kategorie_ist_ordner"}.get(why, "s_kategorie_standard"), pfad))
    with categorize.LOCK:
        kat = categorize.load(app.store)
        n = categorize.set_waiting(kat, ids, pfad, only_empty=modus == "empty")
        mm = app.write_categories(kat, ids, pfad, modus, local, confirmed)
        if mm["written"] and app.ledger is not None:
            categorize.learn(kat, app.ledger)           # suggestions for the rest at once
        categorize.save(app.store, kat)
    ok, err = app.rebuild_report(wait=wait, grund=grund) if app.ledger is not None else (False, None)
    log.info("%d transaction(s) assigned (%d written to MoneyMoney, %d later)", n, mm["written"], mm["later"])
    return {"ok": True, "count": n, "mm": mm, "report": ok, "text": err}


def assistant_assign_categories(app: "App", ids: List[int], pfad: str, local: bool) -> dict:
    """The assistant's card, after your click: the category for those of `ids` that are still open at that moment -- no category in
    MoneyMoney and no assignment of yours waiting in Kontor; MoneyMoney read fresh before each write, written only where it shows no
    category at all (modus "empty"). A category set meanwhile -- by you, on the page, from the iPhone, in MoneyMoney, also by Kontor
    earlier -- is never changed. Returns how many were written, wait for the Mac, were left as they are -- and which (`done`: the
    only ones the card takes back)."""
    pfad = categorize.norm_cat(pfad)
    with categorize.LOCK:                                # held throughout (re-entrant): nothing can be assigned between the check and the write
        kat = categorize.load(app.store)
        by_id = {t.id: t for t in app.ledger.txs} if app.ledger is not None else {}
        still = [i for i in ids if i in by_id and not categorize.mm_of(by_id[i]) and str(i) not in kat["assignment"]]
        if not still:
            return {"written": 0, "later": 0, "skipped": len(ids), "done": []}
        res = assign_categories(app, still, pfad, "empty", local, grund="assistant")
    mm = res["mm"]
    done = list(mm.get("written_ids") or []) + list(mm.get("later_ids") or [])
    return {"written": mm["written"], "later": mm["later"], "skipped": len(ids) - len(done), "done": done}


def unassign_categories(app: "App", ids: List[int], pfad: str, local: bool) -> dict:
    """The assistant's card taken back (`ids`: only what it wrote or set waiting and has not taken back yet): only what is still the
    card's category. What was written into MoneyMoney gets the category from before -- only at the Mac, only where MoneyMoney still
    shows it, and first: if MoneyMoney does not get to all of them (`open`), the waiting ones stay as well, to be taken back later.
    Then the card's waiting ones are dropped in Kontor. Returns which were taken back (`undone`, `dropped`), how many MoneyMoney did
    not get to (`open`) and how many were changed since and stay (`kept`). Nothing to take back at all: ValueError."""
    pfad = categorize.norm_cat(pfad)
    with categorize.LOCK:
        kat = categorize.load(app.store)
        own = (app.store.load_shared("state.json", {}) or {}).get(mm_categories.LOG_KEY) or {}
        mine_waiting = lambda z: categorize.waiting(z) and z.get("e") and categorize.norm_cat(z.get("k") or "") == pfad
        waits = [i for i in ids if mine_waiting(kat["assignment"].get(str(i)))]
        mine = [i for i in ids if i not in waits and categorize.norm_cat((own.get(str(i)) or {}).get("new") or "") == pfad]
        if mine and not local:                           # before anything changes: in MoneyMoney only at the Mac
            raise ValueError(tr("s_nur_von_diesem_mac_aus"))
        res = app.undo_categories(mine) if mine else {"undone": 0, "undone_ids": [], "open": 0}
        if res["open"]:
            waits = []                                   # MoneyMoney did not get to all: the card stays, for the rest later
        for i in waits:
            kat["assignment"].pop(str(i), None)
        if waits:
            categorize.save(app.store, kat)
    if not (waits or res["undone"] or res["open"]):
        raise ValueError(tr("s_ki_inzwischen_geaendert"))
    if waits or res["undone"]:
        app.rebuild_report(wait=False, grund="assignment taken back")
    return {"undone": list(res["undone_ids"]), "dropped": waits, "open": res["open"],
            "kept": 0 if res["open"] else len(ids) - len(waits) - res["undone"]}


def receipt_tx(app: "App", tid: Any, ums: Optional[dict] = None) -> Optional[dict]:
    """The transaction a receipt is filed to (with its area's name for the subfolder) -- None: filed without one."""
    if tid in (None, ""):
        return None
    ums = ums if ums is not None else {t["id"]: t for t in app.umsatzliste()}
    t = ums.get(int(tid))
    if t is None:
        raise ValueError(tr("s_umsatz_s_nicht_gefunden_liste") % tid)
    ds = app.store.load_shared("dataset.json", {}) or {}
    names = {k["uuid"]: k["name"] for k in ds.get("accounts", [])}
    names.update(ds.get("area_names") or {})
    return dict(t, entity_name=names.get(t["entity"], ""))


def receipt_matches(app: "App", fields: dict, amount: Optional[float], day: Optional[str], name: str) -> List[dict]:
    """The transactions a receipt the assistant was given may belong to (receipt_text.candidates) -- with the other side's IBAN
    from the ledger (it is not in the list the pages get)."""
    ibans = {t.id: t.counter_iban for t in app.ledger.txs if t.counter_iban} if app.ledger is not None else {}
    rows = [dict(t, counter_iban=ibans.get(t["id"], "")) for t in app.umsatzliste() if not t.get("transfer")]
    return receipt_text.candidates(fields, rows, amount, day, name)


def receipt_place(app: "App", tid: Optional[int]) -> dict:
    """Where a receipt would be filed (for the card): the transaction, the folder shown with ~, whether it is there yet."""
    tx = receipt_tx(app, tid)
    bl = Belege(app.store, app.config)
    full = os.path.join(bl.folder, bl.subfolder(tx))
    home = os.path.expanduser("~")
    return {"tx": tx, "folder": "~" + full[len(home):] if full.startswith(home + os.sep) else full, "exists": os.path.isdir(bl.folder)}


def assistant_file_receipt(app: "App", data: bytes, name: str, tid: Optional[int], note: str) -> dict:
    """A receipt the user gave the assistant, filed after his click on its card: as an upload under Transactions & receipts
    (the receipts folder -- created with that click when missing --, linked to the transaction). The reference in MoneyMoney
    ("Reference in MoneyMoney") is not written: the assistant changes nothing in MoneyMoney but categories."""
    try:
        e = Belege(app.store, app.config).add_bytes(receipt_tx(app, tid), name, data, note)
    except OSError as ex:                                # the folder cannot be made or written: its reason on the card
        raise ValueError(str(ex))
    log.info("Receipt stored after the user's click on the assistant's card (%d KB)", len(data) // 1024)
    return dict(e)


def assistant_unfile_receipt(app: "App", did: dict) -> None:
    """Takes a receipt filed by the assistant back: its entry and its file -- unless it was changed since (linked to another
    transaction, another note, moved) or is gone."""
    bl = Belege(app.store, app.config)
    e = next((x for x in bl.entries() if x.get("id") == did.get("id")), None)
    if e is None or any(e.get(k) != did.get(k) for k in ("tx_id", "note", "path", "name", "date", "amount")):
        raise ValueError(tr("s_ki_inzwischen_geaendert"))
    bl.remove(e["id"], delete_file=True, like={k: did.get(k) for k in ("tx_id", "note", "path", "name", "date", "amount")})      # exactly this one
    log.info("Receipt filed by the assistant taken back")


def approve_bookings(app: "App", shown: Dict[str, dict]) -> dict:
    """Waiting bookings approved (the assistant's card, after the click at the Mac): a live run -- MoneyMoney read and the rules
    planned afresh, as they are now -- that books only these, each only if it waits exactly as the card showed it (amount, day,
    counterparty, text; core.not_as_shown) and Kontor does not want it checked first (the rule it comes from is the assistant's
    and not confirmed by you yet): the others are left, with the reason. Returns which were booked and which still wait, and why."""
    if app.running:
        return {"booked": [], "left": list(shown), "error": tr("s_ein_abgleich_laeuft_bereits")}
    marks = lambda: {rules_bkey(b["account_id"], b["mark"]) for b in kontor_bookings(app.ledger)}
    before = marks()                                     # in MoneyMoney already (e.g. approved on the page meanwhile): not this click's
    res = app.do_run(False, True, approve={k: {"shown": dict(v)} for k, v in shown.items()})
    refused = res.pop("_refused", None) or {}            # not (or no longer) as shown, or to be checked first: why
    if res.get("status") == "error" and app.ledger is not None:
        try:                                             # something failed after writing (the run's state not kept): MoneyMoney read again
            if app.refresh_ledger()[0] is None:
                raise RuntimeError("not read")
        except Exception as e:                           # not even that: whether it was booked is not known -- said so, never "not booked"
            log.warning("Approval: MoneyMoney not read again after a failed run (%s)", type(e).__name__)
            return {"booked": [], "left": list(shown), "error": tr("s_ki_buchung_unklar")}
    # booked by this click: what carries its mark in MoneyMoney now and did not before -- whatever the run says (it may stop midway)
    after = marks()
    booked = [k for k in shown if k in after and k not in before]
    left = [k for k in shown if k not in booked]
    warn = [w for w in res.get("warnings") or [] if w]
    reasons = list(dict.fromkeys(str(refused[k]) for k in left if k in refused))
    if not left:
        why = None
    elif reasons and all(k in refused for k in left):    # left on purpose: each reason once
        why = " · ".join(reasons)[:300]
    elif tr("s_betraege_geaendert") in warn:            # an amount changed meanwhile: nothing booked
        why = tr("s_betraege_geaendert")
    else:                                                # MoneyMoney stopped, the rules failed, ...: said as the run says it
        why = " · ".join(reasons + [res.get("text") or res.get("error") or (warn[0] if warn else None) or tr("s_ki_nicht_gebucht")])[:300]
    return {"booked": booked, "left": left, "error": why}


def replan_waiting(app: "App", later: bool = True) -> None:
    """The approval list planned again from the rules as they are now and the state last read (nothing is written to
    MoneyMoney): after a rule was saved -- by you or by the assistant's card -- the list is never the old one. A booking of a
    rule not confirmed carries its note, one that changed its new text, one no longer needed is gone. During a sync (planned
    from the rules as they were): once more when it has ended."""
    if app.ledger is None or not app.store.is_open:
        return
    if app.running and later:
        def after() -> None:
            for _ in range(3000):
                if not app.running:
                    break
                time.sleep(0.2)
            try:
                replan_waiting(app, later=False)
            except Exception as e:                       # (signed out or ended meanwhile: the next sync plans it)
                log.info("Approval list not planned again after the sync (%s)", type(e).__name__)
        threading.Thread(target=after, name="kontor-replan", daemon=True).start()
    config, ledger = app.config, app.ledger

    def upd(cur: dict) -> None:
        lr = cur.get("last_run")
        if not isinstance(lr, dict):
            return                                       # no check yet: the first one plans it
        try:
            rows = plan_pending(ledger, config, cur, date.today())
        except Exception as e:                           # the list stays as it was; the next check plans it again
            log.warning("Approval list not recalculated after the rules changed (%s)", type(e).__name__)
            return
        if rows or lr.get("dry_run"):                    # (nothing waits and nothing did: the last run's bookings stay listed)
            lr["proposals"], lr["dry_run"] = rows, bool(rows)
    app.store.update("state.json", upd, {})


RULE_SECTIONS = ("loans", "companies", "account_mirrors")
def _plain_numbers(d: Any) -> Any:
    """3.0 and 3 alike (what the page sends back as JSON has no "3.0")."""
    if isinstance(d, float) and d.is_integer():
        return int(d)
    if isinstance(d, dict):
        return {k: _plain_numbers(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_plain_numbers(v) for v in d]
    return d


_canon = lambda d: json.dumps(_plain_numbers(d), sort_keys=True, ensure_ascii=False, default=str)


RULES_LOCK = threading.Lock()        # a rule checked and saved (the assistant's card, the rules page) -- one at a time


class _Stale(Exception):
    """The same setting changed on the page and meanwhile elsewhere (another window, another device, the assistant)."""


_GONE = object()


def _merge3(seen: Any, mine: Any, now: Any) -> Any:
    """What a page saves, against what it was drawn from (seen) and what stands now: what the page left as it was takes what
    stands now (another window's change stays); what only the page changed is taken; both changed the same thing -- dicts key by
    key, anything else whole -- refused (_Stale), unless both made it the same. _GONE: not there."""
    if mine == now or mine == seen:
        return now
    if now == seen:
        return mine
    if isinstance(seen, dict) and isinstance(mine, dict) and isinstance(now, dict):
        out = {}
        for k in list(now) + [k for k in mine if k not in now]:
            v = _merge3(seen.get(k, _GONE), mine.get(k, _GONE), now.get(k, _GONE))
            if v is not _GONE:
                out[k] = v
        return out
    raise _Stale()


def _rules_now(cfg: dict) -> str:
    """The booking rules as they stand (what the rules page was drawn from, compared when it saves)."""
    return _canon([cfg.get(k) or [] for k in RULE_SECTIONS])


def _rule_form(section: str, d: Any) -> str:
    """A rule as it means the same whichever page wrote it: without empty fields, the review mark and what the rules page fills in
    by itself (a company's threshold 0.01, a loan's counterparty = its name, active, a liability)."""
    def bare(v: Any) -> Any:
        if isinstance(v, dict):
            v = {k: bare(x) for k, x in v.items() if k != "review"}
            return {k: x for k, x in v.items() if x not in (None, "", [], {})}
        if isinstance(v, list):
            return [bare(x) for x in v]
        return v
    d = bare(_plain_numbers(copy.deepcopy(d))) if isinstance(d, dict) else d
    if isinstance(d, dict):
        if section == "companies" and d.get("threshold") == 0.01:
            d.pop("threshold")
        if section == "loans":
            if (d.get("booking") or {}).get("counterparty") == d.get("name"):
                d["booking"].pop("counterparty")
                if not d["booking"]:
                    d.pop("booking")
            if d.get("active") is True:
                d.pop("active")
            if d.get("kind") == "liability":
                d.pop("kind")
    return _canon(d)


def _with_rule(cfg: dict, section: str, old: Optional[dict], new: Optional[dict]) -> dict:
    """The configuration with one rule changed (old -> new), added (old None) or removed (new None) -- old must be there as it was."""
    if section not in RULE_SECTIONS:
        raise ValueError(tr("s_ki_regel_inzwischen"))
    cfg = copy.deepcopy(cfg)
    lst = list(cfg.get(section) or [])
    if old is not None:
        at = next((i for i, x in enumerate(lst) if _rule_form(section, x) == _rule_form(section, old)), None)
        if at is None:                                   # changed or removed meanwhile (on the page, by another card)
            raise ValueError(tr("s_ki_regel_inzwischen"))
        if new is None:
            lst.pop(at)
        else:
            lst[at] = new
    elif new is not None:
        lst.append(new)
    cfg[section] = lst
    return cfg


def rule_preview(app: "App", section: str, old: Optional[dict], new: dict) -> dict:
    """A rule proposed by the assistant, checked before the card: errors in it (check_config) and what it would propose to book --
    bookings that are new or of another amount than with the rules as they are, and those no longer proposed (nothing is saved
    or written)."""
    cfg = _with_rule(app.config, section, old, new)
    merged = merged_config(dict(cfg, not_book=app.config.get("not_book") or []))
    found = check_config(app.ledger, app.categories_raw, merged) if app.ledger is not None else []
    errors = [f["text"] for f in found if f.get("severity") == "error"]
    if errors or app.ledger is None:
        return {"errors": errors, "bookings": 0, "dropped": 0}
    st = app.store.load("state.json", {}) or {}

    def plan(c: dict):
        led = app.ledger.fork()
        return plan_rules(led, c, date.today(), seen=Seen.from_state(st.get("seen"), led, date.today())).proposals
    try:
        before = {p.key: round(p.amount, 2) for p in plan(merged_config(dict(app.config, not_book=app.config.get("not_book") or [])))}
        after = {p.key: round(p.amount, 2) for p in plan(merged)}
    except Exception as e:                               # the rules met something unexpected: said, nothing proposed
        log.warning("Rule preview failed (%s)", type(e).__name__)
        return {"errors": [tr("s_regeln_fehler") % type(e).__name__], "bookings": 0, "dropped": 0}
    return {"errors": [], "bookings": sum(1 for k, v in after.items() if before.get(k) != v), "dropped": sum(1 for k in before if k not in after)}


def save_assistant_rule(app: "App", section: str, old: Optional[dict], new: dict) -> dict:
    """The assistant's rule after your click: saved marked for review -- each booking from it waits for your approval until you
    confirm the rule under Konten & Regeln. Only if the rule it changes is still as it was; never with errors."""
    new = dict(new, review=True)
    with RULES_LOCK:
        cfg = _with_rule(app.config, section, old, new)
        if app.ledger is not None:
            errors = [f["text"] for f in check_config(app.ledger, app.categories_raw, merged_config(cfg)) if f.get("severity") == "error"]
            if errors:
                raise ValueError(errors[0])
        before = [_canon(x) for x in app.config.get(section) or []]
        app.save_config(cfg)
        # as it is stored now (saving fills in fields): what taking it back compares with
        saved = next((x for x in app.config.get(section) or [] if _canon(x) not in before), None) or new
    app.request_rebuild("booking rule from the assistant")
    log.info("Booking rule %s by the assistant after the user's click (%s)", "changed" if old is not None else "added", section)
    return saved


def undo_assistant_rule(app: "App", section: str, old: Optional[dict], saved: dict) -> None:
    """The assistant's rule taken back: as before (or gone, when it was new) -- only while it is still as the card saved it."""
    with RULES_LOCK:
        app.save_config(_with_rule(app.config, section, saved, old))
    app.request_rebuild("booking rule taken back")


def hold_back_bookings(app: "App", keys: List[str]) -> int:
    """Bookings you do not want: never proposed again (settings: not_book) until "Propose again"; what still waits is planned again
    without them (from the last state read, nothing is written)."""
    lr = (app.store.load("state.json", {}) or {}).get("last_run") or {}
    cfg = copy.deepcopy(app.config)
    cfg["not_book"] = [x for x in cfg.get("not_book") or [] if x.get("key") not in keys] + [
        not_booked_entry(next((x for x in lr.get("proposals") or [] if x.get("key") == key), None) or {"account_name": "", "text": ""}, key) for key in keys]
    app.save_config(cfg)

    def upd(cur: dict) -> None:
        lr = cur.get("last_run") or {}
        if lr.get("proposals"):
            lr["proposals"] = [x for x in lr["proposals"] if x.get("key") not in keys]
            if lr.get("dry_run") and app.ledger is not None:
                try:
                    lr["proposals"] = plan_pending(app.ledger, app.config, cur, date.today())
                except Exception as e:          # the list stays as it was; the next check plans it again
                    log.warning("Approval list not recalculated: %s", e)
            lr["dry_run"] = bool(lr["proposals"]) and lr.get("dry_run", False)
    app.store.update("state.json", upd, {})
    log.info("%d booking(s) set to not be booked", len(keys))
    return len(keys)


def restore_bookings(app: "App", keys: List[str]) -> int:
    """"Propose again": off the list of bookings not to book -- the next check proposes them if they are still needed."""
    cfg = copy.deepcopy(app.config)
    before = len(cfg.get("not_book") or [])
    cfg["not_book"] = [x for x in cfg.get("not_book") or [] if x.get("key") not in keys]
    app.save_config(cfg)
    log.info("%d booking(s) to be proposed again", before - len(cfg["not_book"]))
    return before - len(cfg["not_book"])


def kontor_bookings(ledger) -> List[dict]:
    """The bookings Kontor has made in MoneyMoney: those carrying its mark (#kontor-...) in the purpose. Newest first."""
    out: List[dict] = []
    if ledger is None:
        return out
    kinds = {"tx": "repayment", "zins": "interest", "wert": "value", "gk": "mirror"}
    for t in ledger.txs:                                 # the ledger holds no planned bookings (Ledger.without_planned)
        ms = marks_in(t.purpose)
        if not ms or getattr(t, "planned", False):
            continue
        acc = ledger.accounts.get(t.account_uuid)
        k = ms[0].split("-")[1] if ms[0].count("-") >= 2 else ""
        out.append({"date": t.booking_date.isoformat(), "account": acc.name if acc else "", "account_id": t.account_uuid, "kind": kinds.get(k, k), "amount": round(t.amount, 2),
                    "counterparty": t.name, "purpose": TAG_RE.sub("", t.purpose).strip(" ·"), "mark": ms[0]})
    out.sort(key=lambda x: (x["date"], x["mark"]), reverse=True)
    return out


def bind_allowed(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return ip.is_loopback or ip in ipaddress.ip_network("100.64.0.0/10")


def balance_lookup(ledger: Ledger) -> Callable[[str, date, bool], Optional[float]]:
    """Saldo eines Kontos am Ende eines Tages aus den Umsaetzen (heutiger Saldo minus alle spaeteren gebuchten Umsaetze),
    nach Buchungs- oder Wertstellungsdatum; None fuer Depots und unbekannte Konten."""
    idx: Dict[Tuple[str, bool], Tuple[List[date], List[float]]] = {}
    per: Dict[str, List[Tx]] = {}
    for t in ledger.txs:
        if t.booked:
            per.setdefault(t.account_uuid, []).append(t)
    for u, txs in per.items():
        for by_value in (False, True):
            pts = sorted(((t.value_date or t.booking_date) if by_value else t.booking_date, t.amount) for t in txs)
            cum = [0.0]
            for _d, a in pts:
                cum.append(cum[-1] + a)
            idx[(u, by_value)] = ([d for d, _a in pts], cum)

    def balance_at(uuid: str, day: date, by_value: bool = False) -> Optional[float]:
        acc = ledger.accounts.get(uuid)
        if acc is None or acc.portfolio or acc.group:
            return None
        dates, cum = idx.get((uuid, by_value), ([], [0.0]))
        return round(acc.balance - (cum[-1] - cum[bisect.bisect_right(dates, day)]), 2)
    return balance_at


DAMAGED_KEY = "set_aside"                     # in state.json: files that did not read at a sign-in and were set aside (App.unlock)
TID_RE = re.compile(r"[0-9a-f]{32}")          # the id of the sign-in page's Touch ID request (random, made by the page)
TID_LOCK = threading.Lock()
SETUP_LOCK = threading.Lock()                        # the first password is set once: a second click meanwhile waits for nothing


class App:
    DEMO = False                                     # the demo (DemoApp): made-up data, its own sign-in, only some requests
    _demo_box: Optional["DemoBox"] = None
    _tid: Optional[dict] = None                      # the sign-in page's Touch ID request running (touchid_begin; under TID_LOCK)
    # prices for the balance sheet in today's money (price_index.py): newer months of the index, one try at a time
    price_reader: Optional[Callable[[dict], dict]] = None      # (tests: a stand-in for the sealed reader)
    _price_lock = threading.Lock()
    _price_busy = False

    @property
    def demo_box(self) -> Optional["DemoBox"]:
        """The demo shown from the sign-in page (at most one; DemoBox) -- none in the demo itself."""
        if self.DEMO:
            return None
        with DEMO_LOCK:
            if self._demo_box is None:
                self._demo_box = DemoBox(self)
            return self._demo_box

    @property
    def devices(self) -> Optional[devices_mod.Devices]:
        """The iPhones added at the Mac (their passkeys, devices.py) -- none in the demo: it never changes them (a session of it
        opened with an iPhone's passkey is confirmed against the real Kontor's, see the handler's _device_session)."""
        if self.DEMO:
            return None
        with DEMO_LOCK:
            if self.__dict__.get("_devices") is None:
                self.__dict__["_devices"] = devices_mod.Devices(self.store)
            return self.__dict__["_devices"]

    def __init__(self, store: Store, data_dir: str, bridge_factory=Bridge):
        self.store = store
        self.data_dir = data_dir
        self.program_dir = HERE                      # what an uninstall may remove besides the data (tests: a copy)
        self.bridge_factory = bridge_factory
        # before anyone signs in the store is locked: only the start settings (no data) -- unlock() reads the rest
        self.config = merged_config(store.load("config.json", {}) or {}) if store.is_open else merged_config({"ui": access.start_settings(data_dir)})
        self._open_lock = threading.Lock()
        self.apply_language()
        self.sessions = auth.Sessions(idle_minutes=int(self.config["ui"].get("lock_minutes", 15)))
        self.ledger: Optional[Ledger] = None            # letzter Stand aus MoneyMoney
        self.ledger_time: Optional[datetime] = None
        self.umsaetze: Optional[list] = None            # kompakte Umsatzliste des letzten Berichts (sonst aus umsaetze.json)
        st = (store.load("state.json", {}) or {}) if store.is_open else {}
        self.categories_raw: list = mm_categories.with_paths(st.get("categories_raw") or [])
        self.started = datetime.now()
        self.instance = secrets.token_hex(6)              # changes with every (re)start; the page waits for a new one after a restart
        self.last_run_at: Optional[float] = None
        self.last_result: Optional[dict] = None
        self.running = False
        self.run_step: Optional[dict] = None      # what the run is doing now (shown in the interface)
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.update_info: Optional[dict] = None
        self.update_checked: Optional[float] = None
        self.tls_ctx: Optional[ssl.SSLContext] = None
        self.tls_checked: Optional[float] = None
        self._bankabruf_cache: Tuple[Any, Optional[dict]] = (None, None)
        # Berichtsneubau laeuft im Hintergrund: mehrere Anstoesse werden zu einem Lauf zusammengefasst
        self.rebuild_cv = threading.Condition()
        self.rebuild_pending = False
        self.rebuild_running = False
        self.rebuild_reasons: List[str] = []
        self.bericht: dict = {"as_of": None, "duration": None, "error": None, "reason": None}
        self._mm_locked_logged = False          # "locked" logged once, "unlocked" once again (not every 30 s)
        self.bericht_fortschritt: dict = {"share": 0.0, "step": ""}
        self.check_lock = threading.Lock()
        self.ledger_cache_fp: Optional[str] = None
        self.ledger_from_cache = False
        if store.is_open:
            threading.Thread(target=self._load_ledger_cache, name="kontor-cache", daemon=True).start()
        self.mmh: dict = {"running": False, "step": None, "result": None}   # Kontostaende aus MoneyMoney einlesen
        if sys.platform == "darwin" and not self.DEMO:          # Touch-ID-Helfer bei Bedarf (neu) uebersetzen
            threading.Thread(target=lambda: log.info("Touch ID helper: %s", auth.build_touchid()), name="kontor-touchid", daemon=True).start()
            port = int((self.config.get("ui") or {}).get("port") or 8765)          # Kontor's own app: its address, built if needed
            threading.Thread(target=lambda: log.info("Mac app: %s", mac_app.prepare(port)), name="kontor-mac-app", daemon=True).start()
        self.restart_allowed = False        # nur der echte Dienst (serve) startet sich bei neuem Code selbst neu
        self.remote_listening: Optional[Tuple[str, str]] = None     # (Schema, Adresse) des Zugangs fuer andere Geraete
        self.remote_error: Optional[str] = None
        self.remote_tried: float = 0.0
        self._handler = None
        self._ts_cache: Tuple[float, dict] = (0.0, {})
        self.mm_probe: Tuple[float, Optional[bool]] = (0.0, None)     # (Zeitpunkt, gesperrt?)
        self.mm_retry_at: Optional[float] = None
        self._capture_sig: Optional[tuple] = None      # zuletzt gesehener Kontenstand (Konto, Saldo, Abrufzeit)
        self._captured_once = False                     # erster Schnellabgleich seit dem Start erledigt (Lueckenpruefung)
        self._change_since: Optional[float] = None      # seit wann MoneyMoney neue Daten zeigt (Abruf laeuft evtl. noch)
        self.retry_reason = ""
        self._assistant = None                          # created with its first use (assistant.py)
        self._assistant_lock = threading.Lock()
        self._mm_seen = False                           # lief MoneyMoney beim letzten Blick? (bestimmt den Takt)
        self._hb_written = 0.0
        self.prev_seen: Optional[datetime] = None       # wann der Dienst vor diesem Start zuletzt lief
        self._read_prev_seen()

    def _read_prev_seen(self) -> None:
        try:
            ps = (self.store.load("state.json", {}) or {}).get("service_last") if self.store.is_open else None
            self.prev_seen = datetime.fromisoformat(ps) if ps else None
        except Exception:
            self.prev_seen = None

    # -- the data key: only with a sign-in (access.py) ----------------------------------------------------------------------
    def unlock(self, key: bytes, how: str) -> None:
        """The data key after a sign-in: the store opens, the settings and the last state are read, the schedule goes on --
        also once the interface locks again (the key stays in memory until the service ends)."""
        with self._open_lock:
            if self.store.is_open:
                return
            self.store.unlock(key)
            try:
                # the settings, the state, the password record (the sign-in reads it right after): all read before any is set
                # aside -- what may pass (the disk, openssl) raises here, with nothing changed
                docs = {n: self.store.read_record(n) for n in ("config.json", "state.json", "auth.json")}
                aside = [self._set_aside(n) for n, (_, why) in docs.items() if why]
                raw, st = docs["config.json"][0], docs["state.json"][0]
                if docs["config.json"][1]:               # the settings are gone: the factory's -- with the access as this service was started
                    raw = {"ui": access.start_settings(self.data_dir)}       # (port, address, certificate, Touch ID, lock)
                cfg = merged_config(raw)
                if aside:
                    if docs["config.json"][1]:
                        self.store.save("config.json", cfg)
                    self.store.update("state.json", lambda cur: cur.__setitem__(DAMAGED_KEY, (cur.get(DAMAGED_KEY) or []) + aside), {})
            except Exception:                            # the settings cannot be read right now (the disk, openssl): locked again, nothing runs on defaults
                self.store.close()
                raise
            self.config = cfg
            self.apply_language()
            self.sessions.set_idle(int(self.config["ui"].get("lock_minutes", 15)))
            self.categories_raw = mm_categories.with_paths(st.get("categories_raw") or [])
            self._read_prev_seen()
            threading.Thread(target=self._load_ledger_cache, name="kontor-cache", daemon=True).start()
            access.write_start(self.data_dir, self.config)
            log.info("Data opened after sign-in (%s) -- schedule and auto bookings go on", how)

    def _set_aside(self, name: str) -> dict:
        """The settings, the state or the password record after a sign-in, damaged for good -- the key is right (access checked
        it), yet the file does not open with it or holds no such record: it must not lock you out for ever. Set aside under
        another name (never deleted, never changed) and noted (the page says so until you restore a backup or close the
        notice); Kontor goes on without it -- the factory settings (nothing books by itself with them), an empty state. Never a
        new key, never a new setup."""
        kept = self.store.set_aside(name)
        log.error("%s does not read after the sign-in -- set aside as %s, going on without it", name, kept)
        return {"file": name, "kept": kept or "", "time": datetime.now().strftime("%Y-%m-%d %H:%M")}

    def settings_lost(self) -> bool:
        """The settings did not read and were set aside, and no backup was restored since: where your receipts and linked
        documents lie is not known for sure."""
        try:
            return any(x.get("file") == "config.json" for x in self.set_aside()) or bool(self.store.read_record("config.json")[1])
        except Exception:                                # neither the state nor the settings read right now: not known
            return True

    def set_aside(self) -> List[dict]:
        """The files that did not read at a sign-in and were set aside (unlock), until the note is closed or a backup restored."""
        st = self.store.load_shared("state.json", {}) or {}
        return [x for x in (st.get(DAMAGED_KEY) or [] if isinstance(st, dict) else []) if isinstance(x, dict)]

    def password_set(self) -> bool:
        if not self.store.encrypted:                     # without encryption (tests only): Kontor's password in its record
            return bool(self.auth_record())
        return access.password_set(self.data_dir)

    def sign_in(self, password: str) -> bool:
        """Kontor's password: opens the data key (the store is locked) or checks it against the key in use."""
        if self.store.is_open:
            return self.check_password(password)
        got = access.unlock_password(self.data_dir, password)
        if got is None:
            return False
        self.unlock(*got)
        self.sync_touchid()
        return True

    def sign_in_touchid(self, demo: bool = False, tid: str = "") -> bool:
        """Touch ID (at the Mac): with the key in memory the macOS window confirms you; otherwise the Secure Enclave's key opens
        the data key -- after Touch ID or the Mac's password. The window says what the sign-in opens (demo: the demo, else your
        data); tid: the sign-in page's request (its window closes when the page switches, touchid_switch)."""
        reason = tr(auth.TOUCHID_REASON_DEMO if demo else auth.TOUCHID_REASON)
        if self.store.is_open:
            return auth.touchid_verify(reason, tid=tid)
        got = access.unlock_touchid(self.data_dir, reason, tid=tid)
        if got is None:
            return False
        self.unlock(*got)
        self.sync_touchid()
        return True

    # The sign-in page's Touch ID request: one at a time. What it opens (the demo or your data) is decided once its window is
    # confirmed -- as the page then wants it, not as it was when the window opened (the page may switch meanwhile).
    def touchid_begin(self, tid: str, demo: bool) -> dict:
        """A new request (tid: its random id; demo: what it opens) -- the one running from now on. One before it is replaced:
        it opens nothing, whatever its window gets, and its window closes."""
        req = {"id": tid, "demo": demo, "switched": False, "over": False}
        with TID_LOCK:
            old, self._tid = self._tid, req
            if old is not None:
                old["over"] = True
        if old is not None:
            auth.touchid_close(old["id"])
        return req

    def touchid_switch(self, tid: str, demo: bool) -> bool:
        """The page switched between the demo and your data while its request runs: confirmed, the request opens that now -- its
        window (which says the other) closes, the page asks anew. Only with the id of the request running."""
        with TID_LOCK:
            req = self._tid
            if req is None or not TID_RE.fullmatch(tid or "") or not secrets.compare_digest(req["id"], tid):
                return False
            if req["demo"] == demo:
                return True
            req["demo"], req["switched"] = demo, True
        auth.touchid_close(tid)
        return True

    def touchid_cancel(self) -> None:
        """Signed in another way (the password): the request running opens nothing, its window closes."""
        with TID_LOCK:
            old, self._tid = self._tid, None
            if old is not None:
                old["over"] = True
        if old is not None:
            auth.touchid_close(old["id"])

    def touchid_end(self, req: dict) -> Tuple[bool, bool, bool]:
        """The request answered: (what it opens now -- the demo?, switched meanwhile, replaced) -- no longer the one running."""
        with TID_LOCK:
            if self._tid is req:
                self._tid = None
            return req["demo"], req["switched"], req["over"]

    def check_password(self, password: str) -> bool:
        """Kontor's password while signed in (something weighty): does it open the key in use?"""
        if not self.store.encrypted:
            rec = self.auth_record()
            return bool(rec) and auth.verify_password(password, rec)
        return access.verify_password(self.data_dir, self.store.master, password)

    def sync_touchid(self) -> None:
        if not self.store.encrypted or not self.store.is_open:
            return
        try:
            access.set_touchid(self.data_dir, self.store.master, self.touchid_on())
        except Exception:
            log.exception("Touch ID's key not set up")

    def first_password(self, password: str) -> None:
        """The first password (setup): the key in use -- or a new one where no data are -- wrapped with it."""
        if self.store.encrypted or not self.store.is_open:
            key = access.setup_key(self.data_dir, self.store)
            opened = not self.store.is_open
            if opened:
                self.unlock(key, "password")
            try:
                if not access.complete(self.data_dir, key, password):
                    raise StoreError(tr("s_schluessel_passt_nicht"))
            except Exception:
                if opened:                               # a key kept nowhere: not used (nothing was written with it)
                    self.store.close()
                raise
        self.store.save("auth.json", auth.with_offline(auth.hash_password(password), password))
        self.sync_touchid()

    def set_password(self, password: str) -> None:
        if self.store.encrypted:
            access.change_password(self.data_dir, self.store.master, password)
        self.store.save("auth.json", auth.with_offline(auth.hash_password(password), password))

    # -- assistant (a language model on this Mac; assistant.py) --------------------------------------------------------------
    @property
    def assistant(self) -> "assistant_mod.Assistant":
        with self._assistant_lock:
            if self._assistant is None:
                self._assistant = assistant_mod.Assistant(self, {
                    "history": lambda uuid: account_history(self, uuid),
                    "history_set": lambda body: account_history_set(self, body),
                    "plan_update": lambda body: plan_update(self, body),
                    "plan_restore": lambda area, parts: plan_restore(self, area, parts),
                    "lock": ENTRY_LOCK,
                    "transactions": lambda q: filter_transactions(self, q)[0],
                    "status": lambda: self.status(True),
                    "receipt_counts": lambda: Belege(self.store, self.config).counts(),
                    "receipt_text": lambda data: receipt_text.text_of(data, self.store.data_dir),
                    "receipt_layout": lambda data: receipt_text.layout_of(data, self.store.data_dir),
                    "receipt_pictures": lambda data: receipt_text.pictures_of(data, self.store.data_dir),
                    "receipt_matches": lambda fields, amount, day, name: receipt_matches(self, fields, amount, day, name),
                    "receipt_place": lambda tid: receipt_place(self, tid),
                    "file_receipt": lambda data, name, tid, note: assistant_file_receipt(self, data, name, tid, note),
                    "unfile_receipt": lambda did: assistant_unfile_receipt(self, did),
                    "categories": lambda: positions_overview(self.ledger, self.config, self.categories_raw, date.today()) if self.ledger is not None else {},
                    "uncategorized": lambda year, area: open_category_items(self, year, area) if self.ledger is not None else {},
                    "category_problem": lambda path: mm_categories.assignable(mm_categories.index(self.categories_raw), path),
                    "category_paths": lambda: sorted(p for p, c in mm_categories.index(self.categories_raw).items()
                                                     if mm_categories.assignable(mm_categories.index(self.categories_raw), p) is None),
                    "approve_bookings": lambda shown: approve_bookings(self, shown),
                    "rule_preview": lambda section, old, new: rule_preview(self, section, old, new),
                    "save_rule": lambda section, old, new: save_assistant_rule(self, section, old, new),
                    "undo_rule": lambda section, old, new: undo_assistant_rule(self, section, old, new),
                    "hold_bookings": lambda keys: hold_back_bookings(self, keys),
                    "restore_bookings": lambda keys: restore_bookings(self, keys),
                    "assign": lambda ids, path, local: assistant_assign_categories(self, ids, path, local),
                    "unassign": lambda ids, path, local: unassign_categories(self, ids, path, local),
                    "own_data": lambda: (self.ledger, self.config, self.dataset(), self.umsatzliste(), self.categories_raw,          # what never goes out in an internet search
                                         {k: (self.store.load("state.json", {}) or {}).get(k) for k in ("last_run", "history")}),         # (bookings waiting, balances typed in)
                    "bookings": lambda: {"made": kontor_bookings(self.ledger)[:500], "held_back": len(self.config.get("not_book") or []),
                                         "runs": list(reversed((self.store.load("state.json", {}) or {}).get("history_source", [])))[:6]}})
            return self._assistant

    def assistant_stop(self) -> None:
        """Ends the assistant's model (before a restart, an uninstall, at the end)."""
        a = getattr(self, "_assistant", None)            # the command line builds an App without its service parts
        if a is not None:
            try:
                a.stop_all()
            except Exception:  # pragma: no cover
                log.exception("Assistant: stop")

    # -- Konfiguration -----------------------------------------------------
    def save_config(self, cfg: dict) -> None:
        new = merged_config(cfg)
        changed = [k for k in sorted(set(new) | set(self.config or {})) if (self.config or {}).get(k) != new.get(k)]
        old_lang = i18n.lang()
        self.config = new
        self.store.save("config.json", self.config)
        log.info("Configuration saved (changed: %s)", ", ".join(changed) or "nothing")
        if any(k in changed for k in RULE_SECTIONS):          # a rule saved: what waits for approval is planned again from it
            replan_waiting(self)
        access.write_start(self.data_dir, self.config)          # what the service needs before the next sign-in
        if "ui" in changed:
            self.sync_touchid()
        self.sessions.set_idle(int(self.config["ui"].get("lock_minutes", 15)))
        self.apply_language()
        if i18n.lang() != old_lang and self.ledger is not None:
            self.request_rebuild("language")          # Hinweise der Auswertung in der neuen Sprache

    def apply_language(self) -> None:
        i18n.set_lang((self.config.get("ui") or {}).get("language") or "de")

    def auth_record(self) -> dict:
        return self.store.load("auth.json", {}) or {}

    def categories(self) -> List[dict]:
        out = []
        for c in self.categories_raw:
            b = c.get("budget") if isinstance(c.get("budget"), dict) else None
            out.append({"name": c.get("name"), "path": str(c.get("path") or c.get("name") or "").replace("\\", " / "),
                        "raw": str(c.get("path") or c.get("name") or ""),
                        "group": bool(c.get("group", False)), "depth": int(c.get("indentation") or 0),
                        "default": bool(c.get("default", False)), "budget": b if b and b.get("amount") else None})
        return out

    def touchid_on(self) -> bool:
        return bool((self.config.get("ui") or {}).get("touchid", True))

    def config_has_rules(self) -> bool:
        c = self.config
        return bool(c.get("loans") or c.get("companies") or c.get("areas") or c.get("real_estate"))

    # -- MoneyMoney-Stand zwischenspeichern ---------------------------------
    def _load_ledger_cache(self) -> None:
        """Nach einem Neustart den letzten MoneyMoney-Stand aus dem (verschluesselten) Zwischenspeicher laden, damit
        Auswertungen und Verlauf sofort gehen -- auch wenn MoneyMoney gerade gesperrt oder geschlossen ist."""
        t0 = time.time()
        try:
            raw = self.store.read_bytes("moneymoney-ledger.bin")
            if not raw:
                return
            ledger, saved = ledger_from_bytes(raw)
        except Exception as e:
            log.info("MoneyMoney cache unusable (%s) -- recreated on next read", e)
            return
        with self.lock:
            if self.ledger is None:
                self.ledger, self.ledger_time, self.ledger_from_cache = ledger, saved or datetime.now(), True
                self.ledger_cache_fp = ledger_fp(ledger)
        log.info("MoneyMoney data from %s loaded from cache: %d accounts, %d transactions (%.1f s)",
                 (saved.strftime("%Y-%m-%d %H:%M") if saved else "?"), len(ledger.accounts), len(ledger.txs), time.time() - t0)
        # Ohne erreichbares MoneyMoney liest der Zeitplaner nichts: Auswertung einmal im Hintergrund bauen, damit Zwischen-
        # ergebnisse (Kategorien, Zahlungsstroeme) bereitliegen und die erste Aenderung nach einem Neustart schnell geht
        if self.store.exists("dataset.json") and (not is_running() or self.moneymoney_gesperrt(max_age=0) is not False):
            self.request_rebuild("start")

    def _save_ledger_cache(self, ledger: Ledger, force: bool = False) -> None:
        fp = ledger_fp(ledger)
        if fp == self.ledger_cache_fp and not force:
            return
        self.ledger_cache_fp = fp

        def work():
            t0 = time.time()
            try:
                self.store.write_bytes("moneymoney-ledger.bin", ledger_to_bytes(ledger, self.ledger_time))
                log.debug("MoneyMoney data cached (%.1f s)", time.time() - t0)
            except Exception as e:  # pragma: no cover
                log.warning("MoneyMoney data not cached: %s", e)
        threading.Thread(target=work, name="kontor-cache-save", daemon=True).start()

    def take_categories(self, cats: list) -> bool:
        """MoneyMoney's categories as just read. True when the tree changed (one added, deleted, renamed, moved): the list the
        next read compares with is stored -- also when nothing else changed -- and what you set for a category follows it."""
        old = self.categories_raw
        self.categories_raw = cats
        if category_tree(old) == category_tree(cats):
            return False
        self.store.update("state.json", lambda st: st.__setitem__("categories_raw", cats), {})
        cfg = follow_categories(self.config, old, cats)
        if cfg is not None:
            self.save_config(cfg)
            log.info("Categories changed in MoneyMoney: settings followed")
        return bool(old)

    def set_ledger(self, ledger: Ledger, reuse: bool = False) -> None:
        """Neuen MoneyMoney-Stand uebernehmen. reuse=True: sind die Daten unveraendert, bleibt der bisherige Stand mit seinen
        Zwischenergebnissen (Kategorien, Zahlungsstroeme) in Gebrauch -- nur der Lesezeitpunkt wird aktualisiert."""
        old = self.ledger
        if old is not None and old is not ledger and getattr(old, "_paired", None) and not getattr(ledger, "_paired", None):
            ledger._paired = dict(old._paired)             # Kategorien -> Zuordnen: transfers stay out until the report is rebuilt
        if reuse and old is not None and old is not ledger:
            try:
                same = self.ledger_cache_fp is not None and ledger_fp(ledger) == self.ledger_cache_fp
            except Exception:  # pragma: no cover
                same = False
            if same:
                self.ledger_time, self.ledger_from_cache = datetime.now(), False
                log.debug("MoneyMoney data unchanged -- intermediate results kept")
                for u, a in ledger.accounts.items():          # Abrufzeiten der Banken (zaehlen nicht zum Fingerabdruck) aktuell halten
                    if u in old.accounts:
                        old.accounts[u].refresh = a.refresh
                newer = getattr(ledger, "full_at", None)
                if newer and (getattr(old, "full_at", None) is None or old.full_at < newer):
                    old.full_at, old.since = newer, getattr(ledger, "since", None)
                    self._save_ledger_cache(old, force=True)     # Zeitpunkt des vollstaendigen Lesens auch nach Neustart
                return
        self.ledger, self.ledger_time, self.ledger_from_cache = ledger, datetime.now(), False
        self._save_ledger_cache(ledger)

    def _freeze_assignments(self) -> None:
        if self.ledger is None:
            return
        try:
            new = freeze_assignments(self.ledger, self.config)
        except Exception:  # pragma: no cover
            log.exception("Freezing assignments")
            return
        if new is not None:
            self.save_config(new)
            log.info("Position and history source of confirmed accounts frozen (previously automatic)")

    def historie_einlesen(self, buf: bytearray) -> None:
        """Hintergrund: Kontostand-Verlauf aller Konten aus der hochgeladenen MoneyMoney-Datenbank uebernehmen.
        Der Puffer wird in jedem Fall ueberschrieben; gespeichert werden nur Monatsend-Staende (verschluesselt)."""
        def step(t: str) -> None:
            self.mmh["step"] = t
        res: dict
        aufbau = os.path.join(HERE, "mm-history-schema.txt")
        try:
            ledger = self.ledger
            if ledger is None:
                raise mm_history.HistorieError(tr("s_erst_die_konten_aus_moneymoney"))
            accounts = {a.uuid: {"balance_amount": a.balance, "depot": a.portfolio, "iban": a.iban, "number": a.account_number, "sort_code": a.bank_code,
                                 "name": a.name, "currency": a.currency} for a in ledger.accounts.values() if not a.group}
            found, tables, fmt = mm_history.run(buf, accounts, date.today(), step=step, balance_at=balance_lookup(ledger),
                                                since=earliest_needed(self.config, date.today()))
            if not found or not found["accounts"]:
                with open(aufbau, "w", encoding="utf-8") as f:       # nur Tabellen-/Spaltennamen, keine Inhalte
                    f.write(mm_history.schema_text(tables, fmt))
                log.info("MoneyMoney database read (%s, %d tables), balances not recognized", fmt, len(tables))
                res = {"ok": False, "text": tr("s_die_kontostaende_wurden_in_der")}
            else:
                konten = found["accounts"]
                monate = sorted({mk for v in konten.values() for mk in v})
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.store.save(MM_HISTORY_FILE, {"as_of": now, "accounts": konten, "opening": found.get("opening") or {},
                                                  "securities": found.get("securities") or {}})   # replaces the previous state
                meta = {"time": now, "accounts": len(konten), "amounts": sum(len(v) for v in konten.values()),
                        "depots": sum(1 for u in konten if u in ledger.accounts and ledger.accounts[u].portfolio),
                        "date_from": monate[0] if monate else None, "date_to": monate[-1] if monate else None}
                self.store.update("state.json", lambda cur: cur.__setitem__("mm_history_src", meta), {})
                if os.path.exists(aufbau):
                    os.remove(aufbau)
                log.info("Balances imported from MoneyMoney (%s): %d accounts, %d monthly values (check %d/%d)",
                         fmt, meta["accounts"], meta["amounts"], found["hits"], found["verified"])
                self.request_rebuild("balances from MoneyMoney")
                res = dict(meta, ok=True)
        except mm_history.HistorieError as e:
            if str(e) != "aborted":
                log.info("MoneyMoney database not read: %s", str(e)[:120])
            res = {"ok": False, "text": tr("s_abgebrochen") if str(e) == "aborted" else str(e)}
        except Exception:  # pragma: no cover
            log.exception("Balances from MoneyMoney")
            res = {"ok": False, "text": tr("s_unerwarteter_fehler_details_im_protoko")}
        finally:
            mm_history._wipe(buf)
        self.mmh = {"running": False, "step": None, "result": res}

    def _rebuild_now(self) -> Tuple[bool, Optional[str]]:
        """Bericht aus dem letzten bekannten Stand neu bauen (synchron; nur aus dem Hintergrund-Thread aufrufen)."""
        def progress(f: float, text: str) -> None:
            self.bericht_fortschritt = {"share": round(f, 2), "step": text}
        if self.ledger is None:
            progress(0.02, tr("s_moneymoney_wird_gelesen"))
            ledger, err = self.refresh_ledger()
            if ledger is None:
                return False, err
        self._freeze_assignments()
        t0 = time.time()
        progress(0.03, tr("s_wartet_auf_laufenden_abgleich"))
        with REPORT_LOCK:       # one report at a time (dataset.json); a run (reading, rules, booking) goes on beside it
            st = self.store.load("state.json", {}) or {}
            try:
                warn = list((st.get("last_run") or {}).get("warnings") or [])       # the notes of the last run stay in the report
                ds = build_report(self.store, self.ledger, self.config, st, date.today(), warn, self.categories_raw, progress)
                self.umsaetze = ds.pop("_transactions", None)
            except Exception as e:  # pragma: no cover
                log.exception("Report from last data failed")
                return False, tr("s_bericht_fehlgeschlagen_s") % e
            # nur die Monats-Schnappschuesse zurueckschreiben -- Verlauf-Eingaben, die waehrend des Baus kamen, bleiben erhalten
            self.store.update("state.json", lambda cur: (merge_snapshots(cur, st.get("snapshots") or {}), merge_holdings(cur, st)), {})
        log.info("Report rebuilt from last data (%.1f s)", time.time() - t0)
        return True, None

    def _rebuild_worker(self) -> None:
        while True:
            with self.rebuild_cv:
                if not self.rebuild_pending:
                    self.rebuild_running = False
                    self.rebuild_cv.notify_all()
                    return
                self.rebuild_pending = False
                reasons, self.rebuild_reasons = self.rebuild_reasons, []
            t0 = time.time()
            log.debug("Rebuilding report (%s)", ", ".join(reasons) or "requested")
            try:
                ok, err = self._rebuild_now()
            except Exception as e:      # anything unexpected (disk full, a file that does not open): said in the report; the worker goes on
                log.error("Report rebuild failed: %s", e, exc_info=True)
                ok, err = False, str(e)[:300]
            with self.rebuild_cv:
                self.bericht = {"as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "duration": round(time.time() - t0, 1),
                                "error": None if ok else err, "reason": ", ".join(reasons)}
                self.rebuild_cv.notify_all()

    def request_rebuild(self, grund: str = "") -> None:
        """Berichtsneubau anstossen (kehrt sofort zurueck). Mehrere Anstoesse waehrend eines Laufs ergeben genau einen weiteren Lauf."""
        with self.rebuild_cv:
            self.rebuild_pending = True
            if grund and grund not in self.rebuild_reasons:
                self.rebuild_reasons.append(grund)
            if not self.rebuild_running:
                self.rebuild_running = True
                threading.Thread(target=self._rebuild_worker, name="kontor-report", daemon=True).start()

    def rebuild_report(self, wait: bool = False, grund: str = "", timeout: float = 600.0):
        """Neubau anstossen. wait=True wartet auf das Ergebnis und liefert (ok, fehler); sonst ('angefordert', None)."""
        self.request_rebuild(grund)
        if not wait:
            return "requested", None
        with self.rebuild_cv:
            self.rebuild_cv.wait_for(lambda: not self.rebuild_running and not self.rebuild_pending, timeout=timeout)
            b = self.bericht
        return (b.get("error") is None and b.get("as_of") is not None), b.get("error")

    def securities_known(self) -> Tuple[dict, dict, dict]:
        st = self.store.load_shared("state.json", {}) or {}
        mmh = self.store.load_shared(MM_HISTORY_FILE, {}) or {}
        return st, mmh, security_names.catalog(mmh.get("securities") or {}, st.get("sec_names") or {})

    def securities_unnamed(self) -> dict:
        """Securities that have only an ISIN (no name in MoneyMoney) and the list of all securities with their names: MoneyMoney's,
        looked up, your own."""
        st, mmh, known = self.securities_known()
        done = st.get("sec_search") or {}
        found, own = done.get("names") or {}, done.get("own") or {}
        offen = security_names.unnamed(mmh.get("securities") or {}, st.get("snapshots_sec") or {}, st.get("sec_names") or {},
                                       list(found) + list(done.get("without") or []) + list(own))
        liste = [{"isin": i, "mm": known.get(i, ""), "looked_up": found.get(i, ""), "own_name": own.get(i, "")} for i in set(known) | set(found)]
        liste.sort(key=lambda x: ((x["own_name"] or x["mm"] or x["looked_up"] or "~").lower(), x["isin"]))
        return {"open": offen, "found": len(found), "without": len(done.get("without") or []), "time": done.get("time"), "list": liste,
                "from_mm": sum(1 for x in liste if x["mm"])}

    def securities_lookup(self) -> dict:
        """Look up the names of the securities without one (only on request): sends only their ISINs to OpenFIGI."""
        offen = self.securities_unnamed()["open"]
        names = security_names.lookup(offen) if offen else {}
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        def upd(cur: dict) -> None:
            w = cur.setdefault("sec_search", {})
            w["time"] = now
            w.setdefault("names", {}).update(names)
            w["without"] = sorted((set(w.get("without") or []) | set(offen)) - set(w["names"]))
        self.store.update("state.json", upd, {})
        log.info("Security names: %d ISINs looked up, %d names found", len(offen), len(names))
        return {"sent": len(offen), "new": len(names)}

    # -- prices: the balance sheet in today's purchasing power (price_index.py) ----------------------------------------------
    def price_state(self) -> dict:
        st = (self.store.load_shared("state.json", {}) or {}).get(price_index.STATE)
        return st if isinstance(st, dict) else {}

    def price_factors(self, area: str, months: List[str], base: str) -> dict:
        """Per month the factor into the money of month base -- the index as Kontor knows it, after its last month the area's
        inflation of Planung -- and what the page says about it (until when the index is known, when it was fetched)."""
        st = self.price_state()
        res = price_index.factors(price_index.known(st), months, base, price_index.rate_of(self.plan_for(area)))
        res.update(fetched=str(st.get("fetched") or "") if price_index.counts(st) else "", bundled=price_index.BUNDLED_AS_OF)
        return res

    def price_refresh_soon(self) -> None:
        """Newer months of the index when it is time (price_index.due): one try in the background. Only asked while the page
        shows the balance sheet in today's money; never in the demo."""
        if self.DEMO or not self.store.is_open or not price_index.due(self.price_state(), date.today(), time.time()):
            return
        with self._price_lock:
            if self._price_busy:
                return
            self._price_busy = True
        threading.Thread(target=self._price_refresh, name="kontor-prices", daemon=True).start()

    def _price_refresh(self) -> None:
        try:
            # through the sealed reader of the internet search, always in the Mac's sandbox
            reader = self.price_reader or web_search.Reader(self.data_dir, lambda: "strict")
            st = price_index.refresh(reader, self.price_state(), date.today(), time.time())
            self.store.update("state.json", lambda cur: cur.__setitem__(price_index.STATE, st), {})
        except Exception:                                # (signed out meanwhile, the disk): the next look tries again
            log.exception("Prices: refresh failed")
        finally:
            with self._price_lock:
                self._price_busy = False

    def bericht_status(self) -> dict:
        with self.rebuild_cv:
            laeuft = self.rebuild_running or self.rebuild_pending
            return {"running": laeuft, **self.bericht, "progress": self.bericht_fortschritt if laeuft else None}

    def moneymoney_gesperrt(self, max_age: float = 45.0) -> Optional[bool]:
        """Ist MoneyMoney gesperrt? Kurzer Lesezugriff auf die Kontenliste, hoechstens alle max_age Sekunden; None = laeuft nicht."""
        if not is_running():
            return None
        ts, val = self.mm_probe
        if time.time() - ts < max_age:
            return val
        try:
            b = self.bridge_factory(True); b.quiet = True          # a quick check: no lines in the log
            b.export_accounts()
            val = False
        except MoneyMoneyError as e:
            val = "gesperrt" in str(e).lower() or "locked" in str(e).lower() or None
        except Exception:  # pragma: no cover
            val = None
        self.mm_probe = (time.time(), val)
        return val

    # -- Zugriff von anderen Geraeten (iPhone ueber Tailscale) --------------
    def remote_readonly(self) -> bool:
        """Von unterwegs nur ansehen (Standard): Aenderungen nur am Mac."""
        return bool((self.config.get("ui") or {}).get("remote_read_only", True))

    def passkey_site(self) -> Optional[Tuple[str, str]]:
        """(rpId, origin) for passkeys: the Mac's name in the Tailscale network and Kontor's https address there -- only while
        the access from other devices runs with its certificate (a passkey needs https and a name). None otherwise."""
        ui = self.config.get("ui") or {}
        if not (ui.get("tls_cert") and ui.get("tls_key")) or (ui.get("bind") or "127.0.0.1") == "127.0.0.1":
            return None
        host = os.path.basename(str(ui["tls_cert"]))[:-4].lower()
        if not webauthn.RP_ID.fullmatch(host):
            return None
        return host, webauthn.origin_of(host, int(ui.get("port") or 8765))

    def exposure(self) -> dict:
        """The last look at Tailscale (tls_cert.exposure) -- never waits: {"serve": "pending" (not looked yet since the start),
        "off" (no Tailscale running on this Mac), "none", "serve", "funnel" or "unknown" (never got an answer), "lock", "at",
        "failed" (looks in a row without an answer)}."""
        return self.__dict__.get("_exposure") or {"serve": "pending", "lock": None, "at": 0.0, "failed": 0}

    def exposure_tick(self, fresh: bool = False) -> None:
        """Looks at Tailscale anew in the background: at the start (serve), then when the last look is older than
        EXPOSURE_SECONDS -- after a look without an answer sooner (EXPOSURE_RETRY, a few times). fresh: now."""
        if self.DEMO:
            return
        with EXPOSURE_CV:
            cur = self.exposure()
            since = time.time() - self.__dict__.setdefault("_exposure_start", time.time())
            if cur.get("serve") == "pending" and since >= EXPOSURE_FIRST:
                # no answer in time since the start: "unknown" (locks nothing; the looks go on, an answer replaces it -- found
                # passed on, every session at this Mac ends). Signing in never waits for Tailscale's timeouts.
                log.error("Tailscale gave no answer within %d s of the start -- whether it passes Kontor's port on is not known", EXPOSURE_FIRST)
                cur = self.__dict__["_exposure"] = dict(cur, serve="unknown", at=cur.get("at", 0.0))
                EXPOSURE_CV.notify_all()
            failed = int(cur.get("failed") or 0)
            young = since < EXPOSURE_YOUNG     # (Tailscale may start after Kontor)
            wait = EXPOSURE_RETRY if 0 < failed < EXPOSURE_TRIES or cur.get("serve") == "pending" or young else EXPOSURE_SECONDS
            if self.__dict__.get("_exposure_running") or (not fresh and time.time() - cur.get("at", 0.0) < wait):
                return
            self.__dict__["_exposure_running"] = True
        threading.Thread(target=self._exposure_run, name="kontor-exposure", daemon=True).start()

    def _exposure_run(self) -> None:
        import tls_cert
        got = None
        try:
            got = tls_cert.exposure(int((self.config.get("ui") or {}).get("port") or 8765), self.own_names())
        except Exception as e:  # pragma: no cover - a look without an answer
            log.warning("Tailscale not checked (%s)", type(e).__name__)
        finally:
            self._exposure_set(got, running=False)

    def own_names(self) -> List[str]:
        """This Mac's names and addresses beyond 127.0.0.1 (for tls_cert.exposure): its address and name in the Tailscale
        network (the address Kontor listens on, its certificate, Tailscale's last state) and its host name."""
        ui = self.config.get("ui") or {}
        ts = self._ts_cache[1] if isinstance(getattr(self, "_ts_cache", None), tuple) and isinstance(self._ts_cache[1], dict) else {}
        node = os.uname().nodename.lower()
        names = [str(ui.get("bind") or ""), os.path.basename(str(ui.get("tls_cert") or ""))[:-4], str(ts.get("name") or ""), str(ts.get("ip") or ""),
                 node, node.split(".")[0] + ".local"]
        return [n for n in names if n]

    def _exposure_set(self, got: Optional[dict], running: Optional[bool] = None) -> dict:
        """A look at Tailscale taken in: an answer replaces what was known; a look without one (Tailscale runs, but did not
        answer) never does -- the last known state holds (passed on stays passed on); never known since the start: locked
        until EXPOSURE_TRIES looks in a row went without an answer, then "unknown" (nobody is locked out for good). Found
        passed on (it was not before): every session signed in at this Mac's own address ends -- it may have come from elsewhere."""
        serve = (got or {}).get("serve")
        with EXPOSURE_CV:
            prev = self.exposure()
            if serve in ("off", "none", "serve", "funnel"):
                new = {"serve": serve, "lock": got.get("lock"), "at": time.time(), "failed": 0}
            else:
                failed = int(prev.get("failed") or 0) + 1
                keep = prev.get("serve")
                if keep == "pending" and failed >= EXPOSURE_TRIES:
                    keep = "unknown"
                lock = (got or {}).get("lock")
                new = dict(prev, serve=keep, failed=failed, at=time.time(), lock=lock if lock is not None else prev.get("lock"))
            self.__dict__["_exposure"] = new
            if running is not None:
                self.__dict__["_exposure_running"] = running
            EXPOSURE_CV.notify_all()
        was, now = prev.get("serve") in ("serve", "funnel"), new["serve"] in ("serve", "funnel")
        if now and not was:
            log.error("Tailscale passes Kontor's port on (%s) -- sign-in and what stays at the Mac are refused from this Mac until it is off", new["serve"])
            self.end_mac_sessions()
        elif new["serve"] == "unknown" and prev.get("serve") == "pending":
            log.error("Tailscale gave no answer to %d looks -- whether it passes Kontor's port on is not known", new["failed"])
        return new

    def end_mac_sessions(self) -> int:
        """Every session signed in at this Mac's own address (127.0.0.1) ends -- also the demo's -- and a Touch ID window still
        open opens nothing: with "tailscale serve"/Funnel any of them may have come from elsewhere."""
        n = self.sessions.drop_loopback()
        d = self._demo_box.current()[0] if self._demo_box is not None else None        # (none started: none made for it)
        if d is not None:
            n += d.sessions.drop_loopback()
        self.touchid_cancel()
        if n:
            log.warning("%d session(s) signed in at this Mac ended -- sign in again once Tailscale passes nothing on", n)
        return n

    def exposure_block(self, wait: float = 0.0) -> Optional[str]:
        """Why sign-in and what stays at the Mac are refused from this Mac's address right now: "exposed" (serve/Funnel passes
        Kontor's port on), else None. Right after a start (not looked yet) it waits for the first look up to wait seconds, at most
        until EXPOSURE_WAIT seconds after the start, then
        lets it go (user, 2026-11-23: Kontor must work without Tailscale; a sign-in needs the password or Touch ID anyway, and
        a look that finds the port passed on ends every session at this Mac at once)."""
        self.exposure_tick()
        # counted from the start, not from each request (user, 2026-11-24): the first look began with the service -- a page that
        # comes back after an update finds its sign-in, Touch ID and the look at the session at once, not each 2 s later
        wait = min(wait, self.__dict__.get("_exposure_start", time.time()) + EXPOSURE_WAIT - time.time())
        if wait > 0 and self.exposure().get("serve") == "pending":
            until = time.time() + wait
            with EXPOSURE_CV:
                while self.exposure().get("serve") == "pending" and time.time() < until:
                    EXPOSURE_CV.wait(max(0.01, until - time.time()))
        serve = self.exposure().get("serve")
        return "exposed" if serve in ("serve", "funnel") else None

    def exposed(self) -> bool:
        """"tailscale serve" or Funnel passes Kontor's port on (the red note under Zugang)."""
        self.exposure_tick()
        return self.exposure().get("serve") in ("serve", "funnel")

    def remote_acl(self, fresh: bool = False) -> dict:
        """What Tailscale lets in on this Mac, Tailnet Lock and serve/Funnel -- one look at a time, kept 30 s (fresh: anew)."""
        import tls_cert
        with ACL_LOCK:
            hit = self.__dict__.get("_acl")
            if hit and not fresh and time.time() - hit[0] < 30:
                return dict(hit[1], exposure=self.exposure())
            port = int((self.config.get("ui") or {}).get("port") or 8765)
            got = dict(tls_cert.access_check(port))
            seen = self._exposure_set(tls_cert.exposure(port, self.own_names()))
            self.__dict__["_acl"] = (time.time(), got)
            return dict(got, exposure=seen)

    def passkey_only(self) -> bool:
        """Sign-in from other devices only with an added iPhone's passkey (while the data are open) -- devices.py."""
        return bool(self.devices is not None and self.store.is_open and self.devices.passkey_only())

    def remote_changes(self) -> bool:
        """Changes from an added iPhone (each with Face ID) -- the setting "Änderungen vom iPhone" (ui.remote_read_only off)."""
        return not self.remote_readonly()

    def offline_copy(self) -> bool:
        """Darf das iPhone die zuletzt geladenen Daten fuer die Offline-Ansicht behalten?"""
        return bool((self.config.get("ui") or {}).get("offline_copy", True))

    def tailscale(self, fresh: bool = False) -> dict:
        """Tailscale state (tls_cert.status). Older than 30 s: answer with the last state and refresh in the background, so a
        page never waits for Tailscale; fresh=True (or nothing known yet) asks right away."""
        import tls_cert
        t0, st = self._ts_cache
        if fresh or not t0:
            st = tls_cert.status()
            self._ts_cache = (time.time(), st)
        elif time.time() - t0 > 30 and not getattr(self, "_ts_refreshing", False):
            self._ts_refreshing = True

            def refresh():
                try:
                    self._ts_cache = (time.time(), tls_cert.status())
                finally:
                    self._ts_refreshing = False
            threading.Thread(target=refresh, daemon=True).start()
        return st

    def remote_info(self) -> dict:
        ui = self.config.get("ui") or {}
        bind = (ui.get("bind") or "127.0.0.1").strip()
        port = int(ui.get("port") or 8765)
        ts = self.tailscale()
        tls = bool(ui.get("tls_cert") and ui.get("tls_key"))
        exp = None
        if tls:
            import tls_cert
            e = tls_cert.cert_expiry(ui["tls_cert"])
            exp = e.date().isoformat() if e else None
        host = (os.path.basename(ui.get("tls_cert") or "")[:-4] if tls else "") or bind
        return {"active": bind != "127.0.0.1", "address": bind, "port": port, "tls": tls, "valid_until": exp,
                "url": ("https://%s:%d/" % (host, port)) if tls else ("http://%s:%d/" % (bind, port)) if bind != "127.0.0.1" else None,
                "listening": bool(self.remote_listening), "error": self.remote_error,
                "read_only": self.remote_readonly(), "offline_copy": self.offline_copy(), "tailscale": ts,
                "passkeys": self.passkey_site() is not None, "passkey_only": self.passkey_only(),
                "devices": len(self.devices.all()) if self.devices is not None else 0}

    def request_restart(self, why: str = "new access settings") -> None:
        """Dienst neu starten (neue Adresse/Zertifikat, ein anderes Python), kurz nachdem die Antwort raus ist. Nur im echten Dienst."""
        if self.restart_allowed:
            log.info("Restarting service for %s", why)
            threading.Timer(1.5, restart_process).start()

    # -- Kontor's own Python (pyruntime.py; which one serves is decided at the start: pyboot.py) ------------------------------------
    @property
    def python(self) -> "pyruntime.Runtime":
        rt = getattr(self, "_python", None)
        if rt is None:
            rt = self._python = pyruntime.Runtime(self.program_dir)
            rt.on_switch = lambda: self.request_restart("another Python")
        return rt

    def python_hint(self) -> str:
        """What there is to do about Python, for the overview: "failed" (the own one did not start), "newer" (Kontor names a
        newer build than the one loaded), "old" (the Mac's own gets no security fixes and you have not said to keep it) -- or ""."""
        try:
            st = self.python.status()
        except Exception:  # pragma: no cover - a note only
            return ""
        if st["failed"]:
            return "failed"
        if st["newer"]:
            return "newer"
        return "old" if st["supported"] and st["running"]["ended"] and not st["use"] else ""

    def components(self) -> list:
        """Everything foreign Kontor uses, for Einstellungen -> Updates (components.py): the Python it runs in, llama.cpp and
        the models on this Mac, what macOS brings along. Without the assistant (not there, the data locked): the rest."""
        try:
            a = self.assistant
            ai, sandbox = a.ai, a.settings()["sandbox"]
        except Exception:
            ai, sandbox = None, "strict"
        return components.listing(self.python.status(), ai, sandbox, self.program_dir)

    def remote_retry(self) -> None:
        bind = ((self.config.get("ui") or {}).get("bind") or "127.0.0.1").strip()
        if bind != "127.0.0.1" and not self.remote_listening and self._handler is not None and time.time() - self.remote_tried >= 60:
            self.start_remote()

    def start_remote(self) -> None:
        """Zweiten Zugang auf der eingestellten Tailscale-Adresse oeffnen (mit TLS, wenn ein Zertifikat eingetragen ist).
        Klappt das nicht (Tailscale noch nicht verbunden), versucht es der Zeitplaner jede Minute erneut."""
        ui = self.config.get("ui", {}) or {}
        extra = (ui.get("bind") or "127.0.0.1").strip()
        self.remote_tried = time.time()
        if self._handler is None or extra == "127.0.0.1" or self.remote_listening:
            return
        if not bind_allowed(extra) or ipaddress.ip_address(extra).is_loopback:
            self.remote_error = tr("s_adresse_s_nicht_erlaubt_nur") % extra
            return
        port = int(ui.get("port") or 8765)
        try:
            srv2 = _Server((extra, port), self._handler)
        except OSError as e:
            if self.remote_error != str(e):
                log.error("Address %s:%d not usable (%s) -- is Tailscale connected? Retrying every minute", extra, port, e)
            self.remote_error = str(e)
            return
        scheme = "http"
        if ui.get("tls_cert") and ui.get("tls_key"):
            try:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                ctx.load_cert_chain(ui["tls_cert"], ui["tls_key"])
                # the handshake in the request's own thread (with its time limit): a connection that says nothing must not hold
                # up everyone else in accept()
                srv2.socket = ctx.wrap_socket(srv2.socket, server_side=True, do_handshake_on_connect=False)
                self.tls_ctx = ctx
                scheme = "https"
            except (OSError, ssl.SSLError) as e:
                log.error("TLS not enabled (%s) -- continuing without TLS", e)
        self.remote_listening, self.remote_error = (scheme, extra), None
        log.info("Access for other devices at %s://%s:%d/", scheme, extra, port)
        threading.Thread(target=srv2.serve_forever, daemon=True).start()

    # -- MoneyMoney --------------------------------------------------------
    def full_read_days(self) -> int:
        return max(1, int((self.config.get("schedule") or {}).get("full_read_days", 30) or 30))

    def full_read_due(self, now: Optional[datetime] = None) -> bool:
        """Read all transactions when the last full read is at least N days old (setting, default 7). In between the quick
        read checks every balance and reads everything at once if older transactions changed (core.unexplained_balances)."""
        b = self.ledger
        fa = getattr(b, "full_at", None) if b is not None else None
        if fa is None:
            return True
        return ((now or datetime.now()) - fa).total_seconds() >= self.full_read_days() * 86400

    def full_read_info(self) -> dict:
        fa = getattr(self.ledger, "full_at", None) if self.ledger is not None else None
        return {"last": fa.strftime("%Y-%m-%d %H:%M") if fa else None, "days": self.full_read_days()}

    def refresh_ledger(self, full: Optional[bool] = None) -> Tuple[Optional[Ledger], Optional[str]]:
        """MoneyMoney lesen. Der Fortschritt (Schritt, Beginn, Dauer der Schritte beim letzten Mal) steht in self.read_state."""
        t0 = time.time()
        st = self.store.load_shared("state.json", {}) or {}
        self.read_state = {"running": True, "step": None, "since": t0, "start": t0, "duration": dict(st.get("read_duration") or {})}
        took: Dict[str, float] = {}

        def step(name: str) -> None:
            now = time.time()
            if self.read_state.get("step"):
                took[self.read_state["step"]] = round(now - self.read_state["since"], 2)
            self.read_state.update(step=name, since=now)
        try:
            b = self.bridge_factory(True)
            step("categories")
            cats = None
            try:                                      # first: a changed category tree means older transactions are read again
                cats = mm_categories.with_paths(b.export_categories())
            except MoneyMoneyError:
                pass
            moved = cats is not None and bool(self.categories_raw) and category_tree(self.categories_raw) != category_tree(cats)
            ledger = fetch(b, self.config, date.today(), with_portfolio=True, progress=step, base=self.ledger,
                           full=True if moved else (self.full_read_due() if full is None else full))
            log.info("MoneyMoney read (%.1f s)", time.time() - t0)
            if cats is not None:                      # taken over only now: had the read failed, the next one sees the change again
                self.take_categories(cats)
            step("save")
            self.set_ledger(ledger, reuse=True)
            self._baseline(ledger)
            step("done")
            self.store.update("state.json", lambda st: st.__setitem__("read_duration", took), {})
            return self.ledger, None
        except MoneyMoneyError as e:
            log.warning("MoneyMoney not readable: %s", e)
            return None, unavailable_text(e) or (tr("s_moneymoney_fehler_s") % e)
        finally:
            self.read_state["running"] = False

    def do_run(self, dry: Optional[bool], force: bool, with_report: bool = True, full: Optional[bool] = None,
               approve: Optional[Dict[str, dict]] = None, write: bool = True) -> dict:
        """A sync (dry: test run; None: as set). write=False (a test run asked for from another device): nothing goes into
        MoneyMoney -- not even the waiting category assignments (they go with the next sync at the Mac)."""
        with self.lock:
            if self.running:
                return {"status": "already_running", "text": tr("s_ein_abgleich_laeuft_bereits")}
            self.running = True
        try:
            d = self.config.get("dry_run", True) if dry is None else dry
            self._freeze_assignments()
            t0 = time.time()
            log.info("Run started (%s%s%s)", "dry run" if d else "live", ", forced" if force else "", ", without report" if not with_report else "")
            full = self.full_read_due() if full is None else full

            def step(name: str, n: int, of: int) -> None:
                self.run_step = {"step": name, "n": n, "date_from": of}
            # the report follows in the background: the bookings and the approval list are there at once
            res = run_once(self.store, self.config, date.today(), d, force, self.bridge_factory, with_report, base=self.ledger, full=full,
                           approve=approve, report=False, progress=step)
            log.info("Run finished: %s (%.1f s)", res.get("status") or "?", time.time() - t0)
            self.last_run_at = time.time()
            ledger = res.pop("_ledger", None)
            if ledger is not None:                        # the state in MoneyMoney (the report shows the planned bookings)
                ledger = ledger.without_planned(res.pop("_booked", None) or ())
            cats = res.pop("_categories", None)
            ums = res.pop("_transactions", None)
            if ums is not None:
                self.umsaetze = ums
            if ledger is not None:
                self.set_ledger(ledger, reuse=res.get("status") == "unchanged")
                self._baseline(ledger)
            if cats:
                self.take_categories(cats)
            if res.get("status") in ("ok", "error") and with_report:
                self.request_rebuild("after approval" if approve is not None else "after sync")   # the figures follow
            self.last_result = res
            try:
                if write or not d:
                    self.flush_pending_categories()
            except Exception:  # pragma: no cover
                log.exception("Pending categories")
            return res
        except Exception as e:  # pragma: no cover - letzte Sicherung, damit der Dienst weiterlaeuft
            log.exception("Run failed")
            self.last_result = {"status": "error", "text": tr("s_unerwarteter_fehler_s") % e}
            return self.last_result
        finally:
            self.running, self.run_step = False, None

    def refresh_bookings(self) -> dict:
        """Only what the approval list depends on, quicker than a whole sync: the accounts the rules read or book are read again
        and the rules planned (a dry run: nothing is written, no report)."""
        with self.lock:
            if self.running:
                return {"status": "already_running", "text": tr("s_ein_abgleich_laeuft_bereits")}
            self.running = True
        try:
            base = self.ledger
            if base is None:
                return {"status": "error", "text": tr("s_noch_kein_stand_aus_moneymoney")}
            t0 = time.time()
            uuids = rule_accounts(base, self.config)
            try:
                led = refresh_accounts(self.bridge_factory(True), base, self.config, date.today(), uuids)
            except MoneyMoneyError as e:
                log.info("Approval list not refreshed: %s", str(e)[:120])
                return {"status": "unavailable", "text": unavailable_text(e) or (tr("s_moneymoney_fehler_s") % e)}
            res = run_once(self.store, self.config, date.today(), True, True, self.bridge_factory, with_report=False,
                           report=False, ledger=led)
            ledger = res.pop("_ledger", None)
            if ledger is not None:
                self.set_ledger(ledger.without_planned())
            for k in ("_categories", "_transactions", "_booked"):
                res.pop(k, None)
            log.info("Approval list %s from %d account(s) (%.1f s)", "refreshed" if ledger is not None else "not refreshed (%s)" % res.get("status"),
                     len(uuids), time.time() - t0)
            return res
        except Exception as e:  # pragma: no cover - the service keeps running
            log.exception("Refreshing the approval list failed")
            return {"status": "error", "text": tr("s_unerwarteter_fehler_s") % e}
        finally:
            self.running = False

    def _baseline(self, ledger: Ledger) -> None:
        """Kontenstand eines vollstaendigen Lesens merken: nur spaetere Aenderungen in MoneyMoney loesen den naechsten Lauf aus."""
        sig = getattr(ledger, "acc_sig", None)
        if sig is not None:
            self._capture_sig = sig
            self._change_since = None
            if self.retry_reason == "new data":
                self.mm_retry_at = None

    def capture(self) -> None:
        """Schnellabgleich: sobald MoneyMoney offen und entsperrt ist, nur die Kontenliste lesen (unter einer Sekunde) und die
        Staende merken. So reicht auch ein kurzer Blick in MoneyMoney; geaenderte Daten loesen danach den vollen Abgleich aus."""
        self._mm_seen = is_running()
        if self.running or not self._mm_seen:
            return
        try:
            b = self.bridge_factory(True); b.quiet = True          # every 30 s: no lines in the log unless something changes
            raw = b.export_accounts()
        except MoneyMoneyError as e:
            if isinstance(e, MoneyMoneyLocked):
                self.mm_probe = (time.time(), True)
                if not self._mm_locked_logged:
                    self._mm_locked_logged = True
                    log.info("MoneyMoney is locked -- checking quietly every 30 s until it is unlocked")
            elif not isinstance(e, MoneyMoneyNotRunning):
                # MoneyMoney lief, Kontor konnte aber nicht lesen (z. B. Berechtigung) -> sichtbar machen, sonst fehlen Staende
                msg = str(e)[:200]
                log.warning("Quick capture not possible although MoneyMoney is running: %s", msg)
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.store.update("state.json", lambda cur: cur.__setitem__("sync_problem", {"time": stamp, "text": msg}), {})
            return
        self.mm_probe = (time.time(), False)
        if self._mm_locked_logged:
            self._mm_locked_logged = False
            log.info("MoneyMoney unlocked")
        if (self.store.load_shared("state.json", {}) or {}).get("sync_problem"):
            self.store.update("state.json", lambda cur: cur.pop("sync_problem", None), {})
        accs = accounts_from_export(raw)
        sig = account_sig(accs)
        if sig == self._capture_sig:
            return
        first = not self._captured_once
        self._captured_once = True
        known = self._capture_sig is not None
        self._capture_sig = sig
        today = date.today()
        self.store.update("state.json", lambda cur: record_snapshot(cur.setdefault("snapshots", {}), accs.values(), today), {})
        if first:
            self._check_gaps(accs)
        if known and (self.config.get("schedule") or {}).get("automatic", True):
            # neue Daten in MoneyMoney: vollstaendig abgleichen, sobald der Abruf dort fertig ist (Stand 45 s unveraendert,
            # spaetestens 3 Minuten nach der ersten Aenderung) -- sonst liefe bei jeder einzelnen Bank ein eigener Abgleich
            now = time.time()
            self._change_since = self._change_since or now
            self.mm_retry_at = min(now + 45, self._change_since + 180)
            self.retry_reason = "new data"

    def _check_gaps(self, accs: Dict) -> None:
        """Hat MoneyMoney ein Depot abgerufen, waehrend Kontor nicht lief, koennen Monatsend-Staende dazwischen fehlen
        (Kontor sieht nur den neuesten). Schlief der Mac, hat auch MoneyMoney nichts abgerufen -- dann keine Meldung."""
        prev = self.prev_seen
        if prev is None:
            return
        found = []
        for a in accs.values():
            if a.group or not a.portfolio or a.refresh is None or a.refresh.year < 2005:
                continue
            ref = a.refresh.replace(tzinfo=None)            # Ortszeit wie prev_seen/started
            if not (prev + timedelta(minutes=5) < ref < self.started):
                continue
            months, y, m = [], prev.year, prev.month
            while (y, m) < (ref.year, ref.month):
                months.append("%04d-%02d" % (y, m))
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)
            if months:
                found.append({"account": a.uuid, "name": a.name, "months": months, "detected": datetime.now().strftime("%Y-%m-%d %H:%M")})
        if found:
            log.info("Portfolio values possibly incomplete (MoneyMoney refreshed while Kontor was not running): %d portfolio(s)", len(found))

            def upd(cur):
                old = [x for x in cur.get("gaps") or [] if x.get("account") not in {f["account"] for f in found}]
                cur["gaps"] = old + found
            self.store.update("state.json", upd, {})

    def heartbeat(self) -> None:
        if self.store.is_open and time.time() - self._hb_written >= 300:
            self._hb_written = time.time()
            now = datetime.now().isoformat(timespec="seconds")
            self.store.update("state.json", lambda cur: cur.__setitem__("service_last", now), {})

    def code_changed(self) -> Optional[str]:
        """Neue Version im Programmordner (git pull, Update, Dateien ersetzt)? Liefert die neue Versionsnummer."""
        disk = version_on_disk()
        return disk if disk and disk != version() else None

    def restart_if_code_changed(self) -> bool:
        new = self.code_changed()
        if not new or self.running or self.bericht_status().get("running") or not self.restart_allowed:
            return False
        log.info("New version %s in program folder (running %s) -- restarting service", new, version())
        self.stop.set()
        restart_process(self)
        return True

    def assistant_look(self) -> bool:
        """Asks for a newer llama.cpp and newer files of the loaded models when it is time (Assistant.look_due) -- in a thread
        of its own, as the look for Kontor's updates. What it found is loaded later by auto_tick (when set, once idle)."""
        if mm_history.AKTIV.is_set():
            return False
        self.assistant.auto_tick()                       # what the last look found newer: loaded by itself once the assistant is idle
        if not self.assistant.look_due():
            return False
        self.assistant.looked = time.time()
        threading.Thread(target=lambda: self.assistant.look(auto=True), name="kontor-ai-look", daemon=True).start()
        return True

    def scheduler(self) -> None:
        while not self.stop.is_set():
            self.exposure_tick()                         # "tailscale serve"/Funnel: looked at again in the background (EXPOSURE_SECONDS)
            if not self.store.is_open:                   # nobody signed in since the start: nothing reads the data -- the schedule waits
                try:
                    if self.restart_if_code_changed():
                        return
                    self.remote_retry()
                except Exception:  # pragma: no cover
                    log.exception("Scheduler (locked)")
                self.stop.wait(2)
                continue
            try:
                if self.restart_if_code_changed():
                    return
                z = self.config.get("schedule", {}) or {}
                interval = max(5, int(z.get("interval_minutes", 30))) * 60
                due = z.get("automatic", True) and (self.last_run_at is None or time.time() - self.last_run_at >= interval)
                retry = z.get("automatic", True) and self.mm_retry_at is not None and time.time() >= self.mm_retry_at
                if due or retry:
                    if not is_running():
                        if due:
                            log.debug("Scheduler: run due, but MoneyMoney is not running -- checking every minute")
                        self.last_run_at = time.time()
                        self.mm_retry_at = time.time() + 60
                        self.retry_reason = "available again"
                    elif self.moneymoney_gesperrt(max_age=0) is not None and self.moneymoney_gesperrt() is not False:
                        if due:
                            log.debug("Scheduler: run due, but MoneyMoney is locked -- checking every minute")
                        self.last_run_at = time.time()
                        self.mm_retry_at = time.time() + 60
                        self.retry_reason = "available again"
                    else:
                        log.debug("Scheduler: run %s", "due" if due else ("after new data in MoneyMoney" if self.retry_reason == "new data"
                                                                         else "catching up (MoneyMoney available again)"))
                        self.mm_retry_at = None
                        self._change_since = None
                        res = self.do_run(None, force=False)
                        if res.get("status") in ("unavailable", "already_running"):     # z. B. Neuberechnung lief gerade
                            self.mm_retry_at = time.time() + 60
                up = self.config.get("updates", {}) or {}
                every = {"daily": 86400, "weekly": 7 * 86400}.get(up.get("check_mode") or "daily")      # "aus": nie
                wait = every if every and not (self.update_info or {}).get("error") else 7200                   # offline/Fehler: in 2 h erneut
                if every and not mm_history.AKTIV.is_set() and (self.update_checked is None or time.time() - self.update_checked > wait):
                    self.update_checked = time.time()
                    # eigener Thread: eine haengende Verbindung (offline) blockiert weder Zeitplaner noch Oberflaeche
                    threading.Thread(target=lambda: setattr(self, "update_info", updates.check(up.get("repo") or "stecrz/Kontor")),
                                     name="kontor-update", daemon=True).start()
                self.assistant_look()
                self.assistant.keep()                    # end when idle "never": the model runs all the time (after the sign-in, a restart)
                if self.tls_ctx is not None and (self.tls_checked is None or time.time() - self.tls_checked > 86400):
                    self.tls_checked = time.time()
                    import tls_cert
                    if tls_cert.renew_if_due(self.config, self.data_dir):
                        ui = self.config.get("ui") or {}
                        self.tls_ctx.load_cert_chain(ui["tls_cert"], ui["tls_key"])
                        log.info("TLS certificate renewed and reloaded")
            except Exception:  # pragma: no cover
                log.exception("Scheduler")
            try:
                self.remote_retry()
            except Exception:  # pragma: no cover
                log.exception("Remote access")
            try:
                self.heartbeat()
                if (self.config.get("schedule") or {}).get("automatic", True):
                    self.capture()
            except Exception:  # pragma: no cover
                log.exception("Quick capture")
            self.stop.wait(30 if self._mm_seen else 60)

    # -- Daten fuer die Oberflaeche ---------------------------------------
    def plan_all(self) -> dict:
        plan = self.store.load("plan.json", {}) or {}
        if not isinstance(plan.get("areas"), dict):
            return {"areas": {}}
        for a in plan["areas"].values():               # rows that moved (report.PLAN_ROWS_MOVED): under their new key, saved so
            if isinstance(a, dict) and isinstance(a.get("rows"), dict):     # with the next change -- one key to change or reset
                a["rows"] = moved_plan_rows(a["rows"])
        return plan

    def plan_for(self, bereich: str) -> dict:
        return (self.plan_all().get("areas") or {}).get(bereich) or {}

    # -- Kategorien: MoneyMoney ist massgeblich, Kontor traegt dort ein -------------------
    @property
    def categories_raw(self) -> list:
        """MoneyMoney's categories (export_categories, with paths)."""
        return self._categories_raw

    @categories_raw.setter
    def categories_raw(self, cats: list) -> None:
        self._categories_raw = cats
        categorize.set_standard(cats)              # its default category ("Unkategorisiert") counts as none

    @staticmethod
    def mm_write_allowed(local: bool) -> bool:
        """Your assignment goes into MoneyMoney when asked from the Mac itself (from elsewhere: remembered, written at the next
        sync at the Mac). Assigning is the release: nothing is written that you did not assign in Kontor."""
        return local

    def write_categories(self, kat: dict, ids: List[int], path: str, modus: str, local: bool,
                         confirmed: Optional[Dict[str, str]] = None) -> dict:
        """Your assignment (categorize.set_waiting, under categorize.LOCK) into MoneyMoney. modus: "auto" (only where MoneyMoney
        has none or the one Kontor wrote; another one is reported back, fremd), "ueberschreiben" (also another one you just
        confirmed -- confirmed: transaction -> the category the question showed; it must still be that one). From elsewhere
        than the Mac, or with MoneyMoney not reachable, the assignment waits and is written at the next sync -- only where
        MoneyMoney has no category (changing one goes only at the Mac: nur_am_mac). "empty": only where MoneyMoney, read fresh, shows
        no category at all (the assistant's card). written_ids / later_ids: which ones were written / wait."""
        path = categorize.norm_cat(path)
        led = self.ledger
        by_id = {t.id: t for t in led.txs if t.id > 0} if led is not None else {}
        out: Dict[str, Any] = {"written": 0, "waiting": 0, "foreign": [], "error": 0, "later": 0, "mac_only": 0, "unreachable": 0,
                               "written_ids": [], "later_ids": []}

        def later(rest: List[int], reachable_later: bool) -> None:
            for i in rest:                                   # waits (p) -- only what has no category in MoneyMoney
                if i in by_id and categorize.mm_of(by_id[i]):
                    kat["assignment"].pop(str(i), None)       # changing a category needs your answer at the Mac, now
                    out["mac_only" if reachable_later else "unreachable"] += 1
                else:
                    out["later"] += 1
                    out["later_ids"].append(i)
        if not path or not ids:
            return out
        if not self.mm_write_allowed(local) or led is None:
            later(ids, True)
            return out
        conf = confirmed or {}
        items = [{"id": i, "new": path, "old": categorize.norm_cat(conf[str(i)]) if str(i) in conf else categorize.mm_of(by_id[i]),
                  "overwrite": modus == "overwrite"} for i in ids if i in by_id]
        own = (self.store.load_shared("state.json", {}) or {}).get(mm_categories.LOG_KEY) or {}
        idx = mm_categories.index(self.categories_raw)
        try:
            res = mm_categories.write(self.bridge_factory(False), led, items, idx, own, only_empty=modus == "empty")
        except MoneyMoneyError as e:
            log.info("Categories wait for MoneyMoney: %s", e)
            later(ids, False)
            return out
        written = res["written"]
        if written:
            mm_categories.apply_to_ledger(led, idx, written)
            self.store.update("state.json", lambda cur: mm_categories.remember(cur, written), {})
            self._save_ledger_cache(led, force=True)
        for i in [w["id"] for w in written] + res["equal"]:
            kat["assignment"].pop(str(i), None)          # in MoneyMoney now -- the truth
        for i in res["waiting"]:                          # the category is not (any more) in MoneyMoney
            kat["assignment"].pop(str(i), None)
        for f in res["foreign"] + res["error"]:           # another category there (it counts) or the transaction changed there
            kat["assignment"].pop(str(f["id"]), None)
        if res.get("abort"):
            log.info("Categories: MoneyMoney stopped after %d, the rest waits", len(written))
            later(res["open"], False)
        out.update(written=len(written), waiting=len(res["waiting"]), foreign=res["foreign"], error=len(res["error"]), written_ids=[w["id"] for w in written])
        return out

    def categories_written(self) -> dict:
        """What Kontor entered in MoneyMoney (its log), newest first, with the transaction and whether it can be taken back:
        MoneyMoney still shows Kontor's category (as last read) and the transaction is in what Kontor reads."""
        own = (self.store.load_shared("state.json", {}) or {}).get(mm_categories.LOG_KEY) or {}
        by_id = {t.id: t for t in self.ledger.txs if t.id > 0} if self.ledger is not None else {}
        accs = self.ledger.accounts if self.ledger is not None else {}
        out = []
        for tid, e in sorted(own.items(), key=lambda kv: kv[1].get("time") or "", reverse=True):
            t = by_id.get(int(tid)) if str(tid).lstrip("-").isdigit() else None
            now = categorize.mm_of(t) if t is not None else None
            out.append({"id": int(tid), "time": e.get("time"), "old": e.get("old") or "", "new": e.get("new") or "",
                        "date": t.booking_date.isoformat() if t is not None else None, "name": t.name if t is not None else "",
                        "amount": t.amount if t is not None else None, "account": accs[t.account_uuid].name if t is not None and t.account_uuid in accs else "",
                        "now": now, "undo": t is not None and categorize.norm_cat(now or "") == categorize.norm_cat(e.get("new") or "")})
        return {"items": out[:2000], "total": len(out)}

    def undo_categories(self, ids: List[int]) -> dict:
        """Take back what Kontor entered (under categorize.LOCK): each transaction gets the category it had before (none: MoneyMoney's
        default category) -- read fresh just before, and only where MoneyMoney still shows Kontor's category (anything else is
        reported, nothing changed there). Done ones leave the log."""
        out: Dict[str, Any] = {"undone": 0, "changed": 0, "error": 0, "open": 0, "undone_ids": []}
        led = self.ledger
        if led is None:
            raise ValueError(tr("s_noch_kein_lauf_moneymoney_lesen"))
        own = (self.store.load_shared("state.json", {}) or {}).get(mm_categories.LOG_KEY) or {}
        idx = mm_categories.index(self.categories_raw)
        std = next((p for p, c in idx.items() if c["default"]), None)
        by_id = {t.id: t for t in led.txs if t.id > 0}
        items = []
        for i in ids:
            e = own.get(str(i))
            if e is None or i not in by_id:
                out["error"] += 1
                continue
            back = categorize.norm_cat(e.get("old") or "") or std
            if not back:
                out["error"] += 1
                continue
            items.append({"id": i, "new": back, "old": categorize.norm_cat(e.get("new") or ""), "overwrite": False})
        if items:
            try:
                res = mm_categories.write(self.bridge_factory(False), led, items, idx, own, allow_default=True, only_own=True)
            except MoneyMoneyError as e:
                raise ValueError(tr("s_mm_nicht_erreichbar_nichts") + " (%s)" % e)
            done = res["written"]
            if done:
                mm_categories.apply_to_ledger(led, idx, done)
                gone = {str(w["id"]) for w in done}
                self.store.update("state.json", lambda cur: mm_categories.forget(cur, gone), {})
                self._save_ledger_cache(led, force=True)
            out["undone"] = len(done) + len(res["equal"])
            out["undone_ids"] = [w["id"] for w in done] + list(res["equal"])
            if res["equal"]:
                self.store.update("state.json", lambda cur: mm_categories.forget(cur, {str(i) for i in res["equal"]}), {})
            out["changed"] = len(res["foreign"])
            out["error"] += len(res["error"]) + len(res["waiting"]) + len(res.get("open") or [])
            out["open"] = len(res.get("open") or [])             # not tried: MoneyMoney not reachable or stopped
            if res.get("abort"):
                log.info("Taking back categories: MoneyMoney stopped after %d", len(done))
        log.info("Categories taken back in MoneyMoney: %d (changed there meanwhile: %d, not possible: %d)", out["undone"], out["changed"], out["error"])
        return out

    def category_hints(self, kat: dict, area_of: Dict[str, str], roles: Dict[str, str]) -> "categorize.Hints":
        """What the suggestions under Kategorisieren are made of (categorize.Hints) -- kept, made anew when the transactions, your
        assignments, MoneyMoney's categories, the cash flow positions, the areas or the accounts' positions changed. Only
        categories that exist in MoneyMoney are suggested (all while none are known); a counter-booking can be on a bank
        account or an account kept by hand."""
        transfer, is_transfer = transfer_category(self)
        idx = mm_categories.index(self.categories_raw)
        ok = {p for p in idx if mm_categories.assignable(idx, p) is None} if idx else None
        accs = self.ledger.accounts
        counter = {u for u, r in roles.items() if r == "cash" or (r != "ignore" and u in accs and accs[u].offline)}
        key = (id(self.ledger), hash(tuple((t.id, t.mm_category_path, t.amount, t.booked) for t in self.ledger.txs)), json.dumps(
            [kat.get("assignment"), None if ok is None else sorted(ok), transfer, area_of, sorted(counter), sorted(categorize.STANDARD),
             self.config.get("categories") or {}, self.config.get("cashflow") or {}], sort_keys=True, default=str))
        cached = getattr(self, "_hints", None)
        if cached and cached[0] == key:
            return cached[1]
        from report import POS, position_of
        sections: Dict[str, bool] = {}

        def everyday(path: str) -> bool:                 # income or spending in the cash flow (not saving, repayment, transfer ...)
            if path not in sections:
                sections[path] = (POS.get(position_of(path, self.config, {})[0]) or ("",))[0] in ("income", "expenses")
            return sections[path]
        hints = categorize.Hints(kat, self.ledger, area_of, counter, ok, transfer, is_transfer, everyday)
        self._hints = (key, hints)
        return hints

    def tx_meaning(self) -> Optional["categorize.Meaning"]:
        """For suggestions by meaning: the embeddings of transactions' texts the assistant made (only read, never made here) --
        None while the assistant is off or may not read transactions (then they do not exist either)."""
        try:
            if not assistant_mod.settings(self.config)["enabled"]:
                return None
            got = self.assistant.tx_meaning()
        except Exception as e:
            log.warning("Categories: no suggestions by meaning (%s)", type(e).__name__)
            return None
        if not got:
            return None
        if getattr(self, "_mean_cache", None) is None:
            self._mean_cache: dict = {}                  # the counterparties' embeddings, kept across your assignments (categorize.Hints._means)
        return categorize.Meaning(got[0], got[1], self._mean_cache)

    def rule_proposals(self, kat: dict) -> List[dict]:
        """Rules worth adding in MoneyMoney (categorize.rule_proposals), only for categories that exist there."""
        if self.ledger is None:
            return []
        own = (self.store.load_shared("state.json", {}) or {}).get(mm_categories.LOG_KEY) or {}
        idx = mm_categories.index(self.categories_raw)
        ok = {p for p in idx if mm_categories.assignable(idx, p) is None}
        key = (id(self.ledger), hash(tuple((t.id, t.category_path) for t in self.ledger.txs)), json.dumps(
            [own, kat.get("assignment"), kat.get("rule_done"), sorted(ok)], sort_keys=True, default=str))
        cached = getattr(self, "_proposals", None)
        if cached and cached[0] == key:
            return cached[1]
        res = categorize.rule_proposals(kat, self.ledger, own, ok)
        self._proposals = (key, res)
        return res

    def flush_pending_categories(self) -> int:
        """At the sync: write what waits (assigned from elsewhere, or MoneyMoney was not reachable). Has the transaction got a
        category in MoneyMoney meanwhile, that one counts."""
        if self.ledger is None:
            return 0
        if not self.categories_raw:
            return 0                                     # no categories known yet: nothing is written (nor dropped)
        with categorize.LOCK:                            # nothing you assign meanwhile gets lost
            return self._flush_pending()

    def _flush_pending(self) -> int:
        kat = categorize.load(self.store)
        by_id = {t.id: t for t in self.ledger.txs if t.id > 0}
        pend: Dict[Tuple[str, bool], List[int]] = {}
        for tid, z in list(kat["assignment"].items()):
            if not categorize.waiting(z):
                continue
            t = by_id.get(int(tid)) if str(tid).lstrip("-").isdigit() else None
            if t is None or categorize.mm_of(t):
                kat["assignment"].pop(tid, None)          # gone, or categorized in MoneyMoney meanwhile
                continue
            pend.setdefault((z["k"], bool(z.get("e"))), []).append(int(tid))
        n = 0
        for (path, only_empty), ids in pend.items():          # the assistant's card ("e"): only where MoneyMoney shows none
            res = self.write_categories(kat, ids, path, "empty" if only_empty else "auto", True)
            n += res["written"]
            if res["later"]:
                break                                    # MoneyMoney not reachable: next time
        if n:
            categorize.learn(kat, self.ledger)
        categorize.save(self.store, kat)
        if n:
            log.info("%d waiting categor(y/ies) written to MoneyMoney", n)
            self.request_rebuild("categories filled in")
        return n

    def umsatzliste(self) -> list:
        """Kompakte Umsatzliste des aktuellen Berichts (schreibgeschuetzt): aus dem Speicher, sonst aus umsaetze.json."""
        if self.umsaetze is None:
            self.umsaetze = self.store.load_shared("transactions.json", []) or []
        return self.umsaetze

    def dataset(self) -> dict:
        raw = self.store.load_shared("dataset.json", None)
        if raw is None or "areas" not in raw:
            return {"empty": True, "setup": not self.config_has_rules(), "version": version()}
        ds = copy.deepcopy(raw)
        cfg = with_property_categories(self.config, self.ledger)
        immo_res = immo_results(cfg, date.today())
        resolve = self.ledger.resolve if self.ledger is not None else None
        bereiche = ds.get("areas") or {}

        def run(bid: str, fremd: dict) -> None:
            b = bereiche[bid]
            if "error" in b:
                return
            try:
                apply_plan(b, self.plan_for(bid), cfg, fremd_nw=fremd, immo=immo_for_plan(cfg, bid, immo_res), ledger_resolve=resolve)
            except Exception as e:  # pragma: no cover - fehlerhafte Plandaten duerfen die Anzeige nicht stoppen
                log.exception("Planning for area %s", bid)
                b["error"] = tr("s_planung_fehlgeschlagen") % e

        # 1. Durchgang: alle Bereiche; 2. Durchgang: Bereiche mit Beteiligungs-Verknuepfung auf andere Bereiche
        for bid in bereiche:
            run(bid, {})
        fremd = {bid: (b.get("balance", {}).get("projection", {}).get("net_worth") or {}) for bid, b in bereiche.items() if "error" not in b}
        for bid in list(bereiche):
            wcfg = (self.plan_for(bid).get("appreciation") or {})
            if any(isinstance(v, dict) and v.get("area") for v in wcfg.values()):
                bereiche[bid] = copy.deepcopy(raw["areas"][bid])
                run(bid, fremd)
        ds["setup"] = not self.config_has_rules()
        ds["version"] = version()
        ds["positions"] = [{"id": r, "name": role_label(r)} for r in ROLES]
        return ds

    def abruf(self) -> Optional[dict]:
        """Eigener Datenstand von MoneyMoney je Konto (laut dem zuletzt gelesenen Stand): neuester Bankabruf, Konten, die dahinter
        zurueckliegen (mehr als einen Tag, mit Saldo, nicht laenger als inaktiv_monate), und Konten ohne Abruf (offline)."""
        led = self.ledger
        if led is None:
            return None
        n_inakt = int((self.config.get("balance") or {}).get("inactive_months", 12) or 12)
        key = (id(led), n_inakt, json.dumps([self.config.get(k) for k in ("fetch", "loans", "companies", "account_mirrors")], sort_keys=True, default=str))
        if self._bankabruf_cache[0] == key:
            return self._bankabruf_cache[1]
        kinds = abruf_arten(led, self.config)
        leaves = [a for a in led.accounts.values() if not a.group and a.path]
        online = [a for a in leaves if kinds[a.uuid]["kind"] == "online" and a.refresh is not None and a.refresh.year >= 2005]
        newest = max((a.refresh for a in online), default=None)
        cutoff = newest - timedelta(days=30.5 * n_inakt) if newest else None
        konten, lag = [], []
        for a in leaves:
            k = kinds[a.uuid]
            refreshed = a.refresh is not None and a.refresh.year >= 2005
            zurueck = bool(newest and k["kind"] == "online" and refreshed and cutoff <= a.refresh < newest - timedelta(days=1)
                           and (a.portfolio or abs(a.balance) > 0.005))
            alt = bool(newest and k["kind"] == "online" and refreshed and a.refresh < cutoff)
            konten.append({"uuid": a.uuid, "name": a.name, "path": a.path, "kind": k["kind"], "reason": k["reason"], "balance_amount": a.balance,
                           "time": a.refresh.strftime("%Y-%m-%d %H:%M") if refreshed else None, "back": zurueck, "old": alt})
            if zurueck:
                lag.append(a)
        lag.sort(key=lambda a: a.refresh)
        res = {"newest": newest.strftime("%Y-%m-%d %H:%M") if newest else None, "accounts": konten,
               "back": [{"name": a.name, "time": a.refresh.strftime("%Y-%m-%d %H:%M")} for a in lag[:12]], "back_count": len(lag)}
        self._bankabruf_cache = (key, res)
        return res

    def bankabruf(self) -> Optional[dict]:
        r = self.abruf()
        if not r or not r["newest"]:
            return None
        return {"newest": r["newest"], "back": r["back"], "back_count": r["back_count"],
                "accounts": sum(1 for k in r["accounts"] if k["kind"] == "online")}

    # -- uninstall: service, data (with log), data key, optionally the program -- never the receipts or MoneyMoney --------------------
    def uninstall(self, program: bool = True) -> dict:
        """Removes Kontor from this Mac: the background service (its launchd file), Kontor's own files in the data folder
        (settings, data, log, certificate -- nothing else that may lie there; the folder itself only when empty then), the data
        key (only when no encrypted file is left: a key is never deleted while data it opens remain) and, if
        wanted, the program folder. The receipts folder and linked documents stay, also inside the program folder; MoneyMoney is
        not touched. Refuses folders that do not look like Kontor's."""
        from receipts import _canon
        home = _canon(os.path.expanduser("~"))
        bel = (self.config.get("receipts") or {}).get("folder") or "~/Documents/Kontor-Belege"
        keep = [_canon(os.path.expanduser(bel))] + [_canon(p) for p in self.linked_files()]
        data, prog = os.path.realpath(self.data_dir), os.path.realpath(self.program_dir)
        cdata, cprog = _canon(data), _canon(prog)
        under = lambda a, b: a == b or a.startswith(b.rstrip(os.sep) + os.sep)
        if cdata in (home, "/") or under(home, cdata) or not os.path.isdir(data) or not _KONTOR_FILE.search(" ".join(os.listdir(data))):
            return {"error": tr("s_deinstall_ordner_unklar") % data}
        if program and (cprog in (home, "/") or under(home, cprog) or under(cdata, cprog)
                        or not all(os.path.exists(os.path.join(prog, f)) for f in ("kontor.py", "service.py", "VERSION"))):
            return {"error": tr("s_deinstall_ordner_unklar") % prog}
        if under(cprog, cdata):                       # the program inside the data folder: only together with the program
            if not program:
                return {"error": tr("s_deinstall_ordner_unklar") % prog}
        if program and self.settings_lost():          # receipts or linked documents may lie in the program folder -- which, is not known
            return {"error": tr("s_deinstall_einstellungen_fehlen")}
        done, left = [], []
        plist = updates.plist_path()
        if os.path.exists(plist):
            try:
                os.remove(plist); done.append(plist)
            except OSError:
                left.append(plist)
        try:                                          # Kontor's own Python, whether or not the program folder stays
            own = pyruntime.remove_all(prog, program)
            if own == "later":                        # this process runs in it: the starter removes it once the service has ended
                keep = keep + [_canon(pyboot.folder(prog))]
            if own:
                done.append(pyboot.folder(prog))
        except OSError:
            left.append(pyboot.folder(prog))
        if program:
            (done if _remove_tree(prog, keep) else left).append(prog)
        # the data folder: only Kontor's own files (whatever else lies there stays), then the folder when it is empty
        a = getattr(self, "_assistant", None)
        if a is not None:                             # the conversation being answered: not saved again once the folder is gone
            a.delete_chats(everything=True)
        self.assistant_stop()
        done += mac_app.remove_data()                 # Kontor's own app: its settings, website data and permissions (it quits after the answer)
        foreign, failed = _remove_own_files(data, keep)
        (left if failed else done).append(data)
        key = False
        if not any(n.endswith((".enc", ".enc.tmp", ".enc.renew")) for n in (storage_names(data) if os.path.isdir(data) else [])):     # also in its folders (chats)
            key = self.uninstall_key()
        log.warning("Uninstalled: %d removed, %d left, key %s", len(done), len(left), "removed" if key else "kept")
        return {"ok": True, "removed": done, "kept": left, "key_removed": key, "foreign": foreign,
                "receipts": bel if os.path.isdir(os.path.expanduser(bel)) else ""}

    def linked_files(self) -> List[str]:
        """Documents you linked (receipts outside the receipts folder, property documents): they stay where they are."""
        out = []
        for im in self.config.get("real_estate") or []:
            out += [d.get("path") for d in (im.get("documents") or []) if isinstance(d, dict) and d.get("path")]
        try:
            idx = self.store.load("receipts.json", {}) or {}
            for v in (idx.values() if isinstance(idx, dict) else []):
                for e in (v if isinstance(v, list) else [v]):
                    if isinstance(e, dict) and isinstance(e.get("path"), str) and os.path.isabs(e["path"]):
                        out.append(e["path"])
        except Exception:
            pass
        return [os.path.expanduser(p) for p in out if isinstance(p, str)]

    def uninstall_key(self) -> bool:
        """Deletes Kontor's data key (the key file) -- only when no encrypted file is left. True when no key is left."""
        return access.remove_keys(self.data_dir)

    def uninstall_finish(self) -> None:
        """After the answer: launchd drops the service (it stops this process) -- else the process ends by itself; launchd
        must not start it again (KeepAlive), so a failed bootout is followed by a removal of the job."""
        try:
            time.sleep(1.5)
            if sys.platform == "darwin":
                mac_app.remove_data(quit_first=True)         # the app (it may have asked for this) goes now, and what it wrote since
                job = "gui/%d/%s" % (os.getuid(), updates.LABEL)
                r = subprocess.run(["launchctl", "bootout", job], capture_output=True, timeout=20)
                if r.returncode != 0:
                    subprocess.run(["launchctl", "remove", updates.LABEL], capture_output=True, timeout=20)
            time.sleep(1.5)
        except Exception:
            log.exception("Uninstall: service not stopped by launchd")
        finally:
            os._exit(0)

    def status(self, loopback: bool, frisch: bool = False) -> dict:
        st = self.store.load_shared("state.json", {}) or {}
        bcfg = self.config.get("receipts") or {}
        return {
            "version": version(),
            "webapp": bool((self.config.get("ui") or {}).get("webapp")),          # Kontor opened as an app at the Mac (the setup's step 1)
            "mac_app": mac_app.state() if loopback and mac_app.supported() else None,       # Kontor's own app on this Mac
            "service": {"started": self.started.strftime("%Y-%m-%d %H:%M"), "running": self.running, "step": self.run_step,
                       "automatic": (self.config.get("schedule") or {}).get("automatic", True),
                       "interval_minutes": (self.config.get("schedule") or {}).get("interval_minutes", 30)},
            "moneymoney": {"running": is_running(), "locked": self.moneymoney_gesperrt(max_age=3.0 if frisch else 45.0), "from_cache": self.ledger_from_cache,
                           "as_of": self.ledger_time.strftime("%Y-%m-%d %H:%M") if self.ledger_time else None,
                           "bank_fetch": self.bankabruf(), "gaps": len(st.get("gaps") or []), "problem_text": st.get("sync_problem"), "history": st.get("mm_history_src")},
            "storage": {"encrypted": self.store.encrypted, "folder": self.data_dir,
                        "program_folder": self.program_dir, "touchid_unlock": access.touchid_ready(self.data_dir)},
            "receipts": {"folder": os.path.expanduser(bcfg.get("folder") or "~/Documents/Kontor-Belege")},
            "dry_run": self.config.get("dry_run", True),
            "last_run": st.get("last_run"),
            "last_result": self.last_result,
            "report": self.bericht_status(),
            "restart_pending": self.code_changed(),
            "update": self.update_info,
            "touchid": auth.touchid_available() and loopback, "touchid_active": self.touchid_on(),
            "local": loopback,
        }


# ---------------------------------------------------------------------------
# Demo: Kontor with made-up data, to show it to someone without showing your data
# ---------------------------------------------------------------------------
def _demo_no_helper(data: bytes) -> dict:
    """The demo starts (and builds) no helper at the Mac: a PDF or a picture is not read there (text recognition)."""
    raise receipt_text.TextUnavailable(tr("s_demo_beleg_nicht"))


DEMO_LOCK = threading.Lock()
DEMO_PREFIX = "kontor-demo-"           # its data folder: a temporary folder of its own, gone at its end (or at the next start)
# What the demo answers -- everything else is refused (a new request is refused there until it is put into one of these lists;
# tests/test_security.py makes sure every request of the service is in one of them). Reading its own data, the pages, the
# assistant's questions; never anything about this Mac, its files, programs, network, updates, access or the real Kontor.
DEMO_GET = frozenset(("/api/status", "/api/dataset", "/api/config", "/api/plan", "/api/accounts", "/api/categories", "/api/sync", "/api/runs",
                      "/api/transactions", "/api/receipts", "/api/receipts/file", "/api/export/property.xlsx", "/api/package/export",
                      "/api/assistant/status", "/api/assistant/chats", "/api/assistant/chat", "/api/assistant/changes", "/api/assistant/poll", "/api/assistant/file",
                      "/api/help", "/api/check/status", "/api/history", "/api/categories/positions", "/api/categories/written",
                      "/api/categories/unassigned", "/api/categories/proposals", "/api/categories/doubts", "/api/properties", "/api/properties/template",
                      "/api/price_index"))      # (the demo: the index this version holds, never fetched)
DEMO_GET_PREFIX = ("/api/export/",)    # the Excel files of the pages
DEMO_POST = frozenset(("/api/lock", "/api/config", "/api/rules/preview", "/api/check", "/api/sync", "/api/sync/gaps", "/api/bookings/reject",
                       "/api/bookings/plan", "/api/bookings/restore", "/api/bookings/refresh", "/api/run", "/api/report", "/api/report/rebuild",
                       "/api/plan", "/api/history", "/api/history/import", "/api/receipts/upload", "/api/receipts/remove", "/api/receipts/update",
                       "/api/categories/assign", "/api/categories/proposals", "/api/categories/doubts", "/api/categories/positions", "/api/categories/areas",
                       "/api/categories/undo", "/api/properties", "/api/properties/calculate",
                       "/api/assistant/ask", "/api/assistant/stop", "/api/assistant/reset", "/api/assistant/page", "/api/assistant/confirm",
                       "/api/assistant/listen", "/api/assistant/transcribe", "/api/assistant/attach", "/api/assistant/chats/delete", "/api/assistant/undo",
                       "/api/assistant/memory/undo", "/api/assistant/memory/offer",          # (notes of the demo's own memory, under its answers)
                       "/api/confirm"))         # Face ID for a change from the iPhone whose passkey opened it (the real Kontor's devices)
# ... and what it never answers (named, so that a request is never in no list at all)
DEMO_NEVER = frozenset(("/api/setup", "/api/login", "/api/touchid", "/api/touchid/switch", "/api/password", "/api/offline/verifier", "/api/log",
                        "/api/remote", "/api/remote/acl", "/api/timemachine", "/api/timemachine-exclusion", "/api/diagnostics", "/api/update/status",
                        "/api/update/check", "/api/update/install", "/api/language", "/api/securities/lookup", "/api/history/mm-status",
                        "/api/history/mm-import", "/api/history/mm-reveal", "/api/file/choose", "/api/file/open", "/api/file/reveal",
                        "/api/backup", "/api/backup/restore", "/api/reset", "/api/uninstall", "/api/key/renew", "/api/storage/notice", "/api/mac-app/open",
                        "/api/package/import", "/api/receipts/link", "/api/receipts/open", "/api/receipts/export",
                        "/api/assistant/settings", "/api/assistant/check", "/api/assistant/runtime/install", "/api/assistant/runtime/remove",
                        "/api/assistant/model/files", "/api/assistant/model/download", "/api/assistant/model/cancel", "/api/assistant/model/delete",
                        "/api/assistant/web", "/api/assistant/server", "/api/assistant/update-all", "/api/assistant/load",
                        "/api/assistant/memory", "/api/assistant/memory/export", "/api/assistant/memory/import", "/api/assistant/memory/import/undo",
                        # the iPhones added at the Mac and their passkeys: the demo knows none (a sign-in with one opens the demo in the real Kontor)
                        "/api/passkey/options", "/api/passkey/login", "/api/pair/begin", "/api/pair/finish", "/api/devices",
                        "/api/devices/pair", "/api/devices/set", "/api/devices/remove",
                        "/api/python"))
DEMO_FIXED = ("ui", "receipts", "updates", "assistant", "notifications")    # settings of the demo no page changes (how it looks and works)
DEMO_SESSIONS = 20                     # at the same time at most
DEMO_IDLE = 2 * 3600                   # seconds without any session (locked, closed): then it ends, its folder goes


def demo_allowed(method: str, path: str, body: Optional[dict] = None) -> bool:
    """Does the demo answer this request? (Within an allowed one: no file of this Mac linked to a property.)"""
    if method == "GET":
        return path in DEMO_GET or path.startswith(DEMO_GET_PREFIX)
    if path == "/api/properties" and str((body or {}).get("action") or "") == "doc_add":
        return False
    return path in DEMO_POST


class DemoApp(App):
    """Kontor with made-up data (demo.py), to show it: a world of its own in place of MoneyMoney (nothing is read from or written
    to MoneyMoney), its own data folder (temporary, encrypted with a key only in memory, removed at its end) and sessions --
    opened only with the real Kontor's sign-in. It never reads the real data folder, sessions, conversations, memory or receipts,
    of the real settings only how Kontor looks and works (language, lock, the assistant); it answers only DEMO_GET / DEMO_POST.
    The assistant answers with the same model as the real Kontor (a model knows nothing of anyone) and the same rights (the
    internet too, with the real Kontor's keys for Tavily and Claude and their counts) -- with a conversation, saved conversations,
    memory and changes of its own."""
    DEMO = True

    def __init__(self, real: "App", box: "DemoBox"):
        d = tempfile.mkdtemp(prefix=DEMO_PREFIX)
        try:
            store = Store(d, secrets.token_bytes(32))
            std = sorted(categorize.STANDARD)                   # MoneyMoney's default category: named as in the real one
            self.world = demo.World(date.today(), std[0] if len(std) == 1 else "Unkategorisiert")
            store.save("config.json", demo.config(self.world, real.config, os.path.join(d, "Belege")))
            store.save("state.json", self.world.state())
            super().__init__(store, d, bridge_factory=self.world.bridge)
        except Exception:
            shutil.rmtree(d, ignore_errors=True)
            raise
        self.box = box
        DEMO_LIVE.add(d)
        self._peer = lambda: real.assistant                     # the model it shares (nothing else of the real Kontor)
        self._real_open = lambda: real.store.is_open
        self._real_config = lambda: real.config

    def follow_real(self) -> None:
        """The real Kontor's settings of the assistant, "from elsewhere only look" and the lock (changed there meanwhile): taken over
        at each sign-in to the demo and every half minute."""
        if not self._real_open():
            return
        rc = self._real_config()
        ui = dict(self.config.get("ui") or {})
        for k in ("remote_read_only", "lock_minutes"):
            if k in (rc.get("ui") or {}):
                ui[k] = rc["ui"][k]
            else:
                ui.pop(k, None)
        self.config = dict(self.config, assistant=copy.deepcopy(rc.get("assistant") or {}), ui=ui)
        self.sessions.set_idle(int(ui.get("lock_minutes", 15)))

    @property
    def assistant(self) -> "assistant_mod.Assistant":
        """Its own assistant -- it starts (and builds) no helper at the Mac: a PDF or a picture is not read in the demo."""
        a = App.assistant.fget(self)
        if a.hooks.get("receipt_text") is not _demo_no_helper:
            a.hooks.update(receipt_text=_demo_no_helper, receipt_layout=_demo_no_helper)
        return a

    def assistant_peer(self) -> Optional["assistant_mod.Assistant"]:
        """The real Kontor's assistant: its model is the one the demo's assistant asks (assistant.Assistant) -- none while nobody
        signed in to the real Kontor since its start (its settings are data): the demo's assistant is then switched off."""
        return self._peer() if self._real_open() else None

    def apply_language(self) -> None:
        """The language is the real Kontor's (it holds for the whole service)."""

    @property
    def categories_raw(self) -> list:
        return self._categories_raw

    @categories_raw.setter
    def categories_raw(self, cats: list) -> None:
        self._categories_raw = cats                              # (the default category counts for the whole service: the real one's)

    def save_config(self, cfg: dict) -> None:
        cfg = dict(cfg)
        for k in DEMO_FIXED:                                     # whatever a page sends: as at the start of the demo
            if k in self.config:
                cfg[k] = copy.deepcopy(self.config[k])
            else:
                cfg.pop(k, None)
        super().save_config(cfg)

    def shown(self, obj: Any) -> Any:
        """An answer of the demo: its settings go out without the assistant's (they are the real Kontor's -- the model set up
        on this Mac, the websites trusted there; the demo's pages need none of it)."""
        bare = lambda c: {k: v for k, v in c.items() if k != "assistant"}
        if isinstance(obj, dict) and isinstance(obj.get("config"), dict):
            return dict(obj, config=bare(obj["config"]))
        if obj is self.config or (isinstance(obj, dict) and "assistant" in obj and "ui" in obj):     # (also settings saved meanwhile)
            return bare(obj)
        return obj

    def tailscale(self, fresh: bool = False) -> dict:
        return {"found": False}

    def exposed(self) -> bool:
        return self.box.real.exposed()

    def exposure_block(self, wait: float = 0.0) -> Optional[str]:
        return self.box.real.exposure_block(wait)

    def start_remote(self) -> None:
        return None

    def request_restart(self) -> None:
        return None

    def offline_copy(self) -> bool:
        return False

    def _refuse(self, *a, **k):
        raise ValueError(tr("s_demo_nicht_moeglich"))

    uninstall = uninstall_key = uninstall_finish = historie_einlesen = securities_lookup = _refuse

    def status(self, loopback: bool, frisch: bool = False) -> dict:
        st = super().status(loopback, frisch)
        st["moneymoney"].update(running=True, locked=False)
        st.update(demo=True, mac_app=None, update=None, touchid=False, touchid_active=False,
                  storage=dict(st["storage"], folder="", program_folder=""), receipts={"folder": ""})
        return st

    def dispose(self) -> None:
        """The end of the demo: its answers stop, its folder goes (with everything shown, uploaded or asked in it)."""
        self.stop.set()
        self.sessions.drop_all()
        a = self._assistant
        try:
            self.assistant_stop()                                # its own answer only; the shared model runs on
        except Exception:  # pragma: no cover
            log.exception("Demo: assistant")
        until = time.time() + 20                                 # its answer, a sync or report still running: finished first
        while (self.running or self.rebuild_running or (a is not None and a.job is not None and not a.job.done)) and time.time() < until:
            time.sleep(0.05)
        shutil.rmtree(self.data_dir, ignore_errors=True)
        DEMO_LIVE.discard(self.data_dir)
        t = threading.Timer(120, shutil.rmtree, (self.data_dir,), {"ignore_errors": True})      # what a request still on its way wrote after
        t.daemon = True
        t.start()


class DemoBox:
    """The demo of a Kontor: at most one at a time, opened from the sign-in page with the same sign-in (password or Touch ID,
    "demo": true). Locked like the real Kontor, it stays and opens again as it was -- until DEMO_IDLE without any session, or
    until the service ends: then its folder goes, and the next sign-in to the demo starts a new world."""
    REAP_SECONDS = 30

    def __init__(self, real: "App"):
        self.real = real
        self.lock = threading.Lock()
        self.app: Optional["DemoApp"] = None
        self.handler = None                  # its request handler (make_handler), set with it
        self.idle_since: Optional[float] = None       # since when it has no session (it ends after DEMO_IDLE)
        # folders a service before this one left behind -- with the first request after its start: all of them (a running service
        # has none of its own yet); else (tests, several Kontors in one process) only old ones of no demo alive here
        remove_stale_demos(0 if real.restart_allowed else 600)

    def current(self) -> Tuple[Optional["DemoApp"], Any]:
        return self.app, self.handler

    def open_session(self, remote: str, handler_for: Callable[["DemoApp"], Any], via: str = "password", opened_by: Optional[str] = None) -> dict:
        """A session in the demo (started if there is none) -- only after a sign-in: the session. handler_for: make_handler;
        opened_by: the iPhone whose passkey opened it (its removal ends the session)."""
        with self.lock:
            if self.app is None:
                remove_stale_demos(0 if self.real.restart_allowed else 600)
                d = DemoApp(self.real, self)
                try:
                    until = time.time() + 120                    # the world read, the rules booked (after a sync of the real Kontor that runs) ...
                    while d.do_run(False, True).get("status") == "already_running" and time.time() < until:
                        time.sleep(0.5)
                    d.rebuild_report(wait=True, grund="demo", timeout=120)     # ... and the figures there when its first page opens
                    self.app, self.handler = d, handler_for(d)
                except Exception:
                    d.dispose()
                    raise
                threading.Thread(target=self._reap, args=(d,), name="kontor-demo", daemon=True).start()
                log.info("Demo started")
            elif self.app.sessions.active() >= DEMO_SESSIONS:
                raise ValueError(tr("s_demo_zu_viele"))
            self.idle_since = None
            self.app.follow_real()
            return self.app.sessions.create(remote, via, opened_by=opened_by)

    def end(self, only: Optional["DemoApp"] = None, idle: bool = False) -> None:
        """Ends the demo (idle: only once it has had no session for DEMO_IDLE)."""
        with self.lock:
            d = self.app
            if d is None or (only is not None and d is not only):
                return
            if idle:
                if d.sessions.active():
                    self.idle_since = None
                    return
                self.idle_since = self.idle_since or time.time()
                if time.time() - self.idle_since < DEMO_IDLE:
                    return
            self.app, self.handler = None, None
        d.dispose()
        log.info("Demo ended")

    def _reap(self, d: "DemoApp") -> None:
        while self.app is d:
            time.sleep(self.REAP_SECONDS)
            if not self.real.store.is_open:                      # the real Kontor locked its data again (reset, a key that failed)
                self.end(d)
                return
            d.follow_real()
            self.end(d, idle=True)


DEMO_LIVE: set = set()                 # folders of the demos alive in this process (never removed as left behind)


def remove_stale_demos(age: float = 600.0) -> int:
    """Folders of demos a stopped service left behind (encrypted with a key that went with it; receipts uploaded in it are not):
    those not touched for age seconds and of no demo alive in this process."""
    n = 0
    base = tempfile.gettempdir()
    for name in os.listdir(base):
        p = os.path.join(base, name)
        if name.startswith(DEMO_PREFIX) and p not in DEMO_LIVE and os.path.isdir(p) and not os.path.islink(p) and time.time() - os.path.getmtime(p) > age:
            shutil.rmtree(p, ignore_errors=True)
            n += 1
    return n


# ---------------------------------------------------------------------------
# Excel-Exporte
# ---------------------------------------------------------------------------

def _last(d: dict, months: List[str]):
    for m in reversed(months):
        if d.get(m) is not None:
            return d[m]
    return None


EXPORT_FILE_KEYS = {"balance": "xf_balance", "cashflow": "xf_cashflow", "planning": "xf_planning", "tax": "xf_tax", "transactions": "xf_transactions",
                    "holdings": "xf_holdings", "receipts": "xf_receipts", "accounts": "xf_accounts"}       # Dateiname je Export (Sprachkatalog)


def account_history(app: "App", uuid: str, quelle: Optional[str] = None) -> dict:
    """Verlauf eines Kontos fuer das Verlauf-Fenster. Mit MoneyMoney-Stand im Speicher direkt fuer dieses eine Konto
    gerechnet (Millisekunden, unabhaengig vom Neubau der gesamten Auswertung), sonst aus dem letzten Bericht."""
    st = app.store.load_shared("state.json", {}) or {}
    hist = dict((st.get("history") or {}).get(uuid) or {})
    snaps = {mk: v[uuid] for mk, v in (st.get("snapshots") or {}).items() if uuid in v}
    mmh = app.store.load_shared(MM_HISTORY_FILE, {}) or {}
    mmv, mm_start = dict((mmh.get("accounts") or {}).get(uuid) or {}), (mmh.get("opening") or {}).get(uuid)
    vcfg = (app.config.get("balance") or {}).get("history_source") or {}
    explizit = next((v for ref, v in vcfg.items() if ref.split("|")[0].strip() == uuid and v in ("transactions", "balances")), None)
    ledger = app.ledger
    acc = ledger.accounts.get(uuid) if ledger is not None else None
    if acc is not None and acc.group:                    # a group of accounts has no balances of its own
        raise ValueError(tr("s_verlauf_nur_konto"))
    ds = app.store.load_shared("dataset.json", {}) or {}
    kinfo = next((x for x in ds.get("accounts", []) if x.get("uuid") == uuid), {})
    depot = bool(acc.portfolio) if acc else bool(kinfo.get("depot"))
    q = quelle or explizit or ("balances" if depot else "transactions")
    out = {"account": uuid, "name": acc.name if acc else kinfo.get("name", ""), "source": q, "source_explicit": bool(explizit or quelle),
           "source_saved": explizit or ("balances" if depot else "transactions"),
           "depot": depot, "manual": hist, "recorded": snaps, "moneymoney": mmv, "amounts": {}, "hint": None, "anchor": [],
           "live": acc is not None, "report_running": app.bericht_status().get("running", False)}
    if acc is not None:
        today = date.today()
        months = account_months(ledger, acc, today, list(hist) + list(mmv) + (list(snaps) if depot else []))
        werte, hinweis, anker = account_balance_series(ledger, acc, months, q, st.get("snapshots") or {}, hist, today, app.config, mmv, mm_start)
        out.update({"amounts": werte, "hint": hinweis, "anchor": anker})
        # Pruefung der Rueckrechnung: vorgemerkte Umsaetze, Anfangssaldo vor der ersten Buchung
        alle = ledger.transactions(uuid, booked_only=False)
        vorgemerkt = [t for t in alle if not t.booked]
        gebucht = [t for t in alle if t.booked]
        info = {"pending_count": len(vorgemerkt), "pending_sum": round(sum(t.amount for t in vorgemerkt), 2),
                "bookings": len(gebucht), "first_booking": min((t.booking_date for t in gebucht), default=None),
                "opening_balance": round(acc.balance - sum(t.amount for t in gebucht), 2)}
        if info["first_booking"]:
            info["first_booking"] = info["first_booking"].isoformat()
        out["check"] = info
    else:
        for b in ds.get("areas", {}).values():
            for r in (b.get("balance") or {}).get("rows") or []:
                if r.get("id") == uuid:
                    out["amounts"] = r.get("amounts") or {}
    return out


ENTRY_LOCK = threading.RLock()        # balances and planning values: read, changed and saved in one go (the pages and the assistant's entries)


_PLAIN_NUMBER = re.compile(r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?")


def number_in(v) -> float:
    """An amount as the pages send it: a number, or its plain text (digits and at most one decimal sign). A text with group
    signs ("1.234,56", "250,000.00") is refused rather than read one way or the other -- the page turns what you type into a
    number, in the notation of your language."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        x = float(v)
    elif isinstance(v, str) and _PLAIN_NUMBER.fullmatch(v.strip()):
        x = float(v.strip().replace(",", "."))
    else:
        raise ValueError(tr("s_zahl_unlesbar") % str(v)[:40])
    if x != x or x in (float("inf"), float("-inf")):
        raise ValueError(tr("s_zahl_unlesbar") % str(v)[:40])
    return x


def account_history_set(app: "App", body: dict) -> dict:
    uuid = str(body.get("account") or "")
    if not uuid:
        raise ValueError(tr("s_konto_fehlt"))
    n = 0
    sent: Dict[str, Optional[float]] = {}          # read before anything is changed: one value that is no number, and nothing is saved
    for mk, v in (body.get("amounts") or {}).items():
        mk = str(mk)[:7]
        if len(mk) == 7 and mk[:4].isdigit() and mk[5:7].isdigit():
            sent[mk] = None if v in (None, "") else number_in(v)

    def _apply(st):
        nonlocal n
        hist = st.setdefault("history", {}).setdefault(uuid, {})
        for mk, v in sent.items():
            if v is None:
                hist.pop(mk, None)
            else:
                hist[mk] = v
            n += 1
        if body.get("delete"):
            st["history"].pop(uuid, None)
        if not hist:
            st["history"].pop(uuid, None)
    with ENTRY_LOCK:
        app.store.update("state.json", _apply, {})
    if body.get("source") in ("transactions", "balances"):
        cfg = copy.deepcopy(app.config)
        cfg.setdefault("balance", {}).setdefault("history_source", {})
        ref = next((("%s | %s" % (k["uuid"], k["name"])) for k in (app.store.load_shared("dataset.json", {}) or {}).get("accounts", []) if k["uuid"] == uuid), uuid)
        for k in list(cfg["balance"]["history_source"]):
            if k.split("|", 1)[0].strip() == uuid:
                cfg["balance"]["history_source"].pop(k)
        cfg["balance"]["history_source"][ref] = body["source"]
        app.save_config(cfg)
    ok, err = app.rebuild_report(wait=bool(body.get("wait")), grund="history")
    log.info("History of account %s: %d month(s) changed%s", uuid[:8], n, (", source " + body["source"]) if body.get("source") in ("transactions", "balances") else "")
    return {"ok": True, "report": ok, "text": err, "history": account_history(app, uuid)}


def plan_update(app: "App", body: dict) -> dict:
    with ENTRY_LOCK:
        return _plan_update(app, body)


def _plan_rule_set(rule: dict, body: dict, area: bool = False) -> Set[str]:
    """Writes the fields of a planning rule the request names (method, amount, increase) into rule; empty: the level above
    counts again. The fields that changed: "method" (with its amount), "increase"."""
    was = plan_rule(rule, area)
    if "method" in body:
        m = body.get("method") or ""
        if m and m not in (PLAN_AREA_METHODS if area else PLAN_METHODS):
            raise ValueError(tr("s_plan_methode"))
        if m:
            rule["method"] = str(m)
        else:
            rule.pop("method", None)
    for fld, dst in ((() if area else (("amount", "amount"),)) + (("increase", "increase_percent_pa"),)):
        if fld in body:
            v = body.get(fld)
            if v is None or str(v).strip() == "":
                rule.pop(dst, None)
            else:
                rule[dst] = number_in(v)
    if rule.get("method") in ("fix", "yearly_amount"):     # the amount is the method's: kept only where the method uses it
        rule.setdefault("amount", 0.0)
    else:
        rule.pop("amount", None)
    now = plan_rule(rule, area)
    return {f for f, ks in (("method", ("method", "amount")), ("increase", ("increase_percent_pa",))) if any(was.get(k) != now.get(k) for k in ks)}


def _plan_tidy(plan: dict) -> None:
    """Empty rules, categories and rows go (nothing of yours is in them)."""
    rows = plan.get("rows") if isinstance(plan.get("rows"), dict) else {}
    for key in list(rows):
        cfg = rows[key]
        if isinstance(cfg, dict):
            cats = cfg.get("categories") if isinstance(cfg.get("categories"), dict) else None
            for c in list(cats or {}):
                if isinstance(cats[c], dict) and not cats[c].get("amounts"):
                    cats[c].pop("amounts", None)
                if not cats[c]:
                    cats.pop(c)
            if cats is not None and not cats:
                cfg.pop("categories", None)
            if not cfg.get("amounts"):
                cfg.pop("amounts", None)
        if not cfg:
            rows.pop(key)
    if "rows" in plan and not rows:
        plan.pop("rows", None)
    d = plan.get("defaults")
    if isinstance(d, dict):
        for side in list(d):
            if not d[side]:
                d.pop(side)
        if not d:
            plan.pop("defaults", None)


def _plan_run(app: "App", bereich: str, plan: dict) -> Optional[dict]:
    """The planning of an area with these settings (as the pages would show it), to see what a change does."""
    raw = (app.store.load_shared("dataset.json", None) or {}).get("areas") or {}
    if bereich not in raw or "error" in raw[bereich]:
        return None
    b = copy.deepcopy(raw[bereich])
    cfg = with_property_categories(app.config, app.ledger)
    apply_plan(b, plan, cfg, immo=immo_for_plan(cfg, bereich, immo_results(cfg, date.today())),
               ledger_resolve=app.ledger.resolve if app.ledger is not None else None)
    return b


def _plan_conflicts(app: "App", bereich: str, before: dict, after: dict, change: dict) -> Tuple[dict, dict]:
    """What a changed rule sits above: your own rules further down that set what it changes, and your own values whose
    suggestion it changes -- each with what would come instead. And the settings with all of them replaced by the change."""
    repl = copy.deepcopy(after)
    rows = repl.get("rows") if isinstance(repl.get("rows"), dict) else {}
    ds_old = _plan_run(app, bereich, before)
    zs = {s["name"] + "/" + z["row"]: (s["name"], z) for s in (ds_old or {}).get("cashflow", {}).get("sections", []) for z in s["rows"]}
    found_rules: List[dict] = []
    taken: List[Tuple[dict, dict, dict]] = []           # (a rule found, where it stood, what was taken out of it)

    def lower(cfg: Any, fields: Set[str], key: str, cat: Optional[str]) -> None:
        own = plan_rule(cfg)
        hit = {f for f in fields if ("method" if f == "method" else "increase_percent_pa") in own}
        if hit:
            out = {k: cfg.pop(k) for k in ((("method", "amount") if "method" in hit else ()) + (("increase_percent_pa",) if "increase" in hit else ())) if k in cfg}
            found_rules.append({"row": key, "category": cat, "own": own})
            taken.append((found_rules[-1], cfg, out))

    def reaches(key: str) -> bool:                       # a position the area's default plans (not a fixed row, not a one-off)
        sec, z = zs.get(key, (key.split("/", 1)[0], {}))
        return ((z.get("plan") or {}).get("rule") or {}).get("from") != "fixed" and not plan_one_off(sec, z)

    def side_of(key: str) -> str:                        # the side that plans a row: investment income income's (report.plan_sec)
        sec, z = zs.get(key, (key.split("/", 1)[0], {}))
        return plan_sec(sec, z)
    if change["level"] == "area":
        for side, fields in change["sides"].items():
            for key, cfg in rows.items():
                sec = side_of(key)
                here = {f for f in fields if sec in (PLAN_SIDES[side] if f == "method" else (side,))}
                if not here or not isinstance(cfg, dict) or not reaches(key):
                    continue
                lower(cfg, here, key, None)
                for cat, cc in (cfg.get("categories") or {}).items():
                    lower(cc, here, key, cat)
    elif change["level"] == "position" and isinstance(rows.get(change["key"]), dict):
        for cat, cc in (rows[change["key"]].get("categories") or {}).items():
            lower(cc, change["fields"], change["key"], cat)
    ds_new = _plan_run(app, bereich, repl)
    if ds_old is None or ds_new is None:
        return {"values": [], "rules": found_rules}, repl
    new_rows = {s["name"] + "/" + z["row"]: z for s in ds_new["cashflow"]["sections"] for z in s["rows"]}
    old_rows = {s["name"] + "/" + z["row"]: z for s in ds_old["cashflow"]["sections"] for z in s["rows"]}

    def plan_of(z: Optional[dict], cat: Optional[str]) -> dict:
        if z is None:
            return {}
        if cat is None:
            return z.get("plan") or {}
        return next(((d.get("plan") or {}) for d in z.get("details") or [] if (d.get("category") or "") == cat), {})
    for r in found_rules:                                # what comes instead: the rule in effect after the change
        r["new"] = {k: v for k, v in (plan_of(new_rows.get(r["row"]), r["category"]).get("rule") or {}).items() if k in ("method", "amount", "increase", "from", "inc_from")}
    for r, cfg, out in taken:                            # what the change would set anyway is no conflict: it stays (the figures are the same)
        same = (out.get("method") is None or (out["method"] == r["new"].get("method") and out["method"] not in ("fix", "yearly_amount"))) \
            and (out.get("increase_percent_pa") is None or abs(float(out["increase_percent_pa"]) - float(r["new"].get("increase") or 0.0)) < 1e-9)
        if same:
            cfg.update(out)
            found_rules.remove(r)
    found_values: List[dict] = []
    for key, cfg in rows.items():
        if not isinstance(cfg, dict) or (change["level"] != "area" and key != change["key"]):
            continue
        places = [(None, cfg)] if change["level"] != "category" else []
        places += [(c, cc) for c, cc in (cfg.get("categories") or {}).items() if isinstance(cc, dict) and (change["level"] != "category" or c == change["cat"])]
        for cat, where in places:
            old_p, new_p = plan_of(old_rows.get(key), cat).get("proposal") or {}, plan_of(new_rows.get(key), cat).get("proposal") or {}
            for mk, v in sorted((where.get("amounts") or {}).items()):
                if mk in new_p and abs((old_p.get(mk) or 0.0) - new_p[mk]) >= 0.005:
                    found_values.append({"row": key, "category": cat, "month": mk, "own": v, "new": new_p[mk]})
                    where["amounts"].pop(mk)
    _plan_tidy(repl)
    return {"values": found_values, "rules": found_rules}, repl


def _conflict_key(found: Any) -> list:
    """What a change would keep or replace, comparable however it travelled (JSON from the page: 2 for 2.0)."""
    num = lambda v: round(float(v), 2) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
    rule = lambda r: sorted((k, num(v)) for k, v in (r or {}).items()) if isinstance(r, dict) else []
    f = found if isinstance(found, dict) else {}
    return [sorted((str(v.get("row")), str(v.get("category")), str(v.get("month")), num(v.get("own")), num(v.get("new"))) for v in f.get("values") or [] if isinstance(v, dict)),
            sorted((str(r.get("row")), str(r.get("category")), rule(r.get("own")), rule(r.get("new"))) for r in f.get("rules") or [] if isinstance(r, dict))]


def plan_restore(app: "App", bereich: str, parts: dict) -> None:
    """Puts back what the planning's rules and values were (the assistant taking back a change of its own) -- checked as a backup is."""
    with ENTRY_LOCK:
        _plan_restore(app, bereich, parts)


def _plan_restore(app: "App", bereich: str, parts: dict) -> None:
    plan_all = app.plan_all()
    cand = copy.deepcopy(plan_all["areas"].get(bereich) or {})
    for k in ("rows", "defaults"):
        if parts.get(k) is None:
            cand.pop(k, None)
        else:
            cand[k] = copy.deepcopy(parts[k])
    if not _plan_form({"areas": {bereich: cand}}):
        raise ValueError(tr("s_ki_inzwischen_geaendert"))
    plan_all["areas"][bereich] = cand
    app.store.save("plan.json", plan_all)


def _plan_update(app: "App", body: dict) -> dict:
    plan_all = app.plan_all()
    bereich = str(body.get("area") or (app.store.load_shared("dataset.json", {}) or {}).get("main_area") or "")
    if not bereich:
        raise ValueError(tr("s_kein_bereich"))
    plan = plan_all["areas"].setdefault(bereich, {})
    if body.get("reset_flag"):
        plan_all["areas"][bereich] = {}
        app.store.save("plan.json", plan_all)
        return {"ok": True, "plan": {}}
    change: Optional[dict] = None
    if "parameter" in body:
        for k, v in (body["parameter"] or {}).items():
            if k in PLAN_PARAMS:
                if v in (None, ""):
                    plan.pop(k, None)
                else:
                    plan[k] = v
    if "loans" in body:
        d = plan.setdefault("loans", {})
        for name, params in (body["loans"] or {}).items():
            if params is None:
                d.pop(name, None)
            else:
                d[name] = {k: v for k, v in params.items() if k in ("interest_percent_pa", "model", "payment") and v not in (None, "")}
                if not d[name]:
                    d.pop(name, None)
    if "appreciation" in body:
        w = plan.setdefault("appreciation", {})
        for name, params in (body["appreciation"] or {}).items():
            if params is None:
                w.pop(name, None)
            else:
                entry = {k: float(v) for k, v in params.items() if k in ("percent_pa", "base", "share") and v not in (None, "")}
                if params.get("area"):
                    entry["area"] = str(params["area"])
                    entry.setdefault("share", 1.0)
                w[name] = entry
                if not w[name]:
                    w.pop(name, None)
    if "event" in body:
        ev = body["event"] or {}
        lst = plan.setdefault("events", [])
        if ev.get("delete"):
            plan["events"] = [e for e in lst if str(e.get("id")) != str(ev.get("id"))]
        else:
            clean = {"id": str(ev.get("id") or ("e%d" % int(time.time() * 1000 % 10 ** 9))), "text": str(ev.get("text") or "Ereignis")[:80],
                     "month": str(ev.get("month") or "")[:7], "amount": number_in(ev.get("amount") or 0),
                     "kind": ev.get("kind") if ev.get("kind") in ("reallocation", "income", "expense") else "reallocation",
                     "date_from": ev.get("date_from") or None, "after": ev.get("after") or None,
                     "recurrence": ev.get("recurrence") if ev.get("recurrence") in ("once", "monthly", "quarterly", "yearly") else "once",
                     "date_to": (str(ev.get("date_to") or "")[:7] or None), "active": ev.get("active", True)}
            if len(clean["month"]) != 7:
                raise ValueError(tr("s_monat_fehlt"))
            idx = next((i for i, e in enumerate(lst) if str(e.get("id")) == clean["id"]), None)
            if idx is None:
                lst.append(clean)
            else:
                lst[idx] = clean
        if not plan.get("events"):
            plan.pop("events", None)
    before = copy.deepcopy(plan)                         # (after the rates: what a rule beneath it sits under is its own change only)
    key = str(body.get("row") or "")
    if key:
        zeilen = plan.setdefault("rows", {})
        row = zeilen.setdefault(key, {})
        cat = body.get("category")                       # a category inside the position ("": without a category, estimated)
        if cat is not None:
            row.setdefault("categories", {})
            target = row["categories"].setdefault(str(cat), {})
        else:
            target = row
        if "month" in body or isinstance(body.get("months"), dict):          # one month -- or several at once ("months": month -> value), saved together
            werte = target.setdefault("amounts", {})
            for mk, val in ([(body["month"], body.get("value", ""))] if "month" in body else list(body["months"].items())):
                if val is None or str(val).strip() == "":
                    werte.pop(mk, None)
                else:
                    werte[mk] = number_in(val)
        if body.get("clear_all_overrides"):
            target.pop("amounts", None)
        fields = _plan_rule_set(target, body)
        if fields:
            change = {"level": "position" if cat is None else "category", "key": key, "cat": None if cat is None else str(cat), "fields": fields}
    was = plan_defaults(plan)
    if isinstance(body.get("defaults"), dict):           # the area's default rule, per side
        d = plan.setdefault("defaults", {})
        for side in ("income", "expenses"):
            if isinstance(body["defaults"].get(side), dict):
                _plan_rule_set(d.setdefault(side, {}), body["defaults"][side], area=True)
    if body.get("model"):                                # a planning model: the area's default for both sides at once
        m = PLAN_MODELS.get(str(body["model"]))
        if m is None:
            raise ValueError(tr("s_plan_modell"))
        plan["defaults"] = copy.deepcopy(m)
    now = plan_defaults(plan)                            # what the area's default does now against before (not how it is written)
    sides = {side: {f for f, k in (("method", "method"), ("increase", "increase_percent_pa")) if was[side].get(k) != now[side].get(k)} for side in now}
    if any(sides.values()):
        change = {"level": "area", "sides": {k: v for k, v in sides.items() if v}}
    _plan_tidy(plan)
    mode = body.get("conflicts") or "keep"               # never anything of yours replaced unless you say so
    confirmed = body.get("confirmed") if isinstance(body.get("confirmed"), dict) else None      # the list you were shown (page, assistant's card)
    if mode == "replace" and confirmed is None:
        raise ValueError(tr("s_plan_anders"))            # replacing only ever what you were shown: without that list, nothing
    found, replaced = {"values": [], "rules": []}, plan
    if change and (mode in ("ask", "replace", "check") or confirmed is not None):
        found, replaced = _plan_conflicts(app, bereich, before, plan, change)
    if confirmed is not None and _conflict_key(found) != _conflict_key(confirmed):
        raise ValueError(tr("s_plan_anders"))            # what it would keep or replace is no longer what you were shown: nothing done
    if change and mode in ("ask", "replace", "check"):
        if mode == "check":                              # only what it would do (the assistant's card): nothing saved
            return {"ok": True, "changed": True, "conflicts": found, "defaults": plan_defaults(plan)}
        if mode == "ask" and (found["values"] or found["rules"]):
            return {"ok": False, "conflicts": found}     # nothing saved: the page asks you first
        if mode == "replace":
            plan_all["areas"][bereich] = replaced
    if mode == "check":
        return {"ok": True, "changed": bool(change), "conflicts": {"values": [], "rules": []}, "defaults": plan_defaults(plan)}
    app.store.save("plan.json", plan_all)
    return {"ok": True, "plan": plan_all["areas"].get(bereich, {})}


def filter_transactions(app: "App", q: dict):
    """The transactions page's filter (entity, year, account, search, direction, receipts, categories from a chart, ids,
    counted: only what the categories' counts count -- booked, MoneyMoney's own category):
    the matching transactions in their order, the receipt counts and all transactions -- for the list and its Excel export."""
    ums = app.umsatzliste()
    counts = Belege(app.store, app.config).counts()
    qs = (q.get("q") or "").lower().strip()
    # opened from a chart: these categories (and the ones below them) only
    want = None
    if q.get("categories"):
        try:
            got = json.loads(q["categories"])
            want = [categorize.norm_cat(c) for c in (got if isinstance(got, list) else []) if isinstance(c, str) and c.strip()]
        except ValueError:
            want = []
    only = None
    if q.get("ids"):                                   # bookings by their ids
        only = {int(x) for x in q["ids"].split(",") if x.strip().isdigit()}
    if q.get("cf_rows"):                               # the bookings behind cash flow rows in these months (a figure clicked)
        try:
            keys = json.loads(q["cf_rows"])
        except ValueError:
            keys = []
        months = [m for m in (q.get("cf_months") or "").split(",") if m]
        rows = ((app.store.load_shared("cf-ids.json", {}) or {}).get(str(q.get("cf_area") or "")) or {})
        only = {i for k in (keys if isinstance(keys, list) else []) if isinstance(k, str) for m in months for i in ((rows.get(k) or {}).get(m) or [])}
    out = []
    for t in ums:
        if only is not None and t["id"] not in only:
            continue
        if want is not None:
            k = categorize.norm_cat(t.get("category") or "")
            none_ok = (q.get("with_uncategorized") == "1" and not k and t.get("needs", True) and not t.get("transfer")
                       and not t.get("other_area"))          # between two of your areas: not an expense or income
            if not none_ok and (not k or not any(k == c or k.startswith(c + " / ") for c in want)):
                continue
        if q.get("counted") == "1" and (not t.get("booked_count") or t.get("source") != "moneymoney"):
            continue                                   # as the categories' counts: booked, with MoneyMoney's own category
        if q.get("year") and not t["date"].startswith(q["year"]):
            continue
        if q.get("account") and t["account"] != q["account"]:
            continue
        if q.get("entity") and t["entity"] != q["entity"]:
            continue
        if q.get("uncategorized") == "1" and (t["category"] or not t.get("needs", True) or t.get("transfer")):
            continue
        if q.get("without_receipt") == "1" and counts.get(t["id"]):
            continue
        if q.get("with_receipt") == "1" and not counts.get(t["id"]):
            continue
        if q.get("direction") == "out" and t["amount"] >= 0:
            continue
        if q.get("direction") == "in" and t["amount"] < 0:
            continue
        if q.get("from") and t["date"] < q["from"]:
            continue
        if q.get("to") and t["date"] > q["to"]:
            continue
        if qs and qs not in (t["name"] + " " + t["purpose"] + " " + t["category"] + " " + t["account_name"] + " " + str(t["amount"])).lower():
            continue
        out.append(t)
    return out, counts, ums


def export_sheets(app: App, was: str, bereich: Optional[str], modus: str, view: Optional[dict] = None, query: Optional[dict] = None) -> List[Sheet]:
    """view (balance sheet): the state of the table on screen -- open positions, open portfolios, hidden rows shown --
    so that the workbook opens like the page; everything else is in it too, collapsed (Excel's outline)."""
    ds = app.dataset()
    if ds.get("empty"):
        raise ValueError(tr("s_noch_keine_daten_zuerst_einen"))
    key = bereich or ds.get("main_area") or ""
    b = (ds.get("areas") or {}).get(key, {})
    name = (ds.get("area_names") or {}).get(key, "")
    if was in ("balance", "cashflow", "planning") and (not b or "error" in b):
        raise ValueError(tr("s_bereich_nicht_vorhanden_oder_fehlerhaf"))

    def columns(include_plan: bool):
        ist = b.get("months", [])
        plan = b.get("plan_months", []) if include_plan else []
        allm = ist + plan
        if modus == "years":
            years = sorted({m[:4] for m in allm})
            return [(y, [m for m in allm if m.startswith(y)], any(m in plan for m in allm if m.startswith(y))) for y in years]
        return [(m, [m], m in plan) for m in allm]

    if was == "balance":
        v = view or {}
        cols = columns(True)
        bil = b.get("balance", {})
        real = None
        if v.get("real"):                                   # in today's money, as the page shows it (price_index.py)
            real = app.price_factors(key, list(b.get("months") or []) + list(b.get("plan_months") or []),
                                     price_index.base_month(str(b.get("actual_until") or ""), date.today()))
            bil = price_index.deflate(bil, real["factors"])
        proj = {r["id"]: r.get("amounts") or {} for r in ((bil.get("projection") or {}).get("rows") or [])}
        allw = lambda r: dict(r.get("amounts") or {}, **proj.get(r.get("id"), {}))
        inakt = int(((app.config.get("balance") or {}).get("inactive_months") or 12))
        recent = (b.get("months") or [])[-inakt:]
        empty = lambda w: all(_last(w, ms) is None or abs(_last(w, ms)) < 0.005 for _, ms, _p in cols)
        rows, bold, levels, hidden = [], [], [], []

        def add(label, w, level, hide, strong=False):
            rows.append([label] + [_last(w, ms) for _, ms, _p in cols])
            levels.append(level)
            if strong:
                bold.append(len(rows) - 1)
            if hide:
                hidden.append(len(rows) - 1)
        role_open = False
        for r in bil.get("rows", []):
            if r["group"]:
                role_open = r["role"] in v.get("open", ())
                add(r["name"], allw(r), 0, False, True)
                continue
            skip = not v.get("all") and (r.get("inactive") or empty(allw(r)))
            add("    " + r["name"], allw(r), 1, not role_open or skip)
            dep_open = role_open and not skip and r["id"] in v.get("dep", ())
            for w in r.get("securities") or []:
                gone = not v.get("all") and (empty(w["amounts"]) or not any(w["amounts"].get(m) not in (None, 0) for m in recent))
                add("        " + w["name"] + (" (%s)" % w["isin"] if w.get("isin") and w["isin"] != w["name"] else ""), w["amounts"], 2, not dep_open or gone)
        nw = dict(bil.get("net_worth", {}), **((bil.get("projection") or {}).get("net_worth") or {}))
        add(tr("x_nettovermoegen"), nw, 0, False, True)
        add(tr("x_davon_liquide"), bil.get("liquid_net_worth", {}), 0, False)
        for role in dict.fromkeys(r["role"] for r in bil.get("outside") or []):       # outside net worth, collapsed per kind
            accs = [r for r in bil["outside"] if r["role"] == role]
            fx = role == "foreign_currency"                     # other currencies: each in its own, no sum
            tot = {} if fx else {m: round(sum((r["amounts"].get(m) or 0.0) for r in accs), 2) for m in {m for r in accs for m in r["amounts"]}}
            add((tr("fremdwaehrung_nicht_umgerechnet") if fx else role_label(role) + " (" + tr("x_nicht_im_nw") + ")"), tot, 0, False, True)
            for r in accs:
                add("    " + r["name"] + (" (%s)" % r.get("currency") if fx else ""), r["amounts"], 1, role not in v.get("open", ()))
        if real:                                            # what the figures are: the money of which month, the index until when
            rows += [[""], [tr("x_kaufkraft") % (real["base"], real["known_until"], ("%.1f" % real["rate"]) if i18n.lang() == "en" else ("%.1f" % real["rate"]).replace(".", ","))]]
            levels += [0, 0]
        head = [tr("x_konto")] + [c[0] + (tr("x_plan_suffix") if c[2] else "") for c in cols]
        return [Sheet(tr("x_bilanz") + " " + name, head, rows, bold_rows=bold, levels=levels, hidden_rows=hidden)]

    if was in ("cashflow", "planning"):
        cols = columns(True)
        rows, bold, levels, hidden = [], [], [], []

        def line(r, level=0, hide=False):
            rows.append(r); levels.append(level)
            if hide:
                hidden.append(len(rows) - 1)
        # as on the page: operating (income, expenses), investing and financing by kind, the change in cash between the cash at
        # the start and at the end, changes in value, the change in net worth -- each with its sum; the rows beneath grouped
        secs = {sek["name"]: sek for sek in b.get("cashflow", {}).get("sections", [])}
        sums = b.get("cashflow", {}).get("sums", {})
        ue = b.get("cashflow", {}).get("reconciliation", {}) or {}
        all_m = sorted(sums)
        total = lambda k: [round(sum((sums.get(m) or {}).get(k, 0.0) for m in ms), 2) for _, ms, _p in cols]
        allv = lambda z: dict(z["amounts"], **((z.get("plan") or {}).get("amounts", {})))
        val = lambda z: [round(sum(allv(z).get(m, 0.0) for m in ms), 2) for _, ms, _p in cols]

        def section(name, label, level):
            sek = secs.get(name)
            if not sek or not sek["rows"]:
                return
            line(["    " * level + label] + total(name), level); bold.append(len(rows) - 1)
            groups = {}
            for z in sek["rows"]:
                groups.setdefault(z["group"], []).append(z)
            for g, zs in groups.items():
                single = len(zs) == 1 and zs[0]["row"] == g
                depth = level + 1
                if not single:
                    glabel = tr(*zs[0]["glbl"]) if zs[0].get("glbl") else g
                    line(["    " * depth + glabel] + [round(sum(v), 2) for v in zip(*[val(z) for z in zs])], depth)
                    depth += 1
                for z in zs:
                    line(["    " * depth + (tr(*z["lbl"]) if z.get("lbl") else z["row"])] + val(z), depth, not single and depth > level + 2)
                    for d in z.get("details") or []:             # the categories inside a position (collapsed; plan columns: their plan, where they have one)
                        dv = dict(d["amounts"], **((d.get("plan") or {}).get("amounts") or {}))
                        line(["    " * (depth + 1) + (d["category"] or tr("cf_geschaetzt"))] + [None if p_ and not d.get("plan") else round(sum(dv.get(m, 0.0) for m in ms), 2) for _, ms, p_ in cols], depth + 1, True)
        line([tr("cf_operativ")] + total("operating")); bold.append(len(rows) - 1)
        section("income", tr("einnahmen"), 1)
        section("expenses", tr("ausgaben"), 1)
        for name, key in (("investing", "cf_investitionen"), ("financing", "cf_finanzierung"), ("unclear", "cf_unklar")):
            section(name, tr(key), 0)

        def balance(m):                                  # bank balance at the end of a month (None: not known or not there)
            return (sums.get(m) or {}).get("bank") if m else None

        def check(key):
            def cell(ms, plan):
                done = [m for m in ms if m <= b.get("actual_until", "")]
                if plan or not done or any(m not in ue for m in done):
                    return None                              # not every month checked: no claim
                offs = [ue[m][key] for m in done if abs(ue[m][key]) >= 0.005]
                if offs and abs(sum(offs)) < 0.005:
                    return tr("ue_ausgeglichen")             # months differ, but cancel out over the column
                return round(sum(offs), 2) if offs else 0.0
            line([tr("cf_abgleich")] + [cell(ms, p_) for _, ms, p_ in cols])
        line([tr("bankguthaben_anfang")] + [balance(all_m[all_m.index(ms[0]) - 1] if ms and ms[0] in all_m and all_m.index(ms[0]) > 0 else None) for _, ms, _p in cols])
        line([tr("zahlungsfluss_gesamt_veraenderung_liqu")] + total("cash_change")); bold.append(len(rows) - 1)
        check("diff_cash")
        line([tr("bankguthaben_ende")] + [balance(ms[-1]) if ms else None for _, ms, _p in cols])
        # investing, repaying, loans: only moved between your accounts -- added back, the rows add up to the change in net worth
        moves = {}
        for name, sek in secs.items():
            if name != "valuation":
                for z in sek["rows"]:
                    if not z.get("nw"):
                        moves.setdefault(tr(*z["glbl"]) if z.get("glbl") else z["group"], []).append(z)
        mv = {g: [round(-sum(v), 2) for v in zip(*[val(z) for z in zs])] for g, zs in moves.items()}
        mv = {g: v for g, v in mv.items() if any(abs(x) >= 0.005 for x in v)}
        if mv:
            line([tr("cf_umschichtungen")] + [round(sum(v), 2) for v in zip(*mv.values())]); bold.append(len(rows) - 1)
            for g, v in mv.items():
                line(["    " + g] + v, 1)
        section("valuation", tr("cf_wertaenderungen"), 0)
        line([tr("cf_veraenderung_nv")] + total("net_worth_delta")); bold.append(len(rows) - 1)
        check("unexplained")
        head = [tr("x_position")] + [c[0] + (tr("x_plan_suffix") if c[2] else "") for c in cols]
        levels += [0] * (len(rows) - len(levels))
        sheets = [Sheet(tr("x_planung" if was == "planning" else "x_kapitalfluss") + " " + name, head, rows, bold_rows=bold, levels=levels, hidden_rows=hidden)]
        if was == "planning":
            pr = b.get("balance", {}).get("projection", {})
            pcols = [c for c in cols if c[2]]
            prow, pbold = [], []
            for r in pr.get("rows", []):
                prow.append(["    " * r["depth"] + r["name"]] + [_last(r["amounts"], ms) for _, ms, _p in pcols])
                if r.get("group"):
                    pbold.append(len(prow) - 1)
            prow.append([tr("x_nw_plan")] + [_last(pr.get("net_worth", {}), ms) for _, ms, _p in pcols]); pbold.append(len(prow) - 1)
            prow.append([tr("x_liq_plan")] + [_last(pr.get("cash", {}), ms) for _, ms, _p in pcols])
            sheets.append(Sheet(tr("x_fortschreibung"), [tr("x_position")] + [c[0] for c in pcols], prow, bold_rows=pbold))
            P = b.get("plan", {})
            prm = [[k, P.get(k)] for k in PLAN_PARAMS if k != "default_method"] + [["defaults", json.dumps(P.get("defaults") or {}, ensure_ascii=False)]]
            for zn, zc in (P.get("rows") or {}).items():
                prm.append([tr("x_zeile") % zn, json.dumps(zc, ensure_ascii=False)])
            sheets.append(Sheet(tr("x_parameter"), [tr("x_parameter"), tr("x_wert")], prm, widths=[40, 60], freeze="A2"))
        return sheets

    if was == "tax":
        T = ds.get("tax", {})
        sheets = []
        for ent in T.get("entities", []):
            rows, bold = [], []
            for y, J in sorted(ent["years"].items()):
                rows.append([y, "", None, None]); bold.append(len(rows) - 1)
                for pos, p in J["positions"].items():
                    rows.append(["", pos, p["amount"], None]); bold.append(len(rows) - 1)
                    for k in p["categories"]:
                        rows.append(["", "        " + k["path"], k["amount"], k["count"]])
                for o, d in J["properties_list"].items():
                    rows.append(["", tr("x_vermietung") % o, d["result"], None]); bold.append(len(rows) - 1)
                    for a, v in d["kinds"].items():
                        rows.append(["", "        " + a, v, None])
                    for l, v in d["debt_interest"].items():
                        rows.append(["", "        " + tr("x_schuldzinsen") % l, v, None])
                    rows.append(["", "        " + tr("x_afa"), -abs(d["depreciation"]) if d["depreciation"] else 0, None])
                if J["uncategorized_flag"]["count"]:
                    rows.append(["", tr("x_ohne_kategorie"), J["uncategorized_flag"]["amount"], J["uncategorized_flag"]["count"]])
            if ent.get("not_converted"):                 # as on the page: which accounts are not in it (another currency)
                rows.append(["", tr("steuer_nicht_umgerechnet", ", ".join("%s (%s)" % (x["account"], x["currency"]) for x in ent["not_converted"])), None, None])
            sheets.append(Sheet(ent["name"], [tr("x_jahr"), tr("x_position"), tr("x_betrag"), tr("x_buchungen")], rows, widths=[8, 56, 16, 12], freeze="A2", bold_rows=bold))
        return sheets or [Sheet(tr("x_steuer"), [tr("x_hinweis")], [[tr("x_keine_daten")]])]

    if was == "transactions":
        # as on the page: the filtered transactions, all of them (not only the first shown)
        if query is not None:
            ums, counts, _ = filter_transactions(app, query)
            bereich = query.get("entity") or None
            name = (ds.get("area_names") or {}).get(bereich or "", "")
        else:
            ums = app.umsatzliste()
            if bereich:
                ums = [u for u in ums if u["entity"] == bereich]
            counts = Belege(app.store, app.config).counts()
        rows = [[u["date"], u["account_name"] + (" (%s)" % u["currency"] if u.get("currency") else ""), u["name"], u["purpose"], u["amount"], u["category"],
                 counts.get(u["id"], 0), u["id"]] for u in ums]          # (another currency: named with the account -- never a euro amount)
        return [Sheet(tr("s_umsaetze") + (name if bereich else ""), [tr("x_datum"), tr("x_konto"), tr("x_name"), tr("x_zweck"), tr("x_betrag"), tr("x_kategorie"), tr("x_belege"), "ID"],
                      rows, widths=[12, 26, 30, 50, 14, 30, 8, 10], freeze="A2")]

    if was == "holdings":
        rows, bold = [], []
        for d in ds.get("depots", []):
            cur = d.get("currency") or "EUR"
            rows.append([d["name"] + ("" if cur == "EUR" else " (%s)" % cur), "", "", "", None, None, d["cost_basis"], d["sum"]]); bold.append(len(rows) - 1)
            for p in d["positions"]:
                rows.append(["", p["name"], p["isin"], p["asset_class"], p["quantity"], p["price"], p["cost_basis"], p["value"]])
        return [Sheet(tr("x_depots"), [tr("x_depot"), tr("x_position"), "ISIN", tr("x_klasse"), tr("x_menge"), tr("x_kurs"), tr("x_einstand"), tr("x_wert")], rows,
                      widths=[26, 36, 16, 14, 12, 12, 14, 14], freeze="A2", bold_rows=bold)]

    if was == "receipts":
        bl = Belege(app.store, app.config)
        names = {k["uuid"]: k["name"] for k in ds.get("accounts", [])}
        names.update(ds.get("area_names") or {})
        rows = [[e.get("date"), e.get("amount"), e.get("name"), names.get(e.get("account") or "", ""), names.get(e.get("entity") or "", ""),
                 e["path"], e.get("note", ""), e.get("tx_id")] for e in bl.entries()]
        return [Sheet(tr("x_belege"), [tr("x_datum"), tr("x_betrag"), tr("x_name"), tr("x_konto"), tr("x_bereich"), tr("x_datei"), tr("x_notiz"), tr("x_umsatz_id")], rows,
                      widths=[12, 14, 30, 26, 20, 50, 30, 10], freeze="A2")]

    if was == "accounts":
        rows = [["    " * k["depth"] + k["name"], k["uuid"],
                 tr("x_gruppe" if k["group"] else ("x_depot" if k["depot"] else ("x_manuell" if k["manual"] else "x_bank"))),
                 role_label(k["role"]) if k["role"] else "", k["balance_amount"], k.get("updated") or ""] for k in ds.get("accounts", [])]
        return [Sheet(tr("x_konten"), [tr("x_konto"), "UUID", tr("x_typ"), tr("x_rolle"), tr("x_saldo"), tr("x_aktualisiert")], rows, widths=[46, 38, 10, 16, 16, 18])]
    raise ValueError(tr("s_unbekannter_export") % was)


def _parse_balance_csv(text: str) -> Dict[str, Dict[str, float]]:
    """Kontoname -> {JJJJ-MM: Saldo am Monatsende} aus CSV-Text (Langformat oder Matrix), siehe history_import."""
    return history_import.balances_from_rows(history_import.read_csv_rows(text))


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def make_handler(app: App):
    """The request handler of a Kontor (or of its demo, DemoApp). Each request goes to the demo only with a valid session of
    the demo; everything else -- also every sign-in -- to the real Kontor."""
    class H(BaseHTTPRequestHandler):
        server_version = "Kontor"
        sys_version = ""
        timeout = 60                    # a connection that sends nothing (or stops reading) ends, its thread with it

        def _handed_over(self) -> bool:
            """The real Kontor or its demo -- decided anew for each request on the connection: True when the other one answered."""
            if "_home" not in self.__dict__:
                self._home = type(self)                   # the handler the connection came in with: the real Kontor's
            cls = _pick(self)
            if cls is type(self):
                return False
            self.__class__ = cls
            getattr(self, "do_" + self.command)()
            return True

        def log_message(self, fmt, *args):
            line, code = (str(args[0]) if args else ""), (str(args[1]) if len(args) > 1 else "")
            if line.startswith(("GET ", "HEAD ")) and code[:1] in ("2", "3"):
                return                          # reads that worked: no line each (polling every few seconds would fill the log)
            log.debug("%s %s %s", self.client_address[0], line.split("?", 1)[0], code)      # never the query: it can hold names

        # -- Hilfen --------------------------------------------------------
        def _remote(self) -> str:
            return self.client_address[0]

        def _loopback(self) -> bool:
            return auth.is_loopback(self._remote())

        def _cookie(self) -> Optional[str]:
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "kontor_session":
                    return v
            return None

        def _session(self) -> Optional[dict]:
            # a request the page sends without you having touched it for a minute (status poll, progress) is no activity
            if not app.store.is_open:                    # no data key in memory: nobody is signed in
                return None
            s = app.sessions.get(self._cookie(), touch=self.headers.get("X-Kontor-Background") != "1")
            for did in (s.get("device"), s.get("opened_by")) if s is not None else ():
                # its iPhone was removed at the Mac: the session is over (also one of the demo) -- the list not readable right
                # now (a passing error): it stays, but nothing changes from it meanwhile (_device_session finds no device)
                if did and (home_app.devices is None or home_app.devices.present(did) is False):
                    app.sessions.drop_device(did)
                    return None
            return s

        def _sec_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "img-src 'self' data: blob:; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")

        def _json(self, code: int, obj: Any, extra: Optional[Dict[str, str]] = None) -> None:
            if app.DEMO:
                obj = app.shown(obj)                     # its settings without the assistant's setup (model, trusted websites)
            body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
            self._raw(code, body, "application/json; charset=utf-8", extra)

        def _raw(self, code: int, body: bytes, ctype: str, extra: Optional[Dict[str, str]] = None, cache: str = "no-store") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self._sec_headers()
            if app.DEMO:
                self.send_header("X-Kontor-Demo", "1")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            view = memoryview(body)          # in parts: the connection's time limit counts per part, not for a large file as a whole
            for i in range(0, len(view), 262144):
                self.wfile.write(view[i:i + 262144])

        def _body(self, limit: int = MAX_BODY) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0:
                raise ValueError("Content-Length")
            if n > limit:
                raise ValueError(tr("s_anfrage_zu_gross_d_mb") % (n // 1048576, max(1, limit // 1048576)))
            raw = self.rfile.read(n) if n else b""
            self._raw_body = raw                         # as sent: what a confirmation with Face ID is bound to (_confirmed)
            obj = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(obj, dict):
                raise ValueError(tr("s_json_erwartet"))
            return obj

        def _signed_in(self, remote: str, via: str, body: dict, device: Optional[str] = None) -> None:
            """After a sign-in (password, Touch ID or an iPhone's passkey, checked as always): a session of the real Kontor --
            or, asked for ("demo"), one of its demo (DemoApp): the same sign-in, but made-up data in place of yours. device: the
            iPhone of a passkey -- the session is bound to it (in the demo: ends with it). At this Mac's own address the lock
            for "tailscale serve"/Funnel is looked at again right before (a Touch ID window may have been open for minutes)."""
            if self._loopback() and app.exposure_block():
                return self._refuse_exposed(app.exposure_block() or "exposed", "sign-in", read=False)
            if body.get("demo") is not True:
                s = app.sessions.create(remote, via, device=device)
                return self._json(200, {"ok": True, "csrf": s["csrf"]}, self._set_cookie(s["token"]))
            try:
                s = app.demo_box.open_session(remote, make_handler, via, opened_by=device)
            except ValueError as e:
                return self._json(429, {"error": str(e)})
            except Exception as e:
                log.exception("Demo not started")
                return self._json(500, {"error": tr("s_interner_fehler_s") % e})
            log.info("Demo opened from %s", remote)
            return self._json(200, {"ok": True, "csrf": s["csrf"], "demo": True}, self._set_cookie(s["token"]))

        def _proxied(self) -> bool:
            """Passed on by a proxy ("tailscale serve", Funnel, any other: they add such headers) -- such a request would arrive
            from this Mac itself and is never answered: Kontor never sits behind a proxy. Also a request whose header lines do not
            read cleanly (a line Python stops at, e.g. a space before the colon: what follows it would go unseen)."""
            h = self.headers
            if getattr(h, "defects", None) or (h.get_payload() or "").strip():
                return True
            return any(PROXIED.fullmatch(k.strip()) for k in h.keys())

        def _refuse_proxied(self) -> None:
            log.warning("Request passed on by a proxy refused (%s %s)", self.command, urlparse(self.path).path[:60])
            return self._refuse_unread(403, tr("s_weitergereicht"), {"proxied": True})

        def _refuse_exposed(self, why: str, what: str, read: bool = True) -> None:
            """Refused from this Mac's own address: "tailscale serve"/Funnel passes Kontor's port on (why "exposed") or Tailscale
            was not looked at yet since the start ("checking": a moment)."""
            if why == "checking":
                log.info("%s from this Mac waits: Tailscale not looked at yet since the start", what)
                text, code, extra = tr("s_ts_pruefe"), 503, {"checking": True}
            else:
                log.warning("%s refused from this Mac: Tailscale passes Kontor's port on", what)
                text, code, extra = tr("s_ts_weitergereicht"), 403, {"exposed": True}
            return self._refuse_unread(code, text, extra) if read else self._json(code, dict({"error": text}, **extra))

        def _refuse_unread(self, code: int, text: str, extra: Optional[dict] = None) -> None:
            """An answer without reading the request (a small body is read, so that the answer arrives; a larger one ends the connection)."""
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if 0 < n <= 65536:
                self.rfile.read(n)
            elif n:
                self.close_connection = True
            return self._json(code, dict({"error": text}, **(extra or {})))

        def _wrong_password(self, pw, key: str = "s_passwort_falsch") -> bool:
            """Kontor's password, asked again for something weighty: False when it is right. Otherwise the answer is sent
            (wrong -- counted like a failed sign-in --, or: too many wrong ones, wait) and True comes back."""
            ok = app.sessions.check_password(self._remote(), str(pw or ""), app.check_password)
            if ok:
                return False
            if ok is None:
                self._json(429, {"error": tr("s_zu_viele_fehlversuche") % app.sessions.locked(self._remote())})
            else:
                self._json(401, {"error": tr(key)})
            return True

        def _set_cookie(self, token: str, clear: bool = False) -> Dict[str, str]:
            secure = "; Secure" if isinstance(self.connection, ssl.SSLSocket) else ""
            if clear:
                return {"Set-Cookie": "kontor_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0" + secure}
            return {"Set-Cookie": "kontor_session=%s; Path=/; HttpOnly; SameSite=Strict" % token + secure}

        def _host_ok(self) -> bool:
            """On the address of this Mac (127.0.0.1) only loopback names are answered: a foreign web page whose name points
            to 127.0.0.1 (DNS rebinding) gets nothing. *.localhost always means this Mac in browsers."""
            try:
                bound = self.server.server_address[0]
            except Exception:
                return True
            if not auth.is_loopback(bound):
                return True
            host = (self.headers.get("Host") or "").strip().lower()
            name = host[1:host.index("]")] if host.startswith("[") and "]" in host else host.rsplit(":", 1)[0] if host.count(":") == 1 else host
            return name in ("127.0.0.1", "localhost", "::1") or name.endswith(".localhost")

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if not origin:
                return True
            return urlparse(origin).netloc == (self.headers.get("Host") or "")

        def _static(self, path: str) -> None:
            m = re.match(r"^/docs/img/((?:de|en)/[a-z0-9_]+\.png)$", path)      # help images (made-up sample data)
            if m:
                fp = os.path.join(HERE, "docs", "img", *m.group(1).split("/"))
                if not os.path.isfile(fp):
                    return self._raw(404, b"nicht gefunden", "text/plain; charset=utf-8")
                with open(fp, "rb") as f:
                    return self._raw(200, f.read(), "image/png", cache="max-age=86400")
            name = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/i18n.js": "i18n.js", "/app.css": "app.css",
                    "/icon.svg": "icon.svg", "/icon-180.png": "icon-180.png", "/icon-512.png": "icon-512.png",
                    "/manifest.webmanifest": "manifest.webmanifest", "/sw.js": "sw.js"}.get(path)
            fp = os.path.join(WEB_DIR, name) if name else None
            if not fp or not os.path.exists(fp):
                return self._raw(404, b"nicht gefunden", "text/plain; charset=utf-8")
            with open(fp, "rb") as f:
                body = f.read()
            if name in ("sw.js", "index.html"):
                body = body.replace(b"__VERSION__", version().encode("utf-8"))
            ctype = {"html": "text/html; charset=utf-8", "js": "application/javascript; charset=utf-8", "png": "image/png",
                     "css": "text/css; charset=utf-8", "svg": "image/svg+xml", "webmanifest": "application/manifest+json"}[name.rsplit(".", 1)[1]]
            self._raw(200, body, ctype, cache="no-cache")

        # -- GET -----------------------------------------------------------
        def do_GET(self):
            if self._handed_over():
                return
            u = urlparse(self.path)
            if self._proxied():
                return self._refuse_proxied()
            if not self._host_ok():
                return self._raw(421, b"falsche Adresse", "text/plain; charset=utf-8")
            if not u.path.startswith("/api/"):
                return self._static(u.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if app.DEMO:
                s = self._session()
                if u.path == "/api/session":
                    return self._json(200, {"signed_in": s is not None, "csrf": s["csrf"] if s else None, "demo": True, "setup_needed": False,
                                            "setup_local_only": False, "touchid": False, "touchid_available": False, "locked_seconds": 0, "passkey": False, "passkey_only": False,
                                            "local": self._loopback(), "instance": app.instance, "offline_copy": False, "version": version()})
                if not demo_allowed("GET", u.path):
                    return self._json(403, {"error": tr("s_demo_nicht_moeglich")})
            if u.path == "/api/session":
                s = self._session()
                setup = not app.password_set()           # nothing of the data is read here: the key file, the start settings
                locked = not app.store.is_open
                # an added iPhone signs in with Face ID (its passkey) while the data are open -- over https at Kontor's address
                pk = not setup and not locked and not self._loopback() and tls_connection(self.connection) and app.passkey_site() is not None \
                    and bool(app.devices is not None and app.devices.all())
                lock = app.exposure_block(EXPOSURE_WAIT) if self._loopback() else None       # (right after the start: a moment for the first look)
                return self._json(200, {"signed_in": s is not None, "csrf": s["csrf"] if s else None,
                                        "setup_needed": setup and self._loopback(),
                                        "setup_local_only": setup and not self._loopback(),
                                        # after a restart Touch ID opens the data only with its key in the key file
                                        "touchid": auth.touchid_available() and self._loopback() and app.touchid_on() and not setup
                                                   and (not locked or access.touchid_ready(app.data_dir)),
                                        "waiting": locked and not setup,           # the schedule and auto bookings wait for a sign-in
                                        "touchid_available": auth.touchid_available() and self._loopback(),
                                        "locked_seconds": app.sessions.locked(self._remote()), "local": self._loopback(), "instance": app.instance,
                                        "passkey": pk, "passkey_only": pk and app.passkey_only(),
                                        "exposed": lock == "exposed", "checking": lock == "checking",
                                        "offline_copy": app.offline_copy(), "version": version()})
            s = self._session()
            if s is None:
                return self._json(401, {"error": tr("s_nicht_angemeldet")})
            try:
                return self._get(u.path, q, s)
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            except (BrokenPipeError, ConnectionResetError):
                log.debug("GET %s: connection closed by client", u.path)
                return None
            except Exception as e:
                log.exception("GET %s", u.path)
                return self._json(500, {"error": tr("s_interner_fehler_s") % e})

        def _get(self, path: str, q: dict, s: dict):
            if path == "/api/status":
                st = app.status(self._loopback(), frisch=q.get("fresh") == "1")
                st["storage"]["damaged"] = app.set_aside()       # files that did not read at a sign-in and were set aside (App.unlock)
                if self._is_local(s):
                    st["read_only"], st["confirm"] = False, False
                else:                                    # from another device: changes only from an added iPhone, each with Face ID (also in the demo)
                    dsess = self._device_session(s)
                    dev = dsess is not None and dsess.get("changes") is True
                    st["read_only"] = not home_app.remote_changes() or not dev
                    st["read_only_why"] = "setting" if not home_app.remote_changes() else "" if dev else "device" if dsess is not None \
                        else "password" if home_app.passkey_site() else "http"
                    st["confirm"] = not st["read_only"]
                st["trusted"] = self._may_change(s)              # the page offers what is Mac-like (booking, taking back ...): at the Mac or an added iPhone
                st["exposed"] = app.exposed()                     # "tailscale serve"/Funnel passes Kontor on (Einstellungen -> Zugang says how to stop it)
                st["python"] = "" if app.DEMO else app.python_hint()       # what there is to do about Python (Einstellungen -> Updates)
                return self._json(200, st)
            if path == "/api/dataset":
                return self._json(200, app.dataset())
            if path == "/api/config":
                return self._json(200, app.config)
            if path == "/api/plan":
                return self._json(200, app.plan_for(q.get("area") or ""))
            if path == "/api/price_index":                # the balance sheet in today's money: the factor of each month (price_index.py)
                months = price_index.span(q.get("from") or "", q.get("to") or "")
                app.price_refresh_soon()
                return self._json(200, app.price_factors(q.get("area") or "", months, price_index.base_month(q.get("base") or "", date.today())))
            if path == "/api/accounts":
                ds = app.store.load_shared("dataset.json", {}) or {}
                if app.ledger is not None:
                    return self._json(200, {"accounts": account_tree(app.ledger, app.config, None, ds.get("areas") or None), "as_of": app.ledger_time.isoformat()})
                return self._json(200, {"accounts": ds.get("accounts", []), "as_of": ds.get("created")})
            if path == "/api/categories":
                return self._json(200, {"categories": app.categories()})
            if path == "/api/offline/verifier":
                rec = app.auth_record()
                return self._json(200, {"offline": rec.get("offline") if app.offline_copy() else None, "lock_minutes": int(app.config["ui"].get("lock_minutes", 15)),
                                        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M")})
            if path == "/api/sync":
                r = app.abruf() or {"newest": None, "accounts": [], "back": [], "back_count": 0}
                ds = app.store.load_shared("dataset.json", {}) or {}
                bereich = {k["uuid"]: k.get("area") or "" for k in ds.get("accounts") or []}
                # Depots: MoneyMoney gibt ihren Wertverlauf nicht heraus -- Kontor zeichnet ihn selbst auf (Monatsende-Staende)
                st = app.store.load_shared("state.json", {}) or {}
                snaps, hist = st.get("snapshots") or {}, st.get("history") or {}
                mmk = (app.store.load_shared(MM_HISTORY_FILE, {}) or {}).get("accounts") or {}
                depots = []
                for a in (app.ledger.accounts.values() if app.ledger is not None else []):
                    if a.group or not a.portfolio or not a.path:
                        continue
                    rec = sorted(mk for mk, v in snaps.items() if a.uuid in v)
                    own = sorted(mk for mk, v in (hist.get(a.uuid) or {}).items() if v is not None)
                    aus_mm = sorted(mmk.get(a.uuid) or {})
                    known = sorted(set(rec) | set(own) | set(aus_mm))
                    depots.append({"uuid": a.uuid, "name": a.name, "path": a.path, "area": bereich.get(a.uuid, ""),
                                   "recorded_since": rec[0] if rec else None, "own": len(own), "from_moneymoney": len(aus_mm), "first_balance": known[0] if known else None,
                                   "first_booking": None})
                return self._json(200, dict(r, accounts=[dict(k, area=bereich.get(k["uuid"], "")) for k in r["accounts"]], depots=depots, gaps=st.get("gaps") or [], mm_history_src=st.get("mm_history_src"),
                                            recorded_since=min(snaps) if snaps else None,
                                            read_at=app.ledger_time.strftime("%Y-%m-%d %H:%M") if app.ledger_time else None,
                                            full_read=app.full_read_info()))
            if path == "/api/runs":
                st = app.store.load("state.json", {}) or {}
                return self._json(200, {"last_run": st.get("last_run"), "history_source": list(reversed(st.get("history_source", []))),
                                        "created_at": kontor_bookings(app.ledger)[:500], "not_book": list(reversed(app.config.get("not_book") or [])),
                                        "local": self._may_change(s)})
            if path == "/api/log":
                n = max(1, min(2000, int(q.get("n", "300"))))
                try:
                    with open(os.path.join(app.data_dir, "kontor.log"), encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()[-n:]
                except FileNotFoundError:
                    lines = []
                return self._json(200, {"rows": [l.rstrip("\n") for l in lines]})
            if path == "/api/transactions":
                return self._json(200, self._umsaetze(q))
            if path == "/api/receipts":
                bl = Belege(app.store, app.config)
                return self._json(200, {"entry_list": [dict(e, status=file_status(bl.full_path(e))) if e.get("external") else e for e in reversed(bl.entries())],
                                        "missing": bl.check(), "folder": bl.folder, "files": bl.listing() if q.get("files") == "1" else []})
            if path == "/api/receipts/file":
                bl = Belege(app.store, app.config)
                e = next((x for x in bl.entries() if x["id"] == q.get("id")), None)
                if e is None:
                    return self._json(404, {"error": tr("s_beleg_nicht_im_index")})
                full = bl.servable(e)
                if not full:
                    return self._json(404, {"error": tr("s_datei_fehlt_oder_nicht_geladen") % e["path"]})
                with open(full, "rb") as f:
                    data = f.read()
                ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                disp = "inline" if ctype == "application/pdf" or (ctype.startswith("image/") and "svg" not in ctype) else "attachment"
                return self._raw(200, data, ctype, {"Content-Disposition": '%s; filename="%s"' % (disp, os.path.basename(full).replace('"', ""))})
            if path == "/api/export/property.xlsx":
                im = next((x for x in app.config.get("real_estate") or [] if str(x.get("id")) == q.get("id")), None)
                if not im:
                    return self._json(404, {"error": tr("s_immobilie_nicht_gefunden")})
                kalks = im.get("calcs") or []
                k = next((x for x in kalks if str(x.get("id")) == q.get("calculation")), None) or next((x for x in kalks if x.get("active")), kalks[0] if kalks else None)
                if not k:
                    return self._json(404, {"error": tr("s_keine_kalkulation")})
                res = realestate.berechne(k.get("inputs") or {}, date.today())
                data = workbook(realestate.sheets(res))
                return self._raw(200, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 {"Content-Disposition": 'attachment; filename="Kontor-%s-%s-%s.xlsx"' % (tr("xf_property"), str(im.get("name") or tr("x_objekt")).replace('"', "").replace("/", "-"), date.today().isoformat())})
            if path.startswith("/api/export/"):
                was = path[len("/api/export/"):].replace(".xlsx", "")
                view = {"open": set((q.get("open") or "").split(",")) - {""}, "dep": set((q.get("dep") or "").split(",")) - {""}, "all": q.get("all") == "1",
                        "real": q.get("real") == "1"}
                data = workbook(export_sheets(app, was, q.get("area"), "years" if q.get("mode") == "years" else "months", view, q if was == "transactions" else None))
                return self._raw(200, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 {"Content-Disposition": 'attachment; filename="Kontor-%s-%s.xlsx"' % (tr(EXPORT_FILE_KEYS[was]) if was in EXPORT_FILE_KEYS else was, date.today().isoformat())})
            if path == "/api/package/export":
                name = (q.get("name") or "Kontor-Einstellungen").replace('"', "")
                # zum Weitergeben an eine andere MoneyMoney-Installation: Konten ueber Namen/Pfade, ohne Planung und Daten
                pkg = export_package(app.config, name, strip_uuids=True, plan=None, ledger=app.ledger)
                return self._raw(200, json.dumps(pkg, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="%s.kontor.json"' % name})
            if path == "/api/assistant/status":
                if not self._assistant_ok(s):
                    return self._json(200, {"settings": {"enabled": False}, "local": False, "remote_off": True})
                return self._json(200, app.assistant.status(self._is_local(s)))
            if path == "/api/assistant/load":                     # what the models take of this Mac right now (the chart under Settings -> Assistant, while it is on screen): only at the Mac
                if not self._is_local(s) or not self._assistant_ok(s):
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                return self._json(200, app.assistant.load())
            if path in ("/api/assistant/chats", "/api/assistant/chat"):        # saved conversations: where one may ask, one may read them again
                if not self._assistant_ok(s):
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                if path == "/api/assistant/chats":
                    return self._json(200, {"chats": app.assistant.chats(), "save": assistant_mod.settings(app.config)["save_chats"]})
                got = app.assistant.chat(str(q.get("id") or ""))
                return self._json(200, got) if got else self._json(404, {"error": tr("s_ki_verlauf_weg")})
            if path == "/api/assistant/changes":                  # the log of what the assistant changed (after the user's click)
                if not self._assistant_ok(s):
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                return self._json(200, {"changes": app.assistant.changes(self._trusted(s))})
            if path == "/api/assistant/memory":                   # what the assistant was told to remember: the list, at the Mac or on an added iPhone (with its right "remote")
                if not self._trusted(s) or not self._assistant_ok(s):
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                return self._json(200, app.assistant.memory_list(q))
            if path == "/api/assistant/memory/export":            # ... and all of it as one file in an open format, to read and to carry elsewhere: only at the Mac
                if not self._at_mac(s):
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                out = app.assistant.memory_export(version())
                return self._raw(200, out["text"].encode("utf-8"), "text/markdown; charset=utf-8", {"Content-Disposition": 'attachment; filename="%s"' % out["name"]})
            if path == "/api/assistant/file":                     # a file given in the chat, opened again from its name: from memory, only in its conversation (assistant.file_shown)
                if not self._assistant_ok(s):
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                if not assistant_mod.settings(app.config)["enabled"]:         # (opened in a window of its own: a line to read there, not JSON)
                    return self._raw(403, tr("s_ki_aus").encode("utf-8"), "text/plain; charset=utf-8")
                f = app.assistant.file_shown(q.get("id"), q.get("conversation"))
                if f is None:
                    return self._raw(404, tr("s_ki_datei_weg").encode("utf-8"), "text/plain; charset=utf-8")
                return self._raw(200, f["data"], f["type"], {"Content-Disposition": _disposition("inline" if f["inline"] else "attachment", f["name"])})
            if path == "/api/assistant/poll":
                if not self._assistant_ok(s):
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                return self._json(200, app.assistant.poll(str(q.get("job") or ""), int(q.get("after") or 0) if str(q.get("after") or "0").isdigit() else 0))
            if path == "/api/help":
                # help = docs/help.de.md or docs/help.en.md (the same file as on GitHub)
                fn = "help.en.md" if (q.get("lang") or (app.config.get("ui") or {}).get("language")) == "en" else "help.de.md"
                try:
                    with open(os.path.join(HERE, "docs", fn), encoding="utf-8") as f:
                        text = f.read()
                except OSError:
                    return self._json(200, {"text": "", "images": {}})
                return self._json(200, {"text": text, "images": help_image_sizes(text)})
            if path == "/api/remote/acl":                         # what Tailscale lets in, Tailnet Lock, Funnel/serve -- read only, one look at a time
                if not self._trusted(s):
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                return self._json(200, app.remote_acl(fresh=q.get("fresh") == "1"))
            if path == "/api/devices":                            # the iPhones added (their passkeys), the link to add one -- only at the Mac
                if not self._at_mac(s) or app.devices is None:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                site = app.passkey_site()
                return self._json(200, {"devices": [{"id": d["id"], "name": d["name"], "added": d.get("added"), "used": d.get("used"),
                                                     "changes": d.get("changes") is True, "current": bool(site) and d.get("rp") == site[0]}
                                                    for d in app.devices.all()],
                                        "pairing": self._pairing(), "passkeys": site is not None, "passkey_only": app.devices.passkey_only(),
                                        "read_only": app.remote_readonly(), "damaged": app.devices.damaged()})
            if path == "/api/remote":
                if q.get("fresh"):
                    app.tailscale(fresh=True)
                return self._json(200, dict(app.remote_info(), local=self._is_local(s)))
            if path == "/api/timemachine":
                return self._json(200, {"status": timemachine_status(app.data_dir)})
            if path == "/api/diagnostics":
                txt = diagnose(app.store, app.data_dir, app.config, app.status(self._loopback()), mask_names=q.get("names") != "1")
                return self._raw(200, txt.encode("utf-8"), "text/plain; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="Kontor-Diagnose-%s.txt"' % date.today().isoformat()})
            if path == "/api/check/status":
                return self._json(200, dict(getattr(app, "read_state", {"running": False}), now=time.time()))
            if path == "/api/update/status":
                return self._json(200, {"info": app.update_info, "verified": app.update_checked, "version": version(), "date": updates.installed_date(),
                                        "history": changelog.history(), "python": app.python.status(), "components": app.components()})
            if path == "/api/python":                    # while it is loaded and tried: how far it is
                return self._json(200, {"python": app.python.status(), "instance": app.instance})
            if path == "/api/history":
                return self._json(200, self._historie(q.get("account") or "", q.get("source") if q.get("source") in ("transactions", "balances") else None))
            if path == "/api/securities/lookup":
                return self._json(200, dict(app.securities_unnamed(), local=self._may_change(s)))
            if path == "/api/history/mm-status":
                return self._json(200, dict(app.mmh, local=self._is_local(s)))
            if path == "/api/categories/positions":
                if app.ledger is None:
                    return self._json(200, {"categories": [], "positions": [], "hint": tr("s_noch_kein_lauf_moneymoney_lesen")})
                return self._json(200, positions_overview(app.ledger, app.config, app.categories_raw, date.today()))
            if path == "/api/categories/written":
                return self._json(200, dict(app.categories_written(), local=self._may_change(s)))
            if path == "/api/categories/unassigned":
                if app.ledger is None:
                    return self._json(200, {"open": 0, "groups": [], "groups_total": 0, "hint": tr("s_noch_kein_lauf_moneymoney_lesen")})
                kat = categorize.load(app.store)
                areas = bereiche_for(app.ledger, app.config)
                res = open_category_items(app, int(q["year"]) if q.get("year") else None, q.get("area") or None, float(q.get("min") or 0),
                                          max(1, min(5000, int(q.get("limit") or 300))), q.get("level") or None)
                res["skipped"] = sorted(assign_skipped(app.config, areas))
                res["period_chosen"] = app.config.get("assign_from") is not None         # else the running year (not chosen yet)
                if getattr(app.ledger, "_paired", None) is None:
                    app.request_rebuild("assigning")              # which bookings are transfers comes with the report (page reloads then)
                res["transfer"] = transfer_category(app)[0]       # your category for transfers in MoneyMoney (a contribution or withdrawal between two areas)
                res["waiting"] = sum(1 for z in kat["assignment"].values() if categorize.waiting(z))      # written at the next sync
                res["written"] = len((app.store.load_shared("state.json", {}) or {}).get(mm_categories.LOG_KEY) or {})      # entered by Kontor (to take back)
                res["rule_proposals"] = len(app.rule_proposals(kat))
                res["doubts"] = category_doubts(app)["groups_total"]       # categories that make no sense to Kontor (the tab Auffällig)
                res["local"] = self._may_change(s)
                return self._json(200, res)
            if path == "/api/categories/doubts":
                if app.ledger is None:
                    return self._json(200, {"groups": [], "groups_total": 0, "count": 0})
                return self._json(200, dict(category_doubts(app), local=self._may_change(s)))
            if path == "/api/categories/proposals":
                if app.ledger is None:
                    return self._json(200, {"proposals": []})
                return self._json(200, {"proposals": app.rule_proposals(categorize.load(app.store))})
            if path == "/api/properties":
                return self._json(200, {"real_estate": app.config.get("real_estate") or [], "results": {k: {kk: vv for kk, vv in v.items() if kk != "series_data"}
                                                                                                        for k, v in immo_results(app.config, date.today()).items()}})
            if path == "/api/properties/template":
                return self._json(200, {"inputs": realestate.normalize({"name": "Neues Objekt", "transfer_date": date.today().replace(day=1).isoformat()})})
            return self._json(404, {"error": "unknown"})

        def _historie_einlesen(self, s: dict):
            """Kontostaende aus MoneyMoney: hochgeladene (verschluesselte) Datenbank nur in den Arbeitsspeicher lesen und im
            Hintergrund verarbeiten (Passwortfenster des Helfers); der Fortschritt kommt ueber /api/history/mm-status."""
            n = int(self.headers.get("Content-Length") or 0)

            def ablehnen(code: int, text: str, feld: str = "text"):
                # Rest der Datei verwerfen, damit der Browser die Antwort sicher erhaelt
                self.close_connection = True
                left, tmp = max(0, n), bytearray(1 << 20)
                while left > 0:
                    k = self.rfile.readinto(memoryview(tmp)[:min(left, len(tmp))])
                    if not k:
                        break
                    left -= k
                mm_history._wipe(tmp)
                return self._json(code, {"ok": False, feld: text})
            if not self._is_local(s):
                return ablehnen(403, tr("s_nur_direkt_am_mac_moeglich"), "error")
            if mm_history.AKTIV.is_set() or app.mmh.get("running"):
                return ablehnen(409, tr("s_laeuft_bereits_bitte_das_passwortfenst"), "error")
            if is_running():
                return ablehnen(200, tr("s_bitte_moneymoney_zuerst_beenden_q"))
            if app.ledger is None:
                return ablehnen(200, tr("s_erst_die_konten_aus_moneymoney"))
            try:
                buf = mm_history.receive(self.rfile, n)
            except mm_history.HistorieError as e:
                self.close_connection = True
                return self._json(200, {"ok": False, "text": str(e)})
            app.mmh = {"running": True, "step": "received", "result": None}
            threading.Thread(target=app.historie_einlesen, args=(buf,), name="kontor-mm-history", daemon=True).start()
            del buf
            return self._json(200, {"ok": True, "running": True})

        def _historie(self, uuid: str, quelle: Optional[str] = None) -> dict:
            return account_history(app, uuid, quelle)

        def _umsaetze(self, q: dict) -> dict:
            hits, counts, ums = filter_transactions(app, q)
            limit = max(1, min(5000, int(q.get("limit", "500"))))
            jahre = sorted({t["date"][:4] for t in ums}, reverse=True)
            out = [dict(t, receipts=counts.get(t["id"], 0)) for t in hits[:limit]]
            other: Dict[str, float] = {}                 # amounts in another currency: never in the sum in euros (Kontor does not convert)
            for t in hits:
                if t.get("currency"):
                    other[t["currency"]] = round(other.get(t["currency"], 0.0) + t["amount"], 2)
            return {"transactions": out, "hits": len(hits), "sum": round(sum(t["amount"] for t in hits if not t.get("currency")), 2),
                    "sum_other": other, "hits_other": sum(1 for t in hits if t.get("currency")), "total": len(ums), "years": jahre}

        # -- POST/PUT ------------------------------------------------------
        def do_POST(self):
            self._mutating()

        def do_PUT(self):
            self._mutating()

        def _mutating(self):
            if self._handed_over():
                return
            u = urlparse(self.path)
            self._raw_body = b""
            if self._proxied():
                return self._refuse_proxied()
            if not u.path.startswith("/api/") or not self._origin_ok() or not self._host_ok():
                return self._json(403, {"error": "rejected"})
            if self._loopback() and (u.path in SIGN_IN or u.path in MAC_ONLY):
                # "tailscale serve"/Funnel passes Kontor's port on: from this Mac's address may come anyone -- no sign-in (nor
                # Touch ID), nothing that stays at the Mac, until it is switched off; not looked yet since the start: the same,
                # a sign-in waits a moment for the first look (App.exposure_block)
                why = app.exposure_block(EXPOSURE_WAIT if u.path in SIGN_IN else 0.0)
                if why:
                    return self._refuse_exposed(why, u.path)
            before = u.path in SIGN_IN                   # the ways in: a password, a passkey, nothing large
            if app.DEMO and not demo_allowed("POST", u.path):     # (the ways in too: the demo knows no password)
                return self._refuse_unread(403, tr("s_demo_nicht_moeglich"))
            if not before and self._session() is None:          # not signed in: nothing is read (a small body only, so the answer arrives)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = -1
                if 0 < n <= 65536:
                    self.rfile.read(n)
                return self._json(401, {"error": tr("s_nicht_angemeldet")})
            try:
                body = {} if u.path == "/api/history/mm-import" else self._body(
                    65536 if before else MAX_UPLOAD if u.path == "/api/receipts/upload" else MAX_SPEECH if u.path in ("/api/assistant/transcribe", "/api/assistant/attach")
                    else MAX_RESTORE if u.path in ("/api/backup/restore", "/api/assistant/memory/import") else MAX_BODY)
            except (ValueError, json.JSONDecodeError) as e:
                return self._json(400, {"error": tr("s_ungueltige_anfrage_s") % e})
            remote = self._remote()
            if app.DEMO and not demo_allowed("POST", u.path, body):
                return self._json(403, {"error": tr("s_demo_nicht_moeglich")})

            if u.path == "/api/setup":
                err = auth.password_ok(str(body.get("password", "")))
                if self._loopback() and not err and not SETUP_LOCK.acquire(blocking=False):
                    return self._json(409, {"error": tr("s_einrichtung_laeuft")})        # a second click while the first sets it up: that one answers
                try:
                    if app.password_set() or not self._loopback():
                        return self._json(403, {"error": tr("s_einrichtung_nur_einmal_und_nur")})
                    if err:
                        return self._json(400, {"error": err})
                    try:
                        app.first_password(str(body["password"]))
                    except StoreError as e:
                        return self._json(409, {"error": str(e)})
                finally:
                    if self._loopback() and not err:
                        SETUP_LOCK.release()
                if isinstance(body.get("touchid"), bool) or body.get("language") in i18n.LANGS:
                    cfg = copy.deepcopy(app.config)
                    if isinstance(body.get("touchid"), bool):
                        cfg.setdefault("ui", {})["touchid"] = body["touchid"]
                    if body.get("language") in i18n.LANGS:
                        cfg.setdefault("ui", {})["language"] = body["language"]
                    app.save_config(cfg)
                if app.exposure_block():                 # (looked at again right before the session at this Mac's address)
                    return self._refuse_exposed(app.exposure_block() or "exposed", "setup", read=False)
                s = app.sessions.create(remote, "password")
                log.info("Password set, setup started")
                return self._json(200, {"ok": True, "csrf": s["csrf"]}, self._set_cookie(s["token"]))
            if body.get("demo") is True and u.path in ("/api/login", "/api/touchid", "/api/passkey/login") and app.sessions.get(self._cookie(), touch=False) is not None:
                return self._json(409, {"error": tr("s_demo_angemeldet"), "signed_in": True})      # the demo not over a session of yours here (another window signed in meanwhile)
            if u.path == "/api/login":
                wait = app.sessions.locked(remote)
                if wait:
                    return self._json(429, {"error": tr("s_zu_viele_fehlversuche") % wait})
                if not app.password_set():
                    return self._json(403, {"error": tr("s_noch_kein_passwort_festgelegt_einricht")})
                # from another device "only with Face ID of added devices": the password no longer signs in there while the data
                # are open -- after a restart it opens them once, and Face ID follows (never a session from the password alone)
                passkey_only = lambda: not self._loopback() and app.passkey_only() and app.passkey_site() is not None
                if app.store.is_open and passkey_only():
                    return self._json(403, {"error": tr("s_pk_nur_faceid"), "passkey_only": True})
                try:
                    ok = app.sessions.check_password(remote, str(body.get("password", "")), app.sign_in)
                except StoreError as e:                  # the key file does not read, or its key does not open the data
                    log.error("Sign-in: %s", e)
                    return self._json(409, {"error": str(e)})
                except Exception as e:
                    log.exception("Sign-in")
                    return self._json(500, {"error": tr("s_interner_fehler_s") % e})
                if ok is None:
                    return self._json(429, {"error": tr("s_zu_viele_fehlversuche") % app.sessions.locked(remote)})
                if ok:
                    app.touchid_cancel()                 # a Touch ID window still open: it opens nothing any more
                    rec = app.auth_record()
                    if not rec.get("offline"):                # (none: it was damaged and set aside at this sign-in)
                        pw = str(body.get("password", ""))
                        app.store.save("auth.json", auth.with_offline(rec if rec.get("alg") else auth.hash_password(pw), pw))
                        log.info("Offline verifier for the iPhone view created")
                    if passkey_only():
                        log.info("Password from %s opened the data -- the sign-in goes on with Face ID", remote)
                        return self._json(200, {"ok": False, "passkey_needed": True})
                    log.info("Login with password from %s", remote)
                    return self._signed_in(remote, "password", body)
                log.warning("Failed login from %s", remote)
                return self._json(401, {"error": tr("s_passwort_falsch")})
            if u.path == "/api/touchid":
                if not self._loopback() or not auth.touchid_available():
                    return self._json(403, {"error": tr("s_touch_id_nur_an_diesem")})
                if not app.touchid_on():
                    return self._json(403, {"error": tr("s_touch_id_ist_in_den")})
                if not app.password_set():
                    return self._json(403, {"error": tr("s_zuerst_ein_passwort_festlegen")})
                tid = str(body.get("tid") or "")
                # the one request running (a newer one replaces it); the demo or your data: decided once it is confirmed, as
                # the page wants it then (/api/touchid/switch) -- its window says what it opens
                req = app.touchid_begin(tid if TID_RE.fullmatch(tid) else secrets.token_hex(16), body.get("demo") is True)
                try:
                    ok = app.sign_in_touchid(req["demo"], req["id"])
                except StoreError as e:
                    log.error("Sign-in with Touch ID: %s", e)
                    return self._json(409, {"error": str(e)})
                except Exception as e:
                    log.exception("Sign-in with Touch ID")
                    return self._json(500, {"error": tr("s_interner_fehler_s") % e})
                finally:
                    demo, switched, over = app.touchid_end(req)
                if app.exposure_block():                  # found passed on meanwhile (its window ended with it): says so
                    return self._refuse_exposed(app.exposure_block() or "exposed", "Touch ID", read=False)
                if over:                                  # replaced (a newer request, a sign-in with the password): opens nothing
                    return self._json(409, {"error": tr("s_touch_id_nicht_bestaetigt"), "superseded": True})
                if switched:                              # switched meanwhile -- before or after its window was confirmed: nothing signs in,
                    return self._json(409, {"switched": True})      # the page asks anew, for what it wants now (its window says so)
                if not ok:
                    return self._json(401, {"error": tr("s_touch_id_nicht_bestaetigt")})
                if demo and app.sessions.get(self._cookie(), touch=False) is not None:
                    return self._json(409, {"error": tr("s_demo_angemeldet"), "signed_in": True})      # (switched to the demo meanwhile)
                log.info("Login with Touch ID")
                return self._signed_in(remote, "touchid", {"demo": demo})
            if u.path == "/api/touchid/switch":
                # the sign-in page switched between the demo and your data while its Touch ID window is open: only at this Mac,
                # only with the id of the request running; nothing signs in here
                if not self._loopback():
                    return self._json(403, {"error": tr("s_touch_id_nur_an_diesem")})
                if not isinstance(body.get("demo"), bool) or not app.touchid_switch(str(body.get("tid") or ""), body["demo"]):
                    return self._json(409, {"error": tr("s_touchid_keine_abfrage")})
                log.info("Touch ID: the sign-in switched to %s", "the demo" if body["demo"] else "the real Kontor")
                return self._json(200, {"ok": True})
            if u.path in SIGN_IN:                        # the passkey of an added iPhone, adding one
                return self._passkey(u.path, body, remote)

            s = self._session()
            if s is None:
                return self._json(401, {"error": tr("s_nicht_angemeldet")})
            if self.headers.get("X-CSRF-Token") != s["csrf"]:
                return self._json(403, {"error": tr("s_csrf_pruefung_fehlgeschlagen_seite_neu"), "csrf": "invalid"})
            if not self._is_local(s) and self._remote_check(u.path, body, s):     # from another device: at the Mac only, or a change without Face ID
                return None
            if u.path == "/api/history/mm-import":
                return self._historie_einlesen(s)
            t0 = time.time()
            log.debug("%s %s from %s (%d bytes%s)", self.command, u.path, remote, len(json.dumps(body)) if body else 0, ", Mac" if self._is_local(s) else "")
            try:
                res = self._route(u.path, body, s)
                log.debug("%s %s: done in %.2f s", self.command, u.path, time.time() - t0)
                return res
            except ValueError as e:
                log.warning("%s %s rejected (invalid input)", self.command, u.path)          # its text may name a category: not in the log
                return self._json(400, {"error": str(e)})
            except MoneyMoneyError as e:
                log.warning("%s %s: MoneyMoney not available: %s", self.command, u.path, e)
                return self._json(502, {"error": unavailable_text(e) or (tr("s_moneymoney_fehler_s") % e)})
            except (BrokenPipeError, ConnectionResetError):
                log.debug("%s %s: connection closed by client", self.command, u.path)
                return None
            except OSError as e:
                log.exception("%s %s: file error", self.command, u.path)
                return self._json(500, {"error": tr("s_dateifehler") % e})
            except Exception as e:
                log.exception("%s %s", self.command, u.path)
                return self._json(500, {"error": tr("s_interner_fehler_s") % e})

        def _is_local(self, s: dict) -> bool:
            return auth.is_loopback(s.get("remote", "")) and self._loopback()

        def _update_install(self, body: dict, s: dict):
            """Installs an update: only at the Mac; with findings in the new version's files it waits -- installed only with your
            approval for exactly those files, as the page sent it (update_guard keeps this function as a whole)."""
            if not self._is_local(s):
                return self._json(403, {"error": tr("s_updates_nur_von_diesem_mac")})
            res = updates.install((app.config.get("updates") or {}).get("repo") or "stecrz/Kontor", restart=True, approved=str(body.get("approved") or ""))
            if res.get("ok"):
                log.info("Update installed: %s", res.get("version"))
            elif res.get("needs_approval"):                    # shown under Updates (and marked in the menu) until you decide
                app.update_info = dict(app.update_info or {"current": version(), "newer": True, "error": None, "notes": "", "date": "", "source": "main"},
                                       available=res.get("version"), newer=True, review=res.get("review"))
            return self._json(200, res)

        # -- from another device: an added iPhone, Face ID for each change ------------------------------------------------
        def _device_session(self, s: Optional[dict]) -> Optional[dict]:
            """The iPhone this session was signed in from with its passkey (in the demo: the one whose passkey opened it) --
            while it is added, over https at Kontor's address in the Tailscale network. None otherwise (also for a session
            signed in with the password, and while the list does not read)."""
            did = (s.get("opened_by") if app.DEMO else s.get("device")) if s else None
            if not did or home_app.devices is None or not tls_connection(self.connection) or home_app.passkey_site() is None:
                return None
            return home_app.devices.get(did)

        def _device_may_change(self, s: Optional[dict]) -> bool:
            """An added iPhone that may change things: "Änderungen vom iPhone" on (all devices) and its own flag (each device,
            set at the Mac) -- every change then still with Face ID (_confirmed)."""
            dev = self._device_session(s)
            return dev is not None and home_app.remote_changes() and dev.get("changes") is True

        def _may_change(self, s: dict) -> bool:
            """For the page: at the Mac, or an added iPhone that may change things (each with Face ID)."""
            return self._is_local(s) or self._device_may_change(s)

        def _at_mac(self, s: dict) -> bool:
            """At this Mac itself -- what stays at the Mac (MAC_ONLY, parts of requests); not while "tailscale serve"/Funnel
            passes Kontor's port on (a request from this Mac's address may then come from anywhere), nor before it was looked at."""
            return self._is_local(s) and not app.exposure_block()

        def _trusted(self, s: dict) -> bool:
            """At the Mac, or from an added iPhone (whose changes each came with Face ID, _remote_check): rights as at the Mac
            but for MAC_ONLY and what acts on this Mac itself."""
            return self._is_local(s) or self._device_session(s) is not None

        def _remote_check(self, path: str, body: dict, s: dict) -> bool:
            """A request from another device, before anything is done: what stays at the Mac is refused; a change only with
            "Änderungen vom iPhone" on, from an added iPhone that may change things, confirmed with Face ID for exactly this
            request (_confirmed). The demo the same (its assistant uses the real model and internet): a session of it opened
            with an iPhone's passkey follows that iPhone, one opened with the password only looks. True when refused (answered)."""
            if path in MAC_ONLY:
                if path == "/api/history/mm-import":        # (an upload not read yet: refused without it, the iPhone gets the answer)
                    self._refuse_unread(403, tr("s_nur_von_diesem_mac_aus"), {"mac_only": True})
                else:
                    self._json(403, {"error": tr("s_nur_von_diesem_mac_aus"), "mac_only": True})
                return True
            if not remote_change(path, body):
                return False
            if not home_app.remote_changes():
                self._json(403, {"error": tr("s_von_unterwegs_nur_ansehen"), "read_only": True})
                return True
            dev = self._device_session(s)
            if dev is None:
                self._json(403, {"error": tr("s_pk_aendern_anmelden"), "read_only": True})
                return True
            if dev.get("changes") is not True:
                self._json(403, {"error": tr("s_pk_geraet_nur_ansehen"), "read_only": True})
                return True
            if not self._confirmed(path, s):
                self._json(403, {"error": tr("s_pk_nicht_bestaetigt"), "confirm": "needed"})
                return True
            return False

        def _confirmed(self, path: str, s: dict) -> bool:
            """A change from an iPhone confirmed with Face ID: X-Kontor-Confirm holds the passkey's signature (credential id,
            clientDataJSON, authenticatorData, signature -- base64url, joined by dots) over a challenge Kontor made for exactly
            this request: this session, its device, method, path and the SHA-256 of the body as sent; once, within two minutes."""
            dev, site, devs = self._device_session(s), home_app.passkey_site(), home_app.devices
            hdr = self.headers.get("X-Kontor-Confirm") or ""
            if dev is None or site is None or not 16 < len(hdr) <= CONFIRM_HEADER_MAX or hdr.count(".") != 3:
                return False
            try:
                cred, cdj, ad, sig = [webauthn.b64u_decode(x, CONFIRM_HEADER_MAX) for x in hdr.split(".")]
                if not hmac.compare_digest(webauthn.b64u(cred), str(dev.get("cred") or "")):
                    raise webauthn.Invalid("another passkey")
                chal = webauthn.challenge_of(cdj)
                bind = devs.challenge_take(chal, "confirm", str(s.get("sid") or ""))
                want = {"sid": s.get("sid"), "demo": app.DEMO, "device": dev["id"], "method": self.command, "path": path,
                        "body": hashlib.sha256(self._raw_body).hexdigest()}
                if bind != want:
                    raise webauthn.Invalid("challenge not for this request")
                info = webauthn.verify_assertion(cdj, ad, sig, chal, site[1], site[0], int(dev["x"], 16), int(dev["y"], 16), int(dev.get("count") or 0),
                                                 backup_eligible=dev.get("be") if isinstance(dev.get("be"), bool) else None)
            except (webauthn.Invalid, ValueError, TypeError, KeyError) as e:
                log.warning("Change from device %s refused: its confirmation does not check out (%s)", dev["id"], e)
                return False
            devs.used(dev["id"], info["count"])
            return True

        def _confirm_challenge(self, body: dict, s: dict):
            """The challenge for one change from an added iPhone, bound to it (_confirmed) -- the page then asks for Face ID."""
            dev, site = self._device_session(s), home_app.passkey_site()
            if self._is_local(s) or dev is None or site is None:
                return self._json(403, {"error": tr("s_pk_aendern_anmelden"), "read_only": True})
            if not home_app.remote_changes():
                return self._json(403, {"error": tr("s_von_unterwegs_nur_ansehen"), "read_only": True})
            if dev.get("changes") is not True:
                return self._json(403, {"error": tr("s_pk_geraet_nur_ansehen"), "read_only": True})
            method, path, digest = body.get("method"), body.get("path"), body.get("body")
            if method not in ("POST", "PUT") or not isinstance(path, str) or not re.fullmatch(r"/api/[a-z0-9/_-]{1,80}", path) or path in MAC_ONLY \
                    or path in CONFIRM_FREE or path in SIGN_IN or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(tr("s_ungueltige_anfrage_s") % "confirm")
            raw = home_app.devices.challenge_new("confirm", str(s.get("sid") or ""), {"sid": s.get("sid"), "demo": app.DEMO, "device": dev["id"], "method": method,
                                                                                      "path": path, "body": digest})
            return self._json(200, {"challenge": webauthn.b64u(raw), "credential": dev["cred"], "rp_id": site[0], "timeout": 120000})

        def _passkey(self, path: str, body: dict, remote: str):
            """Signing in with the passkey of an added iPhone (Face ID), and adding an iPhone with the link the Mac shows (its
            password once, then a new passkey): only from another device, only over https at Kontor's address in the Tailscale
            network, only while the data are open. Every failure counts like a wrong password."""
            site = app.passkey_site()
            if self._loopback():
                return self._json(403, {"error": tr("s_pk_nur_iphone")})
            if site is None or app.devices is None or not tls_connection(self.connection):
                return self._json(403, {"error": tr("s_pk_https_noetig")})
            wait = app.sessions.locked(remote)
            if wait:
                return self._json(429, {"error": tr("s_zu_viele_fehlversuche") % wait})
            if not app.store.is_open:                    # after a restart: the password opens the data once
                return self._json(409, {"error": tr("s_pk_erst_passwort"), "need_password": True})
            if not app.devices.readable():               # a passing error: nothing let in, nothing counted
                return self._json(503, {"error": tr("s_pk_liste_nicht_lesbar")})
            rp_id, origin = site
            if path == "/api/passkey/options":
                if not app.devices.allow(remote):          # its own budget per address: nobody fills the store
                    log.warning("Sign-in challenges asked for too often from %s", remote)
                    return self._json(429, {"error": tr("s_pk_zu_oft")})
                if not app.devices.all():
                    return self._json(409, {"error": tr("s_pk_keine_geraete")})
                raw = app.devices.challenge_new("login", remote, {"remote": remote})
                return self._json(200, {"challenge": webauthn.b64u(raw), "rp_id": rp_id, "timeout": 120000})
            if path == "/api/passkey/login":
                try:
                    cred = webauthn.b64u_decode(body.get("id"), 1400)
                    cdj = webauthn.b64u_decode(body.get("client_data"), 2800)
                    chal = webauthn.challenge_of(cdj)
                    bind = app.devices.challenge_take(chal, "login", remote)
                    dev = app.devices.by_credential(cred)
                    if bind is None or bind.get("remote") != remote or dev is None or dev.get("rp") != rp_id:
                        raise webauthn.Invalid("unknown passkey or challenge")
                    uh = body.get("user_handle")
                    if uh and not hmac.compare_digest(str(uh).encode("utf-8"), str(dev.get("user") or "").encode("ascii")):
                        raise webauthn.Invalid("user handle")
                    info = webauthn.verify_assertion(cdj, webauthn.b64u_decode(body.get("auth_data"), 5500), webauthn.b64u_decode(body.get("signature"), 120),
                                                     chal, origin, rp_id, int(dev["x"], 16), int(dev["y"], 16), int(dev.get("count") or 0),
                                                     backup_eligible=dev.get("be") if isinstance(dev.get("be"), bool) else None)
                except (webauthn.Invalid, ValueError, TypeError, KeyError) as e:
                    app.sessions.fail(remote)
                    log.warning("Failed sign-in with a passkey from %s (%s)", remote, e)
                    time.sleep(0.5)
                    return self._json(401, {"error": tr("s_pk_nicht_angemeldet")})
                app.sessions.clear_fails(remote)
                app.devices.used(dev["id"], info["count"])
                log.info("Login with Face ID from %s (device %s)", remote, dev["id"])
                return self._signed_in(remote, "passkey", body, dev["id"])      # (the demo: a session of its own that ends with the device)
            if path == "/api/pair/begin":
                if self._link(body.get("token")) is None:
                    app.sessions.fail(remote)
                    log.warning("Adding a device from %s: link not valid", remote)
                    return self._json(403, {"error": tr("s_pk_link_ungueltig")})
                if self._wrong_password(body.get("password")):
                    return None
                if len(app.devices.all()) >= devices_mod.MAX_DEVICES:
                    return self._json(409, {"error": tr("s_pk_zu_viele")})
                name, user = devices_mod.clean_name(body.get("name")), secrets.token_bytes(16)
                raw = app.devices.challenge_new("pair", remote, {"token": body["token"], "remote": remote, "name": name, "user": webauthn.b64u(user)})
                return self._json(200, {"challenge": webauthn.b64u(raw), "rp": {"id": rp_id, "name": "Kontor"},
                                        "user": {"id": webauthn.b64u(user), "name": name, "displayName": name},
                                        "exclude": [d["cred"] for d in app.devices.all()], "timeout": 120000})
            if path == "/api/pair/finish":
                return self._pair_finish(body, remote, rp_id, origin)
            return self._json(404, {"error": "unknown"})

        def _pair_finish(self, body: dict, remote: str, rp_id: str, origin: str):
            """The new passkey of an iPhone being added: checked against the challenge of this very link and address (made after
            the password, /api/pair/begin); the link is used up, the device added, its session begins."""
            try:
                cdj = webauthn.b64u_decode(body.get("client_data"), 2800)
                chal = webauthn.challenge_of(cdj)
                bind = app.devices.challenge_take(chal, "pair", remote)
                token = body.get("token")
                if bind is None or bind.get("remote") != remote or not isinstance(token, str) or not hmac.compare_digest(str(bind["token"]).encode("utf-8"), token.encode("utf-8")) \
                        or self._link(token) is None:
                    raise webauthn.Invalid("challenge or link")
                reg = webauthn.verify_registration(cdj, webauthn.b64u_decode(body.get("attestation"), 5500), chal, origin, rp_id)
                if not hmac.compare_digest(reg["cred_id"], webauthn.b64u_decode(body.get("id"), 1400)):
                    raise webauthn.Invalid("credential id")
                if app.devices.by_credential(reg["cred_id"]) is not None:
                    raise webauthn.Invalid("added already")
            except (webauthn.Invalid, ValueError, TypeError, KeyError) as e:
                app.sessions.fail(remote)
                log.warning("Adding a device from %s refused (%s)", remote, e)
                return self._json(400, {"error": tr("s_pk_nicht_hinzugefuegt")})
            link = app.devices.pairing_take(token)
            if link is None:
                return self._json(403, {"error": tr("s_pk_link_ungueltig")})
            first = link.get("first") is True and not app.devices.all()
            try:                                             # may it change things: as ticked on the card at the Mac (for this device only)
                dev = app.devices.add(bind["name"], reg["cred_id"], reg["x"], reg["y"], webauthn.b64u_decode(bind["user"]), rp_id, reg["count"],
                                      changes=link["changes"], be=bool(reg["flags"] & webauthn.BE))
            except devices_mod.NotWritable as e:
                return self._json(409, {"error": str(e)})
            except ValueError:
                return self._json(409, {"error": tr("s_pk_zu_viele")})
            if first and link["changes"] is True and app.remote_readonly():
                cfg = copy.deepcopy(app.config)              # the very first iPhone, added with the tick set at the Mac: changes from the iPhone on
                cfg.setdefault("ui", {})["remote_read_only"] = False
                app.save_config(cfg)
                log.info("First device added with changes allowed: changes from the iPhone on (as ticked at the Mac)")
            app.sessions.clear_fails(remote)
            log.info("Device %s added from %s", dev["id"], remote)
            s = app.sessions.create(remote, "passkey", device=dev["id"])
            return self._json(200, {"ok": True, "csrf": s["csrf"]}, self._set_cookie(s["token"]))

        def _link(self, token: Any) -> Optional[dict]:
            """The pairing link token names -- while valid and while the Mac's session that made it lasts (locked: gone)."""
            link = app.devices.pairing_check(token)
            if link is not None and not app.sessions.alive(link.get("by") or ""):
                app.devices.pairing_cancel()
                log.info("Link to add a device ended with the Mac's session")
                return None
            return link

        def _pairing(self, token: Optional[str] = None) -> dict:
            """The link to add an iPhone (only at the Mac): its address, the QR code of it, how long it holds."""
            st = app.devices.pairing_state(with_token=True)
            info = app.remote_info()
            if st is None or not info.get("url"):
                return {"active": False}
            url = info["url"] + "#pair=" + st["token"]
            size, path = qr.svg_path(url)
            return {"active": True, "url": url, "qr": {"size": size, "path": path}, "seconds": st["seconds"], "changes": st["changes"]}

        def _devices(self, path: str, body: dict, s: dict):
            """Einstellungen -> Zugang: add an iPhone (a link, shown as a QR code), whether one may change things, remove one --
            only at the Mac (MAC_ONLY)."""
            if path == "/api/devices/remove":
                did = str(body.get("id") or "")
                gone = app.devices.remove(did)
                n = app.sessions.drop_device(did)            # its sessions end at once; its passkey works no more
                d = app.demo_box.current()[0] if app.demo_box is not None else None
                if d is not None:
                    n += d.sessions.drop_device(did)         # ... and the demo's it opened (it uses the real model and internet)
                if gone:
                    log.info("Device %s removed, %d session(s) ended", did, n)
                return self._json(200, {"ok": gone is not None, "ended": n})
            if path == "/api/devices/set":                   # whether this iPhone may change things (each change still with Face ID)
                ok = app.devices.set_changes(str(body.get("id") or ""), body.get("changes") is True)
                if ok:
                    log.info("Device %s: changes %s", body.get("id"), "allowed" if body.get("changes") is True else "not allowed")
                return self._json(200, {"ok": ok})
            act = body.get("action")
            if act == "cancel":
                app.devices.pairing_cancel()
                return self._json(200, {"ok": True})
            if act == "changes":
                return self._json(200, {"ok": app.devices.pairing_set(body.get("changes") is not False)})
            if act != "new":
                raise ValueError(tr("s_unbekannte_aktion"))
            if app.passkey_site() is None or not app.remote_info().get("url"):
                return self._json(409, {"error": tr("s_pk_https_noetig")})
            # the first iPhone, ticked: "Änderungen vom iPhone" goes on once it is added with the tick (never here, see _pair_finish)
            app.devices.pairing_new(body.get("changes") is not False, by=str(s.get("sid") or ""), first=not app.devices.all())
            log.info("Link to add a device made (valid 10 minutes, while this session lasts)")
            return self._json(200, self._pairing())

        def _python_do(self, body: dict, s: dict):
            """Kontor's own Python -- loaded and switched to, a failed one removed: only at the Mac, only what the page
            asks for by one of these words (update_guard keeps this function as a whole)."""
            if not self._is_local(s):
                return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
            what, py = str(body.get("action") or ""), app.python
            if what == "install":
                py.install()
            elif what == "cancel":
                py.cancel()
            elif what == "remove":
                py.remove()
            else:
                raise ValueError("action: install|cancel|remove")
            return self._json(200, {"python": py.status(), "instance": app.instance})

        def _assistant_ok(self, s: dict) -> bool:
            """The assistant answers at the Mac -- and from other devices only with its right "remote"."""
            return self._is_local(s) or bool(assistant_mod.settings(app.config)["rights"]["remote"])

        def _assistant(self, path: str, body: dict, local: bool, mac: bool, may_change: bool = False):
            """Everything about the assistant. Setting it up (install, models, rights, start) only at the Mac -- and never by the
            assistant itself: it has no tool for it and no way to this service. From other devices only with its right
            "remote"; local: at the Mac or an added iPhone (its changes confirmed with Face ID, see _remote_check)."""
            a = app.assistant
            remote_ok = mac or bool(assistant_mod.settings(app.config)["rights"]["remote"])
            if path in ASSISTANT_ASK:
                if not remote_ok:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                if path == "/api/assistant/ask":
                    # what to remember: at the Mac at once; from an added iPhone (changes allowed) each note waits for a click
                    # on it, which Face ID confirms; from a device that may only look nothing is noted or forgotten
                    note = True if mac else "offer" if may_change else False
                    return self._json(200, a.ask(body, may_note=note))
                if path == "/api/assistant/stop":
                    a.stop()
                    return self._json(200, {"ok": True})
                if path == "/api/assistant/reset":
                    a.reset()
                    return self._json(200, {"ok": True})
                if path == "/api/assistant/listen":              # a dictation starts (or the assistant opens: warm): the speech model ready
                    return self._json(200, a.listen(warm=body.get("warm") is True))
                if path == "/api/assistant/transcribe":           # a recording (WAV, base64) -> its text; nothing of it is kept
                    try:
                        wav = base64.b64decode(str(body.get("audio") or ""), validate=True)
                    except (ValueError, binascii.Error):
                        raise ValueError(tr("s_ki_aufnahme_leer"))
                    return self._json(200, a.transcribe(wav, live=bool(body.get("live")), start=body.get("start"), direct=body.get("direct") is True))          # live: while still speaking
                if path == "/api/assistant/attach":               # a receipt for the next question: in memory only (assistant.attach)
                    try:
                        data = base64.b64decode(str(body.get("content") or ""), validate=True)
                    except (ValueError, binascii.Error):
                        raise ValueError(tr("s_dateiinhalt_unlesbar"))
                    return self._json(200, a.attach(body.get("name"), data))
                if path == "/api/assistant/page":
                    a.page_answer(str(body.get("job") or ""), str(body.get("id") or ""), body.get("page"), body.get("result"))
                    return self._json(200, {"ok": True})
                if path == "/api/assistant/confirm":
                    ok = body.get("ok") is True
                    kind = a.waiting_kind(str(body.get("job") or ""), str(body.get("id") or ""))
                    if ok and kind and not local:            # a yes from another device (values, internet -- also in the demo: the real key): an added iPhone, with Face ID
                        return self._json(403, {"error": tr("s_von_unterwegs_nur_ansehen")})
                    a.confirm(str(body.get("job") or ""), str(body.get("id") or ""), ok, body.get("ids"), local)
                    return self._json(200, {"ok": True})
            if path == "/api/assistant/chats/delete":            # one or all (from other devices: only where they may change things -- see do_POST)
                if not remote_ok:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                days = body.get("older_days")
                days = days if isinstance(days, int) and not isinstance(days, bool) and 30 <= days <= 3650 else 0
                return self._json(200, {"deleted": a.delete_chats(str(body.get("id") or ""), body.get("all") is True, older_days=days)})
            if path == "/api/assistant/undo":
                if not remote_ok or not local:
                    return self._json(403, {"error": tr("s_von_unterwegs_nur_ansehen")})
                return self._json(200, {"ok": True, "note": a.take_back(str(body.get("id") or ""), local)})
            if path in ("/api/assistant/memory/undo", "/api/assistant/memory/offer"):      # a note under an answer: taken back or brought back / kept after the click
                if not remote_ok or not local:
                    return self._json(403, {"error": tr("s_von_unterwegs_nur_ansehen")})
                return self._json(200, a.memory_undo(body.get("id")) if path.endswith("/undo") else a.memory_offer(body.get("id"), body.get("ok") is True))
            if path == "/api/assistant/memory":                  # notes added, changed, pinned, deleted -- by the user, in the settings
                if not local or not remote_ok:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                return self._json(200, a.memory_do(body))
            if not mac:                                          # setting it up: at the Mac only (MAC_ONLY)
                return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
            if path == "/api/assistant/memory/import":           # an exported memory (or a plain list) read in: checked as a whole first, all of it or nothing
                return self._json(200, a.memory_import(body))
            if path == "/api/assistant/memory/import/undo":      # the latest import taken back: its notes that were not changed since
                return self._json(200, a.memory_import_undo(body))
            if path == "/api/assistant/settings":
                a.set(body)
            elif path == "/api/assistant/check":
                a.look()
            elif path == "/api/assistant/update-all":           # everything a newer version was found for, one after the other
                a.update_all()
            elif path == "/api/assistant/runtime/install":
                a.ai.install_runtime(a.settings()["sandbox"])
            elif path == "/api/assistant/runtime/remove":
                a.stop_all()
                a.ai.remove_runtime()
            elif path == "/api/assistant/model/files":
                return self._json(200, {"files": a.ai.repo_files(str(body.get("repo") or "").strip())})
            elif path == "/api/assistant/model/download":
                a.load_model(str(body.get("id") or ""), str(body.get("repo") or "").strip(), str(body.get("file") or "").strip())
            elif path == "/api/assistant/model/cancel":
                a.cancel_load()
            elif path == "/api/assistant/model/delete":
                mid = str(body.get("id") or "")
                a.ai.delete_model(mid)
                if assistant_mod.settings(app.config)["model"] == mid:
                    a.set({"model": ""})
            elif path == "/api/assistant/web":                  # your keys for the internet search (Tavily; Claude, tier 4): saved or removed, never shown
                a.set_web(body)
            elif path == "/api/assistant/server":
                if body.get("action") == "start":
                    a.start_model()
                else:
                    a.stop_all(hold=True)                       # set to run all the time: not again by itself until it runs once more
            else:
                return self._json(404, {"error": "unbekannt"})
            return self._json(200, a.status(True))

        def _route(self, path: str, body: dict, s: dict):
            # local: at the Mac or from an added iPhone (each change confirmed with Face ID, _remote_check) -- rights as at the
            # Mac; mac: at this Mac itself (who gets in, whose code runs, what acts on this Mac: MAC_ONLY and parts of requests)
            local, mac = self._trusted(s), self._at_mac(s)
            if path.startswith("/api/assistant/"):
                return self._assistant(path, body, local, mac, self._may_change(s))
            if path == "/api/confirm":
                return self._confirm_challenge(body, s)
            if path in ("/api/devices/pair", "/api/devices/set", "/api/devices/remove"):
                if not mac:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                return self._devices(path, body, s)
            if path == "/api/lock":
                app.sessions.drop_all()                 # (the demo: locked like the real one -- it stays, see DemoBox)
                if app.devices is not None:
                    app.devices.pairing_cancel()         # a link to add an iPhone ends with it
                return self._json(200, {"ok": True}, self._set_cookie("", clear=True))
            if path == "/api/password":
                if not mac:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                if not body.get("old") and mac and app.touchid_on() and auth.touchid_available():
                    if not auth.touchid_verify():                # forgotten: Touch ID (or the Mac's password) instead, at the Mac
                        return self._json(401, {"error": tr("s_touch_id_nicht_bestaetigt")})
                elif self._wrong_password(body.get("old"), "s_altes_passwort_falsch"):
                    return
                err = auth.password_ok(str(body.get("new", "")))
                if err:
                    return self._json(400, {"error": err})
                try:
                    app.set_password(str(body["new"]))
                except StoreError as e:
                    return self._json(409, {"error": str(e)})
                n = app.sessions.drop_others(s["token"])                # other devices have to sign in with the new password
                app.demo_box.end()                                       # ... the demo too (it was opened with the old one)
                new = app.sessions.rotate(s["token"])                    # and this one goes on under a new token
                log.info("Password changed, %d other session(s) ended, this one renewed", n)
                return self._json(200, {"ok": True}, self._set_cookie(new) if new else None)
            if path == "/api/config":
                cfg = body.get("config")
                if not isinstance(cfg, dict):
                    return self._json(400, {"error": tr("s_config_fehlt")})
                seen = body.get("seen")
                if isinstance(seen, dict):                       # what the page was drawn from: another window's change stays
                    own = set(RULE_SECTIONS) | {"not_book", "assistant"}       # taken care of on their own (below)
                    try:
                        merged = _merge3({k: v for k, v in seen.items() if k not in own}, {k: v for k, v in cfg.items() if k not in own},
                                         {k: v for k, v in app.config.items() if k not in own})
                    except _Stale:
                        return self._json(409, {"error": tr("s_einst_inzwischen_geaendert"), "stale": True})
                    cfg = dict(merged, **{k: cfg[k] for k in own if k in cfg})
                if app.DEMO:                              # nothing beyond the demo is taken or even tried (no port asked for, no address checked):
                    cfg = {k: v for k, v in cfg.items() if k not in DEMO_FIXED}         # port, address, certificate, access ... as they are
                    cfg.update({k: copy.deepcopy(app.config[k]) for k in DEMO_FIXED if k in app.config})
                cfg = dict(cfg, not_book=copy.deepcopy(app.config.get("not_book") or []),     # changed only under Auto bookings
                           assistant=copy.deepcopy(app.config.get("assistant") or {}))       # and only under Einstellungen -> Assistent
                b = (cfg.get("ui") or {}).get("bind", "127.0.0.1") or "127.0.0.1"
                if not bind_allowed(b):
                    return self._json(400, {"error": tr("s_adresse_s_nicht_erlaubt_nur") % b})
                # address, port and certificate: only on the Mac; a new port must be free; afterwards restart on it
                old_ui, new_ui = app.config.get("ui") or {}, cfg.get("ui") or {}
                net_keys = ("bind", "port", "tls_cert", "tls_key")
                net_changed = any((old_ui.get(k) or "") != (new_ui.get(k) or "") for k in net_keys if k != "port") or \
                    int(old_ui.get("port") or 8765) != int(new_ui.get("port") or 8765)
                if net_changed and not mac:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                # where files are read and written (receipts folder and its sub-folders): only at the Mac
                if bool(cfg.get("dry_run", True)) != bool(app.config.get("dry_run", True)) and not local:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})      # booking without asking: switched only at the Mac
                old_b, new_b = app.config.get("receipts") or {}, cfg.get("receipts") or {}
                # who gets in and how (as under /api/remote): only at the Mac
                if not mac:
                    cfg["ui"] = dict(cfg.get("ui") or {}, **{k: copy.deepcopy(old_ui[k]) for k in ("remote_read_only", "offline_copy", "touchid", "lock_minutes") if k in old_ui})
                    for k in ("remote_read_only", "offline_copy", "touchid", "lock_minutes"):
                        if k not in old_ui:
                            cfg["ui"].pop(k, None)
                    new_ui = cfg["ui"]
                if any((old_b.get(k) or "") != (new_b.get(k) or "") for k in ("folder", "subfolder")) and not mac:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                if (new_b.get("subfolder") or "") != (old_b.get("subfolder") or ""):
                    why = pattern_problem(str(new_b.get("subfolder") or ""))
                    if why:
                        return self._json(400, {"error": why})
                # where updates come from: only at the Mac (an update is installed with one click there)
                if ((cfg.get("updates") or {}).get("repo") or "stecrz/Kontor") != ((app.config.get("updates") or {}).get("repo") or "stecrz/Kontor") and not mac:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                new_port = int(new_ui.get("port") or 8765)
                if not 1024 <= new_port <= 65535:
                    return self._json(400, {"error": tr("s_port_ungueltig")})
                if new_port != int(old_ui.get("port") or 8765) and not port_free(new_port):
                    return self._json(409, {"error": tr("s_port_belegt", new_port)})
                with RULES_LOCK:
                    if body.get("rules_seen") is None:
                        # only the rules page changes rules, with the rules it was drawn from; any other page (settings, accounts,
                        # setup -- perhaps loaded before the assistant's card changed a rule) leaves them as they are now
                        for k in RULE_SECTIONS:
                            if k in app.config:
                                cfg[k] = copy.deepcopy(app.config[k])
                            else:
                                cfg.pop(k, None)
                    elif _canon(body["rules_seen"]) != _rules_now(app.config):
                        return self._json(409, {"error": tr("s_regeln_inzwischen_geaendert")})     # changed meanwhile (the assistant's card): drawn anew first
                    cfg = prune_account_settings(cfg, app.ledger)        # entries of accounts deleted in MoneyMoney go
                    findings = check_config(app.ledger, app.categories_raw, merged_config(cfg)) if app.ledger is not None else []
                    if any(f["severity"] == "error" for f in findings) and not body.get("anyway"):
                        return self._json(409, {"error": tr("s_konfiguration_hat_fehler"), "findings": findings})
                    app.save_config(cfg)
                log.info("Configuration saved (%d loans, %d companies with rules)",
                         len(app.config.get("loans") or []), len(app.config.get("companies") or []))
                if net_changed:
                    log.info("Address or port changed -- restarting on port %d", new_port)
                    app.request_restart()
                return self._json(200, {"ok": True, "findings": findings, "config": app.config, "restart": net_changed and app.restart_allowed,
                                        "port": new_port, "instance": app.instance})
            if path == "/api/rules/preview":
                # what the rules would book now, for a configuration being edited (nothing is saved or written)
                cfg = body.get("config")
                if not isinstance(cfg, dict) or app.ledger is None:
                    return self._json(200, {"preview": [], "warnings": [], "bookings": 0})
                st = app.store.load("state.json", {}) or {}
                led = app.ledger.fork()
                try:
                    res = plan_rules(led, merged_config(dict(cfg, not_book=app.config.get("not_book") or [])), date.today(),
                                     seen=Seen.from_state(st.get("seen"), led, date.today()))
                except Exception as e:          # something unexpected in MoneyMoney or the rules: named, the page stays usable
                    log.warning("Rules preview failed (%s)", type(e).__name__)
                    return self._json(200, {"preview": [], "warnings": [tr("s_regeln_fehler") % type(e).__name__], "bookings": 0})
                return self._json(200, {"preview": res.preview, "warnings": res.warnings, "bookings": len(res.proposals)})
            if path == "/api/check":
                if not app.check_lock.acquire(blocking=False):
                    return self._json(409, {"error": tr("s_die_pruefung_laeuft_bereits_bitte")})
                try:
                    ledger, err = app.refresh_ledger()
                    if ledger is None:
                        return self._json(200, {"available": False, "text": err, "findings": []})
                    app.request_rebuild("connection checked")      # Auswertung auf den frischen Stand bringen (im Hintergrund)
                    findings = check_config(ledger, app.categories_raw, app.config)
                    return self._json(200, {"available": True, "findings": findings, "accounts": account_tree(ledger, app.config),
                                            "categories": app.categories()})
                finally:
                    app.check_lock.release()
            if path == "/api/sync/gaps":
                app.store.update("state.json", lambda cur: cur.pop("gaps", None), {})
                return self._json(200, {"ok": True})
            if path == "/api/sync":
                if app.ledger is None:
                    return self._json(409, {"error": tr("s_noch_kein_stand_aus_moneymoney")})
                try:
                    acc = app.ledger.resolve(str(body.get("account") or ""))
                except KeyError as e:
                    return self._json(400, {"error": str(e)})
                want = body.get("fetched")
                cfg = copy.deepcopy(app.config)
                ab = cfg.setdefault("fetch", {})
                for k in ("online", "offline"):
                    ab[k] = [r for r in ab.get(k) or [] if r.split("|")[0].strip() != acc.uuid]
                detected = abruf_arten(app.ledger, cfg)[acc.uuid]["kind"]
                if isinstance(want, bool) and (want != (detected == "online")):
                    ab["online" if want else "offline"].append("%s | %s" % (acc.uuid, acc.name))
                app.save_config(cfg)
                return self._json(200, {"ok": True, "fetch": app.abruf()})
            if path == "/api/bookings/reject":
                # a proposed booking you do not want: never proposed again (settings: nicht_buchen), until "Propose again";
                # keys: several at once (both halves of a pair entered by hand)
                raw = body.get("keys") if isinstance(body.get("keys"), list) else [body.get("key")]
                if len(raw) > 20:
                    return self._json(400, {"error": tr("s_markierung_ungueltig")})
                keys = []
                for k in raw:
                    acc, _, tag = str(k or "").partition("|")
                    if not re.fullmatch(r"[0-9A-Za-z-]{8,64}", acc) or not TAG_RE.fullmatch(tag):
                        return self._json(400, {"error": tr("s_markierung_ungueltig")})
                    keys.append(rules_bkey(acc, tag))
                if not keys:
                    return self._json(400, {"error": tr("s_markierung_ungueltig")})
                hold_back_bookings(app, keys)
                return self._json(200, {"ok": True})
            if path == "/api/bookings/plan":
                # the approval list for your selection: what you leave out (halten) or change (aenderungen) and everything
                # planned after it, recalculated from the last state read -- nothing is saved or written
                hold = body.get("hold") or []
                if not isinstance(hold, list) or len(hold) > 2000 or not all(
                        isinstance(k, str) and re.fullmatch(r"[0-9A-Za-z-]{8,64}", k.partition("|")[0]) and TAG_RE.fullmatch(k.partition("|")[2]) for k in hold):
                    return self._json(400, {"error": tr("s_markierung_ungueltig")})
                edits, err = approval(body.get("changes") or {})
                if err:
                    return self._json(400, {"error": err})
                hold = [rules_bkey(k.partition("|")[0], k.partition("|")[2]) for k in hold]
                if app.ledger is None:
                    return self._json(200, {"proposals": None})
                st = app.store.load("state.json", {}) or {}
                try:
                    waits: List[str] = []           # left out with what you left out: shown as waiting, not as not needed
                    rows = plan_pending(app.ledger, app.config, st, date.today(), set(hold), edits, waits)
                    return self._json(200, {"proposals": rows, "waiting": waits})
                except Exception as e:          # the list stays as it was
                    log.warning("Approval list not recalculated (%s)", type(e).__name__)
                    return self._json(409, {"error": tr("s_regeln_fehler") % type(e).__name__})
            if path == "/api/bookings/restore":
                # "Propose again" under "Not booked": out of the list -- the next check proposes it if it is still needed (it
                # waits for your approval when it is older than the last check, also booking fully automatically)
                key = str(body.get("key") or "")
                acc, _, tag = key.partition("|")
                if not re.fullmatch(r"[0-9A-Za-z-]{8,64}", acc) or not TAG_RE.fullmatch(tag):
                    return self._json(400, {"error": tr("s_markierung_ungueltig")})
                restore_bookings(app, [rules_bkey(acc, tag)])
                return self._json(200, {"ok": True})
            if path == "/api/bookings/refresh":
                # "Aktualisieren" under Auto bookings: only the accounts of the rules read again, the approval list planned again
                res = app.refresh_bookings()
                code = 409 if res.get("status") == "already_running" else 200
                return self._json(code, dict({k: res.get(k) for k in ("status", "text", "dry_run")},
                                             wartend=len(res.get("proposals") or []) if res.get("dry_run") else 0))
            if path == "/api/run":
                dry = body.get("dry_run")
                if dry is False and not (local and (mac or body.get("approval") is not None)):
                    return self._json(403, {"error": tr("s_buchen_nur_von_diesem_mac")})      # from an iPhone only what you approved, as shown
                if not mac and dry is not False:
                    dry = True          # from elsewhere a sync is a test run, whatever the test mode says (the Mac's schedule books)
                if app.running:
                    return self._json(409, {"error": tr("s_ein_abgleich_laeuft_bereits")})
                full = True if body.get("full_read") else None          # „Alles neu lesen“; sonst schnell, solange kein vollstaendiges Lesen faellig ist
                approve = None
                if dry is False and body.get("approval") is not None:      # "Book selected": only these, with your changes
                    approve, err = approval(body.get("approval"))
                    if err:
                        return self._json(400, {"error": err})
                threading.Thread(target=app.do_run, args=(dry, bool(body.get("force", True))), kwargs={"full": full, "approve": approve, "write": mac or dry is False},
                                 daemon=True).start()
                return self._json(202, {"started": True})
            if path == "/api/report":
                ledger, err = app.refresh_ledger()
                if ledger is None:
                    return self._json(200, {"ok": False, "text": err})
                ok, err = app.rebuild_report(wait=True, grund="report from MoneyMoney")
                return self._json(200, {"ok": ok, "text": err})
            if path == "/api/plan":
                return self._json(200, self._update_plan(body))
            if path.startswith("/api/receipts/"):
                return self._belege(path, body, mac)
            if path == "/api/package/import":
                pkg = body.get("package")
                if isinstance(pkg, str):
                    pkg = json.loads(pkg)
                cfg, unresolved, report = import_package(app.config, pkg, app.ledger, body.get("mode") or "merge", body.get("assignment") or {})
                if not mac:                                # what is switched only at the Mac stays as it is (as when saving settings)
                    cfg["dry_run"] = app.config.get("dry_run", True)
                    for sec, keys in (("ui", ("bind", "port", "tls_cert", "tls_key")), ("receipts", ("folder", "subfolder"))):
                        old_s, new_s = app.config.get(sec) or {}, cfg.setdefault(sec, {})
                        for k in keys:
                            if k in old_s:
                                new_s[k] = old_s[k]
                            else:
                                new_s.pop(k, None)
                if unresolved and not body.get("anyway"):
                    return self._json(200, {"ok": False, "unresolved": unresolved, "report": report,
                                            "hint": tr("s_konten_zuordnen_oder_trotzdem_ueberneh")})
                findings = check_config(app.ledger, app.categories_raw, cfg) if app.ledger is not None else []
                app.save_config(cfg)
                if pkg.get("plan") and body.get("with_plan"):
                    app.store.save("plan.json", pkg["plan"])
                log.info("Settings package '%s' imported (%s)", pkg.get("name"), body.get("mode") or "merge")
                return self._json(200, {"ok": True, "report": report, "findings": findings, "config": app.config})
            if path == "/api/update/check":
                app.update_info = updates.check((app.config.get("updates") or {}).get("repo") or "stecrz/Kontor")
                app.update_checked = time.time()
                return self._json(200, {"info": app.update_info, "version": version()})
            if path == "/api/update/install":
                return self._update_install(body, s)
            if path == "/api/python":
                return self._python_do(body, s)
            if path == "/api/history":
                return self._json(200, self._historie_set(body))
            if path == "/api/history/import":
                return self._json(200, self._historie_import(body))
            if path == "/api/language":
                if body.get("language") not in i18n.LANGS:
                    raise ValueError("language: de|en")
                cfg = copy.deepcopy(app.config)
                cfg.setdefault("ui", {})["language"] = body["language"]
                app.save_config(cfg)
                return self._json(200, {"ok": True, "language": i18n.lang()})
            if path == "/api/securities/lookup":
                # names of securities by their ISIN (OpenFIGI): only on request, only at the Mac; "entfernen" drops them again
                if not local:
                    return self._json(403, {"error": tr("s_nur_direkt_am_mac_moeglich")})
                if body.get("action") == "remove":
                    app.store.update("state.json", lambda cur: cur.pop("sec_search", None), {})
                    res = {"removed": True}
                elif body.get("action") == "names":
                    # the list of looked-up names, changed by hand (only ISINs already looked up; empty = no name)
                    namen = body.get("names") if isinstance(body.get("names"), dict) else {}
                    known = app.securities_known()[2]
                    app.store.update("state.json", lambda cur: security_names.set_names(cur.setdefault("sec_search", {}), namen, known), {})
                    res = {"saved": True}
                else:
                    try:
                        res = app.securities_lookup()
                    except (OSError, ValueError) as e:
                        log.warning("Security names: lookup failed: %s", e)
                        return self._json(502, {"error": tr("s_wp_suche_fehler") % e})
                ok, err = app.rebuild_report(wait=True, grund="rebuild requested")
                return self._json(200, dict(app.securities_unnamed(), **res, ok=ok, text=err))
            if path == "/api/history/mm-reveal":
                if not self._is_local(s):
                    return self._json(403, {"error": tr("s_nur_direkt_am_mac_moeglich")})
                mm_history.reveal()
                return self._json(200, {"ok": True})
            if path.startswith("/api/categories/"):
                return self._kategorien(path, body, local)
            if path.startswith("/api/properties"):
                return self._immobilien(path, body, mac)
            if path.startswith("/api/file/"):
                return self._datei(path, body, mac)
            if path == "/api/report/rebuild":
                ok, err = app.rebuild_report(wait=bool(body.get("wait")), grund="rebuild requested")
                return self._json(200, {"ok": ok, "text": err, "report": app.bericht_status()})
            if path == "/api/backup":
                # vollstaendige Sicherung, mit einem eigenen Passwort verschluesselt (nur am Mac; Passwort wird nirgends abgelegt)
                if not local:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                st = app.store.load("state.json", {}) or {}
                sich = {"kontor_backup": 1, "version": version(), "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "config": app.config, "plan": app.plan_all(), "categories": categorize.load(app.store),
                        "history": st.get("history") or {}, "snapshots": st.get("snapshots") or {},
                        "receipts": app.store.load("receipts.json", {}) or {}, "mm_history_src": app.store.load(MM_HISTORY_FILE, {}) or {},
                        "memory": app.assistant.memory.export()}             # what the assistant was told to remember (saved conversations stay out)
                out = backup_encrypt(sich, str(body.get("password") or ""))
                log.info("Encrypted backup of all settings created")
                return self._json(200, out)
            if path == "/api/backup/restore":
                if not mac:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                sich = body.get("backup") or {}
                if isinstance(sich, dict) and sich.get("kontor_backup_encrypted"):
                    sich = backup_decrypt(sich, str(body.get("password") or ""))
                if not isinstance(sich, dict) or not sich.get("kontor_backup") or not isinstance(sich.get("config"), dict):
                    raise ValueError(tr("s_keine_kontor_sicherung"))
                check_file_version(sich)
                listened = (app.config.get("ui") or {}).get("bind") or "127.0.0.1"
                teile = restore_backup(app, sich, bool(body.get("with_receipts", True)))      # checked first, then written: whole or not at all
                try:                                     # notes not there yet are added (marked as from a backup, told to the log of changes); nothing there is changed
                    if app.assistant.memory.merge(sich.get("memory")):
                        teile.append(tr("s_teil_gedaechtnis"))
                except Exception as e:                   # a file that cannot be written: the rest of the backup is restored all the same
                    log.warning("Backup: the assistant's memory not restored in full (%s)", type(e).__name__)
                log.info("Backup restored: %s", ", ".join(teile))
                ok, err = app.rebuild_report(wait=bool(body.get("wait")), grund="backup restored") if app.ledger is not None else (False, None)
                narrower = ((app.config.get("ui") or {}).get("bind") or "127.0.0.1") != listened      # the backup says: only this Mac
                if narrower:
                    log.info("Backup: access only at this Mac from now on -- restarting")
                    app.request_restart()
                return self._json(200, {"ok": True, "parts": teile, "report": ok, "config": app.config, "restart": narrower and app.restart_allowed,
                                        "port": int((app.config.get("ui") or {}).get("port") or 8765), "instance": app.instance})
            if path == "/api/reset":
                if not mac:
                    return self._json(403, {"error": tr("s_zuruecksetzen_nur_von_diesem_mac")})
                if self._wrong_password(body.get("password")):
                    return
                dateien = ["config.json", "plan.json", "state.json", "dataset.json", "cf-ids.json", "transactions.json", "categories.json", "receipts.json", "moneymoney-ledger.bin", "mm-history.json"]
                if body.get("with_password"):
                    dateien.append("auth.json")
                for name in dateien:
                    app.store.delete(name)
                for name in storage_names(app.data_dir):             # ... and a file once set aside as damaged (App.unlock)
                    if storage_damaged in name:
                        _remove_quietly(os.path.join(app.data_dir, name))
                app.assistant.delete_chats(everything=True)          # the saved conversations go with the data
                app.store.delete(assistant_mod.CHANGES_FILE)         # ... and the log of what the assistant changed
                app.assistant.memory.forget_all(quiet=True)          # ... and what it was told to remember
                app.store.delete(assistant_mod.web_search.WEB_FILE)  # ... and your keys for the internet search (Tavily, Claude)
                if app.devices is not None:
                    app.devices.forget()                 # ... and the iPhones added (their passkeys work no more)
                app.assistant.forget()                   # the assistant is switched off with its settings: model, conversation and entries to take back end
                app.config = merged_config({})
                app.ledger, app.ledger_time, app.categories_raw, app.last_result, app.last_run_at, app.umsaetze = None, None, [], None, None, None
                app.sessions.drop_all()
                app.demo_box.end()
                access.write_start(app.data_dir, app.config)      # the access as after a fresh setup (only this Mac) from the next start
                if body.get("with_password") and app.store.encrypted:
                    access.forget(app.store)             # the data key goes with the password (and every file it opened)
                log.warning("Program reset (%s); receipt files and log kept", ", ".join(dateien))
                return self._json(200, {"ok": True, "setup_again": bool(body.get("with_password"))}, self._set_cookie("", clear=True))
            if path == "/api/uninstall":
                if not mac:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                if self._wrong_password(body.get("password")):
                    return
                rep = app.uninstall(bool(body.get("program_folder", True)))
                if rep.get("error"):
                    return self._json(409, rep)
                app.sessions.drop_all()
                app.demo_box.end()                                       # its folder too (receipts uploaded in it are not encrypted)
                threading.Thread(target=app.uninstall_finish, daemon=True).start()        # the answer first, then the service goes
                return self._json(200, rep, self._set_cookie("", clear=True))
            if path == "/api/key/renew":
                # a new data key: everything re-encrypted, the old key gone only once all opens with the new one (only at the Mac)
                if not mac:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                if self._wrong_password(body.get("password")):
                    return
                try:
                    n = access.renew(app.store, str(body.get("password") or ""))
                except StoreError as e:
                    return self._json(409, {"error": str(e)})
                return self._json(200, {"ok": True, "files": n, "left": list(app.store.renew_left)})      # left: no key opens them (damaged) -- they stay as they are
            if path == "/api/storage/notice":
                # "a file was damaged and set aside" (App.unlock): read and closed -- the file itself stays where it is
                if not mac:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                app.store.update("state.json", lambda cur: cur.pop(DAMAGED_KEY, None), {})
                return self._json(200, {"ok": True})
            if path == "/api/remote":
                return self._remote_setup(body, mac)
            if path == "/api/mac-app/open":                 # Kontor's own app on this Mac: built if needed, then opened
                if not mac:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                if mac_app.ready():
                    return self._json(200, {"ok": mac_app.open_app(), "mac_app": mac_app.state()})
                threading.Thread(target=lambda: mac_app.build() == "ok" and mac_app.open_app(), name="kontor-mac-app", daemon=True).start()
                return self._json(200, {"ok": True, "mac_app": dict(mac_app.state(), building=True)})
            if path == "/api/timemachine-exclusion":
                if not mac:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                ok, text = timemachine_set(bool(body.get("exclude")), app.data_dir)
                return self._json(200, {"ok": ok, "text": text, "status": timemachine_status(app.data_dir)})
            return self._json(404, {"error": "unknown"})

        def _remote_setup(self, body: dict, local: bool):
            """Zugriff vom iPhone ein-/ausschalten und fein einstellen -- nur am Mac."""
            import tls_cert
            if not local:
                return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
            aktion = body.get("action")
            cfg = copy.deepcopy(app.config)
            ui = cfg.setdefault("ui", {})
            neustart = False
            if aktion == "settings":
                for k in ("remote_read_only", "offline_copy"):
                    if k in body:
                        ui[k] = bool(body[k])
                if isinstance(body.get("passkey_only"), bool) and app.devices is not None:
                    app.devices.set_passkey_only(body["passkey_only"])      # (beside the devices: never in a backup)
            elif aktion == "enable":                 # Zertifikat ueber Tailscale, Adresse = Tailscale-Adresse des Macs
                try:
                    r = tls_cert.setup(cfg, app.data_dir)
                except Exception as e:
                    log.warning("Remote access: certificate not available: %s", e)
                    return self._json(200, {"ok": False, "text": str(e), "tailscale": app.tailscale(fresh=True)})
                cfg["ui"] = dict(r["ui"], bind=r["ip"])
                neustart = True
            elif aktion == "enable_http":            # ohne Zertifikat (nur ueber Tailscale verschluesselt, keine Offline-Ansicht)
                st = app.tailscale(fresh=True)
                if not st.get("connected") or not st.get("ip"):
                    return self._json(200, {"ok": False, "text": tr("s_tailscale_ist_nicht_verbunden_kein"), "tailscale": st})
                ui.update(bind=st["ip"], tls_cert="", tls_key="")
                neustart = True
            elif aktion == "disable":
                ui["bind"] = "127.0.0.1"
                neustart = True
            else:
                raise ValueError(tr("s_unbekannte_aktion"))
            app.save_config(cfg)
            log.info("Remote access settings changed: %s", aktion)
            if neustart:
                app.request_restart()
            return self._json(200, {"ok": True, "restart": neustart and app.restart_allowed, "instance": app.instance, "info": app.remote_info()})

        def _belege(self, path: str, body: dict, local: bool):
            bl = Belege(app.store, app.config)
            # Der Belegordner wird erst nach Rueckfrage angelegt (einmalig; ein in den Einstellungen gewaehlter Ordner gilt als bestaetigt)
            if path in ("/api/receipts/upload", "/api/receipts/open", "/api/receipts/export") and not os.path.isdir(bl.folder):
                bcfg = app.config.get("receipts") or {}
                if body.get("create_folder"):
                    cfg = copy.deepcopy(app.config)
                    cfg.setdefault("receipts", {})["folder_confirmed"] = True
                    app.save_config(cfg)
                elif not bcfg.get("folder_confirmed"):
                    return self._json(409, {"error": tr("s_der_belegordner_s_existiert_noch") % bl.folder, "confirm_folder": True, "folder": bl.folder})
            ums = {t["id"]: t for t in (app.umsatzliste())}
            ds = app.store.load_shared("dataset.json", {}) or {}
            names = {k["uuid"]: k["name"] for k in ds.get("accounts", [])}
            names.update(ds.get("area_names") or {})

            def tx_of(body):
                return receipt_tx(app, body.get("tx_id"), ums)

            if path == "/api/receipts/upload":
                try:
                    data = base64.b64decode(str(body.get("content") or ""), validate=True)
                except Exception:
                    raise ValueError(tr("s_dateiinhalt_unlesbar"))
                e = bl.add_bytes(tx_of(body), str(body.get("file_name") or "Beleg"), data, str(body.get("note") or ""))
                # linked in Kontor only -- a receipt's path is never written into MoneyMoney (decided 22.11.2026)
                log.info("Receipt stored (%d KB)", len(data) // 1024)
                return self._json(200, {"ok": True, "entry": e})
            if path == "/api/receipts/link":
                if body.get("external") and not local:            # a file outside the receipts folder: only chosen at the Mac
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                if body.get("external"):
                    e = dict(bl.link_external(tx_of(body), str(body.get("path") or ""), str(body.get("note") or "")))
                    e["status"] = file_status(e["path"])
                else:
                    e = bl.link_existing(tx_of(body), str(body.get("path") or ""), str(body.get("note") or ""))
                return self._json(200, {"ok": True, "entry": e})
            if path == "/api/receipts/remove":
                ok = bl.remove(str(body.get("id") or ""), bool(body.get("delete_file")))
                return self._json(200, {"ok": ok})
            if path == "/api/receipts/update":
                fields = {k: v for k, v in body.items() if k in ("note", "name", "date", "amount")}
                if "tx_id" in body:
                    t = tx_of(body)
                    fields.update({"tx_id": t["id"], "account": t["account"], "entity": t["entity"]} if t else {"tx_id": None})
                e = bl.update(str(body.get("id") or ""), **fields)
                return self._json(200, {"ok": e is not None, "entry": e})
            if path == "/api/receipts/open":
                if not local:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                err = bl.ensure_folder()
                if err:
                    return self._json(500, {"error": err})
                target = bl.folder
                if body.get("path"):
                    cand = os.path.normpath(os.path.join(bl.folder, str(body["path"])))
                    if cand.startswith(os.path.normpath(bl.folder) + os.sep) and os.path.exists(cand):
                        target = cand
                    elif os.path.isabs(str(body["path"])) and os.path.exists(str(body["path"])):
                        target = os.path.normpath(str(body["path"]))
                if sys.platform != "darwin":
                    return self._json(400, {"error": tr("s_oeffnen_im_finder_nur_unter")})
                show_in_finder(target)
                return self._json(200, {"ok": True})
            if path == "/api/receipts/export":
                target = bl.export_zip(str(body.get("year") or "") or None, str(body.get("entity") or "") or None, names)
                if local and sys.platform == "darwin":
                    show_in_finder(target, select=True)
                log.info("Receipt export created")
                return self._json(200, {"ok": True, "file": target})
            return self._json(404, {"error": "unknown"})

        def _historie_set(self, body: dict) -> dict:
            acc = app.ledger.accounts.get(str(body.get("account") or "")) if app.ledger is not None else None
            if acc is not None and acc.group:            # a group of accounts has no balances of its own
                raise ValueError(tr("s_verlauf_nur_konto"))
            return account_history_set(app, body)

        def _historie_import(self, body: dict) -> dict:
            """Saldenverlauf aus CSV-Text oder Datei (CSV/XLSX): Langformat (Datum, Konto, Saldo), Matrix oder transponiert.
            Vorschau mit Kontovorschlaegen; 'zuordnung' (Tabellenname -> Kontoreferenz) und 'uebernehmen' schreiben die Werte."""
            konto = str(body.get("account") or "")
            mapping = body.get("assignment") or {}
            hints: List[str] = []
            if body.get("file"):
                try:
                    raw = base64.b64decode(str(body["file"]))
                except (binascii.Error, ValueError):
                    raise ValueError(tr("s_dateiinhalt_unlesbar"))
                if len(raw) > 30 * 1024 * 1024:
                    raise ValueError(tr("s_datei_zu_gross_max_30"))
                parsed, hints = history_import.balances_from_file(str(body.get("name") or ""), raw)
            else:
                parsed = _parse_balance_csv(str(body.get("csv") or ""))
            if not parsed:
                raise ValueError(tr("s_keine_werte_erkannt_erwartet_datum"))
            konten = {k["name"]: k["uuid"] for k in (app.store.load_shared("dataset.json", {}) or {}).get("accounts", []) if not k["group"]}
            if app.ledger is not None:
                konten.update({a.name: a.uuid for a in app.ledger.accounts.values() if not a.group})
            uuid_name = {v: k for k, v in konten.items()}
            preview = []
            assign: Dict[str, Dict[str, float]] = {}
            for name, months in sorted(parsed.items()):
                if konto and (name == "" or len(parsed) == 1):
                    target = konto
                elif name in mapping:
                    target = (mapping.get(name) or "").split("|", 1)[0].strip() or None
                else:
                    target = konten.get(name) or history_import.match_account(name, konten)
                preview.append({"name": name or tr("s_ohne_konto"), "uuid": target, "account": uuid_name.get(target or "", ""), "count": len(months), "date_from": min(months), "date_to": max(months),
                                "certain": bool(name in konten or name in mapping or (konto and (name == "" or len(parsed) == 1)))})
                if target:
                    assign.setdefault(target, {}).update(months)
            if not body.get("take_over"):
                return {"ok": True, "preview": preview, "hints": hints}
            total = 0

            def _apply(st):
                nonlocal total
                h = st.setdefault("history", {})
                for uuid, months in assign.items():
                    if body.get("gaps_only"):
                        months = {mk: v for mk, v in months.items() if mk not in (h.get(uuid) or {})}
                    h.setdefault(uuid, {}).update(months)
                    total += len(months)
            app.store.update("state.json", _apply, {})
            # importierte Werte sollen gelten -> diese Konten auf "Kontostaende" stellen
            cfg = copy.deepcopy(app.config)
            vc = cfg.setdefault("balance", {}).setdefault("history_source", {})
            umgestellt = 0
            for uuid in assign:
                if not any(k.split("|", 1)[0].strip() == uuid and v == "balances" for k, v in vc.items()):
                    for k in [k for k in vc if k.split("|", 1)[0].strip() == uuid]:
                        vc.pop(k)
                    vc["%s | %s" % (uuid, uuid_name.get(uuid, ""))] = "balances"
                    umgestellt += 1
            if umgestellt:
                app.save_config(cfg)
            ok, err = app.rebuild_report(wait=bool(body.get("wait")), grund="history import")
            log.info("History import: %d values for %d accounts", total, len(assign))
            return {"ok": True, "taken_over": total, "accounts": len(assign), "switched": umgestellt, "report": ok, "text": err, "preview": preview, "hints": hints}

        def _kategorien(self, path: str, body: dict, local: bool):
            if path == "/api/categories/assign":
                # your assignment goes into MoneyMoney (only categories that exist there); at the Mac right away, from
                # elsewhere at the next sync at the Mac -- until then it waits in Kontor and counts already
                ids = [int(x) for x in (body.get("ids") or [])]
                return self._json(200, assign_categories(app, ids, categorize.norm_cat(str(body.get("category") or "")),
                                                         "overwrite" if body.get("mode") == "overwrite" else "auto", local,
                                                         body.get("confirmed") if isinstance(body.get("confirmed"), dict) else None, bool(body.get("wait"))))
            if path == "/api/categories/doubts":
                # categories you looked at and that are right as they are ("Passt so"): not doubted again while they keep them
                got = body.get("ok") if isinstance(body.get("ok"), list) else []
                ids = {int(x) for x in got[:2000] if isinstance(x, (int, str)) and str(x).lstrip("-").isdigit()}
                if ids and app.ledger is not None:
                    with categorize.LOCK:
                        kat = categorize.load(app.store)
                        mine = dict(kat.get("doubt_ok") or {})
                        for t in app.ledger.txs:
                            if t.id in ids:
                                cat = categorize.effective(kat, t)[0]
                                if cat:
                                    mine.pop(str(t.id), None)          # (said again: the newest, the last to go)
                                    mine[str(t.id)] = cat
                        kat["doubt_ok"] = dict(list(mine.items())[-categorize.DOUBT_OK_MAX:])
                        categorize.save(app.store, kat)
                return self._json(200, {"ok": True})
            if path == "/api/categories/proposals":
                # a rule proposal you took over into MoneyMoney (or do not want): not shown again
                key = str(body.get("done_items") or "")
                if key:
                    with categorize.LOCK:
                        kat = categorize.load(app.store)
                        kat["rule_done"] = sorted(set(kat.get("rule_done") or []) | {key})[-500:]
                        categorize.save(app.store, kat)
                return self._json(200, {"ok": True})
            if path == "/api/categories/positions":
                # your cash flow positions for MoneyMoney's categories (settings: kapitalfluss), then the report anew
                try:
                    cfg = save_positions(app.config, body, app.ledger)
                except KeyError as e:
                    return self._json(400, {"error": str(e).strip("'\"")})
                # only taken over as they stand (the setup's "Übernehmen und weiter"): no figure changes, no new report
                same = ({k: v for k, v in (cfg.get("cashflow") or {}).items() if k != "positions_confirmed"}
                        == {k: v for k, v in (app.config.get("cashflow") or {}).items() if k != "positions_confirmed"})
                app.save_config(cfg)
                ok, err = app.rebuild_report(wait=bool(body.get("wait")), grund="cash flow positions") if app.ledger is not None and not same else (False, None)
                log.info("Cash flow positions saved: %d chosen", len(app.config["cashflow"].get("positions") or {}))
                return self._json(200, {"ok": True, "report": ok, "config": app.config})
            if path == "/api/categories/areas":
                # the areas you categorise and the period (from, to: days, "" open; the rest is left out under Kategorisieren and
                # its counts -- the cash flow estimates it as before) -- areas or period, or both; the period always as a pair
                ohne, per = body.get("without"), body.get("period")
                if ohne is None and per is None:
                    raise ValueError("without")
                if ohne is not None and (not isinstance(ohne, list) or not all(isinstance(x, str) for x in ohne)):
                    raise ValueError("without")
                if per is not None:
                    if not isinstance(per, dict) or not all(isinstance(per.get(k), str) for k in ("from", "to")):
                        raise ValueError("period")
                    try:
                        per = {k: date.fromisoformat(per[k]).isoformat() if per[k] else "" for k in ("from", "to")}
                    except ValueError:
                        raise ValueError(tr("s_datum_ungueltig"))
                    if per["from"] and per["to"] and per["from"] > per["to"]:
                        raise ValueError(tr("s_zeitraum_verkehrt"))
                cfg = copy.deepcopy(app.config)
                if ohne is not None:
                    cfg["assign_without"] = sorted(set(ohne))
                if per is not None:
                    cfg["assign_from"], cfg["assign_to"] = per["from"], per["to"]
                app.save_config(cfg)
                ok, _err = app.rebuild_report(wait=bool(body.get("wait")), grund="assigning") if app.ledger is not None else (False, None)
                return self._json(200, {"ok": True, "report": ok, "config": app.config})
            if path == "/api/categories/undo":
                # what Kontor entered in MoneyMoney, taken back (only at the Mac): the category that was there before -- only where
                # MoneyMoney still shows the one Kontor entered and the transaction is unchanged
                if not local:
                    return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})
                ids = [int(x) for x in (body.get("ids") or [])]
                if not ids:
                    raise ValueError(tr("s_keine_umsaetze_angegeben"))
                if len(ids) > 2000:
                    raise ValueError(tr("s_hoechstens_2000"))
                with categorize.LOCK:
                    res = app.undo_categories(ids)
                ok, err = app.rebuild_report(wait=bool(body.get("wait")), grund="categories taken back") if res["undone"] else (False, None)
                return self._json(200, dict(res, ok=True, report=ok, text=err))
            return self._json(404, {"error": "unknown"})

        def _immobilien(self, path: str, body: dict, local: bool = True):
            if path == "/api/properties/calculate":
                res = realestate.berechne(body.get("inputs") or {}, date.today())
                res.pop("months", None) if body.get("without_months") else None
                return self._json(200, res)
            cfg = copy.deepcopy(app.config)
            lst = cfg.setdefault("real_estate", [])
            aktion = str(body.get("action") or "")
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            im = next((x for x in lst if str(x.get("id")) == str(body.get("id"))), None)
            if aktion == "create":
                iid = "im%d" % (max([int(str(x.get("id"))[2:]) for x in lst if str(x.get("id", "")).startswith("im") and str(x.get("id"))[2:].isdigit()] + [0]) + 1)
                im = {"id": iid, "name": str(body.get("name") or "Neues Objekt"), "area": body.get("area") or "", "category": body.get("category") or "",
                      "property_account": body.get("property_account") or "", "loan_accounts": {}, "in_planning": False, "calcs": [], "documents": [], "notes": ""}
                lst.append(im)
            elif im is None:
                return self._json(404, {"error": tr("s_immobilie_nicht_gefunden")})
            elif aktion == "delete":
                lst.remove(im)
                app.save_config(cfg)
                log.info("Property deleted")
                return self._json(200, {"ok": True})
            if aktion in ("create", "update"):
                for k in ("name", "area", "category", "property_account", "notes"):
                    if k in body:
                        im[k] = body[k]
                if "in_planning" in body:
                    im["in_planning"] = bool(body["in_planning"])
                if isinstance(body.get("loan_accounts"), dict):
                    im["loan_accounts"] = {str(k): v for k, v in body["loan_accounts"].items()}
            elif aktion == "calc_save":
                k = body.get("calc") or {}
                eing = k.get("inputs") or {}
                realestate.berechne(eing, date.today())          # validiert
                kid = str(k.get("id") or "")
                existing = next((x for x in im["calcs"] if str(x.get("id")) == kid), None) if kid else None
                if existing:
                    existing["inputs"] = eing; existing["name"] = k.get("name") or existing.get("name"); existing["changed"] = now
                else:
                    kid = "k%d" % (len(im["calcs"]) + 1 + int(datetime.now().timestamp()) % 1000)
                    im["calcs"].append({"id": kid, "name": k.get("name") or ("Kalkulation %d" % (len(im["calcs"]) + 1)),
                                                "created": now, "active": not im["calcs"], "inputs": eing})
                if k.get("active"):
                    for x in im["calcs"]:
                        x["active"] = str(x.get("id")) == kid
            elif aktion == "calc_delete":
                im["calcs"] = [x for x in im["calcs"] if str(x.get("id")) != str(body.get("calc_id"))]
                if im["calcs"] and not any(x.get("active") for x in im["calcs"]):
                    im["calcs"][0]["active"] = True
            elif aktion == "calc_activate":
                for x in im["calcs"]:
                    x["active"] = str(x.get("id")) == str(body.get("calc_id"))
            elif aktion == "doc_add":
                if not local:                                   # links to files on the Mac: only set there
                    return self._json(403, {"error": tr("s_dateizugriff_nur_von_diesem_mac")})
                pfad = os.path.expanduser(str(body.get("path") or ""))
                if not pfad or file_status(pfad) == "lacking":
                    return self._json(400, {"error": tr("s_datei_nicht_gefunden_s") % pfad})
                im.setdefault("documents", []).append({"id": "d%d" % int(datetime.now().timestamp() * 1000 % 10 ** 9), "title": body.get("title") or os.path.basename(pfad),
                                                       "path": pfad, "kind": body.get("kind") or "", "added": now})
            elif aktion == "doc_remove":
                im["documents"] = [d for d in im.get("documents") or [] if str(d.get("id")) != str(body.get("document_id"))]
            else:
                return self._json(400, {"error": tr("s_unbekannte_aktion")})
            app.save_config(cfg)
            log.info("Property %s: %s", im.get("id"), aktion)
            ok, err = app.rebuild_report(wait=bool(body.get("wait")), grund="property") if app.ledger is not None else (False, None)
            return self._json(200, {"ok": True, "property": im, "report": ok})

        def _datei(self, path: str, body: dict, local: bool):
            if not local:
                return self._json(403, {"error": tr("s_dateizugriff_nur_von_diesem_mac")})
            if sys.platform != "darwin":
                return self._json(400, {"error": tr("s_nur_macos")})
            if path == "/api/file/choose":
                art = body.get("kind") or "file"
                chosen = choose_on_mac(art == "folder", str(body.get("prompt") or tr("s_datei_waehlen")))
                if chosen is None:
                    return self._json(200, {"ok": False, "text": tr("s_zeitueberschreitung")})
                if not chosen:
                    return self._json(200, {"ok": False, "text": tr("s_abgebrochen")})
                p = chosen.rstrip("/") if art == "folder" else chosen
                return self._json(200, {"ok": True, "path": p, "name": os.path.basename(p), "status": file_status(p) if art != "folder" else "ok",
                                        "size_bytes": os.path.getsize(p) if os.path.isfile(p) else None})
            pfad = os.path.expanduser(str(body.get("path") or ""))
            if not pfad or not os.path.isabs(pfad):
                return self._json(400, {"error": tr("s_pfad_fehlt")})
            if path == "/api/file/open":
                st = file_status(pfad)
                if st == "lacking":
                    return self._json(404, {"error": tr("s_datei_nicht_gefunden")})
                open_document(pfad)
                return self._json(200, {"ok": True, "status": st})
            if path == "/api/file/reveal":
                if not os.path.exists(pfad) and file_status(pfad) == "lacking":
                    return self._json(404, {"error": tr("s_datei_nicht_gefunden")})
                show_in_finder(pfad, select=True)
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "unknown"})

        def _update_plan(self, body: dict) -> dict:
            return plan_update(app, body)

    home_app = app.box.real if app.DEMO else app

    def _pick(req) -> Any:
        box = home_app.demo_box
        d, cls = box.current() if box is not None else (None, None)
        if d is not None and d.sessions.get(req._cookie(), touch=False) is not None:
            return cls
        return req._home

    return H


BACKUP_ITER = 600_000
BACKUP_ITER_MIN, BACKUP_ITER_MAX = 100_000, 5_000_000      # what a backup to restore may name (backup_decrypt)


def port_free(port: int) -> bool:
    """Can Kontor listen on 127.0.0.1:port? (checked before switching, so the service never restarts onto a busy port)"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def help_image_sizes(text: str) -> Dict[str, List[int]]:
    """Width and height (pixels) of a help file's images from the PNG header, so the page reserves the space up front
    and jumps to anchors land in the right place."""
    out: Dict[str, List[int]] = {}
    for rel in set(re.findall(r"!\[[^\]]*\]\((img/(?:de|en)/[a-z0-9_]+\.png)\)", text)):
        try:
            with open(os.path.join(HERE, "docs", rel), "rb") as f:
                head = f.read(24)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                out[rel] = [int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")]
        except OSError:
            pass
    return out


def backup_encrypt(data: dict, password: str) -> dict:
    """Sicherung mit eigenem Passwort verschluesseln (PBKDF2-SHA256 -> AES-256 + HMAC wie der Datenordner).
    Das Passwort wird weder gespeichert noch protokolliert."""
    import hashlib
    import secrets
    from storage import encrypt
    if len(password) < 8:
        raise ValueError(tr("s_sicherungspasswort_zu_kurz"))
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, BACKUP_ITER, 32)
    blob = encrypt(key, json.dumps(data, ensure_ascii=False).encode("utf-8"))
    return {"kontor_backup_encrypted": 1, "version": data.get("version"), "created": data.get("created"),
            "kdf": "pbkdf2-sha256", "iter": BACKUP_ITER, "salt": base64.b64encode(salt).decode(), "data": base64.b64encode(blob).decode()}


def backup_decrypt(wrapper: dict, password: str) -> dict:
    import hashlib
    from storage import StoreError, decrypt
    try:
        salt = base64.b64decode(wrapper["salt"]); blob = base64.b64decode(wrapper["data"])
        rounds = wrapper.get("iter") or BACKUP_ITER
        # a file names its own rounds: only a whole number in a range Kontor ever wrote (or might soon) -- a made-up one must
        # not keep the service computing for minutes
        if isinstance(rounds, bool) or not isinstance(rounds, int) or not BACKUP_ITER_MIN <= rounds <= BACKUP_ITER_MAX:
            raise ValueError("iter")
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds, 32)
        return json.loads(decrypt(key, blob).decode("utf-8"))
    except (KeyError, TypeError, ValueError, StoreError, binascii.Error):
        raise ValueError(tr("s_sicherung_passwort_falsch"))


def restored_config(current: dict, incoming: dict) -> dict:
    """The settings of a backup as they are taken over. A backup is a file -- it may be old, changed or not Kontor's own (one
    without a password is read too, and a password proves nothing: anyone can encrypt a file). What decides whose code runs
    on this Mac, who gets in and how, and whether Kontor writes into MoneyMoney without asking never comes from the file alone:
    - where updates come from stays as set here (as with a settings package: an update is installed with one click);
    - the access never gets wider: the address Kontor listens on, port and certificate stay as set on this Mac, and so do
      Touch ID, "from elsewhere only look", the minutes until it locks and the offline copy -- unless the backup is stricter
      (Touch ID off, only look on, fewer minutes, no offline copy, only this Mac: 127.0.0.1), then the stricter one holds;
    - a sub-folder pattern that leads out of the receipts folder is not taken over;
    - booking without asking can be switched off by a backup, never on (on: as set here -- you switch it on yourself). Where
      it stays on, nothing of the backup books by itself: a booking rule that is not here already as it is in the file waits
      for your confirmation under Konten & Regeln (marked for review, like a rule from the assistant), and what you set
      here not to be booked stays so;
    - the assistant's rights stay as they are here."""
    cfg = dict(copy.deepcopy(incoming), assistant=copy.deepcopy(current.get("assistant") or {}))
    upd = dict(cfg["updates"]) if isinstance(cfg.get("updates"), dict) else {}
    upd["repo"] = (current.get("updates") or {}).get("repo") or "stecrz/Kontor"
    cfg["updates"] = upd
    old_ui = current.get("ui") if isinstance(current.get("ui"), dict) else {}
    ui = dict(cfg["ui"]) if isinstance(cfg.get("ui"), dict) else {}
    said = dict(ui)                                      # what the file says about the access
    for k in ("bind", "port", "tls_cert", "tls_key", "touchid", "remote_read_only", "offline_copy", "lock_minutes"):
        ui.pop(k, None)
        if k in old_ui:
            ui[k] = copy.deepcopy(old_ui[k])
    if said.get("bind") == "127.0.0.1" and (old_ui.get("bind") or "127.0.0.1") != "127.0.0.1":
        ui["bind"] = "127.0.0.1"                         # only this Mac
    if said.get("touchid") is False:
        ui["touchid"] = False
    if said.get("remote_read_only", True) is True and old_ui.get("remote_read_only", True) is not True:
        ui["remote_read_only"] = True                    # (not named in the file: only look, as from the factory)
    if said.get("offline_copy") is False:
        ui["offline_copy"] = False
    here, there = old_ui.get("lock_minutes", 15), said.get("lock_minutes")
    if isinstance(there, int) and not isinstance(there, bool) and 1 <= there and (not isinstance(here, int) or isinstance(here, bool) or there < here):
        ui["lock_minutes"] = there
    cfg["ui"] = ui
    old_r = current.get("receipts") if isinstance(current.get("receipts"), dict) else {}
    if isinstance(cfg.get("receipts"), dict):
        sub = cfg["receipts"].get("subfolder")
        if sub and (not isinstance(sub, str) or pattern_problem(sub)):
            cfg["receipts"]["subfolder"] = old_r.get("subfolder") or "{year}"
    if cfg.get("dry_run", True) is not True and current.get("dry_run", True):       # anything but a clear "ask first" (also a missing or odd value)
        cfg["dry_run"] = True
    if cfg.get("dry_run", True) is not True:             # booking without asking stays on: nothing of the file books by itself
        for sec in RULE_SECTIONS:
            have = {_rule_form(sec, r) for r in current.get(sec) or [] if isinstance(r, dict) and r.get("review") is not True}    # (one still to confirm here stays so)
            for r in cfg.get(sec) if isinstance(cfg.get(sec), list) else []:
                if isinstance(r, dict) and _rule_form(sec, r) not in have:
                    r["review"] = True
        mine = [x for x in current.get("not_book") or [] if isinstance(x, dict)]
        keys = {x.get("key") for x in mine}
        cfg["not_book"] = [x for x in (cfg.get("not_book") if isinstance(cfg.get("not_book"), list) else [])
                           if isinstance(x, dict) and x.get("key") not in keys] + copy.deepcopy(mine)
    return cfg


# A backup read back: every part in the form the program reads it in, checked before anything is written (backup_parts) --
# a part in another form would stop the pages that read it (a sync, the transactions, the receipts) until a reset.
_MONTH_KEY = re.compile(r"(?:19|20|21)\d\d-(?:0[1-9]|1[0-2])")


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def _reads_as_num(v: Any, comma: bool = False) -> bool:
    """A number -- or a text the program reads as one (float(...))."""
    if isinstance(v, str):
        try:
            return _is_num(float(v.replace(",", ".") if comma else v))
        except ValueError:
            return False
    return _is_num(v)


def _opt(v: Any, kind: type) -> bool:
    return v is None or isinstance(v, kind)


def _per_month(v: Any, empty: bool = True) -> bool:
    """{month: balance} (a month without one: None, where the program expects that)."""
    return isinstance(v, dict) and all(isinstance(k, str) and _MONTH_KEY.fullmatch(k) is not None and (_is_num(x) or (empty and x is None))
                                       for k, x in v.items())


def _plan_form(plan: Any) -> bool:
    """plan.json as report.apply_plan and the planning page read it."""
    if not isinstance(plan, dict) or not _opt(plan.get("areas"), dict):
        return False
    for a in (plan.get("areas") or {}).values():
        if not isinstance(a, dict):
            return False
        h = a.get("horizon_months")                      # (int(...): a number, or a text of digits)
        if "horizon_months" in a and not (_is_num(h) and abs(h) < 1e9 or isinstance(h, str) and h.strip().lstrip("+-").isdigit()):
            return False
        if not _opt(a.get("default_method"), str):
            return False
        if any(a.get(k) is not None and not _reads_as_num(a[k]) for k in PLAN_PARAMS if k not in ("horizon_months", "default_method")):
            return False
        rows, loans, appr, events, dflt = (a.get(k) for k in ("rows", "loans", "appreciation", "events", "defaults"))
        if not (_opt(rows, dict) and _opt(loans, dict) and _opt(appr, dict) and _opt(events, list) and _opt(dflt, dict)):
            return False
        rule = lambda r: isinstance(r, dict) and _opt(r.get("method"), str) and (r.get("amount") is None or _is_num(r["amount"])) \
            and ("increase_percent_pa" not in r or _is_num(r["increase_percent_pa"])) \
            and (r.get("amounts") is None or (isinstance(r["amounts"], dict) and all(_is_num(x) for x in r["amounts"].values())))
        for r in (rows or {}).values():                  # a position, with the rules and values of its categories
            if not rule(r) or not _opt(r.get("categories"), dict) or not all(rule(c) and "categories" not in c for c in (r.get("categories") or {}).values()):
                return False
        if not all(k in ("income", "expenses") and rule(v) and "amounts" not in v for k, v in (dflt or {}).items()):
            return False
        for d in (loans or {}).values():
            if not isinstance(d, dict) or not _opt(d.get("model"), str) or "rate_list" in d \
                    or any(d.get(k) not in (None, "") and not _reads_as_num(d[k]) for k in ("interest_percent_pa", "payment")):
                return False
        for w in (appr or {}).values():
            if not isinstance(w, dict) or not _opt(w.get("area"), str) or ("share" in w and not _is_num(w["share"])) \
                    or any(w.get(k) not in (None, "") and not _reads_as_num(w[k]) for k in ("percent_pa", "base")):
                return False
        for e in events or []:
            if not isinstance(e, dict) or (e.get("amount") not in (None, "") and not _reads_as_num(e["amount"], comma=True)) \
                    or not all(_opt(e.get(k), str) for k in ("text", "kind", "date_from", "after", "recurrence", "date_to", "month")) \
                    or (e.get("month") and _MONTH_KEY.fullmatch(e["month"][:7]) is None) or not _opt(e.get("id"), (str, int, float)):
                return False
    return True


def _categories_form(d: Any) -> bool:
    """categories.json (categorize): the learned patterns and the proposals for rules you ticked off."""
    if not isinstance(d, dict) or not _opt(d.get("assignment"), dict) or not _opt(d.get("rules"), list) or not _opt(d.get("learned_at"), str):
        return False
    for r in d.get("rules") or []:
        if not isinstance(r, dict) or not all(_opt(r.get(k), str) for k in ("id", "category", "iban", "name_is", "purpose_contains", "source")) \
                or not (r.get("hits") is None or _is_num(r["hits"])):
            return False
    if not (d.get("doubt_ok") is None or (isinstance(d["doubt_ok"], dict) and len(d["doubt_ok"]) <= categorize.DOUBT_OK_MAX
                                          and all(isinstance(k, str) and isinstance(v, str) for k, v in d["doubt_ok"].items()))):
        return False
    return d.get("rule_done") is None or (isinstance(d["rule_done"], list) and all(isinstance(x, str) for x in d["rule_done"]))


def _receipts_form(d: Any) -> bool:
    """receipts.json (receipts.Belege): the list of receipts, each with its id and its file."""
    if not isinstance(d, dict) or not _opt(d.get("entry_list"), list):
        return False
    for e in d.get("entry_list") or []:
        if not isinstance(e, dict) or not (isinstance(e.get("id"), str) and e["id"]) or not (isinstance(e.get("path"), str) and e["path"]) \
                or not (e.get("tx_id") is None or (isinstance(e["tx_id"], int) and not isinstance(e["tx_id"], bool))) \
                or not all(_opt(e.get(k), str) for k in ("account", "entity", "date", "name", "note", "original", "added")) \
                or not all(e.get(k) is None or _is_num(e[k]) for k in ("amount", "size_bytes")) or not _opt(e.get("external"), bool):
            return False
    return True


def _mm_history_form(d: Any) -> bool:
    """mm-history.json: the balances and securities read from MoneyMoney's database."""
    if not isinstance(d, dict) or not _opt(d.get("as_of"), str) or not all(_opt(d.get(k), dict) for k in ("accounts", "opening", "securities")):
        return False
    if not all(isinstance(k, str) and _per_month(v) for k, v in (d.get("accounts") or {}).items()):
        return False
    if not all(isinstance(k, str) and (v is None or _is_num(v)) for k, v in (d.get("opening") or {}).items()):
        return False
    for rows in (d.get("securities") or {}).values():
        if not isinstance(rows, list) or not all(isinstance(w, dict) and _opt(w.get("name"), str) and _opt(w.get("isin"), str)
                                                 and (w.get("amounts") is None or _per_month(w["amounts"])) for w in rows):
            return False
    return True


def backup_parts(backup: dict) -> Dict[str, Any]:
    """The parts of a backup besides the settings, each as it is taken over -- checked before anything is written: one part
    in a form the program does not read (ValueError naming it), and nothing of the file is restored. A part that is missing
    or empty is simply not there. Never comes back: an assignment of a category that still waited to be written into
    MoneyMoney when the backup was made -- a file never makes Kontor write there."""
    out: Dict[str, Any] = {}

    def part(name: str, label: str, ok: Callable[[Any], bool]) -> Any:
        v = backup.get(name)
        if v is None:
            return None
        if not ok(v):
            raise ValueError(tr("s_sicherung_teil_form") % tr(label))
        return v
    plan = part("plan", "s_teil_planung", _plan_form)
    if plan is not None:
        out["plan"] = plan
    cats = part("categories", "s_teil_kategorien", _categories_form)
    if cats is not None and cats.get("version") == 3:   # (another version: categorize.load would take it for empty anyway)
        out["categories"] = {k: v for k, v in cats.items() if k != "assignment" and not k.startswith("_")}
    hist = part("history", "s_teil_verlauf", lambda v: isinstance(v, dict) and all(isinstance(k, str) and _per_month(x) for k, x in v.items()))
    if hist is not None:
        out["history"] = hist
    snaps = part("snapshots", "s_teil_verlauf", lambda v: isinstance(v, dict) and all(
        isinstance(k, str) and _MONTH_KEY.fullmatch(k) is not None and isinstance(x, dict) and all(isinstance(u, str) and _is_num(b) for u, b in x.items())
        for k, x in v.items()))
    if snaps:
        out["snapshots"] = snaps
    rec = part("receipts", "s_teil_belegindex", _receipts_form)
    if rec:
        out["receipts"] = {"entry_list": list(rec.get("entry_list") or [])}
    mmh = part("mm_history_src", "s_teil_mm_verlauf", _mm_history_form)
    if mmh:
        out["mm_history_src"] = mmh
    mem = backup.get("memory")                           # each note is checked by the memory itself (memory.merge)
    if mem is not None and not (isinstance(mem, dict) and isinstance(mem.get("notes"), list)):
        raise ValueError(tr("s_sicherung_teil_form") % tr("s_teil_gedaechtnis"))
    return out


def restore_backup(app: "App", backup: dict, with_receipts: bool = True) -> List[str]:
    """A backup read back, whole or not at all: first every part is checked (backup_parts) and the settings are made as they
    are taken over (restored_config) -- a part in the wrong form refuses the file before anything changes; then all is
    written, and a write that fails puts back what was there. Returns the names of the parts taken over. The memory follows
    (the caller: notes are only added, each checked by the memory)."""
    parts = backup_parts(backup)
    import core as _core
    for k, v in _core.DEFAULT_CONFIG.items():            # the settings' parts as lists or tables as they should be: one that is not refuses the file
        if k in ("ui", "receipts", "updates"):           # (taken as this Mac has them, whatever the file holds: an odd one is dropped)
            continue
        got = backup["config"].get(k) if isinstance(backup.get("config"), dict) else None
        if got is not None and isinstance(v, (list, dict)) and not isinstance(got, type(v)):
            raise ValueError(tr("s_sicherung_teil_form") % ("%s (%s)" % (tr("s_teil_einstellungen"), k)))
    old_cfg = copy.deepcopy(app.config)
    cfg = restored_config(app.config, backup["config"])
    merged_config(cfg)                                   # (as it is saved below: whatever it cannot shape stops here)
    names = [tr("s_teil_einstellungen")]
    back: List[Callable[[], Any]] = []

    def put(name: str, save: Callable[[], Any]) -> None:
        before = app.store.read_raw(name)                # as it lies on the disk -- also a damaged one (the backup replaces it)
        back.append(lambda: app.store.put_raw(name, before))
        save()
    try:
        if "plan" in parts:
            put("plan.json", lambda: app.store.save("plan.json", parts["plan"])); names.append(tr("s_teil_planung"))
        if "categories" in parts:
            with categorize.LOCK:                        # what waits here to be written into MoneyMoney is yours: it stays
                try:
                    waits = categorize.load(app.store).get("assignment") or {}
                except StoreDamaged:                     # (damaged: nothing of it can be written any more anyway)
                    waits = {}
                put(categorize.FILE, lambda: categorize.save(app.store, dict(parts["categories"], version=3, assignment=waits)))
            names.append(tr("s_teil_kategorien"))
        was = app.store.load("state.json", {}) or {}
        kept = {k: copy.deepcopy(was[k]) for k in ("history", "snapshots", DAMAGED_KEY) if k in was}

        def state_back(st: dict) -> None:
            for k in ("history", "snapshots", DAMAGED_KEY):
                st.pop(k, None)
            st.update(copy.deepcopy(kept))

        def merge(st: dict) -> None:
            if "history" in parts:
                st["history"] = parts["history"]
            if "snapshots" in parts:
                st["snapshots"] = {**parts["snapshots"], **(st.get("snapshots") or {})}
            st.pop(DAMAGED_KEY, None)                    # a file set aside as damaged: the backup is what was advised
        back.append(lambda: app.store.update("state.json", state_back, {}))
        app.store.update("state.json", merge, {})
        if "history" in parts:
            names.append(tr("s_teil_verlauf"))
        if "receipts" in parts and with_receipts:
            put("receipts.json", lambda: app.store.save("receipts.json", parts["receipts"])); names.append(tr("s_teil_belegindex"))
        if "mm_history_src" in parts:
            put(MM_HISTORY_FILE, lambda: app.store.save(MM_HISTORY_FILE, parts["mm_history_src"])); names.append(tr("s_teil_mm_verlauf"))
        as_saved = app.store.read_raw("config.json")

        def settings_back() -> None:
            app.save_config(old_cfg)                     # (what follows the settings: the lock, Touch ID, the language)
            if as_saved is not None:
                app.store.put_raw("config.json", as_saved)
        back.append(settings_back)
        app.save_config(cfg)
    except Exception:
        for undo in reversed(back):
            try:
                undo()
            except Exception as e:
                log.error("Backup: a file could not be put back as it was (%s)", type(e).__name__)
        raise
    return names


# Kontor's own files in its data folder (the store, its log and service files, a key file, the certificate): only these go
ASSISTANT_ASK = ("/api/assistant/ask", "/api/assistant/stop", "/api/assistant/reset", "/api/assistant/page", "/api/assistant/confirm", "/api/assistant/listen",
                 "/api/assistant/transcribe", "/api/assistant/attach")

# -- From another device (an iPhone over Tailscale) -------------------------------------------------------------------------
# The ways in before a session: password, Touch ID (only at the Mac), the passkey of an added iPhone, adding an iPhone with
# the link the Mac shows -- small bodies only.
SIGN_IN = ("/api/setup", "/api/login", "/api/touchid", "/api/touchid/switch", "/api/passkey/options", "/api/passkey/login",
           "/api/pair/begin", "/api/pair/finish")
# What stays at the Mac, whoever asks from elsewhere, also with Face ID: who gets in and how (access, devices, pairing,
# password, data key), whose code runs (installing updates; where they come from: a setting, see /api/config), setting up
# the assistant, loading a backup, resetting, deleting Kontor's data -- and what acts on this Mac itself (its windows, its
# files, Time Machine, the MoneyMoney database).
MAC_ONLY = frozenset(("/api/password", "/api/remote", "/api/devices/pair", "/api/devices/set", "/api/devices/remove", "/api/update/install", "/api/backup/restore",
                      "/api/reset", "/api/key/renew", "/api/uninstall", "/api/storage/notice", "/api/mac-app/open", "/api/timemachine-exclusion",
                      "/api/history/mm-import", "/api/history/mm-reveal", "/api/file/choose", "/api/file/open", "/api/file/reveal", "/api/receipts/open",
                      "/api/assistant/settings", "/api/assistant/check", "/api/assistant/update-all", "/api/assistant/runtime/install",
                      "/api/assistant/runtime/remove", "/api/assistant/model/files", "/api/assistant/model/download", "/api/assistant/model/cancel",
                      "/api/assistant/model/delete", "/api/assistant/web", "/api/assistant/server", "/api/assistant/memory/import", "/api/assistant/memory/import/undo", "/api/python"))
# Requests that change nothing: from another device without Face ID (reading, computing what something would do, asking
# the assistant, locking, the challenge for a confirmation). Every other request from another device changes something and
# waits for Face ID on the iPhone it was signed in from (service: _remote_check) -- one not named here is a change.
CONFIRM_FREE = frozenset(("/api/lock", "/api/confirm", "/api/rules/preview", "/api/bookings/plan", "/api/check", "/api/report", "/api/report/rebuild",
                          "/api/bookings/refresh", "/api/properties/calculate", "/api/assistant/ask", "/api/assistant/stop", "/api/assistant/reset", "/api/assistant/page",
                          "/api/assistant/listen", "/api/assistant/transcribe", "/api/assistant/attach"))
# ... and requests that change something only as they are asked: a sync books only when it is not a test run (a test run from
# another device writes nothing into MoneyMoney, not even waiting categories); a click on the assistant's card counts when it
# says yes -- to changes, and to fetches from the internet (they send search words out)
CONFIRM_MAYBE = frozenset(("/api/run", "/api/assistant/confirm"))
CONFIRM_HEADER_MAX = 6000
# Kontor never sits behind a proxy: a request passed on ("tailscale serve", Funnel, any other) would arrive from this Mac
# itself -- one that carries a proxy's headers is never answered (_proxied)
PROXIED = re.compile(r"(?i)forwarded|x-forwarded-.*|x-real-ip|x-original-forwarded-for|true-client-ip|x-client-ip|x-cluster-client-ip|cf-connecting-ip|tailscale-.*")
EXPOSURE_SECONDS = 60                   # how old the check of "tailscale serve"/Funnel may be (App.exposed: looked at anew in the background)
EXPOSURE_RETRY = 5                      # ... after a look without an answer: the next one after these seconds,
EXPOSURE_YOUNG = 180                    # ... in the first minutes after the start (Tailscale may come up later): every EXPOSURE_RETRY
EXPOSURE_TRIES = 3                      # ... never known since the start: locked until so many looks in a row went without an answer
EXPOSURE_WAIT = 2.0                     # a sign-in at the Mac right after the start waits for the first look until so long after the start (then it goes)
EXPOSURE_FIRST = 20                     # ... and no longer than this after the start in all: a Tailscale that does not answer
                                        # (each look waits for its timeouts, up to ~2 min for three) counts as "unknown" then
EXPOSURE_LOCK = threading.Lock()
EXPOSURE_CV = threading.Condition(EXPOSURE_LOCK)
ACL_LOCK = threading.Lock()             # one look at Tailscale's rules at a time (App.remote_acl)


def tls_connection(conn: Any) -> bool:
    """The request came over https (Kontor's address in the Tailscale network with its certificate)."""
    return isinstance(conn, ssl.SSLSocket)


def remote_change(path: str, body: dict) -> bool:
    """Does this request from another device change something (and wait for Face ID)?"""
    if path in CONFIRM_FREE:
        return False
    if path == "/api/run":
        return body.get("dry_run") is False
    if path == "/api/assistant/confirm":
        return body.get("ok") is True
    return True

_KONTOR_FILE = re.compile(r"(?:^|\s)(?:(?:auth|cf-ids|config|dataset|plan|receipts|state|transactions|categories|mm-history|assistant-changes|assistant-web|devices|memory-[a-z]+(?:-\d{4,6})?)"
                          r"\.json(?:\.enc)?(?:\.tmp|\.renew|\.left|\.damaged-[\d-]+)?"
                          r"|moneymoney-ledger\.bin(?:\.enc)?(?:\.tmp|\.renew|\.left)?|kontor\.log[\w.]*|service\.(?:out\.log|err\.log|lock)|key\.json(?:\.tmp)?|key\.lock"
                          r"|start\.json(?:\.tmp)?|tls|assistant|chats)(?=\s|$)")


def _disposition(kind: str, name: str) -> str:
    """Content-Disposition for a file of the user's, any name: an ASCII stand-in and the name itself (RFC 6266/5987) -- a header
    holds only Latin-1, so a name with € or an emoji would otherwise break the answer."""
    plain = "".join(c if " " <= c <= "~" and c not in '"\\;' else "_" for c in name) or "file"
    return "%s; filename=\"%s\"; filename*=UTF-8''%s" % (kind, plain, quote(name, safe=""))


def _remove_own_files(data: str, keep: List[str]) -> Tuple[List[str], List[str]]:
    """Deletes Kontor's own files in the data folder; the folder itself when nothing else is left. Returns (names of files that
    are not Kontor's -- they stay, names of Kontor's files that could not be removed); kept ones (receipts) stay silently."""
    from receipts import _canon
    foreign, failed, kept = [], [], False
    # the key file goes last, and only when no encrypted file is left (a key is never deleted while data it opens remain)
    keys = ("key.json",)
    for name in sorted(os.listdir(data), key=lambda n: (n in keys, n)):
        full = os.path.join(data, name)
        if name in keys and any(n.endswith((".enc", ".enc.tmp", ".enc.renew")) for n in storage_names(data)):
            failed.append(name); continue
        if any(_canon(full) == k or k.startswith(_canon(full).rstrip(os.sep) + os.sep) for k in keep):
            kept = True; continue
        if not _KONTOR_FILE.fullmatch(name):
            foreign.append(name); continue
        try:
            if os.path.isdir(full) and not os.path.islink(full):
                shutil.rmtree(full)
            else:
                os.remove(full)
        except OSError:
            log.exception("Not removed: %s", name)
            failed.append(name)
    if not (foreign or failed or kept):
        try:
            os.rmdir(data)
        except OSError:
            pass
    return foreign, failed


def _remove_tree(path: str, keep: List[str]) -> bool:
    """Deletes path, except what is in keep (canonical paths: files or folders, with what lies in them; their parents stay as
    far as needed). True when done -- also when only kept things are left."""
    from receipts import _canon
    cp = _canon(path)
    inside = [k for k in keep if k == cp or k.startswith(cp.rstrip(os.sep) + os.sep)]
    try:
        if not inside:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return True
        if cp in inside:
            return True
        for name in os.listdir(path):
            if not _remove_tree(os.path.join(path, name), keep):
                return False
        return True
    except OSError:
        log.exception("Not removed: %s", os.path.basename(path))
        return False


# Everything the pages can have this Mac do outside Kontor goes through the four small functions below -- each takes a path (or
# a text for a window) and nothing else, and none can start a program, open a page or an address:
DOCUMENTS = frozenset((".pdf", ".png", ".jpg", ".jpeg", ".heic", ".gif", ".tif", ".tiff", ".bmp", ".webp", ".txt", ".csv", ".rtf", ".md", ".xlsx", ".xls",
                       ".docx", ".doc", ".pptx", ".ppt", ".numbers", ".pages", ".key", ".eml", ".msg"))      # (an archive unpacks itself: shown)


def show_in_finder(path: str, select: bool = False) -> None:
    """Finder shows a folder's content; a file -- and anything that only looks like a folder (a program, a package) -- is
    selected in its folder, never opened."""
    path = os.path.abspath(path)
    plain_folder = os.path.isdir(path) and not os.path.splitext(os.path.basename(path.rstrip(os.sep)))[1]
    subprocess.Popen(["open", "-a", "Finder", path] if plain_folder and not select else ["open", "-R", path])


def open_document(path: str) -> None:
    """A document opens in its own app (types of documents only: a page, a link, a script or a program is shown in Finder)."""
    path = os.path.abspath(path)
    if os.path.isfile(path) and os.path.splitext(path)[1].lower() in DOCUMENTS:
        subprocess.Popen(["open", path])
    else:
        show_in_finder(path, select=True)


def choose_on_mac(folder: bool, prompt: str) -> Optional[str]:
    """macOS' own window to choose a file or folder: its path, "" when closed without one, None when nobody answered."""
    prompt = re.sub(r"[^\w .,:;!?()\-–äöüÄÖÜß]", "", prompt)[:120]                 # a plain line of text: nothing that could end or leave it
    script = 'POSIX path of (choose %s with prompt "%s")' % ("folder" if folder else "file", prompt)
    try:
        r = subprocess.run(["osascript", "-e", 'tell application "System Events" to activate', "-e", script], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return None
    return r.stdout.strip() if r.returncode == 0 else ""


def timemachine_set(exclude: bool, path: str) -> Tuple[bool, str]:
    """Leaves Kontor's data folder out of Time Machine backups, or takes it in again."""
    try:
        r = subprocess.run(["tmutil", "addexclusion" if exclude else "removeexclusion", path], capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def timemachine_status(path: str) -> str:
    """'ausgeschlossen' / 'gesichert' / 'unbekannt' (tmutil isexcluded, nur macOS)."""
    try:
        r = subprocess.run(["tmutil", "isexcluded", path], capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"
    out = r.stdout or ""
    return "excluded" if "[Excluded]" in out else "backed_up" if "[Included]" in out else "unknown"


def restart_process(app: Optional["App"] = None) -> None:
    """Prozess durch sich selbst ersetzen (neuer Code). Gleiche Prozessnummer, launchd bemerkt nichts;
    offene Sockets und die Sperrdatei werden dabei geschlossen (nicht vererbbar). The assistant's model ends before."""
    if app is not None:
        app.assistant_stop()
    logging.shutdown()
    if pyboot.starter():                    # run by a starter (Kontor's own Python): it starts anew and decides which Python serves
        os._exit(pyboot.EX_RESTART)
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except OSError:  # pragma: no cover - dann eben beenden; launchd (KeepAlive) startet neu
        os._exit(0)


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        et, ev = sys.exc_info()[:2]
        if et in (BrokenPipeError, ConnectionResetError, ssl.SSLError, TimeoutError):
            log.debug("Connection %s: %s", client_address[0], ev)
            return
        log.exception("Error handling request from %s", client_address[0])


def serve(app: App) -> None:
    """Oberflaeche auf 127.0.0.1 (immer, http -- fuer den Mac mit Touch ID) und zusaetzlich auf der
    eingestellten Tailscale-Adresse (fuer das iPhone; mit TLS, wenn ein Zertifikat eingetragen ist)."""
    ui = app.config.get("ui", {}) or {}
    extra = (ui.get("bind") or "127.0.0.1").strip()
    if not bind_allowed(extra):
        log.error("Bind address %s not allowed -- 127.0.0.1 only", extra)
        extra = "127.0.0.1"
    port = int(ui.get("port") or 8765)
    app.exposure_tick(fresh=True)           # "tailscale serve"/Funnel: looked at at once (until then no sign-in at this Mac's address)
    handler = make_handler(app)
    servers = []
    try:
        servers.append(("http", "127.0.0.1", _Server(("127.0.0.1", port), handler)))
    except OSError as e:
        log.error("Port %d on 127.0.0.1 not usable (%s) -- is Kontor already running? Change the port in the settings.", port, e)
        raise SystemExit(2)
    app._handler = handler
    try:
        app.assistant                       # a model left over from before this start is ended
    except StoreLocked:                     # it reads the data: made with its first use after the sign-in
        app._assistant = None
    atexit.register(app.assistant_stop)

    def _term(signum, frame):               # the service is ended (launchd, logout): the model ends first, then as before
        app.assistant_stop()
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTERM)
    try:
        signal.signal(signal.SIGTERM, _term)
    except ValueError:  # pragma: no cover - not the main thread (tests)
        pass
    app.start_remote()                      # zweiter Zugang (Tailscale); sonst spaeter erneut vom Zeitplaner
    app.restart_allowed = True
    for line in pyboot.serves():            # Kontor serves: said to the starter when one runs this service (pyboot.py) -- and what
        log.error(line)                     # there is to say about an own Python that ended before it got this far
    threading.Thread(target=app.scheduler, daemon=True).start()
    log.info("Kontor %s: UI at %s (data %s)", version(),
             ", ".join("%s://%s:%d/" % (sc, h, port) for sc, h, _ in servers + ([(app.remote_listening[0], app.remote_listening[1], None)] if app.remote_listening else [])),
             "encrypted" if app.store.encrypted else "KLARTEXT")
    try:
        servers[0][2].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop.set()
        for _, _, srv in servers:
            srv.shutdown() if srv is not servers[0][2] else None
            srv.server_close()
