"""Kontor's own Python on a real Mac -- what GitHub's macOS job checks beyond the tests (tests/test_python.py), with the build
Kontor names (pyruntime.py), really loaded from GitHub, and with Kontor's service as launchd runs it:

  build            the build is loaded as named, a wrong file refused; it carries a signature the Mac accepts; without one
                   (taken off here) and with the mark of files from the internet it is made runnable again by Kontor itself
  parts EXE        what the job's other steps check in Apple's Python, in Kontor's own: every part of Kontor loaded, the
                   internet reader in its sandbox, https to GitHub with the Mac's certificates
  service          against the installed service (install.sh): it runs in Kontor's own Python, started by Apple's; started
                   anew by launchd; damaged -- the Mac's Python serves by itself and says
                   so; tried again
  uninstall        from the page while Kontor runs in its own Python: the service ends, the starter removes that Python
                   after it; nothing of Kontor is left but its program folder
  update DIR       an installation of the version before (a clone in DIR, its service running) gets this version over its
                   own update, with the approval its check asks for -- and runs on; then it loads Kontor's own Python

Usage: python3 tests/mac_python.py build|parts|service|uninstall|update ...   (made-up password, no data; macOS only)"""
import http.cookiejar
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASSWORD = "nur-ein-test-passwort"
PORT = 8765
LOG = os.path.expanduser("~/Library/Application Support/Kontor/kontor.log")


def sh(*cmd, check=True, **kw):
    r = subprocess.run(list(cmd), capture_output=True, text=True, **kw)
    if check and r.returncode != 0:
        raise SystemExit("%s: exit %d\n%s%s" % (" ".join(cmd), r.returncode, r.stdout, r.stderr))
    return r


# ---------------------------------------------------------------------------------------------------------------------------
def build() -> None:
    import llm_local as L
    import pyboot
    import pyruntime as R
    prog = os.path.realpath(tempfile.mkdtemp(prefix="Kontor CI ", dir=os.path.expanduser("~")))      # in the home folder, as Kontor's program folder is (a blank in its name)
    rt, b = R.Runtime(prog), R.build()
    assert b, "no build named for this Mac (%s)" % L.asset_tag()
    print("build:", b["url"], b["size"], b["sha256"])
    # what a Python is tried with holds in the Python this Mac has had all along (else it would say nothing about the new one)
    work = tempfile.mkdtemp(prefix="kontor-python-")
    r = subprocess.run([sys.executable, "-I", "-S", "-B", R.SELFTEST], capture_output=True, text=True, timeout=300, env=R._env(work), cwd=work)
    print("tried in Apple's Python:", r.stdout.strip(), r.stderr.strip()[-600:])
    assert r.returncode == 0 and json.loads(r.stdout.strip().splitlines()[-1])["ok"], r.stdout
    keep = dict(R.FILES[L.asset_tag()])
    R.FILES[L.asset_tag()] = dict(keep, sha256="0" * 64)              # not the file named: refused, nothing of it stays
    assert not rt.install_now(print) and os.listdir(pyboot.folder(prog)) == [], os.listdir(pyboot.folder(prog))
    R.FILES[L.asset_tag()] = keep
    assert rt.install_now(print), rt.job
    exe, root = pyboot.chosen(prog), os.path.join(pyboot.folder(prog), b["name"])
    assert exe and sorted(os.listdir(pyboot.folder(prog))) == sorted([b["name"], pyboot.STATE]), os.listdir(pyboot.folder(prog))
    print("its program:", exe, "-- files of macOS in it:", len(R.programs(root)))
    arm = L.asset_tag() == "macos-arm64"
    if arm:                                                            # as shipped: a signature the Mac accepts
        sh("/usr/bin/codesign", "--verify", exe)
    assert b"quarantine" not in subprocess.run(["/usr/bin/xattr", exe], capture_output=True).stdout      # Kontor's download carries no mark
    # a signature the Mac does not accept (taken off here), and the mark of files from the internet: made runnable by Kontor
    sh("/usr/bin/codesign", "--remove-signature", exe)
    print("without its signature:", R.starts(prog, exe) or "starts (this Mac runs programs without one)")
    assert not arm or R.starts(prog, exe), "a program without a signature ran on Apple's own chip?"
    sh("/usr/bin/xattr", "-w", "com.apple.quarantine", "0081;00000000;Safari;", exe)
    R.runnable(prog, root, exe)
    assert R.starts(prog, exe) == "" and b"quarantine" not in subprocess.run(["/usr/bin/xattr", exe], capture_output=True).stdout
    assert R.tried(prog, exe, R.VERSION)["version"] == R.VERSION
    with open(os.path.join(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir(), "kontor-python"), "w") as f:
        f.write(exe)
    print("ok")


