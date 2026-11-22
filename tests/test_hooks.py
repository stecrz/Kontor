"""The briefing every chat gets about the other chats' work (.claude/hooks/briefing.py) and the push checks
(.githooks/pre-push, which the briefing turns on, and the guard before every push, .claude/hooks/guard.py), on throwaway
repositories: it lists what is new on main, fast-forwards only a clone with nothing of its own, names overlapping files,
stays silent while nothing changed -- and a version squashed onto a stale main is refused."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

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
        # a red version: its chat fixes it
        line, key = self.summary([self.run_("ccc", "3.1.4: c", ok=False), self.run_("bbb", "3.1.3: b", ok=False), self.run_("aaa", "3.1.2: a")], [])
        self.assertIn("ROT seit 3.1.3 (Chat …ABCD)", line); self.assertEqual(key, "red bbb")

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


GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "hooks", "guard.py")


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

    def version(self, d, v, files, keep=True):
        """One version: its files, VERSION and a changelog section on top (keep: the sections before it stay)."""
        old = open(os.path.join(d, "CHANGELOG.md")).read().split("\n", 2)[2] if keep and os.path.exists(os.path.join(d, "CHANGELOG.md")) else ""
        for name, text in dict(files, VERSION=v + "\n", **{"CHANGELOG.md": "# Änderungen\n\n## %s (2026-01-01 10:00)\n- %s\n\n%s" % (v, v, old)}).items():
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        self.git(d, "add", "-A")
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


if __name__ == "__main__":
    unittest.main()
