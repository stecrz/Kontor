# Kontor

Bilanz, Cashflow, Planung und Steuerübersicht auf Basis von [MoneyMoney](https://moneymoney-app.com) (macOS) – für dich privat und für jede Gesellschaft getrennt. Ein kleiner Dienst, der dauerhaft auf dem Mac läuft, mit einer Web-Oberfläche unter `http://127.0.0.1:8765/`. Nur Bordmittel (Python 3, `openssl`, `security`, `osascript`), keine Fremdbibliotheken, keine Zugangsdaten außerhalb von MoneyMoney, keine Netzverbindung außer der abschaltbaren Update-Prüfung bei GitHub (und, nur auf Klick, dem Nachschlagen von Wertpapiernamen per ISIN). Kontor enthält keine Annahmen über deine Konten: Alles wird in der Oberfläche eingerichtet.

![Übersicht](docs/img/de/overview.png)

**Stand:** Bilanz, Synchronisierung und Einrichtung sind geprüft. Die übrigen Seiten (Übersicht, Cashflow, Planung, Immobilien, Steuer, Umsätze & Belege, Kategorien, Buchungen, Regeln) sind nutzbar, aber noch als „Alpha“ markiert – Zahlen dort bitte gegenprüfen.

**Anleitung: [Hilfe](docs/help.de.md)** · English: [help](docs/help.en.md) – dieselbe Hilfe steht in Kontor unter „Hilfe“ (durchsuchbar). Dort steht alles Weitere: was MoneyMoney und was Kontor macht, die Einrichtung, jede Seite, [Sicherheit](docs/help.de.md#security), Kommandozeile und Datenordner, Hilfe bei Fehlern. Alle Bilder zeigen frei erfundene Daten.

| | |
|:---:|:---:|
| ![Bilanz](docs/img/de/balance_sheet.png)<br>[Bilanz](docs/help.de.md#balance-sheet) | ![Cashflow](docs/img/de/cash_flow.png)<br>[Cashflow](docs/help.de.md#cash-flow) |
| ![Planung](docs/img/de/planning.png)<br>[Planung](docs/help.de.md#planning) | ![Immobilien](docs/img/de/property.png)<br>[Immobilien](docs/help.de.md#properties) |
| ![Kategorien zuordnen](docs/img/de/assign_categories.png)<br>[Kategorien](docs/help.de.md#categories) | ![Einrichtung](docs/img/de/setup.png)<br>[Einrichtung](docs/help.de.md#setup) |
| ![Zugriff vom iPhone](docs/img/de/access.png)<br>[Zugriff vom iPhone](docs/help.de.md#iphone) | <img src="docs/img/de/iphone.png" alt="Kontor auf dem iPhone" width="220"><br>[Auf dem iPhone](docs/help.de.md#iphone) |

## Installation

Voraussetzungen: macOS, MoneyMoney, Kommandozeilen-Werkzeuge von Apple (`xcode-select --install`, liefert `python3` und `swiftc`).

1. Eine Zeile im Terminal (Programme → Dienstprogramme → Terminal), lädt nach `~/Kontor` und richtet alles ein:
   ```
   bash <(curl -fsSL https://raw.githubusercontent.com/stecrz/Kontor/main/get.sh)
   ```
   Dieselbe Zeile aktualisiert später auf den neuesten Stand. Alternativ von Hand: `git clone https://github.com/stecrz/Kontor.git ~/Kontor && cd ~/Kontor && bash install.sh`. (Ein ZIP aus dem Browser geht auch, aber Gatekeeper blockiert dann Skripte per Doppelklick; `bash install.sh` im entpackten Ordner entfernt die Sperre. Ein echter Doppelklick-Installer bräuchte eine Apple-Entwicklersignatur.)
2. Der Browser öffnet `http://127.0.0.1:8765/`: Passwort festlegen, dann führt die [Einrichtung](docs/help.de.md#setup) Schritt für Schritt durch alles.

Aktualisieren, neu einrichten und entfernen: [Updates](docs/help.de.md#updates) und [Für Fortgeschrittene](docs/help.de.md#advanced).

## Entwicklung

- Tests: `python3 -m pytest -q tests` – Regeln und Zinsmodelle, Verschlüsselung, Lauf gegen ein simuliertes MoneyMoney, HTTP-API, Immobilienkalkulation gegen eine handgerechnete Tabellenkalkulation (auf den Cent) und die Oberfläche im Browser (Playwright). Testdaten sind frei erfunden.
- Bilder für Hilfe und README: `python3 tests/screenshots.py [Ordner|-] [de|en]` (aus denselben erfundenen Daten).
- Regeln für Änderungen (Version, Sprache, Sicherheit): [CLAUDE.md](CLAUDE.md). Änderungen: [CHANGELOG.md](CHANGELOG.md).

Lizenz: CC0. Keine Gewähr, keine Steuer- oder Anlageberatung.
