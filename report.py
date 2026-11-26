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

import categorize
from categorize import party_key, suggest as suggest_category
from model import Account, Ledger, Tx, add_months, month_end, month_key, months_between, norm_cat, legacy_cat
from model import MARK, marks_in
from i18n import tr, trn

ROLES = ["cash", "securities", "term_investments", "real_estate", "participations", "tangibles", "receivables", "other", "liabilities",
         "contingent", "ignore"]
ROLE_KEYS = {"cash": "pos_bankguthaben", "securities": "pos_wertpapiere", "term_investments": "pos_gebundene_anlagen", "real_estate": "immobilien",
             "participations": "beteiligungen", "tangibles": "sachwerte", "receivables": "pos_forderungen", "other": "sonstiges",
             "liabilities": "pos_verbindlichkeiten", "contingent": "role_eventual",
             "ignore": "nicht_bilanzieren"}       # Schluessel in web/i18n.js


def month_text(key: str) -> str:
    """A month key YYYY-MM as the user reads it in a note: MM/YYYY (as the other notes write months)."""
    return "%s/%s" % (key[5:7], key[:4]) if re.fullmatch(r"\d{4}-\d{2}", key or "") else str(key)


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
COST_WORDS = ["zins", "interest", "gebühr", "gebuehr", "entgelt", "provision", "bereitstellung", "#kontor-zins"]
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
    # a series in MoneyMoney's history without name and ISIN cannot be matched to the export by itself; when the portfolio holds
    # a single security in the history and a single one now (with no history of its own), they are the same – one row
    if len(rows) == 2:
        (k1, r1), (k2, r2) = rows.items()
        old, new = ((k1, r1), (k2, r2)) if k1.startswith("mm:") else ((k2, r2), (k1, r1))
        if old[0].startswith("mm:") and not new[0].startswith("mm:") and set(new[1]["amounts"]) <= {cur}:
            new[1]["amounts"].update(old[1]["amounts"])         # history only before the current month: nothing overlaps
            del rows[old[0]]
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
            h[k] = acc.balance if k >= cur_key else (None if opened and k < opened else ends.get(k))      # (a group without accounts: unknown)
        t = (acc.type or "").lower()
        if any(x in t for x in NO_NEGATIVE_TYPES):
            neg = [k for k in mkeys if (h[k] or 0) < -1.0]
            if neg:
                hinweis = (tr("s_s_die_rueckrechnung_aus_den")
                           % (acc.name, month_text(neg[0]), month_text(neg[-1])))
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
        hinweis = (tr("s_s_kontostaende_vor_s_sind") % (acc.name, month_text(first_known)))
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


VALUE_MARKS = (MARK + "wert-",)     # value adjustments of Kontor (participation): never a transfer
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


def _saving_grp(kind: str, company: bool) -> dict:
    """The group of saving by a category: by the kind of its target account, else "Sparen & Anlegen" (a company's name for it:
    fixed assets and investments)."""
    g = _grp(INVEST_GROUPS, kind if kind in INVEST_GROUPS else "saving_group")
    if company and g["glbl"] == ("pos_saving",):
        g["glbl"] = ("pos_saving_g",)
    return g


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


PAIR_EXACT = 60                                         # bookings in one group of possible pairs up to which the best choice is searched
PAIR_WORTH = PAIR_DAYS_CAT + 1                          # what a pair is worth, in days: two pairs only beat one if they lie this much
                                                        # closer together in all
PAIR_BOTH = 2                                           # ... days more when both bookings say "transfer" (on two accounts)


def best_pairs(cands: list) -> List[Tuple[Tx, Tx]]:
    """Which of the possible pairs (gap in days, smaller id, larger id, booking, booking[, both with a transfer category]) to
    take: each pair is worth PAIR_WORTH days less its gap (PAIR_BOTH days more when both bookings on two accounts say
    "transfer": two such are more likely each other's other side than one of them and a booking by hand), and the choice worth
    most in all wins (of two worth the same, the one with more pairs) --
    not simply the closest first: two payments of one amount a few days apart and two bookings against them each find their
    own, rather than the second payment taking the first one's only counterpart and leaving two alone; but a pair on one day is
    not split up for two pairs days apart (that would invent money in transit for what went elsewhere). Per group of bookings
    that could pair with each other; a pair always joins money out and money in. A group larger than PAIR_EXACT, or one with a
    booking of 0.00, the closest first, as before."""
    cents = lambda x: int(round(x * 100))
    edge: Dict[Tuple[int, int], tuple] = {}
    for c in cands:
        if (c[1], c[2]) not in edge or c[0] < edge[(c[1], c[2])][0]:
            edge[(c[1], c[2])] = c
    tx: Dict[int, Tx] = {}
    up: Dict[int, int] = {}                      # groups: each booking to the first of its group (union-find)

    def top(n: int) -> int:
        while up[n] != n:
            up[n] = up[up[n]]
            n = up[n]
        return n
    for (a, b), c in edge.items():
        tx[a], tx[b] = (c[3], c[4]) if c[3].id == a else (c[4], c[3])
        up.setdefault(a, a); up.setdefault(b, b)
        ra, rb = top(a), top(b)
        if ra != rb:
            up[max(ra, rb)] = min(ra, rb)
    groups: Dict[int, List[tuple]] = defaultdict(list)
    for k, c in edge.items():
        groups[top(k[0])].append(c)
    out: List[Tuple[Tx, Tx]] = []
    for g in sorted(groups):
        es = sorted(groups[g], key=lambda c: c[:3])
        members = {i for c in es for i in (c[1], c[2])}
        if len(members) > PAIR_EXACT or any(cents(tx[n].amount) == 0 for n in members):
            taken: Set[int] = set()
            for c in es:
                if c[1] not in taken and c[2] not in taken:
                    taken.update((c[1], c[2])); out.append((c[3], c[4]))
            continue
        out.extend(_best_worth(es, tx))
    return out


def _best_worth(es: list, tx: Dict[int, Tx]) -> List[Tuple[Tx, Tx]]:
    """The pairs worth most in all (each joins a booking of money out and one of money in): one pair more at a time along the
    path that adds the most worth -- from an unpaired "out" to an unpaired "in", possibly moving pairs already made to another
    partner on the way -- as long as it adds any (successive shortest paths on cost = gap - worth; ties by the bookings' ids,
    so always the same)."""
    cost: Dict[Tuple[int, int], int] = {}
    for c in es:
        g, r = (c[1], c[2]) if tx[c[1]].amount < 0 else (c[2], c[1])
        # in half days, each pair half a day more: of two choices worth the same, the one with more pairs (fewer left unclear)
        cost[(g, r)] = 2 * (c[0] - PAIR_WORTH - (PAIR_BOTH if len(c) > 5 and c[5] and tx[g].account_uuid != tx[r].account_uuid else 0)) - 1
    give = sorted({g for g, _ in cost})
    ins = sorted({r for _, r in cost})
    take: Dict[int, List[Tuple[int, int]]] = {g: sorted((d, r) for (gg, r), d in cost.items() if gg == g) for g in give}
    with_: Dict[int, int] = {}                   # money in -> the money out it is paired with
    done: Set[int] = set()                       # money out that is paired
    far = 1 << 30
    while True:
        dist: Dict[Tuple[str, int], int] = {("g", g): 0 for g in give if g not in done}
        prev: Dict[Tuple[str, int], Optional[Tuple[str, int]]] = {k: None for k in dist}
        for _ in range(len(give) + len(ins) + 1):
            changed = False
            for g in give:                       # a new pair: + its cost
                kg = ("g", g)
                if kg in dist:
                    for d, r in take[g]:
                        if with_.get(r) != g and dist[kg] + d < dist.get(("r", r), far):
                            dist[("r", r)], prev[("r", r)], changed = dist[kg] + d, kg, True
            for r, g in sorted(with_.items()):   # an old pair undone: - its cost
                kr = ("r", r)
                if kr in dist and dist[kr] - cost[(g, r)] < dist.get(("g", g), far):
                    dist[("g", g)], prev[("g", g)], changed = dist[kr] - cost[(g, r)], kr, True
            if not changed:
                break
        ends = sorted((dist[("r", r)], r) for r in ins if r not in with_ and ("r", r) in dist)
        if not ends or ends[0][0] >= 0:          # nothing left that adds worth
            return [(tx[g], tx[r]) for r, g in sorted(with_.items())]
        k: Optional[Tuple[str, int]] = ("r", ends[0][1])
        while k is not None:                     # along the path: each "in" now with the "out" before it
            p = prev[k]
            if p is None:
                break
            with_[k[1]] = p[1]
            done.add(p[1])
            k = prev[p]


def pair_transfers(ledger: Ledger, txs: List[Tx], root: Set[str], roles: Dict[str, str], is_transfer: Callable[[str], bool],
                   cost_words: List[str], kf: dict, pairable: Callable[[Tx], bool] = lambda t: True, keep: Set[int] = frozenset()):
    """Transfers within an area, booking by booking: the counterpart of a transfer is the booking on the other side.
    Found by Kontor's mark (#kontor-tx-<payment>: the repayment of a loan names the payment), by the counter IBAN (a booking of
    that account with the same amount, opposite sign, at most 5 days apart) or -- for a transfer category or an offline account
    -- by amount alone (at most 3 days; a week when both have a transfer category). Two transfers on one account that undo each
    other within a month are each other's counterpart (together nothing). Returns (mate: booking -> counterpart in the area, partner: booking -> account on the
    other side, also outside the area or without a counterpart, category: booking -> marked as transfer by its category).
    keep: bookings of offline accounts left for a payment into another area (not paired by amount here)."""
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
        open_tx = [t for t in txs if by_cat[t.id] and loose(t) and t.id not in keep]
        offline = [t for t in txs if manual_ok and loose(t) and t.id not in keep and roles.get(t.account_uuid) != "cash"
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
        # every possible pair (best_pairs chooses among them): by amount on two accounts -- within a week when both carry a
        # transfer category (PayPal books on the day, the bank days later), else 3 days -- and two transfers on one account that
        # undo each other within the month (a top-up booked back: together nothing)
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
                        cands.append((gap, min(t.id, o.id), max(t.id, o.id), t, o, both))
        for t, o in best_pairs(cands):
            if t.id in mate or o.id in mate:
                continue
            if o.account_uuid == t.account_uuid:
                mate[t.id], mate[o.id] = o, t                    # no partner account: nothing moved anywhere
            else:
                join(t, o)
        # booked back on one account days later (a top-up undone within the month): only among what is left, the closest first
        # -- never instead of a pair between two accounts
        for c in sorted((c for c in cands if c[3].account_uuid == c[4].account_uuid), key=lambda c: c[:3]):
            t, o = c[3], c[4]
            if t.id not in mate and o.id not in mate:
                mate[t.id], mate[o.id] = o, t
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
    ("work_income", "income", "Arbeitseinkommen"), ("revenue", "income", "Umsatzerlöse"), ("benefits", "income", "Rente & Sozialleistungen"),
    ("rental", "income", "Vermietung"), ("capital_income", "income", "Kapitalerträge"), ("gifts_in", "income", "Unterhalt & Geschenke"),
    ("refunds", "income", "Erstattungen"), ("other_income", "income", "Sonstige Einnahmen"),
    ("goods", "expenses", "Wareneinkauf"), ("staff", "expenses", "Personal"), ("operations", "expenses", "Betriebskosten"),
    ("housing", "expenses", "Wohnen"), ("living", "expenses", "Lebenshaltung"), ("mobility", "expenses", "Mobilität"),
    ("insurance", "expenses", "Versicherungen"), ("health", "expenses", "Gesundheit"), ("education", "expenses", "Bildung & Betreuung"),
    ("leisure", "expenses", "Freizeit & Reisen"),
    ("property_costs", "expenses", "Objektkosten"), ("administration", "expenses", "Beratung & Gebühren"), ("taxes", "expenses", "Steuern"),
    ("vat", "expenses", "Umsatzsteuer"),
    ("donations", "expenses", "Unterhalt, Geschenke & Spenden"), ("advances", "expenses", "Auslagen"),
    ("other_expenses", "expenses", "Sonstige Ausgaben"),
    ("saving", "investing", "Sparen & Anlegen"), ("repayment", "financing", "Tilgung"), ("loan_interest", "financing", "Zinsen"),
    ("partners", "financing", "Einlagen & Entnahmen"),
    ("ignore", "", ""),
]
POS = {k: (sec, row, i) for i, (k, sec, row) in enumerate(POSITIONS)}
# the same position, named as a company would (text pos_<key>_g)
COMPANY_ROWS = {"housing": "Raumkosten", "benefits": "Zuschüsse & Förderungen", "education": "Fortbildung"}


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
    (("zins", "finanzierungskost", "vorfaelligkeit"), "capital_income", "loan_interest", False),
    (("tilgung", "kredit", "darlehen", "finanzierung", "annuit", "hypothek"), "repayment", "repayment", False),
    (("einlage", "entnahme", "privateinlage", "privatentnahme", "kapitaleinlage", "gewinnverwendung"), "partners", "partners", True),
    # a distribution received (from a GmbH) is investment income, as "Ausschüttung" and the estimate by the booking's words;
    # paid out, it is equity (money from a GbR to its partners is a withdrawal: "Entnahme", above)
    (("gewinnausschuett",), "capital_income", "partners", True),
    (("sparen", "sparplan", "bauspar", "invest", "wertpapier", "depot", "etf", "aktie", "fonds", "geldanlage", "ruecklage", "krypto",
      "altersvorsorge", "beteiligung", "immobilienkauf", "kapitalanlage", "rentenversicherung", "riester", "ruerup", "basisrente",
      "pensionskasse", "direktversicherung", "kapitallebensversicherung", "fondspolice", "tagesgeld", "festgeld", "edelmetall",
      "vermoegensaufbau"), "saving", "saving", True),
]
FIRST_NOT = ("gebuehr", "kosten", "entgelt", "provision", "kreditkarte")
# the costs of buying an investment (notary, land transfer tax, agent) belong to the purchase: saving, as the purchase itself
# ("Sparen & Anlegen", samt Nebenkosten) -- also where FIRST_NOT ("kosten") would keep them from it (3.17.85: "Sparen &
# Anlegen / Kaufnebenkosten" was proposed as Wohnen)
PURCHASE_COSTS = ("kaufnebenkost", "erwerbsnebenkost", "anschaffungsnebenkost", "grunderwerbsteuer")
# ... and so is the price: buying a property (or any investment) is no cost of it -- also in a category below the property's
# own ("Vermietung / Parkweg / Kaufpreis" counted as the property's costs, its counter-booking in the property's account as a
# change in value: 3.17.87). "Kauf" as a category's whole name says the same below a property or a participation ("Immobilie /
# Kauf") -- not anywhere ("Wertpapiere / Kauf" goes into the depot, "Waren / Ankauf" is goods). Never what pays for it: the
# loan for the price ("Kaufpreisdarlehen / Tilgung") is financing.
PURCHASE_PRICE = ("kaufpreis", "hauskauf", "wohnungskauf", "immobilienkauf", "grundstueckskauf", "objektkauf", "immobilienerwerb")
PURCHASE_NAMES = ("kauf", "ankauf", "erwerb")
PURCHASE_OF = ("immobil", "vermiet", "objekt", "grundstueck", "eigentumswohnung", "beteiligung", "firmenanteil", "geschaeftsanteil")
PURCHASE_NOT = ("zins", "tilgung", "darlehen", "kredit", "finanzierung", "annuit", "hypothek")


