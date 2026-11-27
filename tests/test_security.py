"""Security regressions (all with made-up data): the idle lock with the page open, the data key (key file, renewal, Touch ID,
the terminal), links in the receipts folder that point elsewhere -- and the ways out of the program (which parts can open a
connection, to which hosts, which other programs they start)."""
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


class FakeEnclave:
    """A made-up Secure Enclave for auth.touchid_* (never the real one): a key per handle; it unwraps only while confirm is
    True (Touch ID or the Mac's password confirmed in the macOS window)."""

    def __init__(self):
        self.by_handle, self.by_pub, self.confirm, self.asked, self.windows = {}, {}, True, 0, []

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

    def unseal(self, se, eph, salt, reason="", tid=""):
        self.asked += 1
        self.windows.append((reason, tid))               # what the macOS window says, for which request of the sign-in page
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
        storage.Store(d, key).save("config.json", {})
        for p in se.patches():
            p.start(); self.addCleanup(p.stop)
        self.assertTrue(access.complete(d, key, "ein-langes-passwort")); access.set_touchid(d, key, True)
        self.assertTrue(access.touchid_ready(d))
        with mock.patch.object(auth, "touchid_unseal", side_effect=auth.TouchIdGone()):
            self.assertIsNone(access.unlock_touchid(d))
        self.assertFalse(access.touchid_ready(d)); self.assertTrue(storage.key_record(d)["password"])
        self.assertEqual(access.unlock_password(d, "ein-langes-passwort"), (key, "password"))
        self.assertTrue(access.set_touchid(d, key, True))      # set up again for this Mac after the sign-in
        self.assertEqual(access.unlock_touchid(d), (key, "touchid"))
        # the window says what the sign-in opens -- passed on as it is, with the sign-in page's request
        self.assertEqual(access.unlock_touchid(d, "die Demo öffnen", tid="ab" * 16), (key, "touchid"))
        self.assertEqual(se.windows[-1], ("die Demo öffnen", "ab" * 16))


class TouchIdWindowCloses(unittest.TestCase):
    """The sign-in page switched between your data and the demo while the macOS window is open (service.App.touchid_switch):
    auth.touchid_close deletes the answer file of exactly that request -- touchid.swift sees its output gone and closes the
    window, without an answer --, nothing else; the request asks nothing more (no second window without LaunchServices)."""

    TID = "a1" * 16

    def setUp(self):
        self.addCleanup(auth._TID_FILES.clear)
        self.other = tempfile.mkdtemp(prefix="kontor-tid-")       # another request's folder (another id)
        self.addCleanup(shutil.rmtree, self.other, True)
        with open(os.path.join(self.other, "result"), "w") as f:
            f.write("x")
        auth._tid_track("b2" * 16, os.path.join(self.other, "result"))
        self.runs, self.code, self.answer = [], 0, ""

    def fake_run(self, cmd, **kw):
        """LaunchServices: makes the answer file, the helper's window is open -- the page switches -- the window ends."""
        self.runs.append(cmd[0])
        if cmd[0] != "open":
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        out = cmd[cmd.index("--stdout") + 1]
        args = cmd[cmd.index("--args") + 1:]
        with open(out, "w") as f:
            f.write(self.answer.replace("NONCE", args[2] if args[0] == "--unseal" else args[1]))
        beside = os.path.join(tempfile.gettempdir(), "kontor-beside-%d" % os.getpid())
        with open(beside, "w") as f:
            f.write("x")
        self.addCleanup(lambda: os.path.exists(beside) and os.remove(beside))
        for wrong in ("", "c3" * 16, self.TID.upper()):               # no request, or another one: nothing goes
            self.assertFalse(auth.touchid_close(wrong))
        self.assertTrue(os.path.exists(out))
        self.assertTrue(auth.touchid_close(self.TID))
        self.assertFalse(os.path.exists(out)); self.assertFalse(os.path.exists(os.path.dirname(out)))     # its file, its empty folder
        self.assertTrue(auth.touchid_close(self.TID))                # closed already: nothing more to do
        self.assertTrue(os.path.exists(beside)); self.assertTrue(os.path.exists(os.path.join(self.other, "result")))
        return subprocess.CompletedProcess(cmd, self.code, b"", b"")

    def test_only_the_answer_file_of_the_request(self):
        with mock.patch.object(auth, "touchid_available", return_value=True), mock.patch.object(auth.sys, "platform", "darwin"), \
                mock.patch.object(auth.subprocess, "run", self.fake_run):
            for self.code in (0, 1):                         # `open` ends well or not: no answer either way
                self.answer = "ok NONCE\n"                   # (even what the helper wrote before goes with the file)
                self.assertFalse(auth.touchid_verify("R", tid=self.TID))
        self.assertEqual(self.runs, ["open", "open"])        # never asked again without LaunchServices
        self.assertEqual(list(auth._TID_FILES), ["b2" * 16])     # the request forgotten once it is over, the other one kept

    def test_the_key_is_not_gone_when_the_window_closes(self):
        with mock.patch.object(auth, "_helper_current", return_value=True), mock.patch.object(auth.sys, "platform", "darwin"), \
                mock.patch.object(auth.subprocess, "run", self.fake_run):
            self.answer = "gone NONCE\n"                     # a closed window says nothing about the key: no TouchIdGone
            self.assertIsNone(auth.touchid_unseal("aGFuZGxl", "ZXBo", "00" * 16, "R", tid=self.TID))
        self.assertEqual(self.runs, ["open"])
        self.assertEqual(list(auth._TID_FILES), ["b2" * 16])

    def test_never_a_file_outside_its_own_folder(self):
        d = tempfile.mkdtemp(prefix="kontor-x-")
        self.addCleanup(shutil.rmtree, d, True)
        own = os.path.join(d, "kontor-tid-x")
        os.mkdir(own)
        for i, path in enumerate((os.path.join(d, "result"), os.path.join(own, "result"), os.path.join(self.other, "andere"))):
            with open(path, "w") as f:
                f.write("x")
            tid = "%02d" % i * 16
            auth._tid_track(tid, path)                       # (only touchid_verify / touchid_unseal put their own file there)
            self.assertFalse(auth.touchid_close(tid))
            self.assertTrue(os.path.exists(path))
        self.assertTrue(auth._tid_track("00" * 16, None))    # marked closed all the same: the request asks nothing more
        self.assertFalse(auth._tid_track("00" * 16, None))   # ... and is forgotten
        self.assertFalse(auth._tid_track("", "/x")); self.assertNotIn("", auth._TID_FILES)     # no id: nothing kept



