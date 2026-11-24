# Tests – was welche Datei prüft

Teil von `CLAUDE.md` (Aufbau). Neue Testdatei oder neuer Prüfbereich: hier eintragen.

## Wo was läuft
- **GitHub, jeder Push** (`.github/workflows/tests.yml`, rund 10 min, für kleine und große Versionen gleich): Linux mit Kontors
  eigenem Python, Chrome und Safari-Engine, Code-Checks, in vier Teilen nebeneinander (Seiten = `tests/test_e2e.py`; Assistent und
  Rundgang; Rechnen mit Zufallsfällen – je Push 12 feste; alles andere – eine neue Testdatei landet dort von selbst), dazu Python 3.9
  nur für den Starter (`tests/test_python.py`); `--durations` nennt die langsamsten Tests. macOS: Apples Python, Swift-Helfer,
  Mac-App (bauen, Kontor darin laden, Mikrofon ohne Nachfrage; jede Seite in macOS' WebKit mit echtem Rechtsklick), Abschirmung der
  Modelle (`tests/test_mac_model.py`: kein Netz außer der eigenen Socket-Datei; echtes llama.cpp), MoneyMoney-Brücke, Installation,
  Kontors eigenes Python (`tests/mac_python.py`: echt laden, falsche Prüfsumme, Quarantäne und Signatur, Selbsttest, Helfer in der
  Sandbox, Dienst als Kind des Starters, Neustart durch launchd, beschädigt → Apples Python, Deinstallieren, Update von der Version
  davor); Linux prüft denselben Ablauf mit dem echten Build für Linux.
- **GitHub, nachts** (`nightly.yml`): auf dem neuesten `main` die 1000 festen und so viele neue Zufallsfälle, wie in ~3 h passen,
  auf mehreren Rechnern nebeneinander; dazu Klickpfade durch die Oberfläche (`tests/test_clickpaths.py`, 40 feste und neue, in
  Chromium und der Safari-Engine) – je Push laufen davon 3 feste mit (im Teil „Übrige“).
- **Lokal** (`.claude/tools/release.py`, Skill `release`): Code-Checks, betroffene Tests (`tests/affected.py`) ohne Browser, bei
  Rechenlogik 400 Zufallsfälle, Starter mit Python 3.9, dazu die mit `--tests` genannten (mit Browser). Alles lokal
  (`python3 -m pytest -q tests`, ~30 min) nur, wenn es wirklich nötig ist – GitHub macht es ohnehin.
- Zufallsfälle von Hand: `KONTOR_FUZZ_SEEDS=400 python3 -m pytest -q tests/test_fuzz.py` (feste Fälle 0–399), dazu neue:
  `KONTOR_FUZZ_RANDOM=<Anzahl>` oder `KONTOR_FUZZ_MINUTES=<Minuten>`; einen Fall aus einer Fehlermeldung („seed …“) wiederholen:
  `KONTOR_FUZZ_SEED=<Nummer>`. `pytest -rs` nennt Übersprungenes.

## Dateien

- `fixtures.py` (erfundene Daten)
- `test_rules`, `test_cashflow` (Abstimmung je Monat, Zufallsläufe)
- `test_scenarios` (Lebensfälle über Bereiche: Einlagen, Kauf, Darlehen, Auslagen; Monats-/Jahreswechsel, gemischt)
- `test_worlds` (Zufallswelten: 1–3 Privatpersonen, bis 4 Firmen, Beteiligungen untereinander, Darlehen, PayPal, Miete, Überweisungen zwischen allen – alles geht auf, nichts bleibt unklar; Zeitraum zehn Tage bis vier Jahre mit Ende 2023–2027, je Bereich ruhig, ein Jahr ohne Buchung, konstant, stark schwankend, ein Schub von Hunderten Buchungen, saisonal, Konten, die mitten im Zeitraum beginnen oder enden – ähnlich in `test_rule_worlds` und `test_cashflow`; dazu feste Sonderfälle an jeder Art Tag zwischen jeder Art Bereich)
- `test_rule_worlds` (Zufallswelten für die Buchungsregeln: Beteiligung täglich/monatlich, Darlehen mit beiden Zinsmodellen, Zinswechsel, Buchungstag, Kontenspiegel – am Ende jeder Cent nachgerechnet, nichts zu viel; dazu Änderungen in MoneyMoney zwischen den Läufen)
- `test_categories`, `test_e2e` (simuliertes MoneyMoney, HTTP, Browser; Browser-Tests warten auf einen Zustand – `until`, nach dem
  Speichern `stored` (steht es in der Ablage), vor Eingaben in eine Seite, die gleich neu lädt, `quiet` –, nie eine feste Zeit)
- `test_assistant` (mit `fake_llama.py` statt llama.cpp, Downloads ohne Netz)
- `test_assistant_eval` (Prüfsatz `assistant_eval/`: 73 Aufgaben durch den Assistenten auf der Demo-Welt – jede Musterlösung besteht, keine falsche Antwort; mit echtem Modell nur am Mac, README dort; ändert sich ein Werkzeug oder die Demo-Welt, Aufgaben in `tasks.json` mitziehen)
- `test_tables` (Excel lesen: Werte wie in Excel, Ausschnitte, Summen; abgelehnt: alte/geschützte Dateien, Entitäten, Grenzen, Teile außerhalb; CSV: Trennzeichen, Kodierung, Schreibweise je Spalte, Grenzen; Prüfproben: Summen, Überträge, Soll/Haben, SUMME-Formeln, eine verlesene Zahl, eine verlorene Zeile; Zeilen suchen)
- `test_pdf_tables` (Tabellen aus PDFs/Bildern: erfundene Auswertungen über mehrere Seiten, Spalten, Zahlen, Köpfe, schiefe Scans, jeder Fall stiller Falschzahlen aus der Prüfung und aus dem Messen Zelle für Zelle; ein Wertenachweis über 30 Seiten – jede Zeile einmal, jede Spalte, jedes Vorzeichen, keine Zahl, die das Dokument nicht nennt; Zufallstabellen Zelle für Zelle gegen das Gedruckte; `OnMac` läuft im macOS-Job mit dem echten Helfer)
- `test_web` (Internetsuche ohne Netz: Freigabe, Filter, Hosts, Grenzen, eingeschleuste Befehle; Claude: Karte mit dem ganzen Wortlaut, nie ohne Klick, Filter auf die ganze Frage, Tagesgrenze, Fehlerantworten, Schlüssel nirgends)
- `test_tour` (Rundgang: jede Seite samt Unterseiten und Reitern hell/dunkel, Mac/iPhone, de/en – Skriptfehler, Überlaufen, Textschlüssel, Kontrast; erklärt (`EXPLAINED`, auch in den Seitenfenstern): jedes Bedienelement mit Tooltip oder „?“ – eigenem, dem seines Feldes, seiner Spalte oder seiner Gruppe (Zeile, Leiste, Überschrift, Karte, beschriebene Stelle) –, jede sichtbare Zahl in einer in `docs/ui` beschriebenen Stelle)
- `test_clickpaths` (Klickpfade: Seiten, Dialoge, Seitenfenster und Bezüge – Rechtsklick, „Im Chat fragen“, zurück per Klick – in
  wechselnder Reihenfolge, hell/dunkel, Mac/iPhone, Chromium/WebKit, auf wechselnden Welten: Testwelt, Demo, Zufallswelt aus
  `test_worlds`, leeres Kontor; nach jedem Schritt kein Skriptfehler, keine waagrechte Scrollleiste, nichts überlappt, nichts
  abgeschnitten, Aufgehendes im Fenster; Esc, Enter und ⌘S wirken; Zustände bleiben beim erneuten Öffnen von Seite und
  Seitenfenster. Ein Fehler nennt Fall, Ansicht und jeden Schritt: `KONTOR_FUZZ_SEED=<Nummer>`; je Push 3 feste
  (`KONTOR_CLICK_SEEDS`), nachts so viele, wie passen; Gefundenes nach der Korrektur in `FOUND_CLICKS`. Den Weg eines
  bestandenen Falls zeigt `KONTOR_CLICK_LOG=1` mit `-s`; was sie fanden, hält `FoundTest` fest: Menü am iPhone mit esc und
  Tipp auf die offene Seite, über der Assistenten-Seite, Demo ohne Wertpapiersuche)
- `test_findable` (auffindbar: je Abschnitt der Hilfe Suchwörter, wie der Nutzer sie sagt, in `tests/search_words.json` – die Suche der Hilfe-Seite (unter den ersten drei, springt zum besten) und `search_help` (unter den vier Treffern) finden ihn; jeder Abschnitt und Anker der Hilfe ist Ziel eines „?“ oder Links aus Kontor; beide Suchen falten gleich (Füllwörter aus `memory.STOP`, Endungen). Fehlt ein Treffer: das Wort des Nutzers in den Abschnitt schreiben, nicht die Suche verbiegen; neuer Abschnitt der Hilfe: dort zwei, drei Suchwörter eintragen)
- `test_fuzz`, `test_privacy`, `test_security` (Sperre, Datenschlüssel, Belegordner; `NothingGoesOut`: welche Teile ins Netz können, zu welchen Hosts, welche Programme sie starten – ein neuer Weg nach außen wird dort eingetragen)
- `test_update_guard` (Prüfung vor dem Update: untergeschobene Änderungen werden gefunden, gewöhnliche nicht; Einstufung – Untergeschobenes bleibt kritisch, Geändertes an bestehenden Wegen und der Filter der Internetsuche zu prüfen, nachweislich Strengeres ohne Freigabe; Erklärung und Zeilen je Eintrag; Warten und Freigabe, Archiv und Git-Klon)
- `test_hooks` (Lagebild, Push-Sperre und Lese-Sperre für große Dateien, `release.py` auf Wegwerf-Repositories: ein Commit je Version, schnellerer Chat, Konflikt mit der fremden Version benannt, bewusst geänderte Zeilen dürfen, beim Konflikt verlorene fremde Zeilen sperren, rote Prüfung; `git reset` auf einen fremden Stand gesperrt)
- `test_workflows` (Workflow-Dateien: kein Schlüssel doppelt – sonst startet GitHub gar keinen Lauf, wie nach 3.17.21)
- `test_passkeys` (Zugang vom iPhone: CBOR/COSE/DER streng, ECDSA mit RFC-6979-Vektoren, Registrierung und Anmeldung mit einem Software-Passkey samt allen Fehlfällen, Link und Herausforderungen, QR-Code; über HTTP Hinzufügen, Face-ID-Anmeldung, jede Änderung nur bestätigt und nur für genau diese Anfrage, jede POST-Anfrage, `MAC_ONLY`, Entfernen beendet Sitzungen, nach Neustart, Demo, Zurücksetzen)
- `affected.py` (kein Test): nennt die Testdateien, die eine Änderung betrifft – für den lokalen Lauf vor dem Push
- `test_memory` (beschädigte Datei, Steckbrief in seiner Grenze, Suche und Passendes zur Frage in ihren Grenzen, Suche in gespeicherten Verläufen (`Talks`), kein Werkzeug schreibt, Vergessenes auch aus dem Protokoll und der Unterhaltung, Sicherung, Export und Import (`Carried`: hin und zurück, jede Notiz geprüft, ganz oder gar nicht, Doppelte, Listen von anderswo, fremde und beschädigte Dateien, Grenzen), nur am Mac, nie in der Demo, Liste im Browser)
