import json
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from model import Ledger, accounts_from_export, tx_from_export  # noqa: E402
from rules import Seen, plan_loan, plan_all  # noqa: E402
from rules import mirrors as rules_mirrors  # noqa: E402
import fixtures as F  # noqa: E402


def loan_cfg(**over):
    cfg = {
        "name": "Verkäuferdarlehen",
        "loan_account": "Alpha GbR / Verbindlichkeiten / Verkäuferdarlehen",
        "source_accounts": ["Alpha GbR / Liquidität / Stadtbank Kontokorrent"],
        "detection": {"counter_iban": F.SELLER_IBAN, "text_contains": ["Urkunde 1234/2025"]},
        "from_date": "2026-01-01",
        "interest": {"model": "yearly_base", "rate_list": [{"from_date": "2025-11-20", "percent": 3.0}], "booking_day": "ultimo"},
        "booking": {"counterparty": "Verkäufer", "category_repayment": "Umbuchung", "category_interest": "Zinsen"},
    }
    cfg.update(over)
    return cfg


def make_ledger(balances, txs):
    return Ledger(accounts_from_export(F.accounts_raw(balances)), tx_from_export(txs))


class TreeTests(unittest.TestCase):
    def test_tree_and_paths(self):
        led = make_ledger({}, [])
        vd = led.resolve("Verkäuferdarlehen")
        self.assertEqual(vd.path, "Alpha GbR / Verbindlichkeiten / Verkäuferdarlehen")
        self.assertTrue(vd.offline)
        self.assertFalse(led.resolve("Hausbank Giro").offline)
        with self.assertRaises(KeyError):
            led.resolve("Stadtbank Kontokorrent")          # mehrdeutig (Alpha und Beta)
        self.assertEqual(led.resolve("Beta GbR / Liquidität / Stadtbank Kontokorrent").uuid, F.uid("gb.kk"))
        self.assertEqual(led.resolve("Liquidität / Stadtbank Kontokorrent" if False else F.uid("ga.kk")).name, "Stadtbank Kontokorrent")
        self.assertEqual([r.name for r in led.roots()], ["Privat", "Alpha GbR", "Beta GbR"])

    def test_uuid_label_references_and_hints(self):
        led = make_ledger({}, [])
        vd = led.resolve(F.uid("ga.vd") + " | Verkäuferdarlehen")
        self.assertEqual(vd.name, "Verkäuferdarlehen"); self.assertEqual(led.hints, [])
        # umbenannt: UUID gilt, Hinweis
        led.resolve(F.uid("ga.vd") + " | Alter Name")
        self.assertTrue(any("heißt jetzt" in h for h in led.hints))
        # UUID weg, Name vorhanden: Rueckfall + Hinweis mit neuer UUID
        led2 = make_ledger({}, [])
        acc = led2.resolve("00000000-0000-0000-0000-000000000000 | Verkäuferdarlehen")
        self.assertEqual(acc.uuid, F.uid("ga.vd"))
        self.assertTrue(any("Neue UUID" in h for h in led2.hints))
        with self.assertRaises(KeyError):
            led2.resolve("00000000-0000-0000-0000-000000000000 | Gibt es nicht")
        # Offline-Erkennung: Extension-Konto ohne BLZ, aber aktualisiert -> nicht manuell
        from model import Account
        ext = Account(uuid="x", name="PayPal", type="Girokonto", group=False, indentation=3, balance=0.0, currency="EUR",
                      bank_code="", refresh=__import__("datetime").datetime(2026, 11, 4, 8, 0))
        self.assertFalse(ext.offline)
        self.assertTrue(led.resolve("Verkäuferdarlehen").offline)

    def test_balance_at(self):
        txs = F.ga_transactions(date(2026, 11, 4))
        led = make_ledger({"ga.kk": 40000.0}, txs)
        # KK-Saldo am 31.12.2025 = heute - alle Buchungen 2026 (11 x -6000)
        self.assertAlmostEqual(led.balance_at(F.uid("ga.kk"), date(2025, 12, 31)), 40000 + 11 * 6000, 2)
        # Datumskonvertierung: lokale Mitternacht -> Datum bleibt der 1.
        kk = led.transactions(F.uid("ga.kk"))
        self.assertEqual(kk[0].booking_date, date(2026, 1, 1))


class LoanTests(unittest.TestCase):
    def test_first_run_books_all_months(self):
        today = date(2026, 11, 4)
        led = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today))
        res = plan_loan(led, loan_cfg(), today)
        tilg = [p for p in res.proposals if p.kind == "repayment"]
        zins = [p for p in res.proposals if p.kind == "interest"]
        self.assertEqual(len(tilg), 11)                      # Jan..Nov
        self.assertEqual(len(zins), 10)                      # Jan..Okt (Nov-Ultimo liegt in der Zukunft)
        self.assertEqual({p.kind for p in res.proposals}, {"repayment", "interest"})        # the payments themselves are never touched
        self.assertTrue(all(p.account_uuid == led.resolve(loan_cfg()["loan_account"]).uuid for p in res.proposals))
        self.assertTrue(all(p.amount == 6000.0 for p in tilg))
        self.assertTrue(all(p.amount == -3000.0 for p in zins))   # 1.200.000 x 3,0 % / 12
        self.assertEqual(zins[0].booking_date, date(2026, 1, 31))
        self.assertIn("#kontor-zins-2026-01", zins[0].purpose)
        self.assertIn("#kontor-tx-", tilg[0].purpose)
        self.assertTrue(tilg[0].purpose.startswith("Annuität "))
        # In-Memory-Saldo nach allen Buchungen
        vd = led.resolve("Verkäuferdarlehen")
        self.assertAlmostEqual(vd.balance, -1200000 + 11 * 6000 - 10 * 3000, 2)
        self.assertFalse(res.warnings, res.warnings)

    def test_idempotent_second_run(self):
        today = date(2026, 11, 4)
        led = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today))
        res1 = plan_loan(led, loan_cfg(), today)
        # Zweiter Lauf: Buchungen "existieren" jetzt im Ledger (in-memory) -> nichts Neues
        res2 = plan_loan(led, loan_cfg(), today)
        self.assertTrue(res1.proposals)
        self.assertEqual(res2.proposals, [])

    def test_december_remainder_is_cent_exact(self):
        today = date(2027, 1, 5)
        led = make_ledger({"ga.vd": -1234567.0}, [F.tx("ga.vd", date(2025, 12, 1), -1234567.0, "V", "Start")])
        cfg = loan_cfg(source_accounts=[], expected_monthly=False)
        res = plan_loan(led, cfg, today)
        zins = [p for p in res.proposals if p.kind == "interest" and p.booking_date.year == 2026]
        self.assertEqual(len(zins), 12)
        total = round(sum(-p.amount for p in zins), 2)
        self.assertAlmostEqual(total, round(1234567.0 * 0.03, 2), 2)

    def test_year_base_follows_prior_year_end_and_sondertilgung(self):
        # Sondertilgung im Maerz 2026 aendert 2026 nichts, 2027 schon
        today = date(2027, 2, 15)
        extra = [F.tx("ga.kk", date(2026, 3, 15), -50000.0, "Verkäufer", "Sondertilgung " + F.ANNUITY_TEXT, "", F.SELLER_IBAN)]
        txs = F.ga_transactions(today, extra=extra)
        led = make_ledger({"ga.vd": -1200000.0}, txs)
        res = plan_loan(led, loan_cfg(), today)
        z26 = [p for p in res.proposals if p.kind == "interest" and p.booking_date.year == 2026]
        z27 = [p for p in res.proposals if p.kind == "interest" and p.booking_date.year == 2027]
        self.assertTrue(all(p.amount == -3000.0 for p in z26))
        # Basis 2027 = Stand 31.12.2026 = -1.200.000 + 12*6.000 + 50.000 - 36.000 Zinsen
        base27 = 1200000 - 12 * 6000 - 50000 + 36000
        self.assertEqual(len(z27), 1)
        self.assertAlmostEqual(z27[0].amount, -round(round(base27 * 0.03, 2) / 12, 2), 2)
        sonder = [p for p in res.proposals if p.kind == "repayment" and p.amount == 50000.0]
        self.assertEqual(len(sonder), 1)
        self.assertTrue(sonder[0].purpose.startswith("Sondertilgung "))

    def test_manual_interest_guard_and_ab_datum(self):
        today = date(2026, 11, 4)
        # Jan..Okt manuell gebucht, Automatik ab 2026-11-01
        txs = F.ga_transactions(today, with_manual_interest_until=date(2026, 10, 1))
        led = make_ledger({"ga.vd": -1200000.0 + 10 * 6000 - 10 * 3000}, txs)
        res = plan_loan(led, loan_cfg(from_date="2026-11-01"), today)
        tilg = [p for p in res.proposals if p.kind == "repayment"]
        zins = [p for p in res.proposals if p.kind == "interest"]
        self.assertEqual(len(tilg), 1)                       # nur November
        self.assertEqual(len(zins), 0)                       # November-Ultimo noch nicht erreicht
        # Basis 2026 bleibt der Stand 31.12.2025 trotz manueller Buchungen
        self.assertTrue(any("Zinsbasis 2026 = 1.200.000,00" in i for i in res.info), res.info)
        # repayments and interest you booked yourself (no mark): the repayments count as booked, the months of your interest
        # are left to you -- one note, no warning, nothing twice
        txs2 = F.ga_transactions(today, with_manual_interest_until=date(2026, 10, 1))
        led2 = make_ledger({"ga.vd": -1200000.0}, txs2)
        res2 = plan_loan(led2, loan_cfg(from_date="2026-01-01"), today)
        self.assertEqual(len([p for p in res2.proposals if p.kind == "interest"]), 0)
        self.assertEqual([p.booking_date for p in res2.proposals if p.kind == "repayment"], [date(2026, 11, 1)])
        self.assertFalse(res2.warnings, res2.warnings)
        own = [i for i in res2.info if "selbst gebucht" in i]
        self.assertEqual(len(own), 1); self.assertIn("01/2026", own[0]); self.assertIn("10/2026", own[0])

    def test_missing_base_warns(self):
        today = date(2026, 6, 1)
        led = make_ledger({"ga.vd": -1200000.0}, [F.tx("ga.vd", date(2026, 2, 1), -1200000.0, "V", "Start")])
        res = plan_loan(led, loan_cfg(source_accounts=[], expected_monthly=False), today)
        self.assertTrue(any("Jahresanfangsbasis" in w for w in res.warnings))
        self.assertEqual([p for p in res.proposals if p.kind == "interest"], [])
        cfg = loan_cfg(source_accounts=[], expected_monthly=False)
        cfg["interest"]["base_override"] = {"2026": 1200000}
        res = plan_loan(led, cfg, today)
        self.assertEqual(len([p for p in res.proposals if p.kind == "interest"]), 5)

    def test_restschuld_monatlich_model(self):
        today = date(2026, 4, 2)
        txs = [F.tx("ga.vd", date(2025, 12, 1), -120000.0, "Bank", "Auszahlung")]
        for m in (1, 2, 3):
            txs.append(F.tx("ga.kk", date(2026, m, 1), -1000.0, "Bank", "Rate " + F.ANNUITY_TEXT, "", F.SELLER_IBAN))
        led = make_ledger({"ga.vd": -120000.0}, txs)
        cfg = loan_cfg(interest={"model": "remaining_debt_monthly", "rate_list": [{"from_date": "2025-12-01", "percent": 6.0}]})
        res = plan_loan(led, cfg, today)
        zins = [p for p in res.proposals if p.kind == "interest"]
        # Jan: 120.000 x 6 %/12 = 600; Feb: (120.000-1.000+600) ... Restschuld nach Rate und Zins
        self.assertEqual(len(zins), 3)
        self.assertAlmostEqual(zins[0].amount, -600.0, 2)
        self.assertAlmostEqual(zins[1].amount, -round((120000 - 1000 + 600) * 0.06 / 12, 2), 2)

    def test_no_payment_warning(self):
        today = date(2026, 11, 4)
        led = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(date(2026, 8, 1)))
        res = plan_loan(led, loan_cfg(), today)
        self.assertTrue(any("seit über 35 Tagen" in w for w in res.warnings))
        # Automatik gerade erst gestartet, Rate noch nicht gelaufen: nur Info
        led = make_ledger({"ga.vd": -1200000.0}, [F.tx("ga.vd", date(2025, 12, 1), -1200000.0, "V", "Start")])
        res = plan_loan(led, loan_cfg(from_date="2026-11-01"), today)
        self.assertFalse(any("keine passende Zahlung" in w for w in res.warnings))
        self.assertTrue(any("keine passende Zahlung" in i for i in res.info))
        # IBAN-only Erkennung mit Ausschlusstext
        txs = F.ga_transactions(today, extra=[F.tx("ga.kk", date(2026, 10, 20), -300.0, "Verkäufer", "Nebenkostenabrechnung", "", F.SELLER_IBAN)])
        led = make_ledger({"ga.vd": -1200000.0}, txs)
        cfg = loan_cfg(detection={"counter_iban": F.SELLER_IBAN, "exclude_text": ["Nebenkosten"]})
        res = plan_loan(led, cfg, today)
        self.assertEqual(len([p for p in res.proposals if p.kind == "repayment"]), 11)


def company_cfg(**over):
    cfg = {"areas": [{"id": "p", "name": "Privat", "kind": "private", "main_area": True, "accounts": [F.uid("priv") + " | Privat"]},
                        {"id": "a", "name": "Alpha GbR", "kind": "company", "share": 0.4, "accounts": [F.uid("ga") + " | Alpha GbR"]},
                        {"id": "b", "name": "Beta GbR", "kind": "company", "share": 0.4, "accounts": [F.uid("gb") + " | Beta GbR"]}],
           "companies": [{"area": "a", "participation": F.uid("priv.bet.ga") + " | Beteiligung an Alpha GbR"}]}
    cfg.update(over)
    return cfg


