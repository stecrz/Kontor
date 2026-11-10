import copy
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from model import Ledger, accounts_from_export, tx_from_export, fmt_eur  # noqa: E402
from rules import Seen, plan_loan, plan_all  # noqa: E402
import fixtures as F  # noqa: E402


def loan_cfg(**over):
    cfg = {
        "name": "Verkäuferdarlehen",
        "darlehenskonto": "Alpha GbR / Verbindlichkeiten / Verkäuferdarlehen",
        "quellkonten": ["Alpha GbR / Liquidität / Stadtbank Kontokorrent"],
        "erkennung": {"gegen_iban": F.SELLER_IBAN, "text_enthaelt": ["Urkunde 1234/2025"]},
        "ab_datum": "2026-01-01",
        "zins": {"modell": "jahresbasis", "satz": [{"ab": "2025-11-20", "prozent": 3.3}], "buchungstag": "ultimo"},
        "buchung": {"gegenpartei": "Verkäufer", "kategorie_tilgung": "Umbuchung", "kategorie_zins": "Zinsen"},
        "quelle_kommentar": True,
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
        self.assertEqual(led.resolve("Beta GbR / Liquidität / Stadtbank Kontokorrent").uuid, F.uid("shs.kk"))
        self.assertEqual(led.resolve("Liquidität / Stadtbank Kontokorrent" if False else F.uid("pb.kk")).name, "Stadtbank Kontokorrent")
        self.assertEqual([r.name for r in led.roots()], ["Privat", "Alpha GbR", "Beta GbR"])

    def test_uuid_label_references_and_hints(self):
        led = make_ledger({}, [])
        vd = led.resolve(F.uid("pb.vd") + " | Verkäuferdarlehen")
        self.assertEqual(vd.name, "Verkäuferdarlehen"); self.assertEqual(led.hints, [])
        # umbenannt: UUID gilt, Hinweis
        led.resolve(F.uid("pb.vd") + " | Alter Name")
        self.assertTrue(any("heißt jetzt" in h for h in led.hints))
        # UUID weg, Name vorhanden: Rueckfall + Hinweis mit neuer UUID
        led2 = make_ledger({}, [])
        acc = led2.resolve("00000000-0000-0000-0000-000000000000 | Verkäuferdarlehen")
        self.assertEqual(acc.uuid, F.uid("pb.vd"))
        self.assertTrue(any("Neue UUID" in h for h in led2.hints))
        with self.assertRaises(KeyError):
            led2.resolve("00000000-0000-0000-0000-000000000000 | Gibt es nicht")
        # Offline-Erkennung: Extension-Konto ohne BLZ, aber aktualisiert -> nicht manuell
        from model import Account
        ext = Account(uuid="x", name="PayPal", type="Girokonto", group=False, indentation=3, balance=0.0, currency="EUR",
                      bank_code="", refresh=__import__("datetime").datetime(2026, 11, 4, 8, 0))
        self.assertFalse(ext.offline)
        self.assertTrue(led.resolve("Verkäuferdarlehen").offline)

    def test_group_balance_and_balance_at(self):
        txs = F.pb_transactions(date(2026, 11, 4))
        bal = {"pb.vd": -1600000.0 + 8250.0 * 11}          # 11 Annuitaeten bereits gespiegelt? nein: nur KK
        led = make_ledger({"pb.kk": 40000.0}, txs)
        pb = led.resolve("Alpha GbR")
        self.assertAlmostEqual(led.group_balance(pb.uuid), 40000 + 1900000 - 1600000 - 240000, 2)
        # KK-Saldo am 31.12.2025 = heute - alle Buchungen 2026 (11 x -8250)
        self.assertAlmostEqual(led.balance_at(F.uid("pb.kk"), date(2025, 12, 31)), 40000 + 11 * 8250, 2)
        # Datumskonvertierung: lokale Mitternacht -> Datum bleibt der 1.
        kk = led.transactions(F.uid("pb.kk"))
        self.assertEqual(kk[0].booking_date, date(2026, 1, 1))


class LoanTests(unittest.TestCase):
    def test_first_run_books_all_months(self):
        today = date(2026, 11, 4)
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        res = plan_loan(led, loan_cfg(), today)
        tilg = [p for p in res.proposals if p.kind == "tilgung"]
        zins = [p for p in res.proposals if p.kind == "zins"]
        self.assertEqual(len(tilg), 11)                      # Jan..Nov
        self.assertEqual(len(zins), 10)                      # Jan..Okt (Nov-Ultimo liegt in der Zukunft)
        self.assertEqual({p.kind for p in res.proposals}, {"tilgung", "zins"})        # the payments themselves are never touched
        self.assertTrue(all(p.account_uuid == led.resolve(loan_cfg()["darlehenskonto"]).uuid for p in res.proposals))
        self.assertTrue(all(p.amount == 8250.0 for p in tilg))
        self.assertTrue(all(p.amount == -4400.0 for p in zins))   # 1.600.000 x 3,3 % / 12
        self.assertEqual(zins[0].booking_date, date(2026, 1, 31))
        self.assertIn("#kontor-zins-2026-01", zins[0].purpose)
        self.assertIn("#kontor-tx-", tilg[0].purpose)
        self.assertTrue(tilg[0].purpose.startswith("Annuität "))
        # In-Memory-Saldo nach allen Buchungen
        vd = led.resolve("Verkäuferdarlehen")
        self.assertAlmostEqual(vd.balance, -1600000 + 11 * 8250 - 10 * 4400, 2)
        self.assertFalse(res.warnings, res.warnings)

    def test_idempotent_second_run(self):
        today = date(2026, 11, 4)
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        res1 = plan_loan(led, loan_cfg(), today)
        # Zweiter Lauf: Buchungen "existieren" jetzt im Ledger (in-memory) -> nichts Neues
        res2 = plan_loan(led, loan_cfg(), today)
        self.assertTrue(res1.proposals)
        self.assertEqual(res2.proposals, [])

    def test_december_remainder_is_cent_exact(self):
        today = date(2027, 1, 5)
        led = make_ledger({"pb.vd": -1234567.0}, [F.tx("pb.vd", date(2025, 12, 1), -1234567.0, "V", "Start")])
        cfg = loan_cfg(quellkonten=[], erwartet_monatlich=False)
        res = plan_loan(led, cfg, today)
        zins = [p for p in res.proposals if p.kind == "zins" and p.booking_date.year == 2026]
        self.assertEqual(len(zins), 12)
        total = round(sum(-p.amount for p in zins), 2)
        self.assertAlmostEqual(total, round(1234567.0 * 0.033, 2), 2)

    def test_year_base_follows_prior_year_end_and_sondertilgung(self):
        # Sondertilgung im Maerz 2026 aendert 2026 nichts, 2027 schon
        today = date(2027, 2, 15)
        extra = [F.tx("pb.kk", date(2026, 3, 15), -50000.0, "Verkäufer", "Sondertilgung " + F.ANNUITY_TEXT, "", F.SELLER_IBAN)]
        txs = F.pb_transactions(today, extra=extra)
        led = make_ledger({"pb.vd": -1600000.0}, txs)
        res = plan_loan(led, loan_cfg(), today)
        z26 = [p for p in res.proposals if p.kind == "zins" and p.booking_date.year == 2026]
        z27 = [p for p in res.proposals if p.kind == "zins" and p.booking_date.year == 2027]
        self.assertTrue(all(p.amount == -4400.0 for p in z26))
        # Basis 2027 = Stand 31.12.2026 = -1.600.000 + 12*8.250 + 50.000 - 52.800 Zinsen
        base27 = 1600000 - 12 * 8250 - 50000 + 52800
        self.assertEqual(len(z27), 1)
        self.assertAlmostEqual(z27[0].amount, -round(round(base27 * 0.033, 2) / 12, 2), 2)
        sonder = [p for p in res.proposals if p.kind == "tilgung" and p.amount == 50000.0]
        self.assertEqual(len(sonder), 1)
        self.assertTrue(sonder[0].purpose.startswith("Sondertilgung "))

    def test_manual_interest_guard_and_ab_datum(self):
        today = date(2026, 11, 4)
        # Jan..Okt manuell gebucht, Automatik ab 2026-11-01
        txs = F.pb_transactions(today, with_manual_interest_until=date(2026, 10, 1))
        led = make_ledger({"pb.vd": -1600000.0 + 10 * 8250 - 10 * 4400}, txs)
        res = plan_loan(led, loan_cfg(ab_datum="2026-11-01"), today)
        tilg = [p for p in res.proposals if p.kind == "tilgung"]
        zins = [p for p in res.proposals if p.kind == "zins"]
        self.assertEqual(len(tilg), 1)                       # nur November
        self.assertEqual(len(zins), 0)                       # November-Ultimo noch nicht erreicht
        # Basis 2026 bleibt der Stand 31.12.2025 trotz manueller Buchungen
        self.assertTrue(any("Zinsbasis 2026 = 1.600.000,00" in i for i in res.info), res.info)
        # repayments and interest you booked yourself (no mark): the repayments count as booked, the months of your interest
        # are left to you -- one note, no warning, nothing twice
        txs2 = F.pb_transactions(today, with_manual_interest_until=date(2026, 10, 1))
        led2 = make_ledger({"pb.vd": -1600000.0}, txs2)
        res2 = plan_loan(led2, loan_cfg(ab_datum="2026-01-01"), today)
        self.assertEqual(len([p for p in res2.proposals if p.kind == "zins"]), 0)
        self.assertEqual([p.booking_date for p in res2.proposals if p.kind == "tilgung"], [date(2026, 11, 1)])
        self.assertFalse(res2.warnings, res2.warnings)
        own = [i for i in res2.info if "selbst gebucht" in i]
        self.assertEqual(len(own), 1); self.assertIn("01/2026", own[0]); self.assertIn("10/2026", own[0])

    def test_missing_base_warns(self):
        today = date(2026, 6, 1)
        led = make_ledger({"pb.vd": -1600000.0}, [F.tx("pb.vd", date(2026, 2, 1), -1600000.0, "V", "Start")])
        res = plan_loan(led, loan_cfg(quellkonten=[], erwartet_monatlich=False), today)
        self.assertTrue(any("Jahresanfangsbasis" in w for w in res.warnings))
        self.assertEqual([p for p in res.proposals if p.kind == "zins"], [])
        cfg = loan_cfg(quellkonten=[], erwartet_monatlich=False)
        cfg["zins"]["basis_override"] = {"2026": 1600000}
        res = plan_loan(led, cfg, today)
        self.assertEqual(len([p for p in res.proposals if p.kind == "zins"]), 5)

    def test_restschuld_monatlich_model(self):
        today = date(2026, 4, 2)
        txs = [F.tx("pb.vd", date(2025, 12, 1), -120000.0, "Bank", "Auszahlung")]
        for m in (1, 2, 3):
            txs.append(F.tx("pb.kk", date(2026, m, 1), -1000.0, "Bank", "Rate " + F.ANNUITY_TEXT, "", F.SELLER_IBAN))
        led = make_ledger({"pb.vd": -120000.0}, txs)
        cfg = loan_cfg(zins={"modell": "restschuld_monatlich", "satz": [{"ab": "2025-12-01", "prozent": 6.0}]})
        res = plan_loan(led, cfg, today)
        zins = [p for p in res.proposals if p.kind == "zins"]
        # Jan: 120.000 x 6 %/12 = 600; Feb: (120.000-1.000+600) ... Restschuld nach Rate und Zins
        self.assertEqual(len(zins), 3)
        self.assertAlmostEqual(zins[0].amount, -600.0, 2)
        self.assertAlmostEqual(zins[1].amount, -round((120000 - 1000 + 600) * 0.06 / 12, 2), 2)

    def test_no_payment_warning(self):
        today = date(2026, 11, 4)
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(date(2026, 8, 1)))
        res = plan_loan(led, loan_cfg(), today)
        self.assertTrue(any("seit über 35 Tagen" in w for w in res.warnings))
        # Automatik gerade erst gestartet, Rate noch nicht gelaufen: nur Info
        led = make_ledger({"pb.vd": -1600000.0}, [F.tx("pb.vd", date(2025, 12, 1), -1600000.0, "V", "Start")])
        res = plan_loan(led, loan_cfg(ab_datum="2026-11-01"), today)
        self.assertFalse(any("keine passende Zahlung" in w for w in res.warnings))
        self.assertTrue(any("keine passende Zahlung" in i for i in res.info))
        # IBAN-only Erkennung mit Ausschlusstext
        txs = F.pb_transactions(today, extra=[F.tx("pb.kk", date(2026, 10, 20), -300.0, "Verkäufer", "Nebenkostenabrechnung", "", F.SELLER_IBAN)])
        led = make_ledger({"pb.vd": -1600000.0}, txs)
        cfg = loan_cfg(erkennung={"gegen_iban": F.SELLER_IBAN, "ausschliessen_text": ["Nebenkosten"]})
        res = plan_loan(led, cfg, today)
        self.assertEqual(len([p for p in res.proposals if p.kind == "tilgung"]), 11)


