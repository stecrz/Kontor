"""Worlds of special cases for the pages and the assistant -- not only for the money logic (tests/test_data_worlds.py).

Each world is a MoneyMoney of its own in memory (accounts in their order, categories, transactions, portfolios; what Kontor
writes stays in it), with Kontor's settings for it and a day that is "today" there. What a world holds is told by its kinds:

  long   long names everywhere: areas, accounts, categories five deep, payees, purposes of several hundred characters,
         securities -- and one word of over fifty letters without a place to break it
  large  large amounts: a company with about 100 million turnover a year, a property of 250 million, a loan of 180 million,
         single bookings of 99,999,999.99 -- and single cents
  empty  empty areas: a company whose accounts never had a booking, an area whose group holds no account at all, an account
         with a balance but no booking ever
  full   very full: six companies, an area with forty accounts and thousands of bookings, a category tree of over a hundred,
         a portfolio of many securities
  fx     other currencies: an account in US dollars, one in Swiss francs, a credit card in pounds, a portfolio in dollars,
         money moved between euro and dollar
  edge   month and year ends: today is a 31 Dec, 1 Jan, 29 Feb, the 1st or the last of a month; bookings on 31 Dec, 1 Jan and
         29 Feb, a transfer over the year end, salary on the month's last day, an account opened today, a company founded
         this month
  bare   a new user: one account and a few bookings of this month ("nothing": not even those)

FIXED names the worlds every run builds; World(seed=...) draws one at random (its kinds, today, how many companies, months
and bookings) -- the night builds new ones until its time is up (nightly.yml); a failure names its world ("seed …",
KONTOR_FUZZ_SEED=<number> builds it again). All names and amounts are made up; the IBANs are made at run time and are no
one's account.
"""
from __future__ import annotations

import copy
import random
import threading
import uuid as _uuid
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

KINDS = ("long", "large", "empty", "full", "fx", "edge")
# the worlds of every run: name -> (kinds, today)
FIXED = {"lang": (("long",), date(2026, 11, 4)),
         "gross": (("large",), date(2026, 11, 4)),
         "leer": (("empty",), date(2026, 11, 4)),
         "voll": (("full",), date(2026, 11, 4)),
         "waehrung": (("fx",), date(2026, 11, 4)),
         "jahreswechsel": (("edge",), date(2027, 1, 1)),
         "silvester": (("edge", "long"), date(2026, 12, 31)),
         "schaltjahr": (KINDS, date(2028, 2, 29)),
         "neu": (("bare",), date(2026, 11, 4)),
         "nichts": (("bare", "nothing"), date(2027, 1, 1))}
EDGE_DAYS = [date(2026, 12, 31), date(2027, 1, 1), date(2028, 2, 29), date(2027, 3, 1), date(2027, 1, 31), date(2026, 6, 30),
             date(2027, 2, 28), date(2026, 11, 30), date(2028, 1, 1)]
LONG_WORD = "Grundstücksverwaltungsgesellschaftsbeteiligungsverrechnungskonto"          # 64 letters, nowhere to break

CATEGORIES = [("Unkategorisiert", 0, False, {"default": True}), ("Umbuchung", 0, False, {}),
              ("Einnahmen", 0, True, {}), ("Gehalt", 1, False, {}), ("Kapitalerträge", 1, False, {}), ("Dividenden", 1, False, {}),
              ("Wohnen", 0, True, {}), ("Miete", 1, False, {"budget": {"amount": 1500.0, "period": "monthly"}}), ("Nebenkosten", 1, False, {}),
              ("Finanzierung", 0, True, {}), ("Zinsen", 1, False, {}),
              ("Lebenshaltung", 0, True, {}), ("Lebensmittel", 1, False, {"budget": {"amount": 650.0, "period": "monthly"}}), ("Freizeit", 1, False, {}), ("Reisen", 1, False, {}),
              ("Versicherungen", 0, True, {}), ("Haftpflicht", 1, False, {}),
              ("Investments", 0, True, {}), ("ETF", 1, False, {}),
              ("Vermietung", 0, True, {}), ("Objekt", 1, True, {}), ("Mieteinnahmen", 2, False, {}), ("Bewirtschaftung", 2, False, {}),
              ("Betrieb", 0, True, {}), ("Umsatzerlöse", 1, False, {}), ("Wareneinkauf", 1, False, {}), ("Büromiete", 1, False, {}),
              ("Geschäftsführergehalt", 1, False, {}), ("Erlöse Schweiz", 1, False, {}),
              ("Steuern", 0, True, {}), ("Umsatzsteuer", 1, False, {}), ("Körperschaftsteuer", 1, False, {})]
# five deep, with long names (kind "long"): the path of the last one is what bookings of "Lange Kategorie" carry
LONG_CATEGORIES = [("Sonstige betriebliche Aufwendungen und Erträge aus gewöhnlicher Geschäftstätigkeit", 0, True, {}),
                   ("Aufwendungen für Grundstücke, Gebäude und grundstücksgleiche Rechte einschließlich Nebenkosten", 1, True, {}),
                   ("Instandhaltung und Instandsetzung der Wohn- und Geschäftsräume", 2, True, {}),
                   ("Laufende Wartung technischer Anlagen (Heizung, Aufzug, Lüftung, Brandschutz)", 3, True, {}),
                   (LONG_WORD, 4, False, {})]
