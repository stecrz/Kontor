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
Entschiedenes nie löschen, nach der Umsetzung „(umgesetzt in X.Y.Z)“ anhängen. `GoalTests` in `tests/test_rules.py` prüft, dass alles da ist.

## Arbeitsweise
- **GitHub ist das einzige Gedächtnis** (Nutzer, 2026-11-23): Jeder künftige Chat kennt nur, was im Repo steht – nicht
  frühere Chats, nicht Claudes Erinnerung. Deshalb kommt mit derselben Version ins Repo, von selbst und ohne dass der Nutzer
  daran erinnern muss: jede Entscheidung des Nutzers (`ROADMAP.md`, „Entschieden“/„Offen“), jede neue oder geänderte Regel und
  jeder geänderte Ablauf (`CLAUDE.md`, Skills, Hooks, Tests), jedes geänderte Verhalten (Hilfe, `docs/ui`, Tooltips – siehe
  „Was wo gepflegt wird“). Vor jedem Release fragen: Würde ein neuer Chat mit nur diesem Repo richtig weiterarbeiten? Das Repo ist
  öffentlich: nie etwas Persönliches oder auf den Nutzer Zurückführbares (siehe Sicherheit).
- Was als Nächstes kommt und wann es fertig ist: `ROADMAP.md`. Erledigtes dort abhaken, Neues dort eintragen.
- Skills (`.claude/skills/`): `feature` (Punkt aus dem Fahrplan umsetzen), `ui-check` (Oberfläche ansehen), `release` (jede
  Änderung abschließen). Unabhängige Prüfung vor jedem Release mit Rechenlogik oder Schreibzugriff: Agent `reviewer`.
- Mehrere Aufgaben in einer Nachricht: in unabhängige Teile schneiden und nacheinander erledigen, je Teil eine eigene kleine Version,
  sobald er fertig ist (Nutzer, 2026-11-23: für Paralleles startet er selbst neue Chats). Unteragenten nur, wo sie wirklich etwas
  bringen – die unabhängige Prüfung (`reviewer`) oder eine lange, abgetrennte Suche –, denn jeder liest das Repo neu und kostet viel.
- Leitplanken (`.claude/settings.json`): Sperren für Kontors Datenordner, MoneyMoneys Datenbank, Überweisungen und
  Force-Push; Sperren vor jedem Push (Versionskette, siehe Parallele Chats); Lagebild zu Beginn jeder Aufgabe (was die anderen
  Chats veröffentlicht haben); Erinnerung, wenn eine Änderung nicht abgeschlossen ist.
