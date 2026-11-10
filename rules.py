"""Booking rules: loans (repayment and interest), and per company the value of your participation and account mirrors.

Stateless: every run derives everything from MoneyMoney and the settings. What is booked already is recognised by the mark in
its purpose (#kontor-tx-<id>, #kontor-zins-YYYY-MM, #kontor-wert-..., #kontor-gk-<id>; "#mm-..." until 3.12) or by an equal
booking you made yourself. Kontor keeps no list of its own bookings, so nothing can get out of step with MoneyMoney: a booking
deleted there is simply missing again, one changed there (with its mark) counts as it is now. Kept are only your decisions
"Don't book" (settings: nicht_buchen) and up to where Kontor had looked when it last booked on its own (Seen).

Each rule returns proposals and notes; it never changes MoneyMoney itself (that is core.apply_proposals).
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from model import MARK, TAG_RE, Ledger, Tx, canon_tag, fmt_eur, has_mark, marks_in, month_end, months_between
from i18n import tr


def bkey(account_uuid: str, tag: str) -> str:
    """A booking of Kontor: account and mark (the same mark, e.g. interest of a month, exists once per account)."""
    return "%s|%s" % (account_uuid, canon_tag(tag))


@dataclass
class Proposal:
    rule: str
    kind: str                 # tilgung | zins | wert | spiegel
    account_uuid: str
    account_path: str
    booking_date: date
    amount: float
    payee: str
    purpose: str
    category: str = ""
    tag: str = ""
    group: str = ""           # company (area id) of a participation or account mirror
    retro: bool = False       # older than the last check (backdated, or missing again): never booked without your approval

    @property
    def key(self) -> str:
        return bkey(self.account_uuid, self.tag)

    def describe(self) -> str:
        return "%s  %s  %s  %s  %s  [%s]" % (
            self.rule, self.booking_date.isoformat(), self.account_path,
            fmt_eur(self.amount).rjust(16), self.purpose, self.category or "-")


@dataclass
class RuleResult:
    proposals: List[Proposal] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)
    preview: List[dict] = field(default_factory=list)     # per rule: target, actual, what is open (interface)


class Seen:
    """Up to where Kontor had looked when it last booked on its own: the highest transaction number in MoneyMoney (a new
    transaction gets a higher one) and the day. What arose after that is new; everything else -- backdated, or missing again
    because it was deleted in MoneyMoney -- is never booked without your approval, also when booking fully automatically.
    Without a mark (lost, first run) it starts now: nothing older is booked on its own. Seen() (tests): everything is new."""

    def __init__(self, max_id: Optional[int] = None, day: Optional[date] = None):
        self.max_id, self.day = max_id, day

    def new_tx(self, t: Tx) -> bool:
        """A transaction that came after the last check (or a new booking planned in this run)."""
        return self.max_id is None or t.id > self.max_id or bool(getattr(t, "planned", False) and getattr(t, "fresh", False))

    def after(self, d: date) -> bool:
        return self.day is None or d > self.day

    def since(self, d: date) -> bool:
        return self.day is None or d >= self.day

    @staticmethod
    def top_id(ledger: Ledger) -> int:
        return max((t.id for t in ledger.txs if t.id > 0), default=0)

    @classmethod
    def from_state(cls, raw, ledger: Ledger, today: date) -> "Seen":
        try:
            return cls(int(raw["id"]), date.fromisoformat(str(raw["tag"])))
        except (TypeError, KeyError, ValueError):
            return cls(cls.top_id(ledger), today)

    def dump(self) -> dict:
        return {"id": self.max_id, "tag": self.day.isoformat() if self.day else None}


VALUE_TAGS = (MARK + "wert-", MARK + "spiegel-")          # "spiegel": balance adjustments of counter accounts until 3.12.33
MIRROR_TAG = MARK + "gk-"
EDIT_AMOUNT = ("tilgung", "zins")       # kinds whose amount and date you may change before approving (the others follow MoneyMoney)


def is_value_tag(tag) -> bool:
    """A value adjustment (participation): always the difference to the balance, never a fixed amount."""
    return canon_tag(tag).startswith(VALUE_TAGS)


def present_marks(ledger: Ledger) -> set:
    """(account, mark) of Kontor's bookings that are in MoneyMoney (not the ones planned in this run)."""
    return {(t.account_uuid, m) for t in ledger.txs if not getattr(t, "planned", False) for m in marks_in(t.purpose)}


def not_booked_keys(config: Optional[dict]) -> set:
    """Your "Don't book" decisions (settings: nicht_buchen), as account|mark."""
    out = set()
    for x in (config or {}).get("nicht_buchen") or []:
        acc, _, tag = str((x or {}).get("key") if isinstance(x, dict) else "").partition("|")
        if acc and TAG_RE.fullmatch(tag):
            out.add(bkey(acc, tag))
    return out


