# bookings — Auto-Buchungen
What the booking rules (loans, participations, account mirrors) want to book into the user's offline accounts in MoneyMoney and
what they have booked. The chip at the top right says which mode applies: "Mit Freigabe" (every booking waits here for the user's
approval) or "Vollautomatisch" (each sync books what is new since the last check; older ones still wait). "Freigeben (N)": N =
bookings ticked for booking. Every amount on this page is a booking into an offline account, signed as in that account: positive
raises its balance, negative lowers it (a debt is a negative balance, so a repayment is positive and interest negative). The
user's bank transactions are never changed here.

## bookings.list — Wartet auf Freigabe / Zuletzt geprüft
Heading "Wartet auf Freigabe N": N bookings from the last check wait for approval – not in MoneyMoney yet. Otherwise "Zuletzt
geprüft <date, time> · N gebucht": when the rules were last checked and how many bookings that check wrote; the table then lists
what it booked ("Keine Buchungen nötig." when nothing). A red pill beside the heading: writing stopped with this error.
Columns: checkbox (only while waiting, at the Mac or on an added iPhone: ticked = booked on approval, unticked = left out this time and keeps
waiting); Datum = the booking date it gets (for loans editable); Konto = the offline account booked into, its area small below;
Art: "Rate (Tilgung)" = a loan payment found on the source account, booked onto the loan account as repayment (the payment with
reversed sign); "Zinsen" = one month's interest on the loan account (negative for a debt: it grows; positive for a receivable);
"Wertanpassung" = participation account: the difference between its target (share × the company's net worth) and its balance on
that day; "Kontenspiegel" = a booking of the source account copied with reversed sign. Betrag = € with cents, green positive, red
negative; struck through when "entfällt". Last column: pencil (change) and ✕ (do not book – moves it to "Nicht gebucht").
Leaving out or changing a booking moves every later balance of that account, so Kontor recalculates the list at once (nothing is
booked by that) and books exactly the amounts shown; if MoneyMoney changed meanwhile, it books nothing and shows the new ones.

### bookings.list.text — Text
The purpose the booking gets in MoneyMoney, shown without Kontor's mark (#kontor-…, added when booked). By default: repayment
"Annuität 01.10.2026 von <source account>" (kind of payment, its date); interest "Zinsen 10/2026 · 3 % p.a. auf 1.200.000,00 €"
(month, rate, base = the debt the interest is computed on: yearly model the debt on 31 Dec of the year before, monthly model the
debt at the end of the month before); value "Anteilswertanpassung: 40 % × 133.000,00 € (Wert <company>) = 53.200,00 €" (share ×
company value = the target balance – the amount booked is only the difference to the current balance); mirror "<original text> ·
gespiegelt von <account>". Grey line below: the rule's name · the category the booking gets.
Tags: "geändert" = changed here, not booked yet; "angepasst" = amount recalculated because another booking was left out or changed
(the next value adjustment, for loans the later interest, makes up for it); "neu" = added by that recalculation (the difference that
would otherwise stay open); "älter" (fully automatic mode only) = dated before the last check – backdated, or deleted again in
MoneyMoney – or interest building on it: booked only with approval; "prüfen" = Kontor wants a look first, the line below says why
(a rule from the assistant or a backup not yet confirmed, or a hand-entered booking that may be the counterpart of a mirror) –
starts unticked; "entfällt" = not needed any more with the selection (the balance is right already); "wartet" = interest waiting
for an unticked booking before it (it is computed from the balance before), comes back with it. A pale row: unticked or "entfällt".

## bookings.notes — Hinweise
Warnings of the last check, one per banner, in words with their own figures: e.g. no matching loan payment for 35 days or since a
date, a repayment of Kontor's whose payment is gone, interest booked twice or not matching the debt or rate any more (with the right
amounts per month), a company's value unknown (foreign currency), a balance after booking other than expected, MoneyMoney changed
meanwhile so nothing was booked, a category missing in MoneyMoney (booked without it), a rule that failed.

## bookings.calc — Rechenwege (N)
N = number of lines: how the rules computed, without warnings. E.g. "<rule>: Zinsbasis 2026 = 1.200.000,00 €, 3 % p.a. =
36.000,00 €/Jahr" (yearly model: debt on 31 Dec of the year before × rate = yearly interest, one twelfth per month, December with
the cent remainder); interest the user booked himself (Kontor books nothing for those months); a company's value unknown for some
months (not booked); a loan without interest rate (no interest bookings); no payment yet in the first 35 days; an account renamed
in MoneyMoney (found by its number).

## bookings.rejected — Nicht gebucht (N)
Bookings the user decided not to book (✕), newest first; N = how many. Kept in the settings (so also in backups), never booked
while listed. Columns: Datum, Konto (area below), Art, Betrag (€ as shown when rejected), text without mark with the rule's name
below, and "Wieder vorschlagen" (takes it off the list; if still needed it waits for approval again).

## bookings.created — Von Kontor angelegt N
The bookings in MoneyMoney that carry Kontor's mark – read from MoneyMoney at every sync (Kontor keeps no list of its own), newest
first; N = how many (at most 500; the table shows 300). Columns: Datum, Konto (area below), Art (from the mark), Betrag (as it stands
in MoneyMoney now – a change made there counts), Text (purpose without the mark, else the counterparty), Markierung: #kontor-tx-<id>
= repayment for the payment with that MoneyMoney id; #kontor-zins-2026-10 = interest for that month; #kontor-wert-20261104-1 = value
adjustment of that day; #kontor-gk-<id> = mirror of the booking with that id.

## bookings.history — Verlauf (N)
One row per check of the rules, newest first (at most 100; N = how many): Zeit = date and time; Vorschläge = bookings the rules
planned in that check; Gebucht = bookings written into MoneyMoney in it (0 while waiting for approval); Fehler = why writing stopped.
"Aktualisieren" (only the rule accounts read again) adds no row.
