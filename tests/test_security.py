"""Security regressions (all with made-up data, never the real keychain): the idle lock with the page open, a keychain that
does not answer in time, links in the receipts folder that point elsewhere -- and the ways out of the program (which parts can
open a connection, to which hosts, which other programs they start)."""
import ast
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urlparse
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
        self.entries, self.fail_write, self.fail_delete, self.calls = {}, set(), set(), []

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
            if acc in self.fail_delete:
                return (1, "", "refused")
            return (0, "", "") if self.entries.pop(acc, None) is not None else (44, "", "not found")
        return (1, "", "?")


class FakeEnclave:
    """A made-up Secure Enclave for auth.touchid_* (never the real one): a key per handle; it unwraps only while confirm is
    True (Touch ID or the Mac's password confirmed in the macOS window)."""

    def __init__(self):
        self.by_handle, self.by_pub, self.confirm, self.asked = {}, {}, True, 0

    def new_key(self):
        import base64
        import hashlib
        sec = os.urandom(32)
        handle, pub = base64.b64encode(os.urandom(24)).decode(), base64.b64encode(hashlib.sha256(sec).digest()).decode()
        self.by_handle[handle], self.by_pub[pub] = sec, sec
        return handle, pub

    def _kek(self, sec, eph, salt):
        import hashlib
        import hmac
        return hmac.new(sec, (eph + salt).encode(), hashlib.sha256).digest()

    def seal(self, pub, salt):
        import base64
        sec = self.by_pub.get(pub)
        if sec is None:
            return None
        eph = base64.b64encode(os.urandom(33)).decode()
        return eph, self._kek(sec, eph, salt)

    def unseal(self, se, eph, salt, reason=""):
        self.asked += 1
        sec = self.by_handle.get(se)
        return self._kek(sec, eph, salt) if self.confirm and sec is not None else None

    def patches(self):
        return [mock.patch.object(auth, "touchid_available", return_value=True), mock.patch.object(auth, "_helper_current", return_value=True),
                mock.patch.object(auth, "touchid_new_key", self.new_key),
                mock.patch.object(auth, "touchid_seal", self.seal), mock.patch.object(auth, "touchid_unseal", self.unseal)]


