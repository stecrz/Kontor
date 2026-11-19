"""Cash flow: every booking counts once, transfers within an area leave the net worth unchanged, and every month adds up --
the rows that change the net worth to its change in the balance sheet, the cash rows to the change of the liquid accounts.
All accounts, names and amounts are made up."""
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

TODAY = date(2026, 6, 20)

# key: (name, area, role, iban, kind) -- kind: "bank" (online), "offline", "portfolio"
ACCOUNTS = {
    "giro": ("Giro", "Privat", "cash", "DE11", "bank"),
    "tg": ("Tagesgeld", "Privat", "cash", "DE12", "bank"),
    "darl": ("Darlehen Hausbau", "Privat", "liabilities", "DE13", "bank"),
    "kredit": ("Privatkredit", "Privat", "liabilities", None, "offline"),
    "ford": ("Darlehen an Freund", "Privat", "receivables", None, "offline"),
    "auto": ("Auto", "Privat", "tangibles", None, "offline"),
    "stake": ("Beteiligung an Muster GbR", "Privat", "participations", None, "offline"),
    "usd": ("Dollarkonto", "Privat", "cash", "DE14", "bank"),
    "depot": ("Depot", "Privat", "securities", "DE15", "portfolio"),
    "kk": ("Kontokorrent", "Muster GbR", "cash", "DE21", "bank"),
    "vd": ("Verkäuferdarlehen", "Muster GbR", "liabilities", None, "offline"),
    "kap": ("Kapitalkonto", "Muster GbR", "liabilities", None, "offline"),
    "kind": ("Kinderkonto", "Kinder", "cash", "DE31", "bank"),
}


def build(txs, cfg=None, currency=None):
    """A ledger with three areas (groups) and the bookings [(id, key, day, amount, dict(extra))]; balance = sum of the booked."""
    return datasets(make_ledger(txs, currency), cfg)


def make_ledger(txs, currency=None):
    currency = currency or {"usd": "USD"}
    raw = []
    for area in ("Privat", "Muster GbR", "Kinder"):
        raw.append({"uuid": "g-" + area, "name": area, "indentation": 0, "type": "Kontengruppe", "group": True, "balance": [[0, "EUR"]],
                    "currency": "EUR"})
        for k, (name, a, role, iban, kind) in ACCOUNTS.items():
            if a != area:
                continue
            bal = round(sum(e[3] for e in txs if e[1] == k and (e[4] or {}).get("booked", True)), 2)
            raw.append({"uuid": k, "name": name, "indentation": 1, "type": "Offline-Konto" if kind == "offline" else "Girokonto",
                        "group": False, "balance": [[bal, currency.get(k, "EUR")]], "currency": currency.get(k, "EUR"),
                        "iban": iban, "accountNumber": iban or "", "bankCode": "" if kind == "offline" else "10000000",
                        "portfolio": kind == "portfolio",
                        "refreshTimestamp": None if kind == "offline" else __import__("datetime").datetime(2026, 6, 1)})
    rows = []
    for i, k, day, amount, extra in txs:
        extra = dict(extra or {})
        rows.append({"id": i, "accountUuid": k, "bookingDate": __import__("datetime").datetime(day.year, day.month, day.day, 12),
                     "amount": amount, "currency": currency.get(k, "EUR"), "name": extra.pop("name", "x"), "purpose": extra.pop("purpose", ""),
                     "categoryPath": extra.pop("cat", ""), "accountNumber": extra.pop("iban", ""), "booked": extra.pop("booked", True),
                     "comment": extra.pop("comment", "")})
    return Ledger(accounts_from_export(raw), tx_from_export(rows))


def datasets(ledger, cfg=None):
    config = core.merged_config(dict({"balance": {"roles": {k: v[2] for k, v in ACCOUNTS.items()}}}, **(cfg or {})))
    roles = {k: v[2] for k, v in ACCOUNTS.items()}
    out = {}
    for b in core.bereiche_for(ledger, config):
        out[b["name"]] = report.build_dataset(ledger, config, {}, TODAY, b, roles)
    return out


def rows(ds, section=None):
    return {z["row"]: z for s in ds["cashflow"]["sections"] if section in (None, s["name"]) for z in s["rows"]}


class Reconciles(unittest.TestCase):
    """Helpers: both checks add up, month by month."""

    def assertAddsUp(self, data, allow=()):
        for name, ds in data.items():
            for mk, u in ds["cashflow"]["reconciliation"].items():
                for check, why in (("unexplained", "reasons"), ("diff_cash", "reasons_cash")):
                    reasons = {g[0] for g in u[why]}
                    self.assertTrue(abs(u[check]) < 0.005 or (reasons and reasons <= set(allow)),
                                    "%s %s %s=%s %s" % (name, mk, check, u[check], u[why]))
                    self.assertAlmostEqual(sum(g[1] for g in u[why]), u[check] if u[why] else 0.0, 2)


