"""Booking rules: loans (repayment and interest), and per company the value of your participation and account mirrors.

Stateless: every run derives everything from MoneyMoney and the settings. What is booked already is recognised by the mark in
its purpose (#kontor-tx-<id>, #kontor-zins-YYYY-MM, #kontor-wert-..., #kontor-gk-<id>) or by an equal
booking you made yourself. Kontor keeps no list of its own bookings, so nothing can get out of step with MoneyMoney: a booking
deleted there is simply missing again, one changed there (with its mark) counts as it is now. Kept are only your decisions
"Don't book" (settings: not_book) and up to where Kontor had looked when it last booked on its own (Seen).

Each rule returns proposals and notes; it never changes MoneyMoney itself (that is core.apply_proposals).
"""
from __future__ import annotations

import re
from bisect import bisect_right
from itertools import accumulate
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from model import MARK, TAG_RE, Ledger, Tx, cents, fmt_eur, has_mark, marks_in, month_end, months_between, norm_cat, part
from i18n import tr


def bkey(account_uuid: str, tag: str) -> str:
    """A booking of Kontor: account and mark (the same mark, e.g. interest of a month, exists once per account)."""
    return "%s|%s" % (account_uuid, tag)


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
    note: str = ""            # something to look at before booking (a possible counterpart booked by hand): never booked on its own
    pair: str = ""            # the other half of such a hand-made pair: the key of its own proposal (turned down together)

    @property
    def key(self) -> str:
        return bkey(self.account_uuid, self.tag)


@dataclass
class RuleResult:
    proposals: List[Proposal] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)
    preview: List[dict] = field(default_factory=list)     # per rule: target, actual, what is open (interface)
    waiting: List[str] = field(default_factory=list)     # keys left out with a booking you left out (a loan's interest after it)


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


VALUE_TAGS = (MARK + "wert-",)
MIRROR_TAG = MARK + "gk-"
EDIT_AMOUNT = ("repayment", "interest")       # kinds whose amount and date you may change before approving (the others follow MoneyMoney)


def is_value_tag(tag) -> bool:
    """A value adjustment (participation): always the difference to the balance, never a fixed amount."""
    return str(tag or "").startswith(VALUE_TAGS)


def present_marks(ledger: Ledger) -> set:
    """(account, mark) of Kontor's bookings that are in MoneyMoney (not the ones planned in this run)."""
    return {(t.account_uuid, m) for t in ledger.txs if not getattr(t, "planned", False) for m in marks_in(t.purpose)}


def not_booked_keys(config: Optional[dict]) -> set:
    """Your "Don't book" decisions (settings: nicht_buchen), as account|mark."""
    out = set()
    for x in (config or {}).get("not_book") or []:
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
        if ch.get("amount") is not None:
            p.amount = round(float(ch["amount"]), 2)
        if ch.get("date"):
            p.booking_date = date.fromisoformat(str(ch["date"]))
    if ch.get("purpose") is not None:
        text = TAG_RE.sub("", str(ch["purpose"])).strip(" ·")
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
    for r in sorted(rates, key=lambda x: x.get("from_date", "0000-00-00")):
        ab = date.fromisoformat(r["from_date"]) if r.get("from_date") else date(1900, 1, 1)
        if ab <= day:
            best = float(r["percent"])
    return best


STALE_MIN = 1.0             # booked interest off by less than this is not noted (e.g. after you set the bank's amount before it)


def _pct(rate: float) -> str:
    """A rate as Kontor writes it into its booking text: as entered (up to six places), with a comma."""
    return ("%.6f" % rate).rstrip("0").rstrip(".").replace(".", ",")


def _interest_of(modell: str, base: float, rate: float, m: int) -> float:
    """A month's interest as Kontor books it: on the base of the year (1/12, December with the cent left over) or on the debt
    at the end of the month before -- computed exactly, then rounded to the cent (model.part)."""
    if modell == "yearly_base":
        yearly = part(base, rate, 100)
        per = part(yearly, 1, 12)
        return cents(yearly - 11 * per) if m == 12 else per
    return part(base, rate, 1200)


def _interest_floats(modell: str, base: float, rate: float, m: int) -> float:
    """A month's interest as Kontor booked it up to 3.16.99: multiplied as floats and then rounded -- at half a cent now and then
    a cent less than _interest_of. Only to know such a booking as Kontor's own (never booked anew, never noted for that cent)."""
    if modell == "yearly_base":
        yearly = cents(base * rate / 100.0)
        per = cents(yearly / 12.0)
        return cents(yearly - 11 * per) if m == 12 else per
    return cents(base * rate / 1200.0)


def _written_interest(template: str, purpose: str, month: str, tag: str) -> Optional[Tuple[float, float]]:
    """(base, rate) as Kontor wrote them into its interest booking ("… % p.a. auf … €"); None: not to be read (a text of yours,
    or one without them) -- then nothing is compared."""
    parts, seen = re.split(r"\{(\w+)\}", template), set()
    pat = ""
    for i, p in enumerate(parts):
        if i % 2 == 0:
            pat += re.escape(p)
        elif p in ("base", "percent") and p not in seen:
            seen.add(p)
            pat += r"(?P<base>\d{1,3}(?:\.\d{3})*,\d{2} €)" if p == "base" else r"(?P<percent>\d+(?:,\d+)?)"
        else:
            pat += re.escape({"month": month, "tag": tag}.get(p, "")) if p in ("month", "tag") else ".*?"
    if seen != {"base", "percent"}:
        return None
    hit = re.search(pat, purpose or "")
    if not hit:
        return None
    return (float(hit.group("base")[:-2].replace(".", "").replace(",", ".")), float(hit.group("percent").replace(",", ".")))


