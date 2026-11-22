"""Tables in a PDF or a picture, for the assistant: from the words of every page and where they stand (receipt_text.layout_of --
the PDF's own text or Apple's text recognition, on this Mac) to a workbook like the one table_text builds from Excel. The model
then reads it the same way: a grid with addresses (read_table), in pieces, sums by Kontor.

How (fixed rules, no model):
  - words on the same height are a line; words a normal space apart are one cell (a label and an amount never);
  - what repeats at the top or bottom of the pages goes: page numbers, running heads and feet, the table's own heading on every
    further page (kept once) -- so a table that runs over several pages is one table again;
  - columns are the white rivers that run down the lines with figures (a few lines may cross them); each cell goes to the column
    it lies in. Pages are kept together as long as their columns are lined up on the same edges; where the layout changes, a
    new sheet begins;
  - figures as written become numbers (1.234,56 -> 1234.56; 1.234,56- and (1.234,56) negative; "S"/"H" kept as a mark; per cent;
    dates as YYYY-MM-DD) -- by the notation the document uses (comma or point for decimals), nothing guessed: what is not
    clearly a number stays text.
Pages without a table are their lines, one below the other (column A). Nothing is written anywhere; what comes in is checked
(counts, sizes, kinds) like any other untrusted data."""
from __future__ import annotations

import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple

MAX_PAGES = 300
MAX_ITEMS = 250000
MAX_WORD = 200
MAX_COLS = 60
TOP_LINES, BOTTOM_LINES = 8, 4          # where running heads and feet are looked for
SPACE = 0.45                            # of the line's height: words closer than this are one cell
RIVER = 0.35                            # of the line's height: a river is at least this wide

SIGNS = "-–−+"
_FOREIGN = ("usd", "chf", "gbp", "$", "£", "us$", "sfr", "pln", "czk", "dkk", "sek", "nok", "jpy")       # (euro is the document's own money)
_MONEY = r"€|eur|euro|usd|us\$|chf|sfr|gbp|\$|£|pln|czk|dkk|sek|nok|jpy"
_UNIT = re.compile(r"(?i)^(%s|%%|s|h|-|\+|–|−|stk\.?|st\.?|kg|g|l|m|m²|qm|km|h\.|std\.?|t€|teur|tsd\.?)$" % _MONEY)
_AMOUNT = re.compile(r"^[-+–−(]?\d{1,3}(?:[.,' ]\d{3})*[.,]\d{1,4}[-–−)]?$|^[-+–−(]?\d+[.,]\d{1,4}[-–−)]?$")
_NUMBER = re.compile(r"^[-+–−(]?\d[\d.,' ]*[-–−)]?%?$")
_DATEISH = re.compile(r"^\d{1,2}\.\d{1,2}\.(?:\d{2}|\d{4})?$|^\d{1,2}:\d{2}(?::\d{2})?$|^\d{4}-\d{2}(?:-\d{2})?$")
_DIGITS = re.compile(r"^\d{1,3}$")
_SIGN = re.compile(r"^[-–−+]$")
_GROUP = re.compile(r"^\d{3}(?:[.,]\d+)?[-–−)]?$")
_BARE = re.compile(r"^\W*(\d{1,4})\W*$")
_DATE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_SPACES = dict.fromkeys(map(ord, "\u00a0\u2007\u2009\u202f"), " ")


class Word:
    __slots__ = ("x0", "x1", "yc", "h", "text")

    def __init__(self, x0: float, x1: float, yc: float, h: float, text: str):
        self.x0, self.x1, self.yc, self.h, self.text = x0, x1, yc, h, text


class Cell:
    """Words a space apart, as one: a text or a figure."""
    __slots__ = ("x0", "x1", "words")

    def __init__(self, w: Word):
        self.x0, self.x1, self.words = w.x0, w.x1, [w]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


class Line:
    __slots__ = ("yc", "h", "cells", "page", "figures", "numbers", "plain")

    def __init__(self, yc: float, h: float, cells: List[Cell], page: int):
        self.yc, self.h, self.cells, self.page = yc, h, cells, page
        self.plain = False                               # (True: what it says is text, whatever it looks like)
        self.figures = sum(1 for c in cells if len(c.words) <= 4 and amountlike(c.text))        # amounts (with decimals)
        self.numbers = sum(1 for c in cells if len(c.words) <= 4 and numeric(c.text))           # ... and whole numbers

    @property
    def text(self) -> str:
        return " ".join(c.text for c in self.cells)


def _core(s: str) -> str:
    """A cell without the unit, mark or sign standing beside its figure."""
    parts = s.translate(_SPACES).split()
    while len(parts) > 1 and _UNIT.match(parts[-1]):
        parts.pop()
    while len(parts) > 1 and _UNIT.match(parts[0]):
        parts.pop(0)
    return "".join(parts)


def amountlike(s: str) -> bool:
    """A figure with decimals as documents write it (12,50 / 1.234,56- / (1,234.56)), with or without its unit behind."""
    return bool(_AMOUNT.match(_core(s)))


def numeric(s: str) -> bool:
    """Any figure, whole numbers too (5 / 1.234 / 12,50 / 19 %) -- but no date and no time of day."""
    c = _core(s)
    return bool(_NUMBER.match(c)) and not _DATEISH.match(c)


# -- words, lines, cells -----------------------------------------------------------------------------------------------------
def _words(page: Any) -> List[Word]:
    out = []
    for it in (page.get("items") if isinstance(page, dict) else None) or []:
        if not (isinstance(it, (list, tuple)) and len(it) == 5 and isinstance(it[4], str)):
            continue
        try:
            x, y, w, h = (float(v) / 10.0 for v in it[:4])
        except (TypeError, ValueError):
            continue
        text = it[4].translate(_SPACES).strip()[:MAX_WORD]
        if not text or not all(math.isfinite(v) and abs(v) < 1e5 for v in (x, y, w, h)) or h <= 0 or w < 0:
            continue
        out.append(Word(x, x + w, y + h / 2.0, h, text))
    return out


