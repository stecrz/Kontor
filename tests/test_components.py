"""Everything foreign Kontor uses is named for the user (components.py; Einstellungen -> Updates -> "Verwendete Programme"):
name, version, licence, where it comes from, shielded or not. A model the assistant's lists name comes with its licence, a
library that comes later with one entry -- nothing foreign without its name and licence. The list only reads; the page shows
it with links you open yourself."""
import ast
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import components as C     # noqa: E402
import llm_local as L      # noqa: E402
import pyruntime as R      # noqa: E402
from i18n import tr        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAC = {"running": {"version": "3.9.6", "own": False, "ended": "2025-10-31"}, "loaded": None}
OWN = {"running": {"version": R.VERSION, "own": True, "ended": ""}, "loaded": {"version": R.VERSION, "build": R.BUILD, "date": "2026-11-23 10:00"}}


class AI:
    """The assistant's lists of what is on this Mac, made up: llama.cpp, one model of each kind, one added by hand."""

    def __init__(self, runtime=True, models=True):
        self.rt = {"tag": "b9999", "version": "9999 (abc)", "installed": "2026-11-01 10:00"} if runtime else {}
        chat, speech, embed = L.CATALOG[-1], L.SPEECH[0], L.EMBED[0]
        self.have = {c["id"]: {"repo": c["repo"], "file": "%s-Q4_K_M.gguf" % c["id"], "size": 1, "name": c["name"]} for c in (chat, speech, embed)} if models else {}
        if models:
            self.have["own-1"] = {"repo": "jemand/Ein-Modell-GGUF", "file": "ein-modell.gguf", "size": 1, "name": "Ein Modell"}

    def runtime(self):
        return dict(self.rt)

    def models(self):
        return {k: dict(v) for k, v in self.have.items()}


