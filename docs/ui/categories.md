# categories — Kategorisieren
Fills the gaps in the user's MoneyMoney categories: the categories are MoneyMoney's (Kontor has none of its own); what the user
assigns here Kontor writes into MoneyMoney's category field, after his click only. Three tabs, each with a count: "Offen (N)" =
booked bank-account transactions still needing a category (as of the last report: no category in MoneyMoney – its default
"Unkategorisiert" counts as none – and no assignment waiting; transfers between accounts of the same area and areas left out of
categorising not counted); "Regeln für MoneyMoney (N)" = number of rule proposals; "Eingetragen (N)" = number of categories Kontor
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
from another device that wait to be written at the next sync at the Mac (they already count in Kontor). "Alle Vorschläge übernehmen
(N)": N = transactions that have a suggestion and are not deselected. The card "Nichts offen" means no transaction matches.

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
The text field holds Kontor's suggestion. Tag "Vorschlag": every transaction of the group has the same suggestion. Tag "Vorschläge je
Umsatz": the transactions have different suggestions (shown per transaction in the expanded list). Suggestions are learned from the
user's own categories (MoneyMoney's and waiting assignments): by counterparty IBAN, by name, or by name plus the first three words
of the purpose – a pattern needs at least 2 transactions of which at least 90 % have the same category; the most specific match wins.
Kontor never applies a suggestion by itself. The button with the user's transfer category (only when the other side is an account
of another of the user's areas) assigns that category – for a contribution or withdrawal.

### categories.open.group.tx — Umsätze einer Gegenpartei
The group's transactions (newest first, at most 300): checkbox (ticked = included when assigning), Datum (booking date), Konto,
Zweck (the transaction's own name in bold where it differs from the group's, the purpose, MoneyMoney's booking text as a tag),
Betrag (€, signed: negative = outflow), and – only when the group has no common suggestion – "Vorschlag": the learned suggestion for
this transaction ("–": none).

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