LONG_CATEGORY = "\\".join(c[0] for c in LONG_CATEGORIES)
# the categories only bookings in another currency carry: never in a sum in euros (tax, categories, searches)
FX_CATEGORIES = ("Einnahmen\\Dividenden", "Lebenshaltung\\Reisen", "Betrieb\\Erlöse Schweiz")

COMPANIES = [("Nordwind GmbH", "Nordwind Vermögensverwaltungs- und Beteiligungsgesellschaft mit beschränkter Haftung & Co. Kommanditgesellschaft"),
             ("Lindenhof GbR", "Grundstücksgemeinschaft Lindenhof Wohn- und Gewerbeimmobilien Gesellschaft bürgerlichen Rechts"),
             ("Sonnental KG", "Sonnental Handels- und Dienstleistungsgesellschaft für Erneuerbare Energien Kommanditgesellschaft"),
             ("Bergblick UG", "Bergblick Softwareentwicklung und Beratung Unternehmergesellschaft (haftungsbeschränkt)"),
             ("Seeufer GmbH & Co. KG", "Seeufer Hotel- und Gastronomiebetriebsgesellschaft mbH & Co. KG"),
             ("Talweg eGbR", "Talweg eingetragene Gesellschaft bürgerlichen Rechts zur Verwaltung eigenen Vermögens"),
             ("Feldmark AG", "Feldmark Agrar- und Forstwirtschaftliche Beteiligungen Aktiengesellschaft")]
PAYEES = {"employer": ("Arbeitgeber AG", "Arbeitgeber Aktiengesellschaft Zentrale Personalabrechnung und Entgeltbuchhaltung Standort Süd"),
          "market": ("Biomarkt", "Biomarkt Naturkost und Feinkost Filiale Hauptbahnhof Untergeschoss Einkaufspassage"),
          "landlord": ("Vermieter", "Hausverwaltung und Vermietungsgesellschaft für Wohnungseigentum Musterstadt mbH"),
          "insurer": ("Versicherung Nord", "Versicherung Nord Versicherungsverein auf Gegenseitigkeit Abteilung Haftpflicht"),
          "bank": ("Hausbank", "Hausbank Genossenschaftsbank eG Darlehensabteilung Baufinanzierung"),
          "customer": ("Kunde Süd KG", "Großkunde Süd Industrie- und Handelsgesellschaft mbH & Co. KG Rechnungseingang"),
          "supplier": ("Großhandel Meyer", "Großhandel Meyer Lebensmittel- und Getränkegroßhandel GmbH Niederlassung Nord"),
          "seller": ("Verkäufer", "Verkäufergemeinschaft Erbengemeinschaft Grundstück Lindenhof vertreten durch Testamentsvollstrecker"),
          "tenant": ("Mieter", "Mieter Gewerbeeinheit Erdgeschoss links Einzelhandel und Gastronomie"),
          "tax": ("Finanzamt", "Finanzamt Musterstadt Körperschaftsteuerstelle")}
CREDITOR = "DE98" + "ZZZ09999999999"          # the sample creditor id of the documentation (written in two parts: it is no IBAN)
SEPA = ("EREF+2026-%06d-RE-NR-%06d MREF+M-%08d CRED+" + CREDITOR + " SVWZ+Rechnung vom %s Kundennummer 0012345678 Vertrag "
        "Rahmenvertrag Lieferung und Leistung gemäß Angebot, Abschlag %d von 12, zahlbar ohne Abzug, bei Rückfragen bitte "
        "Referenz angeben. Dies ist ein besonders langer Verwendungszweck, der über mehrere Zeilen geht und auf keine Seite passt.")
SECURITIES = [("Welt-Aktien-ETF", "Weltindex Aktien Industrieländer und Schwellenländer UCITS ETF thesaurierend physisch replizierend Anteilsklasse A"),
              ("Anleihen-ETF", "Euro Staatsanleihen Laufzeit sieben bis zehn Jahre UCITS ETF ausschüttend"),
              ("Schwellenländer-ETF", "Schwellenländer Aktien kleine und mittlere Unternehmen UCITS ETF")]

_NS = _uuid.UUID("0c7e6c39-5a1f-4b8e-9f2d-3e6b1a4d7c58")


def uid(key: str) -> str:
    return str(_uuid.uuid5(_NS, "kontor-data-world/" + key))


def stamp(d: date) -> datetime:
    """As MoneyMoney exports a day: its local midnight, as a time in UTC without a zone (a 1 Jan is a 31 Dec in UTC)."""
    return datetime(d.year, d.month, d.day).astimezone(timezone.utc).replace(tzinfo=None)


def local_day(t: datetime) -> date:
    return t.replace(tzinfo=timezone.utc).astimezone().date()