def apply_edit(p: "Proposal", ch: Optional[dict]) -> None:
    """Your changes to a booking before approving it: the purpose always (its mark stays, so it is never made twice); amount
    and date only for a loan's repayment or interest -- a value adjustment or a mirrored booking follows MoneyMoney exactly."""
    if not ch:
        return
    if p.kind in EDIT_AMOUNT:
        if ch.get("betrag") is not None:
            p.amount = round(float(ch["betrag"]), 2)
        if ch.get("datum"):
            p.booking_date = date.fromisoformat(str(ch["datum"]))
    if ch.get("zweck") is not None:
        text = TAG_RE.sub("", str(ch["zweck"])).strip(" ·")
        p.purpose = ("%s · %s" % (text, p.tag)) if text else p.tag


def _emit(res: "RuleResult", ledger: Ledger, p: "Proposal", edits: Optional[Dict[str, dict]] = None) -> Tx:
    """Add a proposal and post it into the planned ledger -- with your changes from the approval, so everything planned
    after it (the next value adjustment, later interest) builds on what is really booked."""
    apply_edit(p, (edits or {}).get(p.key))
    res.proposals.append(p)
    t = ledger.post(p.account_uuid, p.booking_date, p.amount, p.payee, p.purpose, p.category)
    t.fresh = not p.retro           # a new booking: what follows from it (a participation's value) is new too
    return t


def _skipped(skip: Optional[set], account_uuid: str, tag: str) -> bool:
    """You chose "Don't book" (or left it out of this approval)."""
    return bool(skip) and bkey(account_uuid, tag) in skip


def _fill(template: str, **kw) -> str:
    out = template
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _rate_at(rates: List[dict], day: date) -> Optional[float]:
    best = None
    for r in sorted(rates, key=lambda x: x.get("ab", "0000-00-00")):
        ab = date.fromisoformat(r["ab"]) if r.get("ab") else date(1900, 1, 1)
        if ab <= day:
            best = float(r["prozent"])
    return best


def _matches(t: Tx, erk: dict) -> bool:
    ibans = erk.get("gegen_iban") or []
    if isinstance(ibans, str):
        ibans = [ibans]
    ibans = [i.replace(" ", "").upper() for i in ibans if i]
    texts = erk.get("text_enthaelt") or []
    if isinstance(texts, str):
        texts = [texts]
    if not ibans and not texts:
        return False
    hit_iban = bool(ibans) and t.counter_iban in ibans
    hit_text = bool(texts) and any(s.lower() in t.text.lower() for s in texts)
    if not (hit_iban or hit_text):
        return False
    excl = erk.get("ausschliessen_text") or []
    if isinstance(excl, str):
        excl = [excl]
    if excl and any(x.lower() in t.text.lower() for x in excl):
        return False
    richtung = erk.get("richtung", "abgang")
    if richtung == "abgang" and t.amount >= 0:
        return False
    if richtung == "zugang" and t.amount <= 0:
        return False
    return True


def _first_mark(ledger: Ledger, accounts: Iterable[str], prefixes: Tuple[str, ...]) -> Optional[date]:
    """The day of Kontor's earliest booking of a kind in some accounts (in MoneyMoney), if any."""
    days = [t.booking_date for u in accounts for t in ledger.transactions(u) if not getattr(t, "planned", False)
            and any(m.startswith(prefixes) for m in marks_in(t.purpose))]
    return min(days) if days else None


def _all_ids(ledger: Ledger) -> set:
    """The numbers of all transactions read (once per state)."""
    c = ledger.__dict__.get("_id_set")
    if c is None or c[0] != len(ledger.txs):
        c = ledger._id_set = (len(ledger.txs), {t.id for t in ledger.txs if t.id > 0})
    return c[1]


# ---------------------------------------------------------------------------
# Loans
# ---------------------------------------------------------------------------

def payment_kind(t: Tx) -> str:
    low = t.text.lower()
    if "sondertilgung" in low:
        return "Sondertilgung"
    if "annuit" in low or "rate" in low:
        return "Annuität"
    return "Zahlung"


DEFAULT_TEXTS = {
    "tilgung_text": "{art} {datum} von {quelle} · {tag}",
    "zins_text": "Zinsen {monat} · {prozent} % p.a. auf {basis} · {tag}",
    "wert_text": "Wertanpassung: {anteil} % × {wert} (Wert {quelle}) = {soll} · {tag}",
    "spiegel_text": "{text} · gespiegelt von {quelle} · {tag}",
}

SAME_PAYMENT_DAYS = 7       # a repayment you booked yourself (or one whose payment MoneyMoney replaced) counts within these days


def _payment_id(mark: str) -> Optional[int]:
    m = re.fullmatch(r"#kontor-tx-(\d+)", mark)
    return int(m.group(1)) if m else None


