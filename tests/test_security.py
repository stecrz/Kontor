"""Security regressions (all with made-up data, never the real keychain): the idle lock with the page open, a keychain that
does not answer in time, and links in the receipts folder that point elsewhere."""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

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
        a, b = s.create("127.0.0.1", "password"), s.create("100.64.0.2", "password")
        for _ in range(29):                              # 14.5 minutes of status polls, nobody touches the page
            self.now[0] += 30
            self.assertIsNotNone(s.get(a["token"], touch=False))
        self.assertIsNotNone(s.get(b["token"]))          # another device in use: its own session
        self.now[0] += 60
        self.assertIsNone(s.get(a["token"], touch=False))     # 15.5 minutes without activity: locked
        self.assertIsNotNone(s.get(b["token"]))               # the other one stays

    def test_activity_keeps_it_open_but_not_beyond_the_limit(self):
        s = auth.Sessions(idle_minutes=15, max_hours=12)
        a = s.create("127.0.0.1", "password")
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
        self.assertEqual(storage.load_or_create_master_key(self.dir), (key, "file"))

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
        self.assertEqual((src, len(key)), ("file", 32))
        self.assertEqual(storage.load_or_create_master_key(self.dir), (key, "file"))

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
        self.assertEqual(storage.load_or_create_master_key(self.dir), (key, "file"))
        self.assertNotIn("add-generic-password", calls)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "master.key")))      # the file stays until the keychain answers


class FakeKeychain:
    """A made-up keychain for storage._security (never the real one): entries per account; fail_write: accounts that refuse."""

    def __init__(self):
        self.entries, self.fail_write, self.calls = {}, set(), []

    def __call__(self, args, input_text=None):
        self.calls.append(args)
        acc = args[args.index("-a") + 1] if "-a" in args else ""
        if args[0] == "find-generic-password":
            return (0, self.entries[acc] + "\n", "") if acc in self.entries else (44, "", "not found")
        if args[0] == "add-generic-password":
            if acc in self.fail_write:
                return (1, "", "refused")
            self.entries[acc] = args[args.index("-w") + 1]
            return (0, "", "")
        if args[0] == "delete-generic-password":
            return (0, "", "") if self.entries.pop(acc, None) is not None else (44, "", "not found")
        return (1, "", "?")


