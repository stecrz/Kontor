"""Synthetische Daten im Format des MoneyMoney-Exports (Property-List-Dicts).

Nachgebaut ist die Kontenstruktur: privater Bereich mit Liquiditaet, Anlagen,
Beteiligungen, Verbindlichkeiten; dazu eine GbR mit Kontokorrent, Immobilie,
Verkaeuferdarlehen (manuell) und Kapitalkonten. Namen und Betraege sind frei erfunden.
"""
from __future__ import annotations

import os
import random
import time
import uuid as _uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterator, List

U: Dict[str, str] = {}

# random cases a night found (KONTOR_FUZZ_RANDOM) -- once fixed, their number goes here, so every run checks them from then on
FOUND: List[int] = [377654401, 357881360]     # 3.16.58: two payments of one amount, one took the other's only counterpart


def fuzz_seeds(name: str = "") -> Iterator[int]:
    """The cases of a random test, one after the other: the fixed ones 0 .. KONTOR_FUZZ_SEEDS-1 (default 40; nightly.yml: 1000
    in its first job), those found before (FOUND), then new ones drawn anew every run from 1,000,000 on -- KONTOR_FUZZ_RANDOM of
    them, and more until KONTOR_FUZZ_MINUTES have passed since the test began (nightly.yml: as many as fit). A failure names
    its case ("seed …"); KONTOR_FUZZ_SEED=<number>[,<number>…] runs just those again. On GitHub the numbers go into the run's
    summary. (Many cases: with Python 3.9's pytest, which keeps nothing of a passed case.)"""
    env = os.environ.get
    only = env("KONTOR_FUZZ_SEED")
    if only:
        yield from (int(x) for x in only.replace(",", " ").split())
        return
    fixed, new, n = int(env("KONTOR_FUZZ_SEEDS") or 40), random.SystemRandom(), int(env("KONTOR_FUZZ_RANDOM") or 0)
    until = time.monotonic() + 60 * float(env("KONTOR_FUZZ_MINUTES") or 0)
    done = 0
    try:
        for seed in list(range(fixed)) + FOUND:
            yield seed
        while done < n or time.monotonic() < until:
            yield new.randrange(10 ** 6, 10 ** 9)
            done += 1
    finally:
        summary = env("GITHUB_STEP_SUMMARY")
        if summary and name:
            with open(summary, "a", encoding="utf-8") as f:
                f.write("- %s: %d feste, %d gefundene, %d neue Fälle\n" % (name, fixed, len(FOUND), done))


@contextmanager
def case(seed: int):
    """A failure in a random case names it ("seed …") -- pytest on Python 3.9 (the night's run) does not show the subtest's seed."""
    try:
        yield
    except Exception as e:
        if "seed %d" % seed in str(e):
            raise
        raise AssertionError("seed %d: %s" % (seed, e if isinstance(e, AssertionError) else repr(e))) from e


def uid(key: str) -> str:
    if key not in U:
        U[key] = str(_uuid.uuid5(_uuid.NAMESPACE_URL, "kontor-test/" + key))
    return U[key]


def _dt(d: date) -> datetime:
    # MoneyMoney exportiert lokale Mitternacht als UTC-Zeitpunkt (hier: UTC+1 -> 23:00 Vortag)
    return datetime(d.year, d.month, d.day, 0, 0, tzinfo=timezone(timedelta(hours=1))).astimezone(timezone.utc).replace(tzinfo=None)


def acc(key, name, indent, typ="Girokonto", group=False, balance=0.0, iban=None, bank="", portfolio=False):
    return {
        "uuid": uid(key), "name": name, "indentation": indent, "type": typ, "group": group,
        "balance": [[balance, "EUR"]], "currency": "EUR", "accountNumber": iban or "", "bankCode": bank,
        "iban": iban, "owner": "Inhaber", "portfolio": portfolio, "attributes": {},
        "refreshTimestamp": (_dt(date(2026, 11, 4)) if (bank or portfolio) else None), "icon": b"",
    }


