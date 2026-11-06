"""Kontor-Dienst: Web-Oberflaeche (API + statische Dateien) und Zeitplaner in einem Prozess.

Sicherheit:
  * bindet an 127.0.0.1 (oder eine Tailscale-Adresse 100.64.0.0/10, wenn eingestellt); nie 0.0.0.0
  * Anmeldung mit Passwort (oder Touch ID von diesem Mac aus), Sitzungscookie HttpOnly/SameSite=Strict,
    CSRF-Token fuer jede aendernde Anfrage, Origin-Pruefung, Ratenbegrenzung, Leerlaufsperre
  * CSP ohne Fremdquellen; einzige Netzverbindung: die abschaltbare Update-Pruefung bei GitHub
  * Schreibzugriffe auf MoneyMoney nur ueber mm_core (manuelle Konten, Allowlist der Bruecke);
    Kategorisieren und das Ausloesen der Aktualisierung nur, wenn in den Einstellungen erlaubt
  * Scharfe Laeufe, Updates, Dateizugriffe (Belegordner oeffnen) nur von diesem Mac aus
"""
from __future__ import annotations

import base64
import binascii
import copy
import ipaddress
import json
import logging
import mimetypes
import os
import ssl
import subprocess
import sys
import threading
import time
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import mm_auth
import mm_immo
import mm_import
import mm_kategorien
import mm_update
from mm_belege import Belege, file_status
from mm_bridge import Bridge, MoneyMoneyError, is_running, refresh_moneymoney
from mm_core import (account_tree, bereiche_for, build_report, check_config, diagnose, export_package, fetch, immo_for_plan, immo_results,
                     import_package, merged_config, run_once, unavailable_text, version)
from mm_model import Ledger
from mm_report import ROLE_LABELS, ROLES, apply_plan
from mm_store import Store
from mm_xlsx import Sheet, workbook

log = logging.getLogger("kontor.app")
HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, "web")
MAX_BODY = 2 * 1024 * 1024
MAX_UPLOAD = 90 * 1024 * 1024      # Base64 eines 60-MB-Belegs
PLAN_PARAMS = ("horizont_monate", "standard_methode", "inflation_prozent_pa", "steigerung_einnahmen_prozent_pa",
               "steigerung_ausgaben_prozent_pa", "rendite_prozent_pa", "fi_rendite_real_prozent")


