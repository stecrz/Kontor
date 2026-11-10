"""Regeln: Darlehensspiegelung + Zinsen; je Gesellschaft Beteiligungswert und Gegenkonten.

Jede Regel liefert Buchungsvorschlaege (Proposal) und Warnungen. Sie
veraendert MoneyMoney nicht selbst; das macht kern.run_once nach dem Probelauf.

Idempotenz: Jede automatische Buchung traegt im Verwendungszweck eine
Markierung (#mm-tx-<id>, #mm-zins-JJJJ-MM, #mm-wert-..., #mm-spiegel-...). Vor jedem Vorschlag
wird geprueft, ob die Markierung im Zielkonto schon existiert. Die Wahrheit
liegt damit in MoneyMoney selbst, nicht in einer Notizdatei des Skripts.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from model import TAG_RE, Ledger, Tx, fmt_eur, month_end, months_between
from i18n import tr


def bkey(account_uuid: str, tag: str) -> str:
    """A booking of Kontor: account and mark (the same mark, e.g. interest of a month, exists once per account)."""
    return "%s|%s" % (account_uuid, tag)


@dataclass
class Proposal:
    rule: str
    kind: str                 # tilgung | zins | wert | spiegel | quelle
    account_uuid: str
    account_path: str
    booking_date: date
    amount: float
    payee: str
    purpose: str
    category: str = ""
    tag: str = ""
    # Aenderung an einer bestehenden Buchung (setTransaction)
    source_tx_id: Optional[int] = None
    set_comment: Optional[str] = None
    set_category: Optional[str] = None
    group: str = ""           # company (area id) of a participation or counter account
    retro: bool = False       # booking back to a past day (Rückwirkend ab)

    @property
    def key(self) -> str:
        return bkey(self.account_uuid, self.tag)

    def describe(self) -> str:
        if self.kind == "quelle":
            parts = []
            if self.set_category:
                parts.append("Kategorie '%s'" % self.set_category)
            if self.set_comment:
                parts.append("Kommentar")
            return "%s  Quellbuchung %s: %s setzen" % (self.rule, self.source_tx_id, ", ".join(parts))
        return "%s  %s  %s  %s  %s  [%s]" % (
            self.rule, self.booking_date.isoformat(), self.account_path,
            fmt_eur(self.amount).rjust(16), self.purpose, self.category or "-")


@dataclass
class RuleResult:
    proposals: List[Proposal] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)
    missing: List[dict] = field(default_factory=list)     # created by Kontor before, no longer found in MoneyMoney
    preview: List[dict] = field(default_factory=list)     # per rule: target, actual, difference, months booked back (interface)


VALUE_TAGS = ("#mm-wert-", "#mm-spiegel-")


def is_value_tag(tag) -> bool:
    """A value adjustment (participation, counter account): always the difference to the balance, never a fixed amount."""
    return str(tag or "").startswith(VALUE_TAGS)


def present_mark_txs(ledger: Ledger) -> Dict[Tuple[str, str], Tx]:
    """(account, mark) -> booking, of Kontor's bookings that are in MoneyMoney (not the ones planned in this run)."""
    return {(t.account_uuid, m): t for t in ledger.txs if not getattr(t, "planned", False) and "#mm-" in (t.purpose or "")
            for m in TAG_RE.findall(t.purpose)}


def present_marks(ledger: Ledger) -> set:
    """(account, mark) of Kontor's bookings that are in MoneyMoney (not the ones planned in this run)."""
    return set(present_mark_txs(ledger))


def deleted_values(ledger: Ledger, records: List[dict], marks=None) -> List[dict]:
    """Value adjustments (participation, counter account) Kontor made that are gone from MoneyMoney: their day is checked
    again (see _keep_value, recheck)."""
    marks = present_marks(ledger) if marks is None else marks
    claimed: set = set()
    return [r for r in records or [] if isinstance(r, dict) and is_value_tag(r.get("tag"))
            and (r.get("konto"), r.get("tag")) not in marks and find_unmarked(ledger, r, claimed) is None]


