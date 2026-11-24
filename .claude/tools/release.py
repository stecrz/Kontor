#!/usr/bin/env python3
"""Finishes a change of Kontor in one call: the same checks and the same steps as by hand (skill "release"), done by a script
instead of a dozen chat steps -- each of which would re-read the whole conversation. It stops at the first problem and says
what to do; nothing half is ever pushed.

    python3 .claude/tools/release.py --check [--tests "<pytest arguments>"]
        only the checks, nothing is committed -- as often as wanted while working
    python3 .claude/tools/release.py "<what changes, English>" "<Bezug>: <Punkt>" ["<Bezug>: <Punkt>" ...] [--by "<Modell>: <Link>"]
        publish: own work squashed into one commit on the newest main (rebased, never `reset --soft` onto a foreign state),
        checks, VERSION = main + 1 (third digit), changelog section on top, the guard's version chain, push. Another chat was
        faster (push refused): VERSION and changelog dropped, rebased, checked again, next number -- by itself, up to 4 times.
        --by: model and link of this session, e.g. "Claude Opus 5.5: https://claude.ai/code/session_..." -- once per clone
        (kept in .git/kontor-by). --version X.Y.0: a big version step (only after the user agreed; skill "major").
        --wait: wait for GitHub's tests of this version (at most ~9 min) -- only for a big version; otherwise not: a red run
        shows in the next chat's briefing, which fixes it ("fix ci").

The checks: node --check, pyflakes, ESLint (page changed), the tests the change touches (tests/affected.py) without a browser,
400 random cases when money logic changed, the starter with Python 3.9 when it changed, and what --tests names (with a browser,
e.g. the change's new page test: --tests "tests/test_e2e.py -k drawer"). The page tests in a browser run on GitHub for every
push (Chrome and Safari's engine) -- here they take long and are flaky on a slow machine. The checks run in the background and
are kept per state of the files: a call waits at most ~9 minutes; still running -> "läuft noch", the same command again waits on.

A conflict while rebasing: the files are named, the rebase stays open -- resolve (keep both sides), `git add`,
`git rebase --continue`, run the same command again. Exit codes: 0 done, 1 checks failed, 2 usage, 3 conflict, 4 refused,
5 checks still running."""
import glob
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GIT_DIR = os.path.join(ROOT, ".git")
STATE = os.path.join(GIT_DIR, "kontor-checks")                   # per clone: chats side by side never share it
LOG = os.path.join(GIT_DIR, "kontor-release.log")
SEEN = os.path.join(GIT_DIR, "kontor-seen")                      # the main the own work was built on, kept across a conflict stop
PY = os.path.expanduser("~/kontor-venv/bin/python") if os.path.exists(os.path.expanduser("~/kontor-venv/bin/python")) else sys.executable
PY39 = os.path.expanduser("~/py39/bin/python")
OWN = ("VERSION", "CHANGELOG.md")                                   # written by this script only
CALC = ("rules.py", "model.py", "report.py", "core.py", "realestate.py", "tax.py", "tests/test_fuzz.py")   # money logic: more random cases
STARTER = ("kontor.py", "pyboot.py", "tests/test_python.py")       # what Apple's Python 3.9 runs
POINT = re.compile(r"^[^:\n]{2,40}: \S[^\n]*$")
BIG = 2 * 1024 * 1024
WAIT = float(os.environ.get("KONTOR_RELEASE_WAIT", "540"))         # seconds one call waits for the checks


def git(*args, check=False, timeout=120, env=None):
    r = subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True, timeout=timeout, env=env)
    if check and r.returncode != 0:
        raise SystemExit("git %s: %s" % (" ".join(args), (r.stderr or r.stdout).strip()[-400:]))
    return r


def out(*args):
    return git(*args).stdout.strip()


def say(text):
    print(text, flush=True)


def stop(text, code):
    say(text)
    sys.exit(code)


# ---------------------------------------------------------------- checks


def changed_files():
    files = set(out("diff", "--name-only", "origin/main").split())
    files.update(out("ls-files", "--others", "--exclude-standard").split())
    return sorted(f for f in files if f)


