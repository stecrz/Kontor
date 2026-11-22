# accounts — Konten & Regeln
Everything that decides the user's figures: which accounts belong to which area and balance-sheet position (Konten, Bereiche),
where month-end balances come from (Kontostände), in which cash-flow line each MoneyMoney category counts (Cashflow-Positionen),
what Kontor books by itself (Buchungsregeln) and the basis of the tax overview (Steuer). Six tabs; the page has no area switch and
no period – it shows settings for all areas at once. Changes count after "Speichern" (Buchungsregeln: "Speichern und prüfen");
then Kontor recalculates every page. Nothing here changes MoneyMoney, except that saved booking rules let Kontor book into
offline accounts (see accounts.rules).

## accounts.accounts — Konten
One row per account of MoneyMoney (no groups): its area, balance-sheet position, source of its history, online/offline,
display. Above the table: a field "„Nach Aktivität“: ausblenden ohne Bestand und Umsatz seit N Monaten" (default 12; 0 = never
hide by itself) and a switch "ausgeblendete hier zeigen" (hides grey rows on this page only). A banner names accounts not yet
confirmed ("noch nicht bestätigt"). Saving fixes area, position and history source for every listed account: renaming or moving an
account in MoneyMoney later changes nothing.

### accounts.accounts.table — Kontentabelle
Rows grouped by area: a shaded heading row with the area's name (order as under Bereiche; accounts without an area last, "ohne
Bereich"); within an area the accounts in MoneyMoney's order.
- **Konto**: the account's name; small below it its groups in MoneyMoney and its kind (Depot, manuell = kept by hand/offline, else
  MoneyMoney's account type). Tags: "neu" = not confirmed yet (the values shown are Kontor's proposals); "ausgeblendet" = hidden on
  the other pages (row grey, still counted in every sum); "veraltet?" = a balance other than 0 but no booking and no refresh for
  N months (hover: balance and since when) – maybe a closed account.
- **Bereich**: the area the account counts in; a choice here wins over the groups ticked under Bereiche. "– wie unter Bereiche –" =
  no choice of its own: it counts in the area whose group contains it, else nowhere (then under "ohne Bereich").
- **Position**: balance-sheet position (Bankguthaben … Verbindlichkeiten, "Avale & Bürgschaften" and "nicht bilanzieren" outside
  net worth). It also decides how the account's transactions count in the cash flow (cash: income/expenses; loans:
  interest/repayment; securities, real estate, participations, tangibles: investing/value changes).
- **Verlauf**: where month-end balances come from – "Umsätze" (today's balance minus all later booked transactions; default for
  bank accounts) or "Kontostände" (entered or imported balances are anchors, months between are computed with the bookings;
  default for portfolios). The button "Verlauf" opens the account's month-end balances.
- **Art**: "Online" = MoneyMoney fetches it from a bank or service; "Offline" = kept by hand – only these accounts Kontor ever books
  into. Detected by Kontor (hover: why, last fetch); a change here is saved at once. "–": not known.
- **Anzeige**: "nach Aktivität" (hidden while it had neither balance nor transaction for N months), "immer anzeigen", "ausblenden".
- **Saldo**: the account's current balance in MoneyMoney as last read (not a month-end value), with cents, in the account's own
  currency without a currency sign (Kontor never converts); red below 0, green otherwise.
In the Bereich, Position and Verlauf menus "(Vorschlag)" marks Kontor's proposal (from name, type, group, portfolio); a dashed
border means the proposal is chosen, a solid border the user's own choice.

## accounts.areas — Bereiche
One card per area (Bereich): a set of accounts with its own balance sheet, cash flow, planning and tax overview. Without saved
areas each top-level group in MoneyMoney is proposed as one. Fields of each area:
- **Name**.
- **Art**: "privat" or "Gesellschaft (GbR, GmbH …)" – proposed from the name (GmbH, GbR, UG, Holding …). Only companies appear under
  Buchungsregeln → Beteiligungen.
- **Hauptbereich** (ja/nein): exactly one area; preselected on Übersicht, Bilanz, Cashflow and Planung, and the private person in
  the tax overview.
