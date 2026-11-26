# Kontor – Regeln für Claude

Kontor ist ein lokaler Dienst (Python, nur Standardbibliothek) mit Web-Oberfläche (`web/`), der auf den Daten von
MoneyMoney (macOS) arbeitet. Er läuft als launchd-Dienst beim Nutzer und startet sich selbst neu, sobald sich `VERSION` ändert.
Er läuft in seinem eigenen, aktuellen Python in seinem Ordner (bei der Installation geladen, siehe Sicherheit); Apples Python 3.9 startet nur den Starter – keine Rücksicht mehr auf 3.9 im übrigen Code (Nutzer, 2026-11-23).
Der Nutzer will Ergebnisse, keine Zwischenstände: selbstständig arbeiten, fragen nur bei echten Produktentscheidungen.

## Ziel
Kontor wird der digitale Finanzchef (CFO) des Nutzers: Überblick über sein Privatvermögen und die Gesellschaften dahinter
(Beteiligungen, Immobilien, Darlehen – von der GbR bis zur GmbH mit etwa 100 Mio. € Umsatz), Firmenwerte, die anteilig ins
Privatvermögen fließen, die Gesellschaften selbst führen (Steuer, Umsatzsteuer, Nebenkosten, Ausschüttungen; Zahlen aus DATEV
über das Data-Warehouse) – und im Kern ein lernender KI-Assistent, der sich erinnert, von selbst auf Wichtiges hinweist und
Routine abnimmt. Kein Haushaltsbuch. Rangfolge: Sicherheit, Privatsphäre, Kontrolle, Nachvollziehbarkeit, dann Komfort – alles
lokal, nichts nach außen; die KI schlägt nur vor, ausgeführt wird erst nach dem Klick des Nutzers (einzeln oder als einmal
bestätigte Regel). Ausführlich mit Leitlinien, Entscheidungen, Reihenfolge und Offenem: oben in `ROADMAP.md`. Vom Nutzer
entschiedene Änderungen an den Regeln unten stehen dort unter „Entschieden“; sie gelten, sobald umgesetzt, und kommen dann hierher.
Ziel, Leitlinien, „Entschieden“ und „Offen“ ändert nur der Nutzer (oder ein Chat auf seinen Wunsch); bei Konflikten immer erhalten.
Entschiedenes nie löschen – auch Abgelehntes, immer mit dem Grund –, nach der Umsetzung „(umgesetzt in X.Y.Z)“ anhängen. `GoalTests` in `tests/test_rules.py` prüft, dass alles da ist.

## Arbeitsweise
- **GitHub ist das einzige Gedächtnis** (Nutzer, 2026-11-23): Jeder künftige Chat kennt nur, was im Repo steht. Deshalb kommt
  mit derselben Version ins Repo, von selbst: jede Entscheidung des Nutzers samt Grund – auch jede Ablehnung (`ROADMAP.md`,
  „Entschieden“/„Offen“; Nutzer, 2026-11-24: er will nichts zweimal sagen müssen) –, jede neue Regel und jeder geänderte Ablauf
  (`CLAUDE.md`, Skills, Hooks, Tests), jedes geänderte Verhalten (siehe „Was wo gepflegt wird“). Vor jeder Version fragen: Würde
  ein neuer Chat mit nur diesem Repo richtig weiterarbeiten? Das Repo ist öffentlich: nie etwas Persönliches (siehe Sicherheit).
- `ROADMAP.md`: was offen ist und wann es fertig ist. Erledigte Punkte dort streichen (das Erledigte steht im `CHANGELOG.md`),
  Entscheidungen bleiben.
- Ein Chat je Aufgabe (der Nutzer startet Paralleles selbst). Mehrere Aufgaben in einer Nachricht: nacheinander, je Teil eine
  kleine Version. Unteragenten nur für die unabhängige Prüfung (`reviewer`) oder eine lange, abgetrennte Suche – jeder liest neu.
- Skills (`.claude/skills/`): `feature` (Punkt umsetzen), `ui-check` (Oberfläche ansehen), `release` (jede Version abschließen),
  `major` (großer Versionssprung). Agent `reviewer` (unabhängige Prüfung).
