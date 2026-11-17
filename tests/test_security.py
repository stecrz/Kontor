"""Security regressions (all with made-up data, never the real keychain): the idle lock with the page open, a keychain that
does not answer in time, and links in the receipts folder that point elsewhere."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import auth      # noqa: E402
import storage   # noqa: E402
from receipts import Belege   # noqa: E402


class IdleLock(unittest.TestCase):
    """A request the page makes on its own (status every 30 s) checks the session without counting as activity."""

    def setUp(self):
        self.now = [1000.0]
        self._time = auth.time.time
        auth.time.time = lambda: self.now[0]

    def tearDown(self):
        auth.time.time = self._time

    def test_background_requests_do_not_keep_it_open(self):
        s = auth.Sessions(idle_minutes=15, max_hours=12)
        a, b = s.create("127.0.0.1", "passwort"), s.create("100.64.0.2", "passwort")
        for _ in range(29):                              # 14.5 minutes of status polls, nobody touches the page
            self.now[0] += 30
            self.assertIsNotNone(s.get(a["token"], touch=False))
        self.assertIsNotNone(s.get(b["token"]))          # another device in use: its own session
        self.now[0] += 60
        self.assertIsNone(s.get(a["token"], touch=False))     # 15.5 minutes without activity: locked
        self.assertIsNotNone(s.get(b["token"]))               # the other one stays

    def test_activity_keeps_it_open_but_not_beyond_the_limit(self):
        s = auth.Sessions(idle_minutes=15, max_hours=12)
        a = s.create("127.0.0.1", "passwort")
        for _ in range(12 * 6 - 1):                      # someone at work: a click every 10 minutes for almost 12 hours
            self.now[0] += 600
            self.assertIsNotNone(s.get(a["token"]))
        self.now[0] += 1200
        self.assertIsNone(s.get(a["token"]))             # the absolute limit holds


class KeychainTimeout(unittest.TestCase):
    """macOS keychain locked or a prompt waiting: never a new key file next to the data; a key file that opens the data
    already there is used, nothing is replaced or removed."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-key-")
        self._sec = storage._security

    def tearDown(self):
        storage._security = self._sec
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_timeout_is_not_no_keychain(self):
        run = subprocess.run
        try:
            def slow(*a, **k):
                raise subprocess.TimeoutExpired("security", 30)
            subprocess.run = slow
            self.assertEqual(storage._security(["find-generic-password"])[0], 124)
            def missing(*a, **k):
                raise FileNotFoundError("security")
            subprocess.run = missing
            self.assertEqual(storage._security(["find-generic-password"])[0], 127)
        finally:
            subprocess.run = run

    def test_timeout_end_to_end_creates_no_key(self):
        run = subprocess.run
        try:
            def slow(*a, **k):
                raise subprocess.TimeoutExpired("security", 30)
            subprocess.run = slow
            with self.assertRaises(storage.StoreError):
                storage.load_or_create_master_key(self.dir)
        finally:
            subprocess.run = run
        self.assertFalse(os.path.exists(os.path.join(self.dir, "master.key")))

    def test_first_start_stops_without_a_key_file(self):
        storage._security = lambda args, input_text=None: (124, "", "timeout")
        with self.assertRaises(storage.StoreError):
            storage.load_or_create_master_key(self.dir)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "master.key")))

    def test_key_file_that_opens_the_data_is_used(self):
        key = os.urandom(32)
        with open(os.path.join(self.dir, "master.key"), "w") as f:
            f.write(key.hex())
        with open(os.path.join(self.dir, "config.json.enc"), "wb") as f:
            f.write(storage.encrypt(key, b"{}"))
        storage._security = lambda args, input_text=None: (124, "", "timeout")
        self.assertEqual(storage.load_or_create_master_key(self.dir), (key, "datei"))

    def test_key_file_that_does_not_open_the_data_stays_untouched(self):
        with open(os.path.join(self.dir, "master.key"), "w") as f:
            f.write(os.urandom(32).hex())
        with open(os.path.join(self.dir, "config.json.enc"), "wb") as f:
            f.write(storage.encrypt(os.urandom(32), b"{}"))      # the data belong to another key (in the keychain)
        before = open(os.path.join(self.dir, "master.key")).read()
        storage._security = lambda args, input_text=None: (124, "", "timeout")
        with self.assertRaises(storage.StoreError):
            storage.load_or_create_master_key(self.dir)
        self.assertEqual(open(os.path.join(self.dir, "master.key")).read(), before)

    def test_without_security_the_file_key_stays_as_before(self):
        storage._security = lambda args, input_text=None: (127, "", "no security")     # not macOS
        key, src = storage.load_or_create_master_key(self.dir)
        self.assertEqual((src, len(key)), ("datei", 32))
        self.assertEqual(storage.load_or_create_master_key(self.dir), (key, "datei"))

    def test_only_no_entry_allows_a_new_key(self):
        """Access refused, locked or an entry with unexpected content: no new key, nothing written into the keychain."""
        for answer in ((51, "", "denied"), (36, "", "locked"), (0, "kaputt\n", ""), (0, "z" * 64 + "\n", "")):
            calls = []

            def fake(args, input_text=None, answer=answer):
                calls.append(args[0])
                return answer if args[0] == "find-generic-password" else (0, "", "")
            storage._security = fake
            with self.assertRaises(storage.StoreError):
                storage.load_or_create_master_key(self.dir)
            self.assertNotIn("add-generic-password", calls, answer)
            self.assertFalse(os.path.exists(os.path.join(self.dir, "master.key")))

    def test_refused_keychain_with_key_file_that_opens_the_data(self):
        key = os.urandom(32)
        with open(os.path.join(self.dir, "master.key"), "w") as f:
            f.write(key.hex())
        with open(os.path.join(self.dir, "config.json.enc"), "wb") as f:
            f.write(storage.encrypt(key, b"{}"))
        calls = []

        def fake(args, input_text=None):
            calls.append(args[0])
            return (51, "", "denied") if args[0] == "find-generic-password" else (0, "", "")
        storage._security = fake
        self.assertEqual(storage.load_or_create_master_key(self.dir), (key, "datei"))
        self.assertNotIn("add-generic-password", calls)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "master.key")))      # the file stays until the keychain answers


