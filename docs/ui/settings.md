# settings — Einstellungen
How Kontor works – nothing here changes a figure (what decides the figures is under Konten & Regeln). Tabs: Allgemein,
MoneyMoney-Sync, Zugang, Belege, KI-Assistent, Updates, Sichern & Zurücksetzen. Most fields count after "Einstellungen
speichern" (⌘S); Allgemein and the assistant's settings take effect at once. Many settings can be changed only directly at the
Mac (elsewhere they are greyed out with "nur am Mac"). The assistant never reads or changes this page.

## settings.general — Allgemein
- **Sprache · Language**: Deutsch or English for the interface, messages and the assistant's answers.
- **Erscheinungsbild**: Dunkel, Hell or Wie das System – for this device only.
- **Als App**: Kontor in its own window with an icon in the Dock: at the Mac Kontor's own app ("Mac-App öffnen"; it is built on
  the Mac), in Chrome/Edge an install button, in Safari and on the iPhone the way to add it ("Zum Home-Bildschirm").

## settings.moneymoney — MoneyMoney-Sync
The connection to MoneyMoney, how current the data is and when Kontor reads. Kontor reads through MoneyMoney's script
interface only while MoneyMoney runs and is unlocked; it never starts MoneyMoney.

### settings.moneymoney.connection — Verbindung
Two steps: "MoneyMoney läuft" (dot green: running and unlocked; amber: locked; grey: not running) and "Zugriff erlauben und
Konten lesen" – macOS asks once whether Kontor (python3) may control MoneyMoney (Automation); "Verbindung prüfen" reads accounts
and categories (progress bar). Once connected the section is folded ("MoneyMoney verbunden, Konten gelesen").

### settings.moneymoney.sync — Datenstand
Cards: **MoneyMoney** (running / locked / not running; without reading Kontor works with the last data read), **Banken →
MoneyMoney** (the newest fetch from the banks in MoneyMoney – started in MoneyMoney, by hand or its schedule), **MoneyMoney →
Kontor** (when Kontor last read; automatic every N minutes or off), **Regeln zuletzt angewendet** (with booking rules). Buttons:
"Jetzt synchronisieren" (reads new transactions, applies the rules, updates every page), "Alles neu lesen" (reads all transactions
again – needed when something older changed in MoneyMoney). Below: when everything was last read and every how many days.
Banners: accounts more than a day behind the newest bank fetch (e.g. a TAN needed); MoneyMoney ran but Kontor could not read.

### settings.moneymoney.schedule — Abgleich
- **Automatischer Abgleich**: on/off, every N minutes (default 30; at least 5) – only while MoneyMoney runs and is unlocked; also
  soon after MoneyMoney has new data.
- **Alles neu lesen**: every N days (default 30) a complete reading; a normal sync reads the last 30 days and takes older
  transactions from the last complete reading (it reads everything at once when a balance does not fit).
- **Umsätze lesen**: the last N months (0 = all, recommended) – applies to every page (history, cash flow, planning, tax).

## settings.access — Zugang
Who can open Kontor and how. Kontor listens only on this Mac (127.0.0.1) and, if switched on, in the user's private Tailscale
network – never the open network. Data opens only after signing in.

### settings.access.mac — Am Mac
- **Automatische Sperre**: after N minutes without activity (default 15) Kontor locks; signing in again opens it.
- **Touch ID**: sign in at the Mac with Touch ID (or Apple Watch) instead of the password; on an added iPhone Face ID instead.
- **Erweitert: Adresse, Port, Zertifikat**: address (127.0.0.1 or a Tailscale address 100.x.y.z), port (default 8765), TLS
  certificate and key for https. Saving restarts Kontor under the new address.
- **Passwort**: change Kontor's password (old and new; with Touch ID the old field may stay empty).

