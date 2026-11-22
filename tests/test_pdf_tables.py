"""Tables in PDFs and pictures for the assistant (pdf_tables.py): from the words of the pages and where they stand to a grid --
statements over several pages as one table (running heads, page numbers and repeated headings gone), columns from the white
between them, figures as written, exact sums with marks; and what comes from the helper checked like any untrusted data.
Made-up documents: each is written here both as a PDF and as the words a reader finds in it, so the rules run everywhere --
and on a Mac (class OnMac, run by GitHub's macOS job) the real helper reads the same PDFs: PDFKit's text and Apple's text
recognition, in its sandbox."""
import os
import random
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pdf_tables as P          # noqa: E402
import receipt_text as R        # noqa: E402
import table_text as X          # noqa: E402

# Helvetica's widths (per 1000 of the size): what a right-aligned figure needs
WIDTHS = {" ": 278, ".": 278, ",": 278, "-": 333, "%": 889, "/": 278, ":": 278, "(": 333, ")": 333, "+": 584, "I": 278, "J": 500, "L": 556,
          "M": 833, "W": 944, "f": 278, "i": 222, "j": 222, "l": 222, "m": 833, "r": 333, "t": 278, "w": 722, "ß": 611}
WIDTHS.update({c: 556 for c in "0123456789abdeghnopquäöü"})
WIDTHS.update({c: 500 for c in "cksvxyz"})
WIDTHS.update({c: 667 for c in "ABEKPSVXYÄ"})
WIDTHS.update({c: 722 for c in "CDHNRUÜ"})
WIDTHS.update({c: 611 for c in "FTZ"})
WIDTHS.update({c: 778 for c in "GOQÖ"})


def width(text: str, size: float) -> float:
    return sum(WIDTHS.get(c, 556) for c in text) * size / 1000.0


# how far Helvetica's letters reach above and below their line (of the size): PDFKit gives each letter the box of its own
# shape -- a word of small letters is lower than one with capitals, a minus is a thin stroke in mid-air
REACH = {c: (0.52, 0.0) for c in "acemnorsuvwxz"}
REACH.update({c: (0.52, -0.21) for c in "gpqy"})
REACH.update({",": (0.11, -0.15), ".": (0.11, 0.0), ":": (0.52, 0.0), ";": (0.52, -0.15), "-": (0.32, 0.23), "–": (0.29, 0.24), "−": (0.30, 0.22),
              "+": (0.50, 0.0), "(": (0.74, -0.21), ")": (0.74, -0.21), "j": (0.72, -0.21), "*": (0.72, 0.44), "=": (0.39, 0.12), "·": (0.30, 0.20),
              "Ä": (0.90, 0.0), "Ö": (0.90, 0.0), "Ü": (0.90, 0.0), "$": (0.77, -0.13), "_": (-0.08, -0.13), "'": (0.72, 0.46)})


def reach(word: str):
    tops, bottoms = zip(*(REACH.get(c, (0.72, 0.0)) for c in word))
    return max(tops), min(bottoms)


def de(x: float, mark: str = "", trail: bool = False) -> str:
    """12345.6 -> '12.345,60' (negative: with the sign in front or, as accounting prints it, behind)."""
    s = "%.2f" % abs(x)
    a, b = s.split(".")
    a = ".".join([a[max(0, i - 3):i] for i in range(len(a), 0, -3)][::-1])
    s = a + "," + b
    if x < 0:
        s = s + "-" if trail else "-" + s
    return s + (" " + mark if mark else "")


class Doc:
    """A document of pages (width, height in points); text is put with its left ("l") or right ("r") edge at x, its line at y
    from the top."""

    tight = False                # the boxes as PDFKit gives them (each word as high as its letters), not as high as the writing

    def __init__(self, w: float = 595, h: float = 842):
        self.w, self.h, self.pages = w, h, [[]]

    def page(self) -> None:
        self.pages.append([])

    def put(self, x: float, y: float, text: str, align: str = "l", size: float = 9) -> None:
        if text:
            self.pages[-1].append((x - width(text, size) if align == "r" else x, y, text, size))

    def layout(self, jitter: int = 0, how: str = "pdf") -> dict:
        """The words a reader finds: each with its place (tenths of a point, y from the top) -- jitter: as text recognition
        would place them, a little off."""
        rnd = random.Random(4)
        pages = []
        for n, items in enumerate(self.pages):
            out = []
            for x, y, text, size in items:
                for word in text.split(" "):
                    if word:
                        j = [rnd.randint(-jitter, jitter) for _ in range(3)] if jitter else [0, 0, 0]
                        top, bottom = reach(word) if Doc.tight else (0.8, -0.2)
                        out.append([round(x * 10) + j[0], round((y - top * size) * 10) + j[1], round(width(word, size) * 10), round((top - bottom) * size * 10) + j[2], word])
                    x += width(word + " ", size)
            pages.append({"n": n + 1, "w": round(self.w * 10), "h": round(self.h * 10), "how": how, "items": out})
        return {"pages": pages, "count": len(pages), "cut": False}

    def pdf(self) -> bytes:
        """The same as a PDF (Helvetica, one content stream per page)."""
        objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"", b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>"]
        kids = []
        for items in self.pages:
            body = b"".join(b"BT /F1 %s Tf %.2f %.2f Td (%s) Tj ET\n" % (
                ("%g" % size).encode(), x, self.h - y, text.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)"))
                for x, y, text, size in items)
            objs.append(b"<</Length %d>>stream\n" % len(body) + body + b"endstream")
            objs.append(b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 %d %d]/Contents %d 0 R/Resources<</Font<</F1 3 0 R>>>>>>" % (self.w, self.h, len(objs)))
            kids.append(len(objs))
        objs[1] = b"<</Type/Pages/Kids[%s]/Count %d>>" % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))
        out, offs = b"%PDF-1.4\n", []
        for i, o in enumerate(objs, 1):
            offs.append(len(out))
            out += b"%d 0 obj" % i + o + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % x for x in offs)
        return out + b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


NAMES = ["Kasse", "Bank 1", "Bank 2 Sparkasse", "Forderungen aus Lieferungen und Leistungen", "Vorsteuer 19 %", "Umsatzsteuer 19 %",
         "Wareneingang 7 % Vorsteuer", "Löhne und Gehälter", "Gesetzliche soziale Aufwendungen", "Miete (unbewegliche Wirtschaftsgüter)",
         "Erlöse 7 % USt", "Erlöse 19 % USt", "Verbindlichkeiten aus Lieferungen"]


def statement(pages: int = 4, per_page: int = 38):
    """A list of totals and balances as accounting software prints it: a head and a foot with the page number on every page,
    the table's heading again on each, a carry-over line, marks S/H behind the figures, empty cells, a total at the end."""
    rnd = random.Random(1)
    d, rows, konto = Doc(), [], 1000
    for _ in range(pages * per_page):
        konto += rnd.randint(1, 40)
        eb = rnd.choice([0, 0, round(rnd.uniform(10, 900000), 2)])
        soll, haben = round(rnd.uniform(0, 500000), 2), rnd.choice([0, round(rnd.uniform(0, 500000), 2)])
        rows.append((str(konto), rnd.choice(NAMES), eb, rnd.choice("SH"), soll, haben, round(abs(eb + soll - haben), 2), rnd.choice("SH")))
    k = 0
    for p in range(pages):
        if p:
            d.page()
        d.put(40, 40, "Summen- und Saldenliste", size=11); d.put(555, 40, "Datum: 21.11.2026", "r", 8); d.put(40, 52, "Beispiel Handels GmbH", size=8)
        d.put(555, 52, "Seite: %d" % (p + 1), "r", 8); d.put(40, 64, "Zeitraum 01.01.2026 - 31.10.2026", size=8)
        y = 85
        d.put(40, y, "Konto", size=8); d.put(95, y, "Bezeichnung", size=8)
        for x, t in zip((330, 400, 470, 555), ("EB-Wert", "Soll", "Haben", "Saldo")):
            d.put(x, y, t, "r", 8)
        y += 14
        if p:
            d.put(95, y, "Übertrag", size=8); d.put(400, y, de(sum(r[4] for r in rows[:k])), "r", 8); d.put(470, y, de(sum(r[5] for r in rows[:k])), "r", 8)
            y += 11
        for _ in range(per_page):
            r = rows[k]
            k += 1
            d.put(40, y, r[0], size=8); d.put(95, y, r[1], size=8)
            if r[2]:
                d.put(330, y, de(r[2], r[3]), "r", 8)
            d.put(400, y, de(r[4]), "r", 8)
            if r[5]:
                d.put(470, y, de(r[5]), "r", 8)
            d.put(555, y, de(r[6], r[7]), "r", 8)
            y += 11
        if p == pages - 1:
            d.put(95, y + 4, "Summe", size=8); d.put(400, y + 4, de(sum(r[4] for r in rows)), "r", 8); d.put(470, y + 4, de(sum(r[5] for r in rows)), "r", 8)
        d.put(200, 817, "Erstellt mit Beispielsoftware - Seite %d von %d" % (p + 1, pages), size=7)
    return d, rows


