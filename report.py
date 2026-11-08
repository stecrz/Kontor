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
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from model import Account, Ledger, Tx, add_months, month_end, month_key, months_between, norm_cat
from rules import TAG_RE
from i18n import tr
from categorize import fold as fold_category

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
NAME_HINTS = [
    (r"off.?balance|nicht bilanz", "ignorieren"),
    (r"aval|b(ü|ue)rgschaft|garantie", "eventual"),
    (r"eigenkapital", "eigenkapital"),
    # Kapital-/Gesellschafterkonten wie Gesellschafterdarlehen: in der Gesellschaft Schuld an den Gesellschafter, privat Forderung;
    # das Nettovermoegen der Gesellschaft ist dann der Rest, der nach Anteil verteilt wird (stimmt auch bei ungleichen Einlagen)
    (r"kapitalkont|gesellschafterkont|gesellschafterdarlehen", "+/-"),
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
COST_WORDS = ["zins", "interest", "gebühr", "gebuehr", "entgelt", "provision", "bereitstellung", "#mm-zins"]
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


def _signed(role: Optional[str], acc: Account) -> Optional[str]:
    """"+/-": Guthaben -> Forderung, Schuld -> Verbindlichkeit."""
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

    def walk(acc: Account, group_hint: Optional[str]):
        if acc.group:
            here = cfg_roles.get(acc.uuid) or _hint_role(acc.name) or group_hint
        else:
            t = (acc.type or "").lower()
            role = cfg_roles.get(acc.uuid)
            if not role and acc.portfolio:
                role = "wertpapiere"
            if not role:
                role = _signed(_hint_role(acc.name), acc)
            if not role:
                role = _signed(next((r for k, r in STRONG_TYPES.items() if k in t), None), acc)
            if not role and group_hint:
                role = _signed(group_hint, acc)
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
                   live: Optional[list]) -> List[dict]:
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
    for key, r in rows.items():                       # names Kontor has seen in MoneyMoney's export before
        r["name"] = r["name"] or names.get(key, "")
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


def inactive_accounts(ledger: Ledger, leaves: List[Account], hist: Dict[str, Dict[str, Optional[float]]], mkeys: List[str],
                      config: dict, today: date) -> Tuple[Set[str], Set[str]]:
    """(ausgeblendet, inaktiv nach Aktivitaet). Inaktiv = ohne Bestand und ohne Umsatz in den letzten N Monaten (Altdaten).
    Ausgeblendet = je Konto "ausblenden", oder "nach Aktivitaet" und inaktiv; "immer anzeigen" nie. Ausgeblendete Konten
    bleiben in allen Summen enthalten."""
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
            if all(abs(h.get(k) or 0.0) < 0.005 for k in recent) and abs(acc.balance) < 0.005 \
                    and not any(t.booking_date >= cutoff for t in ledger.transactions(acc.uuid)):
                auto.add(acc.uuid)
    hidden = {u for u in auto if u not in force_show} | {a.uuid for a in leaves if a.uuid in force_hide}
    return hidden, auto


def activity_limits(ledger: Ledger, leaves: List[Account], hist: Dict[str, Dict[str, Optional[float]]], mkeys: List[str],
                    today: date) -> Dict[str, int]:
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
        out[acc.uuid] = max(0, min(since_h, since_t - 1, 9999))
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

    def add(self, section: str, gruppe: str, zeile: str, mk: str, amount: float, *,
            konto: Optional[str] = None, art: str = "kategorie", nw: bool = True):
        key = (section, zeile)
        self.vals[key][mk] += amount
        self.meta.setdefault(key, {"gruppe": gruppe, "konto": konto, "art": art, "nw": nw})


