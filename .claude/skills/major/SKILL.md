---
name: major
description: Großen Versionssprung von Kontor vorbereiten und veröffentlichen (zweite Stelle, z. B. 3.17.x → 3.18.0) – nur auf Wunsch des Nutzers oder nach seiner Zustimmung. Gesamtprüfung mit voller Kraft, Nachpflege von allem, was kleine Versionen bewusst auslassen, dann in perfekter Form veröffentlichen.
---

# Großer Versionssprung

Kleine Versionen lassen bewusst aus, was nur hier geschieht (`CLAUDE.md`, „Prüfen – zwei Stufen“). Ziel: alles seit dem letzten
Sprung final abgenommen, alle Referenzen aktuell, fehlerfrei. Gefundenes direkt verbessern; Fragen des Geschmacks oder des
Produkts vor dem Veröffentlichen mit dem Nutzer klären.

Ausgangspunkt: der Commit des letzten Sprungs, `L=$(git log --format=%H --grep='^[0-9]*\.[0-9]*\.0:' -1 origin/main)` (Betreff
`X.Y.0: …`; im flachen Klon vorher `git fetch --depth=1000 origin main`). Was sich seitdem geändert hat: `git diff --stat $L origin/main`,
`CHANGELOG.md` bis dorthin.

1. **Tests.** Der Lauf der neuesten Version auf GitHub und der letzte Nachtlauf grün (Lagebild bzw. `gh run list -R stecrz/Kontor -L 3`)
   – sie prüfen alles; lokal nicht noch einmal alles. Zusätzlich: eigene Testdaten mit Sonder- und Fehlerfällen für die großen
   Themen seit dem letzten Sprung, alte Funktionen gezielt nachprüfen, ob ein Update sie beschädigt hat; was fehlt, als Test
   ergänzen. Viele Zufallsläufe, wo Rechenlogik geändert wurde (`KONTOR_FUZZ_SEEDS=1000`, auch `test_scenarios`).
2. **Unabhängig prüfen – mit voller Kraft** (Nutzer, 2026-11-24: beim großen Sprung Claude maximal ausreizen, nichts übersehen):
   alles seit `$L` in Bereiche schneiden (etwa Rechenlogik `rules/model/report/core`, Assistent und Gedächtnis, Oberfläche
   `web/`, Sicherheit und Zugang, Updates und eigenes Python, Tests) und je Bereich einen Agent `reviewer` mit eigenem, frischem
   Kontext starten – nebeneinander. Jeder liest jede seit `$L` geänderte Datei seines Bereichs **vollständig** (große Dateien in
   aufeinanderfolgenden Abschnitten von 400 Zeilen, bis zum Ende – die Lese-Sperre verlangt nur Abschnitte, nicht Auslassungen),
   dazu Aufrufer und Tests der geänderten Funktionen, und prüft Sicherheit, Rechenlogik (Sonderfälle, Cent, Summen), Schreibzugriffe,
   Texte. Ein großer Kontext je Prüfer statt eines riesigen für alles: so liest jeder genau und nichts geht in der Masse unter.
   Befunde aller Prüfer sammeln, beheben, dann je betroffenem Bereich ein zweiter Prüfer auf die Korrekturen.
3. **Ansehen:** jede Seite hell/dunkel, Mac/iPhone (Skill `ui-check`); alle Verlinkungen und Sprünge, Hilfe-Icons und Tooltips gegen
   den heutigen Stand; Einheitlichkeit (gleiche Dinge überall gleich gelöst: Bedienung, Farben, Begriffe, Cursor), Überflüssiges
   entfernen.
4. **Nachpflegen:**
   - Englische Hilfe: jeder seit `$L` geänderte Abschnitt (`git diff $L origin/main -- docs/help.de.md` nennt sie) vollständig
     übertragen, auch die Kurzfassungen neuer Abschnitte; Hilfe de/en als Ganzes gegenlesen (gleiche Anker).
   - `README.md` als Ganzes gegen den Stand.
   - Bilder für Hilfe und README neu: `tests/screenshots.py` (de/en, erfundene Daten).
   - `HIGHLIGHTS.md`: Überblick der neuen Hauptversion aus dem Changelog seit `$L` (höchstens sechs Punkte, je eine Zeile bis 150
     Zeichen, keine „Entwicklung“; `HighlightsTests`).
   - Texte de/en vollständig und einheitlich; `ROADMAP.md`: Erledigtes gestrichen, Offenes aktuell.
5. **Veröffentlichen:** `python3 .claude/tools/release.py "<…>" "<Punkte>" --version X.Y.0 --wait` – hier auf GitHub warten; rot:
   sofort beheben (nächste Version).
