#!/usr/bin/env python3
"""A test set for Kontor's assistant, asked the way the user asks it: every task goes through assistant.Assistant.ask -- system
text, tools, memory, the steps of an answer -- to a model llama.cpp runs, on the demo's made-up world (demo.py). It shows
whether a change to Kontor, another model or another setting makes the answers better: points per group of tasks, time, tokens.

A developer's tool, not a part of Kontor: nothing in the program starts it. All data are made up (the demo's world; documents
and tasks of the test set jarvis-lab, invented firms and people). It needs no network and sends nothing anywhere.

    python3 tests/assistant_eval/run.py list
    python3 tests/assistant_eval/run.py run --stand-in reference              # no model: the stand-in gives each task's own answer
    python3 tests/assistant_eval/run.py run --assistant-dir DIR --model ID     # the model on this Mac (README.md)
    python3 tests/assistant_eval/run.py compare before.json after.json

What a run does: a Kontor of its own in a temporary folder (encrypted with a key made for the run, removed at the end) with
the demo's world in place of MoneyMoney; its assistant with the rights to read and to propose (no internet, no navigation);
before each task a new conversation and an empty memory; a change the model proposes is declined on its card -- nothing is
ever entered. With --assistant-dir the model is started exactly as Kontor starts it (llm_local.LocalAI: same options, same
sandbox) from the folder Kontor keeps llama.cpp and the model files in -- only that folder is read, never Kontor's data.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, REPO):
    if p not in sys.path:
        sys.path.insert(0, p)

import grading  # noqa: E402

GROUPS = {"a": "Auswertungen lesen (BWA, SuSa, Wertenachweis)", "b": "Lohnliste und Arbeitsvertrag", "d": "Rechnen mit Werkzeug",
          "f": "Gedächtnis", "g": "Wissen und Ehrlichkeit", "k": "Kontors Zahlen über seine Werkzeuge", "u": "Ursachen finden"}
EFFORTS = ("fast", "balanced", "thorough")
RIGHTS = {"figures": True, "transactions": True, "help": True, "page": True, "navigate": False, "enter_values": True, "categorize": True,
          "book": False, "rules": False, "receipts": False, "internet": False, "remote": False}
STAND_IN = "stand-in"                                   # the id of the made-up model file the stand-in "runs"
ENOUGH = 5                                              # tasks in a row without an answer: the run ends
MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember")


def de(x: float, unit: str = " €") -> str:
    """A figure as Kontor writes it in German: 1.234,56 €."""
    s = "%.2f" % abs(x)
    whole, frac = s.split(".")
    whole = re.sub(r"(?<=\d)(?=(\d{3})+$)", ".", whole)
    return "%s%s,%s%s" % ("-" if x < 0 else "", whole, frac, unit)


def label(month: str) -> str:
    return "%s %s" % (MONTHS[int(month[5:7]) - 1], month[:4])


def load_tasks(groups=None, ids=None):
    with open(os.path.join(HERE, "tasks.json"), encoding="utf-8") as f:
        tasks = json.load(f)["tasks"]
    return [t for t in tasks if (not groups or t["group"] in groups) and (not ids or t["id"] in ids)]


def taskset_version() -> str:
    h = hashlib.sha256()
    for name in ["tasks.json"] + sorted(os.path.join("docs", n) for n in os.listdir(os.path.join(HERE, "docs"))):
        with open(os.path.join(HERE, name), "rb") as f:
            h.update(name.encode() + b"\0" + f.read())
    return h.hexdigest()[:12]


# -- a Kontor of its own, on the demo's world ------------------------------------------------------------------------------------
def build(folder: str, today=None):
    """Kontor in folder with the demo's world as its MoneyMoney, read and calculated once. Returns (app, world)."""
    import categorize
    import demo
    import service
    import storage
    store = storage.Store(folder, os.urandom(32))        # (encrypted with a key made for this run, kept nowhere)
    std = sorted(categorize.STANDARD)
    world = demo.World(today or date.today(), std[0] if len(std) == 1 else "Unkategorisiert")
    store.save("config.json", demo.config(world, {}, os.path.join(folder, "Belege")))
    store.save("state.json", world.state())
    app = service.App(store, folder, bridge_factory=world.bridge)
    app.do_run(False, True)
    app.rebuild_report(wait=True)
    return app, world


