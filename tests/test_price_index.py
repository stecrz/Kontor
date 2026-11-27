"""The balance sheet in today's purchasing power (price_index.py): the consumer price index Kontor ships, the factor of each month
(the index, after its last month the area's inflation of Planung), the balance sheet turned into today's money (sums still add up,
the equity ratio and other currencies untouched), what comes back from the Bundesbank checked before it counts (one series, no gap,
plausible, the same as the shipped one where both are final, a new base year chained on), when Kontor asks at all -- and the
service (only while the page asks, never in the demo, Excel as the page) and the switch in the browser.
The index values are public statistics; every balance here is made up."""
import io
import json
import os
import random
import re
import sys
import threading
import time
import unittest
import zipfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures as F            # noqa: E402
import price_index as P         # noqa: E402

HEAD = ["DATAFLOW", "BBK_STD_FREQ", "TIME_PERIOD", "OBS_VALUE", "BBK_ID", "BBK_UNIT", "BBK_TITLE"]


def rows_of(series, key="BBDP1.M.DE.N.VPI.C.A00000.I20.A", unit="2020=100", head=HEAD):
    """SDMX-CSV rows as the reader hands them back (web_reader, as csv)."""
    out = [["﻿" + head[0]] + head[1:]]
    for m, v in sorted(series.items()):
        out.append(["BBK:BBDP1(1.0)", "M", m, ("%.1f" % v) if isinstance(v, float) else str(v), key, unit, "Verbraucherpreisindex"])
    return out


def last_months(n, upto=P.BUNDLED_LAST):
    return {m: P.BUNDLED[m] for m in sorted(P.BUNDLED) if P.add(upto, -n) < m <= upto}


class Bundled(unittest.TestCase):
    def test_the_index_since_1991_without_a_gap(self):
        self.assertEqual(P.BUNDLED_FIRST, "1991-01"); self.assertEqual(P.BUNDLED_UNIT, "2020=100")
        self.assertTrue(P._plausible(P.BUNDLED))
        self.assertGreaterEqual(P.BUNDLED_LAST, "2026-10")
        # the yearly averages as Destatis publishes them (2020 = 100): a mistyped month would show here
        for year, avg in ((2020, 100.0), (2021, 103.1), (2022, 110.2), (2023, 116.7), (2024, 119.3), (2015, 94.5), (2010, 88.1), (2000, 75.5)):
            got = sum(P.BUNDLED["%d-%02d" % (year, m)] for m in range(1, 13)) / 12
            self.assertAlmostEqual(got, avg, delta=0.051, msg=year)


class Factors(unittest.TestCase):
    S = P.known(None)

    def test_past_months_by_the_index(self):
        f = P.factors(self.S, ["2020-06", "2024-01", P.BUNDLED_LAST], P.BUNDLED_LAST, 2.0)
        self.assertEqual(f["factors"][P.BUNDLED_LAST], 1.0)
        self.assertAlmostEqual(f["factors"]["2020-06"], P.BUNDLED[P.BUNDLED_LAST] / P.BUNDLED["2020-06"], places=9)
        self.assertGreater(f["factors"]["2020-06"], f["factors"]["2024-01"])          # the older, the more it was worth
        self.assertFalse(f["assumed"]); self.assertEqual((f["known_until"], f["first"], f["base"]), (P.BUNDLED_LAST, "1991-01", P.BUNDLED_LAST))

    def test_after_the_index_the_planned_inflation(self):
        base = P.add(P.BUNDLED_LAST, 1)                    # the running month: one month after the last published
        f = P.factors(self.S, [P.BUNDLED_LAST, base, P.add(base, 1), P.add(base, 12)], base, 2.0)["factors"]
        self.assertAlmostEqual(f[P.BUNDLED_LAST], 1.02 ** (1 / 12), places=9)
        self.assertEqual(f[base], 1.0)
        # a plan month: as Planung turns its own figures into today's money (web/app.js, defl) -- the same rate, no jump
        self.assertAlmostEqual(f[P.add(base, 1)], 1.02 ** (-1 / 12), places=9)
        self.assertAlmostEqual(f[P.add(base, 12)], 1 / 1.02, places=9)
        flat = P.factors(self.S, [P.add(base, 24)], base, 0.0)["factors"]
        self.assertEqual(flat[P.add(base, 24)], 1.0)
        self.assertGreater(P.factors(self.S, [P.add(base, 12)], base, -1.0)["factors"][P.add(base, 12)], 1.0)    # deflation: the plan is worth more

    def test_before_1991_unknown_never_guessed(self):
        f = P.factors(self.S, ["1990-12", "1991-01"], "2026-11", 2.0)["factors"]
        self.assertIsNone(f["1990-12"]); self.assertIsNotNone(f["1991-01"])

    def test_the_rate_of_the_plan(self):
        self.assertEqual(P.rate_of({}), 2.0); self.assertEqual(P.rate_of({"inflation_percent_pa": 3.5}), 3.5)
        self.assertEqual(P.rate_of({"inflation_percent_pa": 0}), 0.0); self.assertEqual(P.rate_of({"inflation_percent_pa": "x"}), 2.0)
        self.assertEqual(P.rate_of({"inflation_percent_pa": 1e9}), 100.0); self.assertEqual(P.rate_of({"inflation_percent_pa": float("nan")}), 2.0)

    def test_months_asked_for(self):
        self.assertEqual(P.span("2025-11", "2026-02"), ["2025-11", "2025-12", "2026-01", "2026-02"])
        for a, b in (("2026-02", "2025-11"), ("2026-13", "2027-01"), ("x", "2026-01"), ("1900-01", "2026-01")):
            with self.assertRaises(ValueError):
                P.span(a, b)
        today = date(2026, 11, 4)
        self.assertEqual(P.base_month("2026-10", today), "2026-10")             # data from the month before: its running month
        self.assertEqual(P.base_month("2020-01", today), "2026-11"); self.assertEqual(P.base_month("", today), "2026-11")


