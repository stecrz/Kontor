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
5. **Erst alles andere hochladen** – noch ohne `VERSION` und `CHANGELOG.md`. Andere Chats arbeiten parallel (`CLAUDE.md`,
   „Parallele Chats“):
   - Holen und Release-Sperre prüfen: `git fetch -q --depth=50 origin main && git log --format='%h %s'
     $(git log -1 --format=%H origin/main -- VERSION)..origin/main | grep ' Prepare '`. Ein fremder `Prepare`-Commit:
     warten, alle 2–3 Minuten erneut prüfen, bis dessen Version oben ist.
   - Eigene Commits daraufsetzen (`git pull --rebase origin main`), Konflikte lösen, Tests erneut.
   - Englische Commit-Nachricht `Prepare X.Y.Z: <was sich ändert>` (X.Y.Z = `VERSION` auf dem frisch geholten `main` +1), am
     Ende nur `Co-Authored-By: …` (kein Sitzungslink). `git push -q origin HEAD:main`; abgelehnt → zurück zum Holen. Keine
     Tags, kein Force-Push.
   - **GitHub Actions für genau diesen Commit abwarten:**
     `gh api "repos/stecrz/Kontor/actions/runs?head_sha=$(git rev-parse HEAD)" --jq '.workflow_runs[0] | [.status, .conclusion]'`
     (ein paar Minuten). Schlägt der Lauf fehl: beheben, erneut pushen, wieder abwarten – lokal grün heißt nicht überall grün
     (andere Schriften, Python 3.9).
6. **Dann die Version, als letzter Commit:** erneut holen; `VERSION` auf `main` dritte Stelle +1. Zweite Stelle nur bei
   erheblichen Änderungen und nur nach Rückfrage. Erste nie. Push abgelehnt → holen und rebasen; Konflikt in `VERSION` oder
   `CHANGELOG.md`: `git rebase --abort && git reset --hard origin/main` (der Code ist schon oben) und den Versions-Commit neu
   erstellen. Großer Sprung (zweite Stelle): vorher die Gesamtprüfung aus `CLAUDE.md` („Großer
   Versionssprung“) vollständig durchführen. Dazu **Changelog:** neuer Abschnitt oben in `CHANGELOG.md`, Überschrift
   `## X.Y.Z (JJJJ-MM-TT HH:MM)` mit `TZ=Europe/Berlin date +"%Y-%m-%d %H:%M"`. Deutsch, aus Sicht des Nutzers (was er merkt),
   keine Technik. Kompakt: je Änderung ein Punkt mit wenigen Stichworten in einer Zeile, auf einen Blick lesbar – keine
   Erklärungen, keine Begründungen. Commit `X.Y.Z: <was sich ändert>`, pushen. Die Update-Prüfung liest `VERSION` auf `main`:
   Der Nutzer sieht das Update erst, wenn alles andere schon oben ist. Nach diesem Commit nichts mehr nachschieben – eine
   spätere Korrektur ist ein neues Release.
7. **Antwort an den Nutzer:** auf Deutsch, kurz – was sich für ihn ändert und die Version. Keine Aufzählung der Arbeitsschritte.
   Den Mac aktualisiert der Nutzer selbst (Einstellungen → Updates): nicht darauf zugreifen und nicht erwähnen.