class _Store:
    def __init__(self, d):
        self.data_dir, self._d = d, {}

    def load(self, name, default=None):
        return self._d.get(name, default)

    def save(self, name, obj):
        self._d[name] = obj


class ReceiptLinks(unittest.TestCase):
    """A file counts as in the receipts folder only where it really is: a link in it to a file elsewhere is neither linked
    nor listed; links within the folder and a folder that is itself a link keep working."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="kontor-bl-")
        self.real = os.path.join(self.base, "iCloud-Belege")
        os.makedirs(os.path.join(self.real, "2026"))
        self.folder = os.path.join(self.base, "Belege")
        os.symlink(self.real, self.folder)                        # the receipts folder itself a link (e.g. into iCloud Drive)
        with open(os.path.join(self.real, "2026", "Rechnung.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 innen")
        os.symlink(os.path.join(self.real, "2026", "Rechnung.pdf"), os.path.join(self.real, "Kopie.pdf"))     # a link within
        self.secret = os.path.join(self.base, "geheim.pdf")
        with open(self.secret, "wb") as f:
            f.write(b"%PDF-1.4 geheim")
        os.symlink(self.secret, os.path.join(self.real, "2026", "Fremd.pdf"))       # a link to a file elsewhere
        data = os.path.join(self.base, "daten"); os.makedirs(data)
        self.bl = Belege(_Store(data), {"belege": {"ordner": self.folder}})

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_links(self):
        self.assertTrue(self.bl.link_existing(None, "2026/Rechnung.pdf"))
        self.assertTrue(self.bl.link_existing(None, "Kopie.pdf"))                     # within the folder: fine
        with self.assertRaises(ValueError):
            self.bl.link_existing(None, "2026/Fremd.pdf")                            # elsewhere: refused
        with self.assertRaises(ValueError):
            self.bl.link_existing(None, "../geheim.pdf")
        listed = {x["pfad"] for x in self.bl.listing()}
        self.assertIn("2026/Rechnung.pdf", listed); self.assertIn("Kopie.pdf", listed); self.assertNotIn("2026/Fremd.pdf", listed)
        self.assertFalse(self.bl.inside(os.path.join(self.folder, "2026", "Fremd.pdf")))

    def _legacy(self, pfad):
        """An entry as an earlier version could have made it (before links were checked)."""
        e = {"id": "alt%03d" % len(self.bl.entries()), "tx_id": None, "datum": "2026-03-01", "pfad": pfad, "name": "Alt"}
        self.bl.entries().append(e)
        return e

    def test_export_holds_nothing_from_elsewhere(self):
        import zipfile
        self._legacy("2026/Fremd.pdf")
        self.bl.link_existing(None, "2026/Rechnung.pdf")
        with zipfile.ZipFile(self.bl.export_zip(None, None, {})) as z:
            content = b"".join(z.read(n) for n in z.namelist())
        self.assertIn(b"innen", content); self.assertNotIn(b"geheim", content)
        self.assertIsNone(self.bl.servable(self.bl.entries()[0]))
        self.assertIn("2026/Fremd.pdf", self.bl.check())                    # shown as missing, as it is not handed out

    def test_delete_never_reaches_outside(self):
        other = os.path.join(self.base, "Andere", "Sub"); os.makedirs(other)
        with open(os.path.join(self.base, "Andere", "Rechnung.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 fremd")
        with open(os.path.join(self.real, "Rechnung.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 innen")
        os.symlink(other, os.path.join(self.real, "Archiv"))
        e = self.bl.link_existing(None, "Archiv/../Rechnung.pdf")
        self.assertEqual(e["pfad"], "Rechnung.pdf")                         # stored as it is checked
        legacy = self._legacy("Archiv/../Rechnung.pdf")                     # an older entry with the raw path
        self.assertTrue(self.bl.remove(legacy["id"], delete_file=True))
        self.assertTrue(os.path.exists(os.path.join(self.base, "Andere", "Rechnung.pdf")))
        self.assertTrue(self.bl.remove(e["id"], delete_file=True))
        self.assertFalse(os.path.exists(os.path.join(self.real, "Rechnung.pdf")))     # really in the folder: deleted
        self.assertTrue(os.path.exists(os.path.join(self.base, "Andere", "Rechnung.pdf")))

    def test_upload_into_a_linked_subfolder_stays_viewable(self):
        cloud = os.path.join(self.base, "Cloud", "2025"); os.makedirs(cloud)
        os.symlink(cloud, os.path.join(self.real, "2025"))                   # subfolder {jahr} a link (e.g. into iCloud Drive)
        bl = Belege(self.bl.store, {"belege": {"ordner": self.folder, "unterordner": "{jahr}"}})
        e = bl.add_bytes({"id": 7, "datum": "2025-03-01", "betrag": -12.5, "name": "Laden"}, "beleg.pdf", b"%PDF-1.4 hoch")
        self.assertTrue(os.path.isfile(os.path.join(cloud, os.path.basename(e["pfad"]))))
        self.assertEqual(bl.servable(e), bl.full_path(e))                    # viewable as before
        self.assertNotIn(e["pfad"], bl.check())
        with open(os.path.join(cloud, "fremd.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 nicht von Kontor")
        other = self._legacy_in(bl, "2025/fremd.pdf")
        self.assertTrue(bl.remove(other["id"], delete_file=True))
        self.assertTrue(os.path.isfile(os.path.join(cloud, "fremd.pdf")))       # behind a link and not put there by Kontor: stays
        self.assertTrue(bl.remove(e["id"], delete_file=True))
        self.assertFalse(os.path.isfile(os.path.join(cloud, os.path.basename(e["pfad"]))))    # Kontor's own upload: deleted as before
        os.makedirs(os.path.join(self.base, ".ssh")); os.symlink(os.path.join(self.base, ".ssh"), os.path.join(self.real, "Schluessel"))
        with open(os.path.join(self.base, ".ssh", "id.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 schluessel")
        self.assertIsNone(bl.servable(self._legacy_in(bl, "Schluessel/id.pdf")))   # a link into a hidden folder: not handed out

    def test_case_and_data_volume_spellings_do_not_bypass_the_checks(self):
        import receipts
        home = os.path.expanduser("~")
        old = receipts.FOLD_CASE
        receipts.FOLD_CASE = True                                              # as on macOS
        try:
            for p in (os.path.join(home, "library", "Messages", "Attachments", "IMG.heic"),
                      "/System/Volumes/Data" + os.path.join(home, "Library", "Messages", "IMG.heic"),
                      os.path.join(self.bl.store.data_dir.upper(), "x.pdf")):
                self.assertFalse(self.bl.external_ok(p), p)
            self.assertTrue(self.bl.external_ok(os.path.join(home, "library", "Mobile Documents", "com~apple~CloudDocs", "a.pdf")))
            self.assertTrue(self.bl.external_ok(os.path.join(home, "Documents", "Rechnung.pdf")))
        finally:
            receipts.FOLD_CASE = old

    def _legacy_in(self, bl, pfad):
        e = {"id": "alt-x%d" % len(bl.entries()), "tx_id": None, "datum": "2026-03-01", "pfad": pfad, "name": "Alt"}
        bl.entries().append(e)
        return e


if __name__ == "__main__":
    unittest.main()
