"""Immobilienkalkulation: Objekt, Finanzierung, Indexmiete, Kosten, AfA, Steuer, Cashflow, Kennzahlen.

Rechnet auf Monatsbasis (Zeitachse ab Uebergangsstichtag, Horizont in Jahren) und verdichtet
auf Jahre. Je Darlehen waehlbar: Abrechnung monatlich (Bank: Zins auf den laufenden Saldo,
monatliche Verrechnung) oder jaehrlich (z. B. Verkaeuferdarlehen: Zins auf den Stand zum
1. Januar, nachschuessig; Tilgung = Jahreszahlung - Jahreszins).

Alle Eingaben sind reine Daten (dict), damit Kalkulationen gespeichert, kopiert (Szenarien)
und als Paket weitergegeben werden koennen. Betraege in Euro, Saetze in Prozent.

Input (every field optional, sensible defaults):
{
  "name": "Objekt", "kind": "commercial|housing", "area_sqm": 0, "units": 1,
  "purchase_price": 0, "transfer_date": "2026-05-01",          # erster Monat mit Nutzen und Lasten (Miete)
  "closing_costs": {"transfer_tax_percent": 3.5, "notary": 0, "land_register": 0, "broker_fee": 0, "other_depreciation": 0,
                  "immediately_deductible": 0},                # Posten, die zur AfA-Basis zaehlen bzw. sofort abziehbar sind
  "building_share_percent": 70, "depreciation_percent": 2.0, "remaining_life_years": null,   # remaining life overrides depreciation_percent
  "rent": {"net_rent_month": 0, "utilities_month": 0, "vacancy_percent": 0,
            "index": {"kind": "cpi|percent|none", "cpi_base": 122.7, "cpi_current": 122.7, "cpi_increase_percent": 1.9,
                      "factor": 1.0, "threshold_percent": 0, "increase_percent": 0}},
  "costs": {"non_recoverable_pa": 0, "reserve_pa": 0, "increase": "cpi|none|percent", "increase_percent": 0},
  "loans": [{"name": "Darlehen 1", "amount": 0, "interest_percent": 0, "kind": "annuity|repayment|bullet",
                "annuity_month": null, "initial_repayment_percent": null, "repayment_month": null,
                "special_repayment_month": 0, "special_repayment_from": null, "special_repayments": [{"date": "2027-06-01", "amount": 0}],
                "fixed_rate_until": null, "followup_rate_percent": null, "maturity": null, "maturity_kind": "payback|open",
                "deductible": true, "settlement": "monthly|yearly", "begin": null, "account": "UUID | Name"}],
  "partners": [{"name": "A", "share_percent": 50, "tax_rate_percent": 42}],
  "distribution_percent": 48, "tax_refund_in_cashflow": true,
  "appreciation_percent": 2.0, "sale": {"year": null, "costs_percent": 0},
  "horizon_years": 25
}
"""
from __future__ import annotations

import copy
import math
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from i18n import tr



def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, ""):
            return default
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _d(v: Any) -> Optional[date]:
    if not v:
        return None
    try:
        s = str(v)[:10]
        if len(s) == 7:
            s += "-01"
        return date.fromisoformat(s)
    except ValueError:
        return None


def _mk(y: int, m: int) -> str:
    return "%04d-%02d" % (y, m)


def _add(y: int, m: int, n: int) -> Tuple[int, int]:
    m += n
    while m > 12:
        y, m = y + 1, m - 12
    while m < 1:
        y, m = y - 1, m + 12
    return y, m


def normalize(obj: dict) -> dict:
    """Eingaben mit Standardwerten auffuellen (veraendert das Original nicht)."""
    o = copy.deepcopy(obj or {})
    o.setdefault("name", "Objekt")
    o.setdefault("kind", "commercial")
    nk = o.setdefault("closing_costs", {})
    for k, v in (("transfer_tax_percent", 3.5), ("notary", 0), ("land_register", 0), ("broker_fee", 0), ("other_depreciation", 0), ("immediately_deductible", 0)):
        nk.setdefault(k, v)
    o.setdefault("building_share_percent", 70.0)
    o.setdefault("depreciation_percent", 2.0)
    mi = o.setdefault("rent", {})
    for k, v in (("net_rent_month", 0), ("utilities_month", 0), ("vacancy_percent", 0)):
        mi.setdefault(k, v)
    ix = mi.setdefault("index", {})
    for k, v in (("kind", "cpi"), ("cpi_base", 100.0), ("cpi_current", 100.0), ("cpi_increase_percent", 2.0), ("factor", 1.0), ("threshold_percent", 0), ("increase_percent", 0)):
        ix.setdefault(k, v)
    ko = o.setdefault("costs", {})
    for k, v in (("non_recoverable_pa", 0), ("reserve_pa", 0), ("increase", "cpi"), ("increase_percent", 0)):
        ko.setdefault(k, v)
    o.setdefault("loans", [])
    for i, l in enumerate(o["loans"]):
        l.setdefault("name", "Darlehen %d" % (i + 1))
        l.setdefault("kind", "annuity")
        l.setdefault("deductible", True)
        l.setdefault("settlement", "monthly")
        l.setdefault("special_repayments", [])
        l.setdefault("maturity_kind", "open")
    o.setdefault("partners", [{"name": tr("s_eigentuemer"), "share_percent": 100, "tax_rate_percent": 42}])
    o.setdefault("distribution_percent", 48)
    o.setdefault("tax_refund_in_cashflow", True)
    o.setdefault("appreciation_percent", 2.0)
    o.setdefault("sale", {"year": None, "costs_percent": 0})
    o.setdefault("horizon_years", 25)
    o.setdefault("transfer_date", date.today().isoformat())
    return o