def _matches(t: Tx, erk: dict) -> bool:
    ibans = erk.get("counter_iban") or []
    if isinstance(ibans, str):
        ibans = [ibans]
    ibans = [i.replace(" ", "").upper() for i in ibans if i]
    texts = erk.get("text_contains") or []
    if isinstance(texts, str):
        texts = [texts]
    if not ibans and not texts:
        return False
    hit_iban = bool(ibans) and t.counter_iban in ibans
    hit_text = bool(texts) and any(s.lower() in t.text.lower() for s in texts)
    if not (hit_iban or hit_text):
        return False
    excl = erk.get("exclude_text") or []
    if isinstance(excl, str):
        excl = [excl]
    if excl and any(x.lower() in t.text.lower() for x in excl):
        return False
    richtung = erk.get("direction", "outflow")
    if richtung == "outflow" and t.amount >= 0:
        return False
    if richtung == "inflow" and t.amount <= 0:
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
    "repayment_text": "{kind} {date} von {source} · {tag}",
    "interest_text": "Zinsen {month} · {percent} % p.a. auf {base} · {tag}",
    "value_text": "Anteilswertanpassung: {share} % × {value} (Wert {source}) = {target} · {tag}",
    "mirror_text": "{text} · gespiegelt von {source} · {tag}",
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
    held: List[date] = []                                # ... of those you left out of this approval
    res = RuleResult()
    name = cfg.get("name") or cfg.get("loan_account")
    rule = "Darlehen „%s“" % name                    # your name quoted: "Darlehen „Darlehen Immo A“"
    try:
        loan = ledger.resolve(cfg["loan_account"])
        sources = [ledger.resolve(s) for s in cfg.get("source_accounts", [])]
    except KeyError as e:
        res.warnings.append("%s: %s" % (rule, e))
        return res
    if loan.group:
        res.warnings.append(tr("s_s_darlehenskonto_ist_eine_gruppe") % rule)
        return res
    if not ledger.writable(loan.uuid, config):
        res.warnings.append(tr("s_s_konto_hat_eine_bankanbindung") % rule)
        return res

    ab = date.fromisoformat(cfg["from_date"])
    richtung = cfg.get("kind", "liability")       # verbindlichkeit | forderung
    sign = -1.0 if richtung == "liability" else 1.0
    texts = dict(DEFAULT_TEXTS)
    texts.update(cfg.get("booking", {}) or {})
    cat_tilgung = texts.get("category_repayment", "Umbuchung")
    cat_zins = texts.get("category_interest", "Zinsen")
    payee = texts.get("counterparty", name)
    loan_txs = ledger.transactions(loan.uuid)
    marks: Dict[str, Tx] = {}
    again: List[Tx] = []                                 # Kontor's repayment a second time (its mark twice in MoneyMoney)
    for t in loan_txs:
        for m in marks_in(t.purpose + " " + t.comment):
            if marks.setdefault(m, t) is not t and _payment_id(m) is not None and t not in again:
                again.append(t)
    for t in again:                                      # one is too many: named, and counted once (the debt, see fixes)
        res.warnings.append(tr("s_buchung_doppelt") % (rule, t.booking_date.strftime("%d.%m.%Y"), fmt_eur(t.amount), loan.name))

    # 1. Repayments ---------------------------------------------------------
    erk = cfg.get("detection") or {}
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
            if _skipped(hold, loan.uuid, tag):
                held.append(t.booking_date)
            if auto or _skipped(hold, loan.uuid, tag):
                continue
        purpose = _fill(texts["repayment_text"], kind=payment_kind(t), date=t.booking_date.strftime("%d.%m.%Y"),
                        source=src_name.get(t.account_uuid, ""), amount=fmt_eur(abs(t.amount)), tag=tag)
        # the payment itself (your bank transaction) is never touched: no comment, no category
        _emit(res, ledger, Proposal(rule, "repayment", loan.uuid, loan.path, t.booking_date, amount, payee, purpose, cat_tilgung, tag,
                                    retro=not seen.new_tx(t)), edits)
    known_from = getattr(ledger, "since", None)
    for t in orphans:
        if id(t) not in claimed and t.booking_date >= ab and not (known_from and t.booking_date < known_from):
            res.warnings.append(tr("s_tilgung_ohne_zahlung") % (rule, t.booking_date.strftime("%d.%m.%Y"), fmt_eur(t.amount)))

    if cfg.get("expected_monthly", True) and sources:
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
    zins = cfg.get("interest") or {}
    rates = zins.get("rate_list") or []
    if not rates:
        res.info.append(tr("s_s_kein_zinssatz_hinterlegt_keine") % rule)
        return res
    modell = zins.get("model", "yearly_base")
    if modell not in ("yearly_base", "remaining_debt_monthly"):
        res.warnings.append(tr("s_zinsmodell_unbekannt") % (rule, modell))
        return res
    buchungstag = zins.get("booking_day", "ultimo")
    overrides = {str(k): float(v) for k, v in (zins.get("base_override") or {}).items()}
    year_cache: Dict[int, Tuple[float, float, float]] = {}   # year -> (basis, rate, yearly interest)
    # only the last months read (as ValueSeries): a balance before the first booking read comes from bookings before them --
    # with everything read, the account did not exist before its first booking (a start balance alone is no base)
    limited = int(((config or {}).get("balance") or {}).get("months_back", 0) or 0) > 0

    def year_basis(y: int) -> Tuple[float, float, float]:
        if y not in year_cache:
            rate = _rate_at(rates, date(y, 1, 1))
            prev = date(y - 1, 12, 31)
            if str(y) in overrides:
                base = abs(overrides[str(y)])
            elif ledger.has_history_before(loan.uuid, prev) or ledger.earliest_tx(loan.uuid) is None \
                    or (limited and abs(ledger.balance_at(loan.uuid, prev)) >= 0.005):   # a balance then: bookings before what was read
                base = debt_fixed(prev)
            else:
                base = None
            if base is None or rate is None:
                res.warnings.append(tr("s_s_keine_jahresanfangsbasis_kein_zinssa") % (rule, y, y))
                year_cache[y] = (0.0, 0.0, 0.0)
            else:
                year_cache[y] = (base, rate, part(base, rate, 100))
                res.info.append(tr("s_zinsbasis_info") %
                                (rule, y, fmt_eur(base), _pct(rate), fmt_eur(year_cache[y][2])))
        return year_cache[y]

    zins_cat = norm_cat(str(cat_zins or "")).split(" / ")[-1].lower()           # its name ('Zinsen/Gebühren' stays whole)

    def own_interest(t: Tx) -> bool:
        """Interest you booked yourself: no mark of Kontor, "Zins" in its text or the interest category."""
        if has_mark(t.purpose + " " + t.comment):
            return False
        path = t.mm_category_path if t.mm_category_path is not None else t.category_path
        return "zins" in t.text.lower() or bool(zins_cat and norm_cat(str(path or "")).split(" / ")[-1].lower() == zins_cat)
    own: Dict[Tuple[int, int], List[Tx]] = {}
    for t in loan_txs:
        if own_interest(t):
            own.setdefault((t.booking_date.year, t.booking_date.month), []).append(t)
    own_months: List[str] = []
    # Kontor's interest booked on a debt that has changed since (a payment entered later, a repayment proposed again, a rate
    # changed): it is never changed -- a note with the right amounts. Only what is still as Kontor booked it (an amount you
    # set, e.g. the bank's, is yours). Each right amount, and every new interest, counts the ones before it as corrected:
    # one round of changes as noted fits. Not noted after something unclear: a booking of this loan that waits (not in this
    # plan), or interest twice in a month
    fixes: List[Tuple[date, float]] = [(t.booking_date, round(-t.amount, 2)) for t in again]      # a repayment twice: the debt as if once
    stale: List[str] = []
    unclear: List[date] = [t.booking_date for t in again]

    def owed_at(day: date) -> float:
        """What is owed that day (a loan given: what is owed to you); below 0: overpaid."""
        return (ledger.balance_at(loan.uuid, day) + sum(d for t, d in fixes if t <= day)) * sign

    def debt_fixed(day: date) -> float:
        """What is owed that day -- never below 0: past zero the loan is overpaid, and an overpayment bears no interest
        (decided 2026-11-23)."""
        return max(0.0, owed_at(day))

    def paid_off(y: int, m: int) -> bool:
        """Nothing owed before this month (repaid or overpaid): no interest for it, in either model -- in the yearly one the
        year's base no longer applies once the loan is gone; a base you set for the year applies as set."""
        if modell == "yearly_base" and str(y) in overrides:
            return False
        return owed_at(date(y, m, 1) - timedelta(days=1)) <= 0.005

    per_cache: Dict[int, float] = {}

    def monthly(y: int) -> float:
        """A month's interest on the base of year y: a twelfth of the year's, to the cent. Where Kontor booked months of this
        year a cent off (computed with floats up to 3.16.99), the year goes on with that amount -- so its twelve months still
        add up to the year's interest, December taking what is left."""
        if y not in per_cache:
            base, rate, yearly = year_basis(y)
            per = part(yearly, 1, 12)
            old = _interest_floats(modell, base, rate, 1)
            if old != per and any(abs(abs(marks[k].amount) - old) < 0.005 for k in (MARK + "zins-%04d-%02d" % (y, i) for i in range(1, 12)) if k in marks):
                per = old
            per_cache[y] = per
        return per_cache[y]

    for (y, m) in months_between(ab, today):
        if modell == "yearly_base":
            year_basis(y)
        pay = min((t for t in matched if (t.booking_date.year, t.booking_date.month) == (y, m)), key=lambda t: (t.booking_date, t.id), default=None)
        bday = pay.booking_date if buchungstag == "with_payment" and pay is not None else month_end(y, m)
        if bday > today or bday < ab:
            continue
        tag = MARK + "zins-%04d-%02d" % (y, m)
        mine = own.get((y, m))
        if tag in marks:
            twice = [t for t in loan_txs if tag in marks_in(t.purpose + " " + t.comment)][1:]
            if mine or twice:           # Kontor's and yours in the same month, or Kontor's twice: one of them is too much
                res.warnings.append(tr("s_zins_doppelt") % (rule, "%02d/%04d" % (m, y), fmt_eur((mine or twice)[0].amount)))
                unclear.append(min(t.booking_date for t in [marks[tag]] + (mine or twice)))
                fixes.extend((t.booking_date, round(-t.amount, 2)) for t in twice)      # Kontor's twice: the debt as if once
                continue
            start = date(y, 1, 1) if modell == "yearly_base" else date(y, m, 1)       # the day its base is taken before
            if not (modell == "yearly_base" and str(y) in overrides) and any(d < start for d in unclear + held + (waits if auto else [])):
                continue
            was = _written_interest(texts["interest_text"], marks[tag].purpose, "%02d/%04d" % (m, y), tag)
            if modell == "yearly_base":
                known = year_basis(y)[0] > 0 or year_basis(y)[1] > 0
                rate_now, base_now = year_basis(y)[1], year_basis(y)[0]
            else:
                rate_now = _rate_at(rates, date(y, m, 1))
                base_now = debt_fixed(date(y, m, 1) - timedelta(days=1))
                known = rate_now is not None
            if was is not None and known and rate_now is not None:
                then = _interest_of(modell, was[0], was[1], m)
                now = 0.0 if paid_off(y, m) else _interest_of(modell, base_now, rate_now, m)
                if abs(marks[tag].amount - sign * then) >= 0.005:          # as Kontor computed it up to 3.16.99: its own as well
                    then = _interest_floats(modell, was[0], was[1], m)
                if abs(marks[tag].amount - sign * then) < 0.005 and abs(now - then) >= STALE_MIN:
                    stale.append(tr("s_zins_statt") % ("%02d/%04d" % (m, y), fmt_eur(sign * now), fmt_eur(sign * then)))
                    fixes.append((marks[tag].booking_date, round(sign * (now - then), 2)))
            continue
        if mine:
            own_months.append("%02d/%04d" % (m, y))
            continue
        if _skipped(skip, loan.uuid, tag):
            continue
        # computed from the balance before it (the month before, or the year before): a booking before that which you left out
        # of this approval holds it back too -- else it would be booked from a balance without it, and never adjusted later.
        # Not with a base you set for the year (it does not come from the balance)
        if not (modell == "yearly_base" and str(y) in overrides) and any(h < (date(y, 1, 1) if modell == "yearly_base" else date(y, m, 1)) for h in held):
            held.append(bday)
            res.waiting.append(bkey(loan.uuid, tag))
            continue
        new = (seen.after(bday) or (buchungstag == "with_payment" and pay is not None and seen.new_tx(pay))) and not any(w <= bday for w in waits)
        if not new or _skipped(hold, loan.uuid, tag):
            waits.append(bday)
            if _skipped(hold, loan.uuid, tag):
                held.append(bday)
            if auto or _skipped(hold, loan.uuid, tag):
                continue
        if paid_off(y, m):
            continue                                     # nothing owed (repaid or overpaid): no interest
        if modell == "yearly_base":
            base, rate, yearly = year_basis(y)
            if yearly <= 0:
                continue
            per = monthly(y)
            whole = not any(paid_off(y, k) for k in range(1, 12))
            interest = cents(yearly - 11 * per) if m == 12 and whole else per
        else:
            rate = _rate_at(rates, date(y, m, 1))
            base = debt_fixed(date(y, m, 1) - timedelta(days=1))           # as if the interest noted above were corrected
            if rate is None or base <= 0:
                continue
            interest = part(base, rate, 1200)
        if interest <= 0:
            continue
        purpose = _fill(texts["interest_text"], month="%02d/%04d" % (m, y),
                        percent=_pct(rate), base=fmt_eur(base), tag=tag)
        _emit(res, ledger, Proposal(rule, "interest", loan.uuid, loan.path, bday, round(sign * interest, 2), payee, purpose, cat_zins, tag,
                                    retro=not new), edits)
    if own_months:
        res.info.append(tr("s_zins_selbst_gebucht") % (rule, ", ".join(own_months[:12]) + (" …" if len(own_months) > 12 else "")))
    if stale:
        res.warnings.append(tr("s_zins_veraltet") % (rule, ", ".join(stale)))
    if owed_at(today) < -0.005 and not (modell == "yearly_base" and str(today.year) in overrides):
        # overpaid now (only then the note; not with a base you set for the year, which applies as set): the month it became
        # so -- back over the month ends it already was, as far as the loan's bookings go
        first = ledger.earliest_tx(loan.uuid) or ab
        y, m = today.year, today.month
        for _ in range(600):
            end = date(y, m, 1) - timedelta(days=1)
            if end < first or owed_at(end) >= -0.005:
                break
            y, m = end.year, end.month
        res.warnings.append(tr("s_darlehen_ueberzahlt") % (rule, "%02d/%04d" % (m, y)))
    return res