def plan_loan(ledger: Ledger, cfg: dict, today: date, config: Optional[dict] = None, skip: Optional[set] = None,
              edits: Optional[Dict[str, dict]] = None, seen: Optional[Seen] = None, hold: Optional[set] = None,
              auto: bool = False) -> RuleResult:
    """Every recognised payment from "Buchen ab" on as a repayment in the loan account, and the interest of every month.
    Booked is what is there: a repayment by its mark or as a booking with the same amount within a few days (yours, or
    Kontor's whose payment MoneyMoney replaced); interest by its mark, and a month with interest you booked yourself (its text
    or category says interest) is left to you. skip: your "Don't book". hold: left out of this run (waiting for you) -- the
    interest after it waits as well, as after an older booking (seen: what is new since the last check), because it is
    computed from the balance and never adjusted later. edits: your changes from the approval. auto: planning what booking
    fully automatically books -- what waits is planned as not booked."""
    skip, hold = skip or set(), hold or set()
    seen = seen or Seen()
    waits: List[date] = []                               # days of this loan's bookings that wait for you
    res = RuleResult()
    name = cfg.get("name") or cfg.get("darlehenskonto")
    rule = "Darlehen %s" % name
    try:
        loan = ledger.resolve(cfg["darlehenskonto"])
        sources = [ledger.resolve(s) for s in cfg.get("quellkonten", [])]
    except KeyError as e:
        res.warnings.append("%s: %s" % (rule, e))
        return res
    if loan.group:
        res.warnings.append(tr("s_s_darlehenskonto_ist_eine_gruppe") % rule)
        return res
    if not ledger.writable(loan.uuid, config):
        res.warnings.append(tr("s_s_konto_hat_eine_bankanbindung") % rule)
        return res

    ab = date.fromisoformat(cfg["ab_datum"])
    richtung = cfg.get("art", "verbindlichkeit")       # verbindlichkeit | forderung
    sign = -1.0 if richtung == "verbindlichkeit" else 1.0
    texts = dict(DEFAULT_TEXTS)
    texts.update(cfg.get("buchung", {}) or {})
    cat_tilgung = texts.get("kategorie_tilgung", "Umbuchung")
    cat_zins = texts.get("kategorie_zins", "Zinsen")
    payee = texts.get("gegenpartei", name)
    loan_txs = ledger.transactions(loan.uuid)
    marks: Dict[str, Tx] = {}
    for t in loan_txs:
        for m in marks_in(t.purpose + " " + t.comment):
            marks.setdefault(m, t)

    # 1. Repayments ---------------------------------------------------------
    erk = cfg.get("erkennung") or {}
    matched = sorted((t for src in sources for t in ledger.transactions(src.uuid) if t.booking_date >= ab and _matches(t, erk)),
                     key=lambda t: (t.booking_date, t.id))
    src_name = {s.uuid: s.name for s in sources}
    ids = {t.id for t in matched}
    claimed: set = set()                                 # bookings of the loan account standing for a payment
    open_pay: List[Tx] = []
    for t in matched:
        hit = marks.get(MARK + "tx-%d" % t.id)
        if hit is not None:
            claimed.add(id(hit))
        else:
            open_pay.append(t)
    # Kontor's repayments whose payment is gone (deleted, or replaced by MoneyMoney) or no longer recognised
    orphans = [t for t in loan_txs if id(t) not in claimed and any(
        _payment_id(m) is not None and _payment_id(m) not in ids for m in marks_in(t.purpose + " " + t.comment))]
    plain = [t for t in loan_txs if not has_mark(t.purpose + " " + t.comment)]
    for t in open_pay:
        amount = round(-t.amount, 2)
        if abs(amount) < 0.005:
            continue
        near = [x for x in orphans + plain if id(x) not in claimed and abs(x.amount - amount) < 0.005
                and abs((x.booking_date - t.booking_date).days) <= SAME_PAYMENT_DAYS]
        if near:                                         # booked already: by you, or by Kontor for the payment it replaced
            claimed.add(id(min(near, key=lambda x: abs((x.booking_date - t.booking_date).days))))
            continue
        tag = MARK + "tx-%d" % t.id
        if _skipped(skip, loan.uuid, tag):
            continue
        if _skipped(hold, loan.uuid, tag) or not seen.new_tx(t):
            waits.append(t.booking_date)
            if auto or _skipped(hold, loan.uuid, tag):
                continue
        purpose = _fill(texts["tilgung_text"], art=payment_kind(t), datum=t.booking_date.strftime("%d.%m.%Y"),
                        quelle=src_name.get(t.account_uuid, ""), betrag=fmt_eur(abs(t.amount)), tag=tag)
        # the payment itself (your bank transaction) is never touched: no comment, no category
        _emit(res, ledger, Proposal(rule, "tilgung", loan.uuid, loan.path, t.booking_date, amount, payee, purpose, cat_tilgung, tag,
                                    retro=not seen.new_tx(t)), edits)
    known_from = getattr(ledger, "since", None)
    for t in orphans:
        if id(t) not in claimed and t.booking_date >= ab and not (known_from and t.booking_date < known_from):
            res.warnings.append(tr("s_tilgung_ohne_zahlung") % (rule, t.booking_date.strftime("%d.%m.%Y"), fmt_eur(t.amount)))

    if cfg.get("erwartet_monatlich", True) and sources:
        recent = [t for t in matched if t.booking_date >= today - timedelta(days=35)]
        if not matched:
            msg = tr("s_s_seit_s_keine_passende") % (
                rule, ab.isoformat(), tr("s_erkennung_pruefen") if today - ab >= timedelta(days=35) else
                tr("s_noch_keine_35_tage_normal"))
            (res.warnings if today - ab >= timedelta(days=35) else res.info).append(msg)
        elif not recent and today - timedelta(days=35) >= ab:
            res.warnings.append(tr("s_s_letzte_erkannte_zahlung_am") %
                                (rule, max(t.booking_date for t in matched).isoformat()))

    # 2. Interest ----------------------------------------------------------
    zins = cfg.get("zins") or {}
    rates = zins.get("satz") or []
    if not rates:
        res.info.append(tr("s_s_kein_zinssatz_hinterlegt_keine") % rule)
        return res
    modell = zins.get("modell", "jahresbasis")
    if modell not in ("jahresbasis", "restschuld_monatlich"):
        res.warnings.append("%s: unbekanntes Zinsmodell '%s'." % (rule, modell))
        return res
    buchungstag = zins.get("buchungstag", "ultimo")
    overrides = {str(k): float(v) for k, v in (zins.get("basis_override") or {}).items()}
    year_cache: Dict[int, Tuple[float, float, float]] = {}   # year -> (basis, rate, yearly interest)

    def year_basis(y: int) -> Tuple[float, float, float]:
        if y not in year_cache:
            rate = _rate_at(rates, date(y, 1, 1))
            prev = date(y - 1, 12, 31)
            if str(y) in overrides:
                base = abs(overrides[str(y)])
            elif ledger.has_history_before(loan.uuid, prev) or ledger.earliest_tx(loan.uuid) is None:
                base = abs(ledger.balance_at(loan.uuid, prev))
            else:
                base = None
            if base is None or rate is None:
                res.warnings.append(tr("s_s_keine_jahresanfangsbasis_kein_zinssa") % (rule, y, y))
                year_cache[y] = (0.0, 0.0, 0.0)
            else:
                year_cache[y] = (base, rate, round(base * rate / 100.0, 2))
                res.info.append(tr("s_zinsbasis_info") %
                                (rule, y, fmt_eur(base), ("%.3f" % rate).rstrip("0").rstrip(".").replace(".", ","),
                                 fmt_eur(year_cache[y][2])))
        return year_cache[y]

    zins_cat = str(cat_zins or "").split("\\")[-1].strip().lower()

    def own_interest(t: Tx) -> bool:
        """Interest you booked yourself: no mark of Kontor, "Zins" in its text or the interest category."""
        if has_mark(t.purpose + " " + t.comment):
            return False
        path = t.mm_category_path if t.mm_category_path is not None else t.category_path
        return "zins" in t.text.lower() or bool(zins_cat and str(path or "").replace("\\", "/").split("/")[-1].strip().lower() == zins_cat)
    own: Dict[Tuple[int, int], List[Tx]] = {}
    for t in loan_txs:
        if own_interest(t):
            own.setdefault((t.booking_date.year, t.booking_date.month), []).append(t)
    own_months: List[str] = []
    for (y, m) in months_between(ab, today):
        if modell == "jahresbasis":
            year_basis(y)
        pay = min((t for t in matched if (t.booking_date.year, t.booking_date.month) == (y, m)), key=lambda t: (t.booking_date, t.id), default=None)
        bday = pay.booking_date if buchungstag == "mit_rate" and pay is not None else month_end(y, m)
        if bday > today or bday < ab:
            continue
        tag = MARK + "zins-%04d-%02d" % (y, m)
        mine = own.get((y, m))
        if tag in marks:
            if mine:                    # Kontor's and yours in the same month: one of them is too much
                res.warnings.append(tr("s_zins_doppelt") % (rule, "%02d/%04d" % (m, y), fmt_eur(mine[0].amount)))
            continue
        if mine:
            own_months.append("%02d/%04d" % (m, y))
            continue
        if _skipped(skip, loan.uuid, tag):
            continue
        new = (seen.after(bday) or (buchungstag == "mit_rate" and pay is not None and seen.new_tx(pay))) and not any(w <= bday for w in waits)
        if not new or _skipped(hold, loan.uuid, tag):
            waits.append(bday)
            if auto or _skipped(hold, loan.uuid, tag):
                continue
        if modell == "jahresbasis":
            base, rate, yearly = year_basis(y)
            if yearly <= 0:
                continue
            per = round(yearly / 12.0, 2)
            interest = round(yearly - 11 * per, 2) if m == 12 else per
        else:
            rate = _rate_at(rates, date(y, m, 1))
            base = abs(ledger.balance_at(loan.uuid, date(y, m, 1) - timedelta(days=1)))
            if rate is None or base <= 0:
                continue
            interest = round(base * rate / 1200.0, 2)
        if interest <= 0:
            continue
        purpose = _fill(texts["zins_text"], monat="%02d/%04d" % (m, y),
                        prozent=("%.3f" % rate).rstrip("0").rstrip(".").replace(".", ","), basis=fmt_eur(base), tag=tag)
        _emit(res, ledger, Proposal(rule, "zins", loan.uuid, loan.path, bday, round(sign * interest, 2), payee, purpose, cat_zins, tag,
                                    retro=not new), edits)
    if own_months:
        res.info.append(tr("s_zins_selbst_gebucht") % (rule, ", ".join(own_months[:12]) + (" …" if len(own_months) > 12 else "")))
    return res


