"""The text of a receipt and the transaction it belongs to -- for the assistant (a file dropped into the chat) and Kontor itself.

* Text: a PDF's text layer or Apple's text recognition, on this Mac only: a small Swift helper (receipt_ocr.swift), compiled once
  into Kontor's program folder, gets the file on stdin and prints its text. It always runs in the macOS sandbox, whatever is set
  for the assistant's model -- no network, no other programs, no Apple events, writes only into a folder of its own made for this
  run (never into Kontor's temporary folders), reads nothing in the home folder (so neither Kontor's nor MoneyMoney's data) --
  with a time and size limit, and ends. Elsewhere (not a Mac) there is no text: said so, nothing guessed.
* What it says (read_fields): amounts, the total, dates, IBANs and the issuer, from the text by fixed rules -- no model involved.
* Which transaction (candidates): Kontor's own transactions ranked by amount, date, IBAN and name; each with its differences.
The file itself is never written here: storing it as a receipt is receipts.Belege, after the user's click."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from i18n import tr

HERE = os.path.dirname(os.path.abspath(__file__))
HELPER_SRC = os.path.join(HERE, "receipt_ocr.swift")
HELPER_DIR = os.path.join(HERE, ".receipt_ocr")
HELPER_BIN = os.path.join(HELPER_DIR, "receipt_ocr")
SANDBOX = "/usr/bin/sandbox-exec"
MAX_INPUT = 60 * 1024 * 1024             # as a receipt file (receipts.MAX_FILE)
MAX_TEXT = 20000
SECONDS = 90
MAX_LAYOUT = 60 * 1024 * 1024            # the words of all pages with their places, as JSON
LAYOUT_SECONDS = 300                     # many pages, scanned ones through text recognition


class TextUnavailable(Exception):
    """No text recognition here (not a Mac, Apple's developer tools missing): the reason, in the user's words."""


def _profile(home: str, data_dir: str, work: str) -> str:
    """The sandbox of the helper: as llm_local's "strict", no connection at all, and writing only into its own folder of this run
    and the system's caches (text recognition keeps its models there) -- never into Kontor's temporary folders (kontor-..., where
    e.g. the helper for MoneyMoney's password is built)."""
    q = lambda p: json.dumps(os.path.realpath(p), ensure_ascii=False)
    return "\n".join([
        "(version 1)", "(allow default)", "(deny network*)",
        "(deny process-exec*)", "(allow process-exec* (literal %s))" % q(HELPER_BIN),
        "(deny appleevent-send)", "(deny lsopen)", "(deny signal)", "(allow signal (target self))",
        '(deny mach-lookup (global-name "com.apple.pasteboard.1"))',
        "(deny file-write*)",
        '(allow file-write* (subpath %s) (regex #"^/private/var/folders/[^/]+/[^/]+/C/") (literal "/dev/null"))' % q(work),
        '(deny file-write* (regex #"/kontor-[^/]*(/|$)"))',
        "(deny file-read* (subpath %s) (subpath %s))" % (q(home), q(data_dir)),
        "(allow file-read* (subpath %s))" % q(HELPER_DIR),          # its own program (Kontor's folder may lie in the home folder)
        "(allow file-read-metadata (vnode-type DIRECTORY))"])


def _sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _helper() -> str:
    """The compiled helper, built once (again when its source changed) -- Apple's Swift compiler, as for Touch ID."""
    if sys.platform != "darwin":
        raise TextUnavailable(tr("s_beleg_text_nur_mac"))
    want = _sha(HELPER_SRC)
    stamp = HELPER_BIN + ".sha256"
    try:
        with open(stamp) as f:
            src, built = (f.read().split() + ["", ""])[:2]
        if src == want and os.access(HELPER_BIN, os.X_OK) and _sha(HELPER_BIN) == built:      # its source and the program as built
            return HELPER_BIN
    except OSError:
        pass
    os.makedirs(HELPER_DIR, mode=0o700, exist_ok=True)
    tmp = HELPER_BIN + ".new"
    try:
        r = subprocess.run(["swiftc", "-O", "-o", tmp, HELPER_SRC], capture_output=True, text=True, timeout=600)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        r = None
    if r is None or r.returncode != 0:
        raise TextUnavailable(tr("s_beleg_text_werkzeuge"))
    os.replace(tmp, HELPER_BIN)
    with open(stamp, "w") as f:
        f.write("%s %s" % (want, _sha(HELPER_BIN)))
    return HELPER_BIN


def _ask(data: bytes, data_dir: str, layout: bool = False) -> Optional[bytes]:
    """The helper's answer to one file (its text, or with layout its words and their places) -- always the same program, in
    its sandbox, with nothing handed to it but the file and that one fixed word. None when it failed."""
    if not data or len(data) > MAX_INPUT:
        raise ValueError(tr("s_leere_datei") if not data else tr("s_datei_zu_gross_max_d") % (MAX_INPUT // (1024 * 1024)))
    exe = _helper()
    work = tempfile.mkdtemp(prefix="rcpt-")              # its own folder for this run (not kontor-...: those it may not write)
    try:
        r = subprocess.run([SANDBOX, "-p", _profile(os.path.expanduser("~"), data_dir, work), exe] + (["layout"] if layout else []),
                           input=data, capture_output=True, timeout=LAYOUT_SECONDS if layout else SECONDS, cwd=work,
                           env={"PATH": "/usr/bin:/bin", "TMPDIR": work})
    except subprocess.TimeoutExpired:
        raise TextUnavailable(tr("s_beleg_text_zeit"))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return r.stdout if r.returncode == 0 else None


def text_of(data: bytes, data_dir: str) -> Dict[str, str]:
    """{"text", "how": "pdf" | "ocr" | "none"} of a receipt (PDF or picture) -- recognized on this Mac, always in the sandbox.
    TextUnavailable when it cannot be done here."""
    raw = _ask(data, data_dir)
    try:
        out = json.loads(raw[:4 * MAX_TEXT].decode("utf-8")) if raw is not None else None
    except (ValueError, UnicodeDecodeError):
        out = None
    if not isinstance(out, dict) or not isinstance(out.get("text"), str) or out.get("how") not in ("pdf", "ocr", "none"):
        raise TextUnavailable(tr("s_beleg_text_fehler"))
    return {"text": out["text"][:MAX_TEXT], "how": out["how"]}


def layout_of(data: bytes, data_dir: str) -> Dict[str, Any]:
    """Every page of a document (PDF or picture) with its words and where they stand -- {"pages": [{"n", "w", "h", "how",
    "items": [[x, y, width, height, text] in tenths of a point, y from the top]}], "count", "cut"} -- for its tables
    (pdf_tables.book checks every value). Recognized on this Mac, in the same sandbox. TextUnavailable when it cannot be done."""
    raw = _ask(data, data_dir, layout=True)
    try:
        out = json.loads(raw[:MAX_LAYOUT].decode("utf-8")) if raw is not None and len(raw) <= MAX_LAYOUT else None
    except (ValueError, UnicodeDecodeError, RecursionError):
        out = None
    if not isinstance(out, dict) or not isinstance(out.get("pages"), list):
        raise TextUnavailable(tr("s_beleg_text_fehler"))
    return out


# -- what a receipt says ---------------------------------------------------------------------------------------------------------

_AMOUNT = re.compile(r"(?<![\d.,])(-?\d{1,3}(?:[.\u00a0\u202f]\d{3})*,\d{2}|-?\d+,\d{2}|-?\d{1,3}(?:,\d{3})*\.\d{2}|-?\d+\.\d{2})(?![\d])\s*(?:€|EUR)?")      # a plain space is no thousands separator (1 150,00: one at 150,00)
_TOTAL = re.compile(r"(?i)\b(gesamt\w*|summe|endbetrag|rechnungsbetrag|zu zahlen|zahlbetrag|total|amount due|betrag)\b")
_DATE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4}|\d{2})\b|\b(\d{4})-(\d{2})-(\d{2})\b")       # 3.10.2026, 03/10/2026 (day first), 2026-10-03
_MONTHS = {"jan": 1, "januar": 1, "january": 1, "jän": 1, "feb": 2, "februar": 2, "february": 2, "mär": 3, "märz": 3, "maerz": 3, "mar": 3, "march": 3,
           "apr": 4, "april": 4, "mai": 5, "may": 5, "jun": 6, "juni": 6, "june": 6, "jul": 7, "juli": 7, "july": 7, "aug": 8, "august": 8,
           "sep": 9, "sept": 9, "september": 9, "okt": 10, "oktober": 10, "oct": 10, "october": 10, "nov": 11, "november": 11,
           "dez": 12, "dezember": 12, "dec": 12, "december": 12}
_M = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE_DM = re.compile(r"(?i)\b(\d{1,2})\.?\s*(%s)\.?\s+(\d{4})\b" % _M)          # 3. Oktober 2026, 3 Oct 2026
_DATE_MD = re.compile(r"(?i)\b(%s)\.?\s+(\d{1,2}),?\s+(\d{4})\b" % _M)            # October 3, 2026
_IBAN = re.compile(r"\b([A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?)\b")


def _num(s: str) -> Optional[float]:
    s = s.replace("\u00a0", "").replace("\u202f", "")
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(?:,\d{3})*\.\d{2}|-?\d+\.\d{2}", s):
        s = s.replace(",", "")
    else:
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _iban_ok(iban: str) -> bool:
    s = iban.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    digits = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(digits) % 97 == 1


def read_fields(text: str) -> Dict[str, Any]:
    """What the text of a receipt says, by fixed rules: the amounts, the total (the amount on a line naming it, else the largest),
    the dates (newest first), valid IBANs and the issuer (its first line with letters). Unknown stays out."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    amounts: List[float] = []
    on_total: List[float] = []
    for ln in lines:
        found = [v for v in (_num(m.group(1)) for m in _AMOUNT.finditer(ln)) if v is not None and abs(v) < 1e8]
        amounts += found
        if found and _TOTAL.search(ln):
            on_total.append(found[-1])
    days = []
    found = [(int(m.group(4)), int(m.group(5)), int(m.group(6))) if m.group(4) else (int(m.group(3)), int(m.group(2)), int(m.group(1)))
             for m in _DATE.finditer(text or "")]
    found += [(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1))) for m in _DATE_DM.finditer(text or "")]
    found += [(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2))) for m in _DATE_MD.finditer(text or "")]
    for y, mo, dd in found:
        try:
            d = date(y + 2000 if y < 100 else y, mo, dd)
        except ValueError:
            continue
        if date(1990, 1, 1) <= d <= date.today() + timedelta(days=366):
            days.append(d)
    ibans = sorted({m.group(1).replace(" ", "") for m in _IBAN.finditer((text or "").upper()) if _iban_ok(m.group(1))})
    issuer = next((ln[:80] for ln in lines if re.search(r"[A-Za-zÄÖÜäöüß]{3}", ln)), "")
    out: Dict[str, Any] = {}
    if amounts:
        out["total"] = max(on_total, key=abs) if on_total else max(amounts, key=abs)
        out["amounts"] = sorted(set(amounts), key=abs, reverse=True)[:8]
    if days:
        out["dates"] = [d.isoformat() for d in sorted(set(days), reverse=True)[:5]]
    if ibans:
        out["ibans"] = ibans[:3]
    if issuer:
        out["issuer"] = issuer
    return out


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-zäöüß0-9]{3,}", (s or "").lower()) if w not in {"gmbh", "und", "der", "die", "das", "mbh", "kg"}}


def candidates(fields: Dict[str, Any], transactions: List[dict], amount: Optional[float] = None, day: Optional[str] = None,
               name: str = "", limit: int = 5) -> List[dict]:
    """The transactions a receipt may belong to, best first, each with what differs: amount (the total, or as given), date
    (within 60 days), the IBAN of the other side, words of the issuer or name in the transaction. Only real matches count:
    without an amount within 2 % or a matching IBAN, nothing is offered."""
    want = abs(amount) if amount is not None else (abs(fields["total"]) if fields.get("total") is not None else None)
    days = [date.fromisoformat(d) for d in ([day] if day else fields.get("dates") or []) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d))]
    ibans = set(fields.get("ibans") or [])
    words = _words(name or fields.get("issuer") or "")
    out = []
    for t in transactions:
        try:
            amt, tday = abs(float(t.get("amount") or 0)), date.fromisoformat(str(t.get("date")))
        except (TypeError, ValueError):
            continue
        score, diffs = 0, []
        iban_hit = bool(ibans) and str(t.get("counter_iban") or "").replace(" ", "").upper() in ibans
        if want is not None and want > 0:
            gap = round(amt - want, 2)
            if abs(gap) < 0.005:
                score += 50
            elif abs(gap) <= max(0.02 * want, 0.05):
                score += 25
                diffs.append({"what": "amount", "by": gap})
            elif not iban_hit:
                continue
            else:
                diffs.append({"what": "amount", "by": gap})
        elif not iban_hit:
            continue
        if days:
            gap_d = min(abs((tday - d).days) for d in days)
            if gap_d > 60:
                continue
            score += 20 if gap_d <= 3 else 12 if gap_d <= 14 else 5
            if gap_d > 3:
                diffs.append({"what": "date", "days": gap_d})
        if iban_hit:
            score += 40
        if words and words & _words(" ".join(str(t.get(k) or "") for k in ("name", "purpose"))):
            score += 15
        out.append({"score": score, "tx": t, "differences": diffs})
    out.sort(key=lambda c: (c["score"], str(c["tx"].get("date") or "")), reverse=True)          # alike: the newest first
    return out[:limit]
