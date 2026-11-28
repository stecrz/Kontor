"""Random click paths (user 2026-11-24, ROADMAP "Testwelt ausbauen"): what the user checks by hand, walked at random -- pages,
dialogs, side windows and references (a right click on a figure, "Im Chat fragen", back to it by a click on the reference) in a
changing order, light and dark, MacBook and iPhone, Chromium and WebKit (Safari's engine, where it is installed), German and
now and then English, on changing worlds: the tests' made-up world, the demo, a random world of test_worlds (one to three
private areas, up to four companies, ten days to four years ending between 2023 and 2027, the browser's clock on its day) and
an empty Kontor (MoneyMoney without any account).

After every step: no script error, the page never scrolls sideways, nothing lies on a control or a text (but what opens above
the page on purpose: the side window, a menu, a dialog, the bar at the top, a column that stays), no text cut off (unless an
ellipsis says so) and no words beyond their button, and what opens above the page lies inside the window. Keys: Esc closes what
is open (side window, menu, dialog, the menu of a right click), Enter takes the focused choice (a dialog, the menu of a right
click, a focused card or field), ⌘S saves the booking rules (and saves nothing while nothing changed). States stay when a page
or a side window is opened again: the same view of the same data shows what was opened, chosen and scrolled before.

A failure names its case, its view and every step: KONTOR_FUZZ_SEED=<number> walks it again
(python3 -m pytest -q tests/test_clickpaths.py). By hand 3 fixed cases (KONTOR_CLICK_SEEDS); on GitHub only at night, as many as fit
(nightly.yml); a case a night found goes into FOUND_CLICKS once fixed. All names and amounts are made up."""
import datetime
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import fixtures as F            # noqa: E402
import test_e2e as T            # noqa: E402
import test_tour as TT          # noqa: E402
import test_worlds as TW        # noqa: E402
import core                     # noqa: E402
import service                  # noqa: E402
from service import App, make_handler    # noqa: E402
from fixtures import new_store  # noqa: E402

PASSWORD = TT.PASSWORD
FOUND_CLICKS = [24, 25, 29, 132684508, 520936342, 879068245, 447175332]     # cases a night found -- once fixed, their number goes here (each push walks them again); 3.17.71 (a night
                                # run by hand): the overview's figures wider than their cards beside the assistant, the balance's first
                                # head on the iPhone wider than its column, a net worth of one figure throughout drawn as NaN
                                # 3.17.80 (a night): the side window closed beside it stayed shut when its figure was pressed again
                                # at once (click, Enter); links and cells in a folded <details> taken for visible (covered)
                                # 3.17.84 (that night's other cases; the rest of them: FoundAtNightTest): the balance sheet on the iPhone
                                # opened again stood 28 px from where it was left
FOUND_CLICKS += [220413250]
FOUND_CLICKS += [882424172, 557437501]     # 3.17.95 (a night, iPhone, WebKit): the heat map's last month name in the average's heading; a cell
                                            # scrolled beyond its table's edge taken for free (the tap scrolled it under the names)
FOUND_CLICKS += [874536567]     # 3.17.96 (by hand, iPhone, WebKit): a point half a pixel inside a hairline band of the flow chart, tapped on
                                # the band beside it (WebKit taps on whole pixels)
FOUND_CLICKS += [552234862]     # 3.17.96 (by hand, iPhone, WebKit, under load -- not again alone): "ResizeObserver loop completed with
                                # undelivered notifications" on a page change -- the title bar's height was set inside its observer
FOUND_CLICKS += [594715502, 740557602, 843199979]     # 3.17.105 (a night, WebKit; under load only): the same on a page change from the
                                # balance or the cash flow -- the new page drawn inside an observer's callback (WebKit runs a finished
                                # request's answer there) took away what the old page's charts observed (PageSwapObserversTest)
FOUND_CLICKS += [103983820, 308844772]     # 3.17.131 (a night): on the iPhone the first tap on a cell of the heat map showed no numbers
                                            # right after its side window was closed (the walk: "opens no second time"; it taps twice
                                            # now, as a user does); a reference to a booking that other rules had taken away -- Kontor
                                            # says so, the walk expected a mark (FoundAtNightTest)
KINDS = ["test", "random", "demo", "empty"]
LOCKED_401 = "the server responded with a status of 401"      # a request of a session that was just locked (demo_in)
WORLD_NAMES = {"test": "Testwelt", "random": "Zufallswelt", "demo": "Demo", "empty": "leeres Kontor"}
MAC_SIZES = [(1440, 900), (1512, 945), (1280, 800)]          # a 14-inch MacBook, the window nearly full screen (and a bit smaller)
# pages that only show (a click there opens, folds or picks a view -- never changes data); the others hold forms
SHOWING = ("overview", "balance", "cashflow", "planning", "properties", "tax", "transactions", "categories", "bookings")
# switches of a view, safe to click anywhere (the choice of an area, months or years, levels, periods, ranges ...)
TOGGLES = ("#bereich-seg button, #modus-seg button, #cf-ebene button, #cf-zeit button, #cf-heat-mode button, #cf-pie-art button, "
           "#bch-rb button, #log-min button, #von-jahr button, .cf-shift, #pos-all, #bch-plan, #bch-link, .lc .lc-big, "
           "#main .tabs button, #main label:has(#alle-zeilen), #main label:has(#planan), #main label:has(#realan), #main label:has(#kaufkraft-an), "
           "#main tr.pos td:first-child, #main table.cf-names tr[data-tog] td:first-child, #main details > summary")

# what the page holds as its view (compared when the same view of the same data is opened again)
VIEW_KEY = r"""(() => {
  const skip = new Set(['DATA', 'CFG', 'KONTEN', 'KATS', 'STATUS', 'csrf', 'tab', 'sub', 'sel']), o = {};
  for (const [k, v] of Object.entries(S)) if (!skip.has(k) && typeof v !== 'function') o[k] = v instanceof Set ? [...v] : v;
  return [location.hash, JSON.stringify(o), (S.DATA || {}).as_of || '', document.body.classList.contains('as-open'), innerWidth].join('|');
})()"""
RESTING = r"""(() => document.getAnimations().some(a => a.playState === 'running' && isFinite(a.effect.getComputedTiming().endTime)) ? Math.random() :
  ['.side', '#drawer', '#assist', '.dlg', '#ctx'].map(q => { const el = document.querySelector(q); if (!el) return ''; const r = el.getBoundingClientRect(); return [r.left, r.top, r.width].map(Math.round).join(','); }).join('|'))()"""
# the marked element in view and free to click: "ok"; "layer" (a column or heading that stays, a bar, a panel lies above it on
# purpose: a user clicks elsewhere), "away" (not to be brought into view), "covered <what>" (something of its own layer on it),
# "gone" (the page was drawn anew since it was marked)
FREE = r"""(() => {
  const el = document.querySelector('[data-cp]'); if (!el) return 'gone'; if (!el.closest('#main, #drawer')) return 'ok';
  if (el.checkVisibility && !el.checkVisibility()) return 'away';                 // (in a folded <details>: not to be seen)
  const bar = document.querySelector('.topbar'), top = bar && !bar.closest('#drawer') ? bar.getBoundingClientRect().bottom : 0;
  const hit = () => { const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
    if (y < top + 4 || y > innerHeight - 4 || x < 0 || x > innerWidth) return null;
    // (its middle outside a box that clips it -- a table's cell scrolled sideways beyond its edge: not to be seen there, though
    // the point lies on the card around it; a tap would scroll it under the names that stay -- a night's click path, 3.17.95)
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) { const s = getComputedStyle(a);
      if (s.overflowX !== 'visible' || s.overflowY !== 'visible') { const q = a.getBoundingClientRect(); if (x < q.left || x > q.right || y < q.top || y > q.bottom) return null; } }
    const e = document.elementFromPoint(x, y); return !e || e === el || el.contains(e) || e.contains(el) ? 'ok' : e; };
  let h = hit(); if (h === 'ok') return 'ok';
  el.scrollIntoView({block: 'center', inline: 'center'}); h = hit(); if (h === 'ok') return 'ok';
  if (!h) return 'away';
  for (let a = h; a && a !== document.body; a = a.parentElement) { const p = getComputedStyle(a).position; if (p === 'sticky' || p === 'fixed') return 'layer'; }
  return 'covered ' + h.tagName.toLowerCase() + (h.id ? '#' + h.id : '') + (typeof h.className === 'string' && h.className ? '.' + h.className.trim().split(/\s+/)[0] : '') + ' „' + (h.textContent || '').trim().slice(0, 30) + '“';
})()"""
# a point on the marked shape of a chart, from its box's top left (the middle of a ring's part lies in the ring's hole, that of
# a bar under its label): where a user clicks it; null: none found. A whole pixel whose neighbours one pixel away hit the shape
# too -- WebKit taps on whole pixels, so a point half a pixel inside a hairline band (a small amount beside a big one in the flow
# chart) was tapped on the band next to it; a user taps such an item's name (a night's click path, iPhone, WebKit: 3.17.96)
POINT = r"""(() => {
  const el = document.querySelector('[data-cp]'); if (!el) return null;
  const r = el.getBoundingClientRect(), f = [0.5, 0.25, 0.75, 0.12, 0.88];
  const on = (x, y) => { const e = document.elementFromPoint(x, y); return !!e && (e === el || el.contains(e)); };
  for (const b of f) for (const a of f) { const x = Math.round(r.left + r.width * a), y = Math.round(r.top + r.height * b);
    if (on(x, y) && on(x - 1, y) && on(x + 1, y) && on(x, y - 1) && on(x, y + 1)) return {x: x - r.left, y: y - r.top}; }
  return null;
})()"""
# by touch: the first tap on a month or a cell of the cash flow's charts has shown its numbers, the next one acts (app.js: CF.armed)
ARMED = "typeof CF !== 'undefined' && !!CF.armed && !document.querySelector('#drawer').classList.contains('open')"
TIP_SHOWN = "(() => { const b = document.querySelector('#cf-tip'); return !!b && !b.classList.contains('hidden') && b.textContent.trim() !== ''; })()"
# a reference clicked: what it points to is marked, in view -- or Kontor says that the place is no longer on the page
MARKED = "[...document.querySelectorAll('.as-mark')].some(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.bottom > 0 && r.top < innerHeight; })"
NOT_FOUND = "(() => { const b = document.querySelector('#toast'); return !!b && !b.classList.contains('hidden') && b.textContent === t('ki_ref_nicht_gefunden'); })()"
DRAWER_READY = "document.querySelector('#drawer').classList.contains('open') && !document.querySelector('#drawer .spin') && !document.querySelector('#drawer').textContent.includes(t('wird_geladen'))"
SNAP = r"""(root => {
  const box = document.querySelector(root); if (!box) return null;
  // (seen: also not in a folded <details> -- Chromium keeps its contents' boxes, only checkVisibility() knows: 3.17.80)
  const vis = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden' && (!el.checkVisibility || el.checkVisibility());
  const who = el => el.id ? '#' + el.id : el.tagName.toLowerCase() + Object.entries(el.dataset).filter(([k]) => k !== 'cp' && k !== 'cftip').map(([k, v]) => `[${k}=${v}]`).join('') + (el instanceof SVGElement ? '' : ' „' + (el.textContent || '').trim().slice(0, 24) + '“');          // (a chart's part: its label is drawn by the chart, now or a moment later)
  // the page's own state: what stands in a folded section (<details>) is none of it -- Kontor folds them again when another page
  // was open in between (KEEP_OPEN: "folded sections open only while the same page is drawn again"); the side window's are compared (open)
  const page = el => root !== '#main' || !el.closest('details');
  const on = [...box.querySelectorAll('button.on, [aria-pressed="true"], [aria-selected="true"], input[type="checkbox"]:checked, input[type="radio"]:checked')].filter(vis).filter(page).map(who);
  const rows = [...box.querySelectorAll('tr')].filter(vis).filter(page).length;
  const open = root === '#drawer' ? [...box.querySelectorAll('details[open]')].map(who) : [];
  // what stands in the middle of the window (the same view, also when pictures above it got their height a moment later)
  const m = box.getBoundingClientRect(), mid = document.elementFromPoint(m.left + m.width / 2, innerHeight / 2);
  return {on, rows, open, y: Math.round(root === '#main' ? pageY() : box.scrollTop), mid: mid && box.contains(mid) ? who(mid) : '', title: (document.querySelector(root === '#drawer' ? '#drawer h2' : '#page-title') || {}).textContent || ''};
})"""