def nebenkosten_summe(o: dict) -> Tuple[float, float]:
    """(NK fuer AfA-Basis, sofort abziehbare NK)."""
    nk = o["closing_costs"]
    kp = _f(o.get("purchase_price"))
    afa_nk = kp * _f(nk.get("transfer_tax_percent")) / 100.0 + _f(nk.get("notary")) + _f(nk.get("land_register")) + _f(nk.get("broker_fee")) + _f(nk.get("other_depreciation"))
    return round(afa_nk, 2), round(_f(nk.get("immediately_deductible")), 2)


def _is_num(v: Any) -> bool:
    if v in (None, ""):
        return True
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return math.isfinite(v)
    try:
        float(str(v).replace(",", "."))
        return True
    except ValueError:
        return False


def pruefe(o: dict) -> None:
    """Eingaben pruefen; wirft ValueError mit verstaendlicher Meldung (Feldname) statt still zu rechnen."""
    def num(v, label, lo=None, hi=None):
        if not _is_num(v):
            raise ValueError(tr("s_s_keine_zahl_r") % (label, v))
        if v in (None, ""):
            return 0.0
        x = _f(v)
        if lo is not None and x < lo:
            raise ValueError(tr("s_s_darf_nicht_kleiner_als") % (label, lo))
        if hi is not None and x > hi:
            raise ValueError(tr("s_s_darf_nicht_groesser_als") % (label, hi))
        return x

    def dat(v, label, required=False):
        if v in (None, ""):
            if required:
                raise ValueError(tr("re_fehlt") % label)
            return
        if _d(v) is None:
            raise ValueError(tr("s_s_kein_datum_jjjj_mm") % label)

    num(o.get("purchase_price"), tr("re_kaufpreis"), 0)
    dat(o.get("transfer_date"), tr("s_uebergang"), required=True)
    num(o.get("horizon_years"), tr("re_horizont"), 1, 60)
    num(o.get("area_sqm"), tr("s_flaeche"), 0)
    num(o.get("units"), tr("re_einheiten"), 0)
    nk = o.get("closing_costs") or {}
    num(nk.get("transfer_tax_percent"), tr("re_grunderwerbsteuer_pct"), 0, 100)
    for k, label in (("notary", tr("re_notar")), ("land_register", tr("re_grundbuch")), ("broker_fee", tr("re_makler")), ("other_depreciation", tr("re_sonstige_nebenkosten")), ("immediately_deductible", tr("re_sofort_abziehbare_nebenkosten"))):
        num(nk.get(k), label, 0)
    num(o.get("building_share_percent"), tr("s_gebaeudeanteil"), 0, 100)
    num(o.get("depreciation_percent"), tr("re_afa_pct"), 0, 100)
    num(o.get("remaining_life_years"), tr("re_restnutzungsdauer"), 0, 200)
    mi = o.get("rent") or {}
    num(mi.get("net_rent_month"), tr("re_nettokaltmiete"), 0)
    num(mi.get("utilities_month"), tr("re_umlage"), 0)
    num(mi.get("vacancy_percent"), tr("re_leerstand_pct"), 0, 100)
    ix = mi.get("index") or {}
    if ix.get("kind") not in (None, "", "cpi", "percent", "none"):
        raise ValueError(tr("re_mietanpassung_art") % ix.get("kind"))
    num(ix.get("cpi_base"), tr("re_vpi_basis"), 0.01)
    num(ix.get("cpi_current"), tr("re_vpi_aktuell"), 0.01)
    num(ix.get("cpi_increase_percent"), tr("re_vpi_annahme_pct"), -50, 100)
    num(ix.get("factor"), tr("re_weitergabe_faktor"), 0, 1)
    num(ix.get("threshold_percent"), tr("re_schwelle_pct"), 0, 100)
    num(ix.get("increase_percent"), tr("re_mietsteigerung_pct"), -50, 100)
    ko = o.get("costs") or {}
    num(ko.get("non_recoverable_pa"), tr("s_kosten_nicht_umlagefaehig"), 0)
    num(ko.get("reserve_pa"), tr("s_ruecklage"), 0)
    if ko.get("increase") not in (None, "", "cpi", "percent", "none"):
        raise ValueError(tr("re_kostensteigerung_art") % ko.get("increase"))
    num(ko.get("increase_percent"), tr("re_kostensteigerung_pct"), -50, 100)
    names = set()
    for i, l in enumerate(o.get("loans") or []):
        if not isinstance(l, dict):
            raise ValueError(tr("s_darlehen_d_ungueltig") % (i + 1))
        label = tr("re_darlehen_n") % (l.get("name") or i + 1)
        if l.get("name") in names:
            raise ValueError(tr("re_name_doppelt") % label)
        names.add(l.get("name"))
        num(l.get("amount"), label + " " + tr("x_betrag"), 0)
        num(l.get("interest_percent"), label + " " + tr("re_zins_pct"), 0, 100)
        if l.get("kind") not in (None, "", "annuity", "repayment", "bullet"):
            raise ValueError(tr("re_unbekannte_art") % (label, l.get("kind")))
        num(l.get("annuity_month"), label + " " + tr("re_annuitaet"), 0)
        num(l.get("initial_repayment_percent"), label + " " + tr("re_anfangstilgung_pct"), 0, 100)
        num(l.get("repayment_month"), label + " " + tr("re_tilgung_monat"), 0)
        num(l.get("special_repayment_month"), label + " " + tr("re_sondertilgung_monat"), 0)
        num(l.get("followup_rate_percent"), label + " " + tr("re_anschlusszins_pct"), 0, 100)
        for k, lab in (("special_repayment_from", tr("re_sondertilgung_ab")), ("fixed_rate_until", tr("s_zinsbindung_bis")), ("maturity", tr("s_faelligkeit")), ("begin", tr("re_beginn"))):
            dat(l.get(k), "%s %s" % (label, lab))
        for st in l.get("special_repayments") or []:
            if not isinstance(st, dict):
                raise ValueError(tr("s_s_sondertilgung_ungueltig") % label)
            dat(st.get("date"), label + " " + tr("re_sondertilgung_datum"), required=True)
            num(st.get("amount"), label + " " + tr("re_sondertilgung_betrag"), 0)
        if (l.get("kind") or "annuity") == "annuity" and _f(l.get("amount")) > 0 and not _f(l.get("annuity_month")) and l.get("initial_repayment_percent") in (None, ""):
            raise ValueError(tr("s_s_annuitaet_je_monat_oder") % label)
        if (l.get("settlement") or "monthly") not in ("monthly", "yearly"):
            raise ValueError(tr("s_s_abrechnung_muss_monatlich_oder") % label)
    ges = o.get("partners") or []
    total = 0.0
    for g in ges:
        if not isinstance(g, dict):
            raise ValueError(tr("s_gesellschafter_ungueltig"))
        total += num(g.get("share_percent"), tr("re_ges_anteil") % (g.get("name") or "?"), 0, 100)
        num(g.get("tax_rate_percent"), tr("re_ges_steuersatz") % (g.get("name") or "?"), 0, 100)
    if ges and abs(total - 100.0) > 0.05:
        raise ValueError(tr("re_ges_summe") % total)
    num(o.get("distribution_percent"), tr("s_ausschuettung"), 0, 100)
    num(o.get("appreciation_percent"), tr("re_wertentwicklung_pct"), -50, 100)
    vk = o.get("sale") or {}
    num(vk.get("year"), tr("re_verkaufsjahr"), 1900, 2200)
    num(vk.get("costs_percent"), tr("re_verkaufskosten_pct"), 0, 100)


