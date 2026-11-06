"""Immobilienkalkulation: Objekt, Finanzierung, Indexmiete, Kosten, AfA, Steuer, Cashflow, Kennzahlen.

Rechnet auf Monatsbasis (Zeitachse ab Uebergangsstichtag, Horizont in Jahren) und verdichtet
auf Jahre. Je Darlehen waehlbar: Abrechnung monatlich (Bank: Zins auf den laufenden Saldo,
monatliche Verrechnung) oder jaehrlich (z. B. Verkaeuferdarlehen: Zins auf den Stand zum
1. Januar, nachschuessig; Tilgung = Jahreszahlung - Jahreszins).

Alle Eingaben sind reine Daten (dict), damit Kalkulationen gespeichert, kopiert (Szenarien)
und als Paket weitergegeben werden koennen. Betraege in Euro, Saetze in Prozent.

Eingabeschema (alle Felder optional, sinnvolle Standardwerte):
{
  "name": "Objekt", "art": "gewerbe|wohnen", "flaeche_qm": 0, "einheiten": 1,
  "kaufpreis": 0, "uebergang": "2026-05-01",          # erster Monat mit Nutzen und Lasten (Miete)
  "nebenkosten": {"grunderwerbsteuer_prozent": 3.5, "notar": 0, "grundbuch": 0, "makler": 0, "sonstige_afa": 0,
                  "sofort_abziehbar": 0},                # Posten, die zur AfA-Basis zaehlen bzw. sofort abziehbar sind
  "gebaeudeanteil_prozent": 70, "afa_prozent": 2.0, "restnutzungsdauer_jahre": null,   # RND ueberschreibt afa_prozent
  "miete": {"nettokalt_monat": 0, "nebenkosten_monat": 0, "leerstand_prozent": 0,
            "index": {"art": "vpi|prozent|keine", "vpi_basis": 122.7, "vpi_aktuell": 122.7, "vpi_steigerung_prozent": 1.9,
                      "faktor": 1.0, "schwelle_prozent": 0, "steigerung_prozent": 0}},
  "kosten": {"nicht_umlagefaehig_pa": 0, "ruecklage_pa": 0, "steigerung": "vpi|keine|prozent", "steigerung_prozent": 0},
  "darlehen": [{"name": "Darlehen 1", "betrag": 0, "zins_prozent": 0, "art": "annuitaet|tilgung|endfaellig",
                "annuitaet_monat": null, "anfangstilgung_prozent": null, "tilgung_monat": null,
                "sondertilgung_monat": 0, "sondertilgung_ab": null, "sondertilgungen": [{"datum": "2027-06-01", "betrag": 0}],
                "zinsbindung_bis": null, "anschluss_zins_prozent": null, "faelligkeit": null, "faelligkeit_art": "rueckzahlung|anschluss|offen",
                "abziehbar": true, "abrechnung": "monatlich|jaehrlich", "beginn": null, "konto": "UUID | Name"}],
  "gesellschafter": [{"name": "A", "anteil_prozent": 50, "steuersatz_prozent": 42}],
  "ausschuettung_prozent": 48, "steuererstattung_in_cashflow": true,
  "wertentwicklung_prozent": 2.0, "verkauf": {"jahr": null, "kosten_prozent": 0},
  "horizont_jahre": 25
}
"""
from __future__ import annotations

import copy
import math
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


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
    o.setdefault("art", "gewerbe")
    nk = o.setdefault("nebenkosten", {})
    for k, v in (("grunderwerbsteuer_prozent", 3.5), ("notar", 0), ("grundbuch", 0), ("makler", 0), ("sonstige_afa", 0), ("sofort_abziehbar", 0)):
        nk.setdefault(k, v)
    o.setdefault("gebaeudeanteil_prozent", 70.0)
    o.setdefault("afa_prozent", 2.0)
    mi = o.setdefault("miete", {})
    for k, v in (("nettokalt_monat", 0), ("nebenkosten_monat", 0), ("leerstand_prozent", 0)):
        mi.setdefault(k, v)
    ix = mi.setdefault("index", {})
    for k, v in (("art", "vpi"), ("vpi_basis", 100.0), ("vpi_aktuell", 100.0), ("vpi_steigerung_prozent", 2.0), ("faktor", 1.0), ("schwelle_prozent", 0), ("steigerung_prozent", 0)):
        ix.setdefault(k, v)
    ko = o.setdefault("kosten", {})
    for k, v in (("nicht_umlagefaehig_pa", 0), ("ruecklage_pa", 0), ("steigerung", "vpi"), ("steigerung_prozent", 0)):
        ko.setdefault(k, v)
    o.setdefault("darlehen", [])
    for i, l in enumerate(o["darlehen"]):
        l.setdefault("name", "Darlehen %d" % (i + 1))
        l.setdefault("art", "annuitaet")
        l.setdefault("abziehbar", True)
        l.setdefault("abrechnung", "monatlich")
        l.setdefault("sondertilgungen", [])
        l.setdefault("faelligkeit_art", "offen")
    o.setdefault("gesellschafter", [{"name": "Eigentümer", "anteil_prozent": 100, "steuersatz_prozent": 42}])
    o.setdefault("ausschuettung_prozent", 48)
    o.setdefault("steuererstattung_in_cashflow", True)
    o.setdefault("wertentwicklung_prozent", 2.0)
    o.setdefault("verkauf", {"jahr": None, "kosten_prozent": 0})
    o.setdefault("horizont_jahre", 25)
    o.setdefault("uebergang", date.today().isoformat())
    return o


