# Fahrplan

Reihenfolge = Priorität. Jeder Punkt ist fertig, wenn alle Kriterien erfüllt sind, die Tests grün sind und die Version
veröffentlicht ist (Skill `release`). Geprüfte Seiten verlieren die Markierung „Alpha“.

Geprüft: Bilanz, Synchronisierung, Einrichtung, Einstellungen, Updates, Protokoll, Hilfe, Auto-Buchungen, Buchungsregeln (3.13),
Kategorien und Cashflow (3.13.4: jeder Monat stimmt mit der Bilanz überein, Abweichungen mit Grund; 3.13.6: feste Positionen für alle Bereiche, ohne Kategorie geschätzt); 3.13.10: Kontenspiegel als eigene Regel zwischen beliebigen Konten; 3.13.11: Cashflow in drei Stufen mit Diagrammen, Cashflow-Positionen unter Verwaltung; 3.13.13: Kapitalflussrechnung mit Brücke); Übersicht (3.15.0: vier Grafiken aus Bilanz und Cashflow, ohne eigene Rechnung; 3.15.1: offene Punkte darunter); Kategorisieren (3.15.1: ohne Schalter, Eingetragenes rückgängig machbar; 3.15.2: umbenannt, anfangs nur private Bereiche); Drucken (3.15.1); Übersicht in drei Spalten mit Bilanz-Kacheln (3.15.2).

## Ziel: dein digitaler CFO
Kontor ist eine Finanzplattform für eine Person, deren Vermögen zu großen Teilen aus Beteiligungen besteht: ein Überblick über
das Privatvermögen und die Gesellschaften dahinter – und ein KI-Assistent, der wie ein loyaler, kompetenter Finanzchef (CFO)
mitarbeitet. Alles lokal auf dem Mac. Zuerst für den Nutzer selbst.

- **Kein Haushaltsbuch.** Schwerpunkt Beteiligungen, Immobilien und Darlehen – privat, in kleinen Gesellschaften (z. B. GbR mit
  mehreren Immobilien) und in großen (GmbH bis etwa 100 Mio. € Umsatz, auch mit eigenen Beteiligungen).
- **Von der Gesellschaft ins Privatvermögen.** Je Gesellschaft Bilanz und Cashflow, daraus ein Firmenwert nach wählbarem
  Verfahren – heute der Stand des Bereichs (Buchungsregel Beteiligung), künftig z. B. EBITDA × Vielfaches nach Bereinigungen per
  Regel (Geschäftsführergehalt, Sonderkosten). Der Anteil fließt automatisch ins Privatvermögen, auch über mehrere Stufen.
- **Gesellschaften auch führen, nicht nur ansehen.** GbR: Objekte mit Kalkulation, AfA, Steuer, Umsatzsteuer-Voranmeldung,
  Nebenkostenabrechnung und Ausschüttungen an die Gesellschafter für ihre Steuer (steuerlicher Gewinn trotz Tilgung ohne
  Geldzufluss). GmbH: Zahlen aus der Buchhaltung (DATEV über das Data-Warehouse, BWA, SuSa, Wertenachweise), denn Bankdaten
  allein kennen weder Zahlungsziele noch Verbindlichkeiten oder Ware. Kontor ersetzt die Buchhaltung nicht, es liest sie.
- **Der KI-Assistent ist der Kern.** Ein lernender Mitarbeiter: kennt alle Zahlen, merkt sich, was der Nutzer ihm sagt (ohne
  feste Grenze), erklärt die Lage jederzeit, findet Muster, Auffälligkeiten, Risiken und Aufgaben und meldet sie von selbst,
  vergleicht (Benchmarking) und nimmt Routinearbeit ab – über Regeln, die der Nutzer einmal bestätigt.
- **Grundlage MoneyMoney** (Bankdaten, Kategorien); auf lange Sicht auch ohne MoneyMoney nutzbar – dann ist es eine Quelle unter mehreren.