# ---------------------------------------------------------------------------
# Darlehen
# ---------------------------------------------------------------------------

class _Loan:
    def __init__(self, cfg: dict, start: Tuple[int, int]):
        self.cfg = cfg
        self.name = cfg.get("name") or "Darlehen"
        self.betrag = _f(cfg.get("amount"))
        self.rate = _f(cfg.get("interest_percent"))
        self.art = cfg.get("kind") or "annuity"
        self.abziehbar = bool(cfg.get("deductible", True))
        self.jaehrlich = (cfg.get("settlement") or "monthly") == "yearly"
        b = _d(cfg.get("begin"))
        self.beginn = (b.year, b.month) if b else start
        self.annuitaet = _f(cfg.get("annuity_month"))
        if not self.annuitaet and cfg.get("initial_repayment_percent") not in (None, ""):
            self.annuitaet = round((self.rate + _f(cfg.get("initial_repayment_percent"))) / 100.0 * self.betrag / 12.0, 2)
        self.tilgung_monat = _f(cfg.get("repayment_month"))
        self.sonder_monat = _f(cfg.get("special_repayment_month"))
        sa = _d(cfg.get("special_repayment_from"))
        self.sonder_ab = (sa.year, sa.month) if sa else None
        self.sondertilgungen: Dict[str, float] = {}
        for s in cfg.get("special_repayments") or []:
            dd = _d(s.get("date"))
            if dd and _f(s.get("amount")):
                self.sondertilgungen[_mk(dd.year, dd.month)] = self.sondertilgungen.get(_mk(dd.year, dd.month), 0.0) + _f(s.get("amount"))
        zb = _d(cfg.get("fixed_rate_until"))
        self.zinsbindung_bis = (zb.year, zb.month) if zb else None
        self.anschluss_zins = _f(cfg.get("followup_rate_percent"), self.rate) if cfg.get("followup_rate_percent") not in (None, "") else None
        fa = _d(cfg.get("maturity"))
        self.faelligkeit = (fa.year, fa.month) if fa else None
        self.faelligkeit_art = cfg.get("maturity_kind") or "open"
        self.saldo = 0.0
        self.jahresbasis = 0.0
        self.started = False
        self.hinweise: List[str] = []

    def rate_at(self, ym: Tuple[int, int]) -> float:
        if self.zinsbindung_bis and ym > self.zinsbindung_bis and self.anschluss_zins is not None:
            return self.anschluss_zins
        return self.rate

    def step(self, ym: Tuple[int, int]) -> Tuple[float, float, float]:
        """Ein Monat: (Zins, Tilgung, Sondertilgung) als positive Betraege. Saldo wird fortgeschrieben."""
        if ym < self.beginn:
            return 0.0, 0.0, 0.0
        first = not self.started
        if first:                               # Auszahlung (auch wenn der Beginn vor dem Horizont liegt)
            self.saldo = self.betrag
            self.jahresbasis = self.betrag
            self.started = True
        if ym[1] == 1 or first:
            self.jahresbasis = self.saldo       # Stand zum Jahresanfang (fuer jaehrliche Abrechnung)
        if self.saldo <= 0.005:
            self.saldo = 0.0
            return 0.0, 0.0, 0.0
        r = self.rate_at(ym) / 100.0
        base = self.jahresbasis if self.jaehrlich else self.saldo
        zins = base * r / 12.0
        tilg = 0.0
        if self.art == "annuity":
            tilg = max(0.0, self.annuitaet - zins)
        elif self.art == "repayment":
            tilg = self.tilgung_monat
        # endfaellig: keine Tilgung
        sonder = 0.0
        if self.sonder_monat and self.sonder_ab and ym >= self.sonder_ab:
            sonder += self.sonder_monat
        sonder += self.sondertilgungen.get(_mk(*ym), 0.0)
        if self.faelligkeit and ym == self.faelligkeit and self.faelligkeit_art == "payback":
            sonder += max(0.0, self.saldo - tilg)
        total = min(self.saldo, tilg + sonder)
        tilg = min(tilg, total)
        sonder = total - tilg
        self.saldo = self.saldo - total
        return zins, tilg, sonder


