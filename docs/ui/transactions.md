# transactions — Umsätze & Belege
The transactions Kontor read from MoneyMoney (all accounts that belong to an area, booked and pending), newest first, with the
receipts linked to them in Kontor. The filters at the top apply to the list and to its Excel export; the area switch of the top
bar does not – the filter "Bereich" does. Receipts are files in Kontor's receipt folder or links to files elsewhere on the Mac;
MoneyMoney holds no reference to them. Alpha: still being finished.

## transactions.filters — Filter
First row: Bereich (one area or all), Jahr (booking year; the years that have transactions), Konto (accounts of the chosen area),
search (matches name, purpose, category, account name or the amount as written in the data, e.g. -12.5). Second row: Alle /
Ausgaben (amount below 0) / Einnahmen (0 or more); "ohne Beleg" (no receipt linked); "ohne Kategorie" (needs a category and has
none – transfers between own accounts and accounts that need no category are left out); von/bis = booking date range, both days
included. Third row: chosen categories as chips (each with its subcategories); opened from a chart they are set already, a chip
"<label> – alle N Kategorien" stands for all categories of a cash flow total ("· ohne Kategorie" = transactions without a category
in that direction count too); a chip "Unklar: …" or with the name of a row = exactly the transactions behind a figure clicked
elsewhere (a cash flow figure, unclear transactions, the payments to a recipient). "ohne geschätzte Umsätze ohne Kategorie": the
figure clicked also counted transactions without a category that Kontor estimated into it; this list leaves those out, so its sum
can differ from that figure.

## transactions.hits — Treffer
"N Treffer … von M Umsätzen": N = transactions matching all filters; M = all transactions Kontor has read. "(erste 400 angezeigt
…)": only the newest 400 matches are listed – the Excel export contains all N.

## transactions.table — Umsätze
One row per transaction, newest first (booking date, then MoneyMoney's id). Checkbox: selection for assigning one category to
several at once (the blue bar above names how many are selected). Datum = booking date. Konto = MoneyMoney account. Name =
counterparty. Verwendungszweck = purpose (first 140 characters). Betrag = € with cents, signed as in MoneyMoney (negative =
outflow, red; positive = inflow, green). Kategorie = MoneyMoney's category ("A › B" = subcategory B of A); with ⏳ = assigned in
Kontor, waits to be written into MoneyMoney at the next sync at the Mac (already counts); "–" = needs no category (not a bank
account, pending, or one of Kontor's own bookings); orange "ohne" = no category yet. Hover box of the category: "aus MoneyMoney" or
"zugeordnet, wird in MoneyMoney eingetragen". Belege = number of receipts linked (green); "＋" = none yet. A transfer between two
accounts of the same area may show "ohne" although it needs no category (the filter "ohne Kategorie" leaves it out).

## transactions.detail — Umsatz (Seitenfenster)
One transaction. Heading: counterparty. Datum = booking date; Betrag = € signed (red outflow, green inflow); Konto = account · its
area; Zweck = purpose (first 140 characters); Kategorie = the category with its parent categories (or "ohne"; "–" for a transfer between own accounts, which needs none) · where it comes
from ("aus MoneyMoney", or assigned in Kontor and waiting to be written); Status = "gebucht" (booked by the bank) or "vorgemerkt" (pending), "· abgehakt" =
ticked in MoneyMoney; ID = MoneyMoney's id of the transaction. "Belege (N)": N receipts linked; each with its file name, tag "Mac"
= a link to a file outside the receipt folder (the file stays where it is), its size in KB (files in the folder) or "iCloud, nicht
geladen" / "fehlt" (linked file not on the Mac / not found), and the user's note below it. Below: ways to add a file (upload up to
60 MB, a file already in the receipt folder, or a link to a file on the Mac).