def changed_values(ledger: Ledger, records: List[dict], mark_txs: Optional[Dict[Tuple[str, str], Tx]] = None) -> List[Tuple[dict, Tx]]:
    """Value adjustments Kontor made whose amount or day you changed in MoneyMoney: (its record, the booking now)."""
    mark_txs = present_mark_txs(ledger) if mark_txs is None else mark_txs
    out = []
    for r in records or []:
        if not isinstance(r, dict) or not is_value_tag(r.get("tag")):
            continue
        t = mark_txs.get((r.get("konto"), r.get("tag")))
        if t is not None and (abs(t.amount - float(r.get("betrag") or 0)) >= 0.005 or t.booking_date.isoformat() != r.get("datum")):
            out.append((r, t))
    return out


def apply_edit(p: "Proposal", ch: Optional[dict]) -> None:
    """Your changes to a booking before approving it: amount, date, purpose (its mark stays, so it is never made twice)."""
    if not ch:
        return
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
    return ledger.post(p.account_uuid, p.booking_date, p.amount, p.payee, p.purpose, p.category)


def find_unmarked(ledger: Ledger, rec: dict, claimed: set) -> Optional[Tx]:
    """A booking of Kontor's own list whose mark is gone: the same account, date and amount, without another booking's mark,
    and each booking in MoneyMoney for one entry only (two equal ones are two, not one twice)."""
    for t in ledger.transactions(rec.get("konto") or ""):
        if t.id in claimed or t.booking_date.isoformat() != rec.get("datum") or abs(t.amount - float(rec.get("betrag") or 0)) >= 0.005:
            continue
        if TAG_RE.search(t.purpose or ""):          # carries a mark: belongs to that booking
            continue
        claimed.add(t.id)
        return t
    return None


def _created_check(ledger: Ledger, created: Dict[str, dict], key: str, res: RuleResult, claimed: Optional[set] = None) -> bool:
    """Kontor's own list of the bookings it made (key: account|mark): never proposed again, even if its mark is gone from
    MoneyMoney (changed or deleted there) -- the matching below only decides whether it is shown as missing."""
    rec = created.get(key)
    if not rec:
        return False
    if find_unmarked(ledger, rec, claimed if claimed is not None else set()) is None:
        res.missing.append({k: rec.get(k) for k in ("tag", "konto", "konto_name", "datum", "betrag", "art", "regel", "zweck", "gegenpartei", "kategorie")})
    return True


def _skipped(skip: Optional[set], account_uuid: str, tag: str) -> bool:
    """Rejected by you (account|mark; older entries only by mark)."""
    return bool(skip) and (bkey(account_uuid, tag) in skip or tag in skip)


def tags_in(txs: List[Tx]) -> Dict[str, Tx]:
    out: Dict[str, Tx] = {}
    for t in txs:
        for tag in TAG_RE.findall(t.purpose + " " + t.comment):
            out[tag] = t
    return out


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


# ---------------------------------------------------------------------------
# Darlehen
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
    "wert_text": "Wertanpassung {anteil} % · Wert {quelle} {wert} · {tag}",
    "spiegel_text": "Abgleich mit {quelle} · Stand {wert} · {tag}",
}