# ---------------------------------------------------------------------------
# Companies: participation (share x value of the company) and account mirrors
# ---------------------------------------------------------------------------

VALUE_OFF = {"contingent", "ignore"}      # not part of a company's value: contingent, ignored


def parse_start(s):
    """"Buchen ab" of a company or mirror: a day ('2025-03-14') or "all" (since it exists); anything else (empty: none set) -> None."""
    s = str(s or "").strip()
    if s == "all":
        return "all"
    try:
        d = date.fromisoformat(s)
    except ValueError:
        return None
    return d if 1990 <= d.year <= 2100 else None


def _seq(t: Tx) -> int:
    """The order transactions came in: MoneyMoney's number; one planned in this run (or just written) after all read ones."""
    return t.id if t.id > 0 else 10 ** 15 - t.id


class ValueSeries:
    """Sum of the balances of some accounts at the end of past days, as the balance sheet shows them -- so the bookings match
    it: from the transactions; with the whole history read, an account did not exist before its first transaction; accounts
    whose history comes from their balance (portfolios by default) are unknown. Prefix sums, so many days stay quick.
    Nothing is estimated. factor x value: computed exactly, then rounded to the cent (model.part)."""

    def __init__(self, ledger: Ledger, accs, config: Optional[dict] = None, factor: float = 1.0):
        bil = (config or {}).get("balance") or {}
        full = int(bil.get("months_back", 0) or 0) <= 0
        src: Dict[str, str] = {}
        for ref, v in (bil.get("history_source") or {}).items():
            try:
                src[ledger.resolve(ref).uuid] = v
            except KeyError:
                pass
        self.factor, self.unknown, self.foreign, self.parts, self.now = factor, [], [], [], 0.0
        days: set = set()
        came: List[Tuple[date, int]] = []
        for a in accs:
            txs = sorted(ledger.transactions(a.uuid), key=lambda t: t.booking_date)
            if (a.currency or "EUR").upper() != "EUR":          # kept in another currency: Kontor does not convert (no rates, no
                if abs(a.balance) >= 0.005 or txs:              # estimate) -- the value is unknown, also the one of today
                    self.foreign.append(a.name)
                continue
            self.now += a.balance
            if src.get(a.uuid) == "balances" or (a.portfolio and src.get(a.uuid) != "transactions"):
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
            came.extend((t.booking_date, _seq(t)) for t in txs)
            opening = a.balance - run
            self.parts.append((dates, sums, opening, full and bool(dates)))
        self.change_days = sorted(days)
        came.sort()
        self._came_days, self._came_top = [d for d, _ in came], list(accumulate((n for _, n in came), max))

    def newest(self, day: Optional[date]) -> int:
        """The latest of these accounts' transactions up to `day` (None: of all), by the order they came in (_seq); 0: none."""
        i = len(self._came_days) if day is None else bisect_right(self._came_days, day)
        return self._came_top[i - 1] if i else 0

    def at(self, day: Optional[date]) -> Tuple[float, float, List[str]]:
        """(factor x value, value, unknown accounts) at the end of `day`; None: now."""
        if day is None:
            if self.foreign:
                return 0.0, 0.0, self.foreign
            v = round(self.now, 2)
            return part(v, self.factor), v, []
        if self.unknown or self.foreign:
            return 0.0, 0.0, self.unknown + self.foreign
        total = 0.0
        for dates, sums, opening, born in self.parts:
            i = bisect_right(dates, day)
            if born and i == 0:
                continue                    # did not exist yet
            total += opening + (sums[i - 1] if i else 0.0)
        v = round(total, 2)
        return part(v, self.factor), v, []


