"""Kontor's demo: a made-up world in place of MoneyMoney, to show Kontor without showing anyone's data.

Everything here is invented -- names, accounts, amounts. The IBANs are the public sample IBANs from banks' documentation
(some with a changed last digit), as in the tests. The world is built anew for each demo, its dates counted back from today:
two years of a private household with a flat and its loan, a portfolio, and two partnerships (GbR) with a property each.

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
              ("Restaurant", 1, False, {}), ("Mobilität", 1, False, {}), ("Freizeit", 1, False, {}), ("Haushalt", 1, False, {}),
              ("Versicherungen", 0, True, {}), ("Haftpflicht", 1, False, {}), ("Krankenversicherung", 1, False, {}),
              ("Investments", 0, True, {}), ("ETF", 1, False, {}),
              ("Vermietung", 0, True, {}), ("Parkweg", 1, True, {}), ("Mieteinnahmen", 2, False, {}), ("Bewirtschaftung", 2, False, {}),
              ("Bahnhofstraße", 1, True, {}), ("Mieteinnahmen", 2, False, {}), ("Bewirtschaftung", 2, False, {})]

GIRO_IBAN, BROKER_IBAN, LOAN_IBAN = "DE02120300000000202051", "DE02100500000054540402", "DE02500105170137075030"
ALPHA_IBAN, BETA_IBAN = "DE02701500000000594937", "DE02701500000000594938"
BETA_LOAN1_IBAN, BETA_LOAN2_IBAN = "DE02500105170137075031", "DE02500105170137075032"
SELLER_IBAN = "DE02300209000106531065"
ANNUITY_TEXT = "Annuität Kaufpreisdarlehen Objekt Parkweg 7"


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
        self.start = _months_back(self.today, 24)               # two years of history
        self.purchase = date(self.today.year - 2, 11, 20)      # Alpha GbR bought its property then (a loan of the seller) ...
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

    def _build(self) -> None:
        t = self._tx
        for m in self._months(self.start):
            y, mo = m.year, m.month
            day = lambda n: date(y, mo, n)
            # the household: salary, the flat's loan, living, a savings plan into the portfolio
            t("priv.giro", day(1), 7400.0 if mo != 11 else 7400.0 + 6800.0, "Nordwerk AG", "Gehalt" if mo != 11 else "Gehalt und Weihnachtsgeld", "Einnahmen\\Gehalt")
            t("priv.giro", day(1), -1500.0, "Stadtsparkasse", "Annuität Darlehen Lindenstraße", "Umbuchung", LOAN_IBAN)
            t("priv.darl", day(1), 1500.0, "Hausbank", "Annuität", "Umbuchung", GIRO_IBAN)
            t("priv.darl", day(1), -880.0 + (m.year * 12 + mo - self.start.year * 12 - self.start.month) * 2.0, "Stadtsparkasse", "Zinsen", "Finanzierung\\Zinsen")
            t("priv.giro", day(2), -1000.0, "Broker", "Übertrag Sparplan", "Umbuchung", BROKER_IBAN)
            t("priv.tr", day(2), 1000.0, "Hausbank", "Übertrag Sparplan", "Umbuchung", GIRO_IBAN)
            t("priv.tr", day(4), -1000.0, "Broker", "Sparplan Welt-ETF", "Investments\\ETF")
            t("priv.giro", day(3), -410.0, "WEG Lindenstraße 12", "Hausgeld", "Wohnen\\Hausgeld")
            t("priv.giro", day(5), -96.0, "Versicherung Nord", "Privathaftpflicht und Hausrat", "Versicherungen\\Haftpflicht")
            t("priv.giro", day(5), -612.0, "Krankenkasse", "Beitrag", "Versicherungen\\Krankenversicherung")
            t("priv.giro", day(8), -168.0 - (mo % 3) * 22.0, "Stadtwerke", "Strom und Wärme", "Wohnen\\Nebenkosten")
            for n, amount in ((6, -142.30), (13, -167.85), (20, -121.40), (27, -188.10)):
                t("priv.giro", day(n), amount - (mo % 4) * 3.5, "Biomarkt", "Einkauf", "Lebenshaltung\\Lebensmittel")
            t("priv.giro", day(11), -58.0 - (mo % 5) * 9.0, "Trattoria", "Abendessen", "Lebenshaltung\\Restaurant")
            t("priv.giro", day(17), -89.0, "Verkehrsbetriebe", "Monatskarte", "Lebenshaltung\\Mobilität")
            t("priv.giro", day(22), -64.0 - (mo % 3) * 15.0, "Kino und Konzert", "Tickets", "Lebenshaltung\\Freizeit")
            t("priv.giro", day(15), -48.90 - (mo % 4) * 11.0, "Baumarkt", "Werkzeug", "")              # without a category: to assign
            if mo in (4, 8):
                t("priv.giro", day(19), -1850.0, "Reisebüro", "Urlaub", "")
            if mo == 6:                                                                                  # a yearly contribution into Alpha GbR
                t("priv.giro", day(20), -10000.0, "Alpha GbR", "Einlage", "Umbuchung", ALPHA_IBAN)
                t("ga.kk", day(20), 10000.0, "Gesellschafter A", "Einlage", "Umbuchung", GIRO_IBAN)
            # Beta GbR: rent, upkeep, its two loans
            t("gb.kk", day(3), 14200.0, "Mieter Bahnhofstraße", "Miete", "Vermietung\\Bahnhofstraße\\Mieteinnahmen")
            t("gb.kk", day(9), -1350.0, "Hausverwaltung", "Bewirtschaftung", "Vermietung\\Bahnhofstraße\\Bewirtschaftung")
            for key, iban, paid, interest in (("gb.d1", BETA_LOAN1_IBAN, 6400.0, 3300.0), ("gb.d2", BETA_LOAN2_IBAN, 5200.0, 4100.0)):
                t("gb.kk", day(30 if mo != 2 else 28), -paid, "Bank", "Annuität", "Umbuchung", iban)
                t(key, day(30 if mo != 2 else 28), paid, "Beta GbR", "Annuität", "Umbuchung", BETA_IBAN)
                t(key, day(30 if mo != 2 else 28), -interest, "Bank", "Zinsen", "Finanzierung\\Zinsen")
        # Alpha GbR: the property bought with a seller's loan; rent from the month after, the annuity (the rule books
        # interest and repayment into the loan) from the year after
        t("ga.immo", self.purchase, 1500000.0, "Verkäufer", "Kauf Parkweg 7")
        t("ga.vd", self.purchase, -1250000.0, "Verkäufer", "Kaufpreisstundung")
        t("ga.vd", _months_back(self.purchase, -1).replace(day=15), 50000.0, "Alpha GbR", "Anzahlung")
        for m in self._months(_months_back(self.purchase, -1)):
            t("ga.kk", date(m.year, m.month, 5), 9500.0, "Mieter Parkweg", "Miete", "Vermietung\\Parkweg\\Mieteinnahmen")
            t("ga.kk", date(m.year, m.month, 6), -800.0, "Hausverwaltung", "Bewirtschaftung", "Vermietung\\Parkweg\\Bewirtschaftung")
        for m in self._months(self.first_annuity):
            t("ga.kk", m, -6000.0, "Verkäufer", ANNUITY_TEXT, "Umbuchung", SELLER_IBAN)
        # balances now: what was there two years ago and everything since
        opening = {"priv.giro": 9000.0, "priv.tr": 2500.0, "priv.darl": -318000.0, "ga.kk": 25000.0, "gb.kk": 18000.0,
                   "gb.d1": -1180000.0, "gb.d2": -1560000.0}
        self.balances = dict(opening)
        key_of = {uid(k): k for k in self._keys()}
        for x in self.txs:
            key = key_of[x["accountUuid"]]
            if key in opening:
                self.balances[key] = round(self.balances[key] + x["amount"], 2)
        self.balances.update({"priv.depot": round(sum(p["quantity"] * p["marketPrice"] for p in self.PORTFOLIO), 2), "priv.immo": 465000.0, "priv.bet.ga": 0.0, "priv.bet.gb": 0.0,
                              "ga.vd": 0.0, "ga.kap.a": -120000.0, "ga.kap.b": -120000.0, "gb.immo": 2900000.0, "gb.kap.a": -60000.0, "gb.kap.b": -60000.0})
        for key in ("ga.vd", "ga.immo"):                       # what the purchase brought
            self.balances[key] = round(sum(x["amount"] for x in self.txs if x["accountUuid"] == uid(key)), 2)
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
                ("priv.bet.ga", "Beteiligung Alpha GbR", 3, "Offline-Konto", False, None, "", False),
                ("priv.bet.gb", "Beteiligung Beta GbR", 3, "Offline-Konto", False, None, "", False),
                ("priv.verb", "Verbindlichkeiten", 2, "Kontengruppe", True, None, "", False),
                ("priv.darl", "Darlehen Lindenstraße", 3, "Darlehenskonto", False, LOAN_IBAN, "50010517", False),
                ("ga", "Alpha GbR", 1, "Kontengruppe", True, None, "", False),
                ("ga.liq", "Liquidität", 2, "Kontengruppe", True, None, "", False),
                ("ga.kk", "Stadtbank Geschäftskonto", 3, "Girokonto", False, ALPHA_IBAN, "70150000", False),
                ("ga.anl", "Anlagen", 2, "Kontengruppe", True, None, "", False),
                ("ga.immo", "Immobilie Parkweg", 3, "Festgeldanlage", False, None, "", False),
                ("ga.verb", "Verbindlichkeiten", 2, "Kontengruppe", True, None, "", False),
                ("ga.vd", "Kaufpreisdarlehen", 3, "Darlehenskonto", False, None, "", False),
                ("ga.kap.a", "Kapitalkonto A", 3, "Darlehenskonto", False, None, "", False),
                ("ga.kap.b", "Kapitalkonto B", 3, "Darlehenskonto", False, None, "", False),
                ("gb", "Beta GbR", 1, "Kontengruppe", True, None, "", False),
                ("gb.liq", "Liquidität", 2, "Kontengruppe", True, None, "", False),
                ("gb.kk", "Stadtbank Geschäftskonto", 3, "Girokonto", False, BETA_IBAN, "70150000", False),
                ("gb.anl", "Anlagen", 2, "Kontengruppe", True, None, "", False),
                ("gb.immo", "Immobilie Bahnhofstraße", 3, "Festgeldanlage", False, None, "", False),
                ("gb.verb", "Verbindlichkeiten", 2, "Kontengruppe", True, None, "", False),
                ("gb.d1", "Darlehen Bahnhofstraße I", 3, "Darlehenskonto", False, BETA_LOAN1_IBAN, "50010517", False),
                ("gb.d2", "Darlehen Bahnhofstraße II", 3, "Darlehenskonto", False, BETA_LOAN2_IBAN, "50010517", False),
                ("gb.kap.a", "Kapitalkonto A", 3, "Darlehenskonto", False, None, "", False),
                ("gb.kap.b", "Kapitalkonto B", 3, "Darlehenskonto", False, None, "", False)]

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
        (MoneyMoney does not export them) -- a savings plan of 1,000 a month and a market that mostly rose."""
        now, months = self.balances["priv.depot"], {}
        for k in range(1, 25):
            m = _months_back(self.today, k)
            months["%04d-%02d" % (m.year, m.month)] = round((now - 1000.0 * k) / 1.006 ** k + (1400.0 if k % 5 == 2 else -900.0 if k % 7 == 3 else 0.0), 2)
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

    def set_transaction(self, tx_id: int, category: Optional[str] = None, comment: Optional[str] = None) -> None:
        self.written.append({"method": "setTransaction", "args": {"id": int(tx_id)}})
        if self.dry_run:
            return
        with self.world.lock:
            for x in self.world.txs:
                if x["id"] == int(tx_id):
                    if comment is not None:
                        x["comment"] = comment
                    if category is not None:
                        path = self._path(category)
                        x["category"], x["categoryPath"] = path.split("\\")[-1], path

    def append_comment(self, tx_id: int, account: str, day: date, text: str) -> bool:
        with self.world.lock:
            x = next((x for x in self.world.txs if x["id"] == int(tx_id) and x["accountUuid"] == account), None)
            if x is None or text in (x.get("comment") or ""):
                return False
            if not self.dry_run:
                x["comment"] = ((x.get("comment") or "") + "\n" + text).strip()
            return True

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
    area_of = {"priv": uid("priv"), "ga": uid("ga"), "gb": uid("gb")}
    mapping = {u(k, name): {"area": area_of[k.split(".")[0]], "position": "", "confirmed": True} for k, name, _, _, group, *_ in World._layout() if not group}
    cfg = {
        "dry_run": False, "notifications": False,
        "schedule": {"interval_minutes": 30, "automatic": False},
        "areas": [{"id": uid("priv"), "name": "Privat", "kind": "private", "main_area": True, "accounts": [u("priv", "Privat")]},
                  {"id": uid("ga"), "name": "Alpha GbR", "kind": "company", "share": 0.5, "accounts": [u("ga", "Alpha GbR")]},
                  {"id": uid("gb"), "name": "Beta GbR", "kind": "company", "share": 0.4, "accounts": [u("gb", "Beta GbR")]}],
        "loans": [{"name": "Kaufpreisdarlehen", "loan_account": u("ga.vd", "Kaufpreisdarlehen"), "source_accounts": [u("ga.kk", "Stadtbank Geschäftskonto")],
                   "detection": {"counter_iban": SELLER_IBAN}, "from_date": world.first_annuity.isoformat(),
                   "interest": {"model": "yearly_base", "rate_list": [{"from_date": purchase.isoformat(), "percent": 3.0}], "booking_day": "with_payment"},
                   "booking": {"counterparty": "Verkäufer", "category_repayment": "Umbuchung", "category_interest": "Finanzierung\\Zinsen"}}],
        "companies": [{"area": uid("ga"), "participation": u("priv.bet.ga", "Beteiligung Alpha GbR"), "retroactive_from": "all"},
                      {"area": uid("gb"), "participation": u("priv.bet.gb", "Beteiligung Beta GbR"), "retroactive_from": "all"}],
        "balance": {"months_back": 24, "illiquid_roles": ["participations"], "illiquid_accounts": [u("priv.darl", "Darlehen Lindenstraße")],
                    "accounts_mapping": mapping},
        "cashflow": {"category_to_account": {"Investments\\ETF": u("priv.depot", "Depot")}},
        "real_estate": [{"id": "im1", "name": "Parkweg", "area": uid("ga"), "category": "Vermietung\\Parkweg", "property_account": u("ga.immo", "Immobilie Parkweg"),
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
        "receipts": {"folder": receipts_dir, "subfolder": "{year}/{entity}", "write_comment": False, "folder_confirmed": True},
        "ui": {k: copy.deepcopy(ui_real[k]) for k in ("language", "lock_minutes", "remote_read_only", "theme", "port") if k in ui_real},
        "assistant": copy.deepcopy((real or {}).get("assistant") or {}),
    }
    cfg["ui"]["offline_copy"] = False                  # nothing of the demo is kept on a device for its offline view
    return cfg