def plan_loan(ledger: Ledger, cfg: dict, today: date, created: Optional[Dict[str, dict]] = None, claimed: Optional[set] = None,
              config: Optional[dict] = None, skip: Optional[set] = None, edits: Optional[Dict[str, dict]] = None) -> RuleResult:
    """skip: marks of bookings you rejected under Auto bookings -- never proposed again (or left out of this approval).
    edits: your changes from the approval (account|mark -> amount, date, purpose)."""
    skip = skip or set()
    res = RuleResult()
    claimed = claimed if claimed is not None else set()
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

    existing = tags_in(ledger.transactions(loan.uuid))

    # 1. Spiegelung der Zahlungen ------------------------------------------
    erk = cfg.get("erkennung") or {}
    matched: List[Tx] = []
    for src in sources:
        for t in ledger.transactions(src.uuid):
            if t.booking_date < ab or not _matches(t, erk):
                continue
            matched.append(t)
            tag = "#mm-tx-%d" % t.id
            if tag in existing or _skipped(skip, loan.uuid, tag) or _created_check(ledger, created or {}, bkey(loan.uuid, tag), res, claimed):
                continue
            amount = round(-t.amount, 2)
            purpose = _fill(texts["tilgung_text"], art=payment_kind(t), datum=t.booking_date.strftime("%d.%m.%Y"),
                            quelle=src.name, betrag=fmt_eur(abs(t.amount)), tag=tag)
            p = Proposal(rule, "tilgung", loan.uuid, loan.path, t.booking_date, amount, payee,
                         purpose, cat_tilgung, tag)
            existing[tag] = _emit(res, ledger, p, edits)
            # Quellbuchung kennzeichnen
            want_cat = cfg.get("quelle_kategorie")
            want_comment = None
            if cfg.get("quelle_kommentar", False) and "#mm" not in t.comment:
                want_comment = ((t.comment + " ") if t.comment else "") + "→ %s gespiegelt (#mm-tx-%d)" % (loan.name, t.id)
            if want_cat and t.category_path.split("\\")[-1] == want_cat:
                want_cat = None
            if want_cat or want_comment:
                res.proposals.append(Proposal(rule, "quelle", src.uuid, src.path, t.booking_date, 0.0, "",
                                              "", "", tag, source_tx_id=t.id, set_comment=want_comment,
                                              set_category=want_cat))

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

    # 2. Zinsen ------------------------------------------------------------
    zins = cfg.get("zins") or {}
    rates = zins.get("satz") or []
    if not rates:
        res.info.append(tr("s_s_kein_zinssatz_hinterlegt_keine") % rule)
        return res
    modell = zins.get("modell", "jahresbasis")
    buchungstag = zins.get("buchungstag", "ultimo")
    overrides = {str(k): float(v) for k, v in (zins.get("basis_override") or {}).items()}
    year_cache: Dict[int, Tuple[float, float, float]] = {}   # Jahr -> (Basis, Satz, Jahreszins)
    loan_txs = ledger.transactions(loan.uuid)

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

    for (y, m) in months_between(ab, today):
        if modell == "jahresbasis":
            year_basis(y)
        # Buchungstag
        if buchungstag == "mit_rate":
            in_month = [t for t in matched if (t.booking_date.year, t.booking_date.month) == (y, m)]
            bday = min(t.booking_date for t in in_month) if in_month else month_end(y, m)
        else:
            bday = month_end(y, m)
        if bday > today or bday < ab:
            continue
        tag = "#mm-zins-%04d-%02d" % (y, m)
        if tag in existing or _skipped(skip, loan.uuid, tag) or _created_check(ledger, created or {}, bkey(loan.uuid, tag), res, claimed):
            continue
        # Schutz: manuell gebuchte Zinsen im selben Monat
        manual = [t for t in loan_txs if (t.booking_date.year, t.booking_date.month) == (y, m)
                  and "zins" in t.text.lower() and not TAG_RE.search(t.purpose + t.comment)]
        if manual:
            res.warnings.append(tr("s_s_04d_02d_enthaelt_bereits") % (rule, y, m, fmt_eur(manual[0].amount)))
            continue

        if modell == "jahresbasis":
            base, rate, yearly = year_basis(y)
            if yearly <= 0:
                continue
            per = round(yearly / 12.0, 2)
            interest = round(yearly - 11 * per, 2) if m == 12 else per
        elif modell == "restschuld_monatlich":
            rate = _rate_at(rates, date(y, m, 1))
            prev_end = date(y, m, 1) - timedelta(days=1)
            base = abs(ledger.balance_at(loan.uuid, prev_end))
            if rate is None or base <= 0:
                continue
            interest = round(base * rate / 1200.0, 2)
        else:
            res.warnings.append("%s: unbekanntes Zinsmodell '%s'." % (rule, modell))
            return res

        if interest <= 0:
            continue
        amount = round(sign * interest, 2)
        purpose = _fill(texts["zins_text"], monat="%02d/%04d" % (m, y),
                        prozent=("%.3f" % rate).rstrip("0").rstrip(".").replace(".", ","), basis=fmt_eur(base), tag=tag)
        p = Proposal(rule, "zins", loan.uuid, loan.path, bday, amount, payee, purpose, cat_zins, tag)
        existing[tag] = _emit(res, ledger, p, edits)

    return res


# ---------------------------------------------------------------------------
# Gesellschaften: Beteiligung (Anteil x Wert der Gesellschaft) und Gegenkonten (Faktor x Konto der Gesellschaft)
# ---------------------------------------------------------------------------

VALUE_OFF = {"eigenkapital", "eventual", "ignorieren"}      # not part of a company's value: partners' equity, contingent, ignored


