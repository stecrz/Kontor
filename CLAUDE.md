# Kontor – Regeln für Claude

Kontor ist ein lokaler Dienst (Python, nur Standardbibliothek) mit Web-Oberfläche (`web/`), der auf den Daten von
MoneyMoney (macOS) arbeitet. Er läuft als launchd-Dienst beim Nutzer und startet sich selbst neu, sobald sich `VERSION` ändert.

## Prüfen
- Tests: `python3 -m pytest -q tests` (Browser-Tests mit Playwright; `sqlcipher` nur für Testdatenbanken)
- Oberfläche: `node --check web/app.js`

## Jede Änderung abschließen
1. Tests grün.
2. `VERSION`: dritte Stelle +1 (3.9.6 → 3.9.7) – auch bei mehreren Verbesserungen auf einmal. Zweite Stelle nur bei
   erheblichen Änderungen und nur nach Rückfrage. Erste Stelle nie.
3. `CHANGELOG.md`: neuer Abschnitt oben, kurz, auf Deutsch.
4. Commit und Push auf `main` selbst erledigen, ohne nachzufragen.
5. Ist der Mac des Nutzers verbunden: dort den Kontor-Ordner auf den neuen Stand bringen (`git fetch` + `git reset --hard`).

## Sicherheit (ohne Ausnahme)
- Öffentliches Repo: keine persönlichen Daten (Namen, Konten, IBANs, Beträge, Pfade). Testdaten frei erfunden.
- MoneyMoney nur über die AppleScript-Schnittstelle. Schreiben nur in Offline-Konten (Regeln) und – wenn der Nutzer das
  Zurückschreiben eingeschaltet hat – das Kategoriefeld von Umsätzen, die er in Kontor zuordnet (`mm_categories.py`: direkt
  vorher neu lesen und prüfen, fremde Kategorien nur nach Rückfrage, nur am Mac). Nie Buchungen, den Kategorienbaum oder
  Regeln des Nutzers ändern oder löschen, keine Überweisungen.
- Oberfläche nur über 127.0.0.1 bzw. Tailscale erreichbar. Einzige Netzverbindung: Update-Prüfung bei GitHub.
- Keine Passwörter oder Zugangsdaten speichern, protokollieren oder zwischenspeichern; Datenordner verschlüsselt.
- Kontostände aus MoneyMoney (`mm_history.py`): Datenbankdatei nur per Upload, nur im Arbeitsspeicher; Passwort nur im Swift-Helfer,
  der nur für den Vorgang erzeugt und danach gelöscht wird; Puffer danach überschreiben; keine dauerhaften Freigaben.
- Keine Kontostände schätzen. Unbekanntes als „unbekannt“ kennzeichnen.

## Sprache
- Oberfläche zweisprachig: Deutsch ist Hauptsprache (Layout auf Deutsch abstimmen), Englisch immer mit pflegen.
- Alle Texte für den Nutzer stehen in `web/i18n.js` (Schlüssel → [Deutsch, Englisch]); im Code nur `t('schluessel', …)`
  (app.js) bzw. `tr("schluessel", …)` (Python). Keine Texte fest im Code. Platzhalter `{0}` (JS) bzw. `%s` (Python).
- Texte, die nach MoneyMoney geschrieben werden (Verwendungszwecke), Kategorienamen und Datenschlüssel bleiben unübersetzt.
- Englisch: Datei- und Modulnamen, Datendateien, API-Endpunkte und URL-Parameter, Kommandozeilenbefehle, Protokollmeldungen.
- Präfix `mm_` nur für Teile, die direkt mit MoneyMoney sprechen.

## Oberfläche
- Texte auf Deutsch, kurz, ohne Fachbegriffe, Einzahl/Mehrzahl korrekt.
- Konten in der Reihenfolge von MoneyMoney.
- Hinweise für den Nutzer im Chat, nicht als Dateien im Repo.