def facts(app, world) -> dict:
    """What is true in the demo's world, from Kontor's own figures -- the tasks about them take their expected values from here
    (the world is counted back from today: no figure of it stands in a file)."""
    ds = app.dataset()
    area = {v: k for k, v in ds["area_names"].items()}
    priv, gbr, ug = (ds["areas"][area[n]] for n in ("Privat", "Parkweg GbR", "Muster UG"))
    row = lambda b, name: next(r for r in b["balance"]["rows"] if r["name"] == name and not r.get("group"))["amounts"]
    y = world.purchase.year
    buy, after = "%d-11" % y, "%d-12" % y
    closed = [m for m in priv["months"] if m < priv["actual_until"]]
    last12, last = closed[-12:], closed[-1]
    cf_row = lambda b, sec, part: next(z for s in b["cashflow"]["sections"] if s["name"] == sec for z in s["rows"] if part in z["row"])["amounts"]
    txs = app.umsatzliste()
    nw, gnw = priv["balance"]["net_worth"], gbr["balance"]["net_worth"]
    part = row(priv, "Beteiligung Parkweg GbR")
    year = str(y + 1)
    spring = "%d-04" % (y + 1)                           # a holiday booked in April: the expenses of that month stand out
    june = "%d-06" % (y + 1)                             # the partners' yearly contribution
    f = {
        "y_buy": y, "m_buy": buy, "m_after": after, "l_buy": label(buy), "l_after": label(after), "year_after": year, "m_last": last, "l_last": label(last),
        "m_spring": spring, "l_spring": label(spring), "m_june": june, "l_june": label(june),
        "net_worth_now": round(nw[priv["actual_until"]], 2),
        "part_drop": round(part[buy] - part[after], 2), "gbr_drop": round(gnw[buy] - gnw[after], 2),          # (by how much they fell)
        "closing_costs": round(-sum(t["amount"] for t in txs if t["date"][:7] == after and "Parkweg 7" in t["purpose"] and t["entity"] == area["Parkweg GbR"]), 2),
        "first_value": round(part[buy], 2), "gbr_before": round(gnw[buy], 2),
        "own_funds": round(-next(t["amount"] for t in txs if t["date"][:7] == buy and "Eigenanteil" in t["purpose"]), 2),
        "gbr_rent_12": round(sum(cf_row(gbr, "income", "Miete").get(m) or 0 for m in last12), 2),
        "loan_now": round(-row(gbr, "Kaufpreisdarlehen")[gbr["actual_until"]], 2),
        "ug_cash_last": round(next(r for r in ug["balance"]["rows"] if r["name"] == "Geschäftskonto")["amounts"][last], 2),
        "food_year": round(-sum(t["amount"] for t in txs if t["name"] == "Biomarkt" and t["date"][:4] == year), 2),
        "nw_growth_year": round(nw[year + "-12"] - nw[after], 2),
        "saving_rate": round(100 * priv["figures"]["saving_rate"], 1),
        "holiday": round(-next(t["amount"] for t in txs if t["name"] == "Reisebüro" and t["date"][:7] == spring), 2),
        "contribution": round(next(t["amount"] for t in txs if t["date"][:7] == june and t["purpose"] == "Einlage" and t["entity"] == area["Parkweg GbR"]), 2),
    }
    f.update({k + "_de": de(v) for k, v in list(f.items()) if isinstance(v, float)})
    f["saving_rate_de"] = ("%.1f" % f["saving_rate"]).replace(".", ",") + " %"
    return f


