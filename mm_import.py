"""Import von Saldenverlaeufen aus Tabellen (CSV/XLSX): Langformat (Datum, Konto, Saldo), Matrix
(Zeilen = Konten, Spalten = Stichtage) oder transponiert (Zeilen = Stichtage, Spalten = Konten).
Ohne Fremdbibliotheken: XLSX wird direkt aus dem ZIP gelesen (Shared Strings, Datumsformate)."""
from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

MONTHS = {"jan": 1, "januar": 1, "january": 1, "feb": 2, "februar": 2, "february": 2, "mär": 3, "mrz": 3, "maerz": 3, "märz": 3, "mar": 3, "march": 3,
          "apr": 4, "april": 4, "mai": 5, "may": 5, "jun": 6, "juni": 6, "june": 6, "jul": 7, "juli": 7, "july": 7, "aug": 8, "august": 8,
          "sep": 9, "sept": 9, "september": 9, "okt": 10, "oct": 10, "oktober": 10, "october": 10, "nov": 11, "november": 11, "dez": 12, "dec": 12, "dezember": 12, "december": 12}

_RE_ISO = re.compile(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?(?:[T ].*)?$")
_RE_DE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{2,4})\.?$")
_RE_MY = re.compile(r"^(\d{1,2})[./](\d{4})$")
_RE_TEXT = re.compile(r"^([A-Za-zÄÖÜäöü]{3,9})\.?\s*[ '’]?\s*(\d{2,4})$")


def parse_date_cell(v: Any) -> Optional[Tuple[str, str]]:
    """-> (JJJJ-MM, TT) oder None. Akzeptiert datetime/date, ISO, TT.MM.JJJJ, MM/JJJJ, 'Jan 2024', 'Januar 2024'."""
    if isinstance(v, datetime):
        return "%04d-%02d" % (v.year, v.month), "%02d" % v.day
    if isinstance(v, date):
        return "%04d-%02d" % (v.year, v.month), "%02d" % v.day
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    m = _RE_ISO.match(s)
    if m and 1900 <= int(m.group(1)) <= 2200 and 1 <= int(m.group(2)) <= 12:
        return "%s-%02d" % (m.group(1), int(m.group(2))), "%02d" % int(m.group(3) or 1)
    m = _RE_DE.match(s)
    if m:
        y = int(m.group(3)); y = y + 2000 if y < 100 else y
        if 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(1)) <= 31:
            return "%04d-%02d" % (y, int(m.group(2))), "%02d" % int(m.group(1))
    m = _RE_MY.match(s)
    if m and 1 <= int(m.group(1)) <= 12:
        return "%s-%02d" % (m.group(2), int(m.group(1))), "31"
    m = _RE_TEXT.match(s)
    if m:
        mo = MONTHS.get(m.group(1).lower())
        if mo:
            y = int(m.group(2)); y = y + 2000 if y < 100 else y
            return "%04d-%02d" % (y, mo), "31"
    return None


