"""Real-life scenarios across three areas -- you privately, your holding company and a partnership: contributions with and
without capital accounts, a company bought partly on a seller's loan, bank loans, loans between you, your companies and a
friend, bills booked when due and paid later, money laid out for the partnership, dividends, transfers -- each on one day,
with the money arriving days later, over a month end and over a year end, and all of them mixed at random.

For every one: each month of every area adds up (net worth and cash; the only reason allowed is money in transit over a
month end), the net worth of each area moves by exactly what happened, and the money shows in the row where it belongs --
a payment booked against a manual account goes into that account, never as a change in value."""
import datetime
import os
import random
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from model import Ledger, accounts_from_export, tx_from_export   # noqa: E402
import core                                                         # noqa: E402
import report                                                       # noqa: E402
import fixtures as F                                                # noqa: E402

TODAY = date(2026, 6, 20)
AREAS = ("Privat", "Holding GmbH", "Muster GbR")
# key: (name, area, position, IBAN, kind) -- kind: "bank" (fetched from a bank) or "offline" (kept by hand)
ACCOUNTS = {
    "giro": ("Giro", "Privat", "cash", "DE11", "bank"),
    "tg": ("Tagesgeld", "Privat", "cash", "DE12", "bank"),
    "baufi": ("Baufinanzierung", "Privat", "liabilities", "DE13", "bank"),
    "kap_gbr": ("Kapitalkonto Muster GbR", "Privat", "participations", None, "offline"),
    "bet_gmbh": ("Beteiligung Holding GmbH", "Privat", "participations", None, "offline"),
    "dar_gmbh": ("Darlehen an Holding GmbH", "Privat", "receivables", None, "offline"),
    "dar_freund": ("Darlehen von Freund", "Privat", "liabilities", None, "offline"),
    "dar_an_fr": ("Darlehen an Freund", "Privat", "receivables", None, "offline"),
    "ausl": ("Forderung Auslagen", "Privat", "receivables", None, "offline"),
    "werkst": ("Verbindlichkeit Werkstatt", "Privat", "liabilities", None, "offline"),
    "immo": ("Wohnung", "Privat", "real_estate", None, "offline"),
    "h_kk": ("Holding Konto", "Holding GmbH", "cash", "DE21", "bank"),
    "h_vd": ("Verkäuferdarlehen", "Holding GmbH", "liabilities", None, "offline"),
    "h_bet": ("Beteiligung Ziel GmbH", "Holding GmbH", "participations", None, "offline"),
    "h_gd": ("Gesellschafterdarlehen", "Holding GmbH", "liabilities", None, "offline"),
    "h_dar_gbr": ("Darlehen an Muster GbR", "Holding GmbH", "receivables", None, "offline"),
    "g_kk": ("GbR Konto", "Muster GbR", "cash", "DE31", "bank"),
    "g_kap": ("Kapitalkonto Gesellschafter", "Muster GbR", "liabilities", None, "offline"),
    "g_dar": ("Darlehen Sparkasse", "Muster GbR", "liabilities", "DE33", "bank"),
    "g_dar_h": ("Darlehen Holding GmbH", "Muster GbR", "liabilities", None, "offline"),
    "kredit_gbr": ("Kredit von Muster GbR", "Privat", "liabilities", None, "offline"),
    "g_dar_priv": ("Darlehen an Gesellschafter", "Muster GbR", "receivables", None, "offline"),
    "bet_gbr": ("Beteiligung Muster GbR", "Privat", "participations", None, "offline"),
}
ROLES = {k: v[2] for k, v in ACCOUNTS.items()}
NAME = {k: v[0] for k, v in ACCOUNTS.items()}
# money there before the scenarios start (November)
START = [(1, "giro", date(2025, 11, 3), 50000.0, {"cat": "Gehalt"}),
         (2, "h_kk", date(2025, 11, 3), 200000.0, {"iban": "DE95", "name": "Altgesellschafter", "cat": "Umbuchung"}),
         (3, "g_kk", date(2025, 11, 3), 30000.0, {"cat": "Miete", "name": "Mieter"})]
# where the scenarios begin: the same day, two days later, over a month end, over a year end (paid, arrived days later)
VARIANTS = {"same_day": (date(2026, 2, 10), 0), "two_days": (date(2026, 2, 10), 2), "month_end": (date(2026, 1, 30), 3),
            "year_end": (date(2025, 12, 30), 3)}