def files_key(extra, new_files=None):
    """The state of all files (changed or not, new ones too -- or only `new_files` of the new ones) and the extra tests:
    checks are kept per key. Returns (key, the new files counted)."""
    idx = os.path.join(STATE, "index")
    os.makedirs(STATE, exist_ok=True)
    if os.path.exists(os.path.join(GIT_DIR, "index")):
        shutil.copy(os.path.join(GIT_DIR, "index"), idx)
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    if new_files is None:
        new_files = sorted(out("ls-files", "--others", "--exclude-standard").split())
    git("add", "-u", env=env)
    for i in range(0, len(new_files), 200):
        git("add", "--", *[f for f in new_files[i:i + 200] if os.path.exists(os.path.join(ROOT, f))], env=env)
    tree = git("write-tree", env=env).stdout.strip()
    return hashlib.sha1((tree + "\0" + "\0".join(extra)).encode()).hexdigest()[:16], new_files


def no_browser():
    """A folder whose `playwright` cannot be imported: the tests then skip their browser parts, as they do without it."""
    d = os.path.join(STATE, "nobrowser", "playwright")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "__init__.py"), "w") as f:
        f.write('raise ImportError("browser tests run on GitHub (release.py)")\n')
    return os.path.dirname(d)


def run_logged(cmd, env):
    with open(LOG, "a", encoding="utf-8") as f:
        start = f.tell()
        f.write("\n$ %s\n" % " ".join(cmd))
        f.flush()
        try:
            code = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, env=env, timeout=3600).returncode
        except subprocess.TimeoutExpired:
            f.write("\n(timed out after an hour)\n")
            code = 124
    return code, start


def failures(since):
    """The lines of the log since `since` that name what failed."""
    with open(LOG, encoding="utf-8", errors="replace") as f:
        f.seek(since)
        lines = f.read().splitlines()
    hits = [x for x in lines if re.match(r"^(FAILED|ERROR)\b|^E\s|^\S+:\d+:\d*:? |^\s+\d+:\d+\s+error|SyntaxError", x)]
    return "\n".join(hits[:25] or lines[-15:])