# layout of what is on screen now: sideways, outside the window, cut off, spilling, covered
LAYOUT = r"""(() => {
  const out = {wide: null, outside: [], cut: [], over: []};
  const de = document.documentElement, vw = de.clientWidth, vh = de.clientHeight;
  const CS = new Map(), cs = el => { let s = CS.get(el); if (!s) { s = getComputedStyle(el); CS.set(el, s); } return s; };
  const shown = el => el.checkVisibility ? el.checkVisibility({opacityProperty: true, visibilityProperty: true}) && el.getClientRects().length > 0 : el.getClientRects().length > 0;
  const name = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).filter(c => c !== 'on').slice(0, 2).join('.') : '');
  const desc = el => { const p = []; for (let a = el, i = 0; a && a !== document.body && i < 3; a = a.parentElement, i++) p.unshift(name(a)); return p.join(' › '); };
  const words = el => ((el.innerText || el.textContent || '') + '').trim().replace(/\s+/g, ' ').slice(0, 30);
  const clips = v => v === 'hidden' || v === 'clip', scrolls = v => v === 'auto' || v === 'scroll';
  const clear = c => !c || c === 'transparent' || /,\s*0\)$|\/\s*0\)$/.test(c);
  // 1. the page itself never scrolls sideways (wide tables scroll in their own box)
  if (de.scrollWidth > vw + 1) {
    const clipped = el => { for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) { if (['auto', 'scroll', 'hidden', 'clip'].includes(cs(a).overflowX)) return true; } return false; };
    const wide = [...document.querySelectorAll('body *')].filter(el => shown(el) && el.getBoundingClientRect().right > vw + 1 && !clipped(el));
    out.wide = {scrollWidth: de.scrollWidth, width: vw, elements: [...new Set(wide.slice(-4).map(desc))]};
  }
  // 2. what opens above the page lies inside the window
  for (const el of document.querySelectorAll('#drawer.open, #ctx, .dlg, #assist.open, .as-pop, #cf-mpick, .side.open, #toast:not(.hidden)')) {
    if (!shown(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.left < -1 || r.top < -1 || r.right > vw + 1 || r.bottom > vh + 1) out.outside.push(desc(el) + ' [' + [r.left, r.top, r.right, r.bottom].map(Math.round).join(', ') + ']');
  }
  // 3. a text cut off: it reaches beyond the box that clips it (no "…" drawn there) -- or beyond its button, chip or pill
  const range = document.createRange(), leaves = new Map(), done = new Set();
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = tw.nextNode());) {
    const s0 = n.nodeValue; if (!s0 || !s0.trim()) continue;
    const p = n.parentElement;
    if (!p || p.closest('svg, script, style, textarea, select, noscript, template, [aria-hidden="true"], .sr-only') || !shown(p)) continue;
    range.selectNodeContents(n); const r = range.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;          // out of view: not looked at
    if (!leaves.has(p)) leaves.set(p, r);
    if (done.has(p)) continue;
    const fs = parseFloat(cs(p).fontSize) || 13;
    const face = p.closest('button, .pill, .chip');          // (a face that clips its words: below, "…" allowed)
    // (so is a label inside the face that clips its own words -- the reference before the question: page, then "long label…")
    const inner = el => { for (let a = el; a && a !== face; a = a.parentElement) if (clips(cs(a).overflowX)) return true; return false; };
    if (face && !face.closest('svg') && face.clientWidth > 4 && !clips(cs(face).overflowX) && !inner(p)) {
      const b = face.getBoundingClientRect();
      if (r.left < b.left - 1 || r.right > b.right + 1) { done.add(p); out.cut.push('über den Rand: ' + desc(p) + ' „' + s0.trim().slice(0, 30) + '“'); continue; }
    }
    for (let a = p; a && a !== document.body && a !== de; a = a.parentElement) {
      const s = cs(a);
      if (scrolls(s.overflowX) || scrolls(s.overflowY)) break;                       // a box that scrolls: the rest can be reached
      const cx = clips(s.overflowX), cy = clips(s.overflowY);
      if (!cx && !cy) continue;
      if (a.clientWidth < 2 || a.clientHeight < 2) break;                          // folded away: hidden, not cut
      const b = a.getBoundingClientRect(), l = b.left + a.clientLeft, t = b.top + a.clientTop, rr = l + a.clientWidth, bb = t + a.clientHeight;
      if (!(r.right > l && r.left < rr && r.bottom > t && r.top < bb)) break;      // wholly outside its box: hidden on purpose
      const ell = s.textOverflow === 'ellipsis' || (s.webkitLineClamp && s.webkitLineClamp !== 'none');
      const outX = cx && (r.left < l - 1 || r.right > rr + 1), outY = cy && (r.top < t - fs * 0.3 || r.bottom > bb + fs * 0.3);
      if ((outX || outY) && !ell) { done.add(p); out.cut.push(desc(p) + ' „' + s0.trim().slice(0, 30) + '“'); }
      break;
    }
  }
  // 4. covered: something of the same layer lies on a control or a text (what opens above the page, the bar at the top, a column
  // or heading that stays and a tooltip lie above it on purpose)
  const LAYER = '#drawer, #ctx, .dlg-back, #assist, #toast, .side, .topbar, #find-bar, .as-pop, #cf-mpick, [id$="-tip"], [role="tooltip"]';
  const LY = new Map(), layer = el => {
    if (LY.has(el)) return LY.get(el);
    let r = document.body;
    for (let a = el; a && a.nodeType === 1 && a !== document.body; a = a.parentElement) { const p = cs(a).position; if (p === 'fixed' || p === 'sticky' || a.matches(LAYER)) { r = a; break; } }
    LY.set(el, r); return r;
  };
  const paints = el => {
    if (el instanceof SVGElement || el.matches('img, canvas, video, input, select, textarea, button')) return true;
    const s = cs(el);
    if (s.backgroundImage !== 'none' || !clear(s.backgroundColor)) return true;
    if (['Top', 'Right', 'Bottom', 'Left'].some(k => parseFloat(s['border' + k + 'Width']) > 0 && s['border' + k + 'Style'] !== 'none' && !clear(s['border' + k + 'Color']))) return true;
    return [...el.childNodes].some(n => n.nodeType === 3 && n.nodeValue.trim());
  };
  const cand = new Map(leaves);
  for (const el of document.querySelectorAll('button, a[href], input:not([type="hidden"]), select, textarea, summary, [role="button"], [tabindex="0"]')) if (!cand.has(el)) cand.set(el, null);
  const seen = new Set();
  for (const [el, tr] of cand) {
    if (el.closest('svg') || !shown(el) || cs(el).pointerEvents === 'none') continue;
    const r = tr || el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    const y = r.top + r.height / 2, pts = [[r.left + r.width / 2, y]];
    if (r.width > 24) pts.push([r.left + 3, y], [r.right - 3, y]);
    const L = layer(el);
    for (const [x, yy] of pts) {
      if (x < 0 || yy < 0 || x >= vw || yy >= vh) continue;
      const st = document.elementsFromPoint(x, yy), i = st.findIndex(e => e === el || el.contains(e));
      if (i <= 0) continue;                                                        // on top, or clipped away here
      const top = st.slice(0, i).find(e => !el.contains(e) && layer(e) === L && paints(e));
      if (!top) continue;
      const k = desc(el) + '|' + desc(top);
      if (!seen.has(k)) { seen.add(k); out.over.push(desc(el) + ' „' + words(el) + '“ unter ' + desc(top) + (words(top) ? ' „' + words(top) + '“' : '')); }
      break;
    }
  }
  return out;
})()"""


def _date_class(day):
    return type("FixedDate", (datetime.date,), {"today": classmethod(lambda cls: day)})


def categories_of(rows):
    """The categories a world's bookings use, as MoneyMoney lists them (a group, then its categories, indented)."""
    have = {n for n, i, g, x in T.MockBridge.CATS if i == 0}
    tree = {}
    for r in rows:
        p = (r.get("categoryPath") or "").split("\\")
        if p[0] and p[0] not in have:
            tree.setdefault(p[0], [])
            if len(p) > 1 and p[1] not in tree[p[0]]:
                tree[p[0]].append(p[1])
    out = []
    for top, subs in tree.items():
        out.append((top, 0, bool(subs), {}))
        out += [(s, 1, False, {}) for s in subs]
    return out