class Named(unittest.TestCase):
    def test_every_model_the_lists_name_comes_with_its_licence(self):
        for c in L.CATALOG + L.SPEECH + L.EMBED:
            self.assertTrue(C.model_licence(c, c["repo"]), "the licence of %s (%s) is not named: as its page on Hugging Face names it, one line in "
                            "components.MODEL_LICENCES (or \"licence\" in its entry in llm_local) -- it is shown under Einstellungen -> Updates" % (c["name"], c["repo"]))
        for repo, lic in C.MODEL_LICENCES.items():
            self.assertRegex(repo, L.REPO_RE.pattern); self.assertRegex(lic, r"^[A-Za-z0-9][A-Za-z0-9 .+()-]{1,58}$")
        # named in the entry itself: that one counts; a model Kontor does not know: none is made up
        self.assertEqual(C.model_licence({"licence": "MIT"}, L.CATALOG[0]["repo"]), "MIT")
        self.assertEqual(C.model_licence(None, L.CATALOG[0]["repo"]), L.CATALOG[0]["licence"])      # another variant from the same repository, added by hand
        self.assertEqual(set(C.MODEL_LICENCES), {c["repo"] for c in L.SPEECH + L.EMBED if not c.get("licence")})     # one place each: no line here for an entry that names it itself
        self.assertEqual(C.model_licence(None, "jemand/Ein-Modell-GGUF"), "")

    def test_a_library_needs_one_entry(self):
        for lib in C.LIBRARIES:
            for key in ("id", "name", "version", "licence", "site", "path", "use"):
                self.assertTrue(str(lib.get(key) or ""), "%s of the library %r" % (key, lib.get("name")))
            self.assertIn(lib["site"], C.SITES); self.assertIs(lib.get("shielded"), True, "a library runs only in a shielded helper")
            self.assertNotEqual(tr(lib["use"]), lib["use"])
        self.assertEqual(C.loaded(ROOT), [])                                 # none yet
        # ... and is shown like everything else as soon as it is on this Mac
        keep = C.loaded
        C.loaded = lambda prog: [{"id": "x", "name": "Bibliothek X", "version": "1.2.3", "licence": "MIT", "site": "github", "path": "wer/x", "use": "vp_wofuer_bibliothek", "shielded": True}]
        try:
            got = C.listing(OWN)
        finally:
            C.loaded = keep
        self.assertEqual([(c["kind"], c["name"], c["version"], c["licence"], c["site"], c["path"], c["shielded"]) for c in got if c["kind"] == "library"],
                         [("library", "Bibliothek X", "1.2.3", "MIT", "github", "wer/x", "strict")])
        self.assertEqual([c["kind"] for c in got], ["python", "library", "system"])

    def test_the_python_kontor_runs_in(self):
        mac, own = C.python_item(MAC), C.python_item(OWN)
        self.assertEqual((mac["name"], mac["version"], mac["licence"], mac["site"], mac["path"], mac["shielded"], mac["use"]),
                         ("Python", "3.9.6", "PSF 2.0", "apple", "", "no", "vp_wofuer_python_mac"))
        self.assertEqual((own["name"], own["version"], own["licence"], own["site"], own["shielded"], own["use"]), ("Python", R.VERSION, "PSF 2.0", "github", "no", "vp_wofuer_python"))
        self.assertEqual(own["path"], "astral-sh/python-build-standalone/releases/tag/%s" % R.BUILD)       # the very release its file came from
        self.assertIs(own["holds"], True); self.assertNotIn("holds", mac)        # other free software inside it: the page says so

    def test_the_assistants_programs_and_models(self):
        got = C.listing(MAC, AI(), "strict")
        self.assertEqual([c["kind"] for c in got], ["python", "runtime", "model", "model", "model", "model", "system"])
        rt = got[1]
        self.assertEqual((rt["name"], rt["version"], rt["licence"], rt["site"], rt["path"], rt["shielded"]), ("llama.cpp", "b9999", "MIT", "github", "ggml-org/llama.cpp", "strict"))
        models = {c["name"]: c for c in got if c["kind"] == "model"}
        self.assertEqual(sorted(models, key=str.lower), [c["name"] for c in got if c["kind"] == "model"])          # by name
        chat, speech, embed = models[L.CATALOG[-1]["name"]], models[L.SPEECH[0]["name"]], models[L.EMBED[0]["name"]]
        self.assertEqual((chat["use"], speech["use"], embed["use"]), ("vp_wofuer_modell", "vp_wofuer_diktat", "vp_wofuer_bedeutung"))
        self.assertEqual((chat["site"], chat["path"], chat["version"]), ("huggingface", L.CATALOG[-1]["repo"], "%s-Q4_K_M.gguf" % L.CATALOG[-1]["id"]))
        self.assertTrue(chat["licence"] and speech["licence"] and embed["licence"])
        mine = models["Ein Modell"]                                          # added by its repository: named, its licence not made up
        self.assertEqual((mine["licence"], mine["site"], mine["path"], mine["use"]), ("", "huggingface", "jemand/Ein-Modell-GGUF", "vp_wofuer_modell"))
        # shielded as the assistant is set -- said as it is, also when the sandbox is off
        for level in ("strict", "basic", "off"):
            self.assertEqual({c["shielded"] for c in C.listing(MAC, AI(), level) if c["kind"] in ("runtime", "model")}, {level})
        self.assertEqual({c["shielded"] for c in C.listing(MAC, AI(), "anything") if c["kind"] in ("runtime", "model")}, {"strict"})
        self.assertEqual({c["shielded"] for c in got if c["kind"] in ("python", "system")}, {"no"})
        # nothing of the assistant on this Mac, or no assistant at all: the rest
        self.assertEqual([c["kind"] for c in C.listing(MAC, AI(runtime=False, models=False))], ["python", "system"])
        self.assertEqual([c["kind"] for c in C.listing(OWN)], ["python", "system"])

    def test_every_word_of_the_page_is_there(self):
        keys = {c["use"] for c in C.listing(OWN, AI(), "strict")} | {"vp_wofuer_python_mac", "vp_wofuer_bibliothek", "vp_titel", "h_programme", "vp_lizenz", "vp_lizenz_unbekannt",
                                                                    "vp_teil_von_macos", "vp_enthaelt", "vp_abgeschirmt", "vp_abgeschirmt_basic", "vp_nicht_abgeschirmt"}
        for k in keys:
            self.assertNotEqual(tr(k), k, k)
        with open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8") as f:
            js = f.read()
        for site in C.SITES:                                                 # every place a part can come from has its fixed address on the page
            self.assertIn("%s: [" % site, js.split("const VP_SITES = ")[1].split("\n")[0], site)

    def test_it_only_reads(self):
        with open(os.path.join(ROOT, "components.py"), encoding="utf-8") as f:
            t = ast.parse(f.read())
        mods = {a.name for n in ast.walk(t) if isinstance(n, ast.Import) for a in n.names} | {n.module for n in ast.walk(t) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(mods, {"__future__", "platform", "sys", "typing", "llm_local", "pyruntime"})
        calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "") for n in ast.walk(t) if isinstance(n, ast.Call)}
        self.assertEqual(calls & {"open", "run", "Popen", "urlopen", "system", "connect", "write", "remove", "_open", "install", "fetch"}, set())