def _keep_value(ledger: Ledger, res: RuleResult, rule: str, target, series: ValueSeries, cfg: dict, today: date, payee: str,
                purpose, preview: dict, skip: Optional[set], group: str, edits: Optional[Dict[str, dict]], seen: Seen,
                start, fresh_from: Optional[date], auto: bool = False) -> None:
    """Keep the offline account `target` at the value of `series`, from `start` on, every run again from there: on every day
    the value changed (daily, and today) or at every month end (monthly), the difference to its balance in MoneyMoney. A
    balance is the sum of all bookings up to that day, so a booking missing or changed on one day (deleted or edited in
    MoneyMoney, or left out) is made up by one booking on that day -- the ones after it stay as they are. start None: only
    now (daily) or the month just ended (monthly). Days with an unknown value are skipped, nothing is estimated. auto: what
    booking fully automatically books -- an older day waits, the next new one makes it up."""
    schwelle = max(float(cfg.get("threshold") or 0.01), 0.01)
    monthly = cfg.get("cycle") == "monthly"
    last_end = date(today.year, today.month, 1) - timedelta(days=1)
    days: List[Optional[date]]
    if monthly:
        days = [e for e in (month_end(y, m) for (y, m) in months_between(start, last_end)) if e >= start] if start else [last_end]
    else:
        days = [d for d in sorted({start} | {d for d in series.change_days if d >= start}) if d < today] if start else []
        days.append(None)
    txs = sorted(ledger.transactions(target.uuid), key=lambda t: (t.booking_date, t.id))
    opening = target.balance - sum(t.amount for t in txs)
    used: set = set()
    again: List[Tx] = []                                 # a value adjustment of Kontor's a second time (its mark twice in MoneyMoney)
    for t in txs:
        ms = [m for m in marks_in(t.purpose) if is_value_tag(m)]
        if ms and all(m in used for m in ms):
            again.append(t)
        used.update(marks_in(t.purpose))
    for t in again:                                      # one is too many: named, and the balance taken as if it were there once
        res.warnings.append(tr("s_buchung_doppelt") % (rule, t.booking_date.strftime("%d.%m.%Y"), fmt_eur(t.amount), target.name))
    if again:
        txs = [t for t in txs if not any(t is x for x in again)]
    twice = round(sum(t.amount for t in again), 2)
    mine = sorted((t.booking_date, _seq(t)) for t in txs if any(is_value_tag(m) for m in marks_in(t.purpose)))
    mine_days, mine_top = [x for x, _ in mine], list(accumulate((n for _, n in mine), max))

    def stays(d: Optional[date], have: float, value: float) -> bool:
        """A balance at share x value as Kontor computed it up to 3.16.99 (as floats: half a cent went up or down), with nothing
        new in the company since Kontor's last value adjustment: it stays -- nothing booked moves for that cent. The next
        change is booked to the exact value."""
        if abs(round(series.factor * value, 2) - have) >= 0.005:
            return False
        i = len(mine_days) if d is None else bisect_right(mine_days, d)
        return i > 0 and mine_top[i - 1] > series.newest(d)
    want_now, src_now, unknown_now = series.at(None)
    if abs(want_now - target.balance) >= 0.005 and not unknown_now and stays(None, round(target.balance - twice, 2), src_now):
        want_now = round(target.balance - twice, 2)
    preview.update(target=target.uuid, ist=round(target.balance, 2), soll=want_now, source=src_now, diff=round(want_now - target.balance, 2),
                   retro_count=0, back_sum=0.0, open=0, unknown=[], cycle="monthly" if monthly else "daily",
                   begin=start.isoformat() if isinstance(start, date) else None)
    if unknown_now:          # an account in another currency: no value is known, on no day -- nothing is booked, and it says why
        preview.update(soll=None, source=None, diff=None)
        res.warnings.append(tr("s_wert_fremdwaehrung") % (rule, ", ".join(unknown_now[:3])))
        return
    unknown_months: List[str] = []
    i, cum, posted = 0, 0.0, 0.0
    for d in days:
        if d is None:
            have = round(target.balance - twice, 2)
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
        if abs(diff) < schwelle or stays(d, have, src_value):
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
        p = Proposal(rule, "value", target.uuid, target.path, day, diff, payee, purpose(src_value, tag, want), cfg.get("category") or "", tag,
                     group=group, retro=not new)
        t = _emit(res, ledger, p, edits)
        used.add(tag)
        if d is not None:
            posted += t.amount
        preview["open"] += 1
        if p.retro:
            preview["retro_count"] += 1
            preview["back_sum"] = round(preview["back_sum"] + p.amount, 2)
    if unknown_months:
        preview["unknown"] = unknown_months
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
    m = re.search(r"#kontor-gk-(\d+)", (t.purpose or "") + " " + (t.comment or ""))
    return int(m.group(1)) if m else None


