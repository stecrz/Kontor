"""Briefing for the parallel chats (SessionStart and UserPromptSubmit hook; by hand: python3 .claude/hooks/briefing.py):
what the other chats have published on main since this clone last looked -- versions, files touched, overlap with this
clone's own work, and the state of the tests on GitHub. It only reads from GitHub; locally it fast-forwards a clone that
has nothing of its own and turns on the push check (.githooks/pre-push), and touches nothing else. As a hook it says nothing while nothing changed, and never blocks: any
failure ends silently."""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OWN = {"VERSION", "CHANGELOG.md"}       # every version changes these: no sign of overlapping work
SHOWN = 12                              # newest foreign versions listed


def run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.rstrip()
    except Exception:
        return 1, ""


def git(*args, timeout=20):
    return run(["git"] + list(args), timeout)


def chat(body):
    """The last four characters of the session link in a commit message: enough to tell the chats apart."""
    m = re.search(r"session_(\w+)", body or "")
    return "Chat …" + m.group(1)[-4:] if m else ""


def foreign_commits():
    """What main has and this clone does not, oldest first: (short hash, subject, chat, files)."""
    code, out = git("log", "--reverse", "--name-only", "--format=%x1e%h%x1f%s%x1f%b%x1f", "HEAD..origin/main")
    if code != 0:
        return []
    res = []
    for rec in out.split("\x1e"):
        parts = rec.split("\x1f")
        if len(parts) < 4:
            continue
        files = [f for f in parts[3].split("\n") if f.strip()]
        res.append((parts[0].strip(), parts[1].strip()[:90], chat(parts[2]), files))
    return res


def own_files():
    """Files this clone has changed against the point where it left main (committed or not), and new ones."""
    files = set()
    code, base = git("merge-base", "HEAD", "origin/main")
    if code == 0 and base:
        files.update(f for f in git("diff", "--name-only", base)[1].split("\n") if f)
    for line in git("status", "--porcelain")[1].split("\n"):
        if line[3:].strip():
            files.add(line[3:].strip().split(" -> ")[-1])
    return files - OWN


NIGHT_TESTS = "tests/test_fuzz.py tests/test_cashflow.py tests/test_scenarios.py"      # what nightly.yml runs (1000 fixed + 1000 new cases)


