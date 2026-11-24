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
- **Name:** Untertitel „Dein digitaler CFO“ (seit 23.11.2026 mit Punkt: „Dein digitaler CFO.“); in der Oberfläche heißt er weiter „KI-Assistent“.
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
  Werkzeug-Ergebnissen (geändert am 23.11.2026: auch aus der Antwort, sinngemäß – siehe „Gedächtnis kompakt“). Gespeichert sofort; die Antwort zeigt „Gemerkt: …“ mit „Rückgängig“. Jede Notiz mit Datum und Herkunft
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
  Geändert (Nutzer, 2026-11-23): Freigeben muss er nur, was wirklich ein Risiko sein kann – ein neuer oder weiterer Weg nach
  außen, eine gelockerte Abschirmung, Code, der ungelesen ankommt oder von selbst startet, eine Änderung der Prüfung selbst.
  Jeder solche Fund mit einer Erklärung in klaren Worten (was er bewirken kann, worauf achten) und aufklappbar den betroffenen
  Zeilen (entfernt/neu). Alles andere (strengere Regeln, gewöhnliche Änderungen) braucht keine Freigabe und steht höchstens
  zusammengefasst darunter. (umgesetzt in 3.17.5)
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
  Geändert (Nutzer, 2026-11-23): llama.cpp ist nur wenige MB groß – Programm und Modelle werden automatisch aktualisiert, gesucht
  wird ab Werk täglich. Ausgestaltet: „Automatisch laden“ (abschaltbar) nur, wenn der Assistent ruht, nur in der strengen
  Abschirmung; von llama.cpp nur eine Fassung, die seit zwei Tagen draußen ist, nie eine ältere; startet eine neue Fassung das
  Modell nicht, nimmt Kontor von selbst die vorige. Kontor selbst bleibt Installation per Klick, ein anderes Modell wählt Kontor
  nie von selbst. (umgesetzt in 3.17.35)
- **Hilfe laufend:** Texte der Hilfe (de/en) und des README werden mit jeder Änderung gepflegt, die sie betrifft – auch in
  kleinen Versionen. Nur die Hilfe-Bilder entstehen weiter erst beim großen Versionssprung. (umgesetzt in 3.16.80)
  Geändert 2026-11-24 (Credits sparen, ohne Fehler zu riskieren): in kleinen Versionen nur die deutsche Hilfe, nur der betroffene
  Abschnitt und nur, wenn sich Bedienung oder Verhalten wesentlich ändert (der Assistent sucht darin); englische Hilfe, README,
  alle Bilder und `HIGHLIGHTS.md` beim großen Versionssprung – dort jeder seit dem letzten Sprung geänderte Abschnitt (Skill `major`).
  Die englische Hilfe ganz zu streichen, nur wenn sie nachweislich viel kostet (heute: wenig). (umgesetzt in 3.17.42)
- **Planung nachvollziehbar und frei wählbar** (2026-11-23): Jede Planzahl zeigt, wie sie entsteht (Regel, Grundlage, Steigerung,
  eigener Wert); gerechnete Kennzahlen (Sparquote, Reichweite, Zinslast) werden gezeigt. Planregeln auf jeder Ebene: Standard des
  Bereichs, Position (Überkategorie), Kategorie (Unterkategorie) – die tiefste Ebene mit eigener Regel gilt, sonst die darüber.
  Methoden: Vorjahr Monat für Monat; Ø der letzten 12 oder 6 abgeschlossenen Monate; fester Betrag; Jahresbetrag; Budget aus
  MoneyMoney; keine. Steigerung je Regel: Standard (Inflation bzw. Einnahmen-Steigerung des Bereichs), keine oder eigene % p.a.;
  typische Planungsmodelle für den ganzen Bereich mit einem Klick wählbar. Jede Zelle einzeln überschreibbar – die Regel gilt für
  die übrigen weiter. Ändert sich eine Regel, unter der eigene Werte oder Regeln weiter unten stehen, fragt Kontor nach und listet
  sie (Zeile, Monat, eigener Wert, neuer Wert): behalten oder ersetzen. (umgesetzt in 3.17.6)
- **Zugang vom iPhone** (2026-11-23): Vom iPhone soll alles gehen wie am Mac; nur sehr Kritisches lässt sich in den
  Einstellungen untersagen. Einzelne Geräte lassen sich am Mac entfernen – danach haben sie keinen Zugriff mehr. Verändernde
  Aktionen müssen am iPhone besonders sicher sein. Der Weg zum Mac (Tailscale oder anders) wird beim Überarbeiten neu bewertet.
  (umgesetzt in 3.17.10)
- **Belege nur in Kontor** (2026-11-22): Der Pfad eines Belegs wird nie in einen Umsatz in MoneyMoney geschrieben (auch nicht in
  den Kommentar); Belege werden nur in Kontor verknüpft und gepflegt. Die Einstellung „Verweis in MoneyMoney“ entfällt.
  (umgesetzt in 3.16.89)
- **KI-Plattform** (Nutzer, 2026-11-23): Kontor bleibt der Kern (Daten, Regeln, Freigaben); Modell und Rechner sind
  austauschbar. Der Assistent läuft weiter auf dem MacBook; vorbereitet wird, dass ein stärkerer eigener Rechner später nur eine
  andere Auswahl ist. Sicher geht vor lokal: lokal ist der Weg, nicht das Ziel. Ein Kauf (Mac Studio o. Ä.) erst, wenn er einen
  entscheidenden Vorteil bringt.
  (vorbereitet in 3.17.9–3.17.33: Modellauswahl mit größeren Modellen; der Aufruf des Modells liegt an einer Stelle,
  `LocalAI._connect` – heute fest der Kindprozess auf diesem Mac, keine Adresse, keine Einstellung; was ein zweiter eigener
  Rechner vorher braucht, steht unter „Offen“)
- **Claude als Recherche-Stufe** (Nutzer, 2026-11-23): Der Assistent darf Claude über Anthropics Schnittstelle fragen – mit dem
  eigenen API-Schlüssel des Nutzers (API-Guthaben seines Claude-Abos), nie über ein Abo-Login –, als stärkere Internetsuche neben
  Tavily: Kontor sendet, vorher steht der volle Wortlaut auf der Karte (immer mit Klick, auch in einer erlaubten Unterhaltung),
  gefiltert gegen eigene Daten; die Antwort gilt als Text aus dem Internet. (umgesetzt in 3.17.15)
