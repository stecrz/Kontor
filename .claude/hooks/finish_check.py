"""Before Claude ends a turn (Stop hook): changes to Kontor that are not committed or not pushed, or pushed without their
version yet (an own "Prepare X.Y.Z" on main after the last change to VERSION), get one reminder -- every change is finished
with the skill "release" (tests, push, GitHub Actions green, then VERSION and CHANGELOG as the last commit). Several chats
work in parallel, each in its own clone: only commits made in this clone count, never another chat's release. Never blocks
twice in a row."""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True, timeout=20)


# reflog entries that created a commit in this clone (not fetched or checked out from another chat's work)
OWN = re.compile(r"^(commit|cherry-pick)|\((pick|continue|reword|edit|squash|fixup)\)")


def own_commits() -> set:
    log = git("reflog", "--format=%H %gs")
    if log.returncode != 0:
        return set()
    return {sha for sha, _, what in (line.partition(" ") for line in log.stdout.splitlines()) if OWN.search(what)}


def own_unreleased() -> bool:
    """An own "Prepare" commit on main after the last change to VERSION: pushed, but the version is still missing."""
    last = git("log", "-1", "--format=%H", "origin/main", "--", "VERSION").stdout.strip()
    if not last:
        return False
    since = git("log", "--format=%H %s", last + "..origin/main")
    own = own_commits()
    return any(sha in own and subject.startswith("Prepare ")
               for sha, _, subject in (line.partition(" ") for line in since.stdout.splitlines()))


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    if data.get("stop_hook_active"):
        return 0
    try:
        st = git("status", "--porcelain")
        if st.returncode != 0:
            return 0
        changed = [line for line in st.stdout.splitlines() if line.strip()]
        ahead = git("rev-list", "--count", "origin/main..HEAD")
        unpushed = int(ahead.stdout.strip()) if ahead.returncode == 0 and ahead.stdout.strip().isdigit() else 0
        prepared = own_unreleased()
    except Exception:
        return 0
    if not changed and not unpushed and not prepared:
        return 0
    what = []
    if changed:
        what.append("%d Datei(en) geändert" % len(changed))
    if unpushed:
        what.append("%d Commit(s) nicht gepusht" % unpushed)
    if prepared:
        what.append("hochgeladen, aber noch ohne neue Version")
    print(json.dumps({"decision": "block", "reason":
                      "Kontor hat nicht abgeschlossene Änderungen (%s). Schließe sie mit dem Skill „release“ ab (Tests, Push, "
                      "GitHub Actions grün, dann VERSION und CHANGELOG als letzter Commit). Wartest du auf eine Antwort des "
                      "Nutzers oder will er das ausdrücklich nicht, sag das in einem Satz und beende." % ", ".join(what)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
