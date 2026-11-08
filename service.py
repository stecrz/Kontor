"""Kontor-Dienst: Web-Oberflaeche (API + statische Dateien) und Zeitplaner in einem Prozess.

Sicherheit:
  * bindet an 127.0.0.1 (oder eine Tailscale-Adresse 100.64.0.0/10, wenn eingestellt); nie 0.0.0.0
  * Anmeldung mit Passwort (oder Touch ID von diesem Mac aus), Sitzungscookie HttpOnly/SameSite=Strict,
    CSRF-Token fuer jede aendernde Anfrage, Origin-Pruefung, Ratenbegrenzung, Leerlaufsperre
  * CSP ohne Fremdquellen; einzige Netzverbindung: die abschaltbare Update-Pruefung bei GitHub
  * Schreibzugriffe auf MoneyMoney nur ueber kern (manuelle Konten, Allowlist der Bruecke);
    Kategorisieren und das Ausloesen der Aktualisierung nur, wenn in den Einstellungen erlaubt
  * Scharfe Laeufe, Updates, Dateizugriffe (Belegordner oeffnen) nur von diesem Mac aus
"""
from __future__ import annotations

import base64
import bisect
import binascii
import copy
import ipaddress
import json
import re
import secrets
import logging
import mimetypes
import os
import ssl
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import auth
import i18n
import mm_categories
import mm_history
import realestate
import history_import
import categorize
import updates
from receipts import Belege, file_status
from mm_bridge import Bridge, MoneyMoneyError, MoneyMoneyLocked, MoneyMoneyNotRunning, is_running
from core import (RUN_LOCK, account_sig, account_tree, bereiche_for, build_report, abruf_arten, check_config, diagnose, earliest_needed, export_package, fetch, freeze_assignments, immo_for_plan, merge_snapshots, record_snapshot,
                     immo_results, import_package, ledger_fp, merged_config, run_once, unavailable_text, version, version_on_disk, MM_HISTORY_FILE)
from model import Ledger, Tx, accounts_from_export, ledger_from_bytes, ledger_to_bytes
from report import ROLES, account_balance_series, account_months, apply_plan, role_label
from storage import Store
from excel import Sheet, workbook
from i18n import tr

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


def balance_lookup(ledger: Ledger) -> Callable[[str, date, bool], Optional[float]]:
    """Saldo eines Kontos am Ende eines Tages aus den Umsaetzen (heutiger Saldo minus alle spaeteren gebuchten Umsaetze),
    nach Buchungs- oder Wertstellungsdatum; None fuer Depots und unbekannte Konten."""
    idx: Dict[Tuple[str, bool], Tuple[List[date], List[float]]] = {}
    per: Dict[str, List[Tx]] = {}
    for t in ledger.txs:
        if t.booked:
            per.setdefault(t.account_uuid, []).append(t)
    for u, txs in per.items():
        for by_value in (False, True):
            pts = sorted(((t.value_date or t.booking_date) if by_value else t.booking_date, t.amount) for t in txs)
            cum = [0.0]
            for _d, a in pts:
                cum.append(cum[-1] + a)
            idx[(u, by_value)] = ([d for d, _a in pts], cum)

    def balance_at(uuid: str, day: date, by_value: bool = False) -> Optional[float]:
        acc = ledger.accounts.get(uuid)
        if acc is None or acc.portfolio or acc.group:
            return None
        dates, cum = idx.get((uuid, by_value), ([], [0.0]))
        return round(acc.balance - (cum[-1] - cum[bisect.bisect_right(dates, day)]), 2)
    return balance_at