def ledger(txs):
    raw = []
    for area in AREAS:
        raw.append({"uuid": "g-" + area, "name": area, "indentation": 0, "type": "Kontengruppe", "group": True, "balance": [[0, "EUR"]], "currency": "EUR"})
        for k, (name, a, role, iban, kind) in ACCOUNTS.items():
            if a != area:
                continue
            bal = round(sum(e[3] for e in txs if e[1] == k), 2)
            raw.append({"uuid": k, "name": name, "indentation": 1, "type": "Offline-Konto" if kind == "offline" else "Girokonto", "group": False,
                        "balance": [[bal, "EUR"]], "currency": "EUR", "iban": iban, "accountNumber": iban or "",
                        "bankCode": "" if kind == "offline" else "10000000", "portfolio": False,
                        "refreshTimestamp": None if kind == "offline" else datetime.datetime(2026, 6, 1)})
    rows = []
    for i, k, day, amount, extra in txs:
        extra = dict(extra or {})
        rows.append({"id": i, "accountUuid": k, "bookingDate": datetime.datetime(day.year, day.month, day.day, 12), "amount": round(amount, 2),
                     "currency": "EUR", "name": extra.pop("name", "x"), "purpose": extra.pop("purpose", ""), "categoryPath": extra.pop("cat", ""),
                     "accountNumber": extra.pop("iban", ""), "booked": True, "comment": ""})
    return Ledger(accounts_from_export(raw), tx_from_export(rows))


def run(txs, cfg=None):
    config = core.merged_config(dict({"balance": {"roles": dict(ROLES)}}, **(cfg or {})))
    led = ledger(txs)
    return {b["name"]: report.build_dataset(led, config, {}, TODAY, b, dict(ROLES)) for b in core.bereiche_for(led, config)}


def mk(d):
    return "%04d-%02d" % (d.year, d.month)


def month_end(d):
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


# ---------------------------------------------------------------------------------------------------------------------------
# The scenarios: each (d: the day paid, lag: days until it arrives in the other area, k: a factor on all amounts, i: first id)
# returns the bookings, settings, the net worth change of each area over the whole time, the rows (area, section, row:
# total over all months, counts in the net worth) and the accounts that must show no change in value.
# ---------------------------------------------------------------------------------------------------------------------------
class Sc:
    def __init__(self, txs, cfg=None, nw=None, rows=(), no_value=(), non_cash=(), due_month_nw=None):
        self.txs, self.cfg, self.nw, self.rows, self.no_value, self.non_cash = txs, cfg or {}, nw or {}, list(rows), list(no_value), list(non_cash)
        self.due_month_nw = due_month_nw


def contribution_gmbh_with_stake(d, lag, k, i):
    """Capital put into your GmbH, your stake booked by you at its cost: your net worth stays, the company's grows."""
    x = 20000 * k
    return Sc([(i, "giro", d, -x, {"iban": "DE21", "cat": "Umbuchung", "purpose": "Kapitalrücklage"}), (i + 1, "bet_gmbh", d, x, {"purpose": "Einlage Kapitalrücklage"}),
               (i + 2, "h_kk", d + timedelta(lag), x, {"iban": "DE11", "purpose": "Kapitalrücklage"})],
              nw={"Privat": 0, "Holding GmbH": x},
              rows=[("Privat", "investing", "Einlage/Entnahme Holding GmbH / Beteiligung Holding GmbH", -x, False),
                    ("Holding GmbH", "financing", "Einlagen/Entnahmen Gesellschafter", x, True)],
              no_value=[("Privat", "bet_gmbh")])


def contribution_gmbh_without_stake(d, lag, k, i):
    """Share capital paid in, nothing booked at home: it leaves your net worth (you keep no account of it), the company's grows."""
    x = 25000 * k
    return Sc([(i, "giro", d, -x, {"iban": "DE21", "purpose": "Stammkapital"}), (i + 1, "h_kk", d + timedelta(lag), x, {"iban": "DE11", "purpose": "Stammkapital"})],
              nw={"Privat": -x, "Holding GmbH": x},
              rows=[("Privat", "investing", "Einlage/Entnahme Holding GmbH", -x, True), ("Holding GmbH", "financing", "Einlagen/Entnahmen Gesellschafter", x, True)])


def shareholder_loan(d, lag, k, i):
    """You lend your GmbH money (both sides kept by hand), a third comes back six weeks later: nobody's net worth moves."""
    x, r, d2 = 15000 * k, 5000 * k, d + timedelta(42)
    return Sc([(i, "giro", d, -x, {"iban": "DE21"}), (i + 1, "dar_gmbh", d, x, {"purpose": "Darlehen"}),
               (i + 2, "h_kk", d + timedelta(lag), x, {"iban": "DE11"}), (i + 3, "h_gd", d + timedelta(lag), -x, {"purpose": "Darlehen Gesellschafter"}),
               (i + 4, "h_kk", d2, -r, {"iban": "DE11"}), (i + 5, "h_gd", d2, r, {"purpose": "Rückzahlung"}),
               (i + 6, "giro", d2 + timedelta(lag), r, {"iban": "DE21"}), (i + 7, "dar_gmbh", d2 + timedelta(lag), -r, {"purpose": "Rückzahlung"})],
              nw={"Privat": 0, "Holding GmbH": 0},
              rows=[("Privat", "investing", "Einlage/Entnahme Holding GmbH / Darlehen an Holding GmbH", -x + r, False),
                    ("Holding GmbH", "financing", "Einlage/Entnahme Privat / Gesellschafterdarlehen", x - r, False)],
              no_value=[("Privat", "dar_gmbh"), ("Holding GmbH", "h_gd")])