def balance(months, plan, rng):
    """A made-up balance sheet in the shape of report.build_dataset / apply_plan: positions with their accounts (one a
    portfolio with securities), net worth = the sum of the positions, the plan, the equity ratio, a foreign currency account."""
    roles = ["cash", "securities", "real_estate", "liabilities"]
    rows, nw, proj, pnw = [], {}, [], {}
    for role in roles:
        accs = []
        for k in range(rng.randint(1, 3)):
            am = {m: round(rng.uniform(-5e5, 5e5), 2) for m in months if rng.random() > 0.05}
            acc = {"id": "%s%d" % (role, k), "group": False, "role": role, "name": "Konto %d" % k, "amounts": am}
            if role == "securities":
                acc["securities"] = [{"id": "w%d" % k, "name": "Fonds", "amounts": dict(am)}]
            accs.append(acc)
        g = {m: round(sum(a["amounts"].get(m) or 0 for a in accs), 2) for m in months}
        rows.append({"id": role, "group": True, "role": role, "name": role, "amounts": g})
        rows += accs
        gp = {m: round(rng.uniform(-5e5, 5e5), 2) for m in plan}
        proj.append({"id": role, "amounts": gp})
        for m in months:
            nw[m] = round(nw.get(m, 0) + g[m], 2)
        for m in plan:
            pnw[m] = round(pnw.get(m, 0) + gp[m], 2)
    return {"rows": rows, "net_worth": nw, "liquid_net_worth": dict(nw), "positions": {r: r for r in roles},
            "projection": {"rows": proj, "net_worth": pnw, "cash": {m: 1.0 for m in plan}},
            "equity_ratio": {"months": {m: {"quote": 0.4, "equity_value": 100.0} for m in months}},
            "outside": [{"id": "fx", "role": "foreign_currency", "currency": "USD", "amounts": {m: 50.0 for m in months}},
                        {"id": "av", "role": "contingent", "amounts": {m: -1000.0 for m in months}}]}


