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

import json                   # noqa: E402
import test_e2e as T          # noqa: E402
import test_assistant as TA   # noqa: E402
import llm_local              # noqa: E402
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


def assistant(app):
    """The assistant for the images: llama.cpp is the tests' stand-in (no model, nothing downloaded), with prepared answers --
    their figures read from the made-up data through the assistant's own tools. Sizes as on a Mac with a real model."""
    de = LANG == "de"
    opened = llm_local._open
    TA.install(app, rights={"enter_values": True})
    llm_local._open = opened
    a = app.assistant
    a.set({"sandbox": "strict"})
    llm_local.physical_ram = lambda: 64 * 2 ** 30
    models = a.ai._load("models.json")
    models["models"]["qwen3.6-35b-a3b"]["size"] = 22100000000
    a.ai._save("models.json", models)
    real = a.ai.status

    def status():
        st = real()
        st["platform"].update(can_seal=True)
        st["disk_free"] = 412e9
        if st["server"]["state"] == "ready":
            st["server"].update(sealed="strict", rss=23.4e9, cpu=2.0, tps=41.0)
        return st
    a.ai.status = status
    cf = a.t_get_cashflow({"detail": "rows"}, {"area": ""})
    exp = next(s for s in cf["sections"] if s["section"] == ("Ausgaben" if de else "Expenses"))
    rows = sorted(exp["rows"], key=lambda r: r["values"][0])[:4]
    eur = lambda v: ("{:,.2f}".format(abs(v)).replace(",", "X").replace(".", ",").replace("X", ".") + " €") if de else "€" + "{:,.2f}".format(abs(v))
    surplus = next(iter(cf["sums"].values()))[0]
    table = "\n".join("| %s | %s |" % (r["row"], eur(r["values"][0])) for r in rows)
    q1, q2 = (("Wofür habe ich in den letzten zwölf Monaten am meisten ausgegeben?", "Trag für das Depot Ende März 2025 einen Stand von 70.000 € ein.") if de else
              ("What did I spend most on in the last twelve months?", "Enter a balance of €70,000 for the portfolio at the end of March 2025."))
    say = ("In den letzten zwölf abgeschlossenen Monaten hast du **%s** ausgegeben, am meisten für **%s**:\n\n| Position | Betrag |\n|---|---|\n%s\n\nÜbrig blieb ein Überschuss von %s."
           if de else "In the last twelve closed months you spent **%s**, most of it on **%s**:\n\n| Position | Amount |\n|---|---|\n%s\n\nThat left a surplus of %s.") % (
               eur(exp["total"][0]), rows[0]["row"], table, eur(surplus))
    depot = next(k["name"] for k in app.dataset()["accounts"] if k.get("depot"))
    with open(os.path.join(os.path.dirname(a.ai.runtime()["path"]), "script.json"), "w", encoding="utf-8") as f:
        json.dump([{"q": q1, "steps": [{"call": "get_cashflow", "args": {"detail": "rows"}}, {"say": say}]},
                   {"q": q2, "steps": [{"call": "enter_balances", "args": {"account": depot, "values": [{"month": "2025-03", "amount": 70000}]}}, {"say": "OK."}]}], f)
    return q1, q2