### settings.access.iphone — Zugriff vom iPhone
Off: reachable only at this Mac. On: reachable on the user's devices in the Tailscale network at the address shown, with "Wer"
(who may sign in: added iPhones with Face ID, or also Kontor's password; Tailscale account and devices), "Wo" (from anywhere,
no open port), "Was" (only view, or changes with Face ID), "Verschlüsselung" (certificate valid until …). Setting up: five
steps (Tailscale on Mac and iPhone, MagicDNS and HTTPS certificates, "Zugriff einschalten", open and add to the Home screen).
"Absichern (empfohlen)": a Tailscale access rule so that only Kontor's port is reachable on this Mac, with a check of the
current state; below it, read from Tailscale (Kontor changes nothing there): whether Tailnet Lock is on (new devices only
with the user's signature). In red at the top of this part while "tailscale serve" or Funnel passes Kontor's port on (requests
would seem to come from the Mac itself, or from the internet): sign-in and what stays at the Mac are locked on the Mac until
it is switched off – the command is named; every session signed in at the Mac ended when it was found. Only forwarding to
this Mac counts; Tailscale not running passes nothing on. **Änderungen vom iPhone**: "Nur ansehen" or "Mit Face
ID ändern" – then an added iPhone may do what the Mac can, each change confirmed with Face ID; access and devices, updates,
setting up the assistant, loading a backup, reset, password and data key stay Mac-only. **Anmeldung unterwegs**: "Nur mit
Face ID hinzugefügter iPhones" (default once one is added; the password then opens the data from the iPhone only once after
the Mac restarted). **Offline-Ansicht**: the iPhone app may keep the data last loaded and show it read-only when the Mac is
not reachable.

### settings.access.devices — Geräte
Only at the Mac. The iPhones added, each with its own passkey (Face ID): name typed when it was added, "Hinzugefügt" (date and
time), "Zuletzt" (last sign-in or confirmed change; "–" never), "Ändern" (ticked: this iPhone may change things with Face ID,
while "Änderungen vom iPhone" is on), a mark "andere Adresse" when it was added for an earlier address of the Mac (its Face
ID no longer works there), "Entfernen" (signed out at once, also a demo it opened; its passkey no longer works). A red note
when the list was damaged and set aside (file name; until iPhones are added again nobody signs in remotely).
"Gerät hinzufügen" (only with https) shows a QR code of a one-time link (valid 10 minutes, the minutes left shown; a new link
or locking Kontor at the Mac ends it) and "Änderungen vom iPhone erlauben (mit Face ID)" for this iPhone (the very first
iPhone added with it ticked also switches "Änderungen vom iPhone" on).

## settings.receipts — Belege
- **Belegordner**: where receipt files are stored as ordinary files (default ~/Documents/Kontor-Belege; may be in iCloud Drive);
  created with the first receipt.
- **Unterordner-Muster**: subfolders by placeholders {year}, {month}, {entity} (area name), {account}, e.g. "{year}/{entity}".
Receipts are linked to transactions only in Kontor; MoneyMoney gets no reference.

## settings.assistant — KI-Assistent
The language model on this Mac: program, models, operation, memory and rights. Only at the Mac; settings take effect at once.
"KI-Assistent verwenden" switches it on (then the ✦ button and the menu entry appear).

### settings.assistant.program — Programm
llama.cpp, the free program that runs the models on this Mac: installed version and date, "Installieren", "Aktualisieren" (a
newer version is shown), "Entfernen". Loaded from GitHub only on a click; a progress bar with size, speed and time left.