def company_cfg(**over):
    cfg = {"bereiche": [{"id": "p", "name": "Privat", "art": "privat", "haupt": True, "konten": [F.uid("priv") + " | Privat"]},
                        {"id": "a", "name": "Alpha GbR", "art": "gesellschaft", "anteil": 0.49, "konten": [F.uid("pb") + " | Alpha GbR"]},
                        {"id": "b", "name": "Beta GbR", "art": "gesellschaft", "anteil": 0.49, "konten": [F.uid("shs") + " | Beta GbR"]}],
           "gesellschaften": [{"bereich": "a", "beteiligung": F.uid("priv.bet.pb") + " | Beteiligung an Alpha GbR"}]}
    cfg.update(over)
    return cfg


class CompanyTests(unittest.TestCase):
    def test_participation_value(self):
        today = date(2026, 11, 4)
        led = make_ledger({}, [])
        res = plan_all(led, company_cfg(), today)
        pb_value = 40000 + 1900000 - 1600000 - 120000 - 120000      # = 100.000 (capital accounts are debts of the company)
        want = round(0.49 * pb_value, 2)
        self.assertEqual(len(res.proposals), 1)
        self.assertEqual((res.proposals[0].kind, res.proposals[0].booking_date), ("wert", today))
        self.assertAlmostEqual(res.proposals[0].amount, want - (-90000.0), 2)
        self.assertEqual(led.resolve("Beteiligung an Alpha GbR").balance, want)
        self.assertEqual(res.preview, [{"art": "beteiligung", "bereich": "a", "ziel": F.uid("priv.bet.pb"), "ist": -90000.0, "rueck": 0, "offen": 1,
                                        "rueck_summe": 0.0, "unbekannt": [], "takt": "taeglich", "soll": want, "quelle": float(pb_value), "diff": want + 90000.0,
                                        "beginn": None}])
        self.assertEqual(plan_all(led, company_cfg(), today).proposals, [])        # again: nothing
        # the share comes only from the area; without it nothing is booked
        cfg = company_cfg(); cfg["bereiche"][1].pop("anteil")
        res = plan_all(make_ledger({}, []), cfg, today)
        self.assertEqual(res.proposals, []); self.assertTrue(any("Anteil fehlt" in w for w in res.warnings))

    def test_loans_before_participation_and_equity_roles(self):
        today = date(2026, 11, 4)
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        config = company_cfg(darlehen=[loan_cfg()])
        res = plan_all(led, config, today)
        wert = [p for p in res.proposals if p.kind == "wert"]
        self.assertEqual(len(wert), 1)
        pb_value = 40000 + 1900000 + (-1600000 + 11 * 8250 - 10 * 4400) - 240000
        self.assertAlmostEqual(wert[0].amount, round(0.49 * pb_value, 2) + 90000.0, 2)
        # capital accounts kept as the company's equity are not part of its value
        led2 = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        config["bilanz"] = {"rollen": {F.uid("pb.kap.s") + " | Kapitalkonto A": "eigenkapital", F.uid("pb.kap.p") + " | Kapitalkonto B": "eigenkapital"}}
        wert2 = [p for p in plan_all(led2, config, today).proposals if p.kind == "wert"]
        self.assertAlmostEqual(wert2[0].amount, round(0.49 * (pb_value + 240000), 2) + 90000.0, 2)

    def test_counter_account(self):
        """A counter account mirrors each booking (see MirrorTests); its text names the original account."""
        today = date(2026, 11, 4)
        led = make_ledger({}, [F.tx("shs.kap.s", date(2026, 9, 1), -5000.0, "Ich", "Einlage")])
        cfg = company_cfg(gesellschaften=[{"bereich": "b", "rueckwirkend_ab": "alles", "gegenkonten": [
            {"konto": F.uid("priv.bet.shs") + " | Beteiligung an Beta GbR", "quelle": F.uid("shs.kap.s") + " | Kapitalkonto A"}]}])
        res = plan_all(led, cfg, today)
        self.assertEqual([(p.kind, p.amount, p.booking_date) for p in res.proposals], [("spiegel", 5000.0, date(2026, 9, 1))])
        self.assertTrue(res.proposals[0].tag.startswith("#kontor-gk-"))
        self.assertIn("Einlage · gespiegelt von Kapitalkonto A · #kontor-gk-", res.proposals[0].purpose)
        self.assertEqual(res.proposals[0].payee, "Beta GbR")              # the sender is the company, not its account
        self.assertEqual(res.preview[0]["i"], 0)

    def test_back_to_month_ends(self):
        today = date(2026, 11, 4)
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        cfg = company_cfg(darlehen=[loan_cfg()])
        cfg["gesellschaften"][0].update(rueckwirkend_ab="2026-03", takt="monatlich")
        res = plan_all(led, cfg, today, seen=Seen(Seen.top_id(led), today))
        wert = [p for p in res.proposals if p.kind == "wert"]
        days = [p.booking_date for p in wert]
        self.assertEqual(days[:8], [date(2026, m + 1, 1) - timedelta(days=1) for m in range(3, 11)])      # 31.03. ... 31.10.
        target = led.resolve("Beteiligung an Alpha GbR")
        for p in wert[:8]:          # each month end shows the share of the company's value at that day
            accs = [a for a in led.descendants(F.uid("pb"))]
            v = round(sum(led.balance_at(a.uuid, p.booking_date) for a in accs), 2)
            self.assertAlmostEqual(led.balance_at(target.uuid, p.booking_date), round(0.49 * v, 2), 2)
        self.assertEqual(len({p.tag for p in wert}), len(wert))
        pv = [x for x in res.preview if x["art"] == "beteiligung"][0]
        self.assertEqual(pv["rueck"], 8); self.assertTrue(all(p.retro and p.group == "a" for p in wert))
        self.assertEqual(len(wert), 8)                  # monthly: no booking today, the month runs until its end
        # a second run books nothing (the bookings are there now, every month end is checked again and right); a month later
        # only the month just ended -- new, so booked without asking when booking fully automatically
        self.assertEqual([p for p in plan_all(led, cfg, today).proposals if p.kind == "wert"], [])
        later = plan_all(led, cfg, date(2026, 12, 2), seen=Seen(Seen.top_id(led), today))
        self.assertEqual([x for x in later.preview if x["art"] == "beteiligung"][0]["rueck"], 0)
        self.assertEqual([(p.booking_date, p.retro) for p in later.proposals if p.kind == "wert"], [(date(2026, 11, 30), False)])

    def test_back_to_daily(self):
        """Daily (default): back to every day on which the company's value changed, then today; once done only today."""
        today = date(2026, 11, 4)
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        cfg = company_cfg(darlehen=[loan_cfg()])
        cfg["gesellschaften"][0]["rueckwirkend_ab"] = "2026-03"
        res = plan_all(led, cfg, today, seen=Seen(Seen.top_id(led), today))
        wert = [p for p in res.proposals if p.kind == "wert"]
        target = led.resolve("Beteiligung an Alpha GbR")
        change_days = sorted({t.booking_date for a in led.descendants(F.uid("pb")) for t in led.transactions(a.uuid) if date(2026, 3, 1) <= t.booking_date < today})
        self.assertTrue(set(p.booking_date for p in wert if p.retro) <= set(change_days) | {date(2026, 3, 1)})
        for d in change_days:
            v = round(sum(led.balance_at(a.uuid, d) for a in led.descendants(F.uid("pb"))), 2)
            self.assertAlmostEqual(led.balance_at(target.uuid, d), round(0.49 * v, 2), 2)
        self.assertAlmostEqual(target.balance, res.preview[-1]["soll"], 2)
        self.assertTrue(wert and all(p.retro for p in wert))          # the past waits for you (nothing new since the last check) ...
        self.assertEqual([p for p in plan_all(led, cfg, today).proposals if p.kind == "wert"], [])        # all there: nothing
        # ... and left out, today's value is booked at once: the difference of all of them
        led3 = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        seen, hold = Seen(Seen.top_id(led3), today), set()
        for rounds in range(1, 9):                    # as a run does: left out, planned again, until nothing depends on it
            held = plan_all(led3.fork(), cfg, today, hold=hold, seen=seen)
            more = {p.key for p in held.proposals if p.retro} - hold
            if not more:
                break
            hold |= more
        self.assertLess(rounds, 5)
        now = [p for p in held.proposals if p.kind == "wert"]
        self.assertEqual([(p.booking_date, p.retro) for p in now], [(today, False)])
        self.assertAlmostEqual(now[0].amount, round(0.49 * sum(a.balance for a in led3.descendants(F.uid("pb"))) + 90000.0, 2), delta=0.05)

    def test_back_to_a_day_or_everything(self):
        """"Rückwirkend ab": a day (monthly: the month ends from then on) or "alles" (since the company's first transaction)."""
        today = date(2026, 11, 4)
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        cfg = company_cfg(darlehen=[loan_cfg()])
        cfg["gesellschaften"][0].update(rueckwirkend_ab="2026-03-15", takt="monatlich")
        days = [p.booking_date for p in plan_all(led, cfg, today).proposals if p.kind == "wert"]
        self.assertEqual(days[0], date(2026, 3, 31)); self.assertEqual(days[-1], date(2026, 10, 31))
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        cfg["gesellschaften"][0].update(rueckwirkend_ab="alles", takt="taeglich")
        res = plan_all(led, cfg, today, seen=Seen(Seen.top_id(led), today))
        first = min(t.booking_date for a in led.descendants(F.uid("pb")) for t in led.transactions(a.uuid) if t.id > 0)
        retro = [p for p in res.proposals if p.kind == "wert" and p.retro]
        self.assertTrue(retro); self.assertGreaterEqual(min(p.booking_date for p in retro), first)
        self.assertEqual(min(p.booking_date for p in retro), first)          # the first day already differs (opening balance)

    def test_back_to_unknown_months_skipped(self):
        # a portfolio in the company: its past value is not known -> those months are not booked
        today = date(2026, 11, 4)
        led = make_ledger({}, [])
        cfg = company_cfg(bereiche=[{"id": "a", "name": "Alpha GbR", "art": "gesellschaft", "anteil": 0.5,
                                     "konten": [F.uid("pb") + " | Alpha GbR", F.uid("priv.depot") + " | Depot"]},
                                    {"id": "p", "name": "Privat", "art": "privat", "haupt": True, "konten": [F.uid("priv.bet") + " | Beteiligungen"]}])
        cfg["gesellschaften"][0].update(rueckwirkend_ab="2026-09", takt="monatlich")
        res = plan_all(led, cfg, today)
        self.assertEqual([p.booking_date for p in res.proposals], [])
        self.assertEqual(res.preview[0]["unbekannt"], ["09/2026", "10/2026"])
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
        vd, bet, giro = F.uid("pb.vd"), F.uid("priv.bet.pb"), F.uid("priv.giro")
        fetched = {"refreshTimestamp": datetime(2026, 10, 1)}
        led = led_with({vd: fetched, bet: fetched})
        self.assertTrue(led.writable(bet))                                   # type "Offline-Konto"
        self.assertTrue(led.writable(vd))                                    # manual bookings: fetch time, but no bank code or number
        self.assertFalse(led.writable(giro)); self.assertFalse(led.writable(F.uid("pb"))); self.assertFalse(led.writable(F.uid("priv.depot")))
        # a bank code typed into a manual account
        blz = dict(fetched, bankCode="70150000")
        self.assertFalse(led_with({vd: blz}).writable(vd))
        self.assertTrue(led_with({vd: {"bankCode": "70150000"}}).writable(vd))          # never fetched
        self.assertTrue(led_with({vd: blz}).writable(vd, {"abruf": {"offline": [vd + " | Verkäuferdarlehen"]}}))      # your choice
        self.assertTrue(led_with({vd: blz}, [F.tx("pb.vd", date(2026, 9, 30), -10.0, "x", "Zinsen 09/2026 · #mm-zins-2026-09")]).writable(vd))
        led2 = led_with({vd: blz}); led2.post(vd, date(2026, 11, 4), 1.0, "x", "#kontor-wert-20261104-1")
        self.assertFalse(led2.writable(vd))                                  # a booking planned in this run does not count
        self.assertFalse(led.writable(bet, {"abruf": {"online": [bet + " | Beteiligung an Alpha GbR"]}}))
        # the rules use it
        self.assertEqual(len(plan_all(led_with({bet: fetched}), company_cfg(), date(2026, 11, 4)).proposals), 1)
        res = plan_all(led_with({bet: dict(fetched, bankCode="12030000", type="Girokonto")}), company_cfg(), date(2026, 11, 4))
        self.assertEqual(res.proposals, []); self.assertTrue(any("Bankanbindung" in w for w in res.warnings))

    def test_circular_reference_rejected(self):
        led = make_ledger({}, [])
        cfg = company_cfg(gesellschaften=[{"bereich": "a", "beteiligung": F.uid("pb.immo") + " | Immobilie Parkweg"}])
        res = plan_all(led, cfg, date(2026, 11, 4))
        self.assertTrue(any("Zirkelbezug" in w for w in res.warnings))
        self.assertEqual(res.proposals, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)