# ---------------------------------------------------------------------------------------------------------------------------
def parts(exe: str) -> None:
    import pyruntime as R
    own = lambda code, **kw: subprocess.run([exe, "-I", "-S", "-c", "import sys; sys.path.insert(0, %r)\n%s" % (ROOT, code)], capture_output=True, text=True, timeout=300, **kw)
    r = subprocess.run([exe, "-I", "-S", "-B", os.path.join(ROOT, "pyselftest.py")], capture_output=True, text=True, timeout=300, cwd=tempfile.gettempdir())
    print(r.stdout, r.stderr)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["ok"] and out["version"] == R.VERSION, out
    # the internet reader: started by Kontor's own Python it is that Python again (-I -S), inside its sandbox -- where it may
    # read its own files though they lie in the home folder, and nothing else there; a host it was not given is refused
    r = own("import json, tempfile, web_search as W\n"
            "rd = W.Reader(tempfile.mkdtemp(), lambda: 'strict'); c = rd.command()\n"
            "assert c[0] == W.SANDBOX and c[3:5] == [W.python_exe(), '-I'], c\n"
            "print(json.dumps([W.python_exe(), rd({'url': 'https://example.org/x', 'hosts': ['de.wikipedia.org'], 'as': 'json', 'timeout': 5}),\n"
            "                  rd({'url': 'https://raw.githubusercontent.com/stecrz/Kontor/main/VERSION', 'hosts': ['raw.githubusercontent.com'], 'as': 'text', 'timeout': 30})]))")
    print(r.stdout, r.stderr)
    used, refused, fetched = json.loads(r.stdout.strip().splitlines()[-1])
    assert os.path.realpath(used) == os.path.realpath(exe) and refused == {"ok": False, "error": "host"}, (used, refused)
    # ... and fetches as it does in Apple's Python (the sandbox the same, the certificates the Mac's)
    r = subprocess.run([sys.executable, "-c", "import json, tempfile, web_search as W\n"
                        "print(json.dumps(W.Reader(tempfile.mkdtemp(), lambda: 'strict')({'url': 'https://raw.githubusercontent.com/stecrz/Kontor/main/VERSION', 'hosts': ['raw.githubusercontent.com'], 'as': 'text', 'timeout': 30})))"],
                       capture_output=True, text=True, timeout=120, cwd=ROOT)
    apple = json.loads(r.stdout.strip().splitlines()[-1])
    print("reader in its sandbox -- Kontor's own Python:", str(fetched)[:120], "| Apple's:", str(apple)[:120])
    assert fetched.get("ok") == apple.get("ok"), (fetched, apple)
    # its sandbox: temporary files only -- never Kontor's own temporary folders, nothing in the home folder
    r = own("import os, subprocess as S, tempfile, web_search as W\n"
            "os.environ['TMPDIR'] = S.run(['getconf', 'DARWIN_USER_TEMP_DIR'], capture_output=True, text=True).stdout.strip(); tempfile.tempdir = None\n"
            "d = os.path.realpath(tempfile.mkdtemp()); mine = os.path.realpath(tempfile.mkdtemp(prefix='kontor-'))\n"
            "w = lambda f: S.run(['/usr/bin/sandbox-exec', '-p', W.reader_profile(d), W.python_exe(), '-I', '-S', '-c', 'open(%r, \"w\").close()' % f]).returncode == 0\n"
            "rd = lambda f: S.run(['/usr/bin/sandbox-exec', '-p', W.reader_profile(d), W.python_exe(), '-I', '-S', '-c', 'open(%r).read()' % f]).returncode == 0\n"
            "assert w(os.path.join(os.path.dirname(mine), 'reader-ok')), 'its temporary files'\n"
            "assert not w(mine + '/no') and not w(os.path.expanduser('~/kontor-reader-no')), 'written where it must not'\n"
            "open(os.path.expanduser('~/kontor-reader-secret'), 'w').write('x')\n"
            "assert not rd(os.path.expanduser('~/kontor-reader-secret')) and rd(os.__file__), 'read in the home folder'\n"
            "os.remove(os.path.expanduser('~/kontor-reader-secret')); print('sandbox ok')")
    print(r.stdout, r.stderr)
    assert r.returncode == 0 and "sandbox ok" in r.stdout
    # https with the Mac's certificates: the update check reaches GitHub; the data key through openssl
    r = own("import os, storage, updates\n"
            "u = updates.check('stecrz/Kontor', look=False); print(u['available'], u['error'])\n"
            "assert not u['error'] and u['available'], u\n"
            "k = os.urandom(32); assert storage.decrypt(k, storage.encrypt(k, b'x')) == b'x' and storage._pass_mode() == 'fd'\n"
            "import mm_history; mm_history._aes_cbc(); mm_history._sqlite_lib(); print('parts ok')")
    print(r.stdout, r.stderr)
    assert r.returncode == 0 and "parts ok" in r.stdout
    print("ok")


