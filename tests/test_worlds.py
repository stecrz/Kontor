"""Random worlds: one to three private areas (you, a partner, the children) and up to four companies, owned by them and by
each other in odd shares (a holding owning a company, 0.5 %, a third, 74.9 %, all of it) -- with bank and offline accounts,
and months of bookings between all of them: salaries and expenses, transfers within an area and between any two areas
(over a month end, a year end, days apart), contributions booked against a stake and a capital account, loans between the
areas and from and to a friend, interest, value changes. Amounts come from a small set on purpose (the same amount many
times, a cent, a large one) and days lean towards the edges of months and years -- the cases where bookings could be
confused with each other.

For every world, in every area and every month, without knowing the expected rows in advance:

  * both checks add up (net worth and cash explained to the cent; the only reason allowed: money in transit),
  * income and expenses are exactly the categorised bookings -- never more (a transfer taken for income), never less,
  * nothing is left unclear: every booking without a category has its counterpart (by IBAN, by Kontor's mark, by amount),
  * changes in value are exactly the value changes made -- an offline booking whose payment was not found would show here,
  * the net worth moves by what was booked in the area.

A failure names its world ("seed …"); KONTOR_FUZZ_SEED=<number> builds it again. Below them: what random worlds found, built
by hand, and a fixed list of single special cases (a cent, nearly 100 million, 0.00, two alike on one day, a stake going
negative …), each on every kind of day and between every kind of two areas -- on every run. All names and amounts are made up."""
import datetime
import os
import random
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from model import Ledger, accounts_from_export, tx_from_export   # noqa: E402
import core                                                         # noqa: E402
import report                                                       # noqa: E402
import fixtures as F                                                # noqa: E402

TODAY = date(2026, 6, 20)
START = date(2025, 11, 1)
PRIVATE = ["Privat", "Partnerin", "Kinder"]
COMPANY = ["Alpha GmbH", "Beta GbR", "Gamma KG", "Delta GmbH"]
SHARES = [1.0, 0.5, 1 / 3, 0.749, 0.005, 0.25]
AMOUNTS = [12.5, 250.0, 250.0, 999.99, 1500.0, 0.01, 4000.0, 123456.78]
INCOME = {"Privat": "Gehalt", "Partnerin": "Gehalt", "Kinder": "Gehalt"}     # companies: "Miete"
EXPENSE = ["Lebensmittel", "Wohnen\\Miete"]


def edge_day(rnd, start=START, end=TODAY):
    """A day, leaning towards the edges: the last and first days of months, the year end, today."""
    if rnd.random() < 0.45:
        days = [d for d in (start + timedelta(n) for n in range((end - start).days + 1))
                if d.day in (1, 28, 29, 30, 31) or (d.month, d.day) in ((12, 31), (1, 1)) or d == end]
        return rnd.choice(days)
    return start + timedelta(rnd.randrange((end - start).days + 1))


