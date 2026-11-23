"""Tables the user gives the assistant (Excel .xlsx/.xlsm) -- read here, without other libraries, into a grid the model can
work with reliably, instead of handing it a file it cannot read or a dump it misreads.

What the model gets (render): one sheet or range at a time as a table with Excel's own addresses (columns A, B, ..., row
numbers), so it names the cells it uses; numbers exactly as stored (to Excel's 15 digits, '.' as decimal point, no thousands
separators), dates as YYYY-MM-DD, percentages as shown ("19%"), formulas only on request, hidden rows, columns and sheets and
merged cells said. Sums come from Kontor (sum_range: exact, decimal), not from the model's own arithmetic.

Safety: the file stays in memory. Only the parts a workbook needs are read (workbook, relationships, shared strings, styles,
worksheets -- never macros, links or embedded objects), each streamed (ElementTree) with no document type or entities of its
own (a file that declares them is refused: they can blow up to any size), with limits on what is unpacked, on cells, sheets
and text. Nothing is evaluated: a formula is text, its value the one Excel saved."""
from __future__ import annotations

import bisect
import csv
import io
import json
import os
import re
import time
import unicodedata
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

TYPES = (".xlsx", ".xlsm")
TEXT_TYPES = (".csv", ".tsv")      # tables as text: read the same way into a grid (read_csv)
MAX_CSV_FIELD = 32767              # characters of one field at most (as a cell of Excel)
MAX_UNPACKED = 64 << 20            # bytes unpacked from the file at most (all parts together)
MAX_PARTS = 5000                   # entries in the zip at most
MAX_SHEETS = 60
MAX_SECONDS = 20                   # reading one file at most this long
MAX_COL_RANGES = 500               # blocks of hidden columns kept (as ranges, never column by column)
MAX_CELLS = 200000                 # cells with something in them, all sheets together
MAX_CELL_TEXT = 300                # characters of one cell shown
MAX_COLS_SHOWN = 30                # columns of one read at most
RENDER_CHARS = 4800                # characters of one read at most (a tool result has room for 7000, with what else it says)
CHUNK = 1 << 16

_BUILTIN_DATE = set(range(14, 18)) | {22} | set(range(27, 37)) | set(range(50, 59))
_BUILTIN_TIME = set(range(18, 22)) | {45, 47}
_BUILTIN_DURATION = {46}            # [h]:mm:ss
_BUILTIN_PERCENT = {9, 10}
_ADDR = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})$")


class Unreadable(Exception):
    """The file is no workbook this can read (or breaks a limit): the reason, short, in English (for the log and the model)."""


# -- addresses ---------------------------------------------------------------------------------------------------------------
def col_name(c: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    s, c = "", c + 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


def col_index(letters: str) -> int:
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _addr(ref: str) -> Optional[Tuple[int, int]]:
    m = _ADDR.match(ref or "")
    return (int(m.group(2)) - 1, col_index(m.group(1))) if m else None


def parse_range(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int, int, int]]]:
    """'Bilanz!A1:D20', 'B:D', '5:20', 'C7', '' -> (sheet or None, (row0, col0, row1, col1) or None for all). Inclusive, 0-based."""
    s = str(text or "").strip()
    sheet = None
    if "!" in s:
        sheet, s = s.rsplit("!", 1)
        sheet = sheet.strip()
        if len(sheet) >= 2 and sheet[0] == sheet[-1] == "'":
            sheet = sheet[1:-1].replace("''", "'")
        s = s.strip()
    if not s:
        return sheet, None
    a, _, b = s.replace(" ", "").partition(":")
    b = b or a
    big = 10 ** 7
    if re.fullmatch(r"\$?[A-Za-z]{1,3}", a) and re.fullmatch(r"\$?[A-Za-z]{1,3}", b):          # whole columns
        c0, c1 = col_index(a.strip("$")), col_index(b.strip("$"))
        return sheet, (0, min(c0, c1), big, max(c0, c1))
    if re.fullmatch(r"\$?\d{1,7}", a) and re.fullmatch(r"\$?\d{1,7}", b):                      # whole rows
        r0, r1 = int(a.strip("$")) - 1, int(b.strip("$")) - 1
        if min(r0, r1) < 0:
            raise ValueError("rows start at 1")
        return sheet, (min(r0, r1), 0, max(r0, r1), big)
    p, q = _addr(a), _addr(b)
    if p is None or q is None or min(p[0], q[0]) < 0:
        raise ValueError("not a range like A1:D20, B:D or 5:20")
    return sheet, (min(p[0], q[0]), min(p[1], q[1]), max(p[0], q[0]), max(p[1], q[1]))


def range_name(r0: int, c0: int, r1: int, c1: int) -> str:
    a, b = "%s%d" % (col_name(c0), r0 + 1), "%s%d" % (col_name(c1), r1 + 1)
    return a if a == b else a + ":" + b


# -- numbers and dates -------------------------------------------------------------------------------------------------------
def number(raw: str) -> Optional[Decimal]:
    """A number as Excel stores it, to its 15 significant digits (0.30000000000000004 -> 0.3) -- never more exact than Excel."""
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return None
    if x != x or x in (float("inf"), float("-inf")):
        return None
    d = Decimal("%.15g" % x)
    return Decimal(0) if d == 0 else d


def plain(d: Decimal) -> str:
    """1234.5 -> '1234.5', 1E+3 -> '1000', 0.000012 -> '0.000012': no exponent, no trailing zeros."""
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _strip_fmt(code: str) -> str:
    return re.sub(r'"[^"]*"|\[[^\]]*\]|\\.|_.|\*.', "", code or "").lower()


def fmt_kind(code: str) -> str:
    """What a custom number format shows: 'date', 'time', 'duration' ([h]:mm -- hours beyond a day), 'percent' or '' (a number)."""
    first = code.split(";")[0]
    if re.search(r"\[(h+|m+|s+)\]", re.sub(r'"[^"]*"', "", first), re.I):
        return "duration"
    c = _strip_fmt(first)
    if "%" in c:
        return "percent"
    if "y" in c or "d" in c or ("m" in c and "h" not in c and "s" not in c and "0" not in c and "#" not in c):
        return "date"
    if "h" in c or ("s" in c and "0" not in c):
        return "time"
    return ""