def partnership_contribution(d, lag, k, i, mirrored=False):
    """Paid into the partnership and booked on both capital accounts -- each on the day of its bank, or (mirrored) both on the day
    you paid: in neither area a change of net worth or of value."""
    x = 10000 * k
    later = d if mirrored else d + timedelta(lag)
    cfg = {"account_mirrors": [{"a": "Kapitalkonto Muster GbR", "b": "Kapitalkonto Gesellschafter", "from_date": "all"}]} if mirrored else {}
    return Sc([(i, "giro", d, -x, {"iban": "DE31", "cat": "Umbuchung"}), (i + 1, "kap_gbr", d, x, {"purpose": "Einlage"}),
               (i + 2, "g_kk", d + timedelta(lag), x, {"iban": "DE11"}),
               (i + 3, "g_kap", later, -x, {"purpose": "Einlage" + (" · gespiegelt von Kapitalkonto Muster GbR · #kontor-gk-%d" % (i + 1) if mirrored else "")})], cfg,
              nw={"Privat": 0, "Muster GbR": 0},
              rows=[("Privat", "investing", "Einlage/Entnahme Muster GbR / Kapitalkonto Muster GbR", -x, False),
                    ("Muster GbR", "financing", "Einlage/Entnahme Privat / Kapitalkonto Gesellschafter", x, False)],
              no_value=[("Privat", "kap_gbr"), ("Muster GbR", "g_kap")])


def partnership_contribution_mirrored(d, lag, k, i):
    return partnership_contribution(d, lag, k, i, mirrored=True)


def partnership_withdrawal(d, lag, k, i):
    """Taken out of the partnership, booked on both capital accounts: as a contribution, the other way round."""
    x = 4000 * k
    return Sc([(i, "g_kk", d, -x, {"iban": "DE11"}), (i + 1, "g_kap", d, x, {"purpose": "Entnahme"}),
               (i + 2, "giro", d + timedelta(lag), x, {"iban": "DE31"}), (i + 3, "kap_gbr", d + timedelta(lag), -x, {"purpose": "Entnahme"})],
              nw={"Privat": 0, "Muster GbR": 0},
              rows=[("Privat", "investing", "Einlage/Entnahme Muster GbR / Kapitalkonto Muster GbR", x, False),
                    ("Muster GbR", "financing", "Einlage/Entnahme Privat / Kapitalkonto Gesellschafter", -x, False)],
              no_value=[("Privat", "kap_gbr"), ("Muster GbR", "g_kap")])


def company_bought_on_seller_loan(d, lag, k, i):
    """The holding buys a company: part paid, the rest owed to the seller (no money moves for it); a month later the first rate,
    split by the loan rule into repayment and interest. The purchase moves no net worth; only the interest does."""
    paid, owed, rate, interest = 60000 * k, 40000 * k, 1500 * k, 300 * k
    d2 = d + timedelta(31)
    return Sc([(i, "h_kk", d, -paid, {"iban": "DE90", "name": "Verkäufer", "purpose": "Kaufpreis"}), (i + 1, "h_bet", d, paid, {"purpose": "Kaufpreis bar"}),
               (i + 2, "h_bet", d, owed, {"purpose": "Kaufpreis Verkäuferdarlehen"}), (i + 3, "h_vd", d, -owed, {"purpose": "Verkäuferdarlehen"}),
               (i + 4, "h_kk", d2, -rate, {"iban": "DE90", "name": "Verkäufer", "purpose": "Rate"}),
               (i + 5, "h_vd", d2, rate, {"purpose": "Annuität · #kontor-tx-%d" % (i + 4)}),
               (i + 6, "h_vd", month_end(d2), -interest, {"purpose": "Zinsen · #kontor-zins-%d" % (i + 6)})],
              nw={"Holding GmbH": -interest},
              rows=[("Holding GmbH", "investing", "Beteiligung Ziel GmbH", -paid, False),
                    ("Holding GmbH", "financing", "Verkäuferdarlehen / Tilgung", -(rate - interest), False),
                    ("Holding GmbH", "financing", "Verkäuferdarlehen / Zinsen", -interest, True)],
              non_cash=[("Holding GmbH", ("h_bet", "h_vd"))])


