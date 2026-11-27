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


class Progress(unittest.TestCase):
    """How much is surely placed and how much the cash flow estimates -- under the page's filters, on the cent."""

    def test_counts_and_sums_on_the_cent(self):
        L = ledger([(1, "Shop", "", -100.10, "Haushalt", ""), (2, "Shop", "", -50.05, "", ""), (3, "Kiosk", "", -30.10, "", ""),
                    (4, "Kunde", "", 20.20, "", ""), (5, "Bank", "Zinsen · #kontor-zins-2026-01", -9.99, "", ""),
                    (6, "Ich", "", -500.0, "", "DE22")])         # to another account of the area: a transfer, no category needed
        L.accounts["tag"] = Account(uuid="tag", name="Tagesgeld", type="Giro", group=False, indentation=0, balance=0.0, currency="EUR", iban="DE22")
        d = C.empty(); C.set_waiting(d, [2], "Haushalt")
        off = C.open_items(d, L, {"giro": "a", "tag": "a"})
        self.assertEqual((off["assigned"], off["open"]), (2, 2))
        self.assertEqual((off["assigned_sum"], off["open_sum"]), (150.15, 50.30))
        groups = sum(g["count"] for g in off["groups"])
        self.assertEqual(groups, off["open"])                             # the list and the progress count the same

    def test_filters_apply_to_both_sides(self):
        L = ledger([(1, "Shop", "", -100.0, "Haushalt", ""), (2, "Shop", "", -5.0, "", ""), (3, "Shop", "", -40.0, "", "")])
        off = C.open_items(C.empty(), L, {}, min_betrag=10)
        self.assertEqual((off["assigned"], off["open"], off["assigned_sum"], off["open_sum"]), (1, 1, 100.0, 40.0))
        off = C.open_items(C.empty(), L, {}, period=(date(2026, 1, 3), None))   # booked on the 2nd, 3rd, 4th: the first left out
        self.assertEqual((off["assigned"], off["open"]), (0, 2))
        off = C.open_items(C.empty(), L, {}, period=(None, date(2026, 1, 3)))   # up to the 3rd, the day included: the last left out
        self.assertEqual((off["assigned"], off["open"], off["assigned_sum"], off["open_sum"]), (1, 1, 100.0, 5.0))
        off = C.open_items(C.empty(), L, {}, period=(date(2026, 1, 3), date(2026, 1, 3)))      # one day: from and to included
        self.assertEqual((off["assigned"], off["open"], [g["ids"] for g in off["groups"]]), (0, 1, [[2]]))
        self.assertEqual(C.open_items(C.empty(), L, {}, period=(None, None))["open"], 2)       # open on both sides: all
        st = C.stats(C.empty(), L, period=(date(2026, 1, 3), None))["total"]
        self.assertEqual((st.get("moneymoney", 0), st.get("without", 0)), (0, 2))               # the count follows the same period
        self.assertEqual(C.stats(C.empty(), L, period=(None, date(2026, 1, 2)))["total"], {"moneymoney": 1})
        off = C.open_items(C.empty(), L, {}, jahr=2025)
        self.assertEqual((off["assigned"], off["open"], off["assigned_sum"], off["open_sum"]), (0, 0, 0, 0))

    def test_another_currency_counts_but_adds_no_amount(self):
        L = ledger([(1, "Shop", "", -100.0, "", "")])
        L.accounts["usd"] = Account(uuid="usd", name="USD", type="Giro", group=False, indentation=0, balance=0.0, currency="USD", iban="US11")
        L.txs.append(Tx(id=2, account_uuid="usd", booking_date=date(2026, 2, 1), value_date=None, amount=-70.0, currency="USD", name="Shop",
                        purpose="", category_path="Haushalt", counter_iban=""))
        off = C.open_items(C.empty(), L, {})
        self.assertEqual((off["assigned"], off["open"], off["assigned_sum"], off["open_sum"]), (1, 1, 0, 100.0))


def world(rows, accounts=("giro",)):
    """rows: (id, account, day, name, purpose, amount, category, counter iban) -- accounts made up, all in euros."""
    acc = {u: Account(uuid=u, name=u.capitalize(), type="Giro", group=False, indentation=0, balance=0.0, currency="EUR", iban="DE%02d" % i)
           for i, u in enumerate(accounts)}
    d0 = date(2026, 1, 1)
    return Ledger(acc, [Tx(id=i, account_uuid=a, booking_date=d0 + timedelta(days=day), value_date=None, amount=am, currency="EUR", name=n, purpose=p,
                           category_path=c.replace(" / ", "\\"), counter_iban=ib) for i, a, day, n, p, am, c, ib in rows])