class Case:
    """One case: its world, its view and its steps -- all drawn from its number."""

    def __init__(self, seed, webkit):
        rnd = self.rnd = random.Random(seed)
        self.seed = seed
        fixed = seed < 10 ** 6
        if fixed:          # the fixed ones go round every world and view (per push: the test world on the Mac, a random world on the iPhone, the demo in WebKit)
            self.kind = KINDS[seed % 4]
            self.device = ("mac", "iphone")[(seed + seed // 4) % 2]
            self.theme = ("dark", "light")[(seed // 2 + seed // 8) % 2]
            self.engine = "webkit" if webkit and seed % 3 == 2 else "chromium"
            self.lang = "en" if seed % 7 == 6 else "de"
            self.steps = 14
        else:
            self.kind = rnd.choices(KINDS, weights=[3, 4, 2, 1])[0]
            self.device = rnd.choice(("mac", "iphone"))
            self.theme = rnd.choice(("dark", "light"))
            self.engine = "webkit" if webkit and rnd.random() < 0.35 else "chromium"
            self.lang = "en" if rnd.random() < 0.2 else "de"
            self.steps = rnd.randint(10, 24)
        self.size = rnd.choice(MAC_SIZES)
        self.world_seed = rnd.randrange(10 ** 9)
        self.assistant = self.kind in ("test", "random") and (seed % 2 == 0 if fixed else rnd.random() < 0.6)
        self.all_new = rnd.random() < 0.5

    def describe(self):
        world = WORLD_NAMES[self.kind] + (" %d" % self.world_seed if self.kind == "random" else "")
        view = "%s %s%s, %s, %s" % ("Mac" if self.device == "mac" else "iPhone", "dunkel" if self.theme == "dark" else "hell",
                                    " %d×%d" % self.size if self.device == "mac" else "", "WebKit" if self.engine == "webkit" else "Chromium",
                                    "englisch" if self.lang == "en" else "deutsch")
        return "Fall %d (%s; %s%s)" % (self.seed, world, view, "; Assistent an" if self.assistant else "")


class Walk:
    """A browser page walked at random through Kontor; problems are collected with the step they appeared in."""

    def __init__(self, test, case, pg, store):
        self.t, self.c, self.pg, self.rnd, self.store = test, case, pg, case.rnd, store
        self.log, self.problems, self.errors = [], [], []
        self.snaps, self.last_hash, self.n, self.plain = {}, None, 0, False
        self.latest = {}                    # page -> the view of it noted last (Kontor remembers one place per page)
        self.count = {"Zustände verglichen": 0, "Seitenfenster": 0, "wieder geöffnet": 0, "Rechtsklicks": 0, "Bezüge": 0, "Dialoge": 0, "⌘S": 0}
        self.mobile = case.device == "iphone"
        self.ref = None                     # a reference waiting in the assistant's panel: where it points to
        pg.on("pageerror", lambda e: self.errors.append("Skriptfehler: %s" % e))
        pg.on("console", lambda m: self.errors.append("Konsole: %s%s" % (m.text, " – " + (m.location or {}).get("url", "") if "Failed to load" in m.text else "")) if m.type == "error" else None)
        pg.on("dialog", self._dialog)

    # -- helpers ----------------------------------------------------------------------------------------------------------
    def _dialog(self, d):
        """A question of the browser (unsaved changes ...): answered at random, as a user would."""
        yes = self.rnd.random() < 0.5 if d.type == "confirm" else False
        self.log.append("   Rückfrage „%s“ → %s" % (d.message[:60], "ja" if yes else "nein"))
        try:
            d.accept() if yes else d.dismiss()
        except Exception:
            pass

    def problem(self, what):
        line = "Schritt %d: %s" % (self.n, what)
        if line not in self.problems:
            self.problems.append(line)

    def js(self, code, arg=None):
        return self.pg.evaluate(code, arg) if arg is not None else self.pg.evaluate(code)

    def until(self, code, seconds=8.0, arg=None):
        end = time.time() + seconds
        while True:
            try:
                if self.js(code, arg):
                    return True
            except Exception as e:
                if "context was destroyed" not in str(e) and "navigat" not in str(e):
                    raise
            if time.time() > end:
                return False
            self.pg.wait_for_timeout(80)

    def settle(self):
        try:
            TT.settle(self.pg)
        except AssertionError as e:
            self.problem(str(e))
            return False
        # a side window, the panel or the menu still sliding in or out: until they have come to rest (not every engine lists a
        # transition that has just begun among the animations)
        end, last = time.time() + 4, None
        while time.time() < end:
            now = self.js(RESTING)
            if now == last:
                break
            last = now
            self.pg.wait_for_timeout(60)
        return True

    def rest_pointer(self):
        """The mouse away from what was clicked (its hover look and tooltips are not the page's layout)."""
        if not self.mobile:
            self.pg.mouse.move(2, int(self.js("innerHeight") * 0.62))

    def pick(self, code, arg=None):
        """Marks one of the elements code lists (at random) to act on it; returns its description or None."""
        n = self.js("(() => { document.querySelectorAll('[data-cp]').forEach(e => delete e.dataset.cp); return (%s).length; })()" % code)
        if not n:
            return None
        i = self.rnd.randrange(n)
        return self.js("i => { const el = (%s)[i]; el.dataset.cp = '1'; return (el.id ? '#' + el.id : el.tagName.toLowerCase()) + ' „' + (el.textContent || el.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').slice(0, 30) + '“'; }" % code, i)

    def press(self, how="click", button="left"):
        """Acts on the marked element: a click (a tap on the iPhone), a right click, or the focus and Enter."""
        loc = self.pg.locator("[data-cp='1']").first
        # in view first, as a user scrolls to it (else the click scrolls the page itself -- the page is then left elsewhere than
        # the state noted last); what the page shows now is its state when it is left
        free = self.js(FREE)
        if free == "gone":
            self.note("nicht mehr da (die Seite wurde neu gezeichnet), übersprungen")
            return False
        at = {}
        if self.js("document.querySelector('[data-cp]') instanceof SVGElement"):
            # a shape of a chart: clicked where it is drawn; with keys nothing needs to be free
            pos = self.js(POINT) if how != "enter" else None
            if how != "enter" and not pos:
                self.note("kein freier Punkt der Form, übersprungen")
                return False
            at = {"position": pos} if pos else {}
            free = "ok" if free.startswith("covered") else free
        if free != "ok":
            if free.startswith("covered"):
                self.problem("überlappt: zum Klicken liegt darauf %s" % free[8:])
            else:
                self.note("verdeckt (%s), übersprungen" % {"layer": "eine stehenbleibende Spalte oder Leiste liegt darüber", "away": "nicht im Blick"}.get(free, free))
            return False
        self.note_state()
        try:
            if how == "enter":
                loc.focus(timeout=4000); self.pg.keyboard.press("Enter")
            elif button == "right":
                loc.click(button="right", timeout=4000, **at)
            elif self.mobile:
                loc.tap(timeout=4000, **at)
            else:
                loc.click(timeout=4000, **at)
            return True
        except Exception as e:
            msg = str(e).split("\n")
            hit = [m for m in msg if "intercepts pointer events" in m]
            if hit:
                self.problem("nicht anklickbar, etwas liegt darauf: %s" % hit[0].strip()[:200])
            return False

    def tab(self):
        return self.js("S.tab")

    def view(self):
        return self.js(VIEW_KEY)

    def stable(self):
        return self.js("document.querySelector('#main .loading') === null && !document.querySelector('#drawer.open') && !document.querySelector('.dlg-back, #ctx')")

    def note_state(self):
        """The page's state as it is now (before a click leaves it)."""
        if self.stable():
            key = self.view()
            self.snaps[key] = self.js(SNAP, "#main")
            self.latest[self.js("location.hash")] = key

    # -- checks after every step -----------------------------------------------------------------------------------------
    def check(self):
        self.rest_pointer()
        self.js("document.querySelectorAll('[data-cp]').forEach(e => delete e.dataset.cp)")
        for e in self.errors:
            self.problem(e)
        self.errors.clear()
        r = self.js(LAYOUT)
        if r["outside"]:          # still sliding in (a busy machine draws no frame between two looks, so it seemed at rest): looked at once more
            self.pg.wait_for_timeout(400)
            r = self.js(LAYOUT)
        if r["wide"]:
            self.problem("waagrechte Scrollleiste: %s" % r["wide"])
        for x in r["outside"]:
            self.problem("ragt aus dem Fenster: %s" % x)
        for x in r["cut"][:6]:
            self.problem("abgeschnitten: %s" % x)
        for x in r["over"][:6]:
            self.problem("überlappt: %s" % x)
        # the same view of the same data opened again: it shows what it showed (opened, chosen, scrolled)
        h, plain, self.plain = self.js("location.hash"), self.plain, False
        if not self.stable():
            self.last_hash = h
            return
        key, snap = self.view(), self.js(SNAP, "#main")
        if h != self.last_hash and key in self.snaps and snap is not None:
            self.count["Zustände verglichen"] += 1
            was = self.snaps[key]
            # where it stands: only when it was opened from the menu or a tab (a figure or a card leads to its place on purpose),
            # and only against the view it was left in (one place per page: scrolled later beside the assistant's panel, the
            # page is not where its view without the panel was)
            # ... and not where the page is shorter now than its place (a folded section was open when it was left): it stands at its end
            ended = self.js("(() => { const sc = pageScroller(); return pageY() >= sc.scrollHeight - sc.clientHeight - 2; })()") and snap["y"] < was["y"]
            placed = plain and self.latest.get(h) == key and not ended
            diff = {k: (was[k], snap[k]) for k in snap if was.get(k) != snap[k] and k != "mid"
                    and not (k == "y" and (not placed or abs(was[k] - snap[k]) <= 2 or was["mid"] == snap["mid"]))}
            if diff:
                room = self.js("(() => { const sc = pageScroller(); return 'Seite ' + sc.scrollHeight + ' hoch, ' + sc.clientHeight + ' sichtbar, gemerkt ' + JSON.stringify(SCROLL.pos); })()") if "y" in diff else ""
                self.problem("Zustand beim erneuten Öffnen von %s nicht wie zuvor: %s%s" % (h, json.dumps(diff, ensure_ascii=False)[:600], " (%s)" % room if room else ""))
        self.snaps[key] = snap
        self.latest[h] = key
        self.last_hash = h

    # -- the steps ---------------------------------------------------------------------------------------------------------
    def walk(self, n):
        acts = [("page", 6), ("toggle", 5), ("open", 5), ("ref", 3), ("dialog", 2), ("scroll", 2), ("save", 1), ("panel", 1)]
        for _ in range(n):
            name = self.rnd.choices([a for a, w in acts], weights=[w for a, w in acts])[0]
            self.n += 1
            self.log.append("%d." % self.n); self.cur = len(self.log) - 1
            try:
                self.tidy()
                getattr(self, "do_" + name)()
            except Exception as e:
                if "Target page, context or browser has been closed" in str(e):
                    raise
                self.problem("%s: %s" % (type(e).__name__, str(e).split("\n")[0][:300]))
            if len(self.problems) >= 8:
                break

    def tidy(self):
        """What a user closes before going on: on the iPhone the menu and the assistant over the page; a side window left open
        (a step that ended inside it) with Esc."""
        if self.mobile and self.js("document.querySelector('.side').classList.contains('open')"):
            self.pg.locator("#menu-btn").tap(timeout=4000)
        if self.mobile and self.js("document.querySelector('#assist').classList.contains('open') && S.tab !== 'assistant'"):
            self.pg.locator("#assist .as-close").first.tap(timeout=4000)
        if self.js("document.querySelector('#drawer').classList.contains('open')"):
            self.pg.keyboard.press("Escape")
        if self.js("document.querySelector('.side').classList.contains('open') || document.querySelector('#drawer').classList.contains('open') || (document.querySelector('#assist').classList.contains('open') && innerWidth <= 900 && S.tab !== 'assistant')"):
            self.settle()

    def note(self, what):
        i = getattr(self, "cur", len(self.log) - 1)          # (the step's line, also after a question of the browser below it)
        self.log[i] += (" " if self.log[i].endswith(".") else " · ") + what

    def do_page(self):
        """Another page: from the menu (on the iPhone it opens first), or a page's own link to one of its parts."""
        subs = "[...document.querySelectorAll('#main a[href^=\"#\"], #main .tabs button[data-next]')].filter(a => a.getClientRects().length && (!a.checkVisibility || a.checkVisibility()) && /^#[a-z]+\\/[a-z-]+$/.test(a.getAttribute('href') || a.dataset.next || ''))"
        if self.rnd.random() < 0.3 and self.pick(subs):
            what = self.js("document.querySelector('[data-cp]').getAttribute('href') || document.querySelector('[data-cp]').dataset.next")
            self.note("Teil der Seite " + what)
            if not self.press():
                return
        else:
            if self.mobile:
                self.pg.locator("#menu-btn").tap(timeout=4000)
                if not self.until("document.querySelector('.side').classList.contains('open') && document.querySelector('.side').getBoundingClientRect().left >= 0", 3):
                    self.problem("das Menü öffnet nicht")
                    return
                self.settle(); self.check()
                if self.rnd.random() < 0.25:          # Esc closes it (a narrow window on the Mac, an iPad with keys)
                    self.pg.keyboard.press("Escape")
                    if not self.until("!document.querySelector('.side').classList.contains('open')", 2):
                        self.problem("Esc schließt das Menü nicht")
                    self.note("Menü, Esc")
                    return
            got = self.pick("[...document.querySelectorAll('#nav a[href^=\"#\"]')].filter(a => a.getClientRects().length && (!a.checkVisibility || a.checkVisibility()) && !a.closest('.hidden'))")
            if not got:
                return
            what = self.js("document.querySelector('[data-cp]').getAttribute('href')")
            self.note("Menü " + what)
            if not self.press():
                return
        self.plain = not what.startswith("#help/")          # (a section of the help: the link leads to it, wherever the help was left)
        if self.c.kind == "demo" and self.js("w => DEMO_OFF.has(w.slice(1).split('/')[0])", what):
            # the demo has no settings, no setup and no log (about this Mac and the real Kontor): a link there leads to the overview
            if not self.until("S.tab === 'overview' && location.hash === '#overview'", 6):
                self.problem("Demo: %s führt nicht zur Übersicht (steht auf %s)" % (what, self.js("location.hash")))
        elif not self.until("location.hash.split('?')[0] === %s || S.tab === %s.slice(1).split('/')[0]" % (json.dumps(what), json.dumps(what)), 6):
            self.problem("Seite %s nicht erreicht (steht auf %s)" % (what, self.js("location.hash")))
        if self.settle():
            self.check()

    def do_toggle(self):
        """A switch of the view: an area, months or years, a level, a period, a row or section opened or closed."""
        got = self.pick("[...document.querySelectorAll(%s)].filter(el => el.getClientRects().length && (!el.checkVisibility || el.checkVisibility()) && !el.disabled && getComputedStyle(el).visibility !== 'hidden')" % json.dumps(TOGGLES))
        if not got:
            return self.do_page()
        self.note("Umschalter " + got)
        if self.press() and self.settle():
            self.check()

    def do_scroll(self):
        """Scrolled down the page (and a wide table sideways): what comes into view is checked too."""
        y = self.js("f => { const sc = pageScroller(); pageTo(Math.round((sc.scrollHeight - sc.clientHeight) * f)); return Math.round(pageY()); }", self.rnd.random())
        x = self.js("f => { const w = [...document.querySelectorAll('#main .wrap')].find(w => w.scrollWidth > w.clientWidth + 4); if (!w) return null; w.scrollLeft = Math.round((w.scrollWidth - w.clientWidth) * f); return w.scrollLeft; }", self.rnd.random())
        self.note("gescrollt auf %d%s" % (y, "" if x is None else ", Tabelle auf %d" % x))
        self.pg.wait_for_timeout(150)
        self.check()

    def do_open(self):
        """Something that opens: a figure, a row, a card, a field -- clicked, or focused and Enter. A side window that opens is
        looked at, closed (Esc, its ✕ or a click beside it) and, now and then, opened again: it shows what it showed."""
        if self.tab() not in SHOWING:
            return self.do_page()
        got = self.pick("""[...document.querySelectorAll('#main td, #main th, #main .nm, #main .ov-card, #main .kpi, #main .cf-heat-c, #main .cf-heat-n, #main .cf-br-row, #main a.ka-tx, #main [tabindex="0"], #main .card[data-im]')]
            .filter(el => el.getClientRects().length && (!el.checkVisibility || el.checkVisibility()) && getComputedStyle(el).cursor === 'pointer' && !el.querySelector('input, select, textarea, button') && !el.closest('input, select, textarea, button, label, .bk-rej, [data-cmd-s]'))""")
        if not got:
            return self.do_toggle()
        keys = self.rnd.random() < 0.35 and self.js("(() => { const el = document.querySelector('[data-cp]'); return el.tabIndex >= 0 && (el.matches('[tabindex=\"0\"], a, button')); })()")
        self.note(("Enter auf " if keys else "Klick auf ") + got)
        path = self.js("""(() => { const el = document.querySelector('[data-cp]'), p = [];
            for (let a = el; a && a.id !== 'main'; a = a.parentElement) p.unshift(a.tagName.toLowerCase() + ':nth-child(' + ([...a.parentElement.children].indexOf(a) + 1) + ')');
            return '#main > ' + p.join(' > '); })()""")
        h0 = self.js("location.hash")
        if not self.press("enter" if keys else "click"):
            return
        if self.until(DRAWER_READY, 3):
            self.settle()
            self.drawer(path, "enter" if keys else "click")
            return
        if self.js("location.hash") != h0:
            self.note("→ " + self.js("location.hash"))
        if self.settle():
            self.check()

    def drawer(self, path, how_opened="click"):
        """The side window: inside the window, readable; a folded part opened; closed by Esc, its ✕ or a click beside it -- then
        opened again: it shows what it showed when it was closed."""
        self.count["Seitenfenster"] += 1
        self.check()
        if self.rnd.random() < 0.4 and self.pick("[...document.querySelectorAll('#drawer details > summary')].filter(el => el.getClientRects().length && (!el.checkVisibility || el.checkVisibility()))"):
            self.note("aufgeklappt")
            if self.press():
                self.pg.wait_for_timeout(150); self.check()
        before = self.js(SNAP, "#drawer")
        how = self.rnd.choice(["Esc", "Esc", "✕", "daneben"])
        if how == "Esc":
            self.pg.keyboard.press("Escape")
        elif how == "✕":
            loc = self.pg.locator("#drawer .close").first
            loc.tap(timeout=4000) if self.mobile else loc.click(timeout=4000)
        else:          # beside it: on the page's title (nothing there opens or leads away)
            if self.js("document.querySelector('#drawer').getBoundingClientRect().left < document.querySelector('#page-title').getBoundingClientRect().left + 20"):
                how = "Esc"; self.pg.keyboard.press("Escape")          # (the side window fills the screen: nothing beside it)
            else:
                t = self.pg.locator("#page-title")
                t.tap(position={"x": 4, "y": 4}, timeout=4000) if self.mobile else t.click(position={"x": 4, "y": 4}, timeout=4000)
        self.note("zu mit " + how)
        if not self.until("!document.querySelector('#drawer').classList.contains('open')", 3):
            if not self.js("typeof drawerDirty === 'function' && drawerDirty()"):
                self.problem("das Seitenfenster schließt nicht (%s)" % how)
            return
        if self.settle():
            self.check()
        if self.rnd.random() < 0.5 or not before:
            return
        if not self.js("p => !!document.querySelector(p)", path):
            return
        self.js("p => { document.querySelectorAll('[data-cp]').forEach(e => delete e.dataset.cp); document.querySelector(p).dataset.cp = '1'; }", path)
        self.note("wieder geöffnet")
        if not self.press(how_opened):
            return
        # by touch the first tap on a month or a cell of the cash flow's charts shows its numbers, the second acts -- each time
        # anew, also after its side window was closed
        if self.mobile and how_opened == "click" and self.until(ARMED + " || document.querySelector('#drawer').classList.contains('open')", 2) and self.js(ARMED):
            if not self.js(TIP_SHOWN):
                self.problem("das erste Tippen zeigt die Zahlen der Stelle nicht")
            self.note("zweites Tippen")
            if not self.press(how_opened):
                return
        if not self.until(DRAWER_READY, 4):
            self.problem("das Seitenfenster öffnet beim zweiten Mal nicht")
            return
        self.settle()
        self.count["wieder geöffnet"] += 1
        again = self.js(SNAP, "#drawer")
        diff = {k: (before[k], again[k]) for k in again if before.get(k) != again[k] and k not in ("y", "mid")}
        if diff:
            self.problem("Seitenfenster beim erneuten Öffnen nicht wie zuvor: %s" % json.dumps(diff, ensure_ascii=False)[:600])
        self.check()
        self.pg.keyboard.press("Escape")
        self.until("!document.querySelector('#drawer').classList.contains('open')", 3)

    def do_dialog(self):
        """A question of Kontor's own (a short or a long one, two or three answers; or the password asked again): inside the
        window, readable, the first answer focused -- Enter takes it, Esc or a click beside it takes none."""
        long = self.rnd.random() < 0.4
        msg = ("Sollen die %d Umsätze von „Beispiel Vermögensverwaltung GmbH & Co. KG – Objekt Südhang, Bauabschnitt II“ in MoneyMoney die Kategorie wechseln?" % self.rnd.randint(2, 999)) if long else "Wirklich?"
        if self.rnd.random() < 0.3:
            self.note("Passwort-Dialog")
            self.js("m => { window.__dlg = undefined; askPassword(m).then(v => { window.__dlg = v; }); }", msg)
            if not self.until("!!document.querySelector('.dlg .dlg-pw') && document.activeElement === document.querySelector('.dlg .dlg-pw')", 3):
                self.problem("der Passwort-Dialog hat nicht den Fokus im Feld")
            self.settle(); self.check()
            if self.rnd.random() < 0.5:
                self.pg.keyboard.type("nur-ein-test"); self.pg.keyboard.press("Enter"); want, how = "nur-ein-test", "Enter"
            else:
                self.pg.keyboard.press("Escape"); want, how = None, "Esc"
        else:
            opts = [["a", "Überschreiben"], ["b", "Nur neue Umsätze"]][: self.rnd.choice([1, 2])]
            self.note("Dialog mit %d Antworten%s" % (len(opts) + 1, ", lang" if long else ""))
            self.js("([m, o]) => { window.__dlg = undefined; choose(m, o).then(v => { window.__dlg = v; }); }", [msg, opts])
            if not self.until("!!document.querySelector('.dlg') && document.activeElement === document.querySelector('.dlg button')", 3):
                self.problem("der Dialog hat nicht den Fokus auf der ersten Antwort")
            self.settle(); self.check()
            how = self.rnd.choice(["Enter", "Esc", "daneben"])
            if how == "Enter":
                self.pg.keyboard.press("Enter"); want = opts[0][0]
            elif how == "Esc":
                self.pg.keyboard.press("Escape"); want = None
            else:
                self.pg.mouse.click(3, 3) if not self.mobile else self.pg.touchscreen.tap(3, 3); want = None
        self.note(how)
        if not self.until("window.__dlg !== undefined && !document.querySelector('.dlg-back')", 3):
            self.problem("%s schließt den Dialog nicht" % how)
            self.js("document.querySelectorAll('.dlg-back').forEach(b => b.remove())")
            return
        self.count["Dialoge"] += 1
        got = self.js("window.__dlg")
        if got != want:
            self.problem("%s im Dialog gab %r statt %r" % (how, got, want))
        self.check()

    def do_ref(self):
        """A reference: a right click on a figure, a row, a heading or a chart -- its menu inside the window; Esc closes it, Enter
        takes its first entry (copy); with the assistant: "Im Chat fragen" puts it before the question, and a click on it later
        goes back there. (On the iPhone a reference without a right click is still open: ROADMAP.)"""
        if self.ref and self.rnd.random() < 0.5:
            return self.back_to_ref()
        if self.mobile:
            return self.do_open()
        got = self.pick("""[...document.querySelectorAll('#main [data-ex] td, #main [data-ex] th, #main [data-ex] .kpi, #main [data-ex] .ov-card, #main [data-ex] .lc, #main [data-ex] .cf-card, #drawer.open [data-ex] td')]
            .filter(el => { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4 && r.top > 60 && r.bottom < innerHeight - 4 && (!el.checkVisibility || el.checkVisibility()) && (el.textContent || '').trim(); })""")
        if not got:
            return self.do_open()
        self.note("Rechtsklick auf " + got)
        if not self.press(button="right"):
            return
        if not self.until("!!document.querySelector('#ctx button')", 2):
            self.note("kein Menü")
            return self.check()
        self.settle(); self.check()
        self.count["Rechtsklicks"] += 1
        items = self.js("[...document.querySelectorAll('#ctx button')].map(b => b.textContent.trim())")
        if self.js("document.activeElement && document.activeElement.closest('#ctx') === null"):
            self.problem("das Menü des Rechtsklicks hat nicht den Fokus")
        chat = [i for i in items if i in ("Im Chat fragen", "Ask in the chat")]
        copy = items and ("kopieren" in items[0] or items[0].lower().startswith("copy"))
        how = self.rnd.choice((["chat", "chat"] if chat else []) + ["Esc"] + (["Enter"] if copy else []))
        self.note(how)
        if how == "Esc":
            self.pg.keyboard.press("Escape")
            if not self.until("!document.querySelector('#ctx')", 2):
                self.problem("Esc schließt das Menü des Rechtsklicks nicht")
        elif how == "Enter":
            self.pg.keyboard.press("Enter")
            if not self.until("!document.querySelector('#ctx')", 2):
                self.problem("Enter wählt im Menü des Rechtsklicks nichts")
        else:
            self.pg.locator("#ctx button", has_text=chat[0]).click(timeout=4000)
            if not self.until("!!document.querySelector('#assist.open #as-refs .as-ref')", 4):
                self.problem("der Bezug steht nicht vor der Frage")
                return
            self.count["Bezüge"] += 1
            self.ref = self.js("(() => { const r = AS.refs[AS.refs.length - 1]; return {i: AS.refs.length - 1, route: (r.go || {}).route || '', label: r.label, mark: !!((r.go || {}).mark || {}).text}; })()")
            self.settle()
        self.check()

    def back_to_ref(self):
        """A click on the reference before the question: back to its page, the figure or row marked."""
        if not self.js("AS.open"):
            self.js("asShow(true)"); self.pg.wait_for_timeout(200)
        if not self.js("i => !!document.querySelector('#as-refs .as-ref-go[data-r=\"' + i + '\"]')", self.ref["i"]):
            self.ref = None
            return
        self.js("i => { document.querySelectorAll('[data-cp]').forEach(e => delete e.dataset.cp); document.querySelector('#as-refs .as-ref-go[data-r=\"' + i + '\"]').dataset.cp = '1'; }", self.ref["i"])
        self.note("zurück zum Bezug „%s“" % self.ref["label"][:40])
        if not self.press():
            return
        if self.ref["route"] and not self.until("r => location.hash.split('?')[0] === r.split('?')[0]", 6, self.ref["route"]):
            self.problem("der Bezug führt nicht zurück nach %s (steht auf %s)" % (self.ref["route"], self.js("location.hash")))
        elif self.ref["mark"]:
            self.until("(%s) || (%s)" % (MARKED, NOT_FOUND), 4)
            if self.js(MARKED):
                pass
            elif self.ref.get("stale") and self.js(NOT_FOUND):
                # the rules were saved since: other bookings, the row or figure may be gone -- then Kontor says so, and marks nothing
                self.note("die Stelle gibt es nach den geänderten Regeln nicht mehr – gemeldet")
            else:
                self.problem("der Bezug „%s“ markiert dort nichts im Blick" % self.ref["label"][:40])
        if self.settle():
            self.check()

    def do_panel(self):
        """The assistant's panel opened or closed beside the page (the page gets narrower)."""
        if not self.js("typeof asOn === 'function' && asOn() && S.tab !== 'assistant'"):
            return self.do_scroll()
        self.note("Assistent " + ("zu" if self.js("AS.open") else "auf"))
        loc = self.pg.locator("#assist-btn")
        if self.js("!!document.querySelector('#assist-btn').getClientRects().length"):
            loc.tap(timeout=4000) if self.mobile else loc.click(timeout=4000)
        else:
            self.js("asShow(!AS.open)")
        self.pg.wait_for_timeout(250)
        if self.settle():
            self.check()

    def do_save(self):
        """⌘S on the booking rules: nothing changed -- nothing saved (and not the browser's "save page"); a change -- saved."""
        if self.c.kind == "empty" or self.mobile:
            return self.do_toggle()
        if self.js("location.hash") != "#accounts/rules":
            self.js("location.hash = '#accounts/rules'")
            if not self.until("!!document.querySelector('#save-rules')", 8):
                return
            self.settle()
        self.note("Buchungsregeln, ⌘S")
        self.count["⌘S"] += 1
        self.js("""(() => { window.__saves = 0; window.__kept = null; const b = document.querySelector('#save-rules'); b.addEventListener('click', () => { window.__saves++; });
            if (!window.__keyWatch) { window.__keyWatch = true; window.addEventListener('keydown', e => { if (e.metaKey && e.key === 's') window.__kept = e.defaultPrevented; }); } })()""")
        if self.js("document.querySelector('#save-rules').disabled"):
            self.pg.keyboard.press("Meta+s"); self.pg.wait_for_timeout(150)
            if self.js("window.__saves") or self.js("window.__kept") is not True:
                self.problem("⌘S ohne Änderung: %s" % ("gespeichert" if self.js("window.__saves") else "nicht abgefangen (Browser würde die Seite sichern)"))
        sw = self.js("(() => { const f = document.querySelector('.co-card .c-sw'); return f && f.getClientRects().length ? f.value : null; })()")
        if sw is None:
            self.check()
            return
        v = str(self.rnd.randint(1, 9))
        if v == sw:
            v = str(int(v) % 9 + 1)
        self.pg.locator(".co-card .c-sw").first.fill(v)
        if not self.until("!document.querySelector('#save-rules').disabled", 3):
            self.problem("eine Änderung macht die Regeln nicht speicherbar")
            return
        self.note("Schwelle %s" % v)
        self.pg.keyboard.press("Meta+s")
        if not self.until("document.querySelector('#save-rules').disabled && !DIRTY.on", 20):
            self.problem("⌘S speichert die geänderten Regeln nicht")
            return
        if not self.until("v => (S.CFG.companies || [])[0] && String((S.CFG.companies || [])[0].threshold) === v", 10, v):
            self.problem("⌘S: die Schwelle ist nicht gespeichert")
        self.snaps.clear(); self.latest.clear()          # other rules: other bookings and proposals -- no page shows what it showed
        if self.ref:
            self.ref["stale"] = True                     # ... and what a reference points to may be gone
        if self.settle():
            self.check()


class _Kontor:
    """A Kontor of its own for a case's world, and the sign-in to it."""

    @classmethod
    def setUpClass(cls):
        TT._playwright()
        cls._today = (core.date, service.date, service.is_running)

    @classmethod
    def tearDownClass(cls):
        core.date, service.date, service.is_running = cls._today

    def world(self, c, d):
        """The case's world in a Kontor of its own: the store, the simulated MoneyMoney, its day."""
        T.MockBridge.instances, T.MockBridge.reads, T.MockBridge.extra_cats = [], [], []
        day = T.TODAY
        cfg = {"dry_run": True, "notifications": False, "schedule": {"interval_minutes": 30, "automatic": False},
               "updates": {"check_mode": "aus"}, "ui": {"lock_minutes": 15, "port": 0}}
        if c.kind in ("test", "demo"):
            T.reset_mock()
            cfg = T.config_for_test(os.path.join(d, "Belege"))
        elif c.kind == "random":
            w = TW.World(c.world_seed)
            raw, rows = w.export()
            T.MockBridge.state = {"accounts": raw, "txs": rows}
            T.MockBridge.extra_cats = categories_of(rows)
            cfg.update(w.settings())
            day = w.today
        else:
            T.MockBridge.state = {"accounts": [], "txs": []}
        cfg.setdefault("ui", {})["language"] = c.lang
        core.date = service.date = _date_class(day)
        service.is_running = lambda: True
        store = new_store(d)
        store.save("config.json", cfg)
        if c.all_new:
            store.save("state.json", dict(T.ALL_NEW))
        app = App(store, d, bridge_factory=T.MockBridge)
        app.price_reader = lambda req: {"ok": False, "error": "network"}         # "Kaufkraft": the price index is never fetched in a test
        app.do_run(False, True)
        if c.assistant:
            import test_assistant as TA
            TA.install(app)
        return app, store, day

    def sign_in(self, pg, base, c, errors=None):
        pg.goto(base)
        pg.wait_for_selector("#login-pw")
        pg.fill("#login-pw", PASSWORD)
        if pg.is_visible("#login-pw2"):
            pg.fill("#login-pw2", PASSWORD)
        pg.click("#login-btn")
        T.wait_shell(pg)
        if c.kind == "demo":
            self.demo_in(pg, errors)
        TT.settle(pg)

    def demo_in(self, pg, errors=None):
        """The demo: locked, the sign-in switched to it (the small link below), the same password. A request of the real
        Kontor still under way when it locks (the overview's open items, the status) comes back 401 -- its session ended on
        purpose: the browser's "Failed to load resource ... 401" in errors from the lock until the demo's page stands is no
        fault (night of 3.17.98: 11 demo cases on a slow runner). The demo's page standing proves its own session works."""
        n = len(errors) if errors is not None else 0
        pg.evaluate("lockNow()")
        pg.wait_for_selector("#demo-btn", state="visible")
        pg.click("#demo-btn"); pg.fill("#login-pw", PASSWORD); pg.click("#login-btn")
        T.wait_shell(pg)
        T.until(pg, "typeof demoOn === 'function' && demoOn() && DEMO_PAGE && !!S.KONTEN.length", 30)
        if errors is not None:
            errors[n:] = [e for e in errors[n:] if LOCKED_401 not in e]


class ClickPathTest(_Kontor, unittest.TestCase):
    """Random click paths: a few fixed ones per push, at night as many as fit (see the module's text)."""

    def run_case(self, browsers, seed):
        c = Case(seed, "webkit" in browsers)
        d = tempfile.mkdtemp(prefix="kontor-clicks-")
        app = srv = None
        walk = None
        try:
            app, store, day = self.world(c, d)
            srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = "http://127.0.0.1:%d/" % srv.server_address[1]
            dev = dict(TT.DEVICES[c.device])
            if c.device == "mac":
                dev["viewport"] = {"width": c.size[0], "height": c.size[1]}
            ctx = browsers[c.engine].new_context(color_scheme=c.theme, timezone_id="Europe/Berlin", **dev)
            ctx.add_init_script("try { localStorage.setItem('kontor.theme', %s); localStorage.setItem('kontor.lang', %s); } catch (e) {}" % (json.dumps(c.theme), json.dumps(c.lang)))
            try:
                if c.kind != "demo":          # the browser's clock on the world's day (the demo lives today)
                    ctx.clock.install(time=datetime.datetime(day.year, day.month, day.day, 10, 0))
                pg = ctx.new_page()
                pg.set_default_timeout(15000)
                walk = Walk(self, c, pg, store)
                self.sign_in(pg, base, c, walk.errors)
                walk.log.append("0. angemeldet")
                walk.check()
                walk.walk(c.steps)
            finally:
                ctx.close()
        finally:
            if srv:
                srv.shutdown(); srv.server_close()
            if app:
                try:
                    app.assistant_stop()
                except Exception:
                    pass
                app.stop.set()
            shutil.rmtree(d, ignore_errors=True)
        return c, walk

    def test_click_paths(self):
        from playwright.sync_api import sync_playwright
        total, cases, steps = {}, 0, 0
        with sync_playwright() as p:
            browsers = {"chromium": p.chromium.launch()}
            try:
                browsers["webkit"] = p.webkit.launch()
            except Exception:
                pass                       # Safari's engine not installed here: Chromium only
            try:
                for seed in F.fuzz_seeds("Klickpfade", "KONTOR_CLICK_SEEDS", 3, FOUND_CLICKS):
                    with self.subTest(seed=seed), F.case(seed):
                        c, walk = self.run_case(browsers, seed)
                        cases += 1; steps += walk.n
                        for k, v in walk.count.items():
                            total[k] = total.get(k, 0) + v
                        if os.environ.get("KONTOR_CLICK_LOG"):          # the way of a case that passed, too
                            print("\n%s\n  %s" % (c.describe(), "\n  ".join(walk.log)))
                        if walk.problems:
                            self.fail("seed %d – %s, nachzugehen mit KONTOR_FUZZ_SEED=%d python3 -m pytest -q tests/test_clickpaths.py\n  %s\nWeg:\n  %s"
                                      % (seed, c.describe(), seed, "\n  ".join(walk.problems), "\n  ".join(walk.log)))
            finally:
                for b in browsers.values():
                    b.close()
                summary = os.environ.get("GITHUB_STEP_SUMMARY")
                if summary and cases:          # what the walks did: a night that compares nothing would check little
                    with open(summary, "a", encoding="utf-8") as f:
                        f.write("- Klickpfade: %d Fälle, %d Schritte; %s\n" % (cases, steps, ", ".join("%s %d" % kv for kv in total.items())))


class FoundTest(_Kontor, unittest.TestCase):
    """What the click paths found, held fast: on the iPhone (and in a narrow window) Esc closes the menu, so does a tap on the
    page already open (no new page drawn); the menu lies above the assistant as a page (from there it could not be left); the
    demo never asks for the names of securities (it knows no lookup: its page asked anyway and was refused); a figure the same
    throughout has a scale, the overview's figures stay in their cards beside the assistant, the balance's first head fits its
    column on the iPhone."""

    def test_menu_and_demo(self):
        from playwright.sync_api import sync_playwright
        c = Case(0, False)
        c.kind, c.device, c.assistant, c.lang = "test", "iphone", True, "de"
        d = tempfile.mkdtemp(prefix="kontor-found-")
        app, store, day = self.world(c, d)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d/" % srv.server_address[1]
        side = "document.querySelector('.side').classList.contains('open')"
        slid = side + " && document.querySelector('.side').getBoundingClientRect().left >= 0"
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                pg = b.new_context(**TT.DEVICES["iphone"]).new_page()
                errors, asked = [], []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                pg.on("request", lambda r: asked.append(r.url))
                self.sign_in(pg, base, c)
                pg.tap("#menu-btn"); T.until(pg, slid)
                pg.keyboard.press("Escape"); T.until(pg, "!" + side)                          # Esc closes the menu
                pg.tap("#menu-btn"); T.until(pg, slid)
                pg.tap("#nav a[href='%s']" % pg.evaluate("location.hash || '#overview'")); T.until(pg, "!" + side)          # the page already open
                pg.tap("#menu-btn"); T.until(pg, slid); pg.tap("#nav a[href='#assistant']")
                T.until(pg, "document.body.classList.contains('as-page') && !(%s)" % side); TT.settle(pg)
                pg.tap("#menu-btn"); T.until(pg, slid)
                on_top = pg.evaluate("(() => { const r = document.querySelector('#nav a[href=\"#categories\"]').getBoundingClientRect(), e = document.elementFromPoint(r.left + 20, r.top + r.height / 2); return e.closest('.side') ? true : e.outerHTML.slice(0, 120); })()")
                self.assertIs(on_top, True)                                                    # the menu above the assistant
                pg.tap("#nav a[href='#categories']", timeout=5000)                            # above the assistant: reachable
                T.until(pg, "location.hash === '#categories' && !document.body.classList.contains('as-page')")
                self.demo_in(pg, errors)
                pg.evaluate("location.hash = '#accounts/history'"); pg.wait_for_selector("#mmh-names", state="attached"); T.quiet(pg)
                self.assertFalse([u for u in asked if "/api/securities/lookup" in u])
                self.assertEqual(errors, [])
                b.close()
        finally:
            srv.shutdown(); srv.server_close()
            app.assistant_stop(); app.stop.set()
            shutil.rmtree(d, ignore_errors=True)

    def test_narrow_heads_and_flat_figures(self):
        # what the night run by hand of 3.17.71 found: a figure the same throughout and not round (three months of 1.234,56 €) gave
        # no scale -- the overview drew its net worth as NaN; beside the assistant (1280 px) the overview's cards are 200 px and their
        # figures did not wrap; on the iPhone the balance's first head (▸, label, ?, ↑↓, the eye) was wider than its column
        from playwright.sync_api import sync_playwright
        c = Case(0, False)
        c.kind, c.world_seed, c.assistant, c.lang = "random", 825156183, True, "de"          # a world with hidden accounts: the eye shows
        d = tempfile.mkdtemp(prefix="kontor-found-")
        app, store, day = self.world(c, d)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d/" % srv.server_address[1]
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                ctx = b.new_context(**TT.DEVICES["iphone"]); ctx.clock.install(time=datetime.datetime(day.year, day.month, day.day, 10, 0))
                pg = ctx.new_page()
                self.sign_in(pg, base, c)
                for lo, hi in ((1234.56, 1234.56), (0.2, 0.2), (-98765.43, -98765.43), (0, 0), (5, 5)):
                    ticks = pg.evaluate("([a, b]) => niceTicks(a, b, 3, 3)", [lo, hi])
                    self.assertTrue(ticks and ticks[0] <= lo and ticks[-1] >= hi, (lo, ticks))
                pg.evaluate("location.hash = '#balance'"); pg.wait_for_selector(".bil-tbl .th-first #alle-zeilen", state="attached"); TT.settle(pg)
                head = pg.evaluate("""(() => { const f = document.querySelector('.bil-tbl .th-first'), g = f.parentElement.querySelector('.col-grip').getBoundingClientRect();
                  const over = [...f.querySelectorAll('button, label')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > g.left && r.left < g.right; });
                  return [f.scrollWidth - f.clientWidth, over.map(e => e.textContent)]; })()""")
                self.assertEqual(head, [0, []])
                ctx.close()
                ctx = b.new_context(viewport={"width": 1280, "height": 800}); ctx.clock.install(time=datetime.datetime(day.year, day.month, day.day, 10, 0))
                pg = ctx.new_page()
                self.sign_in(pg, base, c)
                pg.click("#assist-btn"); T.until(pg, "AS.open")
                pg.evaluate("location.hash = '#overview'"); pg.wait_for_selector("#ov-fig-months .ov-s", state="attached"); TT.settle(pg)
                wide = pg.evaluate("""[...document.querySelectorAll('.ov-card')].filter(c => { const r = c.getBoundingClientRect();
                  return [...c.querySelectorAll('.ov-fig *')].some(e => e.getBoundingClientRect().right > r.right + 0.5); }).map(c => c.dataset.ov)""")
                self.assertEqual(wide, [])
                b.close()
        finally:
            srv.shutdown(); srv.server_close()
            app.assistant_stop(); app.stop.set()
            shutil.rmtree(d, ignore_errors=True)

    def test_demo_after_requests_of_the_locked_session(self):
        # the night of 3.17.98 (11 demo cases, step 0): the way into the demo locks the real Kontor first; what the overview had
        # asked just before (open items, the assistant's status, the offline copy) came back 401 on a slow runner -- the session
        # ended on purpose, no fault. Held here until the lock, those requests always come back 401: demo_in drops just those;
        # the demo's page stands, nothing else is dropped (a script error stays a fault)
        from urllib.parse import urlsplit
        from playwright.sync_api import sync_playwright
        c = Case(0, False)
        c.kind, c.device, c.assistant, c.lang = "demo", "mac", False, "de"
        d = tempfile.mkdtemp(prefix="kontor-found-")
        app, store, day = self.world(c, d)
        locked, refused = threading.Event(), []
        base_handler = make_handler(app)

        class Held(base_handler):
            def do_GET(self):
                if urlsplit(self.path).path in ("/api/transactions", "/api/assistant/status", "/api/offline/verifier") and not locked.is_set():
                    if locked.wait(10) and self._session() is None:
                        refused.append(urlsplit(self.path).path)
                return super().do_GET()

            def do_POST(self):
                r = super().do_POST()
                if urlsplit(self.path).path == "/api/lock":
                    locked.set()
                return r

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Held)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d/" % srv.server_address[1]
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append("Skriptfehler: %s" % e))
                pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                self.sign_in(pg, base, c, errors)
                self.assertTrue(refused)                                      # the race happened ...
                self.assertTrue(pg.evaluate("demoOn() && DEMO_PAGE"))         # ... the demo stands ...
                self.assertEqual(errors, [])                                  # ... and its 401s are no fault
                pg.evaluate("setTimeout(() => { throw new Error('nach der Demo') }, 0)"); T.until(pg, "true")
                pg.wait_for_timeout(200)
                self.assertEqual(errors, ["Skriptfehler: nach der Demo"])      # what comes after still counts
                b.close()
        finally:
            srv.shutdown(); srv.server_close()
            app.stop.set()
            shutil.rmtree(d, ignore_errors=True)


class FoundAtNightTest(_Kontor, unittest.TestCase):
    """What the first whole night of click paths found (3.17.71, fixed 3.17.84; the side window: 3.17.82), held fast on the world that showed it: a page
    opened again stands where it was left -- also when its charts get their height only after the place is set, and when parts
    arrive later (the previews of the booking rules); a card of the overview still leads to its chart. A chart's range buttons
    say which range it shows, also when the range holds no value. A side window closed by a click beside it opens again at
    the next click on its figure, however soon (the click that closes it on its own figure still does not reopen it). A long
    title of the side window stands beside its ✕."""

    def test_places_ranges_and_the_side_window(self):
        from playwright.sync_api import sync_playwright
        c = Case(0, False)
        c.kind, c.world_seed, c.assistant, c.lang = "random", 269211242, False, "de"
        d = tempfile.mkdtemp(prefix="kontor-found-")
        app, store, day = self.world(c, d)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d/" % srv.server_address[1]
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                errors = []

                def go(h):
                    pg.evaluate("h => { location.hash = h; }", h)
                    T.until(pg, "location.hash === %s && SCROLL.key === S.tab + '/' + S.sub && !document.querySelector('#main .loading')" % json.dumps(h))
                    TT.settle(pg)
                # 1. the balance sheet on the iPhone, left further down: there again (its charts are drawn after the place is set
                #    and moved it by 29 px; on the Mac this world's charts did not)
                ctx = b.new_context(**TT.DEVICES["iphone"]); ctx.clock.install(time=datetime.datetime(day.year, day.month, day.day, 10, 0))
                pg = ctx.new_page()
                pg.on("pageerror", lambda e: errors.append(str(e)))
                self.sign_in(pg, base, c)
                for y in (300, 500):
                    go("#balance"); pg.evaluate("y => pageTo(y)", y)
                    self.assertEqual(pg.evaluate("pageY()"), y)
                    go("#transactions"); go("#balance")
                    self.assertAlmostEqual(pg.evaluate("pageY()"), y, delta=1)
                ctx.close()
                ctx = b.new_context(viewport={"width": 1440, "height": 900}); ctx.clock.install(time=datetime.datetime(day.year, day.month, day.day, 10, 0))
                pg = ctx.new_page()
                pg.on("pageerror", lambda e: errors.append(str(e)))
                self.sign_in(pg, base, c)
                go("#balance")
                pg.evaluate("pageTo(Math.min(60, pageScroller().scrollHeight - pageScroller().clientHeight))"); y = pg.evaluate("pageY()")
                self.assertGreater(y, 40)
                go("#transactions"); go("#balance")
                self.assertAlmostEqual(pg.evaluate("pageY()"), y, delta=1)
                # ... held there until the user scrolls himself; then it is his
                self.assertTrue(pg.evaluate("!!STAY.off"))
                pg.mouse.move(700, 500); pg.mouse.wheel(0, 120); T.until(pg, "!STAY.off")
                # 2. a month clicked: the three charts show it -- none of their range buttons stays marked, also not the
                #    position's, which has no value in that month (it drew nothing and left its button as it was)
                pg.evaluate("pageTo(0)")
                pg.locator("#main th", has_text="Jul 24").first.click(); TT.settle(pg)
                self.assertEqual(pg.evaluate("LC.pos.d.vals.slice(LC.pos.i0, LC.pos.i1 + 1).filter(v => v != null).length"), 0)          # (the case)
                self.assertEqual(pg.evaluate("['nw', 'sel', 'pos'].map(id => [S.lcRange[id].slice(0, 2).join('..'), document.querySelectorAll('.lc-rb[data-lc=\"' + id + '\"] button.on').length])"),
                                 [["2024-06..2024-07", 0]] * 3)
                self.assertEqual(pg.evaluate("document.querySelector('#lc-pos-span').textContent"), pg.evaluate("document.querySelector('#lc-nw-span').textContent"))
                # 3. the booking rules: their previews arrive after the page is drawn and make it longer -- left at its end, it
                #    stands there again
                go("#accounts/rules"); T.quiet(pg)
                pg.evaluate("pageTo(pageScroller().scrollHeight)"); y = pg.evaluate("pageY()")
                self.assertGreater(y, 100)
                go("#overview"); go("#accounts/rules"); T.quiet(pg); TT.settle(pg)
                self.assertAlmostEqual(pg.evaluate("pageY()"), y, delta=1)
                # 4. a card of the overview leads to its place (the balance sheet's table), wherever that page was left
                go("#balance"); pg.evaluate("pageTo(60)")
                go("#overview"); pg.evaluate("ovGo('table')")
                T.until(pg, "location.hash === '#balance' && SCROLL.key === 'balance/' && !!document.querySelector('.wrap.bil-tbl')"); pg.wait_for_timeout(400); TT.settle(pg)
                top, at, end = pg.evaluate("[document.querySelector('.wrap.bil-tbl').getBoundingClientRect().top, pageY(), pageScroller().scrollHeight - pageScroller().clientHeight]")
                self.assertTrue(at > 61 and (0 <= top < 200 or at >= end - 1), (top, at, end))          # at the table, or as near as the page goes
                self.assertFalse(pg.evaluate("!!STAY.off"))
                # ... so does the help while words are still searched: their first hit again; without: where it was left
                go("#help"); pg.fill("#help-q", "Tilgung"); T.until(pg, "!!document.querySelector('mark.hm.on')")
                pg.evaluate("pageTo(pageScroller().scrollHeight)")
                go("#overview"); go("#help"); T.until(pg, "!!document.querySelector('mark.hm.on')"); TT.settle(pg)
                self.assertTrue(pg.evaluate("(() => { const r = document.querySelector('mark.hm.on').getBoundingClientRect(); return r.top > 0 && r.bottom < innerHeight; })()"))
                pg.fill("#help-q", ""); T.until(pg, "!document.querySelector('mark.hm')")
                pg.evaluate("pageTo(2400)"); y = pg.evaluate("pageY()")
                self.assertGreater(y, 1000)
                go("#overview"); go("#help"); TT.settle(pg)
                self.assertAlmostEqual(pg.evaluate("pageY()"), y, delta=1)
                # 5. the side window: opened by a figure, closed by a click beside it, opened again by the next click on the figure
                #    at once (within 0.8 s nothing opened); a click on its own figure closes it and does not open it again
                go("#cashflow"); pg.evaluate("pageTo(0)")
                pg.evaluate("""() => { const c = [...document.querySelectorAll('#main table.cf-tbl td.tx')].find(el => el.getClientRects().length && getComputedStyle(el).cursor === 'pointer' && /\\d/.test(el.textContent)
                    && el.getBoundingClientRect().top > 120 && el.getBoundingClientRect().bottom < innerHeight - 20 && el.getBoundingClientRect().right < innerWidth - 440 && document.elementFromPoint(el.getBoundingClientRect().left + 8, el.getBoundingClientRect().top + 8) === el); c.dataset.fig = '1'; }""")
                fig, ready, shut = pg.locator("[data-fig='1']"), DRAWER_READY, "!document.querySelector('#drawer').classList.contains('open')"
                fig.click(); T.until(pg, ready)
                pg.locator("#page-title").click(position={"x": 4, "y": 4}); T.until(pg, shut)
                fig.click(); T.until(pg, ready, 4)
                fig.click(); T.until(pg, shut); pg.wait_for_timeout(400)
                self.assertTrue(pg.evaluate(shut))
                fig.click(); T.until(pg, ready, 4)                                                    # and again by the next click
                pg.locator("#page-title").click(position={"x": 4, "y": 4}); T.until(pg, shut)
                fig.focus() if pg.evaluate("document.querySelector('[data-fig]').tabIndex >= 0") else None
                # 6. its title, long: beside the ✕
                fig.click(); T.until(pg, ready, 4); TT.settle(pg)
                pg.evaluate("document.querySelector('#drawer h2').textContent = 'Einlagen & Entnahmen der Gesellschafter · Beispiel Vermögensverwaltung · Jan 25'")
                over = pg.evaluate("""(() => { const h = document.querySelector('#drawer h2'), x = document.querySelector('#drawer .close').getBoundingClientRect(), r = document.createRange(); r.selectNodeContents(h);
                    return [...r.getClientRects()].filter(q => q.right > x.left && q.left < x.right && q.bottom > x.top && q.top < x.bottom).length; })()""")
                self.assertEqual(over, 0)
                self.assertEqual(errors, [])
                b.close()
        finally:
            srv.shutdown(); srv.server_close()
            app.assistant_stop(); app.stop.set()
            shutil.rmtree(d, ignore_errors=True)

    def test_a_tap_shows_the_numbers_first_and_a_reference_to_a_row_that_is_gone_says_so(self):
        """Two things a night found (3.17.131). On the iPhone the first tap on a cell of the heat map shows its numbers, the second
        opens its side window -- each time anew, also right after that window was closed: the cell still had the focus then,
        so the first tap showed nothing (the walk took it for a side window that does not open again). And a reference of the
        assistant to a row the page no longer has (the booking rules were changed since): nothing is marked, Kontor says so --
        a row that is there is marked, without that note."""
        from playwright.sync_api import sync_playwright
        c = Case(0, False)
        c.kind, c.world_seed, c.assistant, c.lang = "random", 832507012, False, "de"
        d = tempfile.mkdtemp(prefix="kontor-found-")
        app, store, day = self.world(c, d)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d/" % srv.server_address[1]
        shut = "!document.querySelector('#drawer').classList.contains('open')"
        try:
            with sync_playwright() as p:
                engines = [p.chromium.launch()]
                try:
                    engines.append(p.webkit.launch())
                except Exception:
                    pass                       # Safari's engine not installed here: Chromium only
                for b in engines:
                    errors = []
                    ctx = b.new_context(**TT.DEVICES["iphone"]); ctx.clock.install(time=datetime.datetime(day.year, day.month, day.day, 10, 0))
                    pg = ctx.new_page()
                    pg.on("pageerror", lambda e: errors.append(str(e)))
                    self.sign_in(pg, base, c)
                    pg.evaluate("location.hash = '#cashflow'")
                    T.until(pg, "!!document.querySelector('#cf-heat .cf-heat-c.open')"); TT.settle(pg)
                    cell = pg.locator("#cf-heat .cf-heat-c.open").first
                    cell.scroll_into_view_if_needed(); TT.settle(pg)
                    for again in (False, True, True):
                        cell.tap(); T.until(pg, ARMED, 4)
                        pg.wait_for_timeout(300)          # (the finger's pointerout and the focus have come by now)
                        self.assertTrue(pg.evaluate(TIP_SHOWN), "%s: the first tap%s shows no numbers" % (b.browser_type.name, " after the side window was closed" if again else ""))
                        self.assertTrue(pg.evaluate(shut))
                        cell.tap(); T.until(pg, DRAWER_READY, 4)
                        self.assertFalse(pg.evaluate(TIP_SHOWN))
                        pg.keyboard.press("Escape"); T.until(pg, shut, 4); TT.settle(pg)
                    self.assertEqual(errors, [])
                    ctx.close()
                # the reference: a row of the bookings that is there, and one that is not (any more)
                ctx = engines[0].new_context(viewport={"width": 1440, "height": 900}); ctx.clock.install(time=datetime.datetime(day.year, day.month, day.day, 10, 0))
                pg = ctx.new_page(); errors = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                self.sign_in(pg, base, c)
                pg.evaluate("location.hash = '#bookings'")
                T.until(pg, "location.hash === '#bookings' && !document.querySelector('#main .loading') && !!document.querySelector('#main tbody td')"); TT.settle(pg)
                there = pg.evaluate("[...document.querySelectorAll('#main tbody tr td:first-child')].map(td => td.textContent.trim()).find(x => /^\\d\\d\\.\\d\\d\\.\\d{4}$/.test(x))")
                self.assertTrue(there)
                pg.evaluate("location.hash = '#overview'"); T.until(pg, "S.tab === 'overview' && !document.querySelector('#main .loading')")
                pg.evaluate("d => { asRefOpen({label: d, go: {route: '#bookings', mark: {text: d, column: 'Konto'}}}); }", there)
                T.until(pg, MARKED, 6)
                self.assertFalse(pg.evaluate(NOT_FOUND))
                pg.evaluate("location.hash = '#overview'"); T.until(pg, "S.tab === 'overview' && !document.querySelector('#main .loading')")
                pg.evaluate("asRefOpen({label: '31.12.1987', go: {route: '#bookings', mark: {text: '31.12.1987', column: 'Konto'}}})")
                T.until(pg, NOT_FOUND, 6)
                self.assertEqual(pg.evaluate("location.hash"), "#bookings")
                self.assertEqual(pg.evaluate("document.querySelectorAll('.as-mark').length"), 0)
                self.assertEqual(errors, [])
                ctx.close()
                for b in engines:
                    b.close()
        finally:
            srv.shutdown(); srv.server_close()
            app.assistant_stop(); app.stop.set()
            shutil.rmtree(d, ignore_errors=True)


class CheckerTest(unittest.TestCase):
    """The layout check finds what it looks for, on a page made of mistakes -- and lets pass what is meant so."""

    def test_finds_cut_covered_and_outside(self):
        sync_playwright = TT._playwright()
        page = """<html><body style="margin:0;font:14px sans-serif">
          <div style="width:80px;overflow:hidden;white-space:nowrap" id="cut">ein viel zu langer Text ohne Ende</div>
          <div style="width:80px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">ein langer Text mit Auslassung</div>
          <div style="width:80px;overflow:auto;white-space:nowrap">ein langer Text, der scrollt</div>
          <button style="width:40px;white-space:nowrap" id="spill">Speichern und prüfen</button>
          <button style="width:40px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">Speichern und prüfen</button>
          <button style="width:90px;display:inline-flex;white-space:nowrap"><b>Seite</b><span style="min-width:0;overflow:hidden;text-overflow:ellipsis">ein langer Bezug mit Auslassung</span></button>
          <button style="width:90px;display:inline-flex;white-space:nowrap"><b>Seite</b><span id="label" style="min-width:0;overflow:hidden">ein langer Bezug ohne Auslassung</span></button>
          <div style="position:relative;height:40px"><span style="position:absolute;left:0;top:0">Erster</span>
            <span id="cover" style="position:absolute;left:0;top:0;background:#fff">Zweiter</span></div>
          <div style="position:relative;height:40px"><span>Unter dem Durchsichtigen</span><div style="position:absolute;inset:0"></div></div>
          <div style="position:sticky;top:0;background:#eee">bleibt oben</div>
          <div id="ctx" style="position:fixed;left:-30px;top:10px;width:100px;height:20px;background:#ddd">Menü</div>
          <div style="max-height:0;overflow:hidden">eingeklappt</div></body></html>"""
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 800, "height": 600})
            pg.set_content(page)
            r = pg.evaluate(LAYOUT)
            b.close()
        # (a label inside a button that ends in "…" is meant so -- 3.17.84: the reference before the question was taken as cut)
        self.assertEqual(len(r["cut"]), 3, r["cut"])
        self.assertIn("div#cut", r["cut"][0]); self.assertIn("über den Rand: button#spill", r["cut"][1]); self.assertIn("span#label", r["cut"][2])
        self.assertEqual(len(r["over"]), 1, r["over"]); self.assertIn("span „Erster“ unter div › span#cover", r["over"][0])
        self.assertEqual(len(r["outside"]), 1, r["outside"]); self.assertIn("div#ctx", r["outside"][0])
        self.assertIsNone(r["wide"])

    def test_a_cell_beyond_its_scrolled_edge_is_not_free(self):
        """A table's cell scrolled sideways beyond its box's edge, its middle on the card around it: not free to click -- in view
        it lies under the names that stay (a night's click path took it for free, the tap was caught by the names: 3.17.95)."""
        sync_playwright = TT._playwright()
        page = """<html><body style="margin:0;font:14px sans-serif"><div id="main" style="padding:60px">
          <div id="w" style="width:300px;overflow-x:auto"><div style="display:flex;width:max-content">
            <span style="order:-1;flex:0 0 100px;position:sticky;left:0;z-index:3;background:#fff;margin-right:-100px;height:20px">Namen</span>
            <span id="ph" data-cp="1" style="flex:0 0 100px;height:20px"></span><span style="flex:0 0 900px;height:20px">Zahlen</span>
          </div></div></div></body></html>"""
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 800, "height": 600})
            pg.set_content(page)
            pg.evaluate("document.querySelector('#w').scrollLeft = 60")
            self.assertEqual(pg.evaluate("Math.round(document.querySelector('#ph').getBoundingClientRect().left)"), 0)
            free = pg.evaluate(FREE)
            b.close()
        self.assertEqual(free, "layer")

    def test_a_hairline_shape_has_no_point_to_tap(self):
        """A band thinner than a pixel beside a thick one (a small amount in the flow chart): no point to tap -- WebKit taps on
        whole pixels and hit the band beside it (a night's click path, 3.17.96); a thick band: a whole pixel inside it."""
        sync_playwright = TT._playwright()
        page = """<html><body style="margin:0"><svg width="300" height="200" style="margin:7.3px">
          <path id="big" d="M10,10L200,10L200,60.4L10,60.4Z" fill="#888"/>
          <g id="thin"><path d="M10,59.7L200,59.7L200,60.7L10,60.7Z" fill="#444"/></g>
          <g id="thick"><path d="M10,80.2L200,80.2L200,84.6L10,84.6Z" fill="#444"/></g></svg></body></html>"""
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 400, "height": 300})
            pg.set_content(page)
            pg.evaluate("document.querySelector('#thin').dataset.cp = '1'")
            thin = pg.evaluate(POINT)
            pg.evaluate("document.querySelector('#thin').removeAttribute('data-cp'); document.querySelector('#thick').dataset.cp = '1'")
            thick = pg.evaluate(POINT)
            at = pg.evaluate("p => { const r = document.querySelector('#thick').getBoundingClientRect(); return [r.left + p.x, r.top + p.y]; }", thick)
            b.close()
        self.assertIsNone(thin)
        self.assertIsNotNone(thick)
        self.assertTrue(all(abs(v - round(v)) < 1e-6 for v in at), at)

    def test_resize_observers_act_in_the_next_frame(self):
        """Every ResizeObserver of the page acts in the next frame (onResizeFrame, requestAnimationFrame): a size or style changed
        inside it while the browser still delivers sizes makes it report "ResizeObserver loop completed with undelivered
        notifications" as an error (the title bar's height set inside one -- a click path on the iPhone, 3.17.96)."""
        import re
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web", "app.js"), encoding="utf-8").read()
        found = [m.end() for m in re.finditer(r"new ResizeObserver\(", src)]
        self.assertGreaterEqual(len(found), 6)
        for at in found:
            head = src[at:at + 120]
            self.assertRegex(head, r"^(onResizeFrame\(|\(\) => (requestAnimationFrame\(|\{ if \(!raf\) raf = requestAnimationFrame\())",
                             "line %d: %s" % (src.count("\n", 0, at) + 1, head[:80]))

    def test_cases_go_round(self):
        """The fixed cases of a push see the test world on the Mac, a random world on the iPhone, the demo in WebKit; every
        number gives the same case again."""
        cs = [Case(s, True) for s in range(3)]
        self.assertEqual([(c.kind, c.device, c.engine) for c in cs], [("test", "mac", "chromium"), ("random", "iphone", "chromium"), ("demo", "mac", "webkit")])
        self.assertEqual(Case(123456789, True).describe(), Case(123456789, True).describe())
        self.assertIn("Fall 123456789", Case(123456789, True).describe())
        self.assertEqual(Case(5, False).engine, "chromium")          # without WebKit: Chromium


if __name__ == "__main__":
    unittest.main()
