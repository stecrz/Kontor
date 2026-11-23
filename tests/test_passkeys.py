"""Access from an iPhone with its own passkey (webauthn.py, devices.py, qr.py, service.py): the strict readers (CBOR, COSE, DER),
ECDSA on P-256 against fixed vectors, registration and sign-in with a software authenticator written here -- and every way it
must fail; the one-time pairing link and challenges; over HTTP: adding an iPhone, signing in with Face ID, each change confirmed
for exactly that request, what stays at the Mac, a removed device, the data locked after a restart, the demo."""
import copy
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import webauthn as W  # noqa: E402
import devices as D  # noqa: E402
import qr  # noqa: E402

RP = "kontor-mac.tail0000.ts.net"           # made up
PORT = 8765
ORIGIN = "https://%s:%d" % (RP, PORT)


# -- a small CBOR writer (tests only) ---------------------------------------------------------------------------------------
def cbor(v) -> bytes:
    def head(major, n):
        if n < 24:
            return bytes([major << 5 | n])
        for info, size in ((24, 1), (25, 2), (26, 4), (27, 8)):
            if n < 1 << (8 * size):
                return bytes([major << 5 | info]) + n.to_bytes(size, "big")
        raise ValueError(n)
    if v is False or v is True or v is None:
        return bytes([0xF4 + (1 if v is True else 2 if v is None else 0)])
    if isinstance(v, int):
        return head(0, v) if v >= 0 else head(1, -1 - v)
    if isinstance(v, bytes):
        return head(2, len(v)) + v
    if isinstance(v, str):
        b = v.encode("utf-8")
        return head(3, len(b)) + b
    if isinstance(v, list):
        return head(4, len(v)) + b"".join(cbor(x) for x in v)
    if isinstance(v, dict):
        return head(5, len(v)) + b"".join(cbor(k) + cbor(x) for k, x in v.items())
    raise TypeError(v)