## Leitlinien (in dieser Rangfolge)
1. **Sicherheit.** Niemand außer dem Nutzer kommt an Kontor oder seine Daten, niemand kann über Kontor etwas verändern. Der echte
   Kontozugriff bleibt bei MoneyMoney: nie Überweisungen (auch keine vorausgefüllten), in MoneyMoney nur der enge, geprüfte
   Schreibrahmen aus `CLAUDE.md`. Eingeschleuste Befehle (in Buchungstexten, Dateien, Belegen, Antworten des Modells) lösen
   nichts aus – deshalb führt die KI nie selbst aus, sie schlägt vor.
2. **Privatsphäre.** Alle Daten bleiben auf dem Mac, verschlüsselt, lesbar erst nach Anmeldung bei Kontor. Standard: offline.
   Verbindungen nur, wo der Nutzer sie zugelassen hat (fest eingestellt oder je Zugriff freigegeben), nie mit seinen Daten nach außen.
3. **Kontrolle.** Alles sichtbar, abschaltbar, rückgängig zu machen; der Assistent jederzeit zu stoppen.
4. **Nachvollziehbarkeit.** Jede Aktion (Einträge, ausgeführte Regeln, Gemerktes, Abrufe) steht mit Zeit und Auslöser im
   Protokoll – Inhalte der Unterhaltungen nie.
5. **Richtig statt geschätzt.** Jede Zahl mit Herkunft (Ist, Plan, Annahme; Quelle und Stand); Unbekanntes heißt „unbekannt“;
   Summen gehen auf den Cent auf.

## Entschieden (Nutzer, 2026-11-21)
Gilt, sobald beim jeweiligen Punkt umgesetzt; dann in `CLAUDE.md` (Sicherheit) übernehmen und hier „(umgesetzt in X.Y.Z)“
anhängen – nie löschen.
- **Reihenfolge:** Sicherheit vorab, dann KI, dann GbR-Entlastung, dann Gesellschaften (Bewertung, Data-Warehouse), dann Planung.
- **Automatik:** Die KI schlägt Regeln vor (z. B. „Umsätze von X immer Kategorie Y“); nach einmaligem Klick führt Kontor sie
  selbst aus – sichtbar, protokolliert, abschaltbar, jedes Ergebnis rückgängig zu machen. Die KI selbst ändert nie etwas.
  Ersetzt „Kontor ordnet nie selbst zu“ durch: nur über so bestätigte Regeln.
- **Daten erst nach Anmeldung:** Kontors Daten sind ohne Anmeldung (Passwort oder Touch ID) unlesbar, auch für jemanden am
  entsperrten Mac; der Schlüssel liegt danach nur im Arbeitsspeicher, bis der Dienst endet. Nach Neustart oder Update einmal
  anmelden, danach läuft alles im Hintergrund weiter, auch bei gesperrtem Kontor. (Heute liegt der Schlüssel im Schlüsselbund und
  ist dort für jedes Programm des Nutzers ohne Rückfrage lesbar.)
- **Data-Warehouse (BigQuery):** eigener Zugang nur zum Lesen (Dienstkonto mit Leserecht auf die nötigen Daten und Recht zum
  Abfragen), einmal am Mac eingerichtet; Kontor speichert ihn selbst verschlüsselt, an die Anmeldung gebunden (nicht frei lesbar im
  Schlüsselbund), nur im Arbeitsspeicher entschlüsselt; nie im Protokoll, in Sicherungen, Paketen oder für die KI erreichbar.
  Verbindung nur zu Googles Adressen für BigQuery und Anmeldung, nur feste Abfragen aus Kontors Code (kein freies SQL), nichts
  nach außen außer der Abfrage. Abschaltbar; bei Google jederzeit widerrufbar. Ausnahme von „keine Zugangsdaten speichern“.
