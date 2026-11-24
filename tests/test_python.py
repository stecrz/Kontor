"""Kontor's own Python (pyboot.py, pyruntime.py, pyselftest.py): the one file named is loaded, checked, compared with what was
unpacked and tried before anything is switched -- and whatever fails, at any step or at any later start, the service goes on
in the Python it was started with. All with stand-ins: an archive made here whose "Python" is a small script handing over to
the Python that runs the tests; nothing is fetched. Where the real build for this machine lies at hand (KONTOR_PYTHON_ARCHIVE:
its file as python-build-standalone publishes it), the same with that."""
import ast
import glob
import hashlib
import http.cookiejar
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import llm_local as L      # noqa: E402
import pyboot              # noqa: E402
import pyruntime as R      # noqa: E402
from i18n import tr        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = "%d.%d.%d" % sys.version_info[:3]
NAME = "cpython-%s-%s" % (NOW, "20990101")
# what the stand-in "Python" of a build does when it is run
OK = '#!/bin/sh\n[ -e "$(dirname "$0")/broken" ] && exit 9\nexec "%s" "$@"\n' % sys.executable        # (a file "broken" beside it: damaged later)
DEAD = "#!/bin/sh\nexit 3\n"
NO_KONTOR = '#!/bin/sh\ncase "$*" in *pyselftest*) echo "no such part" >&2; exit 1;; esac\nexec "%s" "$@"\n' % sys.executable


def archive(script: str = OK, more: tuple = ()) -> bytes:
    """A build as python-build-standalone packs it, in small: python/bin/python3.x (here: a script), the link python3 to it,
    a few files of a library. more: further entries (TarInfo, content)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        def put(name, data, mode=0o644):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            t.addfile(info, io.BytesIO(data))
        put("python/bin/python3.13", script.encode(), 0o775)
        link = tarfile.TarInfo("python/bin/python3")
        link.type, link.linkname = tarfile.SYMTYPE, "python3.13"
        t.addfile(link)
        put("python/lib/python3.13/os.py", b"# a library file\n" * 50)
        put("python/lib/python3.13/LICENSE.txt", b"made up\n")
        for info, data in more:
            t.addfile(info, io.BytesIO(data) if data is not None else None)
    return buf.getvalue()


class Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Net:
    """GitHub, as far as Kontor's own Python asks it: the one file -- or what stands in for a download gone wrong."""

    def __init__(self, data: bytes):
        self.data, self.calls, self.error, self.slow = data, [], None, None

    def open(self, url, kind, headers=None, timeout=30):
        if not L.host_allowed(url, kind):
            raise ValueError("address not allowed: " + url)
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        r = Resp(self.data)
        if self.slow is not None:                       # a download that takes its time (to cancel it)
            ev, inner = self.slow, r.read

            def read(n=-1):
                ev.wait(5)
                return inner(64)
            r.read = read
        return r


class Build:
    """One made-up build named in pyruntime as the one for this machine, and the net that hands it out."""

    def __init__(self, script: str = OK, data: bytes = None, served: bytes = None):
        self.data = archive(script) if data is None else data
        self.net = Net(self.data if served is None else served)
        self.keep = (R.FILES, R.VERSION, R.BUILD, L._open)

    def __enter__(self):
        R.FILES = {L.asset_tag(): {"file": "cpython-%s+20990101-test-install_only_stripped.tar.gz" % NOW, "size": len(self.data),
                                   "sha256": hashlib.sha256(self.data).hexdigest()}}
        R.VERSION, R.BUILD, L._open = NOW, "20990101", self.net.open
        return self

    def __exit__(self, *a):
        R.FILES, R.VERSION, R.BUILD, L._open = self.keep


def wait(rt, seconds=120.0):
    t0 = time.time()
    while rt.job and rt.job["state"] == "running" and time.time() - t0 < seconds:
        time.sleep(0.02)
    return rt.job_view()


def tree(root):
    """Everything in a folder, as names."""
    return sorted(os.path.relpath(os.path.join(d, n), root) for d, ds, fs in os.walk(root) for n in ds + fs)


def put_build(here, script=OK, name=NAME, state=True):
    """A build unpacked in a program folder as the job leaves it (without the job), named in the state file."""
    b = os.path.join(pyboot.folder(here), name, "python", "bin")
    os.makedirs(b)
    with open(os.path.join(b, "python3.13"), "w") as f:
        f.write(script)
    os.chmod(os.path.join(b, "python3.13"), 0o755)
    os.symlink("python3.13", os.path.join(b, "python3"))
    if state:
        pyboot.write_state(here, {"use": "own", "dir": name, "version": NOW, "build": "20990101"})
    return os.path.join(b, "python3.13")


# a stand-in for kontor.py: what the starter runs. It does what the file "mode" says and notes every run in "runs"
SERVICE = '''import os, signal, sys, time
sys.path.insert(0, %r)
import pyboot
HERE = os.path.dirname(os.path.abspath(__file__))
pyboot.START_SECONDS = float(os.environ.get("T_START") or 120)
pyboot.RETRY_SECONDS = float(os.environ.get("T_RETRY") or 0.2)
pyboot.start(HERE, sys.argv)
mode = open(os.path.join(HERE, "mode")).read().strip()
def say(*words):
    with open(os.path.join(HERE, "runs"), "a") as f:
        f.write(" ".join(str(w) for w in (os.getpid(), os.getppid()) + words) + "\\n")
if not pyboot.starter():
    if mode.endswith("both"):            # this Python does not get Kontor to serve either
        say("base-ends")
        sys.exit(2)
    pyboot.serves()
    say("base", "|".join(pyboot.notes))
    sys.exit(0)
say("own", mode, " ".join(sys.argv[1:]), sys.flags.isolated, sys.flags.no_site)
if mode == "crash":
    sys.exit(3)
if mode == "hang":
    time.sleep(600)
pyboot.ready(); pyboot.ready()
pyboot.watch()
if mode.startswith("early"):             # Kontor's parts are loaded, and yet it ends before it serves
    if mode.endswith("once"):            # (only this time: the next try serves)
        open(os.path.join(HERE, "mode"), "w").write("exit 0")
    sys.exit(int(mode.split()[1]))
pyboot.serves(); pyboot.serves()
if mode.startswith("exit"):
    sys.exit(int(mode.split()[1]))
if mode == "again":                      # asks once to be started anew
    open(os.path.join(HERE, "mode"), "w").write("exit 0")
    sys.exit(pyboot.EX_RESTART)
if mode == "back":                       # the Mac's Python is to serve from the next start
    st = pyboot.read_state(HERE); st["use"] = "apple"; pyboot.write_state(HERE, st)
    sys.exit(pyboot.EX_RESTART)
if mode == "uninstall":
    open(os.path.join(pyboot.folder(HERE), pyboot.REMOVE), "w").write(os.environ.get("T_WHOLE") or "")
    sys.exit(0)
def term(*a):
    say("term")
    sys.exit(0)
signal.signal(signal.SIGTERM, term)
say("serving")
while True:
    time.sleep(0.1)
''' % ROOT


