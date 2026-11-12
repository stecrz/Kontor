"""The repository is public: no personal data in any file (names, accounts, IBANs, amounts, paths). What a machine can check:
no IBANs, e-mail addresses or home folders outside the made-up test data -- and there only the sample IBANs from banks'
documentation, example addresses and placeholder folders."""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# public sample IBANs from banks' documentation (some with a changed last digit for a second account) -- add one here only
# if it is such a sample, never a real account
SAMPLE_IBANS = {"DE02100100100006820101", "DE02100100100006820102", "DE02100500000054540402", "DE02120300000000202051",
                "DE02300209000106531065", "DE02500105170137075030", "DE02500105170137075031", "DE02500105170137075032",
                "DE02701500000000594937", "DE02701500000000594938"}
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[0-9A-Z]{12,30}|(?: [0-9A-Z]{4}){3,7}(?: [0-9A-Z]{1,3})?)\b")
MAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
HOME = re.compile(r"/Users/(?!x\b|<)[A-Za-z][\w.-]*")
BINARY = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".pdf", ".zip", ".xlsx", ".woff", ".woff2")


def files():
    try:
        out = subprocess.run(["git", "-C", ROOT, "ls-files", "-co", "--exclude-standard"], capture_output=True, text=True, check=True).stdout
        names = [n for n in out.splitlines() if n]
    except (OSError, subprocess.CalledProcessError):
        names = [os.path.relpath(os.path.join(r, f), ROOT) for r, _, fs in os.walk(ROOT) if "/." not in r for f in fs]
    return [n for n in names if not n.lower().endswith(BINARY) and os.path.isfile(os.path.join(ROOT, n))]


class PrivacyTests(unittest.TestCase):
    def test_no_personal_data_in_the_repository(self):
        found = []
        for name in files():
            try:
                text = open(os.path.join(ROOT, name), encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            in_tests = name.startswith("tests/")
            for m in IBAN.finditer(text):
                iban = m.group(0).replace(" ", "")
                if not (in_tests and iban in SAMPLE_IBANS):
                    found.append("%s: IBAN %s…" % (name, iban[:6]))
            for m in MAIL.finditer(text):
                domain = m.group(0).rsplit("@", 1)[1].lower()
                if domain not in ("example.com", "example.org", "example.net"):
                    found.append("%s: e-mail address @%s" % (name, domain))
            for m in HOME.finditer(text):
                found.append("%s: home folder %s" % (name, m.group(0)[:12]))
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
