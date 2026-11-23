# Prüfsatz für den KI-Assistenten

Ein Werkzeug für die Entwicklung – kein Teil von Kontor, nichts im Programm startet es. Es stellt dem Assistenten 73 Aufgaben
auf Deutsch, so wie du sie in sein Fenster tippen würdest, und bewertet die Antworten. So zeigt sich, ob eine Änderung an
Kontor, ein anderes Modell oder eine andere Einstellung die Antworten besser oder schlechter macht.

Alle Daten sind erfunden: Kontors Demo-Welt (`demo.py`) und Dokumente erfundener Firmen (`docs/`). Der Lauf braucht kein
Internet und sendet nichts.

## Aufgaben

| Gruppe | Was geprüft wird | Aufgaben |
|---|---|---|
| a | Zahlen aus BWA, Summen- und Saldenliste, Wertenachweis lesen | 11 |
| b | Lohnliste und Arbeitsvertrag lesen | 11 |
| d | Rechnen mit dem Rechen-Werkzeug statt im Kopf | 12 |
| f | Gedächtnis: Gemerktes nutzen, Neueres zählt | 10 |
| g | Wissen und Ehrlichkeit: sagen, was es nicht weiß | 16 |
| k | Kontors Zahlen über seine Werkzeuge holen | 8 |
| u | Ursachen finden statt Zeilen aufzählen – über Beteiligung, Gesellschaft, Umsätze | 5 |

Die Gruppen a, b, d, f und g stammen aus dem Prüfsatz der Modell-Auswahl. Die Gruppen k und u fragen nach der Demo-Welt; ihre
Sollwerte rechnet `run.py` bei jedem Lauf aus Kontors eigenen Zahlen.

## Ohne Modell: den Ablauf prüfen

    python3 tests/assistant_eval/run.py list
    python3 tests/assistant_eval/run.py run --stand-in reference --context 65536

Ein Ersatz für llama.cpp (`tests/fake_llama.py`) gibt je Aufgabe die Musterlösung: erst ihre Abfragen, dann ihre Antwort.
Alles läuft durch den echten Assistenten – Systemtext, Werkzeuge, Gedächtnis, Schritte. Ergebnis: 100 Punkte. Mit
`--stand-in wrong` kommen die falschen Antworten; keine darf bestehen. Das läuft auch bei jedem Push
(`tests/test_assistant_eval.py`).

## Am Mac: mit dem echten Modell

Kontor vorher beenden oder das Modell dort stoppen – sonst liegen zwei Modelle im Arbeitsspeicher.

    python3 tests/assistant_eval/run.py run \
        --assistant-dir ~/Library/"Application Support"/Kontor/assistant \
        --model qwen3.8-27b --effort thorough --out ~/Desktop/qwen38.json

- `--assistant-dir`: der Ordner, in dem Kontor llama.cpp und die Modelle hält. Nur dieser Ordner wird gelesen – nie Kontors
  Daten. Geschrieben wird dort eine kleine Datei (`eval.json`: welcher Prozess zum Lauf gehört).
- `--model`: die Kennung eines dort geladenen Modells (`qwen3.8-27b`, `qwen3.6-35b-a3b`, …). Fehlt es, nennt der Lauf die geladenen.
- `--effort`: `fast`, `balanced` (Vorgabe) oder `thorough` – wie Schnell, Ausgewogen, Gründlich.
- `--context`: Kontextlänge in Token; ohne Angabe wie in Kontor nach dem Arbeitsspeicher.
- `--groups u,k` oder `--tasks u01,d03`: nur ein Teil. `--limit`: Sekunden je Aufgabe (Vorgabe 1.800).
- `--out`: Datei für das Ergebnis – außerhalb des Programmordners ablegen.

Das Modell startet genau wie in Kontor: gleiche Optionen, gleiche Sandbox, nur auf diesem Mac erreichbar. Ein ganzer Lauf
dauert je nach Modell eine halbe Stunde bis mehrere Stunden. Antwortet das Modell auf eine Aufgabe nicht in der Zeit, startet
der Lauf es neu; nach fünf Aufgaben in Folge ohne Antwort endet er und sagt es.

Zwei Läufe vergleichen und eine Antwort ansehen:

    python3 tests/assistant_eval/run.py compare ~/Desktop/qwen36.json ~/Desktop/qwen38.json
    python3 tests/assistant_eval/run.py show ~/Desktop/qwen38.json u01

## Wie bewertet wird

Nach festen Regeln, ohne zweites Modell: Zahlen (deutsche Schreibweise, Rundung), nötige und verbotene Wörter, aufgerufene
Werkzeuge. Jede Gruppe zählt gleich viel. Eine Aufgabe gilt als bestanden, wenn sie alle Punkte hat.

Grenzen:

- Ob eine Begründung überzeugt, kann eine Regel nicht beurteilen. Gruppe u prüft, ob die Ursache und die richtigen Zahlen
  genannt, Vermutetes gekennzeichnet und der Weg über die Werkzeuge gegangen wurde. Diese Antworten selbst lesen (`show`).
- Nicht dabei: sehr lange Dokumente, Scans und Bilder, Suche nach Bedeutung, Internet-Recherche.
- Die Demo-Welt rechnet vom heutigen Tag zurück: Beträge der Gruppen k und u ändern sich mit dem Datum, die Aufgaben nicht.
- Ein Lauf ist eine Stichprobe: Modelle antworten nicht jedes Mal gleich. Unterschiede von ein, zwei Aufgaben sagen wenig.

## Dateien

- `run.py` – der Lauf: Kontor mit der Demo-Welt in einem eigenen Ordner, Aufgaben stellen, Ergebnis und Vergleich
- `tasks.json` – die Aufgaben mit Bewertung, Musterlösung und falscher Antwort
- `grading.py`, `numparse.py`, `schema.py` – die Bewertung
- `docs/` – die erfundenen Dokumente