def as_cells(r) -> list:
    """A row of the statement as the grid must show it."""
    n = lambda v: X.plain(X.number("%.2f" % v))
    return [r[0], r[1], ("%s %s" % (n(r[2]), r[3])) if r[2] else "", n(r[4]), n(r[5]) if r[5] else "", "%s %s" % (n(r[6]), r[7])]


def report():
    """A monthly report on two pages: the heading in two lines, negative figures with the sign behind, headings without
    figures, empty cells, six columns of figures."""
    rnd = random.Random(2)
    d, rows = Doc(842, 595), []
    xs = (470, 520, 570, 640, 700, 760)
    names = ["Umsatzerlöse", "Bestandsveränderung", "Gesamtleistung", "Wareneinkauf", "Rohertrag", "Kostenarten:", "Personalkosten", "Raumkosten",
             "Betriebliche Steuern", "Versicherungen und Beiträge", "Fahrzeugkosten (ohne Steuer)", "Werbe- und Reisekosten", "Abschreibungen",
             "Reparatur und Instandhaltung", "Sonstige Kosten", "Gesamtkosten", "Betriebsergebnis", "Zinsaufwand", "Neutraler Aufwand", "Vorläufiges Ergebnis"]
    for p, part in enumerate((names[:11], names[11:])):
        if p:
            d.page()
        d.put(40, 40, "Kurzfristige Erfolgsrechnung Oktober 2026", size=12); d.put(800, 40, "Blatt %d" % (p + 1), "r", 8)
        d.put(40, 54, "Beispiel Handels GmbH, Musterstadt", size=8); d.put(800, 54, "Datum 21.11.2026", "r", 8)
        d.put(40, 80, "Bezeichnung", size=8)
        for x, a, b in zip(xs, ("Okt/2026", "% Ges.-", "% Ges.-", "Jan/2026 -", "% Ges.-", "% Ges.-"), ("", "Leistg.", "Kosten", "Okt/2026", "Leistg.", "Kosten")):
            d.put(x, 80, a, "r", 8); d.put(x, 90, b, "r", 8)
        y = 106
        for name in part:
            d.put(40, y, name, size=8)
            vals = []
            if name not in ("Kostenarten:", "Bestandsveränderung"):
                a = round(rnd.uniform(-90000, 900000), 2)
                vals = [a, round(rnd.uniform(0, 100), 2), round(rnd.uniform(0, 100), 2) if rnd.random() < 0.6 else None,
                        round(a * 9.5, 2), round(rnd.uniform(0, 100), 2), round(rnd.uniform(0, 100), 2) if rnd.random() < 0.6 else None]
                for x, v in zip(xs, vals):
                    if v is not None:
                        d.put(x, y, de(v, trail=True), "r", 8)
            rows.append([name] + [X.plain(X.number("%.2f" % v)) if v is not None else "" for v in vals] + [""] * (6 - len(vals)))
            y += 12
    return d, rows


def grid(sh: dict) -> list:
    return [[sh["cells"].get((r, c), ("", "", ""))[1] for c in range(sh["cols"])] for r in range(sh["rows"])]


ACCOUNTING = [("Erlöse", 28028.0, 24028.0), ("Erstattung", 1002.0, -502.0), ("Rücklage", 21006.0, -20506.0), ("Miete", 3000.0, 2900.0), ("Zinsen", 410.0, -12.5)]


def accounting_doc(rows, size=11, euro=False) -> Doc:
    """Excel's accounting format: the minus at the left edge of the cell, the figure at its right."""
    d = Doc()
    d.put(40, 60, "Position", size=size); d.put(300, 60, "Plan", "r", size); d.put(420, 60, "Ist", "r", size)
    for i, (name, plan, ist) in enumerate(rows):
        y = 76 + (size + 3) * i
        d.put(40, y, name, size=size)
        for right, left, v in ((300, 203, plan), (420, 308, ist)):
            d.put(right, y, de(abs(v)) + (" €" if euro else ""), "r", size)
            if v < 0:
                d.put(left, y, "-", size=size)
    return d