class World:
    """Areas, accounts and bookings -- built at random from a seed."""

    def __init__(self, seed, privates=None, companies=None, owners=None):
        """A world at random from a seed -- or (privates given) just these areas and owners, without bookings."""
        rnd = self.rnd = random.Random(seed)
        self.accounts = {}              # key -> (name, area, role, iban, kind)
        self.uid = {}                   # key (or an area) -> its id in MoneyMoney
        self.txs = []                   # (id, key, day, amount, extra)
        self.income = {}                # area -> categorised income and expenses booked
        self.value = {}                 # area -> value changes booked
        self.n_iban = 10
        self.between = {}               # (two areas, cents) -> days of payments between them
        self.privates = privates or PRIVATE[:rnd.choice([1, 1, 2, 3])]
        self.companies = (companies or []) if privates else rnd.sample(COMPANY, rnd.choice([0, 1, 1, 2, 2, 3, 4]))
        self.areas = self.privates + self.companies
        for a in self.areas:
            self.account(a, "bank", "Konto " + a, "cash", bank=True)
            if a in self.privates and rnd.random() < 0.5:
                self.account(a, "tg", "Tagesgeld " + a, "cash", bank=True)
            if rnd.random() < 0.4:
                self.account(a, "paypal", "PayPal " + a, "cash")          # cash, but no IBAN: found by amount and category only
        # who owns whom: each company by one or two owners -- you, another private area, or a company named before it
        self.owners = {}
        for i, c in enumerate(self.companies):
            pool = self.privates + self.companies[:i]
            self.owners[c] = dict((owners or {}).get(c) or {o: rnd.choice(SHARES) for o in rnd.sample(pool, min(len(pool), rnd.choice([1, 1, 2])))})
            for o in self.owners[c]:
                self.account(o, "stake:" + c, "Beteiligung " + c, "participations")
                self.account(c, "kap:" + o, "Kapitalkonto " + o, "liabilities")
        # the participation Kontor keeps (Booking rules): one per company, held by its first owner -- money between the two
        # without a booking against an account counts into it, and what it is not (yet) worth more is its change in value
        self.holder = {c: sorted(self.owners[c])[0] for c in self.companies}
        self.account(self.privates[0], "kredit", "Darlehen von Freund", "liabilities")
        self.account(self.privates[0], "ford", "Darlehen an Freund", "receivables")
        self.account(self.privates[0], "immo", "Wohnung", "real_estate")
        if privates:
            return
        for a in self.areas:            # money to start with, before anything happens
            self.add(a, "bank", START, rnd.choice([5000.0, 250000.0]), cat=self.cat_in(a), counts=True)
        for _ in range(rnd.randint(15, 70)):
            self.event()

    # -- accounts and bookings ---------------------------------------------------------------------------------------------
    def account(self, area, key, name, role, bank=False):
        k = area + "|" + key
        if k not in self.accounts:
            iban = None
            if bank:
                self.n_iban += 1
                iban = "DE%02d" % self.n_iban
            self.accounts[k] = (name, area, role, iban, "bank" if bank else "offline")
            self.uid[k] = F.uid("world/" + k)
        return k

    def iban(self, area, key="bank"):
        return self.accounts[area + "|" + key][3]

    def add(self, area, key, day, amount, counts=False, value=False, to=None, **extra):
        k = area + "|" + key
        assert k in self.accounts, k
        tid = len(self.txs) + 1
        self.txs.append((tid, k, day, round(amount, 2), extra))
        if to is not None and self.holder.get(to) == area:          # money to (from) a company whose participation is kept here
            value = True
        if counts:
            self.income[area] = round(self.income.get(area, 0.0) + round(amount, 2), 2)
        if value:
            self.value[area] = round(self.value.get(area, 0.0) + round(amount, 2), 2)
        return tid

    def cat_in(self, area):
        return INCOME.get(area, "Miete")

    def amount(self):
        return self.rnd.choice(AMOUNTS)

    def amount_between(self, a, b, d):
        """An amount for a payment between two areas that no other payment between them has within ten days: two such payments
        at the same distance from a booking by hand could each be its other side -- Kontor leaves that open on purpose."""
        for x in self.rnd.sample(AMOUNTS, len(AMOUNTS)) + [self.odd()]:
            days = self.between.setdefault((frozenset((a, b)), int(round(x * 100))), [])
            if all(abs((d - e).days) > 10 for e in days):
                days.append(d)
                return x
        return self.odd()

    def amount_alone(self, area, key, d, x):
        """The amount -- unless another transfer of this kind in the area has it within two weeks: then one no other booking has.
        Of two such transfers a few days apart, each arriving days later, the two bookings of one day pair and the other two
        stay open, on purpose (test_cashflow: a pair on one day is not split up) -- found by a night's run, seed 224088165."""
        days = self.between.setdefault((area + "|" + key, int(round(x * 100))), [])
        if any(abs((d - e).days) <= 2 * report.PAIR_DAYS_CAT for e in days):
            return self.odd()
        days.append(d)
        return x

    def odd(self):
        """An amount no other booking has: a value change must not look like the other side of a payment."""
        return round(self.rnd.uniform(100, 9000), 2) + 0.003 * 0          # (cents at random)

    # -- what happens ------------------------------------------------------------------------------------------------------
    def event(self):
        rnd, d, x = self.rnd, edge_day(self.rnd), self.amount()
        lag = rnd.choice([0, 0, 1, 2, 3])
        later = min(d + timedelta(lag), TODAY)
        a = rnd.choice(self.areas)
        kind = rnd.randrange(13)
        if kind == 0:                                               # income
            self.add(a, "bank", d, x, cat=self.cat_in(a), counts=True)
        elif kind == 1:                                             # an expense
            self.add(a, "bank", d, -x, cat=rnd.choice(EXPENSE), counts=True)
        elif kind == 2 and a + "|tg" in self.accounts:              # to the area's own savings account (and back)
            s = rnd.choice([1, -1])
            self.add(a, "bank", d, -s * x, iban=self.iban(a, "tg"), cat=rnd.choice(["Umbuchung", ""]))
            self.add(a, "tg", later, s * x, iban=self.iban(a))
        elif kind == 3 and len(self.areas) > 1:                     # between two areas, bank to bank
            b = rnd.choice([o for o in self.areas if o != a])
            x = self.amount_between(a, b, d)
            self.add(a, "bank", d, -x, iban=self.iban(b), cat=rnd.choice(["Umbuchung", ""]), to=b)
            self.add(b, "bank", min(d + timedelta(rnd.choice([0, 1, 3, 5])), TODAY), x, iban=self.iban(a), cat=rnd.choice(["Umbuchung", ""]), to=a)
        elif kind == 4 and self.companies:                          # a contribution into a company, booked on the stake (and the capital account)
            c = rnd.choice(self.companies)
            o = rnd.choice(sorted(self.owners[c]))
            x = self.amount_between(o, c, d)
            self.add(o, "bank", d, -x, iban=self.iban(c), cat=rnd.choice(["Umbuchung", ""]), purpose="Einlage " + c)
            self.add(o, "stake:" + c, min(d + timedelta(rnd.choice([0, 0, 1, 2])), TODAY), x, purpose="Einlage " + c)
            self.add(c, "bank", later, x, iban=self.iban(o), purpose="Einlage")
            if rnd.random() < 0.6:
                self.add(c, "kap:" + o, rnd.choice([d, later]), -x, purpose="Einlage")      # on the day paid (mirrored) or arrived
        elif kind == 5 and len(self.areas) > 1:                     # a loan between two areas, booked on both sides; part back later
            b = rnd.choice([o for o in self.areas if o != a])
            self.account(a, "dar:" + b, "Darlehen an " + b, "receivables")
            self.account(b, "dar:" + a, "Darlehen von " + a, "liabilities")
            back = min(d + timedelta(rnd.randint(20, 60)), TODAY)
            x = self.amount_between(a, b, d)
            for day, y in ((d, x), (back, -self.amount_between(a, b, back))):
                if day > TODAY or (y < 0 and rnd.random() < 0.5):
                    continue
                arrive = min(day + timedelta(rnd.choice([0, 1, 2])), TODAY)
                self.add(a, "bank", day, -y, iban=self.iban(b), purpose="Darlehen")
                self.add(a, "dar:" + b, day, y, purpose="Darlehen " + b)
                self.add(b, "bank", arrive, y, iban=self.iban(a), purpose="Darlehen")
                self.add(b, "dar:" + a, rnd.choice([day, arrive]), -y, purpose="Darlehen " + a)
        elif kind == 6:                                             # a friend: lent to or borrowed from, booked by hand days later
            p = self.privates[0]
            if rnd.random() < 0.5:
                self.add(p, "bank", d, -x, name="Freund")
                self.add(p, "ford", later, x, name="Freund")
            else:
                self.add(p, "bank", d, x, name="Freund")
                self.add(p, "kredit", later, -x, name="Freund")
        elif kind == 7:                                             # interest on the friend's loan: a cost, booked by hand
            p, i = self.privates[0], round(x * 0.03, 2) or 0.01
            self.add(p, "kredit", d, -i, purpose="Zinsen")
        elif kind == 8:                                             # the flat changes in value (by hand, an amount nothing else has)
            self.add(self.privates[0], "immo", d, rnd.choice([1, -1]) * self.odd(), purpose="Wertanpassung", value=True)
        elif kind == 9 and self.companies:                          # Kontor's value adjustment of a stake
            c = rnd.choice(self.companies)
            o = rnd.choice(sorted(self.owners[c]))
            self.add(o, "stake:" + c, d, rnd.choice([1, -1]) * x, purpose="Wertanpassung · #kontor-wert-%s-%d" % (d.strftime("%Y%m%d"), len(self.txs)),
                     value=True)
        elif kind == 10:                                            # an expense in a company or a second income
            self.add(a, "bank", d, -x if a in self.companies else x, cat=rnd.choice(EXPENSE) if a in self.companies else self.cat_in(a), counts=True)
        elif kind == 11 and a + "|paypal" in self.accounts:         # to PayPal and back: both sides "Umbuchung", no IBAN, a week apart at most
            s = rnd.choice([1, -1])
            x = self.amount_alone(a, "paypal", d, x)
            self.add(a, "bank", d, -s * x, cat="Umbuchung", name="PayPal")
            self.add(a, "paypal", min(d + timedelta(rnd.choice([0, 1, 3, 5, 7])), TODAY), s * x, cat="Umbuchung", name="PayPal")
        elif kind == 12 and len(self.areas) > 1:                    # rent paid to another area: income there, an expense here
            b = rnd.choice([o for o in self.areas if o != a])
            self.add(a, "bank", d, -x, iban=self.iban(b), cat="Miete", purpose="Miete", counts=True)
            self.add(b, "bank", later, x, iban=self.iban(a), cat="Miete", purpose="Miete", counts=True)

    # -- Kontor's view of it -----------------------------------------------------------------------------------------------
    def ledger(self):
        raw = []
        for area in self.areas:
            self.uid[area] = F.uid("world-area/" + area)
            raw.append({"uuid": self.uid[area], "name": area, "indentation": 0, "type": "Kontengruppe", "group": True, "balance": [[0, "EUR"]], "currency": "EUR"})
            for k, (name, a, role, iban, kind) in self.accounts.items():
                if a != area:
                    continue
                bal = round(sum(e[3] for e in self.txs if e[1] == k), 2)
                raw.append({"uuid": self.uid[k], "name": name, "indentation": 1, "type": "Offline-Konto" if kind == "offline" else "Girokonto", "group": False,
                            "balance": [[bal, "EUR"]], "currency": "EUR", "iban": iban, "accountNumber": iban or "",
                            "bankCode": "" if kind == "offline" else "10000000", "portfolio": False,
                            "refreshTimestamp": None if kind == "offline" else datetime.datetime(2026, 6, 1)})
        rows = []
        for i, k, day, amount, extra in self.txs:
            extra = dict(extra)
            rows.append({"id": i, "accountUuid": self.uid[k], "bookingDate": datetime.datetime(day.year, day.month, day.day, 12), "amount": amount,
                         "currency": "EUR", "name": extra.pop("name", "x"), "purpose": extra.pop("purpose", ""), "categoryPath": extra.pop("cat", ""),
                         "accountNumber": extra.pop("iban", ""), "booked": True, "comment": ""})
        return Ledger(accounts_from_export(raw), tx_from_export(rows))

    def config(self):
        roles = {self.uid[k]: v[2] for k, v in self.accounts.items()}
        areas = [{"id": self.uid[a], "name": a, "kind": "private" if a in self.privates else "company", "main_area": a == self.privates[0],
                  "accounts": [self.uid[a]], **({} if a in self.privates else {"share": round(sum(self.owners[a].values()) / len(self.owners[a]), 4)})}
                 for a in self.areas]
        companies = [{"area": self.uid[c], "participation": self.uid[self.holder[c] + "|stake:" + c]} for c in self.companies]
        return core.merged_config({"balance": {"roles": roles}, "areas": areas, "companies": companies}), roles

    def datasets(self):
        led = self.ledger()
        config, roles = self.config()
        return {b["name"]: report.build_dataset(led, config, {}, TODAY, b, dict(roles)) for b in core.bereiche_for(led, config)}

    def describe(self):
        return "%s; owners %s" % (", ".join(self.areas), {c: {o: round(s, 4) for o, s in v.items()} for c, v in self.owners.items()})


