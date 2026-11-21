# Kontor – Regeln für Claude

Kontor ist ein lokaler Dienst (Python ≥ 3.9, nur Standardbibliothek) mit Web-Oberfläche (`web/`), der auf den Daten von
MoneyMoney (macOS) arbeitet. Er läuft als launchd-Dienst beim Nutzer und startet sich selbst neu, sobald sich `VERSION` ändert.
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
Entschiedenes nie löschen, nach der Umsetzung „(umgesetzt in X.Y.Z)“ anhängen. `GoalTests` in `tests/test_rules.py` prüft, dass alles da ist.

## Arbeitsweise
- Was als Nächstes kommt und wann es fertig ist: `ROADMAP.md`. Erledigtes dort abhaken, Neues dort eintragen.
- Skills (`.claude/skills/`): `feature` (Punkt aus dem Fahrplan umsetzen), `ui-check` (Oberfläche ansehen), `release` (jede
  Änderung abschließen). Unabhängige Prüfung vor jedem Release mit Rechenlogik oder Schreibzugriff: Agent `reviewer`.
- Mehrere Aufgaben in einer Nachricht: selbst in unabhängige Teile schneiden und parallel mit Unteragenten erledigen (jeder in
  eigener Arbeitskopie); was dieselbe Stelle trifft, nacheinander. Je Teil eine eigene kleine Version, sobald er fertig ist.
- Leitplanken (`.claude/settings.json`): Sperren für Kontors Datenordner, MoneyMoneys Datenbank, Überweisungen und
  Force-Push; Sperren vor jedem Push (Versionskette, siehe Parallele Chats); Lagebild zu Beginn jeder Aufgabe (was die anderen
  Chats veröffentlicht haben); Erinnerung, wenn eine Änderung nicht abgeschlossen ist.
- GitHub Actions testet jeden Push (rund 6 min) – Linux: Python 3.9 und neu, Chrome und Safari-Engine, Code-Checks, je
  Python in zwei Hälften nebeneinander (Seiten = `tests/test_e2e.py`; alles andere); macOS: Apples Python, Swift-Helfer,
  Mac-App (bauen, Kontor darin laden, Mikrofon ohne Nachfrage), MoneyMoney-Brücke, Installation. Nachts auf dem neuesten `main` die 1000 festen und so viele jede Nacht neue Zufallsfälle, wie in ~3 h passen, auf
  mehreren Rechnern nebeneinander (`nightly.yml`; rot: siehe Parallele Chats).

## Prüfen
- Tests: `python3 -m pytest -q tests` (~2½ min; Browser-Tests mit Playwright; `sqlcipher` nur für Testdatenbanken).
  Mehr Zufallsläufe: `KONTOR_FUZZ_SEEDS=400 python3 -m pytest -q tests/test_fuzz.py` (feste Fälle 0–399), dazu neue:
  `KONTOR_FUZZ_RANDOM=<Anzahl>` oder `KONTOR_FUZZ_MINUTES=<Minuten>` (viele: mit Python 3.9); einen Fall aus einer
  Fehlermeldung („seed …“) wiederholen: `KONTOR_FUZZ_SEED=<Nummer>`.
- Code-Checks: `python3 -m pyflakes *.py tests/*.py .claude/hooks/*.py` und `npx eslint -c .github/eslint.config.mjs web`
  (einmal `npm install --no-save --no-package-lock eslint@9 globals`).
