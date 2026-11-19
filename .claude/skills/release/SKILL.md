---
name: release
description: Jede Änderung an Kontor abschließen – prüfen, hochladen, GitHub Actions abwarten, erst dann Version und Changelog. Am Ende jeder Änderung verwenden, auch bei kleinen.
---

# Release

1. **Prüfen** (alles muss grün sein, nichts überspringen):
   - `node --check web/app.js && node --check web/i18n.js && node --check web/sw.js`
   - `python3 -m pyflakes *.py` – keine neuen Warnungen
   - `python3 -m pytest -q tests` (~2½ min, im Hintergrund laufen lassen)
   - Rechenlogik oder Buchungsregeln geändert: zusätzlich `KONTOR_FUZZ_SEEDS=400 python3 -m pytest -q tests/test_fuzz.py`
2. **Oberfläche geändert:** Skill `ui-check`. Hilfe (`docs/help.*.md`), README und Hilfe-Bilder (`tests/screenshots.py`)
   **nur beim großen Versionssprung** (zweite Stelle) – bei kleinen Versionen nicht anfassen, auch keine Bilder neu erzeugen.
3. **Unabhängig prüfen** (Rechenlogik, Schreibzugriffe auf MoneyMoney, Sicherheit): Agent `reviewer` auf die Änderung
   ansetzen, Befunde beheben oder begründet verwerfen.
4. **Fahrplan:** in `ROADMAP.md` Erledigtes abhaken bzw. den Stand nachtragen.
5. **Erst alles andere hochladen** – noch ohne `VERSION` und `CHANGELOG.md`: englische Commit-Nachricht
   `Prepare X.Y.Z: <was sich ändert>`, am Ende nur `Co-Authored-By: …` (kein Sitzungslink). `git push -q origin HEAD:main`.
   Keine Tags, kein Force-Push. **GitHub Actions abwarten:**
   `gh api "repos/stecrz/Kontor/actions/runs?per_page=1" --jq '.workflow_runs[0] | [.head_sha[0:7], .status, .conclusion]'`
   (ein paar Minuten). Schlägt der Lauf fehl: beheben, erneut pushen, wieder abwarten – lokal grün heißt nicht überall grün
   (andere Schriften, Python 3.9).
6. **Dann die Version, als letzter Commit:** `VERSION` dritte Stelle +1. Zweite Stelle nur bei erheblichen Änderungen und nur
   nach Rückfrage. Erste nie. Großer Sprung (zweite Stelle): vorher die Gesamtprüfung aus `CLAUDE.md` („Großer
   Versionssprung“) vollständig durchführen. Dazu **Changelog:** neuer Abschnitt oben in `CHANGELOG.md`, Überschrift
   `## X.Y.Z (JJJJ-MM-TT HH:MM)` mit `TZ=Europe/Berlin date +"%Y-%m-%d %H:%M"`. Deutsch, aus Sicht des Nutzers (was er merkt),
   keine Technik. Kompakt: je Änderung ein Punkt mit wenigen Stichworten in einer Zeile, auf einen Blick lesbar – keine
   Erklärungen, keine Begründungen. Commit `X.Y.Z: <was sich ändert>`, pushen. Die Update-Prüfung liest `VERSION` auf `main`:
   Der Nutzer sieht das Update erst, wenn alles andere schon oben ist. Nach diesem Commit nichts mehr nachschieben – eine
   spätere Korrektur ist ein neues Release.
7. **Antwort an den Nutzer:** auf Deutsch, kurz – was sich für ihn ändert und die Version. Keine Aufzählung der Arbeitsschritte.
   Den Mac aktualisiert der Nutzer selbst (Einstellungen → Updates): nicht darauf zugreifen und nicht erwähnen.