def section_total(ds, *names):
    return round(sum(v for s in ds["cashflow"]["sections"] if s["name"] in names for z in s["rows"] for v in z["amounts"].values()), 2)


class RandomWorlds(unittest.TestCase):
    def check(self, w, data, label):
        self.assertEqual(sorted(data), sorted(w.areas), label)
        for area, ds in data.items():
            at = "%s · %s" % (label, area)
            for m, u in ds["cashflow"]["reconciliation"].items():
                for check, why in (("unexplained", "reasons"), ("diff_cash", "reasons_cash")):
                    reasons = {g[0] for g in u[why]}
                    self.assertTrue(abs(u[check]) < 0.005 or (reasons and reasons <= {"ue_unterwegs"}), "%s %s: %s=%s %s" % (at, m, check, u[check], u[why]))
            self.assertAlmostEqual(section_total(ds, "income", "expenses"), w.income.get(area, 0.0), 2, at + ": income and expenses")
            unclear = {z["row"]: {m: v for m, v in z["amounts"].items() if v} for s in ds["cashflow"]["sections"] if s["name"] == "unclear"
                       for z in s["rows"] if any(z["amounts"].values())}
            self.assertEqual(unclear, {}, at + ": unclear")
            vals = {z["row"]: sum(z["amounts"].values()) for s in ds["cashflow"]["sections"] if s["name"] == "valuation" for z in s["rows"]
                    if abs(sum(z["amounts"].values())) >= 0.005}
            self.assertAlmostEqual(round(sum(vals.values()), 2), w.value.get(area, 0.0), 2, "%s: changes in value %s" % (at, vals))
            nw = ds["balance"]["net_worth"]
            booked = round(sum(e[3] for e in w.txs if w.accounts[e[1]][1] == area), 2)
            self.assertAlmostEqual(nw[max(nw)], booked, 2, at + ": net worth")

    def test_found_worlds(self):
        """What random worlds found (3.16.58), each built by hand: bookings that two payments could claim, or that a payment of
        the same amount nearby took first."""
        d = date(2026, 3, 28)
        # two transfers of 1500 from the partner on one day, one of them a loan booked on both sides (seed 144)
        w = World(0, ["Privat", "Partnerin"])
        for key, purpose in (("bank", ""), ("bank", "Darlehen")):
            w.add("Partnerin", key, d, -1500.0, iban=w.iban("Privat"), purpose=purpose)
            w.add("Privat", key, d + timedelta(2), 1500.0, iban=w.iban("Partnerin"), purpose=purpose)
        w.account("Partnerin", "dar:Privat", "Darlehen an Privat", "receivables"); w.account("Privat", "dar:Partnerin", "Darlehen von Partnerin", "liabilities")
        w.add("Partnerin", "dar:Privat", d, 1500.0, purpose="Darlehen Privat"); w.add("Privat", "dar:Partnerin", d + timedelta(2), -1500.0, purpose="Darlehen Partnerin")
        self.check(w, w.datasets(), "two transfers, one a loan")
        # into a company on one day: 250 as a contribution (capital account) and 250 as a loan (seed 375)
        w = World(0, ["Privat"], ["Beta GbR"], {"Beta GbR": {"Privat": 0.5}})
        w.account("Beta GbR", "dar:Privat", "Darlehen von Privat", "liabilities"); w.account("Privat", "dar:Beta GbR", "Darlehen an Beta GbR", "receivables")
        for other, purpose in (("kap:Privat", "Einlage"), ("dar:Privat", "Darlehen")):
            w.add("Privat", "bank", d, -250.0, iban=w.iban("Beta GbR"), purpose=purpose)
            w.add("Privat", "stake:Beta GbR" if other.startswith("kap") else "dar:Beta GbR", d, 250.0, purpose=purpose + " Beta GbR")
            w.add("Beta GbR", "bank", d, 250.0, iban=w.iban("Privat"), purpose=purpose)
            w.add("Beta GbR", other, d, -250.0, purpose=purpose)
        self.check(w, w.datasets(), "contribution and loan alike")
        # two repayments of 125 on one day, each booked on the loan on both sides (seed 396)
        w = World(0, ["Privat"], ["Gamma KG"], {"Gamma KG": {"Privat": 0.749}})
        w.account("Privat", "dar:Gamma KG", "Darlehen von Gamma KG", "liabilities"); w.account("Gamma KG", "dar:Privat", "Darlehen an Privat", "receivables")
        for _ in range(2):
            w.add("Privat", "bank", TODAY, -125.0, iban=w.iban("Gamma KG"), purpose="Darlehen"); w.add("Privat", "dar:Gamma KG", TODAY, 125.0, purpose="Darlehen Gamma KG")
            w.add("Gamma KG", "bank", TODAY, 125.0, iban=w.iban("Privat"), purpose="Darlehen"); w.add("Gamma KG", "dar:Privat", TODAY, -125.0, purpose="Darlehen Privat")
        self.check(w, w.datasets(), "two repayments alike")
        # borrowed 250 from a friend (booked three days later) next to a loan of 250 from the partner, booked on "Darlehen von
        # Partnerin" the same day: the friend's payment must not take the partner's loan booking (seed 1006)
        w = World(0, ["Privat", "Partnerin"])
        w.account("Privat", "dar:Partnerin", "Darlehen von Partnerin", "liabilities"); w.account("Partnerin", "dar:Privat", "Darlehen an Privat", "receivables")
        w.add("Privat", "bank", date(2026, 3, 30), 250.0, name="Freund"); w.add("Privat", "kredit", date(2026, 4, 2), -250.0, name="Freund")
        w.add("Privat", "bank", date(2026, 3, 31), 250.0, iban=w.iban("Partnerin"), purpose="Darlehen")
        w.add("Privat", "dar:Partnerin", date(2026, 3, 31), -250.0, purpose="Darlehen Partnerin")
        w.add("Partnerin", "bank", date(2026, 3, 31), -250.0, iban=w.iban("Privat"), purpose="Darlehen")
        w.add("Partnerin", "dar:Privat", date(2026, 3, 31), 250.0, purpose="Darlehen Privat")
        data = w.datasets()
        self.check(w, data, "friend and partner")
        rows = {z["row"]: round(sum(z["amounts"].values()), 2) for s in data["Privat"]["cashflow"]["sections"] for z in s["rows"] if any(z["amounts"].values())}
        self.assertEqual(rows, {"Darlehen von Freund / Aufnahme": 250.0, "Einlage/Entnahme Partnerin / Darlehen von Partnerin / Aufnahme": 250.0})

    def test_booking_kept_for_a_payment_to_another_area(self):
        """A booking by hand in an account of another area waits for the payment to that area -- but only where that payment is
        as close as any other of the amount, the area's name stands as a word, and the payment pays for nothing (3.16.58)."""
        d = date(2026, 3, 10)
        rows = lambda data, area: {z["row"]: round(sum(z["amounts"].values()), 2) for s in data[area]["cashflow"]["sections"]
                                   for z in s["rows"] if any(z["amounts"].values())}
        # the friend's payment and the partner's loan booking both with the category "Umbuchung": the same as without
        w = World(0, ["Privat", "Partnerin"])
        w.account("Privat", "dar:Partnerin", "Darlehen von Partnerin", "liabilities")
        w.add("Privat", "bank", date(2026, 3, 30), 250.0, name="Freund", cat="Umbuchung"); w.add("Privat", "kredit", date(2026, 4, 2), -250.0, name="Freund")
        w.add("Privat", "bank", date(2026, 3, 31), 250.0, iban=w.iban("Partnerin"), purpose="Darlehen")
        w.add("Privat", "dar:Partnerin", date(2026, 3, 31), -250.0, purpose="Darlehen Partnerin", cat="Umbuchung")
        w.add("Partnerin", "bank", date(2026, 3, 31), -250.0, iban=w.iban("Privat"), purpose="Darlehen")
        self.assertEqual(rows(w.datasets(), "Privat"), {"Darlehen von Freund / Aufnahme": 250.0, "Einlage/Entnahme Partnerin / Darlehen von Partnerin / Aufnahme": 250.0})
        # "Privat" in "Privatdarlehen Meier" is no name of the area: Meier's loan stays Meier's, the contribution a contribution
        w = World(0, ["Privat"], ["Beta GbR"], {"Beta GbR": {"Privat": 0.5}})
        w.account("Beta GbR", "pd", "Privatdarlehen Meier", "liabilities")
        w.add("Beta GbR", "bank", d, 5000.0, iban="DE99", name="Meier"); w.add("Beta GbR", "pd", d, -5000.0, purpose="Darlehen Meier")
        w.add("Privat", "bank", d + timedelta(2), -5000.0, iban=w.iban("Beta GbR"), purpose="Einlage", to="Beta GbR")
        w.add("Beta GbR", "bank", d + timedelta(2), 5000.0, iban=w.iban("Privat"), purpose="Einlage")
        self.assertEqual(rows(w.datasets(), "Beta GbR"), {"Privatdarlehen Meier / Aufnahme": 5000.0, "Einlagen/Entnahmen Gesellschafter": 5000.0})
        # lent to the partner by PayPal on the day, booked on "Darlehen an Partnerin"; household money to her two days later:
        # the nearer payment keeps the booking
        w = World(0, ["Privat", "Partnerin"])
        w.account("Privat", "dar:Partnerin", "Darlehen an Partnerin", "receivables")
        w.add("Privat", "bank", d, 3000.0, cat="Gehalt", counts=True)
        w.add("Privat", "bank", d, -500.0, iban="DE98", name="PayPal"); w.add("Privat", "dar:Partnerin", d, 500.0, purpose="Darlehen")
        w.add("Privat", "bank", d + timedelta(2), -500.0, iban=w.iban("Partnerin"), purpose="Haushalt")
        w.add("Partnerin", "bank", d + timedelta(2), 500.0, iban=w.iban("Privat"), purpose="Haushalt")
        data = w.datasets(); self.check(w, data, "PayPal and household money")
        self.assertEqual(rows(data, "Privat")["Darlehen an Partnerin / Rückzahlung"], -500.0)
        # borrowed from the partner by PayPal, booked on "Darlehen von Partnerin"; her rent share two days later (category Miete)
        # pays for something: it claims no booking, the loan stays the loan
        w = World(0, ["Privat", "Partnerin"])
        w.account("Privat", "dar:Partnerin", "Darlehen von Partnerin", "liabilities")
        w.add("Privat", "bank", d, 800.0, iban="DE98", name="PayPal"); w.add("Privat", "dar:Partnerin", d, -800.0, purpose="Darlehen")
        w.add("Privat", "bank", d + timedelta(2), 800.0, iban=w.iban("Partnerin"), cat="Miete", purpose="Miete")
        w.add("Partnerin", "bank", d + timedelta(2), -800.0, iban=w.iban("Privat"), cat="Miete", purpose="Miete")
        self.assertEqual(rows(w.datasets(), "Privat"), {"Vermietung": 800.0, "Darlehen von Partnerin / Aufnahme": 800.0})
        # a loan from the partner booked on the day she paid (it came two days later) next to a top-up from PayPal on that day:
        # the top-up pairs with PayPal's own "transfer" (three days later), not with the loan booking (seed 2831)
        w = World(0, ["Privat", "Partnerin"])
        w.account("Privat", "paypal", "PayPal Privat", "cash"); w.account("Privat", "dar:Partnerin", "Darlehen von Partnerin", "liabilities")
        w.add("Privat", "dar:Partnerin", d, -250.0, purpose="Darlehen Partnerin")
        w.add("Privat", "bank", d, 250.0, cat="Umbuchung", name="PayPal"); w.add("Privat", "paypal", d + timedelta(3), -250.0, cat="Umbuchung", name="PayPal")
        w.add("Privat", "bank", d + timedelta(2), 250.0, iban=w.iban("Partnerin"), purpose="Darlehen")
        w.add("Partnerin", "bank", d, -250.0, iban=w.iban("Privat"), purpose="Darlehen")
        data = w.datasets(); self.check(w, data, "PayPal and a loan from the partner")
        self.assertEqual(rows(data, "Privat"), {"Einlage/Entnahme Partnerin / Darlehen von Partnerin / Aufnahme": 250.0})
        # of two payments into the company a few days apart, the nearer one takes the booking on the capital account -- day by
        # day, not in steps of three (seed 70)
        w = World(0, ["Privat"], ["Delta GmbH"], {"Delta GmbH": {"Privat": 1.0}})
        w.account("Delta GmbH", "dar:Privat", "Darlehen von Privat", "liabilities")
        w.add("Delta GmbH", "bank", d, 12.5, iban=w.iban("Privat"), purpose="Einlage")
        w.add("Delta GmbH", "dar:Privat", d + timedelta(3), -12.5, purpose="Darlehen Privat")
        w.add("Delta GmbH", "bank", d + timedelta(4), 12.5, iban=w.iban("Privat"), purpose="Darlehen")
        data = w.datasets(); self.check(w, data, "the nearer payment")
        self.assertEqual(rows(data, "Delta GmbH"), {"Einlagen/Entnahmen Gesellschafter": 12.5, "Einlage/Entnahme Privat / Darlehen von Privat": 12.5})
        # borrowed 12.50 from a friend (booked three days later) between two top-ups from PayPal of 12.50 on New Year's Day that
        # PayPal books five and seven days later: three pairs, nothing left over (of two choices worth the same, more pairs)
        w = World(0, ["Privat"]); w.account("Privat", "paypal", "PayPal Privat", "cash")
        w.add("Privat", "bank", date(2025, 12, 29), 12.5, name="Freund"); w.add("Privat", "kredit", date(2026, 1, 1), -12.5, name="Freund")
        for later in (7, 5):
            w.add("Privat", "bank", date(2026, 1, 1), 12.5, cat="Umbuchung", name="PayPal")
            w.add("Privat", "paypal", date(2026, 1, 1) + timedelta(later), -12.5, cat="Umbuchung", name="PayPal")
        self.check(w, w.datasets(), "friend between two top-ups")
        self.assertEqual(rows(data, "Delta GmbH"), {"Einlagen/Entnahmen Gesellschafter": 12.5, "Einlage/Entnahme Privat / Darlehen von Privat": 12.5})
        # 250 from the partner by transfer and 250 in cash on one day, both booked by hand on "Darlehen von Partnerin": one booking
        # is kept for her transfer, the other pairs with the cash by amount -- two loans taken up (3.16.58 to 3.16.99 kept both:
        # the cash became income "without category", the second booking a change in value)
        for cat in ("", "Umbuchung"):
            w = World(0, ["Privat", "Partnerin"])
            w.account("Privat", "dar:Partnerin", "Darlehen von Partnerin", "liabilities")
            w.add("Privat", "bank", d, 250.0, iban=w.iban("Partnerin"), purpose="Darlehen", cat=cat)
            w.add("Partnerin", "bank", d, -250.0, iban=w.iban("Privat"), purpose="Darlehen")
            w.add("Privat", "bank", d, 250.0, name="Bareinzahlung", cat=cat)
            w.add("Privat", "dar:Partnerin", d, -250.0, purpose="Darlehen Partnerin"); w.add("Privat", "dar:Partnerin", d, -250.0, purpose="Darlehen Partnerin bar")
            data = w.datasets(); self.check(w, data, "transfer and cash on one day (%s)" % (cat or "no category"))
            self.assertEqual(rows(data, "Privat"), {"Darlehen von Partnerin / Aufnahme": 250.0, "Einlage/Entnahme Partnerin / Darlehen von Partnerin / Aufnahme": 250.0}, cat)
        # ... and only one payment, from her, beside two bookings on one day: one of them is hers, the other stays what it is
        # (a change in value of that account -- nothing to pair it with)
        w = World(0, ["Privat", "Partnerin"])
        w.account("Privat", "dar:Partnerin", "Darlehen von Partnerin", "liabilities")
        w.add("Privat", "bank", d, 250.0, iban=w.iban("Partnerin"), purpose="Darlehen"); w.add("Partnerin", "bank", d, -250.0, iban=w.iban("Privat"), purpose="Darlehen")
        w.add("Privat", "dar:Partnerin", d, -250.0, purpose="Darlehen Partnerin"); w.add("Privat", "dar:Partnerin", d, -250.0, purpose="Darlehen Partnerin")
        self.assertEqual(rows(w.datasets(), "Privat"), {"Einlage/Entnahme Partnerin / Darlehen von Partnerin / Aufnahme": 250.0, "Darlehen von Partnerin": -250.0})

    def test_random_worlds(self):
        for seed in F.fuzz_seeds("Welten"):
            with self.subTest(seed=seed), F.case(seed):
                w = World(seed)
                self.check(w, w.datasets(), "seed %d (%s)" % (seed, w.describe()))


