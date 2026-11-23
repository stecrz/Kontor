"""Random runs of the booking rules against a simulated MoneyMoney: approving parts, not booking (and proposing again), deleting,
changing, moving and unmarking Kontor's bookings there, changing, deleting or entering again your own bookings (a mirrored
original, a loan payment), new payments, booking fully automatically -- and after every step what must always hold:

  * a mark exists at most once per account (nothing is ever booked twice),
  * Kontor only adds bookings, only into the offline accounts of its rules, each with its mark,
  * nothing that was in MoneyMoney is changed or removed by Kontor,
  * what is booked on approval is exactly what the approval list showed,
  * in the end everything settles: nothing left to book, the participation equals share x value of the company, every booking
    of a mirrored account has its counterpart.

All names and amounts are made up (see fixtures.py)."""
import copy
import os
import random
import shutil
import sys
import tempfile
import time
import unittest
from collections import Counter
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import fixtures as F  # noqa: E402
import core  # noqa: E402
import rules  # noqa: E402
from model import TAG_RE, marks_in  # noqa: E402
from fixtures import new_store  # noqa: E402
from test_e2e import TODAY, MockBridge, config_for_test, patch_today, reset_mock  # noqa: E402

BET, MINE, THEIRS, LOAN = "priv.bet.ga", "priv.bet.gb", "gb.kap.a", "ga.vd"
TARGETS = {F.uid(k) for k in (BET, MINE, THEIRS, LOAN)}             # the only accounts the rules of this test may book into


