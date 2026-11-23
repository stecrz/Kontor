"""Random worlds for the booking rules: one or two private areas and one to three companies, each held by one of them in an
odd share (0.5 %, a third, 74.9 %, all of it); per company either Kontor's participation rule (daily or at month end, from a
day, from the start or only from now on) or an account mirror between your stake and your capital account in the company;
loans with a seller -- interest on the balance at the start of the year or on the remaining debt each month, one rate or a
change during the year, booked at month end or with the payment -- all against a simulated MoneyMoney.

A share of the worlds as before (1 Nov 2025 to 4 Nov 2026, CLASSIC); the others run on any day from 2023 to 2027 (often the
1st, a month's last day, 31 Dec, 1 Jan) over six weeks to four years. Their loans open in the first weeks or anywhere in the
first half, are booked from that day or later, and are paid regularly, every month alike, with a pause of four to fourteen
months, almost never, or with several extra payments in one month (never paid off); up to three rate changes -- on 1 January,
1 July, any 1st, any day, right after a pause, 0 % now and then. Before the rules, a company has nothing, a rent every month,
almost nothing, a month with many payments, or amounts from a cent to a million. "Buchen ab" any 1st of a month in the world.
No interest is expected where there is nothing to compute it from (the year a loan began on a yearly base, the month it began
on the remaining debt, 0 %).

Two kinds of run:

  * clean: payments come in, Kontor checks, you approve parts or all, and in the end everything (turning down and proposing
    again is in the other run: interest Kontor booked meanwhile stays as it was -- it never adjusts booked interest). Then it must all be exact: nothing left to book; every participation at share x value of its company
    (now, or at the end of last month); every mirrored booking has its counterpart; every loan payment its repayment of the
    same amount, and every month its interest -- to the cent, computed here a second time without Kontor's code (as its rule
    says: on a yearly base the rate of 1 January for the whole year); no interest or repayment more than that.
  * with your changes in MoneyMoney between the checks (as tests/test_fuzz.py, on these worlds): you delete, change, move and
    unmark Kontor's bookings, change and delete your own, enter some again. After every step: no mark twice in an account,
    Kontor only adds, only into the accounts of its rules, nothing of yours changes, what is booked on approval is what was
    shown; in the end nothing is left to book and the participations are right.

A failure names its world ("seed …"); KONTOR_FUZZ_SEED=<number> builds it again. All names, numbers and amounts are made up."""
import copy
import os
import random
import sys
import unittest
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import fixtures as F  # noqa: E402
import mm_bridge  # noqa: E402
import core  # noqa: E402
import rules  # noqa: E402
from model import TAG_RE, marks_in  # noqa: E402
from test_e2e import TODAY, MockBridge, config_for_test, patch_today, reset_mock  # noqa: E402
import test_fuzz  # noqa: E402  (the module, not its class: pytest would run test_fuzz's own cases here again)
import test_worlds as W  # noqa: E402  (the module, as test_fuzz)

START = date(2025, 11, 1)
CLASSIC = 0.3                           # share of the worlds built as before
SHARES = [1.0, 0.5, 0.3333, 0.749, 0.005, 0.4]
COMPANIES = ["Alpha GbR", "Beta GmbH", "Gamma KG"]


