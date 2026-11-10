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
from model import Ledger, accounts_from_export, fmt_eur, tx_from_export  # noqa: E402
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
        return [t for t in self.txs if mm_bridge.local_date(t["bookingDate"]) >= from_date]

    def export_portfolio(self, account):
        if account == F.uid("priv.depot"):
            return [{"name": "Welt-ETF", "isin": "IE00B4L5Y983", "quantity": 500.0, "marketPrice": 110.0, "marketValue": 55000.0, "purchaseValue": 42000.0, "currency": "EUR", "assetClass": "ETF"},
                    {"name": "Anleihen-ETF", "isin": "IE00BZ163L38", "quantity": 600.0, "marketPrice": 50.0, "marketValue": 30000.0, "purchaseValue": 31000.0, "currency": "EUR", "assetClass": "ETF"}]
        return []

    def add_transaction(self, account_ref, booking_date, payee, amount, purpose="", category=None, fallback_refs=None):
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
        out.append(F.tx("pb.kk", date(y, m, 5), 9500.0, "Mieter", "Miete", "Vermietung\\Parkweg\\Mieteinnahmen"))
        out.append(F.tx("pb.kk", date(y, m, 6), -800.0, "Hausverwaltung", "Hausgeld", "Vermietung\\Parkweg\\Hausgeld"))
        if m == 6:
            out.append(F.tx("priv.giro", date(y, 6, 20), -10000.0, "Alpha GbR", "Einlage", "Umbuchung", "DE02701500000000594937"))
            out.append(F.tx("pb.kk", date(y, 6, 20), 10000.0, "Gesellschafter A", "Einlage", "Umbuchung", "DE02120300000000202051"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def config_for_test(belege_dir=None):
    cfg = {
        "probelauf": False, "mitteilungen": False,
        "zeitplan": {"intervall_minuten": 30, "automatisch": False},
        "darlehen": [{
            "name": "Verkäuferdarlehen", "darlehenskonto": F.uid("pb.vd") + " | Verkäuferdarlehen",
            "quellkonten": [F.uid("pb.kk") + " | Stadtbank Kontokorrent"],
            "erkennung": {"gegen_iban": F.SELLER_IBAN}, "ab_datum": "2026-01-01",
            "zins": {"modell": "jahresbasis", "satz": [{"ab": "2025-11-20", "prozent": 3.3}], "buchungstag": "mit_rate"},
            "buchung": {"gegenpartei": "Verkäufer", "kategorie_tilgung": "Umbuchung", "kategorie_zins": "Zinsen"},
            "quelle_kommentar": True}],
        "bereiche": [
            {"id": F.uid("priv"), "name": "Privat", "art": "privat", "haupt": True, "konten": [F.uid("priv") + " | Privat"]},
            {"id": F.uid("pb"), "name": "Alpha GbR", "art": "gesellschaft", "anteil": 0.49, "konten": [F.uid("pb") + " | Alpha GbR"]},
            {"id": F.uid("shs"), "name": "Beta GbR", "art": "gesellschaft", "anteil": 0.49, "konten": [F.uid("shs") + " | Beta GbR"]}],
        "gesellschaften": [
            {"bereich": F.uid("pb"), "beteiligung": F.uid("priv.bet.pb") + " | Beteiligung an Alpha GbR"},
            {"bereich": F.uid("shs"), "beteiligung": F.uid("priv.bet.shs") + " | Beteiligung an Beta GbR"}],
        "bilanz": {"monate_zurueck": 24, "illiquide_rollen": ["beteiligungen"],
                   "illiquide_konten": [F.uid("priv.darl") + " | Darlehen Lindenstraße"]},
        "kapitalfluss": {"kategorie_zu_konto": {"Investments\\ETF": F.uid("priv.depot") + " | Depot"}},
        "steuer": {"afa": {"Parkweg": {"2026": 40000}}},
        "updates": {"pruefen": "aus"},
        "oberflaeche": {"sperre_minuten": 15, "port": 0},
    }
    if belege_dir:
        cfg["belege"] = {"ordner": belege_dir, "unterordner": "{jahr}/{entitaet}"}
    return cfg


def reset_mock():
    MockBridge.state = {"accounts": F.accounts_raw({"pb.vd": -1600000.0}), "txs": F.pb_transactions(TODAY) + private_transactions(TODAY)}
    MockBridge.instances = []
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
        reset_mock()
        patch_today()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_approve_selection_change_and_reject(self):
        """With approval: book only the chosen bookings, one changed (amount, date, text; its mark stays); the others keep
        waiting; a rejected one is never proposed again; planned bookings are not in "created by Kontor"."""
        import service as MA
        cfg = core.merged_config(self.store.load("config.json")); cfg["probelauf"] = True
        res = core.run_once(self.store, cfg, TODAY, dry=True, force=True, bridge_factory=MockBridge)
        props = res["vorschlaege"]; self.assertEqual(len(props), 24); self.assertTrue(all(p["tag"].startswith("#mm-") for p in props))
        self.assertEqual(MA.kontor_bookings(res["_ledger"].without_planned()), [])     # planned, not made: nothing "created by Kontor"
        self.assertEqual(res["_ledger"].without_planned().accounts[F.uid("pb.vd")].balance, -1600000.0)
        zins = [p for p in props if p["art"] == "zins"]; tilg = [p for p in props if p["art"] == "tilgung"]
        wert = [p for p in props if p["art"] == "wert"]                     # two companies: the same mark, two accounts
        self.assertEqual(len({p["tag"] for p in wert}), 1); self.assertEqual(len({p["key"] for p in wert}), 2)
        st = self.store.load("state.json"); st["kontor_abgelehnt"] = [{"tag": zins[0]["tag"], "konto": zins[0]["konto_id"]}]; self.store.save("state.json", st)
        approve, err = MA.approval({tilg[0]["key"]: {}, wert[0]["key"]: {}, zins[1]["key"]: {"betrag": "-1234,56", "zweck": "Zinsen laut Abrechnung", "datum": "2026-10-15"}})
        self.assertIsNone(err)
        r = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge, approve=approve)
        self.assertEqual(r["status"], "ok", r); self.assertEqual(r["geschrieben"], 4)        # 3 bookings + the comment on the source payment
        self.assertFalse([w for w in r["warnungen"] if "nach Buchung" in w], r["warnungen"])
        self.assertTrue(r["probelauf"]); self.assertEqual(len(r["vorschlaege"]), 20)          # 24 - 1 rejected - 3 booked: still waiting
        self.assertIn(wert[1]["key"], [p["key"] for p in r["vorschlaege"]]); self.assertNotIn(wert[0]["key"], [p["key"] for p in r["vorschlaege"]])
        self.assertNotIn(zins[0]["tag"], [p["tag"] for p in r["vorschlaege"]])
        made = [t for t in MockBridge.state["txs"] if zins[1]["tag"] in (t.get("purpose") or "")]
        self.assertEqual(len(made), 1); self.assertEqual(made[0]["amount"], -1234.56)
        self.assertEqual(made[0]["purpose"], "Zinsen laut Abrechnung · " + zins[1]["tag"])
        self.assertEqual(made[0]["bookingDate"], F._dt(date(2026, 10, 15)))
        self.assertEqual(len(self.store.load("state.json")["kontor_buchungen"]), 3)
        # invalid changes and marks are refused
        self.assertIsNotNone(MA.approval({zins[2]["key"]: {"betrag": "0"}})[1]); self.assertIsNotNone(MA.approval({"rm -rf": {}})[1])
        self.assertIsNotNone(MA.approval({zins[2]["key"]: {"datum": "2026-13-01"}})[1]); self.assertIsNotNone(MA.approval({zins[2]["tag"]: {}})[1])

    def test_run_twice_then_dataset(self):
        cfg = core.merged_config(self.store.load("config.json"))
        res = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge)
        self.assertEqual(res["status"], "ok", res)
        self.assertEqual(res["geschrieben"], 35)      # 11 Tilgung + 11 Zins + 2 Wert + 11 Quellkommentare
        self.assertEqual(len(res["vorschlaege"]), 24)
        vd = [a for a in MockBridge.state["accounts"] if a["name"] == "Verkäuferdarlehen"][0]["balance"][0][0]
        self.assertAlmostEqual(vd, -1600000 + 11 * 8250 - 11 * 4400, 2)
        res2 = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge)
        self.assertEqual(res2["geschrieben"], 0)
        self.assertEqual(core.run_once(self.store, cfg, TODAY, dry=False, force=False, bridge_factory=MockBridge)["status"], "unveraendert")
        cfg2 = copy.deepcopy(cfg); cfg2["gesellschaften"][0]["schwelle"] = 5          # changed rules: checked again without a change in MoneyMoney
        self.assertEqual(core.run_once(self.store, cfg2, TODAY, dry=True, force=False, bridge_factory=MockBridge)["status"], "ok")
        self.assertEqual(core.run_once(self.store, cfg2, TODAY + timedelta(days=1), dry=True, force=False, bridge_factory=MockBridge)["status"], "ok")   # a new day too
        # Kontor's own list of what it booked (besides the marks): 24 bookings, the 11 comments on source payments are none
        recs = self.store.load("state.json")["kontor_buchungen"]
        self.assertEqual(len(recs), 24); self.assertTrue(all(r["tag"].startswith("#mm-") and r["konto"] for r in recs))
        # a booking deleted in MoneyMoney is not made again on its own, but reported as missing; one whose mark was changed counts as there
        txs = MockBridge.state["txs"]
        zins = [t for t in txs if "#mm-zins-" in (t.get("purpose") or "")]
        gone = zins[0]; txs.remove(gone)
        zins[1]["purpose"] = zins[1]["purpose"].replace("#mm-zins-", "#geaendert-")
        res3 = core.run_once(self.store, cfg, TODAY, dry=False, force=True, bridge_factory=MockBridge)
        self.assertEqual(res3["geschrieben"], 0); self.assertEqual(len(res3["vorschlaege"]), 0)
        self.assertEqual([m["tag"] for m in res3["fehlend"]], re.findall(r"#mm-zins-[0-9-]+", gone["purpose"]))
        txs.append(gone)                                                           # back: nothing missing
        ds = self.store.load("dataset.json")
        self.assertEqual(ds["haupt"], F.uid("priv"))
        self.assertEqual(set(ds["bereich_namen"].values()), {"Privat", "Alpha GbR", "Beta GbR"})
        self.assertIn("steuer", ds); self.assertIn("konten", ds); self.assertIn("depots", ds)
        self.assertEqual(ds["depots"][0]["name"], "Depot"); self.assertAlmostEqual(ds["depots"][0]["summe"], 85000.0, 2)
        self.assertTrue(any(abs(v - 1500.0) < 0.01 for v in ds["budgets"].values()), ds["budgets"])
        b = ds["bereiche"][ds["haupt"]]
        self.assertEqual(b["bereich"]["name"], "Privat")
        secs = {s["name"]: {z["zeile"]: z for z in s["zeilen"]} for s in b["kapitalfluss"]["sektionen"]}
        self.assertAlmostEqual(secs["Finanzierung"]["Darlehen Lindenstraße / Tilgung"]["werte"]["2026-10"], -600.0, 2)
        self.assertAlmostEqual(secs["Finanzierung"]["Darlehen Lindenstraße / Zinsen"]["werte"]["2026-10"], -900.0, 2)
        self.assertAlmostEqual(secs["Investitionen"]["Einlage/Entnahme Alpha GbR"]["werte"]["2026-06"], -10000.0, 2)
        # GbR-Bereich: Mieteinnahmen in den Einnahmen, Verkaeuferdarlehen in der Finanzierung
        g = ds["bereiche"][F.uid("pb")]
        gs = {s["name"]: {z["zeile"]: z for z in s["zeilen"]} for s in g["kapitalfluss"]["sektionen"]}
        self.assertTrue(any("Mieteinnahmen" in k for k in gs["Einnahmen"]), list(gs["Einnahmen"]))
        self.assertTrue(any("Verkäuferdarlehen" in k for k in gs["Finanzierung"]), list(gs["Finanzierung"]))
        # Umsatzliste ohne Gegen-IBAN
        ums = self.store.load("transactions.json")
        self.assertTrue(len(ums) > 300); self.assertNotIn("accountNumber", json.dumps(ums)); self.assertNotIn(F.SELLER_IBAN, json.dumps(ums))
        self.assertTrue(all(set(u) >= {"id", "konto", "entitaet", "datum", "betrag", "kategorie"} for u in ums))
        with open(self.store.path("dataset.json"), "rb") as fh:
            raw = fh.read()
        self.assertTrue(raw.startswith(b"MMT1")); self.assertNotIn(b"Privat", raw)

    def test_dry_run_writes_nothing(self):
        cfg = core.merged_config(self.store.load("config.json"))
        with self.assertLogs(level="DEBUG") as cm:
            res = core.run_once(self.store, cfg, TODAY, dry=True, force=True, bridge_factory=MockBridge)
        self.assertEqual(res["geschrieben"], 0); self.assertEqual(len(res["vorschlaege"]), 24)
        # the plain-text log holds no amounts, payees, purposes or account names of the bookings
        logtext = "\n".join(cm.output)
        for p in res["vorschlaege"]:
            self.assertNotIn(p["text"], logtext); self.assertNotIn(fmt_eur(p["betrag"]), logtext)
        self.assertNotIn("Verkäuferdarlehen", logtext); self.assertNotIn("€", logtext)
        vd = [a for a in MockBridge.state["accounts"] if a["name"] == "Verkäuferdarlehen"][0]["balance"][0][0]
        self.assertEqual(vd, -1600000.0)
        self.assertTrue(any("Freigabe" in w for w in self.store.load("dataset.json")["warnungen"]))

    def test_tax_report(self):
        led = Ledger(accounts_from_export(MockBridge.state["accounts"]), tx_from_export(MockBridge.state["txs"]))
        cfg = core.merged_config(config_for_test())
        t = build_tax(led, cfg, TODAY)
        pb = [e for e in t["entitaeten"] if e["name"] == "Alpha GbR"][0]
        self.assertEqual(pb["art"], "gbr"); self.assertEqual(pb["anteil"], 0.49)
        j = pb["jahre"]["2026"]
        self.assertIn("Parkweg", j["objekte"])
        o = j["objekte"]["Parkweg"]
        self.assertAlmostEqual(o["arten"]["Mieteinnahmen"], 11 * 9500.0, 2)
        self.assertAlmostEqual(o["arten"]["Hausgeld"], -11 * 800.0, 2)
        self.assertEqual(o["afa"], 40000.0)
        self.assertAlmostEqual(o["ergebnis"], 11 * 9500 - 11 * 800 - 40000, 2)
        self.assertAlmostEqual(o["anteil_ergebnis"], round(o["ergebnis"] * 0.49, 2), 2)
        priv = [e for e in t["entitaeten"] if e["name"] == "Privat"][0]["jahre"]["2026"]
        self.assertIn("Anlage N (Arbeitslohn)", priv["positionen"])
        self.assertAlmostEqual(priv["positionen"]["Anlage N (Arbeitslohn)"]["betrag"], 11 * 6500.0, 2)
        self.assertFalse(any("Umbuchung" in k["pfad"] for p in priv["positionen"].values() for k in p["kategorien"]))

    def test_check_config_findings(self):
        led = Ledger(accounts_from_export(MockBridge.state["accounts"]), tx_from_export(MockBridge.state["txs"]))
        cfg = core.merged_config(config_for_test())
        f = core.check_config(led, MockBridge().export_categories(), cfg)
        self.assertFalse([x for x in f if x["stufe"] == "fehler"], f)
        cfg["darlehen"][0]["darlehenskonto"] = F.uid("priv.giro") + " | Hausbank Giro"
        f = core.check_config(led, [], cfg)
        self.assertTrue(any(x["stufe"] == "fehler" and "Bankanbindung" in x["text"] for x in f))

    def test_package_roundtrip_and_mapping(self):
        led = Ledger(accounts_from_export(MockBridge.state["accounts"]), tx_from_export(MockBridge.state["txs"]))
        cfg = core.merged_config(config_for_test())
        pkg = core.export_package(cfg, "Test", strip_uuids=True, ledger=led)
        self.assertEqual(pkg["kontor_paket"], 1)
        txt = json.dumps(pkg, ensure_ascii=False)
        self.assertNotIn(F.uid("pb.vd"), txt); self.assertNotIn("oberflaeche", pkg["config"]); self.assertIn("Verkäuferdarlehen", txt)
        new_cfg, unresolved, report = core.import_package(core.merged_config({}), pkg, led, "ergaenzen")
        self.assertEqual(unresolved, [], unresolved)
        self.assertEqual(new_cfg["darlehen"][0]["darlehenskonto"].split(" | ")[0], F.uid("pb.vd"))
        self.assertEqual(len(new_cfg["gesellschaften"]), 2)
        pkg2 = copy.deepcopy(pkg); pkg2["config"]["darlehen"][0]["darlehenskonto"] = "Darlehen Fremd"
        _, unresolved, _ = core.import_package(core.merged_config({}), pkg2, led, "ergaenzen")
        self.assertEqual(len(unresolved), 1); self.assertEqual(unresolved[0]["label"], "Darlehen Fremd")
        new_cfg, unresolved, _ = core.import_package(core.merged_config({}), pkg2, led, "ergaenzen", {"Darlehen Fremd": F.uid("pb.vd") + " | Verkäuferdarlehen"})
        self.assertEqual(unresolved, []); self.assertIn(F.uid("pb.vd"), new_cfg["darlehen"][0]["darlehenskonto"])
        again, _, _ = core.import_package(new_cfg, pkg, led, "ergaenzen")
        self.assertEqual(len(again["darlehen"]), 1)

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
        self.assertIn("aktuell", info)
        self.assertTrue(info["fehler"] or info["verfuegbar"])
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
        self.assertEqual(info["verfuegbar"], "9.9.9"); self.assertTrue(info["neuer"]); self.assertEqual(info["quelle"], "main")
        self.assertEqual(info["zip"], "https://github.com/stecrz/Kontor/archive/refs/heads/main.zip")
        self.assertEqual(info["notizen"], "- Neu A\n- Neu B")

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
        self.assertEqual(info["verfuegbar"], "v10.0.0"); self.assertEqual(info["quelle"], "tag")
        self.assertEqual(info["zip"], "https://github.com/stecrz/Kontor/archive/refs/tags/v10.0.0.zip")
        self.assertEqual(updates.archive_url("a/b", "main", "heads"), "https://github.com/a/b/archive/refs/heads/main.zip")
        self.assertIsNone(updates.install_via_git(restart=False)) if not os.path.isdir(os.path.join(updates.HERE, ".git")) else None

    def test_update_install_from_archive(self):
        """Archiv wie von GitHub (Wurzelordner mit kontor.py + VERSION) wird in den Programmordner eingespielt, Sicherung unter .alt."""
        src = os.path.join(os.path.dirname(__file__), "..")
        prog = os.path.join(self.dir, "prog")
        shutil.copytree(src, prog, ignore=shutil.ignore_patterns("tests", "__pycache__", ".git", ".alt"))
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
        self.assertTrue(os.path.exists(os.path.join(prog, ".alt", "VERSION")))
        self.assertEqual(open(os.path.join(prog, ".alt", "VERSION")).read().strip(), updates.current_version())
        self.assertFalse(os.path.exists(os.path.join(prog, "tests")))


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
            self.assertTrue(st["gefunden"]); self.assertFalse(st["verbunden"]); self.assertIn("GUI failed", st["fehler"])
            d, p = self.fake('echo \'{"BackendState": "NeedsLogin", "Self": {}}\'\n')
            tls_cert.find_tailscale = lambda: p
            st = tls_cert.status()
            self.assertFalse(st["verbunden"]); self.assertEqual(st["zustand"], "NeedsLogin"); self.assertNotIn("fehler", st)
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
            self.assertTrue(st["verbunden"]); self.assertEqual((st["name"], st["ip"]), ("mac.example.ts.net", "100.101.102.103"))
            self.assertTrue(st["https"]); self.assertEqual(st["geraete"][0]["name"], "iPhone")
            self.assertEqual(seen[0][1], "local-tailscaled.sock")
            d = tempfile.mkdtemp(prefix="kontor-tls-")
            crt, key = tls_cert.issue(None, "mac.example.ts.net", d)
            self.assertIn("BEGIN CERTIFICATE", open(crt).read()); self.assertIn("PRIVATE KEY", open(key).read())
            self.assertEqual(os.stat(key).st_mode & 0o777, 0o600)
            # which ports Tailscale lets in: default -> everything open; Kontor's rule -> only Kontor; wrong port -> Kontor blocked
            a = tls_cert.access_check(8765); self.assertEqual(a["zustand"], "offen"); self.assertTrue(a["alle"])
            rules[0] = [{"SrcIPs": ["100.64.0.0/10"], "DstPorts": [{"IP": "100.101.102.103", "Ports": {"First": 8765, "Last": 8765}}]}]
            self.assertEqual(tls_cert.access_check(8765)["zustand"], "abgesichert")
            self.assertEqual(tls_cert.access_check(9000)["zustand"], "gesperrt")
            rules[0].append({"SrcIPs": ["*"], "DstPorts": [{"IP": "*", "Ports": {"First": 22, "Last": 22}}]})
            a = tls_cert.access_check(8765); self.assertEqual((a["zustand"], a["alle"], a["ports"]), ("offen", False, [[22, 22]]))
            tls_cert.localapi_endpoint = lambda: (srv.server_address[1], "wrong")   # wrong token: message, no crash
            self.assertEqual(tls_cert.access_check(8765)["zustand"], "unbekannt")
            st = tls_cert.status()
            self.assertFalse(st["verbunden"]); self.assertIn("401", st["fehler"])
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
        cfg2 = dict(self.cfg, bilanz=dict(self.cfg["bilanz"], monate_zurueck=6))
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
        app.config = {"zeitplan": {"voll_lesen_tage": 7}}
        app.ledger = None
        self.assertTrue(app.full_read_due())
        app.ledger = type("L", (), {})(); app.ledger.full_at = dt(2026, 11, 4, 15, 0)
        self.assertFalse(app.full_read_due(dt(2026, 11, 5, 3, 0)))            # nachts: kein Sonderfall mehr
        self.assertFalse(app.full_read_due(dt(2026, 11, 11, 14, 0)))          # knapp 7 Tage
        self.assertTrue(app.full_read_due(dt(2026, 11, 11, 15, 0)))           # 7 Tage
        app.config = {}
        self.assertEqual(app.full_read_info()["tage"], 7)                      # Standard

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