def deposit_category(path: str) -> bool:
    """A category for a rent deposit ("Kaution") -- held for the tenant, or paid to a landlord: money owed back, neither rent
    nor a cost. Not its insurance or its interest."""
    low = fold_text(path)
    return "kaution" in low and not any(w in low for w in ("versicher", "zins", "buergschaft"))


def purchase_kind(path: str) -> str:
    """"price" (the purchase of an investment), "costs" (what buying it cost: notary, land transfer tax) or "" -- by the
    category's words."""
    low = fold_text(path)
    if any(w in low for w in PURCHASE_NOT):
        return ""
    if any(w in low for w in PURCHASE_COSTS):
        return "costs"
    parts = low.split(" / ")
    if any(w in low for w in PURCHASE_PRICE) or (len(parts) > 1 and parts[-1] in PURCHASE_NAMES and any(w in " / ".join(parts[:-1]) for w in PURCHASE_OF)):
        return "price"
    return ""
POSITION_CONTEXT = [(("vermiet", "immobil", "objekt", "mieterloes", "pachterloes"), "rental", "property_costs")]
# what a home of your own costs, booked below "Wohnen": housing -- "Hausgeld" and "Grundsteuer" alone name a rented property's costs
HOME_COSTS = ("hausgeld", "instandhalt", "reparatur", "hausverwalt", "grundsteuer")
# a position may be (a company's, a person's): "Verkauf" is revenue in a company, privately selling used things (other income)
POSITION_HINTS = [
    # paid for others and paid back (e.g. fuel for your company) -- both in one category: it cancels out; before "erstattung"
    (("auslage", "verauslag", "durchlaufend"), "advances", "advances"),
    # furnishings and household appliances are no housing costs (rent, utilities) but household goods -- a company's: an
    # investment (as the recommended categories say); after the fees below ("Einrichtungsgebühr"), before "wohnung" and "miete"
    (("steuerberat", "beratung", "notar", "anwalt", "kontofuehr", "gebuehr", "bankgeb", "buchhalt", "buchfuehr", "geldverkehr"), "other_income", "administration"),
    (("einricht", "ausstatt", "moebel", "mobiliar", "haushaltsger", "haushaltsgeraet"), "refunds", ("saving", "living")),
    # a company's: fixed assets are an investment; travel, entertaining, office supplies, postage and advertising run the business
    # (before "material" below: "Büromaterial" is no purchase of goods)
    (("anlagevermoeg", "sachanlage"), "refunds", ("saving", "other_expenses")),
    (("reisekost", "bewirtung"), "refunds", ("operations", "leisure")),
    (("buerobedarf", "bueromaterial", "porto", "werbekost", "werbemittel", "werbematerial", "geringwertig"), "refunds", ("operations", "other_expenses")),
    (("wareneinkauf", "waren", "lieferant", "material", "fremdleist", "subunternehm"), "refunds", "goods"),
    (("personal", "loehne", "sozialversicher", "sozialabgab", "lohnneben"), "refunds", "staff"),
    (("umsatzerl", "kasseneinnahm"), "revenue", "other_expenses"),
    (("erloes", "verkauf", "verkaeuf", "kleinanzeig", "ebay", "vinted", "flohmarkt"), ("revenue", "other_income"), "other_expenses"),
    (("betriebskost", "betriebsbedarf", "marketing", "werbung", "software", "it-kost"), "refunds", "operations"),
    (("ladenmiete", "raumkost", "geschaeftsmiete", "gewerbemiete"), "rental", "housing"),
    (("hausgeld", "instandhalt", "reparatur", "hausverwalt", "grundsteuer"), "refunds", "property_costs"),
    (("umsatzsteuer", "vorsteuer", "ust"), "vat", "vat"),
    (("finanzamt", "steuer", "solidarit"), "refunds", "taxes"),
    (("mieteink", "pachteink"), "rental", "property_costs"),
    (("kapitaleink",), "capital_income", "other_expenses"),
    # pensions and public benefits (a company: grants and subsidies) -- before work income: "Ruhegehalt", "Arbeitslosengeld"
    (("rente", "pension", "ruhegehalt", "versorgungsbez", "kindergeld", "elterngeld", "arbeitslosengeld", "buergergeld", "krankengeld",
      "pflegegeld", "mutterschaftsgeld", "bafoeg", "sozialleistung", "sozialhilfe", "grundsicherung", "kurzarbeit", "zuschuss", "zuschuesse",
      "foerdermittel", "foerderung", "subvention"), "benefits", "other_expenses"),
    (("gehalt", "gehaelt", "lohn", "loehn", "tantieme", "bonus", "gratifikation", "verguetung", "honorar", "arbeit", "minijob", "nebenjob",
      "aushilfe", "werkstudent", "nebeneink", "nebenverdienst", "nebentaetig"), "work_income", "staff"),
    (("dividend", "kapitalertr", "ausschuett", "gewinnanteil", "gewinnauszahl"), "capital_income", "partners"),
    (("mieteinnahm", "pacht"), "rental", "property_costs"),
    (("erstattung", "rueckzahlung", "gutschrift", "cashback"), "refunds", "other_expenses"),
    (("geldautomat", "bargeld", "barabhebung", "abhebung"), "other_income", "other_expenses"),
    (("versicherung", "berufsunfaehig", "haftpflicht", "rechtsschutz"), "refunds", "insurance"),
    (("miete",), "rental", "housing"),
    # telephone and internet: at home part of housing, in a company of running it (as the estimate for a booking says)
    (("internet", "telefon", "mobilfunk", "handy", "kommunikation"), "refunds", ("operations", "housing")),
    (("nebenkost", "strom", "energie", "wasser", "heiz", "rundfunk", "wohnen", "wohnung", "handwerker", "renovier", "modernisier"),
     "refunds", "housing"),
    # eating and drinking -- at home or out -- is living, so "Lebensmittel & Restaurant" has one place; a pet's vet too (before "arzt")
    (("lebensmittel", "supermarkt", "einkauf", "drogerie", "kleidung", "haushalt", "lebenshalt", "restaurant", "gastro", "kantine",
      "lieferdienst", "getraenk", "friseur", "kosmetik", "koerperpflege", "haustier", "tierbedarf", "tierarzt", "elektronik"), "refunds", "living"),
    (("auto", "kfz", "tank", "benzin", "mobilit", "bahn", "oepnv", "taxi", "parken", "fahrrad", "verkehr", "maut", "transport", "fahrzeugkost"),
     "refunds", "mobility"),
    (("gesundheit", "arzt", "apotheke", "medizin", "zahn", "kranken", "therapie", "brille", "optiker", "physio", "pflegeheim", "pflegedienst"),
     "refunds", "health"),
    (("freizeit", "urlaub", "ferien", "reise", "kultur", "sport", "hobby", "abo", "streaming", "kino", "konzert", "hotel", "flug", "sauna",
      "wellness", "fitness", "therme", "schwimmbad", "vereinsbeitr", "event", "veranstaltung", "unterhaltung", "buecher", "zeitung", "zeitschrift",
      "musik"), "refunds", "leisure"),
    (("bildung", "schule", "schulung", "studium", "studienge", "kita", "kindergarten", "kinderbetreuung", "tagesmutter", "nachhilfe", "seminar"),
     "refunds", "education"),
    # support (maintenance, pocket money), gifts, inheritances, donations -- the taxes on them are taxes (above)
    (("spende", "geschenk", "taschengeld", "schenkung", "erbschaft", "unterhaltszahl", "unterhaltsvorschuss", "kindesunterhalt",
      "ehegattenunterhalt", "trennungsunterhalt"), "gifts_in", "donations"),
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
    ("text", r"ausschuettung|dividend|ertragsgutschrift|gewinnanteil|gewinnauszahlung", ("capital_income", ""), ("capital_income", "")),
    ("text", r"\bzins|sollzins|habenzins|zinsabschluss|kupon", ("capital_income", "loan_interest"), ("capital_income", "loan_interest")),
    ("name", r"deutsche rentenversicherung", ("benefits", "insurance"), ("", "staff")),       # money from it: a pension
    ("name", r"familienkasse|elterngeldstelle|jobcenter|bundesagentur fuer arbeit|bafoeg", ("benefits", None), ("benefits", None)),
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
    ("name", r"\brewe\b|\bedeka\b|\baldi\b|\blidl\b|\bpenny\b|kaufland|denns|alnatura|\bdm\b|dm-drogerie|rossmann|amazon|zalando|\bikea\b|restaurant|lieferando|\bwolt\b",
     ("refunds", "living"), (None, None)),
    ("name", r"deutsche bahn|\bdb vertrieb|\bmvg\b|\bmvv\b|\baral\b|\bshell\b|\besso\b|totalenergies|tankstelle|\bsixt\b|share now|\buber\b|flixbus|lufthansa|parkhaus|\bapcoa\b|\badac\b",
     ("refunds", "mobility"), (None, "operations")),
    ("name", r"apotheke|zahnarzt|\barzt|arztpraxis|klinik|krankenhaus|physiotherap|fielmann", ("refunds", "health"), (None, None)),
    ("name", r"netflix|spotify|disney|apple\.com|itunes|google play|eventim|airbnb|booking\.com|\bhotel|\bkino",
     ("refunds", "leisure"), (None, None)),
]
_TX_HINTS = [(f, re.compile(rx), pp, pc) for f, rx, pp, pc in TX_HINTS]
# the tax office: wage tax is part of staff costs (a company), VAT a position of its own, the rest taxes (or a refund)
_TAX_OFFICE = re.compile(r"finanzamt|steuerkasse|bundeskasse|stadtkasse|gemeindekasse")
_WAGE_TAX = re.compile(r"lohnsteuer|\blst\b|lohnst")
_VAT = re.compile(r"umsatzsteuer|\bust\b|ustva|ust-va|ust-vz|ust-voranmeldung|vorsteuer")


# A booking that moves money into or out of an account with balances only (a depot, a fixed deposit, a P2P account), by what
# it says -- folded text of name, purpose and booking text (checked against real-looking texts: tests, MovesAreRecognised).
# Kinds, each with the accounts it may mean:
#   securities  a trade said outright (Wertpapierkauf, WP-Kauf, buy trade, Sparplan, Fondskauf, Depotübertrag) -- or an ISIN
#               or WKN beside a word of buying or selling: that only at the booking's own bank (_TRADE_WEAK; a reference
#               number looks like an ISIN, and "Kauf 2 Stück" is bread as well)
#   term        a fixed deposit (Festgeld, Termingeld, Sparbrief)
# _TRADE_NEVER: what such an account pays or costs, or what is no trade at all -- income, an expense, a loan, a contract of
# its own; it wins over every word. _TRADE_PAYS: income words that only count where no trade is said outright ("Sparplan ...
# High Dividend ...", "Wertpapierkauf inkl. Stückzinsen" are trades).
_TRADE_SURE = re.compile(r"wertpapier(?:kauf|verkauf|abrechnung|sparplan)|wertp\.? ?abrechn|\bwp[- ]?(?:kauf|verkauf|abrechnung)|\b(?:buy|sell) trade\b|savings ?plan"
                         r"|\bsparplan|fonds(?:kauf|verkauf|sparplan)|effekten(?:kauf|verkauf)|depotuebertrag|\buebertrag\b.*\bdepot"
                         r"|\b(?:kauf|verkauf)\b.*\b(?:aktien?|etfs?|fondsanteile?)\b|\b(?:aktien?|etfs?|fondsanteile?)\b.*\b(?:kauf|verkauf)\b")
