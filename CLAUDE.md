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
- GitHub Actions testet jeden Push – Linux: Python 3.9 und neu, Chrome und Safari-Engine, Code-Checks; macOS: Apples Python,
  Swift-Helfer, MoneyMoney-Brücke, Installation – und nachts mit 1000 Zufallsläufen.

## Prüfen
- Tests: `python3 -m pytest -q tests` (~2½ min; Browser-Tests mit Playwright; `sqlcipher` nur für Testdatenbanken).
  Mehr Zufallsläufe: `KONTOR_FUZZ_SEEDS=400 python3 -m pytest -q tests/test_fuzz.py`.
- Code-Checks: `python3 -m pyflakes *.py tests/*.py .claude/hooks/*.py` und `npx eslint -c .github/eslint.config.mjs web`
  (einmal `npm install --no-save --no-package-lock eslint@9 globals`).
- Oberfläche: `node --check web/app.js`; ansehen mit `python3 tests/preview.py <ordner> '#route'` (hell/dunkel, Mac/iPhone; `--js` z. B. für ganze Tabellen).

## Jede Änderung abschließen (Skill `release`)
1. Tests grün.
2. **Ein Commit je Version:** Code, Tests, Texte, Fahrplan, `VERSION` (dritte Stelle +1, auch bei mehreren Verbesserungen auf
   einmal) und `CHANGELOG.md` zusammen. Nachricht kurz, englisch: `X.Y.Z: <was sich ändert>`, darunter nur eine Zeile mit
   Modell und Link zur eigenen Sitzung (`Claude Opus 5.5: https://claude.ai/code/session_…`, beides aus den Hinweisen der
   Sitzung) – keine E-Mail, kein `Co-Authored-By`, keine Tags. Zweite Stelle nur bei erheblichen Änderungen und nur nach Rückfrage. Erste Stelle nie.
3. **Erst geprüft, dann auf `main`:** vor dem Push alle Tests lokal – mit aktuellem Python (samt Browser) und mit Python 3.9
   (Apples Version auf dem Mac) –, dann der eine Commit direkt auf `main`. Ein Push kommt ganz oder gar nicht an: eine Version
   erscheint nie halb. GitHub Actions danach für genau diesen Commit abwarten; rot: sofort als nächste Version beheben und dem
   Nutzer in einem Satz Bescheid geben.
4. `CHANGELOG.md`: neuer Abschnitt oben, Überschrift `## X.Y.Z (JJJJ-MM-TT HH:MM)` (Ortszeit des Nutzers, Europe/Berlin), auf Deutsch, kompakt: je Änderung ein kurzer Punkt (Stichworte, eine Zeile), auf einen Blick lesbar – keine Erklärungen.
5. Commit und Push selbst erledigen, ohne nachzufragen. Nach dem Push auf `main` nichts nachschieben – eine Korrektur ist eine
   neue Version. Nur Regeln, Tests oder CI geändert: mit der nächsten Version mitnehmen; muss es sofort für die anderen Chats
   gelten, eine eigene Version (Changelog: „Entwicklung: …“).
6. Den Mac aktualisiert der Nutzer selbst – kein Zugriff darauf, im Abschluss nicht erwähnen.

## Parallele Chats
Bis zu drei Chats arbeiten gleichzeitig am Repo, meist an Verschiedenem, jeder in seinem eigenen Klon; keiner sieht die anderen.
- Lokal beliebig committen; auf GitHub kommt nur Fertiges, als ein Commit je Version – ohne Zweige, direkt auf `main`.
- Direkt vor dem Versions-Commit holen und die eigene Arbeit daraufsetzen (`git pull --rebase origin main`); die Nummer immer
  aus dem frisch geholten `main`; zusammengefasst wird nur, wenn dieser `main` in der eigenen Arbeit steckt (sonst gingen fremde
  Änderungen verloren). Konflikte: beide Seiten lesen und so zusammenführen, dass beide Änderungen erhalten bleiben;
  Fremdes nie verwerfen. Lässt sich ein Konflikt nicht eindeutig auflösen (Unvereinbares, eine Entscheidung steht an): den
  Nutzer fragen, mit Empfehlung. Nach jedem Rebase die Tests erneut – auch ohne Konflikt, denn Logikfehler meldet Git nicht.
- War ein anderer Chat schneller (Push abgelehnt): `VERSION` und `CHANGELOG.md` nie zusammenführen, sondern den eigenen Commit
  ohne sie neu aufsetzen, daraufsetzen, testen und mit der nächsten Nummer veröffentlichen. Jede Version bleibt ein Commit;
  die Nummer im letzten Commit auf `main` ist immer die aktuelle.