### settings.assistant.models — Modell für Antworten
The models that answer, from Hugging Face, in groups by what each is for: "Gründlich – für Zahlen, Dokumente und Recherche"
(reads long documents and figures most reliably, answers more slowly), "Schnell – für kurze Fragen" (about four times as fast,
less reliable with long documents), "Klein – nur für einfache Fragen" (small models often guess instead of saying that they do
not know), "Andere Modelle" (what the user loaded himself: any GGUF file by "provider/name", "Dateien zeigen"). Per model: its
name (hover: repository and file), one line on what it is good at, then maker, licence (hover: what it allows), file size ("ca."
before it is loaded), the memory from which it runs well ("ab … GB Arbeitsspeicher") and how it sits in this Mac's memory:
"läuft gut auf diesem Mac", "läuft knapp auf diesem Mac" (runs, needs most of the memory), "zu groß für diesen Mac" – or, not
loaded yet, "braucht einen Mac mit mindestens … GB Arbeitsspeicher": such a model cannot be loaded. "empfohlen": the most thorough
model that runs well on this Mac (right answers before speed); none on a Mac where only the small ones run. Kontor never changes
the model in use by itself. Marks "geladen", "neuere Datei"; the dot chooses the model in use; "Laden", "Aktualisieren", "Löschen".

### settings.assistant.dictation — Modell zum Diktieren
A second, small model that only turns speech into text (accurate or smaller); the dot chooses it. "Diktiermodell starten": with the
assistant (ready at once, uses 1–3 GB memory) or on the click on the microphone. "Mikrofonfilter": the Mac's echo and noise filter
on (about two seconds until it hears after a pause) or off (hears at once). Below: whether the microphone is allowed.

### settings.assistant.meaning — Suche nach Bedeutung
A third, small model that writes nothing but compares texts: notes, help and transactions are then found by meaning too
("Ferien" finds "Urlaub"). It starts and ends with the answering model.

### settings.assistant.updates — Aktualisierung und Ablage
**Automatisch suchen**: how often Kontor asks GitHub and Hugging Face for a newer llama.cpp or newer files of the models loaded –
täglich, wöchentlich, monatlich (default), nie; nothing of the user is sent, nothing loaded. "Zuletzt gesucht", "Nach Neuem suchen",
"Alles aktualisieren" (loads what was found, one after another). **Ablage**: the folder of program and models and "Frei auf dem
Mac … · Arbeitsspeicher …".

### settings.assistant.operation — Betrieb
- **Zustand**: gestoppt, startet …, läuft or Fehler; "abgeschirmt" when it runs in macOS's strict sandbox (no network, no other
  programs, cannot read Kontor's or MoneyMoney's data); memory and processor use, speed of the last answer (tokens per second);
  "Starten"/"Stoppen".
