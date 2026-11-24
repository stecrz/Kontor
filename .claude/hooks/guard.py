"""Guard rails for Claude working on Kontor (PreToolUse hook): on the user's Mac never touch Kontor's data folder or
MoneyMoney's own data, never use MoneyMoney's transfer commands; nowhere force-push or delete main; never read a big text file
whole (read_check: find the place, then a range -- what is read is paid again at every later step); and before every push the
version chain (push_check): what goes to main sits on the newest main and is one version after another -- each commit raises
VERSION, keeps every version section of the changelog and heads it with its own version. Exit code 2 blocks the call and
tells Claude why; anything else lets the normal flow go on. A guard rail, not a sandbox.

By hand / on GitHub: python3 .claude/hooks/guard.py chain <before> <after> -- the same version chain for the commits pushed.
The chain also checks the top changelog heading's time against the commit's own time: chats have no clock and guessed it, up
to 29 minutes ahead (3.17.30) -- release.py writes it from the clock."""
import datetime
import json
import os
import re
import subprocess
import sys

ALLOWED = "KONTOR_DATEN_ERLAUBT"        # only after the user explicitly allowed it in this session

RULES = [
    # (only for tools on the Mac, can the user allow it, pattern, reason)
    (True, True, r"Application Support/Kontor\b",
     "Kontors Datenordner am Mac nur mit ausdrücklicher Erlaubnis des Nutzers (dann %s in den Befehl schreiben)." % ALLOWED),
    (True, False, r"com\.moneymoney-app|MoneyMoney\.sqlite|Containers/[^\"']*MoneyMoney",
     "MoneyMoneys eigene Daten liest Kontor nur über den Upload in der Oberfläche – nie direkt."),
    (True, False, r"(?i)create\s*(bank|batch)\s*transfer|create\s*(batch\s*)?direct\s*debit",
     "Überweisungen und Lastschriften sind gesperrt."),
    (False, False, r"git\s+push\b[^\n;&|]*(\s--force\b|\s-f\b|\s--force-with-lease\b|\s\+\S)",
     "Kein Force-Push."),
    (False, False, r"git\s+push\b[^\n;&|]*((\s--delete|\s-d)\b[^\n;&|]*\bmain\b|\s:(refs/heads/)?main\b)",
     "main nie löschen."),
]


PUSH = r"(?:^|[;&|(]\s*|\n\s*)git\s+(?:-C\s+(?:\"[^\"]+\"|'[^']+'|\S+)\s+)?push\b"      # a push command itself (not the words in a text)
HOME_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))     # the folder above .claude


def _git(repo: str, *args: str, timeout: float = 20, env=None):
    return subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True, timeout=timeout, env=env)


BERLIN = "Europe/Berlin"                # the user's local time, in which the changelog headings are written
STAMP = "%Y-%m-%d %H:%M"
EARLY, LATE = 1, 20                     # minutes a heading may be after / before its commit (tests and rebase in between)


def time_problem(repo: str, commit: str, changelog: str, name: str) -> str:
    """The top heading's time against the commit's own time (both Berlin): never after it, at most LATE minutes before."""
    m = re.search(r"(?m)^## \d+\.\d+\.\d+ \((\d{4}-\d\d-\d\d \d\d:\d\d)\)", changelog or "")
    if not m:
        return ""                                       # old headings without a time
    made = _git(repo, "log", "-1", "--date=format-local:" + STAMP, "--format=%cd", commit, env=dict(os.environ, TZ=BERLIN)).stdout.strip()
    try:
        minutes = (datetime.datetime.strptime(m.group(1), STAMP) - datetime.datetime.strptime(made, STAMP)).total_seconds() / 60
    except ValueError:
        return ""
    if -LATE <= minutes <= EARLY:
        return ""
    return ("%s: Uhrzeit im CHANGELOG %s, Commit um %s – nie schätzen, VERSION und CHANGELOG.md schreibt "
            "`.claude/tools/release.py` (Zeit von der Uhr)." % (name, m.group(1), made))


