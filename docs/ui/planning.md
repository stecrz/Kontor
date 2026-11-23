# planning — Planung
Planning carries the past of the chosen area forward: the same cash flow table as on the page Cashflow, with the plan months always
appended and editable, and below it the settings that drive the plan (loans, value per account, planned events). Plan months are the
months after the running one – as many as the horizon says, always up to a December. Planned figures are amounts in euros per month
of this area, computed by Kontor from the actual months and the rules; nothing is booked anywhere. Rules stand on three levels: the
area's default (one for income, one for expenses), a position (a row of the cash flow) and a category of MoneyMoney inside it – the
deepest level that sets a field counts, method and increase each on its own. A position with categories is the sum of its
categories. The plan of each area is saved apart (the area switch chooses it); its projected balances also appear in the plan columns
of the balance sheet and the Cashflow page. "Monate / Jahre" changes the table's columns; "inflationsbereinigt" shows plan values in
today's money.

## planning.params — Parameter
The plan's settings for the whole area. "Einnahmen" and "Ausgaben": the area's default rule for rows without a rule of their own –
the method (Ø 12 Monate, Ø 6 Monate = average of the last 12 or 6 closed months, of fewer when fewer are known; Vorjahresmonat =
the same month a year before; MoneyMoney-Budget = the budgets in MoneyMoney, a category without one: Ø 12 Monate; Keine = 0) and
"mit Steigerung" (the rates below) or "ohne Steigerung" (0 %). The Ausgaben rule also plans the rows of Investitionen and
Finanzierung that follow a method (their increase is 0 % unless a row sets one). "Horizont … Monate" (1–240, default 24),
"Inflation" (% p.a., default 2: the increase of expenses unless "Steigerung Ausgaben" is filled; also the rate of
"inflationsbereinigt"), "Steigerung Einnahmen" (% p.a., default 0), "Steigerung Ausgaben" (% p.a.; empty = the inflation), "Rendite
Wertpapiere/Anlagen" (% p.a., default 0: the yearly change in value of portfolios, securities and term investments without an entry
under Wertentwicklung je Konto). An increase applies month by month: the n-th plan month gets the base × (1 + rate)^(n/12);
Vorjahresmonat: the month a year before × (1 + rate). "Übernehmen" saves; "Plan zurücksetzen" deletes every plan setting of this area.