class Tables(unittest.TestCase):
    def test_statement_over_pages_is_one_table(self):
        d, rows = statement()
        b = P.book(d.layout())
        self.assertEqual((X.overview(b), b["pages"], b["how"]), ('"pages 1-4" A1:F160', 4, {"pdf": 4}))
        sh = b["sheets"][0]
        g = grid(sh)
        self.assertEqual(g[3], ["Konto", "Bezeichnung", "EB-Wert", "Soll", "Haben", "Saldo"])
        self.assertEqual(sum(1 for r in g if r[0] == "Konto"), 1)                     # the heading once, not on every page
        self.assertEqual(sum(1 for r in g if "Summen- und Saldenliste" in r), 1)      # the running head once
        self.assertFalse([r for r in g if any("Seite" in c and "von" in c for c in r)])          # no foot, no page numbers
        self.assertEqual([r[5] for r in g[:2]], ["Datum: 21.11.2026", "Seite: 1"])
        data = [r for r in g if r[0].isdigit()]
        self.assertEqual(data, [as_cells(r) for r in rows])                           # every row, every cell in its column
        self.assertEqual([r[1] for r in g if r[1] in ("Übertrag", "Summe")], ["Übertrag"] * 3 + ["Summe"])
        self.assertEqual(sh["row_pages"], [(0, 1), (42, 2), (81, 3), (120, 4)])
        # for the model: a piece with its pages, the sums by Kontor -- marked figures per mark
        r = X.render(b, rng="A40:F47")
        self.assertEqual(r["pages"], "rows 40-42: page 1; rows 43-47: page 2")
        self.assertIn("| 43 |  | Übertrag |", r["table"])
        s = X.sum_range(b, None, "F5:F42")
        want = {m: X.plain(sum((X.number("%.2f" % x[6]) for x in rows[:38] if x[7] == m), X.number("0"))) for m in "SH"}
        self.assertEqual(("sum" in s, {k: v["sum"] for k, v in s["with_mark"].items()}), (False, want))          # S and H: never one sum
        total = X.sum_range(b, None, "D5:D159")
        self.assertEqual(total["sum"], X.plain(sum((X.number("%.2f" % x[4]) for x in rows), X.number("0")) + sum(
            (X.number(g[i][3]) for i in range(len(g)) if g[i][1] == "Übertrag"), X.number("0"))))

    def test_report_with_two_line_heading_and_signs_behind(self):
        d, rows = report()
        b = P.book(d.layout())
        g = grid(b["sheets"][0])
        self.assertEqual(X.overview(b), '"pages 1-2" A1:G24')
        self.assertEqual(g[:4], [["Kurzfristige Erfolgsrechnung Oktober 2026", "", "", "", "", "", "Blatt 1"],
                                 ["Beispiel Handels GmbH, Musterstadt", "", "", "", "", "", "Datum 21.11.2026"],
                                 ["Bezeichnung", "Okt/2026", "% Ges.-", "% Ges.-", "Jan/2026 -", "% Ges.-", "% Ges.-"],
                                 ["", "", "Leistg.", "Kosten", "Okt/2026", "Leistg.", "Kosten"]])
        self.assertEqual(g[4:], rows)
        self.assertTrue(any(r[1].startswith("-") for r in rows))                      # "12.345,67-" became -12345.67

    def test_text_recognition_places_words_a_little_off(self):
        d, rows = statement(pages=3)
        b = P.book(d.layout(jitter=8, how="ocr"))
        self.assertEqual((len(b["sheets"]), b["how"]), (1, {"ocr": 3}))
        self.assertEqual([r for r in grid(b["sheets"][0]) if r[0].isdigit()], [as_cells(r) for r in rows])

    def test_letter_then_list_and_other_layouts(self):
        d = Doc()
        for i, ln in enumerate(["Beispiel Steuerberatung, Musterweg 1, 80000 Musterstadt", "Sehr geehrte Damen und Herren,",
                                "anbei der Wertenachweis zum 31.10.2026. Die Summe beträgt 123.456,78 EUR und ist um 2,5 % gestiegen."]):
            d.put(60, 80 + 14 * i, ln, size=10)
        rnd, want = random.Random(3), []
        for p in range(2):
            d.page()
            d.put(50, 50, "Wertenachweis Vorräte zum 31.10.2026", size=10)
            for x, t, a in ((50, "Nr.", "l"), (110, "Artikel", "l"), (380, "Menge", "r"), (460, "Preis", "r"), (545, "Wert", "r")):
                d.put(x, 80, t, a)
            for i in range(40):
                nr, name, m, ek = "%05d" % rnd.randint(1, 99999), rnd.choice(["Haferdrink 1 l", "Dinkelmehl Type 630 1 kg", "Tofu natur 2 x 200 g"]), rnd.randint(1, 400), round(rnd.uniform(0.5, 30), 2)
                want.append([nr if nr[0] == "0" else str(int(nr)), name, str(m), X.plain(X.number("%.2f" % ek)), X.plain(X.number("%.2f" % (m * ek)))])
                for x, t, a in ((50, nr, "l"), (110, name, "l"), (380, str(m), "r"), (460, de(ek), "r"), (545, de(m * ek), "r")):
                    d.put(x, 94 + 14 * i, t, a)
            d.put(290, 810, "- %d -" % (p + 2))
        b = P.book(d.layout())
        g = grid(b["sheets"][0])
        self.assertEqual(X.overview(b), '"pages 1-3" A1:E85')
        self.assertIn("anbei der Wertenachweis zum 31.10.2026. Die Summe beträgt 123.456,78 EUR und ist um 2,5 % gestiegen.", g[2])     # a sentence: as it reads
        self.assertEqual([r for r in g if r[2].isdigit()], want)
        self.assertEqual(sum(1 for r in g if r[1] == "Artikel"), 1)
        self.assertFalse([r for r in g if any(c.startswith("- ") for c in r)])        # "- 2 -": a page number
        # another table on the next page (other columns): a sheet of its own; points as decimal sign where the document writes so
        e = Doc()
        for i in range(12):
            e.put(40, 60 + 12 * i, "Item %d" % i); e.put(300, 60 + 12 * i, "{:,.2f}".format(1234.5 * (i + 1)), "r"); e.put(400, 60 + 12 * i, "({:,.2f})".format(99.25 * (i + 1)), "r")
        e.page()
        for i in range(12):
            e.put(60, 60 + 12 * i, "2026-%02d" % (i + 1)); e.put(200, 60 + 12 * i, str(i + 3), "r"); e.put(260, 60 + 12 * i, "{:,.2f}".format(7.5 * (i + 1)), "r")
            e.put(350, 60 + 12 * i, "{:,.2f}".format(1000.5 * (i + 1)), "r"); e.put(380, 60 + 12 * i, "check")
        b = P.book(e.layout())
        self.assertEqual(X.overview(b), '"page 1" A1:C12; "page 2" A1:E12')
        self.assertEqual(grid(b["sheets"][0])[1], ["Item 1", "2469", "-198.5"])
        self.assertEqual(grid(b["sheets"][1])[11], ["2026-12", "14", "90", "12006", "check"])

    def test_a_column_filled_only_later_and_a_label_close_to_its_figure(self):
        d = Doc()
        for p in range(2):
            if p:
                d.page()
            for x, t, a in ((40, "Konto", "l"), (90, "Text", "l"), (330, "Soll", "r"), (420, "Haben", "r"), (520, "Saldo", "r")):
                d.put(x, 60, t, a)
            for i in range(30):
                y = 74 + 12 * i
                d.put(40, y, str(1000 + 100 * p + i)); d.put(90, y, "Buchung %d" % i); d.put(330, y, de(100.5 + i), "r"); d.put(520, y, de(9000.25 + i), "r")
                if p and i % 3 == 0:
                    d.put(420, y, de(50 + i), "r")
            d.put(540, 810, "Seite %d" % (p + 1), "r")
        long = "Umsatzerlöse Inland steuerpflichtig x x x x x x x"
        d.put(40, 74 + 12 * 31, "9999"); d.put(90, 74 + 12 * 31, long); d.put(330, 74 + 12 * 31, de(1234567.89), "r"); d.put(520, 74 + 12 * 31, de(1), "r")
        self.assertLess(330 - width(de(1234567.89), 9) - (90 + width(long, 9)), 6)     # the label ends a hair before its figure
        b = P.book(d.layout())
        g = grid(b["sheets"][0])
        self.assertEqual(X.overview(b), '"pages 1-2" A1:E62')
        self.assertEqual(g[0], ["Konto", "Text", "Soll", "Haben", "Saldo"])
        self.assertEqual(g[1], ["1000", "Buchung 0", "100.5", "", "9000.25"])         # page 1: the column is there, empty
        self.assertEqual(g[31], ["1100", "Buchung 0", "100.5", "50", "9000.25"])
        self.assertEqual(g[61], ["9999", long, "1234567.89", "", "1"])

    def test_never_a_wrong_figure_silently(self):
        """What an independent review found, each as a document: cells drawn together into one number, a sign or a mark that
        went to the wrong figure, a column filled once, lines taken for a running head, a notation tipped by dates."""
        # an invoice: the labels of its totals run over "quantity" and "price" -- both stay columns, 3 and 250,00 never 3250
        d = Doc()
        d.put(60, 40, "Rechnung 2026-0815", size=12)
        for x, t, a in ((40, "Pos", "l"), (70, "Bezeichnung", "l"), (330, "Menge", "r"), (420, "Einzelpreis", "r"), (540, "Gesamt", "r")):
            d.put(x, 70, t, a)
        items = [("Beratung vor Ort", 3, 250.0), ("Fahrtkosten pauschal", 12, 345.0), ("Lizenz Standard", 2, 500.0), ("Schulung", 1, 890.0), ("Wartung Quartal", 4, 125.5)]
        for i, (name, m, ep) in enumerate(items):
            y = 86 + 13 * i
            d.put(40, y, str(i + 1)); d.put(70, y, name); d.put(330, y, str(m), "r"); d.put(420, y, de(ep), "r"); d.put(540, y, de(m * ep), "r")
        for i, (label, v) in enumerate((("Summe netto (zuzüglich Umsatzsteuer)", 7282.0), ("zuzüglich 19 % Umsatzsteuer auf den Nettobetrag", 1383.58), ("Gesamtbetrag brutto, zahlbar bis 30.11.2026", 8665.58))):
            d.put(430, 160 + 13 * i, label, "r"); d.put(540, 160 + 13 * i, de(v), "r")
        b = P.book(d.layout())
        g = grid(b["sheets"][0])
        self.assertEqual(g[1], ["Pos", "Bezeichnung", "Menge", "Einzelpreis", "Gesamt"])
        self.assertEqual(g[2:7], [[str(i + 1), n, str(m), X.plain(X.number("%.2f" % ep)), X.plain(X.number("%.2f" % (m * ep)))] for i, (n, m, ep) in enumerate(items)])
        self.assertEqual((X.sum_range(b, None, "C3:C7")["sum"], X.sum_range(b, None, "E3:E7")["sum"]), ("22", "7282"))
        self.assertEqual(P._value(["3", "250,00"], True, False), ("t", "3 · 250,00"))          # two figures in one column: shown apart, as text
        self.assertEqual(P._value(["1.234,56", "S"], True, False), ("m", "1234.56 S")); self.assertEqual(P._value(["Bank", "Nord"], True, False), ("t", "Bank Nord"))
        e = Doc()
        e.put(60, 60, "Sehr geehrte Damen und Herren,"); e.put(60, 80, "3"); e.put(120, 80, "250,00"); e.put(60, 100, "Mit freundlichen Grüßen")
        self.assertEqual(grid(P.book(e.layout())["sheets"][0])[1], ["3  250,00"])          # (a page without a table: the line as it reads)
        # Excel's accounting format: the minus at the left edge of the column, the figure at the right
        d = Doc()
        d.put(40, 60, "Position"); d.put(300, 60, "Plan", "r"); d.put(420, 60, "Ist", "r")
        for i in range(10):
            d.put(40, 76 + 13 * i, "Zeile %d" % i); d.put(300, 76 + 13 * i, de(1000.0 + i), "r"); d.put(420, 76 + 13 * i, de(500.0 + i), "r")
            if i in (2, 5):
                d.put(340, 76 + 13 * i, "-")
        b = P.book(d.layout())
        self.assertEqual(grid(b["sheets"][0])[3], ["Zeile 2", "1002", "-502"])
        self.assertEqual((X.sum_range(b, None, "B2:B11")["sum"], X.sum_range(b, None, "C2:C11")["sum"]), ("10045", "3031"))
        # a column filled once in sixty lines is still a column
        d = Doc()
        for x, t, a in ((40, "Datum", "l"), (110, "Buchungstext", "l"), (380, "Soll", "r"), (460, "Haben", "r"), (545, "Saldo", "r")):
            d.put(x, 60, t, a)
        for i in range(60):
            y = 74 + 12 * i
            d.put(40, y, "%02d.10.2026" % (i % 28 + 1)); d.put(110, y, "Wareneinkauf Lieferant %d" % i); d.put(545, y, de(1000 + i), "r")
            d.put(460 if i == 30 else 380, y, de(5000 if i == 30 else 100.5 + i), "r")
        b = P.book(d.layout())
        g = grid(b["sheets"][0])
        self.assertEqual((g[0], g[31]), (["Datum", "Buchungstext", "Soll", "Haben", "Saldo"], ["2026-10-03", "Wareneinkauf Lieferant 30", "", "5000", "1030"]))
        self.assertEqual(X.sum_range(b, None, "C2:C61")["sum"], X.plain(sum((X.number("%.2f" % (100.5 + i)) for i in range(60) if i != 30), X.number("0"))))
        # a mark S/H printed apart from its figure -- close behind it, or as a column of its own: the figure's mark, sums per mark
        for gap in (4.0, 30.0):
            d = Doc()
            for i in range(6):
                d.put(40, 60 + 12 * i, str(1200 + i)); d.put(90, 60 + 12 * i, "Konto %d" % i); d.put(400, 60 + 12 * i, de(1000.0 + 100 * i), "r"); d.put(400 + gap, 60 + 12 * i, "SH"[i % 2])
            b = P.book(d.layout())
            self.assertEqual(grid(b["sheets"][0])[1], ["1201", "Konto 1", "1100 H"], gap)
            s = X.sum_range(b, None, "C1:C6")
            self.assertEqual(({k: v["sum"] for k, v in s["with_mark"].items()}, "sum" in s), ({"H": "3900", "S": "3600"}, False), gap)
        # another money is never added to the document's own
        d = Doc()
        for i, t in enumerate(("1.000,00 EUR", "2.000,00 USD", "3.000,00 CHF", "4.000,00 EUR")):
            d.put(40, 60 + 12 * i, "Posten %d" % i); d.put(400, 60 + 12 * i, t, "r")
        s = X.sum_range(P.book(d.layout()), None, "B1:B4")
        self.assertEqual((s["sum"], {k: v["sum"] for k, v in s["with_mark"].items()}), ("5000", {"CHF": "3000", "USD": "2000"}))
        # a long label ending a hair before its amount is a label and an amount (not a sentence)
        d = Doc()
        long = "Zinsen und ähnliche Aufwendungen aus Darlehen von Gesellschaftern und verbundenen Unternehmen im Inland sowie an uns"
        for i, (name, v) in enumerate((("Umsatzerlöse", 900000.0), ("Materialaufwand", -400000.0), (long, -1234567.89), ("Steuern vom Einkommen und vom Ertrag", -50000.0), ("Jahresüberschuss", 100000.0))):
            d.put(40, 76 + 13 * i, name, size=8); d.put(540, 76 + 13 * i, de(v), "r", 8)
        self.assertLess(540 - width(de(-1234567.89), 8) - (40 + width(long, 8)), 5)
        b = P.book(d.layout())
        self.assertEqual((grid(b["sheets"][0])[2], X.sum_range(b, None, "B1:B5")["sum"]), ([long, "-1234567.89"], "-684567.89"))

    def test_signs_marks_and_labels_second_round(self):
        # a dash for "nothing" where other lines have a figure is no minus for the figure beside it
        d = Doc()
        d.put(40, 60, "Position"); d.put(300, 60, "2025", "r"); d.put(420, 60, "2026", "r")
        rows = [("Miete", 12000.0, 12600.0), ("Strom", None, 2400.5), ("Versicherung", 890.0, 910.0), ("Leasing", None, 4800.0), ("Telefon", 480.0, 500.0), ("Wartung", 1200.0, 1100.0)]
        for i, (name, a, b) in enumerate(rows):
            d.put(40, 76 + 13 * i, name); d.put(300, 76 + 13 * i, de(a) if a is not None else "-", "r"); d.put(420, 76 + 13 * i, de(b), "r")
        b = P.book(d.layout())
        g = grid(b["sheets"][0])
        self.assertEqual((g[2], g[4]), (["Strom", "-", "2400.5"], ["Leasing", "-", "4800"]))
        self.assertEqual((X.sum_range(b, None, "B2:B7")["sum"], X.sum_range(b, None, "C2:C7")["sum"]), ("14570", "22310.5"))
        # a sign a little behind its figure belongs to that figure, not to the balance in the next column
        for gap in (2.5, 4.5):
            d = Doc()
            for i in range(6):
                v = 250.0 + 10 * i
                d.put(40, 60 + 12 * i, "Zahlung %d" % i); d.put(300, 60 + 12 * i, de(v), "r"); d.put(420, 60 + 12 * i, de(5000.0 + 100 * i), "r")
                if i % 2 == 0:
                    d.put(300 + gap, 60 + 12 * i, "-")
            b = P.book(d.layout())
            self.assertEqual(grid(b["sheets"][0])[:2], [["Zahlung 0", "-250", "5000"], ["Zahlung 1", "260", "5100"]], gap)
            self.assertEqual(X.sum_range(b, None, "C1:C6")["sum"], "31500", gap)
        # a page number a wide blank behind its word (a scan) is no figure -- also on the only page, where no foot goes
        d = Doc()
        for i in range(5):
            d.put(40, 60 + 12 * i, "Posten %d" % i); d.put(300, 60 + 12 * i, de(100.0 + i), "r"); d.put(420, 60 + 12 * i, de(7.0 + i), "r")
        d.put(250, 800, "Seite 1 von", size=7); d.put(250 + width("Seite 1 von", 7) + 6, 800, "1", size=7)
        b = P.book(d.layout())
        self.assertEqual((grid(b["sheets"][0])[-1][1:], X.sum_range(b, None, "B1:B6")["sum"], X.sum_range(b, None, "C1:C6")["sum"]), (["Seite 1 von 1", ""], "510", "45"))
        for parts, want in ((("Seite", "1 von", "1"), ["Seite 1 von 1"]), (("Blatt 3", "/", "12"), ["Blatt 3 / 12"]), (("Seite 1", "250"), ["Seite 1", "250"]),
                            (("Page 1 of", "12,50"), ["Page 1 of", "12,50"]), (("Seite", "12"), ["Seite 12"])):
            x, words = 40.0, []
            for part in parts:
                words.append(P.Word(x, x + width(part, 7), 5, 7, part)); x += width(part, 7) + 5
            self.assertEqual([c.text for c in P._lines(words, 1)[0].cells], want, parts)
        d = Doc()                                                                                   # ... and a number alone at the bottom
        for i in range(5):
            d.put(40, 60 + 12 * i, "Posten %d" % i); d.put(300, 60 + 12 * i, str(100 + i), "r")
        d.put(300, 800, "1", "r", 7)
        b = P.book(d.layout())
        self.assertEqual((grid(b["sheets"][0])[-1], X.sum_range(b, None, "B1:B6")["sum"]), (["", "1"], "510"))
        self.assertEqual(b["sheets"][0]["cells"][(5, 1)][0], "t")
        ln = P._lines([P.Word(40, 70, 5, 9, "Kasse"), P.Word(74, 80, 5, 9, "1"), P.Word(300, 330, 5, 9, "12,00")], 1)[0]
        self.assertEqual([c.text for c in ln.cells], ["Kasse 1", "12,00"])                          # (and nothing else is glued)
        ln = P._lines([P.Word(40, 70, 5, 9, "Konto"), P.Word(90, 110, 5, 9, "1200"), P.Word(300, 330, 5, 9, "12,00")], 1)[0]
        self.assertEqual([c.text for c in ln.cells], ["Konto", "1200", "12,00"])
        # close to a figure on both sides nobody can tell whose sign it is: neither becomes a number
        ln = P._lines([P.Word(40, 80, 5, 9, "Posten"), P.Word(260, 300, 5, 9, "250,00"), P.Word(303, 306, 5, 9, "-"), P.Word(309, 350, 5, 9, "5.000,00")], 1)[0]
        self.assertEqual([c.text for c in ln.cells], ["Posten", "250,00 - 5.000,00"])               # (a space apart on both sides: one cell, text)
        self.assertEqual(P.figure(ln.cells[1].text)[0], "t")
        # the marks' column with its own heading and a head reaching into it: still marks, row by row
        d = Doc()
        d.put(40, 46, "Summenliste"); d.put(445, 46, "Seite 1", "r"); d.put(40, 60, "Konto"); d.put(90, 60, "Bezeichnung"); d.put(400, 60, "Saldo", "r"); d.put(428, 60, "S/H")
        for i in range(6):
            d.put(40, 74 + 12 * i, str(1200 + i)); d.put(90, 74 + 12 * i, "Konto %d" % i); d.put(400, 74 + 12 * i, de(1000.0 + 100 * i), "r"); d.put(430, 74 + 12 * i, "SH"[i % 2])
        b = P.book(d.layout())
        s = X.sum_range(b, None, "C1:C9")
        self.assertEqual(({k: v["sum"] for k, v in s["with_mark"].items()}, "sum" in s), ({"H": "3900", "S": "3600"}, False))
        # other moneys behind the figure or in a column of their own; a plus behind
        self.assertEqual([P.figure(t) for t in ("2.000,00 SEK", "PLN 3.000,00", "100,00 +", "5,00 EUR")], [("m", "2000 SEK"), ("m", "3000 PLN"), ("n", "100"), ("n", "5")])
        d = Doc()
        for i, cur in enumerate(("EUR", "USD", "CHF", "EUR", "USD")):
            d.put(40, 60 + 12 * i, "Posten %d" % i); d.put(300, 60 + 12 * i, de(1000.0 * (i + 1)), "r"); d.put(340, 60 + 12 * i, cur)
        s = X.sum_range(P.book(d.layout()), None, "B1:B5")
        self.assertEqual((s["sum"], {k: v["sum"] for k, v in s["with_mark"].items()}), ("5000", {"CHF": "3000", "USD": "7000"}))
        # labels ending a hair before the first column of figures (2 of 30), and a long label before a whole number
        d = Doc()
        for x, t, a in ((40, "Konto", "l"), (90, "Bezeichnung", "l"), (380, "Soll", "r"), (460, "Haben", "r"), (545, "Saldo", "r")):
            d.put(x, 60, t, a)
        long = "Aufwendungen für bezogene Leistungen und Fremdarbeiten im a"
        while 380 - width(de(105.5), 9) - (90 + width(long + "a", 9)) > 2.5:
            long += "a"
        for i in range(30):
            y = 74 + 12 * i
            d.put(40, y, str(4000 + i)); d.put(90, y, long if i in (5, 17) else "Buchung %d" % i); d.put(380, y, de(100.5 + i), "r"); d.put(545, y, de(1000 + i), "r")
            if i % 2:
                d.put(460, y, de(50 + i), "r")
        b = P.book(d.layout())
        g = grid(b["sheets"][0])
        self.assertEqual((g[0], g[6]), (["Konto", "Bezeichnung", "Soll", "Haben", "Saldo"], ["4005", long, "105.5", "55", "1005"]))
        self.assertEqual(X.sum_range(b, None, "C2:C31")["sum"], X.plain(sum((X.number("%.2f" % (100.5 + i)) for i in range(30)), X.number("0"))))
        d = Doc()
        label = "Zinsen und ähnliche Aufwendungen aus Darlehen von Gesellschaftern sowie an alle Banken"
        for i, (name, v) in enumerate((("Umsatzerlöse", "900.000"), ("Materialaufwand", "400.000-"), (label, "890"), ("Steuern", "50.000-"), ("Ergebnis", "450.890"))):
            d.put(40, 76 + 13 * i, name, size=8); d.put(540, 76 + 13 * i, v, "r", 8)
        b = P.book(d.layout())
        self.assertEqual((grid(b["sheets"][0])[2], X.sum_range(b, None, "B1:B5")["sum"]), ([label, "890"], "901780"))

    def test_signs_standing_apart_third_round(self):
        accounting = lambda rows, **how: P.book(accounting_doc(rows, **how).layout())
        rows = ACCOUNTING
        for euro in (False, True):
            b = accounting(rows, euro=euro)
            self.assertEqual(grid(b["sheets"][0])[2:4], [["Erstattung", "1002", "-502"], ["Rücklage", "21006", "-20506"]], euro)
            self.assertEqual((X.sum_range(b, None, "B2:B6")["sum"], X.sum_range(b, None, "C2:C6")["sum"], b["signs_apart"]), ("53446", "5907.5", 3), euro)
        b = accounting(rows + [("Korrektur", -300.0, 100.0)])                  # the table says it itself: label, minus, figure
        self.assertEqual((grid(b["sheets"][0])[6], X.sum_range(b, None, "C2:C7")["sum"], b["signs_apart"]), (["Korrektur", "-300", "100"], "6007.5", 0))
        # a column of dashes under a heading of its own is a column without values -- first, in the middle, last
        for empty in (0, 1, 2):
            d = Doc()
            d.put(40, 60, "Position")
            for k, year in enumerate(("2024", "2025", "2026")):
                d.put(260 + 90 * k, 60, year, "r")
            for i in range(6):
                d.put(40, 76 + 13 * i, "Posten %d" % i)
                for k in range(3):
                    d.put(260 + 90 * k - (0 if k != empty else 6), 76 + 13 * i, "-" if k == empty else de(1000.0 * (k + 1) + i), "r")
            b = P.book(d.layout())
            g = grid(b["sheets"][0])
            want = ["Posten 2"] + ["-" if k == empty else X.plain(X.number(str(1000 * (k + 1) + 2))) for k in range(3)]
            self.assertEqual((g[3], b["signs_apart"]), (want, 0), empty)
            for k in range(3):
                got = X.sum_range(b, None, "%s2:%s7" % ("BCD"[k], "BCD"[k]))
                self.assertEqual((got["sum"], got["numbers_added"]), ("0", 0) if k == empty else (str(6000 * (k + 1) + 15), 6), (empty, k))
        d = Doc()                                                                # ... and a dash set in the middle of a column of short figures
        d.put(40, 60, "Position"); d.put(300, 60, "2025", "r"); d.put(420, 60, "2026", "r")
        for i, (a, v) in enumerate((("890,00", 910.0), (None, 2400.5), ("480,00", 500.0), (None, 4800.0))):
            d.put(40, 76 + 13 * i, "Posten %d" % i); d.put(420, 76 + 13 * i, de(v), "r")
            d.put(300 if a else 262, 76 + 13 * i, a or "–", "r" if a else "l")
        b = P.book(d.layout())
        self.assertEqual((grid(b["sheets"][0])[2], X.sum_range(b, None, "C2:C5")["sum"]), (["Posten 1", "–", "2400.5"], "8610.5"))
        # a column of signs far behind the amounts: the table says whose they are -- or nobody does
        def statement(behind_balance, plus=False, onto=False):
            d = Doc()
            for i in range(8):
                y = 60 + 11 * i
                d.put(40, y, "Zahlung %d" % i, size=8); d.put(300, y, de(250.0 + 10 * i), "r", 8); d.put(420, y, de(5000.0 + 100 * i), "r", 8)
                if i % 2 == 0 or plus:
                    d.put(310, y, "-" if i % 2 == 0 else "+", size=8)
                if behind_balance and i % 3 == 0:
                    d.put(430, y, "-", size=8)
                if onto:
                    d.put(520, y, de(3.0 + i) + "-", "r", 8)
            return P.book(d.layout())
        for b in (statement(True), statement(False, onto=True)):
            self.assertEqual((grid(b["sheets"][0])[0][1], grid(b["sheets"][0])[1][1], X.sum_range(b, None, "B1:B8")["sum"], b["signs_apart"]), ("-250", "260", "40", 0))
        self.assertEqual(grid(statement(True)["sheets"][0])[0][:3], ["Zahlung 0", "-250", "-5000"])
        b = statement(False, plus=True)                                          # a plus too, and nothing says before or behind: no figure
        self.assertEqual(grid(b["sheets"][0])[:2], [["Zahlung 0", "250,00 (-)", "(-) 5.000,00"], ["Zahlung 1", "260,00 (+)", "(+) 5.100,00"]])
        self.assertEqual(X.sum_range(b, None, "B1:C8").get("left_out"), {"text": 16})
        b = statement(False)                                                     # nothing says it: before the figure after it, and the model is told
        self.assertEqual((grid(b["sheets"][0])[0], b["signs_apart"]), (["Zahlung 0", "250", "-5000"], 4))
        # a sign a space apart between a number in a text and an amount, in one string: text, never an amount without its sign
        for text in ("Gutschrift zu Rechnung 4711 - 119,00", "Anzahlung vom 3. 10. - 500,00", "Rabatt - 23,80"):
            x, words = 300.0 - width(text, 9), []
            for part in text.split(" "):
                words.append(P.Word(x, x + width(part, 9), 5, 9, part)); x += width(part + " ", 9)
            self.assertEqual([(c.text, P.figure(c.text)[0]) for c in P._lines(words, 1)[0].cells], [(text, "t")])
        # marks in a column of their own: only behind amounts, close by -- not before the figure after them, not behind a count
        def marked(left, mark, right, lx=200, mx=215, rx=330):
            d = Doc()
            for i in range(6):
                d.put(40, 60 + 12 * i, "Zeile %d" % i); d.put(lx, 60 + 12 * i, left[i % len(left)], "r"); d.put(mx, 60 + 12 * i, mark[i % len(mark)])
                if right:
                    d.put(rx, 60 + 12 * i, right[i % len(right)], "r")
            return P.book(d.layout())
        b = marked(["100", "25"], ["USD", "EUR"], ["172,50", "98,10"], mx=260)   # a count, the money of the price after it
        self.assertEqual((grid(b["sheets"][0])[0], "with_mark" in X.sum_range(b, None, "B1:B6")), (["Zeile 0", "100", "USD", "172.5"], False))
        b = marked(["8400", "1200"], ["S", "H"], ["100,00", "250,00"])           # an account, S or H of the amount after it
        self.assertEqual((grid(b["sheets"][0])[0], "with_mark" in X.sum_range(b, None, "B1:B6")), (["Zeile 0", "8400", "S", "100"], False))
        b = marked(["100,00", "25,00"], ["USD"], ["172,50", "98,10"], mx=272)    # amounts, the mark nearer to the figure after it
        self.assertEqual(grid(b["sheets"][0])[0], ["Zeile 0", "100", "USD", "172.5"])
        b = marked(["100,00", "25,00"], ["S", "H"], ["172,50", "98,10"])         # amounts, the mark right behind them
        self.assertEqual((grid(b["sheets"][0])[:2], X.sum_range(b, None, "B1:B6")["with_mark"]["S"]["sum"]), ([["Zeile 0", "100 S", "172.5"], ["Zeile 1", "25 H", "98.1"]], "300"))
        self.assertEqual((P.figure("8,00 h"), P.figure("8,00 H")), (("t", "8,00 h"), ("m", "8 H")))                 # hours are no "Haben"
        b = marked(["8,00", "12,50"], ["h"], None)
        self.assertEqual(grid(b["sheets"][0])[0], ["Zeile 0", "8", "h"])
        # a decimal point nobody proves: 12.500 beside 0.500 or a price 4.80 stays text, never twelve thousand five hundred
        L = lambda *texts: P.Line(0, 9, [P.Cell(P.Word(40 + 100 * i, 80 + 100 * i, 0, 9, t)) for i, t in enumerate(texts)], 1)
        self.assertEqual(P.notation([L("Widget", "0.500", "4.80", "2.40"), L("Gadget", "12.500", "20.00", "250.00")]), "?")
        self.assertEqual(P.notation([L("Widget", "1.250", "4.80"), L("Gadget", "12.500", "20.00")]), "?")
        self.assertEqual(P.notation([L("4400.10", "Erlöse Gruppe", "12.345"), L("4410.11", "Erlöse", "24.690")]), ",")       # (accounts in front)
        self.assertEqual(P.notation([L("Beginn", "14.30", "12.345"), L("Ende", "02.10", "1.250")]), ",")                     # (a time, a date)
        self.assertEqual((P.figure("0.500"), P.figure("0,500", de=False), P.figure("12.500", unsure=True), P.figure("0,5")), (("t", "0.500"), ("t", "0,500"), ("t", "12.500"), ("n", "0.5")))
        d = Doc()
        for i, (name, qty, price, total) in enumerate((("Widget", "0.500", "4.80", "2.40"), ("Gadget", "1.250", "20.00", "25.00"), ("Gizmo", "12.500", "20.00", "250.00"))):
            d.put(40, 60 + 12 * i, name); d.put(300, 60 + 12 * i, qty, "r"); d.put(380, 60 + 12 * i, price, "r"); d.put(460, 60 + 12 * i, total, "r")
        b = P.book(d.layout())
        self.assertEqual((b["decimal"], grid(b["sheets"][0])[2], X.sum_range(b, None, "B1:D3").get("left_out")), ("?", ["Gizmo", "12.500", "20.00", "250.00"], {"text": 9}))

    def test_what_looks_like_a_running_head_but_is_not(self):
        # a head naming another cost centre on each page is another head; years as titles and an account number alone are no page numbers
        d = Doc()
        for p in range(3):
            if p:
                d.page()
            d.put(40, 40, "Betriebswirtschaftliche Auswertung", size=11); d.put(40, 56, "Kostenstelle %d00" % (p + 1)); d.put(540, 56, "Seite %d" % (p + 1), "r")
            d.put(300, 72, str(2024 + p)); d.put(40, 88, "Bezeichnung"); d.put(400, 88, "Monat", "r"); d.put(540, 88, "Kumuliert", "r")
            for i, name in enumerate(("Umsatzerlöse", "Wareneinsatz", "Personalkosten", "Raumkosten", "Ergebnis")):
                d.put(40, 104 + 13 * i, name); d.put(400, 104 + 13 * i, de(1000.5 * (i + 1) * (p + 1)), "r"); d.put(540, 104 + 13 * i, de(9000.25 * (i + 1) * (p + 1)), "r")
            d.put(300, 810, "- %d -" % (p + 1))
        b = P.book(d.layout())
        flat = [" ".join(c for c in r if c) for r in grid(b["sheets"][0])]
        self.assertEqual([t for t in flat if t.startswith("Kostenstelle")], ["Kostenstelle 100 Seite 1", "Kostenstelle 200 Seite 2", "Kostenstelle 300 Seite 3"])
        self.assertEqual([t for t in flat if t in ("2024", "2025", "2026")], ["2024", "2025", "2026"])
        self.assertEqual((flat.count("Betriebswirtschaftliche Auswertung"), flat.count("Bezeichnung Monat Kumuliert"), [t for t in flat if t.startswith("-")]), (1, 1, []))
        self.assertEqual(b["left_out"]["lines"], 7)                                   # 2 titles, 2 headings, 3 page numbers -- and said
        self.assertIn("Bezeichnung Monat Kumuliert", b["left_out"]["examples"])
        # counts without decimals, one page per branch: the same rows near the top of each page are rows, not a head
        d = Doc()
        rows = [("Marktleitung", 1), ("Stellvertretung", 1), ("Vollzeit", 6), ("Teilzeit", 8), ("Aushilfen", 5), ("Auszubildende", 2), ("Reinigung", 1), ("Fahrer", 2)]
        for p, branch in enumerate(("Nord", "Süd")):
            if p:
                d.page()
            d.put(40, 40, "Filiale " + branch, size=11); d.put(40, 60, "Stelle"); d.put(300, 60, "Köpfe", "r"); d.put(400, 60, "Stunden", "r")
            for i, (name, n) in enumerate(rows):
                d.put(40, 76 + 13 * i, name); d.put(300, 76 + 13 * i, str(n), "r"); d.put(400, 76 + 13 * i, str(n * 40), "r")
        b = P.book(d.layout())
        g = grid(b["sheets"][0])
        self.assertEqual(len([r for r in g if r[1].isdigit()]), 16)
        self.assertEqual(X.sum_range(b, None, "B1:B%d" % len(g))["sum"], "52")
        self.assertEqual([r[0] for r in g if r[0].startswith("Filiale")], ["Filiale Nord", "Filiale Süd"])

    def test_notation_and_pages_askew(self):
        N = lambda *texts: P.notation([P.Line(0, 9, [P.Cell(P.Word(0, 10, 0, 9, t)) for t in texts], 1)])
        self.assertEqual(N("1.234,56", "01.10.26", "14.30", "02.10"), ",")            # dates and times of day say nothing
        self.assertEqual(N("01.10.26", "14.30", "3.16", "12.345"), ",")               # whole thousands with points: German
        self.assertEqual(N("1,234.56", "12.50"), "."); self.assertEqual(N("123.45", "999.90", "7,50"), ","); self.assertEqual(N("4400.10", "4410.20", "12.345"), ",")          # (account numbers)
        self.assertEqual(N("12,345", "1,250"), "?"); self.assertEqual(N("12,345", "1.250"), ","); self.assertEqual(N("Text"), ",")
        d = Doc()
        for i in range(4):
            d.put(40, 60 + 12 * i, "Product %d" % i); d.put(300, 60 + 12 * i, "{:,}".format(1250 * (i + 1)), "r"); d.put(400, 60 + 12 * i, "{:,}".format(12345 * (i + 1)), "r")
        b = P.book(d.layout())
        self.assertEqual((b["decimal"], grid(b["sheets"][0])[0], X.sum_range(b, None, "B1:C4")["numbers_added"]), ("?", ["Product 0", "1,250", "12,345"], 0))          # thousands or decimals? text
        d = Doc()
        for i in range(6):
            d.put(40, 60 + 12 * i, "%02d.10.26" % (i + 1)); d.put(100, 60 + 12 * i, "%02d.10.26" % (i + 2)); d.put(160, 60 + 12 * i, "Zahlung %d" % i)
            d.put(400, 60 + 12 * i, ("1.234,56", "1.250", "89,90-", "12.000", "3,50", "250.000")[i], "r")
        b = P.book(d.layout())
        self.assertEqual((b["decimal"], [r[3] for r in grid(b["sheets"][0])]), (",", ["1234.56", "1250", "-89.9", "12000", "3.5", "250000"]))
        # a scanned page lying askew: turned straight before its lines are read
        import math
        d = Doc()
        want = []
        for i in range(12):
            d.put(60, 80 + 13 * i, "Miete Laden %d" % i); d.put(400, 80 + 13 * i, de(1000.0 + 10 * i), "r"); d.put(540, 80 + 13 * i, de(12000.0 + 120 * i), "r")
            want.append(["Miete Laden %d" % i, X.plain(X.number("%.2f" % (1000.0 + 10 * i))), X.plain(X.number("%.2f" % (12000.0 + 120 * i)))])
        for degrees in (-2.0, -0.6, 0.0, 0.4, 1.5, 2.5):
            lay = d.layout(how="ocr")
            t = math.tan(math.radians(degrees))
            for it in lay["pages"][0]["items"]:              # each word turned about the page's corner (its middle moves, its box stays upright)
                xc, yc = it[0] + it[2] / 2.0, it[1] + it[3] / 2.0
                it[0], it[1] = round(xc - yc * t - it[2] / 2.0), round(yc + xc * t - it[3] / 2.0)
            self.assertEqual(grid(P.book(lay)["sheets"][0]), want, degrees)
        # scanned pages lying a little to the side of each other are still one table
        doc, rows = statement(pages=3)
        moved = doc.layout(how="ocr")
        for p, dx in zip(moved["pages"], (0, 70, -50)):       # (7 and 5 points)
            for it in p["items"]:
                it[0] += dx
        b = P.book(moved)
        self.assertEqual(len(b["sheets"]), 1)
        self.assertEqual([r for r in grid(b["sheets"][0]) if r[0].isdigit()], [as_cells(r) for r in rows])
        # pages nothing was found on are not counted as read
        lay = d.layout()
        lay["pages"] += [{"n": 2, "how": "none", "items": []}, {"n": 3, "how": "ocr", "items": []}]
        b = P.book(dict(lay, count=3))
        self.assertEqual((b["pages"], b["pages_read"], b["how"]), (3, 1, {"pdf": 1, "none": 2}))

    def test_a_price_is_no_time_of_day(self):
        """12.40 could be twenty to one -- or a price. Beside figures like 2.500 only a time or a date written as one (02.10,
        14.30 Uhr, and what stands in their column) or a heading Uhrzeit/Datum above leaves those thousands; a price makes
        them unclear: text, never two thousand five hundred for two and a half."""
        def doc(rows, head=("Item", "Quantity", "Price", "Total"), top=None):
            d = Doc()
            if top:
                d.put(top[0], 40, top[1], top[2] if len(top) > 2 else "l")
            for x, t, a in zip((40, 300, 400, 500), head, "lrrr"):
                d.put(x, 70, t, a)
            for i, row in enumerate(rows):
                for x, t, a in zip((40, 300, 400, 500), row, "lrrr"):
                    d.put(x, 86 + 13 * i, t, a)
            return P.book(d.layout())
        # what the review found: every price here could be a time of day (up to 31, up to 59) -- the quantities became thousands
        b = doc([("Widget blue", "2.500", "12.40", "31.00"), ("Widget red", "1.000", "9.50", "9.50"), ("Service fee", "3.000", "10.10", "30.30")])
        self.assertEqual((b["decimal"], grid(b["sheets"][0])[1:]), ("?", [["Widget blue", "2.500", "12.40", "31.00"], ["Widget red", "1.000", "9.50", "9.50"],
                                                                          ["Service fee", "3.000", "10.10", "30.30"]]))
        self.assertEqual((X.sum_range(b, None, "B1:B5")["numbers_added"], X.sum_range(b, None, "B1:D5")["left_out"]), (0, {"text": 12}))
        # ... also with one price, with prices that would even be dates (12.10, 9.05), and with a date written out elsewhere on the page
        for rows, top in (([("Widget blue", "2.500", "12.40")], None), ([("Widget blue", "2.500", "12.10"), ("Widget red", "1.000", "9.05")], None),
                          ([("Widget blue", "2.500", "12.40"), ("Widget red", "1.000", "9.50")], (400, "Date 02.10.2026", "r")),           # (above the prices)
                          ([("Widget blue", "2.500", "12.40"), ("Widget red", "1.000", "9.50")], (40, "Printed 02.10 08:15")),      # (a time of day -- in no column of theirs)
                          ([("Widget blue", "2.500", "12.40"), ("Widget red", "1.000", "9.50")], (400, "Printed 02.10.2026 08:15", "r")),   # the printing time right above the prices
                          ([("Widget blue", "2.500", "12.40", "31.00"), ("Widget red", "1.000", "9.50", "9.50")], (500, "Time 08:15 Page 1", "r")),
                          ([("Widget blue", "2.500", "12.40"), ("Widget red", "1.000", "9.50")], (400, "Datum: 02.10.2026", "r"))):        # (no heading: a figure in its line)
            b = doc(rows, top=top)
            self.assertEqual((b["decimal"], [r[1] for r in grid(b["sheets"][0])[-len(rows):]], X.sum_range(b, None, "B1:C6")["numbers_added"]),
                             ("?", [r[1] for r in rows], 0), rows)
        L = lambda *texts: P.Line(0, 9, [P.Cell(P.Word(40 + 100 * i, 80 + 100 * i, 0, 9, t)) for i, t in enumerate(texts)], 1)
        self.assertEqual(P.notation([L("Widget blue", "2.500", "12.40", "31.00"), L("Widget red", "1.000", "9.50", "9.50")]), "?")
        self.assertEqual(P.notation([L("Lager", "14.30", "12.345"), L("Laden", "16.00", "1.250")]), "?")              # nothing says these are times of day
        self.assertEqual(P.notation([L("Lager", "02.10", "12.345"), L("Laden", "1.250", "14.30")]), "?")              # 14.30 in another column than 02.10
        self.assertEqual(P.notation([L("Lager", "02.10", "12.345")] + [P.Line(0, 9, [P.Cell(P.Word(40, 80, 0, 9, "Laden")), P.Cell(P.Word(140, 180, 0, 9, "14.30"))], 2)]), "?")     # ... on another page
        self.assertEqual(P.notation([L("Lager", "09.75", "12.345")]), "?"); self.assertEqual(P.notation([L("Lager", "08.30", "12.345"), L("Laden", "14.75", "1.250")]), "?")     # (no time of day at all)
        self.assertEqual(P.notation([L("Lager", "8:15", "12.345"), L("Laden", "14.30", "1.250")]), "?")               # 8:15 is no amount, but vouches for nothing
        self.assertEqual(P.notation([L("Lager", "24.30", "Uhr", "12.345"), L("Laden", "14.30", "1.250")]), "?")       # (no time of day: 24.30)
        self.assertEqual(P.notation([L("Tour", "Abfahrt", "Stück"), L("Nord", "14.30", "12.345"), L("Süd", "9.15", "1.250")]), "?")      # a heading that says nothing
        self.assertEqual(P.notation([L("Seite 1", "Zeit", "08:15"), L("Nord", "14.30", "12.345")]), "?")             # (no heading: figures in its line)
        # the other way round -- German lists stay as they were: times of day and dates written as such beside whole thousands
        for lines in ([L("Beginn", "14.30", "12.345"), L("Ende", "02.10", "1.250")],                                   # in the column of 02.10
                      [L("Lager", "14.30", "Uhr", "12.345"), L("Laden", "16.00", "Uhr", "1.250")],                     # 14.30 Uhr
                      [L("Lager", "14.30", "Uhr", "12.345"), L("Laden", "9.15", "1.250")],
                      [L("Tour", "Uhrzeit", "Stück"), L("Nord", "14.30", "12.345"), L("Süd", "9.15", "1.250")],        # under a heading Uhrzeit, Zeit, Uhr, Datum
                      [L("Tour", "Zeit:", "Stück"), L("Nord", "14.30", "12.345")], [L("Lieferung", "Datum", "Stück"), L("Nord", "12.10", "12.345"), L("Süd", "28.10", "1.250")],
                      [L("Lager", "31.12.", "12.345"), L("Laden", "01.10.26", "1.250"), L("Kasse", "14:30", "2.500")],  # (dates and times that are no amounts anyway)
                      [L("4400.10", "Erlöse", "12.345")], [L("Lager", "12.345"), L("Laden", "1.250")],
                      [L("Lager", "14.30", "12.345,00"), L("Laden", "9.50", "1.250,50")]):                             # amounts with a comma: German, whatever else
            self.assertEqual(P.notation(lines), ",", [ln.text for ln in lines])
        b = doc([("Lieferung Nord", "08.30", "12.345", "2.500"), ("Lieferung Süd", "14.30", "1.250", "500"), ("Abholung", "16.00", "3.000", "1.000")],
                head=("Tour", "Uhrzeit", "Stück", "Kisten"))
        self.assertEqual((b["decimal"], grid(b["sheets"][0])[1:], X.sum_range(b, None, "C1:D4")["sum"]),
                         (",", [["Lieferung Nord", "08.30", "12345", "2500"], ["Lieferung Süd", "14.30", "1250", "500"], ["Abholung", "16.00", "3000", "1000"]], "20595"))
        rows = [("Lieferung Nord", "14.30", "12.345", "2.500"), ("Lieferung Süd", "9.15", "1.250", "500"), ("Abholung", "16.00", "3.000", "1.000")]
        for head, sign, c in ((("Tour", "Uhrzeit", "Stück", "Kisten"), ",", ["12345", "1250", "3000"]), (("Tour", "Datum", "Stück", "Kisten"), ",", ["12345", "1250", "3000"]),
                              (("Tour", "Abfahrt", "Stück", "Kisten"), "?", ["12.345", "1.250", "3.000"])):          # times only by their heading -- or nothing says so
            b = doc(rows, head=head)
            self.assertEqual((b["decimal"], [r[2] for r in grid(b["sheets"][0])[1:]]), (sign, c), head)
        d = Doc()                                             # a statement of values: amounts with cents, a day and a time of day in its lines
        for i, (name, day, time, value) in enumerate((("Depot Nord", "31.12.", "12.40 Uhr", "1.234,56"), ("Depot Süd", "31.12.", "9.50 Uhr", "12.345,00"), ("Festgeld", "30.06.", "17.05 Uhr", "2.500,00"))):
            d.put(40, 60 + 13 * i, name); d.put(200, 60 + 13 * i, day); d.put(260, 60 + 13 * i, time); d.put(500, 60 + 13 * i, value, "r")
        b = P.book(d.layout())
        self.assertEqual((b["decimal"], [r[-1] for r in grid(b["sheets"][0])], X.sum_range(b, None, "A1:F3")["sum"]), (",", ["1234.56", "12345", "2500"], "16079.56"))

    def test_figures_as_written(self):
        F = P.figure
        self.assertEqual([F(t) for t in ("1.234,56", "1.234,56-", "(1.234,56)", "-12,5 %", "1 234,56 EUR", "0,00", "1.234", "4400", "+5")],
                         [("n", "1234.56"), ("n", "-1234.56"), ("n", "-1234.56"), ("p", "-12.5%"), ("n", "1234.56"), ("n", "0"), ("n", "1234"), ("n", "4400"), ("n", "5")])
        self.assertEqual([F(t) for t in ("1.234,56 S", "12,00 H", "31.12.2025", "32.13.2025")], [("m", "1234.56 S"), ("m", "12 H"), ("d", "2025-12-31"), ("t", "32.13.2025")])
        for t in ("0800", "12.34", "1.2.3", "Bank 1", "1,5 kg", "12345678901234567", "DE02 1234", "1.234,56,7", ""):          # not clearly a number: text
            self.assertEqual(F(t)[0], "t", t)
        self.assertEqual([F(t, False) for t in ("1,234.56", "(1,234.56)", "12.34", "1.234,56")], [("n", "1234.56"), ("n", "-1234.56"), ("n", "12.34"), ("t", "1.234,56")])
        self.assertTrue(P.amountlike("1.234,56 S")); self.assertTrue(P.amountlike("EUR 12,00")); self.assertFalse(P.amountlike("Bank 1")); self.assertFalse(P.amountlike("2026"))

    def test_what_the_helper_hands_over_is_checked(self):
        with self.assertRaises(ValueError):
            P.book({"pages": "x"})
        with self.assertRaises(ValueError):
            P.book([])
        junk = {"pages": [None, 5, {"items": "x"}, {"n": "x", "how": "magic", "items": [None, [1, 2], [1, 2, 3, 4, 5], ["a", 2, 3, 4, "t"], [1, 2, 3, 0, "flat"],
                                                                                        [float("nan"), 2, 3, 40, "nan"], [1e12, 2, 3, 40, "far"], [10, 20, 300, 90, "  ok  "],
                                                                                        [10, 20, 300, 90, "x" * 5000]]}], "count": "many", "cut": 1}
        b = P.book(junk)
        self.assertEqual((b["pages"], b["how"], [grid(s) for s in b["sheets"]]), (4, {"none": 4}, [[["ok " + "x" * P.MAX_WORD]]]))
        old = P.MAX_ITEMS
        try:
            P.MAX_ITEMS = 50
            d, _ = statement(pages=2)
            b = P.book(d.layout())
            self.assertTrue(b["cut"]); self.assertEqual(b["pages_read"], 0)
        finally:
            P.MAX_ITEMS = old
        self.assertEqual(P.book({"pages": [], "count": 0})["sheets"], [])


