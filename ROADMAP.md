# Fahrplan

Reihenfolge = Priorität. Jeder Punkt ist fertig, wenn alle Kriterien erfüllt sind, die Tests grün sind und die Version
veröffentlicht ist (Skill `release`). Geprüfte Seiten verlieren die Markierung „Alpha“.

Geprüft: Bilanz, Synchronisierung, Einrichtung, Einstellungen, Updates, Protokoll, Hilfe, Auto-Buchungen, Buchungsregeln (3.13),
Kategorien und Cashflow (3.13.4: jeder Monat stimmt mit der Bilanz überein, Abweichungen mit Grund; 3.13.6: feste Positionen für alle Bereiche, ohne Kategorie geschätzt); 3.13.10: Kontenspiegel als eigene Regel zwischen beliebigen Konten; 3.13.11: Cashflow in drei Stufen mit Diagrammen, Cashflow-Positionen unter Verwaltung; 3.13.13: Kapitalflussrechnung mit Brücke); Übersicht (3.15.0: vier Grafiken aus Bilanz und Cashflow, ohne eigene Rechnung; 3.15.1: offene Punkte darunter); Kategorisieren (3.15.1: ohne Schalter, Eingetragenes rückgängig machbar; 3.15.2: umbenannt, anfangs nur private Bereiche); Drucken (3.15.1); Übersicht in drei Spalten mit Bilanz-Kacheln (3.15.2); Gesamtprüfung 3.17.0: Schritte 3.16.1–3.16.100 gegen Changelog, Regeln und die Aufträge aller Chats geprüft, fünf unabhängige Sicherheitsprüfungen, 1000 Zufallsfälle, Hilfe und Bilder neu.

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
  ist dort für jedes Programm des Nutzers ohne Rückfrage lesbar.) (umgesetzt in 3.16.83)
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
  Prozess, danach keine Änderungen im selben Chat. (geändert am 22.11.2026 auf Wunsch des Nutzers: Stufe 3 auch ohne Schlüssel über
  Tavilys Zugang ohne Konto, eigener Schlüssel optional für mehr Abrufe; an alle Quellen, auch Wikimedia, nur eine neutrale Kennung –
  Anonymität vor Wikimedias Kennungsregel; lehnt eine Quelle deshalb ab, sagt es die Karte) (umgesetzt in 3.16.48 und 3.16.95;
  BFH über das Rechtsinformationsportal; Feeds von BMF, Bundesbank und EZB. Nicht drin: Destatis-GENESIS – nur mit Konto und Abfragen
  per POST –, deutsche Zahlen über Eurostat und Bundesbank; IWF – neue Schnittstelle seit 2025, Zugang ohne Anmeldung unklar; Feeds von
  Branchenportalen (Stufe 2) sowie von BFH, BaFin und Destatis – Adressen nicht prüfbar)
- **Internetsuche – Freigabe gebündelt (Nutzer, 2026-11-22):** Der Assistent plant seine Recherche zuerst (was, welche Quellen, bis
  zu welcher Stufe) und fragt dann einmal: eine Karte mit allen Abrufen, jeder abwählbar, ein Klick gibt sie frei – danach arbeitet
  er. Was gesendet wird, steht auf der Karte; lange Adressen und die Einzelheiten eines Abrufs klappen auf. Ersetzt oben „jeder
  Zugriff erst nach Freigabe“ durch: jeder Zugriff steht vor dem Klick auf der Karte. (umgesetzt in 3.16.76)
- **Internetsuche – vertrauenswürdige Quellen ohne Rückfrage (Nutzer, 2026-11-22):** Je Chat einmal erlauben, danach sucht und
  liest der Assistent bei vertrauenswürdigen Quellen ohne Freigabe – im Chat als Info; welche Quellen und Websites vertrauenswürdig
  sind, stellt der Nutzer in den Einstellungen ein. Konkrete Websites außerhalb davon immer einzeln freigeben, auch im erlaubten
  Chat. Ersetzt für vertrauenswürdige Quellen „jeder Zugriff steht vor dem Klick auf der Karte“. (umgesetzt in 3.16.92)