def suggestions(L, area_of=None, **kw):
    """id -> (category, level, kinds of reasons) of every open transaction."""
    area_of = area_of if area_of is not None else {u: "1" for u in L.accounts}
    h = C.Hints(C.empty(), L, area_of, kw.pop("counter", None), kw.pop("assignable", None), kw.pop("transfer", None), kw.pop("is_transfer", None))
    off = C.open_items(C.empty(), L, area_of, hints=h, meaning=kw.pop("meaning", None))
    return {u["id"]: (u["proposal"], u["level"], [w["k"] for w in u["why"]]) for g in off["groups"] for u in g["transactions"]}, off


class Suggestions(unittest.TestCase):
    """Every open transaction gets Kontor's likeliest category and how sure it is: (k + 1) / (n + 2) for k of n comparable
    earlier cases -- from 80 % sure, from 60 % probable, below unsure (made-up names and amounts)."""

    def test_chance_and_levels(self):
        self.assertEqual((C.chance(1, 1), C.chance(3, 3), C.chance(9, 10), C.chance(0, 0)), (2 / 3, 0.8, 10 / 12, 0.5))
        self.assertEqual([C.level_of(p) for p in (0.8, 0.7999, 0.6, 0.5999)], ["high", "medium", "medium", "low"])

    def test_the_counterpartys_past_decides_how_sure(self):
        rows = [(1, "giro", 1, "Bäckerei Korn", "Brot", -4.5, "Lebensmittel", ""), (2, "giro", 2, "Bäckerei Korn", "Brot", -3.2, "Lebensmittel", ""),
                (3, "giro", 3, "Bäckerei Korn", "Brot", -5.1, "Lebensmittel", ""), (4, "giro", 9, "Bäckerei Korn", "Kuchen", -12.0, "", ""),
                (5, "giro", 1, "Kiosk Eck", "Zeitung", -2.0, "Freizeit", ""), (6, "giro", 9, "Kiosk Eck", "Zeitung", -2.5, "", ""),
                (7, "giro", 1, "Laden Mitte", "Einkauf", -9.0, "Haushalt", ""), (8, "giro", 2, "Laden Mitte", "Einkauf", -8.0, "Freizeit", ""),
                (9, "giro", 9, "Laden Mitte", "Einkauf", -7.0, "", "")]
        got, off = suggestions(world(rows))
        self.assertEqual(got[4], ("Lebensmittel", "high", ["party"]))           # 3 of 3: 80 %
        self.assertEqual(got[6], ("Freizeit", "medium", ["party"]))             # 1 of 1: 67 %
        self.assertEqual(got[9][1], "low")                                      # 1 of 2: 50 %
        self.assertEqual(sum(off["levels"].values()), off["groups_total"])

    def test_by_amount_or_by_a_word_where_its_categories_part(self):
        iban = "DE02100100100006820101"
        rows = [(1, "giro", 1, "Verwaltung", "Miete Wohnung", -900.0, "Wohnen / Miete", iban), (2, "giro", 2, "Verwaltung", "Miete Wohnung", -900.0, "Wohnen / Miete", iban),
                (3, "giro", 3, "Verwaltung", "Nebenkosten Abrechnung", -100.0, "Wohnen / Nebenkosten", iban),
                (4, "giro", 4, "Verwaltung", "Nebenkosten Abrechnung", -120.0, "Wohnen / Nebenkosten", iban),
                (5, "giro", 9, "Verwaltung", "Zahlung", -900.0, "", iban), (6, "giro", 9, "Verwaltung", "Zahlung", -95.0, "", iban),
                (7, "giro", 9, "Verwaltung", "Nebenkosten 2025", -700.0, "", iban), (8, "giro", 9, "Verwaltung", "Zahlung", -500.0, "", iban)]
        got, off = suggestions(world(rows))
        chance = {u["id"]: u["chance"] for u in off["groups"][0]["transactions"]}
        self.assertEqual(got[5], ("Wohnen / Miete", "high", ["party_amount"]))            # exactly this amount: 2 of 2, its past half rent
        self.assertEqual(chance[5], round((2 + 0.5) / 3, 3))
        self.assertEqual(got[6], ("Wohnen / Nebenkosten", "high", ["party_below"]))       # below the split
        self.assertEqual(got[7][:2], ("Wohnen / Nebenkosten", "high")); self.assertIn("party_word", got[7][2])     # a word; 700 € lies between the sides
        self.assertEqual(got[8], ("Wohnen / Miete", "low", ["party"]))                    # like none of them: all of its past, 2 of 4
        g = off["groups"][0]
        self.assertIsNone(g["proposal"]); self.assertEqual(g["level"], "low")                   # they differ: per transaction

    def test_what_is_like_this_one_beats_the_counterpartys_share(self):
        """Twenty rents do not make a service charge statement rent: what is like this transaction counts first, the
        counterparty's whole past only as the prior (the reviewer's cases)."""
        iban = "DE02100100100006820101"
        rent = [(i, "giro", i, "Verwaltung", "Miete", -900.0, "Wohnen / Miete", iban) for i in range(1, 21)]
        rows = rent + [(30, "giro", 30, "Verwaltung", "Nebenkostenabrechnung", -150.0, "Wohnen / Nebenkosten", iban),
                       (31, "giro", 31, "Verwaltung", "Nebenkostenabrechnung", -300.0, "Wohnen / Nebenkosten", iban),
                       (40, "giro", 40, "Verwaltung", "Nebenkostenabrechnung", -220.0, "", iban)]
        got, _ = suggestions(world(rows))
        self.assertEqual(got[40][:2], ("Wohnen / Nebenkosten", "medium"))
        rows = rent[:9] + [(30, "giro", 30, "Verwaltung", "Nebenkosten", -100.0, "Wohnen / Nebenkosten", iban), (40, "giro", 40, "Verwaltung", "Zahlung", -100.0, "", iban)]
        got, _ = suggestions(world(rows))
        self.assertEqual(got[40], ("Wohnen / Nebenkosten", "low", ["party_amount"]))        # one like it: no more than a guess
        many = [(i, "giro", i % 900, "Verwaltung", "Miete", -900.0, "Wohnen / Miete", iban) for i in range(1, 451)]
        many += [(1000 + i, "giro", 500 + i, "Verwaltung", "NK", -100.0 - i, "Wohnen / Nebenkosten", iban) for i in range(50)]
        got, _ = suggestions(world(many + [(2000, "giro", 950, "Verwaltung", "Zahlung", -95.0, "", iban)]))
        self.assertEqual(got[2000][:2], ("Wohnen / Nebenkosten", "high"))                   # however many rents there are

    def test_amounts_compared_only_in_one_currency(self):
        iban = "DE02100100100006820101"
        rows = [(1, "usd", 1, "Shop", "Kauf", -50.0, "Reisen", iban), (2, "usd", 2, "Shop", "Kauf", -60.0, "Reisen", iban),
                (3, "giro", 3, "Shop", "Kauf", -500.0, "Technik", iban), (4, "giro", 4, "Shop", "Kauf", -600.0, "Technik", iban),
                (5, "giro", 9, "Shop", "Kauf", -55.0, "", iban)]
        L = world(rows, ("giro", "usd"))
        L.accounts["usd"].currency = "USD"
        got, _ = suggestions(L)
        self.assertNotIn("party_below", got[5][2])              # dollars below, euros above: no split in euros

    def test_words_other_counterparties_had_count_once_each(self):
        rows = [(1, "giro", 1, "Huk Versicherung", "Beitrag", -50.0, "Versicherungen", "DE02100100100006820101"),
                (2, "giro", 2, "Allianz Versicherung", "Beitrag", -10.0, "Versicherungen", "DE02100100100006820102"),
                (3, "giro", 3, "Ergo Versicherung AG", "Beitrag", -22.0, "", "DE02100500000054540402")]
        rows += [(10 + i, "giro", 1 + i, "Markt Süd", "Danke für Ihren Einkauf", -20.0, "Lebensmittel", "") for i in range(30)]
        rows += [(50, "giro", 40, "Verein", "Danke für Ihre Spende", -20.0, "", "")]
        got, _ = suggestions(world(rows))
        self.assertEqual(got[3], ("Versicherungen", "medium", ["word", "catname"]))      # 2 of 2 counterparties × 0.9, and the name
        self.assertNotIn("word", got[50][2])                     # one shop thirty times is one counterparty: not enough
        self.assertEqual(got[50][1], "low")

    def test_a_counter_booking_suggests_the_transfer_category(self):
        rows = [(1, "giro", 5, "", "Übertrag", -500.0, "", ""), (2, "tages", 6, "", "Übertrag", 500.0, "", ""),
                (3, "giro", 5, "", "Sparen", -300.0, "", ""), (4, "tages", 6, "", "Sparen", 300.0, "Umbuchung", ""),
                (5, "giro", 5, "Shop", "Kauf", -77.0, "", ""), (6, "tages", 20, "", "Gutschrift", 77.0, "", ""),       # 15 days apart: no
                (7, "giro", 5, "Shop", "Kauf", -66.0, "", ""), (8, "tages", 6, "Shop", "Erstattung", 66.0, "Haushalt", "")]      # its category says otherwise
        is_t = lambda p: p == "Umbuchung"
        got, _ = suggestions(world(rows, ("giro", "tages")), transfer="Umbuchung", is_transfer=is_t, counter={"giro", "tages"})
        self.assertEqual(got[1], ("Umbuchung", "medium", ["counter"]))                 # the only one, a day apart: 70 %
        self.assertEqual(got[3], ("Umbuchung", "high", ["counter_cat"]))               # the other side is a transfer: 85 %
        self.assertNotEqual(got[5][0], "Umbuchung"); self.assertNotEqual(got[7][0], "Umbuchung")
        got, _ = suggestions(world(rows, ("giro", "tages")), transfer=None, is_transfer=is_t)
        self.assertNotIn("counter", got[1][2])                                          # without a transfer category: none

    def test_no_counter_booking_where_the_money_went_to_someone_else(self):
        """Only the opposite amount is not enough (the reviewer's cases): paid to someone else's IBAN, two names that differ, no
        amount, another currency, or a booking the cash flow paired already -- no transfer."""
        is_t = lambda p: p == "Umbuchung"
        rows = [(1, "giro", 5, "Möbelhaus", "Sofa", -300.0, "", "DE02100100100006820101"), (2, "tages", 7, "", "Übertrag", 300.0, "Umbuchung", ""),
                (3, "giro", 5, "Max", "Rückzahlung", -50.0, "", ""), (4, "tages", 6, "Erika", "Geld", 50.0, "", ""),
                (5, "giro", 5, "", "Null", 0.0, "", ""), (6, "tages", 5, "", "Null", 0.0, "", ""),
                (7, "giro", 5, "", "Übertrag", -120.0, "", ""), (8, "usd", 5, "", "Übertrag", 120.0, "", ""),
                (9, "giro", 5, "", "Übertrag", -77.0, "", ""), (10, "tages", 5, "", "Übertrag", 77.0, "", "")]
        L = world(rows, ("giro", "tages", "usd"))
        L.accounts["usd"].currency = "USD"
        L._paired = {"1": {10}}
        got, _ = suggestions(L, transfer="Umbuchung", is_transfer=is_t, counter={"giro", "tages", "usd"})
        for i in (1, 3, 5, 7, 9):
            self.assertNotIn("counter", got[i][2], i)
            self.assertNotIn("counter_cat", got[i][2], i)

    def test_the_other_side_an_account_of_yours(self):
        acc = world([], ("giro", "firma"))
        acc.accounts["firma"].iban = "DE02500105170137075030"
        L = Ledger(acc.accounts, [Tx(id=1, account_uuid="giro", booking_date=date(2026, 3, 1), value_date=None, amount=-1000.0, currency="EUR",
                                     name="Firma", purpose="Einlage", category_path="", counter_iban="DE02500105170137075030")])
        got, _ = suggestions(L, {"giro": "1", "firma": "2"}, transfer="Umbuchung", is_transfer=lambda p: p == "Umbuchung")
        self.assertEqual(got[1], ("Umbuchung", "medium", ["own_account"]))

    def test_a_word_of_a_categorys_name_and_else_the_most_common(self):
        rows = [(1, "giro", 1, "Markt", "Einkauf", -20.0, "Lebensmittel", ""), (2, "giro", 2, "Markt", "Einkauf", -25.0, "Lebensmittel", ""),
                (3, "giro", 3, "Arbeitgeber", "Lohn", 2000.0, "Einkommen / Gehalt", ""),
                (4, "giro", 9, "Stadtwerke Nord", "Abschlag Strom", -80.0, "", ""), (5, "giro", 9, "Max Muster", "Danke", -30.0, "", ""),
                (6, "giro", 9, "Erika Muster", "Danke", 30.0, "", "")]
        cats = {"Lebensmittel", "Einkommen / Gehalt", "Wohnen / Strom und Gas"}
        got, _ = suggestions(world(rows), assignable=cats)
        self.assertEqual(got[4], ("Wohnen / Strom und Gas", "low", ["catname"]))
        self.assertEqual(got[5], ("Lebensmittel", "low", ["common_out"]))              # a guess, and says so
        self.assertEqual(got[6], ("Einkommen / Gehalt", "low", ["common_in"]))          # by direction
        got, off = suggestions(world([(1, "giro", 1, "Max Muster", "Danke", -30.0, "", "")]))
        self.assertEqual(got[1], (None, None, [])); self.assertEqual(off["groups"][0]["level"], "low")      # nothing known at all

    def test_only_categories_that_exist_in_moneymoney(self):
        rows = [(1, "giro", 1, "Laden", "Kauf", -5.0, "Alt / Weg", ""), (2, "giro", 2, "Laden", "Kauf", -6.0, "Alt / Weg", ""),
                (3, "giro", 3, "Laden", "Kauf", -7.0, "", "")]
        got, _ = suggestions(world(rows), assignable={"Haushalt"})
        self.assertNotEqual(got[3][0], "Alt / Weg")

    def test_a_reason_for_another_category_makes_it_less_sure(self):
        rows = [(i, "giro", i, "Laden", "Kauf", -40.0 - i, "Haushalt", "") for i in range(1, 4)]
        rows += [(9, "giro", 20, "Laden", "Kauf", -55.0, "", ""), (10, "tages", 21, "", "Eingang", 55.0, "", "")]
        got, _ = suggestions(world(rows, ("giro", "tages")), transfer="Umbuchung", is_transfer=lambda p: p == "Umbuchung", counter={"giro", "tages"})
        self.assertEqual(got[9], ("Haushalt", "medium", ["party", "also"]))             # 80 % less half of 70 − 40

    def test_two_kinds_of_reasons_add_up(self):
        h = [("party", "A", 0.75, {"k": "party"}), ("word", "A", 0.675, {"k": "word"}), ("common", "A", 0.3, {"k": "common_out"})]
        got = C.combine(h)                                       # 2 of 2 and a word 2 of 2 counterparties: sure together
        self.assertAlmostEqual(got["chance"], round(0.75 + 0.5 * 0.25 * 0.675, 3))
        self.assertEqual((got["level"], [w["k"] for w in got["why"]]), ("high", ["party", "word"]))       # the most common one is no evidence
        self.assertEqual(C.combine([("common", "B", 0.9, {"k": "common_out"})])["chance"], C.GUESS)      # alone: a guess, whatever its share
        self.assertIsNone(C.combine([]))

    def test_this_area_first(self):
        rows = [(1, "privat", 1, "Tankstelle", "Benzin", -60.0, "Mobilität", ""), (2, "privat", 2, "Tankstelle", "Benzin", -50.0, "Mobilität", ""),
                (3, "firma", 3, "Tankstelle", "Benzin", -70.0, "Firma / Fahrzeuge", ""), (4, "firma", 9, "Tankstelle", "Benzin", -65.0, "", ""),
                (5, "privat", 9, "Tankstelle", "Benzin", -55.0, "", "")]
        got, _ = suggestions(world(rows, ("privat", "firma")), {"privat": "1", "firma": "2"})
        self.assertEqual((got[4][0], got[5][0]), ("Firma / Fahrzeuge", "Mobilität"))

    def test_every_reason_and_level_has_its_text(self):
        """The page shows each reason as kzw_<kind> and each level as kz_lv_<level> (with their tooltip and filter): German and English."""
        import json
        import re
        here = os.path.join(os.path.dirname(__file__), "..")
        txt = open(os.path.join(here, "web", "i18n.js"), encoding="utf-8").read()
        cat = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        src = open(os.path.join(here, "categorize.py"), encoding="utf-8").read()
        kinds = {"party", "party_amount", "party_below", "party_above", "party_word", "party_reverse", "word", "meaning", "counter",
                 "counter_cat", "own_account", "catname", "common_out", "common_in", "also"}
        self.assertLessEqual(set(re.findall(r'"k": "(\w+)"', src)) | set(re.findall(r'\(\d, "(party_\w+)"', src)), kinds)
        keys = ["kzw_" + k for k in kinds] + [p + lv for lv in C.LEVELS for p in ("kz_lv_", "kz_lv_tip_", "kz_f_", "kz_stufe_leer_")]
        for k in keys:
            self.assertEqual(len(cat.get(k) or []), 2, k)

    def test_never_assigned_by_itself(self):
        rows = [(i, "giro", i, "Bäcker", "Brot", -3.0, "Lebensmittel", "") for i in range(1, 6)] + [(9, "giro", 9, "Bäcker", "Brot", -3.0, "", "")]
        L = world(rows)
        d = C.empty()
        got, _ = suggestions(L)
        self.assertEqual(got[9][:2], ("Lebensmittel", "high"))
        C.apply_to_ledger(d, L)
        self.assertEqual((L.txs[-1].category_path, d["assignment"]), ("", {}))