- **Modelle verständlich** (Nutzer, 2026-11-23): Die Modellauswahl erklärt jedes Modell in einfachen Worten (schnell oder
  gründlich, wofür gut, Speicherbedarf, ob es auf diesem Mac läuft) und führt auch größere Modelle für stärkere Rechner.
  (umgesetzt in 3.17.9 – die verständliche Auswahl – und 3.17.29 – größere Modelle, auch in mehreren Dateien)
- **Abschirmung** (Nutzer, 2026-11-23): heißt wirklich kein Netz – auch nicht innerhalb des Macs – und möglichst keine
  Verbindung zu anderen Programmen; in der Oberfläche und Hilfe erklärt.
  (umgesetzt in 3.17.33: kein Netz, auch nicht innerhalb des Macs – das Modell lauscht auf einer Datei statt auf 127.0.0.1;
  im Tooltip und in der Hilfe erklärt. Noch offen: Dienste von macOS nur nach Liste – siehe „2. KI-Assistent“)
- **Aktuelles Python** (Nutzer, 2026-11-23): Kontor läuft auf einer aktuellen, festen Python-Version in seinem eigenen Ordner statt
  auf Apples Python 3.9 (seit 31.10.2025 ohne Sicherheitsupdates); geladen nur nach Klick, geprüft, mit Rückweg; Installation und
  Umstellung ohne Handgriffe des Nutzers, wo es irgend geht. (umgesetzt in 3.17.12: Einstellungen → Updates → Python und bei der Installation;
  der Dienst läuft im eigenen Python 3.15, gestartet wird er weiter vom Python des Macs, das nur noch den Starter ausführt –
  startet das eigene nicht, läuft Kontor im selben Start mit dem des Macs weiter. Mindestversion und was am Mac zu prüfen ist: siehe Offen.)
  Nutzer, 23.11.: kein Rückweg nötig – immer das aktuellste Python. (Der Knopf zurück zum Python des Macs entfällt; geladen wird das
  neueste stabile Python, mit dem Kontors Tests grün sind – heute 3.15.2; neuere bietet ein Update von Kontor an, geladen nach Klick.
  Bleibt: vor dem Umschalten geprüft und probegestartet, sonst wird nicht umgeschaltet; Python 3.9 als Startpython und in CI vorerst.)
  Nutzer, 23.11. abends: keine Rücksicht mehr auf Python 3.9 – einfach halten, Kontor läuft im eigenen, aktuellen Python, das
  aktuell bleibt. Apples Python (kommt mit den Kommandozeilen-Werkzeugen, die die Installation für git und Swift ohnehin braucht)
  startet nur noch den Starter; nur `kontor.py` bis `pyboot.ready()` und `pyboot.py` bleiben 3.9-tauglich, getestet wird 3.9 nur
  noch dafür (`tests/test_python.py`), alles andere nur im aktuellen Python. Eine Reserve im Python des Macs gibt es damit nicht mehr
  verlässlich. (umgesetzt in 3.17.37)
- **Ganzes Bild an den Assistenten** (Nutzer, 2026-11-23): Ein Bild im Chat – hochgeladen oder aus der Zwischenablage, kein
  Unterschied – geht als ganzes Bild an das Modell, nicht nur sein erkannter Text (wie bei Claude oder ChatGPT). Einfach halten:
  der Bildteil des Modells wird mit dem Modell geladen, kein eigener Schalter. Zahlen bleiben belegt aus der Texterkennung
  (Entschieden: Zahlen nie aus einem Modell); das Bild hilft für das, was Text nicht hergibt (Aufbau, Grafik, Stempel, Fotos).
  Umsetzung und Prüfungen: siehe Offen „Bilder für das Modell“. (umgesetzt in 3.17.40)
  Geändert (Nutzer, 2026-11-24): der Satz „Zahlen bleiben belegt aus der Texterkennung“ gilt nicht mehr – siehe „Bilder und PDFs wie Text“.
- **Bilder und PDFs wie Text** (Nutzer, 2026-11-24): Ein Bild oder eine PDF ist für das Modell dasselbe wie getippter Text – es
  darf alles daraus lesen, auch Zahlen, Daten und Namen. Grund: auch eine Eingabe kann einen Tippfehler haben; verboten wird nichts,
  geprüft wird dort, wo eine Zahl weiterverarbeitet wird: jede Änderung steht vorher mit ihrer Zahl auf der Karte und wartet auf
  den Klick; eine Zahl auf der Karte, die nicht im erkannten Text der Bilder und PDFs der Unterhaltung steht, ist dort als „bitte
  prüfen“ markiert. PDFs wie bei Claude und ChatGPT möglichst genau: Text und Seitenbilder zusammen; viele Seiten in mehreren
  Schritten (Seite für Seite, Stand im Gedanken-Teil sichtbar). Abgelehnt: „Zahlen nie vom Bild“ als Anweisung an das Modell
  (3.17.40) – ein Chat hatte „Zahlen nie aus einem Modell“ (unten, gemeint: die Form einer Tabelle aus einem Dokumentmodell) zu
  weit auf das Lesen von Bildern übertragen.
- **Fremdes sichtbar benannt** (Nutzer, 2026-11-23): Alles Fremde, das Kontor nutzt – das neue Python, llama.cpp, die Modelle und
  künftige Bibliotheken –, steht für den Nutzer mit Name, Version, Lizenz, Herkunft und „abgeschirmt ja/nein“ in einer Liste unter
  Einstellungen (Updates → „Verwendete Programme“) und kurz in der Hilfe; so angelegt, dass eine künftige Bibliothek nur einen
  Eintrag braucht. (umgesetzt in 3.17.13: `components.py`)
- **Fertige Bibliotheken statt Eigenbau** (Nutzer, 2026-11-23): Wo bewährte offene Bibliotheken oder Modelle eine Aufgabe besser
  lösen – vor allem PDF- und Excel-Lesen, auch KI-Dokumentmodelle für schwierige PDFs –, nutzt Kontor sie: nur in abgeschirmten
  Hilfsprozessen, mit fester Version und Prüfsumme, geladen nach Klick, für den Nutzer mit Name, Version, Lizenz und Herkunft
  benannt. Zahlen kommen dabei nie aus einem Modell, sondern aus der Datei (Textebene oder Texterkennung): ein Modell darf nur
  die Form einer Tabelle liefern. Der Kern (Dienst, Zugang, Schlüssel, Freigaben, Update-Prüfung) bleibt Standardbibliothek.
