# tax — Steuer
A yearly summary for the tax return, per entity (each area: the private one and each company) and year – compiled from what is
categorised in MoneyMoney, not tax advice. Toolbar: Jahr (every year with booked transactions, plus the current one; the current
year is incomplete) and Entität (name, kind – privat, Gesellschaft, GbR, GmbH – and, for a company, the user's share). All figures
are sums of booked transactions of that entity's accounts in that calendar year, in € (inflows positive, outflows negative). Left
out everywhere: transfers (counter IBAN of an own account of the entity, the user's transfer categories, Kontor's repayment, value
and mirror bookings), portfolios, accounts set to "nicht bilanzieren" and guarantees, bookings on asset accounts (value
bookings are no income) and on loan accounts (only their interest counts, as Schuldzinsen), and accounts kept in another currency
(Kontor does not convert: a note below the cards names them). Alpha: still being finished.

## tax.cards — Kennzahlen des Jahres
"Einnahmen (kategorisiert)": the sum of all categories whose total for the year is positive (each category netted first).
"Ausgaben (kategorisiert)": the sum of all categories whose total is negative. Both in whole €, both including the rental
categories. "Schuldzinsen": interest and fees booked on the entity's loan and receivable accounts in the year (bookings whose
text contains Zins, Gebühr, Entgelt, Provision, Bereitstellung or Kontor's interest mark) – negative = paid. "Ohne Kategorie":
orange "N Buchungen" = booked transactions of the year without a category (that would count here), green "keine" = none; below
their sum in € with cents and a link to them under Umsätze & Belege. Below the cards, only if the entity has accounts in another
currency: "Nicht enthalten, da in anderer Währung geführt" with those accounts and their currencies – none of their amounts is in
any figure of this page (never converted into euros).

## tax.rental — Vermietung je Objekt
One column per rental object, found only from category names "<rental category> \ <object> \ <kind>" (e.g. Vermietung \
Musterstraße \ Mieteinnahmen; the rental category is set under Konten & Regeln → Steuer); a category with only two levels counts
for "(allgemein)", loan interest that fits no object for "(Darlehen ohne Objekt)". Rows, each the year's sum per object: indented
kind rows = sum of that kind (e.g. Mieteinnahmen positive, Hausgeld negative). "Einnahmen" = sum of the kinds with a positive total.
"Werbungskosten (ohne Zinsen/AfA)" = sum of the kinds with a negative total. "Schuldzinsen <loan>" = interest and fees on that loan
account (assigned to an object under Konten & Regeln → Steuer, or to the only object automatically). "AfA (manuell)" = the year's
depreciation as a positive amount: the value entered here for this year (in the field), else the depreciation of the object's active
calculation under Immobilien (matched by the last part of its rental category, else its name; grey in the empty field), else 0. "Ergebnis (Überschuss / Verlust)" = Einnahmen + Werbungskosten +
Schuldzinsen − AfA (green surplus, red loss). "davon Anteil N %" (companies only) = Ergebnis × the user's share in the company.

## tax.positions — Steuerpositionen / Oberkategorien
Every category with booked transactions in the year, grouped. For the private entity "Steuerpositionen": the position the user
assigned to the category (Konten & Regeln → Steuer), else one guessed from the name (e.g. Gehalt → Anlage N, Dividenden → Anlage
KAP, Spenden → Sonderausgaben, Handwerker → § 35a, Wohnen → nicht abziehbar); rental categories always "Anlage V (Vermietung)",
the rest "ohne Zuordnung". For a company "Oberkategorien": grouped by top-level category. Group rows: position name and its sum.
Rows below: category (A › B), Betrag = its sum in the year, Buchungen = number of transactions. Groups alphabetical, categories by
size of the amount.
