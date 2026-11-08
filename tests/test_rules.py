import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from model import Ledger, accounts_from_export, tx_from_export, fmt_eur  # noqa: E402
from rules import plan_loan, plan_mirror, plan_all  # noqa: E402
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
        # Kapitalkonten = Schuld der GbR an die Gesellschafter: der Wert der Beteiligung ist der Anteil am Rest
        pb_value = 40000 + 1900000 + (-1600000 + 11 * 8250 - 10 * 4400) - 240000
        self.assertAlmostEqual(wert[0].amount, round(0.49 * pb_value, 2) + 90000.0, 2)
        # Wer die Kapitalkonten als Eigenkapital fuehrt (Position "Kapitalkonten (Eigenkapital)"), zaehlt sie nicht zum Wert
        led2 = make_ledger({"pb.vd": -1600000.0}, F.pb_transactions(today))
        config["bilanz"] = {"rollen": {F.uid("pb.kap.s") + " | Kapitalkonto A": "eigenkapital", F.uid("pb.kap.p") + " | Kapitalkonto B": "eigenkapital"}}
        wert2 = [p for p in plan_all(led2, config, today).proposals if p.kind == "wert"]
        self.assertAlmostEqual(wert2[0].amount, round(0.49 * (pb_value + 240000), 2) + 90000.0, 2)

    def test_circular_reference_rejected(self):
        led = make_ledger({}, [])
        cfg = {"name": "x", "beteiligungskonto": "Immobilie Parkweg", "gruppe": "Alpha GbR", "anteil": 0.49}
        res = plan_mirror(led, cfg, date(2026, 11, 4))
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
            self.assertEqual(i18n.tr("sync_ohne_abruf", 3), "Without bank retrieval (3)")
        finally:
            i18n.set_lang("de")
        self.assertEqual(i18n.tr("sync_ohne_abruf", 3), "Ohne Bankabruf (3)")
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

    def test_unnamed_leaves_out_named_own_and_done(self):
        from security_names import unnamed
        hist = {"u1": [{"name": "", "isin": "IE00B4L5Y983"}, {"name": "Beispiel", "isin": "US0378331005"}]}
        snaps = {"2026-09": {"u1": {"DE0007164600": 1.0, "n:Fonds": 2.0, "US0378331005": 3.0}}}
        self.assertEqual(unnamed(hist, snaps, {}, {}), ["DE0007164600", "IE00B4L5Y983"])
        self.assertEqual(unnamed(hist, snaps, {"DE0007164600": "Aus dem Export"}, {}), ["IE00B4L5Y983"])
        self.assertEqual(unnamed(hist, snaps, {}, {"IE00B4L5Y983": "Mein Name"}, ["DE0007164600"]), [])

    def test_shown_name_keeps_moneymoneys_name_and_isin(self):
        from datetime import date as D
        from model import Account
        from report import depot_holdings
        acc = Account("u1", "Depot", "portfolio", False, 0, 0.0, "EUR", portfolio=True)
        state = {"historie_mm_wp": {"u1": [{"name": "", "isin": "IE00B4L5Y983", "werte": {"2026-09": 100.0}},
                                           {"name": "Beispiel", "isin": "US0378331005", "werte": {"2026-09": 50.0}},
                                           {"name": "", "isin": "DE0007164600", "werte": {"2026-09": 25.0}}]},
                 "wp_suche": {"namen": {"IE00B4L5Y983": "ISHARES CORE MSCI WORLD", "US0378331005": "NICHT GENUTZT"}}}
        cfg = {"bilanz": {"wp_namen": {"US0378331005": "Mein Name"}}}
        rows = {r["isin"]: r for r in depot_holdings(acc, {"2026-09": 175.0}, ["2026-09"], D(2026, 11, 8), state, None, cfg)}
        a, b, c = rows["IE00B4L5Y983"], rows["US0378331005"], rows["DE0007164600"]
        self.assertEqual((a["name"], a["orig"], a["quelle"]), ("ISHARES CORE MSCI WORLD", "", "suche"))     # looked up: only without a name
        self.assertEqual((b["name"], b["orig"], b["auto"], b["quelle"]), ("Mein Name", "Beispiel", "Beispiel", "eigen"))
        self.assertEqual((c["name"], c["orig"], c["quelle"]), ("DE0007164600", "", ""))                      # nothing known: the ISIN