def plan_mirror(ledger: Ledger, res: RuleResult, rule: str, a, b, cfg: dict, config: Optional[dict], pv: dict,
                skip: Optional[set] = None, edits: Optional[Dict[str, dict]] = None, group: str = "",
                owner: Optional[Dict[str, str]] = None, seen: Optional[Seen] = None, start=None, auto: bool = False) -> None:
    """Account mirror ("Kontenspiegel", config key gegenkonten; owner: account -> who it belongs to, the sender or recipient
    of a mirrored booking -- the company or person, not the account): every booking of one account from `start` on (a day,
    "alles"; None: what is new since the last check) comes into the other with the opposite sign -- same day, its text, a mark
    naming the original (#kontor-gk-<id>) -- into each side that is an offline account. A mirrored booking is never mirrored
    back, a value adjustment never mirrored. Mirrored is what has its counterpart: by the mark, or booked by hand on both sides
    (same day, same amount, opposite sign -- a mirror is exact; days apart, as the two ends of a transfer between banks entered
    on their days: the proposal names the possible counterpart and waits for you); a mirrored booking whose original got a new number in
    MoneyMoney (same amount, same day -- or up to MIRROR_MOVED_DAYS away if you moved it, then a note) still counts. Kontor never changes or deletes: a mirrored booking whose original is gone
    or changed is a note to correct it there; one deleted itself is proposed again."""
    seen = seen or Seen()
    sides = [x for x in (a, b) if ledger.writable(x.uuid, config)]
    if not sides:
        res.warnings.append(tr("s_s_spiegel_kein_offline") % (rule, a.name, b.name))
        return
    real = {x.uuid: list(ledger.transactions(x.uuid)) for x in (a, b)}

    def counts(t: Tx) -> bool:
        if start == "all":
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
            if oid in done_ids:                          # mirrored a second time (its mark twice in MoneyMoney): one is too many
                res.warnings.append(tr("s_buchung_doppelt") % (rule, m.booking_date.strftime("%d.%m.%Y"), fmt_eur(m.amount), x.name))
                continue
            done_ids.add(oid); marked += 1
            if abs(m.amount + o.amount) >= 0.005 or m.booking_date != o.booking_date:
                res.warnings.append(tr("s_s_spiegel_geaendert") % (x.name, m.booking_date.strftime("%d.%m.%Y"), fmt_eur(m.amount), src.name,
                                                                   o.booking_date.strftime("%d.%m.%Y"), fmt_eur(o.amount)))
    cents = lambda t: int(round(t.amount * 100))
    refused = not_booked_keys(config)
    free = lambda t, x: bkey(other[x.uuid].uuid, MIRROR_TAG + str(t.id)) not in refused
    live = [(x, src, m) for x, src, m, oid in orphans if not (oid in _all_ids(ledger) or (known_from and m.booking_date < known_from))]
    # its original has a new number in MoneyMoney (deleted and entered again, replaced): first the booking of that amount on the
    # same day (not one whose mirror you turned down); the rest after the pairs booked by hand below
    rest = []
    for x, src, m in live:
        hit = next((o for o in originals[src.uuid] if o.id not in done_ids and free(o, src) and o.booking_date == m.booking_date
                    and abs(o.amount + m.amount) < 0.005), None)
        if hit is not None:
            done_ids.add(hit.id); marked += 1
        else:
            rest.append((x, src, m))
    # pairs booked by hand on both sides: the same day, the same amount with the opposite sign, each booking in one pair only;
    # not a booking whose mirror you turned down ("Don't book" -- it must not swallow another). Days apart (the two ends of a
    # transfer between banks, entered on their days -- only in what was there before the mirror): no pair, the proposal names
    # the possible counterpart and waits for your approval
    free_b: Dict[Tuple[date, int], List[Tx]] = {}
    for u in sorted(originals[b.uuid], key=lambda t: (t.booking_date, t.id)):
        if u.id not in done_ids and free(u, b):
            free_b.setdefault((u.booking_date, cents(u)), []).append(u)
    pairs = 0
    for t in sorted(originals[a.uuid], key=lambda t: (t.booking_date, t.id)):
        if t.id in done_ids or not free(t, a):
            continue
        hit = free_b.get((t.booking_date, -cents(t)))
        if hit:
            u = hit.pop(0)
            done_ids.update((t.id, u.id)); pairs += 1
    # ... then, if you moved the mirrored booking, the nearest original of that amount up to MIRROR_MOVED_DAYS away, the
    # closest of all first (a note: the days differ) -- else Kontor would mirror the new one again and the amount would be
    # there twice; further away it is another booking (a weekly payment): mirrored, and the old one has no original
    cand = sorted((abs((o.booking_date - m.booking_date).days), i, o.id) for i, (x, src, m) in enumerate(rest) for o in originals[src.uuid]
                  if o.id not in done_ids and free(o, src) and abs(o.amount + m.amount) < 0.005
                  and abs((o.booking_date - m.booking_date).days) <= MIRROR_MOVED_DAYS)
    got = {}
    for d, i, oid2 in cand:
        if i in got or oid2 in done_ids:
            continue
        got[i] = by_id[oid2]; done_ids.add(oid2); marked += 1
    for i, (x, src, m) in enumerate(rest):
        hit = got.get(i)
        if hit is not None:
            res.warnings.append(tr("s_s_spiegel_geaendert") % (x.name, m.booking_date.strftime("%d.%m.%Y"), fmt_eur(m.amount), src.name,
                                                               hit.booking_date.strftime("%d.%m.%Y"), fmt_eur(hit.amount)))
        else:
            res.warnings.append(tr("s_s_spiegel_original_weg") % (x.name, m.booking_date.strftime("%d.%m.%Y"), fmt_eur(m.amount), src.name, x.name))
    # entered by hand where Kontor had mirrored already (the other end's booking came first): one of the two is too many
    kontor_m = {x.uuid: [m for m in real[x.uuid] if _mirror_of(m) is not None] for x in (a, b)}
    twin: Dict[int, Tx] = {}
    for x in (a, b):
        used: set = set()
        for t in sorted(originals[x.uuid], key=lambda t: (t.booking_date, t.id)):
            if t.id in done_ids:
                continue
            m = min((m for m in kontor_m[x.uuid] if m.id not in used and cents(m) == cents(t) and abs((m.booking_date - t.booking_date).days) <= MIRROR_DAYS),
                    key=lambda m: (abs((m.booking_date - t.booking_date).days), m.id), default=None)
            if m is not None:
                used.add(m.id); twin[t.id] = m
                res.warnings.append(tr("s_s_spiegel_doppelt_hand") % (x.name, t.booking_date.strftime("%d.%m.%Y"), fmt_eur(t.amount), m.booking_date.strftime("%d.%m.%Y")))
    # the possible counterpart of a booking left without a pair: the nearest one of the same amount on the other side, up to
    # NEAR_DAYS apart, itself without a pair and not turned down; the two halves name each other only where each is the
    # other's nearest and the other half is proposed too (its side an offline account, from "Buchen ab")
    left = {x.uuid: [t for t in originals[x.uuid] if t.id not in done_ids and free(t, x)] for x in (a, b)}
    near_of: Dict[int, Tx] = {}
    for x in (a, b):
        for t in left[x.uuid]:
            u = min((u for u in left[other[x.uuid].uuid] if cents(u) == -cents(t) and abs((u.booking_date - t.booking_date).days) <= NEAR_DAYS),
                    key=lambda u: (abs((u.booking_date - t.booking_date).days), u.id), default=None)
            if u is not None:
                near_of[t.id] = u
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
            near = near_of.get(t.id)
            mutual = near is not None and t.id not in twin and near_of.get(near.id) is t and x in sides and counts(near)
            pair = bkey(x.uuid, MIRROR_TAG + str(near.id)) if mutual else ""          # the other half: its own proposal, mirrored here
            note = (tr("s_spiegel_doppelt_note") % (x.name, twin[t.id].booking_date.strftime("%d.%m.%Y")) if t.id in twin
                    else tr("s_spiegel_gegenstueck" if mutual else "s_spiegel_gegenstueck_1") % (target.name, near.booking_date.strftime("%d.%m.%Y")) if near else "")
            p = Proposal(rule, "mirror", target.uuid, target.path, t.booking_date, round(-t.amount, 2), (owner or {}).get(x.uuid) or x.name,
                         _fill(DEFAULT_TEXTS["mirror_text"], source=x.name, text=text, tag=tag), cfg.get("category") or "", tag,
                         group=group, retro=not seen.new_tx(t),
                         note=note, pair=pair)
            _emit(res, ledger, p, edits)
            booked += 1
    pv.update(direction="both" if len(sides) == 2 else ("to_a" if sides[0] is a else "to_b"), mirrored=marked + pairs, open=booked,
              paare=pairs, saldo_a=round(a.balance, 2), saldo_b=round(b.balance, 2),
              begin=start.isoformat() if isinstance(start, date) else start if start == "all" else None)


