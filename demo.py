"""Kontor's demo: a made-up world in place of MoneyMoney, to show Kontor without showing anyone's data.

Everything here is invented -- names, accounts, amounts. The IBANs are the public sample IBANs from banks' documentation
(some with a changed last digit), as in the tests. The world is built anew for each demo, its dates counted back from today:
a private person over four years (a flat with its loan, a portfolio, a job until two years ago), the company founded then
(Muster UG: an online trade, two years), and a partnership (Parkweg GbR) with a commercial property bought with a seller's loan.

`World` holds the accounts and transactions; `World.bridge` stands in for the bridge to MoneyMoney (mm_bridge.Bridge): it
answers the same calls from memory and takes what Kontor writes (bookings of the rules, categories) into the same memory.
Nothing here reads a file, starts a program or goes onto the network. The demo itself (its own data folder, its own sign-in,
which requests it answers) is DemoApp in service.py.
"""
from __future__ import annotations

import copy
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

_NS = uuid.UUID("5b0f6c1e-2a47-4f7e-9d0c-6a1d8e3b7c25")

# the flat list MoneyMoney exports: (name, indentation, group, extra)
CATEGORIES = [("Unkategorisiert", 0, False, {"default": True}), ("Umbuchung", 0, False, {}),
              ("Einnahmen", 0, True, {}), ("Gehalt", 1, False, {}), ("Erstattungen", 1, False, {}),
              ("Wohnen", 0, True, {}), ("Hausgeld", 1, False, {}), ("Nebenkosten", 1, False, {}),
              ("Finanzierung", 0, True, {}), ("Zinsen", 1, False, {}),
              ("Lebenshaltung", 0, True, {}), ("Lebensmittel", 1, False, {"budget": {"amount": 650.0, "period": "monthly"}}),
              ("Restaurant", 1, False, {}), ("Mobilität", 1, False, {}), ("Freizeit", 1, False, {}), ("Haushalt", 1, False, {}), ("Reisen", 1, False, {}),
              ("Versicherungen", 0, True, {}), ("Haftpflicht", 1, False, {}), ("Krankenversicherung", 1, False, {}),
              ("Investments", 0, True, {}), ("ETF", 1, False, {}),
              ("Vermietung", 0, True, {}), ("Parkweg", 1, True, {}), ("Mieteinnahmen", 2, False, {}), ("Bewirtschaftung", 2, False, {}),
              ("Betrieb", 0, True, {}), ("Umsatzerlöse", 1, False, {}), ("Wareneinkauf", 1, False, {}), ("Büromiete", 1, False, {}),
              ("Software", 1, False, {}), ("Steuerberatung", 1, False, {}), ("Geschäftsführergehalt", 1, False, {}),
              ("Steuern", 0, True, {}), ("Umsatzsteuer", 1, False, {}), ("Lohnsteuer", 1, False, {}), ("Körperschaftsteuer", 1, False, {})]

GIRO_IBAN, BROKER_IBAN, LOAN_IBAN = "DE02120300000000202051", "DE02100500000054540402", "DE02500105170137075030"
UG_IBAN, UG_SAVINGS_IBAN, GBR_IBAN = "DE02701500000000594937", "DE02100100100006820101", "DE02701500000000594938"
SELLER_IBAN = "DE02300209000106531065"
ANNUITY_TEXT = "Annuität Kaufpreisdarlehen Objekt Parkweg 7"
UG_NAME, GBR_NAME = "Muster UG", "Parkweg GbR"


def uid(key: str) -> str:
    """A fixed id per account (the same in every demo, so a page that remembers an area finds it again)."""
    return str(uuid.uuid5(_NS, "kontor-demo/" + key))