def serial_date(x: float, date1904: bool, kind: str) -> Optional[str]:
    """An Excel date number as text: 'YYYY-MM-DD', with ' HH:MM' when it has a time of day; a time alone as 'HH:MM'; a duration
    as hours:minutes beyond a day ('25:30')."""
    if kind == "duration" and 0 <= x < 1e7:
        sec = int(round(x * 86400))
        return "%d:%02d" % (sec // 3600, sec // 60 % 60) + (":%02d" % (sec % 60) if sec % 60 else "")
    if kind == "time" and 0 <= x < 1:
        sec = int(round(x * 86400)) % 86400
        return "%02d:%02d" % (sec // 3600, sec // 60 % 60) + (":%02d" % (sec % 60) if sec % 60 else "")
    if not (0 <= x if date1904 else 0 < x) or x >= 2958466:
        return None
    if not date1904 and 60 <= x < 61:
        return "1900-02-29"                              # Excel's own day that never was (kept for Lotus 1-2-3)
    base = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 31) if x < 60 else datetime(1899, 12, 30)
    t = base + timedelta(seconds=int(round(x * 86400)))
    return t.strftime("%Y-%m-%d") + (t.strftime(" %H:%M") if (t.hour or t.minute) else "")


# -- reading -----------------------------------------------------------------------------------------------------------------
class _Budget:
    def __init__(self):
        self.left = MAX_UNPACKED
        self.cells = 0
        self.until = time.monotonic() + MAX_SECONDS


def _stream(z: zipfile.ZipFile, name: str, budget: _Budget, start, end, data=None) -> None:
    """One XML part of the file, streamed: no document type and so no entities of its own (refused before the parser sees them),
    UTF-8 only (as Excel writes it), within the budget. Each element is handed on and forgotten at its end (memory stays small)."""
    info = z.getinfo(name)
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):          # Excel writes only these; others unpack unbounded
        raise Unreadable("a part of the file is packed in a way Excel does not use")
    if info.file_size > budget.left:
        raise Unreadable("the file unpacks to more than %d MB" % (MAX_UNPACKED >> 20))
    p = ET.XMLPullParser(events=("start", "end"))
    stack: List[Any] = []

    def drain() -> None:
        for ev, el in p.read_events():
            if ev == "start":
                start(el.tag, el.attrib)
                stack.append(el)
                continue
            if data is not None and el.text:
                data(el.text)
            end(el.tag)
            stack.pop()
            if stack:
                stack[-1].remove(el)                     # (it is its parent's only child left: all before it went the same way)
            el.clear()
    tail, first = b"", True
    try:
        with z.open(info) as f:
            while True:
                chunk = f.read(CHUNK)                    # deflate: never more than asked for at once
                if not chunk:
                    break
                if first and (chunk[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\0" in chunk[:256]):
                    raise Unreadable("a part of the file is not written as Excel writes it (UTF-8)")
                first = False
                budget.left -= len(chunk)
                if budget.left < 0:
                    raise Unreadable("the file unpacks to more than %d MB" % (MAX_UNPACKED >> 20))
                if time.monotonic() > budget.until:
                    raise Unreadable("reading the file takes too long")
                look = tail + chunk                      # (a declaration split between two pieces is found too)
                if b"<!DOCTYPE" in look or b"<!ENTITY" in look:
                    raise Unreadable("the file declares a document type or entities")
                tail = chunk[-16:]
                p.feed(chunk)
                drain()
            p.close()
            drain()
    except ET.ParseError as e:
        raise Unreadable("broken XML in a part of the file (line %s)" % (e.position[0] if getattr(e, "position", None) else "?"))          # no names from the file: they reach the model


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _rel_id(attrs: dict) -> Optional[str]:
    """The relationship id of a sheet: r:id, in whichever namespace of relationships the file uses (transitional or strict)."""
    for k, v in attrs.items():
        if k.endswith("}id") and k[:-3].rstrip("/").endswith("relationships"):
            return v
    return None


def _rels(z: zipfile.ZipFile, names: set, path: str, budget: _Budget) -> Dict[str, str]:
    """Relationship id -> part, for the part at path (only parts inside this file)."""
    folder, base = os.path.split(path)
    rp = os.path.join(folder, "_rels", base + ".rels")
    out: Dict[str, str] = {}
    if rp not in names:
        return out

    def start(tag, a):
        if _local(tag) == "Relationship" and a.get("TargetMode") != "External" and a.get("Id") and a.get("Target"):
            t = a["Target"]
            full = os.path.normpath(t.lstrip("/") if t.startswith("/") else os.path.join(folder, t))
            if not full.startswith(("..", "/")):
                out[a["Id"]] = full
    _stream(z, rp, budget, start, lambda tag: None)
    return out


def _name(v: Any) -> str:
    """A sheet's name as Excel allows it (31 characters), without control or direction marks -- it is shown to the model."""
    s = "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") or c in '"[]{}<>`\\' else c for c in str(v or ""))
    return re.sub(r"\s+", " ", s).strip()[:31] or "?"


def read_xlsx(data: bytes) -> dict:
    """The workbook (see _read); whatever a broken file makes go wrong is Unreadable, never anything else."""
    try:
        return _read(data)
    except Unreadable:
        raise
    except MemoryError:
        raise Unreadable("the file is too large to read")
    except Exception as e:                               # zlib, lzma, a broken zip, an unexpected structure: the file is broken
        raise Unreadable("the file is broken (%s)" % type(e).__name__)


def _read(data: bytes) -> dict:
    """The workbook: {"sheets": [{"name", "hidden", "cells": {(row, col): (kind, text, formula)}, "rows": n, "cols": n,
    "merged": [ranges], "hidden_rows": set, "hidden_cols": set, "no_value": n}], "date1904": bool}. kind: n number (text: its
    plain value), d date/time, p percent (as shown), t text, b TRUE/FALSE, e an error (#DIV/0! ...)."""
    if data[:4] == b"\xd0\xcf\x11\xe0":
        raise Unreadable("an old Excel file (.xls) or one protected by a password -- save it as .xlsx without a password")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise Unreadable("not an Excel file (.xlsx)")
    with z:
        infos = z.infolist()
        if len(infos) > MAX_PARTS:
            raise Unreadable("too many parts in the file")
        names = {i.filename for i in infos}
        budget = _Budget()
        wb_path = "xl/workbook.xml"
        if "_rels/.rels" in names:                       # where the workbook is (nearly always xl/workbook.xml)
            rels_top: Dict[str, str] = {}

            def start_top(tag, a):
                if _local(tag) == "Relationship" and str(a.get("Type", "")).endswith("/officeDocument") and a.get("Target"):
                    rels_top["wb"] = os.path.normpath(a["Target"].lstrip("/"))
            _stream(z, "_rels/.rels", budget, start_top, lambda tag: None)
            wb_path = rels_top.get("wb", wb_path)
        if wb_path not in names:
            raise Unreadable("no workbook in the file (not an Excel file?)")
        rels = _rels(z, names, wb_path, budget)
        book: Dict[str, Any] = {"sheets": [], "date1904": False}
        listed: List[Tuple[str, str, bool]] = []

        def start_wb(tag, a):
            n = _local(tag)
            if n == "workbookPr" and str(a.get("date1904", "")).lower() in ("1", "true"):
                book["date1904"] = True
            elif n == "sheet" and len(listed) >= MAX_SHEETS:
                book["sheets_left_out"] = book.get("sheets_left_out", 0) + 1
            elif n == "sheet":
                rid = _rel_id(a)
                if rid in rels:
                    listed.append((_name(a.get("name")), rels[rid], a.get("state") in ("hidden", "veryHidden")))
        _stream(z, wb_path, budget, start_wb, lambda tag: None)
        targets = set(rels.values())
        shared = _shared(z, names, next((t for t in targets if t.endswith("sharedStrings.xml")), ""), budget)
        styles = _styles(z, names, next((t for t in targets if t.endswith("styles.xml")), ""), budget)
        for name, path, hidden in listed:
            if path in names:
                sh = _sheet(z, path, shared, styles, book["date1904"], budget)
                sh.update(name=name, hidden=hidden)
                book["sheets"].append(sh)
        if not book["sheets"]:
            raise Unreadable("no sheet with cells in the file")
        return book


def _shared(z, names, path, budget) -> List[str]:
    out: List[str] = []
    if path not in names:
        return out
    st = {"in_si": False, "in_t": False, "skip": 0, "buf": [], "len": 0}

    def start(tag, a):
        n = _local(tag)
        if n == "si":
            st["in_si"], st["buf"], st["len"] = True, [], 0
        elif n in ("rPh", "phoneticPr"):              # the reading aid of East Asian text: not part of the text
            st["skip"] += 1
        elif n == "t" and st["in_si"] and not st["skip"]:
            st["in_t"] = True

    def end(tag):
        n = _local(tag)
        if n == "si":
            out.append("".join(st["buf"]))
            st["in_si"] = False
            if len(out) > MAX_CELLS * 2:
                raise Unreadable("too many texts in the file")
        elif n in ("rPh", "phoneticPr"):
            st["skip"] -= 1
        elif n == "t":
            st["in_t"] = False

    def data(s):
        if st["in_t"] and st["len"] < 32767:            # a running count (never adding up the pieces again: many pieces would take forever)
            st["buf"].append(s)
            st["len"] += len(s)
    _stream(z, path, budget, start, end, data)
    return out


def _styles(z, names, path, budget) -> List[str]:
    """Kind of each cell style ('date', 'time', 'percent' or '')."""
    fmts: Dict[int, str] = {}
    xfs: List[int] = []
    st = {"in_xfs": False}
    if path not in names:
        return []

    def start(tag, a):
        n = _local(tag)
        if n == "numFmt" and str(a.get("numFmtId", "")).isdigit():
            fmts[int(a["numFmtId"])] = a.get("formatCode", "")
        elif n == "cellXfs":
            st["in_xfs"] = True
        elif n == "xf" and st["in_xfs"]:
            v = str(a.get("numFmtId", "0"))
            xfs.append(int(v) if v.isdigit() else 0)

    def end(tag):
        if _local(tag) == "cellXfs":
            st["in_xfs"] = False
    _stream(z, path, budget, start, end)
    out = []
    for fid in xfs:
        if fid in fmts:
            out.append(fmt_kind(fmts[fid]))
        else:
            out.append("date" if fid in _BUILTIN_DATE else "time" if fid in _BUILTIN_TIME else "duration" if fid in _BUILTIN_DURATION else
                       "percent" if fid in _BUILTIN_PERCENT else "")
    return out


