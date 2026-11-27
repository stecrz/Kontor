# Änderungen

## 3.17.109 (2026-11-27 16:02)
- Konten & Regeln: Reiter „Bereiche“ vor „Konten“
- Einrichtung: Cashflow-Positionen nötig und vor den Buchungsregeln – „Übernehmen und weiter“ übernimmt Kontors Vorschläge; „Abgleich“ und „Kategorisieren“ nicht mehr in der Einrichtung

## 3.17.108 (2026-11-27 15:13)
- Updates: Freigabe nur noch, wo etwas nach außen gehen oder Schadsoftware hineinkommen kann – Änderungen an Cashflow, Planung oder Kategorisieren fragen nicht mehr

## 3.17.107 (2026-11-27 14:59)
- Oberfläche: in Safari läuft, was nach einer Antwort des Dienstes kommt, nie mehr mitten in der Größenmeldung des Browsers – kein „ResizeObserver loop“-Fehler mehr, auch abseits des Seitenwechsels
- Entwicklung: jede gelesene Antwort über bodyOf (geprüft); WebKit-Test misst es an api() neben einer direkt gelesenen Antwort

## 3.17.106 (2026-11-27 14:46)
- Einstellungen: „!“ bzw. Punkt auch am Reiter Updates (bzw. KI-Assistent) – Klick auf die Markierung in der Seitenleiste führt direkt dorthin
- iPhone: Reiterleiste zeigt den geöffneten Reiter

## 3.17.105 (2026-11-27 14:23)
- Entwicklung: Seitenwechsel ohne „ResizeObserver loop“ in WebKit (Diagramm-Beobachter der alten Seite getrennt)

## 3.17.104 (2026-11-27 05:00)
- Entwicklung: Nachtlauf über GitHubs Zeitplan um 3:05 deutscher Zeit, ohne eigenen Wecker (GitHubs Verspätung hingenommen)

## 3.17.103 (2026-11-27 00:40)
- Entwicklung: Nachtlauf in einem Workflow – Wecker alle 2 h wartet bis zu 5½ h und startet die Zufallsläufe um 3:05 deutscher Zeit (eigener Nachtstart entfällt)
- Entwicklung: Tests je Version in sechs kürzeren Teilen nebeneinander (rund 9 statt 16 min), Klickpfade nur nachts; jede Testdatei läuft genau einmal (geprüft)
- Entwicklung: Lagebild zählt nur echte Nachtläufe, nicht die Wecker

## 3.17.102 (2026-11-27 00:07)
- Hilfe: „GbR anlegen“ und ähnliche Suchen finden den Abschnitt Bereiche wieder

## 3.17.101 (2026-11-26 18:50)
- Cashflow: erhaltene Zinsen, Dividenden und Gewinnausschüttungen nach DRS 21 unter Investitionen (Zeile Kapitalerträge), nicht mehr im Überschuss – in jedem Bereich; gezahlte bleiben unter Finanzierung
- Cashflow: Vermögensbrücke mit eigenem Schritt Kapitalerträge; Kategorien in beiden Brücken und im Gesamtcashflow aufklappbar
- Planung: Kapitalerträge wie Einnahmen geplant (Steigerung der Einnahmen), bisheriger Plan der Zeile bleibt; Sparquote ohne Kapitalerträge
- Cashflow-Positionen: „Erträge aus Beteiligungen“ und „Beteiligungserträge“ zählen als Kapitalerträge statt als Anlage

## 3.17.100 (2026-11-26 17:24)
- Entwicklung: Klickpfade – Weg in die Demo mit noch laufenden Anfragen der gesperrten Sitzung kein Fehler mehr (Nachtlauf)

## 3.17.99 (2026-11-26 15:06)
- Entwicklung: Zufallsläufe starten jede Nacht zwischen 3 und 4 Uhr (Nachtstart alle 2 h wartet auf 3:05 – GitHubs Zeitplan war 7–9 h verspätet)
- Entwicklung: Lagebild meldet eine ausgefallene Nacht

## 3.17.98 (2026-11-26 03:03)
- Cashflow-Positionen: Hinweis „gemischt?“ bei einer Kategorie mit einzelnen, viel größeren Zahlungen (etwa Kaufpreis oder Darlehensauszahlung neben der Miete) – Klick zeigt sie, „Passt so“ bestätigt sie; auch unter Offen in der Übersicht
- Kategorisieren: „Alle … Umsätze sicher zugeordnet“ mit Tausenderpunkt

## 3.17.97 (2026-11-26 02:35)
- Kategorisieren: Fortschritt über der Liste – wie viele Umsätze sicher zugeordnet sind und welcher Anteil am Betrag (den Rest schätzt der Cashflow), für die gewählten Filter

## 3.17.96 (2026-11-25 18:57)
- Hilfe: Tabellen am iPhone brechen Wörter nicht mehr mitten im Wort
- Oberfläche: kein Skriptfehler der Titelleiste mehr beim Seitenwechsel (iPhone)
- Entwicklung: Klickpfade tippen Formen auf ganzen Pixeln mit Rand (haarfeine Bänder im Flussdiagramm ausgelassen); jeder ResizeObserver wirkt im nächsten Frame (geprüft); gezielte Läufe je Ansicht beschrieben

## 3.17.95 (2026-11-25 14:50)
- Cashflow: in der Heatmap ragt der letzte Monatsname am iPhone nicht mehr in die Spalte „Ø“
- Entwicklung: Klickpfade – eine waagrecht aus dem Bild gescrollte Zelle gilt nicht als anklickbar

## 3.17.94 (2026-11-25 11:51)
- Entwicklung: Nachtlauf startet gegen 4 Uhr deutscher Zeit (3:47, Sommer wie Winter) statt 01:17 UTC

## 3.17.93 (2026-11-25 11:47)
- Hilfe: die Suche findet „Geld unterwegs“ (Geldtransit) und „Kredit“ (manuelle Darlehen) wieder

## 3.17.92 (2026-11-25 03:59)
- Darlehen: Schreibt ein Darlehenskonto nur den Tilgungsanteil einer Rate gut und bucht die Zinsen nicht, teilt Kontor die Rate selbst – die Gutschrift ist die Tilgung, der Rest die Zinsen (bisher: Rate unter „Unklar“, Gutschrift als Wertänderung). Die Rate muss das Darlehen nennen: IBAN, Kontonummer oder ein Wort wie „Darlehen“/„Tilgung“; nichts wird geteilt, wo es nicht eindeutig ist.

## 3.17.91 (2026-11-25 03:40)
- Cashflow: Umbuchungs-Kategorie auch mit Zusatz in Klammern erkannt (etwa „Umbuchung (Tagesgeld)“) – ohne Gegenbuchung offen statt Sonstige Ausgaben
- Immobilien: eine Umbuchung unter der Kategorie der Immobilie zählt im Soll-Ist-Vergleich weder als Miete noch als Kosten

## 3.17.90 (2026-11-25 02:44)
- Cashflow: erhaltene Zinsen auf gewährte Darlehen zählen unter Einnahmen → Kapitalerträge (standen unter Investitionen); gezahlte bleiben unter Finanzierung
- Darlehen: Zinsen ohne Zahlung (endfällig, gestundet, Rate unter den Zinsen) erscheinen als Aufnahme statt als positive Tilgung
- Mietkaution: zählt nicht mehr als Miete – als Kategorie Aufnahme und Tilgung, als Mieter gezahlt Sparen & Anlegen; Hilfe beschreibt das Konto dafür

## 3.17.89 (2026-11-25 02:08)
- Cashflow: eine Zahlung an einen anderen Bereich übernimmt keine von Hand gebuchte Darlehensbuchung mehr, die den Namen eines anderen Zahlers trägt
- Beteiligung: Wert bleibt auch dann auf den Cent genau, wenn eine früher erfasste Buchung der Gesellschaft später datiert ist
- Entwicklung: Klickpfade – zugeklappte Abschnitte gehören nicht zum verglichenen Zustand; Seite wird im nächsten Bild an ihrer Stelle gehalten

## 3.17.88 (2026-11-25 01:26)
- Cashflow: Wertpapierkauf und -verkauf, Sparplan und Festgeld werden auch ohne Kategorie oder mit „Umbuchung“ als Umschichtung erkannt – ins Depot bzw. Festanlagekonto, nicht mehr als Ausgabe oder „Unklar“
- Cashflow-Positionen: jede Umbuchung ohne Gegenbuchung steht unter „Zielkonto je Empfänger“ – einmal das Konto wählen, dann zählt sie dort
- Hilfe: Regeln für Geld auf Konten, die nur Stände haben (Depot, Festanlage, P2P)

## 3.17.87 (2026-11-24 23:38)
- Cashflow: Kaufpreis und Kaufnebenkosten einer Immobilie zählen als Investition, auch unter der Kategorie der Immobilie – nicht mehr als Kosten des Objekts (Cashflow, Soll/Ist, Steuerübersicht)
- Planung: Darlehen und Wert einer Immobilie gehen vom tatsächlichen Kontostand weiter statt auf die Kalkulation zu springen – eine Sondertilgung senkt die geplanten Zinsen
- Cashflow-Positionen: mehr Kategorienamen erkannt (Hypothek, Vorfälligkeit, Tagesgeld, Festgeld; Firma: Reisekosten, Bürobedarf, Porto, Telefon unter Betriebskosten; Hausgeld und Grundsteuer unter „Wohnen“ sind Wohnen)
- Hilfe: Wertpapiere kaufen und verkaufen – Kategorie mit Sparen & Anlegen statt „Umbuchung“

## 3.17.86 (2026-11-24 23:10)
- Entwicklung: Link „Mehr in der Hilfe“ hat einen eigenen Tooltip (Rundgang-Test war seit 3.17.85 rot)

## 3.17.85 (2026-11-24 22:24)
- Hilfe: neue Anleitungen „Darlehen einrichten“ und „Immobilie einrichten“ – Gegenbuchungen, volle Rate, Zinsen, Kaufnebenkosten, Darlehen direkt an den Verkäufer; auch der KI-Assistent findet sie; Links unter Buchungsregeln → Darlehen und bei Immobilien
- Cashflow-Positionen: Kaufnebenkosten und Grunderwerbsteuer zählen als Investition statt unter Wohnen und landen ohne gewähltes Zielkonto nicht mehr beim Depot

## 3.17.84 (2026-11-24 21:25)
- Oberfläche: eine wieder geöffnete Seite steht genau dort, wo sie verlassen wurde – auch wenn Diagramme oder Vorschauen erst danach erscheinen (Bilanz, Cashflow, Übersicht, Hilfe, Buchungsregeln)
- Bilanz: die Zeitraum-Knöpfe eines Diagramms stimmen auch, wenn der gewählte Zeitraum keine Werte hat
- Seitenfenster: ein langer Titel steht neben dem ✕
- Entwicklung: Klickpfade der Nacht – übrige Fehlalarme behoben (Diagrammformen dort anklicken, wo sie gezeichnet sind; „…“ in Knöpfen; Stelle einer Seite nur gegen ihre zuletzt verlassene Ansicht; Demo ohne Einstellungen); neuer Test hält die Funde fest

## 3.17.83 (2026-11-24 21:10)
- Cashflow: Gewinnausschüttung zählt immer als Kapitalertrag, auch von deiner eigenen GmbH oder GbR – der gesunkene Wert der Beteiligung steht als Wertänderung daneben (Ausnahme aus 3.17.77 zurückgenommen)
- Cashflow-Positionen: auch „Gewinnanteil“ als Kapitalertrag erkannt

## 3.17.82 (2026-11-24 20:32)
- Seitenfenster: öffnet sofort wieder, wenn du es mit einem Klick daneben schließt und gleich wieder auf dieselbe Zahl klickst (oder Enter drückst)
- Entwicklung: Nachtlauf – Klickpfade übergehen Zugeklapptes; Tests für Einlagen neben gleich hohen Zahlungen und für Beteiligungen auf den Cent

## 3.17.81 (2026-11-24 20:20)
- Entwicklung: Nachtlauf – Cashflow und Planung laufen je in einem eigenen Job (der gemeinsame wurde jede Nacht nach 240 min abgebrochen, die neuen Planungsfälle liefen nie); Test hält fest: je Job genau ein Zufallstest

## 3.17.80 (2026-11-24 20:15)
- Entschieden: Alte Jahre nicht nachträglich kategorisieren

## 3.17.79 (2026-11-24 19:39)
- Cashflow: Darlehen eines Freundes nimmt nicht mehr die Gegenbuchung einer Zahlung an einen anderen Bereich
- Entwicklung: Nachtlauf (Welten) behoben

## 3.17.78 (2026-11-24 19:11)
- Beteiligungen: Wert auf den Cent genau, auch nach einer nachträglichen Monatsbuchung
- Entwicklung: Nachtlauf (Regelwelten) behoben

## 3.17.77 (2026-11-24 18:34)
- Cashflow: Ausschüttung deiner eigenen Gesellschaft zählt als Entnahme, nicht als Kapitalertrag – ihr Gewinn steckt schon im Wert der Beteiligung; von anderen Gesellschaften weiter Kapitalertrag
- Cashflow-Positionen: Einrichtung, Ausstattung und Haushaltsgeräte unter Lebenshaltung statt Wohnen (in einer Firma Investitionen)
- Cashflow-Positionen: Hinweis „zwischen Bereichen“ an Kategorien mit Ausschüttungen deiner Gesellschaften

## 3.17.76 (2026-11-24 17:51)
- Hilfe: Suche findet jeden Abschnitt

## 3.17.75 (2026-11-24 17:23)
- Cashflow: Kategorie zählt auf jedem Konto, auch auf manuellen – etwa der einbehaltene Teil einer Kaution; ohne Kategorie weiter Wertänderung
- Cashflow: als Verbindlichkeit gebuchte Rechnung zählt bei Fälligkeit in ihrer Kategorie, die Schuld als Aufnahme

## 3.17.74 (2026-11-24 16:31)
- Cashflow-Positionen: Empfohlene Kategorien – Gruppe „Vermietung“ nur für Miete und Kosten je Immobilie
- Cashflow-Positionen: Kauf jeder Anlage (Immobilie, Firmenanteile) samt Notar und Grunderwerbsteuer unter Sparen & Anlegen

## 3.17.73 (2026-11-24 16:04)
- Cashflow: neue Position „Auslagen“ – was du für andere zahlst und erstattet bekommst (etwa Tanken für die Firma), hebt sich auf
- Cashflow-Positionen: erhaltene Gewinnausschüttung als Kapitalertrag vorgeschlagen; private Verkäufe (Kleinanzeigen, eBay) als Sonstige Einnahmen, in einer Firma Umsatzerlöse; Nebeneinkünfte als Arbeitseinkommen
- Empfohlene Kategorien: Auslagen, Sonstige Einnahmen › Verkäufe, Gehalt › Tantieme · Nebeneinkünfte, Kapitalerträge › Ausschüttungen

## 3.17.72 (2026-11-24 15:30)
- Cashflow-Positionen: Empfohlene Kategorien – Darlehen mit Tilgung und Zinsen als eigene, eingerückte Zeilen
- Cashflow-Positionen: Immobilie direkt nach den Ausgaben, Kauf eingerückt; Zeile nennt, wohin Miete, Kosten, Kauf und Darlehen zählen
- Cashflow-Positionen: Tooltip am Spaltenkopf – Zeile = anzulegende Kategorie, grau nur Beispiele; Immobilie: Unterkategorien empfohlen bei Erstattungen

## 3.17.71 (2026-11-24 13:42)
- Übersicht: Vermögensgrafik auch bei gleichbleibendem Betrag richtig (statt leer); Zahlen in den Karten brechen neben dem Assistenten um, statt in die Nachbarkarte zu ragen
- Bilanz: Kopf der ersten Spalte am iPhone zweizeilig – ↑↓ und Auge nicht mehr verdeckt
- Entwicklung: Prüfung aller Versionen seit 3.17.20 – keine verlorene Version; Fahrplan: Platzhalter 3.17.V4 → 3.17.33, tote Verweise berichtigt, Kehrtwende MCP-Dienste und Zweige unter Entschieden nachgetragen
- Entwicklung: Lagebild nennt für einen roten Nachtlauf auch Klickpfade und Datenwelten; Nachtlauf von Hand startbar (fiel am 24.11. aus); Funde des lokalen Nachtlaufs in FOUND_CLICKS und FoundTest
- Entwicklung: jede Testdatei in docs/rules/tests.md; Tests gegen Versions-Platzhalter und tote Dateiverweise im Fahrplan

## 3.17.70 (2026-11-24 12:52)
- Entwicklung: großer Versionssprung prüft mit voller Kraft – je Bereich ein eigener Prüfer, jede geänderte Datei vollständig gelesen

## 3.17.69 (2026-11-24 12:39)
- Entwicklung: Push-Sperre prüft fein, was eine fremde Version in eine Zeile schrieb – zusammengeführte Absätze gehen ohne Ausnahme
- Entwicklung: fremde Zeilen ersetzen nur noch nach Zustimmung des Nutzers

## 3.17.68 (2026-11-24 11:02)
- Cashflow: neue Positionen „Rente & Sozialleistungen“, „Unterhalt & Geschenke“, „Bildung & Betreuung“; „Geschenke & Spenden“ heißt „Unterhalt, Geschenke & Spenden“
- Cashflow-Positionen: bessere Vorschläge nach dem Namen – Minijob, Taschengeld, Sauna, Friseur; Essen auch auswärts unter Lebenshaltung; private Rentenversicherung unter Sparen & Anlegen
- Empfohlene Kategorien: Umschalter Privat | Geschäftlich, je Seite nur ihre Zeilen und Namen

## 3.17.67 (2026-11-24 10:24)
- Entwicklung: Nachtlauf startet wieder (Workflow-Datei); Test gegen „: “ in Werten ohne Anführungszeichen

## 3.17.66 (2026-11-24 07:10)
- Fremdwährung: Beträge von Konten in anderer Währung in keiner Euro-Summe mehr (Steuer, Kategorien, Umsatzsummen, Kategorisieren, KI-Assistent), überall mit ihrem Währungskennzeichen
- KI-Assistent: zu lange Ergebnisse gekürzt statt mitten drin abgeschnitten – er weiß, was fehlt; Bilanzzeilen auch in anderen Bereichen gefunden
- iPhone: lange Namen in Auswahllisten machen die Seite nicht mehr breiter
- Entwicklung: Datenwelten mit Sonderfällen (lange Namen, große Beträge, leere und volle Bereiche, Fremdwährung, Monats- und Jahreswechsel) für Seiten und Assistent, je Push und nachts

## 3.17.65 (2026-11-24 06:04)
- Hilfe: Suche Wort für Wort wie man es sagt – findet Wortformen, springt in den passendsten Abschnitt
- KI-Assistent: findet Hilfe-Abschnitte zu Alltagswörtern zuverlässiger (Kredit, Backup, Handy …)
- Oberfläche: fehlende Tooltips und „?“ ergänzt (Tabellen, kleine Grafiken, Zeitraum, Steuer, Umsatzfilter, Reiter, Schließen)
- Entwicklung: Tests – jedes Bedienelement erklärt, jede Hilfe-Stelle erreichbar, Suchwörter je Funktion

## 3.17.64 (2026-11-24 05:35)
- Menü (iPhone, schmales Fenster): esc schließt es, ein Tipp auf die offene Seite auch; auf der Seite des Assistenten liegt es nicht mehr darunter
- Entwicklung: zufällige Klickpfade jede Nacht – Seiten, Dialoge, Seitenfenster, Bezüge; hell/dunkel, Mac/iPhone, Chromium/WebKit, wechselnde Welten; je Push 3 feste
- Entwicklung: Seitentest wartet nach dem Speichern auf den Zustand statt einer festen Zeit; Demo fragt auf „Kontostände“ keine Wertpapiernamen mehr ab

## 3.17.63 (2026-11-24 05:12)
- KI-Assistent: PDFs gehen als Text und Seitenbilder an das Modell – kurze ganz, lange Seite für Seite („Lese Seite 3 von 30 …“ in den Gedanken)

## 3.17.62 (2026-11-24 04:50)
- Entwicklung: Fahrplan nennt die richtige Version

## 3.17.61 (2026-11-24 04:49)
- Updates: nach dem Installieren sofort Ladebildschirm statt schwarzem Fenster, bis die Anmeldung da ist
- Anmeldung: Touch ID kommt gleich mit der Anmeldeseite, auch direkt nach einem Neustart
- Anmeldung: nach Touch ID nicht mehr zurück zur Anmeldeseite geworfen

## 3.17.60 (2026-11-24 04:25)
- KI-Assistent: Karte einer Änderung zeigt „Bitte prüfen“ bei Zahlen, die nicht im erkannten Text der Bilder und PDFs stehen

## 3.17.59 (2026-11-24 04:06)
- KI-Assistent: liest aus Bildern alles wie aus getipptem Text, auch Zahlen; Abweichungen zur Texterkennung nennt er
- KI-Assistent: nach einem Absturz am Bild startet das Modell zuverlässig neu

## 3.17.58 (2026-11-24 03:46)
- Updates: geänderte Hooks der Entwicklung (.githooks) nicht mehr als Fund gemeldet
- Entwicklung: Update-Prüfung behandelt .githooks wie .claude (Kontors Git läuft ohne Hooks)

## 3.17.57 (2026-11-24 03:32)
- Entwicklung: Einrichtung nutzt die Playwright-Version des Servers – vorhandene Browser passen ohne Download

## 3.17.56 (2026-11-24 03:30)
- Immobilien: ohne Vermietungskategorie verknüpft Kontor die passende Kategorie unter Vermietung/Immobilien selbst (Wort aus dem Namen, Hausnummer muss passen)
- Immobilien: Miete und Objektkosten ohne Kategorie zählen geschätzt zur Immobilie, die der Verwendungszweck nennt, sonst zur einzigen des Bereichs; auch in der Planung
- Cashflow-Positionen: Kategorien-Karte zeigt Vermietung/Objektkosten ohne angelegte Immobilie unter „Je Immobilie“
- Entwicklung: Test der Update-Prüfung vergleicht mit 3.17.12 statt dem wachsenden Stand

## 3.17.55 (2026-11-24 03:15)
- Entwicklung: Sperre für Claude in Chrome und Claude Docs aufgehoben – kaum Ersparnis, nichts soll später fehlen

## 3.17.54 (2026-11-24 03:11)
- Entwicklung: Sitzungszweige werden nie hochgeladen; Löschen auf GitHub geht aus einer Sitzung nicht

## 3.17.53 (2026-11-24 03:10)
- Entwicklung: GitHub-Werkzeuge wieder frei (kosteten keinen Kontext); übrig gebliebene Sitzungszweige werden nach dem Veröffentlichen gelöscht

## 3.17.52 (2026-11-24 03:07)
- Entwicklung: Push auf claude/…-Zweige gesperrt, auf GitHub nur main
- Entwicklung: übrige Zweige löschbar ohne Versionsprüfung; MCP-Bestand in CLAUDE.md

## 3.17.51 (2026-11-24 03:04)
- Entwicklung: GitHub-Werkzeuge (MCP) in Kontor-Sitzungen gesperrt – Code und Veröffentlichen laufen über git

## 3.17.50 (2026-11-24 02:42)
- Entwicklung: Claude Docs in Kontor-Sitzungen gesperrt – weniger Grundlast je Schritt

## 3.17.49 (2026-11-24 02:37)
- Entwicklung: Claude in Chrome in Kontor-Sitzungen gesperrt – weniger Grundlast je Schritt

## 3.17.48 (2026-11-24 02:31)
- Bilanz: Depot mit einem Wertpapier – Verlauf zeigt das Wertpapier mit Namen und ISIN statt „Unbenannt 1“ (Kontostände neu einlesen)

## 3.17.47 (2026-11-24 02:16)
- Entwicklung: Sperre vor dem Push nach Herkunft – bewusst geänderte Zeilen dürfen, beim Konflikt verlorene Zeilen paralleler Chats sperren; Konflikt nennt die neuere Version; kein git reset auf fremden Stand

## 3.17.46 (2026-11-24 02:03)
- Konten & Regeln: Empfohlene Kategorien nur zur Orientierung – keine Zählung „X von Y vorhanden“, kein „fehlt“, je Zeile neutral „keine“

## 3.17.45 (2026-11-24 01:55)
- Automatische Buchungen: eigener Darlehensname in Anführungszeichen (Darlehen „Darlehen Immo A“), auch in Prüfhinweisen
- Entwicklung: Versionskette prüft die Changelog-Uhrzeit gegen die Commit-Zeit

## 3.17.44 (2026-11-24 01:27)
- Entwicklung: Lagebild holt GitHubs Testergebnisse auch ohne gh und meldet es, wenn GitHub nicht erreichbar ist

## 3.17.43 (2026-11-24 01:14)
- Bilanz: Depot mit nur einem Wertpapier – Verlauf ohne Namen aus MoneyMoney zählt zu ihm statt „Unbenannt 1“

## 3.17.42 (2026-11-24 00:48)
- Entwicklung: Abschluss jeder Version mit einem Skript (release.py) – prüfen, daraufsetzen, nummerieren, veröffentlichen in einem Schritt
- Entwicklung: Prüfen in zwei Stufen – englische Hilfe, README, Bilder, Highlights nur beim großen Versionssprung (Skill major)
- Entwicklung: große Dateien nur in Bereichen lesen, Werkzeuge beim Start der Sitzung von selbst, rot auf GitHub behebt der nächste Chat
- Entwicklung: Regeln gestrafft, Fahrplan ohne Erledigtes, Ablehnung „Updates erst bei grünen Tests“ festgehalten

## 3.17.41 (2026-11-24 00:45)
- Cashflow-Positionen: Kategorien-Karte als ein Baum für alle Bereiche, Grundregel als erste Zeile, keine Marken „privat“/„Firma“ mehr; Unpassendes „bei Bedarf“.

## 3.17.40 (2026-11-24 00:26)
- KI-Assistent: Bilder (hochgeladen oder eingefügt) gehen als Ganzes an das Modell – für Aufbau, Stempel, Grafik; Zahlen weiter nur aus der Texterkennung
- KI-Assistent: Bildteil des Modells (etwa 1 GB) kommt mit dem Modell; bei geladenen Modellen per Aktualisieren, ohne das Modell neu zu laden
- KI-Assistent: startet ein Modell mit Bildteil nicht oder fällt es an einem Bild um, geht es ohne Bild weiter – Hinweis unter der Antwort
- Einstellungen: „Verwendete Programme“ nennt den Bildteil beim Modell