class CatalogTests(unittest.TestCase):
    """Texte fuer den Nutzer: ein Katalog (web/i18n.js), jeder benutzte Schluessel mit Deutsch und Englisch, gleiche Platzhalter."""

    def test_katalog_vollstaendig(self):
        import glob
        import json
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
            self.assertEqual(i18n.tr("sync_ohne_abruf", 3), "Offline accounts (3)")
        finally:
            i18n.set_lang("de")
        self.assertEqual(i18n.tr("sync_ohne_abruf", 3), "Offline-Konten (3)")
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
        out, details = transit_series(L, leaves, {"a": "liquiditaet", "b": "liquiditaet"}, [(2026, 1), (2026, 2), (2026, 3)], {}, today)
        self.assertEqual(len(details), sum(1 for v in out.values() if v))
        return out

    def test_ueber_monatsende(self):
        t = self.run_transit([("a", date(2026, 1, 31), -500.0, "DE22"), ("b", date(2026, 2, 2), 500.0, "")])
        self.assertEqual(t, {"2026-01": 500.0, "2026-02": 0.0, "2026-03": 0.0})

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

    def test_aktuelle_version_hat_datum(self):
        import updates
        here = os.path.join(os.path.dirname(__file__), "..")
        with open(os.path.join(here, "CHANGELOG.md"), encoding="utf-8") as f:
            text = f.read()
        notes, datum = updates.changelog_section(text, updates.current_version())
        self.assertTrue(notes); self.assertRegex(datum, r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?$")


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
        r = H._portfolios(db, ["portfolio_chart", "securities"], [1], lambda k: {"saldo": 999.70}, D(2026, 11, 8))[1]
        self.assertEqual(r["werte"]["2026-09"], 1000.0); self.assertEqual(r["werte"]["2026-10"], 1000.3)

    def test_sold_position_ends_at_the_next_update(self):
        # sold in June: the next update (June 20) no longer has it -> not in the June month end
        import mm_history as H
        from datetime import date as D
        chart = [(D(2024, 5, 10), 500.0, 1), (D(2024, 5, 10), 200.0, 2), (D(2024, 6, 10), 520.0, 1), (D(2024, 6, 10), 210.0, 2),
                 (D(2024, 6, 20), 525.0, 1), (D(2024, 7, 10), 530.0, 1)]
        db = self._db(chart, [(1, 1, 0), (2, 0, 1)])
        r = H._portfolios(db, ["portfolio_chart", "securities"], [1], lambda k: {"saldo": 530.0}, D(2024, 7, 20))[1]
        self.assertEqual(r["werte"]["2024-05"], 700.0); self.assertEqual(r["werte"]["2024-06"], 525.0)

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
        r = H._portfolios(db, ["portfolio_chart", "securities"], [1], lambda k: {"saldo": 999.70}, D(2026, 11, 8))[1]
        self.assertEqual(r["werte"]["2026-09"], 1000.0); self.assertEqual(r["werte"]["2026-10"], 1000.3)
        # the breakdown: the securities without the total entry, with name and ISIN; the old cash position until its replacement
        wp = {w["name"]: w for w in r["wertpapiere"]}
        self.assertEqual(sorted(wp), ["Titel 1", "Titel 3"]); self.assertEqual(wp["Titel 1"]["isin"], "XX0000000001")
        self.assertEqual(wp["Titel 1"]["werte"]["2026-10"], 1000.0); self.assertEqual(wp["Titel 3"]["werte"], {"2026-10": 0.3})

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
        r = H._portfolios(DB(), ["portfolio_chart", "securities"], [1], lambda k: {"saldo": 1000.0}, D(2026, 11, 8))[1]
        wp = {w["isin"]: w["name"] for w in r["wertpapiere"]}
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
        found = {"namen": {"IE00B4L5Y983": "ISHARES CORE MSCI WORLD"}, "ohne": [], "eigene": {"DE0007164600": "Alt"}}
        set_names(found, {"IE00B4L5Y983": "ISHARES CORE MSCI WORLD", "US0378331005": " Mein Name ", "DE0007164600": "", "XX0000000000": "Fremd"}, known)
        self.assertEqual(found["eigene"], {"US0378331005": "Mein Name"})          # unchanged or empty: none of your own
        self.assertEqual(found["namen"], {"IE00B4L5Y983": "ISHARES CORE MSCI WORLD"})

    def test_shown_name_keeps_moneymoneys_name_and_isin(self):
        from datetime import date as D
        from model import Account
        from report import depot_holdings
        acc = Account("u1", "Depot", "portfolio", False, 0, 0.0, "EUR", portfolio=True)
        state = {"historie_mm_wp": {"u1": [{"name": "", "isin": "IE00B4L5Y983", "werte": {"2026-09": 100.0}},
                                           {"name": "Beispiel", "isin": "US0378331005", "werte": {"2026-09": 50.0}},
                                           {"name": "", "isin": "DE0007164600", "werte": {"2026-09": 25.0}}]},
                 "wp_suche": {"namen": {"IE00B4L5Y983": "ISHARES CORE MSCI WORLD", "US0378331005": "NICHT GENUTZT"}}}
        rows = {r["isin"]: r for r in depot_holdings(acc, {"2026-09": 175.0}, ["2026-09"], D(2026, 11, 8), state, None, {})}
        a, b, c = rows["IE00B4L5Y983"], rows["US0378331005"], rows["DE0007164600"]
        self.assertEqual((a["name"], a["orig"], a["quelle"]), ("ISHARES CORE MSCI WORLD", "", "suche"))     # looked up: only without a name
        self.assertEqual((b["name"], b["orig"], b["quelle"]), ("Beispiel", "Beispiel", ""))                  # MoneyMoney's name goes first
        state["wp_suche"]["eigene"] = {"US0378331005": "Mein Name"}                                          # changed in the list of names
        b = {r["isin"]: r for r in depot_holdings(acc, {"2026-09": 175.0}, ["2026-09"], D(2026, 11, 8), state, None, {})}["US0378331005"]
        self.assertEqual((b["name"], b["orig"], b["quelle"]), ("Mein Name", "Beispiel", "eigen"))
        self.assertEqual((c["name"], c["orig"], c["quelle"]), ("DE0007164600", "", ""))                      # nothing known: the ISIN


class SecurityHardeningTests(unittest.TestCase):
    """No plain-text fallback, the key out of the data folder, sessions ended on a password change, external receipts limited."""

    def test_no_plain_text_fallback(self):
        import tempfile, storage
        d = tempfile.mkdtemp()
        orig = storage.selftest
        storage.selftest = lambda master: False
        try:
            with self.assertRaises(storage.StoreError):
                storage.Store(d, b"k" * 32, "datei")
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
        self.assertEqual((got, src), (key, "schluesselbund"))       # the same key (data stays readable), now in the keychain
        self.assertEqual(chain["w"], key.hex()); self.assertFalse(os.path.exists(path))

    def test_password_change_ends_other_sessions(self):
        import auth
        ss = auth.Sessions(); a = ss.create("127.0.0.1", "pw"); b = ss.create("100.64.0.2", "pw")
        self.assertEqual(ss.drop_others(a["token"]), 1)
        self.assertIsNotNone(ss.get(a["token"])); self.assertIsNone(ss.get(b["token"]))

    def test_external_receipts_limited(self):
        import tempfile, receipts, storage
        d = tempfile.mkdtemp(); st = storage.Store(d, None)
        bl = receipts.Belege(st, {"belege": {"ordner": os.path.join(d, "Belege")}})
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
        for pat, want in (("../../{jahr}", "2026"), ("/etc/{jahr}", "2026"), ("{jahr}/{monat}", os.path.join("2026", "03")), ("{jahr.__class__}", "2026")):
            bl = receipts.Belege(st, {"belege": {"ordner": os.path.join(d, "B"), "unterordner": pat}})
            self.assertEqual(bl.subfolder({"datum": "2026-03-04"}), want, pat)

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
            self.assertEqual((got, src), (fk, "schluesselbund")); self.assertFalse(os.path.exists(path))
            # no keychain at all and no key file: no new key file next to the data -- Kontor does not start
            storage._security = lambda args, input_text=None: (45, "", "denied")
            with self.assertRaises(storage.StoreError):
                storage.load_or_create_master_key(tempfile.mkdtemp())
        finally:
            storage._security = orig


class KontorBookingsTests(unittest.TestCase):
    def test_list_of_created_bookings(self):
        import service
        txs = [F.tx("pb.vd", date(2026, 10, 31), -4400.0, "Zinsen", "Zinsen Oktober #mm-zins-2026-10"),
               F.tx("priv.bet.pb", date(2026, 11, 2), 1500.0, "Wertanpassung", "Anteil 49 % #mm-wert-20261102-1"),
               F.tx("priv.giro", date(2026, 10, 3), -900.0, "Bank", "Rate", comment="→ Darlehen gespiegelt (#mm-tx-7)")]
        led = Ledger(accounts_from_export(F.accounts_raw({})), tx_from_export(txs))
        out = service.kontor_bookings(led)
        self.assertEqual([(x["art"], x["markierung"]) for x in out], [("wert", "#kontor-wert-20261102-1"), ("zins", "#kontor-zins-2026-10")])   # newest first; a comment alone is no booking
        self.assertEqual(out[1]["zweck"], "Zinsen Oktober"); self.assertEqual(out[1]["betrag"], -4400.0)
        self.assertEqual(service.kontor_bookings(None), [])


class StatelessLoanTests(unittest.TestCase):
    """Kontor keeps no list of its bookings: what is booked is recognised in MoneyMoney -- by its mark, or as an equal booking
    you made yourself. Deleted there: proposed again (older than the last check: only with your approval)."""
    today = date(2026, 11, 4)

    def booked(self, cfg=None):
        """All of the loan booked (as if written), then MoneyMoney read again."""
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(self.today))
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
        self.assertEqual(sorted((p.kind, p.booking_date.isoformat()) for p in again.proposals), [("tilgung", "2026-05-01"), ("zins", "2026-03-31")])
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
        pay = next(t for t in real.txs if t.account_uuid == F.uid("pb.kk") and t.booking_date == date(2026, 6, 1))
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
        both = real.fork(); both.post(F.uid("pb.vd"), date(2026, 7, 15), -4400.0, "Bank", "Zinsen Juli laut Bank").planned = False
        r = plan_loan(both, loan_cfg(), self.today)
        self.assertEqual(r.proposals, []); self.assertTrue(any("07/2026" in w for w in r.warnings), r.warnings)

    def test_new_since_last_check_and_dont_book(self):
        today = self.today
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(date(2026, 10, 30)))
        last = max(t.id for t in led.txs)
        before = plan_loan(led, loan_cfg(), date(2026, 10, 30))          # all booked until the last check on 30 October
        real = led.without_planned(keep=[p.key for p in before.proposals])
        real = Ledger(real.accounts, real.txs + tx_from_export([F.tx("pb.kk", date(2026, 11, 1), -8250.0, "Verkäufer", F.ANNUITY_TEXT, "", F.SELLER_IBAN)]))
        res = plan_loan(real.fork(), loan_cfg(), today, seen=Seen(last, date(2026, 10, 30)))
        self.assertEqual(sorted((p.kind, p.booking_date.isoformat(), p.retro) for p in res.proposals),
                         [("tilgung", "2026-11-01", False), ("zins", "2026-10-31", False)])       # the payment after it, the month ended after it
        # an older repayment left out (waiting for you): the interest after it waits too -- it is computed from the balance
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        t3 = next(p for p in plan_loan(led.fork(), loan_cfg(), today).proposals if p.kind == "tilgung" and p.booking_date == date(2026, 3, 1))
        res = plan_loan(led.fork(), loan_cfg(), today, seen=Seen(0, date(2000, 1, 1)), hold={t3.key})
        self.assertNotIn(t3.key, [p.key for p in res.proposals])
        self.assertEqual([p.booking_date for p in res.proposals if p.kind == "zins" and p.retro], [date(2026, m + 1, 1) - timedelta(days=1) for m in range(3, 11)])      # March to October
        self.assertFalse([p for p in res.proposals if p.kind == "zins" and p.booking_date < date(2026, 3, 1) and p.retro])
        # "Don't book" (settings): never proposed
        cfg = {"darlehen": [loan_cfg()], "nicht_buchen": [{"key": t3.key}]}
        self.assertNotIn(t3.key, [p.key for p in plan_all(make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today)), cfg, today).proposals])

    def test_two_equal_payments_one_booked_by_hand(self):
        txs = [F.tx("pb.kk", date(2026, 10, 1), -500.0, "Verkäufer", F.ANNUITY_TEXT, "", F.SELLER_IBAN),
               F.tx("pb.kk", date(2026, 10, 2), -500.0, "Verkäufer", F.ANNUITY_TEXT, "", F.SELLER_IBAN),
               F.tx("pb.vd", date(2026, 10, 1), 500.0, "Ich", "Rate von Hand")]
        led = make_ledger({"pb.vd": -1600000.0}, txs)
        cfg = loan_cfg(ab_datum="2026-10-01", zins={}, erwartet_monatlich=False)
        res = plan_loan(led, cfg, date(2026, 10, 20))
        self.assertEqual([(p.kind, p.booking_date) for p in res.proposals], [("tilgung", date(2026, 10, 2))])     # each booking counts once


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
        self.base = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(self.today))         # the same bookings (ids) each time

    def plan(self, led=None, **kw):
        led = led or self.base.fork()
        cfg = company_cfg(darlehen=[loan_cfg()])
        cfg["gesellschaften"][0].update(rueckwirkend_ab="2026-03", takt="monatlich")
        return led, cfg, plan_all(led, cfg, self.today, **kw)

    def test_left_out_or_changed_moves_only_the_next(self):
        _, _, res = self.plan()
        w = [p for p in res.proposals if p.kind == "wert"]
        self.assertEqual(len(w), 8)
        _, _, held = self.plan(hold={w[1].key})
        h = {p.key: p.amount for p in held.proposals if p.kind == "wert"}
        self.assertNotIn(w[1].key, h)
        self.assertAlmostEqual(h[w[2].key], round(w[1].amount + w[2].amount, 2), 2)          # the next one takes up the difference
        for p in [w[0]] + w[3:]:
            self.assertAlmostEqual(h[p.key], p.amount, 2)
        # a value adjustment follows MoneyMoney: its amount is not changed by hand (only its text)
        _, _, ed = self.plan(edits={w[1].key: {"betrag": round(w[1].amount + 100, 2), "zweck": "Mein Text"}})
        e = {p.key: p for p in ed.proposals if p.kind == "wert"}
        self.assertAlmostEqual(e[w[1].key].amount, w[1].amount, 2); self.assertEqual(e[w[1].key].purpose, "Mein Text · " + w[1].tag)
        # a loan's interest changed by hand: booked with your amount, the value after it follows
        z = next(p for p in res.proposals if p.kind == "zins" and p.booking_date == date(2026, 5, 31))
        _, _, zed = self.plan(edits={z.key: {"betrag": -1000.0}})
        zz = {p.key: p.amount for p in zed.proposals}
        self.assertEqual(zz[z.key], -1000.0)
        self.assertAlmostEqual(zz[w[2].key], round(w[2].amount + 0.49 * (-1000.0 - z.amount), 2), delta=0.02)
        # a loan repayment left out: the company is worth less from that day on, the first value adjustment after it follows
        t0 = next(p for p in res.proposals if p.kind == "tilgung")
        _, _, lo = self.plan(hold={t0.key})
        v = {p.key: p.amount for p in lo.proposals if p.kind == "wert"}
        self.assertAlmostEqual(v[w[0].key], w[0].amount - 0.49 * t0.amount, delta=0.02)
        for p in w[1:]:
            self.assertAlmostEqual(v[p.key], p.amount, delta=0.02)
        self.assertNotIn(t0.key, {p.key for p in lo.proposals})

    def test_deleted_or_changed_is_corrected_on_its_day(self):
        led, cfg, res = self.plan()
        real = led.without_planned(keep=[p.key for p in res.proposals])        # all written: in MoneyMoney now
        self.assertEqual([p for p in plan_all(real.fork(), cfg, self.today).proposals if p.kind == "wert"], [])
        w = [p for p in res.proposals if p.kind == "wert"]
        tx = next(t for t in real.txs if w[2].tag in (t.purpose or "") and t.account_uuid == w[2].account_uuid)
        # deleted in MoneyMoney: every month end is checked again -- one booking on its day (its mark is free again), nothing
        # after it; older than the last check, so it waits for you
        gone = _replace_tx(real, tx)
        again = [p for p in plan_all(gone.fork(), cfg, self.today, seen=Seen(Seen.top_id(real), self.today)).proposals if p.kind == "wert"]
        self.assertEqual([(p.key, p.booking_date, round(p.amount, 2), p.retro) for p in again], [(w[2].key, w[2].booking_date, round(w[2].amount, 2), True)])
        # you booked the value yourself instead: nothing to do
        own = _replace_tx(real, tx)
        own.post(tx.account_uuid, tx.booking_date, tx.amount, "Ich", "Wert selbst gebucht").planned = False
        self.assertEqual([p for p in plan_all(own, cfg, self.today).proposals if p.kind == "wert"], [])
        # amount changed in MoneyMoney: the difference back on that day, with the next free mark
        ch = _replace_tx(real, tx, round(tx.amount + 50, 2))
        fix = [p for p in plan_all(ch, cfg, self.today).proposals if p.kind == "wert"]
        self.assertEqual([(p.booking_date, round(p.amount, 2), p.tag) for p in fix], [(w[2].booking_date, -50.0, w[2].tag[:-1] + "2")])