class TightTables(Tables):
    """All of the above once more with the boxes PDFKit gives: every word as high as its own letters."""

    def setUp(self):
        Doc.tight = True

    def tearDown(self):
        Doc.tight = False


@unittest.skipUnless(sys.platform == "darwin" and os.path.exists(R.SANDBOX), "the real helper: on a Mac only")
class OnMac(unittest.TestCase):
    """The helper itself (PDFKit, Vision) on the documents above -- what it finds must give the same tables."""

    def test_pdf_text_with_places(self):
        d, rows = statement()
        lay = R.layout_of(d.pdf(), tempfile.mkdtemp())
        self.assertEqual((lay["count"], lay["cut"], [p["how"] for p in lay["pages"]]), (4, False, ["pdf"] * 4))
        print("first words:", lay["pages"][0]["items"][:6], "letters:", [p.get("letters") for p in lay["pages"]])
        b = P.book(lay)
        g = grid(b["sheets"][0])
        self.assertEqual(X.overview(b), '"pages 1-4" A1:F160', [r for r in g[:8]])
        self.assertEqual([r for r in g if r[0].isdigit()], [as_cells(r) for r in rows])
        self.assertEqual(g[3], ["Konto", "Bezeichnung", "EB-Wert", "Soll", "Haben", "Saldo"])
        d, rows = report()
        g = grid(P.book(R.layout_of(d.pdf(), tempfile.mkdtemp()))["sheets"][0])
        self.assertEqual(g[4:], rows, g[:6])
        # signs standing alone (thin strokes for PDFKit): the accounting format's minus, a column of dashes, a page number
        d = accounting_doc(ACCOUNTING + [("Korrektur", -300.0, 100.0)])
        d.put(270, 800, "Seite 1 von", size=7); d.put(270 + width("Seite 1 von", 7) + 6, 800, "1", size=7)
        lay = R.layout_of(d.pdf(), tempfile.mkdtemp())
        print("signs:", [i for i in lay["pages"][0]["items"] if i[4] in ("-", "1.002,00", "502,00")][:4])
        b = P.book(lay)
        g = grid(b["sheets"][0])
        self.assertEqual(g[:7], [["Position", "Plan", "Ist"], ["Erlöse", "28028", "24028"], ["Erstattung", "1002", "-502"], ["Rücklage", "21006", "-20506"],
                                 ["Miete", "3000", "2900"], ["Zinsen", "410", "-12.5"], ["Korrektur", "-300", "100"]], g)
        self.assertEqual((X.sum_range(b, None, "B2:B7")["sum"], X.sum_range(b, None, "C2:C7")["sum"]), ("53146", "6007.5"))
        d = Doc()
        d.put(40, 60, "Position"); d.put(300, 60, "2025", "r"); d.put(420, 60, "2026", "r")
        for i in range(6):
            d.put(40, 76 + 13 * i, "Posten %d" % i); d.put(294, 76 + 13 * i, "-", "r"); d.put(420, 76 + 13 * i, de(1000.0 + i), "r")
        b = P.book(R.layout_of(d.pdf(), tempfile.mkdtemp()))
        self.assertEqual((grid(b["sheets"][0])[1], X.sum_range(b, None, "C2:C7")["sum"]), (["Posten 0", "-", "1000"], "6015"), grid(b["sheets"][0]))

    def test_picture_by_text_recognition(self):
        d = Doc(1500, 620)                                # large writing: the page as a picture, read by Apple's text recognition
        rows = [("Miete", 1250.0, 15000.0), ("Strom", 189.9, 2278.8), ("Versicherung", 74.25, 891.0), ("Telefon", 39.99, 479.88), ("Summe", 1554.14, 18649.68)]
        d.put(60, 80, "Position", size=36); d.put(900, 80, "Monat", "r", 36); d.put(1400, 80, "Jahr", "r", 36)
        for i, (name, a, b) in enumerate(rows):
            d.put(60, 170 + 90 * i, name, size=36); d.put(900, 170 + 90 * i, de(a), "r", 36); d.put(1400, 170 + 90 * i, de(b), "r", 36)
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, "t.pdf"), "wb") as f:
            f.write(d.pdf())
        subprocess.run(["sips", "-s", "format", "png", os.path.join(folder, "t.pdf"), "--out", os.path.join(folder, "t.png")], check=True, capture_output=True)
        with open(os.path.join(folder, "t.png"), "rb") as f:
            lay = R.layout_of(f.read(), tempfile.mkdtemp())
        self.assertEqual([p["how"] for p in lay["pages"]], ["ocr"])
        b = P.book(lay)
        g = grid(b["sheets"][0])
        print("recognized:", g)
        got = {r[0]: r[1:] for r in g if r and r[0]}
        right = sum(1 for name, a, bb in rows if got.get(name) == [X.plain(X.number("%.2f" % a)), X.plain(X.number("%.2f" % bb))])
        self.assertGreaterEqual(right, 4, g)              # (recognition may misread a letter; the table must stand)


if __name__ == "__main__":
    unittest.main()
