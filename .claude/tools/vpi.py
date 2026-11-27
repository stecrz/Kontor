#!/usr/bin/env python3
"""Refreshes the consumer price index that Kontor ships (price_index.py: BUNDLED_TEXT, BUNDLED_UNIT, BUNDLED_AS_OF) from the
Deutsche Bundesbank's time series interface -- at each major version (Skill `major`), or when the bundled months are old.
Kontor fetches newer months by itself while the switch "Kaufkraft" is on; the bundled table is what it starts from (and what
the demo and a Mac without the internet use).

Takes the newest series of the index for Germany (any base year: after a rebasing, 2025 = 100 one day, the whole table moves
to the new base), checks it the way Kontor does (price_index.parse: no gap, plausible values) and that it starts in January
1991, then writes it into price_index.py. Needs api.statistiken.bundesbank.de in the network of the cloud environment
(Kontor-Entwicklung allows it).
    python3 .claude/tools/vpi.py
"""
import csv
import io
import os
import re
import subprocess
import sys
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
import price_index as P   # noqa: E402

URL = P.URL % "1991-01"


def main() -> int:
    raw = subprocess.run(["curl", "-sS", "-m", "60", "--fail", URL], capture_output=True, check=False)
    if raw.returncode:
        print("fetch failed: %s" % raw.stderr.decode("utf-8", "replace").strip())
        return 1
    rows = list(csv.reader(io.StringIO(raw.stdout.decode("utf-8-sig")), delimiter=";"))
    key, unit, got = P.parse(rows, date.today())
    if min(got) != "1991-01":
        print("the series %s starts in %s, not in 1991-01 -- not written" % (key, min(got)))
        return 1
    years = {}
    for m in sorted(got):
        years.setdefault(m[:4], []).append(("%.1f" % got[m]))
    text = "\n".join("%s %s" % (y, " ".join(v)) for y, v in sorted(years.items()))
    path = os.path.join(ROOT, "price_index.py")
    src = open(path, encoding="utf-8").read()
    src = re.sub(r'BUNDLED_TEXT = """\n.*?\n"""', lambda _: 'BUNDLED_TEXT = """\n%s\n"""' % text, src, count=1, flags=re.S)
    src = re.sub(r'BUNDLED_UNIT = "[^"]*"', 'BUNDLED_UNIT = "%s"' % unit, src, count=1)
    src = re.sub(r'BUNDLED_AS_OF = "[^"]*"', 'BUNDLED_AS_OF = "%s"' % date.today().isoformat(), src, count=1)
    open(path, "w", encoding="utf-8").write(src)
    print("price_index.py: %s, %s, %s to %s (%d months)" % (key, unit, min(got), max(got), len(got)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