class InService(unittest.TestCase):
    def setUp(self):
        from test_e2e import _AppBase
        self.t = _AppBase("setUp"); self.t.setUp()
        self.addCleanup(self.t.tearDown)
        self.app, self.call = self.t.app, self.t.call

    def test_with_the_updates_page_after_the_sign_in_never_for_the_demo(self):
        import service as MA
        self.assertEqual(self.call("/api/update/status")[0], 401)
        self.t.login()
        code, r = self.call("/api/update/status")
        self.assertEqual(code, 200)
        got = r["components"]
        self.assertEqual((got[0]["kind"], got[0]["name"], got[0]["version"], got[-1]["kind"]), ("python", "Python", "%d.%d.%d" % sys.version_info[:3], "system"))
        for c in got:
            self.assertEqual(set(c) - {"holds", "build", "ended"}, {"kind", "name", "version", "licence", "site", "path", "shielded", "use"})
        self.assertFalse(MA.demo_allowed("GET", "/api/update/status"))       # nothing about this Mac's programs in the demo
        # the assistant's own lists, as they are on this Mac -- and whatever is wrong with them, the page still gets the rest
        ai = AI()
        keep = type(self.app).assistant
        try:
            type(self.app).assistant = property(lambda app: type("A", (), {"ai": ai, "settings": lambda self: {"sandbox": "basic"}})())
            got = self.call("/api/update/status")[1]["components"]
            self.assertEqual([c["kind"] for c in got], ["python", "runtime", "model", "model", "model", "model", "system"])
            self.assertEqual({c["shielded"] for c in got if c["kind"] == "model"}, {"basic"})
            type(self.app).assistant = property(lambda app: (_ for _ in ()).throw(RuntimeError("no assistant")))
            self.assertEqual([c["kind"] for c in self.call("/api/update/status")[1]["components"]], ["python", "system"])
        finally:
            type(self.app).assistant = keep