class Deflate(unittest.TestCase):
    def test_every_amount_by_month_and_the_sums_still_add_up(self):
        """Random balance sheets (fixed and new cases): each amount times its month's factor; net worth stays the sum of the
        positions, a position the sum of its accounts (exactly, before each cell is rounded to the cent); the base month
        unchanged; the input untouched; equity ratio and the other currency as they were."""
        for seed in F.fuzz_seeds("Kaufkraft"):
            rng = random.Random(seed)
            start = P.add("1992-01", rng.randint(0, 400))
            months = P.span(start, P.add(start, rng.randint(1, 30)))
            plan = P.span(P.add(months[-1], 1), P.add(months[-1], rng.randint(1, 36)))
            b = balance(months, plan, rng)
            before = json.dumps(b, sort_keys=True)
            f = P.factors(P.known(None), months + plan, months[-1], rng.uniform(-2, 8))["factors"]
            r = P.deflate(b, f)
            self.assertEqual(json.dumps(b, sort_keys=True), before, "seed %s" % seed)
            for m in months:
                groups = [x for x in r["rows"] if x["group"]]
                self.assertAlmostEqual(r["net_worth"][m], sum(g["amounts"][m] for g in groups), delta=1e-6, msg="seed %s %s" % (seed, m))
                for g in groups:
                    accs = [a for a in r["rows"] if not a["group"] and a["role"] == g["role"]]
                    self.assertAlmostEqual(g["amounts"][m], sum(a["amounts"].get(m) or 0 for a in accs), delta=1e-6, msg="seed %s" % seed)
                    # rounded to the cent cell by cell: a sum differs from its rows by half a cent per row at most
                    self.assertLessEqual(abs(round(g["amounts"][m], 2) - sum(round(a["amounts"].get(m) or 0, 2) for a in accs)), 0.005 * len(accs) + 1e-9)
            for m in plan:
                self.assertAlmostEqual(r["projection"]["net_worth"][m], sum(x["amounts"][m] for x in r["projection"]["rows"]), delta=1e-6)
            last = months[-1]
            self.assertEqual(r["net_worth"][last], b["net_worth"][last])
            sec = next(x for x in r["rows"] if x.get("securities"))
            self.assertAlmostEqual(sec["securities"][0]["amounts"].get(last, 0) or 0, sec["amounts"].get(last, 0) or 0, delta=1e-9)
            self.assertEqual(r["equity_ratio"], b["equity_ratio"]); self.assertEqual(r["outside"][0], b["outside"][0])
            self.assertAlmostEqual(r["outside"][1]["amounts"][months[0]], -1000.0 * f[months[0]], delta=1e-9)
            self.assertEqual(r["positions"], b["positions"])

    def test_a_month_without_a_factor_is_unknown(self):
        r = P.deflate({"net_worth": {"1990-12": 100.0, "1991-01": 100.0, "1991-02": None}, "name": "x", "empty": {}},
                      P.factors(P.known(None), ["1990-12", "1991-01", "1991-02"], "1991-01", 2.0)["factors"])
        self.assertEqual(r["net_worth"], {"1990-12": None, "1991-01": 100.0, "1991-02": None})
        self.assertEqual((r["name"], r["empty"]), ("x", {}))
        self.assertEqual(P.deflate({"net_worth": {"2026-01": 5.0}}, {})["net_worth"], {"2026-01": None})     # not asked for: never the nominal one


