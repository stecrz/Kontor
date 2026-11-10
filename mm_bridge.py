"""MoneyMoney-Anbindung ueber die offizielle Skript-Schnittstelle (osascript/JXA).

Einzige Stelle, die mit MoneyMoney spricht. Alles andere arbeitet auf den
hier gelieferten Python-Objekten (siehe model.py).

Eigenschaften:
  * startet MoneyMoney nie selbst (pgrep-Pruefung vor jedem Aufruf)
  * erkennt gesperrte Datenbank und fehlende Automations-Berechtigung
  * jeder Aufruf mit Zeitlimit (ein offener Dialog in MoneyMoney blockiert sonst)
  * Probelauf: Schreibbefehle werden nur protokolliert
  * Datumsfelder: MoneyMoney exportiert lokale Mitternacht als UTC-Zeitpunkt;
    hier wird in lokale Zeit zurueckgerechnet, sonst rutscht das Datum um
    einen Tag (CET/CEST).
"""
from __future__ import annotations

import json
import logging
import os
import plistlib
import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from i18n import tr

log = logging.getLogger("kontor.bridge")

HERE = os.path.dirname(os.path.abspath(__file__))
JXA_FILE = os.path.join(HERE, "mm_bridge.jxa")
TIMEOUT_SECONDS = 120

# Einzige Befehle, die an MoneyMoney gehen. Ueberweisungen/Lastschriften
# (createBankTransfer, createDirectDebit) sind hier UND in mm_bridge.jxa gesperrt.
ALLOWED_METHODS = frozenset(["exportAccounts", "exportCategories", "exportTransactions",
                             "exportPortfolio", "addTransaction", "setTransaction"])


class MoneyMoneyError(Exception):
    """Allgemeiner Fehler der Skript-Schnittstelle."""


class MoneyMoneyNotRunning(MoneyMoneyError):
    pass


class MoneyMoneyLocked(MoneyMoneyError):
    pass


class MoneyMoneyNotPermitted(MoneyMoneyError):
    pass


class MoneyMoneyTimeout(MoneyMoneyError):
    """No answer in time: for a write it is unknown whether MoneyMoney carried it out -- never tried again blindly."""


