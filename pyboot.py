"""Which Python runs Kontor's service -- asked at every start, before any other part of Kontor is loaded.

launchd starts the service with the Python `kontor.py install` wrote into its file: the Mac's own (Apple's). With Kontor's
own Python chosen (pyruntime.py: a fixed build, checked and tried, in the program folder under .python/), that process does
not serve itself: it stays as the starter -- it loads nothing else of Kontor, reads no data, opens no connection -- and runs
the service as its child in Kontor's own Python. macOS goes on seeing the program it has known all along (what you allowed
it -- steering MoneyMoney, your folders -- stays as it is), and whatever happens to the own Python, the starter is there:

  - the own Python does not get Kontor running (gone, damaged, ends or hangs before Kontor's parts are loaded): noted in the
    state file with the reason, and the service runs in the starter's Python at once, as before -- until you try again;
  - Kontor's parts are loaded in it, and yet the service ends before it serves: that may be nothing of the Python's (after a
    restart the service that ran before can hold Kontor's address for a moment longer), so it is tried once more after a
    short while. Ends it again, the starter's Python takes over -- noted only when that one does get Kontor to serve (else
    it was nothing of the Python's: the address taken, Kontor already running), and the next start tries the own one again;
  - the service asks for a restart (a new version, another Python chosen): it ends with EX_RESTART, the starter starts
    itself anew and decides again;
  - the service ends in any other way: so does the starter, and launchd starts both again;
  - an uninstall carried out by the service leaves a note: the starter removes the folder once nothing runs from it.

The only program ever started here is the one inside .python/ that the state file names -- a plain file really inside that
folder --, with Kontor's own kontor.py and the words it was started with.

This file and kontor.py must keep running with Python 3.9, whatever the rest of Kontor needs one day; this file loads
nothing of Kontor, only the standard library.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

FOLDER = ".python"                     # in the program folder: the builds, the state file
STATE = "state.json"
REMOVE = "remove"                      # left by an uninstall that ran in the own Python: the starter removes the folder after it
EX_RESTART = 75                        # the service ends with it when it wants to be started anew
ENV_STARTER = "KONTOR_STARTER"         # in the service's environment: the starter's process number ...
ENV_READY = "KONTOR_STARTER_READY"     # ... where the service says that Kontor's parts are loaded in it, and then that it serves ...
ENV_PYTHON = "KONTOR_STARTER_PYTHON"   # ... and the program the starter runs it in
START_SECONDS = 120                    # longer than that until Kontor's parts are loaded: taken as not starting
RETRY_SECONDS = 3                      # before the one further try when it ended with Kontor's parts loaded, before Kontor served
DIR_RE = re.compile(r"cpython-[0-9][0-9A-Za-z._+-]{0,60}")
LOADED, SERVES = b"1", b"2"            # the service's two words to the starter
notes: list = []                       # what a start has to say (kontor.py writes it to the log once that is open)
pending: list = []                     # the own Python ended between the two words: (here, why, detail) -- noted when this one serves


def folder(here: str) -> str:
    return os.path.join(here, FOLDER)


def read_state(here: str) -> dict:
    """The state file -- {} when there is none or it does not read (then the Mac's own Python serves, as ever)."""
    try:
        with open(os.path.join(folder(here), STATE), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(here: str, st: dict) -> None:
    """In one piece: written beside it, then put in its place."""
    d = folder(here)
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, STATE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, os.path.join(d, STATE))


def inside(here: str, path: str) -> bool:
    """Is this path really inside Kontor's own folder for Python (links followed)?"""
    root = os.path.realpath(folder(here))
    return bool(path) and os.path.realpath(path).startswith(root + os.sep)


def exe_in(here: str, name: object) -> str:
    """The program of the build unpacked in .python/<name>: a plain file that can be run, really inside that folder, the
    folder really inside the program folder -- else ""."""
    if not isinstance(name, str) or not DIR_RE.fullmatch(name):
        return ""
    base = os.path.realpath(here)
    root = os.path.realpath(os.path.join(folder(here), name))
    if root != os.path.join(base, FOLDER, name):
        return ""
    exe = os.path.realpath(os.path.join(root, "python", "bin", "python3"))
    return exe if exe.startswith(root + os.sep) and os.path.isfile(exe) and os.access(exe, os.X_OK) else ""


def chosen(here: str, st: object = None) -> str:
    """The own Python the service is to run in -- "" when the Mac's is to serve: none chosen, or it did not start."""
    st = read_state(here) if not isinstance(st, dict) else st
    if st.get("use") != "own" or st.get("failed"):
        return ""
    return exe_in(here, st.get("dir"))


def starter() -> int:
    """In the service a starter runs: the starter's process number -- else 0."""
    try:
        return max(0, int(os.environ.get(ENV_STARTER) or 0))
    except ValueError:
        return 0


def is_start(args: list) -> bool:
    """Is this the command that runs the service (the first word that is no option)?"""
    for a in args:
        if not a.startswith("-"):
            return a == "start"
    return False


def running() -> str:
    """The Python this very process runs in, as it was started."""
    return sys.executable or ""


def serving(here: str) -> str:
    """The own Python this very process runs the service in -- "" when it is not one of Kontor's own folder."""
    exe = os.environ.get(ENV_PYTHON) or "" if starter() else running()
    return os.path.realpath(exe) if inside(here, exe) else ""


def launch_python(here: str) -> str:
    """The Python launchd is to start Kontor with: the one running now -- unless that is Kontor's own. launchd never starts
    that one itself: the starter must stay the Mac's Python."""
    exe = running()
    return exe if exe and not inside(here, exe) else "/usr/bin/python3"


def _fail(here: str, why: str, detail: str) -> None:
    """The own Python did not get Kontor running: noted (it is not tried again until you say so), and said in the log."""
    notes.append("Kontor's own Python did not start (%s%s) -- the service runs in the Mac's Python" % (why, ": " + detail if detail else ""))
    try:
        st = read_state(here)
        st["failed"] = {"at": time.strftime("%Y-%m-%d %H:%M"), "why": why, "detail": str(detail)[:200]}
        write_state(here, st)
    except OSError as e:
        notes.append("... and that could not be noted (%s): the next start tries it again" % e)


def start(here: str, argv: list) -> None:
    """First thing in `kontor.py start`. Comes back when the service is to run in this very process: no own Python chosen,
    this process is the service a starter runs, or the own Python did not get Kontor to serve (`notes` says so, or `pending`
    until this process serves). Else it never comes back: this process is the starter, and ends when the service does."""
    if starter():
        return
    st = read_state(here)
    if st.get("use") != "own" or st.get("failed"):
        return
    why, detail = _serve(here, st.get("dir"), argv)
    if why == "ended":                      # Kontor's parts were loaded in it, and it ended before Kontor served: once more
        time.sleep(RETRY_SECONDS)           # after a moment (a service that ran before may have held Kontor's address still)
        why, detail = _serve(here, st.get("dir"), argv)
    if why == "ended":                      # again: whether that is the Python's shows when this one gets further (serves)
        pending.append((here, why, detail))
    else:
        _fail(here, why, detail)


def _serve(here: str, name: object, argv: list) -> tuple:
    """Runs the service in the own Python of this name -- the program found inside .python/<name>, nothing else, with
    Kontor's own kontor.py and the words this process was started with -- and waits for its end. Comes back only when it
    did not get Kontor to serve there: (why, detail) -- why "ended" when Kontor's parts were loaded in it before."""
    exe = exe_in(here, name)
    if not exe:
        return "missing", ""
    rfd, wfd = os.pipe()
    os.set_blocking(rfd, False)
    env = dict(os.environ)
    env[ENV_STARTER], env[ENV_READY], env[ENV_PYTHON] = str(os.getpid()), str(wfd), exe
    cmd = [exe, "-I", "-S", os.path.join(here, "kontor.py")] + list(argv[1:])
    got, box = [], []

    def on(sig, frame):                     # what the starter is told goes to the service (launchd ends Kontor, ctrl-C)
        got.append(sig)
        for c in box:
            try:
                c.send_signal(sig)
            except OSError:
                pass
    old = {s: signal.signal(s, on) for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    t0 = time.time()
    try:
        try:
            child = subprocess.Popen(cmd, env=env, pass_fds=(wfd,))
        except OSError as e:
            return "exec", str(e)
        finally:
            os.close(wfd)
        box.append(child)
        for sig in list(got):                   # (told in the very moment it was started)
            on(sig, None)
            got.pop()
        said, rc = b"", None
        while rc is None:
            if SERVES in said:
                rc = child.wait()               # (what the starter is told meanwhile goes on to the service: `on`)
                break
            said += _words(rfd)                 # the service's words: Kontor's parts are loaded (ready), Kontor serves (serves)
            try:
                rc = child.wait(timeout=0.05 if SERVES in said else 0.25)
            except subprocess.TimeoutExpired:
                if not said and not got and time.time() - t0 > START_SECONDS:
                    child.kill()
                    child.wait()
                    return "slow", "%d s" % START_SECONDS
        said += _words(rfd)                     # (a word and its end in the same moment)
    finally:
        os.close(rfd)
        for s, h in old.items():
            signal.signal(s, h)
    if os.path.exists(os.path.join(folder(here), REMOVE)):
        _remove(here)
        sys.exit(0)
    if got:
        sys.exit(0)
    if rc == EX_RESTART:
        _again(argv, time.time() - t0)
    if SERVES in said:
        sys.exit(rc if rc >= 0 else 128 - rc)
    return "ended" if said else "start", ("exit %d" % rc) if rc >= 0 else ("signal %d" % -rc)


def _words(fd: int) -> bytes:
    """What the service has said to the starter since the last look."""
    try:
        return os.read(fd, 8)
    except OSError:                         # (nothing there yet)
        return b""


def _again(argv: list, ran: float) -> None:
    """The starter anew, as it was started -- with the program as it is now, deciding again which Python serves."""
    if ran < 3:
        time.sleep(1)                       # (never a tight loop, whatever asked for it)
    try:
        os.execv(running(), [running()] + list(argv))
    except OSError:
        sys.exit(1)                         # launchd starts Kontor again


def _remove(here: str) -> None:
    """After an uninstall the service carried out in the own Python: the folder goes now that nothing runs from it -- and
    the program folder, when the uninstall took everything else of it."""
    try:
        with open(os.path.join(folder(here), REMOVE), encoding="utf-8") as f:
            whole = f.read().strip() == "program"
    except OSError:
        whole = False
    shutil.rmtree(folder(here), ignore_errors=True)
    if whole:
        try:
            os.rmdir(here)
        except OSError:
            pass


_said: list = []


def _say(word: bytes) -> None:
    """In the service a starter runs: one word to the starter, each once; after the last one the line is closed (its number
    may stand for something else afterwards). No program this service starts gets the line."""
    fd = os.environ.get(ENV_READY) or ""
    if not starter() or not fd.isdigit() or word in _said or SERVES in _said:
        return
    _said.append(word)
    try:
        os.set_inheritable(int(fd), False)
        os.write(int(fd), word)
        if word == SERVES:
            os.close(int(fd))
    except OSError:
        pass


def ready() -> None:
    """In the service a starter runs: Kontor's parts are loaded in this Python."""
    _say(LOADED)


def serves() -> list:
    """Kontor serves. In the service a starter runs: said to the starter -- from here on the service's end is Kontor's end.
    In the starter itself, after the own Python had ended with Kontor's parts loaded: this Python got further under the very
    same conditions, so it was the own one's -- noted now. Comes back with what there is to write to the log."""
    _say(SERVES)
    n = len(notes)
    while pending:
        _fail(*pending.pop())
    return notes[n:]


def watch() -> None:
    """In the service a starter runs: should the starter be gone, the service ends too (launchd starts both again) -- it
    would otherwise keep Kontor's address to itself."""
    pid = starter()
    if not pid:
        return

    def run():
        while os.getppid() == pid:
            time.sleep(0.5)
        signal.raise_signal(signal.SIGTERM)
    threading.Thread(target=run, name="kontor-starter", daemon=True).start()
