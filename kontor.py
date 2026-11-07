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
import shutil
import subprocess
import sys
from datetime import date
from typing import List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import auth  # noqa: E402
import updates  # noqa: E402
from mm_bridge import Bridge, MoneyMoneyError  # noqa: E402
from core import (account_tree, check_config, diagnose, export_package, fetch, import_package, merged_config,  # noqa: E402
                     run_once, unavailable_text, version)
from model import Ledger, accounts_from_export, fmt_eur  # noqa: E402
from storage import Store, load_or_create_master_key  # noqa: E402

log = logging.getLogger("kontor")
DATA_DIR = os.environ.get("KONTOR_DIR") or os.path.expanduser("~/Library/Application Support/Kontor")
OLD_DATA_DIR = os.path.expanduser("~/Library/Application Support/mmtools")
LAUNCHD_LABEL = updates.LABEL
OLD_LAUNCHD_LABELS = ("de.mmtools.dienst",) + updates.LEGACY_LABELS


def migrate_old_data_dir() -> None:
    """Datenordner der Vorversion (mmtools) uebernehmen, falls Kontor noch keine Daten hat."""
    if os.environ.get("KONTOR_DIR") or not os.path.isdir(OLD_DATA_DIR) or os.path.isdir(DATA_DIR):
        return
    try:
        shutil.copytree(OLD_DATA_DIR, DATA_DIR)
        for fn in ("mmtools.log", "dienst.out.log", "dienst.err.log", "dienst.lock"):   # legacy names
            try:
                os.remove(os.path.join(DATA_DIR, fn))
            except OSError:
                pass
        print("Daten der Vorversion übernommen: %s -> %s (Original bleibt, kann gelöscht werden)" % (OLD_DATA_DIR, DATA_DIR))
    except OSError as e:
        print("Daten der Vorversion konnten nicht übernommen werden: %s" % e)


def setup_logging(quiet: bool) -> None:
    migrate_old_data_dir()
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
    return merged_config(store.load("config.json", {}) or {})


class Lock:
    def __init__(self, name: str):
        self.path = os.path.join(DATA_DIR, name)

    def __enter__(self):
        self.f = open(self.path, "w")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.exit("Kontor läuft bereits (%s)." % self.path)
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
        print("Keine Änderung in MoneyMoney seit dem letzten Lauf (--force erzwingt einen Lauf)."); return 0
    if st == "laeuft_bereits":
        print("Ein Lauf ist bereits aktiv."); return 1
    if st == "fehler":
        print("FEHLER: %s" % res.get("text")); return 1
    for v in res.get("vorschlaege", []):
        print("  %s  %-50s %14s  %s" % (v["datum"], v["konto"][-50:], fmt_eur(v["betrag"]), v["text"]))
    for w in res.get("warnungen", []):
        print("HINWEIS " + w)
    print("%s: %d Vorschlag/Vorschläge, %d gebucht%s" % ("Probelauf" if dry else "Lauf", len(res.get("vorschlaege", [])),
                                                        res.get("geschrieben", 0), (" -- FEHLER: " + res["fehler"]) if res.get("fehler") else ""))
    print("Oberfläche: python3 kontor.py öffnen  (Dienst: python3 kontor.py start)")
    return 1 if res.get("fehler") else 0


def cmd_konten(args) -> int:
    store = open_store()
    cfg = load_config(store)
    try:
        ledger = Ledger(accounts_from_export(Bridge(dry_run=True).export_accounts()), [])
    except MoneyMoneyError as e:
        print(unavailable_text(e) or str(e)); return 2
    print("%-58s %-36s %-8s %-17s %-16s %s" % ("Konto (Pfad)", "UUID", "Typ", "Rolle", "aktualisiert", "Saldo"))
    for k in account_tree(ledger, cfg):
        typ = "Gruppe" if k["gruppe"] else ("Depot" if k["depot"] else ("manuell" if k["manuell"] else "Bank"))
        print("%-58s %-36s %-8s %-17s %-16s %s" % ("  " * k["ebene"] + k["name"], k["uuid"], typ, k["rolle"],
                                                   k["aktualisiert"] or "", "" if k["gruppe"] else fmt_eur(k["saldo"])))
    return 0