def _sheet(z, path, shared, styles, date1904, budget) -> dict:
    cells: Dict[Tuple[int, int], Tuple[str, str, str]] = {}
    sh: Dict[str, Any] = {"cells": cells, "merged": [], "hidden_rows": set(), "hidden_cols": [], "no_value": 0, "rows": 0, "cols": 0}
    cur = {"row": -1, "col": -1, "t": "", "s": 0, "v": [], "f": [], "is": [], "in": "", "has_f": False, "len": 0}

    def start(tag, a):
        n = _local(tag)
        if n == "row":
            r = str(a.get("r", ""))
            cur["row"] = int(r) - 1 if r.isdigit() and int(r) > 0 else cur["row"] + 1
            cur["col"] = -1
            if str(a.get("hidden", "")).lower() in ("1", "true") and len(sh["hidden_rows"]) < MAX_CELLS:
                sh["hidden_rows"].add(cur["row"])
        elif n == "c":
            p = _addr(a.get("r", ""))
            if p is not None:
                cur["row"], cur["col"] = p
            else:
                cur["col"] += 1
            s = str(a.get("s", "0"))
            cur.update({"t": a.get("t", "n"), "s": int(s) if s.isdigit() else 0, "v": [], "f": [], "is": [], "has_f": False, "len": 0})
        elif n in ("v", "f", "t"):
            cur["in"] = "is" if n == "t" else n
            if n == "f":
                cur["has_f"] = True
        elif n == "mergeCell" and len(sh["merged"]) < 2000:
            ref = str(a.get("ref", ""))
            if re.fullmatch(r"[A-Za-z]{1,3}\d{1,7}(:[A-Za-z]{1,3}\d{1,7})?", ref):
                sh["merged"].append(ref.upper())
        elif n == "col" and str(a.get("hidden", "")).lower() in ("1", "true") and len(sh["hidden_cols"]) < MAX_COL_RANGES:
            lo, hi = str(a.get("min", "")), str(a.get("max", ""))
            if lo.isdigit() and hi.isdigit() and 1 <= int(lo) <= int(hi):
                sh["hidden_cols"].append((int(lo) - 1, min(int(hi), 16384) - 1))          # kept as a range, never column by column

    def end(tag):
        n = _local(tag)
        if n in ("v", "f", "t"):
            cur["in"] = ""
        elif n == "c":
            cell = _cell(cur, shared, styles, date1904)
            if cell is not None:
                budget.cells += 1
                if budget.cells > MAX_CELLS:
                    raise Unreadable("more than %d cells in the file" % MAX_CELLS)
                cells[(cur["row"], cur["col"])] = cell
                if cell[0] == "" and cur["has_f"]:
                    sh["no_value"] += 1

    def data(s):
        k = cur["in"]
        if k and cur["len"] < 3 * 32767:                # a running count over value, formula and text of the cell
            cur[k].append(s)
            cur["len"] += len(s)
    _stream(z, path, budget, start, end, data)
    if cells:
        sh["rows"] = max(r for r, _ in cells) + 1
        sh["cols"] = max(c for _, c in cells) + 1
    return sh


def _cell(cur: dict, shared: List[str], styles: List[str], date1904: bool) -> Optional[Tuple[str, str, str]]:
    t, v, f = cur["t"], "".join(cur["v"]).strip(), "".join(cur["f"]).strip()
    if t == "inlineStr":
        text = "".join(cur["is"])
        return ("t", text, f) if text or f else None
    if t == "s":
        if not v.isdigit() or int(v) >= len(shared):
            return None
        text = shared[int(v)]
        return ("t", text, f) if text else None
    if t == "str":
        return ("t", v, f) if v or f else None
    if t == "b":
        return ("b", "TRUE" if v in ("1", "true") else "FALSE", f) if v else None
    if t == "e":
        return ("e", v or "#ERROR", f)
    if t == "d":                                         # an ISO date (Strict files)
        return ("d", v[:16].replace("T", " "), f) if v else None
    if not v:
        return ("", "", f) if f else None                 # a formula whose value Excel did not save
    d = number(v)
    if d is None:
        return ("t", v, f)
    kind = styles[cur["s"]] if cur["s"] < len(styles) else ""
    if kind in ("date", "time", "duration"):
        s = serial_date(float(d), date1904, kind)
        if s:
            return ("d", s, f)
    if kind == "percent":
        return ("p", plain(d * 100) + "%", f)
    return ("n", plain(d), f)


# -- tables as text (CSV) ----------------------------------------------------------------------------------------------------
def _decode(data: bytes) -> Tuple[str, str]:
    """A text file's content and how it was read: by its mark at the start (UTF-8, UTF-16), else UTF-8 where every byte fits,
    else Windows-1252 (what accounting software calls ANSI) -- its few undefined bytes as Latin-1, so nothing is dropped."""
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", "replace"), "UTF-8"
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace"), "UTF-16"
    try:
        return data.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError:
        try:
            return data.decode("cp1252"), "Windows-1252"
        except UnicodeDecodeError:
            return data.decode("latin-1"), "Latin-1"


def _delimiter(text: str) -> str:
    """What parts the fields: the sign (; tab , |) that cuts most of the first lines into the same number of fields, more than
    one -- quotes respected; among equals the one German exports use first."""
    head = text[:200000]
    best, pick = (0.0, 0), ","
    for d in (";", "\t", ",", "|"):
        counts: Dict[int, int] = {}
        try:
            for i, row in enumerate(csv.reader(io.StringIO(head, newline=""), delimiter=d)):
                if i >= 200:
                    break
                if row:
                    counts[len(row)] = counts.get(len(row), 0) + 1
        except csv.Error:
            continue
        n = sum(counts.values())
        width, often = max(counts.items(), key=lambda kv: (kv[1], kv[0])) if counts else (0, 0)
        score = (round(often / float(n), 2) if n and width >= 2 else 0.0, width)
        if score > best:
            best, pick = score, d
    return pick


def read_csv(data: bytes) -> dict:
    """A CSV file as a workbook of one sheet, read like any untrusted text: decoded (see _decode), cut into fields by the sign
    the file uses, its figures as written -- by the notation the file shows (1.234,56 or 1,234.56; where it does not say,
    12,345 stays text), with the same strict rules as a document's (pdf_tables.figure: 0800 is a code, 1.234,56- negative,
    31.12.2025 a date). Limits on cells and on a field's length; nothing is evaluated (a formula is text)."""
    try:
        return _read_csv(data)
    except Unreadable:
        raise
    except MemoryError:
        raise Unreadable("the file is too large to read")
    except Exception as e:
        raise Unreadable("the file is broken (%s)" % type(e).__name__)


def _read_csv(data: bytes) -> dict:
    if data[:4] == b"PK\x03\x04" or data[:4] == b"\xd0\xcf\x11\xe0":
        raise Unreadable("not a text file (an Excel file with the ending .csv?) -- save it as .xlsx or as CSV text")
    text, how = _decode(data)
    if "\0" in text[:4000]:
        raise Unreadable("not a text file")
    d = _delimiter(text)
    rows: List[Tuple[int, List[str]]] = []               # the lines with something in them, each with its number (an empty line counts, as in Excel)
    count = 0
    try:
        for r, row in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=d)):
            if r >= 1048576 or len(row) > 16384:         # (empty lines count: a file of nothing but line breaks is not read to its end)
                raise Unreadable("more rows or columns than a sheet has")
            filled = sum(1 for x in row if x and not x.isspace())
            if not filled:
                continue
            count += filled
            if count > MAX_CELLS:
                raise Unreadable("more than %d cells in the file" % MAX_CELLS)
            if any(len(x) > MAX_CSV_FIELD for x in row):
                raise Unreadable("a field of the file is too long (its quotes do not close?)")
            rows.append((r, [x.strip() for x in row]))
    except csv.Error:
        raise Unreadable("a field of the file is too long or its quotes do not close")
    if not rows:
        raise Unreadable("nothing in the file")
    figurish = lambda x: bool(x) and len(x) <= 40 and _FIGURISH.match(x) is not None
    ways: Dict[int, List[int]] = {}                      # per column: its figures that show their decimal sign -- the German way (12,5; 1.234,56), the English
    for _, row in rows:
        for c, x in enumerate(row):
            w = _way(x) if figurish(x) else ""
            if w:
                ways.setdefault(c, [0, 0])[w == "."] += 1
    de, en = sum(v[0] for v in ways.values()), sum(v[1] for v in ways.values())
    sign = "." if en > de else ","                       # the file's way: that of most of them -- the others stay text (1.10 in a German file: a date, a section?)
    k = int(sign == ".")
    shown = {c: v[k] > 0 and v[1 - k] == 0 for c, v in ways.items()}       # 12.345 is thousands only in a column that shows its decimals, and only this way
    import pdf_tables                                    # (its rules for a figure as written; no part of it reads a file)
    cells: Dict[Tuple[int, int], Tuple[str, str, str]] = {}
    unsure = 0
    for r, row in rows:
        for c, x in enumerate(row):
            if not x:
                continue
            kind, v = "t", x
            if figurish(x) or re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", x):
                kind, v = pdf_tables.figure(x, de=sign != ".", unsure=not shown.get(c))
                if kind != "t" and not shown.get(c) and _SPACED_WHOLE.match(x):
                    kind = "t"                           # 18 231 in a column that never shows decimals: eighteen thousand, or two numbers? text
                if kind == "t" and pdf_tables.figure(x, de=sign != ".")[0] in ("n", "m", "p"):
                    unsure += 1                          # 12.345 in a column that never shows decimals: thousands or decimals? text
            cells[(r, c)] = (kind, v if kind != "t" else x, "")
    sh = {"name": "CSV", "hidden": False, "cells": cells, "rows": max(r for r, _ in cells) + 1, "cols": max(c for _, c in cells) + 1, "merged": [],
          "hidden_rows": set(), "hidden_cols": [], "no_value": 0, "as_written": True}
    return {"sheets": [sh], "date1904": False, "source": "csv", "decimal": sign, "unsure": unsure, "other_way": en if sign == "," else de,
            "delimiter": {";": "semicolon", "\t": "tab", ",": "comma", "|": "bar"}[d], "encoding": how}


