"""Belege: Dateien (Rechnungen, Vertraege) zu Umsaetzen -- lokal in einem frei waehlbaren Ordner.

Die Dateien liegen als normale Dateien im Belegordner (Standard ~/Documents/Kontor-Belege),
Unterordner nach Muster (Standard "{year}"), Dateiname "JJJJ-MM-TT_Betrag_Name_Kennung.ext".
Der Index (welche Datei gehoert zu welchem Umsatz) liegt verschluesselt im Datenordner
(belege.json). Geht der Index verloren, bleiben die Dateien -- die Kennung im Dateinamen
erlaubt die Wiederzuordnung.
"""
from __future__ import annotations

import csv
import io
import os
import sys
import re
import secrets
import zipfile
from datetime import date, datetime
from typing import Dict, List, Optional

from storage import Store
from i18n import tr

DEFAULT_FOLDER = "~/Documents/Kontor-Belege"
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".heic", ".gif", ".txt", ".csv", ".xlsx", ".docx", ".eml", ".msg", ".zip"}
MAX_FILE = 60 * 1024 * 1024


FOLD_CASE = sys.platform == "darwin"      # macOS: names differing only in case are the same file


def _canon(path: str) -> str:
    """A path as the file system sees it, for comparing places: links followed; on macOS case folded and the data volume's
    second name (/System/Volumes/Data/...) taken off."""
    full = os.path.realpath(path)
    if FOLD_CASE:
        if full.startswith("/System/Volumes/Data/"):
            full = full[len("/System/Volumes/Data"):]
        full = full.lower()
    return full


def file_status(full: str) -> str:
    """ok | icloud (Platzhalter, nicht geladen) | fehlt"""
    if os.path.isfile(full):
        return "ok"
    d, n = os.path.split(full)
    if os.path.isfile(os.path.join(d, "." + n + ".icloud")):
        return "icloud"
    return "lacking"


def _safe(s: str, n: int = 40) -> str:
    s = re.sub(r"[^\w\-. äöüÄÖÜß]", "", str(s or "")).strip().replace(" ", "-")
    return s[:n] or "Beleg"