def bind_allowed(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return ip.is_loopback or ip in ipaddress.ip_network("100.64.0.0/10")


class App:
    def __init__(self, store: Store, data_dir: str, bridge_factory=Bridge):
        self.store = store
        self.data_dir = data_dir
        self.bridge_factory = bridge_factory
        self.config = merged_config(store.load("config.json", {}) or {})
        self.sessions = mm_auth.Sessions(idle_minutes=int(self.config["oberflaeche"].get("sperre_minuten", 15)))
        self.ledger: Optional[Ledger] = None            # letzter Stand aus MoneyMoney
        self.ledger_time: Optional[datetime] = None
        st = store.load("state.json", {}) or {}
        self.categories_raw: list = st.get("kategorien_roh") or []
        self.started = datetime.now()
        self.last_run_at: Optional[float] = None
        self.last_result: Optional[dict] = None
        self.running = False
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.update_info: Optional[dict] = None
        self.update_checked: Optional[float] = None
        self.mm_refresh_at: Optional[float] = None
        self._cfg_mtime = self._config_mtime()

    # -- Konfiguration -----------------------------------------------------
    def save_config(self, cfg: dict) -> None:
        self.config = merged_config(cfg)
        self.store.save("config.json", self.config)
        self.sessions.set_idle(int(self.config["oberflaeche"].get("sperre_minuten", 15)))
        self._cfg_mtime = self._config_mtime()

    def _config_mtime(self) -> float:
        try:
            return os.path.getmtime(self.store.path("config.json"))
        except OSError:
            return 0.0

    def reload_config_if_changed(self) -> bool:
        """Konfiguration neu laden, wenn sie ausserhalb des Dienstes geaendert wurde (CLI paket-import)."""
        m = self._config_mtime()
        if m == getattr(self, "_cfg_mtime", None):
            return False
        self._cfg_mtime = m
        self.config = merged_config(self.store.load("config.json", {}) or {})
        self.sessions.set_idle(int(self.config["oberflaeche"].get("sperre_minuten", 15)))
        log.info("Konfiguration neu geladen (ausserhalb des Dienstes geaendert).")
        return True

    def auth_record(self) -> dict:
        return self.store.load("auth.json", {}) or {}

    def categories(self) -> List[dict]:
        out = []
        for c in self.categories_raw:
            b = c.get("budget") if isinstance(c.get("budget"), dict) else None
            out.append({"name": c.get("name"), "pfad": str(c.get("path") or c.get("name") or "").replace("\\", " / "),
                        "roh": str(c.get("path") or c.get("name") or ""),
                        "gruppe": bool(c.get("group", False)), "ebene": int(c.get("indentation") or 0),
                        "budget": b if b and b.get("amount") else None})
        return out

    def config_has_rules(self) -> bool:
        c = self.config
        return bool(c.get("darlehen") or c.get("beteiligungen") or c.get("saldo_spiegel") or c.get("bereiche") or c.get("immobilien"))

    def rebuild_report(self) -> Tuple[bool, Optional[str]]:
        """Bericht aus dem letzten bekannten Stand neu bauen (nach Aenderungen an Verlauf/Konfiguration)."""
        if self.ledger is None:
            ledger, err = self.refresh_ledger()
            if ledger is None:
                return False, err
        st = self.store.load("state.json", {}) or {}
        try:
            build_report(self.store, self.ledger, self.config, st, date.today(), [], self.categories_raw)
        except Exception as e:  # pragma: no cover
            log.exception("Bericht")
            return False, "Bericht fehlgeschlagen: %s" % e
        self.store.save("state.json", st)
        return True, None

    # -- MoneyMoney --------------------------------------------------------
    def refresh_ledger(self) -> Tuple[Optional[Ledger], Optional[str]]:
        try:
            b = self.bridge_factory(True)
            ledger = fetch(b, self.config, date.today())
            try:
                self.categories_raw = b.export_categories()
                st = self.store.load("state.json", {}) or {}
                st["kategorien_roh"] = self.categories_raw
                self.store.save("state.json", st)
            except MoneyMoneyError:
                pass
            self.ledger, self.ledger_time = ledger, datetime.now()
            return ledger, None
        except MoneyMoneyError as e:
            return None, unavailable_text(e) or ("MoneyMoney-Fehler: %s" % e)

    def do_run(self, dry: Optional[bool], force: bool, with_report: bool = True) -> dict:
        with self.lock:
            if self.running:
                return {"status": "laeuft_bereits", "text": "Ein Lauf ist bereits aktiv."}
            self.running = True
        try:
            d = self.config.get("probelauf", True) if dry is None else dry
            res = run_once(self.store, self.config, date.today(), d, force, self.bridge_factory, with_report)
            self.last_run_at = time.time()
            ledger = res.pop("_ledger", None)
            cats = res.pop("_kategorien", None)
            if ledger is not None:
                self.ledger, self.ledger_time = ledger, datetime.now()
            if cats:
                self.categories_raw = cats
            self.last_result = res
            return res
        except Exception as e:  # pragma: no cover - letzte Sicherung, damit der Dienst weiterlaeuft
            log.exception("Lauf fehlgeschlagen")
            self.last_result = {"status": "fehler", "text": "Unerwarteter Fehler: %s" % e}
            return self.last_result
        finally:
            self.running = False

    def scheduler(self) -> None:
        while not self.stop.is_set():
            try:
                self.reload_config_if_changed()
                z = self.config.get("zeitplan", {}) or {}
                interval = max(5, int(z.get("intervall_minuten", 30))) * 60
                due = z.get("automatisch", True) and (self.last_run_at is None or time.time() - self.last_run_at >= interval)
                if due:
                    if is_running():
                        self.do_run(None, force=False)
                    else:
                        self.last_run_at = time.time()
                up = self.config.get("updates", {}) or {}
                if up.get("taeglich_pruefen", True) and (self.update_checked is None or time.time() - self.update_checked > 86400):
                    self.update_checked = time.time()
                    self.update_info = mm_update.check(up.get("repo") or "stecrz/Kontor")
            except Exception:  # pragma: no cover
                log.exception("Zeitplaner")
            self.stop.wait(20)

    def next_run(self) -> Optional[str]:
        z = self.config.get("zeitplan", {}) or {}
        if not z.get("automatisch", True):
            return None
        interval = max(5, int(z.get("intervall_minuten", 30))) * 60
        t = (self.last_run_at + interval) if self.last_run_at else time.time()
        return datetime.fromtimestamp(t).strftime("%H:%M")

    # -- Daten fuer die Oberflaeche ---------------------------------------
    def plan_all(self) -> dict:
        plan = self.store.load("plan.json", {}) or {}
        if "bereiche" in plan:
            return plan
        ds = self.store.load("dataset.json", {}) or {}
        haupt = ds.get("haupt")
        return {"bereiche": ({haupt: plan} if plan and haupt else {})}

    def plan_for(self, bereich: str) -> dict:
        return (self.plan_all().get("bereiche") or {}).get(bereich) or {}

    def dataset(self) -> dict:
        raw = self.store.load("dataset.json", None)
        if raw is None or "bereiche" not in raw:
            return {"leer": True, "einrichtung": not self.config_has_rules(), "version": version()}
        ds = copy.deepcopy(raw)
        immo_res = immo_results(self.config, date.today())
        resolve = self.ledger.resolve if self.ledger is not None else None
        bereiche = ds.get("bereiche") or {}

        def run(bid: str, fremd: dict) -> None:
            b = bereiche[bid]
            if "fehler" in b:
                return
            try:
                apply_plan(b, self.plan_for(bid), self.config, fremd_nw=fremd, immo=immo_for_plan(self.config, bid, immo_res), ledger_resolve=resolve)
            except Exception as e:  # pragma: no cover - fehlerhafte Plandaten duerfen die Anzeige nicht stoppen
                log.exception("Planung fuer Bereich %s", bid)
                b["fehler"] = "Planung fehlgeschlagen: %s" % e

        # 1. Durchgang: alle Bereiche; 2. Durchgang: Bereiche mit Beteiligungs-Verknuepfung auf andere Bereiche
        for bid in bereiche:
            run(bid, {})
        fremd = {bid: (b.get("bilanz", {}).get("projektion", {}).get("nettovermoegen") or {}) for bid, b in bereiche.items() if "fehler" not in b}
        for bid in list(bereiche):
            wcfg = (self.plan_for(bid).get("wertentwicklung") or {})
            if any(isinstance(v, dict) and v.get("bereich") for v in wcfg.values()):
                bereiche[bid] = copy.deepcopy(raw["bereiche"][bid])
                run(bid, fremd)
        ds["einrichtung"] = not self.config_has_rules()
        ds["version"] = version()
        ds["positionen"] = [{"id": r, "name": ROLE_LABELS[r]} for r in ROLES]
        return ds

    def status(self, loopback: bool) -> dict:
        st = self.store.load("state.json", {}) or {}
        bcfg = self.config.get("belege") or {}
        return {
            "version": version(),
            "dienst": {"gestartet": self.started.strftime("%Y-%m-%d %H:%M"), "laeuft": self.running,
                       "naechster_lauf": self.next_run(), "automatisch": (self.config.get("zeitplan") or {}).get("automatisch", True),
                       "intervall_minuten": (self.config.get("zeitplan") or {}).get("intervall_minuten", 30)},
            "moneymoney": {"laeuft": is_running(), "stand": self.ledger_time.strftime("%Y-%m-%d %H:%M") if self.ledger_time else None,
                           "aktualisieren_erlaubt": bool((self.config.get("moneymoney") or {}).get("aktualisieren_erlauben", True)),
                           "kategorisieren_erlaubt": bool((self.config.get("moneymoney") or {}).get("kategorisieren_erlauben", False)),
                           "aktualisiert_um": datetime.fromtimestamp(self.mm_refresh_at).strftime("%H:%M") if self.mm_refresh_at else None},
            "ablage": {"verschluesselt": self.store.encrypted, "schluessel": self.store.key_source, "ordner": self.data_dir},
            "belege": {"ordner": os.path.expanduser(bcfg.get("ordner") or "~/Documents/Kontor-Belege")},
            "probelauf": self.config.get("probelauf", True),
            "letzter_lauf": st.get("letzter_lauf"),
            "letztes_ergebnis": self.last_result,
            "update": self.update_info,
            "touchid": mm_auth.touchid_available() and loopback,
            "lokal": loopback,
        }


# ---------------------------------------------------------------------------
# Excel-Exporte
# ---------------------------------------------------------------------------

def _last(d: dict, months: List[str]):
    for m in reversed(months):
        if d.get(m) is not None:
            return d[m]
    return None


def export_sheets(app: App, was: str, bereich: Optional[str], modus: str) -> List[Sheet]:
    ds = app.dataset()
    if ds.get("leer"):
        raise ValueError("Noch keine Daten -- zuerst einen Lauf ausfuehren.")
    key = bereich or ds.get("haupt") or ""
    b = (ds.get("bereiche") or {}).get(key, {})
    name = (ds.get("bereich_namen") or {}).get(key, "")
    if was in ("bilanz", "kapitalfluss", "planung") and (not b or "fehler" in b):
        raise ValueError("Bereich nicht vorhanden oder fehlerhaft.")

    def columns(include_plan: bool):
        ist = b.get("monate", [])
        plan = b.get("plan_monate", []) if include_plan else []
        allm = ist + plan
        if modus == "jahre":
            years = sorted({m[:4] for m in allm})
            return [(y, [m for m in allm if m.startswith(y)], any(m in plan for m in allm if m.startswith(y))) for y in years]
        return [(m, [m], m in plan) for m in allm]

    if was == "bilanz":
        cols = columns(False)
        rows, bold = [], []
        for r in b.get("bilanz", {}).get("zeilen", []):
            rows.append(["    " * r["ebene"] + r["name"]] + [_last(r["werte"], ms) for _, ms, _p in cols])
            if r["gruppe"]:
                bold.append(len(rows) - 1)
        nw = b.get("bilanz", {}).get("nettovermoegen", {})
        lnw = b.get("bilanz", {}).get("liquides_nettovermoegen", {})
        rows.append(["Nettovermögen"] + [_last(nw, ms) for _, ms, _p in cols]); bold.append(len(rows) - 1)
        rows.append(["davon liquide"] + [_last(lnw, ms) for _, ms, _p in cols])
        return [Sheet("Bilanz " + name, ["Konto"] + [c[0] for c in cols], rows, bold_rows=bold)]

    if was in ("kapitalfluss", "planung"):
        cols = columns(True)
        rows, bold = [], []
        for sek in b.get("kapitalfluss", {}).get("sektionen", []):
            rows.append([sek["name"]] + [None] * len(cols)); bold.append(len(rows) - 1)
            for z in sek["zeilen"]:
                allv = dict(z["werte"]); allv.update((z.get("plan") or {}).get("werte", {}))
                label = "    " + z["zeile"] + ("" if z.get("nw") else "  (Umschichtung)")
                rows.append([label] + [round(sum(allv.get(m, 0.0) for m in ms), 2) for _, ms, _p in cols])
        sums = b.get("kapitalfluss", {}).get("summen", {})
        for k, label in (("Operativ", "Operatives Ergebnis"), ("Cashflow", "Zahlungsfluss gesamt"), ("Nettovermoegen_delta", "Nettovermögensänderung")):
            rows.append([label] + [round(sum((sums.get(m) or {}).get(k, 0.0) for m in ms), 2) for _, ms, _p in cols]); bold.append(len(rows) - 1)
        head = ["Position"] + [c[0] + (" (Plan)" if c[2] else "") for c in cols]
        sheets = [Sheet(("Planung " if was == "planung" else "Kapitalfluss ") + name, head, rows, bold_rows=bold)]
        if was == "planung":
            pr = b.get("bilanz", {}).get("projektion", {})
            pcols = [c for c in cols if c[2]]
            prow, pbold = [], []
            for r in pr.get("zeilen", []):
                prow.append(["    " * r["ebene"] + r["name"]] + [_last(r["werte"], ms) for _, ms, _p in pcols])
                if r.get("gruppe"):
                    pbold.append(len(prow) - 1)
            prow.append(["Nettovermögen (Plan)"] + [_last(pr.get("nettovermoegen", {}), ms) for _, ms, _p in pcols]); pbold.append(len(prow) - 1)
            prow.append(["Liquidität (Plan)"] + [_last(pr.get("liquiditaet", {}), ms) for _, ms, _p in pcols])
            sheets.append(Sheet("Fortschreibung", ["Position"] + [c[0] for c in pcols], prow, bold_rows=pbold))
            P = b.get("plan", {})
            prm = [[k, P.get(k)] for k in PLAN_PARAMS]
            for zn, zc in (P.get("zeilen") or {}).items():
                prm.append(["Zeile " + zn, json.dumps(zc, ensure_ascii=False)])
            sheets.append(Sheet("Parameter", ["Parameter", "Wert"], prm, widths=[40, 60], freeze="A2"))
        return sheets

    if was == "steuer":
        T = ds.get("steuer", {})
        sheets = []
        for ent in T.get("entitaeten", []):
            rows, bold = [], []
            for y, J in sorted(ent["jahre"].items()):
                rows.append([y, "", None, None]); bold.append(len(rows) - 1)
                for pos, p in J["positionen"].items():
                    rows.append(["", pos, p["betrag"], None]); bold.append(len(rows) - 1)
                    for k in p["kategorien"]:
                        rows.append(["", "        " + k["pfad"], k["betrag"], k["anzahl"]])
                for o, d in J["objekte"].items():
                    rows.append(["", "Vermietung " + o, d["ergebnis"], None]); bold.append(len(rows) - 1)
                    for a, v in d["arten"].items():
                        rows.append(["", "        " + a, v, None])
                    for l, v in d["schuldzinsen"].items():
                        rows.append(["", "        Schuldzinsen " + l, v, None])
                    rows.append(["", "        AfA", -abs(d["afa"]) if d["afa"] else 0, None])
                if J["ohne_kategorie"]["anzahl"]:
                    rows.append(["", "Ohne Kategorie", J["ohne_kategorie"]["betrag"], J["ohne_kategorie"]["anzahl"]])
            sheets.append(Sheet(ent["name"], ["Jahr", "Position", "Betrag", "Buchungen"], rows, widths=[8, 56, 16, 12], freeze="A2", bold_rows=bold))
        return sheets or [Sheet("Steuer", ["Hinweis"], [["keine Daten"]])]

    if was == "umsaetze":
        ums = app.store.load("umsaetze.json", []) or []
        if bereich:
            ums = [u for u in ums if u["entitaet"] == bereich]
        counts = Belege(app.store, app.config).counts()
        rows = [[u["datum"], u["konto_name"], u["name"], u["zweck"], u["betrag"], u["kategorie"], counts.get(u["id"], 0), u["id"]] for u in ums]
        return [Sheet("Umsätze " + (name if bereich else ""), ["Datum", "Konto", "Name", "Verwendungszweck", "Betrag", "Kategorie", "Belege", "ID"],
                      rows, widths=[12, 26, 30, 50, 14, 30, 8, 10], freeze="A2")]

    if was == "depots":
        rows, bold = [], []
        for d in ds.get("depots", []):
            rows.append([d["name"], "", "", "", None, None, d["einstand"], d["summe"]]); bold.append(len(rows) - 1)
            for p in d["positionen"]:
                rows.append(["", p["name"], p["isin"], p["klasse"], p["menge"], p["kurs"], p["einstand"], p["wert"]])
        return [Sheet("Depots", ["Depot", "Position", "ISIN", "Klasse", "Menge", "Kurs", "Einstand", "Wert"], rows,
                      widths=[26, 36, 16, 14, 12, 12, 14, 14], freeze="A2", bold_rows=bold)]

    if was == "belege":
        bl = Belege(app.store, app.config)
        names = {k["uuid"]: k["name"] for k in ds.get("konten", [])}
        names.update(ds.get("bereich_namen") or {})
        rows = [[e.get("datum"), e.get("betrag"), e.get("name"), names.get(e.get("konto") or "", ""), names.get(e.get("entitaet") or "", ""),
                 e["pfad"], e.get("notiz", ""), e.get("tx_id")] for e in bl.entries()]
        return [Sheet("Belege", ["Datum", "Betrag", "Name", "Konto", "Bereich", "Datei", "Notiz", "Umsatz-ID"], rows,
                      widths=[12, 14, 30, 26, 20, 50, 30, 10], freeze="A2")]

    if was == "konten":
        rows = [["    " * k["ebene"] + k["name"], k["uuid"],
                 "Gruppe" if k["gruppe"] else ("Depot" if k["depot"] else ("manuell" if k["manuell"] else "Bank")),
                 k["rolle"], k["saldo"], k.get("aktualisiert") or ""] for k in ds.get("konten", [])]
        return [Sheet("Konten", ["Konto", "UUID", "Typ", "Rolle", "Saldo", "aktualisiert"], rows, widths=[46, 38, 10, 16, 16, 18])]
    raise ValueError("Unbekannter Export: %s" % was)


def _parse_balance_csv(text: str) -> Dict[str, Dict[str, float]]:
    """Kontoname -> {JJJJ-MM: Saldo am Monatsende} aus CSV-Text (Langformat oder Matrix), siehe mm_import."""
    return mm_import.balances_from_rows(mm_import.read_csv_rows(text))


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        server_version = "Kontor"
        sys_version = ""

        def log_message(self, fmt, *args):
            log.debug("%s " + fmt, self.client_address[0], *args)

        # -- Hilfen --------------------------------------------------------
        def _remote(self) -> str:
            return self.client_address[0]

        def _loopback(self) -> bool:
            return mm_auth.is_loopback(self._remote())

        def _cookie(self) -> Optional[str]:
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "kontor_session":
                    return v
            return None

        def _session(self) -> Optional[dict]:
            return app.sessions.get(self._cookie())

        def _sec_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "img-src 'self' data: blob:; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")

        def _json(self, code: int, obj: Any, extra: Optional[Dict[str, str]] = None) -> None:
            body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
            self._raw(code, body, "application/json; charset=utf-8", extra)

        def _raw(self, code: int, body: bytes, ctype: str, extra: Optional[Dict[str, str]] = None, cache: str = "no-store") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self._sec_headers()
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _body(self, limit: int = MAX_BODY) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise ValueError("Anfrage zu gross (%d MB, erlaubt %d MB)" % (n // 1048576, limit // 1048576))
            raw = self.rfile.read(n) if n else b""
            obj = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(obj, dict):
                raise ValueError("JSON-Objekt erwartet")
            return obj

        def _set_cookie(self, token: str, clear: bool = False) -> Dict[str, str]:
            secure = "; Secure" if isinstance(self.connection, ssl.SSLSocket) else ""
            if clear:
                return {"Set-Cookie": "kontor_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0" + secure}
            return {"Set-Cookie": "kontor_session=%s; Path=/; HttpOnly; SameSite=Strict" % token + secure}

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if not origin:
                return True
            return urlparse(origin).netloc == (self.headers.get("Host") or "")

        def _static(self, path: str) -> None:
            name = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/app.css": "app.css",
                    "/icon.svg": "icon.svg", "/manifest.webmanifest": "manifest.webmanifest"}.get(path)
            fp = os.path.join(WEB_DIR, name) if name else None
            if not fp or not os.path.exists(fp):
                return self._raw(404, b"nicht gefunden", "text/plain; charset=utf-8")
            with open(fp, "rb") as f:
                body = f.read()
            ctype = {"html": "text/html; charset=utf-8", "js": "application/javascript; charset=utf-8",
                     "css": "text/css; charset=utf-8", "svg": "image/svg+xml", "webmanifest": "application/manifest+json"}[name.rsplit(".", 1)[1]]
            self._raw(200, body, ctype, cache="no-cache")

        # -- GET -----------------------------------------------------------
        def do_GET(self):
            u = urlparse(self.path)
            if not u.path.startswith("/api/"):
                return self._static(u.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/api/session":
                s = self._session()
                rec = app.auth_record()
                return self._json(200, {"angemeldet": s is not None, "csrf": s["csrf"] if s else None,
                                        "einrichtung_noetig": not rec and self._loopback(),
                                        "einrichtung_nur_lokal": not rec and not self._loopback(),
                                        "touchid": mm_auth.touchid_available() and self._loopback(),
                                        "gesperrt_sekunden": app.sessions.locked(self._remote()), "lokal": self._loopback(),
                                        "version": version()})
            s = self._session()
            if s is None:
                return self._json(401, {"fehler": "nicht angemeldet"})
            try:
                return self._get(u.path, q, s)
            except ValueError as e:
                return self._json(400, {"fehler": str(e)})
            except Exception as e:
                log.exception("GET %s", u.path)
                return self._json(500, {"fehler": "Interner Fehler: %s" % e})

        def _get(self, path: str, q: dict, s: dict):
            if path == "/api/status":
                app.reload_config_if_changed()
                return self._json(200, app.status(self._loopback()))
            if path == "/api/dataset":
                return self._json(200, app.dataset())
            if path == "/api/config":
                app.reload_config_if_changed()
                return self._json(200, app.config)
            if path == "/api/plan":
                return self._json(200, app.plan_for(q.get("bereich") or ""))
            if path == "/api/konten":
                ds = app.store.load("dataset.json", {}) or {}
                if app.ledger is not None:
                    return self._json(200, {"konten": account_tree(app.ledger, app.config, None, ds.get("bereiche") or None), "stand": app.ledger_time.isoformat()})
                return self._json(200, {"konten": ds.get("konten", []), "stand": ds.get("erstellt")})
            if path == "/api/kategorien":
                return self._json(200, {"kategorien": app.categories()})
            if path == "/api/runs":
                st = app.store.load("state.json", {}) or {}
                return self._json(200, {"letzter_lauf": st.get("letzter_lauf"), "verlauf": list(reversed(st.get("verlauf", [])))})
            if path == "/api/log":
                n = min(2000, int(q.get("n", "300")))
                try:
                    with open(os.path.join(app.data_dir, "kontor.log"), encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()[-n:]
                except FileNotFoundError:
                    lines = []
                return self._json(200, {"zeilen": [l.rstrip("\n") for l in lines]})
            if path == "/api/umsaetze":
                return self._json(200, self._umsaetze(q))
            if path == "/api/belege":
                bl = Belege(app.store, app.config)
                return self._json(200, {"eintraege": [dict(e, status=file_status(bl.full_path(e))) if e.get("extern") else e for e in reversed(bl.entries())],
                                        "fehlend": bl.check(), "ordner": bl.folder, "dateien": bl.listing() if q.get("dateien") == "1" else []})
            if path == "/api/belege/datei":
                bl = Belege(app.store, app.config)
                e = next((x for x in bl.entries() if x["id"] == q.get("id")), None)
                if e is None:
                    return self._json(404, {"fehler": "Beleg nicht im Index."})
                full = bl.full_path(e)
                if (not e.get("extern") and not full.startswith(os.path.normpath(bl.folder) + os.sep)) or not os.path.isfile(full):
                    return self._json(404, {"fehler": "Datei fehlt oder nicht geladen (iCloud): %s" % e["pfad"]})
                with open(full, "rb") as f:
                    data = f.read()
                ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                disp = "inline" if ctype.startswith(("image/", "application/pdf", "text/")) else "attachment"
                return self._raw(200, data, ctype, {"Content-Disposition": '%s; filename="%s"' % (disp, os.path.basename(full).replace('"', ""))})
            if path == "/api/export/immobilie.xlsx":
                im = next((x for x in app.config.get("immobilien") or [] if str(x.get("id")) == q.get("id")), None)
                if not im:
                    return self._json(404, {"fehler": "Immobilie nicht gefunden."})
                kalks = im.get("kalkulationen") or []
                k = next((x for x in kalks if str(x.get("id")) == q.get("kalkulation")), None) or next((x for x in kalks if x.get("aktiv")), kalks[0] if kalks else None)
                if not k:
                    return self._json(404, {"fehler": "Keine Kalkulation."})
                res = mm_immo.berechne(k.get("eingaben") or {}, date.today())
                data = workbook(mm_immo.sheets(res))
                return self._raw(200, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 {"Content-Disposition": 'attachment; filename="Kontor-Immobilie-%s-%s.xlsx"' % (str(im.get("name") or "Objekt").replace('"', "").replace("/", "-"), date.today().isoformat())})
            if path.startswith("/api/export/"):
                was = path[len("/api/export/"):].replace(".xlsx", "")
                data = workbook(export_sheets(app, was, q.get("bereich"), q.get("modus", "monate")))
                return self._raw(200, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 {"Content-Disposition": 'attachment; filename="Kontor-%s-%s.xlsx"' % (was, date.today().isoformat())})
            if path == "/api/paket/export":
                name = (q.get("name") or "Kontor-Einstellungen").replace('"', "")
                pkg = export_package(app.config, name, strip_uuids=q.get("ohne_uuid") == "1",
                                     plan=(app.plan_all() if q.get("mit_plan") == "1" else None), ledger=app.ledger)
                return self._raw(200, json.dumps(pkg, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="%s.kontor.json"' % name})
            if path == "/api/diagnose":
                txt = diagnose(app.store, app.data_dir, app.config, app.status(self._loopback()), mask_names=q.get("namen") != "1")
                return self._raw(200, txt.encode("utf-8"), "text/plain; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="Kontor-Diagnose-%s.txt"' % date.today().isoformat()})
            if path == "/api/update/status":
                return self._json(200, {"info": app.update_info, "geprueft": app.update_checked, "version": version()})
            if path == "/api/historie":
                return self._json(200, self._historie(q.get("konto") or ""))
            if path == "/api/kategorien/kontor":
                kat = mm_kategorien.load(app.store)
                return self._json(200, {"baum": sorted(kat["baum"], key=lambda k: k["pfad"].lower()), "regeln": kat["regeln"],
                                        "statistik": mm_kategorien.stats(kat, app.ledger) if app.ledger is not None else {},
                                        "einstellungen": app.config.get("kategorien") or {}, "mm_kategorien": [str(c.get("path") or c.get("name") or "") for c in app.categories_raw]})
            if path == "/api/kategorien/offen":
                if app.ledger is None:
                    return self._json(200, {"offen": 0, "gruppen": [], "gruppen_gesamt": 0, "hinweis": "Noch kein Lauf -- MoneyMoney lesen."})
                kat = mm_kategorien.load(app.store)
                bereich_of = {a.uuid: b["id"] for b in bereiche_for(app.ledger, app.config) for a in b["leaves"]}
                return self._json(200, mm_kategorien.open_items(kat, app.ledger, bereich_of, int(q["jahr"]) if q.get("jahr") else None, q.get("bereich") or None,
                                                                 float(q.get("min") or 0), int(q.get("limit") or 300)))
            if path == "/api/immobilien":
                return self._json(200, {"immobilien": app.config.get("immobilien") or [], "ergebnisse": {k: {kk: vv for kk, vv in v.items() if kk != "reihen"}
                                                                                                        for k, v in immo_results(app.config, date.today()).items()}})
            if path == "/api/immobilien/vorlage":
                return self._json(200, {"eingaben": mm_immo.normalize({"name": "Neues Objekt", "uebergang": date.today().replace(day=1).isoformat()})})
            if path == "/api/datei/status":
                full = os.path.expanduser(q.get("pfad") or "")
                st = file_status(full) if full else "fehlt"
                return self._json(200, {"status": st, "groesse": os.path.getsize(full) if st == "ok" else None})
            return self._json(404, {"fehler": "unbekannt"})

        def _historie(self, uuid: str) -> dict:
            st = app.store.load("state.json", {}) or {}
            hist = (st.get("historie") or {}).get(uuid) or {}
            snaps = {mk: v[uuid] for mk, v in (st.get("snapshots") or {}).items() if uuid in v}
            ist: Dict[str, Any] = {}
            quelle = None
            name = ""
            for b in (app.store.load("dataset.json", {}) or {}).get("bereiche", {}).values():
                for r in (b.get("bilanz") or {}).get("zeilen") or []:
                    if r.get("id") == uuid:
                        ist = r.get("werte") or {}; quelle = r.get("verlauf"); name = r.get("name")
            return {"konto": uuid, "name": name, "quelle": quelle, "manuell": hist, "aufgezeichnet": snaps, "ist": ist}

        def _umsaetze(self, q: dict) -> dict:
            ums = app.store.load("umsaetze.json", []) or []
            counts = Belege(app.store, app.config).counts()
            qs = (q.get("q") or "").lower().strip()
            limit = min(5000, int(q.get("limit", "500")))
            out, total = [], 0
            jahre = sorted({t["datum"][:4] for t in ums}, reverse=True)
            for t in ums:
                if q.get("jahr") and not t["datum"].startswith(q["jahr"]):
                    continue
                if q.get("konto") and t["konto"] != q["konto"]:
                    continue
                if q.get("entitaet") and t["entitaet"] != q["entitaet"]:
                    continue
                if q.get("ohne_kategorie") == "1" and t["kategorie"]:
                    continue
                if q.get("ohne_beleg") == "1" and counts.get(t["id"]):
                    continue
                if q.get("mit_beleg") == "1" and not counts.get(t["id"]):
                    continue
                if q.get("richtung") == "aus" and t["betrag"] >= 0:
                    continue
                if q.get("richtung") == "ein" and t["betrag"] < 0:
                    continue
                if q.get("von") and t["datum"] < q["von"]:
                    continue
                if q.get("bis") and t["datum"] > q["bis"]:
                    continue
                if qs and qs not in (t["name"] + " " + t["zweck"] + " " + t["kategorie"] + " " + t["konto_name"] + " " + str(t["betrag"])).lower():
                    continue
                total += 1
                if len(out) < limit:
                    out.append(dict(t, belege=counts.get(t["id"], 0)))
            return {"umsaetze": out, "treffer": total, "gesamt": len(ums), "jahre": jahre}

        # -- POST/PUT ------------------------------------------------------
        def do_POST(self):
            self._mutating()

        def do_PUT(self):
            self._mutating()

        def _mutating(self):
            u = urlparse(self.path)
            if not u.path.startswith("/api/") or not self._origin_ok():
                return self._json(403, {"fehler": "abgelehnt"})
            try:
                body = self._body(MAX_UPLOAD if u.path == "/api/belege/upload" else MAX_BODY)
            except (ValueError, json.JSONDecodeError) as e:
                return self._json(400, {"fehler": "Ungueltige Anfrage: %s" % e})
            remote = self._remote()

            if u.path == "/api/setup":
                if app.auth_record() or not self._loopback():
                    return self._json(403, {"fehler": "Einrichtung nur einmal und nur von diesem Mac aus."})
                err = mm_auth.password_ok(str(body.get("passwort", "")))
                if err:
                    return self._json(400, {"fehler": err})
                app.store.save("auth.json", mm_auth.hash_password(str(body["passwort"])))
                s = app.sessions.create(remote, "passwort")
                log.info("Passwort festgelegt, Einrichtung begonnen")
                return self._json(200, {"ok": True, "csrf": s["csrf"]}, self._set_cookie(s["token"]))
            if u.path == "/api/login":
                wait = app.sessions.locked(remote)
                if wait:
                    return self._json(429, {"fehler": "Zu viele Fehlversuche. Bitte %d Sekunden warten." % wait})
                rec = app.auth_record()
                if not rec:
                    return self._json(403, {"fehler": "Noch kein Passwort festgelegt (Einrichtung am Mac)."})
                if mm_auth.verify_password(str(body.get("passwort", "")), rec):
                    app.sessions.clear_fails(remote)
                    s = app.sessions.create(remote, "passwort")
                    log.info("Anmeldung per Passwort von %s", remote)
                    return self._json(200, {"ok": True, "csrf": s["csrf"]}, self._set_cookie(s["token"]))
                app.sessions.fail(remote)
                time.sleep(0.5)
                log.warning("Fehlgeschlagene Anmeldung von %s", remote)
                return self._json(401, {"fehler": "Passwort falsch."})
            if u.path == "/api/touchid":
                if not self._loopback() or not mm_auth.touchid_available():
                    return self._json(403, {"fehler": "Touch ID nur an diesem Mac."})
                if not app.auth_record():
                    return self._json(403, {"fehler": "Zuerst ein Passwort festlegen."})
                if mm_auth.touchid_verify("Kontor entsperren"):
                    s = app.sessions.create(remote, "touchid")
                    log.info("Anmeldung per Touch ID")
                    return self._json(200, {"ok": True, "csrf": s["csrf"]}, self._set_cookie(s["token"]))
                return self._json(401, {"fehler": "Touch ID nicht bestaetigt."})

            s = self._session()
            if s is None:
                return self._json(401, {"fehler": "nicht angemeldet"})
            if self.headers.get("X-CSRF-Token") != s["csrf"]:
                return self._json(403, {"fehler": "CSRF-Pruefung fehlgeschlagen -- Seite neu laden."})
            try:
                return self._route(u.path, body, s)
            except ValueError as e:
                return self._json(400, {"fehler": str(e)})
            except MoneyMoneyError as e:
                return self._json(502, {"fehler": unavailable_text(e) or ("MoneyMoney-Fehler: %s" % e)})
            except OSError as e:
                return self._json(500, {"fehler": "Dateifehler: %s" % e})
            except Exception as e:
                log.exception("%s %s", self.command, u.path)
                return self._json(500, {"fehler": "Interner Fehler: %s" % e})

        def _is_local(self, s: dict) -> bool:
            return mm_auth.is_loopback(s.get("remote", "")) and self._loopback()

        def _route(self, path: str, body: dict, s: dict):
            local = self._is_local(s)
            if path == "/api/logout":
                app.sessions.drop(s["token"])
                return self._json(200, {"ok": True}, self._set_cookie("", clear=True))
            if path == "/api/lock":
                app.sessions.drop_all()
                return self._json(200, {"ok": True}, self._set_cookie("", clear=True))
            if path == "/api/passwort":
                rec = app.auth_record()
                if not mm_auth.verify_password(str(body.get("alt", "")), rec):
                    return self._json(401, {"fehler": "Altes Passwort falsch."})
                err = mm_auth.password_ok(str(body.get("neu", "")))
                if err:
                    return self._json(400, {"fehler": err})
                app.store.save("auth.json", mm_auth.hash_password(str(body["neu"])))
                log.info("Passwort geaendert")
                return self._json(200, {"ok": True})
            if path == "/api/config":
                cfg = body.get("config")
                if not isinstance(cfg, dict):
                    return self._json(400, {"fehler": "config fehlt"})
                b = (cfg.get("oberflaeche") or {}).get("bind", "127.0.0.1") or "127.0.0.1"
                if not bind_allowed(b):
                    return self._json(400, {"fehler": "Adresse '%s' nicht erlaubt (nur 127.0.0.1 oder Tailscale 100.64.0.0/10)." % b})
                findings = check_config(app.ledger, app.categories_raw, merged_config(cfg)) if app.ledger is not None else []
                if any(f["stufe"] == "fehler" for f in findings) and not body.get("trotzdem"):
                    return self._json(409, {"fehler": "Konfiguration hat Fehler", "befunde": findings})
                app.save_config(cfg)
                log.info("Konfiguration gespeichert (%d Darlehen, %d Beteiligungen, %d Spiegel)",
                         len(app.config.get("darlehen") or []), len(app.config.get("beteiligungen") or []), len(app.config.get("saldo_spiegel") or []))
                return self._json(200, {"ok": True, "befunde": findings, "config": app.config})
            if path == "/api/check":
                ledger, err = app.refresh_ledger()
                if ledger is None:
                    return self._json(200, {"verfuegbar": False, "text": err, "befunde": []})
                findings = check_config(ledger, app.categories_raw, app.config)
                return self._json(200, {"verfuegbar": True, "befunde": findings, "konten": account_tree(ledger, app.config),
                                        "kategorien": app.categories()})
            if path == "/api/run":
                dry = body.get("probelauf")
                if dry is False and not local:
                    return self._json(403, {"fehler": "Scharfe Laeufe nur von diesem Mac aus."})
                if app.running:
                    return self._json(409, {"fehler": "Ein Lauf ist bereits aktiv."})
                threading.Thread(target=app.do_run, args=(dry, bool(body.get("force", True))), daemon=True).start()
                return self._json(202, {"gestartet": True})
            if path == "/api/bericht":
                ledger, err = app.refresh_ledger()
                if ledger is None:
                    return self._json(200, {"ok": False, "text": err})
                st = app.store.load("state.json", {}) or {}
                build_report(app.store, ledger, app.config, st, date.today(), [], app.categories_raw)
                app.store.save("state.json", st)
                return self._json(200, {"ok": True})
            if path == "/api/plan":
                return self._json(200, self._update_plan(body))
            if path == "/api/moneymoney/aktualisieren":
                if not local:
                    return self._json(403, {"fehler": "Nur von diesem Mac aus moeglich."})
                if not (app.config.get("moneymoney") or {}).get("aktualisieren_erlauben", True):
                    return self._json(403, {"fehler": "In den Einstellungen nicht erlaubt (MoneyMoney > Aktualisieren auslösen)."})
                ok, text = refresh_moneymoney()
                if ok:
                    app.mm_refresh_at = time.time()
                    log.info("MoneyMoney-Aktualisierung ausgeloest (%s)", text)
                else:
                    log.warning("MoneyMoney-Aktualisierung nicht moeglich: %s", text)
                return self._json(200, {"ok": ok, "text": text})
            if path == "/api/umsaetze/kategorie":
                if not local:
                    return self._json(403, {"fehler": "Nur von diesem Mac aus moeglich."})
                if not (app.config.get("moneymoney") or {}).get("kategorisieren_erlauben", False):
                    return self._json(403, {"fehler": "Kategorisieren aus Kontor ist in den Einstellungen nicht erlaubt."})
                ids = [int(x) for x in (body.get("ids") or [])][:200]
                kat = str(body.get("kategorie") or "")
                if not ids or not kat:
                    return self._json(400, {"fehler": "ids und kategorie noetig"})
                b = app.bridge_factory(False)
                for i in ids:
                    b.set_transaction(i, category=kat)
                ums = app.store.load("umsaetze.json", []) or []
                for t in ums:
                    if t["id"] in ids:
                        t["kategorie"] = kat.replace("\\", " / ")
                app.store.save("umsaetze.json", ums)
                log.info("%d Umsatz/Umsaetze kategorisiert", len(ids))
                return self._json(200, {"ok": True, "anzahl": len(ids)})
            if path.startswith("/api/belege/"):
                return self._belege(path, body, local)
            if path == "/api/paket/import":
                pkg = body.get("paket")
                if isinstance(pkg, str):
                    pkg = json.loads(pkg)
                cfg, unresolved, report = import_package(app.config, pkg, app.ledger, body.get("modus") or "ergaenzen", body.get("zuordnung") or {})
                if unresolved and not body.get("trotzdem"):
                    return self._json(200, {"ok": False, "unaufgeloest": unresolved, "bericht": report,
                                            "hinweis": "Konten zuordnen oder 'trotzdem uebernehmen' (Referenzen bleiben dann als Name stehen)."})
                findings = check_config(app.ledger, app.categories_raw, cfg) if app.ledger is not None else []
                app.save_config(cfg)
                if pkg.get("plan") and body.get("mit_plan"):
                    app.store.save("plan.json", pkg["plan"])
                log.info("Einstellungspaket '%s' uebernommen (%s)", pkg.get("name"), body.get("modus") or "ergaenzen")
                return self._json(200, {"ok": True, "bericht": report, "befunde": findings, "config": app.config})
            if path == "/api/update/pruefen":
                app.update_info = mm_update.check((app.config.get("updates") or {}).get("repo") or "stecrz/Kontor")
                app.update_checked = time.time()
                return self._json(200, {"info": app.update_info, "version": version()})
            if path == "/api/update/installieren":
                if not local:
                    return self._json(403, {"fehler": "Updates nur von diesem Mac aus."})
                res = mm_update.install((app.config.get("updates") or {}).get("repo") or "stecrz/Kontor", restart=True)
                if res.get("ok"):
                    log.info("Update installiert: %s", res.get("version"))
                return self._json(200, res)
            if path == "/api/historie":
                return self._json(200, self._historie_set(body))
            if path == "/api/historie/import":
                return self._json(200, self._historie_import(body))
            if path.startswith("/api/kategorien/"):
                return self._kategorien(path, body, local)
            if path.startswith("/api/immobilien"):
                return self._immobilien(path, body)
            if path.startswith("/api/datei/"):
                return self._datei(path, body, local)
            if path == "/api/bericht/neu":
                ok, err = app.rebuild_report()
                return self._json(200, {"ok": ok, "text": err})
            if path == "/api/tm-ausschluss":
                flag = "addexclusion" if body.get("ausschliessen") else "removeexclusion"
                try:
                    r = subprocess.run(["tmutil", flag, app.data_dir], capture_output=True, text=True, timeout=30)
                    return self._json(200, {"ok": r.returncode == 0, "text": (r.stdout + r.stderr).strip()})
                except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                    return self._json(200, {"ok": False, "text": str(e)})
            return self._json(404, {"fehler": "unbekannt"})

        def _belege(self, path: str, body: dict, local: bool):
            bl = Belege(app.store, app.config)
            ums = {t["id"]: t for t in (app.store.load("umsaetze.json", []) or [])}
            ds = app.store.load("dataset.json", {}) or {}
            names = {k["uuid"]: k["name"] for k in ds.get("konten", [])}
            names.update(ds.get("bereich_namen") or {})

            def tx_of(body):
                tid = body.get("tx_id")
                if tid in (None, ""):
                    return None
                t = ums.get(int(tid))
                if t is None:
                    raise ValueError("Umsatz %s nicht gefunden (Liste veraltet? Lauf ausfuehren)." % tid)
                return dict(t, entitaet_name=names.get(t["entitaet"], ""))

            if path == "/api/belege/upload":
                try:
                    data = base64.b64decode(str(body.get("inhalt") or ""), validate=True)
                except Exception:
                    raise ValueError("Dateiinhalt unlesbar (Base64).")
                e = bl.add_bytes(tx_of(body), str(body.get("datei_name") or "Beleg"), data, str(body.get("notiz") or ""))
                if (app.config.get("belege") or {}).get("kommentar_schreiben") and e.get("tx_id") is not None and local:
                    try:
                        app.bridge_factory(False).set_transaction(e["tx_id"], comment="Beleg: " + e["pfad"])
                    except MoneyMoneyError as ex:
                        log.warning("Belegverweis nicht in MoneyMoney geschrieben: %s", ex)
                log.info("Beleg abgelegt (%d KB)", len(data) // 1024)
                return self._json(200, {"ok": True, "eintrag": e})
            if path == "/api/belege/verknuepfen":
                if body.get("extern"):
                    e = dict(bl.link_external(tx_of(body), str(body.get("pfad") or ""), str(body.get("notiz") or "")))
                    e["status"] = file_status(e["pfad"])
                else:
                    e = bl.link_existing(tx_of(body), str(body.get("pfad") or ""), str(body.get("notiz") or ""))
                return self._json(200, {"ok": True, "eintrag": e})
            if path == "/api/belege/entfernen":
                ok = bl.remove(str(body.get("id") or ""), bool(body.get("datei_loeschen")))
                return self._json(200, {"ok": ok})
            if path == "/api/belege/aendern":
                fields = {k: v for k, v in body.items() if k in ("notiz", "name", "datum", "betrag")}
                if "tx_id" in body:
                    t = tx_of(body)
                    fields.update({"tx_id": t["id"], "konto": t["konto"], "entitaet": t["entitaet"]} if t else {"tx_id": None})
                e = bl.update(str(body.get("id") or ""), **fields)
                return self._json(200, {"ok": e is not None, "eintrag": e})
            if path == "/api/belege/oeffnen":
                if not local:
                    return self._json(403, {"fehler": "Nur von diesem Mac aus moeglich."})
                err = bl.ensure_folder()
                if err:
                    return self._json(500, {"fehler": err})
                target = bl.folder
                if body.get("pfad"):
                    cand = os.path.normpath(os.path.join(bl.folder, str(body["pfad"])))
                    if cand.startswith(os.path.normpath(bl.folder) + os.sep) and os.path.exists(cand):
                        target = cand
                    elif os.path.isabs(str(body["pfad"])) and os.path.exists(str(body["pfad"])):
                        target = os.path.normpath(str(body["pfad"]))
                if sys.platform != "darwin":
                    return self._json(400, {"fehler": "Oeffnen im Finder nur unter macOS."})
                subprocess.Popen(["open", "-R", target] if os.path.isfile(target) else ["open", target])
                return self._json(200, {"ok": True})
            if path == "/api/belege/export":
                target = bl.export_zip(str(body.get("jahr") or "") or None, str(body.get("entitaet") or "") or None, names)
                if local and sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", target])
                log.info("Belegexport erstellt")
                return self._json(200, {"ok": True, "datei": target})
            return self._json(404, {"fehler": "unbekannt"})

        def _historie_set(self, body: dict) -> dict:
            uuid = str(body.get("konto") or "")
            if not uuid:
                raise ValueError("konto fehlt")
            st = app.store.load("state.json", {}) or {}
            hist = st.setdefault("historie", {}).setdefault(uuid, {})
            n = 0
            for mk, v in (body.get("werte") or {}).items():
                mk = str(mk)[:7]
                if len(mk) != 7 or not mk[:4].isdigit() or not mk[5:7].isdigit():
                    continue
                if v in (None, ""):
                    hist.pop(mk, None)
                else:
                    hist[mk] = float(str(v).replace(".", "").replace(",", ".")) if isinstance(v, str) and "," in str(v) else float(v)
                n += 1
            if body.get("loeschen"):
                st["historie"].pop(uuid, None)
            if not hist:
                st["historie"].pop(uuid, None)
            app.store.save("state.json", st)
            if body.get("quelle") in ("umsaetze", "stand"):
                cfg = copy.deepcopy(app.config)
                cfg.setdefault("bilanz", {}).setdefault("verlauf", {})
                ref = next((("%s | %s" % (k["uuid"], k["name"])) for k in (app.store.load("dataset.json", {}) or {}).get("konten", []) if k["uuid"] == uuid), uuid)
                for k in list(cfg["bilanz"]["verlauf"]):
                    if k.split("|", 1)[0].strip() == uuid:
                        cfg["bilanz"]["verlauf"].pop(k)
                cfg["bilanz"]["verlauf"][ref] = body["quelle"]
                app.save_config(cfg)
            ok, err = app.rebuild_report()
            log.info("Verlauf fuer Konto %s: %d Monat(e) geaendert", uuid[:8], n)
            return {"ok": True, "bericht": ok, "text": err, "historie": self._historie(uuid)}

        def _historie_import(self, body: dict) -> dict:
            """Saldenverlauf aus CSV-Text oder Datei (CSV/XLSX): Langformat (Datum, Konto, Saldo), Matrix oder transponiert.
            Vorschau mit Kontovorschlaegen; 'zuordnung' (Tabellenname -> Kontoreferenz) und 'uebernehmen' schreiben die Werte."""
            konto = str(body.get("konto") or "")
            mapping = body.get("zuordnung") or {}
            hints: List[str] = []
            if body.get("datei"):
                try:
                    raw = base64.b64decode(str(body["datei"]))
                except (binascii.Error, ValueError):
                    raise ValueError("Dateiinhalt unlesbar (Base64).")
                if len(raw) > 30 * 1024 * 1024:
                    raise ValueError("Datei zu gross (max. 30 MB).")
                parsed, hints = mm_import.balances_from_file(str(body.get("name") or ""), raw)
            else:
                parsed = _parse_balance_csv(str(body.get("csv") or ""))
            if not parsed:
                raise ValueError("Keine Werte erkannt. Erwartet: Datum, Konto (optional), Saldo -- oder eine Tabelle mit Stichtagen in einer Zeile oder Spalte.")
            konten = {k["name"]: k["uuid"] for k in (app.store.load("dataset.json", {}) or {}).get("konten", []) if not k["gruppe"]}
            if app.ledger is not None:
                konten.update({a.name: a.uuid for a in app.ledger.accounts.values() if not a.group})
            uuid_name = {v: k for k, v in konten.items()}
            preview = []
            assign: Dict[str, Dict[str, float]] = {}
            for name, months in sorted(parsed.items()):
                if konto and (name == "" or len(parsed) == 1):
                    target = konto
                elif name in mapping:
                    target = (mapping.get(name) or "").split("|", 1)[0].strip() or None
                else:
                    target = konten.get(name) or mm_import.match_account(name, konten)
                preview.append({"name": name or "(ohne Konto)", "uuid": target, "konto": uuid_name.get(target or "", ""), "anzahl": len(months), "von": min(months), "bis": max(months),
                                "sicher": bool(name in konten or name in mapping or (konto and (name == "" or len(parsed) == 1)))})
                if target:
                    assign.setdefault(target, {}).update(months)
            if not body.get("uebernehmen"):
                return {"ok": True, "vorschau": preview, "hinweise": hints}
            st = app.store.load("state.json", {}) or {}
            h = st.setdefault("historie", {})
            total = 0
            for uuid, months in assign.items():
                if body.get("nur_luecken"):
                    months = {mk: v for mk, v in months.items() if mk not in (h.get(uuid) or {})}
                h.setdefault(uuid, {}).update(months)
                total += len(months)
            app.store.save("state.json", st)
            ok, err = app.rebuild_report()
            log.info("Verlaufsimport: %d Werte fuer %d Konto/Konten", total, len(assign))
            return {"ok": True, "uebernommen": total, "konten": len(assign), "bericht": ok, "text": err, "vorschau": preview, "hinweise": hints}

        def _kategorien(self, path: str, body: dict, local: bool):
            kat = mm_kategorien.load(app.store)
            if path == "/api/kategorien/zuordnen":
                ids = [int(x) for x in (body.get("ids") or [])][:5000]
                pfad = str(body.get("kategorie") or "")
                if not ids:
                    raise ValueError("Keine Umsaetze angegeben.")
                rule = None
                if body.get("regel") and pfad:
                    r = dict(body["regel"]); r["kategorie"] = pfad
                    rule = mm_kategorien.add_rule(kat, r)
                n = mm_kategorien.assign(kat, ids, pfad, "manuell", rule["id"] if rule else None)
                mm_written = 0
                if body.get("in_moneymoney") and pfad and local and (app.config.get("moneymoney") or {}).get("kategorisieren_erlauben"):
                    if pfad.replace(" / ", "\\") in {str(c.get("path") or "") for c in app.categories_raw}:
                        try:
                            b = app.bridge_factory(False)
                            for i in ids[:200]:
                                b.set_transaction(i, category=pfad.replace(" / ", "\\"))
                                mm_written += 1
                        except MoneyMoneyError as e:
                            log.warning("Kategorie in MoneyMoney setzen: %s", e)
                if rule and app.ledger is not None:
                    mm_kategorien.auto_assign(kat, app.ledger, overwrite_mm=bool((app.config.get("kategorien") or {}).get("mm_ueberschreiben")))
                mm_kategorien.save(app.store, kat)
                ok, err = app.rebuild_report() if app.ledger is not None else (False, None)
                log.info("%d Umsatz/Umsaetze in Kontor zugeordnet%s", n, " (Regel angelegt)" if rule else "")
                return self._json(200, {"ok": True, "anzahl": n, "regel": rule, "in_moneymoney": mm_written, "bericht": ok, "text": err})
            if path == "/api/kategorien/regel":
                if body.get("loeschen"):
                    kat["regeln"] = [r for r in kat["regeln"] if r.get("id") != str(body.get("loeschen"))]
                    for tid, z in list(kat["zuordnung"].items()):
                        if z.get("r") == str(body.get("loeschen")) and z.get("q") == "regel":
                            del kat["zuordnung"][tid]
                else:
                    mm_kategorien.add_rule(kat, body.get("regel") or {})
                if app.ledger is not None:
                    mm_kategorien.auto_assign(kat, app.ledger, overwrite_mm=bool((app.config.get("kategorien") or {}).get("mm_ueberschreiben")))
                mm_kategorien.save(app.store, kat)
                ok, err = app.rebuild_report() if app.ledger is not None else (False, None)
                return self._json(200, {"ok": True, "regeln": kat["regeln"], "bericht": ok})
            if path == "/api/kategorien/lernen":
                if app.ledger is None:
                    return self._json(200, {"ok": False, "text": "Noch kein Lauf -- MoneyMoney lesen."})
                st = mm_kategorien.learn(kat, app.ledger)
                n = mm_kategorien.auto_assign(kat, app.ledger, overwrite_mm=bool(body.get("mm_ueberschreiben") or (app.config.get("kategorien") or {}).get("mm_ueberschreiben")))
                mm_kategorien.save(app.store, kat)
                ok, err = app.rebuild_report()
                return self._json(200, {"ok": True, "gelernt": st, "zugeordnet": n, "bericht": ok})
            if path == "/api/kategorien/baum":
                aktion = body.get("aktion")
                if aktion == "anlegen":
                    mm_kategorien.ensure_category(kat, str(body.get("pfad") or ""), sektion=body.get("sektion"))
                elif aktion == "umbenennen":
                    mm_kategorien.rename_category(kat, str(body.get("pfad") or ""), str(body.get("neu") or ""))
                elif aktion == "loeschen":
                    mm_kategorien.delete_category(kat, str(body.get("pfad") or ""), body.get("ersatz") or None)
                elif aktion == "mm_uebernehmen":
                    mm_kategorien.seed_from_moneymoney(kat, app.categories_raw)
                else:
                    raise ValueError("Unbekannte Aktion.")
                mm_kategorien.save(app.store, kat)
                ok, err = app.rebuild_report() if (app.ledger is not None and aktion != "anlegen") else (False, None)
                return self._json(200, {"ok": True, "baum": sorted(kat["baum"], key=lambda k: k["pfad"].lower()), "bericht": ok})
            if path == "/api/kategorien/einstellungen":
                cfg = copy.deepcopy(app.config)
                kc = cfg.setdefault("kategorien", {})
                for k in ("aktiv", "lernen", "mm_ueberschreiben"):
                    if k in body:
                        kc[k] = bool(body[k])
                app.save_config(cfg)
                ok, err = app.rebuild_report() if app.ledger is not None else (False, None)
                return self._json(200, {"ok": True, "einstellungen": kc, "bericht": ok})
            return self._json(404, {"fehler": "unbekannt"})

        def _immobilien(self, path: str, body: dict):
            if path == "/api/immobilien/berechnen":
                res = mm_immo.berechne(body.get("eingaben") or {}, date.today())
                res.pop("monate", None) if body.get("ohne_monate") else None
                return self._json(200, res)
            cfg = copy.deepcopy(app.config)
            lst = cfg.setdefault("immobilien", [])
            aktion = str(body.get("aktion") or "")
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            im = next((x for x in lst if str(x.get("id")) == str(body.get("id"))), None)
            if aktion == "anlegen":
                iid = "im%d" % (max([int(str(x.get("id"))[2:]) for x in lst if str(x.get("id", "")).startswith("im") and str(x.get("id"))[2:].isdigit()] + [0]) + 1)
                im = {"id": iid, "name": str(body.get("name") or "Neues Objekt"), "bereich": body.get("bereich") or "", "kategorie": body.get("kategorie") or "",
                      "objekt_konto": body.get("objekt_konto") or "", "darlehen_konten": {}, "in_planung": False, "kalkulationen": [], "dokumente": [], "notizen": ""}
                lst.append(im)
            elif im is None:
                return self._json(404, {"fehler": "Immobilie nicht gefunden."})
            elif aktion == "loeschen":
                lst.remove(im)
                app.save_config(cfg)
                log.info("Immobilie geloescht")
                return self._json(200, {"ok": True})
            if aktion in ("anlegen", "aendern"):
                for k in ("name", "bereich", "kategorie", "objekt_konto", "notizen"):
                    if k in body:
                        im[k] = body[k]
                if "in_planung" in body:
                    im["in_planung"] = bool(body["in_planung"])
                if isinstance(body.get("darlehen_konten"), dict):
                    im["darlehen_konten"] = {str(k): v for k, v in body["darlehen_konten"].items()}
            elif aktion == "kalkulation_speichern":
                k = body.get("kalkulation") or {}
                eing = k.get("eingaben") or {}
                mm_immo.berechne(eing, date.today())          # validiert
                kid = str(k.get("id") or "")
                existing = next((x for x in im["kalkulationen"] if str(x.get("id")) == kid), None) if kid else None
                if existing:
                    existing["eingaben"] = eing; existing["name"] = k.get("name") or existing.get("name"); existing["geaendert"] = now
                else:
                    kid = "k%d" % (len(im["kalkulationen"]) + 1 + int(datetime.now().timestamp()) % 1000)
                    im["kalkulationen"].append({"id": kid, "name": k.get("name") or ("Kalkulation %d" % (len(im["kalkulationen"]) + 1)),
                                                "erstellt": now, "aktiv": not im["kalkulationen"], "eingaben": eing})
                if k.get("aktiv"):
                    for x in im["kalkulationen"]:
                        x["aktiv"] = str(x.get("id")) == kid
            elif aktion == "kalkulation_loeschen":
                im["kalkulationen"] = [x for x in im["kalkulationen"] if str(x.get("id")) != str(body.get("kalkulation_id"))]
                if im["kalkulationen"] and not any(x.get("aktiv") for x in im["kalkulationen"]):
                    im["kalkulationen"][0]["aktiv"] = True
            elif aktion == "kalkulation_aktiv":
                for x in im["kalkulationen"]:
                    x["aktiv"] = str(x.get("id")) == str(body.get("kalkulation_id"))
            elif aktion == "dokument_hinzufuegen":
                pfad = os.path.expanduser(str(body.get("pfad") or ""))
                if not pfad or file_status(pfad) == "fehlt":
                    return self._json(400, {"fehler": "Datei nicht gefunden: %s" % pfad})
                im.setdefault("dokumente", []).append({"id": "d%d" % int(datetime.now().timestamp() * 1000 % 10 ** 9), "titel": body.get("titel") or os.path.basename(pfad),
                                                       "pfad": pfad, "art": body.get("art") or "", "hinzugefuegt": now})
            elif aktion == "dokument_entfernen":
                im["dokumente"] = [d for d in im.get("dokumente") or [] if str(d.get("id")) != str(body.get("dokument_id"))]
            else:
                return self._json(400, {"fehler": "Unbekannte Aktion."})
            app.save_config(cfg)
            log.info("Immobilie %s: %s", im.get("id"), aktion)
            ok, err = app.rebuild_report() if app.ledger is not None else (False, None)
            return self._json(200, {"ok": True, "immobilie": im, "bericht": ok})

        def _datei(self, path: str, body: dict, local: bool):
            if not local:
                return self._json(403, {"fehler": "Dateizugriff nur von diesem Mac aus."})
            if sys.platform != "darwin":
                return self._json(400, {"fehler": "Nur unter macOS."})
            if path == "/api/datei/waehlen":
                art = body.get("art") or "datei"
                prompt = str(body.get("prompt") or "Datei wählen").replace('"', "")
                script = ('POSIX path of (choose folder with prompt "%s")' if art == "ordner" else 'POSIX path of (choose file with prompt "%s")') % prompt
                try:
                    r = subprocess.run(["osascript", "-e", 'tell application "System Events" to activate', "-e", script], capture_output=True, text=True, timeout=600)
                except subprocess.TimeoutExpired:
                    return self._json(200, {"ok": False, "text": "Zeitueberschreitung."})
                if r.returncode != 0:
                    return self._json(200, {"ok": False, "text": "Abgebrochen."})
                p = r.stdout.strip().rstrip("/") if art == "ordner" else r.stdout.strip()
                return self._json(200, {"ok": True, "pfad": p, "name": os.path.basename(p), "status": file_status(p) if art != "ordner" else "ok",
                                        "groesse": os.path.getsize(p) if os.path.isfile(p) else None})
            pfad = os.path.expanduser(str(body.get("pfad") or ""))
            if not pfad or not os.path.isabs(pfad):
                return self._json(400, {"fehler": "Pfad fehlt."})
            if path == "/api/datei/oeffnen":
                st = file_status(pfad)
                if st == "fehlt":
                    return self._json(404, {"fehler": "Datei nicht gefunden."})
                subprocess.Popen(["open", pfad])
                return self._json(200, {"ok": True, "status": st})
            if path == "/api/datei/zeigen":
                if not os.path.exists(pfad) and file_status(pfad) == "fehlt":
                    return self._json(404, {"fehler": "Datei nicht gefunden."})
                subprocess.Popen(["open", "-R", pfad])
                return self._json(200, {"ok": True})
            if path == "/api/datei/laden":
                try:
                    r = subprocess.run(["brctl", "download", pfad], capture_output=True, text=True, timeout=30)
                    return self._json(200, {"ok": r.returncode == 0, "text": (r.stdout + r.stderr).strip()})
                except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                    return self._json(200, {"ok": False, "text": str(e)})
            return self._json(404, {"fehler": "unbekannt"})

        def _update_plan(self, body: dict) -> dict:
            plan_all = app.plan_all()
            bereich = str(body.get("bereich") or (app.store.load("dataset.json", {}) or {}).get("haupt") or "")
            if not bereich:
                raise ValueError("Kein Bereich angegeben.")
            plan = plan_all["bereiche"].setdefault(bereich, {})
            if body.get("zuruecksetzen"):
                plan_all["bereiche"][bereich] = {}
                app.store.save("plan.json", plan_all)
                return {"ok": True, "plan": {}}
            if "parameter" in body:
                for k, v in (body["parameter"] or {}).items():
                    if k in PLAN_PARAMS:
                        if v in (None, ""):
                            plan.pop(k, None)
                        else:
                            plan[k] = v
            if "darlehen" in body:
                d = plan.setdefault("darlehen", {})
                for name, params in (body["darlehen"] or {}).items():
                    if params is None:
                        d.pop(name, None)
                    else:
                        d[name] = {k: v for k, v in params.items() if k in ("zins_prozent_pa", "modell", "zahlung") and v not in (None, "")}
                        if not d[name]:
                            d.pop(name, None)
            if "wertentwicklung" in body:
                w = plan.setdefault("wertentwicklung", {})
                for name, params in (body["wertentwicklung"] or {}).items():
                    if params is None:
                        w.pop(name, None)
                    else:
                        entry = {k: float(v) for k, v in params.items() if k in ("prozent_pa", "basis", "anteil") and v not in (None, "")}
                        if params.get("bereich"):
                            entry["bereich"] = str(params["bereich"])
                            entry.setdefault("anteil", 1.0)
                        w[name] = entry
                        if not w[name]:
                            w.pop(name, None)
            if "ereignis" in body:
                ev = body["ereignis"] or {}
                lst = plan.setdefault("ereignisse", [])
                if ev.get("loeschen"):
                    plan["ereignisse"] = [e for e in lst if str(e.get("id")) != str(ev.get("id"))]
                else:
                    clean = {"id": str(ev.get("id") or ("e%d" % int(time.time() * 1000 % 10 ** 9))), "text": str(ev.get("text") or "Ereignis")[:80],
                             "monat": str(ev.get("monat") or "")[:7], "betrag": float(str(ev.get("betrag") or 0).replace(",", ".")),
                             "art": ev.get("art") if ev.get("art") in ("umschichtung", "einnahme", "ausgabe") else "umschichtung",
                             "von": ev.get("von") or None, "nach": ev.get("nach") or None,
                             "wiederholung": ev.get("wiederholung") if ev.get("wiederholung") in ("einmalig", "monatlich", "quartal", "jaehrlich") else "einmalig",
                             "bis": (str(ev.get("bis") or "")[:7] or None), "aktiv": ev.get("aktiv", True)}
                    if len(clean["monat"]) != 7:
                        raise ValueError("Monat fehlt (JJJJ-MM).")
                    idx = next((i for i, e in enumerate(lst) if str(e.get("id")) == clean["id"]), None)
                    if idx is None:
                        lst.append(clean)
                    else:
                        lst[idx] = clean
                if not plan.get("ereignisse"):
                    plan.pop("ereignisse", None)
            key = str(body.get("zeile") or "")
            if key:
                zeilen = plan.setdefault("zeilen", {})
                row = zeilen.setdefault(key, {})
                if "monat" in body:
                    werte = row.setdefault("werte", {})
                    v = str(body.get("wert", "")).strip().replace(",", ".")
                    if v == "":
                        werte.pop(body["monat"], None)
                    else:
                        werte[body["monat"]] = float(v)
                    if not werte:
                        row.pop("werte", None)
                if body.get("alle_ueberschreibungen_loeschen"):
                    row.pop("werte", None)
                if "methode" in body:
                    if body["methode"]:
                        row["methode"] = str(body["methode"])
                    else:
                        row.pop("methode", None)
                for fld, dst in (("betrag", "betrag"), ("steigerung", "steigerung_prozent_pa")):
                    if fld in body:
                        v = str(body.get(fld, "")).strip().replace(",", ".")
                        if v == "":
                            row.pop(dst, None)
                        else:
                            row[dst] = float(v)
                if not row:
                    zeilen.pop(key, None)
                if not zeilen:
                    plan.pop("zeilen", None)
            app.store.save("plan.json", plan_all)
            return {"ok": True, "plan": plan_all["bereiche"].get(bereich, {})}

    return H


def serve(app: App) -> None:
    ui = app.config.get("oberflaeche", {}) or {}
    host = ui.get("bind") or "127.0.0.1"
    if not bind_allowed(host):
        log.error("Bind-Adresse %s nicht erlaubt -- verwende 127.0.0.1", host)
        host = "127.0.0.1"
    port = int(ui.get("port") or 8765)
    ThreadingHTTPServer.allow_reuse_address = True
    ThreadingHTTPServer.daemon_threads = True
    try:
        srv = ThreadingHTTPServer((host, port), make_handler(app))
    except OSError as e:
        log.error("Port %d auf %s nicht nutzbar (%s) -- laeuft Kontor schon? Port in den Einstellungen aendern.", port, host, e)
        raise SystemExit(2)
    scheme = "http"
    if ui.get("tls_cert") and ui.get("tls_key"):
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(ui["tls_cert"], ui["tls_key"])
            srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
            scheme = "https"
        except (OSError, ssl.SSLError) as e:
            log.error("TLS nicht aktiviert (%s) -- weiter ohne TLS", e)
    threading.Thread(target=app.scheduler, daemon=True).start()
    log.info("Kontor %s: Oberflaeche unter %s://%s:%d/ (Ablage %s)", version(), scheme, host, port,
             "verschluesselt" if app.store.encrypted else "KLARTEXT")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop.set()
        srv.server_close()