class CashflowCases(Reconciles):
    def test_month_end_transfer_between_bank_accounts(self):
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 1, 31), -500.0, {"iban": "DE12", "cat": "Umbuchung"}),
                      (3, "tg", date(2026, 2, 2), 500.0, {"iban": "DE11"}),
                      (4, "giro", date(2026, 3, 1), -50.0, {"cat": "Lebensmittel"})])
        p = data["Privat"]
        self.assertAddsUp(data)
        self.assertNotIn("Umbuchung ohne erkannten Partner", rows(p))
        transit = next(r for r in p["balance"]["rows"] if r["id"] == "transit")
        self.assertEqual(transit["amounts"]["2026-01"], 500.0)
        self.assertEqual(transit["amounts"]["2026-02"], 0.0)

    def test_loan_payment_over_month_end_names_the_reason(self):
        data = build([(1, "giro", date(2025, 12, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 1, 31), -1500.0, {"iban": "DE13", "cat": "Umbuchung"}),
                      (3, "darl", date(2026, 2, 1), 1500.0, {"iban": "DE11", "cat": "Umbuchung"}),
                      (4, "darl", date(2026, 2, 1), -400.0, {"purpose": "Zinsen"}),
                      (5, "giro", date(2026, 3, 1), -50.0, {"cat": "Lebensmittel"})])
        p = data["Privat"]
        self.assertAddsUp(data, allow=("ue_unterwegs",))
        r = rows(p, "financing")
        self.assertEqual(r["Darlehen Hausbau / Tilgung"]["amounts"]["2026-01"], -1500.0)
        self.assertFalse(r["Darlehen Hausbau / Tilgung"]["nw"])
        self.assertEqual(r["Darlehen Hausbau / Zinsen"]["amounts"]["2026-02"], -400.0)
        ue = p["cashflow"]["reconciliation"]
        self.assertEqual(ue["2026-01"]["reasons_cash"], [["ue_unterwegs", 1500.0, ""]])
        self.assertEqual(ue["2026-02"]["reasons_cash"], [["ue_unterwegs", -1500.0, ""]])
        # a click on the difference: the side of the transfer booked in that month
        self.assertEqual(p["cashflow"]["cf_ids"]["\u001fcheck_cash"], {"2026-01": [2], "2026-02": [3]})
        self.assertEqual([ue[m]["n_liq"] for m in ("2026-01", "2026-02", "2026-03")], [1, 1, 0])

    def test_kontor_repayment_is_matched_to_the_payment(self):
        # the payment goes to the seller (no own IBAN); Kontor books the repayment and the interest in the offline loan
        data = build([(1, "kk", date(2026, 1, 3), 9500.0, {"cat": "Miete"}),
                      (2, "kk", date(2026, 2, 1), -6000.0, {"iban": "DE99", "cat": "Umbuchung"}),
                      (3, "vd", date(2026, 2, 1), 6000.0, {"purpose": "Annuität · #kontor-tx-2", "cat": "Umbuchung"}),
                      (4, "vd", date(2026, 2, 28), -3000.0, {"purpose": "Zinsen 02/2026 · #kontor-zins-2026-02", "cat": "Zinsen"})])
        g = data["Muster GbR"]
        self.assertAddsUp(data)
        r = rows(g)
        self.assertNotIn("unclear", [s["name"] for s in g["cashflow"]["sections"] if s["rows"]])
        self.assertEqual(r["Verkäuferdarlehen / Tilgung"]["amounts"]["2026-02"], -3000.0)
        self.assertEqual(r["Verkäuferdarlehen / Zinsen"]["amounts"]["2026-02"], -3000.0)

    def test_contribution_into_a_company_and_its_participation(self):
        cfg = {"companies": [{"area": "Muster GbR", "participation": "Beteiligung an Muster GbR"}]}
        data = build([(1, "giro", date(2026, 1, 5), 30000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 10), -10000.0, {"iban": "DE21", "cat": "Umbuchung"}),
                      (3, "kk", date(2026, 2, 10), 10000.0, {"iban": "DE11"}),
                      (4, "stake", date(2026, 2, 28), 4900.0, {"purpose": "Wertanpassung · #kontor-wert-20260228-1"})], cfg)
        self.assertAddsUp(data)
        p, g = rows(data["Privat"]), rows(data["Muster GbR"])
        self.assertEqual(p["Einlage/Entnahme Muster GbR"]["amounts"]["2026-02"], -10000.0)
        self.assertFalse(p["Einlage/Entnahme Muster GbR"]["nw"])
        self.assertEqual(p["Beteiligung an Muster GbR"]["amounts"]["2026-02"], -5100.0)        # 4,900 worth for 10,000 paid in
        self.assertEqual(g["Einlagen/Entnahmen Gesellschafter"]["amounts"]["2026-02"], 10000.0)
        self.assertTrue(g["Einlagen/Entnahmen Gesellschafter"]["nw"])
        self.assertEqual(g["Einlagen/Entnahmen Gesellschafter"]["lbl"], ["cf_einlagen_gesellschafter"])

    def test_without_participation_a_contribution_leaves_the_net_worth(self):
        data = build([(1, "giro", date(2026, 1, 5), 30000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 10), -10000.0, {"iban": "DE21"}),
                      (3, "kk", date(2026, 2, 10), 10000.0, {"iban": "DE11"})],
                     {"companies": [{"area": "Muster GbR"}], "account_mirrors": [{"a": "Darlehen an Freund", "b": "Verkäuferdarlehen", "from_date": "all"}]})
        self.assertAddsUp(data)
        self.assertTrue(rows(data["Privat"])["Einlage/Entnahme Muster GbR"]["nw"])

    def test_transfer_to_another_area(self):
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -200.0, {"iban": "DE31", "cat": "Umbuchung"}),
                      (3, "kind", date(2026, 2, 3), 200.0, {"iban": "DE11", "cat": "Umbuchung"})])
        self.assertAddsUp(data)
        self.assertEqual(rows(data["Privat"])["Einlage/Entnahme Kinder"]["amounts"]["2026-02"], -200.0)
        self.assertEqual(rows(data["Kinder"])["Einlage/Entnahme Privat"]["amounts"]["2026-02"], 200.0)
        for ds in data.values():
            self.assertNotIn("expenses", [s["name"] for s in ds["cashflow"]["sections"] if s["rows"] and s["name"] != "income"])

    def test_between_areas_paid_for_something_counts_by_category(self):
        # a salary from your own company, rent to your own partnership: income and expense, not a contribution or withdrawal
        data = build([(1, "kk", date(2026, 2, 3), -4000.0, {"iban": "DE11", "name": "Inhaber", "purpose": "Gehalt Februar"}),
                      (2, "giro", date(2026, 2, 3), 4000.0, {"iban": "DE21", "cat": "Gehalt"}),
                      (3, "giro", date(2026, 2, 5), -900.0, {"iban": "DE21", "cat": "Wohnen\\Miete"}),
                      (4, "kk", date(2026, 2, 5), 900.0, {"iban": "DE11", "purpose": "Miete Februar"}),
                      (5, "giro", date(2026, 2, 7), -500.0, {"iban": "DE21", "purpose": "Einlage"}),
                      (6, "kk", date(2026, 2, 7), 500.0, {"iban": "DE11", "purpose": "Einlage"}),
                      (7, "giro", date(2026, 2, 9), -50.0, {"iban": "DE21", "cat": "Umbuchung"}),
                      (8, "kk", date(2026, 2, 9), 50.0, {"iban": "DE11", "cat": "Umbuchung"})])
        self.assertAddsUp(data)
        p, g = rows(data["Privat"]), rows(data["Muster GbR"])
        self.assertEqual((p["Arbeitseinkommen"]["amounts"]["2026-02"], p["Wohnen"]["amounts"]["2026-02"]), (4000.0, -900.0))
        self.assertEqual(p["Einlage/Entnahme Muster GbR"]["amounts"]["2026-02"], -550.0)          # only what was paid for nothing
        self.assertEqual((g["Personal"]["amounts"]["2026-02"], g["Vermietung"]["amounts"]["2026-02"]), (-4000.0, 900.0))   # by its words (estimated)
        self.assertEqual(g["Personal"]["details"][0]["category"], "")
        self.assertEqual(g["Einlagen/Entnahmen Gesellschafter"]["amounts"]["2026-02"], 550.0)
        # a category that does not clearly name income or an expense ("Einlage", anything unknown), and the name of your own
        # company ("Zahnarztpraxis", "Hotel"), change nothing: a contribution or withdrawal -- unless you chose a position
        txs = [(1, "giro", date(2026, 2, 3), -10000.0, {"iban": "DE21", "cat": "Einlage", "name": "Hotel Muster GbR"}),
               (2, "kk", date(2026, 2, 3), 10000.0, {"iban": "DE11", "cat": "Privat\\Entnahmen und Einlagen", "name": "Zahnarzt"}),
               (3, "kk", date(2026, 2, 5), -5000.0, {"iban": "DE11", "name": "Zahnarztpraxis Inhaber"}),
               (4, "giro", date(2026, 2, 5), 5000.0, {"iban": "DE21", "name": "Hotel Muster GbR"})]
        data = build(txs)
        self.assertAddsUp(data)
        p, g = rows(data["Privat"]), rows(data["Muster GbR"])
        self.assertEqual(p["Einlage/Entnahme Muster GbR"]["amounts"]["2026-02"], -5000.0)
        self.assertEqual(g["Einlagen/Entnahmen Gesellschafter"]["amounts"]["2026-02"], 5000.0)
        self.assertFalse({"Sonstige Ausgaben", "Sonstige Einnahmen", "Erstattungen", "Freizeit & Reisen"} & (set(p) | set(g)))
        # named for the positions page: categories Kontor does not know and you did not place (between areas they stay contributions)
        self.assertEqual(data["Privat"]["cashflow"]["uncertain"], {"Einlage": 10000.0})           # moved, either way
        self.assertEqual(data["Muster GbR"]["cashflow"]["uncertain"], {"Privat / Entnahmen und Einlagen": 10000.0})
        data = build(txs, {"cashflow": {"positions": {"Einlage": "other_expenses"}}})
        self.assertNotIn("Einlage", data["Privat"]["cashflow"]["uncertain"])         # your choice: no longer unsure
        self.assertEqual(rows(data["Privat"])["Sonstige Ausgaben"]["amounts"]["2026-02"], -10000.0)
        # the same category on both sides: income for one area, an expense for the other (the direction within the area)
        data = build([(1, "kk", date(2026, 2, 3), -4000.0, {"iban": "DE11", "cat": "Gehalt"}), (2, "giro", date(2026, 2, 3), 4000.0, {"iban": "DE21", "cat": "Gehalt"}),
                      (3, "kk", date(2026, 2, 4), -9000.0, {"cat": "Gehalt", "name": "Mitarbeiter"}),
                      (4, "giro", date(2026, 2, 5), -300.0, {"iban": "DE21", "purpose": "Zinsen Darlehen"}), (5, "kk", date(2026, 2, 5), 300.0, {"iban": "DE11", "purpose": "Zinsen Darlehen"})])
        self.assertAddsUp(data)
        p, g = rows(data["Privat"]), rows(data["Muster GbR"])
        self.assertEqual((p["Arbeitseinkommen"]["amounts"]["2026-02"], g["Personal"]["amounts"]["2026-02"]), (4000.0, -13000.0))
        self.assertEqual((p["Zinsen"]["amounts"]["2026-02"], g["Kapitalerträge"]["amounts"]["2026-02"]), (-300.0, 300.0))

    def test_transfers_need_no_category(self):
        import categorize as C
        txs = [(1, "giro", date(2026, 2, 3), -200.0, {"iban": "DE12"}), (2, "tg", date(2026, 2, 3), 200.0, {"iban": "DE11"}),
               (3, "giro", date(2026, 2, 5), -700.0, {"name": "Freund"}), (4, "ford", date(2026, 2, 6), 700.0, {"name": "Freund"}),
               (5, "giro", date(2026, 2, 8), -30.0, {"name": "Laden"})]
        txs += [(6, "giro", date(2026, 2, 9), -400.0, {"iban": "DE21"}), (7, "kk", date(2026, 2, 9), 400.0, {"iban": "DE11"})]   # to another area
        led = make_ledger(txs)
        datasets(led)                                                        # the report finds the counter-booking in the manual account
        banks = {k for k, v in ACCOUNTS.items() if v[2] == "cash"}
        area_of = {k: v[1] for k, v in ACCOUNTS.items()}
        off = C.open_items(C.empty(), led, area_of, banks=banks)
        # between two areas a category matters (salary or contribution?): those stay in the list
        self.assertEqual(sorted(i for g in off["groups"] for i in g["ids"]), [5, 6, 7])
        self.assertEqual(C.stats(C.empty(), led, banks, area_of)["total"], {"without": 3})
        self.assertEqual({u["account"] for g in off["groups"] for u in g["transactions"]}, {"Giro", "Kontokorrent"})

    def test_offline_booking_paired_by_amount(self):
        # a loan to a friend: paid from the bank account, booked by hand in the offline receivable two days later
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -700.0, {"name": "Freund"}),
                      (3, "ford", date(2026, 2, 5), 700.0, {"name": "Freund"}),
                      (4, "giro", date(2026, 2, 6), -700.0, {"cat": "Lebensmittel"}),           # an expense never pairs
                      (5, "auto", date(2026, 2, 7), 700.0, {"purpose": "Zuschreibung"})])
        self.assertAddsUp(data)
        r = rows(data["Privat"])
        self.assertEqual(r["Darlehen an Freund / Rückzahlung"]["amounts"]["2026-02"], -700.0)
        self.assertEqual(r["Lebenshaltung"]["amounts"]["2026-02"], -700.0)
        self.assertEqual(r["Auto"]["amounts"]["2026-02"], 700.0)

    def test_pending_refund_and_missing_counterpart(self):
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -100.0, {"cat": "Lebensmittel"}),
                      (3, "giro", date(2026, 2, 9), 30.0, {"cat": "Lebensmittel", "name": "Erstattung"}),
                      (4, "giro", date(2026, 6, 19), -999.0, {"cat": "Lebensmittel", "booked": False}),     # pending: not yet
                      (5, "giro", date(2026, 3, 2), -250.0, {"iban": "DE12"}),                              # Tagesgeld: missing
                      (6, "giro", date(2026, 3, 4), -80.0, {"cat": "Umbuchung"})])                          # no counterpart
        self.assertAddsUp(data)
        r = rows(data["Privat"])
        self.assertEqual(r["Lebenshaltung"]["amounts"]["2026-02"], -70.0)
        self.assertEqual(r["Lebenshaltung"]["amounts"]["2026-06"], 0.0)
        self.assertEqual(r["Umbuchung nach Tagesgeld ohne Gegenbuchung"]["amounts"]["2026-03"], -250.0)
        self.assertEqual(r["Umbuchung ohne erkannten Partner"]["amounts"]["2026-03"], -80.0)
        self.assertTrue(any("Umbuchung" in w for w in data["Privat"]["warnings"]))

    def test_transfers_by_category_days_apart_and_undone_on_one_account(self):
        # PayPal books on the day, the bank days later: both marked as transfers -> a pair up to a week apart
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "tg", date(2026, 3, 13), 4.2, {"cat": "Umbuchung", "name": "Bank Account (direct debit)"}),
                      (3, "giro", date(2026, 3, 17), -4.2, {"cat": "Umbuchung", "name": "Zahldienst"}),       # 4 days
                      (4, "tg", date(2026, 2, 27), 624.0, {"cat": "Umbuchung"}),
                      (5, "giro", date(2026, 3, 3), -624.0, {"cat": "Umbuchung"}),                         # over the month end
                      (6, "tg", date(2026, 4, 1), 9.0, {"cat": "Umbuchung"}),
                      (7, "giro", date(2026, 4, 10), -9.0, {"cat": "Umbuchung"}),                          # 9 days: too far apart
                      (12, "tg", date(2026, 4, 14), 7.0, {"cat": "Umbuchung"}),
                      (13, "giro", date(2026, 4, 18), -7.0, {"cat": "Lebensmittel"}),                      # one side only: 3 days at most
                      # a top-up booked back on the same account in the same month: together nothing
                      (8, "giro", date(2026, 5, 16), -3000.0, {"cat": "Umbuchung"}),
                      (9, "giro", date(2026, 5, 16), 3000.0, {"cat": "Umbuchung"}),
                      # a deposit paid back the next month: away over the month end -- stays unclear
                      (10, "giro", date(2026, 5, 24), -1000.0, {"cat": "Umbuchung"}),
                      (11, "giro", date(2026, 6, 5), 1000.0, {"cat": "Umbuchung"})])
        self.assertAddsUp(data)
        p = data["Privat"]
        ids = {mk: sorted(v) for mk, v in p["cashflow"]["cf_ids"]["unclear\u001fUmbuchung ohne erkannten Partner"].items()}
        self.assertEqual(ids, {"2026-04": [6, 7, 12], "2026-05": [10], "2026-06": [11]})
        transit = next(r for r in p["balance"]["rows"] if r["id"] == "transit")
        self.assertEqual(transit["amounts"]["2026-02"], -624.0)                    # booked on PayPal, not yet at the bank

    def test_transfer_pairs_closest_first(self):
        unclear = lambda data: {mk: sorted(v) for mk, v in data["Privat"]["cashflow"]["cf_ids"].get("unclear\u001fUmbuchung ohne erkannten Partner", {}).items()}
        transit = lambda data, mk: next((r["amounts"][mk] for r in data["Privat"]["balance"]["rows"] if r["id"] == "transit"), 0.0)      # no row: nothing in transit
        base = [(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"})]
        # a closer booking keeps its counterpart: the one a week before stays unclear (nothing in transit at the month end)
        d = build(base + [(2, "tg", date(2026, 2, 28), 9.0, {"cat": "Umbuchung"}), (3, "tg", date(2026, 3, 6), 9.0, {"cat": "Umbuchung"}),
                          (4, "giro", date(2026, 3, 7), -9.0, {"cat": "Umbuchung"})])
        self.assertAddsUp(d); self.assertEqual(unclear(d), {"2026-02": [2]}); self.assertEqual(transit(d, "2026-02"), 0.0)
        # booked back the same day on the same account: that pair first, the other account's booking stays unclear
        d = build(base + [(2, "giro", date(2026, 5, 16), -3000.0, {"cat": "Umbuchung"}), (3, "giro", date(2026, 5, 16), 3000.0, {"cat": "Umbuchung"}),
                          (4, "tg", date(2026, 5, 20), 3000.0, {"cat": "Umbuchung"})])
        self.assertAddsUp(d); self.assertEqual(unclear(d), {"2026-05": [4]})
        # a week apart still pairs, eight days do not; two out against one in: the closer one
        d = build(base + [(2, "tg", date(2026, 3, 2), 5.0, {"cat": "Umbuchung"}), (3, "giro", date(2026, 3, 9), -5.0, {"cat": "Umbuchung"}),
                          (4, "tg", date(2026, 4, 1), 6.0, {"cat": "Umbuchung"}), (5, "giro", date(2026, 4, 9), -6.0, {"cat": "Umbuchung"}),
                          (6, "giro", date(2026, 4, 20), -8.0, {"cat": "Umbuchung"}), (7, "giro", date(2026, 4, 27), -8.0, {"cat": "Umbuchung"}),
                          (8, "tg", date(2026, 4, 25), 8.0, {"cat": "Umbuchung"})])
        self.assertAddsUp(d); self.assertEqual(unclear(d), {"2026-04": [4, 5, 6]})
        # undone on an account that is no bank account (a loan, an asset): together nothing as well
        d = build(base + [(2, "kredit", date(2026, 6, 3), -400.0, {"cat": "Umbuchung"}), (3, "kredit", date(2026, 6, 9), 400.0, {"cat": "Umbuchung"})])
        self.assertAddsUp(d); self.assertEqual(unclear(d), {}); self.assertNotIn("Privatkredit", rows(d["Privat"]))
        # in from one counterparty, out to another: no booking back -- both stay unclear
        d = build(base + [(2, "giro", date(2026, 6, 1), 500.0, {"cat": "Umbuchung", "iban": "DE90"}), (3, "giro", date(2026, 6, 20), -500.0, {"cat": "Umbuchung", "iban": "DE91"})])
        self.assertAddsUp(d); self.assertEqual(unclear(d), {"2026-06": [2, 3]})

    def test_transfer_to_a_card_moved_to_another_bank(self):
        # the debit names the old card's IBAN, the payment arrives on the new card: paired all the same (same IBAN on both, or
        # an outdated IBAN with the transfer category on both sides) -- no "without counterpart"
        from unittest import mock
        for new_iban, first in (("DE12", False), ("DE12", True), (None, False), ("DE21", False), ("DE21", True)):      # DE21: also an account of another area
            neu = {"new": ("Karte neu", "Privat", "cash", new_iban, "bank")}
            with mock.patch.dict(ACCOUNTS, dict(neu, **ACCOUNTS) if first else dict(ACCOUNTS, **neu), clear=True):          # before or after the old one
                d = datasets(make_ledger([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                                          (2, "giro", date(2026, 3, 22), -398.85, {"iban": "DE12", "cat": "Umbuchung"}),
                                          (3, "new", date(2026, 3, 22), 398.85, {"cat": "Umbuchung"})]),
                             {"balance": {"roles": {k: v[2] for k, v in ACCOUNTS.items()}}})
                self.assertAddsUp(d)
                self.assertFalse([z for z in rows(d["Privat"], "unclear")], new_iban)
                self.assertFalse([k for k in rows(d["Privat"]) if k.startswith("Einlage")], new_iban)
        # the IBAN's account really lacks it and nothing else fits: still named as missing there -- not booked back against a payment
        # on the same account, not taken by an offline account
        base = [(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}), (2, "giro", date(2026, 3, 2), -250.0, {"iban": "DE12", "cat": "Umbuchung"})]
        for extra in ([], [(3, "giro", date(2026, 3, 20), 250.0, {"cat": "Umbuchung"})], [(3, "kredit", date(2026, 3, 3), 250.0, {})]):
            d = build(base + extra)
            self.assertAddsUp(d); r = rows(d["Privat"])
            self.assertIn("Umbuchung nach Tagesgeld ohne Gegenbuchung", r, extra); self.assertNotIn("Privatkredit / Tilgung", r)

    def test_foreign_currency_is_kept_apart(self):
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -1000.0, {"iban": "DE14", "cat": "Umbuchung"}),
                      (3, "usd", date(2026, 2, 4), 1080.0, {"iban": "DE11", "cat": "Umbuchung"}),
                      (4, "usd", date(2026, 3, 4), -40.0, {"cat": "Reisen"})])
        p = data["Privat"]
        self.assertAddsUp(data)
        self.assertEqual(rows(p)["Fremdwährung Dollarkonto"]["amounts"]["2026-02"], -1000.0)
        self.assertNotIn("Reisen", rows(p))
        self.assertEqual(p["balance"]["net_worth"]["2026-03"], 2000.0)
        out = [r for r in p["balance"]["outside"] if r["role"] == "foreign_currency"]
        self.assertEqual([(r["name"], r["currency"], r["amounts"]["2026-03"]) for r in out], [("Dollarkonto", "USD", 1040.0)])
        self.assertTrue(any("Dollarkonto (USD)" in w for w in p["warnings"]))

    def test_ignored_category_is_a_named_reason(self):
        cfg = {"cashflow": {"positions": {"Privatentnahme": "ignore"}}}
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -300.0, {"cat": "Privatentnahme"})], cfg)
        self.assertAddsUp(data, allow=("ue_ignoriert",))
        u = data["Privat"]["cashflow"]["reconciliation"]["2026-02"]
        self.assertEqual(u["reasons"], [["ue_ignoriert", -300.0, ""]])
        self.assertEqual(u["reasons_cash"], [["ue_ignoriert", -300.0, ""]])
        ids = data["Privat"]["cashflow"]["cf_ids"]                 # the booking behind it, for a click on either check
        self.assertEqual((ids["\u001fcheck_cash"], ids["\u001fcheck_nw"]), ({"2026-02": [2]}, {"2026-02": [2]}))
        self.assertEqual((u["n_liq"], u["n_nw"]), (1, 1))

    def test_labels_are_translated(self):
        import i18n
        data = build([(1, "kk", date(2026, 1, 3), 9500.0, {"cat": "Miete"}),
                      (2, "vd", date(2026, 2, 28), -3000.0, {"purpose": "Zinsen · #kontor-zins-2026-02"})])
        z = rows(data["Muster GbR"])["Verkäuferdarlehen / Zinsen"]
        self.assertEqual((z["lbl"], z["glbl"], z["group"]), (["cf_name", "Verkäuferdarlehen"], ["cf_g_zinsen"], "Zinsen"))     # the loan, in the group "Zinsen"
        try:
            i18n.set_lang("en")
            self.assertEqual((i18n.tr(*z["lbl"]), i18n.tr(*z["glbl"])), ("Verkäuferdarlehen", "Interest"))
        finally:
            i18n.set_lang("de")