_TRADE_TERM = re.compile(r"festgeld|termingeld|festanlage|sparbrief")
_TRADE_ISIN = re.compile(r"\b(?:de|us|ie|lu|fr|nl|gb|ch|at|ca|jp|se|dk|fi|es|it|be|au|ky|bm|je|gg|li|xs)[a-z0-9]{9}[0-9]\b|\bisin\b|\bwkn\b")
_TRADE_WEAK = re.compile(r"\b(?:kauf|verkauf|buy|sell|trade|zeichnung|stk|stueck|quantity)\b")
_TRADE_NEVER = re.compile(r"storno|entgelt|gebuehr|depotfuehrung|depotpreis|\brechnung\b|vorabpauschale|ertragsgutschrift|\bertr\.|ertraegnis|wertpapierertrag|fondsertrag"
                          r"|dividendengutschrift|coupon|kupon|thesaur|kredit|lombard|bauspar|riester|\bvl\b|vermoegenswirksam|tagesgeld|gehalt|\blohn\b|erstattung")
_TRADE_PAYS = re.compile(r"\bdividenden?\b|\bzinsen?\b|zinsgutschrift|habenzins|ausschuettung|\bsteuer")
_TERM_MOVE = re.compile(r"anlage|einzahlung|auszahlung|rueckzahlung|faellig|prolong")


def said_move(text: str) -> Tuple[str, bool]:
    """(kind, weak) of the move a booking's folded text says: "securities", "term" or "" (none); weak: only for an account
    at the booking's own bank."""
    if _TRADE_NEVER.search(text):
        return "", False
    if _TRADE_SURE.search(text):
        return "securities", False
    if _TRADE_TERM.search(text) and (_TERM_MOVE.search(text) or not _TRADE_PAYS.search(text)):
        return "term", False
    if not _TRADE_PAYS.search(text) and _TRADE_WEAK.search(text) and _TRADE_ISIN.search(text):
        return "securities", True
    return "", False


_NAME_GENERIC = {"bank", "gmbh", "depot", "konto", "sparkasse", "volksbank", "capital", "invest", "verrechnungskonto", "wertpapiere"}


_LOAN_GENERIC = {"darlehen", "darlehenskonto", "kredit", "kreditkonto", "ratenkredit", "hypothek", "finanzierung", "baufinanzierung", "immobiliendarlehen", "annuitätendarlehen", "loan", "mortgage"}
_RATE_SAID = re.compile(r"darlehen|annuit|tilgung|kreditrate|kreditvertrag|hypothek|baufinanz|\bloan\b|\bmortgage")   # a payment that says it is a loan's rate


def name_words(text: str) -> Set[str]:
    """The words of a name that tell it apart (four letters or more, no "Bank", "Depot" ...)."""
    return {w for w in re.sub(r"[^\wäöüß]+", " ", (text or "").lower()).split() if len(w) >= 4 and w not in _NAME_GENERIC}