# ---------------------------------------------------------------------------------------------------------------------------
# Single special cases, each in every situation: on every kind of day (the middle of a month, over a month end, over the year
# end, the first day read, today, the end of February) and between every kind of two areas (two private ones, you and the
# company whose participation Kontor keeps, you and a company you hold a stake in, a company and the company it owns) -- on
# every run, not left to chance. Each adds its bookings to a world and what they must show (as the random worlds).
# ---------------------------------------------------------------------------------------------------------------------------
DAYS = {"Monatsmitte": (date(2026, 3, 11), 0), "Monatsende": (date(2026, 3, 31), 2), "Jahresende": (date(2025, 12, 31), 2),
        "erster Tag": (START, 1), "heute": (TODAY, 0), "Ende Februar": (date(2026, 2, 28), 2)}
PAIRS = {"privat-privat": ("Privat", "Partnerin"), "an die Firma (Beteiligung geführt)": ("Partnerin", "Alpha GmbH"),
         "an die Firma (Anteil)": ("Privat", "Alpha GmbH"), "Firma an Tochter": ("Alpha GmbH", "Beta GbR")}


def edge_world():
    return World(0, ["Privat", "Partnerin"], ["Alpha GmbH", "Beta GbR"],
                 {"Alpha GmbH": {"Privat": 0.005, "Partnerin": 0.995}, "Beta GbR": {"Alpha GmbH": 1.0}})