- **Gedächtnis übertragbar** (Nutzer, 2026-11-23): Notizen lassen sich am Mac in einem offenen Format exportieren und wieder
  einlesen, damit ein anderes System sie übernehmen kann. (umgesetzt in 3.17.11)
  Ergänzt (Nutzer, 2026-11-23): „Import zurücknehmen“ in einem Schritt unter Gedächtnis (nur am Mac) – nimmt genau die Notizen dieses
  Imports zurück, die seitdem nicht geändert wurden, und nennt den Rest; im Änderungsprotokoll mit Anzahl. (umgesetzt in 3.17.19)
- **Tailscale prüfen** (Nutzer, 2026-11-23): Kontor prüft (nur lesend), ob Tailnet Lock aktiv ist und Kontor nicht über Funnel/serve
  aus dem Internet erreichbar ist, und erklärt sonst, wie man es behebt. (umgesetzt in 3.17.10)
- **Antworten vor Tempo** (Nutzer, 2026-11-23): Saubere, richtige Antworten sind wichtiger als Geschwindigkeit. Die Einbindung
  der Modelle (Startparameter, Denken, Systemtext, Werkzeuge, Gedächtnis, Verlauf, Recherche) wird geprüft und so eingestellt,
  dass sie ihr Potenzial ausschöpfen; empfohlen wird nur, was dem Nutzer wirklich etwas bringt.
  (teilweise umgesetzt in 3.17.9: empfohlen wird nur das gründlichste Modell, das gut läuft)
  (geprüft und eingestellt in 3.17.17 – Werte je Modellfamilie, Denken je Schritt, Gedanken bleiben zwischen den Abfragen,
  längere Ergebnisse; Start weiter ohne fremdes Chat-Template und mit dem Zwischenspeicher in voller Genauigkeit; offen: Bildeingabe, siehe Offen)
- **Ursachen statt Aufzählung** (Nutzer, 2026-11-23): Auf „Warum ist … gestiegen oder gefallen?“ zählt der Assistent nicht
  Zeilen auf, sondern verfolgt Zusammenhänge – über Bereiche, Konten, Beteiligungen, Immobilien, Darlehen und Umsätze: Treiber
  finden, eine Ebene tiefer gehen, verknüpfte Bereiche und große Umsätze ansehen, daraus schließen, was vermutlich passiert ist.
  Belegtes und Vermutetes getrennt (Zahlen nur belegt, Vermutung gekennzeichnet und begründet). Als allgemeine Arbeitsweise –
  nie ein fest eingebauter Einzelfall. (umgesetzt in 3.17.17: Arbeitsweise im Systemtext, Lese-Werkzeug `get_net_worth_drivers`,
  Fall in der Demo; am Mac prüfen, ob ein echtes Modell die Ursache schließt)
- **Vorrang** (Nutzer, 2026-11-23): Erst muss das Bestehende verlässlich funktionieren – vor allem PDFs (z. B. ein 30-seitiger
  Wertenachweis aus DATEV) und Excel sauber lesen, nie eine Zahl erfinden. „Hinweise von selbst“ später, abschaltbar. Der Nutzer
  lädt keine personenbezogenen Daten hoch; ein Datenschutz-Ausbau ist kein Thema. Später bekommt der Mitgesellschafter einen
  eigenen Kontor (Privates und Gedächtnis getrennt, gemeinsame Bereiche teilbar) – ersetzt beim Punkt „gemeinsame KI“ unter Offen
  das gemeinsame Gedächtnis. (PDF-Tabellen: gemessen und stille Fehler behoben in 3.17.27, siehe CHANGELOG)
- **Zugang vom iPhone – Umsetzung** (Nutzer, 2026-11-23: der Vorschlag gilt so):
  Weg zum Mac: bei Tailscale bleiben (WireGuard, Ende-zu-Ende verschlüsselt, kein offener Port zu Hause; Relais sehen nur
  Verschlüsseltes), dazu Tailnet Lock (Tailscale selbst kann dann keine Geräte hinzufügen). Geprüft und verworfen: Headscale (eigener
  Server nötig, gleiche App), WireGuard direkt (Portfreigabe am Router, scheitert oft an CGNAT), Cloudflare Tunnel (Cloudflare sähe
  die Daten im Klartext – widerspricht „nichts nach außen“), eigenes Relais (viel Aufwand, kein Gewinn gegenüber WireGuard).
  Hinweis: Tailscales kostenloser Personal-Plan gilt nur für nicht-kommerzielle Nutzung.
  Sicherheit in Kontor selbst: HTTPS über das ts.net-Zertifikat (kann Kontor schon), je Gerät ein Passkey mit Face ID statt des
  Passworts – einmal am Mac per QR-Code hinzugefügt; Liste der Geräte unter Einstellungen → Zugang, „Entfernen“ sperrt sofort;
  verändernde Aktionen vom iPhone bestätigt Face ID. Rechte wie am Mac; nur am Mac bleiben Zugang, Updates, Einrichtung des
  Assistenten, Sicherung laden/Zurücksetzen, Passwort. Mac schläft: die Offline-Kopie am iPhone zum Lesen; Änderungen erst, wenn
  der Mac erreichbar ist (MoneyMoney läuft dort). Eine eigene iPhone-App mit iCloud-Abgleich wäre die Alternative – großer Aufwand.
  (umgesetzt in 3.17.10)
- **Darlehen überzahlt** (Nutzer, 2026-11-23): Steht ein Darlehen über null hinaus auf der anderen Seite, rechnet Kontor auf die
  Überzahlung keine Zinsen (Buchungsregeln und Planung) und nennt es in einem Hinweis. (umgesetzt in 3.17.8)
- **GitHub ist das einzige Gedächtnis** (Nutzer, 2026-11-23): Was künftige Chats wissen müssen – Entscheidungen, Regeln, Abläufe,
  Verhalten –, steht immer im Repo, gepflegt mit jeder Version von selbst; nie etwas Persönliches (öffentlich). (umgesetzt in 3.17.8)
- **Assistent läuft immer** (Nutzer, 2026-11-23): Eine Einstellung, mit der das Modell immer läuft – Kopplung an Kontors Mac-App
  nur, wenn sehr einfach. „Beenden bei Leerlauf: nie“ heißt jetzt „läuft immer“: Kontor startet das Modell nach der Anmeldung und
  jedem Neustart selbst, wieder nach ein paar Minuten, wenn es von selbst endete; nach „Stoppen“ aus bis zur nächsten Frage. Die
  Mac-App ist nur ein Fenster – der Dienst und damit das Modell laufen unabhängig davon weiter. Ein Ende mit der Mac-App ist nicht
  einfach (der Dienst erkennt ihr Beenden nicht verlässlich: die Seite ruht in verdeckten Fenstern, eine Prozessabfrage wäre ein
  neuer Aufruf nach außen) und deshalb nicht umgesetzt. (umgesetzt in 3.17.20)