- Werkzeuge (Python wie auf GitHub, Python 3.9 für den Starter, Chrome, ESLint, sqlcipher): `.claude/tools/setup.sh` läuft beim
  Start jeder Sitzung von selbst im Hintergrund (Ergebnis in `/tmp/kontor-setup.out`); meldet `release.py`, dass etwas fehlt: von Hand.
- Leitplanken (`.claude/settings.json`, `.claude/hooks/`): Sperren für Kontors Datenordner, MoneyMoneys Datenbank, Überweisungen,
  Force-Push und das Ganzlesen großer Dateien; keine MCP-Dienste gesperrt (Nutzer, 2026-11-24: die Ersparnis war gering, nichts soll später fehlen); Versionskette vor jedem Push; Lagebild zu Beginn jeder Aufgabe; Erinnerung, wenn
  eine Änderung nicht abgeschlossen ist.

## Sparsam arbeiten (Nutzer, 2026-11-23/24: Credits nur, wo sie etwas bringen – ohne Abstriche bei Sicherheit und Korrektheit)
Jeder Schritt eines Chats liest den ganzen bisherigen Verlauf neu – Kosten wachsen mit Länge des Verlaufs × Zahl der Schritte.
- Große Dateien (`web/app.js`, `assistant.py`, `service.py`, große Tests, Hilfe) nie ganz lesen: `grep -n`, dann Read mit
  `offset`/`limit` um die Stelle (der Guard sperrt sonst ab 100 KB). `ROADMAP.md`, `docs/rules/*.md`: nur den Abschnitt.
- Prüfen und Veröffentlichen mit `.claude/tools/release.py` – ein Aufruf statt vieler Schritte. Nicht auf GitHub warten: ein
  roter Lauf erscheint im Lagebild des nächsten Chats (siehe Parallele Chats). Nie `sleep`, nie wiederholtes Nachsehen.
- Ausgaben klein halten: lange Befehle in eine Datei, dann nur `tail`/`grep`.
- Was erst der große Versionssprung braucht (englische Hilfe, README, Bilder, `HIGHLIGHTS.md`, Gesamtprüfung), nicht in kleinen
  Versionen – aber alles, was Fehler verhindert, in jeder.

## Prüfen – zwei Stufen (Nutzer, 2026-11-24)
GitHub prüft jede Version gleich, ob klein oder groß (`.github/workflows/tests.yml`: alle Tests, Kontors Python und 3.9 für den
Starter, Chrome und Safari-Engine, macOS mit Mac-App und Abschirmung; nachts zwischen 3 und 4 Uhr deutscher Zeit 1000 feste und neue Zufallsfälle und Klickpfade durch die Oberfläche, `nightly.yml`, gestartet von `night_start.yml`;
Einzelheiten: `docs/rules/tests.md`). Was Claude selbst prüft und mitpflegt, hängt von der Stufe ab:

| | Kleine Version (dritte Stelle) | Großer Versionssprung (zweite Stelle) – Skill `major` |
|---|---|---|
| Tests | neue Tests für jede Änderung (Normal-, Sonder-, Fehlerfall; Rechenlogik mit Abstimmung auf den Cent); `release.py`: Code-Checks, betroffene Tests ohne Browser, Rechenlogik mit 400 Zufallsfällen, Starter mit Python 3.9, neue Browser-Tests der Änderung über `--tests` | GitHub und der letzte Nachtlauf grün; zusätzlich eigene Sonder- und Fehlerfälle, alte Funktionen gezielt nachgeprüft |
| Ansehen | geänderte Seite mit `ui-check` (Mac hell, iPhone dunkel) | jede Seite hell/dunkel, Mac/iPhone; Verlinkungen, Hilfe-Icons, Tooltips |
| Unabhängig | `reviewer` bei neuen Wegen nach außen, Schreiben nach MoneyMoney, Zugang und Daten | `reviewer` auf alles seit dem letzten Sprung, auch Rechenlogik |
| Mitpflegen | Texte und Tooltips de + en, `docs/ui`, deutsche Hilfe (nur der betroffene Abschnitt, nur wenn sich Bedienung oder Verhalten ändert), Fahrplan | englische Hilfe (alle seit dem letzten Sprung geänderten Abschnitte), README, Bilder für Hilfe und README, `HIGHLIGHTS.md`, Einheitlichkeit |

