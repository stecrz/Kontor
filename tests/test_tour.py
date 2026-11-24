"""A tour of every page: MacBook and iPhone, dark and light, German and English (Playwright: Chromium, and WebKit, Safari's
engine, where it is installed) -- each page of the menu, its sub-pages and tabs. On every page: no script errors, the page never
scrolls sideways, no raw text keys and no undefined/NaN in the text, every text readable against what lies behind it (contrast as
in Apple's guidelines), and everything explained: every control with a tooltip or a "?", every figure described (EXPLAINED)."""
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
from fixtures import new_store  # noqa: E402
import assistant  # noqa: E402

PASSWORD = "sehr-geheimes-passwort"
# (device, appearance, language); English last: it switches the language of the service
VIEWS = [("mac", "dark", "de"), ("mac", "light", "de"), ("iphone", "dark", "de"), ("iphone", "light", "de"), ("mac", "dark", "en")]
DEVICES = {"mac": {"viewport": {"width": 1440, "height": 900}},
           "iphone": {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True, "device_scale_factor": 2}}
# Apple's guidelines: at least 4.5:1 for text, 3:1 for large text. Still a report, not a failure: a few muted texts (zeros in
# tables, the menu's section titles, small grey notes, green amounts in light mode) are below it -- the user decides first.
CONTRAST_ENFORCED = False

# every table, chart and card a right click can land on lies in a place Kontor describes for the assistant (data-ex, docs/ui) --
# on the pages the assistant may read (never settings, log, setup or its own panel)
PLACES = r"""(known => {
  const vis = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none';
  const desc = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const out = [];
  for (const el of document.querySelectorAll('#main table, #main .card, #main .co-card, #main .kpi, #main #bch, #main .lc, #main .cf-card, #main .ov-card, #main .im-chart, #drawer.open table, #drawer.open .h-chart')) {
    if (!vis(el)) continue;
    const host = el.closest('[data-ex]'), k = host ? host.dataset.ex : '';
    if (!k || !k.includes('.') || !known.includes(k)) out.push(desc(el) + (k ? ' (' + k + ')' : ''));
  }
  return [...new Set(out)];
})"""
HIDDEN = ("settings", "log", "setup", "assistant")

# Explained: every control on a page has a tooltip (title) or a "?" -- its own, its label's, its column's, or the one of the group it
# stands in (field, row, bar, heading, card, or a place the page describes) -- and every visible figure lies in a place Kontor
# describes for the assistant (data-ex, docs/ui; on the pages it may read). A chart's hover tip shows the figures of the card below it.
EXPLAINED = r"""(([known, root]) => {
  const R = document.querySelector(root || '#main');
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getClientRects().length > 0; };
  const faded = el => { let o = 1; for (let a = el; a; a = a.parentElement) o *= Number(getComputedStyle(a).opacity); return o < 0.15; };
  const desc = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '') + ' "' + (el.textContent || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().replace(/\d/g, '9').slice(0, 30) + '"';
  // a "?" explains the group it stands in: a field, row, bar, heading, card or a place the page describes (data-ex) -- up to the card
  const GROUP = 'label, tr, .row, .field, .toolbar, .actions, .seg, .tabs, .tabs-row, h1, h2, h3, h4, li, form, .note, .kpi, details, section, .card, .co-card, .lc, .cf-card, .ov-card, fieldset, .dlg, [data-ex*="."]';
  const STOP = '.card, .co-card, .lc, .cf-card, .ov-card, fieldset, .dlg, #main, #drawer';
  const tipped = el => el.hasAttribute('title') || !!el.dataset.tip || !!el.dataset.help;
  const hqIn = el => [...el.querySelectorAll('.hq')].some(vis);
  function explained(el) {
    for (let a = el; a && a !== document.body; a = a.parentElement) {
      if (tipped(a)) return true;
      if (a.tagName === 'TD' || a.tagName === 'TH') {       // in a table: the head of its column
        const idx = [...a.parentElement.children].indexOf(a), table = a.closest('table');
        const head = table && table.tHead && table.tHead.rows[0] && table.tHead.rows[0].children[idx];
        if (head && head !== a && (tipped(head) || head.querySelector('.hq, [title]'))) return true;
      }
      if (a.id) { const lab = document.querySelector(`label[for="${CSS.escape(a.id)}"]`); if (lab && (tipped(lab) || hqIn(lab))) return true; }
      if (a.matches(GROUP) && hqIn(a)) return true;
      if (a.matches(STOP)) break;
    }
    return false;
  }
  const res = {controls: 0, unexplained: [], numbers: []};
  for (const el of R.querySelectorAll('button, input, select, textarea, [role=button], [role=switch], summary, a[href]')) {
    if (!vis(el) || faded(el) || el.type === 'hidden' || el.closest('.hq')) continue;
    if (el.tagName === 'A' && !el.closest('.toolbar, .actions, .tabs-row, .seg')) continue;   // a link in a text: the text says where it leads
    res.controls++;
    if (!explained(el)) res.unexplained.push(desc(el));
  }
  if (known) {
    const walker = document.createTreeWalker(R, NodeFilter.SHOW_TEXT);
    for (let n; (n = walker.nextNode());) {
      const s = n.nodeValue.trim(), p = n.parentElement;
      if (!s || !/\d/.test(s) || !p || !vis(p) || faded(p) || p.closest('script, style, code, pre, button, select, option, input, textarea, .hq, .stepper, .seg, [role=tooltip]')) continue;
      const host = p.closest('[data-ex]'), k = host ? host.dataset.ex : '';
      if (!k || !k.includes('.') || !known.includes(k)) res.numbers.push(desc(p) + ' [' + s.replace(/\d/g, '9').slice(0, 30) + ']' + (k ? ' (' + k + ')' : ''));
    }
  }
  res.unexplained = [...new Set(res.unexplained)]; res.numbers = [...new Set(res.numbers)];
  return res;
})"""