- **Name:** Untertitel „Dein digitaler CFO“; in der Oberfläche heißt er weiter „KI-Assistent“.
- **Internetsuche (nur lesen):** kostenlos, ohne Kreditkarte, nur über offizielle Schnittstellen, in drei Stufen – der Assistent
  nimmt die erste, die passt: (1) Wissen, Recht, Zahlen ohne Konto: Wikipedia/Wikidata, Gesetze im Internet, Rechtsinformationsportal
  des Bundes, BMF/BFH, GLEIF, Destatis, Bundesbank, EZB, Eurostat, OECD; (2) Nachrichten und Branche ohne Konto: tagesschau-Suche,
  GDELT, Feeds der Portale – nur frei Zugängliches, nie an Bezahlschranken vorbei; (3) allgemeine Websuche nur mit eigenem
  kostenlosem Tavily-Schlüssel des Nutzers (Kontor stoppt vor dem Freikontingent), ohne Schlüssel keine Stufe 3. Kein Abgreifen
  von Suchmaschinen ohne Schnittstelle (DuckDuckGo verbietet es). Jeder Zugriff erst nach Freigabe mit Quelle, Suchbegriffen und
  Adresse; Kontor sucht (nicht das Modell), nur an diese festen Adressen, nie mit eigenen Daten; Seiten liest ein abgeschotteter
  Prozess, danach keine Änderungen im selben Chat.

## Offen (Entscheidung steht aus – mit Empfehlung vorlegen, wenn der Punkt dran ist)
- Umsatzsteuer-Voranmeldung direkt an ELSTER senden (ELSTERs Programmbibliothek ERiC, Anmeldung als Hersteller, Zertifikat und
  PIN bei jedem Senden, nie gespeichert; neue Verbindung) – oder Kontor rechnet nur und der Nutzer überträgt die Werte.
- Unabhängig von MoneyMoney: woher dann die Bankdaten kommen.
- Zukunft: eine gemeinsame KI für Nutzer und Geschäftspartner (später Mitarbeiter) auf einem eigenen Rechner mit starker
  Grafikkarte, Zugang je Konto über einen sicheren Kanal, gemeinsames Gedächtnis; widerspricht heute „alles auf diesem Mac“ –
  erst nach ausdrücklicher Entscheidung. Ebenso ein Gedächtnis über Finanzen hinaus („zweites Gehirn“).

## 1. Daten erst nach Anmeldung (Sicherheit)
Ziel: Wer den entsperrten Mac hat, aber nicht bei Kontor angemeldet ist, kommt an keine Kontor-Daten.

Fertig, wenn
- der Hauptschlüssel nur mit der Anmeldung freikommt (aus dem Passwort abgeleitet bzw. per Touch ID) und nur im Arbeitsspeicher
  des Dienstes liegt; nichts davon frei lesbar im Schlüsselbund oder auf der Festplatte;
- nach Neustart oder Update nur die Anmeldung erscheint (am Mac und vom iPhone); Zeitplan und Auto-Buchungen warten sichtbar
  bis dahin und laufen danach weiter, auch gesperrt;
- die Umstellung ohne Datenverlust geht: der alte Schlüssel verschwindet erst, wenn feststeht, dass der neue alle Daten öffnet;
  Passwort ändern oder vergessen (Touch ID bzw. Mac-Passwort), Touch ID an/aus, Sicherung, Zurücksetzen und Deinstallieren
  funktionieren;
- Tests: ohne Anmeldung liest nichts im Dienst die Daten; Abbruch mitten in der Umstellung; Agent `reviewer`.

## 2. KI-Assistent: digitaler CFO
Ziel: Ein lernender, verlässlicher Mitarbeiter, der die Finanzen kennt, sich erinnert, von selbst auf Wichtiges hinweist und
Routine abnimmt – ohne je selbst etwas zu ändern.