## Jede Änderung abschließen
Skill `release`: `release.py` prüft, setzt auf den neuesten `main`, schreibt `VERSION` (dritte Stelle +1) und den Changelog,
fasst alles zu einem Commit zusammen und pusht – nie etwas halb. Zweite Stelle nur bei erheblichen Änderungen und nur nach
Rückfrage (Skill `major`), erste nie. Den Mac aktualisiert der Nutzer selbst – kein Zugriff darauf, im Abschluss nicht erwähnen.

## Parallele Chats
Mehrere Chats arbeiten gleichzeitig, jeder in seinem Klon, abgestimmt nur über GitHub, ein Commit je Version direkt auf `main`
(keine Zweige; Nutzer, 2026-11-24: auf GitHub nur `main`). Den Zweig `claude/…`, den die Cloud-Sitzung zum Pushen vorgibt, nie
pushen – er bleibt lokal, `release.py` pusht `HEAD:main`, der Guard sperrt den Push dorthin. Einzelheiten: `docs/rules/parallel.md`.
- **Lagebild** (`.claude/hooks/briefing.py`) zu Beginn jeder Aufgabe: was andere veröffentlicht haben, Überschneidungen, Tests auf
  GitHub. Früh daraufsetzen (`git pull --rebase origin main`), genannte Dateien vor dem Ändern neu lesen; klein veröffentlichen.
- **Rot auf GitHub** – eine Version oder der Nachtlauf: der nächste Chat, der es im Lagebild sieht, behebt es zuerst, als eigene
  Version mit „fix ci“ bzw. „fix nightly“ im Betreff – daran lassen die anderen es liegen. War ein anderer schneller: die eigene
  Korrektur verwerfen. Fällt nur die Umgebung aus (Download, Spiegel): `gh run rerun <id> --failed`.
- **Sperren vor jedem Push** (`.claude/hooks/guard.py`, `.githooks/pre-push`, auf GitHub Job „Versionskette“): neuester `main` in der
  eigenen Arbeit, jede Version höher, nichts verloren, was eine Version nach dem eigenen Ausgangsstand in eine Zeile schrieb (bewusst
  Geändertes aus ihm darf); kein `git reset` auf einen fremden Stand. Nie umgehen, nie Force-Push, `main` nie löschen; fremde Zeilen
  ersetzen (`KONTOR_PUSH_OK=1`) nur nach dem Ja des Nutzers im Chat (Nutzer, 2026-11-24).
- Konflikte: beide Seiten erhalten, Fremdes nie verwerfen; Unvereinbares dem Nutzer mit Empfehlung vorlegen.

## Was wo gepflegt wird
Jede Sache steht an genau einer Stelle, die anderen verweisen darauf:

| Was | Wo | Für wen, wie | Wann |
|---|---|---|---|
| Texte der Oberfläche, Tooltips | `web/i18n.js` (`t()`/`tr()`; Tooltips `h_*` über `hq()`, Sprung in die Hilfe über `HELP_AT`) | Nutzer am Element: ein, zwei Sätze; jedes Bedienelement hat Tooltip oder „?“ (`test_tour`) | jede Version, de + en |
| Was jede Stelle zeigt | `docs/ui/<seite>.md`, am Element `data-ex="<seite>.<stelle>"` (Aufbau: `docs/rules/ui.md`) | der Assistent (Rechtsklick, Fragen zur Seite, `search_help`): was jede Zahl ist, wie gerechnet – keine Bedienung | jede neue oder geänderte Stelle, Zahl oder Berechnung |
| Hilfe | `docs/help.de.md` + `docs/help.en.md` (gleiche Anker) | Nutzer: wie es geht, warum, was es bewirkt, Sicherheit; der Assistent sucht darin | deutsch: wenn sich Bedienung oder Verhalten ändert, nur der Abschnitt; englisch: beim großen Sprung (neuer Abschnitt: im Englischen gleich Überschrift, Anker und ein Satz – `ReferenceTests`; dazu ein „?“ oder Link dorthin und Suchwörter in `tests/search_words.json` – `test_findable`) |
| README | `README.md` | Überblick, nur große Themen | großer Sprung |
| Änderungen | `CHANGELOG.md` (schreibt `release.py`), `HIGHLIGHTS.md` (Überblick je Hauptversion) | Nutzer in der Update-Anzeige | Changelog jede Version; Highlights beim großen Sprung |
| Fahrplan | `ROADMAP.md` | Nutzer und Chats: Entscheidungen, Offenes | jede Version, die einen Punkt berührt |
| Regeln, Sicherheit, Aufbau | `CLAUDE.md`, `docs/rules/` | Chats | neue Teile, neue Wege nach außen, neue Regeln |
| Fremdes, das Kontor nutzt | `components.py` (ein Eintrag; die Liste unter Einstellungen → Updates entsteht daraus), `NOTICE` | Nutzer: Name, Version, Lizenz, Herkunft, abgeschirmt ja/nein | jedes neue Modell in `llm_local` (`licence` wie seine Modellkarte sie nennt – nie geraten), jede Bibliothek, jedes fremde Programm |
| Bilder | `tests/screenshots.py` → `docs/img/` | Hilfe und README | großer Sprung |

