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
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from mm_bridge import Bridge, MoneyMoneyError, MoneyMoneyLocked, MoneyMoneyNotPermitted, MoneyMoneyNotRunning
from model import Account, Ledger, Tx, accounts_from_export, add_months, canon_tag, fmt_eur, marks_in, month_key, tx_from_export, norm_cat
import mm_categories
import realestate
import categorize
from report import ROLES, account_roles, build_dataset, equity_ratio, holding_key
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
    "probelauf": True,
    "zeitplan": {"intervall_minuten": 30, "automatisch": True, "voll_lesen_tage": 7},
    "darlehen": [], "gesellschaften": [],
    "bereiche": [],
    "immobilien": [],
    "bilanz": {"monate_zurueck": 0, "rollen": {}, "verlauf": {}, "illiquide_rollen": ["beteiligungen", "immobilien", "sachwerte"],
               "illiquide_konten": [], "inaktiv_monate": 12, "ausgeblendet": [], "immer_anzeigen": [], "ansicht": "positionen"},
    "kapitalfluss": {"kategorie_zuordnung": {}, "kategorie_zu_konto": {},
                     "umbuchungs_kategorien": ["Umbuchung"], "umbuchung_paarung": True, "paarung_manuelle_konten": True},
    "steuer": {"vermietung_kategorie": "Vermietung", "objekt_darlehen": {}, "afa": {}, "positionen": {}, "entitaeten": []},
    "belege": {"ordner": "~/Documents/Kontor-Belege", "unterordner": "{jahr}", "kommentar_schreiben": False, "ordner_bestaetigt": False},
    "moneymoney": {"kategorisieren_erlauben": False},
    "abruf": {"online": [], "offline": []},      # eigene Festlegung: Konto wird von MoneyMoney abgerufen / nicht (sonst erkannt)
    "nicht_buchen": [],      # bookings of the rules you chose not to book: {"key": account|mark, "datum", "betrag", "konto", "art", "text", "regel", "seit"}
    "updates": {"repo": "stecrz/Kontor", "pruefen": "taeglich"},   # pruefen: taeglich | woechentlich | aus
    "oberflaeche": {"sperre_minuten": 15, "touchid": True, "port": 8765, "bind": "127.0.0.1", "tls_cert": "", "tls_key": ""},
}