Stand (seit 3.16.0, ohne „Alpha“ seit 3.16.3): llama.cpp und Modelle unter Einstellungen → KI-Assistent laden, aktualisieren, wählen, starten, stoppen –
Kontor schlägt das Modell passend zum Arbeitsspeicher vor; Seitenfenster auf jeder Seite und als eigene Seite; liest alle Zahlen
(Übersicht, Bilanz, Cashflow, Vergleiche, Planung, Steuer, Immobilien, Kategorien, Auto-Buchungen, Offenes), Umsätze mit Belegen,
Hilfe und die offene Seite; öffnet Ansichten und hebt Zeilen hervor; trägt Kontostände, Planwerte, Annahmen und Ereignisse nur
nach Klick ein (zurücknehmbar); Diktieren mit eigenem Sprachmodell; Rechte einzeln schaltbar; Modelle ohne Netz, abgeschirmt
(macOS-Sandbox); Hilfe-Abschnitt und Bilder; Diagramme im Chat aus Kontors eigenen Zahlen (3.16.11, Klick zeigt die Zahl auf
ihrer Seite); gespeicherte Unterhaltungen unter „Verläufe“ (3.16.11, verschlüsselt, nicht in Sicherungen, abschaltbar); Diktat
bis zehn Minuten, live in Stücken und am Ende als Ganzes, nur mit Sprache (Stille und Rauschen erreichen das Modell nicht);
Dateien über „+“ (3.16.12; Bilder und PDFs erst mit einem Modell, das Bilder sieht); Rechtsklick auf Zahl, Zeile, Spaltenkopf, Grafik oder markierten Text: „KI-Assistent fragen …“ – der Bezug steht
knapp vor der Frage, ein Klick darauf öffnet die Stelle wieder (3.16.23); im selben Menü „Kurz erklären“ (sofort, in einem kleinen
Kasten am Mauszeiger, nicht im Chat), Wert/Zeile/Spalte kopieren, im Bezug die Stelle in der Grafik und der Pfad der Zeile (3.16.26); Stil ab Werk kurz, direkt, inhaltsdicht (3.16.23); Denkaufwand mit klarer Bedeutung (Schnell: ohne Nachdenken,
Ausgewogen: bis 2.000 Token je Antwort, Gründlich: ohne Grenze) und unter jeder Antwort „nachgedacht · Abfragen · Token/s“ (3.16.23).

Fertig, wenn
- **Gedächtnis:** merkt sich Fakten und Erklärungen aus den eigenen Worten des Nutzers („März teurer: Urlaub“) – nie aus
  Buchungstexten, Dateien, Belegen oder Werkzeug-Ergebnissen; jedes Gemerkte erscheint sofort mit „Rückgängig“; Liste unter
  Einstellungen → KI-Assistent zum Ansehen, Ändern, Löschen; verschlüsselt, nie in Paketen oder im Protokoll; ohne feste Grenze:
  das Modell holt sich per Suche, was zur Frage passt (Gemerktes und gespeicherte Verläufe);
- **Hinweise von selbst:** nach jedem Abgleich prüft Kontor (fester Code) auf Auffälliges – gestiegene Ausgaben, ungewöhnliche
  Umsätze, Fristen (Voranmeldung, Zinsbindung), Liquidität, offene Kategorien, Sicherheitslage (Zugang, Freigaben, Updates) –
  und zeigt es unter Offenes; der Assistent erklärt und ordnet ein, Gemerktes zählt (bekannter Grund, kein Alarm);
- **Regeln statt Einzelklicks** (siehe Entschieden): Vorschläge aus wiederkehrenden Mustern; Liste der Regeln mit Herkunft,
  Ausführungen, Abschalten; jedes Ergebnis rückgängig zu machen;
- **Protokoll:** jede Aktion – Vorschlag angenommen, Regel ausgeführt, Gemerktes, Eintrag, Rücknahme – mit Zeit und Auslöser;
- **Vergleiche:** Zeiträume, Bereiche, Objekte, Gesellschaften; Vergleichszahlen von außen als Datei oder über die freigegebene
  Internetsuche (unten);
- **eingeschleuste Befehle wirkungslos:** Tests mit präparierten Buchungstexten, Dateien, Belegen – nichts gemerkt, keine Regel,
  kein Eintrag ohne Klick;
- am Mac mit echten Modellen geprüft: Abschirmung (kein Netz, kein Zugriff auf Kontors Daten), Start, Antworten, Stoppen, Diktieren;
- ~~Kategorien zuordnen als Vorschlag mit Klick möglich ist, wie unter Kategorisieren~~ (3.16.19).
- am iPhone ein Bezug ohne Rechtsklick geht (langes Drücken öffnet dort schon Zeilen);

