---
name: release
description: Jede Änderung an Kontor abschließen – mitpflegen, mit .claude/tools/release.py prüfen und als eine Version direkt auf main veröffentlichen (nicht auf GitHub warten). Am Ende jeder Änderung verwenden, auch bei kleinen.
---

# Release (kleine Version)

1. **Mitpflegen** – GitHub ist das einzige Gedächtnis (`CLAUDE.md`, Arbeitsweise): jede Entscheidung des Nutzers aus diesem Chat
   samt Grund, auch jede Ablehnung (`ROADMAP.md`, „Entschieden“/„Offen“), jede geänderte Regel oder jeder geänderte Ablauf
   (`CLAUDE.md`, `docs/rules/`, Skills, Hooks). Nach „Was wo gepflegt wird“ und der Spalte „Kleine Version“ in „Prüfen“
   (`CLAUDE.md`): Texte und Tooltips de + en, `docs/ui` + `data-ex`, deutsche Hilfe nur im betroffenen Abschnitt und nur, wenn sich
   Bedienung oder Verhalten ändert (neuer Abschnitt: im Englischen gleich Überschrift, Anker und ein Satz). **Nicht** in kleinen
   Versionen: englische Hilfe, README, Bilder, `HIGHLIGHTS.md` – das macht der große Sprung (Skill `major`). Erledigtes aus
   `ROADMAP.md` streichen. Oberfläche geändert: Skill `ui-check`. Neue Tests für die Änderung gehören dazu.
2. **Unabhängig prüfen** nur bei neuen Wegen nach außen, Schreiben nach MoneyMoney, Zugang oder Daten: Agent `reviewer` mit dem
   Diff und den geänderten Funktionen im Auftrag; Befunde beheben oder begründet verwerfen.
3. **Prüfen und veröffentlichen** – ein Aufruf (Zeitgrenze 600000 ms; die Werkzeuge richtet `.claude/tools/setup.sh` beim Start
   der Sitzung ein):
   ```
   python3 .claude/tools/release.py "<was sich ändert, englisch, kurz>" "<Bezug>: <Punkt>" ["<Bezug>: <Punkt>" …] \
     [--tests "tests/test_e2e.py -k <neuer Browser-Test>"] [--by "Claude Opus 5.5: https://claude.ai/code/session_…"]
   ```
   - Changelog-Punkte: Deutsch, aus Sicht des Nutzers (was er merkt), je Punkt eine Zeile mit wenigen Stichworten, keine
     Erklärungen; vorn der Bezug mit Doppelpunkt („KI-Assistent: …“, „Bilanz: …“; nur Regeln, Tests, CI: „Entwicklung: …“ – in der
     Update-Anzeige ausgeblendet). `VERSION` und `CHANGELOG.md` schreibt nur das Skript.
   - `--by` einmal je Klon: Modell und Link dieser Sitzung aus den Hinweisen der Sitzung (keine E-Mail, kein `Co-Authored-By`).
   - Während der Arbeit beliebig oft nur prüfen: `python3 .claude/tools/release.py --check [--tests …]`.
   - „Prüfung läuft noch“ (Ausgang 5): denselben Befehl erneut – die Prüfung läuft im Hintergrund weiter.
   - Rot (1): beheben, denselben Befehl erneut. Konflikt (3): beide Seiten erhalten, `git add`, `git rebase --continue`, erneut.
     Gesperrt (4): die Meldung sagt, was zu tun ist – nie umgehen. Meist fehlt beim Lösen eines Konflikts ein fremder Teil: ihn
     wieder aufnehmen, eigene Änderung darauf, erneut. Soll die eigene Änderung fremde Zeilen wirklich ersetzen: die gemeldeten
     Zeilen dem Nutzer mit Empfehlung vorlegen und auf sein Ja warten – erst dann `KONTOR_PUSH_OK=1`, nie nach eigenem Abwägen
     (`docs/rules/parallel.md`).
4. **Nicht auf GitHub warten.** Ein roter Lauf erscheint im Lagebild des nächsten Chats, der ihn behebt („fix ci“). Nach dem Push
   nichts nachschieben – eine Korrektur ist eine neue Version. Nur Regeln, Tests oder CI geändert: mit der nächsten Version
   mitnehmen, außer es muss sofort für die anderen Chats gelten.
5. **Antwort an den Nutzer:** auf Deutsch, kurz – was sich für ihn ändert und die Version. Keine Aufzählung der Arbeitsschritte.
   Den Mac aktualisiert der Nutzer selbst: nicht darauf zugreifen, nicht erwähnen.
