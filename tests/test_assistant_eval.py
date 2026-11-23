"""The test set for the assistant (tests/assistant_eval, a developer's tool): its tasks hold together, and every task's own
answer passes when it goes the whole way through Kontor's assistant -- system text, tools, memory, the steps of an answer -- on
the demo's world, with the stand-in for llama.cpp (tests/fake_llama.py); a wrong answer never passes. What a real model makes
of the tasks is measured on the Mac (tests/assistant_eval/README.md), never here."""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "assistant_eval"))

import assistant as A          # noqa: E402
import grading as G            # noqa: E402
import run as E                # noqa: E402
import test_e2e as T           # noqa: E402


def named_tools(obj) -> set:
    """Every tool a task names: in its grading (the ways through the tools) and in the lookups of its two answers."""
    found = set()
    if isinstance(obj, dict):
        if isinstance(obj.get("name"), (str, list)) and not ({"file", "id"} & set(obj)):
            found |= set(obj["name"] if isinstance(obj["name"], list) else [obj["name"]])
        for v in obj.values():
            found |= named_tools(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= named_tools(v)
    return found


class TaskSet(unittest.TestCase):
    def test_the_tasks_hold_together(self):
        tasks = E.load_tasks()
        ids = [t["id"] for t in tasks]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({t["group"] for t in tasks}, set(E.GROUPS))
        tools = {t["name"] for t in A.TOOLS}
        for t in tasks:
            with self.subTest(task=t["id"]):
                self.assertTrue(t["id"].startswith(t["group"]) and t["title"] and t["prompt"].strip())
                self.assertIn(t["grader"]["type"], G.GRADERS)
                for said in (t["reference"], t["wrong"]):
                    self.assertTrue(str(said.get("answer") or "").strip())
                for d in t.get("docs") or []:
                    self.assertTrue(os.path.isfile(os.path.join(E.HERE, "docs", d["file"])), d["file"])
                for n in t.get("notes") or []:
                    self.assertRegex(n["date"], r"^\d{4}-\d{2}-\d{2}$")
                    self.assertTrue(n["text"].strip())
                # a tool that is renamed or goes must not leave a task behind that no model can pass
                self.assertEqual(named_tools([t["grader"], t["reference"].get("calls"), t["wrong"].get("calls")]) - tools, set())

    def test_grading_alone_tells_right_from_wrong(self):
        """Without the assistant: the reference of every task that needs no figure of the demo's world has all its points,
        its wrong answer does not pass."""
        for t in E.load_tasks():
            if t.get("world"):
                continue
            with self.subTest(task=t["id"]):
                flat = lambda said: [c for step in said.get("calls") or [] for c in step]
                right = G.grade(t, t["reference"]["answer"], flat(t["reference"]))
                self.assertTrue(right["passed"], right)
                self.assertFalse(G.grade(t, t["wrong"]["answer"], flat(t["wrong"]))["passed"])


class ThroughTheAssistant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        T.patch_today()
        ask = lambda *more: E.run(E.parser().parse_args(["run", "--context", "65536", "--quiet", "--limit", "120"] + list(more)), today=T.TODAY)
        cls.right = ask("--stand-in", "reference")
        cls.wrong = ask("--stand-in", "wrong", "--groups", "d,f,k,u")

    def test_every_reference_passes(self):
        res = self.right["results"]
        self.assertEqual(len(res), len(E.load_tasks()))
        self.assertEqual([(r["id"], r["status"], r["error"], r.get("details")) for r in res if not r["passed"]], [])
        self.assertEqual(self.right["summary"]["points"], 100.0)
        self.assertEqual(set(self.right["summary"]["groups"]), set(E.GROUPS))
        meta = self.right["meta"]
        self.assertEqual((meta["stand_in"], meta["context"], meta["effort"], meta["today"]), ("reference", 65536, "balanced", T.TODAY.isoformat()))

    def test_the_lookups_were_made_by_the_assistant(self):
        """What a task's reference looks up reaches Kontor's own tools -- and the figures it expects are Kontor's own."""
        by = {r["id"]: r for r in self.right["results"]}
        self.assertEqual([c["name"] for c in by["u01"]["calls"]], ["get_net_worth_drivers"])
        self.assertEqual(by["u01"]["calls"][0]["arguments"]["area"], "Privat")
        self.assertRegex(by["u01"]["answer"], r"Beteiligung Parkweg GbR um \d{1,3}\.\d{3},\d{2} € sank")
        self.assertNotIn("{", by["u01"]["answer"])                 # every figure of the demo's world was put in
        self.assertTrue(by["u01"]["reads"] >= 1)
        self.assertEqual({c["name"] for c in by["d01"]["calls"]}, {"calculate"})
        self.assertEqual([c["name"] for c in by["k08"]["calls"]][-1:], ["assign_categories"])     # a change: proposed on its card, declined by the run

    def test_no_wrong_answer_passes(self):
        res = self.wrong["results"]
        self.assertEqual([r["id"] for r in res if r["passed"]], [])
        self.assertEqual({r["status"] for r in res}, {"ok"})
        self.assertLess(self.wrong["summary"]["points"], 40.0)

    def test_a_run_ends_when_nothing_answers(self):
        """A model that does not start or hangs: after a few tasks in a row without an answer the rest is not asked -- and said."""
        asked = []

        def no_answer(a, task, effort, limit):
            asked.append(task["id"])
            return {"id": task["id"], "group": task["group"], "title": task["title"], "status": "error", "error": "no answer within 1 s", "answer": "", "calls": [],
                    "score": 0.0, "passed": False, "seconds": 1.0}
        with mock.patch.object(E, "run_task", no_answer):
            out = E.run(E.parser().parse_args(["run", "--stand-in", "reference", "--quiet", "--groups", "d"]), today=T.TODAY)
        self.assertEqual(asked, [t["id"] for t in E.load_tasks(["d"])][:E.ENOUGH])
        self.assertEqual((out["summary"]["tasks"], out["summary"]["of"], out["summary"]["passed"]), (E.ENOUGH, 12, 0))
        self.assertIn("ended early: %d of 12 tasks asked" % E.ENOUGH, E.table(out))
        self.assertNotIn("ended early", E.table(self.right))

    def test_two_runs_side_by_side(self):
        text = E.compare(self.right, self.wrong)
        self.assertIn("lost: d01", text)
        self.assertIn("won: none", text)
        self.assertRegex(E.table(self.right), r"u  Ursachen finden\s+100\.0\s+5/5")


if __name__ == "__main__":
    unittest.main()
