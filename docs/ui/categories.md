# categories — Kategorisieren
Fills the gaps in the user's MoneyMoney categories: the categories are MoneyMoney's (Kontor has none of its own); what the user
assigns here Kontor writes into MoneyMoney's category field, after his click only. Four tabs, each with a count: "Offen (N)" =
booked bank-account transactions still needing a category (as of the last report: no category in MoneyMoney – its default
"Unkategorisiert" counts as none – and no assignment waiting; transfers between accounts of the same area and areas left out of
categorising not counted); "Auffällig (N)" = groups of transactions whose category makes no sense to Kontor (see categories.doubts);
"Regeln für MoneyMoney (N)" = number of rule proposals; "Eingetragen (N)" = number of categories Kontor
has written into MoneyMoney (its log). The link "Cashflow-Positionen" leads to where each category counts in the cash flow – nothing
on this page changes a figure except through the category written into MoneyMoney.

## categories.open — Offen
The transactions without a category, grouped by counterparty (by its IBAN, else its name, else the first words of the purpose), sorted by
the size of the group's sum (largest absolute sum first), at most 300 groups. Only transactions that need a category: booked (not
pending), on accounts with the position Bankguthaben, not Kontor's own bookings (#kontor marks), not a transfer between two accounts
of the same area (counter IBAN of an own account in the same area, or paired with a counter-booking by the cash flow). Payments
between two of the user's areas do appear (a contribution, withdrawal, salary or rent needs a category).
Filters above the list: area chips (only ticked areas are listed and counted; the others' positions the cash flow estimates),
"Ignorieren vor" (optional day, saved in the settings as assign_ignore_before: transactions booked before it are neither listed nor
counted here nor in the overview's "Offen" -- the cash flow keeps estimating them; empty: all), year
(booking year; "alle Jahre"), "ab … €" (only transactions whose absolute amount is at least this). The note "N Umsätze ohne
Kategorie in MoneyMoney" counts the transactions matching these filters (not the groups). A blue banner counts assignments made
from another device that wait to be written at the next sync at the Mac (they already count in Kontor). "Alle sicheren übernehmen
(N)": N = transactions of the groups the level filter shows, not deselected, whose own suggestion is "sicher"; in the filter
"Wahrscheinlich" the button reads "Alle wahrscheinlichen übernehmen (N)" and N also counts "wahrscheinlich" ones; never "unsicher"
ones (no button in that filter). The card "Nichts offen" means no transaction matches.

### categories.levels — Wie sicher die Vorschläge sind (Filter)
A segmented filter: "Alle (N)" = all groups (counterparties, not transactions), "Sicher (N)", "Wahrscheinlich (N)", "Unsicher (N)" =
groups whose level is that (a group's level is that of its least sure transaction; a group without any suggestion counts as
"Unsicher"). Counted over all groups under the other filters, also beyond the 300 shown. Choosing one lists only those groups
(the 300 with the largest sums; then the note "Die N größten von M Gegenparteien"); "Keine … Vorschläge." when there are none.
"Sicher" lists only groups whose every suggestion is sure – sure suggestions in a mixed group count for "Alle sicheren übernehmen"
under "Alle".

### categories.progress — Fortschritt (sicher zugeordnet / geschätzt)
Above the note: a bar and "N von M Umsätzen sicher zugeordnet · P % des Betrags". M = the transactions under the same filters as the
list (ticked areas, "Ignorieren vor", year, "ab … €"; only those that need a category: booked, on bank accounts, not Kontor's own
bookings, not a transfer between accounts of the same area). N = of them, those with a category – MoneyMoney's or assigned in Kontor and
waiting to be written; the cash flow counts these where their category says (surely placed). M − N = the open ones the list shows; the
cash flow estimates their position (by the user's earlier categories or by name and purpose). P = the share of the absolute amounts
(signs ignored) of the N in those of all M, in euros only (accounts in another currency count in N and M but add no amount); rounded
down and at most 99 % while anything is open. The bar's length is that share. Everything placed: "Alle M Umsätze sicher zugeordnet".
Not shown when the filters leave no transaction.

### categories.open.group — Gegenpartei (eine Gruppe)
One counterparty. Bold: its name (or the start of the purpose). Grey: the accounts its transactions are in, and its IBAN. Tag "N×":
number of its open transactions; "n / N×" when only n of them are selected for assigning. Amount in € (green positive, red
negative): the sum of all its open transactions (all years matching the filters, inflows minus outflows) – not a monthly or yearly
value. Dates: first and last booking date of these transactions. A group of one transaction shows its purpose and MoneyMoney's
booking text as a tag.
The text field holds Kontor's suggestion when every transaction of the group has the same one. The coloured tag beside it is how
sure it is: "sicher" (green, at least 80 % likely right), "wahrscheinlich" (yellow, 60–80 %), "unsicher" (red, below – down to a
guess); for the group the level and percentage of its least sure transaction. Its tooltip: "Sicher – stimmt zu etwa P %" and the
reasons, strongest first. Tag "Vorschläge je Umsatz" (coloured like its least sure transaction): the transactions have different
suggestions (shown per transaction in the expanded list).
How sure: see categories.open.group.level. Kontor never applies a suggestion by itself. The button with the user's transfer category (only when the other side is an account
of another of the user's areas) assigns that category – for a contribution or withdrawal.

### categories.open.group.level — Wie sicher ein Vorschlag ist
The tag beside a suggestion; its tooltip: percentage and reasons. How likely: Laplace's rule of succession (k + 1) / (n + 2) for k of n comparable earlier transactions with that category. Comparable,
from the user's own categories (MoneyMoney's and waiting assignments), in the transaction's area where it has any there: the same
counterparty (IBAN, else name) in the same direction – all of them, or those with exactly this amount, or those on the same side of
the amount that best splits its categories ("unter/ab X €"; only amounts in the transaction's currency, its latest 2,000, not for an
amount between the two sides), or those with a word of this purpose. Where all of its past has one category: (k + 1) / (n + 2) of
all of it. Where its categories differ: of the transactions like this one, (k + p) / (n + 1) with p = the category's share of its
whole past (that past counts as one more transaction); the likeliest of these, and one for another category from 50 % as a reason
against it ("Spricht auch für …"); none like this one: (k + 1) / (n + 2) of all of it. Only earlier payments the other way: × 0.85.
A counter-booking: the opposite amount on another bank or hand-kept account within 5 days, in the same currency, without a category
(70 % if it is the only one within 2 days, else 60 %) or with a transfer category (85 %), or the counter IBAN is an account of the
user's (60 %) – suggests the user's transfer category; never where either booking names someone else's IBAN, both name different
counterparties, the amount is 0 or the cash flow paired the other booking already. A word of name or purpose that other counterparties had: k of n
counterparties (counted once each, at least 2, not this one) × 0.9. By meaning (only with the assistant on, the right "Zahlen und
Umsätze lesen" and its model for finding by meaning; the embeddings it already made, first 128 numbers): the 5 most alike other
counterparties with likeness ≥ 0.5 vote, × 0.8. A word in the name of one of the user's categories: 45 % (40 % if another category
matches as well). Nothing else: the most common category of income or spending (by cash flow position; never a transfer, saving or repayment) for this direction in the area – its share, at most 50 % (a guess). Two kinds of reasons for the
same category: the best plus half of what is left times the second; a reason of another kind for another category at 50 % or more
takes half of what it has above 40 % ("Spricht auch für …"). Levels: from 80 % "sicher", from 60 % "wahrscheinlich". Only categories
that exist in MoneyMoney are suggested.

### categories.open.group.tx — Umsätze einer Gegenpartei
The group's transactions (newest first, at most 300): checkbox (ticked = included when assigning), Datum (booking date), Konto,
Zweck (the transaction's own name in bold where it differs from the group's, the purpose, MoneyMoney's booking text as a tag),
Betrag (€, signed: negative = outflow), and – only when the group has no common suggestion – "Vorschlag": this transaction's
suggestion with a coloured dot for its level (green sicher, yellow wahrscheinlich, red unsicher; tooltip: percentage and reasons;
"–": none).

## categories.doubts — Auffällig
Booked bank-account transactions that have a category (MoneyMoney's or waiting) which makes no sense to Kontor – coarse outliers,
for the user to look at; nothing changes by itself. Same scope as "Offen" (areas ticked there, "Ignorieren vor"; all years; a
transfer category on a booking the cash flow paired is never doubted). Tab count and note: N = groups (tab) / transactions (note).
Doubted when, as if the transaction had no category, (1) Kontor's suggestion for it – the same as under "Offen", without meaning –
is another category at least 60 % likely (at least 80 % where the counterparty has no past of its own and only a word other
counterparties had speaks), and (2) what is comparable gives the category it has under 10 %: (k + 0.5) / (n + 1) for k of n with it –
the base is all of the counterparty's past (none of 5 or more, one of 15, two of 25), else the word Kontor's suggestion rests on; a
smaller set (exactly this amount, a word of the purpose, a side of the split by amount, any word others had) counts only where it
has the category. Not doubted: a category Kontor gives some chance (30 % for B while it suggests A at 60 %), one whose name matches
a word of the transaction, a transfer category with a counter-booking, too little to compare. Groups per counterparty, category
and Kontor's suggestion, the surest doubt first, at most 300.

### categories.doubts.group — Auffällige Gegenpartei
Bold the counterparty, grey accounts and IBAN, "N×" its doubted transactions with this category, their sum (signed). "Jetzt:" the
category they have (tooltip: about P % – what everything comparable gives it); "Kontor würde vorschlagen:" Kontor's suggestion
with its level tag (tooltip: percentage and reasons, counted without these transactions). The field holds that suggestion;
"Ändern" / "Alle N ändern" writes the category into MoneyMoney – replacing MoneyMoney's own only after the question every
replacement asks. "Passt so" keeps them out of this list while they keep this category (stored in categories.json: doubt_ok).
"Umsätze ▾": date, account, purpose, amount.

## categories.rules — Regeln für MoneyMoney
Proposed rules for MoneyMoney (Kontor cannot create rules there), sorted by how many still-open transactions they would catch, at
most 60. Each: bold the category; "aus N Zuordnungen" = how many transactions of this counterparty the user assigned this category
in Kontor (written by Kontor or waiting) – at least 2; "trifft N Umsätze" = how many booked transactions the rule would match;
"N davon noch ohne Kategorie" = of those, how many have no category yet. The code is the rule in MoneyMoney's search syntax:
remote_account:"IBAN" (counterparty), name:"…" (start of the name with *), purpose:"…" (words only this category's transactions
have, when the counterparty also has other categories), amount<0 / amount>0 (direction). Proposed only if it matches no
transaction of another category, the category exists in MoneyMoney, and MoneyMoney did not categorise the newest match itself
(then a rule evidently exists). "Erledigt" removes a proposal for good. The card "Keine Vorschläge": nothing qualifies yet.

## categories.written — Eingetragen
Every category Kontor wrote into MoneyMoney, newest first (at most 2,000 rows; "N Einträge" = all). Columns: checkbox (only for
rows that can be taken back, at the Mac or on an added iPhone), "Eingetragen am" (date and time Kontor wrote it), Datum (booking date of the
transaction; "–" if it is outside what Kontor reads), Konto, Name (counterparty), Betrag (€, signed), Vorher (the category before
Kontor's – "ohne Kategorie" if none), Eingetragen (the category Kontor wrote). A pale row with a tag cannot be taken back: "in
MoneyMoney geändert" = MoneyMoney now shows another category (it stays); "nicht im Abgleich" = the transaction is outside what
Kontor reads. Taking back gives MoneyMoney the category from before (none: "Unkategorisiert").