def transit_series(ledger: Ledger, leaves: List[Account], roles: Dict[str, str], months: List[Tuple[int, int]], quelle: Dict[str, str],
                   today: date) -> Tuple[Dict[str, float], List[dict]]:
    """Geld unterwegs am Monatsende: Umbuchung zwischen zwei Konten des Bereichs, deren Buchungen in verschiedene Monate fallen
    (am 31. abgebucht, am 1. gutgeschrieben). Abgebucht, aber noch nicht gutgeschrieben -> +Betrag; umgekehrt -> -Betrag.
    Nur eindeutige Paare: Gegen-IBAN zeigt auf das andere Konto, gleicher Betrag mit umgekehrtem Vorzeichen, hoechstens 5 Tage Abstand.
    Liefert (Betrag je Monatsende, erkannte Umbuchungen ueber ein Monatsende)."""
    mkeys = ["%04d-%02d" % ym for ym in months]
    out = {mk: 0.0 for mk in mkeys}
    if not months:
        return out, []
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
    for (y, m), mk in zip(months, mkeys):
        cut = min(month_end(y, m), today)
        val = sum(p[2] for p in pairs if p[0] <= cut < p[1]) - sum(p[2] for p in pairs if p[1] <= cut < p[0])
        out[mk] = round(val, 2)
    name = lambda u: ledger.accounts[u].name if u in ledger.accounts else u
    details = [{"ab": p[0].isoformat(), "an": p[1].isoformat(), "betrag": round(p[2], 2), "von": name(p[3]), "nach": name(p[4])}
               for p in sorted(pairs, key=lambda p: min(p[0], p[1]))]
    return out, details