- **Gedächtnis kompakt** (Nutzer, 2026-11-23): Notizen sinngemäß und so kurz wie möglich statt im Wortlaut (er diktiert viel;
  jede Notiz kostet bei jeder Anfrage Platz) – Zahlen, Namen und Daten genau. Notizen dürfen auch aus dem stammen, was der
  Assistent geliefert hat (seine Antwort), nicht nur aus den Worten des Nutzers; der Assistent legt sie von selbst an, der Nutzer
  wird nur informiert (unter der Antwort, mit „Zurücknehmen“), was gemerkt ist, steht immer in den Einstellungen. Ersetzt beim
  Gedächtnis „nur aus den eigenen Worten des Nutzers“; Vorhandenes wird nicht umgeschrieben. (umgesetzt in 3.17.26: Notizen aus
  der Antwort ungefragt nur Tatsachen, Gründe, Personen – Wünsche, Regeln, Pläne nur aus seinen Worten –, gekennzeichnet „aus der
  Antwort“; mit Internet-, Beleg- oder Dateitext in der Unterhaltung erst nach Klick)

- **Modellliste ohne Modus-Wörter** (Nutzer, 2026-11-23): Die Gruppen der Modellliste dürfen nicht wie eine Wahl je Denkaufwand
  wirken (Schnell/Ausgewogen/Gründlich im Chat) – gewählt wird ein Modell für alles; Überschriften nur nach Zweck. (umgesetzt in 3.17.21)
- **Hilfe-Suche springt** (Nutzer, 2026-11-23): Die Suche in der Hilfe springt zum ersten Fund und mit ↩/⌘G durch die Funde. (umgesetzt in 3.17.21)
- **Tests je Push kürzer** (Nutzer, 2026-11-23): Der Lauf je Push soll schnell sein und den Nachtlauf nicht doppeln – Zufallsfälle
  vor allem nachts (dessen Fehler behebt der nächste Chat); je Push wenige feste Fälle, die Tests auf mehr Rechner verteilt. (umgesetzt in 3.17.21)

- **Anmeldung nach Start/Update** (Nutzer, 2026-11-23): Kein „Zugang wird geprüft“ vor dem Festlegen des Passworts; ein Passwort,
  das während der ersten Tailscale-Prüfung abgeschickt wurde, geht danach von selbst ab. (umgesetzt in 3.17.24)
- **Nicht bilanzierte Konten im Bereich** (Nutzer, 2026-11-23): Ein Konto mit „nicht bilanzieren“ (z. B. Genossenschaftsanteile in
  einer Gruppe „Off-Balance“) steht unter Konten in seinem Bereich, nicht unter „ohne Bereich“. (umgesetzt in 3.17.24)
- **Kontoauswahl ohne Bereichsnamen** und **optionale Felder erklärt** (Nutzer, 2026-11-23): siehe CLAUDE.md, Oberfläche. (umgesetzt in 3.17.24)

- **Einstellungen speichern sich selbst** (Nutzer, 2026-11-23): Jede Änderung in den Einstellungen wird sofort gespeichert, kein Knopf „Einstellungen speichern“ mehr (MoneyMoney-Sync, Zugang, Belege, Updates, Steuer); nur das Passwort hat seinen eigenen Knopf. (umgesetzt in 3.17.32)
- **Anmeldung wartet nicht auf Tailscale** (Nutzer, 2026-11-23): Kontor muss ohne Tailscale funktionieren. Zweck der Prüfung bleibt
  (reicht „tailscale serve“/Funnel Kontors Port weiter, kämen fremde Anfragen als „am Mac“ an – dann keine Anmeldung am Mac, alle
  Sitzungen dort enden), aber vor der ersten Prüfung nach einem Start wartet eine Anmeldung höchstens 2 s und geht dann. (umgesetzt in 3.17.31)
- **„Freigeben (n)“ zählt das Angehakte** (Nutzer, 2026-11-23): die Zahl im Knopf ist immer genau die Zahl der angehakten Buchungen. (umgesetzt in 3.17.31)
- **Auto-Buchungen auswählen** (Nutzer, 2026-11-23): Nach „alle abwählen“ und einzelnem Anhaken ist nur das Angehakte gewählt –
  auch Buchungen, die die Neuberechnung neu bringt, bleiben abgewählt; ein Klick in die Zelle des Hakens genügt. (umgesetzt in 3.17.28)
- **Zahl im Dock einstellbar** (Nutzer, 2026-11-23): Einstellungen → Allgemein, in der Mac-App: wartende Auto-Buchungen oder aus. (umgesetzt in 3.17.28)
- **Unteragenten** (Nutzer, 2026-11-23): Mehrere Aufgaben nacheinander erledigen; Paralleles macht er mit eigenen Chats. (umgesetzt in 3.17.28)
- **Anmeldung nach Update ohne Warten** (Nutzer, 2026-11-23): Antwortet Tailscale nach einem Start nicht, wartet die Anmeldung am Mac
  höchstens 20 Sekunden (vorher bis ~2 min, bis drei Blicke ins Leere gingen); kein Satz „Abgleich und Auto-Buchungen warten auf
  deine Anmeldung“ auf der Anmeldeseite; Untertitel „Dein digitaler CFO.“ mit Punkt. (umgesetzt in 3.17.28)
  Noch zu klären: Beim Nutzer antwortet Tailscale Kontor nach jedem Start nicht (Protokoll: „gave no answer to 3 looks“) – die
  Prüfung auf serve/Funnel steht dort also auf „unbekannt“; Ursache (App-Store-Variante, Aufruf aus dem Dienst) noch offen.
- **Updates erst bei grünen Tests: abgelehnt** (Nutzer, bestätigt 2026-11-24 – nicht wieder vorschlagen): Kontor bietet jede Version auf
  `main` zur Installation an, ohne auf GitHubs Tests zu warten. Grund: er installiert selbst, wann er will, und sieht nach jeder Änderung
  auf GitHub nach, ob sie grün ist.