class SecretsStayInside(unittest.TestCase):
    """The secret openssl encrypts with never in its environment (other programs of this user read that, `ps -E`) -- a pipe; and
    the key Touch ID releases reaches Kontor wrapped for that one request, even though it passes a file."""

    def test_openssl_gets_the_secret_over_a_pipe(self):
        seen, real = [], storage.subprocess.run

        def watch(cmd, **kw):
            seen.append((cmd, dict(kw.get("env") or {}), kw.get("pass_fds")))
            return real(cmd, **kw)
        key = os.urandom(32)
        with mock.patch.object(storage.subprocess, "run", watch), mock.patch.object(storage, "_PASS", None):
            blob = storage.encrypt(key, b"geheim")
            self.assertEqual(storage.decrypt(key, blob), b"geheim")
            self.assertEqual(storage._PASS, "fd")
        enc_secret = storage._subkeys(key)[0]
        for cmd, env, fds in seen:
            self.assertNotIn(enc_secret, " ".join(cmd)); self.assertNotIn(enc_secret, env.values())
        work = [x for x in seen if x[2]]
        self.assertTrue(work and all(c[-1].startswith("fd:") for c, _, _ in work[-2:]))
        # the old way still opens what the pipe wrote and the other way round (the same secret)
        with mock.patch.object(storage, "_PASS", "env"):
            self.assertEqual(storage.decrypt(key, blob), b"geheim")
            old = storage.encrypt(key, b"alt")
        self.assertEqual(storage.decrypt(key, old), b"alt")
        # an openssl that cannot read a pipe: the environment, as before (found out with a made-up secret)
        def no_fd(cmd, **kw):
            if any(str(a).startswith("fd:") for a in cmd):
                return subprocess.CompletedProcess(cmd, 1, b"", b"bad option")
            return real(cmd, **kw)
        with mock.patch.object(storage.subprocess, "run", no_fd), mock.patch.object(storage, "_PASS", None):
            self.assertEqual(storage.decrypt(key, storage.encrypt(key, b"x")), b"x")
            self.assertEqual(storage._PASS, "env")

    def test_x25519_and_hkdf(self):
        nine = (9).to_bytes(32, "little")                # RFC 7748 6.1, RFC 5869 A.1
        a = bytes.fromhex("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
        b = bytes.fromhex("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb")
        self.assertEqual(auth._x25519(a, nine).hex(), "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a")
        self.assertEqual(auth._x25519(b, nine).hex(), "de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f")
        self.assertEqual(auth._x25519(a, auth._x25519(b, nine)).hex(), "4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742")
        self.assertEqual(auth._x25519(nine, nine).hex(), "422c8e7a6227d7bca1350b3e2bb7279f7897b87bb6854b783c60e80311ae3079")
        self.assertEqual(auth._hkdf(bytes.fromhex("0b" * 22), bytes.fromhex("000102030405060708090a0b0c"), bytes.fromhex("f0f1f2f3f4f5f6f7f8f9"), 42).hex(),
                         "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865")

    def helper_answer(self, kek, theirs_pub, nonce, tamper=False):
        """What touchid.swift --unseal prints, done the same way here."""
        import base64
        import hashlib
        import hmac
        mine = os.urandom(32)
        okm = auth._hkdf(auth._x25519(mine, theirs_pub), nonce.encode(), auth._TRANSPORT_INFO, 64)
        ct = bytes(x ^ y for x, y in zip(kek, okm[:32]))
        tag = hmac.new(okm[32:], ct, hashlib.sha256).hexdigest()
        if tamper:
            ct = bytes([ct[0] ^ 1]) + ct[1:]
        pub = base64.b64encode(auth._x25519(mine, (9).to_bytes(32, "little"))).decode()
        return "ok %s %s %s %s\n" % (nonce, pub, ct.hex(), tag)

    def test_touch_id_answer_is_wrapped_for_the_request(self):
        kek, files = os.urandom(32), []

        def fake_open(cmd, **kw):
            out = cmd[cmd.index("--stdout") + 1]
            args = cmd[cmd.index("--args") + 1:]
            self.assertEqual(args[0], "--unseal"); self.assertEqual(len(args), 7)
            import base64
            nonce, theirs = args[2], base64.b64decode(args[6])
            text = self.helper_answer(kek, theirs, nonce, tamper=self.tamper) if not self.gone else "gone %s\n" % nonce
            with open(out, "w") as f:
                f.write(text)
            files.append(text)
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        with mock.patch.object(auth, "_helper_current", return_value=True), mock.patch.object(auth.sys, "platform", "darwin"), \
                mock.patch.object(auth.subprocess, "run", fake_open):
            self.tamper = self.gone = False
            self.assertEqual(auth.touchid_unseal("aGFuZGxl", "ZXBo", "00" * 16), kek)
            self.assertNotIn(kek.hex(), files[-1])                 # the file never holds the key itself
            self.tamper = True
            self.assertIsNone(auth.touchid_unseal("aGFuZGxl", "ZXBo", "00" * 16))
            self.tamper, self.gone = False, True
            with self.assertRaises(auth.TouchIdGone):
                auth.touchid_unseal("aGFuZGxl", "ZXBo", "00" * 16)
            self.assertIsNone(auth.touchid_unseal("nicht base64!", "ZXBo", "00" * 16))      # only what Kontor made goes to the helper
        with mock.patch.object(auth, "_helper_current", return_value=False):               # an older build (right after an update): not asked
            self.assertIsNone(auth.touchid_unseal("aGFuZGxl", "ZXBo", "00" * 16))
            self.assertIsNone(auth.touchid_new_key())

    def test_a_touch_id_key_from_another_mac_goes(self):
        import access
        d = tempfile.mkdtemp(prefix="kontor-gone-")
        self.addCleanup(shutil.rmtree, d, True)
        se, key = FakeEnclave(), os.urandom(32)
        storage.Store(d, key, "login").save("config.json", {})
        with mock.patch.object(storage, "_security", FakeKeychain()):
            for p in se.patches():
                p.start(); self.addCleanup(p.stop)
            access.complete(d, key, "ein-langes-passwort"); access.set_touchid(d, key, True)
            self.assertTrue(access.touchid_ready(d))
            with mock.patch.object(auth, "touchid_unseal", side_effect=auth.TouchIdGone()):
                self.assertIsNone(access.unlock_touchid(d))
            self.assertFalse(access.touchid_ready(d)); self.assertTrue(storage.key_record(d)["password"])
            self.assertEqual(access.unlock_password(d, "ein-langes-passwort"), (key, "password"))
            self.assertTrue(access.set_touchid(d, key, True))      # set up again for this Mac after the sign-in
            self.assertEqual(access.unlock_touchid(d), (key, "touchid"))


class KeyRenewal(unittest.TestCase):
    """From before (the key in the keychain): a renewal that broke off is finished before the switch to the key file; the old key
    goes only once all files open with the new one. Only made-up keys and a made-up keychain."""

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

    def test_interrupted_after_the_new_key_is_kept(self):
        """The Mac went off after the new key was kept and some files were replaced: the next start re-encrypts the rest and
        moves the new key into the main entry; both keys stay as long as a file opens only with the old one."""
        new = os.urandom(32)
        self.kc.entries["kontor-next"] = new.hex()
        p = os.path.join(self.dir, "config.json.enc")
        with open(p, "wb") as f:
            f.write(storage.encrypt(new, b'{"a": 1}'))                 # this one replaced already, the others not yet
        open(os.path.join(self.dir, "state.json.enc.renew"), "wb").close()
        os.makedirs(os.path.join(self.dir, "chats"))                      # a saved conversation in its folder, still with the old key
        with open(os.path.join(self.dir, "chats", "assistant-chat-aaaaaaaa.json.enc"), "wb") as f:
            f.write(storage.encrypt(self.old, b'{"turns": []}'))
        open(os.path.join(self.dir, "chats", "assistant-chat-aaaaaaaa.json.enc.renew"), "wb").close()
        self.assertEqual(storage._finish_renewal(self.dir), new)
        self.assertEqual(self.kc.entries, {"kontor": new.hex()}); self.assertTrue(self.opens_all(new))
        with open(os.path.join(self.dir, "chats", "assistant-chat-aaaaaaaa.json.enc"), "rb") as f:
            self.assertEqual(storage.decrypt(new, f.read()), b'{"turns": []}')
        self.assertFalse([n for n in os.listdir(self.dir) + os.listdir(os.path.join(self.dir, "chats")) if n.endswith(".renew")])
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

    def test_keychain_without_answer_during_finishing(self):
        """An unfinished renewal and the keychain does not answer at start: Kontor stops instead of starting with the old key."""
        self.kc.entries["kontor-next"] = os.urandom(32).hex()
        calls = self.kc
        storage._security = lambda args, input_text=None: (124, "", "timeout") if "kontor-next" in args else calls(args, input_text)
        with self.assertRaises(storage.StoreError):
            storage._finish_renewal(self.dir)
        self.assertIn("kontor-next", self.kc.entries)

    def half_done(self):
        """From before: the main entry refused the new key -- all files open with the new key, which is only in kontor-next."""
        new = os.urandom(32)
        for n in self.files():
            p = os.path.join(self.dir, n)
            with open(p, "rb") as f:
                plain = storage.decrypt(self.old, f.read())
            with open(p, "wb") as f:
                f.write(storage.encrypt(new, plain))
        self.kc.entries["kontor-next"] = new.hex()
        return new

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

class KeyFileRenewal(unittest.TestCase):
    """Datenschluessel erneuern with the key file: everything re-encrypted (also in the store's folders), the old key gone only
    once all files open with the new one; a failure before that changes nothing, one after it locks Kontor and the next sign-in
    finishes it. Made-up keys and a made-up Secure Enclave only."""
    PW = "ein-langes-passwort"

    def setUp(self):
        import access
        self.A = access
        self.dir = tempfile.mkdtemp(prefix="kontor-renew2-")
        self._sec = storage._security
        storage._security = FakeKeychain()               # never the real keychain
        self.old = os.urandom(32)
        self.store = storage.Store(self.dir, self.old, "login")
        self.store.save("config.json", {"a": 1}); self.store.save("state.json", {"b": [1, 2]}); self.store.save("chats/assistant-chat-aaaaaaaa.json", {"t": 1})
        self.assertTrue(access.complete(self.dir, self.old, self.PW))

    def tearDown(self):
        storage._security = self._sec
        shutil.rmtree(self.dir, ignore_errors=True)

    def files(self):
        return {n: open(os.path.join(self.dir, n), "rb").read() for n in storage._enc_files(self.dir)}

    def pw_key(self):
        return storage.open_password_entry(storage.key_record(self.dir)["password"], self.PW)

    def test_renew(self):
        self.assertEqual(self.A.renew(self.store, self.PW), 3)
        new = self.store.master
        self.assertNotEqual(new, self.old); self.assertEqual(self.pw_key(), (new, None))
        self.assertEqual(storage.files_not_opening(new, self.dir), [])
        self.assertEqual(len(storage.files_not_opening(self.old, self.dir)), 3)          # the chats folder too
        self.assertEqual(self.store.load("chats/assistant-chat-aaaaaaaa.json"), {"t": 1})
        self.assertFalse([n for n in storage._names(self.dir) if n.endswith((".renew", ".tmp"))])
        self.assertEqual(self.A.unlock_password(self.dir, self.PW), (new, "password"))

    def test_a_failure_before_the_files_change_nothing(self):
        before, rec = self.files(), storage.key_record(self.dir)
        with mock.patch.object(storage, "write_key_record", side_effect=storage.StoreError("x")):
            with self.assertRaises(storage.StoreError):
                self.A.renew(self.store, self.PW)
        self.assertEqual(self.files(), before); self.assertEqual(storage.key_record(self.dir), rec)
        self.assertFalse([n for n in storage._names(self.dir) if n.endswith(".renew")])
        self.assertFalse(self.store.is_open)              # the key file may have taken the next key: locked until a sign-in
        self.assertEqual(self.A.unlock_password(self.dir, self.PW), (self.old, "password"))
        self.store.unlock(self.old, "login")
        with open(os.path.join(self.dir, "chats", "assistant-chat-bbbbbbbb.json.enc"), "wb") as f:
            f.write(storage.encrypt(os.urandom(32), b"{}"))                # a file the key does not open: stops before anything
        before = self.files()
        with self.assertRaises(storage.StoreError):
            self.A.renew(self.store, self.PW)
        self.assertEqual(self.files(), before); self.assertEqual(self.pw_key(), (self.old, None))

    def test_broken_off_after_the_next_key_was_kept(self):
        """The renaming fails half-way (or the key file does not take the new key): neither key in memory would do -- Kontor
        locks, the next sign-in finishes it."""
        real, n = os.replace, [0]

        def off(a, b):
            if a.endswith(".renew"):
                n[0] += 1
                if n[0] > 1:
                    raise OSError("disk full")
            return real(a, b)
        with mock.patch.object(storage.os, "replace", off):
            with self.assertRaises(storage.StoreError):
                self.A.renew(self.store, self.PW)
        self.assertFalse(self.store.is_open)
        with self.assertRaises(storage.StoreLocked):
            self.A.renew(self.store, self.PW)
        key, how = self.A.unlock_password(self.dir, self.PW)
        self.assertNotEqual(key, self.old); self.assertEqual(self.pw_key(), (key, None))
        self.assertEqual(storage.files_not_opening(key, self.dir), [])
        self.assertFalse([x for x in storage._names(self.dir) if x.endswith(".renew")])
        self.store.unlock(key, "login")
        real_write, calls = storage.write_key_record, [0]

        def second(d, r):
            calls[0] += 1
            if calls[0] == 2:
                raise storage.StoreError("x")
            return real_write(d, r)
        with mock.patch.object(storage, "write_key_record", second):
            with self.assertRaises(storage.StoreError):
                self.A.renew(self.store, self.PW)
        self.assertFalse(self.store.is_open)
        newer, _ = self.A.unlock_password(self.dir, self.PW)
        self.assertNotEqual(newer, key); self.assertEqual(storage.files_not_opening(newer, self.dir), []); self.assertEqual(self.pw_key(), (newer, None))

    def test_only_with_the_key_file(self):
        os.remove(os.path.join(self.dir, storage.KEY_FILE))
        with self.assertRaises(storage.StoreError) as e:
            self.A.renew(self.store, self.PW)
        self.assertEqual(str(e.exception), storage.tr("s_schluessel_erneuern_nicht"))
        self.assertEqual(storage.files_not_opening(self.old, self.dir), [])

    def test_touch_id_follows_the_new_key(self):
        se = FakeEnclave()
        for p in se.patches():
            p.start(); self.addCleanup(p.stop)
        self.assertTrue(self.A.set_touchid(self.dir, self.old, True))
        self.assertEqual(self.A.unlock_touchid(self.dir), (self.old, "touchid"))
        self.A.renew(self.store, self.PW)
        self.assertEqual(self.A.unlock_touchid(self.dir), (self.store.master, "touchid"))
        se.confirm = False
        self.assertIsNone(self.A.unlock_touchid(self.dir))


class LockedStore(unittest.TestCase):
    """Before anyone signs in the store has no key: every read and write refuses (StoreLocked), nothing is created -- and the
    key file holds the data key only wrapped (password), never in the clear. Made-up keys only."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-locked-")
        self.key = os.urandom(32)
        st = storage.Store(self.dir, self.key, "file")
        st.save("config.json", {"a": 1}); st.save("chats/assistant-chat-aaaaaaaa.json", {"turns": [1]}); st.write_bytes("x.bin", b"\x01")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def listing(self):
        return sorted(os.path.relpath(os.path.join(r, n), self.dir) for r, ds, fs in os.walk(self.dir) for n in ds + fs)

    def test_nothing_reads_or_writes_until_unlocked(self):
        st = storage.Store.closed(self.dir)
        self.assertFalse(st.is_open); self.assertTrue(st.encrypted)
        before = self.listing()
        for call in (lambda: st.load("config.json"), lambda: st.load("nope.json", {}), lambda: st.load_shared("config.json"),
                     lambda: st.save("config.json", {}), lambda: st.save("memory/x.json", {}), lambda: st.update("state.json", lambda o: None, {}),
                     lambda: st.read_bytes("x.bin"), lambda: st.write_bytes("y.bin", b""), lambda: st.delete("config.json"),
                     lambda: st.exists("config.json"), lambda: st.stamp("config.json"), lambda: st.renew_key(lambda o, n: None, lambda n: None)):
            with self.assertRaises(storage.StoreLocked):
                call()
        self.assertEqual(self.listing(), before)                     # not even a folder for a file that was refused
        self.assertTrue(issubclass(storage.StoreLocked, storage.StoreError))
        st.unlock(self.key, "file")
        self.assertTrue(st.is_open)
        self.assertEqual(st.load("config.json"), {"a": 1}); self.assertEqual(st.load("chats/assistant-chat-aaaaaaaa.json"), {"turns": [1]})
        st.close()
        self.assertFalse(st.is_open)
        with self.assertRaises(storage.StoreLocked):
            st.load("config.json")
        self.assertTrue(storage.Store(tempfile.mkdtemp(dir=self.dir), None).is_open)     # without encryption (tests only): open
        self.assertTrue(storage.Store(self.dir, self.key, "file").is_open)

    def test_unlock_needs_a_working_key(self):
        st = storage.Store.closed(self.dir)
        with mock.patch.object(storage, "selftest", lambda k: False):
            with self.assertRaises(storage.StoreError):
                st.unlock(self.key, "file")
        self.assertFalse(st.is_open)

    def test_key_file_wraps_the_key(self):
        self.assertIsNone(storage.key_record(self.dir))
        new = os.urandom(32)
        e = storage.password_entry(self.key, "ein-langes-passwort", nxt=new)
        storage.write_key_record(self.dir, {"password": e, "touchid": None})
        p = os.path.join(self.dir, storage.KEY_FILE)
        self.assertEqual(oct(os.stat(p).st_mode & 0o777), "0o600")
        raw = open(p, "rb").read()
        for k in (self.key, new):                                     # neither key in the clear, in any spelling
            self.assertNotIn(k, raw); self.assertNotIn(k.hex().encode(), raw); self.assertNotIn(__import__("base64").b64encode(k), raw)
        rec = storage.key_record(self.dir)
        self.assertEqual(storage.open_password_entry(rec["password"], "ein-langes-passwort"), (self.key, new))
        self.assertIsNone(storage.open_password_entry(rec["password"], "ein-falsches-passwort"))
        self.assertEqual(storage.open_password_entry(storage.password_entry(self.key, "pw-1234567890"), "pw-1234567890"), (self.key, None))
        self.assertNotEqual(storage.password_entry(self.key, "pw-1234567890")["salt"], storage.password_entry(self.key, "pw-1234567890")["salt"])
        for bad in ({"rounds": 10}, {"kdf": "md5"}, {"salt": "zz"}, {"key": "nicht-base64!"}, {"key": "AAAA"}):
            with self.assertRaises(storage.StoreError):
                storage.open_password_entry(dict(rec["password"], **bad), "ein-langes-passwort")
        self.assertFalse([n for n in os.listdir(self.dir) if n.endswith(".tmp")])

    def test_a_broken_key_file_is_never_taken_for_none(self):
        p = os.path.join(self.dir, storage.KEY_FILE)
        for content in (b"", b"{", b"[]", b'{"kontor_key": 2}', b'{"kontor_key": 1, "password": 5}', b"\xff\xfe"):
            with open(p, "wb") as f:
                f.write(content)
            with self.assertRaises(storage.StoreError):
                storage.key_record(self.dir)

    def test_files_not_opening_reaches_every_folder(self):
        self.assertEqual(storage.files_not_opening(self.key, self.dir), [])
        other = os.urandom(32)
        self.assertEqual(sorted(storage.files_not_opening(other, self.dir)),
                         sorted(["config.json.enc", os.path.join("chats", "assistant-chat-aaaaaaaa.json.enc"), "x.bin.enc"]))
        with open(os.path.join(self.dir, "chats", "assistant-chat-bbbbbbbb.json.enc"), "wb") as f:
            f.write(storage.encrypt(other, b"{}"))                       # one file in a folder with another key
        self.assertEqual(storage.files_not_opening(self.key, self.dir), [os.path.join("chats", "assistant-chat-bbbbbbbb.json.enc")])
        with mock.patch.object(storage, "ENC_DIRS", ("chats", "memory")):      # a folder added later counts the same way
            os.makedirs(os.path.join(self.dir, "memory"))
            with open(os.path.join(self.dir, "memory", "notes.json.enc"), "wb") as f:
                f.write(storage.encrypt(other, b"{}"))
            self.assertIn(os.path.join("memory", "notes.json.enc"), storage.files_not_opening(self.key, self.dir))


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

    def test_password_with_the_key_file(self):
        """kontor.py password once the key file holds the key: the current password (or Touch ID) opens it, the new one wraps it
        -- the data key stays the same, the old password opens nothing any more."""
        import argparse
        import access
        sec = storage._security
        storage._security = FakeKeychain()                # never the real keychain
        self.addCleanup(setattr, storage, "_security", sec)
        key = os.urandom(32)
        storage.Store(self.dir, key, "login").save("config.json", {})
        access.complete(self.dir, key, "altes-passwort-123")
        opens = lambda pw: access.unlock_password(self.dir, pw)
        with mock.patch.object(self.K.time, "sleep"):
            with mock.patch.object(self.K.getpass, "getpass", side_effect=["falsch"] * 3):
                self.assertEqual(self.K.cmd_passwort(argparse.Namespace()), 1)
            with mock.patch.object(self.K.getpass, "getpass", side_effect=["altes-passwort-123", "neues-passwort-456", "neues-passwort-456"]):
                self.assertEqual(self.K.cmd_passwort(argparse.Namespace()), 0)
        self.assertIsNone(opens("altes-passwort-123")); self.assertEqual(opens("neues-passwort-456"), (key, "password"))
        se = FakeEnclave()
        for p in se.patches():
            p.start(); self.addCleanup(p.stop)
        self.assertTrue(access.set_touchid(self.dir, key, True))
        with mock.patch.object(self.K.getpass, "getpass", side_effect=["drittes-passwort-789", "drittes-passwort-789"]):
            self.assertEqual(self.K.cmd_passwort(argparse.Namespace()), 0)          # forgotten: Touch ID (or the Mac's password) instead
        self.assertEqual(se.asked, 1); self.assertEqual(opens("drittes-passwort-789"), (key, "password"))
        self.assertEqual(access.unlock_touchid(self.dir), (key, "touchid"))      # Touch ID's entry stays

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

    def test_the_list_holds_no_formulas(self):
        """The list in the export (CSV) is opened in a spreadsheet: a name from the bank or a note that starts like a formula
        stays text."""
        import zipfile
        e = self.bl.link_existing(None, "2026/Rechnung.pdf")
        e.update(name='=HYPERLINK("http://x.invalid";"Rechnung")', note="@SUM(1+1)", amount=-12.5, date="2026-03-01")
        with zipfile.ZipFile(self.bl.export_zip(None, None, {})) as z:
            rows = z.read("Belege.csv").decode("utf-8").splitlines()
        self.assertEqual(len(rows), 2)
        self.assertIn(";\"'=HYPERLINK(", rows[1]); self.assertIn(";'@SUM(1+1);", rows[1]); self.assertIn(";-12,50;", rows[1])      # amounts stay numbers
        import excel, io
        wb = excel.workbook([excel.Sheet("Blatt", ["Text", "Zahl"], [["Miete\x0bMärz\x00", float("nan")], ["=1+1", float("inf")], ["ok", 1.5]])])
        with zipfile.ZipFile(io.BytesIO(wb)) as z:
            sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        from xml.dom import minidom
        minidom.parseString(sheet)                                          # opens: no character XML forbids
        self.assertIn("MieteMärz", sheet); self.assertNotIn("nan", sheet.lower()); self.assertNotIn("inf<", sheet.lower()); self.assertIn("<v>1.5</v>", sheet)
        self.assertIn(">=1+1<", sheet); self.assertNotIn("<f>", sheet)      # a text, not a formula

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


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DemoAnswersOnlyItsOwn(unittest.TestCase):
    """The demo (service.DemoApp) answers only what DEMO_GET / DEMO_POST name; every request of the service is named in one of
    them or in DEMO_NEVER -- a new request has to be decided there (refused until then)."""

    def test_every_request_is_decided(self):
        import service as MA
        with open(os.path.join(ROOT, "service.py"), encoding="utf-8") as f:
            src = f.read()
        handler = src[src.index("def make_handler("):src.index("\nBACKUP_ITER")]
        paths = set(re.findall(r'(?:u\.)?path == "(/api/[^"]+)"', handler))
        for group in re.findall(r'path in \(([^)]*)\)', handler):
            paths |= set(re.findall(r'"(/api/[^"]+)"', group))
        self.assertGreater(len(paths), 80)
        paths.discard("/api/session")                           # the demo answers it itself: its own session
        known = MA.DEMO_GET | MA.DEMO_POST | MA.DEMO_NEVER
        self.assertEqual(sorted(p for p in paths if p not in known and not p.startswith(MA.DEMO_GET_PREFIX)), [],
                         "a request the demo has not been decided for: put it into DEMO_GET, DEMO_POST or DEMO_NEVER (service.py)")
        self.assertEqual(MA.DEMO_NEVER & (MA.DEMO_GET | MA.DEMO_POST), frozenset())
        self.assertEqual(sorted((MA.DEMO_GET | MA.DEMO_POST | MA.DEMO_NEVER) - paths), [])        # no name for a request that is gone
        for p in ("/api/setup", "/api/login", "/api/password", "/api/uninstall", "/api/log", "/api/backup", "/api/file/open", "/api/update/install",
                  "/api/assistant/settings", "/api/assistant/web", "/api/remote", "/api/receipts/link", "/api/securities/lookup"):
            self.assertFalse(MA.demo_allowed("GET", p) or MA.demo_allowed("POST", p), p)
        self.assertFalse(MA.demo_allowed("POST", "/api/properties", {"action": "doc_add"}))
        self.assertTrue(MA.demo_allowed("POST", "/api/properties", {"action": "update"}))

    def test_nothing_of_the_real_kontor_in_its_settings(self):
        import demo
        real = {"ui": {"language": "en", "lock_minutes": 9, "bind": "100.64.1.2", "tls_cert": "/x.crt", "port": 9000},
                "areas": [{"id": "x", "name": "Echt GmbH"}], "receipts": {"folder": "/Users/x/Belege"}, "loans": [{"name": "Echt"}],
                "assistant": {"enabled": True, "model": "m"}}
        cfg = demo.config(demo.World(), real, "/tmp/kontor-demo-x/Belege")
        self.assertEqual(cfg["ui"], {"language": "en", "lock_minutes": 9, "port": 9000, "offline_copy": False})      # the port: so that its Mac helpers find nothing to build
        self.assertEqual(cfg["receipts"]["folder"], "/tmp/kontor-demo-x/Belege")
        self.assertNotIn("Echt", json.dumps(cfg, ensure_ascii=False))
        self.assertEqual(cfg["assistant"], real["assistant"])


class NothingGoesOut(unittest.TestCase):
    """"Everything local, nothing goes out" (CLAUDE.md, Sicherheit) as a list a machine checks: which parts of the program can
    open a connection at all, the hosts they name, the other programs they start, and what the pages may reach. A new way
    out does not slip in with some other change -- it has to be named here, where it is seen. (A trip wire for what is
    written in the open, not a proof: the allow-lists in updates.py, llm_local.py and security_names.py are what holds.)"""

    # the program's parts that import something able to open or accept a connection -- and why
    NETWORK = {
        "service.py": {"http.server", "socket", "ssl"},                # the interface itself: 127.0.0.1 and the Tailscale address
        "kontor.py": {"socket"},                                       # asks whether its own service answers on 127.0.0.1
        "tls_cert.py": {"http.client", "ssl"},                         # Tailscale's interface on this Mac (127.0.0.1)
        "updates.py": {"urllib.request"},                              # update check and download: GitHub, on your click or as set
        "llm_local.py": {"urllib.request", "http.client", "socket"},   # llama.cpp and model files (downloads on your click); the model on 127.0.0.1
        "security_names.py": {"urllib.request"},                       # names of securities at OpenFIGI: on your click, ISINs only
        "web_reader.py": {"urllib.request", "http.client", "socket", "ssl"},          # the assistant's internet search: one fetch you approved, in a process of its own
    }
    NETWORK_MODULES = {"socket", "ssl", "http.client", "http.server", "urllib.request", "socketserver", "ftplib", "smtplib", "poplib", "imaplib",
                       "telnetlib", "nntplib", "xmlrpc", "asyncio", "selectors", "webbrowser", "requests", "httpx", "aiohttp", "urllib3", "websocket",
                       "websockets", "paramiko", "pycurl"}
    # hosts written in the program: the ones it connects to, by part ...
    HOSTS = {"updates.py": {"api.github.com", "github.com", "raw.githubusercontent.com"},
             "llm_local.py": {"api.github.com", "huggingface.co"},
             "security_names.py": {"api.openfigi.com"},
             # the internet search's sources (each fetch after your click; the reader checks the host again) -- and, named only:
             # the program's page (in its User-Agent), the ECB's and GLEIF's pages that results link to
             "web_search.py": {"www.wikidata.org", "www.gesetze-im-internet.de", "api.gleif.org", "data-api.ecb.europa.eu", "api.statistiken.bundesbank.de",
                               "ec.europa.eu", "www.tagesschau.de", "api.gdeltproject.org", "api.tavily.com", "data.ecb.europa.eu", "search.gleif.org",
                               "testphase.rechtsinformationen.bund.de", "www.bundesfinanzministerium.de", "www.bundesbank.de", "www.ecb.europa.eu",
                               "sdmx.oecd.org", "api.worldbank.org", "data.worldbank.org", "stats.bis.org"}}
    NAMES_ONLY = {"schemas.openxmlformats.org", "purl.oclc.org", "www.apple.com"}      # ... and names of file formats (never opened)
    # other programs started by their name (all of macOS or Apple's tools, git for an update of a clone)
    COMMANDS = {"security", "openssl", "swiftc", "codesign", "open", "launchctl", "/bin/launchctl", "/usr/sbin/sysctl", "ps", "pgrep", "tmutil",
                "osascript", "/usr/bin/osascript", "xcode-select", "git", "/bin/sh",
                "sips", "iconutil", "defaults", "tccutil"}          # Kontor's own Mac app: its icon, its address, gone on uninstall
    # ... and by a path Kontor made up itself (its Touch ID helper, the password window, llama.cpp, Tailscale's own tool, lsof, the receipt reader, the web reader)
    COMMANDS_BY_PATH = {"auth.py", "mm_history.py", "llm_local.py", "tls_cert.py", "receipt_text.py", "web_search.py"}     # receipt_text: its text recognition, sealed; web_search: python3 -I web_reader.py (in the sandbox)
    # where links on the pages lead (opened by you, in a new window; the pages themselves only talk to Kontor)
    LINKS = {"github.com", "tailscale.com", "login.tailscale.com", "apps.apple.com", "www.w3.org"}
    HOST = re.compile(r"(?:https?|wss?|ftp)://([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")

    @classmethod
    def setUpClass(cls):
        cls.trees = {}
        for path in sorted(glob.glob(os.path.join(ROOT, "*.py"))):
            with open(path, encoding="utf-8") as f:
                cls.trees[os.path.basename(path)] = ast.parse(f.read())

    def test_only_these_parts_can_open_a_connection(self):
        found = {}
        for name, tree in self.trees.items():
            mods = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    mods |= {a.name for a in n.names}
                elif isinstance(n, ast.ImportFrom) and n.module:
                    mods |= {n.module} | {"%s.%s" % (n.module, a.name) for a in n.names}
            hit = {m for m in self.NETWORK_MODULES if any(x == m or x.startswith(m + ".") for x in mods)}
            if hit:
                found[name] = hit
        self.assertEqual(found, self.NETWORK, "a part of the program that can open a connection changed -- name it in NothingGoesOut.NETWORK "
                                              "(and what goes out in CLAUDE.md, Sicherheit)")

    def test_only_these_hosts_are_written_in_the_program(self):
        found = {}
        for name, tree in self.trees.items():
            hosts = {h.lower() for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) for h in self.HOST.findall(n.value)}
            hosts -= self.NAMES_ONLY | {"127.0.0.1"}
            if hosts:
                found[name] = hosts
        self.assertEqual(found, self.HOSTS, "a host written in the program changed (a link in a text counts too) -- name it in NothingGoesOut.HOSTS "
                                            "if Kontor connects to it, in NAMES_ONLY if it only names a file format")
        # and the lists that hold at run time are these
        import llm_local
        import security_names
        import updates
        self.assertEqual(set(updates.ALLOWED_HOSTS), {"api.github.com", "codeload.github.com", "github.com", "raw.githubusercontent.com", "objects.githubusercontent.com"})
        self.assertEqual(security_names.HOST, "api.openfigi.com")
        import web_search                                                # the internet search: these hosts and no others (a result of tier 2 or 3: only its own)
        self.assertEqual({s: set(v["hosts"]) for s, v in web_search.SOURCES.items()},
                         {"wikipedia": {"de.wikipedia.org", "en.wikipedia.org"}, "wikidata": {"www.wikidata.org"}, "laws": {"www.gesetze-im-internet.de"},
                          "gleif": {"api.gleif.org"}, "ecb": {"data-api.ecb.europa.eu"}, "bundesbank": {"api.statistiken.bundesbank.de"}, "eurostat": {"ec.europa.eu"},
                          "ris": {"testphase.rechtsinformationen.bund.de"}, "feeds": {"www.bundesfinanzministerium.de", "www.bundesbank.de", "www.ecb.europa.eu"},
                          "oecd": {"sdmx.oecd.org"}, "worldbank": {"api.worldbank.org"}, "bis": {"stats.bis.org"},
                          "tagesschau": {"www.tagesschau.de"}, "gdelt": {"api.gdeltproject.org"}, "tavily": {"api.tavily.com"}})
        self.assertTrue(all(urlparse(u).hostname in web_search.SOURCES["feeds"]["hosts"] and u.startswith("https://") for u in web_search.FEEDS.values()))
        for url, kind, ok in (("https://github.com/x", "github", True), ("https://release-assets.githubusercontent.com/x", "github", True),
                              ("https://huggingface.co/x", "hf", True), ("https://cdn-lfs.hf.co/x", "hf", True),
                              ("https://example.com/x", "github", False), ("https://example.com/x", "hf", False), ("http://github.com/x", "github", False),
                              ("https://github.com.example.com/x", "github", False), ("https://huggingface.co.example.com/x", "hf", False),
                              ("https://user:pw\x40github.com/x", "github", False), ("https://huggingface.co/x", "github", False)):
            self.assertEqual(llm_local.host_allowed(url, kind), ok, url)

    def test_only_these_programs_are_started(self):
        names, by_path, odd = set(), set(), []
        for name, tree in self.trees.items():
            for n in ast.walk(tree):
                if not isinstance(n, ast.Call):
                    continue
                fn = n.func
                attr, base = (fn.attr, getattr(fn.value, "id", "")) if isinstance(fn, ast.Attribute) else (getattr(fn, "id", ""), "")
                if base == "subprocess":
                    if any(k.arg == "shell" for k in n.keywords):
                        odd.append("%s:%d shell=" % (name, n.lineno))
                    first = n.args[0] if n.args else None
                    while isinstance(first, ast.BinOp):                  # ["security"] + args
                        first = first.left
                    if isinstance(first, ast.IfExp):                     # ["open", "-R", x] if ... else ["open", x]
                        first = first.body
                    if isinstance(first, ast.List) and first.elts and isinstance(first.elts[0], ast.Constant):
                        names.add(first.elts[0].value)
                    else:
                        by_path.add(name)
                elif (base == "os" and (attr in ("system", "popen") or attr.startswith(("spawn", "posix_spawn")))) or (not base and attr in ("eval", "exec", "__import__")) \
                        or base == "importlib" or (base == "os" and attr.startswith("exec") and name != "service.py"):
                    odd.append("%s:%d %s" % (name, n.lineno, attr))
        self.assertEqual(odd, [])
        self.assertEqual(names - self.COMMANDS, set(), "a program started by name that is not in NothingGoesOut.COMMANDS")
        self.assertEqual(by_path, self.COMMANDS_BY_PATH, "a program started by a path: name the part in NothingGoesOut.COMMANDS_BY_PATH")

    def test_the_mac_app_shows_kontor_only(self):
        """Kontor's own Mac app (mac_app.swift): Kontor's address on this Mac only, nothing it fetches itself, no other program;
        the microphone only for Kontor's own page (its address, the main frame); every other address goes to the browser; the
        page's messages count only from Kontor's own page."""
        with open(os.path.join(ROOT, "mac_app.swift"), encoding="utf-8") as f:
            src = f.read()
        code = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("//"))
        self.assertEqual({h.lower() for h in self.HOST.findall(code)}, {"127.0.0.1"})
        self.assertEqual(re.findall(r"URLSession|NSURLConnection|CFNetwork|Process\(|NSTask|\bsystem\(|posix_spawn|isInspectable|developerExtras", code), [])
        self.assertIn('u.scheme == "http", u.host == "127.0.0.1"', code)                               # its address: only ever this Mac
        self.assertIn("guard URL(string: c) == home else", code)                                       # the test mode too: Kontor's address only
        self.assertIn("frame.isMainFrame && isHome(origin) && isHome(webView.url) && type == .microphone ? .grant : .deny", code)
        nav = code[code.index("decidePolicyForNavigationAction"):code.index("decidePolicyForNavigationResponse")]
        self.assertIn("decisionHandler(.cancel)", nav); self.assertIn("openOutside(u)", nav)          # anything else: the browser, never in here
        self.assertIn("decisionHandler(mine ? .download : .cancel)", nav)                              # downloads: Kontor's own only
        pop = code[code.index("createWebViewWithConfiguration"):code.index("webViewDidClose")]
        self.assertIn("guard isHome(u) else { openOutside(u); return nil }", pop)
        msg = code[code.index("func userContentController"):]
        self.assertIn("guard message.frameInfo.isMainFrame, isHome(message.frameInfo.securityOrigin)", msg)
        self.assertIn('body["drag"] as? [[Double]], message.webView === web', msg)                       # the window's strip: Kontor's window only

    def test_the_pages_talk_to_kontor_only(self):
        for path in sorted(glob.glob(os.path.join(ROOT, "web", "*"))):
            if not path.endswith((".js", ".html", ".css", ".webmanifest", ".svg")):
                continue
            with open(path, encoding="utf-8") as f:
                text = f.read()
            name = os.path.basename(path)
            self.assertEqual({h.lower() for h in self.HOST.findall(text)} - self.LINKS, set(), name)
            # requests go to Kontor's own address (a path), never to a full address; nothing else that could send
            self.assertEqual(re.findall(r"""fetch\(\s*['"`](?!/(?!/))[^'"`]*""", text), [], name)
            self.assertEqual(re.findall(r"XMLHttpRequest|sendBeacon|WebSocket|EventSource|importScripts|RTCPeerConnection|<script[^>]+src=[\"'](?!/(?!/))", text), [], name)
        import service
        with open(service.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("default-src 'self'", src); self.assertIn("connect-src 'self'", src); self.assertIn("form-action 'self'", src)


if __name__ == "__main__":
    unittest.main()
