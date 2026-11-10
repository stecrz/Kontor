"""Kontor-eigene Kategorien: Baum, Zuordnungen je Umsatz, Regeln (gelernt und manuell).

MoneyMoney ist massgeblich: hat ein Umsatz dort eine Kategorie, gilt sie -- ausser Kontor soll sie ausdruecklich
uebersteuern (Zuordnung mit "ov", z. B. "nur in Kontor" gewaehlt oder Regeln mit "MoneyMoney ueberschreiben").
Umsaetze ohne Kategorie in MoneyMoney ordnet Kontor zu (von Hand oder per Regel); von Hand Zugeordnetes schreibt Kontor
nach MoneyMoney zurueck, wenn das eingeschaltet ist (mm_categories). Zuordnung mit "w": wartet darauf, dass es die
Kategorie in MoneyMoney gibt. Alles liegt verschluesselt in categories.json.

Pfade sind kanonisch 'A / B / C' (siehe model.norm_cat)."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from functools import lru_cache
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from model import Ledger, Tx, has_mark, norm_cat
from i18n import tr

FILE = "categories.json"
UMBUCHUNG = "Umbuchung"


def empty() -> dict:
    return {"version": 1, "baum": [], "zuordnung": {}, "regeln": [], "gelernt_am": None, "mm_uebernommen": False}


def load(store) -> dict:
    d = store.load(FILE, None) or empty()
    d.setdefault("baum", []); d.setdefault("zuordnung", {}); d.setdefault("regeln", [])
    return d


LOCK = threading.RLock()        # writing the file; the report checks and writes under it (see core._prepare_categories)


def save(store, d: dict) -> None:
    with LOCK:
        store.save(FILE, {k: v for k, v in d.items() if not k.startswith("_")})      # "_..." = Zwischenspeicher, nicht ablegen


def digest(d: dict) -> Dict[str, str]:
    """A fingerprint per part (tree, assignments, rules ...): which parts changed since it was read."""
    return {k: hashlib.sha1(json.dumps(v, sort_keys=True, default=str).encode()).hexdigest() for k, v in d.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Verwendung der Kategorien aus MoneyMoney in Kontor (Einrichtung -> Kategorien auswaehlen)
#   fehlt/"zeile": eigene Zeile · "zusammen": zaehlt samt Unterkategorien zur Oberkategorie · "ignorieren": in Kontor wie
#   ohne Kategorie (auch alle Unterkategorien)
# ---------------------------------------------------------------------------
VERWENDUNG = ("zeile", "zusammen", "ignorieren")


def set_usage(d: dict, usage: Dict[str, str]) -> None:
    clean = {}
    for k, v in (usage or {}).items():
        p = norm_cat(k)
        if not p or v not in VERWENDUNG or v == "zeile":
            continue
        if v == "zusammen" and " / " not in p:
            continue                                   # oberste Ebene hat keine Oberkategorie
        clean[p] = v
    d["verwendung"] = clean
    d.pop("_ign", None)


def ignored(d: dict, path: str) -> bool:
    """Kategorie (oder eine ihrer Oberkategorien) soll in Kontor nicht verwendet werden."""
    if not path:
        return False
    c = d.get("_ign")
    if c is None:
        c = d["_ign"] = {"__set__": {k for k, v in (d.get("verwendung") or {}).items() if v == "ignorieren"}}
    hit = c.get(path)
    if hit is None:
        ign, parts = c["__set__"], path.split(" / ")
        hit = c[path] = bool(ign) and any(" / ".join(parts[:i]) in ign for i in range(1, len(parts) + 1))
    return hit


def fold(usage: Dict[str, str], path: str) -> str:
    """Zeile im Kapitalfluss: die erste Kategorie im Pfad, die zusammengefasst werden soll, zaehlt zu ihrer Oberkategorie."""
    if not usage or " / " not in path:
        return path
    parts = path.split(" / ")
    for i in range(1, len(parts)):
        if usage.get(" / ".join(parts[:i + 1])) == "zusammen":
            return " / ".join(parts[:i])
    return path


# ---------------------------------------------------------------------------
# Baum
# ---------------------------------------------------------------------------

def _slug(path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", path.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")).strip("-")[:80] or "k"


def by_path(d: dict) -> Dict[str, dict]:
    return {k["pfad"]: k for k in d["baum"]}


def ensure_category(d: dict, path: str, quelle: str = "manuell", sektion: Optional[str] = None) -> dict:
    """Kategorie (und Oberkategorien) anlegen, falls nicht vorhanden."""
    path = norm_cat(path)
    if not path:
        raise ValueError(tr("s_kategoriename_fehlt"))
    existing = by_path(d)
    parts = path.split(" / ")
    node = None
    for i in range(1, len(parts) + 1):
        p = " / ".join(parts[:i])
        node = existing.get(p)
        if node is None:
            node = {"id": _slug(p) + ("" if _slug(p) not in {k["id"] for k in d["baum"]} else "-%d" % len(d["baum"])),
                    "pfad": p, "name": parts[i - 1], "quelle": quelle, "aktiv": True}
            if sektion and i == len(parts):
                node["sektion"] = sektion
            d["baum"].append(node)
            existing[p] = node
    return node


def rename_category(d: dict, old: str, new: str) -> int:
    """Pfad umbenennen/verschieben (inkl. Unterkategorien, Zuordnungen, Regeln). Liefert Anzahl betroffener Knoten."""
    old, new = norm_cat(old), norm_cat(new)
    if not old or not new:
        raise ValueError(tr("s_pfad_fehlt"))
    n = 0
    for k in d["baum"]:
        if k["pfad"] == old or k["pfad"].startswith(old + " / "):
            k["pfad"] = new + k["pfad"][len(old):]
            k["name"] = k["pfad"].split(" / ")[-1]
            n += 1
    for z in d["zuordnung"].values():
        if z.get("k") == old or str(z.get("k", "")).startswith(old + " / "):
            z["k"] = new + z["k"][len(old):]
    for r in d["regeln"]:
        if r.get("kategorie") == old or str(r.get("kategorie", "")).startswith(old + " / "):
            r["kategorie"] = new + r["kategorie"][len(old):]
    ensure_category(d, new)
    return n


def delete_category(d: dict, path: str, ersatz: Optional[str] = None) -> int:
    """Kategorie loeschen; Zuordnungen und Regeln auf 'ersatz' umhaengen (oder entfernen)."""
    path = norm_cat(path)
    d["baum"] = [k for k in d["baum"] if not (k["pfad"] == path or k["pfad"].startswith(path + " / "))]
    n = 0
    for tid in list(d["zuordnung"]):
        z = d["zuordnung"][tid]
        if z.get("k") == path or str(z.get("k", "")).startswith(path + " / "):
            n += 1
            if ersatz:
                z["k"] = norm_cat(ersatz)
            else:
                del d["zuordnung"][tid]
    for r in list(d["regeln"]):
        if r.get("kategorie") == path or str(r.get("kategorie", "")).startswith(path + " / "):
            if ersatz:
                r["kategorie"] = norm_cat(ersatz)
            else:
                d["regeln"].remove(r)
    if ersatz:
        ensure_category(d, ersatz)
    return n


MM_PFADE = 1          # Version der Uebernahme (1: volle Pfade aus der Einrueckung)


def seed_from_moneymoney(d: dict, categories: List[dict]) -> int:
    """MoneyMoney-Kategorienbaum als Vorschlag uebernehmen (nur neue Pfade). Knoten frueherer Uebernahmen, die es in
    MoneyMoney so nicht gibt (frueher nur der Name statt des Pfads) und an denen nichts haengt, fallen weg."""
    n = 0
    mm = {norm_cat(str(c.get("path") or c.get("name") or "")) for c in categories or []}
    used = {str(z.get("k") or "") for z in d["zuordnung"].values()} | {str(r.get("kategorie") or "") for r in d["regeln"]}
    keep = lambda k: (k.get("quelle") != "moneymoney" or k["pfad"] in mm or any(u == k["pfad"] or u.startswith(k["pfad"] + " / ") for u in used)
                      or any(p.startswith(k["pfad"] + " / ") for p in mm))
    d["baum"] = [k for k in d["baum"] if keep(k)]
    existing = by_path(d)
    for c in categories or []:
        raw = str(c.get("path") or c.get("name") or "")
        p = norm_cat(raw)
        if not p or p in existing:
            continue
        node = ensure_category(d, p, quelle="moneymoney")
        node["mm_pfad"] = raw
        existing[p] = node
        n += 1
    d["mm_uebernommen"] = True
    d["mm_pfade"] = MM_PFADE
    return n


# ---------------------------------------------------------------------------
# Wirksame Kategorie je Umsatz
# ---------------------------------------------------------------------------

def mm_of(t: Tx) -> str:
    """Kategorie des Umsatzes in MoneyMoney (normiert)."""
    return norm_cat(t.mm_category_path if t.mm_category_path is not None else t.category_path)


def mm_used(d: dict, t: Tx) -> str:
    """Kategorie aus MoneyMoney, soweit Kontor sie verwendet ('' bei "nicht verwenden")."""
    mm = mm_of(t)
    return "" if mm and ignored(d, mm) else mm


def effective(d: dict, t: Tx) -> Tuple[str, str]:
    """(Pfad, Quelle): Kategorie aus MoneyMoney; ohne (oder ausdruecklich uebersteuert) die Zuordnung in Kontor; sonst ''."""
    z = d["zuordnung"].get(str(t.id))
    mm = mm_used(d, t)
    if z and z.get("k") and (not mm or z.get("ov")):
        return z["k"], z.get("q", "manuell")
    return (mm, "moneymoney") if mm else ("", "")


def apply_to_ledger(d: dict, ledger: Ledger) -> Dict[str, int]:
    """Kontor-Zuordnungen auf die Umsaetze legen (category_path in-memory ueberschreiben). Liefert Zaehler je Quelle."""
    counts: Counter = Counter()
    for t in ledger.txs:
        if t.mm_category_path is None:
            t.mm_category_path = t.category_path
        path, q = effective(d, t)
        if q and q != "moneymoney":
            t.category_path = path.replace(" / ", "\\")
            t.category = path.split(" / ")[-1]
        elif q:
            t.category_path = t.mm_category_path
            t.category = norm_cat(t.mm_category_path).split(" / ")[-1] if t.mm_category_path else ""
        else:                                            # ohne Kategorie (oder "nicht verwenden")
            t.category_path, t.category = "", ""
        counts[q or "ohne"] += 1
    return dict(counts)


# ---------------------------------------------------------------------------
# Regeln
# ---------------------------------------------------------------------------

_WS = re.compile(r"\s+")
_NUM = re.compile(r"\d[\d.,/-]*")


@lru_cache(maxsize=8192)
def norm_name(s: str) -> str:
    s = (s or "").lower()
    s = _NUM.sub(" ", s)
    s = re.sub(r"[^\wäöüß]+", " ", s)
    return _WS.sub(" ", s).strip()[:60]


def purpose_key(s: str, words: int = 3) -> str:
    return " ".join(norm_name(s).split()[:words])


def rule_matches(r: dict, t: Tx) -> bool:
    if not r.get("aktiv", True):
        return False
    if r.get("konto") and r["konto"] != t.account_uuid:
        return False
    if r.get("richtung") == "aus" and t.amount >= 0:
        return False
    if r.get("richtung") == "ein" and t.amount <= 0:
        return False
    if r.get("iban"):
        if r["iban"].replace(" ", "").upper() != (t.counter_iban or "").replace(" ", "").upper():
            return False
    if r.get("name_ist"):
        if norm_name(r["name_ist"]) != norm_name(t.name):
            return False
    if r.get("name_enthaelt"):
        if norm_name(r["name_enthaelt"]) not in norm_name(t.name):
            return False
    if r.get("zweck_enthaelt"):
        if norm_name(r["zweck_enthaelt"]) not in norm_name(t.purpose + " " + t.booking_text):
            return False
    if r.get("betrag_von") not in (None, "") and abs(t.amount) < float(r["betrag_von"]):
        return False
    if r.get("betrag_bis") not in (None, "") and abs(t.amount) > float(r["betrag_bis"]):
        return False
    return bool(r.get("iban") or r.get("name_ist") or r.get("name_enthaelt") or r.get("zweck_enthaelt"))


def _specificity(r: dict) -> Tuple[int, int, int]:
    return (1 if r.get("quelle") == "manuell" else 0,
            (3 if r.get("iban") else 0) + (2 if r.get("zweck_enthaelt") else 0) + (2 if r.get("name_ist") else 0) + (1 if r.get("name_enthaelt") else 0)
            + (1 if r.get("konto") else 0) + (1 if r.get("richtung") else 0),
            int(r.get("prio") or 0))


def suggest(d: dict, t: Tx) -> Optional[dict]:
    """Beste passende Regel fuer einen Umsatz."""
    best = None
    for r in d["regeln"]:
        if rule_matches(r, t):
            if best is None or _specificity(r) > _specificity(best):
                best = r
    return best


def learn(d: dict, ledger: Ledger, min_count: int = 2, min_share: float = 0.9, progress=None) -> Dict[str, int]:
    """Regeln aus vorhandenen Zuordnungen (Kontor manuell + MoneyMoney) ableiten. Ersetzt die gelernten Regeln,
    manuelle bleiben. Reihenfolge: Gegen-IBAN, Name + Zweckanfang, Name."""
    samples: List[Tuple[Tx, str]] = []
    n_all = len(ledger.txs) or 1
    for i, t in enumerate(ledger.txs):
        if progress and i % 20000 == 0:
            progress(0.5 * i / n_all)
        path, q = effective(d, t)
        if path and q in ("manuell", "moneymoney"):
            samples.append((t, path))
    groups: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
    for i, (t, path) in enumerate(samples):
        if progress and i % 20000 == 0:
            progress(0.5 + 0.3 * i / (len(samples) or 1))
        iban = (t.counter_iban or "").replace(" ", "").upper()
        nm = norm_name(t.name)
        if iban and len(iban) >= 8:
            groups[("iban", iban)][path] += 1
        if nm:
            groups[("name", nm)][path] += 1
            pk = purpose_key(t.purpose)
            if pk:
                groups[("name+zweck", nm + "|" + pk)][path] += 1
    if progress:
        progress(0.8)
    manual = [r for r in d["regeln"] if r.get("quelle") == "manuell"]
    learned: List[dict] = []
    seen_names: set = set()
    stats = Counter()
    # Name-Regeln nur, wenn eindeutig; sonst Name+Zweck-Regeln
    for (kind, key), cnt in groups.items():
        total = sum(cnt.values())
        path, n = cnt.most_common(1)[0]
        if total < min_count or n / total < min_share:
            continue
        if kind == "name":
            seen_names.add(key)
    for (kind, key), cnt in sorted(groups.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(cnt.values())
        path, n = cnt.most_common(1)[0]
        if total < min_count or n / total < min_share:
            continue
        rid = "g-" + _slug(kind + "-" + key)[:70]
        if kind == "iban":
            r = {"id": rid, "kategorie": path, "iban": key, "quelle": "gelernt", "treffer": total, "aktiv": True}
        elif kind == "name":
            r = {"id": rid, "kategorie": path, "name_ist": key, "quelle": "gelernt", "treffer": total, "aktiv": True}
        else:
            nm, pk = key.split("|", 1)
            if nm in seen_names:
                continue      # Name allein reicht
            r = {"id": rid, "kategorie": path, "name_ist": nm, "zweck_enthaelt": pk, "quelle": "gelernt", "treffer": total, "aktiv": True}
        learned.append(r)
        stats[kind] += 1
    d["regeln"] = manual + learned
    d["gelernt_am"] = time.strftime("%Y-%m-%d %H:%M")
    return {"regeln": len(learned), "muster": len(samples), **{k: v for k, v in stats.items()}}


def auto_assign(d: dict, ledger: Ledger, overwrite_mm: bool = False, progress=None) -> int:
    """Regeln auf Umsaetze ohne manuelle Zuordnung anwenden. overwrite_mm: auch Umsaetze mit MoneyMoney-Kategorie
    (sonst gilt die MoneyMoney-Kategorie weiter). Liefert Anzahl neu/anders zugeordneter Umsaetze."""
    n = 0
    n_all = len(ledger.txs) or 1
    for i, t in enumerate(ledger.txs):
        if progress and i % 20000 == 0:
            progress(i / n_all)
        tid = str(t.id)
        z = d["zuordnung"].get(tid)
        if z and z.get("q") == "manuell":
            continue
        mm_path = mm_used(d, t)
        if not overwrite_mm and mm_path:
            if z and z.get("q") == "regel":
                del d["zuordnung"][tid]        # MoneyMoney-Kategorie gilt wieder
                n += 1
            continue
        r = suggest(d, t)
        if r is None:
            if z and z.get("q") == "regel":
                del d["zuordnung"][tid]
                n += 1
            continue
        ov = bool(overwrite_mm and mm_path)
        if not z or z.get("k") != r["kategorie"] or z.get("r") != r["id"] or bool(z.get("ov")) != ov:
            d["zuordnung"][tid] = dict({"k": r["kategorie"], "q": "regel", "r": r["id"]}, **({"ov": True} if ov else {}))
            n += 1
    return n


def assign(d: dict, tx_ids: List[int], path: str, quelle: str = "manuell", rule_id: Optional[str] = None) -> int:
    path = norm_cat(path)
    if path:
        ensure_category(d, path)
    n = 0
    for tid in tx_ids:
        if path:
            d["zuordnung"][str(tid)] = {"k": path, "q": quelle, **({"r": rule_id} if rule_id else {})}
        else:
            d["zuordnung"].pop(str(tid), None)
        n += 1
    return n


def add_rule(d: dict, rule: dict) -> dict:
    r = {"id": rule.get("id") or ("m-%d" % int(time.time() * 1000 % 10 ** 9)), "kategorie": norm_cat(rule.get("kategorie") or ""),
         "quelle": "manuell", "aktiv": bool(rule.get("aktiv", True)), "prio": int(rule.get("prio") or 0)}
    for k in ("iban", "name_ist", "name_enthaelt", "zweck_enthaelt", "konto", "richtung", "betrag_von", "betrag_bis", "notiz"):
        v = rule.get(k)
        if v not in (None, ""):
            r[k] = v
    if not r["kategorie"]:
        raise ValueError(tr("s_regel_kategorie_fehlt"))
    if not (r.get("iban") or r.get("name_ist") or r.get("name_enthaelt") or r.get("zweck_enthaelt")):
        raise ValueError(tr("s_regel_mindestens_gegen_iban_name"))
    ensure_category(d, r["kategorie"])
    d["regeln"] = [x for x in d["regeln"] if x.get("id") != r["id"]] + [r]
    return r


def open_items(d: dict, ledger: Ledger, bereich_of: Dict[str, str], jahr: Optional[int] = None, bereich: Optional[str] = None,
               min_betrag: float = 0.0, limit: int = 400) -> Dict[str, Any]:
    """Umsaetze ohne wirksame Kategorie, gruppiert nach Gegenpartei, mit Vorschlag aus den Regeln."""
    groups: Dict[str, dict] = {}
    total = 0
    for t in ledger.txs:
        if not t.booked or has_mark(t.purpose):          # eigene Buchungen von Kontor (Spiegelung, Zins, Wert) brauchen keine Kategorie
            continue
        path, q = effective(d, t)
        if path:
            continue
        if jahr and t.booking_date.year != jahr:
            continue
        if bereich and bereich_of.get(t.account_uuid) != bereich:
            continue
        if min_betrag and abs(t.amount) < min_betrag:
            continue
        total += 1
        key = (t.counter_iban or "").replace(" ", "").upper() or norm_name(t.name) or ("zweck:" + purpose_key(t.purpose, 4))
        g = groups.get(key)
        if g is None:
            r = suggest(d, t)
            g = groups[key] = {"key": key, "name": t.name[:80] or t.purpose[:80], "iban": (t.counter_iban or "")[:34], "anzahl": 0, "summe": 0.0, "ids": [],
                               "beispiele": [], "vorschlag": r["kategorie"] if r else None, "regel": r["id"] if r else None,
                               "konto": ledger.accounts[t.account_uuid].name if t.account_uuid in ledger.accounts else "", "von": t.booking_date.isoformat(), "bis": t.booking_date.isoformat()}
        g["anzahl"] += 1
        g["summe"] = round(g["summe"] + t.amount, 2)
        g["ids"].append(t.id)
        g["von"] = min(g["von"], t.booking_date.isoformat()); g["bis"] = max(g["bis"], t.booking_date.isoformat())
        if len(g["beispiele"]) < 3:
            g["beispiele"].append({"id": t.id, "datum": t.booking_date.isoformat(), "betrag": t.amount, "zweck": t.purpose[:120], "konto": g["konto"]})
    out = sorted(groups.values(), key=lambda g: (-abs(g["summe"]), -g["anzahl"]))
    return {"offen": total, "gruppen": out[:limit], "gruppen_gesamt": len(out)}


def stats(d: dict, ledger: Ledger) -> Dict[str, Any]:
    c: Counter = Counter()
    years: Dict[int, Counter] = defaultdict(Counter)
    for t in ledger.txs:
        if has_mark(t.purpose):
            continue
        path, q = effective(d, t)
        k = q or "ohne"
        c[k] += 1
        years[t.booking_date.year][k] += 1
    return {"gesamt": dict(c), "jahre": {str(y): dict(v) for y, v in sorted(years.items())}, "kategorien": len(d["baum"]),
            "regeln": {"manuell": sum(1 for r in d["regeln"] if r.get("quelle") == "manuell"), "gelernt": sum(1 for r in d["regeln"] if r.get("quelle") == "gelernt")},
            "gelernt_am": d.get("gelernt_am")}