class RoundingTests(unittest.TestCase):
    def test_half_a_cent_goes_up(self):
        """Amounts are rounded as in commerce: half a cent away from zero -- not to the even cent, not by the binary form."""
        from model import cents
        self.assertEqual([cents(x) for x in (0.625, 0.615, 1.005, 2.675, 625.025, -0.625, 0.0, 12.344999, 49001.225)],
                         [0.63, 0.62, 1.01, 2.68, 625.03, -0.63, 0.0, 12.34, 49001.23])
        self.assertEqual(round(0.625, 2), 0.62)                      # what round() alone would do
        # interest of a month on 150.00 at 5 %: 0.625 -> 0.63
        today = date(2026, 11, 4)
        led = make_ledger({"ga.vd": -150.0}, [])
        cfg = company_cfg(companies=[], loans=[loan_cfg(from_date="2026-10-01", interest={
            "model": "remaining_debt_monthly", "rate_list": [{"from_date": "2025-11-20", "percent": 5.0}], "booking_day": "ultimo"})])
        res = plan_all(led, cfg, today)
        zins = [p for p in res.proposals if p.kind == "interest"]
        self.assertEqual([abs(p.amount) for p in zins], [0.63], [(p.kind, p.amount) for p in res.proposals])


class CompanyTests(unittest.TestCase):
    def test_participation_value(self):
        today = date(2026, 11, 4)
        led = make_ledger({}, [])
        res = plan_all(led, company_cfg(), today)
        ga_value = 40000 + 1500000 - 1200000 - 120000 - 120000      # = 100.000 (capital accounts are debts of the company)
        want = round(0.4 * ga_value, 2)
        self.assertEqual(len(res.proposals), 1)
        self.assertEqual((res.proposals[0].kind, res.proposals[0].booking_date), ("value", today))
        self.assertAlmostEqual(res.proposals[0].amount, want - (-90000.0), 2)
        self.assertEqual(led.resolve("Beteiligung an Alpha GbR").balance, want)
        items = [dict(pv).pop("items", None) for pv in res.preview]                # what it would book, for the side panel
        self.assertEqual([(x["date"], x["amount"]) for x in items[0]], [(today.isoformat(), round(want + 90000.0, 2))])
        self.assertEqual([{k: v for k, v in pv.items() if k != "items"} for pv in res.preview], [{"kind": "participation", "area": "a", "target": F.uid("priv.bet.ga"), "ist": -90000.0, "retro_count": 0, "open": 1,
                                        "back_sum": 0.0, "unknown": [], "cycle": "daily", "soll": want, "source": float(ga_value), "diff": want + 90000.0,
                                        "begin": None}])
        self.assertEqual(plan_all(led, company_cfg(), today).proposals, [])        # again: nothing
        # an account of the company in another currency: Kontor does not convert, so the value is unknown -- nothing is booked
        # (not its amount taken as euros), and it says why; out of the value (your choice), the rest is booked as before
        raw = F.accounts_raw({})
        usd = next(a for a in raw if a["uuid"] == F.uid("ga.kk")); usd["currency"] = "USD"; usd["balance"] = [[40000.0, "USD"]]
        fx = Ledger(accounts_from_export(raw), tx_from_export([]))
        res = plan_all(fx, company_cfg(), today)
        self.assertEqual(res.proposals, [])
        self.assertTrue(any("anderen Währung" in i and "Stadtbank Kontokorrent" in i for i in res.warnings), res.warnings)
        self.assertEqual([(pv["soll"], pv["source"], pv["diff"], pv["open"]) for pv in res.preview], [(None, None, None, 0)])
        res = plan_all(fx, company_cfg(balance={"roles": {F.uid("ga.kk"): "ignore"}}), today)
        self.assertEqual([round(p.amount, 2) for p in res.proposals], [round(0.4 * (ga_value - 40000) + 90000.0, 2)])
        # the share comes only from the area; without it nothing is booked
        cfg = company_cfg(); cfg["areas"][1].pop("share")
        res = plan_all(make_ledger({}, []), cfg, today)
        self.assertEqual(res.proposals, []); self.assertTrue(any("Anteil fehlt" in w for w in res.warnings))

    def test_loans_before_participation_and_equity_roles(self):
        today = date(2026, 11, 4)
        led = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today))
        config = company_cfg(loans=[loan_cfg()])
        res = plan_all(led, config, today)
        wert = [p for p in res.proposals if p.kind == "value"]
        self.assertEqual(len(wert), 1)
        ga_value = 40000 + 1500000 + (-1200000 + 11 * 6000 - 10 * 3000) - 240000
        self.assertAlmostEqual(wert[0].amount, round(0.4 * ga_value, 2) + 90000.0, 2)
        # capital accounts left out of the balance sheet (contingent/ignored) are not part of its value
        led2 = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today))
        config["balance"] = {"roles": {F.uid("ga.kap.a") + " | Kapitalkonto A": "ignore", F.uid("ga.kap.b") + " | Kapitalkonto B": "ignore"}}
        wert2 = [p for p in plan_all(led2, config, today).proposals if p.kind == "value"]
        self.assertAlmostEqual(wert2[0].amount, round(0.4 * (ga_value + 240000), 2) + 90000.0, 2)

    def test_counter_account(self):
        """A counter account mirrors each booking (see MirrorTests); its text names the original account."""
        today = date(2026, 11, 4)
        led = make_ledger({}, [F.tx("gb.kap.a", date(2026, 9, 1), -5000.0, "Ich", "Einlage")])
        cfg = company_cfg(companies=[{"area": "b", "retroactive_from": "all"}], account_mirrors=[
            {"a": F.uid("priv.bet.gb") + " | Beteiligung an Beta GbR", "b": F.uid("gb.kap.a") + " | Kapitalkonto A", "from_date": "all"}])
        res = plan_all(led, cfg, today)
        self.assertEqual([(p.kind, p.amount, p.booking_date) for p in res.proposals], [("mirror", 5000.0, date(2026, 9, 1))])
        self.assertTrue(res.proposals[0].tag.startswith("#kontor-gk-"))
        self.assertIn("Einlage · gespiegelt von Kapitalkonto A · #kontor-gk-", res.proposals[0].purpose)
        self.assertEqual(res.proposals[0].payee, "Beta GbR")              # the sender is the company, not its account
        self.assertEqual(res.preview[0]["i"], 0)

    def test_back_to_month_ends(self):
        today = date(2026, 11, 4)
        led = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today))
        cfg = company_cfg(loans=[loan_cfg()])
        cfg["companies"][0].update(retroactive_from="2026-03-01", cycle="monthly")
        res = plan_all(led, cfg, today, seen=Seen(Seen.top_id(led), today))
        wert = [p for p in res.proposals if p.kind == "value"]
        days = [p.booking_date for p in wert]
        self.assertEqual(days[:8], [date(2026, m + 1, 1) - timedelta(days=1) for m in range(3, 11)])      # 31.03. ... 31.10.
        target = led.resolve("Beteiligung an Alpha GbR")
        for p in wert[:8]:          # each month end shows the share of the company's value at that day
            accs = [a for a in led.descendants(F.uid("ga"))]
            v = round(sum(led.balance_at(a.uuid, p.booking_date) for a in accs), 2)
            self.assertAlmostEqual(led.balance_at(target.uuid, p.booking_date), round(0.4 * v, 2), 2)
        self.assertEqual(len({p.tag for p in wert}), len(wert))
        pv = [x for x in res.preview if x["kind"] == "participation"][0]
        self.assertEqual(pv["retro_count"], 8); self.assertTrue(all(p.retro and p.group == "a" for p in wert))
        self.assertEqual(len(wert), 8)                  # monthly: no booking today, the month runs until its end
        # a second run books nothing (the bookings are there now, every month end is checked again and right); a month later
        # only the month just ended -- new, so booked without asking when booking fully automatically
        self.assertEqual([p for p in plan_all(led, cfg, today).proposals if p.kind == "value"], [])
        later = plan_all(led, cfg, date(2026, 12, 2), seen=Seen(Seen.top_id(led), today))
        self.assertEqual([x for x in later.preview if x["kind"] == "participation"][0]["retro_count"], 0)
        self.assertEqual([(p.booking_date, p.retro) for p in later.proposals if p.kind == "value"], [(date(2026, 11, 30), False)])

    def test_back_to_daily(self):
        """Daily (default): back to every day on which the company's value changed, then today; once done only today."""
        today = date(2026, 11, 4)
        led = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today))
        cfg = company_cfg(loans=[loan_cfg()])
        cfg["companies"][0]["retroactive_from"] = "2026-03-01"
        res = plan_all(led, cfg, today, seen=Seen(Seen.top_id(led), today))
        wert = [p for p in res.proposals if p.kind == "value"]
        target = led.resolve("Beteiligung an Alpha GbR")
        change_days = sorted({t.booking_date for a in led.descendants(F.uid("ga")) for t in led.transactions(a.uuid) if date(2026, 3, 1) <= t.booking_date < today})
        self.assertTrue(set(p.booking_date for p in wert if p.retro) <= set(change_days) | {date(2026, 3, 1)})
        for d in change_days:
            v = round(sum(led.balance_at(a.uuid, d) for a in led.descendants(F.uid("ga"))), 2)
            self.assertAlmostEqual(led.balance_at(target.uuid, d), round(0.4 * v, 2), 2)
        self.assertAlmostEqual(target.balance, res.preview[-1]["soll"], 2)
        self.assertTrue(wert and all(p.retro for p in wert))          # the past waits for you (nothing new since the last check) ...
        self.assertEqual([p for p in plan_all(led, cfg, today).proposals if p.kind == "value"], [])        # all there: nothing
        # ... and left out, today's value is booked at once: the difference of all of them
        led3 = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today))
        seen, hold = Seen(Seen.top_id(led3), today), set()
        for rounds in range(1, 9):                    # as a run does: left out, planned again, until nothing depends on it
            held = plan_all(led3.fork(), cfg, today, hold=hold, seen=seen)
            more = {p.key for p in held.proposals if p.retro} - hold
            if not more:
                break
            hold |= more
        self.assertLess(rounds, 5)
        now = [p for p in held.proposals if p.kind == "value"]
        self.assertEqual([(p.booking_date, p.retro) for p in now], [(today, False)])
        self.assertAlmostEqual(now[0].amount, round(0.4 * sum(a.balance for a in led3.descendants(F.uid("ga"))) + 90000.0, 2), delta=0.05)

    def test_back_to_a_day_or_everything(self):
        """"Rückwirkend ab": a day (monthly: the month ends from then on) or "alles" (since the company's first transaction)."""
        today = date(2026, 11, 4)
        led = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today))
        cfg = company_cfg(loans=[loan_cfg()])
        cfg["companies"][0].update(retroactive_from="2026-03-15", cycle="monthly")
        days = [p.booking_date for p in plan_all(led, cfg, today).proposals if p.kind == "value"]
        self.assertEqual(days[0], date(2026, 3, 31)); self.assertEqual(days[-1], date(2026, 10, 31))
        led = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today))
        cfg["companies"][0].update(retroactive_from="all", cycle="daily")
        res = plan_all(led, cfg, today, seen=Seen(Seen.top_id(led), today))
        first = min(t.booking_date for a in led.descendants(F.uid("ga")) for t in led.transactions(a.uuid) if t.id > 0)
        retro = [p for p in res.proposals if p.kind == "value" and p.retro]
        self.assertTrue(retro); self.assertGreaterEqual(min(p.booking_date for p in retro), first)
        self.assertEqual(min(p.booking_date for p in retro), first)          # the first day already differs (opening balance)

    def test_legacy_start_keeps_the_month_just_ended(self):
        """Without "Buchen ab" (not written by the interface): since Kontor's first booking -- a booking of Kontor's you moved into the
        next month does not leave the month just ended out (found by the nightly random runs)."""
        today = date(2026, 11, 4)
        led = make_ledger({}, [])
        cfg = company_cfg(); cfg["companies"][0].update(retroactive_from="", cycle="monthly")
        w = [p for p in plan_all(led, cfg, today).proposals if p.kind == "value"]
        self.assertEqual([p.booking_date for p in w], [date(2026, 10, 31)])
        real = led.without_planned(keep=[p.key for p in w])
        next(t for t in real.txs if w[0].tag in t.purpose).booking_date = date(2026, 11, 2)          # you moved it into November
        again = [p for p in plan_all(real.fork(), cfg, today).proposals if p.kind == "value"]
        self.assertEqual([(p.booking_date, round(p.amount, 2)) for p in again], [(date(2026, 10, 31), round(w[0].amount, 2))])

    def test_back_to_unknown_months_skipped(self):
        # a portfolio in the company: its past value is not known -> those months are not booked
        today = date(2026, 11, 4)
        led = make_ledger({}, [])
        cfg = company_cfg(areas=[{"id": "a", "name": "Alpha GbR", "kind": "company", "share": 0.5,
                                     "accounts": [F.uid("ga") + " | Alpha GbR", F.uid("priv.depot") + " | Depot"]},
                                    {"id": "p", "name": "Privat", "kind": "private", "main_area": True, "accounts": [F.uid("priv.bet") + " | Beteiligungen"]}])
        cfg["companies"][0].update(retroactive_from="2026-09-01", cycle="monthly")
        res = plan_all(led, cfg, today)
        self.assertEqual([p.booking_date for p in res.proposals], [])
        self.assertEqual(res.preview[0]["unknown"], ["09/2026", "10/2026"])
        self.assertTrue(any("unbekannt" in i for i in res.info))

    def test_writable_manual_accounts(self):
        """MoneyMoney sets a fetch time on a manual account after a booking, and a bank code can be typed into a manual
        account: several signs count, your own choice (Sync: "retrieved") comes first."""
        from datetime import datetime

        def led_with(changes, txs=()):
            raw = F.accounts_raw({})
            for a in raw:
                a.update(changes.get(a["uuid"], {}))
            return Ledger(accounts_from_export(raw), tx_from_export(list(txs)))
        vd, bet, giro = F.uid("ga.vd"), F.uid("priv.bet.ga"), F.uid("priv.giro")
        fetched = {"refreshTimestamp": datetime(2026, 10, 1)}
        led = led_with({vd: fetched, bet: fetched})
        self.assertTrue(led.writable(bet))                                   # type "Offline-Konto"
        self.assertTrue(led.writable(vd))                                    # manual bookings: fetch time, but no bank code or number
        self.assertFalse(led.writable(giro)); self.assertFalse(led.writable(F.uid("ga"))); self.assertFalse(led.writable(F.uid("priv.depot")))
        # a bank code typed into a manual account
        blz = dict(fetched, bankCode="70150000")
        self.assertFalse(led_with({vd: blz}).writable(vd))
        self.assertTrue(led_with({vd: {"bankCode": "70150000"}}).writable(vd))          # never fetched
        self.assertTrue(led_with({vd: blz}).writable(vd, {"fetch": {"offline": [vd + " | Verkäuferdarlehen"]}}))      # your choice
        self.assertTrue(led_with({vd: blz}, [F.tx("ga.vd", date(2026, 9, 30), -10.0, "x", "Zinsen 09/2026 · #kontor-zins-2026-09")]).writable(vd))
        led2 = led_with({vd: blz}); led2.post(vd, date(2026, 11, 4), 1.0, "x", "#kontor-wert-20261104-1")
        self.assertFalse(led2.writable(vd))                                  # a booking planned in this run does not count
        self.assertFalse(led.writable(bet, {"fetch": {"online": [bet + " | Beteiligung an Alpha GbR"]}}))
        # the rules use it
        self.assertEqual(len(plan_all(led_with({bet: fetched}), company_cfg(), date(2026, 11, 4)).proposals), 1)
        res = plan_all(led_with({bet: dict(fetched, bankCode="12030000", type="Girokonto")}), company_cfg(), date(2026, 11, 4))
        self.assertEqual(res.proposals, []); self.assertTrue(any("Bankanbindung" in w for w in res.warnings))

    def test_circular_reference_rejected(self):
        led = make_ledger({}, [])
        cfg = company_cfg(companies=[{"area": "a", "participation": F.uid("ga.immo") + " | Immobilie Parkweg"}])
        res = plan_all(led, cfg, date(2026, 11, 4))
        self.assertTrue(any("Zirkelbezug" in w for w in res.warnings))
        self.assertEqual(res.proposals, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)