def bank_loan_for_a_flat(d, lag, k, i):
    """A bank loan paid out to your account, the flat bought with it (saving into the flat), a rate and the bank's interest."""
    x, rate, interest = 200000 * k, 900 * k, 500 * k
    d1, d2 = d + timedelta(lag), d + timedelta(20)
    return Sc([(i, "baufi", d, -x, {"iban": "DE11", "purpose": "Auszahlung"}), (i + 1, "giro", d1, x, {"iban": "DE13"}),
               (i + 2, "giro", d1, -x, {"iban": "DE91", "name": "Notar", "cat": "Immobilienkauf"}), (i + 3, "immo", d1, x, {"purpose": "Kauf"}),
               (i + 4, "giro", d2, -rate, {"iban": "DE13", "purpose": "Rate"}), (i + 5, "baufi", d2 + timedelta(lag), rate, {"iban": "DE11", "purpose": "Rate"}),
               (i + 6, "baufi", month_end(d2 + timedelta(lag)), -interest, {"purpose": "Sollzinsen"})],
              {"cashflow": {"positions": {"Immobilienkauf": "saving"}}},
              nw={"Privat": -interest},
              rows=[("Privat", "financing", "Baufinanzierung / Aufnahme", x, False), ("Privat", "investing", "Wohnung", -x, False),
                    ("Privat", "financing", "Baufinanzierung / Tilgung", -(rate - interest), False), ("Privat", "financing", "Baufinanzierung / Zinsen", -interest, True)],
              no_value=[("Privat", "immo")])


def loan_paid_to_the_notary(d, lag, k, i):
    """The bank pays the loan straight to the notary: no money of yours moves -- the flat and the debt rise together."""
    x = 150000 * k
    return Sc([(i, "baufi", d, -x, {"iban": "DE91", "name": "Notar"}), (i + 1, "immo", d, x, {"purpose": "Kaufpreis"})],
              nw={"Privat": 0}, non_cash=[("Privat", ("baufi", "immo"))])


def partnership_bank_loan(d, lag, k, i):
    """The partnership takes a bank loan, pays a rate a month later; the bank charges interest at the month end."""
    x, rate, interest = 100000 * k, 1000 * k, 250 * k
    d2 = d + timedelta(30)
    return Sc([(i, "g_dar", d, -x, {"iban": "DE31", "purpose": "Auszahlung"}), (i + 1, "g_kk", d + timedelta(lag), x, {"iban": "DE33"}),
               (i + 2, "g_kk", d2, -rate, {"iban": "DE33"}), (i + 3, "g_dar", d2 + timedelta(lag), rate, {"iban": "DE31"}),
               (i + 4, "g_dar", month_end(d2 + timedelta(lag)), -interest, {"purpose": "Zinsen"})],
              nw={"Muster GbR": -interest},
              rows=[("Muster GbR", "financing", "Darlehen Sparkasse / Aufnahme", x, False),
                    ("Muster GbR", "financing", "Darlehen Sparkasse / Zinsen", -interest, True)])


def loan_from_a_friend(d, lag, k, i):
    """A friend lends you money (kept by hand), a month later you pay part back."""
    x, r = 5000 * k, 1000 * k
    return Sc([(i, "giro", d, x, {"iban": "DE92", "name": "Freund"}), (i + 1, "dar_freund", d, -x, {"purpose": "Darlehen"}),
               (i + 2, "giro", d + timedelta(30), -r, {"iban": "DE92", "name": "Freund"}), (i + 3, "dar_freund", d + timedelta(30), r, {"purpose": "Rückzahlung"})],
              nw={"Privat": 0},
              rows=[("Privat", "financing", "Darlehen von Freund / Aufnahme", x, False), ("Privat", "financing", "Darlehen von Freund / Tilgung", -r, False)],
              no_value=[("Privat", "dar_freund")])


def loan_to_a_friend(d, lag, k, i):
    """You lend a friend money; interest is added to it; he pays it back with the interest."""
    x, interest = 3000 * k, 50 * k
    d2, d3 = d + timedelta(30), d + timedelta(45)
    return Sc([(i, "giro", d, -x, {"iban": "DE92", "name": "Freund"}), (i + 1, "dar_an_fr", d, x, {}),
               (i + 2, "dar_an_fr", month_end(d2), interest, {"purpose": "Zinsen"}),
               (i + 3, "giro", d3, x + interest, {"iban": "DE92", "name": "Freund"}), (i + 4, "dar_an_fr", d3, -(x + interest), {"purpose": "Rückzahlung"})],
              nw={"Privat": interest},
              rows=[("Privat", "investing", "Darlehen an Freund / Zinsen", interest, True)])