### planning.params.model — Planungsmodell
The area's default rule for income and expenses with one click; the active one is highlighted, "eigenes" when the rules above match
none. Gleichmäßig: both Ø 12 Monate with increase (Kontor's default). Vorsichtig: expenses Ø 12 Monate with increase, income
Vorjahresmonat without increase. Wie Vorjahr: both Vorjahresmonat without increase. Budget: expenses by the MoneyMoney budgets (without
a budget: Ø 12 Monate) with increase, income Ø 12 Monate with increase. A model changes only the area's default: rows and categories
with a rule of their own keep it, unless the user chooses "Ersetzen" when asked.

## planning.figures — Sparquote, Reichweite, Zinslast
Three key figures of the plan, each over the next 12 plan months (the months named in its tooltip). Sparquote: Überschuss ÷
Einnahmen of those months, in % (Überschuss = Einnahmen + Ausgaben, expenses negative); "–" without planned income. Reichweite: the
bank balance at the end of the running month ÷ the planned average fall of the bank balance per month (the row "Veränderung
Bankguthaben" of those months) = how many months the money lasts; "–" when the bank balance does not fall in the plan; 0 when it is
already at or below zero. Zinslast: planned interest on loans (the interest rows of Finanzierung, as a positive amount) ÷ Einnahmen of
those months, in %; "–" without planned income. Plan values with overrides count as they stand; "inflationsbereinigt" does not change
them.

## planning.table — Tabelle (Plan)
The cash flow table of the area (same rows and levels as on the page Cashflow: Überschuss with Einnahmen and Ausgaben and their
positions, Investitionen, Finanzierung, Unklar, Veränderung Bankguthaben, Umschichtungen, Wertänderungen, Veränderung Nettovermögen;
opened at the level "Positionen", "Details" shows the categories). Columns: the actual months (the running month faded), then the plan
months with a tinted background (headings hatched), year columns "Σ 2026" (the running year "Ist + Plan"). Figures without a + sign.

Every plan cell has a tooltip saying how it came about – the same text a right click gives the assistant ("So berechnet"): your own
value and Kontor's suggestion; the base (the months averaged and their average, the month a year before, the fixed or annual amount,
the budget, a share of the position's amount); the increase factor with its rate and months; the result; and where method and
increase come from (own rule, the position, the area's default with its planning model, the rates). A year column: how many plan
months it adds up, how many of them are your own, the rule. A cell with a blue bar at its left edge holds a value of your own (legend
"überschrieben"); "Vorschlagswerte zeigen" shows Kontor's suggestion small below every plan value. Rows from elsewhere: a loan's rows
by the loan schedule, a property's rows by its calculation, planned events as "Ereignis: <text>". Not planned (0) unless given a rule:
Wertänderungen, Unklar, contributions and withdrawals, loans taken up, transfers into or out of accounts. The sums follow from the rows:
Veränderung Bankguthaben = the planned rows; "Bankguthaben am Ende" = the month before + that change; "Nettovermögen am Ende" = planned
cash + projected balance of every account + planned contributions; Wertänderungen in plan columns = planned changes in value without a
row of their own. "inflationsbereinigt": each plan value × (1 + inflation)^(−n/12); the rows Anfang/Ende hidden.

### planning.table.row — Zeile mit Planregel
A position or account row of the plan. Beside its name a tag with the method in effect (Ø 12 Monate, Ø 6 Monate, Vorjahresmonat,
fester Betrag/Monat, Jahresbetrag/12, MoneyMoney-Budget, Keine; " · Budget <amount>" = the position's budget in MoneyMoney per month;
"· n Kategorien anders" = categories with a rule of their own); a framed tag = the row has a rule of its own; the tag's tooltip names
where method and increase come from. Below the name the row's own rule: method ("Standard" = the area's default), "Betrag" (only for
fester Betrag = per month, Jahresbetrag = per year, ÷ 12), increase ("Steigerung: Standard" = from the area, "ohne Steigerung" = 0 %,
"eigene Steigerung" = % p.a. beside it); ✓ saves, ↺ deletes the row's own values. A position with categories is the sum of its
categories in every plan month: each category planned by its own rule, else the position's. A fixed or annual amount or a budget of
the position is shared by its categories that follow it, by their share of the last 12 closed months in its direction (a category
against it – refunds in an expense position – gets no part: 0); a value of your own for the position goes to its categories without
a value of their own, by their suggestion in the same direction (where every category has a value of its own, theirs count and the
position's value shows without the blue bar, its tooltip saying it does not count). Rows of a loan show "Darlehensplan (Zins auf Restsaldo)", of events "aus geplantem Ereignis", of a property
calculation "aus der Immobilienkalkulation": no rule of their own. Expenses negative, income positive.

### planning.table.category — Kategorie in der Planung
A category of MoneyMoney inside a position ("geschätzt" = bookings without a category, placed by Kontor). Actual months: its
bookings; plan months: its plan, editable like a position's cells. Beside the name the tag of its method (framed: a rule of its own),
below it its own rule: method ("wie Position" = the position's rule), "Betrag" (fester Betrag, Jahresbetrag), increase ("Steigerung wie
Position", "ohne Steigerung", "eigene Steigerung"). Its plan: by its own history (Ø of its last 12 or 6 closed months, its month a
year before), by its budget in MoneyMoney (or a budget above it that covers only categories of this position planned by budget,
shared by their share of the last 12 months), by its own amount, or as its share of the position's amount. The position's figure is
the sum of its categories, to the cent.

## planning.loans — Darlehensplan
One row per loan of the area that has repayment or interest rows in the cash flow. Columns: "Darlehen" (the loan account; tag
"Regel: <Modell>" when a booking rule for it exists – Jahresbasis (31.12.) or Restschuld monatlich),
"Zins p.a." (interest rate in %; empty = the rate of the booking rule at the first plan month – without either, the loan's rows are
planned by their method instead), "Modell" ("Restschuld monatlich": each month's interest on the current remaining debt;
"Jahresbasis (31.12.)": on the debt at the end of the year before; without an own entry a loan with a booking rule uses the rule's
model, and the selection shows it), "Zahlung je Monat" (interest + repayment per month; empty = the average of the
last up to 12 closed months). A loan with nothing owed (repaid, or overpaid: its balance on the other side of what its booking rule or its account's role
says) gets no interest and no repayment in the plan.

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
