# Überblick je Hauptversion

Was eine Hauptversion gegenüber der vorigen bringt: die Unterversionen davor (3.16.1 … 3.16.x) sind Schritte zu ihr (3.17.0),
die nach der Gesamtprüfung erscheint. Nur die großen Themen, höchstens sechs Punkte – Einzelheiten in CHANGELOG.md.
Einstellungen → Updates zeigt den Überblick vor den einzelnen Versionen; die kommende Hauptversion als „in Arbeit“.

## 3.18
- KI-Assistent kennt jede Stelle jeder Seite (Rechtsklick: was eine Zahl ist) und sucht Ursachen über Konten, Umsätze und Beteiligungen hinweg
- Updates fragen nur bei echtem Risiko – je Fund in klaren Worten erklärt, mit den betroffenen Zeilen
- Planung: Regeln je Bereich, Position und Kategorie, Modelle mit einem Klick, jede Planzahl erklärt; Sparquote, Reichweite, Zinslast
- KI-Assistent: Modelle nach Zweck, sieht Bilder als Ganzes; fragt auf Wunsch Claude (Anthropic) – jede Frage vorher auf einer Karte
- iPhone: eigener Face-ID-Schlüssel je Gerät, jede Änderung mit Face ID bestätigt, Geräte am Mac entfernbar; Tailscale wird geprüft
- Sicherheit: eigenes, aktuelles Python statt Apples Python 3.9 – nach Klick geladen, geprüft und erst nach bestandener Probe in Gebrauch

## 3.17
- Sicherheit: Daten erst nach deiner Anmeldung lesbar (Passwort oder Touch ID); jedes Update vor dem Installieren gelesen und geprüft
- KI-Assistent schlägt vor, du entscheidest: Kategorien, Buchungsregeln, Auto-Buchungen, Belege – ausgeführt nach deinem Klick, mit Protokoll
- KI-Assistent liest Belege, Excel und mehrseitige PDF-Tabellen (BWA, Summenlisten); Diagramme und gespeicherte Verläufe im Chat
- KI-Assistent: Gedächtnis aus deinen Worten, Suche nach Bedeutung; Internetsuche nur zum Lesen bei festen, meist amtlichen Quellen
- Eigene Mac-App mit Menüleiste und ⌘F; Diktieren bis zehn Minuten; Rechtsklick auf jede Zahl: „Kurz erklären“, „Im Chat fragen“
- Demo mit erfundenen Beispieldaten zum Vorzeigen; Updates zeigen die Änderungen je Hauptversion

## 3.16
- KI-Assistent (Alpha): Sprachmodell nur auf diesem Mac, ohne Netz – liest alle Auswertungen, zeigt Ansichten, trägt Werte nach deinem Klick ein
- Diktieren mit eigenem Sprachmodell auf dem Mac
- Kategorisieren (vorher „Zuordnen“): Eingetragenes rückgängig machen, empfohlene Kategorien für MoneyMoney
- Übersicht: Vermögensaufbau je Baustein, Vermögensstruktur als Bilanz-Kacheln; Drucken (⌘P) mit Grafiken
- Cashflow: Einlagen und Entnahmen zwischen deinen Bereichen über das Kapitalkonto erkannt
- Sicherheit: Kommandozeile ohne Datenzugriff; Installation lädt nur den aktuellen Stand (5 statt 240 MB)

## 3.15
- Übersicht neu: vier Grafiken auf einer Seite, ein Klick führt in Bilanz oder Cashflow
- Einrichtung führt Schritt für Schritt bis zum Abschluss
- Kontor deinstallieren in den Einstellungen; Installation in einer Zeile; Datenschlüssel erneuerbar
- Cashflow-Grafiken feiner: Tooltips, Brücken, Ergebnis je Monat, Farben im Dunkelmodus

## 3.14
- Cashflow neu: gegliedert wie eine Kapitalflussrechnung (Überschuss, Investitionen, Finanzierung), jeder Monat mit der Bilanz abgestimmt
- Cashflow-Grafiken: Liquiditäts- und Vermögensbrücke, Monatlicher Cashflow, Mittelherkunft & -verwendung, Heatmap, Vorjahresvergleich
- Kategorien: MoneyMoney ist maßgeblich – Kontor trägt nach deinem Klick dort ein, mit Vorschlägen; feste Cashflow-Positionen
- Menü neu mit „Konten & Regeln“; Einrichtung als geführter Weg
- Gesamtprüfung: 1000 Zufallsläufe, jede Seite hell und dunkel; jede Cashflow-Zahl zeigt ihre Umsätze