- **Gedächtnis des KI-Assistenten:** Er merkt sich von selbst, was dauerhaft ist – über den Nutzer, seine Pläne, Entscheidungen,
  Menschen, Vorlieben und wie er antworten soll –, auch über Finanzen hinaus („zweites Gehirn“, nur auf diesem Mac). „Merk dir …“
  gilt immer, „Vergiss …“ löscht. Nur aus den eigenen Worten des Nutzers, nie aus Buchungstexten, Belegen, Dateien, Webseiten oder
  Werkzeug-Ergebnissen. Gespeichert sofort; die Antwort zeigt „Gemerkt: …“ mit „Rückgängig“. Jede Notiz mit Datum und Herkunft
  (Unterhaltung); widerspricht eine neue einer alten, ersetzt sie diese sichtbar („ersetzt: …“, rückgängig). Zwei Stufen, damit es
  ohne Grenze wachsen kann und jede Anfrage gleich viel kostet: ein Steckbrief in jeder Anfrage (angeheftete, dann zuletzt gemerkte
  und benutzte Notizen; höchstens etwa 1.500 Token, ändert sich selten – der Zwischenspeicher greift) und eine Suche für alles
  andere (Notizen und gespeicherte Verläufe; nur das Passende kommt zur Frage). Beruht eine Antwort auf Gemerktem, sagt er es.
  Liste unter Einstellungen → KI-Assistent: ansehen, ändern, anheften, löschen, alles vergessen. Verschlüsselt, nie im Protokoll
  oder in Paketen; in der Sicherung enthalten; Zurücksetzen und Deinstallieren löschen es. Jedes Merken, Ersetzen und Vergessen
  mit Zeit im Änderungsprotokoll.
  Ergänzt am 22.11.2026: Text, den der Nutzer in seine Nachricht einfügt, zählt als seine eigenen Worte (Notizen daraus tragen den
  Hinweis „aus eingefügtem Text“); „Merk dir das“ zu einer Antwort gilt sofort. Die Suche findet von Anfang an auch nach Bedeutung
  (ein kleines drittes Modell auf diesem Mac, abgeschirmt wie die anderen; ohne es nach Wörtern) – derselbe Baustein dient danach
  auch der Hilfe- und der Umsatzsuche. (teilweise umgesetzt in 3.16.71: verschlüsselte Ablage, Liste in den Einstellungen,
  Steckbrief in jeder Anfrage, Sicherung, Protokoll; 3.16.81: Merken aus dem Chat; 3.16.93: Suche nach Wörtern; 3.16.97:
  nach Bedeutung; 3.16.98: Suche in Verläufen; 3.16.99: Hilfe und Umsätze im Assistenten – die Suchfelder der Seiten noch nach Wörtern)
- **Update-Prüfung:** Bevor ein Update installiert wird, liest die installierte Version die neuen Dateien – ohne etwas davon
  auszuführen – und vergleicht, was über das Programm hinausreicht: Netz, andere Programme, nachgeladener Code, Umwege dorthin,
  Internet-Adressen, Orte, von denen aus der Mac Programme startet, Helfer und Skripte, die Abschirm-Regeln und die Prüfung selbst.
  Nichts Neues darunter: Installation wie bisher mit einem Klick, ohne ein Wort. Sonst wartet das Update – „!“ im Menü bei
  Einstellungen, die Funde unter Updates – und wird nur mit der Freigabe des Nutzers für genau diese Dateien installiert, am Mac.
  Geprüft wird weiter automatisch (täglich), installiert nie von selbst – auch nicht llama.cpp und Modelle des Assistenten.
  Grenze: Die Prüfung engt den Weg für eine untergeschobene Änderung ein, sie schließt ihn nicht (wer sie kennt, kann sie mit
  Aufwand umgehen); der nächste Schritt wäre, den Dienst selbst in macOS' Sandbox ohne ausgehendes Netz laufen zu lassen.
  (umgesetzt in 3.16.61)