# All names, amounts and numbers here are made up. The IBANs are the public sample IBANs from banks' documentation (some with
# a changed last digit for a second account), not real accounts of anyone involved.
def accounts_raw(balances: Dict[str, float]) -> List[dict]:
    b = balances.get
    return [
        acc("root", "Alle Konten", 0, "Kontengruppe", True),
        acc("priv", "Privat", 1, "Kontengruppe", True),
        acc("priv.liq", "Liquidität", 2, "Kontengruppe", True),
        acc("priv.giro", "Hausbank Giro", 3, "Girokonto", balance=b("priv.giro", 12000.0), iban="DE02120300000000202051", bank="12030000"),
        acc("priv.tr", "Broker Giro", 3, "Girokonto", balance=b("priv.tr", 3000.0), iban="DE02100500000054540402", bank="10050000"),
        acc("priv.anl", "Anlagen", 2, "Kontengruppe", True),
        acc("priv.depot", "Depot", 3, "Portfolio", balance=b("priv.depot", 85000.0), bank="10050000", portfolio=True),
        acc("priv.bet", "Beteiligungen", 2, "Kontengruppe", True),
        acc("priv.immo", "Immobilie Lindenstraße", 3, "Offline-Konto", balance=b("priv.immo", 420000.0)),
        acc("priv.bet.ga", "Beteiligung an Alpha GbR", 3, "Offline-Konto", balance=b("priv.bet.ga", -90000.0)),
        acc("priv.bet.gb", "Beteiligung an Beta GbR", 3, "Offline-Konto", balance=b("priv.bet.gb", -65312.27)),
        acc("priv.verb", "Verbindlichkeiten", 2, "Kontengruppe", True),
        acc("priv.darl", "Darlehen Lindenstraße", 3, "Darlehenskonto", balance=b("priv.darl", -300000.0), iban="DE02500105170137075030", bank="50010517"),
        acc("ga", "Alpha GbR", 1, "Kontengruppe", True),
        acc("ga.liq", "Liquidität", 2, "Kontengruppe", True),
        acc("ga.kk", "Stadtbank Kontokorrent", 3, "Girokonto", balance=b("ga.kk", 40000.0), iban="DE02701500000000594937", bank="70150000"),
        acc("ga.anl", "Anlagen", 2, "Kontengruppe", True),
        acc("ga.immo", "Immobilie Parkweg", 3, "Festgeldanlage", balance=b("ga.immo", 1500000.0)),
        acc("ga.verb", "Verbindlichkeiten", 2, "Kontengruppe", True),
        acc("ga.vd", "Verkäuferdarlehen", 3, "Darlehenskonto", balance=b("ga.vd", -1200000.0)),
        acc("ga.kap.a", "Kapitalkonto A", 3, "Darlehenskonto", balance=b("ga.kap.a", -120000.0)),
        acc("ga.kap.b", "Kapitalkonto B", 3, "Darlehenskonto", balance=b("ga.kap.b", -120000.0)),
        acc("gb", "Beta GbR", 1, "Kontengruppe", True),
        acc("gb.liq", "Liquidität", 2, "Kontengruppe", True),
        acc("gb.kk", "Stadtbank Kontokorrent", 3, "Girokonto", balance=b("gb.kk", 15000.0), iban="DE02701500000000594938", bank="70150000"),
        acc("gb.anl", "Anlagen", 2, "Kontengruppe", True),
        acc("gb.immo", "Immobilie Bahnhofstraße", 3, "Festgeldanlage", balance=b("gb.immo", 2800000.0)),
        acc("gb.verb", "Verbindlichkeiten", 2, "Kontengruppe", True),
        acc("gb.d1", "Darlehen Beta fest", 3, "Darlehenskonto", balance=b("gb.d1", -1100000.0), iban="DE02500105170137075031", bank="50010517"),
        acc("gb.d2", "Darlehen Beta variabel", 3, "Darlehenskonto", balance=b("gb.d2", -1500000.0), iban="DE02500105170137075032", bank="50010517"),
        acc("gb.kap.a", "Kapitalkonto A", 3, "Darlehenskonto", balance=b("gb.kap.a", -60000.0)),
        acc("gb.kap.b", "Kapitalkonto B", 3, "Darlehenskonto", balance=b("gb.kap.b", -60000.0)),
    ]


_tx_id = [100000]


def tx(acct_key: str, d: date, amount: float, name: str = "", purpose: str = "", category: str = "",
       counter_iban: str = "", booked: bool = True, comment: str = "", booking_text: str = "") -> dict:
    _tx_id[0] += 1
    return {
        "id": _tx_id[0], "accountUuid": uid(acct_key), "bookingDate": _dt(d), "valueDate": _dt(d),
        "amount": amount, "currency": "EUR", "name": name, "purpose": purpose, "category": category.split("\\")[-1],
        "categoryPath": category, "categoryUuid": "", "accountNumber": counter_iban, "bankCode": "",
        "booked": booked, "checkmark": False, "comment": comment, "bookingText": booking_text,
    }


ANNUITY_TEXT = "Annuität Darlehen - Darlehensvertrag Objekt Parkweg 7 (Urkunde 1234/2025)"
SELLER_IBAN = "DE02300209000106531065"


def ga_transactions(until: date, with_manual_interest_until: date = None, annuity=6000.0, extra=None) -> List[dict]:
    """Kontokorrent der GbR: Annuitaet am 1. jedes Monats ab 2026-01; Darlehen: Startbuchung 2025-12."""
    out = [tx("ga.vd", date(2025, 11, 20), -1250000.0, "Verkäufer", "Kaufpreisstundung"),
           tx("ga.vd", date(2025, 12, 15), 50000.0, "GbR", "Anzahlung")]
    y, m = 2026, 1
    while date(y, m, 1) <= until:
        out.append(tx("ga.kk", date(y, m, 1), -annuity, "Verkäufer", ANNUITY_TEXT, "Umbuchung", SELLER_IBAN))
        if with_manual_interest_until and date(y, m, 1) <= with_manual_interest_until:
            out.append(tx("ga.vd", date(y, m, 1), annuity, "GbR", "Annuität %02d/%d" % (m, y), "Umbuchung"))
            out.append(tx("ga.vd", date(y, m, 1), -3000.0, "Verkäufer", "Zinsen %02d/%d" % (m, y), "Zinsen"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    for e in (extra or []):
        out.append(e)
    return out
