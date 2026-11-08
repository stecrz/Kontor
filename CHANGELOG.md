# Änderungen

## 3.9.30 (2026-11-08)
- Bilanz: unter der Tabelle zwei eigene Kurven – Nettovermögen allein und die Summe frei wählbarer Positionen (Standard: Bankguthaben, handelbare und gebundene Anlagen), je mit eigenem Zeitraum, Zoom und einer Achse, die sich den sichtbaren Werten anpasst.
- Tabellen: Planwerte blass und schraffiert, laufender Monat nur blass (statt blau), über die ganze Spalte.
- Abgleich: liest nur die letzten 30 Tage und prüft jeden Kontostand; passt einer nicht (z. B. nachträgliche Buchung mit altem Datum), liest Kontor sofort alles. Vollständig sonst alle 7 Tage (einstellbar); „bevorzugt nachts“ entfällt.
- Adressen der Oberfläche englisch (z. B. #planning, #settings/access, #help/…); alte Lesezeichen leiten weiter. Hilfe-Dateien und Bilder englisch benannt.
- Einrichtung mit Tätigkeiten benannt („MoneyMoney verbinden“, „Historische Kontostände einlesen“ …).
- Einstellungen → Zugang: „Am Mac“ und „Passwort“ oben, „Zugriff vom iPhone“ darunter. Kontor nennt den Grund, wenn Tailscale nicht verbunden ist, prüft auf Knopfdruck neu und fragt Tailscale bei Bedarf in der Sitzung des Nutzers ab. Neu: „Absichern“ mit fertiger Tailscale-Regel, die nur Kontor erreichbar macht; Zertifikat auch mit der App-Store-Version von Tailscale.
- Updates: Änderungen der neuesten Version direkt sichtbar, frühere aufklappbar; Einstellungen → Updates führt zur Seite Updates.

## 3.9.29 (2026-11-08)
- Hilfe neu: dieselbe ausführliche Anleitung wie auf GitHub (docs/hilfe.md, docs/help.md), mit Bildern, Inhaltsverzeichnis, Suche und Sprungmarken. Die „?“ führen per Klick zum passenden Abschnitt; lange Hinweise auf den Seiten sind gekürzt und verweisen auf die Hilfe.
- README kürzer, mit Bildern des Tools (frei erfundene Daten) und Verweisen in die Hilfe; veraltete Angaben korrigiert.
- Kategorien → Kontor-Kategorien & Regeln: Erklärung passt jetzt zur Regel „MoneyMoney ist maßgeblich“.

## 3.9.28 (2026-11-08)
- Zugriff vom iPhone (Einstellungen → Zugang, auch als Schritt in der Einrichtung): Kontor erkennt Tailscale, zeigt die Einrichtung in fünf Schritten mit Häkchen und schaltet den Zugriff per Knopf ein oder aus (Zertifikat über Tailscale, Neustart automatisch) – kein Terminal mehr nötig.
- Übersicht wer/wo/was: Geräte im Tailscale-Netz, von überall ohne offenen Port, Verschlüsselung und Gültigkeit des Zertifikats; Link zum Kopieren für das iPhone.
- Feineinstellung: „Von unterwegs nur ansehen“ (Standard) oder „ansehen und bearbeiten“; Offline-Ansicht auf dem iPhone abschaltbar. Zugangseinstellungen nur am Mac.
- Ist Tailscale beim Start noch nicht verbunden, öffnet Kontor die Adresse, sobald es geht (vorher erst nach einem Neustart).

## 3.9.27 (2026-11-07)
- Einstellungen neu gegliedert: Allgemein (Betrieb, MoneyMoney, Belege), Zugang, Updates, Steuer (eigener Reiter), Sichern & Zurücksetzen. Bereiche, Konten und Kategorien nur noch in der Einrichtung; „Umsätze lesen (Monate)“ steht unter MoneyMoney und ist erklärt. „Einrichtung prüfen“ (prüft alle Konto- und Kategoriebezüge gegen MoneyMoney) steht jetzt in der Einrichtung.
- Sicherung: nur noch verschlüsselt mit eigenem Passwort (enthält deine Finanzdaten, jetzt auch die aus MoneyMoney übernommenen Kontostände); Laden fragt das Passwort ab. Sichern und Laden nur am Mac.
- Einstellungspaket: immer ohne UUIDs und ohne Planung (zum Weitergeben); Unterschied zur Sicherung oben auf der Seite erklärt.
- Time Machine: Stand wird angezeigt (gesichert/ausgeschlossen), ein Knopf schaltet um. Diagnosedatei nur noch unter Protokoll.
- Updates: Quelle als GitHub-Adresse; Port erklärt.
- Mehr Abstand zwischen Text und Eingabefeldern. Laufender Monat und laufendes Jahr leicht blass (noch nicht abgeschlossen).

## 3.9.26 (2026-11-07)
- Kategorien → Auswahl (auch als Schritt in der Einrichtung): je Kategorie aus MoneyMoney „Eigene Zeile“, „Zur Oberkategorie“ (samt Unterkategorien; Kapitalfluss und Planung, Steuer bleibt genau) oder „Nicht verwenden“ (in Kontor wie ohne Kategorie, erscheint unter Zuordnen). Schnellwahl „Nur oberste Ebene als Zeile“. In MoneyMoney ändert sich nichts.

## 3.9.25 (2026-11-07)
- Kategorien: MoneyMoney ist maßgeblich – hat ein Umsatz dort eine Kategorie, gilt sie. Umsätze ohne Kategorie ordnest du in Kontor zu.
- „Kategorien zurückschreiben“ (Einstellungen oder „Einschalten“ unter Kategorien, nur am Mac): Zuordnungen aus Kontor setzt Kontor auch in MoneyMoney – nur das Kategoriefeld, direkt vorher neu gelesen und geprüft. Eine vorhandene andere Kategorie nur nach Rückfrage („In MoneyMoney ersetzen“ oder „Nur in Kontor“); von Kontor gesetzte lassen sich ohne Rückfrage ändern.
- Fehlt die Kategorie in MoneyMoney, wartet die Zuordnung (Hinweis unter Kategorien) und wird nach dem Anlegen beim nächsten Abgleich nachgetragen.
- Kategorienbaum aus MoneyMoney mit vollständigen Pfaden (vorher nur der Name der Kategorie).
- Umsätze: Mehrfachauswahl ordnet über denselben geprüften Weg zu. „Datei hierher ziehen“ im Umsatzfenster wieder richtig beschriftet.

## 3.9.24 (2026-11-07)
- Schnelleres Lesen: Ein Abgleich liest nur die Umsätze der letzten drei Monate aus MoneyMoney und übernimmt ältere aus dem letzten vollständigen Lesen. Vollständig gelesen wird alle 24 Stunden (einstellbar, nachts schon nach 12), nach eigenen Buchungen und mit „Alles neu lesen“ (Synchronisierung).
- Bankabruf ohne neue Daten: keine Neuberechnung mehr, nur die Abrufzeiten werden aktualisiert.
- Neuberechnung etwas schneller (Regeln lernen nur beim vollständigen Lesen, Kapitalfluss ordnet jede Kategorie nur einmal ein).

## 3.9.23 (2026-11-07)
- Sync-Knopf: Zeigt nach dem Abgleich wieder „Sync“, auch wenn währenddessen ein automatischer Abgleich lief oder das Fenster im Hintergrund war (Status wird während eines Abgleichs alle 3 s und beim Zurückkehren ins Fenster sofort geprüft).
- Automatischer Abgleich nach neuen Daten in MoneyMoney: wartet, bis MoneyMoney mit dem Abruf fertig ist (45 s ohne weitere Änderung), statt je Bank einen eigenen Lauf zu starten; was ein Abgleich gerade gelesen hat, löst keinen zweiten Lauf mehr aus.

## 3.9.22 (2026-11-07)
- Einrichtung → Konten: Hinweis „Vorschlag: …“ unter den Feldern entfällt. Gestrichelt = Vorschlag gewählt, durchgezogen = eigene Wahl (jetzt bei allen Konten); der Vorschlag steht weiter in der Auswahl.
- Sprache überall als Auswahlliste (Anmeldung, Einrichtung, Einstellungen); in der Einrichtung nicht mehr abgeschnitten.
- Einrichtungsschritt „Verbindung“ heißt „MoneyMoney-Verbindung“.

## 3.9.21 (2026-11-07)
- Einstellungen in Reitern: Allgemein, Zugang, Updates, Sichern & Zurücksetzen.
- Updates: automatische Prüfung täglich, wöchentlich oder nie (Einstellungen → Updates); die Updates-Seite zeigt die Einstellung mit Link.
- Bilanz: „Geld unterwegs“ heißt „Geldtransit“; ein Klick zeigt die erkannten Buchungspaare. „Wertpapiere“ heißt „Handelbare Anlagen“ (auch Krypto und Edelmetall).
- Bilanz: Plan immer an, Planwerte blasser statt gelb; der Plan reicht immer bis Dezember. Aufgeklappte Positionen zeigen ihre Konten in der Grafik.
- Konten mit Umsätzen: Sind alle Umsätze geladen, gibt es vor dem ersten Umsatz keinen Stand mehr – wie in MoneyMoney.

## 3.9.20 (2026-11-07)
- Kontostände aus MoneyMoney, Depots: Manche Depots führen in MoneyMoney zusätzlich einen Eintrag mit dem Depotwert insgesamt (die Summe ergab deshalb genau das Doppelte). Kontor erkennt diesen Eintrag, prüft ihn über seinen ganzen Verlauf gegen die einzelnen Wertpapiere und nimmt dann ihn als Depotwert.

## 3.9.19 (2026-11-07)
- Bilanz: Positionen „Verbindlichkeiten“ und „Gebundene Anlagen“ (Festgeld, Bausparvertrag, Lebens-/Rentenversicherung); „(rechts: Plan)“ entfällt. Englisch in gängiger Finanzsprache: Cash, Securities, Term deposits & pensions, Real estate, Private equity, Receivables, Liabilities.
- Bilanz-Grafik: Standard 1 Jahr; Auswahl 1 J, 3 J, 10 J, Alle; Feld mit der Zahl der angezeigten Monate (eigene Zahl eingeben); Bedienhinweis nur noch im Fragezeichen.
- Seitenleiste: Knopf „Sync“ (gleich breit wie „Sperren“); Ladesymbol unten links sitzt richtig.
- Kontostände aus MoneyMoney: Bei nicht übernommenen Depots nennt das Protokoll Alter des letzten Punkts und Verhältnisse zum Depotwert (nur Prozent).

## 3.9.18 (2026-11-07)
- Kontostände aus MoneyMoney, Depots: Jedes Wertpapier wird für sich gelesen (Wert zum jeweiligen Zeitpunkt); der Depotwert ist die Summe der gehaltenen Wertpapiere, ein verkauftes zählt nach seinem letzten Wert nicht mehr. Übernommen, wenn das den heutigen Depotwert ergibt.
- Vor der ersten Aufzeichnung in MoneyMoney gilt der Stand davor (bei neuen Konten und Depots 0) statt „unbekannt“ mit dem ersten Wert. Neues Einlesen ersetzt den bisherigen Stand vollständig.
- Verlauf-Fenster: „Monat ergänzen“ fügt den eingegebenen Monat ein; die Grafik zeigt beim Darüberfahren Monat und Stand.

## 3.9.17 (2026-11-07)
- Kontostände aus MoneyMoney: MoneyMoney speichert je Konto und Tag die Veränderung, nicht den Saldo (Protokoll: 100 % der Tage passen so). Kontor rechnet die Monatsend-Stände jetzt wie MoneyMoney rückwärts vom aktuellen Saldo; Depots über die Wertveränderung ihrer Wertpapiere, wenn deren Summe den aktuellen Depotwert ergibt. Künftig datierte Punkte werden berücksichtigt. Die ausführliche Fehlersuche im Protokoll ist wieder entfernt.

## 3.9.16 (2026-11-07)
- Einrichtung → Verbindung: Fortschrittsbalken beim Lesen aus MoneyMoney (Konten, Umsätze, Depotbestände, Kategorien); die Dauer schätzt Kontor aus dem letzten Lesen.
- Kontostände aus MoneyMoney: Konten, deren Verlauf nicht zu den Umsätzen passt, verhindern nicht mehr die Übernahme der übrigen (vor allem der Depots); sie behalten die Salden, die Kontor aus ihren Umsätzen rechnet. Vergleich jetzt auf den Cent genau. Das Protokoll prüft für solche Konten mehrere Deutungen (nur Anteile, keine Beträge).

## 3.9.15 (2026-11-07)
- Kontostände aus MoneyMoney: Der Verlauf wird jetzt an den Salden geeicht, die Kontor aus den Umsätzen kennt (auch, ob ein Punkt den Stand vom Vortag zeigt, z. B. am Monatsersten). Ein Konto wird nur übernommen, wenn mindestens 70 % seiner Punkte passen. Gelesen wird ausschließlich (nur SELECT); ein Test stellt das sicher. Scheitert die Erkennung, nennt das Protokoll nur Anzahlen zur Fehlersuche.
- Bilanz-Grafik: Waagerechtes Wischen verschiebt den Ausschnitt bei gleicher Länge (auch am Rand); Zusammen-/Auseinanderziehen zoomt (auch in Safari); Doppelklick vergrößert auf den halben Zeitraum. Die Grafik ist immer sichtbar.
- Verlauf-Fenster eines Kontos: mit Grafik; Klick daneben schließt es.
- Übersicht: Klick auf eine Kachel oder Grafik öffnet Bilanz bzw. Kapitalfluss.
- Positionen: „Bankguthaben“ (grün), „Wertpapiere“ (blau), „Festgeld & Vorsorge“, „Forderungen“.
- Updates: alle Änderungen früherer Versionen aufklappbar.

## 3.9.14 (2026-11-07)
- Kontostände aus MoneyMoney: liest jetzt MoneyMoneys tatsächliche Tabellen – Saldo-Verlauf (balance_chart) und für Depots den Wert der Wertpapiere je Abruf (portfolio_chart). Konten werden über IBAN, sonst Kontonummer + BLZ, sonst Namen zugeordnet; gleichnamige Konten entscheidet der aktuelle Saldo. Übernommen wird nur, was eindeutig passt.

## 3.9.13 (2026-11-07)
- Bilanz: „Geld unterwegs“ unter Liquidität – Umbuchungen zwischen eigenen Konten, die am Monatsende abgebucht, aber erst im Folgemonat gutgeschrieben sind (oder umgekehrt), zählen am Monatsende mit; das Nettovermögen knickt nicht mehr scheinbar ein.
- Ansicht: nur noch „Monate“ (mit Jahressummen, Standard) und „Jahre“. Die Schalter oben rechts sind weg: „Alle Zeilen“ (leere und ausgeblendete) und „Plan“ stehen in der Werkzeugleiste von Bilanz und Kapitalfluss, „inflationsbereinigt“ nur in der Planung. Plan ist standardmäßig an.
- Bilanz: die zweite Sicht „MoneyMoney-Gruppen“ entfällt.
- Menü kürzer: „Zuordnen“ ist ein Reiter unter „Kategorien“, „Pakete“ ein Reiter unter „Einstellungen“ (Sicherung & Pakete), die Seite „Depots“ entfällt – die Positionen eines Depots stehen oben in seinem Verlauf-Fenster.
- Anmeldeseite ohne den Text „Zugang gesperrt.“; Updates zeigen das Datum der Version.
- Aufgeräumt: Übernahme von Daten und Diensten früherer Versionen, deutsche Befehlsnamen und alte Einstellungsformate entfernt; restliche feste Texte (Excel-Export, Fehlermeldungen, Kommandozeile) stehen im Sprachkatalog.

## 3.9.12 (2026-11-07)
- Kontostände aus MoneyMoney: Datenbanken mit Volltextsuche (eigener Tokenizer von MoneyMoney) und eigenen Sortierfolgen werden jetzt gelesen; solche Tabellen werden übersprungen, Vergleiche laufen binär. Das Protokoll nennt das Ergebnis der Suche (nur Tabellen- und Spaltennamen, keine Inhalte).

## 3.9.11 (2026-11-07)
- Bilanz mit Grafik: Zusammensetzung des Vermögens im Zeitverlauf in den Farben der Positionen, mit Nettovermögen, Plan und „heute“. Monatsgenau: Zeigen zeigt Monat und Werte, Ziehen vergrößert, 1/3/5/10 Jahre oder alles, Klick springt zur Spalte der Tabelle. Abschaltbar.
- Tabellen (Bilanz, Kapitalfluss, Planung): Spalten rasten ein – die erste sichtbare Spalte ist nie mehr angeschnitten, auch ganz rechts.
- Englisch als zweite Sprache: Auswahl auf der Anmeldeseite, in der Einrichtung und in den Einstellungen. Alle Texte stehen gebündelt in einem Katalog (web/i18n.js), auch die Meldungen des Dienstes.
- Kontostände aus MoneyMoney: Bibliothek wird robuster gewählt (Fallback, falls macOS-SQLite die Speicherfunktion fehlt).
- Entfernt: die nicht mehr genutzte Schätzung von Depotständen aus Käufen/Verkäufen samt Verrechnungskonto-Einstellung.

## 3.9.10 (2026-11-07)
- Kontostände aus MoneyMoney: Fehler nach dem Entschlüsseln behoben (Programmfehler beim Öffnen der Datenbank im Arbeitsspeicher auf dem Mac).

## 3.9.9 (2026-11-07)
- Technische Namen auf Englisch, die Oberfläche bleibt Deutsch (Grundlage für weitere Sprachen): Programmdateien, Datendateien, Schnittstellen-Adressen, Kommandozeilenbefehle (deutsche Befehle gehen weiter) und Protokollmeldungen.
- Vorhandene Daten werden beim Start automatisch auf die neuen Dateinamen umgestellt; der Hintergrunddienst zieht einmalig unter seinen neuen Namen um.
- `Deinstallieren.command` heißt jetzt `Uninstall.command`, Vorlagen liegen unter `templates/`.

## 3.9.8 (2026-11-07)
- Kontostände aus MoneyMoney als Einrichtungsschritt 4 (nach „Konten“): MoneyMoney beenden, „Im Finder zeigen“ (markiert MoneyMoney.sqlite, ohne Freigabe), Datei ins Fenster ziehen, Passwort im macOS-Fenster. Übernommen wird der Verlauf aller Konten als Monatsend-Stände, nur nach Prüfung am aktuellen Saldo; verschlüsselt gespeichert und in Bilanz und Verlauf-Fenster genutzt (eigene Einträge gehen vor).
- Sicherer und sparsamer: Entschlüsselung an Ort und Stelle, SQLite liest direkt aus diesem Puffer (keine Kopie, Bedarf etwa Dateigröße, Prüfung des Arbeitsspeichers); danach alles mit Nullen überschrieben. Gesucht wird in SQLite, Tabellen mit Zugangsdaten werden nicht angesehen. Verarbeitung im Hintergrund mit Fortschrittsanzeige.
- Dateien umbenannt: Präfix „mm_“ nur noch für Teile, die direkt mit MoneyMoney sprechen (mm_bridge, mm_historie).
- Bereichsauswahl oben mittig, kleine Schalter (Plan, inflationsbereinigt, leere Zeilen) rechts; Ladesymbol im Synchronisieren-Knopf mittig.

## 3.9.7 (2026-11-07)
- Depot-Historie aus MoneyMoney, Schritt 1, ohne jede macOS-Freigabe: Die Datei „MoneyMoney.sqlite“ wird unter Synchronisierung ins Fenster gezogen (bleibt verschlüsselt bis in den Arbeitsspeicher). Das Passwortfenster wird nur für diesen Vorgang erzeugt und danach gelöscht; Schlüssel und entschlüsselte Daten liegen nur in Puffern, die danach mit Nullen überschrieben werden; SQLite schreibt keine Zwischendateien. Kein sqlcipher nötig.
- Der vorab übersetzte Passwort-Helfer aus 3.9.6 wird beim Start entfernt.
- `CLAUDE.md` mit den Projektregeln (Prüfen, Version, Sicherheit).

## 3.9.6 (2026-11-07)
- Depot-Historie aus MoneyMoney, Schritt 1 (Synchronisierung → Depots): „Datenbank prüfen“ liest den Aufbau von MoneyMoneys Datenbank. Das Passwort gibst du in einem eigenen macOS-Fenster ein (kleiner Helfer, wird beim Start übersetzt); Kontor erhält nur den daraus berechneten Schlüssel, entschlüsselt nur im Arbeitsspeicher (macOS CommonCrypto, keine Kopie auf der Festplatte, kein Fremdprogramm), nur lesend und nur bei beendetem MoneyMoney. Währenddessen keine Update-Prüfung.
- Sparsamer im Hintergrund: ohne laufendes MoneyMoney nur einmal pro Minute ein kurzer Blick, mit MoneyMoney alle 30 Sekunden.
- Hinweis, wenn MoneyMoney lief, Kontor aber nicht lesen konnte (z. B. fehlende Berechtigung) – unten links und unter Synchronisierung.

## 3.9.5 (2026-11-07)
- Schnellabgleich: Ist MoneyMoney offen und entsperrt, liest Kontor alle 20 Sekunden nur die Kontenliste (unter einer Sekunde) und merkt sich die Stände – ein kurzer Blick in MoneyMoney genügt. Geänderte Daten lösen danach den vollen Abgleich aus.
- Depotstände zählen für den Monat, in dem MoneyMoney sie abgerufen hat (Abruf am 31., gelesen am 2. → richtiger Monat).
- Hat MoneyMoney ein Depot abgerufen, während Kontor nicht lief, meldet Kontor die möglicherweise fehlenden Monate (Synchronisierung, unten links). Schlief der Mac, gibt es keine Meldung, weil auch MoneyMoney nichts abgerufen hat.

## 3.9.4 (2026-11-07)
- Kein Zugriff auf MoneyMoneys Datenbank: die Prüfung aus 3.9.3 ist wieder entfernt. Kontor nutzt nur MoneyMoneys Skript-Schnittstelle (Freigabe „Automation → MoneyMoney“).
- Synchronisierung: neuer Abschnitt „Depots: Wertverlauf“ – ab wann Stände bekannt sind (eigene Aufzeichnung bzw. eingetragene Werte), mit „Stände eintragen“ je Depot.

## 3.9.3 (2026-11-07)
- Kontostand-Historie aus MoneyMoney, Schritt 1: Unter Einrichtung → Konten liest „Aufbau prüfen“ den Aufbau von MoneyMoneys Datenbank (nur Tabellen- und Spaltennamen, keine Beträge) und legt ihn als „mm-datenbank-aufbau.txt“ in den Kontor-Ordner. Nur am Mac, nur lesend, Passwort wird weder gespeichert noch protokolliert. Voraussetzung: `brew install sqlcipher`.

## 3.9.2 (2026-11-07)
- Einrichtung: oben steht nur „Einrichtung“, darunter der Name des Schritts wie im Einrichtungsplan („Verbindung“, „Bereiche“, „Konten“).
- Einzahl/Mehrzahl: „Ein Konto“ bzw. „N Konten“ statt „Konto/Konten“.
- Verlauf-Fenster: Monate untereinander; das Umstellen zwischen Umsätzen und Kontoständen ist erst eine Vorschau („Speichern“ übernimmt, „Verwerfen“ geht zurück). Aus der Kontentabelle geöffnet, zeigt es die dort gewählte, noch nicht gespeicherte Quelle.
- Keine Schätzung von Depotständen mehr (auch keine Auswahl eines Verrechnungskontos dafür); vor dem ersten bekannten Stand steht gekennzeichnet der erste Wert.
- Kapital- und Gesellschafterkonten werden wie Gesellschafterdarlehen vorgeschlagen: in der Gesellschaft Schuld an den Gesellschafter, privat Forderung. „Kapitalkonten (Eigenkapital)“ bleibt wählbar.
- Vorschlag nur gestrichelt umrandet (ohne Farbe); „Wird neu berechnet …“ passt in eine Zeile.
- Klick auf „Kontor“ führt zur Übersicht, Klick auf die Versionsnummer zu den Updates.

## 3.9.1 (2026-11-07)
- Bilanz: eine Tabelle statt Struktur + Konten – Positionen farbig und aufklappbar (anfangs zugeklappt, „alle aufklappen“), Plan-Spalten rechts in derselben Tabelle statt einer zweiten Tabelle darunter.
- Tabellen scrollen waagerecht zur aktuellen Spalte (Monat bzw. Jahr), auch in der Jahresansicht; mit Plan bleiben die Plan-Spalten rechts im Blick.
- Senkrechte Scrollposition je Reiter: beim Wechsel kommt die zuletzt dort gesehene Stelle (sonst oben), nicht die des vorigen Reiters.
- Depots ohne älteren Stand: Kennzeichen „vor … unbekannt“ (dort steht rückwärts der erste bekannte Wert). Verrechnungskonto für die Schätzung auch ohne Bankleitzahl, wenn Depot und Konto allein in einer Untergruppe liegen.
- Bilanzpositionen & Verlauf: Abweichung vom Vorschlag bleibt unter der Auswahl sichtbar („Vorschlag: …“), auch nach dem Speichern. Ausgegraute Konten folgen sofort der geänderten Monatszahl bei „nach Aktivität“.
- Privat geführtes Kapitalkonto mit Guthaben wird als Beteiligung vorgeschlagen (in einer Gesellschaft bleibt es Eigenkapital); Hilfetext erklärt, warum Kapitalkonten der Gesellschaft nicht doppelt zählen.
- Anmeldung: Touch ID bei der Einrichtung und in den Einstellungen wählbar. Eingeschaltet nur Touch ID (kein Passwortfeld, kein gleichzeitiges Ausfüllen durch den Browser), Passwort über „Stattdessen Passwort eingeben“; ausgeschaltet nur Passwort. Der macOS-Dialog heißt jetzt „Kontor möchte die Finanzübersicht entsperren“ (Helfer wird vom Dienst selbst übersetzt).

## 3.9.0 (2026-11-07)
- Konten überall in der Reihenfolge von MoneyMoney statt alphabetisch (Einrichtung, Bilanz, Gruppenansicht, Synchronisierung).
- Einrichtung · Bilanzpositionen & Verlauf: Konten nach Bereichen gruppiert, in der Reihenfolge unter „Bereiche“; doppelte Unterüberschriften in der Einrichtung entfallen.
- Vorschlag: in der Auswahl immer mit „(Vorschlag)“ gekennzeichnet (auch bei bestätigten Konten); gestrichelt, solange ein neues Konto den Vorschlag trägt – auch nach dem Zurückwechseln. Keine Kursivschrift mehr.
- Neue Seite „Synchronisierung“: Datenstand je Konto (letzter Abruf, Rückstand), Konten ohne Bankabruf getrennt, je Konto festlegbar. Unten links nur noch die beiden Zeitpunkte, ein Hinweis mit Anzahl zurückliegender Konten, Klick führt zur Seite.
- Offline-Konten zählen nicht mehr für den Datenstand: MoneyMoney setzt den Abrufzeitpunkt auch bei ihnen; erkannt werden sie an fehlender Bank-/Kontonummer, an Regeln, die in sie buchen, und an Kontor-Buchungen.
- Kopfzeile: Bereichsauswahl immer oben rechts. Ansicht (Monate/Jahre, Plan, inflationsbereinigt, leere Zeilen) steht in der Werkzeugleiste der Seite neben dem Excel-Export; der Bereichsname wird darunter nicht noch einmal genannt.
- „Verbindung prüfen“ liest jetzt auch die Depotpositionen.

## 3.8.1 (2026-11-07)
- Position und Verlauf bestätigter Konten werden auch beim automatischen Abgleich festgelegt (nicht erst beim nächsten Neuberechnen).

## 3.8.0 (2026-11-07)
- Einrichtung · Bereiche: Reihenfolge mit ▲ ▼ änderbar (gilt für die Bereichsleiste). Vorschlag ohne Einrichtung: Hauptbereich zuerst, dann weitere private Bereiche, dann Gesellschaften; Art-Erkennung wie in der Oberfläche.
- Einrichtung · Bilanzpositionen & Verlauf: kein „auto“ mehr. Position und Verlauf werden fest gespeichert; vorgeschlagen wird nur bei neuen Konten (gestrichelt markiert). Bereits bestätigte Konten mit „auto“ werden beim nächsten Neuberechnen einmalig auf den erkannten Wert festgelegt – Umbenennen, Umgruppieren oder ein anderer Kontotyp in MoneyMoney verschiebt danach nichts mehr.
- Anzeige je Konto: „nach Aktivität“ (laufend geprüft), „immer anzeigen“, „ausblenden“. Grau = ausgeblendet; ändert sich sofort mit der Auswahl. In Bilanz und Depots heißt es „ausgeblendet“ statt „inaktiv“.
- Auswahlfelder gleich breit, „Verlauf…“ steht untereinander.
- Fortschrittsanzeige beim Neuberechnen: feinere Schritte (Kategorien lernen/zuordnen, je Bereich Monatsstände/Zahlungsströme/Bilanz, nach Umsatzzahl gewichtet), laufende Streifen, Sekundenzähler, Balken rückt zwischen den Meldungen weiter.
- Schneller: Liest Kontor unveränderte Daten aus MoneyMoney (automatischer Abgleich, Synchronisieren, Verbindung prüfen), bleiben die Zwischenergebnisse erhalten – die nächste Neuberechnung braucht dann Bruchteile einer Sekunde statt eines vollständigen Durchgangs. Nach einem Neustart ohne erreichbares MoneyMoney wird die Auswertung einmal im Hintergrund vorbereitet; nach „Verbindung prüfen“ ebenso.
- Änderungserkennung genauer: Auch geänderte Texte, Kategorien oder Kontonamen in MoneyMoney gelten als Änderung (vorher nur Salden, Abrufzeit, Umsatzzahl).
- Trifft der automatische Abgleich auf eine laufende Neuberechnung, versucht er es nach einer Minute erneut statt erst im nächsten Intervall.

## 3.7.3 (2026-11-07)
- Datenstand unten links in zwei Stufen: „Banken → MM“ (letzter Bankabruf in MoneyMoney) und „MM → Kontor“ (wann Kontor zuletzt gelesen hat). Konten mit Saldo, die beim Bankabruf mehr als einen Tag zurückliegen, werden gemeldet.
- Neuer Knopf „Synchronisieren“ unten links: liest sofort aus MoneyMoney, wendet bei Änderungen die Regeln an (Testmodus laut Einstellung) und aktualisiert die Auswertungen.
- „Nächster Abgleich“ wird nicht mehr angezeigt; die Infozeile oben in der Übersicht entfällt (alles steht unten links). Buchungsvorschläge erscheinen dort als Link.
- „MoneyMoney aktualisieren“ entfernt (Knopf, Einstellung, Befehl `kontor.py aktualisieren`, Bedienungshilfen-Berechtigung).
- Buchungen: Überschrift „Regeln zuletzt angewendet“ statt „Letzter Abgleich“ – ohne Änderung in MoneyMoney werden die Regeln nicht erneut angewendet.
- Menü scrollt bei kleiner Fensterhöhe, Status und Knöpfe bleiben sichtbar.

## 3.7.2 (2026-11-07)
- Statuszeile zeigt, von wann die Daten aus MoneyMoney stammen („Daten vom …“), statt des Zeitpunkts der letzten Neuberechnung; ohne laufendes MoneyMoney kein „nächster Abgleich“.
- Test: Arbeiten ohne MoneyMoney mit dem zwischengespeicherten Stand (Neustart, Neuberechnung, Verlauf).

## 3.7.1 (2026-11-07)
- Einrichtung · Verbindung: prüft auf der Seite alle 3 Sekunden, ob MoneyMoney läuft und entsperrt ist.
- Einrichtung · Bereiche: Anteil nur bei Gesellschaften (bei „privat“ ausgeblendet).
- Einrichtungsschritte einheitlich: „Speichern“, „Speichern und weiter: …“, „Zurück zur Einrichtung“. „Speichern und weiter“ wartet mit Fortschrittsanzeige, bis die Auswertung aktualisiert ist, und öffnet erst dann den nächsten Schritt (so stimmen dort die Vorschläge).
- Neuberechnung meldet ihren Fortschritt (Schritt und Prozent).

## 3.7.0 (2026-11-07)
- Positionen: Vorschlag neu geordnet – Kontoname vor Kontotyp (z. B. „Immobilie …“ als Festgeldanlage → Immobilien), Gruppenname vor allgemeinem Kontotyp (Sparkonto in „Anlagen“ → Geldanlagen), Bausparer und Versicherungen → Geldanlagen; Darlehen und Kautionen nach Vorzeichen (Guthaben = Forderung, Schuld = Verbindlichkeit); Namen mit Wortgrenzen (z. B. „Haushaltskasse“ ist keine Immobilie).
- Neue Positionen außerhalb des Nettovermögens: „Kapitalkonten (Eigenkapital)“ und „Avale & Bürgschaften“; in der Bilanz unter dem Nettovermögen ausgewiesen. Einlagen/Entnahmen über Kapitalkonten erscheinen im Kapitalfluss. Die Beteiligungsregel bewertet eine Gesellschaft ohne ihre Kapitalkonten (vorher ergab sich so ein Wert nahe 0).
- „nicht bilanzieren“ wird überall so angezeigt (vorher teils „ignorieren“).
- Depot-Schätzung aus Käufen/Verkäufen nur noch über ein Konto derselben Bank (nicht mehr über dieselbe MoneyMoney-Gruppe, was falsche Zusammenhänge erzeugte); im Verlauf-Fenster wählbar oder abschaltbar.
- Verlauf-Fenster prüft die Rückrechnung: Anfangssaldo vor der ersten Buchung, vorgemerkte Umsätze, Konten ohne Umsätze; negative Stände bei Spar-, Tagesgeld-, Festgeld- und Bausparkonten erscheinen als Hinweis.
- Hinweis „veraltet?“ bei Konten mit Saldo, aber ohne Buchung und Aktualisierung seit N Monaten.
- „illiquide“ entfällt als Einstellung; Kennzahl „Finanzielle Unabhängigkeit“ und „liquides Nettovermögen“ aus der Übersicht entfernt; Liquidität mit Reichweite in Monaten.
- Bilanzpositionen & Verlauf: ein Hilfe-Symbol oben, Erklärungen in den Spaltenköpfen; nach dem Speichern nur noch Hinweise mit Handlungsbedarf statt aller geprüften Verweise.

## 3.6.0 (2026-11-07)
- Verlauf-Fenster rechnet das gewählte Konto sofort selbst (unter einer Sekunde, auch bei 190.000 Umsätzen) statt auf die Neuberechnung der gesamten Auswertung zu warten; Umschalten, Eintragen und Löschen zeigen das Ergebnis direkt.
- „Kontostände“ bei Bankkonten neu: eingetragene/importierte Stände sind Anker, Monate dazwischen und davor werden von dort aus mit den Buchungen gerechnet (vorher: erster Stand flach fortgeschrieben bzw. eine Depot-Schätzung, die für Bankkonten nicht passt). Die Buchungen bleiben im Kapitalfluss, Abweichungen erscheinen als „Korrektur Kontostand“. Ohne eigene Werte identisch mit „Umsätze“.
- „Umsätze“: eigene Monatswerte zählen dort nicht (Eingabe nur bei „Kontoständen“); ein Import stellt die importierten Konten automatisch auf „Kontostände“.
- Neuberechnung nach Änderungen 6- bis 10-mal schneller: unveränderte Teile (Kategorien-Lernen, Umsatzliste, Steuer, Kapitalfluss nicht betroffener Bereiche, Depot-Verrechnungskonten) werden wiederverwendet; Dateien werden kompakt gespeichert.
- Letzter MoneyMoney-Stand wird verschlüsselt zwischengespeichert: nach einem Neustart (z. B. Update) sind Auswertung und Verlauf sofort da, auch wenn MoneyMoney gesperrt oder geschlossen ist.
- Einrichtung: „Bericht aktualisieren“ aus „Bilanzpositionen & Verlauf“ entfernt (die Auswertung aktualisiert sich nach dem Speichern selbst); Karte „Erste Auswertung erstellen“ nur, solange es noch keine gibt.
- Fehler behoben: Bereichsleiste erschien nach einer Neuberechnung auch auf Seiten außerhalb der Auswertungen.

## 3.5.1 (2026-11-06)
- Verlauf-Fenster: Umschalten zwischen „Umsätze“ und „Kontoständen“ wirkt sofort (vorher zeigte das Fenster bis zum Ende der Neuberechnung die alte Quelle, dadurch schien der Knopf nicht zu reagieren); die Auswahl in der Kontentabelle zieht mit, die Werte aktualisieren sich nach der Neuberechnung von selbst; Fehler werden angezeigt.
- Speichern im Verlauf-Fenster deutlich schneller (Bericht wird nicht mehr bei jeder Anfrage kopiert).
- „Stände“ heißt jetzt „Kontostände“.

## 3.5.0 (2026-11-06)
- Dienst lädt neue Versionen selbst: liegt im Programmordner eine neue Version (Update, git pull), startet er sich neu, sobald kein Abgleich und keine Berechnung läuft; die geöffnete Seite lädt sich danach neu. Vorher lief nach einem Update der alte Code mit der neuen Oberfläche weiter (Ursache für Hänger beim Verlauf und die nicht funktionierende Update-Prüfung).
- Protokoll beginnt bei jeder neuen Version eine frische Datei (ältere bleiben als kontor.log.1 … .5; je höchstens 5 MB).
- Neues Symbol: weißes K auf Blau mit weißem Rand, auch als Symbol für den iPhone-Home-Bildschirm.
- Verständlichere Begriffe: „Abgleich“ statt „Lauf“, „Testmodus“ statt „Probelauf“, „Jetzt buchen“ statt „Scharf ausführen“; Status unten links kompakt mit Erklärung.
- Einrichtung: Verbindung ohne verwirrende Hinweise (Bereiche, Belegordner), Erklärung der Berechtigung nur im Hilfe-Symbol, Knöpfe statt Links; Bereiche ohne „Kennung“ (wird intern vergeben), Hauptbereich klar erklärt.
- Ungespeicherte Änderungen: „Weiter“ fragt „Speichern und weiter?“, Wegnavigieren fragt „verwerfen?“.
- Bilanzpositionen & Verlauf: inaktive Konten werden standardmäßig angezeigt.

## 3.4.1 (2026-11-06)
- Update-Prüfung liest die Version direkt aus dem Hauptzweig (Datei VERSION) statt aus Tags: neue Versionen werden erkannt, sobald sie gepusht sind; Neuerungen kommen aus CHANGELOG.md. Fallback auf Releases bzw. den höchsten Tag.

## 3.4.0 (2026-11-06)
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

## 3.3.0 (2026-11-06)
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
