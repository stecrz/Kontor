"""Which tests a change touches -- to run locally before a push (the whole suite runs on GitHub for every push).

    python3 tests/affected.py            # the test files for what differs from origin/main (committed or not)
    python3 -m pytest -q $(python3 tests/affected.py)

A changed module brings every test file that names it; texts, rules and the page bring the tests that read them.
Nothing found: the quick checks of the rules (test_rules). Kept simple on purpose: when in doubt it names more, never less.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# files that are no module of the program, and the tests that read them
TEXTS = {
    "CHANGELOG.md": ["test_rules.py", "test_hooks.py"], "HIGHLIGHTS.md": ["test_rules.py"], "VERSION": ["test_hooks.py"],
    "ROADMAP.md": ["test_rules.py"], "CLAUDE.md": ["test_rules.py", "test_hooks.py"], "README.md": ["test_rules.py", "test_privacy.py"],
    "docs/help.de.md": ["test_rules.py"], "docs/help.en.md": ["test_rules.py"], "docs/ui/": ["test_ui_docs.py"],
    "web/": ["test_e2e.py", "test_tour.py", "test_clickpaths.py", "test_ui_docs.py", "test_rules.py"], ".claude/": ["test_hooks.py"],
    ".githooks/": ["test_hooks.py"], ".github/": ["test_workflows.py", "test_hooks.py"], "assistant_eval/": ["test_assistant_eval.py"],
}


def changed() -> list:
    out = set()
    for args in (["git", "diff", "--name-only", "origin/main"], ["git", "ls-files", "--others", "--exclude-standard"]):
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
        out.update(x for x in r.stdout.split() if x)
    return sorted(out)


def affected(files: list) -> list:
    tests = sorted(f for f in os.listdir(HERE) if f.startswith("test_") and f.endswith(".py"))
    texts = {t: open(os.path.join(HERE, t), encoding="utf-8").read() for t in tests}
    pick = set()
    for f in files:
        if f.startswith("tests/"):
            name = os.path.basename(f)
            if name in texts:
                pick.add(name)
            elif name.endswith(".py"):                    # a helper of the tests (fixtures, fake_llama ...): who uses it
                stem = name[:-3]
                pick.update(t for t, src in texts.items() if re.search(r"\b%s\b" % re.escape(stem), src))
            continue
        for key, names in TEXTS.items():
            if f == key or (key.endswith("/") and f.startswith(key)):
                pick.update(names)
        if f.endswith(".py") and "/" not in f:            # a module of the program: every test that names it
            stem = f[:-3]
            pick.update(t for t, src in texts.items() if re.search(r"\b%s\b" % re.escape(stem), src))
            if stem in ("updates", "update_guard") or re.search(r"\b(subprocess|urllib|socket)\b", open(os.path.join(ROOT, f), encoding="utf-8").read() if os.path.exists(os.path.join(ROOT, f)) else ""):
                pick.update({"test_update_guard.py", "test_security.py"})       # it can reach out: what an update would report
        if f.endswith((".swift", ".jxa", ".sb")):
            pick.update({"test_update_guard.py", "test_security.py"})
    return ["tests/" + t for t in sorted(pick)] or ["tests/test_rules.py"]


if __name__ == "__main__":
    print(" ".join(affected(sys.argv[1:] or changed())))