- **Assistent aktuell halten:** Kontor fragt von selbst – täglich, einstellbar unter KI-Assistent (täglich, wöchentlich, nie),
  nur solange der Assistent eingeschaltet ist – GitHub nach einem neueren llama.cpp und Hugging Face nach neueren Dateien der
  geladenen Modelle (auch des Diktiermodells); gesendet wird dabei nichts vom Nutzer, geladen nichts. Gibt es etwas für das Modell
  oder das Diktiermodell in Gebrauch, zeigt das Menü bei Einstellungen einen Punkt; für llama.cpp erst, wenn die installierte
  Version zwei Wochen alt ist (es erscheint fast täglich neu). „Alles aktualisieren“ lädt nach einem Klick alles Gefundene
  nacheinander, jedes geprüft wie einzeln. Installiert wird nie von selbst.
  (umgesetzt in 3.16.70)
  Geändert (Nutzer, 2026-11-22): eine gemeinsame Einstellung für llama.cpp, Modell und Diktiermodell statt der Zwei-Wochen-Regel
  für llama.cpp – täglich, wöchentlich, monatlich oder nie, ab Werk monatlich (llama.cpp erscheint fast täglich neu: so kommt der
  Punkt etwa einmal im Monat); der Punkt gilt für llama.cpp und die Modelle in Gebrauch. Letzte Suche und Fund bleiben über
  Neustarts erhalten. (umgesetzt in 3.16.80)
- **Hilfe laufend:** Texte der Hilfe (de/en) und des README werden mit jeder Änderung gepflegt, die sie betrifft – auch in
  kleinen Versionen. Nur die Hilfe-Bilder entstehen weiter erst beim großen Versionssprung. (umgesetzt in 3.16.80)
- **Belege nur in Kontor** (2026-11-22): Der Pfad eines Belegs wird nie in einen Umsatz in MoneyMoney geschrieben (auch nicht in
  den Kommentar); Belege werden nur in Kontor verknüpft und gepflegt. Die Einstellung „Verweis in MoneyMoney“ entfällt.
  (umgesetzt in 3.16.89)

## Offen (Entscheidung steht aus – mit Empfehlung vorlegen, wenn der Punkt dran ist)
- Umsatzsteuer-Voranmeldung direkt an ELSTER senden (ELSTERs Programmbibliothek ERiC, Anmeldung als Hersteller, Zertifikat und
  PIN bei jedem Senden, nie gespeichert; neue Verbindung) – oder Kontor rechnet nur und der Nutzer überträgt die Werte.
- Unabhängig von MoneyMoney: woher dann die Bankdaten kommen.
- Zukunft: eine gemeinsame KI für Nutzer und Geschäftspartner (später Mitarbeiter) auf einem eigenen Rechner mit starker
  Grafikkarte, Zugang je Konto über einen sicheren Kanal, gemeinsames Gedächtnis; widerspricht heute „alles auf diesem Mac“ –
  erst nach ausdrücklicher Entscheidung. (Ein Gedächtnis über Finanzen hinaus, nur auf diesem Mac: entschieden, siehe Gedächtnis.)

## 1. Daten erst nach Anmeldung (Sicherheit) – umgesetzt in 3.16.83 (3.17.0: Umstellung von früher entfernt, nur Neueinrichtung)
Ziel: Wer den entsperrten Mac hat, aber nicht bei Kontor angemeldet ist, kommt an keine Kontor-Daten.