def nebenkosten_summe(o: dict) -> Tuple[float, float]:
    """(NK fuer AfA-Basis, sofort abziehbare NK)."""
    nk = o["nebenkosten"]
    kp = _f(o.get("kaufpreis"))
    afa_nk = kp * _f(nk.get("grunderwerbsteuer_prozent")) / 100.0 + _f(nk.get("notar")) + _f(nk.get("grundbuch")) + _f(nk.get("makler")) + _f(nk.get("sonstige_afa"))
    return round(afa_nk, 2), round(_f(nk.get("sofort_abziehbar")), 2)


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
            raise ValueError("%s: keine Zahl (%r)." % (label, v))
        if v in (None, ""):
            return 0.0
        x = _f(v)
        if lo is not None and x < lo:
            raise ValueError("%s: darf nicht kleiner als %s sein." % (label, lo))
        if hi is not None and x > hi:
            raise ValueError("%s: darf nicht groesser als %s sein." % (label, hi))
        return x

    def dat(v, label, required=False):
        if v in (None, ""):
            if required:
                raise ValueError("%s fehlt." % label)
            return
        if _d(v) is None:
            raise ValueError("%s: kein Datum (JJJJ-MM)." % label)

    num(o.get("kaufpreis"), "Kaufpreis", 0)
    dat(o.get("uebergang"), "Übergang", required=True)
    num(o.get("horizont_jahre"), "Horizont", 1, 60)
    num(o.get("flaeche_qm"), "Fläche", 0)
    num(o.get("einheiten"), "Einheiten", 0)
    nk = o.get("nebenkosten") or {}
    num(nk.get("grunderwerbsteuer_prozent"), "Grunderwerbsteuer %", 0, 100)
    for k, label in (("notar", "Notar"), ("grundbuch", "Grundbuch"), ("makler", "Makler"), ("sonstige_afa", "Sonstige Nebenkosten"), ("sofort_abziehbar", "Sofort abziehbare Nebenkosten")):
        num(nk.get(k), label, 0)
    num(o.get("gebaeudeanteil_prozent"), "Gebäudeanteil %", 0, 100)
    num(o.get("afa_prozent"), "AfA %", 0, 100)
    num(o.get("restnutzungsdauer_jahre"), "Restnutzungsdauer", 0, 200)
    mi = o.get("miete") or {}
    num(mi.get("nettokalt_monat"), "Nettokaltmiete", 0)
    num(mi.get("nebenkosten_monat"), "Umlage", 0)
    num(mi.get("leerstand_prozent"), "Leerstand %", 0, 100)
    ix = mi.get("index") or {}
    if ix.get("art") not in (None, "", "vpi", "prozent", "keine"):
        raise ValueError("Mietanpassung: unbekannte Art %r." % ix.get("art"))
    num(ix.get("vpi_basis"), "VPI-Basis", 0.01)
    num(ix.get("vpi_aktuell"), "VPI aktuell", 0.01)
    num(ix.get("vpi_steigerung_prozent"), "VPI-Annahme %", -50, 100)
    num(ix.get("faktor"), "Weitergabe-Faktor", 0, 1)
    num(ix.get("schwelle_prozent"), "Schwelle %", 0, 100)
    num(ix.get("steigerung_prozent"), "Mietsteigerung %", -50, 100)
    ko = o.get("kosten") or {}
    num(ko.get("nicht_umlagefaehig_pa"), "Kosten nicht umlagefähig", 0)
    num(ko.get("ruecklage_pa"), "Rücklage", 0)
    if ko.get("steigerung") not in (None, "", "vpi", "prozent", "keine"):
        raise ValueError("Kostensteigerung: unbekannte Art %r." % ko.get("steigerung"))
    num(ko.get("steigerung_prozent"), "Kostensteigerung %", -50, 100)
    names = set()
    for i, l in enumerate(o.get("darlehen") or []):
        if not isinstance(l, dict):
            raise ValueError("Darlehen %d: ungueltig." % (i + 1))
        label = "Darlehen %s" % (l.get("name") or i + 1)
        if l.get("name") in names:
            raise ValueError("%s: Name doppelt." % label)
        names.add(l.get("name"))
        num(l.get("betrag"), label + " Betrag", 0)
        num(l.get("zins_prozent"), label + " Zins %", 0, 100)
        if l.get("art") not in (None, "", "annuitaet", "tilgung", "endfaellig"):
            raise ValueError("%s: unbekannte Art %r." % (label, l.get("art")))
        num(l.get("annuitaet_monat"), label + " Annuität", 0)
        num(l.get("anfangstilgung_prozent"), label + " Anfangstilgung %", 0, 100)
        num(l.get("tilgung_monat"), label + " Tilgung/Monat", 0)
        num(l.get("sondertilgung_monat"), label + " Sondertilgung/Monat", 0)
        num(l.get("anschluss_zins_prozent"), label + " Anschlusszins %", 0, 100)
        for k, lab in (("sondertilgung_ab", "Sondertilgung ab"), ("zinsbindung_bis", "Zinsbindung bis"), ("faelligkeit", "Fälligkeit"), ("beginn", "Beginn")):
            dat(l.get(k), "%s %s" % (label, lab))
        for st in l.get("sondertilgungen") or []:
            if not isinstance(st, dict):
                raise ValueError("%s: Sondertilgung ungueltig." % label)
            dat(st.get("datum"), label + " Sondertilgung Datum", required=True)
            num(st.get("betrag"), label + " Sondertilgung Betrag", 0)
        if (l.get("art") or "annuitaet") == "annuitaet" and _f(l.get("betrag")) > 0 and not _f(l.get("annuitaet_monat")) and l.get("anfangstilgung_prozent") in (None, ""):
            raise ValueError("%s: Annuität je Monat oder Anfangstilgung angeben." % label)
        if (l.get("abrechnung") or "monatlich") not in ("monatlich", "jaehrlich"):
            raise ValueError("%s: Abrechnung muss monatlich oder jaehrlich sein." % label)
    ges = o.get("gesellschafter") or []
    total = 0.0
    for g in ges:
        if not isinstance(g, dict):
            raise ValueError("Gesellschafter: ungueltig.")
        total += num(g.get("anteil_prozent"), "Gesellschafter %s Anteil %%" % (g.get("name") or "?"), 0, 100)
        num(g.get("steuersatz_prozent"), "Gesellschafter %s Steuersatz %%" % (g.get("name") or "?"), 0, 100)
    if ges and abs(total - 100.0) > 0.05:
        raise ValueError("Gesellschafteranteile ergeben %.2f %% statt 100 %%." % total)
    num(o.get("ausschuettung_prozent"), "Ausschüttung %", 0, 100)
    num(o.get("wertentwicklung_prozent"), "Wertentwicklung %", -50, 100)
    vk = o.get("verkauf") or {}
    num(vk.get("jahr"), "Verkaufsjahr", 1900, 2200)
    num(vk.get("kosten_prozent"), "Verkaufskosten %", 0, 100)


