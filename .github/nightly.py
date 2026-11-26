"""The night's wake-up (nightly.yml, job "Wecker"): starts the night's tests between 3 and 4 a.m. German time, summer and winter
(the user, 2026-11-26/27).

GitHub starts scheduled runs late under load and now and then not at all -- in this repository 7-9 hours late (Nov. 2026: 3:47
planned, 12:29 started; three of four two-hourly wake-ups on 26.11. never came). A run started with workflow_dispatch is not
delayed. So nightly.yml wakes this script every two hours (each wake-up as late as GitHub makes it): the first that arrives within
WAIT_MAX before START waits there and starts the night -- the same workflow, by workflow_dispatch; a later one sees it waiting
and ends in seconds, as does one that arrives too early. So a night needs only one of the three or more wake-ups in the
5 1/2 hours before 3:05 (or one between 3:05 and 4:00), whatever GitHub's delay. No start after LAST: a night that did not start
by then is missing (the briefing says so), never run by day. plan() decides without the network (tests/test_workflows.py,
Night); standard library and `gh` (on GitHub's runners) only. Not part of the program (update_guard.BESIDE)."""
import datetime as dt
import json
import os
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
START = dt.time(3, 5)       # German time; after 3:00 -- in spring the hour from 2 to 3 is missing, in autumn it comes twice
LAST = dt.time(4, 0)        # no start after this: a night that did not start by then is missing, not run by day
WAIT_MAX = dt.timedelta(hours=5, minutes=30)   # well over the two hours between wake-ups, under GitHub's six hours per job
EVERY = dt.timedelta(hours=2)                  # the wake-ups (nightly.yml, cron)
RUNNING = ("queued", "in_progress", "waiting", "requested", "pending")


def plan(now, runs, me):
    """(what, seconds, why) at `now` (aware) for the wake-up with the run id `me`, given the workflow's newest runs
    [(id, event, status, created)] (created aware): "wait" (seconds until START, then ask again), "start" (the night, now) or
    "end". Runs by workflow_dispatch are nights (started by a wake-up or by hand), runs by schedule are wake-ups."""
    # in UTC: between two times of the same zone Python counts the clock on the wall (an hour off across a change of the clock)
    now, local = now.astimezone(dt.timezone.utc), now.astimezone(BERLIN)
    day = local.date() + dt.timedelta(days=1 if local.time() >= LAST else 0)
    start = dt.datetime.combine(day, START, tzinfo=BERLIN).astimezone(dt.timezone.utc)
    at = "%s German time" % local.strftime("%d.%m. %H:%M")
    other = [r for r in runs if r[0] != me]
    # an earlier wake-up is waiting (or about to): it starts the night -- later ones always give way, so never two
    for rid, event, status, created in other:
        if event == "schedule" and status in RUNNING and rid < me:
            return "end", 0, "%s: an earlier wake-up (%s) waits for the night" % (at, created.astimezone(BERLIN).strftime("%d.%m. %H:%M"))
    if now < start:
        wait = start - now
        if wait > WAIT_MAX:
            return "end", 0, "%s: the night starts at %s, in %s -- a later wake-up waits for it" % (at, start.astimezone(BERLIN).strftime("%d.%m. %H:%M"), wait)
        return "wait", wait.total_seconds(), "%s: waiting %s for the night's start at %s" % (at, wait, start.astimezone(BERLIN).strftime("%H:%M"))
    # 3:05 to 4:00: a night running (by hand, too) or one started tonight counts as tonight's
    for rid, event, status, created in other:
        if event == "workflow_dispatch" and (status in RUNNING or created >= start - dt.timedelta(minutes=10)):
            return "end", 0, "%s: the night has started (%s, %s)" % (at, created.astimezone(BERLIN).strftime("%d.%m. %H:%M"), status)
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
    out = json.loads(gh("api", "repos/%s/actions/workflows/nightly.yml/runs?per_page=30" % repo))
    return [(int(r["id"]), r["event"], r["status"], dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")))
            for r in out.get("workflow_runs") or []]


def main():
    repo, me = os.environ["GITHUB_REPOSITORY"], int(os.environ["GITHUB_RUN_ID"])
    while True:
        what, seconds, why = plan(dt.datetime.now(dt.timezone.utc), runs(repo), me)
        print(why, flush=True)
        if what == "end":
            return 0
        if what == "wait":
            time.sleep(seconds)
            continue
        gh("workflow", "run", "nightly.yml", "--ref", "main", "-R", repo)
        print("started", flush=True)
        # end only once the night is in the list: a wake-up that looks in between must not start it a second time
        for _ in range(12):
            time.sleep(10)
            if plan(dt.datetime.now(dt.timezone.utc), runs(repo), me)[0] != "start":
                break
        return 0


if __name__ == "__main__":
    sys.exit(main())