## Sicherheit (ohne Ausnahme)
Kurzfassung; die vollständigen Regeln stehen in `docs/rules/security.md` (je Abschnitt die Dateien) – **vor jeder Änderung an
einer dort genannten Datei den Abschnitt lesen** (nur ihn, nicht die ganze Datei). Tests halten die Regeln maschinell
(`test_security`, `test_update_guard`, `test_passkeys`, `test_web`, `test_memory`, `test_privacy`).
- Öffentliches Repo: keine persönlichen Daten (Namen, Konten, IBANs, Beträge, Pfade). Testdaten frei erfunden
  (`tests/test_privacy.py` prüft, was sich prüfen lässt).
- MoneyMoney nur über die AppleScript-Schnittstelle. Schreiben nur in Offline-Konten (Regeln) und das Kategoriefeld von Umsätzen, die er in Kontor
  zuordnet (unter Kategorisieren oder auf der Karte des Assistenten) – sein Klick ist die Freigabe, kein Schalter (`mm_categories.py`: direkt
  vorher neu lesen und prüfen, fremde Kategorien nur nach Rückfrage; von einem hinzugefügten iPhone mit Face ID genau wie am Mac, siehe Zugang vom iPhone; Eingetragenes lässt sich unter Kategorisieren → Eingetragen rückgängig machen, am Mac oder vom hinzugefügten iPhone).
  Nie den Kommentar oder sonst etwas eines Umsatzes (`mm_bridge.jxa` lässt bei setTransaction nur die Kategorie durch); Belege nur in Kontor verknüpft.
  Kontor hat keine eigenen Kategorien und ordnet nie selbst zu (gelernte Muster sind nur Vorschläge); nur im Cashflow schätzt es die Position von Umsätzen ohne Kategorie – sichtbar als „geschätzt“, ohne etwas in MoneyMoney einzutragen. Nie Buchungen, den Kategorienbaum oder
  Regeln des Nutzers in MoneyMoney ändern oder löschen, keine Überweisungen.