Fertig, wenn
- ~~der Hauptschlüssel nur mit der Anmeldung freikommt (aus dem Passwort abgeleitet bzw. per Touch ID) und nur im Arbeitsspeicher
  des Dienstes liegt; nichts davon frei lesbar im Schlüsselbund oder auf der Festplatte;~~ (3.16.83: `key.json`, Secure Enclave; openssl
  bekommt das Geheimnis über eine Pipe statt der Umgebung)
- ~~nach Neustart oder Update nur die Anmeldung erscheint (am Mac und vom iPhone); Zeitplan und Auto-Buchungen warten sichtbar
  bis dahin und laufen danach weiter, auch gesperrt;~~ (3.16.83)
- ~~die Umstellung ohne Datenverlust geht: der alte Schlüssel verschwindet erst, wenn feststeht, dass der neue alle Daten öffnet;
  Passwort ändern oder vergessen (Touch ID bzw. Mac-Passwort), Touch ID an/aus, Sicherung, Zurücksetzen und Deinstallieren
  funktionieren;~~ (3.16.83)
- ~~Tests: ohne Anmeldung liest nichts im Dienst die Daten; Abbruch mitten in der Umstellung; Agent `reviewer`.~~ (3.16.83)
- offen: am Mac mit echter Secure Enclave prüfen (Touch ID nach Neustart, „Passwort vergessen“, Datenordner von einem anderen Mac)

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
Kasten am Mauszeiger, nicht im Chat), Wert/Zeile/Spalte kopieren, im Bezug die Stelle in der Grafik und der Pfad der Zeile (3.16.27); Zahlen in Grafiken und Karten mit Zeile und Wert, beim Klick
auf den Bezug genau diese Zahl markiert; Gedanken und Schritte einer Antwort als ein Eintrag (3.16.35); gespeicherte Verläufe im eigenen Ordner `chats`, Anzahl/Größe in den Einstellungen,
ältere als ein Jahr löschbar, Hinweis bei sehr vielen (3.16.51); Stil ab Werk kurz, direkt, inhaltsdicht (3.16.23); Denkaufwand mit klarer Bedeutung (Schnell: ohne Nachdenken,
Ausgewogen: bis 2.000 Token je Antwort, Gründlich: ohne Grenze; nur oben im Assistenten, je Gerät gemerkt – 3.16.72) und unter jeder Antwort „nachgedacht · Abfragen · Token/s“ (3.16.23). Kontors eigene Mac-App statt Safaris Dock-App: macOS fragt nur einmal nach dem Mikrofon, danach nie wieder; Menüleiste, Downloads, Dock-Abzeichen (3.16.42); ohne eigene Titelleiste: Fensterknöpfe in der Seitenleiste, Seiten wie im Browser (3.16.60, 3.16.63); ⌘F sucht (Seitensuche oder Suchleiste in der App), Tastaturkürzel im Menü und in den Tooltips, die Suche der Hilfe bleibt sichtbar (3.16.64).