- **Arbeitsweise mit Claude** (Nutzer, 2026-11-24): Standard Opus 5.5 „hoch“ statt „extra hoch“ – Fehler sollen ausgebaute Tests finden,
  nicht die Denkstufe; Claude Code statt Chat (mit Diktat); ein Chat je Aufgabe, mehrere nebeneinander; mehrere Aufgaben in einer Nachricht
  gehen weiter nacheinander. Prüfen in zwei Stufen (`CLAUDE.md`): GitHub prüft jede Version gleich; Claude prüft und pflegt in kleinen
  Versionen nur, was Fehler verhindert, alles Nachrangige (englische Hilfe, README, Bilder, Highlights, Gesamtprüfung) beim großen Sprung.
  Abschluss mit `.claude/tools/release.py` in einem Aufruf; kein Warten auf GitHub – rot behebt der nächste Chat („fix ci“). Große Dateien
  nur in Bereichen lesen. Ein Grund für diese Regeln: das Wochenkontingent war mit „extra hoch“ in wenigen Stunden verbraucht.
  (umgesetzt in 3.17.42)
- **Cashflow-Positionen vollständig und eindeutig** (Nutzer, 2026-11-24): Jede private oder unternehmerische Einnahme und Ausgabe
  hat genau eine Position, ohne dass etwas ergänzt werden muss; nicht rückwärtskompatibel nötig (noch nichts eingerichtet). Neu:
  „Rente & Sozialleistungen“ (Firma: „Zuschüsse & Förderungen“), „Unterhalt & Geschenke“ (bekommen), „Bildung & Betreuung“ (Firma:
  „Fortbildung“); „Geschenke & Spenden“ heißt „Unterhalt, Geschenke & Spenden“. Abgrenzungen: Taschengeld ist kein Arbeitseinkommen
  (keine Gegenleistung), sondern „Unterhalt & Geschenke“ – der Nutzer hatte Gehalt vermutet; Minijob ist Arbeitseinkommen; Essen und
  Trinken gehören immer zur Lebenshaltung, auch auswärts (eine Kategorie „Gastro & Lebensmittel“ hat sonst keinen eindeutigen Platz);
  private Renten- und Kapitallebensversicherungen sind „Sparen & Anlegen“ (bauen Vermögen auf), Risikoversicherungen und
  Pflichtbeiträge „Versicherungen“. Erstattungen (Nutzer): zu viel gezahlte Beiträge bucht er in die Kategorie des Beitrags (mindert
  ihn), erstattete Kostenrechnungen unter „Erstattungen“. Die empfohlenen Kategorien zeigen privat und geschäftlich
  getrennt (Umschalter; Nutzer: sonst unübersichtlich). (umgesetzt in 3.17.68)
- **Empfohlene Kategorien nur zur Orientierung** (Nutzer, 2026-11-24): keine Zählung „X von Y vorhanden“, kein „fehlt“ – nicht jede
  Zeile gilt für jeden (ohne Geschäft keine Umsatzerlöse). Die Karte zeigt je Zeile neutral, welche seiner Kategorien dort zählt, sonst „keine“.
  (umgesetzt in 3.17.46)
- **Sperre vor dem Push nach Herkunft** (Nutzer, 2026-11-24): bewusst geänderte Zeilen sollen gehen, nichts eines parallelen Chats
  darf überschrieben werden, ein Konflikt in denselben Teilen einer Datei soll erkannt und abgewogen werden (welcher Stand der neuere
  ist). Umgesetzt: `release.py` merkt sich den eigenen Ausgangsstand; nur Zeilen von Versionen danach sperren; Konflikt-Meldung nennt
  die fremde Version; `git reset` auf einen fremden Stand gesperrt (`docs/rules/parallel.md`). (umgesetzt in 3.17.47)
- **Fremdes nie nach eigenem Abwägen ersetzen** (Nutzer, 2026-11-24, nach 3.17.65 – die Sperre war dort mit `KONTOR_PUSH_OK=1`
  übergangen worden, obwohl nichts verloren war): Es soll nicht zu Überschreibungen kommen, die Sperre nicht routinemäßig umgangen
  werden. Umgesetzt: Die Sperre prüft, was eine fremde Version in eine Zeile schrieb (ihre Wörter mit Kontext), nicht die ganze Zeile –
  ein zusammengeführter Absatz geht ohne Ausnahme; `KONTOR_PUSH_OK=1` für fremde Zeilen nur nach dem Ja des Nutzers im Chat. (umgesetzt in 3.17.69)
- **Nur nötige MCP-Dienste, nur `main` auf GitHub** (Nutzer, 2026-11-24 – Credits für hohe Denkstufen statt für Kontext): Claude in
  Chrome, Claude Docs und `github` gesperrt (Code über Klon, `git` und `gh`); `claude-code-remote` bleibt, weil es die Plattform selbst
  ist (Umgebung, Netz, Schlüssel). Der Zweig `claude/…` jeder Cloud-Sitzung bleibt lokal, der Guard sperrt den Push dorthin;
  übrig gebliebene Zweige werden gelöscht. (umgesetzt in 3.17.49–3.17.52)
  Geändert 2026-11-24 (Nutzer): keine MCP-Dienste gesperrt – die Ersparnis war gering, nichts soll später fehlen (`github` schon
  in 3.17.53 wieder frei, weil seine Werkzeuge erst bei Bedarf laden; umgesetzt in 3.17.55). Übrig gebliebene Zweige löscht kein
  Chat: der Proxy der Cloud-Sitzung verbietet das Löschen auf GitHub; Sitzungszweige werden nie hochgeladen (umgesetzt in 3.17.54).
- **Nach dem Update glatt zurück** (Nutzer, 2026-11-24): Sobald das Update installiert ist, deckt sofort ein Ladebildschirm Kontor ab
  (nie ein schwarzes Fenster), bis die Anmeldung wirklich da ist; mit ihr kommt gleich Touch ID; nach der Anmeldung wird man nicht wieder
  abgemeldet. Ursache des doppelten Logins: die Antwort einer Sitzungsprüfung von vor der Anmeldung (Fokus kehrt beim Schließen des
  Touch-ID-Fensters zurück; nach einem Start antwortete der Dienst je Anfrage bis 2 s verzögert) sperrte wieder. Seitdem verwirft die
  Seite solche Antworten, und die Wartezeit auf den ersten Tailscale-Blick zählt ab dem Start, nicht je Anfrage. (umgesetzt in 3.17.61)

## Offen (Entscheidung steht aus – mit Empfehlung vorlegen, wenn der Punkt dran ist)
- Umsatzsteuer-Voranmeldung direkt an ELSTER senden (ELSTERs Programmbibliothek ERiC, Anmeldung als Hersteller, Zertifikat und
  PIN bei jedem Senden, nie gespeichert; neue Verbindung) – oder Kontor rechnet nur und der Nutzer überträgt die Werte.
