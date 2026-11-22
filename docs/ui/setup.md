# setup — Einrichtung
A guided way through the pages that set Kontor up – not a store of its own: each step opens the page where it is done (Konten &
Regeln, Einstellungen, Immobilien, Planung, Kategorisieren). It stays in the menu until the user closes it ("Einrichtung
abgeschlossen"); while it is open, the pages it leads to carry a slim line "‹ Zurück zur Einrichtung · Weiter zu … ›".

## setup.language — Sprache · Language
The language of Kontor (Deutsch or English), as under Einstellungen → Allgemein; the assistant answers in it too.

## setup.steps — Schritte
One row per step, numbered (✓ when done), with a pill "eingerichtet" (done), "offen" (needed, not done) or "optional", and a
button "Einrichten" or "Anpassen" leading to its page. Steps and when they count as done:
- **Als App im Dock** (optional): Kontor in its own window – Kontor's Mac app, or the browser's way to install it (the row says
  how on this device).
- **MoneyMoney**: MoneyMoney runs, is unlocked and macOS allows the access; done once accounts were read.
- **Bereiche**: which accounts belong together (private, each company) → Konten & Regeln → Bereiche.
- **Konten**: confirm area, position and history source of every account; done when no account is new.
- **Historische Kontostände** (optional): the history of balances once from MoneyMoney's database.
- **Buchungsregeln** (optional): loans, participations, account mirrors; done when there is at least one rule.
- **Cashflow-Positionen** (optional): where each category counts; done when one position is chosen.
- **Immobilien**, **Planung**, **Steuer**, **Belege**, **iPhone-Zugriff**, **KI-Assistent** (switched on and a model ready),
  **Kategorisieren** (no transaction without a category), all optional.
- **Abgleich**: automatic sync and how far back Kontor reads (Einstellungen → MoneyMoney-Sync).

## setup.finish — Einrichtung abgeschlossen / prüfen
"Einrichtung abgeschlossen" hides the setup from the menu (possible once the needed steps – those without "optional" – are done);
afterwards "In der Seitenleiste zeigen" brings it back. "Einrichtung prüfen" reads MoneyMoney and checks that every account and
category the areas, rules, properties, cash flow and tax refer to still exists there (e.g. after renaming); the findings stand
below. It changes nothing.

## setup.report — Erste Auswertung erstellen
Shown before the first report exists: "Auswertung erstellen" reads all transactions from MoneyMoney and builds Übersicht,
Bilanz, Cashflow, Planung and Steuer. Afterwards Kontor keeps them up to date itself (after every change and every sync).
Nothing in MoneyMoney changes.