def fold_text(s: str) -> str:
    return (s or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")


# words that name a property (its street, its place) -- not the common words every rental category or booking has
PROPERTY_STOP = {"wohnung", "wohnungen", "haus", "immobilie", "immobilien", "objekt", "objekte", "vermietung", "miete", "mieten", "kosten",
                 "gbr", "egbr", "gmbh", "strasse", "einnahmen", "ausgaben", "privat", "eigentum", "eigentumswohnung", "grundstueck",
                 "garage", "stellplatz", "ferienwohnung", "buero", "laden", "gewerbe", "halle", "lager", "zimmer", "januar", "februar",
                 "maerz", "april", "juni", "juli", "august", "september", "oktober", "november", "dezember", "nebenkosten", "kaltmiete",
                 "warmmiete", "mieter", "mieterin", "dauerauftrag", "ueberweisung", "gutschrift", "lastschrift", "sepa", "vorauszahlung"}
PROPERTY_CONTEXT = ("vermiet", "immobil", "objekt", "miete")


def property_marks(text: str) -> Tuple[Set[str], Set[str]]:
    """(words of at least four letters, numbers) that may name a property."""
    toks = re.findall(r"[a-z0-9]+", fold_text(text))
    return ({w for w in toks if len(w) >= 4 and not w.isdigit() and w not in PROPERTY_STOP}, {w for w in toks if w.isdigit() and len(w) <= 3})


def marks_fit(prop: Tuple[Set[str], Set[str]], other: Tuple[Set[str], Set[str]]) -> bool:
    """A word of the property's name is in the other text -- and where both carry numbers (house numbers), one agrees."""
    return bool(prop[0] & other[0]) and (not prop[1] or not other[1] or bool(prop[1] & other[1]))


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


def propose_position(path: str, income: bool, company: bool = False) -> str:
    """Kontor's proposal for a category (by its words); income: its money mostly comes in; company: in a company's area."""
    return recognised_position(path, income, company) or ("other_income" if income else "other_expenses")


def recognised_position(path: str, income: bool, company: bool = False) -> Optional[str]:
    """The position a category's words name -- None when none of them is known (then it is "other" income or expenses).
    company: in a company's area (a hint may name one position for a company, another for a person)."""
    low = fold_text(path)
    name = low.split(" / ")[-1]
    low_l = fold_text(legacy_cat(path))                # read as before 3.13.19 (every slash a level) first: the same proposals
    name_l = low_l.split(" / ")[-1]
    texts = list(dict.fromkeys((name_l, low_l, name, low)))
    if not income and purchase_kind(path):
        return "saving"
    if deposit_category(path):
        # received for a property you let: a debt (taken up, paid back) -- best kept in an account of its own; paid as a
        # tenant: money you get back (saving). Never rent, never housing costs (user, 2026-11-25).
        return "repayment" if income or any(_has(words, low) for words, _, _ in POSITION_CONTEXT) else "saving"
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
    if not company and not income and "wohnen" in low and _has(HOME_COSTS, low):
        return "housing"
    for text in texts:
        for words, pin, pout in POSITION_HINTS:
            if _has(words, text):
                pos = pin if income else pout
                return (pos[0] if company else pos[1]) if isinstance(pos, tuple) else pos
    # "Einkommen" names work income only as the category's own name (its subcategories -- child benefit, pension -- are no
    # salary) and as a word of its own ("Hereinkommende Zahlungen" is none)
    if income and any(_has(("einkommen",), n, True) for n in dict.fromkeys((name_l, name))):
        return "work_income"
    # "Unterhalt" as a word of its own in the category's name is support paid or received ("Unterhaltung" is leisure, above)
    if any(_UNTERHALT.search(n) for n in dict.fromkeys((name_l, name))):
        return "gifts_in" if income else "donations"
    return None


_UNTERHALT = re.compile(r"(?<![a-z])unterhalts?(?![a-z])")


def category_totals(ledger: Ledger, accounts: Optional[Set[str]] = None) -> Dict[str, float]:
    """Sum per category over all booked transactions (whether its money mostly comes in or goes out). accounts: only those of
    an area -- "Gehalt" is income for you and an expense for your company."""
    out: Dict[str, float] = defaultdict(float)
    for t in ledger.txs:
        if t.booked and t.category_path and (accounts is None or t.account_uuid in accounts):
            out[norm_cat(t.category_path)] += t.amount
    return dict(out)


def position_of(path: str, config: dict, totals: Dict[str, float], company: bool = False) -> Tuple[str, bool]:
    """(position, yours) of a category: what you chose for it or for the nearest category above it (Kategorien ->
    Cashflow-Positionen), otherwise Kontor's proposal (company: for a company's area)."""
    mine = my_positions(config)
    parts = path.split(" / ")
    for i in range(len(parts), 0, -1):
        p = " / ".join(parts[:i])
        if p in mine:
            return mine[p], True
    return propose_position(path, totals.get(path, 0.0) > 0, company), False


def my_positions(config: dict) -> Dict[str, str]:
    """The positions you chose: category path -> position (or "umbuchung": a transfer between your own accounts)."""
    return {norm_cat(k): v for k, v in ((config.get("cashflow") or {}).get("positions") or {}).items()
            if (v in POS or v == "transfer") and norm_cat(k)}


# the usual names of a transfer category -- the category's own name only (not one above it: "Übertrag / Familie" may be anything)
TRANSFER_NAMES = {"umbuchung", "umbuchungen", "uebertrag", "uebertraege", "kontouebertrag", "eigene konten", "eigenes konto"}
# ... also with a note in brackets after it, which transfer it is: "Umbuchung (zwischen eigenen Konten)", "Umbuchung (AHS)" (3.17.90:
# such a name was no transfer -- one without its counterpart counted as other expenses, below a property as its costs)
_NAME_NOTE = re.compile(r"\s*\([^()]*\)$")


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
                    own = {low[-1], _NAME_NOTE.sub("", low[-1])} if ps else set()
                    if ps and (own & names or own & TRANSFER_NAMES or any(" / ".join(low[:i]) in names for i in range(1, len(low) + 1))):
                        r = True
                        break
            memo[p] = r
        return r
    return check


# A category that mixes payments of another kind with its usual ones: a property's category with its purchase price and the
# loan's payout beside the rent, say. In the cash flow everything in a category counts in its one position, so the purchase
# would count as a cost of the property and the payout as rent. A payment stands out when it is at least MIXED_MIN euros and
# MIXED_RATIO times the median of the rest of its category -- a hint, never a figure: Kontor changes nothing by it.
MIXED_MIN = 5000.0
MIXED_RATIO = 10.0


def standing_out(amounts: Dict[int, float]) -> List[int]:
    """The payments (id -> amount in euros) that stand out from the rest: the largest, as long as it is at least MIXED_MIN and
    MIXED_RATIO times the median of those left, and at least two are left to compare with. Largest first."""
    rest = sorted(amounts.items(), key=lambda x: (abs(x[1]), x[0]))
    out: List[int] = []
    while len(rest) >= 3:
        i, a = rest[-1]
        left = [abs(v) for _, v in rest[:-1]]
        n = len(left)
        med = left[n // 2] if n % 2 else (left[n // 2 - 1] + left[n // 2]) / 2
        if abs(a) < MIXED_MIN or abs(a) < MIXED_RATIO * med:
            break
        out.append(i)
        rest.pop()
    return out


def mixed_categories(ledger: Ledger, config: dict, bereiche: List[dict], banks: Optional[Set[str]] = None,
                     skip: Optional[Set[int]] = None, hidden: Optional[Set[str]] = None, before: Optional[date] = None) -> List[dict]:
    """The categories with payments that stand out (standing_out) among those that count as income or an expense -- or in a
    property's rows -- in the areas you categorise; in the others (hidden: their ids; a company with countless bookings, say)
    only a property's categories, where the cash flow goes most wrong. On your bank accounts (banks; None: all),
    booked on or after the day you chose (before). Left out: transfers between your accounts (skip: their ids), transfer
    categories, a purchase's category (price or costs: an investment by its name), categories you count elsewhere (saving,
    financing, left out), accounts in another currency, and the payments you confirmed as belonging there
    (cashflow.mixed_ok). [{path, ids (largest first), sum (of those, signed, euros), count (bookings of the category)}],
    the largest sums first; a category of several areas once."""
    kf = config.get("cashflow") or {}
    ok = {int(i) for i in (kf.get("mixed_ok") or []) if str(i).lstrip("-").isdigit()}
    is_transfer = transfer_check(config)
    objekte = [norm_cat(str(im.get("category"))) for im in config.get("real_estate") or [] if isinstance(im, dict) and im.get("category")]
    skip = skip or set()
    found: Dict[str, dict] = {}
    for b in bereiche:
        only_props = bool(hidden and str(b.get("id")) in hidden)
        accs = {a.uuid for a in b.get("leaves") or [] if (banks is None or a.uuid in banks) and not foreign_currency(a)}
        if not accs:
            continue
        company = b.get("kind") == "company"
        per: Dict[str, Dict[int, float]] = defaultdict(dict)
        for t in ledger.txs:
            if t.account_uuid not in accs or not t.booked or not t.category_path or t.id in skip or (before and t.booking_date < before):
                continue
            if MARK in t.purpose:                 # Kontor's own bookings
                continue
            c = norm_cat(t.category_path)
            if c and c not in categorize.STANDARD:     # MoneyMoney's default ("Unkategorisiert") is none
                per[c][t.id] = t.amount
        totals = category_totals(ledger, accs)
        for path, amounts in per.items():
            if len(amounts) < 3 or is_transfer(path) or purchase_kind(path):
                continue
            pos, yours = position_of(path, config, totals, company)
            prop = any(path == c or path.startswith(c + " / ") for c in objekte)
            if only_props and not prop:
                continue
            counts = (prop and not (pos in ("repayment", "loan_interest") or (yours and pos in ("saving", "ignore", "partners"))))\
                or POS.get(pos, ("",))[0] in ("income", "expenses")
            if not counts:
                continue
            ids = [i for i in standing_out(amounts) if i not in ok]
            if not ids:
                continue
            f = found.setdefault(path, {"path": path, "ids": [], "sum": 0.0, "count": 0, "_amt": {}})
            f["ids"] += ids
            f["_amt"].update((i, amounts[i]) for i in ids)
            f["sum"] = round(f["sum"] + sum(amounts[i] for i in ids), 2)
            f["count"] += len(amounts)
    for f in found.values():
        amt = f.pop("_amt")
        f["ids"].sort(key=lambda i: (-abs(amt[i]), i))
    return sorted(found.values(), key=lambda f: (-abs(f["sum"]), f["path"]))


def classify(ledger: Ledger, leaves: List[Account], roles: Dict[str, str], config: dict, months: List[Tuple[int, int]],
             verlauf: Dict[str, str], areas: Optional[Dict[str, str]] = None, company: bool = False,
             objekte: Optional[Dict[str, str]] = None, learned: Optional[dict] = None, area_id: str = "", props: Tuple[str, ...] = ()):
    """Cash flow rows of an area. Every booking of its accounts counts once: a transfer within the area (both bookings found)
    as one row that leaves the net worth unchanged, everything else with its amount. areas: account -> name of its area (all
    areas; transfers between areas are contributions/withdrawals); company: this area is a company; objekte: category ->
    property (its own rows); props: the names of the area's properties (its only one takes estimated rent and costs); learned: the patterns learned from your categories (categorize) -- a booking without a category
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
        interest, a repayment or the property's purchase, or you chose saving or leaving it out."""
        r = pos_memo.get(cat)
        if r is None:
            # the most specific property's category (one property's may lie below another's)
            hits = [c for c in objekte if cat == c or cat.startswith(c + " / ")]
            obj = objekte[max(hits, key=len)] if hits else None
            pos, yours = position_of(cat, config, totals, company)
            # (nor its purchase: price and purchase costs are an investment, also in a category below the property's own)
            if obj and (pos in ("repayment", "loan_interest") or (yours and pos in ("saving", "ignore", "partners"))
                        or (pos == "saving" and purchase_kind(cat))):
                obj = None
            r = pos_memo[cat] = (pos, obj)
        return r

    def pairable(t: Tx) -> bool:
        """A bank booking that may be the other side of a booking in an offline account: no category, or one for saving or a
        repayment -- never income or an expense."""
        return not t.category_path or place(norm_cat(t.category_path))[0] in ("saving", "repayment")
    def between_position(t: Tx) -> Tuple[str, Optional[str], bool]:
        """A payment between two of your areas: (its category, the position it counts in, chosen by you)."""
        c0 = norm_cat(t.category_path)
        if not c0:
            return c0, guess_position(t, company, by_name=False), False
        g0, yours = position_of(c0, config, totals, company)
        return c0, (g0 if yours else recognised_position(c0, totals.get(c0, 0.0) > 0, company)), yours

    def paid_for(g0: Optional[str]) -> bool:
        return g0 in POS and (POS[g0][0] in ("income", "expenses") or g0 == "loan_interest")      # interest paid is a cost as well

    def paid_for_something(t: Tx) -> bool:
        """A payment to another area that pays for something (a salary, rent): no contribution, it claims no booking."""
        return not (t.category_path and is_transfer(t.category_path)) and paid_for(between_position(t)[1])

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

    def claimable(o: Tx) -> bool:
        """A booking by you in a manual account (capital account, stake, loan) that a payment into another area may claim below."""
        oa = ledger.accounts[o.account_uuid]
        return roles.get(oa.uuid, "other") in ("participations", "receivables", "liabilities") and oa.offline and oa.uuid not in depots \
            and not _value_adjustment(o) and not foreign_currency(oa) and not _is_cost(o, cost_words)
    def tied_word(o: Tx, name: str) -> bool:
        """As tied, but the area's name only as a whole word ("Privat", not "Privatdarlehen Meier")."""
        oa = ledger.accounts[o.account_uuid]
        word = re.compile(r"(?<!\w)" + re.escape(name.casefold()) + r"(?!\w)")
        return name in mirror_areas.get(oa.uuid, ()) or stake_company.get(oa.uuid) == name \
            or any(word.search((x or "").casefold()) for x in (oa.name, o.name, o.purpose))
    # kept for that: a booking in an account tied to another area (its name as a word, a mirror into it, its participation) with
    # a payment to (from) that area of the opposite amount close by, at least as close as any payment it could pair with by
    # amount alone -- not taken for that other payment first (a loan to your partner booked on "Darlehen an Partnerin" next to
    # a friend's repayment of the same amount). Not for a payment that pays for something (it claims no booking below)
    own_ibans_ = ledger.own_ibans()
    to_area: Dict[int, List[Tuple[Tx, str]]] = defaultdict(list)      # amount in cents -> payments to another area and its name
    by_amount: Dict[int, List[Tx]] = defaultdict(list)                # amount in cents -> payments it could pair with by amount
    for t in in_root:
        if roles.get(t.account_uuid) != "cash":
            continue
        p_t = own_ibans_.get(t.counter_iban) if t.counter_iban else None
        name = (beteiligungs_gruppen.get(p_t) or areas.get(p_t)) if p_t else None
        if name and name != self_name and not foreign_currency(ledger.accounts[p_t]) and not paid_for_something(t):
            to_area[int(round(t.amount * 100))].append((t, name))
        elif p_t is None:
            by_amount[int(round(t.amount * 100))].append(t)
    # (not a rival that says "transfer" and has another such booking of the opposite amount close by -- other than the booking
    # in question: that is its other side)
    says = lambda t: bool(t.category_path) and is_transfer(t.category_path)
    marked_tr: Dict[int, List[Tx]] = defaultdict(list)
    for t in in_root:
        if says(t):
            marked_tr[int(round(t.amount * 100))].append(t)
    # (nor a rival that names its counterparty, which this booking does not, while another booking close by does -- a friend's
    # payment beside "Einlage Gamma KG", "Darlehen an Freund" three days later: that one is its other side)
    def names(o: Tx, who: List[str]) -> bool:
        text = " ".join(fold_text(x or "") for x in (ledger.accounts[o.account_uuid].name, o.name, o.purpose))
        return any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text) for w in who)
    by_cents: Dict[int, List[Tx]] = defaultdict(list)
    for o in in_root:
        if claimable(o):
            by_cents[int(round(o.amount * 100))].append(o)

    def own_other(t: Tx, o: Tx) -> bool:
        who = [w for w in re.split(r"[\s,./-]+", fold_text(t.name)) if len(w) >= 3]
        return bool(who) and not names(o, who) and any(u.id != o.id and abs((u.booking_date - t.booking_date).days) <= PAIR_DAYS
                                                       and names(u, who) for u in by_cents.get(-int(round(t.amount * 100)), ()))
    kept: Set[int] = set()
    wants: List[Tuple[int, int, int]] = []               # (days apart, payment, booking): the booking may be kept for that payment
    for o in in_root:
        k = -int(round(o.amount * 100))
        if not claimable(o) or k not in to_area:
            continue
        gap = lambda t: abs((t.booking_date - o.booking_date).days)
        rival = lambda t: not (says(t) and any(u.id != o.id and u.account_uuid != t.account_uuid and abs((u.booking_date - t.booking_date).days) <= PAIR_DAYS_CAT
                                               for u in marked_tr.get(-k, ())))
        # (only a payment that may pair with it by amount at all -- a transfer or pairable, never one paid for something: an
        # insurance of that amount on the day must not let a top-up take the contribution's counter-booking)
        near = min((gap(t) for t in by_amount.get(k, ()) if (says(t) or pairable(t)) and rival(t) and not own_other(t, o)), default=COUNTER_DAYS)
        wants.extend((gap(t), t.id, o.id) for t, name in to_area[k] if gap(t) <= min(near, COUNTER_DAYS) and tied_word(o, name))
    # one booking per payment to the area, the closest first: of two bookings by hand beside one such payment (lent by transfer
    # and the same amount in cash on that day) only one is kept -- the other still pairs by amount with the payment without
    # an IBAN (kept as well, it stayed a change in value, and the cash "without category")
    paid: Set[int] = set()
    for _gap, t_id, o_id in sorted(wants):
        if t_id not in paid and o_id not in kept:
            paid.add(t_id); kept.add(o_id)
    mate, partner, by_cat = pair_transfers(ledger, in_root, flows, roles, is_transfer, cost_words, kf, pairable, keep=kept)
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
        if claimable(o) and mate.get(o.id) is None:
            pool[cents_(o.amount)].append(o)
    claims_by: List[Tuple[Tx, List[Tx], List[Tx]]] = []
    rivals: Dict[int, List[Tx]] = defaultdict(list)      # amount in cents -> payments that pair by amount alone (no IBAN of yours)
    for amount_, lst in by_amount.items():
        for r in lst:
            m_ = mate.get(r.id)
            if (by_cat[r.id] or pairable(r)) and (m_ is None or (m_.account_uuid != r.account_uuid and roles.get(m_.account_uuid) != "cash"
                                                                  and m_.account_uuid in ledger.accounts and ledger.accounts[m_.account_uuid].offline)):
                rivals[amount_].append(r)
    for t in in_root:
        p_t = partner.get(t.id)
        if roles.get(t.account_uuid) != "cash" or mate.get(t.id) is not None or p_t is None:
            continue
        name = beteiligungs_gruppen.get(p_t) or areas.get(p_t)
        if not name or name == self_name or (p_t in ledger.accounts and foreign_currency(ledger.accounts[p_t])) \
                or paid_for_something(t):
            continue                                     # paid for something, or into another currency: no contribution
        c = [o for o in pool.get(-cents_(t.amount), []) if abs((o.booking_date - t.booking_date).days) <= COUNTER_DAYS]
        lk = [o for o in c if tied(o, name)]
        # a booking not tied to that area which a payment without an IBAN could just as well belong to (the opposite amount, as
        # near or nearer, within PAIR_DAYS -- unpaired, or paired by amount alone with another booking by hand: among many of
        # one amount the pairs may have shifted by one) is not this payment's: it stays as it was, the payment a plain
        # contribution -- on both sides (found by a night's random case: 3.17.16)
        # ... nor one that names the very counterparty such a payment names and this payment does not (a friend's loan booked
        # a day after his payment, a transfer to the children's area on the day itself: the name says whose it is, not the
        # day -- the night's cash flow cases, 3.17.89)
        named = lambda r, o: bool((o.name or "").strip()) and (r.name or "").strip().casefold() == o.name.strip().casefold() \
            and (t.name or "").strip().casefold() != o.name.strip().casefold()
        c = [o for o in c if o in lk or not any(
            abs((r.booking_date - o.booking_date).days) <= (PAIR_DAYS if named(r, o) else min(PAIR_DAYS, abs((o.booking_date - t.booking_date).days)))
            for r in rivals.get(cents_(t.amount), ()))]
        if c:
            claims_by.append((t, lk, c))
    # in steps by distance (the same day, up to PAIR_DAYS, up to COUNTER_DAYS), each with the tied accounts first, and within a
    # step day by day: what is clear in an earlier step is out of the later ones -- of two payments the nearer one takes the
    # booking, but a tied account a day further beats one that is not (a contribution every week stays linked; a mirrored
    # booking that came days later is found all the same)
    reserved: Dict[int, Tx] = {}
    tied_ids = {o.id for _, lk, _ in claims_by for o in lk}
    windows = ((0,), range(1, PAIR_DAYS + 1), range(PAIR_DAYS + 1, COUNTER_DAYS + 1))
    for phase, limit in ((p_, l_) for w_ in windows for p_ in (1, 2) for l_ in w_):
        used = {o.id for o in reserved.values()}
        lists = [(t, [o for o in (lk if phase == 1 else [x for x in c if x.id not in tied_ids])
                      if o.id not in used and abs((o.booking_date - t.booking_date).days) <= limit])
                 for t, lk, c in claims_by if t.id not in reserved]
        n_claims = Counter(o.id for _, c in lists for o in c)
        for t, c in lists:
            if len(c) == 1 and n_claims[c[0].id] == 1:
                reserved[t.id] = c[0]
        # several payments claim the same bookings and nobody else does: if the payments are alike (same account, amount,
        # day and other side -- two transfers of one amount on one day) and at least as many as the bookings, or the bookings
        # are alike (same account, amount and day) and at least as many as the payments, which went into which makes no
        # difference -- each takes one, in order
        alike: Dict[frozenset, List[Tuple[Tx, List[Tx]]]] = defaultdict(list)
        for t, c in lists:
            if c and t.id not in reserved:
                alike[frozenset(o.id for o in c)].append((t, c))
        for ids, members in alike.items():
            if len(members) + len(ids) < 3 or any(n_claims[i] != len(members) for i in ids):
                continue
            same_t = len({(t.account_uuid, cents_(t.amount), t.booking_date, partner.get(t.id)) for t, _ in members}) == 1
            same_o = len({(o.account_uuid, cents_(o.amount), o.booking_date) for o in members[0][1]}) == 1
            if not ((same_t and len(ids) <= len(members)) or (same_o and len(members) <= len(ids))):
                continue
            books = sorted({o.id: o for o in members[0][1]}.values(), key=lambda o: (o.booking_date, o.id))
            for (t, _), o in zip(sorted(members, key=lambda m: m[0].id), books):
                reserved[t.id] = o

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

    def property_row(t: Tx, cat: str, obj: str, mk: str, det: str) -> None:
        """Rent or costs of a property: by the category's sum (a subcategory such as "Hausgeld"); on the property's own category
        by the booking."""
        inc = (t.amount > 0) if (cat in objekte or not cat) else totals.get(cat, 0.0) > 0
        sec = "income" if inc else "expenses"
        row = "%s · %s" % (obj, "Miete" if inc else "Kosten")
        R.add(sec, row, row, mk, t.amount, ord=POS["rental" if inc else "property_costs"][2] + 0.5, property_name=obj, detail=det,
              lbl=("cf_objekt_miete" if inc else "cf_objekt_kosten", obj))

    counter_ids = {o.id for o in reserved.values()}      # counter-bookings of payments between your areas (counter_row)

    def own_category(t: Tx) -> Tuple[Optional[str], Optional[str]]:
        """(position, property) of the category of a booking in an account that is no bank account: a category counts in every
        account (only without one does Kontor work it out) -- not a transfer's, nor on Kontor's own bookings or on the
        counter-booking of a payment (the payment counts)."""
        cat = norm_cat(t.category_path)
        if not cat or is_transfer(cat) or marks_in(t.text) or t.id in counter_ids:
            return None, None
        return place(cat)

    def category_row(t: Tx, pos: Optional[str], obj: Optional[str], mk: str) -> bool:
        """Income or an expense by the category, as a bank booking would count (a property's in its rows) -- e.g. what a landlord
        kept of a deposit for damage, booked out of the receivable. Saving, a repayment, a contribution or "leave out" need a
        payment: not here."""
        if obj:
            property_row(t, norm_cat(t.category_path), obj, mk, norm_cat(t.category_path))
        elif pos in POS and POS[pos][0] in ("income", "expenses"):
            row, key = position_row(pos, company)
            R.add(POS[pos][0], row, row, mk, t.amount, ord=POS[pos][2], lbl=(key,), detail=norm_cat(t.category_path))
        else:
            return False
        return True

    charged: Dict[str, Dict[str, List[Tx]]] = defaultdict(lambda: defaultdict(list))      # loan -> month -> its interest bookings

    def own_row(t: Tx, acc: Account, role: str, mk: str) -> None:
        """A booking of an account that is no bank account (loan, receivable, asset): interest, income or an expense by its
        category, or a change of its value. Interest and the category come with the account's other side -- the debt repaid,
        the receivable paid back, the asset sold -- which lists no booking (it is listed with the interest or the category)."""
        nonlocal unclear
        loan = role in ("liabilities", "receivables")
        if not loan and role not in ASSET_LIKE:
            R.add("unclear", "Konto ohne Position", acc.name + " (Position unbekannt)", mk, t.amount, kind="unclear", tx=t.id,
                  lbl=("cf_position_unbekannt", acc.name), glbl=("cf_konto_ohne_position",)); unclear += 1
            return
        pos, obj = own_category(t)
        interest = loan and (_is_cost(t, cost_words) or (not obj and (pos == "loan_interest" or (role == "receivables" and pos == "capital_income"))))
        if interest and role == "liabilities":
            R.add("financing", row=acc.name + " / Zinsen", mk=mk, amount=t.amount, account=acc.uuid, kind="interest", nw=True, lbl=("cf_name", acc.name), **_grp(FIN_GROUPS, "interest"))
            charged[acc.uuid][mk].append(t)
        elif interest:
            # interest on a loan you granted is investment income like any interest received (user, 2026-11-25; it stood under
            # investing, beside the loan) -- interest you pay stays with financing
            row, key = position_row("capital_income", company)
            R.add("income", row, row, mk, t.amount, ord=POS["capital_income"][2], lbl=(key,), detail=norm_cat(t.category_path))
        elif not category_row(t, pos, obj, mk):
            R.add("valuation", acc.name, acc.name, mk, t.amount, account=acc.uuid, kind="account", nw=True)
            return
        if role == "liabilities" and not interest and t.amount < 0:      # a bill booked as owed: a debt taken up (never a negative repayment)
            R.add("financing", row=acc.name + " / Aufnahme", mk=mk, amount=-t.amount, account=acc.uuid, kind="drawdown", nw=False, lbl=("cf_name", acc.name), tx=-1, **_grp(FIN_GROUPS, "drawdown"))
        elif role == "liabilities":
            R.add("financing", row=acc.name + " / Tilgung", mk=mk, amount=-t.amount, account=acc.uuid, kind="repayment", nw=False, lbl=("cf_name", acc.name), tx=-1, **_grp(FIN_GROUPS, "repayment"))
        elif role == "receivables":
            R.add("investing", row=acc.name + " / Rückzahlung", mk=mk, amount=-t.amount, account=acc.uuid, kind="payback", nw=False, lbl=("cf_name", acc.name), tx=-1, **_grp(INVEST_GROUPS, "receivables"))
        else:
            R.add("investing", row=acc.name, mk=mk, amount=-t.amount, account=acc.uuid, kind="account", nw=False, tx=-1, **_grp(INVEST_GROUPS, role))

    # Money moved into (or out of) an account that has balances only -- a depot, a fixed deposit, a P2P account: its other
    # side is no booking, so nothing pairs. A booking without a category of its own (none, or a transfer's without a counterpart)
    # is recognised (user, 2026-11-25: "as widely as possible, also where I do not categorise"): by your choice for the
    # recipient, or by what it says (a securities trade, a savings plan, an ISIN beside a word of buying, a fixed deposit ...)
    # -- into the one such account at the booking's own bank, else the one its words name, else the area's only one. An
    # estimate: listed with the recipients (Cashflow-Positionen), where you change it. Not by how you categorised the
    # recipient before: a broker's invoice is no saving (test_an_estimate_is_never_saving_or_repayment).
    held = [u for u in sorted(root_leaves) if u in ledger.accounts and verlauf.get(u) == "balances" and roles.get(u) in ASSET_LIKE]
    bank_of = lambda u: re.sub(r"\D", "", ledger.accounts[u].bank_code or "")

    def held_account(t: Tx, kind: str, weak: bool = False) -> Optional[str]:
        """The account without bookings a move of this kind goes into: of its kind (a trade: securities; a fixed deposit:
        fixed investments) the one at the bank the booking names (its counter IBAN, without one the booking's own bank), else
        the one whose name the booking says, else -- said outright -- the only one of its kind."""
        of_kind = [u for u in held if roles.get(u) == ("term_investments" if kind == "term" else "securities")]
        iban = (t.counter_iban or "").replace(" ", "").upper()
        own = bank_of(t.account_uuid)
        at = [u for u in of_kind if len(bank_of(u)) >= 4 and (iban[4:4 + len(bank_of(u))] == bank_of(u) if iban else bank_of(u) == own)]
        if len(at) == 1:
            return at[0]
        if weak:
            return None
        said = name_words((t.name or "") + " " + (t.purpose or ""))
        named = [u for u in (at or of_kind) if said & name_words(ledger.accounts[u].name)]
        return named[0] if len(named) == 1 else of_kind[0] if len(of_kind) == 1 and not at else None

    def note_recipient(t: Tx, key: str, cat: str, target: Optional[str], how: str, auto: Tuple[Optional[str], str]) -> None:
        """A booking whose money goes where no booking shows it, kept by its recipient (for the list under Cashflow-Positionen)."""
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
        if cat and cat not in sv["categories"]:
            sv["categories"].append(cat)
        if not cat:
            sv["estimated"] = sv.get("estimated", 0) + 1          # of them: without a category (Kontor's estimate)
        # by category: the recipient's bookings may go to different accounts (the same account found another way is no mix)
        if sv["target"] != target or (not target and sv["how"] != how):
            sv["how"], sv["target"] = "mixed", None
        if (sv["auto_target"], sv["auto_how"]) != auto:
            sv["auto_how"], sv["auto_target"] = "mixed", None

    def unseen(t: Tx, transfer: bool) -> Optional[Tuple[Optional[str], str, Optional[str]]]:
        """(account or None, how, Kontor's own estimate) for a booking whose other side is an account without bookings -- None:
        not such a booking. how: "recipient" / "external" (your choice), "estimated", "" (a move, but into which account?).
        transfer: it has a transfer's category (and no counterpart). Your choice for the recipient counts for his transfers
        and for what says it is a move -- never for the rest he sends without a category (an invoice, a dividend, a fee)."""
        kind, weak = said_move(fold_text(" ".join((t.name or "", t.purpose or "", t.booking_text or ""))))
        est = held_account(t, kind, weak) if kind else None
        if not transfer and (not kind or (weak and est is None)):
            return None
        e_to = emp_zu_konto.get(party_key(t))
        if e_to == "external":
            return None, "external", est
        if e_to in root_leaves:
            return e_to, "recipient", est
        if est:
            return est, "estimated", est
        return (None, "", None) if transfer or held else None

    # money back under a category that undoes a payment of the same amount within ten days (a returned debit): no loan taken up
    neg_by: Dict[Tuple[str, int], List[Tx]] = defaultdict(list)
    for o in in_root:
        if o.amount < 0 and o.category_path:
            neg_by[(norm_cat(o.category_path), int(round(-o.amount * 100)))].append(o)
    undone: Set[int] = set()
    for o in sorted((o for o in in_root if o.amount > 0 and o.category_path), key=lambda o: o.booking_date):
        cands = neg_by.get((norm_cat(o.category_path), int(round(o.amount * 100)))) or []
        n = next((n for n in cands if abs((o.booking_date - n.booking_date).days) <= 10), None)
        if n is not None:
            undone.add(o.id)
            cands.remove(n)
    loan_no_account: Dict[str, float] = defaultdict(float)     # taken up and repaid by category: the debt is in no account
    prop_marks = [(n, property_marks(n)) for n in props]
    generic: List[bool] = []

    def generic_rent() -> bool:
        """You book rent or a property's costs under a category of their own that belongs to no property: estimates stay beside
        it (the property's calculation would plan them a second time)."""
        if not generic:
            generic.append(any(c and place(c)[0] in ("rental", "property_costs") and not place(c)[1] for c in totals))
        return generic[0]

    def estimated_property(t: Tx) -> Optional[str]:
        """The property a booking without a category belongs to: the one its name or purpose names, else the area's only one."""
        text = property_marks(" ".join((t.name or "", t.purpose or "", t.booking_text or "")))
        named = [n for n, m in prop_marks if m[0] and marks_fit(m, text)]
        return named[0] if len(named) == 1 else props[0] if len(props) == 1 and not named else None

    # A lender's account that credits only the repayment part of a rate (the interest it keeps is no booking there; the user
    # knows accounts that credit the whole rate and book the interest apart -- those pair as transfers -- and asked for the
    # others to work as well, 2026-11-25). The rate left the bank without a counterpart and says which loan it is for: its
    # IBAN (or a mark); else, only without a category of its own (none, a transfer's, a repayment's): the loan's number in
    # its text, or a word for a loan there (_RATE_SAID) and a word of the loan's name no other loan has, or such a word and
    # the area has one loan only. The loan has one credit that can be its part: within PAIR_DAYS_IBAN days, less than the rate (not below
    # a twentieth), without a counterpart or a category of its own, not booked by Kontor, not taken back, not the amount
    # of another payment that could be its counterpart -- and the loan books no interest or fee near it, and no credits
    # that are the whole rate, in one or in parts. Of several credits the one that names the account the rate left; as many
    # rates as credits go in the order of their days; else nothing is split. Where two payments want the same credit, the
    # one that names the loan best has it; equal ones leave it. The credit is the repayment, the rest of the rate the
    # interest. Never a capital account or a deposit owed back.
    part_of: Dict[int, Tx] = {}                          # the rate -> the loan's credit
    part_done: Set[int] = set()
    claimed = {r_.id for r_ in reserved.values()}       # bookings by hand a payment to another area took
    lone = lambda x: mate.get(x.id) is None and x.id not in reserved and x.id not in claimed
    capital = shareholder_ids(ledger)
    by_loan: Dict[str, List[Tx]] = {u: [] for u in sorted(root_leaves) if roles.get(u) == "liabilities" and u in ledger.accounts
                                    and u not in capital and "kaution" not in fold_text(ledger.accounts[u].name)}
    paid: Dict[int, List[Tx]] = defaultdict(list)       # cents -> payments from the bank without a counterpart
    own_cat = lambda x: bool(x.category_path) and not is_transfer(x.category_path) and place(x.category_path)[0] != "repayment"
    for x in in_root:
        if x.account_uuid in by_loan:
            by_loan[x.account_uuid].append(x)
        elif roles.get(x.account_uuid) == "cash" and x.amount < 0 and lone(x) and not own_cat(x):
            paid[int(round(-x.amount * 100))].append(x)       # (one with a category of its own is no counterpart of a credit)
    close = lambda a, b: abs((a.booking_date - b.booking_date).days) <= PAIR_DAYS_IBAN
    loan_no = {u: re.sub(r"\D", "", ledger.accounts[u].account_number or "") for u in by_loan}
    loan_words = {u: name_words(ledger.accounts[u].name) - _LOAN_GENERIC for u in by_loan}
    for u in by_loan:                                    # a word two loans share names neither
        loan_words[u] = {w for w in loan_words[u] if not any(w in name_words(ledger.accounts[v].name) for v in by_loan if v != u)}

    def rate_for(t: Tx) -> Tuple[Optional[str], int]:
        """(the loan account a payment says it is a rate of, how surely) -- (None, 0): none, or not one alone."""
        p_t = partner.get(t.id)
        if p_t is not None:
            return (p_t, 4) if p_t in by_loan else (None, 0)
        text = " ".join((t.name or "", t.purpose or ""))
        low = fold_text(text)
        if (t.counter_iban and own_ibans_.get(t.counter_iban)) or own_cat(t):
            return None, 0                               # it names another account of yours, or you gave it a category
        digits = re.sub(r"[^0-9a-z]", "", low)
        said = [u for u in by_loan if len(loan_no[u]) >= 6 and loan_no[u] in digits]
        if len(said) == 1:
            return said[0], 3
        if not _RATE_SAID.search(low):
            return None, 0                               # it says nothing of a loan
        said = [u for u in by_loan if loan_words[u] & name_words(text)] if not said else []
        if len(said) == 1:
            return said[0], 2
        return (next(iter(by_loan)), 1) if not said and len(by_loan) == 1 else (None, 0)

    could: Dict[int, List[Tx]] = {}                      # the rate -> the credits that can be its part
    rates: Dict[int, Tuple[Tx, str, int]] = {}          # the rate, its loan, how surely
    for t in in_root:
        if t.amount >= 0 or roles.get(t.account_uuid) != "cash" or not by_loan or not lone(t):
            continue
        p_t, sure = rate_for(t)
        if p_t is None:
            continue
        cents = int(round(-t.amount * 100))
        near = [x for x in by_loan[p_t] if close(x, t)]
        if any(x.amount < 0 and _is_cost(x, cost_words) for x in near):
            continue                                     # the loan books its interest itself: nothing to split
        got = [x for x in near if x.amount > 0.005 and lone(x)]
        if any(int(round(x.amount * 100)) == cents for x in got) or (len(got) > 1 and int(round(sum(x.amount for x in got) * 100)) == cents):
            continue                                     # the whole rate was credited (in one, or in parts)
        c = [x for x in got if -t.amount * 0.05 <= x.amount < -t.amount - 0.005 and (not x.category_path or is_transfer(x.category_path))
             and MARK not in (x.purpose or "") and not _is_cost(x, cost_words)
             and not any(y.id != t.id and close(y, x) for y in paid.get(int(round(x.amount * 100)), ()))
             and not any(y.amount == -x.amount and close(y, x) for y in by_loan[p_t])]
        named = [x for x in c if x.counter_iban and own_ibans_.get(x.counter_iban) == t.account_uuid]
        if c:
            could[t.id], rates[t.id] = (named if len(named) == 1 else c), (t, p_t, sure)
    by_day = lambda x: (x.booking_date, x.id)
    for i in sorted(could):                              # as many rates as credits (a rate made up for): in the order of their days
        ids = {x.id for x in could[i]}
        same = sorted((rates[k][0] for k in could if rates[k][1:] == rates[i][1:] and {x.id for x in could[k]} == ids), key=by_day)
        if len(ids) > 1 and len(same) == len(ids):
            for t, x in zip(same, sorted(could[i], key=by_day)):
                could[t.id] = [x]
    wants: Dict[int, List[Tuple[int, Tx]]] = defaultdict(list)      # the credit -> (how surely, the payment) that want it
    credit: Dict[int, Tx] = {}
    for i, c in could.items():
        if len(c) == 1:
            wants[c[0].id].append((rates[i][2], rates[i][0]))
            credit[c[0].id] = c[0]
    for i, ws in wants.items():
        top = max(sure for sure, _ in ws)
        best = [t for sure, t in ws if sure == top]
        if len(best) == 1:
            part_of[best[0].id] = credit[i]
            part_done.add(i)

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
            if o is not None or t.id in part_done:
                continue                                 # the other side (or the bank account) shows the transfer
            own_row(t, acc, role, mk)
            continue
        if t.id in part_of:                              # a rate of which the loan credits only the repayment (see above)
            x = part_of[t.id]
            name = ledger.accounts[x.account_uuid].name
            paired.add(t.id)
            R.add("financing", row=name + " / Tilgung", mk=mk, amount=-x.amount, account=x.account_uuid, kind="repayment", nw=False, lbl=("cf_name", name),
                  **_grp(FIN_GROUPS, "repayment"))
            R.add("financing", row=name + " / Zinsen", mk=mk, amount=round(t.amount + x.amount, 2), account=x.account_uuid, kind="interest", nw=True,
                  lbl=("cf_name", name), **_grp(FIN_GROUPS, "interest"))
            if month_key(x.booking_date) != mk:          # credited in another month: that part is in transit over the month end
                pairs.append((t.booking_date, x.booking_date, x.amount, t.account_uuid, x.account_uuid, t.id, x.id))
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
            # Everything else between areas is a contribution or withdrawal. A profit distribution is investment income, from
            # your own company as from any other (user, 2026-11-24): its value falls by it at the same time -- booked against
            # your participation by the rule for it, a change in value -- as a share's price falls by its dividend.
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
        hit = unseen(t, bool(by_cat[t.id])) if (by_cat[t.id] or not t.category_path) and guess is None else None
        if hit is not None:
            target, how, est = hit
            cat0 = norm_cat(t.category_path)
            note_recipient(t, party_key(t), cat0, target, how, (est, "depot" if est else ""))
            if target:
                kind = roles.get(target) if roles.get(target) in INVEST_GROUPS else "other"
                R.add("investing", row=ledger.accounts[target].name, mk=mk, amount=t.amount, account=target, kind="account", nw=False, **_grp(INVEST_GROUPS, kind))
                if target in depots:
                    inbound[target][mk] += -t.amount
                elif verlauf.get(target) == "balances" and roles.get(target) in ASSET_LIKE:
                    mapped_in[target][mk] += -t.amount
                continue
            if how == "external" and cat0:               # a transfer to no account in MoneyMoney: the money leaves the net worth
                R.add("investing", row=cat0 + " → extern", mk=mk, amount=t.amount, kind="category", nw=True, lbl=("cf_anlage_extern", cat0),
                      **_saving_grp("saving_group", company))
                continue
            # (open -- a move, but into which account -- or "no account" for a booking without a category: counted as before,
            # as a transfer without its counterpart or as income or an expense)
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
            if props and ((pos == "rental" and t.amount > 0) or (pos == "property_costs" and t.amount < 0)) and not generic_rent():
                obj = estimated_property(t)          # rent and costs of a property, estimated like the rest
            if pos == "housing" and company and objekte and t.amount < 0:    # a landlord: costs of the building
                pos = "property_costs"
        # an estimate only ever counts as income or expense (or interest) -- never as saving, repayment, transfer or left out
        if pos is None or pos not in POS or (not mine and pos in ("saving", "repayment", "ignore", "partners")):
            R.add(sec, "Ohne Kategorie", "Ohne Kategorie", mk, t.amount, ord=900, lbl=("cf_ohne_kategorie",))
            continue
        det = cat if mine else ""                        # "" = without a category in MoneyMoney (estimated)
        if obj:
            property_row(t, cat, obj, mk, det)
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
            # the costs of a purchase (notary, land transfer tax) go into no depot: without your choice they leave the net worth
            # Kontor sees, as "no account in MoneyMoney" (3.17.85; before, the area's only depot took them as paid in)
            # The price of a property or a company share goes into no depot either (3.17.87): with a counter-booking in the
            # asset's account it is found as any transfer, without one it stands as "without target account" until you name it.
            buy = purchase_kind(cat)
            costs = buy == "costs"
            auto = (c_to, "category") if c_to in root_leaves else (None, "external") if costs and not c_to \
                else (None, "") if buy == "price" and not c_to \
                else (depots[0], "depot") if len(depots) == 1 and not c_to else (None, "")
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
                  **({"lbl": lbl} if lbl else {}), **_saving_grp(kind, company))
            if target in depots:
                inbound[target][mk] += -t.amount
            elif target and verlauf.get(target) == "balances" and roles.get(target) in ASSET_LIKE:
                mapped_in[target][mk] += -t.amount      # an asset kept by balances: paid in, not a correction of its balance
            elif not target and how != "external":
                no_target[mk] += t.amount
            note_recipient(t, key, cat, target, how, auto)
        elif pos == "repayment" and t.amount > 0 and t.id not in undone:
            # money in under a repayment category: a loan paid out -- taken up, never a negative repayment
            R.add("financing", row="Darlehensaufnahme", mk=mk, amount=t.amount, kind="drawdown", nw=False, lbl=("cf_g_aufnahme",), detail=det,
                  **_grp(FIN_GROUPS, "drawdown"))
            loan_no_account[mk] += t.amount
        elif pos in ("repayment", "loan_interest"):
            if pos == "repayment":
                loan_no_account[mk] += t.amount
            R.add("financing", row=prow, mk=mk, amount=t.amount, kind="interest" if pos == "loan_interest" else "repayment", nw=pos == "loan_interest",
                  lbl=("pos_" + pos,), detail=det, **_grp(FIN_GROUPS, "interest" if pos == "loan_interest" else "repayment"))
        elif pos == "partners":
            # payments to and from partners outside your areas: a company's equity (financing); yours: money put into or taken
            # out of a company Kontor does not keep (investing) -- neither income nor expense
            if company:
                R.add("financing", row="Einlagen/Entnahmen Gesellschafter", mk=mk, amount=t.amount, kind="external", nw=True,
                      lbl=("cf_einlagen_gesellschafter",), detail=det, **_grp(FIN_GROUPS, "partners"))
            else:
                R.add("investing", row="Einlagen & Entnahmen", mk=mk, amount=t.amount, kind="external", nw=True, lbl=("pos_partners",),
                      detail=det, **_grp(INVEST_GROUPS, "participations"))
        else:
            row, key = position_row(pos, company)
            R.add(psec, row, row, mk, t.amount, ord=pord, lbl=(key,), detail=det)

    R.cur = None
    # Interest charged to a loan in a month in which less than that was credited to it (nothing: due at its end, deferred; or a
    # rate below its interest) raises the debt: what is left of it above the credits is taken up -- never a "repayment above
    # zero", as with a loan paid out. By the loan account's own bookings, not by the month's net: a rate that left the bank
    # in one month and its interest in the next is still a rate (the independent check of 3.17.87). The repayment row keeps
    # what it was for the plan (plan_hist): the usual payment, and a debt that keeps growing by its interest.
    R.plan_hist = {}
    for u, per in charged.items():
        key = ("financing", ledger.accounts[u].name + " / Tilgung")
        if key not in R.vals or roles.get(u) != "liabilities":
            continue
        credits: Dict[str, float] = defaultdict(float)
        for x in ledger.transactions(u):
            if x.booked and x.amount > 0:
                credits[month_key(x.booking_date)] += x.amount
        before = dict(R.vals[key])
        for mk, ts in per.items():
            more = round(min(max(R.vals[key].get(mk, 0.0), 0.0), max(-sum(x.amount for x in ts) - credits.get(mk, 0.0), 0.0)), 2)
            if more >= 0.005:
                R.vals[key][mk] -= more
                name = ledger.accounts[u].name
                for i, x in enumerate(ts):
                    R.add("financing", row=name + " / Aufnahme", mk=mk, amount=more if i == 0 else 0.0, account=u, kind="drawdown", nw=False, lbl=("cf_name", name),
                          tx=x.id, **_grp(FIN_GROUPS, "drawdown"))
                R.plan_hist[key] = before
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
    # a loan taken up or repaid by category: its debt is in none of your accounts, so the net worth Kontor sees moves by it
    # (a loan kept by its balances shows the same amount the other way as its change in value)
    for mk, v in loan_no_account.items():
        if abs(v) >= 0.005:
            R.add("valuation", "Darlehen ohne Konto", "Darlehen ohne Konto", mk, round(v, 2), kind="no_account", nw=True,
                  lbl=("cf_darlehen_ohne_konto",), glbl=("cf_darlehen_ohne_konto",))
    for mk, v in no_target.items():
        if abs(v) >= 0.005:
            R.add("valuation", "Anlage ohne Zielkonto", "Anlage ohne Zielkonto", mk, round(v, 2), kind="no_target", nw=True,
                  lbl=("cf_anlage_ohne_ziel",), glbl=("cf_anlage_ohne_ziel",))

    if unclear:
        warnings.append(trn("s_n_umbuchungen_unklar", unclear))
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
    words = name_words
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
    props = tuple(sorted(str(im.get("name") or "") for im in config.get("real_estate") or []
                         if isinstance(im, dict) and str(im.get("area") or "") == str(bereich.get("id"))))
    ckey = (getattr(ledger, "_kat_sig", None), str(bereich.get("id") or ""), back <= 0, tuple(a.uuid for a in leaves), json.dumps(roles, sort_keys=True),
            json.dumps(config.get("cashflow") or {}, sort_keys=True, default=str), tuple(months[0]) if months else None,
            tuple(months[-1]) if months else None, len(months), tuple(sorted(quelle.items())), company, learned_sig, tuple(sorted(objekte.items())), props,
            json.dumps([sorted(areas.items()), config.get("companies"), config.get("account_mirrors")], sort_keys=True, default=str))
    cache = ledger.__dict__.setdefault("_classify_cache", {})
    if ckey in cache:
        R, inbound, warn_c = copy.deepcopy(cache[ckey])        # Bereich unveraendert (z. B. Verlauf eines anderen Bereichs geaendert)
    else:
        R, inbound, warn_c = classify(ledger, leaves, roles, config, months, quelle, areas, company, objekte, learned, str(bereich.get("id") or ""), props)
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
                    first = fortgeschrieben.get(acc.uuid)
                    if abs(val) >= 0.005 and first and mk <= first:      # no balance known before: the first one carried back -- its own row
                        R.add("valuation", acc.name, acc.name + " / unbekannt", mk, val, account=acc.uuid, kind="depot", nw=True,
                              lbl=("cf_wert_unbekannt", acc.name, month_text(first)))
                    elif abs(val) >= 0.005:
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
            if (s, row) in getattr(R, "plan_hist", {}):  # what the plan goes on from, where interest not paid was moved out (classify)
                z["plan_hist"] = {mk: round(R.plan_hist[(s, row)].get(mk, 0.0), 2) for mk in mkeys}
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
                    and z["kind"] in ("repayment", "interest", "category", "drawdown"):
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


