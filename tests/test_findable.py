"""Findable: for every function the words the user would search for (tests/search_words.json) -- the help page's search and the
assistant's search_help find the right section of the help (docs/help.de.md). A search that misses: add the user's word to the
section (a word of everyday language beside the help's own), not a trick to the search."""
import json
import os
import re
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import assistant as A  # noqa: E402
import i18n  # noqa: E402
import memory  # noqa: E402

PAGE_TOP = 3                       # the help page: the right section among the first three it ranks (it jumps to the first)


def read(*p) -> str:
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def words() -> dict:
    return {k: v for k, v in json.loads(read("tests", "search_words.json")).items() if not k.startswith("_")}


def sections() -> dict:
    """Every anchor of the German help -> the section (## or ###) it lies in (an anchor at a list item: its section)."""
    out, cur = {}, None
    for line in read("docs", "help.de.md").splitlines():
        m = re.match(r'<a id="([\w-]+)"></a>\s*$', line)
        if m:
            cur = out[m.group(1)] = m.group(1)
            continue
        for x in re.findall(r'<a id="([\w-]+)"></a>', line):
            out[x] = cur
    return out


def assistant():
    a = A.Assistant.__new__(A.Assistant)
    a.app = types.SimpleNamespace(program_dir=ROOT)
    a._help, a._help_ix, a._help_fold, a._screen_cache = {}, None, None, ((None,), {})
    a._query_vec = lambda *x, **k: None                  # by words (the model for finding by meaning: not in a test)
    return a


class Words(unittest.TestCase):
    def test_every_section_has_words_and_every_word_a_section(self):
        secs, w = sections(), words()
        heads = {k for k, v in secs.items() if k == v}
        self.assertFalse(sorted(k for k in w if k not in secs), "search words for an anchor the help does not have")
        missing = sorted(h for h in heads if h not in w)
        self.assertEqual(missing, [], "sections of the help without the words you would search for (tests/search_words.json)")
        for k, qs in w.items():
            self.assertTrue(qs and all(isinstance(q, str) and q.strip() for q in qs), k)
        self.assertEqual(len(set(map(str.lower, (q for qs in w.values() for q in qs)))), sum(map(len, w.values())), "each search once")

    def test_the_page_folds_as_the_assistant(self):
        """The help page's search leaves out the same words and endings as search_help (one list in memory.py)."""
        js = read("web", "app.js")
        page = set(js[js.index("const HELP_STOP = new Set(`") + 27:js.index("`.split(/\\s+/));")].split())
        self.assertEqual(page, set(memory.STOP))
        src = read("assistant.py")
        # the endings taken off, and how many letters must stay
        ends = lambda text: (re.findall(r"['\"](\w+)['\"]", re.search(r"['\"]ern['\"][^\])]*", text).group(0)), re.search(r">= (\d)\)", text).group(1))  # noqa: E731
        self.assertEqual(ends(js[js.index("function helpWords"):]), ends(src[src.index("def _search_words"):]))


def jumps() -> dict:
    """Where the interface jumps into the help: "?" icons (HELP_AT), the "?" beside each page's title (PAGE_HELP), links
    (#help/<anchor>, more('<anchor>')) -> the anchors, each with where it was found."""
    js = read("web", "app.js") + read("web", "index.html")
    out = {}
    blocks = [js[js.index("const HELP_AT = {"):][:js[js.index("const HELP_AT = {"):].index("};")],
              js[js.index("Object.assign(HELP_AT, {"):][:js[js.index("Object.assign(HELP_AT, {"):].index("});")]]
    for b in blocks:
        for k, v in re.findall(r"(\w+): '([\w-]+)'", b):
            out.setdefault(v, "HELP_AT." + k)
    for k, v in re.findall(r"HELP_AT\.(\w+)(?: = HELP_AT\.\w+)* = '([\w-]+)'", js):
        out.setdefault(v, "HELP_AT." + k)
    pg = js[js.index("const PAGE_HELP = {"):]
    for k, v in re.findall(r"'?([\w/]+)'?: '([\w-]+)'", pg[:pg.index("};")]):
        out.setdefault(v, "PAGE_HELP." + k)
    for v in re.findall(r"#help/([\w-]+)", js) + re.findall(r"more\('([\w-]+)'\)", js):
        out.setdefault(v, "link")
    help_de, secs = read("docs", "help.de.md"), sections()
    for v, via in VIA_HELP.items():                      # only through a part that is itself reached, and that links to it
        for w in via:
            part = help_de[help_de.index('<a id="%s"></a>' % w):]
            part = part[:part.find("\n<a id=") % (len(part) + 1)]           # up to the next part's anchor
            if w in out and "](#%s)" % v in part and secs.get(w) == w:
                out.setdefault(v, "help #" + w)
    return out