def bill_booked_when_due(d, lag, k, i):
    """A repair bill booked when it is due (you owe it: a liability), paid weeks later: the cost counts when due, under its
    category (a category counts in every account), the debt taken up then; the payment only pays the debt."""
    x = 800 * k
    d2 = d + timedelta(25)
    return Sc([(i, "werkst", d, -x, {"purpose": "Rechnung Reparatur", "cat": "Auto"}),
               (i + 1, "giro", d2, -x, {"iban": "DE93", "name": "Werkstatt"}), (i + 2, "werkst", d2, x, {"purpose": "bezahlt"})],
              nw={"Privat": -x}, due_month_nw=("Privat", d, -x),
              rows=[("Privat", "financing", "Verbindlichkeit Werkstatt / Tilgung", -x, False),
                    ("Privat", "financing", "Verbindlichkeit Werkstatt / Aufnahme", x, False), ("Privat", "expenses", "Mobilität", -x, True)])


def laid_out_for_the_partnership(d, lag, k, i):
    """You pay a bill of the partnership (a claim on it, kept by hand); it pays you back, as a cost of its own: your net worth
    stays, the partnership bears the cost."""
    x = 300 * k
    d2 = d + timedelta(20)
    return Sc([(i, "giro", d, -x, {"iban": "DE94", "name": "Baumarkt"}), (i + 1, "ausl", d, x, {"purpose": "Auslage Muster GbR"}),
               (i + 2, "g_kk", d2, -x, {"iban": "DE11", "cat": "Instandhaltung", "purpose": "Erstattung Auslage"}),
               (i + 3, "giro", d2 + timedelta(lag), x, {"iban": "DE31"}), (i + 4, "ausl", d2 + timedelta(lag), -x, {"purpose": "erstattet Muster GbR"})],
              nw={"Privat": 0, "Muster GbR": -x},
              rows=[("Privat", "investing", "@ausl", 0, False), ("Privat", "investing", "Einlage/Entnahme Muster GbR / Forderung Auslagen", x, False)],
              no_value=[("Privat", "ausl")])


def holding_lends_to_the_partnership(d, lag, k, i):
    """One company of yours lends the other money, both kept by hand: a loan granted on one side, a loan taken on the other."""
    x = 25000 * k
    return Sc([(i, "h_kk", d, -x, {"iban": "DE31"}), (i + 1, "h_dar_gbr", d, x, {"purpose": "Darlehen Muster GbR"}),
               (i + 2, "g_kk", d + timedelta(lag), x, {"iban": "DE21"}), (i + 3, "g_dar_h", d + timedelta(lag), -x, {"purpose": "Darlehen Holding GmbH"})],
              nw={"Holding GmbH": 0, "Muster GbR": 0},
              rows=[("Holding GmbH", "investing", "Einlage/Entnahme Muster GbR / Darlehen an Muster GbR", -x, False),
                    ("Muster GbR", "financing", "Einlage/Entnahme Holding GmbH / Darlehen Holding GmbH", x, False)],
              no_value=[("Holding GmbH", "h_dar_gbr"), ("Muster GbR", "g_dar_h")])


def dividend(d, lag, k, i):
    """The GmbH pays you a dividend: income for you, a withdrawal for the company."""
    x = 8000 * k
    return Sc([(i, "h_kk", d, -x, {"iban": "DE11", "purpose": "Gewinnausschüttung"}), (i + 1, "giro", d + timedelta(lag), x, {"iban": "DE21", "cat": "Dividenden"})],
              nw={"Privat": x, "Holding GmbH": -x},
              rows=[("Privat", "income", "Kapitalerträge", x, True), ("Holding GmbH", "financing", "Einlagen/Entnahmen Gesellschafter", -x, True)])


def transfer_to_savings(d, lag, k, i):
    """From the current account to the savings account: nothing changes, over a month end the money is in transit."""
    x = 5000 * k
    return Sc([(i, "giro", d, -x, {"iban": "DE12"}), (i + 1, "tg", d + timedelta(lag), x, {"iban": "DE11"})], nw={"Privat": 0})


def contribution_with_participation_rule(d, lag, k, i):
    """Capital paid in while Kontor keeps the participation at its share of the company (here: worth less than paid)."""
    x, worth = 25000 * k, 12000 * k
    e = month_end(d + timedelta(lag))
    return Sc([(i, "giro", d, -x, {"iban": "DE21"}), (i + 1, "h_kk", d + timedelta(lag), x, {"iban": "DE11"}),
               (i + 2, "bet_gmbh", e, worth, {"purpose": "Wertanpassung · #kontor-wert-%s-1" % e.strftime("%Y%m%d")})],
              {"companies": [{"area": "Holding GmbH", "participation": "Beteiligung Holding GmbH"}]},
              nw={"Privat": worth - x, "Holding GmbH": x},
              rows=[("Privat", "investing", "Einlage/Entnahme Holding GmbH", -x, False)])


