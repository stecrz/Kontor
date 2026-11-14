# Kontor – Regeln für Claude

Kontor ist ein lokaler Dienst (Python ≥ 3.9, nur Standardbibliothek) mit Web-Oberfläche (`web/`), der auf den Daten von
MoneyMoney (macOS) arbeitet. Er läuft als launchd-Dienst beim Nutzer und startet sich selbst neu, sobald sich `VERSION` ändert.
Der Nutzer will Ergebnisse, keine Zwischenstände: selbstständig arbeiten, fragen nur bei echten Produktentscheidungen.

## Arbeitsweise
- Was als Nächstes kommt und wann es fertig ist: `ROADMAP.md`. Erledigtes dort abhaken, Neues dort eintragen.
- Skills (`.claude/skills/`): `feature` (Punkt aus dem Fahrplan umsetzen), `ui-check` (Oberfläche ansehen), `release` (jede
  Änderung abschließen). Unabhängige Prüfung vor jedem Release mit Rechenlogik oder Schreibzugriff: Agent `reviewer`.
- Leitplanken (`.claude/settings.json`): Sperren für Kontors Datenordner, MoneyMoneys Datenbank, Überweisungen und
  Force-Push; Erinnerung, wenn eine Änderung nicht abgeschlossen ist.
- GitHub Actions testet jeden Push (Python 3.9 und neu) und nachts mit 1000 Zufallsläufen.

## Prüfen
- Tests: `python3 -m pytest -q tests` (~2½ min; Browser-Tests mit Playwright; `sqlcipher` nur für Testdatenbanken).
  Mehr Zufallsläufe: `KONTOR_FUZZ_SEEDS=400 python3 -m pytest -q tests/test_fuzz.py`.
- Oberfläche: `node --check web/app.js`; ansehen mit `python3 tests/preview.py <ordner> '#route'` (hell/dunkel, Mac/iPhone; `--js` z. B. für ganze Tabellen).

## Jede Änderung abschließen (Skill `release`)
1. Tests grün.
2. `VERSION`: dritte Stelle +1 (3.9.6 → 3.9.7) – auch bei mehreren Verbesserungen auf einmal. Zweite Stelle nur bei
   erheblichen Änderungen und nur nach Rückfrage. Erste Stelle nie.
3. `CHANGELOG.md`: neuer Abschnitt oben, Überschrift `## X.Y.Z (JJJJ-MM-TT HH:MM)` (Ortszeit des Nutzers, Europe/Berlin), kurz, auf Deutsch.
4. Commit und Push auf `main` selbst erledigen, ohne nachzufragen. Keine Tags.
5. Ist der Mac des Nutzers verbunden: dort den Kontor-Ordner auf den neuen Stand bringen (`git fetch` + `git reset --hard`).

## Sicherheit (ohne Ausnahme)
- Öffentliches Repo: keine persönlichen Daten (Namen, Konten, IBANs, Beträge, Pfade). Testdaten frei erfunden
  (`tests/test_privacy.py` prüft, was sich prüfen lässt).
- MoneyMoney nur über die AppleScript-Schnittstelle. Schreiben nur in Offline-Konten (Regeln) und – wenn der Nutzer das
  Zurückschreiben eingeschaltet hat – das Kategoriefeld von Umsätzen, die er in Kontor zuordnet (`mm_categories.py`: direkt
  vorher neu lesen und prüfen, fremde Kategorien nur nach Rückfrage, nur am Mac). Nie Buchungen, den Kategorienbaum oder
  Regeln des Nutzers ändern oder löschen, keine Überweisungen.
- Oberfläche nur über 127.0.0.1 bzw. Tailscale erreichbar. Netzverbindungen nur: Update-Prüfung bei GitHub und – nur auf ausdrücklichen Klick (Einrichtung → Historische Kontostände) – das Nachschlagen von Wertpapiernamen bei OpenFIGI (`security_names.py`, sendet nur ISINs).
- Keine Passwörter oder Zugangsdaten speichern, protokollieren oder zwischenspeichern; Datenordner verschlüsselt.
- Kontostände aus MoneyMoney (`mm_history.py`): Datenbankdatei nur per Upload, nur im Arbeitsspeicher; Passwort nur im Swift-Helfer,
  der nur für den Vorgang erzeugt und danach gelöscht wird; Puffer danach überschreiben; keine dauerhaften Freigaben.