class CatalogTests(unittest.TestCase):
    """Texte fuer den Nutzer: ein Katalog (web/i18n.js), jeder benutzte Schluessel mit Deutsch und Englisch, gleiche Platzhalter."""

    def test_katalog_vollstaendig(self):
        import glob
        import re
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        txt = open(os.path.join(here, "web", "i18n.js"), encoding="utf-8").read()
        cat = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        js = open(os.path.join(here, "web", "app.js"), encoding="utf-8").read()
        html = open(os.path.join(here, "web", "index.html"), encoding="utf-8").read()
        used = set(re.findall(r"\bt[xn]?\('(\w+)'", js)) | set(re.findall(r'data-i18n(?:-ph|-aria)?="(\w+)"', html))
        for f in glob.glob(os.path.join(here, "*.py")):
            used |= set(re.findall(r'\btr\("(\w+)"', open(f, encoding="utf-8").read()))
        self.assertFalse(sorted(used - set(cat)), "Schluessel fehlen im Katalog")
        ph = re.compile(r"\{\d+\}|%[sdr%]|%0?\d*d|\{[a-z]+\}")
        for k, v in cat.items():
            self.assertEqual(len(v), 2, k)
            self.assertTrue(v[0] and v[1], k)
            self.assertEqual(sorted(ph.findall(v[0])), sorted(ph.findall(v[1])), k)
            self.assertEqual(sorted(re.findall(r"</?\w+", v[0])), sorted(re.findall(r"</?\w+", v[1])), k)

    def test_tr_sprache(self):
        import i18n
        i18n.set_lang("en")
        try:
            self.assertEqual(i18n.tr("s_moneymoney_laeuft_nicht"), "MoneyMoney is not running.")
            self.assertEqual(i18n.tr("cf_ausgaben_vorjahre", 2), "Expenses compared with 2 years before")
        finally:
            i18n.set_lang("de")
        self.assertEqual(i18n.tr("cf_ausgaben_vorjahre", 2), "Ausgaben im Vergleich zu 2 Jahren davor")
        self.assertEqual(i18n.tr("unbekannter_schluessel"), "unbekannter_schluessel")


class TransitTests(unittest.TestCase):
    """Geld unterwegs: Umbuchung zwischen eigenen Konten ueber das Monatsende."""

    def ledger(self, txs):
        from model import Account, Tx
        acc = {u: Account(uuid=u, name=u, type="Giro", group=False, indentation=0, balance=0.0, currency="EUR", iban=iban)
               for u, iban in (("a", "DE11"), ("b", "DE22"), ("x", "DE33"))}
        return Ledger(acc, [Tx(id=i, account_uuid=u, booking_date=d, value_date=d, amount=amt, currency="EUR", counter_iban=ib)
                            for i, (u, d, amt, ib) in enumerate(txs, 1)])

    def run_transit(self, txs, today=date(2026, 3, 15)):
        from report import transit_series
        L = self.ledger(txs)
        leaves = [L.accounts["a"], L.accounts["b"]]
        out, details = transit_series(L, leaves, {"a": "cash", "b": "cash"}, [(2026, 1), (2026, 2), (2026, 3)], {}, today)
        self.assertEqual(len(details), sum(1 for v in out.values() if v))
        return out

    def test_ueber_monatsende(self):
        t = self.run_transit([("a", date(2026, 1, 31), -500.0, "DE22"), ("b", date(2026, 2, 2), 500.0, "")])
        self.assertEqual(t, {"2026-01": 500.0, "2026-02": 0.0, "2026-03": 0.0})

    def test_laufender_monat_ohne_unterwegs(self):
        # today's balances hold every booking, also one dated after today: in the running month nothing is on its way
        t = self.run_transit([("a", date(2026, 2, 27), -300.0, "DE22"), ("b", date(2026, 3, 4), 300.0, "")], today=date(2026, 3, 2))
        self.assertEqual(t, {"2026-01": 0.0, "2026-02": 300.0, "2026-03": 0.0})

    def test_gutschrift_zuerst(self):
        t = self.run_transit([("b", date(2026, 1, 30), 200.0, "DE11"), ("a", date(2026, 2, 1), -200.0, "")])
        self.assertEqual(t["2026-01"], -200.0)

    def test_nicht_gepaart(self):
        # gleicher Monat, kein IBAN-Bezug, zu weit auseinander, Partner ausserhalb des Bereichs -> nichts unterwegs
        for txs in ([("a", date(2026, 2, 10), -100.0, "DE22"), ("b", date(2026, 2, 11), 100.0, "")],
                    [("a", date(2026, 1, 31), -100.0, ""), ("b", date(2026, 2, 1), 100.0, "")],
                    [("a", date(2026, 1, 25), -100.0, "DE22"), ("b", date(2026, 2, 3), 100.0, "")],
                    [("a", date(2026, 1, 31), -100.0, "DE33"), ("x", date(2026, 2, 1), 100.0, "DE11")]):
            self.assertEqual(set(self.run_transit(txs).values()), {0.0}, txs)


