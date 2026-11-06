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
from mm_model import Account, Ledger, accounts_from_export, add_months, fmt_eur, month_key, tx_from_export, norm_cat
import mm_immo
import mm_kategorien
from mm_report import ROLES, account_roles, build_dataset
from mm_rules import Proposal, plan_all
from mm_store import Store
from mm_tax import build_tax

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
    "moneymoney": {"kategorisieren_erlauben": False, "aktualisieren_erlauben": True},
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
    # Vorversionen: bilanz.wurzel / bilanz.hauptbereich / bilanz.bereiche (Referenzen) -> Bereichsobjekte
    bil = out["bilanz"]
    haupt = bil.pop("hauptbereich", None) or bil.pop("wurzel", None)
    alte = bil.pop("bereiche", None) or []
    if not out.get("bereiche"):
        if alte:
            refs = [r for r in ([haupt] if haupt else []) + list(alte) if r]
            seen = set()
            objs = []
            for r in refs:
                key = r.split("|", 1)[0].strip()
                if key in seen:
                    continue
                seen.add(key)
                objs.append({"id": key, "name": (r.split("|", 1)[1].strip() if "|" in r else r), "konten": [r], "haupt": r == haupt})
            out["bereiche"] = objs
        elif haupt:
            bil["hauptbereich"] = haupt      # alle Kontengruppen als Bereiche, diese als Hauptbereich
    for i, b in enumerate(out["bereiche"]):
        if isinstance(b, str):
            out["bereiche"][i] = b = {"id": b.split("|", 1)[0].strip(), "name": (b.split("|", 1)[1].strip() if "|" in b else b), "konten": [b]}
        b.setdefault("id", "b%d" % (i + 1))
        b.setdefault("name", "Bereich %d" % (i + 1))
        b.setdefault("konten", [])
        b.setdefault("art", "")
        b.setdefault("aktiv", True)
    if out["bereiche"] and not any(b.get("haupt") for b in out["bereiche"]):
        out["bereiche"][0]["haupt"] = True
    out["bilanz"].pop("wurzel", None)
    for im in out.get("immobilien") or []:
        im.setdefault("kalkulationen", [])
        im.setdefault("dokumente", [])
        im.setdefault("darlehen_konten", {})
    return out


def version() -> str:
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0"


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


def fetch(bridge: Bridge, config: dict, today: date, with_portfolio: bool = False) -> Ledger:
    accounts = accounts_from_export(bridge.export_accounts())
    since = earliest_needed(config, today)
    txs = tx_from_export(bridge.export_transactions(since))
    ledger = Ledger(accounts, txs)
    ledger.portfolios = {}
    if with_portfolio:
        for a in accounts.values():
            if a.portfolio and not a.group:
                try:
                    ledger.portfolios[a.uuid] = bridge.export_portfolio(a.uuid)
                except MoneyMoneyError as e:
                    log.info("Depot %s: keine Positionsdaten (%s)", a.uuid[:8], str(e)[:80])
    log.info("MoneyMoney: %d Konten, %d Umsätze seit %s, %d Depots", len(accounts), len(txs), since, len(ledger.portfolios))
    return ledger


def fingerprint(ledger: Ledger) -> str:
    h = hashlib.sha256()
    for a in sorted(ledger.accounts.values(), key=lambda x: x.uuid):
        h.update(("%s|%.2f|%s\n" % (a.uuid, a.balance, a.refresh.isoformat() if a.refresh else "")).encode())
    h.update(str(len(ledger.txs)).encode())
    return h.hexdigest()


def unavailable_text(e: Exception) -> Optional[str]:
    if isinstance(e, MoneyMoneyNotRunning):
        return "MoneyMoney läuft nicht."
    if isinstance(e, MoneyMoneyLocked):
        return "MoneyMoney ist gesperrt -- bitte in MoneyMoney entsperren."
    if isinstance(e, MoneyMoneyNotPermitted):
        return ("Keine Berechtigung, MoneyMoney zu steuern: Systemeinstellungen > Datenschutz & Sicherheit > "
                "Automation -> Python/Kontor für MoneyMoney erlauben.")
    return None