def _version(text: str):
    """VERSION as numbers (3.16.9 < 3.16.10), None when it is not one."""
    m = re.fullmatch(r"\s*(\d+)\.(\d+)\.(\d+)\s*", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def _sections(changelog: str):
    """The version headings of CHANGELOG.md ("## X.Y.Z (date)"), top first."""
    return re.findall(r"(?m)^## (\d+\.\d+\.\d+)\b", changelog or "")


def chain_problems(repo: str, before: str, after: str):
    """What is wrong with the commits before..after as versions on main: each raises VERSION over its predecessor (as numbers),
    keeps every "## X.Y.Z" section of its predecessor's changelog and heads it with its own version. Empty: all right."""
    out = []
    revs = _git(repo, "rev-list", "--reverse", "%s..%s" % (before, after) if before else after).stdout.split()
    show = lambda c, f: _git(repo, "show", "%s:%s" % (c, f)).stdout if c else ""
    for c in revs:
        parent = _git(repo, "rev-parse", "--verify", "-q", c + "^").stdout.strip()
        name = "%s (%s)" % (c[:7], _git(repo, "log", "-1", "--format=%s", c).stdout.strip()[:60])
        v, pv = _version(show(c, "VERSION")), _version(show(parent, "VERSION"))
        cl, pcl = show(c, "CHANGELOG.md"), show(parent, "CHANGELOG.md")
        if v is None:
            out.append("%s: VERSION ist keine Versionsnummer." % name)
            continue
        if pv is not None and v <= pv:
            out.append("%s: VERSION %s ist nicht höher als %s davor (eine Version je Commit, Nummer aus dem neuesten main + 1)." % (
                name, ".".join(map(str, v)), ".".join(map(str, pv))))
        gone = [x for x in _sections(pcl) if x not in _sections(cl)]
        if gone:
            out.append("%s: im CHANGELOG fehlen Abschnitte, die davor da waren: %s (fremde Versionen überschrieben?)." % (name, ", ".join(gone[:6])))
        top = (_sections(cl) or [None])[0]
        if top != ".".join(map(str, v)):
            out.append("%s: oberste CHANGELOG-Überschrift %s passt nicht zu VERSION %s." % (name, top, ".".join(map(str, v))))
        late = time_problem(repo, c, cl, name)
        if late:
            out.append(late)
    return out


def lost_lines(repo: str, base: str, ref: str, recent: int = 8):
    """Lines the newest versions on main added (code, tests, texts -- not VERSION or CHANGELOG.md, nor HIGHLIGHTS.md, whose lines
    the next versions condense on purpose) that main still has and the work pushed no longer has: an older tree set on top of
    main loses them while VERSION and CHANGELOG look right (3.16.35 lost the code of 3.16.32 that way). [(commit, file, line)]."""
    out, have, ours = [], {}, {}
    show = lambda c, f: set(_git(repo, "show", "%s:%s" % (c, f)).stdout.split("\n"))
    for c in _git(repo, "rev-list", "-n", str(recent), base).stdout.split():
        if not _git(repo, "rev-parse", "--verify", "-q", c + "^").stdout.strip():
            continue                                    # the first commit: nothing before it
        cur = None
        for line in _git(repo, "diff", "-U0", c + "^", c, "--", ".", ":(exclude)VERSION", ":(exclude)CHANGELOG.md",
                         ":(exclude)HIGHLIGHTS.md").stdout.split("\n"):
            if line.startswith("+++ "):
                cur = line[6:] if line.startswith("+++ b/") else None
                continue
            if not cur or not line.startswith("+") or len(line.strip()) < 8:
                continue
            if cur not in have:
                have[cur], ours[cur] = show(base, cur), show(ref, cur)
            if line[1:] in have[cur] and line[1:] not in ours[cur]:
                out.append((c[:7], cur, line[1:].strip()))
    return out


def _push_repo(command: str, cwd: str) -> str:
    """The repository a push command works in: `git -C <dir>` or a leading `cd <dir>`, else where the command runs."""
    m = re.search(r"\bgit\s+-C\s+(\"[^\"]+\"|'[^']+'|\S+)\s+push\b", command) or re.search(r"(?:^|[;&|]\s*)cd\s+(\"[^\"]+\"|'[^']+'|[^\s;&|]+)", command)
    d = m.group(1).strip("\"'") if m else (cwd or HOME_REPO)
    d = os.path.expanduser(d)
    return d if os.path.isabs(d) else os.path.join(cwd or HOME_REPO, d)


def _pushed_ref(command: str) -> str:
    """What the push sends to main: SRC of `SRC:main`, a bare `main`, else HEAD."""
    m = re.search(PUSH + r"([^\n;&|]*)", command)
    words = (m.group(1) if m else "").split()
    for w in words:
        if w.endswith(":main") or w.endswith(":refs/heads/main"):
            return w.split(":")[0] or "HEAD"
    return "main" if "main" in words else "HEAD"


def push_check(command: str, cwd: str) -> str:
    """Before a push to Kontor's main: the newest main fetched (at most 5 s; else the last one fetched) and in the work pushed;
    every commit on top of it one proper version. Returns why not, or "" (also for other repositories)."""
    repo = _push_repo(command, cwd)
    top = _git(repo, "rev-parse", "--show-toplevel").stdout.strip()
    if not top or not (os.path.isfile(os.path.join(top, "VERSION")) and os.path.isfile(os.path.join(top, "CHANGELOG.md"))):
        return ""                                       # not Kontor
    try:
        _git(top, "fetch", "-q", "origin", "main", timeout=5)
    except subprocess.TimeoutExpired:
        pass                                            # checked against the main fetched last
    if not _git(top, "rev-parse", "--verify", "-q", "origin/main").stdout.strip():
        return ""
    ref = _pushed_ref(command)
    if _git(top, "merge-base", "--is-ancestor", "origin/main", ref).returncode != 0:
        return ("Der neueste main steckt nicht in deiner Arbeit: erst `git pull --rebase origin main` (Konflikte: beide Seiten "
                "erhalten), Tests erneut, Nummer aus dem neuen main + 1 – nie `reset --soft` auf einen fremden Stand.")
    problems = chain_problems(top, "origin/main", ref)
    lost = lost_lines(top, "origin/main", ref) if not problems else []
    if lost:
        return ("Dein Stand löscht Zeilen, die die neuesten Versionen auf main gebracht haben – er beruht auf einem älteren Baum "
                "(wie 3.16.35):\n- " + "\n- ".join("%s %s: %s" % (c, f, l[:90]) for c, f, l in lost[:8])
                + ("\n- … und %d weitere" % (len(lost) - 8) if len(lost) > 8 else "")
                + "\nEigene Änderungen auf den frisch geholten main setzen (`git pull --rebase origin main`), nie `reset --soft` auf einen "
                "fremden Stand. Nur wenn du genau diese Zeilen bewusst geändert hast: KONTOR_PUSH_OK=1.")
    if problems and all("Uhrzeit im CHANGELOG" in p for p in problems):
        return "Changelog-Zeit stimmt nicht:\n- " + "\n- ".join(problems)
    if problems:
        return ("Versionskette stimmt nicht – so würden fremde Versionen überschrieben (wie 66ad67f):\n- " + "\n- ".join(problems)
                + "\nEigene Arbeit ohne VERSION und CHANGELOG.md neu auf den frisch geholten main setzen, dann als nächste Nummer.")
    return ""


BIG_FILE = 100_000          # bytes: above this a text file is read in parts (web/app.js, assistant.py, service.py, the big tests ...)
MOST_LINES = 400            # ... of at most this many lines -- whatever is read stays in the chat and is paid again at every step
PICTURES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".ipynb")