# ---------------------------------------------------------------------------
# Darlehen
# ---------------------------------------------------------------------------

class _Loan:
    def __init__(self, cfg: dict, start: Tuple[int, int]):
        self.cfg = cfg
        self.name = cfg.get("name") or "Darlehen"
        self.betrag = _f(cfg.get("betrag"))
        self.rate = _f(cfg.get("zins_prozent"))
        self.art = cfg.get("art") or "annuitaet"
        self.abziehbar = bool(cfg.get("abziehbar", True))
        self.jaehrlich = (cfg.get("abrechnung") or "monatlich") == "jaehrlich"
        b = _d(cfg.get("beginn"))
        self.beginn = (b.year, b.month) if b else start
        self.annuitaet = _f(cfg.get("annuitaet_monat"))
        if not self.annuitaet and cfg.get("anfangstilgung_prozent") not in (None, ""):
            self.annuitaet = round((self.rate + _f(cfg.get("anfangstilgung_prozent"))) / 100.0 * self.betrag / 12.0, 2)
        self.tilgung_monat = _f(cfg.get("tilgung_monat"))
        self.sonder_monat = _f(cfg.get("sondertilgung_monat"))
        sa = _d(cfg.get("sondertilgung_ab"))
        self.sonder_ab = (sa.year, sa.month) if sa else None
        self.sondertilgungen: Dict[str, float] = {}
        for s in cfg.get("sondertilgungen") or []:
            dd = _d(s.get("datum"))
            if dd and _f(s.get("betrag")):
                self.sondertilgungen[_mk(dd.year, dd.month)] = self.sondertilgungen.get(_mk(dd.year, dd.month), 0.0) + _f(s.get("betrag"))
        zb = _d(cfg.get("zinsbindung_bis"))
        self.zinsbindung_bis = (zb.year, zb.month) if zb else None
        self.anschluss_zins = _f(cfg.get("anschluss_zins_prozent"), self.rate) if cfg.get("anschluss_zins_prozent") not in (None, "") else None
        fa = _d(cfg.get("faelligkeit"))
        self.faelligkeit = (fa.year, fa.month) if fa else None
        self.faelligkeit_art = cfg.get("faelligkeit_art") or "offen"
        self.saldo = 0.0
        self.jahresbasis = 0.0
        self.started = False
        self.hinweise: List[str] = []

    def rate_at(self, ym: Tuple[int, int]) -> float:
        if self.zinsbindung_bis and ym > self.zinsbindung_bis and self.anschluss_zins is not None:
            return self.anschluss_zins
        return self.rate

    def step(self, ym: Tuple[int, int], months_in_year_so_far: int) -> Tuple[float, float, float]:
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
        if self.art == "annuitaet":
            tilg = max(0.0, self.annuitaet - zins)
        elif self.art == "tilgung":
            tilg = self.tilgung_monat
        # endfaellig: keine Tilgung
        sonder = 0.0
        if self.sonder_monat and self.sonder_ab and ym >= self.sonder_ab:
            sonder += self.sonder_monat
        sonder += self.sondertilgungen.get(_mk(*ym), 0.0)
        if self.faelligkeit and ym == self.faelligkeit and self.faelligkeit_art == "rueckzahlung":
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
    start_d = _d(o.get("uebergang")) or heute
    start = (start_d.year, start_d.month)
    horizon = max(1, min(60, int(_f(o.get("horizont_jahre"), 25))))
    end_year = start[0] + horizon - 1
    kp = _f(o.get("kaufpreis"))
    nk_afa, nk_sofort = nebenkosten_summe(o)
    gesamtinvest = kp + nk_afa + nk_sofort
    geb = _f(o.get("gebaeudeanteil_prozent")) / 100.0
    rnd = o.get("restnutzungsdauer_jahre")
    afa_satz = (1.0 / _f(rnd)) if rnd not in (None, "", 0, "0") and _f(rnd) > 0 else _f(o.get("afa_prozent"), 2.0) / 100.0
    afa_basis = round(geb * (kp + nk_afa), 2)
    afa_jahr = round(afa_satz * afa_basis, 2)
    mi, ix, ko = o["miete"], o["miete"]["index"], o["kosten"]
    nkm0 = _f(mi.get("nettokalt_monat"))
    umlage = _f(mi.get("nebenkosten_monat"))
    leer = _f(mi.get("leerstand_prozent")) / 100.0
    loans = [_Loan(l, start) for l in o.get("darlehen") or []]
    darlehen_summe = sum(l.betrag for l in loans)
    ek = kp - darlehen_summe
    ges = [{"name": g.get("name") or "Gesellschafter", "anteil": _f(g.get("anteil_prozent")) / 100.0, "satz": _f(g.get("steuersatz_prozent")) / 100.0}
           for g in (o.get("gesellschafter") or [])]
    aussch = _f(o.get("ausschuettung_prozent")) / 100.0
    erstattung_cf = bool(o.get("steuererstattung_in_cashflow", True))
    wert_g = _f(o.get("wertentwicklung_prozent")) / 100.0
    vk = o.get("verkauf") or {}
    vk_jahr = int(_f(vk.get("jahr"))) if vk.get("jahr") not in (None, "") else None
    vk_kosten = _f(vk.get("kosten_prozent")) / 100.0

    # Index/Steigerungslogik je Jahr (Anpassung zum Jahresbeginn; im ersten Jahr: Ausgangsmiete)
    years = list(range(start[0], end_year + 1))
    nkm_year: Dict[int, float] = {}
    kosten_faktor: Dict[int, float] = {}
    vpi_year: Dict[int, float] = {}
    vpi = _f(ix.get("vpi_aktuell"), 100.0)
    vpi_last = _f(ix.get("vpi_basis"), vpi)
    vpi_g = _f(ix.get("vpi_steigerung_prozent")) / 100.0
    faktor = _f(ix.get("faktor"), 1.0)
    schwelle = _f(ix.get("schwelle_prozent")) / 100.0
    art = ix.get("art") or "vpi"
    nkm = nkm0
    kf = 1.0
    anpassungen: List[dict] = []
    for i, y in enumerate(years):
        if i > 0:
            if art == "vpi":
                vpi = vpi * (1 + vpi_g)
            elif art == "prozent":
                nkm = nkm * (1 + _f(ix.get("steigerung_prozent")) / 100.0)
        vpi_year[y] = vpi
        if art == "vpi":
            erh = vpi / vpi_last - 1 if vpi_last else 0.0
            if abs(erh) > schwelle + 1e-12 and faktor:
                nkm = nkm * (1 + erh * faktor)
                anpassungen.append({"jahr": y, "vpi": round(vpi, 2), "erhoehung_prozent": round(erh * 100, 2), "nkm_neu": round(nkm, 2)})
                vpi_last = vpi
        nkm_year[y] = nkm
        # Kostensteigerung
        if i > 0:
            if ko.get("steigerung") == "vpi":
                kf = kf * (1 + vpi_g)
            elif ko.get("steigerung") == "prozent":
                kf = kf * (1 + _f(ko.get("steigerung_prozent")) / 100.0)
        kosten_faktor[y] = kf

    # Monatsschleife
    monate: List[dict] = []
    ym = start
    cum_cf = 0.0
    wert = kp
    while ym[0] <= end_year:
        y, m = ym
        months_in_year = m - (start[1] if y == start[0] else 1) + 1
        miete = nkm_year[y] * (1 - leer)
        nk_u = umlage
        kosten = -_f(ko.get("nicht_umlagefaehig_pa")) * kosten_faktor[y] / 12.0
        ruecklage = -_f(ko.get("ruecklage_pa")) * kosten_faktor[y] / 12.0
        afa = -afa_satz * afa_basis / 12.0
        row = {"monat": _mk(y, m), "miete": miete, "umlage": nk_u, "kosten": kosten, "ruecklage": ruecklage, "afa": afa,
               "zins": 0.0, "zins_abziehbar": 0.0, "tilgung": 0.0, "sondertilgung": 0.0, "darlehen": {}}
        for l in loans:
            z, t, s = l.step(ym, months_in_year)
            row["darlehen"][l.name] = {"zins": -z, "tilgung": -t, "sondertilgung": -s, "saldo": -l.saldo}
            row["zins"] += -z
            if l.abziehbar:
                row["zins_abziehbar"] += -z
            row["tilgung"] += -t
            row["sondertilgung"] += -s
        wert = wert * (1 + wert_g) ** (1 / 12.0) if ym != start else kp
        row["wert"] = wert
        row["restschuld"] = sum(l.saldo for l in loans)
        monate.append(row)
        ym = _add(y, m, 1)

    # Jahre verdichten
    jahre: List[dict] = []
    cum_vermoegensaufbau = 0.0
    cum_cf = 0.0
    for y in years:
        rows = [r for r in monate if int(r["monat"][:4]) == y]
        if not rows:
            continue
        n = len(rows)
        miete = round(sum(r["miete"] for r in rows), 2)
        kosten = round(sum(r["kosten"] for r in rows), 2)
        ruecklage = round(sum(r["ruecklage"] for r in rows), 2)
        zins = round(sum(r["zins"] for r in rows), 2)
        zins_abz = round(sum(r["zins_abziehbar"] for r in rows), 2)
        tilg = round(sum(r["tilgung"] for r in rows), 2)
        sonder = round(sum(r["sondertilgung"] for r in rows), 2)
        afa = round(sum(r["afa"] for r in rows), 2)
        sofort = -nk_sofort if y == start[0] else 0.0
        ergebnis = round(miete + kosten + zins_abz + afa + sofort, 2)
        steuer_ges = []
        steuer_sum = 0.0
        for g in ges:
            st = round(-g["anteil"] * ergebnis * g["satz"], 2)
            steuer_ges.append({"name": g["name"], "anteil_ergebnis": round(g["anteil"] * ergebnis, 2), "steuer": st})
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
        restschuld = rows[-1]["restschuld"]
        wert_y = rows[-1]["wert"]
        kapitaldienst = round(-(zins + tilg), 2)
        noi = round(miete + kosten + ruecklage, 2)
        jahre.append({
            "jahr": y, "monate": n, "miete": miete, "umlage": round(sum(r["umlage"] for r in rows), 2), "kosten": kosten, "ruecklage": ruecklage,
            "zins": zins, "zins_abziehbar": zins_abz, "tilgung": tilg, "sondertilgung": sonder, "afa": afa, "sofort_abziehbar": sofort,
            "ergebnis": ergebnis, "steuer": steuer_sum, "steuer_gesellschafter": steuer_ges, "ergebnis_nach_steuern": round(ergebnis + steuer_sum, 2),
            "ausschuettung": ausschuettung, "cashflow": cashflow, "cashflow_kumuliert": round(cum_cf, 2),
            "vermoegensaufbau": vermoegensaufbau, "ek_rendite": ek_rendite,
            "restschuld": restschuld, "wert": wert_y, "eigenkapital_objekt": round(wert_y - restschuld, 2),
            "kapitaldienst": kapitaldienst, "dscr": round(noi / kapitaldienst, 2) if kapitaldienst > 0 else None,
            "darlehen": {l.name: {"zins": round(sum(r["darlehen"][l.name]["zins"] for r in rows), 2),
                                  "tilgung": round(sum(r["darlehen"][l.name]["tilgung"] + r["darlehen"][l.name]["sondertilgung"] for r in rows), 2),
                                  "saldo": rows[-1]["darlehen"][l.name]["saldo"]} for l in loans},
            "nkm_monat": nkm_year[y], "vpi": round(vpi_year.get(y, 0.0), 2),
        })

    # Monatszeilen fuer die Ausgabe runden
    for r in monate:
        for k in ("miete", "umlage", "kosten", "ruecklage", "afa", "zins", "zins_abziehbar", "tilgung", "sondertilgung", "wert", "restschuld"):
            r[k] = round(r[k], 2)
        for d in r["darlehen"].values():
            for k in d:
                d[k] = round(d[k], 2)
    for j in jahre:
        j["nkm_monat"] = round(j["nkm_monat"], 2)
        for k in ("restschuld", "wert", "eigenkapital_objekt"):
            j[k] = round(j[k], 2)
        for d in j["darlehen"].values():
            d["saldo"] = round(d["saldo"], 2)

    # Kennzahlen
    jahresmiete = nkm0 * 12
    kennzahlen = {
        "kaufpreis": kp, "nebenkosten": round(nk_afa + nk_sofort, 2), "gesamtinvestition": round(gesamtinvest, 2),
        "eigenkapital": round(ek, 2), "eigenkapital_inkl_nk": round(ek + nk_afa + nk_sofort, 2), "darlehen": round(darlehen_summe, 2),
        "ek_quote": round(ek / kp, 4) if kp else None, "ltv": round(darlehen_summe / kp, 4) if kp else None,
        "kaufpreisfaktor": round(kp / jahresmiete, 2) if jahresmiete else None,
        "bruttomietrendite": round(jahresmiete / kp, 4) if kp else None,
        "nettomietrendite": round((jahresmiete - _f(ko.get("nicht_umlagefaehig_pa")) - _f(ko.get("ruecklage_pa"))) / gesamtinvest, 4) if gesamtinvest else None,
        "preis_qm": round(kp / _f(o.get("flaeche_qm")), 2) if _f(o.get("flaeche_qm")) else None,
        "miete_qm": round(nkm0 / _f(o.get("flaeche_qm")), 2) if _f(o.get("flaeche_qm")) else None,
        "afa_basis": afa_basis, "afa_jahr": afa_jahr, "afa_satz": round(afa_satz * 100, 4),
        "kapitaldienst_monat": round(sum(l.annuitaet if l.art == "annuitaet" else (l.betrag * l.rate / 1200.0 + (l.tilgung_monat if l.art == "tilgung" else 0)) for l in loans), 2),
        "mietanpassungen": anpassungen,
    }
    first_full = next((j for j in jahre if j["monate"] == 12), jahre[0] if jahre else None)
    if first_full:
        kennzahlen["cashflow_jahr1"] = first_full["cashflow"]
        kennzahlen["cash_on_cash"] = round(first_full["cashflow"] / (ek + nk_afa + nk_sofort), 4) if (ek + nk_afa + nk_sofort) > 0 else None
        kennzahlen["dscr_jahr1"] = first_full["dscr"]
        kennzahlen["ergebnis_jahr1"] = first_full["ergebnis"]
    # IRR auf das eingesetzte Kapital (EK + NK) mit Verkauf im Verkaufsjahr bzw. am Horizontende
    cfs = [-(ek + nk_afa + nk_sofort)]
    exit_year = vk_jahr if vk_jahr and any(j["jahr"] == vk_jahr for j in jahre) else (jahre[-1]["jahr"] if jahre else None)
    for j in jahre:
        if exit_year and j["jahr"] > exit_year:
            break
        cf = j["cashflow"]
        if j["jahr"] == exit_year:
            cf += j["wert"] * (1 - vk_kosten) - j["restschuld"]
        cfs.append(cf)
    kennzahlen["irr"] = _irr(cfs)
    kennzahlen["exit_jahr"] = exit_year
    if exit_year:
        je = next(j for j in jahre if j["jahr"] == exit_year)
        kennzahlen["verkaufserloes_netto"] = round(je["wert"] * (1 - vk_kosten) - je["restschuld"], 2)
    hinweise: List[str] = []
    for l in loans:
        if l.faelligkeit and l.faelligkeit_art == "offen" and l.faelligkeit[0] <= end_year:
            rest = next((j["darlehen"][l.name]["saldo"] for j in jahre if j["jahr"] == l.faelligkeit[0]), 0.0)
            if abs(rest) > 0.5:
                hinweise.append("%s: fällig %02d/%d mit Restschuld %s € – Anschluss oder Rückzahlung nicht geplant (Fälligkeit → Art)."
                                % (l.name, l.faelligkeit[1], l.faelligkeit[0], _eur(-rest)))
        if l.zinsbindung_bis and l.anschluss_zins is None and l.zinsbindung_bis[0] <= end_year:
            hinweise.append("%s: Zinsbindung endet %02d/%d – Anschlusszins nicht gesetzt, Zinssatz läuft unverändert weiter."
                            % (l.name, l.zinsbindung_bis[1], l.zinsbindung_bis[0]))
    if jahre:
        worst = min(jahre, key=lambda j: j["cashflow_kumuliert"])
        if worst["cashflow_kumuliert"] < -0.5:
            hinweise.append("Kumulierter Cashflow bis %d negativ (%s €): Liquiditätsbedarf aus Eigenmitteln." % (worst["jahr"], _eur(worst["cashflow_kumuliert"])))
    return {"eingaben": o, "kennzahlen": kennzahlen, "jahre": jahre, "monate": monate, "hinweise": hinweise,
            "darlehen_namen": [l.name for l in loans], "start": _mk(*start)}


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
    out = {"miete": {}, "kosten": {}, "ruecklage": {}, "ausschuettung": {}, "wert": {}, "darlehen": {}}
    for r in res["monate"]:
        mk = r["monat"]
        out["miete"][mk] = r["miete"] + r["umlage"]
        out["kosten"][mk] = r["kosten"] - r["umlage"]
        out["ruecklage"][mk] = r["ruecklage"]
        out["wert"][mk] = r["wert"]
        for name, d in r["darlehen"].items():
            x = out["darlehen"].setdefault(name, {"zins": {}, "tilgung": {}, "saldo": {}})
            x["zins"][mk] = d["zins"]
            x["tilgung"][mk] = d["tilgung"] + d["sondertilgung"]
            x["saldo"][mk] = d["saldo"]
    # Ausschuettung: Jahresbetrag gleichmaessig auf die Monate des Jahres (vereinfachend)
    for j in res["jahre"]:
        n = j["monate"] or 12
        for r in res["monate"]:
            if int(r["monat"][:4]) == j["jahr"]:
                out["ausschuettung"][r["monat"]] = round(j["ausschuettung"] / n, 2)
    return out