# parts of the help without a "?" of their own, reached from the help of the pages they belong to: the tables' switches and
# Excel (user, 2026-11-28: the "?" beside "Monate / Jahre" added nothing)
VIA_HELP = {"tables": ("balance-sheet", "cash-flow")}


class Reachable(unittest.TestCase):
    def test_every_part_of_the_help_is_reached_from_its_place(self):
        """Every section of the help (and every anchor in it) is where some place of Kontor jumps -- a "?" or a link -- and every
        jump finds its anchor (in both languages: ReferenceTests)."""
        secs, j = sections(), jumps()
        self.assertEqual(sorted(a for a in secs if a not in j), [], "parts of the help no place of Kontor jumps to (a \"?\" or more('…'))")
        self.assertEqual(sorted("%s (%s)" % (a, w) for a, w in j.items() if a not in secs), [], "jumps to an anchor the help does not have")
        js = read("web", "app.js")
        h = js[js.index("const H = {"):js.index("const HELP_AT")]
        tips = set(re.findall(r"^\s*(\w+):", h, re.M)) | set(re.findall(r"[,{]\s*(\w+): t\(", h))
        extra = js[js.index("Object.assign(HELP_AT, {"):][:js[js.index("Object.assign(HELP_AT, {"):].index("});")]
        self.assertEqual(sorted(k for k in re.findall(r"(\w+): '", extra) if k not in tips), [], "a jump for a \"?\" without its text (H)")


class AssistantFinds(unittest.TestCase):
    """search_help: the section among what it hands over (HELP_FOUND)."""

    def setUp(self):
        self.lang = i18n.lang()
        i18n.set_lang("de")
        self.a = assistant()

    def tearDown(self):
        i18n.set_lang(self.lang)

    def find(self, q):
        return self.a.t_search_help({"query": q}, {})["found"]

    def test_every_search_finds_its_section(self):
        secs, miss = sections(), []
        for key, qs in words().items():
            for q in qs:
                got = [x.get("anchor") or "place:" + x["place"] for x in self.find(q)]
                if secs[key] not in got:
                    miss.append("%s (%s): %r -> %s" % (key, secs[key], q, got))
        self.assertEqual(miss, [], "search_help does not find:\n" + "\n".join(miss))

    def test_words_forms_and_kontor(self):
        self.assertEqual(A._search_words("Kontor einrichten, und wie?"), ["kontor", "einricht"])
        self.assertEqual(A._search_words("Kontostände KI ki Steuer Zurücksetzen 2026"), ["kontostaend", "ki", "steuer", "zuruecksetz", "2026"])
        self.assertEqual(A._search_words("geht nicht"), [])
        f = A._fold_text("Kontor liest das Konto; der KI-Assistent; Kinder; Kontors Daten")
        self.assertEqual(A._hits(f, "konto"), 1)                       # Kontor is no Konto ...
        self.assertEqual(A._hits(f, "kontor"), 2)                      # ... but is found as itself
        self.assertEqual(A._hits(f, "ki"), 1)                          # a short word only as a word of its own
        self.assertEqual(A._hits(A._fold_text("Einrichtung"), A._search_words("einrichten")[0]), 1)
        with self.assertRaises(A.ToolError):
            self.find("und wie")

    def test_places_leave_room_for_the_help(self):
        """What the pages show (docs/ui) is found too, but at most HELP_PLACES of HELP_FOUND -- the section on how it works stays."""
        for q in ("Eigenkapitalquote", "Nettovermögen", "Vorjahresvergleich Ausgaben", "Cashflow Tabelle"):
            got = self.find(q)
            self.assertLessEqual(len(got), A.HELP_FOUND)
            self.assertLessEqual(sum(1 for x in got if "place" in x), A.HELP_PLACES, q)
            self.assertTrue(any("anchor" in x for x in got), q)


