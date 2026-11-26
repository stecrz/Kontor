"""The workflow files GitHub runs: a key twice in one mapping (3.17.21: two `env:` in one step) and GitHub does not start the
run at all -- no tests for any push until it is fixed. Python's own YAML readers let the last one win, so this checks with the
standard library alone: per mapping (a list item starts a new one), each key once; text of block scalars (`run: |`) is skipped.
Also a plain (unquoted) value with ": " in it (3.17.64: `- name: Browsers (the click paths: Chromium …)`) -- YAML reads a second
key there, GitHub rejects the file and the nightly run never starts.
And the night's jobs (NightJobs): each runs exactly one random test -- two in one job take twice the time and are cancelled;
the night between 3 and 4 German time (Night)."""
import ast
import datetime as dt
import glob
import importlib.util
import os
import random
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


def jobs_of(text):
    """{job id: its text} of a workflow file (the lines under `jobs:` from `  <id>:` to the next)."""
    body = text[text.index("\njobs:\n") + 7:] if "\njobs:\n" in text else ""
    parts = re.split(r"(?m)^  ([\w-]+):[^\n]*\n", body)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def night_jobs(text):
    """([(name, tests, minutes)], the job's limit in minutes) from nightly.yml: the matrix rows, each with its own or the
    workflow's KONTOR_FUZZ_MINUTES."""
    usual = int(re.search(r"KONTOR_FUZZ_MINUTES: \$\{\{ matrix\.minutes \|\| '(\d+)' \}\}", text).group(1))
    text = jobs_of(text).get("fuzz", text)               # the tests' job (nightly.yml has the wake-up's beside it)
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


class PushJobs(unittest.TestCase):
    """Every version's tests (tests.yml) in parts side by side, a few minutes each (the user, 2026-11-27): every test file runs
    in exactly one part with Kontor's own Python -- a new one lands in "Übrige" by itself; the click paths (random walks) only
    at night, where they must be. Nothing lost when parts are cut anew, nothing twice."""
    NIGHT_ONLY = {"tests/test_clickpaths.py"}

    def parts(self):
        with open(os.path.join(ROOT, ".github", "workflows", "tests.yml"), encoding="utf-8") as f:
            text = jobs_of(f.read())["test"]
        rows = re.findall(r'(?m)^          - name: "([^"]+)"\n((?:            [^\n]*\n)+)', text)
        self.assertGreater(len(rows), 4)
        every = {os.path.relpath(f, ROOT) for f in glob.glob(os.path.join(ROOT, "tests", "test_*.py"))}
        out = []
        for name, body in rows:
            python = re.search(r'(?m)^            python: "([\d.]+)"', body).group(1)
            args = shlex.split(re.search(r"(?m)^            tests: (.+)$", body).group(1))
            ignored = {a.split("=", 1)[1] for a in args if a.startswith("--ignore=")}
            self.assertEqual(sorted(ignored - every), [], "%s leaves out a file that is not there" % name)
            files = set()
            for a in args:
                if a == "tests":
                    files |= every - ignored
                elif not a.startswith("-"):
                    self.assertIn(a, every, name)
                    files.add(a)
            out.append((name, python, files))
        return out, every

    def test_every_file_once(self):
        parts, every = self.parts()
        seen = {}
        for name, python, files in parts:
            if python == "3.9":
                self.assertEqual(files, {"tests/test_python.py"}, "Apple's 3.9: only the starter")
                continue
            for f in files:
                self.assertIsNone(seen.get(f), "%s runs in %s and in %s" % (f, seen.get(f), name))
                seen[f] = name
        self.assertEqual(sorted(every - set(seen) - self.NIGHT_ONLY), [], "test files no part runs")
        self.assertEqual(sorted(self.NIGHT_ONLY & set(seen)), [], "the click paths: at night only")
        with open(os.path.join(ROOT, ".github", "workflows", "nightly.yml"), encoding="utf-8") as f:
            night = {t for _, tests, _ in night_jobs(f.read())[0] for t in shlex.split(tests) if t.endswith(".py")}
        self.assertEqual(sorted(self.NIGHT_ONLY - night), [], "not run at night either")


