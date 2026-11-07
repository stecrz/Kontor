# Änderungen

## 3.7.2
- Statuszeile zeigt, von wann die Daten aus MoneyMoney stammen („Daten vom …“), statt des Zeitpunkts der letzten Neuberechnung; ohne laufendes MoneyMoney kein „nächster Abgleich“.
- Test: Arbeiten ohne MoneyMoney mit dem zwischengespeicherten Stand (Neustart, Neuberechnung, Verlauf).

## 3.7.1
- Einrichtung · Verbindung: prüft auf der Seite alle 3 Sekunden, ob MoneyMoney läuft und entsperrt ist.
- Einrichtung · Bereiche: Anteil nur bei Gesellschaften (bei „privat“ ausgeblendet).
- Einrichtungsschritte einheitlich: „Speichern“, „Speichern und weiter: …“, „Zurück zur Einrichtung“. „Speichern und weiter“ wartet mit Fortschrittsanzeige, bis die Auswertung aktualisiert ist, und öffnet erst dann den nächsten Schritt (so stimmen dort die Vorschläge).
- Neuberechnung meldet ihren Fortschritt (Schritt und Prozent).

## 3.7.0
- Positionen: Vorschlag neu geordnet – Kontoname vor Kontotyp (z. B. „Immobilie …“ als Festgeldanlage → Immobilien), Gruppenname vor allgemeinem Kontotyp (Sparkonto in „Anlagen“ → Geldanlagen), Bausparer und Versicherungen → Geldanlagen; Darlehen und Kautionen nach Vorzeichen (Guthaben = Forderung, Schuld = Verbindlichkeit); Namen mit Wortgrenzen (z. B. „Haushaltskasse“ ist keine Immobilie).
- Neue Positionen außerhalb des Nettovermögens: „Kapitalkonten (Eigenkapital)“ und „Avale & Bürgschaften“; in der Bilanz unter dem Nettovermögen ausgewiesen. Einlagen/Entnahmen über Kapitalkonten erscheinen im Kapitalfluss. Die Beteiligungsregel bewertet eine Gesellschaft ohne ihre Kapitalkonten (vorher ergab sich so ein Wert nahe 0).
- „nicht bilanzieren“ wird überall so angezeigt (vorher teils „ignorieren“).
- Depot-Schätzung aus Käufen/Verkäufen nur noch über ein Konto derselben Bank (nicht mehr über dieselbe MoneyMoney-Gruppe, was falsche Zusammenhänge erzeugte); im Verlauf-Fenster wählbar oder abschaltbar.
- Verlauf-Fenster prüft die Rückrechnung: Anfangssaldo vor der ersten Buchung, vorgemerkte Umsätze, Konten ohne Umsätze; negative Stände bei Spar-, Tagesgeld-, Festgeld- und Bausparkonten erscheinen als Hinweis.
- Hinweis „veraltet?“ bei Konten mit Saldo, aber ohne Buchung und Aktualisierung seit N Monaten.
- „illiquide“ entfällt als Einstellung; Kennzahl „Finanzielle Unabhängigkeit“ und „liquides Nettovermögen“ aus der Übersicht entfernt; Liquidität mit Reichweite in Monaten.
- Bilanzpositionen & Verlauf: ein Hilfe-Symbol oben, Erklärungen in den Spaltenköpfen; nach dem Speichern nur noch Hinweise mit Handlungsbedarf statt aller geprüften Verweise.

## 3.6.0
- Verlauf-Fenster rechnet das gewählte Konto sofort selbst (unter einer Sekunde, auch bei 190.000 Umsätzen) statt auf die Neuberechnung der gesamten Auswertung zu warten; Umschalten, Eintragen und Löschen zeigen das Ergebnis direkt.
- „Kontostände“ bei Bankkonten neu: eingetragene/importierte Stände sind Anker, Monate dazwischen und davor werden von dort aus mit den Buchungen gerechnet (vorher: erster Stand flach fortgeschrieben bzw. eine Depot-Schätzung, die für Bankkonten nicht passt). Die Buchungen bleiben im Kapitalfluss, Abweichungen erscheinen als „Korrektur Kontostand“. Ohne eigene Werte identisch mit „Umsätze“.
- „Umsätze“: eigene Monatswerte zählen dort nicht (Eingabe nur bei „Kontoständen“); ein Import stellt die importierten Konten automatisch auf „Kontostände“.
- Neuberechnung nach Änderungen 6- bis 10-mal schneller: unveränderte Teile (Kategorien-Lernen, Umsatzliste, Steuer, Kapitalfluss nicht betroffener Bereiche, Depot-Verrechnungskonten) werden wiederverwendet; Dateien werden kompakt gespeichert.
- Letzter MoneyMoney-Stand wird verschlüsselt zwischengespeichert: nach einem Neustart (z. B. Update) sind Auswertung und Verlauf sofort da, auch wenn MoneyMoney gesperrt oder geschlossen ist.
- Einrichtung: „Bericht aktualisieren“ aus „Bilanzpositionen & Verlauf“ entfernt (die Auswertung aktualisiert sich nach dem Speichern selbst); Karte „Erste Auswertung erstellen“ nur, solange es noch keine gibt.
- Fehler behoben: Bereichsleiste erschien nach einer Neuberechnung auch auf Seiten außerhalb der Auswertungen.

## 3.5.1
- Verlauf-Fenster: Umschalten zwischen „Umsätze“ und „Kontoständen“ wirkt sofort (vorher zeigte das Fenster bis zum Ende der Neuberechnung die alte Quelle, dadurch schien der Knopf nicht zu reagieren); die Auswahl in der Kontentabelle zieht mit, die Werte aktualisieren sich nach der Neuberechnung von selbst; Fehler werden angezeigt.
- Speichern im Verlauf-Fenster deutlich schneller (Bericht wird nicht mehr bei jeder Anfrage kopiert).
- „Stände“ heißt jetzt „Kontostände“.

## 3.5.0
- Dienst lädt neue Versionen selbst: liegt im Programmordner eine neue Version (Update, git pull), startet er sich neu, sobald kein Abgleich und keine Berechnung läuft; die geöffnete Seite lädt sich danach neu. Vorher lief nach einem Update der alte Code mit der neuen Oberfläche weiter (Ursache für Hänger beim Verlauf und die nicht funktionierende Update-Prüfung).
- Protokoll beginnt bei jeder neuen Version eine frische Datei (ältere bleiben als kontor.log.1 … .5; je höchstens 5 MB).
- Neues Symbol: weißes K auf Blau mit weißem Rand, auch als Symbol für den iPhone-Home-Bildschirm.
- Verständlichere Begriffe: „Abgleich“ statt „Lauf“, „Testmodus“ statt „Probelauf“, „Jetzt buchen“ statt „Scharf ausführen“; Status unten links kompakt mit Erklärung.
- Einrichtung: Verbindung ohne verwirrende Hinweise (Bereiche, Belegordner), Erklärung der Berechtigung nur im Hilfe-Symbol, Knöpfe statt Links; Bereiche ohne „Kennung“ (wird intern vergeben), Hauptbereich klar erklärt.
- Ungespeicherte Änderungen: „Weiter“ fragt „Speichern und weiter?“, Wegnavigieren fragt „verwerfen?“.
- Bilanzpositionen & Verlauf: inaktive Konten werden standardmäßig angezeigt.

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
