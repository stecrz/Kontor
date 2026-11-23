"""Tries a Python before Kontor's service is handed to it (pyruntime.py). Run by that Python itself and alone (-I -S: nothing
but its own standard library and Kontor's folder), it loads every part of Kontor -- and with them every part of Python that
Kontor uses -- and looks at what Kontor needs of them: certificates for https, the database, hashes, archives, the Mac's own
libraries, another program started and answered. It opens no connection, reads none of your data and changes nothing (a
made-up database of one row lies in a temporary folder of its own for a moment).

Its answer is one line (JSON) on stdout: {"ok": true, "version": ...} -- or {"ok": false, "error": ...} and exit code 1.
Kontor takes a Python only when the answer is "ok" and the version is the one it loaded.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def parts() -> None:
    """Every part of Kontor, loaded once -- and with them every part of Python they load themselves (the few Kontor loads
    only when it needs them are tried in works(); tests/test_python.py keeps both true as the program grows)."""
    class Loaded:
        import access, assistant, auth, categorize, changelog, core, demo, excel, history_import, i18n, kontor, llm_local, mac_app
        import memory, mm_bridge, mm_categories, mm_history, model, pdf_tables, pyboot, pyruntime, realestate, receipt_text
        import receipts, report, rules, security_names, service, storage, table_text, tax, tls_cert, update_guard, updates
        import web_reader, web_search, webauthn, devices, qr


def certificates_and_database() -> dict:
    """https has a list of certificates to check servers against (the Mac's own, where this Python looks for it), and the
    database works -- nothing is connected to, no file opened."""
    import sqlite3
    import ssl
    ctx = ssl.create_default_context()
    where = ssl.get_default_verify_paths()
    folder = where.capath if where.capath and os.path.isdir(where.capath) else ""
    if not (ctx.cert_store_stats().get("x509_ca") or (folder and any(os.scandir(folder)))):
        raise RuntimeError("no certificates for https (%s)" % (where.cafile or where.openssl_cafile))
    if not (ssl.HAS_TLSv1_2 and ssl.HAS_SNI):
        raise RuntimeError("https without TLS 1.2")
    db = sqlite3.connect(":memory:")
    try:
        db.execute("create table t (a integer, b text)")
        db.execute("insert into t values (?, ?)", (7, "ä€"))
        if db.execute("select a, b from t").fetchone() != (7, "ä€"):
            raise RuntimeError("sqlite")
    finally:
        db.close()
    return {"https": ssl.OPENSSL_VERSION, "database": "SQLite " + sqlite3.sqlite_version}


def works() -> dict:
    """What Kontor needs of those parts, each tried once with made-up values."""
    import decimal
    import gzip
    import hashlib
    import hmac
    import io
    import plistlib
    import tarfile
    import wave
    import xml.etree.ElementTree as ET
    import zipfile
    out = certificates_and_database()
    if hashlib.sha256(b"abc").hexdigest() != "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad":
        raise RuntimeError("sha256")
    if hashlib.pbkdf2_hmac("sha256", b"password", b"salt", 2).hex() != "ae4d0c95af6b46d32d0adff928f06dd02a303f8ef3c251dfd6e2d85a95474c43":
        raise RuntimeError("pbkdf2")
    if hmac.new(b"key", b"The quick brown fox jumps over the lazy dog", hashlib.sha256).hexdigest() != "f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8":
        raise RuntimeError("hmac")
    data = ("Kontor " * 200).encode("utf-8")
    if gzip.decompress(gzip.compress(data)) != data:
        raise RuntimeError("gzip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("a/b.txt", data)
    if zipfile.ZipFile(io.BytesIO(buf.getvalue())).read("a/b.txt") != data:
        raise RuntimeError("zip")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        info = tarfile.TarInfo("a/b.txt")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    with tarfile.open(fileobj=io.BytesIO(buf.getvalue()), mode="r:*") as t:
        if t.extractfile("a/b.txt").read() != data:
            raise RuntimeError("tar")
    if ET.fromstring("<a><b x='1'>ä</b></a>").find("b").text != "ä" or plistlib.loads(plistlib.dumps({"a": [1, "ä"]})) != {"a": [1, "ä"]}:
        raise RuntimeError("xml")
    if decimal.Decimal("1.10") + decimal.Decimal("2.20") != decimal.Decimal("3.30") or json.loads(json.dumps({"ä": 1.5})) != {"ä": 1.5}:
        raise RuntimeError("numbers")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 160)
    # Kontor's own: its texts, its version, another program started and answered (openssl, the secret over a pipe)
    import core
    import i18n
    import storage
    if not i18n._load() or not core.version():
        raise RuntimeError("Kontor's texts")
    key = os.urandom(32)
    if storage.decrypt(key, storage.encrypt(key, data)) != data:
        raise RuntimeError("openssl")
    if sys.platform == "darwin":
        the_macs_libraries()
    out["encoding"] = sys.getfilesystemencoding()
    return out


def the_macs_libraries() -> None:
    """As reading MoneyMoney's database needs them (mm_history.py): the Mac's own AES and the Mac's own SQLite, called from
    this Python -- a known answer, and a made-up database of one row read from memory."""
    import shutil
    import sqlite3
    import tempfile
    import mm_history
    key = bytearray.fromhex("603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4")
    block = bytearray.fromhex("f58c4c04d6e5f1ba779eabfb5f7bfbd6")
    mm_history._aes_cbc()(key, bytes.fromhex("000102030405060708090a0b0c0d0e0f"), block, 0, 16)
    if block.hex() != "6bc1bee22e409f96e93d7e117393172a":
        raise RuntimeError("AES")
    work = tempfile.mkdtemp(prefix="kontor-selftest-")
    try:
        db = sqlite3.connect(os.path.join(work, "t.sqlite"))
        try:
            db.execute("create table t (a integer, b text)")
            db.execute("insert into t values (?, ?)", (7, "ä€"))
            db.commit()
        finally:
            db.close()
        with open(os.path.join(work, "t.sqlite"), "rb") as f:
            image = bytearray(f.read())
    finally:
        shutil.rmtree(work, ignore_errors=True)
    mem = mm_history.MemDB(image)
    try:
        if mem.rows("select a, b from t where a = ?", (7,)) != [(7, "ä€")]:
            raise RuntimeError("the database read from memory")
    finally:
        mem.close()


def main() -> int:
    sys.path.insert(0, HERE)
    out = {"ok": False, "version": "%d.%d.%d" % sys.version_info[:3]}
    try:
        parts()
        out.update(works())
        out["ok"] = True
    except BaseException as e:      # whatever it is: said, not passed over
        out["error"] = "%s: %s" % (type(e).__name__, str(e)[:300])
    sys.stdout.write(json.dumps(out) + "\n")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