# ---------------------------------------------------------------------------
# Berechnung
# ---------------------------------------------------------------------------

def berechne(obj: dict, heute: Optional[date] = None) -> dict:
    o = normalize(obj)
    pruefe(o)
    heute = heute or date.today()
    start_d = _d(o.get("transfer_date")) or heute
    start = (start_d.year, start_d.month)
    horizon = max(1, min(60, int(_f(o.get("horizon_years"), 25))))
    end_year = start[0] + horizon - 1
    kp = _f(o.get("purchase_price"))
    nk_afa, nk_sofort = nebenkosten_summe(o)
    gesamtinvest = kp + nk_afa + nk_sofort
    geb = _f(o.get("building_share_percent")) / 100.0
    rnd = o.get("remaining_life_years")
    afa_satz = (1.0 / _f(rnd)) if rnd not in (None, "", 0, "0") and _f(rnd) > 0 else _f(o.get("depreciation_percent"), 2.0) / 100.0
    afa_basis = round(geb * (kp + nk_afa), 2)
    afa_jahr = round(afa_satz * afa_basis, 2)
    mi, ix, ko = o["rent"], o["rent"]["index"], o["costs"]
    nkm0 = _f(mi.get("net_rent_month"))
    umlage = _f(mi.get("utilities_month"))
    leer = _f(mi.get("vacancy_percent")) / 100.0
    loans = [_Loan(l, start) for l in o.get("loans") or []]
    darlehen_summe = sum(l.betrag for l in loans)
    ek = kp - darlehen_summe
    ges = [{"name": g.get("name") or "Gesellschafter", "share": _f(g.get("share_percent")) / 100.0, "rate_list": _f(g.get("tax_rate_percent")) / 100.0}
           for g in (o.get("partners") or [])]
    aussch = _f(o.get("distribution_percent")) / 100.0
    erstattung_cf = bool(o.get("tax_refund_in_cashflow", True))
    wert_g = _f(o.get("appreciation_percent")) / 100.0
    vk = o.get("sale") or {}
    vk_jahr = int(_f(vk.get("year"))) if vk.get("year") not in (None, "") else None
    vk_kosten = _f(vk.get("costs_percent")) / 100.0

    # Index/Steigerungslogik je Jahr (Anpassung zum Jahresbeginn; im ersten Jahr: Ausgangsmiete)
    years = list(range(start[0], end_year + 1))
    nkm_year: Dict[int, float] = {}
    kosten_faktor: Dict[int, float] = {}
    vpi_year: Dict[int, float] = {}
    vpi = _f(ix.get("cpi_current"), 100.0)
    vpi_last = _f(ix.get("cpi_base"), vpi)
    vpi_g = _f(ix.get("cpi_increase_percent")) / 100.0
    faktor = _f(ix.get("factor"), 1.0)
    schwelle = _f(ix.get("threshold_percent")) / 100.0
    art = ix.get("kind") or "cpi"
    nkm = nkm0
    kf = 1.0
    anpassungen: List[dict] = []
    for i, y in enumerate(years):
        if i > 0:
            if art == "cpi":
                vpi = vpi * (1 + vpi_g)
            elif art == "percent":
                nkm = nkm * (1 + _f(ix.get("increase_percent")) / 100.0)
        vpi_year[y] = vpi
        if art == "cpi":
            erh = vpi / vpi_last - 1 if vpi_last else 0.0
            if abs(erh) > schwelle + 1e-12 and faktor:
                nkm = nkm * (1 + erh * faktor)
                anpassungen.append({"year": y, "cpi": round(vpi, 2), "raise_percent": round(erh * 100, 2), "net_rent_new": round(nkm, 2)})
                vpi_last = vpi
        nkm_year[y] = nkm
        # Kostensteigerung
        if i > 0:
            if ko.get("increase") == "cpi":
                kf = kf * (1 + vpi_g)
            elif ko.get("increase") == "percent":
                kf = kf * (1 + _f(ko.get("increase_percent")) / 100.0)
        kosten_faktor[y] = kf

    # Monatsschleife
    monate: List[dict] = []
    ym = start
    cum_cf = 0.0
    wert = kp
    while ym[0] <= end_year:
        y, m = ym
        miete = nkm_year[y] * (1 - leer)
        nk_u = umlage
        kosten = -_f(ko.get("non_recoverable_pa")) * kosten_faktor[y] / 12.0
        ruecklage = -_f(ko.get("reserve_pa")) * kosten_faktor[y] / 12.0
        afa = -afa_satz * afa_basis / 12.0
        row = {"month": _mk(y, m), "rent": miete, "recoverable_costs": nk_u, "costs": kosten, "reserve": ruecklage, "depreciation": afa,
               "interest": 0.0, "interest_deductible": 0.0, "repayment": 0.0, "special_repayment": 0.0, "loans": {}}
        for l in loans:
            z, t, s = l.step(ym)
            row["loans"][l.name] = {"interest": -z, "repayment": -t, "special_repayment": -s, "balance_amount": -l.saldo}
            row["interest"] += -z
            if l.abziehbar:
                row["interest_deductible"] += -z
            row["repayment"] += -t
            row["special_repayment"] += -s
        wert = wert * (1 + wert_g) ** (1 / 12.0) if ym != start else kp
        row["value"] = wert
        row["remaining_debt"] = sum(l.saldo for l in loans)
        monate.append(row)
        ym = _add(y, m, 1)

    # Jahre verdichten
    jahre: List[dict] = []
    cum_vermoegensaufbau = 0.0
    cum_cf = 0.0
    for y in years:
        rows = [r for r in monate if int(r["month"][:4]) == y]
        if not rows:
            continue
        n = len(rows)
        miete = round(sum(r["rent"] for r in rows), 2)
        kosten = round(sum(r["costs"] for r in rows), 2)
        ruecklage = round(sum(r["reserve"] for r in rows), 2)
        zins = round(sum(r["interest"] for r in rows), 2)
        zins_abz = round(sum(r["interest_deductible"] for r in rows), 2)
        tilg = round(sum(r["repayment"] for r in rows), 2)
        sonder = round(sum(r["special_repayment"] for r in rows), 2)
        afa = round(sum(r["depreciation"] for r in rows), 2)
        sofort = -nk_sofort if y == start[0] else 0.0
        ergebnis = round(miete + kosten + zins_abz + afa + sofort, 2)
        steuer_ges = []
        steuer_sum = 0.0
        for g in ges:
            st = round(-g["share"] * ergebnis * g["rate_list"], 2)
            steuer_ges.append({"name": g["name"], "share_result": round(g["share"] * ergebnis, 2), "tax": st})
            steuer_sum += st
        steuer_sum = round(steuer_sum, 2)
        if ergebnis > 0:
            ausschuettung = round(-ergebnis * aussch, 2)
        else:
            ausschuettung = steuer_sum if erstattung_cf else 0.0
        cashflow = round(miete + kosten + ruecklage + ausschuettung + zins + tilg + sonder, 2)
        vermoegensaufbau = round(cashflow - tilg - sonder, 2)
        basis = ek + nk_afa + nk_sofort + cum_vermoegensaufbau
        ek_rendite = round(vermoegensaufbau / basis, 4) if basis > 0 else None
        cum_vermoegensaufbau += vermoegensaufbau
        cum_cf += cashflow
        restschuld = rows[-1]["remaining_debt"]
        wert_y = rows[-1]["value"]
        kapitaldienst = round(-(zins + tilg), 2)
        noi = round(miete + kosten + ruecklage, 2)
        jahre.append({
            "year": y, "months": n, "rent": miete, "recoverable_costs": round(sum(r["recoverable_costs"] for r in rows), 2), "costs": kosten, "reserve": ruecklage,
            "interest": zins, "interest_deductible": zins_abz, "repayment": tilg, "special_repayment": sonder, "depreciation": afa, "immediately_deductible": sofort,
            "result": ergebnis, "tax": steuer_sum, "tax_partners": steuer_ges, "result_after_tax": round(ergebnis + steuer_sum, 2),
            "distribution": ausschuettung, "cashflow": cashflow, "cashflow_cumulative": round(cum_cf, 2),
            "wealth_build": vermoegensaufbau, "return_on_equity": ek_rendite,
            "remaining_debt": restschuld, "value": wert_y, "equity_property": round(wert_y - restschuld, 2),
            "debt_service": kapitaldienst, "dscr": round(noi / kapitaldienst, 2) if kapitaldienst > 0 else None,
            "loans": {l.name: {"interest": round(sum(r["loans"][l.name]["interest"] for r in rows), 2),
                                  "repayment": round(sum(r["loans"][l.name]["repayment"] + r["loans"][l.name]["special_repayment"] for r in rows), 2),
                                  "balance_amount": rows[-1]["loans"][l.name]["balance_amount"]} for l in loans},
            "net_rent_monthly": nkm_year[y], "cpi": round(vpi_year.get(y, 0.0), 2),
        })

    # Monatszeilen fuer die Ausgabe runden
    for r in monate:
        for k in ("rent", "recoverable_costs", "costs", "reserve", "depreciation", "interest", "interest_deductible", "repayment", "special_repayment", "value", "remaining_debt"):
            r[k] = round(r[k], 2)
        for d in r["loans"].values():
            for k in d:
                d[k] = round(d[k], 2)
    for j in jahre:
        j["net_rent_monthly"] = round(j["net_rent_monthly"], 2)
        for k in ("remaining_debt", "value", "equity_property"):
            j[k] = round(j[k], 2)
        for d in j["loans"].values():
            d["balance_amount"] = round(d["balance_amount"], 2)

    # Kennzahlen
    jahresmiete = nkm0 * 12
    kennzahlen = {
        "purchase_price": kp, "closing_costs": round(nk_afa + nk_sofort, 2), "total_investment": round(gesamtinvest, 2),
        "equity": round(ek, 2), "equity_incl_costs": round(ek + nk_afa + nk_sofort, 2), "loans": round(darlehen_summe, 2),
        "equity_ratio": round(ek / kp, 4) if kp else None, "ltv": round(darlehen_summe / kp, 4) if kp else None,
        "price_factor": round(kp / jahresmiete, 2) if jahresmiete else None,
        "gross_rental_yield": round(jahresmiete / kp, 4) if kp else None,
        "net_rental_yield": round((jahresmiete - _f(ko.get("non_recoverable_pa")) - _f(ko.get("reserve_pa"))) / gesamtinvest, 4) if gesamtinvest else None,
        "price_sqm": round(kp / _f(o.get("area_sqm")), 2) if _f(o.get("area_sqm")) else None,
        "rent_sqm": round(nkm0 / _f(o.get("area_sqm")), 2) if _f(o.get("area_sqm")) else None,
        "depreciation_base": afa_basis, "depreciation_year": afa_jahr, "depreciation_rate": round(afa_satz * 100, 4),
        "debt_service_month": round(sum(l.annuitaet if l.art == "annuity" else (l.betrag * l.rate / 1200.0 + (l.tilgung_monat if l.art == "repayment" else 0)) for l in loans), 2),
        "rent_adjustments": anpassungen,
    }
    first_full = next((j for j in jahre if j["months"] == 12), jahre[0] if jahre else None)
    if first_full:
        kennzahlen["cashflow_year1"] = first_full["cashflow"]
        kennzahlen["cash_on_cash"] = round(first_full["cashflow"] / (ek + nk_afa + nk_sofort), 4) if (ek + nk_afa + nk_sofort) > 0 else None
        kennzahlen["dscr_year1"] = first_full["dscr"]
        kennzahlen["result_year1"] = first_full["result"]
    # IRR auf das eingesetzte Kapital (EK + NK) mit Verkauf im Verkaufsjahr bzw. am Horizontende
    cfs = [-(ek + nk_afa + nk_sofort)]
    exit_year = vk_jahr if vk_jahr and any(j["year"] == vk_jahr for j in jahre) else (jahre[-1]["year"] if jahre else None)
    for j in jahre:
        if exit_year and j["year"] > exit_year:
            break
        cf = j["cashflow"]
        if j["year"] == exit_year:
            cf += j["value"] * (1 - vk_kosten) - j["remaining_debt"]
        cfs.append(cf)
    kennzahlen["irr"] = _irr(cfs)
    kennzahlen["exit_year"] = exit_year
    if exit_year:
        je = next(j for j in jahre if j["year"] == exit_year)
        kennzahlen["net_sale_proceeds"] = round(je["value"] * (1 - vk_kosten) - je["remaining_debt"], 2)
    hinweise: List[str] = []
    for l in loans:
        if l.faelligkeit and l.faelligkeit_art == "open" and l.faelligkeit[0] <= end_year:
            rest = next((j["loans"][l.name]["balance_amount"] for j in jahre if j["year"] == l.faelligkeit[0]), 0.0)
            if abs(rest) > 0.5:
                hinweise.append(tr("s_s_faellig_02d_d_mit")
                                % (l.name, l.faelligkeit[1], l.faelligkeit[0], _eur(-rest)))
        if l.zinsbindung_bis and l.anschluss_zins is None and l.zinsbindung_bis[0] <= end_year:
            hinweise.append(tr("s_s_zinsbindung_endet_02d_d")
                            % (l.name, l.zinsbindung_bis[1], l.zinsbindung_bis[0]))
    if jahre:
        worst = min(jahre, key=lambda j: j["cashflow_cumulative"])
        if worst["cashflow_cumulative"] < -0.5:
            hinweise.append(tr("s_kumulierter_cashflow_bis_d_negativ") % (worst["year"], _eur(worst["cashflow_cumulative"])))
    return {"inputs": o, "figures": kennzahlen, "years": jahre, "months": monate, "hints": hinweise,
            "loan_names": [l.name for l in loans], "loans_yearly": [l.name for l in loans if l.jaehrlich], "start": _mk(*start)}