def schedule(text):
    """[{key: value}] of the entries under `on: schedule:`, values unquoted."""
    m = re.search(r"^  schedule:[^\n]*\n((?:(?:    | *#)[^\n]*\n)+)", text, re.M)
    out = []
    for line in (m.group(1) if m else "").splitlines():
        k = re.match(r"^    (- |  )(\w+): *(\"[^\"]*\"|'[^']*'|[^#\s][^#]*?)\s*(#.*)?$", line)
        if not k:
            continue
        if k.group(1) == "- " or not out:
            out.append({})
        out[-1][k.group(2)] = k.group(3).strip("\"'")
    return out


class Night(unittest.TestCase):
    """The night runs at night in Germany: started between 3 and 4 o'clock, summer and winter (the user, 2026-11-25: around 4;
    2026-11-26/27: always 3 to 4, one workflow for the night). GitHub's own schedule started it here 7-9 hours late (3.17.94:
    3:47 Europe/Berlin, started 12:29) and left out three of four wake-ups (26.11.) -- the `timezone` key sets the hour asked
    for, not the start. So nightly.yml wakes every two hours (job "wake", each as late as GitHub makes it) and .github/nightly.py
    waits for 3:05 and starts the night in the same workflow with workflow_dispatch (not delayed; job "fuzz"). GitHub's parser
    takes only `cron` and `timezone` in a schedule entry (@actions/workflow-parser: "Invalid schedule key" for anything else --
    the file would be rejected)."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("nightly", os.path.join(ROOT, ".github", "nightly.py"))
        cls.N = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.N)
        with open(os.path.join(ROOT, ".github", "workflows", "nightly.yml"), encoding="utf-8") as f:
            cls.text = f.read()
        cls.jobs = jobs_of(cls.text)

    def at(self, text):
        """An aware time from 'YYYY-MM-DD HH:MM' German time (the first, on the autumn hour that comes twice)."""
        return dt.datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=self.N.BERLIN)

    def test_one_workflow_wakes_and_tests(self):
        self.assertEqual(sorted(os.path.basename(f) for f in glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml"))),
                         ["nightly.yml", "tests.yml"], "two kinds of tests (the user, 2026-11-27): every version, every night")
        self.assertEqual(sorted(self.jobs), ["fuzz", "wake"])
        got = schedule(self.text)
        self.assertEqual(len(got), 1, got)
        self.assertLessEqual(set(got[0]), {"cron", "timezone"})
        minute, hour, *rest = got[0]["cron"].split()
        self.assertEqual((hour, rest), ("*/%d" % (self.N.EVERY.seconds // 3600), ["*", "*", "*"]))
        self.assertNotIn(int(minute), (0, 30), "at the full or half hour GitHub is busiest")
        self.assertRegex(self.text, r"(?m)^  workflow_dispatch:")
        # the wake-ups only wake, the night only by workflow_dispatch (by the wake-up or by hand) -- never a schedule's run testing by day
        wake, fuzz = self.jobs["wake"], self.jobs["fuzz"]
        self.assertRegex(wake, r"(?m)^    if: github\.event_name == 'schedule'$")
        self.assertRegex(fuzz, r"(?m)^    if: github\.event_name == 'workflow_dispatch'$")
        self.assertRegex(wake, r"(?m)^      actions: write")
        self.assertNotIn("actions: write", fuzz)
        self.assertIn("python3 .github/nightly.py", wake)
        self.assertNotRegex(self.text, r"(?m)^concurrency:", "a newer wake-up would cancel a waiting one")
        # at least two wake-ups fall into the wait before 3:05; the job's limit holds the wait and the tries to start
        self.assertGreaterEqual(self.N.WAIT_MAX, 2 * self.N.EVERY)
        limit = int(re.search(r"(?m)^    timeout-minutes: *(\d+)", wake).group(1))
        self.assertGreaterEqual(limit, self.N.WAIT_MAX.total_seconds() / 60 + 15)
        self.assertLessEqual(limit, 360, "GitHub ends a job after six hours")

    def test_plan(self):
        P, me = self.N.plan, 50
        old = [(10, "workflow_dispatch", "completed", self.at("2026-11-25 03:05"))]
        self.assertEqual(P(self.at("2026-11-25 21:00"), old, me)[0], "end")             # 6 h 5 min before: a later wake-up waits
        self.assertEqual(P(self.at("2026-11-25 21:34"), old, me)[0], "end")             # 5 h 31 min
        self.assertEqual(P(self.at("2026-11-25 21:36"), old, me)[:2], ("wait", 19740.0))
        self.assertEqual(P(self.at("2026-11-26 01:00"), old, me)[:2], ("wait", 7500.0))
        self.assertEqual(P(self.at("2026-11-26 03:05"), old, me)[0], "start")
        self.assertEqual(P(self.at("2026-11-26 03:59"), old, me)[0], "start")           # a late wake-up still starts it
        self.assertEqual(P(self.at("2026-11-26 04:00"), old, me)[0], "end")             # never by day
        self.assertEqual(P(self.at("2026-11-26 12:30"), old, me)[0], "end")
        # an earlier wake-up waits: this one gives way; a later one never stops it
        waits = old + [(40, "schedule", "in_progress", self.at("2026-11-25 22:40"))]
        self.assertEqual(P(self.at("2026-11-26 00:40"), waits, me)[0], "end")
        self.assertEqual(P(self.at("2026-11-26 03:10"), waits, me)[0], "end")
        later = old + [(60, "schedule", "in_progress", self.at("2026-11-26 03:05"))]
        self.assertEqual(P(self.at("2026-11-26 03:05"), later, me)[0], "start")
        self.assertEqual(P(self.at("2026-11-26 03:05"), old + [(40, "schedule", "completed", self.at("2026-11-25 22:40"))], me)[0], "start")
        # the night started already, or one by hand runs: tonight's
        started = old + [(55, "workflow_dispatch", "in_progress", self.at("2026-11-26 03:05"))]
        self.assertEqual(P(self.at("2026-11-26 03:20"), started, me)[0], "end")
        self.assertEqual(P(self.at("2026-11-26 03:20"), old + [(55, "workflow_dispatch", "completed", self.at("2026-11-26 03:05"))], me)[0], "end")
        self.assertEqual(P(self.at("2026-11-26 03:05"), old + [(30, "workflow_dispatch", "in_progress", self.at("2026-11-26 01:00"))], me)[0], "end")
        self.assertEqual(P(self.at("2026-11-26 03:05"), old + [(30, "workflow_dispatch", "queued", self.at("2026-11-26 03:04"))], me)[0], "end")
        self.assertEqual(P(self.at("2026-11-26 03:05"), old + [(30, "workflow_dispatch", "completed", self.at("2026-11-26 01:00"))], me)[0], "start")
        self.assertEqual(P(self.at("2026-11-26 03:05"), [], me)[0], "start")
        self.assertEqual(P(self.at("2026-11-26 03:05"), [(me, "schedule", "in_progress", self.at("2026-11-26 01:00"))], me)[0], "start")   # itself
        self.assertEqual(P(self.at("2026-07-01 01:00"), [], me)[:2], ("wait", 7500.0))   # summer: the same German time
        # spring forward (28.3.2027: 2:00 -> 3:00): from 0:30 it is 1 h 35 min, not 2 h 35 min, to 3:05
        self.assertEqual(P(self.at("2027-03-28 00:30"), [], me)[:2], ("wait", 5700.0))
        # fall back (25.10.2026: 3:00 -> 2:00): from the first 2:30 it is 1 h 35 min of real time, from 1:00 3 h 5 min
        self.assertEqual(P(dt.datetime(2026, 10, 25, 0, 30, tzinfo=dt.timezone.utc), [], me)[:2], ("wait", 5700.0))
        self.assertEqual(P(dt.datetime(2026, 10, 24, 23, 0, tzinfo=dt.timezone.utc), [], me)[:2], ("wait", 11100.0))
        for what, seconds, why in (P(self.at("2026-11-26 01:00"), old, me), P(self.at("2026-11-26 03:20"), started, me)):
            self.assertIn("German time", why)

    def simulate(self, delay, days, seed=None, drop=0.0):
        """German start times of the nights over `days` from 1.10.2026 (the autumn change of the clock among them): the
        wake-ups (every two hours at the cron's minute, UTC) each arrive `delay` hours late (+- 45 min if `seed`), a share
        `drop` never; each gets the next run id as it arrives and plans on its own, side by side (no `concurrency`); a waiting
        one plans again at the end of its wait; a night runs three hours."""
        import heapq
        rnd = random.Random(seed)
        minute = int(schedule(self.text)[0]["cron"].split()[0])
        t0 = dt.datetime(2026, 10, 1, 0, minute, tzinfo=dt.timezone.utc)
        events = []
        for i in range(days * 12):
            if rnd.random() < drop:
                continue
            t = t0 + i * self.N.EVERY + dt.timedelta(hours=delay, minutes=rnd.uniform(-45, 45) if seed is not None else 0)
            heapq.heappush(events, (t, i, "arrive", None))
        runs, nights, ids = [], [], iter(range(1, 10 ** 6))         # runs: [id, event, created, end]
        state = lambda q: [(r[0], r[1], "in_progress" if r[2] <= q < r[3] else ("queued" if q < r[2] else "completed"), r[2])
                           for r in reversed(runs) if r[2] <= q]
        far = dt.datetime(2100, 1, 1, tzinfo=dt.timezone.utc)
        while events:
            t, i, kind, run = heapq.heappop(events)
            if kind == "arrive":
                run = [next(ids), "schedule", t, far]
                runs.append(run)
            what, seconds, _ = self.N.plan(t, state(t), run[0])
            if kind == "again":
                self.assertNotEqual(what, "wait", "waited, and is to wait again")
            if what == "wait":
                self.assertLessEqual(seconds, self.N.WAIT_MAX.total_seconds())
                heapq.heappush(events, (t + dt.timedelta(seconds=seconds), i, "again", run))
                continue
            if what == "start":
                runs.append([next(ids), "workflow_dispatch", t + dt.timedelta(seconds=5), t + dt.timedelta(hours=3)])
                nights.append(t)
                run[3] = t + dt.timedelta(seconds=40)                  # ends once the night is in the list
            else:
                run[3] = t + dt.timedelta(seconds=20)
        return [n.astimezone(self.N.BERLIN) for n in nights]

    def check(self, got, delay, least):
        nights = [g.date() for g in got]
        self.assertEqual(len(nights), len(set(nights)), "%.2f h late: a night twice" % delay)
        self.assertGreaterEqual(len(nights), least, "%.2f h late: nights missing" % delay)
        for g in got:
            self.assertTrue(dt.time(3, 0) <= g.time() < dt.time(4, 0), "%.2f h late: started %s" % (delay, g))

    def test_every_night_once_between_three_and_four(self):
        for delay in [x / 6 for x in range(0, 121)] + [9.0, 9.0, 9.0]:       # 0 to 20 hours late, in steps of 10 minutes
            for seed in (None, int(delay * 6)):
                got = self.simulate(delay, 40, seed)
                first, last = got[0].date(), got[-1].date()
                self.assertEqual([g.date() for g in got], [first + dt.timedelta(days=d) for d in range((last - first).days + 1)],
                                 "%.2f h late: a night missing or twice" % delay)
                self.check(got, delay, 38)

    def test_wake_ups_left_out(self):
        # half of the wake-ups never come: a night needs one of the three or four in the 6 1/2 hours before 4:00 -- never two
        for delay in (0.0, 0.8, 3.0, 8.5, 9.0, 14.0):
            self.check(self.simulate(delay, 60, seed=int(delay * 10) + 1, drop=0.5), delay, 45)
        self.check(self.simulate(8.7, 40, seed=7, drop=0.75), 8.7, 15)          # 26.11.: three of four left out

    def test_reads_the_schedule(self):
        text = ("on:\n  schedule:                # a comment\n                           # more\n"
                "    - cron: \"17 1 * * *\"\n      timezone: 'Europe/Berlin'  # c\n    - cron: \"5 2 * * 1\"\n"
                "  workflow_dispatch:\n")
        self.assertEqual(schedule(text), [{"cron": "17 1 * * *", "timezone": "Europe/Berlin"}, {"cron": "5 2 * * 1"}])
        self.assertEqual(schedule("on:\n  push:\n"), [])


if __name__ == "__main__":
    unittest.main()
