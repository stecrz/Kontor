import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mm_model import Ledger, accounts_from_export, tx_from_export, fmt_eur  # noqa: E402
from mm_rules import plan_loan, plan_mirror, plan_all  # noqa: E402
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
        self.assertTrue(any("heisst jetzt" in h for h in led.hints))
        # UUID weg, Name vorhanden: Rueckfall + Hinweis mit neuer UUID
        led2 = make_ledger({}, [])
        acc = led2.resolve("00000000-0000-0000-0000-000000000000 | Verkäuferdarlehen")
        self.assertEqual(acc.uuid, F.uid("pb.vd"))
        self.assertTrue(any("Neue UUID" in h for h in led2.hints))
        with self.assertRaises(KeyError):
            led2.resolve("00000000-0000-0000-0000-000000000000 | Gibt es nicht")
        # Offline-Erkennung: Extension-Konto ohne BLZ, aber aktualisiert -> nicht manuell
        from mm_model import Account
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
        quelle = [p for p in res.proposals if p.kind == "quelle"]
        self.assertEqual(len(tilg), 11)                      # Jan..Nov
        self.assertEqual(len(zins), 10)                      # Jan..Okt (Nov-Ultimo liegt in der Zukunft)
        self.assertEqual(len(quelle), 11)
        self.assertTrue(all(p.amount == 8250.0 for p in tilg))
        self.assertTrue(all(p.amount == -4400.0 for p in zins))   # 1.600.000 x 3,3 % / 12
        self.assertEqual(zins[0].booking_date, date(2026, 1, 31))
        self.assertIn("#mm-zins-2026-01", zins[0].purpose)
        self.assertIn("#mm-tx-", tilg[0].purpose)
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
        self.assertEqual([p for p in res2.proposals if p.kind != "quelle"], [])

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
        # Manuelle Zinsbuchung im gleichen Monat -> Warnung statt Doppelbuchung
        txs2 = F.pb_transactions(today, with_manual_interest_until=date(2026, 10, 1))
        led2 = make_ledger({"pb.vd": -1600000.0}, txs2)
        res2 = plan_loan(led2, loan_cfg(ab_datum="2026-01-01"), today)
        self.assertEqual(len([p for p in res2.proposals if p.kind == "zins"]), 0)
        self.assertEqual(len([w for w in res2.warnings if "manuelle Zinsbuchung" in w]), 10)

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
        self.assertTrue(any("seit ueber 35 Tagen" in w for w in res.warnings))
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


class MirrorTests(unittest.TestCase):
    def test_participation_value(self):
        today = date(2026, 11, 4)
        led = make_ledger({}, [])
        cfg = {"name": "Alpha", "beteiligungskonto": "Beteiligung an Alpha GbR", "gruppe": "Alpha GbR", "anteil": 0.49}
        res = plan_mirror(led, cfg, today)
        pb_value = 40000 + 1900000 - 1600000 - 120000 - 120000      # = 100.000
        want = round(0.49 * pb_value, 2)
        self.assertEqual(len(res.proposals), 1)
        self.assertAlmostEqual(res.proposals[0].amount, want - (-90000.0), 2)
        self.assertEqual(led.resolve("Beteiligung an Alpha GbR").balance, want)
        # erneut: nichts
        self.assertEqual(plan_mirror(led, cfg, today).proposals, [])

    def test_loans_before_participation_in_plan_all(self):
        today = date(2026, 11, 4)
        led = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        config = {"darlehen": [loan_cfg()],
                  "beteiligungen": [{"name": "Alpha", "beteiligungskonto": "Beteiligung an Alpha GbR", "gruppe": "Alpha GbR", "anteil": 0.49}]}
        res = plan_all(led, config, today)
        wert = [p for p in res.proposals if p.kind == "wert"]
        self.assertEqual(len(wert), 1)
        pb_value = 40000 + 1900000 + (-1600000 + 11 * 8250 - 10 * 4400) - 240000
        self.assertAlmostEqual(wert[0].amount, round(0.49 * pb_value, 2) + 90000.0, 2)

    def test_circular_reference_rejected(self):
        led = make_ledger({}, [])
        cfg = {"name": "x", "beteiligungskonto": "Immobilie Parkweg", "gruppe": "Alpha GbR", "anteil": 0.49}
        res = plan_mirror(led, cfg, date(2026, 11, 4))
        self.assertTrue(any("Zirkelbezug" in w for w in res.warnings))
        self.assertEqual(res.proposals, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