class ChangelogTests(unittest.TestCase):
    def test_abschnitt_und_datum(self):
        import updates
        self.assertEqual(updates.changelog_section("# X\n\n## 1.2.3 (2026-01-02)\n- a\n\n## 1.2.2\n- b\n", "1.2.3"), ("- a", "2026-01-02"))
        self.assertEqual(updates.changelog_section("## 1.2.2\n- b\n", "1.2.2"), ("- b", ""))

    def test_seit_installierter_version(self):
        """Update over several versions: every point since the installed one, one list, newest first, same topic together,
        no duplicates, nothing for development only."""
        import updates
        cl = ("# X\n\n## 1.2.5 (2026-01-05 10:00)\n- KI-Assistent: c\n- Entwicklung: Tests\n\n## 1.2.4\n- Bilanz: b\n\n"
              "## 1.2.3\n- KI-Assistent: a\n- Bilanz: b\n- frei\n\n## 1.2.2\n- installiert\n")
        self.assertEqual(updates.changelog_since(cl, "1.2.2", "1.2.5"),
                         ("- KI-Assistent: c\n- KI-Assistent: a\n- Bilanz: b\n- frei", "2026-01-05 10:00", "1.2.3"))
        self.assertEqual(updates.changelog_since(cl, "1.2.4", "1.2.5"), ("- KI-Assistent: c", "2026-01-05 10:00", "1.2.5"))
        self.assertEqual(updates.changelog_since(cl, "1.2.5", "1.2.5"), ("", "", ""))

    def test_aktuelle_version_hat_datum(self):
        import updates
        here = os.path.join(os.path.dirname(__file__), "..")
        with open(os.path.join(here, "CHANGELOG.md"), encoding="utf-8") as f:
            text = f.read()
        notes, datum = updates.changelog_section(text, updates.current_version())
        self.assertTrue(notes); self.assertRegex(datum, r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?$")


class GoalTests(unittest.TestCase):
    """The user's goal for Kontor (ROADMAP.md, CLAUDE.md) must survive parallel chats: a version that drops it fails here."""

    def _read(self, name):
        with open(os.path.join(os.path.dirname(__file__), "..", name), encoding="utf-8") as f:
            return f.read()

    def test_goal_stays_in_the_roadmap(self):
        text = self._read("ROADMAP.md")
        for heading in ("## Ziel: dein digitaler CFO", "## Leitlinien", "## Entschieden", "## Offen"):
            self.assertIn("\n" + heading, text, heading)
        for words in ("Kein Haushaltsbuch", "Von der Gesellschaft ins Privatvermögen", "Gesellschaften auch führen",
                      "Der KI-Assistent ist der Kern", "**Sicherheit.**", "**Automatik:**", "**Daten erst nach Anmeldung:**",
                      "**Data-Warehouse (BigQuery):**", "**Reihenfolge:**", "**Name:**", "ELSTER", "gemeinsame KI"):
            self.assertIn(words, text, words)

    def test_goal_stays_in_the_rules(self):
        text = self._read("CLAUDE.md")
        self.assertIn("\n## Ziel\n", text)
        self.assertIn("digitale Finanzchef (CFO)", text)
        self.assertIn("ROADMAP.md", text.split("\n## Ziel\n")[1].split("\n## ")[0])

class PortfolioHistoryTests(unittest.TestCase):
    """Month-end values of a portfolio from MoneyMoney's portfolio_chart (made-up values)."""

    def _db(self, chart, securities):
        import sqlite3
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE portfolio_chart(account_key INTEGER, currency TEXT, timestamp INTEGER, balance REAL, securities_key INTEGER)")
        con.execute("CREATE TABLE securities(rowid INTEGER PRIMARY KEY, account_key INTEGER, quantity REAL, deleted INTEGER, name TEXT, isin TEXT, comment TEXT)")
        from datetime import datetime as DT
        ts = lambda d: int(DT(d.year, d.month, d.day, 12).timestamp())
        con.executemany("INSERT INTO portfolio_chart VALUES(1, 'EUR', ?, ?, ?)", [(ts(d), v, sk) for d, v, sk in chart])
        con.executemany("INSERT INTO securities VALUES(?, 1, ?, ?, ?, ?, 'GEHEIM')", [tuple(x) + ("Titel %d" % x[0], "XX%010d" % x[0])[len(x) - 3:] for x in securities])

        class DB:
            rows = lambda self, sql, params=(): con.execute(sql, params).fetchall()
            one = lambda self, sql, params=(): con.execute(sql, params).fetchone()
        return DB()

    def test_replaced_position_counts_until_the_next_update(self):
        # like a crowdinvesting account: one investment (points only when it changes), a cash position that appears in October
        # and is replaced by a new one (new row, the old one deleted) at the next update in November -> October includes it
        import mm_history as H
        from datetime import date as D
        chart = [(D(2026, 8, 3), 1000.0, 1), (D(2026, 10, 9), 0.30, 2), (D(2026, 10, 30), 0.30, 2), (D(2026, 11, 6), -0.30, 3)]
        db = self._db(chart, [(1, 1, 0), (2, 0, 1), (3, 1, 0)])
        r = H._portfolios(db, ["portfolio_chart", "securities"], [1], lambda k: {"balance_amount": 999.70}, D(2026, 11, 8))[1]
        self.assertEqual(r["amounts"]["2026-09"], 1000.0); self.assertEqual(r["amounts"]["2026-10"], 1000.3)

    def test_sold_position_ends_at_the_next_update(self):
        # sold in June: the next update (June 20) no longer has it -> not in the June month end
        import mm_history as H
        from datetime import date as D
        chart = [(D(2024, 5, 10), 500.0, 1), (D(2024, 5, 10), 200.0, 2), (D(2024, 6, 10), 520.0, 1), (D(2024, 6, 10), 210.0, 2),
                 (D(2024, 6, 20), 525.0, 1), (D(2024, 7, 10), 530.0, 1)]
        db = self._db(chart, [(1, 1, 0), (2, 0, 1)])
        r = H._portfolios(db, ["portfolio_chart", "securities"], [1], lambda k: {"balance_amount": 530.0}, D(2024, 7, 20))[1]
        self.assertEqual(r["amounts"]["2024-05"], 700.0); self.assertEqual(r["amounts"]["2024-06"], 525.0)

    def test_total_entry_beside_one_dominant_security(self):
        # one investment makes up nearly the whole portfolio, MoneyMoney also records the portfolio total: the total entry is
        # the one that matches the sum of the others exactly (not the investment, which matches only roughly) -> October with cash
        import mm_history as H
        from datetime import date as D, timedelta as TD
        chart, d = [], D(2026, 8, 7)
        while d <= D(2026, 11, 8):
            cash = 0.30 if D(2026, 10, 7) <= d < D(2026, 11, 4) else -0.30 if d >= D(2026, 11, 4) else 0.0
            chart += [(d, 1000.0, 1), (d, round(1000.0 + cash, 2), 2)]
            if D(2026, 10, 7) <= d < D(2026, 11, 4):
                chart.append((d, 0.30, 3))
            elif d >= D(2026, 11, 4):
                chart.append((d, -0.30, 4))
            d += TD(days=3)
        db = self._db(chart, [(1, 1, 0), (3, 0, 1), (4, 0, 0, "Guthaben", "")])
        r = H._portfolios(db, ["portfolio_chart", "securities"], [1], lambda k: {"balance_amount": 999.70}, D(2026, 11, 8))[1]
        self.assertEqual(r["amounts"]["2026-09"], 1000.0); self.assertEqual(r["amounts"]["2026-10"], 1000.3)
        # the breakdown: the securities without the total entry, with name and ISIN; the old cash position until its replacement
        wp = {w["name"]: w for w in r["securities"]}
        self.assertEqual(sorted(wp), ["Titel 1", "Titel 3"]); self.assertEqual(wp["Titel 1"]["isin"], "XX0000000001")
        self.assertEqual(wp["Titel 1"]["amounts"]["2026-10"], 1000.0); self.assertEqual(wp["Titel 3"]["amounts"], {"2026-10": 0.3})

    def test_names_from_moneymoneys_short_columns(self):
        # MoneyMoney's securities table has no "name" column: the name is the value of ident/symbol/wpn that reads like a name
        # (not a ticker in capitals, not a WKN or an ISIN)
        import sqlite3
        import mm_history as H
        from datetime import date as D, datetime as DT
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE portfolio_chart(account_key INTEGER, currency TEXT, timestamp INTEGER, balance REAL, securities_key INTEGER)")
        con.execute("CREATE TABLE securities(rowid INTEGER PRIMARY KEY, account_key INTEGER, quantity REAL, deleted INTEGER, ident TEXT, symbol TEXT, wpn TEXT, isin TEXT)")
        ts = int(DT(2026, 10, 10, 12).timestamp())
        con.executemany("INSERT INTO portfolio_chart VALUES(1, 'EUR', ?, ?, ?)", [(ts, 600.0, 1), (ts, 400.0, 2)])
        con.executemany("INSERT INTO securities VALUES(?, 1, 1, 0, ?, ?, ?, ?)",
                        [(1, "IE00B4L5Y983", "EUNL", "A0RPWH", "IE00B4L5Y983"), (2, "Beispiel Fonds Welt", "BFW", "A1B2C3", "US0378331005")])

        class DB:
            rows = lambda self, sql, params=(): con.execute(sql, params).fetchall()
            one = lambda self, sql, params=(): con.execute(sql, params).fetchone()
        r = H._portfolios(DB(), ["portfolio_chart", "securities"], [1], lambda k: {"balance_amount": 1000.0}, D(2026, 11, 8))[1]
        wp = {w["isin"]: w["name"] for w in r["securities"]}
        self.assertEqual(wp, {"IE00B4L5Y983": "", "US0378331005": "Beispiel Fonds Welt"})


class SecurityNameTests(unittest.TestCase):
    """Names of securities by ISIN (OpenFIGI, only on request) and how they are shown (made-up values)."""

    def test_isin_check_digit(self):
        from security_names import valid_isin
        self.assertTrue(valid_isin("IE00B4L5Y983")); self.assertTrue(valid_isin("us0378331005"))
        self.assertFalse(valid_isin("IE00B4L5Y984")); self.assertFalse(valid_isin("A0RPWH")); self.assertFalse(valid_isin("n:Fonds"))

    def test_lookup_sends_only_valid_isins_in_batches(self):
        import urllib.error
        import security_names as N
        sent, waits = [], []
        isins = ["IE00B4L5Y983", "US0378331005", "BAD", "IE00B4L5Y984"] + ["DE0007164600"]

        def post(jobs):
            sent.append([j["idValue"] for j in jobs])
            if len(sent) == 1:
                raise urllib.error.HTTPError(N.URL, 429, "too many", {}, None)       # once too many requests: wait, retry
            return [{"data": [{"name": "ISHARES CORE MSCI WORLD", "ticker": "EUNL"}, {"name": "ISHARES CORE MSCI WORLD"}, {"name": "ISHARES MSCI"}]}
                    if j["idValue"] == "IE00B4L5Y983" else {"warning": "No identifier found."} for j in jobs]
        old = N.BATCH
        try:
            N.BATCH = 2
            names = N.lookup(isins, post=post, sleep=waits.append)
        finally:
            N.BATCH = old
        self.assertEqual(names, {"IE00B4L5Y983": "ISHARES CORE MSCI WORLD"})
        self.assertTrue(all(N.valid_isin(i) for b in sent for i in b)); self.assertEqual(sorted({i for b in sent for i in b}), ["DE0007164600", "IE00B4L5Y983", "US0378331005"])
        self.assertEqual(waits[0], 7.0); self.assertIn(N.PAUSE, waits)

    def test_unnamed_leaves_out_named_and_done(self):
        from security_names import unnamed
        hist = {"u1": [{"name": "", "isin": "IE00B4L5Y983"}, {"name": "Beispiel", "isin": "US0378331005"}]}
        snaps = {"2026-09": {"u1": {"DE0007164600": 1.0, "n:Fonds": 2.0, "US0378331005": 3.0}}}
        self.assertEqual(unnamed(hist, snaps, {}), ["DE0007164600", "IE00B4L5Y983"])
        self.assertEqual(unnamed(hist, snaps, {"DE0007164600": "Aus dem Export"}), ["IE00B4L5Y983"])
        self.assertEqual(unnamed(hist, snaps, {}, ["DE0007164600", "IE00B4L5Y983"]), [])

    def test_names_changed_by_hand_in_the_list_of_all(self):
        from security_names import catalog, set_names
        known = catalog({"u1": [{"name": "", "isin": "ie00b4l5y983"}, {"name": "Beispiel", "isin": "US0378331005"}]}, {"DE0007164600": "Aus dem Export", "n:Fonds": "Fonds"})
        self.assertEqual(known, {"IE00B4L5Y983": "", "US0378331005": "Beispiel", "DE0007164600": "Aus dem Export"})
        found = {"names": {"IE00B4L5Y983": "ISHARES CORE MSCI WORLD"}, "without": [], "own": {"DE0007164600": "Alt"}}
        set_names(found, {"IE00B4L5Y983": "ISHARES CORE MSCI WORLD", "US0378331005": " Mein Name ", "DE0007164600": "", "XX0000000000": "Fremd"}, known)
        self.assertEqual(found["own"], {"US0378331005": "Mein Name"})          # unchanged or empty: none of your own
        self.assertEqual(found["names"], {"IE00B4L5Y983": "ISHARES CORE MSCI WORLD"})

    def test_shown_name_keeps_moneymoneys_name_and_isin(self):
        from datetime import date as D
        from model import Account
        from report import depot_holdings
        acc = Account("u1", "Depot", "portfolio", False, 0, 0.0, "EUR", portfolio=True)
        state = {"history_mm_sec": {"u1": [{"name": "", "isin": "IE00B4L5Y983", "amounts": {"2026-09": 100.0}},
                                           {"name": "Beispiel", "isin": "US0378331005", "amounts": {"2026-09": 50.0}},
                                           {"name": "", "isin": "DE0007164600", "amounts": {"2026-09": 25.0}}]},
                 "sec_search": {"names": {"IE00B4L5Y983": "ISHARES CORE MSCI WORLD", "US0378331005": "NICHT GENUTZT"}}}
        rows = {r["isin"]: r for r in depot_holdings(acc, {"2026-09": 175.0}, ["2026-09"], D(2026, 11, 8), state, None, {})}
        a, b, c = rows["IE00B4L5Y983"], rows["US0378331005"], rows["DE0007164600"]
        self.assertEqual((a["name"], a["orig"], a["source"]), ("ISHARES CORE MSCI WORLD", "", "lookup"))     # looked up: only without a name
        self.assertEqual((b["name"], b["orig"], b["source"]), ("Beispiel", "Beispiel", ""))                  # MoneyMoney's name goes first
        state["sec_search"]["own"] = {"US0378331005": "Mein Name"}                                          # changed in the list of names
        b = {r["isin"]: r for r in depot_holdings(acc, {"2026-09": 175.0}, ["2026-09"], D(2026, 11, 8), state, None, {})}["US0378331005"]
        self.assertEqual((b["name"], b["orig"], b["source"]), ("Mein Name", "Beispiel", "own_name"))
        self.assertEqual((c["name"], c["orig"], c["source"]), ("DE0007164600", "", ""))                      # nothing known: the ISIN


class SecurityHardeningTests(unittest.TestCase):
    """No plain-text fallback, the key out of the data folder, sessions ended on a password change, external receipts limited."""

    def test_no_plain_text_fallback(self):
        import tempfile, storage
        d = tempfile.mkdtemp()
        orig = storage.selftest
        storage.selftest = lambda master: False
        try:
            with self.assertRaises(storage.StoreError):
                storage.Store(d, b"k" * 32, "file")
        finally:
            storage.selftest = orig
        self.assertFalse(storage.Store(d, None).encrypted)          # only without any key (tests, never the service)

    def test_key_file_moved_into_keychain(self):
        import tempfile, storage
        d = tempfile.mkdtemp(); path = os.path.join(d, "master.key"); key = b"\x11" * 32
        with open(path, "w") as f:
            f.write(key.hex())
        chain = {}

        def fake(args, input_text=None):
            if args[0] == "find-generic-password":
                return (0, chain["w"] + "\n", "") if "w" in chain else (44, "", "not found")
            if args[0] == "add-generic-password":
                chain["w"] = args[args.index("-w") + 1]; return 0, "", ""
            return 1, "", ""
        orig = storage._security
        storage._security = fake
        try:
            got, src = storage.load_or_create_master_key(d)
        finally:
            storage._security = orig
        self.assertEqual((got, src), (key, "keychain"))       # the same key (data stays readable), now in the keychain
        self.assertEqual(chain["w"], key.hex()); self.assertFalse(os.path.exists(path))

    def test_password_change_ends_other_sessions(self):
        import auth
        ss = auth.Sessions(); a = ss.create("127.0.0.1", "pw"); b = ss.create("100.64.0.2", "pw")
        self.assertEqual(ss.drop_others(a["token"]), 1)
        self.assertIsNotNone(ss.get(a["token"])); self.assertIsNone(ss.get(b["token"]))

    def test_external_receipts_limited(self):
        import tempfile, receipts, storage
        d = tempfile.mkdtemp(); st = storage.Store(d, None)
        bl = receipts.Belege(st, {"receipts": {"folder": os.path.join(d, "Belege")}})
        home = os.path.expanduser("~")
        self.assertTrue(bl.external_ok(os.path.join(home, "Documents", "Rechnung.pdf")))
        self.assertTrue(bl.external_ok(os.path.join(home, "Library", "Mobile Documents", "com~apple~CloudDocs", "Beleg.pdf")))
        self.assertFalse(bl.external_ok(os.path.join(home, ".ssh", "id_ed25519.pdf")))           # hidden folder
        self.assertFalse(bl.external_ok(os.path.join(home, "Library", "Keychains", "login.pdf")))  # Library outside the cloud folders
        self.assertFalse(bl.external_ok(os.path.join(d, "config.pdf")))                           # Kontor's data folder
        self.assertFalse(bl.external_ok(os.path.join(home, "Documents", "notes.sqlite")))         # not a receipt type

    def test_session_renewed_and_subfolders_inside(self):
        import auth, tempfile, receipts, storage
        ss = auth.Sessions(); a = ss.create("127.0.0.1", "pw"); old = a["token"]
        new = ss.rotate(old)
        self.assertIsNone(ss.get(old)); self.assertIsNotNone(ss.get(new)); self.assertNotEqual(old, new)
        d = tempfile.mkdtemp(); st = storage.Store(d, None)
        for pat, want in (("../../{year}", "2026"), ("/etc/{year}", "2026"), ("{year}/{month}", os.path.join("2026", "03")), ("{jahr.__class__}", "2026")):
            bl = receipts.Belege(st, {"receipts": {"folder": os.path.join(d, "B"), "subfolder": pat}})
            self.assertEqual(bl.subfolder({"date": "2026-03-04"}), want, pat)
        # saving a pattern: braces only around the placeholders, always inside the folder
        for pat in ("{year}", "{year}/{month}", "Belege {entity}/{account}", "", "2026"):
            self.assertIsNone(receipts.pattern_problem(pat), pat)
        for pat in ("{jahr}", "{year", "year}", "{year:>4}", "{0}", "{jahr.__class__}", "{{year}}", "../{year}", "/etc/{year}", "~/x", "a/../b"):
            self.assertTrue(receipts.pattern_problem(pat), pat)

    def test_key_file_besides_keychain(self):
        import tempfile, storage
        d = tempfile.mkdtemp(); path = os.path.join(d, "master.key")
        kc, fk = b"\x22" * 32, b"\x33" * 32
        with open(os.path.join(d, "config.json.enc"), "wb") as f:
            f.write(storage.encrypt(fk, b"{}"))                         # the data belongs to the file's key
        with open(path, "w") as f:
            f.write(fk.hex())
        chain = {"w": kc.hex()}

        def fake(args, input_text=None):
            if args[0] == "find-generic-password":
                return 0, chain["w"] + "\n", ""
            if args[0] == "add-generic-password":
                chain["w"] = args[args.index("-w") + 1]; return 0, "", ""
            return 1, "", ""
        orig = storage._security
        storage._security = fake
        try:
            got, src = storage.load_or_create_master_key(d)
            self.assertEqual((got, src), (fk, "keychain")); self.assertFalse(os.path.exists(path))
            # no keychain at all and no key file: no new key file next to the data -- Kontor does not start
            storage._security = lambda args, input_text=None: (45, "", "denied")
            with self.assertRaises(storage.StoreError):
                storage.load_or_create_master_key(tempfile.mkdtemp())
        finally:
            storage._security = orig


class KontorBookingsTests(unittest.TestCase):
    def test_list_of_created_bookings(self):
        import service
        txs = [F.tx("ga.vd", date(2026, 10, 31), -3000.0, "Zinsen", "Zinsen Oktober #kontor-zins-2026-10"),
               F.tx("priv.bet.ga", date(2026, 11, 2), 1500.0, "Wertanpassung", "Anteil 40 % #kontor-wert-20261102-1"),
               F.tx("priv.giro", date(2026, 10, 3), -900.0, "Bank", "Rate", comment="→ Darlehen gespiegelt (#kontor-tx-7)")]
        led = Ledger(accounts_from_export(F.accounts_raw({})), tx_from_export(txs))
        out = service.kontor_bookings(led)
        self.assertEqual([(x["kind"], x["mark"]) for x in out], [("value", "#kontor-wert-20261102-1"), ("interest", "#kontor-zins-2026-10")])   # newest first; a comment alone is no booking
        self.assertEqual(out[1]["purpose"], "Zinsen Oktober"); self.assertEqual(out[1]["amount"], -3000.0)
        self.assertEqual(service.kontor_bookings(None), [])


class StatelessLoanTests(unittest.TestCase):
    """Kontor keeps no list of its bookings: what is booked is recognised in MoneyMoney -- by its mark, or as an equal booking
    you made yourself. Deleted there: proposed again (older than the last check: only with your approval)."""
    today = date(2026, 11, 4)

    def booked(self, cfg=None):
        """All of the loan booked (as if written), then MoneyMoney read again."""
        led = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(self.today))
        res = plan_loan(led, cfg or loan_cfg(), self.today)
        return led.without_planned(keep=[p.key for p in res.proposals]), res

    def test_deleted_changed_unmarked(self):
        real, res = self.booked()
        self.assertEqual(plan_loan(real.fork(), loan_cfg(), self.today).proposals, [])
        z = next(t for t in real.txs if "#kontor-zins-2026-03" in t.purpose)
        tl = next(t for t in real.txs if "#kontor-tx-" in t.purpose and t.booking_date == date(2026, 5, 1))
        # deleted in MoneyMoney: proposed again, older than the last check -> waits for you; the interest after it waits too
        gone = _replace_tx(_replace_tx(real, z), tl)
        seen = Seen(Seen.top_id(real), self.today)
        again = plan_loan(gone.fork(), loan_cfg(), self.today, seen=seen)
        self.assertEqual(sorted((p.kind, p.booking_date.isoformat()) for p in again.proposals), [("interest", "2026-03-31"), ("repayment", "2026-05-01")])
        self.assertTrue(all(p.retro for p in again.proposals))
        # changed there (its mark kept): counts as it is now
        ch = _replace_tx(real, z, -1234.56)
        self.assertEqual(plan_loan(ch.fork(), loan_cfg(), self.today).proposals, [])
        # its mark removed: the repayment is found by amount and day, the interest by its text (interest you booked)
        z.purpose, tl.purpose = "Zinsen März", "Annuität Mai"
        r = plan_loan(real.fork(), loan_cfg(), self.today)
        self.assertEqual(r.proposals, []); self.assertTrue(any("03/2026" in i for i in r.info))

    def test_replaced_or_gone_payment_and_both_interests(self):
        real, res = self.booked()
        pay = next(t for t in real.txs if t.account_uuid == F.uid("ga.kk") and t.booking_date == date(2026, 6, 1))
        # MoneyMoney replaced the payment (new number, a day later): Kontor's repayment counts for it -- nothing new, no note
        import dataclasses
        moved = Ledger(real.accounts, [dataclasses.replace(t, id=990001, booking_date=date(2026, 6, 2)) if t is pay else t for t in real.txs])
        r = plan_loan(moved.fork(), loan_cfg(), self.today)
        self.assertEqual(r.proposals, []); self.assertFalse(r.warnings, r.warnings)
        # the payment gone: a note to check Kontor's repayment (it deletes nothing)
        gone = Ledger(real.accounts, [t for t in real.txs if t is not pay])
        r = plan_loan(gone.fork(), loan_cfg(), self.today)
        self.assertEqual(r.proposals, []); self.assertTrue(any("keiner erkannten Zahlung" in w for w in r.warnings), r.warnings)
        # interest of Kontor's and yours in the same month: a warning (one of them is too much)
        both = real.fork(); both.post(F.uid("ga.vd"), date(2026, 7, 15), -3000.0, "Bank", "Zinsen Juli laut Bank").planned = False
        r = plan_loan(both, loan_cfg(), self.today)
        self.assertEqual(r.proposals, []); self.assertTrue(any("07/2026" in w for w in r.warnings), r.warnings)

    def test_new_since_last_check_and_dont_book(self):
        today = self.today
        led = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(date(2026, 10, 30)))
        last = max(t.id for t in led.txs)
        before = plan_loan(led, loan_cfg(), date(2026, 10, 30))          # all booked until the last check on 30 October
        real = led.without_planned(keep=[p.key for p in before.proposals])
        real = Ledger(real.accounts, real.txs + tx_from_export([F.tx("ga.kk", date(2026, 11, 1), -6000.0, "Verkäufer", F.ANNUITY_TEXT, "", F.SELLER_IBAN)]))
        res = plan_loan(real.fork(), loan_cfg(), today, seen=Seen(last, date(2026, 10, 30)))
        self.assertEqual(sorted((p.kind, p.booking_date.isoformat(), p.retro) for p in res.proposals),
                         [("interest", "2026-10-31", False), ("repayment", "2026-11-01", False)])       # the payment after it, the month ended after it
        # an older repayment left out (waiting for you): the interest after it waits too -- it is computed from the balance
        led = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today))
        t3 = next(p for p in plan_loan(led.fork(), loan_cfg(), today).proposals if p.kind == "repayment" and p.booking_date == date(2026, 3, 1))
        res = plan_loan(led.fork(), loan_cfg(), today, seen=Seen(0, date(2000, 1, 1)), hold={t3.key})
        self.assertNotIn(t3.key, [p.key for p in res.proposals])
        self.assertEqual([p.booking_date for p in res.proposals if p.kind == "interest" and p.retro], [date(2026, m + 1, 1) - timedelta(days=1) for m in range(3, 11)])      # March to October
        self.assertFalse([p for p in res.proposals if p.kind == "interest" and p.booking_date < date(2026, 3, 1) and p.retro])
        # "Don't book" (settings): never proposed
        cfg = {"loans": [loan_cfg()], "not_book": [{"key": t3.key}]}
        self.assertNotIn(t3.key, [p.key for p in plan_all(make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today)), cfg, today).proposals])

    def test_two_equal_payments_one_booked_by_hand(self):
        txs = [F.tx("ga.kk", date(2026, 10, 1), -500.0, "Verkäufer", F.ANNUITY_TEXT, "", F.SELLER_IBAN),
               F.tx("ga.kk", date(2026, 10, 2), -500.0, "Verkäufer", F.ANNUITY_TEXT, "", F.SELLER_IBAN),
               F.tx("ga.vd", date(2026, 10, 1), 500.0, "Ich", "Rate von Hand")]
        led = make_ledger({"ga.vd": -1200000.0}, txs)
        cfg = loan_cfg(from_date="2026-10-01", interest={}, expected_monthly=False)
        res = plan_loan(led, cfg, date(2026, 10, 20))
        self.assertEqual([(p.kind, p.booking_date) for p in res.proposals], [("repayment", date(2026, 10, 2))])     # each booking counts once


