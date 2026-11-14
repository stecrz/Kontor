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
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from categorize import suggest as suggest_category
from model import Account, Ledger, Tx, add_months, month_end, month_key, months_between, norm_cat
from model import MARK, marks_in
from i18n import tr

ROLES = ["liquiditaet", "wertpapiere", "anlagen", "immobilien", "beteiligungen", "sachwerte", "forderungen", "sonstiges", "verbindlichkeiten",
         "eigenkapital", "eventual", "ignorieren"]
ROLE_KEYS = {"liquiditaet": "pos_bankguthaben", "wertpapiere": "pos_wertpapiere", "anlagen": "pos_gebundene_anlagen", "immobilien": "immobilien",
             "beteiligungen": "beteiligungen", "sachwerte": "sachwerte", "forderungen": "pos_forderungen", "sonstiges": "sonstiges",
             "verbindlichkeiten": "pos_verbindlichkeiten", "eigenkapital": "role_eigenkapital", "eventual": "role_eventual",
             "ignorieren": "nicht_bilanzieren"}       # Schluessel in web/i18n.js


def role_label(role: str) -> str:
    """Name einer Bilanzposition in der eingestellten Sprache."""
    return tr(ROLE_KEYS[role]) if role in ROLE_KEYS else role


OFF_BALANCE = {"eigenkapital", "eventual", "ignorieren"}      # nicht im Nettovermoegen
ASSET_ROLES = {"wertpapiere", "anlagen", "immobilien", "beteiligungen", "sachwerte"}
ILLIQUID_DEFAULT = ["anlagen", "beteiligungen", "immobilien", "sachwerte", "forderungen", "sonstiges"]
# Hinweise aus Konto- und Gruppennamen (Reihenfolge = Vorrang; Wortgrenzen, damit z. B. "Haushalt" nicht als Haus gilt).
# "+/-": Darlehen, Kredite, Kautionen -> Guthaben = Forderung, negativer Saldo = Verbindlichkeit
# "kapital": Kapital-/Gesellschafterkonten und Gesellschafterdarlehen -> Guthaben = Beteiligung (Risikokapital: traegt Verluste mit,
# fliesst erst beim Ausscheiden zurueck), negativer Saldo = Verbindlichkeit (in der Gesellschaft: Schuld an den Gesellschafter)
NAME_HINTS = [
    (r"off.?balance|nicht bilanz", "ignorieren"),
    (r"aval|b(ü|ue)rgschaft|garantie", "eventual"),
    (r"eigenkapital", "eigenkapital"),
    # Kapital-/Gesellschafterkonten wie Gesellschafterdarlehen: in der Gesellschaft Schuld an den Gesellschafter, privat Forderung;
    # das Nettovermoegen der Gesellschaft ist dann der Rest, der nach Anteil verteilt wird (stimmt auch bei ungleichen Einlagen)
    (r"kapitalkont|gesellschafterkont|gesellschafterdarlehen", "kapital"),
    (r"kaution", "+/-"),
    (r"\bp2p|peer.to.peer", "anlagen"),      # P2P loans are an investment, not a loan to manage (before "kredit")
    (r"darlehen|kredit(?!karte)|hypothek|finanzierung|\bschulden", "+/-"),
    (r"bauspar|lebensversicherung|rentenversicherung|\bversicherung|riester|r(ü|ue)rup|fondspolice", "anlagen"),
    (r"immobil|wohnung|\bhaus\b|eigenheim|grundst(ü|ue)ck|\bobjekt", "immobilien"),
    (r"beteilig|\bgesellschafteranteil|\banteil an\b", "beteiligungen"),
    (r"forderung|verliehen", "forderungen"),
    (r"verbindlich", "verbindlichkeiten"),
    (r"fahrzeug|\bauto\b|\bpkw\b|\bmotorrad|\buhren?\b|sachwert|schmuck|\bkunst|\bgold\b", "sachwerte"),
    (r"depot|wertpapier|\betf|aktien|\bfonds|krypto|bitcoin", "wertpapiere"),
    (r"festgeld|sparbrief|\banlage", "anlagen"),
    (r"liquid|\bcash|\bgiro|tagesgeld|\bkasse\b|bargeld", "liquiditaet"),
]
_NAME_HINTS_RE = [(re.compile(rx, re.I), role) for rx, role in NAME_HINTS]
GROUP_HINTS = NAME_HINTS          # Rueckwaerts-Kompatibilitaet
STRONG_TYPES = {"portfolio": "wertpapiere", "depot": "wertpapiere", "girokonto": "liquiditaet", "kreditkarte": "liquiditaet", "bargeld": "liquiditaet", "cash": "liquiditaet",
                "darlehenskonto": "+/-", "loan": "+/-", "bauspar": "anlagen"}
WEAK_TYPES = {"tagesgeld": "liquiditaet", "sparkonto": "liquiditaet", "festgeld": "anlagen"}
TYPE_ROLES = {**WEAK_TYPES, **STRONG_TYPES, "portfolio": "wertpapiere"}
NO_NEGATIVE_TYPES = ("sparkonto", "tagesgeld", "festgeld", "bauspar")
TX_MARK = MARK + "tx-"              # a loan repayment mirrored from a payment: the mark names the payment
COST_WORDS = ["zins", "interest", "gebühr", "gebuehr", "entgelt", "provision", "bereitstellung", "#kontor-zins", "#mm-zins"]
SECTIONS = ["Einnahmen", "Ausgaben", "Investitionen", "Finanzierung", "Bewertung", "Unklar"]
CASH_SECTIONS = ["Einnahmen", "Ausgaben", "Investitionen", "Finanzierung", "Unklar"]
PLAN_METHODS = ("gleitend12", "gleitend6", "vorjahr", "fix", "jahresbetrag", "budget", "keine")


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
    if role == "kapital":
        if in_company or (in_company is None and acc.balance < -0.005):
            return "beteiligungen" if acc.balance > 0.005 else "verbindlichkeiten"
        return "beteiligungen"
    if role != "+/-":
        return role
    return "forderungen" if acc.balance > 0.005 else "verbindlichkeiten"


def account_roles(ledger: Ledger, config: dict) -> Dict[str, str]:
    """uuid -> Position fuer ALLE Konten. Vorrang: eigene Zuordnung > Depot > Kontoname > eindeutiger Kontotyp
    (Giro, Kreditkarte, Darlehen) > Name der naechsten Gruppe > allgemeiner Kontotyp (Spar-, Tagesgeld, Festgeld) > Sonstiges."""
    cfg_roles: Dict[str, str] = {}
    for ref, role in (config.get("bilanz", {}).get("rollen") or {}).items():
        if ref.startswith("_"):
            continue
        try:
            cfg_roles[ledger.resolve(ref).uuid] = role
        except KeyError:
            pass
    for ref, z in (config.get("bilanz", {}).get("konten_zuordnung") or {}).items():
        if isinstance(z, dict) and z.get("position") in ROLES:
            try:
                cfg_roles[ledger.resolve(ref).uuid] = z["position"]
            except KeyError:
                pass
    roles: Dict[str, str] = {}
    company: set = set()                # accounts in areas of the kind "Gesellschaft"
    for b in config.get("bereiche") or []:
        if isinstance(b, dict) and b.get("art") == "gesellschaft":
            for ref in b.get("konten") or []:
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
                role = "wertpapiere"
            inside = (acc.uuid in company) if company else None
            if not role:
                role = _signed(_hint_role(acc.name), acc, inside)
            if not role:
                role = _signed(next((r for k, r in STRONG_TYPES.items() if k in t), None), acc, inside)
            if not role and group_hint:
                role = _signed(group_hint, acc, inside)
            if not role:
                role = next((r for k, r in WEAK_TYPES.items() if k in t), None)
            roles[acc.uuid] = role or "sonstiges"
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
    if v in ("umsaetze", "stand"):
        return v
    return "stand" if acc.portfolio else "umsaetze"


def _valuation_account(acc: Account, src: str) -> bool:
    """Depot mit Verlauf aus Kontostaenden: Wertaenderung ist Bewertung, keine Zahlungsfluesse."""
    return src == "stand" and acc.portfolio


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
        r = rows.setdefault(key, {"id": acc.uuid + "|" + key, "name": name, "isin": isin, "werte": {}})
        if name and not r["name"]:
            r["name"] = name
        return r
    for n, w in enumerate((state.get("historie_mm_wp") or {}).get(acc.uuid) or []):
        r = row(str(w.get("name") or ""), str(w.get("isin") or ""), "mm:%d" % n)
        for mk, v in (w.get("werte") or {}).items():
            if mk < cur and v is not None:
                r["werte"][mk] = round(r["werte"].get(mk, 0.0) + float(v), 2)
    names = state.get("wp_namen") or {}
    covered = {mk for r in rows.values() for mk in r["werte"]}
    for mk, per in (state.get("snapshots_wp") or {}).items():
        if mk >= cur or mk in covered or acc.uuid not in per:
            continue
        for key, v in per[acc.uuid].items():
            r = rows.setdefault(key, {"id": acc.uuid + "|" + key, "name": names.get(key, ""), "isin": key if not key.startswith("n:") else "", "werte": {}})
            r["werte"][mk] = float(v)
    for p in live or []:
        try:
            r = row(str(p.get("name") or ""), str(p.get("isin") or ""))
            r["werte"][cur] = round(r["werte"].get(cur, 0.0) + float(p.get("marketValue") or p.get("amount") or 0), 2)
        except (TypeError, ValueError, AttributeError):
            continue
    found, own = (state.get("wp_suche") or {}).get("namen") or {}, (state.get("wp_suche") or {}).get("eigene") or {}
    for key, r in rows.items():
        # MoneyMoney's own name (history or export) stays as "orig" and is always shown on hover, together with the ISIN; the name
        # shown: one changed in the setup (list of names), else MoneyMoney's, else the one looked up by the ISIN, else the ISIN
        isin = (r.get("isin") or "").upper()
        r["orig"] = r["name"] or names.get(key, "")
        look = str(found.get(isin) or "") if not r["orig"] else ""
        mine = str(own.get(isin) or "") if isin else ""
        r["name"], r["quelle"] = mine or r["orig"] or look, "eigen" if mine else "suche" if look else ""
    out = [r for r in rows.values() if any(abs(v) >= 0.005 for v in r["werte"].values())]
    if not out:
        return []
    for i, r in enumerate(out, 1):
        r["name"] = r["name"] or r.get("isin") or tr("s_wertpapier_n") % i       # without a name: the ISIN
        r["werte"] = {mk: r["werte"].get(mk) for mk in mkeys}
    rest = {}
    for mk in mkeys:
        known = [r["werte"][mk] for r in out if r["werte"][mk] is not None]
        rest[mk] = round((werte.get(mk) or 0.0) - sum(known), 2) if known and werte.get(mk) is not None else None
    if any(v is not None and abs(v) >= 0.5 for v in rest.values()):
        out.append({"id": acc.uuid + "|rest", "name": tr("s_wp_rest"), "isin": "", "rest": True, "werte": rest})
    out.sort(key=lambda r: (bool(r.get("rest")), -abs(next((r["werte"][mk] for mk in reversed(mkeys) if r["werte"].get(mk) is not None), 0.0))))
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
    if src != "stand":
        ends = ledger.month_end_balances(acc.uuid, past)
        # Alle Umsaetze bekannt (kein Zeitfenster): vor dem ersten Umsatz gab es das Konto nicht -- kein Stand (wie in MoneyMoney),
        # statt den Startsaldo endlos zurueckzuschreiben
        full = int(((config or {}).get("bilanz") or {}).get("monate_zurueck", 0) or 0) <= 0
        first = min((t.booking_date for t in ledger.transactions(acc.uuid)), default=None) if full else None
        opened = month_key(first) if first else None
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
        if src == "stand" and acc.portfolio and anker and first_mk and first_mk < anker[0] and abs(acc.balance) > 0.005 \
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
    bcfg = config.get("bilanz", {}) or {}
    n = int(bcfg.get("inaktiv_monate", 12) or 0)
    force_hide: Set[str] = set()
    force_show: Set[str] = set()
    for ref in bcfg.get("ausgeblendet") or []:
        try:
            force_hide.add(ledger.resolve(ref).uuid)
        except KeyError:
            pass
    for ref in bcfg.get("immer_anzeigen") or []:
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

    def add(self, section: str, gruppe: str, zeile: str, mk: str, amount: float, *,
            konto: Optional[str] = None, art: str = "kategorie", nw: bool = True, lbl: Optional[tuple] = None,
            glbl: Optional[tuple] = None, ord: Optional[float] = None, objekt: Optional[str] = None, detail: Optional[str] = None):
        """zeile/gruppe stay German (keys of your planning); lbl/glbl: (text key, value) shown in your language; ord: place in
        the fixed outline (positions); objekt: the property the row belongs to; detail: the category inside the row."""
        key = (section, zeile)
        self.vals[key][mk] += amount
        if detail is not None:
            self.det[key][detail][mk] += amount
        if key not in self.meta:
            self.meta[key] = {"gruppe": gruppe, "konto": konto, "art": art, "nw": nw}
            for k, v in (("lbl", lbl), ("glbl", glbl)):
                if v:
                    self.meta[key][k] = list(v)
            if ord is not None:
                self.meta[key]["ord"] = ord
            if objekt:
                self.meta[key]["objekt"] = objekt


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
        cut = min(month_end(y, m), today)
        val = sum(p[2] for p in pairs if p[0] <= cut < p[1]) - sum(p[2] for p in pairs if p[1] <= cut < p[0])
        out[mk] = round(val, 2)
    name = lambda u: ledger.accounts[u].name if u in ledger.accounts else u
    details = [{"ab": p[0].isoformat(), "an": p[1].isoformat(), "betrag": round(p[2], 2), "von": name(p[3]), "nach": name(p[4])}
               for p in sorted(pairs, key=lambda p: min(p[0], p[1]))]
    return out, details