MIRROR_DAYS = 7     # a mirror: a booking by hand this close to Kontor's own mirrored one of the same amount -- one is too many
MIRROR_MOVED_DAYS = 3   # a mirrored booking you moved this far still counts for its original entered again (a new number)
NEAR_DAYS = 31      # a booking by hand on the other side up to a month apart: the proposal says so and waits for you


def current_day(cfg: dict, today: date) -> date:
    """The day a participation is booked for now: today (daily), the end of last month (monthly)."""
    return date(today.year, today.month, 1) - timedelta(days=1) if cfg.get("cycle") == "monthly" else today


def default_start(ledger: Ledger, cfg: dict, area: dict, today: date, extra: Iterable[str] = ()) -> Optional[date]:
    """For a company without "Buchen ab" (not written by the interface): since Kontor's first booking for its participation
    (its value adjustments; extra: further accounts), at the latest the day booked for now (a booking of Kontor's you moved to
    a later day must not leave that day out) -- None if there is none."""
    accs: List[str] = []
    for ref in [cfg.get("participation")] + list(extra):
        try:
            accs.append(ledger.resolve(str(ref or "")).uuid)
        except KeyError:
            pass
    first = _first_mark(ledger, accs, VALUE_TAGS + (MIRROR_TAG,)) if accs else None
    return min(first, current_day(cfg, today)) if first else None