def months_back(d: date, n: int) -> date:
    """The first day of the month n months before d's."""
    k = d.year * 12 + d.month - 1 - n
    return date(k // 12, k % 12 + 1, 1)


def month_end(d: date) -> date:
    return months_back(d, -1) - timedelta(1)


class World:
    """One world: from a name in FIXED, or at random from a seed."""

    def __init__(self, name: Optional[str] = None, seed: Optional[int] = None):
        if name is not None:
            kinds, today = FIXED[name]
            rnd = random.Random("data world " + name)
            self.label = name
        else:
            rnd = random.Random(seed)
            kinds = [k for k in KINDS if rnd.random() < 0.35] + (["bare"] if rnd.random() < 0.08 else [])
            if "bare" in kinds and rnd.random() < 0.3:
                kinds.append("nothing")
            today = rnd.choice(EDGE_DAYS) if "edge" in kinds else date(2025, 6, 1) + timedelta(rnd.randrange(1300))
            self.label = "seed %d" % seed
        self.rnd, self.kinds, self.today = rnd, set(kinds), today
        self.lock = threading.Lock()
        self.layout: List[tuple] = []           # (key, name, indent, type, group, iban, bank code, portfolio, currency)
        self.opening: Dict[str, float] = {}     # key -> balance before its first booking
        self.opened: Dict[str, date] = {}       # key -> its first day (where later than the world's)
        self.txs: List[dict] = []
        self.portfolios: Dict[str, List[dict]] = {}
        self.areas: List[tuple] = []            # (key, name, kind, share)
        self.companies: List[tuple] = []        # (area key, participation key)
        self.loans: List[dict] = []
        self.properties: List[dict] = []
        self.cats = list(CATEGORIES) + (LONG_CATEGORIES if "long" in self.kinds else [])
        self._id = 700000
        self._iban = 0
        self.ibans: Dict[str, str] = {}
        self.notes: List[str] = []              # what is special (for a failure's message)
        self.pending: List[tuple] = []          # transfers on their way today: (from, to, day out, amount)
        if "bare" in self.kinds:
            self.months = 0
        elif name is not None:
            self.months = 36 if "full" in self.kinds else 14
        else:
            self.months = rnd.choice([1, 3, 13, 14, 25, 48])
        self.start = months_back(today, self.months)
        if "edge" in self.kinds and name is not None:
            self.start = date(today.year - 1, 1, 1) if today.month > 1 or today.day > 1 else date(today.year - 2, 1, 1)
            self.months = (today.year - self.start.year) * 12 + today.month - self.start.month
        self._build()
        self.accounts = self._accounts()

    # -- names and amounts ---------------------------------------------------------------------------------------------------
    def nm(self, short: str, long: str) -> str:
        return long if "long" in self.kinds else short

    def payee(self, k: str) -> str:
        return self.nm(*PAYEES[k])

    def purpose(self, short: str, d: date, n: int = 1) -> str:
        if "long" not in self.kinds:
            return short
        return "%s – %s" % (short, SEPA % (n, d.toordinal() % 999999, n * 7919 % 10 ** 8, d.isoformat(), d.month))

    def amt(self, x: float, big: float = 1000.0) -> float:
        return round(x * big, 2) if "large" in self.kinds else round(x, 2)

    def new_iban(self, key: str) -> str:
        self._iban += 1
        self.ibans[key] = "DE%02d%018d" % (40 + self._iban % 50, 900000000000000000 + self._iban)
        return self.ibans[key]

    # -- accounts and bookings -----------------------------------------------------------------------------------------------
    def group(self, key: str, name: str, indent: int) -> str:
        self.layout.append((key, name, indent, "Kontengruppe", True, None, "", False, "EUR"))
        return key

    def account(self, key: str, name: str, typ: str, opening: float = 0.0, bank: bool = True, currency: str = "EUR",
                portfolio: bool = False, since: Optional[date] = None, indent: int = 2) -> str:
        iban = self.new_iban(key) if bank and not portfolio else None
        self.layout.append((key, name, indent, typ, False, iban, "10000000" if bank else "", portfolio, currency))
        self.opening[key] = round(opening, 2)
        if since:
            self.opened[key] = since
        return key

    def tx(self, key: str, d: date, amount: float, name: str = "", purpose: str = "", category: str = "", counter: str = "",
           currency: Optional[str] = None) -> None:
        if d > self.today or d < self.opened.get(key, self.start) or not amount:
            return
        self._id += 1
        cur = currency or next(x[8] for x in self.layout if x[0] == key)
        self.txs.append({"id": self._id, "accountUuid": uid(key), "bookingDate": stamp(d), "valueDate": stamp(d), "amount": round(amount, 2),
                         "currency": cur, "name": name, "purpose": purpose, "category": category.split("\\")[-1], "categoryPath": category,
                         "categoryUuid": "", "accountNumber": self.ibans.get(counter, ""), "bankCode": "", "booked": True,
                         "checkmark": False, "comment": "", "bookingText": ""})

    def move(self, src: str, dst: str, d: date, x: float, what: str, dst_day: Optional[date] = None, x_dst: Optional[float] = None) -> None:
        """Money from one bank account to another (both with their IBANs: Kontor pairs them)."""
        self.tx(src, d, -x, self.nm("Umbuchung", "Umbuchung zwischen eigenen Konten"), what, "Umbuchung", dst)
        if d <= self.today < (dst_day or d) and d >= self.opened.get(src, self.start):
            self.pending.append((src, dst, d, x))                       # on its way today: out, not yet in
        self.tx(dst, dst_day or d, x if x_dst is None else x_dst, self.nm("Umbuchung", "Umbuchung zwischen eigenen Konten"), what, "Umbuchung", src)

    def days(self, lo: date, hi: date):
        d = lo
        while d <= hi:
            yield d
            d += timedelta(1)

    def month_starts(self):
        d = self.start.replace(day=1)
        while d <= self.today:
            yield d
            d = months_back(d, -1)

    def on(self, m: date, n: int) -> date:
        """The n-th of month m (the 31st: its last day)."""
        return min(date(m.year, m.month, 1) + timedelta(n - 1), month_end(m))

    # -- the world -----------------------------------------------------------------------------------------------------------
    def _build(self) -> None:
        rnd, k = self.rnd, self.kinds
        self.group("root", "Alle Konten", 0)
        priv = self.group("priv", self.nm("Privat", "Privatvermögen Familie Mustermann-Beispielhausen einschließlich Treuhandvermögen der Kinder"), 1)
        self.areas.append((priv, self.layout[-1][1], "private", None))
        giro = self.account("priv.giro", self.nm("Hausbank Giro", "Hausbank Girokonto Gemeinschaftskonto Haushalt und laufende Ausgaben"), "Girokonto",
                            self.amt(4800.0, 25.0))
        if "bare" in k:
            if "nothing" not in k:
                first = self.today.replace(day=1)
                self.tx(giro, first, 2500.0, self.payee("employer"), "Gehalt", "Einnahmen\\Gehalt")
                self.tx(giro, max(first, self.today - timedelta(1)), -84.20, self.payee("market"), "Einkauf", "Lebenshaltung\\Lebensmittel")
                self.tx(giro, self.today, -19.99, "Onlinehandel", "Bestellung", "")
            self.notes.append("new user")
            return
        tg = self.account("priv.tg", self.nm("Tagesgeld", "Tagesgeldkonto Notgroschen und Rücklage für größere Anschaffungen"), "Sparkonto", self.amt(20000.0, 50.0))
        depot_ccy = "USD" if "fx" in k else "EUR"
        depot = self.account("priv.depot", self.nm("Depot", "Wertpapierdepot Altersvorsorge langfristig thesaurierend"), "Portfolio", 0.0,
                             currency=depot_ccy, portfolio=True)
        self.account("priv.immo", self.nm("Wohnung", "Eigentumswohnung Lindenallee 12, drittes Obergeschoss rechts, mit Tiefgaragenstellplatz"),
                            "Offline-Konto", self.amt(420000.0, 600.0), bank=False)
        loan = self.account("priv.darl", self.nm("Darlehen Wohnung", "Annuitätendarlehen Eigentumswohnung Lindenallee Zinsbindung zehn Jahre"),
                            "Darlehenskonto", -self.amt(250000.0, 720.0))
        n_comp = 0 if self.months < 1 else (6 if "full" in k else rnd.choice([1, 2, 2, 3]))
        names = rnd.sample(COMPANIES, n_comp)
        comps = []
        for i, (short, long) in enumerate(names):
            key = "c%d" % i
            name = self.nm(short, long)
            self.group(key, name, 1)
            share = rnd.choice([1.0, 0.5, 0.25, 1 / 3, 0.749, 0.005])
            self.areas.append((key, name, "company", share))
            since = None
            if "edge" in k and i == 1:                                  # founded this month: its first booking on the 1st
                since = self.today.replace(day=1)
                self.notes.append("%s founded this month" % short)
            self.account(key + ".kk", self.nm("Geschäftskonto", "Geschäftskonto Kontokorrent Hauptniederlassung Zahlungsverkehr Inland"),
                         "Girokonto", 0.0 if since else self.amt(50000.0, 1500.0), since=since)
            stake = self.account("priv.bet.%s" % key, self.nm("Beteiligung ", "Gesellschaftsanteil an der ") + short, "Offline-Konto", 0.0,
                                 bank=False, indent=2)
            comps.append((key, short, since))
            if i == 0:
                self.companies.append((key, stake))
        # the private bookings, month by month
        paid_by = comps[0][0] + ".kk" if comps and not comps[0][2] else None
        for n, m in enumerate(self.month_starts()):
            pay_day = month_end(m) if "edge" in k else self.on(m, 28)
            if paid_by:
                self.tx(paid_by, pay_day, -self.amt(6500.0, 40.0), self.nm("Geschäftsführer", "Geschäftsführergehalt laut Anstellungsvertrag"),
                        self.purpose("Gehalt %02d/%d" % (m.month, m.year), m, n), "Betrieb\\Geschäftsführergehalt", giro)
                self.tx(giro, pay_day, self.amt(6500.0, 40.0), self.nm(*names[0]),
                        self.purpose("Gehalt %02d/%d" % (m.month, m.year), m, n), "Einnahmen\\Gehalt", paid_by)
            else:
                self.tx(giro, pay_day, self.amt(6500.0, 40.0), self.payee("employer"), self.purpose("Gehalt", m, n), "Einnahmen\\Gehalt")
            self.tx(giro, self.on(m, 1), -self.amt(1500.0, 720.0), self.payee("bank"), self.purpose("Annuität", m, n), "Umbuchung", loan)
            self.tx(loan, self.on(m, 1), self.amt(1500.0, 720.0), self.payee("bank"), "Annuität", "Umbuchung", giro)
            self.tx(loan, self.on(m, 1), -self.amt(610.0, 720.0), self.payee("bank"), "Zinsen", "Finanzierung\\Zinsen")
            for day, x in ((6, 142.30), (13, 167.85), (20, 121.40), (27, 188.10)):
                self.tx(giro, self.on(m, day), -self.amt(x, 25.0), self.payee("market"), self.purpose("Einkauf", m, n), "Lebenshaltung\\Lebensmittel")
            self.tx(giro, self.on(m, 5), -self.amt(96.0, 25.0), self.payee("insurer"), self.purpose("Privathaftpflicht", m, n), "Versicherungen\\Haftpflicht")
            self.tx(giro, self.on(m, 8), -self.amt(180.0, 25.0), self.nm("Stadtwerke", "Stadtwerke Musterstadt Energie- und Wasserversorgung GmbH"),
                    self.purpose("Strom", m, n), "Wohnen\\Nebenkosten")
            self.tx(giro, self.on(m, 4), -self.amt(500.0, 100.0), self.nm("Broker", "Onlinebroker Wertpapierabrechnung Sparplanausführung"),
                    self.purpose("Sparplan", m, n), "Investments\\ETF")
            self.tx(giro, self.on(m, 15), -self.amt(48.90, 25.0), self.nm("Baumarkt", "Baumarkt und Gartencenter Heimwerkerbedarf Filiale Gewerbegebiet Nord"),
                    self.purpose("Werkzeug", m, n), "")                                           # without a category: to assign
            if "long" in k:
                self.tx(giro, self.on(m, 18), -self.amt(77.70, 25.0), self.payee("landlord"), self.purpose("Wartung Heizung", m, n), LONG_CATEGORY)
            if n % 3 == 0:
                self.move(giro, tg, self.on(m, 2), self.amt(500.0, 25.0), self.purpose("Sparen", m, n))
        if "large" in k:                                                 # single bookings of almost 100 million, and single cents
            d = max(self.start, self.today - timedelta(40))
            self.move(tg, giro, d, 99999999.99, "Umschichtung")
            self.move(giro, tg, d + timedelta(1), 99999999.99, "Umschichtung zurück")
            self.tx(giro, self.today, 0.01, "Bank", "Zinsgutschrift", "Einnahmen\\Kapitalerträge")
            self.tx(giro, self.today, -0.01, "Bank", "Rundung", "")
            self.notes.append("bookings of 99,999,999.99")
        if "edge" in k:
            self._edges(giro, tg)
        if "fx" in k:
            self._currencies(giro, comps)
        if "empty" in k:
            self._empty()
        for key, short, since in comps:
            self._company(key, short, since, giro)
        if comps and "full" in k:
            self._full(comps[0][0])
        # the portfolio: values in its currency now; the savings plan bought into it
        secs = SECURITIES + ([("Einzelaktie %02d" % i, "Einzelaktie Nummer %02d Stammaktie Inhaber" % i) for i in range(1, 25)] if "full" in k else [])
        pos = []
        for i, (short, long) in enumerate(secs):
            q, p = 10.0 + 37 * i, round(112.40 / (1 + i % 5), 2)
            if "large" in k:
                q *= 900
            pos.append({"name": self.nm(short, long), "isin": "XX%010d" % (4711 + i), "quantity": q, "marketPrice": p,
                        "marketValue": round(q * p, 2), "purchaseValue": round(q * p * 0.83, 2), "currency": depot_ccy, "assetClass": "ETF" if i < 3 else "Aktie"})
        self.portfolios[depot] = pos
        self.opening[depot] = round(sum(x["marketValue"] for x in pos), 2)

    def _edges(self, giro: str, tg: str) -> None:
        """Bookings on the edges of months and years; an account opened today."""
        for y in range(self.start.year, self.today.year + 1):
            self.tx(giro, date(y, 12, 31), -self.amt(99.99, 25.0), self.nm("Feuerwerk", "Feuerwerk und Silvesterbedarf Fachhandel"), "Silvester", "Lebenshaltung\\Freizeit")
            self.tx(giro, date(y, 1, 1), self.amt(0.01, 1.0), "Bank", "Zinsen Vorjahr", "Einnahmen\\Kapitalerträge")
            if date(y, 12, 31) < self.today:                            # over the year end: out on 31 Dec, in on 2 Jan
                self.move(giro, tg, date(y, 12, 31), self.amt(1000.0, 25.0), "Jahresübertrag", dst_day=date(y + 1, 1, 2))
            if y % 4 == 0:
                self.tx(giro, date(y, 2, 29), -self.amt(29.02, 25.0), "Onlinehandel", "Schalttag", "Lebenshaltung\\Freizeit")
        new = self.account("priv.neu", self.nm("Neues Konto", "Neues Gemeinschaftskonto heute eröffnet für gemeinsame Ausgaben"), "Girokonto", 0.0,
                           since=self.today)
        self.move(giro, new, self.today, self.amt(100.0, 25.0), "Erste Einzahlung")
        self.notes.append("today %s, an account opened today" % self.today)

    def _currencies(self, giro: str, comps: list) -> None:
        usd = self.account("priv.usd", self.nm("Dollarkonto", "Fremdwährungskonto US-Dollar Verrechnungskonto Dividenden"), "Girokonto",
                           self.amt(3200.0, 25.0), currency="USD")
        gbp = self.account("priv.gbp", self.nm("Kreditkarte GBP", "Kreditkarte Pfund Sterling Reisekonto Vereinigtes Königreich"), "Kreditkarte",
                           -self.amt(150.0, 25.0), currency="GBP")
        for n, m in enumerate(self.month_starts()):
            self.tx(usd, self.on(m, 15), self.amt(350.0, 25.0), self.nm("Dividende", "Quellensteuerpflichtige Dividendenzahlung"), "Dividende",
                    "Einnahmen\\Dividenden")
            if n % 2 == 0:                                               # euros into dollars: two amounts for one transfer
                self.move(giro, usd, self.on(m, 10), self.amt(1000.0, 25.0), "Devisen", x_dst=self.amt(1085.37, 25.0))
            self.tx(gbp, self.on(m, 12), -self.amt(64.50, 25.0), "London Café", "Card", "Lebenshaltung\\Reisen")
            self.tx(usd, self.on(m, 28), -2.50, "Bank", "Kontoführung", "")              # without a category, as one in euros of the same name:
            self.tx(giro, self.on(m, 28), -4.90, "Bank", "Kontoführung", "")             # two groups to assign, never one sum of both
        if comps:
            chf = self.account(comps[0][0] + ".chf", self.nm("Konto CHF", "Geschäftskonto Schweizer Franken Niederlassung Basel"), "Girokonto",
                               self.amt(12000.0, 1000.0), currency="CHF")
            self._chf = chf
        self.notes.append("accounts in USD, GBP, CHF; a portfolio in USD")

    def _empty(self) -> None:
        """An area without any booking, an area whose group holds no account, an account with a balance and no booking."""
        self.account("priv.alt", self.nm("Altes Sparbuch", "Altes Sparbuch aus Kindertagen ohne Umsätze seit Jahren"), "Sparkonto", 1234.56, bank=False)
        self.group("ruhe", self.nm("Ruhende GbR", "Ruhende Gesellschaft bürgerlichen Rechts ohne Geschäftstätigkeit seit Gründung"), 1)
        self.areas.append(("ruhe", self.layout[-1][1], "company", 0.5))
        self.account("ruhe.kk", self.nm("Geschäftskonto", "Geschäftskonto ohne Umsätze"), "Girokonto", 0.0)
        self.group("leer", self.nm("Leere Holding", "Leere Holding ohne ein einziges Konto in MoneyMoney"), 1)
        self.areas.append(("leer", self.layout[-1][1], "company", 1.0))
        self.notes.append("an area without bookings, one without accounts")

    def _company(self, key: str, short: str, since: Optional[date], giro: str) -> None:
        kk = key + ".kk"
        gbr = "GbR" in short
        if since:                                                        # founded this month: the share capital, the first invoice
            self.move(giro, kk, since, self.amt(25000.0, 40.0), "Stammeinlage")
        for n, m in enumerate(self.month_starts()):
            sales = self.amt(9000.0 + 250.0 * (n % 12), 940.0)
            for day, payee, share in ((5, "customer", 0.55), (15, "customer", 0.25), (24, "customer", 0.20)):
                self.tx(kk, self.on(m, day), round(sales * share, 2), self.payee(payee), self.purpose("Rechnung %02d/%d" % (m.month, m.year), m, n),
                        "Betrieb\\Umsatzerlöse")
            self.tx(kk, self.on(m, 8), -round(sales * 0.32, 2), self.payee("supplier"), self.purpose("Wareneinkauf", m, n), "Betrieb\\Wareneinkauf")
            self.tx(kk, self.on(m, 2), -self.amt(950.0, 300.0), self.nm("Bürogemeinschaft", "Bürogemeinschaft und Coworking Space am Hafen"),
                    self.purpose("Miete Büro", m, n), "Betrieb\\Büromiete")
            self.tx(kk, self.on(m, 10), -round(sales * 0.11, 2), self.payee("tax"), self.purpose("Umsatzsteuer", m, n), "Steuern\\Umsatzsteuer")
            if getattr(self, "_chf", None) and self._chf.startswith(key + "."):
                self.tx(self._chf, self.on(m, 20), self.amt(2100.0, 1000.0), "Kunde Basel AG", "Rechnung", "Betrieb\\Erlöse Schweiz")
        buy = date(self.today.year - 1, 11, 20)                         # as such purchases go: in November, paid off from January
        if gbr and not self.properties and not since and self.start <= buy:          # a property bought with a seller's loan, paid off by a rule
            price = self.amt(1500000.0, 166.67)                         # large: 250 million
            immo = self.account(key + ".immo", self.nm("Immobilie Lindenhof", "Wohn- und Geschäftshaus Lindenhof 3–7 mit Hinterhaus und Gewerbeeinheiten"),
                                "Festgeldanlage", 0.0, bank=False)
            vd = self.account(key + ".vd", self.nm("Kaufpreisdarlehen", "Kaufpreisdarlehen der Verkäufergemeinschaft mit jährlicher Zinsabrechnung"),
                              "Darlehenskonto", 0.0, bank=False)
            seller = "seller." + key
            self.ibans[seller] = "DE%02d%018d" % (91, 800000000000000000 + len(self.ibans))
            down = round(price * 0.02, 2)
            self.tx(immo, buy, price, self.payee("seller"), "Kauf")
            self.tx(kk, buy, -down, self.payee("seller"), self.purpose("Anzahlung Kaufpreis", buy))
            self.tx(vd, buy, -round(price - down, 2), self.payee("seller"), "Kaufpreisstundung")
            first = date(self.today.year, 1, 1)                         # (the interest of a year: on its first day's balance)
            annuity = round(price * 0.004, 2)
            for m in self.month_starts():
                if m >= first:
                    self.tx(kk, m, -annuity, self.payee("seller"), self.purpose("Annuität Kaufpreisdarlehen Lindenhof", m), "Umbuchung", seller)
                    self.tx(kk, self.on(m, 5), round(price * 0.0063, 2), self.payee("tenant"), self.purpose("Miete", m), "Vermietung\\Objekt\\Mieteinnahmen")
                    self.tx(kk, self.on(m, 6), -round(price * 0.0005, 2), "Hausverwaltung", "Bewirtschaftung", "Vermietung\\Objekt\\Bewirtschaftung")
            self.loans.append({"name": self.layout[-1][1], "area": key, "loan": vd, "source": kk, "seller": seller, "from": first, "buy": buy,
                               "price": price})
            self.properties.append({"area": key, "account": immo, "price": price, "buy": buy, "annuity": annuity, "loan": round(price - down, 2)})

    def _full(self, key: str) -> None:
        """Forty accounts in one area and thousands of card payments over them; a category tree of over a hundred."""
        for g in range(12):
            self.cats.append(("Kostenstelle %02d" % (g + 1), 0, True, {}))
            for s in range(9):
                self.cats.append(("Kostenart %02d.%d" % (g + 1, s + 1), 1, False, {}))
        accs = []
        for i in range(40):
            typ, bank = [("Girokonto", True), ("Kreditkarte", True), ("Sparkonto", True), ("Offline-Konto", False)][i % 4]
            accs.append(self.account("%s.a%02d" % (key, i), "%s %02d" % ({"Girokonto": "Unterkonto", "Kreditkarte": "Firmenkarte",
                                                                           "Sparkonto": "Rücklage", "Offline-Konto": "Kasse"}[typ], i + 1),
                                     typ, self.amt(1000.0 * (i % 7), 100.0), bank=bank))
        rnd = random.Random(self.label + " full")
        lo = max(self.start, self.today - timedelta(730))
        for d in self.days(lo, self.today):
            for _ in range(rnd.choice([2, 3, 4, 5, 6])):
                g, s = rnd.randrange(12), rnd.randrange(9)
                x = rnd.choice([3.50, 12.99, 49.0, 250.0, 1999.99]) * (1 if rnd.random() < 0.9 else -1)
                self.tx(rnd.choice(accs), d, -x, "Händler %03d" % rnd.randrange(400), "Kartenzahlung",
                        "" if rnd.random() < 0.05 else "Kostenstelle %02d\\Kostenart %02d.%d" % (g + 1, g + 1, s + 1))
        self.notes.append("forty accounts, %d bookings" % len(self.txs))

    # -- for Kontor ----------------------------------------------------------------------------------------------------------
    def ordered_layout(self) -> List[tuple]:
        """MoneyMoney's order: each area's group, then its accounts (the private ones and the stakes in the private group)."""
        groups = [x for x in self.layout if x[4] and x[2] == 1]
        out = [self.layout[0]]
        for g in groups:
            out.append(g)
            out += [x for x in self.layout if not x[4] and x[0].split(".")[0] == g[0]]
        return out

    def _accounts(self) -> List[dict]:
        bal = dict(self.opening)
        keys = {uid(x[0]): x[0] for x in self.layout}
        for t in self.txs:
            k = keys[t["accountUuid"]]
            if k not in self.portfolios:
                bal[k] = round(bal.get(k, 0.0) + t["amount"], 2)
        fetched = stamp(self.today)
        return [{"uuid": uid(key), "name": name, "indentation": indent, "type": typ, "group": group,
                 "balance": [[0.0 if group else bal.get(key, 0.0), cur]], "currency": cur, "accountNumber": iban or "", "bankCode": bank,
                 "iban": iban, "owner": "Inhaber", "portfolio": portfolio, "attributes": {},
                 "refreshTimestamp": fetched if (bank or portfolio) else None, "icon": b""}
                for key, name, indent, typ, group, iban, bank, portfolio, cur in self.ordered_layout()]

    def name_of(self, key: str) -> str:
        return next(x[1] for x in self.layout if x[0] == key)

    def ref(self, key: str) -> str:
        return "%s | %s" % (uid(key), next(x[1] for x in self.layout if x[0] == key))

    def config(self, receipts_dir: str) -> Dict:
        cfg = {
            "dry_run": False, "notifications": False,
            "schedule": {"interval_minutes": 30, "automatic": False},
            "areas": [dict({"id": uid(k), "name": name, "kind": kind, "main_area": i == 0, "accounts": [self.ref(k)]},
                           **({"share": round(share, 4)} if share is not None else {})) for i, (k, name, kind, share) in enumerate(self.areas)],
            "companies": [{"area": uid(c), "participation": self.ref(stake), "retroactive_from": "all"} for c, stake in self.companies],
            "loans": [{"name": ln["name"], "loan_account": self.ref(ln["loan"]), "source_accounts": [self.ref(ln["source"])],
                       "detection": {"counter_iban": self.ibans[ln["seller"]]}, "from_date": ln["from"].isoformat(),
                       "interest": {"model": "yearly_base", "rate_list": [{"from_date": ln["buy"].isoformat(), "percent": 3.0}], "booking_day": "with_payment"},
                       "booking": {"counterparty": self.payee("seller"), "category_repayment": "Umbuchung", "category_interest": "Finanzierung\\Zinsen"}}
                      for ln in self.loans],
            "balance": {"months_back": max(13, min(60, self.months + 1)), "illiquid_roles": ["participations"]},
            "cashflow": {"category_to_account": {"Investments\\ETF": self.ref("priv.depot")}} if any(x[0] == "priv.depot" for x in self.layout) else {},
            "real_estate": [self._property(i, p) for i, p in enumerate(self.properties)],
            "updates": {"check_mode": "aus"},
            "receipts": {"folder": receipts_dir, "subfolder": "{year}/{entity}", "folder_confirmed": True},
            "ui": {"lock_minutes": 15, "port": 0},
        }
        return cfg

    def _property(self, i: int, p: dict) -> dict:
        name = self.nm("Lindenhof", "Wohn- und Geschäftshaus Lindenhof 3–7 mit Hinterhaus")
        price = p["price"]
        return {"id": "dw%d" % i, "name": name, "area": uid(p["area"]), "category": "Vermietung\\Objekt", "property_account": self.ref(p["account"]),
                "loan_accounts": {}, "in_planning": False, "documents": [], "notes": "",
                "calcs": [{"id": "k1", "name": self.nm("Basis", "Basisrechnung mit vorsichtigen Annahmen zur Mietentwicklung"), "created": p["buy"].isoformat() + " 10:00",
                           "active": True, "inputs": {
                               "name": name, "kind": "commercial", "purchase_price": price, "transfer_date": p["buy"].isoformat(), "horizon_years": 20,
                               "closing_costs": {"transfer_tax_percent": 3.5, "notary": round(price * 0.005, 2), "land_register": round(price * 0.002, 2)},
                               "building_share_percent": 70, "depreciation_percent": 2,
                               "rent": {"net_rent_month": round(price * 0.0063, 2), "utilities_month": round(price * 0.0005, 2),
                                        "index": {"kind": "cpi", "cpi_base": 120.0, "cpi_current": 120.0, "cpi_increase_percent": 2.0, "factor": 1, "threshold_percent": 0}},
                               "costs": {"non_recoverable_pa": round(price * 0.0016, 2), "reserve_pa": round(price * 0.0027, 2), "increase": "cpi"},
                               "loans": [{"name": "Kaufpreisdarlehen", "amount": p["loan"], "interest_percent": 3.0, "kind": "annuity",
                                          "annuity_month": p["annuity"], "settlement": "yearly"}],
                               "partners": [{"name": "A", "share_percent": 50, "tax_rate_percent": 42}, {"name": "B", "share_percent": 50, "tax_rate_percent": 42}],
                               "distribution_percent": 50, "tax_refund_in_cashflow": False}}]}

    def state(self) -> Dict:
        return {"seen": {"id": 0, "tag": "2000-01-01"}}

    def categories(self) -> List[dict]:
        out, path = [], []
        for name, indent, group, extra in self.cats:
            path = path[:indent] + [name]
            out.append(dict({"name": name, "indentation": indent, "group": group, "uuid": uid("cat:" + "\\".join(path))}, **extra))
        return out

    def category_paths(self) -> Dict[str, str]:
        out, path = {}, []
        for name, indent, _, _ in self.cats:
            path = path[:indent] + [name]
            out[uid("cat:" + "\\".join(path))] = "\\".join(path)
        return out

    def describe(self) -> str:
        return "%s: %s, today %s, from %s, %d areas, %d accounts, %d bookings%s" % (
            self.label, "+".join(sorted(self.kinds)) or "plain", self.today, self.start, len(self.areas),
            sum(1 for x in self.layout if not x[4]), len(self.txs), ("; " + "; ".join(self.notes)) if self.notes else "")

    def bridge(self, dry_run: bool = True, timeout: int = 0) -> "Bridge":
        """Called like mm_bridge.Bridge (Kontor's bridge_factory)."""
        return Bridge(self, dry_run)


class Bridge:
    """The world's MoneyMoney: the calls of mm_bridge.Bridge, answered from memory; what Kontor writes stays there (as MoneyMoney:
    bookings only into accounts without a bank, categories only)."""

    def __init__(self, world: World, dry_run: bool = True):
        self.world, self.dry_run, self.written, self.quiet = world, dry_run, [], False

    def export_accounts(self) -> List[dict]:
        with self.world.lock:
            return copy.deepcopy(self.world.accounts)

    def export_categories(self) -> List[dict]:
        return self.world.categories()

    def export_transactions(self, from_date: date, to_date: Optional[date] = None, account: Optional[str] = None) -> List[dict]:
        with self.world.lock:
            return [copy.deepcopy(x) for x in self.world.txs if local_day(x["bookingDate"]) >= from_date
                    and (to_date is None or local_day(x["bookingDate"]) <= to_date) and (not account or x["accountUuid"] == account)]

    def export_portfolio(self, account: str) -> List[dict]:
        return copy.deepcopy(next((v for k, v in self.world.portfolios.items() if uid(k) == account), []))

    def add_transaction(self, account_ref: str, booking_date: date, payee: str, amount: float, purpose: str = "", category: Optional[str] = None) -> None:
        self.written.append(("add", account_ref, booking_date, amount))
        if self.dry_run:
            return
        w = self.world
        with w.lock:
            acc = next((a for a in w.accounts if a["uuid"] == account_ref and not a["group"]), None)
            if acc is None or acc.get("iban") or acc.get("portfolio"):
                raise ValueError("only offline accounts")
            path = w.category_paths().get(category or "", category or "")
            w._id += 1
            w.txs.append({"id": w._id, "accountUuid": account_ref, "bookingDate": stamp(booking_date), "valueDate": stamp(booking_date),
                          "amount": round(float(amount), 2), "currency": acc["currency"], "name": payee, "purpose": purpose,
                          "category": path.split("\\")[-1], "categoryPath": path, "categoryUuid": "", "accountNumber": "", "bankCode": "",
                          "booked": True, "checkmark": False, "comment": "", "bookingText": ""})
            acc["balance"][0][0] = round(acc["balance"][0][0] + float(amount), 2)

    def set_transaction(self, tx_id: int, category: Optional[str] = None) -> None:
        self.written.append(("set", tx_id, category))
        if self.dry_run:
            return
        w = self.world
        with w.lock:
            for x in w.txs:
                if x["id"] == int(tx_id) and category is not None:
                    path = w.category_paths().get(category, category)
                    x["category"], x["categoryPath"] = path.split("\\")[-1], path


def worlds(names=None) -> List[World]:
    return [World(n) for n in (names or FIXED)]
