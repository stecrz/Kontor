"""Kontor as an app of its own on the Mac (mac_app.swift): a window with Apple's WebKit around the interface, built here like
the Touch ID helper into Kontor.app in the program folder.

Why: Safari's web app in the Dock keeps the page's microphone grant only while it runs, so it asks again and again; this app
gives the microphone to Kontor's own page without asking (macOS asks once, for the app). To macOS every new build is another
app (signed only here, "ad hoc"): it would ask for the microphone once more -- so the app is built again only when what goes
into it changes (its code, Info.plist, texts of Info.plist, icon), never just because Kontor has a new version.

The app has no words of its own: its menu gets them from the page; Info.plist's (the microphone, the Downloads folder) come
from web/i18n.js here. Its address on this Mac is written to its settings (`defaults`), only ever http://127.0.0.1:<port>/."""
from __future__ import annotations

import hashlib
import logging
import os
import signal
import time
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Dict
from xml.sax.saxutils import escape

import i18n

log = logging.getLogger("kontor")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "mac_app.swift")
ICON = os.path.join(HERE, "mac_app_icon.png")
APP = os.path.join(HERE, "Kontor.app")
BIN = os.path.join(APP, "Contents", "MacOS", "Kontor")
STAMP = os.path.join(HERE, ".mac_app_build")          # what went into the build (outside the bundle: not part of its signature)
LOCKFILE = os.path.join(HERE, ".mac_app_build.lock")   # one build at a time, also across processes (the service and `install`)
BUNDLE_ID = "local.kontor.app"
# where WebKit and macOS keep the app's own things (cookies, website data, caches, window state) -- removed on uninstall
DATA_PATHS = ("~/Library/WebKit/%s", "~/Library/Caches/%s", "~/Library/HTTPStorages/%s", "~/Library/HTTPStorages/%s.binarycookies",
              "~/Library/Saved Application State/%s.savedState", "~/Library/Cookies/%s.binarycookies")
TEXTS = {"NSMicrophoneUsageDescription": "mac_mikro_zweck", "NSDownloadsFolderUsageDescription": "mac_downloads_zweck"}
ICON_SIZES = (16, 32, 128, 256, 512)

_state: Dict[str, object] = {"building": False, "error": ""}
_lock = threading.Lock()


def info_plist() -> str:
    """Info.plist -- no version of Kontor in it (a new one would make a new app to macOS); its texts in German by default."""
    texts = "".join("<key>%s</key><string>%s</string>" % (k, escape(_text(v, "de"))) for k, v in TEXTS.items())
    return ("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>Kontor</string><key>CFBundleIdentifier</key><string>%s</string>
<key>CFBundleName</key><string>Kontor</string><key>CFBundleDisplayName</key><string>Kontor</string>
<key>CFBundlePackageType</key><string>APPL</string><key>CFBundleShortVersionString</key><string>1</string><key>CFBundleVersion</key><string>1</string>
<key>CFBundleIconFile</key><string>AppIcon</string><key>CFBundleDevelopmentRegion</key><string>de</string>
<key>CFBundleLocalizations</key><array><string>de</string><string>en</string></array>
<key>LSApplicationCategoryType</key><string>public.app-category.finance</string>
<key>NSHighResolutionCapable</key><true/><key>NSPrincipalClass</key><string>NSApplication</string>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
%s
</dict></plist>
""" % (BUNDLE_ID, texts))


def _text(key: str, lang: str) -> str:
    e = i18n._load().get(key) or [key]
    return e[1] if lang == "en" and len(e) > 1 and e[1] else e[0]


def strings(lang: str) -> str:
    """InfoPlist.strings of one language (macOS shows the one of the system's language)."""
    q = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    return "".join('"%s" = "%s";\n' % (k, q(_text(v, lang))) for k, v in TEXTS.items())


def inputs() -> str:
    """A fingerprint of what goes into the app: rebuilt only when it changes."""
    h = hashlib.sha256()
    for path in (SRC, ICON):
        try:
            with open(path, "rb") as f:
                h.update(f.read())
        except OSError:
            h.update(b"-")
    h.update(info_plist().encode("utf-8"))
    for lang in i18n.LANGS:
        h.update(strings(lang).encode("utf-8"))
    return h.hexdigest()


def supported() -> bool:
    return sys.platform == "darwin"


def ready() -> bool:
    return os.path.isfile(BIN) and os.access(BIN, os.X_OK)


def state() -> dict:
    """For the interface: built, being built, or why not."""
    return {"ready": ready(), "building": bool(_state["building"]), "error": str(_state["error"] or "")}


QUIET = {"capture_output": True, "text": True}


def _icon(res: str, tmp: str) -> None:
    """AppIcon.icns from the icon (sips and iconutil come with macOS); without them the app has the plain icon."""
    if not os.path.isfile(ICON):
        return
    iconset = os.path.join(tmp, "AppIcon.iconset")
    os.makedirs(iconset, exist_ok=True)
    for size in ICON_SIZES:
        for scale in (1, 2):
            px = size * scale
            name = "icon_%dx%d%s.png" % (size, size, "@2x" if scale == 2 else "")
            subprocess.run(["sips", "-z", str(px), str(px), ICON, "--out", os.path.join(iconset, name)], timeout=60, **QUIET)
    r = subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(res, "AppIcon.icns")], timeout=60, **QUIET)
    if r.returncode != 0:
        log.warning("Mac app: icon not made: %s", (r.stderr or r.stdout)[-200:])