- **Anteil** (companies only, %): the user's share of the company. Kontor values the participation with it (share × the
  company's net worth) and the tax overview takes this part of the result. Empty: tax 100 %, the participation is not valued.
- **Konten / Gruppen**: the tree of MoneyMoney; a ticked group includes every account below it, also ones created later (shown
  ticked and locked). An account in no area counts nowhere.
▲ ▼ set the order of the areas in the area switch at the top of the pages. "Entfernen" deletes an area (not its accounts).

## accounts.history — Kontostände
Where the history of balances comes from beyond what MoneyMoney's interface gives: once from MoneyMoney's database file, for
portfolios from Kontor's own monthly records, and from a file with month-end balances. Each month-end balance taken over counts
for its month; Kontor never estimates – a month without a known value is "unbekannt".

### accounts.history.moneymoney — Aus MoneyMoney übernehmen
Three steps, only directly at the Mac (elsewhere a note says so): quit MoneyMoney (green dot when it is quit), show the file
MoneyMoney.sqlite in Finder, drop it here and type MoneyMoney's password in a macOS window. Kontor decrypts only in memory, checks
the values against today's balances and keeps only month-end balances per account (encrypted). A banner "Übernommen am …" names
when, how many accounts and the months covered; reading again replaces those values. Nothing in MoneyMoney changes.

### accounts.history.securities — Namen der Wertpapiere
Shown after the database was read. "N von M Wertpapieren haben ihren Namen aus MoneyMoney" (also sold ones). Securities MoneyMoney
knows only by ISIN can be looked up once at OpenFIGI on a click ("Namen nachschlagen"; only the ISINs are sent, listed when
unfolded); "Nachgeschlagen: X gefunden, Y ohne Treffer (zuletzt …)". "Alle Namen ansehen und ändern": every ISIN with the name
Kontor uses (the user's own, else MoneyMoney's, else the looked-up one; hover the ISIN: the name in MoneyMoney). Names are kept in Kontor only.

### accounts.history.depots — Depots: Wertverlauf
MoneyMoney gives only a portfolio's current value, not its history; Kontor records the value at every read for the month-end
("seit …" in the note: the first month Kontor recorded). Table, one row per portfolio:
- **Depot** (its groups below), **Bereich**.
- **Bekannt ab**: the first month with a known value (month and year, e.g. "Okt 24"), from any source; "(aus MoneyMoney)" = there
  are values from MoneyMoney's database, "(N eingetragen)" = N months entered or imported by the user; "–": none known – before
  that month the balance sheet shows the portfolio as unknown.
- **Stände eintragen**: opens the month-end values to enter missing ones.
A banner "Möglicherweise fehlen Depotstände" names portfolios and months where MoneyMoney fetched while Kontor was not running, so
a month-end value may be missing.

### accounts.history.import — Saldenverlauf importieren
Month-end (or daily) balances from a CSV or Excel file: a list (date, account, balance) or a table with dates in the header row or
the first column; per month the last value counts. After a file is dropped a card shows, per column/account found in the file:
**In der Datei** (its name), **Monate** (number of months with a value), **Zeitraum** (first – last month), **Konto in Kontor**
(the account it goes to; "Vorschlag" = matched by name similarity, to check; "nicht übernehmen" = left out). "nur Monate übernehmen,
für die noch kein eigener Wert eingetragen ist" keeps existing own values. Imported values are own month-end balances: for
portfolios and accounts set to "Kontostände" they are the anchors; for an account computed from transactions they replace only
that month, not the back-calculation.

## accounts.positions — Cashflow-Positionen
Where each category of MoneyMoney counts in the cash flow (the same outline for every area). Only categories with booked
transactions in the user's areas are listed. Choices count after "Speichern"; the cash flow is then recalculated. MoneyMoney's
categories are never changed; Kontor creates none.

