"""Kontor on worlds of special cases (tests/data_worlds.py): long names, large amounts, empty and very full areas, other
currencies, month and year ends, a new user -- through the whole service, not only the money logic:

  * the sync and the figures: no area fails, every area and month adds up (net worth and cash explained to the cent), the net
    worth now is what the accounts in euro hold, nothing is NaN or infinite, accounts in another currency stand apart in their
    currency (never converted, never in a euro sum);
  * every request the pages make answers (no error, valid JSON -- a NaN would break the page), the downloads too;
  * every tool of the assistant that reads answers on every area, account and month (also before the world began and on its
    last day), its figures are those of the pages, and a whole question runs through it (llama.cpp's stand-in);
  * every page in the browser (a tour as in test_tour: menu and sub-pages) on the world's day as today: no script error, the
    page never scrolls sideways, no raw text key, no undefined/NaN.

Every run: the fixed worlds (data_worlds.FIXED) and a few random ones; the pages of each fixed world in one view (they
take turns: Mac dark, iPhone light, Mac light, iPhone dark; one in English). At night (nightly.yml) new random worlds until
the time is up, pages in every view. A failure names its world ("seed …"; KONTOR_FUZZ_SEED=<number> builds it again)."""
import itertools
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import fixtures as F                  # noqa: E402
import data_worlds as D               # noqa: E402
import core                           # noqa: E402
import service                        # noqa: E402
import assistant as A                 # noqa: E402
import realestate                     # noqa: E402
import receipts                       # noqa: E402
from service import App, make_handler  # noqa: E402

PASSWORD = "sehr-geheimes-passwort"
VIEWS = [("mac", "dark", "de"), ("iphone", "light", "de"), ("mac", "light", "de"), ("iphone", "dark", "de"), ("mac", "dark", "en")]
DATED = (core, service, A, realestate, receipts)            # the modules that ask for today


def seeds(name):
    """Random worlds: a few on every run (fewer than the money logic's: each is a whole service), at night as many as fit."""
    env = os.environ.get
    got = F.fuzz_seeds(name)
    if not (env("KONTOR_FUZZ_SEED") or env("KONTOR_FUZZ_MINUTES") or env("KONTOR_FUZZ_RANDOM")):
        return itertools.islice(got, 4)
    return got


def at_night():
    return bool(os.environ.get("KONTOR_FUZZ_MINUTES") or os.environ.get("KONTOR_FUZZ_SEED") or os.environ.get("KONTOR_FUZZ_RANDOM"))


def no_nan(text):
    """JSON as a browser reads it: NaN, Infinity are no JSON (JSON.parse fails on them)."""
    def bad(c):
        raise ValueError("%s in JSON" % c)
    return json.loads(text, parse_constant=bad)