Fertig, wenn
- **Gedächtnis** wie unter Entschieden („März teurer: Urlaub“, „Ziel: mit 45 finanziell frei“): von selbst und auf „Merk dir“,
  sofort mit „Rückgängig“, Steckbrief plus Suche, Liste in den Einstellungen, in der Sicherung; Tests: eingeschleuste Sätze in
  Buchungstexten, Belegen, Dateien und Webseiten werden nie gemerkt; der Steckbrief bleibt unter seiner Grenze, auch bei
  Tausenden Notizen; in Arbeit bei einem Chat, in Schritten:
  - [x] 3.16.71 Ablage (`memory-notes-*.json`, höchstens 1.000 Notizen je Datei), Liste unter Einstellungen → KI-Assistent (hinzufügen,
    ändern, anheften, vergessen, alles vergessen, Schalter), Steckbrief in jeder Anfrage, Sicherung, Änderungsprotokoll (Vergessenes
    verschwindet auch dort), nie Zugangsdaten, erkannte Namen aus Notizen nie in der Internetsuche (alle Namen erst, wenn das
    Modell sie beim Merken benennt – nächster Schritt).
  - [x] 3.16.81 Merken aus dem Chat: ein zweiter, getrennter Blick des Modells, der nur die Worte des Nutzers bekommt (nie, was
    Werkzeuge, Seiten, Bezüge, Belege, Dateien oder das Internet lieferten); seine Antwort wird geprüft (beruht auf dem Gesagten,
    jede Zahl wurde gesagt, nie Zugangsdaten). „Gemerkt: …“ mit „Zurücknehmen“ unter der Antwort, „ersetzt: …“, „Vergiss …“ (nur
    auf ausdrücklichen Wunsch, zurückholbar, solange Kontor läuft); „Merk dir das“ nimmt die Antwort davor – nach Internet- oder
    Belegtext in der Unterhaltung erst nach Klick; von einem Gerät, das nur ansehen darf, wird nichts gemerkt.
    Am Mac prüfen: was ein echtes Modell merkt (zu viel, zu wenig), und die Wartezeit bis zum ersten Wort der nächsten Frage
    mit Gedächtnis an und aus (der zweite Blick teilt sich den Zwischenspeicher des Modells mit der Unterhaltung).
  - [x] Suche in Notizen nach Wörtern und Bedeutung; das Passende kommt von selbst zur Frage; er sagt, worauf eine Antwort beruht.
    - [x] 3.16.93 nach Wörtern, ohne Modell: Wortformen, Teile zusammengesetzter Wörter, Tippfehler; das Passende kommt in die Nachricht
      (nicht in den Systemtext, festes Budget, je Unterhaltung nicht doppelt), Lese-Werkzeug `recall`, „Aus deinen Notizen: …“ unter
      der Antwort; benutzte Notizen zählen für den Steckbrief; der zweite Blick bekommt verwandte Notizen über dieselbe Suche.
      Am Mac prüfen: ob ein echtes Modell die passenden Notizen nutzt und ob „Aus deinen Notizen“ die richtigen nennt.
    - [x] 3.16.97 nach Bedeutung: drittes Modell Qwen3-Embedding 0.6B (Apache 2.0, Q8_0 etwa 0,6 GB), abgeschirmt wie das Diktiermodell,
      `--embedding --pooling last`; Einbettungen der Notizen (512 Zahlen, je eine Zahl ein Byte) verschlüsselt neben den Notizen, im
      Hintergrund gemacht; Wörter und Bedeutung zusammen gewertet; ohne das Modell bleibt die Wortsuche.
      Am Mac prüfen: Start mit `--embedding` in der Sandbox, ob das Endzeichen `<|endoftext|>` als Zeichen ankommt, Schwellen der
      Ähnlichkeit (`memory.SEM_FLOOR`/`SEM_MIN`) mit echten Notizen, Dauer für Tausende Notizen.
  - [x] Suche in gespeicherten Verläufen (aus Unterhaltungen mit Internet-Text nur die Fragen des Nutzers; Vergessenes taucht nicht wieder auf).
    3.16.98: eigenes verschlüsseltes Suchverzeichnis (`memory-chats-*.json`), mit jeder Antwort nachgeführt, ältere Verläufe im
    Hintergrund; über `recall` (Wörter und Bedeutung); auch Unterhaltungen mit Belegtext nur mit den Fragen; gelöschte Verläufe
    und vergessene Notizen räumen mit auf.
  - [x] Bedeutungssuche auch für Hilfe und Umsätze. 3.16.99: im Assistenten (`search_help`, `search_transactions` – Funde nach
    Bedeutung gekennzeichnet), Einbettungen im Hintergrund; dazu benennt das Modell Namen in von Hand angelegten Notizen (Filter
    der Internetsuche). Offen: die Suchfelder der Hilfe- und der Umsatzseite suchen weiter nach Wörtern (nach Wunsch mit demselben
    Baustein). Am Mac prüfen: Schwelle für Umsätze (`memory.SEM_MIN`) mit echten Gegenparteien.
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
- [x] 3.16.33 Auto-Buchungen prüfen, freigeben, zurückhalten (Freigeben nur am Mac, die Karte sagt: in MoneyMoney nicht rückgängig; Zurückhalten zurücknehmbar).
- [x] 3.16.45 Buchungsregeln (Darlehen, Beteiligungen, Kontenspiegel) anlegen und ändern; Buchungen daraus erst zur Freigabe, bis du die Regel unter Konten & Regeln bestätigst.
- [x] 3.16.26 Offene Aufgaben beim Öffnen, jede mit „Erledigen“ (die Liste kommt von Kontor, auch ohne Modell; ohne passendes Recht „Öffnen“).
- [x] 3.16.46 Belege: Datei in den Chat, Texterkennung von macOS (offline), passenden Umsatz vorschlagen, Abweichungen nennen, ablegen und verknüpfen (Verweis in MoneyMoney nicht durch den Assistenten).
- [x] 3.16.66 Excel-Tabellen im Chat: abgesichert gelesen zu einem Raster mit Excels Adressen, Summen exakt von Kontor; Datei ohne Frage wird für sich bewertet. Grundlage für BWA/SuSa aus Excel (4.).
- [x] 3.16.88 PDFs und Bilder mit Tabellen im Chat: alle Seiten, Tabellen über Seitenumbrüche zusammengesetzt (Köpfe, Seitenzahlen weg), Spalten aus der Lage der Wörter, Zahlen wie geschrieben, Summen von Kontor. Offen: am Mac mit echten Auswertungen (BWA, SuSa, Wertenachweis) prüfen; CSV über denselben Weg.
- [x] 3.16.48 Internet nur zum Lesen, in drei Stufen (siehe Entschieden): Kontor sucht (nicht das Modell), Freigabe je Zugriff mit Quelle,
  Suchbegriffen und Adressen, Filter gegen eigene Daten, Seiten in einem abgeschotteten Prozess, danach keine Änderungen im selben Chat.
  Am Mac mit echtem Netz prüfen (Abschirmung des Abrufs, Antworten der Quellen).
