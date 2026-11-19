"""End-to-End: Kern (run_once) und Dienst (HTTP-API, Oberflaeche) gegen eine Mock-Anbindung -- kein MoneyMoney noetig."""
import base64
import copy
import io
import json
import re
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import fixtures as F  # noqa: E402
import mm_bridge  # noqa: E402
import core  # noqa: E402
import categorize  # noqa: E402
import updates  # noqa: E402
from service import App, make_handler  # noqa: E402
from model import TAG_RE, Ledger, accounts_from_export, fmt_eur, tx_from_export  # noqa: E402
from storage import Store, load_or_create_master_key  # noqa: E402
from tax import build_tax  # noqa: E402

TODAY = date(2026, 11, 4)


def wait_shell(pg, timeout=30000):
    """Wait for the app after login; on timeout report what the login page shows (flaky timeouts under load)."""
    try:
        pg.wait_for_selector("#shell:not(.hidden)", timeout=timeout)
    except Exception as e:
        info = pg.evaluate("({err: (document.querySelector('#login-err') || {}).textContent, login: !document.querySelector('#login').classList.contains('hidden'), btn: (document.querySelector('#login-btn') || {}).textContent})")
        raise AssertionError("shell not shown: %r" % info) from e


class MockBridge:
    """Simuliert MoneyMoney: Konten + Umsaetze im Speicher, Schreibbefehle wirken sofort."""
    instances = []
    reads = []                  # accounts of the transaction exports (None: all)
    state = {"accounts": [], "txs": []}

    def __init__(self, dry_run=True, timeout=0):
        self.dry_run = dry_run
        self.written = []
        self.accounts = copy.deepcopy(MockBridge.state["accounts"])
        self.txs = MockBridge.state["txs"]
        MockBridge.instances.append(self)

    def export_accounts(self):
        return copy.deepcopy(MockBridge.state["accounts"])

    # wie MoneyMoney: flache Liste mit Einrueckung, ohne Pfad; Standardkategorie "Unkategorisiert"
    CATS = [("Unkategorisiert", 0, False, {"default": True}), ("Umbuchung", 0, False, {}), ("Finanzierung", 0, True, {}), ("Zinsen", 1, False, {}),
            ("Wohnen", 0, True, {}), ("Miete", 1, False, {"budget": {"amount": 1500.0, "period": "monthly"}}),
            ("Einnahmen", 0, True, {}), ("Gehalt", 1, False, {}), ("Investments", 0, True, {}), ("ETF", 1, False, {}),
            ("Vermietung", 0, True, {}), ("Parkweg", 1, True, {}), ("Mieteinnahmen", 2, False, {}), ("Hausgeld", 2, False, {})]
    extra_cats: list = []

    def export_categories(self):
        out = [dict({"name": n, "indentation": i, "group": g, "uuid": F.uid("cat:" + n)}, **x) for n, i, g, x in self.CATS + MockBridge.extra_cats]
        return copy.deepcopy(out)

    def export_transactions(self, from_date, to_date=None, account=None):
        MockBridge.reads.append(account)
        return [t for t in self.txs if mm_bridge.local_date(t["bookingDate"]) >= from_date and (not account or t["accountUuid"] == account)]

    def export_portfolio(self, account):
        if account == F.uid("priv.depot"):
            return [{"name": "Welt-ETF", "isin": "IE00B4L5Y983", "quantity": 500.0, "marketPrice": 110.0, "marketValue": 55000.0, "purchaseValue": 42000.0, "currency": "EUR", "assetClass": "ETF"},
                    {"name": "Anleihen-ETF", "isin": "IE00BZ163L38", "quantity": 600.0, "marketPrice": 50.0, "marketValue": 30000.0, "purchaseValue": 31000.0, "currency": "EUR", "assetClass": "ETF"}]
        return []

    append_comment = mm_bridge.Bridge.append_comment

    def add_transaction(self, account_ref, booking_date, payee, amount, purpose="", category=None):
        self.written.append(("add", account_ref, booking_date, amount, purpose))
        if self.dry_run:
            return
        key = [k for k, u in F.U.items() if u == account_ref][0]
        self.txs.append(F.tx(key, booking_date, amount, payee, purpose, category or ""))
        for a in MockBridge.state["accounts"]:
            if a["uuid"] == account_ref:
                a["balance"][0][0] = round(a["balance"][0][0] + amount, 2)

    def set_transaction(self, tx_id, category=None, comment=None, checkmark=None):
        self.written.append(("set", tx_id, category, comment))
        if self.dry_run:
            return
        for t in self.txs:
            if t["id"] == tx_id:
                if comment is not None:
                    t["comment"] = comment
                if category is not None:
                    import mm_categories
                    paths = {c["uuid"]: c["path"] for c in mm_categories.with_paths(self.export_categories())}
                    path = paths.get(category, category)
                    t["category"] = path.split("\\")[-1]; t["categoryPath"] = path


def private_transactions(until):
    out = []
    y, m = 2024, 10
    while date(y, m, 1) <= until:
        d = date(y, m, 1)
        out.append(F.tx("priv.giro", d, 6500.0, "Arbeitgeber", "Gehalt", "Einnahmen\\Gehalt"))
        out.append(F.tx("priv.giro", date(y, m, 3), -1450.0, "Vermieter", "Miete", "Wohnen\\Miete"))
        out.append(F.tx("priv.giro", date(y, m, 5), -320.0, "Versicherer", "Beitrag", "Versicherungen\\Haftpflicht"))
        out.append(F.tx("priv.giro", date(y, m, 15), -600.0, "Supermarkt", "Einkauf", "Lebensmittel"))
        out.append(F.tx("priv.giro", date(y, m, 16), -75.0, "Baumarkt", "Werkzeug", ""))
        out.append(F.tx("priv.giro", date(y, m, 1), -1500.0, "VR-Bank", "Annuität Darlehen", "Umbuchung", "DE02500105170137075030"))
        out.append(F.tx("priv.darl", date(y, m, 1), 1500.0, "Hausbank", "Annuität", "Umbuchung", "DE02120300000000202051"))
        out.append(F.tx("priv.darl", date(y, m, 1), -900.0, "VR-Bank", "Zinsen", "Zinsen"))
        out.append(F.tx("priv.giro", date(y, m, 2), -1000.0, "Broker", "Übertrag", "Umbuchung", "DE02100500000054540402"))
        out.append(F.tx("priv.tr", date(y, m, 2), 1000.0, "Hausbank", "Übertrag", "Umbuchung", "DE02120300000000202051"))
        out.append(F.tx("priv.tr", date(y, m, 4), -1000.0, "Broker", "Sparplan ETF", "Investments\\ETF"))
        out.append(F.tx("ga.kk", date(y, m, 5), 9500.0, "Mieter", "Miete", "Vermietung\\Parkweg\\Mieteinnahmen"))
        out.append(F.tx("ga.kk", date(y, m, 6), -800.0, "Hausverwaltung", "Hausgeld", "Vermietung\\Parkweg\\Hausgeld"))
        if m == 6:
            out.append(F.tx("priv.giro", date(y, 6, 20), -10000.0, "Alpha GbR", "Einlage", "Umbuchung", "DE02701500000000594937"))
            out.append(F.tx("ga.kk", date(y, 6, 20), 10000.0, "Gesellschafter A", "Einlage", "Umbuchung", "DE02120300000000202051"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def config_for_test(belege_dir=None):
    cfg = {
        "dry_run": False, "notifications": False,
        "schedule": {"interval_minutes": 30, "automatic": False},
        "loans": [{
            "name": "Verkäuferdarlehen", "loan_account": F.uid("ga.vd") + " | Verkäuferdarlehen",
            "source_accounts": [F.uid("ga.kk") + " | Stadtbank Kontokorrent"],
            "detection": {"counter_iban": F.SELLER_IBAN}, "from_date": "2026-01-01",
            "interest": {"model": "yearly_base", "rate_list": [{"from_date": "2025-11-20", "percent": 3.0}], "booking_day": "with_payment"},
            "booking": {"counterparty": "Verkäufer", "category_repayment": "Umbuchung", "category_interest": "Zinsen"}}],
        "areas": [
            {"id": F.uid("priv"), "name": "Privat", "kind": "private", "main_area": True, "accounts": [F.uid("priv") + " | Privat"]},
            {"id": F.uid("ga"), "name": "Alpha GbR", "kind": "company", "share": 0.4, "accounts": [F.uid("ga") + " | Alpha GbR"]},
            {"id": F.uid("gb"), "name": "Beta GbR", "kind": "company", "share": 0.4, "accounts": [F.uid("gb") + " | Beta GbR"]}],
        "companies": [
            {"area": F.uid("ga"), "participation": F.uid("priv.bet.ga") + " | Beteiligung an Alpha GbR", "retroactive_from": TODAY.isoformat()},
            {"area": F.uid("gb"), "participation": F.uid("priv.bet.gb") + " | Beteiligung an Beta GbR", "retroactive_from": TODAY.isoformat()}],
        "balance": {"months_back": 24, "illiquid_roles": ["participations"],
                   "illiquid_accounts": [F.uid("priv.darl") + " | Darlehen Lindenstraße"]},
        "cashflow": {"category_to_account": {"Investments\\ETF": F.uid("priv.depot") + " | Depot"}},
        "tax": {"depreciation": {"Parkweg": {"2026": 40000}}},
        "updates": {"check_mode": "aus"},
        "ui": {"lock_minutes": 15, "port": 0},
    }
    if belege_dir:
        cfg["receipts"] = {"folder": belege_dir, "subfolder": "{year}/{entity}"}
    return cfg


ALL_NEW = {"seen": {"id": 0, "tag": "2000-01-01"}}       # Kontor last looked long ago: everything in MoneyMoney is new


def reset_mock():
    MockBridge.state = {"accounts": F.accounts_raw({"ga.vd": -1200000.0}), "txs": F.ga_transactions(TODAY) + private_transactions(TODAY)}
    MockBridge.instances = []
    MockBridge.reads = []
    MockBridge.extra_cats = []


class _FixedDate(date):
    @classmethod
    def today(cls):
        return TODAY


def patch_today():
    import service
    core.date = _FixedDate
    service.date = _FixedDate
    service.is_running = lambda: True


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-test-")
        key, src = load_or_create_master_key(self.dir)
        self.store = Store(self.dir, key, src)
        self.store.save("config.json", config_for_test(os.path.join(self.dir, "Belege")))
        self.store.save("state.json", dict(ALL_NEW))
        reset_mock()
        patch_today()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_approve_selection_change_and_reject(self):
        """With approval: book only the chosen bookings, one changed (amount, date, text; its mark stays); the others keep
        waiting; a rejected one is never proposed again; planned bookings are not in "created by Kontor"."""
        import service as MA
        cfg = core.merged_config(self.store.load("config.json")); cfg["dry_run"] = True
        res = core.run_once(self.store, cfg, TODAY, dry=True, force=True, bridge_factory=MockBridge)
        props = res["proposals"]; self.assertEqual(len(props), 24); self.assertTrue(all(p["tag"].startswith("#kontor-") for p in props))
        self.assertEqual(MA.kontor_bookings(res["_ledger"].without_planned()), [])     # planned, not made: nothing "created by Kontor"
        self.assertEqual(res["_ledger"].without_planned().accounts[F.uid("ga.vd")].balance, -1200000.0)
        zins = [p for p in props if p["kind"] == "interest"]; tilg = [p for p in props if p["kind"] == "repayment"]
        wert = [p for p in props if p["kind"] == "value"]                     # two companies: the same mark, two accounts
        self.assertEqual(len({p["tag"] for p in wert}), 1); self.assertEqual(len({p["key"] for p in wert}), 2)
        cfg["not_book"] = [core.not_booked_entry(zins[0], zins[0]["key"])]           # "Don't book" (settings)
        approve, err = MA.approval({tilg[0]["key"]: {}, wert[0]["key"]: {}, zins[1]["key"]: {"amount": "-1234,56", "purpose": "Zinsen laut Abrechnung", "date": "2026-10-15"}})
        self.assertIsNone(err)
        r = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge, approve=approve)
        self.assertEqual(r["status"], "ok", r); self.assertEqual(r["written"], 3)        # the 3 bookings, nothing else
        self.assertFalse([w for w in r["warnings"] if "nach Buchung" in w], r["warnings"])
        # 24 - 1 rejected - 3 booked, still waiting -- and one more: the value booked matches what is in MoneyMoney now (the loan
        # bookings left out not included), so once they are booked the value needs one more adjustment
        self.assertTrue(r["dry_run"]); self.assertEqual(len(r["proposals"]), 21)
        self.assertIn(wert[1]["key"], [p["key"] for p in r["proposals"]]); self.assertNotIn(wert[0]["key"], [p["key"] for p in r["proposals"]])
        more = [p for p in r["proposals"] if p["kind"] == "value" and p["account_id"] == wert[0]["account_id"]]
        self.assertEqual(len(more), 1); self.assertTrue(more[0]["tag"].endswith("-2"))
        self.assertNotIn(zins[0]["tag"], [p["tag"] for p in r["proposals"]])
        made = [t for t in MockBridge.state["txs"] if zins[1]["tag"] in (t.get("purpose") or "")]
        self.assertEqual(len(made), 1); self.assertEqual(made[0]["amount"], -1234.56)
        self.assertEqual(made[0]["purpose"], "Zinsen laut Abrechnung · " + zins[1]["tag"])
        self.assertEqual(made[0]["bookingDate"], F._dt(date(2026, 10, 15)))
        self.assertEqual(len(MA.kontor_bookings(core.fetch(MockBridge(True), cfg, TODAY))), 3)          # recognised by their marks
        # "Propose again": off the list, waiting for approval again, then approved like any other
        cfg["not_book"] = []
        r1 = core.run_once(self.store, cfg, TODAY, dry=True, force=True, bridge_factory=MockBridge)
        self.assertIn(zins[0]["key"], [p["key"] for p in r1["proposals"]])
        r2 = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge, approve={zins[0]["key"]: {}})
        self.assertEqual(r2["written"], 1)
        self.assertTrue([t for t in MockBridge.state["txs"] if zins[0]["tag"] in (t.get("purpose") or "")])
        # invalid changes and marks are refused
        self.assertIsNotNone(MA.approval({zins[2]["key"]: {"amount": "0"}})[1]); self.assertIsNotNone(MA.approval({"rm -rf": {}})[1])
        self.assertIsNotNone(MA.approval({zins[2]["key"]: {"date": "2026-13-01"}})[1]); self.assertIsNotNone(MA.approval({zins[2]["tag"]: {}})[1])

    def test_left_out_recalculated_and_deleted_value_checked_on_its_day(self):
        """What you leave out of an approval is planned as not booked (the next value adjustment takes up the difference),
        booked is exactly what you saw; a value adjustment deleted or changed in MoneyMoney is corrected on its day."""
        cfg = core.merged_config(self.store.load("config.json")); cfg["dry_run"] = True
        cfg["companies"][0].update(retroactive_from="2026-03", cycle="monthly")
        props = core.run_once(self.store, cfg, TODAY, dry=True, force=True, bridge_factory=MockBridge)["proposals"]
        tilg = [p for p in props if p["kind"] == "repayment"]
        st = self.store.load("state.json")
        led = core.fetch(MockBridge(True), cfg, TODAY)
        held = core.plan_pending(led, cfg, st, TODAY, {tilg[0]["key"]})
        old, new = {p["key"]: p["amount"] for p in props}, {p["key"]: p["amount"] for p in held}
        self.assertNotIn(tilg[0]["key"], new)
        moved = [k for k in new if k in old and abs(new[k] - old[k]) >= 0.005]
        self.assertEqual(len(moved), 1); self.assertTrue(moved[0].split("|")[1].startswith("#kontor-wert-"))       # only the next one
        # the amounts shown before leaving it out are not the ones booked now: nothing is written
        approve = {k: {"shown": v} for k, v in old.items() if k != tilg[0]["key"]}
        r = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge, approve=approve)
        self.assertEqual(r["written"], 0); self.assertIn(core.tr("s_betraege_geaendert"), r["warnings"]); self.assertTrue(r["dry_run"])
        # with the amounts recalculated: all of them booked, the one left out keeps waiting
        approve = {k: {"shown": v} for k, v in new.items()}
        r = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge, approve=approve)
        self.assertEqual(r["status"], "ok", r); self.assertFalse([w for w in r["warnings"] if "nach Buchung" in w], r["warnings"])
        made = {t["accountUuid"] + "|" + TAG_RE.search(t["purpose"]).group(0): t["amount"] for t in MockBridge.state["txs"] if TAG_RE.search(t.get("purpose") or "")}
        for k, v in new.items():
            self.assertAlmostEqual(made[k], v, 2)
        self.assertIn(tilg[0]["key"], [p["key"] for p in r["proposals"]])
        # booked later on: the value adjusted once more, on the first month end after it
        rest = {p["key"]: {"shown": p["amount"]} for p in r["proposals"]}
        r = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge, approve=rest)
        self.assertEqual(r["status"], "ok", r); self.assertEqual(core.run_once(self.store, cfg, TODAY, dry=True, force=True, bridge_factory=MockBridge)["proposals"], [])
        # a value adjustment of a past month end deleted in MoneyMoney: its day checked again (not under "not booked")
        txs = MockBridge.state["txs"]
        wert = sorted((t for t in txs if "#kontor-wert-2026" in (t.get("purpose") or "") and t["accountUuid"] == F.uid("priv.bet.ga")), key=lambda t: t["bookingDate"])[2]
        txs.remove(wert)
        acc = next(a for a in MockBridge.state["accounts"] if a["uuid"] == wert["accountUuid"]); acc["balance"][0][0] = round(acc["balance"][0][0] - wert["amount"], 2)
        r = core.run_once(self.store, cfg, TODAY, dry=True, force=True, bridge_factory=MockBridge)
        wtag = TAG_RE.search(wert["purpose"]).group(0)
        self.assertEqual([(p["key"], p["amount"]) for p in r["proposals"]], [(wert["accountUuid"] + "|" + wtag, wert["amount"])])
        p = r["proposals"][0]
        r = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge, approve={p["key"]: {"shown": p["amount"]}})
        self.assertEqual(r["written"], 1)
        back = [t for t in txs if wtag in (t.get("purpose") or "") and t["accountUuid"] == wert["accountUuid"]]
        self.assertEqual([(t["amount"], t["bookingDate"]) for t in back], [(wert["amount"], wert["bookingDate"])])
        # changed there: the difference back on its day
        back[0]["amount"] = round(back[0]["amount"] + 50, 2); acc["balance"][0][0] = round(acc["balance"][0][0] + 50, 2)
        r = core.run_once(self.store, cfg, TODAY, dry=True, force=True, bridge_factory=MockBridge)
        self.assertEqual([(p["amount"], p["date"]) for p in r["proposals"]], [(-50.0, p["date"])])

    def test_mirror_books_new_at_once_but_older_only_with_approval(self):
        """Account mirror with "Book fully automatically": what was there before the mirror was set up waits for your approval
        (it may be in the other account by hand already, on another day); what is booked afterwards is mirrored at once."""
        cfg = core.merged_config(self.store.load("config.json")); cfg["dry_run"] = False
        self.store.save("state.json", {})              # Kontor looks for the first time: what is there now is older
        cfg["companies"][1] = {"area": F.uid("gb"), "retroactive_from": "all"}
        cfg["account_mirrors"] = [{"a": F.uid("priv.bet.gb") + " | Beteiligung an Beta GbR", "b": F.uid("gb.kap.a") + " | Kapitalkonto A", "from_date": "all"}]
        txs = MockBridge.state["txs"]
        old = F.tx("gb.kap.a", date(2026, 9, 1), -5000.0, "Ich", "Einlage alt"); txs.append(old)
        r = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge)
        self.assertEqual(r["status"], "ok", r)
        gk = [t for t in txs if "#kontor-gk-" in (t.get("purpose") or "")]
        self.assertEqual(gk, [])                                           # the older one: not booked on its own
        wait = [p for p in r["proposals"] if p["kind"] == "mirror"]
        self.assertTrue(r["dry_run"]); self.assertEqual([(p["retroactive"], p["amount"], p["counterparty"]) for p in wait], [(True, 5000.0, "Beta GbR")])
        self.assertGreaterEqual(self.store.load("state.json")["seen"]["id"], old["id"])
        # booked after the mirror was set up: mirrored at the next sync without asking; the older one keeps waiting
        new = F.tx("gb.kap.a", TODAY, 300.0, "Ich", "Entnahme neu"); txs.append(new)
        r = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge)
        gk = [t for t in txs if "#kontor-gk-" in (t.get("purpose") or "")]
        self.assertEqual([(t["amount"], t["accountUuid"], t["name"]) for t in gk], [(-300.0, F.uid("priv.bet.gb"), "Beta GbR")])
        self.assertIn("Entnahme neu · gespiegelt von Kapitalkonto A · #kontor-gk-%d" % new["id"], gk[0]["purpose"])
        self.assertEqual([p["amount"] for p in r["proposals"] if p["kind"] == "mirror"], [5000.0])
        # approved: booked; nothing mirrored back, nothing twice
        key = next(p["key"] for p in r["proposals"] if p["kind"] == "mirror")
        r = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge, approve={key: {}})
        self.assertEqual(len([t for t in txs if "#kontor-gk-" in (t.get("purpose") or "")]), 2)
        r = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge)
        self.assertEqual(len([t for t in txs if "#kontor-gk-" in (t.get("purpose") or "")]), 2)
        self.assertFalse([p for p in r["proposals"] if p["kind"] == "mirror" and r["dry_run"]])         # no mirrored booking waits
        self.assertFalse([w for w in r["warnings"] if "Original" in w])
        # the original deleted in MoneyMoney: a note to delete the mirrored booking too (Kontor deletes nothing)
        txs.remove(new)
        acc = next(a for a in MockBridge.state["accounts"] if a["uuid"] == F.uid("gb.kap.a")); acc["balance"][0][0] = round(acc["balance"][0][0] - 300.0, 2)
        n = len(txs)
        r = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge)
        self.assertTrue([w for w in r["warnings"] if "kein Original mehr" in w], r["warnings"]); self.assertEqual(len(txs), n)

    def test_failing_rules_book_nothing_and_stop_nothing_else(self):
        """Something unexpected inside the rules: nothing is booked, the mark of the last check stays, the run itself goes on
        (reading, the report) and says so; the next sync tries again."""
        cfg = core.merged_config(self.store.load("config.json"))
        core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge)
        before = self.store.load("state.json"); n = len(MockBridge.state["txs"])
        real = core.plan_all

        def boom(*a, **k):
            raise RuntimeError("unerwartet")
        core.plan_all = boom
        try:
            MockBridge.state["txs"].append(F.tx("ga.kk", TODAY, -99.0, "x", "y"))        # something to do: the company is worth less
            kk = next(a for a in MockBridge.state["accounts"] if a["uuid"] == F.uid("ga.kk")); kk["balance"][0][0] = round(kk["balance"][0][0] - 99.0, 2)
            with self.assertLogs(level="ERROR") as cm:
                r = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge)
        finally:
            core.plan_all = real
        self.assertEqual(r["status"], "ok"); self.assertEqual(r["written"], 0); self.assertEqual(len(MockBridge.state["txs"]), n + 1)
        self.assertTrue(any("nichts gebucht" in w for w in r["warnings"]), r["warnings"])
        self.assertNotIn("unerwartet", "".join(cm.output))                            # the log names the kind and place, no contents
        after = self.store.load("state.json")
        self.assertEqual(after["seen"], before["seen"]); self.assertIsNone(after["fingerprint"])
        self.assertTrue(self.store.load("dataset.json").get("areas"))                # the report was built all the same
        r = core.run_once(self.store, cfg, TODAY, dry=False, force=False, bridge_factory=MockBridge)      # the next sync: again
        self.assertEqual(r["status"], "ok"); self.assertEqual(r["written"], 1)

    def test_settings_of_the_wrong_kind_are_dropped(self):
        """A configuration changed by hand or imported with the wrong kind of value somewhere: dropped when loaded, nothing fails."""
        cfg = self.store.load("config.json")
        cfg["loans"].append("kein Darlehen"); cfg["loans"][0]["source_accounts"] = "nur ein Text"; cfg["loans"].append({"name": 5, "from_date": "2026-13-45"})
        cfg["companies"] = [None, {"area": F.uid("ga"), "participation": 12, "threshold": "viel"}]
        cfg["account_mirrors"] = [3, {"a": [], "b": F.uid("ga.kap.a")}]
        cfg["areas"].append(7); cfg["balance"] = "kaputt"; cfg["fetch"] = {"offline": 4}
        m = core.merged_config(cfg)
        self.assertEqual(len(m["loans"]), 2); self.assertEqual(m["loans"][0]["source_accounts"], ["nur ein Text"]); self.assertFalse(m["loans"][1]["active"])
        self.assertEqual(m["companies"], [{"area": F.uid("ga"), "participation": "", "threshold": 0.01}])
        self.assertEqual(m["account_mirrors"], [{"a": "", "b": F.uid("ga.kap.a"), "from_date": ""}])      # incomplete: the check names it, nothing books
        self.assertEqual(m["balance"]["inactive_months"], 12); self.assertEqual(m["fetch"]["offline"], [])
        r = core.run_once(self.store, m, TODAY, dry=True, force=True, bridge_factory=MockBridge)
        self.assertEqual(r["status"], "ok")
        led = core.fetch(MockBridge(True), m, TODAY)
        self.assertTrue(core.check_config(led, [], m))                                  # named, not crashed

    def test_run_progress(self):
        """Reading, rules, then each booking (n of m) -- what the interface shows while a run goes on."""
        steps = []
        cfg = core.merged_config(self.store.load("config.json"))
        res = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge, progress=lambda *a: steps.append(a))
        self.assertEqual(steps[:2], [("read", 0, 0), ("rules", 0, 0)])
        booking = [x for x in steps if x[0] == "buchen"]
        self.assertEqual(len(booking), res["booked_count"]); self.assertEqual([x[1] for x in booking], list(range(res["booked_count"])))
        self.assertEqual({x[2] for x in booking}, {res["booked_count"]}); self.assertEqual(res["booked_count"], res["written"])

    def test_run_twice_then_dataset(self):
        cfg = core.merged_config(self.store.load("config.json"))
        res = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge)
        self.assertEqual(res["status"], "ok", res)
        self.assertEqual(res["written"], 24)      # 11 Tilgung + 11 Zins + 2 Wert -- nothing else: the payments are never touched
        self.assertFalse([w for b in MockBridge.instances for w in b.written if w[0] == "set"])
        self.assertEqual(len(res["proposals"]), 24)
        vd = [a for a in MockBridge.state["accounts"] if a["name"] == "Verkäuferdarlehen"][0]["balance"][0][0]
        self.assertAlmostEqual(vd, -1200000 + 11 * 6000 - 11 * 3000, 2)
        res2 = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge)
        self.assertEqual(res2["written"], 0)
        self.assertEqual(core.run_once(self.store, cfg, TODAY, dry=False, force=False, bridge_factory=MockBridge)["status"], "unchanged")
        cfg2 = copy.deepcopy(cfg); cfg2["companies"][0]["threshold"] = 5          # changed rules: checked again without a change in MoneyMoney
        self.assertEqual(core.run_once(self.store, cfg2, TODAY, dry=True, force=False, bridge_factory=MockBridge)["status"], "ok")
        self.assertEqual(core.run_once(self.store, cfg2, TODAY + timedelta(days=1), dry=True, force=False, bridge_factory=MockBridge)["status"], "ok")   # a new day too
        # Kontor's bookings are recognised by their marks: 24, the payments themselves carry none
        txs = MockBridge.state["txs"]
        self.assertEqual(len([t for t in txs if TAG_RE.search(t.get("purpose") or "")]), 24)
        # deleted in MoneyMoney: missing again, so proposed again -- older than the last check, so it waits for you even when
        # booking fully automatically; one whose mark you removed counts as interest you booked yourself
        zins = [t for t in txs if "#kontor-zins-" in (t.get("purpose") or "")]
        gone = zins[0]; txs.remove(gone)
        vd = next(a for a in MockBridge.state["accounts"] if a["uuid"] == gone["accountUuid"]); vd["balance"][0][0] = round(vd["balance"][0][0] - gone["amount"], 2)
        zins[1]["purpose"] = zins[1]["purpose"].replace("#kontor-zins-", "#geaendert-")
        res3 = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge)
        tag = re.findall(r"#kontor-zins-[0-9-]+", gone["purpose"])[0]
        self.assertEqual(res3["written"], 1)              # the participation follows the company's value at once (today)
        self.assertTrue(res3["dry_run"]); self.assertTrue(any("selbst gebucht" in h for h in res3["hints"]))
        wait = {p["tag"]: p for p in res3["proposals"]}
        self.assertTrue(wait[tag]["retroactive"])            # the interest waits for you; approved, today's value follows it
        self.assertEqual(sorted(p["kind"] for p in res3["proposals"]), ["interest", "value"])
        res4 = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge,
                             approve={p["key"]: {"shown": p["amount"]} for p in res3["proposals"]})
        self.assertEqual(res4["written"], 2); self.assertFalse(res4["dry_run"])
        self.assertEqual(core.run_once(self.store, cfg, TODAY, dry=True, force=True, bridge_factory=MockBridge)["proposals"], [])
        # a value adjustment deleted in MoneyMoney: proposed again on its day (the same mark, free again), approved with the
        # amount shown
        wert = [t for t in txs if "#kontor-wert-" in (t.get("purpose") or "")][0]; txs.remove(wert)
        acc = next(a for a in MockBridge.state["accounts"] if a["uuid"] == wert["accountUuid"]); acc["balance"][0][0] = round(acc["balance"][0][0] - wert["amount"], 2)
        r5 = core.run_once(self.store, cfg, TODAY, dry=True, force=True, bridge_factory=MockBridge)
        w5 = [p for p in r5["proposals"] if p["kind"] == "value"]; self.assertEqual(len(w5), 1)
        wtag = TAG_RE.search(wert["purpose"]).group(0)
        self.assertEqual(w5[0]["key"], wert["accountUuid"] + "|" + wtag); self.assertAlmostEqual(w5[0]["amount"], wert["amount"], 2)
        r6 = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge, approve={w5[0]["key"]: {"shown": w5[0]["amount"]}})
        self.assertEqual(r6["written"], 1)
        again = [t for t in txs if wtag in (t.get("purpose") or "") and t["accountUuid"] == wert["accountUuid"]]
        self.assertEqual(len(again), 1); self.assertEqual(again[0]["amount"], wert["amount"]); self.assertEqual(again[0]["bookingDate"], wert["bookingDate"])
        ds = self.store.load("dataset.json")
        self.assertEqual(ds["main_area"], F.uid("priv"))
        self.assertEqual(set(ds["area_names"].values()), {"Privat", "Alpha GbR", "Beta GbR"})
        self.assertIn("tax", ds); self.assertIn("accounts", ds); self.assertIn("depots", ds)
        self.assertEqual(ds["depots"][0]["name"], "Depot"); self.assertAlmostEqual(ds["depots"][0]["sum"], 85000.0, 2)
        self.assertTrue(any(abs(v - 1500.0) < 0.01 for v in ds["budgets"].values()), ds["budgets"])
        b = ds["areas"][ds["main_area"]]
        self.assertEqual(b["area"]["name"], "Privat")
        secs = {s["name"]: {z["row"]: z for z in s["rows"]} for s in b["cashflow"]["sections"]}
        self.assertAlmostEqual(secs["financing"]["Darlehen Lindenstraße / Tilgung"]["amounts"]["2026-10"], -600.0, 2)
        self.assertAlmostEqual(secs["financing"]["Darlehen Lindenstraße / Zinsen"]["amounts"]["2026-10"], -900.0, 2)
        self.assertAlmostEqual(secs["investing"]["Einlage/Entnahme Alpha GbR"]["amounts"]["2026-06"], -10000.0, 2)
        # GbR-Bereich: Mieteinnahmen in den Einnahmen, Verkaeuferdarlehen in der Finanzierung
        g = ds["areas"][F.uid("ga")]
        gs = {s["name"]: {z["row"]: z for z in s["rows"]} for s in g["cashflow"]["sections"]}
        self.assertIn("Vermietung", gs["income"])                                     # the position, its categories inside
        self.assertTrue(any("Mieteinnahmen" in d["category"] for d in gs["income"]["Vermietung"]["details"]))
        self.assertTrue(any("Verkäuferdarlehen" in k for k in gs["financing"]), list(gs["financing"]))
        # Umsatzliste ohne Gegen-IBAN
        ums = self.store.load("transactions.json")
        self.assertTrue(len(ums) > 300); self.assertNotIn("accountNumber", json.dumps(ums)); self.assertNotIn(F.SELLER_IBAN, json.dumps(ums))
        self.assertTrue(all(set(u) >= {"id", "account", "entity", "date", "amount", "category"} for u in ums))
        with open(self.store.path("dataset.json"), "rb") as fh:
            raw = fh.read()
        self.assertTrue(raw.startswith(b"MMT1")); self.assertNotIn(b"Privat", raw)

    def test_dry_run_writes_nothing(self):
        cfg = core.merged_config(self.store.load("config.json"))
        with self.assertLogs(level="DEBUG") as cm:
            res = core.run_once(self.store, cfg, TODAY, dry=True, force=True, bridge_factory=MockBridge)
        self.assertEqual(res["written"], 0); self.assertEqual(len(res["proposals"]), 24)
        # the plain-text log holds no amounts, payees, purposes or account names of the bookings
        logtext = "\n".join(cm.output)
        for p in res["proposals"]:
            self.assertNotIn(p["text"], logtext); self.assertNotIn(fmt_eur(p["amount"]), logtext)
        self.assertNotIn("Verkäuferdarlehen", logtext); self.assertNotIn("€", logtext)
        vd = [a for a in MockBridge.state["accounts"] if a["name"] == "Verkäuferdarlehen"][0]["balance"][0][0]
        self.assertEqual(vd, -1200000.0)
        self.assertTrue(any("Freigabe" in w for w in self.store.load("dataset.json")["warnings"]))

    def test_tax_report(self):
        led = Ledger(accounts_from_export(MockBridge.state["accounts"]), tx_from_export(MockBridge.state["txs"]))
        cfg = core.merged_config(config_for_test())
        t = build_tax(led, cfg, TODAY)
        pb = [e for e in t["entities"] if e["name"] == "Alpha GbR"][0]
        self.assertEqual(pb["kind"], "gbr"); self.assertEqual(pb["share"], 0.4)
        j = pb["years"]["2026"]
        self.assertIn("Parkweg", j["properties_list"])
        o = j["properties_list"]["Parkweg"]
        self.assertAlmostEqual(o["kinds"]["Mieteinnahmen"], 11 * 9500.0, 2)
        self.assertAlmostEqual(o["kinds"]["Hausgeld"], -11 * 800.0, 2)
        self.assertEqual(o["depreciation"], 40000.0)
        self.assertAlmostEqual(o["result"], 11 * 9500 - 11 * 800 - 40000, 2)
        self.assertAlmostEqual(o["share_result"], round(o["result"] * 0.4, 2), 2)
        priv = [e for e in t["entities"] if e["name"] == "Privat"][0]["years"]["2026"]
        self.assertIn("Anlage N (Arbeitslohn)", priv["positions"])
        self.assertAlmostEqual(priv["positions"]["Anlage N (Arbeitslohn)"]["amount"], 11 * 6500.0, 2)
        self.assertFalse(any("Umbuchung" in k["path"] for p in priv["positions"].values() for k in p["categories"]))

    def test_check_config_findings(self):
        led = Ledger(accounts_from_export(MockBridge.state["accounts"]), tx_from_export(MockBridge.state["txs"]))
        cfg = core.merged_config(config_for_test())
        f = core.check_config(led, MockBridge().export_categories(), cfg)
        self.assertFalse([x for x in f if x["severity"] == "error"], f)
        cfg["loans"][0]["loan_account"] = F.uid("priv.giro") + " | Hausbank Giro"
        f = core.check_config(led, [], cfg)
        self.assertTrue(any(x["severity"] == "error" and "Bankanbindung" in x["text"] for x in f))

    def test_package_roundtrip_and_mapping(self):
        led = Ledger(accounts_from_export(MockBridge.state["accounts"]), tx_from_export(MockBridge.state["txs"]))
        cfg = core.merged_config(config_for_test())
        pkg = core.export_package(cfg, "Test", strip_uuids=True, ledger=led)
        self.assertEqual(pkg["kontor_package"], 1)
        txt = json.dumps(pkg, ensure_ascii=False)
        self.assertNotIn(F.uid("ga.vd"), txt); self.assertNotIn("ui", pkg["config"]); self.assertIn("Verkäuferdarlehen", txt)
        new_cfg, unresolved, report = core.import_package(core.merged_config({}), pkg, led, "merge")
        self.assertEqual(unresolved, [], unresolved)
        self.assertEqual(new_cfg["loans"][0]["loan_account"].split(" | ")[0], F.uid("ga.vd"))
        self.assertEqual(len(new_cfg["companies"]), 2)
        pkg2 = copy.deepcopy(pkg); pkg2["config"]["loans"][0]["loan_account"] = "Darlehen Fremd"
        _, unresolved, _ = core.import_package(core.merged_config({}), pkg2, led, "merge")
        self.assertEqual(len(unresolved), 1); self.assertEqual(unresolved[0]["label"], "Darlehen Fremd")
        new_cfg, unresolved, _ = core.import_package(core.merged_config({}), pkg2, led, "merge", {"Darlehen Fremd": F.uid("ga.vd") + " | Verkäuferdarlehen"})
        self.assertEqual(unresolved, []); self.assertIn(F.uid("ga.vd"), new_cfg["loans"][0]["loan_account"])
        again, _, _ = core.import_package(new_cfg, pkg, led, "merge")
        self.assertEqual(len(again["loans"]), 1)

    def test_diagnose_masks(self):
        cfg = core.merged_config(self.store.load("config.json"))
        core.run_once(self.store, cfg, TODAY, dry=True, force=True, bridge_factory=MockBridge)
        with open(os.path.join(self.dir, "kontor.log"), "w") as f:
            f.write("2026-11-04 INFO Lauf fuer Stadtbank Kontokorrent IBAN DE02701500000000594937 Saldo 1234567\n")
        txt = core.diagnose(self.store, self.dir, cfg, {"version": "x"}, mask_names=True)
        self.assertNotIn("DE02701500000000594937", txt); self.assertNotIn(F.SELLER_IBAN, txt)
        self.assertNotIn("Stadtbank Kontokorrent", txt); self.assertIn("Konto", txt)
        self.assertNotIn("1234567", txt)

    def test_update_check_offline(self):
        info = updates.check("stecrz/Kontor")
        self.assertIn("current", info)
        self.assertTrue(info["error"] or info["available"])
        with self.assertRaises(ValueError):
            updates._get("https://evil.example/x.zip")

    def test_update_check_uses_archive_urls(self):
        """Quelle ist VERSION im Hauptzweig (Tags nicht noetig); Archiv ueber github.com/.../archive (nicht API-Zipball, 415).
        Ohne lesbare VERSION: Release, sonst hoechster Tag."""
        calls = []

        def fake_get(url, accept="application/vnd.github+json"):
            calls.append(url)
            if url.endswith("/main/VERSION"):
                return b"9.9.9\n"
            if url.endswith("/main/CHANGELOG.md"):
                return "# Änderungen\n\n## 9.9.9\n- Neu A\n- Neu B\n\n## 9.9.8\n- alt\n".encode()
            raise AssertionError(url)
        old = updates._get; updates._get = fake_get
        try:
            info = updates.check("stecrz/Kontor")
        finally:
            updates._get = old
        self.assertEqual(info["available"], "9.9.9"); self.assertTrue(info["newer"]); self.assertEqual(info["source"], "main")
        self.assertEqual(info["zip"], "https://github.com/stecrz/Kontor/archive/refs/heads/main.zip")
        self.assertEqual(info["notes"], "- Neu A\n- Neu B")

        def fake_get2(url, accept="application/vnd.github+json"):
            if url.endswith("/main/VERSION"):
                raise urllib.error.HTTPError(url, 404, "nf", {}, None)
            if url.endswith("/releases/latest"):
                raise urllib.error.HTTPError(url, 404, "nf", {}, None)
            if url.endswith("/tags"):
                return json.dumps([{"name": "v9.9.10"}, {"name": "v9.9.9"}, {"name": "v10.0.0"}]).encode()
            raise AssertionError(url)
        updates._get = fake_get2
        try:
            info = updates.check("stecrz/Kontor")
        finally:
            updates._get = old
        self.assertEqual(info["available"], "v10.0.0"); self.assertEqual(info["source"], "tag")
        self.assertEqual(info["zip"], "https://github.com/stecrz/Kontor/archive/refs/tags/v10.0.0.zip")
        self.assertEqual(updates.archive_url("a/b", "main", "heads"), "https://github.com/a/b/archive/refs/heads/main.zip")
        self.assertIsNone(updates.install_via_git(restart=False)) if not os.path.isdir(os.path.join(updates.HERE, ".git")) else None

    def test_update_install_from_archive(self):
        """Archiv wie von GitHub (Wurzelordner mit kontor.py + VERSION) wird in den Programmordner eingespielt -- direkt, ohne
        Sicherung; was die vorige Version brachte und die neue nicht mehr hat, wird entfernt (nur das, nie andere Dateien)."""
        src = os.path.join(os.path.dirname(__file__), "..")
        prog = os.path.join(self.dir, "prog")
        shutil.copytree(src, prog, ignore=shutil.ignore_patterns("tests", "__pycache__", ".git", ".old"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for root, dirs, files in os.walk(prog):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, prog)
                    data = open(full, "rb").read()
                    if rel == "VERSION":
                        data = b"9.9.9\n"
                    if rel == "web/app.js":
                        data = b"// neu\n" + data
                    z.writestr("stecrz-Kontor-abc123/" + rel, data)
            z.writestr("stecrz-Kontor-abc123/neu.txt", b"x")
        os.makedirs(os.path.join(prog, ".old")); open(os.path.join(prog, ".old", "VERSION"), "w").write("1.0.0")      # a backup of before
        open(os.path.join(prog, "weg.py"), "w").write("x"); open(os.path.join(prog, "eigen.txt"), "w").write("x")
        open(os.path.join(prog, ".files"), "w").write("weg.py\nVERSION\n../draussen.txt\n")      # the version before brought weg.py
        open(os.path.join(self.dir, "draussen.txt"), "w").write("x")
        old_get, old_here = updates._get, updates.HERE
        updates._get = lambda url, accept="": buf.getvalue()
        updates.HERE = prog
        try:
            res = updates.install("stecrz/Kontor", zip_url="https://codeload.github.com/stecrz/Kontor/zip/main", restart=False)
        finally:
            updates._get, updates.HERE = old_get, old_here
        self.assertTrue(res["ok"], res); self.assertEqual(res["version"], "9.9.9")
        self.assertEqual(open(os.path.join(prog, "VERSION")).read().strip(), "9.9.9")
        self.assertTrue(open(os.path.join(prog, "web", "app.js")).read().startswith("// neu"))
        self.assertTrue(os.path.exists(os.path.join(prog, "neu.txt")))
        self.assertFalse(os.path.exists(os.path.join(prog, ".old")))                         # no backup (an old one: gone)
        self.assertFalse(os.path.exists(os.path.join(prog, "weg.py")))                        # no longer part of Kontor: removed
        self.assertTrue(os.path.exists(os.path.join(prog, "eigen.txt")))                      # never brought by an update: stays
        self.assertTrue(os.path.exists(os.path.join(self.dir, "draussen.txt")))               # outside the program folder: never
        listed = open(os.path.join(prog, ".files")).read().split()
        self.assertIn("web/app.js", listed); self.assertIn("neu.txt", listed); self.assertNotIn("weg.py", listed)
        self.assertFalse([x for x in listed if x.startswith(".")])                            # no hidden folders (.github, .claude)
        self.assertFalse(os.path.exists(os.path.join(prog, "tests")))
        # again, with the cases that must not go wrong: a renamed case of a name stays (the Mac's disks are alike for both);
        # a linked folder leads outside: nothing deleted there; stopped half-way: the old number, offered again, nothing restarted
        out = os.path.join(self.dir, "fremd"); os.makedirs(out); open(os.path.join(out, "alt.md"), "w").write("x")
        os.symlink(out, os.path.join(prog, "verlinkt"))
        open(os.path.join(prog, "Kontor_Alt.py"), "w").write("x")
        open(os.path.join(prog, ".files"), "a").write("verlinkt/alt.md\nKontor_Alt.py\n")
        buf2 = io.BytesIO()
        with zipfile.ZipFile(buf2, "w") as z, zipfile.ZipFile(buf) as z0:
            for n in z0.namelist():
                z.writestr(n, b"9.9.10\n" if n.endswith("/VERSION") else z0.read(n))
            z.writestr("stecrz-Kontor-abc123/kontor_alt.py", b"y")
        updates._get = lambda url, accept="": buf2.getvalue(); updates.HERE = prog
        try:
            self.assertTrue(updates.install("stecrz/Kontor", zip_url="https://codeload.github.com/x", restart=False)["ok"])
        finally:
            updates._get, updates.HERE = old_get, old_here
        self.assertTrue(os.path.exists(os.path.join(out, "alt.md")))                          # behind a link: never
        self.assertTrue(os.path.exists(os.path.join(prog, "Kontor_Alt.py")))                  # only its case changed: kept
        buf3 = io.BytesIO()
        with zipfile.ZipFile(buf3, "w") as z, zipfile.ZipFile(buf2) as z0:
            for n in z0.namelist():
                z.writestr(n, b"9.9.11\n" if n.endswith("/VERSION") else z0.read(n))
        real_copy = updates.shutil.copy2
        def stop(a, b, **kw):
            if os.sep + "web" + os.sep in b:
                raise OSError("Festplatte voll")
            return real_copy(a, b, **kw)
        updates._get = lambda url, accept="": buf3.getvalue(); updates.HERE = prog; updates.shutil.copy2 = stop
        try:
            res = updates.install("stecrz/Kontor", zip_url="https://codeload.github.com/x", restart=False)
        finally:
            updates._get, updates.HERE, updates.shutil.copy2 = old_get, old_here, real_copy
        self.assertFalse(res["ok"]); self.assertIn("Festplatte voll", res["text"])
        self.assertEqual(open(os.path.join(prog, "VERSION")).read().strip(), "9.9.10")         # the old number: offered again
        self.assertFalse([d for d in os.listdir(tempfile.gettempdir()) if d.startswith("kontor-update-") and os.path.getmtime(os.path.join(tempfile.gettempdir(), d)) > time.time() - 30])
        # no list yet (the first update with this code): nothing removed
        os.remove(os.path.join(prog, ".files")); open(os.path.join(prog, "bleibt.py"), "w").write("x")
        updates._get = lambda url, accept="": buf3.getvalue(); updates.HERE = prog
        try:
            self.assertTrue(updates.install("stecrz/Kontor", zip_url="https://codeload.github.com/x", restart=False)["ok"])
        finally:
            updates._get, updates.HERE = old_get, old_here
        self.assertTrue(os.path.exists(os.path.join(prog, "bleibt.py"))); self.assertEqual(open(os.path.join(prog, "VERSION")).read().strip(), "9.9.11")


class TailscaleTests(unittest.TestCase):
    """Tailscale state with a stand-in CLI: reason when not connected, certificate via stdout (works with the sandboxed App Store variant)."""
    def fake(self, body):
        d = tempfile.mkdtemp(prefix="kontor-ts-")
        p = os.path.join(d, "tailscale")
        with open(p, "w") as f:
            f.write("#!/bin/sh\n" + body)
        os.chmod(p, 0o755)
        return d, p

    def test_status_and_cert(self):
        import tls_cert
        orig = tls_cert.find_tailscale
        try:
            d, p = self.fake('echo "The Tailscale GUI failed to start."; exit 1\n')
            tls_cert.find_tailscale = lambda: p
            st = tls_cert.status()
            self.assertTrue(st["found"]); self.assertFalse(st["connected"]); self.assertIn("GUI failed", st["error"])
            d, p = self.fake('echo \'{"BackendState": "NeedsLogin", "Self": {}}\'\n')
            tls_cert.find_tailscale = lambda: p
            st = tls_cert.status()
            self.assertFalse(st["connected"]); self.assertEqual(st["state"], "NeedsLogin"); self.assertNotIn("error", st)
            pem = "-----BEGIN CERTIFICATE-----\\nQUFB\\n-----END CERTIFICATE-----\\n-----BEGIN EC PRIVATE KEY-----\\nS0tL\\n-----END EC PRIVATE KEY-----"
            d, p = self.fake('if [ "$1" = cert ]; then printf "%s\\n" "' + pem + '"; fi\n')
            crt, key = tls_cert.issue(p, "mac.example.ts.net", d)
            self.assertIn("BEGIN CERTIFICATE", open(crt).read()); self.assertIn("PRIVATE KEY", open(key).read())
            self.assertNotIn("PRIVATE KEY", open(crt).read())
            self.assertEqual(os.stat(key).st_mode & 0o777, 0o600)
        finally:
            tls_cert.find_tailscale = orig


class TailscaleLocalApiTests(unittest.TestCase):
    """Tailscale app's local interface (127.0.0.1, token from the "sameuserproof" file): status and certificate without the CLI."""
    def test_localapi(self):
        import tls_cert
        from http.server import BaseHTTPRequestHandler
        self.assertEqual(tls_cert.parse_proof("p123\nn/Users/x/Library/Group Containers/ABC.io.tailscale.ipn.macos/sameuserproof-12345-0badc0de\n"), (12345, "0badc0de"))       # made up
        self.assertIsNone(tls_cert.parse_proof("nothing here"))
        seen = []
        rules = [[{"SrcIPs": ["*"], "DstPorts": [{"IP": "*", "Ports": {"First": 0, "Last": 65535}}]}]]     # Tailscale's default: everything
        pem = "-----BEGIN EC PRIVATE KEY-----\nS0tL\n-----END EC PRIVATE KEY-----\n-----BEGIN CERTIFICATE-----\nQUFB\n-----END CERTIFICATE-----\n"

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                seen.append((self.path, self.headers.get("Host"), self.headers.get("Authorization")))
                if self.headers.get("Authorization") != "Basic " + base64.b64encode(b":tok123").decode():
                    self.send_response(401); self.end_headers(); return
                if self.path == "/localapi/v0/status":
                    body = json.dumps({"BackendState": "Running", "Self": {"DNSName": "mac.example.ts.net.", "TailscaleIPs": ["100.101.102.103", "fd7a::1"]},
                                       "CertDomains": ["mac.example.ts.net"], "Peer": {"x": {"HostName": "iPhone", "OS": "iOS", "Online": True}}}).encode()
                elif self.path == "/localapi/v0/cert/mac.example.ts.net?type=pair":
                    body = pem.encode()
                elif self.path == "/localapi/v0/debug-packet-filter-rules":
                    body = json.dumps(rules[0]).encode()
                else:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200); self.end_headers(); self.wfile.write(body)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        orig_ep, orig_find = tls_cert.localapi_endpoint, tls_cert.find_tailscale
        try:
            tls_cert.localapi_endpoint = lambda: (srv.server_address[1], "tok123")
            tls_cert.find_tailscale = lambda: None                                  # no CLI at all
            st = tls_cert.status()
            self.assertTrue(st["connected"]); self.assertEqual((st["name"], st["ip"]), ("mac.example.ts.net", "100.101.102.103"))
            self.assertTrue(st["https"]); self.assertEqual(st["devices"][0]["name"], "iPhone")
            self.assertEqual(seen[0][1], "local-tailscaled.sock")
            d = tempfile.mkdtemp(prefix="kontor-tls-")
            crt, key = tls_cert.issue(None, "mac.example.ts.net", d)
            self.assertIn("BEGIN CERTIFICATE", open(crt).read()); self.assertIn("PRIVATE KEY", open(key).read())
            self.assertEqual(os.stat(key).st_mode & 0o777, 0o600)
            # which ports Tailscale lets in: default -> everything open; Kontor's rule -> only Kontor; wrong port -> Kontor blocked
            a = tls_cert.access_check(8765); self.assertEqual(a["state"], "open"); self.assertTrue(a["all"])
            rules[0] = [{"SrcIPs": ["100.64.0.0/10"], "DstPorts": [{"IP": "100.101.102.103", "Ports": {"First": 8765, "Last": 8765}}]}]
            self.assertEqual(tls_cert.access_check(8765)["state"], "secured")
            self.assertEqual(tls_cert.access_check(9000)["state"], "locked")
            rules[0].append({"SrcIPs": ["*"], "DstPorts": [{"IP": "*", "Ports": {"First": 22, "Last": 22}}]})
            a = tls_cert.access_check(8765); self.assertEqual((a["state"], a["all"], a["ports"]), ("open", False, [[22, 22]]))
            tls_cert.localapi_endpoint = lambda: (srv.server_address[1], "wrong")   # wrong token: message, no crash
            self.assertEqual(tls_cert.access_check(8765)["state"], "unknown")
            st = tls_cert.status()
            self.assertFalse(st["connected"]); self.assertIn("401", st["error"])
        finally:
            tls_cert.localapi_endpoint, tls_cert.find_tailscale = orig_ep, orig_find
            srv.shutdown()


class IncrementalReadTests(unittest.TestCase):
    """Schnelles Lesen: nur die letzten 30 Tage aus MoneyMoney, aeltere Umsaetze aus dem letzten vollstaendigen Stand."""
    def setUp(self):
        reset_mock(); patch_today()
        self.cfg = core.merged_config(config_for_test("/tmp/kontor-belege-test"))

    def test_merge_equals_full_read(self):
        from datetime import datetime as dt
        full = core.fetch(MockBridge(True), self.cfg, TODAY)
        self.assertFalse(full.incremental); self.assertIsNotNone(full.full_at)
        # In-Memory-Ueberlagerungen des letzten Stands (Probelauf-Buchung, Kontor-Kategorie) duerfen nicht mitwandern
        full.post(F.uid("priv.giro"), TODAY, -1.0, "Probelauf", "x")
        old = next(t for t in full.txs if t.id > 0 and t.booking_date < TODAY - timedelta(days=200))
        old.mm_category_path, old.category_path = old.category_path, "Kontor \\ Eigene"
        # in MoneyMoney: neuer Umsatz heute, ein vorgemerkter verschwindet
        MockBridge.state["txs"].append(F.tx("priv.giro", TODAY, -42.0, "Bäcker", "Brot", "Haushalt\\Lebensmittel"))
        pend = F.tx("priv.giro", TODAY - timedelta(days=2), -9.0, "Kiosk", "vorgemerkt", booked=False)
        MockBridge.state["txs"].append(pend)
        mid = core.fetch(MockBridge(True), self.cfg, TODAY, base=core.fetch(MockBridge(True), self.cfg, TODAY), full=False)
        self.assertIn(pend["id"], {t.id for t in mid.txs})
        MockBridge.state["txs"].remove(pend)
        inc = core.fetch(MockBridge(True), self.cfg, TODAY, base=full, full=False)
        ref = core.fetch(MockBridge(True), self.cfg, TODAY)
        self.assertTrue(inc.incremental); self.assertEqual(inc.full_at, full.full_at)
        self.assertNotIn(pend["id"], {t.id for t in inc.txs})                 # in MoneyMoney geloescht -> weg
        self.assertFalse([t for t in inc.txs if t.id < 0])                    # keine Probelauf-Buchungen
        o2 = next(t for t in inc.txs if t.id == old.id)
        self.assertEqual(o2.category_path, old.mm_category_path); self.assertIsNone(o2.mm_category_path)
        self.assertEqual([t.id for t in inc.txs], [t.id for t in ref.txs])     # gleiche Umsaetze wie beim vollstaendigen Lesen
        self.assertEqual(core.fingerprint(inc), core.fingerprint(ref))
        # anderer Zeitraum (Historie geaendert) -> vollstaendig
        cfg2 = dict(self.cfg, balance=dict(self.cfg["balance"], months_back=6))
        self.assertFalse(core.fetch(MockBridge(True), cfg2, TODAY, base=full, full=False).incremental)
        # Cache behaelt Zeitraum und Zeitpunkt des vollstaendigen Lesens
        from model import ledger_from_bytes, ledger_to_bytes
        back, _ = ledger_from_bytes(ledger_to_bytes(full))
        self.assertEqual((back.since, back.full_at), (full.since, full.full_at))
        self.assertIsInstance(back.full_at, dt)

    def test_full_read_due(self):
        from datetime import datetime as dt
        import service as MA
        app = MA.App.__new__(MA.App)
        app.config = {"schedule": {"full_read_days": 7}}
        app.ledger = None
        self.assertTrue(app.full_read_due())
        app.ledger = type("L", (), {})(); app.ledger.full_at = dt(2026, 11, 4, 15, 0)
        self.assertFalse(app.full_read_due(dt(2026, 11, 5, 3, 0)))            # nachts: kein Sonderfall mehr
        self.assertFalse(app.full_read_due(dt(2026, 11, 11, 14, 0)))          # knapp 7 Tage
        self.assertTrue(app.full_read_due(dt(2026, 11, 11, 15, 0)))           # 7 Tage
        app.config = {}
        self.assertEqual(app.full_read_info()["days"], 30)                     # Standard

    def test_late_booking_triggers_full_read(self):
        """Nachtraegliche Buchung mit altem Datum (vor dem 30-Tage-Fenster): der Kontostand passt nicht mehr -> alles lesen."""
        from datetime import datetime as dt
        full = core.fetch(MockBridge(True), self.cfg, TODAY)
        full.post(F.uid("priv.giro"), TODAY, -1.0, "Probelauf", "x")           # Probelauf veraendert nur Kontors Saldo
        full.full_at = dt.now() - timedelta(hours=13)
        self.assertTrue(core.fetch(MockBridge(True), self.cfg, TODAY, base=full, full=False).incremental)   # nichts geaendert
        late = F.tx("priv.giro", TODAY - timedelta(days=45), -77.0, "Nachzuegler", "spaet gebucht", "")
        MockBridge.state["txs"].append(late)
        for a in MockBridge.state["accounts"]:
            if a["uuid"] == F.uid("priv.giro"):
                a["balance"][0][0] = round(a["balance"][0][0] - 77.0, 2)
        full.full_at = dt.now() - timedelta(hours=1)                           # gerade erst komplett gelesen -> nicht schon wieder
        self.assertTrue(core.fetch(MockBridge(True), self.cfg, TODAY, base=full, full=False).incremental)
        full.full_at = dt.now() - timedelta(hours=13)
        r = core.fetch(MockBridge(True), self.cfg, TODAY, base=full, full=False)
        self.assertFalse(r.incremental)
        self.assertIn(late["id"], {t.id for t in r.txs})


    def test_categories_rearranged_in_moneymoney(self):
        """Moved to another category, a category renamed or deleted in MoneyMoney: everything is read again and what you set
        for the category in Kontor follows."""
        from datetime import datetime as dt
        full = core.fetch(MockBridge(True), self.cfg, TODAY)
        full.full_at = dt.now() - timedelta(hours=1)
        recent = [t for t in MockBridge.state["txs"] if t.get("categoryPath") and mm_bridge.local_date(t["bookingDate"]) >= TODAY - timedelta(days=20)]
        fresh = [t for t in recent if not t.get("x")][:1]
        self.assertTrue(fresh)
        # the first category of one that had none: the quick read is enough
        blank = [t for t in MockBridge.state["txs"] if not t.get("categoryPath") and mm_bridge.local_date(t["bookingDate"]) >= TODAY - timedelta(days=20)]
        if blank:
            blank[0]["categoryPath"] = blank[0]["category"] = "Lebensmittel"
            self.assertTrue(core.fetch(MockBridge(True), self.cfg, TODAY, base=full, full=False).incremental)
        # moved from one category to another: older ones may have moved as well
        fresh[0]["categoryPath"] = fresh[0]["category"] = "Lebensmittel" if fresh[0]["categoryPath"] != "Lebensmittel" else "Zinsen"
        self.assertFalse(core.fetch(MockBridge(True), self.cfg, TODAY, base=full, full=False).incremental)
        # the tree: ids decide (never names)
        old = [{"uuid": "1", "path": "Einkommen"}, {"uuid": "2", "path": "Einkommen\\Lohn"}, {"uuid": "3", "path": "Sparen"}, {"uuid": "4", "path": "Alt"}]
        new = [{"uuid": "1", "path": "Einnahmen"}, {"uuid": "2", "path": "Einnahmen\\Gehalt"}, {"uuid": "3", "path": "Sparen"}]
        self.assertNotEqual(core.category_tree(old), core.category_tree(new)); self.assertEqual(core.category_tree(old), core.category_tree(copy.deepcopy(old)))
        cfg = {"cashflow": {"positions": {"Einkommen / Lohn": "work_income", "Alt": "ignore", "Sparen": "saving"},
                                "category_to_account": {"Alt": "x", "Sparen": "y"}},
               "real_estate": [{"name": "Haus", "category": "Einkommen\\Lohn"}]}
        got = core.follow_categories(cfg, old, new)
        self.assertEqual(got["cashflow"]["positions"], {"Einnahmen / Gehalt": "work_income", "Sparen": "saving"})
        self.assertEqual(got["cashflow"]["category_to_account"], {"Sparen": "y"})
        self.assertEqual(got["real_estate"][0]["category"], "Einnahmen\\Gehalt")
        self.assertIsNone(core.follow_categories(cfg, old, copy.deepcopy(old)))
        self.assertIsNone(core.follow_categories(cfg, [], new))                           # nothing to compare with: nothing changes
        # one deleted, another renamed into its name: the renamed one's choice counts; deleted and made again: its choice stays
        old = [{"uuid": "1", "path": "Essen"}, {"uuid": "2", "path": "Lebensmittel"}, {"uuid": "3", "path": "A"}, {"uuid": "4", "path": "B"}, {"uuid": "5", "path": "C"}]
        cfg = {"cashflow": {"positions": {"Essen": "living", "Lebensmittel": "ignore", "C": "leisure"}}}
        got = core.follow_categories(cfg, old, [{"uuid": "1", "path": "Lebensmittel"}, {"uuid": "3", "path": "A"}, {"uuid": "4", "path": "B"}, {"uuid": "9", "path": "C"}])
        self.assertEqual(got["cashflow"]["positions"], {"Lebensmittel": "living", "C": "leisure"})
        # another set of categories altogether (another database opened in MoneyMoney): nothing is dropped
        self.assertIsNone(core.follow_categories(cfg, old, [{"uuid": "x%d" % i, "path": "Neu %d" % i} for i in range(6)]))
        # ... but one renamed in a big tidy-up still follows (by its id)
        got = core.follow_categories(cfg, old, [{"uuid": "1", "path": "Nahrung"}] + [{"uuid": "x%d" % i, "path": "Neu %d" % i} for i in range(6)])
        self.assertEqual(got["cashflow"]["positions"], {"Lebensmittel": "ignore", "C": "leisure", "Nahrung": "living"})
        # MoneyMoney's default category counts as none: its first real category is no move
        import categorize
        std, categorize.STANDARD = categorize.STANDARD, {"Unkategorisiert"}
        try:
            base = core.fetch(MockBridge(True), self.cfg, TODAY)
            t0 = next(t for t in base.txs if t.id > 0)
            t0.category_path = t0.mm_category_path = "Unkategorisiert"
            import dataclasses
            self.assertEqual(core.recategorized(base, [dataclasses.replace(t0, category_path="Lebensmittel")]), 0)
            t0.category_path = t0.mm_category_path = "Zinsen"
            self.assertEqual(core.recategorized(base, [dataclasses.replace(t0, category_path="Lebensmittel")]), 1)
        finally:
            categorize.STANDARD = std

    def test_settings_of_deleted_accounts_go(self):
        led = core.fetch(MockBridge(True), self.cfg, TODAY)
        cfg = copy.deepcopy(self.cfg)
        gone = "0d8ae4d1-0000-4000-8000-000000000000 | Gibt es nicht mehr"
        bil = cfg.setdefault("balance", {})
        bil.setdefault("roles", {})[gone] = "participations"; bil.setdefault("history_source", {})[gone] = "balances"
        bil["hidden_accounts"] = [gone]
        n = len(bil["roles"])
        self.assertFalse([f for f in core.check_config(led, [], core.merged_config(cfg)) if f["severity"] == "error"])     # no finding ...
        out = core.prune_account_settings(cfg, led)
        self.assertEqual((len(out["balance"]["roles"]), gone in out["balance"]["history_source"], out["balance"]["hidden_accounts"]), (n - 1, False, []))   # ... and gone with the next save
        self.assertEqual(core.prune_account_settings(cfg, None), cfg)
        # a name alone that is unknown stays a finding (nothing says the account was deleted); many gone at once: another
        # database is open -- nothing is dropped
        cfg2 = copy.deepcopy(self.cfg); cfg2.setdefault("balance", {}).setdefault("roles", {})["Konto das es nie gab"] = "other"
        self.assertTrue([f for f in core.check_config(led, [], core.merged_config(cfg2)) if f["severity"] == "error"])
        self.assertIn("Konto das es nie gab", core.prune_account_settings(cfg2, led)["balance"]["roles"])
        cfg3 = {"balance": {"roles": {"%08d-0000-4000-8000-000000000000 | X%d" % (i, i): "other" for i in range(8)}}}
        self.assertEqual(core.prune_account_settings(cfg3, led), cfg3)
        cfg4 = {"balance": {"roles": {}, "history_source": {"%08d-0000-4000-8000-000000000000 | X%d" % (i, i): "balances" for i in range(8)}}}
        self.assertEqual(core.prune_account_settings(cfg4, led), cfg4)


class _AppBase(unittest.TestCase):
    """Gemeinsamer Aufbau: Dienst auf freiem Port, Cookie-Jar, CSRF."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-app-")
        key, src = load_or_create_master_key(self.dir)
        self.store = Store(self.dir, key, src)
        self.belege = os.path.join(self.dir, "Belege")
        self.store.save("config.json", config_for_test(self.belege))
        self.store.save("state.json", dict(ALL_NEW))
        reset_mock()
        patch_today()
        self.app = App(self.store, self.dir, bridge_factory=MockBridge)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def call(self, path, body=None, method=None, csrf=True, origin=None, raw=False, warten=True):
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        if warten and isinstance(body, dict) and "wait" not in body:
            body = {**body, "wait": True}        # Tests warten auf den Berichtsneubau (Oberflaeche: im Hintergrund)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if csrf and self.csrf:
            req.add_header("X-CSRF-Token", self.csrf)
        if origin:
            req.add_header("Origin", origin)
        try:
            with self.opener.open(req) as r:
                payload = r.read()
                return (r.status, payload, dict(r.headers)) if raw else (r.status, json.loads(payload.decode() or "{}"))
        except urllib.error.HTTPError as e:
            payload = e.read()
            return (e.code, payload, dict(e.headers)) if raw else (e.code, json.loads(payload.decode() or "{}"))

    def login(self):
        code, s = self.call("/api/session")
        self.assertTrue(s["setup_needed"])
        code, r = self.call("/api/setup", {"password": "kurz"})
        self.assertEqual(code, 400)
        code, r = self.call("/api/setup", {"password": "sehr-geheimes-passwort"})
        self.assertEqual(code, 200); self.csrf = r["csrf"]

    def run_and_wait(self):
        code, r = self.call("/api/run", {"dry_run": False, "force": True})
        self.assertEqual(code, 202)
        for _ in range(200):
            time.sleep(0.1)
            if not self.app.running and self.app.last_run_at:
                break
        self.wait_report()

    def wait_report(self):
        """The report follows a run in the background."""
        with self.app.rebuild_cv:
            self.app.rebuild_cv.wait_for(lambda: not self.app.rebuild_running and not self.app.rebuild_pending, timeout=60)


class AppTests(_AppBase):
    """Dienst ueber HTTP: Einrichtung, Anmeldung, CSRF, Daten, Plan, Konfiguration, Lauf, Belege, Exporte."""

    def test_run_reports_its_step_and_the_report_follows(self):
        """The status says what a run does; the report is built afterwards in the background (the bookings are there at once)."""
        self.login()
        code, st = self.call("/api/status"); self.assertIn("step", st["service"]); self.assertIsNone(st["service"]["step"])
        res = self.app.do_run(False, True)
        self.assertEqual(res["status"], "ok"); self.assertIsNone(self.app.run_step)
        self.wait_report()
        self.assertTrue(self.app.dataset().get("areas"))

    def test_approval_list_recalculated(self):
        """The approval list for your selection, from the last state read (nothing written); dropping one plans the rest again."""
        self.login()
        self.app.config["dry_run"] = True
        self.app.do_run(True, True)
        props = self.store.load("state.json")["last_run"]["proposals"]
        k = next(p["key"] for p in props if p["kind"] == "repayment")
        n_txs = len(MockBridge.state["txs"])
        code, r = self.call("/api/bookings/plan", {"hold": [k], "changes": {}})
        self.assertEqual(code, 200); rows = {p["key"]: p["amount"] for p in r["proposals"]}
        self.assertNotIn(k, rows); self.assertEqual(len(MockBridge.state["txs"]), n_txs)
        moved = [x for x in props if x["key"] in rows and abs(rows[x["key"]] - x["amount"]) >= 0.005]
        self.assertEqual([x["kind"] for x in moved], ["value"])
        self.assertEqual(self.call("/api/bookings/plan", {"hold": ["rm -rf"]})[0], 400)
        self.assertEqual(self.call("/api/bookings/plan", {"hold": [], "changes": {k: {"amount": "0"}}})[0], 400)
        # dropped: the list waiting is planned again without it (the same amounts as above)
        self.assertEqual(self.call("/api/bookings/reject", {"key": k})[0], 200)
        lr = self.store.load("state.json")["last_run"]
        self.assertTrue(lr["dry_run"]); self.assertEqual({p["key"]: p["amount"] for p in lr["proposals"]}, rows)

    def test_refresh_reads_only_the_accounts_of_the_rules(self):
        """"Aktualisieren" under Auto bookings: only the accounts the rules read or book are read again, the approval list
        planned again; nothing is written, and the next sync still sees what changed in MoneyMoney."""
        self.login()
        self.app.do_run(False, True)                                        # all booked
        self.app.config["dry_run"] = True
        fp = self.store.load("state.json")["fingerprint"]
        txs = MockBridge.state["txs"]; wert = next(t for t in txs if "#kontor-wert-" in (t.get("purpose") or ""))
        txs.remove(wert)                                                    # deleted in MoneyMoney
        acc = next(a for a in MockBridge.state["accounts"] if a["uuid"] == wert["accountUuid"]); acc["balance"][0][0] = round(acc["balance"][0][0] - wert["amount"], 2)
        MockBridge.reads.clear(); n_txs = len(txs); n_hist = len(self.store.load("state.json")["history_source"])
        code, r = self.call("/api/bookings/refresh", {})
        self.assertEqual(code, 200); self.assertEqual((r["status"], r["wartend"]), ("ok", 1))
        reads = set(MockBridge.reads)
        self.assertNotIn(None, reads)                                       # not all accounts
        self.assertTrue({wert["accountUuid"], F.uid("ga.vd"), F.uid("ga.kk"), F.uid("priv.bet.gb")} <= reads)
        self.assertNotIn(F.uid("priv.giro"), reads)
        lr = self.store.load("state.json")["last_run"]
        self.assertTrue(lr["dry_run"]); self.assertEqual([p["account_id"] for p in lr["proposals"]], [wert["accountUuid"]])
        self.assertEqual(len(txs), n_txs); self.assertEqual(self.store.load("state.json")["fingerprint"], fp)
        self.assertEqual(len(self.store.load("state.json")["history_source"]), n_hist)          # no check of its own in the history
        self.assertNotIn(wert["id"], {t.id for t in self.app.ledger.txs})  # the state read now is the one the list is planned on
        code, r = self.call("/api/bookings/plan", {"hold": [], "changes": {}})
        self.assertEqual([p["key"] for p in r["proposals"]], [p["key"] for p in lr["proposals"]])

    def test_unchanged_read_keeps_warm_state(self):
        """Unveraenderte Daten aus MoneyMoney: bisheriger Stand (mit Zwischenergebnissen) bleibt, nur der Lesezeitpunkt wird neu."""
        self.login(); self.run_and_wait()
        self.assertFalse(self.app.full_read_due())   # own bookings need no full read: the ledger keeps them until the next one
        led, t0 = self.app.ledger, self.app.ledger_time
        self.app.do_run(True, False)                 # after own bookings: a quick read is enough
        led = self.app.ledger
        self.assertFalse(self.app.full_read_due()); self.assertTrue(led.incremental)
        # the accounts of the rules are read in full at every quick read: the bookings written back to January are there as
        # MoneyMoney has them (no stand-ins), nothing is proposed again
        jan = [t for t in led.txs if "#kontor-zins-2026-01" in t.purpose]
        self.assertEqual(len(jan), 1); self.assertGreater(jan[0].id, 0)
        self.assertIn(F.uid("ga.vd"), set(MockBridge.reads)); self.assertNotIn(F.uid("priv.giro"), set(MockBridge.reads))
        again = self.app.do_run(True, True); self.assertEqual(again["proposals"], []); self.assertTrue(self.app.ledger.incremental)
        led = self.app.ledger
        time.sleep(0.01)
        self.assertEqual(self.app.do_run(None, False)["status"], "unchanged")
        self.assertIs(self.app.ledger, led); self.assertGreater(self.app.ledger_time, t0)
        self.app.refresh_ledger(); self.assertIs(self.app.ledger, led)
        # Bankabruf ohne neue Daten: keine Neuberechnung, aber die Abrufzeit ist aktuell
        giro = next(a for a in MockBridge.state["accounts"] if a["uuid"] == F.uid("priv.giro"))
        vorher = led.accounts[F.uid("priv.giro")].refresh
        giro["refreshTimestamp"] = F._dt(date(2026, 11, 3))
        self.assertEqual(self.app.do_run(None, False)["status"], "unchanged")
        self.assertIs(self.app.ledger, led); self.assertNotEqual(led.accounts[F.uid("priv.giro")].refresh, vorher)
        MockBridge.state["accounts"][-1]["name"] += " neu"     # Kontoname geaendert -> neuer Stand
        self.assertNotEqual(self.app.do_run(None, False)["status"], "unchanged")
        self.assertIsNot(self.app.ledger, led)

    def test_receipt_pattern_only_known_placeholders(self):
        """A sub-folder pattern with braces around anything but the placeholders is not saved (at the Mac too)."""
        self.login()
        for pat, want in (("{jahr}", 400), ("{year}/{entity}/{nope}", 400), ("../{year}", 400), ("{year}-{month}", 200)):
            cfg = copy.deepcopy(self.app.config); cfg.setdefault("receipts", {})["subfolder"] = pat
            code, r = self.call("/api/config", {"config": cfg, "anyway": True}, method="PUT")
            self.assertEqual(code, want, (pat, r))
            if want == 400:
                self.assertIn("{year}", r["error"]) if "{" in pat and ".." not in pat else self.assertTrue(r["error"])
        self.assertEqual(self.app.config["receipts"]["subfolder"], "{year}-{month}")

    def test_areas_left_out_of_categorising(self):
        """Areas you do not categorise (a company with countless bookings) stay out of the list and the count; at least one
        stays; the choice is kept in the settings."""
        self.login(); self.run_and_wait()
        led = self.app.ledger
        area = {a.uuid: str(b["id"]) for b in core.bereiche_for(led, self.app.config) for a in b["leaves"]}
        by_id = {t.id: t for t in led.txs}
        # before you choose: only the private areas
        areas = core.bereiche_for(led, self.app.config)
        self.assertIsNone(self.app.config["assign_without"])
        code, off = self.call("/api/categories/unassigned")
        self.assertEqual(off["skipped"], sorted(str(b["id"]) for b in areas if b["kind"] != "private"))
        self.assertTrue(off["skipped"]); self.assertTrue(all(area[by_id[i].account_uuid] not in off["skipped"] for g in off["groups"] for i in g["ids"]))
        self.call("/api/categories/areas", {"without": [], "wait": True})                              # all: kept as chosen
        self.assertEqual(self.app.config["assign_without"], [])
        code, off = self.call("/api/categories/unassigned")
        self.assertEqual(off["skipped"], [])
        ids = [i for g in off["groups"] for i in g["ids"]]
        self.assertTrue(ids)
        hide = area[by_id[ids[0]].account_uuid]
        before = self.store.load("dataset.json")["categories"]["total"].get("without", 0)
        code, r = self.call("/api/categories/areas", {"without": [hide], "wait": True})
        self.assertEqual((code, r["config"]["assign_without"]), (200, [hide]))
        n_all = self.store.load("dataset.json")["categories"]["total"].get("without", 0)
        self.assertLess(n_all, before)                                                                  # the count follows at once
        code, off2 = self.call("/api/categories/unassigned")
        left = [i for g in off2["groups"] for i in g["ids"]]
        self.assertTrue(all(area[by_id[i].account_uuid] != hide for i in left)); self.assertLess(len(left), len(ids))
        self.assertEqual(self.call("/api/categories/areas", {"without": "x"})[0], 400)
        self.assertEqual(self.store.load("dataset.json")["categories"]["total"].get("without", 0), n_all)       # the count without that area (set before)
        self.call("/api/categories/areas", {"without": [], "wait": True})
        self.assertEqual(len([i for g in self.call("/api/categories/unassigned")[1]["groups"] for i in g["ids"]]), len(ids))
        import categorize as CZ
        all_n = CZ.stats(CZ.load(self.store), led, None, area)["total"].get("without", 0)
        part_n = CZ.stats(CZ.load(self.store), led, None, area, {hide})["total"].get("without", 0)
        self.assertLess(part_n, all_n)

    def test_kategorien_zurueckschreiben(self):
        """MoneyMoney ist massgeblich: Zuordnen traegt dort ein (geprueft), eigene Kategorie ohne Rueckfrage aenderbar, ein in
        MoneyMoney geaenderter Umsatz wird nicht beschrieben; von unterwegs gemerkt und beim naechsten Abgleich eingetragen;
        nur Bankkonten brauchen eine Kategorie."""
        import service as MA
        orig_loop = MA.auth.is_loopback
        self.login(); self.run_and_wait()
        sets = lambda: [w for b in MockBridge.instances for w in b.written if w[0] == "set" and w[2] is not None]
        MockBridge.state["txs"] += [F.tx("priv.giro", date(2026, 10, 20), -80.0, "Bauhaus", "Werkzeug"),
                                    F.tx("priv.giro", date(2026, 10, 27), -35.0, "Bauhaus", "Schrauben"),
                                    F.tx("priv.giro", date(2026, 10, 28), -900.0, "Alpha GbR", "Einlage Oktober", "", "DE02701500000000594937")]
        MockBridge.extra_cats = [("Haushalt", 0, True, {}), ("Werkzeug", 1, False, {}), ("Garten", 1, False, {})]
        self.app.do_run(True, False, full=True)
        ids = [t.id for t in self.app.ledger.txs if t.name == "Bauhaus"]
        code, off = self.call("/api/categories/unassigned")
        self.assertIn("Bauhaus", [g["name"] for g in off["groups"]]); self.assertEqual(off["written"], 0)          # no switch: assigning is the release
        # a payment into another area of yours: marked as such, with your category for transfers in MoneyMoney to assign
        self.assertEqual({g["name"]: g["own_account"] for g in off["groups"] if g["name"] in ("Bauhaus", "Alpha GbR")}, {"Bauhaus": False, "Alpha GbR": True})
        self.assertEqual(off["transfer"], "Umbuchung")
        um = next(g for g in off["groups"] if g["name"] == "Alpha GbR")["transactions"][0]
        self.assertEqual((um["account"], um["purpose"]), ("Hausbank Giro", "Einlage Oktober"))
        code, r = self.call("/api/categories/assign", {"ids": ids, "category": "Haushalt / Werkzeug", "wait": True})
        self.assertEqual((r["mm"]["written"], r["mm"]["later"]), (2, 0))
        self.assertEqual(sorted(w[1] for w in sets()), sorted(ids)); self.assertTrue(all(w[2] == F.uid("cat:Werkzeug") for w in sets()))
        self.assertFalse(categorize.load(self.store)["assignment"])                 # steht in MoneyMoney -- dort massgeblich
        self.assertEqual(categorize.mm_of(next(t for t in self.app.ledger.txs if t.id == ids[0])), "Haushalt / Werkzeug")
        # von Kontor geschrieben -> erneut aenderbar ohne Rueckfrage
        code, r = self.call("/api/categories/assign", {"ids": ids[:1], "category": "Haushalt / Garten", "wait": True})
        self.assertEqual((r["mm"]["written"], r["mm"]["foreign"]), (1, []))
        # Eingetragen: what Kontor entered, newest first; "before" is the category from before Kontor (none here)
        code, w = self.call("/api/categories/written"); by = {x["id"]: x for x in w["items"]}
        self.assertEqual((w["total"], self.call("/api/categories/unassigned")[1]["written"]), (2, 2))
        self.assertEqual((by[ids[0]]["old"], by[ids[0]]["new"], by[ids[0]]["undo"], by[ids[0]]["name"]), ("", "Haushalt / Garten", True, "Bauhaus"))
        self.assertEqual(w["items"][0]["id"], ids[0]) if w["items"][0]["time"] != w["items"][1]["time"] else None
        # taken back (several at once): MoneyMoney's default category again (there was none); a transaction changed there stays
        raw1 = next(t for t in MockBridge.state["txs"] if t["id"] == ids[1]); raw1["categoryPath"] = raw1["category"] = "Haushalt\\Garten"
        n0 = len(sets())
        code, r = self.call("/api/categories/undo", {"ids": ids, "wait": True})
        self.assertEqual((code, r["undone"], r["changed"], r["error"]), (200, 1, 1, 0))
        self.assertEqual(sets()[n0:], [("set", ids[0], F.uid("cat:Unkategorisiert"), None)])
        self.assertEqual(categorize.mm_of(next(t for t in self.app.ledger.txs if t.id == ids[0])), "")
        code, w = self.call("/api/categories/written"); self.assertEqual([x["id"] for x in w["items"]], [ids[1]])
        # MoneyMoney shows no category any more (set back there): taken back only where it still shows Kontor's -- nothing written
        raw1["categoryPath"] = raw1["category"] = "Unkategorisiert"
        n1 = len(sets()); code, r = self.call("/api/categories/undo", {"ids": [ids[1]], "wait": True})
        self.assertEqual((r["undone"], r["changed"]), (0, 1)); self.assertEqual(len(sets()), n1)
        raw1["categoryPath"] = raw1["category"] = "Haushalt\\Werkzeug"
        self.assertEqual(self.call("/api/categories/undo", {"ids": []})[0], 400)
        code, r = self.call("/api/categories/assign", {"ids": ids[:1], "category": "Haushalt / Garten", "wait": True})
        self.assertEqual(r["mm"]["written"], 1)
        # in MoneyMoney geaendert (anderer Betrag) -> nicht schreiben, MoneyMoney gilt
        raw = next(t for t in MockBridge.state["txs"] if t["id"] == ids[1]); raw["amount"] = -36.0
        n = len(sets())
        code, r = self.call("/api/categories/assign", {"ids": ids[1:], "category": "Haushalt / Garten", "wait": True})
        self.assertEqual((r["mm"]["written"], r["mm"]["error"]), (0, 1)); self.assertEqual(len(sets()), n)
        self.assertFalse(categorize.load(self.store)["assignment"])
        # von unterwegs: gemerkt (zaehlt schon), beim naechsten Abgleich am Mac eingetragen
        raw["amount"] = -35.0
        MockBridge.state["txs"].append(F.tx("priv.giro", date(2026, 10, 29), -12.0, "Bauhaus", "Duebel"))
        self.app.do_run(True, False, full=True)
        new_id = next(t.id for t in self.app.ledger.txs if t.name == "Bauhaus" and abs(t.amount + 12.0) < 0.01)
        orig = self.app.mm_write_allowed
        self.app.mm_write_allowed = lambda local: False
        try:
            code, r = self.call("/api/categories/assign", {"ids": [new_id], "category": "Haushalt / Werkzeug", "wait": True})
            self.assertEqual((r["mm"]["later"], r["mm"]["written"]), (1, 0)); self.assertEqual(len(sets()), n)
            self.assertTrue(categorize.waiting(categorize.load(self.store)["assignment"][str(new_id)]))
            self.assertEqual(self.call("/api/categories/unassigned")[1]["waiting"], 1)
            u = [x for x in self.call("/api/transactions?q=bauhaus")[1]["transactions"] if x["id"] == new_id][0]
            self.assertEqual((u["category"], u["source"]), ("Haushalt / Werkzeug", "waiting"))
        finally:
            self.app.mm_write_allowed = orig
        self.app.do_run(True, False)
        self.assertIn(new_id, [w[1] for w in sets()]); self.assertFalse(categorize.load(self.store)["assignment"])
        # MoneyMoneys Standardkategorie zaehlt als ohne -- und laesst sich ersetzen, ohne als fremd zu gelten
        MockBridge.state["txs"].append(dict(F.tx("priv.giro", date(2026, 10, 31), -9.0, "Eisenwaren", "Nägel"), categoryPath="Unkategorisiert", category="Unkategorisiert"))
        self.app.do_run(True, False, full=True)
        eid = next(t.id for t in self.app.ledger.txs if t.name == "Eisenwaren")
        self.assertIn(eid, [i for g in self.call("/api/categories/unassigned")[1]["groups"] for i in g["ids"]])
        code, r = self.call("/api/categories/assign", {"ids": [eid], "category": "Haushalt / Werkzeug", "wait": True})
        self.assertEqual((r["mm"]["written"], r["mm"]["foreign"]), (1, []))
        # Kontors Stand veraltet (leer), in MoneyMoney inzwischen "Garten": Rueckfrage zeigt "Garten", Ersetzen mit genau diesem Wert
        MockBridge.state["txs"].append(F.tx("priv.giro", date(2026, 10, 31), -4.0, "Samenhandel", "Samen"))
        self.app.do_run(True, False, full=True)
        sid = next(t.id for t in self.app.ledger.txs if t.name == "Samenhandel")
        raw = next(t for t in MockBridge.state["txs"] if t["id"] == sid); raw["categoryPath"] = raw["category"] = "Haushalt\\Garten"
        code, r = self.call("/api/categories/assign", {"ids": [sid], "category": "Haushalt / Werkzeug", "wait": True})
        self.assertEqual(r["mm"]["foreign"], [{"id": sid, "mm": "Haushalt / Garten"}])
        code, r = self.call("/api/categories/assign", {"ids": [sid], "category": "Haushalt / Werkzeug", "mode": "overwrite",
                                                         "confirmed": {str(sid): "Haushalt / Garten"}, "wait": True})
        self.assertEqual(r["mm"]["written"], 1)
        # von unterwegs: Umsatz mit Kategorie in MoneyMoney wird nicht gemerkt (aendern nur am Mac); Einschalten nur am Mac
        MA.auth.is_loopback = lambda remote: False
        try:
            cfgr = copy.deepcopy(self.app.config); cfgr.setdefault("ui", {})["remote_read_only"] = False; self.app.save_config(cfgr)
            code, r = self.call("/api/categories/assign", {"ids": [sid], "category": "Haushalt / Garten", "wait": True})
            self.assertEqual((r["mm"]["mac_only"], r["mm"]["later"]), (1, 0)); self.assertFalse(categorize.load(self.store)["assignment"])
            self.assertEqual(self.call("/api/categories/undo", {"ids": [sid]})[0], 403)          # taking back: only at the Mac
            self.assertEqual(self.call("/api/categories/written")[1]["local"], False)
            code, r = self.call("/api/package/import", {"package": {"name": "x", "config": {"dry_run": False}}, "anyway": True})
            self.assertEqual(self.app.config.get("dry_run", True), cfgr.get("dry_run", True))
        finally:
            MA.auth.is_loopback = orig_loop
        # nur Bankkonten brauchen eine Kategorie: das Verkaeuferdarlehen (Offline-Konto) erscheint nicht unter Zuordnen
        code, off = self.call("/api/categories/unassigned")
        self.assertFalse([g for g in off["groups"] if any("Verkäuferdarlehen" == k for k in g["accounts"])])
        u = [x for x in self.call("/api/transactions?account=" + F.uid("ga.vd"))[1]["transactions"]]
        self.assertTrue(u and all(x["needs"] is False for x in u))
        self.assertFalse(self.call("/api/transactions?uncategorized=1&account=" + F.uid("ga.vd"))[1]["transactions"])
        # opened from a chart: these categories and the ones below them, in these days; nonsense is no filter error
        alle = self.call("/api/transactions?limit=5000")[1]["transactions"]
        mit = [x for x in alle if x["category"]]
        self.assertTrue(mit)
        top = mit[0]["category"].replace(" › ", " / ").split(" / ")[0]
        von, bis = min(x["date"] for x in alle), max(x["date"] for x in alle)
        q = urllib.parse.quote(json.dumps([top]))
        got = self.call("/api/transactions?limit=5000&categories=%s&from=%s&to=%s" % (q, von, bis))[1]["transactions"]
        want = [x["id"] for x in alle if x["category"] and (x["category"].replace(" › ", " / ") + " / ").startswith(top + " / ")]
        self.assertEqual(sorted(x["id"] for x in got), sorted(want))
        # the total of a heat map row: also those without a category -- but not a payment between two of your areas (a contribution)
        got = self.call("/api/transactions?limit=5000&with_uncategorized=1&categories=%s&from=%s&to=%s" % (q, von, bis))[1]["transactions"]
        none = [x["id"] for x in alle if not x["category"] and x.get("needs", True) and not x.get("transfer") and not x.get("other_area")]
        self.assertTrue(none); self.assertEqual(sorted(x["id"] for x in got), sorted(want + none))
        self.assertTrue([x for x in alle if x.get("other_area")])
        # as the categories count them (a count clicked): booked, with MoneyMoney's own category -- not pending, not waiting
        keep = self.app.umsaetze
        try:
            base = dict(mit[0], booked_count=True, source="moneymoney")
            self.app.umsaetze = [dict(base, id=9001), dict(base, id=9002, booked_count=False), dict(base, id=9003, source="waiting")]
            got = self.call("/api/transactions?limit=5000&counted=1&categories=%s" % q)[1]["transactions"]
            self.assertEqual([x["id"] for x in got], [9001])
            self.assertEqual(len(self.call("/api/transactions?limit=5000&categories=%s" % q)[1]["transactions"]), 3)
        finally:
            self.app.umsaetze = keep
        self.assertFalse([x for x in got if x.get("other_area") and not x["category"]])
        self.assertFalse(self.call("/api/transactions?categories=%s" % urllib.parse.quote(json.dumps(["Gibt es nicht"])))[1]["transactions"])
        self.assertEqual(self.call("/api/transactions?categories=kaputt")[0], 200)
        m = mit[0]["date"][:7]
        one = self.call("/api/transactions?limit=5000&categories=%s&from=%s-01&to=%s-31" % (q, m, m))[1]["transactions"]
        self.assertTrue(one and all(x["date"].startswith(m) for x in one))

    def test_cashflow_positionen(self):
        """Kategorien -> Cashflow-Positionen: Kontor schlaegt je Kategorie eine Position vor, deine Wahl gilt auch darunter;
        Steuer und MoneyMoney bleiben unberuehrt."""
        self.login(); self.run_and_wait()
        def rows(area="priv"):
            b = self.store.load("dataset.json")["areas"][F.uid(area)]
            return {z["row"]: z for sek in b["cashflow"]["sections"] for z in sek["rows"]}
        self.assertIn("Einnahmen / Gehalt", {d["category"] for d in rows()["Arbeitseinkommen"]["details"]})
        code, p = self.call("/api/categories/positions")
        k = {r["path"]: r for r in p["categories"]}
        self.assertEqual((k["Einnahmen / Gehalt"]["proposal"], k["Wohnen / Miete"]["proposal"]), ("work_income", "housing"))
        self.assertGreater(k["Lebensmittel"]["count_all"], 0); self.assertIsNone(k["Einnahmen / Gehalt"]["own"])
        steuer_vorher = json.dumps(self.store.load("dataset.json")["tax"], sort_keys=True)
        code, r = self.call("/api/categories/positions", {"positions": {"Einnahmen / Gehalt": "other_income", "Wohnen": "ignore"}, "wait": True})
        self.assertEqual(code, 200); self.assertEqual(r["config"]["cashflow"]["positions"], {"Einnahmen / Gehalt": "other_income", "Wohnen": "ignore"})
        z = rows()
        self.assertNotIn("Arbeitseinkommen", z); self.assertIn("Einnahmen / Gehalt", {d["category"] for d in z["Sonstige Einnahmen"]["details"]})
        self.assertNotIn("Wohnen", z)                                                        # with "Wohnen / Miete" below it
        ue = self.store.load("dataset.json")["areas"][F.uid("priv")]["cashflow"]["reconciliation"]
        self.assertTrue(any(g[0] == "ue_ignoriert" for m in ue.values() for g in m["reasons"]))
        self.assertEqual(json.dumps(self.store.load("dataset.json")["tax"], sort_keys=True), steuer_vorher)
        # back to Kontor's proposal; a transfer category; nothing unknown
        code, r = self.call("/api/categories/positions", {"positions": {"Einnahmen / Gehalt": "", "Wohnen": "", "Lebensmittel": "transfer"}, "wait": True})
        self.assertEqual(r["config"]["cashflow"]["positions"], {"Lebensmittel": "transfer"})
        self.assertIn("Arbeitseinkommen", rows()); self.assertNotIn("Lebenshaltung", rows())
        code, p = self.call("/api/categories/positions")
        self.assertEqual({x["path"]: x for x in p["categories"]}["Lebensmittel"]["own"], "transfer")
        code, r = self.call("/api/categories/positions", {"positions": {"Lebensmittel": ""}})
        self.assertEqual(r["config"]["cashflow"]["positions"], {})
        self.assertEqual(self.call("/api/categories/positions", {"positions": {"Lebensmittel": "erfunden"}})[0], 400)
        self.assertEqual(self.call("/api/categories/positions", {"accounts": {"Sparen": "kein Konto"}})[0], 400)
        # the account per recipient (Zielkonto je Empfänger): your choice for the broker comes before the category's account
        an = lambda: {a["key"]: a for a in self.store.load("dataset.json")["areas"][F.uid("priv")]["cashflow"]["saving_recipients"]}
        self.assertEqual((an()["broker"]["how"], an()["broker"]["target"]), ("category", F.uid("priv.depot")))
        code, r = self.call("/api/categories/positions", {"recipient": {F.uid("priv"): {"broker": "external"}}, "wait": True})
        self.assertEqual(r["config"]["cashflow"]["recipient_to_account"], {F.uid("priv"): {"broker": "external"}})
        self.assertEqual(an()["broker"]["how"], "external"); self.assertIn("Sparen & Anlegen", {z["group"] for z in rows().values()})
        self.assertEqual(self.call("/api/categories/positions", {"recipient": {F.uid("priv"): {"broker": "kein Konto"}}})[0], 400)
        self.assertEqual(self.call("/api/categories/positions", {"recipient": {F.uid("priv"): ["broker"]}})[0], 400)
        code, r = self.call("/api/categories/positions", {"recipient": {F.uid("priv"): {"broker": ""}}, "wait": True})
        self.assertEqual(r["config"]["cashflow"]["recipient_to_account"], {}); self.assertEqual(an()["broker"]["how"], "category")
        self.assertFalse([w for b in MockBridge.instances for w in b.written if w[0] == "set" and w[2] is not None])

    def test_zugriff_vom_iphone(self):
        """Zugriff von anderen Geraeten: Stand, Ein-/Ausschalten nur am Mac, von unterwegs nur ansehen (Standard),
        Offline-Kopie abschaltbar."""
        import service as MA
        self.login(); self.run_and_wait()
        code, r = self.call("/api/remote")
        self.assertEqual(code, 200); self.assertFalse(r["active"]); self.assertTrue(r["read_only"]); self.assertTrue(r["offline_copy"]); self.assertTrue(r["local"])
        # ohne Tailscale: Einschalten scheitert mit Hinweis, nichts geaendert
        self.app._ts_cache = (time.time() + 999, {"found": False})
        orig_status = MA.App.tailscale
        MA.App.tailscale = lambda app, fresh=False: {"found": False}
        try:
            code, r = self.call("/api/remote", {"action": "enable"})
            self.assertFalse(r["ok"]); self.assertEqual(self.app.config["ui"]["bind"], "127.0.0.1")
            # mit Tailscale (verbunden), ohne Zertifikat
            MA.App.tailscale = lambda app, fresh=False: {"found": True, "connected": True, "ip": "100.101.102.103", "name": "mac.example.ts.net", "https": False, "devices": []}
            code, r = self.call("/api/remote", {"action": "enable_http"})
            self.assertTrue(r["ok"]); self.assertFalse(r["restart"])                     # im Test kein echter Neustart
            self.assertEqual(self.app.config["ui"]["bind"], "100.101.102.103")
            self.assertEqual(r["info"]["url"], "http://100.101.102.103:8765/"); self.assertTrue(r["info"]["active"])
            code, r = self.call("/api/remote", {"action": "disable"})
            self.assertEqual(self.app.config["ui"]["bind"], "127.0.0.1")
        finally:
            MA.App.tailscale = orig_status
        # von unterwegs (nicht vom Mac): Stand ja, Aenderungen nein (Standard "nur ansehen")
        orig = MA.auth.is_loopback
        MA.auth.is_loopback = lambda remote: False
        try:
            self.assertEqual(self.call("/api/remote")[1]["local"], False)
            code, r = self.call("/api/plan", {"area": F.uid("priv"), "row": "income/Arbeitseinkommen", "method": "fix", "amount": "1"})
            self.assertEqual(code, 403); self.assertIn("nur ansehen", r["error"])
            self.assertEqual(self.call("/api/remote", {"action": "disable"})[0], 403)
        finally:
            MA.auth.is_loopback = orig
        code, r = self.call("/api/remote", {"action": "settings", "remote_read_only": False, "offline_copy": False})
        self.assertTrue(r["ok"]); self.assertFalse(r["info"]["read_only"])
        MA.auth.is_loopback = lambda remote: False
        try:
            code, r = self.call("/api/plan", {"area": F.uid("priv"), "row": "income/Arbeitseinkommen", "method": "fix", "amount": "1"})
            self.assertEqual(code, 200)                                                    # bearbeiten erlaubt
            self.assertIsNone(self.call("/api/offline/verifier")[1]["offline"])            # keine Offline-Kopie
            self.assertFalse(self.call("/api/session")[1]["offline_copy"])
            # even with editing allowed: no receipts folder, no file questions, no live run from elsewhere
            cfg = copy.deepcopy(self.app.config); cfg.setdefault("receipts", {})["folder"] = "/"
            self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 403)
            cfg["receipts"] = dict(self.app.config.get("receipts") or {}, subfolder="../../{year}")
            self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 403)
            self.assertEqual(self.call("/api/file/status?path=" + self.dir)[0], 403)
            runs = []; orig_run = self.app.do_run
            self.app.do_run = lambda dry, force, **kw: runs.append(dry)
            try:
                self.assertEqual(self.call("/api/run", {})[0], 202); time.sleep(0.2)
                self.assertEqual(self.call("/api/run", {"dry_run": False})[0], 403)
            finally:
                self.app.do_run = orig_run
            self.assertEqual(runs, [True])                                                  # a dry run, whatever the test mode says
        finally:
            MA.auth.is_loopback = orig

    def test_port_aendern(self):
        """Port change: only from the Mac, must be free and valid; the answer tells the page to follow to the new port."""
        import socket
        import service as MA
        self.login()
        cfg = copy.deepcopy(self.app.config)
        busy = socket.socket(); busy.bind(("127.0.0.1", 0)); busy.listen(1)
        try:
            cfg["ui"]["port"] = busy.getsockname()[1]
            code, r = self.call("/api/config", {"config": cfg}, method="PUT")
            self.assertEqual(code, 409); self.assertIn(str(busy.getsockname()[1]), r["error"])
        finally:
            busy.close()
        cfg["ui"]["port"] = 80
        self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 400)
        free = socket.socket(); free.bind(("127.0.0.1", 0)); port = free.getsockname()[1]; free.close()
        cfg["ui"]["port"] = port
        orig = MA.auth.is_loopback
        MA.auth.is_loopback = lambda remote: False
        try:
            self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 403)    # not from the iPhone
        finally:
            MA.auth.is_loopback = orig
        code, r = self.call("/api/config", {"config": cfg}, method="PUT")
        self.assertEqual(code, 200); self.assertEqual(r["port"], port); self.assertTrue(r["instance"])
        self.assertFalse(r["restart"])                                                       # no real restart in tests
        self.assertEqual(self.app.config["ui"]["port"], port)
        self.assertEqual(self.call("/api/session")[1]["instance"], r["instance"])

    def test_abruf_offline_erkennung(self):
        """MoneyMoney setzt den Abrufzeitpunkt auch bei Offline-Konten: Regelziele und Konten ohne Nummern zaehlen nicht fuer den Datenstand."""
        self.login(); self.run_and_wait()
        led = copy.deepcopy(self.app.ledger)
        neu = max(a.refresh for a in led.accounts.values() if a.refresh)
        for key in ("ga.vd", "priv.bet.ga"):                 # Regelziele mit Zeitstempel (wie nach einer Buchung)
            led.accounts[F.uid(key)].refresh = neu - timedelta(days=20)
        led.fp = "x"; self.app.ledger = led
        kinds = core.abruf_arten(led, self.app.config)
        self.assertEqual(kinds[F.uid("ga.vd")]["kind"], "offline"); self.assertEqual(kinds[F.uid("ga.vd")]["reason"], "Offline-Konto")
        self.assertEqual(kinds[F.uid("priv.bet.ga")]["kind"], "offline")
        self.assertEqual(kinds[F.uid("priv.giro")]["kind"], "online"); self.assertEqual(kinds[F.uid("priv.depot")]["kind"], "online")
        self.assertEqual(self.app.bankabruf()["back_count"], 0)
        code, r = self.call("/api/sync"); self.assertEqual(code, 200)
        self.assertEqual([k["uuid"] for k in r["accounts"]][:3], [a.uuid for a in led.accounts.values() if not a.group and a.path][:3])   # Reihenfolge wie MoneyMoney
        self.assertTrue(r["read_at"]); self.assertIn("area", r["accounts"][0])
        # eigene Festlegung: Giro nicht abgerufen -> offline; zurueck -> wieder erkannt
        code, r = self.call("/api/sync", {"account": F.uid("priv.giro"), "fetched": False}); self.assertEqual(code, 200)
        self.assertEqual([k for k in r["fetch"]["accounts"] if k["uuid"] == F.uid("priv.giro")][0]["kind"], "offline")
        self.assertEqual(len(self.store.load("config.json")["fetch"]["offline"]), 1)
        self.call("/api/sync", {"account": F.uid("priv.giro"), "fetched": True})
        self.assertEqual(self.store.load("config.json")["fetch"], {"online": [], "offline": []})
        # Kontenliste in der Reihenfolge von MoneyMoney (nicht alphabetisch)
        code, k = self.call("/api/accounts")
        self.assertEqual([x["uuid"] for x in k["accounts"]], [a.uuid for a in led.accounts.values() if a.path])
        self.assertEqual([x for x in k["accounts"] if x["uuid"] == F.uid("priv.giro")][0]["role_proposal"], "cash")

    def test_schnellabgleich_und_luecken(self):
        """Kurzer Blick in MoneyMoney genuegt: Kontenliste lesen, Depotstand im Monat des Abrufs merken; Abruf waehrend Kontor
        nicht lief -> Hinweis auf moeglicherweise fehlende Monate."""
        from datetime import datetime as dt
        self.login()
        import service as MA
        MA.is_running = lambda: True
        try:
            depot = [a for a in MockBridge.state["accounts"] if a["uuid"] == F.uid("priv.depot")][0]
            depot["refreshTimestamp"] = F._dt(date(2026, 10, 31))           # Abruf am 31.10.
            self.app.prev_seen = dt(2026, 9, 15, 12, 0)                     # Kontor lief zuletzt am 15.09.
            self.app.capture()
            st = self.store.load("state.json")
            mk = [k for k, v in st["snapshots"].items() if F.uid("priv.depot") in v and k <= "2026-10"]
            self.assertTrue(mk, st["snapshots"].keys())                     # Depot im Monat des Abrufs (Ortszeit 30./31.10.)
            gaps = st.get("gaps") or []
            self.assertEqual(len(gaps), 1); self.assertEqual(gaps[0]["account"], F.uid("priv.depot")); self.assertEqual(gaps[0]["months"][0], "2026-09")
            code, r = self.call("/api/sync"); self.assertEqual(len(r["gaps"]), 1)
            code, stt = self.call("/api/status"); self.assertEqual(stt["moneymoney"]["gaps"], 1)
            self.call("/api/sync/gaps", {}); self.assertFalse(self.store.load("state.json").get("gaps"))
            # unveraendert -> kein erneuter Abgleich; geaendert -> voller Abgleich wird angestossen
            self.app.mm_retry_at = None; self.app.capture(); self.assertIsNone(self.app.mm_retry_at)
            self.app.config.setdefault("schedule", {})["automatic"] = True
            depot["balance"][0][0] += 1000; self.app.capture(); self.assertIsNotNone(self.app.mm_retry_at)
            import time as _t
            self.assertGreater(self.app.mm_retry_at, _t.time() + 30)            # erst wenn MoneyMoney fertig abgerufen hat
            self.app.do_run(True, force=False); self.assertIsNone(self.app.mm_retry_at)   # Lauf (Testmodus) hat den Stand gelesen
            self.app.capture(); self.assertIsNone(self.app.mm_retry_at)          # -> kein zweiter Lauf hinterher
            # Mac schlief (kein Abruf seit dem letzten Lauf) -> keine Meldung
            self.app.prev_seen = dt(2026, 11, 6, 12, 0); self.app._check_gaps(accounts_from_export(MockBridge.state["accounts"]))
            self.assertFalse(self.store.load("state.json").get("gaps"))
        finally:
            import mm_bridge as MB
            MA.is_running = MB.is_running

    def _mm_db(self, compat=None, mit_verlauf=True, passwort="ge'heim", zeit="unix", versatz=False, depot="value"):
        """Erfundene MoneyMoney-Datenbank (SQLCipher) im Aufbau des Originals: accounts (ohne UUID; Zuordnung ueber IBAN,
        Kontonummer + BLZ oder Name), balance_chart (Saldo je Zeitpunkt), portfolio_chart (Wert je Wertpapier, fuer das Depot),
        Zugangsdaten, Umsaetze, Volltextsuche mit eigenem Tokenizer, eigene Sortierfolge."""
        import subprocess as sp
        from datetime import datetime as DT
        led = self.app.ledger
        leaves = [a for a in led.accounts.values() if not a.group]
        ts = lambda d: int((DT(d.year, d.month, d.day) - (DT(2001, 1, 1) if zeit == "cocoa" else DT(1970, 1, 1))).total_seconds())
        q = lambda v: "NULL" if v in (None, "") else "'%s'" % str(v).replace("'", "''")
        sql = ["CREATE TABLE accounts(rowid INTEGER PRIMARY KEY, bank_key INTEGER, account TEXT, subaccount TEXT, bankcode TEXT, portfolio INTEGER, iban TEXT, "
               "currency TEXT, name TEXT COLLATE NOCASE, cred TEXT, userdata BLOB);",
               "CREATE TABLE banks(rowid INTEGER PRIMARY KEY, username TEXT, credential TEXT);", "INSERT INTO banks VALUES(1, 'GEHEIM-NUTZER', 'GEHEIM-PIN');",
               "CREATE VIRTUAL TABLE transactions_fts USING fts4(content, tokenize=simple);", "INSERT INTO transactions_fts VALUES('Suchtext');",
               "CREATE TABLE transactions(rowid INTEGER PRIMARY KEY, local_account_key INTEGER, timestamp INTEGER, amount REAL, unformatted_purpose TEXT);"]
        if mit_verlauf:
            sql += ["CREATE TABLE balance_chart(account_key INTEGER, currency TEXT, timestamp INTEGER, balance REAL);",
                    "CREATE TABLE securities(rowid INTEGER PRIMARY KEY, account_key INTEGER, quantity REAL, deleted INTEGER, comment TEXT);",
                    "CREATE TABLE portfolio_chart(account_key INTEGER, currency TEXT, timestamp INTEGER, balance REAL, securities_key INTEGER);"]
        rows = [(a, a.name) for a in leaves] + [(None, "Fremdes Konto")]
        for i, (a, name) in enumerate(rows, 1):
            if a is None:
                sql.append("INSERT INTO accounts VALUES(%d, 1, '999', NULL, '10050000', 0, NULL, 'EUR', 'Fremdes Konto', 'GEHEIM-%d', NULL);" % (i, i))
                continue
            sql.append("INSERT INTO accounts VALUES(%d, 1, %s, NULL, %s, %d, %s, 'EUR', %s, 'GEHEIM-%d', NULL);"
                       % (i, q(a.account_number), q(a.bank_code), 1 if a.portfolio else 0, q(a.iban), q(name), i))
            for k in range(3):
                sql.append("INSERT INTO transactions(local_account_key, timestamp, amount, unformatted_purpose) VALUES(%d, %d, %f, 'Text %d');" % (i, ts(date(2026, 10, 10 + k)), 12.34 + k, k))
            if not mit_verlauf:
                continue
            # wie bei MoneyMoney: je Tag die Veraenderung (Summe der Buchungen), Zeitpunkt tagsueber; Saldo = rueckwaerts vom aktuellen
            if a.portfolio and depot == "delta":          # Depot als Wertveraenderung je Wertpapier: Summe aller = aktueller Wert
                y, m, prev = 2024, 1, 0.0
                while (y, m) <= (2026, 10):
                    v = 70000.27 if (y, m) == (2025, 6) else round(a.balance * (0.5 + 0.5 * ((y - 2024) * 12 + m) / 34.0), 2)
                    delta, prev = round(v - prev, 2), v
                    part = round(delta * 0.6, 2)
                    sql.append("INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, 1);" % (i, ts(date(y, m, 15)), part))
                    sql.append("INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, 2);" % (i, ts(date(y, m, 15)), round(delta - part, 2)))
                    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
                sql.append("INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, 1);" % (i, ts(date(2026, 11, 3)), round(a.balance - prev, 2)))
                continue
            if a.portfolio:          # Depot: Wert je Wertpapier, unabhaengig voneinander erfasst; Wertpapier 3 im Juni 2024 verkauft
                sql += ["INSERT INTO securities VALUES(%d, %d, 10, 0, 'GEHEIM');" % (100 + i, i), "INSERT INTO securities VALUES(%d, %d, 5, 0, NULL);" % (200 + i, i),
                        "INSERT INTO securities VALUES(%d, %d, 0, 1, NULL);" % (300 + i, i)]
                y, m = 2024, 1
                while (y, m) <= (2026, 10):
                    v = 70000.27 if (y, m) == (2025, 6) else round(a.balance * (0.5 + 0.5 * ((y - 2024) * 12 + m) / 34.0), 2)
                    part = round(v * 0.6, 2)
                    sql.append("INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, %d);" % (i, ts(date(y, m, 12)), part, 100 + i))
                    sql.append("INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, %d);" % (i, ts(date(y, m, 19)), round(v - part, 2), 200 + i))
                    if (y, m) <= (2024, 6):
                        sql.append("INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, 5000.0, %d);" % (i, ts(date(y, m, 8)), 300 + i))
                    if depot in ("total", "gesamt_frei"):     # zusaetzlicher Eintrag mit dem Depotwert insgesamt (bei manchen Depots in MoneyMoney)
                        sql.append("INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, %d);" % (i, ts(date(y, m, 20)), round(v + (5000.0 if (y, m) <= (2024, 6) else 0.0), 2), 900 + i))
                    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
                part = round(a.balance * 0.6, 2)
                if depot in ("total", "gesamt_frei"):     # gesamt_frei: the total entry is no security of its own (e.g. Trade Republic)
                    sql += (["INSERT INTO securities VALUES(%d, %d, 1, 0, NULL);" % (900 + i, i)] if depot == "total" else []) + [
                            "INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, %d);" % (i, ts(date(2026, 11, 3)), a.balance, 900 + i)]
                sql.append("INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, %d);" % (i, ts(date(2026, 11, 3)), part, 100 + i))
                sql.append("INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, %d);" % (i, ts(date(2026, 11, 2)), round(a.balance - part, 2), 200 + i))
                continue
            per_day = {}
            for tx in led.transactions(a.uuid):
                per_day[tx.booking_date] = round(per_day.get(tx.booking_date, 0.0) + tx.amount, 2)
            if a.uuid == F.uid("ga.immo"):
                per_day = {date(2025, 3, 3): 123.0, date(2025, 4, 3): 246.0, date(2025, 5, 3): -50.0}   # passt nicht zu den Umsaetzen
            for d, v in sorted(per_day.items()):
                sql.append("INSERT INTO balance_chart VALUES(%d, 'EUR', %d, %r);" % (i, ts(d) + 37000, v + (1000.0 if versatz else 0.0)))
        db = os.path.join(self.dir, "MoneyMoney.sqlite")
        if os.path.exists(db):
            os.remove(db)
        pre = "PRAGMA key = '%s';\n" % passwort.replace("'", "''") + ("PRAGMA cipher_compatibility = %d;\n" % compat if compat else "")
        # wie bei MoneyMoney: Volltextsuche mit eigenem Tokenizer und eigene Sortierfolge, die es hier nicht gibt
        fix = (".dbconfig defensive off\nPRAGMA writable_schema = ON;\nUPDATE sqlite_master SET sql = replace(sql, 'tokenize=simple', 'tokenize=fts_tokenize') WHERE name = 'transactions_fts';\n"
               "UPDATE sqlite_master SET sql = replace(sql, 'COLLATE NOCASE', 'COLLATE localized') WHERE name = 'accounts';\n")
        sp.run(["sqlcipher", db], input=pre + "BEGIN;\n" + "\n".join(sql) + "\nCOMMIT;\n" + fix, capture_output=True, text=True, check=True)
        with open(db, "rb") as f:
            return f.read()

    def _mm_upload(self, data, csrf=True):
        req = urllib.request.Request("http://127.0.0.1:%d/api/history/mm-import" % self.port, data=data, method="POST")
        req.add_header("Content-Type", "application/octet-stream")
        if csrf:
            req.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.opener.open(req) as r:
                code, res = r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")
        if res.get("running"):
            for _ in range(600):
                time.sleep(0.05)
                c, st = self.call("/api/history/mm-status")
                if not st["running"]:
                    return code, st["result"]
        return code, res

    def test_kontostaende_aus_moneymoney(self):
        """Verlauf aller Konten aus der hochgeladenen (verschluesselten) Datenbank: nur im Speicher, Passwort nie in Kontor,
        geprueft am aktuellen Saldo, Monatsende uebernommen, verschluesselt gespeichert; MoneyMoney muss beendet sein."""
        import hashlib, shutil as sh, mm_history as H, service as MA
        from core import MM_HISTORY_FILE
        if not sh.which("sqlcipher"):
            self.skipTest("sqlcipher fuer die Testdatenbank fehlt")
        self.login(); self.run_and_wait()
        data = self._mm_db()
        self.assertNotIn(b"GEHEIM", data); self.assertNotIn(F.uid("priv.depot").upper().encode(), data)     # wirklich verschluesselt
        old = (H.keys_from_dialog, MA.is_running)
        H.keys_from_dialog = lambda salt: [bytearray(hashlib.pbkdf2_hmac(h, "ge'heim".encode(), salt, r, 32)) for _n, h, r in H.FORMATS]
        aufbau = os.path.join(os.path.dirname(H.__file__), "mm-history-schema.txt")
        try:
            self.assertEqual(self._mm_upload(data, csrf=False)[0], 403)                 # ohne CSRF-Token abgewiesen
            MA.is_running = lambda: True
            code, r = self._mm_upload(data); self.assertFalse(r["ok"]); self.assertIn("beenden", r["text"])
            MA.is_running = lambda: False
            code, r = self._mm_upload(b"kein sqlite" * 200); self.assertFalse(r["ok"]); self.assertIn("Passwort falsch", r["text"])
            sqls = []
            spy = lambda f: (lambda self_, sql, params=(): (sqls.append(sql), f(self_, sql, params))[1])
            orig_rows, orig_one = H.MemDB.rows, H.MemDB.one
            H.MemDB.rows, H.MemDB.one = spy(orig_rows), spy(orig_one)
            try:
                code, r = self._mm_upload(data); self.assertTrue(r["ok"], r)
            finally:
                H.MemDB.rows, H.MemDB.one = orig_rows, orig_one
            # nur lesend: ausschliesslich SELECT (und Einstellungen der Verbindung), nie etwas, das die Datenbank aendert
            self.assertTrue(sqls); self.assertFalse([q for q in sqls if not re.match(r"\s*(SELECT|PRAGMA (query_only|temp_store|mmap_size|cache_size|table_info))\b", q)])
            self.assertFalse([q for q in sqls if re.search(r"\b(cred|credential|username|pin|userdata|purpose|unformatted)\b", q)])   # keine Zugangsdaten, keine Umsaetze
            # uebernommen: das Depot und jedes Konto mit Umsaetzen (dessen Punkte passen); Konten ohne Umsaetze haben keine Punkte
            n = 1 + sum(1 for a in self.app.ledger.accounts.values() if not a.group and not a.portfolio
                        and any(t.booking_date < date(2026, 11, 1) for t in self.app.ledger.transactions(a.uuid)))
            self.assertEqual(r["accounts"], n); self.assertEqual(r["depots"], 1); self.assertEqual((r["date_from"], r["date_to"]), ("2024-01", "2026-10"))
            self.assertFalse(H.AKTIV.is_set()); self.assertFalse(os.path.exists(aufbau))
            self.assertFalse([f for f in os.listdir(self.dir) if f.startswith("kontor-") or f.endswith(".sqlite") and f != "MoneyMoney.sqlite"])
            mm = self.store.load(MM_HISTORY_FILE)["accounts"]
            dep = mm[F.uid("priv.depot")]
            self.assertNotIn(F.uid("ga.immo"), mm)                                      # Punkte passen nicht zu den Umsaetzen: nicht uebernommen
            look = __import__("service").balance_lookup(self.app.ledger)
            for u in mm:                                                                # Monatsende = aktueller Saldo minus spaetere Veraenderungen
                if not self.app.ledger.accounts[u].portfolio:
                    self.assertEqual(mm[u]["2026-09"], look(u, date(2026, 9, 30), False))
            self.assertEqual(dep["2025-06"], 70000.27)                                 # Summe der gehaltenen Wertpapiere am Monatsende
            self.assertGreater(dep["2024-05"] - dep["2024-06"], 3000)          # verkauftes Wertpapier zaehlt nicht mehr im Monat seines letzten Werts
            self.assertEqual(self.store.load(MM_HISTORY_FILE)["opening"][F.uid("priv.depot")], 0.0)   # vor der ersten Aufzeichnung: leer
            self.assertNotIn("2026-11", dep)                                            # laufender Monat kommt aus dem aktuellen Saldo
            with open(self.store.path(MM_HISTORY_FILE), "rb") as f:
                self.assertNotIn(b"70000", f.read())                                    # verschluesselt abgelegt
            self.assertEqual(self.store.load("state.json")["mm_history_src"]["accounts"], n)
            code, st = self.call("/api/status"); self.assertEqual(st["moneymoney"]["history"]["depots"], 1)
            self.app.rebuild_report(wait=True)
            code, h = self.call("/api/history?account=" + F.uid("priv.depot"))
            self.assertEqual(h["amounts"]["2025-06"], 70000.27); self.assertEqual(h["moneymoney"]["2025-06"], 70000.27)
            code, ab = self.call("/api/sync")
            d = next(x for x in ab["depots"] if x["uuid"] == F.uid("priv.depot")); self.assertEqual(d["first_balance"], "2024-01"); self.assertTrue(d["from_moneymoney"])
            # Bilanz nutzt die Werte
            code, ds = self.call("/api/dataset")
            row = next(z for b in ds["areas"].values() for z in b["balance"]["rows"] if z.get("id") == F.uid("priv.depot"))
            self.assertEqual(row["amounts"]["2025-06"], 70000.27)
            self.assertIsNone(row.get("projected_before"))                           # vor der Aufzeichnung leer, nicht "unbekannt"
            self.assertNotIn("fortgeschrieben", h.get("hint") or "")
            # Verlauf der Konten mit Umsaetzen passt nirgends (versetzt): nur das Depot wird uebernommen, die Konten behalten Kontors Salden
            code, r = self._mm_upload(self._mm_db(versatz=True)); self.assertTrue(r["ok"], r); self.assertEqual((r["accounts"], r["depots"]), (1, 1))
            # aelteres Format (SQLCipher 3) und Cocoa-Zeit ebenso
            code, r = self._mm_upload(self._mm_db(compat=3, zeit="cocoa")); self.assertTrue(r["ok"], r); self.assertEqual(r["accounts"], n)
            # Depot mit zusaetzlichem Gesamt-Eintrag (Summe doppelt): der Gesamt-Eintrag gilt
            for variant in ("total", "gesamt_frei"):     # with the total entry as a security of its own or not: never counted twice
                code, r = self._mm_upload(self._mm_db(depot=variant)); self.assertTrue(r["ok"], r); self.assertEqual(r["depots"], 1)
                gd = self.store.load(MM_HISTORY_FILE)["accounts"][F.uid("priv.depot")]
                self.assertEqual(gd["2025-06"], 70000.27, variant); self.assertGreater(gd["2024-06"] - gd["2024-07"], 3000)
            # Depot als Wertveraenderung je Wertpapier ebenso
            code, r = self._mm_upload(self._mm_db(depot="delta")); self.assertTrue(r["ok"], r); self.assertEqual(r["depots"], 1)
            self.assertEqual(self.store.load(MM_HISTORY_FILE)["accounts"][F.uid("priv.depot")]["2025-06"], 70000.27)
            # ohne Verlaufstabelle: nichts uebernommen, nur der Aufbau (Namen, keine Inhalte) als Hinweis
            code, r = self._mm_upload(self._mm_db(mit_verlauf=False)); self.assertFalse(r["ok"]); self.assertIn("nicht sicher erkannt", r["text"])
            txt = open(aufbau, encoding="utf-8").read()
            self.assertIn("transactions", txt); self.assertNotIn("GEHEIM", txt); self.assertNotIn("Text 1", txt)
            self.assertEqual(self.store.load(MM_HISTORY_FILE)["accounts"][F.uid("priv.depot")]["2025-06"], 70000.27)    # bisherige Werte bleiben
            H.keys_from_dialog = lambda salt: [bytearray(hashlib.pbkdf2_hmac(h, b"falsch", salt, r, 32)) for _n, h, r in H.FORMATS]
            code, r = self._mm_upload(data); self.assertFalse(r["ok"]); self.assertIn("Passwort falsch", r["text"])
        finally:
            H.keys_from_dialog, MA.is_running = old
            if os.path.exists(aufbau):
                os.remove(aufbau)

    def test_sprache_englisch(self):
        """Sprache in den Einstellungen: Meldungen des Dienstes und Namen der Auswertung auf Englisch; Deutsch bleibt Standard."""
        import service as MA
        self.login(); self.run_and_wait()
        code, ds = self.call("/api/dataset")
        self.assertEqual(next(z for b in ds["areas"].values() for z in b["balance"]["rows"] if z.get("id") == "pos:liabilities")["name"], "Verbindlichkeiten")
        self.assertEqual(self.call("/api/language", {"language": "xx"})[0], 400)
        code, r = self.call("/api/language", {"language": "en"}); self.assertEqual(r["language"], "en")
        self.assertEqual(self.store.load("config.json")["ui"]["language"], "en")
        self.app.rebuild_report(wait=True)
        code, ds = self.call("/api/dataset")
        self.assertEqual(next(z for b in ds["areas"].values() for z in b["balance"]["rows"] if z.get("id") == "pos:liabilities")["name"], "Liabilities")
        old = MA.is_running; MA.is_running = lambda: True
        try:
            code, r = self._mm_upload(b"x" * 2048); self.assertIn("Please quit MoneyMoney first", r["text"])
        finally:
            MA.is_running = old
        code, r = self.call("/api/language", {"language": "de"})
        code, r = self.call("/api/properties", {"action": "speichern", "id": "gibtsnicht"}); self.assertIn("nicht gefunden", json.dumps(r, ensure_ascii=False))

    def test_historie_puffer_werden_ueberschrieben(self):
        """Schluessel und Klartext liegen nur in einem Puffer, der nach dem Lesen mit Nullen ueberschrieben ist;
        SQLite liest direkt aus diesem Puffer (keine Kopie); Zugangsdaten-Tabellen werden nicht angesehen."""
        import hashlib, shutil as sh, subprocess as sp, mm_history as H
        if not sh.which("sqlcipher"):
            self.skipTest("sqlcipher fehlt")
        db = os.path.join(self.dir, "w.sqlite")
        sp.run(["sqlcipher", db], input="PRAGMA key = 'x';\nCREATE TABLE t(a);\nINSERT INTO t VALUES('GEHEIMER-INHALT');\n", capture_output=True, text=True, check=True)
        buf = bytearray(open(db, "rb").read())
        seen = {}

        def keys(salt):
            seen["keys"] = [bytearray(hashlib.pbkdf2_hmac(h, b"x", salt, r, 32)) for _n, h, r in H.FORMATS]
            return seen["keys"]
        orig = H.MemDB.__init__

        def spy(self_, b):
            seen["klartext"] = b"GEHEIMER-INHALT" in bytes(b)
            seen["equal"] = b is buf
            orig(self_, b)
        H.MemDB.__init__ = spy
        try:
            found, tables, fmt = H.run(buf, {"x": {"saldo": 1.0, "depot": False, "name": "x"}}, date(2026, 11, 4), keys_fn=keys)
        finally:
            H.MemDB.__init__ = orig
        self.assertIsNone(found); self.assertEqual(tables[0]["name"], "t"); self.assertEqual(fmt, "SQLCipher 4")
        self.assertTrue(seen["klartext"]); self.assertTrue(seen["equal"])          # im selben Puffer entschluesselt
        self.assertTrue(all(not any(k) for k in seen["keys"]))                     # Schluessel genullt
        self.assertFalse(any(buf))                                                 # Klartext genullt
        real = H.sys                                                                  # macOS-Zweig (Systembibliothek fehlt hier -> Ersatz)
        H.sys = type("Mac", (), {"platform": "darwin"})()
        try:
            self.assertTrue(H._sqlite_lib().sqlite3_deserialize)
        finally:
            H.sys = real

    def test_lesefehler_wird_gemeldet(self):
        """MoneyMoney laeuft, Kontor kann aber nicht lesen (z. B. Berechtigung) -> Hinweis; erfolgreiches Lesen nimmt ihn zurueck."""
        import service as MA
        self.login()
        old = MA.is_running; MA.is_running = lambda: True
        orig = MockBridge.export_accounts
        try:
            def boom(self_):
                raise mm_bridge.MoneyMoneyNotPermitted("Keine Berechtigung")
            MockBridge.export_accounts = boom
            self.app.capture()
            code, st = self.call("/api/status"); self.assertIn("Berechtigung", st["moneymoney"]["problem_text"]["text"])
            MockBridge.export_accounts = orig
            self.app.capture()
            code, st = self.call("/api/status"); self.assertIsNone(st["moneymoney"]["problem_text"])
        finally:
            MockBridge.export_accounts = orig; MA.is_running = old

    def test_bankabruf_zurueck(self):
        """Konten mit Saldo, die beim Bankabruf mehr als einen Tag zurückliegen, werden gemeldet; uralte (aufgelöste) nicht."""
        self.login()
        self.run_and_wait()
        led = copy.deepcopy(self.app.ledger)
        neu = max(a.refresh for a in led.accounts.values() if a.refresh)
        led.accounts[F.uid("priv.giro")].refresh = neu - timedelta(days=3)
        alt = next(a for a in led.accounts.values() if a.refresh and a.uuid != F.uid("priv.giro") and not a.group)
        alt.refresh = neu - timedelta(days=800)
        self.app.ledger = led
        ba = self.app.bankabruf()
        self.assertEqual(ba["back_count"], 1); self.assertEqual(ba["back"][0]["name"], "Hausbank Giro")
        self.assertEqual(ba["newest"], neu.strftime("%Y-%m-%d %H:%M"))

    def test_auth_and_api_flow(self):
        self.assertEqual(self.call("/api/status")[0], 401)
        self.login()
        self.assertEqual(self.call("/api/setup", {"password": "noch-ein-passwort-123"})[0], 403)
        self.assertEqual(self.call("/api/run", {"dry_run": True}, csrf=False)[0], 403)
        self.assertEqual(self.call("/api/run", {"dry_run": True}, origin="http://evil.example")[0], 403)
        # DNS rebinding: a foreign name pointing to 127.0.0.1 gets nothing; *.localhost and localhost are fine
        import http.client
        for host, want in (("evil.example:%d" % self.port, 421), ("kontor.localhost:%d" % self.port, 200), ("localhost:%d" % self.port, 200)):
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5); c.request("GET", "/", headers={"Host": host})
            self.assertEqual(c.getresponse().status, want, host); c.close()
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("POST", "/api/login", body=b"{}", headers={"Host": "evil.example", "Origin": "http://evil.example", "Content-Type": "application/json"})
        self.assertEqual(c.getresponse().status, 403); c.close()
        code, st = self.call("/api/status")
        self.assertEqual(code, 200); self.assertTrue(st["storage"]["encrypted"]); self.assertIn("version", st)
        code, ds = self.call("/api/dataset")
        self.assertTrue(ds["empty"])
        self.run_and_wait()
        code, runs = self.call("/api/runs")
        self.assertEqual(runs["last_run"]["written"], 24)
        code, st = self.call("/api/status")
        mm = st["moneymoney"]
        self.assertNotIn("naechster_lauf", st["service"]); self.assertNotIn("aktualisieren_erlaubt", mm)
        self.assertTrue(mm["as_of"]); self.assertEqual(mm["bank_fetch"]["back_count"], 0)
        self.assertRegex(mm["bank_fetch"]["newest"], r"^2026-11-0[34] \d\d:00$")       # Fixture: Abruf 04.11. (Ortszeit)
        code, ds = self.call("/api/dataset")
        self.assertEqual(ds["main_area"], F.uid("priv")); self.assertEqual(len(ds["areas"]), 3)
        b = ds["areas"][ds["main_area"]]
        self.assertIn("figures", b); self.assertIn("plan", b); self.assertTrue(b["plan_months"])
        self.assertEqual(b["plan"]["inflation_percent_pa"], 2.0)
        code, k = self.call("/api/accounts")
        self.assertTrue(any(x["name"] == "Verkäuferdarlehen" and x["manual"] for x in k["accounts"]))
        self.assertTrue(any(x["name"] == "Hausbank Giro" and not x["manual"] for x in k["accounts"]))
        code, kats = self.call("/api/categories")
        self.assertTrue(any(c["path"] == "Vermietung / Parkweg / Mieteinnahmen" for c in kats["categories"]))
        # Plan je Bereich: Methode, Ueberschreibung, Parameter, Darlehen, Wertentwicklung
        P = ds["main_area"]
        code, r = self.call("/api/plan", {"area": P, "row": "income/Arbeitseinkommen", "method": "fix", "amount": "7000", "increase": "2"})
        self.assertEqual(code, 200)
        self.call("/api/plan", {"area": P, "row": "income/Arbeitseinkommen", "month": "2027-01", "value": "9000"})
        self.call("/api/plan", {"area": P, "parameter": {"horizon_months": 36, "inflation_percent_pa": 3},
                                "loans": {"Darlehen Lindenstraße": {"interest_percent_pa": "3.6", "model": "remaining_debt_monthly", "payment": ""}},
                                "appreciation": {"Immobilie Lindenstraße": {"percent_pa": "1.5", "base": ""}}})
        code, ds = self.call("/api/dataset")
        b = ds["areas"][P]
        self.assertEqual(len(b["plan_months"]), 37); self.assertEqual(b["plan_months"][-1][5:], "12")    # 36 Monate, bis Jahresende aufgefuellt
        self.assertEqual(b["plan"]["inflation_percent_pa"], 3)
        gz = [z for z in b["cashflow"]["sections"][0]["rows"] if z["row"] == "Arbeitseinkommen"][0]
        self.assertEqual(gz["plan"]["amounts"]["2027-01"], 9000.0)
        self.assertAlmostEqual(gz["plan"]["proposal"]["2027-01"], round(7000 * 1.02 ** (2 / 12), 2), 2)
        self.assertEqual(gz["plan"]["overwritten"], ["2027-01"])
        fz = {z["row"]: z for z in [s for s in b["cashflow"]["sections"] if s["name"] == "financing"][0]["rows"]}
        self.assertEqual(fz["Darlehen Lindenstraße / Zinsen"]["plan"]["method"], "loans")
        # Ausgaben folgen der Inflation (3 %)
        mz = [z for z in [s for s in b["cashflow"]["sections"] if s["name"] == "expenses"][0]["rows"] if z["row"] == "Wohnen"][0]
        self.assertEqual(mz["plan"]["increase_percent_pa"], 3.0)
        # Budget-Methode
        self.call("/api/plan", {"area": P, "row": "expenses/" + mz["row"], "method": "budget"})
        code, ds = self.call("/api/dataset")
        mz2 = [z for z in [s for s in ds["areas"][P]["cashflow"]["sections"] if s["name"] == "expenses"][0]["rows"] if z["row"] == "Wohnen"][0]
        self.assertEqual(mz2["plan"]["method"], "budget"); self.assertAlmostEqual(mz2["plan"]["proposal"][b["plan_months"][0]], round(-1500.0 * 1.03 ** (1 / 12), 2), 2)
        # anderer Bereich hat eigenen (leeren) Plan
        code, plan_ga = self.call("/api/plan?area=" + F.uid("ga"))
        self.assertEqual(plan_ga, {})
        self.assertEqual(len(ds["areas"][F.uid("ga")]["plan_months"]), 25)       # 24 Monate, bis Jahresende aufgefuellt
        self.call("/api/plan", {"area": P, "row": "income/Arbeitseinkommen", "clear_all_overrides": True})
        code, ds = self.call("/api/dataset")
        gz = [z for z in ds["areas"][P]["cashflow"]["sections"][0]["rows"] if z["row"] == "Arbeitseinkommen"][0]
        self.assertEqual(gz["plan"]["amounts"]["2027-01"], gz["plan"]["proposal"]["2027-01"])
        # Konfiguration: Fehler wird abgewiesen, gueltige gespeichert, bind geprueft
        code, cfg = self.call("/api/config")
        bad = copy.deepcopy(cfg); bad["loans"][0]["loan_account"] = F.uid("priv.giro") + " | Hausbank Giro"
        code, r = self.call("/api/config", {"config": bad}, method="PUT")
        self.assertEqual(code, 409); self.assertTrue(any(f["severity"] == "error" for f in r["findings"]))
        good = copy.deepcopy(cfg); good["dry_run"] = True; good["ui"]["bind"] = "0.0.0.0"
        self.assertEqual(self.call("/api/config", {"config": good}, method="PUT")[0], 400)
        good["ui"]["bind"] = "100.100.1.2"
        code, r = self.call("/api/config", {"config": good}, method="PUT")
        self.assertEqual(code, 200); self.assertTrue(r["config"]["dry_run"])
        self.assertTrue(self.store.load("config.json")["dry_run"])
        self.assertTrue(any(e["name"] == "Alpha GbR" for e in ds["tax"]["entities"]))
        # Passwort aendern, abmelden, erneut anmelden; Fehlversuche sperren
        self.assertEqual(self.call("/api/password", {"old": "falsch", "new": "neues-passwort-123"})[0], 401)
        self.assertEqual(self.call("/api/password", {"old": "sehr-geheimes-passwort", "new": "neues-passwort-123"})[0], 200)
        self.assertEqual(self.call("/api/lock", {})[0], 200)
        self.assertEqual(self.call("/api/status")[0], 401)
        for _ in range(5):
            self.assertEqual(self.call("/api/login", {"password": "falsch"})[0], 401)
        self.assertEqual(self.call("/api/login", {"password": "neues-passwort-123"})[0], 429)
        self.app.sessions.clear_fails("127.0.0.1")
        code, r = self.call("/api/login", {"password": "neues-passwort-123"})
        self.assertEqual(code, 200)
        self.assertEqual(self.call("/api/touchid", {})[0], 403)
        with self.opener.open("http://127.0.0.1:%d/" % self.port) as r:
            self.assertIn("Kontor", r.read().decode()); self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])

    def test_umsaetze_belege_exports(self):
        self.login(); self.run_and_wait()
        code, u = self.call("/api/transactions?year=2026&uncategorized=1&limit=5")
        self.assertEqual(code, 200); self.assertTrue(u["hits"] >= 10); self.assertEqual(len(u["transactions"]), 5)
        self.assertTrue(all(not x["category"] for x in u["transactions"]))
        code, u = self.call("/api/transactions?q=supermarkt&entity=" + F.uid("priv"))
        self.assertTrue(u["transactions"]); self.assertTrue(all("Supermarkt" in x["name"] for x in u["transactions"]))
        tx = u["transactions"][0]
        pdf = b"%PDF-1.4 test"
        # Erster Beleg: Ordner wird erst nach Rueckfrage angelegt
        code, r = self.call("/api/receipts/upload", {"tx_id": tx["id"], "file_name": "rechnung.pdf", "content": base64.b64encode(pdf).decode(), "note": "Test"})
        self.assertEqual(code, 409); self.assertTrue(r["confirm_folder"]); self.assertFalse(os.path.isdir(self.belege))
        code, r = self.call("/api/receipts/upload", {"tx_id": tx["id"], "file_name": "rechnung.pdf", "content": base64.b64encode(pdf).decode(), "note": "Test", "create_folder": True})
        self.assertTrue(self.store.load("config.json")["receipts"]["folder_confirmed"])
        self.assertEqual(code, 200, r)
        e = r["entry"]
        self.assertTrue(e["path"].startswith(tx["date"][:4] + "/Privat/"), e["path"]); self.assertTrue(e["path"].endswith(".pdf"))
        self.assertTrue(os.path.isfile(os.path.join(self.belege, e["path"])))
        self.assertEqual(self.call("/api/receipts/upload", {"tx_id": tx["id"], "file_name": "x.exe", "content": base64.b64encode(b"x").decode()})[0], 400)
        code, u2 = self.call("/api/transactions?q=supermarkt&with_receipt=1")
        self.assertEqual(u2["transactions"][0]["receipts"], 1)
        code, u3 = self.call("/api/transactions?q=supermarkt&without_receipt=1")
        self.assertFalse(any(x["id"] == tx["id"] for x in u3["transactions"]))
        code, data, hdr = self.call("/api/receipts/file?id=" + e["id"], raw=True)
        self.assertEqual(code, 200); self.assertEqual(data, pdf); self.assertIn("application/pdf", hdr["Content-Type"])
        os.makedirs(os.path.join(self.belege, "2026"), exist_ok=True)
        with open(os.path.join(self.belege, "2026", "alt.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 alt")
        code, bl = self.call("/api/receipts?files=1")
        self.assertTrue(any(d["path"] == "2026/alt.pdf" and not d["linked"] for d in bl["files"]))
        code, r = self.call("/api/receipts/link", {"tx_id": tx["id"], "path": "2026/alt.pdf"})
        self.assertEqual(code, 200)
        self.assertEqual(self.call("/api/receipts/link", {"tx_id": tx["id"], "path": "../../etc/passwd"})[0], 400)
        code, r = self.call("/api/receipts/export", {"year": "2026", "entity": F.uid("priv")})
        self.assertEqual(code, 200); self.assertTrue(os.path.isfile(r["file"]))
        with zipfile.ZipFile(r["file"]) as z:
            names = z.namelist()
            self.assertIn("Belege.csv", names); self.assertEqual(len(names), 3)
        code, r = self.call("/api/receipts/update", {"id": e["id"], "note": "new"})
        self.assertEqual(r["entry"]["note"], "new")
        code, r = self.call("/api/receipts/remove", {"id": e["id"], "delete_file": False})
        self.assertTrue(r["ok"]); self.assertTrue(os.path.isfile(os.path.join(self.belege, e["path"])))
        # Kategorisieren: nur nach MoneyMoney (eine vorhandene Kategorie nach Rueckfrage)
        import mm_categories
        MockBridge.extra_cats = [("Haushalt", 0, True, {}), ("Lebensmittel", 1, False, {})]
        self.app.categories_raw = mm_categories.with_paths(MockBridge().export_categories())
        kat_of = lambda: [x for x in self.call("/api/transactions?q=supermarkt")[1]["transactions"] if x["id"] == tx["id"]][0]
        self.assertEqual(self.call("/api/categories/assign", {"ids": [tx["id"]], "category": "Gibt es nicht"})[0], 400)    # nur MoneyMoneys
        self.assertEqual(self.call("/api/categories/assign", {"ids": [tx["id"]], "category": "Haushalt"})[0], 400)          # Ordner
        # in MoneyMoney steht schon "Lebensmittel" (fremd): erst nachfragen, nichts schreiben
        code, r = self.call("/api/categories/assign", {"ids": [tx["id"]], "category": "Haushalt / Lebensmittel", "wait": True})
        self.assertEqual(r["mm"]["foreign"], [{"id": tx["id"], "mm": "Lebensmittel"}]); self.assertEqual(r["mm"]["written"], 0)
        self.assertFalse(any(w[0] == "set" and w[2] is not None for b in MockBridge.instances for w in b.written))
        self.assertEqual(kat_of()["category"], "Lebensmittel")                      # bis zur Entscheidung gilt MoneyMoney
        code, r = self.call("/api/categories/assign", {"ids": [tx["id"]], "category": "Haushalt / Lebensmittel", "mode": "overwrite", "wait": True})
        self.assertEqual(r["mm"]["written"], 1)
        self.assertTrue(any(w[0] == "set" and w[1] == tx["id"] and w[2] == F.uid("cat:Lebensmittel") for b in MockBridge.instances for w in b.written))
        self.assertEqual(next(t for t in MockBridge.state["txs"] if t["id"] == tx["id"])["categoryPath"], "Haushalt\\Lebensmittel")
        self.assertEqual((kat_of()["category"], kat_of()["source"]), ("Haushalt / Lebensmittel", "moneymoney"))
        # Excel-Exporte
        for was in ("balance", "cashflow", "planning", "tax", "transactions", "holdings", "receipts", "accounts"):
            for modus in ("months", "years"):
                code, data, hdr = self.call("/api/export/%s.xlsx?mode=%s" % (was, modus), raw=True)
                self.assertEqual(code, 200, (was, data[:200])); self.assertIn("spreadsheetml", hdr["Content-Type"])
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    self.assertIn("xl/workbook.xml", z.namelist()); self.assertIn("xl/worksheets/sheet1.xml", z.namelist())
        # cash flow and planning: the names of the page (every row a text of the catalogue, none a bare key; no "Umschichtung")
        import service as MS
        # the bookings behind a cash flow figure: kept apart from the dataset, resolved on request
        self.assertNotIn('"cf_ids"', json.dumps(self.call("/api/dataset")[1])[:10**7])
        allids = self.app.store.load_shared("cf-ids.json", {})
        area, rows = next((a, r) for a, r in allids.items() if r)
        key, per = next(iter(rows.items())); m = next(iter(per))
        code, lst = self.call("/api/transactions?" + urllib.parse.urlencode({"cf_rows": json.dumps([key]), "cf_area": area, "cf_months": m}))
        self.assertEqual(code, 200); self.assertTrue(0 < lst["hits"] <= len(set(per[m]))); self.assertTrue(all(u["id"] in per[m] for u in lst["transactions"]))
        code, lst = self.call("/api/transactions?" + urllib.parse.urlencode({"cf_rows": "5", "cf_area": area, "cf_months": m}))
        self.assertEqual((code, lst["hits"]), (200, 0))                                       # not a list: nothing (no error)
        # transactions: as filtered on the page -- every match (not only the first shown), nothing else
        for flt in ({"direction": "out"}, {"direction": "in", "limit": "1"}, {"q": "zzz-nichts"}):
            code, lst = self.call("/api/transactions?" + urllib.parse.urlencode(flt))
            rows = MS.export_sheets(self.app, "transactions", None, "months", None, flt)[0].rows
            self.assertEqual(len(rows), lst["hits"], flt)
            if flt.get("direction") == "out": self.assertTrue(rows and all(r[4] < 0 for r in rows))
        self.assertEqual(len(MS.export_sheets(self.app, "transactions", None, "months", None, {})[0].rows), lst["total"])
        for was in ("cashflow", "planning"):
            names = [str(r[0]).strip() for r in MS.export_sheets(self.app, was, None, "months")[0].rows if r and r[0]]      # the table (first sheet)
            for want in ("Überschuss", "Einnahmen", "Investitionen", "Finanzierung", "Veränderung Bankguthaben", "Abgleich mit der Bilanz", "Umschichtungen", "Veränderung Nettovermögen"):
                self.assertIn(want, names, was)
            self.assertFalse([n for n in names if "_" in n or ("Umschichtung" in n and n != "Umschichtungen")], was)
        # the rows add up: change in cash + moves between accounts + changes in value = change in net worth (each column)
        sh = MS.export_sheets(self.app, "cashflow", None, "months")[0]
        rowof = {str(r[0]).strip(): r for r in sh.rows if r and r[0]}
        for i in range(1, len(sh.header)):
            got = sum((rowof[k][i] or 0) for k in ("Veränderung Bankguthaben", "Umschichtungen", "Wertänderungen") if k in rowof)
            self.assertAlmostEqual(got, rowof["Veränderung Nettovermögen"][i] or 0, delta=0.02, msg=sh.header[i])
        # balance sheet: everything in it (positions, accounts, securities), grouped; collapsed as on the page
        code, data, hdr = self.call("/api/export/balance.xlsx?mode=months&open=securities&dep=" + F.uid("priv.depot"), raw=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            x = z.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn('outlinePr summaryBelow="0"', x); self.assertIn("Welt-ETF", x); self.assertIn('outlineLevel="2"', x)
        row = re.search(r'<row r="\d+"([^>]*)><c r="A\d+" s="\d" t="inlineStr"><is><t xml:space="preserve">\s*Welt-ETF', x)
        self.assertTrue(row and "hidden" not in row.group(1), row and row.group(1))           # the open portfolio: its securities visible
        row = re.search(r'<row r="\d+"([^>]*)><c r="A\d+" s="\d" t="inlineStr"><is><t xml:space="preserve">\s*Hausbank Giro', x)
        self.assertTrue(row and 'hidden="1"' in row.group(1))                                      # a closed position: its accounts collapsed
        try:
            import openpyxl
        except ImportError:
            openpyxl = None
        if openpyxl:
            code, data, hdr = self.call("/api/export/planning.xlsx?mode=years", raw=True)
            wb = openpyxl.load_workbook(io.BytesIO(data))
            self.assertEqual(len(wb.sheetnames), 3)
            ws = wb[wb.sheetnames[0]]
            self.assertEqual(ws["A1"].value, "Position"); self.assertTrue(any(str(c.value).startswith("20") for c in ws[1][1:]))
        # Paket-Export/-Import ueber die API
        code, data, hdr = self.call("/api/package/export?without_uuid=1&name=Test", raw=True)
        pkg = json.loads(data.decode()); self.assertEqual(pkg["name"], "Test"); self.assertNotIn(F.uid("ga.vd"), data.decode())
        pkg["config"]["loans"][0]["loan_account"] = "Darlehen Fremd"
        code, r = self.call("/api/package/import", {"package": pkg, "mode": "merge"})
        self.assertFalse(r["ok"]); self.assertEqual(r["unresolved"][0]["label"], "Darlehen Fremd")
        code, r = self.call("/api/package/import", {"package": pkg, "mode": "merge", "assignment": {"Darlehen Fremd": F.uid("ga.vd") + " | Verkäuferdarlehen"}})
        self.assertTrue(r["ok"], r); self.assertEqual(len(r["config"]["loans"]), 1)
        # Diagnose maskiert, Update-Status; MoneyMoney-Aktualisierung gibt es nicht mehr
        code, data, hdr = self.call("/api/diagnostics", raw=True)
        self.assertEqual(code, 200); self.assertNotIn(F.SELLER_IBAN, data.decode()); self.assertNotIn("Stadtbank Kontokorrent", data.decode())
        code, r = self.call("/api/update/status"); self.assertEqual(code, 200)
        code, r = self.call("/api/moneymoney/refresh", {}); self.assertEqual(code, 404)
        code, r = self.call("/api/update/check", {}); self.assertEqual(code, 200); self.assertIn("info", r)


GA_EINGABEN = {          # invented figures (round on purpose): a commercial property bought with a seller's loan
    "name": "Parkweg", "kind": "commercial", "purchase_price": 1500000, "transfer_date": "2026-01-01", "horizon_years": 24,
    "closing_costs": {"transfer_tax_percent": 3.5, "notary": 7500, "land_register": 3000},
    "building_share_percent": 70, "depreciation_percent": 2,
    "rent": {"net_rent_month": 9000, "utilities_month": 800,
              "index": {"kind": "cpi", "cpi_base": 120.0, "cpi_current": 120.0, "cpi_increase_percent": 2.0, "factor": 1, "threshold_percent": 0}},
    "costs": {"non_recoverable_pa": 2400, "reserve_pa": 4000, "increase": "cpi"},
    "loans": [{"name": "Verkäuferdarlehen", "amount": 1200000, "interest_percent": 3.0, "kind": "annuity", "annuity_month": 6000, "settlement": "yearly"}],
    "partners": [{"name": "A", "share_percent": 45, "tax_rate_percent": 42}, {"name": "B", "share_percent": 45, "tax_rate_percent": 42},
                       {"name": "C", "share_percent": 5, "tax_rate_percent": 42}, {"name": "D", "share_percent": 5, "tax_rate_percent": 30}],
    "distribution_percent": 50, "tax_refund_in_cashflow": False,
}


class ImmoEngineTests(unittest.TestCase):
    """Kalkulationskern gegen nachgerechnete Werte erfundener Kalkulationen (jaehrliche Zinsabrechnung, Indexmiete, Gesellschafter)."""

    def test_parity_with_spreadsheet(self):
        import realestate
        r = realestate.berechne(GA_EINGABEN, TODAY)
        J = {j["year"]: j for j in r["years"]}
        # Jahr 1: Miete 12 x 9.000; Zins 3 % auf den Stand 1.1.; Tilgung = 12 x 6.000 - Zins; AfA 2 % x 70 % x (KP + NK 63.000);
        # Ergebnis = Miete - Zins - AfA - Kosten; Steuer 41,4 % (45/45/5 % zu 42 %, 5 % zu 30 %); Ausschuettung 50 % des Ergebnisses
        self.assertEqual(J[2026]["rent"], 108000.0)
        self.assertEqual(J[2026]["interest"], -36000.0); self.assertEqual(J[2026]["repayment"], -36000.0)
        self.assertEqual(J[2026]["depreciation"], -21882.0); self.assertEqual(J[2026]["result"], 47718.0)
        self.assertAlmostEqual(J[2026]["tax"], -19755.25, delta=0.02)
        self.assertEqual(J[2026]["distribution"], -23859.0)
        self.assertEqual(J[2026]["cashflow"], 5741.0); self.assertEqual(J[2026]["wealth_build"], 41741.0)
        self.assertAlmostEqual(J[2026]["return_on_equity"], 0.115, 4); self.assertEqual(J[2026]["remaining_debt"], 1164000.0)
        # Jahr 2: Indexmiete +2 % (Faktor 1, Schwelle 0), Zins auf neuen Jahresstand, Kosten mit VPI
        self.assertEqual(J[2027]["rent"], 110160.0); self.assertEqual(J[2027]["interest"], -34920.0)
        self.assertEqual(J[2027]["repayment"], -37080.0); self.assertEqual(J[2027]["remaining_debt"], 1126920.0)
        self.assertEqual(J[2027]["costs"], -2448.0); self.assertEqual(J[2027]["reserve"], -4080.0)
        self.assertEqual(J[2027]["cashflow"], 6177.0); self.assertEqual(J[2029]["cashflow"], 7058.86)
        self.assertEqual(J[2029]["remaining_debt"], 1049389.43); self.assertEqual(J[2029]["rent"], 114610.46)
        K = r["figures"]
        self.assertEqual(K["equity_incl_costs"], 363000.0); self.assertEqual(K["depreciation_year"], 21882.0)
        self.assertAlmostEqual(K["price_factor"], 1500000 / 108000, 2)
        self.assertAlmostEqual(K["gross_rental_yield"], 108000 / 1500000, 4)
        self.assertEqual(len(r["years"]), 24); self.assertEqual(len(r["months"]), 24 * 12)
        # Planreihen: Monatswerte summieren sich auf das Jahr
        reihen = realestate.planreihen(r)
        self.assertAlmostEqual(sum(v for k, v in reihen["rent"].items() if k.startswith("2027")), 110160.0 + 9600, 1)   # inkl. Umlage (Zahlungsstrom)
        self.assertAlmostEqual(sum(v for k, v in reihen["costs"].items() if k.startswith("2027")), -2448.0 - 9600, 1)
        self.assertEqual(round(reihen["loans"]["Verkäuferdarlehen"]["balance_amount"]["2026-12"], 2), -1164000.0)
        sheets = realestate.sheets(r)
        self.assertEqual([x.name for x in sheets], ["Eingaben", "Kennzahlen", "Jahre", "Monate"])

    def test_parity_second_and_third_sheet(self):
        """Zwei weitere erfundene, nachgerechnete Kalkulationen: Teiljahr ab Mai, drei Darlehensarten (endfaellig, Tilgung mit spaeterer
        Sondertilgung, Annuitaet), Indexmiete mit Schwelle 5 % und Faktor 0,75, RND statt AfA-Satz; und ein einfaches Wohnobjekt."""
        import realestate
        o = {"name": "G", "purchase_price": 3000000, "transfer_date": "2026-05-01", "horizon_years": 10,          # invented figures
             "closing_costs": {"transfer_tax_percent": 3.5, "notary": 15000, "land_register": 9000},
             "building_share_percent": 55, "remaining_life_years": 20,
             "rent": {"net_rent_month": 14000, "utilities_month": 2000,
                       "index": {"kind": "cpi", "cpi_base": 120.0, "cpi_current": 120.2, "cpi_increase_percent": 1.9, "factor": 0.75, "threshold_percent": 5}},
             "costs": {"non_recoverable_pa": 15000, "reserve_pa": 8000, "increase": "none"},
             "loans": [{"name": "E", "amount": 600000, "interest_percent": 3.5, "kind": "bullet", "settlement": "yearly", "maturity": "2031-02"},
                          {"name": "T", "amount": 1000000, "interest_percent": 3.5, "kind": "repayment", "repayment_month": 3500, "special_repayment_month": 2000, "special_repayment_from": "2031-04", "settlement": "yearly"},
                          {"name": "A", "amount": 1000000, "interest_percent": 4.0, "kind": "annuity", "annuity_month": 6000, "settlement": "yearly"}],
             "partners": [{"name": "A", "share_percent": 45, "tax_rate_percent": 42}, {"name": "B", "share_percent": 45, "tax_rate_percent": 42},
                                {"name": "C", "share_percent": 5, "tax_rate_percent": 42}, {"name": "D", "share_percent": 5, "tax_rate_percent": 30}],
             "distribution_percent": 50, "tax_refund_in_cashflow": True}
        J = {j["year"]: j for j in realestate.berechne(o, TODAY)["years"]}
        # 8 Monate: Miete 8 x 14.000; AfA (KP + NK 129.000) x 55 % / 20 Jahre x 8/12; Zins je 8/12 der Jahreszinsen: 14.000 + 23.333,33 + 26.666,67
        self.assertEqual(J[2026]["months"], 8); self.assertEqual(J[2026]["rent"], 112000.0); self.assertEqual(J[2026]["depreciation"], -57365.0)
        self.assertEqual(J[2026]["interest"], -64000.0); self.assertEqual(J[2026]["costs"], -10000.0)
        self.assertAlmostEqual(J[2026]["result"], -19365.0, delta=0.02); self.assertAlmostEqual(J[2026]["tax"], 8017.09, delta=0.03)
        self.assertAlmostEqual(J[2026]["cashflow"], -8649.57, delta=0.02); self.assertAlmostEqual(J[2026]["return_on_equity"], 0.0769, 3)
        self.assertEqual(J[2026]["loans"]["T"]["balance_amount"], -972000.0); self.assertEqual(J[2026]["loans"]["A"]["balance_amount"], -978666.67)
        self.assertEqual(J[2027]["interest"], -94166.67); self.assertAlmostEqual(J[2027]["cashflow"], -12753.33, delta=0.03)
        # Indexmiete erst ab >5 % VPI-Aenderung (2029: +5,98 % x Faktor 0,75), dann wieder drei Jahre spaeter
        self.assertEqual(J[2028]["rent"], 168000.0); self.assertEqual(J[2029]["rent"], 175541.52); self.assertEqual(J[2032]["rent"], 183189.41)
        self.assertAlmostEqual(J[2030]["cashflow"], -7448.04, delta=0.02)
        self.assertEqual(J[2031]["special_repayment"], -18000.0)                                        # 9 x 2.000 (April bis Dezember)
        o2 = {"name": "W", "kind": "housing", "purchase_price": 300000, "transfer_date": "2026-01-01", "horizon_years": 5,
              "closing_costs": {"transfer_tax_percent": 3.5, "notary": 4500}, "building_share_percent": 50, "depreciation_percent": 2.0,
              "rent": {"net_rent_month": 900, "utilities_month": 150, "index": {"kind": "none"}},
              "costs": {"non_recoverable_pa": 900, "increase": "none"},
              "loans": [{"name": "B", "amount": 280000, "interest_percent": 3.5, "annuity_month": 1300, "settlement": "yearly"}],
              "partners": [{"name": "S", "share_percent": 100, "tax_rate_percent": 42}], "distribution_percent": 50, "tax_refund_in_cashflow": True}
        J2 = {j["year"]: j for j in realestate.berechne(o2, TODAY)["years"]}
        # Ergebnis 10.800 - 9.800 Zins - 3.150 AfA - 900 = -3.050 -> 42 % zurueck (im Cashflow); Tilgung 15.600 - 9.800
        self.assertEqual(J2[2026]["result"], -3050.0); self.assertEqual(J2[2026]["tax"], 1281.0); self.assertEqual(J2[2026]["cashflow"], -4419.0)
        self.assertEqual(J2[2026]["remaining_debt"], 274200.0); self.assertEqual(J2[2029]["remaining_debt"], 255553.33); self.assertEqual(J2[2030]["return_on_equity"], 0.0455)

    def test_loan_variants_and_hints(self):
        import realestate
        base = {"name": "Test", "purchase_price": 500000, "transfer_date": "2026-05-01", "horizon_years": 12, "building_share_percent": 80,
                "rent": {"net_rent_month": 2000, "index": {"kind": "none"}}, "costs": {"non_recoverable_pa": 2400, "increase": "none"}}
        # Annuitaet monatlich mit Anfangstilgung, Sondertilgung ab Monat, Zinsbindung + Anschlusszins
        o = dict(base, loans=[{"name": "Bank", "amount": 400000, "interest_percent": 3.6, "initial_repayment_percent": 2.4, "settlement": "monthly",
                                   "special_repayment_month": 500, "special_repayment_from": "2028-01", "fixed_rate_until": "2031-04", "followup_rate_percent": 5.0,
                                   "special_repayments": [{"date": "2027-06", "amount": 20000}]}])
        r = realestate.berechne(o, TODAY)
        M = {m["month"]: m for m in r["months"]}
        self.assertEqual(M["2026-05"]["interest"], -1200.0)                    # 400000 x 3,6 % / 12
        self.assertEqual(M["2026-05"]["repayment"], -800.0)                  # Annuitaet 2000 - Zins
        self.assertEqual(M["2027-06"]["special_repayment"], -20000.0)
        self.assertEqual(M["2028-01"]["special_repayment"], -500.0); self.assertEqual(M["2027-12"]["special_repayment"], 0.0)
        s_apr = M["2031-04"]["loans"]["Bank"]["balance_amount"]; z_mai = M["2031-05"]["interest"]
        self.assertAlmostEqual(z_mai, -round(abs(s_apr) * 5.0 / 1200, 2), 1)   # Anschlusszins ab Mai 2031
        # Endfaellig mit Rueckzahlung
        o2 = dict(base, loans=[{"name": "Privat", "amount": 100000, "interest_percent": 4, "kind": "bullet", "maturity": "2028-12", "maturity_kind": "payback", "deductible": False}])
        r2 = realestate.berechne(o2, TODAY)
        M2 = {m["month"]: m for m in r2["months"]}
        self.assertEqual(M2["2028-11"]["repayment"], 0.0); self.assertEqual(M2["2028-12"]["special_repayment"], -100000.0)
        self.assertEqual(M2["2029-01"]["interest"], 0.0)
        J2 = {j["year"]: j for j in r2["years"]}
        self.assertEqual(J2[2027]["interest_deductible"], 0.0); self.assertEqual(J2[2027]["interest"], -4000.0)
        # Endfaellig offen -> Hinweis
        o3 = dict(base, loans=[{"name": "Privat", "amount": 100000, "interest_percent": 4, "kind": "bullet", "maturity": "2028-12"}])
        r3 = realestate.berechne(o3, TODAY)
        self.assertTrue(any("Privat" in h for h in r3["hints"]))
        # Verkauf mit IRR, RND statt AfA-Satz, Leerstand, feste Mietsteigerung
        o4 = dict(base, remaining_life_years=40, appreciation_percent=2, sale={"year": 2031, "costs_percent": 2},
                  rent={"net_rent_month": 2000, "vacancy_percent": 5, "index": {"kind": "percent", "increase_percent": 2}})
        r4 = realestate.berechne(o4, TODAY)
        self.assertEqual(r4["figures"]["depreciation_rate"], 2.5); self.assertIsNotNone(r4["figures"]["irr"])
        self.assertEqual(r4["figures"]["exit_year"], 2031)
        J4 = {j["year"]: j for j in r4["years"]}
        self.assertEqual(J4[2026]["rent"], round(2000 * 0.95 * 8, 2))
        self.assertAlmostEqual(J4[2028]["net_rent_monthly"], round(2000 * 1.02 ** 2, 2), 2)
        # Darlehen, das vor dem Horizont ausgezahlt wurde, laeuft ab dem ersten Monat mit
        o5 = dict(base, loans=[{"name": "Alt", "amount": 100000, "interest_percent": 3, "annuity_month": 1000, "begin": "2025-11"}])
        r5 = realestate.berechne(o5, TODAY)
        self.assertEqual(r5["months"][0]["interest"], -250.0); self.assertEqual(r5["months"][0]["repayment"], -750.0)
        # Unsinnige Eingaben: Fehler statt Absturz
        with self.assertRaises(ValueError):
            realestate.berechne({"purchase_price": 100, "transfer_date": "2026-01", "partners": [{"name": "A", "share_percent": 60}, {"name": "B", "share_percent": 60}]}, TODAY)
        with self.assertRaises(ValueError):
            realestate.berechne({"purchase_price": 100, "transfer_date": "2026-01", "loans": [{"name": "X", "amount": "viel"}]}, TODAY)
        with self.assertRaises(ValueError):
            realestate.berechne({"purchase_price": -1}, TODAY)
        with self.assertRaises(ValueError):
            realestate.berechne({"purchase_price": 100, "transfer_date": "kein-datum"}, TODAY)


class LoginTouchIdTest(unittest.TestCase):
    """Touch ID eingeschaltet: Anmeldeseite fragt nur Touch ID, Passwort erst auf Wunsch; ausgeschaltet: nur Passwort."""

    def test_login_modes(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright fehlt")
        import auth
        d = tempfile.mkdtemp(prefix="kontor-tid-")
        key, src = load_or_create_master_key(d)
        store = Store(d, key, src); store.save("config.json", config_for_test(os.path.join(d, "Belege")))
        reset_mock(); patch_today()
        old_av, old_ver = auth.touchid_available, auth.touchid_verify
        auth.touchid_available = lambda: True
        auth.touchid_verify = lambda reason=None: False          # Dialog abgebrochen
        app = App(store, d, bridge_factory=MockBridge)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(); pg = b.new_page()
                pg.goto("http://127.0.0.1:%d/" % port)
                self.assertTrue(pg.is_visible("#setup-tid"))                     # Einrichtung fragt nach Touch ID
                pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.fill("#login-pw2", "sehr-geheimes-passwort")
                pg.click("#login-btn"); wait_shell(pg)
                self.assertTrue(store.load("config.json")["ui"]["touchid"])
                pg.click("#lock-btn"); pg.wait_for_selector("#login:not(.hidden)")
                pg.reload(); pg.wait_for_selector("#tid-box:not(.hidden)")
                self.assertFalse(pg.is_visible("#login-pw")); self.assertTrue(pg.is_visible("#pw-instead"))
                pg.click("#pw-instead"); self.assertTrue(pg.is_visible("#login-pw")); self.assertFalse(pg.is_visible("#tid-box"))
                self.assertTrue(pg.is_visible("#tid-instead"))
                pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.click("#login-btn"); wait_shell(pg)
                # ausschalten -> nur Passwort
                cfg = store.load("config.json"); cfg["ui"]["touchid"] = False; app.save_config(cfg)
                pg.click("#lock-btn"); pg.wait_for_selector("#login:not(.hidden)"); pg.reload(); pg.wait_for_selector("#login-pw")
                self.assertTrue(pg.is_visible("#login-pw")); self.assertFalse(pg.is_visible("#tid-box")); self.assertFalse(pg.is_visible("#tid-instead"))
                b.close()
        finally:
            auth.touchid_available, auth.touchid_verify = old_av, old_ver
            srv.shutdown(); srv.server_close(); shutil.rmtree(d, ignore_errors=True)


class BereichOrderTests(unittest.TestCase):
    def test_default_order_main_private_first(self):
        accs = [F.acc("root", "Alle Konten", 0, "Kontengruppe", True),
                F.acc("g1", "Alpha Verwaltung eGbR", 1, "Kontengruppe", True), F.acc("g1.a", "Konto A", 2, balance=1.0, bank="1"),
                F.acc("g2", "Muster GmbH", 1, "Kontengruppe", True), F.acc("g2.a", "Konto B", 2, balance=1.0, bank="1"),
                F.acc("g3", "Max Mustermann", 1, "Kontengruppe", True), F.acc("g3.a", "Konto C", 2, balance=1.0, bank="1"),
                F.acc("g4", "Familie", 1, "Kontengruppe", True), F.acc("g4.a", "Konto D", 2, balance=1.0, bank="1")]
        led = Ledger(accounts_from_export(accs), [])
        out = core.bereiche_for(led, core.merged_config({}))
        self.assertEqual([b["name"] for b in out], ["Max Mustermann", "Familie", "Alpha Verwaltung eGbR", "Muster GmbH"])
        self.assertTrue(out[0]["main_area"]); self.assertEqual([b["kind"] for b in out], ["private", "private", "company", "company"])


class SecurityHttpTests(_AppBase):
    """Over HTTP (made-up data): background requests keep no session open; a link in the receipts folder to a file elsewhere
    is not handed out."""

    def test_log_has_no_line_per_read(self):
        """A read that worked writes no line (the page asks every few seconds); one that failed does -- without its query."""
        self.login()
        import logging as _lg
        with self.assertLogs("kontor.app", level="DEBUG") as cm:
            _lg.getLogger("kontor.app").debug("start")
            self.call("/api/status"); self.call("/api/transactions?q=Erfundener+Name")
            try:
                self.call("/api/gibt-es-nicht?q=Erfundener+Name")
            except Exception:
                pass
        text = "\n".join(cm.output)
        self.assertNotIn("/api/status", text); self.assertNotIn("Erfundener", text)
        self.assertIn("/api/gibt-es-nicht 404", text)

    def _get(self, path, background=False):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path))
        if background:
            req.add_header("X-Kontor-Background", "1")
        try:
            with self.opener.open(req) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_background_requests_are_no_activity(self):
        self.login()
        tok = next(c.value for c in self.jar if c.name == "kontor_session")
        s = self.app.sessions._s[tok]
        s["last"] -= 600; was = s["last"]
        self.assertEqual(self._get("/api/status", background=True), 200)
        self.assertEqual(s["last"], was)                                  # checked, not counted as activity
        self.assertEqual(self._get("/api/status"), 200)
        self.assertGreater(s["last"], was)                                # a request you made: activity
        s["last"] -= 16 * 60
        self.assertEqual(self._get("/api/status", background=True), 401)  # idle longer than the lock: locked

    def test_link_to_a_file_elsewhere_is_not_handed_out(self):
        self.login()
        from receipts import Belege
        os.makedirs(self.belege, exist_ok=True)
        secret = os.path.join(self.dir, "geheim.pdf")
        with open(secret, "wb") as f:
            f.write(b"%PDF-1.4 geheim")
        os.symlink(secret, os.path.join(self.belege, "Fremd.pdf"))
        with open(os.path.join(self.belege, "Echt.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 echt")
        bl = Belege(self.app.store, self.app.config)
        bl.entries().extend([{"id": "aa11bb", "path": "Fremd.pdf", "name": "x"}, {"id": "cc22dd", "path": "Echt.pdf", "name": "y"}]); bl._save()
        self.assertEqual(self._get("/api/receipts/file?id=aa11bb"), 404)
        self.assertEqual(self._get("/api/receipts/file?id=cc22dd"), 200)
        code, r = self.call("/api/receipts/link", {"path": "Fremd.pdf"})
        self.assertEqual(code, 400)


class FeatureTests(_AppBase):
    """Bereiche unabhaengig von der MoneyMoney-Gruppierung, Positionen, Verlaufsquellen, inaktive Konten, Ereignisse, Immobilien, Dateiverknuepfungen."""

    def test_bereiche_positions_history_inactive(self):
        self.login()
        # Altes Konto ohne Bestand und ohne Umsaetze -> inaktiv
        accts = MockBridge.state["accounts"]
        accts.insert([a["uuid"] for a in accts].index(F.uid("priv.tr")) + 1, F.acc("priv.old", "Altes Sparbuch", 3, "Sparkonto", balance=0.0, iban="DE02100100100006820101", bank="10010010"))
        self.run_and_wait()
        code, ds = self.call("/api/dataset")
        P = ds["main_area"]; b = ds["areas"][P]
        self.assertIn(F.uid("priv.old"), b["accounts_inactive"])
        self.assertEqual(b["accounts_activity"][F.uid("priv.old")], 9999); self.assertEqual(b["accounts_activity"][F.uid("priv.giro")], 0)
        # an account new in MoneyMoney: shown at once, before its first booking
        accts.insert([a["uuid"] for a in accts].index(F.uid("priv.tr")) + 1, F.acc("priv.new", "Neues Konto", 3, "Offline-Konto", balance=0.0))
        self.run_and_wait()
        nb = self.call("/api/dataset")[1]["areas"][P]
        self.assertNotIn(F.uid("priv.new"), nb["accounts_inactive"]); self.assertIn(F.uid("priv.old"), nb["accounts_inactive"])
        code, ds = self.call("/api/dataset"); b = ds["areas"][P]
        code, kt = self.call("/api/accounts")
        self.assertEqual([x for x in kt["accounts"] if x["uuid"] == F.uid("priv.old")][0]["active_limit"], 9999)
        alt = [r for r in b["balance"]["rows"] if r["id"] == F.uid("priv.old")][0]
        self.assertTrue(alt["inactive"])
        pos = [r for r in b["balance"]["rows"] if r["group"]]
        self.assertEqual([r["id"] for r in pos][:2], ["pos:cash", "pos:securities"])
        self.assertTrue(all(r["id"].startswith("pos:") for r in pos))
        depot = [r for r in b["balance"]["rows"] if r["id"] == F.uid("priv.depot")][0]
        self.assertEqual(depot["role"], "securities"); self.assertEqual(depot["history_source"], "balances")
        self.assertEqual(depot["amounts"]["2026-11"], 85000.0)
        # kein aelterer Stand bekannt: keine Schaetzung -- der erste bekannte Wert steht davor, gekennzeichnet
        self.assertEqual(depot["amounts"]["2026-10"], 85000.0); self.assertEqual(depot["amounts"]["2024-11"], 85000.0)
        self.assertNotIn("geschaetzt_bis", depot); self.assertEqual(depot["projected_before"], "2026-11")
        self.assertTrue(any("fortgeschrieben" in w for w in b["warnings"]))
        # Verlauf: Monatsstaende setzen, Import, Quelle umstellen
        code, h = self.call("/api/history?account=" + F.uid("priv.depot"))
        self.assertEqual(h["source"], "balances"); self.assertEqual(h["recorded"]["2026-11"], 85000.0)
        code, r = self.call("/api/history", {"account": F.uid("priv.depot"), "amounts": {"2026-10": "84.000,00", "2026-09": 80000, "2025-12": 60000}})
        self.assertEqual(code, 200); self.assertTrue(r["report"])
        code, ds = self.call("/api/dataset"); b = ds["areas"][P]
        depot = [r for r in b["balance"]["rows"] if r["id"] == F.uid("priv.depot")][0]
        self.assertEqual(depot["amounts"]["2026-10"], 84000.0); self.assertEqual(depot["amounts"]["2026-09"], 80000.0)
        self.assertEqual(depot["amounts"]["2026-05"], 60000.0)     # Luecken: letzter bekannter Stand
        self.assertEqual(b["balance"]["net_worth"]["2026-10"], round(sum((r["amounts"]["2026-10"] or 0) for r in b["balance"]["rows"] if not r["group"]), 2))
        csv = "Datum;Konto;Saldo\n31.03.2026;Depot;70.000,00\n30.04.2026;Depot;71.500,50\n31.03.2026;Hausbank Giro;1.000,00\n"
        code, r = self.call("/api/history/import", {"csv": csv})
        self.assertEqual(code, 200); self.assertEqual(len(r["preview"]), 2); self.assertTrue(all(v["uuid"] for v in r["preview"]))
        code, r = self.call("/api/history/import", {"csv": csv, "take_over": True})
        self.assertEqual(r["taken_over"], 3)
        code, h = self.call("/api/history?account=" + F.uid("priv.depot"))
        self.assertEqual(h["manual"]["2026-04"], 71500.5)
        # Girokonto auf "Staende" umstellen und zurueck
        code, r = self.call("/api/history", {"account": F.uid("priv.giro"), "amounts": {}, "source": "balances"})
        code, cfg = self.call("/api/config")
        self.assertEqual(cfg["balance"]["history_source"].get(F.uid("priv.giro") + " | Hausbank Giro"), "balances")
        code, ds = self.call("/api/dataset")
        giro = [r for r in ds["areas"][P]["balance"]["rows"] if r["id"] == F.uid("priv.giro")][0]
        self.assertEqual(giro["history_source"], "balances"); self.assertEqual(giro["amounts"]["2026-03"], 1000.0)
        self.call("/api/history", {"account": F.uid("priv.giro"), "amounts": {}, "source": "transactions", "delete": True})
        code, ds = self.call("/api/dataset")
        giro = [r for r in ds["areas"][P]["balance"]["rows"] if r["id"] == F.uid("priv.giro")][0]
        self.assertEqual(giro["history_source"], "transactions")
        # Bereiche frei aus Konten zusammensetzen (unabhaengig von der Gruppierung) + Position ueberschreiben + Ausblenden
        cfg["areas"] = [
            {"id": "private", "name": "Privat", "kind": "private", "main_area": True, "accounts": [F.uid("priv") + " | Privat"]},
            {"id": "properties_list", "name": "Alle Objekte", "kind": "company", "share": 0.4,
             "accounts": [F.uid("ga.immo") + " | Immobilie Parkweg", F.uid("gb.immo") + " | Immobilie Bahnhofstraße", F.uid("ga.vd") + " | Verkäuferdarlehen", F.uid("ga.kk") + " | Stadtbank Kontokorrent"]}]
        cfg["balance"]["roles"] = {F.uid("priv.immo") + " | Immobilie Lindenstraße": "real_estate", F.uid("priv.tr") + " | Broker Giro": "term_investments"}
        cfg["balance"]["hidden_accounts"] = [F.uid("priv.tr") + " | Broker Giro"]
        cfg["balance"]["inactive_months"] = 0
        code, r = self.call("/api/config", {"config": cfg}, method="PUT")
        self.assertEqual(code, 200, r)
        code, r = self.call("/api/report", {}); self.assertTrue(r["ok"])
        code, ds = self.call("/api/dataset")
        self.assertEqual(set(ds["areas"]), {"private", "properties_list"}); self.assertEqual(ds["main_area"], "private")
        ob = ds["areas"]["properties_list"]
        saldo = {k["uuid"]: k["balance_amount"] for k in ds["accounts"] if not k["group"]}
        self.assertEqual(ob["balance"]["net_worth"]["2026-11"], round(sum(saldo[F.uid(k)] for k in ("ga.immo", "gb.immo", "ga.vd", "ga.kk")), 2))
        self.assertEqual(saldo[F.uid("gb.immo")], 2800000.0)
        self.assertEqual(ds["area_info"]["properties_list"]["account_count"], 4); self.assertEqual(ds["area_info"]["properties_list"]["kind"], "company")
        pr = ds["areas"]["private"]
        immo = [r for r in pr["balance"]["rows"] if r["id"] == F.uid("priv.immo")][0]
        self.assertEqual(immo["role"], "real_estate")
        tr = [r for r in pr["balance"]["rows"] if r["id"] == F.uid("priv.tr")][0]
        self.assertEqual(tr["role"], "term_investments"); self.assertTrue(tr["inactive"])      # ausgeblendet = wie inaktiv, zaehlt aber mit
        self.assertFalse([r for r in pr["balance"]["rows"] if r["id"] == F.uid("priv.old")][0]["inactive"])   # inaktiv_monate 0 = nie
        self.assertTrue(any(e["name"] == "Alle Objekte" and e["share"] == 0.4 for e in ds["tax"]["entities"]))
        # Konten-Export und Pakete enthalten die Bereiche
        code, data, hdr = self.call("/api/package/export?name=B", raw=True)
        pkg = json.loads(data.decode()); self.assertEqual(len(pkg["config"]["areas"]), 2)
        self.assertFalse(re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", json.dumps(pkg["config"])))         # Paket immer ohne UUIDs
        self.assertNotIn("plan", pkg)
        self.assertTrue(any(k["name"] == "Alle Objekte" for k in ds["accounts"] if k["group"]) or ds["area_names"]["properties_list"] == "Alle Objekte")

    def test_events_and_cross_bereich(self):
        self.login(); self.run_and_wait()
        code, ds = self.call("/api/dataset"); P = ds["main_area"]
        b = ds["areas"][P]; fm = b["plan_months"]
        # Umschichtung: 100.000 aus dem Depot auf das Darlehen (Tilgung auf einen Schlag) im 4. Planmonat
        mk = fm[3]
        code, r = self.call("/api/plan", {"area": P, "loans": {"Darlehen Lindenstraße": {"interest_percent_pa": "3.6", "model": "remaining_debt_monthly"}},
                                          "event": {"text": "Rückzahlung aus Depot", "kind": "reallocation", "amount": 100000, "month": mk,
                                                       "date_from": F.uid("priv.depot") + " | Depot", "after": F.uid("priv.darl") + " | Darlehen Lindenstraße"}})
        self.assertEqual(code, 200)
        self.assertEqual(self.call("/api/plan", {"area": P, "event": {"text": "x", "amount": 1, "month": "bald"}})[0], 400)
        code, ds = self.call("/api/dataset"); b = ds["areas"][P]
        self.assertEqual(len(b["plan"]["events"]), 1); eid = b["plan"]["events"][0]["id"]
        pr = {r["id"]: r for r in b["balance"]["projection"]["rows"]}
        dep, darl = pr[F.uid("priv.depot")]["amounts"], pr[F.uid("priv.darl")]["amounts"]
        self.assertAlmostEqual(dep[fm[2]] - dep[mk], 100000, delta=1500)       # Depot sinkt (abzgl. Sparplan/Rendite)
        self.assertAlmostEqual(darl[mk] - darl[fm[2]], 100000, delta=1500)     # Darlehen steigt um 100.000 (weniger negativ) abzgl. regulaerer Tilgung
        fz = {z["row"]: z for z in [s for s in b["cashflow"]["sections"] if s["name"] == "financing"][0]["rows"]}
        z_before, z_after = fz["Darlehen Lindenstraße / Zinsen"]["plan"]["amounts"][fm[2]], fz["Darlehen Lindenstraße / Zinsen"]["plan"]["amounts"][fm[4]]
        self.assertLess(abs(z_after), abs(z_before) - 250)                    # Zins faellt nach der Sondertilgung (3,6 % auf 100.000 = 300/Monat)
        # Ausgabe-Ereignis monatlich bis Enddatum -> Zeile in Ausgaben, Liquiditaet sinkt
        liq0 = b["balance"]["projection"]["cash"]
        code, r = self.call("/api/plan", {"area": P, "event": {"text": "Kita", "kind": "expense", "amount": 400, "month": fm[0], "recurrence": "monthly", "date_to": fm[5]}})
        code, ds = self.call("/api/dataset"); b = ds["areas"][P]
        az = [z for z in [s for s in b["cashflow"]["sections"] if s["name"] == "expenses"][0]["rows"] if z["row"] == "Ereignis: Kita"][0]
        self.assertEqual(az["plan"]["amounts"][fm[0]], -400.0); self.assertEqual(az["plan"]["amounts"][fm[5]], -400.0); self.assertEqual(az["plan"]["amounts"].get(fm[6], 0.0), 0.0)
        self.assertAlmostEqual(b["balance"]["projection"]["cash"][fm[5]], liq0[fm[5]] - 2400, 0)
        # Ereignis loeschen
        self.call("/api/plan", {"area": P, "event": {"id": eid, "delete": True}})
        code, ds = self.call("/api/dataset")
        self.assertEqual([e["text"] for e in ds["areas"][P]["plan"]["events"]], ["Kita"])
        # Beteiligung an anderem Bereich: Wert = Anteil x geplantes Nettovermoegen der GbR
        code, r = self.call("/api/plan", {"area": P, "appreciation": {"Beteiligung an Alpha GbR": {"area": F.uid("ga"), "share": "0.4"}}})
        code, ds = self.call("/api/dataset"); b = ds["areas"][P]
        self.assertEqual(b["plan"]["appreciation"]["Beteiligung an Alpha GbR"], {"share": 0.4, "area": F.uid("ga")})
        pr = {r["id"]: r for r in b["balance"]["projection"]["rows"]}
        gbr_nw = ds["areas"][F.uid("ga")]["balance"]["projection"]["net_worth"]
        self.assertAlmostEqual(pr[F.uid("priv.bet.ga")]["amounts"][fm[5]], round(gbr_nw[fm[5]] * 0.4, 2), 0)

    def test_equity_ratio(self):
        """Equity ratio looking through the companies: own debts plus the share of each linked company's debts; the partners'
        capital accounts are equity, never debts; nothing estimated."""
        self.login(); self.run_and_wait()
        code, ds = self.call("/api/dataset")
        P, A = F.uid("priv"), F.uid("ga")
        priv = ds["areas"][P]["balance"]["equity_ratio"]["months"]; alpha = ds["areas"][A]["balance"]["equity_ratio"]["months"]
        mk = sorted(priv)[-2]; e = priv[mk]; ea = alpha[mk]
        self.assertEqual(e["nw"], ds["areas"][P]["balance"]["net_worth"][mk]); self.assertEqual(e["capital_amount"], 0)
        self.assertEqual([f["name"] for f in e["businesses"]], ["Alpha GbR", "Beta GbR"])
        fa = e["businesses"][0]; self.assertAlmostEqual(fa["share"], 0.4); self.assertAlmostEqual(fa["debts"], ea["own"], 2)
        self.assertAlmostEqual(fa["pro_rata"], round(0.4 * ea["own"], 2), 2)
        self.assertAlmostEqual(e["debts"], e["own"] + sum(f["pro_rata"] for f in e["businesses"]), 2)
        self.assertAlmostEqual(e["quote"], round(e["equity_value"] / (e["equity_value"] + e["debts"]), 4), 4)
        # in the company: the partners' capital accounts are equity (added back), not debts
        self.assertNotIn("Kapitalkonto A", [k[0] for k in ea["accounts"]]); self.assertGreater(ea["capital_amount"], 0)
        self.assertAlmostEqual(ea["equity_value"], ds["areas"][A]["balance"]["net_worth"][mk] + ea["capital_amount"], 2)
        self.assertEqual(ds["areas"][P]["balance"]["equity_ratio"]["without_lookthrough"], [])

    def test_immobilien_api_plan_tax_export(self):
        self.login(); self.run_and_wait()
        code, r = self.call("/api/properties/template"); self.assertEqual(r["inputs"]["name"], "Neues Objekt")
        code, r = self.call("/api/properties/calculate", {"inputs": GA_EINGABEN, "without_months": True})
        self.assertEqual(code, 200); self.assertNotIn("months", r); self.assertEqual(r["years"][0]["cashflow"], 5741.0)
        self.assertEqual(self.call("/api/properties/calculate", {"inputs": {"purchase_price": "abc"}})[0], 400)
        # Objekt anlegen, Kalkulation speichern, zweites Szenario, aktiv wechseln
        code, r = self.call("/api/properties", {"action": "create", "name": "Parkweg", "area": F.uid("ga"), "category": "Vermietung \\ Parkweg",
                                                "property_account": F.uid("ga.immo") + " | Immobilie Parkweg"})
        self.assertEqual(code, 200); iid = r["property"]["id"]
        code, r = self.call("/api/properties", {"action": "calc_save", "id": iid, "calc": {"name": "Basis", "inputs": GA_EINGABEN}})
        self.assertEqual(code, 200); k1 = r["property"]["calcs"][0]; self.assertTrue(k1["active"])
        var = copy.deepcopy(GA_EINGABEN); var["rent"]["net_rent_month"] = 9500
        code, r = self.call("/api/properties", {"action": "calc_save", "id": iid, "calc": {"name": "Mehr Miete", "inputs": var}})
        k2 = r["property"]["calcs"][1]; self.assertFalse(k2["active"])
        self.assertEqual(self.call("/api/properties", {"action": "calc_save", "id": iid, "calc": {"name": "kaputt", "inputs": {"purchase_price": -5}}})[0], 400)
        code, r = self.call("/api/properties", {"action": "update", "id": iid, "in_planning": True, "loan_accounts": {"Verkäuferdarlehen": F.uid("ga.vd") + " | Verkäuferdarlehen"}})
        self.assertTrue(r["report"])
        code, ds = self.call("/api/dataset")
        im = [x for x in ds["real_estate"] if x["id"] == iid][0]
        self.assertEqual(im["figures"]["depreciation_year"], 21882.0); self.assertTrue(im["in_planning"])
        self.assertEqual(len(im["calcs"]), 2)
        # Soll/Ist: Mieteinnahmen 2026 aus Umsaetzen (9.500 x 11 Monate bis Nov) gegen Kalkulation
        si = {x["year"]: x for x in im["target_actual"]}
        self.assertEqual(si[2026]["rent_target"], 108000.0); self.assertEqual(si[2026]["rent_actual"], 9500.0 * 11)
        self.assertEqual(si[2026]["costs_actual"], -800.0 * 11); self.assertEqual(si[2026]["remaining_debt_target"], 1164000.0)
        self.assertIsNotNone(si[2026]["remaining_debt_actual"])
        # Planung der GbR: Mietzeile folgt der Kalkulation, Darlehenssaldo folgt der Kalkulation, Ausschuettung als Entnahme
        gbr = ds["areas"][F.uid("ga")]; fm = gbr["plan_months"]
        ez = [z for z in [s for s in gbr["cashflow"]["sections"] if s["name"] == "income"][0]["rows"] if z.get("property_name") == "Parkweg"][0]
        self.assertEqual(ez["plan"]["method"], "property"); self.assertEqual(ez["plan"]["amounts"][fm[0]], 9800.0)   # NKM + Umlage
        jan27 = [m for m in fm if m == "2027-01"][0]
        self.assertEqual(ez["plan"]["amounts"][jan27], 9980.0)        # 9000 x 1,02 + 800
        pr = {r["id"]: r for r in gbr["balance"]["projection"]["rows"]}
        self.assertEqual(pr[F.uid("ga.vd")]["amounts"]["2026-12"], -1164000.0)
        self.assertEqual(round(pr[F.uid("ga.immo")]["amounts"]["2026-12"]), round(1500000 * 1.02 ** (11 / 12)))   # monatliche Wertentwicklung ab dem 2. Monat
        inv = [z for z in [s for s in gbr["cashflow"]["sections"] if s["name"] == "financing"][0]["rows"] if z["row"] == "Einlagen/Entnahmen Gesellschafter"]
        self.assertTrue(inv); self.assertLess(sum(inv[0]["plan"]["amounts"].values()), 0)
        # Steuer: AfA aus der Kalkulation, wenn nicht manuell eingetragen
        code, cfg = self.call("/api/config"); cfg["tax"]["depreciation"] = {}
        self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 200)
        self.call("/api/report", {})
        code, ds = self.call("/api/dataset")
        ent = [e for e in ds["tax"]["entities"] if e["uuid"] == F.uid("ga")][0]
        self.assertEqual(ent["years"]["2026"]["properties_list"]["Parkweg"]["depreciation"], 21882.0)
        self.assertEqual(ent["years"]["2026"]["properties_list"]["Parkweg"].get("depreciation_source"), "calc")
        # Szenario aktiv wechseln -> andere Miete in der Planung; Szenario loeschen
        code, r = self.call("/api/properties", {"action": "calc_activate", "id": iid, "calc_id": k2["id"]})
        code, ds = self.call("/api/dataset"); gbr = ds["areas"][F.uid("ga")]
        ez = [z for z in [s for s in gbr["cashflow"]["sections"] if s["name"] == "income"][0]["rows"] if z.get("property_name") == "Parkweg"][0]
        self.assertEqual(ez["plan"]["amounts"][fm[0]], 10300.0)   # 9.500 + 800
        code, r = self.call("/api/properties", {"action": "calc_delete", "id": iid, "calc_id": k2["id"]})
        self.assertTrue(r["property"]["calcs"][0]["active"])
        # Excel-Export der Kalkulation
        code, data, hdr = self.call("/api/export/property.xlsx?id=%s" % iid, raw=True)
        self.assertEqual(code, 200); self.assertIn("spreadsheetml", hdr["Content-Type"])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertEqual(sum(1 for n in z.namelist() if n.startswith("xl/worksheets/sheet")), 4)
        self.assertEqual(self.call("/api/export/property.xlsx?id=nix", raw=True)[0], 404)
        # Dokumente: Verknuepfung zu einer Datei (bleibt liegen), fehlende Datei abgewiesen, Status
        doc = os.path.join(self.dir, "Kaufvertrag.pdf")
        with open(doc, "wb") as f:
            f.write(b"%PDF-1.4 vertrag")
        code, r = self.call("/api/properties", {"action": "doc_add", "id": iid, "title": "Kaufvertrag", "kind": "Vertrag", "path": doc})
        self.assertEqual(code, 200); self.assertEqual(r["property"]["documents"][0]["path"], doc)
        self.assertEqual(self.call("/api/properties", {"action": "doc_add", "id": iid, "path": doc + ".lacking"})[0], 400)
        code, r = self.call("/api/file/status?path=" + urllib.parse.quote(doc))
        self.assertEqual(r["status"], "ok"); self.assertEqual(r["size_bytes"], 16)
        code, r = self.call("/api/file/status?path=" + urllib.parse.quote(doc + ".nein"))
        self.assertEqual(r["status"], "lacking")
        did = self.call("/api/config")[1]["real_estate"][0]["documents"][0]["id"]
        code, r = self.call("/api/properties", {"action": "doc_remove", "id": iid, "document_id": did})
        self.assertEqual(r["property"]["documents"], []); self.assertTrue(os.path.isfile(doc))
        # Paket enthaelt Immobilien; Objekt loeschen
        code, data, hdr = self.call("/api/package/export?name=I", raw=True)
        self.assertEqual(len(json.loads(data.decode())["config"]["real_estate"]), 1)
        code, r = self.call("/api/properties", {"action": "delete", "id": iid}); self.assertTrue(r["ok"])
        self.assertEqual(self.call("/api/config")[1]["real_estate"], [])
        # Datei-Dialoge nur am Mac
        code, r = self.call("/api/file/choose", {"kind": "file"})
        self.assertIn(code, (400, 403))


    def test_category_renamed_in_moneymoney(self):
        """Renamed in MoneyMoney: your cash flow position follows -- also when "check" (not a sync) reads the new names first --
        and all transactions are read again."""
        self.login(); self.run_and_wait()
        cfg = copy.deepcopy(self.app.config); cfg["cashflow"]["positions"] = {"Einnahmen / Gehalt": "other_income"}; self.app.save_config(cfg)
        orig = MockBridge.export_categories

        def renamed(b):
            out = orig(b)
            for c in out:
                if c["name"] == "Gehalt":
                    c["name"] = "Lohn"
            return out
        MockBridge.export_categories = renamed
        try:
            for t in MockBridge.state["txs"]:
                if t.get("categoryPath") == "Einnahmen\\Gehalt":
                    t["categoryPath"], t["category"] = "Einnahmen\\Lohn", "Lohn"
            code, r = self.call("/api/check", {})
            self.assertEqual(code, 200)
            self.assertEqual(self.app.config["cashflow"]["positions"], {"Einnahmen / Lohn": "other_income"})
            self.assertFalse(self.app.ledger.incremental)                                   # everything read again
            self.assertFalse([t for t in self.app.ledger.txs if t.category_path == "Einnahmen\\Gehalt"])
            self.assertEqual({c["name"] for c in self.store.load("state.json")["categories_raw"]} & {"Lohn", "Gehalt"}, {"Lohn"})
        finally:
            MockBridge.export_categories = orig

    def test_saving_with_a_deleted_account(self):
        """An account deleted in MoneyMoney still has a position in the settings: saving something else works, the entry goes."""
        self.login(); self.run_and_wait()
        code, cfg = self.call("/api/config")
        gone = "0d8ae4d1-0000-4000-8000-000000000000 | Gibt es nicht mehr"
        cfg["balance"].setdefault("roles", {})[gone] = "participations"; cfg["balance"].setdefault("history_source", {})[gone] = "balances"
        self.app.save_config(cfg)
        code, cfg = self.call("/api/config"); self.assertIn(gone, cfg["balance"]["roles"])
        code, r = self.call("/api/config", {"config": cfg}, method="PUT")
        self.assertEqual(code, 200, r)
        self.assertNotIn(gone, r["config"]["balance"]["roles"]); self.assertNotIn(gone, r["config"]["balance"]["history_source"])

    def test_kontor_kategorien_und_konten_zuordnung(self):
        import mm_categories
        self.login(); self.run_and_wait()
        cfg = copy.deepcopy(self.app.config); cfg.setdefault("moneymoney", {})["allow_categorize"] = True; self.app.save_config(cfg)
        MockBridge.extra_cats = [("Haushalt", 0, True, {}), ("Werkzeug", 1, False, {})]
        self.app.categories_raw = mm_categories.with_paths(MockBridge().export_categories())
        code, k = self.call("/api/categories/positions")
        self.assertEqual(code, 200); self.assertNotIn("baum", k); self.assertNotIn("rules", k)
        self.assertGreater({r["path"]: r for r in k["categories"]}["Lebensmittel"]["count_all"], 0)
        # Offene Umsaetze: Baumarkt (ohne Kategorie) als Gruppe, ohne Vorschlag; gelernte Muster ordnen nie selbst zu
        code, off = self.call("/api/categories/unassigned")
        self.assertTrue(off["open"] >= 20)
        g = [x for x in off["groups"] if x["name"] == "Baumarkt"][0]
        self.assertIsNone(g["proposal"])
        code, ds = self.call("/api/dataset")
        self.assertEqual(set(ds["categories"]["total"]) - {"moneymoney", "without"}, set())
        # zwei zuordnen -> in MoneyMoney; danach Vorschlag fuer den Rest (nur Vorschlag) und eine Regel fuer MoneyMoney
        code, r = self.call("/api/categories/assign", {"ids": g["ids"][:2], "category": "Haushalt / Werkzeug", "wait": True})
        self.assertEqual((code, r["count"], r["mm"]["written"]), (200, 2, 2)); self.assertTrue(r["report"])
        code, off2 = self.call("/api/categories/unassigned")          # learned right after assigning: suggestion for the rest
        g2 = [x for x in off2["groups"] if x["name"] == "Baumarkt"][0]
        self.assertEqual((g2["count"], g2["proposal"]), (g["count"] - 2, "Haushalt / Werkzeug"))
        code, ds = self.call("/api/dataset")
        az = [s["rows"] for s in ds["areas"][ds["main_area"]]["cashflow"]["sections"] if s["name"] == "expenses"][0]
        lh = {d["category"]: d for d in [z for z in az if z["row"] == "Lebenshaltung"][0]["details"]}
        self.assertIn("Haushalt / Werkzeug", lh)                                            # in its position ...
        self.assertIn("", lh)                                                               # ... the rest estimated (learned), not in MoneyMoney
        code, pr = self.call("/api/categories/proposals")
        v = [x for x in pr["proposals"] if x["category"] == "Haushalt / Werkzeug"]
        self.assertEqual(len(v), 1); self.assertEqual(v[0]["phrase"], 'name:"Baumarkt"')
        self.assertEqual((v[0]["yours"], v[0]["hits"], v[0]["open"]), (2, g["count"], g["count"] - 2))
        self.assertEqual(self.call("/api/categories/proposals", {"done_items": v[0]["key"]})[0], 200)
        self.assertFalse([x for x in self.call("/api/categories/proposals")[1]["proposals"] if x["key"] == v[0]["key"]])
        self.assertFalse([w for b in MockBridge.instances for w in b.written if w[0] == "set" and w[1] not in g["ids"][:2] and w[2] is not None])
        # die alten Endpunkte gibt es nicht mehr
        for path in ("/api/categories/rule", "/api/categories/tree", "/api/categories/learn", "/api/categories/legacy"):
            self.assertEqual(self.call(path, {})[0], 404)
        # Kontenzuordnung: alle Konten 'neu', nach Bestaetigung nicht mehr; Konto explizit in anderen Bereich
        code, ds = self.call("/api/dataset")
        self.assertTrue(len(ds["accounts_new"]) >= 10); self.assertTrue(any("ohne bestätigte Zuordnung" in w for w in ds["warnings"]))
        neu = {k["uuid"]: k for k in ds["accounts_new"]}
        self.assertEqual(neu[F.uid("priv.depot")]["area"], F.uid("priv")); self.assertEqual(neu[F.uid("priv.depot")]["position"], "securities")
        code, cfg = self.call("/api/config")
        cfg["balance"]["accounts_mapping"] = {k["uuid"] + " | " + k["name"]: {"area": k["area"], "position": "", "confirmed": True} for k in ds["accounts_new"]}
        cfg["balance"]["accounts_mapping"][F.uid("priv.immo") + " | Immobilie Lindenstraße"] = {"area": F.uid("ga"), "position": "real_estate", "confirmed": True}
        self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 200)
        self.call("/api/report/rebuild", {})
        code, ds = self.call("/api/dataset")
        self.assertEqual(ds["accounts_new"], [])
        # bestaetigte Konten ohne feste Position ("auto" aus aelterer Einrichtung) werden auf den erkannten Wert festgelegt
        zu = store_cfg = self.store.load("config.json")["balance"]
        self.assertTrue(all(z["position"] in core.ROLES for z in zu["accounts_mapping"].values()))
        self.assertEqual(zu["accounts_mapping"][F.uid("priv.giro") + " | Hausbank Giro"]["position"], "cash")
        self.assertEqual(store_cfg["history_source"][F.uid("priv.depot") + " | Depot"], "balances")
        # Umbenennen und anderer Kontotyp in MoneyMoney verschieben die Position nicht mehr
        giro = [a for a in MockBridge.state["accounts"] if a["uuid"] == F.uid("priv.giro")][0]
        giro["name"], giro["type"] = "Hausbank Darlehen", "Darlehenskonto"
        self.run_and_wait()
        code, k = self.call("/api/accounts")
        self.assertEqual([x for x in k["accounts"] if x["uuid"] == F.uid("priv.giro")][0]["role"], "cash")
        giro["name"], giro["type"] = "Hausbank Giro", "Girokonto"
        self.run_and_wait()
        ga_rows = {r["id"]: r for r in ds["areas"][F.uid("ga")]["balance"]["rows"] if not r["group"]}
        self.assertIn(F.uid("priv.immo"), ga_rows); self.assertEqual(ga_rows[F.uid("priv.immo")]["role"], "real_estate")
        self.assertNotIn(F.uid("priv.immo"), {r["id"] for r in ds["areas"][ds["main_area"]]["balance"]["rows"]})
        code, k = self.call("/api/accounts")
        self.assertTrue(all(x["confirmed"] for x in k["accounts"] if not x["group"]))
        self.assertEqual([x for x in k["accounts"] if x["uuid"] == F.uid("priv.immo")][0]["area_id"], F.uid("ga"))
        # Neues Konto in MoneyMoney -> wieder 'neu'
        accts = MockBridge.state["accounts"]
        accts.insert([a["uuid"] for a in accts].index(F.uid("priv.tr")) + 1, F.acc("priv.new", "Neues Tagesgeld", 3, "Sparkonto", balance=5000.0, iban="DE02100100100006820102", bank="10010010"))
        self.run_and_wait()
        code, ds = self.call("/api/dataset")
        self.assertEqual([x["name"] for x in ds["accounts_new"]], ["Neues Tagesgeld"]); self.assertEqual(ds["accounts_new"][0]["area"], F.uid("priv"))

    def test_history_import_file(self):
        self.login(); self.run_and_wait()
        import excel
        # Matrix wie eine eigene Vermoegensuebersicht: Zeilen = Konten, Spalten = Stichtage (XLSX ohne openpyxl geschrieben und gelesen)
        wb = excel.workbook([excel.Sheet("Konten", ["", "Konto", "31.08.2026", "30.09.2026", "31.10.2026"],
                                              [["x", "Depot", 70000, 72000, 74000.5], ["y", "Fremdes Konto", 1, 2, 3], ["z", "Hausbank Giro", 100, 200, 300]])])
        code, r = self.call("/api/history/import", {"file": base64.b64encode(wb).decode(), "name": "Vermoegen.xlsx"})
        self.assertEqual(code, 200, r)
        prev = {v["name"]: v for v in r["preview"]}
        self.assertEqual(prev["Depot"]["uuid"], F.uid("priv.depot")); self.assertEqual(prev["Depot"]["count"], 3); self.assertIsNone(prev["Fremdes Konto"]["uuid"])
        code, r = self.call("/api/history/import", {"file": base64.b64encode(wb).decode(), "name": "Vermoegen.xlsx", "take_over": True,
                                                      "assignment": {"Fremdes Konto": "", "Hausbank Giro": ""}})
        self.assertEqual(r["taken_over"], 3); self.assertEqual(r["accounts"], 1)
        code, h = self.call("/api/history?account=" + F.uid("priv.depot"))
        self.assertEqual(h["manual"]["2026-10"], 74000.5)
        code, ds = self.call("/api/dataset")
        depot = [x for x in ds["areas"][ds["main_area"]]["balance"]["rows"] if x["id"] == F.uid("priv.depot")][0]
        self.assertEqual(depot["amounts"]["2026-09"], 72000.0); self.assertEqual(depot["amounts"]["2026-11"], 85000.0)
        self.assertNotIn("geschaetzt_bis", depot); self.assertEqual(depot["projected_before"], "2026-08")     # davor unbekannt, nicht geschaetzt
        # transponiert (Stichtage in der ersten Spalte) als CSV mit Monatsnamen
        csv = "Monat;Depot;Broker Giro\nJul 2026;60000;1\nJun 2026;58000;1\n"
        code, r = self.call("/api/history/import", {"csv": csv, "take_over": True, "gaps_only": True})
        self.assertEqual(r["taken_over"], 4)
        code, h = self.call("/api/history?account=" + F.uid("priv.depot"))
        self.assertEqual(h["manual"]["2026-07"], 60000.0); self.assertEqual(h["manual"]["2026-10"], 74000.5)
        self.assertEqual(self.call("/api/history/import", {"csv": "nix"})[0], 400)

    def test_external_receipt_link(self):
        self.login(); self.run_and_wait()
        code, u = self.call("/api/transactions?q=supermarkt&entity=" + F.uid("priv")); tx = u["transactions"][0]
        other = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, other, True)
        ext = os.path.join(other, "Rechnung extern.pdf")
        with open(ext, "wb") as f:
            f.write(b"%PDF-1.4 extern")
        inside = os.path.join(self.dir, "Rechnung.pdf")             # in Kontor's data folder: never linked or handed out
        with open(inside, "wb") as f:
            f.write(b"%PDF-1.4 innen")
        self.assertEqual(self.call("/api/receipts/link", {"tx_id": tx["id"], "path": inside, "external": True})[0], 400)
        code, r = self.call("/api/receipts/link", {"tx_id": tx["id"], "path": ext, "external": True, "note": "liegt in iCloud"})
        self.assertEqual(code, 200, r); e = r["entry"]; self.assertTrue(e["external"]); self.assertEqual(e["status"], "ok")
        self.assertEqual(self.call("/api/receipts/link", {"tx_id": tx["id"], "path": "relativ/x.pdf", "external": True})[0], 400)
        self.assertEqual(self.call("/api/receipts/link", {"tx_id": tx["id"], "path": ext + ".lacking", "external": True})[0], 400)
        code, data, hdr = self.call("/api/receipts/file?id=" + e["id"], raw=True)
        self.assertEqual(code, 200); self.assertEqual(data, b"%PDF-1.4 extern")
        code, bl = self.call("/api/receipts")
        self.assertTrue(any(x["id"] == e["id"] and x["external"] for x in bl["entry_list"]))
        code, r = self.call("/api/receipts/export", {"year": "2026", "entity": F.uid("priv"), "create_folder": True})
        with zipfile.ZipFile(r["file"]) as z:
            self.assertTrue(any(n.startswith("external/") for n in z.namelist()))
        # Entfernen loescht externe Dateien nie
        code, r = self.call("/api/receipts/remove", {"id": e["id"], "delete_file": True})
        self.assertTrue(r["ok"]); self.assertTrue(os.path.isfile(ext))

    def test_balance_csv_parser(self):
        from service import _parse_balance_csv
        p = _parse_balance_csv("Datum;Saldo\n31.01.2026;1.234,56\n2026-02-28;2000\n15.02.2026;1500\n")
        self.assertEqual(p[""]["2026-01"], 1234.56); self.assertEqual(p[""]["2026-02"], 2000.0)    # letzter Wert je Monat
        p = _parse_balance_csv("Datum,Konto,Saldo\n2026-01-31,Depot,\"85,000.50\"\n")
        self.assertEqual(p["Depot"]["2026-01"], 85000.5)
        p = _parse_balance_csv("Datum\tKonto\tSaldo\n31.01.2026\tGiro\t-12,5\n")
        self.assertEqual(p["Giro"]["2026-01"], -12.5)
        self.assertEqual(_parse_balance_csv("nur text"), {})

    def test_icon_und_neustart_bei_neuem_code(self):
        import service
        code, body, hdr = self.call("/icon-180.png", raw=True)
        self.assertEqual(code, 200); self.assertEqual(hdr["Content-Type"], "image/png"); self.assertTrue(body.startswith(b"\x89PNG"))
        code, body, hdr = self.call("/", raw=True)
        self.assertIn(("/icon.svg?v=%s" % core.version()).encode(), body); self.assertNotIn(b"__VERSION__", body)
        code, body, hdr = self.call("/icon.svg", raw=True)
        self.assertNotIn(b"c2pa", body); self.assertIn(b"#ffc533", body)          # the logo with its golden dot
        self.assertIsNone(self.app.code_changed())
        old = service.version_on_disk
        service.version_on_disk = lambda: "99.0.0"
        try:
            self.assertEqual(self.app.code_changed(), "99.0.0")
            self.assertFalse(self.app.restart_if_code_changed())      # Testserver: kein Selbst-Neustart
            self.login()
            code, st = self.call("/api/status")
            self.assertEqual(st["restart_pending"], "99.0.0")
        finally:
            service.version_on_disk = old

    def test_sicherung_offline_zuruecksetzen(self):
        import hashlib
        import auth
        self.login()
        # Offline-Pruefwert: eigener Salt, PBKDF2-SHA256, gleicher Hash wie WebCrypto im Browser
        code, v = self.call("/api/offline/verifier")
        self.assertEqual(code, 200); self.assertEqual(v["offline"]["rounds"], auth.OFFLINE_ROUNDS); self.assertEqual(v["lock_minutes"], 15)
        h = hashlib.pbkdf2_hmac("sha256", b"sehr-geheimes-passwort", bytes.fromhex(v["offline"]["salt"]), v["offline"]["rounds"]).hex()
        self.assertEqual(h, v["offline"]["hash"])
        self.assertNotEqual(v["offline"]["salt"], self.app.auth_record()["salt"])
        # Service Worker wird mit Versionsnummer ausgeliefert, Verifier und Sitzung werden nie zwischengespeichert
        code, body, hdr = self.call("/sw.js", raw=True)
        self.assertEqual(code, 200); self.assertIn("application/javascript", hdr["Content-Type"])
        self.assertIn(("const VERSION = '%s'" % core.version()).encode(), body); self.assertNotIn(b"__VERSION__", body)
        self.assertIn(b"'/api/session'", body); self.assertIn(b"'/api/backup'", body)
        code, mf = self.call("/manifest.webmanifest", raw=True)[:2]
        self.assertEqual(code, 200)
        # Sicherung: alles in einer Datei, wieder einspielbar
        self.run_and_wait()
        P = F.uid("priv")
        self.call("/api/plan", {"area": P, "row": "income/Arbeitseinkommen", "method": "fix", "amount": "7000", "increase": "2"})
        # nur verschluesselt (eigenes Passwort, mind. 8 Zeichen); Inhalt nicht lesbar
        self.assertEqual(self.call("/api/backup", {"password": "kurz"})[0], 400)
        code, sich = self.call("/api/backup", {"password": "sicherung-123"})
        self.assertEqual(code, 200); self.assertEqual(sich["kontor_backup_encrypted"], 1)
        self.assertNotIn("config", sich); self.assertNotIn("Gehalt", json.dumps(sich)); self.assertNotIn("sicherung-123", json.dumps(sich))
        import service as MA
        inner = MA.backup_decrypt(sich, "sicherung-123")
        self.assertEqual(inner["kontor_backup"], 1); self.assertIn("plan", inner); self.assertIn("categories", inner)
        self.assertEqual(inner["plan"]["areas"][P]["rows"]["income/Arbeitseinkommen"]["method"], "fix")
        self.assertNotIn("auth", inner)
        # Zuruecksetzen: nur lokal, nur mit Passwort; danach Einrichtung noetig, Passwort bleibt (ohne mit_passwort)
        self.assertEqual(self.call("/api/reset", {"password": "falsch"})[0], 401)
        code, r = self.call("/api/reset", {"password": "sehr-geheimes-passwort"})
        self.assertEqual(code, 200); self.assertFalse(r["setup_again"])
        self.assertIsNone(self.store.load("config.json", None)); self.assertIsNone(self.store.load("plan.json", None))
        self.assertIsNotNone(self.store.load("auth.json", None))
        self.assertEqual(self.call("/api/status")[0], 401)      # Sitzungen verworfen
        code, sess = self.call("/api/session")
        self.assertFalse(sess["signed_in"]); self.assertFalse(sess["setup_needed"])
        code, r = self.call("/api/login", {"password": "sehr-geheimes-passwort"})
        self.assertEqual(code, 200); self.csrf = r["csrf"]
        code, cfg = self.call("/api/config")
        self.assertEqual(cfg["balance"].get("areas"), core.merged_config({})["balance"].get("areas"))
        # Sicherung laden stellt Einstellungen und Plan wieder her
        self.assertEqual(self.call("/api/backup/restore", {"backup": sich, "password": "falsch-falsch"})[0], 400)
        code, r = self.call("/api/backup/restore", {"backup": sich, "password": "sicherung-123"})
        self.assertEqual(code, 200); self.assertIn("Planung", r["parts"]); self.assertIn("Einstellungen", r["parts"])
        self.assertEqual(self.store.load("plan.json")["areas"][P]["rows"]["income/Arbeitseinkommen"]["method"], "fix")
        self.assertEqual(self.call("/api/backup/restore", {"backup": {"x": 1}})[0], 400)

    def test_uninstall_removes_kontor_keeps_receipts(self):
        """Uninstall: only at the Mac and with the password; removes the service file, Kontor's own files in the data folder (also
        the log), the data key and the program folder -- the receipts folder, linked documents and foreign files stay; folders that
        are not Kontor's are refused, the key stays while encrypted data remain."""
        import service as MA
        self.login(); self.run_and_wait()
        tmp = tempfile.mkdtemp(prefix="kontor-uninst-")
        prog = os.path.join(tmp, "Kontor")
        os.makedirs(os.path.join(prog, "web"))
        for f in ("kontor.py", "service.py", "VERSION", "web/app.js"):
            open(os.path.join(prog, f), "w").close()
        os.makedirs(os.path.join(prog, "Dokumente")); open(os.path.join(prog, "Dokumente", "Vertrag.pdf"), "w").close()    # a linked document
        plist = os.path.join(tmp, "LaunchAgents", "de.kontor.service.plist"); os.makedirs(os.path.dirname(plist)); open(plist, "w").close()
        os.makedirs(self.belege, exist_ok=True)
        with open(os.path.join(self.belege, "Rechnung.pdf"), "wb") as f:
            f.write(b"%PDF-1.4")
        for name in ("kontor.log", "service.out.log", "Steuer 2024.pdf"):          # the last one is not Kontor's
            with open(os.path.join(self.dir, name), "w") as f:
                f.write("x")
        cfg = self.store.load("config.json"); cfg.setdefault("real_estate", []).append({"id": "x", "name": "X", "documents": [{"path": os.path.join(prog, "Dokumente", "Vertrag.pdf")}]})
        self.store.save("config.json", cfg); self.app.config = MA.merged_config(cfg)
        calls = []
        self.app.program_dir = prog
        self.app.uninstall_key = lambda: calls.append("key") or True        # never the real keychain
        self.app.uninstall_finish = lambda: calls.append("finish")          # never a real exit
        old_plist, old_home = MA.updates.plist_path, os.environ.get("HOME")
        MA.updates.plist_path = lambda label=MA.updates.LABEL: plist
        try:
            self.assertEqual(self.call("/api/uninstall", {"password": "falsch"})[0], 401)
            self.assertTrue(os.path.exists(self.store.path("config.json")))
            # folders that are not Kontor's: a home folder (a made-up one), a program folder without Kontor's files
            fake_home = os.path.join(tmp, "home"); os.makedirs(fake_home); open(os.path.join(fake_home, "config.json"), "w").close()
            os.environ["HOME"] = fake_home
            bad = MA.App.__new__(MA.App); bad.data_dir, bad.program_dir, bad.config, bad.store = fake_home, prog, {}, self.store
            self.assertIn("error", MA.App.uninstall(bad, True)); self.assertTrue(os.path.exists(os.path.join(fake_home, "config.json")))
            bad.data_dir, bad.program_dir = self.dir, tmp
            self.assertIn("error", MA.App.uninstall(bad, True))
            os.environ["HOME"] = old_home or ""
            code, r = self.call("/api/uninstall", {"password": "sehr-geheimes-passwort", "program_folder": True})
            self.assertEqual(code, 200); time.sleep(0.2)
            self.assertFalse(os.path.exists(plist)); self.assertFalse(os.path.exists(os.path.join(prog, "kontor.py")))
            self.assertTrue(os.path.exists(os.path.join(prog, "Dokumente", "Vertrag.pdf")))                 # linked: stays
            self.assertFalse(os.path.exists(self.store.path("config.json"))); self.assertFalse(os.path.exists(os.path.join(self.dir, "kontor.log")))
            self.assertTrue(os.path.exists(os.path.join(self.belege, "Rechnung.pdf")))                       # the receipts stay
            self.assertEqual(sorted(os.listdir(self.dir)), ["Belege", "Steuer 2024.pdf"])                     # and what is not Kontor's
            self.assertEqual(calls, ["key", "finish"]); self.assertTrue(r["key_removed"]); self.assertEqual(r["foreign"], ["Steuer 2024.pdf"]); self.assertEqual(r["kept"], [])
        finally:
            MA.updates.plist_path = old_plist
            if old_home is not None:
                os.environ["HOME"] = old_home
            shutil.rmtree(tmp, ignore_errors=True)

    def test_uninstall_from_the_terminal(self):
        """Uninstall.command / kontor.py uninstall: the same as in the app -- Kontor's files and the key go, the receipts and
        foreign files stay; without --program the program folder stays (a made-up one here)."""
        import argparse
        import kontor as K, service as MA
        self.login(); self.run_and_wait()
        os.makedirs(self.belege, exist_ok=True); open(os.path.join(self.belege, "Rechnung.pdf"), "w").close()
        open(os.path.join(self.dir, "Notiz.txt"), "w").close()
        prog = tempfile.mkdtemp(prefix="kontor-prog-")
        for f in ("kontor.py", "service.py", "VERSION"):
            open(os.path.join(prog, f), "w").close()
        calls = []
        old = (K.DATA_DIR, K.HERE, MA.App.uninstall_key, MA.updates.plist_path)
        K.DATA_DIR, K.HERE = self.dir, prog
        MA.App.uninstall_key = lambda app: calls.append("key") or True          # never the real keychain
        MA.updates.plist_path = lambda label=MA.updates.LABEL: os.path.join(prog, "none.plist")
        try:
            with mock.patch.object(K.auth, "touchid_available", return_value=False), mock.patch.object(K.time, "sleep"):
                # as in the interface: only with the Kontor password -- wrong three times, nothing is removed
                with mock.patch.object(K.getpass, "getpass", return_value="falsch") as gp:
                    self.assertEqual(K.cmd_uninstall(argparse.Namespace(yes=True, program=False)), 1)
                self.assertEqual(gp.call_count, 3); self.assertEqual(calls, []); self.assertTrue(os.path.exists(self.store.path("config.json")))
                with mock.patch.object(K.getpass, "getpass", return_value="sehr-geheimes-passwort"):
                    self.assertEqual(K.cmd_uninstall(argparse.Namespace(yes=True, program=False)), 0)
        finally:
            K.DATA_DIR, K.HERE, MA.App.uninstall_key, MA.updates.plist_path = old
        self.assertEqual(calls, ["key"]); self.assertFalse(os.path.exists(self.store.path("config.json")))
        self.assertTrue(os.path.exists(os.path.join(self.belege, "Rechnung.pdf"))); self.assertTrue(os.path.exists(os.path.join(self.dir, "Notiz.txt")))
        self.assertTrue(os.path.exists(os.path.join(prog, "kontor.py")))
        shutil.rmtree(prog, ignore_errors=True)

    def test_renew_data_key(self):
        """Datenschluessel erneuern: only at the Mac, with the password; afterwards everything opens with the new key."""
        import storage as ST
        from test_security import FakeKeychain
        self.login(); self.run_and_wait()
        old = self.app.store.master
        kc, sec = FakeKeychain(), ST._security
        kc.entries["kontor"] = old.hex()
        self.addCleanup(setattr, ST, "_security", sec)
        self.assertEqual(self.call("/api/key/renew", {"password": "sehr-geheimes-passwort"})[0], 409)     # key in a file: not here
        ST._security = kc; self.app.store.key_source = "keychain"            # a made-up keychain, never the real one
        self.assertEqual(self.call("/api/key/renew", {"password": "falsch"})[0], 401)
        self.assertEqual(self.app.store.master, old)
        code, r = self.call("/api/key/renew", {"password": "sehr-geheimes-passwort"})
        self.assertEqual(code, 200, r); self.assertGreater(r["files"], 3); self.assertNotEqual(self.app.store.master, old)
        self.assertEqual(kc.entries, {"kontor": self.app.store.master.hex()})
        self.assertTrue(Store(self.dir, self.app.store.master, "keychain").load("config.json")["areas"])
        self.assertEqual(self.call("/api/dataset")[0], 200)

    def test_uninstall_keeps_the_key_while_data_remain(self):
        """The receipts folder is the data folder itself: Kontor's files go, the receipts stay; an encrypted file that cannot be
        removed keeps the key."""
        import service as MA
        self.login()
        os.makedirs(self.belege, exist_ok=True)
        cfg = self.store.load("config.json"); cfg["receipts"]["folder"] = self.dir
        self.store.save("config.json", cfg); self.app.config = MA.merged_config(cfg)
        open(os.path.join(self.dir, "Beleg.pdf"), "w").close()
        calls = []
        self.app.program_dir = "/nonexistent"
        self.app.uninstall_key = lambda: calls.append("key") or True
        old_plist = MA.updates.plist_path
        MA.updates.plist_path = lambda label=MA.updates.LABEL: os.path.join(self.dir, "none.plist")
        real_remove = os.remove
        def stuck(p):
            if p.endswith("state.json.enc"):
                raise OSError("busy")
            real_remove(p)
        try:
            MA.os.remove = stuck
            r = self.app.uninstall(False)
        finally:
            MA.os.remove = real_remove; MA.updates.plist_path = old_plist
        self.assertTrue(os.path.exists(os.path.join(self.dir, "Beleg.pdf"))); self.assertFalse(os.path.exists(self.store.path("config.json")))
        self.assertIn(self.dir, r["kept"]); self.assertEqual(calls, []); self.assertFalse(r["key_removed"])          # data left: key kept
        r = self.app.uninstall(False)
        self.assertEqual(calls, ["key"]); self.assertTrue(r["key_removed"])

    def test_verlauf_quellen_semantik(self):
        """Umsaetze: nur Buchungen. Kontostaende (Bankkonto): eingetragene Staende sind Anker, dazwischen mit Buchungen gerechnet,
        Abweichung als Korrektur im Kapitalfluss. Vorschau im Verlauf-Fenster sofort, ohne auf den Neubau zu warten."""
        self.login(); self.run_and_wait()
        g = F.uid("priv.giro")
        code, h = self.call("/api/history?account=" + g)
        self.assertTrue(h["live"]); self.assertEqual(h["source"], "transactions")
        umsatz = h["amounts"]
        self.assertEqual(umsatz["2026-11"], 12000.0)
        # Vorschau "Kontostaende" ohne eigene Werte = identisch mit Umsaetzen (Bankkonto, Anker nur heutiger Saldo)
        code, h2 = self.call("/api/history?account=%s&source=balances" % g)
        self.assertEqual(h2["amounts"], umsatz)
        # Eigener Stand 2026-03 = 1.000: Monate bis 2026-03 um die Differenz verschoben, danach unveraendert
        code, r = self.call("/api/history", {"account": g, "amounts": {"2026-03": 1000}, "source": "balances"}, warten=False)
        self.assertEqual(r["report"], "requested"); self.assertEqual(r["history"]["source"], "balances")
        w = r["history"]["amounts"]; diff = 1000.0 - umsatz["2026-03"]
        self.assertEqual(w["2026-03"], 1000.0); self.assertEqual(w["2026-01"], round(umsatz["2026-01"] + diff, 2)); self.assertEqual(w["2026-04"], umsatz["2026-04"])
        self.assertIn("2026-03", r["history"]["anchor"])
        # Umsaetze ignorieren eigene Werte
        code, h3 = self.call("/api/history?account=%s&source=transactions" % g)
        self.assertEqual(h3["amounts"]["2026-03"], umsatz["2026-03"])
        # Nach dem Neubau: Bilanz wie Vorschau, Kapitalfluss mit Korrekturzeile, Buchungen des Kontos bleiben Zahlungsfluesse
        self.app.rebuild_report(wait=True)
        code, ds = self.call("/api/dataset"); b = ds["areas"][ds["main_area"]]
        row = [z for z in b["balance"]["rows"] if z["id"] == g][0]
        self.assertEqual(row["amounts"]["2026-03"], 1000.0); self.assertEqual(row["amounts"]["2026-01"], w["2026-01"])
        bew = [s for s in b["cashflow"]["sections"] if s["name"] == "valuation"]
        korr = [z for z in (bew[0]["rows"] if bew else []) if "Korrektur Kontostand" in z["row"]]
        self.assertTrue(korr)
        self.assertAlmostEqual(sum(korr[0]["amounts"].values()), -diff, places=2)       # Sprung zurueck auf die Buchungen nach dem Anker
        self.assertTrue(any(s["name"] == "income" and s["rows"] for s in b["cashflow"]["sections"]))
        # Import stellt importierte Konten auf Kontostaende um
        self.call("/api/history", {"account": g, "amounts": {}, "source": "transactions", "delete": True})
        code, r = self.call("/api/history/import", {"csv": "Datum;Konto;Saldo\n31.01.2026;Hausbank Giro;5.000,00\n", "take_over": True})
        self.assertEqual(r["switched"], 1)
        code, cfg = self.call("/api/config")
        self.assertEqual(cfg["balance"]["history_source"][g + " | Hausbank Giro"], "balances")

    def test_positionen_und_ausserhalb(self):
        """Positionsvorschlaege aus Name/Typ/Gruppe; Kapitalkonten und Avale ausserhalb des Nettovermoegens; keine Depot-Schaetzung."""
        from report import account_roles

        def role(name, typ, bal, group="Privat", bank=""):
            raw = [F.acc("r", "Alle", 0, "Kontengruppe", True), F.acc("g", group, 1, "Kontengruppe", True), F.acc("x", name, 2, typ, balance=bal, bank=bank)]
            return account_roles(Ledger(accounts_from_export(raw), []), core.merged_config({}))[F.uid("x")]
        self.assertEqual(role("Immobilie Musterweg", "Festgeldanlage", 5e5), "real_estate")       # Name vor Kontotyp
        self.assertEqual(role("Darlehen Immobilie X", "Darlehenskonto", -4e5), "liabilities")
        self.assertEqual(role("Darlehen an Firma", "Sonstiges", 1e5), "receivables")             # Guthaben = Forderung
        self.assertEqual(role("Barkaution Mieter", "Sonstiges", -5000), "liabilities")
        self.assertEqual(role("Kapitalkonto A", "Darlehenskonto", -1e5, group="Alpha GbR"), "liabilities")   # in der Gesellschaft: Schuld an den Gesellschafter
        self.assertEqual(role("Kapitalkonto Alpha GbR", "Sonstiges", 1e5), "participations")                       # privat: Teil der Beteiligung (Risikokapital)
        self.assertEqual(role("Gesellschafterdarlehen Alpha", "Darlehenskonto", 5e4), "participations")            # ebenso ein Gesellschafterdarlehen
        self.assertEqual(role("Eigenkapital A", "Sonstiges", -1e5, group="Alpha GbR"), "liabilities")       # Eigenkapital der Gesellschafter: wie ein Kapitalkonto
        self.assertEqual(role("Mietaval Laden", "Darlehenskonto", -3e4), "contingent")
        self.assertEqual(role("Bausparer", "Sparkonto", 2e4), "term_investments")
        self.assertEqual(role("P2P-Kredite", "Sonstiges", 5e3), "term_investments")                      # P2P is an investment, not a loan
        self.assertEqual(role("Sparkonto", "Sparkonto", 2e4, group="Anlagen"), "term_investments")      # Gruppe vor allgemeinem Typ
        self.assertEqual(role("Tagesgeld", "Sparkonto", 1e3, group="Liquidität"), "cash")
        self.assertEqual(role("Girokonto", "Girokonto", 1e3, group="Anlagen"), "cash")  # eindeutiger Typ vor Gruppe
        self.assertEqual(role("Haushaltskasse", "Bargeld", 300), "cash")
        self.assertEqual(role("Kreditkarte", "Kreditkarte", -300), "cash")
        self.login(); self.run_and_wait()
        code, ds = self.call("/api/dataset"); pb = ds["areas"][F.uid("ga")]
        self.assertEqual(pb["balance"]["outside"], [])                                   # Kapitalkonten zaehlen als Schuld der GbR
        rows = {r["id"]: r for r in pb["balance"]["rows"]}
        self.assertEqual(rows[F.uid("ga.kap.a")]["role"], "liabilities")
        saldo = {k["uuid"]: k["balance_amount"] for k in ds["accounts"] if not k["group"]}
        self.assertEqual(pb["balance"]["net_worth"]["2026-11"], round(sum(saldo[F.uid(k)] for k in ("ga.kk", "ga.immo", "ga.vd", "ga.kap.a", "ga.kap.b")), 2))
        code, h = self.call("/api/history?account=" + F.uid("priv.depot"))
        self.assertNotIn("geschaetzt_bis", h); self.assertIn("fortgeschrieben", h["hint"])          # keine Schaetzung mehr
        # Pruefung im Verlauf-Fenster: Anfangssaldo und Buchungen
        code, h = self.call("/api/history?account=" + F.uid("priv.giro"))
        self.assertIn("opening_balance", h["check"]); self.assertGreater(h["check"]["bookings"], 0)

    def test_ohne_moneymoney_mit_letztem_stand(self):
        """Nach einem Neustart ohne laufendes MoneyMoney: letzter Stand aus dem Zwischenspeicher, Verlauf und Neuberechnung gehen."""
        self.login(); self.run_and_wait()
        for _ in range(100):
            if self.store.exists("moneymoney-ledger.bin"):
                break
            time.sleep(0.1)
        self.assertTrue(self.store.exists("moneymoney-ledger.bin"))

        class Weg(MockBridge):
            def export_accounts(self):
                raise mm_bridge.MoneyMoneyNotRunning("MoneyMoney läuft nicht")
            export_transactions = export_categories = lambda self, *a, **k: (_ for _ in ()).throw(mm_bridge.MoneyMoneyNotRunning("aus"))
        app2 = App(self.store, self.dir, bridge_factory=Weg)
        for _ in range(100):
            if app2.ledger is not None:
                break
            time.sleep(0.05)
        self.assertIsNotNone(app2.ledger); self.assertTrue(app2.ledger_from_cache)
        ok, err = app2.rebuild_report(wait=True)
        self.assertTrue(ok, err)
        self.assertEqual(len(app2.ledger.txs), len(self.app.ledger.txs))
        st = app2.status(True)
        self.assertTrue(st["moneymoney"]["from_cache"]); self.assertIsNotNone(st["moneymoney"]["as_of"])

    def test_bericht_im_hintergrund(self):
        """Verlauf-Aenderungen stossen den Neubau nur an; mehrere Anstoesse ergeben einen Lauf; Status zeigt den Fortschritt."""
        self.login(); self.run_and_wait()
        code, st = self.call("/api/status")
        self.assertFalse(st["report"]["running"]); self.assertIn("locked", st["moneymoney"])
        uuid = F.uid("priv.depot")
        for v in ("70000", "71000", "72000"):
            code, r = self.call("/api/history", {"account": uuid, "amounts": {"2026-09": v}}, warten=False)
            self.assertEqual(code, 200); self.assertEqual(r["report"], "requested")
        for _ in range(300):
            code, st = self.call("/api/status")
            if not st["report"]["running"] and st["report"]["as_of"]:
                break
            time.sleep(0.1)
        self.assertFalse(st["report"]["running"]); self.assertIsNone(st["report"]["error"]); self.assertIn("history", st["report"]["reason"])
        code, ds = self.call("/api/dataset")
        row = [z for z in ds["areas"][F.uid("priv")]["balance"]["rows"] if z["id"] == uuid][0]
        self.assertEqual(row["amounts"]["2026-09"], 72000.0)
        # Doppelte Pruefung wird abgewiesen, abgebrochene Verbindung bringt den Dienst nicht aus dem Tritt
        self.app.check_lock.acquire()
        try:
            self.assertEqual(self.call("/api/check", {})[0], 409)
        finally:
            self.app.check_lock.release()
        self.assertEqual(self.call("/api/check", {})[0], 200)
        # Fortschritt beim Lesen: Schritte gemeldet, Dauer je Schritt fuer die naechste Schaetzung gemerkt
        code, p = self.call("/api/check/status")
        self.assertFalse(p["running"]); self.assertEqual(p["step"], "done")
        self.assertEqual(set(self.store.load("state.json")["read_duration"]), {"accounts", "transactions", "parse", "portfolios", "categories", "save"})

    def test_tls_helpers(self):
        import tls_cert
        self.assertIsNone(tls_cert.cert_expiry(os.path.join(self.dir, "fehlt.crt")))
        cfg = {"ui": {"tls_cert": "/irgendwo/fremd.crt"}}
        self.assertFalse(tls_cert.renew_if_due(cfg, self.dir))                 # fremde Zertifikate werden nicht angefasst
        self.assertFalse(tls_cert.renew_if_due({"ui": {}}, self.dir))


class BrowserTest(unittest.TestCase):
    """Oberflaeche im echten Browser (Playwright, falls vorhanden)."""

    def test_ui(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright fehlt")
        d = tempfile.mkdtemp(prefix="kontor-ui-")
        key, src = load_or_create_master_key(d)
        store = Store(d, key, src); store.save("config.json", config_for_test(os.path.join(d, "Belege")))
        reset_mock(); patch_today()
        app = App(store, d, bridge_factory=MockBridge)
        app.do_run(False, True)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        shots = os.environ.get("KONTOR_SHOTS")
        stopped = False
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2 if shots else 1)
                errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.goto("http://127.0.0.1:%d/" % port)
                pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.fill("#login-pw2", "sehr-geheimes-passwort"); pg.click("#login-btn")
                wait_shell(pg)
                pg.wait_for_selector(".ov-grid .ov-plot svg")
                txt = pg.query_selector("#main").inner_text().lower()
                for needle in ("nettovermögen", "vermögensstruktur", "monatlicher cashflow", "vermögensbrücke"):
                    self.assertIn(needle, txt)
                self.assertIsNone(pg.query_selector("#main table"))                                     # the overview: charts only, no tables
                self.assertFalse(pg.evaluate("document.documentElement.scrollHeight > innerHeight + 2"))   # one screen: nothing to scroll
                # a click on a chart opens its place: the monthly cash flow, the net worth bridge, the balance chart, the table
                pg.click(".ov-card[data-ov='months']"); pg.wait_for_selector("[data-cfid='months'] svg")
                self.assertEqual(pg.evaluate("location.hash"), "#cashflow"); self.assertEqual(pg.evaluate("S.cfZeit"), "12m")
                pg.wait_for_timeout(300)
                self.assertTrue(pg.evaluate("(() => { const t = document.querySelector('[data-cfid=\"months\"]').getBoundingClientRect().top; return t >= -2 && (t < 60 || scrollY + innerHeight >= document.documentElement.scrollHeight - 2); })()"))
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".ov-card[data-ov='nw'] svg")
                pg.click(".ov-card[data-ov='nw']"); pg.wait_for_selector("#bch"); pg.wait_for_timeout(300)
                self.assertEqual(pg.evaluate("location.hash"), "#balance")
                self.assertTrue(pg.evaluate("(() => { const t = document.querySelector('#bch').getBoundingClientRect().top; return t >= -2 && (t < 60 || scrollY + innerHeight >= document.documentElement.scrollHeight - 2); })()"))
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".ov-card[data-ov='comp'] svg")
                pg.focus(".ov-card[data-ov='comp']"); pg.keyboard.press("Enter"); pg.wait_for_selector("tr.pos"); pg.wait_for_timeout(300)
                self.assertEqual(pg.evaluate("location.hash"), "#balance")
                self.assertTrue(pg.evaluate("(() => { const t = document.querySelector('.wrap.bil-tbl').getBoundingClientRect().top; return t >= -2 && (t < 60 || scrollY + innerHeight >= document.documentElement.scrollHeight - 2); })()"))
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".ov-card[data-ov='wealth'] svg")
                pg.click(".ov-card[data-ov='wealth']"); pg.wait_for_selector("[data-cfid='wealth'] svg")
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".ov-grid")
                # wealth building: per block its worth and its change (money in/out, value); the monthly cash flow takes a third
                self.assertTrue(pg.query_selector_all("#ov-build .ov-bs-r")); self.assertIn("Beteiligungen", pg.inner_text("#ov-build"))
                w = pg.evaluate("[document.querySelector('.ov-card[data-ov=\"months\"]').offsetWidth, document.querySelector('.ov-grid').offsetWidth]")
                self.assertLess(w[0], w[1] * 0.36)
                # computed: a participation (money in and value apart), property net of its linked loan (repaid), cash with an
                # account whose balance is only carried backwards (unknown, not estimated), the other debts (newly borrowed)
                got = pg.evaluate("""() => { const ms = []; for (let i = 0; i < 13; i++) { const d = new Date(2025, 9 + i, 1); ms.push(d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')); }
                    const b = ms[0], k = ms[12], acc = (id, name, role, v0, v1, pb) => ({id, name, role, group: false, projected_before: pb || null, amounts: {[b]: v0, [k]: v1}});
                    const D = {months: [...ms, '2026-11'], actual_until: '2026-11', area: {kind: 'private'},
                      cashflow: {sums: {}, sections: [{name: 'valuation', rows: [{account: 'P', amounts: {'2026-03': 3000}}]}]},
                      balance: {net_worth: {}, rows: [acc('C', 'Giro', 'cash', 1000, 3000), acc('X', 'Depot', 'securities', 85000, 90000, '2026-06'), acc('P', 'Anteil', 'participations', 10000, 15000),
                        acc('I', 'Haus', 'real_estate', 400000, 400000), acc('L', 'Hausdarlehen', 'liabilities', -300000, -292800), acc('O', 'Kredit', 'liabilities', -5000, -6000)]}};
                    const keep = S.CFG.real_estate; S.CFG.real_estate = [{loan_accounts: {a: 'L | Hausdarlehen'}}];
                    try { CF.tips = []; const o = ovBuild(D), div = document.createElement('div'); div.innerHTML = o.svg;
                      return [...div.querySelectorAll('.ov-bs-r')].map(r => [r.querySelector('.ov-bs-n').textContent, r.querySelector('.ov-bs-d').textContent, r.querySelector('.ov-bs-s').textContent]); }
                    finally { S.CFG.real_estate = keep; } }""")
                self.assertEqual([g[0] for g in got], ["Beteiligungen", "Immobilien nach Darlehen", "Liquidität & Anlagen", "Übrige Schulden"])
                self.assertEqual(got[0][1:], ["+5.000 €", "15.000 € · Geldfluss +2.000 € · Wert +3.000 €"])
                self.assertEqual(got[1][1], "+7.200 €"); self.assertTrue(got[1][2].startswith("107.200 €"))
                self.assertEqual(got[2][1], "unbekannt"); self.assertEqual(got[2][2], "93.000 €")
                self.assertEqual(got[3][1:], ["-1.000 €", "-6.000 € · neu aufgenommen 1.000 €"])
                # the asset structure: a year before only where it is known; new or unknown: nothing, unchanged: ±0 %
                pg.hover("#ov-comp .ov-tile >> nth=1"); pg.wait_for_timeout(100)
                tiles = pg.evaluate("[...document.querySelectorAll('#ov-comp .ov-tile')].map(g => [...g.querySelectorAll('text')].map(x => x.textContent).join(' '))")
                self.assertFalse([x for x in tiles if "neu" in x])
                pg.click("#ov-build .ov-bs-r >> nth=0"); pg.wait_for_selector(".wrap.bil-tbl"); self.assertEqual(pg.evaluate("location.hash"), "#balance")
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".ov-grid")
                self.assertRegex(pg.inner_text(".ov-card[data-ov='comp'] .ov-head"), r"Vermögen \w+ \d\d")
                # hovering a chart: the figures under the pointer (a month, a tile, a step of the bridge, a month of the net worth)
                for sel, needle in (("#ov-months .cf-hit >> nth=3", "Veränderung Bankguthaben"), ("#ov-comp .ov-tile >> nth=0", "Anteil"),
                                    ("#ov-wealth .cf-hit >> nth=1", "€"), ("#ov-nw .ov-pt >> nth=5", "ggü. Vormonat")):
                    pg.hover(sel); pg.wait_for_timeout(120)
                    self.assertFalse(pg.evaluate("document.querySelector('#cf-tip').classList.contains('hidden')"), sel); self.assertIn(needle, pg.inner_text("#cf-tip"))
                pg.mouse.move(5, 5); pg.wait_for_timeout(100); self.assertTrue(pg.evaluate("document.querySelector('#cf-tip').classList.contains('hidden')")); self.assertNotIn("Bilanzsumme", pg.inner_text(".ov-card[data-ov='comp'] .ov-head"))
                if shots: pg.screenshot(path=os.path.join(shots, "ui_uebersicht.png"), full_page=True)
                # Datenstand unten links (zweistufig), keine Infozeile mehr in der Übersicht, Synchronisieren
                sm = pg.query_selector("#status-mini").inner_text()
                self.assertIn("Banken → MM", sm); self.assertIn("MM → Kontor", sm); self.assertNotIn("nächster", sm)
                # the page knows the version of its files: a newer one at the service (also after signing in again) loads it again
                self.assertEqual(pg.evaluate("PAGE_VERSION"), core.version()); self.assertEqual(pg.inner_text("#ver"), "v" + core.version())
                self.assertFalse(pg.evaluate("checkVersion(PAGE_VERSION)"))
                self.assertTrue(pg.evaluate("checkVersion.on = true; const r = checkVersion('9.9.9'); checkVersion.on = false; sessionStorage.removeItem('kontor.reload'); r"))
                # an old token (signed in again in another window): taken anew, the request goes through
                self.assertTrue(pg.evaluate("async () => { const ok = S.csrf; S.csrf = 'old'; const r = await api('/api/bookings/plan', {hold: [], changes: {}}); return S.csrf === ok && 'proposals' in r; }"))
                self.assertIsNone(pg.query_selector(".status-strip"))
                def sync():
                    pg.evaluate("document.querySelector('#toast').textContent = ''")
                    pg.click("#sync-btn")
                    for _ in range(150):
                        t = pg.query_selector("#toast").inner_text()
                        if "Synchronisiert" in t:
                            return t
                        pg.wait_for_timeout(200)
                    return pg.query_selector("#toast").inner_text()
                self.assertIn("Synchronisiert", sync())          # erster Lauf nach eigenen Buchungen: vollständig
                runs_vorher = len(store.load("state.json").get("history_source", []))
                self.assertIn("keine Änderung", sync())
                self.assertEqual(len(store.load("state.json").get("history_source", [])), runs_vorher)      # ohne Änderung kein neuer Regellauf
                self.assertFalse(pg.query_selector("#sync-btn").is_disabled())
                # Bereichsauswahl steht oben rechts an derselben Stelle, egal wie lang der Seitentitel ist
                x_ueb = pg.evaluate("document.querySelector('#bereich-seg').getBoundingClientRect().right")
                pg.click("#nav a[href='#planning']"); pg.wait_for_selector("#main .toolbar #modus-seg")
                self.assertEqual(x_ueb, pg.evaluate("document.querySelector('#bereich-seg').getBoundingClientRect().right"))
                self.assertNotIn("Privat", pg.query_selector("#main .toolbar").inner_text())            # Bereich nicht doppelt genannt
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".ov-grid")
                # Status unten links fuehrt zur Seite Synchronisierung
                pg.click("#status-mini .sm-link"); pg.wait_for_selector("#sync-now")
                main = pg.query_selector("#main").inner_text()
                self.assertFalse(pg.query_selector(".sync-table")); self.assertNotIn("Verkäuferdarlehen", main)      # no list of accounts: only what lags
                self.assertNotIn("Depots: Wertverlauf", main); self.assertFalse(pg.query_selector(".ab-sel"))
                self.assertIn("MoneyMoney-Sync", pg.inner_text("#main .tabs .on"))
                pg.evaluate("location.hash = '#accounts'"); pg.wait_for_selector(".acct-table .ab-sel")             # online or offline: an account's own setting
                self.assertIn("Letzter Abruf", pg.eval_on_selector("tr[data-uuid='%s'] .ab-sel" % F.uid("priv.giro"), "e => e.title"))
                # portfolios' history and the import from a file: under Kontostände
                pg.evaluate("location.hash = '#accounts/history'"); pg.wait_for_selector(".dep-hist")
                self.assertIn("Depots: Wertverlauf", pg.inner_text("#main")); self.assertTrue(pg.query_selector("#hi-drop"))
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".ov-grid")
                # Bereich wechseln
                pg.click("#bereich-seg button:nth-child(2)"); pg.wait_for_timeout(500)
                self.assertEqual(pg.evaluate("document.querySelector('#bereich-seg .on').textContent"), "Alpha GbR")
                if shots: pg.screenshot(path=os.path.join(shots, "ui_uebersicht_gbr.png"), full_page=True)
                pg.click("#bereich-seg button:nth-child(1)"); pg.wait_for_timeout(300)
                for tab in ("balance", "cashflow", "planning", "properties", "tax", "transactions", "bookings", "categories", "accounts", "settings", "help"):
                    pg.click("#nav a[href='#%s']" % tab); pg.wait_for_timeout(400)
                    self.assertTrue(pg.query_selector("#main").inner_html().strip(), tab)
                    self.assertTrue(tab == "help" or pg.query_selector("#page-title .page-hq[data-tip]"), tab)          # beside every title: what the page does
                    if shots: pg.screenshot(path=os.path.join(shots, "ui_%s.png" % tab), full_page=(tab in ("accounts", "settings", "tax", "planning", "help", "balance")))
                # the log: not in the menu -- below the help's topics and under Sichern & Zurücksetzen (the menu marks the settings)
                self.assertIsNone(pg.query_selector("#nav a[href='#log']"))
                pg.click(".help-toc a.help-toc-x[href='#log']"); pg.wait_for_selector("#log-min")
                self.assertTrue(pg.query_selector("#nav a.on[href='#settings']"))
                pg.evaluate("location.hash = '#settings/backup'"); pg.wait_for_selector("#main a[href='#log']")
                # the help icon beside a title: a click opens its section; a chart's icon its own paragraph
                pg.click("#nav a[href='#balance']"); pg.wait_for_selector("#bch svg")
                self.assertEqual(pg.get_attribute("#page-title .page-hq", "data-help"), "balance-sheet"); self.assertEqual(pg.get_attribute("#bch .hq", "data-help"), "balance-sheet-chart")
                pg.click("#bch .hq"); pg.wait_for_selector("#hl-balance-sheet-chart")
                self.assertEqual(pg.evaluate("location.hash"), "#help/balance-sheet-chart")
                # printing one chart: its own menu (right click), everything beside it left out while printing, then back
                pg.click("#nav a[href='#balance']"); pg.wait_for_selector("#bch svg"); pg.evaluate("window.print = () => { PRINT.printed = document.body.classList.contains('print-one') && !!document.querySelector('.print-off'); }")
                pg.wait_for_timeout(800)          # the page settled (a scroll of the page closes the menu)
                pg.click("#bch .bch-head", button="right"); pg.wait_for_selector("#ctx button")
                pg.dispatch_event("#ctx button", "click"); self.assertTrue(pg.evaluate("PRINT.printed")); self.assertIsNone(pg.query_selector("#ctx"))
                pg.evaluate("document.documentElement.dataset.theme = 'dark'")
                pg.evaluate("window.dispatchEvent(new Event('beforeprint'))"); self.assertIn("Kontor", pg.inner_text("#print-head"))
                self.assertEqual(pg.evaluate("document.documentElement.dataset.theme"), "light")                   # printed: always light
                pg.evaluate("window.dispatchEvent(new Event('afterprint'))"); self.assertEqual(pg.evaluate("document.documentElement.dataset.theme"), "dark")
                pg.evaluate("delete document.documentElement.dataset.theme")
                self.assertFalse(pg.evaluate("!!document.querySelector('.print-off, .print-path, #print-head') || document.body.classList.contains('print-one')"))
                # every tab of "Konten & Regeln" and "Einstellungen" draws (the old pages live there now)
                for h in ("#accounts/areas", "#accounts/history", "#accounts/positions", "#accounts/rules", "#accounts/tax", "#settings/moneymoney", "#settings/access", "#settings/receipts", "#settings/updates", "#settings/backup", "#setup"):
                    pg.evaluate("location.hash = '%s'" % h); pg.wait_for_timeout(400)
                    self.assertEqual(pg.evaluate("location.hash"), h); self.assertTrue(pg.query_selector("#main").inner_html().strip(), h)
                    self.assertIsNone(pg.query_selector("#main .banner.err"), h)
                # requests the page makes on its own a minute after you last touched it say so (they keep no session open)
                bg = []
                pg.on("request", lambda r: bg.append(r.headers.get("x-kontor-background")) if r.url.endswith("/api/status") else None)
                pg.evaluate("USER_ACT = Date.now() - 120000"); pg.evaluate("api('/api/status')"); pg.wait_for_timeout(200)
                self.assertEqual(bg[-1], "1")
                pg.mouse.move(40, 40); pg.mouse.move(60, 60); pg.evaluate("api('/api/status')"); pg.wait_for_timeout(200)
                self.assertIsNone(bg[-1])
                pg.evaluate("location.hash = '#overview'"); pg.wait_for_timeout(300)               # the setup in the menu only while a step is open
                self.assertEqual(pg.evaluate("document.querySelector('#nav-setup').classList.contains('hidden')"), not pg.evaluate("setupOpen()"))
                # Cashflow: both checks against the balance sheet as ✓ at the change in cash and in net worth; no row of their own while all adds up
                pg.click("#nav a[href='#cashflow']"); pg.wait_for_selector("#main table.cf-tbl:not(.cf-names) tr.total")
                F_ = "#main table.cf-tbl:not(.cf-names)"; N_ = "#main table.cf-names"        # the figures; the names pinned as one piece over them
                # the row lines beside the names are the figures' own, seen through (Safari may place the pinned table a fraction apart)
                self.assertTrue(pg.evaluate("[...document.querySelectorAll('.cf-pair > .cf-names tbody td')].every(c => { const s = getComputedStyle(c); return s.backgroundClip === 'padding-box' && s.borderBottomColor === 'rgba(0, 0, 0, 0)'; })"))
                # it opens on the last finished month, the running one beside it and (four columns or more) the first plan month
                vis = pg.evaluate("""(() => { const w = document.querySelector('#main .wrap'), sw = w.querySelector('thead th').offsetWidth, x0 = w.scrollLeft + sw - 1, x1 = w.scrollLeft + w.clientWidth + 1;
                  const ths = [...w.querySelectorAll('thead th[data-key]')], cur = ths.findIndex(th => th.dataset.cur), real = ths.filter(th => !(S.mode !== 'years' && th.classList.contains('year')));
                  const seen = real.filter(th => colX(w, th) >= x0 && colX(w, th) + th.offsetWidth <= x1).map(th => th.dataset.key);
                  const last = real[real.indexOf(ths[cur]) - 1].dataset.key, plan = real.slice(real.indexOf(ths[cur]) + 1).filter(th => th.classList.contains('plan')).map(th => th.dataset.key);
                  return {seen, last, cur: ths[cur].dataset.key, plan}; })()""")
                self.assertIn(vis["last"], vis["seen"]); self.assertIn(vis["cur"], vis["seen"])
                if len(vis["seen"]) >= 4: self.assertIn(vis["plan"][0], vis["seen"])
                if len(vis["seen"]) < 8: self.assertNotIn(vis["plan"][1], vis["seen"])
                self.assertEqual(pg.evaluate("firstYear(B())"), int(vis["cur"][:4]) - 1)                     # the running year and the one before
                self.assertEqual(len(pg.query_selector_all(F_ + " tr.check")), 0)
                self.assertEqual(pg.eval_on_selector_all(F_ + " tr.total", "e => e.map(r => r.querySelectorAll('.off-mark').length > 0)"), [False, False])   # all adds up: no mark
                self.assertIsNone(pg.query_selector(F_ + " tr.bal")); self.assertIsNone(pg.query_selector(F_ + " tr.fcf"))      # overview: start and end inside, no FCF
                # Safari draws pinned cells one by one, too late while scrolling: the names are one table, the figures have no pinned cell
                self.assertEqual(pg.evaluate("[...document.querySelectorAll('#main .cf-pair td')].filter(c => getComputedStyle(c).position === 'sticky').length"), 0)
                self.assertEqual(pg.evaluate("getComputedStyle(document.querySelector('#main .cf-names')).position"), "sticky")
                self.assertEqual(pg.evaluate("""(() => { const a = [...document.querySelectorAll('#main table.cf-tbl:not(.cf-names) tr')], b = [...document.querySelectorAll('#main .cf-names tr')];
                    return a.length === b.length && a.every((r, i) => Math.abs(r.getBoundingClientRect().top - b[i].getBoundingClientRect().top) < 1 && Math.abs(r.offsetHeight - b[i].offsetHeight) < 1); })()"""), True)
                self.assertFalse(pg.evaluate("[...document.querySelectorAll('#main td.plan, #main td.part')].some(c => getComputedStyle(c).opacity !== '1')"))
                self.assertFalse(pg.query_selector_all("tr.check td.warn"))
                self.assertNotIn("✓", pg.inner_text(F_ + " tr.total"))
                # a difference: its row below the change in cash, with the amount (made up); the ✓ stays where it adds up
                pg.evaluate("""(() => { const D = B(), m = D.months.filter(m => m < D.actual_until).slice(-1)[0]; window._keep = [m, D.cashflow.reconciliation[m].diff_cash]; D.cashflow.reconciliation[m].diff_cash = 12; return route(); })()""")
                pg.wait_for_timeout(200); self.assertIsNone(pg.query_selector(F_ + " tr.check"))          # inside the change in cash: a small "!" says so
                self.assertEqual(len(pg.query_selector_all(F_ + " tr[data-tog='t:bank'] .off-mark")), 1)
                pg.evaluate("S.cfTog['t:bank'] = true; route()")
                pg.wait_for_selector(F_ + " tr.check"); self.assertEqual(len(pg.query_selector_all(F_ + " tr.check")), 1); self.assertIn("12", pg.inner_text(F_ + " tr.check"))
                # a click on it: its reasons in the side panel (here without single bookings behind them)
                pg.evaluate("(() => { const u = B().cashflow.reconciliation[window._keep[0]]; window._keep.push(u.reasons_cash); u.reasons_cash = [['ue_rest', 12, '']]; return route(); })()"); pg.wait_for_timeout(200)
                pg.click(F_ + " tr.check td.tx[data-chk]"); pg.wait_for_selector("#drawer.open .cf-tx-why li")
                self.assertTrue(pg.inner_text("#drawer h2").startswith("Abgleich mit der Bilanz · ")); self.assertIn("Ohne erkannte Ursache", pg.inner_text("#drawer .cf-tx-why"))
                pg.keyboard.press("Escape"); pg.evaluate("B().cashflow.reconciliation[window._keep[0]].reasons_cash = window._keep.pop()")
                pg.evaluate("delete S.cfTog['t:bank']"); pg.wait_for_timeout(50)
                pg.evaluate("(() => { const D = B(); D.cashflow.reconciliation[window._keep[0]].diff_cash = window._keep[1]; return route(); })()"); pg.wait_for_timeout(200)
                self.assertEqual(len(pg.query_selector_all(F_ + " tr.check")), 0)
                # one outline: sections open and close, positions open to their categories; three levels (overview: sections and results only)
                self.assertEqual(pg.get_attribute("#cf-ebene button.on", "aria-label"), "Hauptebenen")   # four levels as icons, named; the most reduced first
                self.assertEqual(len(pg.query_selector_all("#cf-ebene button svg")), 4)
                self.assertTrue(pg.query_selector("#main .cf-tbl thead th:first-child #cf-ebene"))       # in the table, over the triangles
                self.assertTrue(pg.query_selector("#main .cf-tbl thead th:first-child a.cf-set[href='#accounts/positions']"))   # the gear to the positions
                self.assertIsNone(pg.query_selector("#main .toolbar a[href='#accounts/positions']"))
                # iPhone: one large triangle -- each tap a level further, after everything closed again
                lv = lambda: pg.evaluate("S.cfEbene")
                for want in (1, 2, 3, 0, 1, 2):
                    pg.evaluate("document.querySelector('.cf-lv-btn').click()"); pg.wait_for_timeout(250)
                    self.assertEqual(lv(), want)
                # a cash flow statement: operating (income and expenses within), investing, financing -- then the cash and net worth
                tops = pg.eval_on_selector_all(F_ + " tr.sec", "e => e.map(x => x.dataset.tog)")
                self.assertEqual(tops[:3], ["s:operating", "s:investing", "s:financing"])
                self.assertEqual(pg.eval_on_selector_all(F_ + " tr.sec2", "e => e.map(x => x.dataset.tog)"), ["s:income", "s:expenses"])
                body = pg.inner_text(N_ + " tbody")
                self.assertEqual(body.count("Überschuss"), 1)                                           # the operating section's name, no extra result line
                for gone in ("Nach Zins und Tilgung", "Rohertrag"):
                    self.assertNotIn(gone, body)
                self.assertNotIn("Umschichtung", body.replace("Umschichtungen", ""))                 # transfers are no row; moves between accounts are
                self.assertIn("Tilgung", pg.inner_text(N_ + " tr.sub[data-tog='g:financing|Tilgung']")); self.assertIn("Darlehen Lindenstraße", body)
                self.assertIsNone(pg.query_selector("tr.det"))
                pg.click("button.disc[data-tog^='d:']"); pg.wait_for_selector("tr.det")                 # a position: its categories
                pg.click(N_ + " tr.sec2[data-tog='s:income'] td"); pg.wait_for_timeout(200)      # income closes (its total stays)
                self.assertIsNone(pg.query_selector("tr[data-key^='income/']")); self.assertTrue(pg.query_selector("tr[data-key^='expenses/']"))
                pg.click("#cf-ebene button[data-e='0']"); pg.wait_for_timeout(200)                        # main lines: the three cash flows, the results
                self.assertEqual(pg.eval_on_selector_all(F_ + " tbody tr", "e => e.filter(x => !x.matches('.sec, .sec2, .total, .bal, .check')).length"), 0)
                self.assertEqual(pg.eval_on_selector_all(F_ + " tr.sec", "e => e.map(x => x.dataset.tog)")[:3], ["s:operating", "s:investing", "s:financing"])
                pg.click("#cf-ebene button[data-e='1']"); pg.wait_for_timeout(200)                        # overview: activities with their kinds, no positions
                self.assertEqual(len(pg.query_selector_all("#main .cf-tbl tr[data-key^='income/'], #main .cf-tbl tr[data-key^='expenses/'], #main .cf-tbl tr[data-key^='investing/']")), 0)
                self.assertTrue(pg.query_selector("tr.sec2[data-tog='s:income']")); self.assertTrue(pg.query_selector("tr.sub[data-tog='g:investing|Wertpapiere & Geldanlagen']"))
                self.assertEqual(len(pg.query_selector_all(F_ + " tr.total")), 2); self.assertEqual(len(pg.query_selector_all(F_ + " tr.check")), 0)
                self.assertLess(pg.evaluate("document.querySelector('#main .cf-tbl').offsetHeight"), 760)   # fits on a page
                # from the level "positions": the free cash flow (CFO + CFI) and the cash at the start and the end inside its change
                pg.click("#cf-ebene button[data-e='2']"); pg.wait_for_selector(F_ + " tr.fcf")
                # the change in net worth opens like the change in cash: net worth at the start and the end (from the balance sheet)
                pg.evaluate("S.cfTog['t:nv'] = true; route()"); pg.wait_for_timeout(300)
                nvr = pg.eval_on_selector_all(F_ + " tr[data-tog='t:nv'] ~ tr.bal td.to-bal", "e => e.map(td => td.dataset.bal)")
                self.assertTrue(nvr and all(x.startswith("nw|") for x in nvr))
                pg.evaluate("delete S.cfTog['t:nv']; route()"); pg.wait_for_timeout(300)
                # opening a row far down keeps it where it was on the screen (the page is drawn anew)
                rowtop = "document.querySelector('#main table.cf-tbl:not(.cf-names) tr[data-tog=\"t:bank\"]').getBoundingClientRect().top"
                pg.evaluate("document.querySelector('#main table.cf-tbl:not(.cf-names) tr[data-tog=\"t:bank\"]').scrollIntoView({block: 'end'})"); pg.wait_for_timeout(150)
                y0 = pg.evaluate(rowtop); pg.click(N_ + " tr[data-tog='t:bank'] td"); pg.wait_for_timeout(400)
                self.assertLess(abs(pg.evaluate(rowtop) - y0), 8)
                pg.click(N_ + " tr[data-tog='t:bank'] td"); pg.wait_for_timeout(300)
                val = lambda sel: [float(x.strip().replace(".", "").replace(",", ".").replace("\u2212", "-") or 0) for x in pg.eval_on_selector_all(sel + " td", "e => e.slice(1, 4).map(c => c.firstChild ? c.firstChild.textContent + (c.childNodes[1] && c.childNodes[1].nodeType === 1 && !c.childNodes[1].classList.contains('ok-mark') ? c.childNodes[1].textContent : '') : '')")]
                o, i2, f = val(F_ + " tr.sec[data-tog='s:operating']"), val(F_ + " tr.sec[data-tog='s:investing']"), val(F_ + " tr.fcf")
                self.assertEqual([round(a + b, 2) for a, b in zip(o, i2)], f)
                self.assertEqual(len(pg.query_selector_all(F_ + " tr.bal")), 4)          # cash and net worth: start and end each
                # a year with plan months: no ✓ (only actual months are checked); the end of February
                yi = pg.evaluate("[...document.querySelectorAll('#main table.cf-tbl:not(.cf-names) thead th')].findIndex(th => th.dataset.key === B().actual_until.slice(0, 4))")
                if yi > 0 and pg.evaluate("S.plan"):
                    self.assertEqual(pg.evaluate("[...document.querySelectorAll('#main table.cf-tbl:not(.cf-names) tr.total')].map(r => !!r.cells[%d].querySelector('.off-mark'))" % yi), [False, False])
                self.assertEqual(pg.evaluate("[monthEnd('2028-02'), monthEnd('2026-02'), monthEnd('2026-12')]"), ["2028-02-29", "2026-02-28", "2026-12-31"])
                pg.click("#cf-ebene button[data-e='3']"); pg.wait_for_selector("tr.det")                 # details: everything open
                self.assertGreater(len(pg.query_selector_all(F_ + " tr.det")), 2)
                # a row opened or closed: the page does not move, not even a little (no fade-in when the same page is drawn again)
                for _ in range(2):
                    y0 = pg.evaluate("(() => { const r = document.querySelector('#main table.cf-tbl:not(.cf-names) tr[data-tog=\"s:expenses\"]'); window.scrollBy(0, r.getBoundingClientRect().top - 300); return r.getBoundingClientRect().top; })()")
                    pg.click(N_ + " tr[data-tog='s:expenses'] td >> nth=0"); pg.wait_for_timeout(400)
                    self.assertAlmostEqual(pg.evaluate("document.querySelector('#main table.cf-tbl:not(.cf-names) tr[data-tog=\"s:expenses\"]').getBoundingClientRect().top"), y0, delta=0.6)
                # a figure shows the bookings behind it -- also a section's (all its rows), in the side panel; only the name opens or closes it
                exp = pg.evaluate("""(() => { const td = [...document.querySelectorAll('#main table.cf-tbl:not(.cf-names) tr.sec[data-tog="s:investing"] td.tx')].pop(), c = CF.tblCols[td.cellIndex - 1],
                    zs = CF.zs[+td.parentNode.dataset.zs].zs; td.scrollIntoView({block: 'center', inline: 'center'}); return zs.reduce((a, z) => a + c.months.reduce((b, m) => b + ((z.n || {})[m] || 0), 0), 0); })()""")
                pg.click(F_ + " tr.sec[data-tog='s:investing'] td.tx >> nth=-1"); pg.wait_for_selector("#drawer.open #cftx-page")
                got = len(pg.query_selector_all("#drawer tbody tr")); self.assertGreater(got, 0); self.assertLessEqual(got, exp)     # fetched on the click (each booking once)
                self.assertTrue(pg.inner_text("#drawer h2").startswith("Investitionen · "))                # named as the row, without its abbreviation
                self.assertTrue(pg.query_selector(F_ + " tr[data-key^='investing/']")); pg.click("#drawer .close"); pg.wait_for_timeout(200)       # still open
                pg.click(N_ + " tr.sec[data-tog='s:investing'] td"); pg.wait_for_timeout(250)
                self.assertIsNone(pg.query_selector(F_ + " tr[data-key^='investing/']"))
                pg.click(N_ + " tr.sec[data-tog='s:investing'] td"); pg.wait_for_timeout(250)
                # a figure double-clicked: its row closes (as on the name), no side panel stays open; held: it opens again
                pg.dblclick(F_ + " tr.sec[data-tog='s:investing'] td.tx >> nth=-1"); pg.wait_for_timeout(400)
                self.assertIsNone(pg.query_selector(F_ + " tr[data-key^='investing/']")); self.assertFalse(pg.evaluate("$('#drawer').classList.contains('open')"))
                bx = pg.query_selector(F_ + " tr.sec[data-tog='s:investing'] td.tx >> nth=-1").bounding_box()
                pg.mouse.move(bx["x"] + bx["width"] / 2, bx["y"] + bx["height"] / 2); pg.mouse.down(); pg.wait_for_timeout(750); pg.mouse.up(); pg.wait_for_timeout(300)
                self.assertTrue(pg.query_selector(F_ + " tr[data-key^='investing/']")); self.assertFalse(pg.evaluate("$('#drawer').classList.contains('open')"))
                kat = pg.eval_on_selector(F_ + " tr.det[data-kat]", "tr => tr.dataset.kat")
                pg.click(F_ + " tr.det[data-kat] td:nth-child(2)"); pg.wait_for_selector("#drawer.open #cftx-page")      # a side panel: the cash flow stays
                pg.click(F_ + " tr.det[data-kat] td:nth-child(2)"); pg.wait_for_timeout(250)                    # the same figure again: closed
                self.assertFalse(pg.evaluate("$('#drawer').classList.contains('open')"))
                pg.click(F_ + " tr.det[data-kat] td:nth-child(2)"); pg.wait_for_selector("#drawer.open #cftx-page")      # and again: open
                self.assertEqual(pg.evaluate("S.tab"), "cashflow"); self.assertTrue(pg.query_selector_all("#drawer tbody tr"))
                pg.click("#cftx-page"); pg.wait_for_selector("#uf-von")                                  # ... and from there the page, to correct
                self.assertEqual(pg.evaluate("S.uf.kats"), [kat]); self.assertEqual(pg.evaluate("S.tab"), "transactions")
                # unclear bookings (by their ids) open the same side panel
                pg.click("#nav a[href='#cashflow']"); pg.wait_for_selector(F_ + " tr.det")
                pg.evaluate("""api('/api/transactions?limit=2').then(r => cfOpenTx({ids: r.transactions.map(u => u.id), months: [r.transactions[1].date.slice(0, 7), r.transactions[0].date.slice(0, 7)].sort(), title: 'unclear'}))""")
                pg.wait_for_selector("#drawer.open #cftx-page"); self.assertEqual(pg.evaluate("S.tab"), "cashflow")
                self.assertEqual(len(pg.query_selector_all("#drawer tbody tr")), 2); pg.click("#drawer .close")
                pg.click("#nav a[href='#transactions']"); pg.wait_for_selector("#uf-von")
                pg.evaluate("Object.assign(S.uf, {kats: null, date_from: '', date_to: '', title: '', est: false, ext: false})")
                pg.click("#nav a[href='#cashflow']"); pg.wait_for_selector(F_ + " tr.det")
                pg.click("#cf-ebene button[data-e='2']"); pg.wait_for_timeout(200)
                for tip in pg.eval_on_selector_all("#main .cf-tbl .hq", "e => e.map(x => x.dataset.tip)"):  # headings are explained by their "?"
                    self.assertTrue(tip)
                self.assertNotIn("Tilgung +", pg.inner_text(N_))
                # the month view starts a year back; the year stepper moves its first year back and forth
                first = pg.evaluate("document.querySelector('#main thead th[data-key]').dataset.key")
                n = len(pg.query_selector_all("#main thead th[data-key]"))
                pg.click("#von-jahr button[data-d='-1']"); pg.wait_for_timeout(300)                      # an earlier year: it starts with it
                self.assertLess(pg.evaluate("document.querySelector('#main thead th[data-key]').dataset.key"), first)
                self.assertGreater(len(pg.query_selector_all("#main thead th[data-key]")), n)
                self.assertTrue(pg.is_disabled("#von-jahr button[data-d='-1']"))                        # no earlier data
                self.assertEqual(pg.evaluate("document.querySelector('#main .wrap').scrollLeft"), 0)
                pg.click("#von-jahr button[data-d='1']"); pg.wait_for_timeout(300)
                self.assertEqual(pg.evaluate("document.querySelector('#main thead th[data-key]').dataset.key"), first)
                self.assertIsNone(pg.evaluate("S.vonJahr"))
                # scrolling sideways is left alone (no snapping a moment later)
                pg.evaluate("document.querySelector('#main .wrap').scrollLeft = 37"); pg.wait_for_timeout(700)
                self.assertEqual(pg.evaluate("document.querySelector('#main .wrap').scrollLeft"), 37)
                pg.click("button.disc[data-tog^='d:']"); pg.wait_for_selector("tr.det")                 # ... and a row opened moves nothing
                self.assertEqual(pg.evaluate("document.querySelector('#main .wrap').scrollLeft"), 37)
                pg.click("button.disc[data-tog^='d:']"); pg.wait_for_timeout(200)
                # charts below the table: one period for all, colour = activity, each mark with its figures
                num = lambda t: int("".join(c for c in t.replace("\u2212", "-") if c.isdigit() or c == "-"))
                want = pg.evaluate("""(() => { const D = B(), ms = D.months.filter(m => m < D.actual_until).slice(-12), s = n => Math.round(ms.reduce((a, m) => a + (D.cashflow.sums[m][n] || 0), 0));
                    const prev = D.months[D.months.indexOf(ms[0]) - 1]; return {ein: s('income'), aus: s('expenses'), cash: s('cash_change'), start: Math.round(D.cashflow.sums[prev].bank), end: Math.round(D.cashflow.sums[ms[11]].bank)}; })()""")
                # the table's bottom rows add up: change in cash + moves between accounts + changes in value = change in net worth
                tb = pg.evaluate("""(() => { const v = tr => tr ? [...tr.querySelectorAll('td')].slice(1).map(td => td.textContent.replace('✓', '').trim()) : null;
                  return [v(document.querySelector('.cf-tbl tr[data-tog="t:bank"]')), v(document.querySelector('.cf-tbl tr[data-tog="t:umsch"]')),
                    v(document.querySelector('.cf-tbl tr[data-tog="s:valuation"]')), v([...document.querySelectorAll('.cf-tbl tr.total')].pop())]; })()""")
                self.assertTrue(tb[1], "Umschichtungen")
                pn = lambda x: float(x.replace(".", "").replace(",", ".").replace("−", "-")) if x and x.strip() not in ("", "–") else 0.0
                for i in range(len(tb[3])):
                    self.assertAlmostEqual(pn(tb[0][i]) + pn(tb[1][i]) + (pn(tb[2][i]) if tb[2] else 0), pn(tb[3][i]), delta=0.02, msg=i)
                # 1. cash bridge: opening cash, each activity with its sum and its parts, closing cash; every bar starts where the one before ended
                rows = pg.eval_on_selector_all("#cf-bridge .cf-br-row", "e => e.map(r => [r.classList[1], r.getAttribute('aria-label').split(': ')[0], r.querySelector('.cf-br-v').textContent])")
                self.assertEqual((rows[0][:2], rows[-1][:2]), (["tot", "Anfangsbestand"], ["tot", "Endbestand"]))
                self.assertEqual((num(rows[0][2]), num(rows[-1][2])), (want["start"], want["end"]))
                kids = {n: num(v) for k, n, v in rows if k == "kid"}
                self.assertEqual((kids["Einnahmen"], kids["Ausgaben"]), (want["ein"], want["aus"])); self.assertIn("Tilgung", kids); self.assertIn("Wertpapiere & Geldanlagen", kids)
                grp = [(n, num(v)) for k, n, v in rows if k == "grp"]
                self.assertEqual([n.split()[0] for n, _ in grp], ["Überschuss", "Investitionen", "Finanzierung"])
                self.assertLessEqual(abs(sum(v for _, v in grp) - (want["end"] - want["start"])), 3)      # rounded to whole euros
                # money in green, out red -- by sign, not by activity; opening and closing cash neutral
                bars = pg.eval_on_selector_all("#cf-bridge .cf-br-row", "e => e.map(r => [r.getAttribute('aria-label').split(': ')[0], (r.querySelector('.cf-br-bar') || {classList: [null, '']}).classList[1]])")
                bar = dict(bars)
                self.assertEqual((bar["Einnahmen"], bar["Ausgaben"], bar["Anfangsbestand"], bar["Endbestand"]), ("in", "out", "tot", "tot"))
                for (k, n, v), (_, c) in zip(rows, bars):
                    if k == "kid" and num(v):
                        self.assertEqual(c, "in" if num(v) > 0 else "out", n)
                # an open activity is a bracket in its colour over its parts (not a step of its own), marked like the table
                self.assertEqual(pg.eval_on_selector_all("#cf-bridge .cf-br-row.grp.br .cf-br-brace", "e => e.map(x => x.classList[1])"), ["op", "inv", "fin"])
                self.assertEqual(pg.eval_on_selector_all("#cf-bridge .cf-br-row.grp .cf-br-dot", "e => e.map(x => x.classList[1])"), ["op", "inv", "fin"])
                # opening rows never changes the width of the names (the bars keep their place)
                x0 = pg.evaluate("CF.br_liq.L"); pg.click("#cf-bridge .cf-br-row[data-br='op|Ausgaben']"); pg.wait_for_timeout(100)
                self.assertEqual(pg.evaluate("CF.br_liq.L"), x0); pg.click("#cf-bridge .cf-br-row[data-br='op|Ausgaben']"); pg.wait_for_timeout(100)
                self.assertFalse(pg.query_selector("#cf-bridge .cf-br-row.grp .cf-br-bar"))
                # a click closes an activity: one step instead; on its parts: their positions, which add up to them
                pg.click("#cf-bridge .cf-br-row[data-br='inv']"); pg.wait_for_timeout(150)
                self.assertTrue(pg.query_selector("#cf-bridge .cf-br-row[data-br='inv'] .cf-br-bar.out")); self.assertIsNone(pg.query_selector("#cf-bridge .cf-br-row[data-br='inv'] .cf-br-brace"))
                self.assertNotIn("Beteiligungen", [n for _, n, _ in pg.eval_on_selector_all("#cf-bridge .cf-br-row", "e => e.map(r => [0, r.getAttribute('aria-label').split(': ')[0], 0])")])
                pg.click("#cf-bridge .cf-br-row[data-br='op|Ausgaben']"); pg.wait_for_timeout(150)
                deep = pg.eval_on_selector_all("#cf-bridge .cf-br-row", "e => e.map(r => [r.getAttribute('aria-label').split(': ')[0], r.querySelector('.cf-br-v').textContent, r.classList.contains('br')])")
                i = [d[0] for d in deep].index("Ausgaben"); self.assertTrue(deep[i][2])
                parts = []
                for row in deep[i + 1:]:
                    if row[0] in ("Investitionen", "Finanzierung", "Endbestand"): break
                    parts.append(num(row[1]))
                self.assertGreater(len(parts), 1); self.assertLessEqual(abs(sum(parts) - num(deep[i][1])), len(parts))      # whole euros, rounded each
                self.assertEqual(pg.eval_on_selector("#cf-bridge .cf-br-row[data-br='op|Ausgaben'] .cf-br-brace", "e => e.classList[1]"), "deep")
                self.assertEqual(rows[-1][2], pg.eval_on_selector_all("#cf-bridge .cf-br-row.tot .cf-br-v", "e => e[1].textContent"))   # the end stays the end
                pg.click("#cf-bridge .cf-br-row[data-br='op|Ausgaben']"); pg.click("#cf-bridge .cf-br-row[data-br='inv']"); pg.mouse.move(5, 5); pg.wait_for_timeout(150)
                pg.hover("#cf-bridge .cf-br-row.grp >> nth=2"); pg.wait_for_timeout(150)                  # no tooltip covering the bridge
                self.assertTrue(pg.evaluate("document.querySelector('#cf-tip').classList.contains('hidden') || !document.querySelector('#cf-tip').textContent.trim()")); pg.mouse.move(5, 5)
                self.assertFalse(pg.query_selector("#cf-bridge [data-cftip]:not(.cf-br-c):not(.cf-br-v)"))      # the change and the amount: amount, year before, change
                self.assertEqual(pg.eval_on_selector_all("#cf-bridge .cf-br-row", "rs => rs.filter(r => r.querySelector('.cf-br-c')).every(r => r.querySelector('.cf-br-v').dataset.cftip === r.querySelector('.cf-br-c').dataset.cftip)"), True)
                pg.hover("#cf-bridge .cf-br-row.grp .cf-br-c >> nth=0"); pg.wait_for_timeout(150)
                self.assertIn("Vorjahr", pg.inner_text("#cf-tip"))
                if pg.viewport_size["width"] >= 1000:                                                     # beside the chart, right of the figures (Mac: room there)
                    self.assertTrue(pg.evaluate("document.querySelector('#cf-tip').getBoundingClientRect().left >= document.querySelector('#cf-bridge svg').getBoundingClientRect().right"))
                pg.mouse.move(5, 5)
                # a quiet amount axis; dragging across the chart zooms into that range, the button shows it whole again
                self.assertGreaterEqual(len(pg.query_selector_all("#cf-bridge .cf-br-grid")), 3)
                bb = pg.evaluate("(() => { const r = document.querySelector('#cf-bridge').getBoundingClientRect(); return [r.left + CF.br_liq.L, r.left + CF.br_liq.R, r.top + 30]; })()")
                pg.mouse.move(bb[0] + 20, bb[2]); pg.mouse.down(); pg.mouse.move(bb[0] + 60, bb[2], steps=5); pg.mouse.move(bb[0] + 120, bb[2] + 90, steps=5); pg.mouse.up(); pg.wait_for_timeout(200)
                self.assertEqual(pg.evaluate("getSelection().toString()"), "")                                # moving across the rows selects no text
                self.assertTrue(pg.evaluate("!!S.cfBrZoom")); self.assertTrue(pg.is_visible("#cf-br-reset")); self.assertTrue(pg.query_selector("#cf-bridge svg.zoomed"))
                pg.click("#cf-br-reset"); pg.wait_for_timeout(150)
                self.assertFalse(pg.evaluate("!!S.cfBrZoom")); self.assertTrue(pg.is_hidden("#cf-br-reset"))
                # the closing cash leads to the balance sheet: its month in view, the cash position's cell lights up
                pg.click("#cf-bridge .cf-br-row[data-bal^='liq|'] >> nth=-1"); pg.wait_for_selector("#main tr[data-pos='cash'] td.flash-hit", timeout=4000)
                self.assertEqual(pg.evaluate("S.tab"), "balance")
                hit = pg.evaluate("(() => { const td = document.querySelector('#main tr[data-pos=\"cash\"] td.flash-hit'), i = [...td.parentNode.children].indexOf(td); return document.querySelectorAll('#main .wrap.snap thead th')[i].dataset.key; })()")
                self.assertEqual(hit, pg.evaluate("cfMonths(B(), S.cfZeit)[0].slice(-1)[0]"))
                pg.wait_for_timeout(900)
                self.assertTrue(pg.evaluate("""(() => { const td = document.querySelector('#main tr[data-pos="cash"] td.flash-hit'), w = td.closest('.wrap'), a = w.getBoundingClientRect(), r = td.getBoundingClientRect();
                    return r.left >= a.left + w.querySelector('thead th').offsetWidth - 2 && r.right <= a.right + 2; })()"""))
                pg.click("#nav a[href='#cashflow']"); pg.wait_for_selector("#cf-bridge .cf-br-row")
                # an earlier year: its opening cash is before the balance sheet's first year -- it shows from that year on, the cell lights up
                # (the balance sheet set to start with the current year: the opening month of the 12 months lies before it)
                pg.evaluate("S.vonJahr = +String(B().actual_until).slice(0, 4)")
                r = pg.query_selector("#cf-bridge .cf-br-row[data-bal^='liq|']"); start = r and r.get_attribute("data-bal").split("|")[1]
                self.assertTrue(start and pg.evaluate("m => B().months.includes(m) && +m.slice(0, 4) < firstYear(B())", start), start)
                if start:
                    pg.evaluate("window._lcSave = Object.fromEntries(Object.entries(LC).filter(([id, st]) => st && st.d).map(([id, st]) => [id, [st.i0, st.i1, st.btn]]))")
                    pg.click("#cf-bridge .cf-br-row[data-bal^='liq|'] >> nth=0"); pg.wait_for_selector("#main tr[data-pos='cash'] td.flash-hit", timeout=6000)
                    hit = pg.evaluate("(() => { const td = document.querySelector('#main tr[data-pos=\"cash\"] td.flash-hit'), i = [...td.parentNode.children].indexOf(td); return document.querySelectorAll('#main .wrap.snap thead th')[i].dataset.key; })()")
                    self.assertEqual(hit, start); pg.wait_for_timeout(900)
                    self.assertTrue(pg.evaluate("""(() => { const td = document.querySelector('#main tr[data-pos="cash"] td.flash-hit'), w = td.closest('.wrap'), a = w.getBoundingClientRect(), r = td.getBoundingClientRect();
                        return r.left >= a.left + w.querySelector('thead th').offsetWidth - 2 && r.right <= a.right + 2 && r.top >= 0 && r.bottom <= innerHeight; })()"""))      # the table moved there: the cell in view
                    # ... and as after a click on that cell, the charts line up with the month: the large one shows it, the small ones end with it
                    self.assertEqual(pg.evaluate("""m => { const i = bchIndex(m), small = Object.entries(LC).filter(([id, st]) => st && st.d && document.querySelector('#lc-' + id + '-svg'));
                        return [!!BCH.d && i >= BCH.i0 && i <= BCH.i1, small.length > 0 && small.every(([id, st]) => st.d.months[st.i1] === m)]; }""", start), [True, True])
                    pg.evaluate("Object.entries(window._lcSave).forEach(([id, v]) => lcSet(id, ...v))")      # the small charts back as before, for what follows
                    pg.evaluate("S.vonJahr = null")
                    pg.click("#nav a[href='#cashflow']"); pg.wait_for_selector("#cf-bridge .cf-br-row")
                pg.click("#cf-zeit button[data-z='12m']"); pg.wait_for_timeout(300)
                # 6. the net worth bridge: from the net worth at the start to that at the end, only what changes it (no investing, no repaying)
                wbr = lambda: pg.eval_on_selector_all("#cf-wbridge .cf-br-row", "e => e.map(r => [r.getAttribute('aria-label').split(': ')[0], r.querySelector('.cf-br-v').textContent, [...r.classList]])")
                wb = wbr(); self.assertNotIn("Einnahmen", [w[0] for w in wb])                                # closed at first
                pg.click("#cf-wbridge .cf-br-row[data-br='op']"); pg.wait_for_timeout(150); wb = wbr()
                self.assertEqual((wb[0][0], wb[-1][0]), ("Anfangsvermögen", "Endvermögen"))
                names = [w[0] for w in wb]
                for n in ("Überschuss", "Zinsen", "Wertänderungen", "Einnahmen", "Ausgaben"): self.assertIn(n, names)
                self.assertNotIn("Gespart", names)
                for n in ("Tilgung", "Wertpapiere & Geldanlagen", "Investitionen", "Finanzierung"): self.assertNotIn(n, names)
                exp = pg.evaluate("""(() => { const D = B(), [cur] = cfMonths(D, S.cfZeit), nw = D.balance.net_worth, b = D.months[D.months.indexOf(cur[0]) - 1];
                  return [nw[b], nw[cur[cur.length - 1]], cfSum(D, 'net_worth_delta', cur)]; })()""")
                self.assertAlmostEqual(num(wb[0][1]), exp[0], delta=1); self.assertAlmostEqual(num(wb[-1][1]), exp[1], delta=1)
                tops = [num(w[1]) for w in wb[1:-1] if "grp" in w[2] or "one" in w[2]]
                self.assertLessEqual(abs(num(wb[0][1]) + sum(tops) - num(wb[-1][1])), len(tops) + 1)          # the steps add up, whole euros
                if abs(exp[1] - exp[0] - exp[2]) < 0.5: self.assertNotIn("Abgleich Bilanz", names)             # reconciled: no extra step
                # the same with made-up rows: parts under 50 cents count (no false balance step), the year before from all rows,
                # saving "→ extern" between you and others, value rows by their translated group
                wt = pg.evaluate("""(() => { const M = ['2024-01', '2024-02', '2025-01', '2025-02'], w = o => Object.fromEntries(M.map(m => [m, o[m] || 0]));
                  const z = (row, kind, nw, amounts, x = {}) => ({row, group: row, kind, nw, amounts: w(amounts), details: [], ...x});
                  const D = {months: ['2023-12', ...M], balance: {net_worth: {'2024-12': 1000, '2025-02': 1000 + 1000 + 1.6 - 200 + 300 - 0.4 + 0.4}},
                    cashflow: {sections: [
                      {name: 'income', rows: [z('Gehalt', 'category', true, {'2025-01': 300, '2024-01': 1000})]},
                      {name: 'expenses', rows: []},
                      {name: 'investing', rows: [z('Sparplan → extern', 'category', true, {'2025-02': -200}), z('Depot A', 'account', false, {'2025-01': -500})]},
                      {name: 'financing', rows: [z('K / Zinsen', 'interest', true, {'2025-01': -0.4, '2024-02': -500}), z('L / Zinsen', 'interest', true, {'2025-02': 0.4})]},
                      {name: 'valuation', rows: [z('Depot A', 'depot', true, {'2025-01': 1000}), ...['B', 'C', 'D'].map(n => z('Depot ' + n, 'depot', true, {'2025-02': 0.4})),
                        z('Anlage ohne Zielkonto', 'no_target', true, {'2025-02': 0.4}, {glbl: ['cf_anlage_ohne_ziel']})]},
                      {name: 'unclear', rows: []}]}};
                  D.months = ['2023-12', '2024-01', '2024-02', '2024-12', '2025-01', '2025-02'];
                  return cfWealthTree(D, ['2025-01', '2025-02'], ['2024-01', '2024-02']).map(r => [r.id, Math.round(r.v * 100) / 100, r.p == null ? null : Math.round(r.p * 100) / 100]); })()""")
                ids = {r[0]: r for r in wt}
                self.assertNotIn("off", ids); self.assertNotIn("unk", ids)
                self.assertEqual(ids["value"][1], 1001.6); self.assertEqual(ids["ext"][1], -200); self.assertEqual(ids["op"][1:], [300, 1000]); self.assertNotIn("interest", ids)   # interest: 0 in the period
                self.assertEqual(round(ids["nw0"][1] + ids["op"][1] + ids["ext"][1] + ids["value"][1], 2), ids["nw1"][1])
                flh = lambda: pg.evaluate("document.querySelector('#cf-flow svg').getBoundingClientRect().height")
                h0 = flh()
                pg.click("#cf-wbridge .cf-br-row[data-br='op|aus']"); pg.wait_for_timeout(150)
                self.assertTrue(pg.query_selector("#cf-wbridge .cf-br-row[data-br='op|aus'] .cf-br-brace"))
                self.assertIsNone(pg.query_selector("#cf-bridge .cf-br-row[data-br='op|aus']"))              # the cash bridge is left alone
                bot = lambda sel: pg.evaluate("s => document.querySelector(s).getBoundingClientRect().bottom", sel)
                opened = []
                for _ in range(8):                                                                         # open parts until the bridge is taller than the total beside it
                    if bot("#cf-wbridge") > bot("#cf-flow svg") + 30: break
                    k = pg.evaluate("(() => { const r = [...document.querySelectorAll('#cf-wbridge .cf-br-row[data-br]')].find(r => r.textContent.includes('▸')); return r ? r.dataset.br : null; })()")
                    if not k: break
                    pg.dispatch_event("#cf-wbridge .cf-br-row[data-br='%s']" % k, "click"); pg.wait_for_timeout(150); opened.append(k)
                if bot("#cf-wbridge") > h0 + 30 + pg.evaluate("document.querySelector('#cf-flow svg').getBoundingClientRect().top"):
                    self.assertLess(abs(bot("#cf-flow svg") - bot("#cf-wbridge")), 3); self.assertGreater(flh(), h0 + 20)      # beside it the total grows with it ...
                for k in reversed(opened): pg.dispatch_event("#cf-wbridge .cf-br-row[data-br='%s']" % k, "click"); pg.wait_for_timeout(120)
                pg.click("#cf-wbridge .cf-br-row[data-br='op|aus']"); pg.wait_for_timeout(100)
                self.assertLess(abs(flh() - h0), 2)                                                       # ... and shrinks back
                # 2. per month: income, expenses, investing, financing stacked; the change in cash on its own scale below
                tips = pg.evaluate("[...document.querySelectorAll('#cf-bridge [data-bal], #cf-wbridge [data-bal]')].map(e => (e.querySelector('title') || {}).textContent || e.getAttribute('title') || e.getAttribute('aria-label') || '')")
                self.assertTrue(tips); self.assertFalse([x for x in tips if "undefined" in x or "NaN" in x], tips)      # start and end: the month written out
                self.assertEqual(len(pg.query_selector_all("#cf-months .cf-hit")), 12)
                ends = pg.evaluate("(() => { const D = B(), [ms] = cfMonths(D, S.cfZeit); return [ML(ms[0]), ML(ms[ms.length - 1])]; })()")
                ticks = pg.eval_on_selector_all("#cf-months text.cf-tick", "e => e.map(x => x.textContent)")
                for w in ends: self.assertIn(w, ticks)                                                     # the first and the last month always labelled
                for c in ("ein", "aus", "inv", "fin", "bank", "umsch", "value"):          # below: as the table -- change in cash, moves between accounts, change in value
                    self.assertTrue(pg.query_selector("#cf-months .cf-col." + c), c)
                self.assertIsNone(pg.query_selector("#cf-months .cf-prev-o"))         # no year before in it (too little gain, confusing)
                nets = pg.evaluate("[...document.querySelectorAll('#cf-months line.cf-net')].length"); self.assertGreater(nets, 0); self.assertLessEqual(nets, 24)      # the result of each month as a short line (both panels)
                self.assertFalse(pg.evaluate("[...document.querySelectorAll('#main svg *')].some(e => [...e.attributes].some(a => a.value.includes('NaN')))"))      # every part drawn (no unknown value)
                self.assertTrue(pg.query_selector("#cf-months rect.cf-col.umsch, #cf-months rect.cf-col.value"))      # reallocation and changes in value below
                nwk = pg.evaluate("""(() => { const D = B(), m = D.months.filter(m => m < D.actual_until).slice(-1)[0], s = D.cashflow.sums[m];
                    const u = -D.cashflow.sections.reduce((a, sk) => sk.name === 'valuation' ? a : a + sk.rows.reduce((c, z) => z.nw ? c : c + ((z.amounts || {})[m] || 0), 0), 0);
                    return [s.net_worth_delta, s.valuation, u]; })()""")
                pg.hover("#cf-months .cf-hit >> nth=11"); pg.wait_for_timeout(150)
                tip = pg.inner_text("#cf-tip")
                self.assertIn("=\nVeränderung Bankguthaben", tip)                                     # the results: "=" instead of a colour
                k11 = pg.get_attribute("#cf-months .cf-hit >> nth=11", "data-k")                          # its month heading in the table, softly
                self.assertEqual(pg.eval_on_selector_all(".cf-tbl:not(.cf-names) thead th.cf-hov", "e => e.map(x => x.dataset.key)"), [k11])
                for w in ("Einnahmen", "Ausgaben", "Investitionen", "Finanzierung", "Veränderung Bankguthaben", "Umschichtungen", "Wertänderungen", "Veränderung Nettovermögen"):
                    self.assertIn(w, tip)
                f0 = lambda v: pg.evaluate("v => F0(v)", v)
                self.assertIn(f0(nwk[2]), tip.split("Umschichtungen")[1][:24]); self.assertIn(f0(nwk[0] - nwk[1] - nwk[2]), tip.split("Bankguthaben")[-1][:24])          # below: the short word, as in the legend
                self.assertIn(f0(nwk[0]), tip.split("Veränderung Nettovermögen")[1][:24]); self.assertIn("+", tip)              # movements with a sign
                pg.mouse.move(5, 5)
                self.assertGreaterEqual(len(pg.query_selector_all("#cf-tip i.sw")), 5)
                # a few months far larger than the rest: the scale follows the rest, those bars are cut, marked and labelled
                cut = pg.evaluate("""(() => { const D = JSON.parse(JSON.stringify(B())), ms = D.months.filter(m => m < D.actual_until).slice(-12), id = S.area, keep = S.DATA.areas[id];
                    D.cashflow.sums[ms[3]].investing = -400000; D.cashflow.sums[ms[3]].financing = 400000; S.DATA.areas[id] = D;
                    try { cfDrawMonths(); return [document.querySelectorAll('#cf-months .cf-break:not(.nw)').length, document.querySelector('#cf-months .cf-val-l:not(.nw)').textContent]; } finally { S.DATA.areas[id] = keep; cfDrawMonths(); } })()""")
                self.assertEqual(cut[0], 2); self.assertTrue(cut[1].startswith("+40"), cut[1])                  # 406.500: income and the loan
                # the charts end at the last closed month: the running month is half booked (the table shows it hatched)
                done, running = pg.evaluate("(() => { const D = B(); return [MLL(D.months.filter(m => m < D.actual_until).slice(-1)[0]), ML(D.actual_until)]; })()")
                self.assertTrue(tip.startswith(done), tip); self.assertNotIn(running, pg.inner_text(".cf-period"))
                # 3. money flow: sources on the left, uses on the right, through one column; both sides the same sum, each band its amount
                fl = pg.evaluate("(() => { const F = CF.flow; return [F.src.reduce((a, e) => a + e.v, 0), F.use.reduce((a, e) => a + e.v, 0), F.src.map(e => e.label), F.use.map(e => e.label)]; })()")
                self.assertLess(abs(fl[0] - fl[1]), 1); self.assertIn("Arbeitseinkommen", fl[2]); self.assertIn("Mehr Bankguthaben", fl[3])
                self.assertEqual(len(pg.query_selector_all("#cf-flow .cf-fl-g")), len(fl[2]) + len(fl[3]))
                self.assertIsNone(pg.query_selector("#cf-flow .cf-fl-m")); self.assertTrue(pg.query_selector("#cf-flow linearGradient"))      # no grey bar: the colours run into one another
                self.assertIn("Arbeitseinkommen", pg.text_content("#cf-flow")); self.assertIsNone(pg.query_selector(".cf-su-col"))
                self.assertIn("%", pg.text_content("#cf-flow .cf-fl-p")); self.assertTrue(pg.query_selector("#cf-flow .cf-fl-g[data-cftip]"))       # shares inside, the rest on hover
                # a click opens a position into its categories (heights within it), the name above closes it again
                # (the made-up data has no position with several categories in the period: the largest use gets two invented parts)
                pg.evaluate("(() => { if (document.querySelector('#cf-flow .cf-fl-g[data-fl]')) return; const e = CF.flow.use[0]; e.kids = [{label: 'Teil A', v: e.v * 0.6}, {label: 'Teil B', v: e.v * 0.4}]; cfDrawFlow(); })()")
                key = pg.evaluate("(() => { const g = document.querySelector('#cf-flow .cf-fl-g[data-fl]'); return g ? g.dataset.fl : null; })()")
                self.assertTrue(key)
                # fading: only with a band under the pointer (not anywhere in the card), that band above a veil; away again: as before
                order = lambda: pg.eval_on_selector_all("#cf-flow .cf-fl-g", "e => e.map(g => g.getAttribute('aria-label'))")
                o0 = order(); bb = pg.query_selector("#cf-flow svg").bounding_box()
                pg.mouse.move(bb["x"] + 3, bb["y"] + 3); pg.wait_for_timeout(100); self.assertIsNone(pg.query_selector("#cf-flow .cf-fl-veil"))
                pg.hover("#cf-flow .cf-fl-g >> nth=1"); pg.wait_for_timeout(100)
                self.assertTrue(pg.evaluate("(() => { const v = document.querySelector('#cf-flow .cf-fl-veil'); return !!v && v.nextElementSibling.classList.contains('cf-fl-g'); })()"))
                pg.mouse.move(5, 5); pg.wait_for_timeout(100)
                self.assertIsNone(pg.query_selector("#cf-flow .cf-fl-veil")); self.assertEqual(order(), o0)
                if key:
                    n0 = len(pg.query_selector_all("#cf-flow .cf-fl-g"))
                    pg.dispatch_event("#cf-flow .cf-fl-g[data-fl='%s']" % key, "click"); pg.wait_for_timeout(150)
                    self.assertGreater(len(pg.query_selector_all("#cf-flow .cf-fl-g")), n0); self.assertTrue(pg.query_selector("#cf-flow .cf-fl-up"))
                    pg.dispatch_event("#cf-flow .cf-fl-up", "click"); pg.wait_for_timeout(150)
                    self.assertEqual(len(pg.query_selector_all("#cf-flow .cf-fl-g")), n0)
                    # a click beside the bands opens everything (every level), a second one closes it all again; the total is no button
                    self.assertIsNone(pg.query_selector("#cf-flow [data-flall], #cf-flow .cf-fl-mid[role]"))
                    pg.dispatch_event("#cf-flow .cf-fl-mid:not(.cf-fl-span)", "click"); pg.wait_for_timeout(150)
                    self.assertIsNone(pg.query_selector("#cf-flow .cf-fl-g[aria-expanded='false']")); self.assertGreater(len(pg.query_selector_all("#cf-flow .cf-fl-g")), n0)
                    pg.dispatch_event("#cf-flow .cf-fl-mid:not(.cf-fl-span)", "click"); pg.wait_for_timeout(150)
                    self.assertEqual(len(pg.query_selector_all("#cf-flow .cf-fl-g")), n0)
                    self.assertTrue(pg.evaluate("/Jahr|Monat/.test(document.querySelector('#cf-flow .cf-fl-span').textContent)"))      # the period and its length small above the total
                    # the same with a click beside the chart (the period, the empty card); one item open: the click closes all first
                    pg.dispatch_event("#cf-flow .cf-fl-span", "click"); pg.wait_for_timeout(150); self.assertGreater(len(pg.query_selector_all("#cf-flow .cf-fl-g")), n0)
                    pg.dispatch_event(".cf-card[data-cfid='flow']", "click"); pg.wait_for_timeout(150); self.assertEqual(len(pg.query_selector_all("#cf-flow .cf-fl-g")), n0)
                    pg.dispatch_event("#cf-flow .cf-fl-g[data-fl='%s']" % key, "click"); pg.wait_for_timeout(150)
                    pg.dispatch_event("#cf-flow svg", "click"); pg.wait_for_timeout(150); self.assertEqual(len(pg.query_selector_all("#cf-flow .cf-fl-g")), n0)
                    # hover on a name or band: exact amount, share and the period before -- beside the chart, always in view
                    pg.dispatch_event("#cf-flow .cf-fl-l >> nth=0", "pointerover"); pg.wait_for_timeout(100)
                    tip = pg.inner_text("#cf-tip"); self.assertIn("Betrag", tip); self.assertIn("Anteil", tip); self.assertIn("€", tip)
                    self.assertTrue(pg.evaluate("""(() => { const a = document.querySelector('#cf-tip').getBoundingClientRect(), b = document.querySelector('#cf-flow svg').getBoundingClientRect();
                        return a.top >= 0 && a.bottom <= innerHeight && (innerWidth < 700 || a.right <= b.left + b.width / 2 + 1 || a.left >= b.left + b.width / 2 - 1); })()"""))      # in view, at most over the other half
                    pg.dispatch_event("#cf-flow .cf-fl-l >> nth=0", "pointerout"); pg.wait_for_timeout(50)
                    # opening an item never narrows the bands: the names keep their share of the width
                    pg.dispatch_event("#cf-flow .cf-fl-g[data-fl='%s']" % key, "click"); pg.wait_for_timeout(150)
                    xs = pg.evaluate("[...document.querySelectorAll('#cf-flow .cf-fl-n')].map(r => +r.getAttribute('x'))")
                    pg.dispatch_event("#cf-flow .cf-fl-up", "click"); pg.wait_for_timeout(150)
                    self.assertEqual(sorted(set(xs)), sorted(set(pg.evaluate("[...document.querySelectorAll('#cf-flow .cf-fl-n')].map(r => +r.getAttribute('x'))"))))
                    # a part that opens no further closes its group again: on its band or its name
                    pg.dispatch_event("#cf-flow .cf-fl-g[data-fl='%s']" % key, "click"); pg.wait_for_timeout(150)
                    pg.dispatch_event("#cf-flow .cf-fl-g.back >> nth=0", "click"); pg.wait_for_timeout(150)
                    self.assertEqual(len(pg.query_selector_all("#cf-flow .cf-fl-g")), n0)
                    pg.dispatch_event("#cf-flow .cf-fl-g[data-fl='%s']" % key, "click"); pg.wait_for_timeout(150)
                    pg.dispatch_event("#cf-flow .cf-fl-l.back >> nth=0", "click"); pg.wait_for_timeout(150)
                    self.assertEqual(len(pg.query_selector_all("#cf-flow .cf-fl-g")), n0)
                # small flows (under 3 %) together as "the others", every amount kept
                grp = pg.evaluate("""(() => { const D = JSON.parse(JSON.stringify(B())), ms = cfDone(D).slice(-12), sek = D.cashflow.sections.find(s => s.name === 'expenses');
                    sek.rows.push({...sek.rows[0], row: 'Klein A', lbl: null, amounts: {[ms[0]]: -10}, details: []}, {...sek.rows[0], row: 'Klein B', lbl: null, amounts: {[ms[1]]: -20}, details: []});
                    const keep = CF.flow; cfSourcesUses(D, ms); const F = CF.flow; CF.flow = keep;
                    const o = F.use.find(e => e.kids && e.kids.some(k => k.label === 'Klein A')); return [!!o, o ? o.kids.map(k => k.label) : [], o ? Math.round(o.v - o.kids.reduce((a, k) => a + k.v, 0)) : null]; })()""")
                self.assertTrue(grp[0]); self.assertIn("Klein B", grp[1]); self.assertEqual(grp[2], 0)          # the others add up
                # 4. expenses by position as a ring: their sum in the middle
                self.assertEqual(num(pg.text_content("#cf-pie .cf-pie-v")), -want["aus"])
                self.assertIsNone(pg.query_selector(".cf-list.ex"))                          # the bars by position went (the ring covers them)
                # further charts to choose from: rolling twelve months, savings rate, expenses by month, cash runway, the year so far
                self.assertTrue(pg.query_selector("#cf-heat .cf-heat-c"))
                for gone in ("#cf-rate", "#cf-reach", "#cf-roll", "#cf-yoy"):                   # removed as not useful (rolling: in the months chart)
                    self.assertIsNone(pg.query_selector(gone), gone)
                # the heatmap beside the ring, one scale for all: the largest position darker than a smaller one
                # ... in one card with the ring (one switch for both, in the ring's head); the two bridges side by side, then the two flows
                self.assertTrue(pg.query_selector(".cf-duo #cf-pie-card #cf-pie-art")); self.assertTrue(pg.query_selector(".cf-duo #cf-pie-card + #cf-heat-card"))
                # the line between ring and heat map exactly in the middle of the card (where the gap between two half cards is)
                mid = pg.evaluate("(() => { const c = document.querySelector('.cf-duo').getBoundingClientRect(), h = document.querySelector('#cf-heat-card').getBoundingClientRect(); return [h.left - c.left, c.width / 2]; })()")
                self.assertLess(abs(mid[0] - mid[1]), 1.5)
                # the order: ↑ ↓ at each chart (shown on hover), kept in the browser; a half chart without a half neighbour takes the whole width
                self.assertEqual(pg.eval_on_selector_all(".cf-grid > .cf-card", "e => e.map(c => c.dataset.cfid)"), ["bridge", "months", "wealth", "flow", "duo"])
                self.assertIsNone(pg.query_selector("#cf-order-reset"))                                  # the default: nothing to reset
                pg.click(".cf-card[data-cfid='months'] .th-mv[data-d='1']", force=True); pg.wait_for_timeout(400)
                self.assertEqual(pg.eval_on_selector_all(".cf-grid > .cf-card", "e => e.map(c => c.dataset.cfid)"), ["bridge", "wealth", "months", "flow", "duo"])
                pg.click(".cf-card[data-cfid='duo'] .th-mv[data-d='-1']", force=True); pg.wait_for_timeout(400)
                pg.click(".cf-card[data-cfid='duo'] .th-mv[data-d='-1']", force=True); pg.wait_for_timeout(400)
                self.assertEqual(pg.eval_on_selector_all(".cf-grid > .cf-card", "e => e.map(c => [c.dataset.cfid, c.classList.contains('cf-full')])"),
                                 [["bridge", False], ["wealth", False], ["duo", True], ["months", False], ["flow", False]])
                self.assertTrue(pg.query_selector(".view-btns #cf-order-reset"))                          # styled as on the balance sheet
                pg.click("#cf-order-reset"); pg.wait_for_timeout(400)                                     # "Ansicht zurücksetzen": the default again
                self.assertEqual(pg.eval_on_selector_all(".cf-grid > .cf-card", "e => e.map(c => c.dataset.cfid)"), ["bridge", "months", "wealth", "flow", "duo"])
                self.assertIsNone(pg.query_selector("#cf-order-reset"))
                self.assertEqual(pg.evaluate("[getComputedStyle(document.querySelector('.cf-duo')).gridColumnEnd, getComputedStyle(document.querySelector('#cf-flow').closest('.cf-card')).gridColumnStart, getComputedStyle(document.querySelector('#cf-wbridge').closest('.cf-card')).gridColumnStart]"), ["-1", "span 3", "span 3"])
                ks = pg.evaluate("[...document.querySelectorAll('#cf-heat .cf-heat-c:not(.none)')].map(c => parseInt(c.style.getPropertyValue('--k')))")
                self.assertGreater(max(ks), min(ks) + 20)
                # the expenses as a ring: positions in shades of red, the total in the middle, each with amount and change beside it
                self.assertGreaterEqual(len(pg.query_selector_all(".cf-pie-sl")), 2); self.assertIn("€", pg.text_content("#cf-pie .cf-pie-v"))
                self.assertEqual(len(pg.query_selector_all(".cf-pie-lab")), len(pg.query_selector_all(".cf-pie-sl")))       # each named beside its slice
                self.assertIsNone(pg.query_selector(".cf-pie-prev")); self.assertTrue(pg.inner_text("#cf-pie-card .lc-title").startswith("Vorjahresvergleich der Ausgaben"))
                pg.hover("#cf-pie .cf-pie-c"); pg.wait_for_timeout(150)                 # the middle names both periods
                self.assertEqual(pg.inner_text("#cf-tip").count("–"), 2); pg.mouse.move(5, 5)
                # a click keeps a slice open: its categories named around it, the position in the middle; a click there goes back
                first = pg.evaluate("CF.pie.items[0].label")
                self.assertTrue(pg.evaluate("(() => { const g = document.querySelector('#cf-pie .cf-pie-lab'), r = g.getBoundingClientRect(); return g.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)); })()"))   # also between its two lines
                pg.click("#cf-pie .cf-pie-lab[data-pie='0']"); pg.wait_for_selector("#cf-pie .cf-pie-sl.on")             # its name, like the slice
                self.assertEqual(pg.text_content("#cf-pie .cf-pie-cn"), first); self.assertTrue(pg.query_selector("#cf-pie .cf-pie-sl.off"))
                self.assertIn("›", pg.text_content("#cf-pie .cf-pie-lab"))                   # a category, not a position
                pg.click("#cf-pie .cf-pie-c"); pg.wait_for_timeout(150)
                self.assertIsNone(pg.query_selector("#cf-pie .cf-pie-sl.on"))
                pg.dispatch_event("#cf-pie .cf-pie-sl >> nth=1", "click"); pg.wait_for_selector("#cf-pie .cf-pie-sl.on")
                pg.keyboard.press("Escape"); pg.wait_for_timeout(150)
                self.assertIsNone(pg.query_selector("#cf-pie .cf-pie-sl.on")); self.assertEqual(len(pg.query_selector_all(".cf-pie-lab")), len(pg.query_selector_all(".cf-pie-sl")))
                # "Übrige" compare only where each of them had a period before; ±0 % only for the same amount
                self.assertEqual(pg.evaluate("[cfRestP([{p: 10}, {p: null}], true), cfRestP([{p: 10}, {p: 5}], true), cfRestP([{p: 10}], false)]"), [None, 15, None])
                self.assertEqual(pg.evaluate("[cfChange(1000, 1000, false).txt, cfChange(1002, 1000, false).txt, cfChange(1000000.6, 1000000, false).txt, cfChange(100050, 100000, false).txt, cfChange(10532, 100, false).txt, cfChange(1334, 100, false).txt]"),
                                 ["±0 %", "+0,2 %", "+<0,01 %", "+0,05 %", "+10T %", "+1,2T %"])                                  # never rounded up
                self.assertEqual(pg.evaluate("[cfChgShort(cfChange(1334, 100, false)), cfChgShort(cfChange(350, 100, true)), cfChgShort(cfChange(-2500, 100, true)), cfChgShort(cfChange(100, 100, true))]"),
                                 ["+1T%", "+250%", "−3T%", "±0%"])                                                               # the bridges' narrow column: from 1000 % only thousands, the sign of percent always
                # signed amounts (the bridges): a change of size (expenses up: worse), across zero of the amount; colour only where asked
                self.assertEqual(pg.evaluate("[cfChangeAmt(-1200, -1000, true), cfChangeAmt(900, 1000, true), cfChangeAmt(300, -500, true), cfChangeAmt(-1200, -1000, false)].map(c => [c.txt, c.cls])"),
                                 [["+20 %", "neg"], ["−10 %", "neg"], ["+160 %", "pos"], ["+20 %", ""]])
                self.assertEqual(pg.evaluate("[pctCell(45.4), pctCell(250), pctCell(1499), pctCell(12000), pctCell(-100), pctCell(0)]"), ["+45%", "+250%", "+1,5T%", "+12T%", "−100%", "±0%"])
                pg.hover("#cf-heat .cf-heat-c >> nth=0"); pg.wait_for_timeout(150); self.assertIn("€", pg.inner_text("#cf-tip")); self.assertNotIn("Ø", pg.inner_text("#cf-tip")); pg.mouse.move(5, 5)
                self.assertEqual(len(pg.query_selector_all("#cf-heat .cf-heat-v")), len(pg.query_selector_all("#cf-heat .cf-heat-n")))     # the average per row
                # all positions together: a row of its own below a line, on its own scale
                self.assertTrue(pg.query_selector("#cf-heat .cf-heat-sep + .cf-heat-n.tot")); self.assertEqual(pg.inner_text("#cf-heat .cf-heat-n.tot"), "Ausgaben gesamt")
                for sel, pre in (("#cf-heat .cf-heat-n.tot", "Ausgaben gesamt · "), ("#cf-heat .cf-heat-n.tot ~ .cf-heat-c[data-hr] >> nth=-1", "Ausgaben gesamt · "), ("#cf-heat .cf-heat-n.open >> nth=0", "")):
                    pg.click(sel); pg.wait_for_selector("#drawer.open #cftx-page"); self.assertTrue(pg.inner_text("#drawer h2").startswith(pre))
                    self.assertTrue(pg.query_selector_all("#drawer tbody tr"))
                    self.assertLessEqual(*pg.evaluate("(() => { const w = document.querySelector('#drawer .dr-wrap'); return [w.scrollWidth, w.clientWidth]; })()"))   # no sideways scrolling
                    pg.wait_for_timeout(450)                                                     # a wide window: the panel always beside the page
                    self.assertTrue(pg.evaluate("document.body.classList.contains('dock') && getComputedStyle(document.querySelector('main')).marginRight === '400px'"))
                    self.assertTrue(pg.evaluate("(() => { const s = document.querySelector('.dr-src'); if (!s) return true; return s.getBoundingClientRect().right <= innerWidth - 400 + 2; })()"))   # what you clicked: in view
                    pg.keyboard.press("Escape"); pg.wait_for_timeout(100)
                pg.wait_for_function("!document.body.classList.contains('dock')"); pg.wait_for_timeout(600)      # the page takes its width back (charts drawn anew)
                # a window too narrow for both: the panel lies over the page
                pg.set_viewport_size({"width": 1200, "height": 900}); pg.wait_for_timeout(300)
                pg.click("#cf-heat .cf-heat-n.tot"); pg.wait_for_selector("#drawer.open #cftx-page"); pg.wait_for_timeout(300)
                self.assertEqual(pg.evaluate("getComputedStyle(document.querySelector('main')).marginRight"), "0px")
                pg.keyboard.press("Escape"); pg.set_viewport_size({"width": 1440, "height": 900}); pg.wait_for_timeout(600)
                # a few huge cells (20.000 and 100.000 among values up to 2.000): they get the darkest tones and a mark, the others keep their range
                hk = pg.evaluate("""(() => { const D = JSON.parse(JSON.stringify(B())), id = S.area, keep = S.DATA.areas[id], ms = D.months.filter(m => m < D.actual_until).slice(-12);
                    const sek = D.cashflow.sections.find(s => s.name === 'expenses');
                    sek.rows.forEach((z, i) => ms.forEach((m, j) => { z.amounts[m] = -((i * 397 + j * 131) % 2000 + 1); }));
                    sek.rows[0].amounts[ms[3]] = -20000; sek.rows[1 % sek.rows.length].amounts[ms[7]] = -100000; S.DATA.areas[id] = D;
                    try { cfDrawHeat(); const ks = [...document.querySelectorAll('#cf-heat .cf-heat-n:not(.tot) ~ .cf-heat-c')].slice(0, 12 * (sek.rows.length)).map(c => [parseInt(c.style.getPropertyValue('--k')) || 0, c.classList.contains('big')]);
                      return ks; } finally { S.DATA.areas[id] = keep; cfDrawHeat(); } })()""")
                normal = [k for k, big in hk if not big]; bigs = [k for k, big in hk if big]
                self.assertEqual(len(bigs), 2); self.assertGreaterEqual(min(bigs), 86)
                self.assertLess(min(normal), 20); self.assertGreater(max(normal), 70)               # small and large regular values stay apart
                # switched to income: green, the income in the middle, the title says so; and back
                y0 = pg.evaluate("(() => { const b = document.querySelector(\"#cf-pie-art button[data-a='ein']\"); b.scrollIntoView({block: 'center'}); return b.getBoundingClientRect().top; })()")
                pg.click("#cf-pie-art button[data-a='ein']"); pg.wait_for_selector("#cf-pie svg.ein"); pg.wait_for_selector("#cf-heat .cf-heat.ein")
                self.assertAlmostEqual(pg.evaluate("document.querySelector(\"#cf-pie-art button[data-a='ein']\").getBoundingClientRect().top"), y0, delta=2)     # the switch stays where it was
                self.assertEqual(pg.inner_text("#cf-heat-card .lc-title").strip().split("\n")[0], "Einnahmen je Monat")
                self.assertTrue(pg.inner_text("#cf-pie-card .lc-title").startswith("Vorjahresvergleich der Einnahmen"))
                self.assertEqual(num(pg.text_content("#cf-pie .cf-pie-v")), want["ein"])
                pg.click("#cf-pie-art button[data-a='aus']"); pg.wait_for_selector("#cf-pie svg:not(.ein)")
                # the slice's tooltip: amount, share, the period before, change
                pg.hover("#cf-pie .cf-pie-lab[data-pie='0']"); pg.wait_for_timeout(150)
                tip = pg.inner_text("#cf-tip")
                for w in ("Betrag", "Anteil", "Vorperiode", "Veränderung"):
                    self.assertIn(w, tip)
                pg.mouse.move(5, 5)
                # a position with several categories: an outer ring of them, named when kept open, the tooltip with colour and change
                html = pg.evaluate("""(() => { const D = JSON.parse(JSON.stringify(B())), ms = D.months.filter(m => m < D.actual_until);
                    const z = D.cashflow.sections.find(s => s.name === 'expenses').rows[0], w = Object.fromEntries(ms.map(m => [m, -100]));
                    z.amounts = Object.fromEntries(ms.map(m => [m, -300])); z.details = [{category: 'Wohnen / Miete', amounts: Object.fromEntries(ms.map(m => [m, -200]))}, {category: 'Wohnen / Strom <b>', amounts: w}];
                    CF.tips = []; cfPie(D, ms.slice(-12), ms.slice(-24, -12)); CF.pieSel = CF.pie.items.find(e => e.parts.length > 1).label; cfDrawPie();
                    const out = [document.querySelector('#cf-pie').innerHTML, CF.tips.join('')];
                    CF.pieSel = null; const B0 = B(), [c, p] = cfMonths(B0, S.cfZeit); document.querySelector('#cf-pie-card').outerHTML = cfPie(B0, c, p); cfDrawPie(); return out; })()""")
                self.assertIn('cf-pie-sub cat1', html[0]); self.assertIn('cf-pie-sub cat2', html[0]); self.assertIn('cf-pie-k cat2', html[0])
                self.assertIn("Strom &lt;b&gt;", html[0]); self.assertNotIn("<b>", html[0])
                self.assertIn("Wohnen › Strom &lt;b&gt;", html[1]); self.assertNotIn("<b>", html[1].replace("<b>2.400", "").replace("<b>1.200", "").split("Strom")[1][:20])
                # the balance sheet shows more than the payments (left out on purpose, money in transit): a step of its own, the bridge ends there
                st = pg.evaluate("""(() => { const D = JSON.parse(JSON.stringify(B())), ms = D.months.filter(m => m < D.actual_until).slice(-12);
                    D.cashflow.sums[ms[11]].bank += 1000; const s = cfBridgeSteps(D, ms, []);
                    return s.map(x => [x.label, Math.round(x.v), Math.round(x.b), !!x.total]); })()""")
                self.assertEqual(st[-2][:2], ["Abgleich mit der Bilanz", 1000]); self.assertEqual(st[-2][2], st[-1][1])
                # an account that did not exist yet (no balance in the balance sheet) had nothing: the bank balance is known all the same
                st2 = pg.evaluate("""(() => { const D = JSON.parse(JSON.stringify(B())), ms = D.months.filter(m => m < D.actual_until).slice(-12), prev = D.months[D.months.indexOf(ms[0]) - 1];
                    D.balance.rows.find(r => !r.group && r.role === 'cash').amounts[prev] = null; return cfBridgeSteps(D, ms, []).map(x => x.label); })()""")
                self.assertEqual((st2[0], st2[-1]), ("Bankguthaben am Anfang", "Bankguthaben am Ende"))
                fig = lambda: pg.text_content("#cf-pie .cf-pie-v")
                before = fig()
                self.assertIsNone(pg.query_selector("#cf-zeit button[data-z='all']"))          # always a period, never everything
                # the months come from a small calendar (not a long list): the year with ‹ ›, months without figures greyed
                pickm = lambda btn, m: (pg.click(btn), pg.wait_for_selector("#cf-mpick"), pg.evaluate("y => { for (let i = 0; i < 9; i++) { const p = document.querySelector('#cf-mpick'); const c = +p.querySelector('.cf-mp-h b').textContent; if (c === y) break; p.querySelectorAll('[data-py]')[c > y ? 0 : 1].click(); } }", int(m[:4])),
                                        pg.click("#cf-mpick [data-pm='%s']" % m), pg.wait_for_timeout(300))
                first = pg.evaluate("cfPick(B())[0]")
                pickm("#cf-von", first)                                                              # a range of one's own
                self.assertIsNone(pg.query_selector("#cf-mpick"))
                self.assertEqual(pg.evaluate("[S.cfZeit, document.querySelector('#cf-von').dataset.m]"), ["custom", first])
                self.assertNotEqual(fig(), before); self.assertGreater(len(pg.query_selector_all("#cf-months .cf-hit")), 12)
                self.assertEqual(len(pg.query_selector_all("#cf-heat .cf-heat-v")), len(pg.query_selector_all("#cf-heat .cf-heat-n")))
                hm = pg.evaluate("""(() => { const ms = cfMonths(B(), S.cfZeit)[0], n = ms.length <= 24 ? ms.length : new Set(ms.map(m => m.slice(0, 4) + Math.ceil(+m.slice(5) / 3))).size;
                    return [n, document.querySelector('#cf-heat .cf-heat').style.gridTemplateColumns]; })()""")      # the heatmap covers the whole period
                self.assertIn("repeat(%d," % hm[0], hm[1])
                pg.evaluate("document.querySelector('#main .wrap').scrollLeft = 0")
                pg.click("#cf-zeit button[data-z='12m']"); pg.wait_for_timeout(900)
                self.assertEqual(pg.evaluate("S.cfZeit"), "12m")
                vis = pg.evaluate("""(() => { const w = document.querySelector('#main .wrap'), th = w.querySelector('thead th.cf-endsel'), a = w.getBoundingClientRect(), r = th.getBoundingClientRect();
                    return r.left >= a.left + w.querySelector('thead th').offsetWidth - 2 && r.right <= a.right + 2; })()""")
                self.assertTrue(vis)                                                                       # a preset: the table scrolls to its last month
                y = pg.evaluate("cfDone(B()).slice(-1)[0].slice(0, 4)")
                pickm("#cf-von", y + "-01")                                                         # a whole year (so far) lights up its button
                self.assertEqual(pg.evaluate("S.cfZeit"), y); self.assertTrue(pg.query_selector("#cf-zeit button.on[data-z='%s']" % y))
                pg.click("#cf-zeit button[data-z='12m']"); pg.wait_for_timeout(200)
                # the arrows beside the period move it by a month, its length stays; at the newest month the right one rests
                ms = pg.evaluate("cfDone(B())")
                self.assertFalse(pg.is_disabled(".cf-shift[data-shift='1']"))                      # on into the running month and the plan
                pg.click(".cf-shift[data-shift='-1']"); pg.wait_for_timeout(300); pg.click(".cf-shift[data-shift='-1']"); pg.wait_for_timeout(300)
                self.assertEqual(pg.evaluate("[S.cfZeit, document.querySelector('#cf-von').dataset.m, document.querySelector('#cf-bis').dataset.m]"), ["custom", ms[-14], ms[-3]])
                self.assertEqual(pg.evaluate("document.querySelectorAll('#cf-months .cf-hit').length"), 12)
                pg.click(".cf-shift[data-shift='1']"); pg.wait_for_timeout(300); pg.click(".cf-shift[data-shift='1']"); pg.wait_for_timeout(300)
                self.assertEqual(pg.evaluate("S.cfZeit"), "12m")
                # beyond the last closed month: the running month and the plan, hatched in the charts per month
                pg.click(".cf-shift[data-shift='1']"); pg.wait_for_timeout(300); pg.click(".cf-shift[data-shift='1']"); pg.wait_for_timeout(300)
                self.assertEqual(pg.evaluate("document.querySelector('#cf-bis').dataset.m"), pg.evaluate("cfPick(B()).filter(m => m >= B().actual_until)[1]"))
                self.assertTrue(pg.query_selector("#cf-bis.open")); self.assertEqual(len(pg.query_selector_all("#cf-months .cf-ahead")), 2)
                self.assertGreaterEqual(len(pg.query_selector_all("#cf-heat .cf-heat-c.ahead")), 2)
                self.assertTrue(pg.query_selector("#cf-bridge .cf-br-hatch")); self.assertTrue(pg.query_selector("#cf-wbridge .cf-br-hatch"))      # the bridges hatched too
                wt2 = pg.evaluate("(() => { const [c] = cfMonths(B(), S.cfZeit), r = cfWealthTree(B(), c, []); return r.map(x => x.id); })()")
                self.assertNotIn("off", wt2); self.assertEqual((wt2[0], wt2[-1]), ("nw0", "nw1"))          # into the plan: it still adds up
                pg.click("#cf-zeit button[data-z='12m']"); pg.wait_for_timeout(300)
                self.assertEqual(pg.eval_on_selector_all("#cf-zeit button", "e => e.length"), 1 + len({m[:4] for m in ms[-36:]} & {str(int(ms[-1][:4]) - k) for k in range(3)}))
                # two fingers sideways on the monthly chart: the period moves a month (back and forward again)
                pg.hover("#cf-months"); pg.mouse.wheel(-120, 0); pg.wait_for_timeout(500)
                self.assertEqual(pg.evaluate("document.querySelector('#cf-bis').dataset.m"), ms[-2]); pg.wait_for_timeout(200)
                pg.hover("#cf-months"); pg.mouse.wheel(120, 0); pg.wait_for_timeout(500)
                self.assertEqual(pg.evaluate("S.cfZeit"), "12m")
                # ... over the axis also with a mouse wheel (up and down), and by dragging it
                pg.hover("#cf-months .cf-xaxis"); pg.mouse.wheel(0, -120); pg.wait_for_timeout(500)
                self.assertEqual(pg.evaluate("document.querySelector('#cf-bis').dataset.m"), ms[-2]); pg.wait_for_timeout(200)
                bb = pg.query_selector("#cf-months .cf-xaxis").bounding_box(); slot = float(pg.get_attribute("#cf-months .cf-xaxis", "data-slot"))
                pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + 8); pg.mouse.down()
                pg.mouse.move(bb["x"] + bb["width"] / 2 - slot * 1.3, bb["y"] + 8, steps=4); pg.wait_for_timeout(400); pg.mouse.up()
                self.assertEqual(pg.evaluate("S.cfZeit"), "12m")                                         # pulled to the left: a month later again
                # a scale: dragged up it zooms in (marked; bars beyond it cut and labelled), a click sets it back
                ya = pg.query_selector("#cf-months .cf-yax[data-p='up']").bounding_box(); n_br = len(pg.query_selector_all("#cf-months .cf-break"))
                pg.mouse.move(ya["x"] + ya["width"] / 2, ya["y"] + ya["height"] / 2); pg.mouse.down()
                pg.mouse.move(ya["x"] + ya["width"] / 2, ya["y"] + ya["height"] / 2 - 120, steps=6); pg.mouse.up(); pg.wait_for_timeout(200)
                self.assertLess(pg.evaluate("S.cfMoZ.up"), 0.5); self.assertTrue(pg.query_selector("#cf-months .cf-yax.on[data-p='up']"))
                self.assertGreater(len(pg.query_selector_all("#cf-months .cf-break")), n_br)
                pg.click("#cf-months .cf-yax[data-p='up']"); pg.wait_for_timeout(200)
                self.assertIsNone(pg.evaluate("(S.cfMoZ || {}).up ?? null")); self.assertIsNone(pg.query_selector("#cf-months .cf-yax.on"))
                # a month's heading in the table: the charts end there (12 months up to it)
                pg.click("#main table.cf-tbl:not(.cf-names) thead th[data-key='%s']" % ms[-4]); pg.wait_for_timeout(400)
                self.assertEqual(pg.evaluate("[document.querySelector('#cf-von').dataset.m, document.querySelector('#cf-bis').dataset.m]"), [ms[-15], ms[-4]])
                self.assertTrue(pg.query_selector("#main table.cf-tbl:not(.cf-names) thead th.cf-endsel[data-key='%s']" % ms[-4]))
                pg.click("#cf-zeit button[data-z='12m']"); pg.wait_for_timeout(300)
                pg.click("#cf-months .cf-hit >> nth=5"); pg.wait_for_timeout(200)
                self.assertEqual(pg.evaluate("S.cfZeit"), "12m")                                       # a month in the chart: no jump
                pg.click("#cf-bridge .cf-br-row >> nth=1"); pg.mouse.move(5, 5); pg.wait_for_timeout(100)
                self.assertEqual(pg.evaluate("getComputedStyle(document.querySelectorAll('#cf-bridge .cf-br-bg')[1]).fill"), "rgba(0, 0, 0, 0)")
                pg.click("#cf-zeit button[data-z='12m']"); pg.wait_for_timeout(200)
                # a cell of the heat map: its transactions, the filter named above them and cleared with one click
                cell = pg.evaluate("""(() => { const c = document.querySelector('#cf-heat .cf-heat-c[data-hr]'), r = CF.heat.rows[+c.dataset.hr]; c.scrollIntoView(); return [r.label, [...r.paths], c.dataset.hm]; })()""")
                pg.click("#cf-heat .cf-heat-c[data-hr='%s'][data-hm='%s']" % (pg.evaluate("document.querySelector('#cf-heat .cf-heat-c[data-hr]').dataset.hr"), cell[2]))
                pg.wait_for_selector("#drawer.open #cftx-page")
                self.assertTrue(pg.query_selector_all("#drawer tbody tr"))
                pg.click("#cftx-page"); pg.wait_for_selector("#uf-von")                                                   # the filter is there to change: dates and categories
                self.assertEqual(pg.input_value("#uf-von"), cell[2] + "-01"); self.assertTrue(pg.input_value("#uf-bis").startswith(cell[2] + "-"))
                self.assertEqual(len(pg.query_selector_all(".uf-ext .chip")), len(cell[1]))
                rows = pg.evaluate("UMS.transactions.map(u => [u.date, u.category])")
                self.assertTrue(rows)
                norm = lambda c: " / ".join(x.strip() for x in re.split(r"\\| / | › ", c or "") if x.strip())
                for dat, kat in rows:
                    self.assertTrue(dat.startswith(cell[2]), dat)
                    self.assertTrue(any(norm(kat) == norm(c) or norm(kat).startswith(norm(c) + " / ") for c in cell[1]), kat)
                pg.fill("#uf-von", cell[2][:4] + "-01-01"); pg.dispatch_event("#uf-von", "change"); pg.wait_for_timeout(400)      # by hand: a longer period
                self.assertGreaterEqual(pg.evaluate("UMS.hits"), len(rows))
                if len(cell[1]) > 1:
                    pg.click(".uf-ext .chip [data-kat-x]"); pg.wait_for_timeout(400)             # a category taken off
                    self.assertEqual(len(pg.query_selector_all(".uf-ext .chip")), len(cell[1]) - 1)
                n_all = pg.evaluate("UMS.total"); pg.click("#uf-chip-x"); pg.wait_for_timeout(400)
                self.assertIsNone(pg.query_selector(".uf-ext .chip")); self.assertGreater(pg.evaluate("UMS.hits"), len(rows)); self.assertEqual(pg.evaluate("UMS.total"), n_all)
                # the total row of the heat map: all categories of the expenses as one chip, with those without a category, outgoing only
                pg.click("#nav a[href='#cashflow']"); pg.wait_for_selector("#cf-heat .cf-heat-n.tot")
                pg.click("#cf-heat .cf-heat-sep ~ .cf-heat-c[data-hr] >> nth=11"); pg.wait_for_selector("#drawer.open #cftx-page")
                self.assertTrue(all(v.startswith("-") for v in pg.eval_on_selector_all("#drawer tbody td.num", "e => e.map(x => x.textContent.trim())")))     # outgoing only
                pg.click("#cftx-page"); pg.wait_for_selector("#uf-von")
                self.assertEqual(len(pg.query_selector_all(".uf-ext .chip")), 1); self.assertIn("Ausgaben gesamt", pg.inner_text(".uf-ext .chip"))
                self.assertTrue(all(a < 0 for a in pg.evaluate("UMS.transactions.map(u => u.amount)")))
                pg.click("[data-kat-all]"); pg.wait_for_timeout(300); self.assertIsNone(pg.query_selector(".uf-ext .chip"))
                pg.click("#uf-chip-x"); pg.wait_for_timeout(300)
                self.assertIsNone(pg.query_selector("#uf-ext"))                                       # every filter always in view
                pg.wait_for_selector("#uf-kat-add")                                                   # set by hand: a category of MoneyMoney
                kat = pg.evaluate("document.querySelector('#uf-kats option').value")
                pg.fill("#uf-kat-add", kat); pg.dispatch_event("#uf-kat-add", "change"); pg.wait_for_selector(".uf-ext .chip")
                self.assertTrue(all(norm(k2) == norm(kat) or norm(k2).startswith(norm(kat) + " / ") for k2 in pg.evaluate("UMS.transactions.map(u => u.category)")))
                pg.click("#uf-chip-x"); pg.wait_for_timeout(300)
                self.assertIsNone(pg.query_selector(".uf-ext .chip")); self.assertEqual(pg.input_value("#uf-von"), "")
                pg.click("#nav a[href='#cashflow']"); pg.wait_for_selector("#cf-pie .cf-pie-sl")
                # where a category counts is a setting: its own page under Verwaltung, linked from here (the old address leads there)
                pg.click("#main a[href='#accounts/positions']"); pg.wait_for_selector(".kp-table tr[data-p]")
                self.assertTrue(pg.inner_text("#page-title").startswith("Konten & Regeln")); self.assertTrue(pg.query_selector("#nav a.on[href='#accounts']"))
                self.assertTrue(pg.query_selector(".tabs button.on[data-next='#accounts/positions']"))
                self.assertIn("→", pg.inner_text(".kp-table tbody tr td.kp-arrow"))
                # a parent category without a choice of yours counts per subcategory; a choice on it passes down to them
                par = pg.evaluate("""(() => { const rs = [...document.querySelectorAll('.kp-table tr[data-p]')];
                    const p = rs.find(r => !r.querySelector('.kp-pos').dataset.obj && !r.querySelector('.kp-pos').value && rs.some(x => x.dataset.p.startsWith(r.dataset.p + ' / ')));
                    return p ? p.dataset.p : null; })()""")
                if par:
                    first = lambda p: pg.evaluate("p => document.querySelector(`.kp-table tr[data-p=\"${CSS.escape(p)}\"] .kp-pos`).options[0].textContent", p)
                    kid = pg.evaluate("p => [...document.querySelectorAll('.kp-table tr[data-p]')].find(r => r.dataset.p.startsWith(p + ' / ')).dataset.p", par)
                    self.assertEqual(first(par), "Je Unterkategorie (automatisch)")
                    opt = pg.evaluate("p => { const s = document.querySelector(`.kp-table tr[data-p=\"${CSS.escape(p)}\"] .kp-pos`); return [s.options[2].value, s.options[2].textContent]; }", par)
                    pg.select_option('.kp-table tr[data-p="%s"] .kp-pos' % par, opt[0]); pg.wait_for_timeout(100)
                    self.assertIn(opt[1], first(kid))
                    pg.select_option('.kp-table tr[data-p="%s"] .kp-pos' % par, ""); pg.wait_for_timeout(100); self.assertEqual(first(par), "Je Unterkategorie (automatisch)")
                # what Kontor needs: present or missing, following a change in the table at once
                pg.evaluate("document.querySelector('details.kb').open = true")
                n0 = pg.inner_text("#kb-sum"); self.assertRegex(n0, r"^\d+ von \d+ vorhanden$")
                pg.select_option('.kp-table tr[data-p="Umbuchung"] .kp-pos', "living"); pg.wait_for_timeout(100)
                self.assertNotEqual(pg.inner_text("#kb-sum"), n0); self.assertIn("fehlt", pg.inner_text(".kb-table"))
                pg.select_option('.kp-table tr[data-p="Umbuchung"] .kp-pos', ""); pg.wait_for_timeout(100); self.assertEqual(pg.inner_text("#kb-sum"), n0)
                # a count opens its payments in the side panel
                pg.click(".kp-table tr[data-p='Umbuchung'] a.kp-tx >> nth=0"); pg.wait_for_selector("#drawer.open tbody tr")
                self.assertTrue(pg.inner_text("#drawer h2").startswith("Umbuchung")); pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
                pg.click(".ka-table tr[data-key='broker'] a.ka-tx >> nth=0"); pg.wait_for_selector("#drawer.open tbody tr")
                pg.evaluate("$('#drawer').insertAdjacentHTML('beforeend', '<textarea id=\"h-csv\" class=\"hidden\">1</textarea>'); window._cf = window.confirm; window.confirm = () => false")
                pg.mouse.click(pg.evaluate("innerWidth") - 8, pg.evaluate("innerHeight") - 8); pg.wait_for_timeout(300)   # unsaved entries: asked first (here: kept)
                self.assertTrue(pg.evaluate("$('#drawer').classList.contains('open')"))
                pg.evaluate("$('#drawer #h-csv').remove(); window.confirm = window._cf")
                pg.mouse.click(pg.evaluate("innerWidth") - 8, pg.evaluate("innerHeight") - 8); pg.wait_for_timeout(300)   # a click on the panel's background closes it
                self.assertFalse(pg.evaluate("$('#drawer').classList.contains('open')"))
                # the account per recipient: Kontor's choice named in the first entry; a choice of your own can be saved
                sel = ".ka-table tr[data-key='broker'] select.ka-ziel"
                self.assertIn("Depot", pg.inner_text(sel + " option >> nth=0")); self.assertTrue(pg.is_disabled("#kp-save"))
                pg.select_option(sel, "external"); self.assertFalse(pg.is_disabled("#kp-save"))
                pg.select_option(sel, ""); self.assertTrue(pg.is_disabled("#kp-save"))
                pg.evaluate("location.hash = '#accounts/positions'"); pg.wait_for_timeout(400)
                self.assertEqual(pg.evaluate("location.hash"), "#accounts/positions"); self.assertTrue(pg.query_selector(".kp-table"))
                pg.click("#nav a[href='#categories']"); pg.wait_for_timeout(400)
                self.assertEqual(len(pg.query_selector_all("#main .tabs button")), 3)          # Offen, Regeln für MoneyMoney, Eingetragen
                # Bilanz: Positionen/Gruppen, inaktive, Konto-Klick -> Verlauf
                pg.click("#nav a[href='#balance']"); pg.wait_for_selector("tr.pos")
                self.assertIn("Bankguthaben", pg.query_selector("#main").inner_text())
                # pages not fully tested yet carry "Alpha" in the menu and at the title; the balance sheet does not
                self.assertTrue(pg.query_selector("#nav a.alpha[href='#planning'] .alpha-tag")); self.assertIsNone(pg.query_selector("#nav a[href='#balance'] .alpha-tag"))
                self.assertIsNone(pg.query_selector("#nav a[href='#cashflow'] .alpha-tag")); self.assertIsNone(pg.query_selector("#nav a[href='#categories'] .alpha-tag"))
                self.assertIsNone(pg.query_selector("#page-title .alpha-tag")); self.assertIsNone(pg.query_selector("#nav a[href='#accounts'] .alpha-tag"))
                self.assertEqual(pg.inner_text("#nav a[href='#accounts'] span"), "Konten & Regeln"); self.assertIsNone(pg.query_selector("#nav a[href='#rules']")); self.assertEqual(pg.inner_text("#nav a[href='#bookings'] span"), "Auto-Buchungen")
                # eine Tabelle: Positionen zugeklappt, aufklappbar; Plan-Spalten rechts in derselben Tabelle
                self.assertEqual(len(pg.query_selector_all("#main table")), 1); self.assertIsNone(pg.query_selector("tr.acct"))
                self.assertTrue(pg.query_selector("#main thead th.plan")); self.assertNotIn("Fortschreibung", pg.query_selector("#main").inner_text())
                pg.click("tr.pos[data-pos='cash'] td:first-child"); pg.wait_for_selector("tr.acct")
                pg.click("#pos-all"); pg.wait_for_timeout(300)
                # single curves below the table: net worth and a chosen sum (default cash + tradable + fixed-term); chips change the sum
                self.assertTrue(pg.query_selector("#lc-nw-svg path.bch-nw")); self.assertTrue(pg.query_selector("#lc-sel-svg path.bch-nw"))
                self.assertEqual(pg.inner_text("#lc-sel-title"), "Liquides Vermögen")      # a known combination gets its name
                # the selection named in words, never in codes: groups, "+", "ohne"; shortened words only in the small chart
                av = ['cash', 'securities', 'term_investments', 'real_estate', 'participations', 'liabilities']
                name = lambda sel, big=True: pg.evaluate("([s, a, l]) => lcSelTitle(s, a, l)[0]", [sel, av, big])
                self.assertEqual(name(['cash', 'securities', 'term_investments', 'liabilities']), "Geldanlagen + Verbindlichkeiten")
                self.assertEqual(name(['cash', 'securities', 'term_investments', 'liabilities'], False), "Geldanlagen + Verbindl.")
                self.assertEqual(name([r for r in av if r != 'participations']), "Nettovermögen ohne Beteiligungen")
                self.assertEqual(name(['cash', 'securities', 'term_investments', 'real_estate']), "Geldanlagen + Immobilien")      # a tie: in plus
                self.assertEqual(name(['cash', 'real_estate']), "Bankguthaben + Immobilien"); self.assertEqual(name(av), "Nettovermögen")
                pg.eval_on_selector("#lc-sel-title", "e => e.scrollIntoView({block: 'center'})"); pg.wait_for_timeout(200)      # below the table: in view first (a scroll hides a tip)
                pg.hover("#lc-sel-title"); pg.wait_for_selector(".tip"); self.assertIn("Bankguthaben + Wertpapiere", pg.inner_text(".tip")); self.assertIn("+ Wertpapiere\n= Liquides Vermögen", pg.inner_text(".tip")); pg.mouse.move(5, 5)
                # the names as one written sum, each word once
                self.assertEqual(pg.evaluate("a => lcSumTip(a)", av).split("\n"), ["\u2007 Bankguthaben", "+ Wertpapiere", "= Liquides Vermögen", "+ Festanlagen", "= Geldanlagen", "+ Beteiligungen",
                                 "= Geldvermögen", "+ Immobilien", "= Bruttovermögen", "+ Verbindlichkeiten", "= Nettovermögen", "",
                                 "Gebundenes Verm. = Bruttoverm. − Liquides Verm."])
                self.assertIn("+ Sachvermögen (Immobilien + Sachwerte)", pg.evaluate("a => lcSumTip(a)", av + ["tangibles"]))
                # composition of one position by account (stacked), chips with the accounts: deselecting one keeps the position line
                self.assertTrue(pg.query_selector("#lc-pos-svg path.lc-band")); self.assertIn("Hausbank Giro", pg.inner_text("#lc-pos-accs"))
                tot = pg.get_attribute("#lc-pos-svg path.lc-total", "d"); nb = len(pg.query_selector_all("#lc-pos-svg path.lc-band"))
                pg.click("#lc-pos-accs label:has-text('Hausbank Giro')"); pg.wait_for_timeout(200)
                self.assertLess(len(pg.query_selector_all("#lc-pos-svg path.lc-band")), nb); self.assertEqual(pg.get_attribute("#lc-pos-svg path.lc-total", "d"), tot)
                bb = pg.query_selector("#lc-pos-hit").bounding_box(); pg.mouse.move(bb["x"] + bb["width"] - 40, bb["y"] + 60); pg.wait_for_timeout(150)
                self.assertIn("Auswahl", pg.inner_text("#lc-pos-tip")); pg.mouse.move(5, 5)
                # portfolios broken down into their securities: only offered where a portfolio of the position has them
                self.assertFalse(pg.is_visible("#lc-pos-mode"))
                pg.select_option("#lc-pos-sel", "securities"); pg.wait_for_timeout(200)
                self.assertTrue(pg.is_visible("#lc-pos-mode")); pg.click("#lc-pos-mode"); pg.wait_for_timeout(200)
                pg.evaluate("lcSet('pos', LC.pos.i0, LC.pos.d.ist - 1)"); pg.wait_for_timeout(100)     # the made-up securities exist only this month
                self.assertIn("Welt-ETF", pg.inner_text("#lc-pos-accs")); pg.click("#lc-pos-mode"); pg.wait_for_timeout(200)
                self.assertNotIn("Welt-ETF", pg.inner_text("#lc-pos-accs"))
                pg.select_option("#lc-pos-sel", "liabilities"); pg.wait_for_timeout(200)
                self.assertNotIn("Hausbank Giro", pg.inner_text("#lc-pos-accs")); pg.evaluate("S.lcPos = null")
                # any small chart can become the large one (the balance sheet then shows small in its place), and back
                pg.click(".lc[data-lc='nw'] .lc-big"); pg.wait_for_selector("#bch.big-nw"); pg.wait_for_selector(".lc[data-lc='bil'] path.lc-band")
                self.assertIn("Nettovermögen", pg.inner_text("#bch .bch-head")); self.assertTrue(pg.query_selector("#bch-svg path.bch-nw"))
                self.assertIn("€", pg.inner_text("#bch-val")); self.assertIsNone(pg.query_selector("#bch-plan"))      # value and change as in the small charts, no plan ahead
                self.assertTrue(pg.evaluate("!S.bchBtn || BCH.i1 <= BCH.d.ist - 2")); self.assertIsNone(pg.query_selector("#lc-bil-val"))     # the small balance sheet: no value line, the chart is taller instead
                self.assertGreater(pg.evaluate("document.querySelector('#lc-bil-svg').getBoundingClientRect().height"), pg.evaluate("document.querySelector('#lc-sel-svg').getBoundingClientRect().height") + 20)
                self.assertTrue(pg.query_selector("#bch .bch-row2 #bch-val"))       # value and change under the title
                pg.click(".lc[data-lc='bil'] .lc-big"); pg.wait_for_timeout(300); self.assertIsNone(pg.query_selector("#bch.big-nw")); self.assertTrue(pg.query_selector(".lc[data-lc='nw']"))
                # enlarging swaps with the large one (so any order is possible); nothing of it is kept on its own -- only "Ansicht speichern"
                order = lambda: pg.eval_on_selector_all("#lc-grid .lc", "cs => cs.map(c => c.dataset.lc)")
                pg.click(".lc[data-lc='nw'] .lc-big"); pg.wait_for_selector("#bch.big-nw"); pg.click(".lc[data-lc='sel'] .lc-big"); pg.wait_for_selector("#bch.big-sel")
                self.assertEqual(order(), ["bil", "nw", "pos"])
                pg.click("#modus-seg button[data-m='years']"); pg.wait_for_timeout(300)
                pg.reload(); pg.wait_for_selector("#bch"); self.assertIsNone(pg.query_selector("#bch.big-sel")); self.assertEqual(order(), ["nw", "sel", "pos"])
                self.assertTrue(pg.query_selector("#modus-seg button[data-m='months'].on"))
                pg.click(".lc[data-lc='pos'] .lc-big"); pg.wait_for_selector("#bch.big-pos"); pg.click("#modus-seg button[data-m='years']"); pg.wait_for_timeout(300)
                pg.click("#bch-rb button[data-m='120']"); pg.wait_for_timeout(200); pg.click("#view-save"); pg.wait_for_timeout(200)
                pg.reload(); pg.wait_for_selector("#bch.big-pos"); self.assertEqual(order(), ["nw", "sel", "bil"])
                self.assertTrue(pg.query_selector("#modus-seg button[data-m='years'].on")); self.assertTrue(pg.query_selector("#bch-rb button[data-m='120'].on"))
                # one default each for months and years: the one saved last opens, switching takes the other one's ranges
                pg.click("#modus-seg button[data-m='months']"); pg.wait_for_timeout(300); self.assertTrue(pg.query_selector("#bch-rb button[data-m='12'].on"))     # large chart: 1 J
                pg.click("#bch-rb button[data-m='36']"); pg.wait_for_timeout(200); pg.click("#view-save"); pg.wait_for_timeout(200)
                pg.click("#modus-seg button[data-m='years']"); pg.wait_for_timeout(300); self.assertTrue(pg.query_selector("#bch-rb button[data-m='120'].on"))
                pg.reload(); pg.wait_for_selector("#bch"); self.assertTrue(pg.query_selector("#modus-seg button[data-m='months'].on")); self.assertTrue(pg.query_selector("#bch-rb button[data-m='36'].on"))
                pg.click("#view-reset"); pg.wait_for_timeout(300)
                self.assertIsNone(pg.query_selector("#bch.big-pos")); self.assertEqual(order(), ["nw", "sel", "pos"]); self.assertTrue(pg.query_selector("#modus-seg button[data-m='months'].on"))
                self.assertIsNone(pg.evaluate("localStorage.getItem('kontor.balanceView')"))
                pg.click("#pos-all"); pg.wait_for_timeout(300)                       # all positions open again (as before)
                # table and large chart can be moved up and down (small arrows in their headers), kept with "Ansicht speichern"
                order3 = lambda: pg.evaluate("""() => [...document.querySelectorAll('#main #bch, #main .wrap.bil-tbl, #main #lc-grid')].map(e => e.id === 'bch' ? 'chart' : e.id === 'lc-grid' ? 'lines' : 'table')""")
                tbl = lambda mv: ".wrap .th-mv[data-blk='table'][data-mv='%s']" % mv
                self.assertEqual(order3(), ["chart", "table", "lines"])          # the chart first: opening rows does not move it
                pg.click(tbl(-1)); pg.wait_for_timeout(300); self.assertEqual(order3(), ["table", "chart", "lines"]); self.assertFalse(pg.is_visible(tbl(-1)))
                pg.click(tbl(1)); pg.wait_for_timeout(300); self.assertEqual(order3(), ["chart", "table", "lines"])
                pg.click(tbl(1)); pg.wait_for_timeout(300); self.assertEqual(order3(), ["chart", "lines", "table"])
                pg.click("#bch .th-mv[data-blk='chart'][data-mv='1']"); pg.wait_for_timeout(300); self.assertEqual(order3(), ["lines", "chart", "table"])
                pg.click("#view-save"); pg.wait_for_timeout(200)
                self.assertEqual(pg.evaluate("JSON.parse(localStorage.getItem('kontor.balanceView')).views.months.blocks"), ["lines", "chart", "table"])
                pg.click("#view-reset"); pg.wait_for_timeout(300); self.assertEqual(order3(), ["chart", "table", "lines"]); pg.click("#pos-all"); pg.wait_for_timeout(300)
                # the same in the table: a portfolio opens into its securities (without opening the account's history)
                if not pg.query_selector("[data-dep]"):
                    pg.click("tr.pos[data-pos='securities'] td:first-child")
                pg.wait_for_selector("[data-dep]"); pg.click("[data-dep]"); pg.wait_for_selector("tr.wpr")
                self.assertIn("Welt-ETF", pg.inner_text("#main table")); self.assertFalse(pg.query_selector("#drawer.open"))
                self.assertTrue(any("ISIN IE00B4L5Y983" in x for x in pg.eval_on_selector_all("tr.wpr td:first-child", "ts => ts.map(t => t.title)")))      # MoneyMoney's identity always on hover
                checked = {x.get_attribute("data-r") for x in pg.query_selector_all("#lc-chips input:checked")}
                self.assertIn("cash", checked); self.assertTrue(checked <= {"cash", "securities", "term_investments"})
                v0 = pg.inner_text("#lc-sel-val"); pg.click("#lc-chips input[data-r='real_estate']"); pg.wait_for_timeout(200)
                self.assertNotEqual(pg.inner_text("#lc-sel-val"), v0)
                # range buttons by view: months 6 M / 1 J / 2 J, years 1 J / 3 J / 10 J
                self.assertEqual(pg.eval_on_selector_all(".lc-rb[data-lc='nw'] button", "bs => bs.map(b => b.dataset.m)"), ["6", "12", "24"])
                pg.click(".lc-rb[data-lc='nw'] button[data-m='24']"); pg.wait_for_timeout(200)
                self.assertTrue(pg.query_selector(".lc-rb[data-lc='nw'] button[data-m='24'].on"))
                self.assertEqual(pg.inner_text("#lc-nw-span"), pg.evaluate("spanText(LC.nw.i1 - LC.nw.i0)"))      # the test data is a little shorter than 2 years
                # zoomed in: no range button, the length below them; zoomed back out to a year: "1 J" marked again
                pg.evaluate("lcView('nw', LC.nw.i1 - 10, 10, false)"); pg.wait_for_timeout(100)
                self.assertIsNone(pg.query_selector(".lc-rb[data-lc='nw'] button.on")); self.assertEqual(pg.inner_text("#lc-nw-span"), "10 Monate")
                pg.evaluate("lcView('nw', LC.nw.i1 - 12, 12, false)"); pg.wait_for_timeout(100)
                self.assertTrue(pg.query_selector(".lc-rb[data-lc='nw'] button[data-m='12'].on")); self.assertEqual(pg.inner_text("#lc-nw-span"), "1 Jahr")
                self.assertEqual(pg.evaluate("[11, 18, 24, 30, 32, 37, 120].map(spanText)"), ["11 Monate", "18 Monate", "2 Jahre", "2\u202f½ Jahre", "2 Jahre 8 Mon.", "3 Jahre 1 Mon.", "10 Jahre"])
                self.assertEqual(pg.evaluate("[11, 18, 24, 30, 32, 37, 120].map(spanText)"), ["11 Monate", "18 Monate", "2 Jahre", "2\u202f½ Jahre", "2 Jahre 8 Mon.", "3 Jahre 1 Mon.", "10 Jahre"])
                self.assertEqual(pg.eval_on_selector_all("#bch-rb button", "bs => bs.map(b => b.dataset.m)"), ["6", "12", "24", "36", "0"])
                pg.evaluate("S.lcSel = null")
                pg.click("#nav a[href='#balance']"); pg.wait_for_selector("tr.pos")
                # Grafik: waagerechtes Wischen verschiebt bei gleicher Laenge (auch am linken Rand), Doppelklick halbiert den Zeitraum
                self.assertIsNone(pg.query_selector("#bch-on"))
                pg.click("#bch-rb button[data-m='12']"); pg.wait_for_timeout(200)
                # the balance sheet as the large chart: a third of the range ahead (running month + 3 plan months), "Plan" switches it off; no value
                self.assertEqual(pg.evaluate("BCH.i1"), pg.evaluate("Math.min(BCH.d.months.length - 1, BCH.d.ist + 2)")); self.assertIsNone(pg.query_selector("#bch-val"))
                pg.click("#bch-plan"); pg.wait_for_timeout(200); self.assertEqual(pg.evaluate("BCH.i1"), pg.evaluate("BCH.d.ist - 2"))
                self.assertEqual(pg.evaluate("BCH.i1 - BCH.i0"), 12); self.assertTrue(pg.query_selector("#bch-rb button[data-m='12'].on"))
                self.assertEqual(pg.eval_on_selector_all("#bch .bch-head > *", "es => es.map(e => e.id || e.querySelector('input')?.id || '')").index("bch-n") - 1,
                                 pg.eval_on_selector_all("#bch .bch-head > *", "es => es.map(e => e.id || '')").index("bch-plan"))      # Plan left of the month field
                pg.click("#bch-plan"); pg.wait_for_timeout(200); self.assertEqual(pg.evaluate("BCH.i1"), pg.evaluate("Math.min(BCH.d.months.length - 1, BCH.d.ist + 2)"))
                self.assertEqual(pg.input_value("#bch-n"), "12")         # the month field counts up to the last completed month
                pg.fill("#bch-n", "6"); pg.press("#bch-n", "Enter"); pg.wait_for_timeout(200)
                self.assertTrue(pg.query_selector("#bch-rb button[data-m='6'].on")); self.assertEqual(pg.evaluate("[BCH.i0, BCH.i1]"), pg.evaluate("[BCH.d.ist - 8, BCH.d.ist]"))
                pg.fill("#bch-n", "9"); pg.press("#bch-n", "Enter"); pg.wait_for_timeout(200)
                self.assertEqual(pg.evaluate("[BCH.i0, BCH.i1]"), pg.evaluate("[BCH.d.ist - 11, BCH.d.ist + 1]")); self.assertEqual(pg.input_value("#bch-n"), "9")
                pg.click("#bch-rb button[data-m='12']"); pg.wait_for_timeout(200)
                self.assertGreaterEqual(pg.evaluate("document.querySelectorAll('#bch-svg line.bch-grid').length"), 5)      # at least five lines on the amount axis
                # the small net worth chart: just the month and the value in its tip
                pg.query_selector("#lc-nw-plot").scroll_into_view_if_needed(); pb = pg.query_selector("#lc-nw-plot").bounding_box()
                pg.mouse.move(pb["x"] + pb["width"] * .6, pb["y"] + pb["height"] / 2); pg.wait_for_timeout(150)
                self.assertTrue(pg.query_selector("#lc-nw-tip.one"), pg.inner_html("#lc-nw-tip")); self.assertNotIn("Nettovermögen", pg.inner_text("#lc-nw-tip")); self.assertIn("€", pg.inner_text("#lc-nw-tip"))
                pg.mouse.move(5, 5); pg.wait_for_timeout(100)
                # the first column of the table: wider by dragging its edge, back by a double click
                pg.evaluate("document.querySelector('.bil-tbl').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(100)      # not under the sticky top bar
                w0 = pg.evaluate("document.querySelector('.bil-tbl thead th').getBoundingClientRect().width"); gb = pg.query_selector(".bil-tbl .col-grip").bounding_box()
                pg.mouse.move(gb["x"] + 3, gb["y"] + gb["height"] / 2); pg.mouse.down(); pg.mouse.move(gb["x"] + 63, gb["y"] + gb["height"] / 2, steps=4); pg.mouse.up()
                self.assertAlmostEqual(pg.evaluate("document.querySelector('.bil-tbl thead th').getBoundingClientRect().width"), w0 + 60, delta=3); self.assertTrue(pg.evaluate("S.bilW > 0"))
                pg.dblclick(".bil-tbl .col-grip"); pg.wait_for_timeout(100); self.assertIsNone(pg.evaluate("S.bilW"))
                self.assertAlmostEqual(pg.evaluate("document.querySelector('.bil-tbl thead th').getBoundingClientRect().width"), w0, delta=1)
                pg.evaluate("document.querySelector('#bch').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(150)      # the large chart below the table: in view
                # the area under the pointer stands out, its row in the tip too
                c = pg.evaluate("""() => { const ps = [...document.querySelectorAll('#bch-svg .bch-area')].map(p => p.getBoundingClientRect()).sort((a, b) => b.width * b.height - a.width * a.height);
                    const r = ps[0]; return [r.left + r.width / 2, r.top + r.height / 2]; }""")
                pg.mouse.move(c[0], c[1]); pg.wait_for_timeout(150)
                self.assertTrue(pg.query_selector("#bch-svg.hl .bch-area.hl")); self.assertTrue(pg.query_selector("#bch-tip div.on"))
                pg.mouse.move(5, 5); pg.wait_for_timeout(100); self.assertIsNone(pg.query_selector("#bch-svg.hl"))
                # over the month axis: the values without marking an area
                pb = pg.query_selector("#bch-svg .bch-pan").bounding_box(); pg.mouse.move(pb["x"] + pb["width"] / 2, pb["y"] + pb["height"] / 2); pg.wait_for_timeout(150)
                self.assertTrue(pg.is_visible("#bch-tip")); self.assertIsNone(pg.query_selector("#bch-svg.hl")); pg.mouse.move(5, 5); pg.wait_for_timeout(100)
                # a click on an area works like the table: an account closes its position, the position opens again
                centre = """f => { const ps = [...document.querySelectorAll('#bch-svg .bch-area')].filter(p => f(BCH.d.series[+p.dataset.s])).map(p => [p, p.getBoundingClientRect()])
                    .sort((a, b) => b[1].width * b[1].height - a[1].width * a[1].height); const [p, r] = ps[0]; return [r.left + r.width / 2, r.top + r.height / 2, BCH.d.series[+p.dataset.s].role]; }"""
                x, y, role = pg.evaluate("() => (%s)(x => x.acc && !x.dep)" % centre)
                pg.mouse.click(x, y); pg.wait_for_timeout(400); self.assertFalse(pg.evaluate("r => !!S.posOpen[r]", role))
                self.assertTrue(pg.is_visible("#bch-tip")); self.assertTrue(pg.query_selector("#bch-svg.hl"))      # still under the mouse, without moving it
                x, y, _ = pg.evaluate("r => (%s)(x => x.pos && x.role === r)" % centre, role)
                pg.mouse.click(x, y); pg.wait_for_timeout(400); self.assertTrue(pg.evaluate("r => !!S.posOpen[r]", role))
                n_acc = pg.evaluate("r => BCH.d.series.filter(x => x.role === r && document.querySelector(`#bch-svg .bch-area[data-s=\"${BCH.d.series.indexOf(x)}\"]`)).length", role)
                self.assertEqual(len(pg.query_selector_all("#bch-svg .bch-area.hl")), n_acc)       # all that opened, until the mouse moves
                # the mouse over the name of a row marks the same area in the chart; a click on a value shows month and area for a moment
                pg.hover("tr.acct td:first-child"); pg.wait_for_timeout(100); self.assertTrue(pg.query_selector("#bch-svg.hl .bch-area.hl")); pg.mouse.move(5, 5)
                pg.click("tr.acct td:nth-child(3)"); pg.wait_for_timeout(150)
                self.assertFalse(pg.query_selector("#drawer.open")); self.assertTrue(pg.query_selector("#bch-svg.hl .bch-area.hl")); self.assertTrue(pg.query_selector("#bch-hover .bch-cross"))
                pg.wait_for_timeout(1300); self.assertIsNone(pg.query_selector("#bch-svg.hl")); self.assertIsNone(pg.query_selector("#bch-hover .bch-cross"))
                # a second click on the name of the account whose history is open closes it
                pg.click("tr.acct td:first-child"); pg.wait_for_selector("#drawer.open"); pg.wait_for_timeout(300)
                pg.click("tr.acct td:first-child"); pg.wait_for_timeout(400); self.assertIsNone(pg.query_selector("#drawer.open"))
                span = pg.evaluate("BCH.i1 - BCH.i0"); bb = pg.query_selector("#bch-hit").bounding_box()
                pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
                for _ in range(40):
                    pg.mouse.wheel(-300, 0)
                pg.wait_for_timeout(300)
                self.assertEqual(pg.evaluate("BCH.i0"), 0); self.assertEqual(pg.evaluate("BCH.i1 - BCH.i0"), span)
                pg.mouse.dblclick(bb["x"] + bb["width"] / 2, bb["y"] + 17); pg.wait_for_timeout(300)        # above the areas (a click on one opens it)
                self.assertLessEqual(pg.evaluate("BCH.i1 - BCH.i0"), span // 2 + 1)
                # click on a month heading: chart moved (same span) so that the month lands above the column, column marked
                pg.click("#bch-rb button[data-m='12']"); pg.wait_for_timeout(200)
                for side in (0, 1):         # a visible month on the left and one on the right of the table
                    key = pg.evaluate("""side => { const w = document.querySelector('#main .wrap'), wr = w.getBoundingClientRect(), fw = w.querySelector('thead th').offsetWidth;
                        const vis = [...w.querySelectorAll('thead th[data-key]')].filter(h => { const r = h.getBoundingClientRect(); return r.left >= wr.left + fw - 1 && r.right <= wr.right + 1; });
                        return (side ? vis[vis.length - 2] : vis[1]).dataset.key; }""", side)
                    pg.evaluate("document.querySelector(\"#main .wrap thead th[data-key='%s']\").click()" % key); pg.wait_for_timeout(200)
                    self.assertEqual(pg.evaluate("BCH.i1 - BCH.i0"), span)
                    ok = pg.evaluate("""key => { const i = BCH.d.months.indexOf(key), G = BCH.geo, sr = document.querySelector('#bch-svg').getBoundingClientRect(),
                        r = document.querySelector(`#main .wrap thead th[data-key="${key}"]`).getBoundingClientRect(), step = (G.W - G.P.l - G.P.r) / (BCH.i1 - BCH.i0);
                        return [i >= BCH.i0 && i <= BCH.i1 && (Math.abs(sr.left + G.x(i) - (r.left + r.width / 2)) <= 2 || BCH.i0 === 0 || BCH.i1 === BCH.d.months.length - 1),
                            [i, BCH.i0, BCH.i1, sr.left + G.x(i), r.left + r.width / 2, step]]; }""", key)
                    self.assertTrue(ok[0], (key, ok[1]))
                self.assertTrue(pg.query_selector("#main thead th[data-key='%s'].bch-on" % key)); self.assertFalse(pg.is_visible("#bch-tip"))
                # the small charts keep their length and end with that month; the page does not scroll; the mark goes away again
                self.assertEqual(pg.evaluate("k => Object.keys(LC).filter(id => document.querySelector(`#lc-${id}-svg`)).map(id => LC[id].d.months[LC[id].i1] === k)", key), [True, True, True])
                y0 = pg.evaluate("scrollY"); pg.wait_for_timeout(1400)
                self.assertIsNone(pg.query_selector("#bch-hover .bch-cross")); self.assertIsNone(pg.query_selector("#main thead th.bch-on")); self.assertEqual(pg.evaluate("scrollY"), y0)
                bb = pg.query_selector("#lc-pos-plot").bounding_box(); pg.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2); pg.wait_for_timeout(200)
                self.assertTrue(pg.is_visible("#lc-pos-sel"))          # a click into chart 3 keeps its title (dropdown)
                # equity ratio (alpha) under net worth: a click shows the calculation
                self.assertIsNone(pg.query_selector("#main .bil-tbl tr.ekq"))           # folded by default; the name of net worth opens it
                pg.click("#main .bil-tbl tr.total td:first-child"); pg.wait_for_selector("#main .bil-tbl tr.ekq")
                pg.click("#main .bil-tbl tr.ekq td:first-child"); pg.wait_for_selector("#drawer.open .ekq-tbl")
                self.assertIn("Eigenkapitalquote", pg.inner_text("#drawer")); self.assertIn("Alpha GbR: 40 % von", pg.inner_text("#drawer"))
                pg.click("#drawer .close"); pg.wait_for_timeout(300)
                # a click on a net worth value: aligned as by the month heading, and the net worth dot blinks once
                k = pg.evaluate("Array.from(document.querySelectorAll('#main .bil-tbl tr.total td')).findIndex((td, n) => n > 0 && (() => { const r = td.getBoundingClientRect(), w = document.querySelector('#main .wrap').getBoundingClientRect(); return r.left > w.left + 300 && r.right < w.right - 20; })())")
                pg.evaluate("k => document.querySelectorAll('#main .bil-tbl tr.total td')[k].click()", k); pg.wait_for_timeout(150)
                self.assertTrue(pg.query_selector("#bch-hover .bch-dot.blink")); self.assertTrue(pg.evaluate("""k => { const td = document.querySelectorAll('#main .bil-tbl tr.total td')[k], key = td.closest('table').querySelector('thead tr').children[k].dataset.key,
                    i = BCH.d.months.indexOf(key), G = BCH.geo, sr = document.querySelector('#bch-svg').getBoundingClientRect(), r = td.getBoundingClientRect();
                    return Math.abs(sr.left + G.x(i) - (r.left + r.width / 2)) <= 2 || BCH.i0 === 0 || BCH.i1 === BCH.d.months.length - 1; }""", k))
                pg.wait_for_timeout(1400); self.assertIsNone(pg.query_selector("#bch-hover .bch-dot.blink"))
                self.assertIsNone(pg.query_selector("#bch-svg .bch-today-l"))        # no "heute" label above the chart
                # aligned with the table: each column centre has its point right above it, no value tip, the chart follows the table
                pg.click("#bch-link"); pg.wait_for_selector("#bch.linked"); pg.wait_for_timeout(300)
                off = pg.evaluate("""() => { const svg = document.querySelector('#bch-svg').getBoundingClientRect(), w = document.querySelector('#main .wrap'),
                    th = [...w.querySelectorAll('thead th[data-key]')].find(h => { const r = h.getBoundingClientRect(); return r.left > w.getBoundingClientRect().left + 250 && r.right < w.getBoundingClientRect().right; });
                    const r = th.getBoundingClientRect(), tick = [...document.querySelectorAll('#bch-svg .bch-tick')].map(l => +l.getAttribute('x1') + svg.left);
                    return Math.min(...tick.map(x => Math.abs(x - (r.left + r.width / 2)))); }""")
                self.assertLess(off, 1.5)
                pg.evaluate("document.querySelector('#bch').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(200)      # below the table: in view
                bb = pg.query_selector("#bch-hit").bounding_box(); pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + 60); pg.wait_for_timeout(150)
                self.assertFalse(pg.is_visible("#bch-tip"))
                # swiping and dragging on the chart (also on the axes) scroll the table
                sl = lambda: pg.evaluate("document.querySelector('#main .wrap').scrollLeft")
                pg.evaluate("document.querySelector('#main .wrap').scrollLeft = 0"); pg.wait_for_timeout(300); s0 = sl()
                pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] - 8); pg.mouse.wheel(400, 0); pg.wait_for_timeout(600)
                self.assertGreater(sl(), s0); s1 = sl()
                pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + 80); pg.mouse.down(); pg.mouse.move(bb["x"] + bb["width"] / 2 + 250, bb["y"] + 80, steps=6); pg.mouse.up(); pg.wait_for_timeout(600)
                self.assertLess(sl(), s1)
                pg.click("#bch-link"); pg.wait_for_timeout(300); self.assertIsNone(pg.query_selector("#bch.linked"))
                pg.click("#bch-rb button[data-m='0']"); pg.wait_for_timeout(200)
                # waagerecht zur aktuellen Spalte gescrollt (auch in der Jahresansicht)
                self.assertGreater(pg.evaluate("document.querySelector('#main .wrap').scrollLeft"), 0)
                pg.click("#modus-seg button[data-m='years']"); pg.wait_for_timeout(300)
                self.assertIsNotNone(pg.query_selector("#main thead th[data-cur]"))
                if pg.evaluate("S.tab") == "balance": self.assertIsNone(pg.query_selector("#main td.year, #main th.year"))      # only years: none marked as a year
                pg.click("#modus-seg button[data-m='months']"); pg.wait_for_timeout(300)
                # senkrecht: Position je Reiter, nicht vom einen in den anderen uebertragen
                pg.set_viewport_size({"width": 1440, "height": 500}); pg.evaluate("window.scrollTo(0, 300)"); y_bil = pg.evaluate("window.scrollY")
                pg.click("#nav a[href='#help']"); pg.wait_for_timeout(300); self.assertEqual(pg.evaluate("window.scrollY"), 0)
                pg.click("#nav a[href='#balance']"); pg.wait_for_timeout(400); self.assertEqual(pg.evaluate("window.scrollY"), y_bil)
                pg.evaluate("window.scrollTo(0, 0)"); pg.set_viewport_size({"width": 1440, "height": 900})
                # balance sheet, month view: no year columns (they would only repeat December), a line separates the years;
                # switch in the toolbar, not top right
                self.assertEqual(len(pg.query_selector_all("#modus-seg button")), 2)
                self.assertIsNone(pg.query_selector("#main thead th.year")); self.assertTrue(pg.query_selector("#main thead th.ystart")); self.assertIsNone(pg.query_selector("#top-ctl"))
                self.assertIsNone(pg.query_selector("#main .toolbar #planan")); self.assertTrue(pg.query_selector("#main thead th.plan"))   # Bilanz immer mit Plan
                if pg.query_selector("#alle-zeilen"):        # only offered when empty or hidden accounts exist
                    n_rows = len(pg.query_selector_all("tr.acct")); pg.click("#main label:has(#alle-zeilen)"); pg.wait_for_timeout(300)
                    self.assertGreaterEqual(len(pg.query_selector_all("tr.acct")), n_rows)
                    pg.click("#main label:has(#alle-zeilen)"); pg.wait_for_timeout(300)
                pg.click("tr.acct[data-id='%s'] td" % F.uid("priv.depot")); pg.wait_for_selector("#drawer.open #h-grid")
                self.assertIn("Monatsstände", pg.query_selector("#drawer").inner_text())
                pg.click("#drawer details.holdings summary"); self.assertIn("Welt-ETF", pg.query_selector("#drawer details.holdings").inner_text())   # Depotpositionen
                pg.keyboard.press("Escape"); pg.wait_for_selector("#drawer:not(.open)")
                pg.click("tr.acct[data-id='%s'] td" % F.uid("priv.giro")); pg.wait_for_selector("#drawer.open #h-grid")     # zweites Oeffnen
                self.assertIn("Hausbank Giro", pg.query_selector("#drawer").inner_text())
                self.assertTrue(pg.query_selector("#drawer #h-chart svg"))                                  # Verlauf als Grafik
                pg.click("#page-title", position={"x": 5, "y": 5}); pg.wait_for_selector("#drawer:not(.open)")                        # Klick daneben schliesst
                pg.click("tr.acct[data-id='%s'] td" % F.uid("priv.depot")); pg.wait_for_selector("#drawer.open #h-grid")
                pg.fill("#drawer input[data-mk='2026-09']", "77000"); pg.click("#h-save"); pg.wait_for_timeout(1200)
                if shots: pg.screenshot(path=os.path.join(shots, "ui_verlauf_drawer.png"))
                pg.keyboard.press("Escape")
                self.assertEqual(store.load("state.json")["history"][F.uid("priv.depot")]["2026-09"], 77000.0)
                # Einrichtung: Bausteine, Positionen-Editor speichern
                pg.click("#nav a[href='#setup']"); pg.wait_for_selector(".setup-list")
                self.assertIn("Bereiche", pg.query_selector("#main").inner_text())
                # it stays in the menu until you close it yourself; then it can be shown again
                if not pg.evaluate("setupMissing()"):
                    pg.click("#setup-done"); pg.wait_for_function("location.hash === '#overview'"); pg.wait_for_timeout(200)
                    self.assertTrue(pg.evaluate("document.querySelector('#nav-setup').classList.contains('hidden')")); self.assertTrue(pg.evaluate("S.CFG.ui.setup_done"))
                    pg.goto("http://127.0.0.1:%d/#setup" % port); pg.wait_for_selector("#setup-again"); pg.click("#setup-again"); pg.wait_for_selector("#setup-done")
                    self.assertFalse(pg.evaluate("S.CFG.ui.setup_done")); pg.wait_for_timeout(200)
                    self.assertFalse(pg.evaluate("document.querySelector('#nav-setup').classList.contains('hidden')"))
                else:
                    self.assertTrue(pg.evaluate("document.querySelector('#setup-done').disabled"))
                pg.goto("http://127.0.0.1:%d/#accounts" % port); pg.wait_for_selector("#save-konten")
                for _ in range(2):          # "Verlauf..." laesst sich wiederholt oeffnen
                    pg.click("tr[data-uuid='%s'] .k-hist" % F.uid("priv.depot")); pg.wait_for_selector("#drawer.open #h-grid")
                    pg.keyboard.press("Escape"); pg.wait_for_selector("#drawer:not(.open)")
                # Im Verlauf-Fenster die Quelle wechseln (Umsätze <-> Stände), danach ein anderes Konto oeffnen
                pg.click("tr[data-uuid='%s'] .k-hist" % F.uid("priv.giro")); pg.wait_for_selector("#drawer.open #h-grid")
                pg.click("#drawer .hq-q[data-q='balances']"); pg.wait_for_selector("#drawer.open .hq-q.on[data-q='balances']", timeout=1000)     # sofort
                for _ in range(150):           # CSP verbietet wait_for_function mit Intervall -> selbst abfragen
                    if not pg.evaluate("document.querySelector('#drawer .hq-q').disabled"):
                        break
                    pg.wait_for_timeout(100)
                # erst Vorschau: nichts gespeichert, Tabelle unveraendert, Hinweis + Speichern/Verwerfen
                self.assertIn("Vorschau", pg.query_selector("#hq-pending").inner_text()); self.assertTrue(pg.is_visible("#h-undo"))
                self.assertEqual(pg.eval_on_selector("tr[data-uuid='%s'] .k-verlauf" % F.uid("priv.giro"), "e => e.value"), "transactions")
                self.assertNotEqual((store.load("config.json")["balance"].get("history_source") or {}).get(F.uid("priv.giro") + " | Hausbank Giro"), "balances")
                self.assertEqual(pg.evaluate("getComputedStyle(document.querySelector('#h-grid')).gridTemplateColumns.split(' ').length"), 1)   # Monate untereinander
                pg.click("#h-save"); pg.wait_for_timeout(800)
                self.assertEqual(pg.eval_on_selector("tr[data-uuid='%s'] .k-verlauf" % F.uid("priv.giro"), "e => e.value"), "balances")          # nach Speichern zieht die Tabelle mit
                self.assertEqual(pg.query_selector("#hq-pending").inner_text(), "")
                pg.keyboard.press("Escape"); pg.wait_for_selector("#drawer:not(.open)")
                pg.click("tr[data-uuid='%s'] .k-hist" % F.uid("priv.giro")); pg.wait_for_selector("#drawer.open .hq-q.on[data-q='balances']", timeout=10000)   # bleibt beim erneuten Oeffnen
                # Kontostaende: eigener Wert 2026-03 wirkt sofort auf die Monate davor (Vorschau ohne Neubau)
                self.assertFalse(pg.is_disabled("#drawer input[data-mk='2026-03']"))
                before = pg.get_attribute("#drawer input[data-mk='2026-01']", "placeholder")
                pg.fill("#drawer input[data-mk='2026-03']", "1000"); pg.click("#h-save")
                for _ in range(50):
                    if pg.get_attribute("#drawer input[data-mk='2026-01']", "placeholder") != before:
                        break
                    pg.wait_for_timeout(100)
                self.assertNotEqual(pg.get_attribute("#drawer input[data-mk='2026-01']", "placeholder"), before)
                self.assertEqual(pg.input_value("#drawer input[data-mk='2026-03']"), "1.000,00")
                pg.click("#drawer .hq-q[data-q='transactions']"); pg.wait_for_selector("#drawer.open .hq-q.on[data-q='transactions']", timeout=10000)
                for _ in range(100):
                    if pg.is_disabled("#drawer input[data-mk='2026-03']"):
                        break
                    pg.wait_for_timeout(50)
                self.assertTrue(pg.is_disabled("#drawer input[data-mk='2026-03']"))                     # Umsaetze: eigene Werte zaehlen nicht
                self.assertEqual(pg.get_attribute("#drawer input[data-mk='2026-01']", "placeholder"), before)
                pg.keyboard.press("Escape"); pg.wait_for_selector("#drawer:not(.open)")
                pg.click("tr[data-uuid='%s'] .k-hist" % F.uid("priv.tr")); pg.wait_for_selector("#drawer.open #h-grid", timeout=10000)
                self.assertIn("Broker Giro", pg.query_selector("#drawer").inner_text())
                pg.keyboard.press("Escape"); pg.wait_for_selector("#drawer:not(.open)")
                self.assertTrue(pg.query_selector("#k-show-inactive").is_checked())        # ausgeblendete standardmaessig sichtbar
                # keine "auto"-Optionen bei Position und Verlauf; Anzeige "nach Aktivität" / "immer anzeigen" / "ausblenden"
                self.assertEqual(pg.evaluate("document.querySelectorAll('.k-rolle option[value=\"\"], .k-verlauf option[value=\"\"]').length"), 0)
                self.assertEqual(pg.evaluate("[...document.querySelector('.k-show').options].map(o => o.text)"), ["nach Aktivität", "immer anzeigen", "ausblenden"])
                row = "tr[data-uuid='%s']" % F.uid("priv.giro")
                pg.select_option(row + " .k-show", "hide"); self.assertIn("inactive", pg.get_attribute(row, "class"))   # sofort grau
                self.assertTrue(pg.is_visible(row + " .k-vis"))
                pg.select_option(row + " .k-show", ""); self.assertNotIn("inactive", pg.get_attribute(row, "class") or "")
                # Vorschlag in der Liste gekennzeichnet; gestrichelt nur, solange ein neues Konto ihn traegt (auch nach Zurueckwechseln)
                self.assertIn("(Vorschlag)", pg.eval_on_selector(row + " .k-rolle", "e => e.options[e.selectedIndex].text"))
                neu_row = "tr.new[data-uuid]"
                if pg.query_selector(neu_row):
                    sel = neu_row + " .k-rolle"; vor = pg.get_attribute(sel, "data-vor")
                    self.assertIn("proposal", pg.get_attribute(sel, "class"))
                    pg.select_option(sel, "other" if vor != "other" else "term_investments"); self.assertNotIn("proposal", pg.get_attribute(sel, "class"))
                    pg.select_option(sel, vor); self.assertIn("proposal", pg.get_attribute(sel, "class"))
                # Konten nach Bereichen gruppiert, in der Reihenfolge der Bereiche
                groups = pg.evaluate("[...document.querySelectorAll('.acct-table tr.bgroup td')].map(t => t.textContent)")
                self.assertEqual(groups[:3], ["Privat", "Alpha GbR", "Beta GbR"])
                # Auswahlfelder gleich breit -> "Verlauf…" steht sauber untereinander
                xs = pg.evaluate("[...document.querySelectorAll('.acct-table .k-hist')].map(b => Math.round(b.getBoundingClientRect().left))")
                self.assertEqual(len(set(xs)), 1, xs)
                for _ in range(40):                                                       # the side panel closed: the page has its width back
                    if pg.evaluate("getComputedStyle(document.querySelector('main')).marginRight") == "0px":
                        break
                    pg.wait_for_timeout(50)
                pg.wait_for_timeout(100)
                self.assertLessEqual(pg.evaluate("document.querySelector('.acct-table').scrollWidth"), pg.evaluate("document.querySelector('#main').clientWidth"))   # passt in die Breite
                pg.select_option("tr[data-uuid='%s'] .k-rolle" % F.uid("priv.immo"), "real_estate")
                self.assertIsNone(pg.query_selector("#k-neu"))                                          # kein "Bericht aktualisieren" im Einrichtungsschritt
                pg.click("#save-konten"); pg.wait_for_selector("#findings-k2 .ok", timeout=20000); pg.wait_for_timeout(1500)
                self.assertTrue(pg.evaluate("document.querySelector('#bereich-seg').classList.contains('hidden')"))   # Bereichsleiste nur in den Auswertungen
                self.assertIn("Gespeichert", pg.query_selector("#findings-k2").inner_text())
                bil = store.load("config.json")["balance"]
                self.assertEqual(bil["roles"][F.uid("priv.immo") + " | Immobilie Lindenstraße"], "real_estate")
                self.assertEqual(bil["accounts_mapping"][F.uid("priv.giro") + " | Hausbank Giro"]["position"], "cash")    # fest gespeichert
                self.assertTrue(all(v in ("transactions", "balances") for v in bil["history_source"].values()) and len(bil["history_source"]) >= 10)
                if shots: pg.screenshot(path=os.path.join(shots, "ui_einrichtung_konten.png"), full_page=True)
                # Immobilien: Objekt + Kalkulation anlegen, Ergebnis, speichern, Jahrestabelle
                pg.goto("http://127.0.0.1:%d/#properties" % port); pg.wait_for_selector("#im-new")
                pg.once("dialog", lambda d: d.accept("Parkweg")); pg.click("#im-new"); pg.wait_for_selector("#im-kalk-new")
                pg.once("dialog", lambda d: d.accept("Basis")); pg.click("#im-kalk-new"); pg.wait_for_selector("#im-calc")
                pg.fill("input[data-p='purchase_price']", "1500000"); pg.fill("input[data-p='rent.net_rent_month']", "9000")
                pg.click("#im-loan-add"); pg.wait_for_selector(".loan-box")
                pg.fill(".loan-box input[data-p='loans.0.amount']", "1200000"); pg.fill(".loan-box input[data-p='loans.0.annuity_month']", "6000")
                pg.click("#im-calc"); pg.wait_for_timeout(900)
                self.assertIn("Kaufpreisfaktor", pg.query_selector("#im-result").inner_text())
                pg.click("#im-kalk-save")
                for _ in range(60):                                                                       # saved (a slow machine: not after a fixed time)
                    cfg_im = store.load("config.json").get("real_estate") or []
                    if cfg_im and cfg_im[0].get("calcs") and "purchase_price" in (cfg_im[0]["calcs"][0].get("inputs") or {}):
                        break
                    pg.wait_for_timeout(250)
                self.assertEqual(cfg_im[0]["calcs"][0]["inputs"]["purchase_price"], 1500000)
                self.assertEqual(cfg_im[0]["calcs"][0]["inputs"]["loans"][0]["amount"], 1200000)
                if shots: pg.screenshot(path=os.path.join(shots, "ui_immobilie.png"), full_page=True)
                pg.click(".tabs button[data-t='years']"); pg.wait_for_timeout(500)
                self.assertIn("Restschuld", pg.query_selector("#main").inner_text())
                pg.click(".tabs button[data-t='documents']"); pg.wait_for_timeout(300)
                self.assertIn("Dokumente", pg.query_selector("#main").inner_text())
                pg.click("#nav a[href='#properties']"); pg.wait_for_selector(".card[data-im]")
                if shots: pg.screenshot(path=os.path.join(shots, "ui_immobilien.png"), full_page=True)
                # Zuordnen: Kontor traegt die Kategorie in MoneyMoney ein (kein Schalter) -> Gruppe verschwindet
                import mm_categories
                MockBridge.extra_cats = [("Haushalt", 0, True, {}), ("Werkzeug", 1, False, {})]
                app.categories_raw = mm_categories.with_paths(MockBridge().export_categories())
                pg.click("#nav a[href='#categories']"); pg.wait_for_selector(".kz-group")
                self.assertTrue(pg.inner_text("#page-title").startswith("Kategorisieren")); self.assertEqual(pg.get_attribute("#page-title .page-hq", "data-help"), "categories"); self.assertIsNone(pg.query_selector("#kz-mm-on"))
                pg.wait_for_selector(".kz-save:not([disabled])")
                n_before = len(pg.query_selector_all(".kz-group"))
                box = pg.query_selector(".kz-group"); box.query_selector(".kz-kat").fill("Haushalt / Werkzeug"); box.query_selector(".kz-save").click()
                pg.wait_for_timeout(1500)
                self.assertLess(len(pg.query_selector_all(".kz-group")), n_before)
                self.assertTrue(any(w[0] == "set" and w[2] == F.uid("cat:Werkzeug") for b in MockBridge.instances for w in b.written))
                if shots: pg.screenshot(path=os.path.join(shots, "ui_zuordnen.png"), full_page=True)
                # Eingetragen: the entry listed; taken back (with the question), it leaves the list
                pg.click("#main .tabs button[data-next='#categories/written']"); pg.wait_for_selector(".kw-table tr[data-id]")
                self.assertTrue(pg.query_selector("#kw-undo").is_disabled())
                n_w = len(pg.query_selector_all(".kw-table tr[data-id]")); first_id = pg.get_attribute(".kw-sel:not([disabled])", "data-id")
                pg.click(".kw-sel:not([disabled])"); self.assertIn("1", pg.inner_text("#kw-undo"))
                pg.once("dialog", lambda d: d.accept()); pg.click("#kw-undo")
                pg.wait_for_selector(".kw-table tr[data-id='%s']" % first_id, state="detached", timeout=15000)
                self.assertEqual(len(pg.query_selector_all(".kw-table tr[data-id]")), n_w - 1)
                self.assertTrue(any(w[0] == "set" and w[2] == F.uid("cat:Unkategorisiert") for b in MockBridge.instances for w in b.written))
                self.assertTrue(pg.query_selector("#main .tabs-aside[href='#accounts/positions']"))          # where categories count: one click away
                pg.click("#main .tabs button[data-next='#categories/rules']"); pg.wait_for_selector("#main .note")
                self.assertIn("Regeln", pg.query_selector("#main").inner_text())
                if shots: pg.screenshot(path=os.path.join(shots, "ui_kategorien.png"), full_page=True)
                # Planung: Ereignis anlegen -- erst wenn die Neuberechnung nach dem Zuordnen fertig und geladen ist (sonst baut
                # das Nachladen die Seite waehrend der Eingabe neu auf)
                for _ in range(60):                 # asks for the status itself instead of waiting for the next poll (every 30 s)
                    if pg.evaluate("async () => { try { await pollStatus(); } catch (e) {} return !!S.STATUS && !(S.STATUS.report || {}).running && (S.STATUS.report || {}).as_of === BER.as_of; }"):
                        break
                    pg.wait_for_timeout(500)
                pg.wait_for_timeout(1000)
                pg.click("#nav a[href='#planning']"); pg.wait_for_selector(".ev-row")
                row = pg.query_selector_all(".ev-row")[-1]
                row.query_selector(".ev-text").fill("Rückzahlung"); row.query_selector(".ev-betrag").fill("50000")
                row.query_selector(".ev-von").select_option(F.uid("priv.depot") + " | Depot"); row.query_selector(".ev-nach").select_option(F.uid("priv.darl") + " | Darlehen Lindenstraße")
                row.query_selector(".ev-save").click(); pg.wait_for_timeout(1200)
                self.assertTrue(pg.query_selector(".ev-row .ev-del"))
                if shots: pg.screenshot(path=os.path.join(shots, "ui_planung_ereignisse.png"), full_page=True)
                # Jahresmodus
                pg.click("#nav a[href='#cashflow']"); pg.wait_for_timeout(300)
                pg.click("#modus-seg button[data-m='years']"); pg.wait_for_timeout(400)
                self.assertIn("2026", pg.query_selector("#main thead").inner_text())
                if shots: pg.screenshot(path=os.path.join(shots, "ui_kapitalfluss_jahre.png"))
                pg.click("#modus-seg button[data-m='months']"); pg.wait_for_timeout(200)
                # Planung: the loan plan by the loans' names (their rows are grouped by kind)
                pg.click("#nav a[href='#planning']"); pg.wait_for_selector(".edit")
                loans = pg.eval_on_selector_all("tr[data-loan]", "e => e.map(x => x.dataset.loan)")
                self.assertIn("Darlehen Lindenstraße", loans); self.assertFalse({"Tilgung", "Zinsen", "Darlehensaufnahme"} & set(loans))
                # Planung: Methode setzen
                pg.click("#nav a[href='#planning']"); pg.wait_for_selector(".edit")
                first = pg.query_selector(".edit"); first.query_selector(".meth").select_option("fix"); first.query_selector(".amount").fill("1234"); first.query_selector(".save").click()
                pg.wait_for_timeout(800)
                self.assertIn("1.234,00", pg.query_selector("#main").inner_text())
                # Umsaetze: Zeile oeffnen -> Drawer
                pg.click("#nav a[href='#transactions']"); pg.wait_for_selector("#ums-table tbody tr")
                pg.click("#ums-table tbody tr td:nth-child(4)"); pg.wait_for_selector("#drawer.open"); pg.wait_for_timeout(400)
                self.assertIn("Belege", pg.query_selector("#drawer").inner_text())
                if shots: pg.screenshot(path=os.path.join(shots, "ui_umsaetze_drawer.png"))
                pg.keyboard.press("Escape")
                # Regeln speichern (unveraendert) -> Befunde ok
                pg.evaluate("location.hash = '#accounts/rules'"); pg.wait_for_selector("#save-rules")
                auto = pg.evaluate("S.CFG.dry_run === false"); self.assertEqual(pg.is_checked("#auto-book"), auto)      # the setting as a switch at the top
                # what a rule would book: a click on "… offen" lists it in the side panel, with the way to the approval
                if pg.query_selector("#loans .item"):
                    pg.evaluate("""() => rulesPreviewShow(document.querySelector('#main'), {preview: [{kind: 'loans', i: 0, bookings: 2, items: [
                        {date: '2026-03-31', account: 'X / Darlehen', amount: -100, purpose: 'Tilgung', older: false}, {date: '2026-04-30', account: 'X / Darlehen', amount: -100, purpose: 'Tilgung', older: true}]}]})""")
                    pg.click(".pv-open"); pg.wait_for_selector("#drawer.open #pv-go")
                    self.assertEqual(len(pg.query_selector_all("#drawer tbody tr")), 2); self.assertIn("2 Buchungen", pg.inner_text("#drawer .note"))
                    pg.click("#pv-go"); pg.wait_for_selector(".mode-chip"); self.assertEqual(pg.evaluate("location.hash"), "#bookings")
                    pg.evaluate("location.hash = '#accounts/rules'"); pg.wait_for_selector("#save-rules")
                self.assertIn("Kontor bucht" if auto else "Freigabe", pg.inner_text(".set-row"))
                pg.click("#nav a[href='#bookings']"); pg.wait_for_selector(".mode-chip"); self.assertIn("Vollautomatisch" if auto else "Mit Freigabe", pg.inner_text(".mode-chip"))
                self.assertIsNone(pg.query_selector("#run-dry"))              # checked at every sync, no button of its own
                # the approval list with your selection: left out, recalculated (adjusted), new, not needed any more
                rows = pg.evaluate("""() => { const sv = {...BOOK}, A = 'a|#kontor-wert-20260131-1', B = 'a|#kontor-wert-20260228-1', C = 'a|#kontor-wert-20260331-1', D = 'a|#kontor-wert-20260430-1';
                    Object.assign(BOOK, {off: new Set([A]), edits: {}, calc: [{key: B, amount: 150}, {key: C, amount: 5}], extra: {}});
                    BOOK.extra[C] = {key: C, amount: 5};
                    const r = bkRows({proposals: [{key: A, amount: 50}, {key: B, amount: 100}, {key: D, amount: 7}]});
                    Object.assign(BOOK, sv); return r.map(x => [x.k.slice(-10), x.off, x.gone, x.b, x.adjusted, x.new]); }""")
                self.assertEqual(rows, [["20260131-1", True, False, 50, False, False], ["20260228-1", False, False, 150, True, False],
                                        ["20260430-1", False, True, 7, False, False], ["20260331-1", False, False, 5, False, True]])
                # folded sections stay open when the page is drawn again (e.g. "Not booked" while booking several again); no
                # explanations the button at the top already gives on hover
                pg.click("details[data-keep='bk-hist'] summary"); pg.evaluate("routeKeeping(\"details[data-keep='bk-hist']\")"); pg.wait_for_timeout(500)
                self.assertTrue(pg.evaluate("document.querySelector(\"details[data-keep='bk-hist']\").open"))
                self.assertNotIn("Buchungsregeln bearbeiten", pg.inner_text("#main")); self.assertNotIn("bei jedem Abgleich", pg.inner_text("#main"))
                n_wait = pg.evaluate("((S.STATUS.last_run || {}).dry_run && (S.STATUS.last_run.proposals || []).length) || 0")
                self.assertEqual(pg.evaluate("(document.querySelector('#nav a[href=\"#bookings\"] .nbadge') || {}).textContent || ''"), str(n_wait) if n_wait else "")
                pg.evaluate("window.__st = S.STATUS; S.STATUS = Object.assign({}, S.STATUS, {last_run: {dry_run: true, time: 'x', proposals: [{}, {}, {}]}, update: {newer: true, available: '9.9.9'}}); statusMini()")
                self.assertEqual(pg.inner_text("#nav a[href='#bookings'] .nbadge"), "3"); self.assertTrue(pg.query_selector("#nav a[href='#settings'] .nbadge"))
                pg.evaluate("S.STATUS = Object.assign({}, S.STATUS, {last_run: {dry_run: true, time: 'x', proposals: Array(250).fill({})}}); statusMini()")
                self.assertEqual(pg.inner_text("#nav a[href='#bookings'] .nbadge"), "99+")
                self.assertNotIn("Freigabe", pg.inner_text("#status-mini")); self.assertIsNone(pg.query_selector("#nav a[href='#bookings'] .alpha-tag"))
                pg.evaluate("S.STATUS = window.__st; statusMini()")
                pg.click(".mode-chip"); pg.wait_for_selector("#save-rules")
                # companies come from the areas: one card each with its share, the participation chosen, target/actual live
                self.assertEqual(pg.eval_on_selector_all(".co-card h3", "e => e.map(x => x.textContent)"), ["Alpha GbR", "Beta GbR"])
                self.assertIn("40", pg.inner_text(".co-card .co-head"))
                self.assertEqual(pg.eval_on_selector(".co-card .c-bet", "e => e.value").split(" | ")[0], F.uid("priv.bet.ga"))
                pg.wait_for_function("(document.querySelector('.co-card [data-pv=\"b\"]') || {}).textContent?.includes('Soll')", timeout=8000)
                self.assertGreaterEqual(len(pg.query_selector_all(".co-card .hq")), 6); self.assertGreaterEqual(len(pg.query_selector_all("#loans .hq")), 15)
                self.assertTrue(pg.is_disabled("#save-rules"))
                # participation account: only offline accounts with the position "Beteiligungen", nothing chosen in advance
                opts = pg.eval_on_selector_all(".co-card:first-child .c-bet option", "e => e.map(o => o.textContent)")
                self.assertEqual(opts[1:], ["Beteiligung an Alpha GbR", "Beteiligung an Beta GbR"])
                card = """n => { const d = document.createElement('div'); d.innerHTML = companyCard({id: 'x', name: n, share: 0.5}, {}); return [d.querySelector('.c-bet').value, d.querySelector('.c-rmode').value, !!d.querySelector('details')]; }"""
                self.assertEqual(pg.evaluate(card, "Beta GbR"), ["", "date", False])          # no preselection, from a day (today), nothing folded
                # an incomplete counter account is not saved
                # account mirrors: a section of their own (no company needed); an incomplete one is not saved
                self.assertIsNone(pg.query_selector(".co-card .gk-row")); self.assertIsNone(pg.query_selector(".co-card .opt"))
                pg.click("#add-mirror"); pg.select_option("#mirrors .gk-row .g-a", index=1); pg.click("#save-rules"); pg.wait_for_timeout(300)
                self.assertTrue(pg.query_selector("#mirrors .gk-row.invalid")); self.assertEqual(store.load("config.json").get("account_mirrors") or [], [])
                self.assertTrue(pg.query_selector("#mirrors .gk-row .c-rmode"))                    # its own "Buchen ab"
                pick = """([sel, txt]) => { const s = document.querySelector(sel), o = [...s.options].find(o => o.textContent.includes(txt)); s.value = o.value; s.dispatchEvent(new Event('change', {bubbles: true})); }"""
                # an account in two steps: the area, then its accounts (only those)
                self.assertEqual(pg.eval_on_selector_all("#mirrors .gk-row .acct-pick:first-child .ap-area option", "e => e.map(o => o.textContent)")[:3], ["Privat", "Alpha GbR", "Beta GbR"])
                # accounts of the same name name their company: in the menu and as the chosen entry
                pg.evaluate(pick, ["#mirrors .gk-row .acct-pick:first-child .ap-area", "Alpha GbR"])
                self.assertEqual(pg.eval_on_selector("#mirrors .gk-row .g-a", "e => e.value"), "")          # another area: nothing chosen
                opts = pg.eval_on_selector_all("#mirrors .gk-row .g-a option", "e => e.map(o => o.textContent)")
                self.assertIn("Kapitalkonto A · Alpha GbR", opts); self.assertNotIn("Kapitalkonto A · Beta GbR", opts); self.assertNotIn("Immobilie Lindenstraße", opts)
                pg.evaluate(pick, ["#mirrors .gk-row .acct-pick:first-child .ap-area", "Beta GbR"])
                self.assertIn("Kapitalkonto A · Beta GbR", pg.eval_on_selector_all("#mirrors .gk-row .g-a option", "e => e.map(o => o.textContent)"))
                pg.evaluate(pick, ["#mirrors .gk-row .acct-pick:first-child .ap-area", "Privat"])
                opts = pg.eval_on_selector_all("#mirrors .gk-row .g-a option", "e => e.map(o => o.textContent)")
                self.assertIn("Immobilie Lindenstraße", opts); self.assertNotIn("Immobilie Lindenstraße · Privat", opts)    # a name of its own: as it is
                pg.evaluate(pick, ["#mirrors .gk-row .g-a", "Immobilie Lindenstraße"]); pg.evaluate(pick, ["#mirrors .gk-row .g-b", "Immobilie Lindenstraße"])
                pg.click("#save-rules"); pg.wait_for_timeout(300)                                  # the same account twice: said so, not saved
                self.assertTrue(pg.query_selector("#mirrors .gk-row.invalid")); self.assertIn("dasselbe Konto", pg.inner_text("#toast"))
                self.assertEqual(store.load("config.json").get("account_mirrors") or [], [])
                # two accounts, no company involved: saved as a rule of its own, with what it would book
                pg.evaluate(pick, ["#mirrors .gk-row .gk-arrow + .acct-pick .ap-area", "Alpha GbR"]); pg.evaluate(pick, ["#mirrors .gk-row .g-b", "Kapitalkonto B"])
                pg.select_option("#mirrors .gk-row .c-rmode", "all"); pg.wait_for_timeout(1200)      # (the test's day is fixed: "today" here would be in its future)
                self.assertTrue(pg.is_hidden("#mirrors .gk-row .c-ab"))
                self.assertTrue(pg.inner_text("#mirrors .gk-row .pv").strip())
                pg.click("#save-rules"); pg.wait_for_timeout(900)
                ms = store.load("config.json")["account_mirrors"]
                self.assertEqual([(m["a"].split(" | ")[0], m["b"].split(" | ")[0], m["from_date"], "area" in m) for m in ms],
                                 [(F.uid("priv.immo"), F.uid("ga.kap.b"), "all", False)])
                pg.click("#mirrors .gk-row .gk-del")
                pg.fill(".co-card .c-sw", "1")
                pg.keyboard.press("Meta+s"); pg.wait_for_timeout(900)          # ⌘S saves
                self.assertIn("Gespeichert", pg.query_selector("#findings").inner_text())
                self.assertEqual(store.load("config.json")["companies"][0]["threshold"], 1); self.assertTrue(pg.is_disabled("#save-rules"))
                self.assertEqual(store.load("config.json")["account_mirrors"], [])                   # removed again
                # Sync: online or offline per account as a menu; offline accounts recognised as "Offline-Konto"
                self.assertFalse(pg.evaluate("DIRTY.on"))
                pg.evaluate("location.hash = '#accounts'"); pg.wait_for_selector(".ab-sel")          # leaving after ⌘S: no question (a late change event does not count)
                sel = "tr[data-uuid='%s'] .ab-sel" % F.uid("priv.bet.ga")
                self.assertEqual(pg.eval_on_selector(sel, "e => e.value"), "offline")
                self.assertEqual(pg.eval_on_selector(sel, "e => e.title"), "Offline-Konto")                       # why: as recognised (an offline account: no refresh)
                pg.select_option(sel, "online"); pg.wait_for_timeout(900)                                          # saved at once ...
                self.assertIn(F.uid("priv.bet.ga"), " ".join(store.load("config.json")["fetch"]["online"]))
                self.assertFalse(pg.evaluate("DIRTY.on"))                                                          # ... so no unsaved change
                pg.wait_for_selector(sel); pg.select_option(sel, "offline"); pg.wait_for_timeout(900)
                self.assertNotIn(F.uid("priv.bet.ga"), " ".join(store.load("config.json")["fetch"]["online"]))
                # ⌘L locks
                pg.keyboard.press("Meta+l"); pg.wait_for_selector("#login:not(.hidden)")
                pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.click("#login-btn"); wait_shell(pg)
                # mobil
                pg.set_viewport_size({"width": 390, "height": 844}); pg.click("#menu-btn"); pg.click("#nav a[href='#overview']"); pg.wait_for_timeout(600)
                if shots: pg.screenshot(path=os.path.join(shots, "ui_mobile.png"), full_page=True)
                pg.click("#menu-btn"); pg.click("#lock-btn"); pg.wait_for_selector("#login:not(.hidden)")
                # Offline-Ansicht: Service Worker speichert Oberflaeche und Daten; ohne Dienst oeffnet das Passwort die Kopie (nur lesen)
                pg.set_viewport_size({"width": 1440, "height": 900})
                self.assertFalse(pg.evaluate("navigator.serviceWorker.getRegistrations().then(r => r.length)"))   # none on the Mac itself
                pg.evaluate("localStorage.setItem('kontor.testRemote', '1')"); pg.reload(); pg.wait_for_selector("#login-pw")   # act like the iPhone
                pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.click("#login-btn"); wait_shell(pg)
                pg.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.controller !== null", timeout=15000)
                pg.reload(); pg.wait_for_selector(".ov-grid")           # jetzt laufen alle Abrufe durch den Service Worker
                pg.wait_for_function("caches.open('kontor-data-enc').then(c => c.keys()).then(k => k.some(r => r.url.endsWith('/api/offline/verifier')) && k.some(r => r.url.endsWith('/api/dataset')))", timeout=15000)
                # the stored copy is encrypted (key pair of the device, the private key only with the password): no plain text in it
                raw = pg.evaluate("caches.open('kontor-data-enc').then(c => c.match(location.origin + '/api/dataset')).then(r => r.arrayBuffer()).then(b => new TextDecoder('latin1').decode(b))")
                self.assertNotIn("Hausbank", raw); self.assertNotIn("net_worth", raw); self.assertGreater(len(raw), 1000)
                self.assertFalse(pg.evaluate("caches.has('kontor-data')"))                        # never a plain copy
                pg.goto("http://127.0.0.1:%d/#settings/access" % port); pg.wait_for_selector("#sw-state")
                self.assertIn("aktiv", pg.query_selector("#sw-state").inner_text())
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".ov-grid")
                srv.shutdown(); srv.server_close(); stopped = True
                pg.reload(); pg.wait_for_selector("#login:not(.hidden)")
                self.assertIn("nicht erreichbar", pg.query_selector("#login-text").inner_text())
                pg.fill("#login-pw", "falsches-passwort"); pg.click("#login-btn"); pg.wait_for_timeout(1500)
                self.assertIn("falsch", pg.query_selector("#login-err").inner_text())
                pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.click("#login-btn"); pg.wait_for_selector("#shell:not(.hidden)", timeout=20000)
                pg.wait_for_selector(".ov-grid")
                self.assertIn("Offline-Ansicht", pg.query_selector("#banner").inner_text())
                self.assertIn("nettovermögen", pg.query_selector("#main").inner_text().lower())
                msg = pg.evaluate("api('/api/plan', {area: 'x'}).then(() => 'ok').catch(e => e.message)")
                self.assertIn("Offline", msg)
                pg.click("#nav a[href='#balance']"); pg.wait_for_selector("tr.pos")
                self.assertIn("Bankguthaben", pg.query_selector("#main").inner_text())
                # eine Tabelle: Positionen zugeklappt, aufklappbar; Plan-Spalten rechts in derselben Tabelle
                self.assertEqual(len(pg.query_selector_all("#main table")), 1); self.assertIsNone(pg.query_selector("tr.acct"))
                self.assertTrue(pg.query_selector("#main thead th.plan")); self.assertNotIn("Fortschreibung", pg.query_selector("#main").inner_text())
                # waagerecht zur aktuellen Spalte gescrollt (auch in der Jahresansicht)
                self.assertGreater(pg.evaluate("document.querySelector('#main .wrap').scrollLeft"), 0)
                pg.dispatch_event("tr.pos[data-pos='cash'] td:first-child", "click"); pg.wait_for_selector("tr.acct")      # (a Playwright click would first scroll the sticky name column into view)
                pg.click("#pos-all"); pg.wait_for_timeout(300)
                self.assertGreater(pg.evaluate("document.querySelector('#main .wrap').scrollLeft"), 0, "after opening rows")
                pg.click("#modus-seg button[data-m='years']"); pg.wait_for_timeout(300)
                self.assertIsNotNone(pg.query_selector("#main thead th[data-cur]"))
                pg.click("#modus-seg button[data-m='months']"); pg.wait_for_timeout(300)
                # senkrecht: Position je Reiter, nicht vom einen in den anderen uebertragen
                pg.set_viewport_size({"width": 1440, "height": 500}); pg.evaluate("window.scrollTo(0, 300)"); y_bil = pg.evaluate("window.scrollY")
                pg.click("#nav a[href='#help']"); pg.wait_for_timeout(300); self.assertEqual(pg.evaluate("window.scrollY"), 0)
                pg.click("#nav a[href='#balance']"); pg.wait_for_timeout(400); self.assertEqual(pg.evaluate("window.scrollY"), y_bil)
                pg.evaluate("window.scrollTo(0, 0)"); pg.set_viewport_size({"width": 1440, "height": 900})
                if shots: pg.screenshot(path=os.path.join(shots, "ui_offline.png"), full_page=True)
                # Am Mac selbst gibt es keine Offline-Ansicht: Dienst weg -> Hinweis und neuer Versuch
                pg.evaluate("localStorage.removeItem('kontor.testRemote')")
                pg.reload(); pg.wait_for_selector("#login:not(.hidden)"); pg.wait_for_timeout(500)
                self.assertIn("Dienst", pg.query_selector("#login-err").inner_text())
                self.assertEqual(errors, [])
                b.close()
        finally:
            if not stopped:
                srv.shutdown(); srv.server_close()
            shutil.rmtree(d, ignore_errors=True)


class SafariTablesTest(unittest.TestCase):
    """WebKit (Safari's engine, where installed -- GitHub Actions): the cash flow's pinned names and its figures meet row by
    row, on every row, also with everything open and scrolled sideways; the balance sheet's year view has no year marks."""

    def test_rows_meet(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright fehlt")
        d = tempfile.mkdtemp(prefix="kontor-wk-")
        key, src = load_or_create_master_key(d)
        store = Store(d, key, src); store.save("config.json", config_for_test(os.path.join(d, "Belege")))
        reset_mock(); patch_today()
        app = App(store, d, bridge_factory=MockBridge)
        app.do_run(False, True)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                try:
                    b = p.webkit.launch()
                except Exception:
                    self.skipTest("WebKit nicht installiert")
                for scale in (1, 2):
                    pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=scale)
                    pg.goto("http://127.0.0.1:%d/" % port)
                    if pg.query_selector("#login-pw2:not(.hidden)") and pg.is_visible("#login-pw2"):
                        pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.fill("#login-pw2", "sehr-geheimes-passwort")
                    else:
                        pg.fill("#login-pw", "sehr-geheimes-passwort")
                    pg.click("#login-btn"); wait_shell(pg)
                    pg.evaluate("location.hash = '#cashflow'"); pg.wait_for_selector("table.cf-names")
                    pg.click("#cf-ebene button[data-e='3']"); pg.wait_for_selector("tr.det"); pg.wait_for_timeout(500)
                    measure = """() => { const a = document.querySelector('.cf-pair > table:not(.cf-names)'), n = document.querySelector('.cf-pair > .cf-names');
                        return [...a.rows].map((r, i) => { const x = r.getBoundingClientRect(), y = n.rows[i].getBoundingClientRect(); return [i, +(x.top - y.top).toFixed(2), +(x.bottom - y.bottom).toFixed(2)]; })
                          .filter(e => Math.abs(e[1]) > 0.25 || Math.abs(e[2]) > 0.25); }"""
                    self.assertEqual(pg.evaluate(measure), [], "scale %d" % scale)
                    pg.evaluate("document.querySelector('.cf-pair').parentElement.scrollLeft = 200; window.scrollBy(0, 333)"); pg.wait_for_timeout(300)
                    self.assertEqual(pg.evaluate(measure), [], "scale %d, scrolled" % scale)
                    self.assertTrue(pg.evaluate("[...document.querySelectorAll('.cf-pair > .cf-names tbody td')].every(c => { const s = getComputedStyle(c); return s.backgroundClip === 'padding-box' && s.borderBottomColor === 'rgba(0, 0, 0, 0)'; })"))
                    # the balance sheet in years: no column marked as a year (nothing else to tell it from)
                    pg.evaluate("location.hash = '#balance'"); pg.wait_for_selector("tr.pos")
                    pg.click("#modus-seg button[data-m='years']"); pg.wait_for_timeout(300)
                    self.assertIsNone(pg.query_selector("#main td.year, #main th.year"))
                    pg.click("#modus-seg button[data-m='months']"); pg.wait_for_timeout(200)
                    pg.close()
                b.close()
        finally:
            srv.shutdown(); srv.server_close()
            shutil.rmtree(d, ignore_errors=True)


class BrowserWizardTest(unittest.TestCase):
    """Leere Installation: Einrichtungsassistent, Bereiche speichern, Paket laden, Bericht erstellen."""

    def test_sprache_umschalten(self):
        """Sprache auf der Anmeldeseite waehlen (vor der Einrichtung), danach Oberflaeche und Einstellung auf Englisch; zurueck auf Deutsch."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright fehlt")
        d = tempfile.mkdtemp(prefix="kontor-lang-")
        key, src = load_or_create_master_key(d)
        store = Store(d, key, src); store.save("config.json", config_for_test(os.path.join(d, "Belege")))
        reset_mock(); patch_today()
        app = App(store, d, bridge_factory=MockBridge)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 860})
                errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.goto("http://127.0.0.1:%d/" % port); pg.wait_for_selector("#login:not(.hidden)")
                self.assertEqual(pg.inner_text("#login-btn"), "Passwort festlegen")
                with pg.expect_navigation(): pg.select_option("#lang-sel", "en")
                pg.wait_for_selector("#login:not(.hidden)")
                self.assertEqual(pg.inner_text("#login-btn"), "Set password")
                self.assertEqual(pg.get_attribute("#login-pw2", "placeholder"), "Repeat password")
                pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.fill("#login-pw2", "sehr-geheimes-passwort"); pg.click("#login-btn")
                wait_shell(pg); pg.wait_for_timeout(500)
                self.assertIn("Overview", pg.inner_text("#nav")); self.assertEqual(pg.evaluate("document.documentElement.lang"), "en")
                self.assertEqual(store.load("config.json")["ui"]["language"], "en")
                pg.goto("http://127.0.0.1:%d/#setup" % port); pg.wait_for_selector(".setup-list")
                self.assertIn("Historical balances", pg.inner_text(".setup-list"))
                with pg.expect_navigation(): pg.select_option("#w-lang", "de")
                wait_shell(pg); pg.wait_for_timeout(500)
                self.assertIn("Übersicht", pg.inner_text("#nav")); self.assertEqual(store.load("config.json")["ui"]["language"], "de")
                self.assertEqual(errors, [])
                b.close()
        finally:
            srv.shutdown(); srv.server_close(); shutil.rmtree(d, ignore_errors=True)

    def test_wizard_and_package(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright fehlt")
        d = tempfile.mkdtemp(prefix="kontor-wiz-")
        key, src = load_or_create_master_key(d)
        store = Store(d, key, src)
        store.save("config.json", {"updates": {"check_mode": "aus"}, "schedule": {"automatic": False}, "receipts": {"folder": os.path.join(d, "Belege")}})
        reset_mock(); patch_today()
        app = App(store, d, bridge_factory=MockBridge)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        pkg_path = os.path.join(d, "test.kontor.json")
        led = Ledger(accounts_from_export(MockBridge.state["accounts"]), tx_from_export(MockBridge.state["txs"]))
        pkg = core.export_package(core.merged_config(config_for_test()), "Testpaket", strip_uuids=True, ledger=led)
        pkg["config"]["loans"][0]["loan_account"] = "Darlehen Fremd"       # muss zugeordnet werden
        with open(pkg_path, "w", encoding="utf-8") as f:
            json.dump(pkg, f, ensure_ascii=False)
        shots = os.environ.get("KONTOR_SHOTS")
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2 if shots else 1)
                errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
                reqs = []; pg.on("request", lambda r: reqs.append(r.url))
                pg.goto("http://127.0.0.1:%d/" % port)
                pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.fill("#login-pw2", "sehr-geheimes-passwort"); pg.click("#login-btn")
                wait_shell(pg); pg.wait_for_selector("a[href='#setup']")
                pg.click("#main a[href='#setup'] button"); pg.wait_for_selector(".setup-list")
                self.assertEqual(pg.query_selector(".srow .n").inner_text().strip(), "1")      # geordnete Liste, Schritt 1 offen
                if shots: pg.screenshot(path=os.path.join(shots, "ui_einrichtung_leer.png"), full_page=True)
                pg.click(".srow a[href='#settings/moneymoney'] button"); pg.wait_for_selector(".steps")
                self.assertIn("Wofür", pg.evaluate("document.querySelector('.steps .hq').dataset.tip"))      # Erklaerung im Hilfe-Symbol
                self.assertNotIn("Wofür", pg.query_selector("#main").inner_text())                            # nicht doppelt im Text
                pg.click("#w-check")
                self.assertTrue(pg.evaluate("document.querySelector('#w-check').disabled || document.querySelector('#w-check').classList.contains('busy') || !!document.querySelector('#w-findings .ok')"))
                pg.wait_for_selector("#w-findings .ok")
                self.assertIn("Konten gelesen", pg.query_selector("#w-findings").inner_text())
                self.assertNotIn("Belegordner", pg.query_selector("#w-findings").inner_text())
                self.assertNotIn("Keine Bereiche", pg.query_selector("#w-findings").inner_text())
                self.assertTrue(pg.query_selector(".setup-nav a.next[href='#accounts/areas']"))           # the setup's way on: one slim line
                self.assertTrue(pg.is_visible(".steps"))                                                   # just checked: the connection stays in view
                # step 1 is checked every few seconds only while the connection is not there yet: connected, MoneyMoney is left alone
                n0 = len([r for r in reqs if "/api/status?fresh=1" in r]); pg.wait_for_timeout(3500)
                self.assertEqual(len([r for r in reqs if "/api/status?fresh=1" in r]), n0)
                if shots: pg.screenshot(path=os.path.join(shots, "ui_einrichtung_verbindung.png"), full_page=True)
                # Tooltip bleibt im Fenster (auch ganz oben)
                pg.evaluate("window.scrollTo(0, 0)")              # (clicking the button may have scrolled the short page: the symbol then sits under the title)
                pg.hover(".steps .hq"); pg.wait_for_selector(".tip")
                box = pg.evaluate("(() => { const r = document.querySelector('.tip').getBoundingClientRect(); return [r.top, r.left, r.right, window.innerWidth]; })()")
                self.assertGreaterEqual(box[0], 0); self.assertGreaterEqual(box[1], 0); self.assertLessEqual(box[2], box[3])
                pg.click(".setup-nav a.next"); pg.wait_for_selector("#save-bereiche")
                self.assertEqual(len(pg.query_selector_all("#bereiche .item")), 3)          # Vorschlag: jede Gruppe der obersten Ebene
                names = lambda: pg.evaluate("[...document.querySelectorAll('#bereiche .item .b-name')].map(i => i.value)")
                self.assertEqual(names()[0], "Privat")                                       # Hauptbereich zuerst
                self.assertTrue(pg.is_disabled("#bereiche .item:first-child .b-mv[data-d='-1']")); self.assertTrue(pg.is_disabled("#bereiche .item:last-child .b-mv[data-d='1']"))
                pg.click("#bereiche .item:nth-child(2) .b-mv[data-d='-1']"); self.assertEqual(names()[:2], ["Alpha GbR", "Privat"])
                self.assertTrue(pg.is_disabled("#bereiche .item:first-child .b-mv[data-d='-1']"))
                pg.click("#bereiche .item:first-child .b-mv[data-d='1']"); self.assertEqual(names()[:2], ["Privat", "Alpha GbR"])
                # Vorbelegung: Privat = Hauptbereich und privat, GbRs = Gesellschaft; Konten unter gewaehlter Gruppe sind enthalten
                items = {pg.evaluate("i => i.querySelector('.b-name').value", it): it for it in pg.query_selector_all("#bereiche .item")}
                self.assertTrue(items["Privat"].query_selector(".b-haupt").is_checked()); self.assertEqual(items["Privat"].query_selector(".b-art").input_value(), "private")
                self.assertEqual(items["Alpha GbR"].query_selector(".b-art").input_value(), "company"); self.assertFalse(items["Alpha GbR"].query_selector(".b-haupt").is_checked())
                alpha = items["Alpha GbR"]
                self.assertTrue(alpha.query_selector(".b-k[value^='%s']" % F.uid("ga.kk")).is_disabled())     # unter der Gruppe: enthalten, gesperrt
                alpha.query_selector(".b-anteil").fill("40")
                beta = items["Beta GbR"]
                beta.query_selector(".b-k[value^='%s']" % F.uid("gb")).click(); pg.wait_for_timeout(100)      # Gruppe abwaehlen -> Konten frei
                self.assertFalse(beta.query_selector(".b-k[value^='%s']" % F.uid("gb.kk")).is_disabled()); self.assertFalse(beta.query_selector(".b-k[value^='%s']" % F.uid("gb.kk")).is_checked())
                beta.query_selector(".b-k[value^='%s']" % F.uid("gb")).click(); pg.wait_for_timeout(100)      # wieder anhaken -> alle darunter
                self.assertTrue(beta.query_selector(".b-k[value^='%s']" % F.uid("gb.kk")).is_checked())
                pg.evaluate("[...document.querySelectorAll('#bereiche .item')].find(i => i.querySelector('.b-name').value === 'Beta GbR').querySelector('.del').click()")   # Beta GbR nicht als Bereich
                pg.wait_for_timeout(100)
                self.assertNotIn("Kennung", pg.query_selector("#bereiche").inner_text())
                if shots: pg.screenshot(path=os.path.join(shots, "ui_einrichtung_bereiche.png"), full_page=True)
                # Privat: kein Anteil; Gesellschaft: Anteil sichtbar
                self.assertTrue(pg.evaluate("[...document.querySelectorAll('#bereiche .item')].find(i => i.querySelector('.b-name').value === 'Privat').querySelector('.b-anteil-row').classList.contains('hidden')"))
                self.assertFalse(pg.evaluate("[...document.querySelectorAll('#bereiche .item')].find(i => i.querySelector('.b-name').value === 'Alpha GbR').querySelector('.b-anteil-row').classList.contains('hidden')"))
                # "Speichern und weiter": speichert, wartet mit Ladeanzeige auf die Auswertung, dann erst Positionen & Verlauf
                pg.click("button[data-savenext='#accounts']")
                pg.wait_for_selector(".busy-ov", timeout=5000)
                pg.wait_for_selector("#save-konten", timeout=30000)
                self.assertIsNone(pg.query_selector(".busy-ov"))
                self.assertFalse(self.__class__ is None or app.bericht_status()["running"])
                self.assertTrue(pg.query_selector("button[data-savenext='#accounts/history']")); self.assertTrue(pg.query_selector("button[data-next='#setup']"))
                # Schritt 4: Kontostaende aus MoneyMoney (Finder zeigen, Datei ziehen) -- MoneyMoney laeuft im Test
                pg.goto("http://127.0.0.1:%d/#accounts/history" % port); pg.wait_for_selector("#mmh-drop")
                self.assertEqual(pg.inner_text(".tabs button.on"), "Kontostände")                     # a tab of "Konten & Regeln"
                self.assertIn("⌘Q", pg.query_selector("#mmh-s1").inner_text()); self.assertTrue(pg.query_selector("#mmh-zeigen"))
                if shots: pg.screenshot(path=os.path.join(shots, "ui_einrichtung_historie.png"), full_page=True)
                # names of the securities: all listed (MoneyMoney's name first), changeable by hand; nothing is sent without a click
                store.update("state.json", lambda cur: cur.__setitem__("sec_search", {"time": "2026-11-01 10:00", "names": {"IE00B4L5Y983": "ISHARES CORE MSCI WORLD", "DE0007164600": "SAP"}, "without": []}), {})
                pg.reload(); pg.wait_for_selector("#mmh-names:not(.hidden) summary")
                self.assertIsNone(pg.query_selector("#wp-look")); self.assertIn("2 gefunden, 0 ohne Treffer", pg.inner_text("#mmh-names"))
                pg.click("#mmh-names summary"); self.assertEqual(pg.input_value(".wp-edit input[data-isin='DE0007164600']"), "SAP")
                pg.fill(".wp-edit input[data-isin='DE0007164600']", "Mein Fonds")
                pg.click("#wp-names-save"); pg.wait_for_selector("#wp-look-res .ok", timeout=30000)
                self.assertEqual(store.load("state.json")["sec_search"]["own"], {"DE0007164600": "Mein Fonds"})
                store.update("state.json", lambda cur: cur.pop("sec_search", None), {})
                pg.goto("http://127.0.0.1:%d/#accounts" % port); pg.wait_for_selector("#save-konten")
                cfg0 = store.load("config.json")
                self.assertEqual([b["name"] for b in cfg0["areas"]], ["Privat", "Alpha GbR"]); self.assertEqual(sum(1 for b in cfg0["areas"] if b["main_area"]), 1)
                self.assertTrue(all(b["id"] for b in cfg0["areas"]))
                pg.goto("http://127.0.0.1:%d/#accounts/areas" % port); pg.wait_for_selector("#save-bereiche")
                self.assertEqual([b for b in cfg0["areas"] if b["name"] == "Alpha GbR"][0]["share"], 0.4)       # Prozent -> Anteil
                self.assertEqual([b for b in cfg0["areas"] if b["name"] == "Privat"][0]["kind"], "private")
                # Paket laden mit Zuordnung
                pg.click("#nav a[href='#settings']"); pg.wait_for_selector("#e-lang")
                self.assertIsNone(pg.query_selector("#e-autobook"))                              # booking automatically: on the booking rules only
                pg.select_option("#e-theme", "light"); pg.wait_for_selector("#e-theme"); pg.select_option("#e-theme", "dark"); pg.wait_for_selector("#e-theme")
                self.assertFalse(pg.evaluate("DIRTY.on"))                                        # saves at once: nothing unsaved to ask about
                self.assertTrue(pg.get_attribute("#page-title .page-hq", "data-tip").startswith("Allgemein: "))   # the tab it is about
                pg.click("#main .tabs button[data-next='#settings/backup']"); pg.wait_for_selector("#pk-pick")
                with pg.expect_file_chooser() as fc:
                    pg.click("#pk-pick")
                fc.value.set_files(pkg_path); pg.wait_for_selector("#pk-import")
                pg.click("#pk-import"); pg.wait_for_selector(".pk-map")
                pg.select_option(".pk-map", F.uid("ga.vd") + " | Verkäuferdarlehen")
                if shots: pg.screenshot(path=os.path.join(shots, "ui_pakete_zuordnung.png"), full_page=True)
                pg.click("#pk-import2"); pg.wait_for_timeout(800)
                self.assertIn("Übernommen", pg.query_selector("#pk-report").inner_text())
                cfg = store.load("config.json")
                self.assertEqual(cfg["loans"][0]["loan_account"].split(" | ")[0], F.uid("ga.vd"))
                self.assertEqual(len(cfg["companies"]), 2)
                # Bericht erstellen -> Uebersicht mit Kennzahlen
                pg.click("#nav a[href='#setup']"); pg.wait_for_selector(".setup-list")
                self.assertIsNone(pg.query_selector("#w-report"))      # Auswertung existiert schon ("Speichern und weiter" hat auf sie gewartet)
                self.assertIn("eingerichtet", pg.query_selector(".setup-list").inner_text())
                if shots: pg.screenshot(path=os.path.join(shots, "ui_einrichtung.png"), full_page=True)
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".ov-grid .ov-plot svg", timeout=20000)
                self.assertIn("Vermögensbrücke", pg.query_selector("#main").inner_text())
                self.assertEqual(len(pg.query_selector_all("#bereich-seg button")), 2)      # Paket ohne Bereiche laesst die eigenen Bereiche unveraendert
                self.assertEqual(errors, [])
                b.close()
        finally:
            srv.shutdown(); srv.server_close(); shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)