# Planning rules on three levels -- the area's default, a position (a row of the cash flow), a category inside it: the deepest
# level that sets a field counts, each field on its own (the method with its amount; the increase). An increase of 0: none.
PLAN_METHODS = ("rolling12", "rolling6", "prev_year", "fix", "yearly_amount", "budget", "none")
PLAN_AREA_METHODS = ("rolling12", "rolling6", "prev_year", "budget", "none")     # the area's default: methods without an amount
# Planning models: the area's default with one click -- for income, and for expenses (with the other rows a method plans:
# investing, financing). Without an increase: the area's rates (Steigerung Einnahmen; Ausgaben, else the inflation).
PLAN_MODELS = {
    "even": {"income": {"method": "rolling12"}, "expenses": {"method": "rolling12"}},
    "careful": {"income": {"method": "prev_year", "increase_percent_pa": 0.0}, "expenses": {"method": "rolling12"}},
    "prev_year": {"income": {"method": "prev_year", "increase_percent_pa": 0.0}, "expenses": {"method": "prev_year", "increase_percent_pa": 0.0}},
    "budget": {"income": {"method": "rolling12"}, "expenses": {"method": "budget"}},
}
PLAN_SIDES = {"income": ("income",), "expenses": ("expenses", "investing", "financing")}     # the sections each side's default plans