# ---------------------------------------------------------------------------------------------------------------------------
class Client:
    """The page's requests against the service on this Mac."""

    def __init__(self):
        self.base, self.csrf = "http://127.0.0.1:%d" % PORT, None
        self.op = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **({"X-CSRF-Token": self.csrf} if self.csrf else {})})
        try:
            with self.op.open(req, timeout=120) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def sign_in(self, other_than=None, seconds=180.0, version=None):
        """Waits until the service answers (as another start than the one named, in the version named), then signs in --
        the first time by setting the password. Returns this start's name."""
        t0, last = time.time(), None
        while time.time() - t0 < seconds:
            try:
                code, s = self.call("/api/session")
                last = s
                if code == 200 and s.get("instance") != other_than and (version is None or s.get("version") == version):
                    self.csrf = None
                    # (the first time: the setup's request -- without Touch ID, which this machine could only ask for in a window)
                    code, r = self.call("/api/setup", {"password": PASSWORD, "touchid": False}) if s.get("setup_needed") else self.call("/api/login", {"password": PASSWORD})
                    assert code == 200, (code, r)
                    self.csrf = r["csrf"]
                    return s["instance"]
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
        raise SystemExit("the service does not answer as expected (last: %r)\n%s" % (last, log_tail()))

    def python(self):
        code, r = self.call("/api/python")
        assert code == 200, (code, r)
        return r["python"]

    def job(self, seconds=600.0):
        """Waits for the job that loads and tries Python; its end."""
        t0 = time.time()
        while time.time() - t0 < seconds:
            try:
                st = self.python()
                if not st["job"] or st["job"]["state"] != "running":
                    return st
            except (OSError, ValueError, AssertionError):       # (the service is already starting anew)
                return None
            time.sleep(0.5)
        raise SystemExit("the job does not end\n" + log_tail())


def log_tail(n=40) -> str:
    try:
        with open(LOG, encoding="utf-8") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return "(no log)"


def served_by() -> str:
    """Which Python the service's last start runs in (from Kontor's log)."""
    with open(LOG, encoding="utf-8") as f:
        lines = [line.split("Python ", 1)[1].strip() for line in f if " INFO kontor: Python " in line]
    return lines[-1] if lines else ""