### accounts.positions.needs — Was Kontor von deinen Kategorien braucht
A folded card; its title shows "X von Y vorhanden". One row per need – Einkommen, Kapitalerträge, Wohnen, Lebenshaltung, Weitere
Ausgaben, Sparen & Anlegen, Darlehen (Tilgung and Zinsen), Umbuchung; with a property also "Immobilie: Miete und Kosten" and
"Immobilie: Kauf". ✓ = at least one of the user's categories counts there (named, "und N weitere"; "fehlt noch: …" when only part of
a need is covered); ○ = none yet, with an example of a category to create in MoneyMoney. It follows the table below live.

### accounts.positions.table — Kategorien und Positionen
One row per category, indented under its parent (parents in bold).
- **Kategorie in MoneyMoney**. Tag "zwischen Bereichen": a category without a chosen position that has payments between two of
  the user's areas – those count as contribution or withdrawal until a position is chosen (hover: the amount).
- **Umsätze**: number of booked transactions with this category or one below it, in all areas, over all months read (a click lists
  them).
- **Letzte 12 Monate**: their sum from the same day a year ago up to today, whole euros, inflows positive, outflows negative (red);
  a click lists them.
- **Position im Cashflow**: the position it counts in. The empty choice is automatic and names its result: "… (automatisch)" =
  the choice of the nearest parent, else Kontor's proposal from the name (two names: the areas count it differently); "Je
  Unterkategorie (automatisch)" = each subcategory on its own; a property's category: its own rows "Immobilie …" unless set to
  saving, financing or left out. "Umbuchung" = between the user's own accounts or areas, neither income nor expense; "Nicht
  berücksichtigen" = counts in no line (then shows as a difference in the reconciliation with the balance sheet). A choice of the
  user also counts for the categories below without their own.
- **Zielkonto** (only with "Sparen & Anlegen"): the account the money goes into – "nicht nötig" (the money arrives on own accounts,
  Kontor sees the counter-booking), "automatisch: <Konto>" (found), "fehlt – bitte wählen" (marked; choose one).

### accounts.positions.recipients — Zielkonto je Empfänger
Shown when payments under "Sparen & Anlegen" arrive on none of the user's accounts (e.g. a portfolio or pension kept only by its
balances). Per area (heading with its name when there are several) one table; a pill "N ohne Zielkonto" counts open rows.
- **Empfänger** (with IBAN), **Kategorie** (the saving categories of these payments).
- **Umsätze**: number of payments; **Summe**: their total in whole euros (outflows negative) – both over all months of the area's cash
  flow; a click lists them.
- **Zielkonto**: "automatisch: <Konto>" (Kontor's choice: the category's target account, else the area's only portfolio), "je nach
  Kategorie", "Bitte wählen" (no target known; row marked), an own account, or "Kein Konto in MoneyMoney" (the money leaves the
  wealth Kontor sees). "Vorschlag: <Konto>" is a proposal that counts only once taken and saved.
Without a target the net worth is still right; the payment then shows in the cash flow as value change "Anlage ohne Zielkonto"
instead of being split into payment and gain.

## accounts.rules — Buchungsregeln
What Kontor books by itself into the user's offline (manual) accounts in MoneyMoney – never into bank accounts, never transfers.
Each booking carries a mark like "#kontor-zins-2026-10"; the list of bookings waiting or made is the page Auto-Buchungen (link in
the first line, with the number waiting for approval). Three kinds of rules below; one save bar for all ("Speichern und prüfen"
checks them against MoneyMoney; "Alles gespeichert." when nothing is changed). The figures beside each rule are computed live from
the rules as edited, before saving. A rule made or changed by the assistant carries "Noch nicht bestätigt – Buchungen erst nach
Freigabe" and a button "Bestätigen": until confirmed and saved, each of its bookings waits for approval.

### accounts.rules.auto — Vollautomatisch buchen
A switch (changeable only at the Mac). On: at every sync Kontor books by itself what is new since the last check (only offline
accounts) and reports it; older bookings still wait for approval. Off (default): bookings are proposals waiting under
Auto-Buchungen for the user's approval.