def build(force: bool = False) -> str:
    """Builds Kontor.app (macOS, Xcode Command Line Tools), only when it is missing or what goes into it changed: into a fresh
    folder first, in place only once it is complete and signed (a failed build leaves the app there as it was). One build at a
    time, also across processes. "ok" or why not."""
    if not supported():
        return i18n.tr("s_nicht_macos")
    want = inputs()
    with _lock:
        _state["building"], _state["error"] = True, ""
        lock = tmp = None
        try:
            import fcntl
            lock = open(LOCKFILE, "w")
            fcntl.flock(lock, fcntl.LOCK_EX)              # another one building: waits, then finds it done
            try:
                with open(STAMP, encoding="utf-8") as f:
                    have = f.read().strip()
            except OSError:
                have = ""
            if not force and ready() and have == want:
                return "ok"
            tmp = tempfile.mkdtemp(prefix=".mac-app-", dir=HERE)          # the same disk: the finished app is moved, not copied
            app = os.path.join(tmp, "Kontor.app")
            res, exe = os.path.join(app, "Contents", "Resources"), os.path.join(app, "Contents", "MacOS")
            os.makedirs(exe)
            os.makedirs(res)
            with open(os.path.join(app, "Contents", "Info.plist"), "w", encoding="utf-8") as f:
                f.write(info_plist())
            for lang in i18n.LANGS:
                os.makedirs(os.path.join(res, lang + ".lproj"))
                with open(os.path.join(res, lang + ".lproj", "InfoPlist.strings"), "w", encoding="utf-8") as f:
                    f.write(strings(lang))
            _icon(res, tmp)
            r = subprocess.run(["swiftc", "-O", "-o", os.path.join(exe, "Kontor"), SRC], timeout=600, **QUIET)
            if r.returncode != 0:
                _state["error"] = i18n.tr("s_swiftc_fehler") % (r.stderr or r.stdout)[-300:]
                return str(_state["error"])
            r = subprocess.run(["codesign", "--force", "--sign", "-", app], timeout=120, **QUIET)          # ad hoc, as a whole bundle
            if r.returncode != 0:
                _state["error"] = (r.stderr or r.stdout)[-300:]
                return str(_state["error"])
            if os.path.isdir(APP):
                shutil.rmtree(APP)          # a running app goes on with what it has loaded; the next start is the new one
            os.rename(app, APP)
            with open(STAMP, "w", encoding="utf-8") as f:
                f.write(want + "\n")
            log.info("Mac app built: %s", APP)
            return "ok"
        except (ImportError, subprocess.TimeoutExpired, OSError) as e:
            _state["error"] = i18n.tr("s_swiftc_nicht_verfuegbar_s_xcode") % e if isinstance(e, FileNotFoundError) else str(e)[-300:]
            log.warning("Mac app not built: %s", e)
            return str(_state["error"])
        finally:
            _state["building"] = False
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
            if lock:
                lock.close()                              # lets the lock go


def set_address(port: int) -> None:
    """Tells the app where Kontor answers on this Mac (its own settings, read at its start)."""
    if sys.platform == "darwin":
        try:
            subprocess.run(["defaults", "write", BUNDLE_ID, "url", "http://127.0.0.1:%d/" % int(port)], timeout=20, **QUIET)
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning("Mac app: address not set: %s", e)


def prepare(port: int) -> str:
    """At the service's start: the address, then the app built if needed (in the background)."""
    set_address(port)
    return build()


def open_app() -> bool:
    """Opens the app (or brings it to the front) -- through LaunchServices, like a double click."""
    if not supported() or not ready():
        return False
    try:
        return subprocess.run(["open", APP], timeout=30, **QUIET).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def quit_app() -> None:
    """Ends the app (and only it: its own program file, not a pattern), waiting until it is gone -- so WebKit writes nothing after."""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,command="], timeout=20, **QUIET).stdout
    except (OSError, subprocess.TimeoutExpired):
        return
    pids = []
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit() and (parts[1] == BIN or parts[1].startswith(BIN + " ")):
            pids.append(int(parts[0]))
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(50):
        alive = []
        for pid in pids:
            try:
                os.kill(pid, 0)
                alive.append(pid)
            except OSError:
                pass
        if not alive:
            break
        time.sleep(0.1)
    if pids:
        time.sleep(0.5)                                   # its WebKit helpers end with it


def remove_data(quit_first: bool = False) -> list:
    """On uninstall: the app's settings, website data (cookies, caches, window state) and its permissions in macOS go (the app
    itself goes with the program folder); with quit_first it ends first -- after the answer, since it may be the one that asked.
    Only the app's own places (named by its identifier), links removed as links. Returns what was removed."""
    if not supported():
        return []
    done = []
    if quit_first:
        quit_app()
    try:
        subprocess.run(["defaults", "delete", BUNDLE_ID], timeout=20, **QUIET)
        subprocess.run(["tccutil", "reset", "All", BUNDLE_ID], timeout=20, **QUIET)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("Mac app: settings or permissions not removed: %s", e)
    for pattern in DATA_PATHS:
        path = os.path.expanduser(pattern % BUNDLE_ID)
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
                done.append(path)
            elif os.path.lexists(path):
                os.remove(path)
                done.append(path)
        except OSError as e:
            log.warning("Mac app: %s not removed: %s", path, e)
    for path in (STAMP, LOCKFILE):
        try:
            os.remove(path)
        except OSError:
            pass
    return done