def transfer(w, a, b, d, lag, x, **extra):
    w.add(a, "bank", d, -x, iban=w.iban(b), to=b, **extra)
    w.add(b, "bank", min(d + timedelta(lag), TODAY), x, iban=w.iban(a), to=a, **extra)


def loan(w, a, b, d, lag, x):
    w.account(a, "dar:" + b, "Darlehen an " + b, "receivables"); w.account(b, "dar:" + a, "Darlehen von " + a, "liabilities")
    later = min(d + timedelta(lag), TODAY)
    w.add(a, "bank", d, -x, iban=w.iban(b), purpose="Darlehen"); w.add(a, "dar:" + b, d, x, purpose="Darlehen " + b)
    w.add(b, "bank", later, x, iban=w.iban(a), purpose="Darlehen"); w.add(b, "dar:" + a, later, -x, purpose="Darlehen " + a)


def loan_and_cash(w, a, b, d, lag, x):
    """Lent by transfer and the same amount again in cash on the day it arrived -- both booked by hand on the loan: two loans
    taken up, not income "without category" and a change in value (3.16.58 kept both bookings for the one transfer)."""
    loan(w, a, b, d, lag, x)
    later = min(d + timedelta(lag), TODAY)
    w.add(b, "bank", later, x, name="Bareinzahlung"); w.add(b, "dar:" + a, later, -x, purpose="Darlehen " + a + " bar")


