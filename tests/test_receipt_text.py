"""Reading a receipt (receipt_text.py): what its text says, by fixed rules, and which transaction it belongs to -- on made-up
receipts; the text recognition itself runs only on a Mac (its sandbox and limits are checked here as far as Linux allows)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import receipt_text as R          # noqa: E402

RECEIPT = """Baumarkt Beispiel GmbH
Musterweg 1, 12345 Beispielstadt
Rechnung Nr. 4711 vom 03.10.2026
Schrauben              12,99 €
Werkzeugkoffer        102,00 €
Zwischensumme         114,99
MwSt 19 %              18,36
Gesamtbetrag          114,99 EUR
Bitte überweisen an DE02 1203 0000 0000 2020 51
"""


class Fields(unittest.TestCase):
    def test_total_dates_iban_issuer(self):
        f = R.read_fields(RECEIPT)
        self.assertEqual(f["total"], 114.99)
        self.assertEqual(f["dates"], ["2026-10-03"])
        self.assertEqual(f["ibans"], ["DE02120300000000202051"])
        self.assertEqual(f["issuer"], "Baumarkt Beispiel GmbH")
        self.assertIn(102.0, f["amounts"])

    def test_formats_and_nothing_made_up(self):
        self.assertEqual(R.read_fields("Total 1,234.50\n2026-09-30")["total"], 1234.5)
        self.assertEqual(R.read_fields("Summe 1.234,50 €")["total"], 1234.5)
        self.assertEqual(R.read_fields("Betrag: 7,00\nam 1.2.26")["dates"], ["2026-02-01"])
        self.assertEqual(R.read_fields(""), {})
        self.assertNotIn("ibans", R.read_fields("DE02 1001 0010 0006 8201 02"))      # wrong check digits: no IBAN
        self.assertNotIn("dates", R.read_fields("31.02.2026"))                      # no such day
        self.assertEqual(R.read_fields("Artikel 3,00\nArtikel 9,50")["total"], 9.5)  # no line names it: the largest


class Candidates(unittest.TestCase):
    TXS = [{"id": 1, "date": "2026-10-04", "amount": -114.99, "name": "BAUMARKT BEISPIEL", "purpose": "Karte"},
           {"id": 2, "date": "2026-10-04", "amount": -114.99, "name": "Tankstelle", "purpose": ""},
           {"id": 3, "date": "2026-07-01", "amount": -114.99, "name": "Baumarkt Beispiel", "purpose": ""},
           {"id": 4, "date": "2026-10-20", "amount": -116.00, "name": "Baumarkt Beispiel", "purpose": ""},
           {"id": 5, "date": "2026-10-03", "amount": -50.00, "name": "Andere", "purpose": "", "counter_iban": "DE02120300000000202051"}]

    def test_ranked_with_differences(self):
        got = R.candidates(R.read_fields(RECEIPT), self.TXS)
        self.assertEqual([c["tx"]["id"] for c in got], [1, 2, 5, 4])                # amount, date and name; IBAN alone; close amount
        self.assertEqual(got[0]["differences"], [])
        self.assertEqual(next(c for c in got if c["tx"]["id"] == 4)["differences"], [{"what": "amount", "by": 1.01}, {"what": "date", "days": 17}])
        self.assertNotIn(3, [c["tx"]["id"] for c in got])                           # three months off: not offered
        # as the user says it (another amount, a day): those count
        self.assertEqual([c["tx"]["id"] for c in R.candidates({}, self.TXS, amount=50, day="2026-10-03")], [5])
        self.assertEqual(R.candidates({}, self.TXS), [])                            # nothing to go by: nothing offered


class Recognition(unittest.TestCase):
    def test_only_on_a_mac_and_sealed(self):
        with mock.patch.object(R.sys, "platform", "linux"):
            with self.assertRaises(R.TextUnavailable):
                R.text_of(b"%PDF-1.4", "/tmp/data")
        with self.assertRaises(ValueError):
            R.text_of(b"", "/tmp/data")
        p = R._profile("/Users/x", "/Users/x/Library/Application Support/Kontor", "/private/var/folders/ab/cd/T/rcpt-1")
        for rule in ("(deny network*)", "(deny process-exec*)", "(deny appleevent-send)", "(deny file-write*)", "(deny lsopen)"):
            self.assertIn(rule, p)
        self.assertIn('(deny file-read* (subpath "/Users/x")', p)
        # writes: its own folder of the run only (and the system caches) -- the rule against Kontor's folders comes last, so it wins
        self.assertIn('(allow file-write* (subpath "/private/var/folders/ab/cd/T/rcpt-1")', p)
        self.assertNotIn('(subpath "/private/tmp")', p); self.assertNotIn('(allow file-write* (subpath "/private/var/folders")', p)
        self.assertGreater(p.index('(deny file-write* (regex #"/kontor-'), p.index("(allow file-write*"))

    def test_dates_in_words_amounts_and_the_newest_first(self):
        f = R.read_fields("Händler\n1 150,00 150,00\nRechnung vom 3. Oktober 2026\nGesamt 150,00 €")
        self.assertEqual((f["total"], f["amounts"], f["dates"]), (150.0, [150.0], ["2026-10-03"]))       # a quantity before a price is no thousand
        self.assertEqual(R.read_fields("Invoice October 3, 2026")["dates"], ["2026-10-03"])
        self.assertEqual(R.read_fields("Datum 03/10/2026")["dates"], ["2026-10-03"])
        self.assertEqual(R.read_fields("Summe 1\u202f150,00")["total"], 1150.0)
        subs = [{"id": i, "date": "%d-%02d-15" % (y, m), "amount": -12.99, "name": "Abo", "purpose": ""} for i, (y, m) in enumerate((y, m) for y in (2024, 2025, 2026) for m in range(1, 13))]
        got = R.candidates({"total": 12.99}, subs)
        self.assertEqual([c["tx"]["date"] for c in got][:2], ["2026-12-15", "2026-11-15"])        # alike: the newest first
        got = R.candidates(R.read_fields("Abo\n3. Oktober 2026\nSumme 12,99"), subs)
        self.assertEqual(got[0]["tx"]["date"], "2026-10-15")

    def test_what_the_helper_returns_is_checked(self):
        with mock.patch.object(R.sys, "platform", "darwin"), mock.patch.object(R, "_helper", return_value="/x/receipt_ocr"):
            for out, ok in ((b'{"text": "Summe 5,00", "how": "pdf"}', True), (b'{"text": 5, "how": "pdf"}', False), (b"not json", False),
                            (b'{"text": "x", "how": "magic"}', False)):
                with mock.patch.object(R.subprocess, "run", return_value=mock.Mock(returncode=0, stdout=out)) as run:
                    if ok:
                        self.assertEqual(R.text_of(b"%PDF", "/d"), {"text": "Summe 5,00", "how": "pdf"})
                        cmd = run.call_args[0][0]
                        self.assertEqual(cmd[:2], [R.SANDBOX, "-p"]); self.assertEqual(run.call_args[1]["env"]["PATH"], "/usr/bin:/bin")
                        work = run.call_args[1]["cwd"]          # its own folder of the run, gone afterwards
                        self.assertEqual(run.call_args[1]["env"]["TMPDIR"], work); self.assertIn("/rcpt-", work); self.assertFalse(R.os.path.exists(work))
                    else:
                        with self.assertRaises(R.TextUnavailable):
                            R.text_of(b"%PDF", "/d")
            with mock.patch.object(R.subprocess, "run", side_effect=R.subprocess.TimeoutExpired("x", 1)):
                with self.assertRaises(R.TextUnavailable):
                    R.text_of(b"%PDF", "/d")


if __name__ == "__main__":
    unittest.main()
