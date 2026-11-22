# planning — Planung
Planning carries the past of the chosen area forward: the same cash flow table as on the page Cashflow, with the plan months always
appended and editable, and below it the settings that drive the plan (loans, value per account, planned events). Plan months are the
months after the running one – as many as the horizon says, always up to a December. Planned figures are amounts in euros per month
of this area, computed by Kontor from the actual months and these settings; nothing is booked anywhere. The plan of each area is
saved apart (the area switch chooses it); its projected balances also appear in the plan columns of the balance sheet and the
Cashflow page. "Monate / Jahre" changes the table's columns; "inflationsbereinigt" shows plan values in today's money.

## planning.params — Parameter
The plan's settings for the whole area: "Horizont … Monate" (1–240, default 24: how many months after the running one are planned;
the plan always runs on to the next December), "Standardmethode" (how a row without its own method is planned: Ø 12 Monate or Ø 6
Monate = the average of the last 12 or 6 closed months – of fewer when fewer are known –, Vorjahresmonat = the same month a year
before, MoneyMoney-Budget = the budgets of the position's categories in MoneyMoney, Keine = 0), "Inflation" (% p.a., default 2: the
yearly increase of expenses unless "Ausgaben" is filled; also the rate of "inflationsbereinigt"), "Steigerung Einnahmen" (% p.a.,
default 0, e.g. salary growth), "Ausgaben" (% p.a.; empty = the inflation), "Rendite Wertpapiere/Anlagen" (% p.a., default 0: the
yearly change in value of portfolios, securities and term investments without their own entry under Wertentwicklung je Konto). The
increases apply month by month: a plan month n months after the running one gets the base value × (1 + rate)^(n/12). Investing and
financing rows grow by 0 % unless set. "Übernehmen" saves; "Plan zurücksetzen" deletes every plan setting of this area (methods,
overrides, loans, values, events).

## planning.table — Tabelle (Plan)
The cash flow table of the area (same rows and levels as on the page Cashflow: Überschuss with Einnahmen and Ausgaben and their
positions, Investitionen, Finanzierung, Unklar, Veränderung Bankguthaben, Umschichtungen, Wertänderungen, Veränderung Nettovermögen;
opened at the level "Positionen"). Columns: the actual months (the running month faded: booked so far), then the plan months with a
tinted background in full colour (headings hatched), year columns "Σ 2026" (the running year "Ist + Plan"). Figures without a +
sign, as entered. MoneyMoney's categories inside a position show actual months only – the plan works on whole positions.

A plan cell holds the planned amount of that row and month: by the row's method (see the rows), a loan's rows by the loan schedule,
a property's rows ("<Objekt> · Miete/Kosten") and loans of a property calculation by that calculation, planned events as rows
"Ereignis: <text>" under "Geplante Ereignisse". Not planned (0) unless set: Wertänderungen and Unklar rows, contributions and
withdrawals, loans taken up, transfers into or out of accounts (saving by a MoneyMoney category is planned like a position). A cell
with a blue bar at its left edge is overridden by the user (legend "überschrieben"; its tooltip "Vorschlag: …" = what Kontor would
plan); with "Vorschlagswerte zeigen" every plan cell shows Kontor's suggestion small below the value. The sums follow from the rows:
Veränderung Bankguthaben = the planned rows; "Bankguthaben am Ende" in a plan month = the month before + that change; "Nettovermögen
am Ende" = planned cash + projected balance of every account (loans after repayment, Wertentwicklung, linked areas, property values)
+ planned contributions; Wertänderungen in plan columns = the planned changes in value without a row of their own.
"inflationsbereinigt" (pill "Planwerte in heutiger Kaufkraft"): each plan value × (1 + inflation)^(−n/12), n = months after the
running one; actual months unchanged; the rows Anfang/Ende hidden.

