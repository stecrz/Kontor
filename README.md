# Kontor

Bilanz, Kapitalfluss, Planung, Steuerübersicht, Belege und automatische Gegenbuchungen auf Basis von [MoneyMoney](https://moneymoney-app.com) (macOS). Ein kleiner Dienst, der dauerhaft auf dem Mac läuft, mit einer Web-Oberfläche unter `http://127.0.0.1:8765/`. Nur Bordmittel (Python 3, `openssl`, `security`, `osascript`), keine Fremdbibliotheken, keine Konten- oder Zugangsdaten außerhalb von MoneyMoney, keine Netzverbindung außer der abschaltbaren Update-Prüfung bei GitHub.

Kontor enthält keine Annahmen über deine Konten. Alles – Bereiche, Regeln, Kategorien, Steuerzuordnung – wird in der Oberfläche eingestellt oder als Einstellungspaket (`….kontor.json`) geladen.

## Was MoneyMoney macht und was Kontor macht

| MoneyMoney | Kontor |
|---|---|
| Holt Umsätze und Salden von Banken, Depots, Zahlungsdiensten (auch über Erweiterungen). | Liest diese Daten über die Skript-Schnittstelle – nur lesend. Zugangsdaten sieht Kontor nie. |
| Kategorisiert Umsätze (von Hand oder per Regel), führt Budgets. | Führt eigene Kategorien: Baum aus MoneyMoney übernommen, Regeln aus den bisherigen Zuordnungen gelernt, offene Umsätze in Kontor zuordnen – MoneyMoney-Kategorien sind nur Startpunkt und Rückfall. Legt in MoneyMoney keine Kategorien an, benennt keine um, löscht keine; optional schreibt Kontor eine Zuordnung dorthin zurück (Einstellung, standardmäßig aus). Budgets als Planmethode. |
| Führt Offline-Konten (manuell): private Darlehen, Beteiligungen, Immobilien, Kapitalkonten. | Bucht nach deinen Regeln **ausschließlich in solche Offline-Konten**: Darlehensraten spiegeln und Zinsen berechnen, Beteiligungswert = Anteil × Nettowert einer Kontengruppe, Saldo-Spiegel (Faktor × Konto). Jede Buchung trägt eine Markierung und wird nie doppelt angelegt. Bestehende Buchungen werden nie geändert oder gelöscht. Bank- und Erweiterungskonten werden nie bebucht; Überweisungen und Lastschriften sind in beiden Schichten der Anbindung gesperrt. |
| Ruft Konten bei den Banken ab (von Hand oder nach Zeitplan). | Verwendet, was MoneyMoney hat, und zeigt beide Stände unten links: letzter Bankabruf in MoneyMoney und wann Kontor zuletzt gelesen hat (automatisch im eingestellten Abstand, sofort mit „Synchronisieren“). Konten, die beim Bankabruf zurückbleiben, werden gemeldet. |
| – | Bilanz je Bereich, Kapitalfluss mit Prüfzeile, rollierende Planung (je Zeile anpassbar, Vorschlag bleibt sichtbar), Steuer-Jahresübersicht je Entität, Depots, Belege zu Umsätzen als Dateien, Excel-Export, Einstellungspakete, Updates. |

## Sicherheit

- Oberfläche nur auf diesem Mac (`127.0.0.1`); optional eine Tailscale-Adresse (`100.64.0.0/10`) für das eigene iPhone – nie `0.0.0.0`, nie das LAN. Keine Fremdinhalte (CSP `default-src 'self'`), keine Telemetrie.
- Passwort (PBKDF2-SHA256, 600 000 Runden) oder Touch ID (nur am Mac; bei der Einrichtung und in den Einstellungen wählbar – eingeschaltet fragt die Anmeldung nur nach Touch ID, das Passwort gibt es über „Stattdessen Passwort eingeben“). Sitzungscookie HttpOnly/SameSite=Strict, CSRF-Token, Origin-Prüfung, 5 Fehlversuche → 5 Minuten Sperre, automatische Sperre nach Leerlauf.
- Alle Dateien im Datenordner sind verschlüsselt (AES-256-CBC + HMAC-SHA256), Schlüssel im macOS-Schlüsselbund. Belege liegen als normale Dateien in einem Ordner deiner Wahl.
- Scharfe Läufe, Updates, Kategorisieren und Ordner öffnen nur von diesem Mac aus; vom iPhone nur lesen und planen.
- Das Protokoll enthält keine IBANs, Salden oder Passwörter. Die Diagnosedatei (für Hilfe bei Problemen) maskiert zusätzlich Kontonamen und den Benutzerordner.
- Grenze: Der Datenschlüssel liegt im Login-Schlüsselbund, damit der Dienst nach dem Anmelden ohne Eingabe läuft. Wer den entsperrten Mac bedient, kann ihn lesen – das Oberflächen-Passwort schützt dann den Zugang, nicht die Dateien. FileVault bleibt die Basis.

## Installation

Voraussetzungen: macOS, MoneyMoney, Kommandozeilen-Werkzeuge von Apple (`xcode-select --install`, liefert `python3` und `swiftc`).

1. Eine Zeile im Terminal (Programme → Dienstprogramme → Terminal), lädt nach `~/Kontor` und richtet alles ein:
   ```
   bash <(curl -fsSL https://raw.githubusercontent.com/stecrz/Kontor/main/get.sh)
   ```
   Dieselbe Zeile aktualisiert später auf den neuesten Stand. Alternativ von Hand: `git clone https://github.com/stecrz/Kontor.git ~/Kontor && cd ~/Kontor && bash install.sh`. (Ein ZIP aus dem Browser geht auch, aber Gatekeeper blockiert dann Skripte per Doppelklick – deshalb gibt es keine Installieren-Datei zum Anklicken; `bash install.sh` im entpackten Ordner entfernt die Sperre. Ein echter Doppelklick-Installer bräuchte eine Apple-Entwicklersignatur.)
2. Der Browser öffnet `http://127.0.0.1:8765/`: Passwort festlegen, dann **Einrichtung** – modulare Bausteine, die sich einzeln und in beliebiger Reihenfolge einrichten lassen: Verbindung zu MoneyMoney, Bereiche (Pflicht), Konten (Bereich, Position, Verlauf), Kategorien & Zuordnen, Regeln, Immobilien, Planung, Steuer, Belege, Betrieb. Jeder Baustein zeigt, ob er eingerichtet ist; Hilfe-Knöpfe (?) erklären jedes Feld. Danach „Bericht erstellen“.
3. Beim ersten Zugriff fragt macOS, ob das Programm MoneyMoney steuern darf (Automation) – erlauben.

`install.sh` ist jederzeit wiederholbar: Es ersetzt den Dienst, lässt Datenordner und Einstellungen unangetastet. Updates gehen aus der Oberfläche (Updates → installieren; lädt den aktuellen Stand des Hauptzweigs von github.com, erkennbar an der Datei `VERSION`), per `python3 kontor.py update --installieren` oder mit der Terminal-Zeile von oben. Entfernen: `python3 kontor.py uninstall` oder `Deinstallieren.command` (fragt, ob Daten und Schlüssel gelöscht werden sollen).

Der Dienst startet beim Anmelden, läuft dauerhaft und startet nach Abstürzen neu (launchd, Label `de.kontor.dienst`).

## Konzepte

**Bereiche.** Ein Bereich ist eine frei zusammengestellte Menge von Konten (Privat, jede Gesellschaft …) mit eigener Bilanz, eigenem Kapitalfluss, eigener Planung, Steuerübersicht, Umsätzen und Belegen. Standardvorschlag: jede Kontengruppe auf oberster Ebene in MoneyMoney. Die Gruppierung in MoneyMoney ist aber keine Voraussetzung – Konten und Gruppen lassen sich beliebig zuordnen, zusammenlegen oder weglassen (Einrichtung → Bereiche); ein Bereich ist der Hauptbereich (gilt als „privat“), Gesellschaften bekommen Art und Anteil.

**Bilanzpositionen.** Jedes Konto hat eine Position: Liquidität, Wertpapiere & Depots, Geldanlagen, Immobilien, Beteiligungen, Sachwerte, Forderungen (verliehenes Geld), Sonstiges, Darlehen & Verbindlichkeiten – sowie außerhalb des Nettovermögens: Kapitalkonten als Eigenkapital (nur ausdrücklich gewählt), Avale & Bürgschaften und „nicht bilanzieren“. Vorschlag in dieser Reihenfolge: Depot → Kontoname (z. B. „Immobilie“, „Darlehen“, „Kapitalkonto“, „Aval“, „Bauspar“) → eindeutiger Kontotyp (Giro, Kreditkarte, Darlehen) → Name der Gruppe in MoneyMoney → übriger Kontotyp; Darlehen, Kautionen sowie Kapital- und Gesellschafterkonten mit Guthaben gelten als Forderung, mit Schuld als Verbindlichkeit (in der Gesellschaft Schuld an den Gesellschafter, privat Forderung; der Wert einer Beteiligung ist dann der Anteil am Rest – stimmt auch bei ungleichen Einlagen). Je Konto überschreibbar (Einrichtung → Konten).

**Verlauf.** Je Konto „Umsätze“ oder „Kontostände“. Umsätze (Standard für Bankkonten): Saldo am Monatsende = heutiger Saldo minus alle späteren gebuchten Umsätze – so rechnet auch MoneyMoney seine Verlaufsgrafik; vorgemerkte Umsätze zählen nicht, wie im Kontostand von MoneyMoney. Kontostände: eingetragene oder importierte Stände sind Anker, die Monate dazwischen und davor rechnet Kontor von dort aus mit den Buchungen; Abweichungen erscheinen im Kapitalfluss als „Korrektur Kontostand“. Depots (ohne Buchungen): letzter bekannter Stand, von Kontor monatlich aufgezeichnet; davor steht – gekennzeichnet mit „vor … unbekannt“ – der erste bekannte Wert. Geschätzt wird nichts. Das Verlauf-Fenster prüft die Rückrechnung: Anfangssaldo vor der ersten Buchung in MoneyMoney, vorgemerkte Umsätze, negative Stände bei Konten, die nicht ins Minus können. Import: CSV oder Excel als Liste (Datum, Konto, Saldo), Tabelle mit Stichtagen in der Kopfzeile oder in der ersten Spalte; importierte Konten werden auf „Kontostände“ gestellt.

**Konten bestätigen.** Bereich, Position und Verlauf jedes Kontos werden einmal bestätigt (Einrichtung → Konten) und fest in Kontor gespeichert; MoneyMoney liefert nur den Vorschlag. Umbenennen, Umgruppieren oder ein anderer Kontotyp in MoneyMoney ändert danach nichts mehr; neue Konten erscheinen als „neu“ mit Hinweis in der Übersicht, bis sie bestätigt sind. Anzeige je Konto: „nach Aktivität“ (ausgeblendet, solange seit N Monaten weder Bestand noch Umsatz – laufend geprüft), „immer anzeigen“ oder „ausblenden“; ausgeblendete Konten zählen in allen Summen. Die Reihenfolge der Bereiche (Einrichtung → Bereiche, ▲ ▼) gilt für die Bereichsleiste; Vorschlag: Hauptbereich, weitere private, dann Gesellschaften. Konten erscheinen überall in der Reihenfolge von MoneyMoney.

**Synchronisierung.** Unten links: letzter Bankabruf in MoneyMoney und wann Kontor zuletzt gelesen hat, dazu die Zahl der Konten, die beim Abruf zurückliegen. Die Seite „Synchronisierung“ zeigt den Stand je Konto und trennt Konten ohne Bankabruf (Offline-Konten: ohne Bank-/Kontonummer, Ziel einer Regel oder von Kontor bebucht – MoneyMoney setzt den Abrufzeitpunkt auch bei ihnen); je Konto änderbar. Verlauf aus der Zeit vor Kontor: Einrichtung → „Kontostände aus MoneyMoney“ – MoneyMoney beenden, „Im Finder zeigen“, die Datei „MoneyMoney.sqlite“ ins Fenster ziehen und das MoneyMoney-Passwort in einem macOS-Fenster eingeben. Kontor erhält nur einen daraus berechneten Schlüssel, entschlüsselt nur im Arbeitsspeicher (ohne Kopie, danach überschrieben), prüft die gefundenen Werte am aktuellen Saldo und speichert nur Monatsend-Stände je Konto, verschlüsselt. Keine Freigabe, in MoneyMoney wird nichts verändert.

**Kategorien.** Kontor führt eigene Kategorien (Menü „Kategorien“): der Baum wird aus MoneyMoney übernommen und ist frei erweiterbar (anlegen, umbenennen/verschieben, löschen mit Umhängen). Je Umsatz gilt: manuelle Zuordnung in Kontor > eigene Regel > gelernte Regel > Kategorie aus MoneyMoney. Regeln lernt Kontor aus vorhandenen Zuordnungen (Gegen-IBAN, Gegenpartei, Gegenpartei + Zweckanfang; ab zwei Umsätzen mit 90 % Eindeutigkeit) und bei jedem Lauf nach; eigene Regeln mit Name/Zweck enthält, IBAN, Richtung, Konto, Betrag. Die Seite „Zuordnen“ zeigt alle Umsätze ohne Kategorie gruppiert nach Gegenpartei mit Vorschlag – Zuordnen plus Regel erledigt die Gegenpartei dauerhaft. Ohne Kategorien funktionieren Bilanz, Vermögensentwicklung, Immobilien, Darlehen und Einnahmen/Ausgaben gesamt; Kategorien braucht es nur für die Aufteilung (Kapitalfluss-Zeilen, Planung je Zeile, Steuer). Zuordnungen und Regeln liegen verschlüsselt in `kategorien.json`.

**Inaktive Konten.** Konten ohne Bestand und ohne Umsatz in den letzten N Monaten (Standard 12; Altdaten, aufgelöste Konten) werden in Bilanz und Planung ausgeblendet, bleiben aber in allen Summen und in der Historie. Je Konto erzwingbar („ausblenden“ / „immer anzeigen“).

**Kapitalfluss.** Einnahmen und Ausgaben nach deinem Kategoriebaum, Investitionen (Umschichtungen in Depots/Anlagen, Einlagen in Beteiligungen), Finanzierung (Tilgung + Zinsen je Darlehen), Bewertung (Wertänderungen von Depots und manuelle Buchungen), Unklar. Umbuchungen zwischen eigenen Konten werden erkannt (IBAN, Kategorie „Umbuchung“, Paarung ±3 Tage) und nicht als Einnahme/Ausgabe gezählt. Die Prüfzeile „unerklärte Vermögensänderung“ sollte nahe 0 liegen – sonst fehlt eine Kategorie oder Gegenbuchung.

**Planung.** Rollierend aus der Vergangenheit: je Zeile Methode (Ø 12 oder 6 Monate, Vorjahresmonat, fester Betrag, Jahresbetrag/12, MoneyMoney-Budget, keine), Betrag und Steigerung in % p.a.; Ausgaben folgen standardmäßig der Inflation, Einnahmen der eingestellten Rate. Einzelne Monate lassen sich überschreiben (Doppelklick), der Vorschlag bleibt sichtbar und ist jederzeit wiederherstellbar. Darlehensplan: Zins auf den fortgeschriebenen Restsaldo (Jahresbasis oder Restschuld monatlich), Tilgung = Zahlung − Zins. Wertentwicklung je Konto in % p.a. (optional auf feste Basis), Beteiligungskonten wahlweise gekoppelt an das geplante Nettovermögen eines anderen Bereichs (Wert = Anteil × Nettovermögen). **Ereignisse:** einmalige oder wiederkehrende Umschichtungen zwischen Konten (z. B. ein Darlehen auf einen Schlag aus dem Depot zurückzahlen), Einnahmen und Ausgaben – mit Monat, Wiederholung und Enddatum. Immobilienkalkulationen fließen mit Miete, Kosten, Zins, Tilgung, Restschuld, Objektwert und Ausschüttungen ein. Fortschreibung der Bilanz je Position und Konto, Kennzahlen (Sparquote, Reichweite der Liquidität, Zinslast). Schalter „inflationsbereinigt“ zeigt Planwerte in heutiger Kaufkraft. Plan je Bereich, gespeichert verschlüsselt.

**Immobilien.** Je Objekt beliebig viele Kalkulationen (Szenarien), eine davon aktiv. Eingaben: Kaufpreis und Übergang, Nebenkosten (Grunderwerbsteuer, Notar, Grundbuch, Makler; sofort abziehbare Posten getrennt), Gebäudeanteil und AfA-Satz oder Restnutzungsdauer, Nettokaltmiete und Umlage, Leerstand, Mietanpassung (Indexmiete nach VPI mit Weitergabefaktor und Schwelle, fester Satz oder keine), nicht umlagefähige Kosten und Rücklage (mit VPI oder festem Satz), Darlehen (Annuität, Tilgungsdarlehen, endfällig; Abrechnung monatlich wie bei Banken oder jährlich auf den Stand 1. Januar wie bei Verkäuferdarlehen; Sondertilgungen laufend oder einzeln, Zinsbindung mit Anschlusszins, Fälligkeit mit Rückzahlung; nicht abziehbare Zinsen), Gesellschafter mit Anteil und Steuersatz, Ausschüttung für die Steuer, Wertentwicklung, Verkaufsjahr. Ergebnis: Monats- und Jahrestabelle (Miete, Kosten, Zinsen, Tilgung, AfA, steuerliches Ergebnis, Steuer je Gesellschafter, Ausschüttung, Cashflow, Vermögensaufbau, Eigenkapitalrendite, Restschuld, Objektwert), Kennzahlen (Kaufpreisfaktor, Brutto-/Nettomietrendite, Cash-on-Cash, DSCR, LTV, IRR bis zum Verkauf) und Hinweise (offene Fälligkeiten, fehlender Anschlusszins, negativer kumulierter Cashflow). Ungültige Eingaben werden mit Feldname abgewiesen. Verknüpfungen zu MoneyMoney: Vermietungskategorie und Darlehenskonten für den Soll/Ist-Vergleich je Jahr, Objektkonto für den Wert in der Bilanz; „in Planung übernehmen“ speist die Planung des Bereichs; die AfA der aktiven Kalkulation landet in der Steuerübersicht, solange kein Jahreswert von Hand eingetragen ist. Excel-Export je Kalkulation (Eingaben, Kennzahlen, Jahre, Monate). Dokumente (Kaufvertrag, Darlehensvertrag, Gutachten …) werden als Verknüpfung zu Dateien auf dem Mac abgelegt – auch in iCloud Drive; die Dateien bleiben, wo sie sind.

**Spalten.** Überall: Monate, Monate + Jahressummen, nur Jahre. Jahresspalten sind kumuliert (Zahlungsflüsse als Summe, Bestände als Jahresendstand). Die Übersicht zeigt zusätzlich „Vorjahr gleicher Zeitraum“.

**Regeln.** Darlehen (Rate erkennen per Gegen-IBAN oder Text, auf dem Darlehenskonto spiegeln, Zinsen berechnen: Jahresbasis = Satz × Stand 31.12. des Vorjahres, 1/12 je Monat, Dezember mit Cent-Rest; oder Restschuld monatlich), Beteiligungen (Zielkonto = Anteil × Nettowert einer Gruppe), Saldo-Spiegel (Zielkonto = Faktor × Quellkonto, z. B. Kapitalkonto). Probelauf ist Standard: Vorschläge erscheinen unter „Buchungen“, gebucht wird erst nach „Scharf ausführen“ oder dauerhaftem Abschalten des Probelaufs. Bei Problemen (Konto gelöscht, keine passende Zahlung, Zinsbuchung von Hand vorhanden) gibt es Hinweise und Mitteilungen.

**Steuer.** Je Entität (Hauptbereich = privat, andere Bereiche = Gesellschaft mit Anteil aus der Beteiligungsregel) und Jahr: Vermietung je Objekt aus Kategorien `Vermietung \ Objekt \ Art` (beliebig viele Objekte, auch privat), Schuldzinsen je Darlehen (Zuordnung Darlehen → Objekt), AfA als Jahreswert, Steuerpositionen aus Kategorienamen (anpassbar), Buchungen ohne Kategorie als Prüfposten. Belege des Jahres als ZIP mit Übersicht exportieren. Keine Steuerberatung.

**Umsätze & Belege.** Umsatzbrowser mit Filtern (Bereich, Jahr, Konto, Suche, ohne Beleg, ohne Kategorie). Belege (PDF, Bilder, E-Mails, Office-Dateien bis 60 MB) per Datei auswählen, Drag & Drop auf eine Zeile oder am iPhone fotografieren. Ablage als normale Datei im Belegordner (Standard `~/Documents/Kontor-Belege`, Unterordner-Muster z. B. `{jahr}` oder `{jahr}/{entitaet}`), Dateiname `Datum_Betrag_Name_Kennung`. Vorhandene Dateien im Ordner lassen sich nachträglich zuordnen; Dateien außerhalb des Ordners (z. B. in iCloud Drive) lassen sich verknüpfen, ohne sie zu kopieren – mit Anzeige, ob die Datei lokal vorliegt oder noch aus iCloud geladen wird. Der Index liegt verschlüsselt im Datenordner; die Dateien bleiben ohne ihn nutzbar. Löschen aus Kontor betrifft nie verknüpfte Dateien.

**Depots.** Positionen aus MoneyMoney (Menge, Kurs, Einstand, Wert, Gewinn/Verlust).

**Excel.** Jede Tabelle hat einen Excel-Knopf: Bilanz, Kapitalfluss, Planung (mit Fortschreibung und Parametern), Steuer, Umsätze, Depots, Belege, Konten, Immobilienkalkulation.

**Einstellungspakete.** `….kontor.json` enthält Regeln, Bereiche, Bilanzpositionen, Immobilien, Kategorie- und Steuerzuordnungen – ohne Passwörter, Adresse, Port oder Daten (IBANs aus Darlehensregeln sind enthalten). Export mit UUIDs (gleiche MoneyMoney-Installation) oder als Pfade/Namen (andere Installation). Beim Laden werden Konten zugeordnet; was nicht gefunden wird, ordnest du in der Oberfläche zu. Modus „Ergänzen“ ersetzt gleichnamige Regeln, Bereiche und Immobilien mit gleicher Kennung und überschreibt Zuordnungen, „Ersetzen“ verwirft die vorhandene Konfiguration. Vorlagen liegen unter `vorlagen/`.

**Betrieb.** Alle N Minuten (Standard 30) prüft der Dienst, ob MoneyMoney läuft und entsperrt ist, liest die Daten und führt Regeln aus – nur wenn sich etwas geändert hat. Ist MoneyMoney zu oder gesperrt, passiert nichts; der nächste Lauf holt alles nach. Mitteilungen bei Buchungen, Vorschlägen und Fehlern.

## Vom iPhone

Standard: nicht erreichbar. Wenn gewünscht: Tailscale auf Mac und iPhone (gleiches Tailscale-Konto), dann am Mac im Terminal `python3 ~/Kontor/kontor.py tls`. Das holt über Tailscale ein echtes Zertifikat für den MagicDNS-Namen des Macs (in der Tailscale-Admin-Konsole unter DNS müssen MagicDNS und „HTTPS Certificates“ eingeschaltet sein), trägt Adresse und Zertifikat ein und startet den Dienst neu. Am iPhone `https://<mac-name>.<tailnet>.ts.net:8765/` öffnen (der Befehl zeigt die Adresse) und „Zum Home-Bildschirm“. Auf dem Mac bleibt die Oberfläche parallel unter `http://127.0.0.1:8765/` mit Touch ID. Ohne Zertifikat geht es auch über `http://<Tailscale-IP>:8765/` (Adresse in den Einstellungen eintragen) – dann ohne Offline-Ansicht.

Am iPhone gilt: Anmeldung per Passwort; lesen, planen, Belege fotografieren – keine scharfen Läufe, keine Updates, kein Zurücksetzen. Der Mac muss dafür laufen (nicht im Ruhezustand) und mit Tailscale verbunden sein – egal in welchem Netz.

**Offline-Ansicht.** Die als App gespeicherte Oberfläche behält die zuletzt geladenen Daten auf dem iPhone (Service Worker, nur über https). Ist der Mac aus, im Ruhezustand oder nicht verbunden, öffnet das Passwort diese Kopie: alle Seiten lesbar mit Stand des letzten Abrufs, Schreibzugriffe werden abgewiesen, die Sperre nach Leerlauf gilt auch hier. Das Passwort wird dabei auf dem Gerät gegen einen eigenen Prüfwert (PBKDF2-SHA256, 200 000 Runden, eigener Salt) geprüft; die Kopie selbst liegt im Speicher der App (durch die iPhone-Verschlüsselung geschützt, aber nicht zusätzlich mit dem Passwort verschlüsselt – wer das Gerät entsperrt in der Hand hat und mit Entwicklerwerkzeugen arbeitet, käme an die Daten). Einstellungen → „Gespeicherte Daten auf diesem Gerät löschen“ entfernt die Kopie; sobald der Mac wieder erreichbar ist, wird sie beim nächsten Öffnen aktualisiert. Das Zertifikat erneuert der Dienst selbst (Tailscale stellt es für 90 Tage aus).

**Sicherung und Zurücksetzen.** Einstellungen → Sicherung lädt alle Einstellungen, Planung, Kategorien, Verlauf und den Belegindex als eine Datei (`….kontor-sicherung.json`, ohne Passwort, ohne Umsätze); unter Pakete lässt sie sich wieder einspielen. Zurücksetzen (nur am Mac, mit Passwort) löscht Konfiguration, Planung, Kategorien, Verlauf und Auswertungen – wahlweise auch das Passwort; Belegdateien, Schlüssel und Protokoll bleiben.

## Kommandozeile

`python3 kontor.py …`: `start` (Dienst im Vordergrund), `oeffnen`, `run [--probelauf|--scharf] [--force]`, `konten` (Kontenbaum mit UUIDs, Typ, Rolle), `check` (Konfiguration gegen MoneyMoney prüfen), `status`, `passwort` (zurücksetzen), `paket-export [DATEI] [--ohne-uuid] [--mit-plan]`, `paket-import DATEI [--ersetzen] [--trotzdem]`, `diagnose [DATEI]`, `update [--installieren]`, `install` / `uninstall`, `tls [--aus]` (https über Tailscale einrichten), `version`.

## Datenordner

`~/Library/Application Support/Kontor/` (Umgebungsvariable `KONTOR_DIR` ändert das): `config.json.enc`, `plan.json.enc`, `state.json.enc` (Verlauf, Depot-Monatsstände), `kategorien.json.enc` (Kontor-Kategorien, Zuordnungen, Regeln), `dataset.json.enc` (Auswertungen), `umsaetze.json.enc` (Umsatzliste ohne Gegen-IBAN), `belege.json.enc` (Belegindex), `auth.json.enc` (Passwort-Hash), `kontor.log` (Klartext, rotiert bei 5 MB × 5, ausführlich: jede Anfrage, jeder MoneyMoney-Aufruf mit Dauer, Berichtsumfang, Update-Schritte, Fehler mit Rückverfolgung – ohne Passwörter, IBANs oder Beträge). Time Machine sichert den Ordner als Chiffretext; der Schlüssel liegt im Login-Schlüsselbund. Wer den Ordner nicht sichern will: Einstellungen → Time-Machine-Ausschluss. Daten der Vorversion „mmtools“ werden beim ersten Start übernommen.

## Fehlermeldungen

| Meldung | Bedeutung / Abhilfe |
|---|---|
| MoneyMoney läuft nicht / Datenbank gesperrt | MoneyMoney öffnen und entsperren; Kontor wartet und holt nach. |
| Keine Berechtigung (Automation) | Systemeinstellungen → Datenschutz & Sicherheit → Automation: Terminal bzw. python3 darf MoneyMoney steuern. |
| Konto nicht gefunden / mehrdeutig | Regel verweist auf ein gelöschtes Konto oder ein Paket stammt von einer anderen Installation: unter Regeln bzw. Pakete zuordnen. `UUID \| Name` überlebt Umbenennen und Verschieben. |
| Keine passende Zahlung | Darlehensregel findet die Rate nicht: Gegen-IBAN/Text und Quellkonto prüfen. Bis 35 Tage nach „Automatik ab“ nur ein Hinweis. |
| Prüfzeile ≠ 0 | Fehlende Kategorie, fehlende Gegenbuchung oder manuelle Buchung ohne Markierung. |
| Port nicht nutzbar | Ein anderer Dienst (oder Kontor doppelt) belegt den Port: Einstellungen → Port ändern, `bash install.sh`. |
| Datenschlüssel liegt als Datei | Schlüsselbund nicht nutzbar (Anmeldung ohne Schlüsselbund, Terminalsitzung ohne Benutzerkontext): funktioniert, aber der Schlüssel liegt mit Rechten 0600 im Datenordner. |

Für Hilfe bei Problemen: Protokoll → Diagnosedatei (maskiert). Sie enthält Version, Konfiguration mit maskierten Konten, Status und die letzten Protokollzeilen – keine IBANs, Salden, Passwörter oder Benutzerordner.

## Grenzen

- Schreiben nur in manuelle Konten; Markierungen stehen im Verwendungszweck (die Schnittstelle kennt beim Anlegen kein Kommentarfeld).
- Depots liefern über MoneyMoneys Schnittstelle keine Wertehistorie; die Bilanz nutzt die einmalig aus MoneyMoneys Datenbank übernommenen Stände, danach Kontors Aufzeichnung, eigene Einträge oder einen Saldenexport.
- Immobilienkalkulation: Steuer je Gesellschafter als Anteil × Ergebnis × Steuersatz (keine Progression, kein Verlustausgleich); AfA linear; keine Steuerberatung.
- Zinsmodelle sind vereinfacht (30/360, monatlich); einmal jährlich mit der Zinsabrechnung abgleichen.
- Touch ID braucht `swiftc` (Kommandozeilen-Werkzeuge); der Dienst übersetzt den Helfer selbst nach `.touchid/Kontor` (der Name erscheint im macOS-Dialog). Ohne Helfer gilt nur das Passwort.
- MoneyMoney muss laufen und entsperrt sein – Kontor startet es nicht selbst.

## Tests

`python3 -W ignore -m unittest discover -s tests` – Regeln und Zinsmodelle, Kontenbaum und Referenzen, Verschlüsselung, Kern-Lauf gegen ein simuliertes MoneyMoney, HTTP-API (Einrichtung, Anmeldung, CSRF, Sperre, Plan je Bereich, Ereignisse, Konfiguration, Lauf, Belege, Dateiverknüpfungen, Exporte, Pakete, Diagnose), Bereiche unabhängig von der Gruppierung, Positionen, Verlaufsquellen und Saldenimport, inaktive Konten, Immobilienkalkulation gegen eine handgerechnete Tabellenkalkulation (auf den Cent) und über die API bis in Planung und Steuer, und die Oberfläche im Browser (Playwright, falls vorhanden). Testdaten sind frei erfunden.

Lizenz: CC0. Keine Gewähr, keine Steuer- oder Anlageberatung.