def _irr(cfs: List[float]) -> Optional[float]:
    if len(cfs) < 2 or cfs[0] >= 0:
        return None
    lo, hi = -0.99, 10.0

    def npv(r):
        return sum(cf / (1 + r) ** i for i, cf in enumerate(cfs))
    try:
        if npv(lo) * npv(hi) > 0:
            return None
        for _ in range(200):
            mid = (lo + hi) / 2
            if npv(lo) * npv(mid) <= 0:
                hi = mid
            else:
                lo = mid
        return round((lo + hi) / 2, 4)
    except (OverflowError, ZeroDivisionError):
        return None


def _eur(v: float) -> str:
    s = "{:,.2f}".format(v).replace(",", "X").replace(".", ",").replace("X", ".")
    return s


# ---------------------------------------------------------------------------
# Monatsreihen fuer die Planung (Bereich)
# ---------------------------------------------------------------------------

def planreihen(res: dict) -> dict:
    """Monatsreihen (JJJJ-MM -> Betrag, Vorzeichen wie im Kapitalfluss) fuer die Uebernahme in die Planung."""
    out = {"rent": {}, "costs": {}, "reserve": {}, "distribution": {}, "value": {}, "loans": {}}
    for r in res["months"]:
        mk = r["month"]
        out["rent"][mk] = r["rent"] + r["recoverable_costs"]
        out["costs"][mk] = r["costs"] - r["recoverable_costs"]
        out["reserve"][mk] = r["reserve"]
        out["value"][mk] = r["value"]
        for name, d in r["loans"].items():
            # (yearly: settled once a year on the balance of 1 January -- the plan carries it on from the account that way)
            x = out["loans"].setdefault(name, {"interest": {}, "repayment": {}, "balance_amount": {}, "yearly": name in (res.get("loans_yearly") or ())})
            x["interest"][mk] = d["interest"]
            x["repayment"][mk] = d["repayment"] + d["special_repayment"]
            x["balance_amount"][mk] = d["balance_amount"]
    # Ausschuettung: Jahresbetrag gleichmaessig auf die Monate des Jahres (vereinfachend)
    for j in res["years"]:
        n = j["months"] or 12
        for r in res["months"]:
            if int(r["month"][:4]) == j["year"]:
                out["distribution"][r["month"]] = round(j["distribution"] / n, 2)
    return out


