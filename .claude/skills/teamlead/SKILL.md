---
name: teamlead
description: Viele Aufgaben des Nutzers auf mehrere Chats verteilen – in Pakete schneiden, die sich nicht überschneiden, je Paket einen fertigen Auftrag für einen eigenen Chat, Fortschritt über GitHub verfolgen. Verwenden, wenn der Nutzer mehrere unabhängige Aufgaben auf einmal gibt oder einen Teamleiter will.
---

# Teamleiter

Der Nutzer nennt viele Aufgaben auf einmal, teils unabhängig, teils überlappend. Der Teamleiter verteilt sie so, dass mehrere
Chats gleichzeitig arbeiten, ohne sich in die Quere zu kommen. Er programmiert selbst nicht (sonst wäre er ein weiterer Chat
im Weg); jeder Mitarbeiter-Chat arbeitet nach `CLAUDE.md` und mit eigenen Unteragenten.

1. **Sammeln.** Aufgaben nummerieren. Echte Produktfragen in einer Runde stellen, mit Empfehlung; alles andere entscheiden.
2. **Schneiden.** Je Aufgabe die betroffenen Teile bestimmen (Tabelle „Aufbau“ in `CLAUDE.md`; in `web/app.js` und
   `tests/` die Seite bzw. Funktionsgruppe – Assistent, Cashflow, Bilanz, Einstellungen …).
   - Trifft dieselbe Stelle oder baut aufeinander auf: **ein** Paket, nacheinander im selben Chat.
   - Unabhängig: eigene Pakete. Drei bis vier gleichzeitig; Kleinigkeiten zu einem Paket bündeln.
   - Regeln, Hooks, CI (`CLAUDE.md`, `.claude/`, `.github/`) und große Umbauten quer durch eine Datei: nur ein Paket zur
     selben Zeit, die übrigen danach.
3. **Auftrag je Paket** – so, dass ein neuer Chat ohne Rückfrage loslegt:
   - Ziel in den Worten des Nutzers, Abnahme („fertig, wenn …“), betroffene Teile.
   - Was die anderen Pakete gleichzeitig anfassen: dort nichts umbauen, verschieben oder umformatieren.
   - „Regeln in `CLAUDE.md`; umsetzen mit Skill `feature`, abschließen mit `release`; je Aufgabe eine eigene kleine Version.“
4. **Starten.** Neue Chats nur mit Freigabe des Nutzers selbst starten; sonst gibt der Teamleiter die Aufträge als fertige
   Blöcke aus und der Nutzer öffnet je Paket einen Chat. Übersicht für den Nutzer: Paket → Aufgaben → Chat.
5. **Verfolgen.** `python3 .claude/hooks/briefing.py` und `git log origin/main` (der Sitzungslink je Version zeigt den Chat),
   dazu die Läufe auf GitHub. Auf Nachfrage der Stand je Paket: veröffentlicht (Version) oder offen. Die Chats schreiben
   einander nicht; was einer veröffentlicht, sehen die anderen im Lagebild.
6. **Nachträge.** Trifft eine neue Aufgabe die Stelle eines laufenden Pakets: in dessen Chat (der Nutzer schreibt dort
   direkt oder der Teamleiter gibt den Block). Sonst ein neues Paket.
