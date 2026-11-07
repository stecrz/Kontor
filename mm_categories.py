"""Kategorien nach MoneyMoney zurueckschreiben.

Geschrieben wird nur das Kategoriefeld einzelner Umsaetze (setTransaction, per Kategorie-UUID) -- keine Betraege,
Daten, Loeschungen, keine Kategorien oder Regeln. Vor jedem Schreiben liest Kontor den Umsatz frisch aus MoneyMoney und
schreibt nur, wenn er noch so aussieht wie in Kontor (gleiches Konto, Datum, Betrag, Name) und
  - noch keine Kategorie hat, oder
  - die Kategorie traegt, die Kontor selbst zuletzt geschrieben hat, oder
  - die Ueberschreibung einer fremden Kategorie ausdruecklich bestaetigt wurde und MoneyMoney noch genau die Kategorie
    zeigt, die bei der Bestaetigung zu sehen war.
Jede geschriebene Aenderung landet im Protokoll (state.json, mm_kategorien_log: Umsatz -> zuletzt geschriebene Kategorie).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from mm_bridge import local_date
from model import Ledger, norm_cat

log = logging.getLogger("kontor.mmcat")

LOG_KEY = "mm_kategorien_log"
LOG_MAX = 20000


def with_paths(categories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """MoneyMoney liefert die Kategorien als flache Liste mit Einrueckung (ohne Pfad): Pfad 'A\\B\\C' daraus bilden."""
    stack: List[str] = []
    for c in categories or []:
        name = str(c.get("name") or "")
        if not c.get("path"):
            ind = int(c.get("indentation") or 0)
            stack = stack[:ind]
            c["path"] = "\\".join(stack + [name])
        stack = str(c["path"]).split("\\")
    return categories


def index(categories: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Normierter Pfad ('A / B') -> {uuid, path, group, default} der Kategorien in MoneyMoney."""
    out: Dict[str, Dict[str, Any]] = {}
    for c in categories or []:
        p = norm_cat(str(c.get("path") or c.get("name") or ""))
        if p:
            out[p] = {"uuid": str(c.get("uuid") or ""), "path": str(c.get("path") or c.get("name") or ""),
                      "group": bool(c.get("group")), "default": bool(c.get("default"))}
    return out


def assignable(idx: Dict[str, Dict[str, Any]], path: str) -> Optional[str]:
    """Grund, warum `path` in MoneyMoney nicht gesetzt werden kann (None = geht): fehlt, Ordner, Standardkategorie."""
    c = idx.get(norm_cat(path))
    if c is None:
        return "fehlt"
    if c["group"]:
        return "ordner"
    if c["default"]:
        return "standard"
    return None


def _mm_cat(raw: Dict[str, Any]) -> str:
    return norm_cat(str(raw.get("categoryPath") or raw.get("category") or ""))


def write(bridge, ledger: Ledger, items: List[Dict[str, Any]], idx: Dict[str, Dict[str, Any]],
          own: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """items: [{id, neu, alt (was in MoneyMoney zu sehen war, normiert), ueberschreiben}].
    Liefert {geschrieben: [{id, alt, neu}], wartet: [id] (Kategorie fehlt in MoneyMoney), fremd: [{id, mm}] (fremde
    Kategorie, nicht bestaetigt), gleich: [id], fehler: [{id, grund}]}."""
    res: Dict[str, Any] = {"geschrieben": [], "wartet": [], "fremd": [], "gleich": [], "fehler": []}
    by_id = {t.id: t for t in ledger.txs if t.id > 0}
    todo: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for it in items:
        t = by_id.get(int(it["id"]))
        if t is None:
            res["fehler"].append({"id": it["id"], "grund": "unbekannt"})
            continue
        why = assignable(idx, it["neu"])
        if why == "fehlt":
            res["wartet"].append(t.id)
            continue
        if why:
            res["fehler"].append({"id": t.id, "grund": why})
            continue
        todo[t.account_uuid].append(dict(it, tx=t))
    for acc, its in todo.items():
        # frisch aus MoneyMoney: nur dieses Konto, nur der Zeitraum der betroffenen Umsaetze (Buchungs- und Wertstellungsdatum)
        days = [d for it in its for d in (it["tx"].booking_date, it["tx"].value_date) if d]
        fresh = {int(r.get("id") or 0): r for r in bridge.export_transactions(min(days) - timedelta(days=7), max(days) + timedelta(days=7), account=acc)}
        for it in its:
            t, neu = it["tx"], norm_cat(it["neu"])
            r = fresh.get(t.id)
            if r is None:
                res["fehler"].append({"id": t.id, "grund": "nicht_gefunden"}); continue
            if (str(r.get("accountUuid") or "") != t.account_uuid or local_date(r.get("bookingDate")) != t.booking_date
                    or abs(float(r.get("amount") or 0) - t.amount) > 0.005 or str(r.get("name") or "") != t.name):
                res["fehler"].append({"id": t.id, "grund": "abweichend"}); continue
            cur = _mm_cat(r)
            if cur == neu:
                res["gleich"].append(t.id); continue
            mine = norm_cat((own.get(str(t.id)) or {}).get("neu") or "")
            if cur and cur != mine and not (it.get("ueberschreiben") and cur == norm_cat(it.get("alt") or "")):
                res["fremd"].append({"id": t.id, "mm": cur}); continue
            bridge.set_transaction(t.id, category=idx[neu]["uuid"] or idx[neu]["path"])
            res["geschrieben"].append({"id": t.id, "alt": cur, "neu": neu})
    if res["geschrieben"]:
        log.info("Category set in MoneyMoney for %d transaction(s)", len(res["geschrieben"]))
    if res["fehler"]:
        log.warning("Category not set in MoneyMoney for %d transaction(s): %s", len(res["fehler"]),
                    ", ".join(sorted({f["grund"] for f in res["fehler"]})))
    return res


def apply_to_ledger(ledger: Ledger, idx: Dict[str, Dict[str, Any]], written: List[Dict[str, Any]]) -> None:
    """Geschriebene Kategorien in den Stand im Speicher uebernehmen (so wie MoneyMoney sie jetzt liefert), damit auch das
    schnelle Lesen (aeltere Umsaetze aus dem Stand) sie kennt."""
    by_id = {t.id: t for t in ledger.txs if t.id > 0}
    for w in written:
        t = by_id.get(w["id"])
        if t is None:
            continue
        raw = idx[w["neu"]]["path"]
        if t.mm_category_path is not None:
            t.mm_category_path = raw
        else:
            t.category_path = raw
            t.category = raw.split("\\")[-1]
        t.category_uuid = idx[w["neu"]]["uuid"]


def remember(state: dict, written: List[Dict[str, Any]]) -> None:
    """Protokoll: Umsatz -> zuletzt von Kontor geschriebene Kategorie (begrenzt auf die neuesten LOG_MAX)."""
    lg = state.setdefault(LOG_KEY, {})
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for w in written:
        lg[str(w["id"])] = {"neu": w["neu"], "alt": w["alt"], "zeit": now}
    if len(lg) > LOG_MAX:
        for k, _ in sorted(lg.items(), key=lambda kv: kv[1].get("zeit") or "")[:len(lg) - LOG_MAX]:
            lg.pop(k, None)
