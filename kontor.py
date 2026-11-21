#!/usr/bin/env python3
"""Kontor -- Automatisierung, Bilanz, Kapitalfluss, Planung und Belege auf MoneyMoney (macOS).

Commands (everything else only in the interface, after signing in -- the terminal is no way around it):
  start             run the service: web interface (http://127.0.0.1:8765/) and the scheduled syncs
  open              open the interface in the browser (the service must run)
  install           set up the service in the background (starts at login, keeps running); builds the Touch ID helper
  uninstall         remove Kontor: service, settings, data, log, data key (--program: the program folder too; --yes: without
                    the question) -- receipts and MoneyMoney stay; with the Kontor password or Touch ID
  password          set a new Kontor password -- with the current one or Touch ID
  version           version number

Datenordner: ~/Library/Application Support/Kontor (oder Umgebungsvariable KONTOR_DIR).
Alle Dateien dort sind verschluesselt (Schluessel im macOS-Schluesselbund); nur kontor.log ist Klartext
und enthaelt keine Kontonummern, Salden oder Passwoerter.
"""
from __future__ import annotations

import argparse
import fcntl
import getpass
import logging
import logging.handlers
import os
import plistlib
import socket
import subprocess
import sys
import time
from typing import List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import auth  # noqa: E402
import updates  # noqa: E402
import i18n  # noqa: E402
from core import merged_config, version  # noqa: E402
import storage  # noqa: E402
from storage import Store, load_or_create_master_key  # noqa: E402
from i18n import tr  # noqa: E402

log = logging.getLogger("kontor")
DATA_DIR = os.environ.get("KONTOR_DIR") or os.path.expanduser("~/Library/Application Support/Kontor")
LAUNCHD_LABEL = updates.LABEL