class ReviewCases(Reconciles):
    """Cases found in the independent review of 3.13.4."""

    def test_a_payment_to_another_area_never_pairs_by_amount(self):
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -200.0, {"iban": "DE31", "cat": "Taschengeld"}),
                      (3, "kind", date(2026, 2, 3), 200.0, {"iban": "DE11"}),
                      (4, "auto", date(2026, 2, 4), 200.0, {"purpose": "Zuschreibung"})])
        self.assertAddsUp(data)
        r = rows(data["Privat"])
        self.assertEqual(r["Einlage/Entnahme Kinder"]["amounts"]["2026-02"], -200.0)
        self.assertEqual(r["Auto"]["amounts"]["2026-02"], 200.0)
        self.assertNotIn("investing", [s["name"] for s in data["Privat"]["cashflow"]["sections"]
                                           if any(z["account"] == "auto" for z in s["rows"])])

    def test_payment_into_a_depot_valued_by_its_balances(self):
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -1000.0, {"iban": "DE15"})])
        self.assertAddsUp(data)
        r = rows(data["Privat"], "investing")
        self.assertEqual(r["Depot"]["amounts"]["2026-02"], -1000.0)
        self.assertFalse(r["Depot"]["nw"])
        self.assertFalse(rows(data["Privat"], "unclear"))

    def test_no_money_in_transit_without_a_bank_account(self):
        data = build([(1, "giro", date(2025, 12, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "kredit", date(2026, 1, 31), -10000.0, {"cat": "Umbuchung"}),
                      (3, "auto", date(2026, 2, 2), 10000.0, {"cat": "Umbuchung"})])
        p = data["Privat"]
        self.assertAddsUp(data)
        self.assertFalse([r for r in p["balance"]["rows"] if r["id"] == "transit"])
        liq = next(r for r in p["balance"]["rows"] if r["id"] == "pos:cash")
        self.assertEqual(liq["amounts"]["2026-01"], 3000.0)

    def test_account_moved_into_the_company(self):
        cfg = {"companies": [{"area": "Muster GbR", "participation": "Beteiligung an Muster GbR"}],
               "balance": {"roles": {k: v[2] for k, v in ACCOUNTS.items()}, "accounts_mapping": {"Kinderkonto": {"area": "g-Muster GbR"}}}}
        txs = [(1, "giro", date(2026, 1, 5), 30000.0, {"cat": "Gehalt"}),
               (2, "giro", date(2026, 2, 10), -10000.0, {"iban": "DE21"}),
               (3, "kk", date(2026, 2, 10), 10000.0, {"iban": "DE11"}),
               (4, "giro", date(2026, 2, 12), -500.0, {"iban": "DE31"}),
               (5, "kind", date(2026, 2, 12), 500.0, {"iban": "DE11"})]
        ledger = make_ledger(txs)
        before = datasets(ledger)                       # first without the move (same ledger: the cache must not keep it)
        self.assertIn("Einlage/Entnahme Kinder", rows(before["Privat"]))
        data = datasets(ledger, cfg)
        self.assertAddsUp(data)
        r = rows(data["Privat"])
        self.assertNotIn("Einlage/Entnahme Kinder", r)
        self.assertEqual(r["Einlage/Entnahme Muster GbR"]["amounts"]["2026-02"], -10500.0)
        self.assertFalse(r["Einlage/Entnahme Muster GbR"]["nw"])

    def test_both_sides_naming_each_other_may_be_a_week_apart(self):
        data = build([(1, "giro", date(2025, 11, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2025, 12, 22), -500.0, {"iban": "DE12"}),
                      (3, "tg", date(2025, 12, 28), 500.0, {"iban": "DE11"})])
        self.assertAddsUp(data)
        self.assertFalse(rows(data["Privat"], "unclear"))
        self.assertFalse([w for w in data["Privat"]["warnings"] if "Umbuchung" in w])


    def test_a_missing_booking_does_not_shift_a_recurring_transfer(self):
        txs, n, d = [(1, "giro", date(2025, 12, 1), 5000.0, {"cat": "Gehalt"})], 10, date(2026, 1, 6)
        while d < date(2026, 3, 10):                    # every week to the savings account; one booking there is missing
            n += 1; txs.append((n, "giro", d, -100.0, {"iban": "DE12"}))
            if d != date(2026, 1, 13):
                n += 1; txs.append((n, "tg", d, 100.0, {"iban": "DE11"}))
            d += timedelta(days=7)
        data = build(txs)
        self.assertAddsUp(data)
        r = rows(data["Privat"], "unclear")
        self.assertEqual({k: {m: v for m, v in z["amounts"].items() if v} for k, z in r.items()},
                         {"Umbuchung nach Tagesgeld ohne Gegenbuchung": {"2026-01": -100.0}})
        self.assertFalse([x for x in data["Privat"]["balance"]["rows"] if x["id"] == "transit"])


class Positions(Reconciles):
    """Income and expenses by Kontor's fixed outline; MoneyMoney's categories inside, assigned once (proposed by name)."""

    def test_proposals_by_name_and_direction(self):
        import report as R
        cases = {("Einkommen / Gehälter", True): "work_income", ("Einkommen / Tantieme", True): "work_income",
                 ("Einkommen / Rückzahlung Finanzamt", True): "refunds", ("Einkommen / Zinsen", True): "capital_income",
                 ("Sparen / Firmenanteile", False): "saving", ("Wohnen / Miete", False): "housing", ("Mieteinnahmen", True): "rental",
                 ("Vermietung / Parkweg / Hausgeld", False): "property_costs", ("Steuern / Einkommensteuer", False): "taxes",
                 ("Versicherungen / Kfz-Versicherung", False): "insurance", ("Steuerberater", False): "administration",
                 ("Kredit / Zinsen", False): "loan_interest", ("Lebensmittel", False): "living", ("Irgendwas", True): "other_income",
                 ("Irgendwas", False): "other_expenses", ("Immobilienkauf", False): "saving", ("Beteiligung", False): "saving",
                 ("Finanzierung", False): "repayment", ("Vermietung / Parkweg / Zinsen", False): "loan_interest", ("Geldautomat", False): "other_expenses",
                 ("Krankenkasse", True): "refunds", ("Sparkasse", False): "other_expenses", ("Laborkosten", False): "other_expenses",
                 ("Gehälter", False): "staff", ("Abos", False): "leisure", ("Wareneinkauf", False): "goods",
                 ("Einkommen", True): "work_income", ("Privat / Einkommen", True): "work_income", ("Mieteinkommen", True): "rental",
                 ("Kapitaleinkommen", True): "capital_income", ("Einkommensteuer", False): "taxes",
                 ("Einkommen / Kindergeld", True): "other_income", ("Hereinkommende Zahlungen", True): "other_income"}
        for (path, inc), want in cases.items():
            self.assertEqual(R.propose_position(path, inc), want, path)

    def test_every_position_has_its_text(self):
        import json
        import report as R
        txt = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "i18n.js"), encoding="utf-8").read()
        cat = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        self.assertFalse([k for k, _s, _r in R.POSITIONS + [("transfer", "", ""), ("income", "", ""), ("expenses", "", "")] if "pos_" + k not in cat])

    def test_your_choice_counts_for_the_category_and_below(self):
        cfg = {"cashflow": {"positions": {"Einkommen": "work_income", "Einkommen / Zinsen": "capital_income", "Sparen": "saving"}}}
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Einkommen\\Gehälter"}),
                      (2, "giro", date(2026, 2, 5), 500.0, {"cat": "Einkommen\\Tantieme"}),
                      (3, "giro", date(2026, 2, 6), 12.0, {"cat": "Einkommen\\Zinsen"}),
                      (4, "giro", date(2026, 2, 7), -800.0, {"cat": "Sparen\\Firmenanteile"}),
                      (5, "giro", date(2026, 2, 8), -40.0, {"cat": "Haushalt\\Drogerie"})], cfg)
        self.assertAddsUp(data)
        r = rows(data["Privat"])
        self.assertEqual(r["Arbeitseinkommen"]["amounts"]["2026-02"], 500.0)
        self.assertEqual({d["category"] for d in r["Arbeitseinkommen"]["details"]}, {"Einkommen / Gehälter", "Einkommen / Tantieme"})
        self.assertEqual(r["Kapitalerträge"]["amounts"]["2026-02"], 12.0)
        self.assertEqual(r["Sparen / Firmenanteile"]["group"], "Wertpapiere & Geldanlagen")  # saving: no expense, an investment
        self.assertEqual(r["Lebenshaltung"]["amounts"]["2026-02"], -40.0)                         # proposed by name
        order = [z["row"] for z in data["Privat"]["cashflow"]["sections"][0]["rows"]]
        self.assertEqual(order, ["Arbeitseinkommen", "Kapitalerträge"])                                    # the fixed outline

    def test_without_category_estimated_alike_in_every_area(self):
        # the company has no categories at all: Kontor estimates by the words; the rest stays without a category
        data = build([(1, "kk", date(2026, 1, 3), 9500.0, {"name": "Nexi Germany", "purpose": "Kartenumsaetze 02.01."}),
                      (2, "kk", date(2026, 2, 3), 9500.0, {"name": "Nexi Germany", "purpose": "Kartenumsaetze 02.02."}),
                      (3, "kk", date(2026, 2, 4), -800.0, {"name": "AOK Bayern", "purpose": "Beitrag 02/2026"}),
                      (4, "kk", date(2026, 2, 5), -3100.0, {"name": "Finanzamt", "purpose": "UStVA 01/2026"}),
                      (5, "kk", date(2026, 2, 6), -50.0, {"name": "Grosshandel Nord", "purpose": "RE 4711"}),
                      (6, "giro", date(2026, 2, 7), -60.0, {"name": "AOK Bayern", "purpose": "Beitrag"}),
                      (7, "giro", date(2026, 2, 8), 4000.0, {"name": "Arbeitgeber", "purpose": "Gehalt Februar"})])
        self.assertAddsUp(data)
        g = rows(data["Muster GbR"])
        self.assertEqual(g["Umsatzerlöse"]["amounts"]["2026-02"], 9500.0)
        self.assertEqual(g["Umsatzerlöse"]["details"][0]["category"], "")                    # estimated
        self.assertEqual((g["Personal"]["amounts"]["2026-02"], g["Umsatzsteuer"]["amounts"]["2026-02"]), (-800.0, -3100.0))
        self.assertEqual(g["Ohne Kategorie"]["amounts"]["2026-02"], -50.0)
        p = rows(data["Privat"])
        self.assertEqual((p["Versicherungen"]["amounts"]["2026-02"], p["Arbeitseinkommen"]["amounts"]["2026-02"]), (-60.0, 4000.0))

    def test_words_of_a_booking(self):
        import report as R
        from model import Tx
        def g(name, purpose, amount, company):
            return R.guess_position(Tx(id=1, account_uuid="x", booking_date=date(2026, 1, 1), value_date=date(2026, 1, 1), amount=amount, currency="EUR", name=name, purpose=purpose), company)
        self.assertIsNone(g("Muster GmbH Gesellschafter", "Gewinnausschüttung 2025", -50000.0, True))       # equity, no expense
        self.assertEqual(g("Finanzamt Mitte", "KapESt Gewinnausschüttung", -9000.0, True), "taxes")
        self.assertEqual(g("Finanzamt Mitte", "LSt 10/2026", -41000.0, True), "staff")                  # wage tax: staff costs
        self.assertEqual(g("Finanzamt Mitte", "USt-VA 10/2026", -23000.0, True), "vat")
        self.assertEqual(g("Finanzamt Mitte", "Erstattung USt 09/2026", 1200.0, True), "vat")
        self.assertEqual(g("Finanzamt Mitte", "ESt-Vorauszahlung", -3000.0, False), "taxes")
        self.assertEqual(g("Stadtwerke", "Strom Filiale 4", -900.0, True), "housing")                       # shown as "Raumkosten"
        self.assertEqual(g("Telekom", "Rechnung", -60.0, True), "operations")
        self.assertIsNone(g("Grosshandel Nord", "RE 4711 Umsatzsteuer 19 % Steuernummer 123", -500.0, True))
        self.assertEqual(g("Max Muster", "Lohn 02/2026", -2100.0, True), "staff")
        self.assertIsNone(g("Bank", "Darlehen Zins und Tilgung", -1500.0, False))                       # mixed: no estimate
        self.assertEqual(g("Bank", "Sollzinsen 4. Quartal", -80.0, False), "loan_interest")
        self.assertEqual(g("Nexi Germany", "Kartenumsätze", 900.0, True), "revenue")
        self.assertIsNone(g("Nexi Germany", "Kartenumsätze", 900.0, False))

    def test_an_estimate_is_never_saving_or_repayment(self):
        import categorize as C
        txs = [(1, "giro", date(2026, 1, 5), -100.0, {"name": "Broker AG", "cat": "Sparen\\ETF"}),
               (2, "giro", date(2026, 1, 9), -100.0, {"name": "Broker AG", "cat": "Sparen\\ETF"}),
               (3, "giro", date(2026, 2, 9), -5000.0, {"name": "Broker AG", "purpose": "Rechnung"})]
        led = make_ledger(txs)
        d = C.empty(); C.learn(d, led)
        config = core.merged_config({"balance": {"roles": {k: v[2] for k, v in ACCOUNTS.items()}}})
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
        r = rows(report.build_dataset(led, config, {}, TODAY, b, {k: v[2] for k, v in ACCOUNTS.items()}, learned=d))
        self.assertEqual(r["Ohne Kategorie"]["amounts"]["2026-02"], -5000.0)
        self.assertEqual(r["Sparen / ETF"]["amounts"].get("2026-02", 0.0), 0.0)

    def test_target_account_counts_below_too(self):
        cfg = {"cashflow": {"category_to_account": {"Sparen": "Auto"}}}
        data = build([(1, "giro", date(2026, 2, 5), -400.0, {"cat": "Sparen\\Bausparvertrag"})], cfg)
        self.assertAddsUp(data)
        z = rows(data["Privat"])["Sparen / Bausparvertrag"]
        self.assertEqual((z["account"], z["nw"]), ("auto", False))

    def test_learned_from_transfers_is_no_estimate(self):
        import categorize as C
        txs = [(1, "giro", date(2026, 1, 5), -100.0, {"name": "Ich", "cat": "Umbuchung"}), (2, "giro", date(2026, 1, 9), -100.0, {"name": "Ich", "cat": "Umbuchung"}),
               (3, "giro", date(2026, 2, 9), -700.0, {"name": "Ich"})]
        led = make_ledger(txs)
        d = C.empty(); C.learn(d, led)
        config = core.merged_config({"balance": {"roles": {k: v[2] for k, v in ACCOUNTS.items()}}})
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
        r = rows(report.build_dataset(led, config, {}, TODAY, b, {k: v[2] for k, v in ACCOUNTS.items()}, learned=d))
        self.assertEqual(r["Ohne Kategorie"]["amounts"]["2026-02"], -700.0)

    def test_property_keeps_its_reserve_unless_you_choose(self):
        im = [{"id": "i1", "name": "Parkweg", "area": "g-Muster GbR", "category": "Vermietung\\Parkweg"}]
        txs = [(1, "kk", date(2026, 2, 3), 1000.0, {"cat": "Vermietung\\Parkweg\\Miete"}),
               (2, "kk", date(2026, 2, 4), -100.0, {"cat": "Vermietung\\Parkweg\\Rücklage"})]
        g = rows(build(txs, {"real_estate": im})["Muster GbR"])
        self.assertEqual(g["Parkweg · Kosten"]["amounts"]["2026-02"], -100.0)                           # proposal "saving" does not count here
        data = build(txs, {"real_estate": im, "cashflow": {"positions": {"Vermietung / Parkweg / Rücklage": "saving"}}})
        self.assertAddsUp(data)
        self.assertIn("Vermietung / Parkweg / Rücklage", rows(data["Muster GbR"]))

    def test_usual_transfer_names(self):
        import report as R
        chk = R.transfer_check(core.merged_config({}))
        for path in ("Umbuchungen", "Übertrag", "Finanzen / Eigene Konten", "Umbuchung / Sparplan"):
            self.assertTrue(chk(path), path)
        self.assertFalse(chk("Lebensmittel"))
        for path in ("Reisen / Transfer", "Übertrag / Familie Ausland", "Transfer"):          # only the category's own usual name
            self.assertFalse(chk(path), path)
        self.assertFalse(R.transfer_check(core.merged_config({"cashflow": {"positions": {"Übertrag": "other_expenses"}}}))("Übertrag"))

    def test_transfer_follows_your_choice(self):
        cfg = {"cashflow": {"positions": {"Haushalt": "living", "Umbuchung / Sparplan": "other_expenses"}}}
        data = build([(1, "giro", date(2026, 2, 5), -30.0, {"cat": "Haushalt\\Umbuchung"}),
                      (2, "giro", date(2026, 2, 6), -40.0, {"cat": "Umbuchung\\Sparplan"}),
                      (3, "giro", date(2026, 2, 7), -50.0, {"cat": "Umbuchung\\Sonstiges"})], cfg)
        self.assertAddsUp(data)
        r = rows(data["Privat"])
        self.assertEqual(r["Lebenshaltung"]["amounts"]["2026-02"], -30.0)
        self.assertEqual(r["Sonstige Ausgaben"]["amounts"]["2026-02"], -40.0)
        self.assertEqual(r["Umbuchung ohne erkannten Partner"]["amounts"]["2026-02"], -50.0)            # still a transfer by its parent

    def test_same_position_named_for_a_company(self):
        data = build([(1, "kk", date(2026, 2, 3), -4000.0, {"name": "Vermieter", "purpose": "Miete Laden Februar"}),
                      (2, "giro", date(2026, 2, 3), -1200.0, {"name": "Vermieter", "purpose": "Miete Februar"})])
        self.assertEqual(rows(data["Muster GbR"])["Raumkosten"]["lbl"], ["pos_housing_g"])
        self.assertEqual(rows(data["Privat"])["Wohnen"]["amounts"]["2026-02"], -1200.0)

    def test_totals_for_planning_and_reading(self):
        # gross profit only where there is revenue; after interest and repayment (a new loan is no income); bank balance
        txs = [(1, "kk", date(2026, 1, 3), 10000.0, {"name": "Nexi", "purpose": "Kartenumsaetze"}),
               (2, "kk", date(2026, 1, 4), -6000.0, {"cat": "Wareneinkauf"}),
               (3, "kk", date(2026, 1, 5), -500.0, {"name": "Bank", "purpose": "Sollzinsen"}),
               (4, "vd", date(2026, 1, 6), 300.0, {"name": "Kontokorrent"}), (5, "kk", date(2026, 1, 6), -300.0, {"name": "Verkäuferdarlehen"}),
               (6, "vd", date(2026, 2, 1), -20000.0, {"name": "Kontokorrent"}), (7, "kk", date(2026, 2, 1), 20000.0, {"name": "Verkäuferdarlehen"})]
        led = make_ledger(txs)
        config = core.merged_config({"balance": {"roles": {k: v[2] for k, v in ACCOUNTS.items()}}})
        roles = {k: v[2] for k, v in ACCOUNTS.items()}
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Muster GbR")
        ds = report.build_dataset(led, config, {}, TODAY, b, roles)
        report.apply_plan(ds, {}, config)
        su = ds["cashflow"]["sums"]
        self.assertEqual((su["2026-01"]["Rohertrag"], su["2026-01"]["operating"]), (4000.0, 4000.0))
        self.assertEqual(su["2026-01"]["Nach_Kapitaldienst"], 3200.0)                                  # minus interest and repayment
        self.assertEqual(su["2026-02"]["Nach_Kapitaldienst"], 0.0)                                     # the new loan does not count
        self.assertEqual((su["2026-01"]["bank"], su["2026-02"]["bank"]), (3200.0, 23200.0))
        # start + change = end, also with money in transit over a month end and with an account that comes later
        txs2 = [(1, "giro", date(2026, 1, 3), 5000.0, {"cat": "Gehalt"}), (2, "giro", date(2026, 2, 27), -1000.0, {"name": "Tagesgeld", "iban": "DE12"}),
                (3, "tg", date(2026, 3, 2), 1000.0, {"name": "Giro", "iban": "DE11"}), (4, "giro", date(2026, 4, 3), -50.0, {"cat": "Lebensmittel"})]
        led2 = make_ledger(txs2)
        ds2 = report.build_dataset(led2, config, {}, TODAY, next(x for x in core.bereiche_for(led2, config) if x["name"] == "Privat"), roles)
        report.apply_plan(ds2, {}, config)
        s2, ue = ds2["cashflow"]["sums"], ds2["cashflow"]["reconciliation"]
        ms = sorted(m for m in s2 if m >= "2026-01")
        for prev, m in zip(ms, ms[1:]):
            if m in ue:
                self.assertAlmostEqual(s2[m]["bank"] - s2[prev]["bank"], s2[m]["cash_change"], 2, m)
        self.assertEqual(s2["2026-01"]["bank"], 5000.0)
        p = rows(build([(1, "giro", date(2026, 1, 3), 100.0, {"cat": "Gehalt"})])["Privat"])
        self.assertIn("Arbeitseinkommen", p)
        # Cashflow-Positionen proposes what each area counts: income for you, staff costs of the company (the area with more bookings first)
        both = make_ledger([(1, "giro", date(2026, 1, 3), 100.0, {"cat": "Gehalt"}), (2, "kk", date(2026, 1, 3), -100.0, {"cat": "Gehalt"}),
                            (3, "kk", date(2026, 2, 3), -100.0, {"cat": "Gehalt"})])
        row = next(r for r in core.positions_overview(both, config, [], TODAY)["categories"] if r["path"] == "Gehalt")
        self.assertEqual((row["proposal"], row["proposal_also"]), ("staff", ["work_income"]))
        dsp = report.build_dataset(make_ledger([(1, "giro", date(2026, 1, 3), 100.0, {"cat": "Gehalt"})]), config, {}, TODAY,
                                   next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat"), roles)
        report.apply_plan(dsp, {}, config)
        self.assertNotIn("Rohertrag", dsp["cashflow"]["sums"]["2026-01"])

    def test_learned_patterns_come_before_words(self):
        import categorize as C
        txs = [(1, "giro", date(2026, 1, 5), -40.0, {"name": "Supermarkt", "cat": "Lebensmittel"}),
               (2, "giro", date(2026, 1, 9), -45.0, {"name": "Supermarkt", "cat": "Lebensmittel"}),
               (3, "giro", date(2026, 2, 9), -50.0, {"name": "Supermarkt", "purpose": "Versicherung"})]
        led = make_ledger(txs)
        d = C.empty(); C.learn(d, led)
        config = core.merged_config({"balance": {"roles": {k: v[2] for k, v in ACCOUNTS.items()}}})
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
        ds = report.build_dataset(led, config, {}, TODAY, b, {k: v[2] for k, v in ACCOUNTS.items()}, learned=d)
        r = rows(ds)
        self.assertEqual(r["Lebenshaltung"]["amounts"]["2026-02"], -50.0)                         # not "Versicherungen"
        self.assertEqual({x["category"] for x in r["Lebenshaltung"]["details"]}, {"Lebensmittel", ""})

    def test_a_property_has_its_own_rows(self):
        cfg = {"real_estate": [{"id": "i1", "name": "Parkweg", "area": "g-Muster GbR", "category": "Vermietung\\Parkweg"}]}
        data = build([(1, "kk", date(2026, 1, 3), 9500.0, {"cat": "Vermietung\\Parkweg\\Mieteinnahmen"}),
                      (2, "kk", date(2026, 2, 3), 9500.0, {"cat": "Vermietung\\Parkweg\\Mieteinnahmen"}),
                      (3, "kk", date(2026, 2, 4), -800.0, {"cat": "Vermietung\\Parkweg\\Hausgeld"})], cfg)
        self.assertAddsUp(data)
        g = rows(data["Muster GbR"])
        self.assertEqual((g["Parkweg · Miete"]["amounts"]["2026-02"], g["Parkweg · Miete"]["property_name"]), (9500.0, "Parkweg"))
        self.assertEqual(g["Parkweg · Kosten"]["amounts"]["2026-02"], -800.0)

    def test_property_rows_by_sign_and_the_most_specific_property(self):
        cfg = {"real_estate": [{"id": "i1", "name": "Altbau", "area": "g-Muster GbR", "category": "Vermietung"},
                              {"id": "i2", "name": "Neubau", "area": "g-Muster GbR", "category": "Vermietung\\Neubau"}]}
        data = build([(1, "kk", date(2026, 1, 3), 1500.0, {"cat": "Vermietung"}), (2, "kk", date(2026, 2, 3), 1500.0, {"cat": "Vermietung"}),
                      (3, "kk", date(2026, 2, 4), -4000.0, {"cat": "Vermietung"}), (4, "kk", date(2026, 2, 5), 900.0, {"cat": "Vermietung\\Neubau"}),
                      (5, "kk", date(2026, 2, 6), -300.0, {"cat": "Vermietung\\Neubau\\Zinsen"})], cfg)
        self.assertAddsUp(data)
        g = rows(data["Muster GbR"])
        self.assertEqual((g["Altbau · Miete"]["amounts"]["2026-02"], g["Altbau · Kosten"]["amounts"]["2026-02"]), (1500.0, -4000.0))
        self.assertEqual(g["Neubau · Miete"]["amounts"]["2026-02"], 900.0)
        self.assertEqual(g["Zinsen"]["amounts"]["2026-02"], -300.0)                                      # financing stays financing

    def test_budget_per_position(self):
        led = make_ledger([(1, "giro", date(2026, 1, 3), -100.0, {"cat": "Wohnen\\Strom/Gas"}), (2, "giro", date(2026, 1, 4), -900.0, {"cat": "Wohnen\\Miete"}),
                           (3, "giro", date(2026, 1, 5), -50.0, {"cat": "Lebensmittel\\Supermarkt"})])
        config = core.merged_config({"balance": {"roles": {k: v[2] for k, v in ACCOUNTS.items()}}})
        roles = {k: v[2] for k, v in ACCOUNTS.items()}
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
        ds = report.build_dataset(led, config, {}, TODAY, b, roles)
        ds["budgets"] = core.budgets_from_categories([{"path": "Wohnen\\Strom/Gas", "budget": {"amount": 100, "period": "monthly"}},
                                                      {"path": "Wohnen\\Miete", "budget": {"amount": 900, "period": "monthly"}},
                                                      {"path": "Lebensmittel", "budget": {"amount": 400, "period": "monthly"}}])
        report.apply_plan(ds, {}, config)
        r = rows(ds)
        self.assertEqual((r["Wohnen"]["plan"]["budget"], r["Lebenshaltung"]["plan"]["budget"]), (-1000.0, -400.0))


class StatementGroups(Reconciles):
    def test_loan_taken_up_repaid_and_interest(self):
        """Financing by kind: a loan paid out is "taken up" (its own row, never a negative repayment), repayment and interest
        in their groups with the loan as the row; investing by the kind of account. The amounts and checks stay as before."""
        txs = [(1, "darl", date(2026, 2, 2), -400000.0, {"iban": "DE11"}), (2, "giro", date(2026, 2, 2), 400000.0, {"iban": "DE13"}),
               (3, "giro", date(2026, 3, 1), -1500.0, {"iban": "DE13"}), (4, "darl", date(2026, 3, 1), 1500.0, {"iban": "DE11"}),
               (5, "darl", date(2026, 3, 31), -600.0, {"purpose": "Zinsen · #kontor-zins-2026-03"}),
               (6, "giro", date(2026, 3, 5), -2000.0, {"iban": "DE15"})]
        data = build(txs)
        self.assertAddsUp(data)
        r = rows(data["Privat"], "financing")
        self.assertEqual((r["Darlehen Hausbau / Aufnahme"]["group"], r["Darlehen Hausbau / Aufnahme"]["amounts"]["2026-02"]), ("Darlehensaufnahme", 400000.0))
        self.assertEqual(r["Darlehen Hausbau / Tilgung"]["amounts"]["2026-02"], 0.0)
        self.assertEqual((r["Darlehen Hausbau / Tilgung"]["amounts"]["2026-03"], r["Darlehen Hausbau / Zinsen"]["amounts"]["2026-03"]), (-900.0, -600.0))
        self.assertEqual([z["group"] for z in data["Privat"]["cashflow"]["sections"][3]["rows"]], ["Darlehensaufnahme", "Tilgung", "Zinsen"])
        self.assertEqual(rows(data["Privat"], "investing")["Depot"]["group"], "Wertpapiere & Geldanlagen")
        config = core.merged_config({"balance": {"roles": {k: v[2] for k, v in ACCOUNTS.items()}}})
        ds = data["Privat"]
        report.apply_plan(ds, {}, config)
        z = rows(ds, "financing")["Darlehen Hausbau / Aufnahme"]
        self.assertEqual(z["plan"]["method"], "none"); self.assertFalse(any(abs(v) > 0.005 for v in z["plan"]["amounts"].values()))
        # a loan taken up in the plan raises the debt as much as the cash: net worth stays
        fut = sorted(ds["plan_months"])[2]
        planned = build(txs)["Privat"]
        report.apply_plan(planned, {"rows": {"financing/Darlehen Hausbau / Aufnahme": {"amounts": {fut: 100000.0}}}}, config)
        pp, p0 = planned["balance"]["projection"], ds["balance"]["projection"]
        self.assertAlmostEqual(pp["cash"][fut] - p0["cash"][fut], 100000.0, 2)
        self.assertAlmostEqual(pp["net_worth"][fut], p0["net_worth"][fut], 2)

    def test_saving_without_an_account_and_by_category(self):
        """Saving by a category without a known account is "saving" (not securities); a category row beside the loans of its
        group is "by category", an account named like its group keeps its name."""
        data = build([(1, "giro", date(2026, 3, 3), -500.0, {"cat": "Sparen"}), (2, "giro", date(2026, 3, 1), -300.0, {"cat": "Tilgung"}),
                      (3, "giro", date(2026, 3, 1), -1500.0, {"iban": "DE13"}), (4, "darl", date(2026, 3, 1), 1500.0, {"iban": "DE11"})],
                     {"cashflow": {"positions": {"Sparen": "saving", "Tilgung": "repayment"}}})
        inv, fin = rows(data["Privat"], "investing"), rows(data["Privat"], "financing")
        self.assertEqual(inv["Sparen"]["group"], "Wertpapiere & Geldanlagen" if any(v[4] == "portfolio" for v in ACCOUNTS.values() if v[1] == "Privat") else "Sparen & Anlegen")
        self.assertEqual((fin["Tilgung"]["group"], fin["Tilgung"]["lbl"]), ("Tilgung", ["cf_per_kategorie"]))
        self.assertEqual(fin["Darlehen Hausbau / Tilgung"]["lbl"], ["cf_name", "Darlehen Hausbau"])
        gbr = build([(1, "kk", date(2026, 3, 3), -500.0, {"cat": "Sparen"})], {"cashflow": {"positions": {"Sparen": "saving"}}})["Muster GbR"]
        self.assertEqual(rows(gbr, "investing")["Sparen"]["group"], "Sparen & Anlegen")       # no depot there: no account known


class OpeningBalance(Reconciles):
    """An account that starts later with an opening balance of its own in MoneyMoney (its first booking leaves a rest): a
    transfer where a bank account shows the opposite amount that month (a balance moved over from an old card), else a row
    of its own among the changes in value -- never "balance unknown"."""

    def setUp(self):
        self._acc = dict(ACCOUNTS)
        ACCOUNTS["karte"] = ("Alte Karte", "Privat", "cash", None, "bank")

    def tearDown(self):
        ACCOUNTS.clear(); ACCOUNTS.update(self._acc)

    def data(self, txs):
        led = make_ledger(txs)
        led.accounts["tg"].balance = 0.0                 # the new account: opening balance -115.20, paid off in March
        return datasets(led)

    BASE = [(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
            (2, "karte", date(2026, 1, 9), -115.20, {"cat": "Lebensmittel"}),
            (3, "giro", date(2026, 3, 12), -115.20, {"iban": "DE12"}), (4, "tg", date(2026, 3, 12), 115.20, {"iban": "DE11"})]

    def test_a_balance_moved_over_is_a_transfer(self):
        data = self.data(self.BASE + [(5, "karte", date(2026, 3, 2), 115.20, {"name": "Saldoübertrag"})])
        self.assertAddsUp(data)                                                  # no reason needed at all
        ds = data["Privat"]
        self.assertFalse([u for u in ds["cashflow"]["reconciliation"].values() if u["reasons"] or u["reasons_cash"]])
        self.assertNotIn("Ohne Kategorie", rows(ds, "income")); self.assertNotIn("Tagesgeld / Anfangssaldo", rows(ds))
        tg = next(r for r in ds["balance"]["rows"] if r["id"] == "tg")
        self.assertEqual((tg["amounts"]["2026-02"], tg["amounts"]["2026-03"]), (None, 0.0))

    def test_otherwise_its_own_row(self):
        data = self.data(self.BASE)
        self.assertAddsUp(data, allow=("ue_anfangssaldo",))
        ds = data["Privat"]
        z = rows(ds, "valuation")["Tagesgeld / Anfangssaldo"]
        self.assertEqual((z["amounts"]["2026-03"], z["nw"], z["lbl"]), (-115.2, True, ["cf_anfangssaldo", "Tagesgeld"]))
        self.assertEqual(ds["cashflow"]["reconciliation"]["2026-03"]["reasons_cash"], [["ue_anfangssaldo", -115.2, "Tagesgeld"]])
        self.assertFalse(any(g[0] == "ue_unbekannt" for u in ds["cashflow"]["reconciliation"].values() for g in u["reasons"] + u["reasons_cash"]))
        # a booking of that amount with a category of income, or from another area: it is that, not the balance moved over
        for extra in ({"cat": "Erstattungen"}, {"iban": "DE21"}):
            data = self.data(self.BASE + [(5, "karte", date(2026, 3, 2), 115.20, extra)])
            self.assertIn("Tagesgeld / Anfangssaldo", rows(data["Privat"], "valuation"), extra)
        # two bookings of that amount that month: no guess, its own row
        data = self.data(self.BASE + [(5, "karte", date(2026, 3, 2), 115.20, {}), (6, "giro", date(2026, 3, 20), 115.20, {})])
        self.assertIn("Tagesgeld / Anfangssaldo", rows(data["Privat"], "valuation"))

    def test_opened_before_its_first_booking(self):
        """Kept by its bookings: before the first booking no balance -- unless MoneyMoney recorded the account earlier at 0
        (opened then, nothing on it): from there on 0. No estimate: an opening balance of its own, or a known balance other
        than 0 before the first booking, keeps it unknown there (and the row "Anfangssaldo" where it was)."""
        roles = {k: v[2] for k, v in ACCOUNTS.items()}
        config = core.merged_config({"balance": {"roles": roles}})

        def run(txs, mm, tg_balance=None):
            led = make_ledger(txs)
            if tg_balance is not None:
                led.accounts["tg"].balance = tg_balance
            b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
            ds = report.build_dataset(led, config, {"history_mm": {"tg": mm}} if mm else {}, TODAY, b, roles)
            return ds, next(r for r in ds["balance"]["rows"] if r["id"] == "tg")["amounts"]
        txs = [(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}), (2, "tg", date(2026, 4, 2), 500.0, {"iban": "DE99"})]
        ds, plain = run(txs, None)
        self.assertEqual((plain["2026-02"], plain["2026-03"], plain["2026-04"]), (None, None, 500.0))
        ds, rec = run(txs, {"2026-02": 0.0, "2026-03": 0.0})
        self.assertEqual((rec["2026-01"], rec["2026-02"], rec["2026-03"], rec["2026-04"]), (None, 0.0, 0.0, 500.0))
        self.assertAddsUp({"Privat": ds}, allow=("ue_unbekannt",))
        self.assertFalse(any(g[0] == "ue_unbekannt" and g[2] == "Tagesgeld" for mk in ("2026-03", "2026-04")
                             for g in ds["cashflow"]["reconciliation"][mk]["reasons"] + ds["cashflow"]["reconciliation"][mk]["reasons_cash"]))
        # MoneyMoney knew another balance before the first booking: Kontor does not assume nothing happened
        ds, other = run(txs, {"2026-02": 0.0, "2026-03": 100.0})
        self.assertEqual((other["2026-02"], other["2026-03"], other["2026-04"]), (None, None, 500.0))
        # an opening balance of its own (-115.20): unknown before the first booking, the row "Anfangssaldo" in its month, as before
        ds, op = run(txs, {"2026-02": -115.2, "2026-03": -115.2}, tg_balance=500.0 - 115.2)
        self.assertEqual((op["2026-03"], op["2026-04"]), (None, 384.8))
        self.assertAddsUp({"Privat": ds}, allow=("ue_anfangssaldo",))
        self.assertEqual(rows(ds, "valuation")["Tagesgeld / Anfangssaldo"]["amounts"]["2026-04"], -115.2)


class SavingByRecipient(Reconciles):
    """Saving that arrives as a booking on none of your accounts (a depot kept by balances): the account per recipient you
    chose, else the category's, else the only depot -- without one it never counts as a depot's gain but stands openly as
    "without target account". All IBANs, names and amounts are made up."""
    ONE = "DE02100100100006820101"          # banks' public sample IBANs: at the bank of the first depot (bank code 10010010)
    TWO = "DE02120300000000202051"          # ... and of the second (12030000)

    def setUp(self):
        self._acc = dict(ACCOUNTS)
        ACCOUNTS["depot2"] = ("Depot Zwei", "Privat", "securities", None, "portfolio")

    def tearDown(self):
        ACCOUNTS.clear(); ACCOUNTS.update(self._acc)

    def data(self, txs, cfg=None, hist=None):
        led = make_ledger(txs)
        led.accounts["depot"].bank_code, led.accounts["depot2"].bank_code = "10010010", "12030000"
        config = core.merged_config(dict({"balance": {"roles": {k: v[2] for k, v in ACCOUNTS.items()}},
                                          "cashflow": {"positions": {"Sparen": "saving"}}}, **(cfg or {})))
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
        return b["id"], config, report.build_dataset(led, config, {"history": hist or {}}, TODAY, b, {k: v[2] for k, v in ACCOUNTS.items()})

    def txs(self):
        return [(1, "giro", date(2026, 1, 5), 9000.0, {"cat": "Gehalt"}),
                (2, "giro", date(2026, 6, 3), -1000.0, {"cat": "Sparen", "name": "Broker Zwei AG", "iban": self.TWO}),
                (3, "giro", date(2026, 6, 4), -300.0, {"cat": "Sparen / ETF", "name": "Broker Eins", "iban": self.ONE}),
                (9, "depot2", date(2026, 1, 1), 1000.0, {})]          # depot two: worth 1000 today, 0 before (history below)

    def test_without_a_target_it_is_no_gain_and_stands_openly(self):
        _, _, ds = self.data(self.txs(), hist={"depot2": {"2026-01": 0.0}})
        self.assertAddsUp({"Privat": ds})
        r = rows(ds)
        self.assertEqual(r["Anlage ohne Zielkonto"]["amounts"]["2026-06"], -1300.0)           # out of the net worth Kontor sees ...
        self.assertTrue(r["Anlage ohne Zielkonto"]["nw"])
        self.assertEqual(r["Depot Zwei"]["amounts"]["2026-06"], 1000.0)                      # ... which the depot's rise brings back
        self.assertEqual((r["Sparen"]["account"], r["Sparen"]["nw"]), (None, False))
        an = {a["key"]: a for a in ds["cashflow"]["saving_recipients"]}
        self.assertEqual([a["key"] for a in ds["cashflow"]["saving_recipients"]], [self.TWO, self.ONE])     # largest first
        self.assertEqual((an[self.TWO]["how"], an[self.TWO]["proposal"]), ("", "depot2"))           # proposals by the bank of the IBAN
        self.assertEqual(an[self.ONE]["proposal"], "depot")
        self.assertEqual((an[self.ONE]["count"], an[self.ONE]["sum"], an[self.ONE]["categories"]), (1, -300.0, ["Sparen / ETF"]))
        self.assertEqual(ds["cashflow"]["saving_targets"], ["depot", "depot2"])

    def test_the_account_you_chose_takes_it(self):
        area, _, _ = self.data(self.txs())
        cfg = {"cashflow": {"positions": {"Sparen": "saving"}, "recipient_to_account": {area: {self.TWO: "Depot Zwei", self.ONE: "external"}}}}
        _, _, ds = self.data(self.txs(), cfg, hist={"depot2": {"2026-01": 0.0}})
        self.assertAddsUp({"Privat": ds})
        r = rows(ds)
        self.assertNotIn("Anlage ohne Zielkonto", r)
        self.assertAlmostEqual(r.get("Depot Zwei", {"amounts": {}})["amounts"].get("2026-06", 0.0), 0.0)     # paid in, not a gain
        self.assertEqual((r["Sparen → Depot Zwei"]["account"], r["Sparen → Depot Zwei"]["nw"]), ("depot2", False))
        self.assertEqual((r["Sparen / ETF → extern"]["account"], r["Sparen / ETF → extern"]["nw"]), (None, True))   # none in MoneyMoney: leaves the net worth
        an = {a["key"]: a for a in ds["cashflow"]["saving_recipients"]}
        self.assertEqual((an[self.TWO]["how"], an[self.TWO]["target"], an[self.TWO]["proposal"]), ("recipient", "depot2", None))
        self.assertEqual((an[self.ONE]["how"], an[self.ONE]["auto_how"]), ("external", ""))
        # the recipient's choice comes before the category's account; an account of another area does not count here
        cfg["cashflow"]["category_to_account"] = {"Sparen": "Depot"}
        cfg["cashflow"]["recipient_to_account"] = {area: {self.TWO: "Depot Zwei"}, "anders": {self.ONE: "Depot"}}
        _, _, ds = self.data(self.txs(), cfg)
        an = {a["key"]: a for a in ds["cashflow"]["saving_recipients"]}
        self.assertEqual((an[self.TWO]["target"], an[self.TWO]["auto_target"], an[self.TWO]["auto_how"]), ("depot2", "depot", "category"))
        self.assertEqual((an[self.ONE]["target"], an[self.ONE]["how"]), ("depot", "category"))        # "Sparen / ETF" lies below "Sparen"
        cfg["cashflow"]["recipient_to_account"] = {area: {self.TWO: "Kontokorrent"}}                         # an account of the company: not here
        _, _, ds = self.data(self.txs(), cfg)
        self.assertEqual({a["key"]: a["how"] for a in ds["cashflow"]["saving_recipients"]}[self.TWO], "category")

    def test_one_recipient_over_categories_with_different_accounts(self):
        txs = self.txs() + [(4, "giro", date(2026, 5, 4), -200.0, {"cat": "Altersvorsorge", "name": "Broker Zwei AG", "iban": self.TWO})]
        _, _, ds = self.data(txs, {"cashflow": {"positions": {"Sparen": "saving", "Altersvorsorge": "saving"}, "category_to_account": {"Sparen": "Depot"}}})
        an = {a["key"]: a for a in ds["cashflow"]["saving_recipients"]}
        self.assertEqual((an[self.TWO]["how"], an[self.TWO]["auto_how"], an[self.TWO]["count"]), ("mixed", "mixed", 2))
        self.assertEqual(sorted(an[self.TWO]["categories"]), ["Altersvorsorge", "Sparen"])

    def test_one_category_into_several_accounts(self):
        """The case it is for: one category ("Sparen") to two recipients with different accounts -- each its own row, every
        month adds up."""
        area, _, _ = self.data(self.txs())
        txs = [x if x[0] != 3 else (3, "giro", date(2026, 6, 4), -300.0, {"cat": "Sparen", "name": "Broker Eins", "iban": self.ONE}) for x in self.txs()]
        for order in (txs, [txs[0], txs[2], txs[1], txs[3]]):
            cfg = {"cashflow": {"positions": {"Sparen": "saving"}, "recipient_to_account": {area: {self.TWO: "Depot Zwei", self.ONE: "external"}}}}
            _, _, ds = self.data(order, cfg, hist={"depot2": {"2026-01": 0.0}})
            self.assertAddsUp({"Privat": ds})
            r = rows(ds, "investing")
            self.assertEqual((r["Sparen → Depot Zwei"]["account"], r["Sparen → Depot Zwei"]["nw"], r["Sparen → Depot Zwei"]["amounts"]["2026-06"]), ("depot2", False, -1000.0))
            self.assertEqual((r["Sparen → extern"]["nw"], r["Sparen → extern"]["lbl"], r["Sparen → extern"]["amounts"]["2026-06"]), (True, ["cf_anlage_extern", "Sparen"], -300.0))
            self.assertNotIn("Sparen", r); self.assertNotIn("Anlage ohne Zielkonto", rows(ds))
            report.apply_plan(ds, {}, core.merged_config({}))          # planning: each row with its own account
            self.assertTrue(rows(ds, "investing")["Sparen → Depot Zwei"]["plan"])

    def test_an_account_kept_by_balances_takes_it_as_paid_in(self):
        """An asset kept by balances (no depot): the payment is paid in, not a correction of its balance; a bank account set
        for the category keeps its old way (no "without target account")."""
        area, _, _ = self.data(self.txs())
        txs = self.txs()[:1] + [(5, "giro", date(2026, 2, 3), -1000.0, {"cat": "Sparen", "name": "Goldhandel", "iban": self.TWO})]
        cfg = {"balance": {"roles": {k: v[2] for k, v in ACCOUNTS.items()}, "history_source": {"Auto": "balances"}},
               "cashflow": {"positions": {"Sparen": "saving"}, "recipient_to_account": {area: {self.TWO: "Auto"}}}}
        led = make_ledger(txs); led.accounts["auto"].balance = 1000.0                 # worth 1000 today, 0 in January
        config = core.merged_config(cfg)
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
        ds = report.build_dataset(led, config, {"history": {"auto": {"2026-01": 0.0}}}, TODAY, b, {k: v[2] for k, v in ACCOUNTS.items()})
        self.assertAddsUp({"Privat": ds})
        r = rows(ds)
        self.assertNotIn("Auto / Korrektur Kontostand", r); self.assertEqual(r["Sparen → Auto"]["account"], "auto")
        _, _, ds = self.data(txs, {"cashflow": {"positions": {"Sparen": "saving"}, "category_to_account": {"Sparen": "Tagesgeld"}}})
        self.assertNotIn("Anlage ohne Zielkonto", rows(ds)); self.assertEqual(rows(ds)["Sparen"]["account"], "tg")

    def test_the_category_account_elsewhere_keeps_the_depot_out(self):
        """As before: a category whose account lies in another area does not go into this area's only depot by guess."""
        del ACCOUNTS["depot2"]
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}), (2, "giro", date(2026, 3, 3), -500.0, {"cat": "Sparen", "name": "Bank"})],
                     {"cashflow": {"positions": {"Sparen": "saving"}, "category_to_account": {"Sparen": "Kontokorrent"}}})
        self.assertAddsUp(data)
        self.assertEqual(rows(data["Privat"])["Anlage ohne Zielkonto"]["amounts"]["2026-03"], -500.0)
        self.assertEqual(data["Privat"]["cashflow"]["saving_recipients"][0]["how"], "")

    def test_saving_settings(self):
        led = make_ledger(self.txs())
        cfg = core.save_positions(core.merged_config({}), {"recipient": {"p": {self.TWO: "Depot Zwei", self.ONE: "external"}}}, led)
        self.assertEqual(cfg["cashflow"]["recipient_to_account"], {"p": {self.TWO: "Depot Zwei", self.ONE: "external"}})
        cfg = core.save_positions(cfg, {"recipient": {"p": {self.ONE: ""}}}, led)           # "" = Kontor's choice again
        self.assertEqual(cfg["cashflow"]["recipient_to_account"], {"p": {self.TWO: "Depot Zwei"}})
        cfg2 = core.save_positions(cfg, {"recipient": {"p": {self.TWO: None}}}, led)
        self.assertEqual(cfg2["cashflow"]["recipient_to_account"], {})
        with self.assertRaises(KeyError):
            core.save_positions(cfg, {"recipient": {"p": {self.TWO: "kein Konto"}}}, led)
        for bad in ({"recipient": []}, {"recipient": {"p": "x"}}, {"recipient": {"p": {"": "depot"}}}, {"recipient": {"p": {self.TWO: 5}}}):
            with self.assertRaises(ValueError):
                core.save_positions(cfg, bad, led)
        # odd shapes by hand are dropped; a package never carries your recipients (their IBANs), nor takes them in
        shaped = core.merged_config({"cashflow": {"recipient_to_account": {"p": {self.TWO: "depot2", "x": 3}, "q": "nein"}}})
        self.assertEqual(shaped["cashflow"]["recipient_to_account"], {"p": {self.TWO: "depot2"}})
        self.assertEqual(core.merged_config({"cashflow": {"recipient_to_account": "nein"}})["cashflow"]["recipient_to_account"], {})
        pkg = core.export_package(cfg, ledger=led)
        self.assertNotIn("recipient_to_account", pkg["config"]["cashflow"])
        merged, _, _ = core.import_package(core.merged_config({}), {"kontor_package": 1, "config": {"cashflow": {"recipient_to_account": {"p": {self.TWO: "depot2"}}}}}, led)
        self.assertEqual(merged["cashflow"].get("recipient_to_account") or {}, {})
        for mode in ("replace", "merge"):                     # your own stay, also when a package replaces the cash flow settings
            merged, _, _ = core.import_package(cfg, {"kontor_package": 1, "config": {"cashflow": {"positions": {"Sparen": "saving"}}}}, led, mode)
            self.assertEqual(merged["cashflow"]["recipient_to_account"], {"p": {self.TWO: "Depot Zwei"}}, mode)
        # a gone account: a note, not an error (Kontor's choice applies again)
        found = core.check_config(led, [], dict(cfg, cashflow=dict(cfg["cashflow"], recipient_to_account={"p": {self.TWO: "weg | Altes Depot"}})))
        self.assertTrue(any(f["severity"] == "warning" and self.TWO in f["text"] for f in found))
        self.assertFalse(any(f["severity"] == "error" and self.TWO in f["text"] for f in found))
        area = next(x for x in core.bereiche_for(led, cfg) if x["name"] == "Privat")["id"]          # an account of another area: a note
        found = core.check_config(led, [], dict(cfg, cashflow=dict(cfg["cashflow"], recipient_to_account={area: {self.TWO: "Kontokorrent"}})))
        self.assertTrue(any(f["severity"] == "warning" and "Kontokorrent" in f["text"] for f in found))


