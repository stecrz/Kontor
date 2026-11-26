"""The workflow files GitHub runs: a key twice in one mapping (3.17.21: two `env:` in one step) and GitHub does not start the
run at all -- no tests for any push until it is fixed. Python's own YAML readers let the last one win, so this checks with the
standard library alone: per mapping (a list item starts a new one), each key once; text of block scalars (`run: |`) is skipped.
Also a plain (unquoted) value with ": " in it (3.17.64: `- name: Browsers (the click paths: Chromium …)`) -- YAML reads a second
key there, GitHub rejects the file and the nightly run never starts.
And the night's jobs (NightJobs): each runs exactly one random test -- two in one job take twice the time and are cancelled."""
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


class NightStart(unittest.TestCase):
    """The night runs at night in Germany: started between 3 and 4 o'clock, summer and winter (the user, 2026-11-25: around 4;
    2026-11-26: always 3 to 4). GitHub's own schedule started it 7-9 hours late (3.17.94: 3:47 Europe/Berlin, started 12:29) --
    the `timezone` key sets the hour asked for, not the start. So nightly.yml has no schedule; night_start.yml wakes every two
    hours (each as late as GitHub makes it) and .github/night_start.py waits for 3:05 and starts it with workflow_dispatch
    (not delayed). GitHub's parser takes only `cron` and `timezone` in a schedule entry (@actions/workflow-parser: "Invalid
    schedule key" for anything else -- the file would be rejected)."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("night_start", os.path.join(ROOT, ".github", "night_start.py"))
        cls.N = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.N)
        with open(os.path.join(ROOT, ".github", "workflows", "night_start.yml"), encoding="utf-8") as f:
            cls.wake = f.read()

    def at(self, text):
        """An aware time from 'YYYY-MM-DD HH:MM' German time (the first, on the autumn hour that comes twice)."""
        return dt.datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=self.N.BERLIN)

    def test_the_night_has_no_schedule_of_its_own(self):
        with open(os.path.join(ROOT, ".github", "workflows", "nightly.yml"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(schedule(text), [], "GitHub would start it a second time, hours late, into the day")
        self.assertRegex(text, r"(?m)^  workflow_dispatch:")

    def test_wakes_every_two_hours(self):
        got = schedule(self.wake)
        self.assertEqual(len(got), 1, got)
        self.assertLessEqual(set(got[0]), {"cron", "timezone"})
        minute, hour, *rest = got[0]["cron"].split()
        self.assertEqual((hour, rest), ("*/%d" % (self.N.EVERY.seconds // 3600), ["*", "*", "*"]))
        self.assertNotIn(int(minute), (0, 30), "at the full or half hour GitHub is busiest")
        # the wait spans more than the gap between two wake-ups, and the job's limit the wait and three tries to start
        self.assertGreater(self.N.WAIT_MAX, self.N.EVERY)
        limit = int(re.search(r"(?m)^    timeout-minutes: *(\d+)", self.wake).group(1))
        self.assertGreaterEqual(limit, self.N.WAIT_MAX.total_seconds() / 60 + 5)
        self.assertLessEqual(limit, 360, "GitHub ends a job after six hours")
        self.assertRegex(self.wake, r"(?m)^  actions: write")
        self.assertRegex(self.wake, r"(?m)^concurrency:\n  group: [\w-]+\n  cancel-in-progress: false")
        self.assertIn("python3 .github/night_start.py", self.wake)

    def test_plan(self):
        P = self.N.plan
        old = [(self.at("2026-11-25 03:05"), "completed")]
        self.assertEqual(P(self.at("2026-11-25 22:00"), old)[0], "end")                 # too early: a later wake-up waits
        self.assertEqual(P(self.at("2026-11-26 00:19"), old)[0], "end")                 # 2 h 46 min before
        self.assertEqual(P(self.at("2026-11-26 01:00"), old)[:2], ("wait", 7500.0))      # 2 h 5 min
        self.assertEqual(P(self.at("2026-11-26 03:05"), old)[0], "start")
        self.assertEqual(P(self.at("2026-11-26 03:59"), old)[0], "start")               # a late wake-up still starts it
        self.assertEqual(P(self.at("2026-11-26 04:00"), old)[0], "end")                 # never by day
        self.assertEqual(P(self.at("2026-11-26 12:30"), old)[0], "end")
        started = old + [(self.at("2026-11-26 03:05"), "in_progress")]
        self.assertEqual(P(self.at("2026-11-26 03:20"), started)[0], "end")             # the next wake-up: started already
        self.assertEqual(P(self.at("2026-11-26 03:20"), [(self.at("2026-11-26 03:05"), "completed")])[0], "end")
        self.assertEqual(P(self.at("2026-11-26 03:05"), [(self.at("2026-11-26 01:00"), "in_progress")])[0], "end")   # one by hand
        self.assertEqual(P(self.at("2026-11-26 03:05"), [(self.at("2026-11-26 02:58"), "completed")])[0], "end")
        self.assertEqual(P(self.at("2026-11-26 03:05"), [(self.at("2026-11-26 01:00"), "completed")])[0], "start")
        self.assertEqual(P(self.at("2026-11-26 03:05"), [])[0], "start")
        self.assertEqual(P(self.at("2026-07-01 01:00"), [])[:2], ("wait", 7500.0))       # summer: the same German time
        # spring forward (28.3.2027: 2:00 -> 3:00): from 0:30 it is 1 h 35 min, not 2 h 35 min, to 3:05
        self.assertEqual(P(self.at("2027-03-28 00:30"), [])[:2], ("wait", 5700.0))
        # fall back (25.10.2026: 3:00 -> 2:00): from the first 2:30 it is 1 h 35 min of real time
        first = dt.datetime(2026, 10, 25, 0, 30, tzinfo=dt.timezone.utc)
        self.assertEqual(P(first, [])[:2], ("wait", 5700.0))
        self.assertEqual(P(dt.datetime(2026, 10, 24, 23, 0, tzinfo=dt.timezone.utc), [])[0], "end")      # 1:00: 3 h 5 min
        for what, seconds, why in (P(self.at("2026-11-26 01:00"), old), P(self.at("2026-11-26 03:20"), started)):
            self.assertIn("German time", why)

    def simulate(self, delay, days, seed=None):
        """German start times of the nights over `days` from 1.10.2026 (the autumn change of the clock among them), the
        wake-ups (every two hours at the cron's minute, UTC) each arriving `delay` hours late (+- 45 min if `seed`); one job at a
        time, the newest waiting one replacing an older (`concurrency`); a night's run takes three hours."""
        rnd = random.Random(seed)
        minute = int(schedule(self.wake)[0]["cron"].split()[0])
        t0 = dt.datetime(2026, 10, 1, 0, minute, tzinfo=dt.timezone.utc)
        arrive = sorted(t0 + i * self.N.EVERY + dt.timedelta(hours=delay, minutes=rnd.uniform(-45, 45) if seed is not None else 0)
                        for i in range(days * 12))
        runs, free, i = [], arrive[0] - dt.timedelta(days=1), 0
        state = lambda q: [(c, "in_progress" if q < c + dt.timedelta(hours=3) else "completed") for c in reversed(runs)]
        while i < len(arrive):
            t = arrive[i]
            if t < free:                    # waits for the running one; a newer one replaces it
                while i + 1 < len(arrive) and arrive[i + 1] < free:
                    i += 1
                t = free
            what, seconds, _ = self.N.plan(t, state(t))
            if what == "wait":
                t += dt.timedelta(seconds=seconds)
                what, seconds, _ = self.N.plan(t, state(t))
                self.assertNotEqual(what, "wait")
            if what == "start":
                runs.append(t)
            free, i = t + dt.timedelta(seconds=20), i + 1
        return [r.astimezone(self.N.BERLIN) for r in runs]

    def test_every_night_once_between_three_and_four(self):
        for delay in [x / 6 for x in range(0, 121)] + [9.0, 9.0, 9.0]:       # 0 to 20 hours late, in steps of 10 minutes
            for seed in (None, int(delay * 6)):
                got = self.simulate(delay, 40, seed)
                nights = [g.date() for g in got]
                first, last = nights[0], nights[-1]
                self.assertEqual(nights, [first + dt.timedelta(days=d) for d in range((last - first).days + 1)],
                                 "%.2f h late: a night missing or twice" % delay)
                self.assertGreaterEqual(len(nights), 38, delay)
                for g in got:
                    self.assertTrue(dt.time(3, 0) <= g.time() < dt.time(4, 0), "%.2f h late: started %s" % (delay, g))

    def test_reads_the_schedule(self):
        text = ("on:\n  schedule:                # a comment\n                           # more\n"
                "    - cron: \"17 1 * * *\"\n      timezone: 'Europe/Berlin'  # c\n    - cron: \"5 2 * * 1\"\n"
                "  workflow_dispatch:\n")
        self.assertEqual(schedule(text), [{"cron": "17 1 * * *", "timezone": "Europe/Berlin"}, {"cron": "5 2 * * 1"}])
        self.assertEqual(schedule("on:\n  push:\n"), [])


if __name__ == "__main__":
    unittest.main()