# -- for the model -----------------------------------------------------------------------------------------------------------
def used(sh: dict) -> str:
    return range_name(0, 0, max(0, sh["rows"] - 1), max(0, sh["cols"] - 1)) if sh["cells"] else "empty"


def overview(book: dict) -> str:
    """The sheets in one line: name (quoted as JSON: a name never reads as Kontor's own words), used range, hidden."""
    out = "; ".join("%s %s%s" % (json.dumps(sh["name"], ensure_ascii=False), used(sh), " (hidden)" if sh["hidden"] else "") for sh in book["sheets"])
    return out + ("; %d more sheets not read" % book["sheets_left_out"] if book.get("sheets_left_out") else "")


def col_hidden(sh: dict, c: int) -> bool:
    return any(lo <= c <= hi for lo, hi in sh["hidden_cols"])


def find_sheet(book: dict, name: Optional[str]) -> dict:
    sheets = book["sheets"]
    if not name:
        return next((s for s in sheets if not s["hidden"] and s["cells"]), sheets[0])
    for s in sheets:
        if s["name"] == name:
            return s
    low = name.strip().lower()
    for s in sheets:
        if s["name"].strip().lower() == low:
            return s
    raise ValueError("no sheet %r -- there are: %s" % (name, overview(book)))


def _jlen(s: str) -> int:
    return len(json.dumps(s, ensure_ascii=False)) - 2


def _clean(s: str) -> str:
    """A cell's text on one line of the table: line breaks shown, no control or direction marks, a pipe kept in its cell."""
    s = re.sub(r"\r\n?|\n", " ⏎ ", s)
    return "".join(" " if unicodedata.category(c) in ("Cc", "Cf") else c for c in s).replace("|", "\\|")


def _show(cell: Tuple[str, str, str], formulas: bool, cap: int = MAX_CELL_TEXT, cut: Optional[list] = None) -> str:
    kind, text, f = cell
    s = _clean(text[:cap + 1] if kind else "(no value saved)")
    if formulas and f:
        s += " {=%s}" % _clean(f[:200])
    if len(s) > cap:
        s = s[:cap].rstrip("\\") + "…"                  # (never half a "\|")
        if cut is not None:
            cut.append(1)
    return s


