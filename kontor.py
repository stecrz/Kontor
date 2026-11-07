#!/usr/bin/env python3
"""Kontor -- Automatisierung, Bilanz, Kapitalfluss, Planung und Belege auf MoneyMoney (macOS).

Befehle:
  start             Dienst starten: Web-Oberflaeche (http://127.0.0.1:8765/) + automatische Laeufe
  open              Oberflaeche im Browser oeffnen (Dienst muss laufen)
  run               Einmaliger Lauf ohne Dienst (--dry-run / --live / --force)
  accounts          Kontenbaum mit UUIDs, Typ, Rolle, letzter Aktualisierung
  check             Konfiguration gegen MoneyMoney pruefen
  status            Letzter Lauf, Verlauf
  password          Passwort der Oberflaeche (neu) setzen -- nur im Terminal am Mac
  package-export    Einstellungen als Paket (.kontor.json) ausgeben (--without-uuid: nur Kontonamen)
  package-import    Einstellungspaket einlesen (DATEI [--replace])
  diagnostics       Diagnosedatei (Protokoll + Konfiguration, maskiert) ausgeben
  update            Neue Version von GitHub pruefen (--install spielt sie ein)
  install           Dienst als Hintergrundprogramm einrichten (startet beim Anmelden, laeuft dauerhaft);
                    uebersetzt den Touch-ID-Helfer.   uninstall entfernt den Dienst wieder (Daten bleiben)
  tls               https über Tailscale einrichten (Zertifikat holen, Adresse setzen) -- nötig für die Offline-Ansicht am iPhone
  version           Versionsnummer

Datenordner: ~/Library/Application Support/Kontor (oder Umgebungsvariable KONTOR_DIR).
Alle Dateien dort sind verschluesselt (Schluessel im macOS-Schluesselbund); nur kontor.log ist Klartext
und enthaelt keine Kontonummern, Salden oder Passwoerter.
"""
from __future__ import annotations

import argparse
import fcntl
import getpass
import json
import logging
import logging.handlers
import os
import plistlib
import subprocess
import sys
from datetime import date
from typing import List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import auth  # noqa: E402
import updates  # noqa: E402
import i18n  # noqa: E402
import mm_categories  # noqa: E402
from mm_bridge import Bridge, MoneyMoneyError  # noqa: E402
from core import (account_tree, check_config, diagnose, export_package, fetch, import_package, merged_config,  # noqa: E402
                     run_once, unavailable_text, version)
from model import Ledger, accounts_from_export, fmt_eur  # noqa: E402
from storage import Store, load_or_create_master_key  # noqa: E402
from i18n import tr  # noqa: E402

log = logging.getLogger("kontor")
DATA_DIR = os.environ.get("KONTOR_DIR") or os.path.expanduser("~/Library/Application Support/Kontor")
LAUNCHD_LABEL = updates.LABEL


def setup_logging(quiet: bool) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        os.chmod(DATA_DIR, 0o700)
    except OSError:
        pass
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    path = os.path.join(DATA_DIR, "kontor.log")
    fh = logging.handlers.RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    # Neue Version: frische Protokolldatei beginnen (die alte bleibt als kontor.log.1 usw.)
    marker = os.path.join(DATA_DIR, "log.version")
    try:
        with open(marker, encoding="utf-8") as f:
            last = f.read().strip()
    except OSError:
        last = ""
    if last != version() and os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            fh.doRollover()
        except OSError:
            pass
    try:
        with open(marker, "w", encoding="utf-8") as f:
            f.write(version())
    except OSError:
        pass
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)          # Datei: alles (ohne Zugangsdaten); Terminal: ab INFO
    root.addHandler(fh)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if not quiet:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(logging.Formatter("%(message)s"))
        sh.setLevel(logging.INFO)
        root.addHandler(sh)


def open_store() -> Store:
    key, source = load_or_create_master_key(DATA_DIR)
    return Store(DATA_DIR, key, source)


def load_config(store: Store) -> dict:
    cfg = merged_config(store.load("config.json", {}) or {})
    i18n.set_lang((cfg.get("oberflaeche") or {}).get("sprache") or "de")
    return cfg


class Lock:
    def __init__(self, name: str):
        self.path = os.path.join(DATA_DIR, name)

    def __enter__(self):
        self.f = open(self.path, "w")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.exit(tr("s_kontor_laeuft_bereits_s") % self.path)
        return self

    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


# ---------------------------------------------------------------------------
# Befehle
# ---------------------------------------------------------------------------

