# Fahrplan

Reihenfolge = Priorität. Jeder Punkt ist fertig, wenn alle Kriterien erfüllt sind, die Tests grün sind und die Version
veröffentlicht ist (Skill `release`). Geprüfte Seiten verlieren die Markierung „Alpha“.

Geprüft: Bilanz, Synchronisierung, Einrichtung, Einstellungen, Updates, Protokoll, Hilfe, Auto-Buchungen, Buchungsregeln (3.13),
Kategorien und Cashflow (3.13.4: jeder Monat stimmt mit der Bilanz überein, Abweichungen mit Grund; 3.13.6: feste Positionen für alle Bereiche, ohne Kategorie geschätzt); 3.13.10: Kontenspiegel als eigene Regel zwischen beliebigen Konten; 3.13.11: Cashflow in drei Stufen mit Diagrammen, Cashflow-Positionen unter Verwaltung; 3.13.13: Kapitalflussrechnung mit Brücke); Übersicht (3.15.0: vier Grafiken aus Bilanz und Cashflow, ohne eigene Rechnung; 3.15.1: offene Punkte darunter); Kategorisieren (3.15.1: ohne Schalter, Eingetragenes rückgängig machbar; 3.15.2: umbenannt, anfangs nur private Bereiche); Drucken (3.15.1); Übersicht in drei Spalten mit Bilanz-Kacheln (3.15.2).

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

## 3. BWA und Summen- und Saldenliste (Gesellschaften)
Ziel: Die Bilanz einer Gesellschaft stimmt mit der des Steuerberaters überein.

Fertig, wenn
- BWA und SuSa (DATEV-Export, CSV/PDF) je Gesellschaft geladen werden können, nur lokal und verschlüsselt;
- Posten, die auf keinem Konto stehen (Ware, Forderungen/Zahlungsziele, Rückstellungen, Gewinnvortrag), daraus in Bilanz und Übersicht erscheinen, gekennzeichnet mit Stand und Quelle;
- Bruttovermögen dann als Bilanzsumme abgestimmt; Tests mit erfundenen Exporten.

## ~~Übersicht~~ (erledigt in 3.15.0)
Vier Grafiken aus Bilanz und Cashflow auf einer Bildschirmseite, jede verlinkt an ihre Stelle; am iPhone untereinander; ohne „Alpha“.

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
- [x] 3.15.1 Eingetragene Kategorien sichtbar und rückgängig zu machen.
- [x] 3.15.3 Einlagen mit Gegenbuchung im eigenen Kapitalkonto: ohne Scheinänderung des Nettovermögens.
- [x] 3.15.2 Empfohlene Kategorien als Checkliste unter Cashflow-Positionen (MoneyMoneys Schnittstelle kann keine Kategorien anlegen); Zielkonto einheitlich benannt und erklärt.
- [x] 3.15.8 Übersicht mit Kennzahlen, Vermögen statt Bilanzsumme; offene Buchungen und Positionen anklickbar; Kategorien-Bedarf live.
- [x] 3.15.10 Übersicht mit Hover-Infos in allen Grafiken; Updates ersetzen direkt und räumen alte Dateien weg.
- [x] 3.15.11 Übersicht: Vermögensaufbau je Baustein statt Kennzahlen; Vorjahresvergleich nur mit bekanntem Stand.
- [x] 3.15.12 Bilanz in Jahren ohne graue Jahresspalten; Cashflow-Tabelle: Zeilenlinien neben den Namen ohne Versatz (Safari); Auto-Buchungen: „alle abwählen“ wählt alles ab.
- Danach: Hinweis bei gemischten Kategorien (etwa eine Immobilien-Kategorie mit Kaufpreis, Auszahlung und Miete), Kategorisieren je Empfänger in einem Schritt, Fortschritt „sicher zugeordnet / geschätzt“.

## Laufend
- Sicherheit vor allem: nichts in MoneyMoney kaputt machen, keine Daten nach außen.
- Jede Rechenlogik mit Abstimmungstests (Summen müssen aufgehen) und, wo Zustände sich ändern, mit Zufallsläufen.
- Neue Lebensfälle (Einlage, Kauf, Darlehen, Auslage …) als Szenario in `tests/test_scenarios.py` ergänzen – je Tag, Monats- und Jahreswechsel.
- Oberfläche nach Apples Human Interface Guidelines, hell und dunkel, Mac und iPhone.

## Beim nächsten großen Versionssprung (Hilfe, README, Bilder)
- Hilfe-Bilder und -Texte neu: Übersicht (drei Spalten, Kennzahlen), Kategorisieren, Cashflow-Positionen (Empfehlung), Buchungsregeln (Bereich + Konto) – 3.15.2 hat nur die Texte angepasst.