def company_start(ledger: Ledger, config: Optional[dict], cfg: dict, area: dict, today: date):
    """"Buchen ab" of a company's participation: the day set (or "all"), without one default_start."""
    start = parse_start(cfg.get("retroactive_from"))
    if start is None:
        start = default_start(ledger, cfg, area, today)
    return start


def mirrors(config: dict) -> List[dict]:
    """The account mirrors (config account_mirrors): {"a", "b", "from_date" (Buchen ab: a day, "all"), "category"} between any
    two accounts. The same pair counts once."""
    out: List[dict] = []
    seen_pairs = set()
    for m in config.get("account_mirrors") or []:
        if not isinstance(m, dict):
            continue
        a, b = m.get("a"), m.get("b")
        pair = frozenset((str(a or "").split("|")[0].strip(), str(b or "").split("|")[0].strip()))
        if not a or not b or pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        out.append(dict({"a": str(a), "b": str(b), "from_date": str(m.get("from_date") or ""), "category": str(m.get("category") or "")},
                        **({"review": True} if m.get("review") else {})))
    return out


def plan_account_mirror(ledger: Ledger, m: dict, i: int, today: date, config: Optional[dict] = None, skip: Optional[set] = None,
                        edits: Optional[Dict[str, dict]] = None, owner: Optional[Dict[str, str]] = None, seen: Optional[Seen] = None,
                        auto: bool = False, areas: Optional[Dict[str, dict]] = None) -> RuleResult:
    """One account mirror (plan_mirror) between any two accounts: of your own, of a company, of two companies. Booked from its
    "Buchen ab" on. owner: account -> the name of its area."""
    res = RuleResult()
    pv = {"kind": "mirror", "i": i}
    areas = areas or {}
    try:
        a, b = ledger.resolve(m["a"]), ledger.resolve(m["b"])
    except KeyError as e:
        res.warnings.append("%s: %s" % (tr("s_regel_gegenkonto") % str(i + 1), e))
        return res
    pv.update(a=a.uuid, b=b.uuid)
    rule = tr("s_regel_gegenkonto") % a.name
    if a.group or b.group:
        res.warnings.append(tr("s_s_quelle_ist_eine_gruppe") % rule)
        return res
    if (a.currency or "EUR").upper() != (b.currency or "EUR").upper():      # Kontor does not convert: nothing is mirrored
        res.warnings.append(tr("s_s_spiegel_waehrung") % rule)
        return res
    companies = {str(g.get("area")): g for g in (config or {}).get("companies") or [] if isinstance(g, dict)}
    party = lambda bid, area: (companies.get(bid, {}).get("counterparty") or "").strip() or area["name"]
    who = dict(owner or {})
    start = parse_start(m.get("from_date"))
    if a.uuid == b.uuid:
        res.warnings.append(tr("s_s_spiegel_selbst") % rule)
        return res
    for k, area in areas.items():                      # an account of a company: the counterparty you set for it
        if str(k) in companies:
            who.update({x.uuid: party(str(k), area) for x in (a, b) if x.uuid in {y.uuid for y in area["leaves"]}})
    if start is None:                                  # no day (not written by the interface): Kontor's first booking in the two
        first = _first_mark(ledger, [a.uuid, b.uuid], VALUE_TAGS + (MIRROR_TAG,))
        start = min(first, today) if first else None
    plan_mirror(ledger, res, rule, a, b, {"category": m.get("category") or ""}, config, pv, skip, edits, "", who, seen, start, auto)
    res.preview.append(pv)
    return res