def _months_back(d: date, n: int) -> date:
    """The first day of the month n months before d's."""
    k = d.year * 12 + d.month - 1 - n
    return date(k // 12, k % 12 + 1, 1)


def _stamp(d: date) -> datetime:
    """As MoneyMoney exports a day: its local midnight, as a time in UTC without a zone."""
    return datetime(d.year, d.month, d.day).astimezone(timezone.utc).replace(tzinfo=None)


class World:
    """Accounts, transactions and holdings of the demo, counted back from today."""

    def __init__(self, today: Optional[date] = None, default_category: str = "Unkategorisiert"):
        """default_category: the name of MoneyMoney's default category (as in the real one, so that it counts as none)."""
        self.today = today or date.today()
        self.default_category = default_category
        self.start = _months_back(self.today, 48)               # four years of the private person ...
        self.founded = _months_back(self.today, 24)             # ... two of the company, founded then (its first month: no salary yet)
        self.purchase = date(self.today.year - 2, 11, 20)      # Parkweg GbR bought its property then (a loan of the seller) ...
        self.first_annuity = date(self.today.year - 1, 1, 1)  # ... paid off from January on (the interest of a year: on its first day's balance)
        self.lock = threading.Lock()
        self._next = 500000
        self.txs: List[dict] = []
        self._build()

    # -- the world -----------------------------------------------------------------------------------------------------------
    def _tx(self, key: str, d: date, amount: float, name: str = "", purpose: str = "", category: str = "", counter_iban: str = "") -> None:
        if d > self.today:                                      # nothing in the future
            return
        self._next += 1
        self.txs.append({"id": self._next, "accountUuid": uid(key), "bookingDate": _stamp(d), "valueDate": _stamp(d), "amount": round(amount, 2),
                         "currency": "EUR", "name": name, "purpose": purpose, "category": category.split("\\")[-1], "categoryPath": category,
                         "categoryUuid": "", "accountNumber": counter_iban, "bankCode": "", "booked": True, "checkmark": False,
                         "comment": "", "bookingText": ""})

    def _months(self, since: date):
        d = since
        while d <= self.today:
            yield d
            d = _months_back(d, -1)

    def _n(self, m: date, since: date) -> int:
        """Months from since to m."""
        return (m.year - since.year) * 12 + m.month - since.month

    def _build(self) -> None:
        t = self._tx
        for m in self._months(self.start):
            y, mo = m.year, m.month
            day = lambda n: date(y, mo, min(n, 28 if mo == 2 else 30))
            ug = self._n(m, self.founded)                       # months since the company was founded (< 0: before)
            # income: the job until the company was founded, then the managing director's salary from it (from its second month)
            if ug < 0:
                t("priv.giro", day(1), 7400.0 + (7000.0 if mo == 11 else 0.0), "Nordwerk AG", "Gehalt" if mo != 11 else "Gehalt und Weihnachtsgeld", "Einnahmen\\Gehalt")
            elif ug >= 1:
                pay = 4200.0 if ug < 13 else 5500.0
                t("ug.kk", day(28), -pay, "Geschäftsführer", "Gehalt %02d/%d" % (mo, y), "Betrieb\\Geschäftsführergehalt")
                t("priv.giro", day(28), pay, UG_NAME, "Gehalt %02d/%d" % (mo, y), "Einnahmen\\Gehalt")
                t("ug.kk", day(10), -(1050.0 if ug < 13 else 1500.0), "Finanzamt", "Lohnsteuer", "Steuern\\Lohnsteuer")
            # the flat and its loan, living, a savings plan into the portfolio (smaller since the company)
            t("priv.giro", day(1), -1500.0, "Stadtsparkasse", "Annuität Darlehen Lindenstraße", "Umbuchung", LOAN_IBAN)
            t("priv.darl", day(1), 1500.0, "Hausbank", "Annuität", "Umbuchung", GIRO_IBAN)
            t("priv.darl", day(1), -935.0 + self._n(m, self.start) * 1.6, "Stadtsparkasse", "Zinsen", "Finanzierung\\Zinsen")
            plan = 1000.0 if ug < 0 else 500.0
            t("priv.giro", day(2), -plan, "Broker", "Übertrag Sparplan", "Umbuchung", BROKER_IBAN)
            t("priv.tr", day(2), plan, "Hausbank", "Übertrag Sparplan", "Umbuchung", GIRO_IBAN)
            t("priv.tr", day(4), -plan, "Broker", "Sparplan Welt-ETF", "Investments\\ETF")
            t("priv.giro", day(3), -410.0, "WEG Lindenstraße 12", "Hausgeld", "Wohnen\\Hausgeld")
            t("priv.giro", day(5), -96.0, "Versicherung Nord", "Privathaftpflicht und Hausrat", "Versicherungen\\Haftpflicht")
            t("priv.giro", day(5), -612.0 if ug < 0 else -735.0, "Krankenkasse", "Beitrag", "Versicherungen\\Krankenversicherung")
            t("priv.giro", day(8), -168.0 - (mo % 3) * 22.0, "Stadtwerke", "Strom und Wärme", "Wohnen\\Nebenkosten")
            for n, amount in ((6, -142.30), (13, -167.85), (20, -121.40), (27, -188.10)):
                t("priv.giro", day(n), amount - (mo % 4) * 3.5, "Biomarkt", "Einkauf", "Lebenshaltung\\Lebensmittel")
            t("priv.giro", day(11), -58.0 - (mo % 5) * 9.0, "Trattoria", "Abendessen", "Lebenshaltung\\Restaurant")
            t("priv.giro", day(17), -89.0, "Verkehrsbetriebe", "Monatskarte", "Lebenshaltung\\Mobilität")
            t("priv.giro", day(22), -64.0 - (mo % 3) * 15.0, "Kino und Konzert", "Tickets", "Lebenshaltung\\Freizeit")
            t("priv.giro", day(15), -48.90 - (mo % 4) * 11.0, "Baumarkt", "Werkzeug", "")              # without a category: to assign
            if mo in (4, 8):
                t("priv.giro", day(19), -1850.0, "Reisebüro", "Urlaub", "" if self._n(m, self.start) > 30 else "Lebenshaltung\\Reisen")
            if mo == 6 and m > self.purchase:                                                           # a yearly contribution into the GbR
                t("priv.giro", day(20), -6000.0, GBR_NAME, "Einlage", "Umbuchung", GBR_IBAN)
                t("gbr.kk", day(20), 6000.0, "Gesellschafter A", "Einlage", "Umbuchung", GIRO_IBAN)
            # the company: founded with its share capital; an online trade that grows month by month
            if ug == 0:
                t("priv.giro", day(1), -5000.0, UG_NAME, "Stammeinlage", "Umbuchung", UG_IBAN)
                t("ug.kk", day(1), 5000.0, "Gesellschafter", "Stammeinlage", "Umbuchung", GIRO_IBAN)
            if ug >= 0:
                sales = 9000.0 + 750.0 * ug + (600.0 if mo == 12 else -300.0 if mo in (1, 2) else 0.0)
                for n, name, share in ((5, "Onlineshop Auszahlung", 0.55), (15, "Kunde Nord GmbH", 0.25), (24, "Kunde Süd KG", 0.20)):
                    t("ug.kk", day(n), round(sales * share, 2), name, "Rechnung %02d/%d" % (mo, y), "Betrieb\\Umsatzerlöse")
                t("ug.kk", day(8), -round(sales * 0.32, 2), "Großhandel Meyer", "Wareneinkauf", "Betrieb\\Wareneinkauf")
                t("ug.kk", day(2), -950.0, "Bürogemeinschaft", "Miete Büro", "Betrieb\\Büromiete")
                t("ug.kk", day(10), -180.0, "Softwareabos", "Shop und Buchhaltung", "Betrieb\\Software")
                t("ug.kk", day(20), -320.0, "Kanzlei Steuer", "Buchhaltung", "Betrieb\\Steuerberatung")
                if ug >= 1:
                    t("ug.kk", day(10), -round((9000.0 + 750.0 * (ug - 1)) * 0.11, 2), "Finanzamt", "Umsatzsteuer-Vorauszahlung", "Steuern\\Umsatzsteuer")
                if ug >= 3:                                                                            # a reserve for the taxes
                    t("ug.kk", day(26), -1500.0, UG_NAME, "Steuerrücklage", "Umbuchung", UG_SAVINGS_IBAN)
                    t("ug.tg", day(26), 1500.0, UG_NAME, "Steuerrücklage", "Umbuchung", UG_IBAN)
                if ug >= 12 and mo in (3, 6, 9, 12):
                    t("ug.kk", day(10), -1200.0, "Finanzamt", "Körperschaftsteuer-Vorauszahlung", "Steuern\\Körperschaftsteuer")
                if mo == 12 and ug >= 3:
                    t("ug.tg", day(30), 45.0 + ug * 2.0, "Bank", "Zinsen", "Finanzierung\\Zinsen")
        # Parkweg GbR: the property bought with a seller's loan; rent from the month after, the annuity (the rule books
        # interest and repayment into the loan) from the year after
        t("gbr.immo", self.purchase, 1500000.0, "Verkäufer", "Kauf Parkweg 7")
        t("gbr.kk", self.purchase, -250000.0, "Verkäufer", "Kaufpreis Parkweg 7, Eigenanteil")
        t("gbr.vd", self.purchase, -1250000.0, "Verkäufer", "Kaufpreisstundung")
        t("gbr.vd", _months_back(self.purchase, -1).replace(day=15), 50000.0, GBR_NAME, "Sondertilgung")
        t("gbr.kk", _months_back(self.purchase, -1).replace(day=15), -50000.0, "Verkäufer", "Sondertilgung Kaufpreisdarlehen", "Umbuchung")
        for m in self._months(_months_back(self.purchase, -1)):
            t("gbr.kk", date(m.year, m.month, 5), 9500.0, "Mieter Parkweg", "Miete", "Vermietung\\Parkweg\\Mieteinnahmen")
            t("gbr.kk", date(m.year, m.month, 6), -800.0, "Hausverwaltung", "Bewirtschaftung", "Vermietung\\Parkweg\\Bewirtschaftung")
        for m in self._months(self.first_annuity):
            t("gbr.kk", m, -6000.0, "Verkäufer", ANNUITY_TEXT, "Umbuchung", SELLER_IBAN)
        # balances now: what was there at the start and everything since
        opening = {"priv.giro": 9000.0, "priv.tr": 0.0, "priv.darl": -340000.0, "ug.kk": 0.0, "ug.tg": 0.0, "gbr.kk": 310000.0,
                   "gbr.immo": 0.0, "gbr.vd": 0.0}
        self.balances = dict(opening)
        key_of = {uid(k): k for k in self._keys()}
        for x in self.txs:
            key = key_of[x["accountUuid"]]
            if key in opening:
                self.balances[key] = round(self.balances[key] + x["amount"], 2)
        self.balances.update({"priv.depot": round(sum(p["quantity"] * p["marketPrice"] for p in self.PORTFOLIO), 2), "priv.immo": 465000.0,
                              "priv.bet.ug": 0.0, "priv.bet.gbr": 0.0})
        self.accounts = self._accounts()

    def _keys(self) -> List[str]:
        return [k for k, *_ in self._layout()]

    @staticmethod
    def _layout():
        # key, name, indentation, type, group, iban, bank code, portfolio
        return [("root", "Alle Konten", 0, "Kontengruppe", True, None, "", False),
                ("priv", "Privat", 1, "Kontengruppe", True, None, "", False),
                ("priv.liq", "Liquidität", 2, "Kontengruppe", True, None, "", False),
                ("priv.giro", "Hausbank Giro", 3, "Girokonto", False, GIRO_IBAN, "12030000", False),
                ("priv.tr", "Broker Verrechnungskonto", 3, "Girokonto", False, BROKER_IBAN, "10050000", False),
                ("priv.anl", "Anlagen", 2, "Kontengruppe", True, None, "", False),
                ("priv.depot", "Depot", 3, "Portfolio", False, None, "10050000", True),
                ("priv.immo", "Wohnung Lindenstraße", 3, "Offline-Konto", False, None, "", False),
                ("priv.bet", "Beteiligungen", 2, "Kontengruppe", True, None, "", False),
                ("priv.bet.ug", "Beteiligung " + UG_NAME, 3, "Offline-Konto", False, None, "", False),
                ("priv.bet.gbr", "Beteiligung " + GBR_NAME, 3, "Offline-Konto", False, None, "", False),
                ("priv.verb", "Verbindlichkeiten", 2, "Kontengruppe", True, None, "", False),
                ("priv.darl", "Darlehen Lindenstraße", 3, "Darlehenskonto", False, LOAN_IBAN, "50010517", False),
                ("ug", UG_NAME, 1, "Kontengruppe", True, None, "", False),
                ("ug.liq", "Liquidität", 2, "Kontengruppe", True, None, "", False),
                ("ug.kk", "Geschäftskonto", 3, "Girokonto", False, UG_IBAN, "70150000", False),
                ("ug.tg", "Tagesgeld Steuerrücklage", 3, "Sparkonto", False, UG_SAVINGS_IBAN, "10010010", False),
                ("gbr", GBR_NAME, 1, "Kontengruppe", True, None, "", False),
                ("gbr.liq", "Liquidität", 2, "Kontengruppe", True, None, "", False),
                ("gbr.kk", "Geschäftskonto", 3, "Girokonto", False, GBR_IBAN, "70150000", False),
                ("gbr.anl", "Anlagen", 2, "Kontengruppe", True, None, "", False),
                ("gbr.immo", "Immobilie Parkweg", 3, "Festgeldanlage", False, None, "", False),
                ("gbr.verb", "Verbindlichkeiten", 2, "Kontengruppe", True, None, "", False),
                ("gbr.vd", "Kaufpreisdarlehen", 3, "Darlehenskonto", False, None, "", False)]

    def _accounts(self) -> List[dict]:
        fetched = _stamp(self.today)
        out = []
        for key, name, indent, typ, group, iban, bank, portfolio in self._layout():
            out.append({"uuid": uid(key), "name": name, "indentation": indent, "type": typ, "group": group,
                        "balance": [[self.balances.get(key, 0.0), "EUR"]], "currency": "EUR", "accountNumber": iban or "", "bankCode": bank,
                        "iban": iban, "owner": "Demo", "portfolio": portfolio, "attributes": {},
                        "refreshTimestamp": fetched if (bank or portfolio) else None, "icon": b""})
        return out

    PORTFOLIO = [{"name": "Welt-ETF", "isin": "IE00B4L5Y983", "quantity": 640.0, "marketPrice": 112.40, "purchaseValue": 61800.0, "assetClass": "ETF"},
                 {"name": "Schwellenländer-ETF", "isin": "IE00BKM4GZ66", "quantity": 420.0, "marketPrice": 33.10, "purchaseValue": 12900.0, "assetClass": "ETF"},
                 {"name": "Anleihen-ETF", "isin": "IE00BZ163L38", "quantity": 300.0, "marketPrice": 49.80, "purchaseValue": 15600.0, "assetClass": "ETF"}]

    def portfolio(self) -> List[dict]:
        return [dict(p, marketValue=round(p["quantity"] * p["marketPrice"], 2), currency="EUR") for p in self.PORTFOLIO]

    def state(self) -> Dict:
        """Kontor's state at the demo's start: everything in the world new; the portfolio's month-end values entered by hand
        (MoneyMoney does not export them) -- the savings plan as it was (1,000 a month, 500 since the company) and a market
        that mostly rose."""
        v, months = self.balances["priv.depot"], {}
        for k in range(1, 49):
            m = _months_back(self.today, k)
            v = v / 1.006 - (500.0 if m >= self.founded else 1000.0)
            months["%04d-%02d" % (m.year, m.month)] = round(v + (1400.0 if k % 5 == 2 else -900.0 if k % 7 == 3 else 0.0), 2)
        return {"seen": {"id": 0, "tag": "2000-01-01"}, "history": {uid("priv.depot"): months}}

    def _list(self) -> list:
        return [(self.default_category, 0, False, {"default": True})] + CATEGORIES[1:]

    def categories(self) -> List[dict]:
        return [dict({"name": name, "indentation": indent, "group": group, "uuid": uid("cat:" + path)}, **extra)
                for (name, indent, group, extra), path in zip(self._list(), self._paths())]

    def _paths(self) -> List[str]:
        out, path = [], []
        for name, indent, _, _ in self._list():
            path = path[:indent] + [name]
            out.append("\\".join(path))
        return out

    def category_paths(self) -> Dict[str, str]:
        return {uid("cat:" + p): p for p in self._paths()}

    # -- in place of MoneyMoney ----------------------------------------------------------------------------------------------
    def bridge(self, dry_run: bool = True, timeout: int = 0) -> "DemoBridge":
        """Called like mm_bridge.Bridge (Kontor's bridge_factory)."""
        return DemoBridge(self, dry_run)


class DemoBridge:
    """The demo's MoneyMoney: the calls of mm_bridge.Bridge, answered from the world in memory; what is written stays there."""

    def __init__(self, world: World, dry_run: bool = True):
        self.world, self.dry_run, self.written, self.quiet = world, dry_run, [], False

    def export_accounts(self) -> List[dict]:
        with self.world.lock:
            return copy.deepcopy(self.world.accounts)

    def export_categories(self) -> List[dict]:
        return self.world.categories()

    def export_transactions(self, from_date: date, to_date: Optional[date] = None, account: Optional[str] = None) -> List[dict]:
        day = lambda x: x["bookingDate"].replace(tzinfo=timezone.utc).astimezone().date()      # as mm_bridge.local_date
        with self.world.lock:
            return [copy.deepcopy(x) for x in self.world.txs if day(x) >= from_date and (to_date is None or day(x) <= to_date)
                    and (not account or x["accountUuid"] == account)]

    def export_portfolio(self, account: str) -> List[dict]:
        return self.world.portfolio() if account == uid("priv.depot") else []

    def add_transaction(self, account_ref: str, booking_date: date, payee: str, amount: float, purpose: str = "", category: Optional[str] = None) -> None:
        self.written.append({"method": "addTransaction", "args": {"toAccount": account_ref, "onDate": booking_date.isoformat()}})
        if self.dry_run:
            return
        with self.world.lock:
            acc = next((a for a in self.world.accounts if a["uuid"] == account_ref and not a["group"]), None)
            if acc is None or acc.get("iban"):                    # as MoneyMoney: only into accounts without a bank behind them
                raise ValueError("only offline accounts")
            path = self._path(category or "")
            self.world._next += 1
            self.world.txs.append({"id": self.world._next, "accountUuid": account_ref, "bookingDate": _stamp(booking_date), "valueDate": _stamp(booking_date),
                                   "amount": round(float(amount), 2), "currency": "EUR", "name": payee, "purpose": purpose,
                                   "category": path.split("\\")[-1], "categoryPath": path, "categoryUuid": "", "accountNumber": "", "bankCode": "",
                                   "booked": True, "checkmark": False, "comment": "", "bookingText": ""})
            acc["balance"][0][0] = round(acc["balance"][0][0] + float(amount), 2)

    def set_transaction(self, tx_id: int, category: Optional[str] = None) -> None:
        self.written.append({"method": "setTransaction", "args": {"id": int(tx_id)}})
        if self.dry_run:
            return
        with self.world.lock:
            for x in self.world.txs:
                if x["id"] == int(tx_id):
                    if category is not None:
                        path = self._path(category)
                        x["category"], x["categoryPath"] = path.split("\\")[-1], path

    def _path(self, category: str) -> str:
        """A category given by its id or its path, as its path."""
        return self.world.category_paths().get(category, category)


def config(world: World, real: Dict, receipts_dir: str) -> Dict:
    """The demo's settings: areas, rules, a property with its calculation. From the real settings only what says how Kontor
    looks and works (language, lock, the assistant's model) -- nothing about anyone's money. receipts_dir: in the demo's own
    folder (receipts uploaded there go with it)."""
    u = lambda k, name: "%s | %s" % (uid(k), name)
    ui_real = (real or {}).get("ui") or {}
    purchase = world.purchase
    names = {k: name for k, name, *_ in World._layout()}
    mapping = {u(k, name): {"area": uid(k.split(".")[0]), "position": "", "confirmed": True} for k, name, _, _, group, *_ in World._layout() if not group}
    cfg = {
        "dry_run": False, "notifications": False,
        "schedule": {"interval_minutes": 30, "automatic": False},
        "areas": [{"id": uid("priv"), "name": "Privat", "kind": "private", "main_area": True, "accounts": [u("priv", "Privat")]},
                  {"id": uid("ug"), "name": UG_NAME, "kind": "company", "share": 1.0, "accounts": [u("ug", UG_NAME)]},
                  {"id": uid("gbr"), "name": GBR_NAME, "kind": "company", "share": 0.5, "accounts": [u("gbr", GBR_NAME)]}],
        "loans": [{"name": "Kaufpreisdarlehen", "loan_account": u("gbr.vd", names["gbr.vd"]), "source_accounts": [u("gbr.kk", names["gbr.kk"])],
                   "detection": {"counter_iban": SELLER_IBAN}, "from_date": world.first_annuity.isoformat(),
                   "interest": {"model": "yearly_base", "rate_list": [{"from_date": purchase.isoformat(), "percent": 3.0}], "booking_day": "with_payment"},
                   "booking": {"counterparty": "Verkäufer", "category_repayment": "Umbuchung", "category_interest": "Finanzierung\\Zinsen"}}],
        "companies": [{"area": uid("ug"), "participation": u("priv.bet.ug", names["priv.bet.ug"]), "retroactive_from": "all"},
                      {"area": uid("gbr"), "participation": u("priv.bet.gbr", names["priv.bet.gbr"]), "retroactive_from": "all"}],
        "balance": {"months_back": 48, "illiquid_roles": ["participations"], "illiquid_accounts": [u("priv.darl", names["priv.darl"])],
                    "accounts_mapping": mapping},
        "cashflow": {"category_to_account": {"Investments\\ETF": u("priv.depot", "Depot")}},
        "real_estate": [{"id": "im1", "name": "Parkweg", "area": uid("gbr"), "category": "Vermietung\\Parkweg", "property_account": u("gbr.immo", names["gbr.immo"]),
                         "loan_accounts": {}, "in_planning": False, "documents": [], "notes": "",
                         "calcs": [{"id": "k1", "name": "Basis", "created": world.purchase.isoformat() + " 10:00", "active": True, "inputs": {
                             "name": "Parkweg", "kind": "commercial", "purchase_price": 1500000, "transfer_date": world.purchase.isoformat(), "horizon_years": 20,
                             "closing_costs": {"transfer_tax_percent": 3.5, "notary": 7500, "land_register": 3000},
                             "building_share_percent": 70, "depreciation_percent": 2,
                             "rent": {"net_rent_month": 9500, "utilities_month": 800,
                                      "index": {"kind": "cpi", "cpi_base": 120.0, "cpi_current": 120.0, "cpi_increase_percent": 2.0, "factor": 1, "threshold_percent": 0}},
                             "costs": {"non_recoverable_pa": 2400, "reserve_pa": 4000, "increase": "cpi"},
                             "loans": [{"name": "Kaufpreisdarlehen", "amount": 1200000, "interest_percent": 3.0, "kind": "annuity", "annuity_month": 6000, "settlement": "yearly"}],
                             "partners": [{"name": "A", "share_percent": 50, "tax_rate_percent": 42}, {"name": "B", "share_percent": 50, "tax_rate_percent": 42}],
                             "distribution_percent": 50, "tax_refund_in_cashflow": False}}]}],
        "updates": {"check_mode": "aus"},
        "receipts": {"folder": receipts_dir, "subfolder": "{year}/{entity}", "folder_confirmed": True},
        "ui": {k: copy.deepcopy(ui_real[k]) for k in ("language", "lock_minutes", "remote_read_only", "theme", "port") if k in ui_real},
        "assistant": copy.deepcopy((real or {}).get("assistant") or {}),
    }
    cfg["ui"]["offline_copy"] = False                  # nothing of the demo is kept on a device for its offline view
    return cfg