def run_checks(extra):
    """Code checks and the tests the change touches (without a browser) plus `extra` (with one): (ok, text for the chat)."""
    start = time.time()
    files = changed_files()
    env = dict(os.environ, TZ="Europe/Berlin")
    quiet = dict(env, PYTHONPATH=no_browser() + os.pathsep + env.get("PYTHONPATH", ""))
    steps = [("node --check " + f, ["node", "--check", f], env) for f in ("web/app.js", "web/i18n.js", "web/sw.js")
             if os.path.exists(os.path.join(ROOT, f))]
    py = sorted(glob.glob(os.path.join(ROOT, "*.py")) + glob.glob(os.path.join(ROOT, "tests", "*.py"))
                + glob.glob(os.path.join(ROOT, ".claude", "hooks", "*.py")) + glob.glob(os.path.join(ROOT, ".claude", "tools", "*.py")))
    steps.append(("pyflakes", [PY, "-m", "pyflakes"] + [os.path.relpath(p, ROOT) for p in py], env))
    if any(f.startswith(("web/", ".github/eslint")) for f in files):
        eslint = os.path.join(ROOT, "node_modules", ".bin", "eslint")
        if not os.path.exists(eslint):
            return False, "ESLint fehlt: erst `bash .claude/tools/setup.sh`."
        steps.append(("eslint", [eslint, "-c", ".github/eslint.config.mjs", "web"], env))
    tests = subprocess.run([PY, "tests/affected.py"] + files, cwd=ROOT, capture_output=True, text=True).stdout.split()
    tests = [t for t in tests if os.path.exists(os.path.join(ROOT, t))]
    pytest = [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if tests:
        steps.append(("Tests " + " ".join(t[6:-3] for t in tests), pytest + tests, quiet))
    if any(f in CALC for f in files):
        steps.append(("400 Zufallsfälle", pytest + ["tests/test_fuzz.py"], dict(quiet, KONTOR_FUZZ_SEEDS="400")))
    if any(f in STARTER for f in files):
        if not os.path.exists(PY39):
            return False, "Python 3.9 für den Starter fehlt: erst `bash .claude/tools/setup.sh`."
        steps.append(("Starter mit Python 3.9", [PY39, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_python.py"], quiet))
    steps += [("Tests " + e, pytest + e.split(), env) for e in extra]
    for name, cmd, e in steps:
        code, since = run_logged(cmd, e)
        if code != 0:
            return False, "Prüfung fehlgeschlagen: %s\n%s\n(alles: %s)" % (name[:200], failures(since), LOG)
    took = int(time.time() - start)
    return True, "Geprüft in %d:%02d – %s; Browser-Tests der Seiten: auf GitHub" % (
        took // 60, took % 60, "; ".join(n for n, _, _ in steps if not n.startswith("node")))


def checks(extra):
    """The checks for the files as they are now, run once per state in the background (a long test run outlasts one call):
    True green, False red (said), or the call ends with exit 5 while they still run."""
    key, new_files = files_key(extra)
    with open(os.path.join(STATE, key + ".files"), "w", encoding="utf-8") as f:
        f.write("\n".join(new_files))
    result, pid_file = os.path.join(STATE, key + ".json"), os.path.join(STATE, key + ".pid")
    alive = False
    if os.path.exists(pid_file):
        try:
            os.kill(int(open(pid_file).read().strip()), 0)
            alive = True
        except (OSError, ValueError):
            pass
    if not os.path.exists(result) and not alive:
        open(LOG, "w").close()
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--run-checks", key] + sum([["--tests", e] for e in extra], []),
                             cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        with open(pid_file, "w") as f:
            f.write(str(p.pid))
    started = os.path.getmtime(pid_file) if os.path.exists(pid_file) else time.time()
    deadline = time.time() + WAIT
    while not os.path.exists(result):
        try:
            pid = int(open(pid_file).read().strip())
            os.kill(pid, 0)
            if os.waitpid(pid, os.WNOHANG)[0] == pid:              # our own child that ended (a zombie still answers kill)
                raise OSError
        except ChildProcessError:
            pass                                                    # started by an earlier call: not our child, alive
        except (OSError, ValueError):
            time.sleep(1)
            if not os.path.exists(result):
                say("Die Prüfung brach ab (%s) – denselben Befehl erneut." % LOG)
                if os.path.exists(pid_file):
                    os.remove(pid_file)
                return False
        if time.time() > deadline:
            stop("Prüfung läuft noch (seit %d min) – denselben Befehl erneut aufrufen, sie läuft weiter." % ((time.time() - started) // 60), 5)
        time.sleep(2)
    r = json.load(open(result, encoding="utf-8"))
    say(r["text"])
    if not r["ok"]:
        os.remove(result)                       # after a fix the state differs anyway; the same state again: check again
    return r["ok"]


def background(key, extra):
    """The worker of checks(): runs them and keeps the result for the key -- only if the files did not change meanwhile."""
    listed = os.path.join(STATE, key + ".files")
    new_files = open(listed, encoding="utf-8").read().split("\n") if os.path.exists(listed) else []
    ok, text = run_checks(extra)
    if files_key(extra, [f for f in new_files if f])[0] != key:      # what the tests make themselves does not count
        ok, text = False, "Dateien während der Prüfung geändert – denselben Befehl erneut."
    with open(os.path.join(STATE, key + ".json.tmp"), "w", encoding="utf-8") as f:
        json.dump({"ok": ok, "text": text}, f)
    os.replace(os.path.join(STATE, key + ".json.tmp"), os.path.join(STATE, key + ".json"))
    try:
        os.remove(os.path.join(STATE, key + ".pid"))
    except OSError:
        pass


# ---------------------------------------------------------------- publishing


def by_line(given):
    keep = os.path.join(GIT_DIR, "kontor-by")
    if given:
        with open(keep, "w", encoding="utf-8") as f:
            f.write(given.strip())
        return given.strip()
    if os.path.exists(keep):
        return open(keep, encoding="utf-8").read().strip()
    stop('Einmal je Klon angeben: --by "<Modell>: <Link dieser Sitzung>" (aus den Hinweisen der Sitzung).', 2)


def bump(main_version, wanted):
    old = tuple(int(x) for x in main_version.strip().split("."))
    if wanted:
        new = tuple(int(x) for x in wanted.split("."))
        if len(new) != 3 or new <= old or new[0] != old[0]:
            stop("--version %s passt nicht zu main (%s)." % (wanted, main_version.strip()), 2)
        return wanted
    return "%d.%d.%d" % (old[0], old[1], old[2] + 1)


def changelog(version, points):
    path = os.path.join(ROOT, "CHANGELOG.md")
    text = open(path, encoding="utf-8").read()
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:
        now = datetime.now()
    section = "## %s (%s)\n%s\n\n" % (version, now.strftime("%Y-%m-%d %H:%M"), "\n".join("- " + p for p in points))
    i = text.find("\n## ")
    text = (text[:i + 1] + section + text[i + 1:]) if i >= 0 else text.rstrip("\n") + "\n\n" + section
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def back_to_wip():
    """The version commit back to plain own work (VERSION and changelog as on the main below it)."""
    git("checkout", "HEAD~1", "--", *OWN, check=True)
    git("commit", "--amend", "-q", "--no-verify", "-m", "wip", check=True)


def guard():
    spec = importlib.util.spec_from_file_location("kontor_guard", os.path.join(ROOT, ".claude", "hooks", "guard.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    return g


def guard_says(seen):
    """The lock before the push, knowing the main the work was built on: lines of versions already in it the work changed on
    purpose (named, so it can be traced); lines of versions after it lost lock it -- unless KONTOR_PUSH_OK=1 after weighing."""
    g = guard()
    why = g.push_check("git push origin HEAD:main", ROOT, seen=seen)
    if not why:
        mine = g.lost_lines(ROOT, "origin/main", "HEAD")
        if mine:
            say("Bewusst geändert: %d Zeile(n) aus %s – standen schon in deinem Ausgangsstand %s."
                % (len(mine), ", ".join(sorted({g._subject(ROOT, c) for c, f, l in mine})), out("show", seen + ":VERSION") or seen[:7]))
    elif os.environ.get("KONTOR_PUSH_OK") == "1" and why.startswith("Dein Stand löscht Zeilen von Versionen"):
        say("KONTOR_PUSH_OK=1 – nach dem Abwägen bewusst ersetzt:\n" + why.split("\nDie fremde Version")[0])
        return ""
    return why


def seen_base(base):
    """The main the own work was built on: the oldest of the fork point now and the one kept from a run that stopped at a
    conflict (after `git rebase --continue` the fork point is already the newer main -- what came there the work never had)."""
    try:
        kept = open(SEEN, encoding="utf-8").read().strip()
    except OSError:
        kept = ""
    if kept and git("merge-base", "--is-ancestor", kept, base).returncode == 0:
        return kept
    return base


def forget_seen():
    try:
        os.remove(SEEN)
    except OSError:
        pass


def theirs(seen, files):
    """Per file in a conflict: the newer versions on main that changed it since the work's own start."""
    lines = []
    for f in files:
        vs = out("log", "--format=%s", "%s..origin/main" % seen, "--", f).splitlines()
        lines.append("- %s: %s" % (f, "; ".join(v[:70] for v in vs[:3]) or "?"))
    return "\n".join(lines)


def repo_slug():
    m = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?/?$", out("remote", "get-url", "origin"))
    return m.group(1) if m else "stecrz/Kontor"


def wait_for_github(sha):
    slug, deadline = repo_slug(), time.time() + 540
    while time.time() < deadline:
        r = subprocess.run(["gh", "run", "list", "-R", slug, "-c", sha, "-L", "1", "--json", "databaseId,status,conclusion"],
                           capture_output=True, text=True)
        runs = json.loads(r.stdout or "[]") if r.returncode == 0 else []
        if runs and runs[0]["status"] == "completed":
            if runs[0]["conclusion"] == "success":
                return say("GitHub: grün.")
            jobs = subprocess.run(["gh", "run", "view", str(runs[0]["databaseId"]), "-R", slug, "--json", "jobs", "-q",
                                   '.jobs[] | select(.conclusion=="failure") | .name'], capture_output=True, text=True).stdout.strip()
            return say("GitHub: ROT (%s) – %s\nFehler: gh run view %s -R %s --log-failed | grep -E 'FAILED|Error' | head -30"
                       % (runs[0]["conclusion"], jobs.replace("\n", "; "), runs[0]["databaseId"], slug))
        time.sleep(20)
    say("GitHub: läuft noch – Ergebnis meldet das Lagebild.")


def tidy_branches():
    """Claude Code gives every session a branch claude/...; Kontor publishes on main only. Any claude/... branch on GitHub
    whose work is wholly in main is left over: deleted (one whose work is not in main yet -- another chat's -- stays)."""
    for line in out("ls-remote", "--heads", "origin", "claude/*").splitlines():
        sha, ref = (line.split() + ["", ""])[:2]
        name = ref[len("refs/heads/"):]
        if not name.startswith("claude/"):
            continue
        if git("cat-file", "-e", sha + "^{commit}").returncode != 0:
            git("fetch", "-q", "--depth=50", "origin", ref)
        if git("merge-base", "--is-ancestor", sha, "origin/main").returncode == 0:
            if git("push", "-q", "origin", "--delete", name).returncode == 0:
                say("Übrig gebliebenen Zweig %s gelöscht (steckt ganz in main)." % name)


def publish(subject, points, by, wanted, wait, extra):
    if git("rev-parse", "--verify", "-q", "origin/main").returncode != 0:
        git("fetch", "-q", "origin", "main", check=True)
    if os.path.exists(os.path.join(GIT_DIR, "rebase-merge")) or os.path.exists(os.path.join(GIT_DIR, "rebase-apply")):
        stop("Ein Rebase ist noch offen: Konflikte lösen, `git add`, `git rebase --continue`, dann erneut.", 3)
    base = out("merge-base", "HEAD", "origin/main")
    git("add", "-A", check=True)
    big = [f for f in out("diff", "--cached", "--name-only", "--diff-filter=A", base).splitlines()
           if os.path.isfile(os.path.join(ROOT, f)) and os.path.getsize(os.path.join(ROOT, f)) > BIG]
    if big:
        stop("Neue große Dateien (über 2 MB) – gehören die wirklich ins Repo? %s\nSonst entfernen bzw. in .gitignore." % ", ".join(big), 4)
    if [f for f in out("diff", "--cached", "--name-only", base).splitlines() if f in OWN]:
        stop("VERSION und CHANGELOG.md schreibt nur dieses Skript: `git checkout origin/main -- VERSION CHANGELOG.md`, Punkte als Argumente.", 4)
    if not out("diff", "--cached", "--name-only", base):
        forget_seen()
        stop("Nichts zu veröffentlichen.", 0)
    seen = seen_base(base)
    with open(SEEN, "w", encoding="utf-8") as f:
        f.write(seen + "\n")
    git("reset", "-q", "--soft", base, check=True)                     # own work as one commit on the main it was built on
    git("commit", "-q", "--no-verify", "-m", "wip", check=True)
    for attempt in range(4):
        git("fetch", "-q", "origin", "main", check=True)
        if git("merge-base", "--is-ancestor", "origin/main", "HEAD").returncode != 0:
            r = git("rebase", "-q", "origin/main")
            if r.returncode != 0:
                files = out("diff", "--name-only", "--diff-filter=U").splitlines()
                stop("Konflikt: eine neuere Version auf main hat dieselben Stellen geändert wie du (deine Arbeit beruht auf %s):\n%s\n"
                     "Zwischen `<<<<<<< HEAD` und `=======` steht ihr Teil – der neuere, schon veröffentlichte Stand –, bis `>>>>>>> … (wip)` "
                     "deiner, der ihn nicht kannte. "
                     "Beide Absichten zusammenführen, Fremdes nie verwerfen; Unvereinbares dem Nutzer mit Empfehlung vorlegen. Dann "
                     "`git add`, `git rebase --continue`, denselben Befehl erneut – die Sperre prüft, dass keine ihrer Zeilen verloren ging."
                     % (out("show", seen + ":VERSION") or seen[:7], theirs(seen, files) or "?"), 3)
        if out("rev-parse", "HEAD") == out("rev-parse", "origin/main"):
            forget_seen()
            stop("Nichts mehr zu veröffentlichen – steckt schon in main.", 0)
        if not checks(extra):                                           # per state: after a rebase onto new versions again
            stop("Nicht veröffentlicht. Beheben, dann denselben Befehl erneut.", 1)
        git("fetch", "-q", "origin", "main", check=True)
        if git("merge-base", "--is-ancestor", "origin/main", "HEAD").returncode != 0:
            say("main ist während der Prüfung weiter – neu daraufsetzen.")
            continue
        version = bump(out("show", "origin/main:VERSION"), wanted)
        with open(os.path.join(ROOT, "VERSION"), "w", encoding="utf-8") as f:
            f.write(version + "\n")
        changelog(version, points)
        git("add", *OWN, check=True)
        git("commit", "--amend", "-q", "--no-verify", "-m", "%s: %s" % (version, subject), "-m", by, check=True)
        why = guard_says(seen)
        if why:
            back_to_wip()
            stop("Gesperrt vor dem Push: " + why, 4)
        r = git("-c", "push.negotiate=true", "push", "-q", "origin", "HEAD:main", timeout=300)
        if r.returncode == 0:
            forget_seen()
            sha = out("rev-parse", "HEAD")
            git("fetch", "-q", "origin", "main")
            n = len(out("diff", "--name-only", "HEAD~1", "HEAD").splitlines())
            added = out("diff", "--name-only", "--diff-filter=A", "HEAD~1", "HEAD").splitlines()
            say("%s veröffentlicht (%s, %d Dateien%s). Tests auf GitHub laufen; ein rotes Ergebnis meldet das Lagebild."
                % (version, sha[:7], n, ", neu: " + ", ".join(added[:12]) + (" …" if len(added) > 12 else "") if added else ""))
            tidy_branches()
            if wait:
                wait_for_github(sha)
            return
        back_to_wip()
        if not re.search(r"rejected|fetch first|non-fast-forward|failed to push", r.stderr):
            stop("Push fehlgeschlagen:\n" + r.stderr.strip()[-600:], 4)
        say("Ein anderer Chat war schneller – neu daraufsetzen, prüfen, nächste Nummer.")
    stop("Viermal überholt – denselben Befehl erneut.", 4)


def main():
    args, by, wanted, wait, check_only, extra, worker = [], None, None, False, False, [], None
    it = iter(sys.argv[1:])
    for a in it:
        if a == "--by":
            by = next(it, "")
        elif a == "--version":
            wanted = next(it, "")
        elif a == "--tests":
            extra.append(next(it, ""))
        elif a == "--wait":
            wait = True
        elif a == "--check":
            check_only = True
        elif a == "--run-checks":
            worker = next(it, "")
        elif a in ("-h", "--help"):
            stop(__doc__, 0)
        else:
            args.append(a)
    os.chdir(ROOT)
    if worker:
        return background(worker, extra)
    if git("config", "core.hooksPath").stdout.strip() != ".githooks":
        git("config", "core.hooksPath", ".githooks")
    if check_only:
        if git("rev-parse", "--verify", "-q", "origin/main").returncode != 0:
            git("fetch", "-q", "origin", "main")
        sys.exit(0 if checks(extra) else 1)
    if len(args) < 2:
        stop(__doc__, 2)
    subject, points = args[0].strip(), [re.sub(r"^\s*-\s*", "", p).strip() for p in args[1:]]
    if re.match(r"^\d+\.\d+\.\d+", subject) or "\n" in subject:
        stop("Betreff ohne Versionsnummer, eine Zeile (die Nummer setzt das Skript).", 2)
    bad = [p for p in points if not POINT.match(p)]
    if bad:
        stop("Changelog-Punkt je eine Zeile mit Bezug vorn („KI-Assistent: …“, nur Regeln/Tests/CI: „Entwicklung: …“): %s" % bad[0], 2)
    publish(subject, points, by_line(by), wanted, wait, extra)


if __name__ == "__main__":
    main()
