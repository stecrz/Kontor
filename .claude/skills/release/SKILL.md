---
name: release
description: Jede Änderung an Kontor abschließen – betroffene Tests prüfen (Python 3.9 nur für den Starter), ein Commit je Version direkt auf main, GitHub Actions abwarten. Am Ende jeder Änderung verwenden, auch bei kleinen.
---

# Release

1. **Prüfen** (alles muss grün sein, nichts überspringen):
   - `node --check web/app.js && node --check web/i18n.js && node --check web/sw.js`
   - `python3 -m pyflakes *.py tests/*.py .claude/hooks/*.py` und `npx eslint -c .github/eslint.config.mjs web` – keine Funde
     (ESLint einmal je Sitzung: `npm install --no-save --no-package-lock eslint@9 globals`)
   - Betroffene Tests, Ausgabe in eine Datei, nur das Ende lesen: `T=$(python3 tests/affected.py); python3 -m pytest -q $T > /tmp/t.log 2>&1; tail -3 /tmp/t.log`.
     Python 3.9 nur für den Starter (Apples Python startet nur `kontor.py` bis `pyboot.ready()` und `pyboot.py`; Nutzer, 2026-11-23), wenn diese
     berührt sind: `TZ=Europe/Berlin ~/py39/bin/python -m pytest -q tests/test_python.py`. Fehlt `~/py39`: `uv python install 3.9 && uv venv -q -p 3.9 ~/py39 &&
     VIRTUAL_ENV=~/py39 uv pip install -q pytest cryptography`. Die volle Prüfung macht GitHub (`CLAUDE.md`, Sparsam arbeiten) – lokal alles nur vor einem
     großen Versionssprung.
   - Rechenlogik oder Buchungsregeln geändert: zusätzlich `KONTOR_FUZZ_SEEDS=400 python3 -m pytest -q tests/test_fuzz.py`
2. **Mitpflegen** – GitHub ist das einzige Gedächtnis (`CLAUDE.md`, Arbeitsweise): ein neuer Chat kennt nur das Repo. Jede
   Entscheidung des Nutzers aus diesem Chat (`ROADMAP.md`, „Entschieden“/„Offen“), jede geänderte Regel oder jeder geänderte
   Ablauf (`CLAUDE.md`, Skills, Hooks) und jedes geänderte Verhalten gehört in diese Version – ohne Erinnerung durch den Nutzer.
   Frage vor dem Commit: Würde ein neuer Chat mit nur diesem Repo richtig weiterarbeiten? Nichts Persönliches (öffentlich).
   Nach der Tabelle „Was wo gepflegt wird“ in `CLAUDE.md`: Texte und Tooltips (`web/i18n.js`), was jede neue oder
   geänderte Stelle zeigt (`docs/ui/<seite>.md` + `data-ex`, für den Assistenten), Hilfe (`docs/help.de.md` und `docs/help.en.md`,
   gleiche Anker) und README, wo die Änderung sie betrifft. **Oberfläche geändert:** Skill `ui-check`. Hilfe-Bilder (`tests/screenshots.py`) **nur beim großen Versionssprung**
   (zweite Stelle) – bei kleinen Versionen keine Bilder neu erzeugen.
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
      einer Zeile, auf einen Blick lesbar – keine Erklärungen, keine Begründungen. Vorn der Bezug mit Doppelpunkt
      („KI-Assistent: …“; nur Regeln/Tests/CI: „Entwicklung: …“ – in der Update-Anzeige ausgeblendet).
      **Großes neues Thema** (nicht bei kleinen Anpassungen): dazu `HIGHLIGHTS.md` – Überblick der kommenden Hauptversion
      (3.16.x unter `## 3.17`), höchstens sechs Punkte, je eine Zeile; Gleiches in einen Punkt.
   3. **Ein Commit:** erst prüfen, dass der frisch geholte `main` in der eigenen Arbeit steckt:
      `git fetch -q origin main && git merge-base --is-ancestor origin/main HEAD` – schlägt das fehl, ist `main` inzwischen
      weiter: zurück zu 1 (das Zusammenfassen auf einen neueren `main` würde dessen Änderungen stillschweigend rückgängig
      machen; so entstand 66ad67f: `git reset --soft origin/main` auf altem Stand überschrieb zwei fremde Versionen). Diese
      Prüfung direkt vor dem Versions-Commit, nach dem letzten `git fetch`. Dann eigene Zwischencommits zusammenfassen
      (`git reset --soft origin/main`), dann
      `git commit -qam "X.Y.Z: <was sich ändert>" -m "<Modell>: <Link dieser Sitzung>"`, etwa
      `-m "Claude Opus 5.5: https://claude.ai/code/session_…"` (englisch, kurz; keine E-Mail, kein `Co-Authored-By`, keine Tags).
   4. **Push:** `git push -q origin HEAD:main`. Davor prüfen die Sperren von selbst (`.claude/hooks/guard.py`, dazu der git-Hook `.githooks/pre-push`): neuester `main`
      in der eigenen Arbeit, jeder Commit darüber hebt `VERSION` (als Zahl), behält alle `## X.Y.Z`-Abschnitte des Changelogs
      und trägt die eigene Version oben. Gesperrt: nicht umgehen – meist ist `main` weiter (zurück zu 1) oder ein Zwischencommit
      noch nicht zusammengefasst (3). GitHub prüft dasselbe (Job „Versionskette“).
      Abgelehnt – ein anderer Chat war schneller: `VERSION` und `CHANGELOG.md` nie
      zusammenführen, sondern den eigenen Commit ohne sie neu aufsetzen – Changelog-Punkte vorher merken, dann
      `git reset -q --soft HEAD~1 && git checkout HEAD -- VERSION CHANGELOG.md && git commit -qm wip` – und zurück zu 1
      (die nächste Nummer ergibt sich dort von selbst).
   5. **GitHub Actions für genau diesen Commit abwarten:**
      in **einem** blockierenden Befehl (Zeitgrenze 600000 ms), nie mit `sleep`-Schleifen:
      `gh run watch $(gh run list -R stecrz/Kontor -c $(git rev-parse HEAD) -L1 --json databaseId -q '.[0].databaseId') -R stecrz/Kontor --exit-status > /tmp/ci.log 2>&1; tail -3 /tmp/ci.log`
      (noch kein Lauf da: einmal 20 s warten, dann erneut). Rot: `gh run view <id> --log-failed | grep -E "FAILED|Error" | head -20`. Eigener Fehler (etwa WebKit oder
      Schriften, die es lokal nicht gibt): sofort als nächste Version beheben und dem Nutzer in einem Satz Bescheid geben.
      War schon die Version davor rot und es sind dieselben Fehler: geerbt – nicht reparieren, das macht der Chat jener
      Version (`CLAUDE.md`, „Rot auf GitHub“); dem Nutzer in einem Satz sagen, dass der eigene Teil grün ist.
   Kein Force-Push, keine Zweige. Nach dem Push nichts nachschieben – eine Korrektur ist eine neue Version.
6. **Nur Regeln, Tests oder CI geändert:** mit der nächsten Version mitnehmen; muss es sofort für die anderen Chats gelten,
   eigene Version mit Changelog-Punkt „Entwicklung: …“.
7. **Antwort an den Nutzer:** auf Deutsch, kurz – was sich für ihn ändert und die Version. Keine Aufzählung der Arbeitsschritte.
   Den Mac aktualisiert der Nutzer selbst (Einstellungen → Updates): nicht darauf zugreifen und nicht erwähnen.
