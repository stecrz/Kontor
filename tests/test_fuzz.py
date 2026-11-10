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
import unittest
from collections import Counter
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import fixtures as F  # noqa: E402
import core  # noqa: E402
import rules  # noqa: E402
from model import TAG_RE, marks_in  # noqa: E402
from storage import Store, load_or_create_master_key  # noqa: E402
from test_e2e import TODAY, MockBridge, config_for_test, patch_today, reset_mock  # noqa: E402

BET, MINE, THEIRS, LOAN = "priv.bet.pb", "priv.bet.shs", "shs.kap.s", "pb.vd"
TARGETS = {F.uid(k) for k in (BET, MINE, THEIRS, LOAN)}             # the only accounts the rules of this test may book into


class FuzzTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-fuzz-")
        key, src = load_or_create_master_key(self.dir)
        self.store = Store(self.dir, key, src)
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
        r = core.run_once(self.store, cfg, TODAY, dry=dry, force=True, bridge_factory=MockBridge, approve=approve, with_report=False)
        self.assertEqual(r["status"], "ok", r)
        self.assertFalse([w for w in r["warnungen"] if "nach Buchung" in w], r["warnungen"])        # balances after booking as planned
        return r

    def approve(self, cfg, rnd, part=True):
        r = self.run_once(cfg, True)
        rows = r["vorschlaege"]
        if not rows:
            return
        hold = {p["key"] for p in rows if part and rnd.random() < 0.4}
        led = core.fetch(MockBridge(True), cfg, TODAY)
        shown = core.plan_pending(led, cfg, self.store.load("state.json") or {}, TODAY, hold)
        self.assertFalse(hold & {p["key"] for p in shown})
        before = len(self.txs())
        r = self.run_once(cfg, False, {p["key"]: {"angezeigt": p["betrag"]} for p in shown})
        self.assertNotIn(core.tr("s_betraege_geaendert"), r["warnungen"])          # booked is what was shown
        self.assertEqual(len(self.txs()) - before, len(shown)); self.assertEqual(r["gebucht"], len(shown))
        made = {t["accountUuid"] + "|" + m: t["amount"] for t in self.txs() for m in marks_in(t.get("purpose"))}
        for p in shown:
            self.assertAlmostEqual(made[p["key"]], p["betrag"], 2)

    def scenario(self, seed):
        rnd = random.Random(seed)
        cfg = core.merged_config(config_for_test(os.path.join(self.dir, "Belege")))
        cfg["darlehen"][0].pop("quelle_kommentar", None)
        cfg["gesellschaften"] = [
            dict(bereich=F.uid("pb"), beteiligung=F.uid(BET) + " | B", rueckwirkend_ab=rnd.choice(["", "2026-06-01", "alles"]), takt=rnd.choice(["taeglich", "monatlich"])),
            dict(bereich=F.uid("shs"), rueckwirkend_ab=rnd.choice(["", "alles"]), gegenkonten=[{"konto": F.uid(MINE) + " | M", "quelle": F.uid(THEIRS) + " | T"}])]
        self.store.save("config.json", cfg)
        for d, amt in ((date(2026, 8, 3), -700.0), (date(2026, 9, 9), 250.0)):          # there before the mirror is set up
            F_t = F.tx(THEIRS, d, amt, "Ich", "früher"); self.txs().append(F_t)
        self.frozen = {t["id"]: copy.deepcopy(t) for t in self.txs()}
        steps = []
        touched_mirror = False
        for i in range(18):
            auto = rnd.random() < 0.35
            cfg["probelauf"] = not auto
            act = rnd.choice(["sync", "sync", "approve", "approve", "reject", "delete", "change", "pay", "mirror", "again", "unmark",
                              "redate", "original", "renumber", "paydel"])
            steps.append(act + ("/auto" if auto else ""))
            where = "seed %d step %d (%s)" % (seed, i, " ".join(steps[-4:]))
            if act == "sync":
                self.run_once(cfg, not auto)
            elif act == "approve":
                self.approve(cfg, rnd)
            elif act == "reject":                                                   # "Don't book" (settings)
                rows = self.run_once(cfg, True)["vorschlaege"]
                if rows:
                    p = rnd.choice(rows)
                    cfg["nicht_buchen"] = [x for x in cfg.get("nicht_buchen") or [] if x["key"] != p["key"]] + [core.not_booked_entry(p, p["key"])]
            elif act == "delete" and self.kontor_txs():
                self.remove(rnd.choice(self.kontor_txs()))                      # you delete a booking of Kontor's in MoneyMoney
            elif act == "change":
                vals = [t for t in self.kontor_txs() if any(rules.is_value_tag(m) for m in marks_in(t["purpose"]))]
                if vals:
                    t = rnd.choice(vals); d = rnd.choice([-40.0, 15.5])
                    t["amount"] = round(t["amount"] + d, 2); b = self.balance(t["accountUuid"]); b[0] = round(b[0] + d, 2)
            elif act == "pay":                                                      # the company's value moves
                self.add("pb.kk", TODAY - timedelta(days=rnd.randint(0, 50)), rnd.choice([-1234.5, 800.0, 96.25]), "Zahlung")
            elif act == "mirror":                                                   # a new booking in one of the mirrored accounts
                self.add(rnd.choice([MINE, THEIRS]), TODAY - timedelta(days=rnd.randint(0, 20)), rnd.choice([-300.0, 120.0, 55.55]), "Einlage/Entnahme")
            elif act == "again" and cfg.get("nicht_buchen"):                       # "Propose again"
                cfg["nicht_buchen"].remove(rnd.choice(cfg["nicht_buchen"]))
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
            elif act == "renumber" and self.mine([MINE, THEIRS, "pb.kk"]):         # deleted and entered again in MoneyMoney: a new number
                t = rnd.choice(self.mine([MINE, THEIRS, "pb.kk"]))
                self.remove(t)
                again = self.add(next(k for k, u in F.U.items() if u == t["accountUuid"]), date(2026, 1, 1), t["amount"], t["purpose"])
                again.update({k: t[k] for k in ("bookingDate", "valueDate", "name", "accountNumber", "category", "categoryPath")})
                self.frozen[again["id"]] = copy.deepcopy(again)
            elif act == "paydel":                                                   # a loan payment deleted in MoneyMoney
                pays = [t for t in self.mine(["pb.kk"]) if t.get("accountNumber") == F.SELLER_IBAN]
                if pays:
                    self.remove(rnd.choice(pays))
            self.check(where)
        # in the end: everything approved until nothing is left
        cfg["probelauf"] = True

        cfg["nicht_buchen"] = []          # everything under "Not booked" proposed again
        for _ in range(8):
            if not self.run_once(cfg, True)["vorschlaege"]:
                break
            self.approve(cfg, rnd, part=False)
            self.check("seed %d settling" % seed)
        end = self.run_once(cfg, True)
        self.assertEqual(end["vorschlaege"], [], "seed %d: something is still to book" % seed)
        led = core.fetch(MockBridge(True), cfg, TODAY)
        value = sum(a.balance for a in led.descendants(F.uid("pb")))
        if cfg["gesellschaften"][0]["takt"] == "taeglich":          # daily: the participation is at share x value now
            self.assertAlmostEqual(led.accounts[F.uid(BET)].balance, round(0.49 * value, 2), 2, "seed %d: participation off" % seed)
        else:                                                        # monthly: at the end of last month
            end_of = date(TODAY.year, TODAY.month, 1) - timedelta(days=1)
            then = sum(led.balance_at(a.uuid, end_of) for a in led.descendants(F.uid("pb")))
            self.assertAlmostEqual(led.balance_at(F.uid(BET), end_of), round(0.49 * then, 2), 2, "seed %d: participation off at month end" % seed)
        # every booking of the mirrored accounts has its counterpart: the two balances moved by the same amounts
        mine = sorted(round(t["amount"], 2) for t in self.txs() if t["accountUuid"] == F.uid(MINE))
        theirs = sorted(round(-t["amount"], 2) for t in self.txs() if t["accountUuid"] == F.uid(THEIRS))
        if cfg["gesellschaften"][1]["rueckwirkend_ab"] == "alles" and not touched_mirror:      # (an original you changed: a note, Kontor changes nothing)
            self.assertEqual(mine, theirs, "seed %d: mirror incomplete" % seed)
        return steps

    def test_random_runs(self):
        for seed in range(40):
            reset_mock(); MockBridge.instances = []
            for name in ("state.json",):
                self.store.save(name, {})
            with self.subTest(seed=seed):
                self.scenario(seed)


if __name__ == "__main__":
    unittest.main(verbosity=1)
