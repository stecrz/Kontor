# drawer — Seitenfenster
The side panel at the right, beside the page (on a narrow screen over it): opened by a click on a name, a row or a figure, it
shows what lies behind it; its title at the top names that – an account, a security, a figure with its column, a rule. The
figure it came from stays marked on the page. It belongs to the page below it (its area and period); nothing in it is a new
calculation of its own unless said so.

## drawer.hist — Verlauf eines Kontos
The history of one account (title: its name), opened from the balance sheet or Konten & Regeln: its month-end balances and where
they come from. Parts: the holdings of a portfolio (drawer.hist.holdings, portfolios only), the source of the history
(drawer.hist.source), the chart (drawer.chart), the monthly balances (drawer.hist.months) and, at the end, an import of balances
from a CSV export ("Datum;Saldo" or "Datum;Konto;Saldo"; the last value per month counts; the account is then kept by
balances). All values are balances in € at a month end, never flows; the running month shows today's balance. Kontor never
estimates a balance.

### drawer.hist.source — Verlauf aus …
"Verlauf aus Umsätzen | Kontoständen": how the month ends are computed (the marked one; switched, it is a preview until saved).
"Umsätzen" (default for bank accounts): balance at a month end = today's balance minus all later booked transactions, as
MoneyMoney computes it; own values do not count; before the first transaction there is no balance. "Kontoständen": entered,
imported or taken-over balances are anchors, the months between and before are computed from them with the bookings;
differences to the bookings appear in the cash flow as "Korrektur Kontostand". Portfolios (no bookings): the last known balance
applies (taken over from MoneyMoney, recorded by Kontor each month).
Notes below it, where they apply: first transaction in MoneyMoney with its opening balance ("Startsaldo") – no balance before
it; no transactions at all (the history is today's balance throughout); pending transactions not included (number and sum, as
in MoneyMoney's balance); negative balances for an account that cannot go below zero (transactions missing in MoneyMoney);
balances before a month carried with the first known value; no MoneyMoney data in memory (values of the last report); the
preview of a switched source.

### drawer.hist.months — Monatsstände
One line per month end, from the first booking or first known balance (at least twelve months) to the running month (today's
balance): the month, then an input field with the balance (€ with cents). The grey placeholder text in a field is the balance
Kontor computed or read for that month end; a value typed into the field (black) is an own balance. With "Umsätzen" every field
is locked and only the computed balance shows. With "Kontoständen" an own value (entered or imported) is an anchor and wins; an
empty field shows the balance computed from the anchors and the bookings; a month in the accent colour holds a known balance
that is not an own value (taken over from MoneyMoney – tooltip "aus MoneyMoney" –, for portfolios also Kontor's monthly record).
A month can be added before the first one.

### drawer.hist.holdings — Depotpositionen
Portfolios only, folded at the top: "3 Positionen · 85.000 € · +5.000 € (6,3 %)" = number of holdings, their value, and the gain or
loss against their purchase value from MoneyMoney (in € and in percent of it; green gain, red loss; missing without a purchase
value). The table, as of the last reading of MoneyMoney (today's holdings, not a month end): Position (name; hover: ISIN and
asset class), Menge (quantity), Wert (value in €), G/V (value minus purchase value of that holding).

## drawer.chart — Verlauf (Grafik)
The chart in the history panel of an account or a security: its month-end balances as a line over an area down to zero
(straight lines between month ends; the last point is the running month with today's value), from the first month with a value.
"Alle" (default): the whole history; "1 J": the last twelve month ends. Amount axis at the left (T = thousand, M = million),
thin lines at each new year. Pointing at it shows e.g. "Okt 26: 12.345,67" – the balance at that month end. The same values as
the list of monthly balances below it.

## drawer.security — Wertpapier
One security of a portfolio (title: its name), opened from the balance sheet: below the title its portfolio and ISIN, its name in
MoneyMoney (or that it has none) and whether the name was looked up or changed in Kontor. Its value at each month end, read-only:
the chart (drawer.chart) and the list "Monatsstände" – past months from MoneyMoney's history or Kontor's monthly record, the
running month from MoneyMoney; only months with a known value. "Übrige (nicht aufgeschlüsselt)": the part of the portfolio's
value no known security explains. No plan values.

## drawer.ekq — Eigenkapitalquote
The equity ratio of one month (named below the title), step by step in whole €: "Nettovermögen" of the area; in a company area
"+ Kapitalkonten der Gesellschafter" (capital and shareholder accounts owed to the partners); "= Eigenkapital". "Eigene Schulden":
the area's accounts with a negative balance (not participations, not capital accounts), each listed below in grey. Then one line
per linked company, e.g. "Alpha GbR: 40 % von 120.000 €" with the amount at the right = the area's share of that company's debts,
its debt accounts below (further companies looked through too). "= Schulden"; "Vermögen (Eigenkapital + Schulden)"; last
"Eigenkapitalquote = Eigenkapital ÷ Vermögen" in percent (one decimal) or "unbekannt". Notes: participations not looked through
(no company assigned under booking rules – they count only with their value, without the company's debts); accounts of a company
that lie in no area (ratio unknown).

## drawer.transit — Geldtransit
The transfers between the area's own accounts whose debit and credit fall into different months, newest first: "Abgebucht"
(date, and the account it left), "Gutgeschrieben" (date, and the account it reached), "Betrag" (€). Opened from a month's figure:
only those under way at that month's end, headed "Unterwegs Ende Oktober 2026: 1.234,56" = their sum, the figure of the balance
sheet's row Geldtransit; "Alle zeigen" lists all of them. "Keine Umbuchung über dieses Monatsende": nothing was under way.

## drawer.tx — Umsätze hinter einer Zahl
The transactions behind a figure (title: the row or category and the column or period, e.g. "Lebensmittel · Okt 26"), opened from
a figure of the cash flow (table, heat map, ring) or from Konten & Regeln → Cashflow-Positionen (a category's bookings, a
recipient's payments). The line above the list: for a category "12 Umsätze · Summe −1.234,56" – their number and sum (all
matches, though at most 500 are listed); for other rows of the cash flow only the number ("12 Umsätze"), as the bookings behind
a row can differ from its figure (a transfer, interest booked on a loan account …). "ohne geschätzte Umsätze ohne Kategorie":
transactions without a category that Kontor only estimated for that figure are not listed. Each line: date, counterparty with
the purpose below, amount in € (outflows negative). From the cash flow: only that area and the months of the figure.

## drawer.check — Abgleich mit der Bilanz
The check of the cash flow against the balance sheet for one column (title "Abgleich mit der Bilanz · Okt 26"), opened from a
check row of the cash flow – for the bank balances (their change against the cash rows) or for net worth (its change against the
rows that change it). At the top the reasons for the difference, each "reason: amount €" (with the month when the column spans
several): Kategorie „Nicht berücksichtigen" (transactions left out on purpose), Geld in Transit über das Monatsende, Korrektur
Kontostand / Anfangssaldo / Wertänderung of an account, Kontostand unbekannt (accounts with a known balance in only one of the two
months), or "Ohne erkannte Ursache – Kategorie oder Gegenbuchung prüfen". Below, the bookings behind them (left out, or the side of
a transfer booked in that month) with their number only, no sum; nothing below when the difference has no single bookings behind it.

## drawer.preview — Buchungen einer Regel
What a booking rule would book (title: the rule), opened from Konten & Regeln → Buchungsregeln: "n Buchungen, die diese Regel
buchen würde" – bookings not made yet, computed from the rule as currently edited (nothing is saved or booked by it). Each line:
date, the account it books into, its purpose, amount in €; "älter" = dated before the last check (backdated, or missing again) –
never booked without approval. At most 300 are listed; all of them wait for approval under Auto-Buchungen.