def plan_side(section: str) -> str:
    return "income" if section == "income" else "expenses"


def plan_one_off(section: str, z: dict) -> bool:
    """Rows not planned unless you give them a rule (the area's default does not reach them): contributions and withdrawals,
    loans taken up, transfers into or out of accounts, changes in value, what is unclear."""
    return section in ("valuation", "unclear") or z.get("kind") in ("external", "drawdown") or (section == "investing" and z.get("kind") in ("external", "account"))


def _plan_num(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool) or (isinstance(v, str) and not v.strip()):
        return None
    try:
        f = float(v.replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def plan_rule(cfg: Any, area: bool = False) -> dict:
    """The own rule of a position, a category or a side of the area's default -- only what it sets: the method (fixed amount and
    annual amount with their amount) and the increase in % p.a. (0: none)."""
    out: Dict[str, Any] = {}
    if not isinstance(cfg, dict):
        return out
    m = cfg.get("method")
    if m in (PLAN_AREA_METHODS if area else PLAN_METHODS):
        out["method"] = m
        if m in ("fix", "yearly_amount"):
            out["amount"] = _plan_num(cfg.get("amount")) or 0.0
    g = _plan_num(cfg.get("increase_percent_pa"))
    if g is not None:
        out["increase_percent_pa"] = g
    return out


def plan_defaults(plan: dict) -> Dict[str, dict]:
    """The area's default rule for each side (income; expenses with investing and financing): its method and, where set, its
    increase. Settings from before the rules per side: "default_method" for both."""
    dm = plan.get("default_method") if plan.get("default_method") in PLAN_AREA_METHODS else "rolling12"
    d = plan.get("defaults") if isinstance(plan.get("defaults"), dict) else {}
    out = {}
    for side in ("income", "expenses"):
        r = plan_rule(d.get(side), area=True)
        r.setdefault("method", dm)
        out[side] = r
    return out


def plan_model(plan: dict) -> Optional[str]:
    """The planning model the area's default is (None: an own choice)."""
    d = plan_defaults(plan)
    for k, m in PLAN_MODELS.items():
        if all(d[s]["method"] == m[s]["method"] and d[s].get("increase_percent_pa") == m[s].get("increase_percent_pa") for s in ("income", "expenses")):
            return k
    return None


def _year_before(mk: str) -> str:
    return "%04d-%s" % (int(mk[:4]) - 1, mk[5:])


def _round_group(raws: List[float]) -> List[float]:
    """Each value to cents so that they add up to their rounded sum exactly (the cents left over go where rounding cut most)."""
    r = [round(x, 2) for x in raws]
    k = int(round((round(sum(raws), 2) - sum(r)) * 100))
    if k:
        up = k > 0
        for i in sorted(range(len(raws)), key=lambda j: (raws[j] - r[j]) * (1 if up else -1), reverse=True)[:abs(k)]:
            r[i] = round(r[i] + (0.01 if up else -0.01), 2)
    return r


def _shares(weights: List[float], direction: float = 0.0) -> List[float]:
    """Parts of one by the weights. With a direction (the sign of what is shared): only weights in that direction count -- a
    category against it (refunds in an expense position) gets no part; none in it: equal parts. Without one: by their size."""
    ws = [max(w * (1 if direction > 0 else -1), 0.0) for w in weights] if direction else [abs(w) for w in weights]
    tw = sum(ws)
    if tw > 1e-9:
        return [w / tw for w in ws]
    side = [w * direction >= 0 for w in weights] if direction else [True] * len(weights)      # nothing in its direction lately:
    n = sum(side) or len(weights)                                                             # equal parts -- of those not against it
    return [(1.0 / n if (ok or not any(side)) else 0.0) for ok in side] if weights else []


def _plan_basis(method: str, hist: List[float], months: List[str], amount: Optional[float], budget: Optional[float]) -> Tuple[float, dict]:
    """The monthly base of a plan before its increase (every method but prev_year) and what it rests on, for the explanation:
    the months averaged, the budget, the amount. A budget method without a budget in MoneyMoney: the average of 12 months."""
    if method == "none":
        return 0.0, {}
    if method == "fix":
        a = round(float(amount or 0.0), 2)
        return a, {"amount": a, "value": a}
    if method == "yearly_amount":
        a = round(float(amount or 0.0), 2)
        return round(a / 12.0, 2), {"amount": a, "value": round(a / 12.0, 2)}
    info: Dict[str, Any] = {}
    if method == "budget":
        if budget is not None:
            return round(budget, 2), {"budget": round(budget, 2), "value": round(budget, 2)}
        info["fallback"] = True
    n = 6 if method == "rolling6" else 12
    vals = hist[-n:]                    # fewer closed months known (a new area): their average, not a twelfth of their sum
    if not vals:
        return 0.0, dict(info, n=0, value=0.0)
    v = round(sum(vals) / len(vals), 2)
    return v, dict(info, n=len(vals), months=[months[-len(vals)], months[-1]], value=v)


def _plan_factor(method: str, growth: float, i: int) -> float:
    """The increase of the i-th plan month (0: the first): month by month; prev_year: one year on the month a year before."""
    return 1 + growth / 100.0 if method == "prev_year" else (1 + growth / 100.0) ** ((i + 1) / 12.0)


def _overrides(cfg: dict, future: List[str]) -> Dict[str, float]:
    return {mk: float(v) for mk, v in (cfg.get("amounts") or {}).items() if mk in future and _plan_num(v) is not None}


def plan_position(z: dict, sec: str, cfg: dict, rule: dict, future: List[str], full_months: List[str],
                  budgets: Dict[str, float], row_of_cat: Dict[str, str]) -> None:
    """The plan of one position (z["plan"]) and, where it has categories, of each of them (their "plan"): the position is the
    sum of its categories -- each planned by its own rule, else the position's. rule: the position's own rule resolved
    (method, from, amount, increase, inc_from). A fixed amount, an annual amount or a budget of the position goes to its
    categories that follow it by their share of the last 12 closed months; a budget in MoneyMoney counts for the categories
    beneath it (a budget above several categories when all of them are in this row and planned by budget); a category without
    a budget: the average of 12 months. A value of your own for the position goes to its categories without a value of their
    own by their suggestion."""
    key = sec + "/" + z["row"]
    sign = (lambda v: v) if sec == "income" else (lambda v: -abs(v))
    ov = _overrides(cfg, future)
    method, amount, g = rule["method"], rule.get("amount"), rule["increase"]
    head = {"method": method, "from": rule["from"], "increase": g, "inc_from": rule["inc_from"]}
    if method in ("fix", "yearly_amount"):
        head["amount"] = amount
    dets = [d for d in z.get("details") or [] if isinstance(d, dict)]
    if not dets:                                         # a row of its own (no categories): planned as a whole
        bud = budgets.get(z["row"])
        bud = round(sign(bud), 2) if bud is not None else None
        was = z.get("plan_hist") or z["amounts"]
        basis, info = _plan_basis(method, [was.get(mk, 0.0) for mk in full_months], full_months, amount, bud)
        p = z["plan"] = {"method": method, "amount": amount, "increase_percent_pa": g, "budget": bud,
                         "amounts": {}, "proposal": {}, "overwritten": sorted(ov), "rule": head, "base": info}
        for i, mk in enumerate(future):
            if method == "prev_year":
                ly = _year_before(mk)
                v = (z["amounts"][ly] if ly in z["amounts"] else p["amounts"].get(ly, 0.0)) * _plan_factor(method, g, i)
            else:
                v = basis * _plan_factor(method, g, i)
            p["proposal"][mk] = round(v, 2)
            p["amounts"][mk] = ov.get(mk, round(v, 2))
        return
    ccfg = cfg.get("categories") if isinstance(cfg.get("categories"), dict) else {}
    cats = []
    for d in dets:
        c = d.get("category") or ""
        own_cfg = ccfg.get(c) if isinstance(ccfg.get(c), dict) else {}
        own = plan_rule(own_cfg)
        r = {"method": own["method"], "from": "category", "amount": own.get("amount")} if "method" in own else {"method": method, "from": rule["from"], "amount": amount}
        r["increase"], r["inc_from"] = (own["increase_percent_pa"], "category") if "increase_percent_pa" in own else (g, rule["inc_from"])
        hist = [d["amounts"].get(mk, 0.0) for mk in full_months]
        cats.append({"d": d, "cat": c, "r": r, "own": own, "ov": _overrides(own_cfg, future), "hist": hist, "w": sum(hist[-12:]),
                     "base": 0.0, "info": {}, "group": None})
    # a fixed or annual amount of the position: shared by the categories following it
    follow = [c for c in cats if c["r"]["from"] != "category" and c["r"]["method"] in ("fix", "yearly_amount")]
    if follow:
        p0 = _plan_basis(method, [], [], amount, None)[0]
        for c, s in zip(follow, _shares([c["w"] for c in follow], p0)):
            c.update(base=p0 * s + 0.0, group="amount", info={"share": round(s, 4), "of": p0, "of_kind": method, "value": round(p0 * s, 2) + 0.0})      # (+ 0.0: never −0,00)
    # budgets: those of MoneyMoney above or at the categories planned by budget, each shared by the categories beneath it
    users = [c for c in cats if c["r"]["method"] == "budget"]
    row_names = {c["cat"] for c in cats if c["cat"]}
    under = lambda n, b: n == b or n.startswith(b + " / ")

    def own_budgets(names: Set[str]) -> Dict[str, float]:
        """The budgets for these categories of the row: at or above them, all of their categories in this row and among them."""
        o = {b: v for b, v in budgets.items() if any(under(n, b) for n in names)
             and all(r == key for n, r in row_of_cat.items() if under(n, b)) and all(n in names for n in row_names if under(n, b))}
        return {b: v for b, v in o.items() if not any(a != b and under(b, a) for a in o)}
    own_b = own_budgets({c["cat"] for c in users if c["cat"]})
    all_b = own_budgets(row_names)
    pos_budget = round(sum(sign(v) for v in all_b.values()), 2) if all_b else None       # the position's budget (shown beside its method)
    for b, v in own_b.items():
        mine = [c for c in users if c["cat"] and under(c["cat"], b)]
        for c, s in zip(mine, _shares([c["w"] for c in mine], sign(v))):
            c.update(base=sign(v) * s + 0.0, group="budget:" + b, info={"budget": round(sign(v), 2), "share": round(s, 4), "budget_of": b, "value": round(sign(v) * s, 2) + 0.0})
    for c in cats:                                       # the rest: by its own history (a budget method without a budget: Ø 12)
        if c["group"] is None:
            c["base"], c["info"] = _plan_basis(c["r"]["method"], c["hist"], full_months, c["r"]["amount"], None)
    groups: Dict[str, List[dict]] = defaultdict(list)
    for c in cats:
        if c["group"]:
            groups[c["group"]].append(c)
        c["d"]["plan"] = {"method": c["r"]["method"], "amount": c["r"]["amount"], "increase_percent_pa": c["r"]["increase"],
                          "amounts": {}, "proposal": {}, "overwritten": sorted(c["ov"]), "from_position": [],
                          "rule": dict({k: c["r"][k] for k in ("method", "from", "increase", "inc_from")},
                                       **({"amount": c["r"]["amount"]} if c["r"]["method"] in ("fix", "yearly_amount") else {})),
                          "base": c["info"]}
    p = z["plan"] = {"method": method, "amount": amount, "increase_percent_pa": g, "budget": pos_budget, "amounts": {}, "proposal": {},
                     "overwritten": sorted(ov), "rule": head, "cats": len(cats), "own_cats": sum(1 for c in cats if c["own"]), "ignored": []}
    for i, mk in enumerate(future):
        raw: Dict[int, float] = {}
        for k, c in enumerate(cats):
            m, gr = c["r"]["method"], c["r"]["increase"]
            if c["group"]:
                raw[k] = c["base"] * _plan_factor("", gr, i)
            elif m == "prev_year":
                ly, dp = _year_before(mk), c["d"]["plan"]
                raw[k] = (c["d"]["amounts"][ly] if ly in c["d"]["amounts"] else dp["amounts"].get(ly, 0.0)) * _plan_factor(m, gr, i)
            else:
                raw[k] = c["base"] * _plan_factor(m, gr, i)
        prop = {k: round(v, 2) for k, v in raw.items()}
        for members in groups.values():                   # a shared amount: its parts add up to it to the cent
            ks = [cats.index(c) for c in members]
            for k, v in zip(ks, _round_group([raw[k] for k in ks])):
                prop[k] = v
        val = {k: cats[k]["ov"].get(mk, prop[k]) for k in prop}
        if mk in ov:                                     # your value of the position: shared by the categories without a value of their own
            free = [k for k in prop if mk not in cats[k]["ov"]]
            if free:
                rest = ov[mk] - sum(val[k] for k in prop if k not in free)
                ws = [prop[k] for k in free]                 # by their suggestion in the direction of the rest, else their last 12 months
                if not any(w * rest > 0 for w in ws):
                    ws = [cats[k]["w"] for k in free]
                for k, v in zip(free, _round_group([rest * s + 0.0 for s in _shares(ws, rest)])):
                    val[k] = v
                    cats[k]["d"]["plan"]["from_position"].append(mk)
            else:
                p["ignored"].append(mk)                  # every category has a value of its own: theirs count
        for k, c in enumerate(cats):
            c["d"]["plan"]["proposal"][mk] = prop[k]
            c["d"]["plan"]["amounts"][mk] = val[k]
        p["proposal"][mk] = round(sum(prop.values()), 2)
        p["amounts"][mk] = round(sum(val.values()), 2)


PLAN_NEAR = 1.0        # euro: an account this near its calculation follows it to the cent (rounding, a booking's day)


def _from_actual_debt(series: dict, owed: float, last: str, future: List[str], actual: Optional[Dict[str, Optional[float]]] = None) -> dict:
    """A property calculation's loan (interest, repayment and balance per month, as in the cash flow: paid = negative, owed =
    negative) carried on from what the loan account owes at the end of the last actual month: each month the calculation's
    payment (interest + repayment, with its extra repayments), the interest at the calculation's rate on what is really owed
    (its interest by the ratio of the two debts), the rest repays -- no more than is owed; paid off, nothing is paid any
    more. A loan settled once a year (series["yearly"]: interest on the balance of 1 January) keeps the ratio of the two
    debts at the last year end for the whole year -- an extra repayment during the year lowers the interest from the next
    (actual: the account's balances per month, for the year end before the plan). After the calculation's last month
    nothing is planned from it (what is still owed then stays). Unchanged where the calculation does not know that month's
    debt, the account owes nothing (or is no debt), or both agree within PLAN_NEAR."""
    bal = series.get("balance_amount") or {}
    calc = bal.get(last)
    if calc is None or calc > -0.005 or owed > -0.005 or abs(owed - calc) < PLAN_NEAR:
        return series
    out = {k: dict(series.get(k) or {}) for k in ("interest", "repayment", "balance_amount")}
    yearly, year_end = bool(series.get("yearly")), {}        # year_end: December -> what was owed then (planned)
    b, before = owed, calc
    for mk in future:
        if mk not in out["balance_amount"]:
            break
        ci, cr = float(out["interest"].get(mk, 0.0)), float(out["repayment"].get(mk, 0.0))
        part = b / before if before < -0.005 and b < -0.005 else 0.0
        if yearly and b < -0.005:
            dec = "%d-12" % (int(mk[:4]) - 1)
            was, was_calc = year_end.get(dec, (actual or {}).get(dec) if dec <= last else None), bal.get(dec)
            if was is not None and was_calc is not None and was < -0.005 and was_calc < -0.005:
                part = was / was_calc
        interest = round(ci * part, 2)
        repay = min(0.0, max(round(ci + cr - interest, 2), round(b, 2))) if b < -0.005 else 0.0
        before = float(out["balance_amount"][mk])
        b = round(b - repay, 2)
        out["interest"][mk], out["repayment"][mk], out["balance_amount"][mk] = interest, repay, b
        if mk.endswith("-12"):
            year_end[mk] = b
    return dict(series, **out)


def _from_actual_value(series: Dict[str, float], value: float, last: str, future: List[str]) -> Dict[str, float]:
    """A property calculation's value per month carried on from what the property's account shows at the end of the last
    actual month: it grows as the calculation's value does from there. Unchanged where the calculation has no value for
    that month (not bought yet), the account shows none, or both agree within PLAN_NEAR."""
    calc = series.get(last)
    if calc is None or calc < 0.005 or value < 0.005 or abs(value - calc) < PLAN_NEAR:
        return series
    return dict(series, **{mk: round(value * float(series[mk]) / calc, 2) for mk in future if mk in series})


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
    defaults = plan_defaults(plan)
    inflation = float(plan.get("inflation_percent_pa", 2.0) or 0.0)
    growth_default = {"expenses": float(plan.get("expense_increase_percent_pa", inflation) if plan.get("expense_increase_percent_pa") is not None else inflation),
                      "income": float(plan.get("income_increase_percent_pa") or 0.0)}
    rendite = float(plan.get("return_percent_pa") or 0.0)
    budgets: Dict[str, float] = dataset.get("budgets") or {}
    rows_cfg: Dict[str, dict] = {k: v for k, v in (plan.get("rows", {}) or {}).items() if isinstance(v, dict)}
    row_of_cat: Dict[str, str] = {}               # category -> the row it counts in (budgets of a category above several rows)
    for sek in dataset.get("cashflow", {}).get("sections", []):
        for z in sek["rows"]:
            for d in z.get("details") or []:
                if d["category"]:
                    row_of_cat[d["category"]] = sek["name"] + "/" + z["row"]
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
            has_rows = any(z.get("property_name") == name for z in sec_by_name[sec_name]["rows"])
            if not im.get("category") and not has_rows:          # no category: only its own rows (estimated rent) take it
                continue
            if has_rows:
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
    # A calculation knows its own course only: where the account stands elsewhere today -- an extra repayment it does not hold,
    # a value you set yourself -- the plan goes on from what the account shows, with the calculation's terms (3.17.87; before, the
    # planned debt and value jumped to the calculation's in the first plan month, a change of net worth nobody had).
    now = {u: by_uuid[u]["amounts"].get(ist[-1]) for u in set(immo_loans) | set(immo_wert) if u in by_uuid}
    for u in list(immo_loans):
        if now.get(u) is not None:
            immo_loans[u] = _from_actual_debt(immo_loans[u], now[u], ist[-1], future, by_uuid[u]["amounts"])
    for u in list(immo_wert):
        if now.get(u) is not None:
            immo_wert[u] = _from_actual_value(immo_wert[u], now[u], ist[-1], future)

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

    # 1. Planwerte je Zeile: the deepest rule counts, field by field -- the category's, the position's, the area's default
    for sek in sektionen:
        side = plan_side(sek["name"])
        for z in sek["rows"]:
            key = sek["name"] + "/" + z["row"]
            cfg = rows_cfg.get(key, {})
            own = plan_rule(cfg)
            fx = fixed_rows.get((sek["name"], z["row"]))
            if fx:                                       # the loan schedule, an event, a property calculation: theirs
                ov = _overrides(cfg, future)
                z["plan"] = {"method": fx[1], "amount": None, "increase_percent_pa": 0.0, "budget": None, "amounts": {}, "proposal": {},
                             "overwritten": sorted(ov), "rule": {"method": fx[1], "from": "fixed"}}
                for mk in future:
                    v = round(float(fx[0].get(mk, 0.0)), 2)
                    z["plan"]["proposal"][mk] = v
                    z["plan"]["amounts"][mk] = ov.get(mk, v)
                continue
            if "method" in own:
                rule = {"method": own["method"], "from": "position", "amount": own.get("amount")}
            elif plan_one_off(sek["name"], z):           # contributions/withdrawals, loans taken up: one-offs
                rule = {"method": "none", "from": "kind"}
            else:
                rule = {"method": defaults[side]["method"], "from": "area"}
            if "increase_percent_pa" in own:
                rule["increase"], rule["inc_from"] = own["increase_percent_pa"], "position"
            elif sek["name"] in ("income", "expenses") and "increase_percent_pa" in defaults[side]:
                rule["increase"], rule["inc_from"] = defaults[side]["increase_percent_pa"], "area"
            else:
                rule["increase"], rule["inc_from"] = growth_default.get(sek["name"], 0.0), "standard"
            plan_position(z, sek["name"], cfg, rule, future, full_months, budgets, row_of_cat)

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
                    z["plan"]["rule"] = {"method": "property", "from": "fixed"}
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
        pay_hist = [((tilg.get("plan_hist") or tilg["amounts"])[mk] if tilg else 0.0) + (zins["amounts"][mk] if zins else 0.0) for mk in full_months[-12:]]
        payment = float(lp.get("payment") or (round(-sum(pay_hist) / len(pay_hist), 2) if pay_hist else 0.0))
        kind = lp.get("kind") or ("liability" if acc.get("role") == "liabilities" else "forderung" if acc.get("role") == "receivables" else None)
        loan_state[uuid] = {"rate": rate, "payment": payment, "model": lp.get("model", "remaining_debt_monthly"), "kind": kind,
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
            # which way it is owed: by the booking rule's kind (liability, else a receivable), else the account's role, else the
            # balance; past zero (overpaid) no interest and no repayment (decided 2026-11-23)
            sign = -1.0 if st.get("kind") == "liability" else 1.0 if st.get("kind") else -1.0 if b < 0 else 1.0
            owed = max(0.0, b * sign)
            if st["model"] == "yearly_base":
                if yr not in year_base[uuid]:
                    year_base[uuid][yr] = b
                base = max(0.0, year_base[uuid][yr] * sign)
            else:
                base = owed
            interest = round(base * st["rate"] / 1200.0, 2) if owed > 0.005 else 0.0
            principal = min(max(st["payment"] - interest, 0.0), owed)
            if st["interest"]:
                st["interest"]["plan"]["proposal"][mk] = round(sign * interest, 2)
                if mk in st["ov_z"]:
                    interest = abs(float(st["ov_z"][mk]))
                st["interest"]["plan"]["amounts"][mk] = round(sign * interest, 2)
                st["interest"]["plan"]["method"] = "loans"
                st["interest"]["plan"]["rule"] = {"method": "loans", "from": "fixed"}
            if st["repay"]:
                st["repay"]["plan"]["proposal"][mk] = round(sign * principal, 2)
                if mk in st["ov_t"]:
                    principal = min(abs(float(st["ov_t"][mk])), owed)
                st["repay"]["plan"]["amounts"][mk] = round(sign * principal, 2)
                st["repay"]["plan"]["method"] = "loans"
                st["repay"]["plan"]["rule"] = {"method": "loans", "from": "fixed"}
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
    dataset["plan_figures"] = plan_figures(dataset, future, liq_total[ist[-1]], ist[-1])
    dataset["plan"] = {"horizon_months": horizon, "inflation_percent_pa": inflation,
                       "income_increase_percent_pa": growth_default["income"], "expense_increase_percent_pa": growth_default["expenses"],
                       "expense_rate_own": plan.get("expense_increase_percent_pa") is not None,
                       "return_percent_pa": rendite, "fi_real_return_percent": float(plan.get("fi_real_return_percent") or 3.0),
                       "defaults": defaults, "model": plan_model(plan), "models": PLAN_MODELS,
                       "rows": rows_cfg, "loans": loans_plan, "appreciation": wert_cfg, "events": plan.get("events") or []}
    return dataset


def plan_figures(dataset: dict, future: List[str], cash: float, cash_month: str) -> dict:
    """The plan's key figures over its next 12 months: savings rate = surplus ÷ income; interest burden = interest paid on loans
    (financing) ÷ income; runway = the bank balance at the end of the running month ÷ the planned average fall of the bank
    balance per month (None: it does not fall)."""
    sums = dataset["cashflow"]["sums"]
    nxt = future[:12]
    fin = [z for sek in dataset["cashflow"]["sections"] if sek["name"] == "financing" for z in sek["rows"] if z["kind"] == "interest"]
    inc = round(sum(sums[mk]["income"] for mk in nxt), 2)
    surplus = round(sum(sums[mk]["operating"] for mk in nxt), 2)
    interest = round(-sum((z.get("plan") or {}).get("amounts", {}).get(mk, 0.0) for z in fin for mk in nxt), 2)
    change = round(sum(sums[mk]["cash_change"] for mk in nxt) / len(nxt), 2) if nxt else 0.0
    runway = None if change > -0.005 else 0.0 if cash <= 0 else round(cash / -change, 1)
    return {"months": [nxt[0], nxt[-1]] if nxt else [], "n": len(nxt), "income": inc, "surplus": surplus,
            "saving_rate": round(surplus / inc, 4) if inc > 0.005 else None, "interest": interest,
            "interest_rate": round(interest / inc, 4) if inc > 0.005 else None,
            "cash": round(cash, 2), "cash_month": cash_month, "cash_change_month": change, "runway_months": runway}


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
