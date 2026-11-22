# log — Protokoll
Kontor's log file kontor.log as plain text: what the service did – syncs and readings from MoneyMoney with their duration,
changes of settings, bookings, update steps, the assistant's lookups (only that one happened), warnings and errors. It never holds
passwords, IBANs, balances, amounts or search words. Reached from Einstellungen and the help; the assistant does not read it.

## log.tools — Anzeige und Diagnose
"Alles" (also details, level DEBUG), "Hinweise" (default: INFO and above) or "Warnungen & Fehler" choose which lines are shown;
"Aktualisieren" reads the file again. "Diagnosedatei (maskiert)" downloads status, configuration, the last run and the last 400 log
lines, account and area names replaced by Konto01, Bereich0 … (and a loan's counter IBAN); "Diagnosedatei (mit Kontonamen)" keeps
the names. Neither holds balances or passwords. "Im Finder zeigen" (only at the Mac) shows the file.

## log.file — Datei
Where the file lies (Kontor's data folder, kontor.log): one file of at most 2 MB – when it grows past that, the oldest entries are
dropped. Beside it service.err.log for crashes of the service. How to reach the folder when the interface does not open.

## log.lines — Protokollzeilen
The newest 2,000 lines of the file, oldest first. Each line: date and time (Mac's local time, "2026-11-22 14:03:12"), level
(DEBUG, INFO, WARNING, ERROR), the part of Kontor that wrote it, the message (English). Warnings amber, errors red and bold,
details muted; lines of an error's traceback keep its level. "Noch keine Einträge." / "Nichts zu zeigen – keine Warnungen oder
Fehler." when nothing matches.