class PageFinds(unittest.TestCase):
    """The help page in the browser: typing a search, the right section is among the first it ranks (HELP.hits), shown, and
    the first marked word lies in the best section."""

    def test_every_search_finds_its_section(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright fehlt")
        import test_tour as T
        T.PageTourTest.setUpClass()
        secs, miss = sections(), []
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                pg = b.new_page(**T.DEVICES["mac"])
                pg.goto(T.PageTourTest.base); pg.fill("#login-pw", T.PASSWORD)
                if pg.is_visible("#login-pw2"):
                    pg.fill("#login-pw2", T.PASSWORD)
                pg.click("#login-btn"); pg.wait_for_selector("#shell:not(.hidden)", timeout=30000)
                pg.evaluate("location.hash = '#help'"); pg.wait_for_selector("#help-q"); T.settle(pg)
                for key, qs in words().items():
                    for q in qs:
                        pg.fill("#help-q", q)
                        r = pg.evaluate("""() => { const on = document.querySelector('#help-body mark.hm.on');
                          return {hits: HELP.hits, first: on ? on.dataset.s : null,
                                  shown: [...document.querySelectorAll('#help-body h3[data-a], #help-body h4[data-a]')].filter(e => !e.classList.contains('hidden')).map(e => e.dataset.a)}; }""")
                        top = r["hits"][:PAGE_TOP]
                        if secs[key] not in top or secs[key] not in r["shown"] or r["first"] != r["hits"][0]:
                            miss.append("%s (%s): %r -> %s, first mark in %s" % (key, secs[key], q, top, r["first"]))
                # an empty search shows everything again
                pg.fill("#help-q", "")
                self.assertEqual(pg.evaluate("document.querySelectorAll('#help-body .hidden').length"), 0)
                b.close()
        finally:
            T.PageTourTest.tearDownClass()
        self.assertEqual(miss, [], "the help page does not find:\n" + "\n".join(miss))


# every word (up to a hyphen or slash, where a line may break) of the help's tables wider than the column it stands in
BROKEN_WORDS = r"""(() => {
  const out = [], m = document.createElement('span'); m.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap';
  document.body.appendChild(m);
  for (const c of document.querySelectorAll('#help-body table td, #help-body table th')) {
    if (!c.getClientRects().length) continue;
    const s = getComputedStyle(c), room = c.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight);
    m.style.font = s.font; m.style.letterSpacing = s.letterSpacing;
    for (const w of c.textContent.split(/\s+/).flatMap(x => x.split(/(?<=[-\/‑–])/)).filter(Boolean)) {
      m.textContent = w; const need = m.getBoundingClientRect().width;
      if (need > room + 1) out.push(w + ' (' + Math.round(need) + ' px in ' + Math.round(room) + ')');
    }
  }
  m.remove(); return out;
})()"""


class PageReads(unittest.TestCase):
    """The help on the iPhone: no column of its tables narrower than a word in it -- a long address in the text breaks anywhere,
    in a table it had squeezed the first column to a few letters, words broken letter by letter (3.17.96)."""

    def test_table_words_stay_whole_on_the_iphone(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright fehlt")
        import test_tour as T
        T.PageTourTest.setUpClass()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                pg = b.new_page(**T.DEVICES["iphone"])
                pg.goto(T.PageTourTest.base); pg.fill("#login-pw", T.PASSWORD)
                if pg.is_visible("#login-pw2"):
                    pg.fill("#login-pw2", T.PASSWORD)
                pg.click("#login-btn"); pg.wait_for_selector("#shell:not(.hidden)", timeout=30000)
                pg.evaluate("location.hash = '#help'"); pg.wait_for_selector("#help-q"); T.settle(pg)
                tables = pg.evaluate("document.querySelectorAll('#help-body table').length")
                broken = pg.evaluate(BROKEN_WORDS)
                b.close()
        finally:
            T.PageTourTest.tearDownClass()
        self.assertGreater(tables, 0)
        self.assertEqual(broken, [], "words broken in the help's tables on the iPhone:\n" + "\n".join(broken))


if __name__ == "__main__":
    unittest.main()
