"""Categories: MoneyMoney is the only truth; Kontor's assignments only wait to be written there, learned patterns are only
suggestions, and rules are proposed in MoneyMoney's syntax. All names and amounts are made up."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import categorize as C            # noqa: E402
from model import Account, Ledger, Tx   # noqa: E402


def ledger(rows):
    """rows: (id, name, purpose, amount, category, counter iban)"""
    acc = {"giro": Account(uuid="giro", name="Giro", type="Giro", group=False, indentation=0, balance=0.0, currency="EUR", iban="DE11")}
    d0 = date(2026, 1, 1)
    return Ledger(acc, [Tx(id=i, account_uuid="giro", booking_date=d0 + timedelta(days=i), value_date=None, amount=a, currency="EUR",
                           name=n, purpose=p, category_path=c.replace(" / ", "\\"), counter_iban=ib)
                        for i, n, p, a, c, ib in rows])


class Truth(unittest.TestCase):
    def test_moneymoney_counts_then_what_waits(self):
        L = ledger([(1, "Shop", "", -5.0, "Haushalt", ""), (2, "Shop", "", -6.0, "", ""), (3, "Shop", "", -7.0, "Unkategorisiert", ""),
                    (4, "Shop", "", -9.0, "Haushalt", "")])
        C.set_standard([{"name": "Unkategorisiert", "path": "Unkategorisiert", "default": True}, {"name": "Haushalt", "path": "Haushalt"}])
        try:
            d = C.empty()
            C.set_waiting(d, [2, 4], "Garten")
            got = {t.id: C.effective(d, t) for t in L.txs}
            self.assertEqual(got[1], ("Haushalt", "moneymoney"))
            self.assertEqual(got[2], ("Garten", "waiting"))
            self.assertEqual(got[3], ("", ""))                          # MoneyMoney's default category counts as none
            self.assertEqual(got[4], ("Haushalt", "moneymoney"))        # what waits never beats MoneyMoney
            self.assertEqual([g["ids"] for g in C.open_items(d, L, {})["groups"]], [[3]])
            C.set_waiting(d, [2], "")
            self.assertEqual(list(d["assignment"]), ["4"])
        finally:
            C.STANDARD = set()

    def test_only_bank_accounts_and_never_kontors_own_bookings(self):
        L = ledger([(1, "Bank", "Zinsen · #kontor-zins-2026-01", -50.0, "", ""), (2, "Shop", "", -6.0, "", "")])
        self.assertEqual([g["ids"] for g in C.open_items(C.empty(), L, {})["groups"]], [[2]])
        self.assertEqual(C.open_items(C.empty(), L, {}, banks={"elsewhere"})["open"], 0)
        self.assertEqual(C.stats(C.empty(), L, banks={"giro"})["total"], {"without": 1})

    def test_old_file_starts_empty(self):
        class Store:
            def load(self, name, default):
                return {"baum": [{"path": "X"}], "assignment": {"1": {"k": "X", "q": "manual"}}, "rules": [{"source": "manual"}],
                        "verwendung": {"Wohnen / Miete": "zusammen"}}
        self.assertEqual(C.load(Store()), C.empty())

    def test_mixed_group_suggests_per_transaction(self):
        iban = "DE02100100100006820101"
        L = ledger([(1, "Verwaltung", "Miete Wohnung", -900.0, "Wohnen / Miete", iban), (2, "Verwaltung", "Miete Wohnung", -900.0, "Wohnen / Miete", iban),
                    (3, "Verwaltung", "Nebenkosten Abrechnung", -100.0, "Wohnen / Nebenkosten", iban),
                    (4, "Verwaltung", "Nebenkosten Abrechnung", -120.0, "Wohnen / Nebenkosten", iban),
                    (5, "Verwaltung", "Miete Wohnung", -900.0, "", iban), (6, "Verwaltung", "Nebenkosten Abrechnung", -90.0, "", iban)])
        d = C.empty(); C.learn(d, L)
        g = C.open_items(d, L, {})["groups"][0]
        self.assertIsNone(g["proposal"])                                   # they differ: no suggestion for the whole group
        self.assertEqual(g["proposals"], {"5": "Wohnen / Miete", "6": "Wohnen / Nebenkosten"})
        self.assertEqual({u["id"]: u["proposal"] for u in g["transactions"]}, {5: "Wohnen / Miete", 6: "Wohnen / Nebenkosten"})

    def test_group_lists_its_transactions(self):
        L = ledger([(1, "Versand", "Buch", -20.0, "", ""), (2, "Versand", "Kabel", -9.0, "", "")])
        g = C.open_items(C.empty(), L, {})["groups"][0]
        self.assertEqual([u["id"] for u in g["transactions"]], [2, 1]); self.assertEqual(g["accounts"], ["Giro"])

    def test_learned_patterns_only_suggest(self):
        L = ledger([(1, "Baumarkt", "", -5.0, "Haushalt", ""), (2, "Baumarkt", "", -6.0, "Haushalt", ""), (3, "Baumarkt", "", -7.0, "", "")])
        d = C.empty()
        C.learn(d, L)
        C.apply_to_ledger(d, L)
        self.assertEqual(L.txs[2].category_path, "")                          # not assigned by itself
        off = C.open_items(d, L, {})
        self.assertEqual([(g["name"], g["proposal"], g["ids"]) for g in off["groups"]], [("Baumarkt", "Haushalt", [3])])


class Proposals(unittest.TestCase):
    def setUp(self):
        C._TXT.clear()

    def test_counterparty_assigned_twice(self):
        L = ledger([(1, "Baumarkt Nord 4711", "Kauf", -5.0, "Haushalt", ""), (2, "Baumarkt Nord 0815", "Kauf", -6.0, "Haushalt", ""),
                    (3, "Baumarkt Nord 1234", "Kauf", -7.0, "", "")])
        written = {"1": {"new": "Haushalt"}, "2": {"new": "Haushalt"}}
        p = C.rule_proposals(C.empty(), L, written)
        self.assertEqual([(x["category"], x["phrase"], x["yours"], x["hits"], x["open"]) for x in p],
                         [("Haushalt", 'name:"Baumarkt Nord*"', 2, 3, 1)])

    def test_iban_and_purpose_words_tell_categories_apart(self):
        # the landlord: rent and service charges from the same IBAN -- the purpose tells them apart
        iban = "DE02100100100006820101"
        L = ledger([(1, "Hausverwaltung", "Miete Januar", -900.0, "Wohnen / Miete", iban),
                    (2, "Hausverwaltung", "Miete Februar", -900.0, "Wohnen / Miete", iban),
                    (3, "Hausverwaltung", "Nebenkosten Abrechnung", -120.0, "Wohnen / Nebenkosten", iban)])
        written = {"1": {"new": "Wohnen / Miete"}, "2": {"new": "Wohnen / Miete"}}
        p = C.rule_proposals(C.empty(), L, written)
        self.assertEqual([x["phrase"] for x in p], ['remote_account:"%s" AND purpose:"miete"' % iban])

    def test_direction_when_words_do_not_help(self):
        L = ledger([(1, "Freund", "Danke", -50.0, "Geschenke", ""), (2, "Freund", "Danke", -60.0, "Geschenke", ""),
                    (3, "Freund", "Danke", 40.0, "Erstattung", "")])
        p = C.rule_proposals(C.empty(), L, {"1": {"new": "Geschenke"}, "2": {"new": "Geschenke"}})
        self.assertEqual([x["phrase"] for x in p], ['name:"Freund" AND amount<0'])

    def test_whole_words_like_moneymoney(self):
        # name:"Bar" does not catch "Sportbar" in MoneyMoney (only "Bar*" would) -- so it is no clash
        L = ledger([(1, "Bar", "", -5.0, "Essen", ""), (2, "Bar", "", -6.0, "Essen", ""), (3, "Sportbar", "", -7.0, "Freizeit", ""), (4, "Bar", "", -4.0, "", "")])
        p = C.rule_proposals(C.empty(), L, {"1": {"new": "Essen"}, "2": {"new": "Essen"}})
        self.assertEqual([(x["phrase"], x["hits"]) for x in p], [('name:"Bar"', 3)])

    def test_nothing_that_would_hit_another_category(self):
        L = ledger([(1, "Freund", "Danke", -50.0, "Geschenke", ""), (2, "Freund", "Danke", -60.0, "Geschenke", ""),
                    (3, "Freund", "Danke", -40.0, "Essen", "")])
        self.assertEqual(C.rule_proposals(C.empty(), L, {"1": {"new": "Geschenke"}, "2": {"new": "Geschenke"}}), [])

    def test_once_is_not_enough_and_done_or_existing_rules_hide_it(self):
        L = ledger([(1, "Kiosk", "", -2.0, "Essen", ""), (2, "Kiosk", "", -3.0, "Essen", ""), (3, "Kiosk", "", -4.0, "Essen", "")])
        self.assertEqual(C.rule_proposals(C.empty(), L, {"1": {"new": "Essen"}}), [])
        # assigned twice in Kontor, but the newest one MoneyMoney categorized by itself: the rule exists there already
        self.assertEqual(C.rule_proposals(C.empty(), L, {"1": {"new": "Essen"}, "2": {"new": "Essen"}}), [])
        L2 = ledger([(1, "Kiosk", "", -2.0, "Essen", ""), (2, "Kiosk", "", -3.0, "Essen", ""), (3, "Kiosk", "", -4.0, "", "")])
        p = C.rule_proposals(C.empty(), L2, {"1": {"new": "Essen"}, "2": {"new": "Essen"}})
        self.assertEqual(len(p), 1)
        d = C.empty(); d["rule_done"] = [p[0]["key"]]
        self.assertEqual(C.rule_proposals(d, L2, {"1": {"new": "Essen"}, "2": {"new": "Essen"}}), [])
        self.assertEqual(C.rule_proposals(C.empty(), L2, {"1": {"new": "Essen"}, "2": {"new": "Essen"}}, assignable={"Wohnen"}), [])


if __name__ == "__main__":
    unittest.main()


class SlashInNames(unittest.TestCase):
    """A slash within a category's name ('Strom/Gas') is part of the name, not another level; what was stored under its old
    key follows once (made-up categories)."""

    def test_keys(self):
        from model import norm_cat, legacy_cat
        self.assertEqual(norm_cat("Wohnen\\Strom/Gas"), "Wohnen / Strom/Gas")
        self.assertEqual(norm_cat("Wohnen › Strom/Gas"), "Wohnen / Strom/Gas")         # as the page shows it
        self.assertEqual(norm_cat("Wohnen / Miete"), "Wohnen / Miete")
        self.assertEqual(legacy_cat("Wohnen / Strom/Gas"), "Wohnen / Strom / Gas")

    def test_names_still_recognised(self):
        """Recognising a category by its words reads a slash as before too: transfer and position proposals stay the same."""
        import report
        check = report.transfer_check({"cashflow": {"transfer_categories": ["Umbuchung"]}})
        for p in ("Eigene Konten/Umbuchung", "Umbuchung/Sparen", "Finanzen\\Umbuchung"):
            self.assertTrue(check(p), p)
        self.assertFalse(check("Wohnen\\Strom/Gas"))
        self.assertEqual(report.recognised_position("Steuern / Erstattung/Nachzahlung", False), report.recognised_position("Steuern / Erstattung / Nachzahlung", False))

    def test_tax_setting_as_shown(self):
        import tax
        m = {"Versicherung › Haftpflicht": "Sonderausgaben"}
        self.assertEqual(tax._position_for("Versicherung / Haftpflicht", m), "Sonderausgaben")
