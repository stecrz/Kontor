"""Belege: Dateien (Rechnungen, Vertraege) zu Umsaetzen -- lokal in einem frei waehlbaren Ordner.

Die Dateien liegen als normale Dateien im Belegordner (Standard ~/Documents/Kontor-Belege),
Unterordner nach Muster (Standard "{jahr}"), Dateiname "JJJJ-MM-TT_Betrag_Name_Kennung.ext".
Der Index (welche Datei gehoert zu welchem Umsatz) liegt verschluesselt im Datenordner
(belege.json). Geht der Index verloren, bleiben die Dateien -- die Kennung im Dateinamen
erlaubt die Wiederzuordnung.
"""
from __future__ import annotations

import csv
import io
import os
import re
import secrets
import shutil
import zipfile
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from mm_store import Store

DEFAULT_FOLDER = "~/Documents/Kontor-Belege"
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".heic", ".gif", ".txt", ".csv", ".xlsx", ".docx", ".eml", ".msg", ".zip"}
MAX_FILE = 60 * 1024 * 1024


def file_status(full: str) -> str:
    """ok | icloud (Platzhalter, nicht geladen) | fehlt"""
    if os.path.isfile(full):
        return "ok"
    d, n = os.path.split(full)
    if os.path.isfile(os.path.join(d, "." + n + ".icloud")):
        return "icloud"
    return "fehlt"


def _safe(s: str, n: int = 40) -> str:
    s = re.sub(r"[^\w\-. äöüÄÖÜß]", "", str(s or "")).strip().replace(" ", "-")
    return s[:n] or "Beleg"


