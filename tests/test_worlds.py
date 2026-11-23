"""Random worlds: one to three private areas (you, a partner, the children) and up to four companies, owned by them and by
each other in odd shares (a holding owning a company, 0.5 %, a third, 74.9 %, all of it) -- with bank and offline accounts,
and months of bookings between all of them: salaries and expenses, transfers within an area and between any two areas
(over a month end, a year end, days apart), contributions booked against a stake and a capital account, loans between the
areas and from and to a friend, interest, value changes. Amounts come from a small set on purpose (the same amount many
times, a cent, a large one) and days lean towards the edges of months and years -- the cases where bookings could be
confused with each other.

Time and activity differ from world to world (a quarter of them stay "classic": 1 Nov 2025 to 20 Jun 2026, every area
alike): the time read lasts from ten days to four years and ends on any day from 2023 to 2027 (often the 1st, a month's
last day, 31 Dec, 1 Jan, 29 Feb 2024), and each area has its own way of life --

  * normal: a few bookings a month, on any day;
  * quiet: almost nothing, whole months and years empty;
  * dormant: no booking at all for a year or more (in short worlds: most of the time), over a year end, then bookings again;
  * constant: every month the same -- salary, rent, savings, a standing order to another area, on one day of the month
    (the 31st is the month's last day);
  * volatile: amounts from a cent to 20 million, income booked back and expenses refunded;
  * a burst: one month with 150 to 400 bookings (card payments, refunds) besides everything else;
  * seasonal: December (presents, a bonus) and summer (holidays) with most of it and larger amounts.

Besides that, areas other than the first may begin in the middle of the time (a company founded later), and an area may
open a second bank account in the middle of it -- which half of the time is closed again: its balance moved back to 0,
nothing after. No booking falls into a time where its account does not exist or rests.

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
MORE_EXPENSE = ["Versicherungen", "Tankstelle", "Restaurants"]              # (not in classic worlds: they draw as before)
CLASSIC = 0.25                  # share of the random worlds built as before: START .. TODAY, every area alike
# the cases nights found before diverse worlds (FOUND up to 3.17.x, test_cashflow's two among them): they build the worlds they
# were found in -- here, in test_rule_worlds and in test_cashflow. Fixed: a case found later (FOUND) is drawn like any other
LEGACY = frozenset({377654401, 357881360, 763175317, 224088165})
PROFILES = {"normal": 4, "quiet": 2, "dormant": 2, "constant": 2, "volatile": 2, "burst": 1, "seasonal": 2}
SEASON = (12, 6, 7, 8)          # December and summer
CARD = [4.99, 12.5, 2.2, 89.0, 0.01, 19.99, 250.0]                          # a burst: the same amounts many times
TOPUP = [4.99, 2.2, 89.0, 19.99]                                             # ... and top-ups to PayPal (none of AMOUNTS)


def cents(x):
    return int(round(x * 100))


def month_end(d):
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def months_of(lo, hi):
    y, m = lo.year, lo.month
    while (y, m) <= (hi.year, hi.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def edge_days(start, end):
    return [d for d in (start + timedelta(n) for n in range((end - start).days + 1))
            if d.day in (1, 28, 29, 30, 31) or (d.month, d.day) in ((12, 31), (1, 1)) or d == end]


def edge_day(rnd, start=START, end=TODAY, edges=None):
    """A day, leaning towards the edges: the last and first days of months, the year end, today. edges: edge_days(start,
    end), if known already (a long time: not built anew for every booking)."""
    if rnd.random() < 0.45:
        return rnd.choice(edge_days(start, end) if edges is None else edges)
    return start + timedelta(rnd.randrange((end - start).days + 1))


def some_today(rnd):
    """The last day read: any day from 2023 to 2027, often one at an edge -- the 1st, a month's last day, 31 Dec, 1 Jan, 29 Feb."""
    d = date(2023, 1, 1) + timedelta(rnd.randrange((date(2027, 12, 31) - date(2023, 1, 1)).days + 1))
    r = rnd.random()
    if r < 0.15:
        return d.replace(day=1)
    if r < 0.3:
        return month_end(d)
    if r < 0.36:
        return date(d.year, 12, 31)
    if r < 0.42:
        return date(d.year, 1, 1)
    if r < 0.46:
        return date(2024, 2, 29)
    return d


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
        self.start, self.today = START, TODAY
        self.profile = {}               # area -> its way of life (none in classic worlds)
        self.since = {}                 # area -> its first day
        self.life = {}                  # account key -> (first day, last day) -- only where it differs from its area's
        self.rest = {}                  # area -> (first day, last day) without any booking
        self.pools = {}                 # area -> the amounts it pays with
        self.notes = {}                 # area -> what is special about it (for the message of a failure)
        self.taken = {cents(x) for x in AMOUNTS}        # amounts odd() does not give
        self.edges = {}
        # which worlds stay classic: decided apart from the seed's own draws, so a classic world is the one this seed built
        # before (and what a night found before, LEGACY, stays what it was)
        self.classic = bool(privates) or seed in LEGACY or random.Random("activity %d" % seed).random() < CLASSIC
        if not self.classic:
            self.today = some_today(rnd)
            n = rnd.choice([rnd.randint(10, 60), rnd.randint(61, 365), rnd.randint(366, 1461), rnd.randint(366, 1461)])
            self.start = self.today - timedelta(n)
            r = rnd.random()
            if r < 0.4:
                self.start = self.start.replace(day=1)
            elif r < 0.55 and month_end(self.start) <= self.today - timedelta(7):
                self.start = month_end(self.start)
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
        self.since = {a: self.start for a in self.areas}
        if privates:
            return
        if self.classic:
            for a in self.areas:        # money to start with, before anything happens
                self.add(a, "bank", START, rnd.choice([5000.0, 250000.0]), cat=self.cat_in(a), counts=True)
            for _ in range(rnd.randint(15, 70)):
                self.happen()
            return
        self.ways_of_life()
        for a in self.areas:
            self.add(a, "bank", self.since[a], rnd.choice(self.pools[a][:2] if self.profile[a] == "volatile" else [5000.0, 250000.0]),
                     cat=self.cat_in(a), counts=True)
        for a in self.areas:
            if a + "|k2" in self.accounts:          # a second account, opened with a transfer from the first
                self.move(a, "bank", "k2", self.life[a + "|k2"][0], self.rnd.choice(self.pools[a]))
            if self.profile[a] == "constant":
                self.monthly(a)
            for d in self.own_days(a):
                self.happen(a, d)
            if self.profile[a] == "burst":
                self.burst(a)
        for a in self.areas:
            if a + "|k2" in self.accounts and self.life[a + "|k2"][1] < self.today:
                self.close(a, "k2")

    # -- time and ways of life ---------------------------------------------------------------------------------------------
    def ways_of_life(self):
        """Each area's way of life, its first day, a time it rests, a second account; the amounts it pays with."""
        rnd = self.rnd
        for a in self.areas:
            if a != self.privates[0] and rnd.random() < 0.25 and (self.today - self.start).days >= 40:
                self.since[a] = self.start + timedelta(rnd.randint(7, (self.today - self.start).days - 7))
                self.notes[a] = ["from %s" % self.since[a]]
            else:
                self.notes[a] = []
            p = self.profile[a] = rnd.choices(list(PROFILES), list(PROFILES.values()))[0]
            lo, span = self.since[a], (self.today - self.since[a]).days
            if p == "dormant":
                if span >= 400:
                    n = rnd.randint(365, min(span - 20, 550))
                elif span >= 30:
                    n = int(span * rnd.uniform(0.4, 0.7))
                else:
                    p = self.profile[a] = "quiet"
                if p == "dormant":
                    g = lo + timedelta(rnd.randint(1, span - n - 5))
                    self.rest[a] = (g, g + timedelta(n))
                    self.notes[a].append("rests %s..%s" % self.rest[a])
            if p == "volatile":         # from a cent to 20 million
                self.pools[a] = [max(0.01, round(10 ** rnd.uniform(-2, 7.3), 2)) for _ in range(8)]
                self.taken.update(cents(x) for x in self.pools[a])
            else:
                self.pools[a] = AMOUNTS
            if span >= 20 and rnd.random() < 0.3:
                k = self.account(a, "k2", "Zweitkonto " + a, "cash", bank=True)
                for _ in range(30):
                    o = lo + timedelta(rnd.randint(1, span - 2))
                    c = o + timedelta(rnd.randint(1, (self.today - o).days)) if rnd.random() < 0.5 else self.today
                    if self.area_alive(a, o) and self.area_alive(a, c) and c > o:
                        break
                else:
                    o, c = lo, self.today
                self.life[k] = (o, c)
                self.notes[a].append("second account %s..%s" % (o, "" if c == self.today else c))
            self.notes[a].insert(0, self.profile[a])

    def area_alive(self, area, day):
        r = self.rest.get(area)
        return self.since[area] <= day <= self.today and not (r and r[0] <= day <= r[1])

    def alive(self, k, day):
        """May the account have a booking on this day: it exists, and its area does not rest."""
        area = self.accounts[k][1]
        lo, hi = self.life.get(k, (self.since[area], self.today))
        if not (lo <= day <= hi and self.area_alive(area, day)):
            return False
        return "|stake:" not in k or day >= self.since[k.split("|stake:")[1]]     # a stake: once its company is there

    def happen(self, a=None, d=None, what=None):
        """Something happens (event, or what) -- only where every booking of it may be: otherwise nothing."""
        n, income, value = len(self.txs), dict(self.income), dict(self.value)
        what() if what else self.event(a, d)
        if any(not self.alive(e[1], e[2]) for e in self.txs[n:]):
            del self.txs[n:]
            self.income, self.value = income, value

    def edge_day(self, lo=None, hi=None):
        lo, hi = lo or self.start, hi or self.today
        if (lo, hi) not in self.edges:
            self.edges[(lo, hi)] = edge_days(lo, hi)
        return edge_day(self.rnd, lo, hi, self.edges[(lo, hi)])

    def own_days(self, a):
        """The days on which something starts in the area, by its way of life."""
        rnd, p, lo = self.rnd, self.profile[a], self.since[a]
        months = max(1.0, ((self.today - lo).days + 1) / 30.4)
        rate = rnd.choice([rnd.uniform(0.3, 2), rnd.uniform(2, 8)]) / max(1.0, len(self.areas) / 2.5)    # many areas: each a little less
        n = {"quiet": rnd.randint(0, 4), "constant": rnd.randint(0, 3), "burst": int(months * rate / 2)}.get(p, int(months * rate) + 1)
        out = []
        for _ in range(min(n, 200)):
            for _ in range(40):
                d = self.edge_day(lo)
                if p == "seasonal" and d.month not in SEASON and rnd.random() < 0.85:
                    continue
                if self.area_alive(a, d):
                    out.append(d)
                    break
        return out

    def monthly(self, a):
        """Every month the same: income, an expense, savings to the area's own savings account, a standing order to another
        area -- each with its amount, on its day of the month (30 and 31: or the month's last day)."""
        rnd = self.rnd
        plan = [(rnd.choice([1, 2, 15, 28, 30, 31]), self.odd(), "in"), (rnd.choice([1, 3, 15, 31]), self.odd(), "out")]
        if a + "|tg" in self.accounts and rnd.random() < 0.7:
            plan.append((rnd.choice([1, 28, 31]), self.odd(), "save"))
        others = [o for o in self.areas if o != a]
        if others and rnd.random() < 0.5:
            plan.append((rnd.choice([1, 15, 30, 31]), self.odd(), rnd.choice(others)))
        mine = [c for c in self.companies if a in self.owners[c]]
        if mine and rnd.random() < 0.5:
            plan.append((rnd.choice([1, 10, 31]), self.odd(), "stake:" + rnd.choice(mine)))
        self.notes[a].append("monthly %s" % ", ".join("%s on %d" % (what, day) for day, _, what in plan))
        for y, m in months_of(self.since[a], self.today):
            for day, x, what in plan:
                d = date(y, m, min(day, month_end(date(y, m, 1)).day))
                if not self.area_alive(a, d):
                    continue
                if what == "in":
                    self.add(a, "bank", d, x, cat=self.cat_in(a), counts=True)
                elif what == "out":
                    self.add(a, "bank", d, -x, cat=rnd.choice(EXPENSE), counts=True)
                elif what == "save":
                    self.move(a, "bank", "tg", d, x, lag=rnd.choice([0, 0, 1]), days=10)
                elif what.startswith("stake:"):     # into the company, booked by hand on the stake and (mostly) its capital account
                    self.happen(what=lambda: self.contribute(a, what[6:], d, x, rnd.choice([0, 1, 2])))
                else:                   # a standing order: from the bank to the other area's bank, a day later there at most
                    self.happen(what=lambda: [self.add(a, "bank", d, -x, iban=self.iban(what), purpose="Dauerauftrag", to=what),
                                              self.add(what, "bank", min(d + timedelta(rnd.choice([0, 1])), self.today), x, iban=self.iban(a),
                                                       purpose="Dauerauftrag", to=a)])

    def contribute(self, o, c, d, x, lag):
        """A contribution of o into c: paid, booked on o's stake (on the day or up to two days later), arriving in the company,
        booked there on o's capital account (on the day paid or arrived; now and then not at all)."""
        rnd, later = self.rnd, min(d + timedelta(lag), self.today)
        self.add(o, "bank", d, -x, iban=self.iban(c), cat=rnd.choice(["Umbuchung", ""]), purpose="Einlage " + c)
        self.add(o, "stake:" + c, min(d + timedelta(rnd.choice([0, 0, 1, 2])), self.today), x, purpose="Einlage " + c)
        self.add(c, "bank", later, x, iban=self.iban(o), purpose="Einlage")
        if rnd.random() < 0.6:
            self.add(c, "kap:" + o, rnd.choice([d, later]), -x, purpose="Einlage")      # on the day paid (mirrored) or arrived

    def burst(self, a):
        """One month with hundreds of bookings: card payments and refunds, all with a category -- and some of everything else."""
        rnd = self.rnd
        for _ in range(30):
            d0 = self.edge_day(self.since[a])
            days = [d for d in (d0.replace(day=1) + timedelta(i) for i in range(month_end(d0).day)) if self.area_alive(a, d)]
            if days:
                break
        else:
            return
        keys = [k for k in ("bank", "paypal", "k2") if a + "|" + k in self.accounts]
        n = rnd.randint(150, 400)
        self.notes[a].append("%d bookings in %s" % (n, d0.strftime("%Y-%m")))
        for _ in range(n):
            d, k = rnd.choice(days), rnd.choice(keys)
            if not self.alive(a + "|" + k, d):
                k = "bank"
            x = rnd.choice(CARD) if rnd.random() < 0.6 else round(rnd.uniform(0.01, 600), 2)
            self.add(a, k, d, x if rnd.random() < 0.12 else -x, cat=rnd.choice(EXPENSE + MORE_EXPENSE), counts=True)
        x = rnd.choice(TOPUP)
        lo, hi = days[0] - timedelta(14), days[-1] + timedelta(14)
        if a + "|paypal" in self.accounts and rnd.random() < 0.5 and not any(
                self.accounts[e[1]][1] == a and cents(abs(e[3])) == cents(x) and lo <= e[2] <= hi for e in self.txs):
            n = rnd.randint(10, 60)     # many top-ups of one amount (nothing else of it nearby), each booked by PayPal on its day
            self.notes[a].append("%d top-ups of %.2f" % (n, x))
            for _ in range(n):
                d = rnd.choice(days)
                if self.alive(a + "|paypal", d):
                    self.add(a, "bank", d, -x, cat="Umbuchung", name="PayPal")
                    self.add(a, "paypal", d, x, cat="Umbuchung", name="PayPal")
            self.between.setdefault((a + "|paypal", cents(x)), []).extend(days)     # (no other move of the amount near them)
        for _ in range(rnd.randint(2, 12)):
            self.happen(a, rnd.choice(days))

    def move(self, a, src, dst, d, x, lag=0, days=2 * report.PAIR_DAYS_IBAN_BOTH):
        """From one bank account of the area to another (both naming each other) -- an amount no other such move between the two
        has within four weeks (else one no other booking has; a month apart, each finds its own)."""
        if not self.fits(a + "|" + src + ">" + dst, d, x, days):
            x = self.odd()
        n = len(self.txs)
        self.add(a, src, d, -x, iban=self.iban(a, dst), cat=self.rnd.choice(["Umbuchung", ""]))
        self.add(a, dst, min(d + timedelta(lag), self.today), x, iban=self.iban(a, src))
        if any(not self.alive(e[1], e[2]) for e in self.txs[n:]):
            del self.txs[n:]

    def close(self, a, key):
        """The account is closed on its last day: what is left goes back to the bank account -- 0 afterwards, nothing more."""
        k, last = a + "|" + key, self.life[a + "|" + key][1]
        bal = round(sum(e[3] for e in self.txs if e[1] == k), 2)
        if abs(bal) < 0.005:
            return
        parts = [bal]
        while not all(self.fits(a + "|" + key + ">bank", last, x, 2 * report.PAIR_DAYS_IBAN_BOTH) for x in parts):
            y = self.odd()              # the rest in two moves, each with an amount of its own
            parts = [y, round(bal - y, 2)]
        for x in parts:
            self.add(a, key, last, -x, iban=self.iban(a), cat=self.rnd.choice(["Umbuchung", ""]), purpose="Auflösung")
            self.add(a, "bank", last, x, iban=self.iban(a, key), purpose="Auflösung")

    def fits(self, key, d, x, days):
        """No other transfer of this kind with this amount within the days -- noted, if so."""
        seen = self.between.setdefault((key, cents(x)), [])
        if any(abs((d - e).days) <= days for e in seen):
            return False
        seen.append(d)
        return True

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

    def cat_in(self, area, d=None):
        if d and d.month == 12 and area in self.privates and self.profile.get(area) == "seasonal":
            return "Bonus"
        return INCOME.get(area, "Miete")

    def cat_out(self, area, d):
        p = self.profile.get(area)
        if p == "seasonal" and d.month == 12:
            return "Geschenke"
        if p == "seasonal" and d.month in SEASON:
            return "Freizeit\\Urlaub"
        return self.rnd.choice(EXPENSE if self.classic else EXPENSE + MORE_EXPENSE)

    def amount(self):
        return self.rnd.choice(AMOUNTS)

    def amount_for(self, a, d):
        x = self.rnd.choice(self.pools[a])
        if self.profile.get(a) == "seasonal" and d.month in SEASON:
            x = round(x * self.rnd.choice([3, 10]), 2)
        return x

    def flip(self, a):
        """Volatile: now and then income booked back, an expense refunded."""
        return -1 if self.profile.get(a) == "volatile" and self.rnd.random() < 0.3 else 1

    def amount_between(self, a, b, d):
        """An amount for a payment between two areas that no other payment between them has within ten days: two such payments
        at the same distance from a booking by hand could each be its other side -- Kontor leaves that open on purpose."""
        pool = self.pools.get(a, AMOUNTS)
        for x in self.rnd.sample(pool, len(pool)) + [self.odd()]:
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
        while True:
            x = round(self.rnd.uniform(100, 9000), 2)       # (cents at random)
            if cents(x) not in self.taken:
                self.taken.add(cents(x))
                return x

    def other(self, a, d):
        """Another area for a payment between two: one that is there on the day (a quiet one seldom)."""
        if self.classic:
            return self.rnd.choice([o for o in self.areas if o != a])
        there = [o for o in self.areas if o != a and self.area_alive(o, d) and (self.profile[o] != "quiet" or self.rnd.random() < 0.2)]
        return self.rnd.choice(there) if there else None

    def owner_of(self, a):
        """A company and one of its owners: at random (classic), or one where the area is the one or the other."""
        if self.classic:
            c = self.rnd.choice(self.companies)
            return c, self.rnd.choice(sorted(self.owners[c]))
        pairs = [(c, o) for c in self.companies for o in sorted(self.owners[c]) if a in (c, o)]
        return self.rnd.choice(pairs) if pairs else (None, None)

    # -- what happens ------------------------------------------------------------------------------------------------------
    def event(self, a=None, d=None):
        """Something happens: at random (classic) or in the area on the day, with its amounts."""
        rnd = self.rnd
        if a is None:
            d, x = self.edge_day(), self.amount()
        else:
            x = self.amount_for(a, d)
        lag = rnd.choice([0, 0, 1, 2, 3])
        later = min(d + timedelta(lag), self.today)
        if a is None:
            a = rnd.choice(self.areas)
        kind = rnd.randrange(13 if self.classic else 15)
        p = self.privates[0]
        if kind in (6, 7, 8) and not self.classic and a != p:          # the friend and the flat are yours
            return
        if kind == 0:                                               # income
            self.add(a, "bank", d, x * self.flip(a), cat=self.cat_in(a, d), counts=True)
        elif kind == 1:                                             # an expense
            self.add(a, "bank", d, -x * self.flip(a), cat=self.cat_out(a, d), counts=True)
        elif kind == 2 and a + "|tg" in self.accounts:              # to the area's own savings account (and back)
            s = rnd.choice([1, -1])
            self.add(a, "bank", d, -s * x, iban=self.iban(a, "tg"), cat=rnd.choice(["Umbuchung", ""]))
            self.add(a, "tg", later, s * x, iban=self.iban(a))
        elif kind == 3 and len(self.areas) > 1:                     # between two areas, bank to bank
            b = self.other(a, d)
            if b is None:
                return
            x = self.amount_between(a, b, d)
            self.add(a, "bank", d, -x, iban=self.iban(b), cat=rnd.choice(["Umbuchung", ""]), to=b)
            self.add(b, "bank", min(d + timedelta(rnd.choice([0, 1, 3, 5])), self.today), x, iban=self.iban(a), cat=rnd.choice(["Umbuchung", ""]), to=a)
        elif kind == 4 and self.companies:                          # a contribution into a company, booked on the stake (and the capital account)
            c, o = self.owner_of(a)
            if c is None:
                return
            self.contribute(o, c, d, self.amount_between(o, c, d), lag)
        elif kind == 5 and len(self.areas) > 1:                     # a loan between two areas, booked on both sides; part back later
            b = self.other(a, d)
            if b is None:
                return
            self.account(a, "dar:" + b, "Darlehen an " + b, "receivables")
            self.account(b, "dar:" + a, "Darlehen von " + a, "liabilities")
            back = min(d + timedelta(rnd.randint(20, 60)), self.today)
            x = self.amount_between(a, b, d)
            for day, y in ((d, x), (back, -self.amount_between(a, b, back))):
                if day > self.today or (y < 0 and rnd.random() < 0.5):
                    continue
                arrive = min(day + timedelta(rnd.choice([0, 1, 2])), self.today)
                self.add(a, "bank", day, -y, iban=self.iban(b), purpose="Darlehen")
                self.add(a, "dar:" + b, day, y, purpose="Darlehen " + b)
                self.add(b, "bank", arrive, y, iban=self.iban(a), purpose="Darlehen")
                self.add(b, "dar:" + a, rnd.choice([day, arrive]), -y, purpose="Darlehen " + a)
        elif kind == 6:                                             # a friend: lent to or borrowed from, booked by hand days later
            if rnd.random() < 0.5:
                self.add(p, "bank", d, -x, name="Freund")
                self.add(p, "ford", later, x, name="Freund")
            else:
                self.add(p, "bank", d, x, name="Freund")
                self.add(p, "kredit", later, -x, name="Freund")
        elif kind == 7:                                             # interest on the friend's loan: a cost, booked by hand
            i = round(x * 0.03, 2) or 0.01
            self.add(p, "kredit", d, -i, purpose="Zinsen")
        elif kind == 8:                                             # the flat changes in value (by hand, an amount nothing else has)
            self.add(p, "immo", d, rnd.choice([1, -1]) * self.odd(), purpose="Wertanpassung", value=True)
        elif kind == 9 and self.companies:                          # Kontor's value adjustment of a stake
            c, o = self.owner_of(a)
            if c is None or (not self.classic and o != a):
                return
            self.add(o, "stake:" + c, d, rnd.choice([1, -1]) * x, purpose="Wertanpassung · #kontor-wert-%s-%d" % (d.strftime("%Y%m%d"), len(self.txs)),
                     value=True)
        elif kind == 10:                                            # an expense in a company or a second income
            if a in self.companies:
                self.add(a, "bank", d, -x * self.flip(a), cat=self.cat_out(a, d), counts=True)
            else:
                self.add(a, "bank", d, x * self.flip(a), cat=self.cat_in(a, d), counts=True)
        elif kind == 11 and a + "|paypal" in self.accounts:         # to PayPal and back: both sides "Umbuchung", no IBAN, a week apart at most
            s = rnd.choice([1, -1])
            x = self.amount_alone(a, "paypal", d, x)
            self.add(a, "bank", d, -s * x, cat="Umbuchung", name="PayPal")
            self.add(a, "paypal", min(d + timedelta(rnd.choice([0, 1, 3, 5, 7])), self.today), s * x, cat="Umbuchung", name="PayPal")
        elif kind == 12 and len(self.areas) > 1:                    # rent paid to another area: income there, an expense here
            b = self.other(a, d)
            if b is None:
                return
            self.add(a, "bank", d, -x, iban=self.iban(b), cat="Miete", purpose="Miete", counts=True)
            self.add(b, "bank", later, x, iban=self.iban(a), cat="Miete", purpose="Miete", counts=True)
        elif kind == 13 and a + "|k2" in self.accounts:             # income or an expense on the second account
            if rnd.random() < 0.5:
                self.add(a, "k2", d, x * self.flip(a), cat=self.cat_in(a, d), counts=True)
            else:
                self.add(a, "k2", d, -x * self.flip(a), cat=self.cat_out(a, d), counts=True)
        elif kind == 14 and a + "|k2" in self.accounts:             # between the two bank accounts of the area
            self.move(a, *rnd.choice([("bank", "k2"), ("k2", "bank")]), d, x, lag=lag)

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
        return {b["name"]: report.build_dataset(led, config, {}, self.today, b, dict(roles)) for b in core.bereiche_for(led, config)}

    def describe(self):
        areas = ", ".join("%s (%s)" % (a, ", ".join(self.notes[a])) if self.notes.get(a) else a for a in self.areas)
        return "%s..%s, %d bookings; %s; owners %s" % (self.start, self.today, len(self.txs), areas,
                                                      {c: {o: round(s, 4) for o, s in v.items()} for c, v in self.owners.items()})


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