def cmd_start(args) -> int:
    from service import App, serve
    store = open_store()
    with Lock("service.lock"):
        app = App(store, DATA_DIR)
        serve(app)
    return 0


def ui_url(cfg: dict) -> str:
    port = int((cfg.get("oberflaeche") or {}).get("port") or 8765)
    scheme = "https" if (cfg.get("oberflaeche") or {}).get("tls_cert") else "http"
    return "%s://127.0.0.1:%d/" % (scheme, port)


def cmd_oeffnen(args) -> int:
    store = open_store()
    subprocess.run(["open", ui_url(load_config(store))])
    return 0


def cmd_run(args) -> int:
    store = open_store()
    cfg = load_config(store)
    dry = cfg.get("probelauf", True)
    if args.scharf:
        dry = False
    if args.probelauf:
        dry = True
    res = run_once(store, cfg, date.today(), dry, args.force)
    res.pop("_ledger", None); res.pop("_kategorien", None)
    st = res.get("status")
    if st == "nicht_verfuegbar":
        print(res.get("text")); return 0
    if st == "unveraendert":
        print(tr("s_keine_aenderung_in_moneymoney_seit_2")); return 0
    if st == "laeuft_bereits":
        print(tr("s_ein_lauf_ist_bereits_aktiv")); return 1
    if st == "fehler":
        print("FEHLER: %s" % res.get("text")); return 1
    for v in res.get("vorschlaege", []):
        print("  %s  %-50s %14s  %s" % (v["datum"], v["konto"][-50:], fmt_eur(v["betrag"]), v["text"]))
    for w in res.get("warnungen", []):
        print("HINWEIS " + w)
    print(tr("s_s_d_vorschlag_vorschlaege_d") % ("Probelauf" if dry else "Lauf", len(res.get("vorschlaege", [])),
                                                        res.get("geschrieben", 0), (" -- FEHLER: " + res["fehler"]) if res.get("fehler") else ""))
    print(tr("s_oberflaeche_python3_kontor_py_oeffnen"))
    return 1 if res.get("fehler") else 0


def cmd_konten(args) -> int:
    store = open_store()
    cfg = load_config(store)
    try:
        ledger = Ledger(accounts_from_export(Bridge(dry_run=True).export_accounts()), [])
    except MoneyMoneyError as e:
        print(unavailable_text(e) or str(e)); return 2
    print("%-58s %-36s %-8s %-17s %-16s %s" % (tr("s_konto_pfad"), "UUID", tr("x_typ"), tr("x_rolle"), tr("x_aktualisiert"), tr("x_saldo")))
    for k in account_tree(ledger, cfg):
        typ = tr("x_gruppe" if k["gruppe"] else ("x_depot" if k["depot"] else ("x_manuell" if k["manuell"] else "x_bank")))
        print("%-58s %-36s %-8s %-17s %-16s %s" % ("  " * k["ebene"] + k["name"], k["uuid"], typ, k["rolle"],
                                                   k["aktualisiert"] or "", "" if k["gruppe"] else fmt_eur(k["saldo"])))
    return 0


def cmd_check(args) -> int:
    store = open_store()
    cfg = load_config(store)
    b = Bridge(dry_run=True)
    try:
        ledger = fetch(b, cfg, date.today())
        cats = mm_categories.with_paths(b.export_categories())
    except MoneyMoneyError as e:
        print(unavailable_text(e) or str(e)); return 2
    findings = check_config(ledger, cats, cfg)
    for f in findings:
        print("%-8s %s" % (f["stufe"].upper(), f["text"]))
    bad = any(f["stufe"] == "fehler" for f in findings)
    print(tr("s_probelauf_s") % ("EIN" if cfg.get("probelauf", True) else "AUS"))
    print("Ergebnis: %s" % ("alles in Ordnung" if not bad else "FEHLER vorhanden"))
    return 1 if bad else 0


def cmd_status(args) -> int:
    store = open_store()
    st = store.load("state.json", {}) or {}
    last = st.get("letzter_lauf")
    print("Kontor %s -- Datenordner %s" % (version(), DATA_DIR))
    if not last:
        print(tr("s_noch_kein_lauf")); return 0
    print(json.dumps({k: v for k, v in last.items() if k != "vorschlaege"}, ensure_ascii=False, indent=2))
    for v in last.get("vorschlaege", []):
        print("  %s %s %s %s" % (v["datum"], v["konto"], fmt_eur(v["betrag"]), v["text"]))
    return 0