class MirrorTests(unittest.TestCase):
    """Counter accounts as a mirror: each booking into the other account with the opposite sign, both ways where both are
    offline accounts, never back; pairs booked by hand count; gone or changed originals are notes."""
    today = date(2026, 11, 4)

    def cfg(self, back="alles", quelle="shs.kap.s"):
        return company_cfg(gesellschaften=[{"bereich": "b", "rueckwirkend_ab": back, "gegenkonten": [
            {"konto": F.uid("priv.bet.shs") + " | Beteiligung an Beta GbR", "quelle": F.uid(quelle) + " | Konto"}]}])

    def test_both_ways_pairs_and_never_back(self):
        txs = [F.tx("shs.kap.s", date(2026, 9, 1), -5000.0, "Ich", "Einlage"), F.tx("priv.bet.shs", date(2026, 10, 2), 1200.0, "Beta GbR", "Entnahme"),
               F.tx("shs.kap.s", date(2026, 10, 1), 1000.0, "Ich", "Entnahme Okt"), F.tx("priv.bet.shs", date(2026, 10, 1), -1000.0, "Beta GbR", "von Hand"),
               F.tx("shs.kap.s", date(2026, 10, 20), 70.0, "Ich", "Gebühr"), F.tx("priv.bet.shs", date(2026, 10, 21), -70.0, "Beta GbR", "einen Tag später")]
        led = make_ledger({}, txs)
        res = plan_all(led, self.cfg(), self.today)
        got = sorted((p.account_uuid, p.booking_date, p.amount) for p in res.proposals)
        self.assertEqual(got, sorted([(F.uid("shs.kap.s"), date(2026, 10, 2), -1200.0), (F.uid("priv.bet.shs"), date(2026, 9, 1), 5000.0),
                                      (F.uid("priv.bet.shs"), date(2026, 10, 20), -70.0), (F.uid("shs.kap.s"), date(2026, 10, 21), 70.0)]))   # a day apart: no pair
        pv = res.preview[0]
        self.assertEqual((pv["richtung"], pv["paare"], pv["offen"]), ("beide", 1, 4))
        # written: nothing again, nothing mirrored back
        real = led.without_planned(keep=[p.key for p in res.proposals])
        again = plan_all(real.fork(), self.cfg(), self.today)
        self.assertEqual(again.proposals, []); self.assertEqual(again.warnings, []); self.assertEqual(again.preview[0]["gespiegelt"], 5)

    def test_from_a_day_and_bank_account_one_way(self):
        old = F.tx("shs.kk", date(2026, 10, 1), -300.0, "Ich", "vor dem Start")
        cfg = self.cfg(back="2026-10-15", quelle="shs.kk")        # the company's side is a bank account: only into yours
        res = plan_all(make_ledger({}, [old]), cfg, self.today)
        self.assertEqual(res.proposals, [])
        new = F.tx("shs.kk", date(2026, 10, 20), 800.0, "Ich", "ab dem Start")
        res2 = plan_all(make_ledger({}, [old, new]), cfg, self.today)
        self.assertEqual([(p.account_uuid, p.amount) for p in res2.proposals], [(F.uid("priv.bet.shs"), -800.0)])
        self.assertEqual((res2.preview[0]["richtung"], res2.preview[0]["beginn"]), ("zu_a", "2026-10-15"))
        # set up before 3.13.1 without a day: since Kontor's first mirrored booking, else what is new since the last check
        led = make_ledger({}, [old, new])
        res3 = plan_all(led, self.cfg(back="", quelle="shs.kk"), self.today, seen=Seen(old["id"], self.today))
        self.assertEqual([p.amount for p in res3.proposals], [-800.0])
        # mine is a bank account too: nothing can be mirrored
        cfg3 = company_cfg(gesellschaften=[{"bereich": "b", "gegenkonten": [{"konto": F.uid("priv.giro") + " | Giro", "quelle": F.uid("shs.kk") + " | KK"}]}])
        self.assertTrue(any("Offline-Konto" in w for w in plan_all(make_ledger({}, []), cfg3, self.today).warnings))

    def test_gone_changed_renumbered_original_and_deleted_mirror(self):
        o = F.tx("shs.kap.s", date(2026, 9, 1), -5000.0, "Ich", "Einlage")
        led = make_ledger({}, [o])
        res = plan_all(led, self.cfg(), self.today)
        p = res.proposals[0]
        mirror = F.tx("priv.bet.shs", p.booking_date, p.amount, p.payee, p.purpose)
        # the original deleted: a note to delete the mirrored booking too
        gone = plan_all(make_ledger({}, [mirror]), self.cfg(), self.today)
        self.assertEqual(gone.proposals, []); self.assertTrue(any("kein Original mehr" in w for w in gone.warnings))
        # the original entered again (a new number, same day and amount): the mirrored booking counts for it
        again_o = dict(o, id=o["id"] + 50000)
        r = plan_all(make_ledger({}, [again_o, mirror]), self.cfg(), self.today)
        self.assertEqual(r.proposals, []); self.assertEqual(r.warnings, []); self.assertEqual(r.preview[0]["gespiegelt"], 1)
        # the original changed: a note to adjust it
        changed = plan_all(make_ledger({}, [dict(o, amount=-5500.0), mirror]), self.cfg(), self.today)
        self.assertEqual(changed.proposals, []); self.assertTrue(any("passt nicht mehr" in w for w in changed.warnings))
        # the mirrored booking deleted in MoneyMoney: proposed again -- older than the last check, so only with your approval
        led2 = make_ledger({}, [o])
        again = plan_all(led2, self.cfg(), self.today, seen=Seen(Seen.top_id(led2), self.today))
        self.assertEqual([(q.key, q.retro) for q in again.proposals], [(p.key, True)])

    def test_new_account_shown_before_its_first_booking(self):
        from report import inactive_accounts
        led = make_ledger({"shs.kap.p": 0.0}, [])
        acc = led.accounts[F.uid("shs.kap.p")]
        hidden, auto = inactive_accounts(led, [acc], {}, [], {"bilanz": {"inaktiv_monate": 12}}, self.today)
        self.assertIn(acc.uuid, auto)                                   # empty and long known: hidden by activity
        hidden, auto = inactive_accounts(led, [acc], {}, [], {"bilanz": {"inaktiv_monate": 12}}, self.today, {acc.uuid: "2026-11-03"})
        self.assertNotIn(acc.uuid, auto)                                # new in MoneyMoney: shown at once


