"""Kontor's pages in macOS's own WebKit -- the engine of Kontor's Mac app, where the user mostly works -- on GitHub's Mac
(tests/mac_webview.swift drives it like a person). What Playwright's WebKit on Linux does not do the way the Mac does:

  * a right click selects the word under the pointer (Safari, the Mac app) -- the assistant's reference must still be the cell
    or figure with its row, column and what the place shows, never just that word (3.17.2: "„505,24“" without its place);
  * every main page opens in it without a script error.

Runs only on a Mac with swiftc (the macOS job); skipped elsewhere. All data made up (tests/fixtures.py)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

ON_MAC = sys.platform == "darwin" and shutil.which("swiftc") is not None
HERE = os.path.dirname(os.path.abspath(__file__))


@unittest.skipUnless(ON_MAC, "macOS's WebKit only on a Mac")
class OnMac(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_e2e as T
        from service import App, make_handler
        cls.dir = tempfile.mkdtemp(prefix="kontor-webkit-")
        store = T.new_store(cls.dir)
        store.save("config.json", T.config_for_test(os.path.join(cls.dir, "Belege")))
        store.save("state.json", dict(T.ALL_NEW))
        T.reset_mock()
        T.patch_today()
        cls.app = App(store, cls.dir, bridge_factory=T.MockBridge)
        cls.app.do_run(False, True)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:%d/" % cls.srv.server_address[1]
        cls.bin = os.path.join(cls.dir, "mac_webview")
        subprocess.run(["swiftc", "-O", "-o", cls.bin, os.path.join(HERE, "mac_webview.swift")], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def drive(self, steps):
        path = os.path.join(self.dir, "steps.json")
        with open(path, "w") as f:
            json.dump(steps, f)
        r = subprocess.run([self.bin, self.url, path], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        return json.loads(r.stdout)["steps"]

    # signed in once the page knows its state (SESSION): sets the password on the first start, else signs in with it -- with
    # the password even where Touch ID is on (LOGIN.pw), never turning Touch ID on. Answers true, or what the page shows.
    SIGN_IN = [{"js": "window.__errors = []; window.addEventListener('error', e => window.__errors.push(String(e.message))); "
                      "window.addEventListener('unhandledrejection', e => window.__errors.push(String(e.reason))); "
                      "const ready = () => typeof SESSION !== 'undefined' && SESSION && !document.querySelector('#login').classList.contains('hidden'); "
                      "for (let i = 0; i < 300 && !ready(); i++) await new Promise(r => setTimeout(r, 100)); "
                      "if (!ready()) return ['no login page', document.body.innerText.slice(0, 300)]; "
                      "const setup = !!SESSION.setup_needed; if (!setup && SESSION.touchid) { LOGIN.pw = true; showLogin(); } "
                      "const cb = document.querySelector('#setup-tid-cb'); if (cb) cb.checked = false; "
                      "document.querySelector('#login-pw').value = 'sehr-geheimes-passwort'; "
                      "if (setup) document.querySelector('#login-pw2').value = 'sehr-geheimes-passwort'; "
                      "document.querySelector('#login-btn').click(); "
                      "for (let i = 0; i < 300 && document.querySelector('#shell').classList.contains('hidden'); i++) await new Promise(r => setTimeout(r, 100)); "
                      "return !document.querySelector('#shell').classList.contains('hidden') "
                      "|| ['not signed in', setup, document.querySelector('#login-err').textContent, window.__errors.slice()];"}]

    def test_pages_open_without_script_errors(self):
        steps = list(self.SIGN_IN)
        for page in ("overview", "balance", "cashflow", "planning", "properties", "tax", "transactions", "bookings", "categories", "accounts", "settings", "help"):
            steps.append({"js": "location.hash = '#%s'; " % page
                          + "for (let i = 0; i < 150 && (!document.querySelector('#main').childElementCount || document.querySelector('#main .loading')); i++) await new Promise(r => setTimeout(r, 100)); "
                          + "await new Promise(r => setTimeout(r, 400)); return [location.hash, window.__errors.slice()];"})
        out = self.drive(steps)
        self.assertIs(out[0], True, out)
        for hash_, errors in out[1:]:
            self.assertEqual(errors, [], hash_)

    def test_a_right_click_keeps_the_place_not_the_word_webkit_selects(self):
        """A real right click (the mouse's event, through the window) on a figure of the cash flow table: WebKit selects the word
        under the pointer -- the reference is still the cell, with its row and column, and the word is not left selected."""
        hook = ("const o = window.refAt; window.refAt = e => (window.__ref = o(e)); "          # what the right click hands the assistant
                "const n = document.querySelector('#main .cf-pair table.cf-names'), v = document.querySelector('#main .cf-pair table.cf-tbl:not(.cf-names)'); "
                "const tr = [...n.tBodies[0].rows].find(r => r.getClientRects().length && +r.dataset.depth > 0 && refLabel(r.cells[0]) && refVal(v.rows[r.rowIndex].cells[1])); "
                "const c = v.rows[tr.rowIndex].cells[1]; c.id = 'ref-cell'; return [refLabel(tr.cells[0]), refVal(c)];")
        out = self.drive(list(self.SIGN_IN) + [
            {"js": "location.hash = '#cashflow'; for (let i = 0; i < 150 && !document.querySelector('#main .cf-pair table.cf-names'); i++) await new Promise(r => setTimeout(r, 100)); "
                   "await new Promise(r => setTimeout(r, 600)); return true;"},
            {"js": hook},
            {"right": "#ref-cell"},
            {"js": "const r = window.__ref || {}; return [r.label || '', r.text || '', r.ex || [], getSelection().toString(), !!document.querySelector('#ctx')];"},
        ])
        self.assertIs(out[0], True, out)
        self.assertIsInstance(out[2], list, out)
        row, val = out[2]
        label, text, ex, selected, menu = out[4]
        self.assertTrue(menu, out)                                  # Kontor's own menu, not the system's
        self.assertFalse(label.startswith("„"), label)             # not "the selected text"
        self.assertIn(row, label); self.assertIn(val, label)
        self.assertIn("Spalte: ", text); self.assertIn("Zeile: %s" % row, text)
        self.assertTrue(ex and ex[-1] == "cashflow", ex)
        self.assertEqual(selected, "")                              # the word the click selected: not left marked


if __name__ == "__main__":
    unittest.main()