def plan_company(ledger: Ledger, cfg: dict, area: dict, today: date, roles: Optional[Dict[str, str]] = None,
                 config: Optional[dict] = None, skip: Optional[set] = None, edits: Optional[Dict[str, dict]] = None,
                 owner: Optional[Dict[str, str]] = None, seen: Optional[Seen] = None, auto: bool = False) -> RuleResult:
    """One company (an area of the kind "Gesellschaft"): the participation account follows share x value of the company (its
    accounts without the partners' equity), from "Buchen ab" of the company on (rueckwirkend_ab). The account mirrors are
    planned before (plan_account_mirror), so what was mirrored into the company counts in its value."""
    seen = seen or Seen()
    res = RuleResult()
    roles = roles or {}
    name = area["name"]
    inside = {a.uuid for a in area["leaves"]}
    payee = (cfg.get("counterparty") or "").strip() or name
    start = company_start(ledger, config, cfg, area, today)
    if cfg.get("participation"):
        rule = tr("s_regel_beteiligung") % name
        pv = {"kind": "participation", "area": area["id"]}
        try:
            target = ledger.resolve(cfg["participation"])
        except KeyError as e:
            res.warnings.append("%s: %s" % (rule, e))
            target = None
        anteil = area.get("share")
        if target is not None and anteil is None:
            res.warnings.append(tr("s_s_anteil_fehlt") % rule)
        elif target is not None and _target_ok(ledger, config, res, rule, target, inside):
            accs = [a for a in area["leaves"] if roles.get(a.uuid) not in VALUE_OFF]
            share = float(anteil)
            pct = ("%.4f" % (share * 100)).rstrip("0").rstrip(".").replace(".", ",")
            series = ValueSeries(ledger, accs, config, share)
            begin = (series.change_days[0] if series.change_days else None) if start == "all" else start
            # a value that changed through a new transaction of the company (or a new booking planned now) is new on its day
            fresh_from = None if seen.max_id is None else min(
                (t.booking_date for a in accs for t in ledger.transactions(a.uuid) if seen.new_tx(t)), default=None)
            _keep_value(ledger, res, rule, target, series, cfg, today, payee,
                        lambda v, tag, want: _fill(DEFAULT_TEXTS["value_text"], share=pct, source=name, value=fmt_eur(v), target=fmt_eur(want), tag=tag),
                        pv, skip, str(area["id"]), edits, seen, begin, fresh_from, auto)
            res.preview.append(pv)
    return res


# ---------------------------------------------------------------------------
# All rules of a configuration
# ---------------------------------------------------------------------------

def _review(r: RuleResult, cfg: dict) -> RuleResult:
    """A rule the assistant made or changed, not yet confirmed by the user (review): each of its bookings waits for approval."""
    if cfg.get("review"):
        for p in r.proposals:
            p.note = p.note or tr("s_regel_pruefen")
    return r


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
        for pv in r.preview:                          # what the rule would book (shown in the interface on a click), at most 300
            pv.setdefault("items", [{"date": p.booking_date.isoformat(), "account": p.account_path, "amount": round(p.amount, 2),
                                     "purpose": p.purpose, "older": bool(p.retro)} for p in r.proposals[:300]])
        total.proposals += r.proposals; total.info += r.info; total.preview += r.preview; total.waiting += r.waiting
        total.warnings += [w for w in r.warnings if w not in total.warnings]          # a waiting company: named once
    # order: loans first (they change the values of the companies), then mirrors and participations
    for i, cfg in enumerate(config.get("loans", []) or []):
        if cfg.get("active", True):
            r = _review(plan_loan(ledger, cfg, today, config, skip, edits, seen, hold, auto), cfg)
            r.preview.append({"kind": "loans", "i": i, "bookings": len(r.proposals)})
            add(r)
    ms = mirrors(config)
    if config.get("companies") or ms:
        from report import account_roles          # imported late (report/core import rules)
        from core import bereiche_for
        roles = account_roles(ledger, config)
        areas = {b["id"]: b for b in bereiche_for(ledger, config)}
        owner = {a.uuid: b["name"] for b in areas.values() for a in b["leaves"]}          # an account's area: the company or person
        companies = [c for c in config.get("companies") or [] if isinstance(c, dict)]
        for i, m in enumerate(ms):                    # mirrors first: what they bring into a company counts in its value
            add(_review(plan_account_mirror(ledger, m, i, today, config, skip | hold, edits, owner, seen, auto, areas), m))
        for cfg in companies:
            if not cfg.get("participation"):
                continue
            area = areas.get(str(cfg.get("area")))
            if area is None:
                w = tr("s_gesellschaft_s_bereich_fehlt") % cfg.get("area")
                if w not in total.warnings:
                    total.warnings.append(w)
                continue
            add(_review(plan_company(ledger, cfg, area, today, roles, config, skip | hold, edits, owner, seen, auto), cfg))
    return total