# ---------------------------------------------------------------------------
# Companies: participation (share x value of the company) and account mirrors
# ---------------------------------------------------------------------------

VALUE_OFF = {"eigenkapital", "eventual", "ignorieren"}      # not part of a company's value: partners' equity, contingent, ignored


def parse_start(s):
    """"Buchen ab" of a company: a day ('2025-03-14'), "alles" (since the company exists), older '2025-03' (first of the
    month); anything else (empty: set up before 3.13.1) -> None."""
    s = str(s or "").strip()
    if s == "alles":
        return "alles"
    try:
        parts = [int(x) for x in s.split("-")]
        d = date(parts[0], parts[1], parts[2] if len(parts) > 2 else 1)
    except (ValueError, IndexError):
        return None
    return d if 1990 <= d.year <= 2100 else None


class ValueSeries:
    """Sum of the balances of some accounts at the end of past days, as the balance sheet shows them -- so the bookings match
    it: from the transactions; with the whole history read, an account did not exist before its first transaction; accounts
    whose history comes from their balance (portfolios by default) are unknown. Prefix sums, so many days stay quick.
    Nothing is estimated."""

    def __init__(self, ledger: Ledger, accs, config: Optional[dict] = None, factor: float = 1.0):
        bil = (config or {}).get("bilanz") or {}
        full = int(bil.get("monate_zurueck", 0) or 0) <= 0
        src: Dict[str, str] = {}
        for ref, v in (bil.get("verlauf") or {}).items():
            try:
                src[ledger.resolve(ref).uuid] = v
            except KeyError:
                pass
        self.factor, self.unknown, self.parts, self.now = factor, [], [], 0.0
        days: set = set()
        for a in accs:
            txs = sorted(ledger.transactions(a.uuid), key=lambda t: t.booking_date)
            self.now += a.balance
            if src.get(a.uuid) == "stand" or (a.portfolio and src.get(a.uuid) != "umsaetze"):
                if abs(a.balance) >= 0.005 or txs:
                    self.unknown.append(a.name)
                continue
            dates, sums, run = [], [], 0.0
            for t in txs:
                run += t.amount
                if dates and dates[-1] == t.booking_date:
                    sums[-1] = run
                else:
                    dates.append(t.booking_date); sums.append(run)
            days.update(dates)
            opening = a.balance - run
            self.parts.append((dates, sums, opening, full and bool(dates)))
        self.change_days = sorted(days)

    def at(self, day: Optional[date]) -> Tuple[float, float, List[str]]:
        """(factor x value, value, unknown accounts) at the end of `day`; None: now."""
        if day is None:
            v = round(self.now, 2)
            return round(self.factor * v, 2), v, []
        if self.unknown:
            return 0.0, 0.0, self.unknown
        total = 0.0
        for dates, sums, opening, born in self.parts:
            i = bisect_right(dates, day)
            if born and i == 0:
                continue                    # did not exist yet
            total += opening + (sums[i - 1] if i else 0.0)
        v = round(total, 2)
        return round(self.factor * v, 2), v, []