class OneFileHandler(logging.handlers.RotatingFileHandler):
    """The log as one file: grown past maxBytes, it keeps its newest half (from the start of a line) instead of numbered copies."""

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        try:
            with open(self.baseFilename, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - self.maxBytes // 2))
                data = f.read()
            cut = data.find(b"\n")
            with open(self.baseFilename, "wb") as f:
                f.write(data[cut + 1:] if cut >= 0 else data)
        except OSError:
            pass
        self.stream = self._open()


def setup_logging(quiet: bool) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        os.chmod(DATA_DIR, 0o700)
    except OSError:
        pass
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    path = os.path.join(DATA_DIR, "kontor.log")
    fh = OneFileHandler(path, maxBytes=2_000_000, encoding="utf-8")
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


def open_store(finish: Optional[bool] = None) -> Store:
    """The encrypted store. An unfinished renewal of the data key is finished only under the service's lock: by the service
    (finish=True, it holds the lock) or by a command that gets the lock while no service runs; two processes never finish it
    at the same time. A command beside the running service leaves it to the service."""
    lock = None
    if finish is None:
        try:
            lock = open(os.path.join(DATA_DIR, "service.lock"), "a")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finish = True
        except OSError:
            finish = False
    try:
        key, source = load_or_create_master_key(DATA_DIR, finish=finish)
    finally:
        if lock:
            lock.close()                    # releases the lock: launchd may start the service now
    return Store(DATA_DIR, key, source)


def load_config(store: Store) -> dict:
    cfg = merged_config(store.load("config.json", {}) or {})
    i18n.set_lang((cfg.get("ui") or {}).get("language") or "de")
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
    with Lock("service.lock"):
        store = open_store(finish=True)
        app = App(store, DATA_DIR)
        serve(app)
    return 0


def ui_port(cfg: dict) -> int:
    return int((cfg.get("ui") or {}).get("port") or 8765)


def ui_url(cfg: dict) -> str:
    scheme = "https" if (cfg.get("ui") or {}).get("tls_cert") else "http"
    return "%s://127.0.0.1:%d/" % (scheme, ui_port(cfg))


def cmd_oeffnen(args) -> int:
    store = open_store()
    cfg = load_config(store)
    import mac_app
    if mac_app.ready():                         # Kontor's own app on this Mac, else the browser
        mac_app.set_address(ui_port(cfg))
        if mac_app.open_app():
            return 0
    subprocess.run(["open", ui_url(cfg)])
    return 0


def confirm_identity(store: Store) -> bool:
    """As in the interface: Touch ID where it is switched on, else (or after a cancel) the Kontor password, three tries. No
    password set yet: nothing to confirm."""
    rec = store.load("auth.json", None)
    if not rec:
        return True
    cfg = merged_config(store.load("config.json", {}) or {})
    if (cfg.get("ui") or {}).get("touchid", True) and auth.touchid_available():
        print(tr("s_cli_touchid"))
        if auth.touchid_verify():
            return True
    for _ in range(3):
        try:
            pw = getpass.getpass(tr("s_cli_passwort"))
        except (EOFError, KeyboardInterrupt):
            return False
        if auth.verify_password(pw, rec):
            return True
        time.sleep(1)
        print(tr("s_passwort_falsch"))
    return False


def cmd_passwort(args) -> int:
    store = open_store()
    try:
        ok = confirm_identity(store)
    except Exception as e:                  # the password check does not open: nothing is changed
        print(tr("s_fehler_s") % e); return 1
    if not ok:
        print(tr("s_cli_nicht_bestaetigt")); return 1
    pw = getpass.getpass(tr("s_neues_passwort_fuer_die_oberflaeche"))
    if pw != getpass.getpass(tr("s_cli_wiederholen")):
        print(tr("s_stimmt_nicht_ueberein")); return 1
    err = auth.password_ok(pw)
    if err:
        print(err); return 1
    store.save("auth.json", auth.with_offline(auth.hash_password(pw), pw))
    print(tr("s_passwort_gesetzt_laufende_sitzungen_bl"))
    return 0


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
    import mac_app
    mac_app.set_address(ui_port(cfg))
    try:                                        # Kontor's own app: a failed build stops nothing (the browser still works)
        print(tr("s_mac_app") % mac_app.build())
    except Exception as e:
        print(tr("s_mac_app") % e)
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
    port = ui_port(cfg)
    subprocess.run(["launchctl", "unload", launchd_path()], capture_output=True)
    for _ in range(50):                     # the old service lets go of the port first, else it would count as started
        if not service_answers(port):
            break
        time.sleep(0.1)
    load_service()
    print(tr("s_dienst_eingerichtet_startet_beim_anmel") % launchd_path())
    if not wait_for_service(port, sys.stdin.isatty()):
        return 1
    print(tr("s_oberflaeche_s_python3_kontor_py") % ui_url(cfg))
    print(tr("s_beim_ersten_lauf_fragt_macos"))
    return 0


def service_answers(port: int) -> bool:
    """The service listens on 127.0.0.1 (always there, always http)."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def service_loaded() -> bool:
    return subprocess.run(["launchctl", "print", "gui/%d/%s" % (os.getuid(), LAUNCHD_LABEL)], capture_output=True).returncode == 0


def load_service() -> None:
    """-w: also lifts a 'launchctl disable'. Switched off under Login Items ('Allow in the Background'), macOS refuses the load
    (error 5) -- wait_for_service says so."""
    r = subprocess.run(["launchctl", "load", "-w", launchd_path()], capture_output=True, text=True)
    if r.returncode != 0 or r.stderr.strip():
        log.debug("launchctl load: %s", (r.stderr or r.stdout).strip())


def wait_for_service(port: int, interactive: bool) -> bool:
    """Until the service answers. Not loaded: macOS keeps it from running in the background -- open that page in System
    Settings and load again until it is allowed. Loaded but silent: still starting (or a dialog of macOS waits), the log helps.
    In the terminal it waits until then (ctrl-C cancels), otherwise for half a minute."""
    hint_bg = hint_log = False
    start = time.time()
    try:
        while True:
            if service_answers(port):
                if hint_bg or hint_log:
                    print(tr("s_dienst_laeuft"))
                return True
            if not service_loaded():
                if not hint_bg:
                    hint_bg = True
                    print(tr("s_hintergrund_erlauben"))
                    subprocess.run(["open", "x-apple.systempreferences:com.apple.LoginItems-Settings.extension"], capture_output=True)
                load_service()
            elif not hint_log and time.time() - start > 15:
                hint_log = True
                print(tr("s_dienst_antwortet_noch_nicht") % os.path.join(DATA_DIR, "service.err.log"))
            if not interactive and time.time() - start > 30:
                return False
            time.sleep(2 if hint_bg else 0.5)
    except KeyboardInterrupt:
        print()
        return False


def cmd_uninstall(args) -> int:
    """The same as Settings -> Backup -> Uninstall: the service, Kontor's own files in the data folder (settings, data, log),
    the data key (only when no encrypted file is left) and, with --program, the program folder. Receipts, linked documents and
    MoneyMoney stay. Asks first (unless --yes)."""
    import service
    if not args.yes:
        try:
            ans = input(tr("deinstall_frage") + (" " + tr("deinstall_programmordner") if args.program else "") + " [j/N] ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("j", "ja", "y", "yes"):
            print(tr("s_deinstall_abgebrochen"))
            return 1
    # the key first: encrypted data that cannot be opened stay, and so does everything else (the key might still be needed)
    try:
        key, source = storage.read_master_key(DATA_DIR)
        store = Store(DATA_DIR, key, source)
    except Exception as e:
        if storage._enc_files(DATA_DIR):
            print(tr("s_fehler_s") % e)
            return 1
        store = Store(DATA_DIR, None)       # nothing encrypted is there: nothing to open
    try:
        cfg = merged_config(store.load("config.json", {}) or {})
        ok = confirm_identity(store)        # as in the interface: only with the Kontor password (or Touch ID)
    except Exception as e:                  # the settings do not open: nothing is deleted
        print(tr("s_fehler_s") % e)
        return 1
    if not ok:
        print(tr("s_cli_nicht_bestaetigt")); return 1
    if sys.platform == "darwin":            # stop the service: launchd would start it again
        subprocess.run(["launchctl", "bootout", "gui/%d/%s" % (os.getuid(), LAUNCHD_LABEL)], capture_output=True)
    app = service.App.__new__(service.App)
    app.data_dir, app.program_dir, app.store, app.config = DATA_DIR, HERE, store, cfg
    r = service.App.uninstall(app, program=args.program)
    if r.get("error"):
        print(r["error"])
        return 1
    print(tr("deinstalliert_text" if r["key_removed"] else "deinstalliert_ohne_schluessel"))
    if r.get("receipts"):
        print(tr("deinstall_belege_bleiben", r["receipts"]))
    if r.get("foreign"):
        print(tr("deinstall_fremd", DATA_DIR, ", ".join(r["foreign"])))
    if r.get("kept"):
        print(tr("deinstall_geblieben", ", ".join(r["kept"])))
    if sys.platform == "darwin":            # Kontor's own app: quits; what it wrote while this ran goes too
        import mac_app
        mac_app.remove_data(quit_first=True)
    if sys.platform == "darwin":            # macOS keeps the automation permissions (MoneyMoney, System Events); only tccutil removes them
        print(tr("s_freigaben_entfernen"))
    return 0


def cmd_version(args) -> int:
    print(version())
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="kontor", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quiet", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("start", cmd_start), ("open", cmd_oeffnen), ("password", cmd_passwort), ("install", cmd_install), ("version", cmd_version)):
        sub.add_parser(name).set_defaults(fn=fn)
    un = sub.add_parser("uninstall"); un.set_defaults(fn=cmd_uninstall)
    un.add_argument("--program", action="store_true"); un.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)
    setup_logging(args.quiet)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