def loan_from_your_partnership(d, lag, k, i):
    """The partnership lends you money (a loan to its partner on its side, a liability on yours), you pay part back later:
    taken up and repaid apart -- never a negative loan taken up; nobody's net worth moves."""
    x, r, d2 = 10000 * k, 2000 * k, d + timedelta(60)
    return Sc([(i, "g_kk", d, -x, {"iban": "DE11"}), (i + 1, "g_dar_priv", d, x, {"purpose": "Darlehen an Gesellschafter"}),
               (i + 2, "giro", d + timedelta(lag), x, {"iban": "DE31"}), (i + 3, "kredit_gbr", d + timedelta(lag), -x, {"purpose": "Kredit Muster GbR"}),
               (i + 4, "giro", d2, -r, {"iban": "DE31"}), (i + 5, "kredit_gbr", d2, r, {"purpose": "Rückzahlung Muster GbR"}),
               (i + 6, "g_kk", d2 + timedelta(lag), r, {"iban": "DE11"}), (i + 7, "g_dar_priv", d2 + timedelta(lag), -r, {"purpose": "Rückzahlung"})],
              nw={"Privat": 0, "Muster GbR": 0},
              rows=[("Privat", "financing", "Einlage/Entnahme Muster GbR / Kredit von Muster GbR / Aufnahme", x, False),
                    ("Privat", "financing", "Einlage/Entnahme Muster GbR / Kredit von Muster GbR / Tilgung", -r, False),
                    ("Muster GbR", "investing", "Einlage/Entnahme Privat / Darlehen an Gesellschafter", -x + r, False)],
              no_value=[("Privat", "kredit_gbr"), ("Muster GbR", "g_dar_priv")])


def participation_rule_and_capital_account(d, lag, k, i):
    """As the help recommends: Kontor keeps the participation at its share, your capital account mirrors the partnership's.
    A contribution goes into the capital account (the partnership's value does not change by it: its capital account is a debt)."""
    x = 7000 * k
    return Sc([(i, "giro", d, -x, {"iban": "DE31"}), (i + 1, "kap_gbr", d, x, {"purpose": "Einlage"}),
               (i + 2, "g_kk", d + timedelta(lag), x, {"iban": "DE11"}),
               (i + 3, "g_kap", d, -x, {"purpose": "Einlage · gespiegelt von Kapitalkonto Muster GbR · #kontor-gk-%d" % (i + 1)})],
              {"companies": [{"area": "Muster GbR", "participation": "Beteiligung Muster GbR"}],
               "account_mirrors": [{"a": "Kapitalkonto Muster GbR", "b": "Kapitalkonto Gesellschafter", "from_date": "all"}]},
              nw={"Privat": 0, "Muster GbR": 0},
              rows=[("Privat", "investing", "Einlage/Entnahme Muster GbR / Kapitalkonto Muster GbR", -x, False),
                    ("Muster GbR", "financing", "Einlage/Entnahme Privat / Kapitalkonto Gesellschafter", x, False)],
              no_value=[("Privat", "kap_gbr"), ("Muster GbR", "g_kap")])


def rent_and_salary_between_areas(d, lag, k, i):
    """Paid for something between your areas, with a category on both sides: rent to your partnership, a salary from your
    company -- income and costs, not contributions."""
    rent, salary = 1200 * k, 4000 * k
    return Sc([(i, "giro", d, -rent, {"iban": "DE31", "cat": "Wohnen\\Miete"}), (i + 1, "g_kk", d + timedelta(lag), rent, {"iban": "DE11", "cat": "Mieteinnahmen"}),
               (i + 2, "h_kk", d, -salary, {"iban": "DE11", "cat": "Gehälter"}), (i + 3, "giro", d + timedelta(lag), salary, {"iban": "DE21", "cat": "Gehalt"})],
              nw={"Privat": salary - rent, "Muster GbR": rent, "Holding GmbH": -salary},
              rows=[("Privat", "expenses", "Wohnen", -rent, True), ("Privat", "income", "Arbeitseinkommen", salary, True),
                    ("Muster GbR", "income", "Vermietung", rent, True), ("Holding GmbH", "expenses", "Personal", -salary, True)])