# ---------------------------------------------------------------------------
# Excel-Export
# ---------------------------------------------------------------------------

def sheets(res: dict):
    from mm_xlsx import Sheet
    o, K, J = res["eingaben"], res["kennzahlen"], res["jahre"]
    inputs = [["Objekt", o.get("name")], ["Art", o.get("art")], ["Übergang", o.get("uebergang")], ["Kaufpreis", _f(o.get("kaufpreis"))],
              ["Nebenkosten (AfA-Basis)", K["nebenkosten"]], ["Gesamtinvestition", K["gesamtinvestition"]], ["Eigenkapital", K["eigenkapital"]],
              ["Gebäudeanteil %", _f(o.get("gebaeudeanteil_prozent"))], ["AfA-Satz %", K["afa_satz"]], ["AfA-Basis", K["afa_basis"]], ["AfA p.a.", K["afa_jahr"]],
              ["Nettokaltmiete/Monat", _f(o["miete"].get("nettokalt_monat"))], ["Umlage/Monat", _f(o["miete"].get("nebenkosten_monat"))],
              ["Leerstand %", _f(o["miete"].get("leerstand_prozent"))], ["Index", str(o["miete"]["index"])],
              ["Kosten nicht umlagefähig p.a.", _f(o["kosten"].get("nicht_umlagefaehig_pa"))], ["Rücklage p.a.", _f(o["kosten"].get("ruecklage_pa"))],
              ["Wertentwicklung % p.a.", _f(o.get("wertentwicklung_prozent"))], ["Ausschüttung % des Ergebnisses", _f(o.get("ausschuettung_prozent"))]]
    for l in o.get("darlehen") or []:
        inputs.append(["Darlehen " + str(l.get("name")), "%s € · %s %% · %s · Annuität %s · Tilgung %s · Sonder %s ab %s · Zinsbindung bis %s · Anschluss %s · Abrechnung %s" % (
            _f(l.get("betrag")), _f(l.get("zins_prozent")), l.get("art"), l.get("annuitaet_monat") or "", l.get("tilgung_monat") or "", l.get("sondertilgung_monat") or "",
            l.get("sondertilgung_ab") or "", l.get("zinsbindung_bis") or "", l.get("anschluss_zins_prozent") or "", l.get("abrechnung"))])
    for g in o.get("gesellschafter") or []:
        inputs.append(["Gesellschafter " + str(g.get("name")), "%s %% · Steuersatz %s %%" % (_f(g.get("anteil_prozent")), _f(g.get("steuersatz_prozent")))])
    kz = [[k, v] for k, v in K.items() if not isinstance(v, (list, dict))]
    names = res["darlehen_namen"]
    head = ["Jahr", "Monate", "Miete", "Umlage", "Kosten", "Rücklage", "Zinsen", "Tilgung", "Sondertilgung", "AfA", "sofort abziehbar", "Ergebnis", "Steuer", "Ergebnis n. St.",
            "Ausschüttung", "Cashflow", "Cashflow kum.", "Vermögensaufbau", "EK-Rendite", "Restschuld", "Objektwert", "EK im Objekt", "DSCR", "NKM/Monat", "VPI"]
    for n in names:
        head += [n + " Zins", n + " Tilgung", n + " Saldo"]
    rows = []
    for j in J:
        r = [j["jahr"], j["monate"], j["miete"], j["umlage"], j["kosten"], j["ruecklage"], j["zins"], j["tilgung"], j["sondertilgung"], j["afa"], j["sofort_abziehbar"], j["ergebnis"], j["steuer"],
             j["ergebnis_nach_steuern"], j["ausschuettung"], j["cashflow"], j["cashflow_kumuliert"], j["vermoegensaufbau"], j["ek_rendite"], j["restschuld"], j["wert"], j["eigenkapital_objekt"], j["dscr"], j["nkm_monat"], j["vpi"]]
        for n in names:
            d = j["darlehen"][n]
            r += [d["zins"], d["tilgung"], d["saldo"]]
        rows.append(r)
    mhead = ["Monat", "Miete", "Umlage", "Kosten", "Rücklage", "Zinsen", "Tilgung", "Sondertilgung", "AfA", "Restschuld", "Objektwert"]
    mrows = [[m["monat"], m["miete"], m["umlage"], m["kosten"], m["ruecklage"], m["zins"], m["tilgung"], m["sondertilgung"], m["afa"], m["restschuld"], m["wert"]] for m in res["monate"]]
    return [Sheet("Eingaben", ["Parameter", "Wert"], inputs, widths=[34, 80], freeze="A2"),
            Sheet("Kennzahlen", ["Kennzahl", "Wert"], kz, widths=[34, 20], freeze="A2"),
            Sheet("Jahre", head, rows, widths=[8] + [12] * (len(head) - 1), freeze="B2"),
            Sheet("Monate", mhead, mrows, widths=[10] + [12] * (len(mhead) - 1), freeze="B2")]
