---
name: feature
description: Einen Punkt aus ROADMAP.md oder einen Wunsch des Nutzers in Kontor vollständig umsetzen – von der Analyse über Tests und unabhängige Prüfung bis zum Release, selbstständig und ohne unnötige Rückfragen.
---

# Funktion umsetzen

Ziel ist ein fertiges, geprüftes Ergebnis, das der Nutzer nur noch ansieht.

1. **Verstehen.** Den Punkt in `ROADMAP.md` lesen; seine Kriterien „Fertig, wenn“ sind die Abnahme. Betroffene Teile mit
   der Tabelle „Aufbau“ in `CLAUDE.md` finden und lesen. Den heutigen Stand mit erfundenen Daten ansehen (Skill `ui-check`).
   Lücken, Fehler und Sonderfälle notieren – auch solche, die der Nutzer nicht genannt hat.
2. **Planen.** Aufgabenliste anlegen. Rückfragen nur bei Entscheidungen, die teuer umzukehren sind oder Geschmack betreffen
   (dann mit Empfehlung als erste Option); sonst die vernünftigste Annahme treffen und sie im Ergebnis in einem Satz nennen.
   Eine Änderung, die die zweite Stelle der Version rechtfertigt, vorher ankündigen.
3. **Umsetzen.** Regeln aus `CLAUDE.md`: Sicherheit zuerst, Texte nur über `web/i18n.js` (de + en), nichts schätzen,
   Apples Human Interface Guidelines, hell und dunkel, Mac und iPhone. Bestehendes vereinfachen, wo es Fehler vermeidet.
4. **Testen.** Neue Fälle in `tests/` mit erfundenen Daten: Normalfall, Sonderfälle, Fehlerfälle. Rechenlogik mit
   Abstimmungen (Summen müssen aufgehen, auf den Cent); wo sich Zustände ändern, Zufallsläufe wie `tests/test_fuzz.py`.
   Oberfläche mit `ui-check` ansehen, Browser-Test für neue Bedienwege.
5. **Unabhängig prüfen.** Agent `reviewer` auf die Änderung ansetzen; jeden Befund beheben oder begründet verwerfen.
6. **Abschließen.** Kriterien aus `ROADMAP.md` einzeln gegen das Ergebnis prüfen, dann Skill `release`.