def tests_on_github():
    """One line on the tests of the newest versions on main and of the last night's run, and a key that changes when they turn
    red or green again."""
    url = git("remote", "get-url", "origin")[1]
    m = re.search(r"([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url)
    if not m or "://" not in url and "@" not in url:     # a folder as origin (tests): nothing to ask GitHub
        return "", ""

    def runs(path):
        code, out = run(["gh", "api", "repos/%s/%s/actions/%s" % (m.group(1), m.group(2), path)], 8)
        if code != 0:
            return None
        try:
            return json.loads(out).get("workflow_runs") or []
        except (ValueError, AttributeError):
            return None
    push = runs("runs?branch=main&event=push&per_page=8")
    if push is None:
        return "", ""
    night = runs("workflows/nightly.yml/runs?branch=main&per_page=5") or []
    since = lambda iso: git("log", "--since=" + iso, "--format=%s%x1f%b%x1e", "origin/main")[1] if iso else ""
    who = lambda sha: chat(git("log", "-1", "--format=%b", sha)[1])
    return ci_summary(push, night, since, who)


def ci_summary(push, night, since, who):
    """The line and its key from GitHub's runs: push = the runs of the newest versions on main (newest first), night = those of
    nightly.yml (newest first); since(iso) = subjects and bodies of the commits on main since then, who(sha) = the chat of a
    commit. The night's run belongs to no version: red, the next chat that sees it fixes it ("fix nightly" in its commit subject
    marks the fix, so the others leave it)."""
    name = lambda r: str(r.get("display_title") or "").split(":")[0][:20] or str(r.get("head_sha"))[:7]
    done = [r for r in push if r.get("status") == "completed" and r.get("conclusion") in ("success", "failure")]
    parts, keys = [], []
    if push and push[0].get("status") != "completed":
        parts.append("läuft für %s" % name(push[0]))
    if done and done[0]["conclusion"] == "success":
        parts.append("%s grün" % name(done[0]))
    elif done:
        first = done[0]
        for r in done:                  # the oldest red one of the streak: the version that broke it
            if r["conclusion"] != "failure":
                break
            first = r
        w = who(str(first.get("head_sha")))
        keys.append("red " + str(first.get("head_sha"))[:7])
        parts.append("ROT seit %s%s – das behebt der Chat, der diese Version veröffentlicht hat; ist es nicht deine: nicht "
                     "reparieren, weiterarbeiten (dein eigener Lauf erbt dieselben Fehler, bis die Korrektur da ist)"
                     % (name(first), " (%s)" % w if w else ""))
    nd = [r for r in night if r.get("status") == "completed" and r.get("conclusion") not in (None, "skipped", "neutral")]
    if nd:
        r = nd[0]
        ver = str((r.get("head_commit") or {}).get("message") or "").split(":")[0][:20] or str(r.get("head_sha"))[:7]
        if r["conclusion"] == "success":
            parts.append("Nachtlauf (Zufallsfälle) für %s grün" % ver)
        else:
            fix = [c.split("\x1f") for c in since(str(r.get("created_at") or "")).split("\x1e") if "fix nightly" in c.split("\x1f")[0].lower()]
            if fix:
                keys.append("night-fixed %s" % r.get("id"))
                parts.append("Nachtlauf für %s rot, behoben in %s%s – die nächste Nacht prüft es" % (ver, fix[-1][0].strip().split(":")[0],
                             " (%s)" % chat(fix[-1][1]) if len(fix[-1]) > 1 and chat(fix[-1][1]) else ""))
            else:
                keys.append("night-red %s" % r.get("id"))
                parts.append("Nachtlauf (Zufallsfälle) für %s ROT%s – gehört zu keiner Version: behebe es jetzt als eigene "
                             "Version, Commit-Nachricht mit „fix nightly“ (`X.Y.Z: fix nightly: …`), damit die anderen Chats es "
                             "liegen lassen. Fehler: `gh run view %s --log-failed | tail -80`; der Fall („seed …“) einzeln: "
                             "`KONTOR_FUZZ_SEED=<Nummer>`, ein neuer (ab 1000000) danach in FOUND (tests/fixtures.py); nachprüfen: "
                             "`KONTOR_FUZZ_SEEDS=1000 TZ=Europe/Berlin python3 -m pytest -q %s` (auch mit Python 3.9)"
                             % (ver, "" if r["conclusion"] == "failure" else " (%s)" % r["conclusion"], r.get("id"), NIGHT_TESTS))
    if not parts:
        return "", ""
    return "Tests auf GitHub: " + "; ".join(parts), " ".join(keys) or "ok"


def main() -> int:
    hook = "hook" in sys.argv[1:]
    if hook:
        try:
            sys.stdin.read()            # the hook's input is not needed
        except Exception:
            pass
    if git("rev-parse", "--git-dir")[0] != 0:
        return 0
    if os.path.isfile(os.path.join(ROOT, ".githooks", "pre-push")) and git("config", "core.hooksPath")[1] != ".githooks":
        git("config", "core.hooksPath", ".githooks")     # the push check against undoing other chats' versions
    shallow = git("rev-parse", "--is-shallow-repository")[1] == "true"
    fetched = git("fetch", "-q", *(["--depth=50"] if shallow else []), "origin", "main", timeout=20)[0] == 0
    code, remote = git("rev-parse", "origin/main")
    if code != 0:
        return 0
    if not fetched and not hook:
        print("GitHub nicht erreichbar – Stand vom letzten Holen.")
    version = git("show", "origin/main:VERSION")[1] or "?"
    mine = git("show", "HEAD:VERSION")[1] or "?"
    ci, ci_key = tests_on_github()
    state_file = os.path.join(ROOT, git("rev-parse", "--git-dir")[1], "kontor-briefing")
    state = ("%s %s" % (remote, ci_key)).strip()
    if hook:
        try:
            with open(state_file, encoding="utf-8") as f:
                if f.read().strip() == state:
                    return 0            # nothing new since the last briefing
        except OSError:
            pass
    foreign = foreign_commits()
    ahead = git("rev-list", "--count", "origin/main..HEAD")[1]
    ahead = int(ahead) if ahead.isdigit() else 0
    dirty = bool(git("status", "--porcelain")[1])
    lines = ["Kontor-Lagebild: main steht bei %s." % version]
    if foreign:
        lines[0] += " Neu von anderen Chats (du: %s):" % mine
        if len(foreign) > SHOWN:
            lines.append("- … %d ältere" % (len(foreign) - SHOWN))
        for h, subject, who, files in foreign[-SHOWN:]:
            shown = [f for f in files if f not in OWN]
            lines.append("- %s%s · %s" % (subject, " · " + who if who else "", ", ".join(shown[:8]) + (" …" if len(shown) > 8 else "")))
        if not ahead and not dirty and git("symbolic-ref", "--short", "HEAD")[1] == "main" \
                and git("merge", "-q", "--ff-only", "origin/main")[0] == 0:
            lines.append("Dein Klon hatte nichts Eigenes und steht jetzt auf %s – vorher gelesene Dateien aus der Liste neu lesen." % version)
        else:
            touched = set(f for c in foreign for f in c[3])
            both = sorted(own_files() & touched)
            if both:
                lines.append("Überschneidung mit deiner Arbeit: %s – die fremden Änderungen dort erst lesen "
                             "(`git diff HEAD...origin/main -- <Datei>`)." % ", ".join(both[:10]))
            lines.append("Jetzt daraufsetzen, bevor du weiterarbeitest (je früher, desto kleiner der Konflikt): eigene Änderungen "
                         "lokal committen, dann `git pull --rebase origin main`; nach dem Rebase die betroffenen Tests.")
    elif not hook:
        lines[0] += " Dein Klon ist auf dem Stand%s." % (" (mit eigener Arbeit)" if ahead or dirty else "")
    if ci:
        lines.append(ci)
    if hook and len(lines) == 1 and not ci:
        pass                            # only the version, and it is the clone's own: not worth a line
    else:
        print("\n".join(lines))
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            f.write(state)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