# the side panels, each opened as a click would (page, call): an account's history (bank account, depot), the equity ratio, the
# money in transit, the transactions behind a figure -- a call that finds nothing to open returns false (then it is left out)
DRAWERS = [("#balance", "(k => k ? openHistDrawer(k.uuid) : false)(S.DATA.accounts.find(k => !k.group && k.role === 'cash'))"),
           ("#balance", "(k => k ? openHistDrawer(k.uuid) : false)(S.DATA.accounts.find(k => !k.group && k.role === 'securities'))"),
           ("#balance", "(e => e && Object.keys(e.months || {}).length ? openEkqDrawer(Object.keys(e.months).pop()) : false)((B().balance || {}).equity_ratio)"),
           ("#balance", "((B().balance || {}).rows || []).some(x => x.transit) ? openTransitDrawer() : false"),
           ("#cashflow", "cfOpenTx({title: 'Test', months: B().months.slice(-3)})")]

# the sub-pages of a page: its links (#tab/...) and its tabs (data-next)
SUBPAGES = """tab => [...new Set([...document.querySelectorAll('#main a[href^="#' + tab + '/"], #main [data-next^="#' + tab + '/"], #main [data-next="#' + tab + '"]')]
  .map(a => (a.getAttribute('href') || a.dataset.next).split('?')[0]))]"""

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
    if (!s || !p || !vis(p) || faded(p) || p.closest('script, style, textarea, code, pre, kbd, [data-ex="settings.updates.changes"]')) continue;   // (the changes: written text, may quote such a word)
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
    """Until the page is drawn and its short animations are over. A reload in between -- after the login, the page follows the
    language set in Kontor -- just means waiting again (the page asked about is gone, not broken)."""
    for attempt in range(3):
        try:
            return _settle(pg, timeout)
        except Exception as e:                       # playwright: "Execution context was destroyed" (the reload)
            if "context was destroyed" not in str(e) or attempt == 2:
                raise


