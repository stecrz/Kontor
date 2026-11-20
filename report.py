"""Bilanz, Kapitalflussrechnung und Planung je Bereich aus MoneyMoney-Daten.

Ein Bereich ist eine Menge von Konten (meist eine Kontengruppe der obersten Ebene, kann aber
beliebig zusammengestellt sein). Die Bilanz ist von der Gruppierung in MoneyMoney unabhaengig:
jedes Konto bekommt eine Position (Rolle) -- Liquiditaet, Wertpapiere, Geldanlagen, Immobilien,
Beteiligungen, Sachwerte, Forderungen, Sonstiges, Verbindlichkeiten -- aus Konfiguration,
Gruppennamen oder Kontotyp.

Saldoverlauf je Konto ("verlauf"):
  umsaetze  aus dem aktuellen Saldo rueckwaerts ueber die Umsaetze (Startsalden spielen keine Rolle)
  stand     Monatsend-Staende: von Kontor aufgezeichnet (ab dem ersten Lauf), von Hand eingetragen
            oder aus einem Saldenexport importiert -- fuer Depots und alles ohne Umsatzhistorie
Vor dem ersten bekannten Stand wird der erste bekannte Wert fortgeschrieben (Hinweis).

Kapitalfluss:
  Einnahmen / Ausgaben        je MoneyMoney-Kategorie, hierarchisch (Oberkategorie = Gruppe)
  Investitionen               Umschichtungen in Wertpapiere/Anlagen/Immobilien/Sachwerte, Einlagen in
                              Beteiligungen, Forderungen (Rueckzahlung / Zinsen)
  Finanzierung                je Darlehen: Tilgung (= Zahlung - Zinsen) und Zinsen
  Bewertung                   nicht zahlungswirksam: Wertaenderungen, manuelle Buchungen
  Unklar                      Umbuchungen ohne erkennbaren Partner, Konten ohne Position
Jede Zeile traegt nw=true, wenn sie das Nettovermoegen veraendert.

Planung (apply_plan): Planwerte je Zeile, Ereignisse (einmalig/wiederkehrend), Darlehensplan,
Immobilienkalkulationen (Monatsreihen), Fortschreibung je Konto und Position, Kennzahlen.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from categorize import party_key, suggest as suggest_category
from model import Account, Ledger, Tx, add_months, month_end, month_key, months_between, norm_cat, legacy_cat
from model import MARK, marks_in
from i18n import tr

ROLES = ["cash", "securities", "term_investments", "real_estate", "participations", "tangibles", "receivables", "other", "liabilities",
         "contingent", "ignore"]
ROLE_KEYS = {"cash": "pos_bankguthaben", "securities": "pos_wertpapiere", "term_investments": "pos_gebundene_anlagen", "real_estate": "immobilien",
             "participations": "beteiligungen", "tangibles": "sachwerte", "receivables": "pos_forderungen", "other": "sonstiges",
             "liabilities": "pos_verbindlichkeiten", "contingent": "role_eventual",
             "ignore": "nicht_bilanzieren"}       # Schluessel in web/i18n.js


def role_label(role: str) -> str:
    """Name einer Bilanzposition in der eingestellten Sprache."""
    return tr(ROLE_KEYS[role]) if role in ROLE_KEYS else role


OFF_BALANCE = {"contingent", "ignore"}      # nicht im Nettovermoegen
ASSET_ROLES = {"securities", "term_investments", "real_estate", "participations", "tangibles"}
ILLIQUID_DEFAULT = ["term_investments", "participations", "real_estate", "tangibles", "receivables", "other"]
# Hinweise aus Konto- und Gruppennamen (Reihenfolge = Vorrang; Wortgrenzen, damit z. B. "Haushalt" nicht als Haus gilt).
# "+/-": Darlehen, Kredite, Kautionen -> Guthaben = Forderung, negativer Saldo = Verbindlichkeit
# "kapital": Kapital-/Gesellschafterkonten und Gesellschafterdarlehen -> Guthaben = Beteiligung (Risikokapital: traegt Verluste mit,
# fliesst erst beim Ausscheiden zurueck), negativer Saldo = Verbindlichkeit (in der Gesellschaft: Schuld an den Gesellschafter)
NAME_HINTS = [
    (r"off.?balance|nicht bilanz", "ignore"),
    (r"aval|b(ü|ue)rgschaft|garantie", "contingent"),
    # Kapital-/Gesellschafterkonten wie Gesellschafterdarlehen: in der Gesellschaft Schuld an den Gesellschafter, privat Forderung;
    # das Nettovermoegen der Gesellschaft ist dann der Rest, der nach Anteil verteilt wird (stimmt auch bei ungleichen Einlagen)
    (r"eigenkapital|kapitalkont|gesellschafterkont|gesellschafterdarlehen", "capital_amount"),
    (r"kaution", "+/-"),
    (r"\bp2p|peer.to.peer", "term_investments"),      # P2P loans are an investment, not a loan to manage (before "kredit")
    (r"darlehen|kredit(?!karte)|hypothek|finanzierung|\bschulden", "+/-"),
    (r"bauspar|lebensversicherung|rentenversicherung|\bversicherung|riester|r(ü|ue)rup|fondspolice", "term_investments"),
    (r"immobil|wohnung|\bhaus\b|eigenheim|grundst(ü|ue)ck|\bobjekt", "real_estate"),
    (r"beteilig|\bgesellschafteranteil|\banteil an\b", "participations"),
    (r"forderung|verliehen", "receivables"),
    (r"verbindlich", "liabilities"),
    (r"fahrzeug|\bauto\b|\bpkw\b|\bmotorrad|\buhren?\b|sachwert|schmuck|\bkunst|\bgold\b", "tangibles"),
    (r"depot|wertpapier|\betf|aktien|\bfonds|krypto|bitcoin", "securities"),
    (r"festgeld|sparbrief|\banlage", "term_investments"),
    (r"liquid|\bcash|\bgiro|tagesgeld|\bkasse\b|bargeld", "cash"),
]
_NAME_HINTS_RE = [(re.compile(rx, re.I), role) for rx, role in NAME_HINTS]
STRONG_TYPES = {"portfolio": "securities", "depot": "securities", "girokonto": "cash", "kreditkarte": "cash", "bargeld": "cash", "cash": "cash",
                "darlehenskonto": "+/-", "loan": "+/-", "bauspar": "term_investments"}
WEAK_TYPES = {"tagesgeld": "cash", "sparkonto": "cash", "festgeld": "term_investments"}
NO_NEGATIVE_TYPES = ("sparkonto", "tagesgeld", "festgeld", "bauspar")
TX_MARK = MARK + "tx-"              # a loan repayment mirrored from a payment: the mark names the payment
COST_WORDS = ["zins", "interest", "gebühr", "gebuehr", "entgelt", "provision", "bereitstellung", "#kontor-zins", "#mm-zins"]
SECTIONS = ["income", "expenses", "investing", "financing", "valuation", "unclear"]
CASH_SECTIONS = ["income", "expenses", "investing", "financing", "unclear"]


# ---------------------------------------------------------------------------
# Positionen (Rollen)
# ---------------------------------------------------------------------------

def _hint_role(name: str) -> Optional[str]:
    for rx, role in _NAME_HINTS_RE:
        if rx.search(name or ""):
            return role
    return None


def _signed(role: Optional[str], acc: Account, in_company: Optional[bool] = False) -> Optional[str]:
    """"+/-": Guthaben -> Forderung, Schuld -> Verbindlichkeit; "kapital" (a capital account): in a company its debt to the
    partner (only a credit balance there is a participation); outside the companies it is your participation -- whatever its
    balance or its type in MoneyMoney (often "Darlehenskonto"), also before its first booking. in_company None: no company
    set up yet, so nobody knows -- then a debt is a debt."""
    if role == "capital_amount":
        if in_company or (in_company is None and acc.balance < -0.005):
            return "participations" if acc.balance > 0.005 else "liabilities"
        return "participations"
    if role != "+/-":
        return role
    return "receivables" if acc.balance > 0.005 else "liabilities"


def account_roles(ledger: Ledger, config: dict) -> Dict[str, str]:
    """uuid -> Position fuer ALLE Konten. Vorrang: eigene Zuordnung > Depot > Kontoname > eindeutiger Kontotyp
    (Giro, Kreditkarte, Darlehen) > Name der naechsten Gruppe > allgemeiner Kontotyp (Spar-, Tagesgeld, Festgeld) > Sonstiges."""
    cfg_roles: Dict[str, str] = {}
    for ref, role in (config.get("balance", {}).get("roles") or {}).items():
        if ref.startswith("_"):
            continue
        try:
            cfg_roles[ledger.resolve(ref).uuid] = role
        except KeyError:
            pass
    for ref, z in (config.get("balance", {}).get("accounts_mapping") or {}).items():
        if isinstance(z, dict) and z.get("position") in ROLES:
            try:
                cfg_roles[ledger.resolve(ref).uuid] = z["position"]
            except KeyError:
                pass
    roles: Dict[str, str] = {}
    company: set = set()                # accounts in areas of the kind "Gesellschaft"
    for b in config.get("areas") or []:
        if isinstance(b, dict) and b.get("kind") == "company":
            for ref in b.get("accounts") or []:
                try:
                    a = ledger.resolve(ref)
                except KeyError:
                    continue
                company.update(x.uuid for x in (ledger.descendants(a.uuid) if a.group else [a]))

    def walk(acc: Account, group_hint: Optional[str]):
        if acc.group:
            here = cfg_roles.get(acc.uuid) or _hint_role(acc.name) or group_hint
        else:
            t = (acc.type or "").lower()
            role = cfg_roles.get(acc.uuid)
            if not role and acc.portfolio:
                role = "securities"
            inside = (acc.uuid in company) if company else None
            if not role:
                role = _signed(_hint_role(acc.name), acc, inside)
            if not role:
                role = _signed(next((r for k, r in STRONG_TYPES.items() if k in t), None), acc, inside)
            if not role and group_hint:
                role = _signed(group_hint, acc, inside)
            if not role:
                role = next((r for k, r in WEAK_TYPES.items() if k in t), None)
            roles[acc.uuid] = role or "other"
            here = group_hint
        for c in acc.children:
            walk(ledger.accounts[c], here)

    for root in ledger.roots():
        walk(root, None)
    return roles


# ---------------------------------------------------------------------------
# Saldoverlauf
# ---------------------------------------------------------------------------

def verlauf_quelle(acc: Account, verlauf_cfg: Dict[str, str]) -> str:
    v = verlauf_cfg.get(acc.uuid)
    if v in ("transactions", "balances"):
        return v
    return "balances" if acc.portfolio else "transactions"


def _valuation_account(acc: Account, src: str) -> bool:
    """Depot mit Verlauf aus Kontostaenden: Wertaenderung ist Bewertung, keine Zahlungsfluesse."""
    return src == "balances" and acc.portfolio


def holding_key(name: str, isin: str) -> str:
    """Identity of a security across MoneyMoney's export and its database: the ISIN, otherwise the name."""
    return (isin or "").strip().upper() or "n:" + " ".join((name or "").lower().split())


def depot_holdings(acc: Account, werte: Dict[str, Optional[float]], mkeys: List[str], today: date, state: dict,
                   live: Optional[list], config: Optional[dict] = None) -> List[dict]:
    """The securities of a portfolio, month by month: past months from MoneyMoney's history (or Kontor's own monthly record),
    the current month from MoneyMoney's export. A remainder row takes what the securities do not explain (e.g. cash that
    MoneyMoney does not list as a position), so that the rows always add up to the portfolio value. No estimates: a month
    without any known security stays empty."""
    cur = month_key(today)
    rows: Dict[str, dict] = {}

    def row(name: str, isin: str, fallback: str = "") -> dict:
        key = holding_key(name, isin) if (name or isin) else fallback or holding_key(name, isin)    # unnamed: kept apart
        r = rows.setdefault(key, {"id": acc.uuid + "|" + key, "name": name, "isin": isin, "amounts": {}})
        if name and not r["name"]:
            r["name"] = name
        return r
    for n, w in enumerate((state.get("history_mm_sec") or {}).get(acc.uuid) or []):
        r = row(str(w.get("name") or ""), str(w.get("isin") or ""), "mm:%d" % n)
        for mk, v in (w.get("amounts") or {}).items():
            if mk < cur and v is not None:
                r["amounts"][mk] = round(r["amounts"].get(mk, 0.0) + float(v), 2)
    names = state.get("sec_names") or {}
    covered = {mk for r in rows.values() for mk in r["amounts"]}
    for mk, per in (state.get("snapshots_sec") or {}).items():
        if mk >= cur or mk in covered or acc.uuid not in per:
            continue
        for key, v in per[acc.uuid].items():
            r = rows.setdefault(key, {"id": acc.uuid + "|" + key, "name": names.get(key, ""), "isin": key if not key.startswith("n:") else "", "amounts": {}})
            r["amounts"][mk] = float(v)
    for p in live or []:
        try:
            r = row(str(p.get("name") or ""), str(p.get("isin") or ""))
            r["amounts"][cur] = round(r["amounts"].get(cur, 0.0) + float(p.get("marketValue") or p.get("amount") or 0), 2)
        except (TypeError, ValueError, AttributeError):
            continue
    found, own = (state.get("sec_search") or {}).get("names") or {}, (state.get("sec_search") or {}).get("own") or {}
    for key, r in rows.items():
        # MoneyMoney's own name (history or export) stays as "orig" and is always shown on hover, together with the ISIN; the name
        # shown: one changed in the setup (list of names), else MoneyMoney's, else the one looked up by the ISIN, else the ISIN
        isin = (r.get("isin") or "").upper()
        r["orig"] = r["name"] or names.get(key, "")
        look = str(found.get(isin) or "") if not r["orig"] else ""
        mine = str(own.get(isin) or "") if isin else ""
        r["name"], r["source"] = mine or r["orig"] or look, "own_name" if mine else "lookup" if look else ""
    out = [r for r in rows.values() if any(abs(v) >= 0.005 for v in r["amounts"].values())]
    if not out:
        return []
    for i, r in enumerate(out, 1):
        r["name"] = r["name"] or r.get("isin") or tr("s_wertpapier_n") % i       # without a name: the ISIN
        r["amounts"] = {mk: r["amounts"].get(mk) for mk in mkeys}
    rest = {}
    for mk in mkeys:
        known = [r["amounts"][mk] for r in out if r["amounts"][mk] is not None]
        rest[mk] = round((werte.get(mk) or 0.0) - sum(known), 2) if known and werte.get(mk) is not None else None
    if any(v is not None and abs(v) >= 0.5 for v in rest.values()):
        out.append({"id": acc.uuid + "|rest", "name": tr("s_wp_rest"), "isin": "", "rest": True, "amounts": rest})
    out.sort(key=lambda r: (bool(r.get("rest")), -abs(next((r["amounts"][mk] for mk in reversed(mkeys) if r["amounts"].get(mk) is not None), 0.0))))
    return out


def account_balance_series(ledger: Ledger, acc: Account, months: List[Tuple[int, int]], src: str, snapshots: Dict[str, Dict[str, float]],
                           manual_raw: Dict[str, Any], today: date, config: Optional[dict] = None, mm_raw: Optional[Dict[str, Any]] = None,
                           mm_start: Optional[float] = None):
    """Monatsend-Salden eines Kontos. Liefert (werte, hinweis, anker).

    umsaetze: heutiger Saldo minus alle spaeteren Buchungen (eigene Monatswerte zaehlen nicht).
    stand:    bekannte Kontostaende (eigene/importierte Werte, aus MoneyMoney uebernommene, bei Depots auch die von Kontor
              aufgezeichneten, dazu der heutige Saldo) sind massgeblich. Konten mit Buchungen: von jedem bekannten Stand aus
              rueckwaerts mit den Buchungen weitergerechnet. Depots: letzter bekannter Stand; vor dem ersten bekannten Stand der
              Stand vor MoneyMoneys erster Aufzeichnung (mm_start, meist 0), sonst (gekennzeichnet) der erste bekannte Wert --
              keine Schaetzung."""
    cur_key = month_key(today)
    mkeys = ["%04d-%02d" % ym for ym in months]
    past = [(y, m) for (y, m) in months if "%04d-%02d" % (y, m) < cur_key]
    h: Dict[str, Optional[float]] = {}
    hinweis = None
    manual = {k: float(v) for k, v in (manual_raw or {}).items() if v is not None}
    # Aus MoneyMoney uebernommene Monatsstaende: zaehlen wie eigene Werte, eigene Eintraege gehen aber vor
    for k, v in (mm_raw or {}).items():
        if v is not None and k < month_key(today) and k not in manual:
            manual[k] = float(v)
    if src != "balances":
        ends = ledger.month_end_balances(acc.uuid, past)
        # Alle Umsaetze bekannt (kein Zeitfenster): vor dem ersten Umsatz gab es das Konto nicht -- kein Stand (wie in MoneyMoney),
        # statt den Startsaldo endlos zurueckzuschreiben
        full = int(((config or {}).get("balance") or {}).get("months_back", 0) or 0) <= 0
        first = min((t.booking_date for t in ledger.transactions(acc.uuid)), default=None) if full else None
        opened = month_key(first) if first else None
        # Opened before its first booking with nothing on it: from MoneyMoney's first balance (or one of yours) on it stands at 0
        # -- only if the account started at 0 and every known balance before the first booking says 0 (no estimate; an opening
        # balance of its own keeps its row "Anfangssaldo" in the month of the first booking)
        if opened:
            before = {k: v for k, v in manual.items() if k < opened}
            if before and abs(round(acc.balance - sum(t.amount for t in ledger.transactions(acc.uuid)), 2)) < 0.005 \
                    and all(abs(v) < 0.005 for v in before.values()):
                opened = min(before)
        for k in mkeys:
            h[k] = acc.balance if k >= cur_key else (None if opened and k < opened else ends[k])
        t = (acc.type or "").lower()
        if any(x in t for x in NO_NEGATIVE_TYPES):
            neg = [k for k in mkeys if (h[k] or 0) < -1.0]
            if neg:
                hinweis = (tr("s_s_die_rueckrechnung_aus_den")
                           % (acc.name, neg[0], neg[-1]))
        return h, hinweis, [cur_key]
    if not acc.portfolio:
        # Anker: eigene Werte + heutiger Saldo; dazwischen mit den Buchungen gerechnet (Saldo = Anker - Buchungen danach)
        anchors = {k: v for k, v in manual.items() if k < cur_key}
        anchors[cur_key] = acc.balance
        ends = ledger.month_end_balances(acc.uuid, sorted(set(past) | {(int(k[:4]), int(k[5:7])) for k in anchors if k < cur_key}))
        ends[cur_key] = acc.balance
        akeys = sorted(anchors)
        for k in mkeys:
            if k >= cur_key:
                h[k] = acc.balance
                continue
            a = next(x for x in akeys if x >= k)          # fruehester bekannter Stand ab diesem Monat
            h[k] = round(ends[k] + (anchors[a] - ends[a]), 2)
        return h, None, akeys
    known = dict(manual)
    for k, v in snapshots.items():
        if acc.uuid in v and k not in known:
            known[k] = v[acc.uuid]
    known[cur_key] = acc.balance
    first_known = min(known)
    mm_keys = [k for k, v in (mm_raw or {}).items() if v is not None]
    before = mm_start if mm_start is not None and mm_keys and first_known >= min(mm_keys) else None   # Stand vor der Aufzeichnung
    # Keine Schaetzung: vor dem ersten bekannten Stand steht (gekennzeichnet) dieser erste Wert
    for k in mkeys:
        if k == cur_key:
            h[k] = acc.balance
        elif k in known:
            h[k] = known[k]
        elif k < first_known:
            h[k] = known[first_known] if before is None else before
        else:
            prev = max((kk for kk in known if kk < k), default=first_known)
            h[k] = known[prev]
    if before is None and mkeys and mkeys[0] < first_known and abs(known[first_known]) > 0.005:
        hinweis = (tr("s_s_kontostaende_vor_s_sind") % (acc.name, first_known))
    return h, hinweis, sorted(known)