def _replace_tx(led, tx, amount=None):
    """The ledger without `tx` (amount=None: deleted in MoneyMoney) or with its amount changed there."""
    import dataclasses
    accs = {u: dataclasses.replace(a) for u, a in led.accounts.items()}
    txs = []
    for t in led.txs:
        if t is tx:
            accs[t.account_uuid].balance = round(accs[t.account_uuid].balance - t.amount + (amount or 0.0), 2)
            if amount is not None:
                txs.append(dataclasses.replace(t, amount=amount))
            continue
        txs.append(t)
    return Ledger(accs, txs)


class ChainTests(unittest.TestCase):
    """A balance is the sum of the bookings up to that day: what you leave out or change is made up by the next value adjustment
    of that account (the ones after it stay); one deleted or changed in MoneyMoney is corrected on its own day."""
    today = date(2026, 11, 4)

    def setUp(self):
        self.base = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(self.today))         # the same bookings (ids) each time

    def plan(self, led=None, **kw):
        led = led or self.base.fork()
        cfg = company_cfg(loans=[loan_cfg()])
        cfg["companies"][0].update(retroactive_from="2026-03-01", cycle="monthly")
        return led, cfg, plan_all(led, cfg, self.today, **kw)

    def test_left_out_or_changed_moves_only_the_next(self):
        _, _, res = self.plan()
        w = [p for p in res.proposals if p.kind == "value"]
        self.assertEqual(len(w), 8)
        _, _, held = self.plan(hold={w[1].key})
        h = {p.key: p.amount for p in held.proposals if p.kind == "value"}
        self.assertNotIn(w[1].key, h)
        self.assertAlmostEqual(h[w[2].key], round(w[1].amount + w[2].amount, 2), 2)          # the next one takes up the difference
        for p in [w[0]] + w[3:]:
            self.assertAlmostEqual(h[p.key], p.amount, 2)
        # a value adjustment follows MoneyMoney: its amount is not changed by hand (only its text)
        _, _, ed = self.plan(edits={w[1].key: {"amount": round(w[1].amount + 100, 2), "purpose": "Mein Text"}})
        e = {p.key: p for p in ed.proposals if p.kind == "value"}
        self.assertAlmostEqual(e[w[1].key].amount, w[1].amount, 2); self.assertEqual(e[w[1].key].purpose, "Mein Text · " + w[1].tag)
        # a loan's interest changed by hand: booked with your amount, the value after it follows
        z = next(p for p in res.proposals if p.kind == "interest" and p.booking_date == date(2026, 5, 31))
        _, _, zed = self.plan(edits={z.key: {"amount": -1000.0}})
        zz = {p.key: p.amount for p in zed.proposals}
        self.assertEqual(zz[z.key], -1000.0)
        self.assertAlmostEqual(zz[w[2].key], round(w[2].amount + 0.4 * (-1000.0 - z.amount), 2), delta=0.02)
        # a loan repayment left out: the company is worth less from that day on, the first value adjustment after it follows
        t0 = next(p for p in res.proposals if p.kind == "repayment")
        _, _, lo = self.plan(hold={t0.key})
        v = {p.key: p.amount for p in lo.proposals if p.kind == "value"}
        self.assertAlmostEqual(v[w[0].key], w[0].amount - 0.4 * t0.amount, delta=0.02)
        for p in w[1:]:
            self.assertAlmostEqual(v[p.key], p.amount, delta=0.02)
        self.assertNotIn(t0.key, {p.key for p in lo.proposals})

    def test_deleted_or_changed_is_corrected_on_its_day(self):
        led, cfg, res = self.plan()
        real = led.without_planned(keep=[p.key for p in res.proposals])        # all written: in MoneyMoney now
        self.assertEqual([p for p in plan_all(real.fork(), cfg, self.today).proposals if p.kind == "value"], [])
        w = [p for p in res.proposals if p.kind == "value"]
        tx = next(t for t in real.txs if w[2].tag in (t.purpose or "") and t.account_uuid == w[2].account_uuid)
        # deleted in MoneyMoney: every month end is checked again -- one booking on its day (its mark is free again), nothing
        # after it; older than the last check, so it waits for you
        gone = _replace_tx(real, tx)
        again = [p for p in plan_all(gone.fork(), cfg, self.today, seen=Seen(Seen.top_id(real), self.today)).proposals if p.kind == "value"]
        self.assertEqual([(p.key, p.booking_date, round(p.amount, 2), p.retro) for p in again], [(w[2].key, w[2].booking_date, round(w[2].amount, 2), True)])
        # you booked the value yourself instead: nothing to do
        own = _replace_tx(real, tx)
        own.post(tx.account_uuid, tx.booking_date, tx.amount, "Ich", "Wert selbst gebucht").planned = False
        self.assertEqual([p for p in plan_all(own, cfg, self.today).proposals if p.kind == "value"], [])
        # amount changed in MoneyMoney: the difference back on that day, with the next free mark
        ch = _replace_tx(real, tx, round(tx.amount + 50, 2))
        fix = [p for p in plan_all(ch, cfg, self.today).proposals if p.kind == "value"]
        self.assertEqual([(p.booking_date, round(p.amount, 2), p.tag) for p in fix], [(w[2].booking_date, -50.0, w[2].tag[:-1] + "2")])


