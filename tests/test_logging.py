"""The log stays small and readable (made-up data only): one file that keeps its newest part, no line for every quick check of
MoneyMoney or every page request, a locked MoneyMoney noted once and not as a warning, no paths or query strings."""
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import kontor      # noqa: E402
import mm_bridge   # noqa: E402


class OneFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-log-")
        self.path = os.path.join(self.dir, "kontor.log")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_keeps_one_file_with_its_newest_lines(self):
        h = kontor.OneFileHandler(self.path, maxBytes=20_000, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(message)s"))
        lg = logging.getLogger("kontor.test.onefile"); lg.propagate = False; lg.addHandler(h); lg.setLevel(logging.DEBUG)
        try:
            for i in range(3000):
                lg.info("line %05d %s", i, "x" * 40)
        finally:
            lg.removeHandler(h); h.close()
        self.assertEqual(sorted(os.listdir(self.dir)), ["kontor.log"])                 # no numbered copies
        self.assertLessEqual(os.path.getsize(self.path), 20_000)
        with open(self.path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertTrue(lines[-1].startswith("line 02999"))                             # the newest stays
        self.assertTrue(all(l.startswith("line ") for l in lines))                      # cut at the start of a line


class QuietBridge(unittest.TestCase):
    LOCKED = mm_bridge.JXA_FILE + ": execution error: Error: Error: Locked database. (-2720)"

    def run_call(self, quiet, rc=1, err=None):
        b = mm_bridge.Bridge(True); b.quiet = quiet
        done = subprocess.CompletedProcess([], rc, stdout="" if rc else "<plist/>", stderr=err if err is not None else self.LOCKED)
        with mock.patch.object(mm_bridge, "is_running", return_value=True), mock.patch.object(mm_bridge.subprocess, "run", return_value=done), \
                self.assertLogs("kontor", level="DEBUG") as cm:
            logging.getLogger("kontor").debug("start")
            self.exc = None
            try:
                b._call("exportAccounts", None)
            except mm_bridge.MoneyMoneyError as e:
                self.exc = e
        return cm

    def test_quick_check_while_locked_writes_nothing(self):
        cm = self.run_call(True)
        self.assertEqual([r.getMessage() for r in cm.records], ["start"])
        self.assertIsInstance(self.exc, mm_bridge.MoneyMoneyLocked)

    def test_quick_check_that_works_writes_nothing(self):
        cm = self.run_call(True, rc=0)
        self.assertEqual([r.getMessage() for r in cm.records], ["start"])

    def test_locked_in_a_run_is_a_note_without_the_path(self):
        cm = self.run_call(False)
        locked = [r for r in cm.records if "Locked" in r.getMessage()]
        self.assertEqual([r.levelname for r in locked], ["INFO"])
        self.assertNotIn(mm_bridge.JXA_FILE, locked[0].getMessage())

    def test_a_real_failure_stays_a_warning(self):
        cm = self.run_call(True, err="execution error: something else (-1)")
        self.assertIn("WARNING", [r.levelname for r in cm.records])


if __name__ == "__main__":
    unittest.main()
