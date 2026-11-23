# Oberfläche im Einzelnen

Teil von `CLAUDE.md` (Oberfläche, Was wo gepflegt wird) – lesen, wenn man `docs/ui`, die Modellauswahl oder Browser-Tests ändert.

## docs/ui – was jede Stelle zeigt
`docs/ui` (Englisch, nur für den Assistenten; Kontor als Ganzes in `kontor.md`, er steht im Systemtext): je Seite eine Datei, Überschrift
`# <seite> — <Name>`, darunter je Stelle `## <seite>.<stelle> — <Name auf dem Bildschirm>` (Teile `###`, Schlüssel mit Punkten); der
Schlüssel steht wörtlich als `data-ex="…"` am umgebenden Element (nie zusammengesetzt). Je Karte, Grafik, Tabelle, Spalte, Zeilenart,
Kennzahl: was die Zahl ist – Wert des Zeitraums, Anteil oder Veränderung (wogegen), Zeitraum, Einheit, Vorzeichen, wie gerechnet,
wovon sie abhängt; keine Bedienung, keine Anleitung. Kurz und genau, je Stelle höchstens etwa 300 Wörter: jede sichtbare Zahl einzeln
(„Betrag: Ausgaben der Position im gewählten Zeitraum; Prozent daneben: Veränderung gegenüber denselben Monaten ein Jahr davor“),
Zeilen- und Spaltenarten einer Tabelle, was Farben und Schraffur bedeuten. Der Rechtsklick gibt dem Assistenten die Stelle und alle
Stellen um sie herum (von der Seite abwärts). `tests/test_ui_docs.py` prüft Schlüssel und Dateien, `test_tour`, dass jede sichtbare
Tabelle, Grafik und Karte einer Seite, die der Assistent lesen darf, in einer beschriebenen Stelle liegt.

## Modelle des Assistenten
`llm_local.CATALOG`, Einstellungen → KI-Assistent: nach Zweck gruppiert (für Zahlen und Dokumente, für kurze Fragen, nur für einfache
Fragen – Überschriften ohne die Wörter des Denkaufwands im Chat, damit es nicht wie eine Wahl je Modus wirkt; gewählt wird ein Modell
für alles; dazu „Für einen stärkeren Rechner“ – nie empfohlen), je Modell ein ehrlicher Satz, wofür es taugt – ohne Kennzahlen –,
dazu Hersteller, Lizenz, Dateigröße, Speicherbedarf und ob es auf diesem Mac gut, knapp oder nicht läuft. „Empfohlen“ nur, was dem
Nutzer wirklich etwas bringt: das gründlichste Modell, das gut läuft – richtige Antworten vor Tempo, sonst keines. Was für Zahlen und
Dokumente nicht taugt, steht so da; was nicht in den Arbeitsspeicher passt, nennt, was es braucht, und lässt sich nicht laden. Kontor
wechselt das gewählte Modell nie von selbst.

## Browser-Tests
Neue Browser-Tests warten auf einen Zustand (`until(…)`, `wait_for_function`), nie eine feste Zeit, und vergleichen Maße miteinander,
nie mit festen Pixeln oder Schriftbreiten. GitHub prüft, was es lokal nicht gibt – Safari-Engine (WebKit), andere Schriften,
langsamere Rechner; lokal läuft nur Chrome, und `release.py` lässt Browser-Tests weg (sie laufen auf GitHub) außer denen, die
`--tests` nennt. Ansehen: `python3 tests/preview.py <ordner> '#route'` (hell/dunkel, Mac/iPhone; `--js` z. B. für ganze Tabellen) –
Skill `ui-check`.
