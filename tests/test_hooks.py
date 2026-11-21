"""The briefing every chat gets about the other chats' work (.claude/hooks/briefing.py), on throwaway repositories:
it lists what is new on main, fast-forwards only a clone with nothing of its own, names overlapping files, and stays
silent while nothing changed."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "hooks", "briefing.py")
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
        with open(os.path.join(d, ".git", "info", "exclude"), "a") as f:
            f.write(".claude/\n")
        return d

    def publish(self, d, version, subject, files):
        for name, text in dict(files, VERSION=version + "\n", **{"CHANGELOG.md": version + "\n"}).items():
            os.makedirs(os.path.dirname(os.path.join(d, name)) or d, exist_ok=True)
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        self.git(d, "add", "-A")
        self.git(d, "commit", "-q", "-m", "%s: %s" % (version, subject), "-m", "Claude Test: https://claude.ai/code/session_01ABCDwxyz")
        self.git(d, "push", "-q", "origin", "HEAD:main")

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

    def test_never_fails_outside_a_repository(self):
        d = os.path.join(self.dir, "plain"); os.makedirs(os.path.join(d, ".claude", "hooks"))
        shutil.copy(HOOK, os.path.join(d, ".claude", "hooks", "briefing.py"))
        r = subprocess.run([sys.executable, os.path.join(d, ".claude", "hooks", "briefing.py"), "hook"], cwd=d,
                           env=dict(ENV, GIT_CEILING_DIRECTORIES=self.dir), input="", capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