def company_areas(ledger: Ledger, config: dict) -> List[Tuple[dict, dict]]:
    """The companies set up under Booking rules: (their entry in gesellschaften, their area) -- the area as everywhere else
    (bereiche_for: with the accounts you moved under Setup)."""
    from core import bereiche_for                  # imported late (core imports report)
    areas = bereiche_for(ledger, config)
    by_id = {str(b["id"]): b for b in areas}
    out = []
    for g in config.get("gesellschaften") or []:
        if not isinstance(g, dict) or not (g.get("beteiligung") or g.get("gegenkonten")):
            continue
        b = by_id.get(str(g.get("bereich")))
        if b is None:                              # named by its group or an account in it
            try:
                a = ledger.resolve(str(g.get("bereich")))
            except KeyError:
                continue
            members = {x.uuid for x in (ledger.descendants(a.uuid) if a.group else [a])}
            b = next((x for x in areas if members & {y.uuid for y in x["leaves"]}), None)
        if b is not None:
            out.append((g, b))
    return out


def company_accounts(ledger: Ledger, config: dict) -> Dict[str, str]:
    """Accounts of the companies set up under Booking rules (with a participation or counter account) -> company name."""
    return {a.uuid: b["name"] for g, b in company_areas(ledger, config) for a in b["leaves"]}


VALUE_MARKS = (MARK + "wert-", MARK + "spiegel-")     # value adjustments of Kontor (participation): never a transfer
ASSET_LIKE = ASSET_ROLES | {"sonstiges"}               # positions that change only by bookings, valuations and transfers
PAIR_DAYS_IBAN = 5                                      # counter IBAN known: counterpart at most this many days apart
PAIR_DAYS_IBAN_BOTH = 14                                # ... and both bookings name each other's account
PAIR_DAYS = 3                                           # by amount only (transfer category, offline account)


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
        if g.get("beteiligung"):
            try:
                out[b["name"]] = ledger.resolve(g["beteiligung"]).uuid
            except KeyError:
                pass
    return out


def pair_transfers(ledger: Ledger, txs: List[Tx], root: Set[str], roles: Dict[str, str], is_transfer: Callable[[str], bool],
                   cost_words: List[str], kf: dict, pairable: Callable[[Tx], bool] = lambda t: True):
    """Transfers within an area, booking by booking: the counterpart of a transfer is the booking on the other side.
    Found by Kontor's mark (#kontor-tx-<payment>: the repayment of a loan names the payment), by the counter IBAN (a booking of
    that account with the same amount, opposite sign, at most 5 days apart) or -- for a transfer category or an offline account
    -- by amount alone (at most 3 days). Returns (mate: booking -> counterpart in the area, partner: booking -> account on the
    other side, also outside the area or without a counterpart, category: booking -> marked as transfer by its category)."""
    own_ibans = ledger.own_ibans()
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
            if p not in root:
                partner.setdefault(t.id, p)
                continue
            best = None
            for o in bookings_of(p).get(-cents(t.amount), ()):
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
            else:
                partner[t.id] = p                       # the other account, but its booking is missing
    # 3. by amount: transfer category or a booking of an offline account (no counterpart known yet)
    if kf.get("umbuchung_paarung", True):
        manual_ok = kf.get("paarung_manuelle_konten", True)
        loose = lambda t: t.id not in mate and t.id not in partner          # the other side is not known yet
        open_tx = [t for t in txs if by_cat[t.id] and loose(t)]
        offline = [t for t in txs if manual_ok and loose(t) and roles.get(t.account_uuid) != "liquiditaet"
                   and (roles.get(t.account_uuid) in ("verbindlichkeiten", "forderungen") or roles.get(t.account_uuid) in ASSET_LIKE)
                   and ledger.accounts[t.account_uuid].offline and not _is_cost(t, cost_words) and not _value_adjustment(t)]
        liquid = [t for t in txs if roles.get(t.account_uuid) == "liquiditaet" and loose(t) and (by_cat[t.id] or pairable(t))]
        pools: Dict[str, Dict[int, List[Tx]]] = {"open": defaultdict(list), "offline": defaultdict(list), "liquid": defaultdict(list)}
        for name, lst in (("open", open_tx), ("offline", offline), ("liquid", liquid)):
            for o in lst:
                pools[name][cents(o.amount)].append(o)
        kinds: Dict[int, Set[str]] = defaultdict(set)
        for name, lst in (("open", open_tx), ("offline", offline), ("liquid", liquid)):
            for o in lst:
                kinds[o.id].add(name)
        for t in sorted({o.id: o for o in open_tx + offline + liquid}.values(), key=lambda x: (x.booking_date, x.id)):
            if t.id in mate:
                continue
            k = kinds[t.id]
            search = (["open"] if "open" in k else []) + (["liquid"] if "offline" in k else []) + (["offline"] if "liquid" in k else [])
            best = None
            for name in search:
                for o in pools[name].get(-cents(t.amount), ()):
                    if o.id in mate or o.id == t.id or o.account_uuid == t.account_uuid:
                        continue
                    gap = abs((o.booking_date - t.booking_date).days)
                    if gap <= PAIR_DAYS and (best is None or (gap, o.id) < best[0]):
                        best = ((gap, o.id), o)
            if best is not None:
                join(t, best[1])
    return mate, partner, by_cat


