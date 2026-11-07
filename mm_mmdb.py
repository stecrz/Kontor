"""Lesender Zugriff auf MoneyMoneys eigene Datenbank (nur fuer die Kontostand-Historie).

MoneyMoneys Skript-Schnittstelle liefert nur aktuelle Salden und Umsaetze. Die Kontostand-Kurve, die MoneyMoney
anzeigt, liegt nur in seiner Datenbank (SQLCipher, verschluesselt mit dem MoneyMoney-Passwort).

Sicherheit:
* Das Passwort wird nur fuer den einen Aufruf verwendet: per Standardeingabe an sqlcipher (nicht in der
  Befehlszeile, also nicht in der Prozessliste), nie gespeichert, nie protokolliert.
* Die Datenbank wird nur lesend geoeffnet (-readonly); Kontor schreibt nie hinein.
* Schritt 1 (pruefen) liest nur den Aufbau (Tabellen, Spalten, Zeilenzahl) -- keine Betraege, keine Namen.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple

DB_PATH = os.path.expanduser("~/Library/Containers/com.moneymoney-app.retail/Data/Library/Application Support/MoneyMoney/Database/MoneyMoney.sqlite")
SQLCIPHER_CANDIDATES = ["/opt/homebrew/bin/sqlcipher", "/usr/local/bin/sqlcipher", "/opt/homebrew/opt/sqlcipher/bin/sqlcipher"]


class MMDBError(Exception):
    pass


def find_sqlcipher() -> Optional[str]:
    p = shutil.which("sqlcipher")
    if p:
        return p
    return next((c for c in SQLCIPHER_CANDIDATES if os.path.exists(c) and os.access(c, os.X_OK)), None)


def _quote(pw: str) -> str:
    return "'" + pw.replace("'", "''") + "'"


def _run(password: str, sql: str, compat: int, db: Optional[str] = None, timeout: int = 120) -> str:
    db = db or DB_PATH
    exe = find_sqlcipher()
    if not exe:
        raise MMDBError("sqlcipher fehlt – im Terminal: brew install sqlcipher")
    if not os.path.exists(db):
        raise MMDBError("MoneyMoney-Datenbank nicht gefunden (%s)." % db)
    script = "PRAGMA key = %s;\nPRAGMA cipher_compatibility = %d;\n.bail on\n.headers off\n.mode tabs\n%s\n" % (_quote(password), compat, sql)
    try:
        r = subprocess.run([exe, "-readonly", db], input=script, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise MMDBError("sqlcipher antwortet nicht (Zeitlimit).")
    except OSError as e:
        raise MMDBError("sqlcipher nicht ausführbar: %s" % e)
    err = (r.stderr or "").strip()
    if r.returncode != 0 or err:
        low = err.lower()
        if "not a database" in low or "file is encrypted" in low:
            raise MMDBError("passwort")
        if "operation not permitted" in low or "unable to open" in low or "authorization denied" in low:
            raise MMDBError("Kein Zugriff auf die Daten von MoneyMoney: Systemeinstellungen → Datenschutz & Sicherheit → "
                            "Festplattenvollzugriff → das Programm, das Kontor ausführt (python3), erlauben.")
        msg = err[:200].replace(password, "***") if password else err[:200]
        raise MMDBError("sqlcipher: %s" % msg)
    return r.stdout


def _open(password: str) -> int:
    """Kompatibilitaetsstufe finden (SQLCipher 4, sonst 3). Falsches Passwort -> MMDBError."""
    last = None
    for compat in (4, 3):
        try:
            _run(password, "SELECT count(*) FROM sqlite_master;", compat, timeout=60)
            return compat
        except MMDBError as e:
            if str(e) != "passwort":
                raise
            last = e
    raise MMDBError("Passwort falsch (oder unbekanntes Datenbankformat).") from last


_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def schema(password: str) -> Dict:
    """Aufbau der Datenbank: Tabellen mit Spalten (aus CREATE TABLE) und Zeilenzahl -- keine Inhalte."""
    compat = _open(password)
    out = _run(password, "SELECT name, replace(replace(sql, char(10), ' '), char(9), ' ') FROM sqlite_master WHERE type IN ('table','view') ORDER BY name;", compat)
    tables: List[Tuple[str, str]] = []
    for line in out.splitlines():
        if "\t" in line:
            name, sql = line.split("\t", 1)
            tables.append((name.strip(), sql.strip()))
    names = [n for n, _ in tables if _IDENT.match(n) and not n.startswith("sqlite_")]
    counts: Dict[str, Optional[int]] = {}
    if names:
        q = "\n".join("SELECT '%s', count(*) FROM \"%s\";" % (n, n) for n in names)
        try:
            for line in _run(password, q, compat).splitlines():
                if "\t" in line:
                    n, c = line.split("\t", 1)
                    counts[n.strip()] = int(c.strip()) if c.strip().isdigit() else None
        except MMDBError:
            pass
    return {"kompatibilitaet": compat, "tabellen": [{"name": n, "sql": s, "zeilen": counts.get(n)} for n, s in tables]}


def schema_text(info: Dict) -> str:
    lines = ["MoneyMoney-Datenbank: Aufbau (keine Inhalte)", "SQLCipher-Kompatibilitaet: %s" % info["kompatibilitaet"], ""]
    for t in info["tabellen"]:
        lines.append("%s  (%s Zeilen)" % (t["name"], "?" if t["zeilen"] is None else t["zeilen"]))
        lines.append("  " + (t["sql"] or ""))
        lines.append("")
    return "\n".join(lines)