## 3.13
- Bilanz: große Grafik mit Werte-Fenster, laufendem Monat und Plan; Eigenkapitalquote durch die Gesellschaften gerechnet
- Auto-Buchungen: Freigabe einzeln oder vollautomatisch, nie doppelt; Buchungsregeln neu mit Soll, Ist und Differenz
- Buchungsregeln: Schreiben in MoneyMoney eng begrenzt (Markierung „#kontor-…“), Kontenspiegel
- Sicherheit: Protokoll ohne Beträge und Namen, Offline-Kopie am iPhone verschlüsselt, ⌘L sperrt; neues Logo

## 3.12
- Neuer Look: dunkel als Standard, Akzentfarbe Gold
- Bilanz-Grafiken: Hervorhebung beim Darüberfahren, weiche Kurven, Klick auf eine Fläche klappt auf, „Ansicht speichern“

## 3.11
- Erste allgemeine Version: noch nicht vollständig geprüfte Seiten als „Alpha“ markiert
- Bilanz: Depots in einzelne Wertpapiere aufklappbar; jede Grafik kann die große sein
- Excel-Export der Bilanz mit Konten und Wertpapieren
- Wertpapiernamen nachschlagen (nur auf Klick, sendet nur die ISINs)

## 3.10
- Bilanz mit Grafiken: Vermögen im Zeitverlauf, eine Tabelle mit aufklappbaren Positionen
- Kontostände aus MoneyMoneys Datenbank einlesen (Upload, nur im Arbeitsspeicher)
- Zugriff vom iPhone über Tailscale; Einstellungen in Reitern; Englisch als zweite Sprache
- Kategorien: MoneyMoney ist maßgeblich; Hilfe neu, dieselbe wie auf GitHub

## 3.9
- Konten überall in der Reihenfolge von MoneyMoney

## 3.8
- „Synchronisieren“ auf Knopfdruck; Datenstand in zwei Stufen (Bank → MoneyMoney → Kontor)
- Einrichtung: Bereiche sortierbar, Position und Verlauf je Konto fest gespeichert; schneller bei unveränderten Daten

## 3.7
- Neue Positionen außerhalb des Nettovermögens: Kapitalkonten, Avale & Bürgschaften
- Hinweis „veraltet?“ bei Konten ohne Buchung seit Monaten

## 3.6
- Verlauf je Konto sofort gerechnet; eingetragene Kontostände als Anker
- Neuberechnung 6- bis 10-mal schneller; letzter MoneyMoney-Stand verschlüsselt zwischengespeichert

## 3.5
- Dienst startet sich nach einem Update selbst neu; Update-Prüfung direkt aus dem Hauptzweig
- Verständlichere Begriffe („Abgleich“, „Testmodus“); neues Symbol

## 3.4
- Auswertung 14-mal schneller, Neuberechnung im Hintergrund
- Update-Hinweis im Menü, Prüfung täglich

## 3.3
- Installation mit einer Terminal-Zeile
- iPhone: https über Tailscale, Offline-Ansicht mit Passwort
- Sicherung aller Einstellungen als eine Datei

## 3.2
- Bilanz nach Positionen; Bereiche frei zuordnen
- Verlauf je Konto aus Umsätzen oder Monatsständen, Import aus CSV/Excel
- Planung mit Ereignissen, Immobilien-Kalkulationen, Einrichtung in Schritten

## 3.1
- Neuer Name Kontor; mehrere Bereiche mit eigener Bilanz, Cashflow und Planung
- Umsätze & Belege, Excel-Export, Einstellungspakete, Updates aus GitHub

## 3.0
- Dienst mit Web-Oberfläche, Passwort/Touch ID, verschlüsselte Ablage

## 2.0
- Bilanz, Kapitalfluss, Planung

## 1.0
- Darlehensspiegelung, Zinsen, Beteiligungswerte als Kommandozeilenwerkzeug
