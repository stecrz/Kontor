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

## Nur `main` auf GitHub
Die Cloud-Sitzung legt je Chat einen Zweig `claude/<name>` an und nennt ihn als Push-Ziel. Für Kontor gilt das nicht: der Zweig
bleibt lokal, veröffentlicht wird nur über `release.py` auf `main` (`guard.py` sperrt `git push … claude/…`). Anlass (Nutzer,
2026-11-24): ein Chat hatte seinen Zweig zusätzlich gepusht, ein alter CI-Testzweig lag noch da – auf GitHub braucht es nur `main`.
Einen übrig gebliebenen Zweig löschen (`git push origin --delete <zweig>`; die Versionsprüfung lässt das durch, `main` nie) erst,
wenn `git log origin/main..origin/<zweig>` leer ist oder sein Inhalt nachweislich in `main` steckt.

## Sperren und warum
- `.claude/hooks/guard.py` vor jedem `git push` aus dem Chat und in `release.py`: neuester `main` in der eigenen Arbeit, jeder Commit
  darüber hebt `VERSION` als Zahl, behält alle `## X.Y.Z`-Abschnitte und trägt oben seine eigene Version; keine Zeile, die eine
  der neuesten Versionen auf `main` gebracht hat, geht verloren (außer in `HIGHLIGHTS.md`, das bewusst gestrafft wird – Fremdes
  dort beim Zusammenführen erhalten). Maßgeblich ist die Herkunft: `release.py` merkt sich den `main`, auf dem die eigene Arbeit
  entstand (`.git/kontor-seen`, auch über einen Konflikt-Halt hinweg). Zeilen von Versionen, die schon darin lagen, darf die Arbeit
  ändern – Git trägt die Änderung per Dreiwege-Merge auf den neuen `main` und meldet einen Konflikt, wo eine andere Version dieselbe
  Stelle geändert hat; sie werden nur genannt („Bewusst geändert“). Fehlen Zeilen einer Version, die erst danach kam, sperrt es:
  beim Lösen des Konflikts verloren oder ein alter Baum. Ein Push von Hand kennt den Ausgangsstand nicht und sperrt jede Zeile.
- `git reset` (soft oder gemischt) auf einen Stand außerhalb der eigenen Geschichte ist gesperrt (`guard.reset_check`): er setzt
  die eigenen Dateien unter einen fremden Stand, und der gemerkte Ausgangsstand stimmte nicht mehr. Eigene Commits zusammenfassen
  (Ziel unterhalb von `HEAD`), Austragen aus dem Index und `--hard`/`--keep`/`--merge` dürfen. `.githooks/pre-push` prüft dasselbe gegen GitHub (`VERSION` höher, keine Changelog-Zeile
  verloren), GitHub den ganzen Push (Job „Versionskette“).
- Anlass: 3.16.9 und 66ad67f (3.16.21) – `git reset --soft origin/main` auf altem Stand setzte einen alten Baum auf den neuen
  `main` und löschte fremde Versionen; 3.16.35 setzte bei richtiger Kette den Code von 3.16.32 zurück.
- Anlass der Herkunft (Nutzer, 2026-11-24): 3.17.46 änderte bewusst die Karte, die 3.17.38–3.17.41 gebaut hatten – die alte Sperre
  hielt das für einen alten Baum, weil sie jede Zeile der letzten acht Versionen zählte.
- Fein statt zeilenweise (Nutzer, 2026-11-24, nach 3.17.65): Eine Zeile gilt nur als verloren, wenn fehlt, was die fremde Version in
  sie geschrieben hat – ihre hinzugefügten oder geänderten Wörter samt Wörtern drumherum (mindestens 12 Zeichen, `_added_parts`), eine
  neue Zeile ganz. Wer einen langen Absatz zusammenführt, den beide geändert haben, behält den fremden Teil und wird nicht gesperrt;
  ein zurückgedrehter Wert (`= 45` → `= 30`) oder ein weggelassener Satz sperrt weiter.
- Abgelehnt: nie umgehen, sondern holen, daraufsetzen, neu nummerieren. `KONTOR_PUSH_OK=1` nur für zwei Ausnahmen: ein Tippfehler in
  einem alten Changelog-Eintrag (`.githooks/pre-push`), oder der Nutzer hat im Chat zugestimmt, dass die eigene Änderung genau diese
  fremden Zeilen ersetzt – vorher die gemeldeten Zeilen mit Empfehlung vorlegen, nie nach eigenem Abwägen (Nutzer, 2026-11-24: es soll
  nicht zu Überschreibungen kommen; 3.17.65 ging so durch, obwohl nichts verloren war – die Sperre war zu grob).

## Konflikte
`release.py` nennt je Datei die neuere Version, die dieselbe Stelle geändert hat, und den eigenen Ausgangsstand. Zwischen
`<<<<<<< HEAD` und `=======` steht der fremde Teil – der neuere, schon veröffentlichte Stand –, bis `>>>>>>> … (wip)` der eigene,
der ihn nicht kannte. Beide Seiten lesen und so zusammenführen, dass beide Absichten erhalten bleiben; Fremdes nie verwerfen. Lässt sich ein Konflikt
nicht eindeutig auflösen (Unvereinbares, eine Entscheidung steht an): den Nutzer fragen, mit Empfehlung. Nach jedem Daraufsetzen
prüft `release.py` erneut – auch ohne Konflikt, denn Logikfehler meldet Git nicht.

## Rot auf GitHub
Der Chat, der veröffentlicht, wartet nicht auf GitHub (Nutzer, 2026-11-24: er sieht selbst nach; Warten kostet Zeit und Credits).
Das Lagebild meldet einen roten Lauf jedem Chat einmal: der nächste behebt ihn zuerst, als eigene Version mit „fix ci“ (eine
Version) bzw. „fix nightly“ (Nachtlauf) im Betreff – daran erkennt das Lagebild der anderen, dass es erledigt ist. Ein anderer war
schneller: die eigene Korrektur verwerfen, soweit sie dasselbe behebt. Nachtlauf: ein neuer Fall (Nummer ab 1.000.000) kommt nach
der Korrektur in `FOUND` (`tests/fixtures.py`); nachprüfen mit `KONTOR_FUZZ_SEEDS=1000` und dem Fall.