class Page(unittest.TestCase):
    """Einstellungen -> Updates in the browser: the list, each row with what it is for, its licence, its link and whether it is
    shielded -- on the Mac and on the iPhone, nothing running out of the window."""

    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        from test_tour import PASSWORD as PW, _playwright, settle
        from test_e2e import MockBridge, config_for_test, patch_today, reset_mock
        from service import App, make_handler
        from fixtures import new_store
        cls.sync_playwright, cls.settle, cls.password = staticmethod(_playwright()), staticmethod(settle), PW
        cls.dir = tempfile.mkdtemp(prefix="kontor-vp-ui-")
        store = new_store(cls.dir); store.save("config.json", config_for_test(os.path.join(cls.dir, "Belege")))
        reset_mock(); patch_today()
        cls.app = App(store, cls.dir, bridge_factory=MockBridge)
        cls.app.program_dir = os.path.realpath(tempfile.mkdtemp(prefix="kontor-vp-prog-"))
        cls.app.components = lambda: C.listing(OWN, AI(), cls.level)
        cls.level = "strict"
        cls.app.do_run(False, True)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d/" % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        shutil.rmtree(cls.dir, ignore_errors=True); shutil.rmtree(cls.app.program_dir, ignore_errors=True)

    def test_the_list_on_the_updates_page(self):
        rows = "[...document.querySelectorAll('#vp-box .vp-item')].map(r => r.innerText.replace(/\\s+/g, ' ').trim())"
        links = "[...document.querySelectorAll('#vp-box a')].map(a => [a.getAttribute('href'), a.target, a.rel])"
        with self.sync_playwright() as p:
            b = p.chromium.launch()
            for device in ({"viewport": {"width": 1440, "height": 900}}, {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}):
                type(self).level = "strict"
                pg = b.new_context(**device).new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.goto(self.base); pg.fill("#login-pw", self.password)
                if pg.is_visible("#login-pw2"):
                    pg.fill("#login-pw2", self.password)
                pg.click("#login-btn"); pg.wait_for_selector("#shell:not(.hidden)", timeout=30000); self.settle(pg)
                pg.evaluate("location.hash = '#settings/updates'"); pg.wait_for_selector("#vp-box", timeout=15000)
                self.assertEqual(pg.inner_text("#vp-box h2").replace("?", "").strip(), "Verwendete Programme")
                got = pg.evaluate(rows)
                self.assertEqual(len(got), 7)
                self.assertTrue(got[0].startswith("Python %s Darin läuft Kontor · Lizenz PSF 2.0 · GitHub: astral-sh/python-build-standalone" % R.VERSION), got[0])
                self.assertIn("Enthält unter anderem OpenSSL (Apache 2.0) und SQLite (gemeinfrei)", got[0]); self.assertTrue(got[0].endswith("nicht abgeschirmt"), got[0])
                self.assertEqual(got[1], "llama.cpp b9999 Führt die Modelle des Assistenten aus · Lizenz MIT · GitHub: ggml-org/llama.cpp abgeschirmt")
                mine = next(r for r in got if r.startswith("Ein Modell"))
                self.assertEqual(mine, "Ein Modell Sprachmodell des Assistenten · ein-modell.gguf · Lizenz: siehe Herkunft · Hugging Face: jemand/Ein-Modell-GGUF abgeschirmt")
                self.assertTrue(any("Modell zum Diktieren" in r and "Lizenz Apache 2.0" in r for r in got)); self.assertTrue(any("Suche nach Bedeutung" in r for r in got))
                self.assertTrue(got[-1].startswith("macOS") and "Teil von macOS (Apple)" in got[-1] and "Lizenz" not in got[-1], got[-1])
                hrefs = pg.evaluate(links)
                self.assertEqual(hrefs[0], ["https://github.com/astral-sh/python-build-standalone/releases/tag/%s" % R.BUILD, "_blank", "noopener"])
                self.assertIn(["https://github.com/ggml-org/llama.cpp", "_blank", "noopener"], hrefs)
                self.assertIn(["https://huggingface.co/jemand/Ein-Modell-GGUF", "_blank", "noopener"], hrefs)
                self.assertEqual({h[0].split("/")[2] for h in hrefs}, {"github.com", "huggingface.co"})            # nowhere else
                box = pg.evaluate("(() => { const b = document.querySelector('#vp-box').getBoundingClientRect(); return [b.right, innerWidth, document.documentElement.scrollWidth]; })()")
                self.assertLessEqual(box[0], box[1] + 1); self.assertLessEqual(box[2], box[1] + 1)                # nothing runs out of the window
                self.assertTrue(pg.evaluate("!!document.querySelector('#vp-box h2 .hq[data-help=\"components\"]')"))
                # the weaker level and no sandbox at all are said as they are
                for level, word, cls in (("basic", "abgeschirmt (einfach)", "ok"), ("off", "nicht abgeschirmt", "warn")):
                    type(self).level = level
                    pg.reload(); pg.wait_for_selector("#vp-box", timeout=15000)
                    self.assertEqual(pg.evaluate("[...document.querySelectorAll('#vp-box .vp-item')][1].querySelector('.pill').innerText + '|' + "
                                                 "[...document.querySelectorAll('#vp-box .vp-item')][1].querySelector('.pill').className"), "%s|pill %s" % (word, cls))
                self.assertEqual(errors, [])
                pg.context.close()
            b.close()


if __name__ == "__main__":
    unittest.main()
