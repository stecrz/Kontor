# Fahrplan

Reihenfolge = Priorität. Jeder Punkt ist fertig, wenn alle Kriterien erfüllt sind, die Tests grün sind und die Version
veröffentlicht ist (Skill `release`). Geprüfte Seiten verlieren die Markierung „Alpha“.

Geprüft: Bilanz, Synchronisierung, Einrichtung, Einstellungen, Updates, Protokoll, Hilfe, Auto-Buchungen, Buchungsregeln (3.13).

## 1. Kategorien und Cashflow
Ziel: Jeder Euro ist richtig eingeordnet, der Cashflow geht auf und erklärt die Veränderung des Geldes.

Fertig, wenn
- jeder Umsatz eine Kategorie hat oder sichtbar als „ohne Kategorie“ zählt; Zuordnen geht schnell (einzeln, mehrere, mit Regel) und lernt dazu;
- Umbuchungen zwischen eigenen Konten nie als Einnahme oder Ausgabe zählen – auch über Bereiche hinweg (dann Einlage/Entnahme);
- der Cashflow je Monat aufgeht: Summe aller Zeilen = Veränderung der liquiden Konten, eine Differenz wird mit Grund gezeigt, nie verschwiegen;
- Darlehen in Zins und Tilgung getrennt sind (aus den Auto-Buchungen), Kapitalanlagen als Investition zählen;
- das Zurückschreiben nach MoneyMoney nur das Kategoriefeld ändert (Regeln in `CLAUDE.md`);
- Tests mit erfundenen Daten die Abstimmung je Monat und die Sonderfälle prüfen (Umbuchung über das Monatsende, vorgemerkte Umsätze, Erstattungen, Fremdwährung);
- Hilfe de/en und Bilder aktuell sind; beide Seiten ohne „Alpha“.

## 2. Immobilien und Steuer
Ziel: Kalkulation, Ist-Zahlen und Steuer je Objekt und Gesellschaft stimmen und passen zusammen.

Fertig, wenn
- Soll (Kalkulation) und Ist (MoneyMoney) je Jahr nebeneinander stehen: Miete, Kosten, Zinsen, Restschuld;
- die Steuer-Jahresauswertung je Entität (privat, je GbR, GmbH) aus Kategorien, AfA und Zinsen entsteht und sich gegen den Cashflow abstimmt;
- AfA aus der Kalkulation kommt und von Hand überschrieben werden kann;
- Tests rechnen auf den Cent gegen eine handgerechnete Tabelle; Hilfe und Bilder aktuell; ohne „Alpha“.

## 3. Planung
Ziel: Eine glaubwürdige Vorschau auf Vermögen und Liquidität.

Fertig, wenn
- die Planung aus den Ist-Zahlen fortschreibt (je Kategorie, Budgets aus MoneyMoney), Darlehen und Immobilien einbezieht und Ereignisse kennt;
- jede Zahl ihre Herkunft zeigt (Ist, Plan, Annahme); nichts wird geschätzt, ohne es so zu kennzeichnen;
- Tests prüfen Fortschreibung, Zinseszins und Grenzen; Hilfe und Bilder aktuell; ohne „Alpha“.

## 4. Übersicht
Ziel: Auf einen Blick, was zählt – Vermögen, Liquidität, Sparquote, was zu tun ist.

Fertig, wenn
- alle Kennzahlen aus geprüften Seiten stammen und dorthin verlinken;
- sie am iPhone genauso gut lesbar ist wie am Mac; ohne „Alpha“.

## Laufend
- Sicherheit vor allem: nichts in MoneyMoney kaputt machen, keine Daten nach außen.
- Jede Rechenlogik mit Abstimmungstests (Summen müssen aufgehen) und, wo Zustände sich ändern, mit Zufallsläufen.
- Oberfläche nach Apples Human Interface Guidelines, hell und dunkel, Mac und iPhone.