def _bereich_art(name: str) -> str:
    low = name.lower()
    if any(k in low for k in ("gbr", "ohg", " kg", "gmbh", " ag", " ug", "e.k.", "gesellschaft", "holding")):
        return "gesellschaft"
    return "privat"


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
        haupt_uuid = None
        href = (config.get("bilanz") or {}).get("hauptbereich")
        if href:
            try:
                haupt_uuid = ledger.resolve(href).uuid
            except KeyError:
                pass
        for g in ledger.roots():
            out.append({"id": g.uuid, "name": g.name, "art": _bereich_art(g.name), "anteil": anteile.get(g.uuid), "haupt": g.uuid == haupt_uuid,
                        "konten": ["%s | %s" % (g.uuid, g.name)], "leaves": ledger.descendants(g.uuid), "gruppen": [g]})
        if out and not any(b["haupt"] for b in out):
            out[0]["haupt"] = True
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
    for a in sorted(ledger.accounts.values(), key=lambda x: x.path):
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
            add("fehler", "%s: '%s' hat eine Bankanbindung -- nur manuell geführte Konten werden bebucht." % (label, a.path))
        elif not group_ok and a.group:
            add("fehler", "%s: '%s' ist eine Gruppe." % (label, a.path))
        elif want_group and not a.group:
            add("fehler", "%s: '%s' ist keine Gruppe." % (label, a.path))
        else:
            add("ok", "%s → %s" % (label, a.path))
        return a

    def cat(label, name):
        if name and categories and name not in cat_names and name.split("\\")[-1] not in cat_names:
            add("warnung", "%s: Kategorie '%s' existiert nicht in MoneyMoney." % (label, name))

    for l in config.get("darlehen", []) or []:
        n = l.get("name", "?") + ("" if l.get("aktiv", True) else " (inaktiv)")
        ref("Darlehen %s: Konto" % n, l.get("darlehenskonto", ""), want_offline=True, group_ok=False)
        for s_ in l.get("quellkonten", []) or []:
            ref("Darlehen %s: Quelle" % n, s_, group_ok=False)
        b = l.get("buchung", {}) or {}
        cat("Darlehen %s" % n, b.get("kategorie_tilgung"))
        cat("Darlehen %s" % n, b.get("kategorie_zins"))
        erk = l.get("erkennung") or {}
        iban = (erk.get("gegen_iban") or "").replace(" ", "")
        if not iban and not erk.get("text_enthaelt"):
            add("fehler", "Darlehen %s: Erkennung braucht Gegen-IBAN oder Text." % n)
        if iban and not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", iban):
            add("fehler", "Darlehen %s: '%s' ist keine IBAN." % (n, iban))
        try:
            date.fromisoformat(l.get("ab_datum", ""))
        except ValueError:
            add("fehler", "Darlehen %s: ab_datum fehlt oder ist kein Datum (JJJJ-MM-TT)." % n)
    for b in (config.get("beteiligungen", []) or []) + (config.get("saldo_spiegel", []) or []):
        n = b.get("name", "?") + ("" if b.get("aktiv", True) else " (inaktiv)")
        ref("Wert %s: Ziel" % n, b.get("zielkonto") or b.get("beteiligungskonto", ""), want_offline=True, group_ok=False)
        ref("Wert %s: Quelle" % n, b.get("gruppe") or b.get("quellkonto", ""), want_group=bool(b.get("gruppe")))
    bil = config.get("bilanz", {}) or {}
    if not (config.get("bereiche") or []):
        add("hinweis", "Keine Bereiche gewählt -- jede Kontengruppe der obersten Ebene wird als Bereich ausgewertet.")
    for b in config.get("bereiche") or []:
        if not isinstance(b, dict):
            continue
        if not b.get("konten"):
            add("fehler", "Bereich '%s' hat keine Konten." % b.get("name"))
        for r in b.get("konten") or []:
            ref("Bereich %s" % b.get("name"), r)
    bereiche = bereiche_for(ledger, config)
    seen_leaf: Dict[str, str] = {}
    roles = account_roles(ledger, config)
    for b in bereiche:
        for a in b["leaves"]:
            if a.uuid in seen_leaf and seen_leaf[a.uuid] != b["name"]:
                add("warnung", "Konto '%s' liegt in mehreren Bereichen (%s, %s)." % (a.path, seen_leaf[a.uuid], b["name"]))
            seen_leaf[a.uuid] = b["name"]
        missing = [a.path for a in b["leaves"] if roles.get(a.uuid) == "sonstiges"]
        if missing:
            add("warnung", "%s: Konten ohne Position (Umsätze landen in 'Unklar'): %s -- unter Bilanz → Konten zuordnen."
                % (b["name"], "; ".join(missing[:8]) + (" …" if len(missing) > 8 else "")))
    for r in bil.get("illiquide_konten") or []:
        ref("Bilanz: illiquide", r)
    for k, v in (bil.get("rollen") or {}).items():
        if not k.startswith("_"):
            ref("Position für", k)
            if v not in ROLES:
                add("fehler", "Unbekannte Position '%s' für %s." % (v, k))
    for k, v in (bil.get("verlauf") or {}).items():
        ref("Verlauf für", k, group_ok=False)
        if v not in ("umsaetze", "stand"):
            add("fehler", "Unbekannte Verlaufsquelle '%s' für %s." % (v, k))
    for k in (bil.get("ausgeblendet") or []) + (bil.get("immer_anzeigen") or []):
        ref("Bilanz: Anzeige", k)
    for im in config.get("immobilien") or []:
        n = im.get("name") or "?"
        if im.get("objekt_konto"):
            ref("Immobilie %s: Objektkonto" % n, im["objekt_konto"], group_ok=False)
        for ln, r in (im.get("darlehen_konten") or {}).items():
            if r:
                ref("Immobilie %s: Darlehen %s" % (n, ln), r, group_ok=False)
        if im.get("bereich") and not any(b["id"] == im["bereich"] for b in bereiche):
            add("warnung", "Immobilie %s: Bereich '%s' existiert nicht." % (n, im["bereich"]))
        if im.get("kategorie"):
            cat("Immobilie %s" % n, str(im["kategorie"]).split("\\")[-1])
    kfc = config.get("kapitalfluss", {}) or {}
    for g in kfc.get("beteiligungs_gruppen", []) or []:
        ref("Kapitalfluss: Beteiligungsgruppe", g, want_group=True)
    for k, v in (kfc.get("kategorie_zuordnung") or {}).items():
        if k.startswith("_"):
            continue
        cat("Kapitalfluss: Zuordnung", k)
        if str(v).split("/")[0] not in ("Einnahmen", "Ausgaben", "Investitionen", "Finanzierung"):
            add("fehler", "Kapitalfluss: Zuordnung '%s' → '%s' unbekannt." % (k, v))
    for k, v in (kfc.get("kategorie_zu_konto") or {}).items():
        if not k.startswith("_"):
            cat("Kapitalfluss: Depotzuordnung", k)
            ref("Kapitalfluss: Depot für '%s'" % k, v, group_ok=False)
    st = config.get("steuer", {}) or {}
    for k, v in (st.get("objekt_darlehen") or {}).items():
        ref("Steuer: Darlehen für Objekt '%s'" % v, k)
    bel = config.get("belege", {}) or {}
    folder = os.path.expanduser(bel.get("ordner") or DEFAULT_CONFIG["belege"]["ordner"])
    if os.path.isdir(folder) and not os.access(folder, os.W_OK):
        add("fehler", "Belegordner nicht beschreibbar: %s" % folder)
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
                raise MoneyMoneyError("Verweigert: '%s' ist kein manuell geführtes Konto." % acc.path)
            bridge.add_transaction(acc.uuid, pr.booking_date, pr.payee, pr.amount, pr.purpose,
                                   pr.category or None, fallback_refs=[acc.name])
        done += 1
        log.info("%s %s", "GEBUCHT" if not bridge.dry_run else "PROBELAUF", pr.describe())
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
    kat = mm_kategorien.load(store) if store is not None else mm_kategorien.empty()
    for t in ledger.txs:
        if t.account_uuid not in ent_of:
            continue
        path, q = mm_kategorien.effective(kat, t)
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
            res = mm_immo.berechne(k.get("eingaben") or {}, today)
        except Exception as e:  # pragma: no cover - fehlerhafte Eingaben duerfen den Bericht nicht stoppen
            log.warning("Immobilie %s: Kalkulation fehlgeschlagen: %s", im.get("name"), e)
            out[str(im.get("id"))] = {"fehler": str(e)}
            continue
        out[str(im.get("id"))] = {"kalkulation": k.get("id"), "name": k.get("name"), "kennzahlen": res["kennzahlen"], "jahre": res["jahre"],
                                  "hinweise": res["hinweise"], "darlehen_namen": res["darlehen_namen"], "start": res["start"],
                                  "reihen": mm_immo.planreihen(res)}
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