class Doubts(unittest.TestCase):
    """Categories that make no sense to Kontor: leaving the transaction out, Kontor would suggest another at least 60 % likely
    and everything comparable gives the one it has under 10 % -- what Kontor gives some chance is never doubted (made up)."""

    def doubted(self, rows, d=None, accounts=("giro",), **kw):
        L = world(rows, accounts)
        if "paired" in kw:
            L._paired = kw.pop("paired")
        d = d or C.empty()
        area_of = {u: "1" for u in L.accounts}
        h = C.Hints(d, L, area_of, None, None, kw.pop("transfer", None), kw.pop("is_transfer", None))
        got = C.doubts(d, L, area_of, h)
        return {u["id"]: (g["category"], u["proposal"], u["support"]) for g in got["groups"] for u in g["transactions"]}, got

    def test_the_users_example(self):
        """Kontor would say A (about 60 %) and knows it may be B (about 30 %): B is fine, C makes no sense."""
        a = [(i, "giro", i, "Laden", "Einkauf", -11.0 * i, "Lebensmittel", "") for i in range(1, 7)]
        b = [(10 + i, "giro", 10 + i, "Laden", "Einkauf", -5.0 - 12.0 * i, "Haushalt", "") for i in range(1, 4)]
        got, _ = self.doubted(a + b[:2] + [(20, "giro", 30, "Laden", "Einkauf", -47.0, "Haushalt", "")])
        self.assertNotIn(20, got)
        got, _ = self.doubted(a + b + [(20, "giro", 30, "Laden", "Einkauf", -47.0, "Kleidung", "")])
        self.assertEqual(got[20][:2], ("Kleidung", "Lebensmittel")); self.assertLess(got[20][2], C.DOUBT_LOW)
        self.assertEqual(set(got), {20})                       # the others fit

    def test_one_odd_one_among_twenty(self):
        rows = [(i, "giro", i, "Markt Süd", "Einkauf", -20.0 - i, "Lebensmittel", "") for i in range(1, 21)]
        got, res = self.doubted(rows + [(30, "giro", 30, "Markt Süd", "Einkauf", -33.0, "Restaurant", "")])
        self.assertEqual(got, {30: ("Restaurant", "Lebensmittel", round(0.5 / 21, 3))})
        g = res["groups"][0]
        self.assertEqual((g["proposal"], g["level"], res["count"], res["groups_total"]), ("Lebensmittel", "high", 1, 1))
        self.assertEqual(g["why"][0]["a"][:2], [20, 20])        # counted without it

    def test_the_same_amount_once_says_nothing(self):
        rows = [(i, "giro", i, "Markt Süd", "Einkauf", -20.0 - i, "Lebensmittel", "") for i in range(1, 21)]
        got, _ = self.doubted(rows + [(30, "giro", 30, "Markt Süd", "Einkauf", -33.0, "Restaurant", "")])        # 33 € was Lebensmittel once
        self.assertIn(30, got)

    def test_too_little_to_say(self):
        rows = [(i, "giro", i, "Kiosk", "Zeitung", -2.0 - i, "Freizeit", "") for i in range(1, 4)]
        got, _ = self.doubted(rows + [(9, "giro", 9, "Kiosk", "Zeitung", -3.5, "Bildung", "")])
        self.assertEqual(got, {})                               # none of 3: about 12 %, not under 10 %

    def test_two_of_twentyfive_are_no_outliers(self):
        rows = [(i, "giro", i, "Markt", "Einkauf", -20.0 - i, "Lebensmittel", "") for i in range(1, 21)]
        rows += [(30 + i, "giro", 30 + i, "Markt", "Einkauf", -40.0 - i, "Restaurant", "") for i in range(3)]
        got, _ = self.doubted(rows)
        self.assertEqual(got, {})                               # two others of 22: about 11 %

    def test_by_the_words_of_other_counterparties(self):
        rows = [(i, "giro", i, "Versicherung %s" % n, "Beitrag", -10.0 * i, "Versicherungen", "")
                for i, n in enumerate(("Nord", "Süd", "West", "Ost", "Mitte", "Rhein"), start=1)]
        rows += [(20 + i, "giro", 20 + i, "Markt", "Einkauf", -5.0 - i, "Lebensmittel", "") for i in range(5)]
        got, _ = self.doubted(rows + [(40, "giro", 40, "Ergo Versicherung", "Monat", -30.0, "Lebensmittel", "")])
        self.assertEqual(got[40][:2], ("Lebensmittel", "Versicherungen"))

    def test_the_name_of_the_category_or_a_counter_booking_speaks_for_it(self):
        rows = [(i, "giro", i, "Tankhof", "Einkauf", -50.0 - i, "Lebensmittel", "") for i in range(1, 11)]
        got, _ = self.doubted(rows + [(20, "giro", 20, "Tankhof", "Benzin", -61.0, "Mobilität / Benzin", "")])
        self.assertEqual(got, {})                               # "Benzin" is in the category's name
        rows2 = rows + [(20, "giro", 20, "Tankhof", "Übertrag", -61.0, "Umbuchung", ""), (21, "tages", 21, "", "Übertrag", 61.0, "", "")]
        got, _ = self.doubted(rows2, accounts=("giro", "tages"), transfer="Umbuchung", is_transfer=lambda p: p == "Umbuchung")
        self.assertNotIn(20, got)                               # a transfer with its counter-booking

    def test_fine_as_is_until_the_category_changes(self):
        rows = [(i, "giro", i, "Markt Süd", "Einkauf", -20.0 - i, "Lebensmittel", "") for i in range(1, 21)]
        rows.append((30, "giro", 30, "Markt Süd", "Einkauf", -33.0, "Restaurant", ""))
        d = C.empty(); d["doubt_ok"] = {"30": "Restaurant"}
        self.assertEqual(self.doubted(rows, d)[0], {})
        d["doubt_ok"] = {"30": "Freizeit"}                       # said for another category than it has now
        self.assertIn(30, self.doubted(rows, d)[0])

    def test_never_a_transfer_the_cash_flow_paired(self):
        rows = [(i, "giro", i, "Bank", "Einkauf", -20.0 - i, "Lebensmittel", "") for i in range(1, 21)]
        rows.append((30, "giro", 30, "Bank", "Einkauf", -33.0, "Umbuchung", ""))
        got, _ = self.doubted(rows, paired={"1": {30}}, is_transfer=lambda p: p == "Umbuchung")
        self.assertEqual(got, {})
        got, _ = self.doubted(rows, is_transfer=lambda p: p == "Umbuchung")
        self.assertIn(30, got)                                  # unpaired: as odd as any other

    def test_as_if_it_had_no_category(self):
        """What Kontor would suggest for it without its category decides (the reviewer's cases): the only one in its area or its
        direction falls back to the rest, any word others had speaks for its category, a word of others alone needs a sure one."""
        rows = [(i, "eins", i, "Stadtwerke", "Abschlag", -50.0 - i, "Nebenkosten", "") for i in range(1, 11)]
        rows += [(20 + i, "eins", 20 + i, "Versorger %s" % n, "Abschlag Strom", -40.0 - i, "Strom", "") for i, n in enumerate("ABCDEF")]
        rows.append((40, "zwei", 40, "Stadtwerke", "Abschlag Strom", -55.0, "Nebenkosten", ""))
        L = world(rows, ("eins", "zwei"))
        h = C.Hints(C.empty(), L, {"eins": "1", "zwei": "2"})
        self.assertIsNone(C.doubt_of(h, L.txs[-1], "Nebenkosten"))            # its counterparty's past in the other area: Nebenkosten
        shop = [(i, "giro", i, "Laden Nord", "Einkauf", -20.0 - i, "Lebensmittel", "") for i in range(1, 21)]
        got, _ = self.doubted(shop + [(50, "giro", 50, "Laden Nord", "Gutschrift", 7.5, "Lebensmittel", "")])
        self.assertNotIn(50, got)                                               # the first refund: its purchases in the other direction
        market = [(i, "giro", i, "Markt %s" % n, "Einkauf", -5.0 - i, "Lebensmittel", "") for i, n in enumerate("ABCDEF", start=1)]
        market += [(10, "giro", 10, "Apotheke Süd", "Rezept", -9.0, "Gesundheit", ""), (11, "giro", 11, "Apotheke West", "Rezept", -8.0, "Gesundheit", "")]
        got, _ = self.doubted(market + [(20, "giro", 20, "Apotheke am Markt", "Rezept", -12.0, "Gesundheit", "")])
        self.assertNotIn(20, got)                                               # "Apotheke" speaks for it, whatever "Markt" says
        refunds = [(30 + i, "giro", 30 + i, nm, "Gutschrift", 100.0 + i, "Erstattungen", "") for i, nm in enumerate(("Kasse Eins", "Kasse Zwei", "Amt Drei", "Firma Vier"))]
        got, _ = self.doubted(refunds + [(40, "giro", 40, "Arbeit Fünf", "Gutschrift", 2000.0, "Gehalt", "")])
        self.assertNotIn(40, got)                                               # only a common word of others, Kontor not sure: no doubt

    def test_words_of_others_do_not_excuse_a_counterpartys_outlier(self):
        rows = []
        for n, shop in enumerate(("Bäckerei Sonnenkorn", "Metzgerei Eiche")):
            rows += [(100 * n + i, "giro", i, shop, "Einkauf", -4.0 - i, "Lebensmittel", "") for i in range(1, 9)]
            rows.append((100 * n + 50, "giro", 50, shop, "Einkauf", -6.5, "Wohnen / Miete", ""))
        got, _ = self.doubted(rows)
        self.assertEqual(sorted(got), [50, 150])                # the other's stray "Einkauf" says nothing for this one

    def test_one_suggestion_per_group(self):
        rows = [(i, "giro", i, "Hausverwaltung", "Miete", -900.0 - i, "Wohnen / Miete", "") for i in range(1, 11)]
        rows += [(20 + i, "giro", 20 + i, "Hausverwaltung", "Abrechnung", -40.0 - i, "Wohnen / Nebenkosten", "") for i in range(1, 11)]
        rows += [(40, "giro", 40, "Hausverwaltung", "Miete", -905.5, "Lebensmittel", ""), (41, "giro", 41, "Hausverwaltung", "Abrechnung", -44.5, "Lebensmittel", "")]
        _, res = self.doubted(rows)
        self.assertEqual(sorted((g["ids"], g["proposal"]) for g in res["groups"]), [([40], "Wohnen / Miete"), ([41], "Wohnen / Nebenkosten")])

    def test_changes_nothing(self):
        rows = [(i, "giro", i, "Markt", "Einkauf", -20.0 - i, "Lebensmittel", "") for i in range(1, 21)] + [(30, "giro", 30, "Markt", "Einkauf", -33.0, "Restaurant", "")]
        L = world(rows)
        d = C.empty()
        before = [(t.id, t.category_path) for t in L.txs]
        C.doubts(d, L, {"giro": "1"})
        self.assertEqual(([(t.id, t.category_path) for t in L.txs], d), (before, C.empty()))