- [x] 3.16.92 Internet: je Chat einmal erlauben, danach vertrauenswürdige Quellen und Websites ohne Rückfrage (einstellbar), andere
  Websites immer einzeln; Treffer vorab freigeben entfällt.
- [x] 3.16.76 Internet: erst die Recherche planen, dann eine Karte für alle Abrufe (jeder abwählbar, ein Klick), höhere Stufe als
  Reserve „nur falls nötig“, Treffer lesen mit derselben Freigabe; Adresse und Gesendetes je Abruf aufklappbar.
- [x] 3.16.95 Weitere amtliche Quellen (Stufe 1): Rechtsinformationsportal des Bundes (Gesetze, Urteile auch des BFH), Meldungen von BMF
  (Steuern, Presse), Bundesbank und EZB, OECD, Weltbank, BIZ; Datengruppen der Bundesbank (z. B. Unternehmensabschlüsse), Branchenzahlen von
  Eurostat (SBS); eine anonyme Kennung an alle Quellen, „Quelle lehnt ab“ auf der Karte. Stufe 3 auch ohne Schlüssel (Tavilys Zugang ohne
  Konto, Kontor stoppt bei 200 Abrufen in 31 Tagen; mit eigenem Schlüssel bei 950; nie beides in einer Anfrage). Nicht drin: Destatis-GENESIS
  (Konto, POST), IWF (neue Schnittstelle, Zugang unklar), Feeds von Branchenportalen, BFH und BaFin (Adressen nicht prüfbar). Am Mac einmal echt prüfen.

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

