"""Kontor's description of its pages for the assistant (docs/ui/<page>.md): every place a page marks with data-ex="<key>" is
described, every description belongs to a place, each file to a page. What a place shows is given to the assistant with a right
click on it (the quick explanation, "ask in the chat") and found by search_help -- so a new or changed card, chart, table or
figure comes with its description (CLAUDE.md, "Was wo gepflegt wird"). Whether every visible table, chart and card of a page
lies in a described place: test_tour."""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
import assistant as A  # noqa: E402

FOLDER = os.path.join(ROOT, *A.SCREEN_DIR)
# every page of the menu, the side panels (drawer) and the assistant's own panel
FILES = {"kontor", "overview", "balance", "cashflow", "planning", "properties", "tax", "transactions", "bookings", "categories", "accounts",
         "setup", "settings", "help", "log", "assistant", "drawer"}


def app_js() -> str:
    with open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8") as f:
        return f.read()


def used_keys(js: str) -> set:
    """The places the page marks: data-ex="..." (always written out, never put together), and those named in code (ex: [...])."""
    keys = set(re.findall(r'data-ex="([^"]*)"', js))
    for lst in re.findall(r"\bex: \[([^\]]*)\]", js):
        keys |= set(re.findall(r"'([a-z][a-z0-9.-]*)'", lst))
    return keys


class UiDocsTests(unittest.TestCase):
    def setUp(self):
        self.notes = A.screen_notes(FOLDER)
        self.js = app_js()

    def test_every_file_is_a_page_and_every_key_its_place(self):
        names = {n[:-3] for n in os.listdir(FOLDER) if n.endswith(".md")}
        self.assertEqual(names, FILES, "docs/ui: one file per page (and kontor.md, drawer.md, assistant.md)")
        for key, n in self.notes.items():
            self.assertEqual(key.split(".")[0], n["file"][:-3], "%s stands in %s" % (key, n["file"]))
        for f in FILES:
            self.assertIn(f, self.notes, "docs/ui/%s.md: its first heading is '# %s — <name>'" % (f, f))
        for name in sorted(names):
            with open(os.path.join(FOLDER, name + ".md"), encoding="utf-8") as fh:
                for line in fh:
                    if re.match(r"#{1,3}\s", line):
                        self.assertTrue(A.SCREEN_HEAD.match(line) and A.SCREEN_KEY.fullmatch(A.SCREEN_HEAD.match(line).group(2)),
                                        "docs/ui/%s.md: heading not '## key — Name': %r" % (name, line.strip()))
                    self.assertFalse(re.match(r"#{4,}\s", line), "docs/ui/%s.md: only #, ## and ### start a place" % name)

    def test_every_marked_place_is_described_and_every_description_used(self):
        self.assertNotIn('data-ex="${', self.js, "keys always written out (the test finds them)")
        used = used_keys(self.js)
        bad = sorted(k for k in used if not A.SCREEN_KEY.fullmatch(k))
        self.assertEqual(bad, [], "keys: lower case, page first, parts joined by dots")
        missing = sorted(k for k in used if k not in self.notes)
        self.assertEqual(missing, [], "places marked in web/app.js without a description in docs/ui")
        unused = sorted(k for k in self.notes if "." in k and k not in used)
        self.assertEqual(unused, [], "descriptions in docs/ui of places no page marks (data-ex)")

    def test_descriptions_are_there_and_short(self):
        for key, n in self.notes.items():
            self.assertTrue(n["name"].strip(), key)
            self.assertGreaterEqual(len(n["text"]), 40 if "." in key or key == A.SCREEN_ROOT else 20, "%s: too short" % key)
            self.assertLessEqual(len(n["text"]), 5000 if key == A.SCREEN_ROOT else 2600, "%s: too long for the assistant -- split the place" % key)
            self.assertNotRegex(n["text"], r"TODO|FIXME|\?\?\?", key)

    def test_the_assistant_is_given_what_a_place_shows(self):
        """A right click on a place: the place and the places around it, from the page down, each once -- the innermost first
        when room is short; unknown keys are left out."""
        a = A.Assistant.__new__(A.Assistant)
        a._screen = lambda: {"kontor": {"name": "Kontor", "text": "root"}, "cashflow": {"name": "Cashflow", "text": "The page of the cash flow, month by month. Second sentence, long and only for when it is clicked."},
                             "cashflow.ring": {"name": "Ring", "text": "Amount: this period. Percentage: change against a year before."}}
        got = a._screen_text(["cashflow.ring", "cashflow", "nonsense.place"])
        # the place clicked in full, the places around it by their first sentence (what they are) -- few words for the model
        self.assertEqual(got, "## Cashflow (cashflow)\nThe page of the cash flow, month by month.\n## Ring (cashflow.ring)\nAmount: this period. Percentage: change against a year before.")
        text = A._ref_text([{"label": "Wohnen: 17.400 ±0 %", "text": "Zeile: Wohnen", "ex": ["cashflow.ring", "cashflow"]}], a._screen_text)
        self.assertIn("what these places on the page show", text); self.assertIn("change against a year before", text)
        self.assertNotIn("root", text)                                    # Kontor as a whole: in the system text, not again here
        refs = A._refs([{"label": "x", "text": "y", "ex": ["cashflow.ring", "../etc", "A.B", 7, "a" * 200]}])
        self.assertEqual(refs[0]["ex"], ["cashflow.ring"])
        self.assertEqual(A._ref_text([{"label": "x", "text": "y"}], a._screen_text).count("[Kontor"), 0)


if __name__ == "__main__":
    unittest.main()
