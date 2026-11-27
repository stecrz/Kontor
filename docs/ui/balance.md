# balance — Bilanz
The balance sheet of the chosen area: what it owns and owes, by position and account, as **month-end balances** (the running
month: today's balance) – stocks, never flows. From the top: the large chart (balance.chart), the table (balance.table) and three
small charts (balance.lines); table and large chart can be moved, any small chart can become the large one. "Monate" / "Jahre"
(balance.toolbar) applies to table and charts together. The balance sheet always includes the plan: plan months follow the
running month at the right (faded and hatched in the table, dashed and shaded in the charts) – values Kontor projects from
Planung, not actual balances. The area switch at the top: a company area shows the company's own accounts (100 %); the private
area holds a company as its participation account (share × the company's net worth).

## balance.toolbar — Monate / Jahre
"Monate": one table column per month – the running year and the one before; "‹ ab 2025 ›" names the first year shown (earlier
years one at a time); no year columns (a year would only repeat December), a thin line before each January. "Jahre": one column
per year, each the balance at the year end; a year with fewer than twelve months in the data is labelled e.g. "2024 · 7 Mon.".
The running year's column ("2026", faded, tooltip "Ist + Plan") holds its actual and its plan months and shows the last of them
with a value – with a plan to December the planned December balance, not today's; plan years (hatched) their planned December.
The charts plot month ends in both views; only their range buttons differ (months: 6 M, 1 J, 2 J, 3 J; years: 1 J, 3 J, 5 J,
10 J). "Excel": the table as a spreadsheet.

### balance.toolbar.view — Ansicht speichern
"Ansicht speichern" keeps the current view on this device, one for months and one for years: the charts' ranges (as their length,
always ending with the last closed month), opened rows, the eye, the width of the first column, the order of table and charts,
which chart is large, the choices in the charts, "Plan" and "An Tabelle ausrichten". The view saved last opens at the start.
"Ansicht zurücksetzen" returns to Kontor's default. Neither changes a figure or the area.

## balance.chart — Große Grafik
The large chart above the table. By default the balance sheet itself (balance.bil); after ⤢ on a small chart it shows that one
(balance.nw, balance.sel, balance.pos) and the balance sheet becomes a small chart below.
Head: the range shown ("Oktober 2025 – Februar 2027": first and last month end; aligned with the table: the columns in view).
Range buttons and the field "12 M" = the number of months up to the last closed month, month end to month end ("1 J" in November:
October a year before to October – a change covers exactly twelve closed months). As the balance sheet it also shows about a
third of the range ahead – the running month and plan months; "Plan" switches that off. "An Tabelle ausrichten": every value
stands right above its table column (also year columns), no hover box then.
Plot: amount axis at the left ("Tsd." = thousand, "Mio." = million; at least five lines), months at the bottom (first and last
always labelled; a thin line at each new year). Closed months solid; a dashed vertical line marks the end of the last closed
month; the running month lies under a soft veil (its line dotted, a dot on its value), the plan under a darker shade with dashed
lines. Hover box: the month ("Oktober 2026", with "Plan" or "laufender Monat" where so), the values of that month end of each
series and of the line.

## balance.bil — Bilanz (Grafik)
The balance sheet as a stacked area chart: each position (colours as in the table) at each month end; positive positions stacked
upwards from zero, negative ones (Verbindlichkeiten, a position below zero) downwards. Order of the layers (above and below
zero each): what is there longest and moves least lies next to zero, what comes later, ends, changes sign or changes visibly lies
outside – so a new loan is added below the old one, which keeps its edges; a position's accounts (a portfolio's securities) stay
together; where nothing of this differs, the last position of the table lies next to zero. The whole period counts, so zooming
never reorders; the hover box keeps the table's order.
The gold line is the net worth – the upper stack minus the lower one. As the large chart: a position opened in the table shows
its accounts in shades of its colour (from the eleventh account hatched), an opened portfolio its securities; the area under the
pointer and its row in the hover box are marked. As a small chart (when another one is large): positions only, a legend below.
Hover box: each position (or account, security) with its balance at that month end, last "Nettovermögen". This chart shows no
value and no change (the net worth chart does).