### planning.table.row — Zeile mit Planmethode
A position or account row of the plan. Below its name: a tag with the method in effect (Ø 12 Monate, Ø 6 Monate, Vorjahresmonat,
fester Betrag/Monat, Jahresbetrag/12, MoneyMoney-Budget with " · Budget <amount>", Keine), and the fields: the method ("Standard" =
the area's Standardmethode, else the row's own), "Betrag" (only for fester Betrag = that amount every month, Jahresbetrag = the
amount ÷ 12), "% p.a." (the row's yearly increase; empty = default: expenses the inflation or the expense rate, income the income
rate, other rows 0), ✓ saves, ↺ (only when cells are overridden) brings back the suggestion. Rows of a loan with a known interest
rate show "Darlehensplan (Zins auf Restsaldo)" instead: planned by the loan schedule (section Darlehensplan). Rows of planned events
("Ereignis: …", tag "aus geplantem Ereignis") and of property calculations (tag "aus der Immobilienkalkulation") follow those and
have no method fields.

How a plan cell is computed: Ø 12 / Ø 6 Monate = the average of the last 12 / 6 closed months (of fewer when the area has fewer; a month without bookings counts as 0);
Vorjahresmonat = the same month a year before (actual, else planned) × (1 + increase); fester Betrag, Jahresbetrag/12, Budget, Keine
as named; every method except Vorjahresmonat × (1 + increase)^(n/12) for the n-th plan month. Expenses are negative, income
positive. An overridden month keeps the user's value (blue bar).

## planning.loans — Darlehensplan
One row per loan of the area that has repayment or interest rows in the cash flow. Columns: "Darlehen" (the loan account; tag
"Regel: <Modell>" when a booking rule for it exists – Jahresbasis (31.12.) or Restschuld monatlich),
"Zins p.a." (interest rate in %; empty = the rate of the booking rule at the first plan month – without either, the loan's rows are
planned by their method instead), "Modell" ("Restschuld monatlich": each month's interest on the current remaining debt;
"Jahresbasis (31.12.)": on the debt at the end of the year before; without an own entry a loan with a booking rule uses the rule's
model, and the selection shows it), "Zahlung je Monat" (interest + repayment per month; empty = the average of the
last up to 12 closed months).

Per plan month: interest = debt (Jahresbasis: the debt at the end of the year before) × rate ÷ 12, repayment = payment − interest
(not below 0, never more than the debt left), the debt falls by the repayment. These values fill the loan's rows Zinsen and Tilgung
in the table (unless a cell is overridden) and the loan's balance in the balance sheet's plan columns. Loans of a property
calculation follow that calculation. "Keine Darlehenszeilen im Cashflow." = no such loan.

## planning.appreciation — Wertentwicklung je Konto
One row per account of the area except bank accounts (also liabilities and hidden accounts, tag "ausgeblendet"): "Konto" (its path),
"Position" (its balance-sheet position), "% p.a." (yearly change in value), "Basis (€, optional)" (a fixed amount the percentage
applies to; empty = the projected balance itself), "Kopplung an Bereich" (another area), "Anteil" (0–1, empty = 1). Per plan month:
balance + (Basis or balance) × % ÷ 12. Coupled: the balance = Anteil × that area's planned net worth (a participation at its share).
Without an entry: portfolios, securities and term investments change by "Rendite Wertpapiere/Anlagen" (Parameter), other accounts
stay; an account of a property calculation follows its object value. These changes have no payment: they show as Wertänderungen in
the plan columns and in the projected net worth.

## planning.events — Geplante Ereignisse
One line per planned event, the last one empty for a new event. Fields: "Bezeichnung", kind (Umschichtung, Ausgabe, Einnahme),
"Betrag" (€), "Monat" (its first month), repetition (einmalig, monatlich, je Quartal, jährlich), "bis" (the last month; empty = to
the end of the plan), "Von" → "Nach" (accounts; empty = "Bankguthaben (Bereich)", the area's cash), "aktiv" (inactive events do not
count). Only plan months count.

Effect: Einnahme/Ausgabe = a row "Ereignis: <text>" under "Geplante Ereignisse" in Einnahmen or Ausgaben with + or − the amount in
each event month – it changes cash and net worth (Von/Nach do not matter). Umschichtung = the amount moves from Von to Nach: between
cash and an account it is a row "Ereignis: <text>" under Investitionen (Finanzierung when the account is a liability), − when cash
pays; between two non-bank accounts only their balances move (no cash flow row); net worth stays; a liability is never repaid beyond
zero (e.g. Von = portfolio, Nach = loan account: the loan repaid from the portfolio).