class KeyRenewal(unittest.TestCase):
    """Datenschluessel erneuern: everything re-encrypted, the old key gone only once all files open with the new one; an
    interruption is finished at the next start; a failure before that changes nothing. Only made-up keys and a made-up keychain."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-renew-")
        self._sec = storage._security
        self.kc = FakeKeychain()
        storage._security = self.kc
        self.old = os.urandom(32)
        self.kc.entries["kontor"] = self.old.hex()
        self.store = storage.Store(self.dir, self.old, "keychain")
        self.store.save("config.json", {"a": 1}); self.store.save("state.json", {"b": [1, 2]}); self.store.write_bytes("blob.bin", b"\x00\x01")

    def tearDown(self):
        storage._security = self._sec
        shutil.rmtree(self.dir, ignore_errors=True)

    def files(self):
        return sorted(n for n in os.listdir(self.dir) if n.endswith(".enc"))

    def opens_all(self, key):
        for n in self.files():
            with open(os.path.join(self.dir, n), "rb") as f:
                storage.decrypt(key, f.read())
        return True

    def test_renew(self):
        self.assertEqual(self.store.renew_key(), 3)
        new = bytes.fromhex(self.kc.entries["kontor"])
        self.assertNotEqual(new, self.old); self.assertEqual(self.store.master, new)
        self.assertTrue(self.opens_all(new)); self.assertNotIn("kontor-next", self.kc.entries)
        with self.assertRaises(storage.StoreError):
            self.opens_all(self.old)
        self.assertEqual(self.store.load("state.json"), {"b": [1, 2]})               # the running Kontor reads on
        self.assertEqual(storage.Store(self.dir, *storage.load_or_create_master_key(self.dir)).load("config.json"), {"a": 1})
        self.assertFalse([n for n in os.listdir(self.dir) if n.endswith((".renew", ".tmp", ".next"))])

    def test_keychain_refuses_the_new_key_nothing_changes(self):
        self.kc.fail_write.add("kontor-next")
        before = {n: open(os.path.join(self.dir, n), "rb").read() for n in self.files()}
        with self.assertRaises(storage.StoreError):
            self.store.renew_key()
        self.assertEqual({n: open(os.path.join(self.dir, n), "rb").read() for n in self.files()}, before)
        self.assertEqual(self.kc.entries, {"kontor": self.old.hex()}); self.assertEqual(self.store.master, self.old)
        self.assertFalse([n for n in os.listdir(self.dir) if n.endswith(".renew")])

    def test_a_file_that_does_not_open_stops_it(self):
        with open(os.path.join(self.dir, "fremd.json.enc"), "wb") as f:
            f.write(storage.encrypt(os.urandom(32), b"{}"))
        with self.assertRaises(storage.StoreError):
            self.store.renew_key()
        self.assertEqual(self.kc.entries, {"kontor": self.old.hex()}); self.assertEqual(self.store.master, self.old)

    def test_interrupted_after_the_new_key_is_kept(self):
        """The Mac went off after the new key was kept and some files were replaced: the next start re-encrypts the rest and
        moves the new key into the main entry; both keys stay as long as a file opens only with the old one."""
        new = os.urandom(32)
        self.kc.entries["kontor-next"] = new.hex()
        p = os.path.join(self.dir, "config.json.enc")
        with open(p, "wb") as f:
            f.write(storage.encrypt(new, b'{"a": 1}'))                 # this one replaced already, the others not yet
        open(os.path.join(self.dir, "state.json.enc.renew"), "wb").close()
        self.assertEqual(storage._finish_renewal(self.dir), new)
        self.assertEqual(self.kc.entries, {"kontor": new.hex()}); self.assertTrue(self.opens_all(new))
        self.assertFalse([n for n in os.listdir(self.dir) if n.endswith(".renew")])
        self.assertIsNone(storage._finish_renewal(self.dir))           # nothing more to do

    def test_interrupted_neither_key_opens_a_file(self):
        self.kc.entries["kontor-next"] = os.urandom(32).hex()
        with open(os.path.join(self.dir, "x.json.enc"), "wb") as f:
            f.write(storage.encrypt(os.urandom(32), b"{}"))
        with self.assertRaises(storage.StoreError):
            storage._finish_renewal(self.dir)
        self.assertIn("kontor", self.kc.entries); self.assertIn("kontor-next", self.kc.entries)       # no key deleted

    def test_no_new_key_over_existing_data(self):
        """No entry in the keychain but encrypted data in the folder: Kontor stops instead of making a new key."""
        del self.kc.entries["kontor"]
        with self.assertRaises(storage.StoreError):
            storage.load_or_create_master_key(self.dir)
        self.assertNotIn("kontor", self.kc.entries)
        with self.assertRaises(storage.StoreError):
            storage.read_master_key(self.dir)

    def test_only_with_the_keychain(self):
        """A key in a file (keychain not usable): no renewal -- a file key could not be finished after an interruption."""
        storage._security = lambda args, input_text=None: (127, "", "no security")
        d = tempfile.mkdtemp(prefix="kontor-renew-f-")
        try:
            key, src = storage.load_or_create_master_key(d)
            st = storage.Store(d, key, src); st.save("config.json", {"x": 1})
            with self.assertRaises(storage.StoreError):
                st.renew_key()
            self.assertEqual(storage.load_or_create_master_key(d), (key, "file"))
            with open(os.path.join(d, "master.key"), "w") as f:
                f.write("kaputt")
            with self.assertRaises(storage.StoreError):        # a broken key file next to the data is never replaced
                storage.load_or_create_master_key(d)
            self.assertEqual(open(os.path.join(d, "master.key")).read(), "kaputt")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_half_done_blocks_a_second_renewal(self):
        """The main entry did not take the new key: the running Kontor uses it, a second renewal is refused (its key would be
        lost), the next start finishes it."""
        self.kc.fail_write.add("kontor")
        with self.assertRaises(storage.StoreError):
            self.store.renew_key()
        new = self.store.master
        self.assertNotEqual(new, self.old); self.assertEqual(self.kc.entries["kontor-next"], new.hex()); self.assertTrue(self.opens_all(new))
        self.assertEqual(self.store.load("config.json"), {"a": 1})
        with self.assertRaises(storage.StoreError) as e:
            self.store.renew_key()
        self.assertEqual(str(e.exception), storage.tr("s_schluessel_erneuern_halb"))
        self.assertEqual(self.kc.entries["kontor-next"], new.hex())
        self.assertEqual(storage._finish_renewal(self.dir), new)          # main entry still refuses: starts with the new key anyway
        self.kc.fail_write.discard("kontor")
        self.assertEqual(storage._finish_renewal(self.dir), new)
        self.assertEqual(self.kc.entries, {"kontor": new.hex()})

    def test_keychain_without_answer_before_renewing(self):
        """The keychain does not answer when renewing starts: refused with its own message, nothing changed."""
        before = {n: open(os.path.join(self.dir, n), "rb").read() for n in self.files()}
        calls = self.kc
        storage._security = lambda args, input_text=None: (124, "", "timeout") if "kontor-next" in args else calls(args, input_text)
        with self.assertRaises(storage.StoreError) as e:
            self.store.renew_key()
        self.assertEqual(str(e.exception), storage.tr("s_schluessel_erneuern_nicht"))
        self.assertEqual({n: open(os.path.join(self.dir, n), "rb").read() for n in self.files()}, before)
        self.assertEqual(self.kc.entries, {"kontor": self.old.hex()}); self.assertEqual(self.store.master, self.old)

    def test_keychain_without_answer_during_finishing(self):
        """An unfinished renewal and the keychain does not answer at start: Kontor stops instead of starting with the old key."""
        self.kc.entries["kontor-next"] = os.urandom(32).hex()
        calls = self.kc
        storage._security = lambda args, input_text=None: (124, "", "timeout") if "kontor-next" in args else calls(args, input_text)
        with self.assertRaises(storage.StoreError):
            storage._finish_renewal(self.dir)
        self.assertIn("kontor-next", self.kc.entries)


    def half_done(self):
        """The main entry refused the new key: all files open with the new key, which is only in kontor-next."""
        self.kc.fail_write.add("kontor")
        with self.assertRaises(storage.StoreError):
            self.store.renew_key()
        self.kc.fail_write.discard("kontor")
        return self.store.master

    def test_read_only_takes_the_key_that_opens(self):
        """Uninstalling from the terminal in that state: the key that opens the data is found, nothing is moved."""
        new = self.half_done()
        self.assertEqual(storage.read_master_key(self.dir), (new, "keychain"))
        self.assertEqual(self.kc.entries, {"kontor": self.old.hex(), "kontor-next": new.hex()})

    def test_a_command_beside_the_service_does_not_finish(self):
        """A command in the terminal while the service runs uses the key that opens the data and leaves finishing to the
        service: two processes never finish a renewal at the same time."""
        new = self.half_done()
        before = {n: open(os.path.join(self.dir, n), "rb").read() for n in self.files()}
        with mock.patch.object(storage.sys, "platform", "darwin"):
            self.assertEqual(storage.load_or_create_master_key(self.dir, finish=False), (new, "keychain"))
            self.assertEqual(self.kc.entries, {"kontor": self.old.hex(), "kontor-next": new.hex()})
            self.assertEqual({n: open(os.path.join(self.dir, n), "rb").read() for n in self.files()}, before)
            self.assertEqual(storage.load_or_create_master_key(self.dir), (new, "keychain"))
        self.assertEqual(self.kc.entries, {"kontor": new.hex()})

    def test_keychain_asked_before_the_files_are_locked(self):
        """A slow keychain does not hold up reading and writing: the first two questions come before the lock."""
        kc, free = self.kc, []

        def sec(args, input_text=None):
            if args[0] == "find-generic-password":
                got = []

                def probe():
                    got.append(self.store._key_lock.acquire(blocking=False))
                    if got[0]:
                        self.store._key_lock.release()
                t = threading.Thread(target=probe)
                t.start(); t.join()
                free.append(got[0])
            return kc(args, input_text)
        storage._security = sec
        self.assertEqual(self.store.renew_key(), 3)
        self.assertEqual(free[:2], [True, True]); self.assertIn(False, free)      # the probe sees the lock when it is held


class CommandLine(unittest.TestCase):
    """kontor.py in the terminal: is the service running; uninstall stops when the settings do not open."""

    def setUp(self):
        import kontor
        self.K, self.dir = kontor, tempfile.mkdtemp(prefix="kontor-cli-")
        self._old = kontor.DATA_DIR
        kontor.DATA_DIR = self.dir

    def tearDown(self):
        self.K.DATA_DIR = self._old
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_finishing_only_under_the_service_lock(self):
        """A command finishes an unfinished renewal only while it holds the service's lock; beside the running service it
        leaves that to the service."""
        import fcntl
        seen, orig = [], self.K.load_or_create_master_key
        lock = os.path.join(self.dir, "service.lock")

        def fake(data_dir, finish=True):
            with open(lock, "a") as g:
                try:
                    fcntl.flock(g, fcntl.LOCK_EX | fcntl.LOCK_NB); free = True
                except OSError:
                    free = False
            seen.append((finish, free))
            return None, "file"
        self.K.load_or_create_master_key = fake
        self.addCleanup(setattr, self.K, "load_or_create_master_key", orig)
        self.K.open_store()
        self.assertEqual(seen, [(True, False)])                    # no service: finishes, and holds the lock meanwhile
        with open(lock, "w") as f:                                 # the service runs
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.K.open_store()
        self.assertEqual(seen[1][0], False)
        self.K.open_store()
        self.assertEqual(seen[2], (True, False))                   # the lock was given back each time

    def test_password_only_with_the_current_one_or_touch_id(self):
        """kontor.py password: the terminal is no way around signing in -- the current password (or Touch ID) first."""
        import argparse
        sec = storage._security
        storage._security = lambda args, input_text=None: (127, "", "no security")     # never the real keychain
        self.addCleanup(setattr, storage, "_security", sec)
        st = storage.Store(self.dir, *storage.load_or_create_master_key(self.dir))
        st.save("auth.json", auth.with_offline(auth.hash_password("altes-passwort-123"), "altes-passwort-123"))
        fresh = lambda: storage.Store(self.dir, *storage.load_or_create_master_key(self.dir)).load("auth.json")
        with mock.patch.object(self.K.auth, "touchid_available", return_value=False), mock.patch.object(self.K.time, "sleep"):
            with mock.patch.object(self.K.getpass, "getpass", side_effect=["falsch"] * 3):
                self.assertEqual(self.K.cmd_passwort(argparse.Namespace()), 1)
            self.assertTrue(auth.verify_password("altes-passwort-123", fresh()))
            with mock.patch.object(self.K.getpass, "getpass", side_effect=["altes-passwort-123", "neues-passwort-456", "neues-passwort-456"]):
                self.assertEqual(self.K.cmd_passwort(argparse.Namespace()), 0)
            self.assertTrue(auth.verify_password("neues-passwort-456", fresh()))
        with mock.patch.object(self.K.auth, "touchid_available", return_value=True), mock.patch.object(self.K.auth, "touchid_verify", return_value=True), \
                mock.patch.object(self.K.getpass, "getpass", side_effect=["drittes-passwort-789", "drittes-passwort-789"]):
            self.assertEqual(self.K.cmd_passwort(argparse.Namespace()), 0)          # Touch ID instead of the password
        self.assertTrue(auth.verify_password("drittes-passwort-789", fresh()))

    def test_only_these_commands(self):
        """Everything that reads or changes your data goes through the interface (signed in) -- not through the terminal."""
        import contextlib
        import io
        for cmd in ("run", "status", "accounts", "check", "package-export", "package-import", "diagnostics", "update", "tls"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.K.main([cmd])

    def test_uninstall_stops_when_the_settings_do_not_open(self):
        import argparse
        sec = storage._security
        storage._security = lambda args, input_text=None: (127, "", "no security")     # never the real keychain
        self.addCleanup(setattr, storage, "_security", sec)
        st = storage.Store(self.dir, *storage.load_or_create_master_key(self.dir))
        st.write_bytes("config.json", b"{kaputt")
        self.assertEqual(self.K.cmd_uninstall(argparse.Namespace(yes=True, program=False)), 1)
        self.assertTrue(os.path.exists(st.path("config.json"))); self.assertTrue(os.path.exists(os.path.join(self.dir, "master.key")))

    def test_install_waits_until_the_service_may_run(self):
        """macOS refuses the service (Login Items: background switched off): install says so, opens that page in System
        Settings, loads again until it is allowed and the service answers; without a terminal it gives up after half a minute."""
        import contextlib
        import io
        clock, calls, state = [0.0], [], {"allowed_after": 3, "loads": 0}

        def run(cmd, **kw):
            calls.append(cmd[:2])
            if cmd[:2] == ["launchctl", "load"]:
                state["loads"] += 1
            loaded = state["loads"] >= state["allowed_after"]
            return subprocess.CompletedProcess(cmd, 0 if (cmd[1] != "print" or loaded) else 113, "", "")
        with mock.patch.object(self.K.subprocess, "run", side_effect=run), \
                mock.patch.object(self.K.time, "sleep", side_effect=lambda s: clock.__setitem__(0, clock[0] + s)), \
                mock.patch.object(self.K.time, "time", side_effect=lambda: clock[0]), \
                mock.patch.object(self.K, "service_answers", side_effect=lambda port: state["loads"] >= state["allowed_after"]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.K.load_service()
            self.assertTrue(self.K.wait_for_service(8765, interactive=True))
        self.assertIn(["open", "x-apple.systempreferences:com.apple.LoginItems-Settings.extension"], calls)
        self.assertEqual(calls.count(["open", "x-apple.systempreferences:com.apple.LoginItems-Settings.extension"]), 1)
        self.assertIn(self.K.tr("s_hintergrund_erlauben"), out.getvalue()); self.assertIn(self.K.tr("s_dienst_laeuft"), out.getvalue())
        # allowed from the start: no hint, nothing opened
        calls.clear(); state.update(allowed_after=0, loads=0)
        with mock.patch.object(self.K.subprocess, "run", side_effect=run), \
                mock.patch.object(self.K, "service_answers", return_value=True), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertTrue(self.K.wait_for_service(8765, interactive=False))
        self.assertEqual(out.getvalue(), ""); self.assertNotIn("open", [c[0] for c in calls])
        # never allowed, no terminal: gives up
        clock[0] = 0.0; state.update(allowed_after=10 ** 9, loads=0)
        with mock.patch.object(self.K.subprocess, "run", side_effect=run), \
                mock.patch.object(self.K.time, "sleep", side_effect=lambda s: clock.__setitem__(0, clock[0] + s)), \
                mock.patch.object(self.K.time, "time", side_effect=lambda: clock[0]), \
                mock.patch.object(self.K, "service_answers", return_value=False), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(self.K.wait_for_service(8765, interactive=False))
            self.assertLessEqual(clock[0], 40)


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
        data = os.path.join(self.base, "data"); os.makedirs(data)
        self.bl = Belege(_Store(data), {"receipts": {"folder": self.folder}})

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_links(self):
        self.assertTrue(self.bl.link_existing(None, "2026/Rechnung.pdf"))
        self.assertTrue(self.bl.link_existing(None, "Kopie.pdf"))                     # within the folder: fine
        with self.assertRaises(ValueError):
            self.bl.link_existing(None, "2026/Fremd.pdf")                            # elsewhere: refused
        with self.assertRaises(ValueError):
            self.bl.link_existing(None, "../geheim.pdf")
        listed = {x["path"] for x in self.bl.listing()}
        self.assertIn("2026/Rechnung.pdf", listed); self.assertIn("Kopie.pdf", listed); self.assertNotIn("2026/Fremd.pdf", listed)
        self.assertFalse(self.bl.inside(os.path.join(self.folder, "2026", "Fremd.pdf")))

    def _legacy(self, pfad):
        """An entry as an earlier version could have made it (before links were checked)."""
        e = {"id": "alt%03d" % len(self.bl.entries()), "tx_id": None, "date": "2026-03-01", "path": pfad, "name": "Alt"}
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
        self.assertEqual(e["path"], "Rechnung.pdf")                         # stored as it is checked
        legacy = self._legacy("Archiv/../Rechnung.pdf")                     # an older entry with the raw path
        self.assertTrue(self.bl.remove(legacy["id"], delete_file=True))
        self.assertTrue(os.path.exists(os.path.join(self.base, "Andere", "Rechnung.pdf")))
        self.assertTrue(self.bl.remove(e["id"], delete_file=True))
        self.assertFalse(os.path.exists(os.path.join(self.real, "Rechnung.pdf")))     # really in the folder: deleted
        self.assertTrue(os.path.exists(os.path.join(self.base, "Andere", "Rechnung.pdf")))

    def test_upload_into_a_linked_subfolder_stays_viewable(self):
        cloud = os.path.join(self.base, "Cloud", "2025"); os.makedirs(cloud)
        os.symlink(cloud, os.path.join(self.real, "2025"))                   # subfolder {year} a link (e.g. into iCloud Drive)
        bl = Belege(self.bl.store, {"receipts": {"folder": self.folder, "subfolder": "{year}"}})
        e = bl.add_bytes({"id": 7, "date": "2025-03-01", "amount": -12.5, "name": "Laden"}, "beleg.pdf", b"%PDF-1.4 hoch")
        self.assertTrue(os.path.isfile(os.path.join(cloud, os.path.basename(e["path"]))))
        self.assertEqual(bl.servable(e), bl.full_path(e))                    # viewable as before
        self.assertNotIn(e["path"], bl.check())
        with open(os.path.join(cloud, "fremd.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 nicht von Kontor")
        other = self._legacy_in(bl, "2025/fremd.pdf")
        self.assertTrue(bl.remove(other["id"], delete_file=True))
        self.assertTrue(os.path.isfile(os.path.join(cloud, "fremd.pdf")))       # behind a link and not put there by Kontor: stays
        self.assertTrue(bl.remove(e["id"], delete_file=True))
        self.assertFalse(os.path.isfile(os.path.join(cloud, os.path.basename(e["path"]))))    # Kontor's own upload: deleted as before
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
        e = {"id": "alt-x%d" % len(bl.entries()), "tx_id": None, "date": "2026-03-01", "path": pfad, "name": "Alt"}
        bl.entries().append(e)
        return e


if __name__ == "__main__":
    unittest.main()