class MirrorsAndCompanies(Reconciles):
    def test_a_mirror_into_a_company_counts_at_once(self):
        """A company counts as set up with an account mirror into one of its accounts: a payment to it from another company is
        a contribution there (Investitionen) -- also when only the mirror was added and nothing changed in MoneyMoney."""
        areas = [{"id": "p", "name": "Privat", "kind": "private", "main_area": True, "accounts": ["Privat"]},
                 {"id": "m", "name": "Muster GbR", "kind": "company", "accounts": ["Muster GbR"]},
                 {"id": "k", "name": "Kinder", "kind": "company", "accounts": ["Kinder"]}]
        led = make_ledger([(1, "kk", date(2026, 3, 3), -10000.0, {"iban": "DE31"}), (2, "kind", date(2026, 3, 3), 10000.0, {"iban": "DE21"})])
        before = datasets(led, {"areas": areas})
        self.assertEqual([s for s in ("investing", "financing") if rows(before["Muster GbR"], s)], ["financing"])
        after = datasets(led, {"areas": areas, "account_mirrors": [{"a": "Auto", "b": "Kinderkonto", "from_date": "all"}]})
        self.assertEqual([s for s in ("investing", "financing") if rows(after["Muster GbR"], s)], ["investing"])
        for data in (before, after):
            self.assertAddsUp(data)