class Starter(unittest.TestCase):
    """pyboot.py: which Python runs the service is decided at every start; the own one runs it as the starter's child, and
    whatever it does, the starter is there -- it serves itself when the own one does not get Kontor running."""

    def setUp(self):
        self.here = os.path.realpath(tempfile.mkdtemp(prefix="kontor-boot-"))
        with open(os.path.join(self.here, "kontor.py"), "w") as f:
            f.write(SERVICE)
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
        shutil.rmtree(self.here, ignore_errors=True)

    def mode(self, text):
        with open(os.path.join(self.here, "mode"), "w") as f:
            f.write(text)

    def runs(self):
        try:
            with open(os.path.join(self.here, "runs")) as f:
                return [line.split(None, 3) for line in f.read().splitlines()]
        except OSError:
            return []

    def start(self, wait=True, env=None, seconds=60):
        p = subprocess.Popen([sys.executable, os.path.join(self.here, "kontor.py"), "--quiet", "start"], env=dict(os.environ, **(env or {})),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.procs.append(p)
        if wait:
            p.wait(seconds)
        return p

    def until(self, what, seconds=30.0):
        t0 = time.time()
        while time.time() - t0 < seconds:
            if what():
                return
            time.sleep(0.05)
        self.fail("not reached; runs: %r" % self.runs())

    def test_nothing_chosen_the_starters_python_serves(self):
        self.mode("exit 0")
        p = self.start()
        self.assertEqual(p.returncode, 0)
        self.assertEqual([r[2] for r in self.runs()], ["base"])
        self.assertEqual(self.runs()[0][0], str(p.pid))                      # this very process
        self.assertFalse(os.path.exists(pyboot.folder(self.here)))          # and nothing is written
        # a state file that does not read, or that says nothing: the same
        os.makedirs(pyboot.folder(self.here))
        for text in ("{", "[]", '{"use": "apple", "dir": "%s"}' % NAME, '{"use": "own"}'):
            with open(os.path.join(pyboot.folder(self.here), pyboot.STATE), "w") as f:
                f.write(text)
            self.assertEqual(self.start().returncode, 0, text)
        self.assertEqual({r[2] for r in self.runs()}, {"base"})

    def test_the_own_python_runs_the_service_as_the_starters_child(self):
        put_build(self.here)
        self.mode("exit 7")
        p = self.start()
        self.assertEqual(p.returncode, 7)                                    # the service's end is the starter's
        (pid, ppid, kind, rest), = self.runs()
        self.assertEqual((kind, ppid), ("own", str(p.pid))); self.assertNotEqual(pid, str(p.pid))
        self.assertEqual(rest, "exit 7 --quiet start 1 1")                   # the same words, alone (-I) and without other packages (-S)
        self.assertNotIn("failed", pyboot.read_state(self.here))

    def test_it_does_not_start_the_starters_python_serves_at_once(self):
        put_build(self.here)
        self.mode("crash")
        p = self.start()
        self.assertEqual(p.returncode, 0)
        runs = self.runs()
        self.assertEqual([r[2] for r in runs], ["own", "base"])
        self.assertEqual(runs[1][0], str(p.pid))                             # the starter itself, in this very start
        self.assertIn("did not start (start: exit 3)", runs[1][3])
        st = pyboot.read_state(self.here)
        self.assertEqual((st["failed"]["why"], st["failed"]["detail"], st["use"]), ("start", "exit 3", "own"))
        self.assertEqual(pyboot.chosen(self.here), "")
        self.start()                                                         # the next start does not try it again
        self.assertEqual([r[2] for r in self.runs()], ["own", "base", "base"])
        self.assertEqual(self.runs()[2][3:], [])                             # ... and has nothing to say

    def test_it_ends_before_it_serves_noted_only_when_the_starters_python_gets_further(self):
        put_build(self.here)
        self.mode("early 3")                                                 # Kontor's parts loaded in it, then it ends -- and again at the one further try
        p = self.start()
        self.assertEqual(p.returncode, 0)
        runs = self.runs()
        self.assertEqual([r[2] for r in runs], ["own", "own", "base"]); self.assertEqual(runs[2][0], str(p.pid))      # the starter serves, in this very start
        self.assertIn("did not start (ended: exit 3)", runs[2][3])
        st = pyboot.read_state(self.here)
        self.assertEqual((st["failed"]["why"], st["failed"]["detail"], st["use"]), ("ended", "exit 3", "own"))
        # the starter's Python does not get Kontor to serve either (its address taken, Kontor already running): that was
        # nothing of the own Python's -- not noted, and the next start tries it again
        shutil.rmtree(pyboot.folder(self.here)); put_build(self.here)
        os.remove(os.path.join(self.here, "runs"))
        self.mode("early 4 both")
        p = self.start()
        self.assertEqual(p.returncode, 2)
        self.assertEqual([r[2] for r in self.runs()], ["own", "own", "base-ends"])
        self.assertNotIn("failed", pyboot.read_state(self.here))
        self.mode("exit 0")
        self.assertEqual(self.start().returncode, 0)
        self.assertEqual([r[2] for r in self.runs()], ["own", "own", "base-ends", "own"])
        self.assertNotIn("failed", pyboot.read_state(self.here))
        # after a restart the service that ran before may hold Kontor's address a moment longer: the one further try serves --
        # in its own Python, nothing noted, the starter's Python never asked
        os.remove(os.path.join(self.here, "runs"))
        self.mode("early 2 once")
        t0 = time.time()
        p = self.start(env={"T_RETRY": "1"})
        self.assertEqual(p.returncode, 0); self.assertGreaterEqual(time.time() - t0, 1)
        self.assertEqual([r[2] for r in self.runs()], ["own", "own"])
        self.assertNotIn("failed", pyboot.read_state(self.here))

    def test_damaged_gone_or_hanging(self):
        exe = put_build(self.here)
        self.mode("exit 0")
        for damage, why in ((lambda: open(os.path.join(os.path.dirname(exe), "broken"), "w").close(), "start"),       # ends at once
                            (lambda: os.chmod(exe, 0o644), "missing"),                                                 # no program any more
                            (lambda: os.remove(exe), "missing"),
                            (lambda: shutil.rmtree(os.path.join(pyboot.folder(self.here), NAME)), "missing")):
            shutil.rmtree(pyboot.folder(self.here)); put_build(self.here)
            if os.path.exists(os.path.join(self.here, "runs")):
                os.remove(os.path.join(self.here, "runs"))
            damage()
            self.assertEqual(self.start().returncode, 0)
            self.assertEqual(self.runs()[-1][2], "base", why)
            self.assertEqual(pyboot.read_state(self.here)["failed"]["why"], why)
        # it starts but never gets Kontor's parts loaded: ended after a while, the starter serves
        shutil.rmtree(pyboot.folder(self.here)); put_build(self.here)
        self.mode("hang")
        t0 = time.time()
        p = self.start(env={"T_START": "1.5"})
        self.assertEqual(p.returncode, 0); self.assertLess(time.time() - t0, 30)
        self.assertEqual(pyboot.read_state(self.here)["failed"]["why"], "slow")
        self.assertEqual([r[2] for r in self.runs()][-2:], ["own", "base"])
        self.assertEqual(subprocess.run(["pgrep", "-f", self.here], capture_output=True).stdout, b"")      # nothing of it left

    def test_a_restart_goes_through_the_starter(self):
        put_build(self.here)
        self.mode("again")
        p = self.start()
        self.assertEqual(p.returncode, 0)
        runs = self.runs()
        self.assertEqual([r[2] for r in runs], ["own", "own"])
        self.assertEqual({r[1] for r in runs}, {str(p.pid)})                 # the starter anew: the same process (launchd notices nothing)
        self.assertNotEqual(runs[0][0], runs[1][0])
        # back to the Mac's Python: the service says so and ends; the starter decides anew and serves itself
        os.remove(os.path.join(self.here, "runs"))
        self.mode("back")
        p = self.start()
        self.assertEqual(p.returncode, 0)
        runs = self.runs()
        self.assertEqual([r[2] for r in runs], ["own", "base"]); self.assertEqual(runs[1][0], str(p.pid))
        self.assertEqual(runs[1][3:], [])                                    # nothing failed
        self.assertNotIn("failed", pyboot.read_state(self.here))

    def test_ended_from_outside_and_a_starter_that_is_gone(self):
        put_build(self.here)
        self.mode("serve")
        p = self.start(wait=False)
        self.until(lambda: any(r[2:] == ["serving"] for r in self.runs()))
        p.send_signal(signal.SIGTERM)                                         # launchd ends Kontor: the service is told, the starter waits for it
        self.assertEqual(p.wait(20), 0)
        self.assertTrue(any(r[2:] == ["term"] for r in self.runs()))
        self.assertNotIn("failed", pyboot.read_state(self.here))
        # the starter is killed: the service ends by itself (it would keep Kontor's address to itself)
        os.remove(os.path.join(self.here, "runs"))
        p = self.start(wait=False)
        self.until(lambda: any(r[2:] == ["serving"] for r in self.runs()))
        child = int(self.runs()[0][0])
        p.kill(); p.wait(10)

        def gone():                                                           # (ended; whoever has to collect it may take its time)
            st = subprocess.run(["ps", "-o", "stat=", "-p", str(child)], capture_output=True, text=True).stdout.strip()
            return not st or st.startswith("Z")
        self.until(gone, 20)
        self.assertTrue(any(r[2:] == ["term"] for r in self.runs()))

    def test_ended_before_it_was_ready_is_no_failure_when_kontor_was_ended(self):
        put_build(self.here)
        self.mode("hang")
        p = self.start(wait=False)
        self.until(lambda: len(self.runs()) == 1)
        p.send_signal(signal.SIGTERM)
        self.assertEqual(p.wait(20), 0)
        self.assertNotIn("failed", pyboot.read_state(self.here))
        self.assertEqual([r[2] for r in self.runs()], ["own"])                # ... and the starter does not serve then

    def test_an_uninstall_leaves_the_folder_to_the_starter(self):
        put_build(self.here)
        self.mode("uninstall")
        self.assertEqual(self.start().returncode, 0)
        self.assertFalse(os.path.exists(pyboot.folder(self.here)))           # gone once nothing runs from it
        self.assertTrue(os.path.exists(os.path.join(self.here, "kontor.py")))
        # with the program folder, when the uninstall took everything else of it
        put_build(self.here)
        for name in ("mode", "runs"):
            os.rename(os.path.join(self.here, name), os.path.join(self.here, pyboot.FOLDER, name))
        with open(os.path.join(self.here, "kontor.py"), "w") as f:
            f.write(SERVICE.replace('os.path.join(HERE, "mode")', 'os.path.join(HERE, ".python", "mode")').replace('os.path.join(HERE, "runs")', 'os.path.join(HERE, ".python", "runs")')
                    .replace('open(os.path.join(pyboot.folder(HERE), pyboot.REMOVE), "w").write(os.environ.get("T_WHOLE") or "")',
                             'open(os.path.join(pyboot.folder(HERE), pyboot.REMOVE), "w").write("program"); os.remove(__file__)'))
        self.assertEqual(self.start().returncode, 0)
        self.assertFalse(os.path.exists(self.here))

    def test_only_a_program_really_inside_kontors_folder(self):
        exe = put_build(self.here)
        self.assertEqual(pyboot.exe_in(self.here, NAME), exe)
        self.assertEqual(pyboot.chosen(self.here), exe)
        for name in ("", None, 7, "..", "../x", "cpython-1/../..", "/tmp", "cpython-", "python", NAME + "/python", "cpython-1 x"):
            self.assertEqual(pyboot.exe_in(self.here, name), "", name)
        outside = tempfile.mkdtemp(prefix="kontor-out-")
        try:
            other = put_build(outside, name="cpython-9")
            os.symlink(os.path.join(pyboot.folder(outside), "cpython-9"), os.path.join(pyboot.folder(self.here), "cpython-9"))     # a folder that leads elsewhere
            self.assertEqual(pyboot.exe_in(self.here, "cpython-9"), "")
            put_build(self.here, name="cpython-8", state=False)
            link = os.path.join(pyboot.folder(self.here), "cpython-8", "python", "bin", "python3")
            os.remove(link); os.symlink(other, link)                                                                                  # a program that leads elsewhere
            self.assertEqual(pyboot.exe_in(self.here, "cpython-8"), "")
            self.assertTrue(pyboot.inside(self.here, exe)); self.assertFalse(pyboot.inside(self.here, other))
            self.assertFalse(pyboot.inside(self.here, link)); self.assertFalse(pyboot.inside(self.here, ""))
            # the whole folder a link to elsewhere: nothing of it counts
            shutil.rmtree(pyboot.folder(self.here)); os.symlink(pyboot.folder(outside), pyboot.folder(self.here))
            self.assertEqual(pyboot.exe_in(self.here, "cpython-9"), "")
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_small_things(self):
        self.assertTrue(pyboot.is_start(["--quiet", "start"])); self.assertTrue(pyboot.is_start(["start"]))
        for args in ([], ["--quiet"], ["install"], ["--quiet", "uninstall", "start"], ["version"]):
            self.assertFalse(pyboot.is_start(args), args)
        self.assertEqual(pyboot.launch_python(self.here), sys.executable)
        exe = put_build(self.here)
        with mock.patch.object(pyboot, "running", lambda: exe):              # launchd never starts Kontor's own Python itself
            self.assertEqual(pyboot.launch_python(self.here), "/usr/bin/python3")
        self.assertEqual(os.listdir(pyboot.folder(self.here)).count(pyboot.STATE + ".tmp"), 0)
        with mock.patch.dict(os.environ, {pyboot.ENV_STARTER: "x"}):
            self.assertEqual(pyboot.starter(), 0)
        with mock.patch.dict(os.environ, {pyboot.ENV_STARTER: "4711"}):
            self.assertEqual(pyboot.starter(), 4711)
        self.assertEqual(pyboot.starter(), 0)

    def test_the_start_runs_with_python_3_9_and_loads_nothing_of_kontor(self):
        """The Mac's own Python (3.9) starts Kontor, whatever the rest of the program needs one day: kontor.py and pyboot.py
        keep to what 3.9 reads, and pyboot.py loads only the standard library."""
        own = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(ROOT, "*.py"))}
        for name in ("pyboot.py", "kontor.py"):
            with open(os.path.join(ROOT, name), encoding="utf-8") as f:
                src = f.read()
            t = ast.parse(src, feature_version=(3, 9))
            if name == "pyboot.py":
                mods = {a.name.split(".")[0] for n in ast.walk(t) if isinstance(n, ast.Import) for a in n.names} | {
                    (n.module or "").split(".")[0] for n in ast.walk(t) if isinstance(n, ast.ImportFrom)}
                self.assertEqual(mods & own, set())
                self.assertEqual(mods - {"__future__", "json", "os", "re", "shutil", "signal", "subprocess", "sys", "threading", "time"}, set())
        # in kontor.py the start comes before any other part of Kontor is loaded
        with open(os.path.join(ROOT, "kontor.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertLess(src.index("pyboot.start(HERE, sys.argv)"), src.index("import access"))


class Loading(unittest.TestCase):
    """pyruntime.py: exactly the file named is loaded; another size or content, an archive that is not a build, a Python that
    does not start, does not load Kontor or is another version -- nothing is switched and nothing of it stays. Back, forth
    again, removed."""

    def setUp(self):
        self.here = os.path.realpath(tempfile.mkdtemp(prefix="kontor-py-"))
        self.rt = R.Runtime(self.here)
        self.switched = []
        self.rt.on_switch = lambda: self.switched.append(1)

    def tearDown(self):
        shutil.rmtree(self.here, ignore_errors=True)

    def left(self):
        """What a failed try leaves in the folder: nothing."""
        root = pyboot.folder(self.here)
        return tree(root) if os.path.isdir(root) else []

    def fails(self, text, **build):
        with Build(**build) as b:
            self.rt.install()
            job = wait(self.rt)
        self.assertEqual(job["state"], "error", job)
        self.assertIn(text, job["text"])
        self.assertEqual(self.left(), []); self.assertEqual(self.switched, [])
        self.assertEqual(pyboot.read_state(self.here), {}); self.assertEqual(pyboot.chosen(self.here), "")
        return b

    def test_loaded_checked_tried_switched(self):
        st = self.rt.status()
        self.assertEqual((st["use"], st["loaded"], st["failed"], st["restart"], st["job"]), ("", None, None, False, None))
        with Build() as b:
            self.assertEqual(self.rt.status()["offered"], {"version": NOW, "build": "20990101", "size": len(b.data)})
            self.rt.install()
            with self.assertRaises(ValueError):                     # one at a time
                self.rt.install()
            self.assertEqual(wait(self.rt)["state"], "done", self.rt.job)
            st = self.rt.status()
        # only the one file named, from GitHub
        self.assertEqual(b.net.calls, ["https://github.com/astral-sh/python-build-standalone/releases/download/20990101/cpython-%s%%2B20990101-test-install_only_stripped.tar.gz" % NOW])
        exe = os.path.join(pyboot.folder(self.here), NAME, "python", "bin", "python3.13")
        self.assertEqual(pyboot.chosen(self.here), exe)
        self.assertEqual(sorted(os.listdir(pyboot.folder(self.here))), [NAME, pyboot.STATE])            # the archive and what was beside it are gone
        self.assertEqual(os.stat(exe).st_mode & 0o777, 0o755)                                           # (not as the archive has it: writable by others)
        self.assertEqual(os.stat(os.path.join(pyboot.folder(self.here), NAME, "python", "lib", "python3.13", "os.py")).st_mode & 0o777, 0o644)
        state = pyboot.read_state(self.here)
        self.assertEqual({k: state[k] for k in ("use", "dir", "version", "build", "sha256")},
                         {"use": "own", "dir": NAME, "version": NOW, "build": "20990101", "sha256": hashlib.sha256(b.data).hexdigest()})
        self.assertEqual((st["use"], st["loaded"]["version"], st["newer"], st["failed"]), ("own", NOW, False, None))
        self.assertTrue(st["restart"])                               # chosen, not yet what runs: the service starts anew
        self.assertEqual(self.switched, [1])
        self.assertEqual(glob.glob(os.path.join(ROOT, "__pycache__", "pyselftest*")), [])              # trying it writes nothing beside Kontor's files

    def test_not_the_file_named(self):
        good = archive()
        other = archive(OK + "# one line more\n")
        self.fails(tr("s_ki_pruefsumme"), data=good, served=other)                       # another content
        self.fails(tr("s_ki_pruefsumme"), data=good, served=good[:-1] + bytes([good[-1] ^ 1]))       # one bit
        self.fails(tr("s_ki_pruefsumme"), data=good, served=good[:len(good) // 2])       # cut off on the way
        self.fails(tr("s_ki_pruefsumme"), data=good, served=good + b"x" * 300000)        # more than announced: not read to its end
        self.fails(tr("s_ki_pruefsumme"), data=good, served=b"")

    def test_no_connection_and_stopped_half_way(self):
        with Build() as b:
            b.net.error = urllib.error.URLError("Network is unreachable")
            self.rt.install()
            job = wait(self.rt)
            self.assertEqual(job["state"], "error"); self.assertIn("Keine Verbindung", job["text"])
            b.net.error = urllib.error.HTTPError("https://github.com/x", 404, "Not Found", {}, None)
            self.rt.install()
            self.assertIn("404", wait(self.rt)["text"])
            b.net.error = ConnectionResetError("reset")
            self.rt.install()
            self.assertIn("Keine Verbindung", wait(self.rt)["text"])
            self.assertEqual(self.left(), []); self.assertEqual(self.switched, [])
            # stopped by you while it loads
            b.net.error, b.net.slow = None, threading.Event()
            self.rt.install()
            t0 = time.time()
            while not self.rt.job["done"] and time.time() - t0 < 10:
                b.net.slow.set(); time.sleep(0.01)
            self.rt.cancel(); b.net.slow.set()
            self.assertEqual(wait(self.rt)["state"], "cancelled")
            self.assertEqual(self.left(), []); self.assertEqual(self.switched, []); self.assertEqual(pyboot.read_state(self.here), {})
            # ... and loaded again afterwards as if nothing had been
            b.net.slow = None
            self.rt.install()
            self.assertEqual(wait(self.rt)["state"], "done", self.rt.job)

    def test_a_python_that_does_not_run_kontor(self):
        self.fails(tr("s_py_startet_nicht") % "exit 3", script=DEAD)                     # does not start at all
        b = self.fails("no such part", script=NO_KONTOR)                                # starts, but does not load Kontor's parts
        self.assertEqual(len(b.net.calls), 1)
        keep = R.VERSION
        with Build() as b:                                                              # runs Kontor, but is not the version named
            R.VERSION = "9.9.9"
            R.FILES[L.asset_tag()]["file"] = "cpython-9.9.9+20990101-test.tar.gz"
            self.rt.install()
            job = wait(self.rt)
        self.assertEqual(R.VERSION, keep)
        self.assertEqual(job["state"], "error"); self.assertIn(tr("s_py_version") % (NOW, "9.9.9"), job["text"])
        self.assertEqual(self.left(), []); self.assertEqual(self.switched, [])

    def test_an_archive_that_is_not_a_build(self):
        def entry(name, data=b"x", kind=None, link=""):
            info = tarfile.TarInfo(name)
            info.size = len(data) if kind is None else 0
            if kind is not None:
                info.type, info.linkname = kind, link
            return info, (data if kind is None else None)
        outside = os.path.join(os.path.dirname(self.here), "kontor-escaped")
        for more in ([entry("../kontor-escaped")], [entry("/tmp/kontor-escaped")], [entry("python/../../kontor-escaped")],
                     [entry("python/dev", kind=tarfile.CHRTYPE)], [entry("python/hard", kind=tarfile.LNKTYPE, link="python/bin/python3.13")],
                     [entry("python/out", kind=tarfile.SYMTYPE, link="/etc/hosts")], [entry("python/up", kind=tarfile.SYMTYPE, link="../../../x")]):
            with self.subTest(more[0][0].name):
                self.fails(tr("s_ki_archiv_unsicher"), data=archive(more=tuple(more)))
                self.assertFalse(os.path.exists(outside))
        self.fails("", data=b"not an archive at all")
        self.fails(tr("s_ki_archiv_unsicher"), data=self._without_program())

    def _without_program(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            info = tarfile.TarInfo("python/lib/readme.txt"); info.size = 2
            t.addfile(info, io.BytesIO(b"hi"))
        return buf.getvalue()

    def test_what_was_unpacked_is_what_the_archive_holds(self):
        data = archive()
        arch = os.path.join(self.here, "a.tar.gz")
        with open(arch, "wb") as f:
            f.write(data)
        dest = os.path.join(self.here, "x")
        L.unpack(arch, dest)
        R.same(arch, dest)
        lib = os.path.join(dest, "python", "lib", "python3.13", "os.py")
        with open(lib, "ab") as f:                                    # one file longer
            f.write(b"x")
        with self.assertRaises(ValueError):
            R.same(arch, dest)
        with open(lib, "rb+") as f:                                   # the same length, another content
            f.truncate(os.path.getsize(lib) - 1); f.seek(0); f.write(b"X")
        with self.assertRaises(ValueError):
            R.same(arch, dest)
        shutil.rmtree(dest); L.unpack(arch, dest)
        os.remove(os.path.join(dest, "python", "lib", "python3.13", "LICENSE.txt"))        # one missing
        with self.assertRaises(ValueError):
            R.same(arch, dest)
        shutil.rmtree(dest); L.unpack(arch, dest)
        link = os.path.join(dest, "python", "bin", "python3")
        os.remove(link); os.symlink("/bin/sh", link)                  # a link that leads elsewhere
        with self.assertRaises(ValueError):
            R.same(arch, dest)
        os.remove(link); shutil.copy(os.path.join(dest, "python", "bin", "python3.13"), link)      # a file where a link was
        with self.assertRaises(ValueError):
            R.same(arch, dest)

    def test_once_more_without_loading_and_removed(self):
        self.assertFalse(hasattr(self.rt, "use_apple"))                # no way back by choice (user, 2026-11-23): always the newest Python
        with Build() as b:
            self.rt.install()
            self.assertEqual(wait(self.rt)["state"], "done", self.rt.job)
            self.rt.install()                                         # asked again: on this Mac already -- tried, not loaded again
            self.assertEqual(wait(self.rt)["state"], "done", self.rt.job)
            self.assertEqual(len(b.net.calls), 1); self.assertEqual(self.switched, [1, 1])
            self.assertTrue(pyboot.chosen(self.here))
            # the service runs in it: removing it is refused
            with mock.patch.dict(os.environ, {pyboot.ENV_STARTER: "4711", pyboot.ENV_PYTHON: pyboot.chosen(self.here)}):
                st = self.rt.status()
                self.assertEqual((st["running"]["own"], st["restart"]), (True, False))
                with self.assertRaises(ValueError):
                    self.rt.remove()
            st = self.rt.remove()                                     # (one that did not start, the Mac's Python serving)
            self.assertEqual((st["use"], st["loaded"]), ("", None))
            self.assertEqual(pyboot.read_state(self.here), {})
            self.assertEqual(self.rt.status()["use"] if pyboot.write_state(self.here, {"use": "apple"}) is None else "", "")       # a word from before the decision counts for nothing
            # on this Mac, but damaged since: loaded anew
            self.rt.install(); wait(self.rt)
            exe = pyboot.chosen(self.here)
            with open(exe, "w") as f:
                f.write(DEAD)
            self.rt.install()
            self.assertEqual(wait(self.rt)["state"], "done", self.rt.job)
            self.assertEqual(len(b.net.calls), 3)
            self.assertIn("exec", open(exe).read())

    def test_it_did_not_start_said_and_tried_again(self):
        with Build() as b:
            self.rt.install(); wait(self.rt)
            st = pyboot.read_state(self.here)
            st["failed"] = {"at": "2026-11-23 10:00", "why": "start", "detail": "exit 3"}
            pyboot.write_state(self.here, st)
            got = self.rt.status()
            self.assertEqual(got["failed"], {"at": "2026-11-23 10:00", "why": "start", "detail": "exit 3"})
            self.assertFalse(got["restart"]); self.assertEqual(pyboot.chosen(self.here), "")
            self.rt.install()                                         # "try again": tried, the note taken away, switched
            self.assertEqual(wait(self.rt)["state"], "done")
            self.assertIsNone(self.rt.status()["failed"]); self.assertTrue(pyboot.chosen(self.here))
            self.assertEqual(len(b.net.calls), 1)

    def test_a_newer_build_and_what_is_left_over(self):
        root = pyboot.folder(self.here)
        put_build(self.here, name="cpython-3.0.0-20200101")
        old = pyboot.chosen(self.here)
        for junk in ("x.tar.gz.part", "x.tar.gz"):
            open(os.path.join(root, junk), "w").close()
        os.makedirs(os.path.join(root, "cpython-2.0.0-1.tmp", "python"))
        os.makedirs(os.path.join(root, R.LIBS, "x-1.0"))                     # (the place for libraries of shielded helpers, once there are any)
        put_build(self.here, name="cpython-1.0.0-1", state=False)
        with Build():
            st = self.rt.status()
            self.assertTrue(st["newer"]); self.assertEqual(st["use"], "own")
            self.rt.install()
            self.assertEqual(wait(self.rt)["state"], "done", self.rt.job)
            self.assertFalse(self.rt.status()["newer"])
        # what earlier tries left is gone; the build that was in use until now stays until the next start has left it
        self.assertEqual(sorted(os.listdir(root)), sorted([NAME, "cpython-3.0.0-20200101", pyboot.STATE, R.LIBS]))
        self.assertTrue(os.path.isfile(old))
        self.rt.sweep()
        self.assertEqual(sorted(os.listdir(root)), sorted([NAME, pyboot.STATE, R.LIBS]))
        # never the one this very process runs in, whatever the state file says
        put_build(self.here, name="cpython-3.0.0-20200101", state=False)
        with mock.patch.object(pyboot, "running", lambda: old):
            self.assertEqual(pyboot.serving(self.here), old)
            self.rt.sweep()
        self.assertTrue(os.path.isfile(old))
        # the libraries' place stayed through every sweep -- and goes with Kontor's own Python
        self.assertTrue(os.path.isdir(os.path.join(root, R.LIBS, "x-1.0")))
        self.rt.remove()
        self.assertEqual(os.listdir(root), [pyboot.STATE])

    def test_where_there_is_no_build_and_no_room(self):
        keep = R.FILES
        R.FILES = {}
        try:
            st = self.rt.status()
            self.assertEqual((st["supported"], st["offered"]), (False, None))
            self.rt.install()
            self.assertIn(tr("s_py_kein_build"), wait(self.rt)["text"])
            self.assertFalse(self.rt.install_now(lambda line: None))
        finally:
            R.FILES = keep
        with Build(), mock.patch.object(R.shutil, "disk_usage", lambda p: mock.Mock(free=10 * 1024 * 1024)):
            self.rt.install()
            self.assertIn("Speicherplatz", wait(self.rt)["text"])
        self.assertEqual(self.left(), [])

    def test_the_installer(self):
        said = []
        with Build():
            self.assertTrue(self.rt.install_now(said.append))
            self.assertEqual(len(said), 2); self.assertIn(NOW, said[0]); self.assertIn("GitHub", said[0]); self.assertIn(NOW, said[1])
            self.assertTrue(pyboot.chosen(self.here)); self.assertEqual(self.switched, [])        # (the installer starts the service itself)
        shutil.rmtree(pyboot.folder(self.here))
        said = []
        with Build(script=DEAD):
            self.assertFalse(self.rt.install_now(said.append))
        self.assertIn("Python des Macs", said[1]); self.assertEqual(self.left(), [])
        # `kontor.py install`: only on a Mac, not when you went back to the Mac's Python or say so, not when it is set up already
        import kontor
        calls = []
        with mock.patch.object(R.Runtime, "install_now", lambda self_, say: calls.append(1)), mock.patch.object(kontor, "HERE", self.here):
            if sys.platform != "darwin":
                with Build():
                    kontor.own_python()
                self.assertEqual(calls, [])
            with mock.patch.object(kontor.sys, "platform", "darwin"), Build():
                kontor.own_python()
                self.assertEqual(calls, [1])
                del calls[:]
                with mock.patch.dict(os.environ, {"KONTOR_PYTHON": "apple"}):
                    kontor.own_python()
                self.assertEqual(calls, [])
                shutil.rmtree(pyboot.folder(self.here)); put_build(self.here)
                kontor.own_python()                                   # set up and in use: nothing to do
                self.assertEqual(calls, [])
                st = pyboot.read_state(self.here); st["failed"] = {"why": "start"}; pyboot.write_state(self.here, st)
                kontor.own_python()                                   # it did not start: the installer tries it again
                self.assertEqual(calls, [1])
                put_build(self.here, name="cpython-3.0.0-20200101")
                kontor.own_python()                                   # an older build: the one named now
                self.assertEqual(calls, [1, 1])

    def test_the_build_named(self):
        """The real list: one file per kind of Mac, each with its size and SHA-256; the address is GitHub's and the one
        python-build-standalone publishes it under."""
        self.assertEqual(sorted(R.FILES), ["macos-arm64", "macos-x64"])
        self.assertRegex(R.VERSION, r"^3\.1[3-9]\.\d+$"); self.assertRegex(R.BUILD, r"^20\d{6}$")
        self.assertEqual(R.REPO, "astral-sh/python-build-standalone")
        for tag, f in R.FILES.items():
            arch = {"macos-arm64": "aarch64", "macos-x64": "x86_64"}[tag]
            self.assertEqual(f["file"], "cpython-%s+%s-%s-apple-darwin-install_only_stripped.tar.gz" % (R.VERSION, R.BUILD, arch))
            self.assertRegex(f["sha256"], r"^[0-9a-f]{64}$"); self.assertTrue(20e6 < f["size"] < 60e6)
            with mock.patch.object(L, "asset_tag", lambda t=tag: t):
                b = R.build()
            self.assertEqual(b["url"], "https://github.com/astral-sh/python-build-standalone/releases/download/%s/%s" % (R.BUILD, f["file"].replace("+", "%2B")))
            self.assertTrue(L.host_allowed(b["url"], L.GITHUB)); self.assertEqual(b["name"], "cpython-%s-%s" % (R.VERSION, R.BUILD))
            self.assertTrue(pyboot.DIR_RE.fullmatch(b["name"]))
        self.assertEqual(len({f["sha256"] for f in R.FILES.values()}), len(R.FILES))
        # the Python Kontor is tested with on GitHub is the line it loads
        with open(os.path.join(ROOT, ".github", "workflows", "tests.yml"), encoding="utf-8") as f:
            yml = f.read()
        self.assertIn('python: "%s"' % ".".join(R.VERSION.split(".")[:2]), yml)
        self.assertIn('f="cpython-%s+%s-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"' % (R.VERSION, R.BUILD), yml)      # ... and the real build its tests start
        self.assertIn("releases/download/%s/" % R.BUILD, yml)
        # only ever a Python of Kontor's own folder is run, and only alone
        with self.assertRaises(ValueError):
            R.run_python(self.here, sys.executable, ["-c", "pass"], 10)
        self.assertEqual(R.starts(self.here, "/bin/sh") != "", True)
        exe = put_build(self.here)
        with mock.patch.dict(os.environ, {"KONTOR_DIR": "/the/real/data", "HTTPS_PROXY": "http://x.invalid", "PYTHONPATH": "/x"}):
            r = R.run_python(self.here, exe, ["-c", "import json, os, sys; print(json.dumps([sys.flags.isolated, sys.flags.no_site, sys.flags.dont_write_bytecode, dict(os.environ), os.getcwd()]))"], 30)
        alone, no_site, no_cache, env, cwd = json.loads(r.stdout)
        self.assertEqual((alone, no_site, no_cache), (1, 1, 1))
        self.assertEqual(set(env) - {"LC_CTYPE", "PWD", "OLDPWD", "SHLVL", "_"}, {"HOME", "KONTOR_DIR", "LANG", "PATH", "TMPDIR"})      # nothing of Kontor's own environment
        self.assertTrue(env["KONTOR_DIR"].startswith(env["TMPDIR"])); self.assertIn("kontor-python-", cwd)       # a data folder that is not yours
        self.assertFalse(os.path.exists(env["TMPDIR"]))                                  # ... and gone afterwards


class SelfTest(unittest.TestCase):
    """pyselftest.py: run by a Python, it says whether Kontor runs in it -- every part of Kontor loaded, what Kontor needs of
    Python tried; it connects nowhere."""

    def run_it(self, here=ROOT):
        work = tempfile.mkdtemp(prefix="kontor-selftest-")
        try:
            r = subprocess.run([sys.executable, "-I", "-S", "-B", os.path.join(here, "pyselftest.py")], capture_output=True, text=True, timeout=300,
                               env=R._env(work), cwd=work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])

    def test_this_python_runs_kontor(self):
        code, out = self.run_it()
        self.assertEqual((code, out["ok"], out["version"]), (0, True, NOW), out)
        self.assertIn("OpenSSL", out["https"]); self.assertIn("SQLite", out["database"])

    def test_a_part_that_is_missing_is_said(self):
        here = tempfile.mkdtemp(prefix="kontor-part-")
        try:
            for path in glob.glob(os.path.join(ROOT, "*.py")) + [os.path.join(ROOT, x) for x in ("web", "VERSION")]:
                if os.path.basename(path) not in ("tax.py", "pyselftest.py"):
                    os.symlink(path, os.path.join(here, os.path.basename(path)))
            shutil.copy(os.path.join(ROOT, "pyselftest.py"), here)
            code, out = self.run_it(here)
        finally:
            shutil.rmtree(here, ignore_errors=True)
        self.assertEqual((code, out["ok"]), (1, False)); self.assertIn("tax", out["error"])

    def test_the_lists_are_true(self):
        """It loads every part of Kontor by name -- a new part is added there. And every part of Python that Kontor loads is
        loaded with one of them, at its top; the few loaded only when needed are tried by name."""
        own = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(ROOT, "*.py"))}
        with open(os.path.join(ROOT, "pyselftest.py"), encoding="utf-8") as f:
            src = f.read()
        t = ast.parse(src)
        loaded = next(n for n in ast.walk(t) if isinstance(n, ast.ClassDef) and n.name == "Loaded")
        named = {a.name for n in loaded.body if isinstance(n, ast.Import) for a in n.names}
        self.assertEqual(named, own - {"pyselftest"}, "a part of Kontor is missing in pyselftest.py (parts) or named there and gone")
        top, late = set(), set()
        for path in glob.glob(os.path.join(ROOT, "*.py")):
            if os.path.basename(path) == "pyselftest.py":
                continue
            with open(path, encoding="utf-8") as f:
                mod = ast.parse(f.read())

            def walk(node, inner):
                for c in ast.iter_child_nodes(node):
                    names = [a.name for a in c.names] if isinstance(c, ast.Import) else [c.module] if isinstance(c, ast.ImportFrom) and c.module and not c.level else []
                    (late if inner else top).update(n for n in names if n.split(".")[0] not in own)
                    walk(c, inner or isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)))
            walk(mod, False)
        # gzip: tried in works(); _sqlite3: by mm_history.MemDB, which the_macs_libraries() opens on a Mac; cryptography: only where there is no Mac (tests)
        self.assertEqual(late - top, {"gzip", "_sqlite3", "cryptography.hazmat.primitives.ciphers"},
                         "a part of Python that Kontor loads only when it needs it: try it in pyselftest.py (works) and name it here")
        self.assertIn("import gzip", src); self.assertIn("mm_history.MemDB(image)", src)

    def test_the_macs_own_libraries_called_from_this_python(self):
        """What it tries on a Mac -- the system's AES and SQLite through ctypes, as reading MoneyMoney's database needs them --,
        here with what stands in for them where there is no Mac."""
        import mm_history
        keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True       # (loaded here without a trace beside Kontor's files: Loading looks at that)
        try:
            import pyselftest
        finally:
            sys.dont_write_bytecode = keep
        try:
            mm_history._aes_cbc(); mm_history._sqlite_lib()
        except mm_history.HistorieError as e:
            self.skipTest("no AES or no SQLite to call here: %s" % e)
        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "kontor-selftest-*")))
        pyselftest.the_macs_libraries()
        self.assertEqual(set(glob.glob(os.path.join(tempfile.gettempdir(), "kontor-selftest-*"))), before)       # its made-up database is gone again
        with mock.patch.object(mm_history.MemDB, "rows", lambda self, sql, params=(): [(8, "x")] if "from t" in sql else []):
            with self.assertRaises(RuntimeError):
                pyselftest.the_macs_libraries()

    def test_it_connects_nowhere_and_starts_nothing_itself(self):
        with open(os.path.join(ROOT, "pyselftest.py"), encoding="utf-8") as f:
            t = ast.parse(f.read())
        mods = {a.name for n in ast.walk(t) if isinstance(n, ast.Import) for a in n.names if not isinstance(n, ast.ClassDef)}
        own = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(ROOT, "*.py"))}
        self.assertEqual(mods - own, {"json", "os", "sys", "sqlite3", "ssl", "decimal", "gzip", "hashlib", "hmac", "io", "plistlib", "tarfile", "wave",
                                      "xml.etree.ElementTree", "zipfile", "shutil", "tempfile"})
        calls = {n.func.attr for n in ast.walk(t) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertEqual(calls & {"connect_ex", "urlopen", "create_connection", "wrap_socket", "request", "Popen", "run", "system", "bind", "listen", "send"}, set())
        # the database: in memory, and one made-up file in a temporary folder of its own
        self.assertEqual(sorted(ast.unparse(n.args[0]) for n in ast.walk(t) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "connect"),
                         ["':memory:'", "os.path.join(work, 't.sqlite')"])


def program_copy(dest: str, link: bool = True) -> str:
    """Kontor's program in a folder of its own, so that what it writes beside itself (.python/) lands there: linked, or copied
    where the folder itself is to go."""
    os.makedirs(dest, exist_ok=True)
    for path in glob.glob(os.path.join(ROOT, "*")):
        name = os.path.basename(path)
        if name in ("tests", "node_modules", "__pycache__") or name.endswith(".app"):
            continue
        if link:
            os.symlink(path, os.path.join(dest, name))
        elif os.path.isdir(path):
            shutil.copytree(path, os.path.join(dest, name), ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(path, os.path.join(dest, name))
    return dest


class Service(unittest.TestCase):
    """In the service: asked for only at the Mac, never by the demo; the overview says what there is to do; an uninstall takes
    Kontor's own Python with it; a restart goes through the starter."""

    @classmethod
    def setUpClass(cls):
        from test_e2e import _AppBase
        cls.Base = _AppBase

    def setUp(self):
        self.t = self.Base("setUp"); self.t.setUp()
        self.addCleanup(self.t.tearDown)
        self.app, self.call = self.t.app, self.t.call
        self.prog = os.path.realpath(tempfile.mkdtemp(prefix="kontor-prog-"))
        self.addCleanup(shutil.rmtree, self.prog, True)
        for f in ("kontor.py", "service.py", "VERSION"):
            open(os.path.join(self.prog, f), "w").close()
        self.app.program_dir = self.prog
        self.restarts = []
        self.app.request_restart = lambda why="": self.restarts.append(why)

    def test_only_at_the_mac_and_never_the_demo(self):
        import service as MA
        self.assertEqual(self.call("/api/python")[0], 401)                    # not before the sign-in
        self.t.login()
        code, r = self.call("/api/python")
        self.assertEqual(code, 200); self.assertEqual(r["python"]["running"]["version"], NOW); self.assertEqual(r["instance"], self.app.instance)
        self.assertEqual(self.call("/api/update/status")[1]["python"], r["python"])
        self.assertEqual(self.call("/api/python", {"action": "sudo"})[0], 400)
        keep = MA.auth.is_loopback
        MA.auth.is_loopback = lambda remote: False                            # from another device: nothing of it
        try:
            with Build() as b:
                for action in ("install", "remove", "cancel"):
                    self.assertEqual(self.call("/api/python", {"action": action})[0], 403, action)
                self.assertEqual(self.call("/api/python")[0], 200)            # (what runs may be seen)
                self.assertEqual(b.net.calls, [])
        finally:
            MA.auth.is_loopback = keep
        self.assertFalse(os.path.exists(pyboot.folder(self.prog)))
        self.assertIn("/api/python", MA.DEMO_NEVER)
        self.assertFalse(MA.demo_allowed("GET", "/api/python")); self.assertFalse(MA.demo_allowed("POST", "/api/python"))
        # at the Mac: loaded, tried, switched -- then the service starts anew
        with Build() as b:
            code, r = self.call("/api/python", {"action": "install"})
            self.assertEqual(code, 200); self.assertIn(r["python"]["job"]["state"], ("running", "done"))
            self.assertEqual(self.call("/api/python", {"action": "install"})[0] if r["python"]["job"]["state"] == "running" else 400, 400)
            self.assertEqual(wait(self.app.python)["state"], "done", self.app.python.job)
            self.assertEqual(self.restarts, ["another Python"])
            st = self.call("/api/python")[1]["python"]
            self.assertEqual((st["use"], st["restart"], st["loaded"]["version"]), ("own", True, NOW))
            with mock.patch.dict(os.environ, {pyboot.ENV_STARTER: "4711", pyboot.ENV_PYTHON: pyboot.chosen(self.prog)}):   # the service runs in it now
                self.assertFalse(self.call("/api/python")[1]["python"]["restart"])
                self.assertEqual(self.call("/api/python", {"action": "apple"})[0], 400)       # no way back by choice
                self.assertEqual(self.restarts, ["another Python"])
                self.assertEqual(self.call("/api/python", {"action": "remove"})[0], 400)
            code, r = self.call("/api/python", {"action": "remove"})
            self.assertEqual((code, r["python"]["loaded"], r["python"]["use"]), (200, None, ""))

    def test_the_overview_says_what_there_is_to_do(self):
        self.t.login()
        hint = lambda: self.call("/api/status")[1]["python"]
        with Build():
            with mock.patch.object(R, "ENDED", {}):
                self.assertEqual(hint(), "")                                  # a Python that still gets its fixes: nothing to say
            self.assertEqual(R.ENDED, {(3, 9): "2025-10-31"})                 # (the Mac's own: past that day)
            with mock.patch.object(R, "ENDED", {tuple(sys.version_info[:2]): "2025-10-31"}):
                self.assertEqual(self.call("/api/python")[1]["python"]["running"]["ended"], "2025-10-31")
                self.assertEqual(hint(), "old")
                with mock.patch.object(R, "FILES", {}):                      # nothing to load for this machine: nothing to do
                    self.assertEqual(hint(), "")
                shutil.rmtree(pyboot.folder(self.prog), ignore_errors=True)
                self.app.python.install(); wait(self.app.python)
                st = pyboot.read_state(self.prog); st["failed"] = {"why": "start", "detail": "exit 3", "at": ""}; pyboot.write_state(self.prog, st)
                self.assertEqual(hint(), "failed")
            shutil.rmtree(pyboot.folder(self.prog)); put_build(self.prog, name="cpython-3.0.0-20200101")
            with mock.patch.object(R, "ENDED", {}):
                self.assertEqual(hint(), "newer")
        # the demo is told nothing about this Mac's programs
        import service as MA
        self.assertEqual(MA.App.python_hint.__name__, "python_hint")
        with open(MA.__file__, encoding="utf-8") as f:
            self.assertIn('st["python"] = "" if app.DEMO else app.python_hint()', f.read())

    def uninstall(self, program, own=False):
        import service as MA
        if os.path.exists(pyboot.folder(self.prog)):
            shutil.rmtree(pyboot.folder(self.prog))
        for f in ("kontor.py", "service.py", "VERSION"):
            os.makedirs(self.prog, exist_ok=True); open(os.path.join(self.prog, f), "w").close()
        put_build(self.prog)
        with open(os.path.join(self.app.data_dir, "kontor.log"), "w") as f:
            f.write("x")
        plist = os.path.join(self.app.data_dir, "none.plist")
        with mock.patch.object(MA.updates, "plist_path", lambda label=MA.updates.LABEL: plist), mock.patch.object(MA.mac_app, "remove_data", lambda quit_first=False: []), \
                mock.patch.object(self.app, "uninstall_key", lambda: True), mock.patch.dict(os.environ, {pyboot.ENV_STARTER: "4711"} if own else {}):
            return MA.App.uninstall(self.app, program)

    def fresh(self):
        self.t.tearDown(); self.t.setUp()
        self.app = self.t.app
        self.app.program_dir = self.prog
        self.t.login()

    def test_an_uninstall_takes_it_along(self):
        self.t.login()
        folder = pyboot.folder(self.prog)
        r = self.uninstall(False)                                            # the program folder stays: Kontor's own Python goes all the same
        self.assertTrue(r["ok"], r); self.assertIn(folder, r["removed"])
        self.assertFalse(os.path.exists(folder)); self.assertTrue(os.path.exists(os.path.join(self.prog, "kontor.py")))
        self.fresh()
        r = self.uninstall(True)
        self.assertTrue(r["ok"], r); self.assertFalse(os.path.exists(self.prog))
        # the service itself runs in it: left to the starter, which removes it once the service has ended (pyboot.py)
        self.fresh()
        r = self.uninstall(False, own=True)
        self.assertTrue(r["ok"], r); self.assertIn(folder, r["removed"])
        with open(os.path.join(folder, pyboot.REMOVE)) as f:
            self.assertEqual(f.read(), "")
        self.assertTrue(pyboot.exe_in(self.prog, NAME))                       # still there for the moment: this process needs it
        self.fresh()
        r = self.uninstall(True, own=True)
        self.assertTrue(r["ok"], r)
        with open(os.path.join(folder, pyboot.REMOVE)) as f:
            self.assertEqual(f.read(), "program")
        self.assertEqual(os.listdir(self.prog), [pyboot.FOLDER])              # everything else of the program is gone
        pyboot._remove(self.prog)                                             # what the starter does after the service's end
        self.assertFalse(os.path.exists(self.prog))

    def test_a_restart_goes_through_the_starter(self):
        import service as MA
        done = []
        with mock.patch.object(MA.os, "execv", lambda *a: done.append(("execv", a[0]))), mock.patch.object(MA.os, "_exit", lambda code: done.append(("exit", code))), \
                mock.patch.object(MA.logging, "shutdown", lambda: None):
            MA.restart_process()                                              # as ever: itself anew
            self.assertEqual(done, [("execv", sys.executable)])
            del done[:]
            with mock.patch.dict(os.environ, {pyboot.ENV_STARTER: "4711"}):   # run by a starter: it ends, the starter decides anew
                MA.restart_process()
            self.assertEqual(done[0], ("exit", pyboot.EX_RESTART))


PASSWORD = "sehr-geheimes-passwort"


def free_port() -> int:
    import socket
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


class Whole(unittest.TestCase):
    """Kontor's real service as launchd starts it -- the starter in the Python of these tests, the service in "Kontor's own"
    (the stand-in that hands over to the same Python): started, switched back over the page's request, damaged and started
    again, uninstalled from the page."""

    def setUp(self):
        import access
        from fixtures import new_store
        from service import App
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="kontor-whole-"))
        self.data, self.home, self.port = os.path.join(self.tmp, "data"), os.path.join(self.tmp, "home"), free_port()
        os.makedirs(self.home)
        store = new_store(self.data)
        store.save("config.json", {"updates": {"check_mode": "aus"}, "schedule": {"automatic": False}, "ui": {"port": self.port}})
        app = App(store, self.data)
        app.first_password(PASSWORD)                                          # as the setup does: the key wrapped with the password
        access.write_start(self.data, app.config)
        app.stop.set()
        self.procs, self.csrf = [], None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
                p.wait(10)
        subprocess.run(["pkill", "-KILL", "-f", self.tmp], capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start(self, prog):
        env = dict(os.environ, KONTOR_DIR=self.data, HOME=self.home)
        env.pop("KONTOR_STARTER", None)
        p = subprocess.Popen([sys.executable, os.path.join(prog, "kontor.py"), "--quiet", "start"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.tmp)
        self.procs.append(p)
        return p

    def stop(self, p):
        """As launchd ends Kontor: the starter is told and ends once the service has (the service alone: by that very signal)."""
        p.send_signal(signal.SIGTERM)
        self.assertIn(p.wait(30), (0, -signal.SIGTERM))
        self.assertEqual(subprocess.run(["pgrep", "-f", os.path.join(self.tmp, "Kontor")], capture_output=True).stdout, b"")       # nothing of it left

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=data, headers={"Content-Type": "application/json", **({"X-CSRF-Token": self.csrf} if self.csrf else {})})
        try:
            with self.opener.open(req, timeout=30) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def answers(self, other_than=None, seconds=90.0):
        """Waits until the service answers (as another start than the one named) and signs in."""
        t0 = time.time()
        while time.time() - t0 < seconds:
            try:
                code, s = self.call("/api/session")
                if code == 200 and s.get("instance") != other_than:
                    self.csrf = None
                    code, r = self.call("/api/login", {"password": PASSWORD})
                    self.assertEqual(code, 200, r)
                    self.csrf = r["csrf"]
                    return s["instance"]
            except (OSError, ValueError):
                pass
            time.sleep(0.2)
        self.fail("the service does not answer; its log:\n" + self.log()[-3000:] + "\n" + "".join((p.stderr.read() or b"").decode("utf-8", "replace")[-2000:] for p in self.procs if p.poll() is not None))

    def log(self):
        try:
            with open(os.path.join(self.data, "kontor.log"), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def pythons(self):
        """Which Python served, start by start (from the log)."""
        return [line.split("Python ", 1)[1] for line in self.log().splitlines() if " INFO kontor: Python " in line]

    def test_started_switched_back_damaged_and_started_again(self):
        prog = program_copy(os.path.join(self.tmp, "Kontor"))
        exe = put_build(prog)
        p = self.start(prog)
        first = self.answers()
        st = self.call("/api/python")[1]["python"]
        self.assertEqual((st["running"]["own"], st["use"], st["restart"], st["failed"]), (True, "own", False, None))
        self.assertEqual(self.pythons(), ["%s (Kontor's own)" % NOW])
        kids = subprocess.run(["pgrep", "-P", str(p.pid)], capture_output=True, text=True).stdout.split()
        self.assertEqual(len(kids), 1)                                        # the starter and, as its child, the service
        self.assertEqual(self.call("/api/status")[1]["python"], "")
        # started a second time by hand while it runs: refused as ever (Kontor already runs) -- in the own Python and then in
        # the starter's, so it was nothing of the own Python's: nothing noted, and nothing of the running service's swept
        left = os.path.join(pyboot.folder(prog), "half-loaded")
        os.makedirs(left)
        q = self.start(prog)
        self.assertEqual(q.wait(90), 1); self.assertIn(b"service.lock", q.stderr.read())
        self.assertNotIn("failed", pyboot.read_state(prog)); self.assertTrue(os.path.isdir(left))
        self.assertEqual(self.call("/api/session")[1].get("instance"), first)
        self.assertEqual(self.pythons(), ["%s (Kontor's own)" % NOW] * 3 + ["%s (the Mac's)" % NOW])          # (twice in its own, then in the starter's)
        os.rmdir(left)
        # no way back by choice: the page cannot ask for the Mac's Python
        self.assertEqual(self.call("/api/python", {"action": "apple"})[0], 400)
        self.stop(p)                                                          # (ended as launchd ends it, started as launchd starts it)
        p = self.start(prog)
        third = self.answers(other_than=first)
        self.assertEqual(self.pythons()[-1], "%s (Kontor's own)" % NOW)
        # damaged since: the next start serves in the Mac's Python at once, says so, and does not try it again
        open(os.path.join(os.path.dirname(exe), "broken"), "w").close()
        self.stop(p)
        p = self.start(prog)
        fourth = self.answers(other_than=third)
        self.assertEqual(self.pythons()[-1], "%s (the Mac's)" % NOW)
        self.assertIn("ERROR kontor: Kontor's own Python did not start (start: exit 9)", self.log())
        st = self.call("/api/python")[1]["python"]
        self.assertEqual((st["running"]["own"], st["use"], st["failed"]["why"], st["failed"]["detail"], st["restart"]), (False, "own", "start", "exit 9", False))
        self.assertEqual(self.call("/api/status")[1]["python"], "failed")
        self.stop(p)
        p = self.start(prog)
        self.answers(other_than=fourth)
        self.assertEqual(self.pythons()[-1], "%s (the Mac's)" % NOW); self.assertEqual(self.log().count("did not start"), 1)
        # repaired and tried again (the job, here in this process): the service restarts into it
        os.remove(os.path.join(os.path.dirname(exe), "broken"))
        with Build():
            rt = R.Runtime(prog)
            rt.install()
            self.assertEqual(wait(rt)["state"], "done", rt.job)
        self.stop(p)
        p = self.start(prog)
        self.answers()
        self.assertEqual(self.pythons()[-1], "%s (Kontor's own)" % NOW)
        self.assertIsNone(self.call("/api/python")[1]["python"]["failed"])
        self.stop(p)

    def test_uninstalled_from_the_page_while_it_runs_in_it(self):
        for whole in (False, True):
            with self.subTest(program_folder=whole):
                prog = program_copy(os.path.join(self.tmp, "Kontor-%d" % whole), link=False)
                put_build(prog)
                if whole:
                    self.tearDown(); self.setUp()
                    prog = program_copy(os.path.join(self.tmp, "Kontor-1"), link=False)
                    put_build(prog)
                p = self.start(prog)
                self.answers()
                self.assertTrue(self.call("/api/python")[1]["python"]["running"]["own"])
                code, r = self.call("/api/uninstall", {"password": PASSWORD, "program_folder": whole})
                self.assertEqual(code, 200, r); self.assertIn(pyboot.folder(prog), r["removed"])
                self.assertEqual(p.wait(60), 0)                               # the service ended, then the starter
                self.assertFalse(os.path.exists(pyboot.folder(prog)))         # ... which removed Kontor's own Python after it
                self.assertEqual(os.path.exists(prog), not whole)
                if not whole:
                    self.assertTrue(os.path.exists(os.path.join(prog, "kontor.py")))
                self.assertFalse(os.path.exists(self.data))                   # the data folder with everything of Kontor's


REAL = os.environ.get("KONTOR_PYTHON_ARCHIVE") or ""


@unittest.skipUnless(os.path.isfile(REAL), "the real build for this machine is not at hand (KONTOR_PYTHON_ARCHIVE: its file from python-build-standalone)")
class RealBuild(Whole):
    """The same with a real build of python-build-standalone for this machine (GitHub's tests load the one for Linux; on a Mac
    the workflow's macOS job does all of it with the build Kontor names): loaded as named, unpacked and compared, tried with
    every part of Kontor -- then the real service started in it by the starter, switched back and forth again."""

    test_uninstalled_from_the_page_while_it_runs_in_it = None

    def test_started_switched_back_damaged_and_started_again(self):
        import re
        m = re.match(r"cpython-(\d+\.\d+\.\d+)\+(\d{8})-", os.path.basename(REAL))
        self.assertTrue(m, REAL)
        with open(REAL, "rb") as f:
            data = f.read()
        prog = program_copy(os.path.join(self.tmp, "Kontor"))
        with Build(data=data) as b:
            R.VERSION, R.BUILD = m.group(1), m.group(2)
            R.FILES[L.asset_tag()]["file"] = os.path.basename(REAL)
            rt = R.Runtime(prog)
            rt.install()
            self.assertEqual(wait(rt, 600)["state"], "done", rt.job)
            self.assertEqual(len(b.net.calls), 1); self.assertIn(os.path.basename(REAL).replace("+", "%2B"), b.net.calls[0])
            exe = pyboot.chosen(prog)
            self.assertTrue(exe.endswith("/python/bin/python%s" % ".".join(m.group(1).split(".")[:2])), exe)
            self.assertEqual(R.starts(prog, exe), "")
            self.assertEqual(R.tried(prog, exe, m.group(1))["version"], m.group(1))
        p = self.start(prog)
        first = self.answers()
        st = self.call("/api/python")[1]["python"]
        self.assertEqual((st["running"], st["use"], st["restart"], st["failed"]), ({"version": m.group(1), "own": True, "ended": ""}, "own", False, None))
        self.assertEqual(self.pythons(), ["%s (Kontor's own)" % m.group(1)])
        kid = subprocess.run(["pgrep", "-P", str(p.pid)], capture_output=True, text=True).stdout.split()
        self.assertEqual(len(kid), 1)
        self.assertIn(exe + " -I -S ", subprocess.run(["ps", "-o", "args=", "-p", kid[0]], capture_output=True, text=True).stdout)
        self.stop(p)                                                          # ended as launchd ends it, started again: in its own again
        p = self.start(prog)
        self.answers(other_than=first)
        self.assertEqual(self.pythons()[-1], "%s (Kontor's own)" % m.group(1))
        self.stop(p)


class Page(unittest.TestCase):
    """Einstellungen -> Updates in the browser: the Python Kontor runs in, the one button that fits, how far the loading is,
    what went wrong -- and after the switch the page waits for Kontor's restart."""

    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        from test_tour import PASSWORD as PW, _playwright, settle
        from test_e2e import MockBridge, config_for_test, patch_today, reset_mock
        from service import App, make_handler
        from fixtures import new_store
        cls.sync_playwright, cls.settle, cls.password = staticmethod(_playwright()), staticmethod(settle), PW
        cls.dir = tempfile.mkdtemp(prefix="kontor-py-ui-")
        cls.prog = os.path.realpath(tempfile.mkdtemp(prefix="kontor-py-prog-"))
        store = new_store(cls.dir); store.save("config.json", config_for_test(os.path.join(cls.dir, "Belege")))
        reset_mock(); patch_today()
        cls.app = App(store, cls.dir, bridge_factory=MockBridge)
        cls.app.program_dir = cls.prog
        cls.app.do_run(False, True)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d/" % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        shutil.rmtree(cls.dir, ignore_errors=True); shutil.rmtree(cls.prog, ignore_errors=True)

    def until(self, pg, js, seconds=30.0):
        t0 = time.time()
        while time.time() - t0 < seconds:
            try:
                if pg.evaluate(js):
                    return
            except Exception:                                   # (the page is loading anew)
                pass
            pg.wait_for_timeout(80)
        self.fail("not reached: " + js)

    def test_loaded_on_a_click_what_went_wrong_and_back(self):
        text = "document.querySelector('#py-box').innerText"
        buttons = "[...document.querySelectorAll('#py-box button')].map(b => b.id + (b.disabled ? ' off' : ''))"
        with mock.patch.object(R, "ENDED", {tuple(sys.version_info[:2]): "2025-10-31"}), self.sync_playwright() as p:
            b = p.chromium.launch()
            for device in ({"viewport": {"width": 1440, "height": 900}}, {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}):
                shutil.rmtree(pyboot.folder(self.prog), ignore_errors=True)
                self.app.python.job = None
                pg = b.new_context(**device).new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.on("dialog", lambda d: d.accept())
                with Build(script=DEAD):
                    pg.goto(self.base); pg.fill("#login-pw", self.password)
                    if pg.is_visible("#login-pw2"):
                        pg.fill("#login-pw2", self.password)
                    pg.click("#login-btn"); pg.wait_for_selector("#shell:not(.hidden)", timeout=30000); self.settle(pg)
                    # the overview says that there is something to do
                    pg.evaluate("location.hash = '#overview'"); self.settle(pg)
                    self.until(pg, "document.body.innerText.includes('Python des Macs bekommt keine Sicherheitsupdates mehr')")
                    pg.evaluate("location.hash = '#settings/updates'"); pg.wait_for_selector("#py-box", timeout=15000)
                    got = pg.evaluate(text)
                    self.assertIn("Python %s" % NOW, got); self.assertIn("des Macs (von Apple)", got); self.assertIn("ohne Sicherheitsupdates seit 31.10.2025", got)
                    self.assertEqual(pg.evaluate(buttons), ["py-install"]); self.assertEqual(pg.inner_text("#py-install"), "Python %s laden" % NOW)
                    # a build that does not start on this Mac: said, nothing switched, the button is back
                    pg.click("#py-install")
                    self.until(pg, "!!document.querySelector('#py-box .banner.err')")
                    self.assertIn("startet auf diesem Mac nicht", pg.inner_text("#py-box .banner.err")); self.assertIn("nichts umgestellt", pg.inner_text("#py-box .banner.err"))
                    self.assertEqual(pg.evaluate(buttons), ["py-install"]); self.assertEqual(pyboot.read_state(self.prog), {})
                with Build() as ok:
                    ok.net.slow = threading.Event()                           # while it loads: how far, and a way to stop
                    pg.click("#py-install")
                    self.until(pg, "!!document.querySelector('#py-cancel')")
                    self.assertEqual(pg.evaluate(buttons), ["py-install off", "py-cancel"]); self.assertIn("Laden …", pg.inner_text("#py-box .prog-l"))
                    pg.click("#py-cancel"); ok.net.slow.set()
                    self.until(pg, "!document.querySelector('#py-cancel')")
                    self.assertEqual(pg.evaluate(buttons), ["py-install"]); self.assertEqual(pyboot.read_state(self.prog), {})
                    ok.net.slow = None
                    first = self.app.instance
                    pg.click("#py-install")                                   # loaded, checked, tried, switched: Kontor restarts, the page waits for it
                    self.until(pg, "document.body.innerText.includes('Kontor startet mit dem anderen Python neu')")
                    self.assertTrue(pyboot.chosen(self.prog))
                    with mock.patch.dict(os.environ, {pyboot.ENV_STARTER: "4711", pyboot.ENV_PYTHON: pyboot.chosen(self.prog)}):       # ... as it comes back in its own Python
                        self.app.instance = "restarted-%d" % len(errors)
                        self.until(pg, "!!document.querySelector('#py-box .banner.ok')", 60)
                        self.assertIn("Kontor läuft jetzt mit Python %s." % NOW, pg.inner_text("#py-box .banner.ok"))
                        got = pg.evaluate(text)
                        self.assertIn("von Kontor geladen", got); self.assertNotIn("Sicherheitsupdates", got)
                        self.assertEqual(pg.evaluate(buttons), [])                    # nothing to choose: no way back (user, 2026-11-23)
                        box = pg.evaluate("(() => { const b = document.querySelector('#py-box').getBoundingClientRect(); return [b.right, innerWidth, document.documentElement.scrollWidth]; })()")
                        self.assertLessEqual(box[0], box[1] + 1); self.assertLessEqual(box[2], box[1] + 1)        # nothing runs out of the window
                        pg.reload(); pg.wait_for_selector("#py-box", timeout=15000)
                        self.assertIsNone(pg.query_selector("#py-box .banner.ok"))                               # said once
                    self.app.instance = first + "x"
                    # it did not start (the starter noted it): said, with a way to try again
                    st = pyboot.read_state(self.prog); st.update(use="own", failed={"at": "2026-11-23 10:00", "why": "start", "detail": "exit 1"}); pyboot.write_state(self.prog, st)
                    pg.reload(); pg.wait_for_selector("#py-box .banner.err", timeout=15000)
                    self.assertIn("ist nicht gestartet (beim Start beendet: exit 1). Kontor läuft mit dem Python des Macs weiter.", pg.inner_text("#py-box .banner.err"))
                    self.assertEqual(pg.inner_text("#py-install"), "Erneut versuchen")
                    pg.click("#py-remove")
                    self.until(pg, "!document.querySelector('#py-remove')")
                    self.assertEqual(os.listdir(pyboot.folder(self.prog)), [pyboot.STATE])
                self.assertEqual(errors, [])
                pg.context.close()
            b.close()


class Guard(unittest.TestCase):
    """The check before an update (update_guard.py): a later version that loads another file, starts another program or lets
    another device ask for the switch is shown -- as one entry about Kontor's own Python; a file slipped into its folder
    arrives as a finding. And what the version before this one says about this one."""

    @classmethod
    def setUpClass(cls):
        import update_guard as G
        from test_update_guard import program
        cls.G, cls.files = G, program()
        cls.scan = G.scan(cls.files)

    def changed(self, **edits):
        """What the check says about this version with these places changed (as G.compare, the installed side read once)."""
        G, new = self.G, dict(self.files)
        for rel, (old, repl) in edits.items():
            rel = rel.replace("__", ".")
            self.assertIn(old, new[rel], rel)
            new[rel] = new[rel].replace(old, repl)
        scan = G.scan(new, set(self.files))
        return G.judge(G._differences(self.scan[0], scan, set(new)), self.files, new, self.scan, scan)

    def test_a_later_change_is_one_entry_about_python(self):
        G = self.G
        found = self.changed(
            pyruntime__py=(b'"sha256": "7e58607647b5b4832092a339ff1c55eeeccee128221232509b8fc8d27957065e"', b'"sha256": "' + b"1" * 64 + b'"'),
            pyboot__py=(b'    if root != os.path.join(base, FOLDER, name):\n        return ""\n', b""),
            service__py=(b'            if not self._is_local(s):\n                return self._json(403, {"error": tr("s_nur_von_diesem_mac_aus")})\n            what, py = ', b"            what, py = "))
        asked = G.asking(found)
        self.assertEqual({f["topic"] for f in asked}, {"python"}, [(f["topic"], f["file"], f["where"]) for f in asked])
        self.assertEqual({f["level"] for f in asked}, {"critical"})
        self.assertEqual({(f["file"], f["where"]) for f in asked if not f.get("dup")}, {("pyruntime.py", "FILES"), ("pyboot.py", "exe_in()"), ("service.py", "_python_do()")})
        self.assertEqual({f["title"] for f in asked}, {"upd_t_python"})
        lines = "\n".join(l for f in asked for l in f.get("lines") or [])
        self.assertTrue(any(l.startswith("+") and '"sha256": "' + "1" * 64 in l for l in lines.splitlines()), lines)        # what changes, as lines
        self.assertIn("-if not self._is_local(s):", lines); self.assertIn("-if root != os.path.join(base, FOLDER, name):", lines)
        # what is started: each function that does it is kept as a whole
        for rel, old, new in (("pyboot.py", b'cmd = [exe, "-I", "-S", os.path.join(here, "kontor.py")]', b'cmd = ["/bin/sh", "-c", os.path.join(here, "kontor.py")]'),
                              ("pyruntime.py", b'subprocess.run([exe, "-I", "-S", "-B"] + list(args)', b'subprocess.run([exe] + list(args)'),
                              ("pyruntime.py", b"if got != size or h.hexdigest() != b[\"sha256\"]:", b"if got != size:"),
                              ("pyruntime.py", b"                same(arch, tmp)\n", b""),
                              ("pyruntime.py", b"                tried(self.here, exe, str(b[\"version\"]))\n                self._step(job, \"switch\")", b"                self._step(job, \"switch\")"),
                              ("kontor.py", b"pyboot.launch_python(HERE), os.path.join(HERE, \"kontor.py\")", b"\"/tmp/python3\", os.path.join(HERE, \"kontor.py\")")):
            with self.subTest(old[:40]):
                self.assertTrue(G.asking(self.changed(**{rel.replace(".", "__"): (old, new)})))
        # texts, the page, the tests' stand-ins: an ordinary update, as ever
        self.assertEqual(G.asking(self.changed(pyruntime__py=(b"log.info(\"Python: Kontor's own removed\")", b"log.info(\"Python: removed\")"))), [])

    def test_the_lists_name_it(self):
        G = self.G
        self.assertIn(".python/", G.MADE_HERE.splitlines())
        self.assertIn("made by a program", G.beside(".python/state.json", b'{"use": "own"}') or "")      # in a git clone: never part of an update
        self.assertFalse(G.installable(".python/cpython-3.15.2-20261110/python/bin/python3.15"))
        with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
            self.assertIn(".python/", f.read().splitlines())
        self.assertEqual(G.RULE_LEVEL["pyruntime.py"]["FILES"], ("python", "risk")); self.assertEqual(G.RULE_LEVEL["service.py"]["_python_do"], ("python", "risk"))
        self.assertEqual(G.RULE_LEVEL["pyboot.py"]["exe_in"], ("python", "risk"))
        self.assertEqual(set(G.CHECKED["pyboot.py"]), {"_serve", "_again"}); self.assertEqual(set(G.CHECKED["pyruntime.py"]), {"run_python", "unmark", "sign"})
        self.assertEqual(G.TOPIC_TEXT["python"], ("upd_t_python", "upd_w_python"))
        self.assertTrue(tr("upd_t_python") != "upd_t_python" and tr("upd_w_python") != "upd_w_python")
        # nothing new is taken for harmless: Python's parts that reach out stay as they were
        self.assertFalse({"subprocess", "ssl", "socket", "select", "sqlite3"} & set(G.HARMLESS))

    def test_what_the_version_before_says(self):
        """The update that brought Kontor's own Python, as the version before it (3.17.5) read it: the new place files are
        loaded from, the programs started, the check itself -- asked about, as the changelog says."""
        from test_update_guard import _commit, _files_at, entries
        if not _commit("ab4c520") or not _commit("c837237"):
            self.skipTest("the history before this version is not here (GitHub checks out the newest commit only)")
        import types
        old = _files_at("ab4c520")
        before = types.ModuleType("update_guard_before")
        exec(compile(old["update_guard.py"].decode("utf-8"), "update_guard.py", "exec"), before.__dict__)
        found = before.compare(old, _files_at("c837237"), limit=5000)    # that update (3.17.12) -- not today's files, which keep growing
        asks = entries(before.asking(found))
        crit = {t for t, xs in asks.items() if any(x["level"] == "critical" for x in xs)}
        self.assertTrue({"check", "address:astral-sh/python-build-standalone", "new_program:pyboot.py", "new_program:pyruntime.py", "new_program:xattr",
                         "new_program:codesign"} <= crit, sorted(asks))
        mine = {t for t, xs in asks.items() if any(x["file"] in ("pyboot.py", "pyruntime.py", "pyselftest.py", "kontor.py", "install.sh", "update_guard.py", "updates.py") for x in xs)}
        self.assertLessEqual(len(mine), 24, sorted(mine))
        self.assertLess(len(json.dumps(found)), 64 * 1024)


if __name__ == "__main__":
    unittest.main()