def prepare_categories(store: Store, ledger: Ledger, config: dict, categories: Optional[List[dict]]) -> dict:
    """Kontor-Kategorien: MoneyMoney-Baum als Vorschlag uebernehmen, Regeln lernen, Luecken fuellen, auf den Ledger legen."""
    kc = config.get("kategorien") or {}
    kat = mm_kategorien.load(store)
    if not kc.get("aktiv", True):
        mm_kategorien.apply_to_ledger(mm_kategorien.empty(), ledger)
        return kat
    changed = False
    if categories and (not kat.get("mm_uebernommen") or len(kat["baum"]) < len(categories)):
        if mm_kategorien.seed_from_moneymoney(kat, categories):
            changed = True
    if kc.get("lernen", True):
        before = len(kat["regeln"])
        mm_kategorien.learn(kat, ledger)
        changed = changed or len(kat["regeln"]) != before or not kat.get("gelernt_am")
    if mm_kategorien.auto_assign(kat, ledger, overwrite_mm=bool(kc.get("mm_ueberschreiben"))):
        changed = True
    if changed:
        mm_kategorien.save(store, kat)
    mm_kategorien.apply_to_ledger(kat, ledger)
    return kat


def build_report(store: Store, ledger: Ledger, config: dict, state: dict, today: date, warnings: List[str],
                 categories: Optional[List[dict]] = None) -> dict:
    kat = prepare_categories(store, ledger, config, categories)
    snaps = state.setdefault("snapshots", {})
    snaps[month_key(today)] = {a.uuid: a.balance for a in ledger.accounts.values() if not a.group}
    if len(snaps) > 600:
        for k in sorted(snaps)[:-600]:
            snaps.pop(k, None)
    bereiche = bereiche_for(ledger, config)
    haupt = main_bereich(bereiche)
    roles = account_roles(ledger, config)
    budgets = budgets_from_categories(categories or [])
    immo_res = immo_results(config, today)
    log.debug("Bericht: %d Bereiche (%s), Haupt %s, %d Konten mit Position, %d Immobilienkalkulationen, %d Budgets",
              len(bereiche), ", ".join(b["name"] for b in bereiche), haupt["name"] if haupt else "-", len(roles), len(immo_res), len(budgets))
    datasets: Dict[str, dict] = {}
    for b in bereiche:
        try:
            ds = build_dataset(ledger, config, state, today, b, roles, warnings if (haupt and b["id"] == haupt["id"]) else [])
            ds["budgets"] = budgets
            datasets[b["id"]] = ds
        except Exception as e:
            log.exception("Bereich %s: Bericht fehlgeschlagen", b["name"])
            datasets[b["id"]] = {"fehler": str(e), "wurzel": b["name"]}
    neu = konten_neu(ledger, config, bereiche, roles)
    if neu:
        warnings.append("%d Konto/Konten ohne bestätigte Zuordnung (Einrichtung → Bilanzpositionen & Verlauf): %s"
                        % (len(neu), ", ".join(k["name"] for k in neu[:5]) + (" …" if len(neu) > 5 else "")))
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
                log.warning("Soll/Ist %s: %s", im.get("name"), e)
        elif r:
            entry["fehler"] = r["fehler"]
        immobilien.append(entry)
    for bid, ds in datasets.items():
        if "fehler" not in ds:
            log.debug("Bereich %s: %d Monate (%s bis %s), %d Konten, %d inaktiv, %d Warnung(en)", ds.get("bereich", {}).get("name", bid),
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
        "steuer": build_tax(ledger, config, today, bereiche, roles, immo_afa_map(config, immo_res)),
        "depots": portfolio_summary(ledger, bereiche),
        "immobilien": immobilien,
        "budgets": budgets,
        "warnungen": warnings,
        "kategorien": mm_kategorien.stats(kat, ledger),
        "konten_neu": neu,
    }
    store.save("dataset.json", dataset)
    ums = compact_transactions(ledger, bereiche, store)
    store.save("umsaetze.json", ums)
    dataset["_umsaetze"] = ums        # fuer den Dienst: Liste im Speicher behalten (teilt die Strings mit dem Ledger), nicht Teil der Datei
    return dataset


