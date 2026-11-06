# Änderungen

## 3.4.1
- Update-Prüfung liest die Version direkt aus dem Hauptzweig (Datei VERSION) statt aus Tags: neue Versionen werden erkannt, sobald sie gepusht sind; Neuerungen kommen aus CHANGELOG.md. Fallback auf Releases bzw. den höchsten Tag.

## 3.4.0
- Bericht 14× schneller (190.000 Umsätze: 154 s → 11 s; Umbuchungs-Paarung und Monatssalden ohne quadratischen Aufwand, Steuer nach Jahren gebündelt). Ergebnis bitgleich zur Vorversion geprüft.
- Neubau nach Änderungen (Verlauf, Zuordnungen, Bereiche, Immobilien) läuft im Hintergrund; mehrere Änderungen werden zu einem Neubau zusammengefasst. Die Oberfläche bleibt bedienbar, unten links steht der Fortschritt, danach lädt die Ansicht selbst neu.
- Entschlüsselte Dateien und die Umsatzliste bleiben im Speicher (nur neu gelesen, wenn sie sich ändern); parallele Lese-/Schreibzugriffe auf den Verlauf gehen nicht mehr verloren.
- Kein „Offline-Ansicht“ mehr am Mac: am Mac selbst gibt es keine Offline-Kopie; am iPhone gilt ein langsamer Mac nicht als offline (Gegenprobe ohne Zeitlimit), im Offline-Modus wird die gespeicherte Kopie sofort angezeigt und alle 30 s geprüft, ob der Mac wieder da ist.
- Seitenwechsel: Ladeanzeige, wenn der Dienst nicht sofort antwortet; Überschrift und Inhalt passen immer zusammen; „Erneut versuchen“ bei Fehlern.
- Abgebrochene Verbindungen erzeugen keine Fehlerprotokolle mehr; „Verbindung prüfen“ läuft nicht doppelt.
- Update-Hinweis als blauer Punkt im Menü „Updates“; Prüfung täglich im Hintergrund (bei fehlendem Netz nach 2 h erneut), blockiert nichts.
- MoneyMoney-Status unten links alle 30 s aktuell, inkl. „gesperrt“; ist MoneyMoney gesperrt oder aus, wird der fällige Lauf jede Minute erneut versucht statt erst nach 30 Minuten.
- Berechtigungen werden erklärt (wofür Kontor sie braucht), in der Verbindung und in der Hilfe.
- „Verbindung prüfen“ mit Ladeanzeige, Knopf während der Prüfung gesperrt.
- Belegordner wird erst beim ersten Beleg und nur nach Rückfrage angelegt (oder anderen Ordner in den Einstellungen wählen).
- Tooltips bleiben immer im Fenster.
- Bereiche: Art und Hauptbereich aus dem Namen vorbelegt (GmbH/GbR/AG … = Gesellschaft, der Rest privat), Anteil in Prozent, Gruppe wählen = alle Konten darunter (angezeigt und gesperrt), einzelnes Konto abwählen löst die Gruppe auf.
- Einrichtung als geordnete Liste.
- Bilanzpositionen & Verlauf kompakter (passt auf einen Bildschirm), Tooltips zu Position, Verlauf, Anzeige; „Verlauf …“ öffnet zuverlässig wiederholt.
- Protokoll-Seite zeigt den Dateipfad und kann die Datei im Finder zeigen.

## 3.3.0
- Installation mit einer Terminal-Zeile (`get.sh`: clone/pull + install.sh); `Installieren.command` entfällt (Gatekeeper blockiert heruntergeladene Skripte). Update aus der Oberfläche lädt das Archiv von github.com statt über die API (die mit 415 antwortete).
- Protokoll ausführlich (DEBUG in der Datei): Anfragen, MoneyMoney-Aufrufe mit Dauer, Berichtsumfang, Konfigurationsänderungen, Update-Schritte, Fehler mit Rückverfolgung.
- Touch ID erscheint nach einer Sperre automatisch, sobald das Fenster wieder aktiv ist; Sitzung wird beim Zurückkehren geprüft.
- iPhone: `python3 kontor.py tls` richtet https über ein Tailscale-Zertifikat ein (Erneuerung durch den Dienst); der Dienst hört immer auf 127.0.0.1 und zusätzlich auf der Tailscale-Adresse.
- Offline-Ansicht als App am iPhone: zuletzt geladene Daten bleiben auf dem Gerät und sind mit Passwort lesbar, wenn der Mac aus oder nicht erreichbar ist (Service Worker; Passwortprüfung auf dem Gerät mit eigenem Prüfwert; nur lesen; Sperre nach Leerlauf).
- Sicherung aller Einstellungen (Konfiguration, Planung, Kategorien, Verlauf, Belegindex) als eine Datei; Einspielen unter Pakete; Zurücksetzen des Programms über die Oberfläche (nur am Mac, mit Passwort, wahlweise samt Passwort).
- Oberfläche durchgängig mit Umlauten (Protokoll und Code bleiben ASCII).

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