- GitHub prüft, was es lokal nicht gibt – Safari-Engine (WebKit), andere Schriften, langsamere Rechner. `pytest -rs` nennt
  Übersprungenes: ein Test, der nur in WebKit läuft, ist lokal ungeprüft (einmal je Sitzung `python3 -m playwright install webkit`
  versuchen; geht es nicht, dasselbe Verhalten auch in Chrome prüfen, wo es geht). Neue Browser-Tests warten auf einen Zustand
  (`until(…)`, `wait_for_function`), nie eine feste Zeit, und vergleichen Maße miteinander, nie mit festen Pixeln oder Schriftbreiten.
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
4. `CHANGELOG.md`: neuer Abschnitt oben, Überschrift `## X.Y.Z (JJJJ-MM-TT HH:MM)` (Ortszeit des Nutzers, Europe/Berlin), auf Deutsch, kompakt: je Änderung ein kurzer Punkt (Stichworte, eine Zeile), auf einen Blick lesbar – keine Erklärungen. Vorn der Bezug mit Doppelpunkt („KI-Assistent: …“, „Bilanz: …“; nur Regeln, Tests, CI: „Entwicklung: …“) – danach fasst die Update-Anzeige alles seit der installierten Version zusammen (Entwicklung ausgeblendet).
5. Commit und Push selbst erledigen, ohne nachzufragen. Nach dem Push auf `main` nichts nachschieben – eine Korrektur ist eine
   neue Version. Nur Regeln, Tests oder CI geändert: mit der nächsten Version mitnehmen; muss es sofort für die anderen Chats
   gelten, eine eigene Version (Changelog: „Entwicklung: …“).
6. Den Mac aktualisiert der Nutzer selbst – kein Zugriff darauf, im Abschluss nicht erwähnen.

## Parallele Chats
Mehrere Chats arbeiten gleichzeitig am Repo, meist an Verschiedenem, jeder in seinem eigenen Klon; abgestimmt wird nur über
GitHub. Ziel: jeder immer auf dem Stand, Konflikte klein, nichts doppelt.
- **Lagebild** (`.claude/hooks/briefing.py`): kommt von selbst zu Beginn jeder Aufgabe, sobald es Neues gibt – was andere
  Chats veröffentlicht haben, welche Dateien, Überschneidungen mit der eigenen Arbeit, Tests auf GitHub. Ein Klon ohne Eigenes
  wird dabei vorgespult. Kam zu Beginn einer Aufgabe keines: von Hand `python3 .claude/hooks/briefing.py`.
- **Früh und oft daraufsetzen** (`git pull --rebase origin main`): zu Beginn jeder Aufgabe und sobald das Lagebild Neues
  meldet – nicht erst beim Veröffentlichen. Lieber mehrere kleine Versionen als eine große: Veröffentlichtes kommt keinem mehr
  in die Quere. Dateien, die das Lagebild nennt, vor dem Ändern neu lesen.
- **Rot auf GitHub** behebt der Chat, dessen Version den Lauf als erste rot gemacht hat (Sitzungslink in der Commit-Nachricht) –
  sofort, als nächste Version. Alle anderen reparieren es nicht (sonst doppelt und gegeneinander), arbeiten weiter und
  veröffentlichen normal: ihr Lauf erbt dieselben Fehler, nur neue eigene zählen. Steht der fremde Fehler der eigenen Arbeit
  länger als 30 Minuten im Weg: selbst beheben, im Changelog nennen.
- **Nachtlauf rot** (`nightly.yml`, Zufallsfälle; gehört zu keiner Version, das Lagebild meldet ihn): der nächste Chat,
  der es sieht, behebt es sofort als eigene Version mit „fix nightly“ in der Commit-Nachricht (`X.Y.Z: fix nightly: …`) – daran
  erkennen die anderen Chats, dass es erledigt ist, und lassen es liegen. Ein neuer Fall (Nummer ab 1.000.000) kommt nach der
  Korrektur in `FOUND` (`tests/fixtures.py`), damit jeder Lauf ihn prüft; vor dem Push mit `KONTOR_FUZZ_SEEDS=1000` und dem Fall
  nachprüfen (beide Python-Versionen). Ein anderer Chat war schneller: die eigene Korrektur verwerfen, soweit sie dasselbe behebt.