## Demo (Wunsch des Nutzers, 2026-11-22)
- [x] 3.16.87 Demo-Modus zum Vorzeigen: klein und hellgrau unten auf der Anmeldeseite, ohne Passwort; erfundene Beispieldaten
  (`demo.py`, zwei Jahre bis heute), alles bedienbar außer Einstellungen und Einrichtung; eigener verschlüsselter Ordner,
  eigene Sitzung, eigener Assistent mit demselben Modell (ohne deine Verläufe, ohne Internet); „Beenden“ oder Sperre löscht alles.
- [x] 3.16.96 Demo als eigene Umgebung (Wunsch des Nutzers): nur mit deiner Anmeldung (Passwort oder Touch ID), gesperrt bleibt sie
  und öffnet wieder wie zuvor (weg nach zwei Stunden ohne Anmeldung oder mit dem Ende des Dienstes); Assistent mit deinen Rechten,
  auch Internet; Beispieldaten: Privatperson vier Jahre, Muster UG zwei Jahre (gegründet mit Stammeinlage, Geschäftsführergehalt),
  Parkweg GbR mit Immobilie und Kaufpreisdarlehen.
- Später: Assistent mit vorbereiteten Beispielfragen in der Demo; Firmenwert der UG aus EBITDA, sobald es die gibt.

## Laufend
- Sicherheit vor allem: nichts in MoneyMoney kaputt machen, keine Daten nach außen.
- Jede Rechenlogik mit Abstimmungstests (Summen müssen aufgehen) und, wo Zustände sich ändern, mit Zufallsläufen.
- Neue Lebensfälle (Einlage, Kauf, Darlehen, Auslage …) als Szenario in `tests/test_scenarios.py` ergänzen – je Tag, Monats- und Jahreswechsel –
  und als Ereignis in den Zufallswelten (`tests/test_worlds.py`), damit sie nachts in allen Kombinationen laufen.
- Oberfläche nach Apples Human Interface Guidelines, hell und dunkel, Mac und iPhone.

## ~~Beim nächsten großen Versionssprung~~ (erledigt in 3.17.0)
Hilfe und README als Ganzes auf den Stand gebracht (Ziel „dein digitaler CFO“, Mac-App, Rechtsklick, Sammelkarte des Assistenten,
Gedächtnis, Internet, Daten erst nach Anmeldung, Netzverbindungen), Hilfe-Bilder neu.

## Offen nach der Gesamtprüfung 3.17.0
- Am Mac mit echter Hardware prüfen: Touch ID nach Neustart (Secure Enclave), Diktieren mit echtem Mikrofon, Sandbox-Profile der
  Modelle und des Lesers, echte Modelle (was das Gedächtnis merkt, Wartezeit), echte Auswertungen (BWA, SuSa) als PDF.
- Prüfung vor dem Update: engt untergeschobene Änderungen ein, schließt sie nicht aus; nächster Schritt wäre der Dienst selbst in
  macOS' Sandbox ohne ausgehendes Netz.
- Filter der Internetsuche: Ziffern statt Buchstaben, rückwärts Geschriebenes und Umlaut-Schreibweisen erkennt er erst ab sechs
  Buchstaben (kürzere Namen gingen so durch); „Q3 2025“ lehnt er als lange Ziffernfolge ab – jede Suche steht vorher auf einer Karte im Chat.
- Abschirmung: harte Links im eigenen Zwischenordner könnten pfadbasierte Regeln umgehen – am Mac prüfen, dann `(deny file-link*)`.
- Beschädigte Dateien: Planung, Kategorien und Belegindex nennen die Seiten mit Dateinamen (nicht beiseitegelegt); sind Einstellungen,
  Stand und Anmeldedaten zugleich beschädigt, sperrt die Anmeldung („Schlüssel passt nicht“) – ein falscher Schlüssel sieht gleich aus.
- Planung: Zinsen und Anteile in der Vorschau noch mit gerundeten Kommazahlen (gebucht wird exakt).
- Suchfelder der Hilfe- und der Umsatzseite suchen nach Wörtern (nach Bedeutung nur im Assistenten).