class KeyFileRenewal(unittest.TestCase):
    """Datenschluessel erneuern with the key file: everything re-encrypted (also in the store's folders), the old key gone only
    once all files open with the new one; a failure before that changes nothing, one after it locks Kontor and the next sign-in
    finishes it. Made-up keys and a made-up Secure Enclave only."""
    PW = "ein-langes-passwort"

    def setUp(self):
        import access
        self.A = access
        self.dir = tempfile.mkdtemp(prefix="kontor-renew2-")
        self.old = os.urandom(32)
        self.store = storage.Store(self.dir, self.old)
        self.store.save("config.json", {"a": 1}); self.store.save("state.json", {"b": [1, 2]}); self.store.save("chats/assistant-chat-aaaaaaaa.json", {"t": 1})
        self.assertTrue(access.complete(self.dir, self.old, self.PW))

    def tearDown(self):
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
        self.store.unlock(self.old)
        before = self.files()
        real = storage.decrypt

        def fails(key, blob):                                             # a file that cannot be read right now (openssl, the disk) ...
            if blob == before["state.json.enc"]:
                raise storage.StoreError("openssl")
            return real(key, blob)
        with mock.patch.object(storage, "decrypt", fails):
            with self.assertRaises(storage.StoreError):                   # ... still stops it before anything changes
                self.A.renew(self.store, self.PW)
        self.assertEqual(self.files(), before); self.assertEqual(self.pw_key(), (self.old, None)); self.assertTrue(self.store.is_open)

    def damage(self):
        """Two files no key opens: one cut off (a notes file of the memory), one written with another key."""
        with open(os.path.join(self.dir, "memory-notes-0002.json.enc"), "wb") as f:
            f.write(storage.encrypt(self.old, b'{"v": 1, "notes": []}')[:-9])
        with open(os.path.join(self.dir, "chats", "assistant-chat-bbbbbbbb.json.enc"), "wb") as f:
            f.write(storage.encrypt(os.urandom(32), b"{}"))
        return ["chats/assistant-chat-bbbbbbbb.json.enc", "memory-notes-0002.json.enc"]

    def test_a_file_no_key_opens_does_not_stop_it(self):
        """A damaged file opens with no key, so none is lost with the old one: it stays as it is -- byte for byte, under its
        name -- and is named; everything else gets the new key. (Before: every renewal ended with "check sum does not match",
        without the file's name, for ever.)"""
        bad = self.damage()
        before = self.files()
        self.assertEqual(self.A.renew(self.store, self.PW), 3)
        new = self.store.master
        self.assertNotEqual(new, self.old); self.assertEqual(self.pw_key(), (new, None))
        self.assertEqual(sorted(self.store.renew_left), bad)             # named (the answer of the renewal, the log)
        after = self.files()
        self.assertEqual({n: after[n] for n in bad}, {n: before[n] for n in bad})          # untouched
        self.assertEqual(sorted(storage.files_not_opening(new, self.dir)), bad)             # everything else opens with the new key
        self.assertEqual(len(storage.files_not_opening(self.old, self.dir)), 5)
        self.assertFalse([n for n in storage._names(self.dir) if n.endswith((".renew", ".tmp", storage.LEFT))])
        self.assertEqual(self.A.unlock_password(self.dir, self.PW), (new, "password"))     # and the next sign-in opens as always
        self.assertEqual(self.A.renew(self.store, self.PW), 3)           # again: named again, never in the way
        self.assertEqual(sorted(self.store.renew_left), bad)
        for n in bad:
            os.remove(os.path.join(self.dir, n))
        self.assertEqual(self.A.renew(self.store, self.PW), 3); self.assertEqual(self.store.renew_left, [])

    def test_broken_off_with_a_file_no_key_opens(self):
        """The Mac goes off while the files change: the next sign-in finishes the renewal by opening every file of the store
        with one of the two keys -- a damaged one would stop that for good, so it is out of the way meanwhile and has its
        name again once someone signed in."""
        bad = self.damage()
        before = self.files()
        real, n = os.replace, [0]

        def off(a, b):
            if a.endswith(".renew"):
                n[0] += 1
                if n[0] > 1:
                    raise OSError("power")
            return real(a, b)
        with mock.patch.object(storage.os, "replace", off):
            with self.assertRaises(storage.StoreError):
                self.A.renew(self.store, self.PW)
        self.assertFalse(self.store.is_open)
        self.assertEqual(sorted(n for n in storage._names(self.dir) if n.endswith(storage.LEFT)), [b + storage.LEFT for b in bad])
        key, how = self.A.unlock_password(self.dir, self.PW)             # the sign-in: finished, not stopped by the damaged files
        self.assertNotEqual(key, self.old); self.assertEqual(self.pw_key(), (key, None))
        self.assertEqual(storage.files_not_opening(key, self.dir), [])
        self.store.unlock(key)
        after = self.files()
        self.assertEqual({n: after[n] for n in bad}, {n: before[n] for n in bad})          # back under their names, untouched
        self.assertFalse([n for n in storage._names(self.dir) if n.endswith(storage.LEFT)])
        self.assertEqual(self.store.load("config.json"), {"a": 1})
        # the key file refuses the next key (Kontor locks, as without a damaged file): the next sign-in opens with the key as
        # it was, and the files have their names again
        with mock.patch.object(storage, "write_key_record", side_effect=storage.StoreError("x")):
            with self.assertRaises(storage.StoreError):
                self.A.renew(self.store, self.PW)
        self.assertFalse(self.store.is_open)
        self.assertEqual(self.A.unlock_password(self.dir, self.PW), (key, "password"))
        self.store.unlock(key)
        self.assertEqual(self.files(), after)
        # a name taken meanwhile is never overwritten
        p = os.path.join(self.dir, "memory-notes-0002.json.enc")
        os.rename(p, p + storage.LEFT)
        self.store.save("memory-notes-0002.json", {"v": 1, "notes": [1]})
        self.store.unlock(key)
        self.assertEqual(self.store.load("memory-notes-0002.json"), {"v": 1, "notes": [1]}); self.assertTrue(os.path.exists(p + storage.LEFT))

    def test_deleted_during_a_renewal_stays_deleted(self):
        """A file deleted while the key is renewed (a saved conversation): the delete waits for the renewal -- before, the
        renewal wrote the file again, with its content."""
        import threading
        inside, go, done = threading.Event(), threading.Event(), threading.Event()
        real_keep = [None]

        def slow_renew():
            rec = storage.key_record(self.dir)

            def keep(old, new):                                           # (as access.renew keeps the next key) -- and waits here
                storage.write_key_record(self.dir, dict(rec, password=storage.password_entry(old, self.PW, nxt=new), touchid=None))
                inside.set(); go.wait(10)
            real_keep[0] = self.store.renew_key(keep, lambda new: storage.write_key_record(self.dir, self.A._promoted(storage.key_record(self.dir))))
        t = threading.Thread(target=slow_renew); t.start()
        self.assertTrue(inside.wait(10))
        d = threading.Thread(target=lambda: (self.store.delete("chats/assistant-chat-aaaaaaaa.json"), done.set())); d.start()
        self.assertFalse(done.wait(0.3))                                  # it waits for the key
        go.set(); t.join(10); d.join(10)
        self.assertTrue(done.is_set()); self.assertEqual(real_keep[0], 3)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "chats", "assistant-chat-aaaaaaaa.json.enc")))      # gone, and stays gone
        self.assertEqual(storage.files_not_opening(self.store.master, self.dir), [])
        self.assertEqual(self.store.load("config.json"), {"a": 1})

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
        self.store.unlock(key)
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
        st = storage.Store(self.dir, self.key)
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
        st.unlock(self.key)
        self.assertTrue(st.is_open)
        self.assertEqual(st.load("config.json"), {"a": 1}); self.assertEqual(st.load("chats/assistant-chat-aaaaaaaa.json"), {"turns": [1]})
        st.close()
        self.assertFalse(st.is_open)
        with self.assertRaises(storage.StoreLocked):
            st.load("config.json")
        self.assertTrue(storage.Store(tempfile.mkdtemp(dir=self.dir), None).is_open)     # without encryption (tests only): open
        self.assertTrue(storage.Store(self.dir, self.key).is_open)

    def test_unlock_needs_a_working_key(self):
        st = storage.Store.closed(self.dir)
        with mock.patch.object(storage, "selftest", lambda k: False):
            with self.assertRaises(storage.StoreError):
                st.unlock(self.key)
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