# ---------------------------------------------------------------------------
# Cash flow positions: a fixed outline for income and expenses; MoneyMoney's categories are assigned to them once
# (Kategorien -> Cashflow-Positionen; Kontor proposes by name). Planning works on the positions.
# ---------------------------------------------------------------------------
POSITIONS = [  # (key, section, row -- German, the key of your planning; shown in your language via pos_<key>); one outline for
    # every area (a row shows only where there is money in it)
    ("arbeit", "Einnahmen", "Arbeitseinkommen"), ("umsatz", "Einnahmen", "Umsatzerlöse"), ("vermietung", "Einnahmen", "Vermietung"),
    ("kapitalertraege", "Einnahmen", "Kapitalerträge"), ("erstattungen", "Einnahmen", "Erstattungen"), ("sonstige_einnahmen", "Einnahmen", "Sonstige Einnahmen"),
    ("wareneinkauf", "Ausgaben", "Wareneinkauf"), ("personal", "Ausgaben", "Personal"), ("betrieb", "Ausgaben", "Betriebskosten"),
    ("wohnen", "Ausgaben", "Wohnen"), ("lebenshaltung", "Ausgaben", "Lebenshaltung"), ("mobilitaet", "Ausgaben", "Mobilität"),
    ("versicherungen", "Ausgaben", "Versicherungen"), ("gesundheit", "Ausgaben", "Gesundheit"), ("freizeit", "Ausgaben", "Freizeit & Reisen"),
    ("objektkosten", "Ausgaben", "Objektkosten"), ("verwaltung", "Ausgaben", "Beratung & Gebühren"), ("steuern", "Ausgaben", "Steuern"),
    ("umsatzsteuer", "Ausgaben", "Umsatzsteuer"),
    ("spenden", "Ausgaben", "Geschenke & Spenden"), ("sonstige_ausgaben", "Ausgaben", "Sonstige Ausgaben"),
    ("anlegen", "Investitionen", "Sparen & Anlegen"), ("tilgung", "Finanzierung", "Tilgung"), ("zinsen", "Finanzierung", "Zinsen"),
    ("ignorieren", "", ""),
]
POS = {k: (sec, row, i) for i, (k, sec, row) in enumerate(POSITIONS)}
RENAMED_ROWS = {"Einnahmen/Arbeit": "Einnahmen/Arbeitseinkommen"}     # planning keys of rows that were renamed (3.13.8)
COMPANY_ROWS = {"wohnen": "Raumkosten"}       # the same position, named as a company would (text pos_<key>_g)


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
    (("zins", "finanzierungskost"), "kapitalertraege", "zinsen", False),
    (("tilgung", "kredit", "darlehen", "finanzierung", "annuit"), "tilgung", "tilgung", False),
    (("sparen", "sparplan", "bauspar", "invest", "wertpapier", "depot", "etf", "aktie", "fonds", "geldanlage", "ruecklage", "krypto",
      "altersvorsorge", "beteiligung", "immobilienkauf", "kapitalanlage"), "anlegen", "anlegen", True),
]
FIRST_NOT = ("gebuehr", "kosten", "entgelt", "provision", "kreditkarte")
POSITION_CONTEXT = [(("vermiet", "immobil", "objekt"), "vermietung", "objektkosten")]
POSITION_HINTS = [
    (("steuerberat", "beratung", "notar", "anwalt", "kontofuehr", "gebuehr", "bankgeb"), "sonstige_einnahmen", "verwaltung"),
    (("wareneinkauf", "waren", "lieferant", "material"), "erstattungen", "wareneinkauf"),
    (("personal", "loehne", "sozialversicher", "sozialabgab", "lohnneben"), "erstattungen", "personal"),
    (("umsatzerl", "erloes", "kasseneinnahm", "verkauf"), "umsatz", "sonstige_ausgaben"),
    (("betriebskost", "betriebsbedarf", "marketing", "werbung", "software", "it-kost"), "erstattungen", "betrieb"),
    (("ladenmiete", "raumkost", "geschaeftsmiete", "gewerbemiete"), "vermietung", "wohnen"),
    (("hausgeld", "instandhalt", "reparatur", "hausverwalt", "grundsteuer"), "erstattungen", "objektkosten"),
    (("umsatzsteuer", "vorsteuer", "ust"), "umsatzsteuer", "umsatzsteuer"),
    (("finanzamt", "steuer", "solidarit"), "erstattungen", "steuern"),
    (("gehalt", "gehaelt", "lohn", "loehn", "tantieme", "bonus", "gratifikation", "verguetung", "honorar", "arbeit"), "arbeit", "personal"),
    (("dividend", "kapitalertr", "ausschuett"), "kapitalertraege", "sonstige_ausgaben"),
    (("mieteinnahm", "pacht"), "vermietung", "objektkosten"),
    (("erstattung", "rueckzahlung", "gutschrift", "cashback"), "erstattungen", "sonstige_ausgaben"),
    (("geldautomat", "bargeld", "barabhebung", "abhebung"), "sonstige_einnahmen", "sonstige_ausgaben"),
    (("versicherung",), "erstattungen", "versicherungen"),
    (("restaurant", "gastro"), "erstattungen", "freizeit"),
    (("miete",), "vermietung", "wohnen"),
    (("nebenkost", "strom", "energie", "wasser", "heiz", "internet", "telefon", "mobilfunk", "rundfunk", "wohnen", "wohnung"), "erstattungen", "wohnen"),
    (("lebensmittel", "supermarkt", "einkauf", "drogerie", "kleidung", "haushalt", "lebenshalt"), "erstattungen", "lebenshaltung"),
    (("auto", "kfz", "tank", "benzin", "mobilit", "bahn", "oepnv", "taxi", "parken", "fahrrad", "verkehr", "maut", "transport"), "erstattungen", "mobilitaet"),
    (("gesundheit", "arzt", "apotheke", "medizin", "zahn", "kranken", "therapie"), "erstattungen", "gesundheit"),
    (("freizeit", "urlaub", "reise", "kultur", "sport", "hobby", "abo", "streaming", "kino", "konzert", "hotel", "flug"), "erstattungen", "freizeit"),
    (("spende", "geschenk"), "sonstige_einnahmen", "spenden"),
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
    ("text", r"ausschuettung|dividend|ertragsgutschrift", ("kapitalertraege", ""), ("kapitalertraege", "")),
    ("text", r"\bzins|sollzins|habenzins|zinsabschluss|kupon", ("kapitalertraege", "zinsen"), ("kapitalertraege", "zinsen")),
    ("name", r"deutsche rentenversicherung", ("", "versicherungen"), ("", "personal")),       # money from it: a pension, no estimate
    ("name", r"\baok\b|techniker krankenkasse|barmer|\bdak\b|\bikk\b|\bbkk\b|knappschaft|minijob|berufsgenossenschaft|krankenkasse|rentenversicherung",
     ("erstattungen", "versicherungen"), ("erstattungen", "personal")),
    ("text", r"\blohn\b|\bgehalt|lohn/gehalt|\bloehne\b|entgeltabrechnung|bezuege|\bverguetung", ("arbeit", None), (None, "personal")),
    ("text", r"bareinzahlung|kartenumsa|kartenzahlung|nexi\b|concardis|adyen|sumup|payone|worldline|elavon|ec-cash|girocard|kassenabrechnung", (None, None), ("umsatz", None)),
    ("name", r"steuerberat|rechtsanwalt|notar|kanzlei|wirtschaftspruef|datev|amtsgericht|handelsregister|bundesanzeiger|\bihk\b", (None, "verwaltung"), (None, "verwaltung")),
    ("text", r"hausgeld|wohngeld|instandhaltungsruecklage|hausverwaltung", ("erstattungen", "wohnen"), ("erstattungen", "objektkosten")),
    ("text", r"\bmiete\b|mietzahlung|kaltmiete|warmmiete|\bpacht\b|nebenkosten", ("vermietung", "wohnen"), ("vermietung", "wohnen")),
    ("name", r"stadtwerke|vattenfall|e\.on|\beon\b|\benbw\b|naturstrom|lichtblick|polarstern|\bstrom|fernwaerme", ("erstattungen", "wohnen"), ("erstattungen", "wohnen")),
    ("name", r"telekom|vodafone|telefonica|\bo2\b|1&1|congstar|m-net|rundfunk|beitragsservice", ("erstattungen", "wohnen"), ("erstattungen", "betrieb")),
    ("text", r"kontofuehrung|kontoentgelt|gebuehr|kartenpreis|kontopreis|kontomodell", (None, "verwaltung"), (None, "verwaltung")),
    ("name", r"versicherung|allianz|\bhuk\b|\bergo\b|\baxa\b|generali|signal iduna|debeka|\bhdi\b|\bwwk\b|\blvm\b|\bdevk\b|gothaer|provinzial",
     ("erstattungen", "versicherungen"), ("erstattungen", "versicherungen")),
    ("text", r"spende|unicef|aerzte ohne grenzen|\bwwf\b|greenpeace|albert schweitzer", (None, "spenden"), (None, "spenden")),
    ("name", r"\brewe\b|\bedeka\b|\baldi\b|\blidl\b|\bpenny\b|kaufland|denns|alnatura|\bdm\b|dm-drogerie|rossmann|amazon|zalando|\bikea\b",
     ("erstattungen", "lebenshaltung"), (None, None)),
    ("name", r"deutsche bahn|\bdb vertrieb|\bmvg\b|\bmvv\b|\baral\b|\bshell\b|\besso\b|totalenergies|tankstelle|\bsixt\b|share now|\buber\b|flixbus|lufthansa|parkhaus|\bapcoa\b|\badac\b",
     ("erstattungen", "mobilitaet"), (None, "betrieb")),
    ("name", r"apotheke|zahnarzt|\barzt|arztpraxis|klinik|krankenhaus|physiotherap|fielmann", ("erstattungen", "gesundheit"), (None, None)),
    ("name", r"netflix|spotify|disney|apple\.com|itunes|google play|eventim|airbnb|booking\.com|\bhotel|restaurant|lieferando|\bwolt\b|\bkino",
     ("erstattungen", "freizeit"), (None, None)),
]
_TX_HINTS = [(f, re.compile(rx), pp, pc) for f, rx, pp, pc in TX_HINTS]
# the tax office: wage tax is part of staff costs (a company), VAT a position of its own, the rest taxes (or a refund)
_TAX_OFFICE = re.compile(r"finanzamt|steuerkasse|bundeskasse|stadtkasse|gemeindekasse")
_WAGE_TAX = re.compile(r"lohnsteuer|\blst\b|lohnst")
_VAT = re.compile(r"umsatzsteuer|\bust\b|ustva|ust-va|ust-vz|ust-voranmeldung|vorsteuer")