## 3.17.39 (2026-11-24 00:30)
- Cashflow-Positionen: „Was Kontor von deinen Kategorien braucht“ immer eingeklappt, auch in der Einrichtung.

## 3.17.38 (2026-11-23 23:45)
- Cashflow-Positionen: Kategorien-Karte zeigt „Je Immobilie“ immer (privat und Firma), allgemeine Zeilen Mieteinnahmen/Objektkosten entfallen.

## 3.17.37 (2026-11-23 23:23)
- Entwicklung: Python 3.9 nur noch für den Starter – der übrige Code läuft und wird getestet im eigenen, aktuellen Python
- Entwicklung: Fahrplan – ganzes Bild an den Assistenten (Upload und Zwischenablage gleich) entschieden

## 3.17.36 (2026-11-23 23:21)
- Entwicklung: Regeln schlanker – Sicherheit im Detail in docs/rules/security.md (je Abschnitt nur bei Bedarf gelesen), Tests in docs/rules/tests.md
- Entwicklung: lokal nur betroffene Tests (tests/affected.py), volle Prüfung auf GitHub; auf GitHub in einem Schritt warten

## 3.17.35 (2026-11-23 23:14)
- KI-Assistent: llama.cpp und Modelle aktualisieren sich von selbst („Automatisch laden“, abschaltbar) – nur wenn der Assistent ruht
- KI-Assistent: Suche nach neuen Versionen ab Werk täglich statt monatlich
- KI-Assistent: von llama.cpp nur Fassungen, die seit zwei Tagen draußen sind, nie eine ältere
- KI-Assistent: startet eine neue llama.cpp-Fassung das Modell nicht, kommt die vorige von selbst zurück
- Entwicklung: vor dem Push nur die betroffenen Tests lokal, die volle Prüfung macht GitHub; kein Warten per Schleife

## 3.17.34 (2026-11-23 23:25)
- Cashflow: Auszahlung unter einer Tilgungs-Kategorie zählt als Darlehensaufnahme, gesondert von der Tilgung; Rücklastschrift bleibt Tilgung.
- Cashflow: Darlehen ohne Konto in MoneyMoney – Abgleich mit der Bilanz geht auf (Zeile „Darlehen ohne Konto“ unter Wertänderungen).
- Cashflow-Positionen: neue Position „Einlagen & Entnahmen“ für Mitgesellschafter – Firma unter Finanzierung, privat unter Beteiligungen.
- Cashflow-Positionen: „Sparen & Anlegen“ heißt in Firmen „Anlagevermögen & Geldanlagen“.
- Cashflow-Positionen: empfohlene Kategorien für private und Firmenbereiche, je Position eine; Kennzeichen „privat“/„Firma“.

## 3.17.33 (2026-11-23 22:48)
- KI-Assistent: Abschirmung ohne jedes Netz – das Modell lauscht auf keiner Adresse mehr, auch nicht innerhalb des Macs (eine Datei im eigenen Ordner statt 127.0.0.1)
- KI-Assistent: gilt auch für Diktieren und die Suche nach Bedeutung; ein llama.cpp, das das nicht kann, wird nicht installiert und nicht gestartet
- KI-Assistent: Tooltip und Hilfe-Abschnitt „Abschirmung“ – was sie verhindert und was nicht
- Entwicklung: macOS-Lauf prüft die Abschirmung der Modelle (Regeln fest, echtes llama.cpp als Bericht); Fahrplan: Modelldienst auf einem zweiten Rechner unter „Offen“

## 3.17.32 (2026-11-23 22:30)
- Einstellungen: speichern sich bei jeder Änderung selbst – kein „Einstellungen speichern“ mehr (MoneyMoney-Sync, Zugang, Belege, Updates, Steuer)

## 3.17.31 (2026-11-23 22:10)
- Anmeldung: wartet nach einem Start höchstens 2 s auf Tailscale, dann geht sie – Kontor braucht Tailscale nicht
- Auto-Buchungen: „Freigeben (n)“ zählt genau die angehakten Buchungen – auch nach dem Neuladen der Seite

## 3.17.30 (2026-11-23 22:05)
- Cashflow-Positionen: „Was Kontor von deinen Kategorien braucht“ als empfohlener Kategorienbaum, gegliedert wie die Positionen, je Gruppe wie am besten aufgestellt.
- Cashflow-Positionen: Investitionen und Finanzierung am besten über Konten in MoneyMoney; „Sparen & Anlegen“ und „Darlehen“ nur bei Bedarf, eine Kategorie reicht.

## 3.17.29 (2026-11-23 21:18)
- KI-Assistent: größere Modelle in mehreren Dateien – jede Datei per SHA-256 geprüft, ein Fortschritt, Platz vorab für alle, eingesetzt erst, wenn alle stimmen
- KI-Assistent: Gruppe „Für einen stärkeren Rechner“ mit Qwen3.8 Flash Next (ca. 94 GB) – sichtbar auf jedem Mac, ladbar erst ab 128 GB Arbeitsspeicher, nie empfohlen
- KI-Assistent: abgebrochener Download steht als „angefangen“ in der Liste – „Weiter laden“ oder „Verwerfen“
- KI-Assistent: „Dateien zeigen“ findet auch Modelle in Unterordnern; mehrere Dateien eines Modells als ein Eintrag
- Entwicklung: Probe im macOS-Lauf erweitert – Links im eigenen Ordner, Dienste anderer Programme nach Liste (nur Bericht)

## 3.17.28 (2026-11-23 21:05)
- Anmeldung: antwortet Tailscale nach einem Start nicht, wartet Touch ID bzw. Passwort am Mac höchstens 20 s (vorher bis ~2 min)
- Anmeldung: Satz „Abgleich und Auto-Buchungen warten auf deine Anmeldung“ entfernt; Untertitel „Dein digitaler CFO.“
- Auto-Buchungen: nach „Keine“ einzeln gewählt – neu errechnete Buchungen sind nicht mehr von selbst mit ausgewählt
- Auto-Buchungen: Klick irgendwo in die Zelle des Hakens setzt oder entfernt ihn
- Einstellungen → Allgemein: „Zahl im Dock“ (wartende Auto-Buchungen oder aus), in der Mac-App
- Entwicklung: mehrere Aufgaben nacheinander statt mit Unteragenten

## 3.17.27 (2026-11-23 20:04)
- KI-Assistent: Tabellen aus PDFs genauer – ein Strich für „nichts“ wird kein Minus, zwei Zahlen nebeneinander nie eine, Spalten verrutschen nicht mehr; Unklares bleibt Text
- KI-Assistent: lange Auswertungen (Wertenachweis über 30 Seiten) vollständig – jede Zeile einmal, jede Zahl steht so im Dokument
- KI-Assistent: Kontor rechnet nach, ob Summenzeilen, Überträge sowie Soll und Haben aufgehen – eine verlesene Zahl oder fehlende Zeile fällt auf
- KI-Assistent: sucht in langen Dateien Zeilen nach Wörtern (Konto, Name) statt Seite für Seite; nennt nichts, was er nicht gelesen hat
- KI-Assistent: CSV-Dateien werden wie Excel als Tabelle gelesen
- KI-Assistent: Summen nennen enthaltene Summenzeilen und Überträge, ausgeblendete Zeilen und Zahlen, die als Text dastehen

## 3.17.26 (2026-11-23 20:10)
- KI-Assistent: Notizen kurz und sinngemäß statt im Wortlaut – Zahlen, Namen, Daten genau
- KI-Assistent: merkt sich auch, was er in der Antwort herausfindet (Tatsache, Grund, Person) – „aus der Antwort“, mit „Zurücknehmen“
- KI-Assistent: Wünsche, Regeln, Pläne nur aus deinen Worten; aus einer Antwort mit Internet-, Beleg- oder Dateitext erst nach Klick
- Einstellungen: Gedächtnis-Liste und Export nennen Notizen aus Antworten

## 3.17.25 (2026-11-23 19:31)
- Cashflow: eine Ausgabe gleichen Betrags (z. B. Versicherung) lässt keine PayPal-Aufladung mehr die Gegenbuchung einer Einlage im Beteiligungskonto nehmen
- Entwicklung: übrige Zufallsfälle der Nacht behoben und fest aufgenommen (Testwelten: Sondertilgung vor schon gebuchtem Monatsend-Zins, verschobene Spiegelbuchung mit neu erfasstem Original)

## 3.17.24 (2026-11-23 19:40)
- Anmeldung: kein „Zugang wird geprüft“ vor dem Festlegen des Passworts; ein während der Prüfung abgeschicktes Passwort geht danach von selbst ab
- Konten: „nicht bilanzieren“ (z. B. Gruppe „Off-Balance“) steht in seinem Bereich statt unter „ohne Bereich“
- Regeln: Kontoauswahl nach Bereich ohne Bereichsnamen hinter den Konten
- Darlehen: Gegenpartei – Tooltip sagt, wofür (Tilgung und Zinsen) und was leer gilt; der Name des Darlehens grau im Feld
- Entwicklung: Regeln für optionale Felder und die Kontoauswahl; ein wackliger Browsertest robuster

## 3.17.23 (2026-11-23 19:16)
- Entwicklung: Tests auf GitHub starten wieder – seit 3.17.21 (anderer Chat) stand `env:` im Schritt „Tests“ doppelt, GitHub lehnte die Datei ab
- Entwicklung: neuer Test prüft alle Workflow-Dateien auf doppelte Schlüssel

## 3.17.22 (2026-11-23 18:45)
- KI-Assistent: Nachdenken lässt der Antwort immer Platz – auch bei kleinem Kontext und „Gründlich“ (keine abgeschnittene Antwort mehr)
- KI-Assistent: vergessene Notiz verschwindet auch aus den Gedanken der Unterhaltung
- KI-Assistent: Ursachen-Abfrage wird bei wenig Platz kleiner statt abgeschnitten
- Entwicklung: Text am Ende des Nachdenkens in den Texten der Oberfläche; Stopp-Test wartet länger

## 3.17.21 (2026-11-23 18:40)
- KI-Assistent: Modellliste ohne „Gründlich/Schnell/Klein“ – Gruppen nach Zweck, damit sie nicht wie die Wahl des Denkaufwands im Chat wirken
- Hilfe: Suche springt zum ersten Fund, ↩/⌘G zum nächsten, ⇧↩/⇧⌘G zum vorigen; „3 von 12“
- Entwicklung: Tests je Push auf vier Rechner je Python verteilt, nur 12 feste Zufallsfälle (nachts 1000), langsamste Tests im Log

## 3.17.20 (2026-11-23 17:50)
- KI-Assistent: „Beenden bei Leerlauf: nie“ heißt „läuft immer“ – Modell startet nach der Anmeldung und jedem Neustart von selbst, unabhängig von der Mac-App
- KI-Assistent: endet es von selbst, startet Kontor es nach ein paar Minuten neu; nach „Stoppen“ aus bis zur nächsten Frage
- Updates: „Jetzt prüfen“ zeigt ein Ladesymbol, bis die Prüfung fertig ist

