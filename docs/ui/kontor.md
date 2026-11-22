# kontor — Kontor
Kontor reads the banking app MoneyMoney on this Mac (accounts, balances, transactions, categories) and shows the user's money as
balance sheet, cash flow and planning – for each **area** (Bereich): the private area and each company (GbR, UG, GmbH …). Every
account belongs to exactly one area and has one **position** (Position) of the balance sheet. The area switch at the top of a page
(e.g. "Privat · Alpha GbR · Beta GbR") chooses whose figures are shown; a company's figures are always the company's own (100 %),
never the user's share – the share shows only in the private area, as the value of the participation account (share × the
company's net worth, kept by a booking rule).

Positions, from most to least liquid: Bankguthaben (cash), Wertpapiere (securities, portfolios), Festanlagen (term investments),
Immobilien (real estate), Beteiligungen (participations), Sachwerte (tangible assets), Forderungen (receivables), Sonstiges
(other), Verbindlichkeiten (liabilities, negative). Not in net worth: Eventualverbindlichkeiten (guarantees) and accounts set to
"nicht bilanzieren"; accounts in a foreign currency are never converted (shown outside net worth). **Nettovermögen** (net worth) =
the sum of all balances of the area in net worth: assets minus liabilities.

Time: values are **month-end balances**; the running month shows today's balance. Month labels like "Okt 26" mean October 2026;
"Nov 25 – Okt 26" is a range of months, both included. Charts and the overview count the **closed months** (the running month is
not finished); "12 Monate" means the last twelve closed months. The running month or year is shown faded; **plan** values (months
after the running one) are faded and hatched. Year columns: flows as the year's sum ("Σ 2026"), balances as the year-end value.

Cash flow (Cashflow), the same outline for every area: **Überschuss** (surplus: Einnahmen income minus Ausgaben expenses of everyday
life or business, by fixed positions with the user's MoneyMoney categories in them; interest and dividends received count here),
**Investitionen** (investing: buying and selling assets – money leaves the bank account but stays wealth), **Finanzierung**
(financing: loans taken up, repayment, interest paid, partners' contributions and withdrawals). Their sum, together with
what is unclear, is the **Veränderung Bankguthaben** (change in cash). **Veränderung Nettovermögen** (change in net worth) =
Veränderung Bankguthaben + **Umschichtungen** (money that left the bank accounts but stays wealth: investments, repayment of
loans, money taken up as a loan with a minus) + **Wertänderungen** (changes in value without a payment: prices, revaluations,
participations). Transfers between the user's own accounts never count as income or expense. Transactions without a category
are estimated by Kontor ("geschätzt") – nothing is written into MoneyMoney for that.

How figures are written: amounts in € with the cents set smaller; "T" = thousand (420T = 420.000 €), "Mio." = million. Inflows,
income and assets positive; outflows, expenses and liabilities negative – in flow tables with a sign (+/−), balances without "+".
A percentage beside an amount is, unless the description of the place says otherwise, that amount's change against the comparison
period named there (usually the same months a year before); the amount itself is the value of the period shown, not a change.
"±0 %" means unchanged; "+2k %" means about +2,000 %. A share ("Anteil", "22 %" inside a ring) is a part of the whole, not a change.
"unbekannt" means Kontor does not know the value – Kontor never estimates a balance. Green: income, inflow, better; red: expenses,
outflow, worse – for investing, financing and value changes without judgement.

Booking rules (Buchungsregeln) let Kontor book into the user's offline (manual) accounts in MoneyMoney – loans (repayment and
interest), participations (share × value), account mirrors; these bookings carry a mark like "#kontor-zins-2026-10" and are listed
under Auto-Buchungen. Kontor never changes bank accounts, never transfers money and writes into MoneyMoney only what the user
approved (and the category of transactions the user assigns under Kategorisieren).

Pages marked "Alpha" (Planung, Immobilien, Steuer, Umsätze & Belege) are still being finished.