EDGES = {
    "ein Cent": lambda w, a, b, d, lag: transfer(w, a, b, d, lag, 0.01),
    "fast 100 Mio.": lambda w, a, b, d, lag: transfer(w, a, b, d, lag, 99999999.99, cat="Umbuchung"),
    "fünf Tage unterwegs": lambda w, a, b, d, lag: transfer(w, a, b, d, 5, 250.0),
    "zweimal gleich am selben Tag": lambda w, a, b, d, lag: [transfer(w, a, b, d, lag, 1500.0) for _ in range(2)],
    "hin und zurück am selben Tag": lambda w, a, b, d, lag: [transfer(w, a, b, d, 0, 400.0), transfer(w, b, a, d, 0, 400.0)],
    "Darlehen, am selben Tag zurück": lambda w, a, b, d, lag: [loan(w, a, b, d, lag, 3000.0), loan(w, b, a, d, lag, 3000.0)],
    "Darlehen über einen Cent": lambda w, a, b, d, lag: loan(w, a, b, d, lag, 0.01),
    "Darlehen überwiesen und bar am selben Tag": lambda w, a, b, d, lag: loan_and_cash(w, a, b, d, lag, 250.0),
    "Darlehen überwiesen und bar, beides Umbuchung": lambda w, a, b, d, lag: [
        loan(w, a, b, d, 0, 250.0), w.add(b, "bank", d, 250.0, name="Bareinzahlung", cat="Umbuchung"), w.add(b, "dar:" + a, d, -250.0, purpose="Darlehen " + a + " bar")],
}


