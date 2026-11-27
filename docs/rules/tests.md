# Tests – was welche Datei prüft

Teil von `CLAUDE.md` (Aufbau). Neue Testdatei oder neuer Prüfbereich: hier eintragen.

## Wo was läuft
Zwei Arten auf GitHub, je ein Workflow (Nutzer, 2026-11-27: schlank, nichts verloren): `tests.yml` je Version in wenigen Minuten,
`nightly.yml` jede Nacht (GitHubs Zeitplan, 3:05 deutscher Zeit) stundenlang mit vielen Zufallsfällen. `test_workflows` hält beide fest (`PushJobs`, `NightJobs`, `Night`).
- **GitHub, jeder Push** (`.github/workflows/tests.yml`, rund 9 min, für kleine und große Versionen gleich): Linux mit Kontors
  eigenem Python, Chrome und Safari-Engine, in sechs Teilen nebeneinander – Seiten (`test_e2e`); Rundgang (`test_tour`);
  Datenwelten und Rechnen mit je Push 12 festen Zufallsfällen; Assistent und Gedächtnis; Updates, eigenes Python, PDF-Tabellen;
  Übrige mit Code-Checks (eine neue Testdatei landet dort von selbst; `PushJobs`: jede Datei genau einmal, die Klickpfade nur
  nachts) –, dazu Python 3.9 nur für den Starter (`tests/test_python.py`); `--durations` nennt die langsamsten Tests. macOS:
  Apples Python, Swift-Helfer, Mac-App (bauen, Kontor darin laden, Mikrofon ohne Nachfrage; jede Seite in macOS' WebKit mit echtem
  Rechtsklick), Abschirmung der Modelle (`tests/test_mac_model.py`: kein Netz außer der eigenen Socket-Datei; echtes llama.cpp),
  MoneyMoney-Brücke, Installation, Kontors eigenes Python (`tests/mac_python.py`: echt laden, falsche Prüfsumme, Quarantäne und
  Signatur, Selbsttest, Helfer in der Sandbox, Dienst als Kind des Starters, Neustart durch launchd, beschädigt → Apples Python,
  Deinstallieren, Update von der Version davor); Linux prüft denselben Ablauf mit dem echten Build für Linux.
- **GitHub, nachts** (`.github/workflows/nightly.yml` „Nachtlauf“, GitHubs eigener Zeitplan: 3:05 Europe/Berlin, Sommer wie
  Winter; Nutzer, 2026-11-27: Uhrzeit dort einstellen, kein eigener Wecker). GitHub stellt den Lauf um 3:05 in die Warteschlange,
  startet ihn unter Last aber später oder lässt ihn aus (hier bis zu 9 h, Nov. 2026) – daran ändert keine Einstellung etwas; das
  ist hingenommen. Fehlt eine Nacht (über 36 h kein Lauf), meldet es das Lagebild („Nachtlauf fehlt“). `test_workflows.Night`
  hält Zeitplan, Zeitzone und den Start von Hand fest.
  Der Nachtlauf: auf dem neuesten `main` die 1000 festen und so viele neue Zufallsfälle, wie in ~3 h passen, auf mehreren Rechnern
  nebeneinander; dazu Klickpfade durch die Oberfläche (`tests/test_clickpaths.py`, 40 feste und neue, in Chromium und der
  Safari-Engine – nur nachts, je Push kosteten drei 4 min).
  Jeder Zufallstest zieht neue Fälle, bis `KONTOR_FUZZ_MINUTES` seit **seinem** Beginn um sind – zwei in einem Job brauchen die
  doppelte Zeit und GitHub bricht den Job an seiner Grenze ab (bis 3.17.80 der Cashflow-Job, Nacht für Nacht: Cashflow und
  Planung in einer Datei; die neuen Planungsfälle liefen nie). Deshalb je Zufallstest ein eigener Job, bei zwei in einer Datei
  mit `-k` getrennt (`test_workflows.NightJobs` prüft es bei jedem Push).
  Dazu die Datenwelten (`test_data_worlds`): Zahlen, Anfragen, Assistent und – mit Chrome – jede Seite, die festen Welten in jeder
  Ansicht, dann neue Zufallswelten.
  Von Hand (fiel eine Nacht aus, oder nach einer Korrektur): GitHub → Actions → Nachtlauf → „Run workflow“ startet ihn sofort
  (oder `gh workflow run nightly.yml -R stecrz/Kontor`).
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
- `test_categories` (dazu die Vorschläge mit Stufe: Chance nach Laplace, Gegenpartei mit Betrag und Wort, Gegenbuchung, Wörter anderer je Gegenpartei, Bedeutung mit erfundenen Einbettungen, Geratenes nur als unsicher, nie selbst eingetragen), `test_e2e` (simuliertes MoneyMoney, HTTP, Browser; Browser-Tests warten auf einen Zustand – `until`, nach dem
  Speichern `stored` (steht es in der Ablage), vor Eingaben in eine Seite, die gleich neu lädt, `quiet` –, nie eine feste Zeit)