def past_balances(ledger: Ledger, accs, day: date, config: Optional[dict] = None) -> Tuple[float, List[str]]:
    """Sum of the balances of `accs` at the end of a past `day` (see ValueSeries)."""
    _, v, unknown = ValueSeries(ledger, accs, config).at(day)
    return v, unknown


def _keep_value(ledger: Ledger, res: RuleResult, rule: str, target, series: ValueSeries, cfg: dict, today: date, payee: str,
                purpose, preview: dict, skip: Optional[set], group: str, edits: Optional[Dict[str, dict]], seen: Seen,
                start, fresh_from: Optional[date], auto: bool = False) -> None:
    """Keep the offline account `target` at the value of `series`, from `start` on, every run again from there: on every day
    the value changed (daily, and today) or at every month end (monthly), the difference to its balance in MoneyMoney. A
    balance is the sum of all bookings up to that day, so a booking missing or changed on one day (deleted or edited in
    MoneyMoney, or left out) is made up by one booking on that day -- the ones after it stay as they are. start None: only
    now (daily) or the month just ended (monthly). Days with an unknown value are skipped, nothing is estimated. auto: what
    booking fully automatically books -- an older day waits, the next new one makes it up."""
    schwelle = max(float(cfg.get("schwelle") or 0.01), 0.01)
    monthly = cfg.get("takt") == "monatlich"
    last_end = date(today.year, today.month, 1) - timedelta(days=1)
    days: List[Optional[date]]
    if monthly:
        days = [e for e in (month_end(y, m) for (y, m) in months_between(start, last_end)) if e >= start] if start else [last_end]
    else:
        days = [d for d in sorted({start} | {d for d in series.change_days if d >= start}) if d < today] if start else []
        days.append(None)
    txs = sorted(ledger.transactions(target.uuid), key=lambda t: (t.booking_date, t.id))
    opening = target.balance - sum(t.amount for t in txs)
    used = {m for t in txs for m in marks_in(t.purpose)}
    want_now, src_now, _ = series.at(None)
    preview.update(ziel=target.uuid, ist=round(target.balance, 2), soll=want_now, quelle=src_now, diff=round(want_now - target.balance, 2),
                   rueck=0, rueck_summe=0.0, offen=0, unbekannt=[], takt="monatlich" if monthly else "taeglich",
                   beginn=start.isoformat() if isinstance(start, date) else None)
    unknown_months: List[str] = []
    i, cum, posted = 0, 0.0, 0.0
    for d in days:
        if d is None:
            have = target.balance
        else:
            while i < len(txs) and txs[i].booking_date <= d:
                cum += txs[i].amount
                i += 1
            have = opening + cum + posted
        want, src_value, unknown = series.at(d)
        day = d or today
        if unknown:
            m = day.strftime("%m/%Y")
            if m not in unknown_months:
                unknown_months.append(m)
            continue
        diff = round(want - have, 2)
        if abs(diff) < schwelle:
            continue
        prefix = "%swert-%s-" % (MARK, day.strftime("%Y%m%d"))
        n = 1
        while prefix + str(n) in used:       # the first free number (one deleted in MoneyMoney is free again)
            n += 1
        tag = prefix + str(n)
        if _skipped(skip, target.uuid, tag):          # "Don't book": nothing on this day, the next one makes it up
            continue
        new = d is None or seen.since(d) or (fresh_from is not None and fresh_from <= d)
        if auto and not new:
            continue
        p = Proposal(rule, "wert", target.uuid, target.path, day, diff, payee, purpose(src_value, tag, want), cfg.get("kategorie") or "", tag,
                     group=group, retro=not new)
        t = _emit(res, ledger, p, edits)
        used.add(tag)
        if d is not None:
            posted += t.amount
        preview["offen"] += 1
        if p.retro:
            preview["rueck"] += 1
            preview["rueck_summe"] = round(preview["rueck_summe"] + p.amount, 2)
    if unknown_months:
        preview["unbekannt"] = unknown_months
        res.info.append(tr("s_wert_unbekannt") % (rule, ", ".join(unknown_months[:6]) + (" …" if len(unknown_months) > 6 else ""),
                                                   ", ".join(series.unknown[:3])))
    if monthly:          # what is open now is booked at the end of the month
        preview["diff"] = round(sum(p.amount for p in res.proposals if p.account_uuid == target.uuid), 2)


