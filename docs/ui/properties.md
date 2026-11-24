# properties — Immobilien
Calculations of real-estate objects: per object any number of scenarios (one active) built only from the user's inputs – a
projection, not figures from MoneyMoney – and, against MoneyMoney, a plan-vs-actual comparison. Rows are calendar years from the
month of transfer (the first may be partial: "(n Mon.)"). Simplified: tax per partner = share × result × tax rate (no
progression, no loss offset), depreciation linear. Amounts are signed from the object's view: income positive, costs and payments
negative; remaining debt and value positive. Alpha: still being finished.

## properties.list — Objekte
One card per object. Top line: its area, tag "in Planung" = its active scenario feeds the area's planning. Bold: the name. From
the active scenario: "Kaufpreis X € · Faktor F · Bruttorendite Y %" (Faktor = purchase price ÷ yearly net cold rent at the start;
Bruttorendite = yearly net cold rent ÷ purchase price) – or "keine Kalkulation"; "Cashflow <year>: X € · EK-Rendite Y % · IRR Z %"
= the first full calendar year (else the first year): its cash flow (green/red), its equity return, and the IRR up to the sale.
"N Hinweise" = warnings of the scenario (see Kennzahlen). The card "Noch keine Immobilie": no object yet.

## properties.object — Objektangaben
The object's settings, no figures: Name; Bereich (whose balance sheet and planning it belongs to); Vermietungskategorie (its
MoneyMoney category, e.g. Vermietung \ Objekt – used for Soll/Ist, the planning and the AfA under Steuer; empty: "… (automatisch)" names the category under a rental context Kontor linked by a word of the name; without any, rent and property costs without a category count as estimates for the property their purpose names, else the area's only one); Objektkonto (Wert) (the
offline account that carries its value in the balance sheet); "In Planung übernehmen" (on: rent, costs, interest, repayment,
remaining debt, value and distributions of the active scenario are planned for the area); Notizen. Tabs below: Kalkulation,
Jahrestabelle, Soll/Ist, Dokumente (N = documents linked).

## properties.calc — Kalkulation
Scenario menu ("(aktiv)" = the active one: it counts for planning, the AfA under Steuer and the list). Left the inputs, right the
result – computed from the inputs as they stand on screen, again after each change and before saving; Jahrestabelle and Soll/Ist
show the active scenario as saved.

### properties.calc.inputs — Eingaben
The user's assumptions: Objekt (kind, m², units, purchase price, Übergang = first month with rent, costs, AfA and interest,
horizon in years); Nebenkosten (transfer tax %, notary, land register, broker and "sonstige" raise the AfA base; "sofort abziehbar"
is an expense in the first year); Abschreibung (building share %, AfA % p.a. – or remaining useful life, then rate = 1 ÷ years);
Miete (net cold rent per month, Umlage = service charge advance per month – passes through, in neither result nor cash flow,
vacancy %, adjustment: index rent by CPI with factor and threshold at the start of each year, fixed % p.a., or none); Kosten
(non-recoverable costs p.a., reserve p.a., their yearly increase); Gesellschafter (share %, tax rate %); Ausschüttung % of a
positive result; tax refund in cash flow yes/no; Wert & Verkauf (appreciation % p.a., sale year, sale costs %); Finanzierung per
loan (amount, rate, annuity / repayment loan / bullet, instalment or initial repayment, special repayments, fixed rate until and
follow-up rate, maturity, start, settlement monthly or yearly on the 1 January balance, interest deductible, linked loan account).