def classify(ledger: Ledger, leaves: List[Account], roles: Dict[str, str], config: dict, months: List[Tuple[int, int]],
             verlauf: Dict[str, str]):
    kf = config.get("kapitalfluss", {}) or {}
    root_leaves = {a.uuid for a in leaves}
    own_ibans = ledger.own_ibans()
    transfer_cats = [c.lower() for c in (kf.get("umbuchungs_kategorien") or ["Umbuchung"])]
    cost_words = [w.lower() for w in (kf.get("kosten_texte") or COST_WORDS)]
    invest_cats = [c.lower() for c in (kf.get("investitions_kategorien") or ["invest", "wertpapier", "depot", "immobilienkauf", "beteiligung"])]
    finance_cats = [c.lower() for c in (kf.get("finanzierungs_kategorien") or ["finanzierung", "tilgung", "kredit"])]
    cost_cats = [c.lower() for c in (kf.get("finanzierungskosten_kategorien") or ["zinsen", "zinsaufwand", "finanzierungskosten"])]
    income_cats = [c.lower() for c in (kf.get("einnahmen_kategorien") or [])]
    kat_sektion: Dict[str, str] = {k.replace("\\", " / ").lower(): v for k, v in (kf.get("kategorie_zuordnung") or {}).items()
                                   if not k.startswith("_")}
    kat_zu_konto: Dict[str, str] = {}
    for cat_name, ref in (kf.get("kategorie_zu_konto") or {}).items():
        try:
            kat_zu_konto[cat_name.replace("\\", " / ").lower()] = ledger.resolve(ref).uuid
        except KeyError:
            pass
    beteiligungs_gruppen: Dict[str, str] = {}
    for ref in kf.get("beteiligungs_gruppen") or []:
        try:
            g = ledger.resolve(ref)
            for a in (ledger.descendants(g.uuid) if g.group else [g]):
                beteiligungs_gruppen[a.uuid] = g.name
        except KeyError:
            pass
    first = date(months[0][0], months[0][1], 1)
    last = month_end(months[-1][0], months[-1][1])

    # Depots mit Verlauf aus Kontostaenden liefern keine Zahlungsfluesse: ihre Wertaenderung ist Bewertung.
    # Andere Konten mit Kontostaenden behalten ihre Buchungen; Abweichungen zu den Kontostaenden werden als Korrektur ausgewiesen.
    flows = {u for u in root_leaves if u in ledger.accounts and not _valuation_account(ledger.accounts[u], verlauf.get(u, ""))}
    in_root = [t for t in ledger.txs if t.account_uuid in flows and t.booked and first <= t.booking_date <= last]
    # Nummern und Markierungen (#mm-tx-NNN) einmal je Stand indizieren (fuer alle Bereiche); Partner nur im Zeitraum
    idx = ledger.__dict__.get("_tx_index")
    if idx is None or idx[0] != len(ledger.txs):
        tags: Dict[str, List[Tx]] = defaultdict(list)
        for o in ledger.txs:
            if o.booked and "#mm-tx-" in o.purpose:
                for tag in TAG_RE.findall(o.purpose):
                    if tag.startswith("#mm-tx-"):
                        tags[tag].append(o)
        idx = ledger._tx_index = (len(ledger.txs), {t.id: t for t in ledger.txs if t.booked}, tags)
    by_id_all, tag_all = idx[1], idx[2]

    def by_id_get(i: int) -> Optional[Tx]:
        o = by_id_all.get(i)
        return o if o is not None and first <= o.booking_date <= last else None
    transfer_set = set(transfer_cats)

    partner: Dict[int, Optional[str]] = {}
    is_transfer: Dict[int, bool] = {}
    for t in in_root:
        p = None
        if t.counter_iban and t.counter_iban in own_ibans and own_ibans[t.counter_iban] != t.account_uuid:
            p = own_ibans[t.counter_iban]
        if p is None and "#mm-" in t.purpose + t.comment:
            for tag in TAG_RE.findall(t.purpose + " " + t.comment):
                if tag.startswith("#mm-tx-"):
                    src = by_id_get(int(tag[7:]))
                    if src and src.account_uuid != t.account_uuid:
                        p = src.account_uuid
                    else:
                        for o in tag_all.get(tag, ()):
                            if not first <= o.booking_date <= last:
                                continue
                            if o.account_uuid != t.account_uuid:
                                p = o.account_uuid
                                break
        cat_low = t.category_path.lower()
        transfer = p is not None or cat_low in transfer_set or cat_low.rsplit("\\", 1)[-1] in transfer_set
        partner[t.id] = p
        is_transfer[t.id] = transfer
    if kf.get("umbuchung_paarung", True):
        manual_ok = kf.get("paarung_manuelle_konten", True)
        open_tx = [t for t in in_root if is_transfer[t.id] and partner[t.id] is None]
        manual_side = [t for t in in_root if manual_ok and not is_transfer[t.id]
                       and (roles.get(t.account_uuid) in ("verbindlichkeiten", "forderungen") or roles.get(t.account_uuid) in ASSET_ROLES)
                       and ledger.accounts[t.account_uuid].offline and not _is_cost(t, cost_words)]
        liquid_side = [t for t in in_root if roles.get(t.account_uuid) == "liquiditaet" and partner[t.id] is None]
        # Gegenstuecke nach Betrag (Cent, Vorzeichen gedreht) indizieren: statt n² nur die wenigen Kandidaten gleicher Hoehe pruefen
        cents = lambda x: int(round(x * 100))
        open_ids = {t.id for t in open_tx}
        open_by_amt: Dict[int, List[Tx]] = defaultdict(list)
        for o in open_tx:
            open_by_amt[cents(o.amount)].append(o)
        liquid_by_amt: Dict[int, List[Tx]] = defaultdict(list)
        for o in liquid_side:
            liquid_by_amt[cents(o.amount)].append(o)
        used: Set[int] = set()
        for t in open_tx + manual_side:
            if t.id in used:
                continue
            pool = (open_by_amt if t.id in open_ids else liquid_by_amt).get(-cents(t.amount), ())
            for o in pool:
                if o.id in used or o.id == t.id or o.account_uuid == t.account_uuid:
                    continue
                if abs((o.booking_date - t.booking_date).days) <= 3:
                    partner[t.id], partner[o.id] = o.account_uuid, t.account_uuid
                    is_transfer[t.id] = is_transfer[o.id] = True
                    used.update({t.id, o.id})
                    break

    R = Rows()
    warnings: List[str] = []
    unclear = 0
    inbound: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    def cat_class(cat: str, top: str) -> tuple:
        """Einordnung einer Kategorie (Bankkonten): (Abschnitt, ...) -- Finanzierung (art, nw), Investitionen (Zielkonto),
        Einnahmen, Ausgaben, Ignorieren oder __operativ__ (nach Vorzeichen der Summe)."""
        tl = top.lower()
        zu = kat_sektion.get(cat.lower()) or kat_sektion.get(tl)
        if zu:
            sec, _, art = zu.partition("/")
            if sec == "Finanzierung":
                return ("Finanzierung", "zins" if art.lower().startswith("zins") else "tilgung", art.lower().startswith("zins"))
            if sec == "Investitionen":
                return ("Investitionen", kat_zu_konto.get(cat.lower()) or kat_zu_konto.get(tl))
            if sec in ("Einnahmen", "Ausgaben", "Ignorieren"):
                return (sec,)
            return ("__operativ__",)
        if any(k in tl for k in cost_cats):
            return ("Finanzierung", "zins", True)
        if any(k in tl for k in finance_cats):
            return ("Finanzierung", "tilgung", False)
        if any(k in tl for k in invest_cats) or cat.lower() in kat_zu_konto or tl in kat_zu_konto:
            return ("Investitionen", kat_zu_konto.get(cat.lower()) or kat_zu_konto.get(tl))
        if income_cats and any(k in tl for k in income_cats):
            return ("Einnahmen",)
        return ("__operativ__",)
    cat_memo: Dict[str, tuple] = {}
    zusammen: Dict[str, str] = kf.get("_zusammen") or {}
    fold_memo: Dict[str, str] = {}

    for t in in_root:
        acc = ledger.accounts[t.account_uuid]
        role = roles.get(acc.uuid, "sonstiges")
        mk = month_key(t.booking_date)
        p = partner[t.id]
        p_role = roles.get(p) if p in roles else None
        cat = t.category_path.replace("\\", " / ") or "(ohne Kategorie)"
        if zusammen:                                     # Einrichtung: Unterkategorien zur Oberkategorie zusammenfassen
            f = fold_memo.get(cat)
            if f is None:
                f = fold_memo[cat] = fold_category(zusammen, cat)
            cat = f
        top = cat.split(" / ")[0]
        if role == "ignorieren":
            continue
        if role == "liquiditaet":
            if is_transfer[t.id]:
                if p is not None and p in root_leaves:
                    if p_role in ("liquiditaet", "ignorieren"):
                        continue
                    pacc = ledger.accounts[p]
                    if p_role in ASSET_ROLES:
                        R.add("Investitionen", pacc.name, pacc.name, mk, t.amount, konto=p, art="konto", nw=False)
                        inbound[p][mk] += -t.amount
                    elif p_role == "forderungen":
                        R.add("Investitionen", pacc.name, pacc.name + " / Rückzahlung", mk, t.amount, konto=p, art="rueckzahlung", nw=False)
                    elif p_role == "verbindlichkeiten":
                        R.add("Finanzierung", pacc.name, pacc.name + " / Tilgung", mk, t.amount, konto=p, art="tilgung", nw=False)
                    else:
                        R.add("Unklar", "Umbuchung", "Umbuchung nach " + pacc.name, mk, t.amount, art="unklar"); unclear += 1
                elif p is not None and p in beteiligungs_gruppen:
                    g = beteiligungs_gruppen[p]
                    R.add("Investitionen", "Einlagen/Entnahmen", "Einlage/Entnahme " + g, mk, t.amount, art="extern", nw=False)
                elif p is not None and roles.get(p) == "eigenkapital":
                    R.add("Finanzierung", "Gesellschafter", "Einlagen/Entnahmen Gesellschafter", mk, t.amount, art="extern", nw=True)
                elif p is not None:
                    R.add("Unklar", "Umbuchung", "Umbuchung nach " + ledger.accounts[p].path, mk, t.amount, art="unklar"); unclear += 1
                else:
                    R.add("Unklar", "Umbuchung", "Umbuchung ohne erkannten Partner", mk, t.amount, art="unklar"); unclear += 1
                continue
            # Abschnitt je Kategorie nur einmal bestimmen (gleiche Kategorie -> gleiche Einordnung)
            c = cat_memo.get(cat)
            if c is None:
                c = cat_memo[cat] = cat_class(cat, top)
            kind = c[0]
            if kind == "Finanzierung":
                R.add("Finanzierung", top, cat, mk, t.amount, art=c[1], nw=c[2])
            elif kind == "Investitionen":
                R.add("Investitionen", top, cat, mk, t.amount, konto=c[1], art="kategorie", nw=False)
                if c[1]:
                    inbound[c[1]][mk] += -t.amount
            elif kind != "Ignorieren":
                R.add(kind, top, cat, mk, t.amount)
        elif role == "verbindlichkeiten":
            if is_transfer[t.id]:
                continue
            if _is_cost(t, cost_words):
                R.add("Finanzierung", acc.name, acc.name + " / Zinsen", mk, t.amount, konto=acc.uuid, art="zins", nw=True)
                R.add("Finanzierung", acc.name, acc.name + " / Tilgung", mk, -t.amount, konto=acc.uuid, art="tilgung", nw=False)
            else:
                R.add("Bewertung", acc.name, acc.name, mk, t.amount, konto=acc.uuid, art="konto", nw=True)
        elif role == "forderungen":
            if is_transfer[t.id]:
                continue
            if _is_cost(t, cost_words):
                R.add("Investitionen", acc.name, acc.name + " / Zinsen", mk, t.amount, konto=acc.uuid, art="zins", nw=True)
                R.add("Investitionen", acc.name, acc.name + " / Rückzahlung", mk, -t.amount, konto=acc.uuid, art="rueckzahlung", nw=False)
            else:
                R.add("Bewertung", acc.name, acc.name, mk, t.amount, konto=acc.uuid, art="konto", nw=True)
        elif role in ASSET_ROLES:
            if is_transfer[t.id]:
                continue
            R.add("Bewertung", acc.name, acc.name, mk, t.amount, konto=acc.uuid, art="konto", nw=True)
        else:
            R.add("Unklar", "Konto ohne Position", acc.name + " (Position unbekannt)", mk, t.amount, art="unklar"); unclear += 1

    for key in [k for k in R.vals if k[0] == "__operativ__"]:
        vals = R.vals.pop(key)
        meta = R.meta.pop(key)
        target = "Einnahmen" if sum(vals.values()) > 0 else "Ausgaben"
        for mk, v in vals.items():
            R.vals[(target, key[1])][mk] += v
        R.meta.setdefault((target, key[1]), meta)

    if unclear:
        warnings.append(tr("s_d_umbuchung_en_ohne_erkennbaren") % unclear)
    return R, inbound, warnings