def account_tree(ledger: Ledger, config: dict, roles: Optional[Dict[str, str]] = None, datasets: Optional[Dict[str, dict]] = None) -> List[dict]:
    roles = roles if roles is not None else account_roles(ledger, config)
    inactive: set = set()
    verlauf: Dict[str, str] = {}
    bereich_of: Dict[str, str] = {}
    bereich_id: Dict[str, str] = {}
    for bid, ds in (datasets or {}).items():
        inactive.update(ds.get("konten_inaktiv") or [])
        bname = (ds.get("bereich") or {}).get("name") or ""
        for r in (ds.get("bilanz") or {}).get("zeilen") or []:
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
    vcfg = (config.get("bilanz") or {}).get("verlauf") or {}
    out = []
    for a in sorted(ledger.accounts.values(), key=lambda x: x.path):
        if not a.path:
            continue
        out.append({"uuid": a.uuid, "name": a.name, "pfad": a.path, "ebene": a.path.count(" / "), "gruppe": a.group,
                    "depot": a.portfolio, "manuell": a.offline, "rolle": roles.get(a.uuid, "") if not a.group else "",
                    "saldo": None if a.group else a.balance, "waehrung": a.currency, "typ": a.type, "inaktiv": a.uuid in inactive,
                    "verlauf": verlauf.get(a.uuid) or ("stand" if a.portfolio else "umsaetze"), "bereich": bereich_of.get(a.uuid, ""),
                    "bereich_id": bereich_id.get(a.uuid, ""), "bestaetigt": a.uuid in confirmed,
                    "aktualisiert": a.refresh.strftime("%Y-%m-%d %H:%M") if a.refresh else None})
    return out