### accounts.rules.loans — Manuelle Darlehen
For loans kept in MoneyMoney as an offline account: Kontor recognises each instalment on the paying account and books it as
repayment on the loan account, plus interest each month. Each loan is one foldable row: its name, "→ <Darlehenskonto>", then its
state – "✓ aktuell" (nothing to book) or "N Buchungen offen" (bookings the rule would make now; a click lists them in the side
panel); "aus" = rule switched off (kept, books nothing). Unfolded fields:
- Name; Aktiv. **Konten**: Darlehenskonto (offline account), Zahlungen von (paying account), Art – Verbindlichkeit (the user pays)
  or Forderung (the user receives).
- **Rate erkennen**: IBAN der Gegenseite, oder Text enthält (text in the purpose), Ausschließen, wenn Text enthält.
- **Zinsen**: Zinsmodell – Jahresbasis (rate × balance on 31 Dec of the year before, 1/12 per month), Restschuld monatlich (rate/12 ×
  balance of the month before), or keine Zinsen (instalments only); Zinssätze with start dates ("2026-01-01: 3,3"); Zinsbuchung (on
  the instalment's day or Ultimo); Zinsbasis erzwingen (a base per year).
- **Buchung**: Buchen ab (instalments from this day), Gegenpartei, Kategorie Tilgung, Kategorie Zinsen.

### accounts.rules.companies — Beteiligungen
One card per area of the kind "Gesellschaft". It keeps the user's participation account at share × value of the company; Kontor
books only the difference to the balance in MoneyMoney. Head: the company's name and a pill "Anteil 49 %" (from Bereiche; "Anteil
fehlt": nothing is valued).
- **Beteiligungskonto**: the user's offline account with position Beteiligungen for this company ("– keine –": no bookings).
- **Buchungshäufigkeit**: täglich (the difference at every sync, dated today) or monatlich (one booking at each month-end); a hint
  says which fits "Vollautomatisch buchen".
- **Buchen ab**: from a day, or "alles" since the company's first booking – the whole period is checked, missing days are booked
  (past ones wait for approval).
- **Mindestdifferenz** (€): smaller differences are not booked. **Gegenpartei**: name on the bookings (empty: the company's name).

### accounts.rules.companies.preview — Soll und Ist
The line under the participation account, today:
- **Soll**: what the participation account should show now = share × the company's value, "(= 49 % × X € Wert der Gesellschaft)"
  – the value is the sum of all balances of the company's accounts today (assets minus debts; partners' capital accounts count as
  debts; guarantees and "nicht bilanzieren" left out).
- **Ist**: the participation account's balance in MoneyMoney now.
- "✓ aktuell": nothing to book; else "N Buchungen offen": the bookings the rule would make (over the whole period from "Buchen ab",
  not only today; a click lists them). No separate difference is shown – the amounts are those bookings.
- "unbekannt: 05/2026, …": months whose value is not known (e.g. a portfolio without history) – skipped, nothing estimated.
Soll stays empty when a company account is in a foreign currency (value unknown).

### accounts.rules.mirrors — Kontenspiegel
Pairs of any two accounts showing the same thing from two sides (e.g. a capital account in the company and the user's claim on
it): every booking of one comes into the other with the opposite sign on the same day. Each row: account A ⇄ account B (each chosen
by area, then account), "Buchen ab" (a day, or "alles" = every booking of both), and its state: "in beide Richtungen" or "nur in
<Konto> (das andere ist ein Bankkonto)", "N gespiegelt" (pairs already matched), then "✓ aktuell" or "N Buchungen offen".

## accounts.tax — Steuer
The basis of the tax overview (page Steuer), for all areas:
- **Vermietungs-Oberkategorie** (default "Vermietung"): the MoneyMoney category whose subcategories are the rental properties, each
  with its kinds below ("Vermietung › <Objekt> › <Art>") – the tax overview reads rent and costs per property from them.
- **Darlehen → Objekt**: one row per account with the position Verbindlichkeiten (its groups below); the property it finances, named
  as in the rental category – its interest then counts as that property's interest on debt. "keine Darlehenskonten erkannt": no
  account with that position.
- **Kategorie → Steuerposition**: pairs of a category (or a parent category, for everything below it) and the tax position it
  counts as (e.g. "Sonderausgaben / Vorsorge") – for the main (private) area; a company's positions are its top-level
  categories.
Saved with "Einstellungen speichern".