class App:
    def __init__(self, store: Store, data_dir: str, bridge_factory=Bridge):
        self.store = store
        self.data_dir = data_dir
        self.bridge_factory = bridge_factory
        self.config = merged_config(store.load("config.json", {}) or {})
        self.apply_language()
        self.sessions = auth.Sessions(idle_minutes=int(self.config["oberflaeche"].get("sperre_minuten", 15)))
        self.ledger: Optional[Ledger] = None            # letzter Stand aus MoneyMoney
        self.ledger_time: Optional[datetime] = None
        self.umsaetze: Optional[list] = None            # kompakte Umsatzliste des letzten Berichts (sonst aus umsaetze.json)
        st = store.load("state.json", {}) or {}
        self.categories_raw: list = mm_categories.with_paths(st.get("kategorien_roh") or [])
        self.started = datetime.now()
        self.instance = secrets.token_hex(6)              # changes with every (re)start; the page waits for a new one after a restart
        self.last_run_at: Optional[float] = None
        self.last_result: Optional[dict] = None
        self.running = False
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.update_info: Optional[dict] = None
        self.update_checked: Optional[float] = None
        self.tls_ctx: Optional[ssl.SSLContext] = None
        self.tls_checked: Optional[float] = None
        self._bankabruf_cache: Tuple[Any, Optional[dict]] = (None, None)
        self._cfg_mtime = self._config_mtime()
        # Berichtsneubau laeuft im Hintergrund: mehrere Anstoesse werden zu einem Lauf zusammengefasst
        self.rebuild_cv = threading.Condition()
        self.rebuild_pending = False
        self.rebuild_running = False
        self.rebuild_reasons: List[str] = []
        self.bericht: dict = {"stand": None, "dauer": None, "fehler": None, "grund": None}
        self.bericht_fortschritt: dict = {"anteil": 0.0, "schritt": ""}
        self.check_lock = threading.Lock()
        self.ledger_cache_fp: Optional[str] = None
        self.ledger_from_cache = False
        threading.Thread(target=self._load_ledger_cache, name="kontor-cache", daemon=True).start()
        self.mmh: dict = {"laeuft": False, "schritt": None, "ergebnis": None}   # Kontostaende aus MoneyMoney einlesen
        if sys.platform == "darwin":          # Touch-ID-Helfer bei Bedarf (neu) uebersetzen
            threading.Thread(target=lambda: log.info("Touch ID helper: %s", auth.build_touchid()), name="kontor-touchid", daemon=True).start()
        self.restart_allowed = False        # nur der echte Dienst (serve) startet sich bei neuem Code selbst neu
        self.remote_listening: Optional[Tuple[str, str]] = None     # (Schema, Adresse) des Zugangs fuer andere Geraete
        self.remote_error: Optional[str] = None
        self.remote_tried: float = 0.0
        self._handler = None
        self._ts_cache: Tuple[float, dict] = (0.0, {})
        self.mm_probe: Tuple[float, Optional[bool]] = (0.0, None)     # (Zeitpunkt, gesperrt?)
        self.mm_retry_at: Optional[float] = None
        self._capture_sig: Optional[tuple] = None      # zuletzt gesehener Kontenstand (Konto, Saldo, Abrufzeit)
        self._captured_once = False                     # erster Schnellabgleich seit dem Start erledigt (Lueckenpruefung)
        self._change_since: Optional[float] = None      # seit wann MoneyMoney neue Daten zeigt (Abruf laeuft evtl. noch)
        self.retry_reason = ""
        self._mm_seen = False                           # lief MoneyMoney beim letzten Blick? (bestimmt den Takt)
        self._hb_written = 0.0
        self.prev_seen: Optional[datetime] = None       # wann der Dienst vor diesem Start zuletzt lief
        try:
            ps = (store.load("state.json", {}) or {}).get("dienst_zuletzt")
            self.prev_seen = datetime.fromisoformat(ps) if ps else None
        except Exception:
            self.prev_seen = None

    # -- Konfiguration -----------------------------------------------------
    def save_config(self, cfg: dict) -> None:
        new = merged_config(cfg)
        changed = [k for k in sorted(set(new) | set(self.config or {})) if (self.config or {}).get(k) != new.get(k)]
        old_lang = i18n.lang()
        self.config = new
        self.store.save("config.json", self.config)
        log.info("Configuration saved (changed: %s)", ", ".join(changed) or "nothing")
        self.sessions.set_idle(int(self.config["oberflaeche"].get("sperre_minuten", 15)))
        self._cfg_mtime = self._config_mtime()
        self.apply_language()
        if i18n.lang() != old_lang and self.ledger is not None:
            self.request_rebuild("language")          # Hinweise der Auswertung in der neuen Sprache

    def apply_language(self) -> None:
        i18n.set_lang((self.config.get("oberflaeche") or {}).get("sprache") or "de")

    def _config_mtime(self) -> float:
        try:
            return os.path.getmtime(self.store.path("config.json"))
        except OSError:
            return 0.0

    def reload_config_if_changed(self) -> bool:
        """Konfiguration neu laden, wenn sie ausserhalb des Dienstes geaendert wurde (CLI package-import)."""
        m = self._config_mtime()
        if m == getattr(self, "_cfg_mtime", None):
            return False
        self._cfg_mtime = m
        self.config = merged_config(self.store.load("config.json", {}) or {})
        self.sessions.set_idle(int(self.config["oberflaeche"].get("sperre_minuten", 15)))
        self.apply_language()
        log.info("Configuration reloaded (changed outside the service).")
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
                        "standard": bool(c.get("default", False)), "budget": b if b and b.get("amount") else None})
        return out

    def touchid_on(self) -> bool:
        return bool((self.config.get("oberflaeche") or {}).get("touchid", True))

    def config_has_rules(self) -> bool:
        c = self.config
        return bool(c.get("darlehen") or c.get("beteiligungen") or c.get("saldo_spiegel") or c.get("bereiche") or c.get("immobilien"))

    # -- MoneyMoney-Stand zwischenspeichern ---------------------------------
    def _load_ledger_cache(self) -> None:
        """Nach einem Neustart den letzten MoneyMoney-Stand aus dem (verschluesselten) Zwischenspeicher laden, damit
        Auswertungen und Verlauf sofort gehen -- auch wenn MoneyMoney gerade gesperrt oder geschlossen ist."""
        t0 = time.time()
        try:
            raw = self.store.read_bytes("moneymoney-ledger.bin")
            if not raw:
                return
            ledger, saved = ledger_from_bytes(raw)
        except Exception as e:
            log.info("MoneyMoney cache unusable (%s) -- recreated on next read", e)
            return
        with self.lock:
            if self.ledger is None:
                self.ledger, self.ledger_time, self.ledger_from_cache = ledger, saved or datetime.now(), True
                self.ledger_cache_fp = ledger_fp(ledger)
        log.info("MoneyMoney data from %s loaded from cache: %d accounts, %d transactions (%.1f s)",
                 (saved.strftime("%Y-%m-%d %H:%M") if saved else "?"), len(ledger.accounts), len(ledger.txs), time.time() - t0)
        # Ohne erreichbares MoneyMoney liest der Zeitplaner nichts: Auswertung einmal im Hintergrund bauen, damit Zwischen-
        # ergebnisse (Kategorien, Zahlungsstroeme) bereitliegen und die erste Aenderung nach einem Neustart schnell geht
        if self.store.exists("dataset.json") and (not is_running() or self.moneymoney_gesperrt(max_age=0) is not False):
            self.request_rebuild("Start")

    def _save_ledger_cache(self, ledger: Ledger, force: bool = False) -> None:
        fp = ledger_fp(ledger)
        if fp == self.ledger_cache_fp and not force:
            return
        self.ledger_cache_fp = fp

        def work():
            t0 = time.time()
            try:
                self.store.write_bytes("moneymoney-ledger.bin", ledger_to_bytes(ledger, self.ledger_time))
                log.debug("MoneyMoney data cached (%.1f s)", time.time() - t0)
            except Exception as e:  # pragma: no cover
                log.warning("MoneyMoney data not cached: %s", e)
        threading.Thread(target=work, name="kontor-cache-save", daemon=True).start()

    def set_ledger(self, ledger: Ledger, reuse: bool = False) -> None:
        """Neuen MoneyMoney-Stand uebernehmen. reuse=True: sind die Daten unveraendert, bleibt der bisherige Stand mit seinen
        Zwischenergebnissen (Kategorien, Zahlungsstroeme) in Gebrauch -- nur der Lesezeitpunkt wird aktualisiert."""
        old = self.ledger
        if reuse and old is not None and old is not ledger:
            try:
                same = self.ledger_cache_fp is not None and ledger_fp(ledger) == self.ledger_cache_fp
            except Exception:  # pragma: no cover
                same = False
            if same:
                self.ledger_time, self.ledger_from_cache = datetime.now(), False
                log.debug("MoneyMoney data unchanged -- intermediate results kept")
                for u, a in ledger.accounts.items():          # Abrufzeiten der Banken (zaehlen nicht zum Fingerabdruck) aktuell halten
                    if u in old.accounts:
                        old.accounts[u].refresh = a.refresh
                newer = getattr(ledger, "full_at", None)
                if newer and (getattr(old, "full_at", None) is None or old.full_at < newer):
                    old.full_at, old.since = newer, getattr(ledger, "since", None)
                    self._save_ledger_cache(old, force=True)     # Zeitpunkt des vollstaendigen Lesens auch nach Neustart
                return
        self.ledger, self.ledger_time, self.ledger_from_cache = ledger, datetime.now(), False
        self._save_ledger_cache(ledger)

    def _freeze_assignments(self) -> None:
        if self.ledger is None:
            return
        try:
            new = freeze_assignments(self.ledger, self.config)
        except Exception:  # pragma: no cover
            log.exception("Freezing assignments")
            return
        if new is not None:
            self.save_config(new)
            log.info("Position and history source of confirmed accounts frozen (previously automatic)")

    def historie_einlesen(self, buf: bytearray) -> None:
        """Hintergrund: Kontostand-Verlauf aller Konten aus der hochgeladenen MoneyMoney-Datenbank uebernehmen.
        Der Puffer wird in jedem Fall ueberschrieben; gespeichert werden nur Monatsend-Staende (verschluesselt)."""
        def step(t: str) -> None:
            self.mmh["schritt"] = t
        res: dict
        aufbau = os.path.join(HERE, "mm-history-schema.txt")
        try:
            ledger = self.ledger
            if ledger is None:
                raise mm_history.HistorieError(tr("s_erst_die_konten_aus_moneymoney"))
            accounts = {a.uuid: {"saldo": a.balance, "depot": a.portfolio, "iban": a.iban, "nummer": a.account_number, "blz": a.bank_code,
                                 "name": a.name, "waehrung": a.currency} for a in ledger.accounts.values() if not a.group}
            found, tables, fmt = mm_history.run(buf, accounts, date.today(), step=step, balance_at=balance_lookup(ledger),
                                                since=earliest_needed(self.config, date.today()))
            if not found or not found["konten"]:
                with open(aufbau, "w", encoding="utf-8") as f:       # nur Tabellen-/Spaltennamen, keine Inhalte
                    f.write(mm_history.schema_text(tables, fmt))
                log.info("MoneyMoney database read (%s, %d tables), balances not recognized", fmt, len(tables))
                res = {"ok": False, "text": tr("s_die_kontostaende_wurden_in_der")}
            else:
                konten = found["konten"]
                monate = sorted({mk for v in konten.values() for mk in v})
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.store.save(MM_HISTORY_FILE, {"stand": now, "konten": konten, "anfang": found.get("anfang") or {}})   # ersetzt den bisherigen Stand
                meta = {"zeit": now, "konten": len(konten), "werte": sum(len(v) for v in konten.values()),
                        "depots": sum(1 for u in konten if u in ledger.accounts and ledger.accounts[u].portfolio),
                        "von": monate[0] if monate else None, "bis": monate[-1] if monate else None}
                self.store.update("state.json", lambda cur: cur.__setitem__("mm_verlauf", meta), {})
                if os.path.exists(aufbau):
                    os.remove(aufbau)
                log.info("Balances imported from MoneyMoney (%s): %d accounts, %d monthly values (check %d/%d)",
                         fmt, meta["konten"], meta["werte"], found["treffer"], found["geprueft"])
                self.request_rebuild(tr("s_kontostaende_aus_moneymoney"))
                res = dict(meta, ok=True)
        except mm_history.HistorieError as e:
            if str(e) != "abgebrochen":
                log.info("MoneyMoney database not read: %s", str(e)[:120])
            res = {"ok": False, "text": tr("s_abgebrochen") if str(e) == "abgebrochen" else str(e)}
        except Exception:  # pragma: no cover
            log.exception("Balances from MoneyMoney")
            res = {"ok": False, "text": tr("s_unerwarteter_fehler_details_im_protoko")}
        finally:
            mm_history._wipe(buf)
        self.mmh = {"laeuft": False, "schritt": None, "ergebnis": res}

    def _rebuild_now(self) -> Tuple[bool, Optional[str]]:
        """Bericht aus dem letzten bekannten Stand neu bauen (synchron; nur aus dem Hintergrund-Thread aufrufen)."""
        def progress(f: float, text: str) -> None:
            self.bericht_fortschritt = {"anteil": round(f, 2), "schritt": text}
        if self.ledger is None:
            progress(0.02, tr("s_moneymoney_wird_gelesen"))
            ledger, err = self.refresh_ledger()
            if ledger is None:
                return False, err
        self._freeze_assignments()
        t0 = time.time()
        progress(0.03, tr("s_wartet_auf_laufenden_abgleich"))
        with RUN_LOCK:          # nicht gleichzeitig mit einem Lauf (beide schreiben dataset.json)
            st = self.store.load("state.json", {}) or {}
            try:
                ds = build_report(self.store, self.ledger, self.config, st, date.today(), [], self.categories_raw, progress)
                self.umsaetze = ds.pop("_umsaetze", None)
            except Exception as e:  # pragma: no cover
                log.exception("Report from last data failed")
                return False, tr("s_bericht_fehlgeschlagen_s") % e
            # nur die Monats-Schnappschuesse zurueckschreiben -- Verlauf-Eingaben, die waehrend des Baus kamen, bleiben erhalten
            self.store.update("state.json", lambda cur: merge_snapshots(cur, st.get("snapshots") or {}), {})
        log.info("Report rebuilt from last data (%.1f s)", time.time() - t0)
        return True, None

    def _rebuild_worker(self) -> None:
        while True:
            with self.rebuild_cv:
                if not self.rebuild_pending:
                    self.rebuild_running = False
                    self.rebuild_cv.notify_all()
                    return
                self.rebuild_pending = False
                reasons, self.rebuild_reasons = self.rebuild_reasons, []
            t0 = time.time()
            log.debug("Rebuilding report (%s)", ", ".join(reasons) or "requested")
            ok, err = self._rebuild_now()
            with self.rebuild_cv:
                self.bericht = {"stand": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dauer": round(time.time() - t0, 1),
                                "fehler": None if ok else err, "grund": ", ".join(reasons)}
                self.rebuild_cv.notify_all()

    def request_rebuild(self, grund: str = "") -> None:
        """Berichtsneubau anstossen (kehrt sofort zurueck). Mehrere Anstoesse waehrend eines Laufs ergeben genau einen weiteren Lauf."""
        with self.rebuild_cv:
            self.rebuild_pending = True
            if grund and grund not in self.rebuild_reasons:
                self.rebuild_reasons.append(grund)
            if not self.rebuild_running:
                self.rebuild_running = True
                threading.Thread(target=self._rebuild_worker, name="kontor-bericht", daemon=True).start()

    def rebuild_report(self, wait: bool = False, grund: str = "", timeout: float = 600.0):
        """Neubau anstossen. wait=True wartet auf das Ergebnis und liefert (ok, fehler); sonst ('angefordert', None)."""
        self.request_rebuild(grund)
        if not wait:
            return "angefordert", None
        with self.rebuild_cv:
            self.rebuild_cv.wait_for(lambda: not self.rebuild_running and not self.rebuild_pending, timeout=timeout)
            b = self.bericht
        return (b.get("fehler") is None and b.get("stand") is not None), b.get("fehler")

    def bericht_status(self) -> dict:
        with self.rebuild_cv:
            laeuft = self.rebuild_running or self.rebuild_pending
            return {"laeuft": laeuft, **self.bericht, "fortschritt": self.bericht_fortschritt if laeuft else None}

    def moneymoney_gesperrt(self, max_age: float = 45.0) -> Optional[bool]:
        """Ist MoneyMoney gesperrt? Kurzer Lesezugriff auf die Kontenliste, hoechstens alle max_age Sekunden; None = laeuft nicht."""
        if not is_running():
            return None
        ts, val = self.mm_probe
        if time.time() - ts < max_age:
            return val
        try:
            self.bridge_factory(True).export_accounts()
            val = False
        except MoneyMoneyError as e:
            val = "gesperrt" in str(e).lower() or "locked" in str(e).lower() or None
        except Exception:  # pragma: no cover
            val = None
        self.mm_probe = (time.time(), val)
        return val

    # -- Zugriff von anderen Geraeten (iPhone ueber Tailscale) --------------
    def remote_readonly(self) -> bool:
        """Von unterwegs nur ansehen (Standard): Aenderungen nur am Mac."""
        return bool((self.config.get("oberflaeche") or {}).get("fern_nur_ansehen", True))

    def offline_copy(self) -> bool:
        """Darf das iPhone die zuletzt geladenen Daten fuer die Offline-Ansicht behalten?"""
        return bool((self.config.get("oberflaeche") or {}).get("offline_kopie", True))

    def tailscale(self, fresh: bool = False) -> dict:
        """Tailscale state (tls_cert.status). Older than 30 s: answer with the last state and refresh in the background, so a
        page never waits for Tailscale; fresh=True (or nothing known yet) asks right away."""
        import tls_cert
        t0, st = self._ts_cache
        if fresh or not t0:
            st = tls_cert.status()
            self._ts_cache = (time.time(), st)
        elif time.time() - t0 > 30 and not getattr(self, "_ts_refreshing", False):
            self._ts_refreshing = True

            def refresh():
                try:
                    self._ts_cache = (time.time(), tls_cert.status())
                finally:
                    self._ts_refreshing = False
            threading.Thread(target=refresh, daemon=True).start()
        return st

    def remote_info(self) -> dict:
        ui = self.config.get("oberflaeche") or {}
        bind = (ui.get("bind") or "127.0.0.1").strip()
        port = int(ui.get("port") or 8765)
        ts = self.tailscale()
        tls = bool(ui.get("tls_cert") and ui.get("tls_key"))
        exp = None
        if tls:
            import tls_cert
            e = tls_cert.cert_expiry(ui["tls_cert"])
            exp = e.date().isoformat() if e else None
        host = (os.path.basename(ui.get("tls_cert") or "")[:-4] if tls else "") or bind
        return {"aktiv": bind != "127.0.0.1", "adresse": bind, "port": port, "tls": tls, "gueltig_bis": exp,
                "url": ("https://%s:%d/" % (host, port)) if tls else ("http://%s:%d/" % (bind, port)) if bind != "127.0.0.1" else None,
                "lauscht": bool(self.remote_listening), "fehler": self.remote_error,
                "nur_ansehen": self.remote_readonly(), "offline_kopie": self.offline_copy(), "tailscale": ts}

    def request_restart(self) -> None:
        """Dienst neu starten (neue Adresse/Zertifikat), kurz nachdem die Antwort raus ist. Nur im echten Dienst."""
        if self.restart_allowed:
            log.info("Restarting service for new access settings")
            threading.Timer(1.5, restart_process).start()

    def start_remote(self) -> None:
        """Zweiten Zugang auf der eingestellten Tailscale-Adresse oeffnen (mit TLS, wenn ein Zertifikat eingetragen ist).
        Klappt das nicht (Tailscale noch nicht verbunden), versucht es der Zeitplaner jede Minute erneut."""
        ui = self.config.get("oberflaeche", {}) or {}
        extra = (ui.get("bind") or "127.0.0.1").strip()
        self.remote_tried = time.time()
        if self._handler is None or extra == "127.0.0.1" or self.remote_listening:
            return
        if not bind_allowed(extra) or ipaddress.ip_address(extra).is_loopback:
            self.remote_error = tr("s_adresse_s_nicht_erlaubt_nur") % extra
            return
        port = int(ui.get("port") or 8765)
        try:
            srv2 = _Server((extra, port), self._handler)
        except OSError as e:
            if self.remote_error != str(e):
                log.error("Address %s:%d not usable (%s) -- is Tailscale connected? Retrying every minute", extra, port, e)
            self.remote_error = str(e)
            return
        scheme = "http"
        if ui.get("tls_cert") and ui.get("tls_key"):
            try:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                ctx.load_cert_chain(ui["tls_cert"], ui["tls_key"])
                srv2.socket = ctx.wrap_socket(srv2.socket, server_side=True)
                self.tls_ctx = ctx
                scheme = "https"
            except (OSError, ssl.SSLError) as e:
                log.error("TLS not enabled (%s) -- continuing without TLS", e)
        self.remote_listening, self.remote_error = (scheme, extra), None
        log.info("Access for other devices at %s://%s:%d/", scheme, extra, port)
        threading.Thread(target=srv2.serve_forever, daemon=True).start()

    # -- MoneyMoney --------------------------------------------------------
    def full_read_days(self) -> int:
        return max(1, int((self.config.get("zeitplan") or {}).get("voll_lesen_tage", 7) or 7))

    def full_read_due(self, now: Optional[datetime] = None) -> bool:
        """Read all transactions when the last full read is at least N days old (setting, default 7). In between the quick
        read checks every balance and reads everything at once if older transactions changed (core.unexplained_balances)."""
        b = self.ledger
        fa = getattr(b, "full_at", None) if b is not None else None
        if fa is None:
            return True
        return ((now or datetime.now()) - fa).total_seconds() >= self.full_read_days() * 86400

    def full_read_info(self) -> dict:
        fa = getattr(self.ledger, "full_at", None) if self.ledger is not None else None
        return {"zuletzt": fa.strftime("%Y-%m-%d %H:%M") if fa else None, "tage": self.full_read_days()}

    def refresh_ledger(self, full: Optional[bool] = None) -> Tuple[Optional[Ledger], Optional[str]]:
        """MoneyMoney lesen. Der Fortschritt (Schritt, Beginn, Dauer der Schritte beim letzten Mal) steht in self.lesen."""
        t0 = time.time()
        st = self.store.load_shared("state.json", {}) or {}
        self.lesen = {"laeuft": True, "schritt": None, "seit": t0, "start": t0, "dauer": dict(st.get("lesen_dauer") or {})}
        took: Dict[str, float] = {}

        def step(name: str) -> None:
            now = time.time()
            if self.lesen.get("schritt"):
                took[self.lesen["schritt"]] = round(now - self.lesen["seit"], 2)
            self.lesen.update(schritt=name, seit=now)
        try:
            b = self.bridge_factory(True)
            ledger = fetch(b, self.config, date.today(), with_portfolio=True, progress=step, base=self.ledger,
                           full=self.full_read_due() if full is None else full)
            log.info("MoneyMoney read (%.1f s)", time.time() - t0)
            step("categories")
            try:
                self.categories_raw = mm_categories.with_paths(b.export_categories())
                self.store.update("state.json", lambda st: st.__setitem__("kategorien_roh", self.categories_raw), {})
            except MoneyMoneyError:
                pass
            step("save")
            self.set_ledger(ledger, reuse=True)
            self._baseline(ledger)
            step("done")
            self.store.update("state.json", lambda st: st.__setitem__("lesen_dauer", took), {})
            return self.ledger, None
        except MoneyMoneyError as e:
            log.warning("MoneyMoney not readable: %s", e)
            return None, unavailable_text(e) or (tr("s_moneymoney_fehler_s") % e)
        finally:
            self.lesen["laeuft"] = False

    def do_run(self, dry: Optional[bool], force: bool, with_report: bool = True, full: Optional[bool] = None) -> dict:
        with self.lock:
            if self.running:
                return {"status": "laeuft_bereits", "text": tr("s_ein_abgleich_laeuft_bereits")}
            self.running = True
        try:
            d = self.config.get("probelauf", True) if dry is None else dry
            self._freeze_assignments()
            t0 = time.time()
            log.info("Run started (%s%s%s)", "dry run" if d else "live", ", forced" if force else "", ", without report" if not with_report else "")
            full = self.full_read_due() if full is None else full
            res = run_once(self.store, self.config, date.today(), d, force, self.bridge_factory, with_report, base=self.ledger, full=full)
            log.info("Run finished: %s (%.1f s)", res.get("text") or res.get("status"), time.time() - t0)
            self.last_run_at = time.time()
            ledger = res.pop("_ledger", None)
            cats = res.pop("_kategorien", None)
            ums = res.pop("_umsaetze", None)
            if ums is not None:
                self.umsaetze = ums
            if ledger is not None:
                self.set_ledger(ledger, reuse=res.get("status") == "unveraendert")
                self._baseline(ledger)
            if cats:
                self.categories_raw = cats
            self.last_result = res
            try:
                self.flush_pending_categories()
            except Exception:  # pragma: no cover
                log.exception("Pending categories")
            return res
        except Exception as e:  # pragma: no cover - letzte Sicherung, damit der Dienst weiterlaeuft
            log.exception("Run failed")
            self.last_result = {"status": "fehler", "text": tr("s_unerwarteter_fehler_s") % e}
            return self.last_result
        finally:
            self.running = False

    def _baseline(self, ledger: Ledger) -> None:
        """Kontenstand eines vollstaendigen Lesens merken: nur spaetere Aenderungen in MoneyMoney loesen den naechsten Lauf aus."""
        sig = getattr(ledger, "acc_sig", None)
        if sig is not None:
            self._capture_sig = sig
            self._change_since = None
            if self.retry_reason == "new data":
                self.mm_retry_at = None

    def capture(self) -> None:
        """Schnellabgleich: sobald MoneyMoney offen und entsperrt ist, nur die Kontenliste lesen (unter einer Sekunde) und die
        Staende merken. So reicht auch ein kurzer Blick in MoneyMoney; geaenderte Daten loesen danach den vollen Abgleich aus."""
        self._mm_seen = is_running()
        if self.running or not self._mm_seen:
            return
        try:
            raw = self.bridge_factory(True).export_accounts()
        except MoneyMoneyError as e:
            if isinstance(e, MoneyMoneyLocked):
                self.mm_probe = (time.time(), True)
            elif not isinstance(e, MoneyMoneyNotRunning):
                # MoneyMoney lief, Kontor konnte aber nicht lesen (z. B. Berechtigung) -> sichtbar machen, sonst fehlen Staende
                msg = str(e)[:200]
                log.warning("Quick capture not possible although MoneyMoney is running: %s", msg)
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.store.update("state.json", lambda cur: cur.__setitem__("abgleich_problem", {"zeit": stamp, "text": msg}), {})
            return
        self.mm_probe = (time.time(), False)
        if (self.store.load_shared("state.json", {}) or {}).get("abgleich_problem"):
            self.store.update("state.json", lambda cur: cur.pop("abgleich_problem", None), {})
        accs = accounts_from_export(raw)
        sig = account_sig(accs)
        if sig == self._capture_sig:
            return
        first = not self._captured_once
        self._captured_once = True
        known = self._capture_sig is not None
        self._capture_sig = sig
        today = date.today()
        self.store.update("state.json", lambda cur: record_snapshot(cur.setdefault("snapshots", {}), accs.values(), today), {})
        if first:
            self._check_gaps(accs)
        if known and (self.config.get("zeitplan") or {}).get("automatisch", True):
            # neue Daten in MoneyMoney: vollstaendig abgleichen, sobald der Abruf dort fertig ist (Stand 45 s unveraendert,
            # spaetestens 3 Minuten nach der ersten Aenderung) -- sonst liefe bei jeder einzelnen Bank ein eigener Abgleich
            now = time.time()
            self._change_since = self._change_since or now
            self.mm_retry_at = min(now + 45, self._change_since + 180)
            self.retry_reason = "new data"

    def _check_gaps(self, accs: Dict) -> None:
        """Hat MoneyMoney ein Depot abgerufen, waehrend Kontor nicht lief, koennen Monatsend-Staende dazwischen fehlen
        (Kontor sieht nur den neuesten). Schlief der Mac, hat auch MoneyMoney nichts abgerufen -- dann keine Meldung."""
        prev = self.prev_seen
        if prev is None:
            return
        found = []
        for a in accs.values():
            if a.group or not a.portfolio or a.refresh is None or a.refresh.year < 2005:
                continue
            ref = a.refresh.replace(tzinfo=None)            # Ortszeit wie prev_seen/started
            if not (prev + timedelta(minutes=5) < ref < self.started):
                continue
            months, y, m = [], prev.year, prev.month
            while (y, m) < (ref.year, ref.month):
                months.append("%04d-%02d" % (y, m))
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)
            if months:
                found.append({"konto": a.uuid, "name": a.name, "monate": months, "erkannt": datetime.now().strftime("%Y-%m-%d %H:%M")})
        if found:
            log.info("Portfolio values possibly incomplete (MoneyMoney refreshed while Kontor was not running): %s",
                     ", ".join("%s %s–%s" % (f["name"], f["monate"][0], f["monate"][-1]) for f in found))

            def upd(cur):
                old = [x for x in cur.get("luecken") or [] if x.get("konto") not in {f["konto"] for f in found}]
                cur["luecken"] = old + found
            self.store.update("state.json", upd, {})

    def heartbeat(self) -> None:
        if time.time() - self._hb_written >= 300:
            self._hb_written = time.time()
            now = datetime.now().isoformat(timespec="seconds")
            self.store.update("state.json", lambda cur: cur.__setitem__("dienst_zuletzt", now), {})

    def code_changed(self) -> Optional[str]:
        """Neue Version im Programmordner (git pull, Update, Dateien ersetzt)? Liefert die neue Versionsnummer."""
        disk = version_on_disk()
        return disk if disk and disk != version() else None

    def restart_if_code_changed(self) -> bool:
        new = self.code_changed()
        if not new or self.running or self.bericht_status().get("laeuft") or not self.restart_allowed:
            return False
        log.info("New version %s in program folder (running %s) -- restarting service", new, version())
        self.stop.set()
        restart_process()
        return True

    def scheduler(self) -> None:
        while not self.stop.is_set():
            try:
                if self.restart_if_code_changed():
                    return
                self.reload_config_if_changed()
                z = self.config.get("zeitplan", {}) or {}
                interval = max(5, int(z.get("intervall_minuten", 30))) * 60
                due = z.get("automatisch", True) and (self.last_run_at is None or time.time() - self.last_run_at >= interval)
                retry = z.get("automatisch", True) and self.mm_retry_at is not None and time.time() >= self.mm_retry_at
                if due or retry:
                    if not is_running():
                        if due:
                            log.debug("Scheduler: run due, but MoneyMoney is not running -- checking every minute")
                        self.last_run_at = time.time()
                        self.mm_retry_at = time.time() + 60
                        self.retry_reason = "available again"
                    elif self.moneymoney_gesperrt(max_age=0) is not None and self.moneymoney_gesperrt() is not False:
                        if due:
                            log.debug("Scheduler: run due, but MoneyMoney is locked -- checking every minute")
                        self.last_run_at = time.time()
                        self.mm_retry_at = time.time() + 60
                        self.retry_reason = "available again"
                    else:
                        log.debug("Scheduler: run %s", "due" if due else ("after new data in MoneyMoney" if self.retry_reason == "new data"
                                                                         else "catching up (MoneyMoney available again)"))
                        self.mm_retry_at = None
                        self._change_since = None
                        res = self.do_run(None, force=False)
                        if res.get("status") in ("nicht_verfuegbar", "laeuft_bereits"):     # z. B. Neuberechnung lief gerade
                            self.mm_retry_at = time.time() + 60
                up = self.config.get("updates", {}) or {}
                every = {"taeglich": 86400, "woechentlich": 7 * 86400}.get(up.get("pruefen") or "taeglich")      # "aus": nie
                wait = every if every and not (self.update_info or {}).get("fehler") else 7200                   # offline/Fehler: in 2 h erneut
                if every and not mm_history.AKTIV.is_set() and (self.update_checked is None or time.time() - self.update_checked > wait):
                    self.update_checked = time.time()
                    # eigener Thread: eine haengende Verbindung (offline) blockiert weder Zeitplaner noch Oberflaeche
                    threading.Thread(target=lambda: setattr(self, "update_info", updates.check(up.get("repo") or "stecrz/Kontor")),
                                     name="kontor-update", daemon=True).start()
                if self.tls_ctx is not None and (self.tls_checked is None or time.time() - self.tls_checked > 86400):
                    self.tls_checked = time.time()
                    import tls_cert
                    if tls_cert.renew_if_due(self.config, self.data_dir):
                        ui = self.config.get("oberflaeche") or {}
                        self.tls_ctx.load_cert_chain(ui["tls_cert"], ui["tls_key"])
                        log.info("TLS certificate renewed and reloaded")
            except Exception:  # pragma: no cover
                log.exception("Scheduler")
            try:
                bind = ((self.config.get("oberflaeche") or {}).get("bind") or "127.0.0.1").strip()
                if bind != "127.0.0.1" and not self.remote_listening and self._handler is not None and time.time() - self.remote_tried >= 60:
                    self.start_remote()
            except Exception:  # pragma: no cover
                log.exception("Remote access")
            try:
                self.heartbeat()
                if (self.config.get("zeitplan") or {}).get("automatisch", True):
                    self.capture()
            except Exception:  # pragma: no cover
                log.exception("Quick capture")
            self.stop.wait(30 if self._mm_seen else 60)

    # -- Daten fuer die Oberflaeche ---------------------------------------
    def plan_all(self) -> dict:
        plan = self.store.load("plan.json", {}) or {}
        if "bereiche" in plan:
            return plan
        ds = self.store.load_shared("dataset.json", {}) or {}
        haupt = ds.get("haupt")
        return {"bereiche": ({haupt: plan} if plan and haupt else {})}

    def plan_for(self, bereich: str) -> dict:
        return (self.plan_all().get("bereiche") or {}).get(bereich) or {}

    # -- Kategorien nach MoneyMoney zurueckschreiben ---------------------------
    def mm_write_allowed(self, local: bool) -> bool:
        """Zurueckschreiben eingeschaltet und Anfrage vom Mac selbst (nicht von unterwegs)."""
        return local and bool((self.config.get("moneymoney") or {}).get("kategorisieren_erlauben", False))

    def write_categories(self, kat: dict, ids: List[int], path: str, modus: str, local: bool) -> dict:
        """Nach der Zuordnung in Kontor (categorize.assign): nach MoneyMoney schreiben.
        modus: "auto" (leere und von Kontor gesetzte Kategorien; fremde werden gemeldet), "ueberschreiben" (fremde, die bei
        der Rueckfrage zu sehen waren, ebenfalls), "nur_kontor" (MoneyMoney bleibt, Kontor uebersteuert)."""
        path = categorize.norm_cat(path)
        led = self.ledger
        by_id = {t.id: t for t in led.txs if t.id > 0} if led is not None else {}
        out: Dict[str, Any] = {"geschrieben": 0, "wartet": 0, "fremd": [], "fehler": 0, "nur_kontor": 0, "aus": False}
        if not path or not ids:
            return out
        if modus == "nur_kontor" or not self.mm_write_allowed(local) or led is None:
            # nur in Kontor: gegenueber einer Kategorie aus MoneyMoney ausdruecklich uebersteuern
            for i in ids:
                z = kat["zuordnung"].get(str(i))
                if z and i in by_id and categorize.mm_of(by_id[i]):
                    z["ov"] = True
            out["nur_kontor"] = len(ids)
            out["aus"] = modus != "nur_kontor"
            return out
        items = [{"id": i, "neu": path, "alt": categorize.mm_of(by_id[i]), "ueberschreiben": modus == "ueberschreiben"} for i in ids if i in by_id]
        own = (self.store.load_shared("state.json", {}) or {}).get(mm_categories.LOG_KEY) or {}
        idx = mm_categories.index(self.categories_raw)
        try:
            res = mm_categories.write(self.bridge_factory(False), led, items, idx, own)
        except MoneyMoneyError as e:
            log.warning("Setting categories in MoneyMoney not possible: %s", e)
            raise ValueError(unavailable_text(e) or (tr("s_moneymoney_fehler_s") % e))
        written = res["geschrieben"]
        if written:
            mm_categories.apply_to_ledger(led, idx, written)
            self.store.update("state.json", lambda cur: mm_categories.remember(cur, written), {})
            self._save_ledger_cache(led, force=True)
        for i in [w["id"] for w in written] + res["gleich"]:
            kat["zuordnung"].pop(str(i), None)          # steht jetzt in MoneyMoney -- dort massgeblich
        for i in res["wartet"]:
            if str(i) in kat["zuordnung"]:
                kat["zuordnung"][str(i)]["w"] = 1       # Kategorie in MoneyMoney anlegen, dann wird nachgetragen
        for f in res["fehler"]:                          # MoneyMoney weicht ab: Zuordnung bleibt in Kontor
            z = kat["zuordnung"].get(str(f["id"]))
            if z and f["id"] in by_id and categorize.mm_of(by_id[f["id"]]):
                z["ov"] = True
        out.update(geschrieben=len(written), wartet=len(res["wartet"]), fremd=res["fremd"], fehler=len(res["fehler"]))
        return out

    def flush_pending_categories(self) -> int:
        """Wartende Zuordnungen nachtragen, sobald es die Kategorie in MoneyMoney gibt (Zurueckschreiben eingeschaltet).
        Hat der Umsatz inzwischen in MoneyMoney eine Kategorie, gilt diese und die wartende Zuordnung entfaellt."""
        if not (self.config.get("moneymoney") or {}).get("kategorisieren_erlauben") or self.ledger is None:
            return 0
        kat = categorize.load(self.store)
        idx = mm_categories.index(self.categories_raw)
        pend: Dict[str, List[int]] = {}
        for tid, z in kat["zuordnung"].items():
            if z.get("w") and mm_categories.assignable(idx, z.get("k") or "") is None:
                pend.setdefault(z["k"], []).append(int(tid))
        if not pend:
            return 0
        n = 0
        for path, ids in pend.items():
            try:
                res = self.write_categories(kat, ids, path, "auto", True)
            except ValueError as e:
                log.info("Pending categories not written: %s", e)
                return n
            n += res["geschrieben"]
            for f in res["fremd"]:                       # in MoneyMoney inzwischen anders kategorisiert -> gilt
                kat["zuordnung"].pop(str(f["id"]), None)
        categorize.save(self.store, kat)
        if n:
            log.info("%d pending categor(y/ies) written to MoneyMoney", n)
            self.request_rebuild(tr("s_grund_kategorien_nachgetragen"))
        return n

    def umsatzliste(self) -> list:
        """Kompakte Umsatzliste des aktuellen Berichts (schreibgeschuetzt): aus dem Speicher, sonst aus umsaetze.json."""
        if self.umsaetze is None:
            self.umsaetze = self.store.load_shared("transactions.json", []) or []
        return self.umsaetze

    def dataset(self) -> dict:
        raw = self.store.load_shared("dataset.json", None)
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
                log.exception("Planning for area %s", bid)
                b["fehler"] = tr("s_planung_fehlgeschlagen") % e

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
        ds["positionen"] = [{"id": r, "name": role_label(r)} for r in ROLES]
        return ds

    def abruf(self) -> Optional[dict]:
        """Eigener Datenstand von MoneyMoney je Konto (laut dem zuletzt gelesenen Stand): neuester Bankabruf, Konten, die dahinter
        zurueckliegen (mehr als einen Tag, mit Saldo, nicht laenger als inaktiv_monate), und Konten ohne Abruf (offline)."""
        led = self.ledger
        if led is None:
            return None
        n_inakt = int((self.config.get("bilanz") or {}).get("inaktiv_monate", 12) or 12)
        key = (id(led), n_inakt, json.dumps([self.config.get(k) for k in ("abruf", "darlehen", "beteiligungen", "saldo_spiegel")], sort_keys=True, default=str))
        if self._bankabruf_cache[0] == key:
            return self._bankabruf_cache[1]
        kinds = abruf_arten(led, self.config)
        leaves = [a for a in led.accounts.values() if not a.group and a.path]
        online = [a for a in leaves if kinds[a.uuid]["art"] == "online" and a.refresh is not None and a.refresh.year >= 2005]
        newest = max((a.refresh for a in online), default=None)
        cutoff = newest - timedelta(days=30.5 * n_inakt) if newest else None
        konten, lag = [], []
        for a in leaves:
            k = kinds[a.uuid]
            refreshed = a.refresh is not None and a.refresh.year >= 2005
            zurueck = bool(newest and k["art"] == "online" and refreshed and cutoff <= a.refresh < newest - timedelta(days=1)
                           and (a.portfolio or abs(a.balance) > 0.005))
            alt = bool(newest and k["art"] == "online" and refreshed and a.refresh < cutoff)
            konten.append({"uuid": a.uuid, "name": a.name, "pfad": a.path, "art": k["art"], "grund": k["grund"], "saldo": a.balance,
                           "zeit": a.refresh.strftime("%Y-%m-%d %H:%M") if refreshed else None, "zurueck": zurueck, "alt": alt})
            if zurueck:
                lag.append(a)
        lag.sort(key=lambda a: a.refresh)
        res = {"neuester": newest.strftime("%Y-%m-%d %H:%M") if newest else None, "konten": konten,
               "zurueck": [{"name": a.name, "zeit": a.refresh.strftime("%Y-%m-%d %H:%M")} for a in lag[:12]], "zurueck_anzahl": len(lag)}
        self._bankabruf_cache = (key, res)
        return res

    def bankabruf(self) -> Optional[dict]:
        r = self.abruf()
        if not r or not r["neuester"]:
            return None
        return {"neuester": r["neuester"], "zurueck": r["zurueck"], "zurueck_anzahl": r["zurueck_anzahl"],
                "konten": sum(1 for k in r["konten"] if k["art"] == "online")}

    def status(self, loopback: bool, frisch: bool = False) -> dict:
        st = self.store.load_shared("state.json", {}) or {}
        bcfg = self.config.get("belege") or {}
        return {
            "version": version(),
            "dienst": {"gestartet": self.started.strftime("%Y-%m-%d %H:%M"), "laeuft": self.running,
                       "automatisch": (self.config.get("zeitplan") or {}).get("automatisch", True),
                       "intervall_minuten": (self.config.get("zeitplan") or {}).get("intervall_minuten", 30)},
            "moneymoney": {"laeuft": is_running(), "gesperrt": self.moneymoney_gesperrt(max_age=3.0 if frisch else 45.0), "aus_zwischenspeicher": self.ledger_from_cache,
                           "stand": self.ledger_time.strftime("%Y-%m-%d %H:%M") if self.ledger_time else None,
                           "bankabruf": self.bankabruf(), "luecken": len(st.get("luecken") or []), "problem": st.get("abgleich_problem"), "historie": st.get("mm_verlauf"),
                           "kategorisieren_erlaubt": bool((self.config.get("moneymoney") or {}).get("kategorisieren_erlauben", False))},
            "ablage": {"verschluesselt": self.store.encrypted, "schluessel": self.store.key_source, "ordner": self.data_dir},
            "belege": {"ordner": os.path.expanduser(bcfg.get("ordner") or "~/Documents/Kontor-Belege")},
            "probelauf": self.config.get("probelauf", True),
            "letzter_lauf": st.get("letzter_lauf"),
            "letztes_ergebnis": self.last_result,
            "bericht": self.bericht_status(),
            "neustart_ausstehend": self.code_changed(),
            "update": self.update_info,
            "touchid": auth.touchid_available() and loopback, "touchid_aktiv": self.touchid_on(),
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


EXPORT_FILE_KEYS = {"balance": "xf_balance", "cashflow": "xf_cashflow", "planning": "xf_planning", "tax": "xf_tax", "transactions": "xf_transactions",
                    "holdings": "xf_holdings", "receipts": "xf_receipts", "accounts": "xf_accounts"}       # Dateiname je Export (Sprachkatalog)


def export_sheets(app: App, was: str, bereich: Optional[str], modus: str) -> List[Sheet]:
    ds = app.dataset()
    if ds.get("leer"):
        raise ValueError(tr("s_noch_keine_daten_zuerst_einen"))
    key = bereich or ds.get("haupt") or ""
    b = (ds.get("bereiche") or {}).get(key, {})
    name = (ds.get("bereich_namen") or {}).get(key, "")
    if was in ("balance", "cashflow", "planning") and (not b or "fehler" in b):
        raise ValueError(tr("s_bereich_nicht_vorhanden_oder_fehlerhaf"))

    def columns(include_plan: bool):
        ist = b.get("monate", [])
        plan = b.get("plan_monate", []) if include_plan else []
        allm = ist + plan
        if modus == "jahre":
            years = sorted({m[:4] for m in allm})
            return [(y, [m for m in allm if m.startswith(y)], any(m in plan for m in allm if m.startswith(y))) for y in years]
        return [(m, [m], m in plan) for m in allm]

    if was == "balance":
        cols = columns(False)
        rows, bold = [], []
        for r in b.get("bilanz", {}).get("zeilen", []):
            rows.append(["    " * r["ebene"] + r["name"]] + [_last(r["werte"], ms) for _, ms, _p in cols])
            if r["gruppe"]:
                bold.append(len(rows) - 1)
        nw = b.get("bilanz", {}).get("nettovermoegen", {})
        lnw = b.get("bilanz", {}).get("liquides_nettovermoegen", {})
        rows.append([tr("x_nettovermoegen")] + [_last(nw, ms) for _, ms, _p in cols]); bold.append(len(rows) - 1)
        rows.append([tr("x_davon_liquide")] + [_last(lnw, ms) for _, ms, _p in cols])
        return [Sheet(tr("x_bilanz") + " " + name, [tr("x_konto")] + [c[0] for c in cols], rows, bold_rows=bold)]

    if was in ("cashflow", "planning"):
        cols = columns(True)
        rows, bold = [], []
        for sek in b.get("kapitalfluss", {}).get("sektionen", []):
            rows.append([sek["name"]] + [None] * len(cols)); bold.append(len(rows) - 1)
            for z in sek["zeilen"]:
                allv = dict(z["werte"]); allv.update((z.get("plan") or {}).get("werte", {}))
                label = "    " + z["zeile"] + ("" if z.get("nw") else tr("x_umschichtung"))
                rows.append([label] + [round(sum(allv.get(m, 0.0) for m in ms), 2) for _, ms, _p in cols])
        sums = b.get("kapitalfluss", {}).get("summen", {})
        for k, label in (("Operativ", tr("x_operativ")), ("Cashflow", tr("x_cashflow_gesamt")), ("Nettovermoegen_delta", tr("s_nettovermoegensaenderung"))):
            rows.append([label] + [round(sum((sums.get(m) or {}).get(k, 0.0) for m in ms), 2) for _, ms, _p in cols]); bold.append(len(rows) - 1)
        head = [tr("x_position")] + [c[0] + (tr("x_plan_suffix") if c[2] else "") for c in cols]
        sheets = [Sheet(tr("x_planung" if was == "planning" else "x_kapitalfluss") + " " + name, head, rows, bold_rows=bold)]
        if was == "planning":
            pr = b.get("bilanz", {}).get("projektion", {})
            pcols = [c for c in cols if c[2]]
            prow, pbold = [], []
            for r in pr.get("zeilen", []):
                prow.append(["    " * r["ebene"] + r["name"]] + [_last(r["werte"], ms) for _, ms, _p in pcols])
                if r.get("gruppe"):
                    pbold.append(len(prow) - 1)
            prow.append([tr("x_nw_plan")] + [_last(pr.get("nettovermoegen", {}), ms) for _, ms, _p in pcols]); pbold.append(len(prow) - 1)
            prow.append([tr("x_liq_plan")] + [_last(pr.get("liquiditaet", {}), ms) for _, ms, _p in pcols])
            sheets.append(Sheet(tr("x_fortschreibung"), [tr("x_position")] + [c[0] for c in pcols], prow, bold_rows=pbold))
            P = b.get("plan", {})
            prm = [[k, P.get(k)] for k in PLAN_PARAMS]
            for zn, zc in (P.get("zeilen") or {}).items():
                prm.append([tr("x_zeile") % zn, json.dumps(zc, ensure_ascii=False)])
            sheets.append(Sheet(tr("x_parameter"), [tr("x_parameter"), tr("x_wert")], prm, widths=[40, 60], freeze="A2"))
        return sheets

    if was == "tax":
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
                    rows.append(["", tr("x_vermietung") % o, d["ergebnis"], None]); bold.append(len(rows) - 1)
                    for a, v in d["arten"].items():
                        rows.append(["", "        " + a, v, None])
                    for l, v in d["schuldzinsen"].items():
                        rows.append(["", "        " + tr("x_schuldzinsen") % l, v, None])
                    rows.append(["", "        " + tr("x_afa"), -abs(d["afa"]) if d["afa"] else 0, None])
                if J["ohne_kategorie"]["anzahl"]:
                    rows.append(["", tr("x_ohne_kategorie"), J["ohne_kategorie"]["betrag"], J["ohne_kategorie"]["anzahl"]])
            sheets.append(Sheet(ent["name"], [tr("x_jahr"), tr("x_position"), tr("x_betrag"), tr("x_buchungen")], rows, widths=[8, 56, 16, 12], freeze="A2", bold_rows=bold))
        return sheets or [Sheet(tr("x_steuer"), [tr("x_hinweis")], [[tr("x_keine_daten")]])]

    if was == "transactions":
        ums = app.umsatzliste()
        if bereich:
            ums = [u for u in ums if u["entitaet"] == bereich]
        counts = Belege(app.store, app.config).counts()
        rows = [[u["datum"], u["konto_name"], u["name"], u["zweck"], u["betrag"], u["kategorie"], counts.get(u["id"], 0), u["id"]] for u in ums]
        return [Sheet(tr("s_umsaetze") + (name if bereich else ""), [tr("x_datum"), tr("x_konto"), tr("x_name"), tr("x_zweck"), tr("x_betrag"), tr("x_kategorie"), tr("x_belege"), "ID"],
                      rows, widths=[12, 26, 30, 50, 14, 30, 8, 10], freeze="A2")]

    if was == "holdings":
        rows, bold = [], []
        for d in ds.get("depots", []):
            rows.append([d["name"], "", "", "", None, None, d["einstand"], d["summe"]]); bold.append(len(rows) - 1)
            for p in d["positionen"]:
                rows.append(["", p["name"], p["isin"], p["klasse"], p["menge"], p["kurs"], p["einstand"], p["wert"]])
        return [Sheet(tr("x_depots"), [tr("x_depot"), tr("x_position"), "ISIN", tr("x_klasse"), tr("x_menge"), tr("x_kurs"), tr("x_einstand"), tr("x_wert")], rows,
                      widths=[26, 36, 16, 14, 12, 12, 14, 14], freeze="A2", bold_rows=bold)]

    if was == "receipts":
        bl = Belege(app.store, app.config)
        names = {k["uuid"]: k["name"] for k in ds.get("konten", [])}
        names.update(ds.get("bereich_namen") or {})
        rows = [[e.get("datum"), e.get("betrag"), e.get("name"), names.get(e.get("konto") or "", ""), names.get(e.get("entitaet") or "", ""),
                 e["pfad"], e.get("notiz", ""), e.get("tx_id")] for e in bl.entries()]
        return [Sheet(tr("x_belege"), [tr("x_datum"), tr("x_betrag"), tr("x_name"), tr("x_konto"), tr("x_bereich"), tr("x_datei"), tr("x_notiz"), tr("x_umsatz_id")], rows,
                      widths=[12, 14, 30, 26, 20, 50, 30, 10], freeze="A2")]

    if was == "accounts":
        rows = [["    " * k["ebene"] + k["name"], k["uuid"],
                 tr("x_gruppe" if k["gruppe"] else ("x_depot" if k["depot"] else ("x_manuell" if k["manuell"] else "x_bank"))),
                 role_label(k["rolle"]) if k["rolle"] else "", k["saldo"], k.get("aktualisiert") or ""] for k in ds.get("konten", [])]
        return [Sheet(tr("x_konten"), [tr("x_konto"), "UUID", tr("x_typ"), tr("x_rolle"), tr("x_saldo"), tr("x_aktualisiert")], rows, widths=[46, 38, 10, 16, 16, 18])]
    raise ValueError(tr("s_unbekannter_export") % was)


def _parse_balance_csv(text: str) -> Dict[str, Dict[str, float]]:
    """Kontoname -> {JJJJ-MM: Saldo am Monatsende} aus CSV-Text (Langformat oder Matrix), siehe history_import."""
    return history_import.balances_from_rows(history_import.read_csv_rows(text))


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
            return auth.is_loopback(self._remote())

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
                raise ValueError(tr("s_anfrage_zu_gross_d_mb") % (n // 1048576, limit // 1048576))
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
            m = re.match(r"^/docs/img/((?:de|en)/[a-z0-9_]+\.png)$", path)      # help images (made-up sample data)
            if m:
                fp = os.path.join(HERE, "docs", "img", *m.group(1).split("/"))
                if not os.path.isfile(fp):
                    return self._raw(404, b"nicht gefunden", "text/plain; charset=utf-8")
                with open(fp, "rb") as f:
                    return self._raw(200, f.read(), "image/png", cache="max-age=86400")
            name = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/i18n.js": "i18n.js", "/app.css": "app.css",
                    "/icon.svg": "icon.svg", "/icon-180.png": "icon-180.png", "/icon-512.png": "icon-512.png",
                    "/manifest.webmanifest": "manifest.webmanifest", "/sw.js": "sw.js"}.get(path)
            fp = os.path.join(WEB_DIR, name) if name else None
            if not fp or not os.path.exists(fp):
                return self._raw(404, b"nicht gefunden", "text/plain; charset=utf-8")
            with open(fp, "rb") as f:
                body = f.read()
            if name in ("sw.js", "index.html"):
                body = body.replace(b"__VERSION__", version().encode("utf-8"))
            ctype = {"html": "text/html; charset=utf-8", "js": "application/javascript; charset=utf-8", "png": "image/png",
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
                                        "touchid": auth.touchid_available() and self._loopback() and app.touchid_on(),
                                        "touchid_verfuegbar": auth.touchid_available() and self._loopback(),
                                        "gesperrt_sekunden": app.sessions.locked(self._remote()), "lokal": self._loopback(), "instanz": app.instance,
                                        "offline_kopie": app.offline_copy(), "version": version()})
            s = self._session()
            if s is None:
                return self._json(401, {"fehler": "nicht angemeldet"})
            try:
                return self._get(u.path, q, s)
            except ValueError as e:
                return self._json(400, {"fehler": str(e)})
            except (BrokenPipeError, ConnectionResetError):
                log.debug("GET %s: connection closed by client", u.path)
                return None
            except Exception as e:
                log.exception("GET %s", u.path)
                return self._json(500, {"fehler": tr("s_interner_fehler_s") % e})

        def _get(self, path: str, q: dict, s: dict):
            if path == "/api/status":
                app.reload_config_if_changed()
                return self._json(200, app.status(self._loopback(), frisch=q.get("fresh") == "1"))
            if path == "/api/dataset":
                return self._json(200, app.dataset())
            if path == "/api/config":
                app.reload_config_if_changed()
                return self._json(200, app.config)
            if path == "/api/plan":
                return self._json(200, app.plan_for(q.get("area") or ""))
            if path == "/api/accounts":
                ds = app.store.load_shared("dataset.json", {}) or {}
                if app.ledger is not None:
                    return self._json(200, {"konten": account_tree(app.ledger, app.config, None, ds.get("bereiche") or None), "stand": app.ledger_time.isoformat()})
                return self._json(200, {"konten": ds.get("konten", []), "stand": ds.get("erstellt")})
            if path == "/api/categories":
                return self._json(200, {"kategorien": app.categories()})
            if path == "/api/offline/verifier":
                rec = app.auth_record()
                return self._json(200, {"offline": rec.get("offline") if app.offline_copy() else None, "sperre_minuten": int(app.config["oberflaeche"].get("sperre_minuten", 15)),
                                        "stand": datetime.now().strftime("%Y-%m-%d %H:%M")})
            if path == "/api/sync":
                r = app.abruf() or {"neuester": None, "konten": [], "zurueck": [], "zurueck_anzahl": 0}
                ds = app.store.load_shared("dataset.json", {}) or {}
                bereich = {k["uuid"]: k.get("bereich") or "" for k in ds.get("konten") or []}
                # Depots: MoneyMoney gibt ihren Wertverlauf nicht heraus -- Kontor zeichnet ihn selbst auf (Monatsende-Staende)
                st = app.store.load_shared("state.json", {}) or {}
                snaps, hist = st.get("snapshots") or {}, st.get("historie") or {}
                mmk = (app.store.load_shared(MM_HISTORY_FILE, {}) or {}).get("konten") or {}
                depots = []
                for a in (app.ledger.accounts.values() if app.ledger is not None else []):
                    if a.group or not a.portfolio or not a.path:
                        continue
                    rec = sorted(mk for mk, v in snaps.items() if a.uuid in v)
                    own = sorted(mk for mk, v in (hist.get(a.uuid) or {}).items() if v is not None)
                    aus_mm = sorted(mmk.get(a.uuid) or {})
                    known = sorted(set(rec) | set(own) | set(aus_mm))
                    depots.append({"uuid": a.uuid, "name": a.name, "pfad": a.path, "bereich": bereich.get(a.uuid, ""),
                                   "aufgezeichnet_seit": rec[0] if rec else None, "eigene": len(own), "aus_moneymoney": len(aus_mm), "erster_stand": known[0] if known else None,
                                   "erste_buchung": None})
                return self._json(200, dict(r, konten=[dict(k, bereich=bereich.get(k["uuid"], "")) for k in r["konten"]], depots=depots, luecken=st.get("luecken") or [], mm_verlauf=st.get("mm_verlauf"),
                                            aufzeichnung_seit=min(snaps) if snaps else None,
                                            gelesen=app.ledger_time.strftime("%Y-%m-%d %H:%M") if app.ledger_time else None,
                                            voll=app.full_read_info()))
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
            if path == "/api/transactions":
                return self._json(200, self._umsaetze(q))
            if path == "/api/receipts":
                bl = Belege(app.store, app.config)
                return self._json(200, {"eintraege": [dict(e, status=file_status(bl.full_path(e))) if e.get("extern") else e for e in reversed(bl.entries())],
                                        "fehlend": bl.check(), "ordner": bl.folder, "dateien": bl.listing() if q.get("files") == "1" else []})
            if path == "/api/receipts/file":
                bl = Belege(app.store, app.config)
                e = next((x for x in bl.entries() if x["id"] == q.get("id")), None)
                if e is None:
                    return self._json(404, {"fehler": tr("s_beleg_nicht_im_index")})
                full = bl.full_path(e)
                if (not e.get("extern") and not full.startswith(os.path.normpath(bl.folder) + os.sep)) or not os.path.isfile(full):
                    return self._json(404, {"fehler": tr("s_datei_fehlt_oder_nicht_geladen") % e["pfad"]})
                with open(full, "rb") as f:
                    data = f.read()
                ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                disp = "inline" if ctype.startswith(("image/", "application/pdf", "text/")) else "attachment"
                return self._raw(200, data, ctype, {"Content-Disposition": '%s; filename="%s"' % (disp, os.path.basename(full).replace('"', ""))})
            if path == "/api/export/property.xlsx":
                im = next((x for x in app.config.get("immobilien") or [] if str(x.get("id")) == q.get("id")), None)
                if not im:
                    return self._json(404, {"fehler": tr("s_immobilie_nicht_gefunden")})
                kalks = im.get("kalkulationen") or []
                k = next((x for x in kalks if str(x.get("id")) == q.get("calculation")), None) or next((x for x in kalks if x.get("aktiv")), kalks[0] if kalks else None)
                if not k:
                    return self._json(404, {"fehler": "Keine Kalkulation."})
                res = realestate.berechne(k.get("eingaben") or {}, date.today())
                data = workbook(realestate.sheets(res))
                return self._raw(200, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 {"Content-Disposition": 'attachment; filename="Kontor-%s-%s-%s.xlsx"' % (tr("xf_property"), str(im.get("name") or tr("x_objekt")).replace('"', "").replace("/", "-"), date.today().isoformat())})
            if path.startswith("/api/export/"):
                was = path[len("/api/export/"):].replace(".xlsx", "")
                data = workbook(export_sheets(app, was, q.get("area"), "jahre" if q.get("mode") == "years" else "monate"))
                return self._raw(200, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 {"Content-Disposition": 'attachment; filename="Kontor-%s-%s.xlsx"' % (tr(EXPORT_FILE_KEYS[was]) if was in EXPORT_FILE_KEYS else was, date.today().isoformat())})
            if path == "/api/package/export":
                name = (q.get("name") or "Kontor-Einstellungen").replace('"', "")
                # zum Weitergeben an eine andere MoneyMoney-Installation: Konten ueber Namen/Pfade, ohne Planung und Daten
                pkg = export_package(app.config, name, strip_uuids=True, plan=None, ledger=app.ledger)
                return self._raw(200, json.dumps(pkg, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="%s.kontor.json"' % name})
            if path == "/api/help":
                # help = docs/help.de.md or docs/help.en.md (the same file as on GitHub)
                fn = "help.en.md" if (q.get("lang") or (app.config.get("oberflaeche") or {}).get("sprache")) == "en" else "help.de.md"
                try:
                    with open(os.path.join(HERE, "docs", fn), encoding="utf-8") as f:
                        text = f.read()
                except OSError:
                    return self._json(200, {"text": "", "bilder": {}})
                return self._json(200, {"text": text, "bilder": help_image_sizes(text)})
            if path == "/api/remote/acl":
                import tls_cert
                return self._json(200, tls_cert.access_check(int((app.config.get("oberflaeche") or {}).get("port") or 8765)))
            if path == "/api/remote":
                if q.get("fresh"):
                    app.tailscale(fresh=True)
                return self._json(200, dict(app.remote_info(), lokal=self._is_local(s)))
            if path == "/api/timemachine":
                return self._json(200, {"status": timemachine_status(app.data_dir)})
            if path == "/api/diagnostics":
                txt = diagnose(app.store, app.data_dir, app.config, app.status(self._loopback()), mask_names=q.get("names") != "1")
                return self._raw(200, txt.encode("utf-8"), "text/plain; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="Kontor-Diagnose-%s.txt"' % date.today().isoformat()})
            if path == "/api/check/status":
                return self._json(200, dict(getattr(app, "lesen", {"laeuft": False}), jetzt=time.time()))
            if path == "/api/update/status":
                return self._json(200, {"info": app.update_info, "geprueft": app.update_checked, "version": version(), "datum": updates.installed_date(),
                                        "changelog": updates.changelog()})
            if path == "/api/history":
                return self._json(200, self._historie(q.get("account") or "", q.get("source") if q.get("source") in ("umsaetze", "stand") else None))
            if path == "/api/history/mm-status":
                st = app.store.load_shared("state.json", {}) or {}
                return self._json(200, dict(app.mmh, letzte=st.get("mm_verlauf"), moneymoney_laeuft=is_running(), lokal=self._is_local(s)))
            if path == "/api/categories/kontor":
                kat = categorize.load(app.store)
                anzahl: Dict[str, int] = {}                # Umsaetze je Kategorie in MoneyMoney (fuer die Auswahl)
                for t in (app.ledger.txs if app.ledger is not None else []):
                    if t.id > 0:
                        p = categorize.mm_of(t)
                        if p:
                            anzahl[p] = anzahl.get(p, 0) + 1
                return self._json(200, {"baum": sorted(kat["baum"], key=lambda k: k["pfad"].lower()), "regeln": kat["regeln"],
                                        "statistik": categorize.stats(kat, app.ledger) if app.ledger is not None else {},
                                        "einstellungen": app.config.get("kategorien") or {}, "mm_kategorien": [str(c.get("path") or c.get("name") or "") for c in app.categories_raw],
                                        "verwendung": kat.get("verwendung") or {}, "anzahl": anzahl})
            if path == "/api/categories/unassigned":
                if app.ledger is None:
                    return self._json(200, {"offen": 0, "gruppen": [], "gruppen_gesamt": 0, "hinweis": tr("s_noch_kein_lauf_moneymoney_lesen")})
                kat = categorize.load(app.store)
                bereich_of = {a.uuid: b["id"] for b in bereiche_for(app.ledger, app.config) for a in b["leaves"]}
                res = categorize.open_items(kat, app.ledger, bereich_of, int(q["year"]) if q.get("year") else None, q.get("area") or None,
                                            float(q.get("min") or 0), int(q.get("limit") or 300))
                # Zuordnungen, die auf eine Kategorie in MoneyMoney warten (dort anlegen, dann traegt Kontor nach)
                wart: Dict[str, int] = {}
                for z in kat["zuordnung"].values():
                    if z.get("w"):
                        wart[z["k"]] = wart.get(z["k"], 0) + 1
                res["wartend"] = [{"kategorie": k, "anzahl": n} for k, n in sorted(wart.items())]
                res["zurueckschreiben"] = app.mm_write_allowed(self._is_local(s))
                return self._json(200, res)
            if path == "/api/properties":
                return self._json(200, {"immobilien": app.config.get("immobilien") or [], "ergebnisse": {k: {kk: vv for kk, vv in v.items() if kk != "reihen"}
                                                                                                        for k, v in immo_results(app.config, date.today()).items()}})
            if path == "/api/properties/template":
                return self._json(200, {"eingaben": realestate.normalize({"name": "Neues Objekt", "uebergang": date.today().replace(day=1).isoformat()})})
            if path == "/api/file/status":
                full = os.path.expanduser(q.get("path") or "")
                st = file_status(full) if full else "fehlt"
                return self._json(200, {"status": st, "groesse": os.path.getsize(full) if st == "ok" else None})
            return self._json(404, {"fehler": "unbekannt"})

        def _historie_einlesen(self, s: dict):
            """Kontostaende aus MoneyMoney: hochgeladene (verschluesselte) Datenbank nur in den Arbeitsspeicher lesen und im
            Hintergrund verarbeiten (Passwortfenster des Helfers); der Fortschritt kommt ueber /api/history/mm-status."""
            n = int(self.headers.get("Content-Length") or 0)

            def ablehnen(code: int, text: str, feld: str = "text"):
                # Rest der Datei verwerfen, damit der Browser die Antwort sicher erhaelt
                self.close_connection = True
                left, tmp = max(0, n), bytearray(1 << 20)
                while left > 0:
                    k = self.rfile.readinto(memoryview(tmp)[:min(left, len(tmp))])
                    if not k:
                        break
                    left -= k
                mm_history._wipe(tmp)
                return self._json(code, {"ok": False, feld: text})
            if not self._is_local(s):
                return ablehnen(403, tr("s_nur_direkt_am_mac_moeglich"), "fehler")
            if mm_history.AKTIV.is_set() or app.mmh.get("laeuft"):
                return ablehnen(409, tr("s_laeuft_bereits_bitte_das_passwortfenst"), "fehler")
            if is_running():
                return ablehnen(200, tr("s_bitte_moneymoney_zuerst_beenden_q"))
            if app.ledger is None:
                return ablehnen(200, tr("s_erst_die_konten_aus_moneymoney"))
            try:
                buf = mm_history.receive(self.rfile, n)
            except mm_history.HistorieError as e:
                self.close_connection = True
                return self._json(200, {"ok": False, "text": str(e)})
            app.mmh = {"laeuft": True, "schritt": "received", "ergebnis": None}
            threading.Thread(target=app.historie_einlesen, args=(buf,), name="kontor-mm-historie", daemon=True).start()
            del buf
            return self._json(200, {"ok": True, "laeuft": True})

        def _historie(self, uuid: str, quelle: Optional[str] = None) -> dict:
            """Verlauf eines Kontos fuer das Verlauf-Fenster. Mit MoneyMoney-Stand im Speicher direkt fuer dieses eine Konto
            gerechnet (Millisekunden, unabhaengig vom Neubau der gesamten Auswertung), sonst aus dem letzten Bericht."""
            st = app.store.load_shared("state.json", {}) or {}
            hist = dict((st.get("historie") or {}).get(uuid) or {})
            snaps = {mk: v[uuid] for mk, v in (st.get("snapshots") or {}).items() if uuid in v}
            mmh = app.store.load_shared(MM_HISTORY_FILE, {}) or {}
            mmv, mm_start = dict((mmh.get("konten") or {}).get(uuid) or {}), (mmh.get("anfang") or {}).get(uuid)
            vcfg = (app.config.get("bilanz") or {}).get("verlauf") or {}
            explizit = next((v for ref, v in vcfg.items() if ref.split("|")[0].strip() == uuid and v in ("umsaetze", "stand")), None)
            ledger = app.ledger
            acc = ledger.accounts.get(uuid) if ledger is not None else None
            ds = app.store.load_shared("dataset.json", {}) or {}
            kinfo = next((x for x in ds.get("konten", []) if x.get("uuid") == uuid), {})
            depot = bool(acc.portfolio) if acc else bool(kinfo.get("depot"))
            q = quelle or explizit or ("stand" if depot else "umsaetze")
            out = {"konto": uuid, "name": acc.name if acc else kinfo.get("name", ""), "quelle": q, "quelle_explizit": bool(explizit or quelle),
                   "quelle_gespeichert": explizit or ("stand" if depot else "umsaetze"),
                   "depot": depot, "manuell": hist, "aufgezeichnet": snaps, "moneymoney": mmv, "werte": {}, "hinweis": None, "anker": [],
                   "live": acc is not None, "bericht_laeuft": app.bericht_status().get("laeuft", False)}
            if acc is not None:
                today = date.today()
                months = account_months(ledger, acc, today, list(hist) + (list(snaps) + list(mmv) if depot else []))
                werte, hinweis, anker = account_balance_series(ledger, acc, months, q, st.get("snapshots") or {}, hist, today, app.config, mmv, mm_start)
                out.update({"werte": werte, "hinweis": hinweis, "anker": anker})
                # Pruefung der Rueckrechnung: vorgemerkte Umsaetze, Anfangssaldo vor der ersten Buchung
                alle = ledger.transactions(uuid, booked_only=False)
                vorgemerkt = [t for t in alle if not t.booked]
                gebucht = [t for t in alle if t.booked]
                info = {"vorgemerkt_anzahl": len(vorgemerkt), "vorgemerkt_summe": round(sum(t.amount for t in vorgemerkt), 2),
                        "buchungen": len(gebucht), "erste_buchung": min((t.booking_date for t in gebucht), default=None),
                        "anfangssaldo": round(acc.balance - sum(t.amount for t in gebucht), 2)}
                if info["erste_buchung"]:
                    info["erste_buchung"] = info["erste_buchung"].isoformat()
                out["pruefung"] = info
            else:
                for b in ds.get("bereiche", {}).values():
                    for r in (b.get("bilanz") or {}).get("zeilen") or []:
                        if r.get("id") == uuid:
                            out["werte"] = r.get("werte") or {}
            return out

        def _umsaetze(self, q: dict) -> dict:
            ums = app.umsatzliste()
            counts = Belege(app.store, app.config).counts()
            qs = (q.get("q") or "").lower().strip()
            limit = min(5000, int(q.get("limit", "500")))
            out, total = [], 0
            jahre = sorted({t["datum"][:4] for t in ums}, reverse=True)
            for t in ums:
                if q.get("year") and not t["datum"].startswith(q["year"]):
                    continue
                if q.get("account") and t["konto"] != q["account"]:
                    continue
                if q.get("entity") and t["entitaet"] != q["entity"]:
                    continue
                if q.get("uncategorized") == "1" and t["kategorie"]:
                    continue
                if q.get("without_receipt") == "1" and counts.get(t["id"]):
                    continue
                if q.get("with_receipt") == "1" and not counts.get(t["id"]):
                    continue
                if q.get("direction") == "out" and t["betrag"] >= 0:
                    continue
                if q.get("direction") == "in" and t["betrag"] < 0:
                    continue
                if q.get("from") and t["datum"] < q["from"]:
                    continue
                if q.get("to") and t["datum"] > q["to"]:
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
                body = {} if u.path == "/api/history/mm-import" else self._body(MAX_UPLOAD if u.path == "/api/receipts/upload" else MAX_BODY)
            except (ValueError, json.JSONDecodeError) as e:
                return self._json(400, {"fehler": tr("s_ungueltige_anfrage_s") % e})
            remote = self._remote()

            if u.path == "/api/setup":
                if app.auth_record() or not self._loopback():
                    return self._json(403, {"fehler": tr("s_einrichtung_nur_einmal_und_nur")})
                err = auth.password_ok(str(body.get("passwort", "")))
                if err:
                    return self._json(400, {"fehler": err})
                app.store.save("auth.json", auth.with_offline(auth.hash_password(str(body["passwort"])), str(body["passwort"])))
                if isinstance(body.get("touchid"), bool) or body.get("sprache") in i18n.LANGS:
                    cfg = copy.deepcopy(app.config)
                    if isinstance(body.get("touchid"), bool):
                        cfg.setdefault("oberflaeche", {})["touchid"] = body["touchid"]
                    if body.get("sprache") in i18n.LANGS:
                        cfg.setdefault("oberflaeche", {})["sprache"] = body["sprache"]
                    app.save_config(cfg)
                s = app.sessions.create(remote, "passwort")
                log.info("Password set, setup started")
                return self._json(200, {"ok": True, "csrf": s["csrf"]}, self._set_cookie(s["token"]))
            if u.path == "/api/login":
                wait = app.sessions.locked(remote)
                if wait:
                    return self._json(429, {"fehler": tr("s_zu_viele_fehlversuche") % wait})
                rec = app.auth_record()
                if not rec:
                    return self._json(403, {"fehler": tr("s_noch_kein_passwort_festgelegt_einricht")})
                if auth.verify_password(str(body.get("passwort", "")), rec):
                    app.sessions.clear_fails(remote)
                    if not rec.get("offline"):
                        app.store.save("auth.json", auth.with_offline(rec, str(body.get("passwort", ""))))
                        log.info("Offline verifier for the iPhone view created")
                    s = app.sessions.create(remote, "passwort")
                    log.info("Login with password from %s", remote)
                    return self._json(200, {"ok": True, "csrf": s["csrf"]}, self._set_cookie(s["token"]))
                app.sessions.fail(remote)
                time.sleep(0.5)
                log.warning("Failed login from %s", remote)
                return self._json(401, {"fehler": tr("s_passwort_falsch")})
            if u.path == "/api/touchid":
                if not self._loopback() or not auth.touchid_available():
                    return self._json(403, {"fehler": tr("s_touch_id_nur_an_diesem")})
                if not app.touchid_on():
                    return self._json(403, {"fehler": tr("s_touch_id_ist_in_den")})
                if not app.auth_record():
                    return self._json(403, {"fehler": tr("s_zuerst_ein_passwort_festlegen")})
                if auth.touchid_verify():
                    s = app.sessions.create(remote, "touchid")
                    log.info("Login with Touch ID")
                    return self._json(200, {"ok": True, "csrf": s["csrf"]}, self._set_cookie(s["token"]))
                return self._json(401, {"fehler": tr("s_touch_id_nicht_bestaetigt")})

            s = self._session()
            if s is None:
                return self._json(401, {"fehler": "nicht angemeldet"})
            if self.headers.get("X-CSRF-Token") != s["csrf"]:
                return self._json(403, {"fehler": tr("s_csrf_pruefung_fehlgeschlagen_seite_neu")})
            if not self._is_local(s) and app.remote_readonly() and u.path not in ("/api/logout", "/api/lock"):
                return self._json(403, {"fehler": tr("s_von_unterwegs_nur_ansehen")})
            if u.path == "/api/history/mm-import":
                return self._historie_einlesen(s)
            t0 = time.time()
            log.debug("%s %s from %s (%d bytes%s)", self.command, u.path, remote, len(json.dumps(body)) if body else 0, ", Mac" if self._is_local(s) else "")
            try:
                res = self._route(u.path, body, s)
                log.debug("%s %s: done in %.2f s", self.command, u.path, time.time() - t0)
                return res
            except ValueError as e:
                log.warning("%s %s rejected: %s", self.command, u.path, e)
                return self._json(400, {"fehler": str(e)})
            except MoneyMoneyError as e:
                log.warning("%s %s: MoneyMoney not available: %s", self.command, u.path, e)
                return self._json(502, {"fehler": unavailable_text(e) or (tr("s_moneymoney_fehler_s") % e)})
            except (BrokenPipeError, ConnectionResetError):
                log.debug("%s %s: connection closed by client", self.command, u.path)
                return None
            except OSError as e:
                log.exception("%s %s: file error", self.command, u.path)
                return self._json(500, {"fehler": "Dateifehler: %s" % e})
            except Exception as e:
                log.exception("%s %s", self.command, u.path)
                return self._json(500, {"fehler": tr("s_interner_fehler_s") % e})

        def _is_local(self, s: dict) -> bool:
            return auth.is_loopback(s.get("remote", "")) and self._loopback()

        def _route(self, path: str, body: dict, s: dict):
            local = self._is_local(s)
            if path == "/api/logout":
                app.sessions.drop(s["token"])
                return self._json(200, {"ok": True}, self._set_cookie("", clear=True))
            if path == "/api/lock":
                app.sessions.drop_all()
                return self._json(200, {"ok": True}, self._set_cookie("", clear=True))
            if path == "/api/password":
                rec = app.auth_record()
                if not auth.verify_password(str(body.get("alt", "")), rec):
                    return self._json(401, {"fehler": tr("s_altes_passwort_falsch")})
                err = auth.password_ok(str(body.get("neu", "")))
                if err:
                    return self._json(400, {"fehler": err})
                app.store.save("auth.json", auth.with_offline(auth.hash_password(str(body["neu"])), str(body["neu"])))
                log.info("Password changed")
                return self._json(200, {"ok": True})
            if path == "/api/config":
                cfg = body.get("config")
                if not isinstance(cfg, dict):
                    return self._json(400, {"fehler": tr("s_config_fehlt")})
                b = (cfg.get("oberflaeche") or {}).get("bind", "127.0.0.1") or "127.0.0.1"
                if not bind_allowed(b):
                    return self._json(400, {"fehler": tr("s_adresse_s_nicht_erlaubt_nur") % b})
                # address, port and certificate: only on the Mac; a new port must be free; afterwards restart on it
                old_ui, new_ui = app.config.get("oberflaeche") or {}, cfg.get("oberflaeche") or {}
                net_keys = ("bind", "port", "tls_cert", "tls_key")
                net_changed = any((old_ui.get(k) or "") != (new_ui.get(k) or "") for k in net_keys if k != "port") or \
                    int(old_ui.get("port") or 8765) != int(new_ui.get("port") or 8765)
                if net_changed and not local:
                    return self._json(403, {"fehler": tr("s_nur_von_diesem_mac_aus")})
                new_port = int(new_ui.get("port") or 8765)
                if not 1024 <= new_port <= 65535:
                    return self._json(400, {"fehler": tr("s_port_ungueltig")})
                if new_port != int(old_ui.get("port") or 8765) and not port_free(new_port):
                    return self._json(409, {"fehler": tr("s_port_belegt", new_port)})
                findings = check_config(app.ledger, app.categories_raw, merged_config(cfg)) if app.ledger is not None else []
                if any(f["stufe"] == "fehler" for f in findings) and not body.get("trotzdem"):
                    return self._json(409, {"fehler": tr("s_konfiguration_hat_fehler"), "befunde": findings})
                app.save_config(cfg)
                log.info("Configuration saved (%d loans, %d participations, %d mirrors)",
                         len(app.config.get("darlehen") or []), len(app.config.get("beteiligungen") or []), len(app.config.get("saldo_spiegel") or []))
                if net_changed:
                    log.info("Address or port changed -- restarting on port %d", new_port)
                    app.request_restart()
                return self._json(200, {"ok": True, "befunde": findings, "config": app.config, "neustart": net_changed and app.restart_allowed,
                                        "port": new_port, "instanz": app.instance})
            if path == "/api/check":
                if not app.check_lock.acquire(blocking=False):
                    return self._json(409, {"fehler": tr("s_die_pruefung_laeuft_bereits_bitte")})
                try:
                    ledger, err = app.refresh_ledger()
                    if ledger is None:
                        return self._json(200, {"verfuegbar": False, "text": err, "befunde": []})
                    app.request_rebuild(tr("s_verbindung_geprueft"))      # Auswertung auf den frischen Stand bringen (im Hintergrund)
                    findings = check_config(ledger, app.categories_raw, app.config)
                    return self._json(200, {"verfuegbar": True, "befunde": findings, "konten": account_tree(ledger, app.config),
                                            "kategorien": app.categories()})
                finally:
                    app.check_lock.release()
            if path == "/api/sync/gaps":
                app.store.update("state.json", lambda cur: cur.pop("luecken", None), {})
                return self._json(200, {"ok": True})
            if path == "/api/sync":
                if app.ledger is None:
                    return self._json(409, {"fehler": tr("s_noch_kein_stand_aus_moneymoney")})
                try:
                    acc = app.ledger.resolve(str(body.get("konto") or ""))
                except KeyError as e:
                    return self._json(400, {"fehler": str(e)})
                want = body.get("abgerufen")
                cfg = copy.deepcopy(app.config)
                ab = cfg.setdefault("abruf", {})
                for k in ("online", "offline"):
                    ab[k] = [r for r in ab.get(k) or [] if r.split("|")[0].strip() != acc.uuid]
                detected = abruf_arten(app.ledger, cfg)[acc.uuid]["art"]
                if isinstance(want, bool) and (want != (detected == "online")):
                    ab["online" if want else "offline"].append("%s | %s" % (acc.uuid, acc.name))
                app.save_config(cfg)
                return self._json(200, {"ok": True, "abruf": app.abruf()})
            if path == "/api/run":
                dry = body.get("probelauf")
                if dry is False and not local:
                    return self._json(403, {"fehler": tr("s_buchen_nur_von_diesem_mac")})
                if app.running:
                    return self._json(409, {"fehler": tr("s_ein_abgleich_laeuft_bereits")})
                full = True if body.get("voll") else None          # „Alles neu lesen“; sonst schnell, solange kein vollstaendiges Lesen faellig ist
                threading.Thread(target=app.do_run, args=(dry, bool(body.get("force", True))), kwargs={"full": full}, daemon=True).start()
                return self._json(202, {"gestartet": True})
            if path == "/api/report":
                ledger, err = app.refresh_ledger()
                if ledger is None:
                    return self._json(200, {"ok": False, "text": err})
                ok, err = app.rebuild_report(wait=True, grund=tr("s_bericht_aus_moneymoney"))
                return self._json(200, {"ok": ok, "text": err})
            if path == "/api/plan":
                return self._json(200, self._update_plan(body))
            if path.startswith("/api/receipts/"):
                return self._belege(path, body, local)
            if path == "/api/package/import":
                pkg = body.get("paket")
                if isinstance(pkg, str):
                    pkg = json.loads(pkg)
                cfg, unresolved, report = import_package(app.config, pkg, app.ledger, body.get("modus") or "ergaenzen", body.get("zuordnung") or {})
                if unresolved and not body.get("trotzdem"):
                    return self._json(200, {"ok": False, "unaufgeloest": unresolved, "bericht": report,
                                            "hinweis": tr("s_konten_zuordnen_oder_trotzdem_ueberneh")})
                findings = check_config(app.ledger, app.categories_raw, cfg) if app.ledger is not None else []
                app.save_config(cfg)
                if pkg.get("plan") and body.get("mit_plan"):
                    app.store.save("plan.json", pkg["plan"])
                log.info("Settings package '%s' imported (%s)", pkg.get("name"), body.get("modus") or "ergaenzen")
                return self._json(200, {"ok": True, "bericht": report, "befunde": findings, "config": app.config})
            if path == "/api/update/check":
                app.update_info = updates.check((app.config.get("updates") or {}).get("repo") or "stecrz/Kontor")
                app.update_checked = time.time()
                return self._json(200, {"info": app.update_info, "version": version()})
            if path == "/api/update/install":
                if not local:
                    return self._json(403, {"fehler": tr("s_updates_nur_von_diesem_mac")})
                res = updates.install((app.config.get("updates") or {}).get("repo") or "stecrz/Kontor", restart=True)
                if res.get("ok"):
                    log.info("Update installed: %s", res.get("version"))
                return self._json(200, res)
            if path == "/api/history":
                return self._json(200, self._historie_set(body))
            if path == "/api/history/import":
                return self._json(200, self._historie_import(body))
            if path == "/api/language":
                if body.get("sprache") not in i18n.LANGS:
                    raise ValueError("sprache: de|en")
                cfg = copy.deepcopy(app.config)
                cfg.setdefault("oberflaeche", {})["sprache"] = body["sprache"]
                app.save_config(cfg)
                return self._json(200, {"ok": True, "sprache": i18n.lang()})
            if path == "/api/history/mm-reveal":
                if not self._is_local(s):
                    return self._json(403, {"fehler": tr("s_nur_direkt_am_mac_moeglich")})
                mm_history.reveal()
                return self._json(200, {"ok": True})
            if path.startswith("/api/categories/"):
                return self._kategorien(path, body, local)
            if path.startswith("/api/properties"):
                return self._immobilien(path, body)
            if path.startswith("/api/file/"):
                return self._datei(path, body, local)
            if path == "/api/report/rebuild":
                ok, err = app.rebuild_report(wait=bool(body.get("warten")), grund=tr("s_bericht_neu"))
                return self._json(200, {"ok": ok, "text": err, "bericht": app.bericht_status()})
            if path == "/api/backup":
                # vollstaendige Sicherung, mit einem eigenen Passwort verschluesselt (nur am Mac; Passwort wird nirgends abgelegt)
                if not local:
                    return self._json(403, {"fehler": tr("s_nur_von_diesem_mac_aus")})
                st = app.store.load("state.json", {}) or {}
                sich = {"kontor_sicherung": 1, "version": version(), "erstellt": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "config": app.config, "plan": app.plan_all(), "kategorien": categorize.load(app.store),
                        "historie": st.get("historie") or {}, "snapshots": st.get("snapshots") or {},
                        "belege": app.store.load("receipts.json", {}) or {}, "mm_verlauf": app.store.load(MM_HISTORY_FILE, {}) or {}}
                out = backup_encrypt(sich, str(body.get("passwort") or ""))
                log.info("Encrypted backup of all settings created")
                return self._json(200, out)
            if path == "/api/backup/restore":
                if not local:
                    return self._json(403, {"fehler": tr("s_nur_von_diesem_mac_aus")})
                sich = body.get("sicherung") or {}
                if isinstance(sich, dict) and sich.get("kontor_sicherung_verschluesselt"):
                    sich = backup_decrypt(sich, str(body.get("passwort") or ""))
                if not isinstance(sich, dict) or not sich.get("kontor_sicherung") or not isinstance(sich.get("config"), dict):
                    raise ValueError(tr("s_keine_kontor_sicherung"))
                teile = []
                app.save_config(sich["config"]); teile.append(tr("s_teil_einstellungen"))
                if isinstance(sich.get("plan"), dict):
                    app.store.save("plan.json", sich["plan"]); teile.append(tr("s_teil_planung"))
                if isinstance(sich.get("kategorien"), dict):
                    categorize.save(app.store, sich["kategorien"]); teile.append(tr("s_teil_kategorien"))
                def _merge(st):
                    if isinstance(sich.get("historie"), dict):
                        st["historie"] = sich["historie"]
                    if isinstance(sich.get("snapshots"), dict) and sich["snapshots"]:
                        st["snapshots"] = {**sich["snapshots"], **(st.get("snapshots") or {})}
                app.store.update("state.json", _merge, {})
                if isinstance(sich.get("historie"), dict):
                    teile.append(tr("s_teil_verlauf"))
                if isinstance(sich.get("belege"), dict) and sich["belege"] and body.get("mit_belegen", True):
                    app.store.save("receipts.json", sich["belege"]); teile.append(tr("s_teil_belegindex"))
                if isinstance(sich.get("mm_verlauf"), dict) and sich["mm_verlauf"]:
                    app.store.save(MM_HISTORY_FILE, sich["mm_verlauf"]); teile.append(tr("s_teil_mm_verlauf"))
                log.info("Backup restored: %s", ", ".join(teile))
                ok, err = app.rebuild_report(wait=bool(body.get("warten")), grund=tr("s_grund_sicherung")) if app.ledger is not None else (False, None)
                return self._json(200, {"ok": True, "teile": teile, "bericht": ok, "config": app.config})
            if path == "/api/reset":
                if not local:
                    return self._json(403, {"fehler": tr("s_zuruecksetzen_nur_von_diesem_mac")})
                if not auth.verify_password(str(body.get("passwort", "")), app.auth_record()):
                    time.sleep(0.5)
                    return self._json(401, {"fehler": tr("s_passwort_falsch")})
                dateien = ["config.json", "plan.json", "state.json", "dataset.json", "transactions.json", "categories.json", "receipts.json", "moneymoney-ledger.bin", "mm-history.json"]
                if body.get("mit_passwort"):
                    dateien.append("auth.json")
                for name in dateien:
                    app.store.delete(name)
                app.config = merged_config({})
                app.ledger, app.ledger_time, app.categories_raw, app.last_result, app.last_run_at, app.umsaetze = None, None, [], None, None, None
                app.sessions.drop_all()
                log.warning("Program reset (%s); receipt files and log kept", ", ".join(dateien))
                return self._json(200, {"ok": True, "neu_einrichten": bool(body.get("mit_passwort"))}, self._set_cookie("", clear=True))
            if path == "/api/remote":
                return self._remote_setup(body, local)
            if path == "/api/timemachine-exclusion":
                if not local:
                    return self._json(403, {"fehler": tr("s_nur_von_diesem_mac_aus")})
                flag = "addexclusion" if body.get("ausschliessen") else "removeexclusion"
                try:
                    r = subprocess.run(["tmutil", flag, app.data_dir], capture_output=True, text=True, timeout=30)
                    return self._json(200, {"ok": r.returncode == 0, "text": (r.stdout + r.stderr).strip(), "status": timemachine_status(app.data_dir)})
                except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                    return self._json(200, {"ok": False, "text": str(e), "status": "unbekannt"})
            return self._json(404, {"fehler": "unbekannt"})

        def _remote_setup(self, body: dict, local: bool):
            """Zugriff vom iPhone ein-/ausschalten und fein einstellen -- nur am Mac."""
            import tls_cert
            if not local:
                return self._json(403, {"fehler": tr("s_nur_von_diesem_mac_aus")})
            aktion = body.get("aktion")
            cfg = copy.deepcopy(app.config)
            ui = cfg.setdefault("oberflaeche", {})
            neustart = False
            if aktion == "einstellungen":
                for k in ("fern_nur_ansehen", "offline_kopie"):
                    if k in body:
                        ui[k] = bool(body[k])
            elif aktion == "ein":                 # Zertifikat ueber Tailscale, Adresse = Tailscale-Adresse des Macs
                try:
                    r = tls_cert.setup(cfg, app.data_dir)
                except Exception as e:
                    log.warning("Remote access: certificate not available: %s", e)
                    return self._json(200, {"ok": False, "text": str(e), "tailscale": app.tailscale(fresh=True)})
                cfg["oberflaeche"] = dict(r["oberflaeche"], bind=r["ip"])
                neustart = True
            elif aktion == "ein_http":            # ohne Zertifikat (nur ueber Tailscale verschluesselt, keine Offline-Ansicht)
                st = app.tailscale(fresh=True)
                if not st.get("verbunden") or not st.get("ip"):
                    return self._json(200, {"ok": False, "text": tr("s_tailscale_ist_nicht_verbunden_kein"), "tailscale": st})
                ui.update(bind=st["ip"], tls_cert="", tls_key="")
                neustart = True
            elif aktion == "aus":
                ui["bind"] = "127.0.0.1"
                neustart = True
            else:
                raise ValueError("Unbekannte Aktion.")
            app.save_config(cfg)
            log.info("Remote access settings changed: %s", aktion)
            if neustart:
                app.request_restart()
            return self._json(200, {"ok": True, "neustart": neustart and app.restart_allowed, "instanz": app.instance, "info": app.remote_info()})

        def _belege(self, path: str, body: dict, local: bool):
            bl = Belege(app.store, app.config)
            # Der Belegordner wird erst nach Rueckfrage angelegt (einmalig; ein in den Einstellungen gewaehlter Ordner gilt als bestaetigt)
            if path in ("/api/receipts/upload", "/api/receipts/open", "/api/receipts/export") and not os.path.isdir(bl.folder):
                bcfg = app.config.get("belege") or {}
                if body.get("ordner_anlegen"):
                    cfg = copy.deepcopy(app.config)
                    cfg.setdefault("belege", {})["ordner_bestaetigt"] = True
                    app.save_config(cfg)
                elif not bcfg.get("ordner_bestaetigt"):
                    return self._json(409, {"fehler": tr("s_der_belegordner_s_existiert_noch") % bl.folder, "ordner_bestaetigen": True, "ordner": bl.folder})
            ums = {t["id"]: t for t in (app.umsatzliste())}
            ds = app.store.load_shared("dataset.json", {}) or {}
            names = {k["uuid"]: k["name"] for k in ds.get("konten", [])}
            names.update(ds.get("bereich_namen") or {})

            def tx_of(body):
                tid = body.get("tx_id")
                if tid in (None, ""):
                    return None
                t = ums.get(int(tid))
                if t is None:
                    raise ValueError(tr("s_umsatz_s_nicht_gefunden_liste") % tid)
                return dict(t, entitaet_name=names.get(t["entitaet"], ""))

            if path == "/api/receipts/upload":
                try:
                    data = base64.b64decode(str(body.get("inhalt") or ""), validate=True)
                except Exception:
                    raise ValueError(tr("s_dateiinhalt_unlesbar"))
                e = bl.add_bytes(tx_of(body), str(body.get("datei_name") or "Beleg"), data, str(body.get("notiz") or ""))
                if (app.config.get("belege") or {}).get("kommentar_schreiben") and e.get("tx_id") is not None and local:
                    try:
                        app.bridge_factory(False).set_transaction(e["tx_id"], comment="Beleg: " + e["pfad"])
                    except MoneyMoneyError as ex:
                        log.warning("Receipt reference not written to MoneyMoney: %s", ex)
                log.info("Receipt stored (%d KB)", len(data) // 1024)
                return self._json(200, {"ok": True, "eintrag": e})
            if path == "/api/receipts/link":
                if body.get("extern"):
                    e = dict(bl.link_external(tx_of(body), str(body.get("pfad") or ""), str(body.get("notiz") or "")))
                    e["status"] = file_status(e["pfad"])
                else:
                    e = bl.link_existing(tx_of(body), str(body.get("pfad") or ""), str(body.get("notiz") or ""))
                return self._json(200, {"ok": True, "eintrag": e})
            if path == "/api/receipts/remove":
                ok = bl.remove(str(body.get("id") or ""), bool(body.get("datei_loeschen")))
                return self._json(200, {"ok": ok})
            if path == "/api/receipts/update":
                fields = {k: v for k, v in body.items() if k in ("notiz", "name", "datum", "betrag")}
                if "tx_id" in body:
                    t = tx_of(body)
                    fields.update({"tx_id": t["id"], "konto": t["konto"], "entitaet": t["entitaet"]} if t else {"tx_id": None})
                e = bl.update(str(body.get("id") or ""), **fields)
                return self._json(200, {"ok": e is not None, "eintrag": e})
            if path == "/api/receipts/open":
                if not local:
                    return self._json(403, {"fehler": tr("s_nur_von_diesem_mac_aus")})
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
                    return self._json(400, {"fehler": tr("s_oeffnen_im_finder_nur_unter")})
                subprocess.Popen(["open", "-R", target] if os.path.isfile(target) else ["open", target])
                return self._json(200, {"ok": True})
            if path == "/api/receipts/export":
                target = bl.export_zip(str(body.get("jahr") or "") or None, str(body.get("entitaet") or "") or None, names)
                if local and sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", target])
                log.info("Receipt export created")
                return self._json(200, {"ok": True, "datei": target})
            return self._json(404, {"fehler": "unbekannt"})

        def _historie_set(self, body: dict) -> dict:
            uuid = str(body.get("konto") or "")
            if not uuid:
                raise ValueError(tr("s_konto_fehlt"))
            n = 0

            def _apply(st):
                nonlocal n
                hist = st.setdefault("historie", {}).setdefault(uuid, {})
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
            app.store.update("state.json", _apply, {})
            if body.get("quelle") in ("umsaetze", "stand"):
                cfg = copy.deepcopy(app.config)
                cfg.setdefault("bilanz", {}).setdefault("verlauf", {})
                ref = next((("%s | %s" % (k["uuid"], k["name"])) for k in (app.store.load_shared("dataset.json", {}) or {}).get("konten", []) if k["uuid"] == uuid), uuid)
                for k in list(cfg["bilanz"]["verlauf"]):
                    if k.split("|", 1)[0].strip() == uuid:
                        cfg["bilanz"]["verlauf"].pop(k)
                cfg["bilanz"]["verlauf"][ref] = body["quelle"]
                app.save_config(cfg)
            ok, err = app.rebuild_report(wait=bool(body.get("warten")), grund="Verlauf")
            log.info("History of account %s: %d month(s) changed%s", uuid[:8], n, (", source " + body["quelle"]) if body.get("quelle") in ("umsaetze", "stand") else "")
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
                    raise ValueError(tr("s_dateiinhalt_unlesbar"))
                if len(raw) > 30 * 1024 * 1024:
                    raise ValueError(tr("s_datei_zu_gross_max_30"))
                parsed, hints = history_import.balances_from_file(str(body.get("name") or ""), raw)
            else:
                parsed = _parse_balance_csv(str(body.get("csv") or ""))
            if not parsed:
                raise ValueError(tr("s_keine_werte_erkannt_erwartet_datum"))
            konten = {k["name"]: k["uuid"] for k in (app.store.load_shared("dataset.json", {}) or {}).get("konten", []) if not k["gruppe"]}
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
                    target = konten.get(name) or history_import.match_account(name, konten)
                preview.append({"name": name or tr("s_ohne_konto"), "uuid": target, "konto": uuid_name.get(target or "", ""), "anzahl": len(months), "von": min(months), "bis": max(months),
                                "sicher": bool(name in konten or name in mapping or (konto and (name == "" or len(parsed) == 1)))})
                if target:
                    assign.setdefault(target, {}).update(months)
            if not body.get("uebernehmen"):
                return {"ok": True, "vorschau": preview, "hinweise": hints}
            total = 0

            def _apply(st):
                nonlocal total
                h = st.setdefault("historie", {})
                for uuid, months in assign.items():
                    if body.get("nur_luecken"):
                        months = {mk: v for mk, v in months.items() if mk not in (h.get(uuid) or {})}
                    h.setdefault(uuid, {}).update(months)
                    total += len(months)
            app.store.update("state.json", _apply, {})
            # importierte Werte sollen gelten -> diese Konten auf "Kontostaende" stellen
            cfg = copy.deepcopy(app.config)
            vc = cfg.setdefault("bilanz", {}).setdefault("verlauf", {})
            umgestellt = 0
            for uuid in assign:
                if not any(k.split("|", 1)[0].strip() == uuid and v == "stand" for k, v in vc.items()):
                    for k in [k for k in vc if k.split("|", 1)[0].strip() == uuid]:
                        vc.pop(k)
                    vc["%s | %s" % (uuid, uuid_name.get(uuid, ""))] = "stand"
                    umgestellt += 1
            if umgestellt:
                app.save_config(cfg)
            ok, err = app.rebuild_report(wait=bool(body.get("warten")), grund="Verlaufsimport")
            log.info("History import: %d values for %d accounts", total, len(assign))
            return {"ok": True, "uebernommen": total, "konten": len(assign), "umgestellt": umgestellt, "bericht": ok, "text": err, "vorschau": preview, "hinweise": hints}

        def _kategorien(self, path: str, body: dict, local: bool):
            kat = categorize.load(app.store)
            if path == "/api/categories/assign":
                ids = [int(x) for x in (body.get("ids") or [])][:5000]
                pfad = str(body.get("kategorie") or "")
                if not ids:
                    raise ValueError(tr("s_keine_umsaetze_angegeben"))
                rule = None
                if body.get("regel") and pfad:
                    r = dict(body["regel"]); r["kategorie"] = pfad
                    rule = categorize.add_rule(kat, r)
                n = categorize.assign(kat, ids, pfad, "manuell", rule["id"] if rule else None)
                modus = str(body.get("modus") or "auto")
                mm = app.write_categories(kat, ids[:2000], pfad, modus if modus in ("auto", "ueberschreiben", "nur_kontor") else "auto", local)
                if rule and app.ledger is not None:
                    categorize.auto_assign(kat, app.ledger, overwrite_mm=bool((app.config.get("kategorien") or {}).get("mm_ueberschreiben")))
                categorize.save(app.store, kat)
                ok, err = app.rebuild_report(wait=bool(body.get("warten")), grund="Zuordnung") if app.ledger is not None else (False, None)
                log.info("%d transaction(s) assigned in Kontor%s", n, " (rule created)" if rule else "")
                return self._json(200, {"ok": True, "anzahl": n, "regel": rule, "mm": mm, "in_moneymoney": mm["geschrieben"], "bericht": ok, "text": err})
            if path == "/api/categories/rule":
                if body.get("loeschen"):
                    kat["regeln"] = [r for r in kat["regeln"] if r.get("id") != str(body.get("loeschen"))]
                    for tid, z in list(kat["zuordnung"].items()):
                        if z.get("r") == str(body.get("loeschen")) and z.get("q") == "regel":
                            del kat["zuordnung"][tid]
                else:
                    categorize.add_rule(kat, body.get("regel") or {})
                if app.ledger is not None:
                    categorize.auto_assign(kat, app.ledger, overwrite_mm=bool((app.config.get("kategorien") or {}).get("mm_ueberschreiben")))
                categorize.save(app.store, kat)
                ok, err = app.rebuild_report(wait=bool(body.get("warten")), grund="Kategorieregel") if app.ledger is not None else (False, None)
                return self._json(200, {"ok": True, "regeln": kat["regeln"], "bericht": ok})
            if path == "/api/categories/learn":
                if app.ledger is None:
                    return self._json(200, {"ok": False, "text": tr("s_noch_kein_lauf_moneymoney_lesen")})
                st = categorize.learn(kat, app.ledger)
                n = categorize.auto_assign(kat, app.ledger, overwrite_mm=bool(body.get("mm_ueberschreiben") or (app.config.get("kategorien") or {}).get("mm_ueberschreiben")))
                categorize.save(app.store, kat)
                ok, err = app.rebuild_report(wait=bool(body.get("warten")), grund="Regeln gelernt")
                return self._json(200, {"ok": True, "gelernt": st, "zugeordnet": n, "bericht": ok})
            if path == "/api/categories/tree":
                aktion = body.get("aktion")
                if aktion == "anlegen":
                    categorize.ensure_category(kat, str(body.get("pfad") or ""), sektion=body.get("sektion"))
                elif aktion == "umbenennen":
                    categorize.rename_category(kat, str(body.get("pfad") or ""), str(body.get("neu") or ""))
                elif aktion == "loeschen":
                    categorize.delete_category(kat, str(body.get("pfad") or ""), body.get("ersatz") or None)
                elif aktion == "mm_uebernehmen":
                    categorize.seed_from_moneymoney(kat, app.categories_raw)
                else:
                    raise ValueError("Unbekannte Aktion.")
                categorize.save(app.store, kat)
                ok, err = app.rebuild_report(wait=bool(body.get("warten")), grund="Kategoriebaum") if (app.ledger is not None and aktion != "anlegen") else (False, None)
                return self._json(200, {"ok": True, "baum": sorted(kat["baum"], key=lambda k: k["pfad"].lower()), "bericht": ok})
            if path == "/api/categories/usage":
                categorize.set_usage(kat, body.get("verwendung") or {})
                if app.ledger is not None:
                    categorize.auto_assign(kat, app.ledger, overwrite_mm=bool((app.config.get("kategorien") or {}).get("mm_ueberschreiben")))
                categorize.save(app.store, kat)
                ok, err = app.rebuild_report(wait=bool(body.get("warten")), grund=tr("s_grund_kategorien_auswahl")) if app.ledger is not None else (False, None)
                log.info("Category usage saved: %d combined, %d not used", sum(1 for v in kat["verwendung"].values() if v == "zusammen"),
                         sum(1 for v in kat["verwendung"].values() if v == "ignorieren"))
                return self._json(200, {"ok": True, "verwendung": kat["verwendung"], "bericht": ok})
            if path == "/api/categories/settings":
                cfg = copy.deepcopy(app.config)
                kc = cfg.setdefault("kategorien", {})
                for k in ("aktiv", "lernen", "mm_ueberschreiben"):
                    if k in body:
                        kc[k] = bool(body[k])
                if "mm_schreiben" in body:          # Zurueckschreiben nach MoneyMoney: nur am Mac umschaltbar
                    if not local:
                        return self._json(403, {"fehler": tr("s_nur_von_diesem_mac_aus")})
                    cfg.setdefault("moneymoney", {})["kategorisieren_erlauben"] = bool(body["mm_schreiben"])
                app.save_config(cfg)
                ok, err = app.rebuild_report(wait=bool(body.get("warten")), grund=tr("s_grund_kategorie_einstellungen")) if app.ledger is not None else (False, None)
                return self._json(200, {"ok": True, "einstellungen": kc, "bericht": ok})
            return self._json(404, {"fehler": "unbekannt"})

        def _immobilien(self, path: str, body: dict):
            if path == "/api/properties/calculate":
                res = realestate.berechne(body.get("eingaben") or {}, date.today())
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
                return self._json(404, {"fehler": tr("s_immobilie_nicht_gefunden")})
            elif aktion == "loeschen":
                lst.remove(im)
                app.save_config(cfg)
                log.info("Property deleted")
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
                realestate.berechne(eing, date.today())          # validiert
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
                    return self._json(400, {"fehler": tr("s_datei_nicht_gefunden_s") % pfad})
                im.setdefault("dokumente", []).append({"id": "d%d" % int(datetime.now().timestamp() * 1000 % 10 ** 9), "titel": body.get("titel") or os.path.basename(pfad),
                                                       "pfad": pfad, "art": body.get("art") or "", "hinzugefuegt": now})
            elif aktion == "dokument_entfernen":
                im["dokumente"] = [d for d in im.get("dokumente") or [] if str(d.get("id")) != str(body.get("dokument_id"))]
            else:
                return self._json(400, {"fehler": "Unbekannte Aktion."})
            app.save_config(cfg)
            log.info("Property %s: %s", im.get("id"), aktion)
            ok, err = app.rebuild_report(wait=bool(body.get("warten")), grund="Immobilie") if app.ledger is not None else (False, None)
            return self._json(200, {"ok": True, "immobilie": im, "bericht": ok})

        def _datei(self, path: str, body: dict, local: bool):
            if not local:
                return self._json(403, {"fehler": tr("s_dateizugriff_nur_von_diesem_mac")})
            if sys.platform != "darwin":
                return self._json(400, {"fehler": "Nur unter macOS."})
            if path == "/api/file/choose":
                art = body.get("art") or "datei"
                prompt = str(body.get("prompt") or tr("s_datei_waehlen")).replace('"', "")
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
                return self._json(400, {"fehler": tr("s_pfad_fehlt")})
            if path == "/api/file/open":
                st = file_status(pfad)
                if st == "fehlt":
                    return self._json(404, {"fehler": tr("s_datei_nicht_gefunden")})
                subprocess.Popen(["open", pfad])
                return self._json(200, {"ok": True, "status": st})
            if path == "/api/file/reveal":
                if not os.path.exists(pfad) and file_status(pfad) == "fehlt":
                    return self._json(404, {"fehler": tr("s_datei_nicht_gefunden")})
                subprocess.Popen(["open", "-R", pfad])
                return self._json(200, {"ok": True})
            if path == "/api/file/load":
                try:
                    r = subprocess.run(["brctl", "download", pfad], capture_output=True, text=True, timeout=30)
                    return self._json(200, {"ok": r.returncode == 0, "text": (r.stdout + r.stderr).strip()})
                except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                    return self._json(200, {"ok": False, "text": str(e)})
            return self._json(404, {"fehler": "unbekannt"})

        def _update_plan(self, body: dict) -> dict:
            plan_all = app.plan_all()
            bereich = str(body.get("bereich") or (app.store.load_shared("dataset.json", {}) or {}).get("haupt") or "")
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
                        raise ValueError(tr("s_monat_fehlt"))
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


BACKUP_ITER = 600_000


def port_free(port: int) -> bool:
    """Can Kontor listen on 127.0.0.1:port? (checked before switching, so the service never restarts onto a busy port)"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def help_image_sizes(text: str) -> Dict[str, List[int]]:
    """Width and height (pixels) of a help file's images from the PNG header, so the page reserves the space up front
    and jumps to anchors land in the right place."""
    out: Dict[str, List[int]] = {}
    for rel in set(re.findall(r"!\[[^\]]*\]\((img/(?:de|en)/[a-z0-9_]+\.png)\)", text)):
        try:
            with open(os.path.join(HERE, "docs", rel), "rb") as f:
                head = f.read(24)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                out[rel] = [int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")]
        except OSError:
            pass
    return out


def backup_encrypt(data: dict, password: str) -> dict:
    """Sicherung mit eigenem Passwort verschluesseln (PBKDF2-SHA256 -> AES-256 + HMAC wie der Datenordner).
    Das Passwort wird weder gespeichert noch protokolliert."""
    import hashlib
    import secrets
    from storage import encrypt
    if len(password) < 8:
        raise ValueError(tr("s_sicherungspasswort_zu_kurz"))
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, BACKUP_ITER, 32)
    blob = encrypt(key, json.dumps(data, ensure_ascii=False).encode("utf-8"))
    return {"kontor_sicherung_verschluesselt": 1, "version": data.get("version"), "erstellt": data.get("erstellt"),
            "kdf": "pbkdf2-sha256", "iter": BACKUP_ITER, "salt": base64.b64encode(salt).decode(), "daten": base64.b64encode(blob).decode()}


def backup_decrypt(wrapper: dict, password: str) -> dict:
    import hashlib
    from storage import StoreError, decrypt
    try:
        salt = base64.b64decode(wrapper["salt"]); blob = base64.b64decode(wrapper["daten"])
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(wrapper.get("iter") or BACKUP_ITER), 32)
        return json.loads(decrypt(key, blob).decode("utf-8"))
    except (KeyError, ValueError, StoreError, binascii.Error):
        raise ValueError(tr("s_sicherung_passwort_falsch"))


def timemachine_status(path: str) -> str:
    """'ausgeschlossen' / 'gesichert' / 'unbekannt' (tmutil isexcluded, nur macOS)."""
    try:
        r = subprocess.run(["tmutil", "isexcluded", path], capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unbekannt"
    out = r.stdout or ""
    return "ausgeschlossen" if "[Excluded]" in out else "gesichert" if "[Included]" in out else "unbekannt"


def restart_process() -> None:
    """Prozess durch sich selbst ersetzen (neuer Code). Gleiche Prozessnummer, launchd bemerkt nichts;
    offene Sockets und die Sperrdatei werden dabei geschlossen (nicht vererbbar)."""
    logging.shutdown()
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except OSError:  # pragma: no cover - dann eben beenden; launchd (KeepAlive) startet neu
        os._exit(0)


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        et, ev = sys.exc_info()[:2]
        if et in (BrokenPipeError, ConnectionResetError, ssl.SSLError, TimeoutError):
            log.debug("Connection %s: %s", client_address[0], ev)
            return
        log.exception("Error handling request from %s", client_address[0])


def serve(app: App) -> None:
    """Oberflaeche auf 127.0.0.1 (immer, http -- fuer den Mac mit Touch ID) und zusaetzlich auf der
    eingestellten Tailscale-Adresse (fuer das iPhone; mit TLS, wenn ein Zertifikat eingetragen ist)."""
    ui = app.config.get("oberflaeche", {}) or {}
    extra = (ui.get("bind") or "127.0.0.1").strip()
    if not bind_allowed(extra):
        log.error("Bind address %s not allowed -- 127.0.0.1 only", extra)
        extra = "127.0.0.1"
    port = int(ui.get("port") or 8765)
    handler = make_handler(app)
    servers = []
    try:
        servers.append(("http", "127.0.0.1", _Server(("127.0.0.1", port), handler)))
    except OSError as e:
        log.error("Port %d on 127.0.0.1 not usable (%s) -- is Kontor already running? Change the port in the settings.", port, e)
        raise SystemExit(2)
    app._handler = handler
    app.start_remote()                      # zweiter Zugang (Tailscale); sonst spaeter erneut vom Zeitplaner
    app.restart_allowed = True
    threading.Thread(target=app.scheduler, daemon=True).start()
    log.info("Kontor %s: UI at %s (data %s)", version(),
             ", ".join("%s://%s:%d/" % (sc, h, port) for sc, h, _ in servers + ([(app.remote_listening[0], app.remote_listening[1], None)] if app.remote_listening else [])),
             "verschluesselt" if app.store.encrypted else "KLARTEXT")
    try:
        servers[0][2].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop.set()
        for _, _, srv in servers:
            srv.shutdown() if srv is not servers[0][2] else None
            srv.server_close()