def run_once(store: Store, config: dict, today: date, dry: bool, force: bool,
             bridge_factory: Callable[[bool], Bridge] = Bridge, with_report: bool = True,
             categories: Optional[List[dict]] = None) -> dict:
    if not RUN_LOCK.acquire(blocking=False):
        return {"status": "laeuft_bereits", "text": "Ein Lauf ist bereits aktiv."}
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
                log.info(txt)
                if isinstance(e, MoneyMoneyNotPermitted) and config.get("mitteilungen", True):
                    notify("Kontor", txt)
                return {"status": "nicht_verfuegbar", "text": txt}
            log.error("MoneyMoney-Fehler: %s", e)
            return {"status": "fehler", "text": "MoneyMoney-Fehler: %s" % e}
        fp = fingerprint(ledger)
        if fp == state.get("fingerprint") and not force:
            log.info("Keine Änderung in MoneyMoney seit dem letzten Lauf.")
            return {"status": "unveraendert", "text": "Keine Änderung in MoneyMoney seit dem letzten Lauf.", "_ledger": ledger,
                    "_kategorien": categories}

        result = plan_all(ledger, config, today)
        for h in ledger.hints:
            log.warning(h); result.warnings.append(h)
        for i in result.info:
            log.info(i)
        for w in result.warnings:
            log.warning(w)
        bookings = [x for x in result.proposals if x.kind != "quelle"]
        for pr in result.proposals:
            log.info("  %s", pr.describe())

        written, err = 0, None
        if result.proposals and not dry:
            try:
                written = apply_proposals(bridge, ledger, result.proposals)
            except MoneyMoneyError as e:
                err = e
                log.error("Abbruch beim Schreiben nach %d Buchung(en): %s", written, e)
            try:
                after = accounts_from_export(bridge.export_accounts())
                for u in {x.account_uuid for x in bookings}:
                    if u in after and abs(after[u].balance - ledger.accounts[u].balance) > 0.01:
                        msg = "Saldo %s nach Buchung %s, erwartet %s" % (ledger.accounts[u].name, fmt_eur(after[u].balance),
                                                                      fmt_eur(ledger.accounts[u].balance))
                        log.warning(msg); result.warnings.append(msg)
            except MoneyMoneyError as e:
                log.warning("Kontrolle nach dem Schreiben nicht möglich: %s", e)

        warnings = list(result.warnings)
        if dry and bookings:
            warnings.insert(0, "Probelauf: %d vorgeschlagene Buchung(en) sind NICHT in MoneyMoney." % len(bookings))
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
                cur["snapshots"] = state["snapshots"]
            if state.get("kategorien_roh"):
                cur["kategorien_roh"] = state["kategorien_roh"]
        store.update("state.json", _merge, {})      # Verlauf-Eingaben waehrend des Laufs bleiben erhalten

        if config.get("mitteilungen", True):
            if err:
                notify("Kontor: Fehler", str(err))
            elif written:
                notify("Kontor", "%d Buchung(en) in MoneyMoney angelegt." % written)
            elif bookings and dry:
                notify("Kontor: Probelauf", "%d Buchung(en) warten auf Freigabe." % len(bookings))
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
    bil = cfg.setdefault("bilanz", {})
    if bil.get("hauptbereich"):
        bil["hauptbereich"] = fn("bilanz.hauptbereich", bil["hauptbereich"])
    if bil.get("bereiche"):
        bil["bereiche"] = [fn("bilanz.bereiche", x) for x in (bil.get("bereiche") or [])]
    for b in cfg.get("bereiche") or []:
        if isinstance(b, dict):
            b["konten"] = [fn("bereiche.konten", x) for x in (b.get("konten") or [])]
    bil["illiquide_konten"] = [fn("bilanz.illiquide_konten", x) for x in (bil.get("illiquide_konten") or [])]
    for key in ("ausgeblendet", "immer_anzeigen"):
        if bil.get(key):
            bil[key] = [fn("bilanz." + key, x) for x in bil[key]]
    for key in ("rollen", "verlauf", "konten_zuordnung", "verrechnung"):
        if bil.get(key):
            bil[key] = {(fn("bilanz." + key, k) if not k.startswith("_") else k): v for k, v in bil[key].items()}
    if bil.get("verrechnung"):
        bil["verrechnung"] = {k: (fn("bilanz.verrechnung", v) if isinstance(v, str) and v else v) for k, v in bil["verrechnung"].items()}
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
        raise ValueError("Keine Kontor-Einstellungsdatei (Feld 'config' fehlt).")
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
                        report.append("%s '%s' aktualisiert" % (k, item.get("name") or item.get(key)))
                    else:
                        base[k].append(item)
                        report.append("%s '%s' hinzugefügt" % (k, item.get("name") or item.get(key)))
            elif isinstance(v, dict):
                base.setdefault(k, {})
                for kk, vv in v.items():
                    if isinstance(vv, dict) and isinstance(base[k].get(kk), dict):
                        base[k][kk].update(vv)
                    elif isinstance(vv, list) and kk in ("illiquide_konten", "bereiche", "beteiligungs_gruppen", "umbuchungs_kategorien", "entitaeten"):
                        base[k][kk] = list(dict.fromkeys((base[k].get(kk) or []) + vv))
                    else:
                        base[k][kk] = vv
                report.append("%s ergänzt" % k)
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
                l["erkennung"]["gegen_iban"] = "IBAN…"
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
           "Konfiguration (Namen %s): %s" % ("maskiert" if mask_names else "im Klartext", m(json.dumps(cfg, ensure_ascii=False, indent=1))),
           "Letzter Lauf: " + m(json.dumps(state.get("letzter_lauf"), ensure_ascii=False, default=str)),
           "Verlauf: " + m(json.dumps((state.get("verlauf") or [])[-10:], ensure_ascii=False, default=str)),
           "--- Protokoll (letzte %d Zeilen) ---" % lines]
    try:
        with open(os.path.join(data_dir, "kontor.log"), encoding="utf-8", errors="replace") as f:
            out += [m(l.rstrip("\n")) for l in f.readlines()[-lines:]]
    except FileNotFoundError:
        out.append("(kein Protokoll)")
    return "\n".join(out)