def parse_number(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    s = v.strip().replace("€", "").replace("EUR", "").replace(" ", "").replace(" ", "")
    if not s or s in ("-", "–"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if re.match(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$", s) or ("," in s and "." not in s):
        s = s.replace(".", "").replace(",", ".")
    elif re.match(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$", s):
        s = s.replace(",", "")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


# ---------------------------------------------------------------------------
# XLSX lesen (ohne openpyxl)
# ---------------------------------------------------------------------------

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
_EPOCH = datetime(1899, 12, 30)


def _col_index(ref: str) -> int:
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return n - 1


def _is_date_fmt(code: str) -> bool:
    c = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", code or "").lower()
    if "y" in c or "d" in c:
        return True
    return "m" in c and "h" not in c and "s" not in c


def read_xlsx(data: bytes) -> Dict[str, List[List[Any]]]:
    """Blattname -> Zeilen (Listen von Werten: str, float, datetime, None)."""
    out: Dict[str, List[List[Any]]] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        shared: List[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % _NS["m"])))
        date_styles: List[bool] = []
        if "xl/styles.xml" in names:
            st = ET.fromstring(z.read("xl/styles.xml"))
            fmts = {int(f.get("numFmtId")): f.get("formatCode", "") for f in st.findall("m:numFmts/m:numFmt", _NS)}
            builtin_dates = set(range(14, 23)) | set(range(45, 48)) | {27, 28, 29, 30, 31, 36, 50, 51, 52, 53, 54, 55, 56, 57, 58}
            for xf in st.findall("m:cellXfs/m:xf", _NS):
                fid = int(xf.get("numFmtId", "0"))
                date_styles.append(fid in builtin_dates or (fid in fmts and _is_date_fmt(fmts[fid])))
        rels: Dict[str, str] = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
                rels[rel.get("Id")] = rel.get("Target")
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        for sh in wb.findall("m:sheets/m:sheet", _NS):
            rid = sh.get("{%s}id" % _NS["r"])
            target = rels.get(rid, "")
            path = target if target.startswith("xl/") else ("xl/" + target.lstrip("/"))
            if path not in names:
                continue
            rows: Dict[int, Dict[int, Any]] = {}
            root = ET.fromstring(z.read(path))
            for c in root.iter("{%s}c" % _NS["m"]):
                ref = c.get("r") or ""
                rown = int(re.sub(r"[A-Za-z]", "", ref) or 0) - 1
                coln = _col_index(ref)
                t = c.get("t")
                sidx = int(c.get("s") or 0)
                v_el = c.find("m:v", _NS)
                val: Any = None
                if t == "s" and v_el is not None and v_el.text is not None:
                    val = shared[int(v_el.text)] if int(v_el.text) < len(shared) else ""
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter("{%s}t" % _NS["m"]))
                elif t in ("str", "e"):
                    val = v_el.text if v_el is not None else ""
                elif t == "b":
                    val = (v_el is not None and v_el.text == "1")
                elif v_el is not None and v_el.text not in (None, ""):
                    try:
                        num = float(v_el.text)
                    except ValueError:
                        num = None
                    if num is not None and sidx < len(date_styles) and date_styles[sidx] and 1 < num < 2958466:
                        val = _EPOCH + timedelta(days=num)
                    else:
                        val = num
                if val is None:
                    continue
                rows.setdefault(rown, {})[coln] = val
            if not rows:
                out[sh.get("name") or path] = []
                continue
            maxc = max(max(r) for r in rows.values()) + 1
            grid = []
            for i in range(max(rows) + 1):
                r = rows.get(i, {})
                grid.append([r.get(j) for j in range(maxc)])
            out[sh.get("name") or path] = grid
    return out


# ---------------------------------------------------------------------------
# Tabellen interpretieren
# ---------------------------------------------------------------------------

def read_csv_rows(text: str) -> List[List[Any]]:
    text = text.lstrip("﻿")
    if not text.strip():
        return []
    sample = text[:3000]
    counts = {d: sample.count(d) for d in (";", "\t", ",")}
    delim = max(counts, key=lambda d: counts[d]) if any(counts.values()) else ";"
    return [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(str(c).strip() for c in r)]


def _is_text(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != "" and parse_number(v) is None and parse_date_cell(v) is None


def balances_from_rows(rows: List[List[Any]]) -> Dict[str, Dict[str, float]]:
    """Kontoname -> {JJJJ-MM: Saldo} (letzter Wert je Monat). Erkennt Matrix (Stichtage in einer Zeile oder Spalte)
    und Langformat (Datum, [Konto], Saldo)."""
    if not rows:
        return {}
    width = max(len(r) for r in rows)
    rows = [list(r) + [None] * (width - len(r)) for r in rows]
    best: Dict[str, Dict[str, Tuple[str, float]]] = {}

    def put(name: str, mk: str, day: str, v: float):
        cur = best.setdefault(name, {}).get(mk)
        if cur is None or day >= cur[0]:
            best[name][mk] = (day, v)

    # 1. Stichtage in einer Zeile (Konten als Zeilen): mindestens zwei Stichtage, Mehrheit der belegten Zellen
    date_rows = []
    for i, r in enumerate(rows):
        cols = [(j, parse_date_cell(c)) for j, c in enumerate(r) if parse_date_cell(c)]
        filled = sum(1 for c in r if c not in (None, "") and str(c).strip())
        if len(cols) >= 2 and len(cols) * 2 >= filled:
            date_rows.append((i, cols))
    # 2. Stichtage in einer Spalte (Konten als Spalten oder Langformat)
    date_cols = []
    for j in range(width):
        hits = [(i, parse_date_cell(rows[i][j])) for i in range(len(rows)) if parse_date_cell(rows[i][j])]
        filled = sum(1 for i in range(len(rows)) if rows[i][j] not in (None, "") and str(rows[i][j]).strip())
        if hits and len(hits) * 2 >= filled - 1:
            date_cols.append((j, hits))
    date_rows.sort(key=lambda x: -len(x[1]))
    date_cols.sort(key=lambda x: -len(x[1]))
    if date_rows and (not date_cols or len(date_rows[0][1]) > len(date_cols[0][1])):
        hi, cols = date_rows[0]
        for i in range(hi + 1, len(rows)):
            r = rows[i]
            name_cells = [c for j, c in enumerate(r) if j not in {jj for jj, _ in cols} and _is_text(c)]
            if not name_cells:
                continue
            name = str(name_cells[-1]).strip() if len(name_cells) > 1 and all(len(str(c)) < 6 for c in name_cells[:-1]) else str(name_cells[0]).strip()
            n = 0
            for j, (mk, day) in cols:
                v = parse_number(r[j])
                if v is not None:
                    put(name, mk, day, v); n += 1
            if n == 0:
                best.pop(name, None)
        return {name: {mk: v for mk, (day, v) in m.items()} for name, m in best.items() if m}
    if date_cols:
        dj, hits = date_cols[0]
        first_row = hits[0][0]
        header_row = None
        for i in range(first_row - 1, -1, -1):
            if sum(1 for c in rows[i] if _is_text(c)) >= 1:
                header_row = i
                break
        lower = [str(c).strip().lower() if isinstance(c, str) else "" for c in (rows[header_row] if header_row is not None else [""] * width)]
        # Langformat mit Kontospalte?
        acct_col = next((j for j, h in enumerate(lower) if any(k in h for k in ("konto", "account", "bezeichnung"))), None)
        val_col = next((j for j, h in enumerate(lower) if any(k in h for k in ("saldo", "balance", "stand", "wert", "betrag", "value", "amount"))), None)
        if acct_col is None:
            # Spalte mit ueberwiegend Text neben den Stichtagen = Kontoname (Langformat ohne Kopfzeile)
            for j in range(width):
                if j == dj:
                    continue
                texts = sum(1 for i, _ in hits if _is_text(rows[i][j]))
                if texts and texts * 2 >= len(hits):
                    acct_col = j
                    break
            if acct_col is not None and val_col is None:
                nums = [j for j in range(width) if j not in (dj, acct_col) and sum(1 for i, _ in hits if parse_number(rows[i][j]) is not None) >= 1]
                val_col = nums[-1] if nums else None
        if acct_col is not None and val_col is not None and val_col != dj:
            for i, (mk, day) in hits:
                v = parse_number(rows[i][val_col])
                if v is not None:
                    put(str(rows[i][acct_col] or "").strip(), mk, day, v)
            return {name: {mk: v for mk, (day, v) in m.items()} for name, m in best.items() if m}
        numeric_cols = [j for j in range(width) if j != dj and sum(1 for i, _ in hits if parse_number(rows[i][j]) is not None) >= 1]
        if val_col is not None and acct_col is None and val_col in numeric_cols:
            numeric_cols = [val_col]
            header_row = None            # 'Saldo' ist kein Kontoname: eine namenlose Serie
        if header_row is None or all(not _is_text(rows[header_row][j]) for j in numeric_cols):
            # keine Kontonamen: eine Serie (letzte numerische Spalte)
            if numeric_cols:
                j = numeric_cols[-1]
                for i, (mk, day) in hits:
                    v = parse_number(rows[i][j])
                    if v is not None:
                        put("", mk, day, v)
            return {name: {mk: v for mk, (day, v) in m.items()} for name, m in best.items() if m}
        for j in numeric_cols:
            name = str(rows[header_row][j]).strip() if _is_text(rows[header_row][j]) else ""
            if not name:
                continue
            for i, (mk, day) in hits:
                v = parse_number(rows[i][j])
                if v is not None:
                    put(name, mk, day, v)
        return {name: {mk: v for mk, (day, v) in m.items()} for name, m in best.items() if m}
    return {}


def balances_from_file(filename: str, data: bytes) -> Tuple[Dict[str, Dict[str, float]], List[str]]:
    """-> (Kontoname -> Monatswerte, Hinweise). XLSX: das Blatt mit den meisten Werten gewinnt."""
    fn = (filename or "").lower()
    if fn.endswith((".xlsx", ".xlsm")) or data[:2] == b"PK":
        sheets = read_xlsx(data)
        best: Dict[str, Dict[str, float]] = {}
        best_name = ""
        for name, rows in sheets.items():
            try:
                res = balances_from_rows(rows)
            except Exception:
                continue
            if sum(len(v) for v in res.values()) > sum(len(v) for v in best.values()):
                best, best_name = res, name
        return best, (["Blatt '%s' verwendet." % best_name] if best_name else ["Keine Stichtage erkannt."])
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    return balances_from_rows(read_csv_rows(text)), []


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")).strip()


def match_account(name: str, accounts: Dict[str, str]) -> Optional[str]:
    """Kontoname aus der Tabelle -> UUID (exakt, enthalten, Wortueberlappung)."""
    n = _norm(name)
    if not n:
        return None
    by_norm = {_norm(k): v for k, v in accounts.items()}
    if n in by_norm:
        return by_norm[n]
    toks = set(n.split())
    best, score = None, 0.0
    for k, u in by_norm.items():
        if not k:
            continue
        if k in n or n in k:
            s = 0.8 + min(len(k), len(n)) / max(len(k), len(n)) * 0.2
        else:
            kt = set(k.split())
            s = len(toks & kt) / max(1, len(toks | kt))
        if s > score:
            best, score = u, s
    return best if score >= 0.5 else None