def same_amount_to_two_areas(d, lag, k, i):
    """The same amount to two of your areas in one week, only one booked against a capital account: that one goes into it, the
    other leaves your net worth."""
    x = 1000 * k
    return Sc([(i, "giro", d, -x, {"iban": "DE31"}), (i + 1, "kap_gbr", d, x, {"purpose": "Einlage"}), (i + 2, "g_kk", d + timedelta(lag), x, {"iban": "DE11"}),
               (i + 3, "giro", d + timedelta(1), -x, {"iban": "DE21"}), (i + 4, "h_kk", d + timedelta(1 + lag), x, {"iban": "DE11"})],
              nw={"Privat": -x, "Muster GbR": x, "Holding GmbH": x},
              rows=[("Privat", "investing", "Einlage/Entnahme Muster GbR / Kapitalkonto Muster GbR", -x, False),
                    ("Privat", "investing", "Einlage/Entnahme Holding GmbH", -x, True)],
              no_value=[("Privat", "kap_gbr")])


SCENARIOS = [contribution_gmbh_with_stake, contribution_gmbh_without_stake, shareholder_loan, partnership_contribution,
             partnership_contribution_mirrored, partnership_withdrawal, company_bought_on_seller_loan, bank_loan_for_a_flat,
             loan_paid_to_the_notary, partnership_bank_loan, loan_from_a_friend, loan_to_a_friend, bill_booked_when_due,
             laid_out_for_the_partnership, holding_lends_to_the_partnership, dividend, transfer_to_savings,
             contribution_with_participation_rule, loan_from_your_partnership, participation_rule_and_capital_account,
             rent_and_salary_between_areas, same_amount_to_two_areas]


def merge(cfgs):
    out = {}
    for c in cfgs:
        for key, v in c.items():
            if isinstance(v, list):
                out.setdefault(key, []).extend(x for x in v if x not in out.get(key, []))
            elif isinstance(v, dict):
                for k2, v2 in v.items():
                    out.setdefault(key, {}).setdefault(k2, {}).update(v2) if isinstance(v2, dict) else out.setdefault(key, {}).__setitem__(k2, v2)
    return out


class Checks(unittest.TestCase):
    def adds_up(self, data, label):
        """Every month of every area: net worth and cash explained to the cent; the only reason: money in transit."""
        for area, ds in data.items():
            for m, u in ds["cashflow"]["reconciliation"].items():
                for check, why in (("unexplained", "reasons"), ("diff_cash", "reasons_cash")):
                    reasons = {g[0] for g in u[why]}
                    self.assertTrue(abs(u[check]) < 0.005 or (reasons and reasons <= {"ue_unterwegs"}), "%s · %s %s: %s=%s %s" % (label, area, m, check, u[check], u[why]))
                    self.assertAlmostEqual(sum(g[1] for g in u[why]), u[check] if u[why] else 0.0, 2, "%s · %s %s" % (label, area, m))

    def nw_change(self, ds, since):
        nw = ds["balance"]["net_worth"]
        keys = sorted(nw)
        before = max(k for k in keys if k < since)
        return round(nw[keys[-1]] - nw[before], 2)

    def check(self, sc, data, label, first_day):
        self.adds_up(data, label)
        since = mk(first_day)
        for area, want in sc.nw.items():
            self.assertAlmostEqual(self.nw_change(data[area], since), want, 2, "%s · %s: net worth" % (label, area))
        for area, sec, row, total, nw in sc.rows:          # totals from the scenario's first month on
            if row.startswith("@"):                   # by account: all rows of that account in the section, together
                zs = [z for s in data[area]["cashflow"]["sections"] if s["name"] == sec for z in s["rows"] if z.get("account") == row[1:]]
                self.assertTrue(zs, "%s · %s: %s %s" % (label, area, sec, row))
                self.assertAlmostEqual(sum(v for z in zs for m, v in z["amounts"].items() if m >= since), total, 2, "%s · %s: %s" % (label, area, row))
                self.assertTrue(all(z["nw"] == nw for z in zs), "%s · %s: %s counts in the net worth" % (label, area, row))
                continue
            rs = {z["row"]: z for s in data[area]["cashflow"]["sections"] if s["name"] == sec for z in s["rows"]}
            self.assertIn(row, rs, "%s · %s: %s %s" % (label, area, sec, sorted(rs)))
            self.assertAlmostEqual(sum(v for m, v in rs[row]["amounts"].items() if m >= since), total, 2, "%s · %s: %s" % (label, area, row))
            self.assertEqual(rs[row]["nw"], nw, "%s · %s: %s counts in the net worth" % (label, area, row))
        for area, acc in sc.no_value:
            vals = [z for s in data[area]["cashflow"]["sections"] if s["name"] == "valuation" for z in s["rows"] if z.get("account") == acc]
            self.assertFalse(vals, "%s · %s: no change in value of %s" % (label, area, NAME[acc]))
        if sc.due_month_nw:                         # a cost booked when due: the net worth falls that month, not when paid
            area, day, want = sc.due_month_nw
            nw = data[area]["balance"]["net_worth"]; keys = sorted(nw); m = mk(day)
            self.assertAlmostEqual(round(nw[m] - nw[keys[keys.index(m) - 1]], 2), want, 2, label)
        for area, accs in sc.non_cash:           # bought on credit: no money moved -- both sides change in value, together nothing
            vals = [z for s in data[area]["cashflow"]["sections"] if s["name"] == "valuation" for z in s["rows"] if z.get("account") in accs]
            self.assertEqual(len(vals), len(accs), label)
            self.assertAlmostEqual(sum(sum(z["amounts"].values()) for z in vals), 0.0, 2, label)