class DamagedFiles(unittest.TestCase):
    """A file of the store that does not read: the message names it; damaged for good is told apart from what may pass; it can
    be set aside without losing a byte -- and every file is on the disk before it takes its name. Made-up keys only."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-damaged-")
        self.key = os.urandom(32)
        self.st = storage.Store(self.dir, self.key)
        self.st.save("config.json", {"a": 1}); self.st.save("state.json", {"b": 2})

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_message_names_the_file(self):
        p = os.path.join(self.dir, "config.json.enc")
        raw = open(p, "rb").read()
        for broken in (raw[:-7], raw[:40] + bytes([raw[40] ^ 1]) + raw[41:], b"", b"nicht von Kontor"):
            with open(p, "wb") as f:
                f.write(broken)
            self.st._cache.clear()
            with self.assertRaises(storage.StoreDamaged) as e:
                self.st.load("config.json")
            self.assertIn("config.json.enc", str(e.exception)); self.assertEqual(e.exception.name, "config.json")
        self.st.write_bytes("state.json", b"{kein json")
        with self.assertRaises(storage.StoreDamaged) as e:
            self.st.load("state.json")
        self.assertIn("state.json", str(e.exception)); self.assertEqual(e.exception.name, "state.json")
        self.assertTrue(issubclass(storage.StoreDamaged, storage.StoreError))
        # what may pass (openssl does not answer) is not "damaged": nothing is set aside or given up for it
        self.st.save("state.json", {"b": 2}); self.st._cache.clear()
        with mock.patch.object(storage, "_openssl", side_effect=storage.StoreError("openssl")):
            with self.assertRaises(storage.StoreError) as e:
                self.st.load("state.json")
        self.assertNotIsInstance(e.exception, storage.StoreDamaged)

    def test_on_the_disk_before_it_takes_its_name(self):
        """state.json is written every few minutes: synced before the rename, so the Mac going off right after leaves the old
        file or the new one -- never a file with the name and without the content."""
        steps = []
        sync, replace = os.fsync, os.replace
        with mock.patch.object(storage.os, "fsync", lambda fd: steps.append("sync") or sync(fd)), \
                mock.patch.object(storage.os, "replace", lambda a, b: steps.append("name") or replace(a, b)):
            self.st.save("state.json", {"b": 3})
        self.assertEqual(steps, ["sync", "name"])
        self.assertEqual(oct(os.stat(os.path.join(self.dir, "state.json.enc")).st_mode & 0o777), "0o600")
        with mock.patch.object(storage.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.st.save("state.json", {"b": 4})
        self.st._cache.clear()
        self.assertEqual(self.st.load("state.json"), {"b": 3})           # the old one, whole

    def test_set_aside_loses_nothing(self):
        p = os.path.join(self.dir, "config.json.enc")
        raw = open(p, "rb").read()
        kept = self.st.set_aside("config.json")
        self.assertRegex(kept, r"^config\.json\.enc\.damaged-\d{8}-\d{6}$")
        self.assertFalse(os.path.exists(p)); self.assertEqual(open(os.path.join(self.dir, kept), "rb").read(), raw)
        self.assertIsNone(self.st.load("config.json", None)); self.assertIsNone(self.st.set_aside("config.json"))
        self.assertEqual(storage._enc_files(self.dir), ["state.json.enc"])              # no key is asked to open it, none waits for it
        self.assertEqual(storage.files_not_opening(os.urandom(32), self.dir), ["state.json.enc"])
        self.st.save("config.json", {"a": 2})
        again = self.st.set_aside("config.json")                         # within the same second: another name, nothing overwritten
        self.assertNotEqual(again, kept); self.assertEqual(open(os.path.join(self.dir, kept), "rb").read(), raw)
        import service as MA
        for name in (kept, again, "memory-notes-0002.json.enc" + storage.LEFT):          # uninstalling takes them as Kontor's own
            self.assertTrue(MA._KONTOR_FILE.fullmatch(name), name)
        self.assertFalse(MA._KONTOR_FILE.fullmatch("Steuer.pdf.damaged-20260101-000000"))


class BackupReadBack(unittest.TestCase):
    """A backup is a file from outside: each part in the form the program reads it in or the whole file is refused; never a
    waiting category; the access never wider than set on this Mac; nothing books by itself because of it."""

    def setUp(self):
        import service as MA
        self.MA = MA

    def test_every_part_in_its_form_or_none(self):
        P = self.MA.backup_parts
        good = {"plan": {"areas": {"b1": {"horizon_months": 24, "default_method": "rolling12", "inflation_percent_pa": 2.0,
                                           "rows": {"income/Gehalt": {"method": "fix", "amount": 7000.0, "increase_percent_pa": 2.0, "amounts": {"2027-01": 5.0}}},
                                           "loans": {"Darlehen": {"interest_percent_pa": 3.0, "model": "remaining_debt_monthly", "payment": "1500"}},
                                           "appreciation": {"Haus": {"percent_pa": 2.0, "base": "", "share": 1.0, "area": "b2"}},
                                           "events": [{"id": "e1", "text": "Auto", "month": "2027-03", "amount": "-20000,50", "kind": "expense",
                                                       "date_from": None, "after": None, "recurrence": "once", "date_to": None, "active": True}]}}},
                "categories": {"version": 3, "assignment": {}, "rules": [{"id": "g-1", "category": "Wohnen / Miete", "name_is": "vermieter", "source": "learned", "hits": 5, "active": True}],
                               "learned_at": "2026-11-01 10:00", "rule_done": ["x"]},
                "history": {"u1": {"2026-01": 10.5, "2026-02": None}}, "snapshots": {"2026-01": {"u1": 5.0}},
                "receipts": {"entry_list": [{"id": "abc123", "tx_id": 7, "account": "u1", "entity": "b1", "date": "2026-01-02", "amount": -12.5, "name": "Laden",
                                             "path": "2026/x.pdf", "size_bytes": 10, "added": "2026-01-02 10:00", "note": "", "original": "x.pdf"},
                                            {"id": "def456", "tx_id": None, "date": "2026-01-03", "amount": None, "name": "Scan", "path": "/Users/x/Scan.pdf", "external": True}]},
                "mm_history_src": {"as_of": "2026-11-01 10:00", "accounts": {"u1": {"2025-12": 1.0}}, "opening": {"u1": 0.0},
                                   "securities": {"u2": [{"name": "Welt-ETF", "isin": "IE00B4L5Y983", "amounts": {"2025-12": 100.0}}]}},
                "memory": {"v": 1, "notes": []}}
        got = P(good)
        self.assertEqual(sorted(got), ["categories", "history", "mm_history_src", "plan", "receipts", "snapshots"])
        self.assertEqual(P({}), {}); self.assertEqual(P({"plan": None, "snapshots": {}, "receipts": {}, "mm_history_src": {}}), {})
        self.assertNotIn("categories", P({"categories": {"version": 2, "rules": "x" * 3 and []}}))       # another version: as if not there
        self.assertIn("plan", P({"plan": {"areas": {"b1": {"horizon_months": "24", "inflation_percent_pa": "2.5"}}}}))    # what int()/float() read: taken
        odd = {"plan": [5, [], {"areas": []}, {"areas": {"b1": 5}}, {"areas": {"b1": {"horizon_months": "viele"}}}, {"areas": {"b1": {"rows": []}}},
                        {"areas": {"b1": {"rows": {"r": {"amounts": {"2027-01": "x"}}}}}}, {"areas": {"b1": {"rows": {"r": {"increase_percent_pa": None}}}}},
                        {"areas": {"b1": {"events": [1]}}}, {"areas": {"b1": {"events": [{"month": "abcdefg", "amount": 1, "recurrence": "quarterly"}]}}},
                        {"areas": {"b1": {"events": [{"month": "2027-01", "amount": "viel"}]}}}, {"areas": {"b1": {"loans": {"d": {"rate_list": 5}}}}},
                        {"areas": {"b1": {"appreciation": {"h": {"share": None}}}}}, {"areas": {"b1": {"inflation_percent_pa": float("nan")}}}],
               "categories": [5, {"version": 3, "rules": {}}, {"version": 3, "rules": [1]}, {"version": 3, "rules": [{"iban": ["x"]}]},
                              {"version": 3, "rules": [{"purpose_contains": 5}]}, {"version": 3, "assignment": []}, {"version": 3, "rule_done": [1]}],
               "history": [5, {"u": 5}, {"u": {"2026-13": 1}}, {"u": {"2026-01": "1"}}, {"u": {"0000-01": 1}}, {"u": {"2026-01": True}}],
               "snapshots": [[1], {"2026-01": 5}, {"2026-01": {"u": None}}, {"x": {"u": 1}}, {"2026-01": {"u": "1"}}],
               "receipts": [[1], {"entry_list": [1]}, {"entry_list": {}}, {"entry_list": [{"id": "a"}]}, {"entry_list": [{"id": "a", "path": "x.pdf", "tx_id": [1]}]},
                            {"entry_list": [{"id": 5, "path": "x.pdf"}]}, {"entry_list": [{"id": "a", "path": "x.pdf", "date": 5}]},
                            {"entry_list": [{"id": "a", "path": "x.pdf", "amount": "12"}]}],
               "mm_history_src": [[1], {"accounts": []}, {"accounts": {"u": 5}}, {"accounts": {"u": {"2026-01": "x"}}}, {"opening": {"u": "x"}},
                                  {"securities": {"u": {}}}, {"securities": {"u": [5]}}, {"securities": {"u": [{"amounts": {"x": 1}}]}}],
               "memory": [5, {"notes": 5}, []]}
        for part, cases in odd.items():
            for bad in cases:
                with self.assertRaises(ValueError, msg=(part, bad)) as e:
                    P(dict(good, **{part: bad}))
                self.assertIn("nichts wurde geändert", str(e.exception))
        self.assertIn("Belegindex", self._why(P, dict(good, receipts={"entry_list": [1]}))); self.assertIn("Verlauf", self._why(P, dict(good, snapshots={"2026-01": 5})))

    def _why(self, fn, arg):
        with self.assertRaises(ValueError) as e:
            fn(arg)
        return str(e.exception)

    def test_the_settings_in_their_form_or_none(self):
        """A part of the settings that should be a list or a table and is not (areas: "kaputt"): the whole file is refused before
        anything is written -- not taken with the areas emptied."""
        class App:
            config = {"areas": [{"id": "b1", "name": "Privat", "accounts": []}]}
        for bad in ({"areas": "kaputt"}, {"loans": {}}, {"cashflow": []}, {"companies": 5}):          # (ui, receipts, updates: as this Mac has them)
            with self.assertRaises(ValueError, msg=bad) as e:
                self.MA.restore_backup(App(), {"config": bad})
            self.assertIn("Einstellungen", str(e.exception)); self.assertIn("nichts wurde geändert", str(e.exception))

    def test_a_waiting_category_never_comes_back(self):
        got = self.MA.backup_parts({"categories": {"version": 3, "assignment": {"4711": {"k": "Wohnen / Miete", "q": "manual", "p": 1}},
                                                   "rules": [], "learned_at": None, "_idx": 5}})
        self.assertEqual(got["categories"], {"version": 3, "rules": [], "learned_at": None})

    def test_the_rounds_a_file_names_are_bounded(self):
        """A backup names its own rounds for its password: one made up must not keep the service computing for minutes."""
        import hashlib
        good = self.MA.backup_encrypt({"kontor_backup": 1, "config": {}}, "sicherung-123")
        self.assertEqual(self.MA.backup_decrypt(good, "sicherung-123")["kontor_backup"], 1)
        self.assertEqual(self.MA.backup_decrypt({k: v for k, v in good.items() if k != "iter"}, "sicherung-123")["kontor_backup"], 1)
        calls = []
        with mock.patch.object(hashlib, "pbkdf2_hmac", side_effect=lambda *a: calls.append(a[3]) or b"\0" * 32):
            for rounds in (2_000_000_000, 10 ** 30, 1, -5, 99_999, 600000.0, "600000", True, [600000], {"x": 1}):
                with self.assertRaises(ValueError, msg=rounds):
                    self.MA.backup_decrypt(dict(good, iter=rounds), "sicherung-123")
        self.assertEqual(calls, [])                                       # refused before anything was computed
        for odd in ({"salt": 5}, {"data": None}, {"salt": "kein base64!"}):
            with self.assertRaises(ValueError):
                self.MA.backup_decrypt(dict(good, **odd), "sicherung-123")

    def test_the_access_never_gets_wider(self):
        R = self.MA.restored_config
        here = {"ui": {"touchid": False, "remote_read_only": True, "lock_minutes": 10, "offline_copy": False, "bind": "127.0.0.1", "port": 8765,
                       "tls_cert": "", "tls_key": "", "language": "de"}, "dry_run": True}
        wide = {"ui": {"touchid": True, "remote_read_only": False, "lock_minutes": 100000, "offline_copy": True, "bind": "100.101.102.103", "port": 9999,
                       "tls_cert": "/x/a.crt", "tls_key": "/x/a.key", "language": "en", "theme": "dark"}, "dry_run": False}
        ui = R(here, wide)["ui"]
        self.assertEqual({k: ui.get(k) for k in here["ui"]}, dict(here["ui"], language="en"))       # the access as here; how it looks from the file
        self.assertEqual(ui["theme"], "dark")
        # the other way round: where the file is stricter, the stricter one holds
        open_ = {"ui": {"touchid": True, "remote_read_only": False, "lock_minutes": 60, "offline_copy": True, "bind": "100.101.102.103", "port": 9000,
                        "tls_cert": "/d/tls/a.crt", "tls_key": "/d/tls/a.key"}}
        strict = {"ui": {"touchid": False, "remote_read_only": True, "lock_minutes": 5, "offline_copy": False, "bind": "127.0.0.1", "port": 8765}}
        ui = R(open_, strict)["ui"]
        self.assertEqual((ui["touchid"], ui["remote_read_only"], ui["lock_minutes"], ui["offline_copy"], ui["bind"]), (False, True, 5, False, "127.0.0.1"))
        self.assertEqual((ui["port"], ui["tls_cert"], ui["tls_key"]), (9000, "/d/tls/a.crt", "/d/tls/a.key"))       # port and certificate: this Mac's
        # nothing said, or something odd: as here -- only "from elsewhere only look" counts as said (it is so from the factory)
        for said in ({}, {"ui": None}, {"ui": [["bind", "0.0.0.0"]]}, {"ui": {"touchid": "nein", "lock_minutes": "5", "offline_copy": 0, "bind": 5, "remote_read_only": "x"}},
                     {"ui": {"lock_minutes": 0}}, {"ui": {"lock_minutes": -3}}, {"ui": {"lock_minutes": True}}, {"ui": {"lock_minutes": 61}}):
            ui = R(open_, said)["ui"]
            self.assertEqual({k: ui.get(k) for k in open_["ui"] if k != "remote_read_only"}, {k: v for k, v in open_["ui"].items() if k != "remote_read_only"}, said)
        self.assertTrue(R(open_, {})["ui"]["remote_read_only"])
        self.assertFalse(R(open_, {"ui": {"remote_read_only": False}})["ui"]["remote_read_only"])      # both say so: stays
        self.assertNotIn("touchid", R({}, {"ui": {"touchid": True}})["ui"])                            # (nothing set here: the factory's)

    def test_nothing_books_by_itself_because_of_a_backup(self):
        """Booking without asking is on at this Mac: a rule of the file that is not here already waits for the confirmation
        under Konten & Regeln (review, like a rule from the assistant), and what is set here not to be booked stays so."""
        R = self.MA.restored_config
        loan = {"name": "Darlehen", "loan_account": "u1 | D", "source_accounts": ["u2 | K"], "from_date": "2026-01-01"}
        mine = {"dry_run": False, "loans": [loan], "companies": [{"area": "b2", "participation": "u3 | B"}],
                "account_mirrors": [{"a": "u4", "b": "u5", "from_date": ""}], "not_book": [{"key": "u1|#kontor-z-2026-01", "text": "Zins"}]}
        file = {"dry_run": False, "loans": [dict(loan, active=True), dict(loan, name="Neu", loan_account="u9 | N")],
                "companies": [{"area": "b2", "participation": "u3 | B", "threshold": 500}], "account_mirrors": [{"a": "u4", "b": "u5", "from_date": ""}, {"a": "u6", "b": "u7"}],
                "not_book": [{"key": "u8|#kontor-z-2026-02", "text": "x"}, "odd"]}
        got = R(mine, file)
        self.assertFalse(got["dry_run"])
        self.assertEqual([bool(r.get("review")) for r in got["loans"]], [False, True])                # the same rule: as it was; a new one waits
        self.assertEqual([bool(r.get("review")) for r in got["companies"]], [True])                   # changed: waits
        self.assertEqual([bool(r.get("review")) for r in got["account_mirrors"]], [False, True])
        self.assertEqual(sorted(x["key"] for x in got["not_book"]), ["u1|#kontor-z-2026-01", "u8|#kontor-z-2026-02"])
        self.assertTrue(all(r.get("review") is True for sec in ("loans", "companies", "account_mirrors") for r in self.MA.merged_config(got)[sec] if r.get("review")))
        # a rule still to confirm here (from the assistant): the file has it without the mark -- still to confirm
        got = R(dict(mine, loans=[dict(loan, review=True)]), file)
        self.assertEqual([bool(r.get("review")) for r in got["loans"]], [True, True])
        # asking first (here, or because the file says so): everything waits for you anyway -- nothing is marked
        for a, b in ((dict(mine, dry_run=True), file), (mine, dict(file, dry_run=True))):
            got = R(a, b)
            self.assertTrue(got["dry_run"]); self.assertFalse(any(r.get("review") for sec in ("loans", "companies", "account_mirrors") for r in got[sec]))
        for odd in ({"loans": "x", "not_book": 5}, {"loans": [1, None], "companies": {"a": 1}}):       # the wrong kind of value: no error
            self.assertFalse(R(mine, dict(file, **odd))["dry_run"])


class CommandLine(unittest.TestCase):
    """kontor.py in the terminal: only these commands, the password only with the current one (or Touch ID), uninstall goes
    on when the settings are damaged (and takes the demo's folder), install waits until the service may run."""

    def setUp(self):
        import kontor
        self.K, self.dir = kontor, tempfile.mkdtemp(prefix="kontor-cli-")
        self._old = kontor.DATA_DIR
        kontor.DATA_DIR = self.dir

    def tearDown(self):
        self.K.DATA_DIR = self._old
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_password_with_the_key_file(self):
        """kontor.py password once the key file holds the key: the current password (or Touch ID) opens it, the new one wraps it
        -- the data key stays the same, the old password opens nothing any more."""
        import argparse
        import access
        key = os.urandom(32)
        storage.Store(self.dir, key).save("config.json", {})
        self.assertTrue(access.complete(self.dir, key, "altes-passwort-123"))
        opens = lambda pw: access.unlock_password(self.dir, pw)
        offline = lambda: storage.Store(self.dir, key).load("auth.json")          # the iPhone's check value follows the password
        with mock.patch.object(self.K.time, "sleep"):
            with mock.patch.object(self.K.getpass, "getpass", side_effect=["falsch"] * 3):
                self.assertEqual(self.K.cmd_passwort(argparse.Namespace()), 1)
            self.assertEqual(opens("altes-passwort-123"), (key, "password")); self.assertIsNone(offline())
            with mock.patch.object(self.K.getpass, "getpass", side_effect=["altes-passwort-123", "neues-passwort-456", "neues-passwort-456"]):
                self.assertEqual(self.K.cmd_passwort(argparse.Namespace()), 0)
        self.assertIsNone(opens("altes-passwort-123")); self.assertEqual(opens("neues-passwort-456"), (key, "password"))
        self.assertTrue(offline()["offline"])
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

    def _uninstall(self, program):
        """cmd_uninstall with a made-up program folder, launchd file and temporary folder (never this Mac's own)."""
        import argparse
        import contextlib
        import io
        import service as MA
        out = io.StringIO()
        with mock.patch.object(self.K, "HERE", self.prog), mock.patch.object(MA.updates, "plist_path", lambda label=MA.updates.LABEL: os.path.join(self.prog, "none.plist")), \
                mock.patch.object(tempfile, "tempdir", self.tmp), mock.patch.object(self.K.getpass, "getpass", return_value=self.PW), \
                mock.patch.object(self.K.time, "sleep"), contextlib.redirect_stdout(out):
            code = self.K.cmd_uninstall(argparse.Namespace(yes=True, program=program))
        return code, out.getvalue()

    PW = "ein-langes-passwort"

    def _installed(self):
        import access
        self.prog, self.tmp = tempfile.mkdtemp(prefix="kontor-prog-"), tempfile.mkdtemp(prefix="kontor-tmp-")
        self.addCleanup(shutil.rmtree, self.prog, True); self.addCleanup(shutil.rmtree, self.tmp, True)
        for f in ("kontor.py", "service.py", "VERSION"):
            open(os.path.join(self.prog, f), "w").close()
        os.makedirs(os.path.join(self.prog, "Belege")); open(os.path.join(self.prog, "Belege", "Rechnung.pdf"), "w").close()      # receipts kept in the program folder
        key = os.urandom(32)
        st = storage.Store(self.dir, key)
        st.save("config.json", {"receipts": {"folder": os.path.join(self.prog, "Belege")}}); st.save("state.json", {"b": 1})
        self.assertTrue(access.complete(self.dir, key, self.PW))
        return st

    def test_uninstall_goes_on_when_the_settings_are_damaged(self):
        """config.json.enc damaged for good (the key is right: it opens the state): uninstalling must still be possible --
        before, it stopped with "nothing is deleted" and there was no way left. Only the program folder stays then: receipts
        or linked documents may lie in it, and the settings would have said where."""
        st = self._installed()
        p = st.path("config.json")
        raw = open(p, "rb").read()
        with open(p, "wb") as f:
            f.write(raw[:-5])
        code, out = self._uninstall(program=True)
        self.assertEqual(code, 0, out)
        self.assertFalse([n for n in os.listdir(self.dir) if n.endswith(".enc")] if os.path.isdir(self.dir) else [])
        self.assertFalse(os.path.exists(os.path.join(self.dir, storage.KEY_FILE)))            # the key went with the data
        self.assertTrue(os.path.exists(os.path.join(self.prog, "kontor.py"))); self.assertTrue(os.path.exists(os.path.join(self.prog, "Belege", "Rechnung.pdf")))
        self.assertIn(self.K.tr("s_deinstall_programm_bleibt"), out)

    def test_uninstall_with_settings_that_are_no_settings(self):
        st = self._installed()
        st.write_bytes("config.json", b"{kaputt")
        code, out = self._uninstall(program=False)
        self.assertEqual(code, 0, out); self.assertFalse(os.path.exists(st.path("config.json")))
        self.assertNotIn(self.K.tr("s_deinstall_programm_bleibt"), out)                   # (nobody asked for the program folder)

    def test_uninstall_stops_when_the_settings_cannot_be_read_right_now(self):
        """What may pass (openssl does not answer, the disk) is not "damaged": nothing is deleted, the next try works."""
        st = self._installed()
        with mock.patch.object(storage, "_openssl", side_effect=storage.StoreError("openssl")):
            code, out = self._uninstall(program=True)
        self.assertEqual(code, 1)
        self.assertTrue(os.path.exists(st.path("config.json"))); self.assertTrue(os.path.exists(os.path.join(self.dir, storage.KEY_FILE)))
        self.assertTrue(os.path.exists(os.path.join(self.prog, "kontor.py")))

    def test_uninstall_takes_the_demo_folder(self):
        """The demo's folder lies in the temporary folder (receipts uploaded in it are not encrypted); only the service removed
        it, at its own end or its next start -- uninstalling from the terminal left it there."""
        self._installed()
        demo = os.path.join(self.tmp, "kontor-demo-abc123")
        os.makedirs(os.path.join(demo, "Belege")); open(os.path.join(demo, "Belege", "Beleg.pdf"), "w").close()
        other = os.path.join(self.tmp, "etwas-anderes"); os.makedirs(other)
        code, out = self._uninstall(program=True)
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(demo)); self.assertTrue(os.path.exists(other))
        self.assertFalse(os.path.exists(os.path.join(self.prog, "kontor.py")))            # settings read: the program folder goes as asked ...
        self.assertTrue(os.path.exists(os.path.join(self.prog, "Belege", "Rechnung.pdf")))     # ... and the receipts in it stay

    def test_uninstall_stops_without_the_key_file(self):
        """Encrypted data without their key file (nothing to confirm with): nothing is deleted."""
        import argparse
        st = self._installed()
        os.remove(os.path.join(self.dir, storage.KEY_FILE))
        self.assertEqual(self.K.cmd_uninstall(argparse.Namespace(yes=True, program=False)), 1)
        self.assertTrue(os.path.exists(st.path("config.json")))

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