def main():
    d = tempfile.mkdtemp(prefix="kontor-shots-")
    store = Store(d, *load_or_create_master_key(d))
    cfg = T.config_for_test(os.path.join(d, "Belege")); cfg.setdefault("ui", {})["language"] = LANG
    store.save("config.json", cfg)
    store.save("state.json", dict(T.ALL_NEW))          # everything booked on the first sync (nothing older waits)
    T.reset_mock(); T.patch_today()
    T.MockBridge.extra_cats = [("Haushalt", 0, True, {}), ("Lebensmittel", 1, False, {})]
    T.MockBridge.state["txs"] += [F.tx("priv.giro", date(2026, 8, 31), -2500.0, "Broker", "Übertrag", "Umbuchung", "DE02100500000054540402"),
                                  F.tx("priv.tr", date(2026, 9, 1), 2500.0, "Hausbank", "Übertrag", "Umbuchung", "DE02120300000000202051")]
    app = App(store, d, bridge_factory=T.MockBridge); app.do_run(False, True)
    import service as MA
    MA.App.tailscale = lambda a, fresh=False: {"found": True, "connected": True, "ip": "100.101.102.103", "name": "macbook.tail1234.ts.net",
                                               "https": True, "account": "max@example.com",
                                               "devices": [{"name": "iPhone", "os": "iOS", "online": True}]}
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
            res = pg.evaluate("""async (a) => { try { const r = await api('/api/properties', {action: 'create', name: 'Parkweg', area: a.b, category: 'Vermietung \\\\ Parkweg'});
                await api('/api/properties', {action: 'calc_save', id: r.property.id, calc: {name: 'Basis', inputs: a.e}}); return 'ok'; } catch (e) { return e.message; } }""",
                              {"b": F.uid("ga"), "e": T.GA_EINGABEN})
            print("Immobilie:", res)
            for _ in range(60):                    # wait for the recalculation (otherwise "recalculating" shows in the image)
                pg.wait_for_timeout(500)
                if not pg.evaluate("fetch('/api/status').then(r => r.json()).then(s => !!(s.report || {}).running)"):
                    break
            pg.reload(); pg.wait_for_selector("#shell:not(.hidden)"); pg.wait_for_timeout(1200)
            pg.evaluate("document.querySelectorAll('.banner').forEach(b => b.remove())")
            shots = [("overview", "#overview", None), ("balance_sheet", "#balance", "balance"), ("cash_flow", "#cashflow", None), ("cash_flow_charts", "#cashflow", "cfcharts"),
                     ("planning", "#planning", None), ("setup", "#setup", None), ("accounts", "#accounts", None),
                     ("assign_categories", "#categories", None), ("rules", "#accounts/rules", "rules"), ("category_positions", "#accounts/positions", None), ("sync", "#settings/moneymoney", None),
                     ("access", "#settings/access", None), ("backup", "#settings/backup", None), ("property", "#properties", "immo")]
            for name, h, special in shots:
                pg.goto(U + h); pg.wait_for_timeout(1400)
                pg.evaluate("document.querySelectorAll('#banner').forEach(b => { b.className = 'hidden'; b.innerHTML = ''; })")
                if special == "balance" and not pg.query_selector("tr.acct"):
                    pg.click("tr.pos[data-pos='cash'] td:first-child"); pg.wait_for_timeout(500)
                if special == "rules":                 # numbers loaded
                    pg.wait_for_timeout(1200)
                if special == "cfcharts":              # the charts below the table
                    pg.mouse.move(4, 4)                # no mark hovered
                    pg.evaluate("window.scrollTo(0, document.querySelector('.cf-charts').getBoundingClientRect().top + window.scrollY - 70)"); pg.wait_for_timeout(400)
                if special == "immo":
                    pg.click(".card[data-im]"); pg.wait_for_timeout(1500)
                if name == "backup":                   # the folders as on a Mac (not the test machine's paths), the key in the keychain
                    pg.evaluate("""Object.assign(S.STATUS.storage, {folder: '~/Library/Application Support/Kontor', program_folder: '~/Applications/Kontor', key_source: 'keychain'});
                      S.STATUS.receipts.folder = '~/Documents/Kontor-Belege'; S.CFG.receipts.folder = '~/Documents/Kontor-Belege'; route()""")
                    pg.wait_for_timeout(800)
                save(pg, name)
            # the assistant: its settings, then a conversation beside the cash flow (an answer, an entry waiting for the click)
            app.rebuild_report(wait=True)
            q1, q2 = assistant(app)
            pg.reload(); pg.wait_for_selector("#shell:not(.hidden)"); pg.wait_for_timeout(1200)
            pg.goto(U + "#cashflow"); pg.wait_for_timeout(1400)
            pg.evaluate("document.querySelectorAll('#banner').forEach(b => { b.className = 'hidden'; b.innerHTML = ''; })")
            pg.click("#assist-btn"); pg.wait_for_selector("#assist.open #as-in"); pg.wait_for_timeout(600)
            for q, sel in ((q1, ".as-meta"), (q2, ".as-entry.ask")):
                pg.fill("#as-in", q); pg.keyboard.press("Enter")
                pg.wait_for_selector("#as-body .as-msg:last-child " + sel, timeout=60000); pg.wait_for_timeout(500)
            pg.evaluate("AS.msgs.forEach(m => { if (m.meta) m.meta.seconds = 7; }); asMsgs(); asLoad().then(asHead)"); pg.wait_for_timeout(600)
            pg.mouse.move(700, 4)
            save(pg, "assistant")
            pg.click(".as-no"); pg.wait_for_timeout(500); pg.click(".as-close"); pg.wait_for_timeout(500)
            pg.goto(U + "#settings/assistant"); pg.wait_for_selector("#as-enabled", state="attached"); pg.wait_for_timeout(900)
            pg.evaluate("document.querySelectorAll('#banner').forEach(b => { b.className = 'hidden'; b.innerHTML = ''; })")
            save(pg, "assistant_settings")
            # history panel of an account
            pg.goto(U + "#balance"); pg.wait_for_timeout(1200)
            if not pg.query_selector("tr.acct"):
                pg.click("tr.pos[data-pos='cash'] td:first-child"); pg.wait_for_timeout(400)
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
        app.assistant_stop()
        srv.shutdown()


if __name__ == "__main__":
    main()
