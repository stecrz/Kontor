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
    """The exact sum of the numbers in a range (decimal, by Kontor): how many were added, what was left out and why."""
    name, box = parse_range(rng)
    if box is None:
        raise ValueError("sum needs a range, e.g. C2:C40")
    sh = find_sheet(book, sheet or name)
    r0, c0, r1, c1 = box
    total, n, skipped = Decimal(0), 0, {}
    for (r, c), (kind, text, _) in sh["cells"].items():
        if r0 <= r <= r1 and c0 <= c <= c1:
            if kind == "n":
                total += Decimal(text)
                n += 1
            else:
                k = {"t": "text", "d": "dates and times", "p": "percentages", "b": "true/false", "e": "errors", "": "formulas without value"}[kind]
                skipped[k] = skipped.get(k, 0) + 1
    out: Dict[str, Any] = {"sheet": sh["name"], "range": range_name(r0, c0, min(r1, max(sh["rows"] - 1, r0)), min(c1, max(sh["cols"] - 1, c0))),
                           "sum": plain(total), "numbers_added": n}
    if skipped:
        out["left_out"] = skipped
    return out