Mächtiger und trotzdem sicher (Auftrag vom 21.11.2026; jede Änderung erst nach Klick, je Schritt eine kleine Version):
- [x] 3.16.13 Sammelfreigabe: alle Änderungen einer Antwort auf einer Karte, ein Klick (einzeln abwählbar); Änderungsprotokoll; Änderungsrechte ab Werk an.
- [x] 3.16.19 Kategorien zuordnen (Vorschlag je Gegenpartei, Klick, rückgängig wie unter Kategorisieren; vom iPhone erst am Mac).
- [ ] Auto-Buchungen prüfen, freigeben, verwerfen (die Karte sagt: in MoneyMoney nicht rückgängig).
- [ ] Buchungsregeln (Darlehen, Beteiligungen, Kontenspiegel) anlegen und ändern; Buchungen daraus immer erst zur Freigabe.
- [x] 3.16.26 Offene Aufgaben beim Öffnen, jede mit „Erledigen“ (die Liste kommt von Kontor, auch ohne Modell; ohne passendes Recht „Öffnen“).
- [ ] Belege: Datei in den Chat, Texterkennung von macOS (offline), passenden Umsatz vorschlagen, Abweichungen nennen, ablegen und verknüpfen.
- [ ] Internet nur zum Lesen, in drei Stufen (siehe Entschieden): Kontor sucht (nicht das Modell), Freigabe je Zugriff mit Quelle,
  Suchbegriffen und Adressen, Filter gegen eigene Daten, Seiten in einem abgeschotteten Prozess, danach keine Änderungen im selben Chat.

## 3. GbR-Entlastung: Immobilien, Steuer, Umsatzsteuer
Ziel: Eine vermögensverwaltende GbR lässt sich mit Kontor führen – Objekte, Steuer, Voranmeldung, Nebenkosten, Ausschüttungen –
und Kalkulation, Ist-Zahlen und Steuer passen zusammen.

Fertig, wenn
- Objekte je GbR verknüpft sind und Soll (Kalkulation) und Ist (MoneyMoney) je Jahr nebeneinander stehen: Miete, Kosten, Zinsen, Restschuld;
- die Steuer-Jahresauswertung je Entität (privat, je GbR, GmbH) aus Kategorien, AfA und Zinsen entsteht und sich gegen den Cashflow abstimmt;
- AfA aus der Kalkulation kommt und von Hand überschrieben werden kann;
- die Umsatzsteuer-Voranmeldung je Monat oder Quartal aus den Kategorien entsteht (Umsätze nach Steuersatz, steuerfrei, Vorsteuer)
  – Werte je Kennzahl zum Übertragen in ELSTER, Frist als Hinweis; direktes Senden: siehe Offen;
- die Nebenkostenabrechnung je Objekt und Mieter entsteht: umlagefähige Kosten nach Schlüssel (Fläche, Einheiten, Verbrauch),
  Vorauszahlungen, Nachzahlung oder Guthaben, als Dokument;
- Ausschüttungen vorgeschlagen werden: je Gesellschafter Anteil am steuerlichen Ergebnis und Steuer darauf (Satz je Gesellschafter
  eingestellt, als Annahme gekennzeichnet) gegen die verfügbare Liquidität nach Tilgung; Buchung per Regel, die Überweisung macht
  der Nutzer selbst;
- Tests rechnen auf den Cent gegen handgerechnete Tabellen; ohne „Alpha“.

## 4. Gesellschaften: Bewertung und Buchhaltungsdaten
Ziel: Jede Gesellschaft mit sauberer Bilanz, Kennzahlen und einem nachvollziehbaren Firmenwert, der anteilig ins Privatvermögen
fließt; die Bilanz stimmt mit der des Steuerberaters überein.

Fertig, wenn
- das Bewertungsverfahren je Beteiligung wählbar ist: Stand des Bereichs (heute), Substanzwert (Vermögen minus Schulden, etwa für
  Immobilien-GbR), EBITDA × Vielfaches; Bereinigungen per Regel (Geschäftsführergehalt, Sonderkosten, Einmaliges) ergeben das
  bereinigte EBITDA, Nettofinanzschulden werden abgezogen; jeder Wert mit Herleitung und Stand; über mehrere Stufen;
