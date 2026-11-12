"""Before Claude ends a turn (Stop hook): changes to Kontor that are not committed or not pushed get one reminder -- every
change is finished with the skill "release" (tests, VERSION, CHANGELOG, commit, push, the Mac). Never blocks twice in a row."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True, timeout=20)


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
    except Exception:
        return 0
    if not changed and not unpushed:
        return 0
    what = []
    if changed:
        what.append("%d Datei(en) geändert" % len(changed))
    if unpushed:
        what.append("%d Commit(s) nicht gepusht" % unpushed)
    print(json.dumps({"decision": "block", "reason":
                      "Kontor hat nicht abgeschlossene Änderungen (%s). Schließe sie mit dem Skill „release“ ab (Tests, VERSION, "
                      "CHANGELOG, Commit, Push, Mac). Wartest du auf eine Antwort des Nutzers oder will er das ausdrücklich "
                      "nicht, sag das in einem Satz und beende." % ", ".join(what)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
