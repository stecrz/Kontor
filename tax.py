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

from model import Ledger, Tx
from report import ASSET_ROLES, COST_WORDS, account_roles, _is_cost
from rules import TAG_RE

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


def _entity_type(name: str) -> str:
    low = name.lower()
    if "gbr" in low:
        return "gbr"
    if "gmbh" in low or "ag" == low[-2:]:
        return "gmbh"
    return "privat"


def _position_for(path: str, mapping: Dict[str, str]) -> str:
    low = path.lower()
    for k, v in mapping.items():
        if k.startswith("_"):
            continue
        kl = k.replace("\\", " / ").lower()
        if low == kl or low.startswith(kl + " / ") or low.split(" / ")[0] == kl:
            return v
    for hint, pos in POSITION_HINTS:
        if hint in low:
            return pos
    return "ohne Zuordnung"


def build_tax(ledger: Ledger, config: dict, today: date, bereiche: Optional[List[dict]] = None, roles: Optional[Dict[str, str]] = None,
              immo_afa: Optional[Dict[str, Dict[str, float]]] = None) -> dict:
    """immo_afa: Objektname -> {Jahr: AfA} aus den Immobilienkalkulationen (gilt, wenn steuer.afa nichts vorgibt)."""
    if bereiche is None:
        from core import bereiche_for
        bereiche = bereiche_for(ledger, config)
    immo_afa = immo_afa or {}
    st = config.get("steuer", {}) or {}
    kf = config.get("kapitalfluss", {}) or {}
    verm = (st.get("vermietung_kategorie") or "Vermietung").lower()
    transfer_cats = [c.lower() for c in (kf.get("umbuchungs_kategorien") or ["Umbuchung"])]
    cost_words = [w.lower() for w in (kf.get("kosten_texte") or COST_WORDS)]
    afa_cfg = st.get("afa") or {}
    pos_map = st.get("positionen") or {}

    # Objekt-Zuordnung der Darlehen (Referenz -> Objektname)
    loan_obj: Dict[str, str] = {}
    for ref, obj in (st.get("objekt_darlehen") or {}).items():
        if ref.startswith("_"):
            continue
        try:
            loan_obj[ledger.resolve(ref).uuid] = str(obj)
        except KeyError:
            pass
    # Entitaeten = Bereiche (Hauptbereich = privat, andere nach Art/Name)
    ents: List[dict] = []
    for b in bereiche or []:
        art = b.get("art") or _entity_type(b["name"])
        if art == "gesellschaft":
            art = "gbr" if "gbr" in b["name"].lower() else ("gmbh" if "gmbh" in b["name"].lower() else "gesellschaft")
        ents.append({"id": b["id"], "name": b["name"], "leaves": b["leaves"], "art": art,
                     "anteil": b.get("anteil") if b.get("anteil") not in (None, "", 0) else None})

    by_year: Dict[int, List[Tx]] = defaultdict(list)
    for t in ledger.txs:
        if t.booked:
            by_year[t.booking_date.year].append(t)
    years = sorted(set(by_year) | {today.year})
    out = {"jahre": years, "entitaeten": [], "vermietung_kategorie": st.get("vermietung_kategorie") or "Vermietung"}

    roles = roles if roles is not None else account_roles(ledger, config)
    for e in ents:
        leaves = [a for a in e["leaves"] if roles.get(a.uuid) not in ("ignorieren", "eigenkapital", "eventual")]
        leaf_ids = {a.uuid for a in leaves}
        own_ibans = {a.iban.replace(" ", "").upper() for a in leaves if a.iban}
        ent = {"name": e["name"], "uuid": e["id"], "art": e["art"], "anteil": e["anteil"], "jahre": {}}
        for y in years:
            cats: Dict[str, Dict[str, float]] = defaultdict(lambda: {"betrag": 0.0, "anzahl": 0})
            no_cat = {"betrag": 0.0, "anzahl": 0}
            objekte: Dict[str, dict] = {}
            schuldzinsen: Dict[str, float] = defaultdict(float)
            for t in by_year.get(y, ()):
                if t.account_uuid not in leaf_ids:
                    continue
                acc = ledger.accounts[t.account_uuid]
                role = roles.get(acc.uuid)
                cat_low = t.category_path.lower()
                is_transfer = (t.counter_iban and t.counter_iban in own_ibans) or \
                              any(cat_low.split("\\")[-1] == c or cat_low == c for c in transfer_cats) or \
                              any(tag.startswith("#mm-tx-") for tag in TAG_RE.findall(t.purpose + " " + t.comment)) or \
                              any(tag.startswith(("#mm-wert-", "#mm-spiegel-")) for tag in TAG_RE.findall(t.purpose))
                if acc.portfolio:
                    continue
                if role in ("verbindlichkeiten", "forderungen"):
                    if _is_cost(t, cost_words):
                        schuldzinsen[acc.name] += t.amount
                    continue
                if role in ASSET_ROLES:
                    continue          # Wertbuchungen sind keine Einkuenfte
                if is_transfer:
                    continue
                path = t.category_path.replace("\\", " / ")
                if not path:
                    no_cat["betrag"] += t.amount; no_cat["anzahl"] += 1
                    continue
                cats[path]["betrag"] += t.amount; cats[path]["anzahl"] += 1
                parts = path.split(" / ")
                if parts[0].lower() == verm:
                    obj = parts[1] if len(parts) >= 3 else "(allgemein)"
                    art = parts[-1] if len(parts) >= 2 else "(ohne Art)"
                    o = objekte.setdefault(obj, {"arten": defaultdict(float), "schuldzinsen": {}, "afa": 0.0})
                    o["arten"][art] += t.amount
            # Schuldzinsen den Objekten zuordnen
            obj_names = list(objekte.keys())
            for loan_name, amt in schuldzinsen.items():
                loan_uuid = next((a.uuid for a in leaves if a.name == loan_name), None)
                target = loan_obj.get(loan_uuid)
                if target is None and len(obj_names) == 1:
                    target = obj_names[0]
                if target is None:
                    target = "(Darlehen ohne Objekt)"
                o = objekte.setdefault(target, {"arten": defaultdict(float), "schuldzinsen": {}, "afa": 0.0})
                o["schuldzinsen"][loan_name] = round(amt, 2)
            # AfA (manuell) und Ergebnis je Objekt
            obj_out = {}
            for name, o in objekte.items():
                afa_val = 0.0
                afa_quelle = ""
                a = afa_cfg.get(name)
                if isinstance(a, dict) and a.get(str(y)) not in (None, ""):
                    afa_val = float(a.get(str(y)) or 0.0); afa_quelle = "manuell"
                elif a is not None and not isinstance(a, dict):
                    try:
                        afa_val = float(a); afa_quelle = "manuell"
                    except (TypeError, ValueError):
                        afa_val = 0.0
                if not afa_quelle and name in immo_afa and str(y) in immo_afa[name]:
                    afa_val = abs(float(immo_afa[name][str(y)])); afa_quelle = "kalkulation"
                einnahmen = round(sum(v for v in o["arten"].values() if v > 0), 2)
                werbung = round(sum(v for v in o["arten"].values() if v < 0), 2)
                zinsen = round(sum(o["schuldzinsen"].values()), 2)
                ergebnis = round(einnahmen + werbung + zinsen - afa_val, 2)
                obj_out[name] = {"arten": {k: round(v, 2) for k, v in sorted(o["arten"].items())},
                                 "schuldzinsen": o["schuldzinsen"], "afa": afa_val, "afa_quelle": afa_quelle, "einnahmen": einnahmen,
                                 "werbungskosten": werbung, "zinsen": zinsen, "ergebnis": ergebnis,
                                 "anteil_ergebnis": round(ergebnis * e["anteil"], 2) if e["anteil"] else None}
            # Positionen (privat) bzw. Kategorien
            positionen: Dict[str, dict] = defaultdict(lambda: {"betrag": 0.0, "kategorien": []})
            for path, v in cats.items():
                if path.split(" / ")[0].lower() == verm:
                    pos = "Anlage V (Vermietung)"
                else:
                    pos = _position_for(path, pos_map) if e["art"] == "privat" else path.split(" / ")[0]
                positionen[pos]["betrag"] += v["betrag"]
                positionen[pos]["kategorien"].append({"pfad": path, "betrag": round(v["betrag"], 2), "anzahl": v["anzahl"]})
            for pos in positionen.values():
                pos["betrag"] = round(pos["betrag"], 2)
                pos["kategorien"].sort(key=lambda c: -abs(c["betrag"]))
            ent["jahre"][str(y)] = {
                "kategorien": sorted([{"pfad": k, "betrag": round(v["betrag"], 2), "anzahl": v["anzahl"]} for k, v in cats.items()],
                                     key=lambda c: -abs(c["betrag"])),
                "ohne_kategorie": {"betrag": round(no_cat["betrag"], 2), "anzahl": no_cat["anzahl"]},
                "objekte": obj_out,
                "schuldzinsen": {k: round(v, 2) for k, v in schuldzinsen.items()},
                "positionen": dict(sorted(positionen.items())),
                "summe_einnahmen": round(sum(v["betrag"] for v in cats.values() if v["betrag"] > 0), 2),
                "summe_ausgaben": round(sum(v["betrag"] for v in cats.values() if v["betrag"] < 0), 2),
            }
        out["entitaeten"].append(ent)
    return out