# ---------------------------------------------------------------------------
# Bilanz je Bereich
# ---------------------------------------------------------------------------

def build_dataset(ledger: Ledger, config: dict, state: dict, today: date, bereich: dict, roles: Dict[str, str],
                  rule_warnings: Optional[List[str]] = None, progress: Optional[Callable[[float, str], None]] = None) -> dict:
    """bereich: {"id", "name", "art", "anteil", "leaves": [Account]}"""
    step = progress or (lambda f, t: None)
    order = ledger.order()                      # Konten in der Reihenfolge von MoneyMoney
    bcfg = config.get("bilanz", {}) or {}
    leaves: List[Account] = [a for a in bereich["leaves"] if roles.get(a.uuid) not in OFF_BALANCE]
    ausserhalb_accs = [a for a in bereich["leaves"] if roles.get(a.uuid) in ("eigenkapital", "eventual")]
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
    ckey = (getattr(ledger, "_kat_sig", None), tuple(a.uuid for a in leaves), json.dumps(roles, sort_keys=True),
            json.dumps(config.get("kapitalfluss") or {}, sort_keys=True, default=str), tuple(months[0]) if months else None,
            tuple(months[-1]) if months else None, len(months), tuple(sorted(quelle.items())))
    cache = ledger.__dict__.setdefault("_classify_cache", {})
    if ckey in cache:
        R, inbound, warn_c = copy.deepcopy(cache[ckey])        # Bereich unveraendert (z. B. Verlauf eines anderen Bereichs geaendert)
    else:
        R, inbound, warn_c = classify(ledger, leaves, roles, config, months, quelle)
        if len(cache) > 24:
            cache.clear()
        cache[ckey] = copy.deepcopy((R, inbound, warn_c))
    step(0.85, tr("x_bilanz"))
    inactive, inactive_auto = inactive_accounts(ledger, leaves, hist, mkeys, config, today)
    limits = activity_limits(ledger, leaves, hist, mkeys, today)

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
                        R.add("Bewertung", acc.name, acc.name + " / Korrektur Kontostand", mk, val, konto=acc.uuid, art="korrektur", nw=True)

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
                wp = depot_holdings(a, row["werte"], mkeys, today, state, (getattr(ledger, "portfolios", None) or {}).get(a.uuid))
                if wp:
                    row["wertpapiere"] = wp
            bilanz_rows.append(row)
    # Geld unterwegs (Umbuchung ueber das Monatsende) zaehlt zur Liquiditaet; sonst knickt das Nettovermoegen am Monatsende ein
    transit, transit_details = transit_series(ledger, leaves, roles, months, quelle, today)
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
    for a in sorted(ausserhalb_accs, key=lambda x: (roles.get(x.uuid) or "", order.get(x.uuid, 10**9))):
        wh, _, _ = account_balance_series(ledger, a, months, verlauf_quelle(a, verlauf_cfg), snapshots, historie.get(a.uuid) or {}, today, config,
                                             historie_mm.get(a.uuid), (state.get("historie_mm_anfang") or {}).get(a.uuid))
        ausserhalb.append({"id": a.uuid, "name": a.name, "pfad": a.path, "rolle": roles.get(a.uuid), "werte": {mk: wh[mk] for mk in mkeys}})

    # Kapitalfluss-Sektionen
    sektionen = []
    for sec in SECTIONS:
        zeilen = []
        for (s, row), vals in R.vals.items():
            if s != sec:
                continue
            m = R.meta[(s, row)]
            zeilen.append({"zeile": row, "gruppe": m["gruppe"], "konto": m["konto"], "art": m["art"], "nw": m["nw"],
                           "werte": {mk: round(vals.get(mk, 0.0), 2) for mk in mkeys}})
        gsum = defaultdict(float)
        for z in zeilen:
            gsum[z["gruppe"]] += abs(sum(z["werte"].values()))
        zeilen.sort(key=lambda z: (-gsum[z["gruppe"]], z["gruppe"], z["zeile"]))
        sektionen.append({"name": sec, "zeilen": zeilen})

    ueberleitung = {}
    for i, mk in enumerate(mkeys):
        if i == 0:
            continue
        explained = sum(z["werte"][mk] for sek in sektionen for z in sek["zeilen"] if z["nw"])
        delta = round(nw[mk] - nw[mkeys[i - 1]], 2)
        ueberleitung[mk] = {"delta_nw": delta, "erklaert": round(explained, 2), "unerklaert": round(delta - explained, 2)}

    loans_cfg = {}
    for l in config.get("darlehen", []) or []:
        try:
            a = ledger.resolve(l["darlehenskonto"])
            z = l.get("zins") or {}
            loans_cfg[a.uuid] = {"name": a.name, "modell": z.get("modell", "jahresbasis"), "satz": z.get("satz") or [], "art": l.get("art", "verbindlichkeit")}
        except KeyError:
            pass

    warnings = list(rule_warnings or []) + warn_h + warn_c
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
    rows_cfg: Dict[str, dict] = plan.get("zeilen", {}) or {}
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
    immo_extra: List[dict] = []                                   # zusaetzliche Zeilen (Ausschuettung)
    for im in immo or []:
        reihen = im.get("reihen") or {}
        cat = norm_cat(im.get("kategorie") or "").lower()
        taken_e = taken_a = False
        for sek in sektionen:
            for z in sek["zeilen"]:
                zl = norm_cat(z["zeile"]).lower()
                if cat and (zl == cat or zl.startswith(cat + " / ")):
                    if sek["name"] == "Einnahmen":
                        immo_rows[(sek["name"], z["zeile"])] = reihen.get("miete", {}) if not taken_e else {}
                        taken_e = True
                    elif sek["name"] == "Ausgaben":
                        immo_rows[(sek["name"], z["zeile"])] = ({mk: reihen.get("kosten", {}).get(mk, 0.0) + reihen.get("ruecklage", {}).get(mk, 0.0)
                                                                 for mk in future} if not taken_a else {})
                        taken_a = True
        if cat and not taken_e:
            immo_extra.append({"sektion": "Einnahmen", "gruppe": im.get("name", "Immobilie"), "zeile": "%s / Miete (Kalkulation)" % im.get("name", "Immobilie"),
                               "art": "immobilie", "nw": True, "werte": reihen.get("miete", {})})
        if cat and not taken_a:
            immo_extra.append({"sektion": "Ausgaben", "gruppe": im.get("name", "Immobilie"), "zeile": "%s / Kosten (Kalkulation)" % im.get("name", "Immobilie"),
                               "art": "immobilie", "nw": True, "werte": {mk: reihen.get("kosten", {}).get(mk, 0.0) + reihen.get("ruecklage", {}).get(mk, 0.0) for mk in future}})
        for lname, ref in (im.get("darlehen_konten") or {}).items():
            u = resolve_ref(ref)
            if u and lname in (reihen.get("darlehen") or {}):
                immo_loans[u] = reihen["darlehen"][lname]
        ou = resolve_ref(im.get("objekt_konto"))
        if ou and reihen.get("wert"):
            immo_wert[ou] = reihen["wert"]
        if reihen.get("ausschuettung") and any(abs(v) > 0.005 for v in reihen["ausschuettung"].values()):
            immo_extra.append({"sektion": "Investitionen", "gruppe": "Einlagen/Entnahmen", "zeile": "Entnahmen Gesellschafter (%s)" % im.get("name", "Immobilie"),
                               "art": "ereignis", "nw": False, "werte": reihen["ausschuettung"]})
    for ex in immo_extra:
        sek = sec_by_name[ex["sektion"]]
        sek["zeilen"].append({"zeile": ex["zeile"], "gruppe": ex["gruppe"], "konto": None, "art": ex["art"], "nw": ex["nw"],
                              "werte": {mk: 0.0 for mk in ist}, "synthetisch": True})
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
            elif sek["name"] in ("Bewertung", "Unklar"):
                method = "keine"
            elif sek["name"] == "Investitionen" and z.get("art") in ("extern", "konto", "rueckzahlung", "zins"):
                method = "keine" if z.get("art") in ("extern", "konto") else default_method
            else:
                method = default_method
            growth = float(cfg.get("steigerung_prozent_pa", growth_default.get(sek["name"], 0.0)))
            hist_vals = [z["werte"][mk] for mk in full_months]
            overrides = cfg.get("werte", {}) or {}
            budget = budgets.get(z["zeile"])
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
    for mk in future:
        liq_prev = round(liq_prev + sums[mk]["Cashflow"], 2)
        liq_plan[mk] = liq_prev
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
