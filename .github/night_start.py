"""Starts the night's random runs (nightly.yml, "Zufallsläufe") between 3 and 4 a.m. German time, summer and winter (the user,
2026-11-26).

GitHub starts scheduled runs late under load -- in this repository 7-9 hours (Nov. 2026: 3:47 planned, 12:29 started), and the
schedule's `timezone` only sets the hour asked for, not the start. A run started with workflow_dispatch is not delayed. So
night_start.yml wakes this script every two hours, each wake-up as late as GitHub makes it; the first that arrives within WAIT_MAX
before START waits there and starts the night; the others (one at a time: `concurrency` in the workflow) see it started and end
in seconds. plan() decides without the network (tests/test_workflows.py, NightStart); standard library and `gh` (on GitHub's
runners) only. Not part of the program (update_guard.BESIDE)."""
import datetime as dt
import json
import os
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
START = dt.time(3, 5)       # German time; after 3:00 -- in spring the hour from 2 to 3 is missing, in autumn it comes twice
LAST = dt.time(4, 0)        # no start after this: a night that did not start by then is missing (the briefing says so), not run by day
WAIT_MAX = dt.timedelta(hours=2, minutes=45)   # longer than the two hours between wake-ups, well under the job's limit
EVERY = dt.timedelta(hours=2)                  # the wake-ups (night_start.yml, cron)
RUNNING = ("queued", "in_progress", "waiting", "requested", "pending")


def plan(now, runs):
    """(what, seconds, why) at `now` (aware), given the night's newest runs [(created, status)] (created aware): "wait" (seconds
    until START, then ask again), "start" (now) or "end"."""
    # in UTC: between two times of the same zone Python counts the clock on the wall (an hour off across a change of the clock)
    now, local = now.astimezone(dt.timezone.utc), now.astimezone(BERLIN)
    day = local.date() + dt.timedelta(days=1 if local.time() >= LAST else 0)
    start = dt.datetime.combine(day, START, tzinfo=BERLIN).astimezone(dt.timezone.utc)
    at = "%s German time" % local.strftime("%d.%m. %H:%M")
    if now < start:
        wait = start - now
        if wait > WAIT_MAX:
            return "end", 0, "%s: the night starts at %s, in %s -- a later wake-up waits for it" % (at, start.astimezone(BERLIN).strftime("%d.%m. %H:%M"), wait)
        return "wait", wait.total_seconds(), "%s: waiting %s for the night's start at %s" % (at, wait, start.astimezone(BERLIN).strftime("%H:%M"))
    begun = [(c, s) for c, s in runs if s in RUNNING or c >= start - dt.timedelta(minutes=10)]
    if begun:
        c, s = begun[0]
        return "end", 0, "%s: the night has started (%s, %s)" % (at, c.astimezone(BERLIN).strftime("%d.%m. %H:%M"), s)
    return "start", 0, "%s: starting the night" % at


def gh(*args):
    """`gh` with the run's token (GH_TOKEN); three tries a minute apart, then the error."""
    for attempt in range(3):
        p = subprocess.run(("gh",) + args, capture_output=True, text=True)
        if p.returncode == 0:
            return p.stdout
        print("gh %s: %s" % (args[0], (p.stderr or p.stdout).strip()[-300:]), file=sys.stderr, flush=True)
        if attempt < 2:
            time.sleep(60)
    raise SystemExit(1)


def runs(repo):
    out = json.loads(gh("api", "repos/%s/actions/workflows/nightly.yml/runs?per_page=10" % repo))
    return [(dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")), r["status"]) for r in out.get("workflow_runs") or []]


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    while True:
        what, seconds, why = plan(dt.datetime.now(dt.timezone.utc), runs(repo))
        print(why, flush=True)
        if what == "end":
            return 0
        if what == "wait":
            time.sleep(seconds)
            continue
        gh("workflow", "run", "nightly.yml", "--ref", "main", "-R", repo)
        print("started", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