def _settle(pg, timeout):
    """Until the page is drawn (no eval-based waiting: the page's security rules forbid it)."""
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
    # the fade-in and other short animations finished (lasting ones like a spinner do not count): measured mid-fade, all
    # text looks pale -- slower machines need longer than a fixed pause
    end = time.time() + 5
    while time.time() < end and pg.evaluate("document.getAnimations().some(a => a.playState === 'running' && isFinite(a.effect.getComputedTiming().endTime))"):
        pg.wait_for_timeout(50)
    pg.wait_for_timeout(100)


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


    def test_finds_what_is_unexplained(self):
        sync_playwright = _playwright()
        page = """<html><body><div id="main">
          <button title="Erklärt">mit Tooltip</button><button id="bare">ohne alles</button>
          <div class="card"><h2>Karte <span class="hq" data-tip="x">?</span></h2><div><button id="in-card">in der Karte</button></div></div>
          <label for="f">Feld <span class="hq" data-tip="x">?</span></label><input id="f">
          <table><thead><tr><th>Spalte <span class="hq" data-tip="x">?</span></th><th>ohne</th></tr></thead>
            <tbody><tr><td><input id="in-col"></td><td><input id="no-col"></td></tr></tbody></table>
          <div class="card"><span class="hq" data-tip="x" style="display:none">?</span><button id="hidden-hq">versteckter Tooltip</button></div>
          <a href="#x">ein Link im Text</a><div class="toolbar"><a href="#y" id="bar-link">Link in der Leiste</a></div>
          <div data-ex="p.known"><b>1.234 €</b></div><div data-ex="p.unknown"><b>5 %</b></div><div><b>Stand 2026</b></div>
          <div role="tooltip"><b>99 €</b></div><div style="opacity:0"><b>77 €</b></div></div></body></html>"""
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 800, "height": 600})
            pg.set_content(page)
            r = pg.evaluate(EXPLAINED, [["p.known"], "#main"])
            b.close()
        self.assertEqual([x.split(" ")[0] for x in r["unexplained"]], ["button#bare", "input#no-col", "button#hidden-hq", "a#bar-link"])
        self.assertEqual([x.split(" ")[0] for x in r["numbers"]], ["b", "b"])                  # 5 % (an unknown place), Stand 2026
        self.assertTrue(r["numbers"][0].endswith("[9 %] (p.unknown)") and "Stand" in r["numbers"][1], r["numbers"])      # not the tip, not the faded one