class Belege:
    def __init__(self, store: Store, config: dict):
        self.store = store
        cfg = config.get("belege", {}) or {}
        self.folder = os.path.expanduser(cfg.get("ordner") or DEFAULT_FOLDER)
        self.pattern = cfg.get("unterordner") or "{jahr}"
        self.index = store.load("belege.json", {"eintraege": []}) or {"eintraege": []}

    # -- Ordner ------------------------------------------------------------
    def ensure_folder(self) -> Optional[str]:
        try:
            os.makedirs(self.folder, exist_ok=True)
            return None
        except OSError as e:
            return "Belegordner nicht anlegbar: %s (%s)" % (self.folder, e)

    def subfolder(self, tx: Optional[dict]) -> str:
        d = (tx or {}).get("datum") or date.today().isoformat()
        vals = {"jahr": d[:4], "monat": d[5:7], "entitaet": _safe((tx or {}).get("entitaet_name") or "Allgemein", 30),
                "konto": _safe((tx or {}).get("konto_name") or "Konto", 30)}
        try:
            return self.pattern.format(**vals)
        except (KeyError, IndexError, ValueError):
            return vals["jahr"]

    # -- Index -------------------------------------------------------------
    def _save(self) -> None:
        self.store.save("belege.json", self.index)

    def entries(self) -> List[dict]:
        return self.index.setdefault("eintraege", [])

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
            raise ValueError("Dateityp %s nicht erlaubt (%s)." % (ext or "ohne Endung", ", ".join(sorted(ALLOWED_EXT))))
        if len(data) > MAX_FILE:
            raise ValueError("Datei zu gross (max. %d MB)." % (MAX_FILE // (1024 * 1024)))
        if not data:
            raise ValueError("Leere Datei.")
        kennung = secrets.token_hex(3)
        sub = self.subfolder(tx)
        target_dir = os.path.join(self.folder, sub)
        os.makedirs(target_dir, exist_ok=True)
        if tx:
            base = "%s_%s_%s_%s" % (tx.get("datum", "0000-00-00"), ("%.2f" % abs(float(tx.get("betrag") or 0))).replace(".", ","),
                                    _safe(tx.get("name") or os.path.splitext(filename)[0]), kennung)
        else:
            base = "%s_%s_%s" % (date.today().isoformat(), _safe(os.path.splitext(filename)[0]), kennung)
        name = base + ext
        with open(os.path.join(target_dir, name), "wb") as f:
            f.write(data)
        os.chmod(os.path.join(target_dir, name), 0o600)
        entry = {"id": kennung, "tx_id": (tx or {}).get("id"), "konto": (tx or {}).get("konto"), "entitaet": (tx or {}).get("entitaet"),
                 "datum": (tx or {}).get("datum") or date.today().isoformat(), "betrag": (tx or {}).get("betrag"),
                 "name": (tx or {}).get("name") or os.path.splitext(filename)[0], "pfad": os.path.join(sub, name).replace("\\", "/"),
                 "groesse": len(data), "hinzugefuegt": datetime.now().strftime("%Y-%m-%d %H:%M"), "notiz": notiz, "original": filename}
        self.entries().append(entry)
        self._save()
        return entry

    def link_existing(self, tx: Optional[dict], rel_path: str, notiz: str = "") -> dict:
        full = os.path.normpath(os.path.join(self.folder, rel_path))
        if not full.startswith(os.path.normpath(self.folder) + os.sep) or not os.path.isfile(full):
            raise ValueError("Datei liegt nicht im Belegordner.")
        entry = {"id": secrets.token_hex(3), "tx_id": (tx or {}).get("id"), "konto": (tx or {}).get("konto"), "entitaet": (tx or {}).get("entitaet"),
                 "datum": (tx or {}).get("datum") or date.today().isoformat(), "betrag": (tx or {}).get("betrag"),
                 "name": (tx or {}).get("name") or os.path.basename(rel_path), "pfad": rel_path.replace("\\", "/"),
                 "groesse": os.path.getsize(full), "hinzugefuegt": datetime.now().strftime("%Y-%m-%d %H:%M"), "notiz": notiz, "original": os.path.basename(rel_path)}
        self.entries().append(entry)
        self._save()
        return entry

    def link_external(self, tx: Optional[dict], abs_path: str, notiz: str = "") -> dict:
        """Verknuepfung auf eine Datei ausserhalb des Belegordners (z. B. iCloud Drive). Die Datei bleibt, wo sie ist."""
        full = os.path.normpath(os.path.expanduser(abs_path))
        if not os.path.isabs(full):
            raise ValueError("Bitte einen vollstaendigen Pfad angeben.")
        st = file_status(full)
        if st == "fehlt":
            raise ValueError("Datei nicht gefunden: %s" % full)
        entry = {"id": secrets.token_hex(3), "tx_id": (tx or {}).get("id"), "konto": (tx or {}).get("konto"), "entitaet": (tx or {}).get("entitaet"),
                 "datum": (tx or {}).get("datum") or date.today().isoformat(), "betrag": (tx or {}).get("betrag"),
                 "name": (tx or {}).get("name") or os.path.basename(full), "pfad": full, "extern": True,
                 "groesse": os.path.getsize(full) if st == "ok" else 0, "hinzugefuegt": datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "notiz": notiz, "original": os.path.basename(full)}
        self.entries().append(entry)
        self._save()
        return entry

    def full_path(self, entry: dict) -> str:
        if entry.get("extern"):
            return os.path.normpath(entry["pfad"])
        return os.path.normpath(os.path.join(self.folder, entry["pfad"]))

    def remove(self, entry_id: str, delete_file: bool = False) -> bool:
        for e in list(self.entries()):
            if e["id"] == entry_id:
                self.entries().remove(e)
                if delete_file and not e.get("extern"):      # externe Dateien werden nie geloescht
                    try:
                        os.remove(os.path.join(self.folder, e["pfad"]))
                    except OSError:
                        pass
                self._save()
                return True
        return False

    def update(self, entry_id: str, **fields) -> Optional[dict]:
        for e in self.entries():
            if e["id"] == entry_id:
                for k, v in fields.items():
                    if k in ("notiz", "tx_id", "konto", "entitaet", "datum", "betrag", "name"):
                        e[k] = v
                self._save()
                return e
        return None

    # -- Ordnerinhalt ------------------------------------------------------
    def listing(self) -> List[dict]:
        out = []
        linked = {e["pfad"] for e in self.entries()}
        if not os.path.isdir(self.folder):
            return out
        for root, dirs, files in os.walk(self.folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "Export"]
            for fn in files:
                if fn.startswith("."):
                    continue
                rel = os.path.relpath(os.path.join(root, fn), self.folder).replace("\\", "/")
                out.append({"pfad": rel, "groesse": os.path.getsize(os.path.join(root, fn)), "verknuepft": rel in linked})
        out.sort(key=lambda x: x["pfad"])
        return out

    def check(self) -> List[str]:
        """Fehlende Dateien im Index (iCloud-Platzhalter gelten als vorhanden)."""
        return [e["pfad"] for e in self.entries() if file_status(self.full_path(e)) == "fehlt"]

    # -- Export ------------------------------------------------------------
    def export_zip(self, jahr: Optional[str], entitaet: Optional[str], names: Dict[str, str]) -> str:
        err = self.ensure_folder()
        if err:
            raise OSError(err)
        sel = [e for e in self.entries() if (not jahr or (e.get("datum") or "").startswith(jahr))
               and (not entitaet or e.get("entitaet") == entitaet)]
        exp_dir = os.path.join(self.folder, "Export")
        os.makedirs(exp_dir, exist_ok=True)
        label = "_".join(x for x in (jahr or "alle", _safe(names.get(entitaet or "", "alle"), 30)) if x)
        target = os.path.join(exp_dir, "Belege_%s.zip" % label)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Datum", "Betrag", "Name", "Konto", "Entität", "Datei", "Notiz", "Umsatz-ID"])
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            for e in sel:
                full = self.full_path(e)
                if os.path.isfile(full):
                    z.write(full, ("extern/" + os.path.basename(full)) if e.get("extern") else e["pfad"])
                w.writerow([e.get("datum"), ("%.2f" % e["betrag"]).replace(".", ",") if isinstance(e.get("betrag"), (int, float)) else "",
                            e.get("name"), names.get(e.get("konto") or "", e.get("konto") or ""), names.get(e.get("entitaet") or "", ""),
                            e["pfad"], e.get("notiz", ""), e.get("tx_id") or ""])
            z.writestr("Belege.csv", "﻿" + buf.getvalue())
        os.chmod(target, 0o600)
        return target
