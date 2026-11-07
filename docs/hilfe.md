# Kontor – Hilfe

Kontor macht aus deinen Daten in [MoneyMoney](https://moneymoney.app) eine Bilanz, einen Kapitalfluss, eine Planung und eine Steuerübersicht – für dich privat und für jede Gesellschaft getrennt. Es läuft als kleiner Dienst auf deinem Mac, die Oberfläche öffnest du im Browser unter `http://127.0.0.1:8765/`. Diese Hilfe steht auch in Kontor selbst (Menü „Hilfe“, durchsuchbar).

![Übersicht](img/uebersicht.png)

<a id="ueberblick"></a>
## Was MoneyMoney macht und was Kontor macht

| MoneyMoney | Kontor |
|---|---|
| Holt Umsätze und Salden von Banken, Depots und Zahlungsdiensten. | Liest diese Daten über die Skript-Schnittstelle von MoneyMoney. Zugangsdaten zu Banken sieht Kontor nie. |
| Kategorisiert Umsätze, von Hand oder per Regel. | Nutzt diese Kategorien. Umsätze ohne Kategorie ordnest du in Kontor zu; auf Wunsch schreibt Kontor die Zuordnung nach MoneyMoney zurück. |
| Führt Offline-Konten: private Darlehen, Beteiligungen, Immobilien, Kapitalkonten. | Bucht nach deinen Regeln nur in solche Offline-Konten: Darlehensraten spiegeln und Zinsen berechnen, Beteiligungswerte, Saldo-Spiegel. |
| Hat keine Bilanz, keine Planung, keine Steuerübersicht. | Bilanz je Bereich, Kapitalfluss mit Prüfzeile, rollierende Planung, Immobilienkalkulation, Steuer-Jahresübersicht, Belege, Excel-Export. |

Kontor ändert in MoneyMoney nie Buchungen, den Kategorienbaum oder Regeln und löst keine Überweisungen aus.

<a id="einrichtung"></a>
## Einrichtung

Unter **Einrichtung** stehen alle Bausteine in einer sinnvollen Reihenfolge. Jeder zeigt, ob er schon eingerichtet ist; die ersten vier bauen aufeinander auf, der Rest ist optional und jederzeit nachholbar. „Einrichtung prüfen“ (unten) liest MoneyMoney und meldet, ob alle Konten und Kategorien, auf die sich deine Einrichtung bezieht, dort noch existieren – etwa nachdem du in MoneyMoney etwas umbenannt hast.

![Einrichtung](img/einrichtung.png)

1. **MoneyMoney-Verbindung** – MoneyMoney läuft und ist entsperrt; macOS fragt beim ersten Mal, ob Kontor MoneyMoney steuern darf (Automation). Erlauben.
2. **Bereiche** – welche Konten zusammengehören.
3. **Konten** – Bereich, Position und Verlauf jedes Kontos bestätigen.
4. **Kontostände aus MoneyMoney** – den bisherigen Verlauf einmalig übernehmen.
5. **Kategorien auswählen** und **Kategorien zuordnen**.
6. **Regeln**, **Immobilien**, **Planung**, **Steuer**, **Belege**, **Zugriff vom iPhone**, **Betrieb**.

Danach erstellt „Auswertung erstellen“ die erste Auswertung. Die Sprache (Deutsch oder Englisch) wählst du auf der Anmeldeseite, in der Einrichtung oder unter Einstellungen → Allgemein.

<a id="bereiche"></a>
### Bereiche

Ein Bereich ist eine Menge von Konten mit eigener Bilanz, eigenem Kapitalfluss, eigener Planung, Steuerübersicht, Umsätzen und Belegen – zum Beispiel „Privat“ und je eine Gesellschaft. Vorschlag: jede Kontengruppe auf oberster Ebene in MoneyMoney. Du kannst Konten und Gruppen aber beliebig zuordnen, zusammenlegen oder weglassen. Ein Bereich ist der Hauptbereich (privat); er ist beim Öffnen vorausgewählt. Gesellschaften bekommen Art und deinen Anteil – mit dem Anteil rechnet Kontor deine Beteiligung und die Steuer. Art und Hauptbereich sind aus den Namen vorbelegt; bitte prüfen. Mit ▲ ▼ legst du die Reihenfolge fest, in der die Bereiche oben in der Leiste stehen. Bereiche lassen sich umbenennen, löschen, zusammenlegen oder aus einzelnen Konten und Gruppen zusammenstellen; Konten, die keinem Bereich angehören, zählen nirgends.

<a id="konten"></a>
### Konten und Positionen

Jedes Konto bekommt einen Bereich, eine Position in der Bilanz und eine Verlaufsquelle. Kontor schlägt alles vor; gestrichelt heißt „Vorschlag gewählt“, durchgezogen „eigene Wahl“. Nach dem Speichern bleibt es fest: Umbenennen oder Verschieben in MoneyMoney ändert nichts mehr. Neue Konten erscheinen als „neu“, bis du sie bestätigst. Konten erscheinen überall in der Reihenfolge von MoneyMoney.

![Konten](img/konten.png)

**Positionen** (Zeilen der Bilanz, sortiert nach Verfügbarkeit):

| Position | Was dazugehört |
|---|---|
| Bankguthaben | Giro, Tagesgeld, Kreditkarte – sofort verfügbar |
| Handelbare Anlagen | Depots mit Aktien, Fonds, ETF/ETC, Derivaten, dazu Krypto und Edelmetall – in Tagen verkäuflich, mit Kursrisiko |
| Gebundene Anlagen | Festgeld, Bausparvertrag, Lebens- und Rentenversicherung – vertraglich festgelegt |
| Immobilien, Beteiligungen, Sachwerte | langfristig gebunden |
| Forderungen | Darlehen an andere, Kautionen, Guthaben auf Kapitalkonten |
| Verbindlichkeiten | Darlehen, Kreditkartenschulden, Schulden auf Kapitalkonten |
| außerhalb des Nettovermögens | Eigenkapital (Kapitalkonten, nur ausdrücklich gewählt), Avale & Bürgschaften, „nicht bilanzieren“ |

**So schlägt Kontor vor** (in dieser Reihenfolge): Depot → Kontoname (z. B. „Immobilie“, „Darlehen“, „Kapitalkonto“, „Aval“, „Bauspar“) → eindeutiger Kontotyp (Giro, Kreditkarte, Darlehen) → Name der Gruppe in MoneyMoney → übriger Kontotyp. Darlehen, Kautionen sowie Kapital- und Gesellschafterkonten zählen mit Guthaben als Forderung, mit Schuld als Verbindlichkeit – in der Gesellschaft ist das eine Schuld an den Gesellschafter, privat eine Forderung. Der Wert einer Beteiligung ist dann dein Anteil am Rest; das stimmt auch bei ungleichen Einlagen.

**Anzeige**: „nach Aktivität“ blendet Konten aus, die seit N Monaten weder Bestand noch Umsatz haben; „immer anzeigen“ oder „ausblenden“ legt es fest. Ausgeblendete Konten zählen in allen Summen mit.

<a id="verlauf"></a>
### Verlauf eines Kontos

Woher die Monatsstände eines Kontos kommen:

- **Umsätze** (Standard für Bankkonten): Stand am Monatsende = heutiger Saldo minus alle späteren gebuchten Umsätze – so rechnet auch MoneyMoney. Vorgemerkte Umsätze zählen nicht. Vor dem ersten Umsatz gibt es keinen Stand.
- **Kontostände**: eingetragene oder übernommene Stände sind Anker; die Monate dazwischen rechnet Kontor mit den Buchungen. Abweichungen erscheinen im Kapitalfluss als „Korrektur Kontostand“.
- **Depots**: haben keine Buchungen. Kontor nimmt die aus MoneyMoney übernommenen Stände und zeichnet danach jeden Monat selbst auf.

Kontor schätzt nichts. Ein Klick auf ein Konto in der Bilanz öffnet sein Verlauf-Fenster mit Grafik, Monatsständen und Prüfhinweisen; dort lassen sich Stände eintragen oder aus einer Datei übernehmen. Bei Depots stehen oben die Positionen (Menge, Wert, Gewinn/Verlust).

Das Fenster prüft auch die Rückrechnung: Anfangssaldo vor der ersten Buchung in MoneyMoney, vorgemerkte Umsätze, negative Stände bei Konten, die nicht ins Minus können. Bei Depots ohne übernommenen Verlauf steht „vor … unbekannt“.

**Stände aus einer Datei** (Einrichtung → Konten oder Verlauf-Fenster): CSV oder Excel (.xlsx), als Liste (Datum, Konto, Saldo) oder als Tabelle mit Stichtagen in der Kopfzeile oder in der ersten Spalte. Importierte Konten stehen danach auf „Kontostände“.

![Verlauf eines Kontos](img/verlauf.png)

<a id="kontostaende"></a>
### Kontostände aus MoneyMoney

MoneyMoney gibt den Verlauf der Kontostände über seine Schnittstelle nicht heraus – vor allem bei Depots fehlt sonst die Vergangenheit. Einmalig liest Kontor ihn deshalb aus der Datenbankdatei von MoneyMoney: MoneyMoney beenden, „Im Finder zeigen“, die Datei `MoneyMoney.sqlite` ins Fenster ziehen und das MoneyMoney-Passwort in einem macOS-Fenster eingeben. Kontor bekommt nur einen daraus berechneten Schlüssel, entschlüsselt nur im Arbeitsspeicher, prüft die Werte am aktuellen Saldo und speichert nur Monatsend-Stände, verschlüsselt. In MoneyMoney wird nichts verändert. Erneutes Einlesen ersetzt den bisherigen Stand.

**Danach zeichnet Kontor selbst auf**: Bankkonten rechnet Kontor ohnehin exakt aus den Umsätzen zurück. Für Depots merkt sich Kontor bei jedem Lesen den aktuellen Wert. Der Dienst läuft ab der Anmeldung am Mac im Hintergrund, auch ohne geöffnetes Kontor-Fenster, und liest innerhalb von etwa 20 Sekunden, sobald MoneyMoney offen und entsperrt ist – ein kurzer Blick in MoneyMoney genügt. Jeder Stand zählt für den Monat, in dem MoneyMoney ihn bei der Bank abgerufen hat. Hat MoneyMoney abgerufen, während Kontor nicht lief, oder fehlt ein Monat, weist die Seite „Synchronisierung“ darauf hin.

<a id="synchronisierung"></a>
## Synchronisierung

Der Datenstand hat zwei Stufen: **Banken → MoneyMoney** (MoneyMoney ruft bei den Banken ab) und **MoneyMoney → Kontor** (Kontor liest aus MoneyMoney). Beide Zeitpunkte stehen unten links. „Sync“ liest sofort; automatisch liest Kontor alle 30 Minuten (einstellbar) und sobald MoneyMoney neue Daten hat – jeweils nur, wenn MoneyMoney läuft und entsperrt ist.

![Synchronisierung](img/synchronisierung.png)

- **Schnell lesen**: Ein Abgleich liest nur die Umsätze der letzten drei Monate und übernimmt ältere aus dem letzten vollständigen Lesen. Das dauert Sekunden.
- **Vollständig lesen**: alle 24 Stunden (einstellbar), nachts schon nach der Hälfte, nach eigenen Buchungen von Kontor und mit „Alles neu lesen“. Änderungen an älteren Umsätzen in MoneyMoney (z. B. eine Regel auf alle Umsätze angewendet) erscheinen erst danach.
- Ein Bankabruf ohne neue Daten löst keine Neuberechnung aus.
- **Umsätze lesen** (Einstellungen → Allgemein): wie weit zurück Kontor liest; 0 = alle (empfohlen).

Die Seite „Synchronisierung“ zeigt je Konto den letzten Abruf und meldet Konten, die zurückliegen. Konten ohne Bankabruf (Offline-Konten: ohne Bank- oder Kontonummer, Ziel einer Regel oder von Kontor bebucht) stehen getrennt; je Konto änderbar. Ist MoneyMoney zu oder gesperrt, passiert nichts – der nächste Abgleich holt alles nach. Bei Buchungen, Vorschlägen und Fehlern meldet sich Kontor mit einer macOS-Mitteilung (abschaltbar unter Einstellungen → Allgemein).

<a id="tabellen"></a>
## Tabellen, Schalter und Excel

Überall wählst du **Monate** (mit Jahressummen) oder nur **Jahre**. Jahresspalten sind kumuliert: Zahlungsflüsse als Summe, Bestände als Stand zum Jahresende. Blass sind der laufende Monat und das laufende Jahr (noch nicht abgeschlossen), noch blasser Planwerte.

- **Alle Zeilen** zeigt auch leere und ausgeblendete Zeilen.
- **Plan** (Kapitalfluss) hängt die Planwerte rechts an; aus = nur Ist-Werte. Bilanz und Planung zeigen den Plan immer.
- **inflationsbereinigt** (Planung) zeigt Planwerte in heutiger Kaufkraft.
- Die Übersicht vergleicht zusätzlich mit dem gleichen Zeitraum des Vorjahrs.

Jede Tabelle hat einen **Excel**-Knopf: Bilanz, Kapitalfluss, Planung (mit Fortschreibung und Parametern), Steuer, Umsätze, Depots, Belege, Konten und jede Immobilienkalkulation.

<a id="bilanz"></a>
## Bilanz

Die Bilanz zeigt je Bereich das Vermögen nach Positionen, Monat für Monat, mit Plan bis Dezember des letzten Planjahres. Klick auf eine Position klappt ihre Konten auf, Klick auf ein Konto öffnet seinen Verlauf.

![Bilanz](img/bilanz.png)

- **Blass**: der laufende Monat und das laufende Jahr (noch nicht abgeschlossen); noch blasser: Planwerte.
- **Grafik**: Zusammensetzung des Vermögens in den Farben der Positionen, schwarz das Nettovermögen (gestrichelt: Plan). Zeitraum 1/3/10 Jahre, alles oder eine Monatszahl; waagerecht wischen verschiebt, mit zwei Fingern zoomen, Doppelklick vergrößert, Klick springt zur Spalte. Aufgeklappte Positionen zeigen ihre Konten als Abstufungen der Farbe.
- **Geldtransit**: Liegen die beiden Buchungen einer Umbuchung zwischen eigenen Konten in verschiedenen Monaten (am 31. abgebucht, am 1. gutgeschrieben), zählt der Betrag am Monatsende als „Geldtransit“ zum Bankguthaben – sonst sähe das Nettovermögen kurz zu niedrig aus. Ein Klick zeigt die erkannten Buchungspaare.
- **Monate oder Jahre**: Jahresspalten zeigen Bestände zum Jahresende.

<a id="kapitalfluss"></a>
## Kapitalfluss

Wohin das Geld fließt: Einnahmen und Ausgaben nach Kategorien, Investitionen (Umschichtungen in Depots und Anlagen, Einlagen in Beteiligungen), Finanzierung (Tilgung und Zinsen je Darlehen), Bewertung (Wertänderungen von Depots) und „Unklar“.

![Kapitalfluss](img/kapitalfluss.png)

Umbuchungen zwischen eigenen Konten erkennt Kontor an der Gegen-IBAN, an der Kategorie „Umbuchung“ und an Gegenbuchungen mit gleichem Betrag innerhalb von drei Tagen; sie zählen nicht als Einnahme oder Ausgabe. Die **Prüfzeile** „unerklärte Vermögensänderung“ sollte nahe 0 liegen – sonst fehlt eine Kategorie oder eine Gegenbuchung. Welche Kategorien als eigene Zeile erscheinen, legst du unter [Kategorien → Auswahl](#kategorien-auswahl) fest; welche Oberkategorie zu welchem Abschnitt gehört, unter Kategorien → Kapitalfluss-Zuordnung.

<a id="kategorien"></a>
## Kategorien

**MoneyMoney ist maßgeblich**: Hat ein Umsatz dort eine Kategorie, gilt sie auch in Kontor. Umsätze ohne Kategorie ordnest du in Kontor zu – unter Kategorien → Zuordnen, gruppiert nach Gegenpartei, mit Vorschlägen aus gelernten Regeln. „Regel für diesen Namen“ erledigt die Gegenpartei dauerhaft.

![Zuordnen](img/zuordnen.png)

Die Seite Kategorien hat vier Reiter:

- **Zuordnen** – Umsätze ohne Kategorie, nach Gegenpartei gruppiert; die Zahl im Reiter zeigt, wie viele offen sind.
- **Auswahl** – welche Kategorien aus MoneyMoney Kontor als Zeile nutzt ([mehr](#kategorien-auswahl)).
- **Kontor-Kategorien & Regeln** – Kategorien, die es nur in Kontor gibt (Baum aus MoneyMoney übernommen, ergänzbar), deine eigenen Regeln (Name, Zweck, Gegen-IBAN, Richtung) und die gelernten. Gelernt wird aus der Gegenpartei (IBAN oder Name, ggf. mit Zweckanfang), wenn mindestens 90 % ihrer bisherigen Umsätze dieselbe Kategorie haben. Eigene Regeln gehen vor; spezifischere gewinnen (IBAN vor Name + Zweck vor Name).
- **Kapitalfluss-Zuordnung** – welche Oberkategorie zu welchem Abschnitt des Kapitalflusses gehört (Einnahmen, Ausgaben, Investition, Finanzierung). Ohne Zuordnung entscheidet das Vorzeichen.

**Was gilt**: die Kategorie aus MoneyMoney – außer du übersteuerst sie ausdrücklich („Nur in Kontor“). Ohne sie: manuelle Zuordnung vor eigener Regel vor gelernter Regel. Regeln wirken standardmäßig nur auf Umsätze ohne MoneyMoney-Kategorie; „Regeln auch auf MoneyMoney-kategorisierte Umsätze anwenden“ ändert das – nur in Kontor, MoneyMoney bleibt unverändert.

Kategorien braucht es nur für die Aufteilung (Kapitalfluss-Zeilen, Planung je Zeile, Steuer). Bilanz, Nettovermögen, Immobilien, Darlehen und Einnahmen/Ausgaben insgesamt funktionieren auch ohne. Wenig Pflege: Zahlungen zwischen dir und deinen Gesellschaften erkennt Kontor ohnehin als Einlage oder Entnahme; fein kategorisieren musst du vor allem dort, wo du Kapitalfluss und Steuer genau brauchst.

<a id="kategorien-zurueckschreiben"></a>
### Nach MoneyMoney zurückschreiben

Mit „Kategorien zurückschreiben“ (Einstellungen → Allgemein oder „Einschalten“ unter Kategorien; nur am Mac) setzt Kontor deine Zuordnungen auch in MoneyMoney – so kategorisierst du nur an einer Stelle. Sicherungen:

- Kontor setzt nur das Kategoriefeld eines Umsatzes; Beträge, Daten und Löschen sind damit nicht möglich.
- Direkt vor dem Schreiben liest Kontor den Umsatz neu aus MoneyMoney und schreibt nur, wenn er unverändert ist und noch keine Kategorie hat (oder die von Kontor gesetzte).
- Eine vorhandene andere Kategorie – etwa von einem Geschäftspartner gepflegt – ersetzt Kontor nur nach Rückfrage: „In MoneyMoney ersetzen“ oder „Nur in Kontor“ (MoneyMoney bleibt, Kontor übersteuert).
- Kategorien anlegen kann Kontor in MoneyMoney nicht (lässt MoneyMoney nicht zu). Fehlt eine, wartet die Zuordnung; nach dem Anlegen in MoneyMoney trägt Kontor sie beim nächsten Abgleich nach.

<a id="kategorien-auswahl"></a>
### Auswahl: welche Kategorien Kontor nutzt

Unter Kategorien → Auswahl legst du je Kategorie aus MoneyMoney fest:

- **Eigene Zeile** – erscheint im Kapitalfluss und in der Planung als eigene Zeile.
- **Zur Oberkategorie** – zählt samt Unterkategorien zur Oberkategorie (nur Kapitalfluss und Planung; die Steuer nutzt weiter die genaue Kategorie).
- **Nicht verwenden** – in Kontor wie ohne Kategorie; die Umsätze erscheinen unter „Zuordnen“.

„Nur oberste Ebene als Zeile“ räumt den Kapitalfluss mit einem Klick auf. In MoneyMoney ändert sich dadurch nichts.

![Auswahl der Kategorien](img/kat_auswahl.png)

<a id="planung"></a>
## Planung

Die Planung schreibt die Vergangenheit fort: je Zeile eine Methode (Ø 12 oder 6 Monate, Vorjahresmonat, fester Betrag, Jahresbetrag/12, MoneyMoney-Budget, keine), ein Betrag und eine Steigerung in % p.a. Ausgaben folgen standardmäßig der Inflation, Einnahmen der eingestellten Rate. Einzelne Monate überschreibst du per Doppelklick; der Vorschlag bleibt sichtbar und lässt sich wiederherstellen.

![Planung](img/planung.png)

- **Darlehen**: Zins auf den fortgeschriebenen Restsaldo, Tilgung = Rate − Zins.
- **Wertentwicklung** je Konto in % p.a.; Beteiligungen wahlweise gekoppelt an das geplante Nettovermögen der Gesellschaft (Anteil × Nettovermögen).
- **Ereignisse**: einmalige oder wiederkehrende Umschichtungen, Einnahmen und Ausgaben – z. B. ein Darlehen auf einen Schlag aus dem Depot zurückzahlen.
- **Immobilien**: aktive Kalkulationen fließen mit Miete, Kosten, Zins, Tilgung, Restschuld und Objektwert ein.
- Der Plan reicht immer bis Dezember; „inflationsbereinigt“ zeigt Planwerte in heutiger Kaufkraft.
- Darunter: Fortschreibung der Bilanz je Position und Konto und Kennzahlen (Sparquote, Reichweite der Liquidität, Zinslast). Der Plan gilt je Bereich.

<a id="immobilien"></a>
## Immobilien

Je Objekt beliebig viele Kalkulationen (Szenarien), eine davon aktiv. Eingaben:

- Kaufpreis und Übergang; Nebenkosten (Grunderwerbsteuer, Notar, Grundbuch, Makler; sofort abziehbare Posten getrennt); Gebäudeanteil und AfA-Satz oder Restnutzungsdauer.
- Nettokaltmiete und Umlage, Leerstand, Mietanpassung (Indexmiete nach VPI mit Weitergabefaktor und Schwelle, fester Satz oder keine); nicht umlagefähige Kosten und Rücklage (mit VPI oder festem Satz).
- Darlehen: Annuität, Tilgungsdarlehen oder endfällig; Abrechnung monatlich wie bei Banken oder jährlich auf den Stand 1. Januar wie bei Verkäuferdarlehen; Sondertilgungen laufend oder einzeln, Zinsbindung mit Anschlusszins, Fälligkeit mit Rückzahlung.
- Gesellschafter mit Anteil und Steuersatz, Ausschüttung, Wertentwicklung, Verkaufsjahr.

Ungültige Eingaben weist Kontor mit dem Feldnamen ab.

![Immobilien](img/immobilien.png)

Ergebnis: Monats- und Jahrestabelle (Miete, Kosten, Zinsen, Tilgung, AfA, steuerliches Ergebnis, Steuer, Cashflow, Vermögensaufbau, Restschuld, Objektwert), Kennzahlen (Kaufpreisfaktor, Brutto- und Nettomietrendite, Cash-on-Cash, DSCR, LTV, IRR bis zum Verkauf) und Hinweise (offene Fälligkeiten, fehlender Anschlusszins, negativer kumulierter Cashflow). Verknüpfungen mit MoneyMoney: Vermietungskategorie und Darlehenskonten für den Soll/Ist-Vergleich je Jahr, Objektkonto für den Wert in der Bilanz. „In Planung übernehmen“ speist die Planung des Bereichs; die AfA der aktiven Kalkulation landet in der Steuerübersicht, solange dort kein Jahreswert von Hand steht. Excel-Export je Kalkulation. Dokumente (Kaufvertrag, Gutachten …) werden als Verknüpfung abgelegt – die Dateien bleiben, wo sie sind. Vereinfacht gerechnet: Steuer je Gesellschafter = Anteil × Ergebnis × Steuersatz (keine Progression, kein Verlustausgleich), AfA linear.

<a id="steuer"></a>
## Steuer

Je Entität (Hauptbereich = privat, jede Gesellschaft mit deinem Anteil aus der Beteiligungsregel) und Jahr: Vermietung je Objekt aus den Kategorien `Vermietung \ Objekt \ Art` (beliebig viele Objekte, auch privat), Schuldzinsen je Darlehen (Zuordnung Darlehen → Objekt unter Einstellungen → Steuer), AfA, Steuerpositionen aus Kategorienamen (anpassbar unter Einstellungen → Steuer) und Buchungen ohne Kategorie als Prüfposten. Die Belege eines Jahres lassen sich als ZIP mit Übersicht exportieren. Keine Steuerberatung.

<a id="belege"></a>
## Umsätze und Belege

Der Umsatzbrowser filtert nach Bereich, Jahr, Konto, Text, „ohne Beleg“ und „ohne Kategorie“. Belege (PDF, Bilder, E-Mails, Office-Dateien) fügst du per Auswahl, Drag & Drop oder am iPhone per Foto hinzu. Sie liegen als normale Dateien im Belegordner (Standard `~/Documents/Kontor-Belege`, Unterordner z. B. `{jahr}`), Dateiname `Datum_Betrag_Name_Kennung`. Dateien außerhalb des Ordners (auch iCloud Drive) lassen sich verknüpfen, ohne sie zu kopieren – Kontor zeigt, ob die Datei lokal vorliegt oder noch aus iCloud geladen wird. Vorhandene Dateien im Belegordner lassen sich nachträglich zuordnen. Bis 60 MB je Datei. Der Index liegt verschlüsselt im Datenordner; die Dateien bleiben auch ohne ihn nutzbar. Löschen in Kontor betrifft nie verknüpfte Dateien.

<a id="regeln"></a>
## Regeln (Gegenbuchungen)

Regeln buchen in Offline-Konten in MoneyMoney:

- **Darlehen**: Rate erkennen (Gegen-IBAN oder Text), auf dem Darlehenskonto spiegeln, Zinsen berechnen (Jahresbasis oder Restschuld monatlich).
- **Beteiligungen**: Zielkonto = Anteil × Nettowert einer Kontengruppe.
- **Saldo-Spiegel**: Zielkonto = Faktor × Quellkonto (z. B. Kapitalkonto).

Standard ist der **Testmodus**: Vorschläge erscheinen unter „Buchungen“, gebucht wird erst nach „Jetzt buchen“ oder wenn du den Testmodus ausschaltest. Jede Buchung trägt eine Markierung im Verwendungszweck (die Schnittstelle von MoneyMoney kennt beim Anlegen kein Kommentarfeld) und wird nie doppelt angelegt; bestehende Buchungen ändert oder löscht Kontor nie. Bank- und Erweiterungskonten werden nie bebucht, Überweisungen und Lastschriften sind gesperrt.

**Zinsen**: Jahresbasis = Zinssatz × Stand am 31.12. des Vorjahres, je Monat ein Zwölftel, im Dezember mit dem Cent-Rest – oder monatlich auf die Restschuld. Das Modell ist vereinfacht (30/360); einmal im Jahr mit der Zinsabrechnung der Bank abgleichen. Bei Problemen (Konto gelöscht, keine passende Zahlung, Zinsbuchung schon von Hand vorhanden) gibt es einen Hinweis und eine Mitteilung.

<a id="iphone"></a>
## Zugriff vom iPhone

Standardmäßig ist Kontor nur auf dem Mac erreichbar (`127.0.0.1`) – deshalb öffnet das iPhone die Adresse nicht. Für den Zugriff von unterwegs nutzt Kontor [Tailscale](https://tailscale.com): ein privates, verschlüsseltes Netz nur aus deinen Geräten. Im Heimnetz und im Internet ist dabei kein Port offen, am Router ist nichts einzurichten.

![Zugriff vom iPhone](img/zugang.png)

Unter Einstellungen → Zugang zeigt Kontor die Schritte mit Häkchen:

1. Tailscale auf dem Mac installieren und anmelden.
2. Tailscale auf dem iPhone installieren, mit demselben Konto anmelden.
3. In der Tailscale-Verwaltung unter DNS „MagicDNS“ und „HTTPS Certificates“ einschalten.
4. „Zugriff einschalten“ – Kontor holt ein echtes Zertifikat für den Namen des Macs, öffnet eine zweite Adresse nur im Tailscale-Netz und startet neu.
5. Am iPhone die angezeigte Adresse in Safari öffnen (Link kopieren – er landet über die Zwischenablage auf dem iPhone), anmelden, Teilen → „Zum Home-Bildschirm“.

**Wer, wo, was**: Erreichbar ist Kontor nur für Geräte in deinem Tailscale-Netz und nur mit dem Kontor-Passwort; von überall mit Internet; Standard **nur ansehen** – vom iPhone lässt sich nichts ändern. Wahlweise „ansehen und bearbeiten“ (Planung, Zuordnungen in Kontor, Einstellungen). In MoneyMoney schreiben, Touch ID, Sicherung, Zurücksetzen und die Zugangseinstellungen gibt es nur am Mac. Der Mac muss laufen (nicht im Ruhezustand) und mit Tailscale verbunden sein; ist Tailscale beim Start noch nicht verbunden, öffnet Kontor die Adresse, sobald es geht. Im Terminal: `python3 ~/Kontor/kontor.py tls` (bzw. `tls --off`).

![Kontor auf dem iPhone](img/iphone.png)

**Offline-Ansicht**: Als App gespeichert behält das iPhone die zuletzt geladenen Daten. Ist der Mac nicht erreichbar, öffnet das Kontor-Passwort diese Kopie – nur lesen. Abschaltbar unter Einstellungen → Zugang. Das Passwort prüft das iPhone dabei gegen einen eigenen Prüfwert (PBKDF2-SHA256, eigener Salt); die Kopie ist durch die iPhone-Verschlüsselung geschützt, aber nicht zusätzlich mit dem Passwort verschlüsselt – wer das entsperrte Gerät mit Entwicklerwerkzeugen untersucht, käme an die Daten. „Gespeicherte Daten auf diesem Gerät löschen“ entfernt die Kopie sofort. Das Zertifikat (90 Tage gültig) erneuert der Dienst selbst.

Ohne HTTPS-Zertifikate geht „Ohne Zertifikat einschalten“ (durch Tailscale verschlüsselt, aber ohne Offline-Ansicht).

<a id="sichern"></a>
## Sichern und Zurücksetzen

![Sichern und Zurücksetzen](img/sichern.png)

- **Sicherung** – für dich: Kontor auf einem neuen Mac oder nach dem Zurücksetzen genau so wiederherstellen. Enthält alle Einstellungen, Bereiche, Regeln, Immobilien, Planung, Kategorien und Zuordnungen, Monatsstände und den Belegindex – nicht die Umsätze (kommen aus MoneyMoney), keine Belegdateien, nicht das Kontor-Passwort. Weil sie deine Finanzdaten enthält, wird sie mit einem eigenen Passwort verschlüsselt, das Kontor nicht speichert. Nur am Mac.
- **Einstellungspaket** – für andere: deine Regeln und Zuordnungen als Vorlage, z. B. für einen Geschäftspartner mit eigenem MoneyMoney. Konten nur mit Namen, ohne Kontostände, Umsätze, Planung, Passwörter oder Adresse. Darlehensregeln enthalten die Gegen-IBAN des Darlehensgebers – vor dem Weitergeben prüfen. Beim Laden ordnet Kontor die Konten über die Namen zu; was nicht gefunden wird, ordnest du in der Oberfläche zu. „Ergänzen“ fügt Regeln hinzu und überschreibt Zuordnungen, „Ersetzen“ verwirft die vorhandene Einrichtung. Eine Vorlage liegt im Ordner `templates/`.
- **Time Machine** sichert den Datenordner verschlüsselt (der Schlüssel liegt im Schlüsselbund, nicht im Ordner). Der Stand steht auf der Seite; Ausschließen ist möglich, aber nicht empfohlen.
- **Zurücksetzen** (nur am Mac, mit Passwort) löscht Einstellungen, Planung, Kategorien, Verlauf und Auswertungen, wahlweise auch das Passwort. Belegdateien, Schlüssel und Protokoll bleiben.

<a id="updates"></a>
## Updates

Kontor fragt GitHub nach der neuesten Version (täglich, wöchentlich oder nie – Einstellungen → Updates) und installiert nur nach Klick. Die Update-Prüfung ist die einzige Netzverbindung von Kontor: Sie fragt `raw.githubusercontent.com` nach der Datei `VERSION` im Hauptzweig des Repositorys (Standard: [github.com/stecrz/Kontor](https://github.com/stecrz/Kontor)). Andere Server sind bewusst nicht möglich.

Beim Installieren lädt Kontor diesen Stand als Archiv von github.com, ersetzt den Programmordner (die alten Dateien bleiben daneben als `.alt`), startet den Dienst neu und lädt die Seite neu; ist der Programmordner ein Git-Klon, läuft stattdessen `git pull`. Datenordner und Einstellungen bleiben. Alle Schritte stehen im Protokoll, alle Änderungen unter Updates → „Alle Änderungen“.

Im Terminal installiert und aktualisiert derselbe Befehl:

```
bash <(curl -fsSL https://raw.githubusercontent.com/stecrz/Kontor/main/get.sh)
```

<a id="sicherheit"></a>
## Sicherheit

- Oberfläche nur auf diesem Mac (`127.0.0.1`); optional zusätzlich im eigenen Tailscale-Netz – nie im Heimnetz oder Internet. Keine fremden Inhalte, keine Telemetrie.
- Anmeldung mit Passwort (PBKDF2-SHA256, 600 000 Runden) oder Touch ID am Mac; Sperre nach Leerlauf; fünf Fehlversuche sperren fünf Minuten.
- Alle Dateien im Datenordner sind verschlüsselt (AES-256 + HMAC), der Schlüssel liegt im macOS-Schlüsselbund. Belege liegen als normale Dateien in einem Ordner deiner Wahl.
- Das Protokoll enthält keine IBANs, Salden oder Passwörter.
- Grenze: Wer deinen entsperrten Mac bedient, kommt an den Schlüssel. FileVault bleibt die Basis.

<a id="fehler"></a>
## Wenn etwas nicht klappt

| Meldung | Abhilfe |
|---|---|
| MoneyMoney läuft nicht / Datenbank gesperrt | MoneyMoney öffnen und entsperren; Kontor holt alles nach. |
| Keine Berechtigung (Automation) | Systemeinstellungen → Datenschutz & Sicherheit → Automation: python3 darf MoneyMoney steuern. |
| Konto nicht gefunden | Eine Regel verweist auf ein gelöschtes oder umbenanntes Konto: unter Regeln neu zuordnen; „Einrichtung prüfen“ zeigt alle Fälle. |
| Prüfzeile im Kapitalfluss ≠ 0 | Es fehlt eine Kategorie oder eine Gegenbuchung. |
| iPhone öffnet die Adresse nicht | Zugriff unter Einstellungen → Zugang einschalten; Tailscale auf beiden Geräten verbunden? |
| Keine passende Zahlung | Die Darlehensregel findet die Rate nicht: Gegen-IBAN oder Text und Quellkonto prüfen. Bis 35 Tage nach „Automatik ab“ nur ein Hinweis. |
| Port nicht nutzbar | Ein anderes Programm belegt den Port: Einstellungen → Zugang → Erweitert. |
| Datenschlüssel liegt als Datei | Der Schlüsselbund war nicht nutzbar (z. B. Start ohne Anmeldung): Kontor funktioniert, der Schlüssel liegt dann aber mit Rechten 0600 im Datenordner. |

Für Rückfragen: Protokoll → „Diagnosedatei (maskiert)“. Sie enthält zusätzlich zum Protokoll Status und Einstellungen, Kontonamen ersetzt durch Konto01, Konto02 … – ohne IBANs, Salden oder Passwörter.