def cmd_check(args) -> int:
    store = open_store()
    cfg = load_config(store)
    b = Bridge(dry_run=True)
    try:
        ledger = fetch(b, cfg, date.today())
        cats = b.export_categories()
    except MoneyMoneyError as e:
        print(unavailable_text(e) or str(e)); return 2
    findings = check_config(ledger, cats, cfg)
    for f in findings:
        print("%-8s %s" % (f["stufe"].upper(), f["text"]))
    bad = any(f["stufe"] == "fehler" for f in findings)
    print("Probelauf: %s" % ("EIN" if cfg.get("probelauf", True) else "AUS"))
    print("Ergebnis: %s" % ("alles in Ordnung" if not bad else "FEHLER vorhanden"))
    return 1 if bad else 0


def cmd_status(args) -> int:
    store = open_store()
    st = store.load("state.json", {}) or {}
    last = st.get("letzter_lauf")
    print("Kontor %s -- Datenordner %s" % (version(), DATA_DIR))
    if not last:
        print("Noch kein Lauf."); return 0
    print(json.dumps({k: v for k, v in last.items() if k != "vorschlaege"}, ensure_ascii=False, indent=2))
    for v in last.get("vorschlaege", []):
        print("  %s %s %s %s" % (v["datum"], v["konto"], fmt_eur(v["betrag"]), v["text"]))
    return 0


def cmd_passwort(args) -> int:
    store = open_store()
    pw = getpass.getpass("Neues Passwort für die Oberfläche: ")
    if pw != getpass.getpass("Wiederholen: "):
        print("Stimmt nicht überein."); return 1
    err = auth.password_ok(pw)
    if err:
        print(err); return 1
    store.save("auth.json", auth.with_offline(auth.hash_password(pw), pw))
    print("Passwort gesetzt. Laufende Sitzungen bleiben bis zur Sperre gültig.")
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
        print("Hinweis: %s -- Kontoreferenzen werden nicht geprüft." % (unavailable_text(e) or e))
    new_cfg, unresolved, report = import_package(cfg, pkg, ledger, "ersetzen" if args.ersetzen else "ergaenzen")
    for line in report:
        print("  " + line)
    for u in unresolved:
        print("  NICHT GEFUNDEN: %s (%s)" % (u["label"], u["feld"]))
    if unresolved and not args.trotzdem:
        print("Nicht übernommen -- Konten in MoneyMoney prüfen oder --anyway (Referenzen bleiben als Name).")
        return 1
    store.save("config.json", merged_config(new_cfg))
    if pkg.get("plan") and args.mit_plan:
        store.save("plan.json", pkg["plan"])
    print("Einstellungen übernommen. Prüfen: python3 kontor.py check  -- ein laufender Dienst übernimmt sie binnen 20 Sekunden.")
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
    print("Installiert: %s   Verfügbar: %s (%s)" % (info["aktuell"], info["verfuegbar"], info["quelle"]))
    if not info["neuer"]:
        print("Kontor ist aktuell."); return 0
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
    # Dienste frueherer Versionen entfernen, sonst streiten sich zwei Dienste um den Port
    for old in OLD_LAUNCHD_LABELS:
        if os.path.exists(launchd_path(old)):
            subprocess.run(["launchctl", "unload", launchd_path(old)], capture_output=True)
            try:
                os.remove(launchd_path(old))
                print("Dienst der Vorversion (%s) entfernt." % old)
            except OSError:
                pass
    if not store.load("auth.json", None):
        print("Noch kein Passwort: wird beim ersten Öffnen der Oberfläche am Mac festgelegt.")
    print("Touch-ID-Helfer: %s" % build_touchid())
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
    print("Dienst eingerichtet (startet beim Anmelden, läuft dauerhaft): %s" % launchd_path())
    if r.returncode != 0:
        print("launchctl: " + (r.stderr or r.stdout))
    print("Oberfläche: %s  (python3 kontor.py öffnen)" % ui_url(cfg))
    print("Beim ersten Lauf fragt macOS, ob das Programm MoneyMoney steuern darf -- bitte erlauben.")
    return 0


