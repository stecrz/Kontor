# overview — Übersicht
The start page: the most important charts of the chosen area at a glance – no tables, no plan values, no months/years switch.
Every card counts only **closed months** (the running month is left out); "12 Monate" and the periods named on the cards
("Nov 25 – Okt 26") are the last twelve closed months. Only the area switch at the top changes the figures (a company area:
the company's own accounts, 100 %). On a wide Mac window the cards stand in three columns on one screen, on a narrow window or
the iPhone one below the other – the figures are the same. The same figures in detail: Nettovermögen in the large chart of
Bilanz, Vermögensstruktur and Vermögensaufbau in the balance sheet table, Vermögensbrücke and Monatlicher Cashflow in their
charts in Cashflow (period: the last 12 months).

## overview.nw — Nettovermögen
Net worth of the area at each month end over the last twelve closed months: 13 points – the month end a year before the last
closed month and the twelve after it – as a gold line over a pale area, straight lines between the month ends; a dot marks the
last value. No running month, no plan. Left axis: amounts (T = thousand, M = million), fitted to the values shown; bottom:
first, middle and last month ("Okt 25", "Apr 26", "Okt 26" = October 2026). Net worth = all balances of the area that count in
net worth, assets minus debts (Bilanz, row Nettovermögen).
Hover box of a month: the month ("Oktober 2026"); "Nettovermögen" = net worth at that month end; "ggü. Vormonat" = change
against the month end before (from the second point on); "ggü. Vorjahr" = change against the same month end a year before
(only the last point has one). "Noch zu wenige Monate für einen Verlauf": fewer than two closed months known.

### overview.nw.head — Kopfzahl Nettovermögen
The large amount ("62.533 €"): net worth at the end of the last closed month, named beside it ("Okt 26"). "12 Monate +15.860 €":
the change of net worth over these twelve months – that month end minus the same month end a year before (green: it rose,
red: it fell); a change of wealth, not an income. Missing when fewer than 13 month ends are known. The same change as at the
top of Vermögensbrücke.

## overview.comp — Vermögensstruktur
What the area's wealth consists of at the end of the last closed month, as a balance sheet in two halves of equal size (both
add up to the same total). Left, "Vermögen" (overview.comp.assets): every position with a positive value as a tile, its area
proportional to its amount. Right, "Finanziert durch" (overview.comp.funding): net worth and the debts on the same scale – so
the share of net worth (roughly the equity ratio) shows at a glance. Guarantees and accounts outside net worth are left out.
Each tile: name; amount, short ("420T €" = 420,000 €); below it the change against the same month end a year before in percent
("±0,0 %" unchanged, "−2,3 %") – only where every account in it had a known balance a year before; no percentage when there is
nothing to compare (new, unknown, about 0 a year before). Green = better (assets up, debts down), red = worse. Long names are
shortened, small tiles show no text.
Hover box of a tile: its name; the amount at the last closed month end ("Okt 26: 420.000 €"); the amount a year before
("Okt 25: …" or "unbekannt") with the change in percent; "Anteil 23 %" = its share of the whole (the gross assets, or the debts
when they are larger) – a share, not a change.

### overview.comp.head — Kopfzahl Vermögensstruktur
The large amount: the gross assets – the sum of all positions with a positive value at the end of the last closed month, and of
loan accounts in credit (the left half), before debts; "Vermögen Okt 26" names that month. "± Vorjahr": the tiles show the change against the same month a
year before. Not net worth (that is the gold tile at the right) and, for a company, not its balance sheet total: stock, open
invoices, provisions and the like that are on no account are missing (its tooltip says so). A position worth less than zero
(e.g. participations below zero) is not in it – it stands at the right with the debts.

### overview.comp.assets — Vermögen
The left half: the positions with a positive value (Bankguthaben, Wertpapiere, Festanlagen, Immobilien, Beteiligungen,
Sachwerte, Forderungen, Sonstiges), each as a tile in its position colour as in Bilanz, the largest first. Amount = the sum of the
position's accounts at the end of the last closed month – the same figure as the position's row in the balance sheet table.
A loan account in credit (overpaid) is no debt: it stands here under its own name. When the debts are larger than the assets,
a grey tile "Nicht gedeckter Fehlbetrag" fills the gap: debts minus assets (a
negative net worth), without a comparison.