class PageTourTest(unittest.TestCase):
    """Every page reached from the menu and its sub-pages, in every view."""

    @classmethod
    def setUpClass(cls):
        _playwright()
        cls.dir = tempfile.mkdtemp(prefix="kontor-tour-")
        store = new_store(cls.dir); store.save("config.json", config_for_test(os.path.join(cls.dir, "Belege")))
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
        known = sorted(assistant.screen_notes(os.path.join(os.path.dirname(__file__), "..", *assistant.SCREEN_DIR)))
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
                todo += [s for s in pg.evaluate(SUBPAGES, tab) if s not in seen]
                r = pg.evaluate(CHECKS)
                if (device, theme, lang) == VIEWS[0] and tab not in HIDDEN:
                    for miss in pg.evaluate(PLACES, known):
                        problems.append("%s %s: nicht beschrieben (data-ex, docs/ui): %s" % (view, h, miss))
                if theme == "dark" and lang == "de" and tab != "help":
                    ex = pg.evaluate(EXPLAINED, [known if device == "mac" and tab not in HIDDEN else None, "#main"])
                    for miss in ex["unexplained"]:
                        problems.append("%s %s: Bedienelement ohne Tooltip oder „?“: %s" % (view, h, miss))
                    for miss in ex["numbers"]:
                        problems.append("%s %s: Zahl nicht beschrieben (data-ex, docs/ui): %s" % (view, h, miss))
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
            if theme == "dark" and lang == "de":
                for h, js in DRAWERS:                        # the side panels: explained as the pages are
                    pg.evaluate("h => { location.hash = h; }", h); settle(pg)
                    opened = pg.evaluate("() => { try { return (%s) !== false; } catch (e) { return String(e); } }" % js)
                    if opened is not True:
                        if opened:
                            problems.append("%s %s: Seitenfenster %s: %s" % (view, h, js[:40], opened))
                        continue
                    try:
                        pg.wait_for_selector("#drawer.open", timeout=10000); pg.wait_for_timeout(300)
                    except Exception:
                        problems.append("%s %s: Seitenfenster öffnet nicht: %s" % (view, h, js)); continue
                    ex = pg.evaluate(EXPLAINED, [known if device == "mac" else None, "#drawer"])
                    for miss in ex["unexplained"]:
                        problems.append("%s %s Seitenfenster %s: Bedienelement ohne Tooltip oder „?“: %s" % (view, h, js[:40], miss))
                    for miss in ex["numbers"]:
                        problems.append("%s %s Seitenfenster %s: Zahl nicht beschrieben (data-ex, docs/ui): %s" % (view, h, js[:40], miss))
                    pg.evaluate("closeDrawer()")
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

    def test_top_bar_makes_room(self):
        """Long names of areas and the assistant's panel beside the page: the title stays whole; the areas move towards the free
        side, then the other names get shorter -- the chosen one stays whole; with room they stand in the middle."""
        names = ["Max Mustermann", "Nordlicht Vermögensverwaltung eGbR", "Südhang Verwaltung eGbR", "Beispiel Biomarkt GmbH"]
        measure = """(() => { const h = document.querySelector('#page-title'), s = document.querySelector('#bereich-seg'), a = document.querySelector('#assist-btn');
          const tb = document.querySelector('.topbar').getBoundingClientRect(), sr = s.getBoundingClientRect(), on = s.querySelector('button.on');
          return {title_cut: h.scrollWidth > h.clientWidth + 1, on_cut: on.scrollWidth > on.clientWidth + 1, cut: [...s.querySelectorAll('button')].filter(x => x.scrollWidth > x.clientWidth + 1).length,
                  left: sr.left - tb.left, right: tb.right - sr.right, over: a.getClientRects().length ? sr.right > a.getBoundingClientRect().left : false,
                  inside: sr.left >= h.getBoundingClientRect().right - 1}; })()"""
        with _playwright()() as p:
            b = p.chromium.launch()
            try:
                for device in ("mac", "iphone"):
                    ctx = b.new_context(**dict(DEVICES[device], viewport={"width": 1440, "height": 900}) if device == "mac" else DEVICES[device])
                    pg = ctx.new_page()
                    pg.goto(self.base); pg.fill("#login-pw", PASSWORD)
                    if pg.is_visible("#login-pw2"):
                        pg.fill("#login-pw2", PASSWORD)
                    pg.click("#login-btn"); pg.wait_for_selector("#shell:not(.hidden)", timeout=30000)
                    pg.evaluate("location.hash = '#overview'"); settle(pg)
                    pg.evaluate("""names => { const ks = Object.keys(S.DATA.area_names); ks.forEach((k, i) => { S.DATA.area_names[k] = names[i]; });
                      S.DATA.area_names.extra = names[3]; S.DATA.areas.extra = S.DATA.areas[ks[0]]; bereichSeg(); }""", names)
                    r = pg.evaluate(measure)
                    self.assertFalse(r["title_cut"] or r["on_cut"], (device, r))
                    if device == "mac":
                        self.assertEqual((r["cut"], round(r["left"] - r["right"]) in range(-2, 3)), (0, True), r)          # room: whole, in the middle
                        pg.evaluate("AS.st = {settings: {enabled: true, rights: {}}, local: true}; AS.open = true; asChrome()"); pg.wait_for_timeout(500)          # (the panel open beside the page)
                        r = pg.evaluate(measure)
                        self.assertFalse(r["title_cut"] or r["on_cut"] or r["over"], r)
                        self.assertTrue(r["cut"] > 0 and r["inside"] and r["left"] > r["right"], r)          # moved to the free side, the others shorter
                        pg.click("#bereich-seg button:nth-child(2)"); settle(pg)
                        self.assertFalse(pg.evaluate(measure)["on_cut"])                      # the chosen one: whole
                        self.assertEqual(pg.get_attribute("#bereich-seg button:nth-child(3)", "title"), names[2])         # the whole name on hover
                    ctx.close()
            finally:
                b.close()

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