def render(book: dict, sheet: Optional[str] = None, rng: str = "", formulas: bool = False, chars: int = RENDER_CHARS) -> dict:
    """A sheet or a range of it as a table with Excel's addresses -- as much as fits, and where to go on."""
    name, box = parse_range(rng)
    sh = find_sheet(book, sheet or name)
    if not sh["cells"]:
        return {"sheet": sh["name"], "range": "empty", "table": "(no cells with anything in them)"}
    r0, c0, r1, c1 = box or (0, 0, sh["rows"] - 1, sh["cols"] - 1)
    r1, c1 = min(r1, sh["rows"] - 1), min(c1, sh["cols"] - 1)
    if r0 > r1 or c0 > c1:
        return {"sheet": sh["name"], "range": range_name(r0, c0, max(r0, r1), max(c0, c1)), "table": "(outside the used range %s)" % used(sh)}
    cols_cut = c1 - c0 + 1 > MAX_COLS_SHOWN
    cc1 = c0 + MAX_COLS_SHOWN - 1 if cols_cut else c1
    cols = list(range(c0, cc1 + 1))
    lines = ["| | " + " | ".join(col_name(c) + (" (hidden)" if col_hidden(sh, c) else "") for c in cols) + " |",
             "|---|" + "---|" * len(cols)]
    size = sum(_jlen(x) + 2 for x in lines)              # (+2: the line break, as JSON writes it)
    rows_with = sorted({r for r, c in sh["cells"] if r0 <= r <= r1 and c0 <= c <= cc1})
    cap, cut = min(MAX_CELL_TEXT, max(30, chars // (3 * len(cols)))), []          # wide: long texts shorter, so that a row always fits
    last, cut_at = None, None
    for r in rows_with:
        line = "| %d%s | " % (r + 1, " (hidden)" if r in sh["hidden_rows"] else "") + " | ".join(
            _show(sh["cells"][(r, c)], formulas, cap, cut) if (r, c) in sh["cells"] else "" for c in cols) + " |"
        n = _jlen(line) + 2                              # as long as it will be in the tool's answer (JSON: backslashes doubled)
        if size + n > chars and last is not None:
            cut_at = r
            break
        lines.append(line)
        size += n
        last = r
    out: Dict[str, Any] = {"sheet": sh["name"], "range": range_name(r0, c0, r1, cc1), "table": "\n".join(lines)}
    more = []
    if cut_at is not None:
        more.append('rows %d-%d not shown: read on with range "%s"' % (cut_at + 1, r1 + 1, range_name(cut_at, c0, r1, cc1)))
    if cut:
        more.append("long texts shortened to %d characters: read fewer columns to see more of them" % cap)
    if cols_cut:
        more.append('columns %s-%s not shown: read them with range "%s"' % (col_name(cc1 + 1), col_name(c1), range_name(r0, cc1 + 1, r1, c1)))
    if more:
        out["more"] = "; ".join(more)
    if sh.get("row_pages") and last is not None:         # a document's pages: which rows shown stand on which page
        first = rows_with[0]
        spans = [(max(a, first), min((sh["row_pages"][i + 1][0] if i + 1 < len(sh["row_pages"]) else sh["rows"]) - 1, last), pg)
                 for i, (a, pg) in enumerate(sh["row_pages"])]
        said = ["rows %d-%d: page %d" % (a + 1, b + 1, pg) for a, b, pg in spans if a <= b]
        out["pages"] = "; ".join(said if len(said) <= 6 else said[:3] + ["..."] + said[-2:])
    merged = [m for m in sh["merged"] if _overlaps(m, r0, c0, r1, cc1)]
    if merged:
        out["merged_cells"] = merged[:30]                 # the value stands in the first cell of each
    if sh["no_value"]:
        out["formulas_without_value"] = sh["no_value"]
    if sh["hidden"]:
        out["sheet_hidden"] = True
    return out


def _overlaps(ref: str, r0: int, c0: int, r1: int, c1: int) -> bool:
    try:
        _, (a0, b0, a1, b1) = parse_range(ref)
    except (ValueError, TypeError):
        return False
    return not (a1 < r0 or a0 > r1 or b1 < c0 or b0 > c1)


def sum_range(book: dict, sheet: Optional[str], rng: str) -> dict:
    """The exact sum of the numbers in a range (decimal, by Kontor): how many were added, what was left out and why -- and what
    a reader of the sum must know: numbers that repeat other lines (sums and carry-overs the checks have proven, a SUM formula
    over cells of the range: in the sum, and the sum without them beside), numbers in hidden rows or columns (Excel's own SUM
    adds them, the eye does not), texts that read as figures (not added; in a workbook their sum beside)."""
    name, box = parse_range(rng)
    if box is None:
        raise ValueError("sum needs a range, e.g. C2:C40")
    sh = find_sheet(book, sheet or name)
    r0, c0, r1, c1 = box
    total, n, skipped = Decimal(0), 0, {}
    marked: Dict[str, List[Any]] = {}
    hidden, texts = [Decimal(0), 0], []
    checks(sh)
    again = sh.get("repeats") or {}                      # sums and carry-overs Kontor has proven to repeat other lines
    twice: Dict[str, List[Any]] = {}                     # ... those in the range: per mark ("" none) their sum, how many sums, how many carry-overs
    for (r, c), (kind, text, f) in sh["cells"].items():
        if r0 <= r <= r1 and c0 <= c <= c1:
            what = again.get((r, c)) or ("sum" if f and kind == "n" and _sums_within(f, box) else "")
            if kind == "n":
                total += Decimal(text)
                n += 1
                if r in sh["hidden_rows"] or (sh["hidden_cols"] and col_hidden(sh, c)):
                    hidden[0] += Decimal(text)
                    hidden[1] += 1
                if what:
                    t = twice.setdefault("", [Decimal(0), 0, 0])
                    t[0] += Decimal(text)
                    t[1 if what == "sum" else 2] += 1
            elif kind == "m":                            # a figure with its mark (1234.56 S): added up per mark, never mixed
                v, _, mark = text.partition(" ")
                m = marked.setdefault(mark, [Decimal(0), 0])
                m[0] += Decimal(v)
                m[1] += 1
                if what:
                    t = twice.setdefault(mark, [Decimal(0), 0, 0])
                    t[0] += Decimal(v)
                    t[1 if what == "sum" else 2] += 1
            else:
                k = {"t": "text", "d": "dates and times", "p": "percentages", "b": "true/false", "e": "errors", "": "formulas without value"}[kind]
                skipped[k] = skipped.get(k, 0) + 1
                if kind == "t" and len(texts) < MAX_CELLS and len(text) <= 40 and _FIGURISH.match(text.strip()):
                    texts.append(text.strip())
    out: Dict[str, Any] = {"sheet": sh["name"], "range": range_name(r0, c0, min(r1, max(sh["rows"] - 1, r0)), min(c1, max(sh["cols"] - 1, c0))),
                           "sum": plain(total), "numbers_added": n}
    twice = {k: t for k, t in twice.items() if t[1] + t[2] < (n if k == "" else marked[k][1])}       # (nothing but sums asked for: nothing to say)
    repeated = lambda t, whole: {"sums": t[1], "carry_overs": t[2], "sum": plain(t[0]), "without_them": plain(whole - t[0])}
    if marked:
        out["with_mark"] = {k: dict({"sum": plain(v[0]), "numbers_added": v[1]}, **({"of_which_repeat_other_lines": repeated(twice[k], v[0])} if k in twice else {}))
                            for k, v in sorted(marked.items())}
        if not n:                                        # nothing but marked figures: no sum across the marks (it would read as "0")
            del out["sum"], out["numbers_added"]
    if "" in twice:
        out["of_which_repeat_other_lines"] = repeated(twice[""], total)
    if twice:
        out["note"] = "the range holds lines of sums or carry-overs that repeat other lines (checked by Kontor): they are in the sum above -- for the lines alone take 'without_them'"
    if hidden[1]:
        out["of_which_hidden"] = {"sum": plain(hidden[0]), "numbers_added": hidden[1], "note": "in hidden rows or columns -- in the sum above; say so"}
    if skipped:
        out["left_out"] = skipped
    if texts and (sh.get("row_pages") or sh.get("as_written")):          # a document's or a CSV file's figures are read as written already: what stayed text
        odd = [t for t in texts if re.search(r"\d[.,' \u00a0\u202f]\d", t) and (figure_of(t, ",") is not None or figure_of(t, ".") is not None)]       # ... and would be a figure, were it sure
        if odd:
            out["texts_like_figures"] = {"count": len(odd), "e.g.": odd[0], "note": "kept as text -- the file does not say for sure which number is meant (12.345: thousands or "
                                                                                    "decimals? 18 231: one number or two?): NOT in the sum above; say so"}
    elif texts:
        sign = notation_of(texts)
        read = [v for v in (figure_of(t, sign) for t in texts) if v is not None]
        if read:
            out["texts_like_figures"] = {"count": len(read), "sum": plain(sum(read, Decimal(0))), "e.g.": texts[0],
                                         "note": "written as text in the file, read with '%s' as decimal sign: NOT in the sum above -- say so" % ("." if sign == "." else ",")}
    return out


def _sums_within(formula: str, box: Tuple[int, int, int, int]) -> bool:
    """Is a cell's formula a SUM over cells inside this range alone? Then the cell repeats what the range holds already."""
    m = _SUM_FORMULA.match(formula.strip())
    if not m:
        return False
    for part in re.split(r"[,;]", m.group(1).replace("$", "")):
        try:
            _, (a0, b0, a1, b1) = parse_range(part)
        except (ValueError, TypeError):
            return False
        if not (box[0] <= a0 and a1 <= box[2] and box[1] <= b0 and b1 <= box[3]):
            return False
    return True


# -- figures written as text (cells of a CSV file, texts in a workbook) ----------------------------------------------------------
_FIGURISH = re.compile(r"^[-+–−(]?\s?(?:€|EUR\s?)?\d[\d.,' \u00a0\u202f]*[-–−)]?\s?(?:%|€|EUR|[SH])?$")


_DE_WAY = re.compile(r"\d{1,3}(?:\.\d{3})+,\d+|\d+,\d{1,2}|\d+,\d{4,}")
_EN_WAY = re.compile(r"\d{1,3}(?:,\d{3})+\.\d+|\d+\.\d{1,2}|\d+\.\d{4,}")


_SPACED_WHOLE = re.compile(r"^[-+–−(]?\s?\d{1,3}(?:[ \u00a0\u202f]\d{3})+\s?[-–−)]?$")


def _way(text: str) -> str:
    """The decimal sign a figure written as text shows: "," (12,5; 1.234,56; 1 234,56), "." (12.5; 1,234.56) -- "" where it
    shows none (1234) or could be either (12.345: thousands or decimals?)."""
    s = re.sub(r"(?<=\d)[ \u00a0\u202f'](?=\d{3}(?!\d))", "", text.strip().strip("()-–−+%€ SHEUR"))       # (1 234,56 and 1'234.56: groups parted by a blank or an apostrophe)
    return "," if _DE_WAY.fullmatch(s) else "." if _EN_WAY.fullmatch(s) else ""


def notation_of(texts) -> str:
    """Which sign figures written as text use for decimals: "," (1.234,56) or "." (1,234.56) -- "?" where nothing says so
    (only figures like 12,345 or 12.345: thousands or decimals?) or the texts say both."""
    de = en = unclear = 0
    for t in texts:
        w = _way(t)
        if w == ",":
            de += 1
        elif w == ".":
            en += 1
        elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", t.strip().strip("()-–−+%€ SHEUR")):
            unclear += 1
    if de and en:
        return "?"
    return "," if de else "." if en else "?" if unclear else ","


def figure_of(text: str, sign: str) -> Optional[Decimal]:
    """A text as the number it writes -- by the same strict rules as a document's figures (pdf_tables.figure: 1.234,56,
    1.234,56-, (1.234,56); nothing guessed, 0800 is a code) -- or None. With a mark (S, H, another money) or per cent: None."""
    import pdf_tables                                    # (its rules for a figure as written; no part of it reads a file)
    kind, v = pdf_tables.figure(text, de=sign != ".", unsure=sign == "?")
    return Decimal(v) if kind == "n" else None


# -- what the table says about itself: sums, carry-overs, debit and credit -- checked exactly ------------------------------------
_SUM_WORD = re.compile(r"(?i)^\W*(?:(?:zwischen|teil|gesamt|end)?summen?|gesamt(?:betrag|ergebnis)?|insgesamt|(?:sub|grand )?totals?|sum)\b")
_CARRY_WORD = re.compile(r"(?i)^\W*(?:[üu]e?bertr[aä]ge?|vortrag|carry[- ]?over|(?:carried|brought) forward)\b")
_SUM_FORMULA = re.compile(r"(?i)^SUM\(((?:\$?[A-Z]{1,3}\$?\d{1,7}(?::\$?[A-Z]{1,3}\$?\d{1,7})?)(?:[,;]\$?[A-Z]{1,3}\$?\d{1,7}(?::\$?[A-Z]{1,3}\$?\d{1,7})?)*)\)$")
CHECK_BLOCKS = 400                 # groups a sum is tried against, counted back from it (and all before it together)


def _amount(cell: Optional[Tuple[str, str, str]]) -> Optional[Decimal]:
    """A cell's number for adding up: as it stands; with the mark S as it stands, with H its negative (debit and credit of one
    column add up against each other). Another mark (a foreign money), per cent, text: none."""
    if cell is None:
        return None
    if cell[0] == "n":
        return Decimal(cell[1])
    if cell[0] == "m":
        v, _, mark = cell[1].partition(" ")
        return Decimal(v) if mark == "S" else -Decimal(v) if mark == "H" else None
    return None


def _check_column(c: int, valued: List[int], by_row: dict, carried: set, total, own: set, label: dict, sums: List[dict], carries: List[dict], blocks: int) -> None:
    """One column of figures, line by line: its sums and carry-overs against the lines they stand for (a sum against the last
    `blocks` groups before it, each with all after it, and against all lines)."""
    name = col_name(c)
    acc = Decimal(0)                                     # all lines so far, added up
    groups: List[Tuple[int, Decimal]] = []               # where each group of lines began: (its first line, what stood before it)
    lines: List[int] = []                                # the lines added so far (for counting those of a sum)
    open_ = False
    waiting: Optional[dict] = None                       # a line of sums not proven yet: the lines right below it may add up to it

    def below() -> None:
        if waiting is not None and waiting["first"] is not None and waiting["below"] == waiting["value"]:          # a heading with the sum of its lines below
            waiting.update(ok=True, of="%s%d:%s%d" % (name, waiting["first"] + 1, name, waiting["last"] + 1),
                           lines=bisect.bisect_right(lines, waiting["last"]) - bisect.bisect_left(lines, waiting["first"]))
    for r in valued:
        v = _amount(by_row[r].get(c))
        if r in carried:
            if v is not None and (acc != 0 or v != 0):
                carries.append({"cell": "%s%d" % (name, r + 1), "col": c, "row": r, "ok": v == acc or any(v == acc - before for _, before in groups[-blocks:]), "by": plain(v - acc)})
            continue
        if not total(r):
            if r in own:                                 # a position standing for itself: a line, but none of the heading's before it
                below()
                waiting, open_ = None, False
            if v is not None:
                if not open_:
                    groups.append((r, acc))
                    open_ = True
                acc += v
                lines.append(r)
                if waiting is not None:
                    waiting["below"] += v
                    waiting["first"] = r if waiting["first"] is None else waiting["first"]
                    waiting["last"] = r
            continue
        below()
        waiting = None
        open_ = False                                    # (a line of sums ends the group, with a figure in this column or without)
        if v is None:
            continue
        tries = [(acc - before, first) for first, before in reversed(groups[-blocks:])] + ([(acc, groups[0][0])] if groups else [])
        hit = next((first for got, first in tries if got == v), None)
        near = min(tries, key=lambda t: abs(v - t[0])) if tries else None          # what comes closest: named when nothing fits
        e = {"cell": "%s%d" % (name, r + 1), "col": name, "c": c, "row": r, "value": v, "label": label.get(r, ""), "ok": hit is not None, "of": "", "lines": 0, "first": None, "last": None,
             "below": Decimal(0), "by": plain(v - near[0]) if near else "", "above": "%s%d:%s%d" % (name, near[1] + 1, name, r) if near else "", "tried": bool(tries), "hit": hit}
        if hit is not None:
            e.update(of="%s%d:%s%d" % (name, hit + 1, name, r), lines=len(lines) - bisect.bisect_left(lines, hit))
        else:
            e["tries"] = {first: got for got, first in tries}
            waiting = e
        sums.append(e)
    below()


def _as_beside(e: dict, beside: List[dict]) -> None:
    """A sum that does not fit, measured against the lines its row adds up in the columns where it fits (beside: a row of sums
    adds up the same lines in every column) -- else it stays measured against the lines that come closest."""
    for g in beside:
        first = min((f for f in e.get("tries", {}) if f >= g["hit"]), default=None) if g["hit"] is not None else None      # (this column's first line of them)
        if first is not None:
            e.update(by=plain(e["value"] - e["tries"][first]), above="%s%d:%s%d" % (e["col"], g["hit"] + 1, e["col"], e["row"]), tried=True)
            return
    for g in beside:
        if g["hit"] is None and g["first"] is not None and (g["first"], g["last"]) == (e["first"], e["last"]):       # a heading: its lines below
            e.update(by=plain(e["value"] - e["below"]), above="%s%d:%s%d" % (e["col"], e["first"] + 1, e["col"], e["last"] + 1), tried=True)
            return


def checks(sh: dict) -> dict:
    """What Kontor can prove about a table's own arithmetic, to the cent (kept with the sheet): each line of a sum against the
    lines it adds up -- the lines right above it, or the groups above it together, or (a heading with its own value) the
    lines below it; each carry-over against all lines before it; debit against credit; a workbook's SUM formulas against
    their cells. A sum that fits says its figures and the lines between were read right and none is missing; one that does not
    is named with what is missing -- a figure misread, a line lost, or a sum of another kind (then most do not fit, and
    Kontor says only how many do). Nothing here changes a cell."""
    if "checks" in sh:
        return sh["checks"]
    cells, rows = sh["cells"], sh["rows"]
    out: Dict[str, Any] = {}
    sh["checks"] = out
    if rows < 3 or len(cells) > MAX_CELLS:
        return out
    by_row: Dict[int, Dict[int, Tuple[str, str, str]]] = {}
    for (r, c), v in cells.items():
        by_row.setdefault(r, {})[c] = v
    number = lambda v: v[0] in ("n", "m")
    label: Dict[int, str] = {}                           # each line's first text with letters
    for r, row in by_row.items():
        for c in sorted(row):
            if row[c][0] == "t" and re.search(r"[^\W\d_]{2}", row[c][1]):
                label[r] = row[c][1]
                break
    summed = {r for r in label if _SUM_WORD.match(label[r])}
    carried = {r for r in label if _CARRY_WORD.match(label[r])}
    valued = [r for r in sorted(by_row) if any(number(v) for v in by_row[r].values())]
    plain_rows = [r for r in valued if r not in summed and r not in carried]
    key = None                                           # the column of the lines' own numbers (accounts): the lines to add up have one, sums none
    for c in sorted({c for r in plain_rows[:2000] for c in by_row[r]})[:8]:          # (among the first columns; bounded work on any sheet)
        have = [by_row[r][c] for r in plain_rows if c in by_row[r] and by_row[r][c][1].strip()]
        if len(have) >= max(3, 0.5 * len(plain_rows)):
            if not any(c in by_row[r] for r in summed) and all(v[0] == "n" or (v[0] == "t" and re.fullmatch(r"\w{1,12}", v[1].strip())) for v in have):
                key = c
            break                                        # (the first column most lines fill: their numbers -- or their labels: no key)
    sh["key"] = key
    foreign = {c for (r, c), v in cells.items() if v[0] == "m" and v[1].rpartition(" ")[2] not in ("S", "H")}       # another money: not added up here
    own: set = set()                                     # lines without an account that are no sum either: a position standing for itself
    sums: List[dict] = []
    carries: List[dict] = []
    cols: List[int] = []
    detail: List[int] = []
    for again in (False, True):
        total = lambda r: r in summed or (key is not None and key not in by_row[r] and r not in own)
        detail = [r for r in valued if r not in carried and not total(r)]
        filled: Dict[int, int] = {}
        for r in detail:
            for c, v in by_row[r].items():
                if number(v):
                    filled[c] = filled.get(c, 0) + 1
        cols = sorted(c for c, n in filled.items() if n >= 2 and c != key and c not in foreign)
        cols = cols[:max(1, min(60, 2000000 // max(1, len(valued))))]            # bounded work: a sheet of a hundred thousand lines is checked in its first columns
        blocks = max(8, min(CHECK_BLOCKS, 1500000 // max(1, len(cols) * sum(1 for r in valued if total(r)))))
        sums, carries = [], []
        for c in cols:
            _check_column(c, valued, by_row, carried, total, own, label, sums, carries, blocks)
        sums = [e for e in sums if e["ok"] or e["tried"] or e["first"] is not None]      # (a figure no line could add up to: no sum at all)
        if again or key is None:
            break
        fits: Dict[int, bool] = {}
        for e in sums:
            fits[e["row"]] = fits.get(e["row"], False) or e["ok"]
        own = {r for r, ok in fits.items() if not ok and r not in summed}       # a figure of its own among the accounts (a year's result): a line like them
        if not own:
            break
    if not cols:
        return out
    good = [e for e in sums if e["ok"]]
    if any(e["lines"] >= 2 for e in good):               # (one line "added up" proves nothing: a statement of income names its lines that way)
        bad = [e for e in sums if not e["ok"]]
        best = max(good, key=lambda e: e["lines"])
        out["sums"] = {"checked": len(sums), "equal": len(good), "e.g.": "%s = sum of %s" % (best["cell"], best["of"])}
        if bad and len(good) >= 3 and len(bad) <= max(2, len(sums) // 5):                  # most fit: the few that do not are named
            beside: Dict[int, List[dict]] = {}
            for g in good:
                beside.setdefault(g["row"], []).append(g)
            for e in bad[:40]:
                _as_beside(e, beside.get(e["row"], ()))
            out["sums"]["not_equal"] = [{"cell": e["cell"], "label": e["label"][:40], "more_than_its_lines": e["by"], "lines": e["above"]} for e in bad[:40] if e["tried"]][:6]
    hold = [e for e in carries if e["ok"]]
    if hold:
        named: List[dict] = []
        per: Dict[int, List[dict]] = {}
        for e in carries:
            per.setdefault(e["col"], []).append(e)
        for c in sorted(c for c, mine in per.items() if not all(e["ok"] for e in mine))[:6] if len(hold) >= 2 else ():
            mine = per[c]
            i = next(i for i, e in enumerate(mine) if not e["ok"])
            rest = mine[i:]
            if len(rest) >= 2 and all(not e["ok"] and e["by"] == rest[0]["by"] for e in rest):       # all from one on, by the same amount: one slip before it
                named.append({"from": rest[0]["cell"], "more_than_lines_before": rest[0]["by"], **({"after": mine[i - 1]["cell"]} if i else {})})
            elif sum(1 for e in mine if not e["ok"]) <= max(2, len(mine) // 5):
                named.extend({"cell": e["cell"], "more_than_lines_before": e["by"]} for e in mine if not e["ok"])
        if 2 * len(hold) >= len(carries) or any("from" in e for e in named):       # most fit, or what does not is off by one amount: carry-overs they are
            out["carry_overs"] = {"checked": len(carries), "equal": len(hold)}
            if named:
                out["carry_overs"]["not_equal"] = named[:6]
    if "sums" in out or "carry_overs" in out:            # what repeats other lines, proven: a sum over a range says so (sum_range)
        sh["repeats"] = {(e["row"], e["c"]): "sum" for e in good} if "sums" in out else {}
        if "carry_overs" in out:
            sh["repeats"].update({(e["row"], e["col"]): "carry" for e in hold})
    pairs = _debit_credit(sh, by_row, detail, set(cols))
    if pairs:
        out["debit_credit"] = pairs
    formulas = _formula_sums(sh)
    if formulas:
        out["formulas"] = formulas
    return out


def _debit_credit(sh: dict, by_row: dict, detail: List[int], cols: set) -> List[dict]:
    """Columns headed Soll and Haben side by side (the same words beside them: "Okt/2026 Soll", "Okt/2026 Haben"): the lines'
    debit added up against their credit. All accounts of a ledger balance; a selection of them need not -- so said either
    way, never as an error. And a column of figures marked S and H: its S against its H."""
    out: List[dict] = []
    head = None
    for r in sorted(by_row)[:80]:
        texts = {c: v[1] for c, v in by_row[r].items() if v[0] == "t"}
        if any(re.search(r"(?i)\bsoll\b", t) for t in texts.values()) and any(re.search(r"(?i)\bhaben\b", t) for t in texts.values()):
            head = texts
            break
    add = lambda c: sum((v for v in (_amount(by_row[r].get(c)) for r in detail) if v is not None), Decimal(0))
    if head:
        rest = lambda t, word: re.sub(r"\s+", " ", re.sub(r"(?i)\b%s\b" % word, "", t)).strip().lower()
        soll = [c for c in sorted(head) if re.search(r"(?i)\bsoll\b", head[c]) and c in cols]
        haben = [c for c in sorted(head) if re.search(r"(?i)\bhaben\b", head[c]) and c in cols]
        for c in soll:
            match = next((h for h in haben if h > c and rest(head[h], "haben") == rest(head[c], "soll")), None)
            if match is not None:
                haben.remove(match)
                a, b = add(c), add(match)
                out.append({"columns": "%s/%s" % (col_name(c), col_name(match)),
                            "debit": plain(a), "credit": plain(b), "equal": a == b, **({} if a == b else {"debit_more_by": plain(a - b)})})
    for c in sorted(cols):                               # one column, its figures marked S or H
        marked = [by_row[r][c][1] for r in detail if c in by_row[r] and by_row[r][c][0] == "m"]
        s_ = sum((Decimal(t.partition(" ")[0]) for t in marked if t.endswith(" S")), Decimal(0))
        h_ = sum((Decimal(t.partition(" ")[0]) for t in marked if t.endswith(" H")), Decimal(0))
        if len(marked) >= 5 and any(t.endswith(" S") for t in marked) and any(t.endswith(" H") for t in marked):
            out.append({"columns": "S/H in %s" % col_name(c), "debit": plain(s_), "credit": plain(h_), "equal": s_ == h_, **({} if s_ == h_ else {"debit_more_by": plain(s_ - h_)})})
    return out[:8]


def _formula_sums(sh: dict) -> dict:
    """A workbook's SUM formulas over cells of their own sheet: the value Excel saved against the cells added up here -- they
    differ where the file was saved without calculating anew (written by a program), or a cell in the range is text."""
    checked = equal = 0
    bad: List[dict] = []
    done, room = 0, 2000000                              # formulas looked at, cells still to visit: bounded work on any sheet
    for (r, c), (kind, text, f) in sh["cells"].items():
        m = _SUM_FORMULA.match(f.strip()) if f and kind == "n" and len(f) <= 2000 else None
        if not m or done >= 2000 or room <= 0:
            continue
        done += 1
        got, clean = Decimal(0), True
        for part in re.split(r"[,;]", m.group(1).replace("$", "")):
            try:
                _, (a0, b0, a1, b1) = parse_range(part)
            except (ValueError, TypeError):
                clean = False
                break
            room -= (a1 - a0 + 1) * (b1 - b0 + 1)
            if room < 0:
                clean = False
                break
            for rr in range(a0, a1 + 1):
                for cc in range(b0, b1 + 1):
                    v = sh["cells"].get((rr, cc))
                    if v is not None and v[0] == "n":
                        got += Decimal(v[1])
                    elif v is not None and v[0] not in ("t", "b"):
                        clean = False                    # (a date or per cent -- Excel adds them as numbers --, an error, no value: nothing to check against)
        if not clean:
            continue
        checked += 1
        saved = Decimal(text)
        if abs(saved - got) <= Decimal("0.000001") * max(Decimal(1), abs(saved)):
            equal += 1
        elif len(bad) < 6:
            bad.append({"cell": "%s%d" % (col_name(c), r + 1), "saved": plain(saved), "its_cells_add_up_to": plain(got)})
    if not checked:
        return {}
    out: Dict[str, Any] = {"sum_formulas_checked": checked, "equal": equal}
    if bad:
        out["not_equal"] = bad
    return out


def _more(by: str) -> str:
    return "%s less" % by[1:] if by.startswith("-") else "%s more" % by


def checked_text(sh: dict) -> str:
    """The checks in a line for the model (empty: nothing to check, or nothing that proves anything)."""
    ch = checks(sh)
    said = []
    su = ch.get("sums")
    if su and su["equal"]:
        t = "%d of %d sums equal the lines they add up (e.g. %s)" % (su["equal"], su["checked"], su.get("e.g.", ""))
        if su.get("not_equal"):
            t += "; NOT " + ", ".join("%s (%s: %s than %s)" % (e["cell"], json.dumps(_clean(e["label"]), ensure_ascii=False), _more(e["more_than_its_lines"]), e["lines"])
                                      for e in su["not_equal"]) \
                 + " -- a figure misread or a line missing there, or a sum of another kind: say so, do not smooth it over"
        elif su["equal"] < su["checked"]:
            t += "; the other %d do not (sums of another kind, or figures misread there: not known)" % (su["checked"] - su["equal"])
        said.append(t)
    ca = ch.get("carry_overs")
    if ca and ca["equal"]:
        t = "%d of %d carry-overs equal the lines before them" % (ca["equal"], ca["checked"])
        if ca.get("not_equal"):
            t += "; NOT " + ", ".join(("%s and all after it (%s: a figure misread or a line missing %s)" % (e["from"], _more(e["more_than_lines_before"]),
                                                                                                      "between %s and it" % e["after"] if e.get("after") else "before it")) if "from" in e
                                      else "%s (%s)" % (e["cell"], _more(e["more_than_lines_before"])) for e in ca["not_equal"])
        said.append(t + " (carry-overs repeat amounts: never add them to the lines)")
    pairs = ch.get("debit_credit") or []
    same = ["%s: %s" % (p["columns"], p["debit"]) for p in pairs if p["equal"]]
    if same:
        said.append("debit equals credit over the lines -- " + ", ".join(same))
    for p in pairs:
        if not p["equal"]:
            said.append("debit and credit of the lines in %s differ: %s and %s (all accounts of a ledger balance, a part of them need not)" % (p["columns"], p["debit"], p["credit"]))
    fo = ch.get("formulas")
    if fo:
        t = "%d of %d SUM formulas equal their cells" % (fo["equal"], fo["sum_formulas_checked"])
        if fo.get("not_equal"):
            t += "; NOT " + ", ".join("%s (saved %s, its cells add up to %s)" % (e["cell"], e["saved"], e["its_cells_add_up_to"]) for e in fo["not_equal"]) \
                 + " -- the file may have been saved without calculating anew: say so"
        said.append(t)
    return "; ".join(said)


# -- looking rows up (a long file is not read page by page) ---------------------------------------------------------------------
FIND_ROWS = 60                     # rows of one answer at most
_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _fold(s: str) -> str:
    """For comparing: no case, umlauts as two letters (Rueckstellung finds Rückstellung), blanks as one."""
    return re.sub(r"\s+", " ", s.casefold().translate(_FOLD))


def _head_rows(sh: dict, by_row: Dict[int, Dict[int, Tuple[str, str, str]]]) -> List[int]:
    """The rows that head a sheet's table -- the names of its columns: the rows of texts (up to three, one below the other) above
    the first line with numbers beside a text; a group's own heading may stand between them and that line, and above the names
    a row with a single text counts if it stands over a column further right (the second line of a column's name, no title)."""
    filled = lambda r: sum(1 for v in by_row[r].values() if v[1].strip()) if r in by_row else 0
    names = lambda r: r in by_row and all(v[0] == "t" for v in by_row[r].values())
    first = next((r for r in sorted(by_row) if filled(r) >= 3 and any(v[0] in ("n", "m", "p") for v in by_row[r].values()) and any(v[0] == "t" for v in by_row[r].values())), None)
    if first is None:
        return []
    r, between = first - 1, 0
    while r >= 0 and between < 2 and filled(r) <= 2 and not (names(r) and filled(r) == 2):       # a group's heading, an empty row
        r, between = r - 1, between + 1
    left = min(c for row in by_row.values() for c in row)
    out: List[int] = []
    while r >= 0 and len(out) < 3 and names(r) and (filled(r) >= 2 or (out and min(by_row[r]) > left)):
        out.insert(0, r)
        r -= 1
    return out


def find(book: dict, words: str, sheet: Optional[str] = None, rng: str = "", chars: int = RENDER_CHARS) -> dict:
    """The rows that hold all of the words asked for (in any of their cells; no case, ä as ae; a figure as shown or as written:
    1.234,56 finds 1234.56; "two words" in quotes together) -- over one sheet or, none named, over all: as a grid with their
    addresses, the heading rows of the table above them, and the exact sums of the rows found per column (a selection added
    up by Kontor: all lines of one branch, one account over the months). What does not fit is counted and said."""
    asked = [a or b for a, b in re.findall(r'"([^"]+)"|(\S+)', str(words or "")[:200])][:8]
    if not asked:
        raise ValueError("find needs words to look for, e.g. \"Miete\" or an account's number")
    name, box = parse_range(rng)
    sheets = [find_sheet(book, sheet or name)] if (sheet or name) else [sh for sh in book["sheets"] if sh["cells"]]
    wanted = []
    for w in asked:
        forms = {_fold(w)}
        if re.fullmatch(r"[-+(]?\d[\d.,' ]*[-)]?", w) and not re.fullmatch(r"\d+", w):       # a figure as written: also as the grid shows it
            for sign in (",", "."):
                v = figure_of(w, sign)
                if v is not None:
                    forms.add(plain(v))
        wanted.append(forms)
    out: Dict[str, Any] = {"find": " ".join(asked)}
    tables, total, shown, size, more, each = [], 0, 0, 0, False, [0] * len(wanted)
    for sh in sheets:
        by_row: Dict[int, Dict[int, Tuple[str, str, str]]] = {}
        for (r, c), v in sh["cells"].items():
            by_row.setdefault(r, {})[c] = v
        r0, c0, r1, c1 = box or (0, 0, sh["rows"] - 1, sh["cols"] - 1)
        hits = []
        for r in sorted(by_row):
            if not r0 <= r <= r1:
                continue
            texts = [_fold(v[1][:1000]) for c, v in sorted(by_row[r].items())]
            line = " | ".join(texts)
            got = [any(f in line if not re.fullmatch(r"-?\d+(?:\.\d+)?", f) else f in texts or f in line.split() for f in forms) for forms in wanted]
            for i, g in enumerate(got):
                each[i] += g
            if all(got):
                hits.append(r)
        if not hits:
            continue
        total += len(hits)
        cols = list(range(0, min(sh["cols"], MAX_COLS_SHOWN)))
        head = [r for r in _head_rows(sh, by_row) if r not in hits]
        lines = ["| | " + " | ".join(col_name(c) + (" (hidden)" if col_hidden(sh, c) else "") for c in cols) + " |", "|---|" + "---|" * len(cols)]
        cap = min(MAX_CELL_TEXT, max(30, chars // (3 * len(cols))))
        row_line = lambda r: "| %d%s | " % (r + 1, " (hidden)" if r in sh["hidden_rows"] else "") + " | ".join(
            _show(by_row[r][c], False, cap) if c in by_row[r] else "" for c in cols) + " |"
        lines += [row_line(r) for r in head]
        if head:
            lines.append("| … |" + " |" * len(cols))
        used = []
        for r in hits:
            ln = row_line(r)
            n = _jlen(ln) + 2
            if (size + sum(_jlen(x) + 2 for x in lines) + n > chars or shown >= FIND_ROWS) and (used or tables):
                more = True
                break
            lines.append(ln)
            used.append(r)
            shown += 1
        if not used:
            more = True
            continue
        size += sum(_jlen(x) + 2 for x in lines)
        entry: Dict[str, Any] = {"sheet": sh["name"], "rows_found": len(hits), "table": "\n".join(lines)}
        if sh["cols"] > len(cols):
            entry["columns_not_shown"] = "%s-%s: read a row found with a range to see them" % (col_name(len(cols)), col_name(sh["cols"] - 1))
        if len(hits) >= 2:                               # the rows found, added up per column (all of them, shown or not)
            sums = {}
            checks(sh)
            again = sh.get("repeats") or {}              # (sums and carry-overs proven to repeat other lines: said where they are among the rows found)
            named = min((c for r in hits[:2000] for c, v in by_row[r].items() if v[0] == "t" and re.search(r"[^\W\d_]{2}", v[1])), default=0)     # where the rows' names begin
            for c in cols:
                vals = [(r, by_row[r][c]) for r in hits if c in by_row[r] and by_row[r][c][0] == "n"]
                # the lines' own numbers (accounts, staff, positions) are nothing to add up: the column the checks took for them, or whole numbers of one
                # length left of the names
                codes = c == sh.get("key") or (c < named and len({len(v[1]) for _, v in vals}) == 1 and all(re.fullmatch(r"\d{1,8}", v[1]) for _, v in vals))
                if len(vals) >= 2 and not codes:
                    whole = sum((Decimal(v[1]) for _, v in vals), Decimal(0))
                    twice = [Decimal(v[1]) for r, v in vals if (r, c) in again]
                    sums[col_name(c)] = "%s (%d numbers%s)" % (plain(whole), len(vals), "" if not twice else
                                                               ": all of them sums or carry-overs, they may repeat one another" if len(twice) == len(vals) else
                                                               "; %d of them sums or carry-overs that repeat other lines: %s without them" % (len(twice), plain(whole - sum(twice, Decimal(0)))))
            if sums:
                entry["sums_of_rows_found"] = sums
        if sh.get("row_pages"):
            pages = sorted({pg for r in used for a, pg in [max((x for x in sh["row_pages"] if x[0] <= r), default=sh["row_pages"][0])]})
            entry["pages"] = ", ".join(str(x) for x in pages[:12]) + (" …" if len(pages) > 12 else "")
        tables.append(entry)
    out["rows_found"] = total
    if not total:
        out["note"] = "No row holds %s. Per word: %s. Fewer or other words, or read the sheet in pieces." % (
            "all of these words" if len(asked) > 1 else "this word", "; ".join("%s: %d rows" % (json.dumps(w, ensure_ascii=False), n) for w, n in zip(asked, each)))
        return out
    out["found"] = tables
    if more or shown < total:
        out["more"] = "%d of the %d rows found are shown: narrow the words, name a sheet, or give a range to look in" % (shown, total)
    return out