class Belege:
    def __init__(self, store: Store, config: dict):
        self.store = store
        cfg = config.get("receipts", {}) or {}
        self.folder = os.path.expanduser(cfg.get("folder") or DEFAULT_FOLDER)
        self.pattern = cfg.get("subfolder") or "{year}"
        self.index = store.load("receipts.json", {"entry_list": []}) or {"entry_list": []}

    # -- Ordner ------------------------------------------------------------
    def ensure_folder(self) -> Optional[str]:
        try:
            os.makedirs(self.folder, exist_ok=True)
            return None
        except OSError as e:
            return tr("s_belegordner_nicht_anlegbar_s_s") % (self.folder, e)

    def subfolder(self, tx: Optional[dict]) -> str:
        d = (tx or {}).get("date") or date.today().isoformat()
        vals = {"year": d[:4], "month": d[5:7], "entity": _safe((tx or {}).get("entity_name") or "Allgemein", 30),
                "account": _safe((tx or {}).get("account_name") or "Konto", 30)}
        try:
            sub = os.path.normpath(self.pattern.format(**vals))
        except (KeyError, IndexError, ValueError, AttributeError):
            return vals["year"]
        # always inside the receipts folder: no absolute path, no way up
        if os.path.isabs(sub) or sub == ".." or sub.startswith(".." + os.sep) or "{" in sub or "<" in sub:
            return vals["year"]
        return sub

    # -- Index -------------------------------------------------------------
    def _save(self) -> None:
        self.store.save("receipts.json", self.index)

    def entries(self) -> List[dict]:
        return self.index.setdefault("entry_list", [])

    def for_tx(self, tx_id: int) -> List[dict]:
        return [e for e in self.entries() if e.get("tx_id") == tx_id]

    def counts(self) -> Dict[int, int]:
        out: Dict[int, int] = {}
        for e in self.entries():
            if e.get("tx_id") is not None:
                out[e["tx_id"]] = out.get(e["tx_id"], 0) + 1
        return out

    # -- Anlegen -----------------------------------------------------------
    def add_bytes(self, tx: Optional[dict], filename: str, data: bytes, notiz: str = "") -> dict:
        err = self.ensure_folder()
        if err:
            raise OSError(err)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXT:
            raise ValueError(tr("s_dateityp_s_nicht_erlaubt_s") % (ext or tr("s_ohne_endung"), ", ".join(sorted(ALLOWED_EXT))))
        if len(data) > MAX_FILE:
            raise ValueError(tr("s_datei_zu_gross_max_d") % (MAX_FILE // (1024 * 1024)))
        if not data:
            raise ValueError(tr("s_leere_datei"))
        kennung = secrets.token_hex(3)
        sub = self.subfolder(tx)
        target_dir = os.path.join(self.folder, sub)
        os.makedirs(target_dir, exist_ok=True)
        if tx:
            base = "%s_%s_%s_%s" % (tx.get("date", "0000-00-00"), ("%.2f" % abs(float(tx.get("amount") or 0))).replace(".", ","),
                                    _safe(tx.get("name") or os.path.splitext(filename)[0]), kennung)
        else:
            base = "%s_%s_%s" % (date.today().isoformat(), _safe(os.path.splitext(filename)[0]), kennung)
        name = base + ext
        with open(os.path.join(target_dir, name), "wb") as f:
            f.write(data)
        os.chmod(os.path.join(target_dir, name), 0o600)
        entry = {"id": kennung, "tx_id": (tx or {}).get("id"), "account": (tx or {}).get("account"), "entity": (tx or {}).get("entity"),
                 "date": (tx or {}).get("date") or date.today().isoformat(), "amount": (tx or {}).get("amount"),
                 "name": (tx or {}).get("name") or os.path.splitext(filename)[0], "path": os.path.join(sub, name).replace("\\", "/"),
                 "size_bytes": len(data), "added": datetime.now().strftime("%Y-%m-%d %H:%M"), "note": notiz, "original": filename}
        self.entries().append(entry)
        self._save()
        return entry

    def inside(self, full: str) -> bool:
        """Is the file really in the receipts folder -- also after following links? The folder itself may be a link (e.g. into
        iCloud Drive); a link in it to a file elsewhere does not count (a file elsewhere: "link" at the Mac, external_ok)."""
        root = os.path.realpath(self.folder)
        return os.path.realpath(full).startswith(root + os.sep)

    def allowed(self, e: dict) -> bool:
        """May Kontor hand out the file of this entry (view, export)? Linked from outside: only what external_ok allows. In the
        folder: really in it -- or, where a subfolder is a link elsewhere (e.g. into iCloud Drive), what external_ok allows
        there. A file that is itself a link to somewhere else never counts."""
        full = self.full_path(e)
        if e.get("external"):
            return self.external_ok(full)
        return full.startswith(os.path.normpath(self.folder) + os.sep) and (
            self.inside(full) or (not os.path.islink(full) and self.external_ok(full)))

    def deletable(self, e: dict) -> bool:
        """May "delete with file" remove the file? Never a linked one from outside. In the folder: a file really in it -- or one
        Kontor put there itself through a subfolder that is a link elsewhere (its name ends with the entry's id)."""
        if e.get("external") or not self.allowed(e):
            return False
        full = self.full_path(e)
        return self.inside(full) or os.path.splitext(os.path.basename(full))[0].endswith("_" + str(e.get("id")))

    def servable(self, e: dict) -> Optional[str]:
        """Path of the entry's file if it exists and may be handed out, else None."""
        full = self.full_path(e)
        return full if self.allowed(e) and os.path.isfile(full) else None

    def link_existing(self, tx: Optional[dict], rel_path: str, notiz: str = "") -> dict:
        full = os.path.normpath(os.path.join(self.folder, rel_path))
        if not full.startswith(os.path.normpath(self.folder) + os.sep) or not self.inside(full) or not os.path.isfile(full):
            raise ValueError(tr("s_datei_liegt_nicht_im_belegordner"))
        entry = {"id": secrets.token_hex(3), "tx_id": (tx or {}).get("id"), "account": (tx or {}).get("account"), "entity": (tx or {}).get("entity"),
                 "date": (tx or {}).get("date") or date.today().isoformat(), "amount": (tx or {}).get("amount"),
                 "name": (tx or {}).get("name") or os.path.basename(rel_path), "path": os.path.relpath(full, os.path.normpath(self.folder)).replace("\\", "/"),
                 "size_bytes": os.path.getsize(full), "added": datetime.now().strftime("%Y-%m-%d %H:%M"), "note": notiz, "original": os.path.basename(rel_path)}
        self.entries().append(entry)
        self._save()
        return entry

    def external_ok(self, full: str) -> bool:
        """A file outside the receipts folder that may be linked and handed out: a document type of receipts, not hidden, not
        in Kontor's data folder and not in ~/Library -- except the cloud folders there (iCloud Drive, Dropbox, OneDrive ...)."""
        full = _canon(full)
        if os.path.splitext(full)[1].lower() not in ALLOWED_EXT:
            return False
        if any(p.startswith(".") for p in full.split(os.sep) if p):
            return False
        data = _canon(self.store.data_dir)
        if full == data or full.startswith(data + os.sep):
            return False
        lib = _canon(os.path.expanduser("~/Library"))
        if full.startswith(lib + os.sep):
            return any(full.startswith(_canon(os.path.join(lib, c)) + os.sep) for c in ("Mobile Documents", "CloudStorage"))
        return True

    def link_external(self, tx: Optional[dict], abs_path: str, notiz: str = "") -> dict:
        """Verknuepfung auf eine Datei ausserhalb des Belegordners (z. B. iCloud Drive). Die Datei bleibt, wo sie ist."""
        full = os.path.normpath(os.path.expanduser(abs_path))
        if not os.path.isabs(full):
            raise ValueError(tr("s_bitte_einen_vollstaendigen_pfad_angebe"))
        if not self.external_ok(full):
            raise ValueError(tr("s_beleg_extern_nicht_erlaubt"))
        st = file_status(full)
        if st == "lacking":
            raise ValueError(tr("s_datei_nicht_gefunden_s") % full)
        entry = {"id": secrets.token_hex(3), "tx_id": (tx or {}).get("id"), "account": (tx or {}).get("account"), "entity": (tx or {}).get("entity"),
                 "date": (tx or {}).get("date") or date.today().isoformat(), "amount": (tx or {}).get("amount"),
                 "name": (tx or {}).get("name") or os.path.basename(full), "path": full, "external": True,
                 "size_bytes": os.path.getsize(full) if st == "ok" else 0, "added": datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "note": notiz, "original": os.path.basename(full)}
        self.entries().append(entry)
        self._save()
        return entry

    def full_path(self, entry: dict) -> str:
        if entry.get("external"):
            return os.path.normpath(entry["path"])
        return os.path.normpath(os.path.join(self.folder, entry["path"]))

    def remove(self, entry_id: str, delete_file: bool = False) -> bool:
        for e in list(self.entries()):
            if e["id"] == entry_id:
                self.entries().remove(e)
                if delete_file and self.deletable(e):
                    try:
                        os.remove(self.full_path(e))
                    except OSError:
                        pass
                self._save()
                return True
        return False

    def update(self, entry_id: str, **fields) -> Optional[dict]:
        for e in self.entries():
            if e["id"] == entry_id:
                for k, v in fields.items():
                    if k in ("note", "tx_id", "account", "entity", "date", "amount", "name"):
                        e[k] = v
                self._save()
                return e
        return None

    # -- Ordnerinhalt ------------------------------------------------------
    def listing(self) -> List[dict]:
        out = []
        linked = {e["path"] for e in self.entries()}
        if not os.path.isdir(self.folder):
            return out
        for root, dirs, files in os.walk(self.folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "Export"]
            for fn in files:
                if fn.startswith("."):
                    continue
                rel = os.path.relpath(os.path.join(root, fn), self.folder).replace("\\", "/")
                if not self.inside(os.path.join(root, fn)):    # a link to a file elsewhere: not offered
                    continue
                out.append({"path": rel, "size_bytes": os.path.getsize(os.path.join(root, fn)), "linked": rel in linked})
        out.sort(key=lambda x: x["path"])
        return out

    def check(self) -> List[str]:
        """Fehlende Dateien im Index (iCloud-Platzhalter gelten als vorhanden)."""
        return [e["path"] for e in self.entries() if file_status(self.full_path(e)) == "lacking" or not self.allowed(e)]

    # -- Export ------------------------------------------------------------
    def export_zip(self, jahr: Optional[str], entitaet: Optional[str], names: Dict[str, str]) -> str:
        err = self.ensure_folder()
        if err:
            raise OSError(err)
        sel = [e for e in self.entries() if (not jahr or (e.get("date") or "").startswith(jahr))
               and (not entitaet or e.get("entity") == entitaet)]
        exp_dir = os.path.join(self.folder, "Export")
        os.makedirs(exp_dir, exist_ok=True)
        label = "_".join(x for x in (jahr or "alle", _safe(names.get(entitaet or "", "alle"), 30)) if x)
        target = os.path.join(exp_dir, "Belege_%s.zip" % label)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow([tr("x_datum"), tr("x_betrag"), tr("x_name"), tr("x_konto"), tr("s_entitaet"), tr("x_datei"), tr("x_notiz"), tr("x_umsatz_id")])
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            for e in sel:
                full = self.servable(e)
                if full:
                    z.write(full, ("external/" + os.path.basename(full)) if e.get("external") else e["path"])
                w.writerow([e.get("date"), ("%.2f" % e["amount"]).replace(".", ",") if isinstance(e.get("amount"), (int, float)) else "",
                            e.get("name"), names.get(e.get("account") or "", e.get("account") or ""), names.get(e.get("entity") or "", ""),
                            e["path"], e.get("note", ""), e.get("tx_id") or ""])
            z.writestr("Belege.csv", "﻿" + buf.getvalue())
        os.chmod(target, 0o600)
        return target
