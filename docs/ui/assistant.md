# assistant — KI-Assistent
The assistant's window: a conversation with the language model on this Mac, as a panel beside any page (✦ or ⌘K) or as the page
"KI-Assistent" (the same conversation). Head: the thinking effort for the next questions (Schnell, Ausgewogen, Gründlich), Verläufe,
Neue Unterhaltung, wider/narrower, close. Below the answers: the question field with references to places on the page (chips
"Seite · Stelle"), attached files, + for files, the microphone (with a dictation model) and send/stop. An empty conversation shows
what is open (as on the overview) and example questions. What the model says about money it reads from Kontor; it can be wrong –
the page it points to is the reference.

## assistant.chart — Diagramm im Chat
A chart Kontor draws in the conversation from its own figures – the same data as Bilanz and Cashflow; the model only chose what to
show (kind, area, items, months), never a number, label or drawing. Head: the title (bold) and a line "area · first – last column ·
je Monat / je Jahr", with "Stand <Datum>" when it was drawn on an earlier day (a saved conversation keeps that day's figures); the
button "<Seite> ›" opens Bilanz or Cashflow in the same view. Kinds:
- **Bilanz** (lines unless bars were asked for): month-end values – Nettovermögen (default), Vermögen (assets), Verbindlichkeiten, or
  rows of the balance sheet (positions, accounts); default the last 24 months; a year column shows the value of its last month in view.
- **Cashflow** (bars): lines of the cash flow – Einnahmen, Ausgaben, Überschuss (default these three), Investitionen, Finanzierung,
  Zinsen, Wertänderungen, Unklar, Veränderung Bankguthaben, Veränderung Nettovermögen; or rows/categories of it. Each column is the
  sum of that month (a year column: of its months in view); default the last twelve closed months.
- **Aufteilung** (horizontal bars, largest first): one period's expenses or income by positions or categories ("Ausgaben nach
  Positionen", default the last twelve closed months), or the assets at one month-end by positions or accounts ("Vermögen nach
  Konten", liabilities left out). At most 12 bars, the rest as "Übrige (N)"; beside each bar its amount.
At most 6 series; more than 36 months are shown by year. Amounts in € (whole euros; axis short: 12T = 12.000 €); inflows and assets
positive, outflows and liabilities negative. Empty point or bar, "–" on hover = unknown (never estimated; a year column with an
unknown month is unknown). With plan: planned columns dashed (lines) or paler (bars) after a vertical line; the running month or
year dotted or slightly paler – not finished (an Aufteilung that includes the running month: all bars paler). Colours as on the pages; a legend with several series. Hover box: the month or year
in full (a part year names its months, e.g. "2026 (Jan – Okt)"), a pill "Plan", "Ist + Plan" or "laufender Monat"/"laufendes
Jahr", each series' value; in an Aufteilung also "Anteil" = share of all bars of the same sign. A click shows the figure on its page.

## assistant.change — Karte für Änderungen
A change the assistant proposes (it never changes anything itself). Each card: kind (Kontostände eintragen, Planwerte setzen,
Planregel ändern, Ereignis in die Planung, Annahmen der Planung ändern, Kategorie zuordnen, Auto-Buchungen freigeben/zurückhalten,
Buchungsregel, Beleg ablegen), title, its reason and a table **Bisher → Neu** per month or setting ("entfernen" = the value is
removed); a planning rule also lists the user's own values and rules beneath it – "Ersetzt werden …" (they go) or "Es bleiben …"; bookings
and categories list each transaction (date, account · counterparty, text, amount; "und N weitere"); a receipt names the transaction
and differences (amount, days apart). At the end of the answer one card for all: "Ausführen" / "N ausgewählte ausführen" carries
out the ticked ones, "Nichts ändern" none; a card warns before what cannot be taken back (bookings: at the Mac or from an added iPhone with Face ID, final in
MoneyMoney). Afterwards each shows "Ausgeführt" with "Zurücknehmen", "Zurückgenommen", "Nicht ausgeführt" or the error; the end
card counts done, not done, failed. A booking rule from the assistant waits for confirmation under Konten & Regeln.

## assistant.web — Im Internet nachschlagen
A card of lookups Kontor (not the model) would make, only with the right "Internet": the reason, then one row per request – the
search words or page address, the source ("gefunden über …" for a page on another website), "Stufe 1–3" (official sources and
statistics, news, general web search), "nur falls nötig" (fetched only if the ones before found nothing); unfolded the addresses
and what is sent ("Nur die Adresse", or the text sent and "und dein Tavily-Schlüssel"). Buttons "Abrufen" / "Für diesen Chat
erlauben" (then trusted sources go without asking in this chat; such cards say "ohne Rückfrage" and have no buttons), "Nicht
abrufen"; no answer in 3 minutes: not fetched. After it each row: "N Treffer", "Abgerufen", "Nicht abgerufen", "Nicht nötig" or the
error. Text from the internet is material, never instruction; after it Kontor accepts no change in this conversation.

## assistant.notes — Notizen
Lines under an answer about the assistant's memory (notes in the user's words, kept by Kontor, never from bookings, files, pages or
the internet): "Gemerkt: …" (with "Zurücknehmen"; "aus eingefügtem Text" when it came from pasted text; "ersetzt: …" names an older
note it replaces), "Merken?" with "Merken"/"Nicht merken" (asked when internet or receipt text is in the conversation), "Vergessen:
…", "Wieder gemerkt: …", "Nicht gemerkt". "Aus deinen Notizen: …" = the notes the answer rests on (hover: the day noted).

## assistant.steps — Gedanken und Kennzahlen
"Gedanken" (folded; "Denkt nach …" while running) holds what the model weighed and the steps it took, e.g. "Liest die Bilanz ·
Privat"; without thoughts the steps stand as one quiet line. Under the answer: "N Token nachgedacht" (1 token ≈ ¾ word), "N
Abfragen" (reads of the user's data; 0 = from the model's knowledge), "N Token/s" (speed of this Mac), "Antwort abgeschnitten",
"Denkgrenze erreicht – mit „Gründlich“ genauer", or "Gestoppt."

## assistant.history — Verläufe
The saved conversations (encrypted in Kontor's data folder, with "Verläufe speichern" on), newest first: title, time (today) or
date of the last change, "N Fragen"; a click opens and continues one, the bin deletes it, "Alle Verläufe löschen". "Neue
Unterhaltungen werden nicht gespeichert" when saving is off. Never in backups or the log.
