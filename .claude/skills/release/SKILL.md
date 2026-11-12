---
name: release
description: Jede Änderung an Kontor abschließen – prüfen, Version, Changelog, Commit, Push, Mac aktualisieren. Am Ende jeder Änderung verwenden, auch bei kleinen.
---

# Release

1. **Prüfen** (alles muss grün sein, nichts überspringen):
   - `node --check web/app.js && node --check web/i18n.js && node --check web/sw.js`
   - `python3 -m pyflakes *.py` – keine neuen Warnungen
   - `python3 -m pytest -q tests` (~2½ min, im Hintergrund laufen lassen)
   - Rechenlogik oder Buchungsregeln geändert: zusätzlich `KONTOR_FUZZ_SEEDS=400 python3 -m pytest -q tests/test_fuzz.py`
2. **Oberfläche oder Hilfe geändert:** Skill `ui-check`; Hilfe `docs/help.de.md` und `docs/help.en.md` mit gleichen Ankern;
   Bilder neu: `python3 tests/screenshots.py - de` und `python3 tests/screenshots.py - en`.
3. **Unabhängig prüfen** (Rechenlogik, Schreibzugriffe auf MoneyMoney, Sicherheit): Agent `reviewer` auf die Änderung
   ansetzen, Befunde beheben oder begründet verwerfen.
4. **Version:** `VERSION` dritte Stelle +1. Zweite Stelle nur bei erheblichen Änderungen und nur nach Rückfrage. Erste nie.
5. **Changelog:** neuer Abschnitt oben in `CHANGELOG.md`, Überschrift `## X.Y.Z (JJJJ-MM-TT HH:MM)` mit
   `TZ=Europe/Berlin date +"%Y-%m-%d %H:%M"`. Deutsch, kurz, aus Sicht des Nutzers (was er merkt), keine Technik.
6. **Fahrplan:** in `ROADMAP.md` Erledigtes abhaken bzw. den Stand nachtragen.
7. **Commit und Push:** englische Commit-Nachricht `X.Y.Z: <was sich ändert>`, am Ende die Zuordnungszeilen aus der
   aktuellen Systemerinnerung der Sitzung. `git push -q origin HEAD:main`. Keine Tags, kein Force-Push.
8. **Mac aktualisieren** (über die Verbindung zum Mac, falls vorhanden):
   `cd "$HOME/mnt/Kontor" && git fetch -q https://github.com/stecrz/Kontor.git main && git reset -q --hard FETCH_HEAD && git update-ref refs/remotes/origin/main FETCH_HEAD && cat VERSION`
   Nicht erreichbar: dem Nutzer sagen, dass er das Update unter „Updates“ in Kontor installieren kann.
9. **Antwort an den Nutzer:** auf Deutsch, kurz – was sich für ihn ändert, Version, ob der Mac aktuell ist. Keine Aufzählung der Arbeitsschritte.
