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
    "giro": ("Giro", "Privat", "liquiditaet", "DE11", "bank"),
    "tg": ("Tagesgeld", "Privat", "liquiditaet", "DE12", "bank"),
    "darl": ("Darlehen Hausbau", "Privat", "verbindlichkeiten", "DE13", "bank"),
    "kredit": ("Privatkredit", "Privat", "verbindlichkeiten", None, "offline"),
    "ford": ("Darlehen an Freund", "Privat", "forderungen", None, "offline"),
    "auto": ("Auto", "Privat", "sachwerte", None, "offline"),
    "stake": ("Beteiligung an Muster GbR", "Privat", "beteiligungen", None, "offline"),
    "usd": ("Dollarkonto", "Privat", "liquiditaet", "DE14", "bank"),
    "depot": ("Depot", "Privat", "wertpapiere", "DE15", "portfolio"),
    "kk": ("Kontokorrent", "Muster GbR", "liquiditaet", "DE21", "bank"),
    "vd": ("Verkäuferdarlehen", "Muster GbR", "verbindlichkeiten", None, "offline"),
    "kap": ("Kapitalkonto", "Muster GbR", "eigenkapital", None, "offline"),
    "kind": ("Kinderkonto", "Kinder", "liquiditaet", "DE31", "bank"),
}


def build(txs, cfg=None, currency=None):
    """A ledger with three areas (groups) and the bookings [(id, key, day, amount, dict(extra))]; balance = sum of the booked."""
    return datasets(make_ledger(txs, currency), cfg)


def make_ledger(txs, currency=None):
    currency = currency or {"usd": "USD"}
    raw, ind = [], {}
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
    config = core.merged_config(dict({"bilanz": {"rollen": {k: v[2] for k, v in ACCOUNTS.items()}}}, **(cfg or {})))
    roles = {k: v[2] for k, v in ACCOUNTS.items()}
    out = {}
    for b in core.bereiche_for(ledger, config):
        out[b["name"]] = report.build_dataset(ledger, config, {}, TODAY, b, roles)
    return out


def rows(ds, section=None):
    return {z["zeile"]: z for s in ds["kapitalfluss"]["sektionen"] if section in (None, s["name"]) for z in s["zeilen"]}


