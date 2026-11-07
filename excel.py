"""Minimaler Excel-Schreiber (.xlsx) ohne Abhaengigkeiten.

Unterstuetzt: mehrere Blaetter, Text/Zahlen/Datum (als Text), fette Kopfzeile,
Zahlenformat mit zwei Nachkommastellen, Spaltenbreiten, fixierte Kopfzeile und
erste Spalte. Mehr braucht ein Export aus Kontor nicht.
"""
from __future__ import annotations

import io
import re
import zipfile
from typing import Any, List, Optional, Sequence
from xml.sax.saxutils import escape

_INVALID_SHEET = re.compile(r"[\[\]\*\?/\\:]")


def _col(n: int) -> str:
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Sheet:
    def __init__(self, name: str, header: Sequence[Any], rows: Sequence[Sequence[Any]],
                 widths: Optional[Sequence[float]] = None, freeze: str = "B2", bold_rows: Optional[Sequence[int]] = None):
        self.name = _INVALID_SHEET.sub("-", str(name))[:31] or "Blatt"
        self.header = list(header)
        self.rows = [list(r) for r in rows]
        self.widths = list(widths) if widths else None
        self.freeze = freeze
        self.bold_rows = set(bold_rows or [])

    def xml(self) -> str:
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
        if self.freeze:
            col = re.match(r"([A-Z]+)(\d+)", self.freeze)
            xs = ord(col.group(1)) - 65 if col else 1
            ys = int(col.group(2)) - 1 if col else 1
            out.append('<sheetViews><sheetView workbookViewId="0"><pane xSplit="%d" ySplit="%d" topLeftCell="%s" activePane="bottomRight" state="frozen"/></sheetView></sheetViews>'
                       % (xs, ys, self.freeze))
        ncols = max([len(self.header)] + [len(r) for r in self.rows]) if (self.header or self.rows) else 1
        widths = self.widths or ([34] + [14] * (ncols - 1))
        out.append("<cols>" + "".join('<col min="%d" max="%d" width="%.1f" customWidth="1"/>' % (i + 1, i + 1, w)
                                      for i, w in enumerate(widths[:ncols])) + "</cols>")
        out.append("<sheetData>")
        out.append(self._row(1, self.header, bold=True))
        for i, r in enumerate(self.rows, start=2):
            out.append(self._row(i, r, bold=(i - 2) in self.bold_rows))
        out.append("</sheetData></worksheet>")
        return "".join(out)

    @staticmethod
    def _row(idx: int, values: Sequence[Any], bold: bool) -> str:
        cells = []
        for j, v in enumerate(values):
            ref = "%s%d" % (_col(j), idx)
            if v is None or v == "":
                continue
            if isinstance(v, bool):
                v = "ja" if v else "nein"
            if isinstance(v, (int, float)):
                style = 3 if bold else 1
                cells.append('<c r="%s" s="%d"><v>%s</v></c>' % (ref, style, repr(float(v)) if isinstance(v, float) else v))
            else:
                style = 2 if bold else 0
                cells.append('<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, style, escape(str(v))))
        return '<row r="%d">%s</row>' % (idx, "".join(cells))


def workbook(sheets: List[Sheet]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1)
                             for i in range(len(sheets))) + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets>' + "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(s.name, {'"': "&quot;"}), i + 1, i + 1)
                                        for i, s in enumerate(sheets)) + '</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1)
                             for i in range(len(sheets)))
                   + '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>' % (len(sheets) + 1))
        z.writestr("xl/styles.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00;[Red]-#,##0.00"/></numFmts>'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                   '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                   '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                   '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                   '<cellXfs count="4">'
                   '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                   '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
                   '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
                   '<xf numFmtId="164" fontId="1" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"/>'
                   '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        for i, s in enumerate(sheets):
            z.writestr("xl/worksheets/sheet%d.xml" % (i + 1), s.xml())
    return buf.getvalue()