def exact(amount, factor, per=1):
    """amount x factor / per as a contract means it: multiplied out exactly -- the amount in cents, rate or share as written
    -- and only then rounded to the cent, half a cent up (as in commerce). Computed here without Kontor's code."""
    x = Decimal("%.2f" % amount) * Decimal(str(factor)) / Decimal(str(per))
    return float(x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def months(a, b):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def month_end(y, m):
    return (date(y, m, 28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


class World:
    """Areas, accounts, rules and the bookings already there -- at random from a seed."""

    def __init__(self, rnd, n, classic=True):
        self.rnd, self.n, self.classic = rnd, n, classic
        self.k = lambda key: "rw%d.%s" % (n, key)           # account keys of this world (F.uid needs them unique)
        self.today, self.start, self.notes = TODAY, START, []
        if not classic:                                     # the day Kontor runs on and the first day of the world
            self.today = W.some_today(rnd)
            self.start = self.today - timedelta(rnd.choice([rnd.randint(45, 180), rnd.randint(181, 700), rnd.randint(701, 1461)]))
            if rnd.random() < 0.5:
                self.start = self.start.replace(day=1)
            self.notes.append("%s..%s" % (self.start, self.today))
        today, start = self.today, self.start
        # MoneyMoney's flat list: an account belongs to the group above it with less indentation -- the stakes go under their
        # private area, the company's accounts under the company
        self.raw, priv, comp = [F.acc(self.k("root"), "Alle Konten", 0, "Kontengruppe", True)], [], []
        self.txs, self.n_iban = [], 0
        self.privates = ["Privat"] + (["Partnerin"] if rnd.random() < 0.4 else [])
        self.companies = rnd.sample(COMPANIES, rnd.randint(1, 3))
        for i, p in enumerate(self.privates):
            priv.append([F.acc(self.k("p%d" % i), p, 1, "Kontengruppe", True),
                         F.acc(self.k("p%d.giro" % i), "Giro " + p, 2, "Girokonto", balance=0.0, iban=self.iban(), bank="10000000")])
        self.co = {}
        for j, c in enumerate(self.companies):
            holder = rnd.choice(range(len(self.privates)))
            kind = rnd.choice(["rule", "rule", "mirror"])
            cs = dict(name=c, j=j, holder=holder, kind=kind, share=rnd.choice(SHARES), group=self.k("c%d" % j), kk=self.k("c%d.kk" % j),
                      immo=self.k("c%d.immo" % j), kap=self.k("c%d.kap" % j), stake=self.k("p%d.bet%d" % (holder, j)), lender=None, vd=None)
            here = [F.acc(cs["group"], c, 1, "Kontengruppe", True),
                    F.acc(cs["kk"], "Konto " + c, 2, "Girokonto", balance=0.0, iban=self.iban(), bank="10000000"),
                    F.acc(cs["immo"], "Objekt " + c, 2, "Festgeldanlage", balance=0.0),
                    F.acc(cs["kap"], "Kapitalkonto " + self.privates[holder], 2, "Darlehenskonto", balance=0.0)]
            comp.append(here)
            priv[holder].append(F.acc(cs["stake"], "Beteiligung an " + c, 2, "Offline-Konto", balance=0.0))
            self.add(cs["kk"], start, rnd.choice([20000.0, 150000.0]), "Einlage", "Startkapital")
            self.add(cs["immo"], start, rnd.choice([400000.0, 1250000.0, 99999.99]), "Kauf", "Objekt")
            if rnd.random() < 0.7:                          # a loan from the seller of the property
                cs["vd"], cs["lender"] = self.k("c%d.vd" % j), self.iban()
                here.append(F.acc(cs["vd"], "Verkäuferdarlehen " + c, 2, "Darlehenskonto", balance=0.0))
                if classic:
                    self.classic_loan(cs)
                else:
                    self.loan(cs)
            if kind == "mirror":                            # there before the mirror is set up
                days = (date(2026, 2, 3), date(2026, 6, 9)) if classic else sorted(start + timedelta(rnd.randint(0, (today - start).days)) for _ in range(2))
                for d, amt in zip(days, (-700.0, 250.0)):
                    self.add(cs["kap"], d, amt, "Ich", "früher")
            if not classic:
                self.company_life(cs)
            self.co[c] = cs
        self.raw += [a for group in priv + comp for a in group]
        self.accounts = {a["uuid"]: a for a in self.raw}
        for a in self.raw:
            if not a["group"]:
                a["balance"] = [[round(sum(t["amount"] for t in self.txs if t["accountUuid"] == a["uuid"]), 2), "EUR"]]

    def classic_loan(self, cs):
        """As before: opened in the first weeks of November 2025, booked from 2026, one rate or a change in 2026."""
        rnd = self.rnd
        cs["opened"] = START + timedelta(days=rnd.randint(0, 20))
        self.add(cs["vd"], cs["opened"], -rnd.choice([300000.0, 1000000.0, 75000.0]), "Verkäufer", "Kaufpreisstundung")
        cs["rate"] = [rnd.choice([0.5, 2.75, 3.0, 6.125])]
        cs["rate_change"] = rnd.choice([None, date(2026, 7, 1), date(2026, 1, 1)])
        if cs["rate_change"]:
            cs["rate"].append(rnd.choice([1.0, 4.5]))
        cs["rates"] = [(date(2025, 11, 1), cs["rate"][0])] + ([(cs["rate_change"], cs["rate"][1])] if cs["rate_change"] else [])
        cs["model"] = rnd.choice(["yearly_base", "remaining_debt_monthly"])
        cs["booking_day"] = rnd.choice(["ultimo", "with_payment"])
        cs["from"] = rnd.choice([date(2026, 1, 1), date(2026, 3, 15), date(2026, 8, 1)])
        cs["annuity"] = rnd.choice([1500.0, 6000.0, 333.33])
        for y, m in months(cs["from"], TODAY):              # paid on the first or a few days later; now and then a month left out
            d = date(y, m, 1) + timedelta(days=rnd.choice([0, 0, 2, 5]))
            if d <= TODAY and rnd.random() < 0.9:
                self.add(cs["kk"], d, -cs["annuity"], "Verkäufer", "Annuität", "Umbuchung", cs["lender"])

    def loan(self, cs):
        """Opened in the first weeks (or anywhere in the first half), booked from the opening or a later day; payments in one of
        the ways (test_worlds.PROFILES: regular, every month alike, a pause of months, almost none, extra payments in one month);
        up to three changes of the rate -- on 1 January, 1 July, any 1st, any day, or right after a pause; 0 % now and then."""
        rnd, today, start = self.rnd, self.today, self.start
        span = (today - start).days
        cs["opened"] = start + timedelta(days=rnd.randint(0, 20) if rnd.random() < 0.7 else rnd.randint(0, span // 2))
        lo, hi = cs["opened"], max(cs["opened"], today - timedelta(days=10))
        f = lo + timedelta(days=rnd.randint(0, (hi - lo).days))
        r = rnd.random()
        f = (f.replace(day=1) + timedelta(days=32)).replace(day=1) if r < 0.5 else f.replace(day=15) if r < 0.65 else cs["opened"] if r < 0.75 else f
        cs["from"] = f = min(max(f, start), today)
        pays = list(months(f, today))
        way = cs["pay"] = rnd.choice(["regular", "regular", "constant", "pause", "quiet", "burst"])
        principal = rnd.choice([300000.0, 1000000.0, 75000.0])
        fit = [a for a in (1500.0, 6000.0, 333.33) if a * (len(pays) + 8) <= 0.7 * principal] or [333.33]
        cs["annuity"] = rnd.choice(fit)
        if cs["annuity"] * (len(pays) + 8) > 0.7 * principal:
            principal = 1000000.0                           # never paid off: the debt stays a debt
        self.add(cs["vd"], cs["opened"], -principal, "Verkäufer", "Kaufpreisstundung")
        pause = None
        if way == "pause" and len(pays) >= 3:
            i = rnd.randint(0, len(pays) - 2)
            pause = (pays[i], pays[min(len(pays) - 1, i + rnd.randint(4, 14))])
        day = rnd.choice([1, 31])
        quiet = set(rnd.sample(range(len(pays)), min(len(pays), rnd.randint(0, 3)))) if way == "quiet" else None
        for i, (y, m) in enumerate(pays):
            if way == "constant":                           # every month on the 1st or the last day
                d = date(y, m, min(day, month_end(y, m).day))
            else:
                d = date(y, m, 1) + timedelta(days=rnd.choice([0, 0, 2, 5]))
            if (way == "quiet" and i not in quiet) or (pause and pause[0] <= (y, m) <= pause[1]) or (way in ("regular", "pause", "burst") and rnd.random() < 0.1):
                continue
            if f <= d <= today:
                self.add(cs["kk"], d, -cs["annuity"], "Verkäufer", "Annuität", "Umbuchung", cs["lender"])
        if way == "burst" and pays:                         # extra payments, several in one month
            y, m = rnd.choice(pays)
            for _ in range(rnd.randint(3, 8)):
                d = date(y, m, rnd.randint(1, month_end(y, m).day))
                if f <= d <= today:
                    self.add(cs["kk"], d, -rnd.choice([500.0, 2500.0, 0.01]), "Verkäufer", "Sondertilgung", "Umbuchung", cs["lender"])
        rates = [(start, rnd.choice([0.5, 2.75, 3.0, 6.125]))]
        days = []
        for _ in range(rnd.choice([0, 0, 1, 1, 2, 3])):
            d = start + timedelta(days=rnd.randint(1, span + 60))
            days.append(rnd.choice([date(d.year, 1, 1), date(d.year, 7, 1), d.replace(day=1), d]))
        if pause and rnd.random() < 0.7:                    # a new rate right after a pause (or as it began)
            y, m = pause[1] if rnd.random() < 0.7 else pause[0]
            days.append(date(y, m, 1) + timedelta(days=32 if rnd.random() < 0.7 else 0))
        for d in sorted(set(d for d in days if d > start)):
            rates.append((d, rnd.choice([0.0, 1.0, 4.5, 2.75, 6.125])))
        cs["rates"] = rates
        cs["model"] = rnd.choice(["yearly_base", "remaining_debt_monthly"])
        cs["booking_day"] = rnd.choice(["ultimo", "with_payment"])
        self.notes.append("%s loan opened %s, from %s, %s%s, rates %s" % (cs["name"], cs["opened"], f, way, " %s..%s" % pause if pause else "",
                                                                           ", ".join("%s %s" % (d, r) for d, r in rates)))

    def company_life(self, cs):
        """What happens in the company before the rules (test_worlds.PROFILES): nothing, a rent each month, almost nothing, a month
        with many payments, or amounts from a cent to a million, in and out."""
        rnd, today, start = self.rnd, self.today, self.start
        way = rnd.choice(["none", "none", "constant", "quiet", "burst", "volatile"])
        span = (today - start).days
        if way == "constant":
            day, x = rnd.choice([1, 15, 31]), rnd.choice([2500.0, 777.77])
            for y, m in months(start, today):
                d = date(y, m, min(day, month_end(y, m).day))
                if start <= d <= today:
                    self.add(cs["kk"], d, x, "Mieter", "Miete", "Miete")
        elif way == "quiet":
            for _ in range(rnd.randint(0, 2)):
                self.add(cs["kk"], start + timedelta(days=rnd.randint(0, span)), rnd.choice([-1234.5, 800.0]), "Zahlung", "")
        elif way == "burst":
            d0 = start + timedelta(days=rnd.randint(0, span))
            for _ in range(rnd.randint(20, 80)):
                d = min(today, max(start, d0.replace(day=rnd.randint(1, month_end(d0.year, d0.month).day))))
                self.add(cs["kk"], d, rnd.choice([-12.5, -89.0, 250.0, -0.01, 1500.0]), "Zahlung", "")
        elif way == "volatile":
            for _ in range(rnd.randint(5, 20)):
                self.add(cs["kk"], start + timedelta(days=rnd.randint(0, span)), rnd.choice([1, -1]) * max(0.01, round(10 ** rnd.uniform(-2, 6), 2)), "Zahlung", "")
        if way != "none":
            self.notes.append("%s: %s" % (cs["name"], way))

    def iban(self):
        self.n_iban += 1
        return "DE%02d%04d" % (90 + self.n, self.n_iban)          # made up, not of the form of a real IBAN

    def add(self, key, d, amount, name, purpose, cat="", counter=""):
        t = F.tx(key, d, round(amount, 2), name, purpose, cat, counter)
        self.txs.append(t)
        return t

    def config(self, directory):
        cfg = core.merged_config(config_for_test(os.path.join(directory, "Belege")))
        cfg["balance"] = {"months_back": 24}
        cfg["cashflow"] = {}
        cfg["tax"] = {}
        cfg["areas"] = [{"id": F.uid(self.k("p%d" % i)), "name": p, "kind": "private", "main_area": i == 0,
                         "accounts": [F.uid(self.k("p%d" % i)) + " | " + p]} for i, p in enumerate(self.privates)]
        cfg["areas"] += [{"id": F.uid(cs["group"]), "name": c, "kind": "company", "share": cs["share"], "accounts": [F.uid(cs["group"]) + " | " + c]}
                         for c, cs in self.co.items()]
        cfg["companies"], cfg["account_mirrors"], cfg["loans"] = [], [], []
        for c, cs in self.co.items():
            if cs["kind"] == "rule":
                cs["cycle"] = self.rnd.choice(["daily", "monthly"])
                retro = "2026-06-01" if self.classic else (self.today - timedelta(days=self.rnd.randint(0, (self.today - self.start).days))).replace(day=1).isoformat()
                cs["retro"] = self.rnd.choice(["", retro, "all"])
                cfg["companies"].append(dict(area=F.uid(cs["group"]), participation=F.uid(cs["stake"]) + " | B",
                                             retroactive_from=cs["retro"], cycle=cs["cycle"]))
            else:
                cs["mirror_from"] = self.rnd.choice(["", "all"])
                cfg["companies"].append(dict(area=F.uid(cs["group"])))
                cfg["account_mirrors"].append({"a": F.uid(cs["stake"]) + " | M", "b": F.uid(cs["kap"]) + " | T", "from_date": cs["mirror_from"]})
            if cs["vd"]:
                rates = [{"from_date": d.isoformat(), "percent": r} for d, r in cs["rates"]]
                cfg["loans"].append({"name": "Darlehen " + c, "loan_account": F.uid(cs["vd"]) + " | Verkäuferdarlehen",
                                     "source_accounts": [F.uid(cs["kk"]) + " | Konto"], "detection": {"counter_iban": cs["lender"]},
                                     "from_date": cs["from"].isoformat(),
                                     "interest": {"model": cs["model"], "rate_list": rates, "booking_day": cs["booking_day"]},
                                     "booking": {"counterparty": "Verkäufer", "category_repayment": "Umbuchung", "category_interest": "Zinsen"}})
        return cfg

    def rate_at(self, cs, d):
        """The rate on a day, as the list says: the last change on or before it (0: none yet)."""
        return ([0.0] + [r for day, r in cs["rates"] if day <= d])[-1]

    def describe(self):
        return "; ".join(["%s %s %s%s" % (c, cs["kind"], round(cs["share"], 4), (" loan %s %s %s %s" % (cs["model"], cs["rate"] if self.classic else "", cs["booking_day"], cs["from"])) if cs["vd"] else "")
                          for c, cs in self.co.items()] + self.notes)


class _Day(date):
    """date.today() in core: the day of the world (test_e2e.patch_today fixes its own)."""
    now = TODAY

    @classmethod
    def today(cls):
        return cls.now


class RuleWorlds(test_fuzz.FuzzTests):
    test_random_runs = None             # (test_fuzz's own run is not repeated here)

    def tearDown(self):
        patch_today()                   # date.today() as for the other tests again
        super().tearDown()

    # -- what must always hold (as in test_fuzz, with the accounts of this world's rules) ----------------------------------
    def check(self, where):
        targets = {F.uid(cs[k]) for cs in self.w.co.values() for k in ("stake", "kap", "vd") if cs[k]}
        seen = {}
        for t in self.txs():
            for m in marks_in(t.get("purpose")):
                key = (t["accountUuid"], m)
                self.assertNotIn(key, seen, "%s: a mark twice in an account (%s)" % (where, m))
                seen[key] = True
        for t in self.kontor_txs():
            self.assertIn(t["accountUuid"], targets, "%s: booked into an account outside the rules" % where)
        for b in MockBridge.instances:
            self.assertFalse([x for x in b.written if x[0] == "set"], "%s: an existing booking was changed" % where)
        now = {t["id"]: t for t in self.txs()}
        for i, t in self.frozen.items():
            self.assertEqual(now.get(i), t, "%s: a booking of yours changed" % where)

    def setup_world(self, seed):
        rnd = random.Random(seed)
        # a share of the worlds as before (one time, 1 Nov 2025 to 4 Nov 2026) -- decided apart from the seed's own draws, so they
        # are the worlds these seeds built before (and what a night found before, test_worlds.LEGACY, stays what it was)
        classic = seed in W.LEGACY or random.Random("rule activity %d" % seed).random() < CLASSIC
        self.w = w = World(rnd, seed % 1000, classic)
        self.today = _Day.now = w.today
        core.date = _Day
        MockBridge.state = {"accounts": copy.deepcopy(w.raw), "txs": [copy.deepcopy(t) for t in w.txs]}
        MockBridge.instances = []
        self.cfg = w.config(self.dir)
        self.store.save("config.json", self.cfg)
        self.store.save("state.json", {})
        self.frozen = {t["id"]: copy.deepcopy(t) for t in self.txs()}
        return rnd

    def settle(self, rnd, where):
        self.cfg["dry_run"] = True
        self.cfg["not_book"] = []
        for _ in range(10):
            if not self.run_once(self.cfg, True)["proposals"]:
                break
            self.approve(self.cfg, rnd, part=False)
            self.check(where + " settling")
        end = self.end = self.run_once(self.cfg, True)
        self.assertEqual(end["proposals"], [], "%s: something is still to book" % where)
        return core.fetch(MockBridge(True), self.cfg, self.today)

    def participations_right(self, led, where):
        for c, cs in self.w.co.items():
            if cs["kind"] != "rule":
                continue
            members = [a.uuid for a in led.descendants(F.uid(cs["group"]))]
            # the value to the cent, then share x value -- exactly, half a cent up
            if cs["cycle"] == "daily":
                value = sum(led.accounts[u].balance for u in members)
                self.assertAlmostEqual(led.accounts[F.uid(cs["stake"])].balance, exact(value, cs["share"]), 2, "%s: %s participation" % (where, c))
            else:
                end_of = date(self.today.year, self.today.month, 1) - timedelta(days=1)
                then = sum(led.balance_at(u, end_of) for u in members)
                if cs["retro"] not in ("", "all") and date.fromisoformat(cs["retro"]) > end_of:
                    then = 0.0                              # booked from this month on: nothing due before its end
                self.assertAlmostEqual(led.balance_at(F.uid(cs["stake"]), end_of), exact(then, cs["share"]), 2,
                                       "%s: %s participation at the end of last month" % (where, c))

    def mirrors_complete(self, where, touched):
        for c, cs in self.w.co.items():
            if cs["kind"] != "mirror" or cs["mirror_from"] != "all" or c in touched:
                continue
            mine = sorted(round(t["amount"], 2) for t in self.txs() if t["accountUuid"] == F.uid(cs["stake"]))
            theirs = sorted(round(-t["amount"], 2) for t in self.txs() if t["accountUuid"] == F.uid(cs["kap"]))
            self.assertEqual(mine, theirs, "%s: %s mirror incomplete" % (where, c))

    def loans_exact(self, led, where):
        """Every payment its repayment, every month its interest -- computed here as the contract says. No interest where there
        is nothing to compute it from: on a yearly base, the year the loan began (no balance at the start of the year); on the
        remaining debt, the month it began (no debt at the end of the month before); and nothing at 0 %."""
        for c, cs in self.w.co.items():
            if not cs["vd"]:
                continue
            vd, at = F.uid(cs["vd"]), "%s: %s loan" % (where, c)
            booked = {m: t for t in self.txs() if t["accountUuid"] == vd for m in marks_in(t.get("purpose"))}
            pays = sorted((t for t in self.txs() if t["accountUuid"] == F.uid(cs["kk"]) and t.get("accountNumber") == cs["lender"]
                           and mm_bridge.local_date(t["bookingDate"]) >= cs["from"]), key=lambda t: (t["bookingDate"], t["id"]))
            for p in pays:
                r = booked.get("#kontor-tx-%d" % p["id"])
                self.assertIsNotNone(r, "%s: payment of %s without repayment" % (at, mm_bridge.local_date(p["bookingDate"])))
                self.assertAlmostEqual(r["amount"], -p["amount"], 2, at)
            paid_ids = {"#kontor-tx-%d" % p["id"] for p in pays}
            self.assertFalse([m for m in booked if m.startswith("#kontor-tx-") and m not in paid_ids], "%s: a repayment without its payment" % at)
            due = set()                                     # the months whose interest is due by now
            rate_at = lambda d: self.w.rate_at(cs, d)
            for y, m in months(cs["from"], self.today):
                paid = sorted(mm_bridge.local_date(p["bookingDate"]) for p in pays if (mm_bridge.local_date(p["bookingDate"]).year, mm_bridge.local_date(p["bookingDate"]).month) == (y, m))
                days = paid if cs["booking_day"] == "with_payment" and paid else [month_end(y, m)]
                # with the payment: on the day of the month's first payment Kontor knew of (one entered later, earlier in the
                # month, does not move it -- nothing is changed afterwards)
                if min(days) > self.today or max(days) < cs["from"]:
                    continue
                z = booked.get("#kontor-zins-%04d-%02d" % (y, m))
                if cs["model"] == "yearly_base" and cs["opened"] > date(y - 1, 12, 31):
                    want = 0.0                              # no balance at the start of the year
                elif cs["model"] == "yearly_base":
                    base = abs(led.balance_at(vd, date(y - 1, 12, 31)))
                    yearly = exact(base, rate_at(date(y, 1, 1)), 100)
                    per = exact(yearly, 1, 12)
                    want = round(yearly - 11 * per, 2) if m == 12 else per
                else:
                    want = exact(abs(led.balance_at(vd, date(y, m, 1) - timedelta(days=1))), rate_at(date(y, m, 1)), 1200)
                if want < 0.005:
                    self.assertIsNone(z, "%s: interest for %02d/%d, from nothing" % (at, m, y))
                    continue
                due.add("#kontor-zins-%04d-%02d" % (y, m))
                self.assertIsNotNone(z, "%s: no interest for %02d/%d" % (at, m, y))
                self.assertIn(mm_bridge.local_date(z["bookingDate"]), days, "%s: interest %02d/%d on its day" % (at, m, y))
                self.assertAlmostEqual(z["amount"], -want, 2, "%s: interest %02d/%d" % (at, m, y))
            self.assertFalse([m for m in booked if m.startswith("#kontor-zins-") and m not in due], "%s: interest for a month not due" % at)

    # -- the runs -----------------------------------------------------------------------------------------------------------
    def ago(self, days, this_month=False):
        """A day some days before the world's day -- not before its first (this_month: nor before the 1st of this month: a loan
        payment entered later, dated before interest Kontor booked already, would not change that interest -- by design)."""
        return max(self.w.start, self.today.replace(day=1) if this_month else self.w.start, self.today - timedelta(days=days))

    def not_before_interest(self, cs, day):
        """Nor before this month's interest Kontor booked already on the loan: on the last day of a month without a payment it
        books at the month's end -- a payment entered after that, dated earlier, leaves it there (the same design as ago)."""
        tag = "#kontor-zins-%04d-%02d" % (self.today.year, self.today.month)
        return max([day] + [mm_bridge.local_date(t["bookingDate"]) for t in self.txs()
                            if t["accountUuid"] == F.uid(cs["vd"]) and tag in marks_in(t.get("purpose"))])

    def clean(self, seed):
        rnd = self.setup_world(seed)
        w, where = self.w, "seed %d clean (%s)" % (seed, self.w.describe())
        for i in range(rnd.randint(3, 10)):
            act = rnd.choice(["sync", "auto", "approve", "approve", "pay", "mirror", "loanpay"])
            at = "%s step %d (%s)" % (where, i, act)
            if act == "sync":
                self.run_once(self.cfg, True)
            elif act == "auto":                             # booking fully automatically: what is new since the last check
                self.cfg["dry_run"] = False
                self.run_once(self.cfg, False)
                self.cfg["dry_run"] = True
            elif act == "approve":
                self.approve(self.cfg, rnd)
            elif act == "pay":                              # a company's value moves
                cs = rnd.choice(list(w.co.values()))
                self.add(cs["kk"], self.ago(rnd.randint(0, 40)), rnd.choice([-1234.5, 800.0, 0.01, 96.25]), "Zahlung")
            elif act == "mirror":
                ms = [cs for cs in w.co.values() if cs["kind"] == "mirror"]
                if ms:
                    cs = rnd.choice(ms)
                    self.add(rnd.choice([cs["stake"], cs["kap"]]), self.ago(rnd.randint(0, 20)), rnd.choice([-300.0, 120.0, 55.55]), "Einlage/Entnahme")
            elif act == "loanpay":                          # an extra payment to the seller
                ls = [cs for cs in w.co.values() if cs["vd"]]
                if ls:
                    cs = rnd.choice(ls)
                    t = self.add(cs["kk"], self.not_before_interest(cs, self.ago(rnd.randint(0, 3), this_month=True)), -rnd.choice([500.0, 2500.0]), "Sondertilgung")
                    t["accountNumber"], t["name"] = cs["lender"], "Verkäufer"
                    self.frozen[t["id"]] = copy.deepcopy(t)
            self.check(at)
        led = self.settle(rnd, where)
        self.participations_right(led, where)
        self.mirrors_complete(where, ())
        self.loans_exact(led, where)
        self.assertFalse([w for w in self.end["warnings"] if "passen nicht mehr" in w], where)      # no interest on a changed debt

    def changed(self, seed):
        rnd = self.setup_world(seed)
        w, where = self.w, "seed %d changed (%s)" % (seed, self.w.describe())
        touched = set()
        for i in range(rnd.randint(8, 18)):
            auto = rnd.random() < 0.35
            self.cfg["dry_run"] = not auto
            act = rnd.choice(["sync", "approve", "reject", "delete", "change", "pay", "mirror", "again", "unmark", "redate", "original", "renumber"])
            at = "%s step %d (%s%s)" % (where, i, act, "/auto" if auto else "")
            if act == "sync":
                self.run_once(self.cfg, not auto)
            elif act == "approve":
                self.approve(self.cfg, rnd)
            elif act == "reject":
                rows = self.run_once(self.cfg, True)["proposals"]
                if rows:
                    p = rnd.choice(rows)
                    self.cfg["not_book"] = [x for x in self.cfg.get("not_book") or [] if x["key"] != p["key"]] + [core.not_booked_entry(p, p["key"])]
            elif act == "again" and self.cfg.get("not_book"):
                self.cfg["not_book"].remove(rnd.choice(self.cfg["not_book"]))
            elif act == "delete" and self.kontor_txs():
                self.remove(rnd.choice(self.kontor_txs()))
            elif act == "change":
                vals = [t for t in self.kontor_txs() if any(rules.is_value_tag(m) for m in marks_in(t["purpose"]))]
                if vals:
                    t = rnd.choice(vals); d = rnd.choice([-40.0, 15.5])
                    t["amount"] = round(t["amount"] + d, 2); b = self.balance(t["accountUuid"]); b[0] = round(b[0] + d, 2)
            elif act == "pay":
                cs = rnd.choice(list(w.co.values()))
                self.add(cs["kk"], self.ago(rnd.randint(0, 50)), rnd.choice([-1234.5, 800.0, 96.25]), "Zahlung")
            elif act == "mirror":
                ms = [cs for cs in w.co.values() if cs["kind"] == "mirror"]
                if ms:
                    cs = rnd.choice(ms)
                    self.add(rnd.choice([cs["stake"], cs["kap"]]), self.ago(rnd.randint(0, 20)), rnd.choice([-300.0, 120.0]), "Einlage/Entnahme")
            elif act == "unmark" and self.kontor_txs():
                t = rnd.choice(self.kontor_txs())
                t["purpose"] = TAG_RE.sub("", t["purpose"]).strip(" ·")
                touched.update(c for c, cs in w.co.items() if t["accountUuid"] in (F.uid(cs["stake"]), F.uid(cs["kap"])))
            elif act == "redate" and self.kontor_txs():
                t = rnd.choice(self.kontor_txs())
                t["bookingDate"] = t["valueDate"] = t["bookingDate"] + timedelta(days=rnd.choice([-3, -1, 2]))
            elif act in ("original", "renumber"):
                ms = [cs for cs in w.co.values() if cs["kind"] == "mirror"]
                mine = [t for t in self.txs() if not marks_in(t.get("purpose")) and any(t["accountUuid"] in (F.uid(cs["stake"]), F.uid(cs["kap"])) for cs in ms)]
                if mine:
                    t = rnd.choice(mine)
                    touched.update(c for c, cs in w.co.items() if t["accountUuid"] in (F.uid(cs["stake"]), F.uid(cs["kap"])))
                    if act == "original" and rnd.random() < 0.5:
                        self.remove(t)
                    elif act == "original":
                        d = rnd.choice([-10.0, 33.3]); t["amount"] = round(t["amount"] + d, 2); b = self.balance(t["accountUuid"]); b[0] = round(b[0] + d, 2)
                        self.frozen[t["id"]] = copy.deepcopy(t)
                    else:                                    # deleted and entered again in MoneyMoney: a new number
                        self.remove(t)
                        again = self.add(next(k for k, u in F.U.items() if u == t["accountUuid"]), date(2026, 1, 1), t["amount"], t["purpose"])
                        again.update({k: t[k] for k in ("bookingDate", "valueDate", "name", "accountNumber", "category", "categoryPath")})
                        self.frozen[again["id"]] = copy.deepcopy(again)
            self.check(at)
        led = self.settle(rnd, where)
        self.participations_right(led, where)
        self.mirrors_complete(where, touched)

    def test_random_rule_worlds(self):
        for seed in F.fuzz_seeds("Regel-Welten"):
            with self.subTest(seed=seed), F.case(seed):
                reset_mock(); patch_today()
                self.clean(seed)
                reset_mock()
                self.changed(seed)


if __name__ == "__main__":
    unittest.main(verbosity=1)
