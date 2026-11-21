---
name: release
description: Jede Änderung an Kontor abschließen – prüfen (auch mit Python 3.9), ein Commit je Version direkt auf main, GitHub Actions abwarten. Am Ende jeder Änderung verwenden, auch bei kleinen.
---

# Release

1. **Prüfen** (alles muss grün sein, nichts überspringen):
   - `node --check web/app.js && node --check web/i18n.js && node --check web/sw.js`
   - `python3 -m pyflakes *.py tests/*.py .claude/hooks/*.py` und `npx eslint -c .github/eslint.config.mjs web` – keine Funde
     (ESLint einmal je Sitzung: `npm install --no-save --no-package-lock eslint@9 globals`)
   - `python3 -m pytest -q -rs tests` (~2½ min, im Hintergrund laufen lassen). Übersprungenes steht am Ende: „WebKit nicht
     installiert“ heißt, die Safari-Tests prüft erst GitHub – einmal je Sitzung `python3 -m playwright install webkit` versuchen;
     geht es nicht und die Änderung betrifft die Oberfläche, das Verhalten auch in Chrome prüfen.
   - Rechenlogik oder Buchungsregeln geändert: zusätzlich `KONTOR_FUZZ_SEEDS=400 python3 -m pytest -q tests/test_fuzz.py`
   - Python 3.9 (Apples Version auf dem Mac): `TZ=Europe/Berlin ~/py39/bin/python -m pytest -q tests` (~1 min; Browser-Tests
     laufen nur mit dem aktuellen Python). Fehlt `~/py39`, einmal einrichten: `uv python install 3.9 && uv venv -q -p 3.9 ~/py39 &&
     VIRTUAL_ENV=~/py39 uv pip install -q pytest pillow cryptography` (ohne Playwright).
2. **Oberfläche geändert:** Skill `ui-check`. Hilfe (`docs/help.*.md`), README und Hilfe-Bilder (`tests/screenshots.py`)
   **nur beim großen Versionssprung** (zweite Stelle) – bei kleinen Versionen nicht anfassen, auch keine Bilder neu erzeugen.
3. **Unabhängig prüfen** (Rechenlogik, Schreibzugriffe auf MoneyMoney, Sicherheit): Agent `reviewer` auf die Änderung
   ansetzen, Befunde beheben oder begründet verwerfen.
4. **Fahrplan:** in `ROADMAP.md` Erledigtes abhaken bzw. den Stand nachtragen.
5. **Veröffentlichen – ein Commit je Version, direkt auf `main`.** Andere Chats arbeiten parallel (`CLAUDE.md`, „Parallele Chats“):
   1. **Holen und daraufsetzen:** `git pull --rebase origin main` (nicht erst jetzt zum ersten Mal: zu Beginn jeder Aufgabe und
      sobald das Lagebild Neues meldet); Konflikte lösen (beide Änderungen erhalten, Unvereinbares mit
      Empfehlung dem Nutzer vorlegen), danach Tests erneut (beide Python-Versionen).
   2. **Version:** `VERSION` = Stand auf `origin/main`, dritte Stelle +1. Zweite Stelle nur bei erheblichen Änderungen und nur
      nach Rückfrage, vorher die Gesamtprüfung aus `CLAUDE.md` („Großer Versionssprung“). Erste nie. **Changelog:** neuer
      Abschnitt oben in `CHANGELOG.md`, Überschrift `## X.Y.Z (JJJJ-MM-TT HH:MM)` mit `TZ=Europe/Berlin date +"%Y-%m-%d %H:%M"`.
      Deutsch, aus Sicht des Nutzers (was er merkt), keine Technik. Kompakt: je Änderung ein Punkt mit wenigen Stichworten in
      einer Zeile, auf einen Blick lesbar – keine Erklärungen, keine Begründungen.
   3. **Ein Commit:** erst prüfen, dass der frisch geholte `main` in der eigenen Arbeit steckt:
      `git fetch -q origin main && git merge-base --is-ancestor origin/main HEAD` – schlägt das fehl, ist `main` inzwischen
      weiter: zurück zu 1 (das Zusammenfassen auf einen neueren `main` würde dessen Änderungen stillschweigend rückgängig
      machen). Dann eigene Zwischencommits zusammenfassen (`git reset --soft origin/main`), dann
      `git commit -qam "X.Y.Z: <was sich ändert>" -m "<Modell>: <Link dieser Sitzung>"`, etwa
      `-m "Claude Opus 5.5: https://claude.ai/code/session_…"` (englisch, kurz; keine E-Mail, kein `Co-Authored-By`, keine Tags).
   4. **Push:** `git push -q origin HEAD:main`. Abgelehnt – ein anderer Chat war schneller: `VERSION` und `CHANGELOG.md` nie
      zusammenführen, sondern den eigenen Commit ohne sie neu aufsetzen – Changelog-Punkte vorher merken, dann
      `git reset -q --soft HEAD~1 && git checkout HEAD -- VERSION CHANGELOG.md && git commit -qm wip` – und zurück zu 1
      (die nächste Nummer ergibt sich dort von selbst).
   5. **GitHub Actions für genau diesen Commit abwarten:**
      `gh api "repos/stecrz/Kontor/actions/runs?head_sha=$(git rev-parse HEAD)" --jq '.workflow_runs[0] | [.status, .conclusion]'`
      (ein paar Minuten). Rot: `gh run view <id> --log-failed | tail -60` zeigt, was. Eigener Fehler (etwa WebKit oder
      Schriften, die es lokal nicht gibt): sofort als nächste Version beheben und dem Nutzer in einem Satz Bescheid geben.
      War schon die Version davor rot und es sind dieselben Fehler: geerbt – nicht reparieren, das macht der Chat jener
      Version (`CLAUDE.md`, „Rot auf GitHub“); dem Nutzer in einem Satz sagen, dass der eigene Teil grün ist.
   Kein Force-Push, keine Zweige. Nach dem Push nichts nachschieben – eine Korrektur ist eine neue Version.
6. **Nur Regeln, Tests oder CI geändert:** mit der nächsten Version mitnehmen; muss es sofort für die anderen Chats gelten,
   eigene Version mit Changelog-Punkt „Entwicklung: …“.
7. **Antwort an den Nutzer:** auf Deutsch, kurz – was sich für ihn ändert und die Version. Keine Aufzählung der Arbeitsschritte.
   Den Mac aktualisiert der Nutzer selbst (Einstellungen → Updates): nicht darauf zugreifen und nicht erwähnen.