### properties.calc.kpis — Kennzahlen
Whole €. Gesamtinvestition = purchase price + all closing costs. Eigenkapital inkl. NK = purchase price − loans + closing costs.
Fremdkapital (LTV) = sum of loans (LTV = loans ÷ purchase price). Kaufpreisfaktor = purchase price ÷ (net cold rent × 12 at the
start, no vacancy). Bruttomietrendite = yearly net cold rent ÷ purchase price. Nettomietrendite = (yearly net cold rent −
non-recoverable costs − reserve) ÷ Gesamtinvestition. Cashflow Jahr 1 = cash flow of the first full calendar year. Cash-on-Cash =
Cashflow Jahr 1 ÷ Eigenkapital inkl. NK. DSCR Jahr 1 = (rent + costs + reserve) ÷ (interest + regular repayment) of that year.
AfA p.a. "X € (r % auf B)" = rate × base, base = building share × (purchase price + closing costs that raise it).
Kapitaldienst/Monat = monthly instalments of all loans at the start (annuity; else interest plus monthly repayment). "IRR bis
<year>" = yearly return on equity incl. closing costs from the yearly cash flows up to the sale year (else the horizon's end) plus
the net proceeds then (value × (1 − sale costs) − remaining debt). Preis/m², Miete/m² (net cold rent per month) only with an area.
Banners: warnings – a loan due with debt left, fixed rate ending without follow-up rate, cumulative cash flow below zero (its
lowest point). "Mietanpassungen": index increases (year: +% → new net cold rent per month), the first six.

### properties.calc.chart — Grafik
Per calendar year of the horizon: bar = that year's cash flow (left axis; green positive, red negative); solid line = remaining
debt at year end (right axis); dashed line = object value at year end (right axis: purchase price grown by the appreciation).
Axis labels shortened (T = thousand). The first year may be partial.

### properties.calc.years — Erste Jahre
The first 12 calendar years, whole €. Miete = net cold rent after vacancy. Kosten = non-recoverable costs + reserve. Zinsen = all
loans. Tilgung = regular + special. AfA = depreciation. Ergebnis = taxable result: rent + non-recoverable costs (not the reserve)
+ deductible interest + AfA (+ immediately deductible costs in the first year). Steuer = Σ partners −share × Ergebnis × tax rate
(negative = to pay, positive = refund). Cashflow = rent + costs + reserve + interest + repayments + Ausschüttung (Ergebnis > 0:
−Ergebnis × distribution %; else the tax refund, if chosen). Vermögensaufbau = cash flow minus repayments (repaid debt counts as
wealth, so it adds). EK-Rendite = Vermögensaufbau ÷ (equity incl. closing costs + Vermögensaufbau of earlier years). Restschuld =
debt left at year end.

## properties.years — Jahrestabelle
All years of the active scenario as saved, € with cents, coloured by sign only (so Restschuld shows green). Columns as in Erste
Jahre, plus: Umlage (service charge advances, pass through); Kosten = non-recoverable costs only, Rücklage on its own; Tilgung and
Sondertilgung apart; Ergebnis n. St. = Ergebnis + Steuer; Ausschüttung = distribution paid out, or in a loss year the tax refund (if
chosen); Cashflow kum. = summed from the first year; Objektwert; EK im Objekt = Objektwert − Restschuld; DSCR (as in Kennzahlen,
"–" without debt service); NKM/Monat = net cold rent per month that year after index increases, before vacancy. Then per loan
"<name> Zins", "<name> Tilgung" (incl. special), "<name> Saldo" = its balance at year end (negative, as a debt).

## properties.target — Soll/Ist
Each calendar year with a scenario year and transactions: Soll = active scenario, Ist = MoneyMoney (booked), Δ = Ist − Soll,
whole €; green = better than planned (more rent, less cost or interest, less remaining debt), red = worse, plain = equal. Miete Ist = positive transactions of the rental category and below (service charge advances
included; Soll excludes them). Kosten Soll = costs + reserve; Ist = negative transactions of that category. Zinsen Ist = interest
and fee bookings on the linked loan accounts. Restschuld Ist = what is owed on the linked loan accounts at 31 Dec (this year: today),
above zero like Soll; empty without linked loan accounts. This year is incomplete.

## properties.documents — Dokumente
Links to files on the Mac (contract, appraisal …): title, kind as a tag, path, date linked. The files stay where they are; no
figures.
