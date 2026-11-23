"""Passkeys (WebAuthn) for the iPhone: checking what it sends -- standard library only, verification only.

Kontor never holds a private key: it stays in the iPhone (and the user's iCloud Keychain) and signs only after Face ID.
Kontor keeps the public key and checks every signature itself:
  - CBOR (RFC 8949): a small strict reader -- definite lengths in their shortest form, no tags, no floats, no duplicate or
    odd map keys, limits for size, depth and number of items; anything else is refused;
  - COSE key (RFC 9052/9053): only ES256 on P-256 with exactly the five fields an authenticator sends; the point must lie on
    the curve;
  - ECDSA on P-256 (FIPS 186-4, SEC 1): verification in Python's own integers; r and s within 1..n-1; the signature in its
    strict DER form;
  - registration and sign-in (WebAuthn Level 2, 7.1 and 7.2): type, challenge, origin and cross-origin in clientDataJSON;
    rpIdHash, the flags UP and UV, attested data only at registration, attestation "none"; the sign count rises when used.
Every check fails closed: Invalid (a reason for the log, never shown in detail).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from typing import Any, Dict, Optional, Tuple


class Invalid(ValueError):
    """What a device sent does not check out."""


# -- base64url (RFC 4648, without padding: how WebAuthn writes binary values) ------------------------------------------
_B64URL = re.compile(r"[A-Za-z0-9_-]*")


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64u_decode(text: Any, limit: int = 4096) -> bytes:
    """Strict: only the alphabet, no padding, no stray bits, at most limit characters."""
    if not isinstance(text, str) or len(text) > limit or len(text) % 4 == 1 or not _B64URL.fullmatch(text):
        raise Invalid("base64url")
    raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    if b64u(raw) != text:
        raise Invalid("base64url")
    return raw


# -- CBOR: the strict subset authenticators use --------------------------------------------------------------------------
CBOR_MAX = 4096          # bytes of an attestation object or authenticator data (an iPhone sends a few hundred)
CBOR_DEPTH = 4           # nesting (the attestation object: map > map/bytes; a COSE key: one map)
CBOR_ITEMS = 32          # entries of one array or map


def _cbor_item(data: bytes, i: int, depth: int) -> Tuple[Any, int]:
    if depth > CBOR_DEPTH:
        raise Invalid("cbor: too deep")
    if i >= len(data):
        raise Invalid("cbor: short")
    major, info = data[i] >> 5, data[i] & 31
    i += 1
    if info < 24:
        arg = info
    elif info <= 27:
        n = 1 << (info - 24)
        if i + n > len(data):
            raise Invalid("cbor: short")
        arg = int.from_bytes(data[i:i + n], "big")
        i += n
        if arg < (24 if n == 1 else 1 << (4 * n)):          # not in its shortest form
            raise Invalid("cbor: not shortest")
    else:                                                     # 28-30 reserved, 31 indefinite length
        raise Invalid("cbor: length")
    if major == 0:
        return arg, i
    if major == 1:
        return -1 - arg, i
    if major in (2, 3):
        if arg > len(data) - i:
            raise Invalid("cbor: short")
        raw, i = bytes(data[i:i + arg]), i + arg
        if major == 2:
            return raw, i
        try:
            return raw.decode("utf-8"), i
        except UnicodeDecodeError:
            raise Invalid("cbor: text") from None
    if major == 4:
        if arg > CBOR_ITEMS:
            raise Invalid("cbor: items")
        out = []
        for _ in range(arg):
            v, i = _cbor_item(data, i, depth + 1)
            out.append(v)
        return out, i
    if major == 5:
        if arg > CBOR_ITEMS:
            raise Invalid("cbor: items")
        m: Dict[Any, Any] = {}
        for _ in range(arg):
            k, i = _cbor_item(data, i, depth + 1)
            if type(k) not in (int, str):                    # (never a bool: True would be the key 1)
                raise Invalid("cbor: key")
            if k in m:
                raise Invalid("cbor: duplicate key")
            m[k], i = _cbor_item(data, i, depth + 1)
        return m, i
    if major == 7 and info in (20, 21, 22):
        return (False, True, None)[info - 20], i
    raise Invalid("cbor: tag or simple value")              # major 6 (tags), floats, other simple values


def cbor_decode(data: Any, limit: int = CBOR_MAX) -> Any:
    """One CBOR item that fills data exactly."""
    if not isinstance(data, (bytes, bytearray)) or not data or len(data) > limit:
        raise Invalid("cbor: size")
    v, i = _cbor_item(bytes(data), 0, 0)
    if i != len(data):
        raise Invalid("cbor: trailing bytes")
    return v


def _cbor_at(data: bytes, i: int) -> Tuple[Any, int]:
    """One CBOR item starting at i (inside authenticator data): (item, where it ends)."""
    return _cbor_item(data, i, 1)


# -- P-256 and ECDSA (verification only) ---------------------------------------------------------------------------------
P = 2 ** 256 - 2 ** 224 + 2 ** 192 + 2 ** 96 - 1
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)
_INF = (0, 1, 0)                                              # the point at infinity (Jacobian, Z = 0)


def on_curve(x: int, y: int) -> bool:
    """A point of P-256 in its affine form (the group has cofactor 1: every such point has order n)."""
    return type(x) is int and type(y) is int and 0 <= x < P and 0 <= y < P and (y * y - (x * x * x + A * x + B)) % P == 0


def _dbl(p: Tuple[int, int, int]) -> Tuple[int, int, int]:
    x1, y1, z1 = p
    if z1 == 0 or y1 == 0:
        return _INF
    delta, gamma = z1 * z1 % P, y1 * y1 % P
    beta = x1 * gamma % P
    alpha = 3 * (x1 - delta) * (x1 + delta) % P               # (a = -3)
    x3 = (alpha * alpha - 8 * beta) % P
    z3 = ((y1 + z1) ** 2 - gamma - delta) % P
    y3 = (alpha * (4 * beta - x3) - 8 * gamma * gamma) % P
    return x3, y3, z3


def _add(p: Tuple[int, int, int], q: Tuple[int, int, int]) -> Tuple[int, int, int]:
    x1, y1, z1 = p
    x2, y2, z2 = q
    if z1 == 0:
        return q
    if z2 == 0:
        return p
    z1z1, z2z2 = z1 * z1 % P, z2 * z2 % P
    u1, u2 = x1 * z2z2 % P, x2 * z1z1 % P
    s1, s2 = y1 * z2 * z2z2 % P, y2 * z1 * z1z1 % P
    if u1 == u2:
        return _dbl(p) if s1 == s2 else _INF
    h = (u2 - u1) % P
    i = 4 * h * h % P
    j = h * i % P
    r = 2 * (s2 - s1) % P
    v = u1 * i % P
    x3 = (r * r - j - 2 * v) % P
    y3 = (r * (v - x3) - 2 * s1 * j) % P
    z3 = ((z1 + z2) ** 2 - z1z1 - z2z2) * h % P
    return x3, y3, z3


def _affine(p: Tuple[int, int, int]) -> Tuple[int, int]:
    zi = pow(p[2], P - 2, P)
    return p[0] * zi * zi % P, p[1] * zi * zi * zi % P


def _mul2(u1: int, p1: Tuple[int, int], u2: int, p2: Tuple[int, int]) -> Tuple[int, int, int]:
    """u1 * p1 + u2 * p2 (Shamir's trick). Only public values go in: its time tells nothing."""
    a, b = (p1[0], p1[1], 1), (p2[0], p2[1], 1)
    both = _add(a, b)
    r = _INF
    for bit in range(max(u1.bit_length(), u2.bit_length()) - 1, -1, -1):
        r = _dbl(r)
        x, y = (u1 >> bit) & 1, (u2 >> bit) & 1
        if x or y:
            r = _add(r, both if x and y else a if x else b)
    return r


def ecdsa_verify(x: int, y: int, digest: bytes, r: int, s: int) -> bool:
    """ECDSA P-256 over a SHA-256 digest: the public key on the curve, r and s within 1..n-1, R not infinity, R.x mod n == r."""
    if not on_curve(x, y) or type(r) is not int or type(s) is not int or not (1 <= r < N and 1 <= s < N):
        return False
    if not isinstance(digest, bytes) or len(digest) != 32:
        return False
    e = int.from_bytes(digest, "big")
    w = pow(s, N - 2, N)
    pt = _mul2(e * w % N, G, r * w % N, (x, y))
    if pt[2] == 0:
        return False
    return _affine(pt)[0] % N == r


def der_signature(sig: Any) -> Tuple[int, int]:
    """(r, s) out of an ECDSA signature in DER: SEQUENCE of two INTEGERs, short lengths, minimal and positive, nothing after."""
    if not isinstance(sig, bytes) or not 8 <= len(sig) <= 72 or sig[0] != 0x30 or sig[1] != len(sig) - 2:
        raise Invalid("signature: DER")
    i, out = 2, []
    for _ in range(2):
        if i + 2 > len(sig) or sig[i] != 0x02:
            raise Invalid("signature: DER")
        n = sig[i + 1]
        i += 2
        if not 1 <= n <= 33 or i + n > len(sig):
            raise Invalid("signature: DER")
        v = sig[i:i + n]
        i += n
        if v[0] & 0x80 or (n > 1 and v[0] == 0 and not v[1] & 0x80):        # negative, or not in its shortest form
            raise Invalid("signature: DER")
        out.append(int.from_bytes(v, "big"))
    if i != len(sig):
        raise Invalid("signature: DER")
    r, s = out
    if not (1 <= r < N and 1 <= s < N):
        raise Invalid("signature: range")
    return r, s


def cose_es256(key: Any) -> Tuple[int, int]:
    """The public key out of a COSE key: kty EC2 (2), alg ES256 (-7), crv P-256 (1), x and y of 32 bytes -- and nothing else."""
    if not isinstance(key, dict) or set(key) != {1, 3, -1, -2, -3}:
        raise Invalid("cose: fields")
    if any(type(key[k]) is not int for k in (1, 3, -1)) or (key[1], key[3], key[-1]) != (2, -7, 1):
        raise Invalid("cose: not ES256 on P-256")
    xb, yb = key[-2], key[-3]
    if not isinstance(xb, bytes) or not isinstance(yb, bytes) or len(xb) != 32 or len(yb) != 32:
        raise Invalid("cose: coordinates")
    x, y = int.from_bytes(xb, "big"), int.from_bytes(yb, "big")
    if not on_curve(x, y):
        raise Invalid("cose: not on the curve")
    return x, y


# -- WebAuthn ------------------------------------------------------------------------------------------------------------
UP, UV, BE, BS, AT, ED = 0x01, 0x04, 0x08, 0x10, 0x40, 0x80
RP_ID = re.compile(r"(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]")
CLIENT_DATA_MAX = 2048
CRED_ID_MAX = 1023


def origin_of(rp_id: str, port: int, scheme: str = "https") -> str:
    """The page's origin as the browser writes it into clientDataJSON."""
    return "%s://%s%s" % (scheme, rp_id, "" if (scheme, port) in (("https", 443), ("http", 80)) else ":%d" % port)


def _no_duplicates(pairs: list) -> dict:
    out: Dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise Invalid("clientDataJSON: duplicate key")
        out[k] = v
    return out


def client_data(cdj: Any) -> dict:
    """clientDataJSON as an object (JSON, UTF-8, an object without duplicate keys, at most CLIENT_DATA_MAX bytes)."""
    if not isinstance(cdj, bytes) or not 16 <= len(cdj) <= CLIENT_DATA_MAX:
        raise Invalid("clientDataJSON: size")
    try:
        cd = json.loads(cdj.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, ValueError, RecursionError) as e:
        raise Invalid("clientDataJSON: %s" % type(e).__name__) from None
    if not isinstance(cd, dict):
        raise Invalid("clientDataJSON: not an object")
    return cd


def challenge_of(cdj: Any) -> bytes:
    """The challenge a clientDataJSON names (to find the one Kontor gave out -- checked again with all the rest)."""
    return b64u_decode(client_data(cdj).get("challenge"), 128)


def check_client_data(cdj: bytes, kind: str, challenge: bytes, origin: str) -> None:
    cd = client_data(cdj)
    if cd.get("type") != kind:
        raise Invalid("clientDataJSON: type")
    if not hmac.compare_digest(b64u_decode(cd.get("challenge"), 128), challenge):
        raise Invalid("clientDataJSON: challenge")
    if cd.get("origin") != origin:
        raise Invalid("clientDataJSON: origin")
    if ("crossOrigin" in cd and cd["crossOrigin"] is not False) or "topOrigin" in cd:      # absent or exactly false (not null, 0, "false")
        raise Invalid("clientDataJSON: cross-origin")
    tb = cd.get("tokenBinding")
    if isinstance(tb, dict) and tb.get("status") == "present":
        raise Invalid("clientDataJSON: token binding")


def auth_data(ad: Any, rp_id: str, attested: bool) -> dict:
    """authenticatorData: rpIdHash of this host, user present and verified (Face ID), BS only with BE; attested credential
    data exactly at registration (AT), extensions (ED) only as a map; nothing after."""
    if not isinstance(ad, bytes) or not 37 <= len(ad) <= CBOR_MAX:
        raise Invalid("authData: size")
    if not isinstance(rp_id, str) or not re.fullmatch(r"[a-z0-9.-]{1,253}", rp_id) or not hmac.compare_digest(ad[:32], hashlib.sha256(rp_id.encode("ascii")).digest()):
        raise Invalid("authData: rpIdHash")
    flags = ad[32]
    if not flags & UP or not flags & UV:
        raise Invalid("authData: not present or not verified")
    if flags & BS and not flags & BE:
        raise Invalid("authData: BS without BE")
    out: Dict[str, Any] = {"flags": flags, "count": int.from_bytes(ad[33:37], "big")}
    i = 37
    if attested:
        if not flags & AT or len(ad) < i + 18:
            raise Invalid("authData: no credential")
        out["aaguid"] = ad[i:i + 16]
        n = int.from_bytes(ad[i + 16:i + 18], "big")
        i += 18
        if not 16 <= n <= CRED_ID_MAX or i + n > len(ad):
            raise Invalid("authData: credential id")
        out["cred_id"], i = ad[i:i + n], i + n
        key, i = _cbor_at(ad, i)
        out["x"], out["y"] = cose_es256(key)
    elif flags & AT:
        raise Invalid("authData: credential data in a sign-in")
    if flags & ED:
        ext, i = _cbor_at(ad, i)
        if not isinstance(ext, dict):
            raise Invalid("authData: extensions")
    if i != len(ad):
        raise Invalid("authData: trailing bytes")
    return out


def verify_registration(cdj: bytes, attestation_object: bytes, challenge: bytes, origin: str, rp_id: str) -> dict:
    """A new passkey (navigator.credentials.create): {"cred_id", "x", "y", "count", "flags", "aaguid"} -- or Invalid."""
    check_client_data(cdj, "webauthn.create", challenge, origin)
    att = cbor_decode(attestation_object)
    if not isinstance(att, dict) or set(att) != {"fmt", "attStmt", "authData"}:
        raise Invalid("attestation: fields")
    if att["fmt"] != "none" or att["attStmt"] != {}:
        raise Invalid("attestation: not none")
    return auth_data(att["authData"], rp_id, attested=True)


def verify_assertion(cdj: bytes, ad: bytes, signature: bytes, challenge: bytes, origin: str, rp_id: str,
                     x: int, y: int, count: int, backup_eligible: Optional[bool] = None) -> dict:
    """A signature of a passkey (navigator.credentials.get) with Face ID over authenticatorData || SHA-256(clientDataJSON),
    by the key (x, y); the sign count must rise when either is not 0 (a copy of the key would fall behind); the flag BE as at
    registration (backup_eligible; WebAuthn L3 -- it never changes for a passkey). The new state {"flags", "count"} -- or Invalid."""
    check_client_data(cdj, "webauthn.get", challenge, origin)
    info = auth_data(ad, rp_id, attested=False)
    if backup_eligible is not None and bool(info["flags"] & BE) != bool(backup_eligible):
        raise Invalid("authData: BE not as at registration")
    r, s = der_signature(signature)
    if not ecdsa_verify(x, y, hashlib.sha256(ad + hashlib.sha256(cdj).digest()).digest(), r, s):
        raise Invalid("signature")
    if (info["count"] or count) and info["count"] <= count:
        raise Invalid("sign count")
    return info
