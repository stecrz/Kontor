# cashflow — Cashflow
Where the money of the chosen area went, as a cash flow statement: the table on top (every month, from the actual bookings in
MoneyMoney), the charts below it for one period. The area switch at the top chooses whose figures (a company's own, 100 %). The view
"Monate / Jahre" and the switch "Plan" (on by default: plan months appended, faded and hatched) change only the table's columns;
"Leere Zeilen" also shows rows without any amount. The period above the charts (von–bis, "12 Monate", a year) changes only the
charts, never the table. Amounts are euros of this area; inflows +, outflows −.

## cashflow.table — Tabelle (Kapitalflussrechnung)
Rows: Überschuss (CFO) with Einnahmen and Ausgaben, Investitionen (CFI), Free Cashflow, Finanzierung (CFF), Unklar, Veränderung
Bankguthaben (with Bankguthaben am Anfang/Ende), Umschichtungen, Wertänderungen, Veränderung Nettovermögen (with Nettovermögen am
Anfang/Ende); the rows from Umschichtungen down are a little lighter (from cash to net worth). A row shows only where there is money
in it in some column. Coloured squares before a name: its colour in the charts (cyan Überschuss, yellow Investitionen, magenta
Finanzierung, green Einnahmen, red Ausgaben, beige Umschichtungen, grey-blue Wertänderungen).

Columns: one per month ("Okt 26" = the flows of October 2026); after each December and after the last column a year column "Σ 2026"
= the sum of all months of that year in the table (" · 10 Mon." when fewer than 12) – for the running year this includes the running
month (booked so far) and, with "Plan" on, its plan months: then it is "Ist + Plan" (its tooltip, faded), not a pure actual figure;
with "Plan" off it holds the actual months up to today. The running month is faded (not finished; its heading underlined); plan
months and pure plan years (switch "Plan") faded and hatched, holding the planned values of the page Planung. The month view starts
at the year shown in "‹ ab 2025 ›" (default: the year before the running one); "Jahre": one column per year (sum of its months, the
same rules). The heading of the last month of the charts' period is coloured.

Figures: euros with cents (cents small), flows with sign (+ in, − out, green/red, 0 grey), balances (Anfang/Ende rows) without sign.
A section's row is the sum of the rows under it. The four symbols in the top left cell (levels): Hauptebenen (only the main rows;
Einnahmen and Ausgaben open at first), Überblick (also Einnahmen, Ausgaben and the kinds of investing and financing), Positionen
(also every position, account and loan, Free Cashflow, the start/end rows), Details (also MoneyMoney's categories and the parts of
Umschichtungen). A row with ▸ is closed, ▾ open; a closed row still holds the sum of its parts.

### cashflow.table.operating — Überschuss, Einnahmen, Ausgaben
Überschuss (CFO) = Einnahmen + Ausgaben of the column: income minus expenses of everyday life or business (in companies the
operating cash flow), without investing, repayment and paid interest (those are under Investitionen/Finanzierung); received interest
and dividends count here (position Kapitalerträge). Einnahmen and Ausgaben are each the sum of their positions.

Positions (fixed outline for every area): income Arbeitseinkommen (salary, bonus, profit-related pay, minijob, side earnings from own work), Umsatzerlöse, Rente & Sozialleistungen
(pension, child benefit, parental allowance …; companies: Zuschüsse & Förderungen), Vermietung, Kapitalerträge (interest,
dividends, profit distributions from any company, the user's own GmbH or GbR too – its participation's value falls by it at
the same time, a change in value; capital taken out or paid in is "Einlage/Entnahme"), Unterhalt &
Geschenke (support, pocket money, gifts, inheritance received – no earned income), Erstattungen, Sonstige Einnahmen (e.g. selling
used things privately; "Verkauf" in a company is Umsatzerlöse); expenses
Wareneinkauf, Personal, Betriebskosten, Wohnen (companies: Raumkosten), Lebenshaltung (incl. food and drink at home and eating out,
personal care, furnishings and household appliances – no housing costs), Mobilität, Versicherungen (risk cover and statutory contributions; private pension insurance that builds capital is
Sparen & Anlegen), Gesundheit, Bildung & Betreuung (childcare, school, university, courses; companies: Fortbildung), Freizeit &
Reisen, Objektkosten, Beratung & Gebühren, Steuern, Umsatzsteuer, Unterhalt, Geschenke & Spenden, Auslagen (paid for others and
paid back, e.g. fuel for the user's company – payment and refund in one category cancel out; until refunded the amount stands
there as an expense), Sonstige Ausgaben; a property with its own category has rows "<Objekt> · Miete" and "<Objekt> · Kosten". "(ohne Kategorie)" holds
transactions without a category that Kontor could not estimate (link "Zuordnen"). A position belongs to its section by what it is,
not by the sign of a single booking: a refund in Lebenshaltung makes that position less negative (or positive) inside Ausgaben.
Which MoneyMoney category counts in which position is set under Konten & Regeln → Cashflow-Positionen.