class FuzzTests(unittest.TestCase):
    today = TODAY                       # the day Kontor runs on (test_rule_worlds: each world its own)

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-fuzz-")
        self.store = new_store(self.dir)
        reset_mock(); patch_today()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    # -- the simulated MoneyMoney ------------------------------------------------------------------------------------------
    def txs(self):
        return MockBridge.state["txs"]

    def kontor_txs(self):
        return [t for t in self.txs() if marks_in(t.get("purpose"))]

    def balance(self, uuid):
        return next(a for a in MockBridge.state["accounts"] if a["uuid"] == uuid)["balance"][0]

    def remove(self, t):
        self.txs().remove(t); b = self.balance(t["accountUuid"]); b[0] = round(b[0] - t["amount"], 2)
        self.frozen.pop(t["id"], None)

    def add(self, key, day, amount, text):
        t = F.tx(key, day, amount, "Test", text); self.txs().append(t)
        b = self.balance(F.uid(key)); b[0] = round(b[0] + amount, 2)
        self.frozen[t["id"]] = copy.deepcopy(t)
        return t

    def mine(self, keys):
        """Your own bookings (no mark of Kontor's) in some accounts."""
        uu = {F.uid(k) for k in keys}
        return [t for t in self.txs() if t["accountUuid"] in uu and not marks_in(t.get("purpose")) and "#geaendert" not in (t.get("purpose") or "")]

    # -- what must always hold ---------------------------------------------------------------------------------------------
    def check(self, where):
        seen = Counter((t["accountUuid"], m) for t in self.txs() for m in marks_in(t.get("purpose")))
        twice = [k for k, n in seen.items() if n > 1]
        self.assertEqual(twice, [], "%s: a mark twice in an account" % where)
        for t in self.kontor_txs():
            self.assertIn(t["accountUuid"], TARGETS, "%s: booked into an account outside the rules" % where)
        for b in MockBridge.instances:
            self.assertFalse([w for w in b.written if w[0] == "set"], "%s: an existing booking was changed" % where)
        now = {t["id"]: t for t in self.txs()}
        for i, t in self.frozen.items():                    # everything that was not made by Kontor is as it was
            self.assertEqual(now.get(i), t, "%s: a booking of yours changed" % where)

    def run_once(self, cfg, dry, approve=None):
        r = core.run_once(self.store, cfg, self.today, dry=dry, force=True, bridge_factory=MockBridge, approve=approve, with_report=False)
        self.assertEqual(r["status"], "ok", r)
        self.assertFalse([w for w in r["warnings"] if "nach Buchung" in w], r["warnings"])        # balances after booking as planned
        return r

    def approve(self, cfg, rnd, part=True):
        r = self.run_once(cfg, True)
        rows = r["proposals"]
        if not rows:
            return
        hold = {p["key"] for p in rows if part and rnd.random() < 0.4}
        led = core.fetch(MockBridge(True), cfg, self.today)
        shown = core.plan_pending(led, cfg, self.store.load("state.json") or {}, self.today, hold)
        self.assertFalse(hold & {p["key"] for p in shown})
        before = len(self.txs())
        r = self.run_once(cfg, False, {p["key"]: {"shown": p["amount"]} for p in shown})
        self.assertNotIn(core.tr("s_betraege_geaendert"), r["warnings"])          # booked is what was shown
        self.assertEqual(len(self.txs()) - before, len(shown)); self.assertEqual(r["booked_count"], len(shown))
        made = {t["accountUuid"] + "|" + m: t["amount"] for t in self.txs() for m in marks_in(t.get("purpose"))}
        for p in shown:
            self.assertAlmostEqual(made[p["key"]], p["amount"], 2)

    def scenario(self, seed):
        rnd = random.Random(seed)
        cfg = core.merged_config(config_for_test(os.path.join(self.dir, "Belege")))
        cfg["companies"] = [
            dict(area=F.uid("ga"), participation=F.uid(BET) + " | B", retroactive_from=rnd.choice(["", "2026-06-01", "all"]), cycle=rnd.choice(["daily", "monthly"])),
            dict(area=F.uid("gb"))]
        cfg["account_mirrors"] = [{"a": F.uid(MINE) + " | M", "b": F.uid(THEIRS) + " | T", "from_date": rnd.choice(["", "all"])}]
        self.store.save("config.json", cfg)
        for d, amt in ((date(2026, 8, 3), -700.0), (date(2026, 9, 9), 250.0)):          # there before the mirror is set up
            F_t = F.tx(THEIRS, d, amt, "Ich", "früher"); self.txs().append(F_t)
        self.frozen = {t["id"]: copy.deepcopy(t) for t in self.txs()}
        steps = []
        touched_mirror = False
        for i in range(18):
            auto = rnd.random() < 0.35
            cfg["dry_run"] = not auto
            act = rnd.choice(["sync", "sync", "approve", "approve", "reject", "delete", "change", "pay", "mirror", "again", "unmark",
                              "redate", "original", "renumber", "paydel"])
            steps.append(act + ("/auto" if auto else ""))
            where = "seed %d step %d (%s)" % (seed, i, " ".join(steps[-4:]))
            if act == "sync":
                self.run_once(cfg, not auto)
            elif act == "approve":
                self.approve(cfg, rnd)
            elif act == "reject":                                                   # "Don't book" (settings)
                rows = self.run_once(cfg, True)["proposals"]
                if rows:
                    p = rnd.choice(rows)
                    cfg["not_book"] = [x for x in cfg.get("not_book") or [] if x["key"] != p["key"]] + [core.not_booked_entry(p, p["key"])]
            elif act == "delete" and self.kontor_txs():
                self.remove(rnd.choice(self.kontor_txs()))                      # you delete a booking of Kontor's in MoneyMoney
            elif act == "change":
                vals = [t for t in self.kontor_txs() if any(rules.is_value_tag(m) for m in marks_in(t["purpose"]))]
                if vals:
                    t = rnd.choice(vals); d = rnd.choice([-40.0, 15.5])
                    t["amount"] = round(t["amount"] + d, 2); b = self.balance(t["accountUuid"]); b[0] = round(b[0] + d, 2)
            elif act == "pay":                                                      # the company's value moves
                self.add("ga.kk", TODAY - timedelta(days=rnd.randint(0, 50)), rnd.choice([-1234.5, 800.0, 96.25]), "Zahlung")
            elif act == "mirror":                                                   # a new booking in one of the mirrored accounts
                self.add(rnd.choice([MINE, THEIRS]), TODAY - timedelta(days=rnd.randint(0, 20)), rnd.choice([-300.0, 120.0, 55.55]), "Einlage/Entnahme")
            elif act == "again" and cfg.get("not_book"):                       # "Propose again"
                cfg["not_book"].remove(rnd.choice(cfg["not_book"]))
            elif act == "unmark" and self.kontor_txs():                             # you remove Kontor's mark from a booking's text
                t = rnd.choice(self.kontor_txs())
                t["purpose"] = TAG_RE.sub("", t["purpose"]).strip(" ·")
            elif act == "redate" and self.kontor_txs():                             # you move a booking of Kontor's by a few days
                t = rnd.choice(self.kontor_txs())
                t["bookingDate"] = t["valueDate"] = t["bookingDate"] + timedelta(days=rnd.choice([-3, -1, 2]))
            elif act == "original" and self.mine([MINE, THEIRS]):                   # you change or delete a mirrored original
                t = rnd.choice(self.mine([MINE, THEIRS])); touched_mirror = True
                if rnd.random() < 0.5:
                    self.remove(t)
                else:
                    d = rnd.choice([-10.0, 33.3]); t["amount"] = round(t["amount"] + d, 2); b = self.balance(t["accountUuid"]); b[0] = round(b[0] + d, 2)
                    self.frozen[t["id"]] = copy.deepcopy(t)
            elif act == "renumber" and self.mine([MINE, THEIRS, "ga.kk"]):         # deleted and entered again in MoneyMoney: a new number
                t = rnd.choice(self.mine([MINE, THEIRS, "ga.kk"]))
                self.remove(t)
                again = self.add(next(k for k, u in F.U.items() if u == t["accountUuid"]), date(2026, 1, 1), t["amount"], t["purpose"])
                again.update({k: t[k] for k in ("bookingDate", "valueDate", "name", "accountNumber", "category", "categoryPath")})
                self.frozen[again["id"]] = copy.deepcopy(again)
            elif act == "paydel":                                                   # a loan payment deleted in MoneyMoney
                pays = [t for t in self.mine(["ga.kk"]) if t.get("accountNumber") == F.SELLER_IBAN]
                if pays:
                    self.remove(rnd.choice(pays))
            self.check(where)
        # in the end: everything approved until nothing is left
        cfg["dry_run"] = True

        cfg["not_book"] = []          # everything under "Not booked" proposed again
        for _ in range(8):
            if not self.run_once(cfg, True)["proposals"]:
                break
            self.approve(cfg, rnd, part=False)
            self.check("seed %d settling" % seed)
        end = self.run_once(cfg, True)
        self.assertEqual(end["proposals"], [], "seed %d: something is still to book" % seed)
        led = core.fetch(MockBridge(True), cfg, TODAY)
        value = sum(a.balance for a in led.descendants(F.uid("ga")))
        if cfg["companies"][0]["cycle"] == "daily":          # daily: the participation is at share x value now
            self.assertAlmostEqual(led.accounts[F.uid(BET)].balance, round(0.4 * value, 2), 2, "seed %d: participation off" % seed)
        else:                                                        # monthly: at the end of last month
            end_of = date(TODAY.year, TODAY.month, 1) - timedelta(days=1)
            then = sum(led.balance_at(a.uuid, end_of) for a in led.descendants(F.uid("ga")))
            self.assertAlmostEqual(led.balance_at(F.uid(BET), end_of), round(0.4 * then, 2), 2, "seed %d: participation off at month end" % seed)
        # every booking of the mirrored accounts has its counterpart: the two balances moved by the same amounts
        mine = sorted(round(t["amount"], 2) for t in self.txs() if t["accountUuid"] == F.uid(MINE))
        theirs = sorted(round(-t["amount"], 2) for t in self.txs() if t["accountUuid"] == F.uid(THEIRS))
        if cfg["account_mirrors"][0]["from_date"] == "all" and not touched_mirror:      # (an original you changed: a note, Kontor changes nothing)
            self.assertEqual(mine, theirs, "seed %d: mirror incomplete" % seed)
        return steps

    def test_random_runs(self):
        for seed in F.fuzz_seeds("Buchungsregeln"):          # more: KONTOR_FUZZ_SEEDS / _RANDOM / _MINUTES (nightly.yml), one again: KONTOR_FUZZ_SEED
            reset_mock(); MockBridge.instances = []
            for name in ("state.json",):
                self.store.save(name, {})
            with self.subTest(seed=seed), F.case(seed):
                self.scenario(seed)