class SuggestionsByMeaning(unittest.TestCase):
    """With the assistant's embeddings (made up here): the most alike other counterparties vote -- at most probable alone,
    never this counterparty itself, and nothing breaks without them."""

    def rows(self):
        return [(1, "giro", 1, "Streamo", "Abo", -9.99, "Freizeit / Abos", "DE02100100100006820101"),
                (2, "giro", 2, "Flimmer", "Abo", -12.99, "Freizeit / Abos", "DE02100100100006820102"),
                (3, "giro", 3, "Kinokette", "Monat", -7.99, "Freizeit / Abos", "DE02100500000054540402"),
                (4, "giro", 4, "Markt", "Einkauf", -40.0, "Lebensmittel", "DE02120300000000202051"),
                (5, "giro", 9, "Neuflix", "Monatlich", -8.99, "", "DE02300209000106531065")]

    def meaning(self, broken=False):
        vec = {1: [100, 0, 5], 2: [90, 10, 0], 3: [95, 5, 5], 4: [0, 100, 0], 5: [99, 3, 2]}

        def vectors(txs):
            if broken:
                raise OSError("unreadable")
            return {t.id: vec[t.id] for t in txs if t.id in vec}
        return C.Meaning(("model", len(vec)), vectors)

    def test_alike_counterparties_vote(self):
        got, _ = suggestions(world(self.rows()), meaning=self.meaning())
        self.assertEqual(got[5][0], "Freizeit / Abos")
        self.assertIn("meaning", got[5][2]); self.assertEqual(got[5][1], "medium")       # 3 of 3 alike × 0.8: 64 %
        got, _ = suggestions(world(self.rows()))
        self.assertNotIn("meaning", got[5][2])                                              # without them: the other hints only

    def test_counterparties_made_once_across_assignments(self):
        """A new state of your assignments makes the hints anew -- the counterparties' embeddings come from the cache."""
        vec = {1: [100, 0, 5], 2: [90, 10, 0], 3: [95, 5, 5], 4: [0, 100, 0], 5: [99, 3, 2]}
        calls, cache = [], {}
        m = C.Meaning(("model", 5), lambda txs: calls.append(sorted(t.id for t in txs)) or {t.id: vec[t.id] for t in txs if t.id in vec}, cache)
        L = world(self.rows())
        C.Hints(C.empty(), L, {"giro": "1"})._means(m)
        self.assertEqual(calls, [[1, 2, 3, 4]])
        d = C.empty(); C.set_waiting(d, [5], "Freizeit / Abos")                       # assigned: the hints anew
        C.Hints(d, L, {"giro": "1"})._means(m)
        self.assertEqual(calls[1:], [[5]])                                              # only the new one

    def test_unreadable_embeddings_leave_the_other_hints(self):
        got, _ = suggestions(world(self.rows()), meaning=self.meaning(broken=True))
        self.assertNotIn("meaning", got[5][2]); self.assertIsNotNone(got[5][0])

    def test_never_itself(self):
        rows = self.rows() + [(6, "giro", 5, "Neuflix", "Monatlich", -8.99, "Bildung", "DE02300209000106531065")]
        vec = {1: [100, 0, 5], 2: [90, 10, 0], 3: [95, 5, 5], 4: [0, 100, 0], 5: [99, 3, 2], 6: [99, 3, 2]}
        m = C.Meaning(("model", 6), lambda txs: {t.id: vec[t.id] for t in txs if t.id in vec})
        L = world(rows)
        h = C.Hints(C.empty(), L, {"giro": "1"})
        means = h._means(m)
        hint = h._meaning_hint(L.txs[4], vec[5], "1", -1, C._own(L.txs[4]), means)
        self.assertEqual((hint[1], hint[3]["a"][:2]), ("Freizeit / Abos", [3, 3]))         # its own past ("Bildung") is not alike-voted


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