class Reconciles(unittest.TestCase):
    """Helpers: both checks add up, month by month."""

    def assertAddsUp(self, data, allow=()):
        for name, ds in data.items():
            for mk, u in ds["kapitalfluss"]["ueberleitung"].items():
                for check, why in (("unerklaert", "gruende"), ("abweichung_liq", "gruende_liq")):
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
        transit = next(r for r in p["bilanz"]["zeilen"] if r["id"] == "transit")
        self.assertEqual(transit["werte"]["2026-01"], 500.0)
        self.assertEqual(transit["werte"]["2026-02"], 0.0)

    def test_loan_payment_over_month_end_names_the_reason(self):
        data = build([(1, "giro", date(2025, 12, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 1, 31), -1500.0, {"iban": "DE13", "cat": "Umbuchung"}),
                      (3, "darl", date(2026, 2, 1), 1500.0, {"iban": "DE11", "cat": "Umbuchung"}),
                      (4, "darl", date(2026, 2, 1), -400.0, {"purpose": "Zinsen"}),
                      (5, "giro", date(2026, 3, 1), -50.0, {"cat": "Lebensmittel"})])
        p = data["Privat"]
        self.assertAddsUp(data, allow=("ue_unterwegs",))
        r = rows(p, "Finanzierung")
        self.assertEqual(r["Darlehen Hausbau / Tilgung"]["werte"]["2026-01"], -1500.0)
        self.assertFalse(r["Darlehen Hausbau / Tilgung"]["nw"])
        self.assertEqual(r["Darlehen Hausbau / Zinsen"]["werte"]["2026-02"], -400.0)
        ue = p["kapitalfluss"]["ueberleitung"]
        self.assertEqual(ue["2026-01"]["gruende_liq"], [["ue_unterwegs", 1500.0, ""]])
        self.assertEqual(ue["2026-02"]["gruende_liq"], [["ue_unterwegs", -1500.0, ""]])

    def test_kontor_repayment_is_matched_to_the_payment(self):
        # the payment goes to the seller (no own IBAN); Kontor books the repayment and the interest in the offline loan
        data = build([(1, "kk", date(2026, 1, 3), 9500.0, {"cat": "Miete"}),
                      (2, "kk", date(2026, 2, 1), -8250.0, {"iban": "DE99", "cat": "Umbuchung"}),
                      (3, "vd", date(2026, 2, 1), 8250.0, {"purpose": "Annuität · #kontor-tx-2", "cat": "Umbuchung"}),
                      (4, "vd", date(2026, 2, 28), -4400.0, {"purpose": "Zinsen 02/2026 · #kontor-zins-2026-02", "cat": "Zinsen"})])
        g = data["Muster GbR"]
        self.assertAddsUp(data)
        r = rows(g)
        self.assertNotIn("Unklar", [s["name"] for s in g["kapitalfluss"]["sektionen"] if s["zeilen"]])
        self.assertEqual(r["Verkäuferdarlehen / Tilgung"]["werte"]["2026-02"], -3850.0)
        self.assertEqual(r["Verkäuferdarlehen / Zinsen"]["werte"]["2026-02"], -4400.0)

    def test_contribution_into_a_company_and_its_participation(self):
        cfg = {"gesellschaften": [{"bereich": "Muster GbR", "beteiligung": "Beteiligung an Muster GbR"}]}
        data = build([(1, "giro", date(2026, 1, 5), 30000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 10), -10000.0, {"iban": "DE21", "cat": "Umbuchung"}),
                      (3, "kk", date(2026, 2, 10), 10000.0, {"iban": "DE11"}),
                      (4, "stake", date(2026, 2, 28), 4900.0, {"purpose": "Wertanpassung · #kontor-wert-20260228-1"})], cfg)
        self.assertAddsUp(data)
        p, g = rows(data["Privat"]), rows(data["Muster GbR"])
        self.assertEqual(p["Einlage/Entnahme Muster GbR"]["werte"]["2026-02"], -10000.0)
        self.assertFalse(p["Einlage/Entnahme Muster GbR"]["nw"])
        self.assertEqual(p["Beteiligung an Muster GbR"]["werte"]["2026-02"], -5100.0)        # 4,900 worth for 10,000 paid in
        self.assertEqual(g["Einlagen/Entnahmen Gesellschafter"]["werte"]["2026-02"], 10000.0)
        self.assertTrue(g["Einlagen/Entnahmen Gesellschafter"]["nw"])
        self.assertEqual(g["Einlagen/Entnahmen Gesellschafter"]["lbl"], ["cf_einlagen_gesellschafter"])

    def test_without_participation_a_contribution_leaves_the_net_worth(self):
        data = build([(1, "giro", date(2026, 1, 5), 30000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 10), -10000.0, {"iban": "DE21"}),
                      (3, "kk", date(2026, 2, 10), 10000.0, {"iban": "DE11"})],
                     {"gesellschaften": [{"bereich": "Muster GbR", "gegenkonten": [{"konto": "Darlehen an Freund", "quelle": "Verkäuferdarlehen"}]}]})
        self.assertAddsUp(data)
        self.assertTrue(rows(data["Privat"])["Einlage/Entnahme Muster GbR"]["nw"])

    def test_transfer_to_another_area(self):
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -200.0, {"iban": "DE31", "cat": "Umbuchung"}),
                      (3, "kind", date(2026, 2, 3), 200.0, {"iban": "DE11", "cat": "Umbuchung"})])
        self.assertAddsUp(data)
        self.assertEqual(rows(data["Privat"])["Einlage/Entnahme Kinder"]["werte"]["2026-02"], -200.0)
        self.assertEqual(rows(data["Kinder"])["Einlage/Entnahme Privat"]["werte"]["2026-02"], 200.0)
        for ds in data.values():
            self.assertNotIn("Ausgaben", [s["name"] for s in ds["kapitalfluss"]["sektionen"] if s["zeilen"] and s["name"] != "Einnahmen"])

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
        self.assertEqual((p["Arbeitseinkommen"]["werte"]["2026-02"], p["Wohnen"]["werte"]["2026-02"]), (4000.0, -900.0))
        self.assertEqual(p["Einlage/Entnahme Muster GbR"]["werte"]["2026-02"], -550.0)          # only what was paid for nothing
        self.assertEqual((g["Personal"]["werte"]["2026-02"], g["Vermietung"]["werte"]["2026-02"]), (-4000.0, 900.0))   # by its words (estimated)
        self.assertEqual(g["Personal"]["details"][0]["kategorie"], "")
        self.assertEqual(g["Einlagen/Entnahmen Gesellschafter"]["werte"]["2026-02"], 550.0)
        # a category that does not clearly name income or an expense ("Einlage", anything unknown), and the name of your own
        # company ("Zahnarztpraxis", "Hotel"), change nothing: a contribution or withdrawal -- unless you chose a position
        txs = [(1, "giro", date(2026, 2, 3), -10000.0, {"iban": "DE21", "cat": "Einlage", "name": "Hotel Muster GbR"}),
               (2, "kk", date(2026, 2, 3), 10000.0, {"iban": "DE11", "cat": "Privat\\Entnahmen und Einlagen", "name": "Zahnarzt"}),
               (3, "kk", date(2026, 2, 5), -5000.0, {"iban": "DE11", "name": "Zahnarztpraxis Inhaber"}),
               (4, "giro", date(2026, 2, 5), 5000.0, {"iban": "DE21", "name": "Hotel Muster GbR"})]
        data = build(txs)
        self.assertAddsUp(data)
        p, g = rows(data["Privat"]), rows(data["Muster GbR"])
        self.assertEqual(p["Einlage/Entnahme Muster GbR"]["werte"]["2026-02"], -5000.0)
        self.assertEqual(g["Einlagen/Entnahmen Gesellschafter"]["werte"]["2026-02"], 5000.0)
        self.assertFalse({"Sonstige Ausgaben", "Sonstige Einnahmen", "Erstattungen", "Freizeit & Reisen"} & (set(p) | set(g)))
        data = build(txs, {"kapitalfluss": {"positionen": {"Einlage": "sonstige_ausgaben"}}})
        self.assertEqual(rows(data["Privat"])["Sonstige Ausgaben"]["werte"]["2026-02"], -10000.0)
        # the same category on both sides: income for one area, an expense for the other (the direction within the area)
        data = build([(1, "kk", date(2026, 2, 3), -4000.0, {"iban": "DE11", "cat": "Gehalt"}), (2, "giro", date(2026, 2, 3), 4000.0, {"iban": "DE21", "cat": "Gehalt"}),
                      (3, "kk", date(2026, 2, 4), -9000.0, {"cat": "Gehalt", "name": "Mitarbeiter"}),
                      (4, "giro", date(2026, 2, 5), -300.0, {"iban": "DE21", "purpose": "Zinsen Darlehen"}), (5, "kk", date(2026, 2, 5), 300.0, {"iban": "DE11", "purpose": "Zinsen Darlehen"})])
        self.assertAddsUp(data)
        p, g = rows(data["Privat"]), rows(data["Muster GbR"])
        self.assertEqual((p["Arbeitseinkommen"]["werte"]["2026-02"], g["Personal"]["werte"]["2026-02"]), (4000.0, -13000.0))
        self.assertEqual((p["Zinsen"]["werte"]["2026-02"], g["Kapitalerträge"]["werte"]["2026-02"]), (-300.0, 300.0))

    def test_transfers_need_no_category(self):
        import categorize as C
        txs = [(1, "giro", date(2026, 2, 3), -200.0, {"iban": "DE12"}), (2, "tg", date(2026, 2, 3), 200.0, {"iban": "DE11"}),
               (3, "giro", date(2026, 2, 5), -700.0, {"name": "Freund"}), (4, "ford", date(2026, 2, 6), 700.0, {"name": "Freund"}),
               (5, "giro", date(2026, 2, 8), -30.0, {"name": "Laden"})]
        txs += [(6, "giro", date(2026, 2, 9), -400.0, {"iban": "DE21"}), (7, "kk", date(2026, 2, 9), 400.0, {"iban": "DE11"})]   # to another area
        led = make_ledger(txs)
        datasets(led)                                                        # the report finds the counter-booking in the manual account
        banks = {k for k, v in ACCOUNTS.items() if v[2] == "liquiditaet"}
        area_of = {k: v[1] for k, v in ACCOUNTS.items()}
        off = C.open_items(C.empty(), led, area_of, banks=banks)
        # between two areas a category matters (salary or contribution?): those stay in the list
        self.assertEqual(sorted(i for g in off["gruppen"] for i in g["ids"]), [5, 6, 7])
        self.assertEqual(C.stats(C.empty(), led, banks, area_of)["gesamt"], {"ohne": 3})
        self.assertEqual({u["konto"] for g in off["gruppen"] for u in g["umsaetze"]}, {"Giro", "Kontokorrent"})

    def test_offline_booking_paired_by_amount(self):
        # a loan to a friend: paid from the bank account, booked by hand in the offline receivable two days later
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -700.0, {"name": "Freund"}),
                      (3, "ford", date(2026, 2, 5), 700.0, {"name": "Freund"}),
                      (4, "giro", date(2026, 2, 6), -700.0, {"cat": "Lebensmittel"}),           # an expense never pairs
                      (5, "auto", date(2026, 2, 7), 700.0, {"purpose": "Zuschreibung"})])
        self.assertAddsUp(data)
        r = rows(data["Privat"])
        self.assertEqual(r["Darlehen an Freund / Rückzahlung"]["werte"]["2026-02"], -700.0)
        self.assertEqual(r["Lebenshaltung"]["werte"]["2026-02"], -700.0)
        self.assertEqual(r["Auto"]["werte"]["2026-02"], 700.0)

    def test_pending_refund_and_missing_counterpart(self):
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -100.0, {"cat": "Lebensmittel"}),
                      (3, "giro", date(2026, 2, 9), 30.0, {"cat": "Lebensmittel", "name": "Erstattung"}),
                      (4, "giro", date(2026, 6, 19), -999.0, {"cat": "Lebensmittel", "booked": False}),     # pending: not yet
                      (5, "giro", date(2026, 3, 2), -250.0, {"iban": "DE12"}),                              # Tagesgeld: missing
                      (6, "giro", date(2026, 3, 4), -80.0, {"cat": "Umbuchung"})])                          # no counterpart
        self.assertAddsUp(data)
        r = rows(data["Privat"])
        self.assertEqual(r["Lebenshaltung"]["werte"]["2026-02"], -70.0)
        self.assertEqual(r["Lebenshaltung"]["werte"]["2026-06"], 0.0)
        self.assertEqual(r["Umbuchung nach Tagesgeld ohne Gegenbuchung"]["werte"]["2026-03"], -250.0)
        self.assertEqual(r["Umbuchung ohne erkannten Partner"]["werte"]["2026-03"], -80.0)
        self.assertTrue(any("Umbuchung" in w for w in data["Privat"]["warnungen"]))

    def test_foreign_currency_is_kept_apart(self):
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -1000.0, {"iban": "DE14", "cat": "Umbuchung"}),
                      (3, "usd", date(2026, 2, 4), 1080.0, {"iban": "DE11", "cat": "Umbuchung"}),
                      (4, "usd", date(2026, 3, 4), -40.0, {"cat": "Reisen"})])
        p = data["Privat"]
        self.assertAddsUp(data)
        self.assertEqual(rows(p)["Fremdwährung Dollarkonto"]["werte"]["2026-02"], -1000.0)
        self.assertNotIn("Reisen", rows(p))
        self.assertEqual(p["bilanz"]["nettovermoegen"]["2026-03"], 2000.0)
        out = [r for r in p["bilanz"]["ausserhalb"] if r["rolle"] == "fremdwaehrung"]
        self.assertEqual([(r["name"], r["waehrung"], r["werte"]["2026-03"]) for r in out], [("Dollarkonto", "USD", 1040.0)])
        self.assertTrue(any("Dollarkonto (USD)" in w for w in p["warnungen"]))

    def test_ignored_category_is_a_named_reason(self):
        cfg = {"kapitalfluss": {"positionen": {"Privatentnahme": "ignorieren"}}}
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -300.0, {"cat": "Privatentnahme"})], cfg)
        self.assertAddsUp(data, allow=("ue_ignoriert",))
        u = data["Privat"]["kapitalfluss"]["ueberleitung"]["2026-02"]
        self.assertEqual(u["gruende"], [["ue_ignoriert", -300.0, ""]])
        self.assertEqual(u["gruende_liq"], [["ue_ignoriert", -300.0, ""]])

    def test_labels_are_translated(self):
        import i18n
        data = build([(1, "kk", date(2026, 1, 3), 9500.0, {"cat": "Miete"}),
                      (2, "vd", date(2026, 2, 28), -4400.0, {"purpose": "Zinsen · #kontor-zins-2026-02"})])
        z = rows(data["Muster GbR"])["Verkäuferdarlehen / Zinsen"]
        self.assertEqual((z["lbl"], z["glbl"], z["gruppe"]), (["cf_name", "Verkäuferdarlehen"], ["cf_g_zinsen"], "Zinsen"))     # the loan, in the group "Zinsen"
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
        self.assertEqual(r["Einlage/Entnahme Kinder"]["werte"]["2026-02"], -200.0)
        self.assertEqual(r["Auto"]["werte"]["2026-02"], 200.0)
        self.assertNotIn("Investitionen", [s["name"] for s in data["Privat"]["kapitalfluss"]["sektionen"]
                                           if any(z["konto"] == "auto" for z in s["zeilen"])])

    def test_payment_into_a_depot_valued_by_its_balances(self):
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2026, 2, 3), -1000.0, {"iban": "DE15"})])
        self.assertAddsUp(data)
        r = rows(data["Privat"], "Investitionen")
        self.assertEqual(r["Depot"]["werte"]["2026-02"], -1000.0)
        self.assertFalse(r["Depot"]["nw"])
        self.assertFalse(rows(data["Privat"], "Unklar"))

    def test_no_money_in_transit_without_a_bank_account(self):
        data = build([(1, "giro", date(2025, 12, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "kredit", date(2026, 1, 31), -10000.0, {"cat": "Umbuchung"}),
                      (3, "auto", date(2026, 2, 2), 10000.0, {"cat": "Umbuchung"})])
        p = data["Privat"]
        self.assertAddsUp(data)
        self.assertFalse([r for r in p["bilanz"]["zeilen"] if r["id"] == "transit"])
        liq = next(r for r in p["bilanz"]["zeilen"] if r["id"] == "pos:liquiditaet")
        self.assertEqual(liq["werte"]["2026-01"], 3000.0)

    def test_account_moved_into_the_company(self):
        cfg = {"gesellschaften": [{"bereich": "Muster GbR", "beteiligung": "Beteiligung an Muster GbR"}],
               "bilanz": {"rollen": {k: v[2] for k, v in ACCOUNTS.items()}, "konten_zuordnung": {"Kinderkonto": {"bereich": "g-Muster GbR"}}}}
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
        self.assertEqual(r["Einlage/Entnahme Muster GbR"]["werte"]["2026-02"], -10500.0)
        self.assertFalse(r["Einlage/Entnahme Muster GbR"]["nw"])

    def test_both_sides_naming_each_other_may_be_a_week_apart(self):
        data = build([(1, "giro", date(2025, 11, 5), 3000.0, {"cat": "Gehalt"}),
                      (2, "giro", date(2025, 12, 22), -500.0, {"iban": "DE12"}),
                      (3, "tg", date(2025, 12, 28), 500.0, {"iban": "DE11"})])
        self.assertAddsUp(data)
        self.assertFalse(rows(data["Privat"], "Unklar"))
        self.assertFalse([w for w in data["Privat"]["warnungen"] if "Umbuchung" in w])


    def test_a_missing_booking_does_not_shift_a_recurring_transfer(self):
        txs, n, d = [(1, "giro", date(2025, 12, 1), 5000.0, {"cat": "Gehalt"})], 10, date(2026, 1, 6)
        while d < date(2026, 3, 10):                    # every week to the savings account; one booking there is missing
            n += 1; txs.append((n, "giro", d, -100.0, {"iban": "DE12"}))
            if d != date(2026, 1, 13):
                n += 1; txs.append((n, "tg", d, 100.0, {"iban": "DE11"}))
            d += timedelta(days=7)
        data = build(txs)
        self.assertAddsUp(data)
        r = rows(data["Privat"], "Unklar")
        self.assertEqual({k: {m: v for m, v in z["werte"].items() if v} for k, z in r.items()},
                         {"Umbuchung nach Tagesgeld ohne Gegenbuchung": {"2026-01": -100.0}})
        self.assertFalse([x for x in data["Privat"]["bilanz"]["zeilen"] if x["id"] == "transit"])


class Positions(Reconciles):
    """Income and expenses by Kontor's fixed outline; MoneyMoney's categories inside, assigned once (proposed by name)."""

    def test_proposals_by_name_and_direction(self):
        import report as R
        cases = {("Einkommen / Gehälter", True): "arbeit", ("Einkommen / Tantieme", True): "arbeit",
                 ("Einkommen / Rückzahlung Finanzamt", True): "erstattungen", ("Einkommen / Zinsen", True): "kapitalertraege",
                 ("Sparen / Unternehmenskauf", False): "anlegen", ("Wohnen / Miete", False): "wohnen", ("Mieteinnahmen", True): "vermietung",
                 ("Vermietung / Parkweg / Hausgeld", False): "objektkosten", ("Steuern / Einkommensteuer", False): "steuern",
                 ("Versicherungen / Kfz-Versicherung", False): "versicherungen", ("Steuerberater", False): "verwaltung",
                 ("Kredit / Zinsen", False): "zinsen", ("Lebensmittel", False): "lebenshaltung", ("Irgendwas", True): "sonstige_einnahmen",
                 ("Irgendwas", False): "sonstige_ausgaben", ("Immobilienkauf", False): "anlegen", ("Beteiligung", False): "anlegen",
                 ("Finanzierung", False): "tilgung", ("Vermietung / Parkweg / Zinsen", False): "zinsen", ("Geldautomat", False): "sonstige_ausgaben",
                 ("Krankenkasse", True): "erstattungen", ("Sparkasse", False): "sonstige_ausgaben", ("Laborkosten", False): "sonstige_ausgaben",
                 ("Gehälter", False): "personal", ("Abos", False): "freizeit", ("Wareneinkauf", False): "wareneinkauf"}
        for (path, inc), want in cases.items():
            self.assertEqual(R.propose_position(path, inc), want, path)

    def test_every_position_has_its_text(self):
        import json
        import report as R
        txt = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "i18n.js"), encoding="utf-8").read()
        cat = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        self.assertFalse([k for k, _s, _r in R.POSITIONS + [("umbuchung", "", ""), ("einnahmen", "", ""), ("ausgaben", "", "")] if "pos_" + k not in cat])

    def test_your_choice_counts_for_the_category_and_below(self):
        cfg = {"kapitalfluss": {"positionen": {"Einkommen": "arbeit", "Einkommen / Zinsen": "kapitalertraege", "Sparen": "anlegen"}}}
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Einkommen\\Gehälter"}),
                      (2, "giro", date(2026, 2, 5), 500.0, {"cat": "Einkommen\\Tantieme"}),
                      (3, "giro", date(2026, 2, 6), 12.0, {"cat": "Einkommen\\Zinsen"}),
                      (4, "giro", date(2026, 2, 7), -800.0, {"cat": "Sparen\\Unternehmenskauf"}),
                      (5, "giro", date(2026, 2, 8), -40.0, {"cat": "Haushalt\\Drogerie"})], cfg)
        self.assertAddsUp(data)
        r = rows(data["Privat"])
        self.assertEqual(r["Arbeitseinkommen"]["werte"]["2026-02"], 500.0)
        self.assertEqual({d["kategorie"] for d in r["Arbeitseinkommen"]["details"]}, {"Einkommen / Gehälter", "Einkommen / Tantieme"})
        self.assertEqual(r["Kapitalerträge"]["werte"]["2026-02"], 12.0)
        self.assertEqual(r["Sparen / Unternehmenskauf"]["gruppe"], "Wertpapiere & Geldanlagen")  # saving: no expense, an investment
        self.assertEqual(r["Lebenshaltung"]["werte"]["2026-02"], -40.0)                         # proposed by name
        order = [z["zeile"] for z in data["Privat"]["kapitalfluss"]["sektionen"][0]["zeilen"]]
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
        self.assertEqual(g["Umsatzerlöse"]["werte"]["2026-02"], 9500.0)
        self.assertEqual(g["Umsatzerlöse"]["details"][0]["kategorie"], "")                    # estimated
        self.assertEqual((g["Personal"]["werte"]["2026-02"], g["Umsatzsteuer"]["werte"]["2026-02"]), (-800.0, -3100.0))
        self.assertEqual(g["Ohne Kategorie"]["werte"]["2026-02"], -50.0)
        p = rows(data["Privat"])
        self.assertEqual((p["Versicherungen"]["werte"]["2026-02"], p["Arbeitseinkommen"]["werte"]["2026-02"]), (-60.0, 4000.0))

    def test_words_of_a_booking(self):
        import report as R
        from model import Tx
        def g(name, purpose, amount, company):
            return R.guess_position(Tx(id=1, account_uuid="x", booking_date=date(2026, 1, 1), value_date=date(2026, 1, 1), amount=amount, currency="EUR", name=name, purpose=purpose), company)
        self.assertIsNone(g("Muster GmbH Gesellschafter", "Gewinnausschüttung 2025", -50000.0, True))       # equity, no expense
        self.assertEqual(g("Finanzamt Mitte", "KapESt Gewinnausschüttung", -9000.0, True), "steuern")
        self.assertEqual(g("Finanzamt Mitte", "LSt 10/2026", -41000.0, True), "personal")                  # wage tax: staff costs
        self.assertEqual(g("Finanzamt Mitte", "USt-VA 10/2026", -23000.0, True), "umsatzsteuer")
        self.assertEqual(g("Finanzamt Mitte", "Erstattung USt 09/2026", 1200.0, True), "umsatzsteuer")
        self.assertEqual(g("Finanzamt Mitte", "ESt-Vorauszahlung", -3000.0, False), "steuern")
        self.assertEqual(g("Stadtwerke", "Strom Filiale 4", -900.0, True), "wohnen")                       # shown as "Raumkosten"
        self.assertEqual(g("Telekom", "Rechnung", -60.0, True), "betrieb")
        self.assertIsNone(g("Grosshandel Nord", "RE 4711 Umsatzsteuer 19 % Steuernummer 123", -500.0, True))
        self.assertEqual(g("Max Muster", "Lohn 02/2026", -2100.0, True), "personal")
        self.assertIsNone(g("Bank", "Darlehen Zins und Tilgung", -1500.0, False))                       # mixed: no estimate
        self.assertEqual(g("Bank", "Sollzinsen 4. Quartal", -80.0, False), "zinsen")
        self.assertEqual(g("Nexi Germany", "Kartenumsätze", 900.0, True), "umsatz")
        self.assertIsNone(g("Nexi Germany", "Kartenumsätze", 900.0, False))

    def test_an_estimate_is_never_saving_or_repayment(self):
        import categorize as C
        txs = [(1, "giro", date(2026, 1, 5), -100.0, {"name": "Broker AG", "cat": "Sparen\\ETF"}),
               (2, "giro", date(2026, 1, 9), -100.0, {"name": "Broker AG", "cat": "Sparen\\ETF"}),
               (3, "giro", date(2026, 2, 9), -5000.0, {"name": "Broker AG", "purpose": "Rechnung"})]
        led = make_ledger(txs)
        d = C.empty(); C.learn(d, led)
        config = core.merged_config({"bilanz": {"rollen": {k: v[2] for k, v in ACCOUNTS.items()}}})
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
        r = rows(report.build_dataset(led, config, {}, TODAY, b, {k: v[2] for k, v in ACCOUNTS.items()}, learned=d))
        self.assertEqual(r["Ohne Kategorie"]["werte"]["2026-02"], -5000.0)
        self.assertEqual(r["Sparen / ETF"]["werte"].get("2026-02", 0.0), 0.0)

    def test_target_account_counts_below_too(self):
        cfg = {"kapitalfluss": {"kategorie_zu_konto": {"Sparen": "Auto"}}}
        data = build([(1, "giro", date(2026, 2, 5), -400.0, {"cat": "Sparen\\Bausparvertrag"})], cfg)
        self.assertAddsUp(data)
        z = rows(data["Privat"])["Sparen / Bausparvertrag"]
        self.assertEqual((z["konto"], z["nw"]), ("auto", False))

    def test_learned_from_transfers_is_no_estimate(self):
        import categorize as C
        txs = [(1, "giro", date(2026, 1, 5), -100.0, {"name": "Ich", "cat": "Umbuchung"}), (2, "giro", date(2026, 1, 9), -100.0, {"name": "Ich", "cat": "Umbuchung"}),
               (3, "giro", date(2026, 2, 9), -700.0, {"name": "Ich"})]
        led = make_ledger(txs)
        d = C.empty(); C.learn(d, led)
        config = core.merged_config({"bilanz": {"rollen": {k: v[2] for k, v in ACCOUNTS.items()}}})
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
        r = rows(report.build_dataset(led, config, {}, TODAY, b, {k: v[2] for k, v in ACCOUNTS.items()}, learned=d))
        self.assertEqual(r["Ohne Kategorie"]["werte"]["2026-02"], -700.0)

    def test_property_keeps_its_reserve_unless_you_choose(self):
        im = [{"id": "i1", "name": "Parkweg", "bereich": "g-Muster GbR", "kategorie": "Vermietung\\Parkweg"}]
        txs = [(1, "kk", date(2026, 2, 3), 1000.0, {"cat": "Vermietung\\Parkweg\\Miete"}),
               (2, "kk", date(2026, 2, 4), -100.0, {"cat": "Vermietung\\Parkweg\\Rücklage"})]
        g = rows(build(txs, {"immobilien": im})["Muster GbR"])
        self.assertEqual(g["Parkweg · Kosten"]["werte"]["2026-02"], -100.0)                           # proposal "saving" does not count here
        data = build(txs, {"immobilien": im, "kapitalfluss": {"positionen": {"Vermietung / Parkweg / Rücklage": "anlegen"}}})
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
        self.assertFalse(R.transfer_check(core.merged_config({"kapitalfluss": {"positionen": {"Übertrag": "sonstige_ausgaben"}}}))("Übertrag"))

    def test_transfer_follows_your_choice(self):
        cfg = {"kapitalfluss": {"positionen": {"Haushalt": "lebenshaltung", "Umbuchung / Sparplan": "sonstige_ausgaben"}}}
        data = build([(1, "giro", date(2026, 2, 5), -30.0, {"cat": "Haushalt\\Umbuchung"}),
                      (2, "giro", date(2026, 2, 6), -40.0, {"cat": "Umbuchung\\Sparplan"}),
                      (3, "giro", date(2026, 2, 7), -50.0, {"cat": "Umbuchung\\Sonstiges"})], cfg)
        self.assertAddsUp(data)
        r = rows(data["Privat"])
        self.assertEqual(r["Lebenshaltung"]["werte"]["2026-02"], -30.0)
        self.assertEqual(r["Sonstige Ausgaben"]["werte"]["2026-02"], -40.0)
        self.assertEqual(r["Umbuchung ohne erkannten Partner"]["werte"]["2026-02"], -50.0)            # still a transfer by its parent

    def test_old_sections_become_positions(self):
        cfg = core.merged_config({"kapitalfluss": {"kategorie_zuordnung": {"Altersvorsorge": "Investitionen", "Gehalt": "Einnahmen", "Privat": "Ignorieren"}}})
        self.assertEqual(cfg["kapitalfluss"]["positionen"], {"Altersvorsorge": "anlegen", "Privat": "ignorieren"})
        self.assertNotIn("kategorie_zuordnung", cfg["kapitalfluss"])

    def test_same_position_named_for_a_company(self):
        data = build([(1, "kk", date(2026, 2, 3), -4000.0, {"name": "Vermieter", "purpose": "Miete Laden Februar"}),
                      (2, "giro", date(2026, 2, 3), -1200.0, {"name": "Vermieter", "purpose": "Miete Februar"})])
        self.assertEqual(rows(data["Muster GbR"])["Raumkosten"]["lbl"], ["pos_wohnen_g"])
        self.assertEqual(rows(data["Privat"])["Wohnen"]["werte"]["2026-02"], -1200.0)

    def test_totals_for_planning_and_reading(self):
        # gross profit only where there is revenue; after interest and repayment (a new loan is no income); bank balance
        txs = [(1, "kk", date(2026, 1, 3), 10000.0, {"name": "Nexi", "purpose": "Kartenumsaetze"}),
               (2, "kk", date(2026, 1, 4), -6000.0, {"cat": "Wareneinkauf"}),
               (3, "kk", date(2026, 1, 5), -500.0, {"name": "Bank", "purpose": "Sollzinsen"}),
               (4, "vd", date(2026, 1, 6), 300.0, {"name": "Kontokorrent"}), (5, "kk", date(2026, 1, 6), -300.0, {"name": "Verkäuferdarlehen"}),
               (6, "vd", date(2026, 2, 1), -20000.0, {"name": "Kontokorrent"}), (7, "kk", date(2026, 2, 1), 20000.0, {"name": "Verkäuferdarlehen"})]
        led = make_ledger(txs)
        config = core.merged_config({"bilanz": {"rollen": {k: v[2] for k, v in ACCOUNTS.items()}}})
        roles = {k: v[2] for k, v in ACCOUNTS.items()}
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Muster GbR")
        ds = report.build_dataset(led, config, {}, TODAY, b, roles)
        report.apply_plan(ds, {}, config)
        su = ds["kapitalfluss"]["summen"]
        self.assertEqual((su["2026-01"]["Rohertrag"], su["2026-01"]["Operativ"]), (4000.0, 4000.0))
        self.assertEqual(su["2026-01"]["Nach_Kapitaldienst"], 3200.0)                                  # minus interest and repayment
        self.assertEqual(su["2026-02"]["Nach_Kapitaldienst"], 0.0)                                     # the new loan does not count
        self.assertEqual((su["2026-01"]["Bankguthaben"], su["2026-02"]["Bankguthaben"]), (3200.0, 23200.0))
        # start + change = end, also with money in transit over a month end and with an account that comes later
        txs2 = [(1, "giro", date(2026, 1, 3), 5000.0, {"cat": "Gehalt"}), (2, "giro", date(2026, 2, 27), -1000.0, {"name": "Tagesgeld", "iban": "DE12"}),
                (3, "tg", date(2026, 3, 2), 1000.0, {"name": "Giro", "iban": "DE11"}), (4, "giro", date(2026, 4, 3), -50.0, {"cat": "Lebensmittel"})]
        led2 = make_ledger(txs2)
        ds2 = report.build_dataset(led2, config, {}, TODAY, next(x for x in core.bereiche_for(led2, config) if x["name"] == "Privat"), roles)
        report.apply_plan(ds2, {}, config)
        s2, ue = ds2["kapitalfluss"]["summen"], ds2["kapitalfluss"]["ueberleitung"]
        ms = sorted(m for m in s2 if m >= "2026-01")
        for prev, m in zip(ms, ms[1:]):
            if m in ue:
                self.assertAlmostEqual(s2[m]["Bankguthaben"] - s2[prev]["Bankguthaben"], s2[m]["Cashflow"], 2, m)
        self.assertEqual(s2["2026-01"]["Bankguthaben"], 5000.0)
        p = rows(build([(1, "giro", date(2026, 1, 3), 100.0, {"cat": "Gehalt"})])["Privat"])
        self.assertIn("Arbeitseinkommen", p)
        # Cashflow-Positionen proposes what each area counts: income for you, staff costs of the company (the area with more bookings first)
        both = make_ledger([(1, "giro", date(2026, 1, 3), 100.0, {"cat": "Gehalt"}), (2, "kk", date(2026, 1, 3), -100.0, {"cat": "Gehalt"}),
                            (3, "kk", date(2026, 2, 3), -100.0, {"cat": "Gehalt"})])
        row = next(r for r in core.positions_overview(both, config, [], TODAY)["kategorien"] if r["pfad"] == "Gehalt")
        self.assertEqual((row["vorschlag"], row["vorschlag_auch"]), ("personal", ["arbeit"]))
        dsp = report.build_dataset(make_ledger([(1, "giro", date(2026, 1, 3), 100.0, {"cat": "Gehalt"})]), config, {}, TODAY,
                                   next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat"), roles)
        report.apply_plan(dsp, {}, config)
        self.assertNotIn("Rohertrag", dsp["kapitalfluss"]["summen"]["2026-01"])

    def test_renamed_row_keeps_its_plan(self):
        led = make_ledger([(1, "giro", date(2026, 1, 3), 3000.0, {"cat": "Gehalt"})])
        config = core.merged_config({"bilanz": {"rollen": {k: v[2] for k, v in ACCOUNTS.items()}}})
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
        ds = report.build_dataset(led, config, {}, TODAY, b, {k: v[2] for k, v in ACCOUNTS.items()})
        report.apply_plan(ds, {"zeilen": {"Einnahmen/Arbeit": {"methode": "fix", "betrag": 7000}}}, config)
        z = rows(ds)["Arbeitseinkommen"]
        self.assertEqual(z["plan"]["methode"], "fix")
        self.assertEqual(set(z["plan"]["werte"].values()), {7000.0})

    def test_learned_patterns_come_before_words(self):
        import categorize as C
        txs = [(1, "giro", date(2026, 1, 5), -40.0, {"name": "Biomarkt", "cat": "Lebensmittel"}),
               (2, "giro", date(2026, 1, 9), -45.0, {"name": "Biomarkt", "cat": "Lebensmittel"}),
               (3, "giro", date(2026, 2, 9), -50.0, {"name": "Biomarkt", "purpose": "Versicherung"})]
        led = make_ledger(txs)
        d = C.empty(); C.learn(d, led)
        config = core.merged_config({"bilanz": {"rollen": {k: v[2] for k, v in ACCOUNTS.items()}}})
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
        ds = report.build_dataset(led, config, {}, TODAY, b, {k: v[2] for k, v in ACCOUNTS.items()}, learned=d)
        r = rows(ds)
        self.assertEqual(r["Lebenshaltung"]["werte"]["2026-02"], -50.0)                         # not "Versicherungen"
        self.assertEqual({x["kategorie"] for x in r["Lebenshaltung"]["details"]}, {"Lebensmittel", ""})

    def test_a_property_has_its_own_rows(self):
        cfg = {"immobilien": [{"id": "i1", "name": "Parkweg", "bereich": "g-Muster GbR", "kategorie": "Vermietung\\Parkweg"}]}
        data = build([(1, "kk", date(2026, 1, 3), 9500.0, {"cat": "Vermietung\\Parkweg\\Mieteinnahmen"}),
                      (2, "kk", date(2026, 2, 3), 9500.0, {"cat": "Vermietung\\Parkweg\\Mieteinnahmen"}),
                      (3, "kk", date(2026, 2, 4), -800.0, {"cat": "Vermietung\\Parkweg\\Hausgeld"})], cfg)
        self.assertAddsUp(data)
        g = rows(data["Muster GbR"])
        self.assertEqual((g["Parkweg · Miete"]["werte"]["2026-02"], g["Parkweg · Miete"]["objekt"]), (9500.0, "Parkweg"))
        self.assertEqual(g["Parkweg · Kosten"]["werte"]["2026-02"], -800.0)

    def test_property_rows_by_sign_and_the_most_specific_property(self):
        cfg = {"immobilien": [{"id": "i1", "name": "Altbau", "bereich": "g-Muster GbR", "kategorie": "Vermietung"},
                              {"id": "i2", "name": "Neubau", "bereich": "g-Muster GbR", "kategorie": "Vermietung\\Neubau"}]}
        data = build([(1, "kk", date(2026, 1, 3), 1500.0, {"cat": "Vermietung"}), (2, "kk", date(2026, 2, 3), 1500.0, {"cat": "Vermietung"}),
                      (3, "kk", date(2026, 2, 4), -4000.0, {"cat": "Vermietung"}), (4, "kk", date(2026, 2, 5), 900.0, {"cat": "Vermietung\\Neubau"}),
                      (5, "kk", date(2026, 2, 6), -300.0, {"cat": "Vermietung\\Neubau\\Zinsen"})], cfg)
        self.assertAddsUp(data)
        g = rows(data["Muster GbR"])
        self.assertEqual((g["Altbau · Miete"]["werte"]["2026-02"], g["Altbau · Kosten"]["werte"]["2026-02"]), (1500.0, -4000.0))
        self.assertEqual(g["Neubau · Miete"]["werte"]["2026-02"], 900.0)
        self.assertEqual(g["Zinsen"]["werte"]["2026-02"], -300.0)                                      # financing stays financing

    def test_budget_per_position(self):
        led = make_ledger([(1, "giro", date(2026, 1, 3), -100.0, {"cat": "Wohnen\\Strom/Gas"}), (2, "giro", date(2026, 1, 4), -900.0, {"cat": "Wohnen\\Miete"}),
                           (3, "giro", date(2026, 1, 5), -50.0, {"cat": "Lebensmittel\\Supermarkt"})])
        config = core.merged_config({"bilanz": {"rollen": {k: v[2] for k, v in ACCOUNTS.items()}}})
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
        r = rows(data["Privat"], "Finanzierung")
        self.assertEqual((r["Darlehen Hausbau / Aufnahme"]["gruppe"], r["Darlehen Hausbau / Aufnahme"]["werte"]["2026-02"]), ("Darlehensaufnahme", 400000.0))
        self.assertEqual(r["Darlehen Hausbau / Tilgung"]["werte"]["2026-02"], 0.0)
        self.assertEqual((r["Darlehen Hausbau / Tilgung"]["werte"]["2026-03"], r["Darlehen Hausbau / Zinsen"]["werte"]["2026-03"]), (-900.0, -600.0))
        self.assertEqual([z["gruppe"] for z in data["Privat"]["kapitalfluss"]["sektionen"][3]["zeilen"]], ["Darlehensaufnahme", "Tilgung", "Zinsen"])
        self.assertEqual(rows(data["Privat"], "Investitionen")["Depot"]["gruppe"], "Wertpapiere & Geldanlagen")
        config = core.merged_config({"bilanz": {"rollen": {k: v[2] for k, v in ACCOUNTS.items()}}})
        ds = data["Privat"]
        report.apply_plan(ds, {}, config)
        z = rows(ds, "Finanzierung")["Darlehen Hausbau / Aufnahme"]
        self.assertEqual(z["plan"]["methode"], "keine"); self.assertFalse(any(abs(v) > 0.005 for v in z["plan"]["werte"].values()))
        # a loan taken up in the plan raises the debt as much as the cash: net worth stays
        fut = sorted(ds["plan_monate"])[2]
        planned = build(txs)["Privat"]
        report.apply_plan(planned, {"zeilen": {"Finanzierung/Darlehen Hausbau / Aufnahme": {"werte": {fut: 100000.0}}}}, config)
        pp, p0 = planned["bilanz"]["projektion"], ds["bilanz"]["projektion"]
        self.assertAlmostEqual(pp["liquiditaet"][fut] - p0["liquiditaet"][fut], 100000.0, 2)
        self.assertAlmostEqual(pp["nettovermoegen"][fut], p0["nettovermoegen"][fut], 2)

    def test_saving_without_an_account_and_by_category(self):
        """Saving by a category without a known account is "saving" (not securities); a category row beside the loans of its
        group is "by category", an account named like its group keeps its name."""
        data = build([(1, "giro", date(2026, 3, 3), -500.0, {"cat": "Sparen"}), (2, "giro", date(2026, 3, 1), -300.0, {"cat": "Tilgung"}),
                      (3, "giro", date(2026, 3, 1), -1500.0, {"iban": "DE13"}), (4, "darl", date(2026, 3, 1), 1500.0, {"iban": "DE11"})],
                     {"kapitalfluss": {"positionen": {"Sparen": "anlegen", "Tilgung": "tilgung"}}})
        inv, fin = rows(data["Privat"], "Investitionen"), rows(data["Privat"], "Finanzierung")
        self.assertEqual(inv["Sparen"]["gruppe"], "Wertpapiere & Geldanlagen" if any(v[4] == "portfolio" for v in ACCOUNTS.values() if v[1] == "Privat") else "Sparen & Anlegen")
        self.assertEqual((fin["Tilgung"]["gruppe"], fin["Tilgung"]["lbl"]), ("Tilgung", ["cf_per_kategorie"]))
        self.assertEqual(fin["Darlehen Hausbau / Tilgung"]["lbl"], ["cf_name", "Darlehen Hausbau"])
        gbr = build([(1, "kk", date(2026, 3, 3), -500.0, {"cat": "Sparen"})], {"kapitalfluss": {"positionen": {"Sparen": "anlegen"}}})["Muster GbR"]
        self.assertEqual(rows(gbr, "Investitionen")["Sparen"]["gruppe"], "Sparen & Anlegen")       # no depot there: no account known


class OpeningBalance(Reconciles):
    """An account that starts later with an opening balance of its own in MoneyMoney (its first booking leaves a rest): a
    transfer where a bank account shows the opposite amount that month (a balance moved over from an old card), else a row
    of its own among the changes in value -- never "balance unknown"."""

    def setUp(self):
        self._acc = dict(ACCOUNTS)
        ACCOUNTS["karte"] = ("Alte Karte", "Privat", "liquiditaet", None, "bank")

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
        self.assertFalse([u for u in ds["kapitalfluss"]["ueberleitung"].values() if u["gruende"] or u["gruende_liq"]])
        self.assertNotIn("Ohne Kategorie", rows(ds, "Einnahmen")); self.assertNotIn("Tagesgeld / Anfangssaldo", rows(ds))
        tg = next(r for r in ds["bilanz"]["zeilen"] if r["id"] == "tg")
        self.assertEqual((tg["werte"]["2026-02"], tg["werte"]["2026-03"]), (None, 0.0))

    def test_otherwise_its_own_row(self):
        data = self.data(self.BASE)
        self.assertAddsUp(data, allow=("ue_anfangssaldo",))
        ds = data["Privat"]
        z = rows(ds, "Bewertung")["Tagesgeld / Anfangssaldo"]
        self.assertEqual((z["werte"]["2026-03"], z["nw"], z["lbl"]), (-115.2, True, ["cf_anfangssaldo", "Tagesgeld"]))
        self.assertEqual(ds["kapitalfluss"]["ueberleitung"]["2026-03"]["gruende_liq"], [["ue_anfangssaldo", -115.2, "Tagesgeld"]])
        self.assertFalse(any(g[0] == "ue_unbekannt" for u in ds["kapitalfluss"]["ueberleitung"].values() for g in u["gruende"] + u["gruende_liq"]))
        # a booking of that amount with a category of income, or from another area: it is that, not the balance moved over
        for extra in ({"cat": "Erstattungen"}, {"iban": "DE21"}):
            data = self.data(self.BASE + [(5, "karte", date(2026, 3, 2), 115.20, extra)])
            self.assertIn("Tagesgeld / Anfangssaldo", rows(data["Privat"], "Bewertung"), extra)
        # two bookings of that amount that month: no guess, its own row
        data = self.data(self.BASE + [(5, "karte", date(2026, 3, 2), 115.20, {}), (6, "giro", date(2026, 3, 20), 115.20, {})])
        self.assertIn("Tagesgeld / Anfangssaldo", rows(data["Privat"], "Bewertung"))


class SavingByRecipient(Reconciles):
    """Saving that arrives as a booking on none of your accounts (a depot kept by balances): the account per recipient you
    chose, else the category's, else the only depot -- without one it never counts as a depot's gain but stands openly as
    "without target account". All IBANs, names and amounts are made up."""
    ONE = "DE02100100100006820101"          # banks' public sample IBANs: at the bank of the first depot (bank code 10010010)
    TWO = "DE02120300000000202051"          # ... and of the second (12030000)

    def setUp(self):
        self._acc = dict(ACCOUNTS)
        ACCOUNTS["depot2"] = ("Depot Zwei", "Privat", "wertpapiere", None, "portfolio")

    def tearDown(self):
        ACCOUNTS.clear(); ACCOUNTS.update(self._acc)

    def data(self, txs, cfg=None, hist=None):
        led = make_ledger(txs)
        led.accounts["depot"].bank_code, led.accounts["depot2"].bank_code = "10010010", "12030000"
        config = core.merged_config(dict({"bilanz": {"rollen": {k: v[2] for k, v in ACCOUNTS.items()}},
                                          "kapitalfluss": {"positionen": {"Sparen": "anlegen"}}}, **(cfg or {})))
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
        return b["id"], config, report.build_dataset(led, config, {"historie": hist or {}}, TODAY, b, {k: v[2] for k, v in ACCOUNTS.items()})

    def txs(self):
        return [(1, "giro", date(2026, 1, 5), 9000.0, {"cat": "Gehalt"}),
                (2, "giro", date(2026, 6, 3), -1000.0, {"cat": "Sparen", "name": "Broker Zwei AG", "iban": self.TWO}),
                (3, "giro", date(2026, 6, 4), -300.0, {"cat": "Sparen / ETF", "name": "Broker Eins", "iban": self.ONE}),
                (9, "depot2", date(2026, 1, 1), 1000.0, {})]          # depot two: worth 1000 today, 0 before (history below)

    def test_without_a_target_it_is_no_gain_and_stands_openly(self):
        _, _, ds = self.data(self.txs(), hist={"depot2": {"2026-01": 0.0}})
        self.assertAddsUp({"Privat": ds})
        r = rows(ds)
        self.assertEqual(r["Anlage ohne Zielkonto"]["werte"]["2026-06"], -1300.0)           # out of the net worth Kontor sees ...
        self.assertTrue(r["Anlage ohne Zielkonto"]["nw"])
        self.assertEqual(r["Depot Zwei"]["werte"]["2026-06"], 1000.0)                      # ... which the depot's rise brings back
        self.assertEqual((r["Sparen"]["konto"], r["Sparen"]["nw"]), (None, False))
        an = {a["key"]: a for a in ds["kapitalfluss"]["anlagen"]}
        self.assertEqual([a["key"] for a in ds["kapitalfluss"]["anlagen"]], [self.TWO, self.ONE])     # largest first
        self.assertEqual((an[self.TWO]["wie"], an[self.TWO]["vorschlag"]), ("", "depot2"))           # proposals by the bank of the IBAN
        self.assertEqual(an[self.ONE]["vorschlag"], "depot")
        self.assertEqual((an[self.ONE]["anzahl"], an[self.ONE]["summe"], an[self.ONE]["kategorien"]), (1, -300.0, ["Sparen / ETF"]))
        self.assertEqual(ds["kapitalfluss"]["anlage_ziele"], ["depot", "depot2"])

    def test_the_account_you_chose_takes_it(self):
        area, _, _ = self.data(self.txs())
        cfg = {"kapitalfluss": {"positionen": {"Sparen": "anlegen"}, "empfaenger_zu_konto": {area: {self.TWO: "Depot Zwei", self.ONE: "extern"}}}}
        _, _, ds = self.data(self.txs(), cfg, hist={"depot2": {"2026-01": 0.0}})
        self.assertAddsUp({"Privat": ds})
        r = rows(ds)
        self.assertNotIn("Anlage ohne Zielkonto", r)
        self.assertAlmostEqual(r.get("Depot Zwei", {"werte": {}})["werte"].get("2026-06", 0.0), 0.0)     # paid in, not a gain
        self.assertEqual((r["Sparen → Depot Zwei"]["konto"], r["Sparen → Depot Zwei"]["nw"]), ("depot2", False))
        self.assertEqual((r["Sparen / ETF → extern"]["konto"], r["Sparen / ETF → extern"]["nw"]), (None, True))   # none in MoneyMoney: leaves the net worth
        an = {a["key"]: a for a in ds["kapitalfluss"]["anlagen"]}
        self.assertEqual((an[self.TWO]["wie"], an[self.TWO]["ziel"], an[self.TWO]["vorschlag"]), ("empfaenger", "depot2", None))
        self.assertEqual((an[self.ONE]["wie"], an[self.ONE]["auto_wie"]), ("extern", ""))
        # the recipient's choice comes before the category's account; an account of another area does not count here
        cfg["kapitalfluss"]["kategorie_zu_konto"] = {"Sparen": "Depot"}
        cfg["kapitalfluss"]["empfaenger_zu_konto"] = {area: {self.TWO: "Depot Zwei"}, "anders": {self.ONE: "Depot"}}
        _, _, ds = self.data(self.txs(), cfg)
        an = {a["key"]: a for a in ds["kapitalfluss"]["anlagen"]}
        self.assertEqual((an[self.TWO]["ziel"], an[self.TWO]["auto_ziel"], an[self.TWO]["auto_wie"]), ("depot2", "depot", "kategorie"))
        self.assertEqual((an[self.ONE]["ziel"], an[self.ONE]["wie"]), ("depot", "kategorie"))        # "Sparen / ETF" lies below "Sparen"
        cfg["kapitalfluss"]["empfaenger_zu_konto"] = {area: {self.TWO: "Kontokorrent"}}                         # an account of the company: not here
        _, _, ds = self.data(self.txs(), cfg)
        self.assertEqual({a["key"]: a["wie"] for a in ds["kapitalfluss"]["anlagen"]}[self.TWO], "kategorie")

    def test_one_recipient_over_categories_with_different_accounts(self):
        txs = self.txs() + [(4, "giro", date(2026, 5, 4), -200.0, {"cat": "Altersvorsorge", "name": "Broker Zwei AG", "iban": self.TWO})]
        _, _, ds = self.data(txs, {"kapitalfluss": {"positionen": {"Sparen": "anlegen", "Altersvorsorge": "anlegen"}, "kategorie_zu_konto": {"Sparen": "Depot"}}})
        an = {a["key"]: a for a in ds["kapitalfluss"]["anlagen"]}
        self.assertEqual((an[self.TWO]["wie"], an[self.TWO]["auto_wie"], an[self.TWO]["anzahl"]), ("gemischt", "gemischt", 2))
        self.assertEqual(sorted(an[self.TWO]["kategorien"]), ["Altersvorsorge", "Sparen"])

    def test_one_category_into_several_accounts(self):
        """The case it is for: one category ("Sparen") to two recipients with different accounts -- each its own row, every
        month adds up."""
        area, _, _ = self.data(self.txs())
        txs = [x if x[0] != 3 else (3, "giro", date(2026, 6, 4), -300.0, {"cat": "Sparen", "name": "Broker Eins", "iban": self.ONE}) for x in self.txs()]
        for order in (txs, [txs[0], txs[2], txs[1], txs[3]]):
            cfg = {"kapitalfluss": {"positionen": {"Sparen": "anlegen"}, "empfaenger_zu_konto": {area: {self.TWO: "Depot Zwei", self.ONE: "extern"}}}}
            _, _, ds = self.data(order, cfg, hist={"depot2": {"2026-01": 0.0}})
            self.assertAddsUp({"Privat": ds})
            r = rows(ds, "Investitionen")
            self.assertEqual((r["Sparen → Depot Zwei"]["konto"], r["Sparen → Depot Zwei"]["nw"], r["Sparen → Depot Zwei"]["werte"]["2026-06"]), ("depot2", False, -1000.0))
            self.assertEqual((r["Sparen → extern"]["nw"], r["Sparen → extern"]["lbl"], r["Sparen → extern"]["werte"]["2026-06"]), (True, ["cf_anlage_extern", "Sparen"], -300.0))
            self.assertNotIn("Sparen", r); self.assertNotIn("Anlage ohne Zielkonto", rows(ds))
            plan = report.apply_plan(ds, {}, core.merged_config({})) or ds          # planning: each row with its own account
            self.assertTrue(rows(ds, "Investitionen")["Sparen → Depot Zwei"]["plan"])

    def test_an_account_kept_by_balances_takes_it_as_paid_in(self):
        """An asset kept by balances (no depot): the payment is paid in, not a correction of its balance; a bank account set
        for the category keeps its old way (no "without target account")."""
        area, _, _ = self.data(self.txs())
        txs = self.txs()[:1] + [(5, "giro", date(2026, 2, 3), -1000.0, {"cat": "Sparen", "name": "Goldhandel", "iban": self.TWO})]
        cfg = {"bilanz": {"rollen": {k: v[2] for k, v in ACCOUNTS.items()}, "verlauf": {"Auto": "stand"}},
               "kapitalfluss": {"positionen": {"Sparen": "anlegen"}, "empfaenger_zu_konto": {area: {self.TWO: "Auto"}}}}
        led = make_ledger(txs); led.accounts["auto"].balance = 1000.0                 # worth 1000 today, 0 in January
        config = core.merged_config(cfg)
        b = next(x for x in core.bereiche_for(led, config) if x["name"] == "Privat")
        ds = report.build_dataset(led, config, {"historie": {"auto": {"2026-01": 0.0}}}, TODAY, b, {k: v[2] for k, v in ACCOUNTS.items()})
        self.assertAddsUp({"Privat": ds})
        r = rows(ds)
        self.assertNotIn("Auto / Korrektur Kontostand", r); self.assertEqual(r["Sparen → Auto"]["konto"], "auto")
        _, _, ds = self.data(txs, {"kapitalfluss": {"positionen": {"Sparen": "anlegen"}, "kategorie_zu_konto": {"Sparen": "Tagesgeld"}}})
        self.assertNotIn("Anlage ohne Zielkonto", rows(ds)); self.assertEqual(rows(ds)["Sparen"]["konto"], "tg")

    def test_the_category_account_elsewhere_keeps_the_depot_out(self):
        """As before: a category whose account lies in another area does not go into this area's only depot by guess."""
        del ACCOUNTS["depot2"]
        data = build([(1, "giro", date(2026, 1, 5), 3000.0, {"cat": "Gehalt"}), (2, "giro", date(2026, 3, 3), -500.0, {"cat": "Sparen", "name": "Bank"})],
                     {"kapitalfluss": {"positionen": {"Sparen": "anlegen"}, "kategorie_zu_konto": {"Sparen": "Kontokorrent"}}})
        self.assertAddsUp(data)
        self.assertEqual(rows(data["Privat"])["Anlage ohne Zielkonto"]["werte"]["2026-03"], -500.0)
        self.assertEqual(data["Privat"]["kapitalfluss"]["anlagen"][0]["wie"], "")

    def test_saving_settings(self):
        led = make_ledger(self.txs())
        cfg = core.save_positions(core.merged_config({}), {"empfaenger": {"p": {self.TWO: "Depot Zwei", self.ONE: "extern"}}}, led)
        self.assertEqual(cfg["kapitalfluss"]["empfaenger_zu_konto"], {"p": {self.TWO: "Depot Zwei", self.ONE: "extern"}})
        cfg = core.save_positions(cfg, {"empfaenger": {"p": {self.ONE: ""}}}, led)           # "" = Kontor's choice again
        self.assertEqual(cfg["kapitalfluss"]["empfaenger_zu_konto"], {"p": {self.TWO: "Depot Zwei"}})
        cfg2 = core.save_positions(cfg, {"empfaenger": {"p": {self.TWO: None}}}, led)
        self.assertEqual(cfg2["kapitalfluss"]["empfaenger_zu_konto"], {})
        with self.assertRaises(KeyError):
            core.save_positions(cfg, {"empfaenger": {"p": {self.TWO: "kein Konto"}}}, led)
        for bad in ({"empfaenger": []}, {"empfaenger": {"p": "x"}}, {"empfaenger": {"p": {"": "depot"}}}, {"empfaenger": {"p": {self.TWO: 5}}}):
            with self.assertRaises(ValueError):
                core.save_positions(cfg, bad, led)
        # odd shapes by hand are dropped; a package never carries your recipients (their IBANs), nor takes them in
        shaped = core.merged_config({"kapitalfluss": {"empfaenger_zu_konto": {"p": {self.TWO: "depot2", "x": 3}, "q": "nein"}}})
        self.assertEqual(shaped["kapitalfluss"]["empfaenger_zu_konto"], {"p": {self.TWO: "depot2"}})
        self.assertEqual(core.merged_config({"kapitalfluss": {"empfaenger_zu_konto": "nein"}})["kapitalfluss"]["empfaenger_zu_konto"], {})
        pkg = core.export_package(cfg, ledger=led)
        self.assertNotIn("empfaenger_zu_konto", pkg["config"]["kapitalfluss"])
        merged, _, _ = core.import_package(core.merged_config({}), {"kontor_paket": 1, "config": {"kapitalfluss": {"empfaenger_zu_konto": {"p": {self.TWO: "depot2"}}}}}, led)
        self.assertEqual(merged["kapitalfluss"].get("empfaenger_zu_konto") or {}, {})
        for mode in ("ersetzen", "ergaenzen"):                     # your own stay, also when a package replaces the cash flow settings
            merged, _, _ = core.import_package(cfg, {"kontor_paket": 1, "config": {"kapitalfluss": {"positionen": {"Sparen": "anlegen"}}}}, led, mode)
            self.assertEqual(merged["kapitalfluss"]["empfaenger_zu_konto"], {"p": {self.TWO: "Depot Zwei"}}, mode)
        # a gone account: a note, not an error (Kontor's choice applies again)
        found = core.check_config(led, [], dict(cfg, kapitalfluss=dict(cfg["kapitalfluss"], empfaenger_zu_konto={"p": {self.TWO: "weg | Altes Depot"}})))
        self.assertTrue(any(f["stufe"] == "warnung" and self.TWO in f["text"] for f in found))
        self.assertFalse(any(f["stufe"] == "fehler" and self.TWO in f["text"] for f in found))
        area = next(x for x in core.bereiche_for(led, cfg) if x["name"] == "Privat")["id"]          # an account of another area: a note
        found = core.check_config(led, [], dict(cfg, kapitalfluss=dict(cfg["kapitalfluss"], empfaenger_zu_konto={area: {self.TWO: "Kontokorrent"}})))
        self.assertTrue(any(f["stufe"] == "warnung" and "Kontokorrent" in f["text"] for f in found))


class MirrorsAndCompanies(Reconciles):
    def test_a_mirror_into_a_company_counts_at_once(self):
        """A company counts as set up with an account mirror into one of its accounts: a payment to it from another company is
        a contribution there (Investitionen) -- also when only the mirror was added and nothing changed in MoneyMoney."""
        areas = [{"id": "p", "name": "Privat", "art": "privat", "haupt": True, "konten": ["Privat"]},
                 {"id": "m", "name": "Muster GbR", "art": "gesellschaft", "konten": ["Muster GbR"]},
                 {"id": "k", "name": "Kinder", "art": "gesellschaft", "konten": ["Kinder"]}]
        led = make_ledger([(1, "kk", date(2026, 3, 3), -10000.0, {"iban": "DE31"}), (2, "kind", date(2026, 3, 3), 10000.0, {"iban": "DE21"})])
        before = datasets(led, {"bereiche": areas})
        self.assertEqual([s for s in ("Investitionen", "Finanzierung") if rows(before["Muster GbR"], s)], ["Finanzierung"])
        after = datasets(led, {"bereiche": areas, "kontenspiegel": [{"a": "Auto", "b": "Kinderkonto", "ab": "alles"}]})
        self.assertEqual([s for s in ("Investitionen", "Finanzierung") if rows(after["Muster GbR"], s)], ["Investitionen"])
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
        data = {b["bereich"]["name"]: b for b in store.load("dataset.json")["bereiche"].values()}
        self.assertEqual(len(data), 3)
        self.assertAddsUp(data)
        for ds in data.values():
            self.assertFalse([z["zeile"] for z in rows(ds, "Unklar").values()], ds["bereich"]["name"])


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
        cfg = {"gesellschaften": [{"bereich": "Muster GbR", "beteiligung": "Beteiligung an Muster GbR"}],
               "kapitalfluss": {"positionen": {"Privatentnahme": "ignorieren"}}}
        for seed in range(seeds):
            with self.subTest(seed=seed):
                txs = self.world(random.Random(seed))
                data = build(txs, cfg)
                self.assertAddsUp(data, allow=("ue_unterwegs", "ue_ignoriert"))
                # income and expenses never pair with anything: their rows are exactly their bookings
                p, k = rows(data["Privat"]), rows(data["Kinder"])
                for cat, pos in (("Gehalt", "Arbeitseinkommen"), ("Lebensmittel", "Lebenshaltung"), ("Wohnen\\Miete", "Wohnen")):
                    want = round(sum(e[3] for e in txs if (e[4] or {}).get("cat") == cat and (e[4] or {}).get("booked", True)), 2)
                    got = round(sum(p[pos]["werte"].values()), 2) if pos in p else 0.0
                    self.assertAlmostEqual(got, want, 2, cat)
                    det = {d["kategorie"]: d for d in (p[pos].get("details") or [])} if pos in p else {}
                    self.assertAlmostEqual(round(sum(det[cat.replace("\\", " / ")]["werte"].values()), 2) if det else 0.0, want, 2)
                # between two areas: what one pays in, the other receives
                out = round(sum(p["Einlage/Entnahme Kinder"]["werte"].values()), 2) if "Einlage/Entnahme Kinder" in p else 0.0
                inn = round(sum(k["Einlage/Entnahme Privat"]["werte"].values()), 2) if "Einlage/Entnahme Privat" in k else 0.0
                self.assertAlmostEqual(out, -inn, 2)


if __name__ == "__main__":
    unittest.main()