- Unabhängig von MoneyMoney: woher dann die Bankdaten kommen.
- KI-Dokumentmodell für Scans, Fotos und Tabellen ohne klare Spalten (z. B. GLM-OCR, PaddleOCR-VL, granite-docling) später prüfen
  und nur aufnehmen, wenn es klar hilft – das Modell liefert nur das Raster, jede Zahl muss so in Textebene oder Texterkennung
  stehen (Messung siehe 3.17.27). (Nutzer, 2026-11-23)
- Zukunft: eine gemeinsame KI für Nutzer und Geschäftspartner (später Mitarbeiter) auf einem eigenen Rechner mit starker
  Grafikkarte, Zugang je Konto über einen sicheren Kanal, gemeinsames Gedächtnis; widerspricht heute „alles auf diesem Mac“ –
  erst nach ausdrücklicher Entscheidung. (Ein Gedächtnis über Finanzen hinaus, nur auf diesem Mac: entschieden, siehe Gedächtnis.)
- Python nach der Umstellung (siehe Entschieden „Aktuelles Python“) – am Mac zu prüfen, dann Vorschlag zur Mindestversion:
  Am Mac prüfen (lässt sich auf GitHub nicht testen): fragt macOS nach der Umstellung erneut nach der Steuerung von MoneyMoney
  oder nach Ordnern (erwartet: nein, der Starter bleibt Apples Python); fragt die Firewall bei eingeschaltetem iPhone-Zugang
  einmal nach dem neuen Programm (erwartet: ja, einmal je Python-Version).
  Mindestversion: Der ganze Code läuft vorerst weiter mit 3.9, weil das Python des Macs Starter und Reserve ist (startet das eigene nicht, bedient es selbst). Anheben in
  Schritten: (1) einige Wochen Betrieb im eigenen Python ohne Rückfall; (2) das eigene Python wird Pflicht – Installation und
  Update laden es, die Reserve ist dann der vorige eigene Build (zwei nebeneinander) statt Apples Python; (3) erst danach darf der
  Code über dem Starter das eigene Python (heute 3.15) voraussetzen (`kontor.py` bis `pyboot.ready()` und `pyboot.py` bleiben 3.9-tauglich, solange Apples
  Python startet), CI ohne 3.9; (4) später launchd direkt auf das eigene Python, Apples Python wird nicht mehr gebraucht.
  Zu entscheiden: ob und wann Kontor auf Apples Python als Reserve verzichtet (ein beschädigtes eigenes Python braucht dann das
  Netz zum Reparieren). Empfehlung: Schritt 2 frühestens mit der nächsten Python-Version, die Kontor anbietet.
- Bibliotheken in abgeschirmten Helfern (Grundlage für „Fertige Bibliotheken statt Eigenbau“; noch keine Bibliothek eingebaut) –
  Vorschlag für den Mechanismus, Entscheidung zur Herkunft steht aus:
  Voraussetzung ist Kontors eigenes Python (fertige Pakete passen nur zu einer festen Version und Rechnerart; mit Apples Python
  bleibt es beim heutigen Lesen). Der Kern lädt nie ein Paket: Dienst, Zugang, Schlüssel, Freigaben, Update-Prüfung bleiben
  Standardbibliothek und laufen mit `-I -S` (kein `site-packages`). Je Aufgabe ein Helfer als eigener Prozess
  (`[python, -I, -S, helfer.py]`), der nur seinen eigenen Paketordner auf den Suchpfad nimmt, die Datei über stdin bekommt und ein
  geprüftes JSON zurückgibt – in der Sandbox wie `receipt_text._profile`: kein Netz (auch nicht innerhalb des Macs), keine anderen
  Programme, keine Apple-Events, liest im Benutzerordner nur sein Programm und seine Pakete, nie Kontors oder MoneyMoneys Daten,
  schreibt nur in einen Zwischenordner je Aufruf; ohne Sandbox startet er nicht.
  Pakete: nur fertige Wheels (nie Quellpakete, nie `pip`, kein Installationsskript), je Paket Name, Version, Datei, Größe, SHA-256,
  Lizenz und Herkunft fest im Code – ein Eintrag in `components.LIBRARIES`, aus dem auch die Liste „Verwendete Programme“ entsteht
  (die Liste und ihr Test stehen seit 3.17.13; `components.loaded` nennt dann, was auf dem Mac liegt); geladen nur nach Klick,
  entpackt und verglichen wie das Python (`pyruntime`: laden → entpacken → jede Datei gegen das Archiv → Probe im Helfer → erst
  dann umbenennen), abhängige Pakete einzeln genannt, nichts wird aufgelöst. Ort: `.python/libs/<name>-<version>/` im
  Programmordner (nie im Datenordner; Deinstallieren entfernt ihn mit; ein anderes Python verwirft ihn, weil die Pakete nicht
  mehr passen). Fehlt ein Paket oder scheitert die Probe, liest Kontor wie bisher und sagt es.
  Zu entscheiden: Herkunft der Wheels – die Paketablage von Python (files.pythonhosted.org; ein neuer Host, den das Update als
  Fund zeigt) oder nur Bibliotheken, die ihre Wheels auch bei GitHub veröffentlichen; und welche Lizenzen in Frage kommen
  (Empfehlung: nur MIT, BSD, Apache 2.0, MPL 2.0 – keine AGPL-Bibliothek wie PyMuPDF).
- Claude als Recherche-Stufe, Protokoll: Die Frage steht wie bei jeder Suche im Protokoll der Änderungen und Abrufe (verschlüsselt, nur auf
  dem Mac), von der Antwort nur Zahlen (Token, Websuchen). Der Auftrag sagte „nur Zahlen, nie Inhalte“ – soll auch die Frage nicht hinein?
  Empfehlung: so lassen, damit nachvollziehbar bleibt, was hinausging.
- Prüfsatz für den Assistenten in Kontor selbst (heute nur Entwickler-Werkzeug, `tests/assistant_eval`) – Vorschlag, Entscheidung
  steht aus: unter Einstellungen → KI-Assistent stellt sich ein geladenes Modell auf Klick den Aufgaben (nur erfundene Daten der
  Demo, nichts geht hinaus; dauert Stunden, der Mac ist so lange belegt). Kontor zeigt das Ergebnis neben dem des bisherigen
  Modells – Punkte je Gruppe, Dauer – und schlägt den Wechsel vor, wenn das neue besser ist; gewechselt wird nur nach Klick, nie
  von selbst. Empfehlung: erst entscheiden, wenn Läufe am Mac zeigen, wie gut der Prüfsatz Modelle unterscheidet.