- **Sperren vor jedem Push nach `main`** – zwei Ebenen, dieselbe Regel: der git-Hook `.githooks/pre-push` (schaltet das
  Lagebild ein; gegen den Stand auf GitHub: `VERSION` höher, keine Changelog-Zeile von `main` verloren) und
  `.claude/hooks/guard.py` vor jedem `git push` (holt `main` selbst: neuester `main` in der eigenen Arbeit, jeder Commit hebt
  `VERSION` als Zahl, behält alle `## X.Y.Z`-Abschnitte und trägt oben seine eigene Version; keine Zeile, die eine der neuesten
  Versionen auf `main` gebracht hat, geht verloren – so fiel 3.16.35 auf, das bei richtiger Kette den Code von 3.16.32 zurücksetzte). GitHub prüft die Kette für jeden
  Push (Job „Versionskette“). Abgelehnt: nicht umgehen (`KONTOR_PUSH_OK=1` nur für eine bewusste Ausnahme, etwa einen
  Tippfehler in einem alten Eintrag), sondern holen, daraufsetzen, neu nummerieren. Anlass: 3.16.9 und 66ad67f (3.16.21) –
  `git reset --soft origin/main` auf altem Stand setzte einen alten Baum auf den neuen `main` und löschte fremde Versionen.
  Deshalb `git merge-base --is-ancestor origin/main HEAD` direkt vor dem Versions-Commit, nach dem letzten `git fetch`.
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
  zuordnet (unter Kategorisieren oder auf der Karte des Assistenten) – sein Klick ist die Freigabe, kein Schalter (`mm_categories.py`: direkt
  vorher neu lesen und prüfen, fremde Kategorien nur nach Rückfrage; vom iPhone Zugeordnetes erst beim nächsten Abgleich am Mac; Eingetragenes lässt sich unter Kategorisieren → Eingetragen rückgängig machen, nur am Mac);
  dazu – nur mit seiner Einstellung „Verweis in MoneyMoney“ (Belege), nur am Mac – der Belegpfad, angehängt an den Kommentar des Umsatzes (was dort steht, bleibt).
  Kontor hat keine eigenen Kategorien und ordnet nie selbst zu (gelernte Muster sind nur Vorschläge); nur im Cashflow schätzt es die Position von Umsätzen ohne Kategorie – sichtbar als „geschätzt“, ohne etwas in MoneyMoney einzutragen. Nie Buchungen, den Kategorienbaum oder
  Regeln des Nutzers in MoneyMoney ändern oder löschen, keine Überweisungen.