# ---------------------------------------------------------------------------
# Excel-Export
# ---------------------------------------------------------------------------

def sheets(res: dict):
    from excel import Sheet
    o, K, J = res["inputs"], res["figures"], res["years"]
    inputs = [[tr("re_objekt"), o.get("name")], [tr("re_art"), o.get("kind")], [tr("s_uebergang"), o.get("transfer_date")], [tr("re_kaufpreis"), _f(o.get("purchase_price"))],
              [tr("re_nebenkosten_afa_basis"), K["closing_costs"]], [tr("re_gesamtinvestition"), K["total_investment"]], [tr("re_eigenkapital"), K["equity"]],
              [tr("s_gebaeudeanteil"), _f(o.get("building_share_percent"))], [tr("re_afa_satz_pct"), K["depreciation_rate"]], [tr("re_afa_basis"), K["depreciation_base"]], [tr("re_afa_p_a"), K["depreciation_year"]],
              [tr("re_nettokaltmiete_monat"), _f(o["rent"].get("net_rent_month"))], [tr("re_umlage_monat"), _f(o["rent"].get("utilities_month"))],
              [tr("re_leerstand_pct"), _f(o["rent"].get("vacancy_percent"))], [tr("re_index"), str(o["rent"]["index"])],
              [tr("s_kosten_nicht_umlagefaehig_p_a"), _f(o["costs"].get("non_recoverable_pa"))], [tr("re_ruecklage_p_a"), _f(o["costs"].get("reserve_pa"))],
              [tr("re_wertentwicklung_pct_p_a"), _f(o.get("appreciation_percent"))], [tr("s_ausschuettung_des_ergebnisses"), _f(o.get("distribution_percent"))]]
    for l in o.get("loans") or []:
        inputs.append([tr("re_darlehen_n") % l.get("name"), tr("s_s_s_s_annuitaet_s") % (
            _f(l.get("amount")), _f(l.get("interest_percent")), l.get("kind"), l.get("annuity_month") or "", l.get("repayment_month") or "", l.get("special_repayment_month") or "",
            l.get("special_repayment_from") or "", l.get("fixed_rate_until") or "", l.get("followup_rate_percent") or "", l.get("settlement"))])
    for g in o.get("partners") or []:
        inputs.append([tr("re_gesellschafter_n") % g.get("name"), tr("s_s_steuersatz_s") % (_f(g.get("share_percent")), _f(g.get("tax_rate_percent")))])
    kz = [[k, v] for k, v in K.items() if not isinstance(v, (list, dict))]
    names = res["loan_names"]
    head = [tr("re_jahr"), tr("re_monate"), tr("re_miete"), tr("re_umlage"), tr("re_kosten"), tr("s_ruecklage"), tr("re_zinsen"), tr("re_tilgung"), tr("re_sondertilgung"), tr("re_afa"), tr("re_sofort_abziehbar"), tr("re_ergebnis"), tr("re_steuer"), tr("re_ergebnis_n_st"),
            tr("s_ausschuettung_2"), tr("re_cashflow"), tr("re_cashflow_kum"), tr("re_vermoegensaufbau"), tr("re_ek_rendite"), tr("re_restschuld"), tr("re_objektwert"), tr("re_ek_im_objekt"), tr("re_dscr"), tr("re_nkm_monat"), tr("re_vpi")]
    for n in names:
        head += [n + " " + tr("re_zins"), n + " " + tr("re_tilgung"), n + " " + tr("x_saldo")]
    rows = []
    for j in J:
        r = [j["year"], j["months"], j["rent"], j["recoverable_costs"], j["costs"], j["reserve"], j["interest"], j["repayment"], j["special_repayment"], j["depreciation"], j["immediately_deductible"], j["result"], j["tax"],
             j["result_after_tax"], j["distribution"], j["cashflow"], j["cashflow_cumulative"], j["wealth_build"], j["return_on_equity"], j["remaining_debt"], j["value"], j["equity_property"], j["dscr"], j["net_rent_monthly"], j["cpi"]]
        for n in names:
            d = j["loans"][n]
            r += [d["interest"], d["repayment"], d["balance_amount"]]
        rows.append(r)
    mhead = [tr("re_monat"), tr("re_miete"), tr("re_umlage"), tr("re_kosten"), tr("s_ruecklage"), tr("re_zinsen"), tr("re_tilgung"), tr("re_sondertilgung"), tr("re_afa"), tr("re_restschuld"), tr("re_objektwert")]
    mrows = [[m["month"], m["rent"], m["recoverable_costs"], m["costs"], m["reserve"], m["interest"], m["repayment"], m["special_repayment"], m["depreciation"], m["remaining_debt"], m["value"]] for m in res["months"]]
    return [Sheet(tr("re_eingaben"), [tr("re_parameter"), tr("re_wert")], inputs, widths=[34, 80], freeze="A2"),
            Sheet(tr("re_kennzahlen"), [tr("re_kennzahl"), tr("re_wert")], kz, widths=[34, 20], freeze="A2"),
            Sheet(tr("re_jahre"), head, rows, widths=[8] + [12] * (len(head) - 1), freeze="B2"),
            Sheet(tr("re_monate"), mhead, mrows, widths=[10] + [12] * (len(mhead) - 1), freeze="B2")]