- Bilder für das Modell, Rest (Entschieden „Bilder und PDFs wie Text“): HEIC wird nicht als Bild gegeben (llama.cpp liest es nicht);
  am Mac prüfen, wie Qwen3.8 27B mit Bildern läuft (Meldungen über Abstürze beim Laden eines Bildes – Kontor fängt einen Absturz ab
  und antwortet aus dem Text) und wie lange eine lange PDF Seite für Seite braucht.
- Modelldienst auf einem zweiten eigenen Rechner (KI-Plattform: „später nur eine andere Auswahl“) – vorbereitet, nicht gebaut:
  Kontor spricht das Modell an genau einer Stelle an (`LocalAI._connect`, OpenAIs Formate; heute fest der Kindprozess auf diesem
  Mac über seine Socket-Datei). Einschalten wäre ein neuer Weg nach außen und braucht vorher, alles zusammen: nur im eigenen
  Tailnet (keine andere Adresse wählbar, nie Heimnetz oder Internet); beide Seiten weisen sich aus (je Rechner ein eigener
  Schlüssel, einmal am Mac gekoppelt – ohne ihn keine Antwort); der andere Rechner ohne Internet und dort abgeschirmt wie hier;
  dort keine Protokolle über Eingaben und Antworten, nichts davon auf der Festplatte; Programm und Modelle dort nur über Kontor
  (per SHA-256 geprüft, nie von selbst aktualisiert). Empfehlung: erst angehen, wenn ein Kauf ansteht; bis dahin nur dieser Mac.

## Am echten Gerät prüfen
Gebaut und auf GitHub getestet, aber nur mit echter Hardware, echten Modellen oder echtem Konto abschließend prüfbar:
- Secure Enclave: Touch ID nach Neustart, „Passwort vergessen“, Datenordner von einem anderen Mac (Daten erst nach Anmeldung, 3.16.83).
- Gedächtnis mit echtem Modell: was es merkt (zu viel, zu wenig), Wartezeit bis zum ersten Wort mit Gedächtnis an und aus; ob es die
  passenden Notizen nutzt und „Aus deinen Notizen“ die richtigen nennt; Einbettungsmodell: Start mit `--embedding` in der Sandbox,
  Endzeichen `<|endoftext|>`, Schwellen `memory.SEM_FLOOR`/`SEM_MIN` mit echten Notizen und Gegenparteien, Dauer für Tausende Notizen.
- Mac-App: Export des Gedächtnisses landet unter „Downloads“, „Importieren …“ öffnet das Dateifenster.
- PDF-Tabellen mit echten Auswertungen (BWA, SuSa, Wertenachweis).
- Internet: Abschirmung des Abrufs und Antworten der Quellen mit echtem Netz; einmal echt jede amtliche Quelle; Claude als Stufe 4 mit
  echtem Schlüssel aus der mit dem Abo verknüpften Console-Organisation – Grenzen (Antwort höchstens 8.192 Token, 5 Websuchen,
  5 Minuten), Antwortzeit, Kosten je Frage.
- Modelle: Tempo und Arbeitsspeicher von Qwen3.8 27B (genauere Datei, 22 GB) mit langem Kontext; auf einem Rechner mit 128 GB Laden,
  Start und Tempo von Flash Next.
- Dazu die Punkte unter „Offen nach der Gesamtprüfung 3.17.0“ (iPhone, Diktieren, Sandbox-Profile).

## 2. KI-Assistent: digitaler CFO
Ziel: Ein lernender, verlässlicher Mitarbeiter, der die Finanzen kennt, sich erinnert, von selbst auf Wichtiges hinweist und
Routine abnimmt – ohne je selbst etwas zu ändern. Was er heute kann: Hilfe („KI-Assistent“) und `CHANGELOG.md`. Gedächtnis,
Sammelfreigabe, Kategorien, Auto-Buchungen, Buchungsregeln, Belege, Excel/CSV/PDF-Tabellen mit Prüfproben, Internet in vier Stufen,
verständliche Modellauswahl, große Modelle, Abschirmung ohne Netz: umgesetzt (3.16.13–3.17.29).

Fertig, wenn
- **Hinweise von selbst:** nach jedem Abgleich prüft Kontor (fester Code) auf Auffälliges – gestiegene Ausgaben, ungewöhnliche
  Umsätze, Fristen (Voranmeldung, Zinsbindung), Liquidität, offene Kategorien, Sicherheitslage (Zugang, Freigaben, Updates) –
  und zeigt es unter Offenes; der Assistent erklärt und ordnet ein, Gemerktes zählt (bekannter Grund, kein Alarm);
- **Regeln statt Einzelklicks** (siehe Entschieden): Vorschläge aus wiederkehrenden Mustern; Liste der Regeln mit Herkunft,
  Ausführungen, Abschalten; jedes Ergebnis rückgängig zu machen;
- **Protokoll:** jede Aktion – Vorschlag angenommen, Regel ausgeführt, Gemerktes, Eintrag, Rücknahme – mit Zeit und Auslöser;
- **Vergleiche:** Zeiträume, Bereiche, Objekte, Gesellschaften; Vergleichszahlen von außen als Datei oder über die freigegebene
  Internetsuche;
- **eingeschleuste Befehle wirkungslos:** Tests mit präparierten Buchungstexten, Dateien, Belegen – nichts gemerkt, keine Regel,
  kein Eintrag ohne Klick;
- **KI-Dokumentmodell für schwierige PDFs und Scans:** nur die Struktur vom Modell, jede Zahl aus dem Text des Dokuments; bewährte
  Bibliotheken als abgeschirmter Leser (siehe Entschieden zu Bibliotheken);
- **Dienste von macOS für die Modelle nur nach Liste** statt alle: auf GitHubs Mac (macOS 15) fragt llama.cpp nach elf Diensten
  (coreservicesd, diskarbitrationd, MTLCompilerService, analyticsd, bsd.dirhelper, logd, system.notification_center,
  opendirectoryd.libinfo und .membership, tccd.system, windowserver.active); ganz ohne lädt kein Modell, mit genau diesen läuft es,
  jeder einzelne ist dort entbehrlich. Der Grafikchip dort ist ein Ersatz – ein echter Mac kann andere brauchen, eine falsche Liste
  ließe das Modell nicht starten oder nur langsam rechnen. Deshalb erst nach einem Lauf am echten Mac festlegen (Probe:
  `tests/mac_sandbox_probe.py` aus 3.17.29, in 3.17.33 durch `tests/test_mac_model.py` ersetzt – holen mit
  `git show 7e7729a:tests/mac_sandbox_probe.py`);