def fill(obj, f: dict):
    """A task about the demo's world with its figures put in: "{name}" alone becomes the value itself, inside a text its words."""
    if isinstance(obj, str):
        m = re.fullmatch(r"\{(\w+)\}", obj)
        if m and m.group(1) in f:
            return f[m.group(1)]
        return re.sub(r"\{(\w+)\}", lambda x: str(f[x.group(1)]) if x.group(1) in f else x.group(0), obj)
    if isinstance(obj, list):
        return [fill(x, f) for x in obj]
    if isinstance(obj, dict):
        return {k: fill(v, f) for k, v in obj.items()}
    return obj


def prompt_of(task: dict) -> str:
    """The question as it is typed into the panel: documents pasted in before it."""
    parts = []
    for d in task.get("docs") or []:
        with open(os.path.join(HERE, "docs", d["file"]), encoding="utf-8") as fh:
            parts.append("[Dokument: %s – Text der Seiten]\n%s\n[Ende Dokument %s]" % (d["name"], fh.read().rstrip(), d["name"]))
    return "\n\n".join(parts + [task["prompt"]])


# -- the model ---------------------------------------------------------------------------------------------------------------
def use_stand_in(a, mode: str, tasks: list) -> str:
    """tests/fake_llama.py in place of llama.cpp, set up the way Kontor keeps a runtime and a model -- and told what to answer:
    each task's reference (its lookups, then its answer) or its wrong answer. Returns the model's id."""
    base = a.ai.base
    rdir = os.path.join(base, "runtime", "fake")
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(REPO, "tests", "fake_llama.py"), "rb") as f:
        src = b"#!" + sys.executable.encode() + b"\n" + f.read()
    binp = os.path.join(rdir, "llama-server")
    with open(binp, "wb") as f:
        f.write(src)
    os.chmod(binp, 0o755)
    version, flags, sock = a.ai._probe(binp, "off")
    a.ai._save("runtime.json", {"tag": "fake", "dir": "fake", "bin": "llama-server", "version": version, "flags": flags, "sock": sock, "sha256": "", "installed": ""})
    repo, name = "kontor/stand-in", "stand-in.gguf"
    path = a.ai.model_path(repo, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"GGUF stand-in")
    a.ai._save("models.json", {"models": {STAND_IN: {"repo": repo, "file": name, "size": 13, "sha256": "", "name": "Stand-in"}}})
    script = []
    for t in tasks:
        said = t["reference"] if mode == "reference" else t["wrong"]
        steps = [{"call": c["name"], "args": c.get("arguments") or {}} for step in said.get("calls") or [] for c in step[:1]]
        script.append({"q": t["prompt"][-160:], "steps": steps + [{"say": said["answer"]}]})
    with open(os.path.join(rdir, "script.json"), "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False)
    return STAND_IN


def use_real(a, folder: str, model: str) -> str:
    """The model in Kontor's own folder of llama.cpp and model files (only that folder is touched), started as Kontor starts it
    -- kept track of in a file of its own there ("eval.json"), so that a model Kontor itself runs is left alone."""
    from llm_local import LocalAI
    folder = os.path.abspath(os.path.expanduser(folder))
    if not os.path.isfile(os.path.join(folder, "runtime.json")) or not os.path.isfile(os.path.join(folder, "models.json")):
        raise SystemExit("No llama.cpp and models in %s -- give the folder 'assistant' of Kontor's data folder (README.md)." % folder)
    above = os.path.dirname(folder)                      # Kontor's data folder: the model's sandbox keeps it unread, as in Kontor itself
    a.ai = LocalAI(folder, above if os.path.dirname(above) != above else a.app.data_dir, a.app.program_dir, role="eval")
    have = a.ai.models()
    if model not in have:
        raise SystemExit("Model %r is not loaded there. Loaded: %s" % (model, ", ".join(sorted(have)) or "none"))
    return model


# -- one task ----------------------------------------------------------------------------------------------------------------
def give_notes(a, notes: list) -> None:
    """The memory for a task: empty, then its notes -- each with the day it was noted (a newer note counts over an older one)."""
    import memory
    a.memory.forget_all(quiet=True)
    real = memory._now
    try:
        for n in notes or []:
            memory._now = lambda day=n["date"]: day + " 12:00:00"
            a.memory.add(n["text"], how="manual", names=[])
    finally:
        memory._now = real


def run_task(a, task: dict, effort: str, limit: float) -> dict:
    """One task through the assistant, as a question typed into its panel on the overview. Returns what came of it."""
    a.reset()
    give_notes(a, task.get("notes"))
    res = {"id": task["id"], "group": task["group"], "title": task["title"], "status": "ok", "error": None, "answer": "", "calls": []}
    hist = [{"role": m["role"], "text": m["content"]} for m in task.get("history") or []]
    question = prompt_of(task)
    t0 = time.time()
    try:
        job = a.ask({"question": question, "effort": effort, "history": hist, "page": {"route": "#overview", "title": "Übersicht", "area": ""}})["job"]
    except ValueError as e:                              # (longer than this context takes: said, counted as not answered)
        res.update(status="skipped", error=str(e)[:300], score=0.0, passed=False, seconds=0.0)
        return res
    evs, first = [], None
    while True:
        r = a.poll(job, len(evs))
        for e in r["events"]:
            if first is None and e["type"] in ("think", "delta"):
                first = time.time() - t0
            if e["type"] in ("batch", "web") and e.get("state") == "ask":      # a card that waits for a click: declined -- nothing is entered, nothing fetched
                a.confirm(job, e["id"], False)
        evs += r["events"]
        if r["done"] or r.get("gone") or any(e["type"] in ("done", "error", "stopped") for e in evs):
            break
        if time.time() - t0 > limit:
            a.stop()
            a.ai.stop()                                  # (a model that hangs would hang for every task after this one: the next starts it anew)
            res.update(status="error", error="no answer within %d s" % limit)
            break
    end = next((e for e in reversed(evs) if e["type"] in ("done", "error", "stopped")), {})
    if end.get("type") == "error":
        res.update(status="error", error=str(end.get("text") or "")[:300])
    start = max([i for i, e in enumerate(evs) if e["type"] == "reset"] or [-1])       # (what was shown before a reset was a call, not the answer)
    res["answer"] = "".join(e["text"] for e in evs[start + 1:] if e["type"] == "delta").strip()[:8000]
    turn = getattr(a.job, "turn", None) if a.job is not None and a.job.id == job else None       # this answer's steps (the conversation takes them over a moment later)
    for m in turn or []:
        for tc in m.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except ValueError:
                args = None
            res["calls"].append({"name": tc["function"]["name"], "arguments": args})
    g = grading.grade(task, res["answer"], res["calls"]) if res["status"] == "ok" else {"score": 0.0, "passed": False, "details": {}}
    res.update(score=g["score"], passed=g["passed"], details=g.get("details", {}), seconds=round(time.time() - t0, 2),
               first_token=round(first, 2) if first is not None else None,
               **{k: end.get(k) for k in ("tokens", "tps", "thought", "reads", "cut", "limit") if k in end})
    return res


def summary(results: list) -> dict:
    groups = {}
    for g in sorted({r["group"] for r in results}):
        rs = [r for r in results if r["group"] == g]
        groups[g] = {"name": GROUPS.get(g, g), "tasks": len(rs), "passed": sum(1 for r in rs if r["passed"]), "points": round(100 * sum(r["score"] for r in rs) / len(rs), 1)}
    total = round(sum(g["points"] for g in groups.values()) / len(groups), 1) if groups else 0.0        # every group counts the same
    secs = [r["seconds"] for r in results if r.get("seconds")]
    tps = [r["tps"] for r in results if r.get("tps")]
    return {"points": total, "passed": sum(1 for r in results if r["passed"]), "tasks": len(results), "groups": groups,
            "seconds": round(sum(secs), 1), "tokens_per_second": round(sum(tps) / len(tps), 1) if tps else None}


def run(args, today=None) -> dict:
    """today: the day the demo's world is counted back from (the tests give a fixed one; left out: today)."""
    tasks = load_tasks(args.groups.split(",") if args.groups else None, args.tasks.split(",") if args.tasks else None)
    if not tasks:
        raise SystemExit("No such tasks.")
    folder = tempfile.mkdtemp(prefix="kontor-eval-")
    out = {}
    try:
        say = (lambda s: None) if args.quiet else (lambda s: print(s, file=sys.stderr, flush=True))
        say("Kontor with the demo's world ...")
        app, world = build(folder, today)
        f = facts(app, world)
        tasks = [fill(t, f) if t.get("world") else t for t in tasks]
        a = app.assistant
        if args.stand_in:
            model = use_stand_in(a, args.stand_in, tasks)
        else:
            model = use_real(a, args.assistant_dir, args.model)
        st = {"enabled": True, "model": model, "memory": True, "rights": RIGHTS, "sandbox": args.sandbox if not args.stand_in else "off", "save_chats": False}
        if args.context:
            st["context"] = args.context
        a.set(st)
        results, failed = [], 0
        try:
            for i, t in enumerate(tasks):
                r = run_task(a, t, args.effort, args.limit)
                results.append(r)
                say("[%d/%d] %s %-52s %s %4.2f %6.1f s%s" % (i + 1, len(tasks), t["id"], t["title"][:52], "+" if r["passed"] else "-", r["score"], r["seconds"],
                                                           "  " + r["error"][:70] if r.get("error") else ""))
                failed = failed + 1 if r["status"] == "error" else 0
                if failed >= ENOUGH:                     # the model does not start or does not answer: no use in asking the rest
                    say("ended after %d tasks in a row without an answer -- the rest was not asked" % failed)
                    break
        finally:
            app.assistant_stop()
            a.ai.stop()
        info = a.ai.models().get(model) or {}
        out = {"meta": {"tool": "kontor assistant_eval", "kontor": open(os.path.join(REPO, "VERSION")).read().strip(), "taskset": taskset_version(),
                        "label": args.label or model, "model": model, "file": info.get("file", ""), "llama_cpp": a.ai.runtime().get("tag", ""),
                        "effort": args.effort, "context": a.settings()["context"], "stand_in": args.stand_in or "",
                        "started": datetime.now().isoformat(timespec="seconds"), "machine": platform.machine(), "today": world.today.isoformat()},
               "summary": dict(summary(results), asked=len(results), of=len(tasks)), "results": results}
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    if args.out:
        with open(os.path.expanduser(args.out), "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
    return out


# -- reading results ---------------------------------------------------------------------------------------------------------
def table(run_: dict) -> str:
    s, m = run_["summary"], run_["meta"]
    lines = ["%s -- %s, effort %s, context %s, Kontor %s" % (m["label"], m["file"] or m["model"], m["effort"], m["context"], m["kontor"]),
             "%-48s %6s %9s" % ("group", "points", "passed")]
    for g, v in s["groups"].items():
        lines.append("%-48s %6.1f %5d/%-3d" % ("%s  %s" % (g, v["name"]), v["points"], v["passed"], v["tasks"]))
    lines.append("%-48s %6.1f %5d/%-3d   %s s%s" % ("all (every group counts the same)", s["points"], s["passed"], s["tasks"], s["seconds"],
                                                  ", %s tokens/s" % s["tokens_per_second"] if s["tokens_per_second"] else ""))
    if s.get("of", s["tasks"]) > s["tasks"]:
        lines.append("! ended early: %d of %d tasks asked -- the points count only those" % (s["tasks"], s["of"]))
    return "\n".join(lines)


def compare(a: dict, b: dict) -> str:
    """Two runs side by side: points per group, and which tasks were lost or won."""
    lines = ["before: %s (%s, %s)   after: %s (%s, %s)" % (a["meta"]["label"], a["meta"]["effort"], a["meta"]["kontor"], b["meta"]["label"], b["meta"]["effort"], b["meta"]["kontor"])]
    if a["meta"]["taskset"] != b["meta"]["taskset"]:
        lines.append("! the task sets differ (%s, %s): only partly comparable" % (a["meta"]["taskset"], b["meta"]["taskset"]))
    lines.append("%-48s %7s %7s %7s" % ("group", "before", "after", "change"))
    for g in sorted(set(a["summary"]["groups"]) | set(b["summary"]["groups"])):
        x, y = a["summary"]["groups"].get(g), b["summary"]["groups"].get(g)
        lines.append("%-48s %7s %7s %7s" % ("%s  %s" % (g, GROUPS.get(g, g)), "%.1f" % x["points"] if x else "-", "%.1f" % y["points"] if y else "-",
                                           "%+.1f" % (y["points"] - x["points"]) if x and y else ""))
    lines.append("%-48s %7.1f %7.1f %+7.1f" % ("all", a["summary"]["points"], b["summary"]["points"], b["summary"]["points"] - a["summary"]["points"]))
    was = {r["id"]: r for r in a["results"]}
    lost = [r["id"] for r in b["results"] if r["id"] in was and was[r["id"]]["passed"] and not r["passed"]]
    won = [r["id"] for r in b["results"] if r["id"] in was and not was[r["id"]]["passed"] and r["passed"]]
    lines.append("lost: %s" % (", ".join(lost) or "none"))
    lines.append("won: %s" % (", ".join(won) or "none"))
    lines.append("time: %s s -> %s s" % (a["summary"]["seconds"], b["summary"]["seconds"]))
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="assistant_eval", description="A test set for Kontor's assistant (made-up data).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the tasks")
    r = sub.add_parser("run", help="ask the assistant every task and grade its answers")
    r.add_argument("--stand-in", choices=("reference", "wrong"), help="no model: the stand-in answers with each task's reference (or its wrong answer)")
    r.add_argument("--assistant-dir", help="the folder 'assistant' of Kontor's data folder: llama.cpp and the model files")
    r.add_argument("--model", help="the id of a model loaded there, as under Einstellungen -> KI-Assistent (e.g. qwen3.6-35b-a3b)")
    r.add_argument("--effort", choices=EFFORTS, default="balanced")
    r.add_argument("--context", type=int, help="tokens (16384, 32768, 65536, 131072); left out: by this machine's memory, as Kontor does")
    r.add_argument("--sandbox", choices=("strict", "basic", "off"), default="strict")
    r.add_argument("--groups", help="only these groups, e.g. d,u")
    r.add_argument("--tasks", help="only these tasks, e.g. u01,d03")
    r.add_argument("--limit", type=float, default=1800.0, help="seconds one task may take")
    r.add_argument("--label", help="a name for this run in the results")
    r.add_argument("--out", help="write the results to this file (JSON)")
    r.add_argument("--quiet", action="store_true")
    c = sub.add_parser("compare", help="two runs side by side")
    c.add_argument("before")
    c.add_argument("after")
    s = sub.add_parser("show", help="one task of a run: answer, lookups, grading")
    s.add_argument("results")
    s.add_argument("task")
    return ap


def main(argv=None) -> int:
    ap = parser()
    args = ap.parse_args(argv)
    if args.cmd == "list":
        for t in load_tasks():
            print("%s  %-20s %s" % (t["id"], GROUPS[t["group"]][:20], t["title"]))
        return 0
    if args.cmd == "run":
        if not args.stand_in and not (args.assistant_dir and args.model):
            ap.error("give --assistant-dir and --model, or --stand-in")
        print(table(run(args)))
        return 0
    if args.cmd == "compare":
        with open(os.path.expanduser(args.before), encoding="utf-8") as fa, open(os.path.expanduser(args.after), encoding="utf-8") as fb:
            print(compare(json.load(fa), json.load(fb)))
        return 0
    with open(os.path.expanduser(args.results), encoding="utf-8") as fh:
        res = next((x for x in json.load(fh)["results"] if x["id"] == args.task), None)
    print(json.dumps(res, ensure_ascii=False, indent=1) if res else "no such task in these results")
    return 0


if __name__ == "__main__":
    sys.exit(main())