- Keine Kontostände schätzen. Unbekanntes als „unbekannt“ kennzeichnen.
- Kontors Datenordner und MoneyMoneys Daten am Mac nie ohne ausdrückliche Erlaubnis des Nutzers öffnen.

## Sprache
- Oberfläche zweisprachig: Deutsch ist Hauptsprache (Layout auf Deutsch abstimmen), Englisch immer mit pflegen.
- Alle Texte für den Nutzer stehen in `web/i18n.js` (Schlüssel → [Deutsch, Englisch]); im Code nur `t('schluessel', …)`
  (app.js) bzw. `tr("schluessel", …)` (Python). Keine Texte fest im Code. Platzhalter `{0}` (JS) bzw. `%s` (Python).
- Texte, die nach MoneyMoney geschrieben werden (Verwendungszwecke), Kategorienamen und Datenschlüssel bleiben unübersetzt.
- Englisch: Datei- und Modulnamen, Datendateien, API-Endpunkte, URL-Pfade und -Parameter (auch die #-Adressen der Oberfläche und die Anker der Hilfe), Kommandozeilenbefehle, Protokollmeldungen, Code-Kommentare. Deutsch ist nur der Text, den der Nutzer liest.
- Hilfe: `docs/help.de.md` und `docs/help.en.md` gemeinsam pflegen (gleiche Anker); Bilder mit `tests/screenshots.py` (de/en) aus erfundenen Daten erzeugen.
- Präfix `mm_` nur für Teile, die direkt mit MoneyMoney sprechen.

## Oberfläche
- Gestaltung und Bedienung nach Apples Human Interface Guidelines (macOS und iOS): klare Hierarchie, bekannte Bedienmuster und Tastaturkürzel, ruhige Typografie, Hell- und Dunkelmodus.
- Zielgeräte: 14-Zoll-MacBook (Safari, Fenster fast im Vollbild) und iPhone; im Dunkelmodus gut lesbar (keine Pastelltöne).
- Texte auf Deutsch, kurz, ohne Fachbegriffe, Einzahl/Mehrzahl korrekt. Keine überflüssigen Erklärtexte: was Tooltip oder Hilfe sagt, steht nicht noch einmal auf der Seite.
- Konten in der Reihenfolge von MoneyMoney.
- Hinweise für den Nutzer im Chat, nicht als Dateien im Repo.

## Aufbau
| Teil | Aufgabe |
|---|---|
| `kontor.py` | Kommandozeile (start, run, …) |
| `service.py` | Dienst: HTTP-API, statische Dateien, Zeitplan, Bericht im Hintergrund |
| `core.py` | Lesen aus MoneyMoney (schnell/voll), Einstellungen (`merged_config`, `check_config`), Lauf (`run_once`), Bericht, Pakete |
| `rules.py` | Buchungsregeln – Darlehen, Beteiligung, Kontenspiegel; zustandslos, erkennt Gebuchtes an `#kontor-…` |
| `model.py` | Konten, Umsätze, `Ledger`, Salden zum Stichtag, Markierungen |
| `report.py` | Bilanz, Cashflow, Planung je Bereich |
| `categorize.py` / `mm_categories.py` | Kontor-Kategorien (lernen, zuordnen) / Kategorie nach MoneyMoney zurückschreiben |
| `mm_bridge.py` + `.jxa` | einzige Schnittstelle zu MoneyMoney (Liste erlaubter Methoden) |
| `mm_history.py` + `.swift` | Kontostände aus MoneyMoneys Datenbank (Upload, nur Speicher) |
| `realestate.py`, `tax.py`, `receipts.py` | Immobilienkalkulation, Steuer, Belege |
| `storage.py`, `auth.py`, `updates.py`, `tls_cert.py` | verschlüsselte Ablage, Anmeldung/Touch ID, Updates, Zertifikat |
| `web/app.js`, `web/i18n.js` | Oberfläche (eine Datei, Seiten über `#…`), Texte |
| `tests/` | `fixtures.py` (erfundene Daten), `test_rules`, `test_cashflow` (Abstimmung je Monat, Zufallsläufe), `test_e2e` (simuliertes MoneyMoney, HTTP, Browser), `test_fuzz`, `test_privacy` |
