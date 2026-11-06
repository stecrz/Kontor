# Änderungen

## 3.2.0
- Kontor-eigene Kategorien: Baum aus MoneyMoney übernommen und erweiterbar, Zuordnung je Umsatz in Kontor, Regeln gelernt aus bisherigen Zuordnungen (IBAN, Gegenpartei, Gegenpartei + Zweck) plus eigene Regeln; Seite „Zuordnen“ für offene Umsätze je Gegenpartei; MoneyMoney-Kategorien bleiben Rückfall; Rückschreiben nach MoneyMoney optional.
- Konten einmal bestätigen (Bereich, Position); neue Konten in MoneyMoney erscheinen als „neu“ mit Hinweis.
- Saldenverlauf aus CSV/Excel importieren (Liste, Matrix, transponierte Matrix; Kontozuordnung mit Vorschlag); Depotstände vor dem ersten bekannten Wert aus Käufen/Verkäufen des Verrechnungskontos geschätzt statt flach fortgeschrieben.
- Einrichtung als Bausteine: Verbindung, Bereiche, Bilanzpositionen & Verlauf, Kategorien, Regeln, Immobilien, Planung, Steuer, Belege, Betrieb – einzeln einrichtbar, mit Status; Hilfe-Knöpfe an allen erklärungsbedürftigen Feldern.
- Bereiche unabhängig von der Gruppierung in MoneyMoney: Konten und Gruppen frei zuordnen, Hauptbereich, Art und Anteil je Bereich.
- Bilanz nach Positionen (Liquidität, Wertpapiere, Geldanlagen, Immobilien, Beteiligungen, Sachwerte, Forderungen, Sonstiges, Verbindlichkeiten), umschaltbar auf MoneyMoney-Gruppen; Position je Konto überschreibbar.
- Verlauf je Konto aus Umsätzen (rückwärts vom aktuellen Saldo, Startsalden unerheblich) oder aus Monatsständen; Stände eintragen oder aus Saldenexport (CSV) laden; Depots ohne Umsatzhistorie damit korrekt.
- Inaktive Konten (kein Bestand, kein Umsatz seit N Monaten) ausgeblendet, aber in Summen und Historie enthalten.
- Planung: Ereignisse (einmalig/monatlich/quartalsweise/jährlich; Umschichtung zwischen Konten, Einnahme, Ausgabe), Beteiligungskonten an das Nettovermögen eines anderen Bereichs koppeln, Übernahme der Immobilienkalkulationen.
- Immobilien: Kalkulationen je Objekt mit Szenarien (Nebenkosten, AfA, Indexmiete, Kosten, Darlehen mit monatlicher oder jährlicher Abrechnung, Sondertilgungen, Zinsbindung, Fälligkeit, Gesellschafter, Steuer, Ausschüttung, Cashflow, Vermögensaufbau, Renditen, IRR), Soll/Ist gegen MoneyMoney, AfA in die Steuer, Excel-Export, Dokumente als Verknüpfung zu Dateien auf dem Mac (auch iCloud Drive).
- Belege: Dateien außerhalb des Belegordners verknüpfen (bleiben liegen), iCloud-Status.
- Pakete enthalten Bereiche, Positionen und Immobilien; Ergänzen führt sie nach Kennung zusammen.
- Installation: `install.sh` entfernt das Quarantäne-Attribut (Gatekeeper blockierte `.command`-Dateien aus Downloads).

## 3.1.0
- Neuer Name Kontor (vorher mmtools); Datenordner `~/Library/Application Support/Kontor`, Daten und Schlüssel der Vorversion werden übernommen.
- Mehrere Bereiche (Kontengruppen) mit eigener Bilanz, Kapitalfluss, Planung; Bereichswechsel in der Oberfläche.
- Übersicht neu: Kennzahlen mit Verlauf, Vermögensstruktur, Einnahmen/Ausgaben je Monat, Jahresvergleich (kumuliert, Vorjahr gleicher Zeitraum), offene Punkte, Planvorschau, weitere Bereiche.
- Spaltenmodus Monate / Monate + Jahre / Jahre überall; Planwerte optional inflationsbereinigt.
- Planung: Inflation, getrennte Steigerung für Einnahmen und Ausgaben, Methode „MoneyMoney-Budget“, Zellen inline bearbeiten, Plan je Bereich zurücksetzen.
- Umsätze & Belege: Umsatzbrowser mit Filtern, Belege als Dateien in einem frei wählbaren Ordner, Belegexport als ZIP je Jahr/Bereich, Kategorie zuweisen (abschaltbar).
- Depots mit Positionen; Excel-Export für Bilanz, Kapitalfluss, Planung, Steuer, Umsätze, Depots, Belege, Konten.
- Einstellungspakete (Export/Import mit Kontozuordnung), Einrichtungsassistent, Updates aus GitHub, MoneyMoney-Aktualisierung auslösen, Diagnosedatei mit maskierten Namen.

## 3.0
- Dauerhafter Dienst mit Web-Oberfläche, Passwort/Touch ID, verschlüsselte Ablage, Einstellungen über die Oberfläche.

## 2.0
- Bilanz, Kapitalfluss, Planung; Regeln mit `UUID | Name`; IBAN-Erkennung; nur manuelle Konten beschreibbar.

## 1.0
- Darlehensspiegelung, Zinsen, Beteiligungswerte als Kommandozeilenwerkzeug.
