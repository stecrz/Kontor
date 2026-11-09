"""Create the images for README and help (docs/img/<lang>) from the made-up test data.

Usage: python3 tests/screenshots.py [folder|-] [de|en]   (default: docs/img/de). Needs Playwright and Pillow.
All names, accounts and amounts come from tests/fixtures.py and are made up.
"""
import os
import sys
import tempfile
import threading
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)

import test_e2e as T          # noqa: E402
import fixtures as F          # noqa: E402
from storage import Store, load_or_create_master_key   # noqa: E402
from service import App, make_handler                  # noqa: E402
from http.server import ThreadingHTTPServer            # noqa: E402
from playwright.sync_api import sync_playwright        # noqa: E402
from PIL import Image                                  # noqa: E402

LANG = sys.argv[2] if len(sys.argv) > 2 else "de"
OUT = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "-" else os.path.join(HERE, "..", "docs", "img", LANG)
os.makedirs(OUT, exist_ok=True)


def save(pg, name, clip=None, full=False):
    path = os.path.join(OUT, name + ".png")
    pg.screenshot(path=path, clip=clip, full_page=full)
    im = Image.open(path).convert("RGB")
    im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    print(name, os.path.getsize(path) // 1024, "KB")


def main():
    d = tempfile.mkdtemp(prefix="kontor-shots-")
    store = Store(d, *load_or_create_master_key(d))
    cfg = T.config_for_test(os.path.join(d, "Belege")); cfg.setdefault("oberflaeche", {})["sprache"] = LANG
    store.save("config.json", cfg)
    T.reset_mock(); T.patch_today()
    T.MockBridge.extra_cats = [("Haushalt", 0, True, {}), ("Lebensmittel", 1, False, {})]
    T.MockBridge.state["txs"] += [F.tx("priv.giro", date(2026, 8, 31), -2500.0, "Broker", "Übertrag", "Umbuchung", "DE02100500000054540402"),
                                  F.tx("priv.tr", date(2026, 9, 1), 2500.0, "Hausbank", "Übertrag", "Umbuchung", "DE02120300000000202051")]
    app = App(store, d, bridge_factory=T.MockBridge); app.do_run(False, True)
    import service as MA
    MA.App.tailscale = lambda a, fresh=False: {"gefunden": True, "verbunden": True, "ip": "100.101.102.103", "name": "macbook.tail1234.ts.net",
                                               "https": True, "konto": "max@example.com",
                                               "geraete": [{"name": "iPhone", "os": "iOS", "online": True}]}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    U = "http://127.0.0.1:%d/" % port
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1360, "height": 820}, device_scale_factor=2)
            pg.goto(U); pg.evaluate("l => localStorage.setItem('kontor.lang', l)", LANG); pg.reload(); pg.wait_for_selector("#login-pw")
            pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.fill("#login-pw2", "sehr-geheimes-passwort"); pg.click("#login-btn")
            pg.wait_for_selector("#shell:not(.hidden)"); pg.wait_for_timeout(800)
            # property with a calculation (for the image and the plan)
            res = pg.evaluate("""async (a) => { try { const r = await api('/api/properties', {aktion: 'anlegen', name: 'Parkweg', bereich: a.b, kategorie: 'Vermietung \\\\ Parkweg'});
                await api('/api/properties', {aktion: 'kalkulation_speichern', id: r.immobilie.id, kalkulation: {name: 'Basis', eingaben: a.e}}); return 'ok'; } catch (e) { return e.message; } }""",
                              {"b": F.uid("pb"), "e": T.PB_EINGABEN})
            print("Immobilie:", res)
            for _ in range(60):                    # wait for the recalculation (otherwise "recalculating" shows in the image)
                pg.wait_for_timeout(500)
                if not pg.evaluate("fetch('/api/status').then(r => r.json()).then(s => !!(s.bericht || {}).laeuft)"):
                    break
            pg.reload(); pg.wait_for_selector("#shell:not(.hidden)"); pg.wait_for_timeout(1200)
            pg.evaluate("document.querySelectorAll('.banner').forEach(b => b.remove())")
            shots = [("overview", "#overview", None), ("balance_sheet", "#balance", "bilanz"), ("cash_flow", "#cashflow", None),
                     ("planning", "#planning", None), ("setup", "#setup", None), ("accounts", "#setup/accounts", None),
                     ("assign_categories", "#categories", None), ("rules", "#rules", "rules"), ("category_selection", "#categories/selection", None), ("sync", "#sync", None),
                     ("access", "#settings/access", None), ("backup", "#settings/backup", None), ("property", "#properties", "immo")]
            for name, h, special in shots:
                pg.goto(U + h); pg.wait_for_timeout(1400)
                pg.evaluate("document.querySelectorAll('#banner').forEach(b => { b.className = 'hidden'; b.innerHTML = ''; })")
                if special == "bilanz" and not pg.query_selector("tr.acct"):
                    pg.click("tr.pos[data-pos='liquiditaet'] td:first-child"); pg.wait_for_timeout(500)
                if special == "rules":                 # the settings of the first company open, numbers loaded
                    pg.click(".co-card .co-more summary"); pg.wait_for_timeout(1200)
                if special == "immo":
                    pg.click(".card[data-im]"); pg.wait_for_timeout(1500)
                save(pg, name)
            # history panel of an account
            pg.goto(U + "#balance"); pg.wait_for_timeout(1200)
            if not pg.query_selector("tr.acct"):
                pg.click("tr.pos[data-pos='liquiditaet'] td:first-child"); pg.wait_for_timeout(400)
            pg.click("tr.acct td"); pg.wait_for_selector("#drawer.open"); pg.wait_for_timeout(800)
            save(pg, "account_history", clip={"x": 860, "y": 0, "width": 500, "height": 820})
            # iPhone
            m = b.new_page(viewport={"width": 390, "height": 760}, device_scale_factor=3, is_mobile=True, has_touch=True)
            m.context.add_cookies(pg.context.cookies())
            m.goto(U + "#overview"); m.wait_for_timeout(1500)
            m.evaluate("document.querySelectorAll('#banner').forEach(b => { b.className = 'hidden'; b.innerHTML = ''; })")
            save(m, "iphone")
            b.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