def read_check(tool_input: dict) -> str:
    """A big text file is never read whole (one read of web/app.js would be ~50,000 tokens, carried along every later step):
    find the place first, then read a range around it. Returns why not, or ""."""
    path = str(tool_input.get("file_path") or "")
    if not path or path.lower().endswith(PICTURES):
        return ""
    try:
        size = os.path.getsize(path)
    except OSError:
        return ""
    limit = tool_input.get("limit")
    if size <= BIG_FILE or (isinstance(limit, int) and 0 < limit <= MOST_LINES):
        return ""
    return ("%s hat %d KB – nie ganz lesen. Erst die Stelle suchen (`grep -n '<Funktion oder Text>' %s`), dann Read mit "
            "offset und limit (höchstens %d Zeilen) um die gefundene Zeile." % (os.path.basename(path), size // 1024, path, MOST_LINES))


def main() -> int:
    if sys.argv[1:2] == ["chain"]:                     # GitHub: the commits of a push (before..after)
        before, after = (sys.argv[2:4] + ["", ""])[:2]
        if not after:
            print("usage: guard.py chain <before> <after>", file=sys.stderr)
            return 2
        repo = os.getcwd()
        if not before or set(before) == {"0"} or _git(repo, "cat-file", "-e", before + "^{commit}").returncode != 0:
            before = _git(repo, "rev-parse", "--verify", "-q", after + "^").stdout.strip()     # a new branch: its last commit
        elif _git(repo, "merge-base", "--is-ancestor", before, after).returncode != 0:
            print("Gesperrt: %s ist nicht im neuen Stand – main wurde überschrieben (Force-Push)." % before[:7], file=sys.stderr)
            return 2
        problems = chain_problems(repo, before, after)
        for p in problems:
            print("Versionskette: " + p, file=sys.stderr)
        if not problems:
            print("Versionskette in Ordnung: %s..%s" % (before[:7], after[:7]))
        return 2 if problems else 0
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    tool = str(data.get("tool_name") or "")
    text = json.dumps(data.get("tool_input") or {}, ensure_ascii=False).replace("\\\\", "").replace("\\", "")
    on_mac = tool.startswith("mcp__remote-devices__")
    for mac_only, can_allow, pattern, reason in RULES:
        if mac_only and not on_mac:
            continue
        if re.search(pattern, text) and not (can_allow and ALLOWED in text):
            print("Gesperrt: " + reason, file=sys.stderr)
            return 2
    if tool == "Read":
        why = read_check(data.get("tool_input") or {})
        if why:
            print("Gesperrt: " + why, file=sys.stderr)
            return 2
        return 0
    command = str((data.get("tool_input") or {}).get("command") or "")
    if tool == "Bash" and re.search(PUSH, command) and "KONTOR_PUSH_OK=1" not in command:      # a deliberate exception (like .githooks/pre-push)
        try:
            why = push_check(command, str(data.get("cwd") or ""))
        except Exception as e:                          # the check itself broke: said, not silently let through
            why = "Prüfung vor dem Push fehlgeschlagen (%s) – von Hand: python3 .claude/hooks/guard.py chain origin/main HEAD" % type(e).__name__
        if why:
            print("Gesperrt: " + why, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