- Oberfläche nur über 127.0.0.1 bzw. Tailscale erreichbar. Netzverbindungen nur: Update-Prüfung bei GitHub und – nur auf ausdrücklichen Klick – das Nachschlagen von Wertpapiernamen bei OpenFIGI (Konten & Regeln → Kontostände; `security_names.py`, sendet nur ISINs) sowie das Laden von llama.cpp (GitHub) und Modelldateien (Hugging Face; auch das Sprachmodell zum Diktieren) für den Assistenten (Einstellungen → KI-Assistent; `llm_local.py`: nur diese Hosts, nur https, sendet nichts von dir, prüft jede Datei per SHA-256) – und, nur mit dem Recht „Internet“ des Assistenten (ab Werk aus) und je Abruf nach seinem Klick auf der Karte, die Internetsuche zum Lesen (`web_search.py`, `web_reader.py`): Stufe 1 Wikipedia, Wikidata, Gesetze im Internet, GLEIF, EZB, Bundesbank, Eurostat; Stufe 2 tagesschau-Suche, GDELT (Artikeltext nur frei zugänglich, nie an Bezahlschranken vorbei); Stufe 3 Tavily nur mit seinem eigenen Schlüssel (Kontor stoppt bei 950 Abrufen in 31 Tagen). Nur die festen Hosts je Quelle (Treffer der Stufen 2/3: nur ihr eigener Host, nur Adressen aus einem Treffer), nur https, nur GET (Tavily: sein POST nur mit der Frage), keine Cookies, keine Proxys, nur globale Adressen (nicht dieses Macs, des lokalen Netzes oder von Tailscale), verbunden mit genau der geprüften Adresse; Kontors Kennung (User-Agent) nur an Wikimedia, sonst eine neutrale; vorher prüft Kontor Suchbegriffe und Adresse gegen alles, was auch das Modell lesen kann (aus MoneyMoney und Kontors gespeicherten Zahlen und Einstellungen), und lehnt im Zweifel ab: Buchstaben anderer Alphabete; ganze Namen von Konten, Bereichen, Inhabern, Objekten, Kalkulationen, Gesellschaftern, Regeln, Gegenparteien und Kategorien (vereinheitlicht, auch zusammengeschrieben oder mit Trennzeichen dazwischen, ohne Rechtsform); markante Einzelwörter der eigenen Namen (nicht der Gegenparteien) auch als Wortanfang; IBANs wie geschrieben (gültiges Land, volle Länge, Prüfziffer), eigene Konto- und Vertragsnummern; Beträge, jede Zahl mit Cent, jede Ziffernfolge ab fünf Stellen (Jahre, Paragrafen und Kennungen von Statistiken gehen; Wikidata-Nummern nur an Wikidata, LEIs nur an GLEIF); kennt Kontor gar keine eigenen Daten, sucht es nicht. Kein Abgreifen von Suchmaschinen ohne Schnittstelle.
- Assistent (`assistant.py`, `llm_local.py`): ein Sprachmodell nur auf diesem Mac – llama.cpp als Kindprozess auf 127.0.0.1, Schlüssel nur im Arbeitsspeicher (nie in der Befehlszeile), ohne eigene Werkzeuge, offline, in der macOS-Sandbox (Standard „streng“: kein Netz, keine anderen Programme, keine Apple-Events, schreibt nur Zwischendateien, liest im Benutzerordner nur seinen eigenen Ordner – also weder Kontors noch MoneyMoneys Daten; eine schwächere Stufe stellt nur der Nutzer ein, nie Kontor von selbst – nichts, was der Modellprozess tut, lockert sie). Es kann nur, was die feste Werkzeugliste in `assistant.py` hergibt: lesen, Seiten zeigen und hervorheben, Änderungen vorschlagen – alle einer Antwort auf einer Karte an ihrem Ende, ausgeführt erst mit dem Klick des Nutzers (jede abwählbar), danach dort zurücknehmbar (was sich nicht zurücknehmen lässt, sagt die Karte vorher); jede ausgeführte Änderung mit Zeit, Inhalt und Begründung im Änderungsprotokoll (`assistant-changes.json`, verschlüsselt, Einstellungen → KI-Assistent; nie in Sicherung, Paket oder Protokoll, Zurücksetzen und Deinstallieren löschen es). Buchungsregeln (`propose_rule`: Darlehen, Beteiligung, Kontenspiegel) legt er nur nach Klick an oder ändert sie – geprüft wie unter Konten & Regeln (nie mit Fehlern), nur solange die geänderte Regel noch so ist wie beim Vorschlag, gespeichert als „vom Assistenten“: jede Buchung daraus wartet auf Freigabe, bis der Nutzer die Regel dort bestätigt; zurücknehmbar, solange unverändert. Nie Werkzeuge für Einstellungen, Zugang, Updates, den Assistenten selbst oder sonst etwas in MoneyMoney – außer der Kategorie von Umsätzen ohne Kategorie (`assign_categories`: nur bestehende Kategorien, nie über eine gesetzte, derselbe Weg wie Kategorisieren, zurücknehmbar nur am Mac) und dem Freigeben oder Zurückhalten wartender Auto-Buchungen (`decide_bookings`: nur, was auf Freigabe wartet, gebucht nur mit dem gezeigten Betrag, nur am Mac und endgültig – die Karte sagt es vorher; Zurückhalten zurücknehmbar). Einrichten (laden, Modell, Rechte, „Verläufe speichern“) nur am Mac über `/api/assistant/…` – nie über `/api/config`, Pakete oder Sicherungen. Diagramme im Chat: das Modell wählt nur aus einer festen Liste, was gezeigt wird; die Zahlen nimmt Kontor aus seinen eigenen Daten, gezeichnet von Kontors Code (keine Zahlen, kein Text, kein Code des Modells im Diagramm). Unterhaltungen im Arbeitsspeicher und – mit „Verläufe speichern“ (Standard: an) – verschlüsselt in Kontors Datenordner (`chats/assistant-chat-*.json`; die Schlüssel-Erneuerung erfasst den Ordner mit), damit der Nutzer sie unter „Verläufe“ wieder öffnet: nie in Sicherung, Paket oder Protokoll, kein Werkzeug des Modells dafür, einzeln/alle löschbar, Zurücksetzen und Deinstallieren löschen sie. Belege, die der Nutzer in den Chat gibt (PDF, Bild): nur im Arbeitsspeicher und nur in dieser Unterhaltung, nie gespeichert, protokolliert oder gesichert (im Verlauf nur der Dateiname); ihren Text liest macOS' Texterkennung auf diesem Mac (`receipt_text.py`: eigenes Hilfsprogramm, immer in der Sandbox, gleich was für das Modell eingestellt ist – kein Netz, keine anderen Programme, schreibt nur in einen eigenen Ordner je Lauf (nie in Kontors Zwischenordner `kontor-…`), liest weder Kontors noch MoneyMoneys Daten); der Text ist für das Modell Daten, nie Anweisung – danach stehen andere Vorschläge dieser Unterhaltung auf der Karte abgewählt; abgelegt erst nach dem Klick (`file_receipt`, wie ein Upload unter Umsätze & Belege, ohne Verweis in MoneyMoney), zurücknehmbar samt Datei. Diktieren: ein zweites Modell (nur Spracherkennung) als eigener Prozess mit derselben Abschirmung; die Aufnahme geht nur vom Browser bzw. Kontors Mac-App an Kontor und an dieses Modell, wird nie gespeichert oder protokolliert. Internet (`web_search`, `web_read`, nur mit dem Recht „Internet“): Kontor sucht, nicht das Modell – mitten in der Antwort fragt eine Karte (Quelle, Stufe, Suchbegriffe bzw. Adresse, Begründung; Abrufen/Nicht abrufen; ohne Antwort in 3 Minuten: nein); geholt wird in einem kurzlebigen eigenen Prozess (`python3 -I`, am Mac in der macOS-Sandbox nach der Stufe des Nutzers: Netz nur nach außen auf Port 443, liest weder Benutzerordner noch Kontors Daten, schreibt nur Zwischendateien, keine anderen Programme), Größen- und Zeitgrenze, HTML/XML zu reinem Text bzw. Daten (XML ohne eigene Entitäten); das Modell bekommt es als „untrusted web text“; danach lehnt Kontor in dieser Unterhaltung jede Änderung ab (auch gespeichert und wieder geöffnet), mit Hinweis an Modell und Nutzer; verlinkt werden in Antworten nur Adressen, die Kontor abgerufen hat, und Treffer der Quellen mit festem Host (nur https, nur diese Hosts), immer mit sichtbarem Host; Stopp beendet auch einen laufenden Abruf. Die Kurzerklärung per Rechtsklick hat keine Karte: dort keine Werkzeuge, die auf eine warten (Internet, Änderungen). Jeder Abruf mit Zeit, Quelle, Suchbegriffen bzw. Adresse und Begründung im Änderungsprotokoll (nie Inhalte); in Kontors Log nur, dass abgerufen wurde. Der Tavily-Schlüssel nur am Mac über `/api/assistant/web`, verschlüsselt in `assistant-web.json` (mit dem Zähler), nie angezeigt, nie in Protokoll, Paket, Sicherung oder für das Modell lesbar; Zurücksetzen und Deinstallieren löschen ihn. Standard: aus; Änderungsrechte an (jede Änderung erst nach dem Klick), Internet aus, „vom iPhone“ aus.
- Mac-App (`mac_app.swift`, gebaut von `mac_app.py`): nur ein Fenster um Kontors Seite auf 127.0.0.1 – jede andere Adresse öffnet der Browser, nie die App; das Mikrofon bekommt ohne Nachfrage nur Kontors eigene Seite (eigene Adresse, Hauptframe), sonst nichts (keine Kamera, kein Bildschirm); Nachrichten der Seite zählen nur von dort; keine eigenen Netzverbindungen, keine anderen Programme, kein Web-Inspector; keine Texte in der App (Menü von der Seite, Info.plist aus `web/i18n.js`); neu gebaut nur, wenn sich ihre Bauteile ändern (sonst fragt macOS erneut); Deinstallieren entfernt ihre Website-Daten, Einstellungen und Freigaben.
- Keine Passwörter oder Zugangsdaten speichern, protokollieren oder zwischenspeichern; Datenordner verschlüsselt. Einzige Ausnahme bisher: der
  Tavily-Schlüssel des Nutzers für die Internetsuche (siehe Assistent).
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
- Hilfe: `docs/help.de.md` und `docs/help.en.md` gemeinsam pflegen (gleiche Anker); Bilder mit `tests/screenshots.py` (de/en) aus erfundenen Daten erzeugen – beides nur beim großen Versionssprung (zweite Stelle), nie bei kleinen Versionen.
- Präfix `mm_` nur für Teile, die direkt mit MoneyMoney sprechen.