def balance_history(ledger: Ledger, leaves: List[Account], months: List[Tuple[int, int]], snapshots: Dict[str, Dict[str, float]],
                    historie: Dict[str, Dict[str, float]], verlauf_cfg: Dict[str, str], today: date, config: Optional[dict] = None,
                    historie_mm: Optional[Dict[str, Dict[str, float]]] = None, historie_mm_anfang: Optional[Dict[str, float]] = None):
    """uuid -> {JJJJ-MM: Saldo am Monatsende}. Liefert zusaetzlich Hinweise, die Quelle je Konto und je Depot den Monat,
    vor dem kein Stand bekannt ist (dort steht -- gekennzeichnet -- der erste bekannte Wert)."""
    warnings: List[str] = []
    hist: Dict[str, Dict[str, Optional[float]]] = {}
    quelle: Dict[str, str] = {}
    fortgeschrieben: Dict[str, str] = {}
    first_mk = "%04d-%02d" % months[0] if months else None
    for acc in leaves:
        src = verlauf_quelle(acc, verlauf_cfg)
        quelle[acc.uuid] = src
        h, hinweis, anker = account_balance_series(ledger, acc, months, src, snapshots, historie.get(acc.uuid) or {}, today, config,
                                                       (historie_mm or {}).get(acc.uuid), (historie_mm_anfang or {}).get(acc.uuid))
        hist[acc.uuid] = h
        if hinweis:
            warnings.append(hinweis)
        if src == "balances" and acc.portfolio and anker and first_mk and first_mk < anker[0] and abs(acc.balance) > 0.005 \
                and (historie_mm_anfang or {}).get(acc.uuid) is None:
            fortgeschrieben[acc.uuid] = anker[0]       # vor diesem Monat kein Stand bekannt: erster Wert rueckwaerts uebernommen
    return hist, warnings, quelle, fortgeschrieben