def cmd_uninstall(args) -> int:
    for label in (LAUNCHD_LABEL,) + OLD_LAUNCHD_LABELS:
        if os.path.exists(launchd_path(label)):
            subprocess.run(["launchctl", "unload", launchd_path(label)], capture_output=True)
            try:
                os.remove(launchd_path(label))
            except FileNotFoundError:
                pass
    print("Dienst entfernt. Daten bleiben in %s (bei Bedarf von Hand löschen)." % DATA_DIR)
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
            print("Fehler: %s" % e); return 1
        cfg["oberflaeche"] = r["oberflaeche"]
        store.save("config.json", cfg)
        print("Zertifikat für %s geholt (gültig bis %s), Adresse %s." % (r["name"], (r["gueltig_bis"] or "?")[:10], r["ip"]))
        print("Oberfläche nach dem Neustart: %s  (am iPhone diese Adresse öffnen, dann „Zum Home-Bildschirm“)." % r["url"])
        print("Das Zertifikat wird vom laufenden Dienst automatisch erneuert.")
    if os.path.exists(launchd_path(updates.installed_label())):
        r2 = subprocess.run(["launchctl", "kickstart", "-k", "gui/%d/%s" % (os.getuid(), updates.installed_label())], capture_output=True, text=True)
        print("Dienst neu gestartet." if r2.returncode == 0 else "Dienst bitte neu starten: bash install.sh")
    else:
        print("Dienst neu starten (bash install.sh), damit die Einstellung greift.")
    return 0


def cmd_version(args) -> int:
    print(version())
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="kontor", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quiet", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    # Befehle englisch; fruehere deutsche Namen bleiben als Alias nutzbar
    for name, alias, fn in (("start", None, cmd_start), ("open", "oeffnen", cmd_oeffnen), ("accounts", "konten", cmd_konten), ("check", None, cmd_check),
                            ("status", None, cmd_status), ("password", "passwort", cmd_passwort), ("install", None, cmd_install),
                            ("uninstall", None, cmd_uninstall), ("version", None, cmd_version)):
        sub.add_parser(name, aliases=[alias] if alias else []).set_defaults(fn=fn)
    r = sub.add_parser("run"); r.set_defaults(fn=cmd_run)
    r.add_argument("--dry-run", "--probelauf", dest="probelauf", action="store_true"); r.add_argument("--live", "--scharf", dest="scharf", action="store_true")
    r.add_argument("--force", action="store_true")
    pe = sub.add_parser("package-export", aliases=["paket-export"]); pe.set_defaults(fn=cmd_paket_export)
    pe.add_argument("datei", nargs="?", metavar="file"); pe.add_argument("--name")
    pe.add_argument("--without-uuid", "--ohne-uuid", dest="ohne_uuid", action="store_true"); pe.add_argument("--with-plan", "--mit-plan", dest="mit_plan", action="store_true")
    pi = sub.add_parser("package-import", aliases=["paket-import"]); pi.set_defaults(fn=cmd_paket_import)
    pi.add_argument("datei", metavar="file"); pi.add_argument("--replace", "--ersetzen", dest="ersetzen", action="store_true")
    pi.add_argument("--anyway", "--trotzdem", dest="trotzdem", action="store_true"); pi.add_argument("--with-plan", "--mit-plan", dest="mit_plan", action="store_true")
    dg = sub.add_parser("diagnostics", aliases=["diagnose"]); dg.set_defaults(fn=cmd_diagnose)
    dg.add_argument("datei", nargs="?", metavar="file"); dg.add_argument("--names", "--namen", dest="namen", action="store_true")
    up = sub.add_parser("update"); up.set_defaults(fn=cmd_update); up.add_argument("--install", "--installieren", dest="installieren", action="store_true")
    tl = sub.add_parser("tls"); tl.set_defaults(fn=cmd_tls); tl.add_argument("--off", "--aus", dest="aus", action="store_true", help="TLS wieder abschalten")
    args = ap.parse_args(argv)
    setup_logging(args.quiet)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