## Oberfläche
- Gestaltung und Bedienung nach Apples Human Interface Guidelines (macOS und iOS): klare Hierarchie, bekannte Bedienmuster und Tastaturkürzel, ruhige Typografie, Hell- und Dunkelmodus.
- Zielgeräte: 14-Zoll-MacBook (Kontors Mac-App bzw. Safari, Fenster fast im Vollbild) und iPhone; im Dunkelmodus gut lesbar (keine Pastelltöne).
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
| `realestate.py`, `tax.py`, `receipts.py`, `receipt_text.py` | Immobilienkalkulation, Steuer, Belege, Text eines Belegs (macOS-Texterkennung, abgeschirmt) |
| `assistant.py` / `llm_local.py` | Assistent: feste Werkzeuge, Rechte, Fragen und Einträge nach Klick / llama.cpp und Modelle laden, prüfen, abgeschirmt starten und stoppen |
| `mac_app.py` + `.swift` | Kontors eigene Mac-App: Fenster mit WebKit um die Oberfläche, Menü, Downloads, Mikrofon nur für Kontors Seite; am Mac gebaut (nur bei geänderten Bauteilen) |
| `web_search.py` / `web_reader.py` | Internetsuche des Assistenten: Quellen und Stufen, Filter gegen eigene Daten, Tavily-Schlüssel und Kontingent / ein Abruf im eigenen, abgeschirmten Prozess |
| `storage.py`, `auth.py`, `updates.py`, `tls_cert.py` | verschlüsselte Ablage, Anmeldung/Touch ID, Updates, Zertifikat |
| `web/app.js`, `web/i18n.js` | Oberfläche (eine Datei, Seiten über `#…`), Texte |
| `tests/` | `fixtures.py` (erfundene Daten), `test_rules`, `test_cashflow` (Abstimmung je Monat, Zufallsläufe), `test_scenarios` (Lebensfälle über Bereiche: Einlagen, Kauf, Darlehen, Auslagen; Monats-/Jahreswechsel, gemischt), `test_categories`, `test_e2e` (simuliertes MoneyMoney, HTTP, Browser), `test_assistant` (mit `fake_llama.py` statt llama.cpp, Downloads ohne Netz), `test_web` (Internetsuche ohne Netz: Freigabe, Filter, Hosts, Grenzen, eingeschleuste Befehle), `test_tour` (Rundgang: jede Seite hell/dunkel, Mac/iPhone, de/en – Skriptfehler, Überlaufen, Textschlüssel, Kontrast), `test_fuzz`, `test_privacy`, `test_security` (Sperre, Datenschlüssel, Belegordner; `NothingGoesOut`: welche Teile ins Netz können, zu welchen Hosts, welche Programme sie starten – ein neuer Weg nach außen wird dort eingetragen), `test_hooks` (Lagebild und Push-Sperre der parallelen Chats) |
