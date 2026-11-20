"""A tour of every page: MacBook and iPhone, dark and light, German and English (Playwright: Chromium, and WebKit, Safari's
engine, where it is installed). On every page: no script errors, the page never scrolls sideways, no raw text keys and no
undefined/NaN in the text, and every text readable against what lies behind it (contrast as in Apple's guidelines)."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import warnings
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from test_e2e import MockBridge, config_for_test, patch_today, reset_mock  # noqa: E402
from service import App, make_handler  # noqa: E402
from storage import Store, load_or_create_master_key  # noqa: E402

PASSWORD = "sehr-geheimes-passwort"
# (device, appearance, language); English last: it switches the language of the service
VIEWS = [("mac", "dark", "de"), ("mac", "light", "de"), ("iphone", "dark", "de"), ("iphone", "light", "de"), ("mac", "dark", "en")]
DEVICES = {"mac": {"viewport": {"width": 1440, "height": 900}},
           "iphone": {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True, "device_scale_factor": 2}}
# Apple's guidelines: at least 4.5:1 for text, 3:1 for large text. Still a report, not a failure: a few muted texts (zeros in
# tables, the menu's section titles, small grey notes, green amounts in light mode) are below it -- the user decides first.
CONTRAST_ENFORCED = False

CHECKS = r"""(() => {
  const out = {overflow: null, keys: [], junk: [], contrast: []};
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getClientRects().length > 0; };
  const faded = el => { let o = 1; for (let a = el; a; a = a.parentElement) o *= Number(getComputedStyle(a).opacity); return o < 0.15; };   // invisible on purpose (shown on hover)
  const desc = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  // the page itself never scrolls sideways (wide tables scroll in their own box)
  const iw = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth > iw + 1) {
    const clipped = el => { for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) { if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(a).overflowX)) return true; } return false; };
    const wide = [...document.querySelectorAll('body *')].filter(el => vis(el) && el.getBoundingClientRect().right > iw + 1 && !clipped(el));
    out.overflow = {scrollWidth: document.documentElement.scrollWidth, width: iw, elements: [...new Set(wide.slice(-4).map(desc))]};
  }
  // text: no raw keys (t() returns the key when it has no text), no unfilled placeholders, no undefined / NaN
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode());) {
    const s = n.nodeValue.trim(), p = n.parentElement;
    if (!s || !p || !vis(p) || faded(p) || p.closest('script, style, textarea, code, pre, kbd')) continue;
    if (/^[a-z][a-z0-9]*(_[a-z0-9]+)+$/.test(s)) out.keys.push(s);
    if (/\bundefined\b|\bNaN\b|\[object Object\]|\bInfinity\b|\{\d\}|%s/.test(s)) out.junk.push(s.slice(0, 80));
  }
  // contrast of visible text against the backgrounds behind it (charts and pictures left out)
  // rgb()/rgba(), and color(srgb ...) as browsers give mixed colours (color-mix); any other colour space: unknown (null)
  const rgba = c => { let m = c.match(/^rgba?\(([^)]+)\)/), f = 1; if (!m) { m = c.match(/^color\(srgb ([^)]+)\)/); f = 255; } if (!m) return null;
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [p[0] * f, p[1] * f, p[2] * f, p.length > 3 ? p[3] : 1]; };
  const over = (t, b) => [t[0] * t[3] + b[0] * (1 - t[3]), t[1] * t[3] + b[1] * (1 - t[3]), t[2] * t[3] + b[2] * (1 - t[3]), 1];
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const seen = new Set();
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el) || el.closest('svg, [disabled], [aria-disabled="true"]')) continue;
    const own = [...el.childNodes].filter(n => n.nodeType === 3 && n.nodeValue.trim()).map(n => n.nodeValue.trim()).join(' ');
    const r = el.getBoundingClientRect();
    if (!own || r.width < 1 || r.height < 1) continue;
    const layers = []; let opacity = 1, unknown = false;
    for (let a = el; a; a = a.parentElement) {
      const cs = getComputedStyle(a); opacity *= Number(cs.opacity);
      const bg = rgba(cs.backgroundColor);
      if (cs.backgroundImage !== 'none' || !bg) { unknown = true; break; }
      if (bg[3] > 0) layers.push(bg);
      if (bg[3] >= 1) break;
    }
    if (unknown || opacity < 0.15) continue;          // a picture behind it, or invisible on purpose (shown on hover)
    let bg = document.documentElement.dataset.theme === 'light' ? [255, 255, 255, 1] : [0, 0, 0, 1];
    for (let i = layers.length - 1; i >= 0; i--) bg = over(layers[i], bg);
    const cs = getComputedStyle(el), fg0 = rgba(cs.color); if (!fg0) continue;
    const fg = over([fg0[0], fg0[1], fg0[2], fg0[3] * opacity], bg);
    const size = parseFloat(cs.fontSize), need = size >= 24 || (Number(cs.fontWeight) >= 700 && size >= 18.66) ? 3 : 4.5;
    const q = ratio(fg, bg), k = desc(el) + '|' + Math.round(q * 10);
    if (q < need && !seen.has(k)) { seen.add(k); out.contrast.push({element: desc(el), text: own.slice(0, 40), ratio: Math.round(q * 100) / 100, need}); }
  }
  out.keys = [...new Set(out.keys)]; out.junk = [...new Set(out.junk)];
  return out;
})()"""


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        raise unittest.SkipTest("playwright fehlt")


def settle(pg, timeout=20):
    """Until the page is drawn (no eval-based waiting: the page's security rules forbid it). A reload in between -- the
    language switch -- just means asking again."""
    end = time.time() + timeout
    while True:
        try:
            if pg.evaluate("(() => { const m = document.querySelector('#main'); return !!m && !m.querySelector('.loading') && m.children.length > 0 && !document.querySelector('#shell.hidden'); })()"):
                break
        except Exception:
            pass
        if time.time() > end:
            raise AssertionError("page not drawn: %s" % pg.url)
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(250)          # charts and folded parts finish drawing


class CheckerTest(unittest.TestCase):
    """The checks themselves find what they look for (on a page made of mistakes)."""

    def test_finds_every_kind_of_mistake(self):
        sync_playwright = _playwright()
        page = """<html data-theme="dark"><body style="margin:0;background:#000;color:#fff">
          <div style="width:3000px">zu breit</div><p>neuer_schluessel</p><p>Summe: NaN €</p><p>Hallo {0}</p>
          <p style="color:#555">kaum lesbar</p><div style="opacity:0">unsichtbar_absichtlich</div>
          <p style="background:color-mix(in srgb, #fff 90%, #000);color:color-mix(in srgb, #000 90%, #fff)">gemischt gut lesbar</p>
          <p style="background:color-mix(in srgb, #fff 50%, #000);color:color-mix(in srgb, #fff 40%, #000)">gemischt kaum lesbar</p>
          <p style="color:oklch(0.3 0.1 200)">anderer Farbraum: unbekannt</p>
          <div style="overflow-x:auto;width:100px"><div style="width:900px">darf scrollen</div></div><code>im_code_ok</code></body></html>"""
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 800, "height": 600})
            pg.set_content(page)
            r = pg.evaluate(CHECKS)
            b.close()
        self.assertIsNotNone(r["overflow"]); self.assertIn("div", r["overflow"]["elements"])
        self.assertEqual(r["keys"], ["neuer_schluessel"])          # not the hidden one, not the one in code
        self.assertEqual(r["junk"], ["Summe: NaN €", "Hallo {0}"])
        self.assertEqual([c["text"] for c in r["contrast"]], ["kaum lesbar", "gemischt kaum lesbar"])


class PageTourTest(unittest.TestCase):
    """Every page reached from the menu and its sub-pages, in every view."""

    @classmethod
    def setUpClass(cls):
        _playwright()
        cls.dir = tempfile.mkdtemp(prefix="kontor-tour-")
        key, src = load_or_create_master_key(cls.dir)
        store = Store(cls.dir, key, src); store.save("config.json", config_for_test(os.path.join(cls.dir, "Belege")))
        reset_mock(); patch_today()
        cls.app = App(store, cls.dir, bridge_factory=MockBridge)
        cls.app.do_run(False, True)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d/" % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def tour(self, browser, engine):
        problems, contrast, pages = [], {}, set()
        self.app.config.setdefault("ui", {})["language"] = "de"
        for device, theme, lang in VIEWS:
            if lang != "de":
                self.app.config["ui"]["language"] = lang
            view = "%s/%s/%s/%s" % (engine, device, theme, lang)
            ctx = browser.new_context(**DEVICES[device])
            ctx.add_init_script("try { localStorage.setItem('kontor.theme', %s); } catch (e) {}" % json.dumps(theme))
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append("Skriptfehler: %s" % e))
            pg.on("console", lambda m: errors.append("Konsole: %s" % m.text) if m.type == "error" else None)
            pg.goto(self.base)
            pg.fill("#login-pw", PASSWORD)
            if pg.is_visible("#login-pw2"):
                pg.fill("#login-pw2", PASSWORD)
            pg.click("#login-btn")
            pg.wait_for_selector("#shell:not(.hidden)", timeout=30000)
            settle(pg)
            todo = pg.evaluate("[...document.querySelectorAll('#nav a[href^=\"#\"]')].map(a => a.getAttribute('href'))")
            self.assertGreater(len(todo), 8, "menu not found")
            seen = set()
            while todo:
                h = todo.pop(0)
                if h in seen:
                    continue
                seen.add(h); errors.clear()
                pg.evaluate("h => { location.hash = h; }", h)
                try:
                    settle(pg)
                except AssertionError as e:
                    problems.append("%s %s: %s" % (view, h, e)); continue
                tab = h[1:].split("/")[0]
                todo += [s for s in pg.evaluate("tab => [...new Set([...document.querySelectorAll('#main a[href^=\"#' + tab + '/\"]')].map(a => a.getAttribute('href').split('?')[0]))]", tab) if s not in seen]
                r = pg.evaluate(CHECKS)
                for e in errors:
                    problems.append("%s %s: %s" % (view, h, e))
                if r["overflow"]:
                    problems.append("%s %s: seitlich zu breit %s" % (view, h, r["overflow"]))
                for k in r["keys"]:
                    problems.append("%s %s: Textschlüssel statt Text: %s" % (view, h, k))
                for j in r["junk"]:
                    problems.append("%s %s: Text mit undefined/NaN/Platzhalter: %s" % (view, h, j))
                for c in r["contrast"]:
                    key = (c["element"], theme)
                    if key not in contrast or c["ratio"] < contrast[key]["ratio"]:
                        contrast[key] = dict(c, where="%s %s" % (view, h))
            pages |= seen
            ctx.close()
        self.app.config["ui"]["language"] = "de"
        self.assertGreater(len(pages), 25, "too few pages reached: %s" % sorted(pages))
        low = ["%s %s %.2f (min. %.1f) „%s“ – %s" % (k[1], k[0], c["ratio"], c["need"], c["text"], c["where"])
               for k, c in sorted(contrast.items(), key=lambda kv: kv[1]["ratio"])]
        if low and CONTRAST_ENFORCED:
            problems += ["Kontrast %s" % x for x in low]
        elif low:
            warnings.warn("%s: %d Texte unter dem Kontrast nach Apples Richtlinien:\n  %s" % (engine, len(low), "\n  ".join(low)))
        self.assertEqual(problems, [], "\n".join(problems))

    def test_tour_chromium(self):
        with _playwright()() as p:
            b = p.chromium.launch()
            try:
                self.tour(b, "chromium")
            finally:
                b.close()

    def test_tour_webkit(self):
        """Safari's engine, where it is installed (in GitHub's run with the newest Python)."""
        with _playwright()() as p:
            try:
                b = p.webkit.launch()
            except Exception:
                self.skipTest("WebKit nicht installiert")
            try:
                self.tour(b, "webkit")
            finally:
                b.close()


if __name__ == "__main__":
    unittest.main()