## balance.value — Wert und Veränderung
The value row of a chart (Nettovermögen, Auswahl, Zusammensetzung – small, or above the plot when large): "62.533 €" = the value
at the end of the last actual month in view (normally the last closed month; the running month when moved into view); "+15.860 €
(+34 %)" = the change since the first month end in view (the start of the chosen range), in € and in percent of that start
(green up, red down; no percentage from a start near zero; "+12T %" = about +12,000 %). In a small chart "1 Jahr" at the right,
below the range buttons, is the length of the range that value and change refer to. Plan months never count here.

## balance.nw — Nettovermögen (Grafik)
Net worth of the area alone (the table's row Nettovermögen) at each month end: a gold line with the area down to zero (upwards
when negative). The amount axis fits the values in view, so small changes show too. Hover box: just the month and the value.
Value and change: balance.value.

### balance.nw.stats — Ø je Monat, Höchststand, Tiefststand
Below the net worth chart, for the actual months in view: "Ø je Monat" = the average change of net worth per month (last value
minus first, divided by the months between them; green up, red down) – not an income or a saving; "Höchststand" and
"Tiefststand" = the highest and the lowest net worth at a month end in that range, with its month below.

## balance.sel — Auswahl
The sum of freely chosen positions at each month end (checkboxes below; default Bankguthaben, Wertpapiere and Festanlagen =
"Geldanlagen"), one line in the mixed colour of the chosen positions. The title names the choice in words: one position by its
name, all of them as "Nettovermögen", typical combinations by their name, otherwise "A + B" or "Nettovermögen ohne
Beteiligungen" (shortened words in the small chart). The title's hover box spells out the names (only positions the area has):
Bankguthaben + Wertpapiere = Liquides Vermögen; + Festanlagen = Geldanlagen; + Beteiligungen + Forderungen = Geldvermögen;
+ Sachvermögen (Immobilien + Sachwerte) + Sonstiges = Bruttovermögen; + Verbindlichkeiten = Nettovermögen; Gebundenes Vermögen =
Bruttovermögen − Liquides Vermögen. Hover box of a month: each chosen position's balance and "Summe". "keine Position gewählt": no
box ticked. Value and change: balance.value.

## balance.pos — Zusammensetzung
One position (chosen in the menu in the head; default Bankguthaben when it has several accounts) split into its accounts, stacked
in the account colours of the table, ordered as in balance.bil (later and changing ones outside); the line is always the whole position. "Depot" (only where the
position holds a portfolio): portfolios split into their securities instead. Below, each account or security with a value in the
range can be unticked – the line stays the whole position. Hover box: the month, each account's (security's) balance, "Auswahl" =
the sum of the ticked ones (only when some are unticked), last the position's total. Value and change: balance.value.

## balance.lines — Einzelne Grafiken
The small charts below the table: three of Nettovermögen (balance.nw), Auswahl (balance.sel), Zusammensetzung (balance.pos) and
Bilanz (balance.bil) – whichever is not the large chart. Each has its own range (buttons at the top right: months view 6 M, 1 J,
2 J; years view 1 J, 3 J, 10 J; default 1 J resp. 3 J, ending with the last closed month, month end to month end) and its own
amount axis fitted to the values in view (at least four lines). Closed months solid, the running month dotted under a soft veil,
plan months dashed and shaded – only when moved into view; a dashed vertical line marks the end of the last closed month.