- **Netzverbindungen** (`service.py, updates.py, llm_local.py, web_search.py, web_reader.py, security_names.py, pyruntime.py`): Oberfläche nur 127.0.0.1/Tailscale; Netz nur auf festen, benannten Wegen (Update-Prüfung, Suche/Laden für den Assistenten, OpenFIGI, Internetsuche nach Klick) – jeder neue Weg: dort eintragen und in `test_security.NothingGoesOut`. → [docs/rules/security.md#netzverbindungen](docs/rules/security.md#netzverbindungen)
- **Assistent** (`assistant.py, llm_local.py, receipt_text.py, table_text.py, pdf_tables.py`): Modell nur lokal, abgeschirmt, ohne eigene Werkzeuge; jede Änderung erst nach Klick auf der Karte, zurücknehmbar, protokolliert; Belege/Dateien nur im Arbeitsspeicher; Internet nur mit Recht und Karte. → [docs/rules/security.md#assistent](docs/rules/security.md#assistent)
- **Claude als Recherche-Stufe** (`web_search.py (claude_*), web_reader.ask_claude`): Nur mit eigenem API-Schlüssel, immer mit Karte und Klick, Filter gegen eigene Daten, Tagesgrenze. → [docs/rules/security.md#claude-als-recherche-stufe](docs/rules/security.md#claude-als-recherche-stufe)
- **Gedächtnis** (`memory.py, assistant.py (_notice, _rests_on)`): Notizen schreibt nur Kontor, nur aus den Worten des Nutzers (bzw. gekennzeichnet aus der Antwort), nie Zugangsdaten; Export/Import nur am Mac. → [docs/rules/security.md#gedaechtnis](docs/rules/security.md#gedaechtnis)
- **Mac-App** (`mac_app.swift, mac_app.py`): Nur ein Fenster um 127.0.0.1, Mikrofon nur für Kontors Seite, keine eigenen Verbindungen. → [docs/rules/security.md#mac-app](docs/rules/security.md#mac-app)
- **Eigenes Python** (`pyboot.py, pyruntime.py, pyselftest.py`): Fester, geprüfter Build, nur nach Klick; nur der Starter läuft mit 3.9 und fällt nie aus, der übrige Code nur im eigenen Python (Nutzer, 2026-11-23). → [docs/rules/security.md#eigenes-python](docs/rules/security.md#eigenes-python)
- **Fremdes wird benannt** (`components.py, NOTICE`): Alles Fremde mit Version, Lizenz (nachgeschlagen, nie geraten), Herkunft. → [docs/rules/security.md#fremdes-wird-benannt](docs/rules/security.md#fremdes-wird-benannt)
- **Updates** (`updates.py, update_guard.py`): Kontor nie von selbst installiert; die Prüfung vor dem Update meldet jeden neuen Weg nach außen – Aufrufe nach außen in kleinen, in `CHECKED` eingetragenen Funktionen (höchstens 70 Zeilen). → [docs/rules/security.md#updates](docs/rules/security.md#updates)
- Keine Passwörter oder Zugangsdaten speichern, protokollieren oder zwischenspeichern; Datenordner verschlüsselt. Einzige Ausnahmen: der
  Tavily-Schlüssel und der API-Schlüssel für Claude (Anthropic) des Nutzers für die Internetsuche (siehe Assistent und „Claude als Recherche-Stufe“).
- **Daten erst nach Anmeldung** (`access.py, storage.py`): Datenschlüssel nur verpackt; vor der Anmeldung liest nichts die Daten (`store.is_open`). → [docs/rules/security.md#daten-erst-nach-anmeldung](docs/rules/security.md#daten-erst-nach-anmeldung)
- **Demo** (`demo.py, service.py (DemoApp)`): Eigene erfundene Welt, liest nie Kontors Daten; jede neue Anfrage in `DEMO_GET`/`DEMO_POST`/`DEMO_NEVER`. → [docs/rules/security.md#demo](docs/rules/security.md#demo)
- **Zugang vom iPhone** (`devices.py, webauthn.py, qr.py, service.py (_remote_check, MAC_ONLY)`): Passkey mit Face ID je Gerät; jede Änderung von dort nur bestätigt; `MAC_ONLY` nie von dort; keine Proxys; Tailscale-Prüfung. → [docs/rules/security.md#zugang-vom-iphone](docs/rules/security.md#zugang-vom-iphone)
- Kommandozeile (`kontor.py`) ohne Zugriff auf Daten: nur start, open (Mac-App, sonst Browser), install, uninstall, password, version; Passwort neu setzen und Deinstallieren nur mit
  Kontor-Passwort oder Touch ID. Alles andere nur angemeldet in der Oberfläche.
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
- Präfix `mm_` nur für Teile, die direkt mit MoneyMoney sprechen.

## Oberfläche
- Gestaltung und Bedienung nach Apples Human Interface Guidelines (macOS und iOS): klare Hierarchie, bekannte Bedienmuster und Tastaturkürzel, ruhige Typografie, Hell- und Dunkelmodus.
- Zielgeräte: 14-Zoll-MacBook (Kontors Mac-App bzw. Safari, Fenster fast im Vollbild) und iPhone; im Dunkelmodus gut lesbar (keine Pastelltöne).
- Texte auf Deutsch, kurz, ohne Fachbegriffe, Einzahl/Mehrzahl korrekt. Keine überflüssigen Erklärtexte: was Tooltip oder Hilfe sagt, steht nicht noch einmal auf der Seite.
- Konten in der Reihenfolge von MoneyMoney.
- Einstellungen speichern sich bei jeder Änderung selbst (Feld verlassen, Haken, Auswahl, Zeile entfernt) – kein Speichern-Knopf; Fehler und Hinweise erscheinen darunter (`saveBar`, `data-autosave`; Nutzer, 2026-11-23).
- Optionale Felder: was bei Leerlassen gilt, steht grau im Feld (Platzhalter) oder im Tooltip (Nutzer, 2026-11-23).
- Zweistufige Kontoauswahl (erst Bereich, dann Konto): in der Kontoliste kein Bereichsname mehr; Gleichnamiges nur innerhalb des Bereichs unterschieden.
- Wo was liegt: Was die Zahlen bestimmt, unter „Konten & Regeln“ (Konten, Bereiche, Kontostände, Cashflow-Positionen, Buchungsregeln, Steuer); wie Kontor arbeitet (Verbindung, Abgleich, Zugang, Belege, Assistent, Updates, Sicherung), unter „Einstellungen“. Die Einrichtung ist nur ein geführter Weg durch diese Seiten, keine eigene Ablage.
- Hinweise für den Nutzer im Chat, nicht als Dateien im Repo.
- Auswahl der Modelle des Assistenten (`llm_local.CATALOG`) und Aufbau von `docs/ui`: `docs/rules/ui.md`.

## Aufbau
| Teil | Aufgabe |
|---|---|
| `kontor.py` | Kommandozeile (start, open, install, uninstall, password, version – ohne Daten) |
| `service.py` | Dienst: HTTP-API, statische Dateien, Zeitplan, Bericht im Hintergrund |
| `core.py` | Lesen aus MoneyMoney (schnell/voll), Einstellungen (`merged_config`, `check_config`), Lauf (`run_once`), Bericht, Pakete |
| `rules.py` | Buchungsregeln – Darlehen, Beteiligung, Kontenspiegel; zustandslos, erkennt Gebuchtes an `#kontor-…` |
| `model.py` | Konten, Umsätze, `Ledger`, Salden zum Stichtag, Markierungen |
| `report.py` | Bilanz, Cashflow (feste Positionen für alle Bereiche; Kategorien zählen darin), Planung je Bereich |
| `categorize.py` / `mm_categories.py` | Kategorien: MoneyMoney ist maßgeblich – Kategorisieren, Vorschläge, Regelvorschläge / Kategorie in MoneyMoney eintragen |
| `mm_bridge.py` + `.jxa` | einzige Schnittstelle zu MoneyMoney (Liste erlaubter Methoden) |
| `mm_history.py` + `.swift` | Kontostände aus MoneyMoneys Datenbank (Upload, nur Speicher) |
| `realestate.py`, `tax.py`, `receipts.py`, `receipt_text.py`, `table_text.py`, `pdf_tables.py` | Immobilienkalkulation, Steuer, Belege, Text eines Belegs und Wörter mit Lage je Seite (macOS-Texterkennung, abgeschirmt), Excel- und CSV-Tabellen für den Assistenten (abgesichert gelesen, Raster mit Adressen, exakte Summen, Prüfproben, Zeilen suchen), Tabellen aus PDFs und Bildern (Seiten zusammengesetzt, Spalten aus der Lage der Wörter) |
| `assistant.py` / `llm_local.py` | Assistent: feste Werkzeuge, Rechte, Fragen und Einträge nach Klick / llama.cpp und Modelle laden, prüfen, abgeschirmt starten und stoppen; wie jede Modellfamilie gefragt wird (`FAMILIES`: Werte der Modellkarte, Denkstufen – ein neues Modell der Liste braucht dort seine Familie, `test_sampling_as_the_makers_recommend`). Für die Antwortqualität gilt (Tests `Asking`, `Causes`): Werte nur aus der Modellkarte, nie geraten; Gedanken bleiben zwischen den Abfragen einer Antwort; der Systemtext nennt Arbeitsweisen, nie Einzelfälle; Start ohne fremdes Chat-Template und mit dem Zwischenspeicher (KV-Cache) in voller Genauigkeit (`test_start_chat_stop`). Bilder: als Ganzes nur an ein Modell, das sie liest, nur in der Anfrage ihrer Frage (`_pictures`); sein Bildteil kommt mit ihm (`vision_part`) |
| `memory.py` | Gedächtnis des Assistenten: Notizen (Dateien, Prüfung, nie Zugangsdaten), Steckbrief, Wortsuche (Formen, Wortteile, Tippfehler; nur Standardbibliothek) und Suche nach Bedeutung (Einbettungen daneben), Sicherung, Export und Import im offenen Format `kontor-memory` (`export_file`, `import_file`, `read_file`), Namen für den Suchfilter – Tests: `test_memory` (was sie prüfen: `docs/rules/tests.md`) |
| `mac_app.py` + `.swift` | Kontors eigene Mac-App: Fenster mit WebKit um die Oberfläche, Menü, Downloads, Mikrofon nur für Kontors Seite; am Mac gebaut (nur bei geänderten Bauteilen) |
| `web_search.py` / `web_reader.py` | Internetsuche des Assistenten: Quellen und Stufen, Filter gegen eigene Daten, Tavily-Schlüssel und Kontingent, Frage an Claude (Schlüssel, Modell, Tagesgrenze, Text der Anfrage) / ein Abruf im eigenen, abgeschirmten Prozess (auch der eine an Claude: `ask_claude`) |
| `demo.py` | Demo zum Vorzeigen: erfundene Welt (Privatperson vier Jahre, UG zwei Jahre, GbR mit Immobilie; Konten, Umsätze, Depot, Regeln) und ihr MoneyMoney im Speicher; `DemoApp`/`DemoBox` in `service.py` |
| `storage.py`, `access.py`, `auth.py`, `updates.py` + `update_guard.py`, `tls_cert.py` | verschlüsselte Ablage, Datenschlüssel nur nach Anmeldung (Schlüsseldatei, Erneuern), Anmeldung/Touch ID, Sitzungen (je Gerät), Updates (mit der Prüfung der neuen Dateien vor dem Installieren), Zertifikat und Tailscale-Prüfung (Tailnet Lock, serve/Funnel; nur lesend) |
| `devices.py`, `webauthn.py`, `qr.py` | Zugang vom iPhone: hinzugefügte Geräte (Passkeys, verschlüsselt), Link zum Hinzufügen und Herausforderungen (einmal, kurz, im Arbeitsspeicher) / Prüfen von Passkeys mit Bordmitteln (CBOR, COSE, ECDSA P-256, Registrierung und Anmeldung) / QR-Code des Links |
| `pyboot.py` / `pyruntime.py` / `pyselftest.py` | Kontors eigenes Python: Starter (wählt beim Start, fällt zurück, startet neu; nur Standardbibliothek, läuft mit 3.9) / laden, prüfen, umstellen, entfernen / Selbsttest, den das neue Python vor der Umstellung besteht – Tests: `test_python`, am Mac `tests/mac_python.py` |
| `components.py` | alles Fremde, das Kontor nutzt, für die Liste „Verwendete Programme“: Python, llama.cpp, Modelle (Lizenz je Repository), Bibliotheken (`LIBRARIES`, noch keine), macOS – Tests: `test_components` |
| `changelog.py` | Änderungen je Hauptversion für Einstellungen → Updates (`CHANGELOG.md` + `HIGHLIGHTS.md`; getrennt vom Updater) |
| `web/app.js`, `web/i18n.js` | Oberfläche (eine Datei, Seiten über `#…`), Texte |
| `docs/ui/*.md` | was jede Stelle der Seiten zeigt, für den Assistenten (Rechtsklick, `search_help`, `kontor.md` im Systemtext) |
| `tests/` | je Teil eine Testdatei (`test_<teil>.py`), erfundene Daten in `fixtures.py`, Stand-in für llama.cpp `fake_llama.py`; was welche Datei prüft: `docs/rules/tests.md` |
