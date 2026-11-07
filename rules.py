"""Regeln: Darlehensspiegelung + Zinsen, Beteiligungswert, Saldo-Spiegel.

Jede Regel liefert Buchungsvorschlaege (Proposal) und Warnungen. Sie
veraendert MoneyMoney nicht selbst; das macht kern.run_once nach dem Probelauf.

Idempotenz: Jede automatische Buchung traegt im Verwendungszweck eine
Markierung (#mm-tx-<id>, #mm-zins-JJJJ-MM, #mm-wert-...). Vor jedem Vorschlag
wird geprueft, ob die Markierung im Zielkonto schon existiert. Die Wahrheit
liegt damit in MoneyMoney selbst, nicht in einer Notizdatei des Skripts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from model import Ledger, Tx, fmt_eur, month_end, months_between
from i18n import tr

TAG_RE = re.compile(r"#mm-[a-z]+-[A-Za-z0-9\-]+")


@dataclass
class Proposal:
    rule: str
    kind: str                 # tilgung | zins | wert | quelle
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
}


def plan_loan(ledger: Ledger, cfg: dict, today: date) -> RuleResult:
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
    if not loan.offline:
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
            if tag in existing:
                continue
            amount = round(-t.amount, 2)
            purpose = _fill(texts["tilgung_text"], art=payment_kind(t), datum=t.booking_date.strftime("%d.%m.%Y"),
                            quelle=src.name, betrag=fmt_eur(abs(t.amount)), tag=tag)
            p = Proposal(rule, "tilgung", loan.uuid, loan.path, t.booking_date, amount, payee,
                         purpose, cat_tilgung, tag)
            res.proposals.append(p)
            existing[tag] = ledger.post(loan.uuid, t.booking_date, amount, payee, purpose, cat_tilgung)
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
                res.info.append("%s: Zinsbasis %d = %s, %s %% p.a. = %s/Jahr" %
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
        if tag in existing:
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
        res.proposals.append(p)
        existing[tag] = ledger.post(loan.uuid, bday, amount, payee, purpose, cat_zins)

    return res


# ---------------------------------------------------------------------------
# Wert-Spiegel (Beteiligung = Anteil x Gruppenwert; Saldo-Spiegel = Faktor x Konto)
# ---------------------------------------------------------------------------

def plan_mirror(ledger: Ledger, cfg: dict, today: date, roles: Optional[Dict[str, str]] = None) -> RuleResult:
    res = RuleResult()
    name = cfg.get("name") or cfg.get("zielkonto") or cfg.get("beteiligungskonto")
    rule = "Wert %s" % name
    try:
        target = ledger.resolve(cfg.get("zielkonto") or cfg["beteiligungskonto"])
        if cfg.get("gruppe"):
            source = ledger.resolve(cfg["gruppe"])
        else:
            source = ledger.resolve(cfg["quellkonto"])
    except KeyError as e:
        res.warnings.append("%s: %s" % (rule, e))
        return res
    if target.group:
        res.warnings.append(tr("s_s_zielkonto_ist_eine_gruppe") % rule)
        return res
    if not target.offline:
        res.warnings.append(tr("s_s_zielkonto_hat_eine_bankanbindung") % rule)
        return res
    if source.group and any(a.uuid == target.uuid for a in ledger.descendants(source.uuid)):
        res.warnings.append(tr("s_s_zielkonto_liegt_innerhalb_der") % rule)
        return res

    anteil = float(cfg.get("anteil", cfg.get("faktor", 1.0)))
    schwelle = float(cfg.get("schwelle", 0.01))
    if source.group:
        # Wert der Gesellschaft = Konten der Gruppe ohne Kapitalkonten (Eigenkapital), Avale und nicht bilanzierte Konten
        aus = {"eigenkapital", "eventual", "ignorieren"}
        source_value = round(sum(a.balance for a in ledger.descendants(source.uuid) if (roles or {}).get(a.uuid) not in aus), 2)
    else:
        source_value = source.balance
    want = round(anteil * source_value, 2)
    have = target.balance
    diff = round(want - have, 2)
    res.info.append("%s: Quelle %s = %s, Anteil %s %% -> Soll %s, Ist %s, Differenz %s" %
                    (rule, source.name, fmt_eur(source_value), ("%.4f" % (anteil * 100)).rstrip("0").rstrip(".").replace(".", ","),
                     fmt_eur(want), fmt_eur(have), fmt_eur(diff)))
    if abs(diff) < schwelle:
        return res
    texts = dict(DEFAULT_TEXTS)
    texts.update(cfg.get("buchung", {}) or {})
    seq = 1 + sum(1 for t in ledger.transactions(target.uuid)
                  if t.booking_date == today and "#mm-wert-" in t.purpose)
    tag = "#mm-wert-%s-%d" % (today.strftime("%Y%m%d"), seq)
    purpose = _fill(texts["wert_text"], anteil=("%.4f" % (anteil * 100)).rstrip("0").rstrip(".").replace(".", ","),
                    quelle=source.name, wert=fmt_eur(source_value), tag=tag)
    p = Proposal(rule, "wert", target.uuid, target.path, today, diff,
                 texts.get("gegenpartei", "Wertanpassung"), purpose, texts.get("kategorie_wert", ""), tag)
    res.proposals.append(p)
    ledger.post(target.uuid, today, diff, p.payee, purpose, p.category)
    return res


# ---------------------------------------------------------------------------
# Alle Regeln eines Konfigurationsstands
# ---------------------------------------------------------------------------

def plan_all(ledger: Ledger, config: dict, today: date) -> RuleResult:
    total = RuleResult()
    # Reihenfolge: erst Darlehen (veraendern GbR-Werte), dann Wert-Spiegel
    for cfg in config.get("darlehen", []) or []:
        if cfg.get("aktiv", True):
            r = plan_loan(ledger, cfg, today)
            total.proposals += r.proposals; total.warnings += r.warnings; total.info += r.info
    from report import account_roles          # spaet importiert (auswertung importiert rules)
    roles = account_roles(ledger, config)
    for cfg in (config.get("beteiligungen", []) or []) + (config.get("saldo_spiegel", []) or []):
        if cfg.get("aktiv", True):
            r = plan_mirror(ledger, cfg, today, roles)
            total.proposals += r.proposals; total.warnings += r.warnings; total.info += r.info
    return total