class Fetched(unittest.TestCase):
    TODAY = date(2026, 12, 20)

    def test_the_request_is_fixed(self):
        req = P.request()
        self.assertEqual(req["url"], "https://api.statistiken.bundesbank.de/rest/data/BBDP1/M.DE.N.VPI.C.A00000..A?format=sdmx_csv&startPeriod="
                         + P.add(P.BUNDLED_LAST, -24))
        self.assertEqual((req["hosts"], req["method"], req["as"], req["headers"]), (["api.statistiken.bundesbank.de"], "GET", "csv", {}))
        self.assertNotIn("Kontor", req["user_agent"])

    def test_parse_takes_the_newest_plausible_series(self):
        s = last_months(24); s[P.add(P.BUNDLED_LAST, 1)] = s[P.BUNDLED_LAST] + 0.3
        key, unit, got = P.parse(rows_of(s), self.TODAY)
        self.assertEqual((key, unit, got), ("BBDP1.M.DE.N.VPI.C.A00000.I20.A", "2020=100", s))
        # another series, a base year that does not fit the unit, a month in the future, a broken value: left out
        rows = rows_of(s) + rows_of({"2026-11": 50.0}, key="BBDP1.M.DE.N.HVPI.C.A00000.I20.A")[1:] + rows_of({"2026-11": 50.0}, unit="2015=100")[1:] \
            + rows_of({"2027-01": 130.0})[1:] + [["x", "M", "2026-11", "n/a", "BBDP1.M.DE.N.VPI.C.A00000.I20.A", "2020=100", ""], ["short"]]
        self.assertEqual(P.parse(rows, self.TODAY)[2], s)
        # a new base year with later months wins (chained on in merge)
        new = {m: round(v * 100 / 121.9, 1) for m, v in s.items()}; new[P.add(P.BUNDLED_LAST, 2)] = new[P.add(P.BUNDLED_LAST, 1)]
        self.assertEqual(P.parse(rows_of(s) + rows_of(new, key="BBDP1.M.DE.N.VPI.C.A00000.I25.A", unit="2025=100")[1:], self.TODAY)[:2],
                         ("BBDP1.M.DE.N.VPI.C.A00000.I25.A", "2025=100"))

    def test_parse_refuses(self):
        s = last_months(24)
        gap = dict(s); gap.pop(sorted(gap)[5])
        jump = dict(s); jump[sorted(jump)[5]] = s[sorted(s)[5]] * 1.2
        low = {m: 5.0 for m in s}
        for rows in (rows_of(gap), rows_of(jump), rows_of(low), [HEAD], [], "text", [["TIME_PERIOD", "OBS_VALUE"], ["2026-01", "1"]]):
            with self.assertRaises(ValueError):
                P.parse(rows, self.TODAY)

    def test_merge_same_base(self):
        s = last_months(24); nxt = P.add(P.BUNDLED_LAST, 1); s[nxt] = s[P.BUNDLED_LAST] + 0.2
        got = P.merge(None, "2020=100", s)
        self.assertEqual(got, {m: round(v, 4) for m, v in s.items()})
        # the last two months Kontor knew may have been estimates: corrected
        est = dict(s); est[P.BUNDLED_LAST] += 0.5
        self.assertEqual(P.merge(None, "2020=100", est)[P.BUNDLED_LAST], round(est[P.BUNDLED_LAST], 4))
        # a final month that differs: refused
        bad = dict(s); bad[sorted(bad)[3]] += 1.0
        with self.assertRaises(ValueError):
            P.merge(None, "2020=100", bad)
        with self.assertRaises(ValueError):                      # too little to compare with
            P.merge(None, "2020=100", {nxt: 130.0, P.BUNDLED_LAST: P.BUNDLED[P.BUNDLED_LAST]})

    def test_merge_a_new_base_year_is_chained_on(self):
        s = last_months(24); nxt = P.add(P.BUNDLED_LAST, 1)
        new = {m: round(v * 100 / 121.92, 1) for m, v in s.items()}; new[nxt] = round(new[P.BUNDLED_LAST] * 1.004, 1)
        got = P.merge(None, "2025=100", new)
        for m in s:
            self.assertAlmostEqual(got[m], s[m], delta=0.1, msg=m)
        self.assertAlmostEqual(got[nxt] / got[P.BUNDLED_LAST], new[nxt] / new[P.BUNDLED_LAST], places=6)       # what counts: the ratio
        # as Destatis rebases: new weights from the base year on -- the new series rises a little slower (1 point a year less)
        ms = sorted(s); revised = {m: round(s[m] * 100 / 121.92 * (1 - 0.01 * i / 12), 2) for i, m in enumerate(ms)}
        got = P.merge(None, "2025=100", revised)
        self.assertAlmostEqual(got[ms[0]], s[ms[0]], delta=0.1)                                # joined at the first common months
        self.assertAlmostEqual(got[ms[-1]] / got[ms[0]], revised[ms[-1]] / revised[ms[0]], places=4)       # the new series counts
        other = dict(new); other[sorted(other)[-3]] *= 1.05                                    # 5 % off: not the index
        with self.assertRaises(ValueError):
            P.merge(None, "2025=100", other)

    def test_a_series_that_does_not_fit_gives_way_to_the_next(self):
        """The newest series is refused (here a new base year far off what Kontor knows): the old one, still going on, counts."""
        s = last_months(24); nxt = P.add(P.BUNDLED_LAST, 1); s[nxt] = s[P.BUNDLED_LAST] + 0.1
        bad = {m: round(100 * 1.005 ** i, 1) for i, m in enumerate(sorted(s))}          # rising twice as fast: 6 % off after two years
        rows = rows_of(s) + rows_of(bad, key="BBDP1.M.DE.N.VPI.C.A00000.I25.A", unit="2025=100")[1:]
        self.assertEqual(P.candidates(rows, date(2026, 12, 20))[0][1], "2025=100")
        st = P.refresh(lambda req: {"ok": True, "data": rows}, None, date(2026, 12, 20), 5.0)
        self.assertEqual((st["error"], st["series"], max(P.known(st))), ("", "BBDP1.M.DE.N.VPI.C.A00000.I20.A", nxt))
        self.assertTrue(P.counts(st)); self.assertFalse(P.counts(None)); self.assertFalse(P.counts(dict(st, unit="2025=100")))

    def test_refresh_keeps_what_was_known_when_anything_fails(self):
        s = last_months(24); nxt = P.add(P.BUNDLED_LAST, 1); s[nxt] = s[P.BUNDLED_LAST] + 0.1
        asked = []
        st = P.refresh(lambda req: asked.append(req) or {"ok": True, "data": rows_of(s)}, None, self.TODAY, 1000.0)
        self.assertEqual(asked, [P.request()])
        self.assertEqual((st["error"], st["unit"], st["fetched"], st["tried"], st["fetched_at"]), ("", "2020=100", "2026-12-20", 1000.0, 1000.0))
        self.assertEqual(max(P.known(st)), nxt)
        for answer in ({"ok": False, "error": "timeout"}, {"ok": True, "data": "x"}, None, {"ok": True, "data": rows_of({nxt: 500.0})}):
            st2 = P.refresh(lambda req: answer, st, self.TODAY, 2000.0)
            self.assertTrue(st2["error"]); self.assertEqual(st2["tried"], 2000.0); self.assertEqual(P.known(st2), P.known(st))

        def boom(req):
            raise OSError("no network")
        self.assertIn("no network", P.refresh(boom, None, self.TODAY, 1.0)["error"])

    def test_known_takes_only_what_fits(self):
        nxt = P.add(P.BUNDLED_LAST, 1)
        good = {"unit": "2020=100", "values": {P.BUNDLED_LAST: P.BUNDLED[P.BUNDLED_LAST], nxt: P.BUNDLED[P.BUNDLED_LAST] + 0.4}}
        self.assertEqual(max(P.known(good)), nxt)
        for st in ({"unit": "2025=100", "values": good["values"]},                 # kept in another base (a new version ships another)
                   {"unit": "2020=100", "values": {P.add(nxt, 2): 130.0}},          # a gap to the shipped months
                   {"unit": "2020=100", "values": {nxt: 300.0}},                    # a jump
                   {"unit": "2020=100", "values": {nxt: "130"}}, {"unit": "2020=100", "values": []}, "x", None,
                   {"unit": "2020=100", "values": {"1990-12": 60.0, "1991-01": 60.5}}):
            self.assertEqual(P.known(st), P.BUNDLED, st)

    def test_when_kontor_asks(self):
        now = 10 ** 9
        last = P.BUNDLED_LAST
        stale = date(int(P.add(last, 2)[:4]), int(P.add(last, 2)[5:]), 3)        # a newer month may be out
        self.assertTrue(P.due(None, stale, now))
        self.assertFalse(P.due({"tried": now - 3600}, stale, now))              # not twice a day
        self.assertTrue(P.due({"tried": now - 21 * 3600}, stale, now))
        fresh = date(int(P.add(last, 1)[:4]), int(P.add(last, 1)[5:]), 20)      # Kontor knows last month: every two weeks only
        self.assertFalse(P.due({"tried": now - 2 * 86400, "fetched_at": now - 2 * 86400}, fresh, now))
        self.assertTrue(P.due({"tried": now - 15 * 86400, "fetched_at": now - 15 * 86400}, fresh, now))
        self.assertTrue(P.due({"tried": now + 365 * 86400}, stale, now))       # a clock that ran a year ahead once: no block
        self.assertTrue(P.due({"tried": now - 15 * 86400, "fetched_at": now + 86400}, fresh, now))