def fold_text(s: str) -> str:
    return (s or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")


def guess_position(t: Tx, company: bool) -> Optional[str]:
    """Kontor's estimate for a booking without a category, by the words in its name, purpose and booking text (or None)."""
    name = fold_text(t.name)
    text = name + " " + fold_text(t.purpose + " " + t.booking_text)
    if _TAX_OFFICE.search(name):
        if _WAGE_TAX.search(text):
            return "personal" if company and t.amount < 0 else ("erstattungen" if t.amount > 0 else "steuern")
        if _VAT.search(text):
            return "umsatzsteuer"
        return "erstattungen" if t.amount > 0 else "steuern"
    for field, rx, pp, pc in _TX_HINTS:
        if rx.search(name if field == "name" else text):
            pos = (pc if company else pp)[0 if t.amount > 0 else 1]
            if pos is not None:
                return pos or None
    return None


def propose_position(path: str, income: bool) -> str:
    """Kontor's proposal for a category (by its words); income: its money mostly comes in."""
    low = fold_text(path)
    name = low.split(" / ")[-1]
    for text in (name, low):
        for words, pin, pout, start in POSITION_FIRST:
            if pin != "kapitalertraege" and any(w in text for w in FIRST_NOT):
                continue
            if _has(words, text, start):
                return pin if income else pout
    for words, pin, pout in POSITION_CONTEXT:
        if _has(words, low):
            return pin if income else pout
    for text in (name, low):
        for words, pin, pout in POSITION_HINTS:
            if _has(words, text):
                return pin if income else pout
    return "sonstige_einnahmen" if income else "sonstige_ausgaben"


def category_totals(ledger: Ledger) -> Dict[str, float]:
    """Sum per category over all booked transactions (whether its money mostly comes in or goes out)."""
    out: Dict[str, float] = defaultdict(float)
    for t in ledger.txs:
        if t.booked and t.category_path:
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
    return {norm_cat(k): v for k, v in ((config.get("kapitalfluss") or {}).get("positionen") or {}).items()
            if (v in POS or v == "umbuchung") and norm_cat(k)}


# the usual names of a transfer category -- the category's own name only (not one above it: "Übertrag / Familie" may be anything)
TRANSFER_NAMES = {"umbuchung", "umbuchungen", "uebertrag", "uebertraege", "kontouebertrag", "eigene konten", "eigenes konto"}


def transfer_check(config: dict) -> Callable[[str], bool]:
    """Is a category a transfer between your own accounts? Your choice for it or the nearest category above it decides;
    without one: a transfer category (Einstellungen: umbuchungs_kategorien) -- by its path, one above it or its name."""
    mine = my_positions(config)
    names = {fold_text(norm_cat(c)) for c in ((config.get("kapitalfluss") or {}).get("umbuchungs_kategorien") or ["Umbuchung"]) if c}
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
                    r = v == "umbuchung"
                    break
            if r is None:
                low = [fold_text(x) for x in parts]
                r = bool(parts) and (low[-1] in names or low[-1] in TRANSFER_NAMES or any(" / ".join(low[:i]) in names for i in range(1, len(low) + 1)))
            memo[p] = r
        return r
    return check


def classify(ledger: Ledger, leaves: List[Account], roles: Dict[str, str], config: dict, months: List[Tuple[int, int]],
             verlauf: Dict[str, str], areas: Optional[Dict[str, str]] = None, company: bool = False,
             objekte: Optional[Dict[str, str]] = None, learned: Optional[dict] = None):
    """Cash flow rows of an area. Every booking of its accounts counts once: a transfer within the area (both bookings found)
    as one row that leaves the net worth unchanged, everything else with its amount. areas: account -> name of its area (all
    areas; transfers between areas are contributions/withdrawals); company: this area is a company; objekte: category ->
    property (its own rows); learned: the patterns learned from your categories (categorize) -- a booking without a category
    counts in the position they suggest, else in Kontor's estimate by its words (marked as estimated). Returns (rows, inbound
    per account and month, warnings); rows.pairs: transfers within the area (for money in transit at month end), rows.reasons:
    amounts left out on purpose (category "Ignore"), rows.no_target: investments whose account is unknown."""
    kf = config.get("kapitalfluss", {}) or {}
    root_leaves = {a.uuid for a in leaves}
    areas = areas or {}
    is_transfer = transfer_check(config)
    cost_words = [w.lower() for w in (kf.get("kosten_texte") or COST_WORDS)]
    kat_zu_konto: Dict[str, str] = {}                 # investment category -> the account it goes into
    for cat_name, ref in (kf.get("kategorie_zu_konto") or {}).items():
        try:
            kat_zu_konto[norm_cat(cat_name)] = ledger.resolve(ref).uuid
        except KeyError:
            pass
    totals = category_totals(ledger)
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
    ignored: Dict[str, float] = defaultdict(float)

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
            if obj and (pos in ("tilgung", "zinsen") or (yours and pos in ("anlegen", "ignorieren"))):
                obj = None
            r = pos_memo[cat] = (pos, obj)
        return r

    def pairable(t: Tx) -> bool:
        """A bank booking that may be the other side of a booking in an offline account: no category, or one for saving or a
        repayment -- never income or an expense."""
        return not t.category_path or place(norm_cat(t.category_path))[0] in ("anlegen", "tilgung")
    mate, partner, by_cat = pair_transfers(ledger, in_root, flows, roles, is_transfer, cost_words, kf, pairable)
    pairs: List[Tuple[date, date, float, str, str]] = []
    seen_pair: Set[int] = set()

    def own_row(t: Tx, acc: Account, role: str, mk: str) -> None:
        """A booking of an account that is no bank account (loan, receivable, asset): interest or a change of its value."""
        nonlocal unclear
        if role == "verbindlichkeiten" and _is_cost(t, cost_words):
            R.add("Finanzierung", acc.name, acc.name + " / Zinsen", mk, t.amount, konto=acc.uuid, art="zins", nw=True, lbl=("cf_zinsen", acc.name))
            R.add("Finanzierung", acc.name, acc.name + " / Tilgung", mk, -t.amount, konto=acc.uuid, art="tilgung", nw=False, lbl=("cf_tilgung", acc.name))
        elif role == "forderungen" and _is_cost(t, cost_words):
            R.add("Investitionen", acc.name, acc.name + " / Zinsen", mk, t.amount, konto=acc.uuid, art="zins", nw=True, lbl=("cf_zinsen", acc.name))
            R.add("Investitionen", acc.name, acc.name + " / Rückzahlung", mk, -t.amount, konto=acc.uuid, art="rueckzahlung", nw=False, lbl=("cf_rueckzahlung", acc.name))
        elif role in ("verbindlichkeiten", "forderungen") or role in ASSET_LIKE:
            R.add("Bewertung", acc.name, acc.name, mk, t.amount, konto=acc.uuid, art="konto", nw=True)
        else:
            R.add("Unklar", "Konto ohne Position", acc.name + " (Position unbekannt)", mk, t.amount, art="unklar",
                  lbl=("cf_position_unbekannt", acc.name), glbl=("cf_konto_ohne_position",)); unclear += 1

    for t in in_root:
        acc = ledger.accounts[t.account_uuid]
        role = roles.get(acc.uuid, "sonstiges")
        mk = month_key(t.booking_date)
        o = mate.get(t.id)
        if o is not None and month_key(o.booking_date) != mk and "liquiditaet" not in (role, roles.get(o.account_uuid)):
            o = None                                     # e.g. loan and asset a month apart: no money in transit
        if o is not None and o.id not in seen_pair:
            seen_pair.update({t.id, o.id})
            if month_key(o.booking_date) != mk:                   # over a month end: money in transit
                out_, in_ = (t, o) if t.amount < 0 else (o, t)
                pairs.append((out_.booking_date, in_.booking_date, -out_.amount, out_.account_uuid, in_.account_uuid))
        p = partner.get(t.id)
        if role == "ignorieren":
            continue
        if role != "liquiditaet":
            if o is not None:
                continue                                 # the other side (or the bank account) shows the transfer
            own_row(t, acc, role, mk)
            continue
        if o is not None:                                # transfer within the area
            o_role = roles.get(o.account_uuid, "sonstiges")
            pacc = ledger.accounts[o.account_uuid]
            if o_role == "liquiditaet":
                continue
            if o_role in ASSET_LIKE:
                R.add("Investitionen", pacc.name, pacc.name, mk, t.amount, konto=pacc.uuid, art="konto", nw=False)
                inbound[pacc.uuid][mk] += -t.amount
            elif o_role == "forderungen":
                R.add("Investitionen", pacc.name, pacc.name + " / Rückzahlung", mk, t.amount, konto=pacc.uuid, art="rueckzahlung", nw=False,
                      lbl=("cf_rueckzahlung", pacc.name))
            elif o_role == "verbindlichkeiten":
                R.add("Finanzierung", pacc.name, pacc.name + " / Tilgung", mk, t.amount, konto=pacc.uuid, art="tilgung", nw=False,
                      lbl=("cf_tilgung", pacc.name))
            else:
                R.add("Unklar", "Umbuchung", "Umbuchung nach " + pacc.name, mk, t.amount, art="unklar",
                      lbl=("cf_umbuchung_mit", pacc.name), glbl=("cf_umbuchung",)); unclear += 1
            continue
        if p is not None and p in depots:               # into a depot valued by its balances: its valuation takes the rest
            pacc = ledger.accounts[p]
            R.add("Investitionen", pacc.name, pacc.name, mk, t.amount, konto=p, art="konto", nw=False)
            inbound[p][mk] += -t.amount
            continue
        if p is not None and p in root_leaves:          # an account of the area, but its booking is missing
            R.add("Unklar", "Umbuchung", "Umbuchung nach %s ohne Gegenbuchung" % ledger.accounts[p].name, mk, t.amount, art="unklar",
                  lbl=("cf_ohne_gegenbuchung", ledger.accounts[p].name), glbl=("cf_umbuchung",)); unclear += 1
            continue
        if p is not None and p in ledger.accounts and foreign_currency(ledger.accounts[p]):    # into another currency
            name = ledger.accounts[p].name
            R.add("Investitionen", "Fremdwährung", "Fremdwährung " + name, mk, t.amount, konto=p, art="extern", nw=True,
                  lbl=("cf_fremdwaehrung", name), glbl=("cf_fremdwaehrung_g",))
            continue
        pa = areas.get(p) if p is not None else None
        same = pa is not None and pa == self_name
        if p is not None and roles.get(p) == "eigenkapital" and (same or pa is None):
            R.add("Finanzierung", "Gesellschafter", "Einlagen/Entnahmen Gesellschafter", mk, t.amount, art="extern", nw=True,
                  lbl=("cf_einlagen_gesellschafter",), glbl=("cf_gesellschafter",))
            continue
        if p is not None and not same and p in beteiligungs_gruppen:   # a company: its participation (if held here) takes it
            g = beteiligungs_gruppen[p]
            st = stakes.get(g)
            R.add("Investitionen", "Einlagen/Entnahmen", "Einlage/Entnahme " + g, mk, t.amount, konto=st, art="extern", nw=st is None,
                  lbl=("cf_einlage", g), glbl=("cf_einlagen",))
            if st:
                stake_in[st][mk] += -t.amount
            continue
        if p is not None and not same and pa is not None:             # another area of yours
            if company:
                R.add("Finanzierung", "Gesellschafter", "Einlagen/Entnahmen Gesellschafter", mk, t.amount, art="extern", nw=True,
                      lbl=("cf_einlagen_gesellschafter",), glbl=("cf_gesellschafter",))
            else:
                R.add("Investitionen", "Einlagen/Entnahmen", "Einlage/Entnahme " + pa, mk, t.amount, art="extern", nw=True,
                      lbl=("cf_einlage", pa), glbl=("cf_einlagen",))
            continue
        if p is not None:
            R.add("Unklar", "Umbuchung", "Umbuchung nach " + ledger.accounts[p].path, mk, t.amount, art="unklar",
                  lbl=("cf_umbuchung_mit", ledger.accounts[p].path), glbl=("cf_umbuchung",)); unclear += 1
            continue
        if by_cat[t.id]:
            R.add("Unklar", "Umbuchung", "Umbuchung ohne erkannten Partner", mk, t.amount, art="unklar",
                  lbl=("cf_ohne_partner",), glbl=("cf_umbuchung",)); unclear += 1
            continue
        # income and expenses: by position (MoneyMoney's category assigned to it), a property's in its own rows
        # without a category: the one your categories suggest (learned), else Kontor's estimate by the words -- shown as estimated
        sec = "Einnahmen" if t.amount > 0 else "Ausgaben"
        cat = norm_cat(t.category_path)
        mine = bool(cat)
        if not cat and learned:
            hit = suggest_category(learned, t)
            cat = norm_cat(hit["kategorie"]) if hit else ""
            if cat and is_transfer(cat):                 # learned from transfers: no estimate (a counterpart was not found)
                R.add(sec, "Ohne Kategorie", "Ohne Kategorie", mk, t.amount, ord=900, lbl=("cf_ohne_kategorie",))
                continue
        if cat:
            pos, obj = place(cat)
        else:
            pos, obj = guess_position(t, company), None
            if pos == "wohnen" and company and objekte and t.amount < 0:    # a landlord: costs of the building
                pos = "objektkosten"
        # an estimate only ever counts as income or expense (or interest) -- never as saving, repayment, transfer or left out
        if pos is None or pos not in POS or (not mine and pos in ("anlegen", "tilgung", "ignorieren")):
            R.add(sec, "Ohne Kategorie", "Ohne Kategorie", mk, t.amount, ord=900, lbl=("cf_ohne_kategorie",))
            continue
        det = cat if mine else ""                        # "" = without a category in MoneyMoney (estimated)
        if obj:
            # rent or costs: by the category's sum (a subcategory such as "Hausgeld"); on the property's own category by the booking
            inc = (t.amount > 0) if cat in objekte else totals.get(cat, 0.0) > 0
            sec = "Einnahmen" if inc else "Ausgaben"
            row = "%s · %s" % (obj, "Miete" if inc else "Kosten")
            R.add(sec, row, row, mk, t.amount, ord=POS["vermietung" if inc else "objektkosten"][2] + 0.5, objekt=obj, detail=det,
                  lbl=("cf_objekt_miete" if inc else "cf_objekt_kosten", obj))
            continue
        psec, prow, pord = POS[pos]
        if pos == "ignorieren":
            ignored[mk] += t.amount
        elif pos == "anlegen":
            parts = cat.split(" / ")
            c_to = next((kat_zu_konto[" / ".join(parts[:i])] for i in range(len(parts), 0, -1) if " / ".join(parts[:i]) in kat_zu_konto), None)
            target = c_to if c_to in root_leaves else (depots[0] if len(depots) == 1 and not c_to else None)
            # without a known account the money leaves the net worth -- unless a depot of the area takes it (shown as reason)
            neutral = target is not None or bool(depots)
            R.add("Investitionen", prow, cat, mk, t.amount, konto=target, art="kategorie", nw=not neutral, ord=pord, glbl=("pos_" + pos,))
            if target:
                inbound[target][mk] += -t.amount
            elif neutral:
                no_target[mk] += t.amount
        elif pos in ("tilgung", "zinsen"):
            R.add("Finanzierung", prow, prow, mk, t.amount, art="zins" if pos == "zinsen" else "tilgung", nw=pos == "zinsen", ord=pord,
                  lbl=("pos_" + pos,), detail=det)
        else:
            row, key = position_row(pos, company)
            R.add(psec, row, row, mk, t.amount, ord=pord, lbl=(key,), detail=det)

    # a participation took a contribution: what it is worth more (or less) than the money paid in is its valuation
    for st, per in stake_in.items():
        acc = ledger.accounts[st]
        for mk, v in per.items():
            R.add("Bewertung", acc.name, acc.name, mk, -v, konto=st, art="konto", nw=True)

    if unclear:
        warnings.append(tr("s_d_umbuchung_en_ohne_erkennbaren") % unclear)
    R.pairs = pairs
    R.reasons = {"ignoriert": dict(ignored), "ohne_ziel": dict(no_target)}
    return R, inbound, warnings


# ---------------------------------------------------------------------------
# Bilanz je Bereich
# ---------------------------------------------------------------------------

def reconcile(sektionen: List[dict], nw: Dict[str, float], liq: Dict[str, Optional[float]], mkeys: List[str], leaves: List[Account],
              roles: Dict[str, str], hist: Dict[str, Dict[str, Optional[float]]], R: "Rows", ledger: Ledger, months: List[Tuple[int, int]],
              today: date) -> Dict[str, dict]:
    """Check of the cash flow against the balance sheet, month by month: the rows that change the net worth add up to its change,
    the cash rows to the change of the liquid accounts (with money in transit). A difference is split into its reasons
    ([text key, amount, detail]); what no reason explains is shown as such -- never left out."""
    reasons = getattr(R, "reasons", None) or {}
    ignored, no_target = reasons.get("ignoriert") or {}, reasons.get("ohne_ziel") or {}
    liquid = {a.uuid for a in leaves if roles.get(a.uuid) == "liquiditaet"}
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
        rows = [z for sek in sektionen for z in sek["zeilen"]]
        explained = round(sum(z["werte"].get(mk, 0.0) for z in rows if z["nw"]), 2)
        cash = round(sum(z["werte"].get(mk, 0.0) for sek in sektionen if sek["name"] in CASH_SECTIONS for z in sek["zeilen"]), 2)
        delta = round(nw[mk] - nw[prev], 2)
        dliq = round((liq.get(mk) or 0.0) - (liq.get(prev) or 0.0), 2)
        unknown = sorted(names[u] for u in names
                         if (hist.get(u, {}).get(mk) is None) != (hist.get(u, {}).get(prev) is None))
        g_nw: List[list] = []
        g_liq: List[list] = []
        if abs(ignored.get(mk, 0.0)) >= 0.005:
            g_nw.append(["ue_ignoriert", round(ignored[mk], 2), ""])
            g_liq.append(["ue_ignoriert", round(ignored[mk], 2), ""])
        if abs(no_target.get(mk, 0.0)) >= 0.005:
            g_nw.append(["ue_ohne_ziel", round(no_target[mk], 2), ""])
        tm = round(transit_mixed.get(mk, 0.0) - transit_mixed.get(prev, 0.0), 2)
        if abs(tm) >= 0.005:
            g_liq.append(["ue_unterwegs", tm, ""])
        for z in rows:
            if z["konto"] in liquid and z["art"] in ("korrektur", "depot") and abs(z["werte"].get(mk, 0.0)) >= 0.005:
                g_liq.append(["ue_korrektur" if z["art"] == "korrektur" else "ue_wert", round(z["werte"][mk], 2), names.get(z["konto"], "")])

        def rest(gaps: List[list], total: float) -> None:
            left = round(total - sum(g[1] for g in gaps), 2)
            if abs(left) >= 0.01:
                gaps.append(["ue_unbekannt", left, ", ".join(unknown)] if unknown else ["ue_rest", left, ""])
        un = round(delta - explained, 2)
        ab = round(dliq - cash, 2)
        rest(g_nw, un)
        rest(g_liq, ab)
        out[mk] = {"delta_nw": delta, "erklaert": explained, "unerklaert": un, "gruende": g_nw if abs(un) >= 0.01 else [],
                   "delta_liq": dliq, "zahlungsfluss": cash, "abweichung_liq": ab, "gruende_liq": g_liq if abs(ab) >= 0.01 else []}
    return out


def build_dataset(ledger: Ledger, config: dict, state: dict, today: date, bereich: dict, roles: Dict[str, str],
                  rule_warnings: Optional[List[str]] = None, progress: Optional[Callable[[float, str], None]] = None,
                  learned: Optional[dict] = None) -> dict:
    """bereich: {"id", "name", "art", "anteil", "leaves": [Account]}; learned: patterns from your categories (categorize)"""
    step = progress or (lambda f, t: None)
    order = ledger.order()                      # Konten in der Reihenfolge von MoneyMoney
    bcfg = config.get("bilanz", {}) or {}
    leaves: List[Account] = [a for a in bereich["leaves"] if roles.get(a.uuid) not in OFF_BALANCE]
    # accounts in another currency: not converted (no exchange rates, no estimate) -- shown apart, in their currency
    foreign = [a for a in leaves if foreign_currency(a)]
    leaves = [a for a in leaves if not foreign_currency(a)]
    ausserhalb_accs = [a for a in bereich["leaves"] if roles.get(a.uuid) in ("eigenkapital", "eventual")] + foreign
    leaf_ids = {a.uuid for a in leaves}
    back = int(bcfg.get("monate_zurueck", 0) or 0)
    if back <= 0:
        first_tx = min((t.booking_date for t in ledger.txs if t.account_uuid in leaf_ids), default=today)
        hist_cfg = state.get("historie") or {}
        mm_cfg = state.get("historie_mm") or {}
        first_hist = min((k for u in leaf_ids for k in list(hist_cfg.get(u) or {}) + list(mm_cfg.get(u) or {})), default=None)
        if first_hist and first_hist < month_key(first_tx):
            first_tx = date(int(first_hist[:4]), int(first_hist[5:]), 1)
        y0, m0 = first_tx.year, first_tx.month
    else:
        y0, m0 = add_months(today, -back)
    months = months_between(date(y0, m0, 1), today)
    mkeys = ["%04d-%02d" % ym for ym in months]
    snapshots = state.get("snapshots", {}) or {}
    historie = state.get("historie", {}) or {}
    verlauf_cfg: Dict[str, str] = {}
    for ref, v in (bcfg.get("verlauf") or {}).items():
        try:
            verlauf_cfg[ledger.resolve(ref).uuid] = v
        except KeyError:
            pass

    step(0.05, tr("s_monatsstaende"))
    historie_mm = state.get("historie_mm") or {}
    hist, warn_h, quelle, fortgeschrieben = balance_history(ledger, leaves, months, snapshots, historie, verlauf_cfg, today, config, historie_mm,
                                                            state.get("historie_mm_anfang") or {})
    step(0.3, tr("s_zahlungsstroeme"))
    areas = area_names(ledger, config)
    company = bereich.get("art") == "gesellschaft"
    learned_sig = None
    if learned:
        learned_sig = learned.get("_sig") or hashlib.sha1(json.dumps(learned.get("regeln") or [], sort_keys=True, default=str).encode()).hexdigest()
    objekte = {str(im.get("kategorie")): str(im.get("name") or "") for im in config.get("immobilien") or []
               if isinstance(im, dict) and im.get("kategorie") and str(im.get("bereich") or "") == str(bereich.get("id"))}
    ckey = (getattr(ledger, "_kat_sig", None), tuple(a.uuid for a in leaves), json.dumps(roles, sort_keys=True),
            json.dumps(config.get("kapitalfluss") or {}, sort_keys=True, default=str), tuple(months[0]) if months else None,
            tuple(months[-1]) if months else None, len(months), tuple(sorted(quelle.items())), company, learned_sig, tuple(sorted(objekte.items())),
            json.dumps([sorted(areas.items()), config.get("gesellschaften")], sort_keys=True, default=str))
    cache = ledger.__dict__.setdefault("_classify_cache", {})
    if ckey in cache:
        R, inbound, warn_c = copy.deepcopy(cache[ckey])        # Bereich unveraendert (z. B. Verlauf eines anderen Bereichs geaendert)
    else:
        R, inbound, warn_c = classify(ledger, leaves, roles, config, months, quelle, areas, company, objekte, learned)
        if len(cache) > 24:
            cache.clear()
        cache[ckey] = copy.deepcopy((R, inbound, warn_c))
    step(0.85, tr("x_bilanz"))
    inactive, inactive_auto = inactive_accounts(ledger, leaves, hist, mkeys, config, today, state.get("konten_seit"))
    limits = activity_limits(ledger, leaves, hist, mkeys, today, state.get("konten_seit"))

    # Konten mit Kontostaende-Verlauf: Depots -> Bewertung = Wertaenderung - Zufluesse;
    # andere Konten -> Korrektur = Saldoaenderung - eigene Buchungen (nur dort, wo ein eingetragener Stand abweicht)
    for acc in leaves:
        if quelle.get(acc.uuid) == "stand":
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
                        R.add("Bewertung", acc.name, acc.name, mk, val, konto=acc.uuid, art="depot", nw=True)
                else:
                    val = round(delta - own.get(mk, 0.0), 2)
                    if abs(val) >= 0.005:
                        R.add("Bewertung", acc.name, acc.name + " / Korrektur Kontostand", mk, val, konto=acc.uuid, art="korrektur", nw=True,
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
        bilanz_rows.append({"id": "pos:" + role, "name": role_label(role), "pfad": role_label(role), "ebene": 0, "gruppe": True,
                            "rolle": role, "illiquide": role in illiquid_roles, "depot": False, "offline": False, "inaktiv": False,
                            "passiva": role == "verbindlichkeiten", "werte": werte, "anzahl": len(accs),
                            "inaktive": sum(1 for a in accs if a.uuid in inactive)})
        for a in sorted(accs, key=lambda x: order.get(x.uuid, 10**9)):
            illiq = (role in illiquid_roles) or (a.uuid in illiquid_refs) or any(x.uuid in illiquid_refs for x in ledger.ancestors(a.uuid))
            row = {"id": a.uuid, "name": a.name, "pfad": a.path, "ebene": 1, "gruppe": False, "rolle": role,
                   "illiquide": illiq, "depot": a.portfolio, "offline": a.offline, "inaktiv": a.uuid in inactive,
                   "passiva": role == "verbindlichkeiten", "verlauf": quelle.get(a.uuid, "umsaetze"), "fortgeschrieben_vor": fortgeschrieben.get(a.uuid),
                   "werte": {mk: hist[a.uuid][mk] for mk in mkeys}}
            if a.portfolio:
                wp = depot_holdings(a, row["werte"], mkeys, today, state, (getattr(ledger, "portfolios", None) or {}).get(a.uuid), config)
                if wp:
                    row["wertpapiere"] = wp
            bilanz_rows.append(row)
    # Geld unterwegs (Umbuchung ueber das Monatsende) zaehlt zur Liquiditaet; sonst knickt das Nettovermoegen am Monatsende ein
    transit, transit_details = transit_series(ledger, leaves, roles, months, quelle, today, getattr(R, "pairs", None))
    if any(abs(v) >= 0.005 for v in transit.values()):
        grp = next((r for r in bilanz_rows if r["id"] == "pos:liquiditaet"), None)
        if grp is None:
            grp = {"id": "pos:liquiditaet", "name": role_label("liquiditaet"), "pfad": role_label("liquiditaet"), "ebene": 0, "gruppe": True,
                   "rolle": "liquiditaet", "illiquide": False, "depot": False, "offline": False, "inaktiv": False, "passiva": False,
                   "werte": {mk: 0.0 for mk in mkeys}, "anzahl": 0, "inaktive": 0}
            bilanz_rows.insert(0, grp)
            pos_sums = {"liquiditaet": grp["werte"], **pos_sums}
        idx = max(i for i, r in enumerate(bilanz_rows) if r["rolle"] == "liquiditaet") + 1
        bilanz_rows.insert(idx, {"id": "transit", "name": tr("s_geld_unterwegs"), "pfad": tr("s_geld_unterwegs"), "ebene": 1, "gruppe": False,
                                 "rolle": "liquiditaet", "transit": True, "illiquide": False, "depot": False, "offline": False, "inaktiv": False,
                                 "passiva": False, "werte": dict(transit), "umbuchungen": transit_details})
        for mk in mkeys:
            grp["werte"][mk] = round((grp["werte"][mk] or 0.0) + transit[mk], 2)
    nw = {mk: round(sum(pos_sums[r][mk] for r in pos_sums), 2) for mk in mkeys}
    aktiva = {mk: round(sum(pos_sums[r][mk] for r in pos_sums if r != "verbindlichkeiten"), 2) for mk in mkeys}
    passiva = {mk: round(pos_sums.get("verbindlichkeiten", {}).get(mk, 0.0), 2) for mk in mkeys}
    liquid_nw = {mk: round(nw[mk] - sum((r["werte"][mk] or 0.0) for r in bilanz_rows if not r["gruppe"] and r["illiquide"]), 2) for mk in mkeys}
    # Ausserhalb des Nettovermoegens: Kapitalkonten (Eigenkapital) und Avale/Buergschaften -- nur zur Information
    ausserhalb = []
    out_role = lambda a: "fremdwaehrung" if foreign_currency(a) else roles.get(a.uuid)
    for a in sorted(ausserhalb_accs, key=lambda x: (out_role(x) or "", order.get(x.uuid, 10**9))):
        wh, _, _ = account_balance_series(ledger, a, months, verlauf_quelle(a, verlauf_cfg), snapshots, historie.get(a.uuid) or {}, today, config,
                                             historie_mm.get(a.uuid), (state.get("historie_mm_anfang") or {}).get(a.uuid))
        ausserhalb.append({"id": a.uuid, "name": a.name, "pfad": a.path, "rolle": out_role(a), "waehrung": a.currency or "EUR",
                           "werte": {mk: wh[mk] for mk in mkeys}})

    # Kapitalfluss-Sektionen
    sektionen = []
    for sec in SECTIONS:
        zeilen = []
        for (s, row), vals in R.vals.items():
            if s != sec:
                continue
            m = R.meta[(s, row)]
            z = {"zeile": row, "gruppe": m["gruppe"], "konto": m["konto"], "art": m["art"], "nw": m["nw"],
                 "werte": {mk: round(vals.get(mk, 0.0), 2) for mk in mkeys}}
            for k in ("lbl", "glbl", "ord", "objekt"):
                if m.get(k) is not None:
                    z[k] = m[k]
            det = R.det.get((s, row))
            if det:                                      # the categories inside a position (largest first)
                z["details"] = sorted(({"kategorie": c, "werte": {mk: round(v.get(mk, 0.0), 2) for mk in mkeys}} for c, v in det.items()),
                                      key=lambda d: -abs(sum(d["werte"].values())))
            zeilen.append(z)
        gsum = defaultdict(float)
        for z in zeilen:
            gsum[z["gruppe"]] += abs(sum(z["werte"].values()))
        # the fixed outline first (positions in their order), then the rest by size
        zeilen.sort(key=lambda z: (z.get("ord", 500), -gsum[z["gruppe"]], z["gruppe"], z["zeile"]))
        sektionen.append({"name": sec, "zeilen": zeilen})

    ueberleitung = reconcile(sektionen, nw, pos_sums.get("liquiditaet") or {}, mkeys, leaves, roles, hist, R, ledger, months, today)

    loans_cfg = {}
    for l in config.get("darlehen", []) or []:
        try:
            a = ledger.resolve(l["darlehenskonto"])
            z = l.get("zins") or {}
            loans_cfg[a.uuid] = {"name": a.name, "modell": z.get("modell", "jahresbasis"), "satz": z.get("satz") or [], "art": l.get("art", "verbindlichkeit")}
        except KeyError:
            pass

    warnings = list(rule_warnings or []) + warn_h + warn_c
    if foreign:
        warnings.append(tr("s_fremdwaehrung", ", ".join("%s (%s)" % (a.name, a.currency) for a in foreign)))
    return {
        "erstellt": today.isoformat(),
        "heute": today.isoformat(),
        "monate": mkeys,
        "ist_bis": month_key(today),
        "bereich": {"id": bereich["id"], "name": bereich["name"], "art": bereich.get("art"), "anteil": bereich.get("anteil")},
        "bilanz": {"zeilen": bilanz_rows, "nettovermoegen": nw, "aktiva": aktiva, "passiva": passiva,
                   "liquides_nettovermoegen": liquid_nw, "positionen": {r: role_label(r) for r in pos_sums}, "ausserhalb": ausserhalb},
        "kapitalfluss": {"sektionen": sektionen, "ueberleitung": ueberleitung},
        "darlehen_konfig": loans_cfg,
        "konten_inaktiv": sorted(inactive),
        "konten_inaktiv_auto": sorted(inactive_auto),
        "konten_aktivitaet": limits,
        "warnungen": warnings,
    }


# ---------------------------------------------------------------------------
# Planung
# ---------------------------------------------------------------------------

def shareholder_ids(ledger: Ledger) -> Set[str]:
    """Capital and shareholder accounts (by their own name, otherwise their group's): the partners' equity in a company."""
    out: Set[str] = set()

    def walk(acc: Account, inherited: bool):
        own = _hint_role(acc.name)
        here = own == "kapital" or (own is None and inherited)
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
        for r in (ds.get("bilanz") or {}).get("zeilen") or []:
            if not r.get("gruppe") and r.get("id") and isinstance(r.get("werte"), dict):
                vals.setdefault(r["id"], r["werte"])
    sh = shareholder_ids(ledger)
    links: List[dict] = []
    by_id = {b["id"]: b for b in bereiche}
    for e in config.get("gesellschaften") or []:
        b = by_id.get(str((e or {}).get("bereich")))
        if not b or not e.get("beteiligung") or b.get("anteil") is None:
            continue
        try:
            tgt = ledger.resolve(e["beteiligung"])
        except (KeyError, TypeError, AttributeError):
            continue
        if tgt.group:
            continue
        accs = [a for a in b["leaves"] if roles.get(a.uuid) not in OFF_BALANCE]
        links.append({"n": len(links), "ziel": tgt.uuid, "name": b["name"], "anteil": float(b["anteil"]), "konten": accs})
    targets = {lk["ziel"] for lk in links}

    def look(accs: List[Account], mk: str, seen: frozenset) -> dict:
        ids = {a.uuid for a in accs}
        own, konten, unknown = 0.0, [], []
        for a in accs:
            if a.uuid in sh or a.uuid in targets or roles.get(a.uuid) == "beteiligungen":
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
            if lk["ziel"] not in ids or lk["n"] in seen:
                continue
            sub = look(lk["konten"], mk, seen | {lk["n"]})
            unknown += sub["unbekannt"]
            firmen.append({"name": lk["name"], "anteil": lk["anteil"], "schulden": sub["summe"], "anteilig": round(lk["anteil"] * sub["summe"], 2),
                           "konten": sub["konten"] + [[t["name"], t["anteilig"]] for t in sub["firmen"]]})
        return {"eigene": round(own, 2), "konten": sorted(konten, key=lambda x: -x[1]), "firmen": firmen, "unbekannt": unknown,
                "summe": round(own + sum(f["anteilig"] for f in firmen), 2)}

    for b in bereiche:
        ds = datasets.get(b["id"]) or {}
        if "bilanz" not in ds:
            continue
        accs = [a for a in b["leaves"] if roles.get(a.uuid) not in OFF_BALANCE]
        nw = ds["bilanz"].get("nettovermoegen") or {}
        ohne = sorted({a.name for a in accs if roles.get(a.uuid) == "beteiligungen" and a.uuid not in targets and a.uuid not in sh})
        monate = {}
        for mk in ds.get("monate") or []:
            r = look(accs, mk, frozenset())
            kap = 0.0 if b.get("haupt") else sum(max(0.0, -((vals.get(a.uuid) or {}).get(mk) or 0.0)) for a in accs if a.uuid in sh)
            ek = round((nw.get(mk) or 0.0) + kap, 2)
            den = ek + r["summe"]
            monate[mk] = {"quote": round(ek / den, 4) if den > 0.005 and not r["unbekannt"] else None, "ek": ek, "nw": nw.get(mk),
                          "kapital": round(kap, 2), "schulden": r["summe"], "eigene": r["eigene"], "konten": r["konten"], "firmen": r["firmen"],
                          "unbekannt": sorted(set(r["unbekannt"]))}
        ds["bilanz"]["ek_quote"] = {"monate": monate, "ohne_durchschau": ohne}


def _rate_at(rates: List[dict], day: date) -> Optional[float]:
    best = None
    for r in sorted(rates, key=lambda x: x.get("ab", "0000-00-00")):
        ab = date.fromisoformat(r["ab"]) if r.get("ab") else date(1900, 1, 1)
        if ab <= day:
            best = float(r["prozent"])
    return best


def _plan_value(method: str, hist_vals: List[float], same_month_last_year: Optional[float], betrag: Optional[float],
                budget: Optional[float] = None) -> float:
    if method == "keine":
        return 0.0
    if method == "budget":
        return float(budget or 0.0)
    if method == "fix":
        return float(betrag or 0.0)
    if method == "jahresbetrag":
        return round(float(betrag or 0.0) / 12.0, 2)
    if method == "vorjahr":
        return float(same_month_last_year or 0.0)
    n = 6 if method == "gleitend6" else 12
    vals = hist_vals[-n:]
    return round(sum(vals) / n, 2) if vals else 0.0


def _event_months(ev: dict, future: List[str]) -> List[str]:
    start = str(ev.get("monat") or "")[:7]
    if len(start) != 7:
        return []
    rep = ev.get("wiederholung") or "einmalig"
    bis = str(ev.get("bis") or "")[:7] or future[-1]
    out = []
    for mk in future:
        if mk < start or mk > bis:
            continue
        if rep == "einmalig" and mk != start:
            continue
        if rep == "jaehrlich" and mk[5:] != start[5:]:
            continue
        if rep == "quartal" and (int(mk[5:]) - int(start[5:])) % 3 != 0:
            continue
        out.append(mk)
    return out


def apply_plan(dataset: dict, plan: dict, config: dict, fremd_nw: Optional[Dict[str, Dict[str, float]]] = None,
               immo: Optional[List[dict]] = None, ledger_resolve=None) -> dict:
    """Planung auf einen Bereichs-Datensatz anwenden (in place).
    fremd_nw: Nettovermoegensplan anderer Bereiche (id -> {mk: nw}) fuer Beteiligungskonten.
    immo: Immobilienkalkulationen dieses Bereichs mit Planreihen (siehe realestate.planreihen) und Zuordnungen."""
    horizon = max(1, min(240, int(plan.get("horizont_monate", 24))))
    default_method = plan.get("standard_methode", "gleitend12")
    inflation = float(plan.get("inflation_prozent_pa", 2.0) or 0.0)
    growth_default = {"Ausgaben": float(plan.get("steigerung_ausgaben_prozent_pa", inflation) if plan.get("steigerung_ausgaben_prozent_pa") is not None else inflation),
                      "Einnahmen": float(plan.get("steigerung_einnahmen_prozent_pa") or 0.0)}
    rendite = float(plan.get("rendite_prozent_pa") or 0.0)
    budgets: Dict[str, float] = dataset.get("budgets") or {}
    rows_cfg: Dict[str, dict] = dict(plan.get("zeilen", {}) or {})
    for old_key, new_key in RENAMED_ROWS.items():          # a row renamed: your settings stay with it
        if old_key in rows_cfg and new_key not in rows_cfg:
            rows_cfg[new_key] = rows_cfg[old_key]
    row_of_cat: Dict[str, str] = {}               # category -> the row it counts in (budgets of a category above several rows)
    for sek in dataset.get("kapitalfluss", {}).get("sektionen", []):
        for z in sek["zeilen"]:
            for d in z.get("details") or []:
                if d["kategorie"]:
                    row_of_cat[d["kategorie"]] = sek["name"] + "/" + z["zeile"]

    def position_budget(key: str, z: dict) -> Optional[float]:
        """A position's budget: the budgets in MoneyMoney of its categories -- a budget on a category above them counts when
        all of its categories are in this row (then those below it do not count again)."""
        cats = [d["kategorie"] for d in z.get("details") or [] if d["kategorie"]]
        if not cats:
            return budgets.get(z["zeile"])
        own = {b: v for b, v in budgets.items()
               if any(c == b or c.startswith(b + " / ") for c in cats)
               and all(r == key for c, r in row_of_cat.items() if c == b or c.startswith(b + " / "))}
        own = {b: v for b, v in own.items() if not any(a != b and b.startswith(a + " / ") for a in own)}
        return round(sum(own.values()), 2) if own else None
    loans_plan: Dict[str, dict] = plan.get("darlehen", {}) or {}
    wert_cfg: Dict[str, dict] = plan.get("wertentwicklung", {}) or {}
    events: List[dict] = [e for e in (plan.get("ereignisse") or []) if isinstance(e, dict) and e.get("aktiv", True)]
    ist = dataset["monate"]
    cur = dataset["ist_bis"]
    full_months = [mk for mk in ist if mk < cur]
    y, m = int(cur[:4]), int(cur[5:])
    future = []
    for _ in range(horizon):
        y, m = add_months(date(y, m, 1), 1)
        future.append("%04d-%02d" % (y, m))
    while m != 12:                                       # letztes Planjahr immer vollstaendig
        y, m = add_months(date(y, m, 1), 1)
        future.append("%04d-%02d" % (y, m))
    dataset["plan_monate"] = future
    sektionen = dataset["kapitalfluss"]["sektionen"]
    rows_b = dataset["bilanz"]["zeilen"]
    leaf_rows = [r for r in rows_b if not r["gruppe"]]
    by_uuid = {r["id"]: r for r in leaf_rows}
    by_name = {r["name"]: r for r in leaf_rows}
    loans_cfg = dataset.get("darlehen_konfig", {})
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
        reihen = im.get("reihen") or {}
        name = str(im.get("name") or "Immobilie")
        rent = reihen.get("miete", {})
        costs = {mk: reihen.get("kosten", {}).get(mk, 0.0) + reihen.get("ruecklage", {}).get(mk, 0.0) for mk in future}
        # the property's own rows (its categories, classify: objekt) take the calculation; without actual figures new rows
        for sec_name, row, series, key in (("Einnahmen", "%s · Miete" % name, rent, "cf_objekt_miete"), ("Ausgaben", "%s · Kosten" % name, costs, "cf_objekt_kosten")):
            if not im.get("kategorie"):
                continue
            if any(z.get("objekt") == name for z in sec_by_name[sec_name]["zeilen"]):
                for z in sec_by_name[sec_name]["zeilen"]:
                    if z.get("objekt") == name:
                        immo_rows[(sec_name, z["zeile"])] = series
            else:
                immo_extra.append({"sektion": sec_name, "gruppe": row, "zeile": row, "art": "immobilie", "nw": True, "werte": series,
                                   "objekt": name, "lbl": [key, name]})
        for lname, ref in (im.get("darlehen_konten") or {}).items():
            u = resolve_ref(ref)
            if u and lname in (reihen.get("darlehen") or {}):
                immo_loans[u] = reihen["darlehen"][lname]
        ou = resolve_ref(im.get("objekt_konto"))
        if ou and reihen.get("wert"):
            immo_wert[ou] = reihen["wert"]
        if reihen.get("ausschuettung") and any(abs(v) > 0.005 for v in reihen["ausschuettung"].values()):
            for mk, v in reihen["ausschuettung"].items():     # money to the partners: the row of their contributions/withdrawals
                payout[mk] = payout.get(mk, 0.0) + v
    if payout:
        own = "Einlagen/Entnahmen Gesellschafter"
        if any(z["zeile"] == own for z in sec_by_name["Finanzierung"]["zeilen"]):
            immo_rows[("Finanzierung", own)] = payout
        else:
            immo_extra.append({"sektion": "Finanzierung", "gruppe": "Gesellschafter", "zeile": own, "art": "extern", "nw": True,
                               "werte": payout, "lbl": ["cf_einlagen_gesellschafter"], "glbl": ["cf_gesellschafter"]})
    for ex in immo_extra:
        sek = sec_by_name[ex["sektion"]]
        sek["zeilen"].append(dict({"zeile": ex["zeile"], "gruppe": ex["gruppe"], "konto": None, "art": ex["art"], "nw": ex["nw"],
                                   "werte": {mk: 0.0 for mk in ist}, "synthetisch": True},
                                  **{k: ex[k] for k in ("objekt", "lbl", "glbl") if ex.get(k)}))
        immo_rows[(ex["sektion"], ex["zeile"])] = ex["werte"]
    fixed_rows: Dict[Tuple[str, str], Tuple[Dict[str, float], str]] = {k: (v, "immobilie") for k, v in immo_rows.items()}

    # 0b. Ereignisse: Zeilen anlegen
    event_moves: Dict[str, List[Tuple[Optional[str], Optional[str], float]]] = defaultdict(list)   # mk -> [(von, nach, betrag)]
    liquid_ids = {r["id"] for r in leaf_rows if r["rolle"] == "liquiditaet"}
    event_rows: Dict[Tuple[str, str], Dict[str, float]] = {}
    for ev in events:
        betrag = float(str(ev.get("betrag") or 0).replace(",", ".") or 0)
        months_ = _event_months(ev, future)
        if not betrag or not months_:
            continue
        art = ev.get("art") or "umschichtung"
        text = ev.get("text") or "Ereignis"
        von = resolve_ref(ev.get("von"))
        nach = resolve_ref(ev.get("nach"))
        if art in ("einnahme", "ausgabe"):
            sec = "Einnahmen" if art == "einnahme" else "Ausgaben"
            key = (sec, "Ereignis: " + text)
            event_rows.setdefault(key, {})
            for mk in months_:
                event_rows[key][mk] = event_rows[key].get(mk, 0.0) + (betrag if art == "einnahme" else -betrag)
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
            sec = "Finanzierung" if orow.get("rolle") == "verbindlichkeiten" else "Investitionen"
            key = (sec, "Ereignis: " + text)
            event_rows.setdefault(key, {})
            for mk in months_:
                event_rows[key][mk] = event_rows[key].get(mk, 0.0) + (-betrag if von_liq else betrag)
    for (sec, zeile), vals in event_rows.items():
        sek = sec_by_name[sec]
        sek["zeilen"].append({"zeile": zeile, "gruppe": "Geplante Ereignisse", "konto": None, "art": "ereignis",
                              "nw": sec in ("Einnahmen", "Ausgaben"), "werte": {mk: 0.0 for mk in ist}, "synthetisch": True})
        fixed_rows[(sec, zeile)] = (vals, "ereignis")

    # 1. Planwerte je Zeile
    for sek in sektionen:
        for z in sek["zeilen"]:
            key = sek["name"] + "/" + z["zeile"]
            cfg = rows_cfg.get(key, {})
            fx = fixed_rows.get((sek["name"], z["zeile"]))
            fixed = fx[0] if fx else None
            if fx:
                method = fx[1]
            elif cfg.get("methode"):
                method = cfg["methode"]
            elif sek["name"] in ("Bewertung", "Unklar") or z.get("art") == "extern":     # contributions/withdrawals: one-offs
                method = "keine"
            elif sek["name"] == "Investitionen" and z.get("art") in ("extern", "konto", "rueckzahlung", "zins"):
                method = "keine" if z.get("art") in ("extern", "konto") else default_method
            else:
                method = default_method
            growth = float(cfg.get("steigerung_prozent_pa", growth_default.get(sek["name"], 0.0)))
            hist_vals = [z["werte"][mk] for mk in full_months]
            overrides = cfg.get("werte", {}) or {}
            # a position's budget: the sum of the budgets of its categories in MoneyMoney
            budget = position_budget(sek["name"] + "/" + z["zeile"], z)
            if budget is not None and sek["name"] == "Ausgaben":
                budget = -abs(budget)
            z["plan"] = {"methode": method, "betrag": cfg.get("betrag"), "steigerung_prozent_pa": growth, "budget": budget,
                         "werte": {}, "vorschlag": {}, "ueberschrieben": sorted(k for k in overrides if k in future)}
            if fixed is not None:
                for mk in future:
                    v = round(float(fixed.get(mk, 0.0)), 2)
                    z["plan"]["vorschlag"][mk] = v
                    z["plan"]["werte"][mk] = float(overrides[mk]) if mk in overrides else v
                continue
            base_val = _plan_value(method, hist_vals, None, cfg.get("betrag"), budget)
            for i, mk in enumerate(future):
                if method == "vorjahr":
                    ly = "%04d-%02d" % (int(mk[:4]) - 1, int(mk[5:]))
                    v = z["werte"].get(ly, z["plan"]["werte"].get(ly, 0.0)) * (1 + growth / 100.0)
                else:
                    v = base_val * ((1 + growth / 100.0) ** ((i + 1) / 12.0))
                z["plan"]["vorschlag"][mk] = round(v, 2)
                z["plan"]["werte"][mk] = float(overrides[mk]) if mk in overrides else round(v, 2)

    # 2. Darlehensplan
    fin = sec_by_name["Finanzierung"]
    loan_groups: Dict[str, Dict[str, dict]] = defaultdict(dict)
    for z in fin["zeilen"]:
        if z.get("konto"):
            loan_groups[z["konto"]][z["art"]] = z
    loan_state: Dict[str, dict] = {}
    for uuid, parts in loan_groups.items():
        acc = by_uuid.get(uuid)
        if acc is None:
            continue
        name = acc["name"]
        if uuid in immo_loans:
            series = immo_loans[uuid]
            for part, key in (("zins", "zins"), ("tilgung", "tilgung")):
                z = parts.get(part)
                if z:
                    for mk in future:
                        v = round(float(series.get(key, {}).get(mk, 0.0)), 2)
                        z["plan"]["vorschlag"][mk] = v
                        if mk not in (rows_cfg.get("Finanzierung/" + z["zeile"], {}).get("werte") or {}):
                            z["plan"]["werte"][mk] = v
                    z["plan"]["methode"] = "immobilie"
            continue
        lp = dict(loans_cfg.get(uuid, {}))
        lp.update(loans_plan.get(name, {}))
        rate = None
        if lp.get("zins_prozent_pa") is not None:
            rate = float(lp["zins_prozent_pa"])
        elif lp.get("satz"):
            rate = _rate_at(lp["satz"], date(int(future[0][:4]), int(future[0][5:]), 1))
        if rate is None:
            continue
        tilg, zins = parts.get("tilgung"), parts.get("zins")
        pay_hist = [(tilg["werte"][mk] if tilg else 0.0) + (zins["werte"][mk] if zins else 0.0) for mk in full_months[-12:]]
        payment = float(lp.get("zahlung") or (round(-sum(pay_hist) / len(pay_hist), 2) if pay_hist else 0.0))
        loan_state[uuid] = {"rate": rate, "payment": payment, "modell": lp.get("modell", "restschuld_monatlich"),
                            "tilg": tilg, "zins": zins, "name": name,
                            "ov_t": (rows_cfg.get("Finanzierung/" + tilg["zeile"], {}).get("werte") or {}) if tilg else {},
                            "ov_z": (rows_cfg.get("Finanzierung/" + zins["zeile"], {}).get("werte") or {}) if zins else {}}

    # 3. Fortschreibung je Konto
    liq_total = {mk: round(sum((r["werte"][mk] or 0.0) for r in leaf_rows if r["rolle"] == "liquiditaet"), 2) for mk in ist}
    bal: Dict[str, float] = {r["id"]: (r["werte"][ist[-1]] or 0.0) for r in leaf_rows}
    year_base: Dict[str, Dict[int, float]] = defaultdict(dict)
    for r in leaf_rows:
        if r["rolle"] == "liquiditaet":
            continue
        for mk in ist:
            if mk.endswith("-12"):
                year_base[r["id"]][int(mk[:4]) + 1] = r["werte"][mk] or 0.0
    inv_rows = [z for sek in sektionen if sek["name"] == "Investitionen" for z in sek["zeilen"]]
    growth_of: Dict[str, Tuple[float, Optional[float]]] = {}
    fremd_link: Dict[str, Tuple[str, float]] = {}
    for r in leaf_rows:
        w = wert_cfg.get(r["name"]) or wert_cfg.get(r["pfad"]) or wert_cfg.get(r["id"])
        if w and w.get("bereich"):
            fremd_link[r["id"]] = (str(w["bereich"]), float(w.get("anteil", 1.0)))
        elif w and (w.get("prozent_pa") not in (None, "") or w.get("basis") not in (None, "")):
            growth_of[r["id"]] = (float(w.get("prozent_pa") or 0.0), (float(w["basis"]) if w.get("basis") not in (None, "") else None))
        elif rendite and (r["depot"] or r["rolle"] in ("wertpapiere", "anlagen")):
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
        # Darlehen mit Zinsmodell
        for uuid, st in loan_state.items():
            b = bal[uuid]
            sign = -1.0 if b < 0 else 1.0
            if st["modell"] == "jahresbasis":
                if yr not in year_base[uuid]:
                    year_base[uuid][yr] = b
                base = abs(year_base[uuid][yr])
            else:
                base = abs(b)
            interest = round(base * st["rate"] / 1200.0, 2) if abs(b) > 0.005 else 0.0
            principal = min(max(st["payment"] - interest, 0.0), abs(b))
            if st["zins"]:
                st["zins"]["plan"]["vorschlag"][mk] = round(sign * interest, 2)
                if mk in st["ov_z"]:
                    interest = abs(float(st["ov_z"][mk]))
                st["zins"]["plan"]["werte"][mk] = round(sign * interest, 2)
                st["zins"]["plan"]["methode"] = "darlehen"
            if st["tilg"]:
                st["tilg"]["plan"]["vorschlag"][mk] = round(sign * principal, 2)
                if mk in st["ov_t"]:
                    principal = min(abs(float(st["ov_t"][mk])), abs(b))
                st["tilg"]["plan"]["werte"][mk] = round(sign * principal, 2)
                st["tilg"]["plan"]["methode"] = "darlehen"
            bal[uuid] = round(b - sign * principal, 2)
            if mo == 12:
                year_base[uuid][yr + 1] = bal[uuid]
        # Darlehen aus Immobilienkalkulation: Saldo direkt aus der Kalkulation
        for uuid, series in immo_loans.items():
            if uuid in bal and mk in (series.get("saldo") or {}):
                bal[uuid] = round(float(series["saldo"][mk]), 2)
        # Darlehen ohne bekannten Zinssatz: Saldo folgt der geplanten Tilgungszeile
        for uuid, parts in loan_groups.items():
            if uuid in loan_state or uuid in immo_loans or uuid not in bal or not parts.get("tilgung"):
                continue
            tilg = parts["tilgung"]
            v = tilg["plan"]["werte"].get(mk, 0.0)
            b = bal[uuid]
            nb = b - v
            if (b < 0 < nb) or (b > 0 > nb):
                nb = 0.0
                tilg["plan"]["werte"][mk] = round(b, 2)
            bal[uuid] = round(nb, 2)
        # Investitionen in Konten
        for z in inv_rows:
            v = z["plan"]["werte"].get(mk, 0.0)
            if z.get("konto") and z["konto"] in bal and z["art"] in ("konto", "kategorie", "rueckzahlung"):
                bal[z["konto"]] = round(bal[z["konto"]] - v, 2)
            elif z["art"] == "extern":
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
            if by_uuid[uuid]["rolle"] != "liquiditaet":
                plan_rows[uuid][mk] = bal[uuid]

    # Summen je Monat (Ist + Plan)
    all_months = ist + future
    sums: Dict[str, Dict[str, float]] = {}

    def val_of(z, mk):
        return z["werte"].get(mk, 0.0) if mk in z["werte"] else z.get("plan", {}).get("werte", {}).get(mk, 0.0)
    for mk in all_months:
        s = {}
        for sek in sektionen:
            s[sek["name"]] = round(sum(val_of(z, mk) for z in sek["zeilen"]), 2)
        s["Zinsen"] = round(sum(val_of(z, mk) for sek in sektionen for z in sek["zeilen"] if z["art"] == "zins"), 2)
        s["Operativ"] = round(s["Einnahmen"] + s["Ausgaben"], 2)
        # what is left after interest and repayments (a new loan is no income: only payments count)
        fin = [z for sek in sektionen if sek["name"] == "Finanzierung" for z in sek["zeilen"]]
        s["Nach_Kapitaldienst"] = round(s["Operativ"] + sum(val_of(z, mk) for z in fin if z["art"] == "zins")
                                        + sum(min(val_of(z, mk), 0.0) for z in fin if z["art"] == "tilgung"), 2)
        trade = [z for sek in sektionen for z in sek["zeilen"] if (z.get("lbl") or [""])[0] in ("pos_umsatz", "pos_wareneinkauf")]
        if any((z.get("lbl") or [""])[0] == "pos_umsatz" for z in trade):          # a trading business: revenue minus goods
            s["Rohertrag"] = round(sum(val_of(z, mk) for z in trade), 2)
        s["Cashflow"] = round(sum(s[k] for k in CASH_SECTIONS), 2)
        s["Nettovermoegen_delta"] = round(sum(val_of(z, mk) for sek in sektionen for z in sek["zeilen"] if z["nw"]), 2)
        sums[mk] = s
    dataset["kapitalfluss"]["summen"] = sums

    # Liquiditaet und Nettovermoegen fortschreiben; Rest als Bewertung ausweisen
    liq_prev = liq_total[ist[-1]]
    liq_plan: Dict[str, float] = {}
    nw_plan: Dict[str, float] = {}
    nw_prev = dataset["bilanz"]["nettovermoegen"][ist[-1]]
    einl_cum = 0.0
    for mk in ist:                                  # bank balance at the end of the month, as in the balance sheet (money in transit too)
        sums[mk]["Bankguthaben"] = liq_total[mk]
    for mk in future:
        liq_prev = round(liq_prev + sums[mk]["Cashflow"], 2)
        liq_plan[mk] = liq_prev
        sums[mk]["Bankguthaben"] = liq_prev
        einl_cum += einlagen_plan.get(mk, 0.0)
        total = liq_prev + sum(plan_rows[u][mk] for u in plan_rows) + einl_cum
        nw_plan[mk] = round(total, 2)
        prev_nw = nw_plan.get(prev_mk_of(future, mk), nw_prev)
        bew = round(nw_plan[mk] - prev_nw - sums[mk]["Nettovermoegen_delta"], 2)
        if abs(bew) >= 0.005:
            sums[mk]["Bewertung"] = round(sums[mk]["Bewertung"] + bew, 2)
            sums[mk]["Nettovermoegen_delta"] = round(sums[mk]["Nettovermoegen_delta"] + bew, 2)

    # Projektion nach Positionen
    proj_rows: List[dict] = []
    for r in rows_b:
        if r["gruppe"]:
            role = r["rolle"]
            members = [x for x in leaf_rows if x["rolle"] == role]
            werte = {}
            for mk in future:
                if role == "liquiditaet":
                    werte[mk] = liq_plan[mk]
                else:
                    werte[mk] = round(sum(plan_rows.get(x["id"], {}).get(mk, 0.0) for x in members), 2)
            proj_rows.append({"id": r["id"], "name": r["name"], "ebene": 0, "gruppe": True, "rolle": role, "werte": werte})
        elif r["rolle"] != "liquiditaet" and not r.get("inaktiv"):
            proj_rows.append({"id": r["id"], "name": r["name"], "ebene": 1, "gruppe": False, "rolle": r["rolle"],
                              "werte": {mk: plan_rows[r["id"]][mk] for mk in future}})
    if any(einlagen_plan.values()):
        proj_rows.append({"id": "einlagen", "name": "Einlagen/Entnahmen Beteiligungen (kumuliert, Plan)", "ebene": 1, "gruppe": False, "rolle": "beteiligungen",
                          "werte": {mk: round(einl_cum_at(einlagen_plan, future, mk), 2) for mk in future}})

    dataset["bilanz"]["projektion"] = {"zeilen": proj_rows, "liquiditaet": liq_plan, "nettovermoegen": nw_plan}
    dataset["kennzahlen"] = kennzahlen(dataset, plan, liq_total, full_months)
    dataset["plan"] = {"horizont_monate": horizon, "standard_methode": default_method, "inflation_prozent_pa": inflation,
                       "steigerung_einnahmen_prozent_pa": growth_default["Einnahmen"], "steigerung_ausgaben_prozent_pa": growth_default["Ausgaben"],
                       "rendite_prozent_pa": rendite, "fi_rendite_real_prozent": float(plan.get("fi_rendite_real_prozent") or 3.0),
                       "zeilen": rows_cfg, "darlehen": loans_plan, "wertentwicklung": wert_cfg, "ereignisse": plan.get("ereignisse") or []}
    return dataset


def prev_mk_of(future: List[str], mk: str) -> str:
    i = future.index(mk)
    return future[i - 1] if i > 0 else ""


def einl_cum_at(einlagen_plan: Dict[str, float], future: List[str], mk: str) -> float:
    return sum(v for k, v in einlagen_plan.items() if k <= mk)


def kennzahlen(dataset: dict, plan: dict, liq_total: Dict[str, float], full_months: List[str]) -> dict:
    sums = dataset["kapitalfluss"]["summen"]
    last12 = full_months[-12:]
    n = max(1, len(last12))
    ausgaben = -sum(sums[mk]["Ausgaben"] for mk in last12) / n
    zinsen = -sum(sums[mk]["Zinsen"] for mk in last12) / n
    operativ = sum(sums[mk]["Operativ"] for mk in last12)
    cur = dataset["ist_bis"]
    liq = liq_total.get(cur, 0.0)
    real = float(plan.get("fi_rendite_real_prozent") or 3.0)
    monatlich = ausgaben + zinsen
    benoetigt = round(monatlich * 12 / (real / 100.0), 2) if real > 0 and monatlich > 0 else None
    lnw = dataset["bilanz"]["liquides_nettovermoegen"][cur]
    nw = dataset["bilanz"]["nettovermoegen"][cur]
    ein = sum(sums[mk]["Einnahmen"] for mk in last12)
    return {
        "ausgaben_monat": round(ausgaben, 2), "zinsen_monat": round(zinsen, 2), "operativ_12m": round(operativ, 2),
        "liquiditaet": liq, "reichweite_monate": round(liq / monatlich, 1) if monatlich > 0 else None,
        "fi_rendite_real_prozent": real, "fi_benoetigt": benoetigt,
        "fi_abdeckung_liquide": round(lnw / benoetigt, 3) if benoetigt else None,
        "fi_abdeckung_gesamt": round(nw / benoetigt, 3) if benoetigt else None,
        "sparquote": round(operativ / ein, 3) if ein > 0 else None,
    }
