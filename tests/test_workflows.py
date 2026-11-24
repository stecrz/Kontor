"""The workflow files GitHub runs: a key twice in one mapping (3.17.21: two `env:` in one step) and GitHub does not start the
run at all -- no tests for any push until it is fixed. Python's own YAML readers let the last one win, so this checks with the
standard library alone: per mapping (a list item starts a new one), each key once; text of block scalars (`run: |`) is skipped.
Also a plain (unquoted) value with ": " in it (3.17.64: `- name: Browsers (the click paths: Chromium …)`) -- YAML reads a second
key there, GitHub rejects the file and the nightly run never starts.
And the night's jobs (NightJobs): each runs exactly one random test -- two in one job take twice the time and are cancelled."""
import ast
import glob
import os
import re
import shlex
import shutil
import subprocess
import tempfile
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


def random_tests(path, _seen=None):
    """{class: {test, ...}} of a test file: the tests that draw random cases until the night's time is up -- they call
    fixtures.fuzz_seeds, or a function of their file that does (test_data_worlds.seeds). Read from the source alone: tests of
    a base class count for the class that inherits them (also one of another test file: test_fuzz.FuzzTests), `test_x = None`
    takes one out again."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    def calls(node):
        return {getattr(c.func, "attr", getattr(c.func, "id", "")) for c in ast.walk(node) if isinstance(c, ast.Call)}
    draws = {"fuzz_seeds"} | {f.name for f in tree.body if isinstance(f, ast.FunctionDef) and "fuzz_seeds" in calls(f)}
    classes = {c.name: c for c in tree.body if isinstance(c, ast.ClassDef)}
    seen = (_seen or set()) | {os.path.abspath(path)}

    def of(cls):
        got = set()
        for b in cls.bases:
            if isinstance(b, ast.Name) and b.id in classes:
                got |= of(classes[b.id])
            elif isinstance(b, ast.Attribute) and isinstance(b.value, ast.Name):
                other = os.path.join(os.path.dirname(os.path.abspath(path)), b.value.id + ".py")
                if os.path.exists(other) and other not in seen:
                    got |= random_tests(other, seen).get(b.attr, set())
        for n in cls.body:
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test"):
                got = got | {n.name} if draws & calls(n) else got - {n.name}
            elif isinstance(n, ast.Assign):
                got -= {t.id for t in n.targets if isinstance(t, ast.Name)}
        return got
    return {name: of(c) for name, c in classes.items()}


def chosen(tests, root=ROOT, skip=()):
    """What `pytest <tests>` of a night job runs of them: {(file, class, test)}. tests = files and at most one -k with a word
    or `not <word>` (pytest: part of the file's, the class's or the test's name, whatever the case) -- anything else is not
    understood here and raises."""
    args = shlex.split(tests)
    word, without = None, False
    if "-k" in args:
        i = args.index("-k")
        expr = args[i + 1].split()
        del args[i:i + 2]
        if len(expr) not in (1, 2) or (len(expr) == 2 and expr[0] != "not") or not re.fullmatch(r"\w+", expr[-1]):
            raise ValueError("-k %r: only a word or `not <word>`" % " ".join(expr))
        word, without = expr[-1].lower(), len(expr) == 2
    if not args or any(not a.endswith(".py") for a in args):
        raise ValueError("%r: only test files and -k" % tests)
    got = set()
    for f in args:
        for cls, names in random_tests(os.path.join(root, f)).items():
            for t in names:
                hit = word is not None and any(word in x.lower() for x in (os.path.basename(f), cls, t))
                if (word is None or hit != without) and "%s.%s" % (cls, t) not in skip:
                    got.add((f, cls, t))
    return got


def night_jobs(text):
    """([(name, tests, minutes)], the job's limit in minutes) from nightly.yml: the matrix rows, each with its own or the
    workflow's KONTOR_FUZZ_MINUTES."""
    usual = int(re.search(r"KONTOR_FUZZ_MINUTES: \$\{\{ matrix\.minutes \|\| '(\d+)' \}\}", text).group(1))
    limit = int(re.search(r"^    timeout-minutes: (\d+)", text, re.M).group(1))
    jobs = []
    for row in re.findall(r"^\s*- \{name: .*\}\s*$", text, re.M):
        m = re.search(r'name: "([^"]+)", tests: (?:"([^"]+)"|([^,}]+))', row)
        own = re.search(r'minutes: "(\d+)"', row)
        jobs.append((m.group(1), (m.group(2) or m.group(3)).strip(), int(own.group(1)) if own else usual))
    return jobs, limit


class NightJobs(unittest.TestCase):
    """The night's jobs (nightly.yml): every random test draws new cases for the whole of KONTOR_FUZZ_MINUTES, counted from
    when that test begins. Two of them in one job take twice the time -- past the job's limit, GitHub cancels it: the cash
    flow's file has two (cash flow, plans), its job was cancelled after 240 minutes night after night, the night never green,
    and of the plans' new cases none ever ran (fixed 3.17.81). So: one random test per job, every random test in a job, and
    its time within the job's limit."""
    PROBES = ("Seeds.test_fixed_found_and_new",)        # tests the drawing itself, with a time of its own (a tenth of a second)
    SLACK = 45                                          # minutes for the setup, the browsers and the fixed 1000 before the new ones

    def test_one_random_test_per_job(self):
        with open(os.path.join(ROOT, ".github", "workflows", "nightly.yml"), encoding="utf-8") as f:
            jobs, limit = night_jobs(f.read())
        self.assertGreater(len(jobs), 10)
        ran, files = set(), set()
        for name, tests, minutes in jobs:
            got = chosen(tests, skip=self.PROBES)
            self.assertEqual(len(got), 1, "%s runs %d random tests (%s) -- each takes the job's whole time: one job each, "
                             "picked with -k" % (name, len(got), ", ".join(sorted(t for _, _, t in got)) or "none"))
            self.assertLessEqual(minutes + self.SLACK, limit, "%s: %d minutes of new cases do not fit the job's %d" % (name, minutes, limit))
            ran |= got
            files |= {a for a in shlex.split(tests) if a.endswith(".py")}
        every = set().union(*(chosen(f, skip=self.PROBES) for f in files))
        self.assertEqual(sorted(every - ran), [], "random tests no job of the night runs")

    def test_finds_two_in_one_job(self):
        d = tempfile.mkdtemp(prefix="kontor-night-"); self.addCleanup(shutil.rmtree, d, True)
        os.mkdir(os.path.join(d, "tests"))
        files = {"test_a.py": "import fixtures as F\n\ndef seeds(n):\n    return F.fuzz_seeds(n)\n\n"
                              "class Base:\n    def test_base(self):\n        for s in F.fuzz_seeds('B'):\n            pass\n\n"
                              "class One(Base):\n    def test_plain(self):\n        pass\n\n"
                              "    def test_cash(self):\n        for s in F.fuzz_seeds('C'):\n            pass\n\n"
                              "    def test_plans(self):\n        for i, s in enumerate(seeds('P')):\n            pass\n",
                 "test_b.py": "import fixtures as F\nimport test_a\n\nclass Two(test_a.One):\n    test_base = None\n    test_cash = None\n\n"
                              "    def test_plans(self):\n        pass\n\n    def test_own(self):\n        list(F.fuzz_seeds('O'))\n"}
        for name, text in files.items():
            with open(os.path.join(d, "tests", name), "w", encoding="utf-8") as f:
                f.write(text)
        pick = lambda tests: sorted("%s.%s" % (c, t) for _, c, t in chosen(tests, d))
        # a base class runs its random test itself, and once more in each class that inherits it
        self.assertEqual(pick("tests/test_a.py"), ["Base.test_base", "One.test_base", "One.test_cash", "One.test_plans"])
        self.assertEqual(pick("tests/test_a.py -k plans"), ["One.test_plans"])
        self.assertEqual(pick("tests/test_a.py -k 'not Plans'"), ["Base.test_base", "One.test_base", "One.test_cash"])
        self.assertEqual(pick("tests/test_a.py -k one"), ["One.test_base", "One.test_cash", "One.test_plans"])      # the class's name too
        self.assertEqual(pick("tests/test_a.py -k test_a"), pick("tests/test_a.py"))                                # and the file's
        # inherited from another file; taken out with `= None`, or replaced by one that draws nothing
        self.assertEqual(pick("tests/test_b.py"), ["Two.test_own"])
        self.assertEqual(pick("tests/test_a.py tests/test_b.py -k own"), ["Two.test_own"])
        for bad in ("tests/test_a.py -k 'cash or plans'", "tests/test_a.py -x", "-k plans"):
            with self.assertRaises(ValueError, msg=bad):
                chosen(bad, d)
        # the night as it was until 3.17.80: both of the cash flow's random tests in one job
        jobs, limit = night_jobs('    timeout-minutes: 240\n      matrix:\n        include:\n'
                                 '          - {name: "Cashflow · feste + neue Fälle", tests: tests/test_cashflow.py, fixed: "1000"}\n'
                                 '          - {name: "Seiten", tests: "tests/test_data_worlds.py -k Pages", fixed: "0", browsers: true, minutes: "150"}\n'
                                 "          KONTOR_FUZZ_MINUTES: ${{ matrix.minutes || '170' }}\n")
        self.assertEqual((jobs, limit), ([("Cashflow · feste + neue Fälle", "tests/test_cashflow.py", 170),
                                          ("Seiten", "tests/test_data_worlds.py -k Pages", 150)], 240))
        self.assertEqual(sorted(t for _, _, t in chosen(jobs[0][1])), ["test_random_months_add_up", "test_random_plans_add_up"])


if __name__ == "__main__":
    unittest.main()