def cmd_passwort(args) -> int:
    store = open_store()
    pw = getpass.getpass(tr("s_neues_passwort_fuer_die_oberflaeche"))
    if pw != getpass.getpass("Wiederholen: "):
        print(tr("s_stimmt_nicht_ueberein")); return 1
    err = auth.password_ok(pw)
    if err:
        print(err); return 1
    store.save("auth.json", auth.with_offline(auth.hash_password(pw), pw))
    print(tr("s_passwort_gesetzt_laufende_sitzungen_bl"))
    return 0


def cmd_paket_export(args) -> int:
    store = open_store()
    cfg = load_config(store)
    ledger = None
    if args.ohne_uuid:
        try:
            ledger = fetch(Bridge(dry_run=True), cfg, date.today())
        except MoneyMoneyError:
            pass
    pkg = export_package(cfg, args.name or "Kontor-Einstellungen", strip_uuids=args.ohne_uuid,
                         plan=(store.load("plan.json", {}) if args.mit_plan else None), ledger=ledger)
    text = json.dumps(pkg, ensure_ascii=False, indent=2)
    if args.datei:
        with open(args.datei, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(args.datei, 0o600)
        print("Geschrieben: %s" % args.datei)
    else:
        print(text)
    return 0


def cmd_paket_import(args) -> int:
    store = open_store()
    cfg = load_config(store)
    with open(args.datei, encoding="utf-8") as f:
        pkg = json.load(f)
    if "kontor_paket" not in pkg and "config" not in pkg and isinstance(pkg, dict):
        pkg = {"kontor_paket": 1, "name": os.path.basename(args.datei), "config": pkg}   # rohe Konfiguration
    ledger = None
    try:
        ledger = fetch(Bridge(dry_run=True), cfg, date.today())
    except MoneyMoneyError as e:
        print(tr("s_hinweis_s_kontoreferenzen_werden_nicht") % (unavailable_text(e) or e))
    new_cfg, unresolved, report = import_package(cfg, pkg, ledger, "ersetzen" if args.ersetzen else "ergaenzen")
    for line in report:
        print("  " + line)
    for u in unresolved:
        print("  NICHT GEFUNDEN: %s (%s)" % (u["label"], u["feld"]))
    if unresolved and not args.trotzdem:
        print(tr("s_nicht_uebernommen_konten_in_moneymoney"))
        return 1
    store.save("config.json", merged_config(new_cfg))
    if pkg.get("plan") and args.mit_plan:
        store.save("plan.json", pkg["plan"])
    print(tr("s_einstellungen_uebernommen_pruefen_pyth"))
    return 0


def cmd_diagnose(args) -> int:
    store = open_store()
    cfg = load_config(store)
    txt = diagnose(store, DATA_DIR, cfg, {"version": version(), "datenordner": DATA_DIR}, mask_names=not args.namen)
    if args.datei:
        with open(args.datei, "w", encoding="utf-8") as f:
            f.write(txt)
        print("Geschrieben: %s" % args.datei)
    else:
        print(txt)
    return 0


def cmd_update(args) -> int:
    store = open_store()
    cfg = load_config(store)
    repo = (cfg.get("updates") or {}).get("repo") or "stecrz/Kontor"
    info = updates.check(repo)
    if info.get("fehler"):
        print(info["fehler"]); return 2
    print(tr("s_installiert_s_verfuegbar_s_s") % (info["aktuell"], info["verfuegbar"], info["quelle"]))
    if not info["neuer"]:
        print(tr("s_kontor_ist_aktuell")); return 0
    if not args.installieren:
        print("Einspielen: python3 kontor.py update --install"); return 0
    res = updates.install(repo, info.get("zip"), restart=True)
    print(res.get("text"))
    return 0 if res.get("ok") else 1


def launchd_path(label: str = LAUNCHD_LABEL) -> str:
    return updates.plist_path(label)


def build_touchid() -> str:
    import auth
    return auth.build_touchid(force=True)


def cmd_install(args) -> int:
    store = open_store()
    cfg = load_config(store)
    if not store.load("auth.json", None):
        print(tr("s_noch_kein_passwort_wird_beim"))
    print(tr("s_touchid_helfer") % build_touchid())
    plist = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [sys.executable, os.path.join(HERE, "kontor.py"), "--quiet", "start"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Interactive",
        "EnvironmentVariables": {"KONTOR_DIR": DATA_DIR, "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
        "StandardOutPath": os.path.join(DATA_DIR, "service.out.log"),
        "StandardErrorPath": os.path.join(DATA_DIR, "service.err.log"),
    }
    os.makedirs(os.path.dirname(launchd_path()), exist_ok=True)
    with open(launchd_path(), "wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(["launchctl", "unload", launchd_path()], capture_output=True)
    r = subprocess.run(["launchctl", "load", launchd_path()], capture_output=True, text=True)
    print(tr("s_dienst_eingerichtet_startet_beim_anmel") % launchd_path())
    if r.returncode != 0:
        print("launchctl: " + (r.stderr or r.stdout))
    print(tr("s_oberflaeche_s_python3_kontor_py") % ui_url(cfg))
    print(tr("s_beim_ersten_lauf_fragt_macos"))
    return 0


def cmd_uninstall(args) -> int:
    if os.path.exists(launchd_path()):
        subprocess.run(["launchctl", "unload", launchd_path()], capture_output=True)
        try:
            os.remove(launchd_path())
        except FileNotFoundError:
            pass
    print(tr("s_dienst_entfernt_daten_bleiben_in") % DATA_DIR)
    return 0


def cmd_tls(args) -> int:
    import tls_cert
    store = open_store()
    cfg = load_config(store)
    if args.aus:
        cfg["oberflaeche"].update({"tls_cert": "", "tls_key": ""})
        store.save("config.json", cfg)
        print("TLS abgeschaltet (Adresse bleibt %s)." % cfg["oberflaeche"].get("bind"))
    else:
        try:
            r = tls_cert.setup(cfg, DATA_DIR)
        except Exception as e:
            print(tr("s_fehler_s") % e); return 1
        cfg["oberflaeche"] = r["oberflaeche"]
        store.save("config.json", cfg)
        print(tr("s_zertifikat_fuer_s_geholt_gueltig") % (r["name"], (r["gueltig_bis"] or "?")[:10], r["ip"]))
        print(tr("s_oberflaeche_nach_dem_neustart_s") % r["url"])
        print(tr("s_das_zertifikat_wird_vom_laufenden"))
    if os.path.exists(launchd_path()):
        r2 = subprocess.run(["launchctl", "kickstart", "-k", "gui/%d/%s" % (os.getuid(), LAUNCHD_LABEL)], capture_output=True, text=True)
        print(tr("s_dienst_neu_gestartet") if r2.returncode == 0 else tr("s_dienst_bitte_neu_starten_bash"))
    else:
        print(tr("s_dienst_neu_starten_bash_install"))
    return 0


def cmd_version(args) -> int:
    print(version())
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="kontor", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quiet", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("start", cmd_start), ("open", cmd_oeffnen), ("accounts", cmd_konten), ("check", cmd_check), ("status", cmd_status),
                     ("password", cmd_passwort), ("install", cmd_install), ("uninstall", cmd_uninstall), ("version", cmd_version)):
        sub.add_parser(name).set_defaults(fn=fn)
    r = sub.add_parser("run"); r.set_defaults(fn=cmd_run)
    r.add_argument("--dry-run", dest="probelauf", action="store_true"); r.add_argument("--live", dest="scharf", action="store_true")
    r.add_argument("--force", action="store_true")
    pe = sub.add_parser("package-export"); pe.set_defaults(fn=cmd_paket_export)
    pe.add_argument("datei", nargs="?", metavar="file"); pe.add_argument("--name")
    pe.add_argument("--without-uuid", dest="ohne_uuid", action="store_true"); pe.add_argument("--with-plan", dest="mit_plan", action="store_true")
    pi = sub.add_parser("package-import"); pi.set_defaults(fn=cmd_paket_import)
    pi.add_argument("datei", metavar="file"); pi.add_argument("--replace", dest="ersetzen", action="store_true")
    pi.add_argument("--anyway", dest="trotzdem", action="store_true"); pi.add_argument("--with-plan", dest="mit_plan", action="store_true")
    dg = sub.add_parser("diagnostics"); dg.set_defaults(fn=cmd_diagnose)
    dg.add_argument("datei", nargs="?", metavar="file"); dg.add_argument("--names", dest="namen", action="store_true")
    up = sub.add_parser("update"); up.set_defaults(fn=cmd_update); up.add_argument("--install", dest="installieren", action="store_true")
    tl = sub.add_parser("tls"); tl.set_defaults(fn=cmd_tls); tl.add_argument("--off", dest="aus", action="store_true")
    args = ap.parse_args(argv)
    setup_logging(args.quiet)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
