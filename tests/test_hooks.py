"""The briefing every chat gets about the other chats' work (.claude/hooks/briefing.py) and the push checks
(.githooks/pre-push, which the briefing turns on, and the guard before every push, .claude/hooks/guard.py), on throwaway
repositories: it lists what is new on main, fast-forwards only a clone with nothing of its own, names overlapping files,
stays silent while nothing changed -- and a version squashed onto a stale main is refused."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import datetime
from zoneinfo import ZoneInfo

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "hooks", "briefing.py")
PRE_PUSH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".githooks", "pre-push")
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)


@unittest.skipUnless(shutil.which("git"), "git fehlt")
class Briefing(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-briefing-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.git(self.dir, "init", "-q", "--bare", "origin.git")
        self.git(os.path.join(self.dir, "origin.git"), "symbolic-ref", "HEAD", "refs/heads/main")
        self.a, self.b = self.clone("a"), self.clone("b")
        self.publish(self.b, "1.0.0", "first version", {"web/app.js": "one\n"})
        self.git(self.a, "pull", "-q", "origin", "main")

    def git(self, cwd, *args):
        r = subprocess.run(["git"] + list(args), cwd=cwd, env=ENV, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def clone(self, name):
        d = os.path.join(self.dir, name)
        self.git(self.dir, "clone", "-q", "origin.git", name)
        self.git(d, "checkout", "-q", "-B", "main")
        os.makedirs(os.path.join(d, ".claude", "hooks"))
        shutil.copy(HOOK, os.path.join(d, ".claude", "hooks", "briefing.py"))
        os.makedirs(os.path.join(d, ".githooks"))
        shutil.copy(PRE_PUSH, os.path.join(d, ".githooks", "pre-push"))
        with open(os.path.join(d, ".git", "info", "exclude"), "a") as f:
            f.write(".claude/\n.githooks/\n")
        return d

    def publish(self, d, version, subject, files, push=True):
        try:
            with open(os.path.join(d, "CHANGELOG.md")) as f:
                log = f.read()
        except OSError:
            log = ""
        for name, text in dict(files, VERSION=version + "\n", **{"CHANGELOG.md": "%s %s\n%s" % (version, subject, log)}).items():
            os.makedirs(os.path.dirname(os.path.join(d, name)) or d, exist_ok=True)
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        self.git(d, "add", "-A")
        self.git(d, "commit", "-q", "-m", "%s: %s" % (version, subject), "-m", "Claude Test: https://claude.ai/code/session_01ABCDwxyz")
        if push:
            return subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=d, env=ENV, capture_output=True, text=True)

    def briefing(self, d, *args):
        r = subprocess.run([sys.executable, os.path.join(d, ".claude", "hooks", "briefing.py")] + list(args), cwd=d, env=ENV,
                           input="{}", capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return r.stdout

    def test_untouched_clone_is_fast_forwarded_and_told_what_is_new(self):
        self.briefing(self.a, "hook")
        self.assertEqual(self.briefing(self.a, "hook"), "")                         # nothing new: silent
        self.publish(self.b, "1.0.1", "sharper charts", {"web/app.js": "two\n", "report.py": "x = 1\n"})
        out = self.briefing(self.a, "hook")
        self.assertIn("main steht bei 1.0.1", out)
        self.assertIn("1.0.1: sharper charts · Chat …wxyz · ", out)
        self.assertIn("web/app.js", out); self.assertIn("report.py", out)
        self.assertNotIn("VERSION", out); self.assertNotIn("CHANGELOG", out)        # every version changes these
        self.assertIn("steht jetzt auf 1.0.1", out)
        self.assertEqual(self.git(self.a, "rev-parse", "HEAD"), self.git(self.a, "rev-parse", "origin/main"))
        self.assertEqual(self.briefing(self.a, "hook"), "")
        self.assertIn("main steht bei 1.0.1", self.briefing(self.a))                # by hand: always the state

    def test_own_work_is_never_touched_and_overlap_is_named(self):
        self.briefing(self.a, "hook")
        with open(os.path.join(self.a, "web", "app.js"), "w") as f:
            f.write("mine\n")
        with open(os.path.join(self.a, "tax.py"), "w") as f:
            f.write("mine\n")
        head = self.git(self.a, "rev-parse", "HEAD")
        self.publish(self.b, "1.0.1", "sharper charts", {"web/app.js": "two\n", "report.py": "x = 1\n"})
        out = self.briefing(self.a, "hook")
        self.assertIn("Überschneidung mit deiner Arbeit: web/app.js –", out)
        self.assertIn("git pull --rebase origin main", out)
        self.assertNotIn("steht jetzt auf", out)
        self.assertEqual(self.git(self.a, "rev-parse", "HEAD"), head)
        with open(os.path.join(self.a, "web", "app.js")) as f:
            self.assertEqual(f.read(), "mine\n")
        self.assertEqual(self.briefing(self.a, "hook"), "")                         # told once, no nagging
        # committed work counts as well: not fast-forwarded, the overlap still named with the next foreign version
        self.git(self.a, "commit", "-q", "-am", "wip")
        self.publish(self.b, "1.0.2", "more", {"web/app.js": "three\n"})
        out = self.briefing(self.a, "hook")
        self.assertIn("1.0.1: sharper charts", out); self.assertIn("1.0.2: more", out)
        self.assertIn("Überschneidung mit deiner Arbeit: web/app.js –", out)
        self.assertEqual(self.git(self.a, "log", "-1", "--format=%s"), "wip")

    def test_push_from_a_stale_main_is_refused(self):
        self.briefing(self.a, "hook")                                               # turns the push check on
        self.assertEqual(self.git(self.a, "config", "core.hooksPath"), ".githooks")
        self.assertEqual(self.publish(self.b, "1.0.1", "sharper charts", {"report.py": "x = 1\n"}).returncode, 0)
        # a squashes its work onto the newer main without rebasing: b's version would be gone
        self.publish(self.a, "1.0.1", "mine", {"tax.py": "mine\n"}, push=False)
        self.git(self.a, "fetch", "-q", "origin", "main")
        self.git(self.a, "reset", "-q", "--soft", "origin/main")
        self.git(self.a, "commit", "-q", "-m", "1.0.2: mine")
        r = subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=self.a, env=ENV, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Push nach main abgelehnt", r.stderr)
        self.assertIn("VERSION 1.0.1 ist nicht höher als 1.0.1", r.stderr)
        self.assertIn("CHANGELOG.md verliert 1 Zeile(n) von main, etwa: 1.0.1 sharper charts", r.stderr)
        self.assertEqual(self.git(self.b, "ls-remote", "origin", "main").split()[0], self.git(self.b, "rev-parse", "HEAD"))
        # done the right way -- on top of main, the next number -- it goes through
        self.git(self.a, "reset", "-q", "--hard", "origin/main")
        r = self.publish(self.a, "1.0.2", "mine", {"tax.py": "mine\n"})
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        # a deliberate exception still possible
        with open(os.path.join(self.a, "CHANGELOG.md"), "w") as f:
            f.write("1.0.3 typo fixed\n")
        self.git(self.a, "commit", "-q", "-am", "1.0.3: typo")
        self.assertNotEqual(subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=self.a, env=ENV, capture_output=True).returncode, 0)
        r = subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=self.a, env=dict(ENV, KONTOR_PUSH_OK="1"), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_never_fails_outside_a_repository(self):
        d = os.path.join(self.dir, "plain"); os.makedirs(os.path.join(d, ".claude", "hooks"))
        shutil.copy(HOOK, os.path.join(d, ".claude", "hooks", "briefing.py"))
        r = subprocess.run([sys.executable, os.path.join(d, ".claude", "hooks", "briefing.py"), "hook"], cwd=d,
                           env=dict(ENV, GIT_CEILING_DIRECTORIES=self.dir), input="", capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))


class TestsOnGitHub(unittest.TestCase):
    """The line on GitHub's tests (made-up runs): a red version names the chat that broke it; the night's run (random cases,
    belongs to no version) red -> the next chat fixes it, and once a "fix nightly" version is on main the others leave it."""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("briefing", HOOK)
        self.B = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.B)

    def run_(self, sha, title, ok=True, status="completed"):
        return {"head_sha": sha, "display_title": title, "status": status, "conclusion": ("success" if ok else "failure") if status == "completed" else None}

    def night(self, n, ok, version="3.1.2", conclusion=None):
        return {"id": n, "head_sha": "c%05d" % n, "status": "completed", "conclusion": conclusion or ("success" if ok else "failure"),
                "created_at": "2026-11-22T02:17:00Z", "display_title": "Zufallsläufe", "head_commit": {"message": version + ": something\n\nClaude X: y"}}

    def summary(self, push, night, log=""):
        self.since = []
        def since(iso):
            self.since.append(iso); return log
        return self.B.ci_summary(push, night, since, lambda sha: "Chat …ABCD")

    def test_versions_and_night(self):
        push = [self.run_("bbb", "3.1.3: b", status="in_progress"), self.run_("aaa", "3.1.2: a")]
        line, key = self.summary(push, [])
        self.assertEqual((line, key), ("Tests auf GitHub: läuft für 3.1.3; 3.1.2 grün", "ok"))
        line, key = self.summary(push, [self.night(7, True)])
        self.assertIn("Nachtlauf (Zufallsfälle) für 3.1.2 grün", line); self.assertEqual(key, "ok")
        # a red version: the chat that pushed does not wait -- the next chat that sees it fixes it, marked "fix ci"
        red = [dict(self.run_("ccc", "3.1.4: c", ok=False), id=12), dict(self.run_("bbb", "3.1.3: b", ok=False), id=11, created_at="2026-11-24T01:00:00Z"),
               self.run_("aaa", "3.1.2: a")]
        line, key = self.summary(red, [])
        self.assertIn("ROT seit 3.1.3 (Chat …ABCD)", line); self.assertIn("fix ci", line); self.assertIn("gh run view 11 --log-failed", line)
        self.assertIn("gh run rerun 11 --failed", line); self.assertEqual(key, "red bbb"); self.assertEqual(self.since, ["2026-11-24T01:00:00Z"])
        # a fix on main whose own run is not done yet: the others leave it (the key changes, so every chat hears it once)
        line, key = self.summary(red, [], "3.1.5: fix ci: date in WebKit\x1fClaude X: https://claude.ai/code/session_01Qwxyz\n\x1e")
        self.assertIn("rot seit 3.1.3, behoben in 3.1.5 (Chat …wxyz)", line); self.assertNotIn("ROT", line); self.assertEqual(key, "red-fixed bbb")
        # ... its run done and still red: not fixed
        line, key = self.summary([self.run_("ddd", "3.1.5: fix ci: date", ok=False)] + red, [], "3.1.5: fix ci: date in WebKit\x1f\x1e")
        self.assertIn("ROT seit 3.1.3", line); self.assertEqual(key, "red bbb")

    def test_red_night_is_fixed_by_the_next_chat_once(self):
        push = [self.run_("aaa", "3.1.2: a")]
        line, key = self.summary(push, [self.night(8, False), self.night(7, True)])
        self.assertIn("Nachtlauf (Zufallsfälle) für 3.1.2 ROT", line); self.assertIn("fix nightly", line); self.assertIn("KONTOR_FUZZ_SEED=", line)
        self.assertIn("gh run view 8 --log-failed", line); self.assertIn("KONTOR_FUZZ_SEEDS=1000", line)
        self.assertEqual(key, "night-red 8"); self.assertEqual(self.since, ["2026-11-22T02:17:00Z"])       # only what came after the run
        # versions since then that are no fix: still red
        line, key = self.summary(push, [self.night(8, False)], "3.1.3: nightly mentioned in passing\x1fClaude X: session_01Q\x1e3.1.4: other\x1f\x1e")
        self.assertEqual(key, "night-red 8")
        # a fix on main: the others leave it -- the key changes, so every chat hears it once
        line, key = self.summary(push, [self.night(8, False)], "3.1.5: other\x1f\x1e3.1.4: fix nightly: rounding at the turn of the year\x1fClaude X: https://claude.ai/code/session_01Qwxyz\n\x1e")
        self.assertIn("Nachtlauf für 3.1.2 rot, behoben in 3.1.4 (Chat …wxyz)", line); self.assertNotIn("ROT", line); self.assertEqual(key, "night-fixed 8")
        # the next night green again
        line, key = self.summary(push, [self.night(9, True, "3.1.5"), self.night(8, False)])
        self.assertIn("für 3.1.5 grün", line); self.assertEqual(key, "ok")
        # timed out or cancelled counts as red too (named); still running or skipped: the last finished one counts
        line, key = self.summary(push, [self.night(10, False, conclusion="timed_out")]); self.assertIn("ROT (timed_out)", line)
        running = dict(self.night(11, True), status="in_progress", conclusion=None)
        self.assertEqual(self.summary(push, [running, self.night(10, False)])[1], "night-red 10")

    def test_nothing_known_says_nothing(self):
        self.assertEqual(self.summary([], []), ("", ""))

    def test_night_tests_are_what_nightly_runs(self):
        # the hint for a red night names the files to check again -- the click paths and data worlds (3.17.64, 3.17.66) were missing
        with open(os.path.join(os.path.dirname(HOOK), "..", "..", ".github", "workflows", "nightly.yml"), encoding="utf-8") as f:
            runs = set(re.findall(r"\btests/test_\w+\.py\b", "\n".join(l for l in f if re.match(r"\s*- \{name:", l))))
        self.assertEqual(set(self.B.NIGHT_TESTS.split()), runs)


GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "hooks", "guard.py")


class ReadGuard(unittest.TestCase):
    """A big text file is never read whole -- what is read stays in the chat and is paid again at every later step: find the
    place, then a range of it (.claude/hooks/guard.py, read_check). Pictures and small files as they are."""

    def guard(self, **tool_input):
        r = subprocess.run([sys.executable, GUARD], env=ENV, capture_output=True, text=True, timeout=60,
                           input=json.dumps({"tool_name": "Read", "tool_input": tool_input}))
        return r.returncode, r.stderr

    def test_big_files_in_parts(self):
        d = tempfile.mkdtemp(prefix="kontor-read-"); self.addCleanup(shutil.rmtree, d, True)
        big, small, pic = os.path.join(d, "app.js"), os.path.join(d, "VERSION"), os.path.join(d, "shot.png")
        for path, size in ((big, 300_000), (small, 10), (pic, 300_000)):
            with open(path, "w") as f:
                f.write(("x" * 99 + "\n") * (size // 100))
        code, why = self.guard(file_path=big)
        self.assertEqual(code, 2); self.assertIn("grep -n", why); self.assertIn("offset und limit", why)
        self.assertEqual(self.guard(file_path=big, offset=1200, limit=2000)[0], 2)          # a range too large is no range
        self.assertEqual(self.guard(file_path=big, offset=1200, limit=200)[0], 0)
        self.assertEqual(self.guard(file_path=small)[0], 0)
        self.assertEqual(self.guard(file_path=pic)[0], 0)
        self.assertEqual(self.guard(file_path=os.path.join(d, "missing.py"))[0], 0)


@unittest.skipUnless(shutil.which("git"), "git fehlt")
class PushGuard(unittest.TestCase):
    """The lock before every push (.claude/hooks/guard.py): only the newest main plus one proper version per commit gets to
    GitHub -- never an old state put on top with reset --soft (how 66ad67f overwrote two versions), never off the newest main,
    never without raising VERSION; and the same check for a push on GitHub (chain)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-guard-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.git(self.dir, "init", "-q", "--bare", "origin.git")
        self.git(os.path.join(self.dir, "origin.git"), "symbolic-ref", "HEAD", "refs/heads/main")
        self.a, self.b = self.clone("a"), self.clone("b")
        self.version(self.b, "1.0.0", {"app.js": "one\n"}); self.git(self.b, "push", "-q", "origin", "HEAD:main")
        self.git(self.a, "pull", "-q", "origin", "main")

    def git(self, cwd, *args):
        r = subprocess.run(["git"] + list(args), cwd=cwd, env=ENV, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def clone(self, name):
        d = os.path.join(self.dir, name)
        self.git(self.dir, "clone", "-q", "origin.git", name)
        self.git(d, "checkout", "-q", "-B", "main")
        return d

    def version(self, d, v, files, keep=True, heading=None, made=None):
        """One version: its files, VERSION and a changelog section on top (keep: the sections before it stay); the heading's time
        is the clock's unless given (heading "2026-01-01 10:00", commit made "2026-01-01T09:30:00+01:00")."""
        old = open(os.path.join(d, "CHANGELOG.md")).read().split("\n", 2)[2] if keep and os.path.exists(os.path.join(d, "CHANGELOG.md")) else ""
        heading = heading or datetime.datetime.now(ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d %H:%M")
        for name, text in dict(files, VERSION=v + "\n", **{"CHANGELOG.md": "# Änderungen\n\n## %s (%s)\n- %s\n\n%s" % (v, heading, v, old)}).items():
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        self.git(d, "add", "-A")
        if made:
            subprocess.run(["git", "commit", "-q", "-m", "%s: change" % v], cwd=d, check=True, capture_output=True,
                           env=dict(ENV, GIT_COMMITTER_DATE=made, GIT_AUTHOR_DATE=made))
        else:
            self.git(d, "commit", "-q", "-m", "%s: change" % v)

    def guard(self, d, command="git push origin HEAD:main"):
        r = subprocess.run([sys.executable, GUARD], cwd=d, env=ENV, capture_output=True, text=True, timeout=60,
                           input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": d}))
        return r.returncode, r.stderr

    def test_proper_version_may_go(self):
        self.version(self.a, "1.0.1", {"app.js": "two\n"})
        self.assertEqual(self.guard(self.a), (0, ""))
        self.assertEqual(self.guard(self.dir, "cd %s && git push origin HEAD:main" % self.a), (0, ""))   # pushed from elsewhere: that repository
        self.assertEqual(self.guard(self.a, 'grep -n "git push" CLAUDE.md')[0], 0)  # the words in a text are no push

    def test_only_main_on_github(self):
        """The cloud session names a branch claude/… to push to; Kontor keeps it local (one commit per version on main) --
        removing an old branch stays possible without the version check, main itself never."""
        self.version(self.a, "1.0.1", {"app.js": "two\n"})
        for push in ("git push -u origin claude/some-name-x1", "git push origin HEAD:claude/x", "git push origin HEAD:refs/heads/claude/x"):
            code, out = self.guard(self.a, push)
            self.assertEqual(code, 2, push); self.assertIn("nur auf main", out)
        self.git(self.b, "pull", "-q", "origin", "main"); self.version(self.b, "1.0.1", {"app.js": "b\n"})
        self.git(self.b, "push", "-q", "origin", "HEAD:main")                       # a is behind now: a push to main is locked ...
        self.assertEqual(self.guard(self.a)[0], 2)
        for drop in ("git push origin --delete claude/old-x1 ci/test", "git push origin :claude/old-x1"):
            self.assertEqual(self.guard(self.a, drop), (0, ""), drop)              # ... removing a branch is not a version
        self.assertEqual(self.guard(self.a, "git push origin :claude/old HEAD:main")[0], 2)   # unless main goes along
        self.assertIn("main nie löschen", self.guard(self.a, "git push origin --delete main")[1])
        self.assertIn("Force-Push", self.guard(self.a, "git push -f origin HEAD:main")[1])

    def test_old_state_put_on_top_with_reset_soft_is_locked(self):
        self.version(self.a, "1.0.1", {"tax.py": "mine\n"})                     # own work on the old main
        self.version(self.b, "1.0.1", {"app.js": "two\n"}); self.git(self.b, "push", "-q", "origin", "HEAD:main")
        self.version(self.b, "1.0.2", {"app.js": "three\n"}); self.git(self.b, "push", "-q", "origin", "HEAD:main")
        self.git(self.a, "fetch", "-q", "origin")
        self.git(self.a, "reset", "-q", "--soft", "origin/main")                  # the mistake: main moved under an old tree
        self.git(self.a, "commit", "-q", "-m", "1.0.1: mine")
        code, err = self.guard(self.a)
        self.assertEqual(code, 2)
        self.assertIn("nicht höher als 1.0.2", err); self.assertIn("fehlen Abschnitte, die davor da waren: 1.0.2", err)

    def test_older_tree_with_a_proper_chain_is_locked(self):
        # how 3.16.35 lost the code of 3.16.32: VERSION and CHANGELOG right, but the other files from before that version
        self.version(self.a, "1.0.1", {"tax.py": "mine and long enough\n"})
        self.version(self.b, "1.0.1", {"app.js": "one\nadded by the other chat\n"}); self.git(self.b, "push", "-q", "origin", "HEAD:main")
        self.git(self.a, "fetch", "-q", "origin")
        self.git(self.a, "reset", "-q", "--soft", "origin/main")                  # an older tree under the new main
        self.git(self.a, "checkout", "origin/main", "--", "VERSION", "CHANGELOG.md")  # its chain taken over: looks right
        self.version(self.a, "1.0.2", {"tax.py": "mine and long enough\n"})
        code, err = self.guard(self.a)
        self.assertEqual(code, 2); self.assertIn("app.js: added by the other chat", err)
        self.assertEqual(self.guard(self.a, "KONTOR_PUSH_OK=1 git push origin HEAD:main")[0], 0)   # a deliberate exception
        # built on main as it is (the other chat's line kept, own lines changed): may go
        self.git(self.a, "reset", "-q", "--hard", "origin/main")
        self.version(self.a, "1.0.2", {"tax.py": "mine and long enough\n", "app.js": "one\nadded by the other chat\nmine too, long\n"})
        self.assertEqual(self.guard(self.a), (0, ""))

    def test_reset_onto_a_commit_outside_the_own_history_is_locked(self):
        self.version(self.a, "1.0.1", {"tax.py": "mine and long enough\n"})
        self.version(self.b, "1.0.1", {"app.js": "one\nadded by the other chat\n"}); self.git(self.b, "push", "-q", "origin", "HEAD:main")
        self.git(self.a, "fetch", "-q", "origin")
        code, err = self.guard(self.a, "git reset --soft origin/main")         # an older tree under the newer main
        self.assertEqual(code, 2); self.assertIn("nicht in deiner Geschichte", err); self.assertIn("pull --rebase", err)
        self.assertEqual(self.guard(self.a, "git reset origin/main")[0], 2)     # mixed: the same
        self.assertEqual(self.guard(self.dir, "cd %s && git reset -q --soft origin/main" % self.a)[0], 2)
        self.assertEqual(self.guard(self.a, "git -C %s reset --soft FETCH_HEAD" % self.a)[0], 2)
        for ok in ("git reset --soft HEAD~1", "git reset --hard origin/main", "git reset -q HEAD tax.py", "git reset",
                   "git reset --keep origin/main", 'grep -n "git reset --soft origin/main" docs/rules/parallel.md'):
            self.assertEqual(self.guard(self.a, ok), (0, ""), ok)
        self.git(self.a, "reset", "-q", "--hard", "origin/main")                 # own commits on top of main: squashing may
        self.version(self.a, "1.0.2", {"tax.py": "x\n"}); self.version(self.a, "1.0.3", {"tax.py": "y\n"})
        self.assertEqual(self.guard(self.a, "git reset --soft origin/main"), (0, ""))

    def test_overview_condensed_by_the_next_version_may_go(self):
        # HIGHLIGHTS.md: a chat extends a point another chat's version just added -- rewritten on purpose, not an older tree
        self.version(self.b, "1.0.1", {"HIGHLIGHTS.md": "## 1.0\n- KI-Assistent: Diktieren und Diagramme\n"}); self.git(self.b, "push", "-q", "origin", "HEAD:main")
        self.git(self.a, "pull", "-q", "origin", "main")
        self.version(self.a, "1.0.2", {"HIGHLIGHTS.md": "## 1.0\n- KI-Assistent: Diktieren, Diagramme, Internetsuche\n"})
        self.assertEqual(self.guard(self.a), (0, ""))

    def test_not_on_the_newest_main_is_locked(self):
        self.version(self.a, "1.0.1", {"tax.py": "mine\n"})
        self.version(self.b, "1.0.1", {"app.js": "two\n"}); self.git(self.b, "push", "-q", "origin", "HEAD:main")
        code, err = self.guard(self.a)                                             # fetches main itself
        self.assertEqual(code, 2); self.assertIn("git pull --rebase origin main", err)

    def test_version_not_raised_is_locked(self):
        self.version(self.a, "1.0.0", {"app.js": "two\n"})
        code, err = self.guard(self.a)
        self.assertEqual(code, 2); self.assertIn("nicht höher als 1.0.0", err)
        self.git(self.a, "reset", "-q", "--hard", "origin/main")
        self.version(self.a, "1.0.10", {"app.js": "two\n"})                     # numbers, not text: 1.0.10 > 1.0.9 > 1.0.0
        self.assertEqual(self.guard(self.a)[0], 0)
        with open(os.path.join(self.a, "VERSION"), "w") as f:
            f.write("1.0.11\n")
        self.git(self.a, "commit", "-q", "-am", "1.0.11: no changelog")            # its section missing on top
        code, err = self.guard(self.a)
        self.assertEqual(code, 2); self.assertIn("passt nicht zu VERSION 1.0.11", err)

    def test_changelog_time_from_the_clock(self):
        # chats have no clock and guessed the time (3.17.30: 29 minutes ahead): never after the commit, at most 20 minutes before
        self.version(self.a, "1.0.1", {"app.js": "two\n"}, heading="2026-01-01 10:00", made="2026-01-01T09:30:00+01:00")
        code, err = self.guard(self.a)
        self.assertEqual(code, 2); self.assertIn("Uhrzeit im CHANGELOG 2026-01-01 10:00, Commit um 2026-01-01 09:30", err)
        self.assertNotIn("Versionskette", err)                                     # only the time, not a stale main
        self.git(self.a, "reset", "-q", "--hard", "origin/main")
        self.version(self.a, "1.0.1", {"app.js": "two\n"}, heading="2026-01-01 10:00", made="2026-01-01T10:40:00+01:00")
        self.assertEqual(self.guard(self.a)[0], 2)                                 # written long before the commit
        self.git(self.a, "reset", "-q", "--hard", "origin/main")
        self.version(self.a, "1.0.1", {"app.js": "two\n"}, heading="2026-01-01 10:00", made="2026-01-01T10:12:00+01:00")
        self.assertEqual(self.guard(self.a), (0, ""))                              # tests in between

    def test_chain_on_github(self):
        def chain(before, after):
            r = subprocess.run([sys.executable, GUARD, "chain", before, after], cwd=self.b, env=ENV, capture_output=True, text=True, timeout=60)
            return r.returncode, r.stdout + r.stderr
        good0 = self.git(self.b, "rev-parse", "HEAD")
        self.version(self.b, "1.0.1", {"app.js": "two\n"}); self.version(self.b, "1.0.2", {"app.js": "three\n"})
        good = self.git(self.b, "rev-parse", "HEAD")
        self.assertEqual(chain(good0, good)[0], 0)
        self.assertEqual(chain("0" * 40, good)[0], 0)                              # a new branch: its last commit
        self.version(self.b, "1.0.1", {"app.js": "four\n"}, keep=False)          # an old state on top
        code, out = chain(good, self.git(self.b, "rev-parse", "HEAD"))
        self.assertEqual(code, 2); self.assertIn("nicht höher als 1.0.2", out); self.assertIn("fehlen Abschnitte", out)
        code, out = chain(good, good0)                                             # main overwritten
        self.assertEqual(code, 2); self.assertIn("Force-Push", out)


RELEASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "tools", "release.py")
AFFECTED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "affected.py")


@unittest.skipUnless(shutil.which("git"), "git fehlt")
class ReleaseScript(unittest.TestCase):
    """.claude/tools/release.py on throwaway repositories (bare origin, chats as clones, the script, guard and affected.py
    copied in): one commit per version on the newest main, VERSION + 1 and the changelog section by the script, another
    chat's newer version taken in (rebased, next number) -- also when it lands between the check and the push --, a conflict
    stops with the files named, failing checks push nothing, VERSION/CHANGELOG by hand are refused."""

    def setUp(self):
        import importlib.util
        py = os.path.expanduser("~/kontor-venv/bin/python")
        py = py if os.path.exists(py) else sys.executable
        if subprocess.run([py, "-c", "import pyflakes, pytest"], capture_output=True).returncode != 0:
            self.skipTest("pyflakes/pytest fehlen")
        self.assertIsNotNone(importlib.util.find_spec("unittest"))
        self.dir = tempfile.mkdtemp(prefix="kontor-release-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.git(self.dir, "init", "-q", "--bare", "origin.git")
        self.git(os.path.join(self.dir, "origin.git"), "symbolic-ref", "HEAD", "refs/heads/main")
        seed = os.path.join(self.dir, "seed")
        self.git(self.dir, "clone", "-q", "origin.git", "seed"); self.git(seed, "checkout", "-q", "-B", "main")
        for rel, src in ((".claude/tools/release.py", RELEASE), (".claude/hooks/guard.py", GUARD), ("tests/affected.py", AFFECTED)):
            os.makedirs(os.path.dirname(os.path.join(seed, rel)), exist_ok=True)
            shutil.copy(src, os.path.join(seed, rel))
        self.write(seed, {".gitignore": "__pycache__/\n", "VERSION": "1.0.0\n", "CHANGELOG.md": "# Änderungen\n\n## 1.0.0 (2026-01-01 10:00)\n- Start: da\n",
                          "app.py": "A = 1\nB = 1\n", "tests/test_rules.py": "import app\n\ndef test_ok():\n    assert app.A == 1\n"})
        self.git(seed, "add", "-A"); self.git(seed, "commit", "-q", "-m", "1.0.0: start"); self.git(seed, "push", "-q", "origin", "HEAD:main")
        self.a, self.b = self.clone("a"), self.clone("b")

    def git(self, cwd, *args):
        r = subprocess.run(["git"] + list(args), cwd=cwd, env=ENV, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def clone(self, name):
        self.git(self.dir, "clone", "-q", "origin.git", name)
        return os.path.join(self.dir, name)

    def write(self, d, files):
        for name, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(d, name)) or d, exist_ok=True)
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(text)

    def release(self, d, *args, env=None):
        r = subprocess.run([sys.executable, os.path.join(d, ".claude", "tools", "release.py")] + list(args), cwd=d, env=dict(ENV, **(env or {})),
                           capture_output=True, text=True, timeout=300)
        return r.returncode, r.stdout + r.stderr

    def main_file(self, name):
        return self.git(os.path.join(self.dir, "origin.git"), "show", "main:" + name)

    def test_one_commit_per_version_and_the_faster_chat(self):
        self.write(self.a, {"app.py": "A = 1\nB = 2\n"})
        self.git(self.a, "commit", "-qam", "local step")                     # local steps are squashed into the one version
        self.write(self.a, {"new.txt": "x\n"})
        code, out = self.release(self.a, "B is two", "Bilanz: B zählt doppelt", "--by", "Claude X: https://claude.ai/code/session_01A")
        self.assertEqual(code, 0, out); self.assertIn("1.0.1 veröffentlicht", out)
        origin = os.path.join(self.dir, "origin.git")
        self.assertEqual(self.git(origin, "log", "--format=%s", "main").splitlines(), ["1.0.1: B is two", "1.0.0: start"])
        self.assertEqual(self.git(origin, "log", "-1", "--format=%b", "main"), "Claude X: https://claude.ai/code/session_01A")
        self.assertEqual(self.main_file("VERSION"), "1.0.1"); self.assertEqual(self.main_file("new.txt"), "x")
        self.assertRegex(self.main_file("CHANGELOG.md"), r"^# Änderungen\n\n## 1\.0\.1 \(\d{4}-\d\d-\d\d \d\d:\d\d\)\n- Bilanz: B zählt doppelt\n\n## 1\.0\.0")
        # chat b built on 1.0.0: taken onto 1.0.1, next number, both changes kept; --by kept from before is per clone
        self.write(self.b, {"other.txt": "y\n"})
        code, out = self.release(self.b, "other", "Entwicklung: y")
        self.assertEqual(code, 2, out); self.assertIn("--by", out)
        code, out = self.release(self.b, "other", "Entwicklung: y", "--by", "Claude Y: link")
        self.assertEqual(code, 0, out); self.assertIn("1.0.2 veröffentlicht", out)
        self.assertEqual(self.main_file("app.py"), "A = 1\nB = 2"); self.assertEqual(self.main_file("other.txt"), "y")
        self.assertIn("## 1.0.2", self.main_file("CHANGELOG.md").split("## 1.0.1")[0])
        # a version that lands between the check and the push (here: while the push hook runs): refused, taken in, next number
        c = self.clone("c")
        self.write(self.a, {".githooks/pre-push": "#!/bin/sh\n[ -e %s ] && exit 0\ntouch %s\ncd %s && %s %s faster 'Entwicklung: z' "
                            "--by 'Claude Z: l' >/dev/null 2>&1\nexit 0\n" % ((os.path.join(self.dir, "mark"),) * 2 + (c, sys.executable, os.path.join(c, ".claude", "tools", "release.py")))})
        os.chmod(os.path.join(self.a, ".githooks", "pre-push"), 0o755)
        self.write(c, {"z.txt": "z\n"})
        self.git(self.a, "pull", "-q", "--rebase", "origin", "main")
        self.write(self.a, {"w.txt": "w\n"})
        code, out = self.release(self.a, "w", "Entwicklung: w")
        self.assertEqual(code, 0, out); self.assertIn("schneller", out); self.assertIn("1.0.4 veröffentlicht", out)
        self.assertEqual(self.main_file("z.txt"), "z"); self.assertEqual(self.main_file("w.txt"), "w")
        self.assertEqual(self.git(os.path.join(self.dir, "origin.git"), "log", "--format=%s", "-3", "main").splitlines(),
                         ["1.0.4: w", "1.0.3: faster", "1.0.2: other"])

    def test_conflict_failing_checks_and_own_files_refused(self):
        self.write(self.a, {"app.py": "A = 1\nB = 3\n"})
        self.assertEqual(self.release(self.a, "three", "Bilanz: drei", "--by", "Claude X: l")[0], 0)
        self.write(self.b, {"app.py": "A = 1\nB = 4\n"})
        code, out = self.release(self.b, "four", "Bilanz: vier", "--by", "Claude Y: l")
        self.assertEqual(code, 3, out); self.assertIn("Konflikt", out); self.assertIn("app.py", out)
        self.git(self.b, "rebase", "--abort"); self.git(self.b, "reset", "-q", "--hard", "origin/main")
        self.write(self.b, {"app.py": "A = 2\nB = 3\n"})                      # breaks the test: nothing goes out
        code, out = self.release(self.b, "two", "Bilanz: zwei")
        self.assertEqual(code, 1, out); self.assertIn("Prüfung fehlgeschlagen", out); self.assertIn("test_ok", out)
        self.assertEqual(self.main_file("VERSION"), "1.0.1")
        self.assertEqual(self.release(self.b, "--check")[0], 1)
        self.write(self.b, {"app.py": "A = 1\nB = 3\nC = 1\n", "VERSION": "1.0.9\n"})
        code, out = self.release(self.b, "c", "Bilanz: c")
        self.assertEqual(code, 4, out); self.assertIn("schreibt nur dieses Skript", out)
        self.git(self.b, "checkout", "origin/main", "--", "VERSION")
        self.assertEqual(self.release(self.b, "--check")[0], 0)
        code, out = self.release(self.b, "c", "ohne Bezug")
        self.assertEqual(code, 2, out); self.assertIn("Bezug", out)

    def test_recent_lines_changed_on_purpose_and_lost_in_a_conflict(self):
        # a line of the version just before, changed on purpose (it was in the main the work was built on): may go, named
        self.write(self.a, {"app.py": "A = 1\nB = 1\nLABEL = 'eins'\n"})
        self.assertEqual(self.release(self.a, "eins", "Bilanz: eins", "--by", "Claude X: l")[0], 0)
        self.git(self.b, "pull", "-q", "--rebase", "origin", "main")
        self.write(self.b, {"app.py": "A = 1\nB = 1\nLABEL = 'zwei'\n"})
        code, out = self.release(self.b, "zwei", "Bilanz: zwei", "--by", "Claude Y: l")
        self.assertEqual(code, 0, out); self.assertIn("Bewusst geändert: 1 Zeile(n) aus 1.0.1", out); self.assertIn("1.0.2 veröffentlicht", out)
        # chat a, still on 1.0.1, changes the same line: Git shows the conflict, naming the newer version and the own start
        self.write(self.a, {"app.py": "A = 1\nB = 1\nLABEL = 'drei'\n"})
        code, out = self.release(self.a, "drei", "Bilanz: drei")
        self.assertEqual(code, 3, out); self.assertIn("beruht auf 1.0.1", out); self.assertIn("app.py: 1.0.2: zwei", out)
        self.assertIn("neuere, schon veröffentlichte Stand", out)
        # resolved by keeping only its own side: the newer version's line is lost -- locked, nothing goes out
        self.write(self.a, {"app.py": "A = 1\nB = 1\nLABEL = 'drei'\n"})
        self.git(self.a, "add", "app.py")
        subprocess.run(["git", "rebase", "--continue"], cwd=self.a, env=dict(ENV, GIT_EDITOR="true"), check=True, capture_output=True)
        code, out = self.release(self.a, "drei", "Bilanz: drei")
        self.assertEqual(code, 4, out); self.assertIn("erst nach deinem Ausgangsstand 1.0.1", out); self.assertIn("1.0.2 app.py: LABEL = 'zwei'", out)
        self.assertEqual(self.main_file("VERSION"), "1.0.2")
        # weighed, and its change replaces the other on purpose: said so, then it goes
        code, out = self.release(self.a, "drei", "Bilanz: drei", env={"KONTOR_PUSH_OK": "1"})
        self.assertEqual(code, 0, out); self.assertIn("der Nutzer hat zugestimmt", out); self.assertIn("1.0.3 veröffentlicht", out)
        self.assertEqual(self.main_file("app.py"), "A = 1\nB = 1\nLABEL = 'drei'")
        self.assertFalse(os.path.exists(os.path.join(self.a, ".git", "kontor-seen")))
        # both kept instead: no lock, no exception needed
        self.git(self.b, "pull", "-q", "--rebase", "origin", "main")
        self.write(self.a, {"app.py": "A = 1\nB = 1\nLABEL = 'drei'\nNOTE = 'vier'\n"})
        self.write(self.b, {"app.py": "A = 1\nB = 1\nLABEL = 'drei und fünf'\n"})
        self.assertEqual(self.release(self.b, "fünf", "Bilanz: fünf")[0], 0)
        code, out = self.release(self.a, "vier", "Bilanz: vier")
        self.assertEqual(code, 3, out)
        self.write(self.a, {"app.py": "A = 1\nB = 1\nLABEL = 'drei und fünf'\nNOTE = 'vier'\n"})
        self.git(self.a, "add", "app.py")
        subprocess.run(["git", "rebase", "--continue"], cwd=self.a, env=dict(ENV, GIT_EDITOR="true"), check=True, capture_output=True)
        code, out = self.release(self.a, "vier", "Bilanz: vier")
        self.assertEqual(code, 0, out); self.assertEqual(self.main_file("app.py"), "A = 1\nB = 1\nLABEL = 'drei und fünf'\nNOTE = 'vier'")

    def test_a_long_line_both_changed_merged_goes_without_exception(self):
        """A paragraph of text is one line: two chats change different parts of it. Merged with both parts, nothing of the other
        chat is lost -- it goes without KONTOR_PUSH_OK (3.17.65 needed it); the other chat's words left out: locked."""
        line = "TEXT = 'Kürzel: ⌘K blendet ein, ⌘S speichert, ⌘F sucht in der Hilfe, ⌘P druckt.%s'\n"
        self.write(self.a, {"app.py": "A = 1\nB = 1\n" + line % ""})
        self.assertEqual(self.release(self.a, "eins", "Hilfe: eins", "--by", "Claude X: l")[0], 0)
        self.git(self.b, "pull", "-q", "--rebase", "origin", "main")
        self.write(self.b, {"app.py": "A = 1\nB = 1\n" + line % " Esc schließt, was offen ist."})
        self.assertEqual(self.release(self.b, "esc", "Hilfe: esc", "--by", "Claude Y: l")[0], 0)
        mine = line.replace("sucht in der Hilfe", "sucht Wort für Wort in der Hilfe")
        self.write(self.a, {"app.py": "A = 1\nB = 1\n" + mine % ""})
        code, out = self.release(self.a, "suche", "Hilfe: suche")
        self.assertEqual(code, 3, out)
        # resolved by keeping only its own side: the other chat's sentence is gone -- locked
        self.write(self.a, {"app.py": "A = 1\nB = 1\n" + mine % ""})
        self.git(self.a, "add", "app.py")
        subprocess.run(["git", "rebase", "--continue"], cwd=self.a, env=dict(ENV, GIT_EDITOR="true"), check=True, capture_output=True)
        code, out = self.release(self.a, "suche", "Hilfe: suche")
        self.assertEqual(code, 4, out); self.assertIn("1.0.2 app.py: TEXT", out); self.assertIn("Zustimmung des Nutzers", out)
        # both parts in the line: goes, no exception
        self.write(self.a, {"app.py": "A = 1\nB = 1\n" + mine % " Esc schließt, was offen ist."})
        code, out = self.release(self.a, "suche", "Hilfe: suche")
        self.assertEqual(code, 0, out); self.assertNotIn("KONTOR_PUSH_OK", out)
        self.assertEqual(self.main_file("app.py"), "A = 1\nB = 1\n" + (mine % " Esc schließt, was offen ist.").rstrip("\n"))


class AddedParts(unittest.TestCase):
    """What a version put into a line, as the lock looks for it in the work pushed (guard._added_parts)."""

    def test_parts(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("guard", GUARD)
        g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
        self.assertEqual(g._added_parts([], "a brand new line"), ["a brand new line"])                         # new: all of it
        self.assertEqual(g._added_parts(["MINUTES = 30  # idle"], "MINUTES = 45  # idle"), ["MINUTES = 45  # idle"])   # a figure: with words around it
        self.assertEqual(g._added_parts(["x = 1"], "something else entirely, long"), ["something else entirely, long"])  # not alike: a new line
        long = "Kontor liest die Daten aus MoneyMoney und rechnet daraus die Bilanz je Bereich"
        self.assertEqual(g._added_parts([long], long + " und den Cashflow."), ["Bereich und den Cashflow."])
        self.assertEqual(g._added_parts([long], long.replace("die Daten ", "")), ["Kontor liest aus MoneyMoney"])    # taken out: the words that meet


if __name__ == "__main__":
    unittest.main()