class MirrorTests(unittest.TestCase):
    """Counter accounts as a mirror: each booking into the other account with the opposite sign, both ways where both are
    offline accounts, never back; pairs booked by hand count; gone or changed originals are notes."""
    today = date(2026, 11, 4)

    def cfg(self, back="all", source="gb.kap.a"):
        return company_cfg(companies=[{"area": "b", "retroactive_from": back}], account_mirrors=[
            {"a": F.uid("priv.bet.gb") + " | Beteiligung an Beta GbR", "b": F.uid(source) + " | Konto", "from_date": back}])

    def test_both_ways_pairs_and_never_back(self):
        txs = [F.tx("gb.kap.a", date(2026, 9, 1), -5000.0, "Ich", "Einlage"), F.tx("priv.bet.gb", date(2026, 10, 2), 1200.0, "Beta GbR", "Entnahme"),
               F.tx("gb.kap.a", date(2026, 10, 1), 1000.0, "Ich", "Entnahme Okt"), F.tx("priv.bet.gb", date(2026, 10, 1), -1000.0, "Beta GbR", "von Hand"),
               F.tx("gb.kap.a", date(2026, 10, 20), 70.0, "Ich", "Gebühr"), F.tx("priv.bet.gb", date(2026, 10, 21), -70.0, "Beta GbR", "einen Tag später")]
        led = make_ledger({}, txs)
        res = plan_all(led, self.cfg(), self.today)
        got = sorted((p.account_uuid, p.booking_date, p.amount) for p in res.proposals)
        self.assertEqual(got, sorted([(F.uid("gb.kap.a"), date(2026, 10, 2), -1200.0), (F.uid("priv.bet.gb"), date(2026, 9, 1), 5000.0),
                                      (F.uid("priv.bet.gb"), date(2026, 10, 20), -70.0), (F.uid("gb.kap.a"), date(2026, 10, 21), 70.0)]))   # a day apart: no pair
        self.assertEqual(sorted(bool(p.note) for p in res.proposals), [False, False, True, True])       # ... but each names the other
        pv = res.preview[0]
        self.assertEqual((pv["direction"], pv["paare"], pv["open"]), ("both", 1, 4))
        # written: nothing again, nothing mirrored back
        real = led.without_planned(keep=[p.key for p in res.proposals])
        again = plan_all(real.fork(), self.cfg(), self.today)
        self.assertEqual(again.proposals, []); self.assertEqual(again.warnings, []); self.assertEqual(again.preview[0]["mirrored"], 5)

    def test_hand_pairs_days_apart(self):
        """Counter-bookings entered by hand at the two ends of a transfer between banks (days apart): no pair -- a wrong one
        would leave a booking out unseen -- but each proposal names the other booking, carries the key of the other half (both
        are turned down at once) and is never booked on its own; up to a month apart, nothing further."""
        txs = [F.tx("priv.bet.gb", date(2026, 9, 29), 3000.0, "Beta GbR", "Einlage von Hand"), F.tx("gb.kap.a", date(2026, 10, 2), -3000.0, "Ich", "Eingang +3 Tage"),
               F.tx("priv.bet.gb", date(2026, 8, 1), 800.0, "Beta GbR", "Einlage"), F.tx("gb.kap.a", date(2026, 9, 20), -800.0, "Ich", "50 Tage später"),
               F.tx("priv.bet.gb", date(2026, 10, 25), 250.0, "Beta GbR", "ohne Gegenstück")]
        led = make_ledger({}, txs)
        res = plan_all(led, self.cfg(), self.today)
        by = {(p.account_uuid, p.booking_date, p.amount): p for p in res.proposals}
        a, b = by[(F.uid("gb.kap.a"), date(2026, 9, 29), -3000.0)], by[(F.uid("priv.bet.gb"), date(2026, 10, 2), 3000.0)]
        self.assertIn("02.10.2026", a.note); self.assertIn("29.09.2026", b.note)
        self.assertEqual((a.pair, b.pair), (b.key, a.key))                                    # the two halves know each other
        self.assertFalse(by[(F.uid("gb.kap.a"), date(2026, 8, 1), -800.0)].note)            # more than a month apart: nothing
        self.assertFalse(by[(F.uid("gb.kap.a"), date(2026, 10, 25), -250.0)].note)
        self.assertEqual(res.preview[0]["paare"], 0)
        import core
        rows = {r["key"]: r for r in core.proposal_rows(led, res.proposals)}
        self.assertEqual((rows[a.key]["pair"], bool(rows[a.key]["note"])), (b.key, True))      # the approval list has both

    def test_hand_booking_after_kontors_mirror_and_refused_ones(self):
        """The other end entered by hand after Kontor had mirrored the first (a sync between the two bank days): a note and a
        warning, not booked on its own -- one of the two is too many. A booking whose mirror you turned down pairs with nothing
        (it must not swallow a new one)."""
        cfg = self.cfg()
        orig = F.tx("priv.bet.gb", date(2026, 9, 29), 3000.0, "Beta GbR", "Einlage von Hand")
        first = plan_all(make_ledger({}, [orig]), cfg, self.today)
        mirrored = F.tx("gb.kap.a", date(2026, 9, 29), -3000.0, "Ich", first.proposals[0].purpose)          # Kontor mirrored: GbR −3000 on 29.09.
        again = plan_all(make_ledger({}, [orig, mirrored, F.tx("gb.kap.a", date(2026, 10, 2), -3000.0, "Ich", "Eingang von Hand")]), cfg, self.today)
        p = [x for x in again.proposals if x.kind == "mirror"]
        self.assertEqual([(x.account_uuid, x.booking_date, x.amount) for x in p], [(F.uid("priv.bet.gb"), date(2026, 10, 2), 3000.0)])
        self.assertIn("29.09.2026", p[0].note); self.assertTrue(any("zu viel" in w or "too many" in w for w in again.warnings))
        # turned down: the 500 of 21.09. and 01.10. (10 days apart) were not mirrored; a new 500 on 04.10. is mirrored all the same
        old = [F.tx("priv.bet.gb", date(2026, 9, 21), 500.0, "Beta GbR", "alt"), F.tx("gb.kap.a", date(2026, 10, 1), -500.0, "Ich", "alt")]
        refuse = plan_all(make_ledger({}, old), cfg, self.today).proposals
        self.assertEqual(len(refuse), 2); self.assertTrue(all(x.note for x in refuse))
        cfg2 = dict(cfg, not_book=[{"key": x.key} for x in refuse])
        res = plan_all(make_ledger({}, old + [F.tx("priv.bet.gb", date(2026, 10, 4), 500.0, "Beta GbR", "neu")]), cfg2, self.today, set(x.key for x in refuse))
        self.assertEqual([(x.booking_date, x.amount) for x in res.proposals if x.kind == "mirror"], [(date(2026, 10, 4), -500.0)])
        self.assertFalse(res.proposals[0].note)                  # what you turned down is no counterpart (it would hold the new one back)

    def test_counterparts_name_each_other_only_both_ways(self):
        """Two bookings of the same amount on one side, one on the other: only the nearest two are halves of each other (turned
        down together); the farther one gets the note without the other half. A mirror with a bank account on one side: nothing
        is proposed there, so no other half."""
        txs = [F.tx("priv.bet.gb", date(2026, 10, 1), 100.0, "Beta GbR", "a"), F.tx("priv.bet.gb", date(2026, 10, 10), 100.0, "Beta GbR", "b"),
               F.tx("gb.kap.a", date(2026, 10, 8), -100.0, "Ich", "zu b")]
        res = plan_all(make_ledger({}, txs), self.cfg(), self.today)
        by = {(p.account_uuid, p.booking_date): p for p in res.proposals}
        a, b, c = by[(F.uid("gb.kap.a"), date(2026, 10, 1))], by[(F.uid("gb.kap.a"), date(2026, 10, 10))], by[(F.uid("priv.bet.gb"), date(2026, 10, 8))]
        self.assertEqual((b.pair, c.pair), (c.key, b.key)); self.assertEqual(a.pair, ""); self.assertIn("08.10.2026", a.note)
        self.assertNotIn("beide Seiten", a.note); self.assertIn("beide Seiten", b.note)
        cfg = company_cfg(companies=[{"area": "b", "retroactive_from": "all"}], account_mirrors=[
            {"a": F.uid("priv.giro") + " | Giro", "b": F.uid("gb.kap.a") + " | Konto", "from_date": "all"}])
        res = plan_all(make_ledger({}, [F.tx("priv.giro", date(2026, 10, 1), -100.0, "x", "y"), F.tx("gb.kap.a", date(2026, 10, 3), 100.0, "Ich", "z")]), cfg, self.today)
        self.assertTrue(res.proposals); self.assertTrue(all(p.pair == "" for p in res.proposals))

    def test_mirror_of_its_own_without_a_company(self):
        """A mirror is a rule of its own: between any two accounts (here two of your own, no company, no participation), with
        its own "Buchen ab"."""
        a, b = F.uid("priv.immo"), F.uid("priv.bet.ga")
        cfg = {"areas": [{"id": "p", "name": "Privat", "kind": "private", "main_area": True, "accounts": [F.uid("priv") + " | Privat"]}],
               "account_mirrors": [{"a": a + " | A", "b": b + " | B", "from_date": "2026-10-01"}]}
        txs = [F.tx("priv.immo", date(2026, 9, 1), 900.0, "x", "vor Buchen ab"), F.tx("priv.immo", date(2026, 10, 5), 500.0, "x", "Zugang"),
               F.tx("priv.bet.ga", date(2026, 10, 9), -40.0, "y", "Abgang")]
        led = make_ledger({}, txs)
        res = plan_all(led, cfg, self.today)
        self.assertEqual(sorted((p.account_uuid, p.booking_date, p.amount, p.kind) for p in res.proposals),
                         sorted([(b, date(2026, 10, 5), -500.0, "mirror"), (a, date(2026, 10, 9), 40.0, "mirror")]))
        self.assertEqual(res.warnings, [])
        self.assertEqual([(v["kind"], v["i"], v["direction"]) for v in res.preview], [("mirror", 0, "both")])
        self.assertEqual({p.payee for p in res.proposals}, {"Privat"})                     # whose account the original is in
        real = led.without_planned(keep=[p.key for p in res.proposals])
        self.assertEqual(plan_all(real.fork(), cfg, self.today).proposals, [])            # written: nothing again
        # the same account on both sides, a group: a note, nothing booked
        self.assertTrue(plan_all(make_ledger({}, txs), dict(cfg, account_mirrors=[{"a": a, "b": a, "from_date": "all"}]), self.today).warnings)
        self.assertEqual(plan_all(make_ledger({}, txs), dict(cfg, account_mirrors=[{"a": a, "b": a, "from_date": "all"}]), self.today).proposals, [])
        # kept with a company before: the same list (once), the company's "Buchen ab", the same bookings
        old = self.cfg()
        import rules as R
        self.assertEqual([(m["a"].split(" | ")[0], m["b"].split(" | ")[0], m["from_date"]) for m in R.mirrors(old)], [(F.uid("priv.bet.gb"), F.uid("gb.kap.a"), "all")])
        new = dict(company_cfg(), account_mirrors=[{"a": F.uid("priv.bet.gb"), "b": F.uid("gb.kap.a"), "from_date": "all"}])
        new["companies"] = []
        tx2 = [F.tx("gb.kap.a", date(2026, 9, 1), -5000.0, "Ich", "Einlage"), F.tx("priv.bet.gb", date(2026, 10, 2), 1200.0, "Beta GbR", "Entnahme")]
        want = sorted((p.account_uuid, p.booking_date, p.amount, p.payee, p.tag) for p in plan_all(make_ledger({}, tx2), old, self.today).proposals)
        got = sorted((p.account_uuid, p.booking_date, p.amount, p.payee, p.tag) for p in plan_all(make_ledger({}, tx2), new, self.today).proposals)
        self.assertTrue(want); self.assertEqual(got, want)

    def test_company_with_only_a_mirror(self):
        """A company counts as set up with a mirror into one of its accounts alone (payments to it: contributions); a mirror of
        your own accounts makes no company."""
        import report
        cfg = dict(self.cfg()); cfg["companies"] = [dict(g, participation="") for g in cfg["companies"]]
        led = make_ledger({}, [])
        self.assertTrue(report.company_accounts(led, cfg))
        own = dict(cfg, account_mirrors=[{"a": F.uid("priv.immo"), "b": F.uid("priv.bet.ga"), "from_date": "all"}])
        self.assertEqual(report.company_accounts(led, own), {})
    def test_checks_package_and_reading(self):
        """The check names what is wrong with a mirror; a package adds mirrors pair by pair (none is lost); "Buchen ab" of a
        mirror is read that far back."""
        import core
        A, B, C = F.uid("priv.immo"), F.uid("priv.bet.ga"), F.uid("priv.bet.gb")
        led = make_ledger({}, [])
        base = {"areas": company_cfg()["areas"]}
        errors = lambda ms, **over: [f["text"] for f in core.check_config(led, [], core.merged_config(dict(base, account_mirrors=ms, **over))) if f["severity"] == "error"]
        warns = lambda ms: [f["text"] for f in core.check_config(led, [], core.merged_config(dict(base, account_mirrors=ms))) if f["severity"] == "warning"]
        self.assertEqual(errors([{"a": A, "b": B, "from_date": "all"}]), [])
        self.assertEqual(len(errors([{"a": A, "b": A, "from_date": "all"}])), 1)                                   # the same account
        self.assertEqual(len(errors([{"a": "nope | Weg", "b": B, "from_date": "all"}])), 1)                        # an account is gone
        self.assertIn("Kontenspiegel 1", errors([{"a": "nope | Weg", "b": B, "from_date": "all"}])[0])
        self.assertEqual(len(errors([{"a": A, "b": B, "from_date": "2099-01-01"}])), 1)                              # a day in the future
        self.assertEqual(len(errors([{"a": A, "b": B, "from_date": "all"}, {"a": A, "b": C, "from_date": "all"}])), 1)  # booked by two rules
        self.assertEqual(len(errors([{"a": B, "b": A, "from_date": "all"}], companies=[{"area": "a", "participation": B}])), 1)
        self.assertTrue(warns([{"a": F.uid("priv.giro"), "b": F.uid("ga.kk"), "from_date": "all"}]))               # no offline account
        self.assertTrue(any("doppelt" in w or "twice" in w for w in warns([{"a": A, "b": B, "from_date": "all"}, {"a": B, "b": A, "from_date": "all"}])))   # the same pair twice
        G = F.uid("priv.giro")                                       # a bank account in two mirrors: each booking would come twice
        two = errors([{"a": G, "b": B, "from_date": "all"}, {"a": G, "b": C, "from_date": "all"}])
        self.assertEqual(len(two), 1); self.assertIn("2", two[0])
        # no false alarm: a second mirror that books nothing (two bank accounts, a gone account), the same pair three times: one note
        self.assertEqual(errors([{"a": G, "b": B, "from_date": "all"}, {"a": G, "b": F.uid("ga.kk"), "from_date": "all"}]), [])
        gone = errors([{"a": G, "b": B, "from_date": "all"}, {"a": G, "b": "nope | Weg", "from_date": "all"}])
        self.assertEqual(len(gone), 1); self.assertNotIn("Kontenspiegeln", gone[0])                          # only: the account is gone
        self.assertEqual(len([w for w in warns([{"a": A, "b": B, "from_date": "all"}] * 3) if "doppelt" in w]), 1)
        # package
        cur = core.merged_config(dict(base, account_mirrors=[{"a": A, "b": B, "from_date": "all"}]))
        pkg = core.export_package(core.merged_config(base), "Test", ledger=led)
        self.assertEqual(len(core.import_package(cur, pkg, led, "merge")[0]["account_mirrors"]), 1)         # a package without mirrors
        pkg2 = core.export_package(core.merged_config(dict(base, account_mirrors=[{"a": B, "b": A, "from_date": "2026-01-01"}, {"a": A, "b": C, "from_date": "all"}])), "Test", ledger=led)
        got = core.import_package(cur, pkg2, led, "merge")[0]["account_mirrors"]
        self.assertEqual([(m["a"].split(" | ")[0], m["b"].split(" | ")[0], m["from_date"]) for m in got], [(B, A, "2026-01-01"), (A, C, "all")])
        # reading
        short = {"balance": {"months_back": 12}}
        self.assertGreater(core.earliest_needed(core.merged_config(short), self.today), date(2025, 1, 1))
        self.assertEqual(core.earliest_needed(core.merged_config(dict(short, account_mirrors=[{"a": A, "b": B, "from_date": "all"}])), self.today), date(2000, 1, 1))
        self.assertEqual(core.earliest_needed(core.merged_config(dict(short, account_mirrors=[{"a": A, "b": B, "from_date": "2022-05-01"}])), self.today), date(2021, 1, 1))

    def test_mirror_settings_checked(self):
        """The same pair once, whichever way round; every side Kontor books into is checked; two currencies: nothing is
        mirrored (Kontor does not convert) and it says so."""
        import core
        A, B, K = F.uid("priv.immo"), F.uid("priv.bet.ga"), F.uid("gb.kap.a")
        txs = [F.tx("priv.immo", date(2026, 10, 5), 500.0, "x", "Zugang")]
        self.assertEqual(len(rules_mirrors({"account_mirrors": [{"a": A, "b": B}, {"a": B + " | x", "b": A}, {"a": A, "b": K}]})), 2)
        base = {"areas": company_cfg()["areas"]}
        errors = lambda cfg: [f["text"] for f in core.check_config(make_ledger({}, []), [], core.merged_config(dict(base, **cfg))) if f["severity"] == "error"]
        self.assertEqual(len(errors({"account_mirrors": [{"a": A, "b": B, "from_date": "all"}], "companies": [{"area": "a", "participation": B}]})), 1)
        self.assertEqual(len(errors({"account_mirrors": [{"a": B, "b": A, "from_date": "all"}, {"a": F.uid("priv.bet.gb"), "b": A, "from_date": "all"}]})), 1)
        cur = core.merged_config(dict(base, account_mirrors=[{"a": A, "b": B, "from_date": "all"}]))
        led = make_ledger({}, txs)
        led.accounts[B].currency = "USD"
        res = plan_all(led, cur, self.today)
        self.assertEqual(res.proposals, []); self.assertEqual(len(res.warnings), 1)
        self.assertTrue([f for f in core.check_config(led, [], cur) if f["severity"] == "warning"])
    def test_from_a_day_and_bank_account_one_way(self):
        old = F.tx("gb.kk", date(2026, 10, 1), -300.0, "Ich", "vor dem Start")
        cfg = self.cfg(back="2026-10-15", source="gb.kk")        # the company's side is a bank account: only into yours
        res = plan_all(make_ledger({}, [old]), cfg, self.today)
        self.assertEqual(res.proposals, [])
        new = F.tx("gb.kk", date(2026, 10, 20), 800.0, "Ich", "ab dem Start")
        res2 = plan_all(make_ledger({}, [old, new]), cfg, self.today)
        self.assertEqual([(p.account_uuid, p.amount) for p in res2.proposals], [(F.uid("priv.bet.gb"), -800.0)])
        self.assertEqual((res2.preview[0]["direction"], res2.preview[0]["begin"]), ("to_a", "2026-10-15"))
        # without a day (not written by the interface): since Kontor's first mirrored booking, else what is new since the last check
        led = make_ledger({}, [old, new])
        res3 = plan_all(led, self.cfg(back="", source="gb.kk"), self.today, seen=Seen(old["id"], self.today))
        self.assertEqual([p.amount for p in res3.proposals], [-800.0])
        # mine is a bank account too: nothing can be mirrored
        cfg3 = company_cfg(account_mirrors=[{"a": F.uid("priv.giro") + " | Giro", "b": F.uid("gb.kk") + " | KK", "from_date": "all"}])
        self.assertTrue(any("Offline-Konto" in w for w in plan_all(make_ledger({}, []), cfg3, self.today).warnings))

    def test_gone_changed_renumbered_original_and_deleted_mirror(self):
        o = F.tx("gb.kap.a", date(2026, 9, 1), -5000.0, "Ich", "Einlage")
        led = make_ledger({}, [o])
        res = plan_all(led, self.cfg(), self.today)
        p = res.proposals[0]
        mirror = F.tx("priv.bet.gb", p.booking_date, p.amount, p.payee, p.purpose)
        # the original deleted: a note to delete the mirrored booking too
        gone = plan_all(make_ledger({}, [mirror]), self.cfg(), self.today)
        self.assertEqual(gone.proposals, []); self.assertTrue(any("kein Original mehr" in w for w in gone.warnings))
        # the original entered again (a new number, same day and amount): the mirrored booking counts for it
        again_o = dict(o, id=o["id"] + 50000)
        r = plan_all(make_ledger({}, [again_o, mirror]), self.cfg(), self.today)
        self.assertEqual(r.proposals, []); self.assertEqual(r.warnings, []); self.assertEqual(r.preview[0]["mirrored"], 1)
        # the original changed: a note to adjust it
        changed = plan_all(make_ledger({}, [dict(o, amount=-5500.0), mirror]), self.cfg(), self.today)
        self.assertEqual(changed.proposals, []); self.assertTrue(any("passt nicht mehr" in w for w in changed.warnings))
        # the mirrored booking deleted in MoneyMoney: proposed again -- older than the last check, so only with your approval
        led2 = make_ledger({}, [o])
        again = plan_all(led2, self.cfg(), self.today, seen=Seen(Seen.top_id(led2), self.today))
        self.assertEqual([(q.key, q.retro) for q in again.proposals], [(p.key, True)])

    def test_new_account_shown_before_its_first_booking(self):
        from report import inactive_accounts
        led = make_ledger({"gb.kap.b": 0.0}, [])
        acc = led.accounts[F.uid("gb.kap.b")]
        hidden, auto = inactive_accounts(led, [acc], {}, [], {"balance": {"inactive_months": 12}}, self.today)
        self.assertIn(acc.uuid, auto)                                   # empty and long known: hidden by activity
        hidden, auto = inactive_accounts(led, [acc], {}, [], {"balance": {"inactive_months": 12}}, self.today, {acc.uuid: "2026-11-03"})
        self.assertNotIn(acc.uuid, auto)                                # new in MoneyMoney: shown at once


