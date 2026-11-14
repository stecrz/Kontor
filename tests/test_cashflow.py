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
        self.assertEqual(r["Lebensmittel"]["werte"]["2026-02"], -700.0)
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
        self.assertEqual(r["Lebensmittel"]["werte"]["2026-02"], -70.0)
        self.assertEqual(r["Lebensmittel"]["werte"]["2026-06"], 0.0)
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
        cfg = {"kapitalfluss": {"kategorie_zuordnung": {"Privatentnahme": "Ignorieren"}}}
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
        self.assertEqual(z["lbl"], ["cf_zinsen", "Verkäuferdarlehen"])
        try:
            i18n.set_lang("en")
            self.assertEqual(i18n.tr(*z["lbl"]), "Verkäuferdarlehen / Interest")
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
               "kapitalfluss": {"kategorie_zuordnung": {"Privatentnahme": "Ignorieren"}}}
        for seed in range(seeds):
            with self.subTest(seed=seed):
                txs = self.world(random.Random(seed))
                data = build(txs, cfg)
                self.assertAddsUp(data, allow=("ue_unterwegs", "ue_ignoriert"))
                # income and expenses never pair with anything: their rows are exactly their bookings
                p, k = rows(data["Privat"]), rows(data["Kinder"])
                for cat in ("Gehalt", "Lebensmittel"):
                    want = round(sum(e[3] for e in txs if (e[4] or {}).get("cat") == cat and (e[4] or {}).get("booked", True)), 2)
                    got = round(sum(p[cat]["werte"].values()), 2) if cat in p else 0.0
                    self.assertAlmostEqual(got, want, 2, cat)
                # between two areas: what one pays in, the other receives
                out = round(sum(p["Einlage/Entnahme Kinder"]["werte"].values()), 2) if "Einlage/Entnahme Kinder" in p else 0.0
                inn = round(sum(k["Einlage/Entnahme Privat"]["werte"].values()), 2) if "Einlage/Entnahme Privat" in k else 0.0
                self.assertAlmostEqual(out, -inn, 2)


if __name__ == "__main__":
    unittest.main()