class CapitalAccountRoleTests(unittest.TestCase):
    def test_capital_account_private_participation_company_debt(self):
        """An account named "Kapitalkonto": privately a participation (also empty, also of the type "Darlehenskonto"), in a
        company its debt to the partner."""
        from report import account_roles
        raw = F.accounts_raw({})
        for a in raw:
            if a["uuid"] == F.uid("priv.bet.pb"):
                a.update(name="Kapitalkonto Alpha GbR", type="Darlehenskonto", balance=[[0.0, "EUR"]])
        led = Ledger(accounts_from_export(raw), [])
        roles = account_roles(led, company_cfg())
        self.assertEqual(roles[F.uid("priv.bet.pb")], "beteiligungen")
        self.assertEqual(roles[F.uid("pb.kap.s")], "verbindlichkeiten")
        for a in raw:                                       # also with a debit balance: yours is a participation
            if a["uuid"] == F.uid("priv.bet.pb"):
                a["balance"] = [[-500.0, "EUR"]]
        self.assertEqual(account_roles(Ledger(accounts_from_export(raw), []), company_cfg())[F.uid("priv.bet.pb")], "beteiligungen")
        # no company set up yet: a capital account with a debt stays a debt (as before)
        self.assertEqual(account_roles(Ledger(accounts_from_export(raw), []), {})[F.uid("pb.kap.s")], "verbindlichkeiten")


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

        def set_transaction(self, tx_id, category=None, comment=None, checkmark=None):
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
        there = F.tx("priv.bet.shs", date(2026, 11, 1), 5.0, "x", "da · #mm-wert-20261101-1")
        led = make_ledger({}, [there])
        off, bank = led.accounts[F.uid("priv.bet.pb")], led.accounts[F.uid("priv.giro")]
        ok = Proposal("r", "wert", off.uuid, off.path, date(2026, 11, 4), 12.5, "p", "Text · " + tag, "", tag)
        br = self.Rec()
        made = []
        self.assertEqual(core.apply_proposals(br, led, [ok], made), 1)
        self.assertEqual(br.calls, [("add", off.uuid, date(2026, 11, 4), "p", 12.5, "Text · " + tag, None)]); self.assertEqual(made, [ok])
        for bad in (Proposal("r", "wert", bank.uuid, bank.path, date(2026, 11, 4), 1.0, "p", "x · " + tag, "", tag),       # a bank account
                    Proposal("r", "wert", F.uid("priv"), "Privat", date(2026, 11, 4), 1.0, "p", "x · " + tag, "", tag),      # a group
                    Proposal("r", "wert", off.uuid, off.path, date(2026, 11, 4), 1.0, "p", "ohne Markierung", "", tag),      # no mark in its text
                    Proposal("r", "wert", off.uuid, off.path, date(2026, 11, 4), 1.0, "p", "x", "", ""),
                    Proposal("r", "wert", off.uuid, off.path, date(2026, 11, 4), float("nan"), "p", "x · " + tag, "", tag)):
            br = self.Rec()
            with self.assertRaises(MoneyMoneyError):
                core.apply_proposals(br, led, [bad], [])
            self.assertEqual(br.calls, [])
        # its mark is in the account already, or no amount: nothing is written (never twice)
        twice = Proposal("r", "wert", F.uid("priv.bet.shs"), "x", date(2026, 11, 1), 5.0, "p", "da · #kontor-wert-20261101-1", "", "#kontor-wert-20261101-1")       # there with its older "#mm-" mark
        zero = Proposal("r", "wert", off.uuid, off.path, date(2026, 11, 4), 0.0, "p", "x · " + tag, "", tag)
        br = self.Rec(); made = []
        core.apply_proposals(br, led, [twice, zero, ok, ok], made)
        self.assertEqual(len(br.calls), 1); self.assertEqual(made, [ok])
        # a category only if MoneyMoney has it -- otherwise without one (its category tree is never touched), and a note
        cats = [{"name": "Zinsen", "path": "Finanzen\\Zinsen", "uuid": "u-1"}]
        a = Proposal("r", "zins", off.uuid, off.path, date(2026, 11, 4), -3.0, "p", "x · #kontor-zins-2026-10", "Zinsen", "#kontor-zins-2026-10")
        b = Proposal("r", "zins", off.uuid, off.path, date(2026, 11, 4), -3.0, "p", "x · #kontor-zins-2026-09", "Gibtsnicht", "#kontor-zins-2026-09")
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
    """Kontor's mark reads "#kontor-..." (so MoneyMoney shows who made a booking); bookings made until 3.12 carry "#mm-..." and
    are the same marks: nothing is booked twice, Kontor's lists keep working."""

    def test_old_marks_are_the_same_marks(self):
        from model import canon_tag, marks_in, has_mark
        self.assertEqual(canon_tag("#mm-zins-2026-01"), "#kontor-zins-2026-01"); self.assertEqual(canon_tag("#kontor-gk-12"), "#kontor-gk-12")
        self.assertEqual(marks_in("Zinsen · #mm-zins-2026-01 und #kontor-wert-20260101-2"), ["#kontor-zins-2026-01", "#kontor-wert-20260101-2"])
        self.assertTrue(has_mark("x #mm-tx-5")); self.assertFalse(has_mark("#mmm kein Zeichen"))
        today = date(2026, 11, 4)
        # everything booked by an older version (old marks): nothing is proposed again
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        cfg = company_cfg(darlehen=[loan_cfg()])
        res = plan_all(led, cfg, today)
        self.assertTrue(res.proposals); self.assertTrue(all(p.tag.startswith("#kontor-") and p.tag in p.purpose for p in res.proposals))
        old = led.without_planned(keep=[p.key for p in res.proposals])
        for t in old.txs:
            t.purpose = t.purpose.replace("#kontor-", "#mm-")
        self.assertEqual(plan_all(old.fork(), cfg, today).proposals, [])
        # a mirrored booking with the old mark: recognised, not mirrored again and not mirrored back
        o = F.tx("shs.kap.s", date(2026, 9, 1), -5000.0, "Ich", "Einlage")
        m = F.tx("priv.bet.shs", date(2026, 9, 1), 5000.0, "Beta GbR", "Einlage · #mm-gk-%d" % o["id"])
        mc = company_cfg(gesellschaften=[{"bereich": "b", "rueckwirkend_ab": "alles", "gegenkonten": [
            {"konto": F.uid("priv.bet.shs") + " | B", "quelle": F.uid("shs.kap.s") + " | K"}]}])
        r = plan_all(make_ledger({}, [o, m]), mc, today)
        self.assertEqual(r.proposals, []); self.assertEqual(r.warnings, []); self.assertEqual(r.preview[0]["gespiegelt"], 1)
        # a decision not to book from before (key with "#mm-"): still the same booking
        import rules
        self.assertEqual(rules.bkey("a", "#mm-zins-2026-01"), rules.bkey("a", "#kontor-zins-2026-01"))
        z = next(p for p in res.proposals if p.kind == "zins")
        again = plan_all(make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today)), dict(cfg, nicht_buchen=[{"key": z.account_uuid + "|" + z.tag.replace("#kontor-", "#mm-")}]), today)
        self.assertNotIn(z.tag, [p.tag for p in again.proposals])


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
