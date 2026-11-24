#!/usr/bin/env bash
# Everything a new clone needs for Kontor's local checks, in one quiet call -- started by itself in the background when a
# session starts (.claude/settings.json, SessionStart), so it costs the chat nothing; by hand only when release.py misses a tool. Idempotent: what is
# there is skipped. One line per part; the details in /tmp/kontor-setup.log.
#   bash .claude/tools/setup.sh
# Python: ~/kontor-venv with Kontor's own Python (as on GitHub; falls back to python3), and ~/py39 for the starter
# (tests/test_python.py, Apple's Python 3.9). .claude/tools/release.py uses both by itself.
LOG=/tmp/kontor-setup.log
: > "$LOG"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYV=3.15
ok() { printf '%-28s %s\n' "$1" "$2"; }
try() { "$@" >>"$LOG" 2>&1; }

git -C "$ROOT" config core.hooksPath .githooks

if [ -x ~/kontor-venv/bin/python ]; then ok "Python (~/kontor-venv)" "da"
elif try uv venv -q -p "$PYV" ~/kontor-venv || try uv venv -q -p python3 ~/kontor-venv; then ok "Python (~/kontor-venv)" "$(~/kontor-venv/bin/python -V 2>&1)"
else ok "Python (~/kontor-venv)" "FEHLT (siehe $LOG)"; fi
if [ -x ~/kontor-venv/bin/python ]; then
  # Playwright in the version the machine already has: then its browsers (e.g. /opt/pw-browsers) fit without a download
  PWV="$(python3 -m pip show playwright 2>/dev/null | sed -n 's/^Version: //p')"
  if VIRTUAL_ENV=~/kontor-venv try uv pip install -q pytest "playwright${PWV:+==$PWV}" cryptography pyflakes; then ok "pytest, playwright, pyflakes" "ok"
  else ok "pytest, playwright, pyflakes" "FEHLT (siehe $LOG)"; fi
fi

if [ -x ~/py39/bin/python ] || { try uv python install 3.9 && try uv venv -q -p 3.9 ~/py39 && VIRTUAL_ENV=~/py39 try uv pip install -q pytest cryptography; }
then ok "Python 3.9 (Starter)" "ok"; else ok "Python 3.9 (Starter)" "FEHLT (siehe $LOG)"; fi

if command -v sqlcipher >/dev/null || { try apt-get install -y -q sqlcipher || { try apt-get update -q && try apt-get install -y -q sqlcipher; }; }
then ok "sqlcipher" "ok"; else ok "sqlcipher" "FEHLT – Tests mit MoneyMoney-Datenbank werden übersprungen"; fi

PW=~/kontor-venv/bin/python
# where the download is blocked but an older build of the same browser is already there (cloud sessions): use that one
link_older() {
  "$PW" -m playwright install --dry-run "$1" 2>/dev/null | sed -n 's/^ *Install location: *//p' | while read -r want; do
    [ -e "$want" ] && continue
    base="${want%-*}"; have="$(ls -d "$base"-[0-9]* 2>/dev/null | grep -v -- "$want" | sort -V | tail -1)"
    [ -n "$have" ] && ln -s "$have" "$want" 2>>"$LOG"
  done
}
if [ -x "$PW" ] && { try "$PW" -m playwright install --with-deps chromium || { link_older chromium; try "$PW" -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p: p.chromium.launch().close()"; }; }; then ok "Chrome (Playwright)" "ok"
else ok "Chrome (Playwright)" "FEHLT – Browser-Tests laufen nur auf GitHub"; fi
if [ -x "$PW" ] && try "$PW" -m playwright install --with-deps webkit; then ok "Safari-Engine (WebKit)" "ok"
else ok "Safari-Engine (WebKit)" "fehlt – prüft GitHub"; fi

if [ -x "$ROOT/node_modules/.bin/eslint" ] || (cd "$ROOT" && try npm install -s --no-save --no-package-lock eslint@9 globals)
then ok "ESLint" "ok"; else ok "ESLint" "FEHLT (siehe $LOG)"; fi
exit 0
