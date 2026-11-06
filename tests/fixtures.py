"""Synthetische Daten im Format des MoneyMoney-Exports (Property-List-Dicts).

Nachgebaut ist die Kontenstruktur: privater Bereich mit Liquiditaet, Anlagen,
Beteiligungen, Verbindlichkeiten; dazu eine GbR mit Kontokorrent, Immobilie,
Verkaeuferdarlehen (manuell) und Kapitalkonten. Namen und Betraege sind frei erfunden.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List

U: Dict[str, str] = {}


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
        acc("priv.bet.pb", "Beteiligung an Alpha GbR", 3, "Offline-Konto", balance=b("priv.bet.pb", -90000.0)),
        acc("priv.bet.shs", "Beteiligung an Beta GbR", 3, "Offline-Konto", balance=b("priv.bet.shs", -65312.27)),
        acc("priv.verb", "Verbindlichkeiten", 2, "Kontengruppe", True),
        acc("priv.darl", "Darlehen Lindenstraße", 3, "Darlehenskonto", balance=b("priv.darl", -300000.0), iban="DE02500105170137075030", bank="50010517"),
        acc("pb", "Alpha GbR", 1, "Kontengruppe", True),
        acc("pb.liq", "Liquidität", 2, "Kontengruppe", True),
        acc("pb.kk", "Stadtbank Kontokorrent", 3, "Girokonto", balance=b("pb.kk", 40000.0), iban="DE02701500000000594937", bank="70150000"),
        acc("pb.anl", "Anlagen", 2, "Kontengruppe", True),
        acc("pb.immo", "Immobilie Parkweg", 3, "Festgeldanlage", balance=b("pb.immo", 1900000.0)),
        acc("pb.verb", "Verbindlichkeiten", 2, "Kontengruppe", True),
        acc("pb.vd", "Verkäuferdarlehen", 3, "Darlehenskonto", balance=b("pb.vd", -1600000.0)),
        acc("pb.kap.s", "Kapitalkonto A", 3, "Darlehenskonto", balance=b("pb.kap.s", -120000.0)),
        acc("pb.kap.p", "Kapitalkonto B", 3, "Darlehenskonto", balance=b("pb.kap.p", -120000.0)),
        acc("shs", "Beta GbR", 1, "Kontengruppe", True),
        acc("shs.liq", "Liquidität", 2, "Kontengruppe", True),
        acc("shs.kk", "Stadtbank Kontokorrent", 3, "Girokonto", balance=b("shs.kk", 15000.0), iban="DE02701500000000594938", bank="70150000"),
        acc("shs.anl", "Anlagen", 2, "Kontengruppe", True),
        acc("shs.immo", "Immobilie Bahnhofstraße", 3, "Festgeldanlage", balance=b("shs.immo", 3300000.0)),
        acc("shs.verb", "Verbindlichkeiten", 2, "Kontengruppe", True),
        acc("shs.d1", "Darlehen Beta fest", 3, "Darlehenskonto", balance=b("shs.d1", -1300000.0), iban="DE02500105170137075031", bank="50010517"),
        acc("shs.d2", "Darlehen Beta variabel", 3, "Darlehenskonto", balance=b("shs.d2", -2000000.0), iban="DE02500105170137075032", bank="50010517"),
        acc("shs.kap.s", "Kapitalkonto A", 3, "Darlehenskonto", balance=b("shs.kap.s", -74145.0)),
        acc("shs.kap.p", "Kapitalkonto B", 3, "Darlehenskonto", balance=b("shs.kap.p", -74145.0)),
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


def pb_transactions(until: date, with_manual_interest_until: date = None, annuity=8250.0, extra=None) -> List[dict]:
    """Kontokorrent der GbR: Annuitaet am 1. jedes Monats ab 2026-01; Darlehen: Startbuchung 2025-12."""
    out = [tx("pb.vd", date(2025, 11, 20), -1650000.0, "Verkäufer", "Kaufpreisstundung"),
           tx("pb.vd", date(2025, 12, 15), 50000.0, "GbR", "Anzahlung")]
    y, m = 2026, 1
    while date(y, m, 1) <= until:
        out.append(tx("pb.kk", date(y, m, 1), -annuity, "Verkäufer", ANNUITY_TEXT, "Umbuchung", SELLER_IBAN))
        if with_manual_interest_until and date(y, m, 1) <= with_manual_interest_until:
            out.append(tx("pb.vd", date(y, m, 1), annuity, "GbR", "Annuität %02d/%d" % (m, y), "Umbuchung"))
            out.append(tx("pb.vd", date(y, m, 1), -4400.0, "Verkäufer", "Zinsen %02d/%d" % (m, y), "Zinsen"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    for e in (extra or []):
        out.append(e)
    return out
