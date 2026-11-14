"""Look at Kontor's interface with the made-up test data: pages as images, light and dark, MacBook and iPhone.

Usage: python3 tests/preview.py OUT_DIR ['#route' ...] [--lang de|en] [--nur hell|dunkel] [--nur mac|iphone] [--js CODE]
--js: JavaScript run on each page before the picture (e.g. whole tables: "document.querySelectorAll('.wrap').forEach(w => w.style.maxHeight = 'none')").
Without routes: all main pages. Booked as on a first sync with everything new (nothing older waits).
All names, accounts and amounts come from tests/fixtures.py and are made up."""
import argparse
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)

import test_e2e as T          # noqa: E402
from storage import Store, load_or_create_master_key   # noqa: E402
from service import App, make_handler                  # noqa: E402
from http.server import ThreadingHTTPServer            # noqa: E402
from playwright.sync_api import sync_playwright        # noqa: E402

PAGES = ["#overview", "#balance", "#cashflow", "#planning", "#properties", "#tax", "#transactions", "#bookings", "#sync",
         "#setup", "#rules", "#categories", "#settings", "#updates", "#log", "#help"]
SIZES = {"mac": dict(viewport={"width": 1360, "height": 820}), "iphone": dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("routes", nargs="*")
    ap.add_argument("--lang", default="de")
    ap.add_argument("--nur", action="append", default=[])
    ap.add_argument("--js", default="")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    themes = [t for t in ("dunkel", "hell") if not set(a.nur) & {"dunkel", "hell"} or t in a.nur]
    sizes = [s for s in SIZES if not set(a.nur) & set(SIZES) or s in a.nur]
    d = tempfile.mkdtemp(prefix="kontor-preview-")
    store = Store(d, *load_or_create_master_key(d))
    cfg = T.config_for_test(os.path.join(d, "Belege")); cfg.setdefault("oberflaeche", {})["sprache"] = a.lang
    store.save("config.json", cfg); store.save("state.json", dict(T.ALL_NEW))
    T.reset_mock(); T.patch_today()
    app = App(store, d, bridge_factory=T.MockBridge); app.do_run(False, True)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            first = b.new_page(**SIZES["mac"])
            first.goto(url); first.evaluate("l => localStorage.setItem('kontor.lang', l)", a.lang); first.reload()
            first.wait_for_selector("#login-pw")
            first.fill("#login-pw", "sehr-geheimes-passwort"); first.fill("#login-pw2", "sehr-geheimes-passwort"); first.click("#login-btn")
            first.wait_for_selector("#shell:not(.hidden)")
            cookies = first.context.cookies()
            for size in sizes:
                for theme in themes:
                    ctx = b.new_context(color_scheme="dark" if theme == "dunkel" else "light", **SIZES[size])
                    ctx.add_cookies(cookies)
                    pg = ctx.new_page()
                    pg.goto(url); pg.evaluate("l => localStorage.setItem('kontor.lang', l)", a.lang)
                    pg.evaluate("t => localStorage.setItem('kontor.theme', t)", "light" if theme == "hell" else "dark")   # dark is the default
                    pg.reload()
                    for route in a.routes or PAGES:
                        pg.goto(url + route); pg.wait_for_timeout(1500)
                        if a.js:
                            pg.evaluate("() => { %s }" % a.js); pg.wait_for_timeout(300)
                        name = "%s_%s_%s.png" % (route.strip("#").replace("/", "-") or "start", size, theme)
                        pg.screenshot(path=os.path.join(a.out, name), full_page=True)
                        print(os.path.join(a.out, name))
                    ctx.close()
            b.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