# -- the service: the factors for the page, a fetch only when the page asks, never in the demo, Excel as the page ---------------
import test_e2e as T            # noqa: E402


class Service(T._AppBase):
    def test_factors_fetch_and_excel(self):
        self.login(); self.run_and_wait()
        code, ds = self.call("/api/dataset")
        area = ds["main_area"]; b = ds["areas"][area]
        months, base = b["months"] + b["plan_months"], b["actual_until"]
        asked = []
        nxt = P.add(P.BUNDLED_LAST, 1)
        answer = last_months(24); answer[nxt] = answer[P.BUNDLED_LAST] + 0.2
        self.app.price_reader = lambda req: asked.append(req) or {"ok": True, "data": rows_of(answer)}
        code, r = self.call("/api/price_index?area=%s&from=%s&to=%s&base=%s" % (area, months[0], months[-1], base))
        self.assertEqual(code, 200, r)
        self.assertEqual(sorted(r["factors"]), months); self.assertEqual(r["base"], base); self.assertEqual(r["factors"][base], 1.0)
        self.assertEqual(r["rate"], P.rate_of(self.app.plan_for(area)))
        for _ in range(100):                                  # the fetch runs in the background, once
            if self.app.price_state().get("fetched"):
                break
            time.sleep(0.05)
        self.assertEqual(len(asked), 1); self.assertEqual(asked[0], P.request())
        self.assertEqual(max(P.known(self.app.price_state())), nxt)
        code, r2 = self.call("/api/price_index?area=%s&from=%s&to=%s&base=%s" % (area, months[0], months[-1], base))
        self.assertEqual(r2["known_until"], nxt); self.assertTrue(r2["fetched"])
        self.assertEqual(len(asked), 1)                       # not again the same day
        # the plan's inflation counts after the index
        plan = self.app.plan_all(); plan["areas"][area] = dict(self.app.plan_for(area), inflation_percent_pa=4.0)
        self.app.store.save("plan.json", plan)
        code, r3 = self.call("/api/price_index?area=%s&from=%s&to=%s&base=%s" % (area, months[0], months[-1], base))
        self.assertEqual(r3["rate"], 4.0)
        self.assertAlmostEqual(r3["factors"][months[-1]], 1.04 ** (-(P._key(months[-1]) - P._key(base)) / 12), places=8)
        for bad in ("from=2026-13&to=2027-01", "from=2027-01&to=2026-01", "to=2026-01"):
            self.assertEqual(self.call("/api/price_index?area=%s&%s" % (area, bad))[0], 400)
        # Excel: the balance sheet as the page shows it with the switch on -- each amount times its factor, a line says which money
        code, data, hdr = self.call("/api/export/balance.xlsx?mode=months&real=1&area=" + area, raw=True)
        code, data0, hdr = self.call("/api/export/balance.xlsx?mode=months&area=" + area, raw=True)
        x, x0 = (zipfile.ZipFile(io.BytesIO(d)).read("xl/worksheets/sheet1.xml").decode() for d in (data, data0))
        self.assertIn("In Kaufkraft von %s" % base, x); self.assertNotIn("In Kaufkraft", x0)
        import service as MS
        sh = MS.export_sheets(self.app, "balance", area, "months", {"real": True})[0]
        sh0 = MS.export_sheets(self.app, "balance", area, "months", {})[0]
        f = self.call("/api/price_index?area=%s&from=%s&to=%s&base=%s" % (area, months[0], months[-1], base))[1]["factors"]
        nw, nw0 = (next(r for r in s.rows if r and r[0] == "Nettovermögen") for s in (sh, sh0))
        for i, m in enumerate(sh.header[1:], 1):
            m = m.replace(" (Plan)", "")
            if nw0[i] is not None:
                self.assertAlmostEqual(nw[i], nw0[i] * f[m], delta=1e-6, msg=m)

    def test_never_fetched_in_the_demo_nor_when_signed_out(self):
        import service as MS
        self.assertIn("/api/price_index", MS.DEMO_GET)
        self.login()
        asked = []
        self.app.price_reader = lambda req: asked.append(req) or {"ok": False}
        self.app.DEMO = True
        try:
            self.app.price_refresh_soon()
        finally:
            del self.app.DEMO
        self.app.store.save("state.json", dict(self.app.store.load("state.json", {}), price_index={"tried": time.time()}))
        self.app.price_refresh_soon()                          # tried a moment ago: not again
        time.sleep(0.2)
        self.assertEqual(asked, [])
        # signed out (the data key dropped): nothing is read, nothing asked
        self.app.store.save("state.json", dict(self.app.store.load("state.json", {}), price_index={}))
        master, self.app.store.master = self.app.store.master, None
        try:
            if self.app.store.encrypted:
                self.app.price_refresh_soon(); time.sleep(0.2)
                self.assertEqual(asked, [])
        finally:
            self.app.store.master = master
        # signed out while the answer is on its way: what came back is dropped, nothing breaks, the next look tries again

        def slow(req):
            asked.append(req); self.app.store.master = None
            return {"ok": True, "data": rows_of(last_months(24))}
        self.app.price_reader = slow
        self.app._price_refresh()
        self.app.store.master = master
        self.assertEqual(len(asked), 1); self.assertFalse(self.app._price_busy)
        self.assertEqual(self.app.price_state(), {})