def account_months(ledger: Ledger, acc: Account, today: date, extra_keys=()) -> List[Tuple[int, int]]:
    """Monate fuer die Verlaufsansicht eines Kontos: ab der ersten Buchung bzw. dem ersten bekannten Wert, mindestens 12."""
    first = min((t.booking_date for t in ledger.transactions(acc.uuid)), default=today)
    fk = min(extra_keys, default=None)
    y, m = first.year, first.month
    if fk and fk < "%04d-%02d" % (y, m):
        y, m = int(fk[:4]), int(fk[5:7])
    ly, lm = add_months(today, -11)
    if (y, m) > (ly, lm):
        y, m = ly, lm
    out = []
    while (y, m) <= (today.year, today.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _seen_month(seen: Optional[Dict[str, str]], uuid: str) -> Optional[int]:
    """The month Kontor first saw an account (year * 12 + month), None: unknown or long known."""
    v = (seen or {}).get(uuid) or ""
    try:
        return int(v[:4]) * 12 + int(v[5:7])
    except ValueError:
        return None


def inactive_accounts(ledger: Ledger, leaves: List[Account], hist: Dict[str, Dict[str, Optional[float]]], mkeys: List[str],
                      config: dict, today: date, seen: Optional[Dict[str, str]] = None) -> Tuple[Set[str], Set[str]]:
    """(ausgeblendet, inaktiv nach Aktivitaet). Inaktiv = ohne Bestand und ohne Umsatz in den letzten N Monaten (Altdaten).
    Ausgeblendet = je Konto "ausblenden", oder "nach Aktivitaet" und inaktiv; "immer anzeigen" nie. Ausgeblendete Konten
    bleiben in allen Summen enthalten. seen: uuid -> day Kontor first saw the account -- one new in MoneyMoney is shown at once,
    before its first transaction."""
    bcfg = config.get("balance", {}) or {}
    n = int(bcfg.get("inactive_months", 12) or 0)
    force_hide: Set[str] = set()
    force_show: Set[str] = set()
    for ref in bcfg.get("hidden_accounts") or []:
        try:
            force_hide.add(ledger.resolve(ref).uuid)
        except KeyError:
            pass
    for ref in bcfg.get("always_show") or []:
        try:
            force_show.add(ledger.resolve(ref).uuid)
        except KeyError:
            pass
    y, m = add_months(today, -n)
    cutoff = date(y, m, 1)
    recent = mkeys[-n:] if n else []
    auto: Set[str] = set()
    if n:
        for acc in leaves:
            h = hist.get(acc.uuid, {})
            first = _seen_month(seen, acc.uuid)
            if all(abs(h.get(k) or 0.0) < 0.005 for k in recent) and abs(acc.balance) < 0.005 \
                    and not any(t.booking_date >= cutoff for t in ledger.transactions(acc.uuid)) \
                    and not (first is not None and first >= cutoff.year * 12 + cutoff.month):
                auto.add(acc.uuid)
    hidden = {u for u in auto if u not in force_show} | {a.uuid for a in leaves if a.uuid in force_hide}
    return hidden, auto


def activity_limits(ledger: Ledger, leaves: List[Account], hist: Dict[str, Dict[str, Optional[float]]], mkeys: List[str],
                    today: date, seen: Optional[Dict[str, str]] = None) -> Dict[str, int]:
    """uuid -> groesstes N, bei dem das Konto unter "nach Aktivitaet" noch ausgeblendet waere (wie inactive_accounts):
    ausgeblendet genau dann, wenn 0 < N <= Grenze. 0 = nie (Saldo), 9999 = immer (nie Bestand oder Umsatz)."""
    now = today.year * 12 + today.month
    out: Dict[str, int] = {}
    for acc in leaves:
        if abs(acc.balance) >= 0.005:
            out[acc.uuid] = 0
            continue
        h = hist.get(acc.uuid, {})
        last_h = next((k for k in reversed(mkeys) if abs(h.get(k) or 0.0) >= 0.005), None)
        since_h = now - (int(last_h[:4]) * 12 + int(last_h[5:7])) if last_h else 9999
        last_t = max((t.booking_date for t in ledger.transactions(acc.uuid)), default=None)
        since_t = now - (last_t.year * 12 + last_t.month) if last_t else 10000
        first = _seen_month(seen, acc.uuid)
        since_seen = now - first if first is not None else 10000
        out[acc.uuid] = max(0, min(since_h, since_t - 1, since_seen - 1, 9999))
    return out


# ---------------------------------------------------------------------------
# Kapitalfluss
# ---------------------------------------------------------------------------

def _is_cost(t: Tx, cost_words: List[str]) -> bool:
    low = t.text.lower()
    return any(w in low for w in cost_words)


class Rows:
    """Sammelt Zeilen: (Sektion, Zeile) -> Monatswerte + Metadaten."""

    def __init__(self):
        self.vals: Dict[Tuple[str, str], Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.meta: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.det: Dict[Tuple[str, str], Dict[str, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        self.ids: Dict[Tuple[str, str], Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))   # each row: its bookings
        self.cur: Optional[int] = None                     # the booking being placed (rows added meanwhile hold it)

    def add(self, section: str, group: Optional[str] = None, row: str = "", mk: str = "", amount: float = 0.0, *,
            account: Optional[str] = None, kind: str = "category", nw: bool = True, lbl: Optional[tuple] = None,
            glbl: Optional[tuple] = None, ord: Optional[float] = None, property_name: Optional[str] = None, detail: Optional[str] = None,
            tx: Optional[int] = None):
        """row/group are the keys of your planning (names of categories, accounts and fixed rows); lbl/glbl: (text key, value)
        shown in your language; ord: place in the fixed outline (positions); property_name: the property the row belongs to;
        detail: the category inside the row."""
        key = (section, row)
        self.vals[key][mk] += amount
        tid = tx if tx is not None else self.cur
        if tid is not None and tid > 0 and tid not in self.ids[key][mk][-3:]:      # which bookings a row holds (to look at them; kept on the Mac)
            self.ids[key][mk].append(tid)
        if detail is not None:
            self.det[key][detail][mk] += amount
        if key not in self.meta:
            self.meta[key] = {"group": group, "account": account, "kind": kind, "nw": nw}
            for k, v in (("lbl", lbl), ("glbl", glbl)):
                if v:
                    self.meta[key][k] = list(v)
            if ord is not None:
                self.meta[key]["ord"] = ord
            if property_name:
                self.meta[key]["property_name"] = property_name


def transit_series(ledger: Ledger, leaves: List[Account], roles: Dict[str, str], months: List[Tuple[int, int]], quelle: Dict[str, str],
                   today: date, known: Optional[List[Tuple[date, date, float, str, str]]] = None) -> Tuple[Dict[str, float], List[dict]]:
    """Geld unterwegs am Monatsende: Umbuchung zwischen zwei Konten des Bereichs, deren Buchungen in verschiedene Monate fallen
    (am 31. abgebucht, am 1. gutgeschrieben). Abgebucht, aber noch nicht gutgeschrieben -> +Betrag; umgekehrt -> -Betrag.
    Nur eindeutige Paare: Gegen-IBAN zeigt auf das andere Konto, gleicher Betrag mit umgekehrtem Vorzeichen, hoechstens 5 Tage Abstand.
    known: die Paare der Kapitalfluss-Zuordnung (pair_transfers) -- dann dieselben, damit Bilanz und Kapitalfluss zusammenpassen.
    Liefert (Betrag je Monatsende, erkannte Umbuchungen ueber ein Monatsende)."""
    mkeys = ["%04d-%02d" % ym for ym in months]
    out = {mk: 0.0 for mk in mkeys}
    if not months:
        return out, []
    if known is not None:
        return _transit_from(ledger, months, mkeys, list(known), today)
    area = {a.uuid for a in leaves if roles.get(a.uuid) not in OFF_BALANCE and not _valuation_account(a, quelle.get(a.uuid, ""))}
    own = ledger.own_ibans()
    first = date(months[0][0], months[0][1], 1) - timedelta(days=6)
    last = month_end(months[-1][0], months[-1][1])
    cents = lambda x: int(round(x * 100))
    by_amt: Dict[int, List[Tx]] = defaultdict(list)
    for t in ledger.txs:
        if t.booked and t.account_uuid in area and first <= t.booking_date <= last:
            by_amt[cents(t.amount)].append(t)
    used: Set[int] = set()
    pairs: List[Tuple[date, date, float, str, str]] = []
    for c, outs in by_amt.items():
        if c >= 0 or -c not in by_amt:
            continue
        for t in sorted(outs, key=lambda x: (x.booking_date, x.id)):
            best = None
            for o in by_amt[-c]:
                if o.id in used or o.account_uuid == t.account_uuid:
                    continue
                if own.get(t.counter_iban) != o.account_uuid and own.get(o.counter_iban) != t.account_uuid:
                    continue
                gap = abs((o.booking_date - t.booking_date).days)
                if gap <= 5 and (best is None or gap < best[0]):
                    best = (gap, o)
            if best is None:
                continue
            o = best[1]
            used.update({t.id, o.id})
            if month_key(t.booking_date) != month_key(o.booking_date):
                pairs.append((t.booking_date, o.booking_date, -t.amount, t.account_uuid, o.account_uuid))
    return _transit_from(ledger, months, mkeys, pairs, today)


def _transit_from(ledger: Ledger, months: List[Tuple[int, int]], mkeys: List[str], pairs: List[Tuple[date, date, float, str, str]],
                  today: date) -> Tuple[Dict[str, float], List[dict]]:
    out = {mk: 0.0 for mk in mkeys}
    for (y, m), mk in zip(months, mkeys):
        if mk >= month_key(today):
            continue                                     # the running month stands at today's balances, which hold every booking: nothing on its way
        cut = month_end(y, m)
        val = sum(p[2] for p in pairs if p[0] <= cut < p[1]) - sum(p[2] for p in pairs if p[1] <= cut < p[0])
        out[mk] = round(val, 2)
    name = lambda u: ledger.accounts[u].name if u in ledger.accounts else u
    details = [{"out_date": p[0].isoformat(), "in_date": p[1].isoformat(), "amount": round(p[2], 2), "from_account": name(p[3]), "to_account": name(p[4])}
               for p in sorted(pairs, key=lambda p: min(p[0], p[1]))]
    return out, details


def company_areas(ledger: Ledger, config: dict) -> List[Tuple[dict, dict]]:
    """The companies set up under Booking rules -- with a participation, or with an account mirror into an account of the
    company. (Their entry in companies, their area) -- the area as everywhere else (bereiche_for: with the accounts you moved
    under Setup)."""
    from core import bereiche_for                  # imported late (core imports report)
    import rules
    areas = bereiche_for(ledger, config)
    by_id = {str(b["id"]): b for b in areas}
    free: Set[str] = set()
    for m in rules.mirrors(config):
        for f in ("a", "b"):
            try:
                free.add(ledger.resolve(m[f]).uuid)
            except KeyError:
                pass
    entries = [g for g in config.get("companies") or [] if isinstance(g, dict)]
    out = []
    done: Set[str] = set()
    for g in entries:
        b = by_id.get(str(g.get("area")))
        if b is None:                              # named by its group or an account in it
            try:
                a = ledger.resolve(str(g.get("area")))
            except KeyError:
                continue
            members = {x.uuid for x in (ledger.descendants(a.uuid) if a.group else [a])}
            b = next((x for x in areas if members & {y.uuid for y in x["leaves"]}), None)
        if b is not None and (g.get("participation") or free & {a.uuid for a in b["leaves"]}):
            out.append((g, b))
            done.add(str(b["id"]))
    for b in areas:                                # a mirror into a company that has no entry of its own
        if b.get("kind") == "company" and str(b["id"]) not in done and free & {a.uuid for a in b["leaves"]}:
            out.append(({"area": b["id"]}, b))
    return out


def company_accounts(ledger: Ledger, config: dict) -> Dict[str, str]:
    """Accounts of the companies set up under Booking rules (with a participation or an account mirror) -> company name."""
    return {a.uuid: b["name"] for g, b in company_areas(ledger, config) for a in b["leaves"]}


VALUE_MARKS = (MARK + "wert-", MARK + "spiegel-")     # value adjustments of Kontor (participation): never a transfer
ASSET_LIKE = ASSET_ROLES | {"other"}               # positions that change only by bookings, valuations and transfers
# Investing and financing by kind, as in a cash flow statement (group, its text key, place): the accounts and loans are the
# rows within. The row names (keys of your planning) stay as they were.
INVEST_GROUPS = {"real_estate": ("Immobilien", "cf_g_immobilien", 610), "tangibles": ("Sachwerte", "cf_g_sachwerte", 620),
                 "securities": ("Wertpapiere & Geldanlagen", "cf_g_anlagen", 630), "term_investments": ("Wertpapiere & Geldanlagen", "cf_g_anlagen", 630),
                 "other": ("Sonstige Anlagen", "cf_g_sonstige", 635), "participations": ("Beteiligungen", "cf_g_beteiligungen", 640),
                 "areas": ("Andere Bereiche", "cf_g_bereiche", 645), "receivables": ("Gewährte Darlehen", "cf_g_forderungen", 650),
                 "foreign": ("Fremdwährung", "cf_fremdwaehrung_g", 660), "saving_group": ("Sparen & Anlegen", "pos_saving", 628)}
FIN_GROUPS = {"drawdown": ("Darlehensaufnahme", "cf_g_aufnahme", 710), "repayment": ("Tilgung", "cf_g_tilgung", 720),
              "interest": ("Zinsen", "cf_g_zinsen", 730), "partners": ("Einlagen/Entnahmen Gesellschafter", "cf_einlagen_gesellschafter", 740)}


def _grp(table: Dict[str, tuple], kind: str) -> dict:
    """The keyword arguments of Rows.add for a row in the group of its kind (investing or financing)."""
    g, key, o = table[kind]
    return {"glbl": (key,), "ord": o, "group": g}
PAIR_DAYS_IBAN = 5                                      # counter IBAN known: counterpart at most this many days apart
PAIR_DAYS_IBAN_BOTH = 14                                # ... and both bookings name each other's account
PAIR_DAYS = 3                                           # by amount only (transfer category, offline account)
PAIR_DAYS_CAT = 7                                       # ... both bookings with a transfer category (PayPal books on the day, the bank days later)
COUNTER_DAYS = 7                                        # a contribution and its counter-booking in a capital account (a mirrored booking
                                                        # keeps the sender's day; the money arrives a business day later -- over Easter: 5-6 days)


def _value_adjustment(t: Tx) -> bool:
    return any(m.startswith(VALUE_MARKS) for m in marks_in(t.purpose))


def foreign_currency(acc: Account) -> bool:
    """An account kept in another currency than the euro (Kontor does not convert)."""
    return (acc.currency or "EUR").upper() != "EUR"


def area_names(ledger: Ledger, config: dict) -> Dict[str, str]:
    """Account -> name of its area (all areas, also accounts outside the net worth)."""
    from core import bereiche_for                  # imported late (core imports report)
    return {a.uuid: b["name"] for b in bereiche_for(ledger, config) for a in b["leaves"]}


def company_stakes(ledger: Ledger, config: dict) -> Dict[str, str]:
    """Company name -> its participation account (Booking rules), named as in company_accounts."""
    out: Dict[str, str] = {}
    for g, b in company_areas(ledger, config):
        if g.get("participation"):
            try:
                out[b["name"]] = ledger.resolve(g["participation"]).uuid
            except KeyError:
                pass
    return out


def pair_transfers(ledger: Ledger, txs: List[Tx], root: Set[str], roles: Dict[str, str], is_transfer: Callable[[str], bool],
                   cost_words: List[str], kf: dict, pairable: Callable[[Tx], bool] = lambda t: True):
    """Transfers within an area, booking by booking: the counterpart of a transfer is the booking on the other side.
    Found by Kontor's mark (#kontor-tx-<payment>: the repayment of a loan names the payment), by the counter IBAN (a booking of
    that account with the same amount, opposite sign, at most 5 days apart) or -- for a transfer category or an offline account
    -- by amount alone (at most 3 days; a week when both have a transfer category). Two transfers on one account that undo each
    other within a month are each other's counterpart (together nothing). Returns (mate: booking -> counterpart in the area, partner: booking -> account on the
    other side, also outside the area or without a counterpart, category: booking -> marked as transfer by its category)."""
    own_ibans = ledger.own_ibans()
    same_iban: Dict[str, List[str]] = defaultdict(list)          # an IBAN on several of your accounts (a card moved to a new bank)
    for a in ledger.accounts.values():
        if a.iban:
            same_iban[a.iban.replace(" ", "").upper()].append(a.uuid)
    cents = lambda x: int(round(x * 100))
    idx = ledger.__dict__.get("_tx_index")
    if idx is None or idx[0] != len(ledger.txs):
        tags: Dict[str, List[Tx]] = defaultdict(list)
        for o in ledger.txs:
            if o.booked and "-tx-" in o.purpose:
                for tag in marks_in(o.purpose):
                    if tag.startswith(TX_MARK):
                        tags[tag].append(o)
        idx = ledger._tx_index = (len(ledger.txs), {t.id: t for t in ledger.txs if t.booked}, tags)
    by_id, by_tag = idx[1], idx[2]
    mate: Dict[int, Tx] = {}
    partner: Dict[int, str] = {}
    by_cat: Dict[int, bool] = {}

    def join(a: Tx, b: Tx) -> None:
        mate[a.id], mate[b.id] = b, a
        partner[a.id], partner[b.id] = b.account_uuid, a.account_uuid

    # 1. Kontor's mark: the booking names its payment
    for t in txs:
        by_cat[t.id] = bool(t.category_path) and is_transfer(t.category_path)
        if "-tx-" not in t.purpose and "-tx-" not in t.comment:
            continue
        for tag in marks_in(t.purpose + " " + t.comment):
            if not tag.startswith(TX_MARK):
                continue
            num = tag[len(TX_MARK):]
            src = by_id.get(int(num)) if num.isdigit() else None
            cands = [src] if src is not None else [o for o in by_tag.get(tag, ()) if o.id != t.id]
            for o in cands:
                if o is None or o.account_uuid == t.account_uuid:
                    continue
                if o.account_uuid in root and t.id not in mate and o.id not in mate:
                    join(t, o)
                elif t.id not in partner:
                    partner[t.id] = o.account_uuid
                break
    # 2. counter IBAN: the other account's booking with the same amount
    near: Dict[str, Dict[int, List[Tx]]] = {}

    def bookings_of(u: str) -> Dict[int, List[Tx]]:
        if u not in near:
            m: Dict[int, List[Tx]] = defaultdict(list)
            for o in ledger.transactions(u):
                m[cents(o.amount)].append(o)
            near[u] = m
        return near[u]
    # first close by, then -- for bookings that name each other -- up to two weeks apart (a missing booking does not shift the
    # pairs of a recurring transfer)
    for wide in (False, True):
        for t in sorted(txs, key=lambda x: (x.booking_date, x.id)):
            if t.id in mate or (wide and t.id not in partner):
                continue
            p = own_ibans.get(t.counter_iban) if t.counter_iban else None
            if p is None or p == t.account_uuid:
                continue
            # the same IBAN on several accounts (a card moved to a new bank): the counterpart is looked for in those of this area too
            accs = ([p] if p in root else []) + [u for u in same_iban.get(t.counter_iban, ()) if u not in (p, t.account_uuid) and u in root]
            if not accs:
                partner.setdefault(t.id, p)
                continue
            best = None
            for o in (x for u in accs for x in bookings_of(u).get(-cents(t.amount), ())):
                if o.id in mate:
                    continue
                gap = abs((o.booking_date - t.booking_date).days)
                back = own_ibans.get(o.counter_iban) == t.account_uuid
                if gap > (PAIR_DAYS_IBAN_BOTH if wide and back else PAIR_DAYS_IBAN):
                    continue
                rank = (not back, gap, o.id)
                if best is None or rank < best[0]:
                    best = (rank, o)
            if best is not None:
                join(t, best[1])
            elif p not in root:
                partner.setdefault(t.id, p)              # as before: an account of another area
            else:
                partner[t.id] = p                       # the other account, but its booking is missing
    # a transfer by its category whose IBAN names an account without the counterpart: it may still pair by amount below (the
    # IBAN can be outdated -- a card moved to another bank collects from the old account's IBAN); if not, it stays as it was
    held = {t.id: partner.pop(t.id) for t in txs if by_cat[t.id] and t.id not in mate and t.id in partner and partner[t.id] in root}
    # 3. by amount: transfer category or a booking of an offline account (no counterpart known yet)
    if kf.get("transfer_pairing", True):
        manual_ok = kf.get("pairing_manual_accounts", True)
        loose = lambda t: t.id not in mate and t.id not in partner          # the other side is not known yet
        open_tx = [t for t in txs if by_cat[t.id] and loose(t)]
        offline = [t for t in txs if manual_ok and loose(t) and roles.get(t.account_uuid) != "cash"
                   and (roles.get(t.account_uuid) in ("liabilities", "receivables") or roles.get(t.account_uuid) in ASSET_LIKE)
                   and ledger.accounts[t.account_uuid].offline and not _is_cost(t, cost_words) and not _value_adjustment(t)]
        liquid = [t for t in txs if roles.get(t.account_uuid) == "cash" and loose(t) and (by_cat[t.id] or pairable(t))]
        pools: Dict[str, Dict[int, List[Tx]]] = {"open": defaultdict(list), "offline": defaultdict(list), "liquid": defaultdict(list)}
        for name, lst in (("open", open_tx), ("offline", offline), ("liquid", liquid)):
            for o in lst:
                pools[name][cents(o.amount)].append(o)
        kinds: Dict[int, Set[str]] = defaultdict(set)
        for name, lst in (("open", open_tx), ("offline", offline), ("liquid", liquid)):
            for o in lst:
                kinds[o.id].add(name)
        # every possible pair, the closest first (a booking never takes the counterpart of a closer one): by amount on two
        # accounts -- within a week when both carry a transfer category (PayPal books on the day, the bank days later), else 3 days --
        # and two transfers on one account that undo each other within the month (a top-up booked back: together nothing)
        cands = []
        for t in {o.id: o for o in open_tx + offline + liquid}.values():
            k = kinds[t.id]
            search = (["open"] if "open" in k else []) + (["liquid"] if "offline" in k else []) + (["offline"] if "liquid" in k else [])
            for name in search:
                for o in pools[name].get(-cents(t.amount), ()):
                    if o.id == t.id:
                        continue
                    gap = abs((o.booking_date - t.booking_date).days)
                    both = name == "open" and "open" in k
                    if t.id in held or o.id in held:             # its IBAN named another account: only another transfer on another account
                        ok = both and o.account_uuid != t.account_uuid and gap <= PAIR_DAYS_CAT
                    elif o.account_uuid == t.account_uuid:
                        ok = (both and month_key(o.booking_date) == month_key(t.booking_date)
                              and not (t.counter_iban and o.counter_iban and t.counter_iban != o.counter_iban))      # booked back: the same counterparty
                    else:
                        ok = gap <= (PAIR_DAYS_CAT if both else PAIR_DAYS)
                    if ok:
                        cands.append((gap, min(t.id, o.id), max(t.id, o.id), t, o))
        for _gap, _a, _b, t, o in sorted(cands, key=lambda c: c[:3]):
            if t.id in mate or o.id in mate:
                continue
            if o.account_uuid == t.account_uuid:
                mate[t.id], mate[o.id] = o, t                    # no partner account: nothing moved anywhere
            else:
                join(t, o)
    for i, p in held.items():
        if i not in mate:
            partner[i] = p
    return mate, partner, by_cat


# ---------------------------------------------------------------------------
# Cash flow positions: a fixed outline for income and expenses; MoneyMoney's categories are assigned to them once
# (Kategorien -> Cashflow-Positionen; Kontor proposes by name). Planning works on the positions.
# ---------------------------------------------------------------------------
POSITIONS = [  # (key, section, row -- German, the key of your planning; shown in your language via pos_<key>); one outline for
    # every area (a row shows only where there is money in it)
    ("work_income", "income", "Arbeitseinkommen"), ("revenue", "income", "Umsatzerlöse"), ("rental", "income", "Vermietung"),
    ("capital_income", "income", "Kapitalerträge"), ("refunds", "income", "Erstattungen"), ("other_income", "income", "Sonstige Einnahmen"),
    ("goods", "expenses", "Wareneinkauf"), ("staff", "expenses", "Personal"), ("operations", "expenses", "Betriebskosten"),
    ("housing", "expenses", "Wohnen"), ("living", "expenses", "Lebenshaltung"), ("mobility", "expenses", "Mobilität"),
    ("insurance", "expenses", "Versicherungen"), ("health", "expenses", "Gesundheit"), ("leisure", "expenses", "Freizeit & Reisen"),
    ("property_costs", "expenses", "Objektkosten"), ("administration", "expenses", "Beratung & Gebühren"), ("taxes", "expenses", "Steuern"),
    ("vat", "expenses", "Umsatzsteuer"),
    ("donations", "expenses", "Geschenke & Spenden"), ("other_expenses", "expenses", "Sonstige Ausgaben"),
    ("saving", "investing", "Sparen & Anlegen"), ("repayment", "financing", "Tilgung"), ("loan_interest", "financing", "Zinsen"),
    ("ignore", "", ""),
]
POS = {k: (sec, row, i) for i, (k, sec, row) in enumerate(POSITIONS)}
COMPANY_ROWS = {"housing": "Raumkosten"}       # the same position, named as a company would (text pos_<key>_g)


def position_row(pos: str, company: bool) -> Tuple[str, str]:
    """(row -- German, the key of your planning; text key) of a position in an area."""
    if company and pos in COMPANY_ROWS:
        return COMPANY_ROWS[pos], "pos_%s_g" % pos
    return POS[pos][1], "pos_" + pos
# words in a category's name -> (position when the money comes in, when it goes out); the first hit wins. Context words in the
# path first (a category under "Vermietung" is about a property), then the category's own name, then its whole path.
# words in a category's name -> (position when the money comes in, when it goes out); the first hit wins: saving, financing and
# interest first (name, then whole path), then the context (a category under "Vermietung" is about a property), then the rest
# (name, then path). Folded (ae, oe, ue, ss); German names are compounds, so parts of words count -- words of up to three
# letters only at the start of a word.
POSITION_FIRST = [  # (words, in, out, only at the start of a word); not for costs of these (fees, card) -- see FIRST_NOT
    (("zins", "finanzierungskost"), "capital_income", "loan_interest", False),
    (("tilgung", "kredit", "darlehen", "finanzierung", "annuit"), "repayment", "repayment", False),
    (("sparen", "sparplan", "bauspar", "invest", "wertpapier", "depot", "etf", "aktie", "fonds", "geldanlage", "ruecklage", "krypto",
      "altersvorsorge", "beteiligung", "immobilienkauf", "kapitalanlage"), "saving", "saving", True),
]
FIRST_NOT = ("gebuehr", "kosten", "entgelt", "provision", "kreditkarte")
POSITION_CONTEXT = [(("vermiet", "immobil", "objekt"), "rental", "property_costs")]
POSITION_HINTS = [
    (("steuerberat", "beratung", "notar", "anwalt", "kontofuehr", "gebuehr", "bankgeb"), "other_income", "administration"),
    (("wareneinkauf", "waren", "lieferant", "material"), "refunds", "goods"),
    (("personal", "loehne", "sozialversicher", "sozialabgab", "lohnneben"), "refunds", "staff"),
    (("umsatzerl", "erloes", "kasseneinnahm", "verkauf"), "revenue", "other_expenses"),
    (("betriebskost", "betriebsbedarf", "marketing", "werbung", "software", "it-kost"), "refunds", "operations"),
    (("ladenmiete", "raumkost", "geschaeftsmiete", "gewerbemiete"), "rental", "housing"),
    (("hausgeld", "instandhalt", "reparatur", "hausverwalt", "grundsteuer"), "refunds", "property_costs"),
    (("umsatzsteuer", "vorsteuer", "ust"), "vat", "vat"),
    (("finanzamt", "steuer", "solidarit"), "refunds", "taxes"),
    (("mieteink", "pachteink"), "rental", "property_costs"),
    (("kapitaleink",), "capital_income", "other_expenses"),
    (("gehalt", "gehaelt", "lohn", "loehn", "tantieme", "bonus", "gratifikation", "verguetung", "honorar", "arbeit"), "work_income", "staff"),
    (("dividend", "kapitalertr", "ausschuett"), "capital_income", "other_expenses"),
    (("mieteinnahm", "pacht"), "rental", "property_costs"),
    (("erstattung", "rueckzahlung", "gutschrift", "cashback"), "refunds", "other_expenses"),
    (("geldautomat", "bargeld", "barabhebung", "abhebung"), "other_income", "other_expenses"),
    (("versicherung",), "refunds", "insurance"),
    (("restaurant", "gastro"), "refunds", "leisure"),
    (("miete",), "rental", "housing"),
    (("nebenkost", "strom", "energie", "wasser", "heiz", "internet", "telefon", "mobilfunk", "rundfunk", "wohnen", "wohnung"), "refunds", "housing"),
    (("lebensmittel", "supermarkt", "einkauf", "drogerie", "kleidung", "haushalt", "lebenshalt"), "refunds", "living"),
    (("auto", "kfz", "tank", "benzin", "mobilit", "bahn", "oepnv", "taxi", "parken", "fahrrad", "verkehr", "maut", "transport"), "refunds", "mobility"),
    (("gesundheit", "arzt", "apotheke", "medizin", "zahn", "kranken", "therapie"), "refunds", "health"),
    (("freizeit", "urlaub", "reise", "kultur", "sport", "hobby", "abo", "streaming", "kino", "konzert", "hotel", "flug"), "refunds", "leisure"),
    (("spende", "geschenk"), "other_income", "donations"),
]
_word_rx = {}


def _has(words, text: str, start: bool = False) -> bool:
    for w in words:
        if start or len(w) <= 3:
            rx = _word_rx.get(w) or _word_rx.setdefault(w, re.compile(r"(?<![a-z])" + re.escape(w)))
            if rx.search(text):
                return True
        elif w in text:
            return True
    return False


# a booking without a category: (field "name" or "text" = name, purpose and booking text, words) -> (position when money comes
# in, goes out) for a person and for a company. None: no estimate from this entry (the next one may have one); "": no estimate
# at all (e.g. a loan rate mixes repayment and interest). Learned patterns of your categories come first (see classify).
TX_HINTS = [
    ("text", r"tilgung|annuitaet|darlehensrate|kreditrate|\brate\b", ("", ""), ("", "")),
    ("text", r"ausschuettung|dividend|ertragsgutschrift", ("capital_income", ""), ("capital_income", "")),
    ("text", r"\bzins|sollzins|habenzins|zinsabschluss|kupon", ("capital_income", "loan_interest"), ("capital_income", "loan_interest")),
    ("name", r"deutsche rentenversicherung", ("", "insurance"), ("", "staff")),       # money from it: a pension, no estimate
    ("name", r"\baok\b|techniker krankenkasse|barmer|\bdak\b|\bikk\b|\bbkk\b|knappschaft|minijob|berufsgenossenschaft|krankenkasse|rentenversicherung",
     ("refunds", "insurance"), ("refunds", "staff")),
    ("text", r"\blohn\b|\bgehalt|lohn/gehalt|\bloehne\b|entgeltabrechnung|bezuege|\bverguetung", ("work_income", None), (None, "staff")),
    ("text", r"bareinzahlung|kartenumsa|kartenzahlung|nexi\b|concardis|adyen|sumup|payone|worldline|elavon|ec-cash|girocard|kassenabrechnung", (None, None), ("revenue", None)),
    ("name", r"steuerberat|rechtsanwalt|notar|kanzlei|wirtschaftspruef|datev|amtsgericht|handelsregister|bundesanzeiger|\bihk\b", (None, "administration"), (None, "administration")),
    ("text", r"hausgeld|wohngeld|instandhaltungsruecklage|hausverwaltung", ("refunds", "housing"), ("refunds", "property_costs")),
    ("text", r"\bmiete\b|mietzahlung|kaltmiete|warmmiete|\bpacht\b|nebenkosten", ("rental", "housing"), ("rental", "housing")),
    ("name", r"stadtwerke|vattenfall|e\.on|\beon\b|\benbw\b|naturstrom|lichtblick|polarstern|\bstrom|fernwaerme", ("refunds", "housing"), ("refunds", "housing")),
    ("name", r"telekom|vodafone|telefonica|\bo2\b|1&1|congstar|m-net|rundfunk|beitragsservice", ("refunds", "housing"), ("refunds", "operations")),
    ("text", r"kontofuehrung|kontoentgelt|gebuehr|kartenpreis|kontopreis|kontomodell", (None, "administration"), (None, "administration")),
    ("name", r"versicherung|allianz|\bhuk\b|\bergo\b|\baxa\b|generali|signal iduna|debeka|\bhdi\b|\bwwk\b|\blvm\b|\bdevk\b|gothaer|provinzial",
     ("refunds", "insurance"), ("refunds", "insurance")),
    ("text", r"spende|unicef|aerzte ohne grenzen|\bwwf\b|greenpeace|albert schweitzer", (None, "donations"), (None, "donations")),
    ("name", r"\brewe\b|\bedeka\b|\baldi\b|\blidl\b|\bpenny\b|kaufland|denns|alnatura|\bdm\b|dm-drogerie|rossmann|amazon|zalando|\bikea\b",
     ("refunds", "living"), (None, None)),
    ("name", r"deutsche bahn|\bdb vertrieb|\bmvg\b|\bmvv\b|\baral\b|\bshell\b|\besso\b|totalenergies|tankstelle|\bsixt\b|share now|\buber\b|flixbus|lufthansa|parkhaus|\bapcoa\b|\badac\b",
     ("refunds", "mobility"), (None, "operations")),
    ("name", r"apotheke|zahnarzt|\barzt|arztpraxis|klinik|krankenhaus|physiotherap|fielmann", ("refunds", "health"), (None, None)),
    ("name", r"netflix|spotify|disney|apple\.com|itunes|google play|eventim|airbnb|booking\.com|\bhotel|restaurant|lieferando|\bwolt\b|\bkino",
     ("refunds", "leisure"), (None, None)),
]
_TX_HINTS = [(f, re.compile(rx), pp, pc) for f, rx, pp, pc in TX_HINTS]
# the tax office: wage tax is part of staff costs (a company), VAT a position of its own, the rest taxes (or a refund)
_TAX_OFFICE = re.compile(r"finanzamt|steuerkasse|bundeskasse|stadtkasse|gemeindekasse")
_WAGE_TAX = re.compile(r"lohnsteuer|\blst\b|lohnst")
_VAT = re.compile(r"umsatzsteuer|\bust\b|ustva|ust-va|ust-vz|ust-voranmeldung|vorsteuer")


def fold_text(s: str) -> str:
    return (s or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")


def guess_position(t: Tx, company: bool, by_name: bool = True) -> Optional[str]:
    """Kontor's estimate for a booking without a category, by the words in its name, purpose and booking text (or None).
    by_name=False: the name says nothing (the other side is one of your own areas) -- purpose and booking text only."""
    name = fold_text(t.name) if by_name else ""
    text = name + " " + fold_text(t.purpose + " " + t.booking_text)
    if _TAX_OFFICE.search(name):
        if _WAGE_TAX.search(text):
            return "staff" if company and t.amount < 0 else ("refunds" if t.amount > 0 else "taxes")
        if _VAT.search(text):
            return "vat"
        return "refunds" if t.amount > 0 else "taxes"
    for field, rx, pp, pc in _TX_HINTS:
        if rx.search(name if field == "name" else text):
            pos = (pc if company else pp)[0 if t.amount > 0 else 1]
            if pos is not None:
                return pos or None
    return None


def propose_position(path: str, income: bool) -> str:
    """Kontor's proposal for a category (by its words); income: its money mostly comes in."""
    return recognised_position(path, income) or ("other_income" if income else "other_expenses")


def recognised_position(path: str, income: bool) -> Optional[str]:
    """The position a category's words name -- None when none of them is known (then it is "other" income or expenses)."""
    low = fold_text(path)
    name = low.split(" / ")[-1]
    low_l = fold_text(legacy_cat(path))                # read as before 3.13.19 (every slash a level) first: the same proposals
    name_l = low_l.split(" / ")[-1]
    texts = list(dict.fromkeys((name_l, low_l, name, low)))
    for text in texts:
        for words, pin, pout, start in POSITION_FIRST:
            if pin != "capital_income" and any(w in text for w in FIRST_NOT):
                continue
            if _has(words, text, start):
                return pin if income else pout
    for text in dict.fromkeys((low_l, low)):
        for words, pin, pout in POSITION_CONTEXT:
            if _has(words, text):
                return pin if income else pout
    for text in texts:
        for words, pin, pout in POSITION_HINTS:
            if _has(words, text):
                return pin if income else pout
    # "Einkommen" names work income only as the category's own name (its subcategories -- child benefit, pension -- are no
    # salary) and as a word of its own ("Hereinkommende Zahlungen" is none)
    if income and any(_has(("einkommen",), n, True) for n in dict.fromkeys((name_l, name))):
        return "work_income"
    return None


def category_totals(ledger: Ledger, accounts: Optional[Set[str]] = None) -> Dict[str, float]:
    """Sum per category over all booked transactions (whether its money mostly comes in or goes out). accounts: only those of
    an area -- "Gehalt" is income for you and an expense for your company."""
    out: Dict[str, float] = defaultdict(float)
    for t in ledger.txs:
        if t.booked and t.category_path and (accounts is None or t.account_uuid in accounts):
            out[norm_cat(t.category_path)] += t.amount
    return dict(out)


def position_of(path: str, config: dict, totals: Dict[str, float]) -> Tuple[str, bool]:
    """(position, yours) of a category: what you chose for it or for the nearest category above it (Kategorien ->
    Cashflow-Positionen), otherwise Kontor's proposal."""
    mine = my_positions(config)
    parts = path.split(" / ")
    for i in range(len(parts), 0, -1):
        p = " / ".join(parts[:i])
        if p in mine:
            return mine[p], True
    return propose_position(path, totals.get(path, 0.0) > 0), False


def my_positions(config: dict) -> Dict[str, str]:
    """The positions you chose: category path -> position (or "umbuchung": a transfer between your own accounts)."""
    return {norm_cat(k): v for k, v in ((config.get("cashflow") or {}).get("positions") or {}).items()
            if (v in POS or v == "transfer") and norm_cat(k)}


# the usual names of a transfer category -- the category's own name only (not one above it: "Übertrag / Familie" may be anything)
TRANSFER_NAMES = {"umbuchung", "umbuchungen", "uebertrag", "uebertraege", "kontouebertrag", "eigene konten", "eigenes konto"}


def transfer_check(config: dict) -> Callable[[str], bool]:
    """Is a category a transfer between your own accounts? Your choice for it or the nearest category above it decides;
    without one: a transfer category (settings: cashflow.transfer_categories) -- by its path, one above it or its name."""
    mine = my_positions(config)
    names = {fold_text(f(c)) for c in ((config.get("cashflow") or {}).get("transfer_categories") or ["Umbuchung"]) if c
             for f in (norm_cat, legacy_cat)}                # "Finanzen/Intern" written by hand: also as two levels
    memo: Dict[str, bool] = {}

    def check(path: str) -> bool:
        p = norm_cat(path)
        r = memo.get(p)
        if r is None:
            parts = p.split(" / ") if p else []
            r = None
            for i in range(len(parts), 0, -1):
                v = mine.get(" / ".join(parts[:i]))
                if v:
                    r = v == "transfer"
                    break
            if r is None:                              # by its name -- also read as before 3.13.19 ('Eigene Konten/Umbuchung')
                r = False
                for ps in (parts, legacy_cat(p).split(" / ") if p else []):
                    low = [fold_text(x) for x in ps]
                    if ps and (low[-1] in names or low[-1] in TRANSFER_NAMES or any(" / ".join(low[:i]) in names for i in range(1, len(low) + 1))):
                        r = True
                        break
            memo[p] = r
        return r
    return check


def classify(ledger: Ledger, leaves: List[Account], roles: Dict[str, str], config: dict, months: List[Tuple[int, int]],
             verlauf: Dict[str, str], areas: Optional[Dict[str, str]] = None, company: bool = False,
             objekte: Optional[Dict[str, str]] = None, learned: Optional[dict] = None, area_id: str = ""):
    """Cash flow rows of an area. Every booking of its accounts counts once: a transfer within the area (both bookings found)
    as one row that leaves the net worth unchanged, everything else with its amount. areas: account -> name of its area (all
    areas; transfers between areas are contributions/withdrawals); company: this area is a company; objekte: category ->
    property (its own rows); learned: the patterns learned from your categories (categorize) -- a booking without a category
    counts in the position they suggest, else in Kontor's estimate by its words (marked as estimated). Returns (rows, inbound
    per account and month, warnings); rows.pairs: transfers within the area (for money in transit at month end), rows.reasons:
    amounts left out on purpose (category "Ignore"), rows.saving_recipients: saving without a booking on the other side, by recipient
    (where it went: your choice per recipient, else the category's account, else the only depot), rows.mapped_in: what that
    put into accounts kept by balances that are no depot. area_id: this area (your choices per recipient are per area)."""
    kf = config.get("cashflow", {}) or {}
    root_leaves = {a.uuid for a in leaves}
    areas = areas or {}
    is_transfer = transfer_check(config)
    cost_words = [w.lower() for w in (kf.get("costs_texts") or COST_WORDS)]
    kat_zu_konto: Dict[str, str] = {}                 # investment category -> the account it goes into
    for cat_name, ref in (kf.get("category_to_account") or {}).items():
        try:
            kat_zu_konto[norm_cat(cat_name)] = ledger.resolve(ref).uuid
        except KeyError:
            pass
    emp_zu_konto: Dict[str, str] = {}                 # recipient -> the account saving goes into ("extern": none in MoneyMoney)
    unsure: Dict[str, float] = {}                     # category -> amount between your areas counted as contribution/withdrawal
    for key, ref in ((kf.get("recipient_to_account") or {}).get(str(area_id)) or {}).items():
        if ref == "external":
            emp_zu_konto[key] = ref
            continue
        try:
            emp_zu_konto[key] = ledger.resolve(ref).uuid
        except KeyError:
            pass
    totals = category_totals(ledger, {a.uuid for a in leaves})      # the direction of a category within this area
    objekte = {norm_cat(k): v for k, v in (objekte or {}).items() if k}
    beteiligungs_gruppen = company_accounts(ledger, config)       # payments to and from them: contributions/withdrawals
    stakes = {g: u for g, u in company_stakes(ledger, config).items() if u in root_leaves}     # held by this area
    self_name = next((areas[u] for u in root_leaves if u in areas), None)
    first = date(months[0][0], months[0][1], 1)
    last = month_end(months[-1][0], months[-1][1])

    # Depots mit Verlauf aus Kontostaenden liefern keine Zahlungsfluesse: ihre Wertaenderung ist Bewertung.
    # Andere Konten mit Kontostaenden behalten ihre Buchungen; Abweichungen zu den Kontostaenden werden als Korrektur ausgewiesen.
    flows = {u for u in root_leaves if u in ledger.accounts and not _valuation_account(ledger.accounts[u], verlauf.get(u, ""))}
    depots = [u for u in root_leaves if u in ledger.accounts and u not in flows]
    in_root = [t for t in ledger.txs if t.account_uuid in flows and t.booked and first <= t.booking_date <= last]

    R = Rows()
    warnings: List[str] = []
    unclear = 0
    inbound: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    stake_in: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    no_target: Dict[str, float] = defaultdict(float)
    mapped_in: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    savings: Dict[str, dict] = {}
    ignored: Dict[str, float] = defaultdict(float)
    ignored_ids: Dict[str, List[int]] = defaultdict(list)      # the bookings behind it (a click on the check row)

    pos_memo: Dict[str, Tuple[str, Optional[str]]] = {}

    def place(cat: str) -> Tuple[str, Optional[str]]:
        """(position, property) of a category: a property's category (and those below it) has its own rows -- unless it is
        interest or a repayment, or you chose saving or leaving it out."""
        r = pos_memo.get(cat)
        if r is None:
            # the most specific property's category (one property's may lie below another's)
            hits = [c for c in objekte if cat == c or cat.startswith(c + " / ")]
            obj = objekte[max(hits, key=len)] if hits else None
            pos, yours = position_of(cat, config, totals)
            if obj and (pos in ("repayment", "loan_interest") or (yours and pos in ("saving", "ignore"))):
                obj = None
            r = pos_memo[cat] = (pos, obj)
        return r

    def pairable(t: Tx) -> bool:
        """A bank booking that may be the other side of a booking in an offline account: no category, or one for saving or a
        repayment -- never income or an expense."""
        return not t.category_path or place(norm_cat(t.category_path))[0] in ("saving", "repayment")
    mate, partner, by_cat = pair_transfers(ledger, in_root, flows, roles, is_transfer, cost_words, kf, pairable)
    # An account that starts within these months with a balance of its own (its opening balance in MoneyMoney: before its first
    # booking the balance sheet has none): a transfer where a bank account of the area shows the opposite amount that month
    # and nothing else explains that booking (a balance moved over from an old card, say), else a row of its own among the
    # changes in value -- never "balance unknown".
    openings: List[Tuple[str, str, float]] = []
    n_virtual = 0
    if int(((config.get("balance") or {}).get("months_back", 0) or 0)) <= 0 and months:
        first_mk = "%04d-%02d" % months[0]
        cents = lambda x: int(round(x * 100))
        for u in sorted(flows, key=lambda x: ledger.accounts[x].name):
            own_txs = ledger.transactions(u)
            if not own_txs or verlauf.get(u) == "balances":
                continue
            fm = month_key(min(x.booking_date for x in own_txs))
            op = round(ledger.accounts[u].balance - sum(x.amount for x in own_txs), 2)
            if abs(op) < 0.005 or fm <= first_mk or fm > month_key(last):
                continue
            # only a booking nothing else explains: no category of income or expenses, no other account on its other side
            cands = [x for x in in_root if x.account_uuid != u and roles.get(x.account_uuid) == "cash" and x.id not in mate
                     and (by_cat[x.id] or pairable(x)) and partner.get(x.id) in (None, u)
                     and month_key(x.booking_date) == fm and cents(x.amount) == -cents(op)]
            if len(cands) == 1:
                o = cands[0]
                n_virtual += 1
                v = Tx(id=-(2 * 10**9) - n_virtual, account_uuid=u, booking_date=o.booking_date, value_date=None, amount=op,
                       currency=ledger.accounts[u].currency or "EUR")
                mate[o.id], partner[o.id] = v, u
                continue
            openings.append((u, fm, op))
    pairs: List[Tuple[date, date, float, str, str]] = []
    seen_pair: Set[int] = set()
    paired: Set[int] = set()
    # A contribution or withdrawal between two of your areas that you also booked against a manual account of this area (your
    # capital account at home -- a participation or receivable --, the partner's capital account in the company -- a liability):
    # opposite amount, at most COUNTER_DAYS apart (over a month end: money in transit) -- the money went into (came out of) that account, the net worth
    # stays; not a change in value. Only offline accounts, never a car or a depot; one payment to one booking only: first where
    # the account is tied to the other area (an account mirror into it, its participation, its name in the account or booking),
    # then the rest -- a booking that two payments could claim stays as it was.
    cents_ = lambda x: int(round(x * 100))
    pool: Dict[int, List[Tx]] = defaultdict(list)
    for o in in_root:
        oa = ledger.accounts[o.account_uuid]
        if roles.get(oa.uuid, "other") not in ("participations", "receivables", "liabilities") or not oa.offline or oa.uuid in depots \
                or mate.get(o.id) is not None or _value_adjustment(o) or foreign_currency(oa) or _is_cost(o, cost_words):
            continue
        pool[cents_(o.amount)].append(o)
    mirror_areas: Dict[str, Set[str]] = defaultdict(set)
    for m in config.get("account_mirrors") or []:
        try:
            ma, mb = ledger.resolve(str(m.get("a") or "")).uuid, ledger.resolve(str(m.get("b") or "")).uuid
        except (KeyError, AttributeError):
            continue
        if mb in areas:
            mirror_areas[ma].add(areas[mb])
        if ma in areas:
            mirror_areas[mb].add(areas[ma])
    stake_company = {u: g for g, u in stakes.items()}

    def tied(o: Tx, name: str) -> bool:
        oa, n = ledger.accounts[o.account_uuid], name.casefold()
        return name in mirror_areas.get(oa.uuid, ()) or stake_company.get(oa.uuid) == name \
            or any(n in (x or "").casefold() for x in (oa.name, o.name, o.purpose))
    def between_position(t: Tx) -> Tuple[str, Optional[str], bool]:
        """A payment between two of your areas: (its category, the position it counts in, chosen by you)."""
        c0 = norm_cat(t.category_path)
        if not c0:
            return c0, guess_position(t, company, by_name=False), False
        g0, yours = position_of(c0, config, totals)
        return c0, (g0 if yours else recognised_position(c0, totals.get(c0, 0.0) > 0)), yours

    def paid_for(g0: Optional[str]) -> bool:
        return g0 in POS and (POS[g0][0] in ("income", "expenses") or g0 == "loan_interest")      # interest paid is a cost as well

    claims_by: List[Tuple[Tx, List[Tx], List[Tx]]] = []
    for t in in_root:
        p_t = partner.get(t.id)
        if roles.get(t.account_uuid) != "cash" or mate.get(t.id) is not None or p_t is None:
            continue
        name = beteiligungs_gruppen.get(p_t) or areas.get(p_t)
        if not name or name == self_name or (p_t in ledger.accounts and foreign_currency(ledger.accounts[p_t])) \
                or (not by_cat[t.id] and paid_for(between_position(t)[1])):
            continue                                     # paid for something, or into another currency: no contribution
        c = [o for o in pool.get(-cents_(t.amount), []) if abs((o.booking_date - t.booking_date).days) <= COUNTER_DAYS]
        if c:
            claims_by.append((t, [o for o in c if tied(o, name)], c))
    # in steps by distance (the same day, PAIR_DAYS, COUNTER_DAYS), each with the tied accounts first: what is clear in an
    # earlier step is out of the later ones (a contribution every week stays linked; a mirrored booking that came days
    # later is found all the same)
    reserved: Dict[int, Tx] = {}
    tied_ids = {o.id for _, lk, _ in claims_by for o in lk}
    for limit in (0, PAIR_DAYS, COUNTER_DAYS):
        for phase in (1, 2):
            used = {o.id for o in reserved.values()}
            lists = [(t, [o for o in (lk if phase == 1 else [x for x in c if x.id not in tied_ids])
                          if o.id not in used and abs((o.booking_date - t.booking_date).days) <= limit])
                     for t, lk, c in claims_by if t.id not in reserved]
            n_claims = Counter(o.id for _, c in lists for o in c)
            for t, c in lists:
                if len(c) == 1 and n_claims[c[0].id] == 1:
                    reserved[t.id] = c[0]

    def counter_booking(t: Tx, mk: str) -> Optional[Tx]:
        o = reserved.get(t.id)
        if o is None:
            return None
        # its change in value (in the month of the counter-booking): what it moved by beyond this money
        stake_in[o.account_uuid][month_key(o.booking_date)] += -t.amount
        if month_key(o.booking_date) != mk:              # over a month end (paid on the 30th, booked or arrived on the 1st): in transit
            out_, in_ = (t, o) if t.amount < 0 else (o, t)
            pairs.append((out_.booking_date, in_.booking_date, -out_.amount, out_.account_uuid, in_.account_uuid, out_.id, in_.id))
        return o

    def counter_row(t: Tx, mk: str, other: str, cb: Tx) -> None:
        """A payment between two of your areas that went into (came out of) an account of this one, by that account's kind: a
        participation or a loan granted under investing, a liability under financing (a company: from its partners, yours: a
        loan taken up or repaid). Named \"<other area>: <account>\"; its counter-booking is behind the figure too."""
        ca = ledger.accounts[cb.account_uuid]
        r_c = roles.get(ca.uuid, "other")
        row, kind = "Einlage/Entnahme %s / %s" % (other, ca.name), "external"
        if r_c in ("participations", "receivables"):
            sec, grp = "investing", _grp(INVEST_GROUPS, r_c)
        elif company:
            sec, grp = "financing", _grp(FIN_GROUPS, "partners")
        else:                                            # a loan of yours: taken up and repaid apart (never a negative loan taken up)
            sec, grp = "financing", _grp(FIN_GROUPS, "drawdown" if t.amount > 0 else "repayment")
            row, kind = row + (" / Aufnahme" if t.amount > 0 else " / Tilgung"), ("drawdown" if t.amount > 0 else "repayment")
        R.add(sec, row=row, mk=mk, amount=t.amount, account=ca.uuid, kind=kind, nw=False, lbl=("cf_einlage_auf", other, ca.name), **grp)
        R.ids[(sec, row)][mk].append(cb.id)

    def own_row(t: Tx, acc: Account, role: str, mk: str) -> None:
        """A booking of an account that is no bank account (loan, receivable, asset): interest or a change of its value."""
        nonlocal unclear
        if role == "liabilities" and _is_cost(t, cost_words):
            R.add("financing", row=acc.name + " / Zinsen", mk=mk, amount=t.amount, account=acc.uuid, kind="interest", nw=True, lbl=("cf_name", acc.name), **_grp(FIN_GROUPS, "interest"))
            R.add("financing", row=acc.name + " / Tilgung", mk=mk, amount=-t.amount, account=acc.uuid, kind="repayment", nw=False, lbl=("cf_name", acc.name), tx=-1, **_grp(FIN_GROUPS, "repayment"))      # its other side: the booking is listed with the interest
        elif role == "receivables" and _is_cost(t, cost_words):
            R.add("investing", row=acc.name + " / Zinsen", mk=mk, amount=t.amount, account=acc.uuid, kind="interest", nw=True, lbl=("cf_zinsen", acc.name), **_grp(INVEST_GROUPS, "receivables"))
            R.add("investing", row=acc.name + " / Rückzahlung", mk=mk, amount=-t.amount, account=acc.uuid, kind="payback", nw=False, lbl=("cf_name", acc.name), tx=-1, **_grp(INVEST_GROUPS, "receivables"))
        elif role in ("liabilities", "receivables") or role in ASSET_LIKE:
            R.add("valuation", acc.name, acc.name, mk, t.amount, account=acc.uuid, kind="account", nw=True)
        else:
            R.add("unclear", "Konto ohne Position", acc.name + " (Position unbekannt)", mk, t.amount, kind="unclear", tx=t.id,
                  lbl=("cf_position_unbekannt", acc.name), glbl=("cf_konto_ohne_position",)); unclear += 1

    for t in in_root:
        R.cur = t.id                                     # every row added for it holds it (a click shows the bookings behind a figure)
        acc = ledger.accounts[t.account_uuid]
        role = roles.get(acc.uuid, "other")
        mk = month_key(t.booking_date)
        o = mate.get(t.id)
        if o is not None and month_key(o.booking_date) != mk and "cash" not in (role, roles.get(o.account_uuid)):
            o = None                                     # e.g. loan and asset a month apart: no money in transit
        if o is not None and role == "cash":
            paired.add(t.id)                             # one side of a transfer: needs no category
        if o is not None and o.id not in seen_pair:
            seen_pair.update({t.id, o.id})
            if month_key(o.booking_date) != mk:                   # over a month end: money in transit
                out_, in_ = (t, o) if t.amount < 0 else (o, t)
                pairs.append((out_.booking_date, in_.booking_date, -out_.amount, out_.account_uuid, in_.account_uuid, out_.id, in_.id))
        p = partner.get(t.id)
        if role == "ignore":
            continue
        if role != "cash":
            if o is not None:
                continue                                 # the other side (or the bank account) shows the transfer
            own_row(t, acc, role, mk)
            continue
        if o is not None:                                # transfer within the area
            o_role = roles.get(o.account_uuid, "other")
            pacc = ledger.accounts[o.account_uuid]
            if o_role == "cash":
                continue
            if o_role in ASSET_LIKE:
                R.add("investing", row=pacc.name, mk=mk, amount=t.amount, account=pacc.uuid, kind="account", nw=False, **_grp(INVEST_GROUPS, o_role))
                inbound[pacc.uuid][mk] += -t.amount
            elif o_role == "receivables":
                R.add("investing", row=pacc.name + " / Rückzahlung", mk=mk, amount=t.amount, account=pacc.uuid, kind="payback", nw=False,
                      lbl=("cf_name", pacc.name), **_grp(INVEST_GROUPS, "receivables"))
            elif o_role == "liabilities" and t.amount > 0:      # paid out by the lender: a loan taken up (never "negative repayment")
                R.add("financing", row=pacc.name + " / Aufnahme", mk=mk, amount=t.amount, account=pacc.uuid, kind="drawdown", nw=False,
                      lbl=("cf_name", pacc.name), **_grp(FIN_GROUPS, "drawdown"))
            elif o_role == "liabilities":
                R.add("financing", row=pacc.name + " / Tilgung", mk=mk, amount=t.amount, account=pacc.uuid, kind="repayment", nw=False,
                      lbl=("cf_name", pacc.name), **_grp(FIN_GROUPS, "repayment"))
            else:
                R.add("unclear", "Umbuchung", "Umbuchung nach " + pacc.name, mk, t.amount, kind="unclear", tx=t.id,
                      lbl=("cf_umbuchung_mit", pacc.name), glbl=("cf_umbuchung",)); unclear += 1
            continue
        if p is not None and p in depots:               # into a depot valued by its balances: its valuation takes the rest
            pacc = ledger.accounts[p]
            R.add("investing", row=pacc.name, mk=mk, amount=t.amount, account=p, kind="account", nw=False, **_grp(INVEST_GROUPS, "securities"))
            inbound[p][mk] += -t.amount
            continue
        if p is not None and p in root_leaves:          # an account of the area, but its booking is missing
            R.add("unclear", "Umbuchung", "Umbuchung nach %s ohne Gegenbuchung" % ledger.accounts[p].name, mk, t.amount, kind="unclear", tx=t.id,
                  lbl=("cf_ohne_gegenbuchung", ledger.accounts[p].name), glbl=("cf_umbuchung",)); unclear += 1
            continue
        if p is not None and p in ledger.accounts and foreign_currency(ledger.accounts[p]):    # into another currency
            name = ledger.accounts[p].name
            R.add("investing", row="Fremdwährung " + name, mk=mk, amount=t.amount, account=p, kind="external", nw=True,
                  lbl=("cf_name", name), **_grp(INVEST_GROUPS, "foreign"))
            continue
        pa = areas.get(p) if p is not None else None
        same = pa is not None and pa == self_name
        guess = None
        if p is not None and not same and (pa is not None or p in beteiligungs_gruppen) and not by_cat[t.id]:
            # between two of your areas, but paid for something (a salary, rent): it counts in the position you chose for its
            # category or its name clearly says (not "other") -- without a category by the words of its purpose (estimated).
            # Everything else between areas is a contribution or withdrawal.
            c0, g0, yours = between_position(t)
            if paid_for(g0):
                p, guess = None, (None if c0 else g0)
            elif c0 and g0 is None and not yours:
                # a category Kontor does not know and you did not place: shown under "other" on the positions page, but between
                # your areas it counts as a contribution or withdrawal -- named there, so that the difference is no surprise
                unsure[c0] = unsure.get(c0, 0.0) + abs(t.amount)
        if p is not None and not same and p in beteiligungs_gruppen:   # a company: its participation (if held here) takes it
            g = beteiligungs_gruppen[p]
            st = stakes.get(g)
            cb = counter_booking(t, mk)                # booked against an account by you: that, else the participation
            if cb:
                counter_row(t, mk, g, cb)
            elif st:
                stake_in[st][mk] += -t.amount
                R.add("investing", row="Einlage/Entnahme " + g, mk=mk, amount=t.amount, account=st, kind="external", nw=False,
                      lbl=("cf_name", g), **_grp(INVEST_GROUPS, "participations"))
            else:
                R.add("investing", row="Einlage/Entnahme " + g, mk=mk, amount=t.amount, kind="external", nw=True,
                      lbl=("cf_name", g), **_grp(INVEST_GROUPS, "participations"))
            continue
        if p is not None and not same and pa is not None:             # another area of yours
            cb = counter_booking(t, mk)
            if cb:
                counter_row(t, mk, pa, cb)
            elif company:
                R.add("financing", row="Einlagen/Entnahmen Gesellschafter", mk=mk, amount=t.amount, kind="external", nw=True,
                      lbl=("cf_einlagen_gesellschafter",), **_grp(FIN_GROUPS, "partners"))
            else:
                R.add("investing", row="Einlage/Entnahme " + pa, mk=mk, amount=t.amount, kind="external", nw=True,
                      lbl=("cf_name", pa), **_grp(INVEST_GROUPS, "areas"))
            continue
        if p is not None:
            R.add("unclear", "Umbuchung", "Umbuchung nach " + ledger.accounts[p].path, mk, t.amount, kind="unclear", tx=t.id,
                  lbl=("cf_umbuchung_mit", ledger.accounts[p].path), glbl=("cf_umbuchung",)); unclear += 1
            continue
        if by_cat[t.id]:
            R.add("unclear", "Umbuchung", "Umbuchung ohne erkannten Partner", mk, t.amount, kind="unclear", tx=t.id,
                  lbl=("cf_ohne_partner",), glbl=("cf_umbuchung",)); unclear += 1
            continue
        # income and expenses: by position (MoneyMoney's category assigned to it), a property's in its own rows
        # without a category: the one your categories suggest (learned), else Kontor's estimate by the words -- shown as estimated
        sec = "income" if t.amount > 0 else "expenses"
        cat = norm_cat(t.category_path)
        mine = bool(cat)
        if not cat and learned and guess is None:
            hit = suggest_category(learned, t)
            cat = norm_cat(hit["category"]) if hit else ""
            if cat and is_transfer(cat):                 # learned from transfers: no estimate (a counterpart was not found)
                R.add(sec, "Ohne Kategorie", "Ohne Kategorie", mk, t.amount, ord=900, lbl=("cf_ohne_kategorie",))
                continue
        if cat:
            pos, obj = place(cat)
        else:
            pos, obj = guess or guess_position(t, company), None
            if pos == "housing" and company and objekte and t.amount < 0:    # a landlord: costs of the building
                pos = "property_costs"
        # an estimate only ever counts as income or expense (or interest) -- never as saving, repayment, transfer or left out
        if pos is None or pos not in POS or (not mine and pos in ("saving", "repayment", "ignore")):
            R.add(sec, "Ohne Kategorie", "Ohne Kategorie", mk, t.amount, ord=900, lbl=("cf_ohne_kategorie",))
            continue
        det = cat if mine else ""                        # "" = without a category in MoneyMoney (estimated)
        if obj:
            # rent or costs: by the category's sum (a subcategory such as "Hausgeld"); on the property's own category by the booking
            inc = (t.amount > 0) if cat in objekte else totals.get(cat, 0.0) > 0
            sec = "income" if inc else "expenses"
            row = "%s · %s" % (obj, "Miete" if inc else "Kosten")
            R.add(sec, row, row, mk, t.amount, ord=POS["rental" if inc else "property_costs"][2] + 0.5, property_name=obj, detail=det,
                  lbl=("cf_objekt_miete" if inc else "cf_objekt_kosten", obj))
            continue
        psec, prow, pord = POS[pos]
        if pos == "ignore":
            ignored[mk] += t.amount
            ignored_ids[mk].append(t.id)
        elif pos == "saving":
            # where it went: your choice for the recipient, else the category's account, else -- where no account is set for
            # the category -- the area's only depot (an account of another area does not count here). "extern": an account not
            # in MoneyMoney -- the money leaves the net worth. Without a known account the money goes out of the cash flow and
            # stands as "without target account" among the changes in value, where it takes out what a depot rose by it.
            key = party_key(t)
            parts = cat.split(" / ")
            c_to = next((kat_zu_konto[" / ".join(parts[:i])] for i in range(len(parts), 0, -1) if " / ".join(parts[:i]) in kat_zu_konto), None)
            e_to = emp_zu_konto.get(key)
            auto = (c_to, "category") if c_to in root_leaves else (depots[0], "depot") if len(depots) == 1 and not c_to else (None, "")
            target, how = (None, "external") if e_to == "external" else (e_to, "recipient") if e_to in root_leaves else auto
            kind = roles.get(target, "saving_group") if target else "saving_group"          # the kind of the account it goes into, else "saving"
            # one row per category -- what your choice per recipient sends elsewhere has a row of its own (its account, its
            # effect on the net worth); the category's row keeps its name (the key of your planning)
            zeile, lbl = cat, None
            if how == "external":
                zeile, lbl = cat + " → extern", ("cf_anlage_extern", cat)
            elif how == "recipient" and target != auto[0]:
                acc_t = ledger.accounts[target]                   # by its path where another account of the area has its name
                same = any(ledger.accounts[u].name == acc_t.name for u in root_leaves if u != target and u in ledger.accounts)
                zeile = "%s → %s" % (cat, acc_t.path if same else acc_t.name)
            R.add("investing", row=zeile, mk=mk, amount=t.amount, account=target, kind="category", nw=how == "external",
                  **({"lbl": lbl} if lbl else {}), **_grp(INVEST_GROUPS, kind if kind in INVEST_GROUPS else "saving_group"))
            if target in depots:
                inbound[target][mk] += -t.amount
            elif target and verlauf.get(target) == "balances" and roles.get(target) in ASSET_LIKE:
                mapped_in[target][mk] += -t.amount      # an asset kept by balances: paid in, not a correction of its balance
            elif not target and how != "external":
                no_target[mk] += t.amount
            sv = savings.get(key)
            if sv is None:
                sv = savings[key] = {"key": key, "name": (t.name or t.purpose or t.booking_text)[:80], "iban": (t.counter_iban or "").replace(" ", "").upper()[:34],
                                     "count": 0, "sum": 0.0, "date_from": t.booking_date.isoformat(), "date_to": t.booking_date.isoformat(),
                                     "categories": [], "target": target, "how": how, "auto_target": auto[0], "auto_how": auto[1], "ids": []}
            sv["count"] += 1
            if len(sv["ids"]) < 500:                   # the bookings behind it (a click shows them)
                sv["ids"].append(t.id)
            sv["sum"] = round(sv["sum"] + t.amount, 2)
            sv["date_from"], sv["date_to"] = min(sv["date_from"], t.booking_date.isoformat()), max(sv["date_to"], t.booking_date.isoformat())
            if cat not in sv["categories"]:
                sv["categories"].append(cat)
            if (sv["target"], sv["how"]) != (target, how):         # by category: the recipient's bookings may go to different accounts
                sv["how"], sv["target"] = "mixed", None
            if (sv["auto_target"], sv["auto_how"]) != auto:
                sv["auto_how"], sv["auto_target"] = "mixed", None
        elif pos in ("repayment", "loan_interest"):
            R.add("financing", row=prow, mk=mk, amount=t.amount, kind="interest" if pos == "loan_interest" else "repayment", nw=pos == "loan_interest",
                  lbl=("pos_" + pos,), detail=det, **_grp(FIN_GROUPS, "interest" if pos == "loan_interest" else "repayment"))
        else:
            row, key = position_row(pos, company)
            R.add(psec, row, row, mk, t.amount, ord=pord, lbl=(key,), detail=det)

    R.cur = None
    for u, fm, op in openings:
        acc = ledger.accounts[u]
        R.add("valuation", acc.name, acc.name + " / Anfangssaldo", fm, op, account=u, kind="opening", nw=True, lbl=("cf_anfangssaldo", acc.name))
    # a participation took a contribution: what it is worth more (or less) than the money paid in is its valuation
    for st, per in stake_in.items():
        acc = ledger.accounts[st]
        for mk, v in per.items():
            R.add("valuation", acc.name, acc.name, mk, -v, account=st, kind="account", nw=True)
    # saving whose account is unknown: out of the net worth Kontor sees, until you name the account (Cashflow-Positionen) --
    # where it did go into a depot, that depot's change in value holds it, and this row takes it out again
    for mk, v in no_target.items():
        if abs(v) >= 0.005:
            R.add("valuation", "Anlage ohne Zielkonto", "Anlage ohne Zielkonto", mk, round(v, 2), kind="no_target", nw=True,
                  lbl=("cf_anlage_ohne_ziel",), glbl=("cf_anlage_ohne_ziel",))

    if unclear:
        warnings.append(tr("s_d_umbuchung_en_ohne_erkennbaren") % unclear)
    R.pairs = pairs
    R.paired = paired
    R.reasons = {"ignored": dict(ignored), "ignored_ids": dict(ignored_ids)}
    R.mapped_in = {u: dict(v) for u, v in mapped_in.items()}
    R.saving_recipients = _savings_list(ledger, savings, depots)
    R.uncertain = {c: round(v, 2) for c, v in unsure.items() if abs(v) >= 0.005}
    return R, inbound, warnings


def _savings_list(ledger: Ledger, savings: Dict[str, dict], depots: List[str]) -> List[dict]:
    """The recipients of saving without a counter-booking, largest first, each with Kontor's proposal for its account where it
    is clear (not where you chose one): the one depot of the area at the bank of the recipient's IBAN, else the one whose name
    shares a word with the recipient's. Only a proposal -- it counts once you choose it."""
    generic = {"bank", "gmbh", "depot", "konto", "sparkasse", "volksbank", "capital", "invest", "verrechnungskonto", "wertpapiere"}
    words = lambda s: {w for w in re.sub(r"[^\wäöüß]+", " ", (s or "").lower()).split() if len(w) >= 4 and w not in generic}
    code = {u: re.sub(r"\D", "", ledger.accounts[u].bank_code or "") for u in depots}
    out = []
    for sv in sorted(savings.values(), key=lambda x: (-abs(x["sum"]), x["name"])):
        prop = None
        if sv["how"] not in ("recipient", "external") and len(depots) > 1:      # not where you chose
            at_bank = [u for u in depots if len(code[u]) >= 4 and sv["iban"][4:4 + len(code[u])] == code[u]]
            named = [u for u in depots if words(sv["name"]) & words(ledger.accounts[u].name)]
            prop = at_bank[0] if len(at_bank) == 1 else (named[0] if len(named) == 1 else None)
        out.append(dict(sv, proposal=prop if prop != sv["target"] else None))
    return out


# ---------------------------------------------------------------------------
# Bilanz je Bereich
# ---------------------------------------------------------------------------

def reconcile(sektionen: List[dict], nw: Dict[str, float], liq: Dict[str, Optional[float]], mkeys: List[str], leaves: List[Account],
              roles: Dict[str, str], hist: Dict[str, Dict[str, Optional[float]]], R: "Rows", ledger: Ledger, months: List[Tuple[int, int]],
              today: date, ids_out: Optional[Dict[str, Dict[str, List[int]]]] = None) -> Dict[str, dict]:
    """Check of the cash flow against the balance sheet, month by month: the rows that change the net worth add up to its change,
    the cash rows to the change of the liquid accounts (with money in transit). A difference is split into its reasons
    ([text key, amount, detail]); what no reason explains is shown as such -- never left out. ids_out (when given) gets the
    bookings behind the reasons, per check and month (left out; a transfer in transit: its side in the month)."""
    reasons = getattr(R, "reasons", None) or {}
    ignored = reasons.get("ignored") or {}
    ignored_ids = reasons.get("ignored_ids") or {}
    liquid = {a.uuid for a in leaves if roles.get(a.uuid) == "cash"}
    # transfers over a month end with a side that is no bank account: the bank side counts in its month, the money in transit
    # counts as liquid in the balance sheet until it arrives
    mixed = [p for p in (getattr(R, "pairs", None) or []) if not (p[3] in liquid and p[4] in liquid)]
    transit_mixed, _ = _transit_from(ledger, months, mkeys, mixed, today) if mixed else ({mk: 0.0 for mk in mkeys}, [])
    names = {a.uuid: a.name for a in leaves}
    out: Dict[str, dict] = {}
    for i, mk in enumerate(mkeys):
        if i == 0:
            continue
        prev = mkeys[i - 1]
        rows = [z for sek in sektionen for z in sek["rows"]]
        explained = round(sum(z["amounts"].get(mk, 0.0) for z in rows if z["nw"]), 2)
        cash = round(sum(z["amounts"].get(mk, 0.0) for sek in sektionen if sek["name"] in CASH_SECTIONS for z in sek["rows"]), 2)
        delta = round(nw[mk] - nw[prev], 2)
        dliq = round((liq.get(mk) or 0.0) - (liq.get(prev) or 0.0), 2)
        unknown = sorted(names[u] for u in names
                         if (hist.get(u, {}).get(mk) is None) != (hist.get(u, {}).get(prev) is None))
        g_nw: List[list] = []
        g_liq: List[list] = []
        if abs(ignored.get(mk, 0.0)) >= 0.005:
            g_nw.append(["ue_ignoriert", round(ignored[mk], 2), ""])
            g_liq.append(["ue_ignoriert", round(ignored[mk], 2), ""])
        tm = round(transit_mixed.get(mk, 0.0) - transit_mixed.get(prev, 0.0), 2)
        if abs(tm) >= 0.005:
            g_liq.append(["ue_unterwegs", tm, ""])
        for z in rows:
            if z["account"] in liquid and z["kind"] in ("correction", "depot", "opening") and abs(z["amounts"].get(mk, 0.0)) >= 0.005:
                g_liq.append([{"correction": "ue_korrektur", "opening": "ue_anfangssaldo"}.get(z["kind"], "ue_wert"), round(z["amounts"][mk], 2), names.get(z["account"], "")])

        def rest(gaps: List[list], total: float) -> None:
            left = round(total - sum(g[1] for g in gaps), 2)
            if abs(left) >= 0.01:
                gaps.append(["ue_unbekannt", left, ", ".join(unknown)] if unknown else ["ue_rest", left, ""])
        un = round(delta - explained, 2)
        ab = round(dliq - cash, 2)
        rest(g_nw, un)
        rest(g_liq, ab)
        ids_nw = list(ignored_ids.get(mk) or []) if abs(un) >= 0.01 and abs(ignored.get(mk, 0.0)) >= 0.005 else []
        ids_liq = list(ignored_ids.get(mk) or []) if abs(ab) >= 0.01 and abs(ignored.get(mk, 0.0)) >= 0.005 else []
        if abs(ab) >= 0.01 and abs(tm) >= 0.005:          # a transfer over a month end: the side booked in this month
            ids_liq += [i for p in mixed if len(p) > 6 for d, i in ((p[0], p[5]), (p[1], p[6])) if month_key(d) == mk and month_key(p[0]) != month_key(p[1])]
        if ids_out is not None:
            for k, v in (("check_cash", ids_liq), ("check_nw", ids_nw)):
                if v:
                    ids_out.setdefault("\u001f" + k, {})[mk] = v
        out[mk] = {"delta_nw": delta, "explained": explained, "unexplained": un, "reasons": g_nw if abs(un) >= 0.01 else [],
                   "delta_cash": dliq, "cash_flow_sum": cash, "diff_cash": ab, "reasons_cash": g_liq if abs(ab) >= 0.01 else [],
                   "n_liq": len(ids_liq), "n_nw": len(ids_nw)}
    return out


def build_dataset(ledger: Ledger, config: dict, state: dict, today: date, bereich: dict, roles: Dict[str, str],
                  rule_warnings: Optional[List[str]] = None, progress: Optional[Callable[[float, str], None]] = None,
                  learned: Optional[dict] = None) -> dict:
    """bereich: {"id", "name", "art", "anteil", "leaves": [Account]}; learned: patterns from your categories (categorize)"""
    step = progress or (lambda f, t: None)
    order = ledger.order()                      # Konten in der Reihenfolge von MoneyMoney
    bcfg = config.get("balance", {}) or {}
    leaves: List[Account] = [a for a in bereich["leaves"] if roles.get(a.uuid) not in OFF_BALANCE]
    # accounts in another currency: not converted (no exchange rates, no estimate) -- shown apart, in their currency
    foreign = [a for a in leaves if foreign_currency(a)]
    leaves = [a for a in leaves if not foreign_currency(a)]
    ausserhalb_accs = [a for a in bereich["leaves"] if roles.get(a.uuid) == "contingent"] + foreign
    leaf_ids = {a.uuid for a in leaves}
    back = int(bcfg.get("months_back", 0) or 0)
    if back <= 0:
        first_tx = min((t.booking_date for t in ledger.txs if t.account_uuid in leaf_ids), default=today)
        hist_cfg = state.get("history") or {}
        mm_cfg = state.get("history_mm") or {}
        first_hist = min((k for u in leaf_ids for k in list(hist_cfg.get(u) or {}) + list(mm_cfg.get(u) or {})), default=None)
        if first_hist and first_hist < month_key(first_tx):
            first_tx = date(int(first_hist[:4]), int(first_hist[5:]), 1)
        y0, m0 = first_tx.year, first_tx.month
    else:
        y0, m0 = add_months(today, -back)
    months = months_between(date(y0, m0, 1), today)
    mkeys = ["%04d-%02d" % ym for ym in months]
    snapshots = state.get("snapshots", {}) or {}
    historie = state.get("history", {}) or {}
    verlauf_cfg: Dict[str, str] = {}
    for ref, v in (bcfg.get("history_source") or {}).items():
        try:
            verlauf_cfg[ledger.resolve(ref).uuid] = v
        except KeyError:
            pass

    step(0.05, tr("s_monatsstaende"))
    historie_mm = state.get("history_mm") or {}
    hist, warn_h, quelle, fortgeschrieben = balance_history(ledger, leaves, months, snapshots, historie, verlauf_cfg, today, config, historie_mm,
                                                            state.get("history_mm_start") or {})
    step(0.3, tr("s_zahlungsstroeme"))
    areas = area_names(ledger, config)
    company = bereich.get("kind") == "company"
    learned_sig = None
    if learned:
        learned_sig = learned.get("_sig") or hashlib.sha1(json.dumps(learned.get("rules") or [], sort_keys=True, default=str).encode()).hexdigest()
    objekte = {str(im.get("category")): str(im.get("name") or "") for im in config.get("real_estate") or []
               if isinstance(im, dict) and im.get("category") and str(im.get("area") or "") == str(bereich.get("id"))}
    ckey = (getattr(ledger, "_kat_sig", None), str(bereich.get("id") or ""), back <= 0, tuple(a.uuid for a in leaves), json.dumps(roles, sort_keys=True),
            json.dumps(config.get("cashflow") or {}, sort_keys=True, default=str), tuple(months[0]) if months else None,
            tuple(months[-1]) if months else None, len(months), tuple(sorted(quelle.items())), company, learned_sig, tuple(sorted(objekte.items())),
            json.dumps([sorted(areas.items()), config.get("companies"), config.get("account_mirrors")], sort_keys=True, default=str))
    cache = ledger.__dict__.setdefault("_classify_cache", {})
    if ckey in cache:
        R, inbound, warn_c = copy.deepcopy(cache[ckey])        # Bereich unveraendert (z. B. Verlauf eines anderen Bereichs geaendert)
    else:
        R, inbound, warn_c = classify(ledger, leaves, roles, config, months, quelle, areas, company, objekte, learned, str(bereich.get("id") or ""))
        if len(cache) > 24:
            cache.clear()
        cache[ckey] = copy.deepcopy((R, inbound, warn_c))
    # bank bookings that are one side of a transfer in this area (Kategorien -> Zuordnen leaves them out)
    ledger.__dict__.setdefault("_paired", {})[str(bereich.get("id"))] = set(getattr(R, "paired", ()) or ())
    step(0.85, tr("x_bilanz"))
    inactive, inactive_auto = inactive_accounts(ledger, leaves, hist, mkeys, config, today, state.get("accounts_since"))
    limits = activity_limits(ledger, leaves, hist, mkeys, today, state.get("accounts_since"))

    # Konten mit Kontostaende-Verlauf: Depots -> Bewertung = Wertaenderung - Zufluesse;
    # andere Konten -> Korrektur = Saldoaenderung - eigene Buchungen (nur dort, wo ein eingetragener Stand abweicht)
    for acc in leaves:
        if quelle.get(acc.uuid) == "balances":
            h = hist[acc.uuid]
            own: Dict[str, float] = defaultdict(float)
            if not acc.portfolio:
                for t in ledger.transactions(acc.uuid):
                    own[month_key(t.booking_date)] += t.amount
            for i, mk in enumerate(mkeys):
                if i == 0:
                    continue
                delta = (h[mk] or 0.0) - (h[mkeys[i - 1]] or 0.0)
                if acc.portfolio:
                    val = round(delta - inbound[acc.uuid].get(mk, 0.0), 2)
                    if abs(val) >= 0.005:
                        R.add("valuation", acc.name, acc.name, mk, val, account=acc.uuid, kind="depot", nw=True)
                else:                                   # saving you sent there without a booking counts as paid in
                    val = round(delta - own.get(mk, 0.0) - ((getattr(R, "mapped_in", None) or {}).get(acc.uuid) or {}).get(mk, 0.0), 2)
                    if abs(val) >= 0.005:
                        R.add("valuation", acc.name, acc.name + " / Korrektur Kontostand", mk, val, account=acc.uuid, kind="correction", nw=True,
                              lbl=("cf_korrektur", acc.name))

    illiquid_roles = set(ILLIQUID_DEFAULT)      # fest nach Position (Liquiditaet und Wertpapiere gelten als verfuegbar)
    illiquid_refs: Set[str] = set()

    # Bilanzzeilen nach Positionen
    bilanz_rows: List[dict] = []
    pos_sums: Dict[str, Dict[str, float]] = {}
    for role in ROLES:
        if role in OFF_BALANCE:
            continue
        accs = [a for a in leaves if roles.get(a.uuid) == role]
        if not accs:
            continue
        werte = {mk: round(sum((hist[a.uuid][mk] or 0.0) for a in accs), 2) for mk in mkeys}
        pos_sums[role] = werte
        bilanz_rows.append({"id": "pos:" + role, "name": role_label(role), "path": role_label(role), "depth": 0, "group": True,
                            "role": role, "illiquid": role in illiquid_roles, "depot": False, "offline": False, "inactive": False,
                            "liabilities_side": role == "liabilities", "amounts": werte, "count": len(accs),
                            "inactive_list": sum(1 for a in accs if a.uuid in inactive)})
        for a in sorted(accs, key=lambda x: order.get(x.uuid, 10**9)):
            illiq = (role in illiquid_roles) or (a.uuid in illiquid_refs) or any(x.uuid in illiquid_refs for x in ledger.ancestors(a.uuid))
            row = {"id": a.uuid, "name": a.name, "path": a.path, "depth": 1, "group": False, "role": role,
                   "illiquid": illiq, "depot": a.portfolio, "offline": a.offline, "inactive": a.uuid in inactive,
                   "liabilities_side": role == "liabilities", "history_source": quelle.get(a.uuid, "transactions"), "projected_before": fortgeschrieben.get(a.uuid),
                   "amounts": {mk: hist[a.uuid][mk] for mk in mkeys}}
            if a.portfolio:
                wp = depot_holdings(a, row["amounts"], mkeys, today, state, (getattr(ledger, "portfolios", None) or {}).get(a.uuid), config)
                if wp:
                    row["securities"] = wp
            bilanz_rows.append(row)
    # Geld unterwegs (Umbuchung ueber das Monatsende) zaehlt zur Liquiditaet; sonst knickt das Nettovermoegen am Monatsende ein
    transit, transit_details = transit_series(ledger, leaves, roles, months, quelle, today, getattr(R, "pairs", None))
    if any(abs(v) >= 0.005 for v in transit.values()):
        grp = next((r for r in bilanz_rows if r["id"] == "pos:cash"), None)
        if grp is None:
            grp = {"id": "pos:cash", "name": role_label("cash"), "path": role_label("cash"), "depth": 0, "group": True,
                   "role": "cash", "illiquid": False, "depot": False, "offline": False, "inactive": False, "liabilities_side": False,
                   "amounts": {mk: 0.0 for mk in mkeys}, "count": 0, "inactive_list": 0}
            bilanz_rows.insert(0, grp)
            pos_sums = {"cash": grp["amounts"], **pos_sums}
        idx = max(i for i, r in enumerate(bilanz_rows) if r["role"] == "cash") + 1
        bilanz_rows.insert(idx, {"id": "transit", "name": tr("s_geld_unterwegs"), "path": tr("s_geld_unterwegs"), "depth": 1, "group": False,
                                 "role": "cash", "transit": True, "illiquid": False, "depot": False, "offline": False, "inactive": False,
                                 "liabilities_side": False, "amounts": dict(transit), "transfers": transit_details})
        for mk in mkeys:
            grp["amounts"][mk] = round((grp["amounts"][mk] or 0.0) + transit[mk], 2)
    nw = {mk: round(sum(pos_sums[r][mk] for r in pos_sums), 2) for mk in mkeys}
    aktiva = {mk: round(sum(pos_sums[r][mk] for r in pos_sums if r != "liabilities"), 2) for mk in mkeys}
    passiva = {mk: round(pos_sums.get("liabilities", {}).get(mk, 0.0), 2) for mk in mkeys}
    liquid_nw = {mk: round(nw[mk] - sum((r["amounts"][mk] or 0.0) for r in bilanz_rows if not r["group"] and r["illiquid"]), 2) for mk in mkeys}
    # Ausserhalb des Nettovermoegens: Kapitalkonten (Eigenkapital) und Avale/Buergschaften -- nur zur Information
    ausserhalb = []
    out_role = lambda a: "foreign_currency" if foreign_currency(a) else roles.get(a.uuid)
    for a in sorted(ausserhalb_accs, key=lambda x: (out_role(x) or "", order.get(x.uuid, 10**9))):
        wh, _, _ = account_balance_series(ledger, a, months, verlauf_quelle(a, verlauf_cfg), snapshots, historie.get(a.uuid) or {}, today, config,
                                             historie_mm.get(a.uuid), (state.get("history_mm_start") or {}).get(a.uuid))
        ausserhalb.append({"id": a.uuid, "name": a.name, "path": a.path, "role": out_role(a), "currency": a.currency or "EUR",
                           "amounts": {mk: wh[mk] for mk in mkeys}})

    # Kapitalfluss-Sektionen
    sektionen = []
    cf_ids: Dict[str, Dict[str, List[int]]] = {}         # "section\x1frow" -> month -> bookings (saved apart from the dataset)
    for sec in SECTIONS:
        zeilen = []
        for (s, row), vals in R.vals.items():
            if s != sec:
                continue
            m = R.meta[(s, row)]
            if s == "valuation" and m["kind"] == "account" and all(abs(vals.get(mk, 0.0)) < 0.005 for mk in mkeys):
                continue                                 # an account whose bookings all went with a payment (a contribution booked against it)
            z = {"row": row, "group": m["group"], "account": m["account"], "kind": m["kind"], "nw": m["nw"],
                 "amounts": {mk: round(vals.get(mk, 0.0), 2) for mk in mkeys}}
            for k in ("lbl", "glbl", "ord", "property_name"):
                if m.get(k) is not None:
                    z[k] = m[k]
            ids = R.ids.get((s, row))
            if ids:                                      # how many bookings per month (the ids themselves: kept apart, fetched on a click)
                z["n"] = {mk: len(v) for mk, v in ids.items() if v}
                cf_ids[s + "\u001f" + row] = {mk: list(v) for mk, v in ids.items() if v}
            det = R.det.get((s, row))
            if det:                                      # the categories inside a position (largest first)
                z["details"] = sorted(({"category": c, "amounts": {mk: round(v.get(mk, 0.0), 2) for mk in mkeys}} for c, v in det.items()),
                                      key=lambda d: -abs(sum(d["amounts"].values())))
            zeilen.append(z)
        gsum = defaultdict(float)
        gcount = defaultdict(int)
        for z in zeilen:
            gsum[z["group"]] += abs(sum(z["amounts"].values()))
            gcount[z["group"]] += 1
        for z in zeilen:                                 # e.g. "Tilgung" by category beside the loans of the group "Tilgung"
            if sec in ("investing", "financing") and gcount[z["group"]] > 1 and z["row"] == z["group"] and not z.get("account") \
                    and z["kind"] in ("repayment", "interest", "category"):
                z["lbl"] = ["cf_per_kategorie"]
        # the fixed outline first (positions in their order), then the rest by size
        zeilen.sort(key=lambda z: (z.get("ord", 500), -gsum[z["group"]], z["group"], z["row"]))
        sektionen.append({"name": sec, "rows": zeilen})

    ueberleitung = reconcile(sektionen, nw, pos_sums.get("cash") or {}, mkeys, leaves, roles, hist, R, ledger, months, today, cf_ids)

    loans_cfg = {}
    for l in config.get("loans", []) or []:
        try:
            a = ledger.resolve(l["loan_account"])
            z = l.get("interest") or {}
            loans_cfg[a.uuid] = {"name": a.name, "model": z.get("model", "yearly_base"), "rate_list": z.get("rate_list") or [], "kind": l.get("kind", "liability")}
        except KeyError:
            pass

    # accounts saving can go into without a booking there (Cashflow-Positionen: the account per recipient): kept by balances
    anlage_ziele = [a.uuid for a in sorted(leaves, key=lambda x: order.get(x.uuid, 10**9))
                    if quelle.get(a.uuid) == "balances" and roles.get(a.uuid) in ASSET_LIKE]
    warnings = list(rule_warnings or []) + warn_h + warn_c
    if foreign:
        warnings.append(tr("s_fremdwaehrung", ", ".join("%s (%s)" % (a.name, a.currency) for a in foreign)))
    return {
        "created": today.isoformat(),
        "today": today.isoformat(),
        "months": mkeys,
        "actual_until": month_key(today),
        "area": {"id": bereich["id"], "name": bereich["name"], "kind": bereich.get("kind"), "share": bereich.get("share")},
        "balance": {"rows": bilanz_rows, "net_worth": nw, "assets": aktiva, "liabilities_side": passiva,
                   "liquid_net_worth": liquid_nw, "positions": {r: role_label(r) for r in pos_sums}, "outside": ausserhalb},
        "cashflow": {"sections": sektionen, "reconciliation": ueberleitung, "saving_recipients": list(getattr(R, "saving_recipients", None) or []),
                         "uncertain": dict(getattr(R, "uncertain", None) or {}),
                         "saving_targets": anlage_ziele, "cf_ids": cf_ids},
        "loan_config": loans_cfg,
        "accounts_inactive": sorted(inactive),
        "accounts_inactive_auto": sorted(inactive_auto),
        "accounts_activity": limits,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Planung
# ---------------------------------------------------------------------------

def shareholder_ids(ledger: Ledger) -> Set[str]:
    """Capital and shareholder accounts (by their own name, otherwise their group's): the partners' equity in a company."""
    out: Set[str] = set()

    def walk(acc: Account, inherited: bool):
        own = _hint_role(acc.name)
        here = own == "capital_amount" or (own is None and inherited)
        if not acc.group and here:
            out.add(acc.uuid)
        for c in acc.children:
            walk(ledger.accounts[c], here)

    for root in ledger.roots():
        walk(root, False)
    return out


def equity_ratio(ledger: Ledger, config: dict, roles: Dict[str, str], bereiche: List[dict], datasets: Dict[str, dict]) -> None:
    """Equity ratio looking through the companies (alpha): equity / (equity + debts) per month, written to
    ds["bilanz"]["ek_quote"] with every part, so the calculation can be followed in the interface.

    - Debts: accounts with a negative balance -- not participations (their debts come in through the look-through) and not
      capital or shareholder accounts (equity of the partners, also as loans) -- plus, for each company linked by a
      participation (Booking rules: company area, participation account, share of the area), the share of that company's
      debts, counted the same way (also through its own participations).
    - Equity: net worth; in a company area also the capital and shareholder accounts owed to the partners.
    - The way capital accounts are booked (receivables or participations, one account or two) does not matter: net worth
      stays the same and they are never debts. A company whose accounts are in no area: unknown (nothing is estimated).
    """
    vals: Dict[str, Dict[str, Optional[float]]] = {}
    for ds in datasets.values():
        for r in (ds.get("balance") or {}).get("rows") or []:
            if not r.get("group") and r.get("id") and isinstance(r.get("amounts"), dict):
                vals.setdefault(r["id"], r["amounts"])
    sh = shareholder_ids(ledger)
    links: List[dict] = []
    by_id = {b["id"]: b for b in bereiche}
    for e in config.get("companies") or []:
        b = by_id.get(str((e or {}).get("area")))
        if not b or not e.get("participation") or b.get("share") is None:
            continue
        try:
            tgt = ledger.resolve(e["participation"])
        except (KeyError, TypeError, AttributeError):
            continue
        if tgt.group:
            continue
        accs = [a for a in b["leaves"] if roles.get(a.uuid) not in OFF_BALANCE]
        links.append({"n": len(links), "target": tgt.uuid, "name": b["name"], "share": float(b["share"]), "accounts": accs})
    targets = {lk["target"] for lk in links}

    def look(accs: List[Account], mk: str, seen: frozenset) -> dict:
        ids = {a.uuid for a in accs}
        own, konten, unknown = 0.0, [], []
        for a in accs:
            if a.uuid in sh or a.uuid in targets or roles.get(a.uuid) == "participations":
                continue
            w = vals.get(a.uuid)
            if w is None:
                unknown.append(a.name)
                continue
            v = w.get(mk) or 0.0
            if v < -0.005:
                own += -v
                konten.append([a.name, round(-v, 2)])
        firmen = []
        for lk in links:
            if lk["target"] not in ids or lk["n"] in seen:
                continue
            sub = look(lk["accounts"], mk, seen | {lk["n"]})
            unknown += sub["unknown"]
            firmen.append({"name": lk["name"], "share": lk["share"], "debts": sub["sum"], "pro_rata": round(lk["share"] * sub["sum"], 2),
                           "accounts": sub["accounts"] + [[t["name"], t["pro_rata"]] for t in sub["businesses"]]})
        return {"own": round(own, 2), "accounts": sorted(konten, key=lambda x: -x[1]), "businesses": firmen, "unknown": unknown,
                "sum": round(own + sum(f["pro_rata"] for f in firmen), 2)}

    for b in bereiche:
        ds = datasets.get(b["id"]) or {}
        if "balance" not in ds:
            continue
        accs = [a for a in b["leaves"] if roles.get(a.uuid) not in OFF_BALANCE]
        nw = ds["balance"].get("net_worth") or {}
        ohne = sorted({a.name for a in accs if roles.get(a.uuid) == "participations" and a.uuid not in targets and a.uuid not in sh})
        monate = {}
        for mk in ds.get("months") or []:
            r = look(accs, mk, frozenset())
            kap = 0.0 if b.get("main_area") else sum(max(0.0, -((vals.get(a.uuid) or {}).get(mk) or 0.0)) for a in accs if a.uuid in sh)
            ek = round((nw.get(mk) or 0.0) + kap, 2)
            den = ek + r["sum"]
            monate[mk] = {"quote": round(ek / den, 4) if den > 0.005 and not r["unknown"] else None, "equity_value": ek, "nw": nw.get(mk),
                          "capital_amount": round(kap, 2), "debts": r["sum"], "own": r["own"], "accounts": r["accounts"], "businesses": r["businesses"],
                          "unknown": sorted(set(r["unknown"]))}
        ds["balance"]["equity_ratio"] = {"months": monate, "without_lookthrough": ohne}


def _rate_at(rates: List[dict], day: date) -> Optional[float]:
    best = None
    for r in sorted(rates, key=lambda x: x.get("from_date", "0000-00-00")):
        ab = date.fromisoformat(r["from_date"]) if r.get("from_date") else date(1900, 1, 1)
        if ab <= day:
            best = float(r["percent"])
    return best


def _plan_value(method: str, hist_vals: List[float], same_month_last_year: Optional[float], betrag: Optional[float],
                budget: Optional[float] = None) -> float:
    if method == "none":
        return 0.0
    if method == "budget":
        return float(budget or 0.0)
    if method == "fix":
        return float(betrag or 0.0)
    if method == "yearly_amount":
        return round(float(betrag or 0.0) / 12.0, 2)
    if method == "prev_year":
        return float(same_month_last_year or 0.0)
    n = 6 if method == "rolling6" else 12
    vals = hist_vals[-n:]
    return round(sum(vals) / n, 2) if vals else 0.0


def _event_months(ev: dict, future: List[str]) -> List[str]:
    start = str(ev.get("month") or "")[:7]
    if len(start) != 7:
        return []
    rep = ev.get("recurrence") or "once"
    bis = str(ev.get("date_to") or "")[:7] or future[-1]
    out = []
    for mk in future:
        if mk < start or mk > bis:
            continue
        if rep == "once" and mk != start:
            continue
        if rep == "yearly" and mk[5:] != start[5:]:
            continue
        if rep == "quarterly" and (int(mk[5:]) - int(start[5:])) % 3 != 0:
            continue
        out.append(mk)
    return out


def apply_plan(dataset: dict, plan: dict, config: dict, fremd_nw: Optional[Dict[str, Dict[str, float]]] = None,
               immo: Optional[List[dict]] = None, ledger_resolve=None) -> dict:
    """Planung auf einen Bereichs-Datensatz anwenden (in place).
    fremd_nw: Nettovermoegensplan anderer Bereiche (id -> {mk: nw}) fuer Beteiligungskonten.
    immo: Immobilienkalkulationen dieses Bereichs mit Planreihen (siehe realestate.planreihen) und Zuordnungen."""
    horizon = max(1, min(240, int(plan.get("horizon_months", 24))))
    default_method = plan.get("default_method", "rolling12")
    inflation = float(plan.get("inflation_percent_pa", 2.0) or 0.0)
    growth_default = {"expenses": float(plan.get("expense_increase_percent_pa", inflation) if plan.get("expense_increase_percent_pa") is not None else inflation),
                      "income": float(plan.get("income_increase_percent_pa") or 0.0)}
    rendite = float(plan.get("return_percent_pa") or 0.0)
    budgets: Dict[str, float] = dataset.get("budgets") or {}
    rows_cfg: Dict[str, dict] = dict(plan.get("rows", {}) or {})
    row_of_cat: Dict[str, str] = {}               # category -> the row it counts in (budgets of a category above several rows)
    for sek in dataset.get("cashflow", {}).get("sections", []):
        for z in sek["rows"]:
            for d in z.get("details") or []:
                if d["category"]:
                    row_of_cat[d["category"]] = sek["name"] + "/" + z["row"]

    def position_budget(key: str, z: dict) -> Optional[float]:
        """A position's budget: the budgets in MoneyMoney of its categories -- a budget on a category above them counts when
        all of its categories are in this row (then those below it do not count again)."""
        cats = [d["category"] for d in z.get("details") or [] if d["category"]]
        if not cats:
            return budgets.get(z["row"])
        own = {b: v for b, v in budgets.items()
               if any(c == b or c.startswith(b + " / ") for c in cats)
               and all(r == key for c, r in row_of_cat.items() if c == b or c.startswith(b + " / "))}
        own = {b: v for b, v in own.items() if not any(a != b and b.startswith(a + " / ") for a in own)}
        return round(sum(own.values()), 2) if own else None
    loans_plan: Dict[str, dict] = plan.get("loans", {}) or {}
    wert_cfg: Dict[str, dict] = plan.get("appreciation", {}) or {}
    events: List[dict] = [e for e in (plan.get("events") or []) if isinstance(e, dict) and e.get("active", True)]
    ist = dataset["months"]
    cur = dataset["actual_until"]
    full_months = [mk for mk in ist if mk < cur]
    y, m = int(cur[:4]), int(cur[5:])
    future = []
    for _ in range(horizon):
        y, m = add_months(date(y, m, 1), 1)
        future.append("%04d-%02d" % (y, m))
    while m != 12:                                       # letztes Planjahr immer vollstaendig
        y, m = add_months(date(y, m, 1), 1)
        future.append("%04d-%02d" % (y, m))
    dataset["plan_months"] = future
    sektionen = dataset["cashflow"]["sections"]
    rows_b = dataset["balance"]["rows"]
    leaf_rows = [r for r in rows_b if not r["group"]]
    by_uuid = {r["id"]: r for r in leaf_rows}
    by_name = {r["name"]: r for r in leaf_rows}
    loans_cfg = dataset.get("loan_config", {})
    sec_by_name = {s["name"]: s for s in sektionen}

    def resolve_ref(ref: Optional[str]) -> Optional[str]:
        if not ref:
            return None
        u = ref.split("|", 1)[0].strip()
        if u in by_uuid:
            return u
        label = ref.split("|", 1)[1].strip() if "|" in ref else ref
        if label in by_name:
            return by_name[label]["id"]
        if ledger_resolve:
            try:
                return ledger_resolve(ref).uuid
            except KeyError:
                return None
        return None

    # 0. Immobilienkalkulationen: Zuordnung Zeilen -> Reihen
    immo_rows: Dict[Tuple[str, str], Dict[str, float]] = {}      # (Sektion, Zeile) -> {mk: wert}
    immo_loans: Dict[str, dict] = {}                              # konto uuid -> {"zins": {mk}, "tilgung": {mk}, "saldo": {mk}}
    immo_wert: Dict[str, Dict[str, float]] = {}                   # objekt konto -> {mk: wert}
    immo_extra: List[dict] = []                                   # zusaetzliche Zeilen (Kalkulation ohne Ist-Zeile)
    payout: Dict[str, float] = {}                                 # geplante Ausschuettungen aller Objekte je Monat
    for im in immo or []:
        reihen = im.get("series_data") or {}
        name = str(im.get("name") or "Immobilie")
        rent = reihen.get("rent", {})
        costs = {mk: reihen.get("costs", {}).get(mk, 0.0) + reihen.get("reserve", {}).get(mk, 0.0) for mk in future}
        # the property's own rows (its categories, classify: objekt) take the calculation; without actual figures new rows
        for sec_name, row, series, key in (("income", "%s · Miete" % name, rent, "cf_objekt_miete"), ("expenses", "%s · Kosten" % name, costs, "cf_objekt_kosten")):
            if not im.get("category"):
                continue
            if any(z.get("property_name") == name for z in sec_by_name[sec_name]["rows"]):
                for z in sec_by_name[sec_name]["rows"]:
                    if z.get("property_name") == name:
                        immo_rows[(sec_name, z["row"])] = series
            else:
                immo_extra.append({"section": sec_name, "group": row, "row": row, "kind": "property", "nw": True, "amounts": series,
                                   "property_name": name, "lbl": [key, name]})
        for lname, ref in (im.get("loan_accounts") or {}).items():
            u = resolve_ref(ref)
            if u and lname in (reihen.get("loans") or {}):
                immo_loans[u] = reihen["loans"][lname]
        ou = resolve_ref(im.get("property_account"))
        if ou and reihen.get("value"):
            immo_wert[ou] = reihen["value"]
        if reihen.get("distribution") and any(abs(v) > 0.005 for v in reihen["distribution"].values()):
            for mk, v in reihen["distribution"].items():     # money to the partners: the row of their contributions/withdrawals
                payout[mk] = payout.get(mk, 0.0) + v
    if payout:
        own = "Einlagen/Entnahmen Gesellschafter"
        if any(z["row"] == own for z in sec_by_name["financing"]["rows"]):
            immo_rows[("financing", own)] = payout
        else:
            immo_extra.append({"section": "financing", "group": own, "row": own, "kind": "external", "nw": True,
                               "amounts": payout, "lbl": ["cf_einlagen_gesellschafter"], "glbl": ["cf_einlagen_gesellschafter"], "ord": FIN_GROUPS["partners"][2]})
    for ex in immo_extra:
        sek = sec_by_name[ex["section"]]
        sek["rows"].append(dict({"row": ex["row"], "group": ex["group"], "account": None, "kind": ex["kind"], "nw": ex["nw"],
                                   "amounts": {mk: 0.0 for mk in ist}, "synthetic": True},
                                  **{k: ex[k] for k in ("property_name", "lbl", "glbl", "ord") if ex.get(k)}))
        immo_rows[(ex["section"], ex["row"])] = ex["amounts"]
    fixed_rows: Dict[Tuple[str, str], Tuple[Dict[str, float], str]] = {k: (v, "property") for k, v in immo_rows.items()}

    # 0b. Ereignisse: Zeilen anlegen
    event_moves: Dict[str, List[Tuple[Optional[str], Optional[str], float]]] = defaultdict(list)   # mk -> [(von, nach, betrag)]
    liquid_ids = {r["id"] for r in leaf_rows if r["role"] == "cash"}
    event_rows: Dict[Tuple[str, str], Dict[str, float]] = {}
    for ev in events:
        betrag = float(str(ev.get("amount") or 0).replace(",", ".") or 0)
        months_ = _event_months(ev, future)
        if not betrag or not months_:
            continue
        art = ev.get("kind") or "reallocation"
        text = ev.get("text") or "Ereignis"
        von = resolve_ref(ev.get("date_from"))
        nach = resolve_ref(ev.get("after"))
        if art in ("income", "expense"):
            sec = "income" if art == "income" else "expenses"
            key = (sec, "Ereignis: " + text)
            event_rows.setdefault(key, {})
            for mk in months_:
                event_rows[key][mk] = event_rows[key].get(mk, 0.0) + (betrag if art == "income" else -betrag)
            continue
        von_liq = von is None or von in liquid_ids
        nach_liq = nach is None or nach in liquid_ids
        for mk in months_:
            if not von_liq and von in by_uuid:
                event_moves[mk].append((von, None, betrag))
            if not nach_liq and nach in by_uuid:
                event_moves[mk].append((None, nach, betrag))
        if von_liq != nach_liq:
            other = nach if von_liq else von
            orow = by_uuid.get(other, {})
            sec = "financing" if orow.get("role") == "liabilities" else "investing"
            key = (sec, "Ereignis: " + text)
            event_rows.setdefault(key, {})
            for mk in months_:
                event_rows[key][mk] = event_rows[key].get(mk, 0.0) + (-betrag if von_liq else betrag)
    for (sec, zeile), vals in event_rows.items():
        sek = sec_by_name[sec]
        sek["rows"].append({"row": zeile, "group": "Geplante Ereignisse", "account": None, "kind": "event",
                              "nw": sec in ("income", "expenses"), "amounts": {mk: 0.0 for mk in ist}, "synthetic": True})
        fixed_rows[(sec, zeile)] = (vals, "event")

    # 1. Planwerte je Zeile
    for sek in sektionen:
        for z in sek["rows"]:
            key = sek["name"] + "/" + z["row"]
            cfg = rows_cfg.get(key, {})
            fx = fixed_rows.get((sek["name"], z["row"]))
            fixed = fx[0] if fx else None
            if fx:
                method = fx[1]
            elif cfg.get("method"):
                method = cfg["method"]
            elif sek["name"] in ("valuation", "unclear") or z.get("kind") in ("external", "drawdown"):     # contributions/withdrawals, loans taken up: one-offs
                method = "none"
            elif sek["name"] == "investing" and z.get("kind") in ("external", "account", "payback", "interest"):
                method = "none" if z.get("kind") in ("external", "account") else default_method
            else:
                method = default_method
            growth = float(cfg.get("increase_percent_pa", growth_default.get(sek["name"], 0.0)))
            hist_vals = [z["amounts"][mk] for mk in full_months]
            overrides = cfg.get("amounts", {}) or {}
            # a position's budget: the sum of the budgets of its categories in MoneyMoney
            budget = position_budget(sek["name"] + "/" + z["row"], z)
            if budget is not None and sek["name"] == "expenses":
                budget = -abs(budget)
            z["plan"] = {"method": method, "amount": cfg.get("amount"), "increase_percent_pa": growth, "budget": budget,
                         "amounts": {}, "proposal": {}, "overwritten": sorted(k for k in overrides if k in future)}
            if fixed is not None:
                for mk in future:
                    v = round(float(fixed.get(mk, 0.0)), 2)
                    z["plan"]["proposal"][mk] = v
                    z["plan"]["amounts"][mk] = float(overrides[mk]) if mk in overrides else v
                continue
            base_val = _plan_value(method, hist_vals, None, cfg.get("amount"), budget)
            for i, mk in enumerate(future):
                if method == "prev_year":
                    ly = "%04d-%02d" % (int(mk[:4]) - 1, int(mk[5:]))
                    v = z["amounts"].get(ly, z["plan"]["amounts"].get(ly, 0.0)) * (1 + growth / 100.0)
                else:
                    v = base_val * ((1 + growth / 100.0) ** ((i + 1) / 12.0))
                z["plan"]["proposal"][mk] = round(v, 2)
                z["plan"]["amounts"][mk] = float(overrides[mk]) if mk in overrides else round(v, 2)

    # 2. Darlehensplan
    fin = sec_by_name["financing"]
    loan_groups: Dict[str, Dict[str, dict]] = defaultdict(dict)
    for z in fin["rows"]:
        if z.get("account") and (z.get("lbl") or [""])[0] != "cf_einlage_auf":    # a loan paid between your areas: planned with its account below
            loan_groups[z["account"]][z["kind"]] = z
    loan_state: Dict[str, dict] = {}
    for uuid, parts in loan_groups.items():
        acc = by_uuid.get(uuid)
        if acc is None:
            continue
        name = acc["name"]
        if uuid in immo_loans:
            series = immo_loans[uuid]
            for part, key in (("interest", "interest"), ("repayment", "repayment")):
                z = parts.get(part)
                if z:
                    for mk in future:
                        v = round(float(series.get(key, {}).get(mk, 0.0)), 2)
                        z["plan"]["proposal"][mk] = v
                        if mk not in (rows_cfg.get("financing/" + z["row"], {}).get("amounts") or {}):
                            z["plan"]["amounts"][mk] = v
                    z["plan"]["method"] = "property"
            continue
        lp = dict(loans_cfg.get(uuid, {}))
        lp.update(loans_plan.get(name, {}))
        rate = None
        if lp.get("interest_percent_pa") is not None:
            rate = float(lp["interest_percent_pa"])
        elif lp.get("rate_list"):
            rate = _rate_at(lp["rate_list"], date(int(future[0][:4]), int(future[0][5:]), 1))
        if rate is None:
            continue
        tilg, zins = parts.get("repayment"), parts.get("interest")
        pay_hist = [(tilg["amounts"][mk] if tilg else 0.0) + (zins["amounts"][mk] if zins else 0.0) for mk in full_months[-12:]]
        payment = float(lp.get("payment") or (round(-sum(pay_hist) / len(pay_hist), 2) if pay_hist else 0.0))
        loan_state[uuid] = {"rate": rate, "payment": payment, "model": lp.get("model", "remaining_debt_monthly"),
                            "repay": tilg, "interest": zins, "name": name,
                            "ov_t": (rows_cfg.get("financing/" + tilg["row"], {}).get("amounts") or {}) if tilg else {},
                            "ov_z": (rows_cfg.get("financing/" + zins["row"], {}).get("amounts") or {}) if zins else {}}

    # 3. Fortschreibung je Konto
    liq_total = {mk: round(sum((r["amounts"][mk] or 0.0) for r in leaf_rows if r["role"] == "cash"), 2) for mk in ist}
    bal: Dict[str, float] = {r["id"]: (r["amounts"][ist[-1]] or 0.0) for r in leaf_rows}
    year_base: Dict[str, Dict[int, float]] = defaultdict(dict)
    for r in leaf_rows:
        if r["role"] == "cash":
            continue
        for mk in ist:
            if mk.endswith("-12"):
                year_base[r["id"]][int(mk[:4]) + 1] = r["amounts"][mk] or 0.0
    counter_rows = [z for sek in sektionen for z in sek["rows"] if (z.get("lbl") or [""])[0] == "cf_einlage_auf"]
    inv_rows = [z for sek in sektionen if sek["name"] == "investing" for z in sek["rows"] if z not in counter_rows]
    growth_of: Dict[str, Tuple[float, Optional[float]]] = {}
    fremd_link: Dict[str, Tuple[str, float]] = {}
    for r in leaf_rows:
        w = wert_cfg.get(r["name"]) or wert_cfg.get(r["path"]) or wert_cfg.get(r["id"])
        if w and w.get("area"):
            fremd_link[r["id"]] = (str(w["area"]), float(w.get("share", 1.0)))
        elif w and (w.get("percent_pa") not in (None, "") or w.get("base") not in (None, "")):
            growth_of[r["id"]] = (float(w.get("percent_pa") or 0.0), (float(w["base"]) if w.get("base") not in (None, "") else None))
        elif rendite and (r["depot"] or r["role"] in ("securities", "term_investments")):
            growth_of[r["id"]] = (rendite, None)

    plan_rows: Dict[str, Dict[str, float]] = defaultdict(dict)
    einlagen_plan: Dict[str, float] = {}
    for mk in future:
        yr, mo = int(mk[:4]), int(mk[5:])
        # Ereignisse: Umschichtungen zwischen Konten (vor den Zinsen des Monats)
        for von, nach, betrag in event_moves.get(mk, []):
            if von in bal:
                bal[von] = round(bal[von] - betrag, 2)
            if nach in bal:
                b = bal[nach]
                nb = b + betrag
                if b < 0 < nb:      # Verbindlichkeit nicht ueber null hinaus tilgen
                    nb = 0.0
                bal[nach] = round(nb, 2)
        # Darlehen aufgenommen (geplant): die Schuld steigt, vor den Zinsen des Monats
        for uuid, parts in loan_groups.items():
            z = parts.get("drawdown")
            if z and uuid in bal and uuid not in immo_loans:
                bal[uuid] = round(bal[uuid] - z["plan"]["amounts"].get(mk, 0.0), 2)
        # Darlehen mit Zinsmodell
        for uuid, st in loan_state.items():
            b = bal[uuid]
            sign = -1.0 if b < 0 else 1.0
            if st["model"] == "yearly_base":
                if yr not in year_base[uuid]:
                    year_base[uuid][yr] = b
                base = abs(year_base[uuid][yr])
            else:
                base = abs(b)
            interest = round(base * st["rate"] / 1200.0, 2) if abs(b) > 0.005 else 0.0
            principal = min(max(st["payment"] - interest, 0.0), abs(b))
            if st["interest"]:
                st["interest"]["plan"]["proposal"][mk] = round(sign * interest, 2)
                if mk in st["ov_z"]:
                    interest = abs(float(st["ov_z"][mk]))
                st["interest"]["plan"]["amounts"][mk] = round(sign * interest, 2)
                st["interest"]["plan"]["method"] = "loans"
            if st["repay"]:
                st["repay"]["plan"]["proposal"][mk] = round(sign * principal, 2)
                if mk in st["ov_t"]:
                    principal = min(abs(float(st["ov_t"][mk])), abs(b))
                st["repay"]["plan"]["amounts"][mk] = round(sign * principal, 2)
                st["repay"]["plan"]["method"] = "loans"
            bal[uuid] = round(b - sign * principal, 2)
            if mo == 12:
                year_base[uuid][yr + 1] = bal[uuid]
        # Darlehen aus Immobilienkalkulation: Saldo direkt aus der Kalkulation
        for uuid, series in immo_loans.items():
            if uuid in bal and mk in (series.get("balance_amount") or {}):
                bal[uuid] = round(float(series["balance_amount"][mk]), 2)
        # Darlehen ohne bekannten Zinssatz: Saldo folgt der geplanten Tilgungszeile
        for uuid, parts in loan_groups.items():
            if uuid in loan_state or uuid in immo_loans or uuid not in bal or not parts.get("repayment"):
                continue
            tilg = parts["repayment"]
            v = tilg["plan"]["amounts"].get(mk, 0.0)
            b = bal[uuid]
            nb = b - v
            if (b < 0 < nb) or (b > 0 > nb):
                nb = 0.0
                tilg["plan"]["amounts"][mk] = round(b, 2)
            bal[uuid] = round(nb, 2)
        # Investitionen in Konten (a contribution booked against your capital account: that account)
        for z in inv_rows + counter_rows:
            v = z["plan"]["amounts"].get(mk, 0.0)
            if z.get("account") in bal and (z["kind"] in ("account", "category", "payback") or z in counter_rows):
                bal[z["account"]] = round(bal[z["account"]] - v, 2)
            elif z["kind"] == "external":
                einlagen_plan[mk] = einlagen_plan.get(mk, 0.0) - v
        # Wertentwicklung / Kalkulation / Beteiligung an anderem Bereich
        for uuid, (pct, basis) in growth_of.items():
            if uuid in bal and pct and uuid not in immo_wert:
                bal[uuid] = round(bal[uuid] + (basis if basis is not None else bal[uuid]) * pct / 1200.0, 2)
        for uuid, series in immo_wert.items():
            if uuid in bal and mk in series:
                bal[uuid] = round(float(series[mk]), 2)
        for uuid, (bid, anteil) in fremd_link.items():
            src = (fremd_nw or {}).get(bid) or {}
            if uuid in bal and mk in src:
                bal[uuid] = round(float(src[mk]) * anteil, 2)
        for uuid in bal:
            if by_uuid[uuid]["role"] != "cash":
                plan_rows[uuid][mk] = bal[uuid]

    # Summen je Monat (Ist + Plan)
    all_months = ist + future
    sums: Dict[str, Dict[str, float]] = {}

    def val_of(z, mk):
        return z["amounts"].get(mk, 0.0) if mk in z["amounts"] else z.get("plan", {}).get("amounts", {}).get(mk, 0.0)
    for mk in all_months:
        s = {}
        for sek in sektionen:
            s[sek["name"]] = round(sum(val_of(z, mk) for z in sek["rows"]), 2)
        s["Zinsen"] = round(sum(val_of(z, mk) for sek in sektionen for z in sek["rows"] if z["kind"] == "interest"), 2)
        s["operating"] = round(s["income"] + s["expenses"], 2)
        # what is left after interest and repayments (a new loan is no income: only payments count)
        fin = [z for sek in sektionen if sek["name"] == "financing" for z in sek["rows"]]
        s["Nach_Kapitaldienst"] = round(s["operating"] + sum(val_of(z, mk) for z in fin if z["kind"] == "interest")
                                        + sum(min(val_of(z, mk), 0.0) for z in fin if z["kind"] == "repayment"), 2)
        trade = [z for sek in sektionen for z in sek["rows"] if (z.get("lbl") or [""])[0] in ("pos_revenue", "pos_goods")]
        if any((z.get("lbl") or [""])[0] == "pos_revenue" for z in trade):          # a trading business: revenue minus goods
            s["Rohertrag"] = round(sum(val_of(z, mk) for z in trade), 2)
        s["cash_change"] = round(sum(s[k] for k in CASH_SECTIONS), 2)
        s["net_worth_delta"] = round(sum(val_of(z, mk) for sek in sektionen for z in sek["rows"] if z["nw"]), 2)
        sums[mk] = s
    dataset["cashflow"]["sums"] = sums

    # Liquiditaet und Nettovermoegen fortschreiben; Rest als Bewertung ausweisen
    liq_prev = liq_total[ist[-1]]
    liq_plan: Dict[str, float] = {}
    nw_plan: Dict[str, float] = {}
    nw_prev = dataset["balance"]["net_worth"][ist[-1]]
    einl_cum = 0.0
    for mk in ist:                                  # bank balance at the end of the month, as in the balance sheet (money in transit too)
        sums[mk]["bank"] = liq_total[mk]
    for mk in future:
        liq_prev = round(liq_prev + sums[mk]["cash_change"], 2)
        liq_plan[mk] = liq_prev
        sums[mk]["bank"] = liq_prev
        einl_cum += einlagen_plan.get(mk, 0.0)
        total = liq_prev + sum(plan_rows[u][mk] for u in plan_rows) + einl_cum
        nw_plan[mk] = round(total, 2)
        prev_nw = nw_plan.get(prev_mk_of(future, mk), nw_prev)
        bew = round(nw_plan[mk] - prev_nw - sums[mk]["net_worth_delta"], 2)
        if abs(bew) >= 0.005:
            sums[mk]["valuation"] = round(sums[mk]["valuation"] + bew, 2)
            sums[mk]["net_worth_delta"] = round(sums[mk]["net_worth_delta"] + bew, 2)

    # Projektion nach Positionen
    proj_rows: List[dict] = []
    for r in rows_b:
        if r["group"]:
            role = r["role"]
            members = [x for x in leaf_rows if x["role"] == role]
            werte = {}
            for mk in future:
                if role == "cash":
                    werte[mk] = liq_plan[mk]
                else:
                    werte[mk] = round(sum(plan_rows.get(x["id"], {}).get(mk, 0.0) for x in members), 2)
            proj_rows.append({"id": r["id"], "name": r["name"], "depth": 0, "group": True, "role": role, "amounts": werte})
        elif r["role"] != "cash" and not r.get("inactive"):
            proj_rows.append({"id": r["id"], "name": r["name"], "depth": 1, "group": False, "role": r["role"],
                              "amounts": {mk: plan_rows[r["id"]][mk] for mk in future}})
    if any(einlagen_plan.values()):
        proj_rows.append({"id": "contributions", "name": "Einlagen/Entnahmen Beteiligungen (kumuliert, Plan)", "depth": 1, "group": False, "role": "participations",
                          "amounts": {mk: round(einl_cum_at(einlagen_plan, future, mk), 2) for mk in future}})

    dataset["balance"]["projection"] = {"rows": proj_rows, "cash": liq_plan, "net_worth": nw_plan}
    dataset["figures"] = kennzahlen(dataset, plan, liq_total, full_months)
    dataset["plan"] = {"horizon_months": horizon, "default_method": default_method, "inflation_percent_pa": inflation,
                       "income_increase_percent_pa": growth_default["income"], "expense_increase_percent_pa": growth_default["expenses"],
                       "return_percent_pa": rendite, "fi_real_return_percent": float(plan.get("fi_real_return_percent") or 3.0),
                       "rows": rows_cfg, "loans": loans_plan, "appreciation": wert_cfg, "events": plan.get("events") or []}
    return dataset


def prev_mk_of(future: List[str], mk: str) -> str:
    i = future.index(mk)
    return future[i - 1] if i > 0 else ""


def einl_cum_at(einlagen_plan: Dict[str, float], future: List[str], mk: str) -> float:
    return sum(v for k, v in einlagen_plan.items() if k <= mk)


def kennzahlen(dataset: dict, plan: dict, liq_total: Dict[str, float], full_months: List[str]) -> dict:
    sums = dataset["cashflow"]["sums"]
    last12 = full_months[-12:]
    n = max(1, len(last12))
    ausgaben = -sum(sums[mk]["expenses"] for mk in last12) / n
    zinsen = -sum(sums[mk]["Zinsen"] for mk in last12) / n
    operativ = sum(sums[mk]["operating"] for mk in last12)
    cur = dataset["actual_until"]
    liq = liq_total.get(cur, 0.0)
    real = float(plan.get("fi_real_return_percent") or 3.0)
    monatlich = ausgaben + zinsen
    benoetigt = round(monatlich * 12 / (real / 100.0), 2) if real > 0 and monatlich > 0 else None
    lnw = dataset["balance"]["liquid_net_worth"][cur]
    nw = dataset["balance"]["net_worth"][cur]
    ein = sum(sums[mk]["income"] for mk in last12)
    return {
        "expenses_month": round(ausgaben, 2), "interest_month": round(zinsen, 2), "operating_12m": round(operativ, 2),
        "cash": liq, "runway_months": round(liq / monatlich, 1) if monatlich > 0 else None,
        "fi_real_return_percent": real, "fi_needed": benoetigt,
        "fi_cover_liquid": round(lnw / benoetigt, 3) if benoetigt else None,
        "fi_cover_total": round(nw / benoetigt, 3) if benoetigt else None,
        "saving_rate": round(operativ / ein, 3) if ein > 0 else None,
    }
