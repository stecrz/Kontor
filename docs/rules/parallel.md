# Parallele Chats im Einzelnen

Teil von `CLAUDE.md` (Parallele Chats) – lesen bei einem Konflikt, einer Sperre vor dem Push oder wenn `release.py` nicht geht.

## Wie eine Version auf `main` kommt
`.claude/tools/release.py` (Skill `release`) macht es in einem Aufruf: eigene Arbeit zu einem Commit auf dem `main`, auf dem sie
entstand, holen, daraufsetzen (`rebase`), prüfen, Nummer aus dem frisch geholten `main` + 1, Changelog-Abschnitt oben, Sperre
(`guard.push_check`), Push. Abgelehnt, weil ein anderer Chat schneller war: `VERSION` und `CHANGELOG.md` verworfen, neu
daraufgesetzt, wieder geprüft, nächste Nummer. `VERSION` und `CHANGELOG.md` werden nie zusammengeführt – sie entstehen neu.

Von Hand nur, wenn das Skript selbst kaputt ist – dieselben Schritte: `git pull --rebase origin main`; betroffene Tests; `VERSION`
= `origin/main` + 1; Changelog-Abschnitt oben; direkt vor dem Versions-Commit, nach dem letzten `git fetch`:
`git merge-base --is-ancestor origin/main HEAD` (sonst zurück zum Holen); eigene Zwischencommits zusammenfassen
(`git reset --soft origin/main` nur dann!), ein Commit `X.Y.Z: …` mit Modell und Sitzungslink, `git push origin HEAD:main`.

## Sperren und warum
- `.claude/hooks/guard.py` vor jedem `git push` aus dem Chat und in `release.py`: neuester `main` in der eigenen Arbeit, jeder Commit
  darüber hebt `VERSION` als Zahl, behält alle `## X.Y.Z`-Abschnitte und trägt oben seine eigene Version; keine Zeile, die eine
  der neuesten Versionen auf `main` gebracht hat, geht verloren (außer in `HIGHLIGHTS.md`, das bewusst gestrafft wird – Fremdes
  dort beim Zusammenführen erhalten). `.githooks/pre-push` prüft dasselbe gegen GitHub (`VERSION` höher, keine Changelog-Zeile
  verloren), GitHub den ganzen Push (Job „Versionskette“).
- Anlass: 3.16.9 und 66ad67f (3.16.21) – `git reset --soft origin/main` auf altem Stand setzte einen alten Baum auf den neuen
  `main` und löschte fremde Versionen; 3.16.35 setzte bei richtiger Kette den Code von 3.16.32 zurück.
- Abgelehnt: nie umgehen, sondern holen, daraufsetzen, neu nummerieren. `KONTOR_PUSH_OK=1` nur für eine bewusste Ausnahme (etwa
  ein Tippfehler in einem alten Changelog-Eintrag).

## Konflikte
Beide Seiten lesen und so zusammenführen, dass beide Änderungen erhalten bleiben; Fremdes nie verwerfen. Lässt sich ein Konflikt
nicht eindeutig auflösen (Unvereinbares, eine Entscheidung steht an): den Nutzer fragen, mit Empfehlung. Nach jedem Daraufsetzen
prüft `release.py` erneut – auch ohne Konflikt, denn Logikfehler meldet Git nicht.

## Rot auf GitHub
Der Chat, der veröffentlicht, wartet nicht auf GitHub (Nutzer, 2026-11-24: er sieht selbst nach; Warten kostet Zeit und Credits).
Das Lagebild meldet einen roten Lauf jedem Chat einmal: der nächste behebt ihn zuerst, als eigene Version mit „fix ci“ (eine
Version) bzw. „fix nightly“ (Nachtlauf) im Betreff – daran erkennt das Lagebild der anderen, dass es erledigt ist. Ein anderer war
schneller: die eigene Korrektur verwerfen, soweit sie dasselbe behebt. Nachtlauf: ein neuer Fall (Nummer ab 1.000.000) kommt nach
der Korrektur in `FOUND` (`tests/fixtures.py`); nachprüfen mit `KONTOR_FUZZ_SEEDS=1000` und dem Fall.