- **Kontext**: how much the model keeps in view at once (Automatisch by the Mac's memory, or 16–128 K tokens).
- **Beenden bei Leerlauf**: the model ends after 5, 10, 30 (default) or 60 minutes without a question, or never.
- **Verläufe speichern** (default on): conversations kept encrypted to open again under "Verläufe"; number and size; "Ältere als ein
  Jahr löschen", "Alle Verläufe löschen".
- **Abschirmung von macOS**: Streng (recommended), Einfach (still no network) or Aus – only the user can weaken it.

### settings.assistant.memory — Gedächtnis
"Gedächtnis verwenden" (default on) and the notes the assistant keeps from what the user said: number, pinned ones, progress of
the search by meaning. Add a note by hand, search the notes, and per note its date and how it came about ("in einer Unterhaltung
gesagt", "in den Einstellungen notiert", "aus einer Sicherung", "importiert"; "immer dabei" = goes with every question), pin, change, forget; "Alles vergessen". Never passwords, PINs, TANs or keys.
"Exportieren": all notes that count as one file in an open format, not encrypted – on top a Markdown list to read (per note its
day, where it came from, whether it is pinned, what it replaced), under it the same as JSON for programs (format `kontor-memory`:
the format's version, the time of the export, Kontor's version; per note `text`, `created`, `origin`, `pinned`, `replaces`).
"Importieren …": such a file, or a plain text or Markdown list with one note per line (from another system). Kontor checks the
whole file first, shows the notes it would bring and takes all of it or nothing: a note that is empty, longer than a note may be
or holds a credential refuses the file, named by its line or number. What comes in is marked "importiert", is never pinned and
replaces nothing that was there; notes remembered already are left out. The log of changes says how many notes, never what.
"Import zurücknehmen" (shown while there is an import with notes as they came): removes the notes of the latest import that were
not changed, pinned or replaced since – with the earlier wordings it brought for them; the rest stays and is counted.

### settings.assistant.rights — Was der KI-Assistent darf
Each right on its own: **Lesen** (the user's figures, transactions and the page in view; the help always), **Zeigen** (open
pages, filter transactions, highlight places, show charts), **Ändern** – each change only after the user's click on its card: enter
balances and plan values, assign categories in MoneyMoney (only transactions without one), approve or hold back waiting
auto-bookings, create and change booking rules, file receipts given in the chat; **Von wo**: also from the iPhone (default off);
**Internet** (default off): look things up, read only, per chat after a click – with the optional Tavily key, the sources trusted
without asking ("Ohne Rückfrage") and further websites. **Claude-Schlüssel (optional)**: the user's own API key of Anthropic for
questions to Claude (tier 4), typed once and never shown again – "Gespeichert · heute N von M Anfragen" counts today's questions
against the day's limit; with a key **Claude-Modell** (Opus 5.5, Sonnet 5.5 or Fable 5.2: which model answers) and
**Claude-Anfragen je Tag** (the most questions that go out in a day, default 20). Claude is never among "Ohne Rückfrage": every
question is asked on a card. Never: settings, access, updates, transfers, itself.

### settings.assistant.changes — Protokoll der Änderungen und Abrufe
Folded table of everything the assistant changed after a click, every internet lookup and every change of the memory, newest
first: **Zeitpunkt**, **Änderung** (kind, title, each row before and after as on the card), **Begründung**, **Stand** (done, taken
back, final, failed; lookups: fetched or the number of results). A question to Claude: the question, the model, and of its answer
only figures – "N Token ein · M aus" (tokens Anthropic counted for the request and for the answer: what it cost) and how many web
searches it made; never the answer. At most 500 entries per kind; never in backups.

## settings.updates — Updates
Cards **Installiert** (version and date) and **Verfügbar** (the newest version on GitHub; "neuer als installiert", "Kontor ist
aktuell" or "wartet auf Freigabe") with when it was checked. "Jetzt prüfen"; "Update installieren und Dienst neu starten"
(only at the Mac, only after a click). If the new files reach beyond the program (network, other programs, loaded code,
addresses, shields, the check itself), each finding is judged: "can be a risk" (a new way out, a loosened shield, a file that
arrives unread, the check changed; amber triangle), "existing way changed" (what goes out over a way Kontor already uses is
put together differently; one entry per way, grey triangle), or no approval needed (rules only stricter). The internet search's filter against
the user's own data counts as "existing way changed" (one entry). The box above the list counts the entries of the first two kinds; each entry (title in
plain words) opens to an explanation, then file and function or setting, "neu/geändert/entfernt" and the lines concerned
("−" removed, "+" new, a line around them; "… und N weitere Zeilen": not shown). "Freigeben und installieren" installs exactly
these files. Below, quiet and folded: "N Änderungen an Regeln – nur strenger" with file and name;
with only these the update installs with the ordinary button. Fields: **Automatisch prüfen** (täglich, wöchentlich, nie), **Quelle (GitHub)** – a tag warns when it is not the
official repository.

### settings.updates.python — Python
The Python Kontor runs in: its version and whose it is — "des Macs (von Apple)" (it comes with macOS's command line tools;
"ohne Sicherheitsupdates seit <date>" when python.org no longer fixes that line) or "von Kontor geladen <date>" (Kontor's own:
one fixed build of CPython, downloaded from GitHub on a click, checked by its size and SHA-256, compared with its archive,
tried with every part of Kontor, only then switched to). Buttons, only at the Mac: "Python <version> laden" (download, check,
try, switch, restart), "Erneut versuchen" and "Entfernen" after one that did not start, and "Aktualisieren" beside "neuer: <version>" when a version of Kontor names a newer build. While it
works: a bar with "Laden … x von y MB", then "Prüfen und entpacken", "Testen", "Umstellen". A red line: "… ist nicht gestartet"
(Kontor's own Python did not get Kontor running; Kontor went on with the Mac's Python by itself) or why a download or test
failed (nothing was switched then). "gilt ab dem nächsten Start von Kontor": chosen, not yet what runs. A green line right
after a switch names the version Kontor runs with now.

### settings.updates.components — Verwendete Programme
Everything foreign Kontor uses on this Mac, one row each: name and version in bold; below it what it is for, for a model its
file, "Lizenz <name>" (the licence as under KI-Assistent, e.g. "Apache 2.0", "MIT"; "PSF 2.0" is the Python Software
Foundation's; "Lizenz: siehe Herkunft" when Kontor does not know it – a model the user added by
its repository), and where it comes from (a link to GitHub or Hugging Face that opens in the browser; "Teil von macOS (Apple)"
for the Mac's own Python and tools). The pill on the right: "abgeschirmt" (runs in the macOS sandbox at the level set under
KI-Assistent: no network, no access to Kontor's data), "abgeschirmt (einfach)" (the weaker level) or "nicht abgeschirmt"
(Python and macOS's tools: Kontor itself runs in them; llama.cpp and models only when the user switched the sandbox off).
Rows, in this order: Python (the one Kontor runs in; Kontor's own build also says what it includes), llama.cpp, each model on
this Mac (assistant, dictation, finding by meaning), libraries (none yet), macOS (its built-in tools, among them the Mac's
own Python, which starts Kontor even when Kontor runs in its own). Nothing here can be changed; loading and
removing is done under Python above and under KI-Assistent.

### settings.updates.changes — Änderungen
"Neu in …": all changes since the installed version, when one is available. "Änderungen je Hauptversion": per major version (e.g.
3.17 = 3.16.1 … 3.17.0; one not out yet "in Arbeit") a short overview of its big topics, its single versions folded, older major
versions folded. Lines "Entwicklung: …" are quieter.

## settings.backup — Sichern & Zurücksetzen
Backup, passing on, loading, data, reset and uninstall. Backup, reset and uninstall only at the Mac, with password.

### settings.backup.backup — Sicherung
For the user: everything to restore Kontor on a new Mac or after a reset – settings, areas, rules, properties, planning,
categories and assignments, month-end balances, the receipt index, the assistant's memory; not the transactions (they come from
MoneyMoney), receipt files, conversations, the keys for Tavily and Claude or Kontor's password. Encrypted with a password of its own (typed twice,
never stored).

### settings.backup.package — Einstellungspaket und Datei laden
**Einstellungspaket**: rules and assignments as a template for someone else (accounts only by name; no balances, transactions,
planning, passwords; loan rules hold the lender's IBAN). Below: how many loans, participations and position assignments it would
hold. **Sicherung oder Paket laden**: drop a backup or a package. A backup is checked whole and loaded whole or not at all; a package shows what
it holds, "Ergänzen" (adds rules, overwrites assignments) or "Ersetzen" (discards the present setup), and lets accounts not found
by name be assigned.

### settings.backup.data — Daten
Data folder, program folder, encryption (AES-256, opened by password or Touch ID), receipt folder, Time Machine (backed up or
excluded – the mark is set on the data folder itself), link to the log. **Datenschlüssel erneuern** (with password): encrypts every
file with a new key; the old one is deleted only when everything opens with the new.

### settings.backup.reset — Zurücksetzen und Deinstallieren
**Zurücksetzen**: deletes settings, planning, categories, history, receipt index, reports and the assistant's conversations, memory,
change log, settings and the keys for Tavily and Claude – optionally also the password (then the setup starts anew). Receipt files, linked documents,
the log and loaded models stay. **Deinstallieren**: removes the background service, Kontor's files in the data folder (also the
assistant's program and models), the data key, the Mac app's data and – if ticked – the program folder. Receipts and MoneyMoney
stay untouched.