class Seeds(unittest.TestCase):
    """Which cases a random test runs: the fixed ones, those found before, and new ones drawn anew every run; one again by its number."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-seeds-"); self.addCleanup(shutil.rmtree, self.dir, True)

    def test_fixed_found_and_new(self):
        from unittest import mock
        env = {k: v for k, v in os.environ.items() if not k.startswith("KONTOR_FUZZ")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(F, "FOUND", [1234567]):
            self.assertEqual(list(F.fuzz_seeds()), list(range(40)) + [1234567])                # a push: the 40 fixed ones and the found
            os.environ.update(KONTOR_FUZZ_SEEDS="5", KONTOR_FUZZ_RANDOM="300")
            a, b = list(F.fuzz_seeds()), list(F.fuzz_seeds())
            self.assertEqual(a[:6], [0, 1, 2, 3, 4, 1234567]); self.assertEqual(len(a), 306)
            self.assertTrue(all(10 ** 6 <= x < 10 ** 9 for x in a[6:]))                          # never one of the fixed ones
            self.assertNotEqual(a[6:], b[6:])                                                   # new every run
            # as many as fit into the time: drawn until it is over, then the numbers into GitHub's summary of the run
            os.environ.update(KONTOR_FUZZ_SEEDS="0", KONTOR_FUZZ_RANDOM="0", KONTOR_FUZZ_MINUTES="0.002",
                              GITHUB_STEP_SUMMARY=os.path.join(self.dir, "summary.md"))
            t0 = time.monotonic(); n = sum(1 for _ in F.fuzz_seeds("Probe"))
            self.assertGreater(n, 1); self.assertGreaterEqual(time.monotonic() - t0, 0.11)
            with open(os.environ["GITHUB_STEP_SUMMARY"], encoding="utf-8") as f:
                self.assertEqual(f.read(), "- Probe: 0 feste, 1 gefundene, %d neue Fälle\n" % (n - 1))
            os.environ["KONTOR_FUZZ_SEED"] = "5551234, 7"
            self.assertEqual(list(F.fuzz_seeds()), [5551234, 7])                                # just these again
        # a failure names its case, also where pytest does not show the subtest (Python 3.9)
        for err in (AssertionError("1 != 2"), KeyError("x")):
            with self.assertRaisesRegex(AssertionError, "^seed 5551234: "):
                with F.case(5551234):
                    raise err
        with self.assertRaisesRegex(AssertionError, "^seed 7 step 3"):          # named already: unchanged
            with F.case(7):
                raise AssertionError("seed 7 step 3 (x)")


if __name__ == "__main__":
    unittest.main(verbosity=1)
