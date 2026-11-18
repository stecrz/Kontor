# Fahrplan

Reihenfolge = Priorität. Jeder Punkt ist fertig, wenn alle Kriterien erfüllt sind, die Tests grün sind und die Version
veröffentlicht ist (Skill `release`). Geprüfte Seiten verlieren die Markierung „Alpha“.

Geprüft: Bilanz, Synchronisierung, Einrichtung, Einstellungen, Updates, Protokoll, Hilfe, Auto-Buchungen, Buchungsregeln (3.13),
Kategorien und Cashflow (3.13.4: jeder Monat stimmt mit der Bilanz überein, Abweichungen mit Grund; 3.13.6: feste Positionen für alle Bereiche, ohne Kategorie geschätzt); 3.13.10: Kontenspiegel als eigene Regel zwischen beliebigen Konten; 3.13.11: Cashflow in drei Stufen mit Diagrammen, Cashflow-Positionen unter Verwaltung; 3.13.13: Kapitalflussrechnung mit Brücke).

## 1. Immobilien und Steuer
Ziel: Kalkulation, Ist-Zahlen und Steuer je Objekt und Gesellschaft stimmen und passen zusammen.

Fertig, wenn
- Soll (Kalkulation) und Ist (MoneyMoney) je Jahr nebeneinander stehen: Miete, Kosten, Zinsen, Restschuld;
- die Steuer-Jahresauswertung je Entität (privat, je GbR, GmbH) aus Kategorien, AfA und Zinsen entsteht und sich gegen den Cashflow abstimmt;
- AfA aus der Kalkulation kommt und von Hand überschrieben werden kann;
- Tests rechnen auf den Cent gegen eine handgerechnete Tabelle; Hilfe und Bilder aktuell; ohne „Alpha“.

## 2. Planung
Ziel: Eine glaubwürdige Vorschau auf Vermögen und Liquidität.

Fertig, wenn
- die Planung aus den Ist-Zahlen fortschreibt (je Cashflow-Position, Budgets aus MoneyMoney), Darlehen und Immobilien einbezieht und Ereignisse kennt;
- jede Zahl ihre Herkunft zeigt (Ist, Plan, Annahme); nichts wird geschätzt, ohne es so zu kennzeichnen;
- Tests prüfen Fortschreibung, Zinseszins und Grenzen; Hilfe und Bilder aktuell; ohne „Alpha“.

## 3. Übersicht
Ziel: Auf einen Blick, was zählt – Vermögen, Liquidität, Sparquote, was zu tun ist.

Fertig, wenn
- alle Kennzahlen aus geprüften Seiten stammen und dorthin verlinken;
- sie am iPhone genauso gut lesbar ist wie am Mac; ohne „Alpha“.

## Als Nächstes (Cashflow und Kategorien)
- [x] 3.13.15 Anlageziel je Empfänger (IBAN) statt je Kategorie; Anlagen ohne Ziel nicht als Kursgewinn, sondern offen ausweisen.
- [x] 3.13.19 Kategorienpfade mit „›“ (ein „/“ im Namen bleibt Teil des Namens); Cashflow-Diagramme bis zum letzten abgeschlossenen Monat, Ring für Ausgaben/Einnahmen mit Heatmap, Liquiditätsbrücke, Zu- und Abflüsse je Monat.
- [x] 3.13.20 Menü neu: „Konten & Regeln“ (alles, was die Zahlen bestimmt) und „Einstellungen“ (wie Kontor arbeitet); Einrichtung als geführter Weg; Geldfluss-Diagramm.
- [x] 3.13.21 Sicherheit: automatische Sperre trotz offener Seite, kein Ersatzschlüssel wenn der Schlüsselbund nicht antwortet, Verknüpfungen im Belegordner bleiben im Ordner; Lizenz Apache 2.0.
- [x] 3.13.22 „MoneyMoney-Sync“; Online/Offline je Konto unter Konten, Depot-Verlauf und Datei-Import unter Kontostände; Liquiditätsbrücke grün/rot; vollständig lesen alle 30 Tage.
- [x] 3.13.23 Nettovermögen je Monat, Klick auf Monat (zwölf Monate) und auf Heatmap/Ring (Umsätze), Vorjahresvergleich; Sync-Seite ohne Kontenliste.
- [x] 3.13.24 Liquiditätsbrücke aufklappbar, Cashflow-Gruppen in ihren Farben.
- [x] 3.13.25 Cashflow-Tabelle kompakter (✓ am Wert, FCF), Heatmap robust mit Gesamtzeile, Filter in Umsätze & Belege, Zeitraum per ‹ ›.
- [x] 3.13.26 Liquiditätsbrücke mit Achse und Zoom, Sankey „Mittelherkunft & -verwendung“ neu.
- [x] 3.13.27 Vermögensbrücke, Zeile „Umschichtungen“, Tabelle öffnet auf dem letzten abgeschlossenen Monat.
- [x] 3.13.28 Zeitraum mit Monatskalender und Plan, neue Anordnung der Diagramme, Sprung in die Bilanz.
- [x] 3.13.29 Protokoll schlank (eine Datei, Filter), Diagramme verschiebbar, Klicks in Tabelle und Geldtransit.
- [x] 3.13.30 Vorzeichen, Nettovermögen aufklappbar, Unklar anklickbar, Diagramm-Paare, Schraffur in Brücken.
- [x] 3.13.31 Zugang lädt sofort, Gesamtcashflow-Höhe stabil.
- [x] 3.13.32 Monatlicher Cashflow wie die Tabelle, ruhigere Farben, Gesamtcashflow mit Taille und „alles aufklappen“, Sprung zur Bilanz.
- [x] 3.13.33 Vermögensbrücke mit Überschuss/Zinsen, Seitenfenster für Umsätze, Sankey-Farben, PayPal-Umbuchungen gepaart.
- [x] 3.13.34 Seitenfenster überall, senkrechter Zoom, Farben nach Tabelle, Bilanz-Sprung, umgezogene Karte.
- [x] 3.14.0 Gesamtprüfung; jede Cashflow-Zahl zeigt ihre Umsätze; Sicherheit (Update-Quelle, Protokoll); iPhone-Feinschliff.
- Danach: Empfohlener Kategorienbaum (Checkliste zum Anlegen in MoneyMoney; Kontor legt selbst nur an, falls MoneyMoney es anbietet und du freigibst), Hinweis bei gemischten Kategorien, Zuordnen je Empfänger in einem Schritt, Fortschritt „sicher zugeordnet / geschätzt“; alles Freigegebene sichtbar und rückgängig zu machen.

## Laufend
- Sicherheit vor allem: nichts in MoneyMoney kaputt machen, keine Daten nach außen.
- Jede Rechenlogik mit Abstimmungstests (Summen müssen aufgehen) und, wo Zustände sich ändern, mit Zufallsläufen.
- Oberfläche nach Apples Human Interface Guidelines, hell und dunkel, Mac und iPhone.

## Beim nächsten großen Versionssprung (Hilfe, README, Bilder)
- Hilfe „Konten → Positionen“: erklären, was der Nutzer wählt (nach Verfügbarkeit), statt der Reihenfolge, in der Kontor vorschlägt.
- Hilfe und README: Deinstallieren in der App (Einstellungen → Sicherung), Programmordner in den Daten; Installation als ein Schritt (wartet auf Apples Werkzeuge).