- `test_data_worlds` mit `data_worlds.py` (Datenwelten für Seiten und Assistent, nicht nur die Rechenlogik: lange Namen – auch ein
  Wort von 64 Buchstaben –, Beträge bis knapp 100 Mio. und einzelne Cent, ein leerer Bereich, einer ohne Konto, ein sehr voller mit
  vierzig Konten und Tausenden Umsätzen, Konten und Depot in USD/CHF/GBP, Heute am 31.12., 1.1., 29.2., Monatsersten und -letzten,
  ein heute eröffnetes Konto, eine Umbuchung über den Jahreswechsel, ein neuer Nutzer ohne Umsätze. Je Welt durch den ganzen Dienst:
  jeder Bereich und Monat geht auf, Nettovermögen = Euro-Konten, Fremdwährung in keiner Euro-Summe (Bilanz, Steuer, Kategorien,
  Umsatzsuche) und überall mit ihrem Kennzeichen, jede Anfrage der Seiten und jeder Download, jedes lesende Werkzeug des Assistenten
  zu jedem Bereich, Konto und Monat – nie mitten im JSON abgeschnitten –, eine ganze Frage, jede Seite im Browser am Tag der Welt.
  Je Push die zehn festen Welten (`FIXED`, Seiten in je einer Ansicht) und vier zufällige; nachts mehr, siehe oben)
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
  Seitenfenster. Ein Fehler nennt Fall, Ansicht und jeden Schritt: `KONTOR_FUZZ_SEED=<Nummer>`; von Hand 3 feste
  (`KONTOR_CLICK_SEEDS`), auf GitHub nur nachts, so viele, wie passen; Gefundenes nach der Korrektur in `FOUND_CLICKS`. Den Weg eines
  bestandenen Falls zeigt `KONTOR_CLICK_LOG=1` mit `-s`; was sie fanden, hält `FoundTest` fest: Menü am iPhone mit esc und
  Tipp auf die offene Seite, über der Assistenten-Seite, Demo ohne Wertpapiersuche; Skala auch für einen gleichbleibenden,
  nicht runden Wert (sonst `NaN`), Zahlen der Übersicht neben dem Assistenten in ihren Karten, Kopf der ersten Bilanzspalte am iPhone,
  Weg in die Demo mit noch laufenden Anfragen der eben gesperrten Sitzung (ihre 401 sind kein Fehler, alles danach zählt);
  `FoundAtNightTest` (erste ganze Nacht, 3.17.71): eine wieder geöffnete Seite steht, wo sie verlassen wurde – auch wenn Diagramme
  ihre Höhe erst danach bekommen oder Teile nachkommen (Vorschauen der Buchungsregeln); Karte der Übersicht und Suchwort der Hilfe
  führen weiter an ihre Stelle; Bereichsknöpfe eines Diagramms auch ohne Werte im Zeitraum; Seitenfenster nach Klick daneben
  sofort wieder zu öffnen; langer Titel neben dem ✕. Was die Nacht fälschlich meldete, prüft der Lauf seitdem richtig: nur
  Sichtbares wird angeklickt (Inhalt zugeklappter Karten hat in Chromium Maße), Formen eines Diagramms dort, wo sie gezeichnet
  sind, ein mit „…“ gekürzter Text in einem Knopf gilt nicht als abgeschnitten, die Stelle einer Seite wird nur mit ihrer zuletzt
  verlassenen Ansicht verglichen, gespeicherte Regeln machen jeden gemerkten Zustand ungültig, die Demo führt Links zu
  Einstellungen/Einrichtung/Protokoll zur Übersicht; seit 3.17.89: was in einem zugeklappten Abschnitt (`<details>`) der Seite steht,
  gehört nicht zu ihrem verglichenen Zustand – Kontor klappt Abschnitte zu, sobald eine andere Seite offen war –, und eine Seite,
  die dadurch kürzer ist als ihre gemerkte Stelle, darf an ihrem Ende stehen; seit 3.17.96: eine Form wird auf einem ganzen Pixel
  angetippt, dessen Nachbarn sie auch treffen – WebKit tippt auf ganze Pixel, eine haarfeine Form lässt der Lauf aus; jeder
  ResizeObserver der Seite wirkt erst im nächsten Frame – `CheckerTest`; seit 3.17.107: was nach dem Lesen einer Antwort oder
  Datei weiterläuft, läuft in einer eigenen Aufgabe (`bodyOf`, `api`) – WebKit führte es sonst oft mitten in der Auslieferung
  der ResizeObserver aus, und die dort gezeichnete Seite meldete „ResizeObserver loop …“ – `test_e2e.SafariAfterTheBodyTest`). Gezielt eine Ansicht prüfen, wo die Nacht meist findet
  (iPhone, WebKit): Nummern vorab mit `Case(<nummer>, True)` auswählen und als `KONTOR_FUZZ_SEED=<a>,<b>,…` laufen lassen