## balance.table — Tabelle
One row per position, with its accounts below when opened; one column per month or year (balance.toolbar), then the plan. Every
value is a balance at the end of that month, in € with the cents set smaller – no flows. Kinds of columns: a closed month
("Okt 26" = October 2026, tooltip "Ist"); the running month ("Nov 26", faded) = today's balance, the month is not over; plan
months ("Dez 26" …, faded and hatched, tooltip "Plan") = Kontor's projection from Planung, not a balance. Years view: a year's
year-end balance; the running year (faded, "Ist + Plan") its last month with a value – with a plan that is the planned December;
plan years (hatched) their planned December. Green positive (assets), red negative (debts); "–" = no balance that month (e.g.
before an account's first booking).
Header cell "Position / Konto": ▸ opens all positions; the eye with a number shows empty and hidden accounts and securities –
they count in every sum anyway. Rows: positions (balance.table.pos) with their accounts (balance.table.account), portfolios with
their securities (balance.table.security), Geldtransit (balance.table.transit), the plan's contributions
(balance.table.contributions), Nettovermögen (balance.table.nw) with the equity ratio (balance.table.ekq), then what is outside
net worth (balance.table.outside).

### balance.table.pos — Position
A balance sheet position (Bankguthaben, Wertpapiere, Festanlagen, Immobilien, Beteiligungen, Sachwerte, Forderungen, Sonstiges,
Verbindlichkeiten) with its colour dot: each value is the sum of all its accounts at that month end – hidden and empty ones
included. "(2)" = its number of accounts; "(9/12)" = 9 of 12 shown, the others empty or hidden but counted. A position with
nothing in the columns shown is left out (unless the eye is on). Bankguthaben includes the money in transit. Plan columns: Bankguthaben from the
planned cash flow, the other positions from their accounts' planned values.

### balance.table.account — Konto
One account of the position (in MoneyMoney's order), its dot in the shade used for it in the charts. Values: its balance at each
month end – computed from MoneyMoney (today's balance minus all later bookings) or, set per account, from entered balances
(drawer.hist). Tags: "manuell" = an offline account in MoneyMoney; "ausgeblendet" = hidden or empty in all columns shown (listed
only with the eye); "vor Nov 26 unbekannt" (yellow, portfolios) = no balance known before that month – the months before show
the first known value carried backwards (flat), not real balances – how the value changed before that month is not known,
the flat line there is no "unchanged". A portfolio has ▸ for its securities and their number ("(3)", "(2/3)" = 2 of 3 shown).
Plan columns: the account's planned values from Planung where it has some; accounts of Bankguthaben have none (the position
takes the planned cash).

### balance.table.security — Wertpapier
A security of an opened portfolio: its value at each month end – past months from MoneyMoney's history or Kontor's monthly
record, the running month from MoneyMoney; no plan. Its hover text: MoneyMoney's name and the ISIN, and whether the name was
looked up or changed in Kontor. "Übrige (nicht aufgeschlüsselt)" (grey) = the part of the portfolio's value no known security
explains (e.g. cash in the portfolio). The portfolio's row above is the total.

### balance.table.transit — Geldtransit
Money between two of the area's own accounts over a month end: debited from one account in the old month, credited to the other
only in the new one (or the other way round). Its value at a month end is the amount under way then; it counts to Bankguthaben
(and so to net worth), so net worth does not seem to dip for a few days. The pairs are the transfers the cash flow recognises
(counter IBAN, category "Umbuchung", Kontor's marks; equal amount, a few days apart); 0 when nothing was under way. The transfers themselves: drawer.transit.

### balance.table.contributions — Einlagen/Entnahmen Beteiligungen (kumuliert, Plan)
Only with plan columns, below the participations: the contributions to and withdrawals from companies the plan expects, added up
from the first plan month (cumulative, not per month). Part of the planned net worth, not of the position's row above; actual
columns show "–".

### balance.table.nw — Nettovermögen
The net worth of the area at each month end: the sum of all positions above (assets minus debts); its gold mark stands for the
gold line in the charts. Plan columns: the planned net worth. The rows below it (guarantees, foreign currency) are not in it.
▸ before it (only where Kontor has the equity ratio) opens the key figures (balance.table.ekq).

### balance.table.ekq — Eigenkapitalquote (Alpha)
Share of the assets that belongs to the owner free of debt, looking through the companies: equity ÷ (equity + debts), one
decimal ("45,3 %"). Equity = net worth (in a company area plus the partners' capital and shareholder accounts). Debts = accounts
with a negative balance – not participations, not capital or shareholder accounts – plus, for each company linked to a
participation under booking rules, its debts × the area's share. Per column the figure of its last month with data; none in
plan columns. "?" = unknown (accounts of a linked company lie in no area). The calculation of a month: drawer.ekq.

### balance.table.outside — Nicht im Nettovermögen
Below the net worth, tagged "nicht im Nettovermögen", one foldable row per kind with its number of accounts: "Avale &
Bürgschaften" (guarantees) with their sum at each month end; "Fremdwährung (nicht umgerechnet)" – accounts in another currency,
never converted, so no sum ("–"). Opened: each account's balance at the month end, foreign ones in their own currency (tag with
the currency). None of it counts in net worth or in a position.
