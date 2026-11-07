"""Kernablaeufe, gemeinsam fuer Kommandozeile und Dienst: Daten holen, Konfiguration
pruefen, Lauf (Regeln anwenden, Buchungen schreiben, Berichte je Bereich bauen),
Einstellungspakete, Diagnoseprotokoll."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import platform
import re
import threading
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from mm_bridge import Bridge, MoneyMoneyError, MoneyMoneyLocked, MoneyMoneyNotPermitted, MoneyMoneyNotRunning, notify
from model import Account, Ledger, accounts_from_export, add_months, fmt_eur, month_key, tx_from_export, norm_cat
import realestate
import categorize
from report import ROLES, account_roles, build_dataset
from rules import Proposal, plan_all
from storage import Store
from tax import build_tax
from i18n import tr

log = logging.getLogger("kontor.core")
RUN_LOCK = threading.Lock()
HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CONFIG: Dict[str, Any] = {
    "probelauf": True,
    "mitteilungen": True,
    "zeitplan": {"intervall_minuten": 30, "automatisch": True},
    "darlehen": [], "beteiligungen": [], "saldo_spiegel": [],
    "bereiche": [],
    "immobilien": [],
    "kategorien": {"aktiv": True, "lernen": True, "mm_ueberschreiben": False},
    "bilanz": {"monate_zurueck": 0, "rollen": {}, "verlauf": {}, "illiquide_rollen": ["beteiligungen", "immobilien", "sachwerte"],
               "illiquide_konten": [], "inaktiv_monate": 12, "ausgeblendet": [], "immer_anzeigen": [], "ansicht": "positionen"},
    "kapitalfluss": {"beteiligungs_gruppen": [], "kategorie_zuordnung": {}, "kategorie_zu_konto": {},
                     "umbuchungs_kategorien": ["Umbuchung"], "umbuchung_paarung": True, "paarung_manuelle_konten": True},
    "steuer": {"vermietung_kategorie": "Vermietung", "objekt_darlehen": {}, "afa": {}, "positionen": {}, "entitaeten": []},
    "belege": {"ordner": "~/Documents/Kontor-Belege", "unterordner": "{jahr}", "kommentar_schreiben": False, "ordner_bestaetigt": False},
    "moneymoney": {"kategorisieren_erlauben": False},
    "abruf": {"online": [], "offline": []},      # eigene Festlegung: Konto wird von MoneyMoney abgerufen / nicht (sonst erkannt)
    "updates": {"repo": "stecrz/Kontor", "taeglich_pruefen": True},
    "oberflaeche": {"sperre_minuten": 15, "touchid": True, "port": 8765, "bind": "127.0.0.1", "tls_cert": "", "tls_key": ""},
}

# Felder mit Kontoreferenzen in Listen (fuer Pakete und Pruefung)
REF_FIELDS = [
    ("darlehen", "darlehenskonto"), ("darlehen", "quellkonten"),
    ("beteiligungen", "beteiligungskonto"), ("beteiligungen", "zielkonto"), ("beteiligungen", "gruppe"),
    ("saldo_spiegel", "zielkonto"), ("saldo_spiegel", "quellkonto"),
]


def merged_config(cfg: Optional[dict]) -> dict:
    out: Dict[str, Any] = {}
    cfg = cfg or {}
    for k, v in DEFAULT_CONFIG.items():
        if isinstance(v, dict):
            out[k] = copy.deepcopy(v)
            out[k].update(cfg.get(k) or {})
        else:
            out[k] = cfg.get(k, v)
    for k, v in cfg.items():
        if k not in out:
            out[k] = v
    for i, b in enumerate(out["bereiche"]):
        b.setdefault("id", "b%d" % (i + 1))
        b.setdefault("name", "Bereich %d" % (i + 1))
        b.setdefault("konten", [])
        b.setdefault("art", "")
        b.setdefault("aktiv", True)
    if out["bereiche"] and not any(b.get("haupt") for b in out["bereiche"]):
        out["bereiche"][0]["haupt"] = True
    for im in out.get("immobilien") or []:
        im.setdefault("kalkulationen", [])
        im.setdefault("dokumente", [])
        im.setdefault("darlehen_konten", {})
    return out


def version_on_disk() -> str:
    """Version laut Datei VERSION im Programmordner (aendert sich bei git pull / Update)."""
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0"


LOADED_VERSION = version_on_disk()      # Version des Codes, der in diesem Prozess tatsaechlich laeuft


def version() -> str:
    """Version des laufenden Codes (nicht der Datei -- die kann nach einem Update schon neuer sein)."""
    return LOADED_VERSION


# ---------------------------------------------------------------------------
# Daten holen
# ---------------------------------------------------------------------------

def earliest_needed(config: dict, today: date) -> date:
    back = int((config.get("bilanz", {}) or {}).get("monate_zurueck", 0) or 0)
    if back <= 0:
        return date(2000, 1, 1)
    y, m = add_months(today, -(back + 1))
    start = date(y, m, 1)
    for l in config.get("darlehen", []) or []:
        try:
            ab = date.fromisoformat(l["ab_datum"])
            start = min(start, date(ab.year - 1, 1, 1))
        except Exception:
            pass
    return start


def fetch(bridge: Bridge, config: dict, today: date, with_portfolio: bool = False, progress: Optional[Callable[[str], None]] = None) -> Ledger:
    """Konten, Umsaetze und ggf. Depotbestaende aus MoneyMoney lesen. progress(schritt) meldet den laufenden Schritt."""
    step = progress or (lambda _s: None)
    step("accounts")
    accounts = accounts_from_export(bridge.export_accounts())
    since = earliest_needed(config, today)
    step("transactions")
    raw = bridge.export_transactions(since)
    step("parse")
    txs = tx_from_export(raw)
    del raw
    ledger = Ledger(accounts, txs)
    ledger.portfolios = {}
    if with_portfolio:
        step("portfolios")
        for a in accounts.values():
            if a.portfolio and not a.group:
                try:
                    ledger.portfolios[a.uuid] = bridge.export_portfolio(a.uuid)
                except MoneyMoneyError as e:
                    log.info("Portfolio %s: no holdings data (%s)", a.uuid[:8], str(e)[:80])
    log.info("MoneyMoney: %d accounts, %d transactions since %s, %d portfolios", len(accounts), len(txs), since, len(ledger.portfolios))
    ledger.fp = fingerprint(ledger)          # Fingerabdruck des frischen Stands (vor Probelauf-Buchungen, die Salden veraendern)
    return ledger


def ledger_fp(ledger: Ledger) -> str:
    return getattr(ledger, "fp", None) or fingerprint(ledger)


def fingerprint(ledger: Ledger) -> str:
    """Inhalt des MoneyMoney-Stands: Konten (Name, Pfad, Typ, Saldo, Abrufzeit), Umsaetze (Betrag, Datum, Texte,
    Kategorie aus MoneyMoney, vorgemerkt) und Depotpositionen. Kontor-eigene Ueberlagerungen (Kategorien, Probelauf-
    Buchungen mit negativer Nummer) zaehlen nicht -- gleicher Fingerabdruck = gleiche Daten in MoneyMoney."""
    h = hashlib.sha256()
    for a in sorted(ledger.accounts.values(), key=lambda x: x.uuid):
        h.update(("%s|%s|%s|%s|%.2f|%s\n" % (a.uuid, a.path or a.name, a.type, a.portfolio, a.balance,
                                            a.refresh.isoformat() if a.refresh else "")).encode())
    rows = []
    for t in ledger.txs:
        if t.id < 0:
            continue
        mm = t.mm_category_path if t.mm_category_path is not None else t.category_path
        rows.append("%d|%s|%s|%.2f|%s|%s|%s|%s|%s|%d|%s" % (t.id, t.account_uuid, t.booking_date, t.amount, mm, t.name, t.purpose,
                                                           t.booking_text, t.counter_iban, t.booked, t.comment))
    h.update("\n".join(rows).encode())
    h.update(json.dumps(getattr(ledger, "portfolios", None) or {}, sort_keys=True, default=str).encode())
    return h.hexdigest()


def unavailable_text(e: Exception) -> Optional[str]:
    if isinstance(e, MoneyMoneyNotRunning):
        return tr("s_moneymoney_laeuft_nicht")
    if isinstance(e, MoneyMoneyLocked):
        return tr("s_moneymoney_ist_gesperrt_bitte_in")
    if isinstance(e, MoneyMoneyNotPermitted):
        return (tr("s_keine_berechtigung_moneymoney_zu_steue"))
    return None


# wie guessArt in der Oberflaeche
_FIRMA_RE = re.compile(r"\b(gmbh|ug|ag|se|kg|ohg|gbr|egbr|e\.?\s?k\.?|e\.?\s?v\.?|eg|ltd|inc|llc|holding|verwaltung|beteiligung|"
                       r"immobilien|stiftung|verein|genossenschaft|partner|&\s?co)\b|gmbh|gbr|holding|gesellschaft", re.I)


def _bereich_art(name: str) -> str:
    return "gesellschaft" if _FIRMA_RE.search(name or "") else "privat"


def bereiche_for(ledger: Ledger, config: dict) -> List[dict]:
    """Bereiche mit aufgeloesten Konten: konfiguriert, sonst alle Kontengruppen der obersten Ebene.
    Jeder Bereich: {"id", "name", "art", "anteil", "haupt", "konten" (Referenzen), "leaves" (Account), "gruppen"}."""
    anteile: Dict[str, float] = {}
    for b in config.get("beteiligungen") or []:
        try:
            anteile[ledger.resolve(b["gruppe"]).uuid] = float(b.get("anteil", 1.0))
        except (KeyError, ValueError, TypeError):
            pass
    out: List[dict] = []
    cfg = [b for b in (config.get("bereiche") or []) if isinstance(b, dict) and b.get("aktiv", True)]
    if cfg:
        for b in cfg:
            leaves: List[Account] = []
            gruppen: List[Account] = []
            seen = set()
            for ref in b.get("konten") or []:
                try:
                    a = ledger.resolve(ref)
                except KeyError:
                    continue
                members = ledger.descendants(a.uuid) if a.group else [a]
                if a.group:
                    gruppen.append(a)
                for x in members:
                    if x.uuid not in seen:
                        seen.add(x.uuid)
                        leaves.append(x)
            if not leaves and not b.get("konten"):
                continue
            first_group = gruppen[0] if gruppen else None
            anteil = b.get("anteil")
            if anteil in (None, "") and first_group is not None:
                anteil = anteile.get(first_group.uuid)
            out.append({"id": str(b.get("id")), "name": b.get("name") or (first_group.name if first_group else "Bereich"),
                        "art": b.get("art") or _bereich_art(b.get("name") or (first_group.name if first_group else "")),
                        "anteil": float(anteil) if anteil not in (None, "") else None, "haupt": bool(b.get("haupt")),
                        "konten": list(b.get("konten") or []), "leaves": leaves, "gruppen": gruppen})
    if not out:
        for g in ledger.roots():
            out.append({"id": g.uuid, "name": g.name, "art": _bereich_art(g.name), "anteil": anteile.get(g.uuid), "haupt": False,
                        "konten": ["%s | %s" % (g.uuid, g.name)], "leaves": ledger.descendants(g.uuid), "gruppen": [g]})
        if out and not any(b["haupt"] for b in out):
            (next((b for b in out if b["art"] == "privat"), None) or out[0])["haupt"] = True
        # Vorschlag: Hauptbereich zuerst, dann weitere private Bereiche, dann Gesellschaften
        out.sort(key=lambda b: (not b["haupt"], b["art"] != "privat"))
    if out and not any(b["haupt"] for b in out):
        out[0]["haupt"] = True
    # Explizite Kontenzuordnung (Einrichtung → Konten): Konto in genau diesem Bereich, unabhaengig von der Gruppe
    by_id = {b["id"]: b for b in out}
    for ref, z in ((config.get("bilanz") or {}).get("konten_zuordnung") or {}).items():
        if not isinstance(z, dict) or not z.get("bereich") or z["bereich"] not in by_id:
            continue
        try:
            a = ledger.resolve(ref)
        except KeyError:
            continue
        if a.group:
            continue
        for b in out:
            b["leaves"] = [x for x in b["leaves"] if x.uuid != a.uuid]
        by_id[z["bereich"]]["leaves"].append(a)
    return out


def abruf_arten(ledger: Ledger, config: dict) -> Dict[str, Dict[str, str]]:
    """uuid -> {"art": "online"|"offline", "grund": Text} fuer alle Konten (keine Gruppen). Online = MoneyMoney ruft bei
    Bank oder Dienst ab; offline = von Hand gefuehrt, kein Abruf (zaehlt nicht fuer den Datenstand). MoneyMoney setzt den
    Abrufzeitpunkt auch bei Offline-Konten (z. B. nach einer Buchung), deshalb mehrere Merkmale; eigene Festlegung geht vor."""
    import rules
    ab = config.get("abruf") or {}

    def refs(lst) -> set:
        out = set()
        for r in lst or []:
            try:
                out.add(ledger.resolve(r).uuid)
            except KeyError:
                pass
        return out
    force_on, force_off = refs(ab.get("online")), refs(ab.get("offline"))
    targets = set()
    for key, fields in (("darlehen", ("darlehenskonto",)), ("beteiligungen", ("zielkonto", "beteiligungskonto")), ("saldo_spiegel", ("zielkonto",))):
        for r in config.get(key) or []:
            if isinstance(r, dict):
                targets |= refs([r[f] for f in fields if r.get(f)])
    booked = {t.account_uuid for t in ledger.txs if t.purpose and "#mm-" in t.purpose and rules.TAG_RE.search(t.purpose)}
    out: Dict[str, Dict[str, str]] = {}
    for a in ledger.accounts.values():
        if a.group:
            continue
        refreshed = a.refresh is not None and a.refresh.year >= 2005
        if a.uuid in force_off:
            art, grund = "offline", tr("s_von_dir_als_ohne_abruf")
        elif a.uuid in force_on:
            art, grund = "online", tr("s_von_dir_als_abgerufen_festgelegt")
        elif a.portfolio:
            art, grund = ("online", tr("s_grund_depot")) if refreshed else ("offline", tr("s_depot_ohne_abruf"))
        elif a.offline:
            art, grund = "offline", tr("s_manuell_gefuehrt")
        elif a.uuid in targets:
            art, grund = "offline", tr("s_grund_zielkonto")
        elif a.uuid in booked:
            art, grund = "offline", tr("s_von_kontor_bebucht")
        elif "offline" in (a.type or "").lower():
            art, grund = "offline", tr("s_grund_offline_konto")
        elif not refreshed:
            art, grund = "offline", tr("s_noch_nie_abgerufen")
        elif not ((a.bank_code or "").strip() or (a.account_number or "").strip() or (a.iban or "").strip()):
            art, grund = "offline", tr("s_ohne_bankleitzahl_und_kontonummer")
        else:
            art, grund = "online", tr("s_grund_bank" if (a.bank_code or "").strip() else "s_grund_dienst")
        out[a.uuid] = {"art": art, "grund": grund}
    return out


def freeze_assignments(ledger: Ledger, config: dict) -> Optional[dict]:
    """Bestaetigte Konten ohne feste Position/Verlaufsquelle (aeltere Einrichtung mit "auto") auf den heute erkannten Wert
    festlegen, damit spaetere Aenderungen an Name, Typ oder Gruppe in MoneyMoney die Zuordnung nicht verschieben.
    Liefert die geaenderte Konfiguration oder None, wenn nichts zu tun ist. Unbestaetigte (neue) Konten bleiben Vorschlag."""
    bil = config.get("bilanz") or {}
    zu = bil.get("konten_zuordnung") or {}
    if not zu:
        return None
    roles = account_roles(ledger, config)
    ver_cfg = {}
    for ref in (bil.get("verlauf") or {}):
        try:
            ver_cfg[ledger.resolve(ref).uuid] = ref
        except KeyError:
            pass
    new = copy.deepcopy(config)
    nb = new.setdefault("bilanz", {})
    nzu, nver = nb.setdefault("konten_zuordnung", {}), nb.setdefault("verlauf", {})
    changed = 0
    for ref, z in zu.items():
        if not isinstance(z, dict) or not z.get("bestaetigt", True):
            continue
        try:
            a = ledger.resolve(ref)
        except KeyError:
            continue
        if a.group:
            continue
        if z.get("position") not in ROLES and roles.get(a.uuid) in ROLES:
            nzu[ref] = dict(z, position=roles[a.uuid])
            changed += 1
        if a.uuid not in ver_cfg:
            nver[ref] = "stand" if a.portfolio else "umsaetze"
            changed += 1
    return new if changed else None


def konten_neu(ledger: Ledger, config: dict, bereiche: List[dict], roles: Dict[str, str]) -> List[dict]:
    """Konten ohne bestaetigte Zuordnung (neu in MoneyMoney oder noch nie bestaetigt) mit Vorschlag."""
    zu = (config.get("bilanz") or {}).get("konten_zuordnung") or {}
    confirmed = set()
    for ref in zu:
        try:
            confirmed.add(ledger.resolve(ref).uuid)
        except KeyError:
            pass
    bereich_of = {a.uuid: b for b in bereiche for a in b["leaves"]}
    out = []
    for a in ledger.accounts.values():           # Reihenfolge wie in MoneyMoney
        if a.group or a.uuid in confirmed or not a.path:
            continue
        b = bereich_of.get(a.uuid)
        out.append({"uuid": a.uuid, "name": a.name, "pfad": a.path, "typ": a.type, "saldo": a.balance,
                    "bereich": b["id"] if b else None, "bereich_name": b["name"] if b else None, "position": roles.get(a.uuid, "sonstiges")})
    return out


def main_bereich(bereiche: List[dict]) -> Optional[dict]:
    return next((b for b in bereiche if b.get("haupt")), bereiche[0] if bereiche else None)


# ---------------------------------------------------------------------------
# Konfiguration pruefen
# ---------------------------------------------------------------------------

def check_config(ledger: Ledger, categories: List[dict], config: dict) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    cat_names = {str(c.get("name") or "") for c in categories}
    cat_names |= {str(c.get("path") or "").split("\\")[-1] for c in categories}

    def add(level, text):
        out.append({"stufe": level, "text": text})

    def ref(label, r, want_offline=False, group_ok=True, want_group=False):
        try:
            a = ledger.resolve(r)
        except KeyError as e:
            add("fehler", "%s: %s" % (label, e)); return None
        if want_offline and not a.offline:
            add("fehler", tr("s_s_s_hat_eine_bankanbindung") % (label, a.path))
        elif not group_ok and a.group:
            add("fehler", tr("s_s_s_ist_eine_gruppe") % (label, a.path))
        elif want_group and not a.group:
            add("fehler", tr("s_s_s_ist_keine_gruppe") % (label, a.path))
        else:
            add("ok", "%s → %s" % (label, a.path))
        return a

    def cat(label, name):
        if name and categories and name not in cat_names and name.split("\\")[-1] not in cat_names:
            add("warnung", tr("s_s_kategorie_s_existiert_nicht") % (label, name))

    for l in config.get("darlehen", []) or []:
        n = l.get("name", "?") + ("" if l.get("aktiv", True) else " (inaktiv)")
        ref(tr("s_darlehen_s_konto") % n, l.get("darlehenskonto", ""), want_offline=True, group_ok=False)
        for s_ in l.get("quellkonten", []) or []:
            ref("Darlehen %s: Quelle" % n, s_, group_ok=False)
        b = l.get("buchung", {}) or {}
        cat("Darlehen %s" % n, b.get("kategorie_tilgung"))
        cat("Darlehen %s" % n, b.get("kategorie_zins"))
        erk = l.get("erkennung") or {}
        iban = (erk.get("gegen_iban") or "").replace(" ", "")
        if not iban and not erk.get("text_enthaelt"):
            add("fehler", tr("s_darlehen_s_erkennung_braucht_gegen") % n)
        if iban and not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", iban):
            add("fehler", tr("s_darlehen_s_s_ist_keine") % (n, iban))
        try:
            date.fromisoformat(l.get("ab_datum", ""))
        except ValueError:
            add("fehler", tr("s_darlehen_s_ab_datum_fehlt") % n)
    for b in (config.get("beteiligungen", []) or []) + (config.get("saldo_spiegel", []) or []):
        n = b.get("name", "?") + ("" if b.get("aktiv", True) else " (inaktiv)")
        ref(tr("s_chk_wert_ziel") % n, b.get("zielkonto") or b.get("beteiligungskonto", ""), want_offline=True, group_ok=False)
        ref(tr("s_chk_wert_quelle") % n, b.get("gruppe") or b.get("quellkonto", ""), want_group=bool(b.get("gruppe")))
    bil = config.get("bilanz", {}) or {}
    for b in config.get("bereiche") or []:
        if not isinstance(b, dict):
            continue
        if not b.get("konten"):
            add("fehler", tr("s_bereich_s_hat_keine_konten") % b.get("name"))
        for r in b.get("konten") or []:
            ref("Bereich %s" % b.get("name"), r)
    bereiche = bereiche_for(ledger, config)
    seen_leaf: Dict[str, str] = {}
    roles = account_roles(ledger, config)
    for b in bereiche:
        for a in b["leaves"]:
            if a.uuid in seen_leaf and seen_leaf[a.uuid] != b["name"]:
                add("warnung", tr("s_konto_s_liegt_in_mehreren") % (a.path, seen_leaf[a.uuid], b["name"]))
            seen_leaf[a.uuid] = b["name"]
        missing = [a.path for a in b["leaves"] if roles.get(a.uuid) == "sonstiges"]
        if missing:
            add("warnung", tr("s_s_konten_ohne_position_umsaetze")
                % (b["name"], "; ".join(missing[:8]) + (" …" if len(missing) > 8 else "")))
    for r in bil.get("illiquide_konten") or []:
        ref(tr("s_chk_bilanz_illiquide"), r)
    for k, v in (bil.get("rollen") or {}).items():
        if not k.startswith("_"):
            ref(tr("s_position_fuer"), k)
            if v not in ROLES:
                add("fehler", tr("s_unbekannte_position_s_fuer_s") % (v, k))
    for k, v in (bil.get("verlauf") or {}).items():
        ref(tr("s_verlauf_fuer"), k, group_ok=False)
        if v not in ("umsaetze", "stand"):
            add("fehler", tr("s_unbekannte_verlaufsquelle_s_fuer_s") % (v, k))
    for k in (bil.get("ausgeblendet") or []) + (bil.get("immer_anzeigen") or []):
        ref(tr("s_chk_bilanz_anzeige"), k)
    for im in config.get("immobilien") or []:
        n = im.get("name") or "?"
        if im.get("objekt_konto"):
            ref("Immobilie %s: Objektkonto" % n, im["objekt_konto"], group_ok=False)
        for ln, r in (im.get("darlehen_konten") or {}).items():
            if r:
                ref("Immobilie %s: Darlehen %s" % (n, ln), r, group_ok=False)
        if im.get("bereich") and not any(b["id"] == im["bereich"] for b in bereiche):
            add("warnung", tr("s_immobilie_s_bereich_s_existiert") % (n, im["bereich"]))
        if im.get("kategorie"):
            cat("Immobilie %s" % n, str(im["kategorie"]).split("\\")[-1])
    kfc = config.get("kapitalfluss", {}) or {}
    for g in kfc.get("beteiligungs_gruppen", []) or []:
        ref(tr("s_chk_kf_beteiligungsgruppe"), g, want_group=True)
    for k, v in (kfc.get("kategorie_zuordnung") or {}).items():
        if k.startswith("_"):
            continue
        cat(tr("s_chk_kf_zuordnung"), k)
        if str(v).split("/")[0] not in ("Einnahmen", "Ausgaben", "Investitionen", "Finanzierung"):
            add("fehler", tr("s_kapitalfluss_zuordnung_s_s_unbekannt") % (k, v))
    for k, v in (kfc.get("kategorie_zu_konto") or {}).items():
        if not k.startswith("_"):
            cat(tr("s_chk_kf_depotzuordnung"), k)
            ref(tr("s_kapitalfluss_depot_fuer_s") % k, v, group_ok=False)
    st = config.get("steuer", {}) or {}
    for k, v in (st.get("objekt_darlehen") or {}).items():
        ref(tr("s_steuer_darlehen_fuer_objekt_s") % v, k)
    bel = config.get("belege", {}) or {}
    folder = os.path.expanduser(bel.get("ordner") or DEFAULT_CONFIG["belege"]["ordner"])
    if os.path.isdir(folder) and not os.access(folder, os.W_OK):
        add("fehler", tr("s_belegordner_nicht_beschreibbar_s") % folder)
    for h in ledger.hints:
        add("hinweis", h)
    return out


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def apply_proposals(bridge: Bridge, ledger: Ledger, proposals: List[Proposal]) -> int:
    done = 0
    for pr in proposals:
        acc = ledger.accounts[pr.account_uuid]
        if pr.kind == "quelle":
            bridge.set_transaction(pr.source_tx_id, category=pr.set_category, comment=pr.set_comment)
        else:
            if not acc.offline:
                raise MoneyMoneyError(tr("s_verweigert_s_ist_kein_manuell") % acc.path)
            bridge.add_transaction(acc.uuid, pr.booking_date, pr.payee, pr.amount, pr.purpose,
                                   pr.category or None, fallback_refs=[acc.name])
        done += 1
        log.info("%s %s", "BOOKED" if not bridge.dry_run else "DRY RUN", pr.describe())
    return done


def budgets_from_categories(categories: List[dict]) -> Dict[str, float]:
    """Kategorie-Budgets aus MoneyMoney als Monatsbetrag je Pfad ('A / B')."""
    out: Dict[str, float] = {}
    for c in categories or []:
        b = c.get("budget")
        if not isinstance(b, dict) or not b.get("amount"):
            continue
        try:
            amt = float(b.get("amount") or 0.0)
        except (TypeError, ValueError):
            continue
        period = str(b.get("period") or "monthly").lower()
        monthly = amt / 12 if period.startswith("year") else amt / 3 if period.startswith("quart") else amt
        path = str(c.get("path") or c.get("name") or "").replace("\\", " / ")
        if path and monthly:
            out[path] = round(monthly, 2)
    return out


def compact_transactions(ledger: Ledger, bereiche: List[dict], store: Optional[Store] = None) -> List[dict]:
    """Umsatzliste fuer Belege und Suche (ohne Gegen-IBAN)."""
    ent_of: Dict[str, str] = {}
    for b in bereiche:
        for a in b["leaves"]:
            ent_of.setdefault(a.uuid, b["id"])
    out = []
    kat = categorize.load(store) if store is not None else categorize.empty()
    for t in ledger.txs:
        if t.account_uuid not in ent_of:
            continue
        path, q = categorize.effective(kat, t)
        out.append({"id": t.id, "konto": t.account_uuid, "konto_name": ledger.accounts[t.account_uuid].name, "entitaet": ent_of[t.account_uuid],
                    "datum": t.booking_date.isoformat(), "betrag": t.amount, "name": t.name[:80], "zweck": t.purpose[:140],
                    "kategorie": path, "quelle": q, "gebucht": t.booked, "haken": t.checkmark})
    out.sort(key=lambda x: (x["datum"], x["id"]), reverse=True)
    return out


def portfolio_summary(ledger: Ledger, bereiche: List[dict]) -> List[dict]:
    out = []
    ent_of = {a.uuid: b["name"] for b in bereiche for a in b["leaves"]}
    for uuid, rows in (getattr(ledger, "portfolios", {}) or {}).items():
        acc = ledger.accounts.get(uuid)
        if acc is None:
            continue
        pos = []
        for p in rows:
            try:
                pos.append({"name": str(p.get("name") or ""), "isin": str(p.get("isin") or ""), "menge": float(p.get("quantity") or 0),
                            "kurs": float(p.get("marketPrice") or p.get("price") or 0), "wert": float(p.get("marketValue") or p.get("amount") or 0),
                            "einstand": float(p.get("purchaseValue") or 0), "waehrung": str(p.get("currency") or acc.currency),
                            "klasse": str(p.get("assetClass") or "")})
            except (TypeError, ValueError, AttributeError):
                continue
        pos.sort(key=lambda x: -x["wert"])
        out.append({"konto": uuid, "name": acc.name, "entitaet": ent_of.get(uuid, ""), "summe": round(sum(p["wert"] for p in pos), 2),
                    "einstand": round(sum(p["einstand"] for p in pos), 2), "positionen": pos})
    return out


# ---------------------------------------------------------------------------
# Immobilien
# ---------------------------------------------------------------------------

def immo_active(im: dict) -> Optional[dict]:
    kalks = im.get("kalkulationen") or []
    if not kalks:
        return None
    return next((k for k in kalks if k.get("aktiv")), kalks[0])


def immo_results(config: dict, today: date) -> Dict[str, dict]:
    """id -> Ergebnis der aktiven Kalkulation je Immobilie (fuer Datensatz und Planung)."""
    out: Dict[str, dict] = {}
    for im in config.get("immobilien") or []:
        k = immo_active(im)
        if not k:
            continue
        try:
            res = realestate.berechne(k.get("eingaben") or {}, today)
        except Exception as e:  # pragma: no cover - fehlerhafte Eingaben duerfen den Bericht nicht stoppen
            log.warning("Property %s: calculation failed: %s", im.get("name"), e)
            out[str(im.get("id"))] = {"fehler": str(e)}
            continue
        out[str(im.get("id"))] = {"kalkulation": k.get("id"), "name": k.get("name"), "kennzahlen": res["kennzahlen"], "jahre": res["jahre"],
                                  "hinweise": res["hinweise"], "darlehen_namen": res["darlehen_namen"], "start": res["start"],
                                  "reihen": realestate.planreihen(res)}
    return out


def immo_afa_map(config: dict, results: Dict[str, dict]) -> Dict[str, Dict[str, float]]:
    """Objektname (letzter Teil der Vermietungskategorie bzw. Name) -> {Jahr: AfA} aus den aktiven Kalkulationen."""
    out: Dict[str, Dict[str, float]] = {}
    for im in config.get("immobilien") or []:
        r = results.get(str(im.get("id")))
        if not r or "fehler" in r:
            continue
        obj = (norm_cat(im.get("kategorie") or "").split(" / ")[-1] if im.get("kategorie") else "") or str(im.get("name") or "")
        out[obj] = {str(j["jahr"]): j["afa"] for j in r["jahre"]}
    return out


def immo_for_plan(config: dict, bereich_id: str, results: Dict[str, dict]) -> List[dict]:
    """Kalkulationen eines Bereichs, die in die Planung uebernommen werden sollen."""
    out = []
    for im in config.get("immobilien") or []:
        if str(im.get("bereich") or "") != str(bereich_id) or not im.get("in_planung"):
            continue
        r = results.get(str(im.get("id")))
        if not r or "fehler" in r:
            continue
        out.append({"name": im.get("name"), "kategorie": im.get("kategorie") or "", "objekt_konto": im.get("objekt_konto"),
                    "darlehen_konten": im.get("darlehen_konten") or {}, "reihen": r["reihen"]})
    return out


def immo_soll_ist(ledger: Ledger, config: dict, im: dict, res: dict, roles: Dict[str, str], today: date) -> List[dict]:
    """Jahresvergleich Kalkulation (Soll) gegen MoneyMoney (Ist): Miete, Kosten, Zinsen, Restschuld."""
    cat = norm_cat(im.get("kategorie") or "").lower()
    loans: Dict[str, str] = {}
    for ln, ref in (im.get("darlehen_konten") or {}).items():
        try:
            loans[ln] = ledger.resolve(ref).uuid
        except KeyError:
            pass
    years = sorted({j["jahr"] for j in res.get("jahre", [])} & {t.booking_date.year for t in ledger.txs})
    out = []
    cost_words = [w.lower() for w in COST_WORDS_DEFAULT]
    for y in years:
        soll = next(j for j in res["jahre"] if j["jahr"] == y)
        miete = kosten = 0.0
        if cat:
            for t in ledger.txs:
                if not t.booked or t.booking_date.year != y:
                    continue
                cl = norm_cat(t.category_path).lower()
                if cl == cat or cl.startswith(cat + " / "):
                    if t.amount > 0:
                        miete += t.amount
                    else:
                        kosten += t.amount
        zins = 0.0
        rest = 0.0
        for ln, u in loans.items():
            for t in ledger.transactions(u):
                if t.booking_date.year == y and any(w in t.text.lower() for w in cost_words):
                    zins += t.amount
            rest += ledger.balance_at(u, date(y, 12, 31)) if y < today.year else ledger.accounts[u].balance
        out.append({"jahr": y, "miete_soll": soll["miete"], "miete_ist": round(miete, 2), "kosten_soll": soll["kosten"] + soll["ruecklage"],
                    "kosten_ist": round(kosten, 2), "zins_soll": soll["zins"], "zins_ist": round(zins, 2),
                    "restschuld_soll": soll["restschuld"], "restschuld_ist": round(rest, 2) if loans else None})
    return out


COST_WORDS_DEFAULT = ["zins", "interest", "gebühr", "gebuehr", "entgelt", "provision", "bereitstellung", "#mm-zins"]


def _kat_sig(store: Store, config: dict, categories: Optional[List[dict]]) -> tuple:
    return (store.stamp(categorize.FILE), json.dumps(config.get("kategorien") or {}, sort_keys=True), len(categories or []))


def prepare_categories(store: Store, ledger: Ledger, config: dict, categories: Optional[List[dict]],
                       progress: Optional[Callable[[float, str], None]] = None) -> dict:
    """Kontor-Kategorien: MoneyMoney-Baum als Vorschlag uebernehmen, Regeln lernen, Luecken fuellen, auf den Ledger legen.
    Unveraendert seit dem letzten Mal (gleicher MoneyMoney-Stand, gleiche Kategorien-Datei)? Dann nichts tun."""
    cached = getattr(ledger, "_kat_cache", None)
    if cached and cached[0] == _kat_sig(store, config, categories):
        return cached[1]
    kat = _prepare_categories(store, ledger, config, categories, progress or (lambda f, t: None))
    ledger._kat_cache = (_kat_sig(store, config, categories), kat)
    return kat


def _prepare_categories(store: Store, ledger: Ledger, config: dict, categories: Optional[List[dict]],
                        step: Callable[[float, str], None]) -> dict:
    kc = config.get("kategorien") or {}
    kat = categorize.load(store)
    if not kc.get("aktiv", True):
        categorize.apply_to_ledger(categorize.empty(), ledger)
        return kat
    changed = False
    if categories and (not kat.get("mm_uebernommen") or len(kat["baum"]) < len(categories)):
        if categorize.seed_from_moneymoney(kat, categories):
            changed = True
    if kc.get("lernen", True):
        before = len(kat["regeln"])
        categorize.learn(kat, ledger, progress=lambda f: step(0.6 * f, "Kategorien: Regeln lernen"))
        changed = changed or len(kat["regeln"]) != before or not kat.get("gelernt_am")
    if categorize.auto_assign(kat, ledger, overwrite_mm=bool(kc.get("mm_ueberschreiben")),
                                 progress=lambda f: step(0.6 + 0.3 * f, tr("s_kategorien_umsaetze_zuordnen"))):
        changed = True
    step(0.9, tr("s_kategorien_uebernehmen"))
    if changed:
        categorize.save(store, kat)
    categorize.apply_to_ledger(kat, ledger)
    return kat


MM_HISTORY_FILE = "mm-history.json"


def record_snapshot(snaps: dict, accounts, today: date) -> bool:
    """Staende fuers Monatsende merken. Depots unter dem Monat ihres letzten Abrufs in MoneyMoney (nicht dem Monat, in dem
    Kontor liest: ein Abruf am 31. landet im richtigen Monat, auch wenn Kontor erst am 2. liest), uebrige Konten unter dem
    laufenden Monat. Liefert True, wenn sich etwas geaendert hat."""
    changed = False
    cur = month_key(today)
    for a in accounts:
        if a.group:
            continue
        mk = cur
        if a.portfolio and a.refresh is not None and a.refresh.year >= 2005 and a.refresh.date() <= today:
            mk = month_key(a.refresh.date())
        row = snaps.setdefault(mk, {})
        if row.get(a.uuid) != a.balance:
            row[a.uuid] = a.balance
            changed = True
    if len(snaps) > 600:
        for k in sorted(snaps)[:-600]:
            snaps.pop(k, None)
    return changed


def merge_snapshots(state: dict, snaps: dict) -> None:
    cur = state.setdefault("snapshots", {})
    for mk, row in (snaps or {}).items():
        cur.setdefault(mk, {}).update(row)


def build_report(store: Store, ledger: Ledger, config: dict, state: dict, today: date, warnings: List[str],
                 categories: Optional[List[dict]] = None, progress: Optional[Callable[[float, str], None]] = None) -> dict:
    # Fortschritt grob nach Laufzeit eines Laufs ohne Zwischenergebnisse gewichtet: Kategorien 5-25 %, Bereiche 25-75 % (nach
    # Umsatzzahl), Steuer bis 85 %, Kategorienstatistik und Umsatzliste bis 95 %, Speichern
    step = progress or (lambda f, t: None)
    step(0.05, "Kategorien")
    kat = prepare_categories(store, ledger, config, categories, lambda f, t: step(0.05 + 0.2 * f, t))
    record_snapshot(state.setdefault("snapshots", {}), ledger.accounts.values(), today)
    # aus MoneyMoney uebernommene Kontostand-Verlaeufe (verschluesselt abgelegt, nur im Speicher in den Zustand gelegt)
    state["historie_mm"] = (store.load_shared(MM_HISTORY_FILE, {}) or {}).get("konten") or {}
    bereiche = bereiche_for(ledger, config)
    haupt = main_bereich(bereiche)
    roles = account_roles(ledger, config)
    budgets = budgets_from_categories(categories or [])
    immo_res = immo_results(config, today)
    log.debug("Report: %d areas (%s), main %s, %d accounts with position, %d property calculations, %d budgets",
              len(bereiche), ", ".join(b["name"] for b in bereiche), haupt["name"] if haupt else "-", len(roles), len(immo_res), len(budgets))
    ledger._kat_sig = repr(getattr(ledger, "_kat_cache", (None,))[0])      # fuer Zwischenergebnisse in build_dataset
    datasets: Dict[str, dict] = {}
    weights = [1 + sum(len(ledger.transactions(a.uuid)) for a in b["leaves"]) for b in bereiche]
    total_w, done_w = float(sum(weights) or 1), 0.0
    for i, b in enumerate(bereiche):
        lo, hi = 0.25 + 0.5 * done_w / total_w, 0.25 + 0.5 * (done_w + weights[i]) / total_w
        done_w += weights[i]
        step(lo, "Bereich %s" % b["name"])
        sub = (lambda f, t, lo=lo, hi=hi, name=b["name"]: step(lo + (hi - lo) * f, "Bereich %s: %s" % (name, t)))
        try:
            ds = build_dataset(ledger, config, state, today, b, roles, warnings if (haupt and b["id"] == haupt["id"]) else [], sub)
            ds["budgets"] = budgets
            datasets[b["id"]] = ds
        except Exception as e:
            log.exception("Area %s: report failed", b["name"])
            datasets[b["id"]] = {"fehler": str(e), "wurzel": b["name"]}
    neu = konten_neu(ledger, config, bereiche, roles)
    if neu:
        warnings.append(tr("s_s_ohne_bestaetigte_zuordnung_einrichtu")
                        % (tr("s_ein_konto") if len(neu) == 1 else tr("s_d_konten") % len(neu), ", ".join(k["name"] for k in neu[:5]) + (" …" if len(neu) > 5 else "")))
    immobilien = []
    for im in config.get("immobilien") or []:
        r = immo_res.get(str(im.get("id")))
        entry = {"id": im.get("id"), "name": im.get("name"), "bereich": im.get("bereich"), "in_planung": bool(im.get("in_planung")),
                 "kategorie": im.get("kategorie"), "objekt_konto": im.get("objekt_konto"), "darlehen_konten": im.get("darlehen_konten") or {},
                 "kalkulationen": [{"id": k.get("id"), "name": k.get("name"), "aktiv": bool(k.get("aktiv")), "erstellt": k.get("erstellt")} for k in im.get("kalkulationen") or []],
                 "dokumente": im.get("dokumente") or [], "notizen": im.get("notizen") or ""}
        if r and "fehler" not in r:
            entry.update({"kennzahlen": r["kennzahlen"], "jahre": r["jahre"], "hinweise": r["hinweise"], "darlehen_namen": r["darlehen_namen"], "start": r["start"]})
            try:
                entry["soll_ist"] = immo_soll_ist(ledger, config, im, r, roles, today)
            except Exception as e:  # pragma: no cover
                entry["soll_ist"] = []
                log.warning("Plan vs. actual %s: %s", im.get("name"), e)
        elif r:
            entry["fehler"] = r["fehler"]
        immobilien.append(entry)
    for bid, ds in datasets.items():
        if "fehler" not in ds:
            log.debug("Area %s: %d months (%s to %s), %d accounts, %d inactive, %d warning(s)", ds.get("bereich", {}).get("name", bid),
                      len(ds["monate"]), ds["monate"][0] if ds["monate"] else "-", ds["monate"][-1] if ds["monate"] else "-",
                      sum(1 for r in ds["bilanz"]["zeilen"] if not r["gruppe"]), len(ds.get("konten_inaktiv") or []), len(ds.get("warnungen") or []))
    dataset = {
        "erstellt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "heute": today.isoformat(),
        "haupt": haupt["id"] if haupt else None,
        "bereiche": datasets,
        "bereich_namen": {b["id"]: b["name"] for b in bereiche},
        "bereich_info": {b["id"]: {"name": b["name"], "art": b["art"], "anteil": b["anteil"], "haupt": b["haupt"], "konten": b["konten"],
                                   "gruppen": [g.name for g in b["gruppen"]], "anzahl_konten": len(b["leaves"])} for b in bereiche},
        "konten": account_tree(ledger, config, roles, datasets),
        "steuer": (step(0.76, "Steuer"), _cached(ledger, "_tax_cache", (ledger._kat_sig, today.isoformat(), _bereiche_sig(bereiche),
                                                   json.dumps([config.get(k) for k in ("steuer", "kapitalfluss", "beteiligungen", "bereiche", "immobilien")]
                                                              + [(config.get("bilanz") or {}).get(k) for k in ("rollen", "konten_zuordnung")], sort_keys=True, default=str)),
                          lambda: build_tax(ledger, config, today, bereiche, roles, immo_afa_map(config, immo_res))))[1],
        "depots": portfolio_summary(ledger, bereiche),
        "immobilien": immobilien,
        "budgets": budgets,
        "warnungen": warnings,
        "kategorien": (step(0.86, "Kategorienstatistik"), _cached(ledger, "_katstats_cache", ledger._kat_sig, lambda: categorize.stats(kat, ledger)))[1],
        "konten_neu": neu,
    }
    step(0.88, "Speichern")
    store.save("dataset.json", dataset)
    sig = (ledger._kat_sig, _bereiche_sig(bereiche))
    cached = getattr(ledger, "_ums_cache", None)
    if cached and cached[0] == sig and store.exists("transactions.json"):
        ums = cached[1]                # Umsatzliste unveraendert (z. B. nur Verlauf geaendert) -> nicht neu schreiben
    else:
        step(0.93, "Umsatzliste")
        ums = compact_transactions(ledger, bereiche, store)
        store.save("transactions.json", ums)
        ledger._ums_cache = (sig, ums)
    dataset["_umsaetze"] = ums        # fuer den Dienst: Liste im Speicher behalten (teilt die Strings mit dem Ledger), nicht Teil der Datei
    return dataset


def _bereiche_sig(bereiche: List[dict]) -> tuple:
    return tuple((b["id"], tuple(a.uuid for a in b["leaves"])) for b in bereiche)


def _cached(ledger: Ledger, attr: str, key, fn):
    """Ergebnis am Ledger zwischenspeichern (gleicher MoneyMoney-Stand + gleiche Eingaben -> gleiches Ergebnis)."""
    hit = getattr(ledger, attr, None)
    if hit and hit[0] == key:
        return copy.deepcopy(hit[1])
    val = fn()
    setattr(ledger, attr, (key, copy.deepcopy(val)))
    return val


def account_tree(ledger: Ledger, config: dict, roles: Optional[Dict[str, str]] = None, datasets: Optional[Dict[str, dict]] = None) -> List[dict]:
    roles = roles if roles is not None else account_roles(ledger, config)
    inactive: set = set()
    inactive_auto: set = set()
    limits: Dict[str, int] = {}
    verlauf: Dict[str, str] = {}
    bereich_of: Dict[str, str] = {}
    bereich_id: Dict[str, str] = {}
    for bid, ds in (datasets or {}).items():
        inactive.update(ds.get("konten_inaktiv") or [])
        inactive_auto.update(ds.get("konten_inaktiv_auto") or [])
        limits.update(ds.get("konten_aktivitaet") or {})
        bname = (ds.get("bereich") or {}).get("name") or ""
        for r in ((ds.get("bilanz") or {}).get("zeilen") or []) + ((ds.get("bilanz") or {}).get("ausserhalb") or []):
            if not r.get("gruppe") and r.get("verlauf"):
                verlauf[r["id"]] = r["verlauf"]
            if not r.get("gruppe") and bname:
                bereich_of[r["id"]] = (bereich_of[r["id"]] + ", " + bname) if r["id"] in bereich_of else bname
                bereich_id.setdefault(r["id"], bid)
    zu = (config.get("bilanz") or {}).get("konten_zuordnung") or {}
    confirmed = set()
    for ref in zu:
        try:
            confirmed.add(ledger.resolve(ref).uuid)
        except KeyError:
            pass
    n_inakt = int((config.get("bilanz") or {}).get("inaktiv_monate", 12) or 12)
    y, m = add_months(date.today(), -n_inakt)
    cutoff = date(y, m, 1)
    last_tx: Dict[str, date] = {}
    for t in ledger.txs:
        if t.booked and (t.account_uuid not in last_tx or t.booking_date > last_tx[t.account_uuid]):
            last_tx[t.account_uuid] = t.booking_date
    out = []
    kinds = abruf_arten(ledger, config)
    plain = copy.deepcopy(config)                # Vorschlag ohne eigene Zuordnungen (was Kontor heute erkennen wuerde)
    plain.setdefault("bilanz", {})["rollen"] = {}
    plain["bilanz"]["konten_zuordnung"] = {r: dict(z, position="") for r, z in (plain["bilanz"].get("konten_zuordnung") or {}).items() if isinstance(z, dict)}
    suggested = account_roles(ledger, plain)
    for a in ledger.accounts.values():           # Reihenfolge wie in MoneyMoney
        if not a.path:
            continue
        out.append({"uuid": a.uuid, "name": a.name, "pfad": a.path, "ebene": a.path.count(" / "), "gruppe": a.group,
                    "depot": a.portfolio, "manuell": a.offline, "rolle": roles.get(a.uuid, "") if not a.group else "",
                    "saldo": None if a.group else a.balance, "waehrung": a.currency, "typ": a.type, "inaktiv": a.uuid in inactive, "inaktiv_auto": a.uuid in inactive_auto, "aktiv_grenze": limits.get(a.uuid, 0),
                    "rolle_vorschlag": suggested.get(a.uuid, "") if not a.group else "", "abruf": kinds.get(a.uuid, {}).get("art") if not a.group else None,
                    "verlauf": verlauf.get(a.uuid) or ("stand" if a.portfolio else "umsaetze"), "bereich": bereich_of.get(a.uuid, ""),
                    "bereich_id": bereich_id.get(a.uuid, ""), "bestaetigt": a.uuid in confirmed,
                    "aktualisiert": a.refresh.strftime("%Y-%m-%d %H:%M") if a.refresh else None,
                    "letzte_buchung": last_tx[a.uuid].isoformat() if a.uuid in last_tx else None,
                    # Saldo, aber weder Buchung noch Aktualisierung seit N Monaten: Stand vermutlich veraltet (Konto aufgeloest?)
                    "veraltet": (not a.group and (a.portfolio or not a.offline) and abs(a.balance) > 0.005 and (a.uuid not in last_tx or last_tx[a.uuid] < cutoff)
                                 and (a.refresh is None or a.refresh.date() < cutoff))})
    return out


def run_once(store: Store, config: dict, today: date, dry: bool, force: bool,
             bridge_factory: Callable[[bool], Bridge] = Bridge, with_report: bool = True,
             categories: Optional[List[dict]] = None) -> dict:
    if not RUN_LOCK.acquire(blocking=False):
        return {"status": "laeuft_bereits", "text": tr("s_ein_abgleich_laeuft_bereits")}
    try:
        state = store.load("state.json", {}) or {}
        bridge = bridge_factory(dry)
        try:
            ledger = fetch(bridge, config, today, with_portfolio=with_report)
            if categories is None:
                try:
                    categories = bridge.export_categories()
                except MoneyMoneyError:
                    categories = state.get("kategorien_roh") or []
        except MoneyMoneyError as e:
            txt = unavailable_text(e)
            if txt:
                log.info("MoneyMoney not available: %s", txt)
                if isinstance(e, MoneyMoneyNotPermitted) and config.get("mitteilungen", True):
                    notify("Kontor", txt)
                return {"status": "nicht_verfuegbar", "text": txt}
            log.error("MoneyMoney error: %s", e)
            return {"status": "fehler", "text": tr("s_moneymoney_fehler_s") % e}
        fp = ledger_fp(ledger)
        if fp == state.get("fingerprint") and not force:
            log.info("No change in MoneyMoney since the last run.")
            return {"status": "unveraendert", "text": tr("s_keine_aenderung_in_moneymoney_seit"), "_ledger": ledger,
                    "_kategorien": categories}

        result = plan_all(ledger, config, today)
        for h in ledger.hints:
            log.warning("Data hint: %s", h); result.warnings.append(h)
        for i in result.info:
            log.info("Rules: %s", i)
        for w in result.warnings:
            log.warning("Rules warning: %s", w)
        bookings = [x for x in result.proposals if x.kind != "quelle"]
        for pr in result.proposals:
            log.info("  %s", pr.describe())

        written, err = 0, None
        if result.proposals and not dry:
            try:
                written = apply_proposals(bridge, ledger, result.proposals)
            except MoneyMoneyError as e:
                err = e
                log.error("Writing aborted after %d booking(s): %s", written, e)
            try:
                after = accounts_from_export(bridge.export_accounts())
                for u in {x.account_uuid for x in bookings}:
                    if u in after and abs(after[u].balance - ledger.accounts[u].balance) > 0.01:
                        msg = tr("s_saldo_s_nach_buchung_s") % (ledger.accounts[u].name, fmt_eur(after[u].balance),
                                                                      fmt_eur(ledger.accounts[u].balance))
                        log.warning("Balance of %s after booking is %s, expected %s", ledger.accounts[u].name, fmt_eur(after[u].balance), fmt_eur(ledger.accounts[u].balance)); result.warnings.append(msg)
            except MoneyMoneyError as e:
                log.warning("Verification after writing not possible: %s", e)

        warnings = list(result.warnings)
        if dry and bookings:
            warnings.insert(0, tr("s_probelauf_d_vorgeschlagene_buchung_en") % len(bookings))
        ums = None
        if with_report:
            ums = build_report(store, ledger, config, state, today, warnings, categories).pop("_umsaetze", None)
            state["kategorien_roh"] = categories or []

        summary = {"status": "fehler" if err else "ok", "zeit": datetime.now().strftime("%Y-%m-%d %H:%M"), "probelauf": dry,
                   "vorschlaege": [{"art": x.kind, "konto": x.account_path, "datum": x.booking_date.isoformat(),
                                    "betrag": x.amount, "text": x.purpose, "kategorie": x.category} for x in bookings],
                   "quellaenderungen": len(result.proposals) - len(bookings),
                   "geschrieben": written, "warnungen": result.warnings, "hinweise": result.info,
                   "fehler": str(err) if err else None}
        def _merge(cur: dict) -> None:
            cur["fingerprint"] = fp if err is None else None
            cur["letzter_lauf"] = summary
            cur.setdefault("verlauf", []).append({"zeit": summary["zeit"], "probelauf": dry, "geschrieben": written,
                                                  "vorschlaege": len(bookings), "fehler": summary["fehler"],
                                                  "buchungen": [x.describe() for x in bookings][:50]})
            cur["verlauf"] = cur["verlauf"][-100:]
            if state.get("snapshots"):
                merge_snapshots(cur, state["snapshots"])     # Schnellabgleich waehrend des Laufs bleibt erhalten
            if state.get("kategorien_roh"):
                cur["kategorien_roh"] = state["kategorien_roh"]
        store.update("state.json", _merge, {})      # Verlauf-Eingaben waehrend des Laufs bleiben erhalten

        if config.get("mitteilungen", True):
            if err:
                notify(tr("s_kontor_fehler"), str(err))
            elif written:
                notify("Kontor", "%d Buchung(en) in MoneyMoney angelegt." % written)
            elif bookings and dry:
                notify(tr("s_kontor_probelauf"), tr("s_d_buchung_en_warten_auf") % len(bookings))
            elif result.warnings and not dry:
                notify("Kontor: Hinweis", result.warnings[0])
        return dict(summary, _ledger=ledger, _kategorien=categories, _umsaetze=ums)
    finally:
        RUN_LOCK.release()


# ---------------------------------------------------------------------------
# Einstellungspakete
# ---------------------------------------------------------------------------

def _walk_refs(cfg: dict, fn: Callable[[str, str], str]) -> None:
    """Alle Kontoreferenzen der Konfiguration durch fn(feld, ref) ersetzen (in place)."""
    for section, field in REF_FIELDS:
        for item in cfg.get(section, []) or []:
            v = item.get(field)
            if isinstance(v, list):
                item[field] = [fn(section + "." + field, x) for x in v]
            elif isinstance(v, str) and v:
                item[field] = fn(section + "." + field, v)
    for b in cfg.get("bereiche") or []:
        if isinstance(b, dict):
            b["konten"] = [fn("bereiche.konten", x) for x in (b.get("konten") or [])]
    bil = cfg.setdefault("bilanz", {})
    bil["illiquide_konten"] = [fn("bilanz.illiquide_konten", x) for x in (bil.get("illiquide_konten") or [])]
    for key in ("ausgeblendet", "immer_anzeigen"):
        if bil.get(key):
            bil[key] = [fn("bilanz." + key, x) for x in bil[key]]
    for key in ("rollen", "verlauf", "konten_zuordnung"):
        if bil.get(key):
            bil[key] = {(fn("bilanz." + key, k) if not k.startswith("_") else k): v for k, v in bil[key].items()}
    for im in cfg.get("immobilien") or []:
        if im.get("objekt_konto"):
            im["objekt_konto"] = fn("immobilien.objekt_konto", im["objekt_konto"])
        if im.get("darlehen_konten"):
            im["darlehen_konten"] = {k: (fn("immobilien.darlehen_konten", v) if v else v) for k, v in im["darlehen_konten"].items()}
    kf = cfg.setdefault("kapitalfluss", {})
    kf["beteiligungs_gruppen"] = [fn("kapitalfluss.beteiligungs_gruppen", x) for x in (kf.get("beteiligungs_gruppen") or [])]
    if kf.get("kategorie_zu_konto"):
        kf["kategorie_zu_konto"] = {k: (fn("kapitalfluss.kategorie_zu_konto", v) if not k.startswith("_") else v)
                                    for k, v in kf["kategorie_zu_konto"].items()}
    st = cfg.setdefault("steuer", {})
    if st.get("objekt_darlehen"):
        st["objekt_darlehen"] = {(fn("steuer.objekt_darlehen", k) if not k.startswith("_") else k): v for k, v in st["objekt_darlehen"].items()}
    ents = []
    for e in st.get("entitaeten") or []:
        if isinstance(e, dict):
            e = dict(e); e["gruppe"] = fn("steuer.entitaeten", e.get("gruppe", "")); ents.append(e)
        else:
            ents.append(fn("steuer.entitaeten", e))
    st["entitaeten"] = ents


def export_package(config: dict, name: str = "Kontor-Einstellungen", strip_uuids: bool = False,
                   plan: Optional[dict] = None, ledger: Optional[Ledger] = None) -> dict:
    """Einstellungen als weitergebbares Paket. strip_uuids: Kontoreferenzen als Pfad (wenn ein Ledger
    vorliegt) bzw. Name statt UUID -- fuer eine andere MoneyMoney-Installation."""
    cfg = copy.deepcopy(merged_config(config))
    cfg.pop("oberflaeche", None)
    cfg.pop("updates", None)
    (cfg.get("belege") or {}).pop("ordner", None)
    if strip_uuids:
        def strip(field: str, r: str) -> str:
            if "|" not in r:
                return r
            uuid, label = (x.strip() for x in r.split("|", 1))
            if ledger is not None and uuid in ledger.accounts:
                return ledger.accounts[uuid].path
            return label
        _walk_refs(cfg, strip)
    pkg = {"kontor_paket": 1, "name": name, "version": version(), "erstellt": datetime.now().strftime("%Y-%m-%d"), "config": cfg}
    if plan:
        pkg["plan"] = plan
    return pkg


def import_package(current: dict, pkg: dict, ledger: Optional[Ledger], mode: str = "ergaenzen",
                   mapping: Optional[Dict[str, str]] = None) -> Tuple[dict, List[dict], List[str]]:
    """Paket in die Konfiguration uebernehmen. Liefert (config, unaufgeloeste Referenzen, Bericht)."""
    if not isinstance(pkg, dict) or not isinstance(pkg.get("config"), dict):
        raise ValueError(tr("s_keine_einstellungsdatei"))
    inc = copy.deepcopy(pkg["config"])
    for k in ("oberflaeche", "updates"):
        inc.pop(k, None)
    mapping = mapping or {}
    unresolved: List[dict] = []
    report: List[str] = []

    def resolve(field: str, ref: str) -> str:
        if not ref:
            return ref
        if ref in mapping and mapping[ref]:
            return mapping[ref]
        if ledger is None:
            return ref
        try:
            a = ledger.resolve(ref)
            return "%s | %s" % (a.uuid, a.name)
        except KeyError:
            label = ref.split("|", 1)[1].strip() if "|" in ref else ref
            if not any(u["ref"] == ref for u in unresolved):
                unresolved.append({"ref": ref, "label": label, "feld": field})
            return ref

    _walk_refs(inc, resolve)
    base = copy.deepcopy(merged_config(current))
    if mode == "ersetzen":
        for k, v in inc.items():
            base[k] = v
            report.append("%s ersetzt" % k)
    else:
        for k, v in inc.items():
            if k in ("darlehen", "beteiligungen", "saldo_spiegel", "bereiche", "immobilien"):
                key = "id" if k in ("bereiche", "immobilien") else "name"
                existing = {x.get(key): i for i, x in enumerate(base.get(k) or []) if isinstance(x, dict)}
                base.setdefault(k, [])
                for item in v or []:
                    if not isinstance(item, dict):
                        continue
                    if k == "bereiche" and item.get("haupt"):
                        for x in base[k]:
                            if isinstance(x, dict):
                                x["haupt"] = False
                    if item.get(key) in existing:
                        base[k][existing[item[key]]] = item
                        report.append(tr("s_s_s_aktualisiert") % (k, item.get("name") or item.get(key)))
                    else:
                        base[k].append(item)
                        report.append(tr("s_s_s_hinzugefuegt") % (k, item.get("name") or item.get(key)))
            elif isinstance(v, dict):
                base.setdefault(k, {})
                for kk, vv in v.items():
                    if isinstance(vv, dict) and isinstance(base[k].get(kk), dict):
                        base[k][kk].update(vv)
                    elif isinstance(vv, list) and kk in ("illiquide_konten", "bereiche", "beteiligungs_gruppen", "umbuchungs_kategorien", "entitaeten"):
                        base[k][kk] = list(dict.fromkeys((base[k].get(kk) or []) + vv))
                    else:
                        base[k][kk] = vv
                report.append(tr("s_s_ergaenzt") % k)
            else:
                base[k] = v
                report.append("%s gesetzt" % k)
    return merged_config(base), unresolved, report


# ---------------------------------------------------------------------------
# Diagnose
# ---------------------------------------------------------------------------

_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9 ]{10,32}\b")
_DIGITS = re.compile(r"\d{7,}")


def mask_text(text: str, names: Optional[Dict[str, str]] = None) -> str:
    text = _IBAN.sub(lambda m: m.group(0)[:4] + "…", text)
    text = _DIGITS.sub("#######", text)
    if names:
        for n in sorted(names, key=len, reverse=True):
            if len(n) >= 3:
                text = text.replace(n, names[n])
    return text


def diagnose(store: Store, data_dir: str, config: dict, status: dict, mask_names: bool = True, lines: int = 400) -> str:
    cfg = copy.deepcopy(config)
    cfg.pop("oberflaeche", None)
    names: Dict[str, str] = {}
    if mask_names:
        ds = store.load("dataset.json", {}) or {}
        for i, k in enumerate(ds.get("konten") or []):
            names[k["name"]] = "Konto%02d" % i
        for i, k in enumerate((ds.get("bereich_namen") or {}).values()):
            names[k] = "Bereich%d" % i
        for l in cfg.get("darlehen") or []:
            if (l.get("erkennung") or {}).get("gegen_iban"):
                l["erkennung"]["gegen_iban"] = tr("s_iban")
    _walk_refs(cfg, lambda f, r: ((r.split("|", 1)[0].strip()[:8] + " | " + mask_text(r.split("|", 1)[1].strip(), names))
                                  if "|" in r else mask_text(r, names)))
    state = store.load("state.json", {}) or {}
    st = copy.deepcopy(status)
    for k in ("letztes_ergebnis", "letzter_lauf"):
        if isinstance(st.get(k), dict):
            st[k] = {kk: vv for kk, vv in st[k].items() if kk != "vorschlaege"}
    home = os.path.expanduser("~")

    def m(text: str) -> str:
        text = mask_text(text, names)
        return text.replace(home, "~") if home and home != "/" else text

    out = ["Kontor-Diagnose %s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
           "Version %s, Python %s, %s %s" % (version(), platform.python_version(), platform.system(), platform.release()),
           "Status: " + m(json.dumps(st, ensure_ascii=False, default=str)),
           "Konfiguration (Namen %s): %s" % ("maskiert" if mask_names else tr("s_im_klartext"), m(json.dumps(cfg, ensure_ascii=False, indent=1))),
           tr("s_letzter_lauf") + m(json.dumps(state.get("letzter_lauf"), ensure_ascii=False, default=str)),
           "Verlauf: " + m(json.dumps((state.get("verlauf") or [])[-10:], ensure_ascii=False, default=str)),
           "--- Protokoll (letzte %d Zeilen) ---" % lines]
    try:
        with open(os.path.join(data_dir, "kontor.log"), encoding="utf-8", errors="replace") as f:
            out += [m(l.rstrip("\n")) for l in f.readlines()[-lines:]]
    except FileNotFoundError:
        out.append(tr("s_kein_protokoll"))
    return "\n".join(out)