def contribution(w, a, b, d, lag, x):
    """Into a company, booked on your stake and its capital account (only where a owns b)."""
    later = min(d + timedelta(lag), TODAY)
    w.add(a, "bank", d, -x, iban=w.iban(b), purpose="Einlage " + b); w.add(a, "stake:" + b, d, x, purpose="Einlage " + b)
    w.add(b, "bank", later, x, iban=w.iban(a), purpose="Einlage"); w.add(b, "kap:" + a, later, -x, purpose="Einlage")


OWN_EDGES = {          # within one area (the first of the pair)
    "Einnahme ein Cent": lambda w, a, d: w.add(a, "bank", d, 0.01, cat=w.cat_in(a), counts=True),
    "Ausgabe fast 100 Mio.": lambda w, a, d: w.add(a, "bank", d, -99999999.99, cat="Lebensmittel", counts=True),
    "Buchung über 0,00": lambda w, a, d: w.add(a, "bank", d, 0.0, cat=w.cat_in(a)),
    "Freund, drei Tage später gebucht": lambda w, a, d: [w.add("Privat", "bank", d, -250.0, name="Freund"),
                                                          w.add("Privat", "ford", min(d + timedelta(3), TODAY), 250.0, name="Freund")],
    "Zinsen ein Cent": lambda w, a, d: w.add("Privat", "kredit", d, -0.01, purpose="Zinsen"),
    "Beteiligung wird negativ": lambda w, a, d: w.add("Partnerin", "stake:Alpha GmbH", d, -5000.0,
                                                      purpose="Wertanpassung · #kontor-wert-%s-1" % d.strftime("%Y%m%d"), value=True),
}

class EdgeCases(unittest.TestCase):
    """Each special case of the list above in each situation (about 260 small worlds, a second): checked as the random worlds."""
    check = RandomWorlds.check

    def test_each_special_case_everywhere(self):
        for dname, (d, lag) in DAYS.items():
            for pname, (a, b) in PAIRS.items():
                cases = dict(EDGES, **({"Einlage auf Beteiligung und Kapitalkonto": lambda w, a, b, d, lag: contribution(w, a, b, d, lag, 777.77)}
                                       if b in COMPANY and a in edge_world().owners[b] else {}))
                for ename, fn in cases.items():
                    with self.subTest(case=ename, day=dname, between=pname):
                        w = edge_world(); fn(w, a, b, d, lag)
                        self.check(w, w.datasets(), "%s · %s · %s" % (ename, dname, pname))
            for ename, fn in OWN_EDGES.items():
                for area in ("Privat", "Alpha GmbH"):
                    with self.subTest(case=ename, day=dname, area=area):
                        w = edge_world(); fn(w, area, d)
                        self.check(w, w.datasets(), "%s · %s · %s" % (ename, dname, area))


if __name__ == "__main__":
    unittest.main()