- GitHub Actions testet jeden Push (rund 10 min) – Linux: Kontors eigenes Python, Chrome und Safari-Engine, Code-Checks, in vier Teilen nebeneinander, dazu Python 3.9 nur für den Starter (`tests/test_python.py`) (Seiten = `tests/test_e2e.py`; Assistent und Rundgang; Rechnen mit Zufallsfällen – je Push nur 12 feste, nachts 1000 und neue; alles andere – eine neue Testdatei landet dort von selbst); `--durations` nennt die langsamsten Tests; macOS: Apples Python, Swift-Helfer,
  Mac-App (bauen, Kontor darin laden, Mikrofon ohne Nachfrage; jede Seite in macOS' WebKit mit echtem Rechtsklick), Abschirmung der Modelle (`tests/test_mac_model.py`: kein Netz außer der eigenen Socket-Datei; echtes llama.cpp), MoneyMoney-Brücke, Installation, dazu Kontors eigenes Python (`tests/mac_python.py`: echt laden, falsche Prüfsumme, Quarantäne und Signatur, Selbsttest, Helfer in der Sandbox, Dienst als Kind des Starters, Neustart durch launchd, beschädigt → Apples Python, Deinstallieren, Update von der Version davor); Linux prüft denselben Ablauf mit dem echten Build für Linux. Nachts auf dem neuesten `main` die 1000 festen und so viele jede Nacht neue Zufallsfälle, wie in ~3 h passen, auf
  mehreren Rechnern nebeneinander (`nightly.yml`; rot: siehe Parallele Chats).

## Sparsam arbeiten (Nutzer, 2026-11-23: Credits nur, wo sie etwas bringen – ohne Abstriche bei Sicherheit und Korrektheit)
Jeder Schritt eines Chats liest den ganzen bisherigen Verlauf neu – Kosten wachsen mit Länge des Verlaufs × Zahl der Schritte.
- Lokal nur die betroffenen Tests: `python3 -m pytest -q $(python3 tests/affected.py)`; die volle Prüfung (beide Python, alle
  Browser, macOS, Zufallsfälle) macht GitHub bei jedem Push.
- Auf GitHub in **einem** Schritt warten: `gh run watch $(gh run list -R stecrz/Kontor -c $(git rev-parse HEAD) -L1 --json databaseId -q '.[0].databaseId') -R stecrz/Kontor --exit-status > /tmp/ci.log 2>&1; tail -3 /tmp/ci.log`
  (blockiert bis zum Ende; Zeitgrenze des Befehls hoch setzen). Nie `sleep`-Schleifen, nie wiederholtes Nachsehen.
- Ausgaben klein halten: lange Befehle in eine Datei, dann nur `tail`/`grep`; Dateien gezielt lesen (Abschnitt, Zeilenbereich),
  `ROADMAP.md` und `docs/rules/*.md` nur den betroffenen Abschnitt.
- Unteragenten nur für die unabhängige Prüfung (`reviewer`, bei Sicherheit, Geld, Schreibzugriff) – mit dem Diff und den
  geänderten Funktionen im Auftrag, damit er nicht das ganze Repo liest.
- Früh daraufsetzen und klein veröffentlichen: jeder Konflikt mit einem anderen Chat kostet ein erneutes Zusammenführen.

## Prüfen
- Tests: `python3 -m pytest -q tests` (alles, hier ~30 min – lokal nur vor einem großen Versionssprung; sonst `tests/affected.py`;
  Browser-Tests mit Playwright; `sqlcipher` nur für Testdatenbanken).
  Mehr Zufallsläufe: `KONTOR_FUZZ_SEEDS=400 python3 -m pytest -q tests/test_fuzz.py` (feste Fälle 0–399), dazu neue:
  `KONTOR_FUZZ_RANDOM=<Anzahl>` oder `KONTOR_FUZZ_MINUTES=<Minuten>`; einen Fall aus einer
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
3. **Erst geprüft, dann auf `main`:** vor dem Push lokal nur die betroffenen Tests (`tests/affected.py`, siehe Sparsam arbeiten; mit Python 3.9 nur `tests/test_python.py`, der Starter),
   dann der eine Commit direkt auf `main`. Ein Push kommt ganz oder gar nicht an: eine Version
   erscheint nie halb. GitHub Actions danach für genau diesen Commit abwarten; rot: sofort als nächste Version beheben und dem
   Nutzer in einem Satz Bescheid geben.
4. `CHANGELOG.md`: neuer Abschnitt oben, Überschrift `## X.Y.Z (JJJJ-MM-TT HH:MM)` (Ortszeit des Nutzers, Europe/Berlin), auf Deutsch, kompakt: je Änderung ein kurzer Punkt (Stichworte, eine Zeile), auf einen Blick lesbar – keine Erklärungen. Vorn der Bezug mit Doppelpunkt („KI-Assistent: …“, „Bilanz: …“; nur Regeln, Tests, CI: „Entwicklung: …“) – danach fasst die Update-Anzeige alles seit der installierten Version zusammen (Entwicklung ausgeblendet). Bringt die Version ein großes neues Thema (eines für den Überblick der Hauptversion, keine kleine Anpassung): auch `HIGHLIGHTS.md` unter der kommenden Hauptversion ergänzen oder einen Punkt dort erweitern (Unterversionen sind Schritte zur nächsten: 3.16.x unter `## 3.17`) – höchstens sechs Punkte, je eine Zeile bis 150 Zeichen; diesen Überblick zeigt die Update-Anzeige je Hauptversion vor den einzelnen Versionen (`HighlightsTests`).
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
  nachprüfen (aktuelles Python). Ein anderer Chat war schneller: die eigene Korrektur verwerfen, soweit sie dasselbe behebt.
- **Sperren vor jedem Push nach `main`** – zwei Ebenen, dieselbe Regel: der git-Hook `.githooks/pre-push` (schaltet das
  Lagebild ein; gegen den Stand auf GitHub: `VERSION` höher, keine Changelog-Zeile von `main` verloren) und
  `.claude/hooks/guard.py` vor jedem `git push` (holt `main` selbst: neuester `main` in der eigenen Arbeit, jeder Commit hebt
  `VERSION` als Zahl, behält alle `## X.Y.Z`-Abschnitte und trägt oben seine eigene Version; keine Zeile, die eine der neuesten
  Versionen auf `main` gebracht hat, geht verloren (außer in `HIGHLIGHTS.md`, das bewusst gestrafft wird – Fremdes dort beim Zusammenführen erhalten) – so fiel 3.16.35 auf, das bei richtiger Kette den Code von 3.16.32 zurücksetzte). GitHub prüft die Kette für jeden
  Push (Job „Versionskette“). Abgelehnt: nicht umgehen (`KONTOR_PUSH_OK=1` nur für eine bewusste Ausnahme, etwa einen
  Tippfehler in einem alten Eintrag), sondern holen, daraufsetzen, neu nummerieren. Anlass: 3.16.9 und 66ad67f (3.16.21) –
  `git reset --soft origin/main` auf altem Stand setzte einen alten Baum auf den neuen `main` und löschte fremde Versionen.
  Deshalb `git merge-base --is-ancestor origin/main HEAD` direkt vor dem Versions-Commit, nach dem letzten `git fetch`.
- Lokal beliebig committen; auf GitHub kommt nur Fertiges, als ein Commit je Version – ohne Zweige, direkt auf `main`.
- Direkt vor dem Versions-Commit holen und die eigene Arbeit daraufsetzen (`git pull --rebase origin main`); die Nummer immer
  aus dem frisch geholten `main`; zusammengefasst wird nur, wenn dieser `main` in der eigenen Arbeit steckt (sonst gingen fremde
  Änderungen verloren). Konflikte: beide Seiten lesen und so zusammenführen, dass beide Änderungen erhalten bleiben;
  Fremdes nie verwerfen. Lässt sich ein Konflikt nicht eindeutig auflösen (Unvereinbares, eine Entscheidung steht an): den
  Nutzer fragen, mit Empfehlung. Nach jedem Rebase die betroffenen Tests erneut – auch ohne Konflikt, denn Logikfehler meldet Git nicht.
- War ein anderer Chat schneller (Push abgelehnt): `VERSION` und `CHANGELOG.md` nie zusammenführen, sondern den eigenen Commit
  ohne sie neu aufsetzen, daraufsetzen, testen und mit der nächsten Nummer veröffentlichen. Jede Version bleibt ein Commit;
  die Nummer im letzten Commit auf `main` ist immer die aktuelle.
- Nie Force-Push, `main` nie löschen.

## Was wo gepflegt wird
Jede Änderung pflegt mit, was sie betrifft – jede Sache steht an genau einer Stelle, die anderen verweisen darauf statt sie zu wiederholen:

| Was | Wo | Für wen, wie | Wann |
|---|---|---|---|
| Texte der Oberfläche, Tooltips | `web/i18n.js` (`t()`/`tr()`; Tooltips `h_*` über `hq()`, Sprung in die Hilfe über `HELP_AT`) | Nutzer am Element: ein, zwei Sätze | mit jedem sichtbaren Text |
| Was jede Stelle zeigt | `docs/ui/<seite>.md`, am Element `data-ex="<seite>.<stelle>"` | der Assistent (Kurzerklärung per Rechtsklick, Fragen zur Seite, `search_help`): je Karte, Grafik, Tabelle, Spalte, Zeilenart, Kennzahl, was die Zahl ist – Wert des Zeitraums, Anteil oder Veränderung (wogegen), Zeitraum, Einheit, Vorzeichen, wie gerechnet, wovon sie abhängt; keine Bedienung, keine Anleitung | jede neue oder geänderte Stelle, Zahl oder Berechnung |
| Hilfe | `docs/help.de.md` + `docs/help.en.md` (gleiche Anker) | Nutzer: wie es geht, warum, was es bewirkt, Sicherheit | wenn sich Bedienung oder Verhalten ändert |
| README | `README.md` | Überblick, nur große Themen | neues großes Thema |
| Änderungen | `CHANGELOG.md`, `HIGHLIGHTS.md` (siehe Jede Änderung abschließen) | Nutzer in der Update-Anzeige | jede Version |
| Fahrplan | `ROADMAP.md` | Nutzer und Chats: Erledigtes, Offenes | jede Version, die einen Punkt berührt |
| Regeln, Sicherheit, Aufbau | `CLAUDE.md` | Chats | neue Teile, neue Wege nach außen, neue Regeln |
| Fremdes, das Kontor nutzt | `components.py` (ein Eintrag; die Liste unter Einstellungen → Updates entsteht daraus), `NOTICE` | Nutzer: Name, Version, Lizenz, Herkunft, abgeschirmt ja/nein | jedes neue Modell in `llm_local` (`licence` im Eintrag, wie seine Modellkarte sie nennt – nie geraten), jede Bibliothek, jedes neue fremde Programm |
| Hilfe-Bilder | `tests/screenshots.py` → `docs/img/` | Hilfe und README | nur beim großen Versionssprung |

`docs/ui` (Englisch, nur für den Assistenten; Kontor als Ganzes in `kontor.md`, er steht im Systemtext): je Seite eine Datei, Überschrift
`# <seite> — <Name>`, darunter je Stelle `## <seite>.<stelle> — <Name auf dem Bildschirm>` (Teile `###`, Schlüssel mit Punkten); der
Schlüssel steht wörtlich als `data-ex="…"` am umgebenden Element (nie zusammengesetzt). Kurz und genau, je Stelle höchstens etwa
300 Wörter: jede sichtbare Zahl einzeln („Betrag: Ausgaben der Position im gewählten Zeitraum; Prozent daneben: Veränderung
gegenüber denselben Monaten ein Jahr davor“), Zeilen- und Spaltenarten einer Tabelle, was Farben und Schraffur bedeuten. Der
Rechtsklick gibt dem Assistenten die Stelle und alle Stellen um sie herum (von der Seite abwärts). `tests/test_ui_docs.py` prüft
Schlüssel und Dateien, `test_tour`, dass jede sichtbare Tabelle, Grafik und Karte einer Seite, die der Assistent lesen darf, in
einer beschriebenen Stelle liegt.

## Kleine und große Versionen
- Kleine Versionen (dritte Stelle): zügig vorankommen – Funktionen, Verbesserungen, neue Features im Code; die üblichen Prüfungen.
  Texte der Hilfe (`docs/help.de.md`, `docs/help.en.md`) und des README mit pflegen, wo die Änderung sie betrifft – kurz, nur die
  betroffene Stelle. **Keine** Hilfe-Bilder: die gibt es nur beim großen Versionssprung. Tooltips in `web/i18n.js` gehören zum Code.
- Großer Versionssprung (zweite Stelle, z. B. 3.11.5 → 3.12.0; auf Wunsch des Nutzers oder nach Rückfrage): vorher eine
  Gesamtprüfung mit voller Kraft – die letzten Änderungen final abnehmen, alle Referenzen aktuell, fehlerfrei. Gefundenes direkt
  verbessern, dann in perfekter Form veröffentlichen:
  - Alle Tests, dazu viele Zufallsläufe (`KONTOR_FUZZ_SEEDS=1000`, auch für `test_scenarios`), zusätzlich eigene Testdaten mit Sonderfällen und
    Fehlerfällen; alte Funktionen gezielt nachprüfen, ob ein Update sie beschädigt hat.
  - Jede Seite in hell/dunkel, Mac/iPhone ansehen (`ui-check`); alle Verlinkungen und Sprünge, alle Hilfe-Icons und Tooltips
    gegen den heutigen Stand; Texte de/en vollständig und einheitlich.
  - `README.md` und Hilfe (de/en, gleiche Anker) als Ganzes gegenlesen, Hilfe-Bilder (`tests/screenshots.py`) neu erzeugen.
  - `HIGHLIGHTS.md`: Überblick der neuen Hauptversion (was die Schritte seit der letzten gebracht haben) final straffen.
  - Einheitlichkeit: gleiche Dinge überall gleich gelöst (Bedienung, Farben, Begriffe, Cursor); Überflüssiges entfernen.
  - Sicherheit und Datenschutz erneut prüfen (Agent `reviewer` auf den ganzen Stand seit dem letzten großen Sprung).
  - Gefundenes beheben und sinnvoll optimieren; Änderungen mit Geschmacks- oder Produktfrage vor dem Push mit dem Nutzer klären.

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
- Hilfe: `docs/help.de.md` und `docs/help.en.md` gemeinsam pflegen (gleiche Anker); Texte mit jeder Änderung, die sie betrifft; Bilder mit `tests/screenshots.py` (de/en) aus erfundenen Daten – nur beim großen Versionssprung (zweite Stelle), nie bei kleinen Versionen.
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
- Modelle des Assistenten (`llm_local.CATALOG`, Einstellungen → KI-Assistent): nach Zweck gruppiert (für Zahlen und Dokumente, für kurze Fragen, nur für einfache Fragen – Überschriften ohne die Wörter des Denkaufwands im Chat, damit es nicht wie eine Wahl je Modus wirkt; gewählt wird ein Modell für alles; dazu „Für einen stärkeren Rechner“ – nie empfohlen), je Modell ein ehrlicher Satz, wofür es taugt – ohne Kennzahlen –, dazu Hersteller, Lizenz, Dateigröße, Speicherbedarf und ob es auf diesem Mac gut, knapp oder nicht läuft. „Empfohlen“ nur, was dem Nutzer wirklich etwas bringt: das gründlichste Modell, das gut läuft – richtige Antworten vor Tempo, sonst keines. Was für Zahlen und Dokumente nicht taugt, steht so da; was nicht in den Arbeitsspeicher passt, nennt, was es braucht, und lässt sich nicht laden. Kontor wechselt das gewählte Modell nie von selbst.

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
| `memory.py` | Gedächtnis des Assistenten: Notizen (Dateien, Prüfung, nie Zugangsdaten), Steckbrief, Wortsuche (Formen, Wortteile, Tippfehler; nur Standardbibliothek) und Suche nach Bedeutung (Einbettungen daneben), Sicherung, Export und Import im offenen Format `kontor-memory` (`export_file`, `import_file`, `read_file`), Namen für den Suchfilter – Tests: `test_memory` (beschädigte Datei, Steckbrief in seiner Grenze, Suche und Passendes zur Frage in ihren Grenzen, Suche in gespeicherten Verläufen (`Talks`), kein Werkzeug schreibt, Vergessenes auch aus dem Protokoll und der Unterhaltung, Sicherung, Export und Import (`Carried`: hin und zurück, jede Notiz geprüft, ganz oder gar nicht, Doppelte, Listen von anderswo, fremde und beschädigte Dateien, Grenzen), nur am Mac, nie in der Demo, Liste im Browser) |
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