- BWA, SuSa und Wertenachweise je Gesellschaft als Datei geladen werden können (CSV, Excel, PDF), lokal und verschlüsselt gespeichert;
- das Data-Warehouse (BigQuery) angebunden ist wie unter Entschieden: Konten, Salden, Buchungen; Abruf nach Zeitplan;
- Posten, die auf keinem Bankkonto stehen (Ware, Forderungen und Zahlungsziele, Verbindlichkeiten, Rückstellungen,
  Gewinnvortrag), in Bilanz und Übersicht erscheinen, gekennzeichnet mit Stand und Quelle; Bilanzsumme abgestimmt;
- Kennzahlen je Gesellschaft (Umsatz, Rohertrag, EBITDA, Liquidität, Working Capital, Verschuldung) auch bei Hunderttausenden
  Buchungen schnell da sind;
- der Assistent eigene Werkzeuge für BWA/SuSa, Lohnabrechnungen, Bewertung und Kennzahlen hat;
- Tests mit erfundenen Exporten; ohne „Alpha“.

## 5. Planung
Ziel: Eine glaubwürdige Vorschau auf Vermögen und Liquidität.

Fertig, wenn
- die Planung aus den Ist-Zahlen fortschreibt (je Cashflow-Position, Budgets aus MoneyMoney), Darlehen und Immobilien einbezieht und Ereignisse kennt;
- jede Zahl ihre Herkunft zeigt (Ist, Plan, Annahme); nichts wird geschätzt, ohne es so zu kennzeichnen;
- Tests prüfen Fortschreibung, Zinseszins und Grenzen; Hilfe und Bilder aktuell; ohne „Alpha“.

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
- [x] 3.15.13 Kontenspiegel erkennt Gegenbuchungen von Hand mit einigen Tagen Abstand; Auto-Buchungen mit Bereich; Ausgaben je Monat: stärkste Farbe für den höchsten Wert, ✦ für neu, Skala bis 100 %; Einrichtung: Weg zum nächsten Schritt unter der Verbindung.
- [x] 3.15.14 Kontenspiegel: Paare von Hand nur am selben Tag; mit Tagen Abstand „prüfen“, abgewählt, beide Hälften auf einmal verwerfen.
- Danach: Hinweis bei gemischten Kategorien (etwa eine Immobilien-Kategorie mit Kaufpreis, Auszahlung und Miete), Kategorisieren je Empfänger in einem Schritt, Fortschritt „sicher zugeordnet / geschätzt“.

## Laufend
- Sicherheit vor allem: nichts in MoneyMoney kaputt machen, keine Daten nach außen.
- Jede Rechenlogik mit Abstimmungstests (Summen müssen aufgehen) und, wo Zustände sich ändern, mit Zufallsläufen.
- Neue Lebensfälle (Einlage, Kauf, Darlehen, Auslage …) als Szenario in `tests/test_scenarios.py` ergänzen – je Tag, Monats- und Jahreswechsel.
- Oberfläche nach Apples Human Interface Guidelines, hell und dunkel, Mac und iPhone.

## Beim nächsten großen Versionssprung (Hilfe, README, Bilder)
- Hilfe: Rechtsklick → KI-Assistent „Kurz erklären“ / „Im Chat fragen“ (Bezug, Sprung zurück), Kopieren, „Grafik drucken …“ bei allen Grafiken (3.16.23, 3.16.27).
- README und Hilfe: Ziel „dein digitaler CFO“ (siehe oben) als Einleitung; Netzverbindungen nach dem Stand dann.
- Hilfe: eigener Abschnitt „Assistent“ (einrichten, Rechte, was er nie darf, Abschirmung) mit Bildern; README (Netzverbindungen).
- Hilfe Assistent: Änderungen nur noch über die Sammelkarte am Ende einer Antwort (statt „Eintragen“ je Karte), Änderungsrechte ab Werk an (bisher „anfangs aus“), Protokoll der Änderungen unter Einstellungen → KI-Assistent.
- Hilfe Assistent: Diagramme im Chat und „Verläufe“ (gespeicherte Unterhaltungen, Einstellung „Verläufe speichern“) mit Bild (3.16.11).
- Hilfe-Bilder und -Texte neu: Übersicht (drei Spalten, Kennzahlen), Kategorisieren, Cashflow-Positionen (Empfehlung), Buchungsregeln (Bereich + Konto) – 3.15.2 hat nur die Texte angepasst.