class _AppBase(unittest.TestCase):
    """Gemeinsamer Aufbau: Dienst auf freiem Port, Cookie-Jar, CSRF."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-app-")
        key, src = load_or_create_master_key(self.dir)
        self.store = Store(self.dir, key, src)
        self.belege = os.path.join(self.dir, "Belege")
        self.store.save("config.json", config_for_test(self.belege))
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
        if warten and isinstance(body, dict) and "warten" not in body:
            body = {**body, "warten": True}        # Tests warten auf den Berichtsneubau (Oberflaeche: im Hintergrund)
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
        self.assertTrue(s["einrichtung_noetig"])
        code, r = self.call("/api/setup", {"passwort": "kurz"})
        self.assertEqual(code, 400)
        code, r = self.call("/api/setup", {"passwort": "sehr-geheimes-passwort"})
        self.assertEqual(code, 200); self.csrf = r["csrf"]

    def run_and_wait(self):
        code, r = self.call("/api/run", {"probelauf": False, "force": True})
        self.assertEqual(code, 202)
        for _ in range(200):
            time.sleep(0.1)
            if not self.app.running and self.app.last_run_at:
                break


class AppTests(_AppBase):
    """Dienst ueber HTTP: Einrichtung, Anmeldung, CSRF, Daten, Plan, Konfiguration, Lauf, Belege, Exporte."""

    def test_unchanged_read_keeps_warm_state(self):
        """Unveraenderte Daten aus MoneyMoney: bisheriger Stand (mit Zwischenergebnissen) bleibt, nur der Lesezeitpunkt wird neu."""
        self.login(); self.run_and_wait()
        self.assertFalse(self.app.full_read_due())   # own bookings need no full read: the ledger keeps them until the next one
        led, t0 = self.app.ledger, self.app.ledger_time
        self.app.do_run(True, False)                 # after own bookings: a quick read is enough
        led = self.app.ledger
        self.assertFalse(self.app.full_read_due()); self.assertTrue(led.incremental)
        # the bookings written back to January come from the kept ones (the quick read sees 30 days): nothing proposed again
        self.assertTrue(any(t.id <= 0 and "#mm-zins-2026-01" in t.purpose for t in led.txs))
        again = self.app.do_run(True, True); self.assertEqual(again["vorschlaege"], []); self.assertTrue(self.app.ledger.incremental)
        led = self.app.ledger
        time.sleep(0.01)
        self.assertEqual(self.app.do_run(None, False)["status"], "unveraendert")
        self.assertIs(self.app.ledger, led); self.assertGreater(self.app.ledger_time, t0)
        self.app.refresh_ledger(); self.assertIs(self.app.ledger, led)
        # Bankabruf ohne neue Daten: keine Neuberechnung, aber die Abrufzeit ist aktuell
        giro = next(a for a in MockBridge.state["accounts"] if a["uuid"] == F.uid("priv.giro"))
        vorher = led.accounts[F.uid("priv.giro")].refresh
        giro["refreshTimestamp"] = F._dt(date(2026, 11, 3))
        self.assertEqual(self.app.do_run(None, False)["status"], "unveraendert")
        self.assertIs(self.app.ledger, led); self.assertNotEqual(led.accounts[F.uid("priv.giro")].refresh, vorher)
        MockBridge.state["accounts"][-1]["name"] += " neu"     # Kontoname geaendert -> neuer Stand
        self.assertNotEqual(self.app.do_run(None, False)["status"], "unveraendert")
        self.assertIsNot(self.app.ledger, led)

    def test_kategorien_zurueckschreiben(self):
        """Zurueckschreiben nach MoneyMoney: fehlende Kategorie wartet und wird nachgetragen, eigene Kategorie ohne Rueckfrage
        aenderbar, abweichender Umsatz wird nicht beschrieben, von unterwegs nur in Kontor."""
        import mm_categories
        self.login(); self.run_and_wait()
        cfg = copy.deepcopy(self.app.config); cfg.setdefault("moneymoney", {})["kategorisieren_erlauben"] = True; self.app.save_config(cfg)
        sets = lambda: [w for b in MockBridge.instances for w in b.written if w[0] == "set" and w[2] is not None]
        # ohne Kategorie in MoneyMoney: Bauhaus-Umsaetze (Kategorie fehlt in MoneyMoney -> wartet)
        MockBridge.state["txs"] += [F.tx("priv.giro", date(2026, 10, 20), -80.0, "Bauhaus", "Werkzeug"),
                                    F.tx("priv.giro", date(2026, 10, 27), -35.0, "Bauhaus", "Schrauben")]
        self.app.do_run(True, False, full=True)
        ids = [t.id for t in self.app.ledger.txs if t.name == "Bauhaus"]
        code, r = self.call("/api/categories/assign", {"ids": ids, "kategorie": "Haushalt / Werkzeug", "warten": True})
        self.assertEqual((r["mm"]["geschrieben"], r["mm"]["wartet"]), (0, 2)); self.assertFalse(sets())
        code, off = self.call("/api/categories/unassigned")
        self.assertEqual(off["wartend"], [{"kategorie": "Haushalt / Werkzeug", "anzahl": 2}])
        # in MoneyMoney angelegt -> beim naechsten Lesen nachgetragen (per UUID)
        MockBridge.extra_cats = [("Haushalt", 0, True, {}), ("Werkzeug", 1, False, {})]
        self.app.do_run(True, False)
        self.assertEqual(sorted(w[1] for w in sets()), sorted(ids)); self.assertTrue(all(w[2] == F.uid("cat:Werkzeug") for w in sets()))
        self.assertFalse([z for z in categorize.load(self.store)["zuordnung"].values() if z.get("w")])
        self.assertEqual(categorize.mm_of(next(t for t in self.app.ledger.txs if t.id == ids[0])), "Haushalt / Werkzeug")
        # von Kontor geschrieben -> erneut aenderbar ohne Rueckfrage
        MockBridge.extra_cats.append(("Garten", 1, False, {}))
        self.app.categories_raw = mm_categories.with_paths(MockBridge().export_categories())
        code, r = self.call("/api/categories/assign", {"ids": ids[:1], "kategorie": "Haushalt / Garten", "warten": True})
        self.assertEqual((r["mm"]["geschrieben"], r["mm"]["fremd"]), (1, []))
        # in MoneyMoney geaendert (anderer Betrag) -> nicht schreiben, bleibt in Kontor
        raw = next(t for t in MockBridge.state["txs"] if t["id"] == ids[1]); raw["amount"] = -36.0
        n = len(sets())
        code, r = self.call("/api/categories/assign", {"ids": ids[1:], "kategorie": "Haushalt / Garten", "warten": True})
        self.assertEqual((r["mm"]["geschrieben"], r["mm"]["fehler"]), (0, 1)); self.assertEqual(len(sets()), n)
        # von unterwegs (nicht vom Mac): nur in Kontor
        orig = self.app.mm_write_allowed
        self.app.mm_write_allowed = lambda local: False
        try:
            code, r = self.call("/api/categories/assign", {"ids": ids[:1], "kategorie": "Haushalt / Werkzeug", "warten": True})
            self.assertTrue(r["mm"]["aus"]); self.assertEqual(len(sets()), n)
            self.assertTrue(categorize.load(self.store)["zuordnung"][str(ids[0])].get("ov"))
        finally:
            self.app.mm_write_allowed = orig

    def test_kategorien_auswahl(self):
        """Einrichtung -> Kategorien auswaehlen: zusammenfassen (Kapitalfluss-Zeile = Oberkategorie, Steuer unveraendert) und
        nicht verwenden (in Kontor ohne Kategorie, erscheint unter Zuordnen); MoneyMoney bleibt unberuehrt."""
        self.login(); self.run_and_wait()
        def zeilen():
            ds = self.store.load("dataset.json")
            return {z["zeile"] for b in ds["bereiche"].values() for sek in b["kapitalfluss"]["sektionen"] for z in sek["zeilen"]}
        self.assertIn("Vermietung / Parkweg / Mieteinnahmen", zeilen()); self.assertIn("Wohnen / Miete", zeilen())
        steuer_vorher = json.dumps(self.store.load("dataset.json")["steuer"], sort_keys=True)
        code, off = self.call("/api/categories/unassigned"); offen_vorher = off["offen"]
        code, r = self.call("/api/categories/usage", {"verwendung": {"Vermietung / Parkweg": "zusammen", "Wohnen": "zusammen"}, "warten": True})
        self.assertEqual(code, 200)
        z = zeilen()
        self.assertIn("Vermietung", z); self.assertFalse([x for x in z if "Parkweg" in x])
        self.assertIn("Wohnen / Miete", z)                                                  # oberste Ebene nicht zusammenfassbar
        self.assertEqual(json.dumps(self.store.load("dataset.json")["steuer"], sort_keys=True), steuer_vorher)   # Steuer: genaue Kategorie
        code, r = self.call("/api/categories/usage", {"verwendung": {"Vermietung / Parkweg": "zusammen", "Wohnen": "zusammen",
                                                                   "Lebensmittel": "ignorieren", "Einnahmen / Gehalt": "zeile"}, "warten": True})
        self.assertEqual(r["verwendung"], {"Vermietung / Parkweg": "zusammen", "Lebensmittel": "ignorieren"})
        code, off = self.call("/api/categories/unassigned")
        self.assertGreater(off["offen"], offen_vorher); self.assertIn("Supermarkt", [g["name"] for g in off["gruppen"]])
        code, k = self.call("/api/categories/kontor"); self.assertEqual(k["verwendung"]["Lebensmittel"], "ignorieren")
        self.assertGreater(k["anzahl"]["Lebensmittel"], 0)
        self.assertFalse([w for b in MockBridge.instances for w in b.written if w[0] == "set" and w[2] is not None])
        self.assertEqual(self.store.load("dataset.json")["kategorien"]["verwendung"], 2)

    def test_zugriff_vom_iphone(self):
        """Zugriff von anderen Geraeten: Stand, Ein-/Ausschalten nur am Mac, von unterwegs nur ansehen (Standard),
        Offline-Kopie abschaltbar."""
        import service as MA
        self.login(); self.run_and_wait()
        code, r = self.call("/api/remote")
        self.assertEqual(code, 200); self.assertFalse(r["aktiv"]); self.assertTrue(r["nur_ansehen"]); self.assertTrue(r["offline_kopie"]); self.assertTrue(r["lokal"])
        # ohne Tailscale: Einschalten scheitert mit Hinweis, nichts geaendert
        self.app._ts_cache = (time.time() + 999, {"gefunden": False})
        orig_status = MA.App.tailscale
        MA.App.tailscale = lambda app, fresh=False: {"gefunden": False}
        try:
            code, r = self.call("/api/remote", {"aktion": "ein"})
            self.assertFalse(r["ok"]); self.assertEqual(self.app.config["oberflaeche"]["bind"], "127.0.0.1")
            # mit Tailscale (verbunden), ohne Zertifikat
            MA.App.tailscale = lambda app, fresh=False: {"gefunden": True, "verbunden": True, "ip": "100.101.102.103", "name": "mac.example.ts.net", "https": False, "geraete": []}
            code, r = self.call("/api/remote", {"aktion": "ein_http"})
            self.assertTrue(r["ok"]); self.assertFalse(r["neustart"])                     # im Test kein echter Neustart
            self.assertEqual(self.app.config["oberflaeche"]["bind"], "100.101.102.103")
            self.assertEqual(r["info"]["url"], "http://100.101.102.103:8765/"); self.assertTrue(r["info"]["aktiv"])
            code, r = self.call("/api/remote", {"aktion": "aus"})
            self.assertEqual(self.app.config["oberflaeche"]["bind"], "127.0.0.1")
        finally:
            MA.App.tailscale = orig_status
        # von unterwegs (nicht vom Mac): Stand ja, Aenderungen nein (Standard "nur ansehen")
        orig = MA.auth.is_loopback
        MA.auth.is_loopback = lambda remote: False
        try:
            self.assertEqual(self.call("/api/remote")[1]["lokal"], False)
            code, r = self.call("/api/plan", {"bereich": F.uid("priv"), "zeile": "Einnahmen/Einnahmen / Gehalt", "methode": "fix", "betrag": "1"})
            self.assertEqual(code, 403); self.assertIn("nur ansehen", r["fehler"])
            self.assertEqual(self.call("/api/remote", {"aktion": "aus"})[0], 403)
        finally:
            MA.auth.is_loopback = orig
        code, r = self.call("/api/remote", {"aktion": "einstellungen", "fern_nur_ansehen": False, "offline_kopie": False})
        self.assertTrue(r["ok"]); self.assertFalse(r["info"]["nur_ansehen"])
        MA.auth.is_loopback = lambda remote: False
        try:
            code, r = self.call("/api/plan", {"bereich": F.uid("priv"), "zeile": "Einnahmen/Einnahmen / Gehalt", "methode": "fix", "betrag": "1"})
            self.assertEqual(code, 200)                                                    # bearbeiten erlaubt
            self.assertIsNone(self.call("/api/offline/verifier")[1]["offline"])            # keine Offline-Kopie
            self.assertFalse(self.call("/api/session")[1]["offline_kopie"])
            # even with editing allowed: no receipts folder, no file questions, no live run from elsewhere
            cfg = copy.deepcopy(self.app.config); cfg.setdefault("belege", {})["ordner"] = "/"
            self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 403)
            cfg["belege"] = dict(self.app.config.get("belege") or {}, unterordner="../../{jahr}")
            self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 403)
            self.assertEqual(self.call("/api/file/status?path=" + self.dir)[0], 403)
            runs = []; orig_run = self.app.do_run
            self.app.do_run = lambda dry, force, **kw: runs.append(dry)
            try:
                self.assertEqual(self.call("/api/run", {})[0], 202); time.sleep(0.2)
                self.assertEqual(self.call("/api/run", {"probelauf": False})[0], 403)
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
            cfg["oberflaeche"]["port"] = busy.getsockname()[1]
            code, r = self.call("/api/config", {"config": cfg}, method="PUT")
            self.assertEqual(code, 409); self.assertIn(str(busy.getsockname()[1]), r["fehler"])
        finally:
            busy.close()
        cfg["oberflaeche"]["port"] = 80
        self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 400)
        free = socket.socket(); free.bind(("127.0.0.1", 0)); port = free.getsockname()[1]; free.close()
        cfg["oberflaeche"]["port"] = port
        orig = MA.auth.is_loopback
        MA.auth.is_loopback = lambda remote: False
        try:
            self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 403)    # not from the iPhone
        finally:
            MA.auth.is_loopback = orig
        code, r = self.call("/api/config", {"config": cfg}, method="PUT")
        self.assertEqual(code, 200); self.assertEqual(r["port"], port); self.assertTrue(r["instanz"])
        self.assertFalse(r["neustart"])                                                       # no real restart in tests
        self.assertEqual(self.app.config["oberflaeche"]["port"], port)
        self.assertEqual(self.call("/api/session")[1]["instanz"], r["instanz"])

    def test_abruf_offline_erkennung(self):
        """MoneyMoney setzt den Abrufzeitpunkt auch bei Offline-Konten: Regelziele und Konten ohne Nummern zaehlen nicht fuer den Datenstand."""
        self.login(); self.run_and_wait()
        led = copy.deepcopy(self.app.ledger)
        neu = max(a.refresh for a in led.accounts.values() if a.refresh)
        for key in ("pb.vd", "priv.bet.pb"):                 # Regelziele mit Zeitstempel (wie nach einer Buchung)
            led.accounts[F.uid(key)].refresh = neu - timedelta(days=20)
        led.fp = "x"; self.app.ledger = led
        kinds = core.abruf_arten(led, self.app.config)
        self.assertEqual(kinds[F.uid("pb.vd")]["art"], "offline"); self.assertEqual(kinds[F.uid("pb.vd")]["grund"], "Offline-Konto")
        self.assertEqual(kinds[F.uid("priv.bet.pb")]["art"], "offline")
        self.assertEqual(kinds[F.uid("priv.giro")]["art"], "online"); self.assertEqual(kinds[F.uid("priv.depot")]["art"], "online")
        self.assertEqual(self.app.bankabruf()["zurueck_anzahl"], 0)
        code, r = self.call("/api/sync"); self.assertEqual(code, 200)
        self.assertEqual([k["uuid"] for k in r["konten"]][:3], [a.uuid for a in led.accounts.values() if not a.group and a.path][:3])   # Reihenfolge wie MoneyMoney
        self.assertTrue(r["gelesen"]); self.assertIn("bereich", r["konten"][0])
        # eigene Festlegung: Giro nicht abgerufen -> offline; zurueck -> wieder erkannt
        code, r = self.call("/api/sync", {"konto": F.uid("priv.giro"), "abgerufen": False}); self.assertEqual(code, 200)
        self.assertEqual([k for k in r["abruf"]["konten"] if k["uuid"] == F.uid("priv.giro")][0]["art"], "offline")
        self.assertEqual(len(self.store.load("config.json")["abruf"]["offline"]), 1)
        self.call("/api/sync", {"konto": F.uid("priv.giro"), "abgerufen": True})
        self.assertEqual(self.store.load("config.json")["abruf"], {"online": [], "offline": []})
        # Kontenliste in der Reihenfolge von MoneyMoney (nicht alphabetisch)
        code, k = self.call("/api/accounts")
        self.assertEqual([x["uuid"] for x in k["konten"]], [a.uuid for a in led.accounts.values() if a.path])
        self.assertEqual([x for x in k["konten"] if x["uuid"] == F.uid("priv.giro")][0]["rolle_vorschlag"], "liquiditaet")

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
            gaps = st.get("luecken") or []
            self.assertEqual(len(gaps), 1); self.assertEqual(gaps[0]["konto"], F.uid("priv.depot")); self.assertEqual(gaps[0]["monate"][0], "2026-09")
            code, r = self.call("/api/sync"); self.assertEqual(len(r["luecken"]), 1)
            code, stt = self.call("/api/status"); self.assertEqual(stt["moneymoney"]["luecken"], 1)
            self.call("/api/sync/gaps", {}); self.assertFalse(self.store.load("state.json").get("luecken"))
            # unveraendert -> kein erneuter Abgleich; geaendert -> voller Abgleich wird angestossen
            self.app.mm_retry_at = None; self.app.capture(); self.assertIsNone(self.app.mm_retry_at)
            self.app.config.setdefault("zeitplan", {})["automatisch"] = True
            depot["balance"][0][0] += 1000; self.app.capture(); self.assertIsNotNone(self.app.mm_retry_at)
            import time as _t
            self.assertGreater(self.app.mm_retry_at, _t.time() + 30)            # erst wenn MoneyMoney fertig abgerufen hat
            self.app.do_run(True, force=False); self.assertIsNone(self.app.mm_retry_at)   # Lauf (Testmodus) hat den Stand gelesen
            self.app.capture(); self.assertIsNone(self.app.mm_retry_at)          # -> kein zweiter Lauf hinterher
            # Mac schlief (kein Abruf seit dem letzten Lauf) -> keine Meldung
            self.app.prev_seen = dt(2026, 11, 6, 12, 0); self.app._check_gaps(accounts_from_export(MockBridge.state["accounts"]))
            self.assertFalse(self.store.load("state.json").get("luecken"))
        finally:
            import mm_bridge as MB
            MA.is_running = MB.is_running

    def _mm_db(self, compat=None, mit_verlauf=True, passwort="ge'heim", zeit="unix", versatz=False, depot="wert"):
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
                    if depot in ("gesamt", "gesamt_frei"):     # zusaetzlicher Eintrag mit dem Depotwert insgesamt (bei manchen Depots in MoneyMoney)
                        sql.append("INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, %d);" % (i, ts(date(y, m, 20)), round(v + (5000.0 if (y, m) <= (2024, 6) else 0.0), 2), 900 + i))
                    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
                part = round(a.balance * 0.6, 2)
                if depot in ("gesamt", "gesamt_frei"):     # gesamt_frei: the total entry is no security of its own (e.g. Trade Republic)
                    sql += (["INSERT INTO securities VALUES(%d, %d, 1, 0, NULL);" % (900 + i, i)] if depot == "gesamt" else []) + [
                            "INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, %d);" % (i, ts(date(2026, 11, 3)), a.balance, 900 + i)]
                sql.append("INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, %d);" % (i, ts(date(2026, 11, 3)), part, 100 + i))
                sql.append("INSERT INTO portfolio_chart VALUES(%d, 'EUR', %d, %r, %d);" % (i, ts(date(2026, 11, 2)), round(a.balance - part, 2), 200 + i))
                continue
            per_day = {}
            for tx in led.transactions(a.uuid):
                per_day[tx.booking_date] = round(per_day.get(tx.booking_date, 0.0) + tx.amount, 2)
            if a.uuid == F.uid("pb.immo"):
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
        if res.get("laeuft"):
            for _ in range(600):
                time.sleep(0.05)
                c, st = self.call("/api/history/mm-status")
                if not st["laeuft"]:
                    return code, st["ergebnis"]
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
            self.assertEqual(r["konten"], n); self.assertEqual(r["depots"], 1); self.assertEqual((r["von"], r["bis"]), ("2024-01", "2026-10"))
            self.assertFalse(H.AKTIV.is_set()); self.assertFalse(os.path.exists(aufbau))
            self.assertFalse([f for f in os.listdir(self.dir) if f.startswith("kontor-") or f.endswith(".sqlite") and f != "MoneyMoney.sqlite"])
            mm = self.store.load(MM_HISTORY_FILE)["konten"]
            dep = mm[F.uid("priv.depot")]
            self.assertNotIn(F.uid("pb.immo"), mm)                                      # Punkte passen nicht zu den Umsaetzen: nicht uebernommen
            look = __import__("service").balance_lookup(self.app.ledger)
            for u in mm:                                                                # Monatsende = aktueller Saldo minus spaetere Veraenderungen
                if not self.app.ledger.accounts[u].portfolio:
                    self.assertEqual(mm[u]["2026-09"], look(u, date(2026, 9, 30), False))
            self.assertEqual(dep["2025-06"], 70000.27)                                 # Summe der gehaltenen Wertpapiere am Monatsende
            self.assertGreater(dep["2024-05"] - dep["2024-06"], 3000)          # verkauftes Wertpapier zaehlt nicht mehr im Monat seines letzten Werts
            self.assertEqual(self.store.load(MM_HISTORY_FILE)["anfang"][F.uid("priv.depot")], 0.0)   # vor der ersten Aufzeichnung: leer
            self.assertNotIn("2026-11", dep)                                            # laufender Monat kommt aus dem aktuellen Saldo
            with open(self.store.path(MM_HISTORY_FILE), "rb") as f:
                self.assertNotIn(b"70000", f.read())                                    # verschluesselt abgelegt
            self.assertEqual(self.store.load("state.json")["mm_verlauf"]["konten"], n)
            code, st = self.call("/api/status"); self.assertEqual(st["moneymoney"]["historie"]["depots"], 1)
            self.app.rebuild_report(wait=True)
            code, h = self.call("/api/history?account=" + F.uid("priv.depot"))
            self.assertEqual(h["werte"]["2025-06"], 70000.27); self.assertEqual(h["moneymoney"]["2025-06"], 70000.27)
            code, ab = self.call("/api/sync")
            d = next(x for x in ab["depots"] if x["uuid"] == F.uid("priv.depot")); self.assertEqual(d["erster_stand"], "2024-01"); self.assertTrue(d["aus_moneymoney"])
            # Bilanz nutzt die Werte
            code, ds = self.call("/api/dataset")
            row = next(z for b in ds["bereiche"].values() for z in b["bilanz"]["zeilen"] if z.get("id") == F.uid("priv.depot"))
            self.assertEqual(row["werte"]["2025-06"], 70000.27)
            self.assertIsNone(row.get("fortgeschrieben_vor"))                           # vor der Aufzeichnung leer, nicht "unbekannt"
            self.assertNotIn("fortgeschrieben", h.get("hinweis") or "")
            # Verlauf der Konten mit Umsaetzen passt nirgends (versetzt): nur das Depot wird uebernommen, die Konten behalten Kontors Salden
            code, r = self._mm_upload(self._mm_db(versatz=True)); self.assertTrue(r["ok"], r); self.assertEqual((r["konten"], r["depots"]), (1, 1))
            # aelteres Format (SQLCipher 3) und Cocoa-Zeit ebenso
            code, r = self._mm_upload(self._mm_db(compat=3, zeit="cocoa")); self.assertTrue(r["ok"], r); self.assertEqual(r["konten"], n)
            # Depot mit zusaetzlichem Gesamt-Eintrag (Summe doppelt): der Gesamt-Eintrag gilt
            for variant in ("gesamt", "gesamt_frei"):     # with the total entry as a security of its own or not: never counted twice
                code, r = self._mm_upload(self._mm_db(depot=variant)); self.assertTrue(r["ok"], r); self.assertEqual(r["depots"], 1)
                gd = self.store.load(MM_HISTORY_FILE)["konten"][F.uid("priv.depot")]
                self.assertEqual(gd["2025-06"], 70000.27, variant); self.assertGreater(gd["2024-06"] - gd["2024-07"], 3000)
            # Depot als Wertveraenderung je Wertpapier ebenso
            code, r = self._mm_upload(self._mm_db(depot="delta")); self.assertTrue(r["ok"], r); self.assertEqual(r["depots"], 1)
            self.assertEqual(self.store.load(MM_HISTORY_FILE)["konten"][F.uid("priv.depot")]["2025-06"], 70000.27)
            # ohne Verlaufstabelle: nichts uebernommen, nur der Aufbau (Namen, keine Inhalte) als Hinweis
            code, r = self._mm_upload(self._mm_db(mit_verlauf=False)); self.assertFalse(r["ok"]); self.assertIn("nicht sicher erkannt", r["text"])
            txt = open(aufbau, encoding="utf-8").read()
            self.assertIn("transactions", txt); self.assertNotIn("GEHEIM", txt); self.assertNotIn("Text 1", txt)
            self.assertEqual(self.store.load(MM_HISTORY_FILE)["konten"][F.uid("priv.depot")]["2025-06"], 70000.27)    # bisherige Werte bleiben
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
        self.assertEqual(next(z for b in ds["bereiche"].values() for z in b["bilanz"]["zeilen"] if z.get("id") == "pos:verbindlichkeiten")["name"], "Verbindlichkeiten")
        self.assertEqual(self.call("/api/language", {"sprache": "xx"})[0], 400)
        code, r = self.call("/api/language", {"sprache": "en"}); self.assertEqual(r["sprache"], "en")
        self.assertEqual(self.store.load("config.json")["oberflaeche"]["sprache"], "en")
        self.app.rebuild_report(wait=True)
        code, ds = self.call("/api/dataset")
        self.assertEqual(next(z for b in ds["bereiche"].values() for z in b["bilanz"]["zeilen"] if z.get("id") == "pos:verbindlichkeiten")["name"], "Liabilities")
        old = MA.is_running; MA.is_running = lambda: True
        try:
            code, r = self._mm_upload(b"x" * 2048); self.assertIn("Please quit MoneyMoney first", r["text"])
        finally:
            MA.is_running = old
        code, r = self.call("/api/language", {"sprache": "de"})
        code, r = self.call("/api/properties", {"aktion": "speichern", "id": "gibtsnicht"}); self.assertIn("nicht gefunden", json.dumps(r, ensure_ascii=False))

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
            seen["gleich"] = b is buf
            orig(self_, b)
        H.MemDB.__init__ = spy
        try:
            found, tables, fmt = H.run(buf, {"x": {"saldo": 1.0, "depot": False, "name": "x"}}, date(2026, 11, 4), keys_fn=keys)
        finally:
            H.MemDB.__init__ = orig
        self.assertIsNone(found); self.assertEqual(tables[0]["name"], "t"); self.assertEqual(fmt, "SQLCipher 4")
        self.assertTrue(seen["klartext"]); self.assertTrue(seen["gleich"])          # im selben Puffer entschluesselt
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
            code, st = self.call("/api/status"); self.assertIn("Berechtigung", st["moneymoney"]["problem"]["text"])
            MockBridge.export_accounts = orig
            self.app.capture()
            code, st = self.call("/api/status"); self.assertIsNone(st["moneymoney"]["problem"])
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
        self.assertEqual(ba["zurueck_anzahl"], 1); self.assertEqual(ba["zurueck"][0]["name"], "Hausbank Giro")
        self.assertEqual(ba["neuester"], neu.strftime("%Y-%m-%d %H:%M"))

    def test_auth_and_api_flow(self):
        self.assertEqual(self.call("/api/status")[0], 401)
        self.login()
        self.assertEqual(self.call("/api/setup", {"passwort": "noch-ein-passwort-123"})[0], 403)
        self.assertEqual(self.call("/api/run", {"probelauf": True}, csrf=False)[0], 403)
        self.assertEqual(self.call("/api/run", {"probelauf": True}, origin="http://evil.example")[0], 403)
        # DNS rebinding: a foreign name pointing to 127.0.0.1 gets nothing; *.localhost and localhost are fine
        import http.client
        for host, want in (("evil.example:%d" % self.port, 421), ("kontor.localhost:%d" % self.port, 200), ("localhost:%d" % self.port, 200)):
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5); c.request("GET", "/", headers={"Host": host})
            self.assertEqual(c.getresponse().status, want, host); c.close()
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("POST", "/api/login", body=b"{}", headers={"Host": "evil.example", "Origin": "http://evil.example", "Content-Type": "application/json"})
        self.assertEqual(c.getresponse().status, 403); c.close()
        code, st = self.call("/api/status")
        self.assertEqual(code, 200); self.assertTrue(st["ablage"]["verschluesselt"]); self.assertIn("version", st)
        code, ds = self.call("/api/dataset")
        self.assertTrue(ds["leer"])
        self.run_and_wait()
        code, runs = self.call("/api/runs")
        self.assertEqual(runs["letzter_lauf"]["geschrieben"], 35)
        code, st = self.call("/api/status")
        mm = st["moneymoney"]
        self.assertNotIn("naechster_lauf", st["dienst"]); self.assertNotIn("aktualisieren_erlaubt", mm)
        self.assertTrue(mm["stand"]); self.assertEqual(mm["bankabruf"]["zurueck_anzahl"], 0)
        self.assertRegex(mm["bankabruf"]["neuester"], r"^2026-11-0[34] \d\d:00$")       # Fixture: Abruf 04.11. (Ortszeit)
        code, ds = self.call("/api/dataset")
        self.assertEqual(ds["haupt"], F.uid("priv")); self.assertEqual(len(ds["bereiche"]), 3)
        b = ds["bereiche"][ds["haupt"]]
        self.assertIn("kennzahlen", b); self.assertIn("plan", b); self.assertTrue(b["plan_monate"])
        self.assertEqual(b["plan"]["inflation_prozent_pa"], 2.0)
        code, k = self.call("/api/accounts")
        self.assertTrue(any(x["name"] == "Verkäuferdarlehen" and x["manuell"] for x in k["konten"]))
        self.assertTrue(any(x["name"] == "Hausbank Giro" and not x["manuell"] for x in k["konten"]))
        code, kats = self.call("/api/categories")
        self.assertTrue(any(c["pfad"] == "Vermietung / Parkweg / Mieteinnahmen" for c in kats["kategorien"]))
        # Plan je Bereich: Methode, Ueberschreibung, Parameter, Darlehen, Wertentwicklung
        P = ds["haupt"]
        code, r = self.call("/api/plan", {"bereich": P, "zeile": "Einnahmen/Einnahmen / Gehalt", "methode": "fix", "betrag": "7000", "steigerung": "2"})
        self.assertEqual(code, 200)
        self.call("/api/plan", {"bereich": P, "zeile": "Einnahmen/Einnahmen / Gehalt", "monat": "2027-01", "wert": "9000"})
        self.call("/api/plan", {"bereich": P, "parameter": {"horizont_monate": 36, "inflation_prozent_pa": 3},
                                "darlehen": {"Darlehen Lindenstraße": {"zins_prozent_pa": "3.6", "modell": "restschuld_monatlich", "zahlung": ""}},
                                "wertentwicklung": {"Immobilie Lindenstraße": {"prozent_pa": "1.5", "basis": ""}}})
        code, ds = self.call("/api/dataset")
        b = ds["bereiche"][P]
        self.assertEqual(len(b["plan_monate"]), 37); self.assertEqual(b["plan_monate"][-1][5:], "12")    # 36 Monate, bis Jahresende aufgefuellt
        self.assertEqual(b["plan"]["inflation_prozent_pa"], 3)
        gz = [z for z in b["kapitalfluss"]["sektionen"][0]["zeilen"] if z["zeile"] == "Einnahmen / Gehalt"][0]
        self.assertEqual(gz["plan"]["werte"]["2027-01"], 9000.0)
        self.assertAlmostEqual(gz["plan"]["vorschlag"]["2027-01"], round(7000 * 1.02 ** (2 / 12), 2), 2)
        self.assertEqual(gz["plan"]["ueberschrieben"], ["2027-01"])
        fz = {z["zeile"]: z for z in [s for s in b["kapitalfluss"]["sektionen"] if s["name"] == "Finanzierung"][0]["zeilen"]}
        self.assertEqual(fz["Darlehen Lindenstraße / Zinsen"]["plan"]["methode"], "darlehen")
        # Ausgaben folgen der Inflation (3 %)
        mz = [z for z in [s for s in b["kapitalfluss"]["sektionen"] if s["name"] == "Ausgaben"][0]["zeilen"] if "Miete" in z["zeile"]][0]
        self.assertEqual(mz["plan"]["steigerung_prozent_pa"], 3.0)
        # Budget-Methode
        self.call("/api/plan", {"bereich": P, "zeile": "Ausgaben/" + mz["zeile"], "methode": "budget"})
        code, ds = self.call("/api/dataset")
        mz2 = [z for z in [s for s in ds["bereiche"][P]["kapitalfluss"]["sektionen"] if s["name"] == "Ausgaben"][0]["zeilen"] if "Miete" in z["zeile"]][0]
        self.assertEqual(mz2["plan"]["methode"], "budget"); self.assertAlmostEqual(mz2["plan"]["vorschlag"][b["plan_monate"][0]], round(-1500.0 * 1.03 ** (1 / 12), 2), 2)
        # anderer Bereich hat eigenen (leeren) Plan
        code, plan_pb = self.call("/api/plan?area=" + F.uid("pb"))
        self.assertEqual(plan_pb, {})
        self.assertEqual(len(ds["bereiche"][F.uid("pb")]["plan_monate"]), 25)       # 24 Monate, bis Jahresende aufgefuellt
        self.call("/api/plan", {"bereich": P, "zeile": "Einnahmen/Einnahmen / Gehalt", "alle_ueberschreibungen_loeschen": True})
        code, ds = self.call("/api/dataset")
        gz = [z for z in ds["bereiche"][P]["kapitalfluss"]["sektionen"][0]["zeilen"] if z["zeile"] == "Einnahmen / Gehalt"][0]
        self.assertEqual(gz["plan"]["werte"]["2027-01"], gz["plan"]["vorschlag"]["2027-01"])
        # Konfiguration: Fehler wird abgewiesen, gueltige gespeichert, bind geprueft
        code, cfg = self.call("/api/config")
        bad = copy.deepcopy(cfg); bad["darlehen"][0]["darlehenskonto"] = F.uid("priv.giro") + " | Hausbank Giro"
        code, r = self.call("/api/config", {"config": bad}, method="PUT")
        self.assertEqual(code, 409); self.assertTrue(any(f["stufe"] == "fehler" for f in r["befunde"]))
        good = copy.deepcopy(cfg); good["probelauf"] = True; good["oberflaeche"]["bind"] = "0.0.0.0"
        self.assertEqual(self.call("/api/config", {"config": good}, method="PUT")[0], 400)
        good["oberflaeche"]["bind"] = "100.100.1.2"
        code, r = self.call("/api/config", {"config": good}, method="PUT")
        self.assertEqual(code, 200); self.assertTrue(r["config"]["probelauf"])
        self.assertTrue(self.store.load("config.json")["probelauf"])
        self.assertTrue(any(e["name"] == "Alpha GbR" for e in ds["steuer"]["entitaeten"]))
        # Passwort aendern, abmelden, erneut anmelden; Fehlversuche sperren
        self.assertEqual(self.call("/api/password", {"alt": "falsch", "neu": "neues-passwort-123"})[0], 401)
        self.assertEqual(self.call("/api/password", {"alt": "sehr-geheimes-passwort", "neu": "neues-passwort-123"})[0], 200)
        self.assertEqual(self.call("/api/lock", {})[0], 200)
        self.assertEqual(self.call("/api/status")[0], 401)
        for _ in range(5):
            self.assertEqual(self.call("/api/login", {"passwort": "falsch"})[0], 401)
        self.assertEqual(self.call("/api/login", {"passwort": "neues-passwort-123"})[0], 429)
        self.app.sessions.clear_fails("127.0.0.1")
        code, r = self.call("/api/login", {"passwort": "neues-passwort-123"})
        self.assertEqual(code, 200)
        self.assertEqual(self.call("/api/touchid", {})[0], 403)
        with self.opener.open("http://127.0.0.1:%d/" % self.port) as r:
            self.assertIn("Kontor", r.read().decode()); self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])

    def test_umsaetze_belege_exports(self):
        self.login(); self.run_and_wait()
        code, u = self.call("/api/transactions?year=2026&uncategorized=1&limit=5")
        self.assertEqual(code, 200); self.assertTrue(u["treffer"] >= 10); self.assertEqual(len(u["umsaetze"]), 5)
        self.assertTrue(all(not x["kategorie"] for x in u["umsaetze"]))
        code, u = self.call("/api/transactions?q=supermarkt&entity=" + F.uid("priv"))
        self.assertTrue(u["umsaetze"]); self.assertTrue(all("Supermarkt" in x["name"] for x in u["umsaetze"]))
        tx = u["umsaetze"][0]
        pdf = b"%PDF-1.4 test"
        # Erster Beleg: Ordner wird erst nach Rueckfrage angelegt
        code, r = self.call("/api/receipts/upload", {"tx_id": tx["id"], "datei_name": "rechnung.pdf", "inhalt": base64.b64encode(pdf).decode(), "notiz": "Test"})
        self.assertEqual(code, 409); self.assertTrue(r["ordner_bestaetigen"]); self.assertFalse(os.path.isdir(self.belege))
        code, r = self.call("/api/receipts/upload", {"tx_id": tx["id"], "datei_name": "rechnung.pdf", "inhalt": base64.b64encode(pdf).decode(), "notiz": "Test", "ordner_anlegen": True})
        self.assertTrue(self.store.load("config.json")["belege"]["ordner_bestaetigt"])
        self.assertEqual(code, 200, r)
        e = r["eintrag"]
        self.assertTrue(e["pfad"].startswith(tx["datum"][:4] + "/Privat/"), e["pfad"]); self.assertTrue(e["pfad"].endswith(".pdf"))
        self.assertTrue(os.path.isfile(os.path.join(self.belege, e["pfad"])))
        self.assertEqual(self.call("/api/receipts/upload", {"tx_id": tx["id"], "datei_name": "x.exe", "inhalt": base64.b64encode(b"x").decode()})[0], 400)
        code, u2 = self.call("/api/transactions?q=supermarkt&with_receipt=1")
        self.assertEqual(u2["umsaetze"][0]["belege"], 1)
        code, u3 = self.call("/api/transactions?q=supermarkt&without_receipt=1")
        self.assertFalse(any(x["id"] == tx["id"] for x in u3["umsaetze"]))
        code, data, hdr = self.call("/api/receipts/file?id=" + e["id"], raw=True)
        self.assertEqual(code, 200); self.assertEqual(data, pdf); self.assertIn("application/pdf", hdr["Content-Type"])
        os.makedirs(os.path.join(self.belege, "2026"), exist_ok=True)
        with open(os.path.join(self.belege, "2026", "alt.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 alt")
        code, bl = self.call("/api/receipts?files=1")
        self.assertTrue(any(d["pfad"] == "2026/alt.pdf" and not d["verknuepft"] for d in bl["dateien"]))
        code, r = self.call("/api/receipts/link", {"tx_id": tx["id"], "pfad": "2026/alt.pdf"})
        self.assertEqual(code, 200)
        self.assertEqual(self.call("/api/receipts/link", {"tx_id": tx["id"], "pfad": "../../etc/passwd"})[0], 400)
        code, r = self.call("/api/receipts/export", {"jahr": "2026", "entitaet": F.uid("priv")})
        self.assertEqual(code, 200); self.assertTrue(os.path.isfile(r["datei"]))
        with zipfile.ZipFile(r["datei"]) as z:
            names = z.namelist()
            self.assertIn("Belege.csv", names); self.assertEqual(len(names), 3)
        code, r = self.call("/api/receipts/update", {"id": e["id"], "notiz": "neu"})
        self.assertEqual(r["eintrag"]["notiz"], "neu")
        code, r = self.call("/api/receipts/remove", {"id": e["id"], "datei_loeschen": False})
        self.assertTrue(r["ok"]); self.assertTrue(os.path.isfile(os.path.join(self.belege, e["pfad"])))
        # Kategorisieren: ohne Zurueckschreiben nur in Kontor (uebersteuert MoneyMoney), eingeschaltet geprueft nach MoneyMoney
        import mm_categories
        MockBridge.extra_cats = [("Haushalt", 0, True, {}), ("Lebensmittel", 1, False, {})]
        self.app.categories_raw = mm_categories.with_paths(MockBridge().export_categories())
        kat_of = lambda: [x for x in self.call("/api/transactions?q=supermarkt")[1]["umsaetze"] if x["id"] == tx["id"]][0]
        code, r = self.call("/api/categories/assign", {"ids": [tx["id"]], "kategorie": "Haushalt / Lebensmittel", "warten": True})
        self.assertEqual(code, 200); self.assertTrue(r["mm"]["aus"]); self.assertEqual(r["mm"]["geschrieben"], 0)
        self.assertEqual((kat_of()["kategorie"], kat_of()["quelle"]), ("Haushalt / Lebensmittel", "manuell"))
        self.assertFalse(any(w[0] == "set" and w[2] is not None for b in MockBridge.instances for w in b.written))
        code, cfg = self.call("/api/config"); cfg["moneymoney"]["kategorisieren_erlauben"] = True
        self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 200)
        # in MoneyMoney steht schon "Lebensmittel" (fremd): erst nachfragen, nichts schreiben
        code, r = self.call("/api/categories/assign", {"ids": [tx["id"]], "kategorie": "Haushalt / Lebensmittel", "warten": True})
        self.assertEqual(r["mm"]["fremd"], [{"id": tx["id"], "mm": "Lebensmittel"}]); self.assertEqual(r["mm"]["geschrieben"], 0)
        self.assertFalse(any(w[0] == "set" and w[2] is not None for b in MockBridge.instances for w in b.written))
        self.assertEqual(kat_of()["kategorie"], "Lebensmittel")                      # bis zur Entscheidung gilt MoneyMoney
        code, r = self.call("/api/categories/assign", {"ids": [tx["id"]], "kategorie": "Haushalt / Lebensmittel", "modus": "ueberschreiben", "warten": True})
        self.assertEqual(r["mm"]["geschrieben"], 1)
        self.assertTrue(any(w[0] == "set" and w[1] == tx["id"] and w[2] == F.uid("cat:Lebensmittel") for b in MockBridge.instances for w in b.written))
        self.assertEqual(next(t for t in MockBridge.state["txs"] if t["id"] == tx["id"])["categoryPath"], "Haushalt\\Lebensmittel")
        self.assertEqual((kat_of()["kategorie"], kat_of()["quelle"]), ("Haushalt / Lebensmittel", "moneymoney"))
        # Excel-Exporte
        for was in ("balance", "cashflow", "planning", "tax", "transactions", "holdings", "receipts", "accounts"):
            for modus in ("months", "years"):
                code, data, hdr = self.call("/api/export/%s.xlsx?mode=%s" % (was, modus), raw=True)
                self.assertEqual(code, 200, (was, data[:200])); self.assertIn("spreadsheetml", hdr["Content-Type"])
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    self.assertIn("xl/workbook.xml", z.namelist()); self.assertIn("xl/worksheets/sheet1.xml", z.namelist())
        # balance sheet: everything in it (positions, accounts, securities), grouped; collapsed as on the page
        code, data, hdr = self.call("/api/export/balance.xlsx?mode=months&open=wertpapiere&dep=" + F.uid("priv.depot"), raw=True)
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
        pkg = json.loads(data.decode()); self.assertEqual(pkg["name"], "Test"); self.assertNotIn(F.uid("pb.vd"), data.decode())
        pkg["config"]["darlehen"][0]["darlehenskonto"] = "Darlehen Fremd"
        code, r = self.call("/api/package/import", {"paket": pkg, "modus": "ergaenzen"})
        self.assertFalse(r["ok"]); self.assertEqual(r["unaufgeloest"][0]["label"], "Darlehen Fremd")
        code, r = self.call("/api/package/import", {"paket": pkg, "modus": "ergaenzen", "zuordnung": {"Darlehen Fremd": F.uid("pb.vd") + " | Verkäuferdarlehen"}})
        self.assertTrue(r["ok"], r); self.assertEqual(len(r["config"]["darlehen"]), 1)
        # Diagnose maskiert, Update-Status; MoneyMoney-Aktualisierung gibt es nicht mehr
        code, data, hdr = self.call("/api/diagnostics", raw=True)
        self.assertEqual(code, 200); self.assertNotIn(F.SELLER_IBAN, data.decode()); self.assertNotIn("Stadtbank Kontokorrent", data.decode())
        code, r = self.call("/api/update/status"); self.assertEqual(code, 200)
        code, r = self.call("/api/moneymoney/refresh", {}); self.assertEqual(code, 404)
        code, r = self.call("/api/update/check", {}); self.assertEqual(code, 200); self.assertIn("info", r)


PB_EINGABEN = {
    "name": "Parkweg", "art": "gewerbe", "kaufpreis": 1900000, "uebergang": "2026-01-01", "horizont_jahre": 24,
    "nebenkosten": {"grunderwerbsteuer_prozent": 3.5, "notar": 9689.37, "grundbuch": 4127.5},
    "gebaeudeanteil_prozent": 76, "afa_prozent": 2,
    "miete": {"nettokalt_monat": 12600, "nebenkosten_monat": 1000,
              "index": {"art": "vpi", "vpi_basis": 122.7, "vpi_aktuell": 122.7, "vpi_steigerung_prozent": 1.9, "faktor": 1, "schwelle_prozent": 0}},
    "kosten": {"nicht_umlagefaehig_pa": 2928, "ruecklage_pa": 5000, "steigerung": "vpi"},
    "darlehen": [{"name": "Verkäuferdarlehen", "betrag": 1600000, "zins_prozent": 3.3, "art": "annuitaet", "annuitaet_monat": 8250, "abrechnung": "jaehrlich"}],
    "gesellschafter": [{"name": "A", "anteil_prozent": 49, "steuersatz_prozent": 47.475}, {"name": "B", "anteil_prozent": 49, "steuersatz_prozent": 47.475},
                       {"name": "C", "anteil_prozent": 1, "steuersatz_prozent": 47.475}, {"name": "D", "anteil_prozent": 1, "steuersatz_prozent": 40}],
    "ausschuettung_prozent": 48, "steuererstattung_in_cashflow": False,
}


class ImmoEngineTests(unittest.TestCase):
    """Kalkulationskern gegen die Werte einer handgerechneten Excel-Kalkulation (jaehrliche Zinsabrechnung, Indexmiete, Gesellschafter)."""

    def test_parity_with_spreadsheet(self):
        import realestate
        r = realestate.berechne(PB_EINGABEN, TODAY)
        J = {j["jahr"]: j for j in r["jahre"]}
        # Jahr 1: Miete, Zins (3,3 % auf Stand 1.1.), Tilgung = 12 x 8.250 - Zins, AfA 2 % x 76 % x (KP + NK)
        self.assertEqual(J[2026]["miete"], 151200.0)
        self.assertEqual(J[2026]["zins"], -52800.0); self.assertEqual(J[2026]["tilgung"], -46200.0)
        self.assertEqual(J[2026]["afa"], -30100.82); self.assertEqual(J[2026]["ergebnis"], 65371.18)
        self.assertAlmostEqual(J[2026]["steuer"], -30986.10, delta=0.02)
        self.assertEqual(J[2026]["ausschuettung"], -31378.17)
        self.assertEqual(J[2026]["cashflow"], 12893.83); self.assertEqual(J[2026]["vermoegensaufbau"], 59093.83)
        self.assertAlmostEqual(J[2026]["ek_rendite"], 0.1554, 4); self.assertEqual(J[2026]["restschuld"], 1553800.0)
        # Jahr 2: Indexmiete +1,9 % (Faktor 1, Schwelle 0), Zins auf neuen Jahresstand, Kosten mit VPI
        self.assertEqual(J[2027]["miete"], 154072.8); self.assertEqual(J[2027]["zins"], -51275.4)
        self.assertEqual(J[2027]["tilgung"], -47724.6); self.assertEqual(J[2027]["restschuld"], 1506075.4)
        self.assertEqual(J[2027]["kosten"], -2983.63); self.assertEqual(J[2027]["ruecklage"], -5095.0)
        self.assertEqual(J[2027]["cashflow"], 13531.95); self.assertEqual(J[2029]["cashflow"], 14813.52)
        self.assertEqual(J[2029]["restschuld"], 1405849.49)
        K = r["kennzahlen"]
        self.assertEqual(K["eigenkapital_inkl_nk"], 380316.87); self.assertEqual(K["afa_jahr"], 30100.82)
        self.assertAlmostEqual(K["kaufpreisfaktor"], 1900000 / 151200, 2)
        self.assertAlmostEqual(K["bruttomietrendite"], 151200 / 1900000, 4)
        self.assertEqual(len(r["jahre"]), 24); self.assertEqual(len(r["monate"]), 24 * 12)
        # Planreihen: Monatswerte summieren sich auf das Jahr
        reihen = realestate.planreihen(r)
        self.assertAlmostEqual(sum(v for k, v in reihen["miete"].items() if k.startswith("2027")), 154072.8 + 12000, 1)   # inkl. Umlage (Zahlungsstrom)
        self.assertAlmostEqual(sum(v for k, v in reihen["kosten"].items() if k.startswith("2027")), -2983.63 - 12000, 1)
        self.assertEqual(round(reihen["darlehen"]["Verkäuferdarlehen"]["saldo"]["2026-12"], 2), -1553800.0)
        sheets = realestate.sheets(r)
        self.assertEqual([x.name for x in sheets], ["Eingaben", "Kennzahlen", "Jahre", "Monate"])

    def test_parity_second_and_third_sheet(self):
        """Zwei weitere handgerechnete Kalkulationen: Teiljahr ab Mai, drei Darlehensarten (endfaellig, Tilgung mit spaeterer
        Sondertilgung, Annuitaet), Indexmiete mit Schwelle 5 % und Faktor 0,75, RND statt AfA-Satz; und ein einfaches Wohnobjekt."""
        import realestate
        o = {"name": "G", "kaufpreis": 4000000, "uebergang": "2026-05-01", "horizont_jahre": 10,
             "nebenkosten": {"grunderwerbsteuer_prozent": 3.5, "notar": 18122.9, "grundbuch": 11788.0},
             "gebaeudeanteil_prozent": 51.44, "restnutzungsdauer_jahre": 18,
             "miete": {"nettokalt_monat": 18603.18, "nebenkosten_monat": 2300,
                       "index": {"art": "vpi", "vpi_basis": 122.6, "vpi_aktuell": 122.8, "vpi_steigerung_prozent": 1.9, "faktor": 0.75, "schwelle_prozent": 5}},
             "kosten": {"nicht_umlagefaehig_pa": 20600, "ruecklage_pa": 10000, "steigerung": "keine"},
             "darlehen": [{"name": "E", "betrag": 800000, "zins_prozent": 3.39, "art": "endfaellig", "abrechnung": "jaehrlich", "faelligkeit": "2031-02"},
                          {"name": "T", "betrag": 1300000, "zins_prozent": 3.49, "art": "tilgung", "tilgung_monat": 4450, "sondertilgung_monat": 2260, "sondertilgung_ab": "2031-04", "abrechnung": "jaehrlich"},
                          {"name": "A", "betrag": 1300000, "zins_prozent": 4.0, "art": "annuitaet", "annuitaet_monat": 8080.2, "abrechnung": "jaehrlich"}],
             "gesellschafter": [{"name": "A", "anteil_prozent": 49, "steuersatz_prozent": 47.475}, {"name": "B", "anteil_prozent": 49, "steuersatz_prozent": 47.475},
                                {"name": "C", "anteil_prozent": 1, "steuersatz_prozent": 47.475}, {"name": "D", "anteil_prozent": 1, "steuersatz_prozent": 40}],
             "ausschuettung_prozent": 48, "steuererstattung_in_cashflow": True}
        J = {j["jahr"]: j for j in realestate.berechne(o, TODAY)["jahre"]}
        self.assertEqual(J[2026]["monate"], 8); self.assertEqual(J[2026]["miete"], 148825.44); self.assertEqual(J[2026]["afa"], -79444.52)
        self.assertAlmostEqual(J[2026]["ergebnis"], -27345.75, delta=0.02); self.assertAlmostEqual(J[2026]["steuer"], 12961.95, delta=0.02)
        self.assertAlmostEqual(J[2026]["cashflow"], -7180.87, delta=0.02); self.assertAlmostEqual(J[2026]["ek_rendite"], 0.0758, 3)
        self.assertEqual(J[2026]["darlehen"]["T"]["saldo"], -1264400.0); self.assertEqual(J[2026]["darlehen"]["A"]["saldo"], -1270025.07)
        self.assertEqual(J[2027]["zins"], -122048.56); self.assertAlmostEqual(J[2027]["cashflow"], -10686.12, delta=0.03)
        self.assertEqual(J[2028]["miete"], 223238.16); self.assertEqual(J[2029]["miete"], 233253.06)    # Indexanpassung erst ab >5 % VPI-Aenderung
        self.assertAlmostEqual(J[2030]["cashflow"], -5209.56, delta=0.02)
        self.assertEqual(J[2031]["sondertilgung"], -20340.0)                                        # 9 x 2.260 (April bis Dezember)
        o2 = {"name": "W", "art": "wohnen", "kaufpreis": 344000, "uebergang": "2026-01-01", "horizont_jahre": 5,
              "nebenkosten": {"grunderwerbsteuer_prozent": 3.5, "notar": 5160}, "gebaeudeanteil_prozent": 44.46, "afa_prozent": 2.0,
              "miete": {"nettokalt_monat": 800, "nebenkosten_monat": 200, "index": {"art": "keine"}},
              "kosten": {"nicht_umlagefaehig_pa": 1000, "steigerung": "keine"},
              "darlehen": [{"name": "B", "betrag": 326000, "zins_prozent": 3.75, "annuitaet_monat": 1510, "abrechnung": "jaehrlich"}],
              "gesellschafter": [{"name": "S", "anteil_prozent": 100, "steuersatz_prozent": 47.475}], "ausschuettung_prozent": 49, "steuererstattung_in_cashflow": True}
        J2 = {j["jahr"]: j for j in realestate.berechne(o2, TODAY)["jahre"]}
        self.assertEqual(J2[2026]["ergebnis"], -6836.79); self.assertEqual(J2[2026]["steuer"], 3245.77); self.assertEqual(J2[2026]["cashflow"], -6274.23)
        self.assertEqual(J2[2026]["restschuld"], 320105.0); self.assertEqual(J2[2029]["restschuld"], 301060.15); self.assertEqual(J2[2030]["ek_rendite"], 0.0033)

    def test_loan_variants_and_hints(self):
        import realestate
        base = {"name": "Test", "kaufpreis": 500000, "uebergang": "2026-05-01", "horizont_jahre": 12, "gebaeudeanteil_prozent": 80,
                "miete": {"nettokalt_monat": 2000, "index": {"art": "keine"}}, "kosten": {"nicht_umlagefaehig_pa": 2400, "steigerung": "keine"}}
        # Annuitaet monatlich mit Anfangstilgung, Sondertilgung ab Monat, Zinsbindung + Anschlusszins
        o = dict(base, darlehen=[{"name": "Bank", "betrag": 400000, "zins_prozent": 3.6, "anfangstilgung_prozent": 2.4, "abrechnung": "monatlich",
                                   "sondertilgung_monat": 500, "sondertilgung_ab": "2028-01", "zinsbindung_bis": "2031-04", "anschluss_zins_prozent": 5.0,
                                   "sondertilgungen": [{"datum": "2027-06", "betrag": 20000}]}])
        r = realestate.berechne(o, TODAY)
        M = {m["monat"]: m for m in r["monate"]}
        self.assertEqual(M["2026-05"]["zins"], -1200.0)                    # 400000 x 3,6 % / 12
        self.assertEqual(M["2026-05"]["tilgung"], -800.0)                  # Annuitaet 2000 - Zins
        self.assertEqual(M["2027-06"]["sondertilgung"], -20000.0)
        self.assertEqual(M["2028-01"]["sondertilgung"], -500.0); self.assertEqual(M["2027-12"]["sondertilgung"], 0.0)
        s_apr = M["2031-04"]["darlehen"]["Bank"]["saldo"]; z_mai = M["2031-05"]["zins"]
        self.assertAlmostEqual(z_mai, -round(abs(s_apr) * 5.0 / 1200, 2), 1)   # Anschlusszins ab Mai 2031
        # Endfaellig mit Rueckzahlung
        o2 = dict(base, darlehen=[{"name": "Privat", "betrag": 100000, "zins_prozent": 4, "art": "endfaellig", "faelligkeit": "2028-12", "faelligkeit_art": "rueckzahlung", "abziehbar": False}])
        r2 = realestate.berechne(o2, TODAY)
        M2 = {m["monat"]: m for m in r2["monate"]}
        self.assertEqual(M2["2028-11"]["tilgung"], 0.0); self.assertEqual(M2["2028-12"]["sondertilgung"], -100000.0)
        self.assertEqual(M2["2029-01"]["zins"], 0.0)
        J2 = {j["jahr"]: j for j in r2["jahre"]}
        self.assertEqual(J2[2027]["zins_abziehbar"], 0.0); self.assertEqual(J2[2027]["zins"], -4000.0)
        # Endfaellig offen -> Hinweis
        o3 = dict(base, darlehen=[{"name": "Privat", "betrag": 100000, "zins_prozent": 4, "art": "endfaellig", "faelligkeit": "2028-12"}])
        r3 = realestate.berechne(o3, TODAY)
        self.assertTrue(any("Privat" in h for h in r3["hinweise"]))
        # Verkauf mit IRR, RND statt AfA-Satz, Leerstand, feste Mietsteigerung
        o4 = dict(base, restnutzungsdauer_jahre=40, wertentwicklung_prozent=2, verkauf={"jahr": 2031, "kosten_prozent": 2},
                  miete={"nettokalt_monat": 2000, "leerstand_prozent": 5, "index": {"art": "prozent", "steigerung_prozent": 2}})
        r4 = realestate.berechne(o4, TODAY)
        self.assertEqual(r4["kennzahlen"]["afa_satz"], 2.5); self.assertIsNotNone(r4["kennzahlen"]["irr"])
        self.assertEqual(r4["kennzahlen"]["exit_jahr"], 2031)
        J4 = {j["jahr"]: j for j in r4["jahre"]}
        self.assertEqual(J4[2026]["miete"], round(2000 * 0.95 * 8, 2))
        self.assertAlmostEqual(J4[2028]["nkm_monat"], round(2000 * 1.02 ** 2, 2), 2)
        # Darlehen, das vor dem Horizont ausgezahlt wurde, laeuft ab dem ersten Monat mit
        o5 = dict(base, darlehen=[{"name": "Alt", "betrag": 100000, "zins_prozent": 3, "annuitaet_monat": 1000, "beginn": "2025-11"}])
        r5 = realestate.berechne(o5, TODAY)
        self.assertEqual(r5["monate"][0]["zins"], -250.0); self.assertEqual(r5["monate"][0]["tilgung"], -750.0)
        # Unsinnige Eingaben: Fehler statt Absturz
        with self.assertRaises(ValueError):
            realestate.berechne({"kaufpreis": 100, "uebergang": "2026-01", "gesellschafter": [{"name": "A", "anteil_prozent": 60}, {"name": "B", "anteil_prozent": 60}]}, TODAY)
        with self.assertRaises(ValueError):
            realestate.berechne({"kaufpreis": 100, "uebergang": "2026-01", "darlehen": [{"name": "X", "betrag": "viel"}]}, TODAY)
        with self.assertRaises(ValueError):
            realestate.berechne({"kaufpreis": -1}, TODAY)
        with self.assertRaises(ValueError):
            realestate.berechne({"kaufpreis": 100, "uebergang": "kein-datum"}, TODAY)


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
                self.assertTrue(store.load("config.json")["oberflaeche"]["touchid"])
                pg.click("#lock-btn"); pg.wait_for_selector("#login:not(.hidden)")
                pg.reload(); pg.wait_for_selector("#tid-box:not(.hidden)")
                self.assertFalse(pg.is_visible("#login-pw")); self.assertTrue(pg.is_visible("#pw-instead"))
                pg.click("#pw-instead"); self.assertTrue(pg.is_visible("#login-pw")); self.assertFalse(pg.is_visible("#tid-box"))
                self.assertTrue(pg.is_visible("#tid-instead"))
                pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.click("#login-btn"); wait_shell(pg)
                # ausschalten -> nur Passwort
                cfg = store.load("config.json"); cfg["oberflaeche"]["touchid"] = False; app.save_config(cfg)
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
        self.assertTrue(out[0]["haupt"]); self.assertEqual([b["art"] for b in out], ["privat", "privat", "gesellschaft", "gesellschaft"])


class FeatureTests(_AppBase):
    """Bereiche unabhaengig von der MoneyMoney-Gruppierung, Positionen, Verlaufsquellen, inaktive Konten, Ereignisse, Immobilien, Dateiverknuepfungen."""

    def test_bereiche_positions_history_inactive(self):
        self.login()
        # Altes Konto ohne Bestand und ohne Umsaetze -> inaktiv
        accts = MockBridge.state["accounts"]
        accts.insert([a["uuid"] for a in accts].index(F.uid("priv.tr")) + 1, F.acc("priv.alt", "Altes Sparbuch", 3, "Sparkonto", balance=0.0, iban="DE02100100100006820101", bank="10010010"))
        self.run_and_wait()
        code, ds = self.call("/api/dataset")
        P = ds["haupt"]; b = ds["bereiche"][P]
        self.assertIn(F.uid("priv.alt"), b["konten_inaktiv"])
        self.assertEqual(b["konten_aktivitaet"][F.uid("priv.alt")], 9999); self.assertEqual(b["konten_aktivitaet"][F.uid("priv.giro")], 0)
        code, kt = self.call("/api/accounts")
        self.assertEqual([x for x in kt["konten"] if x["uuid"] == F.uid("priv.alt")][0]["aktiv_grenze"], 9999)
        alt = [r for r in b["bilanz"]["zeilen"] if r["id"] == F.uid("priv.alt")][0]
        self.assertTrue(alt["inaktiv"])
        pos = [r for r in b["bilanz"]["zeilen"] if r["gruppe"]]
        self.assertEqual([r["id"] for r in pos][:2], ["pos:liquiditaet", "pos:wertpapiere"])
        self.assertTrue(all(r["id"].startswith("pos:") for r in pos))
        depot = [r for r in b["bilanz"]["zeilen"] if r["id"] == F.uid("priv.depot")][0]
        self.assertEqual(depot["rolle"], "wertpapiere"); self.assertEqual(depot["verlauf"], "stand")
        self.assertEqual(depot["werte"]["2026-11"], 85000.0)
        # kein aelterer Stand bekannt: keine Schaetzung -- der erste bekannte Wert steht davor, gekennzeichnet
        self.assertEqual(depot["werte"]["2026-10"], 85000.0); self.assertEqual(depot["werte"]["2024-11"], 85000.0)
        self.assertNotIn("geschaetzt_bis", depot); self.assertEqual(depot["fortgeschrieben_vor"], "2026-11")
        self.assertTrue(any("fortgeschrieben" in w for w in b["warnungen"]))
        # Verlauf: Monatsstaende setzen, Import, Quelle umstellen
        code, h = self.call("/api/history?account=" + F.uid("priv.depot"))
        self.assertEqual(h["quelle"], "stand"); self.assertEqual(h["aufgezeichnet"]["2026-11"], 85000.0)
        code, r = self.call("/api/history", {"konto": F.uid("priv.depot"), "werte": {"2026-10": "84.000,00", "2026-09": 80000, "2025-12": 60000}})
        self.assertEqual(code, 200); self.assertTrue(r["bericht"])
        code, ds = self.call("/api/dataset"); b = ds["bereiche"][P]
        depot = [r for r in b["bilanz"]["zeilen"] if r["id"] == F.uid("priv.depot")][0]
        self.assertEqual(depot["werte"]["2026-10"], 84000.0); self.assertEqual(depot["werte"]["2026-09"], 80000.0)
        self.assertEqual(depot["werte"]["2026-05"], 60000.0)     # Luecken: letzter bekannter Stand
        self.assertEqual(b["bilanz"]["nettovermoegen"]["2026-10"], round(sum((r["werte"]["2026-10"] or 0) for r in b["bilanz"]["zeilen"] if not r["gruppe"]), 2))
        csv = "Datum;Konto;Saldo\n31.03.2026;Depot;70.000,00\n30.04.2026;Depot;71.500,50\n31.03.2026;Hausbank Giro;1.000,00\n"
        code, r = self.call("/api/history/import", {"csv": csv})
        self.assertEqual(code, 200); self.assertEqual(len(r["vorschau"]), 2); self.assertTrue(all(v["uuid"] for v in r["vorschau"]))
        code, r = self.call("/api/history/import", {"csv": csv, "uebernehmen": True})
        self.assertEqual(r["uebernommen"], 3)
        code, h = self.call("/api/history?account=" + F.uid("priv.depot"))
        self.assertEqual(h["manuell"]["2026-04"], 71500.5)
        # Girokonto auf "Staende" umstellen und zurueck
        code, r = self.call("/api/history", {"konto": F.uid("priv.giro"), "werte": {}, "quelle": "stand"})
        code, cfg = self.call("/api/config")
        self.assertEqual(cfg["bilanz"]["verlauf"].get(F.uid("priv.giro") + " | Hausbank Giro"), "stand")
        code, ds = self.call("/api/dataset")
        giro = [r for r in ds["bereiche"][P]["bilanz"]["zeilen"] if r["id"] == F.uid("priv.giro")][0]
        self.assertEqual(giro["verlauf"], "stand"); self.assertEqual(giro["werte"]["2026-03"], 1000.0)
        self.call("/api/history", {"konto": F.uid("priv.giro"), "werte": {}, "quelle": "umsaetze", "loeschen": True})
        code, ds = self.call("/api/dataset")
        giro = [r for r in ds["bereiche"][P]["bilanz"]["zeilen"] if r["id"] == F.uid("priv.giro")][0]
        self.assertEqual(giro["verlauf"], "umsaetze")
        # Bereiche frei aus Konten zusammensetzen (unabhaengig von der Gruppierung) + Position ueberschreiben + Ausblenden
        cfg["bereiche"] = [
            {"id": "privat", "name": "Privat", "art": "privat", "haupt": True, "konten": [F.uid("priv") + " | Privat"]},
            {"id": "objekte", "name": "Alle Objekte", "art": "gesellschaft", "anteil": 0.49,
             "konten": [F.uid("pb.immo") + " | Immobilie Parkweg", F.uid("shs.immo") + " | Immobilie Bahnhofstraße", F.uid("pb.vd") + " | Verkäuferdarlehen", F.uid("pb.kk") + " | Stadtbank Kontokorrent"]}]
        cfg["bilanz"]["rollen"] = {F.uid("priv.immo") + " | Immobilie Lindenstraße": "immobilien", F.uid("priv.tr") + " | Broker Giro": "anlagen"}
        cfg["bilanz"]["ausgeblendet"] = [F.uid("priv.tr") + " | Broker Giro"]
        cfg["bilanz"]["inaktiv_monate"] = 0
        code, r = self.call("/api/config", {"config": cfg}, method="PUT")
        self.assertEqual(code, 200, r)
        code, r = self.call("/api/report", {}); self.assertTrue(r["ok"])
        code, ds = self.call("/api/dataset")
        self.assertEqual(set(ds["bereiche"]), {"privat", "objekte"}); self.assertEqual(ds["haupt"], "privat")
        ob = ds["bereiche"]["objekte"]
        saldo = {k["uuid"]: k["saldo"] for k in ds["konten"] if not k["gruppe"]}
        self.assertEqual(ob["bilanz"]["nettovermoegen"]["2026-11"], round(sum(saldo[F.uid(k)] for k in ("pb.immo", "shs.immo", "pb.vd", "pb.kk")), 2))
        self.assertEqual(saldo[F.uid("shs.immo")], 3300000.0)
        self.assertEqual(ds["bereich_info"]["objekte"]["anzahl_konten"], 4); self.assertEqual(ds["bereich_info"]["objekte"]["art"], "gesellschaft")
        pr = ds["bereiche"]["privat"]
        immo = [r for r in pr["bilanz"]["zeilen"] if r["id"] == F.uid("priv.immo")][0]
        self.assertEqual(immo["rolle"], "immobilien")
        tr = [r for r in pr["bilanz"]["zeilen"] if r["id"] == F.uid("priv.tr")][0]
        self.assertEqual(tr["rolle"], "anlagen"); self.assertTrue(tr["inaktiv"])      # ausgeblendet = wie inaktiv, zaehlt aber mit
        self.assertFalse([r for r in pr["bilanz"]["zeilen"] if r["id"] == F.uid("priv.alt")][0]["inaktiv"])   # inaktiv_monate 0 = nie
        self.assertTrue(any(e["name"] == "Alle Objekte" and e["anteil"] == 0.49 for e in ds["steuer"]["entitaeten"]))
        # Konten-Export und Pakete enthalten die Bereiche
        code, data, hdr = self.call("/api/package/export?name=B", raw=True)
        pkg = json.loads(data.decode()); self.assertEqual(len(pkg["config"]["bereiche"]), 2)
        self.assertFalse(re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", json.dumps(pkg["config"])))         # Paket immer ohne UUIDs
        self.assertNotIn("plan", pkg)
        self.assertTrue(any(k["name"] == "Alle Objekte" for k in ds["konten"] if k["gruppe"]) or ds["bereich_namen"]["objekte"] == "Alle Objekte")

    def test_events_and_cross_bereich(self):
        self.login(); self.run_and_wait()
        code, ds = self.call("/api/dataset"); P = ds["haupt"]
        b = ds["bereiche"][P]; fm = b["plan_monate"]
        # Umschichtung: 100.000 aus dem Depot auf das Darlehen (Tilgung auf einen Schlag) im 4. Planmonat
        mk = fm[3]
        code, r = self.call("/api/plan", {"bereich": P, "darlehen": {"Darlehen Lindenstraße": {"zins_prozent_pa": "3.6", "modell": "restschuld_monatlich"}},
                                          "ereignis": {"text": "Rückzahlung aus Depot", "art": "umschichtung", "betrag": 100000, "monat": mk,
                                                       "von": F.uid("priv.depot") + " | Depot", "nach": F.uid("priv.darl") + " | Darlehen Lindenstraße"}})
        self.assertEqual(code, 200)
        self.assertEqual(self.call("/api/plan", {"bereich": P, "ereignis": {"text": "x", "betrag": 1, "monat": "bald"}})[0], 400)
        code, ds = self.call("/api/dataset"); b = ds["bereiche"][P]
        self.assertEqual(len(b["plan"]["ereignisse"]), 1); eid = b["plan"]["ereignisse"][0]["id"]
        pr = {r["id"]: r for r in b["bilanz"]["projektion"]["zeilen"]}
        dep, darl = pr[F.uid("priv.depot")]["werte"], pr[F.uid("priv.darl")]["werte"]
        self.assertAlmostEqual(dep[fm[2]] - dep[mk], 100000, delta=1500)       # Depot sinkt (abzgl. Sparplan/Rendite)
        self.assertAlmostEqual(darl[mk] - darl[fm[2]], 100000, delta=1500)     # Darlehen steigt um 100.000 (weniger negativ) abzgl. regulaerer Tilgung
        fz = {z["zeile"]: z for z in [s for s in b["kapitalfluss"]["sektionen"] if s["name"] == "Finanzierung"][0]["zeilen"]}
        z_before, z_after = fz["Darlehen Lindenstraße / Zinsen"]["plan"]["werte"][fm[2]], fz["Darlehen Lindenstraße / Zinsen"]["plan"]["werte"][fm[4]]
        self.assertLess(abs(z_after), abs(z_before) - 250)                    # Zins faellt nach der Sondertilgung (3,6 % auf 100.000 = 300/Monat)
        # Ausgabe-Ereignis monatlich bis Enddatum -> Zeile in Ausgaben, Liquiditaet sinkt
        liq0 = b["bilanz"]["projektion"]["liquiditaet"]
        code, r = self.call("/api/plan", {"bereich": P, "ereignis": {"text": "Kita", "art": "ausgabe", "betrag": 400, "monat": fm[0], "wiederholung": "monatlich", "bis": fm[5]}})
        code, ds = self.call("/api/dataset"); b = ds["bereiche"][P]
        az = [z for z in [s for s in b["kapitalfluss"]["sektionen"] if s["name"] == "Ausgaben"][0]["zeilen"] if z["zeile"] == "Ereignis: Kita"][0]
        self.assertEqual(az["plan"]["werte"][fm[0]], -400.0); self.assertEqual(az["plan"]["werte"][fm[5]], -400.0); self.assertEqual(az["plan"]["werte"].get(fm[6], 0.0), 0.0)
        self.assertAlmostEqual(b["bilanz"]["projektion"]["liquiditaet"][fm[5]], liq0[fm[5]] - 2400, 0)
        # Ereignis loeschen
        self.call("/api/plan", {"bereich": P, "ereignis": {"id": eid, "loeschen": True}})
        code, ds = self.call("/api/dataset")
        self.assertEqual([e["text"] for e in ds["bereiche"][P]["plan"]["ereignisse"]], ["Kita"])
        # Beteiligung an anderem Bereich: Wert = Anteil x geplantes Nettovermoegen der GbR
        code, r = self.call("/api/plan", {"bereich": P, "wertentwicklung": {"Beteiligung an Alpha GbR": {"bereich": F.uid("pb"), "anteil": "0.49"}}})
        code, ds = self.call("/api/dataset"); b = ds["bereiche"][P]
        self.assertEqual(b["plan"]["wertentwicklung"]["Beteiligung an Alpha GbR"], {"anteil": 0.49, "bereich": F.uid("pb")})
        pr = {r["id"]: r for r in b["bilanz"]["projektion"]["zeilen"]}
        gbr_nw = ds["bereiche"][F.uid("pb")]["bilanz"]["projektion"]["nettovermoegen"]
        self.assertAlmostEqual(pr[F.uid("priv.bet.pb")]["werte"][fm[5]], round(gbr_nw[fm[5]] * 0.49, 2), 0)

    def test_equity_ratio(self):
        """Equity ratio looking through the companies: own debts plus the share of each linked company's debts; the partners'
        capital accounts are equity, never debts; nothing estimated."""
        self.login(); self.run_and_wait()
        code, ds = self.call("/api/dataset")
        P, A, B_ = F.uid("priv"), F.uid("pb"), F.uid("shs")
        priv = ds["bereiche"][P]["bilanz"]["ek_quote"]["monate"]; alpha = ds["bereiche"][A]["bilanz"]["ek_quote"]["monate"]
        mk = sorted(priv)[-2]; e = priv[mk]; ea = alpha[mk]
        self.assertEqual(e["nw"], ds["bereiche"][P]["bilanz"]["nettovermoegen"][mk]); self.assertEqual(e["kapital"], 0)
        self.assertEqual([f["name"] for f in e["firmen"]], ["Alpha GbR", "Beta GbR"])
        fa = e["firmen"][0]; self.assertAlmostEqual(fa["anteil"], 0.49); self.assertAlmostEqual(fa["schulden"], ea["eigene"], 2)
        self.assertAlmostEqual(fa["anteilig"], round(0.49 * ea["eigene"], 2), 2)
        self.assertAlmostEqual(e["schulden"], e["eigene"] + sum(f["anteilig"] for f in e["firmen"]), 2)
        self.assertAlmostEqual(e["quote"], round(e["ek"] / (e["ek"] + e["schulden"]), 4), 4)
        # in the company: the partners' capital accounts are equity (added back), not debts
        self.assertNotIn("Kapitalkonto A", [k[0] for k in ea["konten"]]); self.assertGreater(ea["kapital"], 0)
        self.assertAlmostEqual(ea["ek"], ds["bereiche"][A]["bilanz"]["nettovermoegen"][mk] + ea["kapital"], 2)
        self.assertEqual(ds["bereiche"][P]["bilanz"]["ek_quote"]["ohne_durchschau"], [])

    def test_immobilien_api_plan_tax_export(self):
        self.login(); self.run_and_wait()
        code, r = self.call("/api/properties/template"); self.assertEqual(r["eingaben"]["name"], "Neues Objekt")
        code, r = self.call("/api/properties/calculate", {"eingaben": PB_EINGABEN, "ohne_monate": True})
        self.assertEqual(code, 200); self.assertNotIn("monate", r); self.assertEqual(r["jahre"][0]["cashflow"], 12893.83)
        self.assertEqual(self.call("/api/properties/calculate", {"eingaben": {"kaufpreis": "abc"}})[0], 400)
        # Objekt anlegen, Kalkulation speichern, zweites Szenario, aktiv wechseln
        code, r = self.call("/api/properties", {"aktion": "anlegen", "name": "Parkweg", "bereich": F.uid("pb"), "kategorie": "Vermietung \\ Parkweg",
                                                "objekt_konto": F.uid("pb.immo") + " | Immobilie Parkweg"})
        self.assertEqual(code, 200); iid = r["immobilie"]["id"]
        code, r = self.call("/api/properties", {"aktion": "kalkulation_speichern", "id": iid, "kalkulation": {"name": "Basis", "eingaben": PB_EINGABEN}})
        self.assertEqual(code, 200); k1 = r["immobilie"]["kalkulationen"][0]; self.assertTrue(k1["aktiv"])
        var = copy.deepcopy(PB_EINGABEN); var["miete"]["nettokalt_monat"] = 13000
        code, r = self.call("/api/properties", {"aktion": "kalkulation_speichern", "id": iid, "kalkulation": {"name": "Mehr Miete", "eingaben": var}})
        k2 = r["immobilie"]["kalkulationen"][1]; self.assertFalse(k2["aktiv"])
        self.assertEqual(self.call("/api/properties", {"aktion": "kalkulation_speichern", "id": iid, "kalkulation": {"name": "kaputt", "eingaben": {"kaufpreis": -5}}})[0], 400)
        code, r = self.call("/api/properties", {"aktion": "aendern", "id": iid, "in_planung": True, "darlehen_konten": {"Verkäuferdarlehen": F.uid("pb.vd") + " | Verkäuferdarlehen"}})
        self.assertTrue(r["bericht"])
        code, ds = self.call("/api/dataset")
        im = [x for x in ds["immobilien"] if x["id"] == iid][0]
        self.assertEqual(im["kennzahlen"]["afa_jahr"], 30100.82); self.assertTrue(im["in_planung"])
        self.assertEqual(len(im["kalkulationen"]), 2)
        # Soll/Ist: Mieteinnahmen 2026 aus Umsaetzen (9.500 x 11 Monate bis Nov) gegen Kalkulation
        si = {x["jahr"]: x for x in im["soll_ist"]}
        self.assertEqual(si[2026]["miete_soll"], 151200.0); self.assertEqual(si[2026]["miete_ist"], 9500.0 * 11)
        self.assertEqual(si[2026]["kosten_ist"], -800.0 * 11); self.assertEqual(si[2026]["restschuld_soll"], 1553800.0)
        self.assertIsNotNone(si[2026]["restschuld_ist"])
        # Planung der GbR: Mietzeile folgt der Kalkulation, Darlehenssaldo folgt der Kalkulation, Ausschuettung als Entnahme
        gbr = ds["bereiche"][F.uid("pb")]; fm = gbr["plan_monate"]
        ez = [z for z in [s for s in gbr["kapitalfluss"]["sektionen"] if s["name"] == "Einnahmen"][0]["zeilen"] if "Mieteinnahmen" in z["zeile"]][0]
        self.assertEqual(ez["plan"]["methode"], "immobilie"); self.assertEqual(ez["plan"]["werte"][fm[0]], 13600.0)   # NKM + Umlage
        jan27 = [m for m in fm if m == "2027-01"][0]
        self.assertEqual(ez["plan"]["werte"][jan27], 13839.4)        # 12600 x 1,019 + 1000
        pr = {r["id"]: r for r in gbr["bilanz"]["projektion"]["zeilen"]}
        self.assertEqual(pr[F.uid("pb.vd")]["werte"]["2026-12"], -1553800.0)
        self.assertEqual(round(pr[F.uid("pb.immo")]["werte"]["2026-12"]), round(1900000 * 1.02 ** (11 / 12)))   # monatliche Wertentwicklung ab dem 2. Monat
        inv = [z for z in [s for s in gbr["kapitalfluss"]["sektionen"] if s["name"] == "Investitionen"][0]["zeilen"] if "Entnahmen Gesellschafter" in z["zeile"]]
        self.assertTrue(inv); self.assertLess(sum(inv[0]["plan"]["werte"].values()), 0)
        # Steuer: AfA aus der Kalkulation, wenn nicht manuell eingetragen
        code, cfg = self.call("/api/config"); cfg["steuer"]["afa"] = {}
        self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 200)
        self.call("/api/report", {})
        code, ds = self.call("/api/dataset")
        ent = [e for e in ds["steuer"]["entitaeten"] if e["uuid"] == F.uid("pb")][0]
        self.assertEqual(ent["jahre"]["2026"]["objekte"]["Parkweg"]["afa"], 30100.82)
        self.assertEqual(ent["jahre"]["2026"]["objekte"]["Parkweg"].get("afa_quelle"), "kalkulation")
        # Szenario aktiv wechseln -> andere Miete in der Planung; Szenario loeschen
        code, r = self.call("/api/properties", {"aktion": "kalkulation_aktiv", "id": iid, "kalkulation_id": k2["id"]})
        code, ds = self.call("/api/dataset"); gbr = ds["bereiche"][F.uid("pb")]
        ez = [z for z in [s for s in gbr["kapitalfluss"]["sektionen"] if s["name"] == "Einnahmen"][0]["zeilen"] if "Mieteinnahmen" in z["zeile"]][0]
        self.assertEqual(ez["plan"]["werte"][fm[0]], 14000.0)
        code, r = self.call("/api/properties", {"aktion": "kalkulation_loeschen", "id": iid, "kalkulation_id": k2["id"]})
        self.assertTrue(r["immobilie"]["kalkulationen"][0]["aktiv"])
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
        code, r = self.call("/api/properties", {"aktion": "dokument_hinzufuegen", "id": iid, "titel": "Kaufvertrag", "art": "Vertrag", "pfad": doc})
        self.assertEqual(code, 200); self.assertEqual(r["immobilie"]["dokumente"][0]["pfad"], doc)
        self.assertEqual(self.call("/api/properties", {"aktion": "dokument_hinzufuegen", "id": iid, "pfad": doc + ".fehlt"})[0], 400)
        code, r = self.call("/api/file/status?path=" + urllib.parse.quote(doc))
        self.assertEqual(r["status"], "ok"); self.assertEqual(r["groesse"], 16)
        code, r = self.call("/api/file/status?path=" + urllib.parse.quote(doc + ".nein"))
        self.assertEqual(r["status"], "fehlt")
        did = self.call("/api/config")[1]["immobilien"][0]["dokumente"][0]["id"]
        code, r = self.call("/api/properties", {"aktion": "dokument_entfernen", "id": iid, "dokument_id": did})
        self.assertEqual(r["immobilie"]["dokumente"], []); self.assertTrue(os.path.isfile(doc))
        # Paket enthaelt Immobilien; Objekt loeschen
        code, data, hdr = self.call("/api/package/export?name=I", raw=True)
        self.assertEqual(len(json.loads(data.decode())["config"]["immobilien"]), 1)
        code, r = self.call("/api/properties", {"aktion": "loeschen", "id": iid}); self.assertTrue(r["ok"])
        self.assertEqual(self.call("/api/config")[1]["immobilien"], [])
        # Datei-Dialoge nur am Mac
        code, r = self.call("/api/file/choose", {"art": "datei"})
        self.assertIn(code, (400, 403))


    def test_kontor_kategorien_und_konten_zuordnung(self):
        self.login(); self.run_and_wait()
        code, k = self.call("/api/categories/kontor")
        self.assertEqual(code, 200)
        pfade = {x["pfad"] for x in k["baum"]}
        self.assertIn("Wohnen / Miete", pfade); self.assertIn("Vermietung / Parkweg / Mieteinnahmen", pfade)   # aus MoneyMoney uebernommen
        self.assertTrue(k["statistik"]["regeln"]["gelernt"] >= 3)        # Arbeitgeber, Vermieter, Versicherer, Supermarkt, ...
        regeln = {r.get("name_ist") or r.get("name_enthaelt"): r for r in k["regeln"]}
        self.assertEqual(regeln["supermarkt"]["kategorie"], "Lebensmittel")
        # Offene Umsaetze: Baumarkt (ohne Kategorie) als Gruppe
        code, off = self.call("/api/categories/unassigned")
        self.assertTrue(off["offen"] >= 20)
        g = [x for x in off["gruppen"] if x["name"] == "Baumarkt"][0]
        self.assertEqual(g["anzahl"], off["offen"] if len(off["gruppen"]) == 1 else g["anzahl"]); self.assertIsNone(g["vorschlag"])
        # Zuordnen mit Regel -> alle Baumarkt-Umsaetze kategorisiert, Kapitalfluss zeigt die neue Kategorie
        code, r = self.call("/api/categories/assign", {"ids": g["ids"][:2], "kategorie": "Haushalt / Werkzeug", "regel": {"name_enthaelt": "Baumarkt"}})
        self.assertEqual(code, 200); self.assertEqual(r["anzahl"], 2); self.assertTrue(r["regel"]); self.assertTrue(r["bericht"])
        code, off2 = self.call("/api/categories/unassigned")
        self.assertFalse(any(x["name"] == "Baumarkt" for x in off2["gruppen"]))          # Regel hat den Rest erfasst
        code, ds = self.call("/api/dataset")
        az = [s["zeilen"] for s in ds["bereiche"][ds["haupt"]]["kapitalfluss"]["sektionen"] if s["name"] == "Ausgaben"][0]
        self.assertTrue(any(z["zeile"] == "Haushalt / Werkzeug" for z in az))
        self.assertEqual(ds["kategorien"]["gesamt"]["regel"] >= 20, True)
        code, u = self.call("/api/transactions?q=baumarkt&limit=3")
        self.assertEqual(u["umsaetze"][0]["kategorie"], "Haushalt / Werkzeug"); self.assertIn(u["umsaetze"][0]["quelle"], ("manuell", "regel"))
        # Kategorie umbenennen/verschieben, Regel loeschen, manuelle Zuordnung entfernen
        code, r = self.call("/api/categories/tree", {"aktion": "umbenennen", "pfad": "Haushalt / Werkzeug", "neu": "Wohnen / Werkzeug"})
        self.assertTrue(any(x["pfad"] == "Wohnen / Werkzeug" for x in r["baum"]))
        code, k = self.call("/api/categories/kontor")
        rid = [x["id"] for x in k["regeln"] if x.get("quelle") == "manuell"][0]
        self.assertEqual([x["kategorie"] for x in k["regeln"] if x["id"] == rid], ["Wohnen / Werkzeug"])
        code, r = self.call("/api/categories/rule", {"loeschen": rid})
        self.assertFalse(any(x["id"] == rid for x in r["regeln"]))
        code, off3 = self.call("/api/categories/unassigned")
        self.assertFalse(any(x["name"] == "Baumarkt" for x in off3["gruppen"]))          # aus den 2 manuellen Zuordnungen wurde eine Regel gelernt
        code, k = self.call("/api/categories/kontor")
        self.assertTrue(any(x.get("name_ist") == "baumarkt" and x["quelle"] == "gelernt" for x in k["regeln"]))
        self.assertEqual(self.call("/api/categories/assign", {"ids": g["ids"][:2], "kategorie": ""})[1]["anzahl"], 2)   # manuelle Zuordnungen weg -> Regel verschwindet
        code, off4 = self.call("/api/categories/unassigned")
        self.assertEqual([x for x in off4["gruppen"] if x["name"] == "Baumarkt"][0]["anzahl"], g["anzahl"])
        # Eigene Regel ueber die API, Lernen, Einstellungen
        code, r = self.call("/api/categories/rule", {"regel": {"iban": "DE02500105170137075030", "kategorie": "Finanzierung / Annuität", "richtung": "aus"}})
        self.assertTrue(any(x.get("iban") == "DE02500105170137075030" for x in r["regeln"]))
        self.assertEqual(self.call("/api/categories/rule", {"regel": {"kategorie": "X"}})[0], 400)
        code, r = self.call("/api/categories/learn", {}); self.assertTrue(r["ok"]); self.assertIn("regeln", r["gelernt"])
        code, r = self.call("/api/categories/settings", {"mm_ueberschreiben": True})
        self.assertTrue(r["einstellungen"]["mm_ueberschreiben"])
        code, u = self.call("/api/transactions?q=VR-Bank&direction=out&limit=3&account=" + F.uid("priv.giro"))
        self.assertEqual(u["umsaetze"][0]["kategorie"], "Finanzierung / Annuität"); self.assertEqual(u["umsaetze"][0]["quelle"], "regel")   # Regel ueberschreibt 'Umbuchung'
        self.call("/api/categories/settings", {"mm_ueberschreiben": False})
        code, u = self.call("/api/transactions?q=VR-Bank&direction=out&limit=3&account=" + F.uid("priv.giro"))
        self.assertEqual(u["umsaetze"][0]["kategorie"], "Umbuchung"); self.assertEqual(u["umsaetze"][0]["quelle"], "moneymoney")
        # Kategorien aus: Bericht nutzt nur MoneyMoney
        self.call("/api/categories/settings", {"aktiv": False})
        code, ds = self.call("/api/dataset")
        self.assertEqual(ds["kategorien"]["gesamt"].get("regel", 0), 0)
        self.call("/api/categories/settings", {"aktiv": True})
        # Kontenzuordnung: alle Konten 'neu', nach Bestaetigung nicht mehr; Konto explizit in anderen Bereich
        code, ds = self.call("/api/dataset")
        self.assertTrue(len(ds["konten_neu"]) >= 10); self.assertTrue(any("ohne bestätigte Zuordnung" in w for w in ds["warnungen"]))
        neu = {k["uuid"]: k for k in ds["konten_neu"]}
        self.assertEqual(neu[F.uid("priv.depot")]["bereich"], F.uid("priv")); self.assertEqual(neu[F.uid("priv.depot")]["position"], "wertpapiere")
        code, cfg = self.call("/api/config")
        cfg["bilanz"]["konten_zuordnung"] = {k["uuid"] + " | " + k["name"]: {"bereich": k["bereich"], "position": "", "bestaetigt": True} for k in ds["konten_neu"]}
        cfg["bilanz"]["konten_zuordnung"][F.uid("priv.immo") + " | Immobilie Lindenstraße"] = {"bereich": F.uid("pb"), "position": "immobilien", "bestaetigt": True}
        self.assertEqual(self.call("/api/config", {"config": cfg}, method="PUT")[0], 200)
        self.call("/api/report/rebuild", {})
        code, ds = self.call("/api/dataset")
        self.assertEqual(ds["konten_neu"], [])
        # bestaetigte Konten ohne feste Position ("auto" aus aelterer Einrichtung) werden auf den erkannten Wert festgelegt
        zu = store_cfg = self.store.load("config.json")["bilanz"]
        self.assertTrue(all(z["position"] in core.ROLES for z in zu["konten_zuordnung"].values()))
        self.assertEqual(zu["konten_zuordnung"][F.uid("priv.giro") + " | Hausbank Giro"]["position"], "liquiditaet")
        self.assertEqual(store_cfg["verlauf"][F.uid("priv.depot") + " | Depot"], "stand")
        # Umbenennen und anderer Kontotyp in MoneyMoney verschieben die Position nicht mehr
        giro = [a for a in MockBridge.state["accounts"] if a["uuid"] == F.uid("priv.giro")][0]
        giro["name"], giro["type"] = "Hausbank Darlehen", "Darlehenskonto"
        self.run_and_wait()
        code, k = self.call("/api/accounts")
        self.assertEqual([x for x in k["konten"] if x["uuid"] == F.uid("priv.giro")][0]["rolle"], "liquiditaet")
        giro["name"], giro["type"] = "Hausbank Giro", "Girokonto"
        self.run_and_wait()
        pb_rows = {r["id"]: r for r in ds["bereiche"][F.uid("pb")]["bilanz"]["zeilen"] if not r["gruppe"]}
        self.assertIn(F.uid("priv.immo"), pb_rows); self.assertEqual(pb_rows[F.uid("priv.immo")]["rolle"], "immobilien")
        self.assertNotIn(F.uid("priv.immo"), {r["id"] for r in ds["bereiche"][ds["haupt"]]["bilanz"]["zeilen"]})
        code, k = self.call("/api/accounts")
        self.assertTrue(all(x["bestaetigt"] for x in k["konten"] if not x["gruppe"]))
        self.assertEqual([x for x in k["konten"] if x["uuid"] == F.uid("priv.immo")][0]["bereich_id"], F.uid("pb"))
        # Neues Konto in MoneyMoney -> wieder 'neu'
        accts = MockBridge.state["accounts"]
        accts.insert([a["uuid"] for a in accts].index(F.uid("priv.tr")) + 1, F.acc("priv.neu", "Neues Tagesgeld", 3, "Sparkonto", balance=5000.0, iban="DE02100100100006820102", bank="10010010"))
        self.run_and_wait()
        code, ds = self.call("/api/dataset")
        self.assertEqual([x["name"] for x in ds["konten_neu"]], ["Neues Tagesgeld"]); self.assertEqual(ds["konten_neu"][0]["bereich"], F.uid("priv"))

    def test_history_import_file(self):
        self.login(); self.run_and_wait()
        import excel
        # Matrix wie eine eigene Vermoegensuebersicht: Zeilen = Konten, Spalten = Stichtage (XLSX ohne openpyxl geschrieben und gelesen)
        wb = excel.workbook([excel.Sheet("Konten", ["", "Konto", "31.08.2026", "30.09.2026", "31.10.2026"],
                                              [["x", "Depot", 70000, 72000, 74000.5], ["y", "Fremdes Konto", 1, 2, 3], ["z", "Hausbank Giro", 100, 200, 300]])])
        code, r = self.call("/api/history/import", {"datei": base64.b64encode(wb).decode(), "name": "Vermoegen.xlsx"})
        self.assertEqual(code, 200, r)
        prev = {v["name"]: v for v in r["vorschau"]}
        self.assertEqual(prev["Depot"]["uuid"], F.uid("priv.depot")); self.assertEqual(prev["Depot"]["anzahl"], 3); self.assertIsNone(prev["Fremdes Konto"]["uuid"])
        code, r = self.call("/api/history/import", {"datei": base64.b64encode(wb).decode(), "name": "Vermoegen.xlsx", "uebernehmen": True,
                                                      "zuordnung": {"Fremdes Konto": "", "Hausbank Giro": ""}})
        self.assertEqual(r["uebernommen"], 3); self.assertEqual(r["konten"], 1)
        code, h = self.call("/api/history?account=" + F.uid("priv.depot"))
        self.assertEqual(h["manuell"]["2026-10"], 74000.5)
        code, ds = self.call("/api/dataset")
        depot = [x for x in ds["bereiche"][ds["haupt"]]["bilanz"]["zeilen"] if x["id"] == F.uid("priv.depot")][0]
        self.assertEqual(depot["werte"]["2026-09"], 72000.0); self.assertEqual(depot["werte"]["2026-11"], 85000.0)
        self.assertNotIn("geschaetzt_bis", depot); self.assertEqual(depot["fortgeschrieben_vor"], "2026-08")     # davor unbekannt, nicht geschaetzt
        # transponiert (Stichtage in der ersten Spalte) als CSV mit Monatsnamen
        csv = "Monat;Depot;Broker Giro\nJul 2026;60000;1\nJun 2026;58000;1\n"
        code, r = self.call("/api/history/import", {"csv": csv, "uebernehmen": True, "nur_luecken": True})
        self.assertEqual(r["uebernommen"], 4)
        code, h = self.call("/api/history?account=" + F.uid("priv.depot"))
        self.assertEqual(h["manuell"]["2026-07"], 60000.0); self.assertEqual(h["manuell"]["2026-10"], 74000.5)
        self.assertEqual(self.call("/api/history/import", {"csv": "nix"})[0], 400)

    def test_external_receipt_link(self):
        self.login(); self.run_and_wait()
        code, u = self.call("/api/transactions?q=supermarkt&entity=" + F.uid("priv")); tx = u["umsaetze"][0]
        other = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, other, True)
        ext = os.path.join(other, "Rechnung extern.pdf")
        with open(ext, "wb") as f:
            f.write(b"%PDF-1.4 extern")
        inside = os.path.join(self.dir, "Rechnung.pdf")             # in Kontor's data folder: never linked or handed out
        with open(inside, "wb") as f:
            f.write(b"%PDF-1.4 innen")
        self.assertEqual(self.call("/api/receipts/link", {"tx_id": tx["id"], "pfad": inside, "extern": True})[0], 400)
        code, r = self.call("/api/receipts/link", {"tx_id": tx["id"], "pfad": ext, "extern": True, "notiz": "liegt in iCloud"})
        self.assertEqual(code, 200, r); e = r["eintrag"]; self.assertTrue(e["extern"]); self.assertEqual(e["status"], "ok")
        self.assertEqual(self.call("/api/receipts/link", {"tx_id": tx["id"], "pfad": "relativ/x.pdf", "extern": True})[0], 400)
        self.assertEqual(self.call("/api/receipts/link", {"tx_id": tx["id"], "pfad": ext + ".fehlt", "extern": True})[0], 400)
        code, data, hdr = self.call("/api/receipts/file?id=" + e["id"], raw=True)
        self.assertEqual(code, 200); self.assertEqual(data, b"%PDF-1.4 extern")
        code, bl = self.call("/api/receipts")
        self.assertTrue(any(x["id"] == e["id"] and x["extern"] for x in bl["eintraege"]))
        code, r = self.call("/api/receipts/export", {"jahr": "2026", "entitaet": F.uid("priv"), "ordner_anlegen": True})
        with zipfile.ZipFile(r["datei"]) as z:
            self.assertTrue(any(n.startswith("extern/") for n in z.namelist()))
        # Entfernen loescht externe Dateien nie
        code, r = self.call("/api/receipts/remove", {"id": e["id"], "datei_loeschen": True})
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
            self.assertEqual(st["neustart_ausstehend"], "99.0.0")
        finally:
            service.version_on_disk = old

    def test_sicherung_offline_zuruecksetzen(self):
        import hashlib
        import auth
        self.login()
        # Offline-Pruefwert: eigener Salt, PBKDF2-SHA256, gleicher Hash wie WebCrypto im Browser
        code, v = self.call("/api/offline/verifier")
        self.assertEqual(code, 200); self.assertEqual(v["offline"]["rounds"], auth.OFFLINE_ROUNDS); self.assertEqual(v["sperre_minuten"], 15)
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
        self.call("/api/plan", {"bereich": P, "zeile": "Einnahmen/Einnahmen / Gehalt", "methode": "fix", "betrag": "7000", "steigerung": "2"})
        # nur verschluesselt (eigenes Passwort, mind. 8 Zeichen); Inhalt nicht lesbar
        self.assertEqual(self.call("/api/backup", {"passwort": "kurz"})[0], 400)
        code, sich = self.call("/api/backup", {"passwort": "sicherung-123"})
        self.assertEqual(code, 200); self.assertEqual(sich["kontor_sicherung_verschluesselt"], 1)
        self.assertNotIn("config", sich); self.assertNotIn("Gehalt", json.dumps(sich)); self.assertNotIn("sicherung-123", json.dumps(sich))
        import service as MA
        inner = MA.backup_decrypt(sich, "sicherung-123")
        self.assertEqual(inner["kontor_sicherung"], 1); self.assertIn("plan", inner); self.assertIn("kategorien", inner)
        self.assertEqual(inner["plan"]["bereiche"][P]["zeilen"]["Einnahmen/Einnahmen / Gehalt"]["methode"], "fix")
        self.assertNotIn("auth", inner)
        # Zuruecksetzen: nur lokal, nur mit Passwort; danach Einrichtung noetig, Passwort bleibt (ohne mit_passwort)
        self.assertEqual(self.call("/api/reset", {"passwort": "falsch"})[0], 401)
        code, r = self.call("/api/reset", {"passwort": "sehr-geheimes-passwort"})
        self.assertEqual(code, 200); self.assertFalse(r["neu_einrichten"])
        self.assertIsNone(self.store.load("config.json", None)); self.assertIsNone(self.store.load("plan.json", None))
        self.assertIsNotNone(self.store.load("auth.json", None))
        self.assertEqual(self.call("/api/status")[0], 401)      # Sitzungen verworfen
        code, sess = self.call("/api/session")
        self.assertFalse(sess["angemeldet"]); self.assertFalse(sess["einrichtung_noetig"])
        code, r = self.call("/api/login", {"passwort": "sehr-geheimes-passwort"})
        self.assertEqual(code, 200); self.csrf = r["csrf"]
        code, cfg = self.call("/api/config")
        self.assertEqual(cfg["bilanz"].get("bereiche"), core.merged_config({})["bilanz"].get("bereiche"))
        # Sicherung laden stellt Einstellungen und Plan wieder her
        self.assertEqual(self.call("/api/backup/restore", {"sicherung": sich, "passwort": "falsch-falsch"})[0], 400)
        code, r = self.call("/api/backup/restore", {"sicherung": sich, "passwort": "sicherung-123"})
        self.assertEqual(code, 200); self.assertIn("Planung", r["teile"]); self.assertIn("Einstellungen", r["teile"])
        self.assertEqual(self.store.load("plan.json")["bereiche"][P]["zeilen"]["Einnahmen/Einnahmen / Gehalt"]["methode"], "fix")
        self.assertEqual(self.call("/api/backup/restore", {"sicherung": {"x": 1}})[0], 400)

    def test_verlauf_quellen_semantik(self):
        """Umsaetze: nur Buchungen. Kontostaende (Bankkonto): eingetragene Staende sind Anker, dazwischen mit Buchungen gerechnet,
        Abweichung als Korrektur im Kapitalfluss. Vorschau im Verlauf-Fenster sofort, ohne auf den Neubau zu warten."""
        self.login(); self.run_and_wait()
        g = F.uid("priv.giro")
        code, h = self.call("/api/history?account=" + g)
        self.assertTrue(h["live"]); self.assertEqual(h["quelle"], "umsaetze")
        umsatz = h["werte"]
        self.assertEqual(umsatz["2026-11"], 12000.0)
        # Vorschau "Kontostaende" ohne eigene Werte = identisch mit Umsaetzen (Bankkonto, Anker nur heutiger Saldo)
        code, h2 = self.call("/api/history?account=%s&source=stand" % g)
        self.assertEqual(h2["werte"], umsatz)
        # Eigener Stand 2026-03 = 1.000: Monate bis 2026-03 um die Differenz verschoben, danach unveraendert
        code, r = self.call("/api/history", {"konto": g, "werte": {"2026-03": 1000}, "quelle": "stand"}, warten=False)
        self.assertEqual(r["bericht"], "angefordert"); self.assertEqual(r["historie"]["quelle"], "stand")
        w = r["historie"]["werte"]; diff = 1000.0 - umsatz["2026-03"]
        self.assertEqual(w["2026-03"], 1000.0); self.assertEqual(w["2026-01"], round(umsatz["2026-01"] + diff, 2)); self.assertEqual(w["2026-04"], umsatz["2026-04"])
        self.assertIn("2026-03", r["historie"]["anker"])
        # Umsaetze ignorieren eigene Werte
        code, h3 = self.call("/api/history?account=%s&source=umsaetze" % g)
        self.assertEqual(h3["werte"]["2026-03"], umsatz["2026-03"])
        # Nach dem Neubau: Bilanz wie Vorschau, Kapitalfluss mit Korrekturzeile, Buchungen des Kontos bleiben Zahlungsfluesse
        self.app.rebuild_report(wait=True)
        code, ds = self.call("/api/dataset"); b = ds["bereiche"][ds["haupt"]]
        row = [z for z in b["bilanz"]["zeilen"] if z["id"] == g][0]
        self.assertEqual(row["werte"]["2026-03"], 1000.0); self.assertEqual(row["werte"]["2026-01"], w["2026-01"])
        bew = [s for s in b["kapitalfluss"]["sektionen"] if s["name"] == "Bewertung"]
        korr = [z for z in (bew[0]["zeilen"] if bew else []) if "Korrektur Kontostand" in z["zeile"]]
        self.assertTrue(korr)
        self.assertAlmostEqual(sum(korr[0]["werte"].values()), -diff, places=2)       # Sprung zurueck auf die Buchungen nach dem Anker
        self.assertTrue(any(s["name"] == "Einnahmen" and s["zeilen"] for s in b["kapitalfluss"]["sektionen"]))
        # Import stellt importierte Konten auf Kontostaende um
        self.call("/api/history", {"konto": g, "werte": {}, "quelle": "umsaetze", "loeschen": True})
        code, r = self.call("/api/history/import", {"csv": "Datum;Konto;Saldo\n31.01.2026;Hausbank Giro;5.000,00\n", "uebernehmen": True})
        self.assertEqual(r["umgestellt"], 1)
        code, cfg = self.call("/api/config")
        self.assertEqual(cfg["bilanz"]["verlauf"][g + " | Hausbank Giro"], "stand")

    def test_positionen_und_ausserhalb(self):
        """Positionsvorschlaege aus Name/Typ/Gruppe; Kapitalkonten und Avale ausserhalb des Nettovermoegens; keine Depot-Schaetzung."""
        from report import account_roles

        def role(name, typ, bal, group="Privat", bank=""):
            raw = [F.acc("r", "Alle", 0, "Kontengruppe", True), F.acc("g", group, 1, "Kontengruppe", True), F.acc("x", name, 2, typ, balance=bal, bank=bank)]
            return account_roles(Ledger(accounts_from_export(raw), []), core.merged_config({}))[F.uid("x")]
        self.assertEqual(role("Immobilie Musterweg", "Festgeldanlage", 5e5), "immobilien")       # Name vor Kontotyp
        self.assertEqual(role("Darlehen Immobilie X", "Darlehenskonto", -4e5), "verbindlichkeiten")
        self.assertEqual(role("Darlehen an Firma", "Sonstiges", 1e5), "forderungen")             # Guthaben = Forderung
        self.assertEqual(role("Barkaution Mieter", "Sonstiges", -5000), "verbindlichkeiten")
        self.assertEqual(role("Kapitalkonto A", "Darlehenskonto", -1e5, group="Alpha GbR"), "verbindlichkeiten")   # in der Gesellschaft: Schuld an den Gesellschafter
        self.assertEqual(role("Kapitalkonto Alpha GbR", "Sonstiges", 1e5), "beteiligungen")                       # privat: Teil der Beteiligung (Risikokapital)
        self.assertEqual(role("Gesellschafterdarlehen Alpha", "Darlehenskonto", 5e4), "beteiligungen")            # ebenso ein Gesellschafterdarlehen
        self.assertEqual(role("Eigenkapital A", "Sonstiges", -1e5, group="Alpha GbR"), "eigenkapital")            # Eigenkapital nur ausdruecklich
        self.assertEqual(role("Mietaval Laden", "Darlehenskonto", -3e4), "eventual")
        self.assertEqual(role("Bausparer", "Sparkonto", 2e4), "anlagen")
        self.assertEqual(role("P2P-Kredite", "Sonstiges", 5e3), "anlagen")                      # P2P is an investment, not a loan
        self.assertEqual(role("Sparkonto", "Sparkonto", 2e4, group="Anlagen"), "anlagen")      # Gruppe vor allgemeinem Typ
        self.assertEqual(role("Tagesgeld", "Sparkonto", 1e3, group="Liquidität"), "liquiditaet")
        self.assertEqual(role("Girokonto", "Girokonto", 1e3, group="Anlagen"), "liquiditaet")  # eindeutiger Typ vor Gruppe
        self.assertEqual(role("Haushaltskasse", "Bargeld", 300), "liquiditaet")
        self.assertEqual(role("Kreditkarte", "Kreditkarte", -300), "liquiditaet")
        self.login(); self.run_and_wait()
        code, ds = self.call("/api/dataset"); pb = ds["bereiche"][F.uid("pb")]
        self.assertEqual(pb["bilanz"]["ausserhalb"], [])                                   # Kapitalkonten zaehlen als Schuld der GbR
        rows = {r["id"]: r for r in pb["bilanz"]["zeilen"]}
        self.assertEqual(rows[F.uid("pb.kap.s")]["rolle"], "verbindlichkeiten")
        saldo = {k["uuid"]: k["saldo"] for k in ds["konten"] if not k["gruppe"]}
        self.assertEqual(pb["bilanz"]["nettovermoegen"]["2026-11"], round(sum(saldo[F.uid(k)] for k in ("pb.kk", "pb.immo", "pb.vd", "pb.kap.s", "pb.kap.p")), 2))
        code, h = self.call("/api/history?account=" + F.uid("priv.depot"))
        self.assertNotIn("geschaetzt_bis", h); self.assertIn("fortgeschrieben", h["hinweis"])          # keine Schaetzung mehr
        # Pruefung im Verlauf-Fenster: Anfangssaldo und Buchungen
        code, h = self.call("/api/history?account=" + F.uid("priv.giro"))
        self.assertIn("anfangssaldo", h["pruefung"]); self.assertGreater(h["pruefung"]["buchungen"], 0)

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
        self.assertTrue(st["moneymoney"]["aus_zwischenspeicher"]); self.assertIsNotNone(st["moneymoney"]["stand"])

    def test_bericht_im_hintergrund(self):
        """Verlauf-Aenderungen stossen den Neubau nur an; mehrere Anstoesse ergeben einen Lauf; Status zeigt den Fortschritt."""
        self.login(); self.run_and_wait()
        code, st = self.call("/api/status")
        self.assertFalse(st["bericht"]["laeuft"]); self.assertIn("gesperrt", st["moneymoney"])
        uuid = F.uid("priv.depot")
        for v in ("70000", "71000", "72000"):
            code, r = self.call("/api/history", {"konto": uuid, "werte": {"2026-09": v}}, warten=False)
            self.assertEqual(code, 200); self.assertEqual(r["bericht"], "angefordert")
        for _ in range(300):
            code, st = self.call("/api/status")
            if not st["bericht"]["laeuft"] and st["bericht"]["stand"]:
                break
            time.sleep(0.1)
        self.assertFalse(st["bericht"]["laeuft"]); self.assertIsNone(st["bericht"]["fehler"]); self.assertIn("Verlauf", st["bericht"]["grund"])
        code, ds = self.call("/api/dataset")
        row = [z for z in ds["bereiche"][F.uid("priv")]["bilanz"]["zeilen"] if z["id"] == uuid][0]
        self.assertEqual(row["werte"]["2026-09"], 72000.0)
        # Doppelte Pruefung wird abgewiesen, abgebrochene Verbindung bringt den Dienst nicht aus dem Tritt
        self.app.check_lock.acquire()
        try:
            self.assertEqual(self.call("/api/check", {})[0], 409)
        finally:
            self.app.check_lock.release()
        self.assertEqual(self.call("/api/check", {})[0], 200)
        # Fortschritt beim Lesen: Schritte gemeldet, Dauer je Schritt fuer die naechste Schaetzung gemerkt
        code, p = self.call("/api/check/status")
        self.assertFalse(p["laeuft"]); self.assertEqual(p["schritt"], "done")
        self.assertEqual(set(self.store.load("state.json")["lesen_dauer"]), {"accounts", "transactions", "parse", "portfolios", "categories", "save"})

    def test_tls_helpers(self):
        import tls_cert
        self.assertIsNone(tls_cert.cert_expiry(os.path.join(self.dir, "fehlt.crt")))
        cfg = {"oberflaeche": {"tls_cert": "/irgendwo/fremd.crt"}}
        self.assertFalse(tls_cert.renew_if_due(cfg, self.dir))                 # fremde Zertifikate werden nicht angefasst
        self.assertFalse(tls_cert.renew_if_due({"oberflaeche": {}}, self.dir))


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
                pg.wait_for_selector(".cards")
                txt = pg.query_selector("#main").inner_text().lower()
                for needle in ("nettovermögen", "jahresvergleich", "offene punkte", "weitere bereiche", "vermögensstruktur"):
                    self.assertIn(needle, txt)
                if shots: pg.screenshot(path=os.path.join(shots, "ui_uebersicht.png"), full_page=True)
                # Datenstand unten links (zweistufig), keine Infozeile mehr in der Übersicht, Synchronisieren
                sm = pg.query_selector("#status-mini").inner_text()
                self.assertIn("Banken → MM", sm); self.assertIn("MM → Kontor", sm); self.assertNotIn("nächster", sm)
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
                runs_vorher = len(store.load("state.json").get("verlauf", []))
                self.assertIn("keine Änderung", sync())
                self.assertEqual(len(store.load("state.json").get("verlauf", [])), runs_vorher)      # ohne Änderung kein neuer Regellauf
                self.assertFalse(pg.query_selector("#sync-btn").is_disabled())
                # Bereichsauswahl steht oben rechts an derselben Stelle, egal wie lang der Seitentitel ist
                x_ueb = pg.evaluate("document.querySelector('#bereich-seg').getBoundingClientRect().right")
                pg.click("#nav a[href='#planning']"); pg.wait_for_selector("#main .toolbar #modus-seg")
                self.assertEqual(x_ueb, pg.evaluate("document.querySelector('#bereich-seg').getBoundingClientRect().right"))
                self.assertNotIn("Privat", pg.query_selector("#main .toolbar").inner_text())            # Bereich nicht doppelt genannt
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".cards")
                # Status unten links fuehrt zur Seite Synchronisierung
                pg.click("#status-mini .sm-link"); pg.wait_for_selector(".sync-table")
                self.assertIn("Offline-Konten", pg.query_selector("#main").inner_text()); self.assertIn("Verkäuferdarlehen", pg.query_selector_all(".sync-table")[-1].inner_text())
                self.assertIn("Depots: Wertverlauf", pg.query_selector("#main").inner_text()); self.assertTrue(pg.query_selector(".dep-hist"))
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".cards")
                # Bereich wechseln
                pg.click("#bereich-seg button:nth-child(2)"); pg.wait_for_timeout(500)
                self.assertEqual(pg.evaluate("document.querySelector('#bereich-seg .on').textContent"), "Alpha GbR")
                if shots: pg.screenshot(path=os.path.join(shots, "ui_uebersicht_gbr.png"), full_page=True)
                pg.click("#bereich-seg button:nth-child(1)"); pg.wait_for_timeout(300)
                for tab in ("balance", "cashflow", "planning", "properties", "tax", "transactions", "bookings", "sync", "setup", "rules", "categories", "settings", "updates", "log", "help"):
                    pg.click("#nav a[href='#%s']" % tab); pg.wait_for_timeout(400)
                    self.assertTrue(pg.query_selector("#main").inner_html().strip(), tab)
                    if shots: pg.screenshot(path=os.path.join(shots, "ui_%s.png" % tab), full_page=(tab in ("rules", "settings", "tax", "planning", "help", "balance", "setup")))
                # Bilanz: Positionen/Gruppen, inaktive, Konto-Klick -> Verlauf
                pg.click("#nav a[href='#balance']"); pg.wait_for_selector("tr.pos")
                self.assertIn("Bankguthaben", pg.query_selector("#main").inner_text())
                # pages not fully tested yet carry "Alpha" in the menu and at the title; the balance sheet does not
                self.assertTrue(pg.query_selector("#nav a.alpha[href='#cashflow'] .alpha-tag")); self.assertIsNone(pg.query_selector("#nav a[href='#balance'] .alpha-tag"))
                self.assertIsNone(pg.query_selector("#page-title .alpha-tag")); self.assertTrue(pg.query_selector("#nav a.alpha[href='#rules']"))
                self.assertEqual(pg.inner_text("#nav a[href='#rules'] span"), "Buchungsregeln"); self.assertEqual(pg.inner_text("#nav a[href='#bookings'] span"), "Auto-Buchungen")
                # eine Tabelle: Positionen zugeklappt, aufklappbar; Plan-Spalten rechts in derselben Tabelle
                self.assertEqual(len(pg.query_selector_all("#main table")), 1); self.assertIsNone(pg.query_selector("tr.acct"))
                self.assertTrue(pg.query_selector("#main thead th.plan")); self.assertNotIn("Fortschreibung", pg.query_selector("#main").inner_text())
                pg.click("tr.pos[data-pos='liquiditaet'] td:first-child"); pg.wait_for_selector("tr.acct")
                pg.click("#pos-all"); pg.wait_for_timeout(300)
                # single curves below the table: net worth and a chosen sum (default cash + tradable + fixed-term); chips change the sum
                self.assertTrue(pg.query_selector("#lc-nw-svg path.bch-nw")); self.assertTrue(pg.query_selector("#lc-sel-svg path.bch-nw"))
                self.assertEqual(pg.inner_text("#lc-sel-title"), "Liquides Vermögen")      # a known combination gets its name
                # the selection named in words, never in codes: groups, "+", "ohne"; shortened words only in the small chart
                av = ['liquiditaet', 'wertpapiere', 'anlagen', 'immobilien', 'beteiligungen', 'verbindlichkeiten']
                name = lambda sel, big=True: pg.evaluate("([s, a, l]) => lcSelTitle(s, a, l)[0]", [sel, av, big])
                self.assertEqual(name(['liquiditaet', 'wertpapiere', 'anlagen', 'verbindlichkeiten']), "Geldanlagen + Verbindlichkeiten")
                self.assertEqual(name(['liquiditaet', 'wertpapiere', 'anlagen', 'verbindlichkeiten'], False), "Geldanlagen + Verbindl.")
                self.assertEqual(name([r for r in av if r != 'beteiligungen']), "Nettovermögen ohne Beteiligungen")
                self.assertEqual(name(['liquiditaet', 'wertpapiere', 'anlagen', 'immobilien']), "Geldanlagen + Immobilien")      # a tie: in plus
                self.assertEqual(name(['liquiditaet', 'immobilien']), "Bankguthaben + Immobilien"); self.assertEqual(name(av), "Nettovermögen")
                pg.hover("#lc-sel-title"); pg.wait_for_selector(".tip"); self.assertIn("Bankguthaben + Wertpapiere", pg.inner_text(".tip")); self.assertIn("+ Wertpapiere\n= Liquides Vermögen", pg.inner_text(".tip")); pg.mouse.move(5, 5)
                # the names as one written sum, each word once
                self.assertEqual(pg.evaluate("a => lcSumTip(a)", av).split("\n"), ["\u2007 Bankguthaben", "+ Wertpapiere", "= Liquides Vermögen", "+ Festanlagen", "= Geldanlagen", "+ Beteiligungen",
                                 "= Geldvermögen", "+ Immobilien", "= Bruttovermögen (Bilanzsumme)", "+ Verbindlichkeiten", "= Nettovermögen", "",
                                 "Gebundenes Verm. = Bruttoverm. − Liquides Verm."])
                self.assertIn("+ Sachvermögen (Immobilien + Sachwerte)", pg.evaluate("a => lcSumTip(a)", av + ["sachwerte"]))
                # composition of one position by account (stacked), chips with the accounts: deselecting one keeps the position line
                self.assertTrue(pg.query_selector("#lc-pos-svg path.lc-band")); self.assertIn("Hausbank Giro", pg.inner_text("#lc-pos-accs"))
                tot = pg.get_attribute("#lc-pos-svg path.lc-total", "d"); nb = len(pg.query_selector_all("#lc-pos-svg path.lc-band"))
                pg.click("#lc-pos-accs label:has-text('Hausbank Giro')"); pg.wait_for_timeout(200)
                self.assertLess(len(pg.query_selector_all("#lc-pos-svg path.lc-band")), nb); self.assertEqual(pg.get_attribute("#lc-pos-svg path.lc-total", "d"), tot)
                bb = pg.query_selector("#lc-pos-hit").bounding_box(); pg.mouse.move(bb["x"] + bb["width"] - 40, bb["y"] + 60); pg.wait_for_timeout(150)
                self.assertIn("Auswahl", pg.inner_text("#lc-pos-tip")); pg.mouse.move(5, 5)
                # portfolios broken down into their securities: only offered where a portfolio of the position has them
                self.assertFalse(pg.is_visible("#lc-pos-mode"))
                pg.select_option("#lc-pos-sel", "wertpapiere"); pg.wait_for_timeout(200)
                self.assertTrue(pg.is_visible("#lc-pos-mode")); pg.click("#lc-pos-mode"); pg.wait_for_timeout(200)
                pg.evaluate("lcSet('pos', LC.pos.i0, LC.pos.d.ist - 1)"); pg.wait_for_timeout(100)     # the made-up securities exist only this month
                self.assertIn("Welt-ETF", pg.inner_text("#lc-pos-accs")); pg.click("#lc-pos-mode"); pg.wait_for_timeout(200)
                self.assertNotIn("Welt-ETF", pg.inner_text("#lc-pos-accs"))
                pg.select_option("#lc-pos-sel", "verbindlichkeiten"); pg.wait_for_timeout(200)
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
                pg.click("#modus-seg button[data-m='jahre']"); pg.wait_for_timeout(300)
                pg.reload(); pg.wait_for_selector("#bch"); self.assertIsNone(pg.query_selector("#bch.big-sel")); self.assertEqual(order(), ["nw", "sel", "pos"])
                self.assertTrue(pg.query_selector("#modus-seg button[data-m='monate'].on"))
                pg.click(".lc[data-lc='pos'] .lc-big"); pg.wait_for_selector("#bch.big-pos"); pg.click("#modus-seg button[data-m='jahre']"); pg.wait_for_timeout(300)
                pg.click("#bch-rb button[data-m='120']"); pg.wait_for_timeout(200); pg.click("#view-save"); pg.wait_for_timeout(200)
                pg.reload(); pg.wait_for_selector("#bch.big-pos"); self.assertEqual(order(), ["nw", "sel", "bil"])
                self.assertTrue(pg.query_selector("#modus-seg button[data-m='jahre'].on")); self.assertTrue(pg.query_selector("#bch-rb button[data-m='120'].on"))
                # one default each for months and years: the one saved last opens, switching takes the other one's ranges
                pg.click("#modus-seg button[data-m='monate']"); pg.wait_for_timeout(300); self.assertTrue(pg.query_selector("#bch-rb button[data-m='12'].on"))     # large chart: 1 J
                pg.click("#bch-rb button[data-m='36']"); pg.wait_for_timeout(200); pg.click("#view-save"); pg.wait_for_timeout(200)
                pg.click("#modus-seg button[data-m='jahre']"); pg.wait_for_timeout(300); self.assertTrue(pg.query_selector("#bch-rb button[data-m='120'].on"))
                pg.reload(); pg.wait_for_selector("#bch"); self.assertTrue(pg.query_selector("#modus-seg button[data-m='monate'].on")); self.assertTrue(pg.query_selector("#bch-rb button[data-m='36'].on"))
                pg.click("#view-reset"); pg.wait_for_timeout(300)
                self.assertIsNone(pg.query_selector("#bch.big-pos")); self.assertEqual(order(), ["nw", "sel", "pos"]); self.assertTrue(pg.query_selector("#modus-seg button[data-m='monate'].on"))
                self.assertIsNone(pg.evaluate("localStorage.getItem('kontor.bilanzView')"))
                pg.click("#pos-all"); pg.wait_for_timeout(300)                       # all positions open again (as before)
                # table and large chart can be moved up and down (small arrows in their headers), kept with "Ansicht speichern"
                order3 = lambda: pg.evaluate("""() => [...document.querySelectorAll('#main #bch, #main .wrap.bil-tbl, #main #lc-grid')].map(e => e.id === 'bch' ? 'chart' : e.id === 'lc-grid' ? 'lines' : 'table')""")
                tbl = lambda mv: ".wrap .th-mv[data-blk='table'][data-mv='%s']" % mv
                self.assertEqual(order3(), ["chart", "table", "lines"]); pg.click(tbl(-1)); pg.wait_for_timeout(300); self.assertEqual(order3(), ["table", "chart", "lines"])
                self.assertFalse(pg.is_visible(tbl(-1))); pg.click(tbl(1)); pg.wait_for_timeout(300); pg.click(tbl(1)); pg.wait_for_timeout(300)
                self.assertEqual(order3(), ["chart", "lines", "table"])
                pg.click("#bch .th-mv[data-blk='chart'][data-mv='1']"); pg.wait_for_timeout(300); self.assertEqual(order3(), ["lines", "chart", "table"])
                pg.click("#view-save"); pg.wait_for_timeout(200)
                self.assertEqual(pg.evaluate("JSON.parse(localStorage.getItem('kontor.bilanzView')).views.monate.blocks"), ["lines", "chart", "table"])
                pg.click("#view-reset"); pg.wait_for_timeout(300); self.assertEqual(order3(), ["chart", "table", "lines"]); pg.click("#pos-all"); pg.wait_for_timeout(300)
                # the same in the table: a portfolio opens into its securities (without opening the account's history)
                if not pg.query_selector("[data-dep]"):
                    pg.click("tr.pos[data-pos='wertpapiere'] td:first-child")
                pg.wait_for_selector("[data-dep]"); pg.click("[data-dep]"); pg.wait_for_selector("tr.wpr")
                self.assertIn("Welt-ETF", pg.inner_text("#main table")); self.assertFalse(pg.query_selector("#drawer.open"))
                self.assertTrue(any("ISIN IE00B4L5Y983" in x for x in pg.eval_on_selector_all("tr.wpr td:first-child", "ts => ts.map(t => t.title)")))      # MoneyMoney's identity always on hover
                checked = {x.get_attribute("data-r") for x in pg.query_selector_all("#lc-chips input:checked")}
                self.assertIn("liquiditaet", checked); self.assertTrue(checked <= {"liquiditaet", "wertpapiere", "anlagen"})
                v0 = pg.inner_text("#lc-sel-val"); pg.click("#lc-chips input[data-r='immobilien']"); pg.wait_for_timeout(200)
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
                # old German addresses lead to the English ones
                pg.evaluate("location.hash = '#einrichtung/konten'"); pg.wait_for_timeout(400)
                self.assertEqual(pg.evaluate("location.hash"), "#setup/accounts")
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
                pg.evaluate("window.scrollTo(0, 0)"); pg.wait_for_timeout(100)
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
                    .sort((a, b) => b[1].width * b[1].height - a[1].width * a[1].height); const [p, r] = ps[0]; return [r.left + r.width / 2, r.top + r.height / 2, BCH.d.series[+p.dataset.s].rolle]; }"""
                x, y, role = pg.evaluate("() => (%s)(x => x.acc && !x.dep)" % centre)
                pg.mouse.click(x, y); pg.wait_for_timeout(400); self.assertFalse(pg.evaluate("r => !!S.posOpen[r]", role))
                self.assertTrue(pg.is_visible("#bch-tip")); self.assertTrue(pg.query_selector("#bch-svg.hl"))      # still under the mouse, without moving it
                x, y, _ = pg.evaluate("r => (%s)(x => x.pos && x.rolle === r)" % centre, role)
                pg.mouse.click(x, y); pg.wait_for_timeout(400); self.assertTrue(pg.evaluate("r => !!S.posOpen[r]", role))
                n_acc = pg.evaluate("r => BCH.d.series.filter(x => x.rolle === r && document.querySelector(`#bch-svg .bch-area[data-s=\"${BCH.d.series.indexOf(x)}\"]`)).length", role)
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
                self.assertIn("Eigenkapitalquote", pg.inner_text("#drawer")); self.assertIn("Alpha GbR: 49 % von", pg.inner_text("#drawer"))
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
                pg.click("#modus-seg button[data-m='jahre']"); pg.wait_for_timeout(300)
                self.assertIsNotNone(pg.query_selector("#main thead th[data-cur]"))
                pg.click("#modus-seg button[data-m='monate']"); pg.wait_for_timeout(300)
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
                pg.click("#page-title"); pg.wait_for_selector("#drawer:not(.open)")                        # Klick daneben schliesst
                pg.click("tr.acct[data-id='%s'] td" % F.uid("priv.depot")); pg.wait_for_selector("#drawer.open #h-grid")
                pg.fill("#drawer input[data-mk='2026-09']", "77000"); pg.click("#h-save"); pg.wait_for_timeout(1200)
                if shots: pg.screenshot(path=os.path.join(shots, "ui_verlauf_drawer.png"))
                pg.keyboard.press("Escape")
                self.assertEqual(store.load("state.json")["historie"][F.uid("priv.depot")]["2026-09"], 77000.0)
                # Einrichtung: Bausteine, Positionen-Editor speichern
                pg.click("#nav a[href='#setup']"); pg.wait_for_selector(".setup-list")
                self.assertIn("Bereiche", pg.query_selector("#main").inner_text())
                pg.goto("http://127.0.0.1:%d/#setup/accounts" % port); pg.wait_for_selector("#save-konten")
                for _ in range(2):          # "Verlauf..." laesst sich wiederholt oeffnen
                    pg.click("tr[data-uuid='%s'] .k-hist" % F.uid("priv.depot")); pg.wait_for_selector("#drawer.open #h-grid")
                    pg.keyboard.press("Escape"); pg.wait_for_selector("#drawer:not(.open)")
                # Im Verlauf-Fenster die Quelle wechseln (Umsätze <-> Stände), danach ein anderes Konto oeffnen
                pg.click("tr[data-uuid='%s'] .k-hist" % F.uid("priv.giro")); pg.wait_for_selector("#drawer.open #h-grid")
                pg.click("#drawer .hq-q[data-q='stand']"); pg.wait_for_selector("#drawer.open .hq-q.on[data-q='stand']", timeout=1000)     # sofort
                for _ in range(150):           # CSP verbietet wait_for_function mit Intervall -> selbst abfragen
                    if not pg.evaluate("document.querySelector('#drawer .hq-q').disabled"):
                        break
                    pg.wait_for_timeout(100)
                # erst Vorschau: nichts gespeichert, Tabelle unveraendert, Hinweis + Speichern/Verwerfen
                self.assertIn("Vorschau", pg.query_selector("#hq-pending").inner_text()); self.assertTrue(pg.is_visible("#h-undo"))
                self.assertEqual(pg.eval_on_selector("tr[data-uuid='%s'] .k-verlauf" % F.uid("priv.giro"), "e => e.value"), "umsaetze")
                self.assertNotEqual((store.load("config.json")["bilanz"].get("verlauf") or {}).get(F.uid("priv.giro") + " | Hausbank Giro"), "stand")
                self.assertEqual(pg.evaluate("getComputedStyle(document.querySelector('#h-grid')).gridTemplateColumns.split(' ').length"), 1)   # Monate untereinander
                pg.click("#h-save"); pg.wait_for_timeout(800)
                self.assertEqual(pg.eval_on_selector("tr[data-uuid='%s'] .k-verlauf" % F.uid("priv.giro"), "e => e.value"), "stand")          # nach Speichern zieht die Tabelle mit
                self.assertEqual(pg.query_selector("#hq-pending").inner_text(), "")
                pg.keyboard.press("Escape"); pg.wait_for_selector("#drawer:not(.open)")
                pg.click("tr[data-uuid='%s'] .k-hist" % F.uid("priv.giro")); pg.wait_for_selector("#drawer.open .hq-q.on[data-q='stand']", timeout=10000)   # bleibt beim erneuten Oeffnen
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
                pg.click("#drawer .hq-q[data-q='umsaetze']"); pg.wait_for_selector("#drawer.open .hq-q.on[data-q='umsaetze']", timeout=10000)
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
                neu_row = "tr.neu[data-uuid]"
                if pg.query_selector(neu_row):
                    sel = neu_row + " .k-rolle"; vor = pg.get_attribute(sel, "data-vor")
                    self.assertIn("vorschlag", pg.get_attribute(sel, "class"))
                    pg.select_option(sel, "sonstiges" if vor != "sonstiges" else "anlagen"); self.assertNotIn("vorschlag", pg.get_attribute(sel, "class"))
                    pg.select_option(sel, vor); self.assertIn("vorschlag", pg.get_attribute(sel, "class"))
                # Konten nach Bereichen gruppiert, in der Reihenfolge der Bereiche
                groups = pg.evaluate("[...document.querySelectorAll('.acct-table tr.bgroup td')].map(t => t.textContent)")
                self.assertEqual(groups[:3], ["Privat", "Alpha GbR", "Beta GbR"])
                # Auswahlfelder gleich breit -> "Verlauf…" steht sauber untereinander
                xs = pg.evaluate("[...document.querySelectorAll('.acct-table .k-hist')].map(b => Math.round(b.getBoundingClientRect().left))")
                self.assertEqual(len(set(xs)), 1, xs)
                self.assertLessEqual(pg.evaluate("document.querySelector('.acct-table').scrollWidth"), pg.evaluate("document.querySelector('#main').clientWidth"))   # passt in die Breite
                pg.select_option("tr[data-uuid='%s'] .k-rolle" % F.uid("priv.immo"), "immobilien")
                self.assertIsNone(pg.query_selector("#k-neu"))                                          # kein "Bericht aktualisieren" im Einrichtungsschritt
                pg.click("#save-konten"); pg.wait_for_selector("#findings-k2 .ok", timeout=20000); pg.wait_for_timeout(1500)
                self.assertTrue(pg.evaluate("document.querySelector('#bereich-seg').classList.contains('hidden')"))   # Bereichsleiste nur in den Auswertungen
                self.assertIn("Gespeichert", pg.query_selector("#findings-k2").inner_text())
                bil = store.load("config.json")["bilanz"]
                self.assertEqual(bil["rollen"][F.uid("priv.immo") + " | Immobilie Lindenstraße"], "immobilien")
                self.assertEqual(bil["konten_zuordnung"][F.uid("priv.giro") + " | Hausbank Giro"]["position"], "liquiditaet")    # fest gespeichert
                self.assertTrue(all(v in ("umsaetze", "stand") for v in bil["verlauf"].values()) and len(bil["verlauf"]) >= 10)
                if shots: pg.screenshot(path=os.path.join(shots, "ui_einrichtung_konten.png"), full_page=True)
                # Immobilien: Objekt + Kalkulation anlegen, Ergebnis, speichern, Jahrestabelle
                pg.goto("http://127.0.0.1:%d/#properties" % port); pg.wait_for_selector("#im-new")
                pg.once("dialog", lambda d: d.accept("Parkweg")); pg.click("#im-new"); pg.wait_for_selector("#im-kalk-new")
                pg.once("dialog", lambda d: d.accept("Basis")); pg.click("#im-kalk-new"); pg.wait_for_selector("#im-calc")
                pg.fill("input[data-p='kaufpreis']", "1900000"); pg.fill("input[data-p='miete.nettokalt_monat']", "12600")
                pg.click("#im-loan-add"); pg.wait_for_selector(".loan-box")
                pg.fill(".loan-box input[data-p='darlehen.0.betrag']", "1600000"); pg.fill(".loan-box input[data-p='darlehen.0.annuitaet_monat']", "8250")
                pg.click("#im-calc"); pg.wait_for_timeout(900)
                self.assertIn("Kaufpreisfaktor", pg.query_selector("#im-result").inner_text())
                pg.click("#im-kalk-save"); pg.wait_for_timeout(1500)
                cfg_im = store.load("config.json")["immobilien"]
                self.assertEqual(cfg_im[0]["kalkulationen"][0]["eingaben"]["kaufpreis"], 1900000)
                self.assertEqual(cfg_im[0]["kalkulationen"][0]["eingaben"]["darlehen"][0]["betrag"], 1600000)
                if shots: pg.screenshot(path=os.path.join(shots, "ui_immobilie.png"), full_page=True)
                pg.click(".tabs button[data-t='jahre']"); pg.wait_for_timeout(500)
                self.assertIn("Restschuld", pg.query_selector("#main").inner_text())
                pg.click(".tabs button[data-t='dokumente']"); pg.wait_for_timeout(300)
                self.assertIn("Dokumente", pg.query_selector("#main").inner_text())
                pg.click("#nav a[href='#properties']"); pg.wait_for_selector(".card[data-im]")
                if shots: pg.screenshot(path=os.path.join(shots, "ui_immobilien.png"), full_page=True)
                # Zuordnen: offene Gegenpartei mit Regel zuordnen -> verschwindet, Kategorien-Seite zeigt Regel
                pg.click("#nav a[href='#categories']"); pg.wait_for_selector(".kz-group")
                n_before = len(pg.query_selector_all(".kz-group"))
                box = pg.query_selector(".kz-group"); box.query_selector(".kz-kat").fill("Haushalt / Werkzeug"); box.query_selector(".kz-save").click()
                pg.wait_for_timeout(1500)
                self.assertLess(len(pg.query_selector_all(".kz-group")), n_before)
                if shots: pg.screenshot(path=os.path.join(shots, "ui_zuordnen.png"), full_page=True)
                pg.click("#main .tabs button[data-next='#categories/rules']"); pg.wait_for_selector("#kk-add")
                self.assertIn("Haushalt / Werkzeug", pg.query_selector("#main").inner_text())
                if shots: pg.screenshot(path=os.path.join(shots, "ui_kategorien.png"), full_page=True)
                # Planung: Ereignis anlegen -- erst wenn die Neuberechnung nach dem Zuordnen fertig und geladen ist (sonst baut
                # das Nachladen die Seite waehrend der Eingabe neu auf)
                for _ in range(60):                 # asks for the status itself instead of waiting for the next poll (every 30 s)
                    if pg.evaluate("async () => { try { await pollStatus(); } catch (e) {} return !!S.STATUS && !(S.STATUS.bericht || {}).laeuft && (S.STATUS.bericht || {}).stand === BER.stand; }"):
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
                pg.click("#modus-seg button[data-m='jahre']"); pg.wait_for_timeout(400)
                self.assertIn("2026", pg.query_selector("#main thead").inner_text())
                if shots: pg.screenshot(path=os.path.join(shots, "ui_kapitalfluss_jahre.png"))
                pg.click("#modus-seg button[data-m='monate']"); pg.wait_for_timeout(200)
                # Planung: Methode setzen
                pg.click("#nav a[href='#planning']"); pg.wait_for_selector(".edit")
                first = pg.query_selector(".edit"); first.query_selector(".meth").select_option("fix"); first.query_selector(".betrag").fill("1234"); first.query_selector(".save").click()
                pg.wait_for_timeout(800)
                self.assertIn("1.234,00", pg.query_selector("#main").inner_text())
                # Umsaetze: Zeile oeffnen -> Drawer
                pg.click("#nav a[href='#transactions']"); pg.wait_for_selector("#ums-table tbody tr")
                pg.click("#ums-table tbody tr td:nth-child(4)"); pg.wait_for_selector("#drawer.open"); pg.wait_for_timeout(400)
                self.assertIn("Belege", pg.query_selector("#drawer").inner_text())
                if shots: pg.screenshot(path=os.path.join(shots, "ui_umsaetze_drawer.png"))
                pg.keyboard.press("Escape")
                # Regeln speichern (unveraendert) -> Befunde ok
                pg.click("#nav a[href='#rules']"); pg.wait_for_selector("#save-rules")
                auto = pg.evaluate("S.CFG.probelauf === false"); self.assertEqual(pg.is_checked("#auto-book"), auto)      # the setting as a switch at the top
                self.assertIn("Kontor bucht" if auto else "Freigabe", pg.inner_text(".set-row"))
                pg.click("#nav a[href='#bookings']"); pg.wait_for_selector(".mode-chip"); self.assertIn("Vollautomatisch" if auto else "Mit Freigabe", pg.inner_text(".mode-chip"))
                self.assertIsNone(pg.query_selector("#run-dry"))              # checked at every sync, no button of its own
                n_wait = pg.evaluate("((S.STATUS.letzter_lauf || {}).probelauf && (S.STATUS.letzter_lauf.vorschlaege || []).length) || 0")
                self.assertEqual(pg.evaluate("(document.querySelector('#nav a[href=\"#bookings\"] .nbadge') || {}).textContent || ''"), str(n_wait) if n_wait else "")
                pg.evaluate("window.__st = S.STATUS; S.STATUS = Object.assign({}, S.STATUS, {letzter_lauf: {probelauf: true, zeit: 'x', vorschlaege: [{}, {}, {}]}, update: {neuer: true, verfuegbar: '9.9.9'}}); statusMini()")
                self.assertEqual(pg.inner_text("#nav a[href='#bookings'] .nbadge"), "3"); self.assertTrue(pg.query_selector("#nav a[href='#updates'] .nbadge"))
                pg.evaluate("S.STATUS = Object.assign({}, S.STATUS, {letzter_lauf: {probelauf: true, zeit: 'x', vorschlaege: Array(250).fill({})}}); statusMini()")
                self.assertEqual(pg.inner_text("#nav a[href='#bookings'] .nbadge"), "99+")
                self.assertNotIn("Freigabe", pg.inner_text("#status-mini")); self.assertIsNone(pg.query_selector("#nav a[href='#bookings'] .alpha-tag"))
                pg.evaluate("S.STATUS = window.__st; statusMini()")
                pg.click(".mode-chip"); pg.wait_for_selector("#save-rules")
                # companies come from the areas: one card each with its share, the participation chosen, target/actual live
                self.assertEqual(pg.eval_on_selector_all(".co-card h3", "e => e.map(x => x.textContent)"), ["Alpha GbR", "Beta GbR"])
                self.assertIn("49", pg.inner_text(".co-card .co-head"))
                self.assertEqual(pg.eval_on_selector(".co-card .c-bet", "e => e.value").split(" | ")[0], F.uid("priv.bet.pb"))
                pg.wait_for_function("(document.querySelector('.co-card [data-pv=\"b\"]') || {}).textContent?.includes('Soll')", timeout=8000)
                self.assertGreaterEqual(len(pg.query_selector_all(".co-card .hq")), 6); self.assertGreaterEqual(len(pg.query_selector_all("#loans .hq")), 15)
                self.assertTrue(pg.is_disabled("#save-rules"))
                # participation: only offline accounts with the position "Beteiligungen"; a suggestion only when exactly one fits the name
                opts = pg.eval_on_selector_all(".co-card:first-child .c-bet option", "e => e.map(o => o.textContent)")
                self.assertEqual(opts[1:], ["Beteiligung an Alpha GbR", "Beteiligung an Beta GbR"])
                card = """n => { const keep = S.CFG.gesellschaften; S.CFG.gesellschaften = []; const d = document.createElement('div'); d.innerHTML = companyCard({id: 'x', name: n, anteil: 0.5}, {}); S.CFG.gesellschaften = keep; return [d.querySelector('.c-bet').value, !!d.querySelector('.sug')]; }"""
                v, sug = pg.evaluate(card, "Beta GbR"); self.assertTrue(sug); self.assertEqual(v.split(" | ")[0], F.uid("priv.bet.shs"))
                self.assertEqual(pg.evaluate(card, "Gamma GbR"), ["", False]); self.assertEqual(pg.evaluate(card, "GbR"), ["", False])
                # an incomplete counter account is not saved
                pg.click(".co-card .add-gk"); pg.select_option(".gk-row .g-konto", index=1); pg.click("#save-rules"); pg.wait_for_timeout(300)
                self.assertTrue(pg.query_selector(".gk-row.invalid")); self.assertNotIn("gegenkonten", json.dumps(store.load("config.json")["gesellschaften"]))
                pg.click(".gk-row .gk-del")
                pg.click(".co-card .co-more summary"); pg.fill(".co-card .c-sw", "1")
                pg.keyboard.press("Meta+s"); pg.wait_for_timeout(900)          # ⌘S saves
                self.assertIn("Gespeichert", pg.query_selector("#findings").inner_text())
                self.assertEqual(store.load("config.json")["gesellschaften"][0]["schwelle"], 1); self.assertTrue(pg.is_disabled("#save-rules"))
                # Sync: online or offline per account as a menu; offline accounts recognised as "Offline-Konto"
                self.assertFalse(pg.evaluate("DIRTY.on"))
                pg.click("#nav a[href='#sync']"); pg.wait_for_selector(".ab-sel")          # leaving after ⌘S: no question (a late change event does not count)
                self.assertIn("Offline-Konto", pg.inner_text("#main")); self.assertIn("Offline-Konten", pg.inner_text("#main"))
                self.assertEqual(pg.eval_on_selector("tr[data-uuid='%s'] .ab-sel" % F.uid("priv.bet.pb"), "e => e.value"), "offline")
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
                pg.reload(); pg.wait_for_selector(".cards")           # jetzt laufen alle Abrufe durch den Service Worker
                pg.wait_for_function("caches.open('kontor-data-enc').then(c => c.keys()).then(k => k.some(r => r.url.endsWith('/api/offline/verifier')) && k.some(r => r.url.endsWith('/api/dataset')))", timeout=15000)
                # the stored copy is encrypted (key pair of the device, the private key only with the password): no plain text in it
                raw = pg.evaluate("caches.open('kontor-data-enc').then(c => c.match(location.origin + '/api/dataset')).then(r => r.arrayBuffer()).then(b => new TextDecoder('latin1').decode(b))")
                self.assertNotIn("Hausbank", raw); self.assertNotIn("nettovermoegen", raw); self.assertGreater(len(raw), 1000)
                self.assertFalse(pg.evaluate("caches.has('kontor-data')"))                        # never a plain copy
                pg.goto("http://127.0.0.1:%d/#settings/access" % port); pg.wait_for_selector("#sw-state")
                self.assertIn("aktiv", pg.query_selector("#sw-state").inner_text())
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".cards")
                srv.shutdown(); srv.server_close(); stopped = True
                pg.reload(); pg.wait_for_selector("#login:not(.hidden)")
                self.assertIn("nicht erreichbar", pg.query_selector("#login-text").inner_text())
                pg.fill("#login-pw", "falsches-passwort"); pg.click("#login-btn"); pg.wait_for_timeout(1500)
                self.assertIn("falsch", pg.query_selector("#login-err").inner_text())
                pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.click("#login-btn"); pg.wait_for_selector("#shell:not(.hidden)", timeout=20000)
                pg.wait_for_selector(".cards")
                self.assertIn("Offline-Ansicht", pg.query_selector("#banner").inner_text())
                self.assertIn("nettovermögen", pg.query_selector("#main").inner_text().lower())
                msg = pg.evaluate("api('/api/plan', {bereich: 'x'}).then(() => 'ok').catch(e => e.message)")
                self.assertIn("Offline", msg)
                pg.click("#nav a[href='#balance']"); pg.wait_for_selector("tr.pos")
                self.assertIn("Bankguthaben", pg.query_selector("#main").inner_text())
                # eine Tabelle: Positionen zugeklappt, aufklappbar; Plan-Spalten rechts in derselben Tabelle
                self.assertEqual(len(pg.query_selector_all("#main table")), 1); self.assertIsNone(pg.query_selector("tr.acct"))
                self.assertTrue(pg.query_selector("#main thead th.plan")); self.assertNotIn("Fortschreibung", pg.query_selector("#main").inner_text())
                pg.click("tr.pos[data-pos='liquiditaet'] td:first-child"); pg.wait_for_selector("tr.acct")
                pg.click("#pos-all"); pg.wait_for_timeout(300)
                # waagerecht zur aktuellen Spalte gescrollt (auch in der Jahresansicht)
                self.assertGreater(pg.evaluate("document.querySelector('#main .wrap').scrollLeft"), 0)
                pg.click("#modus-seg button[data-m='jahre']"); pg.wait_for_timeout(300)
                self.assertIsNotNone(pg.query_selector("#main thead th[data-cur]"))
                pg.click("#modus-seg button[data-m='monate']"); pg.wait_for_timeout(300)
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
                self.assertEqual(store.load("config.json")["oberflaeche"]["sprache"], "en")
                pg.goto("http://127.0.0.1:%d/#setup" % port); pg.wait_for_selector(".setup-list")
                self.assertIn("Historical balances", pg.inner_text(".setup-list"))
                with pg.expect_navigation(): pg.select_option("#w-lang", "de")
                wait_shell(pg); pg.wait_for_timeout(500)
                self.assertIn("Übersicht", pg.inner_text("#nav")); self.assertEqual(store.load("config.json")["oberflaeche"]["sprache"], "de")
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
        store.save("config.json", {"updates": {"pruefen": "aus"}, "zeitplan": {"automatisch": False}, "belege": {"ordner": os.path.join(d, "Belege")}})
        reset_mock(); patch_today()
        app = App(store, d, bridge_factory=MockBridge)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        pkg_path = os.path.join(d, "test.kontor.json")
        led = Ledger(accounts_from_export(MockBridge.state["accounts"]), tx_from_export(MockBridge.state["txs"]))
        pkg = core.export_package(core.merged_config(config_for_test()), "Testpaket", strip_uuids=True, ledger=led)
        pkg["config"]["darlehen"][0]["darlehenskonto"] = "Darlehen Fremd"       # muss zugeordnet werden
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
                pg.click(".srow a[href='#setup/connect'] button"); pg.wait_for_selector(".steps")
                self.assertIn("Wofür", pg.evaluate("document.querySelector('.steps .hq').dataset.tip"))      # Erklaerung im Hilfe-Symbol
                self.assertNotIn("Wofür", pg.query_selector("#main").inner_text())                            # nicht doppelt im Text
                pg.click("#w-check")
                self.assertTrue(pg.evaluate("document.querySelector('#w-check').disabled || document.querySelector('#w-check').classList.contains('busy') || !!document.querySelector('#w-findings .ok')"))
                pg.wait_for_selector("#w-findings .ok")
                self.assertIn("Konten gelesen", pg.query_selector("#w-findings").inner_text())
                self.assertNotIn("Belegordner", pg.query_selector("#w-findings").inner_text())
                self.assertNotIn("Keine Bereiche", pg.query_selector("#w-findings").inner_text())
                self.assertTrue(pg.query_selector(".steps button[data-next='#setup/areas']"))           # Knopf statt Link
                # Schritt 1 wird auf dieser Seite alle paar Sekunden neu geprueft
                n0 = len([r for r in reqs if "/api/status?fresh=1" in r]); pg.wait_for_timeout(3500)
                self.assertGreater(len([r for r in reqs if "/api/status?fresh=1" in r]), n0)
                if shots: pg.screenshot(path=os.path.join(shots, "ui_einrichtung_verbindung.png"), full_page=True)
                # Tooltip bleibt im Fenster (auch ganz oben)
                pg.hover(".steps .hq"); pg.wait_for_selector(".tip")
                box = pg.evaluate("(() => { const r = document.querySelector('.tip').getBoundingClientRect(); return [r.top, r.left, r.right, window.innerWidth]; })()")
                self.assertGreaterEqual(box[0], 0); self.assertGreaterEqual(box[1], 0); self.assertLessEqual(box[2], box[3])
                pg.click(".steps button[data-next='#setup/areas']"); pg.wait_for_selector("#save-bereiche")
                self.assertEqual(len(pg.query_selector_all("#bereiche .item")), 3)          # Vorschlag: jede Gruppe der obersten Ebene
                names = lambda: pg.evaluate("[...document.querySelectorAll('#bereiche .item .b-name')].map(i => i.value)")
                self.assertEqual(names()[0], "Privat")                                       # Hauptbereich zuerst
                self.assertTrue(pg.is_disabled("#bereiche .item:first-child .b-mv[data-d='-1']")); self.assertTrue(pg.is_disabled("#bereiche .item:last-child .b-mv[data-d='1']"))
                pg.click("#bereiche .item:nth-child(2) .b-mv[data-d='-1']"); self.assertEqual(names()[:2], ["Alpha GbR", "Privat"])
                self.assertTrue(pg.is_disabled("#bereiche .item:first-child .b-mv[data-d='-1']"))
                pg.click("#bereiche .item:first-child .b-mv[data-d='1']"); self.assertEqual(names()[:2], ["Privat", "Alpha GbR"])
                # Vorbelegung: Privat = Hauptbereich und privat, GbRs = Gesellschaft; Konten unter gewaehlter Gruppe sind enthalten
                items = {pg.evaluate("i => i.querySelector('.b-name').value", it): it for it in pg.query_selector_all("#bereiche .item")}
                self.assertTrue(items["Privat"].query_selector(".b-haupt").is_checked()); self.assertEqual(items["Privat"].query_selector(".b-art").input_value(), "privat")
                self.assertEqual(items["Alpha GbR"].query_selector(".b-art").input_value(), "gesellschaft"); self.assertFalse(items["Alpha GbR"].query_selector(".b-haupt").is_checked())
                alpha = items["Alpha GbR"]
                self.assertTrue(alpha.query_selector(".b-k[value^='%s']" % F.uid("pb.kk")).is_disabled())     # unter der Gruppe: enthalten, gesperrt
                alpha.query_selector(".b-anteil").fill("49")
                beta = items["Beta GbR"]
                beta.query_selector(".b-k[value^='%s']" % F.uid("shs")).click(); pg.wait_for_timeout(100)      # Gruppe abwaehlen -> Konten frei
                self.assertFalse(beta.query_selector(".b-k[value^='%s']" % F.uid("shs.kk")).is_disabled()); self.assertFalse(beta.query_selector(".b-k[value^='%s']" % F.uid("shs.kk")).is_checked())
                beta.query_selector(".b-k[value^='%s']" % F.uid("shs")).click(); pg.wait_for_timeout(100)      # wieder anhaken -> alle darunter
                self.assertTrue(beta.query_selector(".b-k[value^='%s']" % F.uid("shs.kk")).is_checked())
                pg.evaluate("[...document.querySelectorAll('#bereiche .item')].find(i => i.querySelector('.b-name').value === 'Beta GbR').querySelector('.del').click()")   # Beta GbR nicht als Bereich
                pg.wait_for_timeout(100)
                self.assertNotIn("Kennung", pg.query_selector("#bereiche").inner_text())
                if shots: pg.screenshot(path=os.path.join(shots, "ui_einrichtung_bereiche.png"), full_page=True)
                # Privat: kein Anteil; Gesellschaft: Anteil sichtbar
                self.assertTrue(pg.evaluate("[...document.querySelectorAll('#bereiche .item')].find(i => i.querySelector('.b-name').value === 'Privat').querySelector('.b-anteil-row').classList.contains('hidden')"))
                self.assertFalse(pg.evaluate("[...document.querySelectorAll('#bereiche .item')].find(i => i.querySelector('.b-name').value === 'Alpha GbR').querySelector('.b-anteil-row').classList.contains('hidden')"))
                # "Speichern und weiter": speichert, wartet mit Ladeanzeige auf die Auswertung, dann erst Positionen & Verlauf
                pg.click("button[data-savenext='#setup/accounts']")
                pg.wait_for_selector(".busy-ov", timeout=5000)
                pg.wait_for_selector("#save-konten", timeout=30000)
                self.assertIsNone(pg.query_selector(".busy-ov"))
                self.assertFalse(self.__class__ is None or app.bericht_status()["laeuft"])
                self.assertTrue(pg.query_selector("button[data-savenext='#setup/history']")); self.assertTrue(pg.query_selector("button[data-next='#setup']"))
                # Schritt 4: Kontostaende aus MoneyMoney (Finder zeigen, Datei ziehen) -- MoneyMoney laeuft im Test
                pg.goto("http://127.0.0.1:%d/#setup/history" % port); pg.wait_for_selector("#mmh-drop")
                self.assertEqual(pg.query_selector("h2.sub-h").inner_text(), "Historische Kontostände")
                self.assertIn("⌘Q", pg.query_selector("#mmh-s1").inner_text()); self.assertTrue(pg.query_selector("#mmh-zeigen"))
                if shots: pg.screenshot(path=os.path.join(shots, "ui_einrichtung_historie.png"), full_page=True)
                # names of the securities: all listed (MoneyMoney's name first), changeable by hand; nothing is sent without a click
                store.update("state.json", lambda cur: cur.__setitem__("wp_suche", {"zeit": "2026-11-01 10:00", "namen": {"IE00B4L5Y983": "ISHARES CORE MSCI WORLD", "DE0007164600": "SAP"}, "ohne": []}), {})
                pg.reload(); pg.wait_for_selector("#mmh-names:not(.hidden) summary")
                self.assertIsNone(pg.query_selector("#wp-look")); self.assertIn("2 gefunden, 0 ohne Treffer", pg.inner_text("#mmh-names"))
                pg.click("#mmh-names summary"); self.assertEqual(pg.input_value(".wp-edit input[data-isin='DE0007164600']"), "SAP")
                pg.fill(".wp-edit input[data-isin='DE0007164600']", "Mein Fonds")
                pg.click("#wp-names-save"); pg.wait_for_selector("#wp-look-res .ok", timeout=30000)
                self.assertEqual(store.load("state.json")["wp_suche"]["eigene"], {"DE0007164600": "Mein Fonds"})
                store.update("state.json", lambda cur: cur.pop("wp_suche", None), {})
                pg.goto("http://127.0.0.1:%d/#setup/accounts" % port); pg.wait_for_selector("#save-konten")
                cfg0 = store.load("config.json")
                self.assertEqual([b["name"] for b in cfg0["bereiche"]], ["Privat", "Alpha GbR"]); self.assertEqual(sum(1 for b in cfg0["bereiche"] if b["haupt"]), 1)
                self.assertTrue(all(b["id"] for b in cfg0["bereiche"]))
                pg.goto("http://127.0.0.1:%d/#setup/areas" % port); pg.wait_for_selector("#save-bereiche")
                self.assertEqual([b for b in cfg0["bereiche"] if b["name"] == "Alpha GbR"][0]["anteil"], 0.49)       # Prozent -> Anteil
                self.assertEqual([b for b in cfg0["bereiche"] if b["name"] == "Privat"][0]["art"], "privat")
                # Paket laden mit Zuordnung
                pg.click("#nav a[href='#settings']"); pg.wait_for_selector("#e-autobook")
                pg.click("#main .tabs button[data-next='#settings/backup']"); pg.wait_for_selector("#pk-pick")
                with pg.expect_file_chooser() as fc:
                    pg.click("#pk-pick")
                fc.value.set_files(pkg_path); pg.wait_for_selector("#pk-import")
                pg.click("#pk-import"); pg.wait_for_selector(".pk-map")
                pg.select_option(".pk-map", F.uid("pb.vd") + " | Verkäuferdarlehen")
                if shots: pg.screenshot(path=os.path.join(shots, "ui_pakete_zuordnung.png"), full_page=True)
                pg.click("#pk-import2"); pg.wait_for_timeout(800)
                self.assertIn("Übernommen", pg.query_selector("#pk-report").inner_text())
                cfg = store.load("config.json")
                self.assertEqual(cfg["darlehen"][0]["darlehenskonto"].split(" | ")[0], F.uid("pb.vd"))
                self.assertEqual(len(cfg["gesellschaften"]), 2)
                # Bericht erstellen -> Uebersicht mit Kennzahlen
                pg.click("#nav a[href='#setup']"); pg.wait_for_selector(".setup-list")
                self.assertIsNone(pg.query_selector("#w-report"))      # Auswertung existiert schon ("Speichern und weiter" hat auf sie gewartet)
                self.assertIn("eingerichtet", pg.query_selector(".setup-list").inner_text())
                if shots: pg.screenshot(path=os.path.join(shots, "ui_einrichtung.png"), full_page=True)
                pg.click("#nav a[href='#overview']"); pg.wait_for_selector(".cards .spark", timeout=20000)
                self.assertIn("Jahresvergleich", pg.query_selector("#main").inner_text())
                self.assertEqual(len(pg.query_selector_all("#bereich-seg button")), 2)      # Paket ohne Bereiche laesst die eigenen Bereiche unveraendert
                self.assertEqual(errors, [])
                b.close()
        finally:
            srv.shutdown(); srv.server_close(); shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