class MockData(Reconciles):
    def test_every_month_of_the_sample_adds_up(self):
        # the made-up sample of the end-to-end tests (loans with Kontor's bookings, participations, contributions)
        import tempfile
        import test_e2e as T
        from storage import Store, load_or_create_master_key
        d = tempfile.mkdtemp()
        store = Store(d, *load_or_create_master_key(d))
        cfg = core.merged_config(T.config_for_test(os.path.join(d, "B")))
        store.save("config.json", cfg); store.save("state.json", dict(T.ALL_NEW))
        T.reset_mock(); T.patch_today()
        core.run_once(store, cfg, T.TODAY, dry=False, force=True, bridge_factory=T.MockBridge)
        data = {b["area"]["name"]: b for b in store.load("dataset.json")["areas"].values()}
        self.assertEqual(len(data), 3)
        self.assertAddsUp(data)
        for ds in data.values():
            self.assertFalse([z["row"] for z in rows(ds, "unclear").values()], ds["area"]["name"])


class CashflowFuzz(Reconciles):
    """Random months of bookings across every kind of account: both checks add up -- with only the reasons that name
    themselves (money in transit over a month end, the category "Ignore")."""

    def world(self, rnd):
        txs, n = [], [0]

        def add(key, day, amount, **extra):
            n[0] += 1
            txs.append((n[0], key, day, round(amount, 2), extra))
            return n[0]
        start = date(2025, 11, 1)
        days = (TODAY - start).days
        for _ in range(rnd.randint(30, 90)):
            d = start + timedelta(days=rnd.randrange(days))
            gap = timedelta(days=rnd.choice([0, 0, 1, 2, 3]))
            amt = rnd.choice([12.5, 80, 250, 999.99, 1500, 4000])
            kind = rnd.randrange(14)
            if kind == 0:
                add("giro", d, amt * 3, cat="Gehalt")
            elif kind == 1:
                add("giro", d, -amt, cat=rnd.choice(["Lebensmittel", "Wohnen\\Miete", ""]))
            elif kind == 2:                                         # bank to bank, maybe over a month end
                add("giro", d, -amt, iban="DE12", cat=rnd.choice(["Umbuchung", ""]))
                add("tg", d + gap, amt, iban="DE11")
            elif kind == 3:                                         # repayment to the bank loan
                add("giro", d, -amt, iban="DE13", cat="Umbuchung")
                add("darl", d + gap, amt, iban="DE11")
                add("darl", d + gap, -round(amt * 0.2, 2), purpose="Zinsen")
            elif kind == 4:                                         # Kontor's repayment of an offline loan
                pid = add("kk", d, -amt, iban="DE99", cat="Umbuchung")
                add("vd", d, amt, purpose="Annuität · #kontor-tx-%d" % pid, cat="Umbuchung")
                add("vd", d, -round(amt * 0.3, 2), purpose="Zinsen · #kontor-zins-%s" % d.strftime("%Y-%m"))
            elif kind == 5:                                         # contribution to the company (and back)
                s = rnd.choice([1, -1])
                add("giro", d, -s * amt, iban="DE21", cat=rnd.choice(["Umbuchung", ""]))
                add("kk", d + gap, s * amt, iban="DE11")
            elif kind == 6:                                         # Kontor's value adjustment of the participation
                add("stake", d, rnd.choice([1, -1]) * amt, purpose="Wertanpassung · #kontor-wert-%s-1" % d.strftime("%Y%m%d"),
                    cat=rnd.choice(["Umbuchung", ""]))
            elif kind == 7:                                         # by hand into an offline account, paired by amount
                add("giro", d, -amt, name="Freund")
                add(rnd.choice(["ford", "kredit", "auto"]), d + gap, amt, name="Freund")
            elif kind == 8:                                         # a transfer nobody booked on the other side
                add("giro", d, -amt, cat="Umbuchung")
            elif kind == 9:
                add("giro", d, -amt, cat="Lebensmittel", booked=False)
            elif kind == 10:                                        # to the children's area
                add("giro", d, -amt, iban="DE31", cat="Umbuchung")
                add("kind", d + gap, amt, iban="DE11", cat="Umbuchung")
            elif kind == 11:                                        # foreign currency
                add("giro", d, -amt, iban="DE14", cat="Umbuchung")
                add("usd", d + gap, amt * 1.1, iban="DE11")
            elif kind == 12:
                add("giro", d, -amt, cat="Privatentnahme")          # ignored category
            else:
                add("kk", d, amt * 2, cat="Miete")
        return txs

    def test_random_months_add_up(self):
        seeds = int(os.environ.get("KONTOR_FUZZ_SEEDS") or 40)
        cfg = {"companies": [{"area": "Muster GbR", "participation": "Beteiligung an Muster GbR"}],
               "cashflow": {"positions": {"Privatentnahme": "ignore"}}}
        for seed in range(seeds):
            with self.subTest(seed=seed):
                txs = self.world(random.Random(seed))
                data = build(txs, cfg)
                self.assertAddsUp(data, allow=("ue_unterwegs", "ue_ignoriert"))
                # income and expenses never pair with anything: their rows are exactly their bookings
                p, k = rows(data["Privat"]), rows(data["Kinder"])
                for cat, pos in (("Gehalt", "Arbeitseinkommen"), ("Lebensmittel", "Lebenshaltung"), ("Wohnen\\Miete", "Wohnen")):
                    want = round(sum(e[3] for e in txs if (e[4] or {}).get("cat") == cat and (e[4] or {}).get("booked", True)), 2)
                    got = round(sum(p[pos]["amounts"].values()), 2) if pos in p else 0.0
                    self.assertAlmostEqual(got, want, 2, cat)
                    det = {d["category"]: d for d in (p[pos].get("details") or [])} if pos in p else {}
                    self.assertAlmostEqual(round(sum(det[cat.replace("\\", " / ")]["amounts"].values()), 2) if det else 0.0, want, 2)
                # between two areas: what one pays in, the other receives
                out = round(sum(p["Einlage/Entnahme Kinder"]["amounts"].values()), 2) if "Einlage/Entnahme Kinder" in p else 0.0
                inn = round(sum(k["Einlage/Entnahme Privat"]["amounts"].values()), 2) if "Einlage/Entnahme Privat" in k else 0.0
                self.assertAlmostEqual(out, -inn, 2)


if __name__ == "__main__":
    unittest.main()