class Browser(unittest.TestCase):
    """The switch on the balance sheet: the table and the charts in today's money (each cell = the real amount × its factor),
    the tag names the month, Excel follows; off again: the real amounts. Other pages stay real."""

    def test_switch(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright fehlt")
        import tempfile
        from http.server import ThreadingHTTPServer
        from service import App, make_handler
        d = tempfile.mkdtemp(prefix="kontor-pix-")
        store = F.new_store(d)
        store.save("config.json", T.config_for_test(os.path.join(d, "Belege"))); store.save("state.json", dict(T.ALL_NEW))
        T.reset_mock(); T.patch_today()
        app = App(store, d, bridge_factory=T.MockBridge)
        app.price_reader = lambda req: {"ok": False, "error": "network"}        # nothing goes out in the test
        app.do_run(False, True)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(); errors = []
                pg = b.new_page(viewport={"width": 1440, "height": 900}); pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.goto("http://127.0.0.1:%d/" % port)
                pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.fill("#login-pw2", "sehr-geheimes-passwort"); pg.click("#login-btn")
                T.wait_shell(pg)
                pg.evaluate("location.hash = '#balance'"); pg.wait_for_selector("tr.pos")
                key = pg.evaluate("[...document.querySelectorAll('.bil-tbl thead th[data-key]')].map(t => t.dataset.key)")
                col = next(i for i, k in enumerate(key) if k < T.TODAY.strftime("%Y-%m"))          # a closed month in view
                sel = "tr.total td:nth-child(%d)" % (col + 2)
                before, m = pg.inner_text(sel), key[col]
                nominal = pg.evaluate("B().balance.net_worth['%s']" % m)
                self.assertIsNone(pg.query_selector(".tb-real .pill"))
                pg.click("label.switch:has(#kaufkraft-an)")
                T.until(pg, "!!document.querySelector('.tb-real .pill.info')")
                f = pg.evaluate("S.PIX.data.factors['%s']" % m)
                self.assertGreater(f, 1.0)
                after = pg.inner_text(sel)
                shown = float(re.sub(r"[^\d,-]", "", after).replace(",", "."))
                self.assertAlmostEqual(shown, round(nominal * f, 2), delta=0.006, msg=(before, after))
                self.assertIn("in Kaufkraft von", pg.inner_text(".tb-real .pill")); self.assertIn("Nov 2026", pg.inner_text(".tb-real .pill"))
                self.assertIn("Verbraucherpreisindex", pg.get_attribute(".tb-real .pill", "title"))
                # the charts read the same: the net worth chart's value at its last closed month
                self.assertAlmostEqual(pg.evaluate("BCH.d.nw[BCH.d.months.indexOf('%s')]" % m), nominal * f, delta=1e-6)
                # other pages and drawers: the real amounts
                self.assertEqual(pg.evaluate("B().balance.net_worth['%s']" % m), nominal)
                # the years view: each year's year-end balance in today's money too
                pg.click("#modus-seg button[data-m='years']")
                T.until(pg, "S.mode === 'years' && !!document.querySelector('.bil-tbl thead th[data-key=\"2025\"]')")
                y = pg.evaluate("[...document.querySelectorAll('.bil-tbl thead th[data-key]')].map(t => t.dataset.key).indexOf('2025')")
                shown = float(re.sub(r"[^\d,-]", "", pg.inner_text("tr.total td:nth-child(%d)" % (y + 2))).replace(",", "."))
                self.assertAlmostEqual(shown, round(pg.evaluate("B().balance.net_worth['2025-12'] * S.PIX.data.factors['2025-12']"), 2), delta=0.006)
                pg.evaluate("S.mode = 'months'; route()"); pg.wait_for_selector(sel)
                # off again: the real figures
                pg.click("label.switch:has(#kaufkraft-an)")
                T.until(pg, "!document.querySelector('.tb-real .pill')")
                self.assertEqual(pg.inner_text(sel), before)
                # the factors cannot be had: said in yellow, the figures stay the real ones
                pg.route("**/api/price_index*", lambda r: r.fulfill(status=500, content_type="application/json", body='{"error": "kaputt"}'))
                pg.evaluate("S.PIX = null")
                pg.click("label.switch:has(#kaufkraft-an)")
                T.until(pg, "!!document.querySelector('.tb-real .pill.warn')")
                self.assertIn("nicht verfügbar", pg.inner_text(".tb-real .pill.warn")); self.assertEqual(pg.inner_text(sel), before)
                self.assertEqual(errors, [])
                b.close()
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
