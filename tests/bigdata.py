"""Synthetische Daten in realer Groessenordnung (100 Konten, ~190.000 Umsaetze, 25 Jahre) fuer Laufzeitmessungen.

Aufbau wie bei einer gewachsenen MoneyMoney-Installation: vier Kontengruppen oberster Ebene (Privat, zwei GbRs,
eine GmbH), darunter Untergruppen, viele Alt-Konten ohne Umsatz seit Jahren, drei Depots. Namen erfunden.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Dict, List, Tuple

import fixtures as F

CATS = ["Einnahmen\\Gehalt", "Einnahmen\\Sonstiges", "Wohnen\\Miete", "Wohnen\\Nebenkosten", "Haushalt\\Lebensmittel",
        "Haushalt\\Drogerie", "Freizeit\\Restaurant", "Freizeit\\Reisen", "Mobilität\\Auto", "Mobilität\\ÖPNV",
        "Versicherung\\Haftpflicht", "Versicherung\\Kfz", "Investments\\ETF", "Umbuchung", "Finanzierung\\Zinsen",
        "Vermietung\\Objekt A\\Mieteinnahmen", "Vermietung\\Objekt A\\Hausgeld", "Betrieb\\Wareneinkauf", "Betrieb\\Personal",
        "Betrieb\\Miete", "Betrieb\\Umsatz", "Steuern\\Umsatzsteuer", "Steuern\\Einkommensteuer", ""]
PAYEES = ["REWE", "EDEKA", "Amazon", "Stadtwerke", "Versicherung AG", "Arbeitgeber GmbH", "Mieter Müller", "Mieter Schmidt",
          "Finanzamt", "Telekom", "Bahn", "Tankstelle", "Apotheke", "Großhandel AG", "Lohnbüro", "Vermieter", "Bank", "Restaurant"]


def build(n_tx: int = 190_000, years: int = 25, seed: int = 7, today: date = date(2026, 11, 6)) -> Tuple[List[dict], List[dict], List[dict]]:
    """Liefert (accounts_raw, transactions_raw, categories_raw) im MoneyMoney-Exportformat."""
    rnd = random.Random(seed)
    accounts: List[dict] = [F.acc("root", "Alle Konten", 0, "Kontengruppe", True)]
    leaves: List[Tuple[str, float, date]] = []     # (key, Gewicht fuer Umsatzhaeufigkeit, letzter Umsatz)
    start = date(today.year - years, 1, 1)

    def group(key, name, indent):
        accounts.append(F.acc(key, name, indent, "Kontengruppe", True))

    def leaf(key, name, indent, typ="Girokonto", weight=1.0, last=None, portfolio=False, balance=None):
        bal = balance if balance is not None else rnd.uniform(-50000, 150000)
        accounts.append(F.acc(key, name, indent, typ, balance=round(bal, 2), iban=None if typ == "Offline-Konto" else "DE%020d" % rnd.randrange(10**19),
                              bank="" if typ == "Offline-Konto" else "70150000", portfolio=portfolio))
        leaves.append((key, weight, last or today))

    # Privat: 34 Konten, davon 9 alt
    group("priv", "Max Mustermann", 1)
    group("priv.liq", "Liquidität", 2)
    for i in range(6):
        leaf("priv.giro%d" % i, "Girokonto %d" % i, 3, weight=8.0 if i < 2 else 1.0, last=None if i < 3 else date(today.year - 6 + i, 5, 1))
    group("priv.anl", "Anlagen", 2)
    leaf("priv.depot", "Depot Broker", 3, "Portfolio", weight=0.5, portfolio=True, balance=180000)
    leaf("priv.depot2", "Depot Altbank", 3, "Portfolio", weight=0.2, portfolio=True, balance=0, last=date(2016, 3, 1))
    for i in range(5):
        leaf("priv.tg%d" % i, "Tagesgeld %d" % i, 3, "Tagesgeldkonto", weight=0.3, last=None if i < 2 else date(2015 + i, 1, 1))
    group("priv.bet", "Beteiligungen", 2)
    for i in range(4):
        leaf("priv.bet%d" % i, "Beteiligung %d" % i, 3, "Offline-Konto", weight=0.05)
    group("priv.sach", "Sachwerte", 2)
    for i in range(4):
        leaf("priv.sach%d" % i, "Sachwert %d" % i, 3, "Offline-Konto", weight=0.02)
    group("priv.verb", "Verbindlichkeiten", 2)
    for i in range(5):
        leaf("priv.darl%d" % i, "Darlehen %d" % i, 3, "Darlehenskonto", weight=0.3, last=None if i < 2 else date(2012 + i, 1, 1), balance=-rnd.uniform(10000, 400000))
    group("priv.kk", "Kreditkarten", 2)
    for i in range(5):
        leaf("priv.cc%d" % i, "Kreditkarte %d" % i, 3, "Kreditkarte", weight=2.0 if i < 2 else 0.5, last=None if i < 2 else date(2010 + i, 1, 1))
    # GmbH: 23 Konten
    group("gmbh", "Muster Biomarkt GmbH", 1)
    group("gmbh.liq", "Liquidität", 2)
    for i in range(10):
        leaf("gmbh.giro%d" % i, "Geschäftskonto %d" % i, 3, weight=12.0 if i < 4 else 2.0, last=None if i < 7 else date(2019 + i - 7, 6, 1))
    group("gmbh.verb", "Darlehen", 2)
    for i in range(8):
        leaf("gmbh.darl%d" % i, "Bankdarlehen %d" % i, 3, "Darlehenskonto", weight=0.4, balance=-rnd.uniform(50000, 900000))
    group("gmbh.sonst", "Sonstiges", 2)
    for i in range(5):
        leaf("gmbh.s%d" % i, "Sonstiges %d" % i, 3, "Offline-Konto", weight=0.1)
    # GbR A: 6 Konten, GbR B: 7 Konten (jung)
    group("pb", "Alpha Asset eGbR", 1)
    leaf("pb.kk", "Kontokorrent", 2, weight=0.5, balance=40000)
    leaf("pb.immo", "Immobilie Parkweg", 2, "Offline-Konto", weight=0.01, balance=1900000)
    leaf("pb.vd", "Verkäuferdarlehen", 2, "Offline-Konto", weight=0.05, balance=-1600000)
    for i in range(3):
        leaf("pb.k%d" % i, "Kapitalkonto %d" % i, 2, "Offline-Konto", weight=0.02, balance=-120000)
    group("shs", "Beta Verwaltung eGbR", 1)
    leaf("shs.kk", "Kontokorrent", 2, weight=0.5, balance=15000)
    leaf("shs.immo", "Immobilie Bahnhofstraße", 2, "Offline-Konto", weight=0.01, balance=3300000)
    for i in range(3):
        leaf("shs.d%d" % i, "Darlehen %d" % i, 2, "Darlehenskonto", weight=0.3, balance=-1000000)
    for i in range(2):
        leaf("shs.k%d" % i, "Kapitalkonto %d" % i, 2, "Offline-Konto", weight=0.02, balance=-74000)
    # Rest bis 100 Konten: alte Konten in einer Gruppe "Archiv"
    group("priv.archiv", "Archiv", 2)
    i = 0
    while len([a for a in accounts if not a["group"]]) < 100:
        leaf("priv.arch%d" % i, "Altkonto %d" % i, 3, weight=0.3, last=date(2004 + (i % 10), 2, 1))
        i += 1

    # Umsaetze: je Konto nach Gewicht, gleichmaessig ueber die Jahre bis "last"
    keys = [k for k, _, _ in leaves]
    weights = [w for _, w, _ in leaves]
    last_of = {k: l for k, _, l in leaves}
    txs: List[dict] = []
    for n in range(n_tx):
        key = rnd.choices(keys, weights)[0]
        last = last_of[key]
        span = (last - start).days
        d = start + timedelta(days=rnd.randrange(max(1, span)))
        if key.startswith("gmbh"):
            cat = rnd.choice(CATS[17:23] + ["Umbuchung", ""])
            amt = rnd.choice([-1, -1, -1, 1]) * round(rnd.uniform(5, 25000), 2)
        elif key in ("pb.kk", "shs.kk"):
            cat = rnd.choice(["Vermietung\\Objekt A\\Mieteinnahmen", "Vermietung\\Objekt A\\Hausgeld", "Finanzierung\\Zinsen", "Umbuchung"])
            amt = rnd.choice([-1, 1]) * round(rnd.uniform(100, 12000), 2)
        else:
            cat = rnd.choice(CATS[:15] + ["", ""])
            amt = rnd.choice([-1, -1, -1, 1]) * round(rnd.uniform(1, 3000), 2)
        txs.append(F.tx(key, d, amt, rnd.choice(PAYEES), "Verwendungszweck %d" % rnd.randrange(5000), cat,
                        counter_iban="DE%020d" % rnd.randrange(10**19) if rnd.random() < 0.7 else ""))
    cats = []
    seen = set()
    for c in CATS:
        if not c:
            continue
        parts = c.split("\\")
        for i in range(1, len(parts) + 1):
            p = "\\".join(parts[:i])
            if p not in seen:
                seen.add(p)
                cats.append({"name": parts[i - 1], "path": p, "group": i < len(parts)})
    return accounts, txs, cats


def config_for_big() -> Dict:
    return {
        "probelauf": True, "mitteilungen": False,
        "zeitplan": {"intervall_minuten": 30, "automatisch": False},
        "darlehen": [], "beteiligungen": [], "saldo_spiegel": [],
        "bereiche": [
            {"id": "b-priv", "name": "Max Mustermann", "art": "privat", "haupt": True, "anteil": None, "aktiv": True, "konten": [F.uid("priv") + " | Max Mustermann"]},
            {"id": "b-gmbh", "name": "Muster Biomarkt GmbH", "art": "firma", "haupt": False, "anteil": None, "aktiv": True, "konten": [F.uid("gmbh") + " | Muster Biomarkt GmbH"]},
            {"id": "b-pb", "name": "Alpha Asset eGbR", "art": "gesellschaft", "haupt": False, "anteil": 0.49, "aktiv": True, "konten": [F.uid("pb") + " | Alpha Asset eGbR"]},
            {"id": "b-shs", "name": "Beta Verwaltung eGbR", "art": "gesellschaft", "haupt": False, "anteil": 0.49, "aktiv": True, "konten": [F.uid("shs") + " | Beta Verwaltung eGbR"]},
        ],
        "bilanz": {"monate_zurueck": 0, "inaktiv_monate": 12},
        "kategorien": {"aktiv": True, "lernen": True, "mm_ueberschreiben": False},
        "updates": {"taeglich_pruefen": False},
        "oberflaeche": {"sperre_minuten": 15, "port": 0},
    }