def _target_ok(ledger: Ledger, config: Optional[dict], res: RuleResult, rule: str, target, inside: set) -> bool:
    if target.group:
        res.warnings.append(tr("s_s_zielkonto_ist_eine_gruppe") % rule)
    elif not ledger.writable(target.uuid, config):
        res.warnings.append(tr("s_s_zielkonto_hat_eine_bankanbindung") % rule)
    elif target.uuid in inside:
        res.warnings.append(tr("s_s_zielkonto_liegt_innerhalb_der") % rule)
    else:
        return True
    return False


def _mirror_of(t: Tx) -> Optional[int]:
    m = re.search(r"#(?:kontor|mm)-gk-(\d+)", (t.purpose or "") + " " + (t.comment or ""))
    return int(m.group(1)) if m else None


def plan_mirror(ledger: Ledger, res: RuleResult, rule: str, a, b, cfg: dict, config: Optional[dict], pv: dict,
                skip: Optional[set] = None, edits: Optional[Dict[str, dict]] = None, group: str = "",
                owner: Optional[Dict[str, str]] = None, seen: Optional[Seen] = None, start=None, auto: bool = False) -> None:
    """Account mirror ("Kontenspiegel", config key gegenkonten; owner: account -> who it belongs to, the sender or recipient
    of a mirrored booking -- the company or person, not the account): every booking of one account from `start` on (a day,
    "alles"; None: what is new since the last check) comes into the other with the opposite sign -- same day, its text, a mark
    naming the original (#kontor-gk-<id>) -- into each side that is an offline account. A mirrored booking is never mirrored
    back, a value adjustment never mirrored. Mirrored is what has its counterpart: by the mark, or booked by hand on both sides
    (same day, same amount, opposite sign -- a mirror is exact); a mirrored booking whose original got a new number in
    MoneyMoney (same day and amount) still counts. Kontor never changes or deletes: a mirrored booking whose original is gone
    or changed is a note to correct it there; one deleted itself is proposed again."""
    seen = seen or Seen()
    sides = [x for x in (a, b) if ledger.writable(x.uuid, config)]
    if not sides:
        res.warnings.append(tr("s_s_spiegel_kein_offline") % (rule, a.name, b.name))
        return
    real = {x.uuid: list(ledger.transactions(x.uuid)) for x in (a, b)}

    def counts(t: Tx) -> bool:
        if start == "alles":
            return True
        if isinstance(start, date):
            return t.booking_date >= start
        return seen.new_tx(t)

    # originals: real bookings from MoneyMoney (their number is known) that are no mirrored ones and no value adjustments
    originals = {x.uuid: [t for t in real[x.uuid] if t.id > 0 and _mirror_of(t) is None and abs(t.amount) >= 0.005
                          and not any(is_value_tag(m) for m in marks_in(t.purpose))] for x in (a, b)}
    by_id = {t.id: t for x in (a, b) for t in originals[x.uuid]}
    other = {a.uuid: b, b.uuid: a}
    known_from = getattr(ledger, "since", None)
    done_ids: set = set()
    marked = 0
    orphans: List[Tuple] = []
    for x in (a, b):
        src = other[x.uuid]
        for m in real[x.uuid]:
            oid = _mirror_of(m)
            if oid is None:
                continue
            o = by_id.get(oid)
            if o is None or o.account_uuid != src.uuid:
                orphans.append((x, src, m, oid))
                continue
            done_ids.add(oid); marked += 1
            if abs(m.amount + o.amount) >= 0.005 or m.booking_date != o.booking_date:
                res.warnings.append(tr("s_s_spiegel_geaendert") % (x.name, m.booking_date.strftime("%d.%m.%Y"), fmt_eur(m.amount), src.name,
                                                                   o.booking_date.strftime("%d.%m.%Y"), fmt_eur(o.amount)))
    for x, src, m, oid in orphans:
        if oid in _all_ids(ledger) or (known_from and m.booking_date < known_from):
            continue                # the mirrored booking of another pair of accounts, or older than what is read
        hit = next((o for o in originals[src.uuid] if o.id not in done_ids and o.booking_date == m.booking_date
                    and abs(o.amount + m.amount) < 0.005), None)
        if hit is not None:         # its original has a new number in MoneyMoney (deleted and entered again, replaced)
            done_ids.add(hit.id); marked += 1
            continue
        res.warnings.append(tr("s_s_spiegel_original_weg") % (x.name, m.booking_date.strftime("%d.%m.%Y"), fmt_eur(m.amount), src.name, x.name))
    # pairs booked by hand on both sides: the same day and amount, each booking in one pair only
    free_b: Dict[Tuple[date, int], List[Tx]] = {}
    for u in originals[b.uuid]:
        if u.id not in done_ids:
            free_b.setdefault((u.booking_date, int(round(u.amount * 100))), []).append(u)
    pairs = 0
    for t in sorted(originals[a.uuid], key=lambda t: (t.booking_date, t.id)):
        if t.id in done_ids:
            continue
        hit = free_b.get((t.booking_date, -int(round(t.amount * 100))))
        if hit:
            u = hit.pop(0)
            done_ids.update((t.id, u.id)); pairs += 1
    booked = 0
    for x in (a, b):
        target = other[x.uuid]
        if target not in sides:
            continue
        for t in sorted(originals[x.uuid], key=lambda t: (t.booking_date, t.id)):
            if t.id in done_ids or not counts(t):
                continue
            tag = MIRROR_TAG + str(t.id)
            if _skipped(skip, target.uuid, tag) or (auto and not seen.new_tx(t)):
                continue
            text = TAG_RE.sub("", (t.purpose or t.name or "")).strip(" ·") or "-"          # the original's own mark stays there
            p = Proposal(rule, "spiegel", target.uuid, target.path, t.booking_date, round(-t.amount, 2), (owner or {}).get(x.uuid) or x.name,
                         _fill(DEFAULT_TEXTS["spiegel_text"], quelle=x.name, text=text, tag=tag), cfg.get("kategorie") or "", tag,
                         group=group, retro=not seen.new_tx(t))
            _emit(res, ledger, p, edits)
            booked += 1
    pv.update(richtung="beide" if len(sides) == 2 else ("zu_a" if sides[0] is a else "zu_b"), gespiegelt=marked + pairs, offen=booked,
              paare=pairs, saldo_a=round(a.balance, 2), saldo_b=round(b.balance, 2),
              beginn=start.isoformat() if isinstance(start, date) else start if start == "alles" else None)


