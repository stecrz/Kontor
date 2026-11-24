"""The workflow files GitHub runs: a key twice in one mapping (3.17.21: two `env:` in one step) and GitHub does not start the
run at all -- no tests for any push until it is fixed. Python's own YAML readers let the last one win, so this checks with the
standard library alone: per mapping (a list item starts a new one), each key once; text of block scalars (`run: |`) is skipped.
Also a plain (unquoted) value with ": " in it (3.17.64: `- name: Browsers (the click paths: Chromium …)`) -- YAML reads a second
key there, GitHub rejects the file and the nightly run never starts."""
import glob
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = re.compile(r'^( *)(- +)?([A-Za-z_][\w.-]*|"[^"]*"|\'[^\']*\'):(?=\s|$)')


def duplicate_keys(text, colons=None):
    """(line, key) for every key that a mapping already has; colons: a list that gets (line, key) of every plain value with
    ": " in it (or ending in ":")."""
    found, stack, block = [], [], None
    for no, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        ind = len(line) - len(line.lstrip(" "))
        if block is not None:
            if ind > block:
                continue
            block = None
        m = KEY.match(line)
        if not m:
            continue
        col, dash, key = m.start(3), bool(m.group(2)), m.group(3)
        while stack and (stack[-1][0] > col or (dash and stack[-1][0] == col)):
            stack.pop()
        if stack and stack[-1][0] == col:
            if key in stack[-1][1]:
                found.append((no, key))
            stack[-1][1].add(key)
        else:
            stack.append((col, {key}))
        rest = line[m.end():].split(" #")[0].strip()
        if rest[:1] in ("|", ">"):
            block = col
        elif colons is not None and rest and rest[0] not in "\"'{[&*!" and (": " in rest or rest.endswith(":")):
            colons.append((no, key))
    return found


class Workflows(unittest.TestCase):
    def test_no_key_twice(self):
        files = sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml")))
        self.assertTrue(files)
        for f in files:
            with open(f, encoding="utf-8") as fh:
                self.assertEqual(duplicate_keys(fh.read()), [], os.path.basename(f))

    def test_no_colon_in_a_plain_value(self):
        for f in sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml"))):
            got = []
            with open(f, encoding="utf-8") as fh:
                duplicate_keys(fh.read(), got)
            self.assertEqual(got, [], os.path.basename(f) + ": quote the value")

    def test_finds_a_colon_in_a_plain_value(self):
        got = []
        duplicate_keys("steps:\n  - name: Browsers (the click paths: Chromium)\n    if: matrix.browsers\n"
                       "  - name: \"Quoted: fine\"\n    run: |\n      echo a: b\n    env:\n      URL: https://x.org  # c: d\n"
                       "      M: {a: 1}\n", got)
        self.assertEqual(got, [(2, "name")])

    def test_finds_what_stopped_github(self):
        bad = ("jobs:\n  t:\n    steps:\n      - name: Tests\n        env:\n          TZ: Europe/Berlin\n"
               "        run: |\n          env: not a key\n          echo x\n        env:\n          A: '1'\n"
               "      - name: Next\n        env:\n          TZ: x\n")
        self.assertEqual(duplicate_keys(bad), [(10, "env")])
        ok = "a:\n  - b: 1\n    c: 2\n  - b: 3\n    c: 4\nd: |\n  d: inside\n  d: inside\ne: 5\n"
        self.assertEqual(duplicate_keys(ok), [])

    def test_the_broken_file_of_3_17_21(self):
        try:
            text = subprocess.run(["git", "show", "8464dfc:.github/workflows/tests.yml"], cwd=ROOT, capture_output=True,
                                  text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            self.skipTest("no git")
        if text.returncode:
            self.skipTest("commit not in this clone")
        self.assertEqual([k for _, k in duplicate_keys(text.stdout)], ["env"])


if __name__ == "__main__":
    unittest.main()