# Felder mit Kontoreferenzen in Listen (fuer Pakete und Pruefung)
REF_FIELDS = [
    ("darlehen", "darlehenskonto"), ("darlehen", "quellkonten"), ("gesellschaften", "beteiligung"),
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
        elif k in cfg and isinstance(v, list):
            cfg[k] = dicts(cfg[k])
    for b in cfg.get("bereiche") or []:
        for f in ("id", "name", "art"):
            if f in b and not isinstance(b[f], str):
                b[f] = str(b[f]) if isinstance(b[f], (int, float)) and not isinstance(b[f], bool) else ""
            if f in b and not b[f] and f != "art":
                b.pop(f)
        b["konten"] = texts(b.get("konten"))
        if "anteil" in b:
            b["anteil"] = number(b["anteil"])
    for d in cfg.get("darlehen") or []:
        d["darlehenskonto"] = text(d.get("darlehenskonto"))
        d["quellkonten"] = texts(d.get("quellkonten"))
        e = d["erkennung"] = d["erkennung"] if isinstance(d.get("erkennung"), dict) else {}
        for f in ("gegen_iban", "text_enthaelt", "ausschliessen_text"):
            if f in e and not isinstance(e[f], str):
                e[f] = texts(e[f])
        d["ab_datum"] = day(d.get("ab_datum"))
        if not d["ab_datum"] or not d["darlehenskonto"]:
            d["aktiv"] = False                      # cannot run: shown as switched off until it is complete
        if "name" in d and not isinstance(d["name"], str):
            d.pop("name")
        if "buchung" in d and not isinstance(d["buchung"], dict):
            d.pop("buchung")
        for f in [f for f, v in (d.get("buchung") or {}).items() if v is not None and not isinstance(v, str)]:
            d["buchung"].pop(f)
        if "art" in d and not isinstance(d["art"], str):
            d.pop("art")
        z = d.get("zins")
        if z is not None and not isinstance(z, dict):
            d.pop("zins")
        elif z:
            z["satz"] = [{"ab": day(r.get("ab")), "prozent": number(r.get("prozent"))} for r in dicts(z.get("satz")) if number(r.get("prozent")) is not None]
            z["basis_override"] = {str(k): number(v) for k, v in z["basis_override"].items() if number(v) is not None} if isinstance(z.get("basis_override"), dict) else {}
            for f in ("modell", "buchungstag"):
                if f in z and not isinstance(z[f], str):
                    z.pop(f)
    for g in cfg.get("gesellschaften") or []:
        g["bereich"] = str(g["bereich"]) if isinstance(g.get("bereich"), (str, int)) and not isinstance(g.get("bereich"), bool) else ""
        for f in ("beteiligung", "rueckwirkend_ab", "takt", "gegenpartei", "kategorie"):
            if f in g:
                g[f] = text(g[f])
        if "gegenkonten" in g:
            g["gegenkonten"] = [{"konto": text(x.get("konto")), "quelle": text(x.get("quelle"))} for x in dicts(g["gegenkonten"])]
        if "schwelle" in g:
            g["schwelle"] = number(g["schwelle"], 0.01)
    bil = cfg.get("bilanz")
    if isinstance(bil, dict):
        for f in ("rollen", "verlauf", "konten_zuordnung"):
            if f in bil:
                bil[f] = {k: v for k, v in bil[f].items() if isinstance(k, str) and isinstance(v, dict if f == "konten_zuordnung" else str)} if isinstance(bil[f], dict) else {}
        for f in ("illiquide_konten", "ausgeblendet", "immer_anzeigen", "illiquide_rollen"):
            if f in bil:
                bil[f] = texts(bil[f])
        for f in ("monate_zurueck", "inaktiv_monate"):
            if f in bil and number(bil[f]) is None:
                bil.pop(f)
    ab = cfg.get("abruf")
    if isinstance(ab, dict):
        for f in ("online", "offline"):
            if f in ab:
                ab[f] = texts(ab[f])
    if "nicht_buchen" in cfg:
        keep, have = [], set()
        for x in cfg["nicht_buchen"]:
            acc, _, tag = text(x.get("key")).partition("|")
            if acc and rules.TAG_RE.fullmatch(tag) and x["key"] not in have:
                have.add(x["key"])
                keep.append({k: v for k, v in x.items() if isinstance(v, (str, int, float)) and not isinstance(v, bool)})
        cfg["nicht_buchen"] = keep[-1000:]
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
    out["zeitplan"].pop("voll_lesen_stunden", None)       # replaced by voll_lesen_tage (3.9.30)
    out.pop("mitteilungen", None)                         # no macOS notifications any more: the sidebar shows what is to do (3.12.24)
    for k in ("beteiligungen", "saldo_spiegel"):          # replaced by gesellschaften (3.12.18)
        out.pop(k, None)
    out["kapitalfluss"].pop("beteiligungs_gruppen", None)
    for i, b in enumerate(out["bereiche"]):
        b.setdefault("id", "b%d" % (i + 1))
        b.setdefault("name", "Bereich %d" % (i + 1))
        b.setdefault("konten", [])
        b.setdefault("art", "")
        b.setdefault("aktiv", True)
    if out["bereiche"] and not any(b.get("haupt") for b in out["bereiche"]):
        out["bereiche"][0]["haupt"] = True
    for im in out.get("immobilien") or []:
        im.setdefault("kalkulationen", [])
        im.setdefault("dokumente", [])
        im.setdefault("darlehen_konten", {})
    return out


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
    back = int((config.get("bilanz", {}) or {}).get("monate_zurueck", 0) or 0)
    if back <= 0:
        return date(2000, 1, 1)
    y, m = add_months(today, -(back + 1))
    start = date(y, m, 1)
    for l in config.get("darlehen", []) or []:
        try:
            ab = date.fromisoformat(l["ab_datum"])
            start = min(start, date(ab.year - 1, 1, 1))
        except Exception:
            pass
    for g in config.get("gesellschaften", []) or []:
        rs = parse_start((g or {}).get("rueckwirkend_ab"))
        if rs == "alles":
            start = min(start, date(2000, 1, 1))
        elif rs:
            start = min(start, date(rs.year - 1, 1, 1))
    return start


INCREMENT_DAYS = 30          # quick read: only the last 30 days of transactions, older ones come from the last full read
RECHECK_HOURS = 12           # a balance the quick read cannot explain triggers a full read at most this often


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
    for d in config.get("darlehen") or []:
        if isinstance(d, dict) and d.get("aktiv", True):
            add(d.get("darlehenskonto"))
            for src in d.get("quellkonten") or []:
                add(src)
    companies = [g for g in config.get("gesellschaften") or [] if isinstance(g, dict) and (g.get("beteiligung") or g.get("gegenkonten"))]
    if companies:
        areas = {str(b["id"]): b for b in bereiche_for(ledger, config)}
        for g in companies:
            add(g.get("beteiligung"))
            for k in g.get("gegenkonten") or []:
                if isinstance(k, dict):
                    add(k.get("konto")); add(k.get("quelle"))
            area = areas.get(str(g.get("bereich")))
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
    return "gesellschaft" if _FIRMA_RE.search(name or "") else "privat"


def bereiche_for(ledger: Ledger, config: dict) -> List[dict]:
    """Bereiche mit aufgeloesten Konten: konfiguriert, sonst alle Kontengruppen der obersten Ebene.
    Jeder Bereich: {"id", "name", "art", "anteil", "haupt", "konten" (Referenzen), "leaves" (Account), "gruppen"}."""
    out: List[dict] = []
    cfg = [b for b in (config.get("bereiche") or []) if isinstance(b, dict) and b.get("aktiv", True)]
    if cfg:
        for b in cfg:
            leaves: List[Account] = []
            gruppen: List[Account] = []
            seen = set()
            for ref in b.get("konten") or []:
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
            if not leaves and not b.get("konten"):
                continue
            first_group = gruppen[0] if gruppen else None
            anteil = b.get("anteil")
            out.append({"id": str(b.get("id")), "name": b.get("name") or (first_group.name if first_group else "Bereich"),
                        "art": b.get("art") or _bereich_art(b.get("name") or (first_group.name if first_group else "")),
                        "anteil": float(anteil) if anteil not in (None, "") else None, "haupt": bool(b.get("haupt")),
                        "konten": list(b.get("konten") or []), "leaves": leaves, "gruppen": gruppen})
    if not out:
        for g in ledger.roots():
            out.append({"id": g.uuid, "name": g.name, "art": _bereich_art(g.name), "anteil": None, "haupt": False,
                        "konten": ["%s | %s" % (g.uuid, g.name)], "leaves": ledger.descendants(g.uuid), "gruppen": [g]})
        if out and not any(b["haupt"] for b in out):
            (next((b for b in out if b["art"] == "privat"), None) or out[0])["haupt"] = True
        # Vorschlag: Hauptbereich zuerst, dann weitere private Bereiche, dann Gesellschaften
        out.sort(key=lambda b: (not b["haupt"], b["art"] != "privat"))
    if out and not any(b["haupt"] for b in out):
        out[0]["haupt"] = True
    # Explizite Kontenzuordnung (Einrichtung → Konten): Konto in genau diesem Bereich, unabhaengig von der Gruppe
    by_id = {b["id"]: b for b in out}
    for ref, z in ((config.get("bilanz") or {}).get("konten_zuordnung") or {}).items():
        if not isinstance(z, dict) or not z.get("bereich") or z["bereich"] not in by_id:
            continue
        try:
            a = ledger.resolve(ref)
        except KeyError:
            continue
        if a.group:
            continue
        for b in out:
            b["leaves"] = [x for x in b["leaves"] if x.uuid != a.uuid]
        by_id[z["bereich"]]["leaves"].append(a)
    return out


def abruf_arten(ledger: Ledger, config: dict) -> Dict[str, Dict[str, str]]:
    """uuid -> {"art": "online"|"offline", "grund": Text} fuer alle Konten (keine Gruppen). Online = MoneyMoney ruft bei
    Bank oder Dienst ab; offline = von Hand gefuehrt, kein Abruf (zaehlt nicht fuer den Datenstand). MoneyMoney setzt den
    Abrufzeitpunkt auch bei Offline-Konten (z. B. nach einer Buchung), deshalb mehrere Merkmale; eigene Festlegung geht vor."""
    out: Dict[str, Dict[str, str]] = {}
    for a in ledger.accounts.values():
        if not a.group:
            art, grund = ledger.fetch_kind(a.uuid, config)
            out[a.uuid] = {"art": art, "grund": tr(grund)}
    return out


def freeze_assignments(ledger: Ledger, config: dict) -> Optional[dict]:
    """Bestaetigte Konten ohne feste Position/Verlaufsquelle (aeltere Einrichtung mit "auto") auf den heute erkannten Wert
    festlegen, damit spaetere Aenderungen an Name, Typ oder Gruppe in MoneyMoney die Zuordnung nicht verschieben.
    Liefert die geaenderte Konfiguration oder None, wenn nichts zu tun ist. Unbestaetigte (neue) Konten bleiben Vorschlag."""
    bil = config.get("bilanz") or {}
    zu = bil.get("konten_zuordnung") or {}
    if not zu:
        return None
    roles = account_roles(ledger, config)
    ver_cfg = {}
    for ref in (bil.get("verlauf") or {}):
        try:
            ver_cfg[ledger.resolve(ref).uuid] = ref
        except KeyError:
            pass
    new = copy.deepcopy(config)
    nb = new.setdefault("bilanz", {})
    nzu, nver = nb.setdefault("konten_zuordnung", {}), nb.setdefault("verlauf", {})
    changed = 0
    for ref, z in zu.items():
        if not isinstance(z, dict) or not z.get("bestaetigt", True):
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
            nver[ref] = "stand" if a.portfolio else "umsaetze"
            changed += 1
    return new if changed else None


def konten_neu(ledger: Ledger, config: dict, bereiche: List[dict], roles: Dict[str, str]) -> List[dict]:
    """Konten ohne bestaetigte Zuordnung (neu in MoneyMoney oder noch nie bestaetigt) mit Vorschlag."""
    zu = (config.get("bilanz") or {}).get("konten_zuordnung") or {}
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
        out.append({"uuid": a.uuid, "name": a.name, "pfad": a.path, "typ": a.type, "saldo": a.balance,
                    "bereich": b["id"] if b else None, "bereich_name": b["name"] if b else None, "position": roles.get(a.uuid, "sonstiges")})
    return out


def main_bereich(bereiche: List[dict]) -> Optional[dict]:
    return next((b for b in bereiche if b.get("haupt")), bereiche[0] if bereiche else None)


# ---------------------------------------------------------------------------
# Konfiguration pruefen
# ---------------------------------------------------------------------------

def check_config(ledger: Ledger, categories: List[dict], config: dict) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    cat_names = {str(c.get("name") or "") for c in categories}
    cat_names |= {str(c.get("path") or "").split("\\")[-1] for c in categories}

    def add(level, text):
        out.append({"stufe": level, "text": text})

    def ref(label, r, want_offline=False, group_ok=True, want_group=False):
        try:
            a = ledger.resolve(r)
        except KeyError as e:
            add("fehler", "%s: %s" % (label, e)); return None
        if want_offline and not ledger.writable(a.uuid, config):
            add("fehler", tr("s_s_s_hat_eine_bankanbindung") % (label, a.path))
        elif not group_ok and a.group:
            add("fehler", tr("s_s_s_ist_eine_gruppe") % (label, a.path))
        elif want_group and not a.group:
            add("fehler", tr("s_s_s_ist_keine_gruppe") % (label, a.path))
        else:
            add("ok", "%s → %s" % (label, a.path))
        return a

    def cat(label, name):
        if name and categories and name not in cat_names and name.split("\\")[-1] not in cat_names:
            add("warnung", tr("s_s_kategorie_s_existiert_nicht") % (label, name))

    for l in config.get("darlehen", []) or []:
        n = l.get("name", "?") + ("" if l.get("aktiv", True) else " (inaktiv)")
        ref(tr("s_darlehen_s_konto") % n, l.get("darlehenskonto", ""), want_offline=True, group_ok=False)
        for s_ in l.get("quellkonten", []) or []:
            ref("Darlehen %s: Quelle" % n, s_, group_ok=False)
        b = l.get("buchung", {}) or {}
        cat("Darlehen %s" % n, b.get("kategorie_tilgung"))
        cat("Darlehen %s" % n, b.get("kategorie_zins"))
        erk = l.get("erkennung") or {}
        iban = (erk.get("gegen_iban") or "").replace(" ", "")
        if not iban and not erk.get("text_enthaelt"):
            add("fehler", tr("s_darlehen_s_erkennung_braucht_gegen") % n)
        if iban and not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", iban):
            add("fehler", tr("s_darlehen_s_s_ist_keine") % (n, iban))
        try:
            date.fromisoformat(l.get("ab_datum", ""))
        except ValueError:
            add("fehler", tr("s_darlehen_s_ab_datum_fehlt") % n)
    bil = config.get("bilanz", {}) or {}
    for b in config.get("bereiche") or []:
        if not isinstance(b, dict):
            continue
        if not b.get("konten"):
            add("fehler", tr("s_bereich_s_hat_keine_konten") % b.get("name"))
        for r in b.get("konten") or []:
            ref("Bereich %s" % b.get("name"), r)
    bereiche = bereiche_for(ledger, config)
    seen_leaf: Dict[str, str] = {}
    roles = account_roles(ledger, config)
    for b in bereiche:
        for a in b["leaves"]:
            if a.uuid in seen_leaf and seen_leaf[a.uuid] != b["name"]:
                add("warnung", tr("s_konto_s_liegt_in_mehreren") % (a.path, seen_leaf[a.uuid], b["name"]))
            seen_leaf[a.uuid] = b["name"]
        missing = [a.path for a in b["leaves"] if roles.get(a.uuid) == "sonstiges"]
        if missing:
            add("warnung", tr("s_s_konten_ohne_position_umsaetze")
                % (b["name"], "; ".join(missing[:8]) + (" …" if len(missing) > 8 else "")))
    by_id = {b["id"]: b for b in bereiche}
    used: Dict[str, str] = {}
    for g in config.get("gesellschaften") or []:
        if not isinstance(g, dict) or not (g.get("beteiligung") or g.get("gegenkonten")):
            continue
        b = by_id.get(str(g.get("bereich")))
        if b is None:              # area removed or changed: the rules wait (no error, so the areas can still be saved)
            add("warnung", tr("s_gesellschaft_s_bereich_fehlt") % g.get("bereich"))
            continue
        n, inside = b["name"], {a.uuid for a in b["leaves"]}
        if g.get("takt") not in (None, "", "taeglich", "monatlich"):
            add("fehler", tr("s_s_takt_unbekannt") % (n, g.get("takt")))
        rs = parse_start(g.get("rueckwirkend_ab")) if g.get("rueckwirkend_ab") else ""
        if rs is None or (isinstance(rs, date) and rs > date.today()):
            add("fehler", tr("s_s_rueckwirkend_ungueltig") % (n, g["rueckwirkend_ab"]))
        targets = []
        if g.get("beteiligung"):
            if b.get("anteil") is None:
                add("fehler", tr("s_s_anteil_fehlt") % (tr("s_regel_beteiligung") % n))
            a = ref(tr("s_regel_beteiligung") % n, g["beteiligung"], want_offline=True, group_ok=False)
            if a is not None:
                targets.append(a)
                if roles.get(a.uuid) != "beteiligungen":
                    add("warnung", tr("s_s_keine_position_beteiligungen") % (tr("s_regel_beteiligung") % n, a.name))
        for x in g.get("gegenkonten") or []:
            if not isinstance(x, dict) or not x.get("konto") or not x.get("quelle"):
                continue
            a = ref(tr("s_regel_gegenkonto") % n, x["konto"], group_ok=False)
            q = ref(tr("s_chk_gegenkonto_quelle") % n, x["quelle"], group_ok=False)
            if a is not None:
                targets.append(a)
            if a is not None and q is not None and not (ledger.writable(a.uuid, config) or ledger.writable(q.uuid, config)):
                add("warnung", tr("s_s_spiegel_kein_offline") % (tr("s_regel_gegenkonto") % n, a.name, q.name))
            if q is not None and q.uuid not in inside:
                add("warnung", tr("s_s_quelle_nicht_in_gesellschaft") % (n, q.path))
            if q is not None and g.get("beteiligung") and roles.get(q.uuid) in rules.VALUE_OFF:
                add("warnung", tr("s_s_doppelt_gezaehlt") % (n, q.name))
        for a in targets:
            if a.uuid in inside:
                add("fehler", tr("s_s_zielkonto_liegt_innerhalb_der") % ("%s: %s" % (n, a.name)))
            if a.uuid in used:
                add("fehler", tr("s_konto_s_mehrfach_ziel") % (a.path, used[a.uuid], n))
            used.setdefault(a.uuid, n)
    for r in bil.get("illiquide_konten") or []:
        ref(tr("s_chk_bilanz_illiquide"), r)
    for k, v in (bil.get("rollen") or {}).items():
        if not k.startswith("_"):
            ref(tr("s_position_fuer"), k)
            if v not in ROLES:
                add("fehler", tr("s_unbekannte_position_s_fuer_s") % (v, k))
    for k, v in (bil.get("verlauf") or {}).items():
        ref(tr("s_verlauf_fuer"), k, group_ok=False)
        if v not in ("umsaetze", "stand"):
            add("fehler", tr("s_unbekannte_verlaufsquelle_s_fuer_s") % (v, k))
    for k in (bil.get("ausgeblendet") or []) + (bil.get("immer_anzeigen") or []):
        ref(tr("s_chk_bilanz_anzeige"), k)
    for im in config.get("immobilien") or []:
        n = im.get("name") or "?"
        if im.get("objekt_konto"):
            ref("Immobilie %s: Objektkonto" % n, im["objekt_konto"], group_ok=False)
        for ln, r in (im.get("darlehen_konten") or {}).items():
            if r:
                ref("Immobilie %s: Darlehen %s" % (n, ln), r, group_ok=False)
        if im.get("bereich") and not any(b["id"] == im["bereich"] for b in bereiche):
            add("warnung", tr("s_immobilie_s_bereich_s_existiert") % (n, im["bereich"]))
        if im.get("kategorie"):
            cat("Immobilie %s" % n, str(im["kategorie"]).split("\\")[-1])
    kfc = config.get("kapitalfluss", {}) or {}
    for k, v in (kfc.get("kategorie_zuordnung") or {}).items():
        if k.startswith("_"):
            continue
        cat(tr("s_chk_kf_zuordnung"), k)
        if str(v).split("/")[0] not in ("Einnahmen", "Ausgaben", "Investitionen", "Finanzierung"):
            add("fehler", tr("s_kapitalfluss_zuordnung_s_s_unbekannt") % (k, v))
    for k, v in (kfc.get("kategorie_zu_konto") or {}).items():
        if not k.startswith("_"):
            cat(tr("s_chk_kf_depotzuordnung"), k)
            ref(tr("s_kapitalfluss_depot_fuer_s") % k, v, group_ok=False)
    st = config.get("steuer", {}) or {}
    for k, v in (st.get("objekt_darlehen") or {}).items():
        ref(tr("s_steuer_darlehen_fuer_objekt_s") % v, k)
    bel = config.get("belege", {}) or {}
    folder = os.path.expanduser(bel.get("ordner") or DEFAULT_CONFIG["belege"]["ordner"])
    if os.path.isdir(folder) and not os.access(folder, os.W_OK):
        add("fehler", tr("s_belegordner_nicht_beschreibbar_s") % folder)
    for h in ledger.hints:
        add("hinweis", h)
    return out


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

# Kontor's own lists of its bookings until 3.13.0 (state): replaced by what is in MoneyMoney, see migrate_booking_state
OLD_STATE_KEYS = ("kontor_buchungen", "kontor_abgelehnt", "kontor_neu", "abgleich", "rueckwirkend", "spiegel_seit")


def not_booked_entry(row: dict, key: str) -> dict:
    """An entry of "Don't book" (config nicht_buchen): the booking as it was shown, so the list can name it."""
    def num(v):
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return None
    out = {"key": key, "datum": str(row.get("datum") or "")[:10], "betrag": num(row.get("betrag")),
           "konto": str(row.get("konto_name") or row.get("konto") or "")[:120], "art": str(row.get("art") or "")[:20],
           "text": rules.TAG_RE.sub("", str(row.get("text") or row.get("zweck") or "")).strip(" ·")[:200],
           "regel": str(row.get("regel") or "")[:120], "seit": datetime.now().strftime("%Y-%m-%d %H:%M")}
    return {k: v for k, v in out.items() if v is not None}


def migrate_booking_state(store: Store) -> bool:
    """Until 3.13.0 Kontor kept lists of its own bookings in its state. From 3.13.1 it derives everything from MoneyMoney and the
    settings; only your decisions not to book a booking stay -- moved into the settings (nicht_buchen, part of every backup),
    the rest is dropped. True if something was there."""
    st = store.load("state.json", {}) or {}
    if not any(k in st for k in OLD_STATE_KEYS):
        return False
    rej = [r for r in st.get("kontor_abgelehnt") or [] if isinstance(r, dict) and r.get("konto") and r.get("tag")
           and rules.TAG_RE.fullmatch(canon_tag(r.get("tag")))]
    if rej:
        cfg = store.load("config.json", {}) or {}
        cur = [x for x in cfg.get("nicht_buchen") or [] if isinstance(x, dict)]
        have = {x.get("key") for x in cur}
        for r in rej:
            key = rules.bkey(str(r["konto"]), r["tag"])
            if key not in have:
                cur.append(dict(not_booked_entry(dict(r, konto_name=r.get("konto_name") or ""), key), seit=str(r.get("abgelehnt") or "")[:16]))
                have.add(key)
        cfg["nicht_buchen"] = cur[-1000:]
        store.save("config.json", cfg)

    def drop(cur: dict) -> None:
        for k in OLD_STATE_KEYS:
            cur.pop(k, None)
    store.update("state.json", drop, {})
    log.info("Kontor's own booking lists replaced by MoneyMoney (%d decision(s) not to book kept)", len(rej))
    return True


def fix_start_dates(ledger: Ledger, config: dict, today: date) -> Optional[dict]:
    """"Buchen ab" of each company as a day: until 3.13.0 it could be empty (from now on). An empty one gets the day of Kontor's
    first booking for the company's rules (so everything since is kept right), otherwise today -- and never moves again.
    Returns the changed configuration, or None."""
    gs = [g for g in config.get("gesellschaften") or [] if isinstance(g, dict) and (g.get("beteiligung") or g.get("gegenkonten"))
          and parse_start(g.get("rueckwirkend_ab")) is None]
    if not gs:
        return None
    new = copy.deepcopy(config)
    areas = {str(b["id"]): b for b in bereiche_for(ledger, config)}
    changed = False
    for g in new.get("gesellschaften") or []:
        if not isinstance(g, dict) or not (g.get("beteiligung") or g.get("gegenkonten")) or parse_start(g.get("rueckwirkend_ab")) is not None:
            continue
        area = areas.get(str(g.get("bereich")))
        if area is not None:
            g["rueckwirkend_ab"] = (rules.default_start(ledger, g, area, today) or rules.current_day(g, today)).isoformat()
            changed = True
    return new if changed else None


def _plan_round(ledger: Ledger, config: dict, today: date, seen: "rules.Seen", hold: Optional[set] = None,
                edits: Optional[Dict[str, dict]] = None, auto: bool = False) -> "rules.RuleResult":
    """The rules once: hold = left out of this run (planned as not booked: what follows makes up for it, a loan's interest
    after it waits too), edits = your changes from the approval (planned as changed), auto = only what booking fully
    automatically books (what is new since the last check)."""
    return plan_all(ledger, config, today, set(hold or ()), edits, seen, auto)


def proposal_rows(ledger: Ledger, proposals: List[Proposal]) -> List[dict]:
    """Bookings waiting for approval, as the interface shows them."""
    return [{"art": x.kind, "konto": x.account_path, "konto_name": ledger.accounts[x.account_uuid].name if x.account_uuid in ledger.accounts else "",
             "konto_id": x.account_uuid, "key": x.key, "datum": x.booking_date.isoformat(), "betrag": x.amount, "text": x.purpose,
             "kategorie": x.category, "tag": x.tag, "regel": x.rule, "rueckwirkend": x.retro, "gegenpartei": x.payee}
            for x in proposals]


def plan_pending(ledger: Ledger, config: dict, state: dict, today: date, hold: Optional[set] = None,
                 edits: Optional[Dict[str, dict]] = None) -> List[dict]:
    """The approval list with your selection: what you leave out or change, and everything planned after it, recalculated
    (nothing is written)."""
    lg = ledger.fork()
    seen = rules.Seen.from_state(state.get("gesehen"), lg, today)
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
        path = str(c.get("path") or c.get("name") or "").replace("\\", " / ")
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
    for t in ledger.txs:
        if t.account_uuid not in ent_of:
            continue
        path, q = categorize.effective(kat, t)
        out.append({"id": t.id, "konto": t.account_uuid, "konto_name": ledger.accounts[t.account_uuid].name, "entitaet": ent_of[t.account_uuid],
                    "datum": t.booking_date.isoformat(), "betrag": t.amount, "name": t.name[:80], "zweck": t.purpose[:140],
                    "kategorie": path, "quelle": q, "gebucht": t.booked, "haken": t.checkmark,
                    "braucht": categorize.needs_category(t, banks)})
    out.sort(key=lambda x: (x["datum"], x["id"]), reverse=True)
    return out


def record_holdings(state: dict, portfolios: Dict[str, list], today: date) -> None:
    """Month-end values of the securities of each portfolio as Kontor sees them (overwritten during the month, like the
    portfolio values), for the breakdown of a portfolio in months the MoneyMoney history does not cover."""
    if not portfolios:
        return
    mk = month_key(today)
    snaps, names = state.setdefault("snapshots_wp", {}), state.setdefault("wp_namen", {})
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
                pos.append({"name": str(p.get("name") or ""), "isin": str(p.get("isin") or ""), "menge": float(p.get("quantity") or 0),
                            "kurs": float(p.get("marketPrice") or p.get("price") or 0), "wert": float(p.get("marketValue") or p.get("amount") or 0),
                            "einstand": float(p.get("purchaseValue") or 0), "waehrung": str(p.get("currency") or acc.currency),
                            "klasse": str(p.get("assetClass") or "")})
            except (TypeError, ValueError, AttributeError):
                continue
        pos.sort(key=lambda x: -x["wert"])
        out.append({"konto": uuid, "name": acc.name, "entitaet": ent_of.get(uuid, ""), "summe": round(sum(p["wert"] for p in pos), 2),
                    "einstand": round(sum(p["einstand"] for p in pos), 2), "positionen": pos})
    return out


# ---------------------------------------------------------------------------
# Immobilien
# ---------------------------------------------------------------------------

def immo_active(im: dict) -> Optional[dict]:
    kalks = im.get("kalkulationen") or []
    if not kalks:
        return None
    return next((k for k in kalks if k.get("aktiv")), kalks[0])


def immo_results(config: dict, today: date) -> Dict[str, dict]:
    """id -> Ergebnis der aktiven Kalkulation je Immobilie (fuer Datensatz und Planung)."""
    out: Dict[str, dict] = {}
    for im in config.get("immobilien") or []:
        k = immo_active(im)
        if not k:
            continue
        try:
            res = realestate.berechne(k.get("eingaben") or {}, today)
        except Exception as e:  # pragma: no cover - fehlerhafte Eingaben duerfen den Bericht nicht stoppen
            log.warning("Property %s: calculation failed (%s)", im.get("id"), type(e).__name__)
            out[str(im.get("id"))] = {"fehler": str(e)}
            continue
        out[str(im.get("id"))] = {"kalkulation": k.get("id"), "name": k.get("name"), "kennzahlen": res["kennzahlen"], "jahre": res["jahre"],
                                  "hinweise": res["hinweise"], "darlehen_namen": res["darlehen_namen"], "start": res["start"],
                                  "reihen": realestate.planreihen(res)}
    return out


def immo_afa_map(config: dict, results: Dict[str, dict]) -> Dict[str, Dict[str, float]]:
    """Objektname (letzter Teil der Vermietungskategorie bzw. Name) -> {Jahr: AfA} aus den aktiven Kalkulationen."""
    out: Dict[str, Dict[str, float]] = {}
    for im in config.get("immobilien") or []:
        r = results.get(str(im.get("id")))
        if not r or "fehler" in r:
            continue
        obj = (norm_cat(im.get("kategorie") or "").split(" / ")[-1] if im.get("kategorie") else "") or str(im.get("name") or "")
        out[obj] = {str(j["jahr"]): j["afa"] for j in r["jahre"]}
    return out


def immo_for_plan(config: dict, bereich_id: str, results: Dict[str, dict]) -> List[dict]:
    """Kalkulationen eines Bereichs, die in die Planung uebernommen werden sollen."""
    out = []
    for im in config.get("immobilien") or []:
        if str(im.get("bereich") or "") != str(bereich_id) or not im.get("in_planung"):
            continue
        r = results.get(str(im.get("id")))
        if not r or "fehler" in r:
            continue
        out.append({"name": im.get("name"), "kategorie": im.get("kategorie") or "", "objekt_konto": im.get("objekt_konto"),
                    "darlehen_konten": im.get("darlehen_konten") or {}, "reihen": r["reihen"]})
    return out


def immo_soll_ist(ledger: Ledger, config: dict, im: dict, res: dict, roles: Dict[str, str], today: date) -> List[dict]:
    """Jahresvergleich Kalkulation (Soll) gegen MoneyMoney (Ist): Miete, Kosten, Zinsen, Restschuld."""
    cat = norm_cat(im.get("kategorie") or "").lower()
    loans: Dict[str, str] = {}
    for ln, ref in (im.get("darlehen_konten") or {}).items():
        try:
            loans[ln] = ledger.resolve(ref).uuid
        except KeyError:
            pass
    years = sorted({j["jahr"] for j in res.get("jahre", [])} & {t.booking_date.year for t in ledger.txs})
    out = []
    cost_words = [w.lower() for w in COST_WORDS_DEFAULT]
    for y in years:
        soll = next(j for j in res["jahre"] if j["jahr"] == y)
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
        out.append({"jahr": y, "miete_soll": soll["miete"], "miete_ist": round(miete, 2), "kosten_soll": soll["kosten"] + soll["ruecklage"],
                    "kosten_ist": round(kosten, 2), "zins_soll": soll["zins"], "zins_ist": round(zins, 2),
                    "restschuld_soll": soll["restschuld"], "restschuld_ist": round(rest, 2) if loans else None})
    return out


COST_WORDS_DEFAULT = ["zins", "interest", "gebühr", "gebuehr", "entgelt", "provision", "bereitstellung", "#kontor-zins", "#mm-zins"]


def _kat_sig(store: Store, config: dict, categories: Optional[List[dict]]) -> tuple:
    return (store.stamp(categorize.FILE), json.dumps(config.get("kategorien") or {}, sort_keys=True), len(categories or []))


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


def bank_accounts(roles: Dict[str, str]) -> set:
    """The accounts a category matters for (cash flow, tax): those with the position "liquidity"."""
    return {u for u, r in roles.items() if r == "liquiditaet"}


def _prepare_categories(store: Store, ledger: Ledger, config: dict, categories: Optional[List[dict]],
                        step: Callable[[float, str], None]) -> dict:
    """Categories are MoneyMoney's; on top only what you assigned and what waits to be written there. The patterns for the
    suggestions are learned at the full read (daily)."""
    categorize.set_standard(categories)
    kat = categorize.load(store)
    base = categorize.digest(kat)
    changed = False
    if not getattr(ledger, "incremental", False) or not kat.get("gelernt_am"):
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
    cur = state.setdefault("snapshots_wp", {})
    for mk, row in (built.get("snapshots_wp") or {}).items():
        cur.setdefault(mk, {}).update(row)
    if built.get("wp_namen"):
        state.setdefault("wp_namen", {}).update(built["wp_namen"])


def build_report(store: Store, ledger: Ledger, config: dict, state: dict, today: date, warnings: List[str],
                 categories: Optional[List[dict]] = None, progress: Optional[Callable[[float, str], None]] = None) -> dict:
    # Fortschritt grob nach Laufzeit eines Laufs ohne Zwischenergebnisse gewichtet: Kategorien 5-25 %, Bereiche 25-75 % (nach
    # Umsatzzahl), Steuer bis 85 %, Kategorienstatistik und Umsatzliste bis 95 %, Speichern
    step = progress or (lambda f, t: None)
    step(0.05, tr("s_schritt_kategorien"))
    kat = prepare_categories(store, ledger, config, categories, lambda f, t: step(0.05 + 0.2 * f, t))
    zus = {k: v for k, v in (kat.get("verwendung") or {}).items() if v == "zusammen"}
    if zus:                       # Kapitalfluss-Zeilen: zusammengefasste Kategorien (nur fuer die Berechnung, nicht gespeichert)
        config = dict(config, kapitalfluss=dict(config.get("kapitalfluss") or {}, _zusammen=zus))
    record_snapshot(state.setdefault("snapshots", {}), ledger.accounts.values(), today)
    record_holdings(state, getattr(ledger, "portfolios", None) or {}, today)
    # aus MoneyMoney uebernommene Kontostand-Verlaeufe (verschluesselt abgelegt, nur im Speicher in den Zustand gelegt)
    mmh = store.load_shared(MM_HISTORY_FILE, {}) or {}
    state["historie_mm"], state["historie_mm_anfang"] = mmh.get("konten") or {}, mmh.get("anfang") or {}
    state["historie_mm_wp"] = mmh.get("wertpapiere") or {}
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
            ds = build_dataset(ledger, config, state, today, b, roles, warnings if (haupt and b["id"] == haupt["id"]) else [], sub)
            ds["budgets"] = budgets
            datasets[b["id"]] = ds
        except Exception as e:
            log.exception("Area %s: report failed", str(b["id"])[:8])
            datasets[b["id"]] = {"fehler": str(e), "wurzel": b["name"]}
    try:
        equity_ratio(ledger, config, roles, bereiche, datasets)
    except Exception:  # pragma: no cover
        log.exception("Equity ratio failed")
    neu = konten_neu(ledger, config, bereiche, roles)
    if neu:
        warnings.append(tr("s_s_ohne_bestaetigte_zuordnung_einrichtu")
                        % (tr("s_ein_konto") if len(neu) == 1 else tr("s_d_konten") % len(neu), ", ".join(k["name"] for k in neu[:5]) + (" …" if len(neu) > 5 else "")))
    immobilien = []
    for im in config.get("immobilien") or []:
        r = immo_res.get(str(im.get("id")))
        entry = {"id": im.get("id"), "name": im.get("name"), "bereich": im.get("bereich"), "in_planung": bool(im.get("in_planung")),
                 "kategorie": im.get("kategorie"), "objekt_konto": im.get("objekt_konto"), "darlehen_konten": im.get("darlehen_konten") or {},
                 "kalkulationen": [{"id": k.get("id"), "name": k.get("name"), "aktiv": bool(k.get("aktiv")), "erstellt": k.get("erstellt")} for k in im.get("kalkulationen") or []],
                 "dokumente": im.get("dokumente") or [], "notizen": im.get("notizen") or ""}
        if r and "fehler" not in r:
            entry.update({"kennzahlen": r["kennzahlen"], "jahre": r["jahre"], "hinweise": r["hinweise"], "darlehen_namen": r["darlehen_namen"], "start": r["start"]})
            try:
                entry["soll_ist"] = immo_soll_ist(ledger, config, im, r, roles, today)
            except Exception as e:  # pragma: no cover
                entry["soll_ist"] = []
                log.warning("Plan vs. actual %s: %s", im.get("id"), type(e).__name__)
        elif r:
            entry["fehler"] = r["fehler"]
        immobilien.append(entry)
    for bid, ds in datasets.items():
        if "fehler" not in ds:
            log.debug("Area %s: %d months (%s to %s), %d accounts, %d inactive, %d warning(s)", str(bid)[:8],
                      len(ds["monate"]), ds["monate"][0] if ds["monate"] else "-", ds["monate"][-1] if ds["monate"] else "-",
                      sum(1 for r in ds["bilanz"]["zeilen"] if not r["gruppe"]), len(ds.get("konten_inaktiv") or []), len(ds.get("warnungen") or []))
    dataset = {
        "erstellt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "heute": today.isoformat(),
        "haupt": haupt["id"] if haupt else None,
        "bereiche": datasets,
        "bereich_namen": {b["id"]: b["name"] for b in bereiche},
        "bereich_info": {b["id"]: {"name": b["name"], "art": b["art"], "anteil": b["anteil"], "haupt": b["haupt"], "konten": b["konten"],
                                   "gruppen": [g.name for g in b["gruppen"]], "anzahl_konten": len(b["leaves"])} for b in bereiche},
        "konten": account_tree(ledger, config, roles, datasets),
        "steuer": (step(0.76, "Steuer"), _cached(ledger, "_tax_cache", (ledger._kat_sig, today.isoformat(), _bereiche_sig(bereiche),
                                                   json.dumps([config.get(k) for k in ("steuer", "kapitalfluss", "gesellschaften", "bereiche", "immobilien")]
                                                              + [(config.get("bilanz") or {}).get(k) for k in ("rollen", "konten_zuordnung")], sort_keys=True, default=str)),
                          lambda: build_tax(ledger, config, today, bereiche, roles, immo_afa_map(config, immo_res))))[1],
        "depots": portfolio_summary(ledger, bereiche),
        "immobilien": immobilien,
        "budgets": budgets,
        "warnungen": warnings,
        "kategorien": dict((step(0.86, "Kategorienstatistik"), _cached(ledger, "_katstats_cache", (ledger._kat_sig, tuple(sorted(bank_accounts(roles)))),
                                                                                  lambda: categorize.stats(kat, ledger, bank_accounts(roles))))[1],
                           verwendung=len(kat.get("verwendung") or {})),
        "konten_neu": neu,
    }
    step(0.88, "Speichern")
    store.save("dataset.json", dataset)
    sig = (ledger._kat_sig, _bereiche_sig(bereiche), tuple(sorted(bank_accounts(roles))))
    cached = getattr(ledger, "_ums_cache", None)
    if cached and cached[0] == sig and store.exists("transactions.json"):
        ums = cached[1]                # Umsatzliste unveraendert (z. B. nur Verlauf geaendert) -> nicht neu schreiben
    else:
        step(0.93, "Umsatzliste")
        ums = compact_transactions(ledger, bereiche, store, bank_accounts(roles))
        store.save("transactions.json", ums)
        ledger._ums_cache = (sig, ums)
    dataset["_umsaetze"] = ums        # fuer den Dienst: Liste im Speicher behalten (teilt die Strings mit dem Ledger), nicht Teil der Datei
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
        inactive.update(ds.get("konten_inaktiv") or [])
        inactive_auto.update(ds.get("konten_inaktiv_auto") or [])
        limits.update(ds.get("konten_aktivitaet") or {})
        bname = (ds.get("bereich") or {}).get("name") or ""
        for r in ((ds.get("bilanz") or {}).get("zeilen") or []) + ((ds.get("bilanz") or {}).get("ausserhalb") or []):
            if not r.get("gruppe") and r.get("verlauf"):
                verlauf[r["id"]] = r["verlauf"]
            if not r.get("gruppe") and bname:
                bereich_of[r["id"]] = (bereich_of[r["id"]] + ", " + bname) if r["id"] in bereich_of else bname
                bereich_id.setdefault(r["id"], bid)
    zu = (config.get("bilanz") or {}).get("konten_zuordnung") or {}
    confirmed = set()
    for ref in zu:
        try:
            confirmed.add(ledger.resolve(ref).uuid)
        except KeyError:
            pass
    n_inakt = int((config.get("bilanz") or {}).get("inaktiv_monate", 12) or 12)
    y, m = add_months(date.today(), -n_inakt)
    cutoff = date(y, m, 1)
    last_tx: Dict[str, date] = {}
    for t in ledger.txs:
        if t.booked and (t.account_uuid not in last_tx or t.booking_date > last_tx[t.account_uuid]):
            last_tx[t.account_uuid] = t.booking_date
    out = []
    kinds = abruf_arten(ledger, config)
    plain = copy.deepcopy(config)                # Vorschlag ohne eigene Zuordnungen (was Kontor heute erkennen wuerde)
    plain.setdefault("bilanz", {})["rollen"] = {}
    plain["bilanz"]["konten_zuordnung"] = {r: dict(z, position="") for r, z in (plain["bilanz"].get("konten_zuordnung") or {}).items() if isinstance(z, dict)}
    suggested = account_roles(ledger, plain)
    for a in ledger.accounts.values():           # Reihenfolge wie in MoneyMoney
        if not a.path:
            continue
        out.append({"uuid": a.uuid, "name": a.name, "pfad": a.path, "ebene": a.path.count(" / "), "gruppe": a.group,
                    "depot": a.portfolio, "manuell": ledger.writable(a.uuid, config), "rolle": roles.get(a.uuid, "") if not a.group else "",
                    "saldo": None if a.group else a.balance, "waehrung": a.currency, "typ": a.type, "inaktiv": a.uuid in inactive, "inaktiv_auto": a.uuid in inactive_auto, "aktiv_grenze": limits.get(a.uuid, 0),
                    "rolle_vorschlag": suggested.get(a.uuid, "") if not a.group else "", "abruf": kinds.get(a.uuid, {}).get("art") if not a.group else None,
                    "verlauf": verlauf.get(a.uuid) or ("stand" if a.portfolio else "umsaetze"), "bereich": bereich_of.get(a.uuid, ""),
                    "bereich_id": bereich_id.get(a.uuid, ""), "bestaetigt": a.uuid in confirmed,
                    "aktualisiert": a.refresh.strftime("%Y-%m-%d %H:%M") if a.refresh else None,
                    "letzte_buchung": last_tx[a.uuid].isoformat() if a.uuid in last_tx else None,
                    # Saldo, aber weder Buchung noch Aktualisierung seit N Monaten: Stand vermutlich veraltet (Konto aufgeloest?)
                    "veraltet": (not a.group and (a.portfolio or not a.offline) and abs(a.balance) > 0.005 and (a.uuid not in last_tx or last_tx[a.uuid] < cutoff)
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
        return {"status": "laeuft_bereits", "text": tr("s_ein_abgleich_laeuft_bereits")}
    try:
        state = store.load("state.json", {}) or {}
        bridge = bridge_factory(dry)
        t_start = time.time()
        prefetched = ledger is not None
        try:
            if not prefetched:
                step("lesen", 0, 0)
                ledger = fetch(bridge, config, today, with_portfolio=with_report, base=base, full=full)
            if categories is None and prefetched:
                categories = state.get("kategorien_roh") or []
            elif categories is None:
                try:
                    categories = mm_categories.with_paths(bridge.export_categories())
                except MoneyMoneyError:
                    categories = state.get("kategorien_roh") or []
        except MoneyMoneyError as e:
            txt = unavailable_text(e)
            if txt:
                log.info("MoneyMoney not available: %s", txt)
                return {"status": "nicht_verfuegbar", "text": txt}
            log.error("MoneyMoney error: %s", e)
            return {"status": "fehler", "text": tr("s_moneymoney_fehler_s") % e}
        # a new version builds the report again (new figures, e.g. after an update); the rules run again when their basis
        # changed: their settings (your "Don't book" among them) and the day (interest at month end, values)
        basis = json.dumps([[config.get(k) for k in ("darlehen", "gesellschaften", "bereiche", "abruf", "probelauf", "bilanz", "nicht_buchen")],
                            today.isoformat()], sort_keys=True, default=str)
        fp = "%s@%s#%s" % (ledger_fp(ledger), version(), hashlib.sha256(basis.encode()).hexdigest()[:16])
        if fp == state.get("fingerprint") and not force:
            log.info("No change in MoneyMoney since the last run.")
            return {"status": "unveraendert", "text": tr("s_keine_aenderung_in_moneymoney_seit"), "_ledger": ledger,
                    "_kategorien": categories}

        # when Kontor first saw each account: one new in MoneyMoney shows at once (before its first transaction); the first
        # time all known accounts count as long known
        seen_before = state.get("konten_seit")
        known = dict(seen_before) if isinstance(seen_before, dict) else {}
        for u, a in ledger.accounts.items():
            if not a.group and u not in known:
                known[u] = today.isoformat() if isinstance(seen_before, dict) else "alt"      # "alt": known before
        known_new = {u: v for u, v in known.items() if u not in (seen_before or {})}
        state["konten_seit"] = known                # for the report of this run
        step("regeln", 0, 0)
        # up to where Kontor had looked when it last booked on its own: what arose after that is new (Seen)
        seen = rules.Seen.from_state(state.get("gesehen"), ledger, today)
        new_seen = None if isinstance(state.get("gesehen"), dict) and state["gesehen"].get("tag") else seen.dump()
        top = rules.Seen.top_id(ledger)
        t_read = time.time()
        approving = not dry and approve is not None
        automatic = not dry and approve is None
        edits = {k: v for k, v in approve.items() if isinstance(v, dict)} if approving else None
        hold: set = set()

        def wanted(p: Proposal) -> bool:
            """Booked in this run: what you approved; booking fully automatically what is new since the last check -- what is
            backdated or missing again (deleted in MoneyMoney) waits for you, and a loan's interest after it too."""
            return p.key in approve if approving else not p.retro
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
                    shown = ch.get("angezeigt") if isinstance(ch, dict) else None
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
                ums = build_report(store, ledger, config, state, today, warnings, categories).pop("_umsaetze", None)
        if with_report:
            state["kategorien_roh"] = categories or []
        log.info("Run times: read %.1f s (%s), rules %.1f s, write %.1f s, report %.1f s", t_read - t_start,
                 "quick" if getattr(ledger, "incremental", False) else "full", t_rules - t_read, t_write - t_rules, time.time() - t_write)

        # shown: what waits for approval, otherwise what was just booked
        summary = {"status": "fehler" if err else "ok", "zeit": datetime.now().strftime("%Y-%m-%d %H:%M"), "probelauf": dry or bool(waiting) or bool(moved),
                   "vorschlaege": proposal_rows(ledger, waiting or bookings),
                   "geschrieben": written, "gebucht": len(made), "warnungen": result.warnings, "hinweise": result.info,
                   "fehler": str(err) if err else None}

        def _merge(cur: dict) -> None:
            for k in OLD_STATE_KEYS:                # Kontor's own booking lists until 3.13.0 (migrate_booking_state)
                cur.pop(k, None)
            if known_new:
                cur["konten_seit"] = dict(known_new, **(cur.get("konten_seit") or {}))
            if new_seen:
                cur["gesehen"] = new_seen
            if not prefetched:
                cur["fingerprint"] = fp if err is None and not failed else None        # after an error: again at the next sync
            cur["letzter_lauf"] = summary
            if not prefetched:                  # "Refresh" (only the accounts of the rules) is no check of its own
                cur.setdefault("verlauf", []).append({"zeit": summary["zeit"], "probelauf": dry, "geschrieben": written,
                                                      "vorschlaege": len(bookings), "fehler": summary["fehler"]})
            cur["verlauf"] = [{k: v for k, v in x.items() if k != "buchungen"} for x in (cur.get("verlauf") or [])[-100:]]     # at most 100
            if state.get("snapshots"):
                merge_snapshots(cur, state["snapshots"])     # Schnellabgleich waehrend des Laufs bleibt erhalten
            merge_holdings(cur, state)
            if state.get("kategorien_roh"):
                cur["kategorien_roh"] = state["kategorien_roh"]
        store.update("state.json", _merge, {})      # Verlauf-Eingaben waehrend des Laufs bleiben erhalten

        return dict(summary, _ledger=ledger, _kategorien=categories, _umsaetze=ums, _gebucht=[p.key for p in made])
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
    for b in cfg.get("bereiche") or []:
        if isinstance(b, dict):
            b["konten"] = [fn("bereiche.konten", x) for x in (b.get("konten") or [])]
    bil = cfg.setdefault("bilanz", {})
    bil["illiquide_konten"] = [fn("bilanz.illiquide_konten", x) for x in (bil.get("illiquide_konten") or [])]
    for key in ("ausgeblendet", "immer_anzeigen"):
        if bil.get(key):
            bil[key] = [fn("bilanz." + key, x) for x in bil[key]]
    for key in ("rollen", "verlauf", "konten_zuordnung"):
        if bil.get(key):
            bil[key] = {(fn("bilanz." + key, k) if not k.startswith("_") else k): v for k, v in bil[key].items()}
    for im in cfg.get("immobilien") or []:
        if im.get("objekt_konto"):
            im["objekt_konto"] = fn("immobilien.objekt_konto", im["objekt_konto"])
        if im.get("darlehen_konten"):
            im["darlehen_konten"] = {k: (fn("immobilien.darlehen_konten", v) if v else v) for k, v in im["darlehen_konten"].items()}
    for g in cfg.get("gesellschaften") or []:
        for x in (g.get("gegenkonten") or []) if isinstance(g, dict) else []:
            for f in ("konto", "quelle"):
                if isinstance(x, dict) and x.get(f):
                    x[f] = fn("gesellschaften.gegenkonten." + f, x[f])
    kf = cfg.setdefault("kapitalfluss", {})
    if kf.get("kategorie_zu_konto"):
        kf["kategorie_zu_konto"] = {k: (fn("kapitalfluss.kategorie_zu_konto", v) if not k.startswith("_") else v)
                                    for k, v in kf["kategorie_zu_konto"].items()}
    st = cfg.setdefault("steuer", {})
    if st.get("objekt_darlehen"):
        st["objekt_darlehen"] = {(fn("steuer.objekt_darlehen", k) if not k.startswith("_") else k): v for k, v in st["objekt_darlehen"].items()}
    ents = []
    for e in st.get("entitaeten") or []:
        if isinstance(e, dict):
            e = dict(e); e["gruppe"] = fn("steuer.entitaeten", e.get("gruppe", "")); ents.append(e)
        else:
            ents.append(fn("steuer.entitaeten", e))
    st["entitaeten"] = ents


def export_package(config: dict, name: str = "Kontor-Einstellungen", strip_uuids: bool = False,
                   plan: Optional[dict] = None, ledger: Optional[Ledger] = None) -> dict:
    """Einstellungen als weitergebbares Paket. strip_uuids: Kontoreferenzen als Pfad (wenn ein Ledger
    vorliegt) bzw. Name statt UUID -- fuer eine andere MoneyMoney-Installation."""
    cfg = copy.deepcopy(merged_config(config))
    cfg.pop("oberflaeche", None)
    cfg.pop("updates", None)
    cfg.pop("nicht_buchen", None)                 # decisions about bookings in your MoneyMoney: they stay here
    (cfg.get("belege") or {}).pop("ordner", None)
    ids = {str(b.get("id")) for b in cfg.get("bereiche") or [] if isinstance(b, dict)}
    if ids:                                   # rules of companies whose area no longer exists do not travel along
        cfg["gesellschaften"] = [g for g in cfg.get("gesellschaften") or [] if isinstance(g, dict) and str(g.get("bereich")) in ids]
    if strip_uuids:
        def strip(field: str, r: str) -> str:
            if "|" not in r:
                return r
            uuid, label = (x.strip() for x in r.split("|", 1))
            if ledger is not None and uuid in ledger.accounts:
                return ledger.accounts[uuid].path
            return label
        _walk_refs(cfg, strip)
    pkg = {"kontor_paket": 1, "name": name, "version": version(), "erstellt": datetime.now().strftime("%Y-%m-%d"), "config": cfg}
    if plan:
        pkg["plan"] = plan
    return pkg


def import_package(current: dict, pkg: dict, ledger: Optional[Ledger], mode: str = "ergaenzen",
                   mapping: Optional[Dict[str, str]] = None) -> Tuple[dict, List[dict], List[str]]:
    """Paket in die Konfiguration uebernehmen. Liefert (config, unaufgeloeste Referenzen, Bericht)."""
    if not isinstance(pkg, dict) or not isinstance(pkg.get("config"), dict):
        raise ValueError(tr("s_keine_einstellungsdatei"))
    inc = copy.deepcopy(pkg["config"])
    for k in ("oberflaeche", "updates", "nicht_buchen"):
        inc.pop(k, None)
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
                unresolved.append({"ref": ref, "label": label, "feld": field})
            return ref

    _walk_refs(inc, resolve)
    base = copy.deepcopy(merged_config(current))
    if mode == "ersetzen":
        for k, v in inc.items():
            base[k] = v
            report.append("%s ersetzt" % k)
    else:
        for k, v in inc.items():
            if k in ("darlehen", "gesellschaften", "bereiche", "immobilien"):
                key = {"bereiche": "id", "immobilien": "id", "gesellschaften": "bereich"}.get(k, "name")
                existing = {x.get(key): i for i, x in enumerate(base.get(k) or []) if isinstance(x, dict)}
                base.setdefault(k, [])
                for item in v or []:
                    if not isinstance(item, dict):
                        continue
                    if k == "bereiche" and item.get("haupt"):
                        for x in base[k]:
                            if isinstance(x, dict):
                                x["haupt"] = False
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
                    elif isinstance(vv, list) and kk in ("illiquide_konten", "bereiche", "umbuchungs_kategorien", "entitaeten"):
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
    cfg.pop("oberflaeche", None)
    cfg["nicht_buchen"] = len(cfg.get("nicht_buchen") or [])        # only how many (amounts and texts stay out)
    names: Dict[str, str] = {}
    if mask_names:
        ds = store.load("dataset.json", {}) or {}
        for i, k in enumerate(ds.get("konten") or []):
            names[k["name"]] = "Konto%02d" % i
        for i, k in enumerate((ds.get("bereich_namen") or {}).values()):
            names[k] = "Bereich%d" % i
        for l in cfg.get("darlehen") or []:
            if (l.get("erkennung") or {}).get("gegen_iban"):
                l["erkennung"]["gegen_iban"] = tr("s_iban")
    _walk_refs(cfg, lambda f, r: ((r.split("|", 1)[0].strip()[:8] + " | " + mask_text(r.split("|", 1)[1].strip(), names))
                                  if "|" in r else mask_text(r, names)))
    state = store.load("state.json", {}) or {}
    st = copy.deepcopy(status)
    for k in ("letztes_ergebnis", "letzter_lauf"):
        if isinstance(st.get(k), dict):
            st[k] = {kk: vv for kk, vv in st[k].items() if kk != "vorschlaege"}
    home = os.path.expanduser("~")

    def m(text: str) -> str:
        text = mask_text(text, names)
        return text.replace(home, "~") if home and home != "/" else text

    out = ["Kontor-Diagnose %s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
           "Version %s, Python %s, %s %s" % (version(), platform.python_version(), platform.system(), platform.release()),
           "Status: " + m(json.dumps(st, ensure_ascii=False, default=str)),
           "Konfiguration (Namen %s): %s" % ("maskiert" if mask_names else tr("s_im_klartext"), m(json.dumps(cfg, ensure_ascii=False, indent=1))),
           tr("s_letzter_lauf") + m(json.dumps(state.get("letzter_lauf"), ensure_ascii=False, default=str)),
           "Verlauf: " + m(json.dumps((state.get("verlauf") or [])[-10:], ensure_ascii=False, default=str)),
           "--- Protokoll (letzte %d Zeilen) ---" % lines]
    try:
        with open(os.path.join(data_dir, "kontor.log"), encoding="utf-8", errors="replace") as f:
            out += [m(l.rstrip("\n")) for l in f.readlines()[-lines:]]
    except FileNotFoundError:
        out.append(tr("s_kein_protokoll"))
    return "\n".join(out)
