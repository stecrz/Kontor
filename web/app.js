/* Kontor -- Oberflaeche. Keine Fremdbibliotheken, alles laeuft gegen /api/ auf demselben Rechner. */
'use strict';

// ---------------------------------------------------------------- Grundlagen
const fmt = new Intl.NumberFormat('de-DE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const fmt0 = new Intl.NumberFormat('de-DE', {maximumFractionDigits: 0});
const F = v => (v == null || isNaN(v) ? '–' : fmt.format(v));
const F0 = v => (v == null || isNaN(v) ? '–' : fmt0.format(v));
const Fk = v => (v == null || isNaN(v) ? '–' : (Math.abs(v) >= 1e6 ? (v / 1e6).toLocaleString('de-DE', {maximumFractionDigits: 2}) + ' M' : Math.abs(v) >= 1e4 ? (v / 1e3).toLocaleString('de-DE', {maximumFractionDigits: 0}) + ' k' : F0(v)));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const MONATE = ['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'];
const ML = m => MONATE[+m.slice(5) - 1] + ' ' + m.slice(2, 4);
const FD = d => (d && d.length >= 10) ? d.slice(8, 10) + '.' + d.slice(5, 7) + '.' + d.slice(0, 4) : (d || '');
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const ROLE = {liquiditaet: ['Liquidität', 'var(--c-liq)'], wertpapiere: ['Wertpapiere & Depots', 'var(--c-anl)'], anlagen: ['Geldanlagen', '#2fb8a0'], immobilien: ['Immobilien', '#b8860b'],
              beteiligungen: ['Beteiligungen', 'var(--c-bet)'], sachwerte: ['Sachwerte', '#8e8e93'], forderungen: ['Forderungen (verliehenes Geld)', 'var(--c-ford)'], sonstiges: ['Sonstiges', '#636366'], verbindlichkeiten: ['Darlehen & Verbindlichkeiten', 'var(--c-verb)'],
              eigenkapital: ['Kapitalkonten (Eigenkapital)', '#7d7aa8'], eventual: ['Avale & Bürgschaften', '#a8a29e'], ignorieren: ['nicht bilanzieren', '#c7c7cc']};
const ROLE_OPTS = [['liquiditaet', 'Liquidität'], ['wertpapiere', 'Wertpapiere & Depots'], ['anlagen', 'Geldanlagen'], ['immobilien', 'Immobilien'], ['beteiligungen', 'Beteiligungen'], ['sachwerte', 'Sachwerte'], ['forderungen', 'Forderungen (verliehenes Geld)'], ['sonstiges', 'Sonstiges'], ['verbindlichkeiten', 'Darlehen & Verbindlichkeiten'], ['eigenkapital', 'Kapitalkonten (Eigenkapital) – nicht im Nettovermögen'], ['eventual', 'Avale & Bürgschaften – nicht im Nettovermögen'], ['ignorieren', 'nicht bilanzieren']];
// Hilfetexte (Tooltips). Schluessel werden mit hq('schluessel') eingeblendet.
const H = {
  bereich: 'Ein Bereich ist eine Menge von Konten, die zusammen bilanziert werden – meist eine Kontengruppe der obersten Ebene (Privat, eine Gesellschaft). Er bekommt eigene Bilanz, Kapitalfluss, Planung und Steuerübersicht. Die Gruppierung in MoneyMoney ist dafür keine Voraussetzung: Konten lassen sich frei zuordnen.',
  haupt: 'Es gibt genau einen Hauptbereich – in der Regel du privat. Er ist beim Öffnen von Übersicht, Bilanz, Kapitalfluss und Planung vorausgewählt, die anderen Bereiche erscheinen dort als „weitere Bereiche“, und in der Steuerübersicht gilt er als Privatperson.',
  anteil: 'Dein Anteil an dieser Gesellschaft in Prozent (z. B. 49). Damit rechnet die Steuerübersicht deinen Teil des Ergebnisses, und die Beteiligungsregel bewertet dein Beteiligungskonto. Leer = 100 %.',
  gruppenwahl: 'Eine Gruppe wählen heißt: alle Konten darunter gehören dazu – auch solche, die später in MoneyMoney in dieser Gruppe angelegt werden. Einzelne Konten lassen sich abwählen; dann gilt nicht mehr die Gruppe, sondern die verbleibenden Konten einzeln.',
  anzeige: '„nach Aktivität“ (Standard) blendet ein Konto aus, solange es seit N Monaten weder Bestand noch Umsatz hat, und zeigt es wieder, sobald sich das ändert – wird also laufend geprüft. „immer anzeigen“ / „ausblenden“ legt es je Konto fest. Ausgeblendete Konten sind grau, zählen aber in allen Summen und im Verlauf.',
  position_kurz: 'Wo das Konto in der Bilanz erscheint und wie seine Umsätze im Kapitalfluss zählen. Vorschlag in dieser Reihenfolge: Depot → Kontoname (z. B. „Immobilie“, „Darlehen“, „Kapitalkonto“, „Aval“, „Bauspar“) → eindeutiger Kontotyp (Giro, Kreditkarte, Darlehen) → Name der Gruppe in MoneyMoney → übriger Kontotyp (Spar-, Tagesgeld, Festgeld). Darlehen, Kautionen, Kapital- und Gesellschafterkonten: Guthaben = Forderung, Schuld = Verbindlichkeit. So steht dein Kapitalkonto in der Gesellschaft als Schuld an dich und privat als Forderung; das Nettovermögen der Gesellschaft ist der Rest, dein Anteil daran kommt über die Beteiligungsregel dazu – das stimmt auch, wenn die Einlagen nicht den Anteilen entsprechen. „Kapitalkonten (Eigenkapital)“ nur wählen, wenn die Einlagen genau den Anteilen entsprechen und privat nichts gebucht ist. Avale und „nicht bilanzieren“ zählen nicht zum Nettovermögen.',
  verlauf_kurz: 'Woher die Monatsstände kommen: „Umsätze“ = vom heutigen Saldo rückwärts über die Buchungen gerechnet (Standard für Bankkonten). „Kontostände“ = bekannte Stände (eingetragen, importiert, bei Depots monatlich aufgezeichnet) sind maßgeblich, dazwischen rechnet Kontor mit den Buchungen (Standard für Depots). Geschätzt wird nichts: Vor dem ersten bekannten Stand eines Depots steht dieser erste Wert, gekennzeichnet mit „vor … unbekannt“.',
  berechtigung: 'Wofür: Kontor liest über die Skript-Schnittstelle von MoneyMoney Konten, Umsätze und Kategorien – nur lesend; Zugangsdaten zu Banken sieht Kontor nie. Ohne diese Freigabe kann Kontor nichts auswerten. Geschrieben wird nur in Offline-Konten, die du später in Regeln benennst. Erscheint die Abfrage nicht: Systemeinstellungen → Datenschutz & Sicherheit → Automation → python3 → MoneyMoney.',
  position: 'Die Bilanzposition eines Kontos. Sie bestimmt, wo das Konto in der Bilanz erscheint und wie Umsätze im Kapitalfluss behandelt werden (Liquidität: Einnahmen/Ausgaben; Darlehen: Zins/Tilgung; Wertpapiere, Immobilien, Beteiligungen, Sachwerte: Umschichtung/Bewertung). Vorschlag aus Gruppenname und Kontotyp, hier überschreibbar.',
  verlauf: '„Umsätze“: Saldo am Monatsende = heutiger Saldo minus alle späteren Buchungen. Eigene Monatswerte zählen hier nicht. „Kontostände“: eingetragene oder importierte Stände sind maßgeblich; Monate dazwischen und davor rechnet Kontor von dort aus mit den Buchungen weiter, Abweichungen erscheinen im Kapitalfluss als „Korrektur Kontostand“. Bei Depots (ohne Buchungen) gilt der letzte bekannte Stand; Kontor zeichnet ihn monatlich auf, ältere Stände kannst du eintragen oder importieren.',
  zuordnen: 'Hier landen alle Umsätze, die weder in Kontor noch in MoneyMoney eine Kategorie haben. Zuordnung je Gegenpartei; „Regel“ merkt sich die Zuordnung für künftige Umsätze. Kategorien tippen: neue werden angelegt (Oberkategorie / Unterkategorie).',
  kontor_kategorien: 'Reihenfolge: manuelle Zuordnung > eigene Regel > gelernte Regel > Kategorie aus MoneyMoney. Gelernte Regeln entstehen aus Gegenpartei (IBAN oder Name, ggf. plus Zweckanfang), wenn mindestens 90 % der bisherigen Umsätze dieser Gegenpartei dieselbe Kategorie haben.',
  mm_ueberschreiben: 'Standard: Umsätze mit MoneyMoney-Kategorie behalten sie. Eingeschaltet: Kontor-Regeln gelten auch dort (MoneyMoney selbst wird nicht verändert).',
  konten_zuordnung: 'Bereich, Position und Verlauf werden je Konto fest gespeichert. Vorgeschlagen wird nur bei neuen Konten (aus Name, Typ und Gruppe in MoneyMoney); danach ändern Umbenennen, Umgruppieren oder ein anderer Kontotyp in MoneyMoney nichts mehr – nur du hier.',
  verlauf_import: 'Datei mit Monats- oder Tagesständen. Spalten werden automatisch erkannt; Kontonamen aus der Datei ordnest du den Konten in Kontor zu (Vorschlag per Namensähnlichkeit). Mehrere Werte je Monat: der letzte zählt.',
  inaktiv: 'Gilt für Konten mit Anzeige „nach Aktivität“: ohne Bestand und ohne Umsatz in den letzten N Monaten (z. B. Altdaten) werden sie ausgeblendet, bleiben aber in Summen und Historie enthalten. 0 = nie automatisch ausblenden.',
  probelauf: 'Im Testmodus schlägt Kontor die Buchungen aus deinen Regeln (z. B. Darlehenszinsen) nur vor und legt nichts in MoneyMoney an. Zum Anlegen unter „Buchungen“ auf „Jetzt buchen“ klicken oder den Testmodus abschalten.',
  mmhist: 'Sicherheit: Die Datei bleibt verschlüsselt, bis sie bei Kontor im Arbeitsspeicher ankommt (nur auf diesem Mac, über 127.0.0.1). Dein Passwort gibst du in einem macOS-Fenster ein, das Kontor nur für diesen Vorgang erzeugt und danach löscht; Kontor erhält nur einen daraus berechneten Schlüssel und speichert weder Passwort noch Schlüssel. Entschlüsselt wird nur im Arbeitsspeicher, ohne Kopie, danach wird alles mit Nullen überschrieben – keine Datei, keine dauerhafte Freigabe, keine Netzverbindung währenddessen. MoneyMoney selbst bleibt unverändert. Übernommen werden nur Monatsend-Stände je Konto (verschlüsselt gespeichert), nie Zugangsdaten.',
  depotverlauf: 'MoneyMoney stellt über seine Schnittstelle nur den aktuellen Depotwert bereit, nicht die Kurve. Den bisherigen Verlauf übernimmt Kontor einmalig aus MoneyMoneys Datenbank (Einrichtung → Kontostände aus MoneyMoney); danach speichert Kontor bei jedem Lesen den Stand fürs Monatsende. Fehlt etwas: im Verlauf-Fenster eintragen oder als Datei importieren; davor steht „unbekannt“. Geschätzt wird nichts.',
  abruf: 'Stand je Konto in dem Datenstand, den Kontor zuletzt aus MoneyMoney gelesen hat. „zurück“ = mehr als einen Tag älter als der neueste Abruf (Konten mit Saldo). „ruht“ = seit über N Monaten kein Abruf (vermutlich aufgelöst). Offline-Konten erkennt Kontor an fehlender Bank-/Kontonummer, an Regeln, die in das Konto buchen, und an Kontor-Buchungen; MoneyMoney setzt den Abrufzeitpunkt auch bei Offline-Konten, deshalb zählt er allein nicht.',
  touchid: 'Eingeschaltet: Die Anmeldung am Mac fragt nur nach Touch ID (oder Apple Watch); das Passwortfeld erscheint erst nach Klick auf „Stattdessen Passwort eingeben“. Ausgeschaltet: nur Passwort. Am iPhone gilt immer das Passwort.',
  bilanz_stand: 'Salden am Monatsende; der laufende Monat zeigt den aktuellen Stand. Klick auf ein Konto: Monatsstände ansehen und bearbeiten.',
  abgleich: 'Datenstand in zwei Stufen: „Banken → MM“ = wann MoneyMoney zuletzt bei den Banken abgerufen hat – das löst du in MoneyMoney aus (von Hand oder per Zeitplan dort). „MM → Kontor“ = wann Kontor zuletzt aus MoneyMoney gelesen hat – automatisch im eingestellten Abstand oder sofort mit „Synchronisieren“; dabei werden auch die Regeln angewendet, falls sich etwas geändert hat. Ist MoneyMoney aus oder gesperrt, rechnet Kontor mit dem zuletzt gelesenen Stand weiter und versucht es jede Minute erneut. Bleiben Konten beim Bankabruf zurück (z. B. TAN nötig), steht das hier. Testmodus: Buchungen aus Regeln werden nur vorgeschlagen.',
  kennung: 'Interne Kennung des Bereichs – wird automatisch vergeben und nirgends angezeigt.',
  intervall: 'Der Dienst liest alle N Minuten MoneyMoney (wenn es läuft und entsperrt ist) und führt die Regeln aus – nur wenn sich etwas geändert hat.',
  mm_cat: 'Erlaubt, einzelnen Umsätzen aus Kontor eine Kategorie zuzuweisen. Ändert nur das Kategoriefeld des gewählten Umsatzes – nie Regeln, nie andere Umsätze.',
  belege_ordner: 'Belege werden als normale Dateien in diesem Ordner abgelegt (kein Datenbankformat). Der Ordner kann in iCloud Drive liegen.',
  belege_sub: 'Platzhalter: {jahr}, {monat}, {entitaet} (Bereichsname), {konto}. Beispiel: {jahr}/{entitaet}',
  belege_kommentar: 'Schreibt den Dateinamen des Belegs als Kommentar an den Umsatz in MoneyMoney (ändert das Kommentarfeld).',
  monate_zurueck: 'Wie viele Monate Historie gelesen und angezeigt werden. 0 = alles ab dem ältesten Umsatz.',
  bind: 'Auf diesem Mac ist die Oberfläche immer unter 127.0.0.1 erreichbar. Eine Tailscale-Adresse (100.x.y.z) hier macht sie zusätzlich in deinem privaten Gerätenetz erreichbar (iPhone). Nie das offene Netz. Für https und die Offline-Ansicht: Terminal → python3 kontor.py tls (trägt Adresse und Zertifikat ein).',
  tls: 'Optional: Zertifikat/Schlüssel (PEM) für HTTPS, z. B. aus „tailscale cert“.',
  updates: 'Einzige Netzverbindung von Kontor: einmal täglich bei GitHub nachsehen, ob es eine neuere Version gibt. Installiert wird nur nach Klick.',
  darlehen_iban: 'Die Rate wird am Gegenkonto (IBAN des Zahlungsempfängers) erkannt. Alternativ ein Text, der im Verwendungszweck steht.',
  darlehen_konto: 'Das manuell geführte Darlehenskonto in MoneyMoney, auf dem Kontor die Raten spiegelt und die Zinsen bucht.',
  darlehen_quelle: 'Das Konto, von dem die Rate abgeht (Girokonto).',
  zinsmodell: 'Jahresbasis: Zins = Satz × Stand am 31.12. des Vorjahres, 1/12 je Monat (typisch für private Darlehen mit jährlicher Abrechnung). Restschuld monatlich: Satz/12 × Stand des Vormonats (Bankdarlehen).',
  satz: 'Zinssätze mit Gültigkeitsbeginn, z. B. „2026-01-01: 3,3; 2028-01-01: 3,0“.',
  basis_override: 'Erzwingt die Zinsbasis für ein Jahr (z. B. wenn der Stand am 31.12. nicht der vertraglichen Basis entspricht).',
  beteiligung: 'Zielkonto = Anteil × Nettowert der gewählten Kontengruppe (Summe aller Konten darin). Wird bei jedem Abgleich nachgeführt, wenn die Abweichung über der Schwelle liegt.',
  spiegel: 'Zielkonto = Faktor × Saldo des Quellkontos. Für Kapitalkonten: Faktor −1 spiegelt ein negatives Kapitalkonto der Gesellschaft als positiven Wert im Privatbereich.',
  methode: 'Ø 12/6 Monate: Durchschnitt der abgeschlossenen Monate. Vorjahresmonat: derselbe Monat ein Jahr zuvor. Fester Betrag je Monat. Jahresbetrag/12. MoneyMoney-Budget der Kategorie. Keine = 0.',
  inflation: 'Ausgaben steigen standardmäßig mit dieser Rate. Mit „inflationsbereinigt“ werden Planwerte in heutiger Kaufkraft gezeigt.',
  steig_ein: 'Jährliche Steigerung der Einnahmen (z. B. Gehaltsentwicklung).',
  rendite: 'Jährliche Wertentwicklung für Wertpapiere und Geldanlagen ohne eigene Angabe.',
  ereignis: 'Einmalige oder wiederkehrende Planereignisse: Umschichtung zwischen zwei Konten (z. B. Darlehen aus dem Depot zurückzahlen), Einnahme oder Ausgabe. „Von“/„Nach“ leer = Liquidität.',
  wert_bereich: 'Beteiligungskonto an das Nettovermögen eines anderen Bereichs koppeln: Wert = Anteil × geplantes Nettovermögen des Bereichs.',
  immo_uebergang: 'Erster Monat mit Nutzen und Lasten: ab hier laufen Miete, Kosten, AfA und Zinsen.',
  immo_nk: 'Grunderwerbsteuer, Notar (nur Kaufvertrag), Grundbuch (Auflassung/Eigentumsumschreibung) und Makler erhöhen die AfA-Basis. Kosten für Grundschuld, Gutachten u. ä. sind sofort abziehbar.',
  immo_geb: 'Anteil des Gebäudes am Kaufpreis (Kaufpreisaufteilung, z. B. über Bodenrichtwert). Nur dieser Anteil wird abgeschrieben.',
  immo_afa: 'AfA-Satz p.a. (2 % Wohnen nach 1925, 3 % Gewerbe/Neubau) – oder Restnutzungsdauer aus Gutachten (1/RND).',
  immo_index: 'Indexmiete: Erhöhung zum Jahresbeginn um Faktor × VPI-Änderung seit der letzten Anpassung, sobald die Schwelle überschritten ist (z. B. Faktor 0,75 und Schwelle 5 %). VPI-Basis = Stand bei der letzten Anpassung, VPI aktuell = heutiger Stand, Annahme p.a. = künftige Inflation.',
  immo_kosten: 'Nicht umlagefähige Kosten p.a.: Verwaltung, Hausgeld-Anteil, Steuerberater, Kontoführung, Instandhaltung. Umlagefähige Nebenkosten laufen durch (Mieter zahlt).',
  immo_ruecklage: 'Rücklage für Sonderumlagen/Instandhaltung p.a. – mindert den Cashflow, nicht das steuerliche Ergebnis.',
  immo_darlehen_art: 'Annuität: feste Monatsrate (Zins + Tilgung). Tilgungsdarlehen: feste Tilgung je Monat plus Zins auf den Restsaldo. Endfällig: nur Zinsen, Rückzahlung bei Fälligkeit.',
  immo_abrechnung: 'Monatlich: Zins auf den laufenden Saldo (Bank). Jährlich: Zins auf den Stand zum 1. Januar, nachschüssig (z. B. privates Verkäuferdarlehen).',
  immo_sonder: 'Laufende Sondertilgung je Monat ab einem Datum (z. B. wenn ein anderes Darlehen ausläuft) und einzelne Sondertilgungen mit Datum.',
  immo_zinsbindung: 'Nach Ende der Zinsbindung gilt der Anschlusszins (Annahme). Ohne Angabe läuft der Zinssatz weiter.',
  immo_faellig: 'Endfällige Darlehen: bei Fälligkeit zurückzahlen (aus Liquidität) oder offen lassen (Hinweis in der Kalkulation).',
  immo_abziehbar: 'Zinsen nicht abziehbarer Darlehen (z. B. Gesellschafterdarlehen) zählen im Cashflow, nicht im steuerlichen Ergebnis.',
  immo_ges: 'Gesellschafter mit Gewinnanteil und persönlichem Steuersatz: daraus ergeben sich die Steuer je Gesellschafter und die Ausschüttung.',
  immo_aussch: 'Bei positivem Ergebnis schüttet die Gesellschaft diesen Anteil des Ergebnisses aus, damit die Gesellschafter ihre Steuer zahlen können. Bei negativem Ergebnis: Steuererstattung der Gesellschafter (optional im Cashflow).',
  immo_wert: 'Angenommene Wertentwicklung des Objekts p.a. Wirkt auf Objektwert, Eigenkapital im Objekt und IRR – nicht auf den Cashflow.',
  immo_verkauf: 'Optional: Verkaufsjahr für die IRR-Berechnung (Erlös = Objektwert − Kosten − Restschuld). Ohne Angabe: Verkauf am Ende des Horizonts.',
  immo_planung: 'Übernimmt Miete, Kosten, Zinsen, Tilgung, Restschuld, Objektwert und Ausschüttungen der aktiven Kalkulation in die Planung des Bereichs. Zeilen der Vermietungskategorie und verknüpfte Darlehenskonten werden damit geplant.',
  immo_kategorie: 'Vermietungskategorie des Objekts in MoneyMoney (Vermietung \\ Objekt). Damit vergleicht Kontor Soll (Kalkulation) und Ist (Umsätze) und übernimmt die Planung.',
  immo_objektkonto: 'Das Offline-Konto, das den Objektwert in der Bilanz trägt (z. B. mit dem Kaufpreis).',
  immo_darlehen_konten: 'Zuordnung der Darlehen der Kalkulation zu den Darlehenskonten in MoneyMoney (für Soll/Ist und Planung).',
  dokumente: 'Verknüpfungen zu Dateien auf dem Mac (Kaufvertrag, Darlehensvertrag, Gutachten …). Die Dateien bleiben, wo sie sind – auch in iCloud Drive.',
  offline: 'Als App auf dem iPhone (Zum Home-Bildschirm) speichert Kontor die zuletzt geladenen Daten auf dem Gerät. Ist der Mac aus oder nicht erreichbar, öffnet das Passwort diese Kopie – nur lesen, Stand des letzten Abrufs. Braucht https (Tailscale-Zertifikat, siehe Einstellungen).',
  paket: 'Einstellungspaket: Regeln, Bereiche, Positionen, Kategorie- und Steuerzuordnungen, Immobilien – ohne Passwörter, Adresse/Port oder Daten.',
};
const hq = k => H[k] ? `<span class="hq" tabindex="0" data-tip="${esc(H[k])}">?</span>` : '';
// Tooltip als eigenes Element: unterhalb, wenn oben kein Platz ist; nie ueber den Fensterrand hinaus
(function tooltips() {
  let tip = null, cur = null;
  const hide = () => { if (tip) tip.remove(); tip = null; cur = null; };
  const show = el => {
    hide(); cur = el;
    tip = document.createElement('div'); tip.className = 'tip'; tip.textContent = el.dataset.tip; document.body.appendChild(tip);
    const r = el.getBoundingClientRect(), w = Math.min(340, window.innerWidth - 16); tip.style.maxWidth = w + 'px';
    const tr = tip.getBoundingClientRect();
    let left = r.left + r.width / 2 - tr.width / 2; left = Math.max(8, Math.min(left, window.innerWidth - tr.width - 8));
    let top = r.top - tr.height - 8; if (top < 8) top = r.bottom + 8;
    if (top + tr.height > window.innerHeight - 8) top = Math.max(8, window.innerHeight - tr.height - 8);
    tip.style.left = left + 'px'; tip.style.top = top + 'px';
  };
  document.addEventListener('mouseover', e => { const el = e.target.closest && e.target.closest('.hq'); if (el && el !== cur) show(el); });
  document.addEventListener('mouseout', e => { const el = e.target.closest && e.target.closest('.hq'); if (el && el === cur && !(e.relatedTarget && el.contains(e.relatedTarget))) hide(); });
  document.addEventListener('focusin', e => { const el = e.target.closest && e.target.closest('.hq'); if (el) show(el); });
  document.addEventListener('focusout', e => { if (e.target.closest && e.target.closest('.hq')) hide(); });
  document.addEventListener('click', e => { const el = e.target.closest && e.target.closest('.hq'); if (el) { e.preventDefault(); if (cur === el && tip) hide(); else show(el); } else hide(); });
  window.addEventListener('scroll', hide, true); window.addEventListener('resize', hide);
})();

const S = { tab: 'uebersicht', modus: 'monate', plan: true, real: false, nullzeilen: false, collapsed: {}, csrf: null, bereich: null,
            DATA: null, CFG: null, KONTEN: [], KATS: [], STATUS: null, steuerJahr: null, steuerEnt: null, vorschlag: false,
            uf: {entitaet: '', jahr: '', konto: '', q: '', ohne_beleg: false, ohne_kategorie: false, richtung: ''}, sel: new Set(), drawerTx: null };

function toast(msg, ms = 2600) { const t = $('#toast'); t.textContent = msg; t.classList.remove('hidden'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add('hidden'), ms); }
function banner(msg, kind = '') { const b = $('#banner'); if (!msg) { b.classList.add('hidden'); return; } b.textContent = msg; b.className = 'banner ' + kind; }

// Am Mac selbst gibt es keine Offline-Ansicht: der Dienst ist erreichbar oder nicht (Tests können das Gerät als "entfernt" markieren)
let IS_LOCAL = ['127.0.0.1', 'localhost', '::1', '[::1]'].includes(location.hostname);
try { if (localStorage.getItem('kontor.testRemote') === '1') IS_LOCAL = false; } catch (e) {}
async function api(path, body, method, netMode) {
  const opts = { method: method || (body === undefined ? 'GET' : 'POST'), headers: {}, credentials: 'same-origin' };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  if (S.csrf) opts.headers['X-CSRF-Token'] = S.csrf;
  const mode = netMode || (IS_LOCAL ? 'direct' : (OFFLINE.mode && opts.method === 'GET' ? 'cache' : ''));
  if (mode) opts.headers['X-Kontor-Net'] = mode;
  let ctl = null;
  if (mode === 'direct' && !IS_LOCAL) { ctl = new AbortController(); opts.signal = ctl.signal; setTimeout(() => ctl.abort(), 20000); }
  let r;
  try { r = await fetch(path, opts); } catch (e) { throw new Error(IS_LOCAL ? 'Kontor-Dienst nicht erreichbar (läuft er? Terminal: bash install.sh).' : 'Der Mac ist nicht erreichbar.'); }
  if (r.headers.get('X-Kontor-Offline') === '1' && opts.method === 'GET' && !OFFLINE.mode && !IS_LOCAL && mode !== 'direct' && path !== '/api/session') {
    // Zwischengespeicherte Antwort, obwohl wir online waren: Server nur langsam? Gegenprobe ohne Zeitlimit
    try { return await api(path, body, method, 'direct'); }
    catch (e) { OFFLINE.mode = true; offlineBanner(); }
  }
  let data = null;
  try { data = await r.json(); } catch (e) { data = {}; }
  if (r.headers.get('X-Kontor-Offline') === '1') {
    const at = r.headers.get('X-Kontor-Cached-At'); if (at) OFFLINE.stand = at;
    if (IS_LOCAL) throw new Error('Der Kontor-Dienst antwortet nicht.');
  } else if (OFFLINE.mode && opts.method === 'GET' && r.ok && path !== '/api/session') { OFFLINE.mode = false; OFFLINE.stand = null; offlineBanner(); }
  if (r.status === 401 && path !== '/api/session') { S.csrf = null; if (OFFLINE.mode) { OFFLINE.mode = false; OFFLINE.stand = null; checkSession(); } else showLogin(); throw new Error('nicht angemeldet'); }
  if (!r.ok) { const e = new Error(data.fehler || ('Fehler ' + r.status)); e.data = data; throw e; }
  if (opts.method !== 'GET' && data && data.bericht === 'angefordert') afterRebuild(data);
  return data;
}
function download(url) { const a = document.createElement('a'); a.href = url; a.download = ''; document.body.appendChild(a); a.click(); a.remove(); }
const xlsxBtn = (was, extra = '') => `<button class="xlsx small" data-xlsx="${was}" ${extra}>Excel</button>`;

// ---------------------------------------------------------------- Offline (PWA am iPhone, Mac nicht erreichbar)
const OFFLINE = {mode: false, stand: null, idle: null};
function offlineBanner() {
  if (OFFLINE.mode) { const b = $('#banner'); b.innerHTML = `Offline-Ansicht – der Mac ist nicht erreichbar. Stand ${OFFLINE.stand ? new Date(OFFLINE.stand).toLocaleString('de-DE', {dateStyle: 'short', timeStyle: 'short'}) : 'unbekannt'}; nur lesen. ${hq('offline')}`; b.className = 'banner info'; }
  else if (S.DATA) banner('');
  idleReset();
}
function idleReset() {
  clearTimeout(OFFLINE.idle);
  if (OFFLINE.mode && S.csrf) OFFLINE.idle = setTimeout(() => { S.csrf = null; showLogin(); }, Math.max(1, ((S.CFG && S.CFG.oberflaeche) || {}).sperre_minuten || 15) * 60000);
}
for (const ev of ['pointerdown', 'keydown', 'touchstart']) document.addEventListener(ev, idleReset, {passive: true});
async function offlinePing() {
  // Im Offline-Modus alle 30 s prüfen, ob der Mac wieder da ist (Sitzung ist nie zwischengespeichert)
  if (!OFFLINE.mode || document.hidden) return;
  try { const s = await api('/api/session'); if (!s.offline) await revalidate(); } catch (e) {}
}
setInterval(offlinePing, 30000);
const hexOf = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
const bytesOf = hex => new Uint8Array(hex.match(/../g).map(h => parseInt(h, 16)));
async function offlineLogin(pw) {
  if (!(window.crypto && crypto.subtle)) throw new Error('Offline-Anmeldung braucht eine sichere Verbindung (https).');
  const v = await api('/api/offline/verifier');
  if (!v.offline) throw new Error('Für diese Installation ist noch kein Offline-Prüfwert gespeichert – einmal mit Passwort am Mac anmelden, dann wieder hier.');
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits({name: 'PBKDF2', hash: 'SHA-256', salt: bytesOf(v.offline.salt), iterations: v.offline.rounds}, key, 256);
  if (hexOf(bits) !== v.offline.hash) throw new Error('Passwort falsch.');
  if (S.CFG) S.CFG.oberflaeche = Object.assign(S.CFG.oberflaeche || {}, {sperre_minuten: v.sperre_minuten});
  return true;
}
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});

// ---------------------------------------------------------------- Anmeldung
let SESSION = null;
async function checkSession() {
  try { SESSION = await api('/api/session'); } catch (e) { $('#login').classList.remove('hidden'); $('#login-err').textContent = e.message + ' Neuer Versuch in 5 s …'; setTimeout(checkSession, 5000); return; }
  $('#ver').textContent = 'v' + (SESSION.version || '');
  if (SESSION.offline && IS_LOCAL) { $('#login').classList.remove('hidden'); $('#login-err').textContent = 'Der Kontor-Dienst antwortet nicht – läuft er? (Terminal: bash install.sh). Neuer Versuch in 5 s …'; setTimeout(checkSession, 5000); return; }
  if (SESSION.offline) { OFFLINE.mode = true; showLogin(); return; }
  OFFLINE.mode = false;
  if (SESSION.angemeldet) { S.csrf = SESSION.csrf; await enterApp(); } else showLogin();
}
function showLogin() {
  $('#shell').classList.add('hidden'); $('#login').classList.remove('hidden'); $('#drawer').classList.remove('open');
  const setup = SESSION && SESSION.einrichtung_noetig && !OFFLINE.mode;
  $('#login-text').textContent = OFFLINE.mode ? 'Der Mac ist nicht erreichbar. Passwort eingeben, um die auf diesem Gerät gespeicherte Ansicht zu öffnen (nur lesen).'
    : setup ? 'Erster Start: Passwort festlegen (mindestens 10 Zeichen). Es schützt den Zugang zur Oberfläche; die Daten liegen zusätzlich verschlüsselt auf diesem Mac.'
    : (SESSION && SESSION.einrichtung_nur_lokal ? 'Noch kein Passwort festgelegt – die Einrichtung ist nur direkt am Mac möglich.' : 'Zugang gesperrt.');
  // Touch ID eingeschaltet (am Mac): nur Touch ID, Passwort erst auf Wunsch – nie beides gleichzeitig
  const tid = !setup && !OFFLINE.mode && SESSION && SESSION.touchid;
  const tidMode = tid && !LOGIN.pw;
  $('#login-pw2').classList.toggle('hidden', !setup);
  $('#setup-tid').classList.toggle('hidden', !(setup && SESSION && SESSION.touchid_verfuegbar));
  $('#login-btn').textContent = setup ? 'Passwort festlegen' : 'Anmelden';
  $('#tid-box').classList.toggle('hidden', !tidMode);
  $('#login-form').classList.toggle('hidden', !!tidMode);
  $('#tid-instead').classList.toggle('hidden', !(tid && LOGIN.pw));
  $('#login-err').textContent = SESSION && SESSION.gesperrt_sekunden ? ('Gesperrt für ' + SESSION.gesperrt_sekunden + ' s nach Fehlversuchen.') : '';
  if (!tidMode) setTimeout(() => $('#login-pw').focus(), 50);
  if (tidMode && !document.hidden) tryTouchId(true);     // Touch ID sofort anbieten, ohne Klick
}
const LOGIN = {pw: false};      // true = Nutzer hat "Stattdessen Passwort eingeben" gewählt
const TID = {pending: false, lastTry: 0};
async function tryTouchId(auto) {
  if (TID.pending || LOGIN.pw || !(SESSION && SESSION.touchid && !SESSION.einrichtung_noetig)) return;
  if (auto && TID.skipNext) { TID.skipNext = false; return; }           // nach bewusstem Sperren nicht sofort wieder fragen
  if (auto && Date.now() - TID.lastTry < 4000) return;
  TID.pending = true; TID.lastTry = Date.now();
  $('#login-err').textContent = 'Touch ID … bitte am Mac bestätigen.';
  try { const r = await api('/api/touchid', {}); S.csrf = r.csrf; $('#login-err').textContent = ''; await enterApp(); }
  catch (err) { $('#login-err').textContent = auto ? 'Touch ID nicht bestätigt – erneut versuchen oder Passwort eingeben.' : err.message; }
  finally { TID.pending = false; }
}
let REVAL = 0;
async function revalidate() {
  // Beim Zurueckkehren zum Fenster: Sitzung pruefen; gesperrt -> Anmeldeseite (mit Touch ID), sonst nichts
  if (document.hidden || Date.now() - REVAL < 2000) return;
  REVAL = Date.now();
  let s;
  try { s = await fetch('/api/session', {credentials: 'same-origin'}).then(r => r.json()); } catch (e) { return; }
  const loginShown = !$('#login').classList.contains('hidden');
  if (s.offline) { if (IS_LOCAL) return; if (!OFFLINE.mode && !loginShown) { OFFLINE.mode = true; offlineBanner(); } return; }   // Mac weg: gespeicherte Ansicht bleibt offen
  if (OFFLINE.mode) { OFFLINE.mode = false; OFFLINE.stand = null; SESSION = s; S.csrf = s.angemeldet ? s.csrf : null; if (s.angemeldet) { await enterApp(); } else showLogin(); return; }
  if (!s.angemeldet && !loginShown) { SESSION = s; S.csrf = null; showLogin(); }
  else if (!s.angemeldet && loginShown && s.touchid && !s.einrichtung_noetig) { SESSION = s; tryTouchId(true); }
  else if (s.angemeldet && loginShown) { SESSION = s; S.csrf = s.csrf; await enterApp(); }
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) revalidate(); });
window.addEventListener('focus', revalidate);
$('#login-form').addEventListener('submit', async e => {
  e.preventDefault();
  const pw = $('#login-pw').value, setup = SESSION && SESSION.einrichtung_noetig && !OFFLINE.mode;
  if (setup && pw !== $('#login-pw2').value) { $('#login-err').textContent = 'Passwörter stimmen nicht überein.'; return; }
  if (OFFLINE.mode) {
    $('#login-err').textContent = 'Prüfe …';
    try { await offlineLogin(pw); S.csrf = 'offline'; $('#login-pw').value = ''; $('#login-err').textContent = ''; await enterApp(); } catch (err) { $('#login-err').textContent = err.message; }
    return;
  }
  try {
    const r = await api(setup ? '/api/setup' : '/api/login', setup && SESSION.touchid_verfuegbar ? {passwort: pw, touchid: $('#setup-tid-cb').checked} : {passwort: pw});
    LOGIN.pw = false;
    S.csrf = r.csrf; $('#login-pw').value = ''; $('#login-pw2').value = '';
    await enterApp();
  } catch (err) { $('#login-err').textContent = err.message; }
});
$('#touchid-btn').addEventListener('click', () => tryTouchId(false));
$('#pw-instead').addEventListener('click', () => { LOGIN.pw = true; showLogin(); });
$('#tid-instead').addEventListener('click', () => { LOGIN.pw = false; showLogin(); });
$('#sync-btn').addEventListener('click', () => syncNow());
$('.side .brand').addEventListener('click', e => { location.hash = e.target.closest('#ver') ? '#updates' : '#uebersicht'; });
$('#lock-btn').addEventListener('click', async () => { try { await api('/api/lock', {}); } catch (e) {} S.csrf = null; TID.skipNext = true; await checkSession(); });

async function enterApp() {
  $('#login').classList.add('hidden'); $('#shell').classList.remove('hidden');
  await loadAll();
  route();
  if (!OFFLINE.mode) api('/api/offline/verifier').catch(() => {});       // für die Offline-Ansicht zwischenspeichern
  offlineBanner();
}
async function loadAll() {
  const [status, data, cfg, konten, kats] = await Promise.all([
    api('/api/status'), api('/api/dataset'), api('/api/config'), api('/api/accounts'), api('/api/categories')]);
  S.STATUS = status; S.DATA = data.leer ? null : data; S.CFG = cfg; S.KONTEN = konten.konten || []; S.KATS = kats.kategorien || [];
  if (!(status.bericht || {}).laeuft) BER.stand = (status.bericht || {}).stand || '';     // dieser Stand ist jetzt geladen
  S.einrichtung = data.einrichtung;
  if (S.DATA) { const keys = Object.keys(S.DATA.bereiche || {}); if (!S.bereich || !keys.includes(S.bereich)) S.bereich = S.DATA.haupt || keys[0]; }
  if (OFFLINE.mode) offlineBanner();
  else if (status.update && status.update.neuer) banner('Kontor ' + status.update.verfuegbar + ' ist verfügbar – unter „Updates“ installieren.', 'info');
  else if (S.DATA && (S.DATA.konten_neu || []).length) { const b = $('#banner'); b.innerHTML = `Neue oder unbestätigte Konten: ${esc(S.DATA.konten_neu.slice(0, 4).map(k => k.name).join(', '))}${S.DATA.konten_neu.length > 4 ? ' …' : ''} – <a href="#einrichtung/konten">Bereich und Position bestätigen</a>`; b.className = 'banner info'; }
  else if (S.DATA) banner('');
  statusMini(); bereichSeg();
}
const B = () => (S.DATA && S.DATA.bereiche && S.DATA.bereiche[S.bereich] && !S.DATA.bereiche[S.bereich].fehler) ? S.DATA.bereiche[S.bereich] : null;
const BN = u => (S.DATA && S.DATA.bereich_namen && S.DATA.bereich_namen[u || S.bereich]) || '';
function mmState(st) {
  const m = st.moneymoney || {};
  if (!m.laeuft) return {cls: 'off', text: 'MoneyMoney aus'};
  if (m.gesperrt === true) return {cls: 'warn', text: 'MoneyMoney gesperrt'};
  if (m.gesperrt === false) return {cls: 'ok', text: 'MoneyMoney läuft'};
  return {cls: 'ok', text: 'MoneyMoney läuft'};
}
const nKonten = n => n === 1 ? 'Ein Konto' : n + ' Konten';
function fmtZeit(t) {
  // 'YYYY-MM-DD HH:MM' -> 'heute 13:40' / 'gestern 08:12' / '03.11. 22:10' / '03.11.25 22:10' (Ortszeit)
  if (!t) return '';
  const iso = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  const now = new Date(), tag = t.slice(0, 10), zeit = t.slice(11, 16);
  if (tag === iso(now)) return 'heute ' + zeit;
  if (tag === iso(new Date(now.getTime() - 864e5))) return 'gestern ' + zeit;
  return t.slice(8, 10) + '.' + t.slice(5, 7) + '.' + (t.slice(0, 4) === String(now.getFullYear()) ? '' : t.slice(2, 4)) + ' ' + zeit;
}
function viewCtl(cols) {
  // Spaltenansicht der Tabellen (in der Werkzeugleiste der Seite)
  const m = [['monate', 'Monate'], ['monate_jahre', 'Monate + Jahre'], ['jahre', 'Jahre']];
  return cols ? `<div class="seg" id="modus-seg">${m.map(([k, l]) => `<button data-m="${k}" class="${S.modus === k ? 'on' : ''}">${l}</button>`).join('')}</div>` : '';
}
function topCtl() {
  // Kleine Einstellungen oben rechts: Plan, inflationsbereinigt, leere Zeilen (nur in den Auswertungen)
  const el = $('#top-ctl'), tabs = ['uebersicht', 'bilanz', 'kapitalfluss', 'planung'];
  if (!tabs.includes(S.tab) || !S.DATA) { el.innerHTML = ''; return; }
  const cols = S.tab !== 'uebersicht';
  el.innerHTML = `<label class="switch"><input type="checkbox" id="planan" ${S.plan ? 'checked' : ''}><i></i>Plan</label><label class="switch"><input type="checkbox" id="realan" ${S.real ? 'checked' : ''}><i></i>inflationsbereinigt</label>${cols ? `<label class="switch"><input type="checkbox" id="nullzeilen" ${S.nullzeilen ? 'checked' : ''}><i></i>leere Zeilen</label>` : ''}`;
}
function hasRules() { const c = S.CFG || {}; return !!((c.darlehen || []).length || (c.beteiligungen || []).length || (c.saldo_spiegel || []).length); }
function statusMini() {
  const st = S.STATUS; if (!st) return;
  const mm = mmState(st), m = st.moneymoney || {}, b = st.bericht || {}, l = st.letzter_lauf, ba = m.bankabruf;
  const zeile = (k, v, title) => `<div class="sm-row"${title ? ' title="' + esc(title) + '"' : ''}><span>${k}</span><b>${v}</b></div>`;
  let h = `<div class="sm-head"><span class="dot ${mm.cls}"></span>${mm.text} ${hq('abgleich')}</div>`;
  if (m.stand || ba) {
    const n = ba ? ba.zurueck_anzahl : 0;
    const warn = n ? ` <span class="sm-badge" title="${esc(n + (n === 1 ? ' Konto' : ' Konten') + ' länger nicht abgerufen: ' + ba.zurueck.slice(0, 5).map(k => k.name).join(', ') + (n > 5 ? ' …' : '') + ' – Details unter Synchronisierung')}">⚠ ${n}</span>` : '';
    h += `<a href="#synchronisierung" class="sm-link" title="Details zur Synchronisierung">`
      + zeile('Banken → MM', (ba ? esc(fmtZeit(ba.neuester)) : '–') + warn, '')
      + zeile('MM → Kontor', m.stand ? esc(fmtZeit(m.stand)) : '–', '') + '</a>';
  } else h += '<div>noch keine Daten aus MoneyMoney</div>';
  if (st.neustart_ausstehend) h += '<div><span class="spin" style="width:9px;height:9px;margin-right:4px"></span>Version ' + esc(st.neustart_ausstehend) + ' wird geladen …</div>';
  else if (b.laeuft) h += '<div><span class="spin" style="width:9px;height:9px;margin-right:4px"></span>Wird neu berechnet …</div>';
  if (m.luecken) h += '<div><a href="#synchronisierung">⚠ Depotstände prüfen</a></div>';
  if (m.problem) h += `<div><a href="#synchronisierung" title="${esc(m.problem.text)}">⚠ MoneyMoney lief, Kontor konnte nicht lesen</a></div>`;
  if (hasRules() && st.probelauf) h += '<div><b>Testmodus</b> – Regeln buchen nichts</div>';
  if (l && l.fehler) h += '<div><a href="#buchungen">⚠ letzter Abgleich mit Fehler</a></div>';
  else if (l && l.probelauf && (l.vorschlaege || []).length) h += `<div><a href="#buchungen">${l.vorschlaege.length} Buchungsvorschläge</a></div>`;
  $('#status-mini').innerHTML = h;
  const sb = $('#sync-btn');
  if (sb) {
    const busy = !!(st.dienst.laeuft || SYNC.busy);
    sb.classList.toggle('busy', busy); sb.disabled = busy || OFFLINE.mode;
    sb.title = OFFLINE.mode ? 'Offline-Ansicht – der Mac ist nicht erreichbar' : 'Jetzt aus MoneyMoney lesen, Regeln anwenden und Auswertungen aktualisieren';
  }
  const upd = $('#nav a[href="#updates"]'); if (upd) { let d = upd.querySelector('.nbadge'); const neu = !!(st.update && st.update.neuer); if (neu && !d) { d = document.createElement('span'); d.className = 'nbadge'; d.title = 'Update ' + st.update.verfuegbar + ' verfügbar'; upd.appendChild(d); } else if (!neu && d) d.remove(); }
  if (!st.ablage.verschluesselt) banner('Daten liegen unverschlüsselt (Verschlüsselung nicht verfügbar).', 'err');
  else if (st.ablage.schluessel === 'datei') banner('Datenschlüssel liegt als Datei (Schlüsselbund nicht verfügbar).');
}
const BER = {stand: '', timer: null};
const SYNC = {busy: false};
const MMH = {busy: false};
const DATA_TABS = ['uebersicht', 'bilanz', 'kapitalfluss', 'planung', 'steuer', 'depots', 'immobilien', 'umsaetze', 'zuordnen', 'buchungen'];
async function pollStatus() {
  // Status holen; läuft ein Berichtsneubau, öfter nachsehen und nach Abschluss die Daten frisch laden
  S.STATUS = await api('/api/status'); statusMini();
  if (S.STATUS.version && SESSION && SESSION.version && S.STATUS.version !== SESSION.version) { toast('Neue Version ' + S.STATUS.version + ' – Seite wird neu geladen …', 3000); setTimeout(() => location.reload(), 1200); return; }
  if (S.STATUS.neustart_ausstehend) { clearTimeout(BER.timer); BER.timer = setTimeout(() => pollStatus().catch(() => setTimeout(() => location.reload(), 4000)), 3000); return; }
  const b = S.STATUS.bericht || {};
  clearTimeout(BER.timer);
  if (b.laeuft) { BER.timer = setTimeout(() => pollStatus().catch(() => {}), 3000); return; }
  if ((b.stand || '') !== BER.stand) {
    BER.stand = b.stand || '';
    if (b.fehler) { toast('Auswertung konnte nicht aktualisiert werden: ' + b.fehler, 6000); return; }
    await loadAll();
    const dr = $('#drawer');
    if (dr.classList.contains('open') && HD.uuid && $('#hq-seg', dr)) { if (!HD.live && !$$('#h-grid input:not(.auto)', dr).some(i => i.value !== i.defaultValue)) { try { await openHistDrawer(HD.uuid); } catch (e) {} } }
    else if (DATA_TABS.includes(S.tab) && !dr.classList.contains('open')) route();
    toast('Auswertung aktualisiert');
  }
}
function afterRebuild(r) {
  // Antwort einer Änderung, die den Bericht neu baut: sofort Status prüfen (Hintergrund)
  if (r && r.bericht === 'angefordert') pollStatus().catch(() => {});
}
function bereichSeg() {
  const seg = $('#bereich-seg'); if (!S.DATA) { seg.classList.add('hidden'); return; }
  const keys = Object.keys(S.DATA.bereiche || {});
  seg.classList.toggle('hidden', keys.length < 2 || !['uebersicht', 'bilanz', 'kapitalfluss', 'planung'].includes(S.tab));
  seg.innerHTML = keys.map(k => `<button data-b="${k}" class="${k === S.bereich ? 'on' : ''}">${esc(BN(k))}</button>`).join('');
  $$('button', seg).forEach(b => b.addEventListener('click', () => { S.bereich = b.dataset.b; S.collapsed = {}; bereichSeg(); route(); }));
}

// ---------------------------------------------------------------- Spalten, Werte
function cols(D) {
  D = D || B(); const ist = D.monate, plan = S.plan ? (D.plan_monate || []) : [];
  const mcol = (m, isPlan) => ({key: m, label: ML(m), months: [m], plan: isPlan, cur: m === D.ist_bis, year: false});
  const all = [...ist.map(m => mcol(m, false)), ...plan.map(m => mcol(m, true))];
  if (S.modus === 'monate') return all;
  const years = {};
  for (const c of all) { const y = c.key.slice(0, 4); (years[y] = years[y] || {months: [], plan: false, ist: false}).months.push(c.key); if (c.plan) years[y].plan = true; else years[y].ist = true; }
  const ycol = y => ({key: y, label: (S.modus === 'jahre' ? y : 'Σ ' + y) + (years[y].plan && years[y].ist ? ' Ist+Plan' : '') + (years[y].months.length < 12 ? ' · ' + years[y].months.length + ' Mon.' : ''), months: years[y].months, plan: years[y].plan && !years[y].ist, mixed: years[y].plan && years[y].ist, cur: false, year: true});
  if (S.modus === 'jahre') return Object.keys(years).sort().map(ycol);
  const out = [];
  for (const c of all) { out.push(c); if (c.key.endsWith('-12') || c.key === all[all.length - 1].key) out.push(ycol(c.key.slice(0, 4))); }
  return out;
}
function defl(m) {
  const D = B(); if (!S.real || !D || !D.plan_monate || !D.plan_monate.includes(m)) return 1;
  const i = D.plan_monate.indexOf(m) + 1, infl = +((D.plan || {}).inflation_prozent_pa || 0);
  return Math.pow(1 + infl / 100, -i / 12);
}
const sumOver = (vals, months) => months.reduce((a, m) => a + (vals[m] ?? 0) * defl(m), 0);
const lastOf = (vals, months) => { for (let i = months.length - 1; i >= 0; i--) if (vals[months[i]] != null) return vals[months[i]] * defl(months[i]); return null; };
function cls(v, c) { let s = ''; if (c.plan) s += ' plan'; if (c.cur && S.modus !== 'jahre') s += ' cur'; if (c.year) s += ' year'; if (v == null || Math.abs(v) < 0.005) s += ' zero'; else s += v < 0 ? ' neg' : ' pos'; return s; }
const cells = (C, fn) => C.map(c => { const v = fn(c); return `<td class="${cls(v, c)}">${F(v)}</td>`; }).join('');
const isCurCol = c => { const D = B(), ib = (D && D.ist_bis) || ''; return c.year ? c.key === ib.slice(0, 4) && S.modus === 'jahre' : c.key === ib; };
const thead = (first, C) => `<thead><tr><th>${first}</th>${C.map(c => `<th class="${c.year ? 'year' : ''}${c.plan ? ' plan' : ''}"${isCurCol(c) ? ' data-cur="1"' : ''} title="${c.plan ? 'Plan' : c.mixed ? 'Ist + Plan' : 'Ist'}">${c.label}</th>`).join('')}</tr></thead>`;
const noData = '<div class="card"><div class="v s">Noch keine Daten</div><div class="d">Unter „Einrichtung“ den Bericht erstellen (MoneyMoney muss laufen und entsperrt sein) – danach erscheinen Übersicht, Bilanz, Kapitalfluss und Planung.</div></div>';
const sumsOf = (D, name, months) => months.reduce((a, m) => a + (D.kapitalfluss.summen[m]?.[name] ?? 0) * defl(m), 0);

// ---------------------------------------------------------------- Diagramme (SVG)
function sparkline(vals, color = 'var(--accent)', W = 160, H = 34) {
  const v = vals.filter(x => x != null); if (v.length < 2) return '';
  const min = Math.min(...v), max = Math.max(...v), x = i => 2 + i * (W - 4) / (v.length - 1), y = n => H - 3 - (n - min) * (H - 6) / ((max - min) || 1);
  const d = v.map((n, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(n).toFixed(1)).join(' ');
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><path d="${d} L${x(v.length - 1).toFixed(1)} ${H} L2 ${H} Z" fill="${color}" opacity=".12"/><path d="${d}" fill="none" stroke="${color}" stroke-width="1.8" vector-effect="non-scaling-stroke"/></svg>`;
}
function chartStack(D) {
  const keys = D.monate.slice(-36), pm = S.plan ? (D.plan_monate || []) : [], all = [...keys, ...pm];
  const leaves = D.bilanz.zeilen.filter(r => !r.gruppe && r.rolle && ROLE[r.rolle]);
  const series = {}; for (const r of Object.keys(ROLE)) series[r] = all.map(m => 0);
  for (const r of leaves) keys.forEach((m, i) => { series[r.rolle][i] += r.werte[m] || 0; });
  const pr = D.bilanz.projektion;
  if (pm.length && pr) { for (const row of pr.zeilen) { const leaf = D.bilanz.zeilen.find(z => z.id === row.id && !z.gruppe); if (!leaf || !ROLE[leaf.rolle]) continue; pm.forEach((m, j) => { series[leaf.rolle][keys.length + j] += (row.werte[m] || 0) * defl(m); }); } }
  const nw = all.map(m => (D.bilanz.nettovermoegen[m] ?? (pr ? pr.nettovermoegen[m] : null)) * defl(m));
  const posTot = all.map((m, i) => Object.keys(ROLE).reduce((a, r) => a + Math.max(0, series[r][i]), 0));
  const negTot = all.map((m, i) => Object.keys(ROLE).reduce((a, r) => a + Math.min(0, series[r][i]), 0));
  const W = 920, H = 280, P = {l: 56, r: 12, t: 12, b: 26}, max = Math.max(...posTot, ...nw.filter(v => v != null), 1), min = Math.min(...negTot, ...nw.filter(v => v != null), 0);
  const x = i => P.l + i * (W - P.l - P.r) / Math.max(1, all.length - 1), y = v => P.t + (max - v) * (H - P.t - P.b) / ((max - min) || 1);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}">`;
  const ticks = niceTicks(min, max, 5);
  for (const t of ticks) s += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--line)"/><text x="${P.l - 6}" y="${y(t) + 4}" text-anchor="end">${Fk(t)}</text>`;
  const up = all.map(() => 0), down = all.map(() => 0);
  for (const r of Object.keys(ROLE)) {
    const pts = []; const vals = series[r]; if (vals.every(v => Math.abs(v) < 0.5)) continue;
    const top = [], bot = [];
    vals.forEach((v, i) => { if (v >= 0) { bot.push([x(i), y(up[i])]); up[i] += v; top.push([x(i), y(up[i])]); } else { bot.push([x(i), y(down[i])]); down[i] += v; top.push([x(i), y(down[i])]); } });
    const d = top.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ') + ' ' + bot.slice().reverse().map(p => 'L' + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ') + ' Z';
    s += `<path d="${d}" fill="${ROLE[r][1]}" opacity=".55"/>`;
  }
  const line = (from, to, dash) => { const pts = []; for (let i = from; i < to; i++) if (nw[i] != null) pts.push((pts.length ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(nw[i]).toFixed(1)); return pts.length ? `<path d="${pts.join(' ')}" fill="none" stroke="var(--fg)" stroke-width="2" ${dash ? 'stroke-dasharray="5 4" opacity=".7"' : ''}/>` : ''; };
  s += line(0, keys.length, false) + (pm.length ? line(keys.length - 1, all.length, true) : '');
  if (pm.length) s += `<line x1="${x(keys.length - 1)}" x2="${x(keys.length - 1)}" y1="${P.t}" y2="${H - P.b}" stroke="var(--line-2)" stroke-dasharray="3 3"/>`;
  all.forEach((k, i) => { if (k.endsWith('-01') || (i === 0 && +k.slice(5) <= 9)) s += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${k.slice(0, 4)}</text>`; });
  s += '</svg><div class="chart-legend">' + Object.entries(ROLE).filter(([r]) => !series[r].every(v => Math.abs(v) < 0.5)).map(([r, [l, c]]) => `<span><i style="background:${c}"></i>${l}</span>`).join('') + '<span><i style="background:var(--fg)"></i>Nettovermögen' + (pm.length ? ' (gestrichelt: Plan)' : '') + '</span></div>';
  return s;
}
function chartCashflow(D) {
  const keys = D.monate.slice(-24), pm = S.plan ? (D.plan_monate || []).slice(0, 12) : [], all = [...keys, ...pm], sums = D.kapitalfluss.summen;
  const ein = all.map(m => (sums[m]?.Einnahmen ?? 0) * defl(m)), aus = all.map(m => (sums[m]?.Ausgaben ?? 0) * defl(m)), op = all.map(m => (sums[m]?.Operativ ?? 0) * defl(m));
  const W = 920, H = 240, P = {l: 56, r: 12, t: 12, b: 26}, max = Math.max(...ein, ...op, 1), min = Math.min(...aus, ...op, 0);
  const n = all.length, bw = (W - P.l - P.r) / n, x = i => P.l + i * bw, y = v => P.t + (max - v) * (H - P.t - P.b) / ((max - min) || 1);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}">`;
  for (const t of niceTicks(min, max, 5)) s += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--line)"/><text x="${P.l - 6}" y="${y(t) + 4}" text-anchor="end">${Fk(t)}</text>`;
  all.forEach((m, i) => {
    const o = i >= keys.length ? ' opacity=".45"' : '';
    s += `<rect x="${(x(i) + bw * 0.12).toFixed(1)}" y="${y(ein[i]).toFixed(1)}" width="${(bw * 0.76).toFixed(1)}" height="${(y(0) - y(ein[i])).toFixed(1)}" fill="var(--c-ein)" rx="2"${o}/>`;
    s += `<rect x="${(x(i) + bw * 0.12).toFixed(1)}" y="${y(0).toFixed(1)}" width="${(bw * 0.76).toFixed(1)}" height="${(y(aus[i]) - y(0)).toFixed(1)}" fill="var(--c-aus)" rx="2"${o}/>`;
    if (m.endsWith('-01') || (i === 0 && +m.slice(5) <= 10)) s += `<text x="${(x(i) + bw / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle">${ML(m)}</text>`;
  });
  s += `<path d="${op.map((v, i) => (i ? 'L' : 'M') + (x(i) + bw / 2).toFixed(1) + ' ' + y(v).toFixed(1)).join(' ')}" fill="none" stroke="var(--fg)" stroke-width="2"/>`;
  s += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--line-2)"/>`;
  return s + '</svg><div class="chart-legend"><span><i style="background:var(--c-ein)"></i>Einnahmen</span><span><i style="background:var(--c-aus)"></i>Ausgaben</span><span><i style="background:var(--fg)"></i>Operatives Ergebnis</span>' + (pm.length ? '<span class="muted">blass: Plan</span>' : '') + '</div>';
}
function niceTicks(min, max, n) {
  const span = (max - min) || 1, raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p, step = (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
  const out = []; for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(v); return out;
}

// ---------------------------------------------------------------- Übersicht
async function vUebersicht() {
  const D = B();
  let h = '';
  if (!D) return h + (S.einrichtung || !S.DATA ? '<div class="card"><div class="v s">Willkommen bei Kontor</div><div class="d">Die Einrichtung führt dich durch Verbindung, Bereiche, Bilanzpositionen und die optionalen Bausteine.</div><div class="actions"><a href="#einrichtung"><button>Einrichtung öffnen</button></a></div></div>' : noData);
  const nw = D.bilanz.nettovermoegen, m = D.monate, K = D.kennzahlen || {};
  const cur = m[m.length - 1], prev = m[m.length - 2], yago = m[m.length - 13], y = cur.slice(0, 4), ly = String(+y - 1);
  const ytd = m.filter(k => k.startsWith(y)), lytd = m.filter(k => k.startsWith(ly) && +k.slice(5) <= +cur.slice(5)), lyAll = m.filter(k => k.startsWith(ly));
  const proj = D.bilanz.projektion, pm = D.plan_monate || [];
  const delta = (a, b) => a == null || b == null ? '' : `<span class="delta ${a - b >= 0 ? 'pos' : 'neg'}">${a - b >= 0 ? '+' : ''}${F0(a - b)} €</span>`;
  const pct = x => x == null ? '–' : (x * 100).toFixed(0) + ' %';
  const liqRow = D.bilanz.zeilen.filter(r => !r.gruppe && r.rolle === 'liquiditaet'), liq = Object.fromEntries(m.map(k => [k, liqRow.reduce((a, r) => a + (r.werte[k] || 0), 0)]));
  const kpi = (l, v, d, spark) => `<div class="card"><div class="l">${l}</div><div class="v">${v}</div><div class="d">${d || ''}</div>${spark || ''}</div>`;
  const opYtd = sumsOf(D, 'Operativ', ytd), opLytd = sumsOf(D, 'Operativ', lytd), opLy = sumsOf(D, 'Operativ', lyAll);
  const einYtd = sumsOf(D, 'Einnahmen', ytd), einLytd = sumsOf(D, 'Einnahmen', lytd), ausYtd = sumsOf(D, 'Ausgaben', ytd), ausLytd = sumsOf(D, 'Ausgaben', lytd);
  const pend = pm.length ? pm[pm.length - 1] : null;
  h += '<div class="cards">'
    + kpi('Nettovermögen', F0(nw[cur]) + ' €', (prev != null ? 'Monat ' + delta(nw[cur], nw[prev]) : '') + (yago != null ? ' · Jahr ' + delta(nw[cur], nw[yago]) : '') + (pend ? ' · Plan ' + ML(pend) + ': ' + F0(proj.nettovermoegen[pend] * defl(pend)) + ' €' : ''), sparkline(m.slice(-24).map(k => nw[k])))
    + kpi('Liquidität', F0(liq[cur]) + ' €', 'reicht ' + (K.reichweite_monate == null ? '–' : K.reichweite_monate.toFixed(1) + ' Monate') + ' bei Ø Ausgaben inkl. Zinsen' + (pend ? ' · Plan ' + ML(pend) + ': ' + F0(proj.liquiditaet[pend] * defl(pend)) + ' €' : ''), sparkline(m.slice(-24).map(k => liq[k]), 'var(--c-liq)'))
    + kpi('Einnahmen ' + y, F0(einYtd) + ' €', 'Vorjahr gleicher Zeitraum ' + F0(einLytd) + ' € ' + delta(einYtd, einLytd), sparkline(m.slice(-24).map(k => D.kapitalfluss.summen[k]?.Einnahmen ?? 0), 'var(--c-ein)'))
    + kpi('Ausgaben ' + y, F0(ausYtd) + ' €', 'Vorjahr gleicher Zeitraum ' + F0(ausLytd) + ' € ' + delta(ausYtd, ausLytd), sparkline(m.slice(-24).map(k => -(D.kapitalfluss.summen[k]?.Ausgaben ?? 0)), 'var(--c-aus)'))
    + kpi('Operatives Ergebnis ' + y, F0(opYtd) + ' €', 'Vorjahr gleicher Zeitraum ' + F0(opLytd) + ' € ' + delta(opYtd, opLytd) + ' · ' + ly + ' gesamt ' + F0(opLy) + ' €', sparkline(m.slice(-24).map(k => D.kapitalfluss.summen[k]?.Operativ ?? 0), 'var(--c-anl)'))
    + kpi('Sparquote, 12 Monate', pct(K.sparquote), 'operatives Ergebnis ' + F0(K.operativ_12m) + ' € / Einnahmen · Ausgaben Ø ' + F0(K.ausgaben_monat) + ' €/Monat')
    + kpi('Zinslast', F0(K.zinsen_monat) + ' €/Monat', 'Durchschnitt der letzten 12 Monate · ' + F0((K.zinsen_monat || 0) * 12) + ' €/Jahr')
    + '</div>';
  h += `<div class="grid2"><div class="card"><h3>Vermögensstruktur</h3>${chartStack(D)}</div><div class="card"><h3>Einnahmen und Ausgaben je Monat</h3>${chartCashflow(D)}</div></div>`;
  // Jahresvergleich (kumuliert)
  const years = [...new Set([...m, ...(S.plan ? pm : [])].map(k => k.slice(0, 4)))].sort();
  const ycols = years.map(yy => ({key: yy, months: [...m, ...(S.plan ? pm : [])].filter(k => k.startsWith(yy)), plan: !m.some(k => k.startsWith(yy)), mixed: m.some(k => k.startsWith(yy)) && pm.some(k => k.startsWith(yy)), year: true, cur: false}));
  const lab = c => c.key + (c.mixed ? ' Ist+Plan' : c.plan ? ' Plan' : '') + (c.months.length < 12 ? ' · ' + c.months.length + ' Mon.' : '');
  h += `<h2>Jahresvergleich <span class="x">kumulierte Werte · Spalte „${ly} bis ${MONATE[+cur.slice(5) - 1]}“ = Vorjahr gleicher Zeitraum</span></h2><div class="wrap auto"><table><thead><tr><th>Position</th>${ycols.map(c => `<th class="year${c.plan ? ' plan' : ''}">${lab(c)}</th>`).join('')}${lytd.length ? `<th class="year">${ly} bis ${MONATE[+cur.slice(5) - 1]}</th>` : ''}</tr></thead><tbody>`;
  const rowY = (label, fn, total) => `<tr class="${total ? 'total' : ''}"><td>${label}</td>${ycols.map(c => { const v = fn(c.months); return `<td class="${cls(v, c)}">${F0(v)}</td>`; }).join('')}${lytd.length ? `<td class="year ${(fn(lytd) || 0) < 0 ? 'neg' : 'pos'}">${F0(fn(lytd))}</td>` : ''}</tr>`;
  for (const [k, l] of [['Einnahmen', 'Einnahmen'], ['Ausgaben', 'Ausgaben'], ['Zinsen', 'davon Zinsen']]) h += rowY(l, ms => sumsOf(D, k, ms));
  h += rowY('Operatives Ergebnis', ms => sumsOf(D, 'Operativ', ms), true);
  for (const [k, l] of [['Investitionen', 'Investitionen (Umschichtung)'], ['Finanzierung', 'Finanzierung (Tilgung + Zinsen)'], ['Bewertung', 'Bewertung, Wertänderungen']]) h += rowY(l, ms => sumsOf(D, k, ms));
  h += rowY('Nettovermögensänderung', ms => sumsOf(D, 'Nettovermoegen_delta', ms), true);
  h += rowY('Nettovermögen am Jahresende', ms => lastOf(Object.assign({}, nw, proj ? proj.nettovermoegen : {}), ms));
  h += '</tbody></table></div>';
  // Offene Punkte + naechste Monate
  const yr = cur.slice(0, 4);
  const [ok, ob] = await Promise.all([api(`/api/transactions?year=${yr}&uncategorized=1&limit=1&entity=${S.bereich}`), api(`/api/transactions?year=${yr}&without_receipt=1&direction=out&limit=1&entity=${S.bereich}`)]);
  const lastRun = S.STATUS.letzter_lauf, items = [];
  if (lastRun && lastRun.probelauf && lastRun.vorschlaege && lastRun.vorschlaege.length) items.push(['warn', lastRun.vorschlaege.length + ' Buchungsvorschläge warten (Testmodus)', '#buchungen']);
  if (ok.treffer) items.push(['warn', ok.treffer + ' Umsätze ' + yr + ' ohne Kategorie – zuordnen', '#zuordnen']);
  if ((S.DATA.konten_neu || []).length) items.push(['warn', nKonten(S.DATA.konten_neu.length) + ' ohne bestätigte Zuordnung (Bereich, Position)', '#einrichtung/konten']);
  if (ob.treffer) items.push(['neutral', ob.treffer + ' Ausgaben ' + yr + ' ohne Beleg', '#umsaetze?ohne_beleg=1']);
  const ue = (D.kapitalfluss.ueberleitung || {})[cur]; if (ue && Math.abs(ue.unerklaert) > 1) items.push(['warn', 'Unerklärte Vermögensänderung im laufenden Monat: ' + F(ue.unerklaert) + ' € (Prüfzeile)', '#kapitalfluss']);
  for (const w of (D.warnungen || []).slice(0, 6)) items.push(['warn', w, '#buchungen']);
  if (S.STATUS.update && S.STATUS.update.neuer) items.push(['info', 'Update ' + S.STATUS.update.verfuegbar + ' verfügbar', '#updates']);
  let nx = '';
  if (pm.length) {
    const sums = D.kapitalfluss.summen;
    nx = '<table class="plain"><thead><tr><th>Monat</th><th class="num">Operativ</th><th class="num">Zahlungsfluss</th><th class="num">Liquidität</th></tr></thead><tbody>' + pm.slice(0, 6).map(k => `<tr><td>${ML(k)}</td><td class="num ${(sums[k]?.Operativ || 0) < 0 ? 'neg' : 'pos'}">${F0((sums[k]?.Operativ || 0) * defl(k))}</td><td class="num ${(sums[k]?.Cashflow || 0) < 0 ? 'neg' : 'pos'}">${F0((sums[k]?.Cashflow || 0) * defl(k))}</td><td class="num">${F0(proj.liquiditaet[k] * defl(k))}</td></tr>`).join('') + '</tbody></table>';
  }
  h += `<div class="grid2"><div class="card"><h3>Offene Punkte</h3>${items.length ? items.map(([k, t, href]) => `<div style="margin:4px 0"><a href="${href}" class="pill ${k}">${esc(t)}</a></div>`).join('') : '<div class="muted">Nichts offen.</div>'}</div><div class="card"><h3>Nächste Monate (Plan)</h3>${nx || '<div class="muted">Plan unter „Planung“ aktivieren.</div>'}</div></div>`;
  // andere Bereiche
  const others = Object.keys(S.DATA.bereiche).filter(k => k !== S.bereich);
  if (others.length) {
    h += '<h2>Weitere Bereiche</h2><div class="cards">' + others.map(k => { const o = S.DATA.bereiche[k]; if (o.fehler) return `<div class="card"><div class="l">${esc(BN(k))}</div><div class="v s"><span class="pill err">Fehler</span></div><div class="d">${esc(o.fehler)}</div></div>`;
      const om = o.monate, oc = om[om.length - 1], op = om[om.length - 2], onw = o.bilanz.nettovermoegen; const ko = o.kennzahlen || {};
      return `<div class="card clickable" data-b="${k}" style="cursor:pointer"><div class="l">${esc(BN(k))}</div><div class="v s">${F0(onw[oc])} €</div><div class="d">Monat ${delta(onw[oc], onw[op])} · operativ 12 M ${F0(ko.operativ_12m)} €</div>${sparkline(om.slice(-24).map(x => onw[x]), 'var(--c-bet)')}</div>`; }).join('') + '</div>';
  }
  return h;
}

// ---------------------------------------------------------------- Einrichtung (modular)
const MODULES = [
  {id: 'verbindung', t: 'Verbindung', d: 'MoneyMoney läuft und ist entsperrt, macOS erlaubt den Zugriff (Automation). Konten und Kategorien werden gelesen.', done: () => S.KONTEN.length > 0},
  {id: 'bereiche', t: 'Bereiche', d: 'Welche Konten gehören zusammen (Privat, jede Gesellschaft)? Unabhängig von der Gruppierung in MoneyMoney.', done: () => (S.CFG.bereiche || []).length > 0 || !!S.DATA},
  {id: 'konten', t: 'Konten', d: 'Jedes Konto bestätigen: Bereich und Position (Vorschlag aus MoneyMoney), Verlaufsquelle, inaktiv. Neue Konten in MoneyMoney tauchen hier als „neu“ auf. Saldenverlauf importieren.', done: () => !!S.DATA && !((S.DATA.konten_neu || []).length)},
  {id: 'historie', t: 'Kontostände aus MoneyMoney', d: 'Bisherigen Verlauf aller Konten einmalig aus MoneyMoney übernehmen – vor allem für Depots, deren Wertverlauf MoneyMoney sonst nicht herausgibt. Passwort nur im macOS-Fenster, in MoneyMoney wird nichts verändert.', done: () => !!((S.STATUS || {}).moneymoney || {}).historie},
  {id: 'zuordnen', t: 'Kategorien & Zuordnen', d: 'Kontor-eigene Kategorien (Baum aus MoneyMoney übernommen), Regeln aus bisherigen Zuordnungen gelernt, offene Umsätze je Gegenpartei zuordnen. Funktioniert auch ganz ohne Kategorien in MoneyMoney.', done: () => !!S.DATA && !(((S.DATA.kategorien || {}).gesamt || {}).ohne), href: '#zuordnen', optional: true},
  {id: 'kategorien', t: 'Kategorien → Kapitalfluss', d: 'Oberkategorien den Abschnitten zuordnen (Einnahmen, Ausgaben, Investitionen, Finanzierung), Umbuchungen, Depot-Käufe.', done: () => Object.keys((S.CFG.kapitalfluss || {}).kategorie_zuordnung || {}).length > 0, href: '#kategorien', optional: true},
  {id: 'regeln', t: 'Regeln (Gegenbuchungen)', d: 'Darlehen spiegeln und verzinsen, Beteiligungswerte, Saldo-Spiegel – schreibt nur in manuelle Konten.', done: () => (S.CFG.darlehen || []).length + (S.CFG.beteiligungen || []).length + (S.CFG.saldo_spiegel || []).length > 0, href: '#regeln', optional: true},
  {id: 'immobilien', t: 'Immobilien', d: 'Kalkulationen anlegen, mit Konten und Kategorien verknüpfen, Dokumente verlinken, in die Planung übernehmen.', done: () => (S.CFG.immobilien || []).length > 0, href: '#immobilien', optional: true},
  {id: 'planung', t: 'Planung', d: 'Horizont, Inflation, Steigerungen, Darlehensplan, Ereignisse (z. B. Rückzahlungen), Wertentwicklung.', done: () => !!S.DATA, href: '#planung', optional: true},
  {id: 'steuer', t: 'Steuer', d: 'Vermietungskategorie, Darlehen → Objekt, AfA, Kategorie → Steuerposition.', done: () => !!(S.CFG.steuer || {}).vermietung_kategorie, href: '#einstellungen', optional: true},
  {id: 'belege', t: 'Belege & Dokumente', d: 'Belegordner und Ablagemuster; Belege zu Umsätzen, Dateien vom Mac verknüpfen.', done: () => !!(S.CFG.belege || {}).ordner, href: '#einstellungen', optional: true},
  {id: 'betrieb', t: 'Betrieb & Zugang', d: 'Testmodus, automatischer Abgleich, Mitteilungen, Updates, Adresse für das iPhone, Passwort.', done: () => true, href: '#einstellungen'},
];
function vEinrichtung(sub) {
  const sh = id => `<h2 class="sub-h">${esc((MODULES.find(m => m.id === id) || {}).t || '')}</h2>`;      // gleicher Name wie im Einrichtungsplan
  if (sub === 'bereiche') return sh('bereiche') + vBereicheEditor();
  if (sub === 'konten') return sh('konten') + vKontenEditor();
  if (sub === 'verbindung') return sh('verbindung') + vVerbindung();
  if (sub === 'historie') return sh('historie') + vMMHistorie();
  const roots = S.KONTEN.filter(k => k.gruppe && k.ebene === 0);
  let h = `<div class="note">In dieser Reihenfolge einrichten – die ersten Schritte bauen aufeinander auf (Konten lesen → Bereiche → Konten bestätigen → Kontostände aus MoneyMoney), der Rest ist optional und jederzeit nachholbar. ${S.KONTEN.length ? roots.length + ' Kontengruppen, ' + S.KONTEN.filter(k => !k.gruppe).length + ' Konten aus MoneyMoney bekannt.' : 'Noch keine Konten aus MoneyMoney gelesen – mit Schritt 1 beginnen.'}</div><div class="setup-list">`;
  MODULES.forEach((m, i) => {
    const ok = m.done();
    h += `<div class="srow ${ok ? 'done' : ''}"><div class="n">${ok ? '✓' : i + 1}</div><div class="b"><div class="t">${esc(m.t)}<span class="pill ${ok ? 'ok' : (m.optional ? 'neutral' : 'warn')}">${ok ? 'eingerichtet' : (m.optional ? 'optional' : 'offen')}</span></div><div class="d">${esc(m.d)}</div></div><div class="a"><a href="${m.href || ('#einrichtung/' + m.id)}"><button class="small ${ok ? 'secondary' : ''}">${ok ? 'Anpassen' : 'Einrichten'}</button></a></div></div>`;
  });
  h += '</div>';
  if (!S.DATA) h += `<div class="card"><h3>Erste Auswertung erstellen</h3><div class="small muted">Liest alle Umsätze aus MoneyMoney und baut Übersicht, Bilanz, Kapitalfluss, Planung und Steuer. In MoneyMoney wird nichts verändert. Danach hält Kontor die Auswertung selbst aktuell (nach jeder Änderung und bei jedem Abgleich).</div><div class="actions"><button id="w-report" class="small">Auswertung erstellen</button></div></div>`;
  return h;
}
function mmhStep1(st) {
  const off = !(st.moneymoney || {}).laeuft;
  return `<div class="b"><b>MoneyMoney beenden</b><span class="dot ${off ? 'ok' : 'warn'}"></span>${off ? 'MoneyMoney ist beendet.' : 'In MoneyMoney ⌘Q drücken – sonst ist die Datei unvollständig. Diese Anzeige prüft alle paar Sekunden.'}</div>`;
}
function vMMHistorie() {
  const st = S.STATUS, last = (st.moneymoney || {}).historie;
  if (!st.lokal) return '<div class="note">Nur direkt am Mac möglich – dort liegt die Datenbank von MoneyMoney.</div>';
  const n = x => x === 1 ? 'ein Konto' : x + ' Konten';
  return `${last ? `<div class="banner info small">Übernommen am ${esc(fmtZeit(last.zeit))}: ${n(last.konten)}${last.von ? `, ${ML(last.von)} bis ${ML(last.bis)}` : ''}. Erneutes Einlesen ersetzt diese Werte.</div>` : ''}
  <div class="note">Kontor übernimmt einmalig den bisherigen Verlauf aller Konten (Stand am Monatsende) aus der Datenbank von MoneyMoney – vor allem für Depots, deren Wertverlauf MoneyMoney sonst nicht herausgibt. Danach zeichnet Kontor selbst auf. In MoneyMoney wird nichts verändert. ${hq('mmhist')}</div>
  <div class="steps">
    <div class="step ${(st.moneymoney || {}).laeuft ? '' : 'done'}" id="mmh-s1">${mmhStep1(st)}</div>
    <div class="step"><div class="b"><b>Datei im Finder zeigen</b>Kontor öffnet ein Finder-Fenster, in dem „MoneyMoney.sqlite“ markiert ist.<div class="actions"><button id="mmh-zeigen" class="small">Im Finder zeigen</button></div><div class="small muted">Kein Fenster? In MoneyMoney „Hilfe → Datenbank im Finder anzeigen“ wählen und MoneyMoney danach beenden.</div></div></div>
    <div class="step ${last ? 'done' : ''}"><div class="b"><b>Hierher ziehen, Passwort eingeben</b>Danach erscheint ein Fenster von macOS für das MoneyMoney-Passwort.<div class="drop" id="mmh-drop">MoneyMoney.sqlite hierher ziehen<br><button id="mmh-pick" class="small" style="margin-top:8px">Datei wählen</button><input type="file" id="mmh-file" class="hidden"></div><div id="mmh-res" class="findings"></div></div></div>
    <div class="step"><div class="b"><b>Weiter</b><div class="actions"><button data-next="#zuordnen" ${last ? '' : 'class="secondary"'}>Weiter: Kategorien &amp; Zuordnen</button><button class="secondary" data-next="#einrichtung">Zurück zur Einrichtung</button></div></div></div></div>`;
}
const MMH_TXT = {'Datei erhalten': 'Gleich erscheint das Passwortfenster von macOS (beim ersten Mal kann das bis zu einer Minute dauern) …', 'Passwort': 'Bitte im Fenster von macOS das MoneyMoney-Passwort eingeben …', 'Entschlüsseln': 'Wird im Arbeitsspeicher entschlüsselt …', 'Kontostände suchen': 'Kontostände werden gesucht und geprüft …'};
async function mmhFollow() {
  // Fortschritt des Einlesens verfolgen, bis ein Ergebnis da ist
  for (;;) {
    let r; try { r = await api('/api/history/mm-status'); } catch (e) { await new Promise(ok => setTimeout(ok, 1500)); continue; }
    const res = $('#mmh-res');
    if (r.laeuft) { if (res) res.innerHTML = `<div class="working"><span class="spin"></span>${esc(MMH_TXT[r.schritt] || 'Bitte warten …')}</div>`; await new Promise(ok => setTimeout(ok, 800)); continue; }
    const e = r.ergebnis || {};
    if (e.ok) { try { S.STATUS = await api('/api/status'); statusMini(); } catch (x) {} }
    const msg = e.ok ? `Kontostände von ${e.konten === 1 ? 'einem Konto' : e.konten + ' Konten'} übernommen${e.von ? ` (${ML(e.von)} bis ${ML(e.bis)})` : ''}${e.depots ? `, davon ${e.depots === 1 ? 'ein Depot' : e.depots + ' Depots'}` : ''}. Die Auswertung wird neu berechnet.` : (e.text || 'Nicht übernommen.');
    if (S.tab === 'einrichtung' && S.sub === 'historie') { if (e.ok) await route(); const res2 = $('#mmh-res'); if (res2) showFindings(res2, [], msg, e.ok ? 'ok' : 'fehler'); }
    else toast(msg, 8000);
    return;
  }
}
const MMHP = {timer: null};
function mmhPoll() {
  // Auf der Seite "Kontostände aus MoneyMoney": alle 3 s pruefen, ob MoneyMoney beendet ist
  clearTimeout(MMHP.timer);
  if (!(S.tab === 'einrichtung' && S.sub === 'historie')) return;
  MMHP.timer = setTimeout(async () => {
    try { S.STATUS = await api('/api/status?fresh=1'); statusMini(); const el = $('#mmh-s1'); if (el) { el.className = 'step ' + ((S.STATUS.moneymoney || {}).laeuft ? '' : 'done'); el.innerHTML = mmhStep1(S.STATUS); } } catch (e) {}
    mmhPoll();
  }, 3000);
}
function mmStepDone(st) { return st.moneymoney.laeuft && st.moneymoney.gesperrt !== true; }
function mmStepInner(st) {
  const m = st.moneymoney;
  const txt = !m.laeuft ? 'MoneyMoney starten und entsperren – Kontor startet es nicht selbst. Diese Anzeige prüft alle paar Sekunden.'
    : m.gesperrt === true ? 'MoneyMoney läuft, ist aber gesperrt – bitte in MoneyMoney entsperren.' : 'MoneyMoney läuft und ist entsperrt.';
  return `<div class="b"><b>MoneyMoney läuft</b><span class="dot ${!m.laeuft ? 'off' : m.gesperrt === true ? 'warn' : 'ok'}"></span>${txt}</div>`;
}
const VB = {timer: null};
function vbPoll() {
  // Auf der Seite "Verbindung" alle 3 s pruefen, ob MoneyMoney laeuft und entsperrt ist
  clearTimeout(VB.timer);
  if (!(S.tab === 'einrichtung' && S.sub === 'verbindung')) return;
  VB.timer = setTimeout(async () => {
    try { S.STATUS = await api('/api/status?fresh=1'); statusMini(); const el = $('#vb-mm'); if (el) { el.className = 'step ' + (mmStepDone(S.STATUS) ? 'done' : ''); el.innerHTML = mmStepInner(S.STATUS); } } catch (e) {}
    vbPoll();
  }, 3000);
}
function vVerbindung() {
  const st = S.STATUS;
  return `<div class="steps">
    <div class="step ${mmStepDone(st) ? 'done' : ''}" id="vb-mm">${mmStepInner(st)}</div>
    <div class="step ${S.KONTEN.length ? 'done' : ''}"><div class="b"><b>Zugriff erlauben und Konten lesen ${hq('berechtigung')}</b>macOS fragt einmal, ob „python3“ MoneyMoney steuern darf – erlauben.<div class="actions"><button id="w-check" class="small">Verbindung prüfen</button><span id="w-busy" class="working hidden"><span class="spin"></span>Lese Konten und Umsätze aus MoneyMoney … bei vielen Umsätzen bis zu einer Minute.</span></div><div id="w-findings" class="findings"></div></div></div>
    <div class="step ${S.KONTEN.length ? 'done' : ''}"><div class="b"><b>Weiter</b><div class="actions"><button data-next="#einrichtung/bereiche" ${S.KONTEN.length ? '' : 'class="secondary"'}>Weiter: Bereiche</button><button class="secondary" data-next="#einrichtung">Zurück zur Einrichtung</button></div></div></div></div>`;
}
const FIRMA_RE = /\b(gmbh|ug|ag|se|kg|ohg|gbr|egbr|e\.?\s?k\.?|e\.?\s?v\.?|eg|ltd|inc|llc|holding|verwaltung|beteiligung|immobilien|stiftung|verein|genossenschaft|partner|&\s?co)\b/i;
const guessArt = name => FIRMA_RE.test(name || '') || /(gmbh|gbr|holding)/i.test(name || '') ? 'gesellschaft' : 'privat';
function anteilAusRegel(konten) {
  // Beteiligungsregel, deren Gruppe zu diesem Bereich gehoert -> Anteil als Vorschlag
  const ids = new Set((konten || []).map(r => r.split('|')[0].trim()));
  const b = (S.CFG.beteiligungen || []).find(x => ids.has((x.gruppe || '').split('|')[0].trim()));
  return b && b.anteil != null ? b.anteil : null;
}
function vBereicheEditor() {
  const roots = S.KONTEN.filter(k => k.gruppe && k.ebene === 0);
  let list = (S.CFG.bereiche || []).length ? S.CFG.bereiche : roots.map(r => ({id: r.uuid, name: r.name, konten: [r.uuid + ' | ' + r.name], haupt: false, art: guessArt(r.name), anteil: null}));
  if (list.length && !list.some(b => b.haupt)) { const p = list.find(b => (b.art || guessArt(b.name)) === 'privat') || list[0]; p.haupt = true; }
  if (!(S.CFG.bereiche || []).length) list = list.map((b, i) => [b, i]).sort((x, y) => (!x[0].haupt - !y[0].haupt) || (((x[0].art || guessArt(x[0].name)) !== 'privat') - ((y[0].art || guessArt(y[0].name)) !== 'privat')) || x[1] - y[1]).map(x => x[0]);
  let h = `<div class="note">Standard: jede Kontengruppe der obersten Ebene ist ein Bereich – der Hauptbereich zuerst, dann weitere private, dann Gesellschaften. Art und Hauptbereich sind aus den Namen vorbelegt – prüfen und bei Bedarf ändern. Mit ▲ ▼ die Reihenfolge ändern: so erscheinen die Bereiche oben in der Leiste. Bereiche lassen sich umbenennen, löschen, zusammenlegen oder aus einzelnen Konten und Gruppen zusammenstellen. ${hq('bereich')} ${S.KONTEN.length ? '' : '<b>Noch keine Konten geladen – zuerst die Verbindung prüfen.</b>'}</div><div class="list" id="bereiche">`;
  list.forEach((b, i) => { h += bereichForm(b, i); });
  h += '</div><div class="actions"><button id="add-bereich" class="secondary">Bereich hinzufügen</button><button id="save-bereiche" class="secondary">Speichern</button><button data-savenext="#einrichtung/konten" data-save="bereiche">Speichern und weiter: Konten</button><button class="secondary" data-next="#einrichtung">Zurück zur Einrichtung</button></div><div id="findings-b" class="findings"></div>';
  return h;
}
function bereichForm(b, i) {
  const sel = new Set((b.konten || []).map(r => r.split('|')[0].trim()));
  const art = b.art || guessArt(b.name);
  const regel = anteilAusRegel(b.konten);
  const pct = b.anteil != null && b.anteil !== '' ? Math.round(parseFloat(b.anteil) * 10000) / 100 : '';
  // Konten unter einer gewaehlten Gruppe sind enthalten (angehakt, gesperrt)
  const rows = []; let within = null;
  for (const k of S.KONTEN) {
    if (within !== null && k.ebene <= within) within = null;
    const implied = within !== null;
    const checked = sel.has(k.uuid) || implied;
    if (k.gruppe && sel.has(k.uuid) && within === null) within = k.ebene;
    rows.push(`<label class="chk small ${implied ? 'implied' : ''}" style="padding-left:${k.ebene * 14}px"><input type="checkbox" class="b-k" data-ebene="${k.ebene}" data-gruppe="${k.gruppe ? 1 : 0}" value="${k.uuid} | ${esc(k.name)}" ${checked ? 'checked' : ''} ${implied ? 'disabled' : ''}> ${esc(k.name)}${k.gruppe ? ' <span class="muted">(Gruppe – mit allen Konten darunter)</span>' : ''}</label>`);
  }
  return `<div class="item" data-i="${i}"><div class="grow"><div class="form">
    <label>Name</label><input type="text" class="b-name" value="${esc(b.name || '')}">
    <input type="hidden" class="b-id" value="${esc(b.id || '')}">
    <label>Art</label><select class="b-art"><option value="privat" ${art === 'privat' ? 'selected' : ''}>privat</option><option value="gesellschaft" ${art === 'gesellschaft' ? 'selected' : ''}>Gesellschaft (GbR, GmbH …)</option></select>
    <label>Hauptbereich ${hq('haupt')}</label><label class="chk"><input type="radio" name="b-haupt" class="b-haupt" ${b.haupt ? 'checked' : ''}> ${b.haupt ? 'ja' : 'nein'}</label>
    <label class="b-anteil-row ${art === 'privat' ? 'hidden' : ''}">Anteil ${hq('anteil')}</label><div class="row tight b-anteil-row ${art === 'privat' ? 'hidden' : ''}"><input type="number" step="0.01" min="0" max="100" class="b-anteil" value="${pct}" placeholder="${regel != null ? Math.round(regel * 10000) / 100 : '100'}" style="width:110px"> %${regel != null && pct === '' ? `<span class="small muted">Vorschlag aus der Beteiligungsregel: ${Math.round(regel * 10000) / 100} %</span>` : ''}</div>
    <label>Konten / Gruppen ${hq('gruppenwahl')}</label><div class="list b-konten" style="max-height:240px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:6px 10px">${rows.join('')}</div>
  </div></div><div class="b-side"><div class="b-mvs"><button class="secondary small b-mv" data-d="-1" title="nach oben">▲</button><button class="secondary small b-mv" data-d="1" title="nach unten">▼</button></div><button class="danger small del">Entfernen</button></div></div>`;
}
function bereichMvState() { const its = $$('#bereiche .item'); its.forEach((it, i) => { const [up, dn] = $$('.b-mv', it); if (up) up.disabled = i === 0; if (dn) dn.disabled = i === its.length - 1; }); }
function bindBereichKonten(main) {
  // Gruppe anhaken -> alle Konten darunter enthalten (gesperrt); Konto darunter abwaehlen -> Gruppe wird abgewaehlt, die uebrigen bleiben einzeln gewaehlt
  $$('.b-konten', main).forEach(box => box.addEventListener('change', e => {
    const cb = e.target; if (!cb.classList.contains('b-k')) return;
    const all = $$('.b-k', box), idx = all.indexOf(cb), lvl = +cb.dataset.ebene;
    const below = []; for (let j = idx + 1; j < all.length && +all[j].dataset.ebene > lvl; j++) below.push(all[j]);
    if (cb.dataset.gruppe === '1') {
      below.forEach(c => { c.checked = cb.checked; c.disabled = cb.checked; c.closest('label').classList.toggle('implied', cb.checked); });
    } else if (!cb.checked) {
      // uebergeordnete, angehakte Gruppen aufloesen: die uebrigen Konten darunter bleiben einzeln gewaehlt
      let cur = lvl;
      for (let j = idx - 1; j >= 0; j--) {
        const g = all[j]; if (+g.dataset.ebene >= cur) continue;
        cur = +g.dataset.ebene;
        if (g.dataset.gruppe === '1' && g.checked) { g.checked = false; for (let m = j + 1; m < all.length && +all[m].dataset.ebene > cur; m++) { all[m].disabled = false; all[m].closest('label').classList.remove('implied'); } }
      }
      cb.checked = false;
    }
  }));
  $$('.b-haupt', main).forEach(r => r.addEventListener('change', () => $$('.b-haupt', main).forEach(x => { x.parentElement.lastChild.textContent = x.checked ? ' ja' : ' nein'; })));
  const anteilSichtbar = it => $$('.b-anteil-row', it).forEach(x => x.classList.toggle('hidden', $('.b-art', it).value === 'privat'));
  $$('.b-name', main).forEach(inp => inp.addEventListener('input', () => { const it = inp.closest('.item'), sel = $('.b-art', it); if (sel && !sel.dataset.touched) { sel.value = guessArt(inp.value); anteilSichtbar(it); } }));
  $$('.b-art', main).forEach(sel => sel.addEventListener('change', () => { sel.dataset.touched = '1'; anteilSichtbar(sel.closest('.item')); }));
}
function collectBereiche() {
  const cfg = JSON.parse(JSON.stringify(S.CFG));
  cfg.bereiche = $$('#bereiche .item').map(it => ({ id: $('.b-id', it).value.trim() || ('b-' + Math.random().toString(36).slice(2, 10)), name: $('.b-name', it).value.trim(),
    art: $('.b-art', it).value || guessArt($('.b-name', it).value), haupt: $('.b-haupt', it).checked,
    anteil: $('.b-art', it).value === 'privat' || $('.b-anteil', it).value === '' ? null : Math.round(parseFloat($('.b-anteil', it).value) * 100) / 10000, aktiv: true,
    konten: $$('.b-k:checked', it).filter(c => !c.disabled).map(c => c.value) }));
  if (cfg.bereiche.length && !cfg.bereiche.some(b => b.haupt)) cfg.bereiche[0].haupt = true;
  if (cfg.bilanz) delete cfg.bilanz.hauptbereich;
  return cfg;
}
function vKontenEditor() {
  const leaves = S.KONTEN.filter(k => !k.gruppe);
  const cfg = S.CFG, rollen = cfg.bilanz.rollen || {}, verlauf = cfg.bilanz.verlauf || {}, ill = new Set((cfg.bilanz.illiquide_konten || []).map(r => r.split('|')[0].trim())), hide = new Set((cfg.bilanz.ausgeblendet || []).map(r => r.split('|')[0].trim())), show = new Set((cfg.bilanz.immer_anzeigen || []).map(r => r.split('|')[0].trim()));
  const roleOf = u => { const k = Object.keys(rollen).find(x => x.split('|')[0].trim() === u); return k ? rollen[k] : ''; };
  const verOf = u => { const k = Object.keys(verlauf).find(x => x.split('|')[0].trim() === u); return k ? verlauf[k] : ''; };
  const bereichOf = u => { const k = S.KONTEN.find(x => x.uuid === u); if (k && k.bereich) return k.bereich; for (const b of (S.CFG.bereiche || [])) if ((b.konten || []).some(r => { const id = r.split('|')[0].trim(); const g = S.KONTEN.find(x => x.uuid === id); return id === u || (g && g.gruppe && leaves.find(l => l.uuid === u && l.pfad.startsWith(g.pfad + ' / '))); })) return b.name; return ''; };
  const bereiche = (S.CFG.bereiche || []).length ? S.CFG.bereiche.map(b => [b.id, b.name]) : Object.entries((S.DATA && S.DATA.bereich_namen) || {});
  const neu = leaves.filter(k => !k.bestaetigt);
  let h = `<div class="note">Jedes Konto gehört zu einem Bereich und hat eine Position. Vorschläge kommen aus der Gruppierung in MoneyMoney, dem Gruppennamen und dem Kontotyp und sind in der Auswahl mit „(Vorschlag)“ gekennzeichnet – hier bestätigst oder änderst du sie. Neue Konten tauchen als „neu“ auf (gestrichelt = Vorschlag noch nicht bestätigt), bis du sie einmal gespeichert hast. Reihenfolge wie unter „Bereiche“, darin wie in MoneyMoney. ${hq('konten_zuordnung')}</div>
  ${neu.length ? `<div class="banner info">${nKonten(neu.length)} noch nicht bestätigt: ${esc(neu.slice(0, 6).map(k => k.name).join(', '))}${neu.length > 6 ? ' …' : ''} – Vorschläge prüfen und „Speichern“.</div>` : ''}
  <div class="row tight"><label>„Nach Aktivität“: ausblenden ohne Bestand und Umsatz seit <input type="number" id="k-inaktiv" min="0" value="${cfg.bilanz.inaktiv_monate ?? 12}" style="width:70px"> Monaten ${hq('inaktiv')}</label><label class="switch"><input type="checkbox" id="k-show-inactive" checked><i></i>ausgeblendete hier zeigen</label></div>
  <div class="wrap auto"><table class="plain acct-table"><thead><tr><th>Konto</th><th>Bereich ${hq('bereich')}</th><th>Position ${hq('position_kurz')}</th><th>Verlauf ${hq('verlauf_kurz')}</th><th>Anzeige ${hq('anzeige')}</th><th class="num">Saldo</th></tr></thead><tbody>`;
  // Reihenfolge: Bereiche wie unter „Bereiche“ angeordnet, darin die Konten wie in MoneyMoney; ohne Bereich zum Schluss
  const zuOf = k => ((cfg.bilanz.konten_zuordnung || {})[k.uuid + ' | ' + k.name]) || Object.entries(cfg.bilanz.konten_zuordnung || {}).find(([r]) => r.split('|')[0].trim() === k.uuid)?.[1] || {};
  const bIdx = Object.fromEntries(bereiche.map(([id], i) => [id, i]));
  const rows = leaves.map((k, i) => ({k, i, bsel: zuOf(k).bereich || k.bereich_id || ''})).sort((a, b) => ((bIdx[a.bsel] ?? 1e6) - (bIdx[b.bsel] ?? 1e6)) || a.i - b.i);
  let lastB = null;
  for (const {k, bsel} of rows) {
    if (bsel !== lastB) { lastB = bsel; h += `<tr class="bgroup"><td colspan="6">${esc((bereiche.find(([id]) => id === bsel) || [null, 'ohne Bereich'])[1])}</td></tr>`; }
    const cur = roleOf(k.uuid), ver = verOf(k.uuid);
    const vis = hide.has(k.uuid) ? 'hide' : show.has(k.uuid) ? 'show' : '', grenze = k.aktiv_grenze ?? (k.inaktiv_auto ? 9999 : 0), auto = autoHidden(grenze, cfg.bilanz.inaktiv_monate ?? 12);
    const rolle = cur || k.rolle || 'sonstiges', quelle = ver || k.verlauf || (k.depot ? 'stand' : 'umsaetze');
    // Vorschlag (was Kontor aus Name, Typ und Gruppe erkennt) steht in der Liste mit „(Vorschlag)“; gestrichelt, solange ein neues Konto ihn noch trägt
    const sv = k.rolle_vorschlag || rolle, vv = k.depot ? 'stand' : 'umsaetze';
    const dash = (cur, v) => !k.bestaetigt && cur === v ? ' vorschlag' : '';
    h += `<tr data-uuid="${k.uuid}" data-ref="${k.uuid} | ${esc(k.name)}" data-auto="${auto ? 1 : 0}" data-grenze="${grenze}" class="${kontoHidden(vis, auto) ? 'inactive' : ''}${k.bestaetigt ? '' : ' neu'}"><td title="${esc(k.pfad)}">${esc(k.name)}${k.bestaetigt ? '' : '<span class="tag warn">neu</span>'}<span class="tag k-vis">ausgeblendet</span>${k.veraltet ? `<span class="tag warn" title="Saldo ${F(k.saldo)}, aber seit ${esc(k.letzte_buchung || k.aktualisiert || 'jeher')} weder Buchung noch Aktualisierung – Konto aufgelöst? Dann in MoneyMoney den Saldo auf 0 setzen (Verlauf bleibt) oder „nicht bilanzieren“.">veraltet?</span>` : ''}<div class="small muted">${esc(k.pfad.split(' / ').slice(0, -1).join(' / '))} · ${k.depot ? 'Depot' : (k.manuell || k.abruf === 'offline') ? 'manuell' : esc(k.typ || 'Bank')}</div></td><td><select class="k-bereich"><option value="">– keiner –</option>${bereiche.map(([id, n]) => `<option value="${esc(id)}" ${bsel === id ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></td>
      <td><select class="k-rolle${dash(rolle, sv)}" data-vor="${sv}">${ROLE_OPTS.map(([v, l]) => `<option value="${v}" ${rolle === v ? 'selected' : ''}>${l}${v === sv ? ' (Vorschlag)' : ''}</option>`).join('')}</select>${vorHint(rolle, sv, ROLE_OPTS)}</td>
      <td class="nowrap"><select class="k-verlauf${dash(quelle, vv)}" data-vor="${vv}">${[['umsaetze', 'Umsätze'], ['stand', 'Kontostände']].map(([v, l]) => `<option value="${v}" ${quelle === v ? 'selected' : ''}>${l}${v === vv ? ' (Vorschlag)' : ''}</option>`).join('')}</select> <button class="ghost small k-hist" title="Monatsstände ansehen und bearbeiten">Verlauf…</button>${vorHint(quelle, vv, [['umsaetze', 'Umsätze'], ['stand', 'Kontostände']])}</td>
      <td><select class="k-show" title="${auto ? 'Kein Bestand und kein Umsatz seit ' + (cfg.bilanz.inaktiv_monate ?? 12) + ' Monaten' : 'Mit Bestand oder Umsatz in den letzten ' + (cfg.bilanz.inaktiv_monate ?? 12) + ' Monaten'}"><option value="">nach Aktivität</option><option value="show" ${vis === 'show' ? 'selected' : ''}>immer anzeigen</option><option value="hide" ${vis === 'hide' ? 'selected' : ''}>ausblenden</option></select></td>
      <td class="num ${(k.saldo || 0) < 0 ? 'neg' : 'pos'}">${F(k.saldo)}</td></tr>`;
  }
  h += '</tbody></table></div><div class="actions"><button id="save-konten" class="secondary">Speichern</button><button data-savenext="#einrichtung/historie" data-save="konten">Speichern und weiter: Kontostände aus MoneyMoney</button><button class="secondary" data-next="#einrichtung">Zurück zur Einrichtung</button></div><div id="findings-k2" class="findings"></div>';
  h += `<h2>Saldenverlauf importieren ${hq('verlauf_import')}</h2><div class="note">Für Depots und Konten ohne Umsatzhistorie: Monatsstände aus einer Datei übernehmen. Erkannt werden CSV und Excel (.xlsx) – als Liste (Datum, Konto, Saldo), als Tabelle mit Stichtagen in der Kopfzeile (Konten als Zeilen, z. B. eine eigene Vermögensübersicht) oder mit Stichtagen in der ersten Spalte (Konten als Spalten). Je Monat zählt der letzte Wert. Umsatzkonten brauchen das nicht.</div>
    <div class="drop" id="hi-drop">Datei hierher ziehen<br><button id="hi-pick" class="small" style="margin-top:8px">Datei wählen</button></div><div id="hi-preview"></div>`;
  return h;
}
let HI = null;   // {name, b64, vorschau}
async function histImportPreview(file) {
  const b64 = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1] || ''); r.onerror = rej; r.readAsDataURL(file); });
  HI = {name: file.name, b64};
  try { const r = await api('/api/history/import', {datei: b64, name: file.name}); HI.vorschau = r.vorschau; HI.hinweise = r.hinweise || []; } catch (e) { HI = null; $('#hi-preview').innerHTML = `<div class="findings"><div class="fehler">${esc(e.message)}</div></div>`; return; }
  renderHistImport();
}
function renderHistImport() {
  const el = $('#hi-preview'); if (!el || !HI) return;
  const leaves = S.KONTEN.filter(k => !k.gruppe);
  const opts = sel => '<option value="">– nicht übernehmen –</option>' + leaves.map(k => `<option value="${k.uuid} | ${esc(k.name)}" ${sel === k.uuid ? 'selected' : ''}>${esc(k.name)}${k.depot ? ' · Depot' : ''}${k.verlauf === 'stand' ? ' · Kontostände' : ''}</option>`).join('');
  el.innerHTML = `<div class="card" style="margin-top:12px"><h3>${esc(HI.name)} <span class="muted">· ${HI.vorschau.length} Spalten/Konten erkannt${HI.hinweise.length ? ' · ' + esc(HI.hinweise.join(' ')) : ''}</span></h3>
    <div class="wrap auto"><table class="plain"><thead><tr><th>In der Datei</th><th class="num">Monate</th><th>Zeitraum</th><th>Konto in Kontor</th></tr></thead><tbody>${HI.vorschau.map(v => `<tr data-name="${esc(v.name)}"><td>${esc(v.name)}</td><td class="num">${v.anzahl}</td><td class="small">${v.von} – ${v.bis}</td><td><select class="hi-map">${opts(v.uuid)}</select>${v.uuid && !v.sicher ? ' <span class="tag" title="automatisch zugeordnet – prüfen">Vorschlag</span>' : ''}</td></tr>`).join('')}</tbody></table></div>
    <div class="row tight" style="margin-top:8px"><label class="chk"><input type="checkbox" id="hi-gaps" checked> nur Monate übernehmen, für die noch kein eigener Wert eingetragen ist</label><button id="hi-import" class="small">Übernehmen</button><span class="small muted">Ohne Zuordnung bleibt eine Zeile unberücksichtigt. Werte zählen als eigene Monatsstände (Verlaufsquelle „Kontostände“ für Depots; bei Umsatzkonten überschreiben sie nur den Monat, nicht die Rückrechnung).</span></div><div id="hi-report" class="findings"></div></div>`;
  $('#hi-import').onclick = async () => {
    const zuordnung = {}; $$('#hi-preview tr[data-name]').forEach(tr => { zuordnung[tr.dataset.name === '(ohne Konto)' ? '' : tr.dataset.name] = $('.hi-map', tr).value; });
    try { const r = await api('/api/history/import', {datei: HI.b64, name: HI.name, zuordnung, uebernehmen: true, nur_luecken: $('#hi-gaps').checked}); showFindings($('#hi-report'), [], r.uebernommen + ' Monatswerte für ' + (r.konten === 1 ? 'ein Konto' : r.konten + ' Konten') + ' übernommen' + (r.bericht ? '; Bericht aktualisiert.' : '.'), 'ok'); await loadAll(); } catch (e) { showFindings($('#hi-report'), [], e.message, 'fehler'); }
  };
}
function kontoHidden(vis, auto) { return vis === 'hide' || (vis === '' && !!auto); }
function autoHidden(grenze, n) { n = +n || 0; return n > 0 && n <= (+grenze || 0); }      // "nach Aktivität": ohne Bestand und Umsatz seit N Monaten
function vorHint(val, vor, opts) {
  // Abweichung vom Vorschlag bleibt auch nach dem Speichern sichtbar
  const l = (opts.find(o => o[0] === vor) || [vor, vor])[1].replace(/ – nicht im Nettovermögen$/, '');
  return `<div class="vor-hint small muted${val === vor ? ' hidden' : ''}">Vorschlag: ${esc(l)}</div>`;
}
function collectKonten() {
  const cfg = JSON.parse(JSON.stringify(S.CFG)); const b = cfg.bilanz = cfg.bilanz || {};
  b.rollen = {}; b.verlauf = {}; b.illiquide_konten = []; b.ausgeblendet = []; b.immer_anzeigen = []; b.konten_zuordnung = b.konten_zuordnung || {};
  $$('tr[data-uuid]').forEach(tr => { const ref = tr.dataset.ref;
    // Position und Verlauf werden fest gespeichert: spätere Änderungen an Name, Typ oder Gruppe in MoneyMoney verschieben nichts
    b.konten_zuordnung[ref] = {bereich: $('.k-bereich', tr).value, position: $('.k-rolle', tr).value, bestaetigt: true};
    b.rollen[ref] = $('.k-rolle', tr).value;
    b.verlauf[ref] = $('.k-verlauf', tr).value;
    if ($('.k-show', tr).value === 'hide') b.ausgeblendet.push(ref); if ($('.k-show', tr).value === 'show') b.immer_anzeigen.push(ref); });
  b.inaktiv_monate = Math.max(0, parseInt($('#k-inaktiv').value) || 0);
  return cfg;
}
// Verlauf (Monatsstaende) je Konto
async function openHistDrawer(uuid, vorschau) {
  // vorschau: Verlaufsquelle, die erst angezeigt und mit „Speichern“ übernommen wird (z. B. aus der Kontentabelle)
  const r = await api('/api/history?account=' + encodeURIComponent(uuid) + (vorschau ? '&source=' + vorschau : ''));
  const k = S.KONTEN.find(x => x.uuid === uuid) || {name: r.name || uuid};
  const d = $('#drawer');
  HD.uuid = uuid; HD.live = r.live;
  d.innerHTML = `<button class="close icon">✕</button><h2>${esc(k.name || r.name)}</h2>
    <div class="row tight"><span class="small muted">Verlauf aus ${hq('verlauf')}</span><div class="seg" id="hq-seg"><button class="hq-q" data-q="umsaetze">Umsätze</button><button class="hq-q" data-q="stand">Kontoständen</button></div></div>
    <div class="small muted" id="hq-erkl" style="margin:4px 0 8px"></div>
    <div id="hq-hinweis"></div><div id="hq-pending"></div>
    <h3>Monatsstände</h3>
    <div class="row tight" id="h-addrow"><input type="month" id="h-von" style="width:140px"><button id="h-add" class="small secondary">Monat davor ergänzen</button></div>
    <div class="hist-grid" id="h-grid"></div>
    <div class="actions" id="h-actions"><button id="h-save" class="small">Speichern</button><button id="h-undo" class="small secondary hidden">Verwerfen</button><button id="h-clear" class="small secondary">Alle eigenen Werte löschen</button></div>
    <div id="h-importbox"><h3>Import aus Saldenexport</h3><div class="small muted">CSV mit Datum;Saldo (ein Konto) oder Datum;Konto;Saldo (z. B. Werte aus Depot- oder Jahresauszügen). Es zählt der letzte Wert je Monat; das Konto wird dabei auf „Kontostände“ umgestellt.</div>
    <textarea id="h-csv" placeholder="Datum;Saldo\n31.12.2024;12.345,67\n31.01.2025;12.900,00"></textarea><div class="actions"><button id="h-import" class="small secondary">Vorschau</button><button id="h-import2" class="small hidden">Übernehmen</button></div><div id="h-prev" class="findings"></div></div>`;
  d.classList.add('open');
  renderHist(r);
  $('.close', d).onclick = closeDrawer;
  // Quelle umstellen = nur Vorschau (die Liste zeigt, was sich ändern würde); übernommen wird mit „Speichern“
  $$('.hq-q', d).forEach(b => b.onclick = async () => {
    if (b.classList.contains('on')) return;
    $$('.hq-q', d).forEach(x => { x.classList.toggle('on', x === b); x.disabled = true; });
    try { renderHist(await api('/api/history?account=' + encodeURIComponent(uuid) + '&source=' + b.dataset.q)); }
    catch (e) { toast(e.message, 6000); renderHist(HD.r); }
    finally { $$('.hq-q', d).forEach(x => { x.disabled = false; }); }
  });
  $('#h-undo', d).onclick = async () => { try { renderHist(await api('/api/history?account=' + encodeURIComponent(uuid) + '&source=' + HD.r.quelle_gespeichert)); } catch (e) { toast(e.message, 6000); } };
  $('#h-add', d).onclick = () => { const v = $('#h-von', d).value; if (!v) return; let [yy, mm] = v.split('-').map(Number); mm--; if (mm < 1) { mm = 12; yy--; } const mk = `${yy}-${String(mm).padStart(2, '0')}`; $('#h-von', d).value = mk; $('#h-grid', d).insertAdjacentHTML('afterbegin', `<label>${ML(mk)}<input type="text" data-mk="${mk}" class="auto" value=""></label>`); };
  $('#h-save', d).onclick = async () => {
    const werte = {}; if (HD.r.quelle === 'stand') $$('#h-grid input', d).forEach(i => { if (!i.classList.contains('auto') || i.value.trim()) werte[i.dataset.mk] = i.value.trim() === '' ? null : i.value.trim(); });
    const body = {konto: uuid, werte}; if (HD.r.quelle !== HD.r.quelle_gespeichert) body.quelle = HD.r.quelle;
    try {
      const res = await api('/api/history', body); renderHist(res.historie); toast('Gespeichert');
      if (body.quelle) { S.CFG = await api('/api/config'); const sel = $(`tr[data-uuid="${uuid}"] .k-verlauf`); if (sel) { sel.value = body.quelle; sel.classList.toggle('vorschlag', sel.closest('tr').classList.contains('neu') && sel.value === sel.dataset.vor); const hn = sel.parentElement.querySelector('.vor-hint'); if (hn) hn.classList.toggle('hidden', sel.value === sel.dataset.vor); } }
    } catch (e) { toast(e.message, 6000); }
  };
  $('#h-clear', d).onclick = async () => { if (!confirm('Alle eigenen Monatswerte dieses Kontos löschen?')) return; try { const res = await api('/api/history', {konto: uuid, werte: {}, loeschen: true}); renderHist(res.historie); } catch (e) { toast(e.message, 6000); } };
  $('#h-import', d).onclick = async () => { try { const r2 = await api('/api/history/import', {konto: uuid, csv: $('#h-csv', d).value}); $('#h-prev', d).innerHTML = r2.vorschau.map(v => `<div class="${v.uuid ? 'ok' : 'warnung'}">${esc(v.name)}: ${v.anzahl} Monate (${v.von} – ${v.bis})${v.uuid ? '' : ' – kein Konto zugeordnet'}</div>`).join(''); $('#h-import2', d).classList.remove('hidden'); } catch (e) { $('#h-prev', d).innerHTML = `<div class="fehler">${esc(e.message)}</div>`; } };
  $('#h-import2', d).onclick = async () => { try { const r2 = await api('/api/history/import', {konto: uuid, csv: $('#h-csv', d).value, uebernehmen: true}); toast(r2.uebernommen + ' Werte übernommen'); S.CFG = await api('/api/config'); const sel = $(`tr[data-uuid="${uuid}"] .k-verlauf`); if (sel) sel.value = 'stand'; await openHistDrawer(uuid); } catch (e) { toast(e.message, 6000); } };
}
function renderHist(r) {
  // Fensterinhalt aus der Vorschau des Dienstes (fuer dieses eine Konto sofort gerechnet)
  const d = $('#drawer'); if (!d.classList.contains('open')) return;
  HD.r = r; HD.live = r.live;
  const stand = r.quelle === 'stand';
  $$('.hq-q', d).forEach(x => x.classList.toggle('on', x.dataset.q === r.quelle));
  $('#hq-erkl', d).textContent = stand
    ? (r.depot ? 'Letzter bekannter Kontostand gilt (Depots haben keine Buchungen). Bekannt sind die aus MoneyMoney übernommenen Stände und Kontors monatliche Aufzeichnung; Fehlendes hier eintragen.'
               : 'Eingetragene Kontostände sind maßgeblich; die Monate dazwischen und davor rechnet Kontor von dort aus mit den Buchungen. Ohne eigene Werte = wie „Umsätze“.')
    : 'Saldo am Monatsende = heutiger Saldo minus alle späteren Buchungen. Eigene Monatswerte gelten nur bei „Kontoständen“.';
  const P = r.pruefung || {}, infos = [];
  if (r.hinweis) infos.push(r.hinweis.replace(/^'[^']*': /, ''));
  if (!stand && P.erste_buchung && Math.abs(P.anfangssaldo || 0) > 0.005) infos.push(`MoneyMoney hat Umsätze erst ab ${P.erste_buchung.slice(8, 10)}.${P.erste_buchung.slice(5, 7)}.${P.erste_buchung.slice(0, 4)}; davor gilt der Anfangssaldo ${F(P.anfangssaldo)} €. War der Stand davor anders: auf „Kontostände“ stellen und bekannte Stände eintragen.`);
  if (!stand && !P.buchungen && !r.depot) infos.push('Keine Umsätze in MoneyMoney – der Verlauf ist konstant der heutige Saldo. Für einen echten Verlauf auf „Kontostände“ stellen.');
  if (P.vorgemerkt_anzahl) infos.push(`${P.vorgemerkt_anzahl} vorgemerkte Umsätze (zusammen ${F(P.vorgemerkt_summe)} €) sind nicht eingerechnet – wie im Kontostand von MoneyMoney.`);
  if (!r.live) infos.push('Noch kein MoneyMoney-Stand im Speicher – angezeigt werden die Werte der letzten Auswertung.');
  $('#hq-hinweis', d).innerHTML = infos.map(t => `<div class="banner info small">${esc(t)}</div>`).join('');
  const pending = r.quelle_gespeichert && r.quelle !== r.quelle_gespeichert;
  $('#hq-pending', d).innerHTML = pending ? `<div class="banner small">Vorschau: Verlauf aus ${r.quelle === 'stand' ? 'Kontoständen' : 'Umsätzen'} – gespeichert ist „${r.quelle_gespeichert === 'stand' ? 'Kontostände' : 'Umsätze'}“. „Speichern“ übernimmt die Umstellung.</div>` : '';
  const werte = r.werte || {}, man = r.manuell || {};
  const months = Object.keys(Object.assign({}, werte, man)).sort();
  const anker = new Set(r.anker || []);
  $('#h-grid', d).innerHTML = months.map(mk => {
    const own = man[mk] != null;
    const val = werte[mk] != null ? F(werte[mk]) : '';
    if (!stand) return `<label>${ML(mk)}<input type="text" data-mk="${mk}" class="auto" value="" placeholder="${val}" disabled></label>`;
    return `<label class="${anker.has(mk) && !own ? 'rec' : ''}"${!own && (r.moneymoney || {})[mk] != null ? ' title="aus MoneyMoney"' : ''}>${ML(mk)}<input type="text" data-mk="${mk}" class="${own ? '' : 'auto'}" value="${own ? F(man[mk]) : ''}" placeholder="${val}"></label>`;
  }).join('');
  $('#h-von', d).value = months[0] || new Date().toISOString().slice(0, 7);
  $('#h-addrow', d).classList.toggle('hidden', !stand);
  $('#h-actions', d).classList.toggle('hidden', !stand && !pending);
  $('#h-clear', d).classList.toggle('hidden', !stand); $('#h-undo', d).classList.toggle('hidden', !pending);
  const g = $('#h-grid', d); if (g) g.scrollTop = g.scrollHeight;          // neueste Monate sichtbar
}
const HD = {uuid: null, live: false, r: null};

// ---------------------------------------------------------------- Bilanz
function vBilanz() {
  // Eine Tabelle: Positionen (farbig, aufklappbar) bzw. MoneyMoney-Gruppen; Plan-Spalten rechts angehängt
  const D = B(); if (!D) return noData;
  const C = cols();
  const view = S.bilanzView || 'positionen';
  const pr = S.plan ? D.bilanz.projektion : null;
  const proj = pr ? Object.fromEntries(pr.zeilen.map(r => [r.id, r.werte])) : {};
  const W = new Map(), werte = r => { if (!W.has(r.id)) W.set(r.id, proj[r.id] ? Object.assign({}, r.werte, proj[r.id]) : r.werte); return W.get(r.id); };
  const nw = pr ? Object.assign({}, D.bilanz.nettovermoegen, pr.nettovermoegen) : D.bilanz.nettovermoegen;
  const nInactive = (D.konten_inaktiv || []).length;
  const pos = D.bilanz.zeilen.filter(r => r.gruppe);
  S.posOpen = S.posOpen || {};
  const allOpen = pos.length && pos.every(r => S.posOpen[r.rolle]);
  let h = `<div class="toolbar">${viewCtl(true)}<span class="tb-sep"></span><div class="seg"><button data-v="positionen" class="${view === 'positionen' ? 'on' : ''}">Bilanzpositionen</button><button data-v="gruppen" class="${view === 'gruppen' ? 'on' : ''}">MoneyMoney-Gruppen</button></div>${view === 'positionen' ? `<button class="ghost small" id="pos-all">${allOpen ? 'alle zuklappen' : 'alle aufklappen'}</button>` : ''}${nInactive ? `<label class="switch"><input type="checkbox" id="show-inactive" ${S.showInactive ? 'checked' : ''}><i></i>${nInactive} ausgeblendete zeigen</label>` : ''} ${hq('bilanz_stand')}<span class="sp"></span>${xlsxBtn('balance')}</div>`;
  const tag = r => (r.depot ? '<span class="tag">Depot</span>' : '') + (r.offline && !r.gruppe ? '<span class="tag">manuell</span>' : '') + (r.inaktiv ? '<span class="tag">ausgeblendet</span>' : '')
    + (r.verlauf === 'stand' && !r.gruppe ? '<span class="tag" title="Verlauf aus Kontoständen">Kontostände</span>' : '')
    + (r.geschaetzt_bis ? `<span class="tag warn" title="Kontostände bis ${ML(r.geschaetzt_bis)} aus Käufen/Verkäufen geschätzt – Werte eintragen oder importieren">geschätzt bis ${ML(r.geschaetzt_bis)}</span>` : '')
    + (r.fortgeschrieben_vor ? `<span class="tag warn" title="Vor ${ML(r.fortgeschrieben_vor)} ist kein Stand bekannt – bis dahin steht rückwärts der erste bekannte Wert. Klick: Monatsstände eintragen, Datei importieren oder ein Verrechnungskonto für die Schätzung wählen.">vor ${ML(r.fortgeschrieben_vor)} unbekannt</span>` : '')
    + (view === 'gruppen' && r.rolle && !r.gruppe ? `<span class="tag">${(ROLE[r.rolle] || [r.rolle])[0]}</span>` : '');
  const row = (r, cls0, label) => `<tr class="${cls0}" data-id="${r.id}"><td title="${esc(r.pfad || r.name)}">${label}</td>${C.map(c => { const v = lastOf(werte(r), c.months); return `<td class="${cls(v, c)}">${F(v)}</td>`; }).join('')}</tr>`;
  const skip = r => { if (!r.gruppe && r.inaktiv && !S.showInactive) return true; const vals = C.map(c => lastOf(werte(r), c.months)); return !S.nullzeilen && !r.gruppe && !r.inaktiv && vals.every(v => v == null || Math.abs(v) < 0.005); };
  h += '<div class="wrap"><table>' + thead(view === 'gruppen' ? 'Konto (MoneyMoney-Gruppen)' : 'Position / Konto', C) + '<tbody>';
  if (view === 'positionen') {
    for (const r of D.bilanz.zeilen) {
      if (r.gruppe) {
        const [label, color] = ROLE[r.rolle] || [r.name, 'var(--c-neutral)'], open = !!S.posOpen[r.rolle];
        h += row(r, 'group pos', `<span class="caret">${open ? '▾' : '▸'}</span><i class="pos-dot" style="background:${color}"></i>${label} <span class="small muted">(${r.anzahl}${r.inaktive ? ', ' + r.inaktive + ' ausgeblendet' : ''})</span>`).replace('<tr ', `<tr data-pos="${r.rolle}" `).replace(` data-id="${r.id}"`, '');
        continue;
      }
      if (!S.posOpen[r.rolle] || skip(r)) continue;
      h += row(r, 'clickable acct ind1', esc(r.name) + tag(r));
      if (pr && r.rolle === 'beteiligungen' && proj.einlagen && r === D.bilanz.zeilen.filter(x => !x.gruppe && x.rolle === 'beteiligungen').slice(-1)[0])
        h += row({id: 'einlagen', name: 'Einlagen/Entnahmen (kumuliert, Plan)', werte: {}}, 'ind1 muted', 'Einlagen/Entnahmen Beteiligungen (kumuliert, Plan)');
    }
  } else {
    const hidden = new Set();
    for (const r of (D.bilanz.baum || [])) {
      if ([...hidden].some(p => r.pfad.startsWith(p + ' / '))) continue;
      if (skip(r)) continue;
      const coll = S.collapsed[r.id]; if (r.gruppe && coll) hidden.add(r.pfad);
      h += row(r, `${r.gruppe ? 'group' : 'clickable acct'} ind${Math.min(r.ebene, 4)}`, `${r.gruppe ? (coll ? '▸ ' : '▾ ') : ''}${esc(r.name)}${tag(r)}`);
    }
  }
  h += `<tr class="total"><td>Nettovermögen${pr ? ' <span class="small muted">(rechts: Plan)</span>' : ''}</td>${cells(C, c => lastOf(nw, c.months))}</tr>`;
  h += (D.bilanz.ausserhalb || []).map(r => `<tr class="muted"><td>${esc(r.name)} <span class="tag">${esc((ROLE[r.rolle] || [r.rolle])[0])} · nicht im Nettovermögen</span></td>${cells(C, c => lastOf(r.werte, c.months))}</tr>`).join('');
  h += '</tbody></table></div>';
  h += '<div class="note">Klick auf eine Position klappt sie auf, Klick auf ein Konto öffnet Position, Verlaufsquelle und Monatsstände. Positionen: Einrichtung → Konten. Plan-Spalten (rechts): Liquidität + Zahlungsfluss; Darlehen − Tilgung; Wertpapiere/Immobilien/Beteiligungen + Investition + Wertentwicklung bzw. Kalkulation (Planung → Parameter).</div>';
  return h;
}

// ---------------------------------------------------------------- Kapitalfluss / Planung
const SEC_LABEL = {Einnahmen: 'Einnahmen', Ausgaben: 'Ausgaben', Investitionen: 'Investitionen (Umschichtung)', Finanzierung: 'Finanzierung (Tilgung + Zinsen)', Bewertung: 'Bewertung & manuelle Buchungen (nicht zahlungswirksam)', Unklar: 'Unklar (Zuordnung prüfen)'};
const METH = {gleitend12: 'Ø 12 Monate', gleitend6: 'Ø 6 Monate', vorjahr: 'Vorjahresmonat', fix: 'fester Betrag/Monat', jahresbetrag: 'Jahresbetrag/12', budget: 'MoneyMoney-Budget', keine: 'keine'};
function vKapitalfluss(editable) {
  const D = B(); if (!D) return noData;
  const C = cols(), KF = D.kapitalfluss, sums = KF.summen || {}, P = D.plan || {};
  const vOf = (z, c) => sumOver(Object.assign({}, z.werte, (z.plan && z.plan.werte) || {}), c.months);
  const sOf = (z, c) => sumOver(Object.assign({}, z.werte, (z.plan && z.plan.vorschlag) || {}), c.months);
  let h = `<div class="toolbar">${viewCtl(true)}<span class="sp"></span>${xlsxBtn(editable ? 'planning' : 'cashflow')}</div>`;
  h += '<div class="legend"><span class="p">Plan</span><span class="c">laufender Monat</span><span class="y">Jahressumme</span><span class="o">überschrieben</span>' + (editable ? '<label class="chk"><input type="checkbox" id="vorschlag-an" ' + (S.vorschlag ? 'checked' : '') + '> Vorschlagswerte zeigen</label><em>Doppelklick auf eine Planzelle = eigener Wert · Methode, Betrag, Steigerung unter dem Zeilennamen · ↺ = Vorschlag wiederherstellen</em>' : '') + (S.real ? '<em class="pill info">Planwerte in heutiger Kaufkraft</em>' : '') + '</div>';
  if (editable) {
    h += `<div class="card" style="margin-bottom:12px"><h3>Parameter</h3><div class="row tight">
      <label>Horizont <input id="p_horizont" type="number" min="1" max="240" value="${P.horizont_monate ?? 24}" style="width:70px"> Monate</label>
      <label>Standardmethode ${hq('methode')} <select id="p_methode">${['gleitend12', 'gleitend6', 'vorjahr', 'budget', 'keine'].map(x => `<option value="${x}" ${P.standard_methode === x ? 'selected' : ''}>${METH[x]}</option>`).join('')}</select></label>
      <label>Inflation ${hq('inflation')} <input id="p_infl" type="number" step="0.1" value="${P.inflation_prozent_pa ?? 2}" style="width:64px"> % p.a.</label>
      <label>Steigerung Einnahmen ${hq('steig_ein')} <input id="p_se" type="number" step="0.1" value="${P.steigerung_einnahmen_prozent_pa ?? 0}" style="width:64px"> %</label>
      <label>Ausgaben <input id="p_sa" type="number" step="0.1" value="${P.steigerung_ausgaben_prozent_pa ?? ''}" placeholder="= Inflation" style="width:64px"> %</label>
      <label>Rendite Wertpapiere/Anlagen ${hq('rendite')} <input id="p_rendite" type="number" step="0.1" value="${P.rendite_prozent_pa ?? 0}" style="width:64px"> %</label>
      <button id="p_save" class="small">Übernehmen</button><button id="p_reset" class="small secondary" title="Alle Planeinstellungen dieses Bereichs löschen">Plan zurücksetzen</button></div>
      <div class="note" style="margin:6px 0 0">Ausgaben steigen standardmäßig mit der Inflation, Einnahmen mit der eingetragenen Rate. Jede Zeile kann eigene Methode, Betrag und Steigerung haben; einzelne Monate lassen sich überschreiben – der Vorschlag bleibt sichtbar.</div></div>`;
  }
  h += '<div class="wrap"><table>' + thead('Position', C) + '<tbody>';
  const secTotal = name => C.map(c => c.months.reduce((a, m) => a + (sums[m]?.[name] ?? 0) * defl(m), 0));
  for (const sek of KF.sektionen) {
    const tot = secTotal(sek.name);
    if (!sek.zeilen.length && !S.nullzeilen) continue;
    h += `<tr class="sec"><td>${SEC_LABEL[sek.name] || sek.name}</td>${tot.map((v, i) => `<td class="${cls(v, C[i])}">${F(v)}</td>`).join('')}</tr>`;
    const groups = [];
    for (const z of sek.zeilen) { let g = groups.find(x => x.name === z.gruppe); if (!g) groups.push(g = {name: z.gruppe, rows: []}); g.rows.push(z); }
    for (const g of groups) {
      const gvals = C.map(c => g.rows.reduce((a, z) => a + vOf(z, c), 0));
      const single = g.rows.length === 1 && g.rows[0].zeile === g.name;
      if (!S.nullzeilen && gvals.every(v => Math.abs(v) < 0.005)) continue;
      const gid = sek.name + '|' + g.name, coll = S.collapsed[gid];
      if (!single) h += `<tr class="sub ind1" data-gid="${esc(gid)}"><td>${coll ? '▸ ' : '▾ '}${esc(g.name)}</td>${gvals.map((v, i) => `<td class="${cls(v, C[i])}">${F(v)}</td>`).join('')}</tr>`;
      if (coll && !single) continue;
      for (const z of g.rows) {
        const vals = C.map(c => vOf(z, c));
        if (!S.nullzeilen && vals.every(v => Math.abs(v) < 0.005)) continue;
        const key = sek.name + '/' + z.zeile;
        const label = single ? z.zeile : z.zeile.startsWith(g.name + ' / ') ? z.zeile.slice(g.name.length + 3) : z.zeile;
        let e = '';
        const p = z.plan || {}, ov = new Set(p.ueberschrieben || []);
        if (editable) {
          const isLoan = p.methode === 'darlehen';
          e = isLoan ? `<div class="edit"><span class="tag">Darlehensplan (Zins auf Restsaldo)</span>${ov.size ? ` <button class="small secondary reset-row" data-key="${esc(key)}" title="alle Überschreibungen löschen">↺</button>` : ''}</div>`
            : `<div class="edit" data-key="${esc(key)}">
              <select class="meth"><option value="">Standard</option>${Object.entries(METH).map(([mm, ml]) => `<option value="${mm}" ${p.methode === mm && (D.plan.zeilen || {})[key]?.methode ? 'selected' : ''}>${ml}</option>`).join('')}</select>
              <input class="betrag" type="number" step="0.01" placeholder="Betrag" value="${p.betrag ?? ''}" title="Betrag für fester Betrag / Jahresbetrag">
              <input class="pct steig" type="number" step="0.1" placeholder="% p.a." value="${(D.plan.zeilen || {})[key]?.steigerung_prozent_pa ?? ''}" title="Steigerung % p.a. (leer = Standard)">
              <button class="save small" title="Übernehmen">✓</button>${ov.size ? `<button class="small secondary reset-row" data-key="${esc(key)}" title="alle Überschreibungen löschen">↺</button>` : ''}</div>`;
        }
        h += `<tr class="${single ? 'ind1' : 'ind2'}" data-key="${esc(key)}"><td title="${esc(z.zeile)}">${esc(label)}${z.nw ? '' : '<span class="tag">Umschichtung</span>'}${editable && p.methode && p.methode !== 'darlehen' ? `<span class="tag">${METH[p.methode] || p.methode}${p.budget ? ' · Budget ' + F0(p.budget) : ''}</span>` : ''}${e}</td>`
           + vals.map((v, i) => {
               const c = C[i], isOv = c.plan && c.months.some(mm => ov.has(mm));
               const sug = (S.vorschlag && c.plan) ? `<div class="small muted">${F(sOf(z, c))}</div>` : '';
               return `<td class="${cls(v, c)}${editable && c.plan && !c.year ? ' editable' : ''}${isOv ? ' ov' : ''}" data-month="${c.key}" ${isOv ? `title="Vorschlag: ${F(sOf(z, c))}"` : ''}>${F(v)}${sug}</td>`; }).join('') + '</tr>';
      }
    }
  }
  for (const [name, label] of [['Operativ', 'Operatives Ergebnis (Einnahmen + Ausgaben)'], ['Zinsen', 'davon Zinsen'], ['Cashflow', 'Zahlungsfluss gesamt (Veränderung Liquidität)'], ['Nettovermoegen_delta', 'Nettovermögensänderung (erklärt)']]) {
    const tot = secTotal(name);
    h += `<tr class="total"><td>${label}</td>${tot.map((v, i) => `<td class="${cls(v, C[i])}">${F(v)}</td>`).join('')}</tr>`;
  }
  const ue = KF.ueberleitung || {};
  h += `<tr><td>Unerklärte Vermögensänderung (Prüfzeile)</td>${C.map(c => { const v = c.plan ? null : c.months.reduce((a, m) => a + (ue[m]?.unerklaert ?? 0), 0); return `<td class="${cls(v, c)}">${v == null ? '' : F(v)}</td>`; }).join('')}</tr>`;
  h += '</tbody></table></div>';
  if (editable) h += vPlanExtras(D);
  h += '<div class="note">Umschichtungen (Tilgung, Investition, Einlage) verändern das Nettovermögen nicht; Einnahmen, Ausgaben, Zinsen und Bewertungen schon. Die Prüfzeile sollte nahe 0 liegen – sonst fehlt eine Zuordnung (Kategorien) oder eine Gegenbuchung.' + (editable ? ' Methoden: Ø 12/6 Monate der abgeschlossenen Monate, Vorjahresmonat, fester Betrag je Monat, Jahresbetrag/12, MoneyMoney-Budget der Kategorie; Steigerung in % p.a. wirkt auf jede Methode.' : '') + '</div>';
  return h;
}
function vPlanExtras(D) {
  const P = D.plan || {}, loans = D.darlehen_konfig || {};
  const fin = (D.kapitalfluss.sektionen.find(s => s.name === 'Finanzierung') || {zeilen: []}).zeilen;
  const loanNames = [...new Set(fin.filter(z => z.konto).map(z => z.gruppe))];
  let h = '<h2>Darlehensplan</h2><div class="note">Zins auf den fortgeschriebenen Restsaldo, Tilgung = Zahlung − Zins. Darlehen mit Regel sind vorbelegt; für Bankdarlehen Zinssatz und Modell eintragen (leer = Planmethode der Zeilen).</div><div class="wrap auto"><table class="plain"><thead><tr><th>Darlehen</th><th>Zins % p.a.</th><th>Modell</th><th>Zahlung je Monat (leer = Durchschnitt)</th><th></th></tr></thead><tbody>';
  for (const name of loanNames) {
    const d = (P.darlehen || {})[name] || {}; const cfgLoan = Object.values(loans).find(l => l.name === name);
    h += `<tr data-loan="${esc(name)}"><td>${esc(name)}${cfgLoan ? '<span class="tag">Regel: ' + esc(cfgLoan.modell) + '</span>' : ''}</td><td class="num"><input type="number" step="0.01" class="lz" value="${d.zins_prozent_pa ?? ''}" style="width:90px"></td><td><select class="lm"><option value="restschuld_monatlich" ${d.modell === 'restschuld_monatlich' ? 'selected' : ''}>Restschuld monatlich</option><option value="jahresbasis" ${d.modell === 'jahresbasis' ? 'selected' : ''}>Jahresbasis (31.12.)</option></select></td><td class="num"><input type="number" step="0.01" class="lp" value="${d.zahlung ?? ''}" style="width:110px"></td><td><button class="small save-loan">✓</button></td></tr>`;
  }
  if (!loanNames.length) h += '<tr><td colspan="5" class="muted">Keine Darlehenszeilen im Kapitalfluss.</td></tr>';
  h += '</tbody></table></div>';
  const leafs = D.bilanz.zeilen.filter(r => !r.gruppe && r.rolle !== 'liquiditaet');
  const others = Object.entries((S.DATA && S.DATA.bereich_namen) || {}).filter(([k]) => k !== S.bereich);
  h += `<h2>Wertentwicklung je Konto ${hq('rendite')}</h2><div class="note">Jährliche Wertänderung in Prozent; Basis optional als feste Bezugsgröße, sonst der fortgeschriebene Saldo. Ohne Eintrag gilt die Planrendite für Wertpapiere und Geldanlagen. Beteiligungskonten lassen sich an einen anderen Bereich koppeln ${hq('wert_bereich')}; Konten mit Immobilienkalkulation folgen dem Objektwert der Kalkulation.</div><div class="wrap auto"><table class="plain"><thead><tr><th>Konto</th><th>Position</th><th>% p.a.</th><th>Basis (€, optional)</th><th>Kopplung an Bereich</th><th>Anteil</th><th></th></tr></thead><tbody>`;
  for (const r of leafs) {
    const w = (P.wertentwicklung || {})[r.name] || {};
    h += `<tr data-acct="${esc(r.name)}"><td>${esc(r.pfad)}${r.inaktiv ? '<span class="tag">ausgeblendet</span>' : ''}</td><td class="small">${(ROLE[r.rolle] || [r.rolle])[0]}</td><td class="num"><input type="number" step="0.1" class="wp" value="${w.prozent_pa ?? ''}" style="width:80px"></td><td class="num"><input type="number" step="1" class="wb" value="${w.basis ?? ''}" style="width:130px"></td><td><select class="wbr"><option value="">–</option>${others.map(([k, n]) => `<option value="${k}" ${w.bereich === k ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></td><td class="num"><input type="number" step="0.01" min="0" max="1" class="wa" value="${w.anteil ?? ''}" placeholder="1" style="width:70px"></td><td><button class="small save-wert">✓</button></td></tr>`;
  }
  h += '</tbody></table></div>';
  // Ereignisse
  const evs = P.ereignisse || [];
  const konten = D.bilanz.zeilen.filter(r => !r.gruppe);
  const kOpt = sel => '<option value="">Liquidität (Bereich)</option>' + konten.map(k => `<option value="${k.id} | ${esc(k.name)}" ${sel && sel.split('|')[0].trim() === k.id ? 'selected' : ''}>${esc(k.name)}${k.rolle ? ' · ' + (ROLE[k.rolle] || [k.rolle])[0] : ''}</option>`).join('');
  const WH = {einmalig: 'einmalig', monatlich: 'monatlich', quartal: 'je Quartal', jaehrlich: 'jährlich'};
  const nextM = (() => { const d = new Date(); d.setMonth(d.getMonth() + 1); return d.toISOString().slice(0, 7); })();
  const evRow = (e, isNew) => `<div class="ev-row item" data-id="${esc(e.id || '')}"><div class="grow">
    <div class="row tight"><input type="text" class="ev-text" value="${esc(e.text || '')}" placeholder="Bezeichnung, z. B. Rückzahlung Unternehmenskauf" style="width:260px">
      <select class="ev-art">${[['umschichtung', 'Umschichtung'], ['ausgabe', 'Ausgabe'], ['einnahme', 'Einnahme']].map(([v, l]) => `<option value="${v}" ${(e.art || 'umschichtung') === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <label class="chk small">Betrag <input type="number" step="0.01" class="ev-betrag" value="${e.betrag ?? ''}" style="width:120px"></label>
      <label class="chk small">Monat <input type="month" class="ev-monat" value="${esc(e.monat || (isNew ? nextM : ''))}"></label>
      <select class="ev-wdh">${Object.entries(WH).map(([v, l]) => `<option value="${v}" ${(e.wiederholung || 'einmalig') === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <label class="chk small">bis <input type="month" class="ev-bis" value="${esc(e.bis || '')}" title="Enddatum bei Wiederholung (leer = Horizont)"></label></div>
    <div class="row tight"><label class="chk small">Von <select class="ev-von">${kOpt(e.von)}</select></label><span class="muted">→</span><label class="chk small">Nach <select class="ev-nach">${kOpt(e.nach)}</select></label>
      <label class="chk small"><input type="checkbox" class="ev-aktiv" ${e.aktiv !== false ? 'checked' : ''}> aktiv</label>
      <button class="small ev-save">${e.id ? 'Speichern' : 'Hinzufügen'}</button>${e.id ? '<button class="small danger ev-del">Löschen</button>' : ''}</div></div></div>`;
  h += `<h2>Geplante Ereignisse ${hq('ereignis')}</h2><div class="note">Umschichtung: Betrag geht von „Von“ nach „Nach“ (Konto leer = Liquidität des Bereichs). Beispiel Darlehen auf einen Schlag zurückzahlen: Von = Depot, Nach = Darlehenskonto. Einnahme/Ausgabe: zahlungswirksam, verändert das Nettovermögen. Wiederholungen bis zum Enddatum (leer = bis Horizont).</div><div class="list">`;
  for (const e of evs) h += evRow(e, false);
  h += evRow({}, true) + '</div>';
  return h;
}

// ---------------------------------------------------------------- Synchronisierung
async function vSync() {
  const st = S.STATUS, m = st.moneymoney || {}, z = st.dienst || {}, l = st.letzter_lauf, r = await api('/api/sync');
  const online = r.konten.filter(k => k.art === 'online'), offline = r.konten.filter(k => k.art === 'offline'), stale = online.filter(k => k.zurueck);
  const tage = t => r.neuester && t ? Math.floor((new Date(r.neuester.replace(' ', 'T')) - new Date(t.replace(' ', 'T'))) / 864e5) : null;
  const card = (t, v, d) => `<div class="card"><div class="l">${t}</div><div class="v s">${v}</div><div class="d">${d}</div></div>`;
  let h = `<div class="cards">
    ${card('MoneyMoney', `<span class="dot ${mmState(st).cls}"></span>${mmState(st).text}`, m.laeuft ? (m.gesperrt ? 'Zum Lesen in MoneyMoney entsperren.' : 'Kontor kann lesen.') : 'Kontor rechnet mit dem zuletzt gelesenen Stand.')}
    ${card('Banken → MoneyMoney', r.neuester ? esc(fmtZeit(r.neuester)) : '–', 'Neuester Bankabruf in MoneyMoney. Den Abruf löst du in MoneyMoney aus (von Hand oder per Zeitplan dort).')}
    ${card('MoneyMoney → Kontor', r.gelesen ? esc(fmtZeit(r.gelesen)) : '–', (z.automatisch ? 'Automatisch alle ' + z.intervall_minuten + ' Minuten, wenn MoneyMoney läuft und entsperrt ist' : 'Automatischer Abgleich ist aus') + ' (<a href="#einstellungen">Einstellungen</a>).')}
    ${hasRules() ? card('Regeln zuletzt angewendet', l ? esc(fmtZeit(l.zeit)) : '–', 'Nur wenn sich in MoneyMoney etwas geändert hat. <a href="#buchungen">Buchungen</a>') : ''}
  </div>
  <div class="toolbar"><button id="sync-now" ${OFFLINE.mode ? 'disabled' : ''}>Jetzt synchronisieren</button><span class="muted small">liest sofort aus MoneyMoney, wendet bei Änderungen die Regeln an und aktualisiert alle Auswertungen</span></div>`;
  if (stale.length) h += `<div class="banner">${stale.length === 1 ? '1 Konto liegt' : stale.length + ' Konten liegen'} mehr als einen Tag hinter dem neuesten Bankabruf: ${esc(stale.map(k => k.name).join(', '))}. In MoneyMoney einzeln aktualisieren (z. B. wenn eine TAN nötig ist).</div>`;
  const row = k => {
    const d = tage(k.zeit);
    const stand = k.art === 'offline' ? `<span class="muted">${esc(k.grund)}</span>` : k.alt ? '<span class="tag">ruht – seit über ' + ((S.CFG.bilanz || {}).inaktiv_monate || 12) + ' Monaten kein Abruf</span>' : k.zurueck ? `<span class="tag warn">${d} ${d === 1 ? 'Tag' : 'Tage'} zurück</span>` : d != null && d >= 1 && !(k.saldo) ? `<span class="muted">${d} Tage zurück (ohne Saldo)</span>` : '<span class="tag ok">aktuell</span>';
    return `<tr data-uuid="${k.uuid}"><td>${esc(k.name)}<div class="small muted">${esc(k.pfad.split(' / ').slice(0, -1).join(' / '))}</div></td><td class="small">${esc(k.bereich || '–')}</td>
      ${k.art === 'online' ? `<td class="nowrap">${k.zeit ? esc(fmtZeit(k.zeit)) : '–'}</td>` : ''}<td>${stand}</td>
      <td class="c"><input type="checkbox" class="ab-chk" ${k.art === 'online' ? 'checked' : ''} title="Wird von MoneyMoney bei Bank oder Dienst abgerufen"></td></tr>`;
  };
  const dep = r.depots || [];
  if (m.problem) h += `<div class="banner err">MoneyMoney lief am ${esc(fmtZeit(m.problem.zeit))}, Kontor konnte aber nicht lesen: ${esc(m.problem.text)} – ohne Lesen fehlen Depotstände. Der Hinweis verschwindet beim nächsten erfolgreichen Lesen.</div>`;
  if ((r.luecken || []).length) h += `<div class="banner">Möglicherweise fehlen Depotstände – MoneyMoney hat abgerufen, während Kontor nicht lief: ${r.luecken.map(l => `<b>${esc(l.name)}</b> ${l.monate.map(ML).join(', ')}`).join('; ')}. Die Monate im Verlauf-Fenster prüfen. <button class="small secondary" id="gap-ok">Hinweis ausblenden</button></div>`;
  if (dep.length) h += `<h2>Depots: Wertverlauf ${hq('depotverlauf')}</h2><div class="note">Bankkonten rechnet Kontor exakt aus den Umsätzen in MoneyMoney zurück – auch rückwirkend. Den Wertverlauf von Depots gibt MoneyMoney über seine Schnittstelle nicht heraus: Den bisherigen Verlauf übernimmt Kontor einmalig aus MoneyMoneys Datenbank, danach zeichnet Kontor selbst auf (seit ${r.aufzeichnung_seit ? ML(r.aufzeichnung_seit) : 'heute'}). Der Dienst läuft ab der Anmeldung im Hintergrund, auch ohne geöffnetes Kontor-Fenster, und liest innerhalb von etwa 20 Sekunden, sobald MoneyMoney offen und entsperrt ist – ein kurzer Blick in MoneyMoney genügt. Jeder Stand zählt für den Monat, in dem MoneyMoney ihn abgerufen hat. Rief MoneyMoney ab, während Kontor nicht lief, erscheint hier ein Hinweis.</div>
    <div class="small" style="margin:6px 0 10px">${r.mm_verlauf ? `Verlauf aus MoneyMoney übernommen am ${esc(fmtZeit(r.mm_verlauf.zeit))}.` : 'Bisheriger Verlauf noch nicht übernommen.'} <a href="#einrichtung/historie">Kontostände aus MoneyMoney ${r.mm_verlauf ? 'erneut ' : ''}einlesen</a></div>
    <div class="wrap auto"><table class="plain acct-table sync-table"><thead><tr><th>Depot</th><th>Bereich</th><th>Bekannt ab</th><th></th></tr></thead><tbody>${dep.map(k => `<tr data-uuid="${k.uuid}"><td>${esc(k.name)}<div class="small muted">${esc(k.pfad.split(' / ').slice(0, -1).join(' / '))}</div></td><td class="small">${esc(k.bereich || '–')}</td><td>${k.erster_stand ? ML(k.erster_stand) : '–'}${k.aus_moneymoney ? ' <span class="small muted">(aus MoneyMoney)</span>' : ''}${k.eigene ? ` <span class="small muted">(${k.eigene} eingetragen)</span>` : ''}</td><td class="c"><button class="small secondary dep-hist">Stände eintragen</button></td></tr>`).join('')}</tbody></table></div>`;
  h += `<h2>Konten mit Bankabruf (${online.length}) ${hq('abruf')}</h2><div class="wrap auto"><table class="plain acct-table sync-table"><thead><tr><th>Konto</th><th>Bereich</th><th>Letzter Abruf</th><th>Stand</th><th class="c">abgerufen</th></tr></thead><tbody>${online.map(row).join('') || '<tr><td colspan="5" class="muted">keine</td></tr>'}</tbody></table></div>`;
  h += `<h2>Ohne Bankabruf (${offline.length})</h2><div class="note">Von Hand geführte Konten (z. B. Kapitalkonten, private Darlehen, Immobilien) – sie zählen nicht für den Datenstand. Falsch erkannt? Häkchen bei „abgerufen“ setzen bzw. oben entfernen.</div>
    <div class="wrap auto"><table class="plain acct-table sync-table"><thead><tr><th>Konto</th><th>Bereich</th><th>Erkannt als</th><th class="c">abgerufen</th></tr></thead><tbody>${offline.map(row).join('') || '<tr><td colspan="4" class="muted">keine</td></tr>'}</tbody></table></div>`;
  return h;
}

// ---------------------------------------------------------------- Buchungen (Laeufe)
function vBuchungen(runs) {
  const st = S.STATUS, l = runs.letzter_lauf;
  let h = `<div class="toolbar">
    <button id="run-dry">Abgleich jetzt (Test)</button>
    <button id="run-live" class="${st.probelauf ? 'secondary' : ''}" ${st.lokal ? '' : 'disabled title="nur am Mac"'}>Jetzt buchen</button>
    <button id="run-report" class="secondary">Nur Bericht aktualisieren</button>
  </div>`;
  if (l) {
    h += `<h2>Regeln zuletzt angewendet ${esc(l.zeit)} · ${l.probelauf ? '<span class="pill warn">Testmodus</span>' : '<span class="pill ok">gebucht</span>'} · ${l.geschrieben} gebucht${l.fehler ? ' · <span class="pill err">' + esc(l.fehler) + '</span>' : ''}</h2>`;
    if (l.vorschlaege && l.vorschlaege.length) {
      h += '<div class="wrap auto"><table class="plain"><thead><tr><th>Datum</th><th>Konto</th><th>Art</th><th class="num">Betrag</th><th>Text</th><th>Kategorie</th></tr></thead><tbody>'
        + l.vorschlaege.map(v => `<tr><td style="white-space:nowrap">${FD(v.datum)}</td><td>${esc(v.konto)}</td><td>${esc(v.art)}</td><td class="num ${v.betrag < 0 ? 'neg' : 'pos'}">${F(v.betrag)}</td><td>${esc(v.text)}</td><td>${esc(v.kategorie || '')}</td></tr>`).join('') + '</tbody></table></div>';
      if (l.probelauf) h += '<div class="note">Diese Buchungen sind noch nicht in MoneyMoney. „Jetzt buchen“ legt sie an (nur Offline-Konten) – oder in den Einstellungen den Testmodus dauerhaft abschalten.</div>';
    } else h += '<div class="note">Keine Buchungen nötig.</div>';
    if (l.hinweise && l.hinweise.length) h += '<h3>Rechenwege</h3>' + l.hinweise.map(x => `<div class="small muted">${esc(x)}</div>`).join('');
    if (l.warnungen && l.warnungen.length) h += '<h3>Hinweise</h3>' + l.warnungen.map(x => `<div class="banner">${esc(x)}</div>`).join('');
  }
  h += '<h2>Verlauf</h2><div class="wrap auto"><table class="plain"><thead><tr><th>Zeit</th><th>Modus</th><th class="num">Vorschläge</th><th class="num">Gebucht</th><th>Fehler</th><th>Buchungen</th></tr></thead><tbody>'
    + (runs.verlauf || []).map(v => `<tr><td>${esc(v.zeit)}</td><td>${v.probelauf ? 'Test' : 'gebucht'}</td><td class="num">${v.vorschlaege ?? ''}</td><td class="num">${v.geschrieben}</td><td>${esc(v.fehler || '')}</td><td class="small">${(v.buchungen || []).map(esc).join('<br>')}</td></tr>`).join('') + '</tbody></table></div>';
  return h;
}

// ---------------------------------------------------------------- Steuer
function vSteuer() {
  if (!S.DATA || !S.DATA.steuer) return noData;
  const T = S.DATA.steuer, years = T.jahre, ents = T.entitaeten;
  if (!years.length || !ents.length) return '<div class="note">Keine Steuerdaten (keine kategorisierten Buchungen).</div>';
  if (!S.steuerJahr) S.steuerJahr = String(years[years.length - 1]);
  if (!S.steuerEnt || !ents.some(e => e.uuid === S.steuerEnt)) S.steuerEnt = (ents.find(e => e.uuid === S.bereich) || ents[0]).uuid;
  const ent = ents.find(e => e.uuid === S.steuerEnt) || ents[0];
  let h = `<div class="toolbar"><label>Jahr <select id="st-jahr">${years.map(y => `<option ${String(y) === S.steuerJahr ? 'selected' : ''}>${y}</option>`).join('')}</select></label>
    <label>Entität <select id="st-ent">${ents.map(e => `<option value="${e.uuid}" ${e.uuid === ent.uuid ? 'selected' : ''}>${esc(e.name)} (${e.art}${e.anteil ? ', Anteil ' + (e.anteil * 100).toFixed(0) + ' %' : ''})</option>`).join('')}</select></label>
    <span class="sp"></span><button id="st-belege" class="secondary small">Belege ${esc(S.steuerJahr)} exportieren</button>${xlsxBtn('tax')}</div>`;
  const J = ent.jahre[S.steuerJahr]; if (!J) return h + '<div class="note">Keine Daten für dieses Jahr.</div>';
  const objs = Object.keys(J.objekte);
  h += `<div class="cards"><div class="card"><div class="l">Einnahmen (kategorisiert)</div><div class="v">${F0(J.summe_einnahmen)} €</div></div><div class="card"><div class="l">Ausgaben (kategorisiert)</div><div class="v">${F0(J.summe_ausgaben)} €</div></div><div class="card"><div class="l">Schuldzinsen</div><div class="v">${F0(Object.values(J.schuldzinsen).reduce((a, b) => a + b, 0))} €</div></div><div class="card"><div class="l">Ohne Kategorie</div><div class="v">${J.ohne_kategorie.anzahl ? '<span class="pill warn">' + J.ohne_kategorie.anzahl + ' Buchungen</span>' : '<span class="pill ok">keine</span>'}</div><div class="d">${F(J.ohne_kategorie.betrag)} € – <a href="#umsaetze?ohne_kategorie=1&jahr=${S.steuerJahr}&entitaet=${ent.uuid}">kategorisieren</a></div></div></div>`;
  if (objs.length) {
    h += `<h2>Vermietung je Objekt <span class="x">Kategorien „${esc(T.vermietung_kategorie)} \\ Objekt \\ Art“</span></h2><div class="wrap auto"><table class="plain"><thead><tr><th>Position</th>${objs.map(o => `<th class="num">${esc(o)}</th>`).join('')}</tr></thead><tbody>`;
    const arten = [...new Set(objs.flatMap(o => Object.keys(J.objekte[o].arten)))];
    for (const a of arten) h += `<tr><td class="ind1">${esc(a)}</td>${objs.map(o => `<td class="num">${F(J.objekte[o].arten[a] ?? 0)}</td>`).join('')}</tr>`;
    h += `<tr class="total"><td>Einnahmen</td>${objs.map(o => `<td class="num pos">${F(J.objekte[o].einnahmen)}</td>`).join('')}</tr>`;
    h += `<tr class="total"><td>Werbungskosten (ohne Zinsen/AfA)</td>${objs.map(o => `<td class="num neg">${F(J.objekte[o].werbungskosten)}</td>`).join('')}</tr>`;
    const loans = [...new Set(objs.flatMap(o => Object.keys(J.objekte[o].schuldzinsen)))];
    for (const l of loans) h += `<tr><td class="ind1">Schuldzinsen ${esc(l)}</td>${objs.map(o => `<td class="num">${F(J.objekte[o].schuldzinsen[l] ?? 0)}</td>`).join('')}</tr>`;
    h += `<tr><td class="ind1">AfA (manuell)</td>${objs.map(o => `<td class="num"><input type="number" step="0.01" class="afa" data-obj="${esc(o)}" value="${J.objekte[o].afa || ''}" style="width:110px"></td>`).join('')}</tr>`;
    h += `<tr class="total"><td>Ergebnis (Überschuss / Verlust)</td>${objs.map(o => `<td class="num ${J.objekte[o].ergebnis < 0 ? 'neg' : 'pos'}">${F(J.objekte[o].ergebnis)}</td>`).join('')}</tr>`;
    if (ent.anteil) h += `<tr class="total"><td>davon Anteil ${(ent.anteil * 100).toFixed(0)} %</td>${objs.map(o => `<td class="num">${F(J.objekte[o].anteil_ergebnis)}</td>`).join('')}</tr>`;
    h += '</tbody></table></div><div class="actions"><button id="afa-save" class="small">AfA speichern</button></div>';
  } else h += `<div class="note">Keine Vermietungskategorien für diese Entität gefunden. Erwartetes Muster: „${esc(T.vermietung_kategorie)} \\ Objektname \\ Art“ (z. B. Mieteinnahmen, Nebenkosten, Hausgeld, Instandhaltung, Grundsteuer, Versicherung). Objekte entstehen allein aus den Kategorienamen.</div>`;
  h += `<h2>${ent.art === 'privat' ? 'Steuerpositionen' : 'Oberkategorien'}</h2><div class="wrap auto"><table class="plain"><thead><tr><th>Position</th><th>Kategorie</th><th class="num">Betrag</th><th class="num">Buchungen</th></tr></thead><tbody>`;
  for (const [pos, p] of Object.entries(J.positionen)) {
    h += `<tr class="sub"><td colspan="2">${esc(pos)}</td><td class="num ${p.betrag < 0 ? 'neg' : 'pos'}">${F(p.betrag)}</td><td></td></tr>` + p.kategorien.map(k => `<tr><td></td><td>${esc(k.pfad)}</td><td class="num">${F(k.betrag)}</td><td class="num">${k.anzahl}</td></tr>`).join('');
  }
  h += '</tbody></table></div><div class="note">Zusammenstellung der kategorisierten Buchungen ohne Umbuchungen; Wertbuchungen auf Anlage-/Beteiligungskonten zählen nicht. Zuordnung der Kategorien zu Positionen unter Einstellungen → Steuer. Belege zu Umsätzen unter „Umsätze & Belege“; der Export legt eine ZIP-Datei mit allen Belegen des Jahres und einer Übersicht (CSV) im Belegordner ab. Keine Steuerberatung.</div>';
  return h;
}

// ---------------------------------------------------------------- Immobilien
const IM = {edit: null, res: null, tab: 'kalkulation', kalk: null, timer: null};
const immoOf = id => (S.CFG.immobilien || []).find(x => String(x.id) === String(id));
const immoData = id => ((S.DATA && S.DATA.immobilien) || []).find(x => String(x.id) === String(id));
function vImmobilien(id) {
  if (id) return vImmobilie(id);
  const list = S.CFG.immobilien || [];
  let h = `<div class="toolbar"><span class="muted small">Kalkulationen je Objekt, mehrere Szenarien, Soll/Ist gegen MoneyMoney, Übernahme in Planung und Steuer.</span><span class="sp"></span><button id="im-new" class="small">Neues Objekt</button></div>`;
  if (!list.length) return h + '<div class="card"><div class="v s">Noch keine Immobilie</div><div class="d">Lege ein Objekt an und erfasse Kaufpreis, Nebenkosten, Miete, Kosten, Finanzierung und Gesellschafter. Die Kalkulation rechnet Steuer, Cashflow, Vermögensaufbau, Renditen und IRR über den gewählten Horizont – und kann die Planung des Bereichs füttern.</div></div>';
  h += '<div class="cards k3">' + list.map(im => { const d = immoData(im.id) || {}; const K = d.kennzahlen || {}; const j1 = (d.jahre || []).find(j => j.monate === 12) || (d.jahre || [])[0];
    return `<div class="card clickable" data-im="${esc(im.id)}" style="cursor:pointer"><div class="l">${esc(BN(im.bereich) || im.bereich || '–')}${im.in_planung ? '<span class="tag">in Planung</span>' : ''}</div><div class="v s">${esc(im.name)}</div>
      <div class="d">${K.kaufpreis != null ? 'Kaufpreis ' + F0(K.kaufpreis) + ' € · Faktor ' + (K.kaufpreisfaktor ?? '–') + ' · Bruttorendite ' + (K.bruttomietrendite != null ? (K.bruttomietrendite * 100).toFixed(2) + ' %' : '–') : 'keine Kalkulation'}</div>
      <div class="d">${j1 ? 'Cashflow ' + j1.jahr + ': <b class="' + (j1.cashflow < 0 ? 'neg' : 'pos') + '">' + F0(j1.cashflow) + ' €</b> · EK-Rendite ' + (j1.ek_rendite != null ? (j1.ek_rendite * 100).toFixed(1) + ' %' : '–') + ' · IRR ' + (K.irr != null ? (K.irr * 100).toFixed(1) + ' %' : '–') : ''}</div>
      ${(d.hinweise || []).length ? `<div class="d"><span class="pill warn">${d.hinweise.length} Hinweise</span></div>` : ''}</div>`; }).join('') + '</div>';
  return h;
}
function vImmobilie(id) {
  const im = immoOf(id); if (!im) return '<div class="banner err">Immobilie nicht gefunden.</div>';
  const d = immoData(id) || {};
  const kalks = im.kalkulationen || [];
  if (!IM.kalk || !kalks.some(k => k.id === IM.kalk)) IM.kalk = (kalks.find(k => k.aktiv) || kalks[0] || {}).id || null;
  const k = kalks.find(x => x.id === IM.kalk);
  if (!IM.edit || IM.editFor !== id + '|' + IM.kalk) { IM.edit = JSON.parse(JSON.stringify((k && k.eingaben) || null)); IM.editFor = id + '|' + IM.kalk; IM.res = null; }
  const konten = S.KONTEN.filter(x => !x.gruppe);
  const kats = S.KATS.filter(x => x.ebene <= 1);
  let h = `<div class="toolbar"><a href="#immobilien" class="small">← Alle Objekte</a><h2 style="margin:0">${esc(im.name)}</h2><span class="sp"></span>${xlsxBtn('property', `data-immo="${esc(im.id)}" data-kalk="${esc(IM.kalk || '')}"`)}<button id="im-del" class="danger small">Objekt löschen</button></div>
  <div class="card" style="margin-bottom:12px"><div class="immo-form">
    <label>Name</label><input type="text" id="im-name" value="${esc(im.name)}">
    <label>Bereich ${hq('bereich')}</label><select id="im-bereich">${Object.entries((S.DATA && S.DATA.bereich_namen) || {}).map(([bid, n]) => `<option value="${bid}" ${im.bereich === bid ? 'selected' : ''}>${esc(n)}</option>`).join('') || (S.CFG.bereiche || []).map(b => `<option value="${esc(b.id)}" ${im.bereich === b.id ? 'selected' : ''}>${esc(b.name)}</option>`).join('')}</select>
    <label>Vermietungskategorie ${hq('immo_kategorie')}</label><input type="text" id="im-kat" list="im-kats" value="${esc(im.kategorie || '')}" placeholder="Vermietung \\ Objekt"><datalist id="im-kats">${kats.map(c => `<option value="${esc(c.roh)}">`).join('')}</datalist>
    <label>Objektkonto (Wert) ${hq('immo_objektkonto')}</label><select id="im-konto">${acctOptions(im.objekt_konto, x => !x.gruppe)}</select>
    <label>In Planung übernehmen ${hq('immo_planung')}</label><label class="switch"><input type="checkbox" id="im-plan" ${im.in_planung ? 'checked' : ''}><i></i>${im.in_planung ? 'aktiv' : 'aus'}</label>
    <label>Notizen</label><input type="text" id="im-notiz" value="${esc(im.notizen || '')}">
  </div><div class="actions"><button id="im-save-meta" class="small">Objekt speichern</button></div></div>
  <div class="tabs">${[['kalkulation', 'Kalkulation'], ['jahre', 'Jahrestabelle'], ['sollist', 'Soll / Ist'], ['dokumente', 'Dokumente (' + (im.dokumente || []).length + ')']].map(([t, l]) => `<button data-t="${t}" class="${IM.tab === t ? 'on' : ''}">${l}</button>`).join('')}</div>`;
  if (IM.tab === 'kalkulation') h += vImmoKalk(im, k, konten);
  else if (IM.tab === 'jahre') h += vImmoJahre(d);
  else if (IM.tab === 'sollist') h += vImmoSollIst(d);
  else h += vImmoDokumente(im);
  return h;
}
function vImmoKalk(im, k, konten) {
  const kalks = im.kalkulationen || [];
  let h = `<div class="row tight"><label>Szenario <select id="im-kalk">${kalks.map(x => `<option value="${esc(x.id)}" ${x.id === IM.kalk ? 'selected' : ''}>${esc(x.name)}${x.aktiv ? ' (aktiv)' : ''}</option>`).join('')}${!kalks.length ? '<option value="">– keine –</option>' : ''}</select></label>
    <button id="im-kalk-new" class="small secondary">${kalks.length ? 'Als neues Szenario kopieren' : 'Kalkulation anlegen'}</button>${k && !k.aktiv ? '<button id="im-kalk-aktiv" class="small secondary">Als aktiv setzen</button>' : ''}${k ? '<button id="im-kalk-del" class="small danger">Szenario löschen</button>' : ''}
    <span class="small muted">Das aktive Szenario gilt für Planung, Steuer (AfA) und Übersicht.</span></div>`;
  if (!IM.edit) return h + '<div class="note">Noch keine Kalkulation – „Kalkulation anlegen“ startet mit sinnvollen Standardwerten.</div>';
  const e = IM.edit;
  const inp = (path, label, type = 'number', opts = {}) => { let v = get(e, path); if (type === 'month' && v) v = String(v).slice(0, 7); const attrs = Object.entries(opts).filter(([a]) => a !== 'hq').map(([a, b]) => `${a}="${b}"`).join(' '); return `<label>${label}${opts.hq ? hq(opts.hq) : ''}</label><input type="${type}" data-p="${path}" value="${v == null ? '' : esc(v)}" ${attrs}>`; };
  const sel = (path, label, options, hqk) => `<label>${label}${hqk ? hq(hqk) : ''}</label><select data-p="${path}">${options.map(([v, l]) => `<option value="${v}" ${String(get(e, path) ?? '') === String(v) ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
  h += `<div class="immo-grid"><div class="card"><h3>Eingaben <span class="muted" style="text-transform:none;letter-spacing:0">· Szenario „${esc(k ? k.name : 'neu')}“</span></h3><div class="immo-form">
    <h4>Objekt</h4>
    ${inp('name', 'Bezeichnung', 'text')}${sel('art', 'Art', [['gewerbe', 'Gewerbe'], ['wohnen', 'Wohnen']])}${inp('flaeche_qm', 'Fläche m²', 'number', {step: '0.1'})}${inp('einheiten', 'Einheiten', 'number', {step: '1'})}
    ${inp('kaufpreis', 'Kaufpreis €', 'number', {step: '1000'})}${inp('uebergang', 'Übergang (Nutzen/Lasten)', 'month', {hq: 'immo_uebergang'})}${inp('horizont_jahre', 'Horizont Jahre', 'number', {step: '1', min: '1', max: '60'})}
    <h4>Nebenkosten ${hq('immo_nk')}</h4>
    ${inp('nebenkosten.grunderwerbsteuer_prozent', 'Grunderwerbsteuer %', 'number', {step: '0.1'})}${inp('nebenkosten.notar', 'Notar (Kaufvertrag) €', 'number', {step: '1'})}${inp('nebenkosten.grundbuch', 'Grundbuch €', 'number', {step: '1'})}${inp('nebenkosten.makler', 'Makler €', 'number', {step: '1'})}${inp('nebenkosten.sonstige_afa', 'Sonstige (AfA-Basis) €', 'number', {step: '1'})}${inp('nebenkosten.sofort_abziehbar', 'Sofort abziehbar €', 'number', {step: '1'})}
    <h4>Abschreibung</h4>
    ${inp('gebaeudeanteil_prozent', 'Gebäudeanteil %', 'number', {step: '0.01', hq: 'immo_geb'})}${inp('afa_prozent', 'AfA % p.a.', 'number', {step: '0.01', hq: 'immo_afa'})}${inp('restnutzungsdauer_jahre', 'oder Restnutzungsdauer Jahre', 'number', {step: '1'})}
    <h4>Miete</h4>
    ${inp('miete.nettokalt_monat', 'Nettokaltmiete / Monat €', 'number', {step: '1'})}${inp('miete.nebenkosten_monat', 'Umlage (NK-Vorauszahlung) / Monat €', 'number', {step: '1'})}${inp('miete.leerstand_prozent', 'Leerstand / Mietausfall %', 'number', {step: '0.5'})}
    ${sel('miete.index.art', 'Anpassung', [['vpi', 'Indexmiete (VPI)'], ['prozent', 'feste Steigerung % p.a.'], ['keine', 'keine']], 'immo_index')}
    ${inp('miete.index.vpi_basis', 'VPI bei letzter Anpassung', 'number', {step: '0.1'})}${inp('miete.index.vpi_aktuell', 'VPI aktuell', 'number', {step: '0.1'})}${inp('miete.index.vpi_steigerung_prozent', 'VPI-Annahme % p.a.', 'number', {step: '0.1'})}${inp('miete.index.faktor', 'Weitergabe-Faktor (0–1)', 'number', {step: '0.05'})}${inp('miete.index.schwelle_prozent', 'Schwelle %', 'number', {step: '0.5'})}${inp('miete.index.steigerung_prozent', 'feste Steigerung % p.a.', 'number', {step: '0.1'})}
    <h4>Kosten</h4>
    ${inp('kosten.nicht_umlagefaehig_pa', 'Nicht umlagefähig p.a. €', 'number', {step: '10', hq: 'immo_kosten'})}${inp('kosten.ruecklage_pa', 'Rücklage p.a. €', 'number', {step: '10', hq: 'immo_ruecklage'})}${sel('kosten.steigerung', 'Steigerung', [['vpi', 'mit VPI'], ['prozent', 'fester Satz'], ['keine', 'keine']])}${inp('kosten.steigerung_prozent', 'fester Satz % p.a.', 'number', {step: '0.1'})}
    <h4>Gesellschafter ${hq('immo_ges')}</h4></div><div id="im-ges">${(e.gesellschafter || []).map((g, i) => `<div class="row tight" data-g="${i}"><input type="text" data-p="gesellschafter.${i}.name" value="${esc(g.name || '')}" placeholder="Name" style="width:140px"><input type="number" step="0.01" data-p="gesellschafter.${i}.anteil_prozent" value="${g.anteil_prozent ?? ''}" placeholder="Anteil %" style="width:90px"><input type="number" step="0.001" data-p="gesellschafter.${i}.steuersatz_prozent" value="${g.steuersatz_prozent ?? ''}" placeholder="Steuersatz %" style="width:110px"><button class="ghost small im-ges-del" data-i="${i}">✕</button></div>`).join('')}</div><div class="row tight"><button id="im-ges-add" class="small secondary">Gesellschafter hinzufügen</button></div>
    <div class="immo-form">${inp('ausschuettung_prozent', 'Ausschüttung % des Ergebnisses', 'number', {step: '1', hq: 'immo_aussch'})}${sel('steuererstattung_in_cashflow', 'Steuererstattung im Cashflow', [['true', 'ja'], ['false', 'nein']])}
    <h4>Wert & Verkauf</h4>${inp('wertentwicklung_prozent', 'Wertentwicklung % p.a.', 'number', {step: '0.1', hq: 'immo_wert'})}${inp('verkauf.jahr', 'Verkaufsjahr (optional)', 'number', {step: '1', hq: 'immo_verkauf'})}${inp('verkauf.kosten_prozent', 'Verkaufskosten %', 'number', {step: '0.1'})}</div>
    <h4 style="margin:12px 0 2px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)">Finanzierung</h4><div id="im-loans">${(e.darlehen || []).map((l, i) => loanBox(l, i, im, konten)).join('')}</div><div class="row tight"><button id="im-loan-add" class="small secondary">Darlehen hinzufügen</button></div>
    <div class="actions"><button id="im-calc" class="small secondary">Neu berechnen</button><label class="chk small">Szenario-Name <input type="text" id="im-kalk-name" value="${esc(k ? k.name : 'Kalkulation')}" style="width:160px"></label><button id="im-kalk-save" class="small">Speichern</button></div><div id="im-err" class="findings"></div></div>
    <div id="im-result">${IM.res ? immoResultHtml(IM.res) : '<div class="card"><div class="muted">Berechnung läuft …</div></div>'}</div></div>`;
  return h;
}
function loanBox(l, i, im, konten) {
  const p = k => `darlehen.${i}.${k}`;
  const v = k => l[k] == null ? '' : esc(l[k]);
  const ref = (im.darlehen_konten || {})[l.name] || '';
  const st = (l.sondertilgungen || []).map(x => `${x.datum ? String(x.datum).slice(0, 7) : ''}: ${x.betrag}`).join('; ');
  return `<div class="loan-box" data-loan="${i}"><div class="immo-form">
    <label>Bezeichnung</label><input type="text" data-p="${p('name')}" value="${v('name')}">
    <label>Betrag €</label><input type="number" step="1000" data-p="${p('betrag')}" value="${v('betrag')}">
    <label>Zins % p.a.</label><input type="number" step="0.01" data-p="${p('zins_prozent')}" value="${v('zins_prozent')}">
    <label>Art ${hq('immo_darlehen_art')}</label><select data-p="${p('art')}">${[['annuitaet', 'Annuität'], ['tilgung', 'Tilgungsdarlehen'], ['endfaellig', 'endfällig']].map(([a, b]) => `<option value="${a}" ${l.art === a ? 'selected' : ''}>${b}</option>`).join('')}</select>
    <label>Annuität / Monat €</label><input type="number" step="0.01" data-p="${p('annuitaet_monat')}" value="${v('annuitaet_monat')}" placeholder="oder Anfangstilgung">
    <label>Anfangstilgung % p.a.</label><input type="number" step="0.01" data-p="${p('anfangstilgung_prozent')}" value="${v('anfangstilgung_prozent')}">
    <label>Tilgung / Monat € (Tilgungsdarlehen)</label><input type="number" step="1" data-p="${p('tilgung_monat')}" value="${v('tilgung_monat')}">
    <label>Sondertilgung / Monat € ${hq('immo_sonder')}</label><input type="number" step="1" data-p="${p('sondertilgung_monat')}" value="${v('sondertilgung_monat')}">
    <label>… ab Monat</label><input type="month" data-p="${p('sondertilgung_ab')}" value="${l.sondertilgung_ab ? String(l.sondertilgung_ab).slice(0, 7) : ''}">
    <label>Einzelne Sondertilgungen</label><input type="text" data-p="${p('sondertilgungen')}" data-kind="st" value="${esc(st)}" placeholder="2027-06: 50000; 2028-06: 50000">
    <label>Zinsbindung bis ${hq('immo_zinsbindung')}</label><input type="month" data-p="${p('zinsbindung_bis')}" value="${l.zinsbindung_bis ? String(l.zinsbindung_bis).slice(0, 7) : ''}">
    <label>Anschlusszins % p.a.</label><input type="number" step="0.01" data-p="${p('anschluss_zins_prozent')}" value="${v('anschluss_zins_prozent')}">
    <label>Fälligkeit ${hq('immo_faellig')}</label><input type="month" data-p="${p('faelligkeit')}" value="${l.faelligkeit ? String(l.faelligkeit).slice(0, 7) : ''}">
    <label>Bei Fälligkeit</label><select data-p="${p('faelligkeit_art')}">${[['offen', 'offen (Hinweis)'], ['rueckzahlung', 'Rückzahlung aus Liquidität']].map(([a, b]) => `<option value="${a}" ${(l.faelligkeit_art || 'offen') === a ? 'selected' : ''}>${b}</option>`).join('')}</select>
    <label>Beginn (Auszahlung)</label><input type="month" data-p="${p('beginn')}" value="${l.beginn ? String(l.beginn).slice(0, 7) : ''}" placeholder="= Übergang">
    <label>Abrechnung ${hq('immo_abrechnung')}</label><select data-p="${p('abrechnung')}">${[['monatlich', 'monatlich (Bank)'], ['jaehrlich', 'jährlich (Stand 1.1.)']].map(([a, b]) => `<option value="${a}" ${(l.abrechnung || 'monatlich') === a ? 'selected' : ''}>${b}</option>`).join('')}</select>
    <label>Zinsen abziehbar ${hq('immo_abziehbar')}</label><select data-p="${p('abziehbar')}"><option value="true" ${l.abziehbar !== false ? 'selected' : ''}>ja</option><option value="false" ${l.abziehbar === false ? 'selected' : ''}>nein</option></select>
    <label>Darlehenskonto in MoneyMoney ${hq('immo_darlehen_konten')}</label><select class="im-loan-konto" data-loan-name="${esc(l.name || '')}">${acctOptions(ref, x => !x.gruppe)}</select>
  </div><div class="row tight"><button class="ghost small im-loan-del" data-i="${i}">Darlehen entfernen</button></div></div>`;
}
function get(o, path) { return path.split('.').reduce((a, k) => (a == null ? undefined : a[k]), o); }
function setp(o, path, v) { const ks = path.split('.'); let a = o; for (let i = 0; i < ks.length - 1; i++) { const k = ks[i]; if (a[k] == null) a[k] = /^\d+$/.test(ks[i + 1]) ? [] : {}; a = a[k]; } a[ks[ks.length - 1]] = v; }
function immoResultHtml(r) {
  const K = r.kennzahlen, J = r.jahre;
  const pct = x => x == null ? '–' : (x * 100).toFixed(2) + ' %';
  const kp = (l, v) => `<div class="k"><div class="l">${l}</div><div class="v">${v}</div></div>`;
  let h = `<div class="card"><h3>Kennzahlen</h3><div class="kpis">${kp('Gesamtinvestition', F0(K.gesamtinvestition) + ' €')}${kp('Eigenkapital inkl. NK', F0(K.eigenkapital_inkl_nk) + ' €')}${kp('Fremdkapital (LTV)', F0(K.darlehen) + ' € (' + pct(K.ltv) + ')')}${kp('Kaufpreisfaktor', K.kaufpreisfaktor ?? '–')}${kp('Bruttomietrendite', pct(K.bruttomietrendite))}${kp('Nettomietrendite', pct(K.nettomietrendite))}${kp('Cashflow Jahr 1', F0(K.cashflow_jahr1) + ' €')}${kp('Cash-on-Cash', pct(K.cash_on_cash))}${kp('DSCR Jahr 1', K.dscr_jahr1 ?? '–')}${kp('AfA p.a.', F0(K.afa_jahr) + ' € (' + (K.afa_satz || 0).toFixed(2) + ' % auf ' + F0(K.afa_basis) + ')')}${kp('Kapitaldienst / Monat', F0(K.kapitaldienst_monat) + ' €')}${kp('IRR bis ' + (K.exit_jahr || '–'), pct(K.irr))}${K.preis_qm ? kp('Preis / m²', F0(K.preis_qm) + ' €') : ''}${K.miete_qm ? kp('Miete / m²', F(K.miete_qm) + ' €') : ''}</div>
    ${(r.hinweise || []).map(x => `<div class="banner" style="margin:4px 0">${esc(x)}</div>`).join('')}
    ${(K.mietanpassungen || []).length ? '<div class="small muted">Mietanpassungen: ' + K.mietanpassungen.slice(0, 6).map(a => a.jahr + ': +' + a.erhoehung_prozent + ' % → ' + F0(a.nkm_neu) + ' €').join(' · ') + (K.mietanpassungen.length > 6 ? ' …' : '') + '</div>' : ''}
    ${immoChart(J)}</div>
    <div class="card" style="margin-top:12px"><h3>Erste Jahre</h3><div class="wrap auto"><table class="plain"><thead><tr><th>Jahr</th><th class="num">Miete</th><th class="num">Kosten</th><th class="num">Zinsen</th><th class="num">Tilgung</th><th class="num">AfA</th><th class="num">Ergebnis</th><th class="num">Steuer</th><th class="num">Cashflow</th><th class="num">Vermögensaufbau</th><th class="num">EK-Rendite</th><th class="num">Restschuld</th></tr></thead><tbody>`
    + J.slice(0, 12).map(j => `<tr><td>${j.jahr}${j.monate < 12 ? ' <span class="muted small">(' + j.monate + ' Mon.)</span>' : ''}</td><td class="num">${F0(j.miete)}</td><td class="num">${F0(j.kosten + j.ruecklage)}</td><td class="num">${F0(j.zins)}</td><td class="num">${F0(j.tilgung + j.sondertilgung)}</td><td class="num">${F0(j.afa)}</td><td class="num ${j.ergebnis < 0 ? 'neg' : 'pos'}">${F0(j.ergebnis)}</td><td class="num">${F0(j.steuer)}</td><td class="num ${j.cashflow < 0 ? 'neg' : 'pos'}">${F0(j.cashflow)}</td><td class="num">${F0(j.vermoegensaufbau)}</td><td class="num">${j.ek_rendite == null ? '–' : (j.ek_rendite * 100).toFixed(1) + ' %'}</td><td class="num">${F0(j.restschuld)}</td></tr>`).join('') + '</tbody></table></div></div>';
  return h;
}
function immoChart(J) {
  if (!J.length) return '';
  const W = 560, H = 200, P = {l: 56, r: 56, t: 10, b: 24}, n = J.length, bw = (W - P.l - P.r) / n;
  const cfs = J.map(j => j.cashflow), rs = J.map(j => j.restschuld), ws = J.map(j => j.wert);
  const cmax = Math.max(...cfs, 1) * 1.1, cmin = Math.min(...cfs, 0) * 1.1, rmax = Math.max(...rs, ...ws, 1) * 1.05;
  const yc = v => P.t + (cmax - v) * (H - P.t - P.b) / ((cmax - cmin) || 1), yr = v => P.t + (rmax - v) * (H - P.t - P.b) / rmax, x = i => P.l + i * bw;
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}">`;
  for (const t of niceTicks(cmin, cmax, 4)) s += `<line x1="${P.l}" x2="${W - P.r}" y1="${yc(t)}" y2="${yc(t)}" stroke="var(--line)"/><text x="${P.l - 6}" y="${yc(t) + 4}" text-anchor="end">${Fk(t)}</text>`;
  cfs.forEach((v, i) => { s += `<rect x="${(x(i) + bw * 0.15).toFixed(1)}" y="${Math.min(yc(v), yc(0)).toFixed(1)}" width="${(bw * 0.7).toFixed(1)}" height="${Math.abs(yc(v) - yc(0)).toFixed(1)}" fill="${v < 0 ? 'var(--c-aus)' : 'var(--c-ein)'}" rx="2"/>`; if (i % Math.ceil(n / 8) === 0) s += `<text x="${(x(i) + bw / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle">${J[i].jahr}</text>`; });
  s += `<path d="${rs.map((v, i) => (i ? 'L' : 'M') + (x(i) + bw / 2).toFixed(1) + ' ' + yr(v).toFixed(1)).join(' ')}" fill="none" stroke="var(--c-verb)" stroke-width="2"/>`;
  s += `<path d="${ws.map((v, i) => (i ? 'L' : 'M') + (x(i) + bw / 2).toFixed(1) + ' ' + yr(v).toFixed(1)).join(' ')}" fill="none" stroke="#b8860b" stroke-width="2" stroke-dasharray="4 3"/>`;
  for (const t of niceTicks(0, rmax, 4)) s += `<text x="${W - P.r + 6}" y="${yr(t) + 4}">${Fk(t)}</text>`;
  return s + '</svg><div class="chart-legend"><span><i style="background:var(--c-ein)"></i>Cashflow je Jahr (links)</span><span><i style="background:var(--c-verb)"></i>Restschuld (rechts)</span><span><i style="background:#b8860b"></i>Objektwert (rechts)</span></div>';
}
function vImmoJahre(d) {
  const J = d.jahre || []; if (!J.length) return '<div class="note">Keine Kalkulation vorhanden oder Bericht noch nicht aktualisiert.</div>';
  const names = d.darlehen_namen || [];
  let h = `<div class="toolbar"><span class="muted small">Aktive Kalkulation „${esc(d.name || '')}“ · alle Jahre</span><span class="sp"></span>${xlsxBtn('property', `data-immo="${esc(d.id)}"`)}</div><div class="wrap"><table><thead><tr><th>Jahr</th>${['Miete', 'Umlage', 'Kosten', 'Rücklage', 'Zinsen', 'Tilgung', 'Sondertilgung', 'AfA', 'Ergebnis', 'Steuer', 'Ergebnis n. St.', 'Ausschüttung', 'Cashflow', 'Cashflow kum.', 'Vermögensaufbau', 'EK-Rendite', 'Restschuld', 'Objektwert', 'EK im Objekt', 'DSCR', 'NKM/Monat'].map(x => `<th>${x}</th>`).join('')}${names.map(n => `<th>${esc(n)} Zins</th><th>${esc(n)} Tilgung</th><th>${esc(n)} Saldo</th>`).join('')}</tr></thead><tbody>`;
  const c = v => `<td class="${v == null ? 'zero' : v < 0 ? 'neg' : 'pos'}">${v == null ? '–' : F(v)}</td>`;
  for (const j of J) h += `<tr><td>${j.jahr}${j.monate < 12 ? ' (' + j.monate + ' Mon.)' : ''}</td>${[j.miete, j.umlage, j.kosten, j.ruecklage, j.zins, j.tilgung, j.sondertilgung, j.afa, j.ergebnis, j.steuer, j.ergebnis_nach_steuern, j.ausschuettung, j.cashflow, j.cashflow_kumuliert, j.vermoegensaufbau].map(c).join('')}<td>${j.ek_rendite == null ? '–' : (j.ek_rendite * 100).toFixed(2) + ' %'}</td>${[j.restschuld, j.wert, j.eigenkapital_objekt].map(c).join('')}<td>${j.dscr ?? '–'}</td>${c(j.nkm_monat)}${names.map(n => c(j.darlehen[n].zins) + c(j.darlehen[n].tilgung) + c(j.darlehen[n].saldo)).join('')}</tr>`;
  h += '</tbody></table></div>';
  return h;
}
function vImmoSollIst(d) {
  const rows = d.soll_ist || [];
  if (!rows.length) return '<div class="note">Für Soll/Ist braucht das Objekt eine Vermietungskategorie und/oder verknüpfte Darlehenskonten – und Umsätze in MoneyMoney in den Kalkulationsjahren.</div>';
  const c = (v, cls2 = '') => `<td class="num ${cls2}">${v == null ? '–' : F0(v)}</td>`;
  const dv = (soll, ist) => ist == null || soll == null ? '<td></td>' : `<td class="num ${ist - soll >= 0 ? 'pos' : 'neg'}">${F0(ist - soll)}</td>`;
  return `<div class="wrap auto"><table class="plain"><thead><tr><th>Jahr</th><th class="num">Miete Soll</th><th class="num">Miete Ist</th><th class="num">Δ</th><th class="num">Kosten Soll</th><th class="num">Kosten Ist</th><th class="num">Δ</th><th class="num">Zinsen Soll</th><th class="num">Zinsen Ist</th><th class="num">Δ</th><th class="num">Restschuld Soll</th><th class="num">Restschuld Ist</th><th class="num">Δ</th></tr></thead><tbody>`
    + rows.map(r => `<tr><td>${r.jahr}</td>${c(r.miete_soll)}${c(r.miete_ist)}${dv(r.miete_soll, r.miete_ist)}${c(r.kosten_soll)}${c(r.kosten_ist)}${dv(r.kosten_soll, r.kosten_ist)}${c(r.zins_soll)}${c(r.zins_ist)}${dv(r.zins_soll, r.zins_ist)}${c(r.restschuld_soll)}${c(r.restschuld_ist)}${dv(r.restschuld_soll, r.restschuld_ist)}</tr>`).join('')
    + '</tbody></table></div><div class="note">Ist = kategorisierte Umsätze der Vermietungskategorie (Einnahmen positiv, Kosten negativ) und Zinsbuchungen der verknüpften Darlehenskonten; laufendes Jahr unvollständig.</div>';
}
function vImmoDokumente(im) {
  const docs = im.dokumente || [];
  let h = `<div class="note">${H.dokumente}</div><div class="card">${docs.map(d => `<div class="doc" data-id="${esc(d.id)}"><div class="n"><b>${esc(d.titel)}</b>${d.art ? ' <span class="tag">' + esc(d.art) + '</span>' : ''}<div class="p" title="${esc(d.pfad)}">${esc(d.pfad)}</div></div><span class="small muted">${esc(d.hinzugefuegt || '')}</span>${S.STATUS.lokal ? `<button class="ghost small doc-open">Öffnen</button><button class="ghost small doc-show">Finder</button>` : ''}<button class="ghost small doc-del">✕</button></div>`).join('') || '<div class="muted small">Noch keine Dokumente verknüpft.</div>'}
    <div class="row tight" style="margin-top:10px"><input type="text" id="doc-titel" placeholder="Titel (z. B. Kaufvertrag)" style="width:200px"><input type="text" id="doc-art" placeholder="Art (Vertrag, Gutachten …)" style="width:160px"><input type="text" id="doc-pfad" placeholder="Pfad auf dem Mac" style="min-width:260px;flex:1">${S.STATUS.lokal ? '<button id="doc-pick" class="small secondary">Datei wählen …</button>' : ''}<button id="doc-add" class="small">Verknüpfen</button></div></div>`;
  return h;
}
async function immoCalc() {
  if (!IM.edit) return;
  try { IM.res = await api('/api/properties/calculate', {eingaben: IM.edit, ohne_monate: true}); const el = $('#im-result'); if (el) el.innerHTML = immoResultHtml(IM.res); const er = $('#im-err'); if (er) er.innerHTML = ''; }
  catch (e) { const el = $('#im-err'); if (el) el.innerHTML = `<div class="fehler">${esc(e.message)}</div>`; }
}
function bindImmo(main) {
  $$('.card[data-im]', main).forEach(c => c.addEventListener('click', () => { location.hash = '#immobilien/' + c.dataset.im; }));
  const nw = $('#im-new', main); if (nw) nw.addEventListener('click', async () => { const name = prompt('Name des Objekts:'); if (!name) return; const b = S.bereich || ((S.CFG.bereiche || [])[0] || {}).id || ''; try { const r = await api('/api/properties', {aktion: 'anlegen', name, bereich: b}); S.CFG = await api('/api/config'); location.hash = '#immobilien/' + r.immobilie.id; } catch (e) { toast(e.message, 5000); } });
  const id = (location.hash.split('/')[1] || '').split('?')[0]; if (!id) return;
  const im = immoOf(id); if (!im) return;
  $$('.tabs button[data-t]', main).forEach(b => b.addEventListener('click', () => { IM.tab = b.dataset.t; route(); }));
  const del = $('#im-del', main); if (del) del.addEventListener('click', async () => { if (!confirm('Objekt „' + im.name + '“ mit allen Kalkulationen löschen?')) return; await api('/api/properties', {aktion: 'loeschen', id}); S.CFG = await api('/api/config'); location.hash = '#immobilien'; });
  const sm = $('#im-save-meta', main); if (sm) sm.addEventListener('click', async () => { try { await api('/api/properties', {aktion: 'aendern', id, name: $('#im-name').value, bereich: $('#im-bereich').value, kategorie: $('#im-kat').value, objekt_konto: $('#im-konto').value, in_planung: $('#im-plan').checked, notizen: $('#im-notiz').value}); toast('Gespeichert'); await loadAll(); route(); } catch (e) { toast(e.message, 5000); } });
  const ks = $('#im-kalk', main); if (ks) ks.addEventListener('change', e => { IM.kalk = e.target.value; IM.edit = null; route(); });
  const kn = $('#im-kalk-new', main); if (kn) kn.addEventListener('click', async () => {
    let eing = IM.edit ? JSON.parse(JSON.stringify(IM.edit)) : (await api('/api/properties/template')).eingaben;
    if (!IM.edit) { eing.name = im.name; if (S.DATA && S.DATA.bereich_info && S.DATA.bereich_info[im.bereich] && S.DATA.bereich_info[im.bereich].art === 'privat') eing.gesellschafter = [{name: 'Eigentümer', anteil_prozent: 100, steuersatz_prozent: 42}]; }
    const name = prompt('Name des Szenarios:', IM.edit ? 'Variante' : 'Basis'); if (!name) return;
    try { const r = await api('/api/properties', {aktion: 'kalkulation_speichern', id, kalkulation: {name, eingaben: eing}}); S.CFG = await api('/api/config'); IM.kalk = r.immobilie.kalkulationen[r.immobilie.kalkulationen.length - 1].id; IM.edit = null; await loadAll(); route(); } catch (e) { toast(e.message, 6000); } });
  const ka = $('#im-kalk-aktiv', main); if (ka) ka.addEventListener('click', async () => { await api('/api/properties', {aktion: 'kalkulation_aktiv', id, kalkulation_id: IM.kalk}); await loadAll(); route(); });
  const kd = $('#im-kalk-del', main); if (kd) kd.addEventListener('click', async () => { if (!confirm('Szenario löschen?')) return; await api('/api/properties', {aktion: 'kalkulation_loeschen', id, kalkulation_id: IM.kalk}); IM.kalk = null; IM.edit = null; await loadAll(); route(); });
  // Eingaben binden
  $$('[data-p]', main).forEach(inp => inp.addEventListener('input', () => {
    let v = inp.value;
    if (inp.dataset.kind === 'st') { v = v.split(';').map(x => x.trim()).filter(Boolean).map(x => { const [d, b] = x.split(':'); return {datum: (d || '').trim(), betrag: parseFloat((b || '0').replace(',', '.')) || 0}; }); }
    else if (inp.type === 'number') v = v === '' ? null : parseFloat(v.replace(',', '.'));
    else if (v === 'true') v = true; else if (v === 'false') v = false;
    setp(IM.edit, inp.dataset.p, v);
    clearTimeout(IM.timer); IM.timer = setTimeout(immoCalc, 600);
  }));
  const la = $('#im-loan-add', main); if (la) la.addEventListener('click', () => { IM.edit.darlehen = IM.edit.darlehen || []; IM.edit.darlehen.push({name: 'Darlehen ' + (IM.edit.darlehen.length + 1), betrag: 0, zins_prozent: 3.5, art: 'annuitaet', abrechnung: 'monatlich', abziehbar: true}); route(); });
  $$('.im-loan-del', main).forEach(b => b.addEventListener('click', () => { IM.edit.darlehen.splice(+b.dataset.i, 1); route(); }));
  const ga = $('#im-ges-add', main); if (ga) ga.addEventListener('click', () => { IM.edit.gesellschafter = IM.edit.gesellschafter || []; IM.edit.gesellschafter.push({name: '', anteil_prozent: 0, steuersatz_prozent: 42}); route(); });
  $$('.im-ges-del', main).forEach(b => b.addEventListener('click', () => { IM.edit.gesellschafter.splice(+b.dataset.i, 1); route(); }));
  const cb = $('#im-calc', main); if (cb) cb.addEventListener('click', immoCalc);
  const sv = $('#im-kalk-save', main); if (sv) sv.addEventListener('click', async () => {
    const dk = {}; $$('.im-loan-konto', main).forEach(sel => { const name = sel.closest('.loan-box').querySelector('[data-p$=".name"]').value; if (sel.value) dk[name] = sel.value; });
    try { await api('/api/properties', {aktion: 'aendern', id, darlehen_konten: dk}); await api('/api/properties', {aktion: 'kalkulation_speichern', id, kalkulation: {id: IM.kalk, name: $('#im-kalk-name').value, eingaben: IM.edit}}); toast('Kalkulation gespeichert'); await loadAll(); route(); } catch (e) { $('#im-err').innerHTML = `<div class="fehler">${esc(e.message)}</div>`; } });
  if (IM.edit && !IM.res) immoCalc();
  // Dokumente
  const dp = $('#doc-pick', main); if (dp) dp.addEventListener('click', async () => { toast('Dateiauswahl am Mac geöffnet …', 4000); try { const r = await api('/api/file/choose', {art: 'datei', prompt: 'Dokument für ' + im.name}); if (r.ok) { $('#doc-pfad').value = r.pfad; if (!$('#doc-titel').value) $('#doc-titel').value = r.name.replace(/\.[^.]+$/, ''); } else toast(r.text); } catch (e) { toast(e.message, 5000); } });
  const da = $('#doc-add', main); if (da) da.addEventListener('click', async () => { try { await api('/api/properties', {aktion: 'dokument_hinzufuegen', id, titel: $('#doc-titel').value, art: $('#doc-art').value, pfad: $('#doc-pfad').value}); S.CFG = await api('/api/config'); route(); } catch (e) { toast(e.message, 5000); } });
  $$('.doc-del', main).forEach(b => b.addEventListener('click', async e => { const did = e.target.closest('.doc').dataset.id; await api('/api/properties', {aktion: 'dokument_entfernen', id, dokument_id: did}); S.CFG = await api('/api/config'); route(); }));
  $$('.doc-open', main).forEach(b => b.addEventListener('click', async e => { const did = e.target.closest('.doc').dataset.id; const d = (im.dokumente || []).find(x => x.id === did); try { const r = await api('/api/file/open', {pfad: d.pfad}); if (r.status === 'icloud') toast('Datei liegt in iCloud und wird geladen …', 5000); } catch (er) { toast(er.message, 5000); } }));
  $$('.doc-show', main).forEach(b => b.addEventListener('click', async e => { const did = e.target.closest('.doc').dataset.id; const d = (im.dokumente || []).find(x => x.id === did); try { await api('/api/file/reveal', {pfad: d.pfad}); } catch (er) { toast(er.message, 5000); } }));
}

// ---------------------------------------------------------------- Depots
function vDepots() {
  const dep = (S.DATA && S.DATA.depots) || [];
  let h = `<div class="toolbar"><span class="muted small">Bestände aus MoneyMoney (Stand des letzten Laufs)</span><span class="sp"></span>${xlsxBtn('holdings')}</div>`;
  if (!dep.length) return h + '<div class="note">Keine Depots in den gewählten Bereichen – oder MoneyMoney liefert für diese Konten keine Positionen.</div>';
  h += '<div class="cards">' + dep.map(d => `<div class="card"><div class="l">${esc(d.name)}<span class="tag">${esc(d.entitaet)}</span></div><div class="v">${F0(d.summe)} €</div><div class="d">Einstand ${F0(d.einstand)} € · ${d.einstand ? `<span class="delta ${d.summe - d.einstand >= 0 ? 'pos' : 'neg'}">${d.summe - d.einstand >= 0 ? '+' : ''}${F0(d.summe - d.einstand)} € (${((d.summe / d.einstand - 1) * 100).toFixed(1)} %)</span>` : ''}</div></div>`).join('') + '</div>';
  for (const d of dep) {
    h += `<h2>${esc(d.name)} <span class="x">${d.positionen.length} Positionen</span></h2><div class="wrap auto"><table class="plain"><thead><tr><th>Position</th><th>ISIN</th><th>Klasse</th><th class="num">Menge</th><th class="num">Kurs</th><th class="num">Einstand</th><th class="num">Wert</th><th class="num">Anteil</th><th class="num">G/V</th></tr></thead><tbody>`
      + d.positionen.map(p => `<tr><td>${esc(p.name)}</td><td class="mono small">${esc(p.isin)}</td><td>${esc(p.klasse)}</td><td class="num">${p.menge.toLocaleString('de-DE', {maximumFractionDigits: 4})}</td><td class="num">${F(p.kurs)}</td><td class="num">${F(p.einstand)}</td><td class="num">${F(p.wert)}</td><td class="num">${d.summe ? (p.wert / d.summe * 100).toFixed(1) + ' %' : ''}</td><td class="num ${p.wert - p.einstand >= 0 ? 'pos' : 'neg'}">${p.einstand ? F(p.wert - p.einstand) : ''}</td></tr>`).join('') + '</tbody></table></div>';
  }
  return h;
}

// ---------------------------------------------------------------- Umsaetze & Belege
let UMS = {umsaetze: [], treffer: 0, gesamt: 0, jahre: []};
async function loadUms() {
  const f = S.uf, q = new URLSearchParams();
  const P = {entitaet: 'entity', jahr: 'year', konto: 'account', q: 'q'};
  for (const k in P) if (f[k]) q.set(P[k], f[k]);
  if (f.richtung) q.set('direction', f.richtung === 'aus' ? 'out' : 'in');
  if (f.ohne_beleg) q.set('without_receipt', '1'); if (f.ohne_kategorie) q.set('uncategorized', '1');
  q.set('limit', '400');
  UMS = await api('/api/transactions?' + q.toString());
}
async function vUmsaetze() {
  if (!S.DATA) return noData;
  await loadUms();
  const f = S.uf, st = S.STATUS, konten = S.DATA.konten.filter(k => !k.gruppe && (!f.entitaet || k.pfad.startsWith(BN(f.entitaet))));
  const catAllowed = st.lokal && st.moneymoney.kategorisieren_erlaubt;
  let h = `<div class="toolbar">
    <select id="uf-ent"><option value="">alle Bereiche</option>${Object.keys(S.DATA.bereiche).map(k => `<option value="${k}" ${f.entitaet === k ? 'selected' : ''}>${esc(BN(k))}</option>`).join('')}</select>
    <select id="uf-jahr"><option value="">alle Jahre</option>${UMS.jahre.map(y => `<option ${f.jahr === y ? 'selected' : ''}>${y}</option>`).join('')}</select>
    <select id="uf-konto"><option value="">alle Konten</option>${konten.map(k => `<option value="${k.uuid}" ${f.konto === k.uuid ? 'selected' : ''}>${esc(k.name)}</option>`).join('')}</select>
    <input type="search" id="uf-q" placeholder="Suche (Name, Zweck, Kategorie, Betrag)" value="${esc(f.q)}" style="min-width:220px">
    <div class="seg"><button data-r="" class="${!f.richtung ? 'on' : ''}">alle</button><button data-r="aus" class="${f.richtung === 'aus' ? 'on' : ''}">Ausgaben</button><button data-r="ein" class="${f.richtung === 'ein' ? 'on' : ''}">Einnahmen</button></div>
    <label class="switch"><input type="checkbox" id="uf-ob" ${f.ohne_beleg ? 'checked' : ''}><i></i>ohne Beleg</label>
    <label class="switch"><input type="checkbox" id="uf-ok" ${f.ohne_kategorie ? 'checked' : ''}><i></i>ohne Kategorie</label>
  </div>
  <div class="toolbar"><span class="muted small">${UMS.treffer} Treffer${UMS.treffer > UMS.umsaetze.length ? ' (erste ' + UMS.umsaetze.length + ' angezeigt – Filter verfeinern)' : ''} von ${UMS.gesamt} Umsätzen · Klick auf eine Zeile öffnet Details und Belege · Dateien lassen sich direkt auf eine Zeile ziehen</span><span class="sp"></span>
    <button id="bl-folder" class="secondary small" ${st.lokal ? '' : 'disabled title="nur am Mac"'}>Belegordner öffnen</button>
    <button id="bl-export" class="secondary small">Belege exportieren (ZIP)</button>
    ${xlsxBtn('transactions', f.entitaet ? `data-bereich="${f.entitaet}"` : '')} ${xlsxBtn('receipts')}</div>`;
  if (S.sel.size) h += `<div class="banner info" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">${S.sel.size} ausgewählt ${catAllowed ? `<select id="bulk-cat">${catOptions('')}</select><button id="bulk-cat-btn" class="small">Kategorie zuweisen</button>` : '<span class="small">Kategorisieren aus Kontor ist in den Einstellungen nicht erlaubt (oder nicht am Mac).</span>'}<button id="bulk-clear" class="small secondary">Auswahl aufheben</button></div>`;
  h += '<div class="wrap"><table class="plain" id="ums-table"><thead><tr><th style="width:28px"><input type="checkbox" id="sel-all"></th><th>Datum</th><th>Konto</th><th>Name</th><th>Verwendungszweck</th><th class="num">Betrag</th><th>Kategorie</th><th class="num">Belege</th></tr></thead><tbody>'
    + UMS.umsaetze.map(u => `<tr class="clickable ${S.sel.has(u.id) ? 'sel' : ''}" data-id="${u.id}"><td><input type="checkbox" class="sel" ${S.sel.has(u.id) ? 'checked' : ''}></td><td class="small" style="white-space:nowrap">${FD(u.datum)}</td><td class="small">${esc(u.konto_name)}</td><td>${esc(u.name)}</td><td class="small muted" style="max-width:360px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(u.zweck)}</td><td class="num ${u.betrag < 0 ? 'neg' : 'pos'}">${F(u.betrag)}</td><td class="small" title="${u.quelle === 'regel' ? 'per Kontor-Regel' : u.quelle === 'manuell' ? 'in Kontor zugeordnet' : u.quelle === 'moneymoney' ? 'aus MoneyMoney' : ''}">${u.kategorie ? esc(u.kategorie) + (u.quelle === 'regel' ? ' <span class="muted">R</span>' : u.quelle === 'manuell' ? ' <span class="muted">K</span>' : '') : '<span class="pill warn">ohne</span>'}</td><td class="num">${u.belege ? `<span class="pill ok">${u.belege}</span>` : `<button class="ghost small add-beleg" title="Beleg hinzufügen">＋</button>`}</td></tr>`).join('')
    + '</tbody></table></div>';
  return h;
}
async function openDrawer(txId) {
  const u = UMS.umsaetze.find(x => x.id === txId); if (!u) return;
  S.drawerTx = txId;
  const [bl] = await Promise.all([api('/api/receipts?files=1'), KZ.kat ? Promise.resolve() : loadKat().catch(() => null)]);
  const mine = bl.eintraege.filter(e => e.tx_id === txId), free = bl.dateien.filter(d => !d.verknuepft);
  const st = S.STATUS, catAllowed = st.lokal && st.moneymoney.kategorisieren_erlaubt;
  const d = $('#drawer');
  const QUELLE = {manuell: 'in Kontor zugeordnet', regel: 'per Kontor-Regel', moneymoney: 'aus MoneyMoney', '': ''};
  d.innerHTML = `<button class="close icon">✕</button><h2>${esc(u.name)}</h2>
    <div class="kv"><div>Datum</div><div>${FD(u.datum)}</div><div>Betrag</div><div class="${u.betrag < 0 ? 'neg' : 'pos'}" style="font-weight:600;color:var(--${u.betrag < 0 ? 'neg' : 'pos'})">${F(u.betrag)} €</div><div>Konto</div><div>${esc(u.konto_name)} · ${esc(BN(u.entitaet))}</div><div>Zweck</div><div>${esc(u.zweck) || '–'}</div><div>Kategorie</div><div>${esc(u.kategorie) || '<span class="pill warn">ohne</span>'}${u.quelle ? ' <span class="small muted">· ' + QUELLE[u.quelle] + '</span>' : ''}</div><div>Status</div><div>${u.gebucht ? 'gebucht' : 'vorgemerkt'}${u.haken ? ' · abgehakt' : ''}</div><div>ID</div><div class="mono small">${u.id}</div></div>
    <div class="row tight" style="margin-top:10px"><input type="text" id="dr-kat" list="dr-kats" value="${esc(u.kategorie || '')}" placeholder="Kategorie in Kontor (neu = anlegen)" style="min-width:240px;flex:1">${katList('dr-kats')}<label class="chk small"><input type="checkbox" id="dr-rule"> Regel für „${esc((u.name || '').slice(0, 24))}“</label>${catAllowed ? '<label class="chk small"><input type="checkbox" id="dr-mm"> auch in MoneyMoney</label>' : ''}<button id="dr-cat-btn" class="small">Zuordnen</button></div>
    <h3>Belege (${mine.length})</h3>
    ${mine.map(e => `<div class="beleg" data-id="${e.id}"><span class="n" title="${esc(e.pfad)}">${e.extern ? '<span class="tag" title="Verknüpfung zu einer Datei außerhalb des Belegordners">Mac</span>' : ''}${esc(e.pfad.split('/').pop())}</span><span class="small muted">${e.extern ? (e.status === 'icloud' ? '<span class="pill warn">iCloud, nicht geladen</span>' : e.status === 'fehlt' ? '<span class="pill err">fehlt</span>' : '') : (e.groesse / 1024).toFixed(0) + ' KB'}</span><a href="/api/receipts/file?id=${e.id}" target="_blank" class="small">ansehen</a>${st.lokal ? `<button class="ghost small bl-show" title="im Finder zeigen">Finder</button>` : ''}<button class="ghost small bl-note" title="Notiz">✎</button><button class="ghost small bl-del" title="${e.extern ? 'Verknüpfung entfernen (Datei bleibt)' : 'Zuordnung entfernen'}">✕</button></div>${e.notiz ? `<div class="small muted" style="padding:0 0 6px">${esc(e.notiz)}</div>` : ''}`).join('') || '<div class="muted small">Noch kein Beleg.</div>'}
    <div class="drop" id="dr-drop" style="margin-top:12px">Datei hierher ziehen<br><button id="dr-pick" class="small" style="margin-top:8px">Datei wählen</button> <button id="dr-cam" class="small secondary" style="margin-top:8px">Foto aufnehmen</button><div class="small muted" style="margin-top:6px">PDF, Bilder, E-Mails, Office-Dateien bis 60 MB. Ablage als Datei im Belegordner, Name: Datum_Betrag_Name_Kennung.</div></div>
    ${free.length ? `<h3>Vorhandene Datei aus dem Belegordner zuordnen</h3><div class="row tight"><select id="dr-free" style="max-width:300px">${free.map(x => `<option value="${esc(x.pfad)}">${esc(x.pfad)}</option>`).join('')}</select><button id="dr-link" class="small secondary">Zuordnen</button></div>` : ''}
    <h3>Datei auf dem Mac verknüpfen ${hq('dokumente')}</h3><div class="row tight"><input type="text" id="dr-ext" placeholder="Pfad, z. B. ~/Library/Mobile Documents/com~apple~CloudDocs/Verträge/Kaufvertrag.pdf" style="flex:1;min-width:220px">${st.lokal ? '<button id="dr-ext-pick" class="small secondary">Datei wählen …</button>' : ''}<button id="dr-ext-link" class="small secondary">Verknüpfen</button></div><div class="small muted">Die Datei bleibt, wo sie liegt (auch iCloud Drive); Kontor speichert nur den Pfad.</div>`;
  d.classList.add('open');
  $('.close', d).onclick = closeDrawer;
  $('#dr-pick', d).onclick = () => pickFiles(txId, false);
  $('#dr-cam', d).onclick = () => pickFiles(txId, true);
  const dz = $('#dr-drop', d);
  dz.ondragover = e => { e.preventDefault(); dz.classList.add('over'); }; dz.ondragleave = () => dz.classList.remove('over');
  dz.ondrop = async e => { e.preventDefault(); dz.classList.remove('over'); await uploadFiles(txId, e.dataTransfer.files); };
  const lk = $('#dr-link', d); if (lk) lk.onclick = async () => { try { await api('/api/receipts/link', {tx_id: txId, pfad: $('#dr-free', d).value}); toast('Zugeordnet'); await refreshUms(txId); } catch (e) { toast(e.message, 5000); } };
  $$('.bl-del', d).forEach(b => b.onclick = async e => { const id = e.target.closest('.beleg').dataset.id, ent = mine.find(x => x.id === id); const del = ent && ent.extern ? false : confirm('Zuordnung entfernen. Datei auch löschen?\nOK = Datei löschen, Abbrechen = nur Zuordnung entfernen'); try { await api('/api/receipts/remove', {id, datei_loeschen: del}); await refreshUms(txId); } catch (er) { toast(er.message, 5000); } });
  const ep = $('#dr-ext-pick', d); if (ep) ep.onclick = async () => { toast('Dateiauswahl am Mac geöffnet …', 4000); try { const r = await api('/api/file/choose', {art: 'datei', prompt: 'Beleg für ' + u.name}); if (r.ok) $('#dr-ext', d).value = r.pfad; else toast(r.text); } catch (er) { toast(er.message, 5000); } };
  const el = $('#dr-ext-link', d); if (el) el.onclick = async () => { const pfad = $('#dr-ext', d).value.trim(); if (!pfad) return toast('Pfad fehlt'); try { await api('/api/receipts/link', {tx_id: txId, pfad, extern: true}); toast('Verknüpft'); await refreshUms(txId); } catch (er) { toast(er.message, 6000); } };
  $$('.bl-note', d).forEach(b => b.onclick = async e => { const id = e.target.closest('.beleg').dataset.id, ent = mine.find(x => x.id === id); const n = prompt('Notiz zum Beleg:', ent.notiz || ''); if (n === null) return; await api('/api/receipts/update', {id, notiz: n}); await refreshUms(txId); });
  $$('.bl-show', d).forEach(b => b.onclick = async e => { const id = e.target.closest('.beleg').dataset.id, ent = mine.find(x => x.id === id); try { await api('/api/receipts/open', {pfad: ent.pfad}); } catch (er) { toast(er.message, 4000); } });
  const cb = $('#dr-cat-btn', d); if (cb) cb.onclick = async () => { const kat = $('#dr-kat', d).value.trim(); const body = {ids: [txId], kategorie: kat, in_moneymoney: !!($('#dr-mm', d) && $('#dr-mm', d).checked)}; if ($('#dr-rule', d).checked && kat) body.regel = {name_enthaelt: u.name}; try { const r = await api('/api/categories/assign', body); toast(kat ? 'Zugeordnet' + (r.regel ? ' · Regel angelegt' : '') : 'Zuordnung entfernt'); await loadAll(); await refreshUms(txId); } catch (e) { toast(e.message, 5000); } };
}
function closeDrawer() { $('#drawer').classList.remove('open'); S.drawerTx = null; }
async function belegeApi(path, body) {
  // Erster Beleg: Ordner nur nach Rueckfrage anlegen (oder anderen Ordner in den Einstellungen waehlen)
  try { return await api(path, body); }
  catch (e) {
    if (!(e.data && e.data.ordner_bestaetigen)) throw e;
    if (!confirm('Belege werden im Ordner\n' + e.data.ordner + '\nabgelegt. Den Ordner jetzt anlegen?\n\n(Abbrechen = anderen Ordner unter Einstellungen → Belege wählen)')) { location.hash = '#einstellungen'; throw new Error('Kein Belegordner – unter Einstellungen → Belege festlegen.'); }
    return api(path, Object.assign({}, body, {ordner_anlegen: true}));
  }
}
async function refreshUms(txId) { await route(); if (txId != null) await openDrawer(txId); }
function pickFiles(txId, camera) {
  const inp = $('#file-input'); inp.value = '';
  if (camera) { inp.setAttribute('accept', 'image/*'); inp.setAttribute('capture', 'environment'); } else { inp.setAttribute('accept', '.pdf,.png,.jpg,.jpeg,.heic,.gif,.txt,.csv,.xlsx,.docx,.eml,.msg,.zip'); inp.removeAttribute('capture'); }
  inp.onchange = async () => { await uploadFiles(txId, inp.files); };
  inp.click();
}
async function uploadFiles(txId, files) {
  for (const f of files) {
    if (f.size > 60 * 1024 * 1024) { toast(f.name + ': zu groß (max. 60 MB)', 5000); continue; }
    toast('Lade ' + f.name + ' …', 60000);
    try {
      const b64 = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1] || ''); r.onerror = rej; r.readAsDataURL(f); });
      await belegeApi('/api/receipts/upload', {tx_id: txId, datei_name: f.name, inhalt: b64});
      toast(f.name + ' abgelegt');
    } catch (e) { toast('Fehler: ' + e.message, 6000); }
  }
  await refreshUms(txId);
}

// ---------------------------------------------------------------- Regeln
function acctOptions(selected, filter) {
  const sel = (selected || '').split('|')[0].trim();
  return '<option value="">– wählen –</option>' + S.KONTEN.filter(filter || (() => true)).map(k =>
    `<option value="${k.uuid} | ${esc(k.name)}" ${k.uuid === sel ? 'selected' : ''}>${' '.repeat(k.ebene * 3)}${esc(k.name)}${k.gruppe ? ' (Gruppe)' : (k.manuell ? ' · manuell' : '')}</option>`).join('')
    + (sel && !S.KONTEN.some(k => k.uuid === sel) ? `<option value="${esc(selected)}" selected>${esc(selected)} (nicht gefunden)</option>` : '');
}
const onlyManual = k => !k.gruppe && k.manuell, onlyGroups = k => k.gruppe, onlyLeaves = k => !k.gruppe;
function vRegeln() {
  const C = S.CFG;
  let h = '<div class="note">Regeln schreiben ausschließlich in manuell geführte Konten („Offline-Konten“ in MoneyMoney). Jede Buchung trägt eine Markierung im Verwendungszweck und wird nie doppelt angelegt; bestehende Buchungen werden nie geändert oder gelöscht. Änderungen werden erst nach „Speichern“ wirksam und vorher gegen MoneyMoney geprüft.' + (S.KONTEN.length ? '' : ' <b>Noch keine Konten geladen – unter Einstellungen „Konfiguration prüfen“ oder einen Abgleich starten.</b>') + '</div>';
  h += '<h2>Darlehen <span class="x">Rate erkennen, auf dem Darlehenskonto spiegeln, Zinsen berechnen</span></h2><div class="list" id="loans">';
  (C.darlehen || []).forEach((l, i) => { h += loanForm(l, i); });
  h += '</div><div class="actions"><button id="add-loan" class="secondary">Darlehen hinzufügen</button></div>';
  h += '<h2>Beteiligungen <span class="x">Wert = Anteil × Nettowert einer Kontengruppe</span></h2><div class="list" id="bets">';
  (C.beteiligungen || []).forEach((b, i) => { h += mirrorForm(b, i, 'bet'); });
  h += '</div><div class="actions"><button id="add-bet" class="secondary">Beteiligung hinzufügen</button></div>';
  h += '<h2>Saldo-Spiegel <span class="x">Zielkonto = Faktor × Quellkonto (z. B. Kapitalkonto)</span></h2><div class="list" id="mirrors">';
  (C.saldo_spiegel || []).forEach((b, i) => { h += mirrorForm(b, i, 'mirror'); });
  h += '</div><div class="actions"><button id="add-mirror" class="secondary">Spiegel hinzufügen</button><button id="save-rules">Speichern und prüfen</button></div><div id="findings" class="findings"></div>';
  return h;
}
function loanForm(l, i) {
  const z = l.zins || {}, b = l.buchung || {}, e = l.erkennung || {};
  const satz = (z.satz || []).map(s => `${s.ab}: ${s.prozent}`).join('; ');
  return `<div class="item" data-i="${i}"><div class="grow"><div class="form">
    <label>Name</label><input type="text" class="f-name" value="${esc(l.name || '')}">
    <label>aktiv</label><label class="chk"><input type="checkbox" class="f-aktiv" ${l.aktiv === false ? '' : 'checked'}></label>
    <label>Darlehenskonto (manuell) ${hq('darlehen_konto')}</label><select class="f-konto">${acctOptions(l.darlehenskonto, onlyManual)}</select>
    <label>Quellkonto (Zahlungen) ${hq('darlehen_quelle')}</label><select class="f-quelle">${acctOptions((l.quellkonten || [])[0], onlyLeaves)}</select>
    <label>Gegen-IBAN ${hq('darlehen_iban')}</label><input type="text" class="f-iban" value="${esc(e.gegen_iban || '')}" placeholder="DE… (IBAN des Darlehensgebers/-nehmers)">
    <label>oder Text enthält</label><input type="text" class="f-text" value="${esc((e.text_enthaelt || []).join('; '))}" placeholder="z. B. Darlehen Mustermann (wenn keine IBAN)">
    <label>Ausschließen, wenn Text enthält</label><input type="text" class="f-excl" value="${esc((e.ausschliessen_text || []).join('; '))}" placeholder="z. B. Nebenkosten; Kaution">
    <label>Art</label><select class="f-art"><option value="verbindlichkeit" ${l.art !== 'forderung' ? 'selected' : ''}>Verbindlichkeit (ich zahle)</option><option value="forderung" ${l.art === 'forderung' ? 'selected' : ''}>Forderung (ich erhalte)</option></select>
    <label>Automatik ab</label><input type="date" class="f-ab" value="${esc(l.ab_datum || '')}">
    <label>Zinsmodell ${hq('zinsmodell')}</label><select class="f-modell"><option value="jahresbasis" ${z.modell !== 'restschuld_monatlich' && z.satz ? 'selected' : ''}>Jahresbasis: Satz × Stand 31.12. Vorjahr, 1/12 je Monat</option><option value="restschuld_monatlich" ${z.modell === 'restschuld_monatlich' ? 'selected' : ''}>Restschuld monatlich: Satz/12 × Stand Vormonat</option><option value="" ${!z.satz ? 'selected' : ''}>keine Zinsen (nur spiegeln)</option></select>
    <label>Zinssätze (ab: %) ${hq('satz')}</label><input type="text" class="f-satz" value="${esc(satz)}" placeholder="2025-11-20: 3,3; 2027-01-01: 3,0">
    <label>Zinsbuchung</label><select class="f-tag"><option value="mit_rate" ${z.buchungstag !== 'ultimo' ? 'selected' : ''}>am Tag der Rate (sonst Ultimo)</option><option value="ultimo" ${z.buchungstag === 'ultimo' ? 'selected' : ''}>Ultimo</option></select>
    <label>Jahresbasis erzwingen (Jahr=Betrag) ${hq('basis_override')}</label><input type="text" class="f-basis" value="${esc(Object.entries(z.basis_override || {}).map(([k, v]) => k + '=' + v).join('; '))}" placeholder="2026=160000">
    <label>Gegenpartei</label><input type="text" class="f-gp" value="${esc(b.gegenpartei || '')}">
    <label>Kategorie Tilgung</label><select class="f-kt">${catOptions(b.kategorie_tilgung)}</select>
    <label>Kategorie Zinsen</label><select class="f-kz">${catOptions(b.kategorie_zins)}</select>
  </div></div><button class="danger small del">Entfernen</button></div>`;
}
function mirrorForm(b, i, kind) {
  return `<div class="item" data-i="${i}" data-kind="${kind}"><div class="grow"><div class="form">
    <label>Name</label><input type="text" class="f-name" value="${esc(b.name || '')}">
    <label>aktiv</label><label class="chk"><input type="checkbox" class="f-aktiv" ${b.aktiv === false ? '' : 'checked'}></label>
    <label>Zielkonto (manuell)</label><select class="f-ziel">${acctOptions(b.zielkonto || b.beteiligungskonto, onlyManual)}</select>
    <label>${kind === 'bet' ? 'Kontengruppe (Wert)' : 'Quellkonto'} ${hq(kind === 'bet' ? 'beteiligung' : 'spiegel')}</label><select class="f-quelle">${acctOptions(kind === 'bet' ? b.gruppe : b.quellkonto, kind === 'bet' ? onlyGroups : onlyLeaves)}</select>
    <label>${kind === 'bet' ? 'Anteil (0–1)' : 'Faktor'}</label><input type="number" step="0.0001" class="f-anteil" value="${kind === 'bet' ? (b.anteil ?? 0.5) : (b.faktor ?? -1)}">
    <label>Schwelle €</label><input type="number" step="0.01" class="f-schwelle" value="${b.schwelle ?? 0.01}">
    <label>Gegenpartei (Buchungstext)</label><input type="text" class="f-gp" value="${esc((b.buchung || {}).gegenpartei || '')}" placeholder="optional">
  </div></div><button class="danger small del">Entfernen</button></div>`;
}
function catOptions(selected) {
  const leaves = S.KATS.filter(k => !k.gruppe);
  return '<option value="">– keine –</option>' + leaves.map(k => `<option value="${esc(k.name)}" ${k.name === selected ? 'selected' : ''}>${esc(k.pfad)}</option>`).join('') + (selected && !leaves.some(k => k.name === selected) ? `<option value="${esc(selected)}" selected>${esc(selected)} (nicht in MoneyMoney)</option>` : '');
}
function collectRules() {
  const cfg = JSON.parse(JSON.stringify(S.CFG));
  const lst = s => s.split(';').map(x => x.trim()).filter(Boolean);
  cfg.darlehen = $$('#loans .item').map(it => {
    const v = s => $(s, it).value.trim();
    const satz = lst(v('.f-satz')).map(x => { const [ab, p] = x.split(':'); return {ab: ab.trim(), prozent: parseFloat((p || '0').replace(',', '.'))}; });
    const basis = {}; lst(v('.f-basis')).forEach(x => { const [k, val] = x.split('='); basis[k.trim()] = parseFloat((val || '0').replace(',', '.')); });
    const modell = v('.f-modell');
    const l = { name: v('.f-name'), aktiv: $('.f-aktiv', it).checked, darlehenskonto: v('.f-konto'), quellkonten: v('.f-quelle') ? [v('.f-quelle')] : [],
      erkennung: { gegen_iban: v('.f-iban').replace(/\s/g, '').toUpperCase(), text_enthaelt: lst(v('.f-text')), ausschliessen_text: lst(v('.f-excl')) },
      art: v('.f-art'), ab_datum: v('.f-ab'),
      buchung: { gegenpartei: v('.f-gp') || v('.f-name'), kategorie_tilgung: v('.f-kt') || null, kategorie_zins: v('.f-kz') || null } };
    if (modell) l.zins = { modell, satz, buchungstag: v('.f-tag'), basis_override: basis };
    return l;
  });
  cfg.beteiligungen = $$('#bets .item').map(it => ({ name: $('.f-name', it).value.trim(), aktiv: $('.f-aktiv', it).checked, beteiligungskonto: $('.f-ziel', it).value, gruppe: $('.f-quelle', it).value, anteil: parseFloat($('.f-anteil', it).value) || 0, schwelle: parseFloat($('.f-schwelle', it).value) || 0.01, buchung: $('.f-gp', it).value.trim() ? {gegenpartei: $('.f-gp', it).value.trim()} : undefined }));
  cfg.saldo_spiegel = $$('#mirrors .item').map(it => ({ name: $('.f-name', it).value.trim(), aktiv: $('.f-aktiv', it).checked, zielkonto: $('.f-ziel', it).value, quellkonto: $('.f-quelle', it).value, faktor: parseFloat($('.f-anteil', it).value) || -1, schwelle: parseFloat($('.f-schwelle', it).value) || 0.01, buchung: $('.f-gp', it).value.trim() ? {gegenpartei: $('.f-gp', it).value.trim()} : undefined }));
  return cfg;
}
function showFindings(el, befunde, extra, kind = 'hinweis') {
  el.innerHTML = (extra ? `<div class="${kind}">${esc(extra)}</div>` : '') + (befunde || []).map(f => `<div class="${f.stufe}">${esc(f.text)}</div>`).join('');
}
async function saveConfig(cfg, findingsEl, trotzdem) {
  try {
    const r = await api('/api/config', {config: cfg, trotzdem: !!trotzdem}, 'PUT');
    DIRTY.on = false;
    const probleme = (r.befunde || []).filter(f => f.stufe !== 'ok');      // erfolgreich gepruefte Verweise nicht einzeln auflisten
    S.CFG = r.config; showFindings(findingsEl, probleme, 'Gespeichert.' + (S.KONTEN.length ? '' : ' (Noch nicht gegen MoneyMoney geprüft.)'), 'ok'); toast('Gespeichert');
    S.STATUS = await api('/api/status'); statusMini();
    return true;
  } catch (e) {
    if (e.data && e.data.befunde) { showFindings(findingsEl, e.data.befunde, 'Nicht gespeichert – Fehler beheben oder „trotzdem speichern“.', 'fehler'); findingsEl.insertAdjacentHTML('beforeend', '<div class="actions"><button id="save-anyway" class="danger small">Trotzdem speichern</button></div>'); $('#save-anyway').addEventListener('click', () => saveConfig(cfg, findingsEl, true)); }
    else toast('Fehler: ' + e.message, 5000);
    return false;
  }
}

// ---------------------------------------------------------------- Kategorien
async function vKategorien() {
  const tabs = `<div class="tabs">${[['baum', 'Kontor-Kategorien & Regeln'], ['kapitalfluss', 'Kapitalfluss-Zuordnung']].map(([t, l]) => `<button data-kt="${t}" class="${KZ.tab === t ? 'on' : ''}">${l}</button>`).join('')}</div>`;
  if (KZ.tab === 'baum') { await loadKat(); return tabs + vKontorKategorien(); }
  return tabs + vKapitalflussZuordnung();
}
function vKapitalflussZuordnung() {
  const kf = S.CFG.kapitalfluss || {}, zu = kf.kategorie_zuordnung || {}, zk = kf.kategorie_zu_konto || {}, umb = kf.umbuchungs_kategorien || ['Umbuchung'];
  const kontorTops = KZ.kat ? [...new Set(KZ.kat.baum.map(k => k.pfad.split(' / ')[0]))] : [];
  const tops = S.KATS.filter(k => k.ebene === 0).map(k => ({name: k.name, budget: k.budget}));
  for (const n of kontorTops) if (!tops.some(t => t.name === n)) tops.push({name: n, budget: null});
  let h = '<div class="note">Zuordnung der Oberkategorien (Kontor und MoneyMoney) zu den Abschnitten des Kapitalflusses. Ohne Zuordnung entscheidet das Vorzeichen (Einnahmen/Ausgaben) bzw. der Name (invest → Investitionen, tilgung/kredit → Finanzierung, zinsen → Zinsen). Kategorien in MoneyMoney werden von Kontor nie angelegt, umbenannt oder gelöscht.' + (tops.length ? '' : ' <b>Noch keine Kategorien geladen – Abgleich starten oder Konfiguration prüfen.</b>') + '</div>';
  h += '<div class="wrap auto"><table class="plain"><thead><tr><th>Oberkategorie</th><th>Abschnitt</th><th>Käufe fließen in Depot/Anlage</th><th class="num">Budget (MoneyMoney)</th></tr></thead><tbody>';
  for (const t of tops) {
    const cur = zu[t.name] || '';
    h += `<tr data-cat="${esc(t.name)}"><td>${esc(t.name)}${umb.includes(t.name) ? '<span class="tag">Umbuchung</span>' : ''}</td><td><select class="k-sek"><option value="">automatisch</option>${['Einnahmen', 'Ausgaben', 'Investitionen', 'Finanzierung/Tilgung', 'Finanzierung/Zinsen', 'Ignorieren'].map(x => `<option ${cur === x ? 'selected' : ''}>${x}</option>`).join('')}</select></td><td><select class="k-depot">${acctOptions(zk[t.name], k => !k.gruppe && (k.depot || k.rolle === 'anlagen'))}</select></td><td class="num small muted">${t.budget ? F0(t.budget.amount) + ' / ' + esc(t.budget.period || '') : ''}</td></tr>`;
  }
  h += '</tbody></table></div>';
  h += `<div class="form" style="margin-top:12px"><label>Umbuchungs-Kategorien</label><input type="text" id="k-umb" value="${esc(umb.join('; '))}"><label>Beteiligungsgruppen (Einlagen zählen als Investition)</label><div>${[0, 1, 2].map(i => `<select class="k-bg">${acctOptions((kf.beteiligungs_gruppen || [])[i], onlyGroups)}</select>`).join(' ')}</div></div>`;
  h += '<div class="actions"><button id="save-kats">Speichern</button></div><div id="findings-k" class="findings"></div>';
  const have = new Set(S.KATS.map(k => k.pfad));
  const rec = [
    ['Finanzierung', 'Oberkategorie für Zins- und Tilgungsbuchungen, die keine Umbuchung zwischen eigenen Konten sind'],
    ['Finanzierung / Zinsen', 'Zinsbuchungen der Darlehensregeln (dann unter Regeln als „Kategorie Zinsen“ wählen)'],
    ['Finanzierung / Tilgung', 'Zahlungen an private Darlehensgeber'],
    ['Steuern', 'Einkommensteuer-Vorauszahlungen und -Nachzahlungen'],
    ['Einkommen / Gehalt', 'Anlage N'], ['Einkommen / Kapitalerträge', 'Anlage KAP: Zinsen, Dividenden'],
    ['Einkommen / Ausschüttungen', 'Entnahmen/Ausschüttungen aus Beteiligungen'],
    [(S.CFG.steuer && S.CFG.steuer.vermietung_kategorie) || 'Vermietung', 'Oberkategorie; darunter je Objekt: Mieteinnahmen, Nebenkosten (Umlagen), Hausgeld/Verwaltung, Instandhaltung, Grundsteuer, Versicherung, Sonstiges'],
  ].filter(([p]) => !have.has(p));
  if (rec.length && tops.length) h += '<h2>Empfohlene Ergänzungen <span class="x">in MoneyMoney anlegen – bestehende Buchungen und Regeln bleiben unberührt</span></h2><div class="wrap auto"><table class="plain"><thead><tr><th>Kategorie</th><th>Zweck</th></tr></thead><tbody>' + rec.map(([p, z]) => `<tr><td>${esc(p)}</td><td>${esc(z)}</td></tr>`).join('') + '</tbody></table></div>';
  return h;
}

// ---------------------------------------------------------------- Zuordnen (Kontor-Kategorien)
const KZ = {jahr: '', bereich: '', min: '', open: {}, kat: null, offen: null, tab: 'baum'};
async function loadKat() { KZ.kat = await api('/api/categories/kontor'); return KZ.kat; }
const katPaths = () => (KZ.kat ? KZ.kat.baum.map(k => k.pfad) : []);
const katList = id => `<datalist id="${id}">${katPaths().map(p => `<option value="${esc(p)}">`).join('')}</datalist>`;
async function vZuordnen() {
  if (!S.DATA) return noData;
  const [kat, off] = await Promise.all([loadKat(), api(`/api/categories/unassigned?year=${KZ.jahr}&area=${KZ.bereich}&min=${KZ.min}`)]);
  KZ.offen = off;
  const st = (S.DATA.kategorien || {}).gesamt || {}, years = Object.keys((S.DATA.kategorien || {}).jahre || {}).sort().reverse();
  const mmAllowed = S.STATUS.lokal && S.STATUS.moneymoney.kategorisieren_erlaubt;
  let h = `<div class="toolbar"><select id="kz-bereich"><option value="">alle Bereiche</option>${Object.keys(S.DATA.bereiche).map(k => `<option value="${k}" ${KZ.bereich === k ? 'selected' : ''}>${esc(BN(k))}</option>`).join('')}</select>
    <select id="kz-jahr"><option value="">alle Jahre</option>${years.map(y => `<option ${KZ.jahr === y ? 'selected' : ''}>${y}</option>`).join('')}</select>
    <label class="chk small">ab <input type="number" id="kz-min" value="${esc(KZ.min)}" placeholder="0" style="width:80px"> €</label>
    <span class="sp"></span><button id="kz-lernen" class="secondary small" title="Regeln aus allen vorhandenen Zuordnungen (Kontor und MoneyMoney) neu ableiten und Lücken füllen">Regeln neu lernen</button><a href="#kategorien"><button class="secondary small">Kategorien & Regeln</button></a></div>
    <div class="note">${off.offen} Umsätze ohne Kategorie${off.hinweis ? ' – ' + esc(off.hinweis) : ''}, gruppiert nach Gegenpartei (${off.gruppen_gesamt} Gruppen). Zuordnen setzt die Kategorie in Kontor; mit „Regel“ gilt sie künftig automatisch für diese Gegenpartei. Stand: ${st.manuell || 0} manuell · ${st.regel || 0} per Regel · ${st.moneymoney || 0} aus MoneyMoney · ${st.ohne || 0} offen. ${hq('zuordnen')}</div>` + katList('kz-kats');
  if (!off.gruppen.length) return h + '<div class="card"><div class="v s">Nichts offen</div><div class="d">Alle Umsätze haben eine Kategorie (Filter beachten).</div></div>';
  h += '<div class="list">';
  for (const g of off.gruppen) {
    const open = KZ.open[g.key];
    h += `<div class="item kz-group" data-key="${esc(g.key)}"><div class="grow">
      <div class="row tight"><b style="min-width:220px">${esc(g.name)}</b><span class="small muted">${esc(g.konto)}${g.iban ? ' · ' + esc(g.iban) : ''}</span><span class="tag">${g.anzahl}×</span><span class="num ${g.summe < 0 ? 'neg' : 'pos'}" style="font-weight:600">${F(g.summe)} €</span><span class="small muted">${FD(g.von)}${g.von !== g.bis ? ' – ' + FD(g.bis) : ''}</span><button class="ghost small kz-toggle">${open ? 'Beispiele ▴' : 'Beispiele ▾'}</button></div>
      ${open ? '<div class="small muted" style="margin:4px 0 6px">' + g.beispiele.map(b => `${FD(b.datum)} · ${F(b.betrag)} € · ${esc(b.zweck || '–')}`).join('<br>') + '</div>' : ''}
      <div class="row tight"><input type="text" class="kz-kat" list="kz-kats" value="${esc(g.vorschlag || '')}" placeholder="Kategorie (neu = anlegen), z. B. Wohnen / Miete" style="min-width:300px">${g.vorschlag ? '<span class="tag" title="Vorschlag aus Regel ' + esc(g.regel || '') + '">Vorschlag</span>' : ''}
        <label class="chk small"><input type="checkbox" class="kz-rule" checked> Regel für ${g.iban ? 'diese IBAN' : 'diesen Namen'}</label>${mmAllowed ? '<label class="chk small"><input type="checkbox" class="kz-mm"> auch in MoneyMoney</label>' : ''}
        <button class="small kz-save">Zuordnen</button><button class="small secondary kz-umb" title="Übertrag zwischen eigenen Konten">Umbuchung</button></div></div></div>`;
  }
  return h + '</div>';
}
function bindZuordnen(main) {
  const bindF = (id, key) => { const el = $(id, main); if (el) el.addEventListener('change', e => { KZ[key] = e.target.value; route(); }); };
  bindF('#kz-bereich', 'bereich'); bindF('#kz-jahr', 'jahr'); bindF('#kz-min', 'min');
  const ln = $('#kz-lernen', main); if (ln) ln.addEventListener('click', async () => { toast('Lerne …', 10000); try { const r = await api('/api/categories/learn', {}); toast(`${r.gelernt.regeln} Regeln aus ${r.gelernt.muster} Umsätzen, ${r.zugeordnet} neu zugeordnet`, 6000); await loadAll(); route(); } catch (e) { toast(e.message, 6000); } });
  $$('.kz-toggle', main).forEach(b => b.addEventListener('click', e => { const k = e.target.closest('.kz-group').dataset.key; KZ.open[k] = !KZ.open[k]; route(); }));
  const assign = async (box, kat) => {
    const g = KZ.offen.gruppen.find(x => x.key === box.dataset.key); if (!g || !kat) return toast('Kategorie fehlt');
    const body = {ids: g.ids, kategorie: kat, in_moneymoney: !!($('.kz-mm', box) && $('.kz-mm', box).checked)};
    if ($('.kz-rule', box).checked) body.regel = g.iban ? {iban: g.iban} : {name_enthaelt: g.name};
    try { const r = await api('/api/categories/assign', body); toast(`${r.anzahl} zugeordnet${r.regel ? ' · Regel angelegt' : ''}${r.in_moneymoney ? ' · ' + r.in_moneymoney + ' in MoneyMoney' : ''}`); await loadAll(); route(); } catch (e) { toast(e.message, 6000); }
  };
  $$('.kz-save', main).forEach(b => b.addEventListener('click', e => { const box = e.target.closest('.kz-group'); assign(box, $('.kz-kat', box).value.trim()); }));
  $$('.kz-umb', main).forEach(b => b.addEventListener('click', e => { const box = e.target.closest('.kz-group'); assign(box, 'Umbuchung'); }));
  $$('.kz-kat', main).forEach(i => i.addEventListener('keydown', e => { if (e.key === 'Enter') { const box = e.target.closest('.kz-group'); assign(box, e.target.value.trim()); } }));
}
function vKontorKategorien() {
  const kat = KZ.kat; if (!kat) return '<div class="note">Lade …</div>';
  const e = kat.einstellungen || {}, st = kat.statistik || {}, ges = st.gesamt || {};
  let h = `<div class="note">Kontor führt eigene Kategorien: Baum aus MoneyMoney übernommen (ergänzbar, umbenennbar), Zuordnung je Umsatz in Kontor, Regeln gelernt aus deinen bisherigen Zuordnungen plus eigene Regeln. Für Umsätze ohne Kontor-Zuordnung gilt weiterhin die Kategorie aus MoneyMoney – nichts geht verloren, und der Partner kommt ohne MoneyMoney-Kategorien aus. ${hq('kontor_kategorien')}</div>
  <div class="row tight" style="margin-bottom:10px"><label class="switch"><input type="checkbox" id="kk-aktiv" ${e.aktiv !== false ? 'checked' : ''}><i></i>Kontor-Kategorien aktiv</label><label class="switch"><input type="checkbox" id="kk-lernen" ${e.lernen !== false ? 'checked' : ''}><i></i>bei jedem Abgleich Regeln nachlernen</label><label class="switch"><input type="checkbox" id="kk-mm" ${e.mm_ueberschreiben ? 'checked' : ''}><i></i>Regeln auch auf MoneyMoney-kategorisierte Umsätze anwenden ${hq('mm_ueberschreiben')}</label>
    <span class="small muted">${st.kategorien || 0} Kategorien · Regeln: ${(st.regeln || {}).manuell || 0} eigene, ${(st.regeln || {}).gelernt || 0} gelernt${st.gelernt_am ? ' (' + esc(st.gelernt_am) + ')' : ''} · Umsätze: ${ges.manuell || 0} manuell, ${ges.regel || 0} Regel, ${ges.moneymoney || 0} MoneyMoney, ${ges.ohne || 0} offen</span></div>`;
  h += `<h2>Kategorien <span class="x">${kat.baum.length}</span></h2><div class="row tight" style="margin-bottom:6px"><input type="text" id="kk-neu" placeholder="Neue Kategorie, z. B. Wohnen / Nebenkosten" style="min-width:320px"><button id="kk-add" class="small">Anlegen</button><button id="kk-mmsync" class="small secondary" title="Neue Kategorien aus MoneyMoney in den Kontor-Baum übernehmen">Aus MoneyMoney ergänzen</button></div>
    <div class="wrap auto" style="max-height:420px;overflow:auto"><table class="plain"><thead><tr><th>Kategorie</th><th>Quelle</th><th></th></tr></thead><tbody>${kat.baum.map(k => `<tr data-pfad="${esc(k.pfad)}"><td class="ind${Math.min(3, k.pfad.split(' / ').length - 1)}">${esc(k.name)}<span class="small muted"> · ${esc(k.pfad)}</span></td><td class="small">${k.quelle === 'moneymoney' ? 'MoneyMoney' : 'Kontor'}</td><td style="white-space:nowrap"><button class="ghost small kk-ren">Umbenennen</button><button class="ghost small kk-del">✕</button></td></tr>`).join('')}</tbody></table></div>`;
  h += `<h2>Regeln <span class="x">eigene zuerst; spezifischere gewinnen (IBAN &gt; Name + Zweck &gt; Name)</span></h2>
    <div class="row tight" style="margin-bottom:6px"><input type="text" id="kr-name" placeholder="Name enthält" style="width:180px"><input type="text" id="kr-zweck" placeholder="Zweck enthält" style="width:180px"><input type="text" id="kr-iban" placeholder="Gegen-IBAN" style="width:200px"><select id="kr-richtung"><option value="">beide Richtungen</option><option value="aus">Ausgaben</option><option value="ein">Einnahmen</option></select><input type="text" id="kr-kat" list="kk-kats" placeholder="Kategorie" style="width:220px"><button id="kr-add" class="small">Regel anlegen</button></div>${katList('kk-kats')}
    <div class="wrap auto" style="max-height:420px;overflow:auto"><table class="plain"><thead><tr><th>Bedingung</th><th>Kategorie</th><th>Quelle</th><th class="num">Treffer</th><th></th></tr></thead><tbody>${kat.regeln.map(r => `<tr data-id="${esc(r.id)}"><td class="small">${[r.iban ? 'IBAN ' + esc(r.iban) : '', r.name_ist ? 'Name = „' + esc(r.name_ist) + '“' : '', r.name_enthaelt ? 'Name enthält „' + esc(r.name_enthaelt) + '“' : '', r.zweck_enthaelt ? 'Zweck enthält „' + esc(r.zweck_enthaelt) + '“' : '', r.richtung ? (r.richtung === 'aus' ? 'Ausgaben' : 'Einnahmen') : ''].filter(Boolean).join(' · ')}</td><td>${esc(r.kategorie)}</td><td class="small">${r.quelle === 'manuell' ? 'eigene' : 'gelernt'}</td><td class="num small">${r.treffer ?? ''}</td><td><button class="ghost small kr-del">✕</button></td></tr>`).join('') || '<tr><td colspan="5" class="muted">Noch keine Regeln – „Regeln neu lernen“ unter Zuordnen.</td></tr>'}</tbody></table></div>`;
  return h;
}
function bindKontorKategorien(main) {
  const setEinst = async () => { try { await api('/api/categories/settings', {aktiv: $('#kk-aktiv').checked, lernen: $('#kk-lernen').checked, mm_ueberschreiben: $('#kk-mm').checked}); toast('Gespeichert'); await loadAll(); } catch (e) { toast(e.message, 5000); } };
  for (const id of ['#kk-aktiv', '#kk-lernen', '#kk-mm']) { const el = $(id, main); if (el) el.addEventListener('change', setEinst); }
  const add = $('#kk-add', main); if (add) add.addEventListener('click', async () => { const p = $('#kk-neu').value.trim(); if (!p) return; try { await api('/api/categories/tree', {aktion: 'anlegen', pfad: p}); toast('Angelegt'); await loadKat(); route(); } catch (e) { toast(e.message, 5000); } });
  const ms = $('#kk-mmsync', main); if (ms) ms.addEventListener('click', async () => { try { await api('/api/categories/tree', {aktion: 'mm_uebernehmen'}); await loadKat(); route(); } catch (e) { toast(e.message, 5000); } });
  $$('.kk-ren', main).forEach(b => b.addEventListener('click', async e => { const p = e.target.closest('tr').dataset.pfad; const n = prompt('Neuer Pfad (Verschieben = Oberkategorie ändern):', p); if (!n || n === p) return; try { await api('/api/categories/tree', {aktion: 'umbenennen', pfad: p, neu: n}); await loadKat(); await loadAll(); route(); } catch (er) { toast(er.message, 5000); } }));
  $$('.kk-del', main).forEach(b => b.addEventListener('click', async e => { const p = e.target.closest('tr').dataset.pfad; const ers = prompt('„' + p + '“ löschen. Zuordnungen und Regeln umhängen auf (leer = entfernen):', ''); if (ers === null) return; try { await api('/api/categories/tree', {aktion: 'loeschen', pfad: p, ersatz: ers}); await loadKat(); await loadAll(); route(); } catch (er) { toast(er.message, 5000); } }));
  const ra = $('#kr-add', main); if (ra) ra.addEventListener('click', async () => { try { await api('/api/categories/rule', {regel: {name_enthaelt: $('#kr-name').value, zweck_enthaelt: $('#kr-zweck').value, iban: $('#kr-iban').value, richtung: $('#kr-richtung').value, kategorie: $('#kr-kat').value}}); toast('Regel angelegt'); await loadKat(); await loadAll(); route(); } catch (e) { toast(e.message, 6000); } });
  $$('.kr-del', main).forEach(b => b.addEventListener('click', async e => { const id = e.target.closest('tr').dataset.id; try { await api('/api/categories/rule', {loeschen: id}); await loadKat(); await loadAll(); route(); } catch (er) { toast(er.message, 5000); } }));
}

// ---------------------------------------------------------------- Einstellungen
function vEinstellungen() {
  const C = S.CFG, z = C.zeitplan || {}, b = C.bilanz || {}, o = C.oberflaeche || {}, st = C.steuer || {}, bl = C.belege || {}, mm = C.moneymoney || {}, up = C.updates || {};
  const loans = S.KONTEN.filter(k => !k.gruppe && k.rolle === 'verbindlichkeiten');
  let h = `<h2>Betrieb</h2><div class="form">
    <label>Testmodus ${hq('probelauf')}</label><label class="chk"><input type="checkbox" id="e-probelauf" ${C.probelauf ? 'checked' : ''}> Buchungen aus Regeln nur vorschlagen, nichts in MoneyMoney anlegen</label>
    <label>Automatischer Abgleich ${hq('abgleich')}</label><label class="chk"><input type="checkbox" id="e-auto" ${z.automatisch !== false ? 'checked' : ''}> alle <input type="number" id="e-intervall" min="5" value="${z.intervall_minuten ?? 30}" style="width:70px"> Minuten (nur wenn MoneyMoney läuft und entsperrt ist)</label>
    <label>Mitteilungen (macOS)</label><label class="chk"><input type="checkbox" id="e-mitt" ${C.mitteilungen !== false ? 'checked' : ''}> bei Buchungen, Vorschlägen und Fehlern</label>
  </div>
  <h2>Bilanz</h2><div class="form">
    <label>Bereiche, Positionen, Verlauf</label><div><a href="#einrichtung/bereiche">Bereiche</a> · <a href="#einrichtung/konten">Konten</a> · <a href="#einrichtung">Einrichtung (alle Bausteine)</a><div class="small muted">${(C.bereiche || []).length ? (C.bereiche || []).map(x => esc(x.name) + (x.haupt ? ' (Haupt)' : '')).join(', ') : 'Standard: jede Kontengruppe der obersten Ebene'}</div></div>
    <label>Historie ${hq('monate_zurueck')}</label><label class="chk"><input type="number" id="e-monate" min="0" value="${b.monate_zurueck ?? 0}" style="width:70px"> Monate (0 = alles)</label>
  </div>
  <h2>MoneyMoney</h2><div class="form">
    <label>Kategorisieren erlauben ${hq('mm_cat')}</label><label class="chk"><input type="checkbox" id="e-mm-cat" ${mm.kategorisieren_erlauben ? 'checked' : ''}> Umsätzen aus Kontor eine Kategorie zuweisen (ändert nur die Kategorie des gewählten Umsatzes, nie Regeln)</label>
  </div>
  <h2>Belege</h2><div class="form">
    <label>Belegordner ${hq('belege_ordner')}</label><div><input type="text" id="e-bl-ordner" value="${esc(bl.ordner || '~/Documents/Kontor-Belege')}" style="width:100%"><div class="small muted">${bl.ordner_bestaetigt ? 'Wird beim ersten Beleg angelegt, falls er fehlt.' : 'Noch nicht angelegt – beim ersten Beleg fragt Kontor, ob dieser Ordner erstellt werden soll. Ein hier eingetragener Ordner gilt als gewählt.'}</div></div>
    <label>Unterordner-Muster ${hq('belege_sub')}</label><input type="text" id="e-bl-sub" value="${esc(bl.unterordner || '{jahr}')}" placeholder="{jahr} · {jahr}/{entitaet} · {entitaet}/{jahr}/{monat} · {konto}">
    <label>Verweis in MoneyMoney ${hq('belege_kommentar')}</label><label class="chk"><input type="checkbox" id="e-bl-comment" ${bl.kommentar_schreiben ? 'checked' : ''}> Dateipfad als Kommentar an den Umsatz schreiben (ändert das Kommentarfeld des Umsatzes)</label>
    <div class="full note">Belege werden als normale Dateien abgelegt (kein Datenbankformat) und können mit dem Finder, Time Machine oder iCloud genauso behandelt werden wie andere Dokumente. Der Index (Datei ↔ Umsatz) liegt verschlüsselt im Datenordner.</div>
  </div>
  <h2>Steuer</h2><div class="form">
    <label>Vermietungs-Oberkategorie</label><input type="text" id="e-verm" value="${esc(st.vermietung_kategorie || 'Vermietung')}">
    <label>Darlehen → Objekt</label><div class="list" id="objloans">${loans.map(l => `<div class="row tight"><span style="min-width:260px">${esc(l.pfad)}</span><input type="text" class="e-obj" data-ref="${l.uuid} | ${esc(l.name)}" value="${esc((st.objekt_darlehen || {})[l.uuid + ' | ' + l.name] || Object.entries(st.objekt_darlehen || {}).find(([k]) => k.startsWith(l.uuid))?.[1] || '')}" placeholder="Objektname (wie in der Kategorie)"></div>`).join('') || '<span class="muted small">keine Darlehenskonten erkannt</span>'}</div>
    <label>Kategorie → Steuerposition</label><div class="list" id="positions">${Object.entries(st.positionen || {}).filter(([k]) => !k.startsWith('_')).map(([k, v]) => posRow(k, v)).join('')}<button id="add-pos" class="secondary small">Zuordnung hinzufügen</button></div>
  </div>
  <h2>Updates</h2><div class="form">
    <label>Täglich prüfen ${hq('updates')}</label><label class="chk"><input type="checkbox" id="e-up-auto" ${up.taeglich_pruefen !== false ? 'checked' : ''}> einmal täglich bei GitHub nachsehen (einzige Netzverbindung von Kontor; installiert wird nur nach Klick)</label>
    <label>Quelle (GitHub-Repo)</label><input type="text" id="e-up-repo" value="${esc(up.repo || 'stecrz/Kontor')}">
  </div>
  <h2>Oberfläche und Zugang</h2><div class="form">
    <label>Automatische Sperre</label><label class="chk">nach <input type="number" id="e-sperre" min="1" value="${o.sperre_minuten ?? 15}" style="width:70px"> Minuten ohne Aktivität</label>
    <label>Touch ID ${hq('touchid')}</label><label class="chk"><input type="checkbox" id="e-touchid" ${o.touchid !== false ? 'checked' : ''} ${S.STATUS.touchid ? '' : 'disabled'}> Am Mac mit Touch ID entsperren – das Passwort gibt es dann nur über „Stattdessen Passwort eingeben“${S.STATUS.touchid ? '' : ' (an diesem Gerät nicht verfügbar)'}</label>
    <label>Adresse ${hq('bind')}</label><input type="text" id="e-bind" value="${esc(o.bind || '127.0.0.1')}" placeholder="127.0.0.1 oder Tailscale-Adresse 100.x.y.z">
    <label>Port</label><input type="number" id="e-port" value="${o.port ?? 8765}" style="width:100px">
    <label>TLS-Zertifikat (optional) ${hq('tls')}</label><input type="text" id="e-cert" value="${esc(o.tls_cert || '')}" placeholder="/Pfad/zert.crt">
    <label>TLS-Schlüssel (optional)</label><input type="text" id="e-key" value="${esc(o.tls_key || '')}" placeholder="/Pfad/zert.key">
    <div class="full note">Adresse und Port gelten nach einem Neustart des Dienstes. Erlaubt sind nur dieser Mac (127.0.0.1) oder eine Tailscale-Adresse (100.64.0.0/10) – nie das offene Netz. Dieser Mac bleibt immer unter 127.0.0.1 erreichbar. Vom iPhone aus: Tailscale auf beiden Geräten, dann am Mac im Terminal <code>python3 ~/Kontor/kontor.py tls</code> (https, nötig für die Offline-Ansicht) oder hier die Tailscale-Adresse eintragen und http://&lt;Tailscale-Adresse&gt;:${o.port ?? 8765}/ öffnen – Anmeldung dort nur per Passwort; Buchen, Updates, Zurücksetzen und Ordner öffnen nur am Mac.</div>
  </div>
  <div class="actions"><button id="save-settings">Einstellungen speichern</button><button id="check-btn" class="secondary">Konfiguration gegen MoneyMoney prüfen</button></div><div id="findings-e" class="findings"></div>
  <h2>Passwort</h2><div class="form"><label>Altes Passwort</label><input type="password" id="pw-alt" autocomplete="current-password"><label>Neues Passwort</label><input type="password" id="pw-neu" autocomplete="new-password"></div><div class="actions"><button id="pw-save" class="secondary">Passwort ändern</button></div>
  <h2>Offline-Ansicht (iPhone) ${hq('offline')}</h2><div class="kv"><div>Auf diesem Gerät</div><div id="sw-state">${navigator.serviceWorker && navigator.serviceWorker.controller ? 'aktiv – die zuletzt geladenen Daten bleiben auf diesem Gerät und sind mit Passwort auch ohne Mac lesbar' : (location.protocol === 'https:' || location.hostname === '127.0.0.1' ? 'wird beim nächsten Laden aktiv' : 'nicht möglich über http – Tailscale-Zertifikat einrichten (Terminal: python3 kontor.py tls), dann https verwenden')}</div></div>
  <div class="actions"><button id="sw-clear" class="secondary">Gespeicherte Daten auf diesem Gerät löschen</button></div>
  <h2>Sicherung &amp; Zurücksetzen</h2><div class="note">Die Sicherung ist eine Datei mit allem, was du in Kontor eingestellt hast: Einstellungen, Bereiche, Regeln, Immobilien, Planung, Kontor-Kategorien und Zuordnungen, Monatsstände, Belegindex – ohne Passwort. Zurücksetzen löscht die Daten von Kontor auf diesem Mac (Belegdateien, verknüpfte Dokumente und das Protokoll bleiben); danach beginnt die Einrichtung von vorn, eine Sicherung lässt sich unter Pakete wieder laden.</div>
  <div class="actions"><button id="bk-save" class="secondary">Sicherung herunterladen</button><a href="#pakete"><button class="secondary">Sicherung laden (Pakete)</button></a></div>
  <div class="row tight" style="margin-top:8px"><input type="password" id="rs-pw" placeholder="Passwort zur Bestätigung" autocomplete="current-password" style="width:220px"><label class="chk"><input type="checkbox" id="rs-pw-reset"> Passwort ebenfalls zurücksetzen (Einrichtung mit neuem Passwort)</label><button id="rs-go" class="danger" ${S.STATUS.lokal ? '' : 'disabled title="nur am Mac"'}>Programm zurücksetzen</button></div><div id="rs-report" class="findings"></div>
  <h2>Daten</h2><div class="kv"><div>Datenordner</div><div>${esc(S.STATUS.ablage.ordner)}</div><div>Verschlüsselung</div><div>${S.STATUS.ablage.verschluesselt ? 'AES-256, Schlüssel im ' + (S.STATUS.ablage.schluessel === 'schluesselbund' ? 'macOS-Schlüsselbund' : 'Dateisystem (0600)') : 'KEINE'}</div><div>Belegordner</div><div>${esc(S.STATUS.belege.ordner)}</div><div>Touch ID</div><div>${S.STATUS.touchid ? 'verfügbar' : 'nicht verfügbar (Helfer nicht übersetzt oder nicht am Mac)'}</div><div>Version</div><div>${esc(S.STATUS.version)}</div></div>
  <div class="actions"><button id="tm-ex" class="secondary">Datenordner von Time Machine ausschließen</button><button id="tm-in" class="secondary">Ausschluss aufheben</button><button id="diag" class="secondary">Diagnosedatei (maskiert)</button></div>
  <div class="note">Die Diagnosedatei enthält Protokoll, Konfiguration und Status mit maskierten Kontonamen, ohne IBANs, Salden oder Passwörter – zum Weitergeben bei Problemen.</div>`;
  return h;
}
const posRow = (k, v) => `<div class="row tight pos-row"><input type="text" class="p-kat" value="${esc(k)}" placeholder="Kategorie oder Oberkategorie"><input type="text" class="p-pos" value="${esc(v)}" placeholder="z. B. Sonderausgaben: Vorsorge"><button class="danger small del-row">×</button></div>`;
function collectSettings() {
  const cfg = JSON.parse(JSON.stringify(S.CFG));
  cfg.probelauf = $('#e-probelauf').checked; cfg.mitteilungen = $('#e-mitt').checked;
  cfg.zeitplan = { automatisch: $('#e-auto').checked, intervall_minuten: Math.max(5, parseInt($('#e-intervall').value) || 30) };
  cfg.bilanz = Object.assign(cfg.bilanz || {}, { monate_zurueck: parseInt($('#e-monate').value) || 0 });
  delete cfg.bilanz.wurzel;
  cfg.moneymoney = Object.assign(cfg.moneymoney || {}, { kategorisieren_erlauben: $('#e-mm-cat').checked }); delete cfg.moneymoney.aktualisieren_erlauben;
  cfg.belege = Object.assign(cfg.belege || {}, { ordner: $('#e-bl-ordner').value.trim() || '~/Documents/Kontor-Belege', unterordner: $('#e-bl-sub').value.trim() || '{jahr}', kommentar_schreiben: $('#e-bl-comment').checked,
    ordner_bestaetigt: !!(cfg.belege || {}).ordner_bestaetigt || $('#e-bl-ordner').value.trim() !== ((S.CFG.belege || {}).ordner || '') });    // ein hier gewählter Ordner gilt als bestätigt
  cfg.steuer = Object.assign(cfg.steuer || {}, { vermietung_kategorie: $('#e-verm').value.trim() || 'Vermietung',
    objekt_darlehen: Object.fromEntries($$('.e-obj').map(i => [i.dataset.ref, i.value.trim()]).filter(([, v]) => v)),
    positionen: Object.fromEntries($$('.pos-row').map(r => [$('.p-kat', r).value.trim(), $('.p-pos', r).value.trim()]).filter(([k, v]) => k && v)) });
  cfg.updates = { taeglich_pruefen: $('#e-up-auto').checked, repo: $('#e-up-repo').value.trim() || 'stecrz/Kontor' };
  cfg.oberflaeche = Object.assign(cfg.oberflaeche || {}, { sperre_minuten: Math.max(1, parseInt($('#e-sperre').value) || 15), touchid: $('#e-touchid').checked, bind: $('#e-bind').value.trim() || '127.0.0.1',
    port: parseInt($('#e-port').value) || 8765, tls_cert: $('#e-cert').value.trim(), tls_key: $('#e-key').value.trim() });
  return cfg;
}

// ---------------------------------------------------------------- Pakete
let PKG = null, PKG_UNRES = null;
function vPakete() {
  const C = S.CFG;
  let h = `<div class="note">Ein Einstellungspaket ist eine Datei <code>Name.kontor.json</code> mit Regeln, Bereichen, Positionen, Immobilien, Kategorie- und Steuerzuordnungen – ohne Passwörter, ohne Adresse/Port, ohne Daten. Damit lässt sich eine Konfiguration weitergeben (z. B. an einen Geschäftspartner mit ähnlicher Kontenstruktur) oder sichern. Beim Laden werden Konten über UUID oder Namen zugeordnet; was nicht gefunden wird, ordnest du hier zu. Eine vollständige <b>Sicherung</b> (<code>….kontor-sicherung.json</code> aus Einstellungen → Sicherung) lädst du über dieselbe Fläche – sie ersetzt alles. ${hq('paket')}</div>
  <h2>Exportieren</h2><div class="row"><label>Name <input type="text" id="pk-name" value="Kontor-Einstellungen"></label><label class="chk"><input type="checkbox" id="pk-nouuid"> ohne UUIDs (nur Kontonamen – für andere MoneyMoney-Installationen)</label><label class="chk"><input type="checkbox" id="pk-plan"> Planung mitnehmen</label><button id="pk-export" class="small">Paket herunterladen</button></div>
  <div class="small muted">Aktuell: ${(C.darlehen || []).length} Darlehen, ${(C.beteiligungen || []).length} Beteiligungen, ${(C.saldo_spiegel || []).length} Spiegel, ${Object.keys((C.kapitalfluss || {}).kategorie_zuordnung || {}).length} Kategoriezuordnungen.</div>
  <h2>Laden</h2><div class="drop" id="pk-drop">Paketdatei hierher ziehen<br><button id="pk-pick" class="small" style="margin-top:8px">Datei wählen</button></div><div id="pk-preview"></div>`;
  return h;
}
function pkgPreview() {
  const el = $('#pk-preview'); if (!PKG) { el.innerHTML = ''; return; }
  const c = PKG.config || {};
  let h = `<div class="card" style="margin-top:12px"><h3>${esc(PKG.name || 'Paket')} <span class="muted">· Version ${esc(PKG.version || '?')} · ${esc(PKG.erstellt || '')}</span></h3>
    <div class="small">${(c.darlehen || []).length} Darlehen, ${(c.beteiligungen || []).length} Beteiligungen, ${(c.saldo_spiegel || []).length} Spiegel, ${Object.keys((c.kapitalfluss || {}).kategorie_zuordnung || {}).length} Kategoriezuordnungen, ${Object.keys((c.steuer || {}).positionen || {}).length} Steuerpositionen${PKG.plan ? ', Planung enthalten' : ''}.</div>
    <div class="row tight" style="margin-top:8px"><div class="seg" id="pk-mode"><button data-m="ergaenzen" class="on">Ergänzen (Regeln hinzufügen, Zuordnungen überschreiben)</button><button data-m="ersetzen">Ersetzen (vorhandene Regeln verwerfen)</button></div>${PKG.plan ? '<label class="chk"><input type="checkbox" id="pk-withplan"> Planung übernehmen</label>' : ''}<button id="pk-import" class="small">Übernehmen</button></div>`;
  if (PKG_UNRES && PKG_UNRES.length) {
    h += '<h3 style="margin-top:12px">Nicht gefundene Konten zuordnen</h3><div class="list">' + PKG_UNRES.map((u, i) => `<div class="row tight"><span style="min-width:280px"><b>${esc(u.label)}</b> <span class="small muted">(${esc(u.feld)})</span></span><select class="pk-map" data-ref="${esc(u.ref)}">${acctOptions('')}</select></div>`).join('') + '</div><div class="row tight"><button id="pk-import2" class="small">Mit Zuordnung übernehmen</button><button id="pk-force" class="small secondary">Ohne Zuordnung übernehmen (Namen bleiben stehen)</button></div>';
  }
  el.innerHTML = h + '<div id="pk-report" class="findings"></div></div>';
  let mode = 'ergaenzen';
  $$('#pk-mode button').forEach(b => b.onclick = () => { $$('#pk-mode button').forEach(x => x.classList.remove('on')); b.classList.add('on'); mode = b.dataset.m; });
  const doImport = async (mapping, force) => {
    try {
      const r = await api('/api/package/import', {paket: PKG, modus: mode, zuordnung: mapping || {}, trotzdem: !!force, mit_plan: !!($('#pk-withplan') && $('#pk-withplan').checked)});
      if (!r.ok) { PKG_UNRES = r.unaufgeloest; pkgPreview(); showFindings($('#pk-report'), [], r.hinweis + ' (' + r.unaufgeloest.length + ' offen)', 'warnung'); return; }
      S.CFG = r.config; PKG_UNRES = null; showFindings($('#pk-report'), r.befunde, 'Übernommen: ' + r.bericht.join(' · '), 'ok'); toast('Paket übernommen');
    } catch (e) { showFindings($('#pk-report'), [], e.message, 'fehler'); }
  };
  $('#pk-import').onclick = () => doImport({}, false);
  const i2 = $('#pk-import2'); if (i2) i2.onclick = () => doImport(Object.fromEntries($$('.pk-map').map(s => [s.dataset.ref, s.value]).filter(([, v]) => v)), false);
  const i3 = $('#pk-force'); if (i3) i3.onclick = () => doImport(Object.fromEntries($$('.pk-map').map(s => [s.dataset.ref, s.value]).filter(([, v]) => v)), true);
}
async function readPkgFile(file) {
  try {
    const obj = JSON.parse(await file.text());
    if (obj.kontor_sicherung) {
      const teile = ['Einstellungen', obj.plan ? 'Planung' : '', obj.kategorien ? 'Kategorien' : '', obj.historie ? 'Verlauf' : '', obj.belege ? 'Belegindex' : ''].filter(Boolean).join(', ');
      if (!confirm('Sicherung vom ' + (obj.erstellt || '?') + ' (Version ' + (obj.version || '?') + ') wiederherstellen? Ersetzt: ' + teile + '.')) return;
      const r = await api('/api/backup/restore', {sicherung: obj});
      S.CFG = r.config; toast('Sicherung geladen: ' + r.teile.join(', '), 6000); await loadAll(); route(); return;
    }
    PKG = obj; if (!PKG.config) { if (PKG.darlehen || PKG.bilanz) PKG = {kontor_paket: 1, name: file.name, config: PKG}; else throw new Error('kein Kontor-Paket'); } PKG_UNRES = null; pkgPreview(); }
  catch (e) { toast('Datei unlesbar: ' + e.message, 5000); }
}

// ---------------------------------------------------------------- Updates
async function vUpdates() {
  const r = await api('/api/update/status'), st = S.STATUS, info = r.info;
  let h = `<div class="cards"><div class="card"><div class="l">Installiert</div><div class="v">${esc(r.version)}</div><div class="d">Programmordner wird beim Update ersetzt, Datenordner und Einstellungen bleiben.</div></div>
    <div class="card"><div class="l">Verfügbar</div><div class="v">${info ? (info.fehler ? '<span class="pill err">?</span>' : esc(info.verfuegbar || '–')) : '–'}</div><div class="d">${info ? (info.fehler ? esc(info.fehler) : (info.neuer ? '<span class="pill ok">neuer als installiert</span>' : 'Kontor ist aktuell') + ' · Quelle: ' + esc(info.quelle || '')) : 'noch nicht geprüft'}${r.geprueft ? ' · geprüft ' + new Date(r.geprueft * 1000).toLocaleString('de-DE') : ''}</div></div></div>
    <div class="actions"><button id="up-check" class="secondary">Jetzt prüfen</button><button id="up-install" ${info && info.neuer && st.lokal ? '' : 'disabled'}>Update installieren und Dienst neu starten</button></div>
    ${info && info.notizen ? '<h2>Änderungen</h2><pre class="log">' + esc(info.notizen) + '</pre>' : ''}
    <div class="note">Die Prüfung fragt nur GitHub (${esc((S.CFG.updates || {}).repo || 'stecrz/Kontor')}) nach der neuesten Version; sonst verbindet sich Kontor mit keinem Server. Maßgeblich ist die Datei VERSION im Hauptzweig. Beim Installieren wird dieser Stand als Archiv von github.com geladen, der Programmordner ersetzt (alte Dateien unter <code>.alt</code>) und der Dienst neu gestartet; ist der Programmordner ein Git-Klon, läuft stattdessen <code>git pull</code>. Die Seite lädt danach neu. Manuell: <code>bash &lt;(curl -fsSL https://raw.githubusercontent.com/${esc((S.CFG.updates || {}).repo || 'stecrz/Kontor')}/main/get.sh)</code> im Terminal – installiert und aktualisiert gleichermaßen. Alle Schritte stehen im Protokoll.</div>`;
  return h;
}

// ---------------------------------------------------------------- Protokoll / Hilfe
async function vProtokoll() {
  const r = await api('/api/log?n=500');
  const ordner = (S.STATUS && S.STATUS.ablage && S.STATUS.ablage.ordner) || '~/Library/Application Support/Kontor';
  return `<div class="toolbar"><button id="log-refresh" class="secondary small">Aktualisieren</button><button id="diag2" class="secondary small">Diagnosedatei (maskiert)</button><button id="diag3" class="secondary small">Diagnosedatei (mit Kontonamen)</button>${S.STATUS && S.STATUS.lokal ? '<button id="log-show" class="secondary small">Im Finder zeigen</button>' : ''}</div>
    <div class="note">Datei: <code>${esc(ordner)}/kontor.log</code> (Klartext, rotiert bei 5 MB; daneben <code>dienst.err.log</code> für Abstürze des Dienstes). Zur Fehlersuche diese Datei oder die Diagnosedatei schicken – sie enthalten keine IBANs, Salden oder Passwörter. Ist die Oberfläche nicht erreichbar: Finder → Gehe zu → Ordner … → <code>~/Library/Application Support/Kontor</code>.</div><pre class="log">` + esc(r.zeilen.join('\n')) + '</pre>';
}
function vHilfe() {
  return `<div class="help">
  <h2>Was macht MoneyMoney, was macht Kontor?</h2>
  <table class="plain"><thead><tr><th>MoneyMoney</th><th>Kontor</th></tr></thead><tbody>
  <tr><td>Holt Umsätze und Salden von Banken, Depots, PayPal usw. (auch über Erweiterungen).</td><td>Liest diese Daten über die Skript-Schnittstelle – nur lesend, nie Zugangsdaten.</td></tr>
  <tr><td>Kategorisiert Umsätze (von Hand oder per Regel) und führt Budgets.</td><td>Wertet die Kategorien aus (Kapitalfluss, Steuer) und nutzt Budgets als Planmethode. Kategorien werden nie angelegt, umbenannt oder gelöscht. Auf Wunsch (Einstellung) darf Kontor einzelnen Umsätzen eine Kategorie zuweisen.</td></tr>
  <tr><td>Führt Offline-Konten (manuell): Darlehen, Beteiligungen, Immobilien, Kapitalkonten.</td><td>Bucht nach deinen Regeln in <b>genau diese Offline-Konten</b>: Darlehensraten spiegeln, Zinsen berechnen, Beteiligungswerte fortschreiben. Jede Buchung ist markiert und wird nie doppelt angelegt; bestehende Buchungen werden nie geändert oder gelöscht. Echte Bankkonten werden nie bebucht; Überweisungen sind technisch gesperrt.</td></tr>
  <tr><td>Ruft Konten bei den Banken ab (von Hand oder nach Zeitplan in MoneyMoney).</td><td>Verwendet, was MoneyMoney hat, und zeigt beide Stände: letzter Bankabruf und wann Kontor zuletzt gelesen hat (unten links). „Synchronisieren“ liest sofort neu.</td></tr>
  <tr><td>Hat keine Bilanz-/Planungs-/Steuer-Sicht.</td><td>Bilanz je Bereich nach Positionen, Kapitalfluss mit Prüfzeile, Planung (rollierend aus der Vergangenheit, je Zeile anpassbar, Ereignisse), Immobilienkalkulationen, Steuer-Jahresübersicht, Depots, Belege zu Umsätzen, Excel-Export.</td></tr>
  </tbody></table>
  <h2>Bereiche, Positionen, Verlauf</h2>
  <ul><li><b>Bereich</b> = frei zusammengestellte Konten (Privat, jede Gesellschaft). Vorschlag: jede Kontengruppe der obersten Ebene; die Gruppierung in MoneyMoney ist keine Voraussetzung. Einrichtung → Bereiche.</li>
  <li><b>Position</b> = Zeile in der Bilanz (Liquidität, Wertpapiere, Geldanlagen, Immobilien, Beteiligungen, Sachwerte, Forderungen, Sonstiges, Verbindlichkeiten). Vorschlag aus Gruppenname und Kontotyp, je Konto überschreibbar. Einrichtung → Konten.</li>
  <li><b>Verlauf</b> = woher die Monatsstände kommen: aus den Umsätzen (rückwärts vom aktuellen Saldo gerechnet – Startsalden sind unerheblich) oder aus Kontoständen (Depots, Konten ohne Umsatzhistorie: Kontor zeichnet monatlich auf). Fehlende ältere Depotstände schätzt Kontor aus Käufen/Verkäufen des Verrechnungskontos (Kennzeichen „geschätzt bis“); genauer: Monatsstände eintragen (Klick auf das Konto in der Bilanz) oder eine Datei importieren (Einrichtung → Konten: CSV/Excel, z. B. eine eigene Vermögensübersicht oder Werte aus Depotauszügen).</li>
  <li><b>Konten bestätigen</b>: Bereich, Position und Verlauf jedes Kontos werden einmal bestätigt und bleiben dann fest – auch wenn du das Konto in MoneyMoney umbenennst, umgruppierst oder den Kontotyp änderst. Neue Konten erscheinen als „neu“ (Hinweis in der Übersicht), bis du sie bestätigst.</li>
  <li><b>Ausgeblendete Konten</b>: Anzeige „nach Aktivität“ blendet Konten ohne Bestand und Umsatz seit N Monaten aus (laufend geprüft); „ausblenden“ / „immer anzeigen“ legt es je Konto fest. Sie zählen in allen Summen und in der Historie.</li></ul>
  <h2>Immobilien</h2>
  <ul><li>Je Objekt mehrere Kalkulationen (Szenarien); die aktive gilt für Planung, Steuer (AfA) und Übersicht. Ergebnisse erscheinen beim Tippen; „Speichern“ sichert die Eingaben.</li>
  <li>Darlehen: Annuität (feste Rate), Tilgungsdarlehen, endfällig. Abrechnung monatlich (Bank: Zins auf den laufenden Saldo) oder jährlich (Zins auf den Stand 1. Januar, z. B. Verkäuferdarlehen). Sondertilgungen laufend ab einem Monat oder einzeln; Zinsbindung mit Anschlusszins; Fälligkeit mit Rückzahlung aus Liquidität oder als offener Hinweis.</li>
  <li>Indexmiete: Erhöhung zum Jahresbeginn um Faktor × VPI-Änderung seit der letzten Anpassung, sobald die Schwelle überschritten ist. Kosten steigen wahlweise mit dem VPI.</li>
  <li>Steuer: Ergebnis = Miete − Kosten − abziehbare Zinsen − AfA − sofort abziehbare Nebenkosten; Steuer je Gesellschafter = Anteil × Ergebnis × Steuersatz; Ausschüttung = pauschaler Anteil des positiven Ergebnisses. Cashflow = Miete − Kosten − Rücklage − Zinsen − Tilgung − Ausschüttung. Vermögensaufbau = Cashflow + Tilgung. EK-Rendite = Vermögensaufbau / (Eigenkapital + Nebenkosten + bisheriger Vermögensaufbau).</li>
  <li>Verknüpfung mit MoneyMoney: Vermietungskategorie und Darlehenskonten → Soll/Ist je Jahr; Objektkonto → Wert in der Bilanz; „in Planung übernehmen“ → Planung des Bereichs. Dokumente werden nur verlinkt (Pfad auf dem Mac, auch iCloud Drive), nie kopiert oder gelöscht.</li></ul>
  <h2>Kategorien</h2>
  <ul><li>Kontor führt eigene Kategorien (Menü „Kategorien“): der Baum wird einmal aus MoneyMoney übernommen und ist frei erweiterbar. Zuordnung je Umsatz liegt in Kontor; Rangfolge: manuell &gt; eigene Regel &gt; gelernte Regel &gt; Kategorie aus MoneyMoney.</li>
  <li>Regeln lernt Kontor aus den vorhandenen Zuordnungen (Gegen-IBAN, Name, Name + Zweckanfang; ab 2 Umsätzen und 90 % Eindeutigkeit) – bei jedem Abgleich nach. Eigene Regeln: Name/Zweck enthält, IBAN, Richtung, Konto.</li>
  <li>„Zuordnen“ zeigt alle Umsätze ohne Kategorie, gruppiert nach Gegenpartei mit Vorschlag; Zuordnen + Regel erledigt die Gegenpartei dauerhaft. „Umbuchung“ für Überträge zwischen eigenen Konten.</li>
  <li>Ohne Kategorien funktionieren Bilanz, Vermögensentwicklung, Immobilien und Darlehen vollständig; Einnahmen/Ausgaben gesamt ebenfalls (Umbuchungen werden an Gegen-IBAN und Betrag erkannt). Kategorien braucht es nur für die Aufteilung (Kapitalfluss-Zeilen, Planung je Zeile, Steuer).</li>
  <li>Optional schreibt Kontor eine Zuordnung auch nach MoneyMoney (Einstellung „Kategorisieren erlauben“, Häkchen „auch in MoneyMoney“) – nur das Kategoriefeld des Umsatzes.</li></ul>
  <h2>Planung: Ereignisse</h2>
  <p>Umschichtung = Betrag wandert von „Von“ nach „Nach“ (Konto leer = Liquidität des Bereichs): z. B. Darlehen auf einen Schlag aus dem Depot zurückzahlen (Von = Depot, Nach = Darlehenskonto). Einnahme/Ausgabe = zahlungswirksam. Wiederholung einmalig, monatlich, je Quartal, jährlich – bis zum Enddatum oder Horizont. Beteiligungskonten lassen sich an das geplante Nettovermögen eines anderen Bereichs koppeln (Wertentwicklung → Kopplung).</p>
  <h2>Berechtigungen, die macOS abfragt</h2>
  <ul><li><b>Automation → MoneyMoney</b> (beim ersten „Verbindung prüfen“ oder Abgleich): Kontor liest darüber Konten, Umsätze, Kategorien und Depotpositionen aus MoneyMoney – nur lesend. Geschrieben wird ausschließlich in Offline-Konten, die du in Regeln benennst. Bank-Zugangsdaten sieht Kontor nie. Ohne diese Freigabe kann Kontor nichts auswerten.</li>
  <li><b>Automation → System Events</b> („Datei wählen …“): öffnet den macOS-Dateidialog, damit du Belege oder Dokumente verknüpfen kannst.</li>
  <li><b>Schlüsselbund</b>: Der Schlüssel für die verschlüsselte Ablage liegt im Login-Schlüsselbund; macOS fragt ggf. einmal nach Zugriff.</li></ul>
  <h2>Protokoll und Fehlersuche</h2>
  <p>Das Protokoll liegt als Klartext unter <code>~/Library/Application Support/Kontor/kontor.log</code> (Finder → Gehe zu → Ordner …), daneben <code>dienst.err.log</code>. Seite „Protokoll“ zeigt die letzten Zeilen und kann die Datei im Finder zeigen; die Diagnosedatei enthält Protokoll plus maskierte Konfiguration. Beides enthält keine IBANs, Salden oder Passwörter. Ein Berichtsneubau nach Änderungen läuft im Hintergrund (Status unten links); die Ansicht lädt sich danach selbst neu.</p>
  <h2>iPhone und Offline-Ansicht</h2>
  <p>Tailscale auf Mac und iPhone, dann am Mac im Terminal <code>python3 ~/Kontor/kontor.py tls</code>: holt ein Zertifikat für den Tailscale-Namen des Macs, trägt Adresse und Zertifikat ein und startet den Dienst neu (in der Tailscale-Admin-Konsole müssen MagicDNS und „HTTPS Certificates“ an sein). Am iPhone die angezeigte https-Adresse öffnen und „Zum Home-Bildschirm“. Die App behält die zuletzt geladenen Daten: ist der Mac aus oder nicht erreichbar, öffnet das Passwort diese Kopie – nur lesen, Stand des letzten Abrufs. Sobald der Mac wieder erreichbar ist, lädt die App frische Daten. Einstellungen → „Gespeicherte Daten auf diesem Gerät löschen“ entfernt die Kopie.</p>
  <h2>Sicherung und Zurücksetzen</h2>
  <p>Einstellungen → Sicherung herunterladen: eine Datei mit Konfiguration, Planung, Kategorien, Verlauf und Belegindex (ohne Passwort und Umsätze). Wieder einspielen unter Pakete (Datei wählen). Zurücksetzen löscht Konfiguration, Planung, Kategorien, Verlauf und Auswertungen (wahlweise auch das Passwort) – nur am Mac und mit Passwort; Belegdateien, Schlüssel und Protokoll bleiben.</p>
  <h2>Sicherheit</h2>
  <ul><li>Die Oberfläche ist nur auf diesem Mac erreichbar (127.0.0.1) oder optional über eine Tailscale-Adresse – nie aus dem Internet.</li>
  <li>Alle Daten im Datenordner sind mit AES-256 verschlüsselt; der Schlüssel liegt im macOS-Schlüsselbund. Belege liegen als normale Dateien im Belegordner.</li>
  <li>Keine Verbindung zu externen Servern außer der abschaltbaren Update-Prüfung bei GitHub. Keine Telemetrie.</li>
  <li>Passwort, Touch ID, automatische Sperre, Schutz gegen Rateversuche; Buchen, Updates und Dateizugriffe nur am Mac.</li>
  <li>Das Protokoll enthält keine IBANs, Salden oder Passwörter; die Diagnosedatei maskiert zusätzlich Kontonamen.</li></ul>
  <h2>Typische Meldungen</h2>
  <ul><li><b>MoneyMoney läuft nicht / Datenbank gesperrt</b> – MoneyMoney öffnen und entsperren; Kontor wartet.</li>
  <li><b>Keine Berechtigung</b> – Systemeinstellungen → Datenschutz &amp; Sicherheit → Automation: dem Programm (Terminal bzw. python3) den Zugriff auf MoneyMoney erlauben.</li>
  <li><b>Konto nicht gefunden</b> – ein in einer Regel verwendetes Konto wurde in MoneyMoney gelöscht oder das Paket stammt von einer anderen Installation: unter Regeln bzw. Pakete neu zuordnen.</li>
  <li><b>Prüfzeile ≠ 0</b> – eine Vermögensänderung ist nicht erklärt: fehlende Kategorie, fehlende Gegenbuchung oder manuelle Buchung ohne Markierung.</li>
  <li><b>Keine passende Zahlung</b> – die Darlehensregel findet die Rate nicht: Gegen-IBAN/Text prüfen, Quellkonto prüfen.</li>
  <li><b>Kontostände vor … fortgeschrieben</b> – für ein Konto mit Verlaufsquelle „Kontostände“ fehlen ältere Monatswerte: in der Bilanz auf das Konto klicken und Werte eintragen oder importieren.</li>
  <li><b>Datei liegt in iCloud</b> – die verknüpfte Datei ist nur in der Cloud; „Öffnen“ lädt sie herunter (oder im Finder auf die Wolke klicken).</li></ul>
  <h2>Kommandozeile</h2>
  <p><code>python3 kontor.py check</code> (Konfiguration prüfen) · <code>run --dry-run</code> · <code>accounts</code> (Kontenbaum mit UUIDs) · <code>package-export</code> / <code>package-import DATEI</code> · <code>diagnostics</code> · <code>update --install</code> · <code>install</code> (Dienst einrichten, jederzeit wiederholbar).</p>
  </div>`;
}

// ---------------------------------------------------------------- Steuerung
const TITLES = {uebersicht: 'Übersicht', bilanz: 'Bilanz', kapitalfluss: 'Kapitalfluss', planung: 'Planung', buchungen: 'Buchungen', steuer: 'Steuer', immobilien: 'Immobilien', depots: 'Depots', umsaetze: 'Umsätze & Belege', zuordnen: 'Zuordnen', einrichtung: 'Einrichtung', regeln: 'Regeln', kategorien: 'Kategorien', einstellungen: 'Einstellungen', synchronisierung: 'Synchronisierung', pakete: 'Pakete', updates: 'Updates', protokoll: 'Protokoll', hilfe: 'Hilfe'};
const SUBTITLES = {};
async function route() {
  if (DIRTY.on && location.hash !== DIRTY.hash) {
    if (!confirm('Ungespeicherte Änderungen verwerfen?')) { history.replaceState(null, '', DIRTY.hash || '#uebersicht'); return; }
    DIRTY.on = false;
  }
  const raw = (location.hash || '#uebersicht').slice(1), [path, qs] = raw.split('?'), [tab, sub] = path.split('/');
  const y0 = window.scrollY;
  if (SCROLL.key) SCROLL.pos[SCROLL.key] = y0;                 // Position des bisherigen Reiters merken
  S.tab = TITLES[tab] ? tab : 'uebersicht'; S.sub = sub || '';
  const key = S.tab + '/' + S.sub, sameTab = key === SCROLL.key;
  if (qs && S.tab === 'umsaetze') { const p = new URLSearchParams(qs); S.uf.ohne_kategorie = p.get('ohne_kategorie') === '1'; S.uf.ohne_beleg = p.get('ohne_beleg') === '1'; if (p.get('jahr')) S.uf.jahr = p.get('jahr'); if (p.get('entitaet')) S.uf.entitaet = p.get('entitaet'); history.replaceState(null, '', '#umsaetze'); }
  $$('#nav a').forEach(a => a.classList.toggle('on', a.getAttribute('href') === '#' + S.tab));
  $('#page-title').textContent = SUBTITLES[S.tab + '/' + S.sub] || (S.tab === 'immobilien' && S.sub ? 'Immobilie' : TITLES[S.tab]);
  $('#bereich-seg').classList.toggle('hidden', !(S.DATA && Object.keys(S.DATA.bereiche || {}).length > 1 && ['uebersicht', 'bilanz', 'kapitalfluss', 'planung'].includes(S.tab)));
  topCtl();
  $('.side').classList.remove('open');
  if (S.tab !== 'umsaetze') closeDrawer();
  const main = $('#main');
  const myRoute = ++ROUTE_SEQ;
  const slow = setTimeout(() => { if (ROUTE_SEQ === myRoute) main.innerHTML = `<div class="loading"><span class="spin"></span>${esc(TITLES[S.tab] || '')} wird geladen …<div class="note">Der Dienst antwortet noch nicht – er arbeitet gerade (z. B. Bericht wird neu gebaut) oder MoneyMoney liest.</div></div>`; }, 400);
  try {
    let h = '';
    if (S.tab === 'uebersicht') h = await vUebersicht();
    else if (S.tab === 'bilanz') h = vBilanz();
    else if (S.tab === 'kapitalfluss') h = vKapitalfluss(false);
    else if (S.tab === 'planung') h = vKapitalfluss(true);
    else if (S.tab === 'buchungen') h = vBuchungen(await api('/api/runs'));
    else if (S.tab === 'steuer') h = vSteuer();
    else if (S.tab === 'immobilien') h = vImmobilien(S.sub);
    else if (S.tab === 'einrichtung') h = vEinrichtung(S.sub);
    else if (S.tab === 'depots') h = vDepots();
    else if (S.tab === 'umsaetze') h = await vUmsaetze();
    else if (S.tab === 'regeln') h = vRegeln();
    else if (S.tab === 'kategorien') h = await vKategorien();
    else if (S.tab === 'zuordnen') h = await vZuordnen();
    else if (S.tab === 'einstellungen') h = vEinstellungen();
    else if (S.tab === 'synchronisierung') h = await vSync();
    else if (S.tab === 'pakete') h = vPakete();
    else if (S.tab === 'updates') h = await vUpdates();
    else if (S.tab === 'protokoll') h = await vProtokoll();
    else if (S.tab === 'hilfe') h = vHilfe();
    clearTimeout(slow);
    if (ROUTE_SEQ !== myRoute) return;          // inzwischen woanders hin geklickt
    main.innerHTML = `<div class="fade">${h}</div>`;
    SCROLL.key = key;
    window.scrollTo(0, sameTab ? y0 : (SCROLL.pos[key] || 0));      // eigener Reiter: bleibt; anderer Reiter: dessen letzte Position, sonst oben
    bind(main);
    guardDirty(main);
    vbPoll(); mmhPoll();
    if (S.tab === 'immobilien') bindImmo(main);
    if (S.tab === 'zuordnen') bindZuordnen(main);
    if (S.tab === 'kategorien') { bindKontorKategorien(main); $$('.tabs button[data-kt]', main).forEach(b => b.addEventListener('click', () => { KZ.tab = b.dataset.kt; route(); })); }
  } catch (e) { clearTimeout(slow); if (ROUTE_SEQ === myRoute && e.message !== 'nicht angemeldet') main.innerHTML = `<div class="banner err">${esc(e.message)} <button class="small secondary" onclick="route()">Erneut versuchen</button></div>`; }
}
let ROUTE_SEQ = 0;
const SCROLL = {key: '', pos: {}};
// Ungespeicherte Aenderungen: Formulare auf Seiten mit Speichern-Knopf melden Aenderungen; Wegnavigieren fragt nach
const DIRTY = {on: false, hash: location.hash};
const GUARDED = ['einrichtung/bereiche', 'einrichtung/konten', 'einstellungen', 'regeln'];
const guarded = () => GUARDED.includes(S.tab + (S.sub ? '/' + S.sub : ''));
(function dirtyListeners() {
  // einmal am Hauptbereich (bleibt bestehen); ob die Seite geschuetzt ist, wird beim Ereignis geprueft
  const main = $('#main');
  const mark = e => { if (!guarded() || e.target.closest('#hi-preview, .toolbar') || e.target.id === 'k-show-inactive') return; DIRTY.on = true; };
  main.addEventListener('input', mark); main.addEventListener('change', mark);
  main.addEventListener('click', e => { if (guarded() && e.target.closest('.del, #add-bereich, .add-item, .b-mv')) DIRTY.on = true; });
})();
function guardDirty(main) {
  DIRTY.on = false; DIRTY.hash = location.hash;
  $$('[data-next]', main).forEach(b => b.addEventListener('click', () => { location.hash = b.dataset.next; }));     // Rueckfrage bei Ungespeichertem: route()
  $$('[data-savenext]', main).forEach(b => b.addEventListener('click', async () => {
    $$('.findings', main).forEach(f => { f.innerHTML = ''; });
    b.disabled = true;
    try {
      if (!(await SAVE[b.dataset.save]())) return;          // Fehler stehen auf der Seite
      await api('/api/report/rebuild', {});
      if (!(await waitRebuild('Auswertung wird mit den gespeicherten Angaben aktualisiert'))) return;
      await loadAll();
      location.hash = b.dataset.savenext;
    } finally { b.disabled = false; }
  }));
}
async function waitRebuild(title) {
  // Ladeanzeige mit Fortschritt, bis die Auswertung im Hintergrund fertig ist. Laufende Streifen und Sekundenzähler zeigen,
  // dass gearbeitet wird; zwischen zwei Meldungen rückt der Balken langsam weiter (nie über die nächste Etappe hinaus)
  const ov = document.createElement('div'); ov.className = 'busy-ov';
  ov.innerHTML = `<div class="box"><div class="t">${esc(title)} …</div><div class="bar"><i style="width:3%"></i></div><div class="s small muted"><span class="st">startet …</span><span class="el"></span></div></div>`;
  document.body.appendChild(ov);
  const t0 = Date.now(), P = {ziel: 0.03, zeige: 0.03};
  const tick = setInterval(() => {
    const sec = Math.round((Date.now() - t0) / 1000); $('.el', ov).textContent = sec >= 2 ? sec + ' s' : '';
    P.zeige = Math.min(Math.max(P.zeige, P.ziel) + 0.004, P.ziel + 0.06, 0.97);          // langsam weiter bis kurz vor die nächste Meldung
    $('.bar i', ov).style.width = Math.round(P.zeige * 100) + '%';
  }, 500);
  try {
    for (let i = 0; i < 1500; i++) {
      await new Promise(r => setTimeout(r, i < 5 ? 150 : 400));
      let st; try { st = await api('/api/status'); } catch (e) { continue; }
      S.STATUS = st; const b = st.bericht || {};
      if (!b.laeuft) {
        if (b.fehler) { toast('Auswertung konnte nicht aktualisiert werden: ' + b.fehler, 8000); return false; }
        clearInterval(tick); $('.bar i', ov).style.width = '100%'; await new Promise(r => setTimeout(r, 200));
        BER.stand = b.stand || ''; return true;
      }
      const f = b.fortschritt || {};
      if ((f.anteil || 0) > P.ziel) { P.ziel = f.anteil; P.zeige = Math.max(P.zeige, P.ziel); }
      $('.st', ov).textContent = (f.schritt || 'läuft') + ' · ' + Math.round(P.ziel * 100) + ' %';
    }
    toast('Die Auswertung dauert ungewöhnlich lange – sie läuft im Hintergrund weiter.', 8000); return true;
  } finally { clearInterval(tick); ov.remove(); }
}
// Speichern je Einrichtungsschritt (true = gespeichert)
const SAVE = {
  bereiche: async () => {
    const f = $('#findings-b'), cfg = collectBereiche();
    if (!cfg.bereiche.length) { showFindings(f, [], 'Mindestens ein Bereich ist nötig.', 'fehler'); return false; }
    if (cfg.bereiche.some(b => !b.name)) { showFindings(f, [], 'Jeder Bereich braucht einen Namen.', 'fehler'); return false; }
    if (cfg.bereiche.some(b => !b.konten.length)) { showFindings(f, [], 'Jeder Bereich braucht mindestens ein Konto oder eine Gruppe.', 'fehler'); return false; }
    return saveConfig(cfg, f);
  },
  konten: async () => saveConfig(collectKonten(), $('#findings-k2')),
};
window.addEventListener('beforeunload', e => { if (DIRTY.on) { e.preventDefault(); e.returnValue = ''; } });
function bind(main) {
  $$('tr.group[data-id]', main).forEach(tr => tr.addEventListener('click', () => { S.collapsed[tr.dataset.id] = !S.collapsed[tr.dataset.id]; route(); }));
  $$('tr.pos[data-pos]', main).forEach(tr => tr.addEventListener('click', () => { S.posOpen[tr.dataset.pos] = !S.posOpen[tr.dataset.pos]; route(); }));
  const pa = $('#pos-all', main); if (pa) pa.addEventListener('click', () => { const D = B(), pos = D.bilanz.zeilen.filter(r => r.gruppe), open = !pos.every(r => S.posOpen[r.rolle]); pos.forEach(r => { S.posOpen[r.rolle] = open; }); route(); });
  $$('tr.sub[data-gid]', main).forEach(tr => tr.addEventListener('click', () => { S.collapsed[tr.dataset.gid] = !S.collapsed[tr.dataset.gid]; route(); }));
  $$('.card[data-b]', main).forEach(c => c.addEventListener('click', () => { S.bereich = c.dataset.b; bereichSeg(); route(); }));
  // Waagerecht: aktuelle Spalte (Monat bzw. Jahr) rechts im Blick, ältere Jahre links davon; Plan-Spalten rechts anschließend
  if (['bilanz', 'kapitalfluss', 'planung'].includes(S.tab)) $$('.wrap', main).forEach(w => { const c = $('th[data-cur]', w); if (c && w.scrollWidth > w.clientWidth) w.scrollLeft = Math.max(0, c.offsetLeft + c.offsetWidth - w.clientWidth * (S.plan ? 0.62 : 0.97)); });
  const vs = $('#vorschlag-an', main); if (vs) vs.addEventListener('change', e => { S.vorschlag = e.target.checked; route(); });
  $$('[data-xlsx]', main).forEach(b => b.addEventListener('click', () => download(b.dataset.xlsx === 'property' ? `/api/export/property.xlsx?id=${encodeURIComponent(b.dataset.immo || '')}&calculation=${encodeURIComponent(b.dataset.kalk || '')}` : `/api/export/${b.dataset.xlsx}.xlsx?area=${encodeURIComponent(b.dataset.bereich || S.bereich || '')}&mode=${S.modus === 'jahre' ? 'years' : 'months'}`)));

  // Einrichtung
  const wc = $('#w-check', main); if (wc) wc.addEventListener('click', async () => {
    wc.classList.add('busy'); wc.disabled = true; const busy = $('#w-busy'); if (busy) busy.classList.remove('hidden'); $('#w-findings').innerHTML = '';
    let r; try { r = await api('/api/check', {}); } catch (e) { wc.classList.remove('busy'); wc.disabled = false; if (busy) busy.classList.add('hidden'); showFindings($('#w-findings'), [], e.message, 'fehler'); return; }
    if (!r.verfuegbar) { wc.classList.remove('busy'); wc.disabled = false; if (busy) busy.classList.add('hidden'); showFindings($('#w-findings'), [], r.text, 'fehler'); return; }
    S.KONTEN = r.konten; S.KATS = r.kategorien || S.KATS; await route(); showFindings($('#w-findings'), r.befunde, 'Verbindung steht: ' + r.konten.length + ' Konten gelesen.', 'ok'); });
  const wr = $('#w-report', main); if (wr) wr.addEventListener('click', () => rebuildReport(true));
  const abr = $('#add-bereich', main); if (abr) { bindBereichKonten(main); abr.addEventListener('click', () => { $('#bereiche').insertAdjacentHTML('beforeend', bereichForm({name: 'Neuer Bereich', id: '', konten: [], haupt: false}, $$('#bereiche .item').length)); bindDel(main); bindBereichKonten($('#bereiche .item:last-child')); bereichMvState(); }); }
  const bli = $('#bereiche', main); if (bli) {
    bereichMvState();
    bli.addEventListener('click', e => {
      const b = e.target.closest('.b-mv'); if (!b) { if (e.target.closest('.del')) setTimeout(bereichMvState, 0); return; }
      const it = b.closest('.item');
      if (+b.dataset.d < 0 && it.previousElementSibling) it.parentNode.insertBefore(it, it.previousElementSibling);
      else if (+b.dataset.d > 0 && it.nextElementSibling) it.parentNode.insertBefore(it.nextElementSibling, it);
      bereichMvState(); it.classList.remove('moved'); void it.offsetWidth; it.classList.add('moved'); it.scrollIntoView({block: 'nearest', behavior: 'smooth'});
    });
  }
  const sbr = $('#save-bereiche', main); if (sbr) sbr.addEventListener('click', async () => { if (await SAVE.bereiche()) { const box = $('#findings-b').innerHTML; await rebuildReport(false); const f = $('#findings-b'); if (f) f.innerHTML = box; } });
  const skn = $('#save-konten', main); if (skn) skn.addEventListener('click', async () => { if (await SAVE.konten()) { const box = $('#findings-k2').innerHTML; await rebuildReport(false); const f = $('#findings-k2'); if (f) f.innerHTML = box; } });
  $$('.k-hist', main).forEach(b => b.addEventListener('click', async e => { const btn = e.target; btn.classList.add('busy'); try { const tr = btn.closest('tr'), sel = $('.k-verlauf', tr); await openHistDrawer(tr.dataset.uuid, sel ? sel.value : null); } catch (er) { toast('Verlauf konnte nicht geladen werden: ' + er.message, 6000); } finally { btn.classList.remove('busy'); } }));
  const hp = $('#hi-pick', main); if (hp) hp.addEventListener('click', () => { const inp = $('#file-input'); inp.value = ''; inp.setAttribute('accept', '.csv,.txt,.xlsx,.xlsm'); inp.removeAttribute('capture'); inp.onchange = () => { if (inp.files[0]) histImportPreview(inp.files[0]); }; inp.click(); });
  const hd = $('#hi-drop', main); if (hd) { hd.addEventListener('dragover', e => { e.preventDefault(); hd.classList.add('over'); }); hd.addEventListener('dragleave', () => hd.classList.remove('over')); hd.addEventListener('drop', e => { e.preventDefault(); hd.classList.remove('over'); if (e.dataTransfer.files[0]) histImportPreview(e.dataTransfer.files[0]); }); if (HI) renderHistImport(); }
  const mz = $('#mmh-zeigen', main); if (mz) mz.addEventListener('click', async () => { try { await api('/api/history/mm-reveal', {}); } catch (e) { toast(e.message, 6000); } });
  const md = $('#mmh-drop', main); if (md) {
    const send = async file => {
      // Datei (verschlüsselt) direkt als Bytes an den Dienst auf diesem Mac; nichts davon wird gespeichert
      const res = $('#mmh-res', main); if (!file) return;
      if (MMH.busy) return; MMH.busy = true; md.classList.add('busy'); res.innerHTML = '<div class="working"><span class="spin"></span>Datei wird übergeben …</div>';
      try {
        const r = await fetch('/api/history/mm-import', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/octet-stream', 'X-CSRF-Token': S.csrf, 'X-Kontor-Net': 'direct'}, body: file});
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.fehler || ('Fehler ' + r.status));
        if (j.laeuft) await mmhFollow(); else showFindings($('#mmh-res') || res, [], j.text, 'fehler');
      } catch (e) { showFindings($('#mmh-res') || res, [], e.message, 'fehler'); }
      finally { MMH.busy = false; const d2 = $('#mmh-drop'); if (d2) d2.classList.remove('busy'); }
    };
    md.addEventListener('dragover', e => { e.preventDefault(); md.classList.add('over'); });
    md.addEventListener('dragleave', () => md.classList.remove('over'));
    md.addEventListener('drop', e => { e.preventDefault(); md.classList.remove('over'); send(e.dataTransfer.files[0]); });
    $('#mmh-pick', main).addEventListener('click', () => $('#mmh-file', main).click());
    $('#mmh-file', main).addEventListener('change', e => { send(e.target.files[0]); e.target.value = ''; });
  }
  const go = $('#gap-ok', main); if (go) go.addEventListener('click', async () => { try { await api('/api/sync/gaps', {}); S.STATUS = await api('/api/status'); statusMini(); route(); } catch (e) { toast(e.message, 5000); } });
  $$('.dep-hist', main).forEach(b => b.addEventListener('click', async () => { b.classList.add('busy'); try { await openHistDrawer(b.closest('tr').dataset.uuid); } catch (e) { toast(e.message, 6000); } finally { b.classList.remove('busy'); } }));
  const sn = $('#sync-now', main); if (sn) sn.addEventListener('click', async () => { sn.classList.add('busy'); try { await syncNow(); } finally { sn.classList.remove('busy'); } });
  $$('.ab-chk', main).forEach(cb => cb.addEventListener('change', async () => {
    try { await api('/api/sync', {konto: cb.closest('tr').dataset.uuid, abgerufen: cb.checked}); S.STATUS = await api('/api/status'); statusMini(); route(); }
    catch (e) { toast(e.message, 5000); cb.checked = !cb.checked; }
  }));
  const ksi = $('#k-show-inactive', main); if (ksi) ksi.addEventListener('change', e => $$('tr.inactive', main).forEach(tr => tr.style.display = e.target.checked ? '' : 'none'));
  $$('.k-show', main).forEach(sel => sel.addEventListener('change', () => { const tr = sel.closest('tr'); tr.classList.toggle('inactive', kontoHidden(sel.value, tr.dataset.auto === '1')); }));
  $$('.acct-table select[data-vor]', main).forEach(sel => sel.addEventListener('change', () => {
    sel.classList.toggle('vorschlag', sel.closest('tr').classList.contains('neu') && sel.value === sel.dataset.vor);
    const hint = sel.parentElement.querySelector('.vor-hint'); if (hint) hint.classList.toggle('hidden', sel.value === sel.dataset.vor);
  }));
  const kin = $('#k-inaktiv', main); if (kin) kin.addEventListener('input', () => $$('tr[data-grenze]', main).forEach(tr => {   // ausgegraut sofort neu
    tr.dataset.auto = autoHidden(tr.dataset.grenze, kin.value) ? '1' : '0';
    const on = kontoHidden($('.k-show', tr).value, tr.dataset.auto === '1'); tr.classList.toggle('inactive', on);
    if (!$('#k-show-inactive', main).checked) tr.style.display = on ? 'none' : '';
  }));

  // Bilanz
  $$('tr.acct[data-id]', main).forEach(tr => tr.addEventListener('click', () => openHistDrawer(tr.dataset.id)));
  $$('.seg button[data-v]', main).forEach(b => b.addEventListener('click', () => { S.bilanzView = b.dataset.v; route(); }));
  const shi = $('#show-inactive', main); if (shi) shi.addEventListener('change', e => { S.showInactive = e.target.checked; route(); });

  // Planung
  $$('.edit .save', main).forEach(b => b.addEventListener('click', async e => { const box = e.target.closest('.edit'); await plan({zeile: box.dataset.key, methode: $('.meth', box).value, betrag: $('.betrag', box).value, steigerung: $('.steig', box).value}); }));
  $$('.reset-row', main).forEach(b => b.addEventListener('click', async e => { await plan({zeile: e.target.dataset.key, alle_ueberschreibungen_loeschen: true}); }));
  $$('td.plan.editable', main).forEach(td => td.addEventListener('dblclick', () => {
    if ($('input', td)) return;
    const key = td.closest('tr').dataset.key, m = td.dataset.month, old = td.firstChild.textContent.replace(/\./g, '').replace(',', '.');
    td.innerHTML = `<input type="text" value="${esc(old === '–' ? '' : old)}" style="width:90px;text-align:right;padding:1px 4px" title="leer = Vorschlag verwenden">`;
    const inp = $('input', td); inp.focus(); inp.select();
    let done = false; const fin = async save => { if (done) return; done = true; if (save) await plan({zeile: key, monat: m, wert: inp.value}); else route(); };
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') fin(true); if (e.key === 'Escape') fin(false); }); inp.addEventListener('blur', () => fin(true));
  }));
  const ps = $('#p_save', main); if (ps) ps.addEventListener('click', () => plan({parameter: {horizont_monate: +$('#p_horizont').value, standard_methode: $('#p_methode').value, inflation_prozent_pa: +$('#p_infl').value, steigerung_einnahmen_prozent_pa: +$('#p_se').value, steigerung_ausgaben_prozent_pa: $('#p_sa').value === '' ? '' : +$('#p_sa').value, rendite_prozent_pa: +$('#p_rendite').value}}));
  const pr = $('#p_reset', main); if (pr) pr.addEventListener('click', () => { if (confirm('Alle Planeinstellungen und Überschreibungen für „' + BN() + '“ löschen?')) plan({zuruecksetzen: true}); });
  $$('.save-loan', main).forEach(b => b.addEventListener('click', e => { const tr = e.target.closest('tr'); plan({darlehen: {[tr.dataset.loan]: {zins_prozent_pa: $('.lz', tr).value, modell: $('.lm', tr).value, zahlung: $('.lp', tr).value}}}); }));
  $$('.save-wert', main).forEach(b => b.addEventListener('click', e => { const tr = e.target.closest('tr'); const p = $('.wp', tr).value, bs = $('.wb', tr).value, br = $('.wbr', tr).value, an = $('.wa', tr).value; plan({wertentwicklung: {[tr.dataset.acct]: (p === '' && bs === '' && !br) ? null : {prozent_pa: p, basis: bs, bereich: br, anteil: an}}}); }));
  $$('.ev-save', main).forEach(b => b.addEventListener('click', e => { const tr = e.target.closest('.ev-row'); const ev = {id: tr.dataset.id || undefined, text: $('.ev-text', tr).value, art: $('.ev-art', tr).value, betrag: $('.ev-betrag', tr).value, monat: $('.ev-monat', tr).value, wiederholung: $('.ev-wdh', tr).value, bis: $('.ev-bis', tr).value, von: $('.ev-von', tr).value, nach: $('.ev-nach', tr).value, aktiv: $('.ev-aktiv', tr).checked}; if (!ev.text.trim()) return toast('Bezeichnung fehlt'); if (!ev.betrag) return toast('Betrag fehlt'); plan({ereignis: ev}); }));
  $$('.ev-del', main).forEach(b => b.addEventListener('click', e => { const tr = e.target.closest('.ev-row'); if (confirm('Ereignis löschen?')) plan({ereignis: {id: tr.dataset.id, loeschen: true}}); }));

  // Buchungen
  const rd = $('#run-dry', main); if (rd) rd.addEventListener('click', () => startRun(true));
  const rl = $('#run-live', main); if (rl) rl.addEventListener('click', () => { if (confirm('Jetzt buchen: Buchungen werden jetzt in MoneyMoney angelegt (nur manuelle Konten). Fortfahren?')) startRun(false); });
  const rr = $('#run-report', main); if (rr) rr.addEventListener('click', async () => { toast('Bericht wird erstellt …', 20000); const r = await api('/api/report', {}); if (!r.ok) toast(r.text || 'MoneyMoney nicht verfügbar', 5000); await loadAll(); route(); });

  // Steuer
  const sj = $('#st-jahr', main); if (sj) sj.addEventListener('change', e => { S.steuerJahr = e.target.value; route(); });
  const se = $('#st-ent', main); if (se) se.addEventListener('change', e => { S.steuerEnt = e.target.value; route(); });
  const sb = $('#st-belege', main); if (sb) sb.addEventListener('click', async () => { try { const r = await belegeApi('/api/receipts/export', {jahr: S.steuerJahr, entitaet: S.steuerEnt}); toast('Export erstellt: ' + r.datei, 8000); } catch (e) { toast(e.message, 6000); } });
  const afa = $('#afa-save', main); if (afa) afa.addEventListener('click', async () => {
    const cfg = JSON.parse(JSON.stringify(S.CFG)); cfg.steuer = cfg.steuer || {}; cfg.steuer.afa = cfg.steuer.afa || {};
    $$('.afa', main).forEach(i => { const o = i.dataset.obj; cfg.steuer.afa[o] = typeof cfg.steuer.afa[o] === 'object' && cfg.steuer.afa[o] ? cfg.steuer.afa[o] : {}; if (i.value === '') delete cfg.steuer.afa[o][S.steuerJahr]; else cfg.steuer.afa[o][S.steuerJahr] = parseFloat(i.value); });
    await saveConfig(cfg, document.createElement('div')); toast('AfA gespeichert – wirkt nach dem nächsten Abgleich');
  });

  // Umsaetze & Belege
  const uf = S.uf;
  const bindF = (id, key, prop = 'value') => { const el = $(id, main); if (el) el.addEventListener('change', e => { uf[key] = e.target[prop]; S.sel.clear(); route(); }); };
  bindF('#uf-ent', 'entitaet'); bindF('#uf-jahr', 'jahr'); bindF('#uf-konto', 'konto'); bindF('#uf-ob', 'ohne_beleg', 'checked'); bindF('#uf-ok', 'ohne_kategorie', 'checked');
  const q = $('#uf-q', main); if (q) { let t; q.addEventListener('input', e => { clearTimeout(t); t = setTimeout(() => { uf.q = e.target.value; route().then(() => { const n = $('#uf-q'); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }); }, 350); }); }
  $$('.seg button[data-r]', main).forEach(b => b.addEventListener('click', () => { uf.richtung = b.dataset.r; route(); }));
  const tbl = $('#ums-table', main);
  if (tbl) {
    $$('tbody tr', tbl).forEach(tr => {
      const id = +tr.dataset.id;
      tr.addEventListener('click', e => { if (e.target.closest('input,button,a')) return; openDrawer(id); });
      $('.sel', tr).addEventListener('change', e => { if (e.target.checked) S.sel.add(id); else S.sel.delete(id); tr.classList.toggle('sel', e.target.checked); if (S.sel.size <= 1) route(); });
      const ab = $('.add-beleg', tr); if (ab) ab.addEventListener('click', () => pickFiles(id, false));
      tr.addEventListener('dragover', e => { e.preventDefault(); tr.classList.add('sel'); }); tr.addEventListener('dragleave', () => tr.classList.toggle('sel', S.sel.has(id)));
      tr.addEventListener('drop', async e => { e.preventDefault(); tr.classList.toggle('sel', S.sel.has(id)); await uploadFiles(id, e.dataTransfer.files); });
    });
    $('#sel-all', tbl).addEventListener('change', e => { S.sel.clear(); if (e.target.checked) UMS.umsaetze.forEach(u => S.sel.add(u.id)); route(); });
  }
  const bc = $('#bulk-clear', main); if (bc) bc.addEventListener('click', () => { S.sel.clear(); route(); });
  const bk = $('#bulk-cat-btn', main); if (bk) bk.addEventListener('click', async () => { const kat = $('#bulk-cat').value; if (!kat) return toast('Kategorie wählen'); if (!confirm(S.sel.size + ' Umsätzen die Kategorie „' + kat + '“ zuweisen?')) return; try { const r = await api('/api/transactions/category', {ids: [...S.sel], kategorie: kat}); toast(r.anzahl + ' kategorisiert'); S.sel.clear(); route(); } catch (e) { toast(e.message, 6000); } });
  const bf = $('#bl-folder', main); if (bf) bf.addEventListener('click', async () => { try { await belegeApi('/api/receipts/open', {}); } catch (e) { toast(e.message, 5000); } });
  const be = $('#bl-export', main); if (be) be.addEventListener('click', async () => { const jahr = prompt('Jahr (leer = alle):', uf.jahr || new Date().getFullYear()); if (jahr === null) return; try { const r = await belegeApi('/api/receipts/export', {jahr, entitaet: uf.entitaet}); toast('Export erstellt: ' + r.datei, 9000); } catch (e) { toast(e.message, 6000); } });

  // Regeln
  const al = $('#add-loan', main); if (al) al.addEventListener('click', () => { $('#loans').insertAdjacentHTML('beforeend', loanForm({name: 'Neues Darlehen', ab_datum: new Date().toISOString().slice(0, 10), zins: {modell: 'jahresbasis', satz: [], buchungstag: 'mit_rate'}, buchung: {kategorie_tilgung: 'Umbuchung'}}, $$('#loans .item').length)); bindDel(main); });
  const ab = $('#add-bet', main); if (ab) ab.addEventListener('click', () => { $('#bets').insertAdjacentHTML('beforeend', mirrorForm({name: 'Neue Beteiligung', anteil: 0.5}, $$('#bets .item').length, 'bet')); bindDel(main); });
  const am = $('#add-mirror', main); if (am) am.addEventListener('click', () => { $('#mirrors').insertAdjacentHTML('beforeend', mirrorForm({name: 'Neuer Spiegel', faktor: -1}, $$('#mirrors .item').length, 'mirror')); bindDel(main); });
  const sr = $('#save-rules', main); if (sr) sr.addEventListener('click', () => saveConfig(collectRules(), $('#findings')));
  bindDel(main);

  // Kategorien
  const sk = $('#save-kats', main); if (sk) sk.addEventListener('click', () => {
    const cfg = JSON.parse(JSON.stringify(S.CFG)); const kf = cfg.kapitalfluss = cfg.kapitalfluss || {};
    kf.kategorie_zuordnung = {}; kf.kategorie_zu_konto = {};
    $$('tr[data-cat]', main).forEach(tr => { const c = tr.dataset.cat; if ($('.k-sek', tr).value) kf.kategorie_zuordnung[c] = $('.k-sek', tr).value; if ($('.k-depot', tr).value) kf.kategorie_zu_konto[c] = $('.k-depot', tr).value; });
    kf.umbuchungs_kategorien = $('#k-umb').value.split(';').map(x => x.trim()).filter(Boolean);
    kf.beteiligungs_gruppen = $$('.k-bg').map(s => s.value).filter(Boolean);
    saveConfig(cfg, $('#findings-k'));
  });

  // Einstellungen
  const ss = $('#save-settings', main); if (ss) ss.addEventListener('click', () => saveConfig(collectSettings(), $('#findings-e')));
  const cb = $('#check-btn', main); if (cb) cb.addEventListener('click', async () => { toast('Prüfe …'); const r = await api('/api/check', {}); if (!r.verfuegbar) { showFindings($('#findings-e'), [], r.text, 'fehler'); return; } S.KONTEN = r.konten; S.KATS = r.kategorien || S.KATS; showFindings($('#findings-e'), r.befunde, 'Geprüft gegen den aktuellen Stand von MoneyMoney (' + r.konten.length + ' Konten).', 'ok'); });
  const ap = $('#add-pos', main); if (ap) ap.addEventListener('click', e => { e.target.insertAdjacentHTML('beforebegin', posRow('', '')); bindDel(main); });
  const pw = $('#pw-save', main); if (pw) pw.addEventListener('click', async () => { try { await api('/api/password', {alt: $('#pw-alt').value, neu: $('#pw-neu').value}); toast('Passwort geändert'); $('#pw-alt').value = $('#pw-neu').value = ''; } catch (e) { toast(e.message, 4000); } });
  const tmx = $('#tm-ex', main); if (tmx) tmx.addEventListener('click', async () => { const r = await api('/api/timemachine-exclusion', {ausschliessen: true}); toast(r.ok ? 'Vom Time-Machine-Backup ausgeschlossen' : 'Fehler: ' + r.text, 4000); });
  const tmi = $('#tm-in', main); if (tmi) tmi.addEventListener('click', async () => { const r = await api('/api/timemachine-exclusion', {ausschliessen: false}); toast(r.ok ? 'Ausschluss aufgehoben' : 'Fehler: ' + r.text, 4000); });
  for (const [id, url] of [['#diag', '/api/diagnostics'], ['#diag2', '/api/diagnostics'], ['#diag3', '/api/diagnostics?names=1'], ['#bk-save', '/api/backup']]) { const d = $(id, main); if (d) d.addEventListener('click', () => download(url)); }
  const swc = $('#sw-clear', main); if (swc) swc.addEventListener('click', async () => { try { const ks = await caches.keys(); await Promise.all(ks.filter(k => k === 'kontor-data').map(k => caches.delete(k))); toast('Gespeicherte Daten gelöscht'); } catch (e) { toast('Nicht möglich: ' + e.message, 4000); } });
  const rs = $('#rs-go', main); if (rs) rs.addEventListener('click', async () => {
    const pw = $('#rs-pw').value, withPw = $('#rs-pw-reset').checked;
    if (!pw) return showFindings($('#rs-report'), [], 'Passwort eingeben.', 'fehler');
    if (!confirm('Wirklich alle Kontor-Daten auf diesem Mac löschen (Einstellungen, Regeln, Immobilien, Planung, Kategorien, Verlauf, Belegindex)' + (withPw ? ' und das Passwort zurücksetzen' : '') + '? Belegdateien und Protokoll bleiben. Vorher eine Sicherung herunterladen!')) return;
    try { const r = await api('/api/reset', {passwort: pw, mit_passwort: withPw}); toast('Zurückgesetzt – Neustart der Oberfläche', 4000); setTimeout(() => location.reload(), 1200); }
    catch (e) { showFindings($('#rs-report'), [], e.message, 'fehler'); } });

  // Pakete
  const pe = $('#pk-export', main); if (pe) pe.addEventListener('click', () => download(`/api/package/export?name=${encodeURIComponent($('#pk-name').value || 'Kontor-Einstellungen')}&without_uuid=${$('#pk-nouuid').checked ? 1 : 0}&with_plan=${$('#pk-plan').checked ? 1 : 0}`));
  const pp = $('#pk-pick', main); if (pp) pp.addEventListener('click', () => { const inp = $('#file-input'); inp.value = ''; inp.setAttribute('accept', '.json'); inp.removeAttribute('capture'); inp.onchange = () => { if (inp.files[0]) readPkgFile(inp.files[0]); }; inp.click(); });
  const pd = $('#pk-drop', main); if (pd) { pd.addEventListener('dragover', e => { e.preventDefault(); pd.classList.add('over'); }); pd.addEventListener('dragleave', () => pd.classList.remove('over')); pd.addEventListener('drop', e => { e.preventDefault(); pd.classList.remove('over'); if (e.dataTransfer.files[0]) readPkgFile(e.dataTransfer.files[0]); }); if (PKG) pkgPreview(); }

  // Updates
  const uc = $('#up-check', main); if (uc) uc.addEventListener('click', async () => { toast('Prüfe …'); await api('/api/update/check', {}); S.STATUS = await api('/api/status'); route(); });
  const ui = $('#up-install', main); if (ui) ui.addEventListener('click', async () => { if (!confirm('Update installieren und Dienst neu starten?')) return; toast('Update wird installiert …', 30000); try { const r = await api('/api/update/install', {}); toast(r.text, 8000); if (r.ok && r.neustart) setTimeout(() => location.reload(), 6000); } catch (e) { toast(e.message, 8000); } });
  const lr = $('#log-refresh', main); if (lr) lr.addEventListener('click', route);
  const ls = $('#log-show', main); if (ls) ls.addEventListener('click', async () => { try { await api('/api/file/reveal', {pfad: ((S.STATUS.ablage || {}).ordner || '') + '/kontor.log'}); } catch (e) { toast(e.message, 5000); } });
}
function bindDel(main) {
  $$('.item .del', main).forEach(b => { b.onclick = e => e.target.closest('.item').remove(); });
  $$('.del-row', main).forEach(b => { b.onclick = e => e.target.closest('.row').remove(); });
}
async function rebuildReport(fresh) {
  // fresh: zuerst MoneyMoney neu lesen (wartet); sonst aus dem letzten Stand neu rechnen -- läuft im Hintergrund,
  // der Status unten links zeigt den Fortschritt, danach werden die Daten automatisch neu geladen
  toast(fresh ? 'MoneyMoney wird gelesen, Auswertung wird erstellt …' : 'Auswertung wird im Hintergrund aktualisiert …', fresh ? 60000 : 4000);
  try {
    let r = fresh ? await api('/api/report', {}) : await api('/api/report/rebuild', {});
    if (!r.ok && fresh) r = await api('/api/report/rebuild', {});
    if (!r.ok) { toast(r.text || 'MoneyMoney nicht verfügbar – Bericht später erstellen', 7000); await loadAll(); route(); return false; }
    if (r.ok === 'angefordert') { await pollStatus(); return true; }
  } catch (e) { toast(e.message, 7000); return false; }
  await loadAll(); route(); toast('Auswertung aktualisiert'); return true;
}
async function plan(body) {
  try { await api('/api/plan', Object.assign({bereich: S.bereich}, body)); S.DATA = await api('/api/dataset'); route(); toast('Plan gespeichert'); }
  catch (e) { toast('Fehler: ' + e.message, 4000); }
}
async function syncNow() {
  // Wie der automatische Abgleich, nur sofort: MoneyMoney lesen, Regeln anwenden (Testmodus laut Einstellung), Auswertung bauen
  if (SYNC.busy) return;
  SYNC.busy = true; statusMini();
  try {
    try { await api('/api/run', {force: false}); }
    catch (e) { if (!/läuft bereits/.test(e.message)) throw e; }
    let tries = 0;
    do { await new Promise(r => setTimeout(r, tries ? 1500 : 800)); S.STATUS = await api('/api/status'); statusMini(); } while (S.STATUS.dienst.laeuft && tries++ < 200);
    const r = S.STATUS.letztes_ergebnis || {};
    await loadAll(); route();
    const n = (r.vorschlaege || []).length;
    const msg = r.status === 'unveraendert' ? 'Synchronisiert – keine Änderung in MoneyMoney'
      : r.status === 'ok' ? 'Synchronisiert' + (r.geschrieben ? ' – ' + r.geschrieben + ' gebucht' : '') + (r.probelauf && n ? ' – ' + n + ' Buchungsvorschläge (Testmodus)' : '') + ((r.warnungen || []).length ? ' – ' + r.warnungen.length + ' Hinweise unter „Buchungen“' : '')
      : (r.text || r.fehler || 'Synchronisiert');
    toast(msg, r.status === 'nicht_verfuegbar' || r.status === 'fehler' ? 7000 : 4500);
  } catch (e) { toast('Synchronisieren fehlgeschlagen: ' + e.message, 6000); }
  finally { SYNC.busy = false; statusMini(); }
}
async function startRun(dry) {
  try { await api('/api/run', {probelauf: dry, force: true}); toast(dry ? 'Abgleich gestartet (Test) …' : 'Abgleich mit Buchung gestartet …'); } catch (e) { toast(e.message, 4000); return; }
  let tries = 0;
  const poll = async () => { S.STATUS = await api('/api/status'); statusMini(); if (S.STATUS.dienst.laeuft && tries++ < 150) return setTimeout(poll, 2000); await loadAll(); route(); const r = S.STATUS.letztes_ergebnis; toast(r && r.text ? r.text : 'Abgleich beendet', 6000); };
  setTimeout(poll, 1500);
}

window.addEventListener('hashchange', route);
document.addEventListener('click', e => { const b = e.target.closest('#modus-seg button'); if (b) { S.modus = b.dataset.m; route(); } });
document.addEventListener('change', e => { const id = e.target.id; if (id === 'planan') { S.plan = e.target.checked; route(); } else if (id === 'realan') { S.real = e.target.checked; route(); } else if (id === 'nullzeilen') { S.nullzeilen = e.target.checked; route(); } });
$('#menu-btn').addEventListener('click', () => $('.side').classList.toggle('open'));
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });
try { const s = JSON.parse(localStorage.getItem('kontor.ui') || '{}'); Object.assign(S, {modus: s.modus || S.modus, plan: s.plan !== false, real: !!s.real, bereich: s.bereich || null}); } catch (e) {}
window.addEventListener('beforeunload', () => { try { localStorage.setItem('kontor.ui', JSON.stringify({modus: S.modus, plan: S.plan, real: S.real, bereich: S.bereich})); } catch (e) {} });
setInterval(async () => { if (S.csrf && !document.hidden && !OFFLINE.mode) { try { await pollStatus(); } catch (e) {} } }, 30000);
checkSession();