def _joins(a: Word, b: Word, unit: float) -> bool:
    """Whether two words next to each other are one cell: a normal space apart -- but never a label and its amount, nor two
    amounts (a thousands group written with a space is one: 1 234,56)."""
    if b.x0 - a.x1 > SPACE * unit:
        return False
    fa, fb = bool(_AMOUNT.match(a.text)), bool(_AMOUNT.match(b.text))
    if _SIGN.match(a.text) or _SIGN.match(b.text):       # a sign alone: with the word a space beside it -- never with a unit, a
        return not _UNIT.match(b.text if _SIGN.match(a.text) else a.text)       # mark or a sign (those are settled with the columns)
    if _DIGITS.match(a.text) and _GROUP.match(b.text):
        return b.x0 - a.x1 > -0.15 * unit                # (boxes lying on top of each other are two figures, not 1 234)
    if _UNIT.match(a.text) or _UNIT.match(b.text):
        return True
    return not (fa or fb)


def _lone(c: Cell) -> bool:
    """A sign standing alone."""
    return len(c.words) == 1 and bool(_SIGN.match(c.words[0].text))


def _is_figure(c: Cell) -> bool:
    return len(c.words) <= 4 and numeric(c.text)


def _unit(row: List[Word]) -> float:
    """The size of a line's writing: the height of its words -- at least what their width says (text recognition draws its
    boxes tight around the letters, a PDF around the whole line)."""
    h = sorted(w.h for w in row)[len(row) // 2]
    wide = sorted((w.x1 - w.x0) / len(w.text) for w in row if len(w.text) >= 2)
    return max(h, 1.8 * wide[len(wide) // 2]) if wide else max(w.h for w in row)      # (- 1 -: as high as its figure, not its strokes)


def _prose(row: List[Word], unit: float) -> bool:
    """A line of running text (a sentence of a letter, a note): many words, mostly with letters, a space apart each -- kept
    as it reads, whatever figures it names."""
    if len(row) < 7:
        return False
    end = [w for w in row if not _UNIT.match(w.text)]
    if end and (_AMOUNT.match(end[-1].text) or (len(end) > 1 and numeric(end[-1].text) and end[-1].x0 - end[-2].x1 > SPACE * unit)):
        return False                                     # it ends in an amount, or a number set apart: a line of a table with a long label
    if any(b.x0 - a.x1 > 1.2 * unit for a, b in zip(row, row[1:])):
        return False
    return sum(1 for w in row if re.search(r"[^\W\d_]{2}", w.text)) >= 0.7 * len(row)


def _fuse(cells: List[Cell], unit: float) -> List[Cell]:
    """A mark S or H standing alone close behind a figure belongs to that figure. (A sign standing alone is settled later,
    with the columns: _sign.)"""
    out: List[Cell] = []
    for c in cells:
        if out and len(c.words) == 1 and c.text in ("S", "H") and amountlike(out[-1].text) and not re.search(r" [SH]$", out[-1].text) \
                and c.x0 - out[-1].x1 <= 3.0 * unit:
            out[-1].words += c.words
            out[-1].x1 = max(out[-1].x1, c.x1)
        else:
            out.append(c)
    return out


def _deskew(words: List[Word]) -> List[Word]:
    """A page read from a picture that lies a little askew (a scan, a photo): turned straight, so that what stands on one
    line is found on one height. The angle (up to 3 degrees) is read from words standing right next to each other -- the
    middle value of how much the second stands higher or lower than the first (never from words far apart: in a table the
    next row's figures would line up just as well)."""
    if not 12 <= len(words) <= 20000:
        return words
    h = sorted(w.h for w in words)[len(words) // 2]
    order = sorted(words, key=lambda w: w.x0)
    slopes: List[float] = []
    for i, a in enumerate(order):
        for b in order[i + 1:i + 40]:
            if b.x0 - a.x1 > 1.5 * h:
                break
            dx = (b.x0 + b.x1 - a.x0 - a.x1) / 2.0
            if b.x0 >= a.x1 - 0.2 * h and abs(b.yc - a.yc) <= 0.6 * h and dx > h:
                slopes.append((b.yc - a.yc) / dx)
    if len(slopes) < 8:
        return words
    slopes.sort()
    t = slopes[len(slopes) // 2]
    spread = (slopes[(3 * len(slopes)) // 4] - slopes[len(slopes) // 4]) / 1.35
    if abs(t) < math.tan(math.radians(0.3)) or abs(t) < 3.0 * 1.25 * spread / math.sqrt(len(slopes)):
        return words                                     # straight, or not clearly askew (the places are only that exact)

    def sharp(tan: float) -> int:                        # how well the words fall into lines when the page is turned by this
        bins: Dict[int, int] = {}
        for w in words:
            k = int(round((w.yc - (w.x0 + w.x1) / 2.0 * tan) / (0.25 * h)))
            bins[k] = bins.get(k, 0) + 1
        return sum(v * v for v in bins.values())
    near = [math.tan(math.atan(t) + math.radians(k / 10.0)) for k in range(-4, 5)]          # ... looked at closely around that angle only
    t = max(near, key=sharp)
    if abs(t) > math.tan(math.radians(3.0)) or sharp(t) < sharp(0.0):
        return words
    for w in words:
        xc, yc = (w.x0 + w.x1) / 2.0, w.yc
        w.yc = yc - xc * t
        w.x0, w.x1 = w.x0 + yc * t, w.x1 + yc * t
    return words


def _lines(words: List[Word], page: int) -> List[Line]:
    words = sorted(words, key=lambda w: (w.yc, w.x0))
    # a PDF's own text gives every word the box of its letters: a minus is a thin stroke, a word of small letters lower than
    # one with capitals -- no word counts as flatter than most of what the page's words are high
    least = 0.7 * sorted(w.h for w in words)[len(words) // 2] if words else 0.0
    rows: List[List[Word]] = []
    total = 0.0                                          # of the heights of the line so far (kept, not added up again: a page of
    for w in words:                                      # very many words on one height must not take forever)
        if rows:
            last = rows[-1]
            if abs(w.yc - total / len(last)) <= 0.5 * min(max(w.h, least), max(last[0].h, least)):
                last.append(w)
                total += w.yc
                continue
        rows.append([w])
        total = w.yc
    out = []
    for row in rows:
        row.sort(key=lambda w: w.x0)
        cells = [Cell(row[0])]
        unit = _unit(row)
        whole = _prose(row, unit)
        for prev, w in zip(row, row[1:]):
            c = cells[-1]
            if whole or _joins(prev, w, unit):           # (a sign a space from a figure on both sides: all one cell -- text)
                c.words.append(w)
                c.x1 = max(c.x1, w.x1)
            else:
                cells.append(Cell(w))
        out.append(Line(sum(w.yc for w in row) / len(row), unit, _fuse(_paged(cells, unit), unit), page))
    return out


_PAGE_OPEN = re.compile(r"(?i)\b(seite|blatt|page)\W{0,3}(?:\d{1,4}(?:\s*(?:von|/|of))?)?\W{0,2}$")
_PAGE_SAID = re.compile(r"(?i)\b(seite|blatt|page)\W{0,3}\d{1,4}(?:\s*(?:von|/|of)(?:\s*\d{1,4})?)?\W{0,2}$")


def _paged(cells: List[Cell], unit: float) -> List[Cell]:
    """"Seite 4 von" and its "4" a little apart (a scan's wide blank): one cell -- a page number is never a figure."""
    out = [cells[0]]
    for c in cells[1:]:
        last = out[-1]
        if c.x0 - last.x1 < 2.0 * unit and _PAGE_OPEN.search(last.text) and _PAGE_SAID.search("%s %s" % (last.text, c.text)):
            last.words.extend(c.words)
            last.x1 = max(last.x1, c.x1)
        else:
            out.append(c)
    return out


# -- what repeats on every page ----------------------------------------------------------------------------------------------
_PAGE_WORD = re.compile(r"(?i)\b(seite|blatt|page)\W{0,3}\d{1,4}(?:\s*(?:von|/|of)\s*\d{1,4})?")
_DATE_WORD = re.compile(r"(?i)\b(datum|date|gedruckt|druckdatum|erstellt|gedruckt am|stand)\W{0,3}\d{1,2}[./]\d{1,2}[./]\d{2,4}(?:\W{0,3}\d{1,2}:\d{2}(?::\d{2})?)?")
_CLOCK = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
_DIGIT = re.compile(r"\d")


def _key(line: Line) -> str:
    """What a line says, for finding it again on other pages: the same but for a page number behind "Seite", a date behind
    "Datum", a time of day -- every other figure counts (a head naming another cost centre is another head)."""
    t = re.sub(r"\s+", " ", line.text).strip().lower()
    t = _PAGE_WORD.sub(lambda m: m.group(1).lower() + " #", t)
    t = _DATE_WORD.sub(lambda m: m.group(1).lower() + " #", t)
    return _CLOCK.sub("#:#", t)


def _zone(lines: List[Line], zone: str) -> List[Line]:
    """The lines at the top (bottom) of a page where a running head (foot) can stand: the first (last) few, up to the first
    (after the last) line of the table itself -- one with an amount, or with several cells and a number among them."""
    part = lines[:TOP_LINES] if zone == "top" else lines[::-1][:BOTTOM_LINES]
    for i, ln in enumerate(part):
        if (ln.figures or (len(ln.cells) >= 2 and ln.numbers)) and _DIGIT.search(_key(ln)):
            part = part[:i]                              # (a line whose only numbers are its page, date and time is no table line)
            break
    return part if zone == "top" else part[::-1]


def _drop_repeats(pages: List[List[Line]]) -> List[str]:
    """Running heads and feet and the table's heading on every further page: gone (a head once, a foot never) -- the same
    words at the same place on at least half of the pages. A number standing alone goes only as a page number: counting up
    from page to page. What went is handed back (the model is told)."""
    gone_texts: List[str] = []
    if len(pages) < 2:
        return gone_texts
    need = max(2, int(math.ceil(len(pages) * 0.5)))
    for zone in ("top", "bottom"):
        seen: Dict[str, List[Tuple[int, float]]] = {}
        bare: List[Tuple[float, int, int, int]] = []     # numbers standing alone: (place, page, number, line)
        for i, lines in enumerate(pages):
            for ln in _zone(lines, zone):
                m = _BARE.match(ln.text) if len(ln.cells) == 1 else None
                if m:
                    bare.append((ln.cells[0].x0, i, int(m.group(1)), id(ln)))
                else:
                    seen.setdefault(_key(ln), []).append((i, ln.cells[0].x0))
        often: Dict[str, Tuple[float, int]] = {}         # the same words at the same place on enough pages: where, and the first page
        for k, at in seen.items():
            mid = sorted(x for _, x in at)[len(at) // 2]
            on = sorted({i for i, x in at if abs(x - mid) <= 4.0})
            if len(on) >= need:
                often[k] = (mid, on[0])
        numbers = set()                                  # page numbers: at one place, each as much higher as its page is further on
        bare.sort()
        start = 0
        for j in range(1, len(bare) + 1):
            if j == len(bare) or bare[j][0] - bare[j - 1][0] > 6.0:
                run = bare[start:j]
                steps: Dict[int, List[int]] = {}
                for _, i, n, ident in run:
                    if 0 <= n - i <= 20:                 # (a document's pages start at 1, or a little later -- 2025, 2026 are years)
                        steps.setdefault(n - i, []).append(ident)
                if not steps:
                    start = j
                    continue
                most = max(steps.values(), key=len)
                if len(most) >= need:
                    numbers.update(most)
                start = j
        for i, lines in enumerate(pages):
            gone = set()
            for ln in _zone(lines, zone):
                hit = often.get(_key(ln))
                if id(ln) in numbers or (hit is not None and abs(ln.cells[0].x0 - hit[0]) <= 4.0 and (zone == "bottom" or hit[1] != i)):
                    gone.add(id(ln))
                    gone_texts.append(ln.text)
            if gone:
                pages[i] = [ln for ln in lines if id(ln) not in gone]
    return gone_texts


# -- columns -----------------------------------------------------------------------------------------------------------------
def _table_lines(lines: List[Line]) -> List[Line]:
    """The lines that say where the columns are: several cells, an amount among them -- without amounts anywhere: a number;
    without numbers: several cells."""
    for want in ("figures", "numbers"):
        hit = [ln for ln in lines if len(ln.cells) >= 2 and (ln.figures if want == "figures" else ln.numbers)]
        if len(hit) >= 2:
            return hit
    return [ln for ln in lines if len(ln.cells) >= 2]


def _river_lines(lines: List[Line]) -> List[Line]:
    """The table's lines, and with them the lines that are a label alone standing left of all figures (a heading within
    the table, a label running over two lines): they say where the labels' column ends."""
    table = _table_lines(lines)
    edges = [c.x0 for ln in table for c in ln.cells if len(c.words) <= 4 and numeric(c.text)]
    if not edges:
        return table
    edge, own = min(edges), {id(ln) for ln in table}
    return table + [ln for ln in lines if id(ln) not in own and len(ln.cells) == 1 and ln.cells[0].x1 < edge and not ln.numbers]


def _rivers(lines: List[Line]) -> List[Tuple[float, float]]:
    """The white rivers between the columns: stretches no cell of these lines lies in. A few long texts of many lines may
    cross one (a label running on) -- a figure never: where one stands, there is a column, however rarely it is filled."""
    if len(lines) < 2:
        return []
    tol = max(1, int(len(lines) * 0.03)) if len(lines) >= 4 else 0
    h = sorted(ln.h for ln in lines)[len(lines) // 2]
    events: List[Tuple[float, int, int]] = []
    for ln in lines:
        for c in ln.cells:
            strict = 1 if _lone(c) or (len(c.words) <= 4 and numeric(c.text)) else 0
            events.append((c.x0, 1, strict))
            events.append((max(c.x1, c.x0 + 0.01), -1, strict))
    events.sort()
    left, right = events[0][0], max(e[0] for e in events)
    out: List[Tuple[float, float]] = []
    after_figure: List[bool] = []                        # for each river: whether a figure stands between it and the one before
    texts = figures = 0
    start = None
    seen_figure = False
    for x, d, strict in events:
        was = figures == 0 and texts <= tol
        if strict:
            figures += d
        else:
            texts += d
        free = figures == 0 and texts <= tol
        if free and not was and x < right:               # from here on free: a river may begin
            start = x
        elif was and not free and start is not None:     # ... and ends
            if x - start >= RIVER * h and start > left:
                out.append((start, x))
                after_figure.append(seen_figure)         # (a figure between the river before and this one?)
                seen_figure = False
            start = None
        if figures:
            seen_figure = True
    joined: List[Tuple[float, float]] = []
    for (a, b), fig in zip(out, after_figure):           # two rivers with less between them than a letter is wide, and no figure
        if joined and a - joined[-1][1] < 0.5 * h and not fig:          # there: one river
            joined[-1] = (joined[-1][0], b)
        else:
            joined.append((a, b))
    out = _between_figures(lines, joined, h)
    if len(out) > MAX_COLS - 1:
        out = sorted(sorted(out, key=lambda r: r[0] - r[1])[:MAX_COLS - 1])
    return out


def _between_figures(lines: List[Line], rivers: List[Tuple[float, float]], h: float) -> List[Tuple[float, float]]:
    """Rivers that long texts cross too often to count above, found from the figures: between two columns of figures (the
    labels of the totals under an invoice run over "quantity" and "price"), and at the left edge of a column of figures whose
    labels end right before it -- where no figure stands and texts cross in fewer than four of ten lines."""
    spans = sorted((c.x0, c.x1) for ln in lines for c in ln.cells if len(c.words) <= 4 and numeric(c.text))
    blocks: List[List[float]] = []                       # the columns of figures, from left to right: [left, right, how many figures]
    for x0, x1 in spans:
        if blocks and x0 - blocks[-1][1] < RIVER * h:
            blocks[-1][1] = max(blocks[-1][1], x1)
            blocks[-1][2] += 1
        else:
            blocks.append([x0, x1, 1])
    blocks = blocks[:4 * MAX_COLS]
    out: List[Tuple[float, float]] = []
    for (_, a, _), (b, _, _) in zip(blocks, blocks[1:]):
        if any(min(b, r1) - max(a, r0) > 0 for r0, r1 in rivers):
            continue                                     # (found above already, or a column of text stands in it)
        both = cross = 0
        for ln in lines:
            left = right = False
            for c in ln.cells:
                fig = len(c.words) <= 4 and numeric(c.text)
                if fig and c.x1 <= a + 0.01:
                    left = True
                elif fig and c.x0 >= b - 0.01:
                    right = True
                elif not fig and min(c.x1, b) - max(c.x0, a) > 0.5 * (b - a):
                    cross += 1
            both += left and right
        if both >= 2 and cross < 0.4 * len(lines):
            out.append((a, b))
    for edge, _, members in blocks:                      # ... and where labels end a hair before their figures
        if members < 2 or any(r0 < edge and r1 >= edge - 0.5 * h for r0, r1 in rivers + out):
            continue                                     # (one figure alone is no column; or the river is there)
        before = cross = 0
        reach = None
        for ln in lines:
            for c in ln.cells:
                if _lone(c) or (len(c.words) <= 4 and numeric(c.text)):
                    continue
                if c.x1 <= edge + 0.5:
                    before += 1
                    reach = c.x1 if reach is None else max(reach, c.x1)
                elif c.x0 < edge - 0.5:
                    cross += 1
        if before >= 2 and reach is not None and cross < 0.4 * len(lines):
            a = min(reach, edge - 0.01)
            near = [r for r in rivers + out if min(edge, r[1]) - max(a, r[0]) > 0]          # a river there already, ending too early: it runs on to the figures
            if near:
                r = near[-1]
                (rivers if r in rivers else out).remove(r)
                a = r[0]
            out.append((a, edge))
    return sorted(rivers + out)


def _anchors(lines: List[Line]) -> List[Tuple[str, float]]:
    """Where the columns of these lines are lined up: the left edges many cells share (text) and the right edges (figures)."""
    if len(lines) < 2:
        return []
    unit = sorted(ln.h for ln in lines)[len(lines) // 2]
    need = max(2, int(math.ceil(0.3 * len(lines))))
    found: List[Tuple[int, str, float]] = []
    for side in ("l", "r"):
        xs = sorted((c.x0 if side == "l" else c.x1) for ln in lines for c in ln.cells)
        run = [xs[0]]
        for x in xs[1:] + [float("inf")]:
            if x - run[-1] <= 0.25 * unit:
                run.append(x)
                continue
            if len(run) >= need:
                found.append((len(run), side, sum(run) / len(run)))
            run = [x]
    found.sort(reverse=True)                             # (the edges most cells share, as many as there can be columns)
    return [(side, x) for _, side, x in found[:2 * MAX_COLS]]


def _alike(a: List[Tuple[str, float]], b: List[Tuple[str, float]], unit: float) -> bool:
    """Whether two pages hold the same table: most of the edges their columns are lined up on are the same."""
    if not a or not b:
        return True                                      # (a page without a table goes with what stands before it)
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    same = sum(1 for side, x in small if any(s2 == side and abs(x - x2) <= 0.5 * unit for s2, x2 in large))
    return same >= 0.6 * len(small)


def _slip(a: List[Tuple[str, float]], b: List[Tuple[str, float]], unit: float) -> float:
    """By how much the second page's columns must be moved sideways to stand on the first one's edges (at most 30 points) --
    0 where no move makes them alike."""
    best, move = 0, 0.0
    for side, x in a[:40]:
        for s2, x2 in b[:40]:
            dx = x - x2
            if s2 != side or not 0.5 * unit < abs(dx) <= 30.0:
                continue
            moved = [(s3, x3 + dx) for s3, x3 in b]
            same = sum(1 for s3, x3 in moved if any(s4 == s3 and abs(x3 - x4) <= 0.5 * unit for s4, x4 in a))
            if same > best:
                best, move = same, dx
    return move if best >= 2 and _alike(a, [(s3, x3 + move) for s3, x3 in b], unit) and best >= 0.8 * min(len(a), len(b)) else 0.0


def _column(cell: Cell, bounds: List[float]) -> int:
    """The column a cell lies in (most of it): bounds are the middles of the rivers."""
    best, where = -1.0, 0
    lo = -1e9
    for i, hi in enumerate(bounds + [1e9]):
        over = min(cell.x1, hi) - max(cell.x0, lo)
        if over > best + 1e-6:
            best, where = over, i
        lo = hi
    return where


# -- figures -----------------------------------------------------------------------------------------------------------------
def notation(lines: List[Line]) -> str:
    """Which sign the document uses for decimals: "," (German) unless figures like 1,234.56 clearly lead ("."); "?"
    when nobody can tell thousands from three decimals -- it only has figures like 12,345, or figures like 12.345 beside what
    reads like a decimal point (0.500; a price 4.80 behind its label): those stay text. Dates and times of day (01.10.26,
    14.30) say nothing about it, nor does a number like 4400.10 in front of its line (an account)."""
    de = en = de3 = en3 = point = 0
    for ln in lines:
        label = False                                    # a text stood before: what follows is no account number
        for c in ln.cells:
            for w in c.words:
                t = w.text.strip("()-–−+%")
                if re.fullmatch(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}", t):
                    de += 1
                elif re.fullmatch(r"\d{1,3}(?:,\d{3})+\.\d{2}", t):          # (123.45 alone says nothing: account 4400.10)
                    en += 1
                elif re.fullmatch(r"0\.\d{3}", t):
                    point += 1
                elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", t):
                    de3 += 1
                elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", t):
                    en3 += 1
                elif label and re.fullmatch(r"\d+\.\d{2}", t) and not (int(t[:-3]) <= 31 and int(t[-2:]) <= 59):
                    point += 1                           # (14.30 and 02.10 are a time of day and a date)
            if re.search(r"[^\W\d_]{3}", c.text):
                label = True
    if de or en:
        return "." if en > de else ","
    return "?" if (en3 and not de3) or (de3 and point) else ","


def figure(text: str, de: bool = True, unsure: bool = False) -> Tuple[str, str]:
    """A cell as (kind, value): n a number ('1234.56'), m a number with its mark ('1234.56 S', '100 USD'), p per cent
    ('12.5%'), d a date (YYYY-MM-DD), t text as written. Only what is clearly a figure in the document's notation becomes
    one (unsure: 12,345 could be thousands or decimals -- text)."""
    s = re.sub(r"\s+", " ", text.translate(_SPACES)).strip()
    m = _DATE.match(s)
    if m:
        try:
            return "d", date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            return "t", s
    core, mark, pct = s, "", False
    mm = re.match(r"^(.*\d[-–−)]?)\s?([SH])$", core)
    if mm:
        core, mark = mm.group(1), mm.group(2)
    cur = re.match(r"(?i)^(%s)\s?(?=[-–−+(\d])" % _MONEY, core) or re.search(r"(?i)(?<=[\d)\-–−+])\s?(%s)$" % _MONEY, core)
    if cur:
        core = (core[:cur.start()] + core[cur.end():]).strip()
        if cur.group(1).lower() in _FOREIGN:             # another money than the document's own: never added to the rest
            if mark:
                return "t", s
            mark = cur.group(1).upper()
    if core.endswith("%"):
        core, pct = core[:-1].strip(), True
    neg = False
    if core.startswith("(") and core.endswith(")"):
        core, neg = core[1:-1].strip(), True
    if core[:1] in SIGNS and len(core) > 1:
        neg, core = neg != (core[0] != "+"), core[1:].strip()
    elif core[-1:] in SIGNS and len(core) > 1:
        neg, core = neg != (core[-1] != "+"), core[:-1].strip()
    if de:
        ok = re.fullmatch(r"\d{1,3}(?:[. ']\d{3})+(?:,\d+)?|\d+(?:,\d+)?", core)
        plain = re.sub(r"[. ']", "", core).replace(",", ".")
    else:
        ok = re.fullmatch(r"\d{1,3}(?:[, ']\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", core)
        plain = re.sub(r"[, ']", "", core)
    whole = re.sub(r"\D", "", plain.split(".")[0])
    if not ok or len(whole) > 15 or (len(whole) > 1 and whole[0] == "0" and "." not in plain) \
            or (unsure and re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", core)) or (pct and mark):
        return "t", s                                    # (0800, 007: a code, not a number -- 0.500 is no thousand either)
    try:
        d = Decimal(plain)
    except InvalidOperation:
        return "t", s
    if neg:
        d = -d
    v = format(d, "f")
    if "." in v:
        v = v.rstrip("0").rstrip(".")
    v = "0" if v in ("-0", "") else v
    if pct:
        return "p", v + "%"
    return ("m", "%s %s" % (v, mark)) if mark else ("n", v)


# -- the workbook ------------------------------------------------------------------------------------------------------------
def _value(texts: List[str], de: bool, unsure: bool) -> Tuple[str, str]:
    """What stands in one cell of the grid, from the cells of a line that lie in its column: one -- as written; a figure with
    its unit, mark or sign beside it -- that figure; texts -- side by side; several figures -- never one figure (3 and 250,00
    are not 3250): shown apart, as text."""
    if len(texts) == 1:
        return figure(texts[0], de, unsure)
    figures = [t for t in texts if numeric(t)]
    if len(figures) == 1 and all(_UNIT.match(t) for t in texts if t is not figures[0]):
        return figure(" ".join(texts), de, unsure)
    return "t", (" · " if len(figures) >= 2 else " ").join(texts)


def _signed(text: str) -> bool:
    c = _core(text)
    return c[:1] in SIGNS + "(" or c[-1:] in SIGNS + ")"


def _running(lines: List[Line], where: List[List[int]], items: List[Tuple[int, int, Any, Any]], de: bool, unsure: bool) -> bool:
    """Signs between amounts and a balance: do the balances run on by the amounts, taken with these signs (5.000,00 and then
    260,00 + : 5.260,00)? Then they are the amounts' signs -- the table proves it."""
    kl, kr = items[0][2], items[0][3]
    sign = {r: -1 if lines[r].cells[i].text != "+" else 1 for r, i, _, _ in items}
    rows = []
    for r, ln in enumerate(lines):
        got: Dict[int, Decimal] = {}
        for k, c in zip(where[r], ln.cells):
            if k in (kl, kr) and _is_figure(c) and not _signed(c.text):
                kind, v = figure(c.text, de, unsure)
                if kind == "n":
                    got[k] = Decimal(v)
        if kl in got and kr in got:
            rows.append((got[kl] * sign.get(r, 1), got[kr]))
    steps = [b - before == a for (_, before), (a, b) in zip(rows, rows[1:])]
    return sum(steps) >= 3 and sum(steps) >= 0.5 * len(steps)       # (to the cent, three times and more: no chance)


def _signs(lines: List[Line], bounds: List[float], spans: Dict[int, Tuple[float, float]], de: bool = True,
           unsure: bool = False) -> Tuple[Dict[Tuple[int, int], List[Tuple[int, str]]], int]:
    """Where each sign standing alone belongs -- {(row, cell): [(column, text) ...]} -- and how many were read as the sign of
    the figure after them without the document proving it. In the column of a figure of its line: that figure's sign. In a
    column of figures, its line without one: a dash for "nothing". In a column of signs only, the table says whose they are:
    lines with a figure on one side only (accounting formats print the minus at the left edge of the cell: label, minus,
    figure; a column of signs behind the amounts: amount, minus, nothing) -- or signs written onto figures elsewhere
    (1.234,56-), or standing right behind the figure before them, or balances that run on by the amounts with these signs. A column of dashes with a heading of its own, beside the next column's: a column without values. Nothing
    says it: before the figure after it (the usual way such a sign gets there), counted -- with a plus among them, or the
    table saying both: shown as (-) on both figures, which makes neither a number."""
    out: Dict[Tuple[int, int], List[Tuple[int, str]]] = {}
    waiting: Dict[int, List[Tuple[int, int, Any, Any]]] = {}
    close: Dict[int, List[bool]] = {}                    # of a column's signs between two figures: close behind the first?
    lead = trail = 0
    where = [[_column(c, bounds) for c in ln.cells] for ln in lines]
    for r, ln in enumerate(lines):
        for i, c in enumerate(ln.cells):
            if not _lone(c):
                if _is_figure(c):
                    core = _core(c.text)
                    lead += core[:1] in "-–−"
                    trail += core[-1:] in "-–−"
                continue
            own = where[r][i]
            kl = where[r][i - 1] if i and _is_figure(ln.cells[i - 1]) and not _signed(ln.cells[i - 1].text) else None
            kr = where[r][i + 1] if i + 1 < len(ln.cells) and _is_figure(ln.cells[i + 1]) and not _signed(ln.cells[i + 1].text) else None
            if kl is not None and kl != own and any(j in spans for j in range(kl + 1, own)):
                kl = None                                # (a column of figures lies between: not that figure's sign)
            if kr is not None and kr != own and any(j in spans for j in range(own + 1, kr)):
                kr = None
            if own in (kl, kr) or own in spans:
                out[(r, i)] = [(own, c.text)]
            else:
                waiting.setdefault(own, []).append((r, i, kl, kr))
                if kl is not None and kr is not None:
                    gl, gr = c.x0 - ln.cells[i - 1].x1, ln.cells[i + 1].x0 - c.x1
                    close.setdefault(own, []).append(gl <= 0.6 * ln.h and gr >= 3.0 * gl)
    way: Dict[int, str] = {}
    full: Dict[int, bool] = {}
    for own, items in waiting.items():
        rows = {r for r, _, _, _ in items}
        only_l = sum(1 for _, _, kl, kr in items if kl is not None and kr is None)
        only_r = sum(1 for _, _, kl, kr in items if kr is not None and kl is None)
        both = sum(1 for _, _, kl, kr in items if kl is not None and kr is not None)
        side = own + 1 if only_r or both else own - 1    # the column these dashes could stand for "nothing" beside
        beside = [r for r, ln in enumerate(lines) if any(k == side and _is_figure(c) for k, c in zip(where[r], ln.cells))]
        full[own] = len(beside) >= 3 and all(r in rows for r in beside)
        headed = any(r not in rows and own in ks and side in ks for r, ks in enumerate(where))
        plus = any(lines[r].cells[i].text == "+" for r, i, _, _ in items)
        if headed and not plus and len(rows) >= 0.9 * max(1, len(beside)):
            way[own] = "own"
        elif only_l and not only_r:
            way[own] = "left"
        elif only_r and not only_l:
            way[own] = "right"
        elif only_l and only_r:
            way[own] = "line"
        elif both and all(close[own]):                   # 250,00 -   5.000,00: no accounting format sets its minus that close
            way[own] = "left"                            # behind the figure before (the cells' own margins lie between)
        else:
            way[own] = "?" if both else "own"
    said = {w for w in way.values() if w in ("left", "right")}
    if bool(lead) != bool(trail):
        said.add("right" if lead else "left")
    apart = 0
    for own, items in waiting.items():
        w = way[own]
        guessed = False
        if w == "?":
            plus = any(lines[r].cells[i].text == "+" for r, i, _, _ in items)
            if _running(lines, where, items, de, unsure):
                w = "left"
            else:
                w = next(iter(said)) if len(said) == 1 else "line" if said or plus else "right"
            guessed = w == "right" and not said
        elif w == "right" and full[own]:
            guessed = True                               # (every line has it: all negative -- or a column of dashes without a heading)
        for r, i, kl, kr in items:
            t = lines[r].cells[i].text
            if w == "left" and kl is not None:
                out[(r, i)] = [(kl, t)]
            elif w == "right" and kr is not None:
                out[(r, i)] = [(kr, t)]
                apart += guessed
            elif w == "line" and (kl is None) != (kr is None):
                out[(r, i)] = [(kl if kl is not None else kr, t)]
            elif w == "line" and kl is not None:
                out[(r, i)] = [(kl, "(%s)" % t), (kr, "(%s)" % t)]
            else:                                        # a dash for "nothing": in the column of figures beside it that this
                k = own                                  # line leaves empty (set in the middle of the cell), else in its own
                for j in (own + 1, own - 1):
                    if j in spans and j not in where[r]:
                        k = j
                        break
                out[(r, i)] = [(k, t)]
    return out, apart


_MARK = re.compile(r"^(?:S|H|(?i:%s))$" % _MONEY)


def _sheet(lines: List[Line], rivers: List[Tuple[float, float]], de: bool, unsure: bool, first: int, last: int) -> dict:
    bounds = [(a + b) / 2.0 for a, b in rivers]
    cells: Dict[Tuple[int, int], Tuple[str, str, str]] = {}
    row_pages: List[Tuple[int, int]] = []
    spans: Dict[int, Tuple[float, float]] = {}           # where the figures of each column stand
    edges: Dict[Tuple[int, int], Tuple[float, float, float]] = {}       # left and right end of what a cell holds, and its line's height
    for ln in lines:
        for c in ln.cells:
            if bounds and len(c.words) <= 4 and numeric(c.text):
                k = _column(c, bounds)
                spans[k] = (min(spans[k][0], c.x0), max(spans[k][1], c.x1)) if k in spans else (c.x0, c.x1)
    signs, apart = _signs(lines, bounds, spans, de, unsure) if bounds else ({}, 0)
    amounts = set()                                      # cells that hold one amount (with decimals) as written
    for r, ln in enumerate(lines):
        if not row_pages or row_pages[-1][1] != ln.page:
            row_pages.append((r, ln.page))
        placed: Dict[int, List[str]] = {}
        for i, c in enumerate(ln.cells):
            for k, text in signs.get((r, i)) or [((_column(c, bounds) if bounds else 0), c.text)]:
                placed.setdefault(k, []).append(text)
                x0, x1, _ = edges.get((r, k), (c.x0, c.x1, ln.h))
                edges[(r, k)] = (min(x0, c.x0), max(x1, c.x1), ln.h)
        for k, texts in placed.items():
            if ln.plain or (not bounds and len(texts) > 1):         # a page without a table: its line as it reads, never a figure made of parts
                cells[(r, k)] = ("t", "  ".join(texts), "")
            else:
                cells[(r, k)] = _value(texts, de, unsure) + ("",)
                if sum(1 for t in texts if amountlike(t)) == 1:
                    amounts.add((r, k))
    cols = max((c for _, c in cells), default=-1) + 1
    for k in range(1, cols):                             # a column of marks (S and H, another money) close behind amounts: their
        col = [(r, v) for (r, c), v in cells.items() if c == k]                 # marks -- not before the figures after it (USD 172,50),
        marks = [(r, v) for r, v in col if v[0] == "t" and _MARK.match(v[1])]   # nor behind an account or a count (8400 S, 100 USD)
        if len(marks) >= 2 and len(marks) >= 0.6 * len(col):
            behind = []
            for r, v in marks:
                left = cells.get((r, k - 1))
                if left is not None and left[0] == "n" and (r, k - 1) in amounts:
                    gap = edges[(r, k)][0] - edges[(r, k - 1)][1]
                    after = cells.get((r, k + 1))
                    if gap <= 8.0 * edges[(r, k)][2] and (after is None or after[0] not in "nmp" or edges[(r, k + 1)][0] - edges[(r, k)][1] > gap):
                        behind.append((r, v, left))
            if len(behind) < 0.8 * len(marks):
                continue
            for r, v, left in behind:
                if v[1] in ("S", "H") or v[1].lower() in _FOREIGN:
                    cells[(r, k - 1)] = ("m", "%s %s" % (left[1], v[1].upper()), "")
                del cells[(r, k)]                        # (the document's own money: said once is enough)
    for k in range(cols - 1, 0, -1):                     # one text alone in its column, a space behind the text before it: its end
        col = [r for (r, c) in cells if c == k]
        if len(col) == 1 and cells[(col[0], k)][0] == "t" and cells.get((col[0], k - 1), ("",))[0] == "t":
            r = col[0]
            if edges[(r, k)][0] - edges[(r, k - 1)][1] < edges[(r, k)][2]:
                cells[(r, k - 1)] = ("t", "%s %s" % (cells[(r, k - 1)][1], cells[(r, k)][1]), "")
                del cells[(r, k)]
    used = sorted({c for _, c in cells})                 # a column nothing landed in (two texts met in a river): closed up
    if used != list(range(len(used))):
        at = {c: i for i, c in enumerate(used)}
        cells = {(r, at[c]): v for (r, c), v in cells.items()}
    name = "page %d" % first if first == last else "pages %d-%d" % (first, last)
    return {"name": name, "hidden": False, "cells": cells, "rows": len(lines), "cols": max((c for _, c in cells), default=-1) + 1,
            "merged": [], "hidden_rows": set(), "hidden_cols": [], "no_value": 0, "row_pages": row_pages, "signs_apart": apart}


def book(layout: Any) -> dict:
    """The workbook of a document's layout ({"pages": [{"n", "w", "h", "how", "items": [[x, y, w, h, text] in tenths of a
    point, y from the top]}], "count", "cut"}): one sheet per run of pages whose columns hold."""
    raw = layout.get("pages") if isinstance(layout, dict) else None
    if not isinstance(raw, list):
        raise ValueError("no pages")
    pages: List[List[Line]] = []
    numbers: List[int] = []
    how: Dict[str, int] = {}
    total = 0
    short = len(raw) > MAX_PAGES
    for i, p in enumerate(raw[:MAX_PAGES]):
        words = _words(p)
        total += len(words)
        if total > MAX_ITEMS:
            short = True
            break
        n = p.get("n") if isinstance(p, dict) and isinstance(p.get("n"), int) and 0 < p["n"] < 100000 else i + 1
        kind = p.get("how") if isinstance(p, dict) and p.get("how") in ("pdf", "ocr", "none") else "none"
        if kind != "none" and not words:
            kind = "none"                                # (nothing found on it: not read)
        how[kind] = how.get(kind, 0) + 1
        pages.append(_lines(_deskew(words) if kind == "ocr" else words, n))
        numbers.append(n)
    dropped = _drop_repeats(pages)
    for lines in pages:                                  # a small number alone at the very top or bottom of a page is its number,
        for ln in ((lines[0], lines[-1]) if len(lines) >= 2 else ()):       # also where nothing proves it (one page): never a figure
            if len(ln.cells) == 1 and _BARE.match(ln.text):
                ln.plain = True
    sign = notation([ln for lines in pages for ln in lines])
    de, unsure = sign != ".", sign == "?"
    sheets: List[dict] = []
    group: List[Line] = []
    anchors: List[Tuple[str, float]] = []
    span: List[int] = []

    def close() -> None:
        if group:
            sheets.append(_sheet(group, _rivers(_river_lines(group)), de, unsure, span[0], span[-1]))
    for lines, n in zip(pages, numbers):
        if not lines:
            continue
        table = _table_lines(lines)
        own = _anchors(table)
        unit = sorted(ln.h for ln in lines)[len(lines) // 2]
        if group and own and anchors and not _alike(anchors, own, unit):
            dx = _slip(anchors, own, unit)               # the same table, the page a little to the side (a scan, a left-hand page)?
            if dx:
                for ln in lines:
                    for c in ln.cells:
                        c.x0, c.x1 = c.x0 + dx, c.x1 + dx
                own = [(side, x + dx) for side, x in own]
        if group and _alike(anchors, own, unit):
            group = group + lines
            anchors = anchors + [x for x in own if not any(s2 == x[0] and abs(x[1] - x2) <= 0.5 * unit for s2, x2 in anchors)]
            span.append(n)
        else:
            close()
            group, anchors, span = list(lines), own, [n]
    close()
    count = layout.get("count") if isinstance(layout.get("count"), int) and 0 <= layout["count"] < 1000000 else len(pages)
    kinds: Dict[str, int] = {}
    for t in dropped:
        kinds[t] = kinds.get(t, 0) + 1
    return {"sheets": sheets, "date1904": False, "source": "pages", "pages": count, "pages_read": len(pages) - how.get("none", 0), "decimal": sign,
            "signs_apart": sum(sh.pop("signs_apart", 0) for sh in sheets),
            "left_out": {"lines": len(dropped), "examples": [t[:60] for t, _ in sorted(kinds.items(), key=lambda kv: -kv[1])[:3]]},
            "cut": bool(layout.get("cut")) or short or count > len(pages), "how": how}