- Nie Force-Push, `main` nie löschen.

## Kleine und große Versionen
- Kleine Versionen (dritte Stelle): zügig vorankommen – Funktionen, Verbesserungen, neue Features im Code; die üblichen Prüfungen.
  **Keine** Hilfe-Bilder, **keine** Überarbeitung von README und Hilfe (`docs/`) – das gibt es nur beim großen Versionssprung
  (unnötige Änderungen im Repo vermeiden). Tooltips in `web/i18n.js` gehören zum Code und werden mit gepflegt.
- Großer Versionssprung (zweite Stelle, z. B. 3.11.5 → 3.12.0; auf Wunsch des Nutzers oder nach Rückfrage): vorher eine
  Gesamtprüfung mit voller Kraft – die letzten Änderungen final abnehmen, alle Referenzen aktuell, fehlerfrei. Gefundenes direkt
  verbessern, dann in perfekter Form veröffentlichen:
  - Alle Tests, dazu viele Zufallsläufe (`KONTOR_FUZZ_SEEDS=1000`, auch für `test_scenarios`), zusätzlich eigene Testdaten mit Sonderfällen und
    Fehlerfällen; alte Funktionen gezielt nachprüfen, ob ein Update sie beschädigt hat.
  - Jede Seite in hell/dunkel, Mac/iPhone ansehen (`ui-check`); alle Verlinkungen und Sprünge, alle Hilfe-Icons und Tooltips
    gegen den heutigen Stand; Texte de/en vollständig und einheitlich.
  - `README.md`, Hilfe (de/en, gleiche Anker) und Hilfe-Bilder (`tests/screenshots.py`) aktualisieren.
  - Einheitlichkeit: gleiche Dinge überall gleich gelöst (Bedienung, Farben, Begriffe, Cursor); Überflüssiges entfernen.
  - Sicherheit und Datenschutz erneut prüfen (Agent `reviewer` auf den ganzen Stand seit dem letzten großen Sprung).
  - Gefundenes beheben und sinnvoll optimieren; Änderungen mit Geschmacks- oder Produktfrage vor dem Push mit dem Nutzer klären.

## Sicherheit (ohne Ausnahme)
- Öffentliches Repo: keine persönlichen Daten (Namen, Konten, IBANs, Beträge, Pfade). Testdaten frei erfunden
  (`tests/test_privacy.py` prüft, was sich prüfen lässt).
- MoneyMoney nur über die AppleScript-Schnittstelle. Schreiben nur in Offline-Konten (Regeln) und das Kategoriefeld von Umsätzen, die er in Kontor
  zuordnet – sein Klick ist die Freigabe, kein Schalter (`mm_categories.py`: direkt
  vorher neu lesen und prüfen, fremde Kategorien nur nach Rückfrage; vom iPhone Zugeordnetes erst beim nächsten Abgleich am Mac; Eingetragenes lässt sich unter Kategorisieren → Eingetragen rückgängig machen, nur am Mac);
  dazu – nur mit seiner Einstellung „Verweis in MoneyMoney“ (Belege), nur am Mac – der Belegpfad, angehängt an den Kommentar des Umsatzes (was dort steht, bleibt).
  Kontor hat keine eigenen Kategorien und ordnet nie selbst zu (gelernte Muster sind nur Vorschläge); nur im Cashflow schätzt es die Position von Umsätzen ohne Kategorie – sichtbar als „geschätzt“, ohne etwas in MoneyMoney einzutragen. Nie Buchungen, den Kategorienbaum oder
  Regeln des Nutzers ändern oder löschen, keine Überweisungen.