def parse_start(s):
    """"Rückwirkend ab": a day ('2025-03-14'), "alles" (since the company exists), older '2025-03' (first of the month);
    anything else (empty: from now on only) -> None."""
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


def _keep_value(ledger: Ledger, res: RuleResult, rule: str, kind: str, target, series: ValueSeries, cfg: dict, today: date,
                payee: str, purpose, preview: dict, skip: Optional[set] = None, retro_done: bool = False, group: str = "",
                edits: Optional[Dict[str, dict]] = None, recheck=None) -> None:
    """Keep the manual account `target` at the value of `series`, always booking only the difference to its balance in
    MoneyMoney (so a booking that is there is never made twice). A balance is the sum of all bookings up to that day, so one
    booking on a day moves every later balance by the same amount: a missing or changed booking is corrected by one booking
    on its own day, never by changing the ones after it.
    - daily (default): today; monthly ("takt"): at the end of last month,
    - "Rückwirkend ab" (a day, or "alles": since the company's first transaction) once, until it is marked as done: every past
      day on which the value changed (daily) or every month end (monthly) from then on -- this also checks and corrects what
      is there,
    - recheck: past days to check again, once (a booking of Kontor's deleted or changed in MoneyMoney, "Book again").
    Unknown days are skipped. edits: your changes from the approval, posted as changed so what follows builds on them."""
    schwelle = max(float(cfg.get("schwelle") or 0.01), 0.01)
    monthly = cfg.get("takt") == "monatlich"
    first = date(today.year, today.month, 1)
    last_end = first - timedelta(days=1)
    days: List[Tuple[Optional[date], bool]] = []
    start = parse_start(cfg.get("rueckwirkend_ab"))
    if start == "alles":                       # since the company exists: from its first transaction
        start = series.change_days[0] if series.change_days else None
    if start and not retro_done:
        if monthly:
            days = [(e, True) for e in (month_end(y, m) for (y, m) in months_between(start, last_end)) if e >= start]
        else:
            days = [(d, True) for d in sorted({start} | {d for d in series.change_days if start <= d < today}) if d < today]
    elif monthly and (not start or last_end >= start):
        days = [(last_end, False)]
    again = {d for d in (recheck or ()) if d < today} - {d for d, _ in days}
    if again:
        days = sorted(days + [(d, True) for d in again], key=lambda x: x[0])
    if not monthly:
        days.append((None, False))
    preview.update(ziel=target.uuid, ist=round(target.balance, 2), rueck=0, rueck_summe=0.0, unbekannt=[], takt="monatlich" if monthly else "taeglich")
    want_now, src_now, _ = series.at(None)
    preview.update(soll=want_now, quelle=src_now, diff=round(want_now - preview["ist"], 2))
    unknown_months: List[str] = []
    for d, retro in days:
        day = d or today
        want, src_value, unknown = series.at(d)
        if unknown:
            m = day.strftime("%m/%Y")
            if m not in unknown_months:
                unknown_months.append(m)
            continue
        have = target.balance if d is None else ledger.balance_at(target.uuid, d)
        diff = round(want - have, 2)
        if abs(diff) < schwelle:
            continue
        prefix = "#mm-%s-%s-" % (kind, day.strftime("%Y%m%d"))
        used = {m for t in ledger.transactions(target.uuid) if prefix in (t.purpose or "") for m in TAG_RE.findall(t.purpose)}
        n = 1
        while prefix + str(n) in used:       # the first free number (one deleted in MoneyMoney is free again)
            n += 1
        tag = prefix + str(n)
        if _skipped(skip, target.uuid, tag):          # rejected by you under Auto bookings
            continue
        p = Proposal(rule, kind, target.uuid, target.path, day, diff, payee, purpose(src_value, tag), cfg.get("kategorie") or "", tag,
                     group=group, retro=retro)
        _emit(res, ledger, p, edits)
        if retro:
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