def default_start(ledger: Ledger, cfg: dict, area: dict) -> Optional[date]:
    """For a company set up before 3.13.1 without "Buchen ab": since Kontor's first booking for its rules (the participation's
    value adjustments, the mirrored bookings) -- None if there is none."""
    accs: List[str] = []
    for ref in [cfg.get("beteiligung")] + [x.get(f) for x in cfg.get("gegenkonten") or [] if isinstance(x, dict) for f in ("konto", "quelle")]:
        try:
            accs.append(ledger.resolve(str(ref or "")).uuid)
        except KeyError:
            pass
    return _first_mark(ledger, accs, VALUE_TAGS + (MIRROR_TAG,)) if accs else None


def plan_company(ledger: Ledger, cfg: dict, area: dict, today: date, roles: Optional[Dict[str, str]] = None,
                 config: Optional[dict] = None, skip: Optional[set] = None, edits: Optional[Dict[str, dict]] = None,
                 owner: Optional[Dict[str, str]] = None, seen: Optional[Seen] = None, auto: bool = False) -> RuleResult:
    """One company (an area of the kind "Gesellschaft"): its account mirrors mirror each booking (plan_mirror), then the
    participation account follows share x value of the company (its accounts without the partners' equity) -- so what was
    mirrored into the company counts in its value. Both from "Buchen ab" of the company on (rueckwirkend_ab)."""
    seen = seen or Seen()
    res = RuleResult()
    roles = roles or {}
    name = area["name"]
    inside = {a.uuid for a in area["leaves"]}
    payee = (cfg.get("gegenpartei") or "").strip() or name
    start = parse_start(cfg.get("rueckwirkend_ab"))
    if start is None:
        start = default_start(ledger, cfg, area)
    for i, g in enumerate(cfg.get("gegenkonten") or []):
        if not isinstance(g, dict) or not g.get("konto") or not g.get("quelle"):
            continue
        pv = {"art": "gegenkonto", "bereich": area["id"], "i": i}
        try:
            mine, theirs = ledger.resolve(g["konto"]), ledger.resolve(g["quelle"])
        except KeyError as e:
            res.warnings.append("%s: %s" % (tr("s_regel_gegenkonto") % name, e))
            continue
        rule = tr("s_regel_gegenkonto") % mine.name
        if mine.group or theirs.group:
            res.warnings.append(tr("s_s_quelle_ist_eine_gruppe") % rule)
            continue
        if mine.uuid in inside or theirs.uuid not in inside or mine.uuid == theirs.uuid:
            res.warnings.append(tr("s_s_zielkonto_liegt_innerhalb_der") % rule)
            continue
        who = dict(owner or {})
        who[theirs.uuid] = payee                       # the company (or the counterparty you set for it)
        plan_mirror(ledger, res, rule, mine, theirs, cfg, config, pv, skip, edits, str(area["id"]), who, seen, start, auto)
        res.preview.append(pv)
    if cfg.get("beteiligung"):
        rule = tr("s_regel_beteiligung") % name
        pv = {"art": "beteiligung", "bereich": area["id"]}
        try:
            target = ledger.resolve(cfg["beteiligung"])
        except KeyError as e:
            res.warnings.append("%s: %s" % (rule, e))
            target = None
        anteil = area.get("anteil")
        if target is not None and anteil is None:
            res.warnings.append(tr("s_s_anteil_fehlt") % rule)
        elif target is not None and _target_ok(ledger, config, res, rule, target, inside):
            accs = [a for a in area["leaves"] if roles.get(a.uuid) not in VALUE_OFF]
            share = float(anteil)
            pct = ("%.4f" % (share * 100)).rstrip("0").rstrip(".").replace(".", ",")
            series = ValueSeries(ledger, accs, config, share)
            begin = (series.change_days[0] if series.change_days else None) if start == "alles" else start
            # a value that changed through a new transaction of the company (or a new booking planned now) is new on its day
            fresh_from = None if seen.max_id is None else min(
                (t.booking_date for a in accs for t in ledger.transactions(a.uuid) if seen.new_tx(t)), default=None)
            _keep_value(ledger, res, rule, target, series, cfg, today, payee,
                        lambda v, tag, want: _fill(DEFAULT_TEXTS["wert_text"], anteil=pct, quelle=name, wert=fmt_eur(v), soll=fmt_eur(want), tag=tag),
                        pv, skip, str(area["id"]), edits, seen, begin, fresh_from, auto)
            res.preview.append(pv)
    return res