### overview.comp.funding — Finanziert durch
The right half: what stands against the assets. "Nettovermögen" (gold) = assets minus debts, shown only when positive; its
percentage compares with the net worth a year before (only if every position was known then). Then each debt account
(position Verbindlichkeiten with a negative balance) as a red tile, the largest first. A position that is no debt but below zero
as a whole (overdrawn Bankguthaben, Beteiligungen worth less than nothing) also stands here, red, under the position's name.
These red tiles show their amount **without a sign** – "301T €" is a debt of 301,000 € (in the balance sheet −301.000), in the
tile and in its hover box. Their percentage is the change of that debt against a year before (only where its balance then is
known): a rise (more debt) red, a fall (repaid) green.

## overview.wealth — Vermögensbrücke
Where the change of net worth over the last twelve closed months came from, as a waterfall: each bar starts where the one
before ended. Rows from the top: "Anfangsvermögen" = net worth at the month end before the twelve months (grey bar from zero);
then only what changes net worth – "Überschuss" (income minus expenses), "Kapitalerträge" (interest and dividends received,
also on a loan given – in the cash flow under investing, DRS 21), "Zinsen" (interest paid, negative), "Einlagen & Entnahmen" (money between the area and others: contributions, withdrawals),
"Wertänderungen" (changes in value without a payment: prices of portfolios, revaluations, participations, balance
corrections), "Unklar" (what Kontor could not place), "Abgleich Bilanz" (what the balance sheet shows beyond these rows, e.g.
an unknown balance); last "Endvermögen" = net worth at the end of the last closed month. Rows without an amount are left out.
Investing and repaying loans are no steps: they only move money between the area's own accounts.
Figures at the right: start and end without sign, each step with its sign (+ raised, − lowered net worth). Bars: green a step
up, red a step down; grey start, end, "Unklar" and "Abgleich Bilanz". Hover box of a step: its largest parts (up to eight –
positions, categories or accounts) and their sum, or the period with the amount. Net worth at the start unknown: no start
row, the last row is "Veränderung Nettovermögen" (the sum of the steps). The same bridge for any period: Cashflow.

### overview.wealth.head — Zeitraum Vermögensbrücke
"Nov 25 – Okt 26": the twelve closed months of the bridge, both included; the start is the net worth at the end of the month
before the first one. "+15.860 €": Endvermögen minus Anfangsvermögen – the change of net worth in these months (green up,
red down); the same figure as "12 Monate" on the card Nettovermögen. Missing when the start is not known.

## overview.months — Monatlicher Cashflow
The payments of the last twelve closed months, one column per month: money in upwards, money out downwards, stacked by kind –
Einnahmen (income), Ausgaben (expenses), Investitionen (investing: buying assets down, selling up), Finanzierung (financing:
loans taken up and contributions up; repayment, interest paid, withdrawals down) and, grey, Unklar (named in the legend when there is any).
Colours as in the legend below the chart. The short dashed stroke on a column = the change in cash of that month (Veränderung
Bankguthaben: the sum of all parts, money in minus money out); missing when it lies close to the zero line. Left axis: amounts
per month (T = thousand). If a few months are far larger than the rest (e.g. a property purchase), the axis follows the others
and those columns are cut, marked with a slanted stroke. Labels: first, middle and last month.
Hover box of a month: the month, each part with its sign (Einnahmen, Ausgaben, Investitionen, Finanzierung, Unklar) and
"= Veränderung Bankguthaben". Transfers between the area's own accounts are no payments; changes in value (prices) are not in
this chart. It is the upper part of the monthly chart in Cashflow.

### overview.months.head — Kopfzahl Monatlicher Cashflow
"Bankguthaben 12 Monate +8.660 €": the change of the bank balances over all twelve closed months shown together – the sum of the
twelve monthly changes (the dashed strokes), not a figure per month; green: the bank balances rose, red: they fell. Not a
surplus: investing and financing are in it.