def der(r: int, s: int) -> bytes:
    def i(x):
        b = x.to_bytes((x.bit_length() + 8) // 8, "big")
        return b"\x02" + bytes([len(b)]) + b
    body = i(r) + i(s)
    return b"\x30" + bytes([len(body)]) + body


def scalar_mult(k: int, point=W.G):
    return W._affine(W._mul2(k, point, 0, point))


class SoftKey:
    """A software passkey (tests only): what an iPhone does after Face ID."""

    def __init__(self, rp=RP, origin=ORIGIN, count_step=0):
        self.rp, self.origin, self.step = rp, origin, count_step
        self.d = secrets.randbelow(W.N - 1) + 1
        self.x, self.y = scalar_mult(self.d)
        self.cred = secrets.token_bytes(20)
        self.count = 0

    def cose(self):
        return {1: 2, 3: -7, -1: 1, -2: self.x.to_bytes(32, "big"), -3: self.y.to_bytes(32, "big")}

    def client_data(self, kind, challenge, **extra):
        cd = {"type": kind, "challenge": W.b64u(challenge), "origin": self.origin, "crossOrigin": False}
        cd.update(extra)
        return json.dumps(cd).encode()

    def auth_data(self, flags=W.UP | W.UV, attested=False, rp=None, count=None, cose=None, extra=b""):
        ad = hashlib.sha256((rp or self.rp).encode()).digest() + bytes([flags | (W.AT if attested else 0)]) + (self.count if count is None else count).to_bytes(4, "big")
        if attested:
            ad += bytes(16) + len(self.cred).to_bytes(2, "big") + self.cred + cbor(cose if cose is not None else self.cose())
        return ad + extra

    def create(self, challenge, **kw):
        cdj = self.client_data("webauthn.create", challenge)
        att = cbor({"fmt": "none", "attStmt": {}, "authData": self.auth_data(attested=True, **kw)})
        return cdj, att

    def sign(self, msg: bytes, low_s=False):
        e = int.from_bytes(hashlib.sha256(msg).digest(), "big")
        while True:
            k = secrets.randbelow(W.N - 1) + 1
            r = scalar_mult(k)[0] % W.N
            s = pow(k, W.N - 2, W.N) * (e + r * self.d) % W.N
            if r and s:
                return r, s

    def get(self, challenge, flags=W.UP | W.UV, cdj=None, ad=None):
        self.count += self.step
        cdj = cdj or self.client_data("webauthn.get", challenge)
        ad = ad if ad is not None else self.auth_data(flags=flags)
        r, s = self.sign(ad + hashlib.sha256(cdj).digest())
        return cdj, ad, der(r, s)


class Base64Url(unittest.TestCase):
    def test_strict(self):
        self.assertEqual(W.b64u_decode(W.b64u(b"\x00\xff\x10")), b"\x00\xff\x10")
        for bad in ("ab=", "a+b", "a/b", "a", "ab c", "AB" * 3000, None, 12, "QR"):          # "QR": stray bits
            with self.assertRaises(W.Invalid, msg=repr(bad)[:20]):
                W.b64u_decode(bad)


class Cbor(unittest.TestCase):
    def test_reads_what_authenticators_send(self):
        v = {"fmt": "none", "attStmt": {}, "authData": b"\x01" * 40, 1: -7, -3: [True, False, None], "n": 70000}
        self.assertEqual(W.cbor_decode(cbor(v)), v)

    def test_refuses_anything_else(self):
        for name, data in (("indefinite map", b"\xbf\x61a\x01\xff"), ("indefinite bytes", b"\x5f\x41a\xff"), ("tag", b"\xc2\x41\x01"),
                           ("float", b"\xfa\x3f\x80\x00\x00"), ("simple 16", b"\xf0"), ("not shortest 1", b"\x18\x05"),
                           ("not shortest 2", b"\x19\x00\x10"), ("not shortest 4", b"\x1a\x00\x00\xff\xff"), ("reserved", b"\x1c"),
                           ("duplicate key", b"\xa2\x01\x01\x01\x02"), ("bool key", b"\xa1\xf5\x01"), ("bytes key", b"\xa1\x41a\x01"),
                           ("bad utf-8", b"\x62\xc3\x28"), ("short", b"\x43ab"), ("trailing", b"\x01\x02"), ("empty", b""),
                           ("too deep", b"\x81" * 6 + b"\x01"), ("too many", b"\x98\x21" + b"\x01" * 33), ("huge length", b"\x5b" + b"\xff" * 8),
                           ("too large", cbor(b"x" * 5000))):
            with self.subTest(name), self.assertRaises(W.Invalid):
                W.cbor_decode(data)


class Ecdsa(unittest.TestCase):
    # RFC 6979, A.2.5: ECDSA, 256 bits (prime field), SHA-256
    D = 0xC9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721
    UX = 0x60FED4BA255A9D31C961EB74C6356D68C049B8923B61FA6CE669622E60F29FB6
    UY = 0x7903FE1008B8BC99A41AE9E95628BC64F2F1B20C2D7E9F5177A3C294D4462299
    VECTORS = ((b"sample", 0xEFD48B2AACB6A8FD1140DD9CD45E81D69D2C877B56AAF991C34D0EA84EAF3716, 0xF7CB1C942D657C41D436C7A1B6E29F65F3E900DBB9AFF4064DC4AB2F843ACDA8),
               (b"test", 0xF1ABB023518351CD71D881567B1EA663ED3EFCF6C5132B354F28D3B0B7D38367, 0x019F4113742A2B14BD25926B49C649155F267E60D3814B4C0CC84250E46F0083))

    def test_rfc6979_vectors(self):
        self.assertEqual(scalar_mult(self.D), (self.UX, self.UY))
        self.assertTrue(W.on_curve(*W.G) and W.on_curve(self.UX, self.UY))
        for msg, r, s in self.VECTORS:
            h = hashlib.sha256(msg).digest()
            self.assertTrue(W.ecdsa_verify(self.UX, self.UY, h, r, s))
            self.assertEqual(W.der_signature(der(r, s)), (r, s))
            self.assertFalse(W.ecdsa_verify(self.UX, self.UY, hashlib.sha256(msg + b".").digest(), r, s))       # another message
            self.assertFalse(W.ecdsa_verify(self.UX, self.UY, h, r, (s + 1) % W.N))
            self.assertFalse(W.ecdsa_verify(self.UX, self.UY, h, r ^ 1, s))
            self.assertFalse(W.ecdsa_verify(self.UX, (self.UY + 1) % W.P, h, r, s))             # off the curve
            self.assertFalse(W.ecdsa_verify(self.UX, W.P - self.UY, h, r, s))                   # the other point with this x
            for rr, ss in ((0, s), (r, 0), (W.N, s), (r, W.N), (r + W.N, s), (-r, s)):
                self.assertFalse(W.ecdsa_verify(self.UX, self.UY, h, rr, ss))

    def test_software_key_and_curve_edges(self):
        k = SoftKey()
        for _ in range(5):
            msg = secrets.token_bytes(50)
            r, s = k.sign(msg)
            self.assertTrue(W.ecdsa_verify(k.x, k.y, hashlib.sha256(msg).digest(), r, s))
            self.assertTrue(W.ecdsa_verify(k.x, k.y, hashlib.sha256(msg).digest(), r, W.N - s))      # (ECDSA: s and n - s both hold)
        self.assertFalse(W.on_curve(0, 0)); self.assertFalse(W.on_curve(W.P, 0)); self.assertFalse(W.on_curve(True, 1))
        self.assertFalse(W.ecdsa_verify(W.G[0], W.G[1], b"\x00" * 31, 1, 1))                   # a digest of another length

    def test_der_strict(self):
        r, s = self.VECTORS[0][1:]
        good = der(r, s)
        bad = {"long form length": b"\x30\x81" + bytes([len(good) - 2]) + good[2:], "wrong total": good[:1] + bytes([good[1] + 1]) + good[2:],
               "trailing": good + b"\x00", "not integer": good[:2] + b"\x03" + good[3:], "negative": der(r, s)[:4] + b"\x80" + der(r, s)[5:],
               "padded": b"\x30\x08\x02\x02\x00\x01\x02\x02\x00\x01", "zero r": der(0, s), "r = n": der(W.N, s), "empty": b"",
               "too long": b"\x30\x48" + b"\x02\x22" + b"\x00" * 34 + b"\x02\x22" + b"\x00" * 34}
        for name, sig in bad.items():
            with self.subTest(name), self.assertRaises(W.Invalid):
                W.der_signature(sig)


class Cose(unittest.TestCase):
    def test_only_es256_p256_with_five_fields(self):
        k = SoftKey()
        self.assertEqual(W.cose_es256(k.cose()), (k.x, k.y))
        for name, change in (("RS256", {3: -257}), ("EdDSA kty", {1: 1}), ("P-384", {-1: 2}), ("short x", {-2: b"\x01" * 31}),
                             ("x as int", {-2: 5}), ("bool kty", {1: True}), ("off curve", {-3: ((k.y + 1) % W.P).to_bytes(32, "big")}),
                             ("extra field", {4: b"k"}), ("x too big", {-2: W.P.to_bytes(32, "big")})):
            key = k.cose(); key.update(change)
            with self.subTest(name), self.assertRaises(W.Invalid):
                W.cose_es256(key)
        key = k.cose(); key.pop(-3)
        with self.assertRaises(W.Invalid):
            W.cose_es256(key)


class Registration(unittest.TestCase):
    def setUp(self):
        self.k, self.ch = SoftKey(), secrets.token_bytes(32)

    def reg(self, cdj, att, ch=None, origin=ORIGIN, rp=RP):
        return W.verify_registration(cdj, att, ch or self.ch, origin, rp)

    def test_a_new_passkey(self):
        got = self.reg(*self.k.create(self.ch))
        self.assertEqual((got["cred_id"], got["x"], got["y"], got["count"]), (self.k.cred, self.k.x, self.k.y, 0))
        cdj, _ = self.k.create(self.ch)                                                # backed up in iCloud (BE, BS): fine
        att = cbor({"fmt": "none", "attStmt": {}, "authData": self.k.auth_data(flags=W.UP | W.UV | W.BE | W.BS, attested=True)})
        self.assertEqual(self.reg(cdj, att)["cred_id"], self.k.cred)
        att = cbor({"fmt": "none", "attStmt": {}, "authData": self.k.auth_data(flags=W.UP | W.UV | W.ED, attested=True, extra=cbor({"credProtect": 2}))})
        self.assertEqual(self.reg(cdj, att)["cred_id"], self.k.cred)                   # extensions: a map, read and set aside

    def test_refused(self):
        k, ch = self.k, self.ch
        cdj, att = k.create(ch)
        ad = lambda **kw: cbor({"fmt": "none", "attStmt": {}, "authData": k.auth_data(attested=True, **kw)})
        cd = lambda **kw: json.dumps(dict({"type": "webauthn.create", "challenge": W.b64u(ch), "origin": ORIGIN}, **kw)).encode()
        cases = {
            "another challenge": (cdj, att, secrets.token_bytes(32), ORIGIN, RP),
            "another origin": (cdj, att, ch, "https://%s:9999" % RP, RP),
            "another rpId": (cdj, att, ch, ORIGIN, "other-mac.tail0000.ts.net"),
            "type get": (cd(type="webauthn.get"), att, ch, ORIGIN, RP),
            "cross origin": (cd(crossOrigin=True), att, ch, ORIGIN, RP),
            "top origin": (cd(topOrigin="https://example.com"), att, ch, ORIGIN, RP),
            "token binding": (cd(tokenBinding={"status": "present", "id": "x"}), att, ch, ORIGIN, RP),
            "duplicate key in client data": (b'{"type":"webauthn.create","type":"webauthn.create","challenge":"%s","origin":"%s"}' % (W.b64u(ch).encode(), ORIGIN.encode()), att, ch, ORIGIN, RP),
            "client data not JSON": (b"x" * 40, att, ch, ORIGIN, RP),
            "client data an array": (b"[" + b'"x",' * 10 + b'"x"]', att, ch, ORIGIN, RP),
            "client data too large": (cd(pad="x" * 3000), att, ch, ORIGIN, RP),
            "not verified (no UV)": (cdj, ad(flags=W.UP), ch, ORIGIN, RP),
            "not present (no UP)": (cdj, ad(flags=W.UV), ch, ORIGIN, RP),
            "BS without BE": (cdj, ad(flags=W.UP | W.UV | W.BS), ch, ORIGIN, RP),
            "passkey for another host": (cdj, ad(rp="evil.example"), ch, ORIGIN, RP),
            "trailing bytes": (cdj, ad(extra=b"\x00"), ch, ORIGIN, RP),
            "extensions not a map": (cdj, ad(flags=W.UP | W.UV | W.ED, extra=cbor([1])), ch, ORIGIN, RP),
            "RSA key": (cdj, ad(cose={1: 3, 3: -257, -1: b"n" * 256, -2: b"\x01\x00\x01"}), ch, ORIGIN, RP),
            "attestation packed": (cdj, cbor({"fmt": "packed", "attStmt": {}, "authData": k.auth_data(attested=True)}), ch, ORIGIN, RP),
            "attestation statement": (cdj, cbor({"fmt": "none", "attStmt": {"sig": b"x"}, "authData": k.auth_data(attested=True)}), ch, ORIGIN, RP),
            "extra field": (cdj, cbor({"fmt": "none", "attStmt": {}, "authData": k.auth_data(attested=True), "x": 1}), ch, ORIGIN, RP),
            "no credential data": (cdj, cbor({"fmt": "none", "attStmt": {}, "authData": k.auth_data()}), ch, ORIGIN, RP),
            "authData not bytes": (cdj, cbor({"fmt": "none", "attStmt": {}, "authData": "x" * 40}), ch, ORIGIN, RP),
        }
        for name, args in cases.items():
            with self.subTest(name), self.assertRaises(W.Invalid):
                W.verify_registration(*args)
        short = SoftKey(); short.cred = b"\x01" * 8                                       # a credential id shorter than 16 bytes
        with self.assertRaises(W.Invalid):
            self.reg(*short.create(ch))


class Assertion(unittest.TestCase):
    def setUp(self):
        self.k, self.ch = SoftKey(), secrets.token_bytes(32)

    def check(self, cdj, ad, sig, ch=None, count=0, x=None):
        return W.verify_assertion(cdj, ad, sig, ch or self.ch, ORIGIN, RP, x or self.k.x, self.k.y, count)

    def test_signed_with_face_id(self):
        self.assertEqual(self.check(*self.k.get(self.ch))["count"], 0)
        k = SoftKey(count_step=1)                                                       # a key that counts: each use higher
        self.assertEqual(W.verify_assertion(*k.get(self.ch), self.ch, ORIGIN, RP, k.x, k.y, 0)["count"], 1)
        got = k.get(self.ch)
        self.assertEqual(W.verify_assertion(*got, self.ch, ORIGIN, RP, k.x, k.y, 1)["count"], 2)
        with self.assertRaises(W.Invalid):                                              # the same count again: a copy of the key?
            W.verify_assertion(*got, self.ch, ORIGIN, RP, k.x, k.y, 2)
        with self.assertRaises(W.Invalid):                                              # 0 after it counted
            self.check(*self.k.get(self.ch), count=5)

    def test_refused(self):
        k, ch = self.k, self.ch
        other = SoftKey()
        cases = {
            "another challenge": (k.get(ch), {"ch": secrets.token_bytes(32)}),
            "another key": (other.get(ch), {}),
            "cross origin": (k.get(ch, cdj=k.client_data("webauthn.get", ch, crossOrigin=True)), {}),
            "type create": (k.get(ch, cdj=k.client_data("webauthn.create", ch)), {}),
            "another origin": (k.get(ch, cdj=json.dumps({"type": "webauthn.get", "challenge": W.b64u(ch), "origin": "https://evil.example"}).encode()), {}),
            "no Face ID (UV)": (k.get(ch, flags=W.UP), {}),
            "no UP": (k.get(ch, flags=W.UV), {}),
            "credential data in a sign-in": (k.get(ch, ad=k.auth_data(attested=True)), {}),
            "another rpId": (k.get(ch, ad=k.auth_data(rp="evil.example")), {}),
            "trailing bytes": (k.get(ch, ad=k.auth_data(extra=b"\x00")), {}),
            "short authData": (k.get(ch, ad=b"\x00" * 36), {}),
        }
        for name, (got, kw) in cases.items():
            with self.subTest(name), self.assertRaises(W.Invalid):
                self.check(*got, ch=kw.get("ch"))
        c, a, s = k.get(ch)
        for name, args in (("signature of other data", (c, k.auth_data(count=7), s)), ("client data changed", (c.replace(b'"crossOrigin": false', b'"crossOrigin": null'), a, s)),
                           ("signature cut", (c, a, s[:-1])), ("no signature", (c, a, b""))):
            with self.subTest(name), self.assertRaises(W.Invalid):
                self.check(*args)


class StricterChecks(unittest.TestCase):
    """crossOrigin only absent or exactly false; extensions at sign-in only as a map; BE as at registration."""

    def test_cross_origin_only_absent_or_false(self):
        k, ch = SoftKey(), secrets.token_bytes(32)
        for bad in (None, 0, "false", [], {}, 1, True):
            cdj = json.dumps({"type": "webauthn.get", "challenge": W.b64u(ch), "origin": ORIGIN, "crossOrigin": bad}).encode()
            with self.subTest(bad), self.assertRaises(W.Invalid):
                W.verify_assertion(*k.get(ch, cdj=cdj), ch, ORIGIN, RP, k.x, k.y, 0)
        cdj = json.dumps({"type": "webauthn.get", "challenge": W.b64u(ch), "origin": ORIGIN}).encode()        # absent: fine
        self.assertEqual(W.verify_assertion(*k.get(ch, cdj=cdj), ch, ORIGIN, RP, k.x, k.y, 0)["count"], 0)

    def test_extensions_at_sign_in(self):
        k, ch = SoftKey(), secrets.token_bytes(32)
        ok = k.get(ch, ad=k.auth_data(flags=W.UP | W.UV | W.ED, extra=cbor({"credProtect": 2})))
        self.assertEqual(W.verify_assertion(*ok, ch, ORIGIN, RP, k.x, k.y, 0)["count"], 0)
        for extra in (cbor([1]), cbor("x"), b"", cbor({"a": 1}) + b"\x00", b"\xa1"):
            with self.subTest(extra), self.assertRaises(W.Invalid):
                W.verify_assertion(*k.get(ch, ad=k.auth_data(flags=W.UP | W.UV | W.ED, extra=extra)), ch, ORIGIN, RP, k.x, k.y, 0)

    def test_backup_eligibility_as_at_registration(self):
        k, ch = SoftKey(), secrets.token_bytes(32)
        synced = k.get(ch, flags=W.UP | W.UV | W.BE | W.BS)
        self.assertEqual(W.verify_assertion(*synced, ch, ORIGIN, RP, k.x, k.y, 0, backup_eligible=True)["count"], 0)
        with self.assertRaises(W.Invalid):
            W.verify_assertion(*synced, ch, ORIGIN, RP, k.x, k.y, 0, backup_eligible=False)
        with self.assertRaises(W.Invalid):
            W.verify_assertion(*k.get(ch), ch, ORIGIN, RP, k.x, k.y, 0, backup_eligible=True)


class QrCode(unittest.TestCase):
    def test_reed_solomon_and_bits(self):
        # the classic example ("HELLO WORLD", version 1-M): its data codewords and the error correction that belongs to them
        self.assertEqual(qr.rs_remainder([32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17], 10),
                         [196, 35, 39, 119, 235, 215, 231, 226, 93, 23])
        self.assertEqual(qr.format_bits(0), 0b101010000010010)                          # level M, mask 0
        self.assertEqual(qr.version_bits(7), 0x07C94)

    def test_structure(self):
        for n, version in ((10, 1), (95, 6), (200, 10)):
            m = qr.matrix(("https://%s:%d/#pair=" % (RP, PORT) + secrets.token_urlsafe(160))[:n])
            self.assertEqual(len(m), version * 4 + 17)
            for cx, cy in ((3, 3), (len(m) - 4, 3), (3, len(m) - 4)):                   # the three finder patterns
                self.assertTrue(all(m[cy][cx + d] for d in (-1, 0, 1)) and not m[cy][cx - 2] and m[cy][cx - 3])
            self.assertTrue(m[len(m) - 8][8])                                           # the dark module
        size, path = qr.svg_path("https://%s:%d/#pair=x" % (RP, PORT))
        self.assertEqual(size, len(qr.matrix("https://%s:%d/#pair=x" % (RP, PORT))) + 8)
        self.assertRegex(path, r"^(M\d+ \d+h\d+v1h-\d+z)+$")
        with self.assertRaises(ValueError):
            qr.matrix("x" * 214)

    def test_decodes(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV not installed (decoding only checked where it is)")
        det = cv2.QRCodeDetectorAruco() if hasattr(cv2, "QRCodeDetectorAruco") else cv2.QRCodeDetector()
        for n in (20, 60, 95, 130, 180, 213):
            text = ("https://%s:%d/#pair=" % (RP, PORT) + secrets.token_urlsafe(200))[:n]
            m = qr.matrix(text)
            img = np.full((len(m) + 8, len(m) + 8), 255, np.uint8)
            for y, row in enumerate(m):
                for x, v in enumerate(row):
                    if v:
                        img[y + 4, x + 4] = 0
            img = cv2.resize(img, (img.shape[0] * 8,) * 2, interpolation=cv2.INTER_NEAREST)
            self.assertEqual(det.detectAndDecode(img)[0], text, n)


class FakeStore:
    is_open = True

    def __init__(self):
        self.files, self.aside, self.broken = {}, [], None

    def load_shared(self, name, default=None):
        if self.broken is not None and name in self.files:
            raise self.broken
        return self.files.get(name, default)

    def update(self, name, fn, default=None):
        obj = copy.deepcopy(self.load_shared(name, default if default is not None else {}))
        fn(obj)
        self.files[name] = obj
        return obj

    def save(self, name, obj):
        self.files[name] = copy.deepcopy(obj)

    def set_aside(self, name):
        self.aside.append(name)
        self.files.pop(name, None)
        self.broken = None
        return name + ".enc.damaged-20261123-120000"

    def delete(self, name):
        self.files.pop(name, None)


class Devices(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.d = D.Devices(FakeStore(), clock=lambda: self.now[0])

    def test_pairing_link(self):
        t = self.d.pairing_new(True, by="sid-mac")
        self.assertGreaterEqual(len(t), 40)
        self.assertIsNotNone(self.d.pairing_check(t)); self.assertIsNotNone(self.d.pairing_check(t))      # valid until used
        self.assertEqual(self.d.pairing_check(t)["by"], "sid-mac")
        for bad in (t[:-1], t + "x", t.upper(), "", None, 5, "x" * 30):
            self.assertIsNone(self.d.pairing_check(bad))
        t2 = self.d.pairing_new(False)                                                 # a new one: the one before is gone
        self.assertIsNone(self.d.pairing_check(t)); self.assertFalse(self.d.pairing_check(t2)["changes"])
        self.assertTrue(self.d.pairing_set(True)); self.assertTrue(self.d.pairing_check(t2)["changes"])
        self.assertIsNotNone(self.d.pairing_take(t2)); self.assertIsNone(self.d.pairing_take(t2)); self.assertIsNone(self.d.pairing_check(t2))
        t3 = self.d.pairing_new(True)
        self.now[0] += D.PAIR_SECONDS - 1
        self.assertIsNotNone(self.d.pairing_check(t3))
        self.now[0] += 2
        self.assertIsNone(self.d.pairing_check(t3)); self.assertIsNone(self.d.pairing_take(t3)); self.assertIsNone(self.d.pairing_state())

    def test_challenges(self):
        c = self.d.challenge_new("confirm", "s1", {"sid": "s1"})
        self.assertIsNone(self.d.challenge_take(c, "login", "s1"))                     # made for something else
        self.assertIsNone(self.d.challenge_take(c, "confirm", "s2"))                   # ... or someone else
        self.assertEqual(self.d.challenge_take(c, "confirm", "s1"), {"sid": "s1"})
        self.assertIsNone(self.d.challenge_take(c, "confirm", "s1"))                   # once
        c = self.d.challenge_new("login", "10.0.0.1", {})
        self.now[0] += D.CHALLENGE_SECONDS
        self.assertIsNone(self.d.challenge_take(c, "login", "10.0.0.1"))               # expired
        self.assertIsNone(self.d.challenge_take(b"x" * 31, "login", "10.0.0.1"))

    def test_nobody_pushes_out_anothers_challenges(self):
        mine = self.d.challenge_new("confirm", "session-a", {"n": "a"})
        login = self.d.challenge_new("login", "100.64.0.9", {"n": "phone"})
        for i in range(500):                                                           # someone else, as often as they like
            self.d.challenge_new("login", "100.64.0.66", {"n": i})
            self.d.challenge_new("confirm", "session-b", {"n": i})
            self.d.challenge_new("pair", "100.64.0.66", {"n": i})
        self.assertEqual(self.d.challenge_take(mine, "confirm", "session-a"), {"n": "a"})
        self.assertEqual(self.d.challenge_take(login, "login", "100.64.0.9"), {"n": "phone"})
        own = [self.d.challenge_new("confirm", "session-a", {"n": i}) for i in range(D.PER_OWNER["confirm"] + 1)]
        self.assertIsNone(self.d.challenge_take(own[0], "confirm", "session-a"))       # a session's own oldest goes, nobody else's
        self.assertEqual(self.d.challenge_take(own[-1], "confirm", "session-a"), {"n": D.PER_OWNER["confirm"]})
        firsts = [self.d.challenge_new("login", "100.64.%d.%d" % (i // 250, i % 250), {}) for i in range(D.MAX_OWNERS + 5)]
        self.assertIsNone(self.d.challenge_take(firsts[0], "login", "100.64.0.0"))     # many addresses: the longest waiting goes
        self.assertIsNotNone(self.d.challenge_take(firsts[-1], "login", "100.64.%d.%d" % ((D.MAX_OWNERS + 4) // 250, (D.MAX_OWNERS + 4) % 250)))

    def test_budget_for_sign_in_challenges(self):
        self.assertTrue(all(self.d.allow("100.64.0.66") for _ in range(D.OPTIONS_PER_MINUTE)))
        self.assertFalse(self.d.allow("100.64.0.66")); self.assertTrue(self.d.allow("100.64.0.9"))
        self.now[0] += 61
        self.assertTrue(self.d.allow("100.64.0.66"))

    def test_devices_and_names(self):
        k = SoftKey()
        self.assertFalse(self.d.passkey_only())
        dev = self.d.add("  Mein\u200b iPhone\n", k.cred, k.x, k.y, b"u" * 16, RP, 0, changes=True, be=True)
        self.assertEqual((dev["name"], dev["changes"], dev["be"]), ("Mein iPhone", True, True)); self.assertTrue(self.d.passkey_only())     # on once a device is there
        self.assertEqual(self.d.by_credential(k.cred)["id"], dev["id"])
        with self.assertRaises(ValueError):
            self.d.add("x", k.cred, k.x, k.y, b"u" * 16, RP, 0)                        # the same passkey twice
        self.d.set_passkey_only(False); self.assertFalse(self.d.passkey_only())
        self.assertTrue(self.d.set_changes(dev["id"], False)); self.assertFalse(self.d.get(dev["id"])["changes"])
        self.d.used(dev["id"], 7); self.d.used(dev["id"], 3)
        self.assertEqual(self.d.get(dev["id"])["count"], 7)                            # never lower than before
        c = self.d.challenge_new("confirm", "s1", {"device": dev["id"]})
        self.assertEqual(self.d.remove(dev["id"])["id"], dev["id"])
        self.assertIsNone(self.d.get(dev["id"])); self.assertIsNone(self.d.challenge_take(c, "confirm", "s1"))     # its challenges went with it
        self.assertIsNone(self.d.remove(dev["id"])); self.assertIsNone(self.d.get("../x"))
        self.assertEqual(D.clean_name(""), "iPhone"); self.assertEqual(len(D.clean_name("x" * 100)), D.NAME_MAX)

    def test_a_damaged_list_is_set_aside_and_fails_closed(self):
        import storage
        k = SoftKey()
        self.d.add("x", k.cred, k.x, k.y, b"u" * 16, RP, 0)
        self.d.set_passkey_only(False)
        self.d.store.broken = storage.StoreDamaged("devices.json.enc: check sum", "devices.json")
        self.assertEqual(self.d.all(), [])
        self.assertEqual(self.d.store.aside, ["devices.json"])
        self.assertTrue(self.d.passkey_only())                                         # fail closed: no password from elsewhere
        self.assertEqual(self.d.damaged()["kept"], "devices.json.enc.damaged-20261123-120000")
        self.d.add("y", k.cred, k.x, k.y, b"u" * 16, RP, 0)                            # added again: the note is done
        self.assertIsNone(self.d.damaged()); self.assertTrue(self.d.passkey_only())
        self.d.store.broken = storage.StoreError("openssl not there")                  # may pass: nothing set aside, nothing let in
        self.assertEqual(self.d.all(), []); self.assertTrue(self.d.passkey_only()); self.assertEqual(self.d.store.aside, ["devices.json"])
        self.d.store.broken = None
        self.d.store.files["devices.json"] = ["not", "a", "list"]                      # JSON, but not the list: damaged too
        self.assertEqual(self.d.all(), []); self.assertEqual(len(self.d.store.aside), 2)


class DevicesStore(unittest.TestCase):
    def test_not_writable_and_not_readable_right_now(self):
        import storage
        st = FakeStore()
        d = D.Devices(st)
        k = SoftKey()
        dev = d.add("x", k.cred, k.x, k.y, b"u" * 16, RP, 0)
        self.assertIs(d.present(dev["id"]), True); self.assertIs(d.present("d" + "0" * 16), False); self.assertTrue(d.readable())
        st.broken = storage.StoreError("openssl not there")                           # a passing error: nothing ends, nothing let in
        self.assertIsNone(d.present(dev["id"])); self.assertFalse(d.readable()); self.assertIsNone(d.get(dev["id"]))
        with self.assertRaises(D.NotWritable) as e:                                    # never written over what did not read
            d.set_passkey_only(False)
        self.assertEqual(str(e.exception), D.tr("s_pk_liste_nicht_speicherbar"))
        self.assertEqual(st.aside, [])
        st.broken = None
        self.assertIs(d.present(dev["id"]), True)
        d._closed = {"kept": "", "time": ""}                                           # damaged and not written anew
        for act in (lambda: d.set_passkey_only(True), lambda: d.add("y", SoftKey().cred, 1, 2, b"v" * 16, RP, 0)):
            self.assertRaises(D.NotWritable, act)
        self.assertFalse(d.set_changes(dev["id"], True)); self.assertIsNone(d.remove(dev["id"]))       # (none there to change)
        d.used(dev["id"], 5)                                                           # (nothing to note it in: no error)
        self.assertIs(d.present(dev["id"]), False)


class TailscaleCheck(unittest.TestCase):
    """Tailnet Lock and "tailscale serve"/Funnel, read from Tailscale (tls_cert.ask, exposure): only two fixed questions."""

    def test_what_is_found(self):
        import tls_cert as T
        given = {}
        orig = T.ask
        T.ask = lambda what: copy.deepcopy(given.get(what))
        web = lambda target: {"TCP": {"443": {"HTTPS": True}}, "Web": {"mac.example.ts.net:443": {"Handlers": {"/": {"Proxy": target}}}}}
        try:
            for lock, serve, want in (
                    ({"Enabled": True}, {}, (True, "none")),
                    ({"Enabled": False}, web("http://127.0.0.1:8765"), (False, "serve")),
                    ({"Enabled": False}, dict(web("http://localhost:8765/"), AllowFunnel={"mac.example.ts.net:443": True}), (False, "funnel")),
                    ({}, dict(web("http://127.0.0.1:8765"), AllowFunnel={"mac.example.ts.net:443": False}), (None, "serve")),
                    (None, {"TCP": {"8765": {"TCPForward": "127.0.0.1:8765"}}}, (None, "serve")),
                    ({"Enabled": "yes"}, {"Services": {"svc:x": web("8765")}}, (None, "serve")),
                    ({"Enabled": True}, web("http://127.0.0.1:3000"), (True, "none")),
                    ({"Enabled": True}, web("http://127.0.0.1"), (True, "none")),
                    ({"Enabled": True}, None, (True, "unknown")),
                    # only what is this Mac counts: another device in the network with the same port is not Kontor
                    ({"Enabled": True}, web("http://192.168.1.10:8765"), (True, "none")),
                    ({"Enabled": True}, web("http://nas.local:8765"), (True, "none")),
                    ({"Enabled": True}, web("http://100.64.1.9:8765"), (True, "none")),
                    ({"Enabled": True}, web("http://100.64.1.2:8765"), (True, "serve")),          # this Mac's own address (given)
                    ({"Enabled": True}, web("http://Kontor-Mac.tail0000.ts.net.:8765"), (True, "serve")),
                    ({"Enabled": True}, web("https+insecure://[::1]:8765"), (True, "serve")),
                    ({"Enabled": True}, web("http://127.0.0.2:8765/x"), (True, "serve")),
                    ({"Enabled": True}, web("http://[::ffff:7f00:1]:8765"), (True, "serve")),            # 127.0.0.1 written in IPv6
                    ({"Enabled": True}, web("http://[0:0:0:0:0:ffff:127.0.0.1]:8765"), (True, "serve")),
                    ({"Enabled": True}, web("http://[::]:8765"), (True, "serve")),
                    ({"Enabled": True}, {"TCP": {"8765": {"TCPForward": "0.0.0.0:8765"}}}, (True, "serve")),
                    ({"Enabled": True}, {"TCP": {"8765": {"TCPForward": "kontor.localhost:8765"}}}, (True, "serve")),
                    ({"Enabled": True}, T.OFF, (None, "off"))):                                # Tailscale does not run: nothing passed on
                given = {"lock": lock, "serve": serve}
                got = T.exposure(8765, ("100.64.1.2", "kontor-mac.tail0000.ts.net", ""))
                self.assertEqual((got["lock"], got["serve"]), want, (lock, serve))
        finally:
            T.ask = orig

    def test_off_only_when_tailscale_does_not_run(self):
        """"off" (nothing can pass anything on) only when neither Tailscale's app nor its program answers because it does not
        run -- an answer refused, a program that hangs or does not start in the background is no answer (the last state holds)."""
        import subprocess
        import tls_cert as T
        orig = (T.localapi, T.find_tailscale, T.run)
        no_app = lambda path, timeout=15: (_ for _ in ()).throw(RuntimeError("Tailscale local interface not found"))
        app_fails = lambda path, timeout=15: (_ for _ in ()).throw(RuntimeError("Tailscale 500: busy"))
        cli = lambda code, out: (lambda binary, args, timeout: subprocess.CompletedProcess(args, code, "", out))
        hang = lambda binary, args, timeout: (_ for _ in ()).throw(subprocess.TimeoutExpired(args, timeout))
        try:
            for api, binary, run, want in (
                    (no_app, None, None, T.OFF),                                               # neither app nor program on this Mac
                    (app_fails, None, None, None),                                             # its app runs, but answers nothing
                    (no_app, "/usr/local/bin/tailscale", cli(1, "failed to connect to local tailscaled; it doesn't appear to be running (sudo systemctl start tailscaled ?)"), T.OFF),
                    (no_app, "/usr/local/bin/tailscale", cli(1, "Failed to connect to local Tailscale daemon for /localapi/v0/serve-config; not running? Error: dial unix: no such file"), T.OFF),
                    (no_app, "/usr/local/bin/tailscale", cli(1, "Failed to connect to local Tailscale daemon: permission denied"), None),
                    (no_app, "/Applications/Tailscale.app/Contents/MacOS/Tailscale", cli(1, "The Tailscale GUI failed to start"), None),
                    (no_app, "/usr/local/bin/tailscale", hang, None),
                    (no_app, "/usr/local/bin/tailscale", cli(0, ""), {}),                       # runs, serves nothing
                    (no_app, "/usr/local/bin/tailscale", lambda binary, args, timeout: subprocess.CompletedProcess(args, 0, "null\n", ""), {}),     # ... as it says it
                    (lambda path, timeout=15: b"null", None, None, {})):                        # its app: nothing served (or signed out)
                T.localapi, T.find_tailscale = api, (lambda b=binary: b)
                if run:
                    T.run = run
                with self.subTest(binary=binary, want=want):
                    self.assertEqual(T.ask("serve"), want)
        finally:
            T.localapi, T.find_tailscale, T.run = orig

    def test_only_the_fixed_questions(self):
        import subprocess
        import tls_cert as T
        calls = []
        orig = (T.localapi, T.find_tailscale, T.run)
        T.localapi = lambda path, timeout=15: (_ for _ in ()).throw(RuntimeError("no app"))
        T.find_tailscale = lambda: "/usr/local/bin/tailscale"
        T.run = lambda binary, args, timeout: calls.append(list(args)) or subprocess.CompletedProcess(args, 0, '{"Enabled": false}', "")
        try:
            self.assertIsNone(T.ask("status")); self.assertIsNone(T.ask("serve --bg 8765"))
            self.assertEqual(T.ask("lock"), {"Enabled": False})
            self.assertEqual(T.ask("serve"), {"Enabled": False})
            self.assertEqual(calls, [["lock", "status", "--json"], ["serve", "status", "--json"]])
        finally:
            T.localapi, T.find_tailscale, T.run = orig


class PageLists(unittest.TestCase):
    def test_the_page_asks_face_id_where_the_service_wants_it(self):
        """The page's lists (web/app.js) are the service's: what goes without Face ID, the ways in."""
        import re
        import service as MA
        with open(os.path.join(os.path.dirname(__file__), "..", "web", "app.js"), encoding="utf-8") as f:
            js = f.read()
        lst = lambda name: set(re.findall(r"'(/api/[^']+)'", re.search(r"const %s = \[(.*?)\];" % name, js, re.S).group(1)))
        self.assertEqual(lst("NO_CONFIRM"), set(MA.CONFIRM_FREE | MA.CONFIRM_MAYBE))
        self.assertEqual(lst("SIGN_IN"), set(MA.SIGN_IN))
        self.assertEqual(len(re.findall(r"navigator\.credentials\.", js)), 2)            # both in pkCall, nowhere else
        self.assertEqual(js.count("navigator.credentials"), 3)


# -- over HTTP ---

# -- over HTTP ---------------------------------------------------------------------------------------------------------------
class Client:
    def __init__(self, port):
        self.port, self.jar, self.csrf = port, CookieJar(), None
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, path, body=None, method=None, headers=None, raw=False):
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=data, method=method or ("POST" if data is not None else "GET"))
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.csrf:
            req.add_header("X-CSRF-Token", self.csrf)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with self.opener.open(req) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")


class OverHttp(unittest.TestCase):
    """The service with an iPhone simulated: Kontor's address in the Tailscale network with its certificate (made up), requests
    from it arrive from another address over https (both patched -- the checks behind are the real ones)."""

    def setUp(self):
        import service as MA
        import fixtures as F
        import test_e2e as E
        self.MA = MA
        self.dir = tempfile.mkdtemp(prefix="kontor-pk-")
        store = F.new_store(self.dir)
        cfg = E.config_for_test(os.path.join(self.dir, "Belege"))
        cfg["ui"] = dict(cfg.get("ui") or {}, bind="100.64.1.2", tls_cert="/tmp/tls/%s.crt" % RP, tls_key="/tmp/tls/%s.key" % RP, port=PORT)
        store.save("config.json", cfg)
        store.save("state.json", dict(E.ALL_NEW))
        E.reset_mock()
        E.patch_today()
        self.app = MA.App(store, self.dir, bridge_factory=E.MockBridge)
        self.app.tailscale = lambda fresh=False: {"found": False}
        import tls_cert
        self.T, self.orig_exposure = tls_cert, tls_cert.exposure                       # Tailscale's answer, as the test sets it
        self.answer = {"serve": "none", "lock": None}
        tls_cert.exposure = lambda port, own=(): dict(self.answer, port=port)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), MA.make_handler(self.app))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.remote = [False]
        self.orig = (MA.auth.is_loopback, MA.tls_connection)
        MA.auth.is_loopback = lambda addr: not self.remote[0] and addr in ("127.0.0.1", "::1", "localhost")
        MA.tls_connection = lambda conn: self.remote[0]
        self.mac = Client(self.srv.server_address[1])
        code, r = self.mac.call("/api/setup", {"password": "sehr-geheimes-passwort"})
        self.assertEqual(code, 200)
        self.mac.csrf = r["csrf"]

    def tearDown(self):
        self.MA.auth.is_loopback, self.MA.tls_connection = self.orig
        self.T.exposure = self.orig_exposure
        self.srv.shutdown(); self.srv.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def at_mac(self, path, body=None):
        self.remote[0] = False
        return self.mac.call(path, body)

    def phone(self):
        return Client(self.srv.server_address[1])

    def on_phone(self, client, path, body=None, **kw):
        self.remote[0] = True
        return client.call(path, body, **kw)

    def link(self, changes=True):
        code, r = self.at_mac("/api/devices/pair", {"action": "new", "changes": changes})
        self.assertEqual(code, 200, r)
        return r["url"].split("#pair=")[1]

    def pair(self, client=None, key=None, changes=True, password="sehr-geheimes-passwort", name="Testgerät"):
        client, key = client or self.phone(), key or SoftKey()
        token = self.link(changes)
        code, opt = self.on_phone(client, "/api/pair/begin", {"token": token, "name": name, "password": password})
        self.assertEqual(code, 200, opt)
        self.assertEqual((opt["rp"]["id"], opt["user"]["name"]), (RP, name))
        cdj, att = key.create(W.b64u_decode(opt["challenge"]))
        code, r = self.on_phone(client, "/api/pair/finish", {"token": token, "id": W.b64u(key.cred), "client_data": W.b64u(cdj), "attestation": W.b64u(att)})
        self.assertEqual(code, 200, r)
        client.csrf = r["csrf"]
        return client, key

    def confirmed(self, client, key, path, body, method="POST"):
        """A change from the iPhone: the challenge for exactly this request, Face ID (the software key), the request."""
        raw = json.dumps(body).encode()
        code, c = self.on_phone(client, "/api/confirm", {"method": method, "path": path, "body": hashlib.sha256(raw).hexdigest()})
        self.assertEqual(code, 200, c)
        self.assertEqual(c["credential"], W.b64u(key.cred))
        cdj, ad, sig = key.get(W.b64u_decode(c["challenge"]))
        hdr = ".".join(W.b64u(x) for x in (key.cred, cdj, ad, sig))
        return self.on_phone(client, path, raw, method=method, headers={"X-Kontor-Confirm": hdr}), hdr, raw

    def sign_in(self, key, client=None, demo=False):
        client = client or self.phone()
        code, opt = self.on_phone(client, "/api/passkey/options", {})
        self.assertEqual(code, 200, opt)
        cdj, ad, sig = key.get(W.b64u_decode(opt["challenge"]))
        code, r = self.on_phone(client, "/api/passkey/login", dict({"id": W.b64u(key.cred), "client_data": W.b64u(cdj), "auth_data": W.b64u(ad), "signature": W.b64u(sig)},
                                                                   **({"demo": True} if demo else {})))
        client.csrf = r.get("csrf")
        return code, r, client

    def test_adding_an_iphone(self):
        self.assertFalse(self.app.remote_changes())                                   # a new Kontor: only look from elsewhere
        self.assertEqual(self.at_mac("/api/devices")[1]["devices"], [])
        token = self.link()
        self.assertFalse(self.app.remote_changes())                                   # the link alone switches nothing
        st = self.at_mac("/api/devices")[1]
        self.assertTrue(st["pairing"]["active"]); self.assertIn("#pair=" + token, st["pairing"]["url"])
        self.assertTrue(st["pairing"]["url"].startswith("https://%s:%d/" % (RP, PORT)))
        p = self.phone()
        self.assertEqual(self.on_phone(p, "/api/devices")[0], 401)
        self.assertFalse(self.on_phone(p, "/api/session")[1]["passkey"])               # no device yet
        # a wrong link, a wrong password: refused and counted
        self.assertEqual(self.on_phone(p, "/api/pair/begin", {"token": token[:-2] + "xx", "name": "x", "password": "sehr-geheimes-passwort"})[0], 403)
        self.assertEqual(self.on_phone(p, "/api/pair/begin", {"token": token, "name": "x", "password": "falsch-falsch"})[0], 401)
        # not from the Mac itself
        self.remote[0] = False
        self.assertEqual(self.mac.call("/api/pair/begin", {"token": token, "name": "x", "password": "sehr-geheimes-passwort"})[0], 403)
        key = SoftKey()
        code, opt = self.on_phone(p, "/api/pair/begin", {"token": token, "name": "Testgerät", "password": "sehr-geheimes-passwort"})
        self.assertEqual(code, 200)
        ch = W.b64u_decode(opt["challenge"])
        # a passkey made for another host, or over another challenge: refused, the link stays
        for bad in (SoftKey(rp="evil.example"), SoftKey(origin="https://evil.example")):
            cdj, att = bad.create(ch)
            self.assertEqual(self.on_phone(p, "/api/pair/finish", {"token": token, "id": W.b64u(bad.cred), "client_data": W.b64u(cdj), "attestation": W.b64u(att)})[0], 400)
        code, opt = self.on_phone(p, "/api/pair/begin", {"token": token, "name": "Testgerät", "password": "sehr-geheimes-passwort"})
        cdj, att = key.create(W.b64u_decode(opt["challenge"]))
        other = self.phone()                                                           # the challenge belongs to this address and link
        self.assertEqual(self.on_phone(other, "/api/pair/finish", {"token": "y" * 43, "id": W.b64u(key.cred), "client_data": W.b64u(cdj), "attestation": W.b64u(att)})[0], 400)
        code, opt = self.on_phone(p, "/api/pair/begin", {"token": token, "name": "Testgerät", "password": "sehr-geheimes-passwort"})
        cdj, att = key.create(W.b64u_decode(opt["challenge"]))
        body = {"token": token, "id": W.b64u(key.cred), "client_data": W.b64u(cdj), "attestation": W.b64u(att)}
        code, r = self.on_phone(p, "/api/pair/finish", body)
        self.assertEqual(code, 200, r)
        self.assertTrue(self.app.remote_changes())                                    # the first iPhone added, ticked on the card at the Mac
        self.assertEqual(self.on_phone(p, "/api/pair/finish", body)[0], 400)           # the link and its challenge: used up
        self.assertEqual(self.on_phone(self.phone(), "/api/pair/begin", {"token": token, "name": "x", "password": "sehr-geheimes-passwort"})[0], 403)
        devs = self.at_mac("/api/devices")[1]["devices"]
        self.assertEqual([(d["name"], d["current"]) for d in devs], [("Testgerät", True)])
        stored = json.dumps(self.app.devices.all())
        self.assertNotIn(str(key.d), stored); self.assertNotIn("%064x" % key.d, stored)          # (the private key never leaves the iPhone)
        self.assertNotIn("Testgerät", open(os.path.join(self.dir, "devices.json.enc"), "rb").read().decode("latin-1"))      # encrypted

    def test_each_change_confirmed_for_exactly_that_request(self):
        p, key = self.pair()
        p.csrf = p.csrf
        st = self.on_phone(p, "/api/status")[1]
        self.assertEqual((st["read_only"], st["confirm"], st["trusted"]), (False, True, True))
        body = {"area": self.area(), "row": "income/Arbeitseinkommen", "method": "fix", "amount": "1"}
        code, r = self.on_phone(p, "/api/plan", body)
        self.assertEqual((code, r.get("confirm")), (403, "needed"))                    # without Face ID: nothing
        (code, r), hdr, raw = self.confirmed(p, key, "/api/plan", body)
        self.assertEqual(code, 200, r)
        self.assertEqual(self.on_phone(p, "/api/plan", raw, headers={"X-Kontor-Confirm": hdr})[0], 403)          # the same confirmation again
        # a confirmation for one request does not carry another: other body, other path, other method
        raw2 = json.dumps(dict(body, amount="2")).encode()
        code, c = self.on_phone(p, "/api/confirm", {"method": "POST", "path": "/api/plan", "body": hashlib.sha256(raw).hexdigest()})
        cdj, ad, sig = key.get(W.b64u_decode(c["challenge"]))
        hdr = ".".join(W.b64u(x) for x in (key.cred, cdj, ad, sig))
        self.assertEqual(self.on_phone(p, "/api/plan", raw2, headers={"X-Kontor-Confirm": hdr})[0], 403)
        code, c = self.on_phone(p, "/api/confirm", {"method": "POST", "path": "/api/plan", "body": hashlib.sha256(raw).hexdigest()})
        cdj, ad, sig = key.get(W.b64u_decode(c["challenge"]))
        hdr = ".".join(W.b64u(x) for x in (key.cred, cdj, ad, sig))
        self.assertEqual(self.on_phone(p, "/api/language", raw, headers={"X-Kontor-Confirm": hdr})[0], 403)
        # ... nor another session, nor another passkey
        code, r, p2 = self.sign_in(key)
        self.assertEqual(code, 200, r)
        code, c = self.on_phone(p, "/api/confirm", {"method": "POST", "path": "/api/plan", "body": hashlib.sha256(raw).hexdigest()})
        cdj, ad, sig = key.get(W.b64u_decode(c["challenge"]))
        self.assertEqual(self.on_phone(p2, "/api/plan", raw, headers={"X-Kontor-Confirm": ".".join(W.b64u(x) for x in (key.cred, cdj, ad, sig))})[0], 403)
        stranger = SoftKey()
        code, c = self.on_phone(p, "/api/confirm", {"method": "POST", "path": "/api/plan", "body": hashlib.sha256(raw).hexdigest()})
        cdj, ad, sig = stranger.get(W.b64u_decode(c["challenge"]))
        for cred in (stranger.cred, key.cred):
            self.assertEqual(self.on_phone(p, "/api/plan", raw, headers={"X-Kontor-Confirm": ".".join(W.b64u(x) for x in (cred, cdj, ad, sig))})[0], 403)
        # without Face ID (UV), or a header that is no confirmation
        code, c = self.on_phone(p, "/api/confirm", {"method": "POST", "path": "/api/plan", "body": hashlib.sha256(raw).hexdigest()})
        cdj, ad, sig = key.get(W.b64u_decode(c["challenge"]), flags=W.UP)
        self.assertEqual(self.on_phone(p, "/api/plan", raw, headers={"X-Kontor-Confirm": ".".join(W.b64u(x) for x in (key.cred, cdj, ad, sig))})[0], 403)
        for junk in ("x", "a.b.c.d", "." * 3, "A" * 7000, "!!.##.$$.%%"):
            self.assertEqual(self.on_phone(p, "/api/plan", raw, headers={"X-Kontor-Confirm": junk})[0], 403)
        # the challenge only for changes that need one; and never for what stays at the Mac
        for bad in ({"method": "GET", "path": "/api/plan"}, {"method": "POST", "path": "/api/lock"}, {"method": "POST", "path": "/api/reset"},
                    {"method": "POST", "path": "/api/plan", "body": "x"}, {"method": "POST", "path": "https://evil.example/api/plan"}):
            self.assertEqual(self.on_phone(p, "/api/confirm", dict({"body": "0" * 64}, **bad))[0], 400, bad)
        # CSRF stays: a confirmed request without the session's token is refused
        code, c = self.on_phone(p, "/api/confirm", {"method": "POST", "path": "/api/plan", "body": hashlib.sha256(raw).hexdigest()})
        cdj, ad, sig = key.get(W.b64u_decode(c["challenge"]))
        csrf, p.csrf = p.csrf, None
        code, r = self.on_phone(p, "/api/plan", raw, headers={"X-Kontor-Confirm": ".".join(W.b64u(x) for x in (key.cred, cdj, ad, sig))})
        self.assertEqual((code, r.get("csrf")), (403, "invalid"))
        p.csrf = csrf

    def area(self):
        import fixtures as F
        return F.uid("priv")

    def test_every_change_waits_for_face_id_and_the_mac_keeps_its_own(self):
        """Every POST request of the service, from an added iPhone without a confirmation: refused before anything is done --
        unless it changes nothing (CONFIRM_FREE, CONFIRM_MAYBE as asked) or is a way in."""
        import re
        p, key = self.pair()
        with open(os.path.join(os.path.dirname(__file__), "..", "service.py"), encoding="utf-8") as f:
            src = f.read()
        handler = src[src.index("def make_handler("):src.index("\nBACKUP_ITER")]
        posts = set(self.MA.DEMO_POST | self.MA.DEMO_NEVER) - set(self.MA.DEMO_GET) - {"/api/offline/verifier", "/api/log", "/api/remote/acl",
                                                                                         "/api/timemachine", "/api/diagnostics", "/api/update/status",
                                                                                         "/api/history/mm-status", "/api/devices"}
        posts |= {p_ for p_ in set(re.findall(r'path == "(/api/[^"]+)"', handler)) if p_ not in self.MA.DEMO_GET}
        self.assertGreater(len(posts), 70)
        self.assertTrue(self.MA.MAC_ONLY <= posts and self.MA.CONFIRM_FREE <= posts | {"/api/confirm"})
        free = set(self.MA.CONFIRM_FREE) | set(self.MA.SIGN_IN) | set(self.MA.CONFIRM_MAYBE)
        for path in sorted(posts - free):
            if path == "/api/history/mm-import":
                continue                                                                # (an upload in its own form: MAC_ONLY, below)
            code, r = self.on_phone(p, path, {})
            with self.subTest(path):
                self.assertEqual(code, 403, (path, r))
                self.assertTrue(r.get("confirm") == "needed" or r.get("mac_only"), (path, r))
        for path in sorted(self.MA.MAC_ONLY):                                           # what stays at the Mac: no challenge for it -- and also with Face ID
            self.assertEqual(self.on_phone(p, "/api/confirm", {"method": "POST", "path": path, "body": hashlib.sha256(b"{}").hexdigest()})[0], 400, path)
            code, c = self.on_phone(p, "/api/confirm", {"method": "POST", "path": "/api/language", "body": hashlib.sha256(b"{}").hexdigest()})
            cdj, ad, sig = key.get(W.b64u_decode(c["challenge"]))
            code, r = self.on_phone(p, path, b"{}", headers={"X-Kontor-Confirm": ".".join(W.b64u(x) for x in (key.cred, cdj, ad, sig))})
            with self.subTest(path):
                self.assertEqual((code, r.get("mac_only")), (403, True), path)
        # what changes nothing goes without Face ID; a sync is a test run, a booking only with Face ID
        self.assertEqual(self.on_phone(p, "/api/rules/preview", {"config": self.app.config})[0], 200)
        self.assertEqual(self.on_phone(p, "/api/run", {"dry_run": False, "approval": {}})[1].get("confirm"), "needed")
        runs = []
        self.app.do_run = lambda dry, force, **kw: runs.append(dry)
        self.assertEqual(self.on_phone(p, "/api/run", {})[0], 202)
        self.assertEqual(self.confirmed(p, key, "/api/run", {"dry_run": False})[0][0], 403)          # booking from an iPhone: only what was approved
        self.assertEqual(self.confirmed(p, key, "/api/run", {"dry_run": False, "approval": {}})[0][0], 202)
        self.assertEqual(runs, [True, False])
        # settings: the iPhone saves what it may -- who gets in, the receipts folder and where updates come from stay
        cfg = copy.deepcopy(self.app.config)
        cfg["ui"]["remote_read_only"] = True; cfg["ui"]["lock_minutes"] = 999
        cfg.setdefault("schedule", {})["interval_minutes"] = 47
        (code, r), _h, _b = self.confirmed(p, key, "/api/config", {"config": cfg}, method="PUT")
        self.assertEqual(code, 200, r)
        self.assertEqual(self.app.config["schedule"]["interval_minutes"], 47)
        self.assertFalse(self.app.config["ui"]["remote_read_only"]); self.assertNotEqual(self.app.config["ui"].get("lock_minutes"), 999)
        for change in ({"receipts": dict(cfg.get("receipts") or {}, folder="/")}, {"updates": {"repo": "someone/else"}},
                       {"ui": dict(cfg["ui"], port=9999)}):
            c2 = dict(copy.deepcopy(self.app.config), **change)
            self.assertEqual(self.confirmed(p, key, "/api/config", {"config": c2}, method="PUT")[0][0], 403, change)

    def test_sign_in_with_face_id_and_removing_the_device(self):
        p, key = self.pair()
        s = self.on_phone(self.phone(), "/api/session")[1]
        self.assertEqual((s["passkey"], s["passkey_only"]), (True, True))
        # the password from elsewhere: no longer, once a device is added (it can be switched back on at the Mac)
        code, r = self.on_phone(self.phone(), "/api/login", {"password": "sehr-geheimes-passwort"})
        self.assertEqual((code, r.get("passkey_only")), (403, True))
        code, r, p2 = self.sign_in(key)
        self.assertEqual(code, 200, r)
        self.assertEqual(self.on_phone(p2, "/api/status")[0], 200)
        # replayed, another challenge, a key nobody added, Face ID left out
        code, opt = self.on_phone(self.phone(), "/api/passkey/options", {})
        cdj, ad, sig = key.get(W.b64u_decode(opt["challenge"]))
        login = {"id": W.b64u(key.cred), "client_data": W.b64u(cdj), "auth_data": W.b64u(ad), "signature": W.b64u(sig)}
        self.assertEqual(self.on_phone(self.phone(), "/api/passkey/login", login)[0], 200)
        self.assertEqual(self.on_phone(self.phone(), "/api/passkey/login", login)[0], 401)
        code, opt = self.on_phone(self.phone(), "/api/passkey/options", {})
        stranger = SoftKey()
        cdj, ad, sig = stranger.get(W.b64u_decode(opt["challenge"]))
        self.assertEqual(self.on_phone(self.phone(), "/api/passkey/login", {"id": W.b64u(stranger.cred), "client_data": W.b64u(cdj), "auth_data": W.b64u(ad), "signature": W.b64u(sig)})[0], 401)
        code, opt = self.on_phone(self.phone(), "/api/passkey/options", {})
        cdj, ad, sig = key.get(W.b64u_decode(opt["challenge"]), flags=W.UP)
        self.assertEqual(self.on_phone(self.phone(), "/api/passkey/login", {"id": W.b64u(key.cred), "client_data": W.b64u(cdj), "auth_data": W.b64u(ad), "signature": W.b64u(sig)})[0], 401)
        self.app.sessions.clear_fails("127.0.0.1")
        # switched off at the Mac: the password signs in again (only looking: no device, no Face ID)
        self.assertEqual(self.at_mac("/api/remote", {"action": "settings", "passkey_only": False})[0], 200)
        pw = self.phone()
        code, r = self.on_phone(pw, "/api/login", {"password": "sehr-geheimes-passwort"})
        self.assertEqual(code, 200); pw.csrf = r["csrf"]
        st = self.on_phone(pw, "/api/status")[1]
        self.assertEqual((st["read_only"], st["read_only_why"]), (True, "password"))
        self.assertEqual(self.on_phone(pw, "/api/confirm", {"method": "POST", "path": "/api/plan", "body": "0" * 64})[0], 403)
        # removed at the Mac: its sessions end at once, its passkey works no more
        did = self.at_mac("/api/devices")[1]["devices"][0]["id"]
        code, r = self.at_mac("/api/devices/remove", {"id": did})
        self.assertEqual((code, r["ok"]), (200, True)); self.assertGreaterEqual(r["ended"], 2)
        self.assertEqual(self.on_phone(p, "/api/status")[0], 401); self.assertEqual(self.on_phone(p2, "/api/status")[0], 401)
        self.assertEqual(self.on_phone(self.phone(), "/api/passkey/options", {})[0], 409)          # no device left
        self.pair(key=SoftKey())
        code, opt = self.on_phone(self.phone(), "/api/passkey/options", {})
        cdj, ad, sig = key.get(W.b64u_decode(opt["challenge"]))
        self.assertEqual(self.on_phone(self.phone(), "/api/passkey/login", {"id": W.b64u(key.cred), "client_data": W.b64u(cdj), "auth_data": W.b64u(ad), "signature": W.b64u(sig)})[0], 401)

    def test_after_a_restart_the_password_once_then_face_id(self):
        p, key = self.pair()
        self.app.sessions.drop_all(); self.app.store.close()                          # as after a restart: the data locked
        code, r = self.on_phone(self.phone(), "/api/passkey/options", {})
        self.assertEqual((code, r.get("need_password")), (409, True))
        s = self.on_phone(self.phone(), "/api/session")[1]
        self.assertFalse(s["passkey"]); self.assertTrue(s["waiting"])
        c = self.phone()
        code, r = self.on_phone(c, "/api/login", {"password": "sehr-geheimes-passwort"})
        self.assertEqual((code, r.get("passkey_needed"), r.get("csrf")), (200, True, None))     # the data open -- no session from the password alone
        self.assertTrue(self.app.store.is_open)
        self.assertEqual(self.on_phone(c, "/api/status")[0], 401)
        code, r, c = self.sign_in(key, client=c)
        self.assertEqual(code, 200)
        self.assertEqual(self.on_phone(c, "/api/status")[1]["confirm"], True)

    def test_only_look_and_the_demo(self):
        p, key = self.pair(changes=False)
        self.assertFalse(self.app.remote_changes())
        st = self.on_phone(p, "/api/status")[1]
        self.assertEqual((st["read_only"], st["read_only_why"]), (True, "setting"))
        self.assertEqual(self.on_phone(p, "/api/confirm", {"method": "POST", "path": "/api/plan", "body": "0" * 64})[0], 403)
        self.assertEqual(self.on_phone(p, "/api/plan", {"area": self.area()})[1].get("read_only"), True)
        # the demo from the iPhone with Face ID: a session of the demo that follows this iPhone (it only looks), never its devices
        code, r, d = self.sign_in(key, demo=True)
        self.assertEqual((code, r.get("demo")), (200, True))
        demo = self.app.demo_box.current()[0]
        try:
            self.assertIsNone(demo.devices)
            self.assertTrue(all(not s.get("device") and s.get("opened_by") for s in demo.sessions._s.values()))
            for path in ("/api/devices", "/api/confirm", "/api/passkey/options", "/api/devices/pair"):
                self.assertEqual(self.on_phone(d, path, {} if path != "/api/devices" else None)[0], 403, path)
        finally:
            self.app.demo_box.end()

    def test_failed_attempts_count_like_wrong_passwords(self):
        p, key = self.pair()
        for _ in range(5):                                                             # a guessed link, a passkey nobody added
            self.on_phone(self.phone(), "/api/pair/begin", {"token": secrets.token_urlsafe(32), "name": "x", "password": "sehr-geheimes-passwort"})
        for path in ("/api/passkey/options", "/api/pair/begin", "/api/login"):
            self.assertEqual(self.on_phone(self.phone(), path, {"token": "x" * 43, "password": "sehr-geheimes-passwort"})[0], 429, path)
        self.app.sessions.clear_fails("127.0.0.1")
        code, opt = self.on_phone(self.phone(), "/api/passkey/options", {})
        self.assertEqual(code, 200)
        stranger = SoftKey()
        for _ in range(5):
            cdj, ad, sig = stranger.get(W.b64u_decode(opt["challenge"]))
            self.on_phone(self.phone(), "/api/passkey/login", {"id": W.b64u(stranger.cred), "client_data": W.b64u(cdj), "auth_data": W.b64u(ad), "signature": W.b64u(sig)})
        self.assertEqual(self.on_phone(self.phone(), "/api/passkey/options", {})[0], 429)

    def test_requests_passed_on_by_a_proxy_are_never_answered(self):
        """"tailscale serve" and Funnel pass the Host on and add their own headers: such a request is refused, whatever it asks."""
        for hdr in ({"X-Forwarded-For": "203.0.113.7"}, {"X-Forwarded-Host": "kontor.example"}, {"X-Forwarded-Proto": "https"},
                    {"Forwarded": "for=203.0.113.7"}, {"X-Real-IP": "203.0.113.7"}, {"Tailscale-Funnel-Request": "?1"},
                    {"Tailscale-User-Login": "x@example.com"}, {"x-forwarded-for": "203.0.113.7"}):
            for path, body in (("/api/login", {"password": "sehr-geheimes-passwort"}), ("/api/touchid", {}), ("/api/session", None), ("/api/status", None),
                               ("/", None), ("/api/remote", {"action": "disable"})):
                self.remote[0] = False
                code, r = self.mac.call(path, body, headers=hdr) if path != "/" else (self._raw_get("/", hdr), {})
                with self.subTest(path=path, hdr=hdr):
                    self.assertEqual(code, 403, (path, hdr, r))
        self.assertEqual(self.mac.call("/api/status")[0], 200)                         # without them: as ever
        # a header line Python stops at (space before the colon): what follows would go unseen -- refused as well
        import socket
        for extra in (["X-Forwarded-For : 203.0.113.7"], ["X-Kontor-Background : 1", "X-Forwarded-For: 203.0.113.7"]):
            for line in ("GET / HTTP/1.1", "GET /api/session HTTP/1.1"):
                with socket.create_connection(("127.0.0.1", self.srv.server_address[1])) as c:
                    c.sendall(("\r\n".join([line, "Host: 127.0.0.1:%d" % self.srv.server_address[1]] + extra) + "\r\n\r\n").encode("latin-1"))
                    first = c.recv(64).split(b"\r\n")[0]
                with self.subTest(extra=extra, line=line):
                    self.assertIn(b" 403 ", first + b" ")

    def _raw_get(self, path, headers):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.srv.server_address[1], path), headers=headers)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_while_serve_passes_kontor_on_nothing_signs_in_from_this_mac(self):
        """A plain TCP forward carries no headers: while Tailscale passes Kontor's port on, a request from this Mac's address
        may come from anywhere -- no sign-in, no Touch ID, no first password, nothing that stays at the Mac; unknown blocks nothing."""
        import time as _t
        p, key = self.pair()
        for state, blocked in (("serve", True), ("funnel", True), ("unknown", False), ("none", False)):
            self.app.__dict__["_exposure"] = {"serve": state, "lock": None, "at": _t.time()}
            fresh = Client(self.srv.server_address[1])
            self.remote[0] = False
            code, r = fresh.call("/api/login", {"password": "sehr-geheimes-passwort"})
            with self.subTest(state):
                self.assertEqual(code == 403 and r.get("exposed") is True, blocked, (state, code, r))
                self.assertEqual(fresh.call("/api/session")[1]["exposed"], blocked)
                self.assertEqual(self.mac.call("/api/touchid", {})[1].get("exposed") is True, blocked)
                code, r = self.mac.call("/api/remote", {"action": "settings", "offline_copy": True})
                self.assertEqual(code == 403, blocked, r)                              # a session from before: what stays at the Mac, not now
                self.assertEqual(self.mac.call("/api/devices")[0] == 403, blocked)
                self.assertEqual(self.mac.call("/api/status")[1]["exposed"], blocked)
                self.assertEqual(self.on_phone(p, "/api/status")[0], 200)                # the iPhone (its own address) as before
        self.app.__dict__["_exposure"] = {"serve": "unknown", "lock": None, "at": _t.time()}

    def _no_look(self):
        """A service just started: Tailscale not looked at yet, its first look on its way (the test gives its answers)."""
        self.app.__dict__.pop("_exposure", None)
        self.app.__dict__["_exposure_running"] = True

    def test_nothing_signs_in_at_the_mac_before_tailscale_was_looked_at(self):
        """Right after a start Kontor does not know whether "tailscale serve" passes its port on: a sign-in from this Mac's
        address waits a moment for the first look, then says so -- and goes once the look is there; Tailscale not running is
        known to pass nothing on; a Tailscale that never answers locks nobody out for good."""
        p, key = self.pair()
        self.MA.EXPOSURE_WAIT, wait = 0.05, self.MA.EXPOSURE_WAIT
        try:
            self._no_look()
            fresh = Client(self.srv.server_address[1])
            self.remote[0] = False
            code, r = fresh.call("/api/login", {"password": "sehr-geheimes-passwort"})
            self.assertEqual((code, r.get("checking")), (503, True))
            self.assertEqual(fresh.call("/api/session")[1]["checking"], True)
            self.assertEqual(fresh.call("/api/touchid", {})[1].get("checking"), True)
            self.assertEqual(self.mac.call("/api/remote", {"action": "settings", "offline_copy": True})[0], 503)        # what stays at the Mac: not yet
            self.assertEqual(self.mac.call("/api/devices")[0], 403)
            self.assertEqual(self.on_phone(p, "/api/status")[0], 200)                  # the iPhone (its own address) as before
            for _ in range(self.MA.EXPOSURE_TRIES - 1):                                # looks without an answer: still locked
                self.app._exposure_set(None)
                self.assertEqual(self.app.exposure()["serve"], "pending")
                self.remote[0] = False
                self.assertEqual(fresh.call("/api/login", {"password": "sehr-geheimes-passwort"})[0], 503)
            self.app._exposure_set({"serve": "unknown", "lock": None})                 # ... never an answer: nobody locked out for good
            self.assertEqual(self.app.exposure()["serve"], "unknown")
            self.remote[0] = False
            self.assertEqual(fresh.call("/api/login", {"password": "sehr-geheimes-passwort"})[0], 200)
            for answer in ({"serve": "off", "lock": None}, {"serve": "none", "lock": True}):     # Tailscale does not run / passes nothing on
                self._no_look()
                self.app._exposure_set(answer)
                self.remote[0] = False
                self.assertEqual(Client(self.srv.server_address[1]).call("/api/login", {"password": "sehr-geheimes-passwort"})[0], 200, answer)
        finally:
            self.MA.EXPOSURE_WAIT = wait
            self.app.__dict__["_exposure_running"] = False
        # the first look after a start comes while the sign-in waits for it: it goes through
        self.app.__dict__.pop("_exposure", None)
        self.answer = {"serve": "none", "lock": None}
        self.remote[0] = False
        code, r = Client(self.srv.server_address[1]).call("/api/login", {"password": "sehr-geheimes-passwort"})
        self.assertEqual(code, 200, r)
        self.assertEqual(self.app.exposure()["serve"], "none")

    def test_looked_at_often_in_the_first_minutes(self):
        """Tailscale may come up after Kontor (both start at sign-in to the Mac): in the first minutes after the start Kontor
        looks again every few seconds even after an answer "nothing passed on" -- later once a minute."""
        import time
        started = []
        keep = self.app._exposure_run
        self.app._exposure_run = lambda: started.append(1) or self.app.__dict__.__setitem__("_exposure_running", False)
        try:
            self.app.__dict__["_exposure_running"] = False
            self.app.__dict__["_exposure"] = {"serve": "none", "lock": None, "at": time.time() - self.MA.EXPOSURE_RETRY - 1, "failed": 0}
            self.app.__dict__["_exposure_start"] = time.time()                           # young: looked at again
            self.app.exposure_tick()
            t0 = time.time()
            while not started and time.time() - t0 < 5:                                  # (the look runs in a thread of its own)
                time.sleep(0.02)
            self.assertEqual(started, [1]); started.clear()
            self.app.__dict__["_exposure_start"] = time.time() - self.MA.EXPOSURE_YOUNG - 1  # later: not yet
            self.app.__dict__["_exposure"]["at"] = time.time() - self.MA.EXPOSURE_RETRY - 1
            self.app.exposure_tick()
            self.assertEqual(started, [])
        finally:
            self.app._exposure_run = keep
            self.app.__dict__["_exposure_running"] = False

    def test_a_look_without_an_answer_keeps_what_was_known(self):
        self.app.__dict__["_exposure_running"] = True                                  # (no look of its own meanwhile)
        try:
            self.app._exposure_set({"serve": "serve", "lock": False})
            for failed in (None, {"serve": "unknown", "lock": None}, {"serve": "pending"}):
                self.app._exposure_set(failed)
                self.assertEqual((self.app.exposure()["serve"], self.app.exposure()["lock"]), ("serve", False), failed)
                self.remote[0] = False
                code, r = Client(self.srv.server_address[1]).call("/api/login", {"password": "sehr-geheimes-passwort"})
                self.assertEqual((code, r.get("exposed")), (403, True), failed)
            self.app._exposure_set({"serve": "none", "lock": True})                    # an answer: off now
            self.app._exposure_set(None)
            self.assertEqual(self.app.exposure()["serve"], "none")
            self.remote[0] = False
            self.assertEqual(Client(self.srv.server_address[1]).call("/api/login", {"password": "sehr-geheimes-passwort"})[0], 200)
        finally:
            self.app.__dict__["_exposure_running"] = False

    def test_it_is_looked_at_again_right_before_a_session_at_the_mac(self):
        """Found passed on while a sign-in is on its way (a Touch ID window open for minutes, the password being checked): no
        session comes of it."""
        self.app.__dict__["_exposure_running"] = True
        orig = (self.MA.auth.touchid_available, self.app.sign_in)
        try:
            self.app._exposure_set({"serve": "none", "lock": None})
            self.MA.auth.touchid_available = lambda: True
            self.app.touchid_on = lambda: True
            self.app.sign_in_touchid = lambda demo, rid: self.app._exposure_set({"serve": "serve", "lock": None}) is not None
            n = len(self.app.sessions._s)
            self.remote[0] = False
            code, r = Client(self.srv.server_address[1]).call("/api/touchid", {})
            self.assertEqual((code, r.get("exposed")), (403, True), r)
            self.app._exposure_set({"serve": "none", "lock": None})
            n = len(self.app.sessions._s)
            self.app.sign_in = lambda pw, _f=orig[1]: (self.app._exposure_set({"serve": "funnel", "lock": None}), _f(pw))[1]
            code, r = Client(self.srv.server_address[1]).call("/api/login", {"password": "sehr-geheimes-passwort"})
            self.assertEqual((code, r.get("exposed")), (403, True), r)
            self.assertEqual(len(self.app.sessions._s), 0)                             # (and the session from before: ended)
            self.assertLessEqual(len(self.app.sessions._s), n)
        finally:
            self.MA.auth.touchid_available, self.app.sign_in = orig
            for k in ("touchid_on", "sign_in_touchid"):
                self.app.__dict__.pop(k, None)
            self.app.__dict__["_exposure_running"] = False

    def test_found_passed_on_ends_every_session_at_the_mac(self):
        """Sessions signed in at this Mac's own address before it was found may have come from elsewhere: they end (also the
        demo's); the iPhone's go on. Off again: signing in at the Mac works as before."""
        self.app.__dict__["_exposure_running"] = True
        p, key = self.pair()
        code, r, d = self.sign_in(key, demo=True)                                      # the demo: from the iPhone ...
        self.assertEqual(code, 200)
        try:
            md = Client(self.srv.server_address[1])                                    # ... and at the Mac
            self.remote[0] = False
            code, r = md.call("/api/login", {"password": "sehr-geheimes-passwort", "demo": True})
            self.assertEqual((code, r.get("demo")), (200, True), r)
            md.csrf = r["csrf"]
            self.assertEqual(self.mac.call("/api/status")[0], 200)
            self.app._exposure_set({"serve": "serve", "lock": None})
            self.remote[0] = False
            self.assertEqual(self.mac.call("/api/status")[0], 401)
            self.assertEqual(md.call("/api/status")[0], 401)
            self.assertEqual(self.on_phone(p, "/api/status")[0], 200)
            self.assertEqual(self.on_phone(d, "/api/status")[0], 200)
            self.app._exposure_set({"serve": "none", "lock": None})
            self.remote[0] = False
            code, r = self.mac.call("/api/login", {"password": "sehr-geheimes-passwort"})
            self.assertEqual(code, 200)
        finally:
            self.app.demo_box.end()
            self.app.__dict__["_exposure_running"] = False

    def test_the_demo_follows_the_iphone_that_opened_it(self):
        """In the demo (its assistant uses the real model and the real Tavily key): a session opened with an iPhone's passkey
        follows that iPhone -- "Änderungen vom iPhone", its tick, Face ID for each change (also a yes on the assistant's card);
        one opened with the password only looks."""
        p, key = self.pair()                                                           # may change (the first, ticked)
        p2, key2 = self.pair(changes=False, name="Nur ansehen")
        self.at_mac("/api/remote", {"action": "settings", "passkey_only": False})
        code, r, d = self.sign_in(key, demo=True)
        self.assertEqual(code, 200)
        try:
            code, r, d2 = self.sign_in(key2, demo=True)
            self.assertEqual(code, 200)
            dp = self.phone()
            code, r = self.on_phone(dp, "/api/login", {"password": "sehr-geheimes-passwort", "demo": True})
            self.assertEqual((code, r.get("demo")), (200, True), r)
            dp.csrf = r["csrf"]
            card = {"job": "x", "id": "y", "ok": True}
            for client, why in ((d2, "device"), (dp, "password")):
                st = self.on_phone(client, "/api/status")[1]
                self.assertEqual((st["read_only"], st["read_only_why"], st["confirm"]), (True, why, False))
                self.assertEqual(self.on_phone(client, "/api/assistant/confirm", card)[1].get("read_only"), True, why)
                self.assertEqual(self.on_phone(client, "/api/confirm", {"method": "POST", "path": "/api/plan", "body": "0" * 64})[0], 403, why)
            st = self.on_phone(d, "/api/status")[1]
            self.assertEqual((st["read_only"], st["confirm"]), (False, True))
            code, r = self.on_phone(d, "/api/assistant/confirm", card)
            self.assertEqual((code, r.get("confirm")), (403, "needed"))                 # a yes on the card: Face ID first
            (code, r), hdr, raw = self.confirmed(d, key, "/api/assistant/confirm", card)
            self.assertEqual((code, r.get("error")), (403, self.MA.tr("s_nur_von_diesem_mac_aus")))          # confirmed -- the assistant's right "vom iPhone" decides
            cfg = copy.deepcopy(self.app.config)
            cfg.setdefault("assistant", {}).setdefault("rights", {})["remote"] = True
            self.app.save_config(cfg)
            self.app.demo_box.current()[0].follow_real()
            self.assertEqual(self.on_phone(d, "/api/assistant/confirm", card)[1].get("confirm"), "needed")
            (code, r), hdr, raw = self.confirmed(d, key, "/api/assistant/confirm", card)
            self.assertEqual(code, 400, r)                                             # through to the assistant (nothing waits under this id)
            # a confirmation made in the demo is for the demo's session only -- not for the real Kontor's
            raw = json.dumps(card).encode()
            code, c = self.on_phone(d, "/api/confirm", {"method": "POST", "path": "/api/assistant/confirm", "body": hashlib.sha256(raw).hexdigest()})
            cdj, ad, sig = key.get(W.b64u_decode(c["challenge"]))
            hdr = ".".join(W.b64u(x) for x in (key.cred, cdj, ad, sig))
            self.assertEqual(self.on_phone(p, "/api/assistant/confirm", raw, headers={"X-Kontor-Confirm": hdr})[1].get("confirm"), "needed")
            self.at_mac("/api/remote", {"action": "settings", "remote_read_only": True})          # changes from the iPhone off: the demo too
            self.assertEqual(self.on_phone(d, "/api/status")[1]["read_only_why"], "setting")
            self.assertEqual(self.on_phone(d, "/api/assistant/confirm", card)[1].get("read_only"), True)
        finally:
            self.app.demo_box.end()

    def test_a_passing_read_error_of_the_device_list_ends_nothing(self):
        """devices.json not readable for a moment (openssl, the disk): sessions stay, nothing changes from them and nobody
        signs in with a passkey meanwhile (not counted); afterwards as before."""
        import storage
        p, key = self.pair()
        st, orig = self.app.store, self.app.store.load_shared

        def flaky(name, default=None):
            if name == "devices.json":
                raise storage.StoreError("openssl not there")
            return orig(name, default)
        st.load_shared = flaky
        try:
            status = self.on_phone(p, "/api/status")
            self.assertEqual(status[0], 200)
            self.assertEqual((status[1]["read_only"], status[1]["trusted"]), (True, False))
            self.assertEqual(self.on_phone(p, "/api/language", {"language": "de"})[0], 403)
            self.assertEqual(self.on_phone(self.phone(), "/api/passkey/options", {})[0], 503)
            self.assertEqual(self.app.sessions.locked("127.0.0.1"), 0)
            code, r = self.at_mac("/api/devices/set", {"id": "d" + "0" * 16, "changes": True})
            self.assertEqual(code, 200)
            code, r = self.at_mac("/api/remote", {"action": "settings", "passkey_only": True})
            self.assertEqual(self.app.devices.present(None), None)
        finally:
            st.load_shared = orig
        self.assertEqual(self.on_phone(p, "/api/status")[1]["confirm"], True)
        self.assertEqual(self.confirmed(p, key, "/api/language", {"language": "de"})[0][0], 200)

    def test_the_device_list_not_writable_says_so(self):
        p, key = self.pair()
        did = self.app.devices.all()[0]["id"]
        self.app.devices._closed = {"kept": "", "time": ""}
        try:
            self.assertEqual(self.at_mac("/api/devices/set", {"id": did, "changes": False})[1], {"ok": False})      # (none there to change)
            code, r = self.at_mac("/api/remote", {"action": "settings", "passkey_only": False})
            self.assertEqual(r.get("error") or r.get("text"), self.MA.tr("s_pk_liste_nicht_speicherbar"), r)
        finally:
            self.app.devices._closed = None
        import storage
        st, orig = self.app.store, self.app.store.update
        token = self.link()
        k2, p2 = SoftKey(), self.phone()
        code, opt = self.on_phone(p2, "/api/pair/begin", {"token": token, "name": "x", "password": "sehr-geheimes-passwort"})
        cdj, att = k2.create(W.b64u_decode(opt["challenge"]))
        st.update = lambda name, fn, default=None: (_ for _ in ()).throw(storage.StoreError("disk full")) if name == "devices.json" else orig(name, fn, default)
        try:
            code, r = self.on_phone(p2, "/api/pair/finish", {"token": token, "id": W.b64u(k2.cred), "client_data": W.b64u(cdj), "attestation": W.b64u(att)})
        finally:
            st.update = orig
        self.assertEqual((code, r.get("error")), (409, self.MA.tr("s_pk_liste_nicht_speicherbar")))

    def test_the_first_iphone_switches_changes_on_only_once_added_with_the_tick(self):
        token = self.link(changes=True)
        self.at_mac("/api/devices/pair", {"action": "cancel"})                         # cancelled: nothing switched
        self.assertFalse(self.app.remote_changes())
        self.link(changes=True)
        self.app.devices._pair["until"] = 0                                            # ran out: nothing switched
        self.assertIsNone(self.app.devices.pairing_state())
        self.assertFalse(self.app.remote_changes())
        token = self.link(changes=True)
        self.at_mac("/api/devices/pair", {"action": "changes", "changes": False})      # the tick taken away before it was added
        key, p = SoftKey(), self.phone()
        code, opt = self.on_phone(p, "/api/pair/begin", {"token": token, "name": "x", "password": "sehr-geheimes-passwort"})
        cdj, att = key.create(W.b64u_decode(opt["challenge"]))
        self.assertEqual(self.on_phone(p, "/api/pair/finish", {"token": token, "id": W.b64u(key.cred), "client_data": W.b64u(cdj), "attestation": W.b64u(att)})[0], 200)
        self.assertFalse(self.app.remote_changes())
        self.pair(changes=True, name="Zweites")                                        # not the first any more: switches nothing
        self.assertFalse(self.app.remote_changes())

    def test_one_flag_per_device_and_pairing_never_switches_all(self):
        p, key = self.pair()                                                           # the first: ticked -- changes from the iPhone on
        self.assertTrue(self.app.remote_changes())
        token = self.link(changes=True)
        self.assertEqual(self.at_mac("/api/remote", {"action": "settings", "remote_read_only": True})[0], 200)       # meanwhile: only look
        key2, p2 = SoftKey(), self.phone()
        code, opt = self.on_phone(p2, "/api/pair/begin", {"token": token, "name": "Zweites", "password": "sehr-geheimes-passwort"})
        cdj, att = key2.create(W.b64u_decode(opt["challenge"]))
        code, r = self.on_phone(p2, "/api/pair/finish", {"token": token, "id": W.b64u(key2.cred), "client_data": W.b64u(cdj), "attestation": W.b64u(att)})
        self.assertEqual(code, 200); p2.csrf = r["csrf"]
        self.assertFalse(self.app.remote_changes())                                    # completing a pairing switches nothing for all
        self.assertEqual(self.at_mac("/api/remote", {"action": "settings", "remote_read_only": False})[0], 200)
        devs = {d["name"]: d for d in self.at_mac("/api/devices")[1]["devices"]}
        self.assertEqual((devs["Testgerät"]["changes"], devs["Zweites"]["changes"]), (True, True))
        self.assertEqual(self.at_mac("/api/devices/set", {"id": devs["Zweites"]["id"], "changes": False})[1]["ok"], True)
        self.assertEqual(self.on_phone(p2, "/api/status")[1]["read_only_why"], "device")
        code, r = self.on_phone(p2, "/api/confirm", {"method": "POST", "path": "/api/language", "body": "0" * 64})
        self.assertEqual((code, r.get("read_only")), (403, True))
        self.assertEqual(self.on_phone(p2, "/api/language", {"language": "de"})[0], 403)
        self.assertEqual(self.confirmed(p, key, "/api/language", {"language": "de"})[0][0], 200)          # the other one may
        self.assertEqual(self.on_phone(p, "/api/devices/set", {"id": devs["Zweites"]["id"], "changes": True})[1].get("mac_only"), True)

    def test_the_link_ends_with_the_macs_session(self):
        token = self.link()
        self.at_mac("/api/lock", {})                                                   # locked at the Mac: the link is gone
        self.assertIsNone(self.app.devices.pairing_state())
        code, r = self.mac.call("/api/login", {"password": "sehr-geheimes-passwort"})
        self.mac.csrf = r["csrf"]
        token = self.link()
        self.app.sessions.drop_all()                                                   # the Mac's session over (idle, ended)
        self.assertEqual(self.on_phone(self.phone(), "/api/pair/begin", {"token": token, "name": "x", "password": "sehr-geheimes-passwort"})[0], 403)

    def test_a_removed_iphone_ends_the_demo_it_opened(self):
        p, key = self.pair()
        code, r, d = self.sign_in(key, demo=True)
        self.assertEqual(code, 200)
        try:
            self.assertEqual(self.on_phone(d, "/api/status")[0], 200)
            did = self.app.devices.all()[0]["id"]
            self.at_mac("/api/devices/remove", {"id": did})
            self.assertEqual(self.on_phone(d, "/api/status")[0], 401)
            code, r, d2 = self.sign_in(self.pair()[1], demo=True)                    # ... also when the list goes another way (damaged)
            self.app.devices._closed = {"kept": "", "time": ""}
            self.assertEqual(self.on_phone(d2, "/api/status")[0], 401)
        finally:
            self.app.devices._closed = None
            self.app.demo_box.end()

    def test_a_damaged_device_list_over_http(self):
        p, key = self.pair()
        self.at_mac("/api/remote", {"action": "settings", "passkey_only": False})
        path = os.path.join(self.dir, "devices.json.enc")
        raw = bytearray(open(path, "rb").read()); raw[len(raw) // 2] ^= 0x01
        with open(path, "wb") as f:
            f.write(bytes(raw))
        self.app.store._cache.clear()
        for path_, body in (("/api/devices", None), ("/api/remote", None), ("/api/devices/remove", {"id": "d0000000000000000"})):
            self.assertEqual(self.at_mac(path_, body)[0], 200, path_)
        self.assertTrue([n for n in os.listdir(self.dir) if n.startswith("devices.json.enc.damaged-")])
        st = self.at_mac("/api/devices")[1]
        self.assertEqual(st["devices"], []); self.assertTrue(st["damaged"]["kept"].startswith("devices.json.enc.damaged-"))
        self.assertTrue(self.app.passkey_only())                                       # fail closed
        self.assertEqual(self.on_phone(p, "/api/status")[0], 401)                      # its session: over
        self.assertEqual(self.on_phone(self.phone(), "/api/session")[0], 200)
        code, r = self.on_phone(self.phone(), "/api/login", {"password": "sehr-geheimes-passwort"})
        self.assertEqual((code, r.get("passkey_only")), (403, True))                   # no password session from elsewhere
        self.assertEqual(self.at_mac("/api/status")[0], 200)                           # the Mac: as ever

    def test_sign_in_challenges_have_a_budget_and_confirmations_stay(self):
        p, key = self.pair()
        raw = json.dumps({"language": "de"}).encode()
        code, c = self.on_phone(p, "/api/confirm", {"method": "POST", "path": "/api/language", "body": hashlib.sha256(raw).hexdigest()})
        codes = [self.on_phone(self.phone(), "/api/passkey/options", {})[0] for _ in range(70)]
        self.assertIn(429, codes); self.assertLessEqual(codes.count(200), 10)
        cdj, ad, sig = key.get(W.b64u_decode(c["challenge"]))
        self.assertEqual(self.on_phone(p, "/api/language", raw, headers={"X-Kontor-Confirm": ".".join(W.b64u(x) for x in (key.cred, cdj, ad, sig))})[0], 200)

    def test_what_changes_nothing_and_what_does(self):
        p, key = self.pair()
        runs = []
        self.app.do_run = lambda dry, force, **kw: runs.append((dry, kw.get("write")))
        self.assertEqual(self.on_phone(p, "/api/run", {})[0], 202)                     # a test run from the iPhone: nothing into MoneyMoney
        self.at_mac("/api/run", {"dry_run": True})
        self.assertEqual(runs, [(True, False), (True, True)])
        self.assertEqual(self.on_phone(p, "/api/properties/calculate", {"inputs": {}})[0], 200)      # only computes
        self.assertTrue(self.MA.remote_change("/api/assistant/confirm", {"ok": True}))  # a yes on a card (also to the internet): Face ID
        self.assertFalse(self.MA.remote_change("/api/assistant/confirm", {"ok": False}))
        # notes and the change log from an iPhone only with the assistant's right "vom iPhone"
        self.assertFalse(self.MA.assistant_mod.settings(self.app.config)["rights"]["remote"])
        self.assertEqual(self.on_phone(p, "/api/assistant/memory")[0], 403)
        self.assertEqual(self.confirmed(p, key, "/api/assistant/memory", {"action": "add", "text": "x"})[0][0], 403)
        # Tailscale's rules: the Mac or an added iPhone, not a session signed in with the password
        self.assertEqual(self.on_phone(p, "/api/remote/acl")[0], 200)
        self.at_mac("/api/remote", {"action": "settings", "passkey_only": False})
        pw = self.phone()
        code, r = self.on_phone(pw, "/api/login", {"password": "sehr-geheimes-passwort"}); pw.csrf = r["csrf"]
        self.assertEqual(self.on_phone(pw, "/api/remote/acl")[0], 403)

    def test_the_moneymoney_upload_refused_from_an_iphone_answers(self):
        p, key = self.pair()
        self.remote[0] = True
        req = urllib.request.Request("http://127.0.0.1:%d/api/history/mm-import" % self.srv.server_address[1], data=os.urandom(300000), method="POST",
                                     headers={"Content-Type": "application/octet-stream", "X-CSRF-Token": p.csrf})
        try:
            p.opener.open(req)
            code, r = 200, {}
        except urllib.error.HTTPError as e:
            code, r = e.code, json.loads(e.read().decode() or "{}")
        self.assertEqual((code, r.get("mac_only")), (403, True))

    def test_reset_forgets_the_devices(self):
        self.pair()
        self.assertTrue(self.app.devices.all())
        self.assertEqual(self.at_mac("/api/reset", {"password": "sehr-geheimes-passwort"})[0], 200)
        self.assertEqual(self.app.devices.all(), [])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "devices.json.enc")))


class BrowserFaceId(unittest.TestCase):
    """The pages with Chromium's virtual authenticator in place of Face ID: the Mac shows the QR code's link, the iPhone adds
    itself with it, a change goes through only confirmed (refused when Face ID fails), signing in again with Face ID, and a
    device removed at the Mac is signed out. The iPhone's page runs on http://localhost (a secure context, as https is for
    the real one), its requests counted as from another device over https (patched; the checks behind are the real ones)."""

    def test_pairing_and_a_confirmed_change(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright missing")
        import service as MA
        import fixtures as F
        import test_e2e as E
        d = tempfile.mkdtemp(prefix="kontor-pkb-")
        store = F.new_store(d)
        cfg = E.config_for_test(os.path.join(d, "Belege"))
        cfg["ui"] = dict(cfg.get("ui") or {}, bind="100.64.1.2", tls_cert="/tmp/tls/%s.crt" % RP, tls_key="/tmp/tls/%s.key" % RP, port=PORT)
        store.save("config.json", cfg)
        store.save("state.json", dict(E.ALL_NEW))
        E.reset_mock()
        E.patch_today()
        app = MA.App(store, d, bridge_factory=E.MockBridge)
        app.tailscale = lambda fresh=False: {"found": False}
        srv = ThreadingHTTPServer(("127.0.0.1", 0), MA.make_handler(app))
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        app.passkey_site = lambda: ("localhost", "http://localhost:%d" % port)
        remote = [False]
        orig = (MA.auth.is_loopback, MA.tls_connection)
        MA.auth.is_loopback = lambda addr: not remote[0] and addr in ("127.0.0.1", "::1", "localhost")
        MA.tls_connection = lambda conn: remote[0]
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                mac = b.new_page(viewport={"width": 1360, "height": 900})
                mac.goto("http://127.0.0.1:%d/" % port)
                mac.wait_for_selector("#login-pw")
                mac.fill("#login-pw", "sehr-geheimes-passwort"); mac.fill("#login-pw2", "sehr-geheimes-passwort"); mac.click("#login-btn")
                mac.wait_for_selector("#shell:not(.hidden)")
                mac.goto("http://127.0.0.1:%d/#settings/access" % port)
                mac.wait_for_selector("#dev-add:not([disabled])")
                mac.click("#dev-add")
                mac.wait_for_selector(".pair-card .qr svg path")
                url = mac.get_attribute("#pair-copy", "data-url")
                self.assertIn("#pair=", url)
                token = url.split("#pair=")[1]
                self.assertTrue(mac.is_checked("#pair-changes"))                         # the first iPhone: changes allowed
                mac.close()
                remote[0] = True
                ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
                ctx.add_init_script("localStorage.setItem('kontor.testRemote', '1')")
                phone = ctx.new_page()
                cdp = ctx.new_cdp_session(phone)
                cdp.send("WebAuthn.enable")
                auth = cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {"protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
                                                                                  "hasUserVerification": True, "isUserVerified": True,
                                                                                  "automaticPresenceSimulation": True}})["authenticatorId"]
                phone.goto("http://localhost:%d/#pair=%s" % (port, token))
                phone.wait_for_selector("#pair-form:not(.hidden)")
                self.assertNotIn("pair=", phone.url)                                      # the link is out of the address at once
                phone.fill("#pair-name", "Testgerät"); phone.fill("#pair-pw", "sehr-geheimes-passwort"); phone.click("#pair-btn")
                phone.wait_for_selector("#shell:not(.hidden)", timeout=30000)
                self.assertEqual([x["name"] for x in app.devices.all()], ["Testgerät"])
                self.assertTrue(app.remote_changes())
                phone.wait_for_function("() => S.STATUS && S.STATUS.confirm === true")
                # a change: Face ID (the virtual authenticator) for exactly this request, then it is taken
                import categorize
                done = lambda: categorize.load(store).get("rule_done") or []
                got = phone.evaluate("() => api('/api/categories/proposals', {done_items: 'test-a'}).then(r => r.ok, e => 'error: ' + e.message)")
                self.assertEqual(got, True)
                self.assertEqual(done(), ["test-a"])
                # Face ID fails: refused at once, the page offers a tap (Safari wants one) -- cancelled, nothing changes
                cdp.send("WebAuthn.setUserVerified", {"authenticatorId": auth, "isUserVerified": False})
                phone.evaluate("() => { window.__r = api('/api/categories/proposals', {done_items: 'test-b'}).then(r => 'taken', e => 'refused: ' + e.message); }")
                phone.wait_for_selector("#pk-tap button[data-a='no']")
                phone.click("#pk-tap button[data-a='no']")
                phone.wait_for_function("() => window.__r && true")
                self.assertTrue(phone.evaluate("() => window.__r").startswith("refused"))
                self.assertEqual(done(), ["test-a"])
                cdp.send("WebAuthn.setUserVerified", {"authenticatorId": auth, "isUserVerified": True})
                # locked, then signed in again with Face ID
                phone.evaluate("() => lockNow()")
                phone.wait_for_selector("#fid-box:not(.hidden)")
                self.assertFalse(phone.is_visible("#login-pw"))                            # only Face ID once a device is added
                phone.click("#fid-btn")
                phone.wait_for_selector("#shell:not(.hidden)")
                # removed at the Mac: signed out with its next request
                remote[0] = False
                did = app.devices.all()[0]["id"]
                app.devices.remove(did); app.sessions.drop_device(did)
                remote[0] = True
                phone.evaluate("() => api('/api/status').catch(() => null)")
                phone.wait_for_selector("#login:not(.hidden)")
                b.close()
        finally:
            MA.auth.is_loopback, MA.tls_connection = orig
            srv.shutdown(); srv.server_close()
            shutil.rmtree(d, ignore_errors=True)


    def test_setup_while_tailscale_is_looked_at(self):
        """Right after a start (the first look at Tailscale on its way): the page asks for the password as always -- no note
        about Tailscale before anything waits for it; the password sent meanwhile waits and goes by itself once the look is there."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright missing")
        import service as MA
        import fixtures as F
        import test_e2e as E
        d = tempfile.mkdtemp(prefix="kontor-pkc-")
        store = F.new_store(d)
        store.save("config.json", E.config_for_test(os.path.join(d, "Belege")))
        store.save("state.json", dict(E.ALL_NEW))
        E.reset_mock()
        E.patch_today()
        app = MA.App(store, d, bridge_factory=E.MockBridge)
        app.tailscale = lambda fresh=False: {"found": False}
        app.__dict__.pop("_exposure", None); app.__dict__["_exposure_running"] = True      # the first look: on its way
        wait, MA.EXPOSURE_WAIT = MA.EXPOSURE_WAIT, 0.05
        srv = ThreadingHTTPServer(("127.0.0.1", 0), MA.make_handler(app))
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                pg = b.new_page(viewport={"width": 1360, "height": 900})
                pg.goto("http://127.0.0.1:%d/" % port)
                pg.wait_for_selector("#login-pw2")
                self.assertEqual(pg.inner_text("#login-err").strip(), "")
                pg.fill("#login-pw", "sehr-geheimes-passwort"); pg.fill("#login-pw2", "sehr-geheimes-passwort"); pg.click("#login-btn")
                E.until(pg, "document.querySelector('#login-err').textContent.length > 0")      # it waits -- and says so
                self.assertFalse(pg.evaluate("!document.querySelector('#shell').classList.contains('hidden')"))
                app._exposure_set({"serve": "off", "lock": None}, running=False)              # the look is there: it goes by itself
                pg.wait_for_selector("#shell:not(.hidden)", timeout=15000)
                b.close()
        finally:
            MA.EXPOSURE_WAIT = wait
            srv.shutdown(); srv.server_close()
            shutil.rmtree(d, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