def processes() -> list:
    """Kontor's processes as launchd runs them: [(pid, parent, command)]."""
    out = sh("/bin/ps", "-axo", "pid=,ppid=,command=").stdout.splitlines()
    return [(int(x.split()[0]), int(x.split()[1]), " ".join(x.split()[2:])) for x in out if "kontor.py --quiet start" in x]


def service() -> None:
    import pyboot
    import pyruntime as R
    own, mac = "%s (Kontor's own)" % R.VERSION, "(the Mac's)"
    c = Client()
    first = c.sign_in()
    st = c.python()
    print("after install.sh:", json.dumps(st))
    assert st["running"] == {"version": R.VERSION, "own": True, "ended": ""} and st["use"] == "own" and not st["restart"] and not st["failed"], st
    assert served_by() == own, served_by()
    ps = processes()
    print("\n".join(map(str, ps)))
    starter = [p for p in ps if p[1] == 1]
    assert len(ps) == 2 and len(starter) == 1, ps                    # the starter (launchd's child) and the service (the starter's)
    assert not pyboot.inside(ROOT, starter[0][2].split()[0]), starter  # launchd starts the Mac's own Python, as ever ...
    kid = [p for p in ps if p[1] == starter[0][0]]
    assert len(kid) == 1 and pyboot.inside(ROOT, kid[0][2].split()[0]) and " -I -S " in kid[0][2], ps      # ... which runs the service in Kontor's own
    plist = sh("/usr/bin/plutil", "-p", os.path.expanduser("~/Library/LaunchAgents/de.kontor.service.plist")).stdout
    assert ".python" not in plist, plist
    code, status = c.call("/api/status")
    assert code == 200 and status["python"] == "", status.get("python")
    # no way back by choice (user, 2026-11-23: always the newest Python): the page cannot ask for the Mac's Python
    code, r = c.call("/api/python", {"action": "apple"})
    assert code == 400, (code, r)
    loads = lambda: open(LOG, encoding="utf-8").read().count("GET https://github.com/astral-sh/")
    before = loads()
    third = first
    # started anew by launchd while it runs in its own Python (as after an update): in its own again, and nothing is noted
    # against it -- whatever the service that ran before still held for a moment
    sh("/bin/launchctl", "kickstart", "-k", "gui/%d/de.kontor.service" % os.getuid())
    third = c.sign_in(other_than=third)
    st = c.python()
    assert served_by() == own and st["running"]["own"] and not st["failed"] and not st["restart"], (served_by(), st, log_tail(30))
    assert len(processes()) == 2, processes()
    # damaged since (its program emptied): the next start serves in the Mac's Python at once, says so, and stays there
    exe = pyboot.chosen(ROOT)
    assert exe
    open(exe, "w").close()
    sh("/bin/launchctl", "kickstart", "-k", "gui/%d/de.kontor.service" % os.getuid())
    fourth = c.sign_in(other_than=third)
    st = c.python()
    print("damaged:", json.dumps(st))
    assert served_by().endswith(mac) and not st["running"]["own"] and st["failed"] and st["failed"]["why"] in ("exec", "start"), (served_by(), st)
    assert "did not start" in log_tail(60)
    code, status = c.call("/api/status")
    assert status["python"] == "failed", status.get("python")
    sh("/bin/launchctl", "kickstart", "-k", "gui/%d/de.kontor.service" % os.getuid())
    fifth = c.sign_in(other_than=fourth)
    assert served_by().endswith(mac) and c.python()["failed"], served_by()
    # "try again": the damaged build is loaded anew, checked, tried -- and Kontor runs in its own Python again
    code, r = c.call("/api/python", {"action": "install"})
    assert code == 200, r
    st = c.job(900)
    assert st is None or st["job"]["state"] == "done", st
    c.sign_in(other_than=fifth)
    st = c.python()
    assert served_by() == own and st["running"]["own"] and not st["failed"], (served_by(), st)
    assert loads() == before + 1, (loads(), before)
    print("ok")