class CapitalAccountRoleTests(unittest.TestCase):
    def test_capital_account_private_participation_company_debt(self):
        """An account named "Kapitalkonto": privately a participation (also empty, also of the type "Darlehenskonto"), in a
        company its debt to the partner."""
        from report import account_roles
        raw = F.accounts_raw({})
        for a in raw:
            if a["uuid"] == F.uid("priv.bet.ga"):
                a.update(name="Kapitalkonto Alpha GbR", type="Darlehenskonto", balance=[[0.0, "EUR"]])
        led = Ledger(accounts_from_export(raw), [])
        roles = account_roles(led, company_cfg())
        self.assertEqual(roles[F.uid("priv.bet.ga")], "participations")
        self.assertEqual(roles[F.uid("ga.kap.a")], "liabilities")
        for a in raw:                                       # also with a debit balance: yours is a participation
            if a["uuid"] == F.uid("priv.bet.ga"):
                a["balance"] = [[-500.0, "EUR"]]
        self.assertEqual(account_roles(Ledger(accounts_from_export(raw), []), company_cfg())[F.uid("priv.bet.ga")], "participations")
        # no company set up yet: a capital account with a debt stays a debt (as before)
        self.assertEqual(account_roles(Ledger(accounts_from_export(raw), []), {})[F.uid("ga.kap.a")], "liabilities")