class EachScenario(Checks):
    def test_every_scenario_on_every_kind_of_day(self):
        for fn in SCENARIOS:
            for variant, (d, lag) in VARIANTS.items():
                with self.subTest(scenario=fn.__name__, variant=variant):
                    sc = fn(d, lag, 1, 100)
                    data = run(START + sc.txs, sc.cfg)
                    self.check(sc, data, "%s/%s" % (fn.__name__, variant), d)
                    crosses = {mk(t[2]) for t in sc.txs if t[1] in ("giro", "h_kk", "g_kk")} != {mk(t[2]) for t in sc.txs}
                    if not crosses and lag == 0:            # all in one month: nothing in transit, no reason needed at all
                        for area, ds in data.items():
                            for m, u in ds["cashflow"]["reconciliation"].items():
                                self.assertFalse(u["reasons"] or u["reasons_cash"], "%s/%s · %s %s" % (fn.__name__, variant, area, m))

    def test_money_in_transit_over_the_year_end(self):
        """Paid on 30 December, arrived on 2 January: at the year end it is in transit -- part of the net worth, under cash."""
        sc = partnership_contribution_mirrored(date(2025, 12, 30), 3, 1, 100)
        data = run(START + sc.txs, sc.cfg)
        g = data["Muster GbR"]
        transit = next(r for r in g["balance"]["rows"] if r["id"] == "transit")
        self.assertEqual((transit["amounts"]["2025-12"], transit["amounts"]["2026-01"], transit["role"]), (10000.0, 0.0, "cash"))
        nw = g["balance"]["net_worth"]
        self.assertEqual((nw["2025-12"], nw["2026-01"]), (nw["2025-11"], nw["2025-11"]))
        u = g["cashflow"]["reconciliation"]
        self.assertEqual([r[0] for r in u["2025-12"]["reasons_cash"]], ["ue_unterwegs"]); self.assertFalse(u["2025-12"]["reasons"])

    def test_same_day_booked_by_hand_needs_no_transit(self):
        """Your counter-booking on the day of your bank's booking: never anything in transit, even on the last of the month."""
        for d in (date(2026, 1, 31), date(2025, 12, 31)):
            sc = partnership_contribution(d, 0, 1, 100)
            data = run(START + sc.txs, sc.cfg)
            for area, ds in data.items():
                self.assertFalse(any(r["id"] == "transit" for r in ds["balance"]["rows"]), area)
                self.assertFalse(any(u["reasons"] or u["reasons_cash"] for u in ds["cashflow"]["reconciliation"].values()), area)


class MixedAtRandom(Checks):
    def test_many_scenarios_at_once(self):
        """Several scenarios in one ledger, on random days with random amounts (the same amount may come twice): every month
        still adds up, and every area's net worth moves by the sum of what happened."""
        for seed in F.fuzz_seeds("Szenarien gemischt"):
            rnd = random.Random(seed)
            picks = [rnd.choice(SCENARIOS) for _ in range(rnd.randint(3, 8))]
            scs, first = [], None
            for n, fn in enumerate(picks):
                d = date(2025, 12, 1) + timedelta(rnd.randint(0, 90))
                d = d.replace(day=rnd.choice([d.day, 28, 29, 30, 31])) if rnd.random() < 0.4 and d.month != 2 else d
                scs.append(fn(d, rnd.choice([0, 0, 1, 2, 3, 5]), rnd.choice([1, 1, 1.5, 2, 3]), 100 + 20 * n))
                first = min(first or d, d)
            with self.subTest(seed=seed, scenarios=[f.__name__ for f in picks]), F.case(seed):
                data = run(START + [t for sc in scs for t in sc.txs], merge([sc.cfg for sc in scs]))
                self.adds_up(data, "seed %d" % seed)
                for area in AREAS:
                    want = round(sum(sc.nw.get(area, 0) for sc in scs), 2)
                    self.assertAlmostEqual(self.nw_change(data[area], mk(first)), want, 2, "seed %d · %s" % (seed, area))


if __name__ == "__main__":
    unittest.main()