def finite(x, at=""):
    """Every number in it finite."""
    if isinstance(x, float):
        assert math.isfinite(x), "%s: %r" % (at, x)
    elif isinstance(x, dict):
        for k, v in x.items():
            finite(v, "%s.%s" % (at, k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            finite(v, "%s[%d]" % (at, i))


class Running:
    """Kontor on one world: its own data folder, the world's day as today, its MoneyMoney; a sync done, the report built;
    the service on a free port, signed in."""

    def __init__(self, w, http=True):
        self.w = w
        self.dir = tempfile.mkdtemp(prefix="kontor-dw-")
        self.kept = [(m, m.date) for m in DATED] + [(service, None)]
        self._is_running = service.is_running
        day = w.today

        class Today(date):
            @classmethod
            def today(cls):
                return day
        for m in DATED:
            m.date = Today
        service.is_running = lambda: True
        store = F.new_store(self.dir)
        store.save("config.json", w.config(os.path.join(self.dir, "Belege")))
        store.save("state.json", w.state())
        self.app = App(store, self.dir, bridge_factory=w.bridge)
        self.result = self.app.do_run(False, True)
        self.app.rebuild_report(wait=True)
        self.srv = None
        if http:
            self.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
            threading.Thread(target=self.srv.serve_forever, daemon=True).start()
            self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]
            self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
            self.csrf = None
            code, r = self.call("/api/setup", {"password": PASSWORD})
            assert code == 200, r
            self.csrf = r["csrf"]

    def call(self, path, body=None, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method="POST" if data is not None else "GET")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.csrf:
            req.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.opener.open(req, timeout=120) as r:
                payload = r.read()
                return r.status, (payload if raw else no_nan(payload.decode() or "{}"))
        except urllib.error.HTTPError as e:
            payload = e.read()
            return e.code, (payload if raw else no_nan(payload.decode() or "{}"))

    def wait_report(self):
        with self.app.rebuild_cv:
            self.app.rebuild_cv.wait_for(lambda: not self.app.rebuild_running and not self.app.rebuild_pending, timeout=120)

    def close(self):
        try:
            self.app.assistant_stop()
        except Exception:
            pass
        if self.srv:
            self.srv.shutdown(); self.srv.server_close()
        for m, d in self.kept:
            if d is not None:
                m.date = d
        service.is_running = self._is_running
        shutil.rmtree(self.dir, ignore_errors=True)


# -- what every world must show -------------------------------------------------------------------------------------------
def check_figures(t, run):
    """The sync and the report: no failure, everything adds up, other currencies apart."""
    w, app = run.w, run.app
    t.assertNotEqual(run.result.get("status"), "error", run.result)
    ds = app.dataset()
    t.assertFalse(ds.get("empty"), "no report")
    no_nan(json.dumps(ds, default=str))
    finite(ds, "dataset")
    names = {a["id"]: a["name"] for a in w.config("")["areas"]}
    t.assertEqual(sorted(ds["area_names"].values()), sorted(names.values()))
    accounts = {a["uuid"]: a for a in w.accounts}
    for key, area in ds["areas"].items():
        at = names.get(key, key)
        t.assertNotIn("error", area, at)
        for m, u in (area.get("cashflow") or {}).get("reconciliation", {}).items():
            for check, why in (("unexplained", "reasons"), ("diff_cash", "reasons_cash")):
                reasons = {g[0] for g in u.get(why) or []}
                t.assertTrue(abs(u[check]) < 0.005 or (reasons and reasons <= {"ue_unterwegs"}), "%s %s: %s=%s %s" % (at, m, check, u[check], u.get(why)))
        # nothing unclear -- but a transfer on its way today (out, not yet in): its booking without a counterpart, as it is
        unclear = {z["row"]: {m: round(v, 2) for m, v in z["amounts"].items() if abs(v) >= 0.005}
                   for sec in (area.get("cashflow") or {}).get("sections") or [] if sec["name"] == "unclear" for z in sec["rows"]}
        expect = {}
        for src, dst, d, x in w.pending:
            if uid_area(w, src) == key:
                row = expect.setdefault("Umbuchung nach %s ohne Gegenbuchung" % w.name_of(dst), {})
                row[d.strftime("%Y-%m")] = round(row.get(d.strftime("%Y-%m"), 0.0) - x, 2)
        t.assertEqual({k: v for k, v in unclear.items() if v}, expect, "%s: unclear" % at)
        # the net worth now: what the area's accounts in euro hold (the stakes Kontor books included; other currencies apart)
        nw = (area.get("balance") or {}).get("net_worth") or {}
        if nw:
            group = w.config("")["areas"][[a["id"] for a in w.config("")["areas"]].index(key)]["accounts"][0].split(" | ")[0]
            mine = members(w, group)
            euro = round(sum(a["balance"][0][0] for a in w.accounts if a["uuid"] in mine and not a["group"] and a["currency"] == "EUR"), 2)
            now = max(m for m in nw if m <= w.today.strftime("%Y-%m"))
            t.assertAlmostEqual(nw[now], euro, 2, "%s: net worth %s" % (at, now))
        out = (area.get("balance") or {}).get("outside") or []
        for r in out:
            if accounts.get(r.get("id"), {}).get("currency", "EUR") != "EUR":
                t.assertEqual(r.get("role"), "foreign_currency", r)
                t.assertEqual(r.get("currency"), accounts[r["id"]]["currency"], r)
    # the tax overview: amounts in another currency in no sum (they have categories of their own here), those accounts named
    fx_paths = {p.replace("\\", " / ") for p in D.FX_CATEGORIES}
    for e in (ds.get("tax") or {}).get("entities") or []:
        for y, v in (e.get("years") or {}).items():
            t.assertEqual({c["path"] for c in v.get("categories") or []} & fx_paths, set(), "tax %s %s: another currency added to euros" % (e["name"], y))
        group = next(a["accounts"][0].split(" | ")[0] for a in w.config("")["areas"] if a["id"] == e["uuid"])
        named = sorted(a["name"] for a in w.accounts if a["uuid"] in members(w, group) and not a["group"] and a["currency"] != "EUR" and not a["portfolio"])
        t.assertEqual(sorted(x["account"] for x in e.get("not_converted") or []), named, "tax %s: accounts not converted" % e["name"])
    foreign = [a for a in w.accounts if not a["group"] and a["currency"] != "EUR"]
    if foreign:
        shown = {r.get("id") for area in ds["areas"].values() for r in (area.get("balance") or {}).get("outside") or []}
        t.assertLessEqual({a["uuid"] for a in foreign}, shown, "other currencies apart")
    return ds


def uid_area(w, key):
    """The area (its id) an account of the world is in."""
    for a in w.config("")["areas"]:
        if D.uid(key) in members(w, a["accounts"][0].split(" | ")[0]):
            return a["id"]
    return None


def members(w, group_uuid):
    """The accounts under a group (MoneyMoney's order and indentation)."""
    out, inside, level = set(), False, 0
    for a in w.accounts:
        if a["uuid"] == group_uuid:
            inside, level = True, a["indentation"]
            continue
        if inside:
            if a["indentation"] <= level:
                break
            out.add(a["uuid"])
    return out


def get_requests(w, ds):
    """Every request the pages read with (GET), for this world."""
    year = str(w.today.year)
    out = ["/api/status", "/api/status?fresh=1", "/api/dataset", "/api/config", "/api/plan", "/api/accounts", "/api/categories",
           "/api/sync", "/api/runs", "/api/log", "/api/receipts?files=1", "/api/assistant/status", "/api/assistant/chats",
           "/api/assistant/changes", "/api/help", "/api/categories/proposals", "/api/categories/written", "/api/categories/positions",
           "/api/categories/unassigned?min=0", "/api/categories/unassigned?year=%s&min=0" % year, "/api/offline/verifier", "/api/timemachine", "/api/python",
           "/api/transactions", "/api/transactions?limit=5000", "/api/transactions?q=" + urllib.parse.quote(D.LONG_WORD[:20]),
           "/api/transactions?q=" + urllib.parse.quote("99.999.999,99"), "/api/package/export"]
    for key in ds.get("areas") or {}:
        q = urllib.parse.quote(key)
        out += ["/api/transactions?year=%s&uncategorized=1&limit=1&entity=%s" % (year, q),
                "/api/transactions?year=%s&without_receipt=1&direction=out&limit=1&entity=%s" % (year, q)]
        for kind in ("balance", "cashflow", "planning", "tax", "transactions", "holdings", "accounts"):
            out.append("/api/export/%s.xlsx?area=%s" % (kind, q))
        out.append("/api/export/cashflow.xlsx?area=%s&mode=years" % q)
    for a in w.accounts:
        if not a["group"]:
            out.append("/api/history?account=" + urllib.parse.quote(a["uuid"]))
    return out


def check_requests(t, run, ds):
    for path in get_requests(run.w, ds):
        raw = "/export/" in path or "/package/" in path
        code, body = run.call(path, raw=raw)
        t.assertEqual(code, 200, "%s: %s" % (path, body if not raw else body[:300]))
        if raw:
            t.assertGreater(len(body), 100, path)
        else:
            finite(body, path)
    # transactions: each in its account's currency, the sum in euros only, other currencies apart
    cur = {a["uuid"]: a["currency"] for a in run.w.accounts}
    code, r = run.call("/api/transactions?limit=5000")
    for x in r["transactions"]:
        t.assertEqual(x.get("currency"), None if cur[x["account"]] == "EUR" else cur[x["account"]], x)
    if r["hits"] == len(r["transactions"]):
        t.assertAlmostEqual(r["sum"], round(sum(x["amount"] for x in r["transactions"] if not x.get("currency")), 2), 2)
        other = {}
        for x in r["transactions"]:
            if x.get("currency"):
                other[x["currency"]] = round(other.get(x["currency"], 0.0) + x["amount"], 2)
        t.assertEqual({k: round(v, 2) for k, v in r["sum_other"].items()}, other)
    # to assign: another currency in a group of its own, its sum in it
    by_name = {}
    for a in run.w.accounts:
        by_name.setdefault(a["name"], set()).add(a["currency"])
    code, r = run.call("/api/categories/unassigned?year=%d&min=0" % run.w.today.year)
    for g in r.get("groups") or []:
        for x in g["transactions"]:
            t.assertEqual(by_name.get(x["account"], {"EUR"}), {g.get("currency", "EUR")}, "a group mixes currencies: %s" % g["name"])
    code, r = run.call("/api/categories")
    fx_paths = {p.replace("\\", " / ") for p in D.FX_CATEGORIES}
    for c in r.get("categories") or []:
        if str(c.get("path") or "").replace("\\", " / ") in fx_paths:
            t.assertFalse(c.get("sum_12m"), "a category of another currency summed in euros: %s" % c)
    # what the pages ask with a body (reading only)
    for path, body in (("/api/report", {}), ("/api/rules/preview", {"config": {}}), ("/api/categories/areas", {"without": [], "wait": True}),
                       ("/api/categories/areas", {"period": {"from": "", "to": ""}, "wait": True})):
        code, r = run.call(path, body)
        t.assertIn(code, (200, 202), "%s: %s" % (path, r))


def tool_calls(w, ds):
    """The assistant's reading tools with arguments from this world: every area, account and month the user could name --
    the first and the last, one before the world began, the year's end and start."""
    names = [a["name"] for a in w.config("")["areas"]]
    accs = [a["name"] for a in w.accounts if not a["group"]]
    now, first = w.today.strftime("%Y-%m"), w.start.strftime("%Y-%m")
    before = D.months_back(w.start, 2).strftime("%Y-%m")
    dec, jan = "%d-12" % (w.today.year - 1), "%d-01" % w.today.year
    year = str(w.today.year)
    out = [("calculate", {"expression": "99999999.99 * 12 + 0.01"}), ("get_overview", {}), ("get_status", {}), ("get_securities", {}),
           ("list_accounts", {}), ("get_rules", {}), ("get_categories", {}), ("get_categories", {"text": D.LONG_WORD}), ("get_uncategorized", {}),
           ("get_auto_bookings", {}), ("get_real_estate", {}), ("get_real_estate", {"year": year}), ("get_planning", {}), ("get_tax", {}),
           ("search_help", {"query": "Fremdwährung"}), ("search_help", {"query": D.LONG_WORD}), ("get_current_page", {}),
           ("search_transactions", {"text": D.LONG_WORD}), ("search_transactions", {"text": "Umschichtung"}), ("search_transactions", {"text": "Dividende"}),
           ("search_transactions", {"uncategorized": True}), ("search_transactions", {"from": dec, "to": jan}),
           ("get_cashflow", {"from": before, "to": now, "group_by": "month", "detail": "categories"}), ("get_changes", {}),
           ("get_net_worth_drivers", {"from": dec, "to": jan})]
    for n in names:
        out += [("get_overview", {"area": n}), ("get_balance", {"area": n}), ("get_balance", {"area": n, "month": first}),
                ("get_balance", {"area": n, "month": before}), ("get_balance", {"area": n, "month": now, "positions_only": True}),
                ("get_balance_history", {"area": n, "months": 60}), ("get_balance_history", {"area": n, "yearly": True}),
                ("get_cashflow", {"area": n, "group_by": "year", "detail": "rows"}), ("get_cashflow", {"area": n, "from": dec, "to": jan, "group_by": "month"}),
                ("get_cashflow", {"area": n, "with_plan": True}), ("get_changes", {"area": n, "against": "year_before"}),
                ("get_net_worth_drivers", {"area": n}), ("get_planning", {"area": n}), ("get_tax", {"area": n, "year": year}),
                ("get_uncategorized", {"area": n, "year": year}), ("list_accounts", {"area": n}), ("search_transactions", {"area": n})]
    for a in accs[:60]:                  # by name alone (several of one name: the tool asks for the path)
        out += [("get_account_history", {"account": a, "months": 60}), ("get_balance_history", {"row": a}), ("search_transactions", {"account": a})]
    return out


def tool_musts(w, ds):
    """Calls that must answer without an error: every account by its path, every account in euro as a row of its area's
    balance sheet (another currency: said so, with where its balances are)."""
    names = {a["id"]: a["name"] for a in w.config("")["areas"]}
    by_uuid = {a["uuid"]: a for a in w.accounts}
    out = []
    for acc in (ds.get("accounts") or [])[:80]:
        if acc.get("group"):
            continue
        out += [("get_account_history", {"account": acc["path"], "months": 60}), ("search_transactions", {"account": acc["path"]})]
        mine = by_uuid.get(acc["uuid"])
        area = next((k for k in names if mine and acc["uuid"] in members(w, next(x["accounts"][0].split(" | ")[0] for x in w.config("")["areas"] if x["id"] == k))), None)
        if mine and area and mine["currency"] == "EUR":
            out.append(("get_balance_history", {"area": names[area], "row": acc["name"]}))
    return out


def check_assistant(t, run, ds):
    """Every reading tool answers; its figures are the pages'; a whole question runs through it."""
    import test_assistant as TA
    keep = TA.L._open
    try:
        TA.install(run.app)
        a = run.app.assistant
        a.set({"rights": {k: True for k in ("figures", "transactions", "help", "page", "navigate")}})
        job = A.Job()
        ctx = {"job": job, "conv": a.conv, "area": "", "page": {"route": "#overview"}}
        for name, args in tool_calls(run.w, ds):
            out = a._use(job, name, json.dumps(args, ensure_ascii=False), ctx)
            # too long for the model's room (the smallest: a small context): its lists shortened, saying so -- never cut in the middle
            t.assertNotIn("[cut:", out, "%s %s: cut (%d characters)" % (name, args, len(out)))
            res = no_nan(out)
            t.assertNotIn("That did not work", out, "%s %s: %s" % (name, args, out[:300]))
            t.assertNotIn("There is no tool", out, name)
            if isinstance(res, dict) and "error" in res:
                t.assertTrue(args, "%s without arguments: %s" % (name, res))       # an error only for something the user named
        for name, args in tool_musts(run.w, ds):
            out = a._use(job, name, json.dumps(args, ensure_ascii=False), ctx)
            t.assertFalse(out.startswith('{"error"'), "%s %s: %s" % (name, args, out[:300]))
        paths = {x["uuid"]: x["path"] for x in ds.get("accounts") or []}
        for acc in run.w.accounts:      # another currency: in no balance sheet in euros -- the tool says so and where its balances are
            if not acc["group"] and acc["currency"] != "EUR":
                out = a._use(job, "get_balance_history", json.dumps({"row": acc["name"]}, ensure_ascii=False), ctx)
                t.assertIn(acc["currency"], out, out[:300]); t.assertIn("get_account_history", out, out[:300])
                got = no_nan(a._use(job, "get_account_history", json.dumps({"account": paths[acc["uuid"]]}, ensure_ascii=False), ctx))
                t.assertEqual(got.get("currency"), acc["currency"], got)            # its balances: said to be in its currency
        found = no_nan(a._use(job, "search_transactions", json.dumps({"text": "Dividende"}), ctx))
        if "fx" in run.w.kinds and found.get("count"):         # only dollars: nothing in the euro sums, all in other_currencies
            t.assertEqual((found["sum"], found["sum_in"]), (0, 0), found)
            t.assertEqual(found["other_currencies"]["USD"]["count"], found["count"], found)
            t.assertTrue(all(x.get("currency") == "USD" for x in found["transactions"]), found)
        cats = no_nan(a._use(job, "get_categories", "{}", ctx))
        for c in cats.get("categories") or []:
            if str(c["category"]).replace("\\", " / ") in {p.replace("\\", " / ") for p in D.FX_CATEGORIES}:
                t.assertFalse(c.get("sum_last_12_months"), c)
        fx_names = {x["name"] for x in run.w.accounts if not x["group"] and x["currency"] != "EUR"}
        for n in ds["area_names"].values():          # what moved the net worth in euros: never an amount in another currency
            got = no_nan(a._use(job, "get_net_worth_drivers", json.dumps({"area": n}, ensure_ascii=False), ctx))
            t.assertFalse([x for x in got.get("largest_transactions") or [] if x.get("account") in fx_names], got.get("largest_transactions"))
        main = ds["main_area"]
        over = a.t_get_overview({"area": ds["area_names"][main]}, ctx)
        t.assertIn(ds["area_names"][main], json.dumps(over, ensure_ascii=False))
        accs = json.dumps(a.t_list_accounts({}, ctx), ensure_ascii=False)
        for acc in run.w.accounts:
            if not acc["group"] and acc["currency"] != "EUR":
                t.assertIn(acc["currency"], accs, acc["name"])
        if "long" in run.w.kinds and not {"bare"} & run.w.kinds:
            found = a.t_search_transactions({"text": D.LONG_WORD}, ctx)
            t.assertTrue(found.get("transactions") or found.get("count") or found.get("hits"), found)
        q = "\n".join("call %s %s" % (n, json.dumps(x, ensure_ascii=False)) for n, x in
                      [("get_overview", {}), ("list_accounts", {}), ("get_balance", {"area": ds["area_names"][main]})])
        r = a.ask({"question": q})
        evs = TA.events(a, r["job"], seconds=60)
        t.assertEqual(evs[-1]["type"], "done", evs[-3:])
        t.assertTrue(TA.text_of(evs).startswith("Ergebnis: "), TA.text_of(evs)[:300])
    finally:
        TA.L._open = keep


class Shortened(unittest.TestCase):
    """A tool's result too long for the model's room: its longest lists end early, saying how many are left out -- whole JSON,
    the outer lists first; without a list to shorten: None (the text is then cut)."""

    def test_lists_end_early_and_say_so(self):
        res = {"year": 2026, "areas": [{"area": "Bereich %d" % i, "positions": [{"category": "Kostenart %02d.%d" % (i, k), "amount": 1234.56 * k}
                                                                               for k in range(40)]} for i in range(9)], "note": "n"}
        for most in (7000, 3000):
            out = A._shortened(res, most)
            self.assertLessEqual(len(out), most)
            got = no_nan(out)
            self.assertEqual((got["year"], got["note"]), (2026, "n"))
            self.assertEqual([x["area"] for x in got["areas"]], ["Bereich %d" % i for i in range(9)])      # every area, in order
            for i, x in enumerate(got["areas"]):                                         # each its first positions, the rest said
                self.assertEqual(x["positions"], res["areas"][i]["positions"][:len(x["positions"])])
                self.assertEqual(got["left_out"]["areas[%d].positions" % i], 40 - len(x["positions"]))
            self.assertLessEqual(max(len(x["positions"]) for x in got["areas"]) - min(len(x["positions"]) for x in got["areas"]), 1)    # alike: alike shares
        self.assertEqual(len(res["areas"]), 9)                                            # the tool's own result untouched
        self.assertIsNone(A._shortened({"text": "x" * 9000}, 7000))                      # nothing to shorten: cut as before
        self.assertIsNone(A._shortened(["a"] * 9000, 7000))
        # series side by side with their months: never shortened (a value must not slip to another month) -- cut as before
        self.assertIsNone(A._shortened({"months": ["2026-%02d" % m for m in range(1, 13)] * 5, "series": {k: [1234.56] * 60 for k in "abcdefghij"}}, 2000))

    def test_every_part_of_a_structure_keeps_its_share(self):
        """One large section beside small ones: every section stays, the large one is shortened, the small ones whole."""
        row = lambda name, k: {"row": "%s %d" % (name, k), "amounts": {"2026-%02d" % m: -123.45 * m for m in range(1, 13)}}
        res = {"area": "Privat", "sections": [{"name": "income", "rows": [row("Gehalt", k) for k in range(2)]},
                                              {"name": "expenses", "rows": [row("Kostenart", k) for k in range(60)]},
                                              {"name": "investing", "rows": [row("Depot", k) for k in range(2)]},
                                              {"name": "financing", "rows": [row("Darlehen", k) for k in range(2)]}]}
        got = no_nan(A._shortened(res, 7000))
        self.assertEqual([x["name"] for x in got["sections"]], ["income", "expenses", "investing", "financing"])
        self.assertEqual(got["sections"][0], res["sections"][0])                           # small ones whole
        self.assertEqual(got["sections"][3], res["sections"][3])
        kept = len(got["sections"][1]["rows"])
        self.assertTrue(10 < kept < 60, kept)
        self.assertEqual(got["left_out"], {"sections[1].rows": 60 - kept})
        self.assertLessEqual(len(json.dumps(got, ensure_ascii=False, separators=(",", ":"))), 7000)
        # lists side by side in one object: each in its share, not one emptied and another whole
        many = {"accounts": [{"account": "Konto %02d" % i, "balance": 1000.0 * i} for i in range(80)],
                "categories": [{"category": "Kategorie %03d" % i, "sum": -12.5 * i} for i in range(160)]}
        got = no_nan(A._shortened(many, 3000))
        self.assertTrue(got["accounts"] and got["categories"], got["left_out"])
        self.assertEqual(set(got["left_out"]), {"accounts", "categories"})


class Figures(unittest.TestCase):
    """Sync, report, requests and the assistant on every world (no browser)."""

    def world(self, w):
        run = Running(w)
        try:
            ds = check_figures(self, run)
            check_requests(self, run, ds)
            check_assistant(self, run, ds)
        finally:
            run.close()

    def test_fixed_worlds(self):
        for name in D.FIXED:
            w = D.World(name)
            with self.subTest(world=name):
                try:
                    self.world(w)
                except AssertionError as e:
                    raise AssertionError("%s -- %s" % (w.describe(), e)) from e

    def test_random_worlds(self):
        for seed in seeds("Datenwelten (Zahlen, Anfragen, Assistent)"):
            w = D.World(seed=seed)
            with self.subTest(seed=seed), F.case(seed):
                try:
                    self.world(w)
                except AssertionError as e:
                    raise AssertionError("seed %d: %s -- %s" % (seed, w.describe(), e)) from e


class Pages(unittest.TestCase):
    """Every page in the browser on the world's day."""

    @classmethod
    def setUpClass(cls):
        from test_tour import _playwright
        cls.browsers = staticmethod(_playwright())

    def tour(self, browser, w, views):
        from test_tour import CHECKS, DEVICES, settle
        run = Running(w)
        problems, reached = [], set()
        try:
            for device, theme, lang in views:
                run.app.config.setdefault("ui", {})["language"] = lang
                view = "%s/%s/%s" % (device, theme, lang)
                ctx = browser.new_context(**DEVICES[device])
                ctx.add_init_script("try { localStorage.setItem('kontor.theme', %s); localStorage.setItem('kontor.lang', %s); } catch (e) {}"
                                    % (json.dumps(theme), json.dumps(lang)))
                ctx.clock.set_system_time(datetime(w.today.year, w.today.month, w.today.day, 11, 0))
                pg = ctx.new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append("Skriptfehler: %s" % e))
                pg.on("console", lambda m: errors.append("Konsole: %s" % m.text) if m.type == "error" else None)
                pg.goto(run.base + "/")
                pg.fill("#login-pw", PASSWORD)
                pg.click("#login-btn")
                pg.wait_for_selector("#shell:not(.hidden)", timeout=30000)
                settle(pg)
                todo = pg.evaluate("[...document.querySelectorAll('#nav a[href^=\"#\"]')].map(a => a.getAttribute('href'))")
                self.assertGreater(len(todo), 5, "menu not found")
                seen = set()
                while todo:
                    h = todo.pop(0)
                    if h in seen:
                        continue
                    seen.add(h); errors.clear()
                    pg.evaluate("h => { location.hash = h; }", h)
                    try:
                        settle(pg, timeout=40)
                    except AssertionError as e:
                        problems.append("%s %s: %s" % (view, h, e)); continue
                    tab = h[1:].split("/")[0]
                    todo += [s for s in pg.evaluate("tab => [...new Set([...document.querySelectorAll('#main a[href^=\"#' + tab + '/\"]')].map(a => a.getAttribute('href').split('?')[0]))]", tab) if s not in seen]
                    r = pg.evaluate(CHECKS)
                    problems += ["%s %s: %s" % (view, h, e) for e in errors]
                    if r["overflow"]:
                        problems.append("%s %s: seitlich zu breit %s" % (view, h, r["overflow"]))
                    problems += ["%s %s: Textschlüssel statt Text: %s" % (view, h, k) for k in r["keys"]]
                    problems += ["%s %s: Text mit undefined/NaN/Platzhalter: %s" % (view, h, j) for j in r["junk"]]
                reached |= seen
                ctx.close()
        finally:
            run.close()
        self.assertGreater(len(reached), 10, "too few pages: %s" % sorted(reached))
        self.assertEqual(problems, [], "\n".join(problems))

    def test_fixed_worlds(self):
        with self.browsers() as p:
            b = p.chromium.launch()
            try:
                for i, name in enumerate(D.FIXED):
                    w = D.World(name)
                    views = VIEWS if at_night() else [VIEWS[i % len(VIEWS)]]
                    with self.subTest(world=name):
                        try:
                            self.tour(b, w, views)
                        except AssertionError as e:
                            raise AssertionError("%s -- %s" % (w.describe(), e)) from e
            finally:
                b.close()

    def test_random_worlds(self):
        if not at_night():
            self.skipTest("pages of random worlds: at night (nightly.yml)")
        with self.browsers() as p:
            b = p.chromium.launch()
            try:
                for i, seed in enumerate(seeds("Datenwelten (Seiten)")):
                    w = D.World(seed=seed)
                    with self.subTest(seed=seed), F.case(seed):
                        try:
                            self.tour(b, w, [VIEWS[i % len(VIEWS)], VIEWS[(i + 1) % len(VIEWS)]])
                        except AssertionError as e:
                            raise AssertionError("seed %d: %s -- %s" % (seed, w.describe(), e)) from e
            finally:
                b.close()


if __name__ == "__main__":
    unittest.main()