class WritePathTests(unittest.TestCase):
    """Everything Kontor may do in MoneyMoney, in one place: new bookings in offline accounts (core.apply_proposals), the
    category of a transaction you assign (mm_categories.write), a receipt reference added to a comment (Bridge.append_comment).
    Nothing else -- no transfers, nothing deleted, nothing existing replaced."""

    class Rec:
        dry_run = False

        def __init__(self, txs=()):
            self.calls, self.txs = [], list(txs)

        def add_transaction(self, *a, **k):
            self.calls.append(("add",) + a)

        def set_transaction(self, tx_id, category=None, comment=None):
            self.calls.append(("set", tx_id, category, comment))

        def export_transactions(self, from_date, to_date=None, account=None):
            return [t for t in self.txs if t["accountUuid"] == account]

    def test_only_these_calls_exist(self):
        import re as _re
        import mm_bridge
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assertEqual(set(mm_bridge.ALLOWED_METHODS), {"exportAccounts", "exportCategories", "exportTransactions", "exportPortfolio",
                                                           "addTransaction", "setTransaction"})
        jxa = open(os.path.join(root, "mm_bridge.jxa"), encoding="utf-8").read()
        allowed = set(_re.findall(r"(\w+): true", jxa.split("const ERLAUBT")[1].split("};")[0]))
        self.assertEqual(allowed, set(mm_bridge.ALLOWED_METHODS))
        for word in ("createBankTransfer", "createBatchTransfer", "createDirectDebit", "createBatchDirectDebit"):
            self.assertNotIn(word, allowed)
        found = {}
        for name in sorted(os.listdir(root)):
            if not name.endswith(".py"):
                continue
            src = open(os.path.join(root, name), encoding="utf-8").read()
            for call in ("add_transaction", "set_transaction", "append_comment", "_call"):
                n = len(_re.findall(r"\.%s\(" % call, src))
                if n:
                    found[(name, call)] = n
        self.assertEqual(found, {("core.py", "add_transaction"): 1,              # apply_proposals
                                 ("mm_categories.py", "set_transaction"): 1,     # the category you assign (write-back on)
                                 ("service.py", "append_comment"): 1,            # receipt reference (your setting)
                                 ("mm_bridge.py", "set_transaction"): 1,         # inside append_comment
                                 ("mm_bridge.py", "_call"): 8})

    def test_bookings_only_marked_once_and_into_offline_accounts(self):
        import core
        from rules import Proposal
        from mm_bridge import MoneyMoneyError
        tag = "#kontor-wert-20261104-1"
        there = F.tx("priv.bet.gb", date(2026, 11, 1), 5.0, "x", "da · #kontor-wert-20261101-1")
        led = make_ledger({}, [there])
        off, bank = led.accounts[F.uid("priv.bet.ga")], led.accounts[F.uid("priv.giro")]
        ok = Proposal("r", "value", off.uuid, off.path, date(2026, 11, 4), 12.5, "p", "Text · " + tag, "", tag)
        br = self.Rec()
        made = []
        self.assertEqual(core.apply_proposals(br, led, [ok], made), 1)
        self.assertEqual(br.calls, [("add", off.uuid, date(2026, 11, 4), "p", 12.5, "Text · " + tag, None)]); self.assertEqual(made, [ok])
        for bad in (Proposal("r", "value", bank.uuid, bank.path, date(2026, 11, 4), 1.0, "p", "x · " + tag, "", tag),       # a bank account
                    Proposal("r", "value", F.uid("priv"), "Privat", date(2026, 11, 4), 1.0, "p", "x · " + tag, "", tag),      # a group
                    Proposal("r", "value", off.uuid, off.path, date(2026, 11, 4), 1.0, "p", "ohne Markierung", "", tag),      # no mark in its text
                    Proposal("r", "value", off.uuid, off.path, date(2026, 11, 4), 1.0, "p", "x", "", ""),
                    Proposal("r", "value", off.uuid, off.path, date(2026, 11, 4), float("nan"), "p", "x · " + tag, "", tag)):
            br = self.Rec()
            with self.assertRaises(MoneyMoneyError):
                core.apply_proposals(br, led, [bad], [])
            self.assertEqual(br.calls, [])
        # its mark is in the account already, or no amount: nothing is written (never twice)
        twice = Proposal("r", "value", F.uid("priv.bet.gb"), "x", date(2026, 11, 1), 5.0, "p", "da · #kontor-wert-20261101-1", "", "#kontor-wert-20261101-1")       # there already
        zero = Proposal("r", "value", off.uuid, off.path, date(2026, 11, 4), 0.0, "p", "x · " + tag, "", tag)
        br = self.Rec(); made = []
        core.apply_proposals(br, led, [twice, zero, ok, ok], made)
        self.assertEqual(len(br.calls), 1); self.assertEqual(made, [ok])
        # a category only if MoneyMoney has it -- otherwise without one (its category tree is never touched), and a note
        cats = [{"name": "Zinsen", "path": "Finanzen\\Zinsen", "uuid": "u-1"}]
        a = Proposal("r", "interest", off.uuid, off.path, date(2026, 11, 4), -3.0, "p", "x · #kontor-zins-2026-10", "Zinsen", "#kontor-zins-2026-10")
        b = Proposal("r", "interest", off.uuid, off.path, date(2026, 11, 4), -3.0, "p", "x · #kontor-zins-2026-09", "Gibtsnicht", "#kontor-zins-2026-09")
        br = self.Rec(); notes = []
        core.apply_proposals(br, led, [a, b], [], None, None, cats, notes)
        self.assertEqual([c[-1] for c in br.calls], ["Zinsen", None]); self.assertEqual(len(notes), 1); self.assertIn("Gibtsnicht", notes[0])

    def test_comment_is_added_never_replaced(self):
        import mm_bridge
        t = F.tx("priv.giro", date(2026, 10, 1), -10.0, "Laden", "Einkauf", comment="meine Notiz")
        br = self.Rec([t]); br.append_comment = mm_bridge.Bridge.append_comment.__get__(br)
        self.assertTrue(br.append_comment(t["id"], t["accountUuid"], date(2026, 10, 1), "Beleg: 2026/a.pdf"))
        self.assertEqual(br.calls, [("set", t["id"], None, "meine Notiz\nBeleg: 2026/a.pdf")])
        t["comment"] = "meine Notiz\nBeleg: 2026/a.pdf"; br.calls.clear()
        self.assertFalse(br.append_comment(t["id"], t["accountUuid"], date(2026, 10, 1), "Beleg: 2026/a.pdf")); self.assertEqual(br.calls, [])
        self.assertFalse(br.append_comment(999999, t["accountUuid"], date(2026, 10, 1), "x")); self.assertEqual(br.calls, [])       # not found: nothing


class MarkTests(unittest.TestCase):
    """Kontor's mark reads "#kontor-<kind>-..." (so MoneyMoney shows who made a booking). Nothing else is one -- also not the
    "#mm-..." of versions before 3.12: such a booking is one of your own, like any other."""

    def test_only_kontors_mark_is_one(self):
        from model import marks_in, has_mark
        import rules
        self.assertEqual(marks_in("Zinsen · #kontor-zins-2026-01 und #kontor-wert-20260101-2"), ["#kontor-zins-2026-01", "#kontor-wert-20260101-2"])
        self.assertEqual(marks_in("Zinsen · #mm-zins-2026-01"), []); self.assertEqual(marks_in(None), [])
        self.assertTrue(has_mark("x #kontor-tx-5")); self.assertFalse(has_mark("x #mm-tx-5")); self.assertFalse(has_mark("#kontor kein Zeichen"))
        self.assertTrue(rules.is_value_tag("#kontor-wert-20260101-1"))
        self.assertFalse(rules.is_value_tag("#kontor-spiegel-20260101-1")); self.assertFalse(rules.is_value_tag("#mm-wert-20260101-1"))
        self.assertEqual(rules.bkey("a", "#kontor-zins-2026-01"), "a|#kontor-zins-2026-01")
        today = date(2026, 11, 4)
        # everything Kontor booked: nothing is proposed again
        led = make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today))
        cfg = company_cfg(loans=[loan_cfg()])
        res = plan_all(led, cfg, today)
        self.assertTrue(res.proposals); self.assertTrue(all(p.tag.startswith("#kontor-") and p.tag in p.purpose for p in res.proposals))
        booked = led.without_planned(keep=[p.key for p in res.proposals])
        self.assertEqual(plan_all(booked.fork(), cfg, today).proposals, [])
        # the same bookings under another mark are not Kontor's but yours, like any you made by hand -- and as such they still
        # count where they stand as Kontor made them: interest by its text and month, a repayment or a mirrored booking by an
        # equal one, the value by the balance (one you changed since, or moved, is no longer found by its mark)
        other = led.without_planned(keep=[p.key for p in res.proposals])
        for t in other.txs:
            t.purpose = t.purpose.replace("#kontor-", "#mm-")
        self.assertEqual(other.kontor_marked(), set())
        again = plan_all(other.fork(), cfg, today)
        self.assertEqual(again.proposals, []); self.assertEqual(again.warnings, [])
        self.assertTrue(any("Zinsen selbst gebucht" in i for i in again.info), again.info)
        o = F.tx("gb.kap.a", date(2026, 9, 1), -5000.0, "Ich", "Einlage")
        m = F.tx("priv.bet.gb", date(2026, 9, 1), 5000.0, "Beta GbR", "Einlage · #mm-gk-%d" % o["id"])
        mc = company_cfg(companies=[], account_mirrors=[{"a": F.uid("priv.bet.gb") + " | B", "b": F.uid("gb.kap.a") + " | K", "from_date": "all"}])
        r = plan_all(make_ledger({}, [o, m]), mc, today)
        self.assertEqual(r.proposals, []); self.assertEqual(r.warnings, [])
        import service
        self.assertEqual(service.kontor_bookings(other), [])                                # not in the list of Kontor's bookings either
        # a decision not to book: by account and mark
        z = next(p for p in res.proposals if p.kind == "interest")
        left = plan_all(make_ledger({"ga.vd": -1200000.0}, F.ga_transactions(today)), dict(cfg, not_book=[{"key": z.account_uuid + "|" + z.tag}]), today)
        self.assertNotIn(z.tag, [p.tag for p in left.proposals])

    def test_a_mark_someone_sent_makes_no_account_bookable(self):
        """The purpose of a payment is written by its sender. A mark of Kontor in it must not make a bank account one that Kontor
        books into: only a booking as Kontor makes them counts (nothing a bank adds -- no account of the other side, no
        booking text)."""
        today = date(2026, 11, 4)
        giro = F.uid("priv.giro")
        plain = make_ledger({}, [])
        self.assertEqual(plain.fetch_kind(giro)[0], "online"); self.assertFalse(plain.writable(giro))
        for sent in (F.tx("priv.giro", date(2026, 10, 1), 0.01, "Fremder", "Rechnung 4711 #kontor-ref-2026", counter_iban="DE02300209000106531065"),
                     F.tx("priv.giro", date(2026, 10, 1), 0.01, "Fremder", "#kontor-zins-2026-09", booking_text="Gutschrift"),
                     F.tx("priv.giro", date(2026, 10, 1), 0.01, "Fremder", "#kontor-wert-20261001-1", counter_iban="DE02300209000106531065", booking_text="Überweisung")):
            led = make_ledger({}, [sent])
            self.assertEqual(led.fetch_kind(giro), ("online", "s_grund_bank"), sent["purpose"])
            self.assertFalse(led.writable(giro))
            self.assertEqual(led.kontor_marked(), set())
        # a booking of Kontor's own (a name and a purpose, nothing else) still shows an account kept by hand
        own = make_ledger({}, [F.tx("priv.giro", date(2026, 10, 1), 12.0, "Alpha GbR", "Zinsen 09/2026 · #kontor-zins-2026-09")])
        self.assertEqual(own.fetch_kind(giro)[0], "offline"); self.assertEqual(own.kontor_marked(), {giro})
        # and a bank account with such a payment gets no booking from a rule that names it
        cfg = company_cfg(companies=[], account_mirrors=[{"a": giro + " | Giro", "b": F.uid("priv.bet.gb") + " | B", "from_date": "all"}])
        sent = F.tx("priv.giro", date(2026, 10, 1), 0.01, "Fremder", "Rechnung #kontor-ref-2026", counter_iban="DE02300209000106531065")
        res = plan_all(make_ledger({}, [sent, F.tx("priv.bet.gb", date(2026, 10, 2), 500.0, "Beta GbR", "Einlage")]), cfg, today)
        self.assertNotIn(giro, [p.account_uuid for p in res.proposals])


class ReferenceTests(unittest.TestCase):
    """What points to something else finds it: help sections in both languages, help icons, the addresses the interface calls."""

    def test_help_icons_sections_and_addresses(self):
        import re as _re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        read = lambda *p: open(os.path.join(root, *p), encoding="utf-8").read()   # noqa: E731
        js, de, en, svc = read("web", "app.js"), read("docs", "help.de.md"), read("docs", "help.en.md"), read("service.py")
        a_de, a_en = set(_re.findall(r'<a id="([\w-]+)"', de)), set(_re.findall(r'<a id="([\w-]+)"', en))
        self.assertEqual(a_de, a_en)                                               # the same sections in both languages
        self.assertEqual(len(_re.findall(r"^#{2,3} ", de, _re.M)), len(_re.findall(r"^#{2,3} ", en, _re.M)))
        block = js[js.index("const H = {"):js.index("const HELP_AT")]
        tips = set(_re.findall(r"^\s*(\w+):", block, _re.M)) | set(_re.findall(r"[,{]\s*(\w+): t\(", block))
        at = js[js.index("const HELP_AT = {"):]; at = dict(_re.findall(r"(\w+): '([\w-]+)'", at[:at.index("};")]))
        self.assertFalse(sorted(set(_re.findall(r"hq\('(\w+)'\)", js)) - tips - {"schluessel"}), "help icon without a text")
        self.assertFalse(sorted(v for v in at.values() if v not in a_de), "help icon pointing to a section that is not there")
        self.assertFalse(sorted(k for k in at if k not in tips), "section for a help icon that is not there")
        # beside every page title: its line of text and its section (the general settings: the line only)
        i18 = read("web", "i18n.js"); cat = json.loads(i18[i18.index("{"):i18.rindex("}") + 1])
        pg = js[js.index("const PAGE_HELP = {"):]; pg = dict(_re.findall(r"'?([\w/]+)'?: '([\w-]*)'", pg[:pg.index("};")]))
        self.assertTrue(len(pg) > 20 and all(v in a_de for v in pg.values() if v), pg)
        self.assertFalse(sorted(k for k in pg if "page_" + k.replace("/", "_") not in cat), "page without its line of text")
        self.assertTrue(set(pages) - {"help"} <= {k.split("/")[0] for k in pg} if (pages := set(_re.findall(r"(\w+):", js[js.index("const TITLES"):][:js[js.index("const TITLES"):].index("};")]))) else True)
        links = set(_re.findall(r"#help/([\w-]+)", js)) | set(_re.findall(r"more\('([\w-]+)'\)", js))
        self.assertFalse(sorted(x for x in links if x not in a_de))
        for text in (de, en):
            for img in _re.findall(r"\]\((img/[\w/.-]+)\)", text):
                self.assertTrue(os.path.exists(os.path.join(root, "docs", img)), img)
        known = set(_re.findall(r'"(/api/[\w/-]+)"', svc))
        used = set(_re.findall(r"api\(\s*[`'](/api/[\w/-]+)", js)) | set(_re.findall(r"fetch\(\s*[`'](/api/[\w/-]+)", js))
        self.assertFalse(sorted(e for e in used if e not in known and not any(e.startswith(k) for k in known if k.endswith("/"))), "address the service does not know")
        titles = js[js.index("const TITLES"):]; pages = set(_re.findall(r"(\w+):", titles[:titles.index("};")]))
        self.assertFalse(sorted(x for x in set(_re.findall(r'href="#(\w+)["/]', js + read("web", "index.html"))) if x not in pages), "link to a page that is not there")


class FileFormatTests(unittest.TestCase):
    """Packages and backups from before 3.15.0 name their settings differently: refused with a clear message."""

    def test_old_package_refused(self):
        import core
        cur = core.merged_config({})
        for v in ("3.14.9", "2.0", "kaputt"):
            with self.assertRaises(ValueError):
                core.import_package(cur, {"kontor_package": 1, "version": v, "config": {"areas": []}}, None, "replace")
        cfg, _, _ = core.import_package(cur, {"kontor_package": 1, "version": "3.15.0", "config": {"areas": []}}, None, "merge")
        self.assertEqual(cfg["areas"], [])
        core.import_package(cur, {"config": {"areas": []}}, None, "merge")          # written by hand, no version: current