def is_running() -> bool:
    try:
        r = subprocess.run(["pgrep", "-x", "MoneyMoney"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:  # pragma: no cover - pgrep fehlt nur auf Nicht-macOS
        return False


def local_date(value: Any) -> Optional[date]:
    """plist-Datum (naiv, UTC) -> lokales Datum."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone().date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def local_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone()
    return None


class Bridge:
    def __init__(self, dry_run: bool = True, timeout: int = TIMEOUT_SECONDS):
        self.dry_run = dry_run
        self.timeout = timeout
        self.written: List[Dict[str, Any]] = []   # im Probelauf: was geschrieben worden waere

    # -- Low level ---------------------------------------------------------

    def _call(self, method: str, args: Optional[Dict[str, Any]]) -> str:
        if method not in ALLOWED_METHODS:
            raise MoneyMoneyError(tr("s_befehl_nicht_erlaubt_s") % method)
        if not is_running():
            raise MoneyMoneyNotRunning(tr("s_moneymoney_laeuft_nicht"))
        payload = json.dumps({"method": method, "args": args}, ensure_ascii=False)
        t0 = time.time()
        log.debug("MoneyMoney %s (%s)", method, ", ".join(sorted(args or {})))      # only the names of the arguments: no amounts, payees or texts
        try:
            r = subprocess.run(
                ["osascript", "-l", "JavaScript", JXA_FILE, payload],
                capture_output=True, text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            log.error("MoneyMoney %s: timeout of %ds exceeded", method, self.timeout)
            raise MoneyMoneyTimeout(
                tr("s_moneymoney_antwortet_nicht_zeitlimit_d") % self.timeout)
        log.debug("MoneyMoney %s: status %d, %d chars, %.1f s", method, r.returncode, len(r.stdout or ""), time.time() - t0)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            log.warning("MoneyMoney %s failed: %s", method, err[:500])
            low = err.lower()
            if "-1743" in err or "not permitted" in low or "nicht erlaubt" in low or "nicht berechtigt" in low:
                raise MoneyMoneyNotPermitted(
                    tr("s_keine_berechtigung_moneymoney_zu_steue_2") + err)
            if "locked" in low or "gesperrt" in low or "verschl" in low or "password" in low or "passwort" in low:
                raise MoneyMoneyLocked(tr("s_moneymoney_datenbank_ist_gesperrt_orig") + err)
            if "-600" in err or "-10810" in err:
                raise MoneyMoneyNotRunning(tr("s_moneymoney_nicht_erreichbar_original") + err)
            raise MoneyMoneyError(tr("s_moneymoney_fehler_bei_s_s") % (method, err))
        return r.stdout

    @staticmethod
    def _plist(text: str) -> Any:
        text = text.strip()
        if not text:
            raise MoneyMoneyError(tr("s_leere_antwort_von_moneymoney"))
        try:
            return plistlib.loads(text.encode("utf-8"))
        except Exception as e:
            raise MoneyMoneyError(tr("s_antwort_ist_keine_property_list") % e)

    # -- Lesen -------------------------------------------------------------

    def export_accounts(self) -> List[Dict[str, Any]]:
        try:
            raw = self._plist(self._call("exportAccounts", None))
        except (MoneyMoneyNotRunning, MoneyMoneyLocked, MoneyMoneyNotPermitted):
            raise                       # not reachable: asking again in another form changes nothing
        except MoneyMoneyError:
            raw = self._plist(self._call("exportAccounts", {"as": "plist"}))
        if not isinstance(raw, list):
            raise MoneyMoneyError(tr("s_kontenexport_hat_unerwartetes_format"))
        return raw

    def export_categories(self) -> List[Dict[str, Any]]:
        try:
            raw = self._plist(self._call("exportCategories", None))
        except (MoneyMoneyNotRunning, MoneyMoneyLocked, MoneyMoneyNotPermitted):
            raise
        except MoneyMoneyError:
            raw = self._plist(self._call("exportCategories", {"as": "plist"}))
        return raw if isinstance(raw, list) else []

    def export_transactions(self, from_date: date, to_date: Optional[date] = None,
                            account: Optional[str] = None) -> List[Dict[str, Any]]:
        args: Dict[str, Any] = {"fromDate": from_date.isoformat(), "as": "plist"}
        if to_date is not None:
            args["toDate"] = to_date.isoformat()
        if account:
            args["fromAccount"] = account
        raw = self._plist(self._call("exportTransactions", args))
        if isinstance(raw, dict):
            raw = raw.get("transactions", [])
        if not isinstance(raw, list):
            raise MoneyMoneyError(tr("s_umsatzexport_hat_unerwartetes_format"))
        return raw

    def export_portfolio(self, account: str) -> List[Dict[str, Any]]:
        raw = self._plist(self._call("exportPortfolio", {"fromAccount": account, "as": "plist"}))
        if isinstance(raw, dict):
            raw = raw.get("portfolio", raw.get("securities", []))
        return raw if isinstance(raw, list) else []

    # -- Schreiben (nur manuelle Konten) ---------------------------------

    def add_transaction(self, account_ref: str, booking_date: date, payee: str,
                        amount: float, purpose: str = "", category: Optional[str] = None) -> None:
        """A new booking in an offline account, addressed by its UUID only -- never by a name (two accounts may carry the same
        one), and one attempt only: after an error or a timeout it is not tried again in another form (it may have been
        carried out). MoneyMoney itself accepts this only for offline accounts."""
        args: Dict[str, Any] = {
            "toAccount": account_ref,
            "onDate": booking_date.isoformat(),
            "to": payee,
            "amount": round(float(amount), 2),
        }
        if purpose:
            args["purpose"] = purpose
        if category:
            args["category"] = category
        if self.dry_run:
            log.info("DRY RUN addTransaction (%s)", ", ".join(sorted(args)))      # no amount, payee or purpose in the log
            self.written.append({"method": "addTransaction", "args": args})
            return
        try:
            self._call("addTransaction", args)
        except (MoneyMoneyNotRunning, MoneyMoneyLocked, MoneyMoneyNotPermitted, MoneyMoneyTimeout):
            raise
        except MoneyMoneyError as e:
            raise MoneyMoneyError(tr("s_buchung_konnte_nicht_angelegt_werden") % e)
        self.written.append({"method": "addTransaction", "args": dict(args)})

    def set_transaction(self, tx_id: int, category: Optional[str] = None,
                        comment: Optional[str] = None, checkmark: Optional[bool] = None) -> None:
        args: Dict[str, Any] = {"id": int(tx_id)}
        if category is not None:
            args["categoryTo"] = category
        if comment is not None:
            args["commentTo"] = comment
        if checkmark is not None:
            args["checkmarkTo"] = "on" if checkmark else "off"
        if len(args) == 1:
            return
        if self.dry_run:
            log.info("DRY RUN setTransaction %s", json.dumps(args, ensure_ascii=False))
            self.written.append({"method": "setTransaction", "args": args})
            return
        self._call("setTransaction", args)
        self.written.append({"method": "setTransaction", "args": args})

    def append_comment(self, tx_id: int, account: str, day: date, text: str) -> bool:
        """Add a note to a transaction's comment without losing what is there: read just before (only this account, around that
        day), keep the comment and add the text. Nothing if the text is there already or the transaction is not found."""
        rows = self.export_transactions(day - timedelta(days=7), day + timedelta(days=7), account=account)
        r = next((x for x in rows if int(x.get("id") or 0) == int(tx_id) and str(x.get("accountUuid") or account) == account), None)
        if r is None:
            return False
        cur = str(r.get("comment") or "")
        if text in cur:
            return False
        self.set_transaction(tx_id, comment=(cur + "\n" if cur.strip() else "") + text)
        return True


def restrict_permissions(path: str) -> None:
    """Dateien/Ordner nur fuer den eigenen Benutzer lesbar (0600/0700)."""
    try:
        os.chmod(path, 0o700 if os.path.isdir(path) else 0o600)
    except OSError:
        pass