- **hängendes Modell früher erkennen:** Qwen3.6 35B-A3B kann in llama.cpp nach mehreren Fragen hängen bleiben (dort #22450, keine
  Abhilfe bekannt); Kontor gibt eine Anfrage ohne Antwort erst nach 15 Minuten auf. Offen: über den Fortschritt, den llama.cpp
  meldet, früher erkennen und das Modell von selbst neu starten;
- am iPhone ein Bezug ohne Rechtsklick geht (langes Drücken öffnet dort schon Zeilen);
- die Suchfelder der Hilfe- und der Umsatzseite auch nach Bedeutung suchen (heute nur im Assistenten);
- am Mac mit echten Modellen geprüft (siehe „Am echten Gerät prüfen“).

Bewusst nicht (mit Grund):
- Destatis-GENESIS (Konto, POST), IWF (neue Schnittstelle, Zugang unklar), Feeds von Branchenportalen, BFH und BaFin (Adressen nicht
  prüfbar) als Quellen; eine von Anthropic unterbrochene Antwort fortsetzen (wäre ein zweiter, nicht gezeigter Abruf – das Modell
  erfährt, dass sie unvollständig sein kann); Preise in Euro (nur Token).
- Modelle: GLM-5.3 Flash (antwortet nie ohne Nachdenken – das brauchen die kurzen Schritte hier), DeepSeek V4.1 Flash (nur mit eigener
  Laufzeit), MiMo-V2.6 Flash und DeepSeek V4 Flash (lesen lange Dokumente bei 160–170 GB nicht zuverlässiger als Qwen3.8 27B).

## Testwelt ausbauen (Nutzer, 2026-11-24)
Ziel: Alles, was der Nutzer heute von Hand prüft, prüfen Tests – damit Opus auf „hoch“ reicht und Fehler vor ihm auffallen.

Fertig, wenn
- Verständlichkeit (lässt sich nicht fest prüfen): bei jedem großen Versionssprung sieht sich ein Modell alle Seiten an (Skill `major`).

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

## Als Nächstes (Cashflow und Kategorien)
- Hinweis bei gemischten Kategorien (etwa eine Immobilien-Kategorie mit Kaufpreis, Auszahlung und Miete), Kategorisieren je Empfänger
  in einem Schritt, Fortschritt „sicher zugeordnet / geschätzt“.

## Demo (Wunsch des Nutzers, 2026-11-22; umgesetzt in 3.16.87 und 3.16.96)
- Später: Assistent mit vorbereiteten Beispielfragen in der Demo; Firmenwert der UG aus EBITDA, sobald es die gibt.

## Laufend
- Sicherheit vor allem: nichts in MoneyMoney kaputt machen, keine Daten nach außen.
- Jede Rechenlogik mit Abstimmungstests (Summen müssen aufgehen) und, wo Zustände sich ändern, mit Zufallsläufen.
- Neue Lebensfälle (Einlage, Kauf, Darlehen, Auslage …) als Szenario in `tests/test_scenarios.py` ergänzen – je Tag, Monats- und Jahreswechsel –
  und als Ereignis in den Zufallswelten (`tests/test_worlds.py`), damit sie nachts in allen Kombinationen laufen.
- Oberfläche nach Apples Human Interface Guidelines, hell und dunkel, Mac und iPhone.
- Mac-App am besten geprüft (Wunsch des Nutzers, 2026-11-23: die Mac-App ist das Wichtigste, dann Safari am Mac und iPhone): ein
  Rundgang in der echten Mac-App auf GitHub (macOS-Job, eigener Prüf-Build, `tests/test_mac_webview.py`, `tests/mac_webview.swift`) –
  heute jede Hauptseite ohne Skriptfehler und ein echter Rechtsklick. Weiter: Menü, Tastenkürzel, Scrollen, Einfügen aus der
  Zwischenablage, Diktieren ohne Nachfrage (Playwright mit der Safari-Engine unter Linux bildet das nicht nach).

## Offen nach der Gesamtprüfung 3.17.0
- Zugang vom iPhone (Passkey je iPhone, Face ID für jede Änderung, Tailscale-Prüfung; Stand der Umsetzung): am echten iPhone prüfen –
  Passkey sichern, Anmelden, Bestätigen (verlangt Safari vorher einen eigenen Tipp, fragt Kontor „Mit Face ID bestätigen?“) – und mit
  echter Tailscale-App, was `lock status`/`serve status` (App Store und Standalone) liefern; getestet bisher mit Software-Passkey und Chromium.
- Am Mac mit echter Hardware prüfen: Touch ID nach Neustart (Secure Enclave), Diktieren mit echtem Mikrofon, Sandbox-Profile der
  Modelle und des Lesers, echte Modelle (was das Gedächtnis merkt, Wartezeit), echte Auswertungen (BWA, SuSa) als PDF.
- Prüfung vor dem Update: engt untergeschobene Änderungen ein, schließt sie nicht aus; nächster Schritt wäre der Dienst selbst in
  macOS' Sandbox ohne ausgehendes Netz.
- Filter der Internetsuche: Ziffern statt Buchstaben, rückwärts Geschriebenes und Umlaut-Schreibweisen erkennt er erst ab sechs
  Buchstaben (kürzere Namen gingen so durch); „Q3 2025“ lehnt er als lange Ziffernfolge ab – jede Suche steht vorher auf einer Karte im Chat.
- Beschädigte Dateien: Planung, Kategorien und Belegindex nennen die Seiten mit Dateinamen (nicht beiseitegelegt); sind Einstellungen,
  Stand und Anmeldedaten zugleich beschädigt, sperrt die Anmeldung („Schlüssel passt nicht“) – ein falscher Schlüssel sieht gleich aus.
- Planung: Zinsen und Anteile in der Vorschau noch mit gerundeten Kommazahlen (gebucht wird exakt).
- Nach der Prüfung 3.17.1 offen: Depot mit Lücke zwischen zwei bekannten Ständen – die Änderung landet im Monat des nächsten Stands
  (gekennzeichnet ist nur die Zeit vor dem ersten); Heatmap höchstens zehn Streifen ohne „Übrige“, Ring-Scheiben ohne Gegenposten
  (Hilfe sagt es nicht); von unterwegs „nur ansehen“ gekennzeichnet, Felder aber nicht gesperrt (der Dienst lehnt ab); Jahrestabelle der
  Immobilie färbt nur nach Vorzeichen.
