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
