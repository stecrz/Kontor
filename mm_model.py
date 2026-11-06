"""Datenmodell: Konten, Kontenbaum, Umsaetze, Salden zum Stichtag.

Reine Logik ohne MoneyMoney-Zugriff -- vollstaendig ohne macOS testbar.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from mm_bridge import local_date, local_datetime

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# Namen der Wurzel, die MoneyMoney im Export als erste Zeile liefert
ROOT_NAMES = {"alle konten", "all accounts"}



def norm_cat(path: str) -> str:
    """Kategoriepfad vereinheitlichen: 'A\\B', 'A \\ B' und 'A / B' werden zu 'A / B' (Teile getrimmt)."""
    parts = [p.strip() for p in re.split(r"[\\/]", str(path or ""))]
    return " / ".join(p for p in parts if p)

@dataclass
class Account:
    uuid: str
    name: str
    type: str
    group: bool
    indentation: int
    balance: float
    currency: str
    iban: Optional[str] = None
    account_number: Optional[str] = None
    bank_code: Optional[str] = None
    owner: Optional[str] = None
    portfolio: bool = False
    refresh: Optional[datetime] = None
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    path: str = ""
    extra_currencies: Dict[str, float] = field(default_factory=dict)

    @property
    def offline(self) -> bool:
        """Manuell gepflegtes Konto: keine Gruppe, kein Depot, nie von einer Bank/Extension
        aktualisiert (Extension-Konten wie PayPal haben keine Bankleitzahl, aber einen
        Aktualisierungszeitpunkt). MoneyMoney selbst verweigert Buchungen in Online-Konten
        zusaetzlich -- diese Erkennung dient der Anzeige und als erste Schranke."""
        if self.group or self.portfolio:
            return False
        refreshed = self.refresh is not None and self.refresh.year >= 2005
        return not refreshed and not (self.bank_code or "").strip()


@dataclass
class Tx:
    id: int
    account_uuid: str
    booking_date: date
    value_date: Optional[date]
    amount: float
    currency: str
    name: str = ""
    purpose: str = ""
    booking_text: str = ""
    category: str = ""
    category_path: str = ""
    category_uuid: str = ""
    counter_iban: str = ""
    counter_bank: str = ""
    booked: bool = True
    checkmark: bool = False
    comment: str = ""
    mm_category_path: Optional[str] = None      # Original aus MoneyMoney, wenn category_path von Kontor ueberlagert wurde

    @property
    def text(self) -> str:
        return " ".join(x for x in (self.name, self.purpose, self.booking_text, self.comment) if x)


# ---------------------------------------------------------------------------
# Konvertierung aus dem MoneyMoney-Export
# ---------------------------------------------------------------------------

def _balance_eur(raw: Any) -> Tuple[float, Dict[str, float]]:
    """MoneyMoney liefert balance als Liste von [Betrag, Waehrung]-Paaren."""
    main, others = 0.0, {}
    if isinstance(raw, list):
        for i, pair in enumerate(raw):
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                amt, cur = float(pair[0]), str(pair[1])
                if i == 0:
                    main = amt
                else:
                    others[cur] = amt
    elif isinstance(raw, (int, float)):
        main = float(raw)
    return main, others


def accounts_from_export(raw: List[Dict[str, Any]]) -> Dict[str, Account]:
    """Kontenliste des Exports -> Baum (Eltern/Kinder ueber Einrueckung)."""
    accounts: Dict[str, Account] = {}
    order: List[Account] = []
    for r in raw:
        uuid = str(r.get("uuid") or "")
        if not uuid:
            continue
        bal, others = _balance_eur(r.get("balance"))
        acc = Account(
            uuid=uuid,
            name=str(r.get("name") or ""),
            type=str(r.get("type") or ""),
            group=bool(r.get("group", False)),
            indentation=int(r.get("indentation") or 0),
            balance=bal,
            currency=str(r.get("currency") or "EUR"),
            iban=(str(r.get("iban")) if r.get("iban") else None),
            account_number=(str(r.get("accountNumber")) if r.get("accountNumber") else None),
            bank_code=(str(r.get("bankCode")) if r.get("bankCode") else None),
            owner=(str(r.get("owner")) if r.get("owner") else None),
            portfolio=bool(r.get("portfolio", False)),
            refresh=local_datetime(r.get("refreshTimestamp")),
            extra_currencies=others,
        )
        if acc.iban is None and acc.account_number and re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", acc.account_number):
            acc.iban = acc.account_number
        accounts[uuid] = acc
        order.append(acc)

    # Baum: Stack nach Einrueckung; die Wurzel "Alle Konten" wird uebersprungen
    stack: List[Account] = []
    for acc in order:
        if acc.indentation == 0 and acc.name.strip().lower() in ROOT_NAMES and acc.group:
            stack = [acc]
            acc.path = ""
            continue
        while stack and stack[-1].indentation >= acc.indentation:
            stack.pop()
        parent = stack[-1] if stack else None
        if parent is not None and parent.name.strip().lower() in ROOT_NAMES and parent.indentation == 0:
            acc.parent = None
            acc.path = acc.name
        elif parent is not None:
            acc.parent = parent.uuid
            parent.children.append(acc.uuid)
            acc.path = (parent.path + " / " + acc.name) if parent.path else acc.name
        else:
            acc.parent = None
            acc.path = acc.name
        if acc.group:
            stack.append(acc)
    return accounts


def tx_from_export(raw: List[Dict[str, Any]]) -> List[Tx]:
    out: List[Tx] = []
    for r in raw:
        bd = local_date(r.get("bookingDate"))
        if bd is None:
            continue
        out.append(Tx(
            id=int(r.get("id") or 0),
            account_uuid=str(r.get("accountUuid") or ""),
            booking_date=bd,
            value_date=local_date(r.get("valueDate")),
            amount=float(r.get("amount") or 0.0),
            currency=str(r.get("currency") or "EUR"),
            name=str(r.get("name") or ""),
            purpose=str(r.get("purpose") or ""),
            booking_text=str(r.get("bookingText") or ""),
            category=str(r.get("category") or ""),
            category_path=str(r.get("categoryPath") or r.get("category") or ""),
            category_uuid=str(r.get("categoryUuid") or ""),
            counter_iban=str(r.get("accountNumber") or "").replace(" ", "").upper(),
            counter_bank=str(r.get("bankCode") or ""),
            booked=bool(r.get("booked", True)),
            checkmark=bool(r.get("checkmark", False)),
            comment=str(r.get("comment") or ""),
        ))
    out.sort(key=lambda t: (t.booking_date, t.id))
    return out


# ---------------------------------------------------------------------------
# Kontenbaum
# ---------------------------------------------------------------------------

class Ledger:
    """Konten + Umsaetze einer Sitzung, mit In-Memory-Buchungen fuer den Probelauf."""

    def __init__(self, accounts: Dict[str, Account], txs: Iterable[Tx]):
        self.accounts = accounts
        self.txs: List[Tx] = list(txs)
        self.hints: List[str] = []      # Hinweise zu Kontoreferenzen (umbenannt, nur ueber Namen gefunden)
        self._by_account: Dict[str, List[Tx]] = {}
        for t in self.txs:
            self._by_account.setdefault(t.account_uuid, []).append(t)
        self._next_virtual_id = -1

    # -- Auflösung von Kontoreferenzen -----------------------------------

    def resolve(self, ref: str, groups_ok: bool = True) -> Account:
        """Kontoreferenz aufloesen. Empfohlen: "UUID | Name" -- die UUID ist massgeblich
        (ueberlebt Umbenennen und Verschieben), der Name dient als Lesehilfe und Rueckfall.
        Auch moeglich: UUID allein, vollstaendiger Pfad 'A / B / C', Pfad-Suffix, eindeutiger Name."""
        ref = (ref or "").strip()
        if not ref:
            raise KeyError("Leere Kontoreferenz.")
        label = None
        if "|" in ref:
            ref, label = (x.strip() for x in ref.split("|", 1))
        if UUID_RE.match(ref):
            acc = self.accounts.get(ref.lower()) or self.accounts.get(ref) or self.accounts.get(ref.upper())
            if acc is not None:
                if label and label != acc.name and not acc.path.endswith(label):
                    self._hint("Konto '%s' heisst jetzt '%s' (UUID unveraendert) -- Beschriftung in config.json "
                               "bei Gelegenheit anpassen." % (label, acc.path))
                return acc
            if label:
                try:
                    acc = self.resolve(label)
                except KeyError:
                    raise KeyError("Konto '%s' (UUID %s) nicht gefunden -- geloescht? 'kontor konten' zeigt die "
                                   "aktuelle Liste." % (label, ref))
                self._hint("Konto '%s': UUID %s existiert nicht mehr, ueber den Namen gefunden (%s). Neue UUID in "
                           "config.json eintragen: %s" % (label, ref, acc.path, acc.uuid))
                return acc
            raise KeyError("Konto mit UUID %s nicht gefunden." % ref)
        norm = " / ".join(p.strip() for p in ref.split("/"))
        exact = [a for a in self.accounts.values() if a.path == norm]
        if len(exact) == 1:
            return exact[0]
        suffix = [a for a in self.accounts.values() if a.path.endswith(norm) and
                  (a.path == norm or a.path.endswith(" / " + norm))]
        if len(suffix) == 1:
            return suffix[0]
        byname = [a for a in self.accounts.values() if a.name == ref]
        if len(byname) == 1:
            return byname[0]
        cands = suffix or byname
        if not cands:
            raise KeyError("Konto '%s' nicht gefunden." % ref)
        raise KeyError("Konto '%s' ist mehrdeutig: %s -- bitte Pfad oder UUID angeben." %
                       (ref, "; ".join(a.path for a in cands)))

    def _hint(self, text: str) -> None:
        if text not in self.hints:
            self.hints.append(text)

    def descendants(self, uuid: str, leaves_only: bool = True) -> List[Account]:
        out: List[Account] = []
        acc = self.accounts[uuid]
        for c in acc.children:
            child = self.accounts[c]
            if child.group:
                if not leaves_only:
                    out.append(child)
                out.extend(self.descendants(c, leaves_only))
            else:
                out.append(child)
        return out

    def roots(self) -> List[Account]:
        return [a for a in self.accounts.values() if a.parent is None and a.path]

    def ancestors(self, uuid: str) -> List[Account]:
        out = []
        p = self.accounts[uuid].parent
        while p:
            out.append(self.accounts[p])
            p = self.accounts[p].parent
        return out

    def group_balance(self, uuid: str) -> float:
        acc = self.accounts[uuid]
        if not acc.group:
            return acc.balance
        return round(sum(a.balance for a in self.descendants(uuid)), 2)

    # -- Umsaetze und Salden ---------------------------------------------

    def transactions(self, uuid: str, booked_only: bool = True) -> List[Tx]:
        txs = self._by_account.get(uuid, [])
        return [t for t in txs if t.booked] if booked_only else list(txs)

    def balance_at(self, uuid: str, day: date) -> float:
        """Saldo am Ende des Tages `day` (aus aktuellem Saldo rueckgerechnet)."""
        acc = self.accounts[uuid]
        if acc.group:
            return round(sum(self.balance_at(a.uuid, day) for a in self.descendants(uuid)), 2)
        later = sum(t.amount for t in self.transactions(uuid) if t.booking_date > day)
        return round(acc.balance - later, 2)

    def has_history_before(self, uuid: str, day: date) -> bool:
        return any(t.booking_date <= day for t in self.transactions(uuid))

    def earliest_tx(self, uuid: str) -> Optional[date]:
        txs = self.transactions(uuid)
        return txs[0].booking_date if txs else None

    # -- In-Memory-Buchung (fuer Probelauf und Reihenfolge innerhalb eines Laufs)

    def post(self, uuid: str, booking_date: date, amount: float, name: str, purpose: str,
             category: str = "") -> Tx:
        acc = self.accounts[uuid]
        t = Tx(id=self._next_virtual_id, account_uuid=uuid, booking_date=booking_date,
               value_date=booking_date, amount=round(amount, 2), currency=acc.currency,
               name=name, purpose=purpose, category=category, category_path=category, booked=True)
        self._next_virtual_id -= 1
        self.txs.append(t)
        self._by_account.setdefault(uuid, []).append(t)
        self._by_account[uuid].sort(key=lambda x: (x.booking_date, x.id))
        acc.balance = round(acc.balance + t.amount, 2)
        return t

    def own_ibans(self) -> Dict[str, str]:
        out = {}
        for a in self.accounts.values():
            if a.iban:
                out[a.iban.replace(" ", "").upper()] = a.uuid
        return out


# ---------------------------------------------------------------------------
# Datums-Hilfen
# ---------------------------------------------------------------------------

def month_end(y: int, m: int) -> date:
    if m == 12:
        return date(y, 12, 31)
    return date(y, m + 1, 1).fromordinal(date(y, m + 1, 1).toordinal() - 1)


def add_months(d: date, n: int) -> Tuple[int, int]:
    y, m = d.year, d.month + n
    while m > 12:
        y, m = y + 1, m - 12
    while m < 1:
        y, m = y - 1, m + 12
    return y, m


def month_key(d: date) -> str:
    return "%04d-%02d" % (d.year, d.month)


def months_between(start: date, end: date) -> List[Tuple[int, int]]:
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = add_months(date(y, m, 1), 1)
    return out


def fmt_eur(x: float) -> str:
    s = "%.2f" % abs(x)
    whole, frac = s.split(".")
    whole = "{:,}".format(int(whole)).replace(",", ".")
    return ("-" if x < 0 else "") + whole + "," + frac + " €"