- Oberfläche nur über 127.0.0.1 bzw. Tailscale erreichbar. Netzverbindungen nur: Update-Prüfung bei GitHub und – nur auf ausdrücklichen Klick – das Nachschlagen von Wertpapiernamen bei OpenFIGI (Konten & Regeln → Kontostände; `security_names.py`, sendet nur ISINs) sowie das Laden von llama.cpp (GitHub) und Modelldateien (Hugging Face; auch das Sprachmodell zum Diktieren) für den Assistenten (Einstellungen → KI-Assistent; `llm_local.py`: nur diese Hosts, nur https, sendet nichts von dir, prüft jede Datei per SHA-256).
- Assistent (`assistant.py`, `llm_local.py`): ein Sprachmodell nur auf diesem Mac – llama.cpp als Kindprozess auf 127.0.0.1, Schlüssel nur im Arbeitsspeicher (nie in der Befehlszeile), ohne eigene Werkzeuge, offline, in der macOS-Sandbox (Standard „streng“: kein Netz, keine anderen Programme, keine Apple-Events, schreibt nur Zwischendateien, liest im Benutzerordner nur seinen eigenen Ordner – also weder Kontors noch MoneyMoneys Daten; eine schwächere Stufe stellt nur der Nutzer ein, nie Kontor von selbst – nichts, was der Modellprozess tut, lockert sie). Es kann nur, was die feste Werkzeugliste in `assistant.py` hergibt: lesen, Seiten zeigen und hervorheben, Einträge vorschlagen – eingetragen wird erst mit dem Klick des Nutzers auf die Karte, und dort lässt es sich zurücknehmen. Nie Werkzeuge für Einstellungen, Regeln, Zugang, Updates, den Assistenten selbst, Auto-Buchungen oder MoneyMoney. Einrichten (laden, Modell, Rechte) nur am Mac über `/api/assistant/…` – nie über `/api/config`, Pakete oder Sicherungen. Unterhaltungen nur im Arbeitsspeicher, nichts davon im Protokoll. Diktieren: ein zweites Modell (nur Spracherkennung) als eigener Prozess mit derselben Abschirmung; die Aufnahme geht nur vom Browser an Kontor und an dieses Modell, wird nie gespeichert oder protokolliert. Standard: aus; „Werte eintragen“ und „vom iPhone“ aus.
- Keine Passwörter oder Zugangsdaten speichern, protokollieren oder zwischenspeichern; Datenordner verschlüsselt.
- Kommandozeile (`kontor.py`) ohne Zugriff auf Daten: nur start, open, install, uninstall, password, version; Passwort neu setzen und Deinstallieren nur mit
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
- Hilfe: `docs/help.de.md` und `docs/help.en.md` gemeinsam pflegen (gleiche Anker); Bilder mit `tests/screenshots.py` (de/en) aus erfundenen Daten erzeugen – beides nur beim großen Versionssprung (zweite Stelle), nie bei kleinen Versionen.
- Präfix `mm_` nur für Teile, die direkt mit MoneyMoney sprechen.

## Oberfläche
- Gestaltung und Bedienung nach Apples Human Interface Guidelines (macOS und iOS): klare Hierarchie, bekannte Bedienmuster und Tastaturkürzel, ruhige Typografie, Hell- und Dunkelmodus.
- Zielgeräte: 14-Zoll-MacBook (Safari, Fenster fast im Vollbild) und iPhone; im Dunkelmodus gut lesbar (keine Pastelltöne).
- Texte auf Deutsch, kurz, ohne Fachbegriffe, Einzahl/Mehrzahl korrekt. Keine überflüssigen Erklärtexte: was Tooltip oder Hilfe sagt, steht nicht noch einmal auf der Seite.
- Konten in der Reihenfolge von MoneyMoney.
- Wo was liegt: Was die Zahlen bestimmt, unter „Konten & Regeln“ (Konten, Bereiche, Kontostände, Cashflow-Positionen, Buchungsregeln, Steuer); wie Kontor arbeitet (Verbindung, Abgleich, Zugang, Belege, Assistent, Updates, Sicherung), unter „Einstellungen“. Die Einrichtung ist nur ein geführter Weg durch diese Seiten, keine eigene Ablage.
- Hinweise für den Nutzer im Chat, nicht als Dateien im Repo.

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
| `realestate.py`, `tax.py`, `receipts.py` | Immobilienkalkulation, Steuer, Belege |
| `assistant.py` / `llm_local.py` | Assistent: feste Werkzeuge, Rechte, Fragen und Einträge nach Klick / llama.cpp und Modelle laden, prüfen, abgeschirmt starten und stoppen |
| `storage.py`, `auth.py`, `updates.py`, `tls_cert.py` | verschlüsselte Ablage, Anmeldung/Touch ID, Updates, Zertifikat |
| `web/app.js`, `web/i18n.js` | Oberfläche (eine Datei, Seiten über `#…`), Texte |
| `tests/` | `fixtures.py` (erfundene Daten), `test_rules`, `test_cashflow` (Abstimmung je Monat, Zufallsläufe), `test_scenarios` (Lebensfälle über Bereiche: Einlagen, Kauf, Darlehen, Auslagen; Monats-/Jahreswechsel, gemischt), `test_categories`, `test_e2e` (simuliertes MoneyMoney, HTTP, Browser), `test_assistant` (mit `fake_llama.py` statt llama.cpp, Downloads ohne Netz), `test_tour` (Rundgang: jede Seite hell/dunkel, Mac/iPhone, de/en – Skriptfehler, Überlaufen, Textschlüssel, Kontrast), `test_fuzz`, `test_privacy` |