## overview.build — Vermögensaufbau
For each building block of the area's wealth: what it is worth and how it changed in the twelve closed months named at the top
("Nov 25 – Okt 26": from the month end before the first of them to the end of the last, as in the bridge). Blocks, each with
its own place: Beteiligungen, Immobilien or "Immobilien nach Darlehen", Liquidität & Anlagen, Schulden or "Übrige Schulden" –
only those with a balance at the start or the end.
Each row: coloured mark and name; at the right, large, the **change** of the block over these twelve months in € – the sum of its
accounts at the end minus at the start ("±0 €" unchanged; green up, red down) – or "unbekannt"; it is not the block's value. A
bar from the middle line, to the right for a rise, to the left for a fall, its length relative to the largest change of all
blocks. The small line below starts with the block's **value** (balance at the end of the last closed month, e.g. "420.000 €")
and then tells how the change splits: "Geldfluss" = money that went in or out (contributions, purchases, saving,
repayment: the change minus the change in value) and "Wert" = changes in value without money moving (the cash flow's
Wertänderungen of its accounts). The debt block names instead what was repaid or newly borrowed.
Hover box: block and period; each account (up to eight, largest first) with its value at the end and its change (or "vor …
unbekannt"); "Übrige (n)" for the rest; then Geldfluss, Wert and "= Veränderung", and a note. "unbekannt": for an account of the
block no balance is known at the start (only carried backwards from a later month) – the change cannot be read, nothing is
estimated.

### overview.build.bet — Beteiligungen
The accounts of the position Beteiligungen – in the private area usually one per company, kept by a booking rule as share ×
the company's net worth. Value: their sum at the end of the last closed month (negative when a company is worth less than
nothing). Geldfluss: money paid in or taken out. Wert: the change in value without a payment (e.g. the share of the company's
result booked by the rule).

### overview.build.immo — Immobilien
"Immobilien": the accounts of the position Immobilien (the properties' values as kept in their accounts). "Immobilien nach
Darlehen" when a loan account is linked to a property calculation (page Immobilien) and the area has a property: the property
accounts plus these linked loan accounts (negative) – the equity in the properties. Value: that sum at the end of the last
closed month. Geldfluss: purchases and sales and, with the loans in it, repayment (raises the block) and new borrowing (lowers
it). Wert: revaluations of the property accounts without a payment.

### overview.build.liq — Liquidität & Anlagen
Everything that is no debt, no property and no participation: Bankguthaben (with money in transit), Wertpapiere, Festanlagen,
Sachwerte, Forderungen, Sonstiges. Value: their sum at the end of the last closed month (as those positions in Bilanz).
Geldfluss: what flowed in or out – surplus saved, money paid for or received from the other blocks (purchases, repayment,
contributions). Wert: price changes of portfolios and other changes in value without a payment (also balance corrections).
"unbekannt" when one of its accounts (e.g. a portfolio) has no known balance at the start.

### overview.build.debt — Schulden
"Schulden": the accounts of the position Verbindlichkeiten (loans, credit cards with a debt …); "Übrige Schulden" when loans
linked to a property are counted in "Immobilien nach Darlehen" – then the rest. Value: their sum at the end of the last closed
month, negative. Change: positive (green) = less debt. Below: "getilgt 7.200 €" = the debt fell by that much, "neu aufgenommen
… €" = it rose by that much. No split into Geldfluss and Wert; the hover box notes that fewer debts raise the net worth.

## overview.todo — Offen
What is open in Kontor, each line leading to the page where it is done; the number at the top right counts the lines. Missing
when nothing is open. Lines (yellow dot: to look at; grey: for information; blue: news):
- "n Buchungen warten auf Freigabe" – bookings the booking rules prepared, waiting for approval under Auto-Buchungen.
- "n Umsätze ohne Kategorie – zuordnen" – transactions without a category in MoneyMoney in the areas and the period chosen under
  Kategorisieren (not this page's area); the same number as beside "Kategorisieren" in the sidebar.
- "n Konten ohne bestätigte Zuordnung (Bereich, Position)" – new accounts (of all areas).
- "Kategorie „X“ gemischt? n große Einzelzahlungen" / "n Kategorien gemischt? …" – categories with payments far larger than
  the rest (of all areas; see Konten & Regeln → Cashflow-Positionen, "gemischt?").
- "n Ausgaben 2026 ohne Beleg" (grey) – outgoing transactions of the running year in this area without a receipt in Kontor.
- "Cashflow weicht im laufenden Monat vom Nettovermögen ab: X €" – in the running month the cash flow does not explain the
  change of net worth (difference over 1 €; Cashflow, check row).
- up to three warnings of the area's report (e.g. balances carried backwards before a month, problems of a rule).
- an update of Kontor (available, or waiting for approval) and a newer version for the assistant (blue).
The counts are Kontor's own, as of the last report.