## 3.17.19 (2026-11-23 17:41)
- KI-Assistent: „Import zurücknehmen“ unter Gedächtnis – nimmt den letzten Import in einem Schritt zurück, nur Notizen, die seitdem nicht geändert, angeheftet oder ersetzt wurden; der Rest bleibt und wird genannt (nur am Mac, im Änderungsprotokoll mit Anzahl)
- KI-Assistent: Gedächtnis-Export – Adressen in Notizen (https://…, www.…, E-Mail) bleiben Text, kein Link
- KI-Assistent: Änderungsprotokoll zeigt eine Frage an Claude ganz (bis 1.000 Zeichen), nicht nur den Anfang

## 3.17.18 (2026-11-23 17:38)
- Entwicklung: Prüfsatz für den Assistenten (`tests/assistant_eval`) – 73 Aufgaben durch den Assistenten auf der Demo-Welt; am Mac mit dem echten Modell
- Entwicklung: Fahrplan – Bildeingabe und Prüfsatz in Kontor unter Offen

## 3.17.17 (2026-11-23 16:41)
- KI-Assistent: sucht Ursachen statt Zeilen aufzuzählen – über Konten, größte Umsätze und Beteiligungen bis in die Gesellschaft dahinter
- KI-Assistent: trennt Belegtes von Vermutetem („vermutlich …, weil …“)
- KI-Assistent: jedes Modell so gefragt, wie sein Hersteller es empfiehlt (Qwen, Gemma)
- KI-Assistent: Gedanken bleiben zwischen den Abfragen einer Antwort erhalten
- KI-Assistent: „Ausgewogen“ denkt vor jeder Abfrage und vor der Antwort (je bis 4.000 Token); Qwen3.8 auf mittlerer Denkstufe
- KI-Assistent: großer Kontext – längere Ergebnisse je Abfrage (Tabellen, Seite, Internet)
- KI-Assistent: wird der Platz knapp, weichen zuerst alte Gedanken und die ältesten Fragen – nicht mehr der ganze Verlauf
- KI-Assistent: verstümmelte Abfrage des Modells beendet die Antwort nicht mehr
- Demo: Kaufnebenkosten der Parkweg GbR – ein Fall für „Warum ist mein Nettovermögen gefallen?“

## 3.17.16 (2026-11-23 15:50)
- Cashflow: Zahlung in einen anderen Bereich nimmt keine von Hand gebuchte Gegenbuchung mehr, die genauso gut zu einer anderen Zahlung ohne IBAN passt – Einlage und Entnahme stimmen auf beiden Seiten überein
- Entwicklung: Zufallsfall der Nacht (754384078) behoben und fest aufgenommen

## 3.17.15 (2026-11-23 15:49)
- KI-Assistent: fragt auf Wunsch Claude (Anthropic) – Stufe 4 der Internetsuche, ein stärkeres Modell, das selbst im Web sucht; nur mit eigenem API-Schlüssel
- KI-Assistent: jede Frage an Claude vorher im ganzen Wortlaut auf der Karte, nie ohne Klick – auch im erlaubten Chat; auf eigene Daten geprüft
- KI-Assistent: Claudes Antwort gilt als fremder Text – danach keine Änderungen im Chat; genannte Quellen lesen erst nach Klick
- Einstellungen: KI-Assistent → Internet – Claude-Schlüssel, Modell (Opus 5.5, Sonnet 5.5, Fable 5.2), Anfragen je Tag (ab Werk 20)
- Einstellungen: Protokoll nennt je Frage an Claude die Token; lange Einträge brechen um statt abgeschnitten zu werden
- Updates: dieses Update braucht deine Freigabe – neuer Weg nach außen (api.anthropic.com, nur mit deinem Schlüssel und Klick), Prüfliste ergänzt

## 3.17.14 (2026-11-23 14:29)
- Entwicklung: macOS-Test des eigenen Pythons – eine Annahme über unsignierte Programme entfernt (geladen, geprüft und probegestartet lief es dort)

## 3.17.13 (2026-11-23 13:50)
- Updates: „Verwendete Programme“ – alles Fremde, das Kontor nutzt, mit Version, Lizenz, Herkunft und ob es abgeschirmt läuft: Python, llama.cpp, jedes Modell, Bordmittel von macOS
- Hilfe: Abschnitt „Verwendete Programme“
- Entwicklung: `components.py` – künftige Bibliotheken brauchen dort einen Eintrag; ein Test verlangt die Lizenz zu jedem Modell der Listen; Platz für Bibliotheken neben Kontors Python reserviert

## 3.17.12 (2026-11-23 13:50)
- Python: Kontor läuft auf Wunsch mit einem eigenen, aktuellen Python 3.15 statt Apples 3.9 (ohne Sicherheitsupdates) – Einstellungen → Updates → Python
- Python: geladen nur nach Klick von GitHub – Prüfsumme, Vergleich jeder Datei, Test mit allen Teilen von Kontor, erst dann umgestellt
- Python: startet es einmal nicht, läuft Kontor sofort mit dem Python des Macs weiter und sagt es – „Erneut versuchen“ lädt es neu
- Installation: richtet das eigene Python gleich mit ein (ohne: `KONTOR_PYTHON=apple`); Deinstallieren entfernt es
- Übersicht: Hinweis, solange das Python des Macs keine Sicherheitsupdates bekommt
- Updates: dieses Update braucht einmal deine Freigabe – Kontor kann jetzt eine Datei von GitHub laden (Python) und sie starten; die Prüfung selbst kennt das neu
- Entwicklung: macOS-Test lädt das echte Python, stellt um, beschädigt es, deinstalliert, aktualisiert von der Version davor

## 3.17.11 (2026-11-23 13:38)
- KI-Assistent: Gedächtnis exportieren – eine Datei zum Lesen (Markdown) mit denselben Notizen als Daten für Programme (JSON); je Notiz Tag, Herkunft, angeheftet, was sie ersetzt hat
- KI-Assistent: Gedächtnis importieren – so eine Datei oder eine Liste mit einer Notiz je Zeile aus einem anderen System; vorab geprüft, ganz oder gar nicht
- KI-Assistent: Importiertes ist gekennzeichnet, nie angeheftet, ersetzt nichts; schon Gemerktes bleibt draußen, Zugangsdaten nie
- KI-Assistent: beides unter Einstellungen → KI-Assistent → Gedächtnis, nur am Mac; im Änderungsprotokoll nur die Anzahl

## 3.17.10 (2026-11-23 10:12)
- Zugang: iPhone mit eigenem Face-ID-Schlüssel (Passkey), am Mac per QR-Code hinzugefügt; Anmeldung mit Face ID
- Zugang: jede Änderung vom iPhone mit Face ID bestätigt; sonst alles wie am Mac – nur Zugang, Updates, Einrichtung des Assistenten, Sicherung laden, Zurücksetzen, Passwort am Mac
- Zugang: Geräteliste am Mac – „Ändern“ je Gerät, „Entfernen“ meldet sofort ab
- Zugang: Kategorien vom iPhone gleich in MoneyMoney; wartende Buchungen vom iPhone freigeben
- Zugang: Tailscale-Prüfung (Tailnet Lock, serve/Funnel) mit Anleitung; gibt serve/Funnel Kontor weiter, ist die Anmeldung am Mac gesperrt
- Sicherheit: über einen Proxy weitergereichte Anfragen abgelehnt – galten vorher als „am Mac“
- Entwicklung: Rundgang in macOS' WebKit zählt jetzt wie jeder Schritt

## 3.17.9 (2026-11-23 06:58)
- KI-Assistent: Modellliste verständlich – Gruppen „Gründlich“, „Schnell“, „Klein“; je Modell wofür es taugt, Hersteller, Lizenz, Größe, Speicherbedarf
- KI-Assistent: je Modell, ob es auf diesem Mac gut, knapp oder nicht läuft – was nicht passt, nennt den nötigen Arbeitsspeicher und lässt sich nicht laden
- KI-Assistent: „empfohlen“ nur das gründlichste Modell, das gut läuft (Qwen3.8 27B) – richtige Antworten vor Tempo; auf kleinen Macs keines
- KI-Assistent: Gemma 4 und kleine Modelle unter „nur für einfache Fragen“; das gewählte Modell wechselt nie von selbst
- Entwicklung: macOS-Lauf prüft mit echtem llama.cpp die Abschirmung über eine Socket-Datei statt 127.0.0.1 (nur Bericht)

## 3.17.8 (2026-11-23 05:49)
- Buchungsregeln: getilgtes oder überzahltes Darlehen – keine Zinsen mehr (auch bei Jahresbasis), Hinweis solange überzahlt; ebenso im Darlehensplan
- Entwicklung: Regel „GitHub ist das einzige Gedächtnis“; Entscheidungen zum iPhone-Zugang und zu überzahlten Darlehen im Fahrplan

## 3.17.7 (2026-11-23 04:42)
- Entwicklung: Entscheidungen vom 23.11. im Fahrplan – KI-Plattform, Claude als Recherche-Stufe, Abschirmung, aktuelles Python, fertige Bibliotheken, Gedächtnis-Export, Tailscale-Prüfung, Antworten vor Tempo

## 3.17.6 (2026-11-23 04:24)
- Planung: Regeln je Bereich, Position und Kategorie – die tiefste gewinnt; Methode und Steigerung (Standard, keine, eigene %) je für sich
- Planung: Kategorien werden geplant – Position = Summe ihrer Kategorien; eigene Werte je Zelle, auch je Kategorie
- Planung: jede Planzahl zeigt im Tooltip, wie sie entsteht – auch für den Rechtsklick des Assistenten
- Planung: Modelle mit einem Klick (Gleichmäßig, Vorsichtig, Wie Vorjahr, Budget); Kennzahlen Sparquote, Reichweite, Zinslast
- Planung: Rückfrage mit Liste, bevor eigene Werte oder Regeln ersetzt würden – behalten oder ersetzen
- Planung: Budget ohne Budget plant Ø 12 Monate statt 0; Kategorien ohne Budget in einer Position ebenso
- Cashflow: Kategorien auch in Planmonaten – Tabelle, Grafiken, Excel
- KI-Assistent: setzt Planregeln (Position, Kategorie, Bereich, Modell) – die Karte nennt, was ersetzt würde

## 3.17.5 (2026-11-23 03:20)
- Updates: Freigabe nur bei echtem Risiko (neuer Weg nach außen, gelockerte Abschirmung, ungelesene Datei, Prüfung selbst geändert)
- Updates: je Eintrag Erklärung in klaren Worten und aufklappbar die betroffenen Zeilen (− entfernt, + neu)
- Updates: geänderte bestehende Wege und der Filter der Internetsuche gebündelt je ein Eintrag; nur Strengeres ohne Freigabe, eine Zeile
- Updates: Prüfung strenger – Dateien in anderer Kodierung, nachträglich geänderte Regeln, versteckte Zeichen werden gefunden
- Updates: dieses Update braucht einmal deine Freigabe – die Prüfung selbst hat sich geändert

## 3.17.4 (2026-11-23 02:50)
- Buchungsregeln: Zins auf den Stand zum Jahresanfang – nur die letzten Monate gelesen und Darlehen im Vorjahr ruhend: im ersten Jahr fehlten die Zinsen
- Entwicklung: Zufallswelten vielfältiger – leere Monate und Jahre, Schübe mit Hunderten Buchungen, stark schwankend, konstant, saisonal, Konten mittendrin auf und zu

## 3.17.3 (2026-11-23 02:14)
- Hilfe: genannte Seiten von Kontor öffnen per Klick direkt die Seite (fett mit ↗) – Sprünge innerhalb der Hilfe bleiben unterstrichen
- Entwicklung: Rundgang in macOS' WebKit (Engine der Mac-App) auf GitHub – jede Seite ohne Skriptfehler, echter Rechtsklick auf eine Zelle

## 3.17.2 (2026-11-23 01:42)
- KI-Assistent: Rechtsklick am Mac nimmt die angeklickte Zelle oder Zahl mit Zeile, Spalte und Beschreibung – nicht mehr nur das Wort, das Safari und die Mac-App beim Rechtsklick markieren (Hauptursache falscher Kurzerklärungen)
- KI-Assistent: Beschreibung kompakter – die angeklickte Stelle ganz, die umliegenden nur in einem Satz
- KI-Assistent: Rechtsklick auf eine Kategorie im geöffneten Ring nennt ihre eigenen Zahlen statt die der Position
- KI-Assistent: Rechtsklick ordnet auch gekürzte Zahlen (420T €) und Veränderungen in Klammern ihrer Bedeutung zu
- KI-Assistent: sagt klar, wenn er nicht weiß, was eine Zahl ist – keine Vermutung als Tatsache
- KI-Assistent: übernommene Kurzerklärung als die des Assistenten gekennzeichnet, nie als Annahme des Nutzers
- KI-Assistent: Gedanken lassen sich schon während des Nachdenkens aufklappen und darin scrollen
- KI-Assistent: Bilder aus der Zwischenablage (⌘V) in den Chat einfügen
- Oberfläche: Rechtsklick-Menü schließt nicht mehr durch ein nachlaufendes Scrollen

## 3.17.1 (2026-11-22 21:43)
- KI-Assistent: kennt jede Stelle jeder Seite – Rechtsklick und Fragen zur Seite wissen, ob eine Zahl Wert des Zeitraums, Anteil oder Veränderung ist
- KI-Assistent: Rechtsklick benennt jeden Teil einer Beschriftung (Betrag, Veränderung), nennt Zeitraum, Plan- und laufende Spalten, Kennzeichen; Achsen und Knöpfe zählen nicht
- KI-Assistent: Werkzeuge mit den Begriffen der Seiten (Vermögen, liquides Vermögen, Prozent nach Größe); Umsatzsuche ohne Kontors eigene Regelbuchungen
- Cashflow: Depotänderung vor dem ersten bekannten Stand eigene Zeile „bis … unbekannt“
- Einstellungen: Speichern behält, was ein anderes Fenster oder Gerät inzwischen geändert hat; beide an derselben Stelle: Hinweis zum Neuladen
- Sperren (⌘L, Leerlauf): Eingetipptes bleibt nach der Anmeldung stehen
- Einrichtung: Passwort bei Doppelklick nur einmal festgelegt; Steuer und Belege erst nach eigener Angabe erledigt
- Auto-Buchungen: Auswahl und Änderungen bleiben beim nächsten Abgleich (neuer Hinweis: abgewählt); zurück zu „mit Freigabe“ nie durch Fehler blockiert
- Zugang: Passwort ändern mit Wiederholung; von unterwegs „Nur ansehen“ in der Seitenleiste
- Seitenfenster: Eingetipptes auch in grauen Feldern erkannt; Esc fragt vorher
- Konten & Regeln: Kontenliste nach dem Abgleich neu; Bereiche zeigen, was unter Konten zugeordnet ist; Auswahl „wie unter Bereiche“
- Konten & Regeln: Zinssätze nur mit lesbarem Datum; Kontostände-Import lehnt verrutschte Spalten ab
- Sicherung: Einstellungen in falscher Form lehnen die Datei ab
- Planung: Ø 12/6 Monate über die bekannten Monate; Darlehensplan zeigt und behält das Modell der Regel; Ereignis- und Immobilienzeilen ohne eigene Methode
- Übersicht: Vermögensstruktur zählt Schulden je Konto (Darlehen im Plus beim Vermögen); Legende nennt „Unklar“
- Immobilien: Soll/Ist mit Restschuld wie in der Kalkulation, grün = besser als geplant
- Steuer: AfA-Feld nur mit eigenem Wert, berechneter grau – Speichern übernimmt ihn nicht mehr als eigenen
- Umsätze: Umbuchungen ohne „ohne Kategorie“; Kategoriepfade lesbar; Filter einer Empfängerzeile ohne „Unklar“
- Hilfe: Planung, Buchungsregeln und laufendes Jahr wie auf den Seiten; Tooltips Geld unterwegs und Heatmap berichtigt
- Entwicklung: „Was wo gepflegt wird“ in CLAUDE.md; Beschreibung jeder Stelle in docs/ui, geprüft von test_ui_docs und dem Rundgang

## 3.17.0 (2026-11-22 18:05)
- Gesamtprüfung aller Versionen seit 3.16.0: Funktionen, Texte, Hilfe, README und Fahrplan gegen den Code geprüft, Gefundenes behoben
- Sicherheit: neu einzurichten – alte Schlüsselbund-Umstellung und Reste älterer Versionen entfernt; Sicherungen und Pakete erst ab 3.17.0
- Anmeldung: „Demo“ wirkt auch bei offener Touch-ID-Abfrage – das Fenster nennt Demo oder echtes Kontor, nie entsteht die andere Sitzung
- Sicherung: vorab ganz geprüft, ganz oder gar nicht; Zugang bleibt wie an diesem Mac; Regeln aus der Sicherung warten auf Bestätigung
- Datenordner: jede Datei atomar geschrieben; beschädigte Einstellungen werden beiseitegelegt statt auszusperren; Erneuern übergeht Beschädigtes
- KI-Assistent: Auto-Buchungen nur genau wie gezeigt, nie aus unbestätigten Regeln; jede Buchung auf der Karte und im Protokoll
- KI-Assistent: Protokoll zeigt jede Änderung Zeile für Zeile; ohne Protokolleintrag kein Abruf
- Gedächtnis: Zugangsdaten strenger erkannt (auch ohne Ziffern, Kartennummern); „Vergiss“ nur mit Befehl und passender Notiz; Vergessenes bleibt vergessen
- Internetsuche: Filter gegen eigene Daten verschärft (Namen mit „und“/Rechtsform, Umschreibungen, wartende Buchungen, eingetragene Stände)
- Abschirmung: Modell, Internet-Leser und Belegleser schreiben nie in Kontors Zwischenordner oder die Modul-Caches der Compiler
- Update-Prüfung: erkennt auch geänderte Filter, Hosts, Abschirm-Regeln und untergeschobene Dateien; im Git-Klon ganzer Stand, nur vom eingestellten Repository
- Buchungsregeln: Zinsen und Anteile exakt gerechnet, kaufmännisch auf den Cent; doppelte Buchungen von Kontor gemeldet
- Tabellen aus PDFs: 12.40 neben 2.500 bleibt Text (außer als Uhrzeit oder Datum)
- Belege: verknüpfte Dateien außer PDF und CSV nur im Finder gezeigt, nie geöffnet
- Mac-App: Fensterknöpfe, wo macOS sie hinsetzt – gleicher Abstand oben und links
- Diktieren: ohne Mikrofonfilter auch kein Pegelausgleich des Systems
- KI-Assistent: Denkaufwand nur noch oben im Panel (keine versteckte Einstellung); Hilfe-Funde nach Bedeutung gekennzeichnet
- Oberfläche: Texte, Pfade und Begriffe vereinheitlicht (de/en), Einzahl/Mehrzahl, Zeiten und Monate einheitlich, Grün im hellen Modus lesbarer
- Hilfe, README und Hilfe-Bilder neu
- Entwicklung: toter Code und ungenutzte Texte entfernt; macOS-Job prüft die Abschirmung von Modell und Internet-Leser

## 3.16.100 (2026-11-22 12:55)
- Entwicklung: Nachtlauf behoben – Zufallswelten bauen keine zwei gleich hohen PayPal-Umbuchungen im Wochenabstand mehr (bleibt bewusst offen); der gefundene Fall läuft bei jedem Test mit
- Entwicklung: Test der gespeicherten Verläufe wartet auf das Speichern (schlug unter Last zufällig fehl)
- Mac-App: Fensterknöpfe bleiben auf Höhe des Seitentitels, auch wenn macOS die Titelzeile neu anordnet (Mac-Prüfung auf GitHub war deshalb zeitweise rot)

## 3.16.99 (2026-11-22 09:19)
- KI-Assistent: findet in Hilfe und Umsätzen auch nach Bedeutung – Funde so gekennzeichnet
- Gedächtnis: Namen in von Hand angelegten Notizen gehen nie in eine Internetsuche (vom Modell erkannt)
- KI-Assistent: eine Frage direkt nach einer Antwort wird nicht mehr abgelehnt, während Kontor noch nachbereitet

## 3.16.98 (2026-11-22 07:34)
- KI-Assistent: sucht bei Bedarf auch in gespeicherten Verläufen – nach Wörtern und Bedeutung
- Verläufe: eigenes verschlüsseltes Suchverzeichnis; aus Unterhaltungen mit Internet- oder Belegtext nur deine Fragen
- Gedächtnis: Vergessenes taucht auch dort nicht wieder auf; gelöschte Verläufe verschwinden aus der Suche
- Entwicklung: Test der Suche nach Bedeutung ohne Wettlauf mit dem Einbetten

## 3.16.97 (2026-11-22 07:05)
- KI-Assistent: Suche nach Bedeutung – drittes, kleines Modell (Qwen3-Embedding 0,6B) unter Einstellungen → KI-Assistent
- Gedächtnis: findet Notizen auch ohne gemeinsames Wort („Ferien“ zu „Urlaub“); ohne das Modell weiter nach Wörtern
- Gedächtnis: Vergleichswerte der Notizen verschlüsselt neben den Notizen, im Hintergrund gemacht, weg mit der Notiz
- Updates: die Prüfung meldet eine geänderte Startzeile der Modelle – das dritte Modell startet nur für Vergleichswerte (--embedding)

## 3.16.96 (2026-11-22 06:21)
- Demo: nur noch mit deiner Anmeldung (Passwort oder Touch ID) – „Demo“ unten auf der Anmeldeseite stellt sie um
- Demo: eigene Umgebung – gesperrt bleibt sie und öffnet wieder wie zuvor; weg nach 2 Stunden ohne Anmeldung, mit neuem Passwort oder beim Neustart
- Demo: Assistent mit deinen Rechten, auch Internet (mit deinem Tavily-Schlüssel, Abrufe auch in deinem Protokoll); eigenes Gedächtnis und eigene Verläufe
- Demo: neue Beispieldaten – Privatperson über 4 Jahre, Muster UG über 2 Jahre, Parkweg GbR mit Immobilie
- Anmeldung: falsches Passwort heißt jetzt „Passwort falsch“ statt „Nicht angemeldet“

## 3.16.95 (2026-11-22 05:49)
- KI-Assistent, Internet: neue amtliche Quellen – Rechtsinformationsportal (auch BFH), Meldungen von BMF, Bundesbank und EZB, OECD, Weltbank, BIZ, Branchenzahlen (Bundesbank, Eurostat)
- Tavily (Stufe 3) auch ohne Konto; eigener Schlüssel optional für mehr Abrufe
- Eine neutrale Kennung an alle Quellen; lehnt eine Quelle ab, steht es auf der Karte

## 3.16.94 (2026-11-22 05:42)
- Diktieren: neue Einstellung „Mikrofonfilter“ – aus: das Mikrofon hört sofort nach dem Klick (statt nach etwa 2 s)
- Diktieren: ohne Filter gleicht Kontor die Lautstärke selbst aus – leise Aufnahmen gelten nicht mehr als Stille
- Diktieren: Protokoll nennt Mikrofonart und Pegel der Aufnahme

## 3.16.93 (2026-11-22 05:38)
- KI-Assistent: zur Frage passende Notizen kommen von selbst mit – auch in anderer Wortform, als Wortteil oder mit Tippfehler
- KI-Assistent: unter der Antwort „Aus deinen Notizen: …“ – worauf sie beruht
- KI-Assistent: sucht bei Bedarf selbst in deinen Notizen
- Gedächtnis: zuletzt genutzte Notizen gehen mit jeder Frage mit; die Suche in der Liste findet auch Wortformen und Tippfehler
- Gedächtnis: Vergessenes verschwindet sofort auch aus der laufenden Unterhaltung

## 3.16.92 (2026-11-22 04:57)
- KI-Assistent: Internet je Chat einmal erlauben – danach vertrauenswürdige Quellen ohne Rückfrage, im Chat sichtbar
- KI-Assistent: Seiten anderer Websites weiter immer einzeln freigeben
- Einstellungen: unter Internet wählbar, welche Quellen und Websites ohne Rückfrage gehen
- KI-Assistent: Scrollleiste langer Adressen unter dem Text statt darüber

## 3.16.91 (2026-11-22 04:50)
- Darlehen: Hinweis, wenn gebuchte Zinsen nicht mehr zu Restschuld oder Zinssatz passen – mit den richtigen Beträgen je Monat
- Darlehen: neue Zinsen rechnen schon so, als wären die genannten angepasst; ab 1 € Abweichung, nicht nach Wartendem oder Doppeltem
- Darlehen: Zinswechsel mitten im Jahr bei Jahresbasis gemeldet (gilt erst ab dem Folgejahr)
- Darlehen: Zinssatz im Buchungstext so genau wie eingegeben

## 3.16.90 (2026-11-22 04:30)
- KI-Assistent: PDF-Tabellen am Mac richtig gelesen – Wörter standen ab der zweiten Zeile an falscher Stelle (der GitHub-Lauf von 3.16.88 war deshalb rot)
- KI-Assistent: einzelne Minuszeichen und Striche in PDFs bleiben in ihrer Zeile

## 3.16.89 (2026-11-22 03:59)
- Belege nur in Kontor: Einstellung „Verweis in MoneyMoney“ entfällt, nie mehr ein Belegpfad im Kommentar eines Umsatzes
- MoneyMoney-Brücke: bei Umsätzen nur noch die Kategorie, alles andere abgewiesen

## 3.16.88 (2026-11-22 03:57)
- KI-Assistent: liest Tabellen aus PDFs und Bildern (BWA, Summenlisten, Wertenachweise) – alle Seiten, zu einer Tabelle zusammengesetzt
- KI-Assistent: Seitenköpfe, Seitenzahlen und wiederholte Tabellenköpfe fallen heraus; Summen rechnet Kontor
- KI-Assistent: Zahlen wie geschrieben (Minus davor, dahinter oder abgesetzt; S/H; fremde Währung) – Unklares bleibt Text
- KI-Assistent: gescannte Seiten über die Texterkennung des Macs, schiefe Scans gerade gerichtet
- Hilfe: Dateien im Assistenten (PDF, Bild, Excel)

## 3.16.87 (2026-11-22 03:31)
- Demo: Kontor zum Vorzeigen mit erfundenen Beispieldaten – klein und hellgrau unten auf der Anmeldeseite, ohne Passwort
- Demo: eigener Ordner und eigene Anmeldung – nie deine Daten, Einstellungen, Belege, Verläufe oder das Gedächtnis des Assistenten
- Demo: fast alles bedienbar, auch der Assistent (dein Modell, ohne Internet); Einstellungen und Einrichtung ausgeblendet
- Demo: „Beenden“ oder die Sperre löscht alles darin; auf dem Gerät und in der iPhone-Offline-Kopie bleibt nichts davon
- Entwicklung: jede Anfrage des Dienstes ist für die Demo erlaubt oder abgelehnt (Test)

## 3.16.86 (2026-11-22 03:19)
- Mac-App: Fensterknöpfe verdecken „Kontor“ nicht mehr, auch wenn die App seit vor dem Update offen ist

## 3.16.85 (2026-11-22 03:12)
- KI-Assistent: seltener Fehler bei „neuere Versionen“ behoben (ein Download endete währenddessen – der GitHub-Lauf von 3.16.81 war deshalb rot)
- Gedächtnis: wartet nach einem Neustart auf die Anmeldung – liest vorher nichts und hält keine Datei für beschädigt

## 3.16.84 (2026-11-22 02:59)
- Entwicklung: GitHub prüft am Mac, dass openssl das Geheimnis über die Pipe bekommt und die Touch-ID-Antwort aus Swift in Python aufgeht

## 3.16.83 (2026-11-22 02:44)
- Sicherheit: Daten erst nach Anmeldung lesbar – Datenschlüssel nur mit Passwort oder Touch ID, danach nur im Arbeitsspeicher; nicht mehr im Schlüsselbund
- Sicherheit: nach Neustart oder Update einmal anmelden (Mac und iPhone); Abgleich und Auto-Buchungen warten, danach laufen sie weiter, auch gesperrt
- Sicherheit: Umstellung bei der ersten Anmeldung mit Passwort; alter Schlüssel erst weg, wenn der neue jede Datei öffnet
- Sicherheit: openssl bekommt das Geheimnis über eine Pipe statt in der Umgebung (für andere Programme unsichtbar)
- Touch ID: öffnet die Daten auch nach einem Neustart (Secure Enclave); Passwort vergessen: beim Ändern altes Feld leer lassen
- Einstellungen: Datenschlüssel erneuern über die Anmeldung, Abbruch wird bei der nächsten Anmeldung abgeschlossen; Zurücksetzen mit Passwort löscht ihn mit
- Entwicklung: vor der Anmeldung ist `app.store.is_open` falsch – nichts darf die Ablage lesen (Zeitplan, Threads, Neues: vorher prüfen); neue verschlüsselte Ordner in `storage.ENC_DIRS`

## 3.16.82 (2026-11-22 02:37)
- Tastenkürzel: ⌘R lädt die Seite neu – wie im Browser, auch in der Mac-App und Safaris Dock-App
- Tastenkürzel: Mit MoneyMoney abgleichen jetzt ⇧⌘R

## 3.16.81 (2026-11-22 02:36)
- KI-Assistent: Gedächtnis, Schritt 2 – merkt sich von selbst, was du ihm sagst und was dauerhaft ist; „Merk dir …“ gilt immer, „Vergiss …“ löscht
- Unter der Antwort: „Gemerkt: …“ mit „Zurücknehmen“, bei Widerspruch „ersetzt: …“; Vergessenes lässt sich zurückholen, solange Kontor läuft
- Nur aus deinen eigenen Worten (auch Eingefügtes, so gekennzeichnet) – nie aus Buchungstexten, Belegen, Dateien, Seiten oder dem Internet
- „Merk dir das“ nimmt die Antwort davor; nach Internet- oder Belegtext in der Unterhaltung erst nach deinem Klick
- Die nächste Frage geht sofort, auch während Kontor noch merkt; von einem Gerät, das nur ansehen darf, wird nichts gemerkt
- Namen in Notizen aus dem Chat benennt das Modell – sie gehen nie in eine Internetsuche

## 3.16.80 (2026-11-22 02:18)
- KI-Assistent: eine Einstellung für die automatische Suche nach neueren Versionen (llama.cpp, Modell, Diktiermodell) – täglich, wöchentlich, monatlich, nie; Standard monatlich
- KI-Assistent: Punkt im Menü für llama.cpp und die Modelle in Gebrauch (keine Sonderregel für llama.cpp mehr); letzte Suche und Fund bleiben über Neustarts
- KI-Assistent: eigener Abschnitt „Aktualisierung“ (Automatisch suchen, Jetzt suchen, Alles aktualisieren) und „Ablage“
- KI-Assistent: Fortschritt beim Laden steht beim richtigen Teil (Diktiermodell unter „Modell zum Diktieren“)
- KI-Assistent: klarere Begriffe – „Programm“, „Modell für Antworten“, „Modell zum Diktieren“, „Diktiermodell“; Tooltips erklären den Unterschied
- Hilfe: Suche nach neueren Versionen, Netzverbindungen von selbst, Prüfung vor dem Update
- Entwicklung: Hilfe-Texte und README ab jetzt mit jeder Änderung; nur Hilfe-Bilder beim großen Versionssprung

## 3.16.79 (2026-11-22 02:10)
- Auto-Buchungen: Zinsen nach einer abgewählten Tilgung warten mit, statt aus dem Saldo ohne sie gebucht zu werden – in der Freigabe „wartet“
- Auto-Buchungen: Kennzeichen „neu“ für Buchungen, die die Neuberechnung dazunimmt, wieder sichtbar
- Entwicklung: Zufallswelten für die Buchungsregeln (Beteiligung, Darlehen, Kontenspiegel), nachts auf zwei weiteren Rechnern

## 3.16.78 (2026-11-22 02:06)
- Diktieren: Knopf wird erst rot, wenn das Mikrofon wirklich hört – nach einer Pause dreht er etwa 2 s (so lange braucht macOS), direkt nach einer Aufnahme sofort
- Diktieren: kein verschluckter Anfang mehr bei der ersten Aufnahme
- Diktieren: Protokoll nennt zusätzlich den Anteil reiner Stille

## 3.16.77 (2026-11-22 02:05)
- Updates: Hauptversion schließt die Schritte davor ab – 3.17 zeigt, was 3.16.1 bis 3.17.0 bringen; die kommende als „in Arbeit“
- Updates: Versionsspanne je Hauptversion beim Aufklappen („Alle 24 Versionen (3.15.1 bis 3.16.0)“); Überblicke neu zugeordnet
- Entwicklung: große Themen der Unterversionen 3.16.x unter „## 3.17“ in HIGHLIGHTS.md

## 3.16.76 (2026-11-22 02:01)
- KI-Assistent: Internetrecherche fragt nur noch einmal – eine Karte mit allen Abrufen, jeder abwählbar, ein Klick gibt sie frei
- KI-Assistent: höhere Stufe als Reserve „nur falls nötig“; bis zu 3 Treffer lesen mit derselben Freigabe, ohne zweite Karte
- KI-Assistent: je Abruf aufklappbar Adresse und Gesendetes; lange Adressen scrollen in ihrer Zeile
- KI-Assistent: Suchwörter mit unsichtbaren Zeichen abgelehnt; gestoppte Abrufe stehen im Protokoll

## 3.16.75 (2026-11-22 02:00)
- Updates: Zusatz „Quelle: main“ entfällt

## 3.16.74 (2026-11-22 02:45)
- Entwicklung: `Store.is_open` („Ablage offen?“) – ohne Schlüssel wirft jedes Lesen/Schreiben `StoreLocked`; wer die Ablage liest, prüft das vorher
- Entwicklung: Schlüsseldatei-Bausteine (Datenschlüssel nur mit dem Passwort verpackt), noch ungenutzt

## 3.16.73 (2026-11-22 01:55)
- Mac-App: Fensterknöpfe auf Höhe des Seitentitels; schmales Fenster mit denselben Abständen wie das breite

## 3.16.72 (2026-11-22 01:40)
- KI-Assistent: Denkaufwand nur noch oben im Assistenten wählbar, je Gerät gemerkt – nicht mehr in den Einstellungen

## 3.16.71 (2026-11-22 01:40)
- KI-Assistent: Gedächtnis, Schritt 1 – Notizen unter Einstellungen → KI-Assistent: hinzufügen, suchen, ändern, anheften, vergessen, alles vergessen; Schalter
- KI-Assistent: jede Frage bekommt angeheftete und neueste Notizen mit (höchstens 1.500 Token, egal wie viel gemerkt ist)
- Gedächtnis: verschlüsselt, in der Sicherung (als „aus einer Sicherung“ gekennzeichnet zurück), nie im Protokoll; Zurücksetzen und Deinstallieren löschen es
- Gedächtnis: nie Passwörter, PINs, TANs, Schlüssel, Kartennummern; erkannte Namen nie in der Internetsuche
- Protokoll der Änderungen: Merken, Ändern, Vergessen mit Zeit und Auslöser – Vergessenes verschwindet auch dort
- Sicherung wiederherstellen: bis 64 MB
- Noch offen: Merken im Chat („Merk dir …“) und Suche

## 3.16.70 (2026-11-22 01:26)
- KI-Assistent: sucht von selbst nach neueren Versionen (llama.cpp, Modell, Diktiermodell) – täglich, einstellbar unter Betrieb; geladen wird dabei nichts
- KI-Assistent: Punkt im Menü bei Einstellungen, wenn es für Modell oder Diktiermodell in Gebrauch Neueres gibt (llama.cpp erst nach zwei Wochen)
- KI-Assistent: „Alles aktualisieren“ lädt alles Gefundene nacheinander; Abbrechen beendet alles
- KI-Assistent: eigene Modelle lassen sich aktualisieren
- Updates: Hinweis bei „Automatisch prüfen“ stimmt wieder (auch die Suche des KI-Assistenten geht von selbst ins Netz)

## 3.16.69 (2026-11-22 01:25)
- Schmales Fenster: Bereichsauswahl mittig
- Mac-App, schmales Fenster: Menü und Seitentitel oben neben den Fensterknöpfen

## 3.16.68 (2026-11-22 01:25)
- Mac-App: Suche schließt mit erneutem ⌘F oder einem Klick daneben
- Mac-App: geschlossene oder geleerte Suche ohne gelbe Markierungen

## 3.16.67 (2026-11-22 01:11)
- Updates: Änderungen je Hauptversion (3.16, 3.15 …) – kurzer Überblick der großen Themen immer sichtbar, einzelne Versionen aufklappbar
- Updates: die neuesten drei Hauptversionen offen, ältere zusammengefaltet; Entwicklungs-Punkte blasser
- Entwicklung: Überblick je Hauptversion in HIGHLIGHTS.md – ein großes neues Thema ergänzt ihn (Regel und Test)

## 3.16.66 (2026-11-22 00:59)
- KI-Assistent: Excel-Tabellen (.xlsx) im Chat lesbar – als Raster mit Zelladressen, Summen rechnet Kontor exakt
- KI-Assistent: Datei ohne Text wird für sich bewertet statt „Lege diesen Beleg ab“; nichts vorgeschlagen
- KI-Assistent: Dateiauswahl zeigt nur lesbare Formate, Tooltip nennt sie; Belege lesen braucht nur das Leserecht
- KI-Assistent: Verlauf zeigt Fragen nur mit Datei wieder an

## 3.16.65 (2026-11-22 00:52)
- Diktieren: Mikrofon wieder mit Echo-, Rausch- und Pegelfilter (behebt verschluckte Anfänge und fehlende Sätze seit 3.16.57)
- Diktieren: Knopf wird rot, sobald der Ton ankommt – kein Warten mehr auf das erste Geräusch
- Diktieren: leise Anfänge bleiben drin (0,8 s vor dem ersten Laut statt 0,25 s), auch leise Sprache zählt

## 3.16.64 (2026-11-22 00:41)
- ⌘F sucht: in der Hilfe und bei Umsätzen im eigenen Suchfeld, sonst in der Mac-App eine Suchleiste (Treffer markiert und gezählt, ⌘G/⇧⌘G, ↩, esc)
- Suchfeld der Hilfe bleibt beim Scrollen sichtbar
- Mac-App-Menü mit Kontors Kürzeln: ⌘R abgleichen, ⌘S sichern, ⌘L sperren, ⌘K Assistent, ⌘1–9 Seiten; Neu laden jetzt ⇧⌘R
- Kürzel in den Tooltips – nur, wo sie wirken (im Browser kein ⌘R/⌘1–9)
- ⌘S speichert auch die Einstellungen (MoneyMoney, Belege)

## 3.16.63 (2026-11-22 00:32)
- Mac-App: Seiten mit denselben Abständen wie im Browser – nur die Fensterknöpfe oben in der Seitenleiste

## 3.16.62 (2026-11-22 00:20)
- Behoben: Kontenspiegel – gespiegelte Buchung verschoben, Original neu eingegeben: nicht mehr doppelt gespiegelt (bis 3 Tage, mit Hinweis)
- Kontenspiegel: abgelehnte Buchungen und von Hand gebuchte Paare werden dabei nie mitgenommen

## 3.16.61 (2026-11-22 00:17)
- Updates: jede neue Version wird vor dem Installieren gelesen – neue Netzzugriffe, Programmaufrufe, Helfer oder Umwege dorthin halten sie an
- Updates: angehaltene Version mit „!“ im Menü, Funde unter Einstellungen → Updates, installiert erst nach deiner Freigabe; unauffällige wie bisher mit einem Klick
- Sicherheit: verknüpfte Dateien öffnen nur als Dokument (Seiten, Skripte und Programme zeigt der Finder); die Oberfläche lädt Dateien nur von Kontor selbst

## 3.16.60 (2026-11-22 00:12)
- Mac-App: keine eigene Titelleiste mehr – Fensterknöpfe in der Seitenleiste, Seitentitel daneben, mehr Platz
- Mac-App: Fenster über die Titelzeile verschieben, Doppelklick wie in macOS eingestellt

## 3.16.59 (2026-11-22 00:03)
- Hilfe: Abschnitt „Internet (nur lesen)“ mit Stufen und Einrichtung des Tavily-Schlüssels; Tooltip mit den drei Schritten

## 3.16.58 (2026-11-22 00:02)
- Behoben: zwei gleich hohe Zahlungen kurz hintereinander – Gegenbuchungen nicht mehr vertauscht, keine falsche „Wertänderung“ oder „unklar“
- Behoben: Handbuchung auf einem Konto eines anderen Bereichs (z. B. „Darlehen von Partnerin“) geht nicht mehr an eine fremde Zahlung gleichen Betrags
- Behoben: gleichartige Zahlungen oder Buchungen am selben Tag werden zugeordnet statt offen gelassen
- Zuordnung: von zwei Zahlungen nimmt die nähere die Gegenbuchung; zwei „Umbuchungen“ passen eher zueinander als zu einer Handbuchung
- Entwicklung: Zufallswelten (1–3 Privatpersonen, bis 4 Firmen, Beteiligungen, Darlehen, PayPal, Miete) – jede Nacht ~3 h neue Fälle
- Entwicklung: feste Liste von Sonderfällen an jeder Art Tag zwischen jeder Art Bereich, bei jedem Testlauf

## 3.16.57 (2026-11-21 23:56)
- Diktieren: neue Einstellung „Sprachmodell starten“ – sofort (mit dem KI-Modell und beim Öffnen des Assistenten) oder erst beim Diktieren; Standard nach Arbeitsspeicher
- Diktieren: Mikrofon ohne Telefonie-Filter (Echo, Rauschen) – kein Warten mehr auf das erste Geräusch, andere Töne werden nicht leiser
- Diktieren: Startzeiten im Protokoll (Mikrofon, Sprachmodell, erstes Geräusch)

## 3.16.56 (2026-11-21 23:50)
- Entwicklung: Gedächtnis des KI-Assistenten im Fahrplan festgelegt (Entschieden)

## 3.16.55 (2026-11-21 23:49)
- Anmeldung: nach einem Update dreht sich „Kontor wird geladen …“ statt eines dunklen Fensters

## 3.16.54 (2026-11-21 23:37)
- Einstellungen → KI-Assistent: „Von wo“ vor „Internet“; Tavily-Schlüssel direkt unter dem Häkchen „Internet“

## 3.16.53 (2026-11-21 23:28)
- KI-Assistent: bei kleinem Kontext (16k) Werkzeuge kompakt (ohne Parameter-Hinweise) – mehr Platz für Frage und Unterhaltung

## 3.16.52 (2026-11-21 23:21)
- KI-Assistent: Stil geschärft – Finanzwahrheit unverblümt, Finanzen/BWL/Rechnungswesen zuerst, mentale Modelle (Psychologie, Spieltheorie, Evolution, Physik) nur wo sie etwas klären, logisch hergeleitet

## 3.16.51 (2026-11-21 23:15)
- KI-Assistent: gespeicherte Verläufe im eigenen Ordner „chats“ im Datenordner; vorhandene ziehen beim Start um
- Einstellungen: Anzahl und Größe der Verläufe, „Ältere als ein Jahr löschen“, Hinweis bei sehr vielen
- Verlaufsliste lädt in Stücken zu 100 („Ältere anzeigen“)
- Sicherheit: neuer Datenschlüssel erfasst auch den Ordner „chats“; Deinstallieren entfernt ihn

## 3.16.50 (2026-11-21 23:05)
- KI-Assistent: beim Nachdenken nur noch „Denkt nach …“ (aufklappbar, mit laufendem Schritt) – fertig wird daraus „Gedanken“

## 3.16.49 (2026-11-21 22:52)
- Belege im Assistenten: Bilder mit transparentem Hintergrund werden vor der Texterkennung auf Weiß gelegt (behebt leeren Text)

## 3.16.48 (2026-11-21 22:46)
- KI-Assistent: Internetsuche nur zum Lesen in drei Stufen – Wikipedia, Gesetze, GLEIF, EZB, Bundesbank, Eurostat / tagesschau, GDELT / Tavily mit eigenem kostenlosen Schlüssel
- Jeder Abruf erst nach deinem Klick; Filter gegen eigene Daten; abgeschirmter Abruf; danach keine Änderungen in derselben Unterhaltung
- Recht „Internet“ ab Werk aus (Einstellungen → KI-Assistent)

## 3.16.47 (2026-11-21 22:45)
- Diktieren: Aufnahme ab dem Klick – sofort lossprechen, auch wenn das Sprachmodell noch lädt; nichts geht verloren
- Diktieren: Knopf dreht, bis das Diktat läuft; erst dann rot, Zeit ab 0:00
- Diktieren: Sprachmodell startet schon beim Klick; startet es nicht, kommt der Fehler sofort

## 3.16.46 (2026-11-21 22:36)
- KI-Assistent: Belege (PDF, Bild) in den Chat ziehen – liest den Text auf diesem Mac, findet den passenden Umsatz, nennt Abweichungen
- Ablegen im Belegordner nach deinem Klick, mit Umsatz verknüpft, zurücknehmbar; Datei nur im Arbeitsspeicher

## 3.16.45 (2026-11-21 22:19)
- KI-Assistent: legt Buchungsregeln an und ändert sie (Darlehen, Beteiligungen, Kontenspiegel) – nach deinem Klick, zurücknehmbar
- Regeln vom Assistenten: ihre Buchungen warten auf Freigabe, bis du die Regel unter Konten & Regeln bestätigst
- Konten & Regeln: Speichern verweigert, wenn sich Regeln inzwischen geändert haben; andere Seiten lassen Regeln unverändert

## 3.16.44 (2026-11-21 22:17)
- Updates: „Neu in …“ zeigt alle Änderungen seit der installierten Version, nicht nur die der neuesten (nach Bezug gruppiert, ohne Entwicklung)

## 3.16.43 (2026-11-21 22:04)
- KI-Assistent: beendet sich ab Werk erst nach 30 Minuten ohne Frage (vorher 10)

## 3.16.42 (2026-11-21 22:03)
- Eigene Mac-App „Kontor“ statt Safaris Dock-App: macOS fragt nur einmal nach dem Mikrofon, danach nie wieder
- Mac-App: Menüleiste (⌘, Einstellungen, ⌘P Drucken, Zoom), Downloads in „Downloads“, Abzeichen im Dock, Darstellung wie in Kontor
- Einstellungen → Allgemein → Als App und Einrichtung Schritt 1: „Mac-App öffnen“
- Deinstallieren entfernt auch die Daten und Freigaben der Mac-App
- Entwicklung: GitHub baut und prüft die Mac-App (Kontor laden, Mikrofon ohne Nachfrage)

## 3.16.41 (2026-11-21 21:56)
- Entwicklung: Nachtlauf auf 6 Rechnern nebeneinander, je ~3 h neue Zufallsfälle; Anzahl in der Zusammenfassung des Laufs

## 3.16.40 (2026-11-21 21:48)
- Behoben: 3.16.32 wiederhergestellt (Ablage der KI-Modelle, Hilfe-Symbole, Texte zu Zurücksetzen und Deinstallieren) – von 3.16.35 versehentlich zurückgesetzt
- Entwicklung: Push-Sperre erkennt auch einen älteren Code-Stand bei richtiger Versionskette (Zeilen der neuesten Versionen verloren)
- Entwicklung: Test des KI-Fensters wartet auf das Zurücksetzen

## 3.16.39 (2026-11-21 21:35)
- Entwicklung: Nachtlauf mit 1000 festen und 1000 jede Nacht neuen Zufallsfällen (~10 min)
- Entwicklung: gefundene Fälle einzeln wiederholbar und danach bei jedem Lauf geprüft

## 3.16.38 (2026-11-21 21:26)
- KI-Assistent: lange Unterhaltungen behalten mehr Fragen im Blick – Nachgelesenes früherer Fragen fällt weg (wird bei Bedarf neu gelesen)

## 3.16.37 (2026-11-21 21:10)
- Entwicklung: Nachtlauf (1000 Zufallsläufe) im Lagebild der Chats; rot behebt ihn der nächste Chat

## 3.16.36 (2026-11-21 21:02)
- KI-Assistent: denkt in der Sprache von Kontor (Gedanken auf Deutsch statt Englisch)

## 3.16.35 (2026-11-21 20:56)
- KI-Assistent: Gedanken und Schritte („Liest die Bilanz“ …) als ein Eintrag; zeigt beim Antworten den laufenden Schritt
- Rechtsklick auf eine Zahl in Grafik oder Karte: Bezug mit Zeile und Wert (etwa „Überschuss: +48.660“) samt Details
- Klick auf den Bezug markiert genau diese Zahl bzw. Zeile (mit ihrem Hinweis), nicht nur die Karte
- Punkt in einer Grafik heißt im Bezug nach Grafik und Stelle (etwa „Nettovermögen · Oktober 2026“)

## 3.16.34 (2026-11-21 20:44)
- Bilanz-Tabelle: Klick auf einen Wert klappt die Zeile zusätzlich auf bzw. zu (Position, Depot, Kennzahlen) – Markierung in der Grafik wie bisher
- Doppelklick/Halten auf einen Wert entfällt dafür
- Auf-/Zuklappen: Seite bleibt stehen, auch wenn sich die Grafik darüber neu aufbaut

## 3.16.33 (2026-11-21 20:30)
- KI-Assistent: schlägt wartende Auto-Buchungen zur Freigabe oder zum Zurückhalten vor – gebucht erst nach deinem Klick, nur am Mac, in MoneyMoney endgültig
- KI-Assistent: was Kontor erst geprüft haben will, gibst du weiter selbst unter Auto-Buchungen frei; Paare werden zusammen zurückgehalten
- KI-Assistent: neues Recht „Auto-Buchungen“ (ab Werk an, jede Buchung erst nach dem Klick)

## 3.16.32 (2026-11-21 20:25)
- KI-Assistent: Ablage von llama.cpp und allen Modellen (auch Diktieren) angezeigt, „Im Finder zeigen“
- KI-Assistent: Hilfe-Symbole bei Programm, Modelle und Ablage
- Zurücksetzen und Deinstallieren sagen, was mit den KI-Modellen geschieht (bleiben bzw. werden gelöscht)

## 3.16.31 (2026-11-21 20:12)
- Einstellungen → KI-Assistent, Mikrofon: in der Dock-App kein falsches „Dauerhaft erlaubt“ mehr – sagt, wann sie wieder fragt, und wie es in Safari ohne Nachfrage geht

## 3.16.30 (2026-11-21 20:03)
- Behoben: KI-Modell fertig geladen – Einstellungen zeigen es sofort, ohne Neuladen
- KI-Assistent: „Dateien zeigen“ erst nach Eingabe eines Repositorys aktiv, mit Hinweis
- Diktieren: Spracherkennungsmodell wählbar, wenn mehrere geladen sind (sonst das genaueste)
- KI-Assistent: Kontext „Automatisch“ nach Arbeitsspeicher (ab 48 GB 64 Tsd., ab 24 GB 32 Tsd. Token), zur Wahl bis 128 Tsd.
- KI-Assistent: Rechte in Gruppen – Lesen (ein Schalter, Hilfe immer), Zeigen, Ändern, Von wo
- KI-Assistent: Ändern (Werte eintragen, Kategorien) an – jede Änderung erst nach deinem Klick

## 3.16.29 (2026-11-21 19:46)
- Sicherheit: „Sicherung wiederherstellen“ übernimmt Update-Quelle, unerlaubte Adressen und fremde Zertifikate nicht mehr aus der Datei
- Sicherheit: eine Sicherung schaltet „Buchen ohne Rückfrage“ und „Verweis in MoneyMoney“ nur aus, nie ein
- Entwicklung: Test listet jeden Weg nach außen – Netz-Zugriffe, Hosts, gestartete Programme; Neues fällt sofort auf

## 3.16.28 (2026-11-21 19:31)
- Entwicklung: GitHub-Prüfung aufgeräumt – nur bei Push auf main, ungenutzte Auslöser und doppelte Prüfungen entfernt
- Entwicklung: Nachtlauf nur noch 1000 Zufallsläufe (Python 3.9), statt alles erneut
- Entwicklung: Mac-Prüfung lädt alle Module (auch Assistent)
- Entwicklung: Touch-ID-Test wartet auf die Anmeldeseite (schlug zufällig fehl)

## 3.16.27 (2026-11-21 19:19)
- Rechtsklick: Gruppe „KI-Assistent“ mit „Kurz erklären“ und „Im Chat fragen“ (ohne „…“)
- „Kurz erklären“: sofort, höchstens zwei kurze Sätze, in einem kleinen Kasten am Mauszeiger – nicht im Chat; „Im Chat weiterfragen“
- Bezug genauer: Stelle in der Grafik unter dem Mauszeiger, Pfad der Zeile, ganze Zeile bei schmalen Tabellen (etwa Umsätze)
- Rechtsklick: Wert, Zeile oder Spalte kopieren (als Tabelle für Excel/Numbers), auch ohne KI-Assistent
- „Grafik drucken …“ auch für Grafiken im Chat
- Behoben: Sprung zurück zu einer Cashflow-Zeile öffnet die Tabelle tief genug

## 3.16.26 (2026-11-21 18:40)
- KI-Assistent: leeres Gespräch zeigt, was offen ist (wie in der Übersicht) – „Erledigen“ stellt dem Assistenten die passende Frage, sonst „Öffnen“

## 3.16.25 (2026-11-21 18:33)
- Entwicklung: GitHub prüft bei jedem Push die Versionskette – jeder Commit hebt VERSION, kein Changelog-Abschnitt geht verloren, oben die eigene Version
- Entwicklung: zweite Sperre vor jedem Push direkt in Claude – holt main selbst, prüft jeden Commit einzeln

## 3.16.24 (2026-11-21 18:12)
- Entwicklung: Push-Sperre – eine Version auf veraltetem Stand kann fremde Versionen nicht mehr löschen

## 3.16.23 (2026-11-21 17:55)
- KI-Assistent: antwortet ab Werk kurz, direkt und inhaltsdicht – widerspricht mit Begründung, ohne Floskeln, Fachwörter kurz erklärt
- KI-Assistent: Denkaufwand mit klarer Bedeutung – Schnell: ohne Nachdenken, Ausgewogen: bis 2.000 Token je Antwort, Gründlich: ohne Grenze; in den Einstellungen mit geschätzter Zeit
- KI-Assistent: unter jeder Antwort „Token nachgedacht · Abfragen · Token/s“, dazu „Denkgrenze erreicht“
- KI-Assistent: Gründlich nicht mehr von der Antwortlänge gedeckelt; Denkgrenze auch mit älteren llama.cpp-Versionen
- KI-Assistent: Änderungsprotokoll zeigt die Zahl der eingetragenen Umsätze richtig
- Entwicklung: Rundgang in der Safari-Engine übersteht das Neuladen nach der Anmeldung (3.16.19 war auf GitHub rot)
- KI-Assistent: Rechtsklick auf Zahl, Zeile, Spaltenkopf, Grafik oder Markierung → „KI-Assistent fragen …“, Bezug vor der Frage; „Grafik drucken …“ bei allen Grafiken (kam ohne Changelog-Eintrag)
- Entwicklung: 3.16.21 und 3.16.22 wiederhergestellt – ein späterer Commit hatte sie überschrieben

## 3.16.22 (2026-11-21 17:48)
- Entwicklung: Skill „Teamleiter“ wieder entfernt – mehrere Aufgaben in einer Nachricht teilt jeder Chat selbst auf (Unteragenten)

## 3.16.21 (2026-11-21 17:43)
- KI-Assistent: nummerierte Listen zählen weiter, auch mit Leerzeilen; Text unter einem Punkt bleibt bei ihm; Liste in der Liste.
- KI-Assistent: breite Tabelle scrollt in ihrem Rahmen, ohne die Zeile darunter zu überdecken.
- KI-Assistent: Weg zur dauerhaften Mikrofon-Freigabe der App im Dock korrigiert (Systemeinstellungen → Datenschutz & Sicherheit).
- Behoben: seltene Fehlermeldung direkt nach der Anmeldung (Einstellungen noch nicht geladen).

## 3.16.20 (2026-11-21 17:33)
- Entwicklung: Lagebild für parallele Chats – zu Beginn jeder Aufgabe, was die anderen veröffentlicht haben, Überschneidungen, Tests auf GitHub
- Entwicklung: Rot auf GitHub behebt nur der Chat, der es verursacht hat (keine doppelten Korrekturen)
- Entwicklung: Tests auf GitHub in zwei Hälften nebeneinander – rund 5 statt 9 Minuten
- Entwicklung: Skill „Teamleiter“ – viele Aufgaben auf mehrere Chats verteilen

## 3.16.19 (2026-11-21 17:20)
- KI-Assistent: schlägt Kategorien für Umsätze ohne Kategorie vor (je Gegenpartei, nur bestehende Kategorien) – eingetragen erst nach deinem Klick, wie unter Kategorisieren
- KI-Assistent: nie über eine inzwischen gesetzte Kategorie; Zurücknehmen nur, was die Karte eingetragen hat (in MoneyMoney nur am Mac)
- KI-Assistent: Karte und Änderungsprotokoll nennen Teil-Ergebnisse (wartet auf den Mac, übersprungen, inzwischen geändert) und die Anzahl
- Entwicklung: Internetsuche entschieden – kostenlos, offizielle Quellen in drei Stufen

## 3.16.18 (2026-11-21 17:11)
- Entwicklung: Ziel und Entscheidungen im Fahrplan per Test gegen Verlust gesichert; Entschiedenes wird nie gelöscht

## 3.16.17 (2026-11-21 16:57)
- KI-Assistent: Einstellungen zeigen beim Sprachmodell, ob das Mikrofon dauerhaft erlaubt ist – sonst der Weg dahin (App im Dock, Safari, iPhone) und „Jetzt freigeben“.

## 3.16.16 (2026-11-21 16:46)
- Entwicklung: Test der Feldbreite beim Diktat unabhängig von der Schriftart (war auf GitHub rot).

## 3.16.15 (2026-11-21 16:16)
- Entwicklung: Ziel geschärft („dein digitaler CFO“) – Leitlinien, Entscheidungen, Offenes in Fahrplan und Regeln
- Entwicklung: Fahrplan neu geordnet – Daten erst nach Anmeldung, KI-Assistent, GbR-Entlastung, Gesellschaften, Planung
- Anmeldung: Untertitel „Dein digitaler CFO“

## 3.16.14 (2026-11-21 16:12)
- Kopfzeile: Seitentitel wird nicht mehr abgeschnitten; Bereiche rücken bei wenig Platz zur freien Seite und kürzen dann die übrigen Namen („…“), der gewählte bleibt ganz; voller Name beim Darüberfahren.
- KI-Assistent: Senden auch während des Diktats – beendet es, schreibt es und schickt die Frage ab.

## 3.16.13 (2026-11-21 15:51)
- KI-Assistent: alle Änderungen einer Antwort auf einer Karte am Ende, ein Klick führt die angehakten aus.
- KI-Assistent: Begründung je Änderung; Protokoll der Änderungen unter Einstellungen → KI-Assistent.
- KI-Assistent: Werte eintragen ab Werk an (jede Änderung erst nach deinem Klick).

## 3.16.12 (2026-11-21 15:09)
- KI-Assistent: Diktat bis zehn Minuten (vorher knapp drei); live in Stücken, am Ende einmal als Ganzes für ein sauberes Transkript.
- KI-Assistent: Stille und Rauschen erreichen das Sprachmodell nicht mehr (keine erfundenen Sätze); Pausen am Rand abgeschnitten.
- KI-Assistent: Diktat kursiv und blasser, solange es läuft; Mikrofon übernimmt, ✕ verwirft (statt Senden).
- KI-Assistent: „+“ im Fragefeld für Dateien (Text, CSV, Code); bei mehreren Zeilen Text über die ganze Breite, Knöpfe darunter.
- Behoben: Aufnahme ließ sich manchmal erst mit dem zweiten Klick beenden.

## 3.16.11 (2026-11-20 20:50)
- KI-Assistent: Diagramme im Chat aus Kontors eigenen Zahlen (Verlauf, Cashflow, Aufteilung) – Werte beim Darüberfahren, Klick zeigt die Zahl in Bilanz oder Cashflow.
- KI-Assistent: Verläufe – Unterhaltungen verschlüsselt gespeichert, wieder öffnen und fortsetzen, einzeln oder alle löschen; Einstellung „Verläufe speichern“ (Standard an), nicht in Sicherungen.
- KI-Assistent: Symbol „Neue Unterhaltung“ als Stift.
- Entwicklung: Installationsprüfung auf dem Mac zählt jetzt mit.

## 3.16.10 (2026-11-20 19:04)
- Behoben: Korrektur aus 3.16.8 (Grafiken beim Aufklappen des Assistenten in Safari) war mit 3.16.9 verloren gegangen – wieder drin.
- Entwicklung: Schutz beim Veröffentlichen, damit kein Chat die Änderungen eines anderen überschreibt.

## 3.16.9 (2026-11-20 18:53)
- KI-Assistent: Lade-Kreisel dreht beim Nachdenken durchgehend (blieb scheinbar stehen).

## 3.16.8 (2026-11-20 18:52)
- Behoben: Fehlermeldung der Safari-Engine beim Aufklappen des Assistenten (Grafiken zeichnen sich im nächsten Bild neu).

## 3.16.7 (2026-11-20 18:42)
- KI-Assistent: Diktat erscheint schon beim Sprechen im Textfeld.
- KI-Assistent: Scrollbalken im Textfeld nur, wenn es etwas zu scrollen gibt.

## 3.16.6 (2026-11-20 18:29)
- KI-Assistent: Mikrofon erscheint gleich nach dem Laden des Sprachmodells (und verschwindet beim Löschen), ohne Neuladen.

## 3.16.5 (2026-11-20 18:16)
- Assistent neben der Seite: die Seite scrollt für sich, Scrollleiste an ihrem rechten Rand statt hinter dem Assistenten; Position bleibt beim Öffnen und Schließen.

## 3.16.4 (2026-11-20 17:25)
- KI-Assistent: Download zeigt Geschwindigkeit und Restzeit.
- Unten links: „KI-Modell lädt · 42 %“ mit Ladesymbol, auf jeder Seite; Klick führt hin, Meldung wenn fertig.
- llama.cpp: auf Apple-Chips immer die passende Version, auch wenn Python übersetzt läuft.

## 3.16.3 (2026-11-20 15:42)
- Behoben: KI-Assistent – llama.cpp ließ sich nicht installieren („keine fertige Version für macos-arm64“); Kontor nimmt jetzt den neuesten Build.
- Einrichtung: „Als App im Dock“ ist Schritt 1, mit Anleitung direkt im Schritt; Kontor erkennt die App und macht dort mit der Einrichtung weiter.
- Erster Start: direkt in die Einrichtung.
- „KI-Assistent“ heißt er jetzt in Einrichtung und Einstellungen; ohne „Alpha“.

## 3.16.2 (2026-11-20 15:04)
- Einrichtung: neuer Schritt „Als App im Dock“; Einstellungen → Allgemein zeigt den Weg (Safari: Ablage → Zum Dock hinzufügen, iPhone: Zum Home-Bildschirm).
- Chrome/Edge: Knopf „Als App installieren“; als App geöffnet gilt der Schritt als erledigt.
- Installation: Hinweis auf die App im Dock.

## 3.16.1 (2026-11-20 11:49)
- Alte Buchungsmarken „#mm-…“ (vor 3.12) und „#kontor-spiegel-…“ zählen nicht mehr als Kontors Buchungen, sondern als deine eigenen.

## 3.16.0 (2026-11-20 07:32)
- Neu: Assistent (Alpha) – Sprachmodell nur auf diesem Mac, ohne Netz; als Fenster neben jeder Seite (✦ oder ⌘K) und als Menüpunkt.
- Assistent: Fragen in normaler Sprache, auch mit eingefügten Zahlen, Tabellen, Code oder abgelegten Textdateien; antwortet in Kontors Sprache; jederzeit stoppbar.
- Assistent liest: Übersicht, Bilanz, Cashflow, Vergleiche, Planung, Steuer, Immobilien, Kategorien, Auto-Buchungen, Offenes, Wertpapiere, Umsätze mit Belegen, Hilfe.
- Assistent zeigt: öffnet die passende Ansicht, filtert Umsätze, hebt Zeilen und Felder hervor.
- Assistent trägt ein: Kontostände, Planwerte, Annahmen, Ereignisse – nur nach Klick auf die Karte, mit „Zurücknehmen“.
- Diktieren: Mikrofon im Fragefeld, eigenes Sprachmodell auf dem Mac, ohne Internet.
- Einstellungen → Assistent: llama.cpp und Modelle laden, aktualisieren, wechseln, löschen; Empfehlung passend zum Arbeitsspeicher; Rechte einzeln; Denkaufwand, Kontext, Leerlauf, Abschirmung.
- Zahlen eingeben: Monatsstände und Planwerte in der Schreibweise der Sprache (1.234,56 bzw. 1,234.56); behoben: falsche Werte bei Tausenderzeichen.
- Buchungsregeln: Konto in anderer Währung → Wert der Beteiligung „unbekannt“ statt 1:1 in Euro; Zinsen kaufmännisch gerundet.
- Sicherheit: Verwendungszweck einer fremden Zahlung macht kein Bankkonto buchbar; Fehlversuche beim Passwort zählen überall; Zugang und „Verweis in MoneyMoney“ nur am Mac einstellbar; Pakete ohne Buchungsschalter.
- Behoben: Zugang – „nur ansehen“ und „Offline-Kopie“ ließen sich nicht umschalten; „Erneut versuchen“ nach einem Ladefehler ohne Wirkung.
- Installation: Standardordner `~/Applications/Kontor`; README kürzer, Einzelheiten in der Hilfe.
- Aufgeräumt: Altlasten und ungenutzter Code entfernt; Hilfe und Bilder auf dem Stand von heute.

## 3.15.23 (2026-11-20 05:30)
- Entwicklung: Rundgang misst erst nach dem Einblenden der Seite (vorher falsche Kontrast-Meldungen auf langsamen Rechnern).

## 3.15.22 (2026-11-20 05:18)
- Entwicklung: Rundgang liest gemischte Farben richtig (keine falschen Kontrast-Meldungen in der Safari-Engine).

## 3.15.21 (2026-11-20 05:07)
- Entwicklung: Rundgang über alle Seiten (hell/dunkel, Mac/iPhone, de/en), Code-Checks, Prüfung auf dem Mac; verständliche Namen der Prüfungen.

## 3.15.20 (2026-11-20 04:28)
- Entwicklung: Zwischenspeicher bleibt klein; GitHub-Bausteine aktuell.

## 3.15.19 (2026-11-20 04:13)
- Entwicklung: Prüfung bei GitHub behält die geladenen Systempakete (schneller, unabhängig vom langsamen Paketserver); scheitert die Einrichtung, bricht sie ab statt ohne Werkzeuge weiterzulaufen.

## 3.15.18 (2026-11-20 03:46)
- Entwicklung: Prüfung bei GitHub wieder schnell und ohne Hänger (feste Systemversion, Paketsperre abwarten).

## 3.15.17 (2026-11-20 03:31)
- Entwicklung: Zeitgrenzen gegen hängende Prüfungen bei GitHub.

## 3.15.16 (2026-11-20 03:22)
- Entwicklung: ein Commit je Version, beginnt mit der Versionsnummer, mit Claude-Version und Link zum Chat.

## 3.15.15 (2026-11-20 02:53)
- Installation: lädt nur noch den aktuellen Stand (5 statt 240 MB), deutlich schneller.
- Installation: blockiert macOS den Hintergrunddienst, öffnet sie die passende Systemeinstellung und wartet, bis er läuft.

## 3.15.14 (2026-11-19 21:26)
- Kontenspiegel: Gegenbuchungen von Hand gelten nur am selben Tag als Paar; mit Tagen Abstand „prüfen“ mit Gegenstück, anfangs abgewählt, nie automatisch.
- Auto-Buchungen: Verwerfen einer Hälfte verwirft beide Seiten auf einmal.

## 3.15.13 (2026-11-19 20:22)
- Kontenspiegel: Gegenbuchungen von Hand mit bis zu 7 Tagen Abstand gelten als gespiegelt (in den Rechenwegen genannt); weiter auseinander oder doppelt zu Kontors Spiegelbuchung: Vorschlag mit „prüfen“, nie automatisch.
- Auto-Buchungen: Bereich unter jedem Konto.
- Ausgaben je Monat: höchster Wert in kräftigster Farbe, Ausreißer gerahmt mit ▲/▲▲/▲▲▲, neu mit ✦; Vorjahresskala bis 100 %.
- Einrichtung: Weg zum nächsten Schritt unter der Verbindung statt oben.

## 3.15.12 (2026-11-19 19:36)
- Bilanz in Jahren: keine grau hinterlegten Jahresspalten mehr.
- Cashflow-Tabelle: Zeilenlinien neben den Namen ohne Versatz (Safari).
- Auto-Buchungen: „alle abwählen“ wählt wirklich alles ab.

## 3.15.11 (2026-11-19 18:43)
- Übersicht: „Vermögensaufbau“ je Baustein (Beteiligungen, Immobilien, Liquidität, Schulden) mit Geldfluss und Wertänderung statt der Kennzahlen.
- Vermögensstruktur: Vorjahresvergleich nur mit bekanntem Stand; kein „neu“, ±0 % nur ohne Veränderung.

## 3.15.10 (2026-11-19 18:20)
- Übersicht: Hover-Infos in allen Grafiken (Monat, Kachel, Schritt der Brücke).
- Updates ersetzen die Dateien direkt, ohne Sicherungsordner; nicht mehr benötigte Dateien werden entfernt.

## 3.15.9 (2026-11-19 17:09)
- Seitenfenster steht immer neben der Seite (die Seite rückt zur Seite); nur bei schmalem Fenster liegt es darüber.

## 3.15.8 (2026-11-19 16:44)
- Übersicht: neue Karte „Kennzahlen“ (Sparquote, Ausgaben je Monat, Reserve, finanzielle Freiheit, Schulden, Eigenkapitalquote); Monatlicher Cashflow nur noch ein Drittel breit.
- Vermögensstruktur: Vermögen | Finanziert durch, je Kachel Betrag und Veränderung zum Vorjahr; Summe „Vermögen“ statt „Bilanzsumme“.
- Nettovermögen: 12 abgeschlossene Monate; Vermögensbrücke ohne laufenden Monat.
- Drucken immer hell.
- Seitenfenster schmaler, schließt per Klick auf den Hintergrund (bei ungespeicherten Eingaben mit Rückfrage).
- „… Buchungen offen“ unter Buchungsregeln anklickbar: Liste im Seitenfenster, Weg zur Freigabe.
- Cashflow-Positionen: Anzahl und Summe anklickbar; „Was Kontor von deinen Kategorien braucht“ mit vorhanden/fehlt, passt sich sofort an.
- Zielkonto: „nicht nötig“, „automatisch: …“ oder „fehlt – bitte wählen“; je Empfänger nur „Bitte wählen“ auszufüllen.
- Kontenspiegel: Warnung bei doppelter Regel, Fehler wenn ein Bankkonto in mehreren Kontenspiegeln steht.
- Cashflow-Tabelle: Auf- und Zuklappen ohne Sprung der Seite.

## 3.15.7 (2026-11-19 15:17)
- Zahlungen zwischen Bereichen mit Gegenbuchung: Zeile „Bereich: Konto“, eingeordnet nach Art des Kontos (Beteiligung, gewährtes Darlehen, Schuld); Darlehen an dich getrennt nach Aufnahme und Tilgung.
- Seitenfenster mit Umsätzen: Tabelle ohne seitliches Scrollen; angeklickte Zahl markiert; würde das Fenster sie verdecken, rückt die Seite zur Seite.
- Neue Szenario-Tests: Einlagen, Unternehmenskauf mit Verkäuferdarlehen, Bank- und Privatdarlehen, Darlehen zwischen Gesellschaften, Auslagen, fällige Rechnungen, Ausschüttung – je Tag, Monats- und Jahreswechsel, zufällig gemischt.

## 3.15.6 (2026-11-19 14:17)
- Einlagen mit Gegenbuchung im Kapitalkonto auch über das Monatsende verbunden (als „Geld unterwegs“).
- Geld unterwegs im laufenden Monat nicht mehr doppelt, wenn eine Buchung nach heute datiert ist.

## 3.15.5 (2026-11-19 13:39)
- MoneyMoney-Sync: Synchronisierung oben, dann Abgleich; Verbindung eingeklappt am Ende, sobald sie steht.
- Einrichtung: „Weiter“ und „Zurück zur Einrichtung“ als schmale Zeile oben (MoneyMoney-Sync, Kontostände).
- Sichern & Zurücksetzen: Erklärungen zu Sicherung und Einstellungspaket im Hilfe-Symbol statt oben; Belegordner anklickbar (zur Einstellung); Zeile Time Machine bündig.
- Belege: Unterordner-Muster nur mit bekannten Platzhaltern in geschweiften Klammern speicherbar.

## 3.15.4 (2026-11-19 13:25)
- Einlagen mit Gegenbuchung im Kapitalkonto: bis 7 Tage Abstand (Wochenende, Feiertage, Kontenspiegel); nächste Buchung zuerst, wöchentliche Einlagen bleiben verbunden.
- Einstellungen → Allgemein: keine Rückfrage mehr wegen ungespeicherter Änderungen.
- Hilfe-Symbol am Seitentitel nennt den Reiter („Belege: …“).

## 3.15.3 (2026-11-19 12:30)
- Cashflow: Einlagen/Entnahmen zwischen deinen Bereichen, die du im eigenen Kapitalkonto gegenbuchst, gehen in dieses Konto – keine Änderung des Nettovermögens, keine Wertänderung mehr (beide Seiten, auch mit Beteiligungsregel).

## 3.15.2 (2026-11-19 04:27)
- „Zuordnen“ heißt jetzt „Kategorisieren“; anfangs nur private Bereiche ausgewählt.
- Einrichtung: Buchungsregeln vor Cashflow-Positionen, Kategorisieren am Ende; „Weiter“ führt zum nächsten Schritt.
- Cashflow-Positionen: Empfohlene Kategorien für MoneyMoney (Checkliste); „Zielkonto“ statt „Angelegt auf“, Erklärung der Reihenfolge; Tooltip zu „Umbuchung“ und „Nicht berücksichtigen“; feste Spaltenköpfe.
- Übersicht in drei Spalten, kleinere Grafiken; Vermögensstruktur als Bilanz-Kacheln mit Eigenkapital und Schulden; „Offen“ rechts unten.
- Verlauf aus Umsätzen: Stand 0 ab Kontoeröffnung laut MoneyMoney, auch vor dem ersten Umsatz.
- Buchungsregeln: Konto in zwei Schritten (Bereich, dann Konto); „Manuelle Darlehen“; Buchungstext „Anteilswertanpassung“.
- Monatlicher Cashflow: Ergebnis-Strich nur innerhalb der Achse.
- Umsätze & Belege: „Kategoriefilter hinzufügen“.
- Hilfe-Symbol am Seitentitel mittig und mit etwas Abstand.
- Hilfe-Texte angepasst.

## 3.15.1 (2026-11-18 22:18)
- Zuordnen (vorher „Kategorien“): kein Schalter fürs Eintragen; Reiter „Eingetragen“ mit Rückgängig; Link zu Cashflow-Positionen.
- Kommandozeile ohne Datenzugriff; Passwort und Deinstallieren nur mit Kontor-Passwort oder Touch ID.
- Drucken (⌘P) mit Grafiken und Kopfzeile; einzelne Grafik per Rechtsklick.
- Übersicht: offene Punkte als Liste unter den Grafiken.
- Hilfe-Symbol neben jedem Seitentitel; Symbole an Grafiken und Tabellen führen zum passenden Absatz.
- Bilanz: Grafik über der Tabelle; Doppelklick/Halten auf Wert klappt auf; Verlauf auch in erster Spalte.
- Ausgaben je Monat: Umschalter Beträge / ± Vorjahr.
- Brücken: Prozent immer mit %, Farbe nur bei Einnahmen/Ausgaben, mehr Ausgaben = + und rot (war vertauscht).
- Cashflow-Grafiken: Tooltips nur Betrag fett; Zeitraumlänge in Ring und Gesamtcashflow; Summe ohne Hover; Ergebnis-Striche dezent gestrichelt; Wertänderungen gedeckter.
- Monatlicher Cashflow: Umschichtungen und Wertänderungen unten wieder sichtbar (Fehler aus 3.15.0).
- Einstellungen: Sprache gilt sofort; Sync-Knöpfe nebeneinander mit Tooltip.
- Protokoll nicht mehr im Menü (Sichern & Zurücksetzen, Synchronisierung, Hilfe).
- Umsätze & Belege: alle Filter immer sichtbar.
- Hilfe und Bilder aktualisiert.

## 3.15.0 (2026-11-18 20:28)
- Neu installieren: Einstellungen und Daten älterer Versionen werden nicht übernommen.
- Übersicht neu: vier Grafiken auf einer Seite, Klick führt in Bilanz oder Cashflow; ohne Tabellen, ohne „Alpha“.
- Datenschlüssel erneuerbar (Einstellungen → Sichern & Zurücksetzen); nie ein neuer Schlüssel über vorhandene Daten.
- Installation in einer Zeile (`install.sh`); `Uninstall.command` deinstalliert wie die App.
- Position „Eigenkapital“ entfällt.
- Interne Namen englisch (Einstellungen, Daten, API, Sicherung, Paket).
- Altlasten und unbenutzte Dateien entfernt.
- Hilfe, README und Bilder aktualisiert.

## 3.14.9 (2026-11-18 17:26)
- Einstellungen → Sicherung: Kontor deinstallieren (Dienst, Kontors Dateien, Protokoll, Schlüssel, Programmordner; Belege, verknüpfte Dokumente, fremde Dateien und MoneyMoney bleiben); Programmordner wird angezeigt.
- Installation: wartet auf Apples Kommandozeilen-Werkzeuge und läuft dann von selbst weiter.

## 3.14.8 (2026-11-18 16:36)
- Deinstallation nennt, wie man die macOS-Freigaben (Automation) entfernt.

## 3.14.7 (2026-11-18 16:24)
- Einrichtung: „Einrichtung abgeschlossen“ vor „Einrichtung prüfen“; ein Hilfe-Tooltip erklärt beide Knöpfe.

## 3.14.6 (2026-11-18 16:03)
- Cashflow-Positionen: Oberkategorie ohne eigene Wahl zeigt „Je Unterkategorie (automatisch)“; eine Wahl dort gilt für die Unterkategorien.

## 3.14.5 (2026-11-18 15:59)
- Einrichtung: bleibt in der Seitenleiste und führt Schritt für Schritt, bis du „Einrichtung abgeschlossen“ drückst; danach wieder einblendbar.

## 3.14.4 (2026-11-18 15:53)
- Konten: Tooltip zur Position erklärt die Wahl (nach Verfügbarkeit, mit Beispielen) statt Kontors Erkennungsreihenfolge.
- Position „Kapitalkonten (Eigenkapital)“ heißt „Eigenkapital“ und steht nur noch zur Auswahl, wo ein Konto sie schon nutzt.

## 3.14.3 (2026-11-18 15:22)
- Cashflow und Planung: Zeilenlinien der festen Namensspalte genau auf Höhe der Zahlen (kein Pixelversatz).

## 3.14.2 (2026-11-18 15:14)
- Brücken: Veränderungen ab 1000 % kurz als Tausender („+2T“).
- Cashflow-Tabelle: Doppelklick oder langes Halten auf eine Zahl klappt die Zeile auf bzw. zu.
- Cashflow-Tabelle: startet mit der Vergangenheit – letzter abgeschlossener und laufender Monat, eine Planspalte erst ab acht Spalten.
- Monatlicher Cashflow: Ergebnis je Monat als kurzer Strich (Nettovermögen deutlich, Bankguthaben dezent); unteres Diagramm etwas höher, ohne Legende; Höhen abgeschnittener Balken darüber statt auf dem Balken.
- Dunkelmodus: Wertänderungen blau statt graublau, Bankguthaben heller – klar unterscheidbar.
- Ausgaben je Monat: im Tooltip Summe rechtsbündig, Vorjahr und Veränderung nebeneinander.
- Gesamtcashflow: Tooltip neben der Grafik auf Höhe des Zeigers (immer sichtbar); neben den Bändern normaler Mauszeiger.
- Vorjahresvergleich: Umschalten hält die Position auch am Seitenende.

## 3.14.1 (2026-11-18 14:22)
- Seitenfenster: zweiter Klick auf dieselbe Zahl schließt es.
- „Abgleich mit der Bilanz“: Klick zeigt Gründe und die Buchungen dahinter.
- „Ausgaben je Monat“: Klick auf einen Namen (auch „Ausgaben gesamt“) zeigt die Umsätze des Zeitraums; Tooltip mit Vorjahr und Linie vor den Unterkategorien.
- Sprung in die Bilanz: Markierung länger, Grafiken richten sich auf den Monat aus.
- Bilanz: Tabelle standardmäßig vor der großen Grafik.
- Vermögensbrücke anfangs zugeklappt; Brücken: weniger Abstand unter dem Titel, Pfeile auf dem iPhone in der Titelzeile.
- Brücken: Tooltip auch auf dem Betrag, rechts neben der Grafik.
- Gesamtcashflow: Titel ohne Zusatz (steht im Tooltip); Tooltip mit genauem Betrag, Anteil, Vorperiode, Veränderung und Unterpositionen (über der Grafik); Klick neben die Bänder klappt alles auf bzw. zu; Anteile dezenter.
- Monatlicher Cashflow: erster und letzter Monat fett; im Tooltip „=“ vor den Ergebniszeilen; Monat unter dem Zeiger in der Tabelle leicht markiert.
- Vorjahresvergleich: Umschalten Ausgaben/Einnahmen hält die Position.
- Immobilien: Kennzahlen und Mieterhöhungen mit Dezimalkomma, „Mon.“ übersetzt.
- Testdaten: erfundene Immobilienzahlen; Hilfe-Bilder erneuert.

## 3.14.0 (2026-11-18 06:40)
- Gesamtprüfung: Tests mit 1000 Zufallsläufen, alle Seiten hell/dunkel auf Mac und iPhone, Hilfe, Tooltips, README und Hilfe-Bilder aktualisiert.
- Cashflow-Tabelle: jede Zahl zeigt die Umsätze dahinter (auch zusammengefasste Zeilen wie „Unklar“); auf- und zuklappen nur über den Namen.
- Sicherheit: Update-Quelle nur am Mac änderbar und angezeigt, wenn sie abweicht; Protokoll ohne Fehlertexte abgelehnter Anfragen; Parameter geprüft.
- iPhone: Hilfe nicht mehr breiter als der Bildschirm; Auto-Buchungen kompakter.
- Umsätze & Belege: Knöpfe in einer Zeile.
- Testdaten neutralisiert.

## 3.13.34 (2026-11-18 05:39)
- Umsätze hinter einer Zahl immer im Seitenfenster, auch bei „Unklar“.
- Update installieren ohne Rückfrage.
- Gesamtcashflow: Bänder behalten ihre Farbe und blassen erst kurz vor der Mitte aus.
- Vermögensbrücke: Zinsen, Einlagen/Entnahmen ohne Farbpunkt; Ring: Kategorien in eigener Farbe (Indigo-Stufen).
- Monatlicher Cashflow: Skalen senkrecht zoombar (ziehen/scrollen, Klick setzt zurück), gekappte Balken beschriftet.
- Sprung zur Bilanz: Tabelle scrollt zum Monat (auch frühere Jahre, Planmonate).
- Unklar: Lastschrift auf eine umgezogene Karte (alte IBAN) wird gepaart.

## 3.13.33 (2026-11-18 04:39)
- Vermögensbrücke: „Überschuss“ und „Zinsen“ statt „Gespart“.
- Monatlicher Cashflow: ohne Vorjahresbalken; Tooltip ohne Zeilen mit 0,00.
- Tabelle: „Veränderung Bankguthaben“ ohne Farbpunkt.
- Gesamtcashflow: Farbe in der Mitte je Höhe aus links und rechts; keine Haarlinien; Abblenden nur über einem Band; Name und Betrag in einer Zeile (iPhone zweizeilig).
- Klick auf eine Kategorie-Zahl: Umsätze im Seitenfenster statt Reiterwechsel („Unklar“ weiter auf der Seite).
- Unklar: Umbuchungen mit Kategorie auf beiden Seiten bis 7 Tage gepaart (PayPal); Rückbuchung auf demselben Konto im selben Monat zählt nicht.

## 3.13.32 (2026-11-18 04:08)
- Standard-Reihenfolge: Liquiditätsbrücke und Monatlicher Cashflow, darunter Vermögensbrücke und Gesamtcashflow.
- Monatlicher Cashflow: unten wie die Tabelle (Bankguthaben, Umschichtungen, Wertänderungen); Vorzeichen; erster/letzter Monat immer beschriftet.
- Ruhigere Farben für Umschichtungen, Wertänderungen, Einlagen; dieselben Punkte in der Tabelle.
- Gesamtcashflow: schmalere Mitte mit Zeitraum über der Summe; ohne Trennlinie; wächst mit dem Nachbarn; Klick auf die Summe klappt alles auf/zu.
- Tabelle: Abgleich vor „am Ende“; Einnahmen/Ausgaben, Umschichtungen, Wertänderungen dünner; Hand-Cursor bei „Unklar“.
- Fix: Tooltip am Anfangs-/Endbestand („undefined“); Sprung zur Bilanz bei früheren Jahren.
- „Ansicht zurücksetzen“ im Cashflow sauber ausgerichtet.
- Umsätze & Belege: nur noch ein Excel-Knopf; exportiert die gefilterten Umsätze (alle Treffer).
- Monatlicher Cashflow: gekappter Vorjahresbalken markiert; Zeitraum per Ziehen/Scrollen über der x-Achse verschieben.
- Zeitraum-Knöpfe (12 Monate, Jahre) scrollen die Tabelle zum letzten Monat.

## 3.13.31 (2026-11-18 03:04)
- Einstellungen → Zugang: Seite sofort da, der Tailscale-Teil lädt nach.
- Gesamtcashflow: Höhe nach dem Diagramm daneben (wuchs bei jedem Neuzeichnen).

## 3.13.30 (2026-11-18 02:47)
- Tabelle: Bewegungen mit Vorzeichen (+); startet auf Hauptebenen mit Einnahmen/Ausgaben; Nettovermögen klappt zu Anfang/Ende auf.
- Tabelle: Umschichtungen bis Nettovermögen etwas dünner statt abgesetzt; „✱“ statt „!“; Hand-Cursor überall; Aufklappen scrollt nicht mehr.
- Tabelle: Klick auf „Unklar“-Zahlen zeigt die Buchungen dahinter.
- Diagramme: Brücken nebeneinander, darunter Monatlicher Cashflow und Gesamtcashflow; „Ansicht zurücksetzen“; Pfeile neben dem Titel.
- Brücken schraffiert bei laufendem Monat/Plan; Gesamtcashflow mit Zeitraum, füllt die Höhe, Beträge mit einer Nachkommastelle.
- Heatmap: Ausreißer dezenter gerahmt, Betrag ohne Nachkommastelle, ▲ wenn zu schmal; Tooltip ohne Zusatztext.
- Vorjahresvergleich: nur Stücke nahe 12/6 Uhr wechseln nach rechts.
- Zeitraum: Klick auf eine Monatsüberschrift der Tabelle = 12 Monate bis dorthin; zwei Finger seitwärts über dem Monatlichen Cashflow verschieben ihn.
- Tooltip Veränderung Bankguthaben: „= Netto-Cashflow“; Bilanz: „Ansicht zurücksetzen“.

## 3.13.29 (2026-11-18 01:41)
- Protokoll: eine Datei (max. 2 MB), alte nummerierte gelöscht; keine Zeile je Seitenabruf oder 30-s-Prüfung; „gesperrt“ nur einmal.
- Protokoll-Seite: Filter Alles / Hinweise / Warnungen & Fehler; Warnungen gelb, Fehler rot.
- Diagramme mit ↑ ↓ verschiebbar (beim Darüberfahren); Vorjahresvergleich standardmäßig unten.
- Sankey und Vermögensbrücke je halb; Sankey mit fester Namensbreite, Beträge kurz.
- Vorjahresvergleich: Namen links/rechts ausgeglichen; Schalter im Ring; Trennlinie mittig.
- Heatmap: Ausreißer mit Rahmen und Betrag.
- Tabelle: Klick auf eine Zahl klappt die Zeile; bei Kategorien öffnet er die Umsätze.
- Bilanz, Geldtransit: Klick auf einen Monat zeigt die Umbuchungen über dessen Ende.

## 3.13.28 (2026-11-18 01:12)
- Zeitraum: Monatskalender statt Liste; auch laufender Monat und Plan (schraffiert); Voreinstellungen rechts.
- Diagramme neu angeordnet; Vorjahresvergleich und Ausgaben je Monat in einer Karte.
- Anfangs-/Endbestand und Bankguthaben-Zeilen: Klick springt in die Bilanz.
- Tabelle: „!“ statt Haken bei Abweichungen; laufender Monat blass wie Plan; Tooltips CFO/CFI/CFF klarer.

## 3.13.27 (2026-11-18 00:38)
- Neu: Vermögensbrücke.
- Tabelle: Zeile „Umschichtungen“ (Bankguthaben → Nettovermögen geht auf); öffnet auf dem letzten abgeschlossenen Monat; Monatsansicht ab Vorjahr.
- Liquiditätsbrücke: Achse oben, keine Textmarkierung beim Zoomen, feste Namensbreite.
- Vorjahresvergleich: Anteile im Ring, größere Schrift; Monatlicher Cashflow ohne Legende.
- Heatmap: Gesamtzeile klickbar; Sankey: Gruppen per Klick schließen.

## 3.13.26 (2026-11-17 23:45)
- **Liquiditätsbrücke:** dezente Achse mit Beträgen; einen Bereich mit der Maus aufziehen vergrößert ihn (längere Balken am Rand gekappt und markiert), „Ganze Brücke“ zeigt wieder alles. Ein Tooltip nur noch an der Veränderung: Betrag, Vorjahr, Veränderung und die Teile. Klammern je Ebene feiner: Tätigkeiten farbig, darunter grau, noch tiefer dünner.
- **Mittelherkunft & -verwendung** (statt „Geldfluss“), ein Sankey-Diagramm: Die Farben der Bänder gehen in der Mitte ineinander über statt eines grauen Balkens; breite Bänder tragen ihren Anteil; Ströme unter 3 % stehen zusammen unter „Übrige“; ein Klick auf einen Namen mit ▸ öffnet seine Teile. Fährst du über ein Band, treten die anderen zurück; die Summe steht dezent über der Mitte.

## 3.13.25 (2026-11-17 23:27)
- **Cashflow-Tabelle kompakter:** „Veränderung Bankguthaben“ klappt zu Anfangs- und Endbestand auf; der Abgleich mit der Bilanz steht als kleines ✓ an der Zahl, eine eigene Zeile nur bei Abweichung. Ab der Ebene „Positionen“ der **Free Cashflow** (CFO + CFI).
- **Heatmap:** Riesenbeträge in einzelnen Monaten färben nicht mehr alles andere blass – sie bekommen die dunkelsten Töne und eine Markierung. Neu: eine Zeile mit allen Ausgaben (bzw. Einnahmen) zusammen, auf eigener Skala.
- **Umsätze & Belege – weitere Filter:** Zeitraum von–bis und Kategorien von Hand setzen, entfernen und ergänzen; nach einem Klick aus der Heatmap sind sie schon gesetzt.
- **Zeitraum der Diagramme:** ‹ und › verschieben ihn um einen Monat; ein Klick auf einen Monat springt nicht mehr. „Monatlicher Cashflow“ heißt jetzt so.
- **Liquiditätsbrücke ohne Tooltip** – Betrag und Veränderung stehen rechts, die Teile öffnet ein Klick.
- **Kategorie „Einkommen“** wird als Arbeitseinkommen erkannt. Cashflow-Positionen markieren Kategorien mit Zahlungen zwischen deinen Bereichen, die erst mit deiner Zuordnung als Einnahme oder Ausgabe zählen („zwischen Bereichen“).
- **Monatlicher Cashflow:** mindestens vier Achsenstufen, unten Mitte und Rand beschriftet, „Veränderung Nettovermögen“ als eigener Titel; im Tooltip tragen Summen keine Farbe mehr.
- Die halb breiten Diagramme bleiben nebeneinander, bis das Fenster deutlich schmaler ist.

## 3.13.24 (2026-11-17 22:44)
- **Liquiditätsbrücke aufklappbar:** Überschuss (CFO), Investitionen (CFI) und Finanzierung (CFF) tragen ihre Farbe und spannen eine Klammer über ihre Teile – sie sind kein eigener Schritt, sondern deren Summe. Ein Klick auf eine Zeile mit ▸ teilt sie weiter auf (Positionen, Kategorien), ▾ fasst sie wieder zusammen.
- „Zu- und Abflüsse je Monat“ heißt jetzt **Monatlicher Cashflow nach Tätigkeit**.
- Auf dem iPhone steht die Legende unter „Veränderung Nettovermögen“ in eigener Zeile.

## 3.13.23 (2026-11-17 22:30)
- **Zu- und Abflüsse je Monat:** unten jetzt die Veränderung des Nettovermögens – gespart und Wertänderung gestapelt, gestrichelt derselbe Monat ein Jahr davor. Ein Klick auf einen Monat wählt die zwölf Monate bis zu ihm.
- **Umsätze aus den Diagrammen:** Ein Klick auf ein Feld der Heatmap oder auf eine Kategorie im offenen Ring zeigt die Umsätze dazu; der Filter steht oben und lässt sich mit einem Klick aufheben.
- **Vorjahresvergleich der Ausgaben** (statt „gegenüber Vorperiode“) – gemeint sind immer dieselben Monate ein Jahr davor.
- Ein Klick markiert nur noch, was etwas bewirkt; Beschriftungen im Ring reagieren auf ihrer ganzen Fläche.
- Cashflow-Tabelle: Einnahmen grün und Ausgaben rot markiert wie in den Diagrammen.
- MoneyMoney-Sync ohne Kontenliste – nur Konten, die zurückliegen, mit der Zahl der Tage; den letzten Abruf je Konto zeigt der Tooltip unter Konten & Regeln → Konten. Die Hilfe erklärt, wozu Kontor online und offline unterscheidet.
- Weniger Text: Touch ID und Offline-Ansicht ohne Erklärungen neben dem Schalter, am Mac keine Zeile zur Offline-Ansicht; schmale Auswahlfelder unter Einstellungen.
- Die automatischen Tests bei GitHub laufen wieder durch.

## 3.13.22 (2026-11-17 21:52)
- **Einstellungen → MoneyMoney-Sync** (statt „MoneyMoney & Abgleich“) zeigt nur noch den Stand des Abgleichs: Verbindung, Zeitplan, Abruf je Online-Konto.
- **Online oder offline** stellst du jetzt je Konto unter Konten & Regeln → Konten ein (Spalte „Art“, gilt sofort; der Grund der Erkennung steht im Tooltip).
- **Kontostände** (Konten & Regeln) bündeln alles zum Verlauf: Übernahme aus MoneyMoney, Wertverlauf der Depots mit Hinweis auf fehlende Monate und den Import aus einer Datei.
- **Liquiditätsbrücke:** Zuflüsse grün, Abflüsse rot, Anfangs- und Endbestand neutral.
- **Vollständig lesen** alle 30 statt 7 Tage – Kontor liest ohnehin sofort alles, wenn ein Kontostand nicht passt, sich der Kategorienbaum ändert oder neuere Umsätze umkategorisiert wurden. Wer den alten Standard hatte, bekommt einmalig den neuen.
- README und NOTICE ohne Altlasten (frühere Lizenz, Herstellername).

## 3.13.21 (2026-11-17 21:23)
- **Automatische Sperre wirkt auch bei offener Seite:** Nur echte Bedienung (Tippen, Klicken, Scrollen, Ablegen) hält die Anmeldung offen, die Statusabfrage im Hintergrund nicht mehr. Sitzungen auf anderen Geräten und die Grenze von 12 Stunden bleiben wie bisher.
- **Schlüsselbund:** Antwortet er nicht oder verweigert er den Zugriff, legt Kontor keinen neuen Schlüssel an und ersetzt keinen, sondern startet nicht; eine vorhandene Schlüsseldatei, die die Daten öffnet, wird weiter genutzt. Ein neuer Schlüssel nur, wenn es wirklich keinen Eintrag gibt.
- **Belegordner:** Verweise darin auf Dateien außerhalb werden weder angeboten noch verknüpft, angezeigt oder exportiert; Löschen trifft nie etwas außerhalb des Ordners. Ein Beleg- oder Unterordner, der selbst z. B. nach iCloud Drive zeigt, funktioniert weiter. Gesperrte Orte (Library, Datenordner) lassen sich auch mit anderer Schreibweise nicht verknüpfen.
- **Lizenz:** Apache 2.0 statt CC0; Urheber und Unabhängigkeit von MoneyMoney stehen in NOTICE.

## 3.13.20 (2026-11-17 20:45)
- **Menü neu geordnet:** „Konten & Regeln“ bündelt alles, was deine Zahlen bestimmt (Konten, Bereiche, Kontostände, Cashflow-Positionen, Buchungsregeln, Steuer). „Einstellungen“ zeigt, wie Kontor arbeitet (Allgemein, MoneyMoney & Abgleich mit der bisherigen Synchronisierung, Zugang, Belege, Updates, Sichern). Alte Lesezeichen führen an die neue Stelle.
- **Einrichtung als geführter Weg** durch diese Seiten; sie verschwindet aus dem Menü, sobald die nötigen Schritte erledigt sind („Einrichtung prüfen“ oben rechts unter Konten & Regeln). Historische Kontostände sind optional.
- **Auto-Buchen** nur noch bei den Buchungsregeln.
- **Geldfluss** statt der Liste „Mittelherkunft und -verwendung“: Herkunft links, Verwendung rechts, jedes Band so breit wie sein Betrag.
- „Überschuss kumuliert“ entfernt; Liquiditätsbrücke und Zu- und Abflüsse je halb breit nebeneinander.
- Heatmap: „(ohne Kategorie)“ immer unten. Große Veränderungen abgekürzt (+1,2T %, +10T %).
- Ungespeicherte Eingaben bleiben erhalten, wenn ein Knopf die Seite neu zeichnet; MoneyMoney wird nur noch abgefragt, solange die Verbindung fehlt.

## 3.13.19 (2026-11-17 19:43)
- **Zeitraum der Diagramme:** 12 Monate (Standard), ein Jahr oder Von–Bis nach Wahl, gut sichtbar neben der Auswahl; „Alle“ entfällt. Alle Diagramme enden am letzten abgeschlossenen Monat und folgen dem Zeitraum; Vorperiode sind dieselben Monate ein Jahr davor.
- **Liquiditätsbrücke** (statt „Vom Bankguthaben …“): Anfangsbestand, je Tätigkeit Summe und Teile, Endbestand, Veränderung zur Vorperiode; Details beim Darüberfahren.
- **Zu- und Abflüsse je Monat:** Einnahmen, Ausgaben, Investitionen und Finanzierung gestapelt, die Veränderung des Bankguthabens auf eigener Skala darunter; einzelne Riesenmonate gekappt und beschriftet.
- **Ausgaben gegenüber Vorperiode:** Ring umschaltbar auf Einnahmen; Mitte mit beiden Zeiträumen beim Darüberfahren; ein Klick hält eine Position offen und beschriftet ihre Kategorien. „±0 %“ nur bei gleichem Betrag, „Übrige“ nur mit vollständigem Vergleich.
- **Heatmap** neben dem Ring, schaltet mit ihm um: eine Skala für alle Felder, Ø je Monat rechts, im Tooltip die Kategorien des Monats.
- **Überschuss kumuliert** über den Zeitraum gegen die Vorperiode.
- Entfernt: Balken nach Position, Sparquote, Reichweite, Rollierend 12 Monate.
- **Kategorienpfade mit „›“:** Ein „/“ im Namen (z. B. „Strom/Gas“) ist keine eigene Ebene mehr; Einstellungen und wartende Zuordnungen ziehen einmalig mit.
- **Web-App im Dock:** Wischen mit zwei Fingern blättert nicht mehr zurück.

## 3.13.18 (2026-11-17 18:36)
- **Neue Diagramme im Cashflow zur Auswahl:** Zusammensetzung der Ausgaben (Ring mit Beschriftung rundherum, beim Darüberfahren die Kategorien), Einnahmen nach Position, Rollierend 12 Monate, Sparquote, Ausgaben je Monat (Jahreszahlungen und Ausreißer auf einen Blick), Reichweite des Bankguthabens und Überschuss im Jahresverlauf.
- **Abkürzungen:** CFO, CFI und CFF klein neben Überschuss, Investitionen und Finanzierung.
- **Farben:** die drei Cashflows in Cyan, Gelb und Magenta; Unterkategorien in eigenen Farben.
- **Bilanz:** Ein ruhendes Konto erscheint, wo es in den gezeigten Monaten noch ein Guthaben hatte; eine Position ohne Betrag in den gezeigten Monaten verschwindet ganz.
- „Geld in Transit“ statt „Geld unterwegs“.

## 3.13.17 (2026-11-17 18:07)
- **Anfangssaldo eines neuen Kontos** (z. B. eine neue Karte, die in MoneyMoney mit der Restschuld der alten startet): Zeigt ein anderes Bankkonto im selben Monat den Gegenbetrag, zählt er als Umbuchung; sonst steht er als „Anfangssaldo“ unter Wertänderungen – nicht mehr als „Kontostand unbekannt“.
- **„Überschuss“** statt „Operativer Cashflow“ (Einnahmen minus Ausgaben).
- **Farben:** Überschuss blau, Investitionen gelb-orange, Finanzierung lila.
- **Cashflow öffnet auf „Überblick“**, die Planung auf „Positionen“.
- **Ausgaben nach Position:** Betrag und Veränderung zur Vorperiode stehen direkt da; beim Darüberfahren die Aufteilung in eigenen Farben, „Übrige“ mit Vorperiode, Beträge sauber in ihrer Spalte.
- **Cent-Beträge** in Bilanz und Cashflow klein neben den Euro.
- Ab 100 000 % (oder aus fast null) zeigen Diagramme keine Steigerung mehr an.

## 3.13.16 (2026-11-17 17:36)
- **Cashflow-Farben:** Operativer Cashflow blau, Investitionen gelb, Finanzierung magenta – Grün und Rot bleiben für Geld, das hereinkommt bzw. hinausgeht.
- **Kürzere Überschriften:** „Investitionen“ und „Finanzierung“ statt „Investitions-Cashflow“ und „Finanzierungs-Cashflow“.
- Das Zahnrad steht direkt neben der Auswahl der Stufen.

## 3.13.15 (2026-11-17 17:22)
- **Zielkonto je Empfänger** (Cashflow-Positionen): Geld für „Sparen & Anlegen“, das auf keinem deiner Konten als Buchung ankommt (etwa in ein Depot mit Kontoständen), ordnest du je Empfänger einem Konto zu. So kann eine Kategorie wie „Sparen“ auf mehrere Konten laufen. Kontor schlägt ein Depot vor, wo es eindeutig ist.
- **Ohne Zielkonto kein Kursgewinn:** Solches Geld steht im Cashflow unter Wertänderungen als eigene Zeile „Anlage ohne Zielkonto“ (mit Link zur Einstellung), statt still als Wertzuwachs eines Depots zu zählen.
- **Cashflow-Tabelle:** vier Stufen als kleine Symbole in der Kopfzelle; die erste zeigt nur die Hauptebenen. Planspalten sind in allen Zeilen schraffiert, auch in den Summen.
- **Diagramme:** je zwei nebeneinander. „Ausgaben nach Position“ steht schmal neben der Brücke und hat rote Balken; Betrag, Anteil, Vorperiode und Veränderung erscheinen beim Darüberfahren bzw. Antippen, die Unterkategorien dann in Farben ohne Rot.

## 3.13.14 (2026-11-17 16:45)
- **Cashflow und Planung in Safari:** Beim schnellen Scrollen erschienen die Zeilennamen verspätet und die Spalten wirkten verrutscht. Die Namensspalte ist jetzt ein festes Stück und erscheint sofort mit den Zahlen.
- **Bankguthaben:** Monate, in denen ein Konto noch nicht existierte, zeigen wieder den Betrag statt „unbekannt“ – das Konto zählt dort mit 0, wie in der Bilanz.

## 3.13.13 (2026-11-17 16:11)
Cashflow als Kapitalflussrechnung.
- **Gliederung wie in einer professionellen Kapitalflussrechnung:** Operativer Cashflow (Einnahmen und Ausgaben), Investitions-Cashflow, Finanzierungs-Cashflow, dann Veränderung des Bankguthabens. „Überschuss“, „Nach Zins und Tilgung“ und „Rohertrag“ entfallen.
- **Investition und Finanzierung nach Art:** Immobilien, Wertpapiere & Geldanlagen, Beteiligungen, gewährte Darlehen bzw. Darlehensaufnahme, Tilgung, Zinsen, Einlagen und Entnahmen – die Konten und Darlehen darunter. Die Auszahlung eines Darlehens steht als **Darlehensaufnahme**, nicht mehr als „negative Tilgung“; die Planung zählt sie nicht mehr in die durchschnittliche Rate.
- **Neue Diagramme:** eine Brücke vom Bankguthaben am Anfang zum Ende, Cashflow je Monat nach Tätigkeit, Mittelherkunft und -verwendung sowie Ausgaben nach Position mit Anteil, Vorperiode und Veränderung – beim Darüberfahren teilt sich der Balken in die Kategorien.
- **Kategorien:** Bereiche, die du nicht zuordnest (z. B. eine GmbH), lassen sich abwählen; sie erscheinen nicht mehr in der Liste und zählen nicht mehr als offen.
- Excel-Export und Übersicht in derselben Gliederung.
- Ist ein Bankstand nicht bekannt, steht im Cashflow „unbekannt“ statt einer Zahl; die Legende „Plan / laufender Monat“ entfällt.

## 3.13.12 (2026-11-17 15:25)
- **Kontenspiegel und andere Kontoauswahlen:** Konten mit gleichem Namen zeigen ihre Gesellschaft (z. B. „Kapitalkonto A · Alpha GbR“) – in der Liste und im gewählten Eintrag.
- **Cashflow:** Die Auswahl „Überblick / Positionen / Details“ steht in der Kopfzelle der Tabelle, direkt über den Pfeilen; am iPhone klappt dort ein großer Pfeil mit jedem Tippen eine Stufe weiter auf, zuletzt wieder zu. Das Zahnrad daneben führt zu den Cashflow-Positionen (statt des Links oben rechts).
- **Updates:** Fettgedrucktes in den Änderungen erscheint fett.

## 3.13.11 (2026-11-17 06:45)
Cashflow neu gegliedert, mit Diagrammen.
- **Eine Gliederung, drei Stufen:** „Überblick“ zeigt den ganzen Cashflow auf einer Seite (Einnahmen, Ausgaben, Überschuss, Investitionen, Finanzierung, Veränderung Bankguthaben, Wertänderungen, Veränderung Nettovermögen), „Positionen“ und „Details“ klappen bis zu den Kategorien und einzelnen Darlehen auf. Jeder Abschnitt lässt sich ein- und ausklappen, auch Einnahmen und Ausgaben.
- **Klare Überschriften**, erklärt am „?“: „Investitionen“, „Finanzierung“, „Wertänderungen“, „Überschuss“. Die Markierung „Umschichtung“ und der Erklärtext unter der Tabelle entfallen.
- **Diagramme** unter der Tabelle für einen wählbaren Zeitraum: Einnahmen und Ausgaben je Monat mit Überschuss, Zusammensetzung der Veränderung des Bankguthabens, Ausgaben und Einnahmen nach Position mit Vergleich zur Vorperiode.
- **Jahre vor und zurück:** „‹ ab 2024 ›“ neben „Monate / Jahre“ (auch in Bilanz und Planung) ersetzt den Knopf, der nur zurück führte.
- Tabellen rasten beim seitlichen Blättern nicht mehr nachträglich ein; die erste Spalte ist fest breit, Aufklappen verschiebt keine Zahlen.
- Excel-Export und Übersicht nennen die Zeilen wie die Seite („Überschuss“, „Veränderung Nettovermögen“).
- **Cashflow-Positionen** ist eine eigene Seite unter Verwaltung (Kategorie in MoneyMoney → Position im Cashflow), erreichbar auch oben rechts im Cashflow. „Zielkonto“ heißt „Angelegt auf“.

## 3.13.10 (2026-11-17 05:52)
- **Kontenspiegel sind eine eigene Regel:** eigener Abschnitt unter Buchungsregeln, zwischen zwei beliebigen Konten – ohne Gesellschaft oder Beteiligung –, jeder mit eigenem „Buchen ab“. Bisherige Kontenspiegel sind übernommen und buchen wie zuvor. Der Abschnitt „Gesellschaften“ heißt jetzt „Beteiligungen“; „optional“ entfällt.
- Kontenspiegel zwischen Konten verschiedener Währungen bucht Kontor nicht mehr (es rechnet nicht um) und sagt es.
- **Zuordnen:** Bei Zahlungen an einen anderen deiner Bereiche (z. B. Einlage in die GbR) trägt ein Knopf deine Umbuchungs-Kategorie aus MoneyMoney ein.
- Eine Kategorie, die bei dir Einnahme und in deiner Gesellschaft Ausgabe ist (Gehalt), zählt in jedem Bereich in der passenden Position; Zinsen zwischen deinen Bereichen zählen als Zinsen.
- Nach großem Umräumen der Kategorien in MoneyMoney folgen umbenannte Kategorien weiter; Einstellungen gelöschter Konten räumt Kontor zuverlässiger auf.

## 3.13.9 (2026-11-17 04:21)
- **Sync** lädt die offene Seite neu, sobald sich etwas geändert hat.
- **Speichern scheitert nicht mehr an gelöschten Konten:** Einstellungen zu Konten, die es in MoneyMoney nicht mehr gibt, entfallen von selbst; bei einem Fehler stehen nur noch die Probleme da, nicht mehr jede geprüfte Zeile.
- **Kategorien in MoneyMoney umgeräumt** (umbenannt, verschoben, gelöscht, Umsätze umgehängt): Kontor liest dann alle Umsätze neu, deine Cashflow-Position bleibt bei der Kategorie.
- **Zuordnen:** Umbuchungen innerhalb eines Bereichs stehen nicht mehr in der Liste (auch mit Gegenbuchung von Hand in einem manuellen Konto) – sie brauchen keine Kategorie. Jeder Umsatz mit Konto, ganzem Verwendungszweck und Buchungstext. Der Knopf „Umbuchung“ entfällt.
- **Zahlungen zwischen deinen Bereichen**, mit denen du etwas bezahlst (Gehalt aus der eigenen GmbH, Miete an die eigene GbR), zählen in ihrer Position statt als Einlage oder Entnahme – nach der Kategorie, ohne Kategorie nach dem Verwendungszweck.
- Cashflow-Positionen: je Kategorie ein Name („Raumkosten“ bei Kategorien einer Gesellschaft, sonst „Wohnen“); „Zielkonto“ erklärt.

## 3.13.8 (2026-11-14 19:48)
- **Cashflow, Planung und Bilanz öffnen sofort** (vorher 1–2 Sekunden bei langer Historie): Die Monatsansicht zeigt das laufende und die zwei Jahre davor; „‹ Jahr“ oben links holt frühere Monate dazu, „Jahre“ zeigt alle.
- „Arbeit“ heißt jetzt **Arbeitseinkommen** (Gehalt, Tantieme, Bonus, Honorare); Planeinstellungen bleiben erhalten.
- Umbuchungs-Kategorien erkennt Kontor auch unter den Namen „Umbuchungen“, „Übertrag“ und „Eigene Konten“.

## 3.13.7 (2026-11-14 18:19)
Cashflow verständlicher und über alle Bereiche vergleichbar.
- **Summen unten:** Rohertrag (Umsatz − Wareneinkauf, nur wo es Umsätze gibt), Einnahmen − Ausgaben, **nach Zins und Tilgung**, Bankguthaben am Anfang, Veränderung, Bankguthaben am Ende. „davon Zinsen“ entfällt (Zinsen stehen unter Finanzierung).
- **Finanzamt getrennt:** Lohnsteuer zählt bei Gesellschaften zu Personal, Umsatzsteuer als eigene Position, der Rest unter Steuern.
- Bei Gesellschaften heißt „Wohnen“ **Raumkosten** (Miete, Nebenkosten, Energie der Geschäftsräume); bei vermietenden Gesellschaften zählen Kosten des Gebäudes zu Objektkosten.
- Geplante Ausschüttungen einer Immobilie stehen bei den Einlagen und Entnahmen der Gesellschafter unter Finanzierung.

## 3.13.6 (2026-11-14 16:55)
Cashflow nach festen Positionen statt nach dem Kategorienbaum – gleich für privat, GbR und GmbH.
- **Feste Gliederung:** Arbeit, Umsatzerlöse, Vermietung, Kapitalerträge, Erstattungen · Wareneinkauf, Personal, Betriebskosten, Wohnen, Lebenshaltung, Mobilität, Versicherungen, Steuern … · Sparen & Anlegen · Tilgung, Zinsen. ▸ vor einer Position zeigt die Kategorien darin.
- **Kategorien → Cashflow-Positionen:** Kontor schlägt je Kategorie aus MoneyMoney eine Position vor (z. B. „Rückzahlung Finanzamt“ → Erstattungen, „Sparen“ → Sparen & Anlegen); deine Wahl gilt auch für die Kategorien darunter. Ersetzt „Auswahl“ und „Cashflow-Zuordnung“.
- **Ohne Kategorie geschätzt:** nach deinen bisherigen Kategorien, sonst nach Name und Verwendungszweck (Finanzamt, Gehalt, Krankenkasse, Kartenabrechnung …) – sichtbar als „ohne Kategorie, geschätzt“. Funktioniert damit auch für eine GmbH ohne Kategorien; Zuordnen macht es genauer. In MoneyMoney wird dabei nichts eingetragen.
- Immobilien-Kategorien als eigene Zeilen „Miete“ und „Kosten“; Zinsen und Tilgung bleiben unter Finanzierung.
- Planung auf den Positionen (Budgets aus MoneyMoney je Position zusammengezählt). Frühere Planeinstellungen je Kategorie entfallen.
- Excel: Kategorien unter jeder Position (eingeklappt).
- Tabellen: senkrechtes Blättern verzieht in Safari nicht mehr die Spalten.

## 3.13.5 (2026-11-14 15:32)
Kategorien neu: MoneyMoney ist die einzige Wahrheit, Kontor hilft beim Füllen der Lücken.
- **Zuordnen trägt direkt in MoneyMoney ein** (nur das Kategoriefeld, direkt vorher geprüft; eine vorhandene Kategorie nur nach Rückfrage). Zur Auswahl stehen nur Kategorien aus MoneyMoney. Einmal am Mac einschalten.
- **Vorschläge** aus deinen bisherigen Kategorien, je Umsatz – Kontor übernimmt sie nie von selbst; „Alle Vorschläge übernehmen“ auf Wunsch. Einzelne Umsätze einer Gegenpartei lassen sich abwählen.
- **Regeln für MoneyMoney:** Ordnest du eine Gegenpartei mehrmals zu, schlägt Kontor eine Regel in MoneyMoneys Schreibweise vor – kopieren, dort einfügen, fertig.
- Vom iPhone aus Zugeordnetes trägt Kontor beim nächsten Abgleich am Mac ein; Einschalten und Ändern vorhandener Kategorien nur am Mac.
- Nur Bankkonten brauchen eine Kategorie; „Unkategorisiert“ zählt als ohne. Im Cashflow führt „zuordnen“ neben „(ohne Kategorie)“ direkt zum Zuordnen.
- Entfallen: Kontors eigene Kategorien, Regeln und „nicht verwenden“.
- Ein Einstellungspaket, das vom iPhone aus eingespielt wird, kann nichts mehr ändern, was nur am Mac geht.

## 3.13.4 (2026-11-14 14:04)
Cashflow und Kategorien sind geprüft – ohne „Alpha“.
- **Jeder Monat stimmt mit der Bilanz überein:** zwei Prüfzeilen vergleichen den Zahlungsfluss mit der Veränderung der liquiden Konten und die übrigen Zeilen mit der Veränderung des Nettovermögens. ✓ heißt auf den Cent; eine Abweichung nennt beim Darüberfahren ihren Grund (z. B. Geld, das über das Monatsende zu einem Darlehen unterwegs ist).
- **Umbuchungen Buchung für Buchung gepaart:** Darlehensraten mit Kontors Tilgung (bisher teils „Unklar“ und doppelt gezählt), Gegenbuchungen über die IBAN auch eine Woche auseinander; Bankbuchungen mit Einnahme- oder Ausgabenkategorie werden nie als Umbuchung gedeutet.
- **Zwischen Bereichen:** Zahlungen in einen anderen Bereich sind Einlage/Entnahme, in einer Gesellschaft „Einlagen/Entnahmen Gesellschafter“. Hältst du die Beteiligung, steht der Unterschied zwischen eingezahltem Geld und ihrem Wert unter Bewertung.
- Wertanpassungen der Beteiligung mit Kategorie „Umbuchung“ zählen jetzt als Bewertung (fehlten bisher im Cashflow).
- **Konten in Fremdwährung** zählt Kontor nicht mehr als Euro: Sie stehen in der Bilanz außerhalb des Nettovermögens, in ihrer Währung.
- Cashflow-Zeilen und Excel-Export auch auf Englisch; Einlagen werden in der Planung nicht mehr als Monatsdurchschnitt fortgeschrieben.

## 3.13.3 (2026-11-13 14:22)
- Beteiligung monatlich, vor 3.13.1 „nicht rückwirkend“ eingerichtet: Hattest du Kontors Buchung zum Monatsende in MoneyMoney in den nächsten Monat verschoben, prüfte Kontor das abgelaufene Monatsende nicht mehr und die Beteiligung blieb dort falsch. Jetzt wird es immer geprüft (gefunden von den nächtlichen Zufallstests).

## 3.13.2 (2026-11-12 17:05)
Grundlage für die weitere Entwicklung – an Kontor selbst ändert sich nichts.
- Fahrplan mit klaren Abnahmekriterien je Bereich (Kategorien und Cashflow zuerst).
- Jede Änderung wird nach festem Ablauf geprüft und veröffentlicht; Rechenlogik und Zugriffe auf MoneyMoney prüft vorher ein unabhängiger Durchgang.
- Feste Sperren bei der Entwicklung: kein Zugriff auf Kontors Datenordner oder MoneyMoneys Daten am Mac, keine Überweisungen.
- Automatische Tests bei jedem Update (auch mit der Python-Version des Mac) und jede Nacht mit 1000 Zufallsläufen; ein Test verhindert persönliche Daten im öffentlichen Repo.

## 3.13.1 (2026-11-10 19:35)
Auto-Buchungen ohne eigene Buchungsliste – Kontor leitet alles aus MoneyMoney und den Einstellungen ab, Änderungen dort bringen nichts mehr durcheinander.
- **Was gebucht ist, erkennt Kontor in MoneyMoney:** an der Markierung oder an einer gleichen Buchung, die du selbst angelegt hast (Tilgung mit gleichem Betrag bis 7 Tage neben der Zahlung, Zinsen mit „Zins“ im Text oder der Zinskategorie, im Kontenspiegel gleiche Buchungen auf beiden Seiten). Geänderte Buchungen gelten, wie sie jetzt sind; gelöschte schlägt Kontor wieder vor. Funktioniert auch mit Konten, die du schon von Hand geführt hast, und ohne Datensicherung.
- **Vollautomatisch bucht Kontor nur, was seit der letzten Prüfung neu ist.** Älteres – rückwirkend oder in MoneyMoney gelöscht – wartet auch dann auf deine Freigabe (Hinweis „älter“), ebenso Zinsen, die darauf aufbauen.
- **„Buchen ab“** je Gesellschaft (statt „Rückwirkend ab“): ein Tag (neu: heute) oder alles. Kontor prüft bei jedem Abgleich den ganzen Zeitraum und korrigiert genau den Tag, an dem etwas fehlt oder geändert wurde. „Erneut prüfen“ und „Neu buchen“ entfallen.
- **Echte Zinsen:** Kontors Zinsbuchung in MoneyMoney ändern oder die Zinsen selbst buchen – Kontor bucht für diesen Monat dann nichts, doppelte Zinsen in einem Monat meldet es.
- **„Nicht buchen“** wird in den Einstellungen gespeichert (also auch in der Datensicherung); „Wieder vorschlagen“ statt „Neu buchen“. Bisherige Entscheidungen werden übernommen.
- Hinweise, wenn die Zahlung zu einer Tilgung fehlt; bekommt eine Zahlung oder ein gespiegeltes Original in MoneyMoney eine neue Nummer, zählt Kontors Buchung weiter.
- Bearbeiten in der Freigabe: Betrag und Datum nur bei Darlehen (Wertanpassungen und gespiegelte Buchungen folgen MoneyMoney genau), Text überall.
- „Von Kontor angelegt“ zeigt alle Buchungen mit Kontors Markierung. Punkt an „Auto-Buchungen“ in der Seitenleiste, wenn es Hinweise gibt; umbenannte Konten sind nur noch ein Rechenweg-Hinweis.
- Fällt die Vorschau oder Neuberechnung der Regeln einmal aus, bleibt die Seite bedienbar.

## 3.13.0 (2026-11-10 18:09)
Prüfung aller Funktionen, Schwerpunkt: nie etwas in MoneyMoney kaputt machen.
- **Was Kontor in MoneyMoney schreibt, ist jetzt eng begrenzt:** neue Buchungen nur in Offline-Konten, nur mit Markierung, nie zweimal (vor jeder Buchung erneut geprüft); die Kategorie eines Umsatzes nur, wenn du sie zuordnest und das Zurückschreiben an ist; der Belegpfad wird an den Kommentar angehängt statt ihn zu ersetzen. Die Darlehensregel schreibt nichts mehr an deine Bankumsätze (Kommentar/Kategorie). Eine Buchung wird nur noch über die Konto-ID angelegt (nie über einen Namen) und nach einem Fehler oder Zeitlimit nicht blind wiederholt. Eine Kategorie, die es in MoneyMoney nicht gibt, wird nicht mitgegeben (Hinweis statt neuer Kategorie).
- **Markierung „#kontor-…“** statt „#mm-…“ – in MoneyMoney sieht man, dass Kontor die Buchung angelegt hat. Ältere Buchungen mit „#mm-…“ zählen weiter als dieselben.
- **Kontenspiegel** (vorher „Gegenkonten“): Sender bzw. Empfänger ist die Gesellschaft bzw. Person, nicht das Konto; Text „… · gespiegelt von <Konto>“. Was beim Einrichten schon da war, spiegelt Kontor nur nach Freigabe – auch bei „Vollautomatisch buchen“. Wertanpassungen werden nie gespiegelt.
- **Nach dem Speichern der Buchungsregeln** werden die Auto-Buchungen sofort neu gerechnet.
- Die Konten der Buchungsregeln werden bei jedem Abgleich vollständig gelesen – die Regeln rechnen nie auf einem älteren Stand.
- Rechnen die Buchungsregeln einmal nicht (unerwarteter Fehler), wird nichts gebucht; Lesen und Auswertung laufen weiter, der nächste Abgleich versucht es erneut.
- Beschädigte oder von Hand geänderte Einstellungen werden beim Laden bereinigt, statt Abläufe abzubrechen. Ein einzelnes nicht lesbares Konto hält den Abgleich nicht mehr auf.
- Private Kapitalkonten werden immer als „Beteiligungen“ vorgeschlagen, auch mit negativem Saldo.
- Auto-Buchungen: Hilfe-Symbol neben dem Seitentitel (Klick: Abschnitt „Auto-Buchungen“ in der Hilfe).
- Die Oberfläche lädt nach einem Update auch nach einer neuen Anmeldung die neuen Dateien.
- Neue Tests: Zufallsabläufe (Freigeben, Verwerfen, Löschen, Ändern, neue Zahlungen) mit Prüfung, dass nichts doppelt gebucht und nichts Bestehendes verändert wird; feste Liste aller Schreibwege; Verweise zwischen Oberfläche, Hilfe und Dienst.

## 3.12.35 (2026-11-10 17:21)
- Gegenkonten: Von Hand gebuchte Paare zählen nur bei gleichem Tag und Betrag – der Spiegel ist exakt.

## 3.12.34 (2026-11-10 17:14)
- Gegenkonten sind jetzt ein Spiegel: Jede Buchung im einen Konto kommt mit umgekehrtem Vorzeichen ins andere – in beide Richtungen, soweit beide Offline-Konten sind. Früher beidseitig von Hand gebuchte Paare werden erkannt. Fehlt das Original einer Gegenbuchung oder wurde es geändert, steht ein Hinweis unter „Auto-Buchungen“. Das Feld „Faktor“ entfällt.
- Wertanpassungen der Beteiligung nennen die Rechnung: „Wertanpassung: Anteil × … (Wert …) = …“.
- Auto-Buchungen: Hilfe-Symbol mit Kurzhilfe (Klick: Hilfe) und Link zu den Buchungsregeln.
- Nach einem Update lädt die Seite erst neu, wenn der Dienst wieder antwortet – keine Fehlerseite mehr in der Web-App.
- Neue Konten aus MoneyMoney erscheinen sofort, nicht erst nach dem ersten Umsatz.
- Konten mit „Kapitalkonto“ im Namen werden privat als „Beteiligungen“ vorgeschlagen (in der Gesellschaft weiter als Schuld), auch wenn sie in MoneyMoney Darlehenskonten sind.

## 3.12.33 (2026-11-10 16:52)
- Abgleich und Freigabe: links unten (und auf „Freigeben“) steht, was Kontor gerade tut – „Liest MoneyMoney …“, „Bucht 12 von 56 …“. Das Ergebnis erscheint sofort, die Auswertung rechnet Kontor danach im Hintergrund neu; ein Abgleich muss nicht mehr auf sie warten.
- Kategorien, die du zuordnest, während die Auswertung neu berechnet wird, gehen nicht mehr verloren.
- Nach einem Update lädt sich die Oberfläche selbst neu – auch wenn das Fenster im Hintergrund war und du dich neu angemeldet hast.
- Nach einer Anmeldung in einem anderen Fenster übernimmt die Seite die neue Sitzung, statt mit „CSRF-Prüfung fehlgeschlagen“ (403) abzubrechen.
- „Nicht gebucht“ und „Verlauf“ sind beim Öffnen der Seite eingeklappt; „Aktualisieren“ zählt nicht mehr als eigener Eintrag im Verlauf (höchstens 100 Einträge).

## 3.12.32 (2026-11-10 16:29)
- Auto-Buchungen: „Nicht gebucht“ bleibt nach „Neu buchen“ geöffnet und an seiner Stelle – mehrere lassen sich nacheinander neu buchen; die Freigabe wird dabei nur aus den Konten der Buchungsregeln neu gerechnet.
- Überflüssige Erklärtexte auf der Seite entfernt (stehen im Hover der Knöpfe und in der Hilfe).

## 3.12.31 (2026-11-10 15:27)
- Auto-Buchungen: „Aktualisieren“ neben „Freigeben“ liest nur die Konten neu, die die Buchungsregeln betreffen, und rechnet die Freigabe neu – schneller als „Sync“, bucht nichts.

## 3.12.30 (2026-11-10 15:01)
- Freigabe: Abwählen, Verwerfen oder Ändern einer Buchung rechnet die Liste sofort neu – die nächste Wertanpassung desselben Kontos gleicht die Differenz aus (bei Darlehen die Zinsen danach). Gebucht wird genau, was angezeigt ist; hat sich in MoneyMoney inzwischen etwas geändert, bucht Kontor nichts und zeigt die neuen Beträge.
- In MoneyMoney gelöschte oder geänderte Wertanpassungen: Kontor prüft ihren Tag einmal neu und bucht dort, was fehlt (statt der Differenz heute) – die Buchungen danach bleiben. Sie stehen nicht mehr unter „Nicht gebucht“.
- Markierungen nehmen die erste freie Nummer eines Tages (keine doppelte Markierung nach einer gelöschten Buchung).

## 3.12.29 (2026-11-10 14:23)
- Gesellschaften: alle Einstellungen direkt sichtbar (kein ausklappbarer Bereich), „Beteiligung“ heißt jetzt „Beteiligungskonto“ und ist nicht vorausgewählt.
- „Rückwirkend ab“ steht standardmäßig auf „nicht rückwirkend (ab jetzt)“.
- Die Rechnung steht grau neben dem Soll: „(= N % × Betrag Wert der Gesellschaft)“.

## 3.12.28 (2026-11-10 14:02)
- „Neu buchen“ legt eine Buchung wieder zur Freigabe vor, wo du sie vor dem Buchen ändern kannst; mit „Vollautomatisch buchen“ bucht es sie sofort.
- Verlauf unter Auto-Buchungen zeigt nur noch die Prüfungen (Zeit, Vorschläge, gebucht, Fehler) – die Buchungen selbst stehen darüber.

## 3.12.27 (2026-11-10 13:51)
- Touch ID: Der Dialog erscheint erst, wenn du zu Kontor wechselst – nicht mehr im Vordergrund, wenn Kontor im Hintergrund gesperrt wurde.
- Gegenkonten als „optional“ gekennzeichnet; Hilfe erklärt, wofür sie gut sind und wann man sie nicht braucht.
- „Buchungsregeln“ ohne Alpha-Kennzeichen.

## 3.12.26 (2026-11-10 13:44)
- Auto-Buchungen: „Nicht gebucht“ sammelt Buchungen, die du nicht gebucht hast (✕), und solche, die nachträglich in MoneyMoney gelöscht wurden. „Neu buchen“ legt sie mit Datum, Betrag und Text wie zuvor an. Den Status „fehlt“ gibt es nicht mehr; „Von Kontor angelegt“ zeigt nur, was in MoneyMoney steht. Taucht eine gelöschte Buchung dort wieder auf, gilt sie wieder als angelegt.

## 3.12.25 (2026-11-10 02:09)
- „Rückwirkend ab“: nicht rückwirkend, ab einem bestimmten Tag (Datumsfeld) oder alles seit der ersten Buchung der Gesellschaft.
- Seitenleiste: Zahl und Punkt in den Farben der Oberfläche statt rot; ab 100 wartenden Buchungen „99+“.

## 3.12.24 (2026-11-10 01:53)
- Freigabe: Auswahl einzelner Buchungen klappt jetzt auch bei zwei Gesellschaften (gleiche Markierung in verschiedenen Konten wurde verwechselt); der Kommentar an der Quellzahlung geht mit seiner Tilgung. Dieselbe Verwechslung hätte bei zwei Darlehen Zinsen übersprungen – behoben.
- Beteiligungen und Gegenkonten: „Buchen“ täglich (Standard, MoneyMoney zeigt den aktuellen Stand) oder monatlich; Empfehlung je nach Freigabe. „Rückwirkend ab“ spielt die Vergangenheit einmalig ein (täglich je Tag mit Änderung) und prüft danach nur noch den aktuellen Stand; „Erneut prüfen“ kontrolliert den ganzen Verlauf noch einmal.
- Schneller: Nach eigenen Buchungen kein vollständiges Lesen mehr (Kontor behält sie bis zum nächsten), nach der Freigabe sofort aktuell (Auswertung im Hintergrund), Wertberechnung über viele Tage deutlich schneller. Das Protokoll zeigt die Zeiten je Schritt.
- Keine macOS-Mitteilungen mehr – die Seitenleiste zeigt, was zu tun ist.

## 3.12.23 (2026-11-10 01:23)
- Seitenleiste zeigt, wo etwas zu tun ist: Zahl an „Auto-Buchungen“ für wartende Buchungen („!“ nach einem Fehler), roter Punkt an „Updates“ für eine neue Version; bei schmalem Fenster ein Punkt am Menüknopf, in der Web-App im Dock die Zahl am Symbol. Der Datenstand unten links zeigt das nicht mehr doppelt.
- „Jetzt prüfen“ entfällt: Jeder Abgleich („Sync“) prüft die Buchungsregeln – jetzt auch, wenn sich nur die Regeln, deine Entscheidungen (abgelehnt, wieder anlegen) oder der Tag geändert haben.
- „Auto-Buchungen“ ohne Alpha-Kennzeichen.

## 3.12.22 (2026-11-10 01:13)
- Auto-Buchungen: Freigabe einzeln – Häkchen entfernen nimmt eine Buchung aus (sie wartet weiter), der Stift ändert Datum, Betrag oder Text (die Markierung bleibt), ✕ lehnt sie ab. Abgelehnte schlägt Kontor nicht wieder vor („Abgelehnt“ → „Wieder vorschlagen“).
- „Von Kontor angelegt“ zeigt nur noch, was wirklich in MoneyMoney steht – nicht schon die wartenden Vorschläge. Auch die Vorschau in den Buchungsregeln rechnet mit dem Stand in MoneyMoney.
- „Nur Bericht aktualisieren“ entfällt: „Jetzt prüfen“ aktualisiert die Auswertungen ohnehin (und bucht nichts).

## 3.12.21 (2026-11-10 00:05)
- Buchungsregeln: Als Beteiligung wählbar sind nur Offline-Konten mit der Position „Beteiligungen“. Passt genau eines dem Namen nach zur Gesellschaft, ist es vorausgewählt (übernommen mit „Speichern und prüfen“). Warnung, wenn ein gespeichertes Beteiligungskonto eine andere Position hat.
- Synchronisierung: „Online-Konten“ und „Offline-Konten“; je Konto „Art“ als Auswahl (Online/Offline) statt des Häkchens „abgerufen“. Erkannte Offline-Konten heißen einheitlich „Offline-Konto“, eigene Festlegungen „von dir festgelegt“.
- Nach ⌘S fragt die Seite beim Verlassen nicht mehr nach ungespeicherten Änderungen.

## 3.12.20 (2026-11-09 20:59)
- Von Hand geführte Konten: Eine eingetragene Bankleitzahl schließt ein Konto nicht mehr aus. Ob Kontor bucht, folgt jetzt genau der Einordnung unter Synchronisierung (nie abgerufen, ohne Bank- und Kontonummer, als Offline-Konto angelegt, von Kontor bebucht – oder dort das Häkchen „abgerufen“ entfernt).

## 3.12.19 (2026-11-09 19:52)
- Von Hand geführte Konten werden zuverlässig erkannt, auch wenn MoneyMoney nach einer Buchung einen Abrufzeitpunkt setzt (Kontotyp „Offline“, „abgerufen“ unter Synchronisierung abgewählt oder schon von Kontor bebucht). Damit erscheinen sie in den Auswahllisten für Beteiligung, Gegenkonten und Darlehen. Konten mit Bankleitzahl werden weiter nie bebucht.
- „Vollautomatisch buchen“ statt „Automatisch buchen“; „Darlehen hinzufügen“ und „Gegenkonto hinzufügen“ als sichtbare Schaltflächen.
- Hinweise ohne den Zusatz „Klick: mehr in der Hilfe“.

## 3.12.18 (2026-11-09 19:07)
- Buchungsregeln (vorher „Auto-Regeln“) neu aufgebaut: Darlehen als aufklappbare Zeilen mit gegliederten Feldern; je Gesellschaft eine Karte mit Beteiligung und Gegenkonten (ersetzt „Beteiligungen“ und „Saldo-Spiegel“). Der Anteil steht nur noch unter Einrichtung → Bereiche.
- Neben jeder Regel Soll, Ist und Differenz, schon beim Ändern; neben jedem Feld ein „?“ mit Erklärung und Verweis in die Hilfe; eine Speicherleiste für die ganze Seite (⌘S).
- Rückwirkend buchen: Beteiligungen und Gegenkonten auf Wunsch ab einem Monat, je eine Buchung zum Monatsende (nur die Differenz, unbekannte Monate werden übersprungen).
- Warnung, wenn ein Gegenkonto zusätzlich zur Beteiligung doppelt zählt. Eigenkapitalquote und Einlagen im Cashflow ergeben sich aus den Gesellschaften; die Einstellung „Beteiligungsgruppen“ entfällt.
- Einrichtung: Schritte heißen nur noch nach ihrem Thema, der lange Einleitungstext entfällt.

## 3.12.17 (2026-11-09 17:49)
- Auto-Regeln: Schalter „Automatisch buchen“ oben (aus = mit Freigabe), wie in den macOS-Einstellungen; Auto-Buchungen zeigen oben rechts, was gilt, und haben „Freigeben“ und „Jetzt prüfen“ mit Symbolen.
- Erkennung geänderter Markierungen: Jede Buchung in MoneyMoney zählt nur einmal; Buchungen mit fremder Markierung zählen nicht mit.

## 3.12.16 (2026-11-09 17:31)
- Auto-Buchungen: „Vor dem Buchen fragen“ oder „Automatisch buchen“ statt „Testmodus“ (umschalten nur am Mac); „Jetzt prüfen“ und „Freigeben und buchen“. Hinweise zuerst, Rechenwege und Verlauf aufklappbar; Verweise zwischen Auto-Regeln und Auto-Buchungen.
- Nie doppelt: Kontor führt eine eigene Liste aller Buchungen, die es angelegt hat. Geänderte Markierungen erkennt es an Konto, Datum und Betrag; in MoneyMoney gelöschte Buchungen legt es nicht von selbst neu an, sondern zeigt sie als fehlend („Wieder anlegen“).
- „Von Kontor angelegt“ (statt „In MoneyMoney angelegt“) mit Status je Buchung.

## 3.12.15 (2026-11-09 16:49)
- „Regeln“ heißt jetzt „Auto-Regeln“, „Buchungen“ jetzt „Auto-Buchungen“ – es geht um automatische Buchungen.
- Auto-Buchungen: neue Liste „In MoneyMoney angelegt“ mit allen Buchungen, die Kontor angelegt hat (so, wie sie jetzt in MoneyMoney stehen); Hinweis, wie man sie löscht.
- Sicherheit: Auch der Probelauf am Mac schreibt keine Beträge, Empfänger oder Texte mehr ins Protokoll. Mitteilung „Buchungen angelegt“ auch auf Englisch.

## 3.12.14 (2026-11-09 16:14)
- Touch ID: Der Helfer startet als kleine App über macOS selbst und bekommt so den Fokus – Finger auflegen genügt, ohne erst auf den Dialog zu klicken.

## 3.12.13 (2026-11-09 15:43)
- ⌘L sperrt Kontor (auch in der Web-App im Dock).
- Touch ID: Der Dialog holt sich nach vorn, statt hinter dem Fenster zu bleiben.

## 3.12.12 (2026-11-09 15:22)
- Sicherheit: Offline-Kopie am iPhone mit dem Kontor-Passwort verschlüsselt (eigenes Schlüsselpaar je Gerät, privater Teil nur mit Passwort); die bisherige unverschlüsselte Kopie wird gelöscht. Sie entsteht neu bei der nächsten Anmeldung mit Passwort, solange der Mac erreichbar ist.
- Sicherheit: Unter 127.0.0.1 antwortet Kontor nur noch auf Namen dieses Macs (127.0.0.1, localhost, *.localhost) – fremde Webseiten, deren Name auf den Mac zeigt, bekommen nichts.

## 3.12.11 (2026-11-09 15:08)
- Öffentliches Repo: Beispielwert für den Tailscale-Zugang durch einen erfundenen ersetzt; Testdaten als erfunden gekennzeichnet (Beispiel-IBANs aus Bankunterlagen).

## 3.12.10 (2026-11-09 14:58)
- Sicherheit: Von unterwegs (auch mit „ansehen und bearbeiten“) weder Belegordner noch Dateiverknüpfungen ändern; ein Abgleich von dort ist immer ein Probelauf. Unterordner für Belege bleiben immer im Belegordner.
- Sicherheit: Passwortwechsel erneuert auch die eigene Anmeldung. Ohne Schlüsselbund kein neuer Schlüssel als Datei (Kontor startet dann nicht); liegt neben dem Schlüsselbund noch eine Schlüsseldatei, wird sie entfernt.
- Sicherheit: Protokoll ohne Bereichs- und Objektnamen; Protokolle älterer Versionen werden einmalig gelöscht.

## 3.12.9 (2026-11-09 14:10)
- Sicherheit: Ohne funktionierende Verschlüsselung startet Kontor nicht mehr (bisher: Weiterarbeit unverschlüsselt). Ein Datenschlüssel, der als Datei im Datenordner liegt, zieht in den Schlüsselbund um; die Datei wird gelöscht.
- Sicherheit: Protokoll ohne Beträge, Empfänger, Verwendungszwecke und Kontonamen von Buchungen (auch im Probelauf).
- Sicherheit: Passwortwechsel meldet alle anderen Geräte ab. Belege außerhalb des Belegordners nur noch am Mac verknüpfbar, nur Belegdateien, nichts aus versteckten Ordnern, dem Datenordner oder der Library.
- Laufender Monat: geht ohne Stufe in den Plan über.

## 3.12.8 (2026-11-09 13:56)
- Kleine Grafiken: laufender Monat und Plan wie in der großen – ein Schleier über Flächen und Kurven statt schwarzer Fläche, Plankurven etwas blasser.
- Laufender Monat (alle Grafiken): eigener heller Schleier, der zum Plan hin weich zunimmt – mit sichtbarer Kante am Schnitt und beim Übergang in den Plan.

## 3.12.7 (2026-11-09 13:45)
- Bilanzgrafik: Der laufende Monat geht als weicher Verlauf von der Vergangenheit (ohne Schleier) in den Plan über.
- Grafik 2: Zeile „Gebundenes Verm.“ beim Darüberfahren durchgehend gekürzt, damit sie in eine Zeile passt.

## 3.12.6 (2026-11-09 13:35)
- Kleine Grafiken: Zeiträume über zwei Jahren in Jahren und Monaten („2 Jahre 8 Mon.“, „2 ½ Jahre“).
- Kennzahlen unter dem Nettovermögen (Eigenkapitalquote) sind zugeklappt; ein Klick auf „Nettovermögen“ klappt sie auf.
- Grafik 2: neue Namen – „Liquides Vermögen“ (statt „Verfügbar“), „Geldanlagen“ (statt „Finanzvermögen“), neu „Geldvermögen“ (mit Beteiligungen und Forderungen, wie bei der Bundesbank), „Gebundenes Vermögen“.

## 3.12.5 (2026-11-09 04:49)
- Eigenkapitalquote erscheint jetzt auch ohne neue Daten in MoneyMoney: Nach einem Update rechnet Kontor die Auswertung einmal neu.
- Kleine Grafiken: unter den Zeitraum-Knöpfen steht die Länge des gezeigten Zeitraums; nach dem Zoomen ist der passende Knopf wieder markiert, sobald die Länge stimmt.
- Grafik 2: Die Namen der Kombinationen stehen beim Darüberfahren und in der Hilfe als schriftliche Rechnung untereinander.

## 3.12.4 (2026-11-09 04:30)
- Neu (Alpha): Eigenkapitalquote unter dem Nettovermögen – durchgerechnet durch die Gesellschaften (deren Schulden mit deinem Anteil); ein Klick zeigt die Rechnung Schritt für Schritt.
- Kapital- und Gesellschafterkonten (auch Gesellschafterdarlehen) zählen mit Guthaben standardmäßig zu den Beteiligungen statt zu den Forderungen.
- Klick auf Monatsüberschrift oder Nettovermögen: Markierung blinkt nur kurz, die kleinen Grafiken enden mit dem Monat, die Seite scrollt nicht mehr.
- Kleine Grafik 3: Klick in die Grafik ließ die Auswahl oben verschwinden – behoben.
- Kästchen etwas weicher, weniger Leerraum am Seitenende.

## 3.12.3 (2026-11-09 04:08)
- Klick auf eine Monatsüberschrift: Die große Grafik steht wieder genau über der Spalte. Klick auf einen Wert des Nettovermögens ebenso, dazu blinkt sein Punkt kurz auf.
- Große Grafik: Wert und Veränderung unter der Überschrift, Werte-Fenster leicht durchsichtig, mindestens fünf Hilfslinien, „heute“ entfällt (dafür etwas höher). „Plan“ steht links vom Monatsfeld; das Feld zählt die Monate bis zum letzten abgeschlossenen.
- Kleine Bilanz-Grafik: ohne Wertzeile, dafür höher.

## 3.12.2 (2026-11-09 03:33)
- Große Grafik: Nettovermögen, Auswahl und Zusammensetzung zeigen Wert und Veränderung wie die kleinen; die Bilanz zeigt keine Veränderung mehr (groß und klein).
- Bilanz als große Grafik: etwa ein Drittel des Zeitraums nach vorn – laufender Monat und Plan (1 J: +4 Monate, 3 J: +12). Schalter „Plan“ links neben den Zeiträumen, gehört zur Ansicht.
- Bilanz-Tabelle: erste Spalte am rechten Rand breiter oder schmaler ziehen (Doppelklick: Standard), gehört zur Ansicht.
- Goldener Strich vor „Nettovermögen“ im Werte-Fenster und in der Tabelle.
- Kleine Grafiken: Werte-Fenster leicht durchsichtig; beim Nettovermögen nur Monat und Betrag.
- Neues Logo: dunkle Kachel, helles K mit goldenem Punkt.

## 3.12.1 (2026-11-09 03:04)
- Akzente neutral statt Gold (dunkel: weiß, hell: schwarz) – sie konkurrieren nicht mehr mit den Farben der Grafiken; Gold bleibt für Logo und Nettovermögen. Links im Text unterstrichen.
- Bilanz-Tabelle: erste Spalte fest breit, damit sich beim Auf- und Zuklappen nichts verschiebt; lange Konto- und Wertpapiernamen werden gekürzt.
- Werte-Fenster der Grafiken gleich breit, lange Namen gekürzt.
- „Bruttovermögen“ heißt in der Erklärung auch „Bilanzsumme“.

## 3.12.0 (2026-11-09 02:46)
- Neuer Look: Akzentfarbe Gold statt Blau, neues goldenes Logo (auch als Symbol am iPhone).
- Dunkel ist jetzt der Standard; hell oder wie das System unter Einstellungen → Allgemein → Erscheinungsbild (je Gerät).
- Bilanz in Hilfe, README und den Hilfe-Symbolen neu beschrieben (Zeiträume, Tabelle, große Grafik, einzelne Grafiken, Anordnung und Ansicht speichern); Bilder im neuen Look.

## 3.11.8 (2026-11-09 02:36)
- Bilanz-Grafik: Nach einem Klick auf eine Fläche ist alles markiert, was aufgeklappt wurde, bis sich die Maus bewegt. Die Tabelle bleibt beim Auf- und Zuklappen stehen und rückt nur, wenn der Monat nicht schon dort steht.
- Klick auf einen Wert der Tabelle: Fläche und Monat leuchten in der großen Grafik einmal kurz und weich auf.
- Zweiter Klick auf ein Konto (bzw. Wertpapier) schließt seinen Verlauf wieder.
- Klick auf eine Spaltenüberschrift verschiebt die Grafik, ohne die Auswahl des Zeitraums (z. B. „1 J“) zu verlieren.
- Große Grafik vorausgewählt: 1 J (Monate) bzw. 3 J (Jahre).
- Grafiken: mindestens vier Hilfslinien auf der Betragsachse (z. B. 0 / 25 / 50 / 75 / 100 Tsd.).
- Kleine Bilanz-Grafik: Zeilen der Legende enger beisammen.

## 3.11.7 (2026-11-09 02:11)
- Grafiken der Bilanz: Zeiträume enden am letzten abgeschlossenen Monat (im November: „1 J“ = Oktober bis Oktober). Der laufende Monat ist gepunktet und leicht hinterlegt, der Plan gestrichelt; die senkrechte Linie markiert das Ende des letzten abgeschlossenen Monats, „heute“ den laufenden. Kürzester Zeitraum: ein Monat. Große Grafik zusätzlich mit 3 J (Monate) bzw. 5 J (Jahre), vorausgewählt 2 J bzw. 5 J.
- Auch die große Grafik lässt sich über kleine Pfeile in ihrem Kopf nach oben oder unten schieben (auch unter die kleinen Grafiken); wird mit „Ansicht speichern“ gemerkt.
- Bilanz-Tabelle: Klick auf den Namen wie bisher (aufklappen bzw. Verlauf), Klick auf einen Wert zeigt Monat und Fläche kurz in der großen Grafik. Hervorhebung beim Darüberfahren nur noch über dem Namen, ohne springende Monatslinie.
- Klick auf eine Fläche: Werte-Fenster und Hervorhebung sind danach sofort wieder da (ohne die Maus zu bewegen), ein zweiter Klick klappt gleich wieder zu; die Tabelle springt dabei wie gewohnt zum Monat.

## 3.11.6 (2026-11-09 01:46)
- Bilanz-Grafik: Über der Monatsachse erscheint das Werte-Fenster ohne Hervorhebung; Klick dort springt in die Tabelle, waagerechtes Wischen verschiebt.
- Klick auf eine Fläche klappt wie in der Tabelle auf (Position → Konten → Depot → Wertpapiere); Klick auf ein Konto oder Wertpapier klappt die Position wieder zu.
- Darüberfahren über die Tabelle hebt dieselbe Fläche in der Grafik hervor, über einer Zelle auch ihren Monat.
- Immobilien brauner, Nettovermögen gelber; im dunklen Modus trennt der Rand der Linie die Flächen nicht mehr sichtbar. Abstand, wenn die Tabelle über der Grafik steht.

## 3.11.5 (2026-11-09 01:27)
- Bilanz-Grafik schöner: weiche Kurven (an jedem Monatsende exakt), Flächen mit leichtem Verlauf, Nettovermögen als goldene Linie mit hellem Rand und Punkt für heute (auch in den kleinen Grafiken).
- Grafik „Auswahl“: Titel in Worten statt Kürzeln – „Finanzvermögen + Verbindlichkeiten“, „Nettovermögen ohne Beteiligungen“ usw., bei Platzmangel mit gekürzten Wörtern; ohne „Auswahl:“ davor. Darüberfahren über den Titel zeigt, was die Namen bedeuten (z. B. Finanzvermögen = Bankguthaben + Wertpapiere + Festanlagen).

## 3.11.4 (2026-11-09 01:11)
- Grafiken der Bilanz: erster und letzter Monat stehen immer auf der Zeitachse (hervorgehoben); die Zeitraum-Angabe oben rechts in den kleinen Grafiken entfällt dafür.
- „Als Standard“ heißt jetzt „Ansicht speichern“.

## 3.11.3 (2026-11-09 01:07)
- Zeiträume von Monatsende zu Monatsende: „1 J“ zeigt November bis November (13 Punkte), die Veränderung umfasst damit genau zwölf Monate (bisher elf); ebenso 6 M, 2 J usw.
- Bilanz-Grafiken: Die Fläche unter dem Mauszeiger wird hervorgehoben (die anderen blasser), ebenso ihre Zeile im Werte-Fenster.
- Bilanz-Tabelle: lässt sich über kleine Pfeile im Tabellenkopf über die große Grafik oder unter die einzelnen Grafiken schieben; wird mit „Als Standard“ gemerkt. Anzahl der Konten bzw. Wertpapiere („(9/13)“) nicht mehr fett.
- Namen der Wertpapiere: sagt, wie viele ihren Namen schon aus MoneyMoney haben (auch verkaufte) – nachgeschlagen werden nur die übrigen.

## 3.11.2 (2026-11-09 00:51)
- Einrichtung → Historische Kontostände, „Namen der Wertpapiere“: listet nach dem Einlesen alle Wertpapiere mit ISIN (auch verkaufte und ausgeblendete) mit ihrem Namen aus MoneyMoney bzw. dem nachgeschlagenen; Namen lassen sich dort ändern. Name aus MoneyMoney und ISIN bleiben beim Darüberfahren sichtbar.

## 3.11.1 (2026-11-09 00:44)
- Bilanz: „Als Standard“ gilt getrennt für Monate und Jahre (z. B. Monate 2 J, Jahre 10 J); die zuletzt gespeicherte Ansicht öffnet beim Start, beim Wechsel gelten die gespeicherten Zeiträume der anderen.
- Wertpapiere: eigener Name im Verlauf entfällt (wurde nicht übernommen). Stattdessen zeigt der Schritt „Namen nachschlagen“ danach alle nachgeschlagenen ISINs in einer Liste, in der sich Namen ändern oder ergänzen lassen.
- Text dieses Schritts korrigiert.
- Einlesen: Name und ISIN eines Wertpapiers werden über seine Kennung gesucht, auch wenn MoneyMoney es inzwischen einem anderen Konto zuordnet; das Protokoll nennt je Depot, wie viele Wertpapiere ISIN und Namen haben.

## 3.11.0 (2026-11-09 00:08)
- Erste allgemeine Version: Noch nicht vollständig geprüfte Seiten (Übersicht, Cashflow, Planung, Immobilien, Steuer, Umsätze & Belege, Kategorien, Buchungen, Regeln) sind nutzbar, im Menü aber blass und mit „Alpha“ markiert, ebenso am Seitentitel.
- Bilanz: Ansicht wird nicht mehr nebenbei gemerkt. Neu „Als Standard“ (merkt Monate/Jahre, Zeiträume bis heute, aufgeklappte Zeilen, Auge, große Grafik, Auswahl; je Gerät) und „Zurücksetzen“ auf den Standard von Kontor – neben Excel.
- Grafiken: ⤢ tauscht eine kleine mit der großen Grafik, die Reihenfolge ist damit frei.
- Wertpapiere: Name aus MoneyMoney und ISIN bleiben beim Darüberfahren immer sichtbar, auch bei eigenem Namen. Namen werden jetzt auch aus MoneyMoneys Datenbank übernommen, wo vorhanden.
- Einrichtung → Historische Kontostände: optionaler Schritt „Namen der Wertpapiere nachschlagen“ (nur auf Klick, sendet nur die ISINs an OpenFIGI; wieder entfernbar).
- Kontors eigene Monatsaufzeichnung der Wertpapiere wird jetzt dauerhaft gespeichert.

## 3.10.11 (2026-11-08 23:42)
- Bilanz: Jede der vier Grafiken kann die große oben sein (⤢ in einer kleinen Grafik tauscht sie); mit allen Möglichkeiten der großen Grafik (Zeitraum, „Alle“, An Tabelle ausrichten).
- Bilanz-Tabelle: Depots zeigen die Zahl ihrer Wertpapiere („(12)“ bzw. „(9/12)“); Wertpapiere nicht mehr fett; das Auge zählt ausgeblendete Wertpapiere nur aufgeklappter Positionen mit. Klick auf ein Wertpapier zeigt seinen Verlauf, dort lässt sich ein eigener Name vergeben. Ohne Namen „Unbenannt N“ statt „Wertpapier N“.
- Verlauf eines Kontos: Grafik lässt sich verschieben und zoomen, dazu 1 J / Alle.
- „Zusammensetzung“: höchstens drei Zeilen Einträge (größte zuerst, der Rest scrollt), Namen sinnvoll gekürzt (z. B. „ACWI“).
- „Auswahl“: Namen für typische Kombinationen (Verfügbar, Finanzvermögen, Gebunden, Bruttovermögen, Sachvermögen); groß angezeigt ausgeschrieben.
- Excel-Export der Bilanz: mit Konten und Wertpapieren, in Excel auf- und zuklappbar, beim Öffnen so aufgeklappt wie auf der Seite; mit Planspalten.
- Kleine Grafiken: Zeitraum fett. Fest eingestellter Wertebereich bleibt an der blau markierten Betragsachse erkennbar.

## 3.10.10 (2026-11-08 22:59)
- Bilanz-Tabelle: Konten leicht eingerückt; der Knopf in der Kopfzelle klappt wieder nur alle Positionen auf und zu, Depots öffnet man einzeln. Ein geöffnetes Depot zeigt seine Wertpapiere auch in der großen Grafik. Die Hinweise „Depot“ und „Kontostände“ neben Konten entfallen. Lange Namen werden gekürzt (ganz beim Darüberfahren).
- Wertpapiere ohne Wert in der eingestellten Zeit (Einrichtung → Konten, „Nach Aktivität“) sind wie Konten ausgeblendet; das Auge zeigt sie. Sein Hinweis nennt jetzt, wo das eingestellt wird.
- Grafiken: Auf der Betragsachse nach oben/unten ziehen vergrößert bzw. verkleinert den Wertebereich, das Mausrad verschiebt ihn, Tippen oder Klick dort macht ihn wieder automatisch. Seitlich verschieben geht über die Monatsachse.
- „Zusammensetzung“: auch kleine Beträge (z. B. 0,29 € Guthaben) erscheinen; bei vielen Einträgen werden die Namen unten gekürzt, beim Darüberfahren steht der ganze Name (bei Wertpapieren mit Depot).
- Laufendes Jahr ohne „Ist+Plan“-Zusatz: blass wie der laufende Monat (noch nicht abgeschlossen), Planjahre blass und schraffiert.
- Wertpapiernamen: Kontor sucht sie beim Einlesen auch unter anderen Spaltennamen und in anderen Tabellen von MoneyMoney und nimmt sonst Namen, die es aus MoneyMoney schon kennt; ohne Namen steht die ISIN statt „Wertpapier N“.

## 3.10.9 (2026-11-08 22:21)
- Depot-Aufschlüsselung: Wertpapiere ohne Namen in MoneyMoneys Datenbank werden nicht mehr zu einer Zeile zusammengefasst.

## 3.10.8 (2026-11-08 22:18)
- Bilanz: Depots lassen sich in ihre Wertpapiere aufklappen (▸ vor dem Depot). Der Knopf in der Kopfzelle klappt nacheinander die Konten, dann auch alle Depots auf und wieder zu. Werte je Wertpapier: frühere Monate aus den eingelesenen MoneyMoney-Kontoständen (bzw. Kontors monatlicher Aufzeichnung), der laufende Monat aus MoneyMoney; was die Wertpapiere nicht erklären, steht als „Übrige“.
- Kleine Grafik „Zusammensetzung“: „Depot“ neben der Auswahl schlüsselt Depots in ihre Wertpapiere auf (nur wo es das gibt, je Position gemerkt). Konten bzw. Wertpapiere lassen sich unten einzeln abwählen – die Linie der Position bleibt, beim Darüberfahren steht zusätzlich die Summe der Auswahl. Beim Wechsel der Position ist wieder alles gewählt.
- Für die Wertpapiere bitte die Kontostände einmal neu einlesen (dabei werden jetzt auch Name und ISIN der Wertpapiere übernommen).

## 3.10.7 (2026-11-08 21:57)
- Historische Kontostände der Depots: Macht eine Anlage fast das ganze Depot aus, wurde sie mit MoneyMoneys Eintrag für den Depotwert insgesamt verwechselt. Jetzt gilt der Eintrag, der am genauesten zur Summe der übrigen passt – also MoneyMoneys gespeicherter Depotwert. Bitte die Kontostände neu einlesen.

## 3.10.6 (2026-11-08 21:47)
- Historische Kontostände der Depots: Eine Position, die MoneyMoney später ersetzt oder entfernt hat (z. B. ein Guthaben im Depot), zählt bis zur nächsten Aktualisierung des Depots – auch über ein Monatsende hinweg. Bisher fiel sie schon mit ihrem letzten Punkt weg. Bitte die Kontostände neu einlesen.

## 3.10.5 (2026-11-08 13:15)
- Historische Kontostände: Depots, bei denen MoneyMoney zusätzlich den Depotwert insgesamt aufzeichnet (z. B. Trade Republic), wurden doppelt gezählt. Dieser Eintrag gilt jetzt allein. Bitte die Kontostände einmal neu einlesen.

## 3.10.4 (2026-11-08 04:59)
- „An Tabelle ausrichten“: Die Grafik nutzt links die volle Breite – über den Zeilenüberschriften der Tabelle zeigt sie die Monate davor.

## 3.10.3 (2026-11-08 04:54)
- Kürzel im Titel von „Auswahl“ erklärt: Darüberfahren (am iPhone Tippen) zeigt „C = Bankguthaben · WP = Wertpapiere …“; der Titel ist dafür fein unterstrichen.
- Kürzel für Bankguthaben: „C“ (Cash), in beiden Sprachen.

## 3.10.2 (2026-11-08 04:53)
- Kleine Grafik „Auswahl“: Titel wieder mit „Auswahl:“ davor („Auswahl: BG + WP + FA“).
- Kürzel: Beteiligungen „PE“ (Private Equity), Immobilien „RE“ (Real Estate), in beiden Sprachen.

## 3.10.1 (2026-11-08 04:46)
- Kleine Grafik „Auswahl“: Der Titel nennt die gewählten Positionen stark abgekürzt (z. B. „BG + WP + FA“, ausgeschrieben beim Darüberfahren); eine Position ausgeschrieben, alle Positionen „Nettovermögen“.

## 3.10.0 (2026-11-08 04:37)
Die Bilanz ist als erste Seite in ihrer neuen Form fertig.
- Avale & Bürgschaften (und Kapitalkonten als Eigenkapital) stehen gesammelt in je einer aufklappbaren Zeile unter dem Nettovermögen statt einzeln.
- Der Hinweis zu „(9/12)“ unter der Tabelle entfällt (verschob beim Umschalten die kleinen Grafiken); er steht jetzt im „?“ der Kopfzelle.
- Hilfe zur Bilanz neu gegliedert (Tabelle, große Grafik, einzelne Grafiken); Bilder in Hilfe und README neu.

## 3.9.47 (2026-11-08 04:29)
- „An Tabelle ausrichten“: Wischen oder Ziehen auf der Grafik (auch auf den Achsen) scrollt die Tabelle seitlich; danach rastet sie auf der nächsten Spalte ein.

## 3.9.46 (2026-11-08 04:27)
- Kleine Grafiken: Fläche immer zur Nulllinie hin gefüllt – bei negativen Werten nach oben, so ist das Vorzeichen sofort sichtbar.
- Kleine Grafiken: Kopf, Wertzeile und Grafik teilen sich die Zeilen – die Grafiken und ihre x-Achsen stehen auf gleicher Höhe, auch wenn eine Zeile umbricht.
- Bilanz: Tabellen-Optionen wieder ohne Abstand zur Grafik – in der Kopfzelle der Tabelle: ▸/▾ klappt alle Positionen auf bzw. zu, das Auge (mit Anzahl) zeigt leere und ausgeblendete Konten; Excel wieder oben rechts.

## 3.9.45 (2026-11-08 04:21)
- Bilanz: Klick auf eine Spaltenüberschrift verschiebt die Grafik so, dass der Monat ungefähr über der Spalte steht (statt in der Mitte).
- Bilanz: Der Erklärtext unter der Tabelle steckt jetzt im „?“ neben „Position / Konto“.
- Bilanz: „Konten zeigen“, „Ausgeblendete“ und Excel stehen jetzt direkt über der Tabelle; oben bleibt nur Monate/Jahre (gilt für Grafik und Tabelle). „Ausgeblendete“ erscheint nur, wenn es leere oder ausgeblendete Konten gibt.
- Anzahl der Konten je Position kompakt: „(9/12)“ = 9 von 12 angezeigt (statt „12, 3 ausgeblendet“), einmal kurz unter der Tabelle erklärt.
- Große Grafik: Flächen kräftiger, Positionen dadurch besser zu unterscheiden; Immobilien in wärmerem Braun (klar getrennt von Beteiligungen).

## 3.9.44 (2026-11-08 04:09)
- Bilanz-Grafiken: Standard-Zeitraum in der Monatsansicht 1 Jahr (groß und klein), in der Jahresansicht 3 Jahre; beim Wechsel der Ansicht gilt deren Standard.
- Farben nach Verfügbarkeit: Bankguthaben Grün, Wertpapiere Smaragd, Festanlagen Türkis, Forderungen Blau, Beteiligungen Violett.

## 3.9.43 (2026-11-08 03:58)
- „An Tabelle ausrichten“: Die Skala passt sich den sichtbaren Spalten an (Ausreißer weiter links verzerren nichts mehr).
- Kleine Grafiken: Achse nur so breit wie ihre Beschriftung. Nettovermögen zeigt darunter Ø je Monat, Höchst- und Tiefststand im Zeitraum.
- Farben: Forderungen in Goldgelb (statt Rosa), Immobilien dafür in Braun.
- Zeitraum-Knöpfe je nach Ansicht: Monate 6 M, 1 J, 2 J (Standard 2 J), Jahre 1 J, 3 J, 10 J (Standard 3 J); große Grafik zusätzlich „Alle“. „Alle“ bleibt jetzt auch nach dem Neuaufbau erhalten.
- Bilanz, Monatsansicht: keine Jahresspalten mehr (sie wiederholten nur den Dezember bzw. den laufenden Monat); ein feiner Strich trennt die Jahre.

## 3.9.42 (2026-11-08 03:41)
- Bilanz: „An Tabelle ausrichten“ – die große Grafik steht Spalte für Spalte über der Tabelle (jeder Wert genau über seiner Spalte) und scrollt mit; ohne Werte-Fenster, Zeitraum folgt der Tabelle.
- Kleine Grafiken: „seit …“ entfällt ganz; der Zeitraum oben rechts ist genau der Bezug von Wert (Ende) und Veränderung (Beginn).
- Kontofarben wieder wie in 3.9.40 (die kräftigere Abstufung aus 3.9.41 zurückgenommen).

## 3.9.41 (2026-11-08 03:38)
- Anmeldeseite: Hinweise (z. B. „Touch ID nicht bestätigt …“) stehen zentriert.
- Kleine Grafiken: Zeitraum kompakt oben rechts („Dez 25 – Nov 26“) statt ausgeschrieben unter der Grafik; „seit …“ steht als Hinweis an der Veränderung.
- Achsen: alle Beträge einer Achse in derselben Einheit („5T, 10T, 15T“ statt „5.000, 10T, 15T“).
- Forderungen in Rosa statt Hellblau – klar unterscheidbar von Wertpapieren und Festanlagen.
- Kontofarben innerhalb einer Position deutlicher unterschiedlich, „Zusammensetzung“ kräftiger.

## 3.9.40 (2026-11-08 03:26)
- Beträge an den Achsen: wo es eng ist (kleine Grafiken, Prozente) „T“ und „M“ ohne Leerzeichen („150T“, „1,2M“, „+12T %“), in den breiten Grafiken „Tsd.“ und „Mio.“ (Englisch jeweils „k“, „M“).

## 3.9.39 (2026-11-08 03:19)
- Kontofarben: Konten einer Position haben Abwandlungen ihrer Farbe (benachbarter Farbton, andere Helligkeit), auch bei 5–10 Konten gut unterscheidbar – gleich in Tabelle, großer Grafik und „Zusammensetzung“; ab dem elften Konto schraffiert.
- Kleine Grafiken: Summenlinie bei „Zusammensetzung“ in der Farbe der Position, bei „Auswahl“ in der Mischfarbe der gewählten Positionen statt Blau.
- Grafiken verschieben: auch auf der Monatsachse unten seitlich ziehen.
- Bilanz: Klick auf eine Spaltenüberschrift markiert den Monat in der Grafik nur noch mit der Linie, ohne Werte-Fenster (die Werte stehen in der Tabelle).
- Kurzbeträge einheitlich: „Tsd.“, „Mio.“, „Mrd.“ (Englisch „k“, „M“, „B“), auch bei Prozenten („+12 Tsd. %“).
- Konten mit „P2P“ im Namen werden als Festanlage vorgeschlagen (bisher Darlehen). Hilfe: Faustregel Wertpapiere oder Festanlagen.

## 3.9.38 (2026-11-08 02:57)
- Bilanz: Klick auf eine Spaltenüberschrift (Monat oder Jahr) zeigt diesen Monat in der Grafik – Zeitraum bleibt gleich lang, die Werte erscheinen daneben.
- Kleine Grafiken: „Zusammensetzung“ hat nur noch die Auswahl als Überschrift; bei „Auswahl“ stehen die Positionen unter der Grafik, damit alle drei Grafiken auf gleicher Höhe beginnen. Prozente über 1000 ohne Tausenderpunkt, ab 10 000 % in Tausend („12T %“), nicht berechenbar: ∞. Achsen: „T“ und „Mio.“ (Englisch „k“ und „M“).

## 3.9.37 (2026-11-08 02:39)
- Bilanz: Hauptgrafik zeigt beim Öffnen die letzten drei Jahre bis heute (statt einem Jahr).

## 3.9.36 (2026-11-08 02:31)
- „Kapitalfluss“ heißt jetzt „Cashflow“. Positionen kürzer: „Wertpapiere“ (statt Handelbare Anlagen) und „Festanlagen“ (statt Gebundene Anlagen).
- Bilanz: Tabelle zeigt beim Öffnen den laufenden Monat (bzw. das laufende Jahr) ganz rechts. „Konten zeigen“ / „Nur Positionen“ statt „alle aufklappen“, „Ausgeblendete“ statt „Alle Zeilen“ (Cashflow und Planung: „Leere Zeilen“); das „?“ daneben erklärt beides.
- Kleine Grafiken: Zeitraum oben rechts (1 J, 3 J, Alle), Standard 1 Jahr. Nettovermögen ohne Positionsliste. „Auswahl“ zeigt beim Darüberfahren jede Position einzeln und die Summe. Prozentuale Veränderung mit höchstens drei Ziffern (über 100 % ohne Nachkommastelle). „Zusammensetzung“: Auswahl unter dem Titel, nur Konten, die im Zeitraum nicht durchgehend 0 € stehen, Farben auch im Dunkelmodus gut lesbar.
- Updates: Änderungen tragen jetzt auch die Uhrzeit der Version.

## 3.9.35 (2026-11-08)
- Bilanz: dritte Grafik – eine Position wählen und ihre Zusammensetzung nach Konten sehen (gestapelt, eigene Pastellfarben, bei sehr vielen Konten zusätzlich schraffiert, mit Legende). Aufgeklappte Konten tragen in der Tabelle denselben Farbton wie in der großen Grafik.
- iPhone: Seite nicht mehr breiter als der Bildschirm – die Leiste der Bereiche (und Reiter) lässt sich bei vielen Einträgen seitlich schieben.
- Grafiken am iPhone: auf dem Streifen mit den Beträgen links seitlich ziehen verschiebt den Zeitraum; zwei Finger verschieben und zoomen, ohne dass dabei die Werte-Anzeige erscheint; nur ein Tippen springt zur Spalte.
- „?“ am iPhone: erstes Tippen zeigt den Hinweis, zweites öffnet die Hilfe. Der Zusatz „Klick: mehr in der Hilfe“ entfällt.

## 3.9.34 (2026-11-08)
- Am Mac legt Kontor keine Offline-Kopie der Seite mehr an (die gibt es nur fürs iPhone); vorhandene werden entfernt. Dadurch zeigt nach einem Portwechsel die alte Adresse keine Anmeldeseite mehr.
- Absichern über Tailscale: Schritt-für-Schritt-Anleitung (Regel kopieren, „Access controls“, „JSON editor“, gesamten Text ersetzen, „Save“) und eine Prüfung: Kontor liest die Regeln, die Tailscale auf dem Mac anwendet, und zeigt „abgesichert“, „noch weitere Ports erreichbar“ oder „Kontor gesperrt“.

## 3.9.33 (2026-11-08)
- „Zugriff einschalten“: Die Seite wartet jetzt auf den neu gestarteten Dienst und lädt dann selbst neu (vorher konnte sie zu früh neu laden und hängen bleiben). Während das Zertifikat geholt wird, steht ein Hinweis da.
- Port oder Adresse ändern (Einstellungen → Zugang → Erweitert): Kontor prüft, ob der Port frei ist, startet neu und öffnet die Seite unter dem neuen Port; die iPhone-Adresse nutzt ihn ebenfalls. Nur am Mac.
- Bilanz-Grafiken: 1/3/10 J zeigen genau so viele Monate bis heute (ohne Plan), die Veränderung bezieht sich damit auf den ganzen Zeitraum; der Plan bleibt per Wischen nach rechts oder „Alle“ erreichbar.
- Tailscale-Abfrage schneller und ohne Warten beim Öffnen der Seite.
- „Verlauf aus Umsätzen“ statt „Umsätze“.

## 3.9.32 (2026-11-08)
- Zugriff vom iPhone: Kontor fragt Tailscale jetzt direkt über dessen lokale Schnittstelle ab (wie Tailscales eigenes Kommandozeilenprogramm) und holt auch das Zertifikat so. Behebt „The Tailscale GUI failed to start“, wenn das Programm in Tailscale.app aus dem Hintergrunddienst nicht startet. Schlägt beides fehl, nennt Kontor beide Gründe.

## 3.9.31 (2026-11-08)
- README auf GitHub schlank: Einführung, Bilder, Installation, Entwicklung; alles Weitere nur noch in der Hilfe (keine doppelt gepflegten Texte). Sicherheit, Kommandozeile und Datenordner stehen jetzt vollständig in der Hilfe („Für Fortgeschrittene“); veraltete Angabe zum Dienstnamen korrigiert.
- Time Machine: Hinweis, dass „gesichert“ der Standard ist und „Ausschließen“ nur eine Markierung am Datenordner setzt (nicht die Time-Machine-Einstellungen ändert, daher nicht in deren Ausschlussliste sichtbar).

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