# ---------------------------------------------------------------------------------------------------------------------------
def uninstall() -> None:
    import pyboot
    c = Client()
    c.sign_in()
    st = c.python()
    assert st["running"]["own"], st
    before = processes()
    code, r = c.call("/api/uninstall", {"password": PASSWORD, "program_folder": False})
    print(json.dumps(r)[:1500])
    assert code == 200 and pyboot.folder(ROOT) in r.get("removed", []), (code, r)
    t0 = time.time()
    while time.time() - t0 < 120 and (processes() or os.path.lexists(pyboot.folder(ROOT))):
        time.sleep(0.5)
    assert not processes(), (before, processes())                    # the service has ended, and the starter after it ...
    assert not os.path.lexists(pyboot.folder(ROOT)), os.listdir(pyboot.folder(ROOT))       # ... which took Kontor's own Python along
    assert os.path.isfile(os.path.join(ROOT, "kontor.py"))           # the program folder stays, as asked
    assert not os.path.exists(os.path.expanduser("~/Library/LaunchAgents/de.kontor.service.plist"))
    data = os.path.dirname(LOG)
    left = [n for n in (os.listdir(data) if os.path.isdir(data) else []) if n.endswith(".enc") or n in ("key.json", "start.json", "kontor.log")]
    assert not left, left
    listed = sh("/bin/launchctl", "print", "gui/%d/de.kontor.service" % os.getuid(), check=False)
    assert listed.returncode != 0, listed.stdout[:600]               # launchd no longer knows the service
    print("ok")


# ---------------------------------------------------------------------------------------------------------------------------
def update(old: str) -> None:
    with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as f:
        new = f.read().strip()
    with open(os.path.join(old, "VERSION"), encoding="utf-8") as f:
        was = f.read().strip()
    c = Client()
    first = c.sign_in(version=was)
    print("installed:", was, "-- this version:", new)
    code, r = c.call("/api/update/check", {})
    info = r.get("info") or {}
    assert code == 200 and info.get("newer") and not info.get("error"), r
    rev = info.get("review") or {}
    asked = [f for f in rev.get("findings") or [] if f.get("level") != "plain"]
    print("the installed version's check of the new files: %d finding(s), %d to approve" % (len(rev.get("findings") or []), len(asked)))
    for f in asked[:60]:
        print("  ", f.get("level"), f.get("topic") or f.get("kind"), f.get("file"), f.get("where") or f.get("what"))
    code, r = c.call("/api/update/install", {})                      # without your approval: it waits
    assert code == 200, r
    if not r.get("ok"):
        assert r.get("needs_approval"), r
        rev = r.get("review") or rev
        code, r = c.call("/api/update/install", {"approved": rev.get("digest") or ""})
    else:
        assert not asked, asked
    assert code == 200 and r.get("ok"), r
    print(r.get("text"))
    with open(os.path.join(old, "VERSION"), encoding="utf-8") as f:
        now = f.read().strip()
    second = c.sign_in(other_than=first, version=now)                 # runs on, in the Mac's Python: nothing was chosen
    st = c.python()
    print("after the update:", now, json.dumps(st))
    assert not st["running"]["own"] and st["use"] == "" and st["supported"] and st["offered"], st
    code, status = c.call("/api/status")
    assert status["python"] == "old", status.get("python")           # ... and says that there is something to do
    code, r = c.call("/api/python", {"action": "install"})            # on your click: loaded, checked, tried, switched
    assert code == 200, r
    st = c.job(900)
    assert st is None or st["job"]["state"] == "done", st
    c.sign_in(other_than=second)
    st = c.python()
    assert st["running"]["own"] and st["use"] == "own" and not st["failed"], st
    print("ok")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if sys.platform != "darwin" or what not in ("build", "parts", "service", "uninstall", "update"):
        raise SystemExit(__doc__)
    {"build": build, "parts": parts, "service": service, "uninstall": uninstall, "update": update}[what](*sys.argv[2:])
