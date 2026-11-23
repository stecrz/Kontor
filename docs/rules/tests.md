# Tests – was welche Datei prüft

Teil von `CLAUDE.md` (Aufbau). Neue Testdatei oder neuer Prüfbereich: hier eintragen.

- `fixtures.py` (erfundene Daten)
- `test_rules`, `test_cashflow` (Abstimmung je Monat, Zufallsläufe)
- `test_scenarios` (Lebensfälle über Bereiche: Einlagen, Kauf, Darlehen, Auslagen; Monats-/Jahreswechsel, gemischt)
- `test_worlds` (Zufallswelten: 1–3 Privatpersonen, bis 4 Firmen, Beteiligungen untereinander, Darlehen, PayPal, Miete, Überweisungen zwischen allen – alles geht auf, nichts bleibt unklar; Zeitraum zehn Tage bis vier Jahre mit Ende 2023–2027, je Bereich ruhig, ein Jahr ohne Buchung, konstant, stark schwankend, ein Schub von Hunderten Buchungen, saisonal, Konten, die mitten im Zeitraum beginnen oder enden – ähnlich in `test_rule_worlds` und `test_cashflow`; dazu feste Sonderfälle an jeder Art Tag zwischen jeder Art Bereich)
- `test_rule_worlds` (Zufallswelten für die Buchungsregeln: Beteiligung täglich/monatlich, Darlehen mit beiden Zinsmodellen, Zinswechsel, Buchungstag, Kontenspiegel – am Ende jeder Cent nachgerechnet, nichts zu viel; dazu Änderungen in MoneyMoney zwischen den Läufen)
- `test_categories`, `test_e2e` (simuliertes MoneyMoney, HTTP, Browser)
- `test_assistant` (mit `fake_llama.py` statt llama.cpp, Downloads ohne Netz)
- `test_assistant_eval` (Prüfsatz `assistant_eval/`: 73 Aufgaben durch den Assistenten auf der Demo-Welt – jede Musterlösung besteht, keine falsche Antwort; mit echtem Modell nur am Mac, README dort; ändert sich ein Werkzeug oder die Demo-Welt, Aufgaben in `tasks.json` mitziehen)
- `test_tables` (Excel lesen: Werte wie in Excel, Ausschnitte, Summen; abgelehnt: alte/geschützte Dateien, Entitäten, Grenzen, Teile außerhalb; CSV: Trennzeichen, Kodierung, Schreibweise je Spalte, Grenzen; Prüfproben: Summen, Überträge, Soll/Haben, SUMME-Formeln, eine verlesene Zahl, eine verlorene Zeile; Zeilen suchen)
- `test_pdf_tables` (Tabellen aus PDFs/Bildern: erfundene Auswertungen über mehrere Seiten, Spalten, Zahlen, Köpfe, schiefe Scans, jeder Fall stiller Falschzahlen aus der Prüfung und aus dem Messen Zelle für Zelle; ein Wertenachweis über 30 Seiten – jede Zeile einmal, jede Spalte, jedes Vorzeichen, keine Zahl, die das Dokument nicht nennt; Zufallstabellen Zelle für Zelle gegen das Gedruckte; `OnMac` läuft im macOS-Job mit dem echten Helfer)
- `test_web` (Internetsuche ohne Netz: Freigabe, Filter, Hosts, Grenzen, eingeschleuste Befehle; Claude: Karte mit dem ganzen Wortlaut, nie ohne Klick, Filter auf die ganze Frage, Tagesgrenze, Fehlerantworten, Schlüssel nirgends)
- `test_tour` (Rundgang: jede Seite hell/dunkel, Mac/iPhone, de/en – Skriptfehler, Überlaufen, Textschlüssel, Kontrast)
- `test_fuzz`, `test_privacy`, `test_security` (Sperre, Datenschlüssel, Belegordner; `NothingGoesOut`: welche Teile ins Netz können, zu welchen Hosts, welche Programme sie starten – ein neuer Weg nach außen wird dort eingetragen)
- `test_update_guard` (Prüfung vor dem Update: untergeschobene Änderungen werden gefunden, gewöhnliche nicht; Einstufung – Untergeschobenes bleibt kritisch, Geändertes an bestehenden Wegen und der Filter der Internetsuche zu prüfen, nachweislich Strengeres ohne Freigabe; Erklärung und Zeilen je Eintrag; Warten und Freigabe, Archiv und Git-Klon)
- `test_hooks` (Lagebild und Push-Sperre der parallelen Chats)
- `test_workflows` (Workflow-Dateien: kein Schlüssel doppelt – sonst startet GitHub gar keinen Lauf, wie nach 3.17.21)
- `test_passkeys` (Zugang vom iPhone: CBOR/COSE/DER streng, ECDSA mit RFC-6979-Vektoren, Registrierung und Anmeldung mit einem Software-Passkey samt allen Fehlfällen, Link und Herausforderungen, QR-Code; über HTTP Hinzufügen, Face-ID-Anmeldung, jede Änderung nur bestätigt und nur für genau diese Anfrage, jede POST-Anfrage, `MAC_ONLY`, Entfernen beendet Sitzungen, nach Neustart, Demo, Zurücksetzen)
- `affected.py` (kein Test): nennt die Testdateien, die eine Änderung betrifft – für den lokalen Lauf vor dem Push