def plan_company(ledger: Ledger, cfg: dict, area: dict, today: date, roles: Optional[Dict[str, str]] = None,
                 config: Optional[dict] = None, skip: Optional[set] = None, done: Optional[Dict[str, str]] = None,
                 edits: Optional[Dict[str, dict]] = None, recheck: Optional[Dict[str, set]] = None) -> RuleResult:
    """One company (an area of the kind "Gesellschaft"): the participation account follows share x value of the company
    (its accounts without the partners' equity), each counter account follows factor x one account of the company.
    recheck: account -> past days to check again (see _keep_value)."""
    recheck = recheck or {}
    res = RuleResult()
    roles = roles or {}
    name = area["name"]
    inside = {a.uuid for a in area["leaves"]}
    payee = (cfg.get("gegenpartei") or "").strip() or name
    retro_done = bool(cfg.get("rueckwirkend_ab")) and (done or {}).get(str(area["id"])) == cfg.get("rueckwirkend_ab")
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
            _keep_value(ledger, res, rule, "wert", target, ValueSeries(ledger, accs, config, share), cfg, today, payee,
                        lambda v, tag: _fill(DEFAULT_TEXTS["wert_text"], anteil=pct, quelle=name, wert=fmt_eur(v), tag=tag), pv, skip,
                        retro_done, str(area["id"]), edits, recheck.get(target.uuid))
            res.preview.append(pv)
    for i, g in enumerate(cfg.get("gegenkonten") or []):
        if not isinstance(g, dict) or not g.get("konto") or not g.get("quelle"):
            continue
        pv = {"art": "gegenkonto", "bereich": area["id"], "i": i}
        try:
            target, src = ledger.resolve(g["konto"]), ledger.resolve(g["quelle"])
        except KeyError as e:
            res.warnings.append("%s: %s" % (tr("s_regel_gegenkonto") % name, e))
            continue
        rule = tr("s_regel_gegenkonto") % target.name
        if src.group:
            res.warnings.append(tr("s_s_quelle_ist_eine_gruppe") % rule)
            continue
        if not _target_ok(ledger, config, res, rule, target, inside | {src.uuid}):
            continue
        f = float(g.get("faktor", -1) if g.get("faktor") not in (None, "") else -1)
        _keep_value(ledger, res, rule, "spiegel", target, ValueSeries(ledger, [src], config, f), cfg, today, payee,
                    lambda v, tag, src=src: _fill(DEFAULT_TEXTS["spiegel_text"], quelle=src.name, wert=fmt_eur(v), tag=tag), pv, skip,
                    retro_done, str(area["id"]), edits, recheck.get(target.uuid))
        res.preview.append(pv)
    return res


# ---------------------------------------------------------------------------
# Alle Regeln eines Konfigurationsstands
# ---------------------------------------------------------------------------

def plan_all(ledger: Ledger, config: dict, today: date, created: Optional[Dict[str, dict]] = None,
             skip: Optional[set] = None, done: Optional[Dict[str, str]] = None, edits: Optional[Dict[str, dict]] = None,
             recheck: Optional[Dict[str, set]] = None) -> RuleResult:
    """created: Kontor's own list of the bookings it made (tag -> record), see _created_check. Values (participations, counter
    accounts) need none: they always book the difference to the balance in MoneyMoney. skip: marks you rejected (or left out
    of an approval). edits: your changes from the approval. recheck: account -> past days to check again."""
    total = RuleResult()
    claimed: set = set()

    def add(r: RuleResult) -> None:
        total.proposals += r.proposals; total.warnings += r.warnings; total.info += r.info
        total.missing += r.missing; total.preview += r.preview
    # Reihenfolge: erst Darlehen (veraendern die Werte der Gesellschaften), dann Beteiligungen und Gegenkonten
    for i, cfg in enumerate(config.get("darlehen", []) or []):
        if cfg.get("aktiv", True):
            r = plan_loan(ledger, cfg, today, created, claimed, config, skip, edits)
            r.preview.append({"art": "darlehen", "i": i, "buchungen": len(r.proposals), "fehlend": len(r.missing)})
            add(r)
    if config.get("gesellschaften"):
        from report import account_roles          # spaet importiert (report/core importieren rules)
        from core import bereiche_for
        roles = account_roles(ledger, config)
        areas = {b["id"]: b for b in bereiche_for(ledger, config)}
        for cfg in config.get("gesellschaften") or []:
            if not isinstance(cfg, dict) or not (cfg.get("beteiligung") or cfg.get("gegenkonten")):
                continue
            area = areas.get(str(cfg.get("bereich")))
            if area is None:
                total.warnings.append(tr("s_gesellschaft_s_bereich_fehlt") % cfg.get("bereich"))
                continue
            add(plan_company(ledger, cfg, area, today, roles, config, skip, done, edits, recheck))
    return total