- `test_findable` (auffindbar: je Abschnitt der Hilfe Suchwörter, wie der Nutzer sie sagt, in `tests/search_words.json` – die Suche der Hilfe-Seite (unter den ersten drei, springt zum besten) und `search_help` (unter den vier Treffern) finden ihn; jeder Abschnitt und Anker der Hilfe ist Ziel eines „?“ oder Links aus Kontor; beide Suchen falten gleich (Füllwörter aus `memory.STOP`, Endungen). Fehlt ein Treffer: das Wort des Nutzers in den Abschnitt schreiben, nicht die Suche verbiegen; neuer Abschnitt der Hilfe: dort zwei, drei Suchwörter eintragen; am iPhone ist keine Spalte einer Tabelle der Hilfe schmaler als ein Wort darin – `PageReads`)
- `test_fuzz`, `test_privacy`, `test_security` (Sperre, Datenschlüssel, Belegordner; `NothingGoesOut`: welche Teile ins Netz können, zu welchen Hosts, welche Programme sie starten – ein neuer Weg nach außen wird dort eingetragen)
- `test_update_guard` (Prüfung vor dem Update: untergeschobene Änderungen werden gefunden, gewöhnliche nicht; Einstufung – Untergeschobenes bleibt kritisch, Geändertes an bestehenden Wegen und der Filter der Internetsuche zu prüfen, nachweislich Strengeres ohne Freigabe; nur was einen Aufruf nach außen erreicht, fragt (nicht die anderen Einträge einer Tabelle von Funktionen; eine sofort aufgerufene Tabelle, ein Verteiler, Methoden und verschachtelte Prüfungen fragen weiter); Erklärung und Zeilen je Eintrag; Warten und Freigabe, Archiv und Git-Klon)
- `test_hooks` (Lagebild, Push-Sperre und Lese-Sperre für große Dateien, `release.py` auf Wegwerf-Repositories: ein Commit je Version, schnellerer Chat, Konflikt mit der fremden Version benannt, bewusst geänderte Zeilen dürfen, beim Konflikt verlorene fremde Zeilen sperren (fein: was die fremde Version in die Zeile schrieb – ein Absatz, den beide geändert und zusammengeführt haben, geht ohne Ausnahme; `AddedParts`), rote Prüfung; `git reset` auf einen fremden Stand gesperrt)
- `test_workflows` (Workflow-Dateien: kein Schlüssel doppelt, kein „: “ in einem Wert ohne Anführungszeichen – sonst startet GitHub gar keinen Lauf, wie nach 3.17.21 und 3.17.64; `NightJobs`: jeder Job der Nacht fährt genau einen Zufallstest, jeder Zufallstest hat einen Job, seine Zeit passt in die Grenze des Jobs; `NightStart`: die Nacht startet jede Nacht genau einmal zwischen 3 und 4 Uhr, bei jeder Verspätung von GitHubs Zeitplan)
- `test_passkeys` (Zugang vom iPhone: CBOR/COSE/DER streng, ECDSA mit RFC-6979-Vektoren, Registrierung und Anmeldung mit einem Software-Passkey samt allen Fehlfällen, Link und Herausforderungen, QR-Code; über HTTP Hinzufügen, Face-ID-Anmeldung, jede Änderung nur bestätigt und nur für genau diese Anfrage, jede POST-Anfrage, `MAC_ONLY`, Entfernen beendet Sitzungen, nach Neustart, Demo, Zurücksetzen)
- `affected.py` (kein Test): nennt die Testdateien, die eine Änderung betrifft – für den lokalen Lauf vor dem Push
- `test_components` (Fremdes benannt: jedes Modell der Listen mit Lizenz, jede Bibliothek mit Eintrag – Name, Version, Lizenz, Herkunft, abgeschirmt)
- `test_logging` (Protokoll klein und lesbar: eine Datei, die ihr Neuestes behält, keine Zeile je Abfrage, gesperrtes MoneyMoney einmal, keine Pfade)
- `test_mac_webview` (nur im macOS-Lauf: jede Seite in macOS' WebKit mit `mac_webview.swift` – echter Rechtsklick, Bezug bleibt Zelle bzw. Zahl)
- `test_receipt_text` (Belege: was ihr Text sagt und zu welchem Umsatz sie gehören, erfundene Belege; Sandbox und Grenzen der Texterkennung, soweit Linux sie prüfen kann)
- `test_ui_docs` (`docs/ui`: jede Stelle mit `data-ex` beschrieben, jede Beschreibung gehört zu einer Stelle, jede Datei zu einer Seite)
- `test_memory` (beschädigte Datei, Steckbrief in seiner Grenze, Suche und Passendes zur Frage in ihren Grenzen, Suche in gespeicherten Verläufen (`Talks`), kein Werkzeug schreibt, Vergessenes auch aus dem Protokoll und der Unterhaltung, Sicherung, Export und Import (`Carried`: hin und zurück, jede Notiz geprüft, ganz oder gar nicht, Doppelte, Listen von anderswo, fremde und beschädigte Dateien, Grenzen), nur am Mac, nie in der Demo, Liste im Browser)
