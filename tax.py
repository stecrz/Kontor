"""Steuer-Jahresauswertung je Entitaet (privat, je GbR, GmbH) aus den MoneyMoney-Daten.

Keine Steuerberatung, sondern die geordnete Zusammenstellung dessen, was in
MoneyMoney kategorisiert ist -- je Jahr und Entitaet:

* Kategoriesummen (ohne Umbuchungen), Betraege ohne Kategorie als Pruefposten
* Vermietung je Objekt: Kategorien nach dem Muster  <Vermietung> \\ <Objekt> \\ <Art>
  (z.B. "Vermietung\\Musterstrasse\\Mieteinnahmen"); Objekte entstehen allein aus
  den Kategorienamen -- beliebig viele je Entitaet, nichts ist fest verdrahtet
* Schuldzinsen je Darlehenskonto (Zins-/Gebuehrenbuchungen), Objekt-Zuordnung
  ueber steuer.objekt_darlehen oder automatisch bei genau einem Objekt
* AfA als manueller Wert je Objekt und Jahr (steuer.afa), nicht gebucht
* Privat: Zuordnung der Kategorien zu Steuerpositionen (Anlage N/KAP/V,
  Sonderausgaben, aussergewoehnliche Belastungen, §35a, Spenden, Steuern)
  ueber steuer.positionen, mit Namensheuristik als Standard
* Anteil des Gesellschafters (aus den Beteiligungsregeln) am GbR-Ergebnis
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional

from model import Ledger, Tx, norm_cat
from report import ASSET_ROLES, COST_WORDS, account_roles, foreign_currency, purchase_kind, deposit_category, _is_cost
from model import MARK, marks_in
from i18n import tr

POSITION_HINTS = [
    ("gehalt", "Anlage N (Arbeitslohn)"), ("lohn", "Anlage N (Arbeitslohn)"), ("tantieme", "Anlage N (Arbeitslohn)"),
    ("kapitalertr", "Anlage KAP"), ("dividend", "Anlage KAP"), ("zinsertr", "Anlage KAP"), ("zinseinnahm", "Anlage KAP"),
    ("ausschütt", "Anlage KAP / GbR-Anteil"), ("ausschuett", "Anlage KAP / GbR-Anteil"),
    ("krankenversicherung", "Sonderausgaben: Vorsorge (Basis)"), ("pflegeversicherung", "Sonderausgaben: Vorsorge (Basis)"),
    ("rentenversicherung", "Sonderausgaben: Altersvorsorge"), ("altersvorsorge", "Sonderausgaben: Altersvorsorge"),
    ("haftpflicht", "Sonderausgaben: weitere Vorsorge"), ("unfallversicherung", "Sonderausgaben: weitere Vorsorge"),
    ("berufsunf", "Sonderausgaben: weitere Vorsorge"), ("rechtsschutz", "nicht abziehbar (privat)"),
    ("spende", "Sonderausgaben: Spenden"), ("kirchensteuer", "Sonderausgaben: Kirchensteuer"),
    ("handwerker", "§ 35a: Handwerker"), ("haushaltsnah", "§ 35a: haushaltsnahe Dienstleistungen"),
    ("gesundheit", "Außergewöhnliche Belastungen (ggf.)"), ("arzt", "Außergewöhnliche Belastungen (ggf.)"),
    ("steuern", "Gezahlte Steuern / Vorauszahlungen"), ("finanzamt", "Gezahlte Steuern / Vorauszahlungen"),
    ("bildung", "Werbungskosten (ggf.)"), ("arbeitsmittel", "Werbungskosten (ggf.)"),
    ("invest", "Umschichtung (nicht relevant)"), ("depot", "Umschichtung (nicht relevant)"), ("wertpapier", "Umschichtung (nicht relevant)"),
    ("sparen", "Umschichtung (nicht relevant)"), ("tilgung", "Umschichtung (nicht relevant)"),
    ("wohnen", "nicht abziehbar (privat)"), ("miete", "nicht abziehbar (privat)"), ("lebensmittel", "nicht abziehbar (privat)"),
    ("gastro", "nicht abziehbar (privat)"), ("kleidung", "nicht abziehbar (privat)"), ("urlaub", "nicht abziehbar (privat)"),
    ("geschenk", "nicht abziehbar (privat)"), ("abos", "nicht abziehbar (privat)"), ("mobilit", "nicht abziehbar (privat)"),
    ("sonstiges", "nicht abziehbar (privat)"), ("anderes", "nicht abziehbar (privat)"), ("strom", "nicht abziehbar (privat)"),
    ("internet", "nicht abziehbar (privat)"), ("rundfunk", "nicht abziehbar (privat)"),
]

GENERIC = {"nicht abziehbar (privat)": "tax_nicht_abziehbar", "Umschichtung (nicht relevant)": "tax_umschichtung"}   # shown in the user's language


def _entity_type(name: str) -> str:
    low = name.lower()
    if "gbr" in low:
        return "gbr"
    if "gmbh" in low or "ag" == low[-2:]:
        return "gmbh"
    return "private"


def _position_for(path: str, mapping: Dict[str, str]) -> str:
    low = path.lower()
    for k, v in mapping.items():
        if k.startswith("_"):
            continue
        kl = norm_cat(k).lower()                         # "A\\B", "A / B" or "A › B" (as the page shows it)
        if low == kl or low.startswith(kl + " / ") or low.split(" / ")[0] == kl:
            return v
    for hint, pos in POSITION_HINTS:
        if hint in low:
            return tr(GENERIC[pos]) if pos in GENERIC else pos       # the tax forms' names stay German
    return tr("tax_ohne_zuordnung")


def build_tax(ledger: Ledger, config: dict, today: date, bereiche: Optional[List[dict]] = None, roles: Optional[Dict[str, str]] = None,
              immo_afa: Optional[Dict[str, Dict[str, float]]] = None) -> dict:
    """immo_afa: Objektname -> {Jahr: AfA} aus den Immobilienkalkulationen (gilt, wenn steuer.afa nichts vorgibt)."""
    if bereiche is None:
        from core import bereiche_for
        bereiche = bereiche_for(ledger, config)
    immo_afa = immo_afa or {}
    st = config.get("tax", {}) or {}
    kf = config.get("cashflow", {}) or {}
    verm = (st.get("rental_category") or "Vermietung").lower()
    from report import transfer_check
    transfer_cat = transfer_check(config)          # the same transfer categories as the cash flow (your positions first)
    cost_words = [w.lower() for w in (kf.get("costs_texts") or COST_WORDS)]
    afa_cfg = st.get("depreciation") or {}
    pos_map = st.get("positions") or {}

    # Objekt-Zuordnung der Darlehen (Referenz -> Objektname)
    loan_obj: Dict[str, str] = {}
    for ref, obj in (st.get("property_loans") or {}).items():
        if ref.startswith("_"):
            continue
        try:
            loan_obj[ledger.resolve(ref).uuid] = str(obj)
        except KeyError:
            pass
    # Entitaeten = Bereiche (Hauptbereich = privat, andere nach Art/Name)
    ents: List[dict] = []
    for b in bereiche or []:
        art = b.get("kind") or _entity_type(b["name"])
        if art == "company":
            art = "gbr" if "gbr" in b["name"].lower() else ("gmbh" if "gmbh" in b["name"].lower() else "company")
        ents.append({"id": b["id"], "name": b["name"], "leaves": b["leaves"], "kind": art,
                     "share": b.get("share") if b.get("share") not in (None, "", 0) else None})

    by_year: Dict[int, List[Tx]] = defaultdict(list)
    for t in ledger.txs:
        if t.booked:
            by_year[t.booking_date.year].append(t)
    years = sorted(set(by_year) | {today.year})
    out = {"years": years, "entities": [], "rental_category": st.get("rental_category") or "Vermietung"}

    roles = roles if roles is not None else account_roles(ledger, config)
    for e in ents:
        leaves = [a for a in e["leaves"] if roles.get(a.uuid) not in ("ignore", "contingent")]
        leaf_ids = {a.uuid for a in leaves}
        own_ibans = {a.iban.replace(" ", "").upper() for a in leaves if a.iban}
        ent = {"name": e["name"], "uuid": e["id"], "kind": e["kind"], "share": e["share"], "years": {}}
        # accounts in another currency: their amounts are not added to euros (Kontor does not convert) -- named, so the page says so
        fx = [a for a in leaves if foreign_currency(a) and not a.portfolio and roles.get(a.uuid) not in ASSET_ROLES]
        if fx:
            ent["not_converted"] = [{"account": a.name, "currency": (a.currency or "").upper()} for a in fx]
        fx_ids = {a.uuid for a in fx}
        for y in years:
            cats: Dict[str, Dict[str, float]] = defaultdict(lambda: {"amount": 0.0, "count": 0})
            no_cat = {"amount": 0.0, "count": 0}
            objekte: Dict[str, dict] = {}
            schuldzinsen: Dict[str, float] = defaultdict(float)
            for t in by_year.get(y, ()):
                if t.account_uuid not in leaf_ids or t.account_uuid in fx_ids:
                    continue
                acc = ledger.accounts[t.account_uuid]
                role = roles.get(acc.uuid)
                is_transfer = (t.counter_iban and t.counter_iban in own_ibans) or \
                              (bool(t.category_path) and transfer_cat(t.category_path)) or \
                              any(tag.startswith(MARK + "tx-") for tag in marks_in(t.purpose + " " + t.comment)) or \
                              any(tag.startswith((MARK + "wert-", MARK + "gk-")) for tag in marks_in(t.purpose))
                if acc.portfolio:
                    continue
                if role in ("liabilities", "receivables"):
                    if _is_cost(t, cost_words):
                        schuldzinsen[acc.name] += t.amount
                    continue
                if role in ASSET_ROLES:
                    continue          # Wertbuchungen sind keine Einkuenfte
                if is_transfer:
                    continue
                path = t.category_path.replace("\\", " / ")
                if not path:
                    no_cat["amount"] += t.amount; no_cat["count"] += 1
                    continue
                cats[path]["amount"] += t.amount; cats[path]["count"] += 1
                parts = path.split(" / ")
                # (price and purchase costs of a property are no income-related expenses: they are written off -- AfA)
                if parts[0].lower() == verm and not purchase_kind(path) and not deposit_category(path):
                    obj = parts[1] if len(parts) >= 3 else "(allgemein)"
                    art = parts[-1] if len(parts) >= 2 else tr("tax_ohne_art")
                    o = objekte.setdefault(obj, {"kinds": defaultdict(float), "debt_interest": {}, "depreciation": 0.0})
                    o["kinds"][art] += t.amount
            # Schuldzinsen den Objekten zuordnen
            obj_names = list(objekte.keys())
            for loan_name, amt in schuldzinsen.items():
                loan_uuid = next((a.uuid for a in leaves if a.name == loan_name), None)
                target = loan_obj.get(loan_uuid)
                if target is None and len(obj_names) == 1:
                    target = obj_names[0]
                if target is None:
                    target = tr("tax_darlehen_ohne_objekt")
                o = objekte.setdefault(target, {"kinds": defaultdict(float), "debt_interest": {}, "depreciation": 0.0})
                o["debt_interest"][loan_name] = round(amt, 2)
            # AfA (manuell) und Ergebnis je Objekt
            obj_out = {}
            for name, o in objekte.items():
                afa_val = 0.0
                afa_quelle = ""
                a = afa_cfg.get(name)
                if isinstance(a, dict) and a.get(str(y)) not in (None, ""):
                    afa_val = float(a.get(str(y)) or 0.0); afa_quelle = "manual"
                elif a is not None and not isinstance(a, dict):
                    try:
                        afa_val = float(a); afa_quelle = "manual"
                    except (TypeError, ValueError):
                        afa_val = 0.0
                if not afa_quelle and name in immo_afa and str(y) in immo_afa[name]:
                    afa_val = abs(float(immo_afa[name][str(y)])); afa_quelle = "calc"
                einnahmen = round(sum(v for v in o["kinds"].values() if v > 0), 2)
                werbung = round(sum(v for v in o["kinds"].values() if v < 0), 2)
                zinsen = round(sum(o["debt_interest"].values()), 2)
                ergebnis = round(einnahmen + werbung + zinsen - afa_val, 2)
                obj_out[name] = {"kinds": {k: round(v, 2) for k, v in sorted(o["kinds"].items())},
                                 "debt_interest": o["debt_interest"], "depreciation": afa_val, "depreciation_source": afa_quelle, "income_sum": einnahmen,
                                 "deductible_costs": werbung, "loan_interest": zinsen, "result": ergebnis,
                                 "share_result": round(ergebnis * e["share"], 2) if e["share"] else None}
            # Positionen (privat) bzw. Kategorien
            positionen: Dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "categories": []})
            for path, v in cats.items():
                if path.split(" / ")[0].lower() == verm:
                    pos = "Anlage V (Vermietung)"
                else:
                    pos = _position_for(path, pos_map) if e["kind"] == "private" else path.split(" / ")[0]
                positionen[pos]["amount"] += v["amount"]
                positionen[pos]["categories"].append({"path": path, "amount": round(v["amount"], 2), "count": v["count"]})
            for pos in positionen.values():
                pos["amount"] = round(pos["amount"], 2)
                pos["categories"].sort(key=lambda c: -abs(c["amount"]))
            ent["years"][str(y)] = {
                "categories": sorted([{"path": k, "amount": round(v["amount"], 2), "count": v["count"]} for k, v in cats.items()],
                                     key=lambda c: -abs(c["amount"])),
                "uncategorized_flag": {"amount": round(no_cat["amount"], 2), "count": no_cat["count"]},
                "properties_list": obj_out,
                "debt_interest": {k: round(v, 2) for k, v in schuldzinsen.items()},
                "positions": dict(sorted(positionen.items())),
                "sum_income": round(sum(v["amount"] for v in cats.values() if v["amount"] > 0), 2),
                "sum_expenses": round(sum(v["amount"] for v in cats.values() if v["amount"] < 0), 2),
            }
        out["entities"].append(ent)
    return out