### cashflow.table.category — Kategorie aus MoneyMoney
The deepest rows (level Details): one row per MoneyMoney category inside the position above it, named by its path ("Wohnen ›
Strom"); together they make up the position. Plan columns (switch "Plan"): the category's plan from the page Planung (each category
by its own rule or the position's; they add up to the position) – empty only under a row planned by a property calculation. "ohne Kategorie, geschätzt": transactions without a category in MoneyMoney whose position Kontor
estimated (from the user's earlier categories for the same counterparty or purpose, else from words in name and purpose) – an
estimate, nothing is written into MoneyMoney; link "Zuordnen" to assign them.

### cashflow.table.investing — Investitionen
Investitionen (CFI): buying (−) and selling (+) assets – money leaves the bank account but stays wealth, so it is no expense. Kinds
(rows below it, by the kind of the account the money went to): Immobilien, Wertpapiere & Geldanlagen, Sachwerte, Sonstige Anlagen,
Beteiligungen (money paid into or out of a company of the user, named by the company; "Einlagen & Entnahmen" = a category with
that position in a private area: money into or out of a company Kontor does not keep), Andere Bereiche (contributions to and
withdrawals from another area of the user, named by the area), Gewährte Darlehen (the account; "<account> / Zinsen" = interest
received on a loan granted), Fremdwährung (money moved into an account in another currency), Sparen & Anlegen (saving whose account
is unknown; a company's: "Anlagevermögen & Geldanlagen"). Buying securities into a depot (which has balances only, no bookings) and
selling them back belongs here by a category with the position Sparen & Anlegen: the purchase −, the sale +, the depot's change in
value shows only the prices; a category "Umbuchung" finds no counter-booking there and lands under Unklar. The price and the purchase
costs of a property count here too, also from a category below the property's own (never as the property's costs; a price without
a counter-booking in the property's account goes into no depot: "Anlage ohne Zielkonto"). Under each kind its accounts – or, for saving by a MoneyMoney category, the category ("… → <Konto>" when the user chose
another account for a recipient; "… → kein Konto in MoneyMoney" = money that leaves the wealth Kontor sees). A kind's row is the sum
of its rows. Plan columns: saving by category and loans granted planned like positions; transfers into or out of accounts,
contributions and withdrawals not planned (0).

### cashflow.table.fcf — Free Cashflow
Free Cashflow (FCF) = Überschuss + Investitionen of the column (CFO + CFI): what is left after living and investing; negative = what
had to come from loans or from cash. Shown from the level "Positionen".

### cashflow.table.financing — Finanzierung
Finanzierung (CFF): payments to and from lenders and partners. Kinds: Darlehensaufnahme (+, a loan paid out – never a "negative
repayment"), Tilgung (−, repayment), Zinsen (−, interest paid – costs net worth, unlike repayment), Einlagen & Entnahmen der
Gesellschafter (companies). Under each kind the loan accounts by name; "Nach Kategorie" = repayment or interest booked by a
MoneyMoney category beside the loans (money in under a repayment category counts as Darlehensaufnahme, "Nach Kategorie"); "<area>:
<account>" = a payment between two areas booked against a capital or loan account. Einlagen & Entnahmen der Gesellschafter also holds
payments of a category with the position "Einlagen & Entnahmen" (partners outside the user's areas).

### cashflow.table.unclear — Unklar
Bookings Kontor could not place, with their amount (they count in Veränderung Bankguthaben and Veränderung Nettovermögen), grouped
as "Umbuchung" and "Konto ohne Position": "Umbuchung mit <Konto>" (a transfer with an account it cannot place), "Umbuchung mit
<Konto> ohne Gegenbuchung" (the counter-booking in that account of the area is missing), "Umbuchung ohne erkanntes Gegenkonto"
(category Umbuchung, no counterpart found), "<Konto> (Position unbekannt)" (an account without a balance-sheet position). At the
levels Hauptebenen and Überblick only its sum. Not planned (plan columns 0).

### cashflow.table.cash — Veränderung Bankguthaben
Veränderung Bankguthaben = Überschuss + Investitionen + Finanzierung + Unklar of the column: by how much the cash (Bankguthaben: the
sum of the liquid accounts, money in transit over a month end included) is higher (+) or lower (−) at the end than at the start. ✱
at a figure: the balance sheet differs in a month of that column (see the row "Abgleich mit der Bilanz"). Opened (level Positionen):
"Bankguthaben am Anfang" = cash at the end of the month before the column's first month; "Bankguthaben am Ende" = cash at the end of
its last month (running month: today; plan months: planned = previous + planned change). Both as in the balance sheet's position
Bankguthaben, without sign; empty before the first month of data. Anfang + Veränderung (+ the check's difference, if any) = Ende.

### cashflow.table.check — Abgleich mit der Bilanz
Shown only where a month differs: inside Veränderung Bankguthaben (difference of cash) and inside Veränderung Nettovermögen
(difference of net worth), before the end row. Each cell: what the balance sheet shows more (+) or less (−) than the cash flow
explains, summed over the column's actual months (cash: change of the liquid accounts − Veränderung Bankguthaben; net worth: change
of net worth − Veränderung Nettovermögen). "✓" = that column adds up to the cent; empty = plan or the first month of data. Muted,
dotted: a known cause (tooltip), e.g. "Kategorie „Nicht berücksichtigen“", "Geld in Transit über das Monatsende", "Korrektur
Kontostand <Konto>", "Anfangssaldo <Konto>", "Wertänderung <Konto>"; yellow, bold: no known cause ("Ohne erkannte Ursache",
"Kontostand unbekannt: <Konten>"). The ✱ on the total row points to it.

### cashflow.table.moves — Umschichtungen
Money that left (or entered) the bank accounts but stays wealth: investing, repaying a loan, a loan taken up – added back here with
the opposite sign (investing −1.000 € → Umschichtungen +1.000 €; a loan paid out +10.000 € → −10.000 €). Veränderung Bankguthaben +
Umschichtungen + Wertänderungen = Veränderung Nettovermögen. Opened (level Details): one row per kind (e.g. Wertpapiere &
Geldanlagen, Tilgung, Darlehensaufnahme).

### cashflow.table.valuation — Wertänderungen
Changes of net worth without a payment: prices of portfolios (change of the depot's value minus what was paid in), balance
corrections of accounts kept by balances ("<Konto> / Korrektur Kontostand"), bookings of non-bank accounts without a category (with a category for income or an expense they count in its position and
the account's other side stands under Investitionen/Finanzierung: "<Konto> / Rückzahlung", "<Konto> / Tilgung", "<Konto> / Aufnahme" for a bill booked as owed, or the asset's row), the value of a
participation beyond the money paid in, "Anfangssaldo <Konto>" (an account starting with a balance), "Anlage ohne Zielkonto" (saving
whose account is unknown – it offsets the rise of the depot it went into; link "Ziel festlegen"), "Darlehen ohne Konto" (a loan
taken up or repaid by category: its debt is in none of the user's accounts, so the net worth Kontor sees moves by that amount). One row per account; a depot
with no balance known before some month has a second row "<Depot> / bis <Monat> unbekannt": up to that month its first known
balance stands carried back, so what is there is only what was paid in or out (with the sign turned), no real change in value. In plan
columns the total also holds the planned changes in value that have no row of their own (Wertentwicklung je Konto, participations
linked to another area, values of property calculations) – so there the rows need not add up to it.

### cashflow.table.networth — Veränderung Nettovermögen
Veränderung Nettovermögen = everything that changed net worth in the column: Überschuss, interest, contributions and withdrawals,
Wertänderungen, Unklar – not investing, repaying or taking up loans (they only move money between accounts). Equals Veränderung
Bankguthaben + Umschichtungen + Wertänderungen. ✱: differs from the balance sheet in a month of the column. Opened: "Nettovermögen
am Anfang" (end of the month before the column) and "Nettovermögen am Ende" (end of its last month; plan: projected), as in the
balance sheet, without sign; Anfang + Veränderung (+ check) = Ende.

## cashflow.charts — Diagramme (Zeitraum)
All charts show one period, chosen in the row above them: von–bis (two month buttons; ‹ › shift it by a month), presets "12 Monate"
(default: the last twelve closed months), the running year (its closed months) and the two years before. The running month is not in
the presets (half booked); a period may reach into it and, with the plan on, into plan months – those months are hatched (where a
chart has bars or cells) and count with booked-so-far resp. planned values. Comparison ("Vorjahr", "Vorperiode"): the same months
one year earlier; for a period longer than twelve months whole years further back (13–24 months: two years); only where all those
months are in the data – otherwise no change is shown. Colours: green inflow/income, red outflow/expenses; cyan Überschuss, yellow
Investitionen, magenta Finanzierung, grey unclear/totals. A change is green or red only for income and expenses (more income, less
expense: green); investing, financing, interest and values without judgement. The hover box names exact amounts. "Keine Zahlungen in
diesem Zeitraum." = no flows in the period. Charts need at least two closed months; their order is the user's (↑ ↓).

A percentage beside an amount is always the change of that amount (of the chosen period) against the comparison period – never a
share, except where named "Anteil" or inside the ring. In the bridges amounts keep their sign, and while the sign stays the same the
percentage is the change of the size: −22.000 € against −21.000 € = "+4,8 %" (the outflow or loss grew by 4,8 %), −20.000 € against
−21.000 € = "−4,8 %" (it shrank), +22.000 € against +21.000 € = "+4,8 %"; when the sign flipped, the change of the signed amount
measured against the earlier size (+1.000 € against −500 € = "+300 %", −1.000 € against +500 € = "−300 %"). The ring, the heatmap
and the Gesamtcashflow show amounts positive (expenses too): "+" = larger, "−" = smaller. No percentage when the comparison amount
is 0 (or the change is 100.000 % and more); "±0 %" = the same amount (to 50 cents).

## cashflow.bridge — Liquiditätsbrücke
A waterfall from the cash at the start of the period to the cash at its end. Rows: "Anfangsbestand" (cash at the end of the month
before the period, grey), then the steps – Einnahmen, Ausgaben, each kind of investing and financing, Unklar, "Abgleich Bilanz"
(what the balance sheet shows beyond the payments, only if ≥ 0,50 €) – then "Endbestand" (cash at the end of the last month;
"(Plan)" when that month is planned). Unknown start: no Anfangsbestand, the last row is "Veränderung Bankguthaben". Each bar starts
where the one before ended (green in, red out; dashed lines join them). A coloured bracket over rows is no step: it spans its parts
and stands for their sum (Überschuss cyan, Investitionen yellow, Finanzierung magenta; deeper levels grey). ▸ opens a row into its
positions, then categories (at most eight parts; the smaller ones together as "Übrige (n)"), ▾ closes it.

Right: the amount in whole euros (+ for an inflow step, totals without sign) and its change against the comparison period, short
("+12%", "−5%", from 1000 % "+2T%"; none when the comparison is 0 or unknown; none for totals, Unklar, Abgleich) – for an outflow
the change of its size: Ausgaben −30.000 against −25.000 = "+20%" (more spent, red). Hover on the amount or change: Betrag, Vorjahr
(amount of the comparison period), Veränderung and the parts. The axis on top is an amount scale; a dragged range zooms in (bars cut
at the edge marked with two strokes; "Ganze Brücke" shows all). Amounts are sums over the period.

## cashflow.months — Monatlicher Cashflow
Upper part, one column per month of the period (more than 36 months: per year, a partial year faded): stacked bars from the zero
line – inflows up, outflows down, by kind: Einnahmen (green), Ausgaben (red), Investitionen (yellow), Finanzierung (magenta), Unklar
(grey); each kind with the sign of its month's total. A short dashed line marks the month's result, Veränderung Bankguthaben
(missing when close to zero or cut). Lower part, on its own scale ("Veränderung Nettovermögen"): the same months split into
Bankguthaben (= Veränderung Bankguthaben, grey), Umschichtungen (beige) and Wertänderungen (grey-blue), stacked; its dashed line is
Veränderung Nettovermögen. The scale labels are amounts per month ("+20T" = +20.000 €). When a few months are far larger than most
(over three times the upper quartile), the scale follows the rest: those bars are cut, marked with two strokes and labelled with the
full height of the cut stack – above the upper part "+11,6T" = the sum of all upward parts of that month (all inflows), below it
"−50T" = the sum of all downward parts (all outflows); at the lower part likewise the sum of its positive resp. negative parts
(Bankguthaben, Umschichtungen, Wertänderungen) – never the month's result (Veränderung Bankguthaben or Nettovermögen, which only the
hover box gives then). A highlighted scale has been zoomed by hand. Running and plan months: hatched background. Hover over a month:
Einnahmen, Ausgaben, Investitionen, Finanzierung, Unklar (rows of 0 left out), "= Veränderung Bankguthaben"; then Bankguthaben,
Umschichtungen, Wertänderungen, "= Veränderung Nettovermögen" – all flows of that month (or year) in euros.

## cashflow.wealth — Vermögensbrücke
A waterfall like the Liquiditätsbrücke, but from net worth at the start ("Anfangsvermögen": end of the month before the period) to
net worth at the end ("Endvermögen", "(Plan)" if planned), with only what changes net worth: Überschuss (Einnahmen, Ausgaben),
Zinsen (paid and received interest – under Finanzierung/Investitionen in the table, but they cost or bring net worth), "Einlagen &
Entnahmen" (money between this area and others, money out of the wealth Kontor sees), Wertänderungen (per account; plan months also
"Wertentwicklung laut Plan"), Unklar, "Abgleich Bilanz" (what the balance sheet shows beyond these rows, e.g. an unknown balance).
Investing, repaying and taking up loans are missing: they only move money between the user's accounts. All rows start closed; ▸
opens positions, accounts, categories. Colours of the brackets: Überschuss cyan, Wertänderungen grey-blue, Zinsen and Einlagen grey.
Right: sum over the period and change against the comparison period (coloured only within Überschuss), read as in the bridge – e.g.
Wertänderungen −22.000 against −21.000 = "+4,8%": the loss grew. Hover as in the bridge.

## cashflow.flow — Gesamtcashflow
Sankey diagram of the sources and uses of money in the period. Left everything that came in: income positions, Darlehensaufnahme,
sales of assets, "Weniger Bankguthaben" (cash went down); right what it went to: expense positions, investments, Tilgung, Zinsen,
"Mehr Bankguthaben" (cash went up); also Unklar and "Abgleich mit der Bilanz" on the side of their sign. An item is placed by the
sign of its sum over the period. Both sides add up to the same total – shown above the middle in euros: everything that came in
during the period (with "Weniger Bankguthaben" if cash fell) = everything it went to; above it the period and its length ("Nov 25 –
Okt 26 · 1 Jahr"; little room: only the length). Each band is as wide as its amount; bands of at least 5 % carry their share of the
total ("12 %"). Flows under 3 % stand together as "Übrige (n)". The names carry short amounts ("17,4T" = 17.400 €); ▸ opens an item
into its parts (categories, accounts), "▾ <Name>" closes them. The bands meet in the middle on purpose: money has no label, so no
source is tied to a use. Hover: Betrag, Anteil (of the total), Vorperiode (the item's amount on the same side in the comparison
period; 0 if it was not there), Veränderung, and its parts.

## cashflow.ring — Vorjahresvergleich der Ausgaben (Ring)
The expenses of the period by position as a ring (switch "Ausgaben / Einnahmen": income, then green); title "Vorjahresvergleich der
Ausgaben", "… im Vergleich zu 2 Jahren davor" for longer periods, "Zusammensetzung der Ausgaben" when the comparison period is not
in the data (no changes then). Positions in order of size, darker = larger; more than seven: the six largest and "Übrige (n)"
(grey). Only positions whose sum points the normal way are slices; positions with the opposite sum (e.g. more refunds than costs)
are "Gegenposten (nicht im Ring)".

Beside each slice: the position's name, then its amount = its sum over the chosen period in euros, shown positive (expenses too),
and after it a percentage = the change of that amount against the comparison period (the same months a year before), not a share:
"+12 %" = 12 % more than then, "±0 %" = the same amount, "+10T %" ≈ +10.000 %; red when expenses rose (income: when it fell), green
the other way; none when the comparison is 0 or unknown. "Übrige" shows a change only when each position in it had an amount then.
Inside a slice (where it fits): its share of the ring (all slices = 100 %).

Middle: the length of the period ("1 Jahr"), the total of the section in euros (Gegenposten included, so the slices can add up to
more) and its change against the comparison period. Hover the middle: the period with its amount, Gegenposten, the comparison period
with its amount, and Veränderung as euros and percent. Hover a slice: Betrag, Anteil, Vorperiode (its amount then), Veränderung, its
three largest categories (+ "Übrige") with amount and change – and an outer ring shows them.

### cashflow.ring.pinned — Ring mit offenem Stück (Kategorien)
A slice kept open by a click: the other slices faded; the middle shows that position – its name, its amount over the period and its
change against the comparison period. Around the ring stand its categories instead of the positions: the three largest (colour dots
like the outer ring) and "Übrige (n)" for the rest, each with its amount over the period and its change against the same months of
the comparison period – its hover box: "<Position> › <Kategorie>", Betrag, "Anteil an <Position>" (share of the position, not of
all expenses), Vorperiode, Veränderung. Category names are the last two levels of the MoneyMoney path; "ohne Kategorie, geschätzt" = transactions
without a category whose position Kontor estimated; "laut Plan" = the part of plan months planned without categories (a property calculation). For
the slice "Übrige" its positions stand there instead.

## cashflow.heatmap — Ausgaben je Monat
One strip per position – at most ten: the largest of the period by sum, "(ohne Kategorie)" always last; smaller positions and
positions with no net expense in the period have no strip – one cell per month of the period (more than 24 months: per quarter,
title "… je Quartal"; a partial quarter striped). Mode "Beträge" (default): the darker the cell, the larger that position's expenses
in that month; one scale for all strips, so a large position stands out against a small one. The scale follows the usual months (up
to three times the upper quartile): the highest of them gets the strongest colour; outliers above it get it too, a frame and their
rounded amount in the cell ("12T"), or ▲, ▲▲, ▲▲▲ when the cell is too narrow (beyond 1×, 3×, 10× the scale's end). Empty grey:
nothing. Running and plan months hatched (plan values). Right column "Ø": the strip's average per month over the period (its sum ÷
number of months of the period – per month also when the cells are quarters), short ("1,2T" = 1.200 €). Hover a cell: Ausgaben (the
amount of that month), Vorjahr = the same month one year earlier with its change in percent (always 12 months back, unlike the
ring's comparison for periods over a year; missing when that month is not in the data), the categories that made it up (largest
first, "Übrige"). The switch "Ausgaben / Einnahmen" beside the ring turns both to income (green). The strips need not add up to the
row "Ausgaben gesamt" (it holds every position).

### cashflow.heatmap.change — ± Vorjahr
Mode "± Vorjahr": each cell shows the change of that month's amount against the same month one year earlier, in percent – green
better (less expense, more income), red worse, the stronger the more; grey = ±0 %. The colour scale ends at most at 100 % (lower
when the usual changes are smaller); beyond it: strongest colour, a frame and the change in whole percent ("+140%", "+1,5T%"), or
▲/▼ marks when narrow. ✦ = new: nothing a year before, something now (strongest colour, no frame). An empty frame = the year before
is not in the data – and the running and plan months (hatched), which are not compared. Right column "±": the change of the whole
period against the year before, over the months whose year before is known ("✦" if there was nothing then). The hover box stays as
in "Beträge" (amount and year before); cells within the scale carry no number.

### cashflow.heatmap.total — Ausgaben gesamt
The last row, below a line: all expense positions of the area together per month (every position, also those without a strip of
their own, refunds netted), on its own scale – it is always far larger than a single position. Its right cell: average per month
(mode "Beträge") or the change of the whole period (mode "± Vorjahr"). Hover: its amount, the same month a year before with the
change, and the positions that made it up. With "Einnahmen": "Einnahmen gesamt".