class LinkedFilesOpenAsDocuments(unittest.TestCase):
    """A linked file opens in its own app only when it is a document (service.DOCUMENTS); a page, a script, a program, an
    archive or anything that only looks like a document is shown in Finder, never opened (3.16.61)."""

    def test_only_documents_open(self):
        import service
        d = tempfile.mkdtemp(prefix="kontor-doc-")
        self.addCleanup(shutil.rmtree, d, True)
        made = {}
        for name in ("Rechnung.pdf", "Auszug.CSV", "Seite.html", "Start.command", "run.sh", "Archiv.zip", "Werkzeug.py", "Notiz"):
            made[name] = os.path.join(d, name)
            with open(made[name], "w") as f:
                f.write("x")
        made["Programm.app"] = os.path.join(d, "Programm.app"); os.makedirs(os.path.join(made["Programm.app"], "Contents"))
        made["Beleg.pdf.app"] = os.path.join(d, "Beleg.pdf.app"); os.makedirs(made["Beleg.pdf.app"])
        made["Tabelle.numbers"] = os.path.join(d, "Tabelle.numbers"); os.makedirs(made["Tabelle.numbers"])      # a package: a folder
        calls = []
        with mock.patch.object(service.subprocess, "Popen", side_effect=lambda cmd, *a, **k: calls.append(cmd)):
            for name, path in sorted(made.items()):
                calls.clear()
                service.open_document(path)
                opened = calls == [["open", os.path.abspath(path)]]
                self.assertEqual(opened, name in ("Rechnung.pdf", "Auszug.CSV"), (name, calls))
                if not opened:
                    self.assertEqual(calls, [["open", "-R", os.path.abspath(path)]], name)       # shown in its folder, selected


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
                                                                                      # (also a question to Claude, Anthropic's interface: your own key, a card every time)
        "pyselftest.py": {"ssl"},                                      # tries a Python before Kontor runs in it: are the certificates for https there? Connects nowhere
    }
    NETWORK_MODULES = {"socket", "ssl", "http.client", "http.server", "urllib.request", "socketserver", "ftplib", "smtplib", "poplib", "imaplib",
                       "telnetlib", "nntplib", "xmlrpc", "asyncio", "selectors", "webbrowser", "requests", "httpx", "aiohttp", "urllib3", "websocket",
                       "websockets", "paramiko", "pycurl"}
    # hosts written in the program: the ones it connects to, by part ...
    HOSTS = {"updates.py": {"api.github.com", "github.com", "raw.githubusercontent.com"},
             "llm_local.py": {"api.github.com", "huggingface.co"},
             "pyruntime.py": {"github.com"},                # Kontor's own Python: the one file named there, on your click (over llm_local's checked way)
             "security_names.py": {"api.openfigi.com"},
             # the consumer price index for the balance sheet in today's money: newer months from the Bundesbank, through the
             # internet search's sealed reader, only while the switch is on (price_index.py opens no connection itself)
             "price_index.py": {"api.statistiken.bundesbank.de"},
             # the internet search's sources (each fetch after your click; the reader checks the host again) -- and, named only:
             # the program's page (in its User-Agent), the ECB's and GLEIF's pages that results link to
             "web_search.py": {"www.wikidata.org", "www.gesetze-im-internet.de", "api.gleif.org", "data-api.ecb.europa.eu", "api.statistiken.bundesbank.de",
                               "ec.europa.eu", "www.tagesschau.de", "api.gdeltproject.org", "api.tavily.com", "data.ecb.europa.eu", "search.gleif.org",
                               "testphase.rechtsinformationen.bund.de", "www.bundesfinanzministerium.de", "www.bundesbank.de", "www.ecb.europa.eu",
                               "sdmx.oecd.org", "api.worldbank.org", "data.worldbank.org", "stats.bis.org",
                               "api.anthropic.com"},              # a question to Claude (tier 4): only with your own API key, asked on a card every time
             # ... the one address the reader itself holds: the only place your key for Claude is ever sent to (web_reader.ask_claude)
             "web_reader.py": {"api.anthropic.com"}}
    NAMES_ONLY = {"schemas.openxmlformats.org", "purl.oclc.org", "www.apple.com"}      # ... and names of file formats (never opened)
    # other programs started by their name (all of macOS or Apple's tools, git for an update of a clone)
    COMMANDS = {"openssl", "swiftc", "codesign", "open", "launchctl", "/bin/launchctl", "/usr/sbin/sysctl", "ps", "pgrep", "tmutil",
                "osascript", "/usr/bin/osascript", "xcode-select", "git", "/bin/sh",
                "sips", "iconutil", "defaults", "tccutil",          # Kontor's own Mac app: its icon, its address, gone on uninstall
                "/usr/bin/xattr", "/usr/bin/codesign"}              # Kontor's own Python, unpacked: the mark for files from the internet off, signed on this Mac if need be
    # ... and by a path Kontor made up itself (its Touch ID helper, the password window, llama.cpp, Tailscale's own tool, lsof, the receipt reader, the web reader)
    COMMANDS_BY_PATH = {"auth.py", "mm_history.py", "llm_local.py", "tls_cert.py", "receipt_text.py", "web_search.py",     # receipt_text: its text recognition, sealed; web_search: python3 -I web_reader.py (in the sandbox)
                        "pyboot.py", "pyruntime.py"}        # Kontor's own Python, only from inside .python/ in the program folder: the starter runs the service in it; a build is tried before
    # where links on the pages lead (opened by you, in a new window; the pages themselves only talk to Kontor)
    LINKS = {"github.com", "tailscale.com", "login.tailscale.com", "apps.apple.com", "www.w3.org",
             "huggingface.co"}             # Einstellungen -> Updates, "Verwendete Programme": the page of a model, where its licence stands
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
        import price_index                                               # the price index: one fixed address, GET, nothing of yours
        req = price_index.request()
        self.assertEqual((price_index.HOST, req["hosts"], req["method"], req["as"], urlparse(req["url"]).hostname, urlparse(req["url"]).scheme),
                         ("api.statistiken.bundesbank.de", ["api.statistiken.bundesbank.de"], "GET", "csv", "api.statistiken.bundesbank.de", "https"))
        self.assertEqual(req["url"], price_index.URL % price_index.add(price_index.BUNDLED_LAST, -price_index.BACK))
        self.assertEqual((req["headers"], req["user_agent"]), ({}, web_search.NEUTRAL_AGENT))
        self.assertEqual({s: set(v["hosts"]) for s, v in web_search.SOURCES.items()},
                         {"wikipedia": {"de.wikipedia.org", "en.wikipedia.org"}, "wikidata": {"www.wikidata.org"}, "laws": {"www.gesetze-im-internet.de"},
                          "gleif": {"api.gleif.org"}, "ecb": {"data-api.ecb.europa.eu"}, "bundesbank": {"api.statistiken.bundesbank.de"}, "eurostat": {"ec.europa.eu"},
                          "ris": {"testphase.rechtsinformationen.bund.de"}, "feeds": {"www.bundesfinanzministerium.de", "www.bundesbank.de", "www.ecb.europa.eu"},
                          "oecd": {"sdmx.oecd.org"}, "worldbank": {"api.worldbank.org"}, "bis": {"stats.bis.org"},
                          "tagesschau": {"www.tagesschau.de"}, "gdelt": {"api.gdeltproject.org"}, "tavily": {"api.tavily.com"},
                          "claude": {"api.anthropic.com"}})
        # a question to Claude: one address, written the same on both sides -- the reader sends your key there and nowhere else, and
        # Claude is never among what goes without a card
        import web_reader
        self.assertEqual((web_search.CLAUDE_URL, web_reader.CLAUDE, sorted(web_reader.POST_ONLY)), ("https://api.anthropic.com/v1/messages",) * 2 + (["api.anthropic.com", "api.tavily.com"],))
        self.assertEqual(web_reader.POST_ONLY["api.anthropic.com"], ("/v1/messages",))
        self.assertIn("claude", web_search.ASKED_ALWAYS)
        self.assertNotIn("claude", web_search.trusted_default()["sources"])
        self.assertNotIn("claude", web_search.trusted({"sources": list(web_search.SOURCES)})["sources"])
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
                    while isinstance(first, ast.BinOp):                  # ["openssl", "enc"] + opts
                        first = first.left
                    if isinstance(first, ast.IfExp):                     # ["open", "-R", x] if ... else ["open", x]
                        first = first.body
                    if isinstance(first, ast.List) and first.elts and isinstance(first.elts[0], ast.Constant):
                        names.add(first.elts[0].value)
                    else:
                        by_path.add(name)
                elif (base == "os" and (attr in ("system", "popen") or attr.startswith(("spawn", "posix_spawn")))) or (not base and attr in ("eval", "exec", "__import__")) \
                        or base == "importlib" or (base == "os" and attr.startswith("exec") and name not in ("service.py", "pyboot.py")):      # (both: themselves anew)
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