# ---------------------------------------------------------------------------
# All rules of a configuration
# ---------------------------------------------------------------------------

def plan_all(ledger: Ledger, config: dict, today: date, hold: Optional[set] = None, edits: Optional[Dict[str, dict]] = None,
             seen: Optional[Seen] = None, auto: bool = False) -> RuleResult:
    """All rules on the ledger (it receives the planned bookings). Not proposed: your "Don't book" (config nicht_buchen) and
    hold (left out of this run: what follows is planned without it). edits: your changes from the approval. seen: what is new
    since the last check. auto: what booking fully automatically books -- only what is new, everything after an older
    booking planned without it (in one pass)."""
    total = RuleResult()
    skip = not_booked_keys(config)
    hold = set(hold or ())

    def add(r: RuleResult) -> None:
        total.proposals += r.proposals; total.warnings += r.warnings; total.info += r.info; total.preview += r.preview
    # order: loans first (they change the values of the companies), then mirrors and participations
    for i, cfg in enumerate(config.get("darlehen", []) or []):
        if cfg.get("aktiv", True):
            r = plan_loan(ledger, cfg, today, config, skip, edits, seen, hold, auto)
            r.preview.append({"art": "darlehen", "i": i, "buchungen": len(r.proposals)})
            add(r)
    if config.get("gesellschaften"):
        from report import account_roles          # imported late (report/core import rules)
        from core import bereiche_for
        roles = account_roles(ledger, config)
        areas = {b["id"]: b for b in bereiche_for(ledger, config)}
        owner = {a.uuid: b["name"] for b in areas.values() for a in b["leaves"]}          # an account's area: the company or person
        for cfg in config.get("gesellschaften") or []:
            if not isinstance(cfg, dict) or not (cfg.get("beteiligung") or cfg.get("gegenkonten")):
                continue
            area = areas.get(str(cfg.get("bereich")))
            if area is None:
                total.warnings.append(tr("s_gesellschaft_s_bereich_fehlt") % cfg.get("bereich"))
                continue
            add(plan_company(ledger, cfg, area, today, roles, config, skip | hold, edits, owner, seen, auto))
    return total
